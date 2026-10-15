import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

// In development the backend's dev server (ragcat.apps.dev) also stands in for S3 uploads and
// CloudFront /pages/*, so both /v1 and /dev are proxied to it. In AWS everything is same-origin
// behind CloudFront. widget.html is the Website widget's frame page: the api fills it in per
// Assistant at /v1/widget/{aid}/frame (docs/api-design.md §7); public/widget.js is its loader.
export default defineConfig({
  plugins: [react()],
  build: {
    rollupOptions: { input: { main: 'index.html', widget: 'widget.html' } },
  },
  server: {
    port: 5173,
    proxy: {
      '/v1': process.env.RAGCAT_API ?? 'http://localhost:8010',
      '/dev': process.env.RAGCAT_API ?? 'http://localhost:8010',
    },
  },
})
