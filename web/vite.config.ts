import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';

// 开发模式：/api 代理到 eco-server（默认 127.0.0.1:8788）
export default defineConfig({
  plugins: [react()],
  server: {
    port: 5174,
    proxy: {
      '/api': { target: 'http://127.0.0.1:8788', changeOrigin: true },
      '/healthz': { target: 'http://127.0.0.1:8788', changeOrigin: true },
    },
  },
  build: {
    outDir: 'dist',
    sourcemap: false,
  },
});
