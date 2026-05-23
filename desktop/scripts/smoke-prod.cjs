/* Headless smoke for the PRODUCTION code path.
 *
 * Same lifecycle as scripts/smoke.cjs but with SOLARSTATA_DEV
 * unset, forcing backend.ts to resolve the PyInstaller-bundled
 * launcher at backend/dist/solarstata-backend/. Confirms the
 * production spawn path before any electron-builder packaging.
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
