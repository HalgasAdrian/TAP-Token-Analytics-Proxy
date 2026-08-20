import react from "@vitejs/plugin-react";
import { defineConfig } from "vite";

const API_TARGET = process.env.VITE_DEV_API_TARGET ?? "http://localhost:8000";

// The dev server proxies the API so development is same-origin too, matching
// production where the API serves this bundle. No CORS either way.
export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    host: true,
    proxy: {
      "/v1": { target: API_TARGET, changeOrigin: true },
      "/metrics": { target: API_TARGET, changeOrigin: true },
    },
  },
});
