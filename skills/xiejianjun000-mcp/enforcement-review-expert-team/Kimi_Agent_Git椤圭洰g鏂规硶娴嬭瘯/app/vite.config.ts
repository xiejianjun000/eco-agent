import { defineConfig, loadEnv } from 'vite';
import react from '@vitejs/plugin-react';
import path from 'node:path';

// https://vitejs.dev/config/
export default defineConfig(({ mode }) => {
  const env = loadEnv(mode, process.cwd(), '');

  return {
    plugins: [react()],
    resolve: {
      alias: {
        '@': path.resolve(__dirname, './src'),
      },
    },
    define: {
      __APP_VERSION__: JSON.stringify(process.env.npm_package_version ?? '1.0.0'),
      __BUILD_TIME__: JSON.stringify(new Date().toISOString()),
      __APP_ENV__: JSON.stringify(mode),
    },
    server: {
      port: 5173,
      host: true,
      strictPort: false,
    },
    preview: {
      port: 4173,
      host: true,
    },
    build: {
      target: 'es2020',
      sourcemap: mode === 'development',
      assetsInlineLimit: 4096,
      chunkSizeWarningLimit: 800,
      emptyOutDir: true,
      reportCompressedSize: true,
      cssCodeSplit: true,
      minify: true,
      cssMinify: 'lightningcss',
      rollupOptions: {
        output: {
          manualChunks(id: string): string | undefined {
            if (!id.includes('node_modules')) return undefined;
            if (id.includes('react') || id.includes('scheduler')) return 'react-vendor';
            return 'vendor';
          },
          chunkFileNames: 'assets/[name]-[hash].js',
          entryFileNames: 'assets/[name]-[hash].js',
          assetFileNames: 'assets/[name]-[hash][extname]',
        },
      },
    },
  };
});
