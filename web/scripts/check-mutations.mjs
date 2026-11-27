// Prove that the browser tests can fail: break each key rule of the booking flow and expect its
// own tests to catch it. Run from web/: npm run mutations
//
// A mutant counts as caught only when its named tests run and fail. A mutant that breaks the
// build or a page script (the guard in tests/e2e/fixtures.ts marks that), or names no test, is
// reported as broken, not as caught; one mutant breaks a script on purpose, so that this path is
// proven on every run. Each fragment must occur exactly once in its file, so a refactoring that
// moves a rule makes this script fail loudly until the mutation is updated. The original of the file being mutated is kept in .mutation-backup until
// it is restored, so a run killed half-way is repaired by the next one.
import { spawnSync } from 'node:child_process';
import { existsSync, readFileSync, unlinkSync, writeFileSync } from 'node:fs';
import { fileURLToPath } from 'node:url';

const root = fileURLToPath(new URL('..', import.meta.url));
const BACKUP = `${root}.mutation-backup`;
const PLAYWRIGHT = `${root}node_modules/@playwright/test/cli.js`;

class Mutation {
  /**
   * @param {string} caughtBy the start of the title of the tests that must fail
   * @param {string} expected the verdict this mutant must get
   */
  constructor(file, original, mutant, caughtBy, expected = 'caught') {
    // A Windows checkout has CRLF line endings and CI has LF: a fragment must not span lines.
    if (original.includes('\n')) throw new Error(`${file}: fragment spans lines: ${original}`);
    Object.assign(this, { file, original, mutant, caughtBy, expected });
  }

  /** Write the mutant and return the file's original bytes, to be restored as they were. */
  apply() {
    const path = root + this.file;
    const original = readFileSync(path);
    const source = original.toString('utf8');
    if (source.split(this.original).length !== 2) {
      throw new Error(`${this.file}: fragment not found exactly once: ${this.original}`);
    }
    writeFileSync(BACKUP, JSON.stringify({ path, original: original.toString('base64') }));
    // A function, not a string: a replacement string would expand $& and the like.
    writeFileSync(path, source.replace(this.original, () => this.mutant));
    return original;
  }

  restore(original) {
    writeFileSync(root + this.file, original);
    unlinkSync(BACKUP);
  }
}

const M = (...args) => new Mutation(...args);
const DIALOG = 'src/components/BookingDialog.astro';
const API = 'src/scripts/booking-api.ts';
const PAGE = 'src/scripts/booking-page.ts';

const MUTATIONS = [
  // The booking dialog.
  M(DIALOG, 'if (payload !== this.payload) {', 'if (true) {', 'сбой платёжного сервиса: понятное сообщение и повтор'),
  M(DIALOG, 'if (payload !== this.payload) {', "if (this.key === '') {", 'исправленная после сбоя анкета'),
  M(DIALOG, 'consent.required = !isFree();', 'consent.required = false;', 'без согласия с офертой'),
  M(DIALOG, 'tabindex="-1" autocomplete="off"', 'autocomplete="off"', 'ловушка для ботов'),
  M(DIALOG, 'booking.checkout_url ?? `/booking/?id=', 'booking.checkout_url ?? `/?id=', 'повтор уже оплаченной анкеты'),
  M(DIALOG, 'if (!event.persisted) return;', 'return;', 'возврат со страницы оплаты кнопкой «Назад» окно брони'),
  M(DIALOG, "dlg.addEventListener('close', () => pending?.abort());", "dlg.addEventListener('close', () => {});", 'пока ждём API, анкету не поправить'),
  M(DIALOG, 'if (cancel.signal.aborted) return;', 'if (false) return;', 'пока ждём API, анкету не поправить'),
  M(DIALOG, 'fields.disabled = true;', 'fields.disabled = false;', 'пока ждём API, анкету не поправить'),
  M(DIALOG, String.raw`required maxlength="100" pattern=".*\S.*"`, 'required maxlength="100"', 'имя из одних пробелов'),
  // What each failure of the API turns into.
  M(API, "if (status === 422 && Array.isArray(detail)) return 'invalid';", "if (false) return 'invalid';", 'API не принял анкету'),
  M(API, "['payment_provider_unavailable', 'provider_down'],", '', 'сбой платёжного сервиса'),
  M(API, "new BookingApiError(timedOut ? 'timeout' : 'network');", "new BookingApiError('server');", 'нет связи с сервером'),
  M(API, "new BookingApiError(timedOut ? 'timeout' : 'network');", "new BookingApiError('network');", 'API молчит'),
  M(API, "if (typeof detail === 'string')", "if (status === 404) return 'not_found'; if (typeof detail === 'string')", 'по адресу API ничего нет'),
  M(API, 'if (response.ok && isBookingView(body)) return body;', 'if (response.ok) return body as BookingView;', 'API ответил непонятно'),
  // The booking page.
  M(PAGE, 'if (!id || !BOOKING_ID.test(id)) {', 'if (!id) {', 'ссылка без брони не ходит в API'),
  M(PAGE, 'attempt <= this.poll.attempts', 'attempt < this.poll.attempts', 'опрос не бесконечный'),
  M(PAGE, "booking.status === 'awaiting_payment' && !booking.can_retry_payment;", "booking.status === 'awaiting_payment';", 'оплату не удалось открыть: страница не ждёт впустую'),
  M(PAGE, 'this.show(STILL_WAITING, { resume: waiting.checkout_url });', 'this.show(STILL_WAITING);', 'опрос не бесконечный'),
  M(PAGE, "if (failure === 'not_found') return;", 'return;', 'временный сбой связи не останавливает опрос'),
  M(PAGE, "if (failure === 'not_found') return;", 'if (false) return;', 'бронь, которой нет у API: больше не спрашивает'),
  M(PAGE, 'retry: booking.can_retry_payment,', 'retry: true,', 'оплачено'),
  M(PAGE, 'resume: inFlight(booking) ? booking.checkout_url : null,', 'resume: null,', 'оплата открыта: можно вернуться к ней'),
  M(PAGE, 'this.view.retry.hidden = !actions.retry;', 'this.view.retry.hidden = true;', 'Оплата не прошла: «Оплатить снова»'),
  M(PAGE, "if (failure === 'conflict') return this.watch(id);", 'if (false) return this.watch(id);', '«Оплатить снова», а бронь тем временем оплачена'),
  M(PAGE, "{ retry: failure !== 'not_found' });", '{});', '«Оплатить снова», а платёжный сервис не отвечает'),
  M('src/pages/booking/index.astro', 'if (event.persisted) window.location.reload();', 'if (false) window.location.reload();', 'возврат со страницы оплаты кнопкой «Назад» страница брони'),
  // Shared pieces the booking flow relies on.
  M('src/styles/base.css', '[hidden]{display:none!important}', '', 'оплата на проверке'),
  M('src/sections/Offers.astro', '<span>Visa</span><span>Mastercard</span><em>', '<span>Visa</span><span>Mastercard</span><span>Мир</span><em>', 'обещает только те способы оплаты'),
  M('src/components/Header.astro', '<a href="/#help">', '<a href="#help">', 'шапка ведёт на разделы главной'),
  // Proves the broken-script path: this one must not count as caught.
  M(DIALOG, "byId('book-fields', HTMLFieldSetElement)", "byId('no-such-id', HTMLFieldSetElement)", 'анкета уходит в API', 'BROKEN (script)'),
];

function restoreInterruptedRun() {
  if (!existsSync(BACKUP)) return;
  const { path, original } = JSON.parse(readFileSync(BACKUP, 'utf8'));
  writeFileSync(path, Buffer.from(original, 'base64'));
  unlinkSync(BACKUP);
  console.log(`restored ${path}, left mutated by an interrupted run`);
}

const escape = (text) => text.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');

/** Run the tests whose full titles start with one of the given prefixes; a fresh build each time. */
function run(titles) {
  const grep = titles.map((title) => `(^| )${escape(title)}`).join('|');
  const done = spawnSync(process.execPath, [PLAYWRIGHT, 'test', '--grep', grep, '--reporter=line'], {
    cwd: root,
    encoding: 'utf8',
  });
  const output = `${done.stdout}${done.stderr}`;
  const count = (word) => Number(output.match(new RegExp(`(\\d+) ${word}`))?.[1] ?? 0);
  return {
    code: done.status,
    failed: count('failed'),
    passed: count('passed'),
    // Set by the guard in tests/e2e/fixtures.ts: the mutant broke a page script, and the tests
    // failed for that rather than for the rule they check.
    scriptBroken: output.includes('uncaught error in a page script'),
  };
}

function verdict({ code, failed, scriptBroken }) {
  if (scriptBroken) return 'BROKEN (script)';
  if (code === 1 && failed > 0) return 'caught';
  if (code === 0) return 'SURVIVED';
  return `BROKEN (exit ${code})`;
}

function main() {
  restoreInterruptedRun();
  const named = run([...new Set(MUTATIONS.map((m) => m.caughtBy))]);
  if (named.code !== 0 || named.passed === 0) {
    console.log('the named tests are not green without mutations; fix that first');
    return 1;
  }
  let wrong = 0;
  MUTATIONS.forEach((mutation, index) => {
    const original = mutation.apply();
    let outcome;
    try {
      outcome = verdict(run([mutation.caughtBy]));
    } finally {
      mutation.restore(original);
    }
    const note = outcome === mutation.expected ? '' : `  <- expected ${mutation.expected}`;
    if (note) wrong += 1;
    console.log(`${String(index + 1).padStart(2)} ${outcome.padEnd(15)} ${mutation.file}: ${mutation.caughtBy}${note}`);
  });
  console.log(`${MUTATIONS.length - wrong}/${MUTATIONS.length} as expected`);
  return wrong ? 1 : 0;
}

process.exitCode = main();
