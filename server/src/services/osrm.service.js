const fetch = require("node-fetch");
const DistanceCache = require("../models/DistanceCache");
const { haversine } = require("./haversine.service");

const OSRM_BASE = "https://router.project-osrm.org/route/v1/driving";
const NOMINATIM_BASE = "https://nominatim.openstreetmap.org/search";

function cacheKey(a, b) {
  // Order-independent so A->B and B->A share one row.
  const p1 = `${a.lat},${a.lon}`;
  const p2 = `${b.lat},${b.lon}`;
  return p1 < p2 ? `${p1}|${p2}` : `${p2}|${p1}`;
}

/**
 * Real driving distance between two points, in km, via OSRM.
 * Falls back to haversine (flagged as such in the cache) if OSRM is
 * unreachable or returns no route, so route planning degrades gracefully
 * instead of failing outright.
 */
async function getDrivingDistanceKm(a, b) {
  const key = cacheKey(a, b);
  const cached = await DistanceCache.findOne({ key }).lean();
  if (cached) return cached.distanceKm;

  let distanceKm;
  let source = "osrm";
  try {
    const url = `${OSRM_BASE}/${a.lon},${a.lat};${b.lon},${b.lat}?overview=false`;
    const res = await fetch(url, { timeout: 8000 });
    const data = await res.json();
    if (!data.routes || data.routes.length === 0) throw new Error("no route from OSRM");
    distanceKm = data.routes[0].distance / 1000;
  } catch (err) {
    distanceKm = haversine(a, b);
    source = "haversine";
  }

  await DistanceCache.updateOne(
    { key },
    { $setOnInsert: { key, distanceKm, source } },
    { upsert: true }
  );

  return distanceKm;
}

/**
 * Full OSRM route (geometry + distance) between two points — used only for
 * drawing the final path on the map, not for the A* search itself.
 */
async function getFullRoute(a, b) {
  const url = `${OSRM_BASE}/${a.lon},${a.lat};${b.lon},${b.lat}?overview=full&geometries=geojson`;
  const res = await fetch(url, { timeout: 10000 });
  const data = await res.json();
  if (!data.routes || data.routes.length === 0) return null;
  return {
    distanceKm: data.routes[0].distance / 1000,
    coordinates: data.routes[0].geometry.coordinates, // [lon, lat][]
  };
}

/** Geocode a free-text place name to {lat, lon} via Nominatim. */
async function geocode(place) {
  const url = `${NOMINATIM_BASE}?q=${encodeURIComponent(place)}&format=json&addressdetails=1&limit=1`;
  const res = await fetch(url, {
    timeout: 8000,
    headers: { "User-Agent": "ev-route-optimizer/1.0" }, // Nominatim usage policy requires an identifying UA
  });
  const data = await res.json();
  if (!data.length) return null;
  return { name: place, lat: parseFloat(data[0].lat), lon: parseFloat(data[0].lon) };
}

module.exports = { getDrivingDistanceKm, getFullRoute, geocode };
