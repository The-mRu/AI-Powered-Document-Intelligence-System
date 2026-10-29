import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// Dev server (npm run dev) forwards /api to the backend; in Docker, nginx does the same job.
export default defineConfig({
  plugins: [react()],
  server: { port: 5173, proxy: { "/api": "http://localhost:8000" } },
  test: { environment: "jsdom", globals: true, setupFiles: ["./tests/setup.js"] },
});
