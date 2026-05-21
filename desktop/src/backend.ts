/* FastAPI backend sidecar lifecycle.
 *
 * spawnBackend  — picks a free TCP port, launches uvicorn, returns
 *                 a handle with the port + child process reference.
 * waitForHealth — polls /healthz until 2xx or timeout.
 * stopBackend   — SIGTERM then SIGKILL after 3s grace period.
 *
 * In dev mode (SOLARSTATA_DEV=1) we run the editable backend via
 * `python -m uvicorn solarstata.main:app` from the repo's .venv.
 * In packaged mode we'll point at the PyInstaller-built binary
 * (lands in v3.1B). The branch is decided by `getBackendCommand`.
 */

import { spawn, type ChildProcess } from "child_process";
import * as net from "net";
import * as path from "path";
import * as fs from "fs";
import * as http from "http";

import { logLine } from "./logger.js";

export interface BackendHandle {
  port: number;
  child: ChildProcess;
}

export async function pickFreePort(): Promise<number> {
  return new Promise((resolve, reject) => {
    const server = net.createServer();
    server.unref();
    server.on("error", reject);
    server.listen(0, "127.0.0.1", () => {
      const addr = server.address();
      if (typeof addr === "object" && addr) {
        const port = addr.port;
        server.close(() => resolve(port));
      } else {
        reject(new Error("could not resolve free port"));
      }
    });
  });
}

function repoRoot(): string {
  // desktop/build/backend.js → desktop/ → repo root
  return path.resolve(__dirname, "..", "..");
}

function getBackendCommand(port: number): { cmd: string; args: string[]; cwd: string; env: NodeJS.ProcessEnv } {
  const root = repoRoot();
  const env: NodeJS.ProcessEnv = {
    ...process.env,
    SOLARSTATA_PORT: String(port),
    PYTHONUNBUFFERED: "1",
  };
  if (process.env.SOLARSTATA_DEV) {
    const venvPy = process.platform === "win32"
      ? path.join(root, "backend", ".venv", "Scripts", "python.exe")
      : path.join(root, "backend", ".venv", "bin", "python");
    const pyCmd = fs.existsSync(venvPy) ? venvPy : (process.platform === "win32" ? "python" : "python3");
    return {
      cmd: pyCmd,
      args: ["-m", "uvicorn", "solarstata.main:app",
             "--host", "127.0.0.1",
             "--port", String(port),
             "--log-level", "info"],
      cwd: path.join(root, "backend"),
      env: {
        ...env,
        PYTHONPATH: path.join(root, "backend", "src"),
      },
    };
  }
  // Production: PyInstaller-bundled binary (filled in by v3.1B).
  const exe = process.platform === "win32" ? "solarstata-backend.exe" : "solarstata-backend";
  const resourcesPath = (process as NodeJS.Process & { resourcesPath?: string }).resourcesPath;
  const bundled = resourcesPath
    ? path.join(resourcesPath, "backend", exe)
    : path.join(root, "backend", "dist", "solarstata-backend", exe);
  return {
    cmd: bundled,
    args: ["--port", String(port)],
    cwd: path.dirname(bundled),
    env,
  };
}

export async function spawnBackend(): Promise<BackendHandle> {
  const port = await pickFreePort();
  const { cmd, args, cwd, env } = getBackendCommand(port);

  logLine(`spawning backend: ${cmd} ${args.join(" ")} (cwd=${cwd}, port=${port})`);

  const child = spawn(cmd, args, { cwd, env, stdio: ["ignore", "pipe", "pipe"] });

  child.stdout?.on("data", (buf: Buffer) => logLine(buf.toString().trimEnd()));
  child.stderr?.on("data", (buf: Buffer) => logLine(buf.toString().trimEnd()));
  child.on("exit", (code, signal) => {
    logLine(`backend exited code=${code} signal=${signal ?? "none"}`);
  });

  return { port, child };
}

export async function waitForHealth(port: number, timeoutMs = 30000): Promise<void> {
  const url = `http://127.0.0.1:${port}/healthz`;
  const start = Date.now();
  let lastErr: string = "no attempts yet";
  while (Date.now() - start < timeoutMs) {
    try {
      await fetchHealth(url);
      logLine(`backend healthy after ${Date.now() - start}ms`);
      return;
    } catch (e) {
      lastErr = String(e);
      await sleep(250);
    }
  }
  throw new Error(`backend did not become healthy within ${timeoutMs}ms (last error: ${lastErr})`);
}

function fetchHealth(url: string): Promise<void> {
  return new Promise((resolve, reject) => {
    const req = http.get(url, (res) => {
      // drain so the socket can be reused / closed
      res.resume();
      if (res.statusCode && res.statusCode >= 200 && res.statusCode < 300) resolve();
      else reject(new Error(`status ${res.statusCode}`));
    });
    req.on("error", reject);
    req.setTimeout(2000, () => {
      req.destroy(new Error("health probe timeout"));
    });
  });
}

function sleep(ms: number): Promise<void> {
  return new Promise((r) => setTimeout(r, ms));
}

export async function stopBackend(handle: BackendHandle): Promise<void> {
  const { child } = handle;
  if (child.exitCode !== null || child.killed) return;
  logLine("stopping backend (SIGTERM)…");
  child.kill("SIGTERM");
  const exited = await raceExit(child, 3000);
  if (!exited) {
    logLine("backend still alive after 3s grace — sending SIGKILL");
    try {
      child.kill("SIGKILL");
    } catch {
      /* already dead */
    }
  }
}

function raceExit(child: ChildProcess, ms: number): Promise<boolean> {
  return new Promise((resolve) => {
    if (child.exitCode !== null) return resolve(true);
    const t = setTimeout(() => resolve(false), ms);
    child.once("exit", () => {
      clearTimeout(t);
      resolve(true);
    });
  });
}
