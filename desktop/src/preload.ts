/* Preload script — runs in the renderer context with limited Node
 * access. Exposes a small, frozen `window.electronAPI` surface so
 * the React app can:
 *   - learn the backend port (assigned dynamically by Electron)
 *   - open the backend log file in the OS file viewer
 *
 * Anything else must stay on the main process side; the renderer
 * cannot import Node modules directly.
 */

import { contextBridge, ipcRenderer } from "electron";

const electronAPI = {
  isElectron: true,
  platform: process.platform,
  getBackendPort: (): Promise<number | null> => ipcRenderer.invoke("solarstata:backend-port"),
  openLogs: (): Promise<string> => ipcRenderer.invoke("solarstata:open-logs"),
} as const;

contextBridge.exposeInMainWorld("electronAPI", electronAPI);

declare global {
  interface Window {
    electronAPI: typeof electronAPI;
  }
}
