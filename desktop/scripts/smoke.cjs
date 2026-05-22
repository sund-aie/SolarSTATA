/* Headless smoke test for the FastAPI sidecar lifecycle.
 *
 * Runs the same pickFreePort → spawn → waitForHealth → stopBackend
 * flow that main.ts uses on Electron startup, but without launching
 * a BrowserWindow. Confirms the contract is sound before opening
 * the GUI for end-to-end testing.
 *
 * Usage:  SOLARSTATA_DEV=1 node scripts/smoke.cjs
 */

const path = require("path");
const fs = require("fs");

// Stub electron.app so logger.ts can resolve a logs directory without
// the real Electron runtime.
const logsDir = path.join(__dirname, "..", "tmp-logs");
fs.mkdirSync(logsDir, { recursive: true });
require.cache[require.resolve("electron")] = {
  exports: { app: { getPath: () => logsDir } },
};

const { spawnBackend, waitForHealth, stopBackend } = require(path.join(__dirname, "..", "build", "backend.js"));

(async () => {
  console.log("[smoke] picking port + spawning backend…");
  const handle = await spawnBackend();
  console.log(`[smoke] spawned on port ${handle.port}`);

  try {
    console.log("[smoke] waiting for /healthz…");
    await waitForHealth(handle.port, 30000);
    console.log("[smoke] backend reports healthy ✔");

    // Hit /healthz once more to make sure the response is real.
    const http = require("http");
    const body = await new Promise((res, rej) => {
      http.get(`http://127.0.0.1:${handle.port}/healthz`, (r) => {
        let d = "";
        r.on("data", (c) => (d += c));
        r.on("end", () => res(d));
        r.on("error", rej);
      }).on("error", rej);
    });
    console.log("[smoke] /healthz body:", body);
  } finally {
    console.log("[smoke] stopping backend (SIGTERM)…");
    await stopBackend(handle);
    console.log("[smoke] backend stopped ✔");
  }
})().catch((e) => {
  console.error("[smoke] FAILED:", e);
  process.exit(1);
});
