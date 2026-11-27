"""Prove that the tests can fail: break each key rule and expect its own test to catch it.

Run from api/: uv run python scripts/check_mutations.py

A mutant counts as caught only when its named test runs and fails (pytest exit code 1). A mutant
that does not import or collect is reported as broken, not as caught. Each fragment must occur
exactly once in its file, so a refactoring that moves a rule makes this script fail loudly
until the mutation is updated.
"""

from __future__ import annotations

import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

SRC = Path("src/ritis_api")


@dataclass(frozen=True)
class Mutation:
    file: str
    original: str
    mutant: str
    caught_by: str  # a pytest -k expression naming the test that must fail

    def apply(self) -> bytes:
        """Write the mutant and return the file's original bytes, to be restored as they were."""
        path = SRC / self.file
        # Bytes, not text: text mode would rewrite line endings on Windows.
        original = path.read_bytes()
        source = original.decode("utf-8")
        if source.count(self.original) != 1:
            raise SystemExit(f"{self.file}: fragment not found exactly once: {self.original!r}")
        path.write_bytes(source.replace(self.original, self.mutant).encode("utf-8"))
        return original


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
        "if booking is None or booking.attempt(order_id).provider != self._provider.name:",
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
        "now - t < self._interval",
        "True",
        "test_asks_the_provider_at_most_once_per_interval",
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
        "!= (command.booking_format, command.customer)",
        "!= (booking.format, booking.customer)",
        "test_a_key_reused_for_another_request_is_refused",
    ),
    M(
        "app/open_booking.py",
        "self._ensure_checkout(self._confirm_payment.refresh(booking_id))",
        "self._ensure_checkout(self._repository.get(booking_id))",
        "test_asks_the_provider_before_opening_another_order",
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
]


def run(selection: str) -> int:
    command = [
        "uv",
        "run",
        "pytest",
        "-q",
        "-p",
        "no:cacheprovider",
        "--no-header",
        "-k",
        selection,
    ]
    return subprocess.run(command, capture_output=True, check=False).returncode


def main() -> int:
    if run("not live") != 0:
        print("the suite is not green without mutations; fix that first")
        return 1
    survived = []
    for number, mutation in enumerate(MUTATIONS, 1):
        original = mutation.apply()
        try:
            code = run(mutation.caught_by)
        finally:
            (SRC / mutation.file).write_bytes(original)
        verdict = {1: "caught", 0: "SURVIVED", 5: "NO SUCH TEST"}.get(code, f"BROKEN (exit {code})")
        print(f"{number:2} {verdict:<14} {mutation.file}: {mutation.caught_by}")
        if code != 1:
            survived.append(mutation)
    print(f"{len(MUTATIONS) - len(survived)}/{len(MUTATIONS)} caught")
    return 1 if survived else 0


if __name__ == "__main__":
    sys.exit(main())
