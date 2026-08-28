import { defineConfig } from "vite";
import solid from "vite-plugin-solid";

// Dev-only: point the /api proxy at a running server (defaults to the compose port).
declare const process: { env: Record<string, string | undefined> };
const apiTarget = process.env.API_TARGET || "http://localhost:8039";

// The Python server serves ../static as its document root, so we build straight
// into it. Everything Vite needs to keep (favicon, manifest) lives in web/public.
export default defineConfig({
  plugins: [solid()],
  build: {
    outDir: "../static",
    emptyOutDir: true,
    target: "es2022",
    assetsDir: "assets",
  },
  server: {
    port: 5173,
    proxy: {
      "/api": {
        target: apiTarget,
        changeOrigin: true,
      },
    },
  },
});
