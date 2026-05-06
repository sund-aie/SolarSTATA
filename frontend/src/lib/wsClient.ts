/* Pro-mode WebSocket client.
 *
 * Manages a single connection to /ws/pro for the lifetime of the Pro mode
 * mount. Emits typed events for `started`, `block`, `complete`, and `error`.
 */

export type WsEvent =
  | { type: "started"; command: string }
  | { type: "block"; kind: string; structured: unknown; text: string; command: string }
  | { type: "history_appended"; command: string }
  | { type: "complete" }
  | { type: "error"; detail: string }
  | { type: "open" }
  | { type: "close" };

export class ProWsClient {
  private ws: WebSocket | null = null;
  private listeners = new Set<(e: WsEvent) => void>();
  private url: string;
  private reconnectDelay = 1000;
  private wantOpen = true;

  constructor(url = wsUrl()) {
    this.url = url;
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

  private connect() {
    if (this.ws && (this.ws.readyState === WebSocket.OPEN || this.ws.readyState === WebSocket.CONNECTING)) {
      return;
    }
    this.ws = new WebSocket(this.url);
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

function wsUrl(): string {
  const proto = location.protocol === "https:" ? "wss:" : "ws:";
  return `${proto}//${location.host}/ws/pro`;
}
