import react from '@vitejs/plugin-react'
import { defineConfig } from 'vite'

// El frontend llama a "/api/..." y Vite lo reenvía al backend (FastAPI en el puerto 8000).
export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    allowedHosts: true, // permite abrir la app con un túnel https (ngrok/cloudflared) desde el celular
    proxy: { '/api': 'http://127.0.0.1:8000' },
  },
})
