// Prices live in shared/catalog.json, the same file the API charges by; they are not final.
import catalog from '../../shared/catalog.json';
import type { Locale } from './i18n/locales';

const NBSP = String.fromCharCode(0xa0); // non-breaking space

type BookingFormat = 'start' | 'launch' | 'foundation' | 'subscription' | 'teardown';
export type PaidFormat = Exclude<BookingFormat, 'teardown'>;

type CatalogFormat = { price_minor?: number; starts_with?: string; from_minor?: number; per?: string };
const formats: Record<PaidFormat, CatalogFormat> = catalog.formats;

/** How a language writes a price: where the sign goes, "from", "a month", thousands separator. */
interface MoneyStyle {
  amount: (lari: string) => string;
  from: (price: string) => string;
  month: string;
  group: string;
}

/**
 * Every language writes prices in lari: a price offered in Georgia is stated in lari only
 * (Organic Law on the National Bank of Georgia, art. 34(2¹)).
 */
const MONEY: Record<Locale, MoneyStyle> = {
  ru: { amount: (n) => `${n}${NBSP}₾`, from: (p) => `от ${p}`, month: '/мес', group: NBSP },
};

function lari(locale: Locale, amountMinor: number): string {
  if (catalog.currency !== 'GEL' || amountMinor % 100 !== 0) {
    throw new Error(`catalog price ${amountMinor} ${catalog.currency} is not whole lari`);
  }
  const money = MONEY[locale];
  return money.amount(String(amountMinor / 100).replace(/\B(?=(\d{3})+(?!\d))/g, money.group));
}

/** What booking a format charges: its own price, or the price of the format it starts with. */
function bookedAt(locale: Locale, format: PaidFormat): string {
  const own = formats[format];
  const priced = own.starts_with ? formats[own.starts_with as PaidFormat] : own;
  if (!priced?.price_minor) throw new Error(`catalog: ${format} has no booking price`);
  return lari(locale, priced.price_minor);
}

function from(locale: Locale, format: PaidFormat): string {
  const { from_minor: amount, per } = formats[format];
  if (!amount) throw new Error(`catalog: ${format} has no package price`);
  if (per && per !== 'month') throw new Error(`catalog: ${format} is priced per ${per}, which the site cannot show`);
  return MONEY[locale].from(lari(locale, amount)) + (per ? MONEY[locale].month : '');
}

export type Prices = Record<PaidFormat, string>;

/** Prices as the offers show them. */
export const pricesIn = (locale: Locale): Prices => ({
  start: bookedAt(locale, 'start'),
  launch: bookedAt(locale, 'launch'),
  foundation: from(locale, 'foundation'),
  subscription: from(locale, 'subscription'),
});

/** What the booking dialog charges now for each paid format. */
export const bookingPricesIn = (locale: Locale): Prices => ({
  start: bookedAt(locale, 'start'),
  launch: bookedAt(locale, 'launch'),
  foundation: bookedAt(locale, 'foundation'),
  subscription: bookedAt(locale, 'subscription'),
});

const MONTHS: Record<Locale, string[]> = {
  ru: ['января', 'февраля', 'марта', 'апреля', 'мая', 'июня', 'июля', 'августа', 'сентября', 'октября', 'ноября', 'декабря'],
};

/** A date as the legal pages write it. */
export function legalDate(locale: Locale, iso: string): string {
  const [year, month, day] = iso.split('-').map(Number);
  const name = MONTHS[locale][month - 1];
  return `${day} ${name} ${year} года`;
}

/** The offer in force, from the catalog the API stamps on every booking; the refund terms share it. */
export const offerRevision = catalog.offer_revision;

export const links = {
  github: 'https://github.com/RitisBarauskas',
  linkedin: 'https://www.linkedin.com/in/ritis-barauskas/',
  youtube: 'https://www.youtube.com/@ritisdoit',
  telegram: 'https://t.me/ritisdoit',
  email: 'hello@ritis.dev',
} as const;

/** The party to the offer; its name in each language is in the content of that language. */
export const merchant = {
  nameLatin: 'Individual Entrepreneur Ritis Barauskas',
  registryId: '304748094',
} as const;

export const payments = {
  // Flitt's test merchant: no real money moves. Switched off with the real merchant account.
  testMode: true,
} as const;
