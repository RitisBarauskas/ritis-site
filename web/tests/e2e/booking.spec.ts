import type { Request, Route } from '@playwright/test';
import {
  answer,
  asksAgain,
  booking,
  CHECKOUT,
  fakeCheckout,
  fillForm,
  ID,
  inFlight,
  openDialog,
  requested,
  statusSequence,
} from './booking-mocks';
import { expect, test } from './fixtures';

test.describe('оплата из окна брони', () => {
  test('анкета уходит в API и ведёт на страницу оплаты', async ({ page }) => {
    const requests: Request[] = [];
    await fakeCheckout(page);
    await page.route('**/api/bookings', (route) => {
      requests.push(route.request());
      return route.fulfill({ status: 201, json: booking('awaiting_payment', CHECKOUT) });
    });
    await openDialog(page);
    await fillForm(page);
    await page.locator('#consent').check();

    await page.locator('#book-submit').click();

    await expect(page).toHaveURL(CHECKOUT);
    expect(requests).toHaveLength(1);
    expect(requests[0].method()).toBe('POST');
    expect(requests[0].headers()['idempotency-key']).toMatch(/^[0-9a-f-]{36}$/);
    expect(requests[0].postDataJSON()).toEqual({
      format: 'session',
      name: 'Тест',
      contact: 'test@example.com',
      about: '',
      links: '',
      consent: true,
      website: '',
    });
  });

  test('без согласия с офертой анкета не уходит', async ({ page }) => {
    await openDialog(page);
    await fillForm(page);

    await page.locator('#book-submit').click();

    // The browser stops the submission on the unticked box, before any request.
    await expect(page.locator('#consent:invalid')).toHaveCount(1);
    await expect(page.locator('#book')).toHaveAttribute('open');
  });

  test('ловушка для ботов людям не видна и клавиатурой до неё не дойти', async ({ page }) => {
    await openDialog(page);
    await expect(page.locator('input[name="leave_empty"]')).not.toBeInViewport();
    await page.locator('#format').focus();

    const reached: string[] = [];
    for (let step = 0; step < 12; step++) {
      await page.keyboard.press('Tab');
      reached.push(await page.evaluate(() => document.activeElement?.getAttribute('name') ?? ''));
    }

    expect(reached).toContain('links');
    expect(reached).not.toContain('leave_empty');
  });

  test('имя из одних пробелов браузер не пропускает', async ({ page }) => {
    await openDialog(page);
    await fillForm(page);
    await page.getByLabel('Как вас зовут').fill('   ');
    await page.locator('#consent').check();

    await page.locator('#book-submit').click();

    // The API trims spaces and would refuse an empty name with a message about the whole form.
    await expect(page.locator('input[name="name"]:invalid')).toHaveCount(1);
  });

  test('пока ждём API, анкету не поправить; закрытое окно запрос отменяет', async ({ page }) => {
    let release = () => {};
    await page.route('**/api/bookings', async (route) => {
      await new Promise<void>((resolve) => (release = resolve));
      await route.fulfill({ status: 201, json: booking('awaiting_payment', CHECKOUT) }).catch(() => {});
    });
    await openDialog(page);
    await fillForm(page);
    await page.locator('#consent').check();
    await page.locator('#book-submit').click();
    await expect(page.locator('#book-submit')).toHaveText('Открываем оплату…');
    await expect(page.getByLabel('Почта или Telegram')).toBeDisabled();
    // Well before the request's own 20 s timeout, which would drop it too.
    const cancelled = page.waitForEvent('requestfailed', {
      predicate: (request) => request.url().endsWith('/api/bookings'),
      timeout: 5000,
    });

    await page.keyboard.press('Escape');

    // The browser drops the request: there is no answer left to lead anywhere.
    await cancelled;
    release();
    // The attribute, not visibility: everything in a closed dialog is invisible.
    await expect(page.locator('#book-error')).toHaveAttribute('hidden');
    await expect(page.getByLabel('Почта или Telegram')).toBeEnabled();
    await expect(page.locator('#book-submit')).toHaveText('Оплатить €200 →');
  });

  test('API молчит: через 20 секунд понятное сообщение', async ({ page }) => {
    await page.clock.install();
    await page.route('**/api/bookings', () => new Promise<void>(() => {}));
    await openDialog(page);
    await fillForm(page);
    await page.locator('#consent').check();
    await page.locator('#book-submit').click();
    await expect(page.locator('#book-submit')).toHaveText('Открываем оплату…');

    await page.clock.runFor(20_000);

    await expect(page.locator('#book-error')).toHaveText(/Сервер долго не отвечает/);
    await expect(page.locator('#book-submit')).toBeEnabled();
  });

  test('сбой платёжного сервиса: понятное сообщение и повтор того же запроса', async ({ page }) => {
    const keys: string[] = [];
    await fakeCheckout(page);
    await page.route('**/api/bookings', (route) => {
      keys.push(route.request().headers()['idempotency-key']);
      return keys.length === 1
        ? route.fulfill({ status: 502, json: { detail: 'payment_provider_unavailable' } })
        : route.fulfill({ status: 201, json: booking('awaiting_payment', CHECKOUT) });
    });
    await openDialog(page);
    await fillForm(page);
    await page.locator('#consent').check();

    await page.locator('#book-submit').click();
    await expect(page.locator('#book-error')).toHaveText(/Платёжный сервис сейчас не отвечает/);
    await expect(page.locator('#book-submit')).toBeEnabled();
    await expect(page.locator('#book-submit')).toHaveText('Оплатить €200 →');

    await page.locator('#book-submit').click();
    await expect(page).toHaveURL(CHECKOUT);
    expect(keys[1]).toBe(keys[0]);
  });

  test('исправленная после сбоя анкета уходит с новым ключом', async ({ page }) => {
    const keys: string[] = [];
    await page.route('**/api/bookings', (route) => {
      keys.push(route.request().headers()['idempotency-key']);
      return route.fulfill({ status: 502, json: { detail: 'payment_provider_unavailable' } });
    });
    await openDialog(page);
    await fillForm(page, 'tpyo@example.com');
    await page.locator('#consent').check();
    await page.locator('#book-submit').click();
    await expect(page.locator('#book-error')).toBeVisible();

    await page.getByLabel('Почта или Telegram').fill('typo@example.com');
    await page.locator('#book-submit').click();

    await expect.poll(() => keys.length).toBe(2);
    expect(keys[1]).not.toBe(keys[0]);
  });

  const failures: Array<[string, (route: Route) => Promise<void>, RegExp]> = [
    ['API не принял анкету', (route) => route.fulfill({ status: 422, json: { detail: [] } }), /Проверьте анкету/],
    ['нет связи с сервером', (route) => route.abort(), /Нет связи с сервером/],
    ['сервер ответил ошибкой', (route) => route.fulfill({ status: 500, body: 'oops' }), /на нашей стороне/],
    // Not a missing booking: the API is not where the site expects it.
    ['по адресу API ничего нет', (route) => route.fulfill({ status: 404, body: 'Not Found' }), /на нашей стороне/],
    ['API ответил непонятно', (route) => route.fulfill({ status: 201, json: {} }), /на нашей стороне/],
  ];
  for (const [why, reply, message] of failures) {
    test(`${why}: понятное сообщение, анкета остаётся`, async ({ page }) => {
      await page.route('**/api/bookings', reply);
      await openDialog(page);
      await fillForm(page);
      await page.locator('#consent').check();

      await page.locator('#book-submit').click();

      await expect(page.locator('#book-error')).toHaveText(message);
      await expect(page.getByLabel('Почта или Telegram')).toHaveValue('test@example.com');
    });
  }

  test('повтор уже оплаченной анкеты ведёт на страницу брони', async ({ page }) => {
    await page.route('**/api/bookings', (route) => route.fulfill({ status: 201, json: booking('paid') }));
    await statusSequence(page, [answer('paid')]);
    await openDialog(page);
    await fillForm(page);
    await page.locator('#consent').check();

    await page.locator('#book-submit').click();

    await expect(page).toHaveURL(`/booking/?id=${ID}`);
    await expect(page.locator('#booking-title')).toHaveText('Оплачено');
  });

  test('бесплатный разбор не просит согласия и не ходит в API', async ({ page }) => {
    await openDialog(page, 'teardown');
    await expect(page.locator('#consent-row')).toBeHidden();
    await fillForm(page);
    const sent = requested(page, '**/api/**');

    await page.locator('#book-submit').click();

    await expect(page.locator('#toast')).toHaveText(/заявка на разбор/);
    expect(await sent).toBe(false);
  });
});

test.describe('страница брони', () => {
  test('оплачено', async ({ page }) => {
    await statusSequence(page, [answer('paid')]);
    await page.goto(`/booking/?id=${ID}`);
    await expect(page.locator('#booking-title')).toHaveText('Оплачено');
    await expect(page.locator('#booking-retry')).toBeHidden();
  });

  test('пока оплата в пути, страница спрашивает снова и показывает итог', async ({ page }) => {
    await page.clock.install();
    const calls = await statusSequence(page, [inFlight(1), inFlight(2), answer('paid')]);
    await page.goto(`/booking/?id=${ID}`);

    // One poll at a time: the page shows each answer's link in the same turn as it sets the
    // timer for the next poll, so the clock moves only once that timer is there.
    for (let asked = 1; asked < 3; asked++) {
      await expect(page.locator('#booking-resume')).toHaveAttribute('href', `${CHECKOUT}#${asked}`);
      await page.clock.runFor(3000);
    }

    await expect(page.locator('#booking-title')).toHaveText('Оплачено');
    expect(calls()).toBe(3);
  });

  test('опрос не бесконечный', async ({ page }) => {
    await page.clock.install();
    const marks = Array.from({ length: 20 }, (_, index) => index + 1);
    const calls = await statusSequence(page, marks.map((mark) => inFlight(mark)));
    await page.goto(`/booking/?id=${ID}`);

    for (const mark of marks.slice(0, -1)) {
      await expect(page.locator('#booking-resume')).toHaveAttribute('href', `${CHECKOUT}#${mark}`);
      await page.clock.runFor(3000);
    }

    await expect(page.locator('#booking-title')).toHaveText('Оплата пока не подтвердилась');
    // Its text sends the customer back to the checkout, which is still open.
    await expect(page.locator('#booking-resume')).toBeVisible();
    await expect(page.locator('#booking-resume')).toHaveAttribute('href', `${CHECKOUT}#20`);
    expect(calls()).toBe(20);
    const again = asksAgain(page);
    await page.clock.runFor(3000 * 10);
    expect(await again).toBe(false);
  });

  test('временный сбой связи не останавливает опрос', async ({ page }) => {
    await page.clock.install();
    const calls = await statusSequence(page, [(route) => route.abort(), answer('paid')]);
    await page.goto(`/booking/?id=${ID}`);
    await expect(page.locator('#booking-title')).toHaveText('Не удалось проверить оплату');
    await expect(page.locator('#booking-text')).toHaveText(/Нет связи с сервером/);

    await page.clock.runFor(3000);

    await expect(page.locator('#booking-title')).toHaveText('Оплачено');
    expect(calls()).toBe(2);
  });

  test('оплата открыта: можно вернуться к ней', async ({ page }) => {
    await fakeCheckout(page);
    await statusSequence(page, [inFlight()]);
    await page.goto(`/booking/?id=${ID}`);
    await expect(page.getByRole('link', { name: 'Вернуться к оплате' })).toBeVisible();

    await page.getByRole('link', { name: 'Вернуться к оплате' }).click();

    await expect(page).toHaveURL(CHECKOUT);
  });

  test('оплату не удалось открыть: страница не ждёт впустую', async ({ page }) => {
    await page.clock.install();
    const calls = await statusSequence(page, [answer('awaiting_payment', true)]);
    await page.goto(`/booking/?id=${ID}`);
    await expect(page.locator('#booking-title')).toHaveText('Не удалось открыть оплату');
    const again = asksAgain(page);

    await page.clock.runFor(3000 * 3);

    expect(await again).toBe(false);
    expect(calls()).toBe(1);
    await expect(page.locator('#booking-title')).toHaveText('Не удалось открыть оплату');
  });

  for (const [status, title] of [
    ['declined', 'Оплата не прошла'],
    ['expired', 'Время на оплату истекло'],
    // A checkout that could not be opened: the provider was down when the last one was asked for.
    ['awaiting_payment', 'Не удалось открыть оплату'],
  ] as const) {
    test(`${title}: «Оплатить снова» открывает новую страницу оплаты`, async ({ page }) => {
      const again: Request[] = [];
      await fakeCheckout(page);
      await statusSequence(page, [answer(status, true)]);
      await page.route(`**/api/bookings/${ID}/payments`, (route) => {
        again.push(route.request());
        return route.fulfill({ json: booking('awaiting_payment', 'https://pay.example/again') });
      });
      await page.goto(`/booking/?id=${ID}`);
      await expect(page.locator('#booking-title')).toHaveText(title);

      await page.locator('#booking-retry').click();

      await expect(page).toHaveURL('https://pay.example/again');
      expect(again.map((request) => request.method())).toEqual(['POST']);
    });
  }

  test('«Оплатить снова», а бронь тем временем оплачена: показывает её статус', async ({ page }) => {
    await statusSequence(page, [answer('declined', true), answer('paid')]);
    await page.route(`**/api/bookings/${ID}/payments`, (route) =>
      route.fulfill({ status: 409, json: { detail: 'booking_conflict' } }),
    );
    await page.goto(`/booking/?id=${ID}`);
    await expect(page.locator('#booking-title')).toHaveText('Оплата не прошла');

    await page.locator('#booking-retry').click();

    await expect(page.locator('#booking-title')).toHaveText('Оплачено');
    await expect(page.locator('#booking-retry')).toBeHidden();
  });

  test('«Оплатить снова», а платёжный сервис не отвечает: можно повторить', async ({ page }) => {
    await statusSequence(page, [answer('declined', true)]);
    await page.route(`**/api/bookings/${ID}/payments`, (route) =>
      route.fulfill({ status: 502, json: { detail: 'payment_provider_unavailable' } }),
    );
    await page.goto(`/booking/?id=${ID}`);
    await expect(page.locator('#booking-title')).toHaveText('Оплата не прошла');

    await page.locator('#booking-retry').click();

    await expect(page.locator('#booking-title')).toHaveText('Не удалось открыть оплату');
    await expect(page.locator('#booking-text')).toHaveText(/Платёжный сервис сейчас не отвечает/);
    await expect(page.locator('#booking-retry')).toBeVisible();
    await expect(page.locator('#booking-retry')).toBeEnabled();
  });

  test('оплата на проверке: повтор не предлагается', async ({ page }) => {
    await statusSequence(page, [answer('needs_review')]);
    await page.goto(`/booking/?id=${ID}`);
    await expect(page.locator('#booking-title')).toHaveText('Оплата получена и ждёт проверки');
    await expect(page.locator('#booking-retry')).toBeHidden();
  });

  for (const query of ['?error=not_found', '?id=../../etc', '?id=ABC']) {
    test(`ссылка без брони не ходит в API: ${query}`, async ({ page }) => {
      let calls = 0;
      await page.route('**/api/**', (route) => {
        calls += 1;
        return route.abort();
      });
      await page.goto(`/booking/${query}`);
      await expect(page.locator('#booking-title')).toHaveText('Бронь не найдена');
      expect(calls).toBe(0);
    });
  }

  test('бронь, которой нет у API: больше не спрашивает', async ({ page }) => {
    await page.clock.install();
    const calls = await statusSequence(page, [
      (route) => route.fulfill({ status: 404, json: { detail: 'booking_not_found' } }),
    ]);
    await page.goto(`/booking/?id=${ID}`);
    await expect(page.locator('#booking-title')).toHaveText('Бронь не найдена');
    const again = asksAgain(page);

    await page.clock.runFor(3000 * 3);

    expect(await again).toBe(false);
    expect(calls()).toBe(1);
  });

  test('шапка ведёт на разделы главной', async ({ page }) => {
    await statusSequence(page, [answer('paid')]);
    await page.goto(`/booking/?id=${ID}`);

    await page.getByRole('link', { name: 'Чем помогаю' }).click();

    await expect(page).toHaveURL('/#help');
    await expect(page.locator('#help')).toBeInViewport();
  });
});
