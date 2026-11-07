import tailwindcss from '@tailwindcss/vite'
import react from '@vitejs/plugin-react'
import { defineConfig, loadEnv } from 'vite'

// Backend target for the dev proxy. Override with VITE_API_TARGET=http://host:port.
export default defineConfig(({ mode }) => {
  const env = loadEnv(mode, process.cwd(), '')
  const target = env.VITE_API_TARGET || 'http://localhost:8765'
  const proxy = {
    '/api': { target, changeOrigin: true },
    '/files': { target, changeOrigin: true },
  }
  return {
    plugins: [react(), tailwindcss()],
    server: {
      host: true,
      port: 5173,
      // Allow cloudflared quick tunnels (phone testing over HTTPS) and localhost.
      allowedHosts: true,
      proxy,
    },
    preview: { host: true, allowedHosts: true, proxy },
  }
})
