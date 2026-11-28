import type { Locale } from '../i18n/locales';
import EnDetails from './en/Details.astro';
import EnOffer from './en/Offer.astro';
import EnPrivacy from './en/Privacy.astro';
import EnRefund from './en/Refund.astro';
import KaDetails from './ka/Details.astro';
import KaOffer from './ka/Offer.astro';
import KaPrivacy from './ka/Privacy.astro';
import KaRefund from './ka/Refund.astro';
import RuDetails from './ru/Details.astro';
import RuOffer from './ru/Offer.astro';
import RuPrivacy from './ru/Privacy.astro';
import RuRefund from './ru/Refund.astro';

const ru = { Offer: RuOffer, Refund: RuRefund, Privacy: RuPrivacy, Details: RuDetails };

/**
 * The legal documents of each language, each written whole: a contract is read as it stands,
 * so its text is not assembled from phrases shared between languages.
 */
export const LEGAL: Record<Locale, typeof ru> = {
  ru,
  ka: { Offer: KaOffer, Refund: KaRefund, Privacy: KaPrivacy, Details: KaDetails },
  en: { Offer: EnOffer, Refund: EnRefund, Privacy: EnPrivacy, Details: EnDetails },
};
