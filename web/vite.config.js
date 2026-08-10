import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'

// https://vite.dev/config/
export default defineConfig({
  plugins: [vue()],
  server: {
    port: 5100,
    proxy: {
      // Placeholder for the future FastAPI backend; server.py answers this for now.
      '/api': {
        target: 'https://127.0.0.1:9001',
        changeOrigin: true,
        secure: false,
      },
    },
  },
})
