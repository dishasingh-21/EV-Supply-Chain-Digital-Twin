require("dotenv").config();
const { createApp } = require("./src/app");
const { connectDB } = require("./src/config/db");

const PORT = process.env.PORT || 5000;
const MONGO_URI = process.env.MONGO_URI || "mongodb://127.0.0.1:27017/ev_route_optimizer";

async function main() {
  await connectDB(MONGO_URI);
  const app = createApp();
  app.listen(PORT, "0.0.0.0", () => {
    console.log(`[server] listening on http://localhost:${PORT}`);
  });
}

main().catch((err) => {
  console.error("[server] failed to start:", err);
  process.exit(1);
});
