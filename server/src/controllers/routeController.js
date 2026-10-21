const { planRoute, RouteError } = require("../services/route.service");
const { planDeliveryRoute } = require("../services/deliveryRoute.service");

// POST /api/route  { startPlace, endPlace, batteryPercent }
async function computeRoute(req, res, next) {
  try {
    const { startPlace, endPlace, batteryPercent } = req.body;
    const result = await planRoute({
      startPlace,
      endPlace,
      batteryPercent: Number(batteryPercent),
    });
    res.json(result);
  } catch (err) {
    if (err instanceof RouteError) {
      return res.status(err.status).json({ error: err.message });
    }
    next(err);
  }
}

// POST /api/route/delivery  { warehouseCode?, deliveryLat, deliveryLon, batteryPercent }
// warehouseCode is optional — if omitted, the nearest active warehouse to
// the delivery point is used as the pickup point automatically.
async function computeDeliveryRoute(req, res, next) {
  try {
    const { warehouseCode, deliveryLat, deliveryLon, batteryPercent } = req.body;
    const result = await planDeliveryRoute({
      warehouseCode,
      deliveryLat: Number(deliveryLat),
      deliveryLon: Number(deliveryLon),
      batteryPercent: Number(batteryPercent),
    });
    res.json(result);
  } catch (err) {
    if (err instanceof RouteError) {
      return res.status(err.status).json({ error: err.message });
    }
    next(err);
  }
}

module.exports = { computeRoute, computeDeliveryRoute };
