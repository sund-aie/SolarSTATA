/* Headless smoke for the PyInstaller-bundled launcher itself.
 *
 * Spawns the in-repo backend/dist/solarstata-backend binary,
 * waits for /healthz, and shuts it down — confirming the bundle
 * boots and serves traffic. This does NOT exercise the packaged-
 * Electron path-resolution branch in bundledBackendDir (plain
 * node never sets process.resourcesPath); that's covered by the
 * unit tests in tests/bundle-path.test.cjs.
 *
 * Usage:  node scripts/smoke-prod.cjs
 *
 * Prereq: backend/dist/solarstata-backend/ must exist (run
 *         `npm run build:backend` first).
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

// Make sure we are NOT in dev mode for this smoke.
delete process.env.SOLARSTATA_DEV;

const { spawnBackend, waitForHealth, stopBackend } = require(path.join(__dirname, "..", "build", "backend.js"));

(async () => {
  console.log("[smoke-prod] spawning PyInstaller-bundled backend…");
  const handle = await spawnBackend();
  console.log(`[smoke-prod] spawned on port ${handle.port}`);

  try {
    await waitForHealth(handle.port, 30000);
    console.log("[smoke-prod] backend reports healthy ✔");

    const http = require("http");
    const body = await new Promise((res, rej) => {
      http.get(`http://127.0.0.1:${handle.port}/healthz`, (r) => {
        let d = "";
        r.on("data", (c) => (d += c));
        r.on("end", () => res(d));
        r.on("error", rej);
      }).on("error", rej);
    });
    console.log("[smoke-prod] /healthz body:", body);
  } finally {
    console.log("[smoke-prod] stopping backend (SIGTERM)…");
    await stopBackend(handle);
    console.log("[smoke-prod] backend stopped ✔");
  }
})().catch((e) => {
  console.error("[smoke-prod] FAILED:", e);
  process.exit(1);
});
