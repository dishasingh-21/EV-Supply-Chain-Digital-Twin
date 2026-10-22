const EARTH_RADIUS_KM = 6371;

/**
 * Great-circle distance between two {lat, lon} points, in km.
 * Same formula as the original script2.js — kept identical so the A*
 * heuristic stays admissible against the OSRM-based edge weights.
 */
function haversine(a, b) {
  const lat1 = (a.lat * Math.PI) / 180;
  const lat2 = (b.lat * Math.PI) / 180;
  const dLat = lat2 - lat1;
  const dLon = ((b.lon - a.lon) * Math.PI) / 180;

  const h =
    Math.sin(dLat / 2) ** 2 +
    Math.cos(lat1) * Math.cos(lat2) * Math.sin(dLon / 2) ** 2;

  return EARTH_RADIUS_KM * (2 * Math.asin(Math.sqrt(h)));
}

module.exports = { haversine };
