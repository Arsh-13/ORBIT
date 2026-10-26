/// <reference types="vitest/config" />
import react from '@vitejs/plugin-react'
import { defineConfig } from 'vite'

// Where the FastAPI backend runs. Override with ORBIT_API_URL (e.g. to run a second copy on another port).
const API_TARGET = process.env.ORBIT_API_URL ?? 'http://127.0.0.1:8000'

// https://vite.dev/config/
export default defineConfig({
  plugins: [react()],
  // `npm test` runs the component tests in a simulated browser (jsdom).
  test: { environment: 'jsdom' },
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
