import { defineConfig } from "vitest/config";
import react from "@vitejs/plugin-react";
import tailwindcss from "@tailwindcss/vite";

export default defineConfig({
  base: "/app/",
  plugins: [react(), tailwindcss()],
  server: {
    proxy: {
      "/api": "http://localhost:8080",
    },
  },
  test: {
    exclude: ["e2e/**", "node_modules/**", "dist/**"],
  },
});
