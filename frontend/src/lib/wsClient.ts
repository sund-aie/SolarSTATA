/* Pro-mode WebSocket client.
 *
 * Manages a single connection to /ws/pro for the lifetime of the Pro mode
 * mount. Emits typed events for `started`, `block`, `complete`, and `error`.
 *
 * URL resolution defers to lib/electron.ts: inside the Electron shell
 * we connect to the dynamic sidecar port (ws://127.0.0.1:<port>/ws/pro);
 * in browser dev we use the page's host so the Vite proxy can hand off
 * to FastAPI on :8000.
 */

import { wsUrl as resolveWsUrl } from "./electron";

export type WsEvent =
  | { type: "started"; command: string }
  | { type: "block"; kind: string; structured: unknown; text: string; command: string }
  | { type: "graph"; command: string; figure: { data: unknown[]; layout: Record<string, unknown> } }
  | { type: "history_appended"; command: string }
  | { type: "complete" }
  | { type: "error"; detail: string }
  | { type: "open" }
  | { type: "close" };

export class ProWsClient {
  private ws: WebSocket | null = null;
  private listeners = new Set<(e: WsEvent) => void>();
  private urlPromise: Promise<string>;
  private reconnectDelay = 1000;
  private wantOpen = true;

  constructor(url?: string) {
    this.urlPromise = url ? Promise.resolve(url) : resolveWsUrl();
  }

  on(listener: (e: WsEvent) => void): () => void {
    this.listeners.add(listener);
    return () => this.listeners.delete(listener);
  }

  open() {
    this.wantOpen = true;
    this.connect();
  }

  send(command: string) {
    if (!this.ws || this.ws.readyState !== WebSocket.OPEN) {
      this.emit({ type: "error", detail: "WebSocket not open" });
      return;
    }
    this.ws.send(JSON.stringify({ type: "run", command }));
  }

  close() {
    this.wantOpen = false;
    this.ws?.close();
    this.ws = null;
  }

  private async connect() {
    if (this.ws && (this.ws.readyState === WebSocket.OPEN || this.ws.readyState === WebSocket.CONNECTING)) {
      return;
    }
    const url = await this.urlPromise;
    if (!this.wantOpen) return;
    this.ws = new WebSocket(url);
    this.ws.onopen = () => this.emit({ type: "open" });
    this.ws.onclose = () => {
      this.emit({ type: "close" });
      if (this.wantOpen) {
        setTimeout(() => this.connect(), this.reconnectDelay);
      }
    };
    this.ws.onerror = () => this.emit({ type: "error", detail: "websocket error" });
    this.ws.onmessage = (ev) => {
      try {
        const msg = JSON.parse(ev.data);
        this.emit(msg as WsEvent);
      } catch {
        this.emit({ type: "error", detail: "bad message JSON" });
      }
    };
  }

  private emit(e: WsEvent) {
    for (const l of this.listeners) l(e);
  }
}
