/* Electron-bridge helpers: browser-mode fallback + sidecar resolution. */

import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

type ElectronAPIStub = {
  isElectron: true;
  platform: string;
  getBackendPort: () => Promise<number | null>;
  openLogs: () => Promise<string>;
};

const setElectron = (api: ElectronAPIStub | undefined) => {
  (window as unknown as { electronAPI?: ElectronAPIStub }).electronAPI = api;
};

describe("lib/electron", () => {
  beforeEach(() => {
    vi.resetModules();
    setElectron(undefined);
  });

  afterEach(() => {
    setElectron(undefined);
  });

  it("isElectron() reports false in a regular browser", async () => {
    const { isElectron } = await import("../src/lib/electron");
    expect(isElectron()).toBe(false);
  });

  it("apiBase() resolves to empty string when not in Electron (relative URLs via Vite proxy)", async () => {
    const { apiBase } = await import("../src/lib/electron");
    expect(await apiBase()).toBe("");
  });

  it("apiBase() returns the dynamic sidecar URL when window.electronAPI is exposed", async () => {
    setElectron({
      isElectron: true,
      platform: "darwin",
      getBackendPort: async () => 51234,
      openLogs: async () => "/tmp/log",
    });
    const { apiBase, isElectron } = await import("../src/lib/electron");
    expect(isElectron()).toBe(true);
    expect(await apiBase()).toBe("http://127.0.0.1:51234");
  });

  it("wsUrl() picks ws://127.0.0.1:<port>/ws/pro inside Electron", async () => {
    setElectron({
      isElectron: true,
      platform: "linux",
      getBackendPort: async () => 49152,
      openLogs: async () => "/tmp/log",
    });
    const { wsUrl } = await import("../src/lib/electron");
    expect(await wsUrl()).toBe("ws://127.0.0.1:49152/ws/pro");
  });

  it("wsUrl() falls back to location-relative URL in browser dev", async () => {
    const { wsUrl } = await import("../src/lib/electron");
    const got = await wsUrl();
    // jsdom default: http://localhost:3000 — proto becomes ws:
    expect(got.startsWith("ws://") || got.startsWith("wss://")).toBe(true);
    expect(got.endsWith("/ws/pro")).toBe(true);
  });
});
