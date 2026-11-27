// What the browser scripts say, in each language. Kept apart from the page content so that a
// script bundles a few lines per language, not the whole site. The page's <html lang> picks one.
import type { BookingStatus, Failure } from '../scripts/booking-api';
import type { PaidFormat } from '../site.config';
import { DEFAULT_LOCALE, isLocale, type Locale } from './locales';

export interface Screen {
  title: string;
  text: string;
}

export interface ClientText {
  /** What paying now buys, by format: a label before the price and the text after it. */
  pay: Record<PaidFormat, { label: string; text: string }>;
  payButton: (price: string) => string;
  opening: string;
  free: { label: string; text: string; submit: string; toast: string };
  waitlistToast: string;
  failures: Record<Failure, string>;
  screens: Record<BookingStatus, Screen>;
  /** Awaiting payment, yet the API offers to pay again: the last checkout could not be opened. */
  notOpened: Screen;
  /** Still in flight when the booking page stops asking: the checkout is open. */
  stillWaiting: Screen;
  notFoundTitle: string;
  checkFailedTitle: string;
}

const ru: ClientText = {
  pay: {
    start: { label: 'К оплате', text: ' — созвон по задаче, а через 5 рабочих дней после него — репозиторий под неё.' },
    launch: { label: 'К оплате', text: ' — исправления пулл-реквестами в вашем репозитории. Если проекту нужно больше, до начала работ предложу другой формат или верну деньги.' },
    foundation: { label: 'К оплате сейчас', text: ' — технический старт, первый этап. Сумма засчитается в «Фундамент», если вы его закажете.' },
    subscription: { label: 'К оплате сейчас', text: ' — технический старт, первый этап. Сумма засчитается в первый месяц разработки по подписке, если вы её закажете.' },
  },
  payButton: (price) => `Оплатить ${price} →`,
  opening: 'Открываем оплату…',
  free: {
    label: 'Бесплатно.',
    text: ' Если репозиторий подойдёт для ролика, напишу и договоримся о разборе.',
    submit: 'Отправить заявку →',
    toast: 'Демо: заявка на разбор ушла бы мне в Telegram.',
  },
  waitlistToast: 'Демо: адрес попал бы в лист ожидания.',
  failures: {
    invalid: 'Проверьте анкету: какое-то поле заполнено не так.',
    not_found: 'Бронь не найдена. Проверьте ссылку или оформите бронь заново.',
    conflict: 'Бронь как раз обновляется. Попробуйте ещё раз через пару секунд.',
    provider_down: 'Платёжный сервис сейчас не отвечает. Попробуйте через пару минут.',
    timeout: 'Сервер долго не отвечает. Попробуйте ещё раз.',
    network: 'Нет связи с сервером. Проверьте интернет и попробуйте ещё раз.',
    server: 'Что-то пошло не так на нашей стороне. Попробуйте ещё раз чуть позже.',
  },
  screens: {
    awaiting_payment: { title: 'Проверяем оплату…', text: 'Если вы только что оплатили, статус обновится через несколько секунд.' },
    paid: { title: 'Оплачено', text: 'Спасибо! В течение рабочего дня напишу по контакту из анкеты, чтобы назначить созвон.' },
    declined: { title: 'Оплата не прошла', text: 'Банк отклонил платёж. Можно попробовать ещё раз — другой картой или чуть позже.' },
    expired: { title: 'Время на оплату истекло', text: 'Ссылка на оплату действует ограниченное время. Можно открыть новую.' },
    needs_review: { title: 'Оплата получена и ждёт проверки', text: 'Что-то в платеже не сошлось с бронью. Я проверю сам и напишу вам — ничего делать не нужно.' },
    refunded: { title: 'Деньги возвращены', text: 'Оплата по этой брони возвращена.' },
  },
  notOpened: { title: 'Не удалось открыть оплату', text: 'Платёжный сервис не ответил. Попробуйте открыть оплату ещё раз.' },
  stillWaiting: { title: 'Оплата пока не подтвердилась', text: 'Если вы ещё не оплатили, вернитесь к оплате. Если деньги списались, я это увижу и напишу вам.' },
  notFoundTitle: 'Бронь не найдена',
  checkFailedTitle: 'Не удалось проверить оплату',
};

const CLIENT_TEXT: Record<Locale, ClientText> = { ru };

/** The language of the page this script runs on: its <html lang>. */
export function pageLocale(): Locale {
  const lang = document.documentElement.lang;
  return isLocale(lang) ? lang : DEFAULT_LOCALE;
}

export const clientText = (locale: Locale = pageLocale()): ClientText => CLIENT_TEXT[locale];
