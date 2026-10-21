const mongoose = require("mongoose");

async function connectDB(uri) {
  mongoose.set("strictQuery", true);

  try {
    await mongoose.connect(uri, {
      // Modern mongoose (>=6) doesn't need the old useNewUrlParser/useUnifiedTopology
      // flags, but we keep serverSelectionTimeoutMS short so failures surface fast
      // instead of hanging the whole server on boot.
      serverSelectionTimeoutMS: 8000,
    });
    console.log(`[db] connected -> ${mongoose.connection.host}/${mongoose.connection.name}`);
  } catch (err) {
    console.error("[db] connection failed:", err.message);
    throw err;
  }

  mongoose.connection.on("disconnected", () => {
    console.warn("[db] disconnected");
  });
}

module.exports = { connectDB };
