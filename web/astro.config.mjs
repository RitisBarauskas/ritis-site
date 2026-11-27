import { defineConfig } from 'astro/config';

export default defineConfig({
  site: 'https://ritis.dev',
  // Astro 7 defaults to 'jsx', which drops spaces between inline elements; the page relies on them.
  compressHTML: true,
  vite: {
    server: {
      // The price catalog sits outside web/ (shared with the API); let the dev server read it.
      fs: { allow: ['.', '../shared'] },
      // Same origin as in production, where Firebase Hosting rewrites /api/** to the API.
      proxy: { '/api': 'http://127.0.0.1:8000' },
    },
  },
});
