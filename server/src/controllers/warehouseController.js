const Warehouse = require("../models/Warehouse");
const { findNearestWarehouse } = require("../services/deliveryRoute.service");

// GET /api/warehouses
async function listWarehouses(req, res, next) {
  try {
    const filter = req.query.active === undefined ? { active: true } : { active: req.query.active === "true" };
    const warehouses = await Warehouse.find(filter).lean();
    res.json({ count: warehouses.length, warehouses });
  } catch (err) {
    next(err);
  }
}

// GET /api/warehouses/nearest?lat=..&lon=..
async function nearestWarehouse(req, res, next) {
  try {
    const { lat, lon } = req.query;
    if (lat === undefined || lon === undefined) {
      return res.status(400).json({ error: "lat and lon query params are required" });
    }
    const warehouse = await findNearestWarehouse({ lat: Number(lat), lon: Number(lon) });
    if (!warehouse) return res.status(404).json({ error: "No active warehouses available" });
    res.json(warehouse);
  } catch (err) {
    next(err);
  }
}

module.exports = { listWarehouses, nearestWarehouse };
