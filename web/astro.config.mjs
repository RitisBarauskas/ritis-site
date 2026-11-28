import { defineConfig } from 'astro/config';

export default defineConfig({
  site: 'https://ritis.dev',
  // Astro 7 defaults to 'jsx', which drops spaces between inline elements; the page relies on them.
  compressHTML: true,
  // The local API sends the customer back from the checkout to http://127.0.0.1:4321
  // (RITIS_SITE_URL); left to itself, the dev server may listen on ::1 only.
  server: { host: '127.0.0.1' },
  vite: {
    server: {
      // The price catalog sits outside web/ (shared with the API); let the dev server read it.
      fs: { allow: ['.', '../shared'] },
      // The site calls /api on its own origin; in production Firebase Hosting is to forward it.
      // Vite's preview server inherits this proxy; the browser tests block /api themselves.
      proxy: { '/api': 'http://127.0.0.1:8000' },
    },
  },
});
