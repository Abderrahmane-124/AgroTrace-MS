import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

export default defineConfig({
    plugins: [react()],
    server: {
        host: '0.0.0.0',
        port: 3000,
        proxy: {
            '/api': {
                target: 'http://dashboard-backend:8085',
                changeOrigin: true,
            }
        }
    },
    build: {
        outDir: 'dist'
    }
})
