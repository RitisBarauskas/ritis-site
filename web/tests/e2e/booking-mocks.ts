// The booking API as the browser tests stand it in: answers are mocked per test with page.route.
import type { Page, Route } from '@playwright/test';

export const ID = 'a'.repeat(32);
export const CHECKOUT = 'https://pay.example/checkout';

export function booking(status: string, checkoutUrl: string | null = null, canRetry = false) {
  return {
    id: ID,
    status,
    format: 'session',
    amount_minor: 20000,
    currency: 'EUR',
    checkout_url: checkoutUrl,
    can_retry_payment: canRetry,
  };
}

/** Stands in for the provider's checkout page, so a redirect to it can be observed. */
export async function fakeCheckout(page: Page): Promise<void> {
  await page.route('https://pay.example/**', (route) =>
    route.fulfill({ contentType: 'text/html', body: '<title>checkout</title>' }),
  );
}

/** Answers status requests with the given answers in turn, repeating the last one. */
export async function statusSequence(page: Page, answers: Array<(route: Route) => Promise<void>>) {
  let calls = 0;
  await page.route(`**/api/bookings/${ID}`, (route) => {
    const answer = answers[Math.min(calls, answers.length - 1)];
    calls += 1;
    return answer(route);
  });
  return () => calls;
}

/**
 * Whether the page sends a request to `url` within `ms` of real time. Start it before the
 * action: a request the page sends reaches the test only a little later.
 */
export function requested(page: Page, url: string, ms = 2000): Promise<boolean> {
  return page.waitForRequest(url, { timeout: ms }).then(
    () => true,
    () => false,
  );
}

export const asksAgain = (page: Page) => requested(page, `**/api/bookings/${ID}`);

export const answer = (status: string, canRetry = false) => (route: Route) =>
  route.fulfill({ json: booking(status, null, canRetry) });

/**
 * A checkout is open and the customer has not finished it yet. A mark tells the answers
 * apart: the page shows the link, and the test can wait for it before moving the clock.
 */
export const inFlight =
  (mark?: number) =>
  (route: Route): Promise<void> =>
    route.fulfill({ json: booking('awaiting_payment', mark ? `${CHECKOUT}#${mark}` : CHECKOUT) });

export async function openDialog(page: Page, format = 'session'): Promise<void> {
  await page.goto('/');
  await page.locator(`main [data-book="${format}"]`).first().click();
}

export async function fillForm(page: Page, contact = 'test@example.com'): Promise<void> {
  await page.getByLabel('Как вас зовут').fill('Тест');
  await page.getByLabel('Почта или Telegram').fill(contact);
}
