/* Unit tests for bundledBackendDir() — the path-resolution helper
 * that decides whether to spawn the packaged PyInstaller launcher
 * (under process.resourcesPath) or the in-repo dev bundle.
 *
 * Why this file exists: smoke-prod.cjs runs under plain node, which
 * never sets process.resourcesPath. So the packaged-path branch in
 * bundledBackendDir was unreachable from any prior test. That gap
 * is what let the earlier `startsWith(root)` asar-collapse bug
 * ship a broken Mac dmg. These four cases close it.
 *
 * Uses node:test (built-in, zero deps). Imports the compiled JS
 * from build/ — run `npm run build` first.
 */

const test = require("node:test");
const assert = require("node:assert");
const path = require("path");
const fs = require("fs");

// Stub electron so backend.js's transitive `require("electron")`
// (via logger.js → app.getPath) resolves to something harmless.
const tmpLogs = path.join(__dirname, "..", "tmp-logs");
fs.mkdirSync(tmpLogs, { recursive: true });
require.cache[require.resolve("electron")] = {
  exports: { app: { getPath: () => tmpLogs } },
};

const { bundledBackendDir } = require(path.join(__dirname, "..", "build", "backend.js"));

const FAKE_ROOT = "/Users/dev/SolarSTATA";
const DEV_FALLBACK = path.join(FAKE_ROOT, "backend", "dist", "solarstata-backend");

test("packaged: resourcesPath set + bundle present → returns packaged path", () => {
  const resourcesPath = "/Applications/SolarSTATA.app/Contents/Resources";
  const expected = path.join(resourcesPath, "solarstata-backend");
  const exists = (p) => p === expected;

  const got = bundledBackendDir(FAKE_ROOT, resourcesPath, exists);
  assert.strictEqual(got, expected);
});

test("packaged-but-empty: resourcesPath set + bundle missing → falls back to dev path", () => {
  const resourcesPath = "/Applications/SolarSTATA.app/Contents/Resources";
  const exists = () => false; // bundle not at packaged location

  const got = bundledBackendDir(FAKE_ROOT, resourcesPath, exists);
  assert.strictEqual(got, DEV_FALLBACK);
});

test("dev / plain node: resourcesPath undefined → falls back to dev path", () => {
  // exists is never consulted in this branch — assert by passing a
  // throwing stub so a regression that did consult it would fail loudly.
  const exists = () => {
    throw new Error("exists() must not be called when resourcesPath is unset");
  };

  const got = bundledBackendDir(FAKE_ROOT, undefined, exists);
  assert.strictEqual(got, DEV_FALLBACK);
});

test("regression: asar-collapse — resourcesPath shares prefix with repoRoot, bundle still resolves", () => {
  // This is the exact bug class that shipped: under an asar build,
  // __dirname → repoRoot() collapses to equal process.resourcesPath,
  // so a `resourcesPath.startsWith(root)` heuristic misroutes to
  // the dev fallback. We use existence, not prefixes, so the
  // packaged path wins regardless.
  const resourcesPath = FAKE_ROOT; // pathological: equal to repoRoot
  const expected = path.join(resourcesPath, "solarstata-backend");
  const exists = (p) => p === expected;

  const got = bundledBackendDir(FAKE_ROOT, resourcesPath, exists);
  assert.strictEqual(got, expected);
});
