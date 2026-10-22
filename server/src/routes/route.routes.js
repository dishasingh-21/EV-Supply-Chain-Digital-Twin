const express = require("express");
const { computeRoute, computeDeliveryRoute } = require("../controllers/routeController");

const router = express.Router();

router.post("/", computeRoute);
router.post("/delivery", computeDeliveryRoute);

module.exports = router;
