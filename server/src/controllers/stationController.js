const Station = require("../models/Station");
const { invalidate } = require("../services/graphCache.service");

function escapeRegex(str) {
  return str.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
}

// GET /api/stations?town=Ajmer
async function listStations(req, res, next) {
  try {
    const filter = {};
    if (req.query.town) filter.town = new RegExp(`^${escapeRegex(String(req.query.town))}$`, "i");
    const stations = await Station.find(filter).lean();
    res.json({ count: stations.length, stations });
  } catch (err) {
    next(err);
  }
}

// GET /api/stations/near?lat=..&lon=..&km=50
async function nearStations(req, res, next) {
  try {
    const { lat, lon, km = 50 } = req.query;
    if (lat === undefined || lon === undefined) {
      return res.status(400).json({ error: "lat and lon query params are required" });
    }
    const stations = await Station.find({
      location: {
        $near: {
          $geometry: { type: "Point", coordinates: [Number(lon), Number(lat)] },
          $maxDistance: Number(km) * 1000,
        },
      },
    }).lean();
    res.json({ count: stations.length, stations });
  } catch (err) {
    next(err);
  }
}

// POST /api/stations  { town, subtown, lat, lon }
// Note: adding a station here does NOT automatically create graph edges for
// it — run `npm run seed` / the precompute script afterwards so it becomes
// reachable by the A* planner.
async function createStation(req, res, next) {
  try {
    const { town, subtown, lat, lon, isCharging = true } = req.body;
    if (!town || !subtown || lat === undefined || lon === undefined) {
      return res.status(400).json({ error: "town, subtown, lat, lon are required" });
    }
    const station = await Station.create({ town, subtown, lat, lon, isCharging });
    invalidate(); // next route request will reload the graph, though edges still need precomputing
    res.status(201).json(station);
  } catch (err) {
    next(err);
  }
}

module.exports = { listStations, nearStations, createStation };
