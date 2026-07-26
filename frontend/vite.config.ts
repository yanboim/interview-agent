import { fileURLToPath, URL } from "node:url";
import { defineConfig } from "vite";
import vue from "@vitejs/plugin-vue";

// 生产构建由 FastAPI 在 /static 下托管；开发模式从 Vite 根路径访问。
// dev server (5173) 把 /api 与 /ready|/health|/metrics 代理到后端 (8000),
// 浏览器只连接 dev server,满足后端 CSP `connect-src 'self'`。
export default defineConfig(({ command }) => ({
  plugins: [vue()],
  base: command === "serve" ? "/" : "/static/",
  build: {
    outDir: "dist",
    emptyOutDir: true,
    target: "es2020",
    manifest: true,
  },
  resolve: {
    alias: {
      "@": fileURLToPath(new URL("./src", import.meta.url)),
    },
  },
  server: {
    port: 5173,
    proxy: {
      "/api": "http://localhost:8000",
      "/ready": "http://localhost:8000",
      "/health": "http://localhost:8000",
      "/metrics": "http://localhost:8000",
    },
  },
}));
