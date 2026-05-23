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

## Production build (3.1B)

The packaged app ships the Python interpreter + the entire
scientific stack inside its Resources folder via PyInstaller. The
end user installs nothing.

### Prerequisites (one-time)

```bash
# from repo root
make setup                                       # creates .venv
.venv/bin/pip install pyinstaller                # bundler itself
cd desktop && npm install                        # Electron + builder
```

### Building a distributable

```bash
cd desktop

# Mac dmg → desktop/dist/SolarSTATA-<version>.dmg
npm run dist:mac

# Windows NSIS installer → desktop/dist/SolarSTATA Setup <version>.exe
npm run dist:win

# Linux AppImage (not officially supported in v3.1; useful for testing)
npm run dist:linux
```

What `dist:mac` does, in order:

1. `npm run build:backend` — invokes `python -m PyInstaller backend/pyinstaller.spec`
   producing a one-folder bundle at `backend/dist/solarstata-backend/`
   (the launcher + `_internal/` with every wheel pre-resolved).
2. `npm run build:frontend` — `vite build` with `base: "./"` so the
   bundled HTML loads via `file://`.
3. `npm run build` — compiles the Electron main/preload TypeScript.
4. `electron-builder` packs the Electron shell + extras:
   - `extraResources["../backend/dist/solarstata-backend" → "solarstata-backend"]`
   - `extraResources["../frontend/dist" → "frontend"]`
   - All `node_modules` and `desktop/build/*.js`.

The packaged path layout (Mac):
```
SolarSTATA.app/
├── Contents/
│   ├── MacOS/SolarSTATA              ← Electron launcher
│   ├── Resources/
│   │   ├── app.asar                  ← compiled main.js + preload.js
│   │   ├── solarstata-backend/       ← PyInstaller bundle
│   │   │   ├── solarstata-backend    ← uvicorn launcher
│   │   │   └── _internal/            ← every Python dep
│   │   └── frontend/                 ← Vite production bundle
│   │       ├── index.html
│   │       └── assets/
```

At runtime `process.resourcesPath` resolves to
`/Applications/SolarSTATA.app/Contents/Resources/` and
`main.ts` / `backend.ts` use it to find the bundled launcher and
the production HTML. No system Python is touched.

### Verifying the build is hermetic

```bash
# 1. confirm the bundled launcher works standalone
SOLARSTATA_PORT=9876 backend/dist/solarstata-backend/solarstata-backend &
curl http://127.0.0.1:9876/healthz                       # expect {"status":"ok",…}
kill %1

# 2. inside the packaged app, the spawn log shows:
#    backend: production bundle path /Applications/SolarSTATA.app/.../solarstata-backend
#    spawning backend: …/solarstata-backend (cwd=…/solarstata-backend, port=<dynamic>)
#    NOT a path under ~/.venv or /usr/local/bin/python3.
```

The PyInstaller bundle currently weighs ~500MB unzipped (the
scientific Python stack is big). Future work: trim with
`--exclude-module` for unused parts of statsmodels / matplotlib /
scipy.tests, which can roughly halve it.

## Phase status

| Phase | Status | Scope |
| --- | --- | --- |
| 3.1A | ✅ landed | Electron shell + FastAPI sidecar (this folder) |
| 3.1B | ✅ landed | PyInstaller bundling, no system Python needed |
| 3.1C | ⏳ next | Icons, installer polish, README rewrite |

Out of scope for v3.1 (deferred to v3.2): auto-updater, code
signing / notarization, publication figure polish, mac install
hygiene fixes.
