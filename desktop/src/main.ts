/* Electron main process for SolarSTATA desktop.
 *
 * Lifecycle:
 *   1. Pick a free TCP port for the FastAPI sidecar.
 *   2. Spawn the backend; pipe its stdout/stderr to the log file.
 *   3. Show a splash window with the gold S while we poll /healthz.
 *   4. On health, swap the same window to the React app (Vite dev
 *      URL in dev, file:// bundle in production — production lands
 *      in v3.1B).
 *   5. On quit, SIGTERM the backend; SIGKILL after 3s grace.
 *
 * The renderer learns the backend port through preload.ts which
 * exposes it as `window.electronAPI.backendPort`.
 */

import { app, BrowserWindow, ipcMain, shell } from "electron";
import * as path from "path";

import {
  spawnBackend,
  waitForHealth,
  stopBackend,
  type BackendHandle,
} from "./backend.js";
import { openLog, closeLog, logLine } from "./logger.js";

const isDev = !!process.env.SOLARSTATA_DEV;
let mainWindow: BrowserWindow | null = null;
let backend: BackendHandle | null = null;
let quitting = false;

// Ensure only one instance.
const gotLock = app.requestSingleInstanceLock();
if (!gotLock) {
  app.quit();
} else {
  app.on("second-instance", () => {
    if (mainWindow) {
      if (mainWindow.isMinimized()) mainWindow.restore();
      mainWindow.focus();
    }
  });
}

app.whenReady().then(async () => {
  const { logPath } = openLog();
  logLine(`SolarSTATA starting (dev=${isDev}, electron=${process.versions.electron})`);
  logLine(`log file: ${logPath}`);

  mainWindow = createMainWindow();
  await mainWindow.loadFile(path.join(__dirname, "static", "splash.html"));

  try {
    backend = await spawnBackend();
    // Make the port readable to preload before we navigate the renderer.
    process.env.SOLARSTATA_BACKEND_PORT = String(backend.port);
    await waitForHealth(backend.port, 30000);
    await navigateToApp(mainWindow, backend.port);
  } catch (e) {
    logLine(`STARTUP FAILED: ${String(e)}`);
    if (mainWindow) {
      await mainWindow.webContents.executeJavaScript(
        `document.body.dataset.state="failed"; ` +
        `document.getElementById('msg').textContent=${JSON.stringify(
          "Backend failed to start — open Help menu → Show logs for diagnostics."
        )}; ` +
        `document.getElementById('detail').textContent=${JSON.stringify(String(e))};`
      ).catch(() => undefined);
    }
  }

  app.on("activate", () => {
    if (BrowserWindow.getAllWindows().length === 0) {
      mainWindow = createMainWindow();
      // Re-run boot flow if reactivated post-quit (rare on mac with all
      // windows closed but app still in dock).
      void mainWindow.loadFile(path.join(__dirname, "static", "splash.html"));
    }
  });
});

function createMainWindow(): BrowserWindow {
  const win = new BrowserWindow({
    width: 1400,
    height: 900,
    minWidth: 1024,
    minHeight: 700,
    backgroundColor: "#0e0d0b",
    show: true,
    title: "SolarSTATA",
    webPreferences: {
      preload: path.join(__dirname, "preload.js"),
      contextIsolation: true,
      nodeIntegration: false,
      sandbox: false,
    },
  });

  // External links open in the system browser, not inside the app.
  win.webContents.setWindowOpenHandler(({ url }) => {
    if (url.startsWith("http://") || url.startsWith("https://")) {
      void shell.openExternal(url);
    }
    return { action: "deny" };
  });

  win.on("closed", () => {
    if (win === mainWindow) mainWindow = null;
  });

  return win;
}

async function navigateToApp(win: BrowserWindow, port: number): Promise<void> {
  if (isDev) {
    // Use 127.0.0.1 (not localhost) so the renderer shares a host
    // with the backend sidecar. Cookies set by the backend on
    // 127.0.0.1 then ride along under SameSite=Lax for cross-port
    // fetches from the renderer; the upload→finalize handshake
    // depends on this. Vite is bound to 127.0.0.1:5173 in
    // vite.config.ts so this URL is always reachable.
    await win.loadURL("http://127.0.0.1:5173");
    win.webContents.openDevTools({ mode: "detach" });
    return;
  }
  // Production bundle (file://). Lands in v3.1B; for now we fall
  // back to a placeholder so dev parity holds.
  const indexHtml = path.join(__dirname, "..", "..", "frontend", "dist", "index.html");
  await win.loadFile(indexHtml);
  logLine(`renderer loaded: ${indexHtml} backend port=${port}`);
}

// IPC: renderer asks for the backend port via preload.
ipcMain.handle("solarstata:backend-port", () => backend?.port ?? null);
ipcMain.handle("solarstata:open-logs", async () => {
  const logPath = path.join(app.getPath("logs"), "backend.log");
  await shell.openPath(logPath);
  return logPath;
});

app.on("before-quit", async (event) => {
  if (quitting) return;
  if (backend) {
    event.preventDefault();
    quitting = true;
    logLine("before-quit: stopping backend…");
    try {
      await stopBackend(backend);
    } finally {
      backend = null;
      closeLog();
      app.quit();
    }
  } else {
    closeLog();
  }
});

app.on("window-all-closed", () => {
  // On macOS, apps usually stay alive when all windows are closed.
  // We follow that convention; explicit Cmd+Q triggers before-quit.
  if (process.platform !== "darwin") app.quit();
});
