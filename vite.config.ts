import { defineConfig, loadEnv } from 'vite'
import react from '@vitejs/plugin-react'

// https://vite.dev/config/
export default defineConfig(({ mode }) => {
  const env = loadEnv(mode, '.', '')

  return {
    plugins: [react()],
    base: env.VITE_BASE_PATH || '/',
    server: {
      proxy: {
        '/api': {
          target: env.VITE_API_TARGET || 'http://127.0.0.1:8081',
          changeOrigin: true,
        },
      },
    },
  }
})
