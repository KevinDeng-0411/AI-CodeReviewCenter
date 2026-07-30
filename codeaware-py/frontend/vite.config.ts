import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

const apiTarget = process.env.CODEAWARE_API_BASE_URL ?? "http://localhost:8000";

// 开发：Vite 5173 代理 /api -> FastAPI 8000，避免 CORS
// 生产：npm run build -> dist/，由 FastAPI 静态托管（同源）
export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    proxy: {
      "/api": {
        target: apiTarget,
        changeOrigin: true,
      },
      "/health": {
        target: apiTarget,
        changeOrigin: true,
      },
    },
  },
  build: {
    outDir: "dist",
    sourcemap: false,
  },
});
