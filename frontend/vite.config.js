import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

// In development the browser talks only to Vite; /api is forwarded to FastAPI,
// so the frontend never needs the backend's address or CORS during dev.
// Set SAFESPEAK_API_URL to point the proxy at a backend on another port.
const apiTarget = process.env.SAFESPEAK_API_URL ?? 'http://127.0.0.1:8000'

export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    strictPort: true,
    proxy: {
      '/api': apiTarget,
    },
  },
})
