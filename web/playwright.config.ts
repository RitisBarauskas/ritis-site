import { defineConfig } from '@playwright/test';

const PORT = 4329;

export default defineConfig({
  testDir: 'tests/e2e',
  fullyParallel: true,
  reporter: 'list',
  use: {
    baseURL: `http://127.0.0.1:${PORT}`,
    // Uses the locally installed Chrome, so no browser download is needed.
    channel: 'chrome',
    reducedMotion: 'reduce',
  },
  webServer: {
    // Always test a fresh build: a stale dist/ would let tests pass against old code.
    command: `npm run build && npx astro preview --host 127.0.0.1 --port ${PORT}`,
    url: `http://127.0.0.1:${PORT}`,
    reuseExistingServer: false,
    timeout: 180_000,
  },
});
