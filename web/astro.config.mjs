import { defineConfig } from 'astro/config';

export default defineConfig({
  site: 'https://ritis.dev',
  // Astro 7 defaults to 'jsx', which drops spaces between inline elements; the page relies on them.
  compressHTML: true,
});
