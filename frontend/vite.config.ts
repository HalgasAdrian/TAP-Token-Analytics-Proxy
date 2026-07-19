import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// Vite dev server runs on 5173 (matches the backend CORS default of
// http://localhost:5173). VITE_API_BASE points the app at the proxy API.
export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    host: true,
  },
});
