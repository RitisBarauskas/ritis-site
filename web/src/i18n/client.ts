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

const en: ClientText = {
  pay: {
    start: { label: 'To pay', text: ' — a call about your task, then, within 5 working days of it, a repository for the task.' },
    launch: { label: 'To pay', text: ' — fixes as pull requests in your repository. If the project needs more, I will offer another format or return the money before any work starts.' },
    foundation: { label: 'To pay now', text: ' — the technical start, the first stage. It counts towards the Foundation if you order it.' },
    subscription: { label: 'To pay now', text: ' — the technical start, the first stage. It counts towards the first month of the development subscription if you order it.' },
  },
  payButton: (price) => `Pay ${price} →`,
  opening: 'Opening the payment page…',
  free: {
    label: 'Free.',
    text: ' If the repository suits a video, I will write to you to arrange the teardown.',
    submit: 'Send the request →',
    toast: 'Demo: the teardown request would go to my Telegram.',
  },
  waitlistToast: 'Demo: your address would join the waitlist.',
  failures: {
    invalid: 'Please check the form: one of the fields is filled in incorrectly.',
    not_found: 'Booking not found. Check the link or book again.',
    conflict: 'The booking is being updated right now. Try again in a couple of seconds.',
    provider_down: 'The payment service is not responding. Try again in a couple of minutes.',
    timeout: 'The server is taking too long to respond. Please try again.',
    network: 'No connection to the server. Check your internet connection and try again.',
    server: 'Something went wrong on our side. Please try again a little later.',
  },
  screens: {
    awaiting_payment: { title: 'Checking the payment…', text: 'If you have just paid, the status will update in a few seconds.' },
    paid: { title: 'Paid', text: 'Thank you! Within a working day I will write to the contact from your form to schedule the call.' },
    declined: { title: 'The payment did not go through', text: 'The bank declined the payment. You can try again — with another card or a little later.' },
    expired: { title: 'The time to pay has run out', text: 'A payment link is valid for a limited time. You can open a new one.' },
    needs_review: { title: 'Payment received, under review', text: 'Something in the payment did not match the booking. I will check it myself and write to you — you do not need to do anything.' },
    refunded: { title: 'Money returned', text: 'The payment for this booking has been refunded.' },
  },
  notOpened: { title: 'The payment could not be opened', text: 'The payment service did not respond. Try opening the payment again.' },
  stillWaiting: { title: 'The payment is not confirmed yet', text: 'If you have not paid yet, go back to the payment. If the money was charged, I will see it and write to you.' },
  notFoundTitle: 'Booking not found',
  checkFailedTitle: 'Could not check the payment',
};

const ka: ClientText = {
  pay: {
    start: { label: 'გადასახდელი', text: ' — ვიდეოზარი თქვენს ამოცანაზე, ხოლო მისგან 5 სამუშაო დღეში — რეპოზიტორია ამ ამოცანისთვის.' },
    launch: { label: 'გადასახდელი', text: ' — შესწორებები pull request-ებით თქვენს რეპოზიტორიაში. თუ პროექტს მეტი სჭირდება, სამუშაოს დაწყებამდე შემოგთავაზებთ სხვა ფორმატს ან დაგიბრუნებთ თანხას.' },
    foundation: { label: 'ახლა გადასახდელი', text: ' — ტექნიკური სტარტი, პირველი ეტაპი. თანხა ჩაითვლება „ფუნდამენტის“ ფასში, თუ მას შეუკვეთავთ.' },
    subscription: { label: 'ახლა გადასახდელი', text: ' — ტექნიკური სტარტი, პირველი ეტაპი. თანხა ჩაითვლება გამოწერით შემუშავების პირველი თვის საფასურში, თუ მას შეუკვეთავთ.' },
  },
  payButton: (price) => `გადაიხადეთ ${price} →`,
  opening: 'გადახდის გვერდი იხსნება…',
  free: {
    label: 'უფასოა.',
    text: ' თუ რეპოზიტორია ვიდეოსთვის გამოდგება, მოგწერთ და განხილვაზე შევთანხმდებით.',
    submit: 'განაცხადის გაგზავნა →',
    toast: 'დემო: განხილვის განაცხადი ჩემს Telegram-ში გაიგზავნებოდა.',
  },
  waitlistToast: 'დემო: მისამართი მოლოდინის სიაში დაემატებოდა.',
  failures: {
    invalid: 'შეამოწმეთ ანკეტა: ერთ-ერთი ველი არასწორადაა შევსებული.',
    not_found: 'ჯავშანი ვერ მოიძებნა. შეამოწმეთ ბმული ან ხელახლა დაჯავშნეთ.',
    conflict: 'ჯავშანი ამ წუთას ახლდება. სცადეთ ხელახლა რამდენიმე წამში.',
    provider_down: 'გადახდის სერვისი ახლა არ პასუხობს. სცადეთ რამდენიმე წუთში.',
    timeout: 'სერვერი დიდხანს არ პასუხობს. სცადეთ ხელახლა.',
    network: 'სერვერთან კავშირი არ არის. შეამოწმეთ ინტერნეტი და სცადეთ ხელახლა.',
    server: 'ჩვენს მხარეს რაღაც შეფერხდა. სცადეთ ცოტა მოგვიანებით.',
  },
  screens: {
    awaiting_payment: { title: 'გადახდას ვამოწმებთ…', text: 'თუ ახლახან გადაიხადეთ, სტატუსი რამდენიმე წამში განახლდება.' },
    paid: { title: 'გადახდილია', text: 'გმადლობთ! ერთი სამუშაო დღის განმავლობაში მოგწერთ ანკეტაში მითითებულ კონტაქტზე, რომ ვიდეოზარი დავნიშნოთ.' },
    declined: { title: 'გადახდა ვერ შესრულდა', text: 'ბანკმა გადახდა უარყო. შეგიძლიათ ხელახლა სცადოთ — სხვა ბარათით ან ცოტა მოგვიანებით.' },
    expired: { title: 'გადახდის დრო ამოიწურა', text: 'გადახდის ბმული შეზღუდული დროით მოქმედებს. შეგიძლიათ ახალი გახსნათ.' },
    needs_review: { title: 'გადახდა მიღებულია და შემოწმებას ელოდება', text: 'გადახდაში რაღაც არ დაემთხვა ჯავშანს. თავად შევამოწმებ და მოგწერთ — თქვენგან არაფერია საჭირო.' },
    refunded: { title: 'თანხა დაბრუნებულია', text: 'ამ ჯავშნისთვის გადახდილი თანხა დაბრუნებულია.' },
  },
  notOpened: { title: 'გადახდის გახსნა ვერ მოხერხდა', text: 'გადახდის სერვისმა არ უპასუხა. სცადეთ გადახდის ხელახლა გახსნა.' },
  stillWaiting: { title: 'გადახდა ჯერ არ დადასტურებულა', text: 'თუ ჯერ არ გადაგიხდიათ, დაბრუნდით გადახდის გვერდზე. თუ თანხა ჩამოგეჭრათ, ამას დავინახავ და მოგწერთ.' },
  notFoundTitle: 'ჯავშანი ვერ მოიძებნა',
  checkFailedTitle: 'გადახდის შემოწმება ვერ მოხერხდა',
};

const CLIENT_TEXT: Record<Locale, ClientText> = { ru, ka, en };

/** The language of the page this script runs on: its <html lang>. */
export function pageLocale(): Locale {
  const lang = document.documentElement.lang;
  return isLocale(lang) ? lang : DEFAULT_LOCALE;
}

export const clientText = (locale: Locale = pageLocale()): ClientText => CLIENT_TEXT[locale];
