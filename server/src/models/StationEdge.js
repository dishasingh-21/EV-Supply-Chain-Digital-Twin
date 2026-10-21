const mongoose = require("mongoose");

// Precomputed edges between two existing stations that are within MAX_RANGE
// of each other (haversine distance). This is the MongoDB equivalent of the
// `distances` map inside the original workable_stations.json — built once
// by scripts/precomputeAdjacency.js instead of shipping a 5.7MB static file
// to the browser.
const stationEdgeSchema = new mongoose.Schema(
  {
    from: { type: mongoose.Schema.Types.ObjectId, ref: "Station", required: true, index: true },
    to: { type: mongoose.Schema.Types.ObjectId, ref: "Station", required: true, index: true },
    distanceKm: { type: Number, required: true },
  },
  { timestamps: true }
);

stationEdgeSchema.index({ from: 1, to: 1 }, { unique: true });

module.exports = mongoose.model("StationEdge", stationEdgeSchema);
