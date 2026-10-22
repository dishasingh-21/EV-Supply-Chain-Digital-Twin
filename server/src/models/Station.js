const mongoose = require("mongoose");

// Existing, already-built charging stations. This is the dataset your original
// workable_stations.json / CoordinateData csv represented, now living in MongoDB
// instead of a static file bundled with the frontend.
const stationSchema = new mongoose.Schema(
  {
    town: { type: String, required: true, index: true },
    subtown: { type: String, required: true },
    lat: { type: Number, required: true },
    lon: { type: Number, required: true },
    isCharging: { type: Boolean, default: true },
    // GeoJSON point, kept in sync with lat/lon via the pre-save hook below.
    // Lets us use MongoDB's native $near / $geoWithin queries instead of
    // pulling every station down and filtering in JS.
    location: {
      type: { type: String, enum: ["Point"], default: "Point" },
      coordinates: { type: [Number], default: [0, 0] }, // [lon, lat]
    },
  },
  { timestamps: true }
);

stationSchema.pre("save", function setLocation(next) {
  this.location = { type: "Point", coordinates: [this.lon, this.lat] };
  next();
});

stationSchema.index({ location: "2dsphere" });

module.exports = mongoose.model("Station", stationSchema);
