const Warehouse = require("../models/Warehouse");
const { planRouteByCoords, RouteError } = require("./route.service");

/**
 * Finds the nearest active warehouse to a given point using Mongo's
 * $near geospatial query (same 2dsphere index pattern as Station.near).
 */
async function findNearestWarehouse({ lat, lon }) {
  const warehouse = await Warehouse.findOne({
    active: true,
    location: {
      $near: { $geometry: { type: "Point", coordinates: [lon, lat] } },
    },
  }).lean();
  return warehouse;
}

/**
 * Plans a pickup -> delivery route for a delivery rider.
 * Pickup point comes from the warehouses dataset (by `warehouseCode`, or the
 * nearest active warehouse to the delivery point if omitted). Delivery point
 * is always given directly as {lat, lon} — no geocoding, per the requirement
 * that the delivery location is supplied as coordinates.
 */
async function planDeliveryRoute({ warehouseCode, deliveryLat, deliveryLon, batteryPercent }) {
  if (!Number.isFinite(deliveryLat) || !Number.isFinite(deliveryLon)) {
    throw new RouteError("deliveryLat and deliveryLon must be numbers");
  }

  let warehouse;
  if (warehouseCode) {
    warehouse = await Warehouse.findOne({ code: warehouseCode, active: true }).lean();
    if (!warehouse) throw new RouteError(`No active warehouse with code "${warehouseCode}"`, 404);
  } else {
    warehouse = await findNearestWarehouse({ lat: deliveryLat, lon: deliveryLon });
    if (!warehouse) throw new RouteError("No active warehouses available", 404);
  }

  const startLoc = { lat: warehouse.lat, lon: warehouse.lon, name: warehouse.name };
  const endLoc = { lat: deliveryLat, lon: deliveryLon, name: "Delivery Location" };

  const planned = await planRouteByCoords({ startLoc, endLoc, batteryPercent });

  return {
    warehouse: { code: warehouse.code, name: warehouse.name, lat: warehouse.lat, lon: warehouse.lon },
    delivery: { lat: deliveryLat, lon: deliveryLon },
    ...planned,
  };
}

module.exports = { planDeliveryRoute, findNearestWarehouse };
