import { createHash } from 'node:crypto';
import { LOCALES } from '../../src/i18n/locales';
import { expect, test } from './fixtures';

// The offer as a customer accepts it, in each language: its page (with the refund terms and
// prices) and the two checkboxes of the booking dialog. Changing any of it makes a new revision
// of the offer: set offer_revision in shared/catalog.json to the publication date, then update
// the hash of every language whose text changed.
const OFFER_TEXT_SHA256: Record<string, string> = {
  ru: 'a160ea798e5d31860356d57a55e8606ed838260bef66bbf640eba6f620c2c1e2',
  en: '7c8be7d8a06b46e27a2957afff151feea583b3a26557a50cb0048238b12c74c8',
};

const NBSP = String.fromCharCode(0xa0);

/** Each language's legal pages, as its footer names them and as their headings read. */
const SITES: Record<string, { home: string; pages: Array<[string, string, string]>; offerPrices: string[] }> = {
  ru: {
    home: '/',
    pages: [
      ['Оферта', '/offer/', 'Публичная оферта'],
      ['Возврат', '/refund/', 'Условия возврата'],
      ['Конфиденциальность', '/privacy/', 'Политика конфиденциальности'],
      ['Реквизиты', '/details/', 'Реквизиты и контакты'],
    ],
    offerPrices: [
      `Технический старт — 600${NBSP}₾`,
      `Подготовка к запуску — 1${NBSP}500${NBSP}₾`,
      `Фундамент — от 6${NBSP}000${NBSP}₾`,
      `Разработка по подписке — от 3${NBSP}000${NBSP}₾/мес`,
    ],
  },
  en: {
    home: '/en/',
    pages: [
      ['Public offer', '/en/offer/', 'Public offer'],
      ['Refunds', '/en/refund/', 'Refund terms'],
      ['Privacy', '/en/privacy/', 'Privacy policy'],
      ['Business details', '/en/details/', 'Business details and contacts'],
    ],
    offerPrices: [
      'Technical start — ₾600',
      'Launch preparation — ₾1,500',
      'Foundation — from ₾6,000',
      'Development subscription — from ₾3,000/month',
    ],
  },
};

const offerOf = (locale: string) => SITES[locale].pages[0][1];
const refundOf = (locale: string) => SITES[locale].pages[1][1];

test('юридические страницы проверены на каждом языке сайта', () => {
  expect(Object.keys(SITES).sort()).toEqual([...LOCALES].sort());
  expect(Object.keys(OFFER_TEXT_SHA256).sort()).toEqual([...LOCALES].sort());
});

for (const locale of Object.keys(SITES)) {
  const { home, pages, offerPrices } = SITES[locale];

  test.describe(`юридические страницы [${locale}]`, () => {
    for (const [link, path, title] of pages) {
      test(`ссылка «${link}» в подвале ведёт на страницу «${title}»`, async ({ page }) => {
        await page.goto(home);

        await page.locator('footer').getByRole('link', { name: link, exact: true }).click();

        await expect(page).toHaveURL(path);
        await expect(page.getByRole('heading', { level: 1 })).toHaveText(title);
      });
    }

    test('согласие в окне брони ведёт на оферту, политику и условия возврата этого языка', async ({ page }) => {
      await page.goto(home);
      await page.locator('main [data-book="start"]').first().click();

      const links = await page.locator('#book .paid-only a').evaluateAll((all) => all.map((a) => a.getAttribute('href')));

      expect(links).toEqual([offerOf(locale), pages[2][1], refundOf(locale)]);
    });

    test('условия возврата в оферте и на своей странице одни и те же', async ({ page }) => {
      await page.goto(refundOf(locale));
      const standalone = await page.locator('ol.refund').innerText();

      await page.goto(offerOf(locale));

      await expect(page.locator('#refund + ol.refund')).toHaveText(standalone);
    });

    test('текст оферты меняется только вместе с датой редакции', async ({ page }) => {
      const text = (s: string | null) => (s ?? '').replace(/\s+/g, ' ').trim();
      await page.goto(offerOf(locale));
      const offer = text(await page.locator('main').textContent());
      await page.goto(home);
      const checkboxes = (await page.locator('#book .paid-only').allTextContents()).map(text);

      const hash = createHash('sha256').update([offer, ...checkboxes].join('\n')).digest('hex');

      expect(hash).toBe(OFFER_TEXT_SHA256[locale]);
    });

    test('в оферте у каждого формата своя цена', async ({ page }) => {
      await page.goto(offerOf(locale));

      // Raw textContent: toHaveText would normalise a non-breaking space into a plain one.
      const formats = await page.locator('dl.formats dt').allTextContents();

      expect(formats).toEqual(offerPrices);
    });
  });
}

test('внутренние ссылки ведут на существующие страницы и разделы и не уводят на другой язык', async ({ page, request }) => {
  const links = new Set<string>();
  const strays: string[] = [];
  for (const [locale, { home, pages }] of Object.entries(SITES)) {
    for (const path of [home, ...pages.map(([, p]) => p)]) {
      await page.goto(path);
      await expect(page.locator('a[href="#"]'), path).toHaveCount(0);
      // The language switcher is the one way to another language.
      const hrefs = await page
        .locator('a[href^="/"]:not([data-lang-switch])')
        .evaluateAll((all) => all.map((a) => a.getAttribute('href') ?? ''));
      for (const href of hrefs) {
        links.add(href);
        const prefixed = /^\/([a-z]{2})(?=\/|#|$)/.exec(href)?.[1];
        if ((prefixed ?? 'ru') !== locale) strays.push(`${path} → ${href}`);
      }
    }
  }

  expect(strays).toEqual([]);
  for (const link of links) {
    const [path, section] = link.split('#');
    expect((await request.get(path)).status(), link).toBe(200);
    if (section) {
      await page.goto(path);
      await expect(page.locator(`#${section}`), link).toHaveCount(1);
    }
  }
});
