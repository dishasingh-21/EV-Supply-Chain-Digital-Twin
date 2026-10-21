// Single source of truth for where the backend API lives.
// Local dev -> localhost:5000. Deployed -> set PROD_API_URL below to your
// backend's public URL (must end in /api), e.g. "https://ev-route-api.onrender.com/api".
const PROD_API_URL = "https://YOUR-BACKEND-URL/api";
const isLocal = ["localhost", "127.0.0.1", ""].includes(window.location.hostname);
window.API_BASE_URL = window.API_BASE_URL || (isLocal ? "http://localhost:5000/api" : PROD_API_URL);
