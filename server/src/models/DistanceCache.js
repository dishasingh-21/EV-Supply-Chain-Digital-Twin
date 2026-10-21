const mongoose = require("mongoose");

// The original frontend cached OSRM distances in an in-memory `Map` that was
// thrown away on every page refresh. Persisting it in Mongo means repeated
// route requests between the same two points (very common — the station
// graph is mostly fixed) skip the OSRM round-trip entirely after the first hit.
const distanceCacheSchema = new mongoose.Schema(
  {
    // Order-independent key: "lat1,lon1|lat2,lon2" with the smaller pair first.
    key: { type: String, required: true, unique: true, index: true },
    distanceKm: { type: Number, required: true },
    source: { type: String, enum: ["osrm", "haversine"], required: true },
  },
  { timestamps: true }
);

module.exports = mongoose.model("DistanceCache", distanceCacheSchema);
