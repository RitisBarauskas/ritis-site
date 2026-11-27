import { expect, test } from '@playwright/test';
import { answer, booking, CHECKOUT, fakeCheckout, fillForm, ID, openDialog, statusSequence } from './booking-mocks';

// Playwright turns Chrome's back/forward cache off; browsers of real people keep it on,
// and a page restored from it comes back exactly as it was left.
test.use({ launchOptions: { ignoreDefaultArgs: ['--disable-back-forward-cache'] } });

test.describe('возврат со страницы оплаты кнопкой «Назад»', () => {
  test('окно брони: анкету можно отправить снова', async ({ page }) => {
    await fakeCheckout(page);
    await page.route('**/api/bookings', (route) =>
      route.fulfill({ status: 201, json: booking('awaiting_payment', CHECKOUT) }),
    );
    await openDialog(page);
    await fillForm(page);
    await page.locator('#consent').check();
    await page.locator('#book-submit').click();
    await page.waitForURL(CHECKOUT);

    // A restore from the cache fires pageshow, not load.
    await page.goBack({ waitUntil: 'commit' });

    // Still open: the page came back from the cache, not from a fresh load.
    await expect(page.locator('#book')).toHaveAttribute('open');
    await expect(page.locator('#book-submit')).toBeEnabled();
    await expect(page.locator('#book-submit')).toHaveText('Оплатить €200 →');
  });

  test('страница брони: статус проверяется заново', async ({ page }) => {
    await fakeCheckout(page);
    await statusSequence(page, [answer('declined', true), answer('paid')]);
    await page.route(`**/api/bookings/${ID}/payments`, (route) =>
      route.fulfill({ json: booking('awaiting_payment', CHECKOUT) }),
    );
    await page.goto(`/booking/?id=${ID}`);
    await page.locator('#booking-retry').click();
    await page.waitForURL(CHECKOUT);

    // A restore from the cache fires pageshow, not load.
    await page.goBack({ waitUntil: 'commit' });

    await expect(page.locator('#booking-title')).toHaveText('Оплачено');
  });
});
