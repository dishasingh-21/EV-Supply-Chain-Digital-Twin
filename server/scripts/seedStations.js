require("dotenv").config();
const fs = require("fs");
const path = require("path");
const mongoose = require("mongoose");
const { connectDB } = require("../src/config/db");
const Station = require("../src/models/Station");

async function main() {
  const uri = process.env.MONGO_URI || "mongodb://127.0.0.1:27017/ev_route_optimizer";
  await connectDB(uri);

  const dataPath = path.join(__dirname, "..", "data", "existing_stations.json");
  const stations = JSON.parse(fs.readFileSync(dataPath, "utf-8"));

  await Station.deleteMany({});
  // insertMany bypasses Mongoose's pre('save') hook, so the GeoJSON `location`
  // field would never be set — which silently breaks the 2dsphere index and
  // every $near query. Build it explicitly here.
  await Station.insertMany(
    stations.map((s) => ({
      ...s,
      location: { type: "Point", coordinates: [s.lon, s.lat] },
    }))
  );
  console.log(`[seed] inserted ${stations.length} stations`);

  await mongoose.disconnect();
}

main().catch((err) => {
  console.error("[seed] failed:", err);
  process.exit(1);
});
