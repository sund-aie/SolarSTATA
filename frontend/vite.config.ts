import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";
import path from "node:path";
import { readFileSync } from "node:fs";

const pkg = JSON.parse(readFileSync(path.resolve(__dirname, "./package.json"), "utf-8")) as {
  version: string;
};

// `base: "./"` makes the production build load assets via relative
// paths so the bundled HTML works under Electron's file:// protocol
// (Phase 3.1B). The Vite dev server keeps absolute root URLs in dev,
// so the proxy block below is unaffected.
//
// __APP_VERSION__ is injected at build time from package.json so the
// topbar version chip can never go stale — a single source of truth.
export default defineConfig({
  base: "./",
  define: {
    __APP_VERSION__: JSON.stringify(pkg.version),
  },
  plugins: [react()],
  resolve: {
    alias: {
      "@": path.resolve(__dirname, "./src"),
    },
  },
  server: {
    port: 5173,
    host: "127.0.0.1",
    proxy: {
      "/api":     { target: "http://127.0.0.1:8000", changeOrigin: true },
      "/healthz": { target: "http://127.0.0.1:8000", changeOrigin: true },
      "/ws":      { target: "ws://127.0.0.1:8000", ws: true, changeOrigin: true },
    },
  },
});
