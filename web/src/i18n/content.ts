import { localeOfUrl, type Locale } from './locales';
import ru from './ru';

/** Everything a page says, in one language. Russian sets the shape; the others must match it. */
export type Content = typeof ru;

const CONTENT: Record<Locale, Content> = { ru };

export const contentIn = (locale: Locale): Content => CONTENT[locale];

/** What the page being rendered says: pass it Astro.url. */
export const pageContent = (url: URL): Content => contentIn(localeOfUrl(url));
