import tailwindcss from '@tailwindcss/vite'
import react from '@vitejs/plugin-react'
import { defineConfig } from 'vite'

// In development the browser talks only to Vite; /api is forwarded to FastAPI,
// so the frontend never needs the backend's address or CORS during dev.
// Set SAFESPEAK_API_URL to point the proxy at a backend on another port.
const apiTarget = process.env.SAFESPEAK_API_URL ?? 'http://127.0.0.1:8000'

export default defineConfig({
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
})
