// Prices live in shared/catalog.json, the same file the API charges by; they are not final.
import catalog from '../../shared/catalog.json';

const NBSP = String.fromCharCode(0xa0); // non-breaking space

/** Whole euros with non-breaking thousands separators, as the page shows them. */
function euros(amountMinor: number): string {
  if (catalog.currency !== 'EUR' || amountMinor % 100 !== 0) {
    throw new Error(`catalog price ${amountMinor} ${catalog.currency} is not whole euros`);
  }
  return '€' + String(amountMinor / 100).replace(/\B(?=(\d{3})+(?!\d))/g, NBSP);
}

type BookingFormat = 'start' | 'launch' | 'foundation' | 'subscription' | 'teardown';
export type PaidFormat = Exclude<BookingFormat, 'teardown'>;

type CatalogFormat = { price_minor?: number; starts_with?: string; from_minor?: number; per?: string };
const formats: Record<PaidFormat, CatalogFormat> = catalog.formats;
const PER: Record<string, string> = { month: '/мес' };

/** What booking a format charges: its own price, or the price of the format it starts with. */
function bookedAt(format: PaidFormat): string {
  const own = formats[format];
  const priced = own.starts_with ? formats[own.starts_with as PaidFormat] : own;
  if (!priced?.price_minor) throw new Error(`catalog: ${format} has no booking price`);
  return euros(priced.price_minor);
}

function from(format: PaidFormat): string {
  const { from_minor: amount, per } = formats[format];
  if (!amount) throw new Error(`catalog: ${format} has no package price`);
  if (per && !PER[per]) throw new Error(`catalog: ${format} is priced per ${per}, which the site cannot show`);
  return `от ${euros(amount)}${per ? PER[per] : ''}`;
}

/** Prices as the offers show them. */
export const prices = {
  start: bookedAt('start'),
  launch: bookedAt('launch'),
  foundation: from('foundation'),
  subscription: from('subscription'),
} as const;

/** What the booking dialog charges now for each paid format. */
export const bookingPrice: Record<PaidFormat, string> = {
  start: bookedAt('start'),
  launch: bookedAt('launch'),
  foundation: bookedAt('foundation'),
  subscription: bookedAt('subscription'),
};

export const links = {
  github: 'https://github.com/RitisBarauskas',
  linkedin: 'https://www.linkedin.com/in/ritis-barauskas/',
  youtube: 'https://www.youtube.com/@ritisdoit',
  telegram: 'https://t.me/ritisdoit',
  email: 'hello@ritis.dev',
} as const;

/** The party to the offer: the offer, the details page and the footer name it the same way. */
export const merchant = {
  name: 'Индивидуальный предприниматель Ритис Бараускас',
  nameLatin: 'Individual Entrepreneur Ritis Barauskas',
  registryId: '304748094',
  registry: 'Национальное агентство публичного реестра Грузии',
  country: 'Грузия',
} as const;

const MONTHS = ['января', 'февраля', 'марта', 'апреля', 'мая', 'июня', 'июля', 'августа', 'сентября', 'октября', 'ноября', 'декабря'];

/** The offer in force, from the catalog the API stamps on every booking; the refund terms share it. */
export const offerRevision = (() => {
  const [year, month, day] = catalog.offer_revision.split('-').map(Number);
  return `${day} ${MONTHS[month - 1]} ${year} года`;
})();

export const payments = {
  // Flitt's test merchant: no real money moves. Switched off with the real merchant account.
  testMode: true,
} as const;

export const demoBadge = 'демо · ritis.dev';
