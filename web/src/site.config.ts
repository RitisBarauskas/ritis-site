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

export type BookingFormat = 'start' | 'launch' | 'foundation' | 'subscription' | 'teardown';
export type PaidFormat = Exclude<BookingFormat, 'teardown'>;

const formats: Record<PaidFormat, { price_minor?: number; starts_with?: string; from_minor?: number }> =
  catalog.formats;

/** What booking a format charges: its own price, or the price of the format it starts with. */
function bookedAt(format: PaidFormat): string {
  const own = formats[format];
  const priced = own.starts_with ? formats[own.starts_with as PaidFormat] : own;
  if (!priced?.price_minor) throw new Error(`catalog: ${format} has no booking price`);
  return euros(priced.price_minor);
}

function from(format: PaidFormat): string {
  const amount = formats[format].from_minor;
  if (!amount) throw new Error(`catalog: ${format} has no package price`);
  return `от ${euros(amount)}`;
}

/** Prices as the offers show them. */
export const prices = {
  start: bookedAt('start'),
  launch: bookedAt('launch'),
  foundation: from('foundation'),
  subscription: `${from('subscription')}/мес`,
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

export const payments = {
  // Flitt's test merchant: no real money moves. Switched off with the real merchant account.
  testMode: true,
} as const;

export const demoBadge = 'демо · ritis.dev';
