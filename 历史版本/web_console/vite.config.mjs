import { defineConfig } from 'vite';
import { resolve } from 'node:path';

export default defineConfig({
  build: {
    outDir: resolve(__dirname, 'static'),
    emptyOutDir: false,
    cssCodeSplit: false,
    rollupOptions: {
      input: resolve(__dirname, 'frontend/main.jsx'),
      output: {
        entryFileNames: 'app.js',
        assetFileNames: (assetInfo) => {
          if (assetInfo.name === 'style.css') {
            return 'app.css';
          }
          return '[name][extname]';
        },
      },
    },
  },
});
