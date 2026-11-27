import {
  BookingApi,
  BookingApiError,
  failureMessages,
  type BookingStatus,
  type BookingView,
  type Failure,
} from './booking-api';

interface Screen {
  title: string;
  text: string;
  retry?: boolean;
}

const SCREENS: Record<BookingStatus, Screen> = {
  awaiting_payment: {
    title: 'Проверяем оплату…',
    text: 'Если вы только что оплатили, статус обновится через несколько секунд.',
  },
  paid: {
    title: 'Оплачено',
    text: 'Спасибо! Свяжусь с вами в течение дня по контакту из анкеты, чтобы выбрать время звонка.',
  },
  declined: {
    title: 'Оплата не прошла',
    text: 'Банк отклонил платёж. Можно попробовать ещё раз — другой картой или чуть позже.',
    retry: true,
  },
  expired: {
    title: 'Время на оплату истекло',
    text: 'Ссылка на оплату действует ограниченное время. Можно открыть новую.',
    retry: true,
  },
  needs_review: {
    title: 'Оплата получена и ждёт проверки',
    text: 'Что-то в платеже не сошлось с бронью. Я проверю сам и напишу вам — ничего делать не нужно.',
  },
  refunded: {
    title: 'Деньги возвращены',
    text: 'Оплата по этой брони возвращена.',
  },
};

const BOOKING_ID = /^[0-9a-f]{32}$/;

const STILL_WAITING: Screen = {
  title: 'Оплата пока не подтвердилась',
  text: 'Если деньги списались, я это увижу и напишу вам. Можно обновить страницу позже.',
};

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
    },
    private readonly api: BookingApi,
    private readonly poll: PollPolicy,
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

  /** Show the booking's status, asking again while its payment is in flight. */
  private async watch(id: string): Promise<void> {
    for (let attempt = 1; attempt <= this.poll.attempts; attempt++) {
      const booking = await this.load(id);
      if (!booking) return;
      if (booking.status !== 'awaiting_payment') return;
      if (attempt < this.poll.attempts) await sleep(this.poll.intervalMs);
    }
    this.show(STILL_WAITING);
  }

  private async load(id: string): Promise<BookingView | null> {
    try {
      const booking = await this.api.status(id);
      this.show(SCREENS[booking.status]);
      return booking;
    } catch (error) {
      this.showFailure(BookingApiError.failureOf(error));
      return null;
    }
  }

  private async payAgain(id: string): Promise<void> {
    this.view.retry.disabled = true;
    try {
      const booking = await this.api.payAgain(id);
      if (booking.checkout_url) window.location.assign(booking.checkout_url);
      else this.show(SCREENS[booking.status]);
    } catch (error) {
      const failure = BookingApiError.failureOf(error);
      // The booking moved on meanwhile (paid in another tab, say): show where it stands now.
      if (failure === 'conflict') await this.watch(id);
      else this.show({ title: 'Не удалось открыть оплату', text: failureMessages[failure], retry: true });
    }
  }

  private showFailure(failure: Failure): void {
    const title = failure === 'not_found' ? 'Бронь не найдена' : 'Не удалось проверить оплату';
    this.show({ title, text: failureMessages[failure] });
  }

  private show(screen: Screen): void {
    this.view.title.textContent = screen.title;
    this.view.text.textContent = screen.text;
    this.view.retry.hidden = !screen.retry;
    this.view.retry.disabled = false;
  }
}

function sleep(ms: number): Promise<void> {
  return new Promise((resolve) => setTimeout(resolve, ms));
}
