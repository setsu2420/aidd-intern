import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import path from 'path'

export default defineConfig({
  plugins: [react()],
  resolve: {
    alias: {
      '@': path.resolve(__dirname, './src'),
    },
  },
  server: {
    port: 5173,
    proxy: {
      '/api': {
        target: 'http://[::1]:7860',
        changeOrigin: true,
        ws: true, // Proxy WebSocket connections (/api/ws/...)
      },
      '/auth': {
        target: 'http://[::1]:7860',
        changeOrigin: true,
      },
    },
  },
  build: {
    outDir: 'dist',
    sourcemap: false,
    rollupOptions: {
      output: {
        manualChunks(id) {
          if (!id.includes('node_modules')) {
            return undefined;
          }

          if (id.includes('@mui/') || id.includes('@emotion/')) {
            return 'mui-vendor';
          }

          if (id.includes('@ai-sdk/') || id.includes('/ai/')) {
            return 'ai-vendor';
          }

          if (
            id.includes('react/') ||
            id.includes('react-dom/') ||
            id.includes('scheduler/')
          ) {
            return 'react-vendor';
          }

          if (
            id.includes('react-markdown') ||
            id.includes('react-syntax-highlighter') ||
            id.includes('remark-') ||
            id.includes('micromark') ||
            id.includes('rehype-') ||
            id.includes('unist-') ||
            id.includes('mdast-')
          ) {
            return 'markdown-vendor';
          }

          return 'vendor';
        },
      },
    },
  },
})
