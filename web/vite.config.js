import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'

// https://vite.dev/config/
export default defineConfig({
  plugins: [vue()],
  server: {
    port: 5100,
    proxy: {
      // Order matters: the first matching prefix wins, so the backend API is
      // listed before the static-file fallback.
      '/api/v1': {
        target: 'http://127.0.0.1:8000',
        changeOrigin: true,
      },
      // Static JSON fixtures still served by server.py.
      '/api': {
        target: 'https://127.0.0.1:9001',
        changeOrigin: true,
        secure: false,
      },
    },
  },
})
