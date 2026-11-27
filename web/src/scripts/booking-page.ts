import type { ClientText, Screen } from '../i18n/client';
import { BookingApi, BookingApiError, type BookingView, type Failure } from './booking-api';

/** What the customer can do from a screen: pay again, or go back to the checkout still open. */
interface Actions {
  retry?: boolean;
  resume?: string | null;
}

const BOOKING_ID = /^[0-9a-f]{32}$/;

/** The payment is still to be settled: a checkout is open, or is being opened. */
const inFlight = (booking: BookingView) =>
  booking.status === 'awaiting_payment' && !booking.can_retry_payment;

interface PollPolicy {
  intervalMs: number;
  attempts: number;
}

/** The page a customer lands on after the checkout: shows where the booking stands. */
export class BookingStatusPage {
  constructor(
    private readonly view: {
      title: HTMLElement;
      text: HTMLElement;
      retry: HTMLButtonElement;
      resume: HTMLAnchorElement;
    },
    private readonly api: BookingApi,
    private readonly poll: PollPolicy,
    private readonly text: ClientText,
  ) {}

  async start(params: URLSearchParams): Promise<void> {
    const id = params.get('id');
    // A booking id is 32 hex digits; anything else is a broken link, not a question for the API.
    if (!id || !BOOKING_ID.test(id)) {
      this.showFailure('not_found');
      return;
    }
    this.view.retry.addEventListener('click', () => void this.payAgain(id));
    await this.watch(id);
  }

  /** Show the booking, asking again while its payment is in flight or the API is out of reach. */
  private async watch(id: string): Promise<void> {
    let waiting: BookingView | null = null;
    for (let attempt = 1; attempt <= this.poll.attempts; attempt++) {
      if (attempt > 1) await sleep(this.poll.intervalMs);
      try {
        const booking = await this.api.status(id);
        this.showBooking(booking);
        waiting = inFlight(booking) ? booking : null;
        if (!waiting) return;
      } catch (error) {
        const failure = BookingApiError.failureOf(error);
        this.showFailure(failure);
        waiting = null;
        // A booking the API does not know will not appear; any other failure may pass.
        if (failure === 'not_found') return;
      }
    }
    if (waiting) this.show(this.text.stillWaiting, { resume: waiting.checkout_url });
  }

  private async payAgain(id: string): Promise<void> {
    this.view.retry.disabled = true;
    try {
      const booking = await this.api.payAgain(id);
      if (booking.checkout_url) window.location.assign(booking.checkout_url);
      else this.showBooking(booking);
    } catch (error) {
      const failure = BookingApiError.failureOf(error);
      // The booking moved on meanwhile (paid in another tab, say): show where it stands now.
      if (failure === 'conflict') return this.watch(id);
      this.show({ title: this.text.notOpened.title, text: this.text.failures[failure] }, { retry: failure !== 'not_found' });
      this.view.retry.focus();
    }
  }

  private showBooking(booking: BookingView): void {
    const failedToOpen = booking.status === 'awaiting_payment' && booking.can_retry_payment;
    this.show(failedToOpen ? this.text.notOpened : this.text.screens[booking.status], {
      retry: booking.can_retry_payment,
      resume: inFlight(booking) ? booking.checkout_url : null,
    });
  }

  private showFailure(failure: Failure): void {
    const title = failure === 'not_found' ? this.text.notFoundTitle : this.text.checkFailedTitle;
    this.show({ title, text: this.text.failures[failure] });
  }

  private show(screen: Screen, actions: Actions = {}): void {
    this.view.title.textContent = screen.title;
    this.view.text.textContent = screen.text;
    this.view.retry.hidden = !actions.retry;
    this.view.retry.disabled = false;
    this.view.resume.hidden = !actions.resume;
    if (actions.resume) this.view.resume.href = actions.resume;
  }
}

function sleep(ms: number): Promise<void> {
  return new Promise((resolve) => setTimeout(resolve, ms));
}
