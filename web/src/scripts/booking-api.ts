/** The booking API as the browser sees it (api/src/ritis_api/http): no personal data comes back. */

export type BookingStatus =
  | 'awaiting_payment'
  | 'paid'
  | 'declined'
  | 'expired'
  | 'refunded'
  | 'needs_review';

export interface BookingView {
  id: string;
  status: BookingStatus;
  format: string;
  amount_minor: number;
  currency: string;
  checkout_url: string | null;
  can_retry_payment: boolean;
}

export interface BookingRequest {
  format: string;
  name: string;
  contact: string;
  about: string;
  links: string;
  consent: boolean;
  website: string; // honeypot: stays empty for people
}

export type Failure = 'invalid' | 'not_found' | 'conflict' | 'provider_down' | 'network' | 'server';

const FAILURE_BY_STATUS: ReadonlyMap<number, Failure> = new Map([
  [404, 'not_found'],
  [409, 'conflict'],
  [422, 'invalid'],
  [502, 'provider_down'],
]);

export class BookingApiError extends Error {
  constructor(readonly failure: Failure) {
    super(failure);
  }

  /** Anything other than an answer of the API, such as a malformed body, counts as our fault. */
  static failureOf(error: unknown): Failure {
    return error instanceof BookingApiError ? error.failure : 'server';
  }
}

/** What to tell a person about each failure. */
export const failureMessages: Record<Failure, string> = {
  invalid: 'Проверьте анкету: какое-то поле заполнено не так.',
  not_found: 'Бронь не найдена. Проверьте ссылку или оформите бронь заново.',
  conflict: 'Бронь как раз обновляется. Попробуйте ещё раз через пару секунд.',
  provider_down: 'Платёжный сервис сейчас не отвечает. Попробуйте через пару минут.',
  network: 'Нет связи с сервером. Проверьте интернет и попробуйте ещё раз.',
  server: 'Что-то пошло не так на нашей стороне. Попробуйте ещё раз чуть позже.',
};

export class BookingApi {
  constructor(private readonly base = '/api/bookings') {}

  create(request: BookingRequest, idempotencyKey: string): Promise<BookingView> {
    return this.send(this.base, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json', 'Idempotency-Key': idempotencyKey },
      body: JSON.stringify(request),
    });
  }

  status(id: string): Promise<BookingView> {
    return this.send(`${this.base}/${encodeURIComponent(id)}`, { method: 'GET' });
  }

  payAgain(id: string): Promise<BookingView> {
    return this.send(`${this.base}/${encodeURIComponent(id)}/payments`, { method: 'POST' });
  }

  private async send(url: string, init: RequestInit): Promise<BookingView> {
    let response: Response;
    try {
      response = await fetch(url, init);
    } catch {
      throw new BookingApiError('network');
    }
    if (response.ok) return (await response.json()) as BookingView;
    throw new BookingApiError(FAILURE_BY_STATUS.get(response.status) ?? 'server');
  }
}
