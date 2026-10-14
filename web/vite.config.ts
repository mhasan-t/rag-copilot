import tailwindcss from '@tailwindcss/vite'
import react from '@vitejs/plugin-react'
import { defineConfig } from 'vite'

export default defineConfig({
  plugins: [react(), tailwindcss()],
  server: {
    host: true,
    // The UI calls the API on its own origin (/v1/...), so no CORS setup is needed; in dev, Vite forwards it.
    proxy: { '/v1': process.env.API_PROXY_TARGET ?? 'http://localhost:8000' },
  },
})
