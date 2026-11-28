"""Prove that the tests can fail: break each key rule and expect its own test to catch it.

Run from api/: uv run python scripts/check_mutations.py

A mutant counts as caught only when its named test runs and fails: pytest reports failures and
no errors. A mutant that does not import, or breaks a fixture, is reported as broken, not as
caught. Each fragment must occur exactly once in its file, so a refactoring that moves a rule
makes this script fail loudly until the mutation is updated. The original of the file being
mutated is kept in .mutation-backup until it is restored, so a run killed half-way is repaired
by the next one.
"""

from __future__ import annotations

import base64
import json
import os
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

SRC = Path("src/ritis_api")
BACKUP = Path(".mutation-backup")


@dataclass(frozen=True)
class Mutation:
    file: str
    original: str
    mutant: str
    caught_by: str  # a pytest -k expression naming the test that must fail
    # Firestore mutants run the tests that only the emulator can serve.
    marks: str = "not live and not firestore"

    def apply(self) -> bytes:
        """Write the mutant and return the file's original bytes, to be restored as they were."""
        path = SRC / self.file
        # Bytes, not text: text mode would rewrite line endings on Windows.
        original = path.read_bytes()
        source = original.decode("utf-8")
        if source.count(self.original) != 1:
            raise SystemExit(f"{self.file}: fragment not found exactly once: {self.original!r}")
        backup = {"file": str(path), "original": base64.b64encode(original).decode()}
        BACKUP.write_text(json.dumps(backup), encoding="utf-8")
        path.write_bytes(source.replace(self.original, self.mutant).encode("utf-8"))
        return original

    def restore(self, original: bytes) -> None:
        (SRC / self.file).write_bytes(original)
        BACKUP.unlink()


M = Mutation
MUTATIONS = [
    # Money and review rules of the Booking aggregate.
    M(
        "domain/booking.py",
        "if amount != attempt.price:",
        "if False:",
        "test_a_charge_other_than_the_price_is_flagged_and_kept",
    ),
    M(
        "domain/booking.py",
        "elif settled_before:",
        "elif False:",
        "test_a_second_successful_payment_is_flagged",
    ),
    M(
        "domain/booking.py",
        "settled_before = self.status in _SETTLED",
        "settled_before = self.status is BookingStatus.PAID",
        "test_a_second_successful_payment_is_flagged and refunded",
    ),
    M(
        "domain/booking.py",
        "elif self.status is BookingStatus.NEEDS_REVIEW:",
        "elif False:",
        "test_a_correct_payment_after_a_flag_does_not_clear_it",
    ),
    M(
        "domain/booking.py",
        "elif self.status is BookingStatus.PAID and self._everything_refunded():",
        "elif self._everything_refunded():",
        "test_refunding_an_overcharge_keeps_the_flag",
    ),
    M(
        "domain/booking.py",
        "and refunded <= previous:",
        "and refunded < previous:",
        "test_running_totals_from_the_provider",
    ),
    M(
        "domain/booking.py",
        "if charged is None or charged.currency is not refunded.currency or charged < refunded:",
        "if charged is None:",
        "test_a_refund_above_the_charge_is_flagged_not_raised",
    ),
    M(
        "domain/booking.py",
        "if attempt.status in {attempt_status, AttemptStatus.APPROVED}:",
        "if attempt.status in {attempt_status}:",
        "test_a_failure_after_approval_is_stale",
    ),
    M(
        "domain/booking.py",
        "self.status is BookingStatus.AWAITING_PAYMENT and attempt is self.current_attempt",
        "attempt is self.current_attempt",
        "test_a_failure_while_flagged_keeps_the_flag",
    ),
    M(
        "domain/booking.py",
        " and attempt is self.current_attempt:",
        ":",
        "test_an_old_attempt_failing_leaves_the_open_one_alone",
    ),
    M(
        "domain/booking.py",
        "if attempt.charged == amount:",
        "if True:",
        "test_a_provider_changing_a_recorded_charge_is_flagged",
    ),
    M(
        "domain/booking.py",
        "return bool(approved) and all(a.refunded_in_full for a in approved)",
        "return bool(approved)",
        "test_running_totals_from_the_provider",
    ),
    M(
        "domain/payment.py",
        "if self.refunded.currency is not self.amount.currency:",
        "if False:",
        "test_a_report_cannot_refund_in_another_currency_than_it_charged",
    ),
    # Flitt: signature, notifications, replies.
    M(
        "adapters/flitt/signature.py",
        "for name in sorted(fields):",
        "for name in sorted(fields, reverse=True):",
        "test_matches_the_documented_example",
    ),
    M(
        "adapters/flitt/signature.py",
        "return hmac.compare_digest(received.encode(), self.sign(fields).encode())",
        "return True",
        "test_rejects_tampered_or_missing_signatures",
    ),
    M(
        "adapters/flitt/notifications.py",
        'if str(payload.get("merchant_id")) != str(self._merchant_id):',
        "if False:",
        "test_a_notification_for_another_merchant",
    ),
    M(
        "adapters/flitt/notifications.py",
        "if not isinstance(order_id, str) or not order_id:",
        "if not isinstance(order_id, str):",
        "test_a_notification_without_an_order",
    ),
    M(
        "adapters/flitt/provider.py",
        '"delayed": "N",',
        "",
        "test_a_signed_request_for_one_try_per_order",
    ),
    M(
        "adapters/flitt/provider.py",
        'self._amount("actual_amount")',
        'self._amount("amount")',
        "test_the_charge_is_what_the_card_paid_not_what_was_asked",
    ),
    M(
        "adapters/flitt/provider.py",
        'raw = self._reply.get("actual_currency")',
        'raw = self._reply.get("currency")',
        "test_the_charge_is_what_the_card_paid_not_what_was_asked",
    ),
    M(
        "adapters/flitt/provider.py",
        'refunded = charged if status == "reversed" else Money.zero(currency)',
        "refunded = Money.zero(currency)",
        "test_a_full_reversal_without_an_amount_refunds_the_whole_charge",
    ),
    M(
        "adapters/flitt/client.py",
        "if signed_reply and not self._signer.verify(reply):",
        "if False:",
        "test_unusable_status_replies and tampered",
    ),
    M("adapters/flitt/client.py", '"1018": OrderNotFoundError,', "", "test_recorded_unknown_order"),
    M(
        "adapters/memory.py",
        "if stored.version != booking.version:",
        "if False:",
        "test_a_stale_copy_cannot_overwrite_a_newer_one",
    ),
    # Confirming payments.
    M(
        "app/confirm_payment.py",
        "if booking is None or not self._holds(booking.attempt(order_id)):",
        "if booking is None:",
        "test_unknown_orders_and_orders_of_another_provider",
    ),
    M(
        "app/confirm_payment.py",
        "if not self._rechecks.admit(attempt.order_id):",
        "if False:",
        "test_asks_the_provider_at_most_once_per_interval",
    ),
    M(
        "app/confirm_payment.py",
        "timedelta(0) <= now - t < self._interval",
        "timedelta(0) <= now - t",
        "test_asks_the_provider_at_most_once_per_interval",
    ),
    M(
        "app/confirm_payment.py",
        "timedelta(0) <= now - t < self._interval",
        "now - t < self._interval",
        "test_a_clock_set_back_does_not_lock_out_rechecks",
    ),
    M(
        "app/confirm_payment.py",
        "return attempt.provider == self._provider.name",
        "return True",
        "test_a_refresh_leaves_another_providers_order_alone",
    ),
    M(
        "app/confirm_payment.py",
        "except PaymentProviderError:",
        "except ValueError:",
        "test_answers_during_a_provider_outage",
    ),
    M(
        "app/confirm_payment.py",
        "for _ in range(self._SAVE_ATTEMPTS):",
        "for _ in range(1):",
        "test_a_payment_survives_a_concurrent_change_of_the_booking",
    ),
    M(
        "app/confirm_payment.py",
        "booking = self._repository.get(booking.id)",
        "return booking",
        "test_a_payment_survives_a_concurrent_change_of_the_booking",
    ),
    M(
        "app/confirm_payment.py",
        "if booking.status is BookingStatus.PAID and status is not BookingStatus.PAID:",
        "if booking.status is BookingStatus.PAID:",
        "test_a_partial_refund_is_not_announced_as_a_payment",
    ),
    M(
        "app/confirm_payment.py",
        "booking.review_reason != reason",
        "status is not BookingStatus.NEEDS_REVIEW",
        "test_every_new_problem_is_announced_for_review",
    ),
    # Opening bookings.
    M(
        "app/open_booking.py",
        "if booking.open_checkout_url is not None:",
        "if False:",
        "test_a_repeated_request_returns_the_same_checkout",
    ),
    M(
        "app/open_booking.py",
        "booking.mark_checkout_failed(attempt.order_id)",
        "pass",
        "test_an_interrupted_start_is_finished_with_a_new_order",
    ),
    M(
        "app/open_booking.py",
        "customer_email=contact if _EMAIL.match(contact) else None,",
        "customer_email=contact,",
        "test_a_telegram_handle_is_not_passed_as_email",
    ),
    M(
        "app/open_booking.py",
        "return self._repeat(twin, command)",
        "raise",
        "test_a_twin_request_answers_with_the_winners_checkout",
    ),
    M(
        "app/open_booking.py",
        "return self._repository.get(booking.id)",
        "return booking",
        "test_losing_the_write_answers_with_the_stored_state",
    ),
    M(
        "app/open_booking.py",
        "asked = (command.booking_format, command.customer, command.language)",
        "asked = (booking.format, booking.customer, booking.language)",
        "test_a_key_reused_for_another_request_is_refused",
    ),
    M(
        "app/open_booking.py",
        "asked = (command.booking_format, command.customer, command.language)",
        "asked = (command.booking_format, command.customer, booking.language)",
        "test_a_key_reused_in_another_language_is_refused",
    ),
    # The customer's language: the checkout, its description and the way back follow it.
    M(
        "app/open_booking.py",
        "language=booking.language.value,",
        'language="ru",',
        "test_the_checkout_speaks_the_language_the_customer_booked_in",
    ),
    M(
        "app/open_booking.py",
        "description=self._catalog.offer(booking.format).description(booking.language),",
        "description=self._catalog.offer(booking.format).description(Language.RU),",
        "test_the_checkout_speaks_the_language_the_customer_booked_in",
    ),
    M(
        "app/open_booking.py",
        "language=command.language,",
        "language=Language.RU,",
        "test_the_checkout_speaks_the_language_the_customer_booked_in",
    ),
    M(
        "http/flitt.py",
        "language = Language(lang) if lang in set(Language) else Language.RU",
        "language = Language.RU",
        "test_the_customer_comes_back_to_the_booking_page_in_their_language",
    ),
    M(
        "http/flitt.py",
        '?booking={{booking_id}}&lang={{language}}",',
        '?booking={{booking_id}}",',
        "test_the_customer_comes_back_to_the_booking_page_in_their_language",
    ),
    M(
        "app/catalog.py",
        "missing = set(Language) - set(self.description)",
        "missing: set[Language] = set()",
        "test_rejects_a_broken_catalog and no_georgian_description",
    ),
    # Wiring of Flitt's inbound path.
    M(
        "http/flitt.py",
        'notification_url=f"{api_base_url}{NOTIFICATION_PATH}",',
        'notification_url=f"{api_base_url}{RETURN_PATH}",',
        "test_the_notification_url_handed_to_the_provider_reaches_the_handler",
    ),
    M(
        "main.py",
        "merchant_id=settings.flitt_merchant_id, secret_key=secret",
        'merchant_id=settings.flitt_merchant_id, secret_key="not-the-key"',
        "test_the_app_is_wired_end_to_end",
    ),
    M(
        "main.py",
        "merchant_id=settings.flitt_merchant_id, secret_key=secret",
        "merchant_id=0, secret_key=secret",
        "test_the_app_is_wired_end_to_end",
    ),
    M(
        "settings.py",
        "if unknown:",
        "if False:",
        "test_a_misspelt_environment_variable_stops_the_start",
    ),
    # Each format is booked at its own price and reads as itself at the provider.
    M(
        "app/open_booking.py",
        "price=self._catalog.offer(command.booking_format).price,",
        "price=next(iter(self._catalog.offers.values())).price,",
        "test_charges_and_names_the_format_that_was_booked",
    ),
    M(
        "app/open_booking.py",
        "description=self._catalog.offer(booking.format).description(booking.language),",
        "description=next(iter(self._catalog.offers.values())).description(booking.language),",
        "test_charges_and_names_the_format_that_was_booked",
    ),
    M(
        "app/catalog.py",
        "own[entry.starts_with or booking_format]",
        "entry.from_minor or own[booking_format]",
        "test_a_package_is_booked_at_the_price_of_the_format_it_starts_with",
    ),
    M(
        "app/catalog.py",
        "if (self.price_minor is None) == (self.starts_with is None):",
        "if False:",
        "test_rejects_a_broken_catalog and (both_prices or no_price)",
    ),
    M(
        "app/catalog.py",
        "missing = set(BookingFormat) - set(self.formats)",
        "missing: set[BookingFormat] = set()",
        "test_rejects_a_broken_catalog and drop_format",
    ),
    M(
        "app/catalog.py",
        "and self.formats[entry.starts_with].price_minor is None",
        "and False",
        "test_rejects_a_broken_catalog and starts_with_a_package",
    ),
    # HTTP edges.
    M(
        "http/flitt.py",
        "order_id = notifications.order_id_of(payload)",
        'order_id = payload["order_id"]',
        "test_a_forged_notification_is_rejected_without_touching_the_order",
    ),
    M(
        "http/flitt.py",
        "except UnknownOrderError:",
        "except Exception:",
        "test_when_the_order_cannot_be_read_flitt_is_told_to_retry",
    ),
    M(
        "http/flitt.py",
        "valid = booking is not None and re.fullmatch(BOOKING_ID_PATTERN, booking)",
        "valid = booking is not None",
        "test_a_return_without_a_valid_booking_id",
    ),
    M(
        "http/schemas.py",
        'raise ValueError("the policies must be accepted before paying")',
        "pass",
        "no-consent",
    ),
    M(
        "http/schemas.py",
        'raise ValueError("work starts right after payment, and the customer must ask for it")',
        "pass",
        "no-start-request",
    ),
    M(
        "app/open_booking.py",
        "offer_revision=self._catalog.offer_revision,",
        "offer_revision=self._catalog.offer_revision.replace(year=2000),",
        "test_records_which_revision_of_the_offer_the_customer_accepted",
    ),
    M("http/schemas.py", 'raise ValueError("rejected")', "pass", "honeypot"),
    M(
        "settings.py",
        'if not (parts.scheme == "https" or local) or not parts.hostname:',
        "if not parts.hostname:",
        "test_base_urls_must_be_https_without_a_query",
    ),
    M(
        "settings.py",
        "if parts.query or parts.fragment:",
        "if False:",
        "test_base_urls_must_be_https_without_a_query",
    ),
    # Storage on Firestore: uniqueness, concurrency and the round trip, against the emulator.
    M(
        "adapters/firestore.py",
        "if key_ref.get(transaction=transaction).exists:",
        "if False:",
        "test_one_booking_per_idempotency_key and firestore or test_twins_racing",
        marks="firestore",
    ),
    M(
        "adapters/firestore.py",
        'if _data(stored)["version"] != booking.version:',
        "if False:",
        "test_a_stale_copy_cannot_overwrite_a_newer_one and firestore",
        marks="firestore",
    ),
    M(
        "adapters/firestore.py",
        '"order_ids": [a.order_id for a in booking.attempts],',
        '"order_ids": [],',
        "test_finds_by_idempotency_key_and_order and firestore",
        marks="firestore",
    ),
    M(
        "adapters/firestore.py",
        "utc.year, utc.month, utc.day, utc.hour, utc.minute, utc.second, utc.microsecond, tzinfo=UTC",
        "utc.year, utc.month, utc.day, utc.hour, utc.minute, utc.second, 0, tzinfo=UTC",
        "test_reads_back_what_was_stored and firestore",
        marks="firestore",
    ),
    M(
        "adapters/firestore.py",
        '"expire_at": booking.discard_after,',
        '"expire_at": None,',
        "test_an_unpaid_booking_and_its_key_carry_their_deletion_date",
        marks="firestore",
    ),
    M(
        "main.py",
        'if settings.storage == "firestore":',
        "if False:",
        "test_the_app_is_wired_to_firestore",
        marks="firestore",
    ),
    M(
        "settings.py",
        'if os.environ.get("K_SERVICE") and self.storage == "memory":',
        "if False:",
        "test_memory_storage_is_refused_on_cloud_run",
    ),
    # Retention: the privacy policy keeps an unpaid booking's form 30 days, a paid one longer.
    M(
        "domain/booking.py",
        "return self.created_at + UNPAID_RETENTION if self.status in _UNPAID else None",
        "return self.created_at + UNPAID_RETENTION",
        "test_a_booking_that_took_money_is_kept",
    ),
    M(
        "domain/booking.py",
        "return self.created_at + UNPAID_RETENTION if self.status in _UNPAID else None",
        "return None",
        "test_a_booking_nobody_paid_for_goes_after_thirty_days",
    ),
]


def restore_interrupted_run() -> None:
    if BACKUP.exists():
        backup = json.loads(BACKUP.read_text(encoding="utf-8"))
        Path(backup["file"]).write_bytes(base64.b64decode(backup["original"]))
        BACKUP.unlink()
        print(f"restored {backup['file']}, left mutated by an interrupted run")


def run(selection: str, marks: str) -> tuple[int, str]:
    """Run the selected tests; return pytest's exit code and its summary line."""
    command = [
        "uv",
        "run",
        "pytest",
        "-q",
        "-p",
        "no:cacheprovider",
        "--no-header",
        "-m",
        marks,
        "-k",
        selection,
    ]
    done = subprocess.run(command, capture_output=True, text=True, check=False)
    lines = [line for line in done.stdout.splitlines() if line.strip()]
    return done.returncode, lines[-1] if lines else ""


def verdict(code: int, summary: str) -> str:
    if code == 1 and " failed" in summary and " error" not in summary:
        return "caught"
    if code == 0:
        return "SURVIVED"
    if code == 5:
        return "NO SUCH TEST"
    return f"BROKEN (exit {code})"


def main() -> int:
    restore_interrupted_run()
    if not os.environ.get("FIRESTORE_EMULATOR_HOST"):
        print("start the Firestore emulator and set FIRESTORE_EMULATOR_HOST (api/README.md)")
        return 1
    if run("not live", "not live")[0] != 0:
        print("the suite is not green without mutations; fix that first")
        return 1
    survived = []
    for number, mutation in enumerate(MUTATIONS, 1):
        original = mutation.apply()
        try:
            outcome = verdict(*run(mutation.caught_by, mutation.marks))
        finally:
            mutation.restore(original)
        print(f"{number:2} {outcome:<14} {mutation.file}: {mutation.caught_by}")
        if outcome != "caught":
            survived.append(mutation)
    print(f"{len(MUTATIONS) - len(survived)}/{len(MUTATIONS)} caught")
    return 1 if survived else 0


if __name__ == "__main__":
    sys.exit(main())
