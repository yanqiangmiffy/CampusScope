import react from "@vitejs/plugin-react";
import { defineConfig } from "vite";

// development: /api goes to the demo backend on the host (compose publishes it on 127.0.0.1:8796), like nginx does
// in Docker; the frontend code only ever uses the relative path /api
export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    proxy: { "/api": { target: process.env.VITE_BACKEND_URL ?? "http://localhost:8796", changeOrigin: true } },
  },
});
