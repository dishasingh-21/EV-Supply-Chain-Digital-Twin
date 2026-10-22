// Write endpoints are disabled unless ADMIN_API_KEY is set, and then require
// it in the x-api-key header. Prevents anyone on the internet from adding stations.
function requireAdmin(req, res, next) {
  const key = process.env.ADMIN_API_KEY;
  if (!key) return res.status(403).json({ error: "Write access is disabled on this server" });
  if (req.get("x-api-key") !== key) return res.status(401).json({ error: "Invalid API key" });
  next();
}

module.exports = { requireAdmin };
