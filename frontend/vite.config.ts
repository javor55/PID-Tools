/// <reference types="vitest/config" />
// Vývoj: npm run dev (Vite na :5173, API na :8765 přes proxy). Sestavení: npm run build → pidtools/api/ui
// (FastAPI ho servíruje na /, fonty na /fonts ze static/fonts).
import react from "@vitejs/plugin-react";
import { defineConfig } from "vite";

declare const process: { env: Record<string, string | undefined> };   // běží v Node (bez @types/node)
const API = process.env.PID_API ?? "http://127.0.0.1:8765";
const proxied = ["/health", "/i18n", "/workspaces", "/jobs", "/opc", "/fonts"];

export default defineConfig({
  plugins: [react()],
  build: { outDir: "../pidtools/api/ui", emptyOutDir: true, sourcemap: false },
  // prohlížeč záznamu (viewer.js, viewer_an.js, viewer.css) sdílí s dnešním webem pidtools/ui/static
  server: { proxy: Object.fromEntries(proxied.map((p) => [p, API])), fs: { allow: [".."] } },
  test: { environment: "jsdom", include: ["tests/**/*.test.ts?(x)"] },
});
