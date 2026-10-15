import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

// In development the backend's dev server (ragcat.apps.dev) also stands in for S3 uploads and
// CloudFront /pages/*, so both /v1 and /dev are proxied to it. In AWS everything is same-origin
// behind CloudFront.
export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    proxy: {
      '/v1': process.env.RAGCAT_API ?? 'http://localhost:8010',
      '/dev': process.env.RAGCAT_API ?? 'http://localhost:8010',
    },
  },
})
