import tailwindcss from '@tailwindcss/vite'
import react from '@vitejs/plugin-react'
import { defineConfig, loadEnv } from 'vite'

// Backend target for the dev proxy. Override with VITE_API_TARGET=http://host:port.
export default defineConfig(({ mode }) => {
  const env = loadEnv(mode, process.cwd(), '')
  const target = env.VITE_API_TARGET || 'http://127.0.0.1:8770'
  const proxy = {
    '/api': { target, changeOrigin: true },
    '/files': { target, changeOrigin: true },
  }
  return {
    plugins: [react(), tailwindcss()],
    server: {
      host: '127.0.0.1',
      port: 5173,
      allowedHosts: [],
      proxy,
    },
    preview: { host: '127.0.0.1', allowedHosts: [], proxy },
  }
})
