import type { Page } from '@playwright/test';
import { LOCALES } from '../../src/i18n/locales';
import { agree, answer, booking, ID, statusSequence } from './booking-mocks';
import { expect, test } from './fixtures';

const PAGES = ['/', '/booking/', '/offer/', '/refund/', '/privacy/', '/details/'];
/** Where each language lives; Russian, the default, has no prefix. */
const PREFIX: Record<string, string> = { ru: '', ka: '/ka', en: '/en' };
const CYRILLIC = /[А-Яа-яЁё]/;
const GEORGIAN = /[Ⴀ-ჿ]/;
/** Scripts a page of the language must not show, and the one it must (when it has its own). */
const SCRIPTS: Record<string, { foreign: RegExp; own?: RegExp }> = {
  ka: { foreign: CYRILLIC, own: GEORGIAN },
  en: { foreign: new RegExp(`${CYRILLIC.source}|${GEORGIAN.source}`) },
};

/**
 * Texts and attributes of the page that match the pattern and are in the page's own language:
 * an element marked with another lang (the switcher's "Русский") speaks that language.
 */
async function textsMatching(page: Page, pattern: RegExp): Promise<string[]> {
  return page.evaluate((source) => {
    const re = new RegExp(source);
    const lang = document.documentElement.lang;
    const own = (el: Element) => (el.closest('[lang]')?.getAttribute('lang') ?? lang) === lang;
    const found: string[] = [];
    const walker = document.createTreeWalker(document.body, NodeFilter.SHOW_TEXT);
    for (let node = walker.nextNode(); node; node = walker.nextNode()) {
      const parent = node.parentElement;
      if (parent && !parent.closest('script, style') && own(parent) && re.test(node.textContent ?? '')) {
        found.push((node.textContent ?? '').trim());
      }
    }
    for (const el of document.querySelectorAll('[aria-label], [placeholder], [alt], [title], meta[name="description"]')) {
      if (!own(el)) continue;
      for (const name of ['aria-label', 'placeholder', 'alt', 'title', 'content']) {
        const value = el.getAttribute(name);
        if (value && re.test(value)) found.push(`${name}="${value}"`);
      }
    }
    if (re.test(document.title)) found.push(`<title>${document.title}`);
    return found;
  }, pattern.source);
}

test('языки сайта проверены все', () => {
  expect(Object.keys(PREFIX).sort()).toEqual([...LOCALES].sort());
});

test('проверка чужого текста видит русский на русской странице', async ({ page }) => {
  await page.goto('/');

  expect((await textsMatching(page, CYRILLIC)).length).toBeGreaterThan(50);
});

for (const [locale, { foreign, own }] of Object.entries(SCRIPTS)) {
  const prefix = PREFIX[locale];
  test.describe(`страницы [${locale}]`, () => {
    for (const path of PAGES) {
      test(`${prefix}${path}: объявляет свой язык и говорит только на нём`, async ({ page }) => {
        await page.goto(`${prefix}${path}`);

        await expect(page.locator('html')).toHaveAttribute('lang', locale);
        expect(await textsMatching(page, foreign)).toEqual([]);
        if (own) expect((await textsMatching(page, own)).length).toBeGreaterThan(5);
      });
    }

    test('окно брони на языке страницы для каждого формата', async ({ page }) => {
      await page.goto(`${prefix}/`);
      await page.locator('main [data-book="start"]').first().click();

      const found: string[] = [];
      for (const format of ['start', 'foundation', 'launch', 'subscription', 'teardown']) {
        await page.locator('#format').selectOption(format);
        found.push(...(await textsMatching(page, foreign)));
      }

      expect(found).toEqual([]);
    });
  });
}

test.describe('переключатель языка', () => {
  test('ведёт на ту же страницу на другом языке и сохраняет её параметры', async ({ page }) => {
    await page.goto(`/booking/?id=${ID}`);

    await page.locator('header').getByRole('link', { name: 'English' }).click();
    await expect(page).toHaveURL(`/en/booking/?id=${ID}`);
    await expect(page.locator('html')).toHaveAttribute('lang', 'en');

    await page.locator('header').getByRole('link', { name: 'Русский' }).click();
    await expect(page).toHaveURL(`/booking/?id=${ID}`);
  });

  test('сохраняет раздел страницы', async ({ page }) => {
    await page.goto('/offer/#refund');

    await page.locator('header').getByRole('link', { name: 'English' }).click();

    await expect(page).toHaveURL('/en/offer/#refund');
  });

  test('отмечает текущий язык', async ({ page }) => {
    await page.goto('/en/privacy/');

    const current = await page
      .locator('header [data-lang-switch]')
      .evaluateAll((all) => all.map((a) => `${a.textContent}:${a.getAttribute('aria-current')}`));

    expect(current).toEqual(['RU:null', 'KA:null', 'EN:page']);
  });
});

test('каждая страница называет поисковикам себя на всех языках', async ({ page, request }) => {
  await page.goto('/en/refund/');

  const alternates = await page
    .locator('link[rel="alternate"]')
    .evaluateAll((all) => all.map((l) => [l.getAttribute('hreflang'), l.getAttribute('href')]));

  expect(alternates).toEqual([
    ['ru', 'https://ritis.dev/refund/'],
    ['ka', 'https://ritis.dev/ka/refund/'],
    ['en', 'https://ritis.dev/en/refund/'],
    ['x-default', 'https://ritis.dev/refund/'],
  ]);
  for (const [, href] of alternates) expect((await request.get(new URL(href ?? '').pathname)).status()).toBe(200);
});

test.describe('бронь на английском', () => {
  async function openEnglishDialog(page: Page, format: string): Promise<void> {
    await page.goto('/en/');
    await page.locator(`main [data-book="${format}"]`).first().click();
    await page.locator('#book [name="name"]').fill('Test');
    await page.locator('#book [name="contact"]').fill('test@example.com');
  }

  test('окно говорит, сколько и за что платить, и объясняет сбой на языке страницы', async ({ page }) => {
    await page.route('**/api/bookings', (route) =>
      route.fulfill({ status: 502, json: { detail: 'payment_provider_unavailable' } }),
    );
    await openEnglishDialog(page, 'launch');
    await agree(page);

    await expect(page.locator('#pay')).toHaveText(
      'To pay: ₾1,500 — fixes as pull requests in your repository. If the project needs more, I will offer another format or return the money before any work starts.',
    );
    await expect(page.locator('#book-submit')).toHaveText('Pay ₾1,500 →');
    await page.locator('#book-submit').click();

    await expect(page.locator('#book-error')).toHaveText('The payment service is not responding. Try again in a couple of minutes.');
  });

  test('без открытой оплаты ведёт на страницу брони того же языка', async ({ page }) => {
    const languages: unknown[] = [];
    await page.route('**/api/bookings', (route) => {
      languages.push(route.request().postDataJSON().language);
      return route.fulfill({ status: 201, json: booking('paid') });
    });
    await statusSequence(page, [answer('paid')]);
    await openEnglishDialog(page, 'start');
    await agree(page);

    await page.locator('#book-submit').click();

    await expect(page).toHaveURL(`/en/booking/?id=${ID}`);
    await expect(page.locator('#booking-title')).toHaveText('Paid');
    // The API needs it too: the checkout and the way back from it speak the same language.
    expect(languages).toEqual(['en']);
  });

  test('бесплатный разбор отвечает на языке страницы', async ({ page }) => {
    await openEnglishDialog(page, 'teardown');

    await page.locator('#book-submit').click();

    await expect(page.locator('#toast')).toHaveText('Demo: the teardown request would go to my Telegram.');
  });
});
