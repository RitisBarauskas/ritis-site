/** The site's languages. Russian is the default and lives at the root; the others under /ka/, /en/. */
export const LOCALES = ['ru', 'en'] as const;
export type Locale = (typeof LOCALES)[number];
export const DEFAULT_LOCALE: Locale = 'ru';

/** How each language names itself, for the switcher. */
export const LANGUAGE_NAMES: Record<Locale, string> = { ru: 'Русский', en: 'English' };
export const LANGUAGE_CODES: Record<Locale, string> = { ru: 'RU', en: 'EN' };

export const isLocale = (value: unknown): value is Locale => LOCALES.includes(value as Locale);

const PREFIXED = LOCALES.filter((locale) => locale !== DEFAULT_LOCALE);

/** The language of a site path: its first segment, or the default for a path without one. */
export function localeOfPath(pathname: string): Locale {
  const first = pathname.split('/')[1];
  return PREFIXED.find((locale) => locale === first) ?? DEFAULT_LOCALE;
}

/** The language of the page being rendered: pass it Astro.url. */
export const localeOfUrl = (url: URL): Locale => localeOfPath(url.pathname);

/** For getStaticPaths of a page that exists in every language: the default one has no prefix. */
export const localePaths = () =>
  LOCALES.map((locale) => ({ params: { locale: locale === DEFAULT_LOCALE ? undefined : locale } }));

/** A site path in a language: "/offer/" becomes "/en/offer/". */
export const localized = (locale: Locale, path: string): string =>
  locale === DEFAULT_LOCALE ? path : `/${locale}${path}`;

/** The same path without its language prefix, to switch it to another language. */
export function withoutLocale(pathname: string): string {
  if (localeOfPath(pathname) === DEFAULT_LOCALE) return pathname;
  return pathname.replace(/^\/[^/]+/, '') || '/';
}
