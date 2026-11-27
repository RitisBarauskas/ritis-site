// Every browser test runs inside this guard: the real API is out of reach (the preview server
// proxies /api to a local one), and an uncaught error of a page script fails the test.
import { test as base, expect } from '@playwright/test';

// scripts/check-mutations.mjs looks for this text to tell a mutant that breaks the page script
// from one that a test catches.
const PAGE_SCRIPT_ERROR = 'uncaught error in a page script';

export const test = base.extend<{ guard: void }>({
  guard: [
    async ({ page }, use) => {
      // A route a test adds is tried first: Playwright runs the newest matching route first.
      await page.route('**/api/**', (route) => route.abort());
      const errors: string[] = [];
      page.on('pageerror', (error) => errors.push(error.message));
      await use();
      expect(errors, PAGE_SCRIPT_ERROR).toEqual([]);
    },
    { auto: true },
  ],
});

export { expect };
