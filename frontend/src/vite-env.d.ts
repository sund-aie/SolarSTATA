/// <reference types="vite/client" />

declare module "*.css";

// Injected at build time by vite.config.ts from frontend/package.json
// — drives the version chip in the topbar Wordmark.
declare const __APP_VERSION__: string;
