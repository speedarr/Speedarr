import { defineConfig } from 'vitest/config'
import react from '@vitejs/plugin-react'
import path from 'node:path'

// https://vitejs.dev/config/
export default defineConfig({
  plugins: [react()],
  define: {
    __APP_VERSION__: JSON.stringify(process.env.VITE_APP_VERSION || 'dev'),
    __APP_COMMIT__: JSON.stringify(process.env.VITE_APP_COMMIT || 'unknown'),
    __APP_BRANCH__: JSON.stringify(process.env.VITE_APP_BRANCH || 'unknown'),
  },
  resolve: {
    alias: {
      '@': path.resolve(import.meta.dirname, './src'),
    },
  },
  server: {
    port: 3000,
    proxy: {
      '/api': {
        target: 'http://localhost:9494',
        changeOrigin: true,
      },
    },
  },
  build: {
    outDir: 'dist',
    sourcemap: false,
  },
  test: {
    environment: 'jsdom',
    setupFiles: ['./src/test/setup.ts'],
    include: ['src/**/*.test.{ts,tsx}'],
    // The arm64 leg of the image build runs this suite under QEMU, roughly 70x slower than
    // native (91 s for a 1.2 s run). The slowest tests take ~120 ms natively, which is over
    // vitest's default 5 s there, so give each test 30 s; a hung test still fails, just later.
    testTimeout: 30_000,
  },
})
