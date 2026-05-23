/* Build the PyInstaller-bundled FastAPI sidecar.
 *
 * Resolves a Python interpreter (preferring the repo .venv so all
 * deps are already installed), invokes `python -m PyInstaller` on
 * backend/pyinstaller.spec, and produces
 * backend/dist/solarstata-backend/ — a one-folder bundle that
 * electron-builder picks up via the extraResources block in
 * desktop/package.json.
 *
 * Usage (from desktop/):
 *   npm run build:backend
 *   SOLARSTATA_PYTHON=/path/to/python npm run build:backend   # override
 *
 * Prerequisite: PyInstaller installed in the chosen interpreter
 * (pip install pyinstaller).
 */

const { spawnSync } = require("child_process");
const fs = require("fs");
const path = require("path");

const repoRoot = path.resolve(__dirname, "..", "..");
const backendDir = path.join(repoRoot, "backend");
const spec = path.join(backendDir, "pyinstaller.spec");
const isWin = process.platform === "win32";

function resolvePython() {
  const candidates = [];
  if (process.env.SOLARSTATA_PYTHON) candidates.push(process.env.SOLARSTATA_PYTHON);

  const venvBin = isWin
    ? path.join("Scripts", "python.exe")
    : path.join("bin", "python3");
  candidates.push(path.join(repoRoot, ".venv", venvBin));
  if (!isWin) candidates.push(path.join(repoRoot, ".venv", "bin", "python"));
  candidates.push(path.join(repoRoot, "backend", ".venv", venvBin));
  if (!isWin) candidates.push(path.join(repoRoot, "backend", ".venv", "bin", "python"));

  for (const c of candidates) {
    try {
      if (fs.existsSync(c) && fs.statSync(c).isFile()) return c;
    } catch { /* skip */ }
  }
  return isWin ? "python" : "python3";
}

const py = resolvePython();
console.log(`[build:backend] python: ${py}`);
console.log(`[build:backend] spec:   ${spec}`);

// Sanity: PyInstaller installed?
const probe = spawnSync(py, ["-c", "import PyInstaller; print(PyInstaller.__version__)"], {
  encoding: "utf8",
});
if (probe.status !== 0) {
  console.error(`[build:backend] PyInstaller not installed in ${py}.`);
  console.error("[build:backend] Install with: " + py + " -m pip install pyinstaller");
  process.exit(1);
}
console.log(`[build:backend] PyInstaller ${probe.stdout.trim()}`);

const args = [
  "-m", "PyInstaller",
  spec,
  "--clean",
  "--noconfirm",
  "--distpath", path.join(backendDir, "dist"),
  "--workpath", path.join(backendDir, "build", "pyinstaller"),
];

console.log(`[build:backend] running: ${py} ${args.join(" ")}`);
const result = spawnSync(py, args, { cwd: backendDir, stdio: "inherit" });
if (result.status !== 0) {
  console.error(`[build:backend] PyInstaller exited with status ${result.status}`);
  process.exit(result.status ?? 1);
}

const bundleDir = path.join(backendDir, "dist", "solarstata-backend");
const exe = path.join(bundleDir, isWin ? "solarstata-backend.exe" : "solarstata-backend");
if (!fs.existsSync(exe)) {
  console.error(`[build:backend] bundle launcher missing at ${exe}`);
  process.exit(1);
}
console.log(`[build:backend] done — bundle at ${bundleDir}`);
