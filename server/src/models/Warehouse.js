const mongoose = require("mongoose");

// Pickup points for deliveries. Deliberately mirrors the Station schema's
// lat/lon + GeoJSON pattern (same pre-save hook, same 2dsphere index) so it
// plugs into the existing distance/route services without new geo logic.
const warehouseSchema = new mongoose.Schema(
  {
    code: { type: String, required: true, unique: true, index: true }, // e.g. "WH01"
    name: { type: String, required: true }, // e.g. "Jaipur Fulfillment Center"
    town: { type: String, required: true, index: true },
    lat: { type: Number, required: true },
    lon: { type: Number, required: true },
    capacityUnits: { type: Number, default: 0 },
    active: { type: Boolean, default: true },
    location: {
      type: { type: String, enum: ["Point"], default: "Point" },
      coordinates: { type: [Number], default: [0, 0] }, // [lon, lat]
    },
  },
  { timestamps: true }
);

warehouseSchema.pre("save", function setLocation(next) {
  this.location = { type: "Point", coordinates: [this.lon, this.lat] };
  next();
});

warehouseSchema.index({ location: "2dsphere" });

module.exports = mongoose.model("Warehouse", warehouseSchema);
