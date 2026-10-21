const express = require("express");
const { listWarehouses, nearestWarehouse } = require("../controllers/warehouseController");

const router = express.Router();

router.get("/nearest", nearestWarehouse); // before "/" so it isn't shadowed
router.get("/", listWarehouses);

module.exports = router;
