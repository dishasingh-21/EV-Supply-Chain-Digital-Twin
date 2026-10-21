require("dotenv").config();
const fs = require("fs");
const path = require("path");
const mongoose = require("mongoose");
const XLSX = require("xlsx");
const { connectDB } = require("../src/config/db");
const Warehouse = require("../src/models/Warehouse");

// Reads server/data/warehouses.xlsx (sheet "Warehouses") and replaces the
// warehouses collection with its contents. Re-run any time you edit the
// spreadsheet — no server restart needed, the API reads Mongo per request.
//
// Pass a different file with:  node scripts/importWarehousesExcel.js path/to/file.xlsx

const SHEET_NAME = "Warehouses";
const REQUIRED = ["code", "name", "town", "lat", "lon"];

function toNumber(value) {
  if (typeof value === "number") return value;
  if (typeof value === "string" && value.trim() !== "") {
    const n = Number(value.trim());
    return Number.isNaN(n) ? null : n;
  }
  return null;
}

function toBoolean(value, fallback = true) {
  if (value === undefined || value === null || value === "") return fallback;
  if (typeof value === "boolean") return value;
  const s = String(value).trim().toLowerCase();
  if (["true", "yes", "y", "1"].includes(s)) return true;
  if (["false", "no", "n", "0"].includes(s)) return false;
  return fallback;
}

function parseRows(rows) {
  const errors = [];
  const seenCodes = new Set();
  const warehouses = [];

  rows.forEach((row, i) => {
    // +2 because row 1 is the header and arrays are 0-indexed — this makes the
    // number match what the user sees in Excel.
    const excelRow = i + 2;

    // Skip fully blank rows rather than erroring on them.
    const isBlank = Object.values(row).every(
      (v) => v === undefined || v === null || String(v).trim() === ""
    );
    if (isBlank) return;

    const missing = REQUIRED.filter(
      (f) => row[f] === undefined || row[f] === null || String(row[f]).trim() === ""
    );
    if (missing.length) {
      errors.push(`Row ${excelRow}: missing required field(s): ${missing.join(", ")}`);
      return;
    }

    const lat = toNumber(row.lat);
    const lon = toNumber(row.lon);
    if (lat === null || lon === null) {
      errors.push(`Row ${excelRow}: lat/lon must be numbers (got lat="${row.lat}", lon="${row.lon}")`);
      return;
    }
    if (lat < -90 || lat > 90) {
      errors.push(`Row ${excelRow}: lat ${lat} is outside -90..90`);
      return;
    }
    if (lon < -180 || lon > 180) {
      errors.push(`Row ${excelRow}: lon ${lon} is outside -180..180`);
      return;
    }

    const code = String(row.code).trim();
    if (seenCodes.has(code)) {
      errors.push(`Row ${excelRow}: duplicate code "${code}" — codes must be unique`);
      return;
    }
    seenCodes.add(code);

    warehouses.push({
      code,
      name: String(row.name).trim(),
      town: String(row.town).trim(),
      lat,
      lon,
      capacityUnits: toNumber(row.capacityUnits) ?? 0,
      active: toBoolean(row.active, true),
    });
  });

  return { warehouses, errors };
}

async function main() {
  const fileArg = process.argv[2];
  const filePath = fileArg
    ? path.resolve(fileArg)
    : path.join(__dirname, "..", "data", "warehouses.xlsx");

  if (!fs.existsSync(filePath)) {
    console.error(
      `[import] file not found: ${filePath}\n` +
      `         Put your warehouse spreadsheet at server/data/warehouses.xlsx, ` +
      `or pass a path: node scripts/importWarehousesExcel.js <file.xlsx>`
    );
    process.exit(1);
  }

  const wb = XLSX.readFile(filePath);
  const sheet = wb.Sheets[SHEET_NAME] || wb.Sheets[wb.SheetNames[0]];
  if (!sheet) {
    console.error(`[import] no sheet named "${SHEET_NAME}" and the workbook is empty`);
    process.exit(1);
  }
  if (!wb.Sheets[SHEET_NAME]) {
    console.warn(`[import] no sheet named "${SHEET_NAME}" — falling back to "${wb.SheetNames[0]}"`);
  }

  const rows = XLSX.utils.sheet_to_json(sheet, { defval: "" });
  const { warehouses, errors } = parseRows(rows);

  if (errors.length) {
    console.error(`[import] aborted — ${errors.length} problem(s) found, nothing was written:`);
    errors.forEach((e) => console.error(`  - ${e}`));
    process.exit(1);
  }

  if (!warehouses.length) {
    console.error("[import] no data rows found in the sheet");
    process.exit(1);
  }

  const uri = process.env.MONGO_URI || "mongodb://127.0.0.1:27017/ev_route_optimizer";
  await connectDB(uri);

  await Warehouse.deleteMany({});
  // insertMany (not create) does NOT run Mongoose's pre('save') hook, so we
  // build the GeoJSON `location` explicitly here to keep the 2dsphere index
  // populated for $near queries.
  await Warehouse.insertMany(
    warehouses.map((w) => ({
      ...w,
      location: { type: "Point", coordinates: [w.lon, w.lat] },
    }))
  );

  const activeCount = warehouses.filter((w) => w.active).length;
  console.log(
    `[import] inserted ${warehouses.length} warehouses from ${path.basename(filePath)} ` +
    `(${activeCount} active, ${warehouses.length - activeCount} inactive)`
  );

  await mongoose.disconnect();
}

main().catch((err) => {
  console.error("[import] failed:", err);
  process.exit(1);
});
