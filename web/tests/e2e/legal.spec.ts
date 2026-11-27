import { expect, test } from './fixtures';

const PAGES: Array<[string, string, string]> = [
  ['Оферта', '/offer/', 'Публичная оферта'],
  ['Возврат', '/refund/', 'Условия возврата'],
  ['Конфиденциальность', '/privacy/', 'Политика конфиденциальности'],
  ['Реквизиты', '/details/', 'Реквизиты и контакты'],
];

test.describe('юридические страницы', () => {
  for (const [link, path, title] of PAGES) {
    test(`ссылка «${link}» в подвале ведёт на страницу «${title}»`, async ({ page }) => {
      await page.goto('/');

      await page.locator('footer').getByRole('link', { name: link }).click();

      await expect(page).toHaveURL(path);
      await expect(page.getByRole('heading', { level: 1 })).toHaveText(title);
    });
  }

  test('согласие в окне брони ведёт на оферту и политику', async ({ page }) => {
    await page.goto('/');
    await page.locator('main [data-book="start"]').first().click();

    const consent = page.locator('#book');

    await expect(consent.getByRole('link', { name: 'оферту' })).toHaveAttribute('href', '/offer/');
    await expect(consent.getByRole('link', { name: 'политикой конфиденциальности' })).toHaveAttribute('href', '/privacy/');
  });

  test('внутренние ссылки ведут на существующие страницы и разделы', async ({ page, request }) => {
    const links = new Set<string>();
    for (const path of ['/', ...PAGES.map(([, p]) => p)]) {
      await page.goto(path);
      await expect(page.locator('a[href="#"]'), path).toHaveCount(0);
      const hrefs = await page.locator('a[href^="/"]').evaluateAll((all) => all.map((a) => a.getAttribute('href') ?? ''));
      for (const href of hrefs) links.add(href);
    }

    for (const link of links) {
      const [path, section] = link.split('#');
      expect((await request.get(path)).status(), link).toBe(200);
      if (section) {
        await page.goto(path);
        await expect(page.locator(`#${section}`), link).toHaveCount(1);
      }
    }
  });

  test('условия возврата в оферте и на своей странице одни и те же', async ({ page }) => {
    await page.goto('/refund/');
    const standalone = await page.locator('ol.refund').innerText();

    await page.goto('/offer/');

    await expect(page.locator('#refund + ol.refund')).toHaveText(standalone);
  });

  test('в оферте у каждого формата своя цена', async ({ page }) => {
    await page.goto('/offer/');

    // Raw textContent: toHaveText would normalise a non-breaking space into a plain one.
    const formats = await page.locator('dl.formats dt').allTextContents();

    const nbsp = String.fromCharCode(0xa0);
    expect(formats).toEqual([
      'Технический старт — €200',
      'Подготовка к запуску — €500',
      `Фундамент — от €2${nbsp}000`,
      `Разработка по подписке — от €1${nbsp}000/мес`,
    ]);
  });
});
