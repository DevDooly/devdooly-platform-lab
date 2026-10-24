import { defineConfig } from 'astro/config';
import react from '@astrojs/react';

export default defineConfig({
  output: 'static',
  site: process.env.SITE_URL || undefined,
  base: process.env.SITE_BASE || '/',
  integrations: [react()],
  devToolbar: { enabled: false },
  vite: {
    server: {
      proxy: { '^/api(?:/|$)': { target: process.env.API_PROXY_TARGET || 'http://127.0.0.1:8080', changeOrigin: true } },
    },
  },
});
