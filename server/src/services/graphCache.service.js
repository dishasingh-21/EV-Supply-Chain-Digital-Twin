const Station = require("../models/Station");
const StationEdge = require("../models/StationEdge");

// The station graph (≈700 nodes, ≈170k edges) changes rarely — only when an
// admin adds a station and re-runs the precompute script — so we load it
// once from Mongo and hold it in memory for the life of the process, rather
// than re-querying (or re-shipping a static JSON file to every client) on
// every route request. `invalidate()` clears it so the next request rebuilds.
let cache = null; // { stations: [...], adjacency: Map<stationId, [{node, dist}]> }

async function buildGraph() {
  const stations = await Station.find().lean();
  const edges = await StationEdge.find().lean();

  const adjacency = new Map();
  stations.forEach((s) => adjacency.set(String(s._id), []));

  edges.forEach((e) => {
    const from = String(e.from);
    const to = String(e.to);
    if (!adjacency.has(from) || !adjacency.has(to)) return; // stale edge, orphaned station
    adjacency.get(from).push({ node: to, dist: e.distanceKm });
    adjacency.get(to).push({ node: from, dist: e.distanceKm });
  });

  return { stations, adjacency };
}

async function getGraph() {
  if (!cache) cache = await buildGraph();
  return cache;
}

function invalidate() {
  cache = null;
}

module.exports = { getGraph, invalidate };
