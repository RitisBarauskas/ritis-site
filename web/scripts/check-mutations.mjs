// Prove that the browser tests can fail: break each rule of the booking flow and expect its own
// test to catch it. Run from web/: npm run mutations
//
// A mutant counts as caught only when its named tests run and fail. A mutant that breaks the
// build, or names no test, is reported as broken, not as caught. Each fragment must occur exactly
// once in its file, so a refactoring that moves a rule makes this script fail loudly until the
// mutation is updated. The original of the file being mutated is kept in .mutation-backup until
// it is restored, so a run killed half-way is repaired by the next one.
import { spawnSync } from 'node:child_process';
import { existsSync, readFileSync, unlinkSync, writeFileSync } from 'node:fs';
import { fileURLToPath } from 'node:url';

const root = fileURLToPath(new URL('..', import.meta.url));
const BACKUP = `${root}.mutation-backup`;
const PLAYWRIGHT = `${root}node_modules/@playwright/test/cli.js`;

class Mutation {
  /** @param {string} caughtBy the start of the title of the tests that must fail */
  constructor(file, original, mutant, caughtBy) {
    // A Windows checkout has CRLF line endings and CI has LF: a fragment must not span lines.
    if (original.includes('\n')) throw new Error(`${file}: fragment spans lines: ${original}`);
    Object.assign(this, { file, original, mutant, caughtBy });
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
  // What each failure of the API turns into.
  M(API, "[422, 'invalid'],", '', 'API не принял анкету'),
  M(API, "[502, 'provider_down'],", '', 'сбой платёжного сервиса'),
  M(API, "throw new BookingApiError('network');", "throw new BookingApiError('server');", 'нет связи с сервером'),
  // The booking page.
  M(PAGE, 'if (!id || !BOOKING_ID.test(id)) {', 'if (!id) {', 'ссылка без брони не ходит в API'),
  M(PAGE, 'attempt <= this.poll.attempts', 'attempt < this.poll.attempts', 'опрос не бесконечный'),
  M(PAGE, 'this.view.retry.hidden = !screen.retry;', 'this.view.retry.hidden = true;', 'Оплата не прошла: «Оплатить снова»'),
  M(PAGE, "if (failure === 'conflict') await this.watch(id);", 'if (false) await this.watch(id);', '«Оплатить снова», а бронь тем временем оплачена'),
  M(PAGE, 'failureMessages[failure], retry: true });', 'failureMessages[failure] });', '«Оплатить снова», а платёжный сервис не отвечает'),
  M('src/pages/booking/index.astro', 'if (event.persisted) window.location.reload();', 'if (false) window.location.reload();', 'возврат со страницы оплаты кнопкой «Назад» страница брони'),
  // Shared pieces the booking flow relies on.
  M('src/styles/base.css', '[hidden]{display:none!important}', '', 'оплата на проверке'),
  M('src/site.config.ts', 'russianMethods: false,', 'russianMethods: true,', 'обещает только те способы оплаты'),
  M('src/components/Header.astro', '<a href="/#help">', '<a href="#help">', 'шапка ведёт на разделы главной'),
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
  return { code: done.status, failed: count('failed'), passed: count('passed') };
}

function verdict({ code, failed }) {
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
  let survived = 0;
  MUTATIONS.forEach((mutation, index) => {
    const original = mutation.apply();
    let outcome;
    try {
      outcome = verdict(run([mutation.caughtBy]));
    } finally {
      mutation.restore(original);
    }
    if (outcome !== 'caught') survived += 1;
    console.log(`${String(index + 1).padStart(2)} ${outcome.padEnd(14)} ${mutation.file}: ${mutation.caughtBy}`);
  });
  console.log(`${MUTATIONS.length - survived}/${MUTATIONS.length} caught`);
  return survived ? 1 : 0;
}

process.exitCode = main();
