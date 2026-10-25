import react from '@vitejs/plugin-react'
import { defineConfig } from 'vite'

const API_TARGET = 'http://127.0.0.1:8000'

// https://vite.dev/config/
export default defineConfig({
  plugins: [react()],
  server: {
    // Listen on this machine only, so nobody else on your Wi-Fi can open it.
    host: '127.0.0.1',
    port: 5173,
    strictPort: true,
    // Forward /api/* to the FastAPI backend. The browser only talks to one origin,
    // so the backend doesn't need CORS.
    proxy: { '/api': API_TARGET },
  },
  preview: {
    host: '127.0.0.1',
    port: 4173,
    strictPort: true,
    proxy: { '/api': API_TARGET },
  },
})
