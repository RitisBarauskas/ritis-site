import type { Page } from '@playwright/test';
import { expect, test } from './fixtures';

const FAVICON = /\/favicon\.ico$/;
const NBSP = String.fromCharCode(0xa0);
/** The home page of each language: its layout differs with the length of its texts. */
const HOMES: Record<string, string> = { ru: '/', ka: '/ka/', en: '/en/' };

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
  for (const [locale, home] of Object.entries(HOMES)) {
    test(`[${locale}] загружается без ошибок в консоли`, async ({ page }) => {
      const errors = await collectErrors(page);

      await page.goto(home, { waitUntil: 'networkidle' });

      expect(errors).toEqual([]);
    });

    for (const width of [390, 820, 1024, 1440]) {
      test(`[${locale}] не даёт горизонтальной прокрутки на ширине ${width} ни на одной вкладке демо`, async ({ page }) => {
        await page.setViewportSize({ width, height: 900 });
        await page.goto(home);

        // Each demo tab has different content, so each one can push the layout wider.
        const overflow: number[] = [];
        for (const tab of await page.getByRole('tab').all()) {
          await tab.click();
          overflow.push(await page.evaluate(() => document.documentElement.scrollWidth - window.innerWidth));
        }

        expect(overflow).toEqual([0, 0, 0]);
      });

      if (width === 390) {
        test(`[${locale}] на ширине 390 текст не вылезает за свои блоки`, async ({ page }) => {
          await page.setViewportSize({ width, height: 900 });
          await page.goto(home);

          const clipped = await page.evaluate(() => {
            const found: string[] = [];
            // Code scrolls inside its own box; an open question's "+" turns by 45° and pokes out by design.
            for (const el of document.querySelectorAll('header *, main *, footer *')) {
              if (el.closest('pre, details') || el.matches('.faq') || getComputedStyle(el).overflowX !== 'visible') continue;
              if (el.clientWidth > 0 && el.scrollWidth > el.clientWidth + 1) found.push(el.outerHTML.slice(0, 80));
            }
            // The questions themselves: no line of one may run past its row.
            for (const question of document.querySelectorAll('#faq summary')) {
              const range = document.createRange();
              range.selectNodeContents(question);
              const edge = question.getBoundingClientRect().right;
              if ([...range.getClientRects()].some((line) => line.right > edge + 1)) found.push(question.outerHTML.slice(0, 80));
            }
            return found;
          });

          expect(clipped).toEqual([]);
        });
      }

      test(`[${locale}] шапка на ширине ${width} умещается в одну строку`, async ({ page }) => {
        await page.setViewportSize({ width, height: 900 });
        await page.goto(home);

        // Wrapped links or buttons stand taller than the bar or stick out of it.
        const clipped = await page.locator('header.nav .nav-in > *:visible, header.nav .nav-in > * > *:visible').evaluateAll((all) => {
          const bar = document.querySelector('header.nav .nav-in')!.getBoundingClientRect();
          return all
            .filter((el) => {
              const box = el.getBoundingClientRect();
              return box.top < bar.top || box.bottom > bar.bottom || box.left < bar.left - 1 || box.right > bar.right + 1;
            })
            .map((el) => el.outerHTML.slice(0, 60));
        });

        expect(clipped).toEqual([]);
      });
    }
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

  // Raw textContent: toHaveText would normalise a non-breaking space into a plain one.
  const PRICES: Record<string, string[]> = {
    ru: [`600${NBSP}₾`, `от 6${NBSP}000${NBSP}₾`, `1${NBSP}500${NBSP}₾`, `от 3${NBSP}000${NBSP}₾/мес`],
    ka: [`600${NBSP}₾`, `6${NBSP}000${NBSP}₾-დან`, `1${NBSP}500${NBSP}₾`, `3${NBSP}000${NBSP}₾-დან${NBSP}თვეში`],
    en: ['₾600', 'from ₾6,000', '₾1,500', 'from ₾3,000/month'],
  };
  for (const [locale, expected] of Object.entries(PRICES)) {
    test(`[${locale}] цены из каталога, в записи этого языка`, async ({ page }) => {
      await page.goto(HOMES[locale]);

      expect(await page.locator('#help .price b').allTextContents()).toEqual(expected);
    });
  }
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
    ['start', '600 ₾', 'К оплате: 600 ₾ — созвон по задаче, а через 5 рабочих дней после него — репозиторий под неё.'],
    ['launch', '1 500 ₾', 'К оплате: 1 500 ₾ — исправления пулл-реквестами в вашем репозитории.'],
    ['foundation', '600 ₾', 'К оплате сейчас: 600 ₾ — технический старт, первый этап. Сумма засчитается в «Фундамент», если вы его закажете.'],
    ['subscription', '600 ₾', 'К оплате сейчас: 600 ₾ — технический старт, первый этап. Сумма засчитается в первый месяц разработки по подписке, если вы её закажете.'],
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

  for (const [locale, home] of Object.entries(HOMES)) {
    test(`[${locale}] на ширине 390 содержимое окна не вылезает за его края`, async ({ page }) => {
      await page.setViewportSize({ width: 390, height: 844 });
      await page.goto(home);
      await page.locator('main [data-book="foundation"]').first().click();

      // The honeypot is squeezed to 1px on purpose.
      const overflowing = await page.locator('#book .dlg-body *').evaluateAll((all) =>
        all
          .filter((el) => !el.closest('.hp') && el.scrollWidth > el.clientWidth + 1)
          .map((el) => el.outerHTML.slice(0, 80)));

      expect(overflowing).toEqual([]);
    });
  }

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
