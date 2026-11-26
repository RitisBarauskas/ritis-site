import { defineConfig } from '@playwright/test';

const PORT = 4329;
const CI = Boolean(process.env.CI);

export default defineConfig({
  testDir: 'tests/e2e',
  fullyParallel: true,
  // A test.only left in a commit must fail CI, not silently skip the other tests.
  forbidOnly: CI,
  reporter: CI ? [['list'], ['github']] : 'list',
  use: {
    baseURL: `http://127.0.0.1:${PORT}`,
    // Uses the installed Chrome (GitHub's Ubuntu runners ship it), so no browser download is needed.
    channel: 'chrome',
    reducedMotion: 'reduce',
    trace: 'retain-on-failure',
  },
  webServer: {
    // Always test a fresh build: a stale dist/ would let tests pass against old code.
    command: `npm run build && npx astro preview --host 127.0.0.1 --port ${PORT}`,
    url: `http://127.0.0.1:${PORT}`,
    reuseExistingServer: false,
    timeout: 180_000,
  },
});
