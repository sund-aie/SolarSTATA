/* Electron-bridge helpers.
 *
 * The preload script (desktop/src/preload.ts) exposes a tiny
 * `window.electronAPI` surface when the app is running inside the
 * Electron shell. Browser dev (Vite at :5173 without the shell)
 * leaves the global undefined and we fall back to relative URLs +
 * the Vite proxy.
 */

type ElectronPlatform =
  | "aix" | "android" | "darwin" | "freebsd" | "haiku" | "linux"
  | "openbsd" | "sunos" | "win32" | "cygwin" | "netbsd";

interface ElectronAPI {
  isElectron: true;
  platform: ElectronPlatform;
  getBackendPort: () => Promise<number | null>;
  openLogs: () => Promise<string>;
}

declare global {
  interface Window {
    electronAPI?: ElectronAPI;
  }
}

export const isElectron = (): boolean => typeof window !== "undefined" && !!window.electronAPI;

let cachedPort: number | null | undefined;
let pending: Promise<number | null> | null = null;

/** Returns the FastAPI sidecar port chosen by Electron, or null if
 *  we're running in a regular browser (use relative URLs instead). */
export async function getBackendPort(): Promise<number | null> {
  if (!isElectron()) return null;
  if (cachedPort !== undefined) return cachedPort;
  if (!pending) {
    pending = window.electronAPI!.getBackendPort()
      .then((p) => {
        cachedPort = p;
        return p;
      })
      .catch(() => {
        cachedPort = null;
        return null;
      });
  }
  return pending;
}

/** Synchronous accessor for once the port has been resolved at least
 *  once. Returns null if unknown — callers should await getBackendPort
 *  on cold start. */
export function backendPortSync(): number | null {
  return cachedPort ?? null;
}

/** HTTP base URL for API calls.
 *  - In Electron: http://127.0.0.1:<port>
 *  - In browser dev: "" so fetches stay relative and Vite proxies. */
export async function apiBase(): Promise<string> {
  const port = await getBackendPort();
  return port ? `http://127.0.0.1:${port}` : "";
}

/** WebSocket URL for the Pro mode stream.
 *  - In Electron: ws://127.0.0.1:<port>/ws/pro
 *  - In browser dev: ws[s]://<location.host>/ws/pro (proxied). */
export async function wsUrl(): Promise<string> {
  const port = await getBackendPort();
  if (port) return `ws://127.0.0.1:${port}/ws/pro`;
  const proto = location.protocol === "https:" ? "wss:" : "ws:";
  return `${proto}//${location.host}/ws/pro`;
}
