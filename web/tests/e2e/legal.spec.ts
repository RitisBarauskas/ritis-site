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

    const consent = page.locator('#consent-row');

    await expect(consent.getByRole('link', { name: 'офертой' })).toHaveAttribute('href', '/offer/');
    await expect(consent.getByRole('link', { name: 'политикой конфиденциальности' })).toHaveAttribute('href', '/privacy/');
  });

  test('на страницах нет ссылок в никуда', async ({ page }) => {
    for (const path of ['/', ...PAGES.map(([, p]) => p)]) {
      await page.goto(path);
      await expect(page.locator('a[href="#"]'), path).toHaveCount(0);
    }
  });

  test('условия возврата в оферте и на своей странице одни и те же', async ({ page }) => {
    await page.goto('/refund/');
    const standalone = await page.locator('ol.refund').innerText();

    await page.goto('/offer/');

    await expect(page.locator('#refund + ol.refund')).toHaveText(standalone);
  });

  test('цены в оферте те же, что в блоке форматов', async ({ page }) => {
    await page.goto('/');
    const offered = await page.locator('#help .price b').allTextContents();

    await page.goto('/offer/');
    const terms = await page.locator('dl dt').allTextContents();

    for (const price of offered) expect(terms.join(' ')).toContain(price);
  });
});
