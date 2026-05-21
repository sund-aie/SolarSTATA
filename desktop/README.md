# SolarSTATA desktop shell

Electron wrapper that turns the existing React frontend + FastAPI
backend into a native-feeling desktop app. Phase 3.1A boots the
shell against the Vite dev server with a Python sidecar; phase
3.1B will bundle the Python interpreter via PyInstaller so the
end-user installs nothing else.

## Architecture

```
┌────────────────────────────────────────────────────────────────┐
│  Electron main process (this folder)                            │
│  ────────────────────────────────────                           │
│  • picks a free TCP port (net.createServer)                    │
│  • spawns python -m uvicorn solarstata.main:app on that port   │
│  • polls /healthz; navigates the BrowserWindow on first 2xx    │
│  • on quit, SIGTERM → 3s grace → SIGKILL                       │
└────────────────────────────────────────────────────────────────┘
                                ↓
┌────────────────────────────────────────────────────────────────┐
│  BrowserWindow                                                  │
│  preload.ts exposes window.electronAPI = { getBackendPort(), …}│
│  Renderer (React) detects Electron and talks to 127.0.0.1:<p>  │
└────────────────────────────────────────────────────────────────┘
```

## Dev setup

```bash
# from repo root, install Python deps once
make setup

# desktop deps (Electron, electron-builder, TypeScript, …)
cd desktop
npm install

# dev mode: starts Vite + Electron with sidecar
npm run electron:dev
```

What that script does:
1. `tsc` compiles `src/*.ts` → `build/*.js` (CommonJS).
2. `concurrently` boots the Vite dev server (port 5173) and waits
   for it to be ready.
3. Electron launches with `SOLARSTATA_DEV=1`. It picks a random
   free port, spawns the backend, polls `/healthz`, then loads
   `http://localhost:5173` in the BrowserWindow.
4. Quitting (Cmd+Q / Alt+F4) triggers `before-quit` which SIGTERMs
   the backend; SIGKILL after 3s if still alive.

## Headless smoke test

The backend lifecycle (spawn → health → stop) can be exercised
without the GUI:

```bash
SOLARSTATA_DEV=1 node scripts/smoke.cjs
```

This is the fastest way to confirm Python is wired up before
opening Electron.

## Log files

Backend stdout/stderr is piped to a rolling log:

| Platform | Path |
| --- | --- |
| macOS   | `~/Library/Logs/SolarSTATA/backend.log` |
| Windows | `%APPDATA%\SolarSTATA\logs\backend.log` |
| Linux   | `~/.config/SolarSTATA/logs/backend.log` |

Previous run is rotated to `backend.log.1` on each launch.
The renderer can call `window.electronAPI.openLogs()` to open
the current log in the OS file viewer.

## Phase status

| Phase | Status | Scope |
| --- | --- | --- |
| 3.1A | ✅ landed | Electron shell + FastAPI sidecar (this folder) |
| 3.1B | ⏳ next | PyInstaller bundling, no system Python needed |
| 3.1C | ⏳ later | Icons, installers (.dmg / .exe), README rewrite |

Out of scope for v3.1 (deferred to v3.2): auto-updater, code
signing / notarization, publication figure polish, mac install
hygiene fixes.
