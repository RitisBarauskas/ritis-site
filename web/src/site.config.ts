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

export const prices = {
  session: euros(catalog.call.amount_minor),
  foundation: `от ${euros(catalog.packages.foundation.from_minor)}`,
  checkup: `от ${euros(catalog.packages.checkup.from_minor)}`,
  support: `от ${euros(catalog.packages.support.from_minor)}/мес`,
} as const;

export const links = {
  github: 'https://github.com/RitisBarauskas',
  linkedin: 'https://www.linkedin.com/in/ritis-barauskas/',
  youtube: 'https://www.youtube.com/@ritisdoit',
  telegram: 'https://t.me/ritisdoit',
  email: 'hello@ritis.dev',
} as const;

export type BookingFormat = 'session' | 'foundation' | 'checkup' | 'support' | 'teardown';

/** Package names in the accusative case: "сумма засчитается в …". */
export const packageAccusative: Partial<Record<BookingFormat, string>> = {
  foundation: '«Фундамент»',
  checkup: '«Проверку перед запуском»',
  support: '«Техлид на связи»',
};

export const demoBadge = 'демо · ritis.dev';
