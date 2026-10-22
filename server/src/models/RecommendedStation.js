const mongoose = require("mongoose");

// Candidate NEW station locations — output of the set-covering / RTO-wise
// priority analysis (the "Operations Research part" spreadsheet in the
// original project). `decision` mirrors the solver's Xi variable: 1 = build,
// 0 = evaluated but not selected. Keeping both lets the map show what was
// considered, not just what was chosen.
const recommendedStationSchema = new mongoose.Schema(
  {
    town: { type: String, required: true, index: true },
    subtown: { type: String, required: true },
    lat: { type: Number, required: true },
    lon: { type: Number, required: true },
    populationScore: Number,
    tourismScore: Number,
    transitScore: Number,
    adminScore: Number,
    existingEvStations: Number,
    demandScore: Number,
    decision: { type: Number, enum: [0, 1], required: true },
    priority: String,
    note: String,
    location: {
      type: { type: String, enum: ["Point"], default: "Point" },
      coordinates: { type: [Number], default: [0, 0] },
    },
  },
  { timestamps: true }
);

recommendedStationSchema.pre("save", function setLocation(next) {
  this.location = { type: "Point", coordinates: [this.lon, this.lat] };
  next();
});

recommendedStationSchema.index({ location: "2dsphere" });

module.exports = mongoose.model("RecommendedStation", recommendedStationSchema);
