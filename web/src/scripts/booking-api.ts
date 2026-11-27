/** The booking API as the browser sees it (api/src/ritis_api/http): no personal data comes back. */

const STATUSES = ['awaiting_payment', 'paid', 'declined', 'expired', 'refunded', 'needs_review'] as const;

export type BookingStatus = (typeof STATUSES)[number];

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
  start_immediately: boolean;
  website: string; // honeypot: stays empty for people
}

export type Failure =
  | 'invalid'
  | 'not_found'
  | 'conflict'
  | 'provider_down'
  | 'timeout'
  | 'network'
  | 'server';

// The API names each failure in `detail`; a proxy or a host in front of it answers with the
// same HTTP statuses, so the status alone says little.
const FAILURE_BY_DETAIL: ReadonlyMap<string, Failure> = new Map([
  ['booking_not_found', 'not_found'],
  ['booking_conflict', 'conflict'],
  ['booking_busy', 'conflict'],
  ['payment_provider_unavailable', 'provider_down'],
]);

const TIMEOUT_MS = 20_000;

export class BookingApiError extends Error {
  constructor(readonly failure: Failure) {
    super(failure);
  }

  /** An error that did not come from talking to the API is a bug of ours, and reads so. */
  static failureOf(error: unknown): Failure {
    return error instanceof BookingApiError ? error.failure : 'server';
  }
}

export class BookingApi {
  constructor(private readonly base = '/api/bookings') {}

  /** `cancel` aborts the request; the booking may still be created, and a repeat finds it. */
  create(request: BookingRequest, idempotencyKey: string, cancel?: AbortSignal): Promise<BookingView> {
    return this.send(
      this.base,
      {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', 'Idempotency-Key': idempotencyKey },
        body: JSON.stringify(request),
      },
      cancel,
    );
  }

  status(id: string): Promise<BookingView> {
    return this.send(`${this.base}/${encodeURIComponent(id)}`, { method: 'GET' });
  }

  payAgain(id: string): Promise<BookingView> {
    return this.send(`${this.base}/${encodeURIComponent(id)}/payments`, { method: 'POST' });
  }

  private async send(url: string, init: RequestInit, cancel?: AbortSignal): Promise<BookingView> {
    // One controller for both reasons to stop: AbortSignal.any and .timeout are missing from
    // browsers still in use (Safari before 17.4, and the in-app browsers built on it).
    const abort = new AbortController();
    let timedOut = false;
    const timer = setTimeout(() => {
      timedOut = true;
      abort.abort();
    }, TIMEOUT_MS);
    const stop = () => abort.abort();
    cancel?.addEventListener('abort', stop, { once: true });
    const lost = () => new BookingApiError(timedOut ? 'timeout' : 'network');
    try {
      let response: Response;
      try {
        response = await fetch(url, { ...init, signal: abort.signal });
      } catch {
        throw lost();
      }
      const body: unknown = await response.json().catch((error: unknown) => {
        // Not JSON is an answer to judge below; a body cut off on the way is a lost connection.
        if (error instanceof SyntaxError) return null;
        throw lost();
      });
      if (response.ok && isBookingView(body)) return body;
      throw new BookingApiError(response.ok ? 'server' : failureIn(response.status, body));
    } finally {
      clearTimeout(timer);
      cancel?.removeEventListener('abort', stop);
    }
  }
}

function failureIn(status: number, body: unknown): Failure {
  const detail = (body as { detail?: unknown } | null)?.detail;
  if (typeof detail === 'string') return FAILURE_BY_DETAIL.get(detail) ?? 'server';
  // FastAPI's own validation answer: a list of the fields that failed.
  if (status === 422 && Array.isArray(detail)) return 'invalid';
  return 'server';
}

function isBookingView(body: unknown): body is BookingView {
  const view = body as Partial<BookingView> | null;
  return (
    typeof view?.id === 'string' &&
    (STATUSES as readonly unknown[]).includes(view.status) &&
    (view.checkout_url === null || typeof view.checkout_url === 'string') &&
    typeof view.can_retry_payment === 'boolean'
  );
}
