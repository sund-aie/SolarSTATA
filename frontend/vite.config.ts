import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";
import path from "node:path";

// `base: "./"` makes the production build load assets via relative
// paths so the bundled HTML works under Electron's file:// protocol
// (Phase 3.1B). The Vite dev server keeps absolute root URLs in dev,
// so the proxy block below is unaffected.
export default defineConfig({
  base: "./",
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
