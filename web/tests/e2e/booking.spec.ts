import { expect, test, type Request, type Route } from '@playwright/test';
import { answer, booking, CHECKOUT, fakeCheckout, fillForm, ID, openDialog, statusSequence } from './booking-mocks';

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

    await page.waitForURL(CHECKOUT);
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
    let sent = 0;
    await page.route('**/api/bookings', (route) => {
      sent += 1;
      return route.abort();
    });
    await openDialog(page);
    await fillForm(page);

    await page.locator('#book-submit').click();

    await expect(page.locator('#book')).toHaveAttribute('open');
    expect(sent).toBe(0);
  });

  test('ловушка для ботов людям не видна и не берёт фокус', async ({ page }) => {
    await openDialog(page);
    const honeypot = page.locator('input[name="website"]');
    await expect(honeypot).not.toBeInViewport();
    await expect(honeypot).toHaveAttribute('tabindex', '-1');
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
    await page.waitForURL(CHECKOUT);
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

    await page.waitForURL(`**/booking/?id=${ID}`);
    await expect(page.locator('#booking-title')).toHaveText('Оплачено');
  });

  test('бесплатный разбор не просит согласия и не ходит в API', async ({ page }) => {
    let sent = 0;
    await page.route('**/api/**', (route) => {
      sent += 1;
      return route.abort();
    });
    await openDialog(page, 'teardown');
    await expect(page.locator('#consent-row')).toBeHidden();
    await fillForm(page);

    await page.locator('#book-submit').click();

    await expect(page.locator('#toast')).toHaveText(/заявка на разбор/);
    expect(sent).toBe(0);
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
    const calls = await statusSequence(page, [
      answer('awaiting_payment'),
      answer('awaiting_payment'),
      answer('paid'),
    ]);
    await page.goto(`/booking/?id=${ID}`);
    await expect(page.locator('#booking-title')).toHaveText('Проверяем оплату…');

    await page.clock.runFor(3000);
    await page.clock.runFor(3000);

    await expect(page.locator('#booking-title')).toHaveText('Оплачено');
    expect(calls()).toBe(3);
  });

  test('опрос не бесконечный', async ({ page }) => {
    await page.clock.install();
    const calls = await statusSequence(page, [answer('awaiting_payment')]);
    await page.goto(`/booking/?id=${ID}`);
    await expect(page.locator('#booking-title')).toHaveText('Проверяем оплату…');

    // One poll at a time: each answer arrives after the timer that asked for it has run.
    for (let asked = 1; asked < 20; asked++) {
      await expect.poll(calls).toBe(asked);
      await page.clock.runFor(3000);
    }

    await expect(page.locator('#booking-title')).toHaveText('Оплата пока не подтвердилась');
    await page.clock.runFor(3000 * 10);
    expect(calls()).toBe(20);
  });

  for (const [status, title] of [
    ['declined', 'Оплата не прошла'],
    ['expired', 'Время на оплату истекло'],
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

      await page.waitForURL('https://pay.example/again');
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

  test('бронь, которой нет у API', async ({ page }) => {
    await statusSequence(page, [(route) => route.fulfill({ status: 404, json: { detail: 'booking_not_found' } })]);
    await page.goto(`/booking/?id=${ID}`);
    await expect(page.locator('#booking-title')).toHaveText('Бронь не найдена');
  });

  test('нет связи с сервером: понятное сообщение', async ({ page }) => {
    await statusSequence(page, [(route) => route.abort()]);
    await page.goto(`/booking/?id=${ID}`);
    await expect(page.locator('#booking-title')).toHaveText('Не удалось проверить оплату');
    await expect(page.locator('#booking-text')).toHaveText(/Нет связи с сервером/);
  });

  test('шапка ведёт на разделы главной', async ({ page }) => {
    await statusSequence(page, [answer('paid')]);
    await page.goto(`/booking/?id=${ID}`);

    await page.getByRole('link', { name: 'Чем помогаю' }).click();

    await page.waitForURL('**/#help');
    await expect(page.locator('#help')).toBeInViewport();
  });

  test('загружается без ошибок в консоли', async ({ page }) => {
    const errors: string[] = [];
    page.on('pageerror', (error) => errors.push(error.message));
    await statusSequence(page, [answer('paid')]);
    await page.goto(`/booking/?id=${ID}`);
    await expect(page.locator('#booking-title')).toHaveText('Оплачено');
    expect(errors).toEqual([]);
  });
});
