// Prices and currency are not final: every price on the page is taken from here.
export const prices = {
  session: '€200',
  foundation: 'от €2 000',
  checkup: 'от €500',
  support: 'от €1 000/мес',
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
