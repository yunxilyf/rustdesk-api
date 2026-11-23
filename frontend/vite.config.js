import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'

export default defineConfig({
  base: '/static/console/',
  plugins: [vue()],
  server: {
    port: 5173,
    proxy: {
      '/api': {
        target: 'http://127.0.0.1:21114',
        changeOrigin: true,
      },
    },
  },
  build: {
    outDir: '../static/console',
    emptyOutDir: true,
    chunkSizeWarningLimit: 1500,
  },
})
