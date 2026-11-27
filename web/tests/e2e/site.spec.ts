import type { Page } from '@playwright/test';
import { expect, test } from './fixtures';

const FAVICON = /\/favicon\.ico$/;

async function collectErrors(page: Page): Promise<string[]> {
  const errors: string[] = [];
  page.on('pageerror', (error) => errors.push(error.message));
  page.on('console', (msg) => {
    // No favicon yet (none in the design either); the browser's automatic request for it is not a page error.
    if (msg.type() === 'error' && !FAVICON.test(msg.location().url)) errors.push(msg.text());
  });
  return errors;
}

test.describe('страница', () => {
  test('загружается без ошибок в консоли', async ({ page }) => {
    const errors = await collectErrors(page);

    await page.goto('/', { waitUntil: 'networkidle' });

    expect(errors).toEqual([]);
  });

  for (const width of [390, 820, 1440]) {
    test(`не даёт горизонтальной прокрутки на ширине ${width} ни на одной вкладке демо`, async ({ page }) => {
      await page.setViewportSize({ width, height: 900 });
      await page.goto('/');

      // Each demo tab has different content, so each one can push the layout wider.
      const overflowByTab: Record<string, number> = {};
      for (const tab of await page.getByRole('tab').all()) {
        await tab.click();
        overflowByTab[(await tab.textContent()) ?? ''] =
          await page.evaluate(() => document.documentElement.scrollWidth - window.innerWidth);
      }

      expect(overflowByTab).toEqual({ 'Как спрашивают обычно': 0, 'Как спрашиваю я': 0, 'Как на самом деле': 0 });
    });
  }

  test('все фото загружаются, когда до них доходит прокрутка', async ({ page }) => {
    await page.goto('/');
    const images = page.locator('main img');

    const loaded: boolean[] = [];
    for (const img of await images.all()) {
      await img.scrollIntoViewIfNeeded();
      loaded.push(await img.evaluate((el: HTMLImageElement) =>
        el.complete && el.naturalWidth > 0
          ? true
          : new Promise<boolean>((resolve) => {
              el.addEventListener('load', () => resolve(el.naturalWidth > 0), { once: true });
              el.addEventListener('error', () => resolve(false), { once: true });
            })));
    }

    expect(loaded).toEqual([true, true, true]);
  });

  test('внешние ссылки открываются в новой вкладке без доступа к opener', async ({ page }) => {
    await page.goto('/');

    const unsafe = await page.locator('a[href^="http"]').evaluateAll((links) =>
      links
        .filter((a) => a.getAttribute('target') !== '_blank' || !/\bnoopener\b/.test(a.getAttribute('rel') ?? ''))
        .map((a) => a.getAttribute('href')));

    expect(unsafe).toEqual([]);
  });

  test('обещает только те способы оплаты, что подключены', async ({ page }) => {
    await page.goto('/');

    await expect(page.locator('.paychips span')).toHaveText(['Visa', 'Mastercard']);
    // Not in the offers, the FAQ or the booking dialog until a Russian provider is connected.
    const text = await page.locator('body').textContent();
    expect(text).not.toMatch(/«Мир»|СБП/);
  });

  test('цены из каталога, разряды через неразрывный пробел', async ({ page }) => {
    await page.goto('/');

    // Raw textContent: toHaveText would normalise a non-breaking space into a plain one.
    const prices = await page.locator('#help .price b').allTextContents();

    const nbsp = String.fromCharCode(0xa0);
    expect(prices).toEqual(['€200', `от €2${nbsp}000`, '€500', `от €1${nbsp}000/мес`]);
  });
});

test.describe('тема', () => {
  test('по умолчанию тёмная', async ({ page }) => {
    await page.goto('/');

    await expect(page.locator('html')).toHaveAttribute('data-theme', 'dark');
  });

  test('переключатель включает светлую и запоминает её после перезагрузки', async ({ page }) => {
    await page.goto('/');
    await page.getByRole('button', { name: 'Сменить тему' }).click();

    await page.reload();

    await expect(page.locator('html')).toHaveAttribute('data-theme', 'light');
  });

  test('сохранённая светлая тема применяется до отрисовки тела страницы', async ({ page }) => {
    await page.addInitScript(() => {
      localStorage.setItem('ritis-theme', 'light');
      // Init scripts run before <html> exists, so watch the whole document for <body> to appear.
      new MutationObserver((_, observer) => {
        if (!document.body) return;
        (window as unknown as { themeAtBody: string | undefined }).themeAtBody = document.documentElement.dataset.theme;
        observer.disconnect();
      }).observe(document, { childList: true, subtree: true });
    });

    await page.goto('/');

    expect(await page.evaluate(() => (window as unknown as { themeAtBody?: string }).themeAtBody)).toBe('light');
  });
});

test.describe('демо «Как я работаю с ИИ»', () => {
  test('вкладка «Как спрашиваю я» показывает свою панель и прячет первую', async ({ page }) => {
    await page.goto('/');

    await page.getByRole('tab', { name: 'Как спрашиваю я' }).click();

    await expect(page.locator('#panel-pro')).toBeVisible();
    await expect(page.locator('#panel-naive')).toBeHidden();
  });

  test('стрелка вправо переводит фокус и выбор на следующую вкладку', async ({ page }) => {
    await page.goto('/');
    await page.getByRole('tab', { name: 'Как спрашивают обычно' }).focus();

    await page.keyboard.press('ArrowRight');

    await expect(page.getByRole('tab', { name: 'Как спрашиваю я' })).toHaveAttribute('aria-selected', 'true');
  });

  test('находка подсвечивает ровно свои строки кода', async ({ page }) => {
    await page.goto('/');
    await page.getByRole('tab', { name: 'Как спрашиваю я' }).click();

    await page.locator('#panel-pro .cmt[data-lines="3-5"]').click();

    const highlighted = await page.locator('.ln.hl').evaluateAll((lines) => lines.map((l) => l.getAttribute('data-n')));
    expect(highlighted).toEqual(['3', '4', '5']);
  });

  test('смена вкладки снимает подсветку', async ({ page }) => {
    await page.goto('/');
    await page.getByRole('tab', { name: 'Как спрашиваю я' }).click();
    await page.locator('#panel-pro .cmt[data-lines="1-2"]').click();

    await page.getByRole('tab', { name: 'Как спрашивают обычно' }).click();

    await expect(page.locator('.ln.hl')).toHaveCount(0);
  });

  test('кнопка «А на самом деле…» открывает третью вкладку', async ({ page }) => {
    await page.goto('/');
    await page.getByRole('tab', { name: 'Как спрашиваю я' }).click();

    await page.getByRole('button', { name: /А на самом деле/ }).click();

    await expect(page.locator('#panel-real')).toBeVisible();
  });
});

test.describe('окно брони', () => {
  const triggers: Array<[string, string]> = [
    ['start', 'Технический старт'],
    ['foundation', 'Фундамент: от идеи до репозитория'],
    ['launch', 'Подготовка к запуску'],
    ['subscription', 'Разработка по подписке'],
    ['teardown', 'Бесплатный разбор в ролике'],
  ];

  for (const [format, label] of triggers) {
    test(`кнопка формата «${label}» открывает окно с этим форматом`, async ({ page }) => {
      await page.goto('/');

      await page.locator(`main [data-book="${format}"]`).first().click();

      await expect(page.locator('#format')).toHaveValue(format);
    });
  }

  // Packages are booked as the technical start that opens them; launch preparation has its own price.
  const charges: Array<[string, string, string]> = [
    ['start', '€200', 'К оплате: €200 — созвон по задаче и репозиторий под неё в течение 5 рабочих дней.'],
    ['launch', '€500', 'К оплате: €500 — исправления пулл-реквестами в вашем репозитории.'],
    ['foundation', '€200', 'К оплате сейчас: €200 — технический старт, первый этап. Сумма засчитается в «Фундамент».'],
    ['subscription', '€200', 'К оплате сейчас: €200 — технический старт, первый этап. Сумма засчитается в «Разработку по подписке».'],
  ];
  for (const [format, price, text] of charges) {
    test(`формат ${format}: к оплате ${price} и за что`, async ({ page }) => {
      await page.goto('/');

      await page.locator(`main [data-book="${format}"]`).first().click();

      await expect(page.locator('#pay')).toContainText(text);
      await expect(page.locator('#book-submit')).toHaveText(`Оплатить ${price} →`);
    });
  }

  test('бесплатный разбор не просит оплату', async ({ page }) => {
    await page.goto('/');

    await page.locator('main [data-book="teardown"]').click();

    await expect(page.locator('#book-submit')).toHaveText('Отправить заявку →');
  });

  test('клик по затемнению вокруг окна закрывает его', async ({ page }) => {
    await page.goto('/');
    await page.locator('main [data-book="start"]').first().click();

    await page.mouse.click(5, 5);

    await expect(page.locator('#book')).not.toHaveAttribute('open');
  });
});

test.describe('лист ожидания Veritas (заглушка)', () => {
  test('отправка очищает форму и показывает сообщение', async ({ page }) => {
    await page.goto('/');
    const form = page.locator('#waitlist');
    await form.getByLabel('Ссылка на репозиторий').fill('https://github.com/example/repo');
    await form.getByLabel('Почта').fill('test@example.com');

    await form.getByRole('button', { name: 'В лист ожидания' }).click();

    await expect(form.getByLabel('Почта')).toHaveValue('');
    await expect(page.locator('#toast')).toHaveText(/лист ожидания/);
  });
});
