require("dotenv").config();
const fs = require("fs");
const path = require("path");
const mongoose = require("mongoose");
const { connectDB } = require("../src/config/db");
const RecommendedStation = require("../src/models/RecommendedStation");

async function main() {
  const uri = process.env.MONGO_URI || "mongodb://127.0.0.1:27017/ev_route_optimizer";
  await connectDB(uri);

  const dataPath = path.join(__dirname, "..", "data", "recommended_stations.json");
  const recommended = JSON.parse(fs.readFileSync(dataPath, "utf-8"));

  await RecommendedStation.deleteMany({});
  // insertMany skips pre('save'), so set the GeoJSON location explicitly.
  await RecommendedStation.insertMany(
    recommended.map((r) => ({
      ...r,
      location: { type: "Point", coordinates: [r.lon, r.lat] },
    }))
  );
  console.log(`[seed] inserted ${recommended.length} recommended stations`);

  await mongoose.disconnect();
}

main().catch((err) => {
  console.error("[seed] failed:", err);
  process.exit(1);
});
