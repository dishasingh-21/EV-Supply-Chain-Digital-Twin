require("dotenv").config();
const fs = require("fs");
const path = require("path");
const mongoose = require("mongoose");
const { connectDB } = require("../src/config/db");
const Warehouse = require("../src/models/Warehouse");

// Reads server/data/warehouses.json — this is YOUR dataset, not a sample
// bundled with the project. See data/warehouses.example.json for the exact
// shape expected (code, name, town, lat, lon, capacityUnits, active).
async function main() {
  const uri = process.env.MONGO_URI || "mongodb://127.0.0.1:27017/ev_route_optimizer";

  const dataPath = path.join(__dirname, "..", "data", "warehouses.json");
  if (!fs.existsSync(dataPath)) {
    console.error(
      `[seed] server/data/warehouses.json not found.\n` +
      `       Add your warehouse dataset there — see server/data/warehouses.example.json ` +
      `for the expected fields (code, name, town, lat, lon, capacityUnits, active).`
    );
    process.exit(1);
  }

  await connectDB(uri);

  const warehouses = JSON.parse(fs.readFileSync(dataPath, "utf-8"));

  await Warehouse.deleteMany({});
  // insertMany skips pre('save'), so set the GeoJSON location explicitly —
  // otherwise /api/warehouses/nearest ($near) silently returns nothing.
  await Warehouse.insertMany(
    warehouses.map((w) => ({
      ...w,
      location: { type: "Point", coordinates: [w.lon, w.lat] },
    }))
  );
  console.log(`[seed] inserted ${warehouses.length} warehouses`);

  await mongoose.disconnect();
}

main().catch((err) => {
  console.error("[seed] failed:", err);
  process.exit(1);
});
