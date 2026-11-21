// SPDX-License-Identifier: AGPL-3.0-or-later
// Entwicklungsserver und Build. Der Server lauscht nur an 127.0.0.1 (Fachkonzept 11.1) und
// leitet /api an das Backend weiter.
import react from "@vitejs/plugin-react";
import { defineConfig } from "vitest/config";

export default defineConfig({
  plugins: [react()],
  server: {
    host: "127.0.0.1",
    port: 5173,
    strictPort: true,
    proxy: { "/api": "http://127.0.0.1:8000" },
  },
  preview: { host: "127.0.0.1" },
  test: {
    environment: "happy-dom",
    include: ["src/**/*.test.{ts,tsx}"],
  },
});
