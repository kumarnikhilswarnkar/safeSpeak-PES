import tailwindcss from '@tailwindcss/vite'
import react from '@vitejs/plugin-react'
import { defineConfig, loadEnv } from 'vite'

// In development the browser talks only to Vite; /api is forwarded to FastAPI,
// so the frontend never needs the backend's address or CORS during dev.
// SAFESPEAK_API_URL points the proxy at the backend. It is read from the shell
// environment or from frontend/.env, .env.local, .env.[mode] (shell values win).
// It has no VITE_ prefix, so it is used by this config only and never reaches the browser bundle.
const DEFAULT_API_TARGET = 'http://127.0.0.1:8001'

export default defineConfig(({ mode }) => {
  const env = loadEnv(mode, process.cwd(), '')
  const apiTarget = env.SAFESPEAK_API_URL || DEFAULT_API_TARGET

  return {
    plugins: [react(), tailwindcss()],
    server: {
      port: 5173,
      strictPort: true,
      proxy: {
        '/api': apiTarget,
      },
    },
    build: {
      rollupOptions: {
        output: {
          // Charts are only needed on dashboard pages; keep them out of the main chunk.
          manualChunks: (id) => (id.includes('recharts') || id.includes('d3-') ? 'charts' : undefined),
        },
      },
    },
  }
})
