const RecommendedStation = require("../models/RecommendedStation");

// GET /api/recommendations?decision=1
async function listRecommendations(req, res, next) {
  try {
    const filter = {};
    if (req.query.decision !== undefined) filter.decision = Number(req.query.decision);
    const stations = await RecommendedStation.find(filter).sort({ demandScore: -1 }).lean();
    res.json({ count: stations.length, stations });
  } catch (err) {
    next(err);
  }
}

module.exports = { listRecommendations };
