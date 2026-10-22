const express = require("express");
const { listStations, nearStations, createStation } = require("../controllers/stationController");

const { requireAdmin } = require("../middleware/requireAdmin");

const router = express.Router();

router.get("/near", nearStations); // must come before /:something-style routes if added later
router.get("/", listStations);
router.post("/", requireAdmin, createStation);

module.exports = router;
