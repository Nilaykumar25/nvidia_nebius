import { defineConfig, loadEnv } from 'vite'
import react from '@vitejs/plugin-react'

export default defineConfig(({ mode }) => {
  const env = loadEnv(mode, process.cwd(), '')

  // In production, VITE_API_BASE_URL (or legacy VITE_API_URL) points to the backend.
  // In development, proxy /api to localhost:8000.
  const apiTarget = env.VITE_API_BASE_URL || env.VITE_API_URL || 'http://127.0.0.1:8000'

  return {
    plugins: [react()],

    server: {
      proxy: {
        '/api': {
          target: apiTarget,
          rewrite: (p) => p.replace(/^\/api/, ''),
          changeOrigin: true,
        },
      },
    },

    test: {
      environment: 'jsdom',
      globals: true,
      setupFiles: ['./src/test/setup.js'],
    },
  }
})
