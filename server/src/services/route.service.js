const { haversine } = require("./haversine.service");
const { getDrivingDistanceKm, getFullRoute, geocode } = require("./osrm.service");
const { getGraph } = require("./graphCache.service");
const { PriorityQueue } = require("./priorityQueue");

const MAX_RANGE_KM = Number(process.env.MAX_RANGE_KM || 400);
const AVG_SPEED_KMH = Number(process.env.AVG_SPEED_KMH || 60);
const CHARGE_STOP_MINUTES = Number(process.env.CHARGE_STOP_MINUTES || 30);
const MAX_ITERATIONS = 20000;

class RouteError extends Error {
  constructor(message, status = 400) {
    super(message);
    this.status = status;
  }
}

async function isDirectPossible(start, end, initialRange) {
  const d = await getDrivingDistanceKm(start, end);
  return d <= initialRange;
}

/**
 * A* over [start, ...chargingStations, end]. Identical logic to the
 * original client-side aStar in script2.js: battery resets to MAX_RANGE_KM
 * at every charging stop, haversine is the (admissible) heuristic, and edges
 * are only traversable if the remaining battery covers their length.
 */
function aStar(nodes, startIdx, endIdx, adj) {
  const n = nodes.length;
  const g = new Array(n).fill(Infinity);
  const f = new Array(n).fill(Infinity);
  const parent = new Array(n).fill(null);
  const visited = new Set();

  const open = new PriorityQueue();
  g[startIdx] = 0;
  f[startIdx] = haversine(nodes[startIdx], nodes[endIdx]);
  open.add({ idx: startIdx, f: f[startIdx], battery: nodes[startIdx]._initialRange });

  let iterations = 0;
  while (!open.isEmpty()) {
    const { idx: current, battery } = open.remove();
    const visitKey = `${current}-${Math.floor(battery / 25)}`;
    if (visited.has(visitKey)) continue;
    visited.add(visitKey);

    if (current === endIdx) break;

    iterations += 1;
    if (iterations > MAX_ITERATIONS) return null;

    const neighbors = adj[current] || [];
    for (const { node: neighborIdx, dist: d } of neighbors) {
      if (d > battery) continue;

      const isEndNode = neighborIdx === endIdx;
      const newBattery = isEndNode ? battery - d : MAX_RANGE_KM;

      const newG = g[current] + d;
      if (newG >= g[neighborIdx]) continue;

      g[neighborIdx] = newG;
      const h = haversine(nodes[neighborIdx], nodes[endIdx]);
      f[neighborIdx] = g[neighborIdx] + h;
      parent[neighborIdx] = { node: current, battery };
      open.add({ idx: neighborIdx, f: f[neighborIdx], battery: newBattery });
    }
  }

  if (g[endIdx] === Infinity) return null;

  const path = [];
  let cursor = endIdx;
  while (cursor !== startIdx) {
    path.push(nodes[cursor]);
    if (!parent[cursor]) return null; // unreachable / broken chain
    cursor = parent[cursor].node;
  }
  path.push(nodes[startIdx]);
  path.reverse();
  return path;
}

/**
 * Core planner: works directly off {lat, lon, name} points for both ends,
 * with no geocoding involved. Both the place-name planner (planRoute, below)
 * and the warehouse delivery planner (planDeliveryRoute, in
 * deliveryRoute.service.js) build their start/end points and call this.
 * Returns { route, viaDirectRoute, legs, totalDistanceKm, etaMinutes }.
 */
async function planRouteByCoords({ startLoc, endLoc, batteryPercent }) {
  if (!startLoc || !endLoc) throw new RouteError("startLoc and endLoc are required");
  if (
    !Number.isFinite(startLoc.lat) || !Number.isFinite(startLoc.lon) ||
    !Number.isFinite(endLoc.lat) || !Number.isFinite(endLoc.lon)
  ) {
    throw new RouteError("startLoc/endLoc must have numeric lat and lon");
  }
  if (!Number.isFinite(batteryPercent) || batteryPercent <= 0 || batteryPercent > 100) {
    throw new RouteError("batteryPercent must be a number between 1 and 100");
  }

  const startPlace = startLoc.name || "Start";
  const endPlace = endLoc.name || "End";
  const initialRange = MAX_RANGE_KM * (batteryPercent / 100);

  let direct = false;
  try {
    direct = await isDirectPossible(startLoc, endLoc, initialRange);
  } catch (err) {
    direct = false; // fall through to A* if OSRM/direct check fails
  }

  let routeNodes;
  if (direct) {
    routeNodes = [
      { ...startLoc, isCharging: false, name: startPlace },
      { ...endLoc, isCharging: false, name: endPlace },
    ];
  } else {
    const { stations, adjacency } = await getGraph();

    // Node 0 = start, nodes 1..N = stations, node N+1 = end.
    const nodes = [
      { ...startLoc, isCharging: false, name: startPlace, _initialRange: initialRange },
      ...stations.map((s) => ({
        _id: String(s._id),
        lat: s.lat,
        lon: s.lon,
        name: s.subtown || s.town,
        isCharging: true,
      })),
      { ...endLoc, isCharging: false, name: endPlace },
    ];
    const startIdx = 0;
    const endIdx = nodes.length - 1;

    // Build an index-based adjacency list for this request: reuse the
    // precomputed station<->station edges, and add dynamic edges from
    // start->reachable stations and stations->end.
    const stationIdToIdx = new Map(stations.map((s, i) => [String(s._id), i + 1]));
    const adj = Array.from({ length: nodes.length }, () => []);

    stations.forEach((s, i) => {
      const idx = i + 1;
      const d = haversine(startLoc, s);
      if (d <= initialRange) adj[startIdx].push({ node: idx, dist: d });

      const dToEnd = haversine(s, endLoc);
      if (dToEnd <= MAX_RANGE_KM) adj[idx].push({ node: endIdx, dist: dToEnd });

      const edges = adjacency.get(String(s._id)) || [];
      edges.forEach(({ node: neighborId, dist }) => {
        const neighborIdx = stationIdToIdx.get(neighborId);
        if (neighborIdx !== undefined) adj[idx].push({ node: neighborIdx, dist });
      });
    });

    routeNodes = aStar(nodes, startIdx, endIdx, adj);
    if (!routeNodes) throw new RouteError("No feasible route found within battery constraints.", 422);
  }

  // Draw each leg with a real OSRM route so distances/ETA reflect roads, not
  // straight lines, and so the frontend gets polyline geometry to render.
  const legs = [];
  let totalDistanceKm = 0;
  for (let i = 0; i < routeNodes.length - 1; i += 1) {
    const a = routeNodes[i];
    const b = routeNodes[i + 1];
    let full = null;
    try {
      full = await getFullRoute(a, b);
    } catch (err) {
      full = null; // OSRM unreachable: fall back to haversine + straight line
    }
    const distanceKm = full ? full.distanceKm : haversine(a, b);
    totalDistanceKm += distanceKm;
    legs.push({
      from: { name: a.name, lat: a.lat, lon: a.lon, isCharging: !!a.isCharging },
      to: { name: b.name, lat: b.lat, lon: b.lon, isCharging: !!b.isCharging },
      distanceKm: Number(distanceKm.toFixed(2)),
      geometry: full ? full.coordinates : null, // [lon, lat][] or null if OSRM failed
    });
  }

  const chargeStops = routeNodes.filter((p) => p.isCharging).length;
  const drivingMinutes = (totalDistanceKm / AVG_SPEED_KMH) * 60;
  const etaMinutes = Math.round(drivingMinutes + chargeStops * CHARGE_STOP_MINUTES);

  return {
    viaDirectRoute: direct,
    route: routeNodes.map((n) => ({
      name: n.name,
      lat: n.lat,
      lon: n.lon,
      isCharging: !!n.isCharging,
    })),
    legs,
    chargeStops,
    totalDistanceKm: Number(totalDistanceKm.toFixed(2)),
    etaMinutes,
  };
}

/**
 * Place-name planner (the original public API): geocodes both ends via
 * Nominatim, then delegates to planRouteByCoords. Used by the "Starting
 * Point" / "Ending Destination" free-text flow on the planner page.
 */
async function planRoute({ startPlace, endPlace, batteryPercent }) {
  if (!startPlace || !endPlace) throw new RouteError("startPlace and endPlace are required");

  const startLoc = await geocode(startPlace);
  const endLoc = await geocode(endPlace);
  if (!startLoc) throw new RouteError(`Could not find coordinates for "${startPlace}"`, 404);
  if (!endLoc) throw new RouteError(`Could not find coordinates for "${endPlace}"`, 404);

  return planRouteByCoords({ startLoc, endLoc, batteryPercent });
}

module.exports = { planRoute, planRouteByCoords, RouteError, MAX_RANGE_KM };
