const express = require("express");
const { listRecommendations } = require("../controllers/recommendationController");

const router = express.Router();

router.get("/", listRecommendations);

module.exports = router;
