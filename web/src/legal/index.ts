import type { Locale } from '../i18n/locales';
import Details from './ru/Details.astro';
import Offer from './ru/Offer.astro';
import Privacy from './ru/Privacy.astro';
import Refund from './ru/Refund.astro';

const ru = { Offer, Refund, Privacy, Details };

/**
 * The legal documents of each language, each written whole: a contract is read as it stands,
 * so its text is not assembled from phrases shared between languages.
 */
export const LEGAL: Record<Locale, typeof ru> = { ru };
