require("dotenv").config();
const mongoose = require("mongoose");
const { connectDB } = require("../src/config/db");
const Station = require("../src/models/Station");
const StationEdge = require("../src/models/StationEdge");
const { haversine } = require("../src/services/haversine.service");

const MAX_RANGE_KM = Number(process.env.MAX_RANGE_KM || 400);

async function main() {
  const uri = process.env.MONGO_URI || "mongodb://127.0.0.1:27017/ev_route_optimizer";
  await connectDB(uri);

  const stations = await Station.find().lean();
  console.log(`[precompute] ${stations.length} stations loaded`);

  await StationEdge.deleteMany({});

  const edges = [];
  for (let i = 0; i < stations.length; i += 1) {
    for (let j = i + 1; j < stations.length; j += 1) {
      const d = haversine(stations[i], stations[j]);
      if (d <= MAX_RANGE_KM) {
        edges.push({ from: stations[i]._id, to: stations[j]._id, distanceKm: d });
      }
    }
  }

  console.log(`[precompute] writing ${edges.length} edges...`);
  // insertMany in batches to avoid one giant payload for large station sets
  const BATCH = 5000;
  for (let i = 0; i < edges.length; i += BATCH) {
    await StationEdge.insertMany(edges.slice(i, i + BATCH), { ordered: false });
  }

  console.log("[precompute] done");
  await mongoose.disconnect();
}

main().catch((err) => {
  console.error("[precompute] failed:", err);
  process.exit(1);
});
