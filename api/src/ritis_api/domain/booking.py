"""A paid booking of a call: the aggregate that owns its payment attempts.

The provider is the source of truth about money. The booking records what it reports and,
when the report contradicts the booking (another amount, another currency, a second payment,
a refund above the charge), flags it for a human instead of guessing. A flag is never cleared
automatically.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import StrEnum

from ritis_api.domain.errors import BookingError
from ritis_api.domain.identifiers import BookingId, OrderId
from ritis_api.domain.money import Money
from ritis_api.domain.payment import (
    AttemptStatus,
    Charged,
    NotCharged,
    Outcome,
    PaymentAttempt,
    PaymentReport,
)


class BookingFormat(StrEnum):
    """Paid formats. Every one of them starts with the same paid call."""

    SESSION = "session"
    FOUNDATION = "foundation"
    CHECKUP = "checkup"
    SUPPORT = "support"


class BookingStatus(StrEnum):
    AWAITING_PAYMENT = "awaiting_payment"
    PAID = "paid"
    DECLINED = "declined"
    EXPIRED = "expired"
    REFUNDED = "refunded"
    NEEDS_REVIEW = "needs_review"


_RETRYABLE = frozenset(
    {BookingStatus.AWAITING_PAYMENT, BookingStatus.DECLINED, BookingStatus.EXPIRED}
)
_SETTLED = frozenset({BookingStatus.PAID, BookingStatus.REFUNDED})


@dataclass(frozen=True, slots=True)
class Customer:
    name: str
    contact: str
    about: str
    links: str


@dataclass(slots=True)
class Booking:
    id: BookingId
    idempotency_key: str
    format: BookingFormat
    customer: Customer
    price: Money
    created_at: datetime
    status: BookingStatus = BookingStatus.AWAITING_PAYMENT
    attempts: list[PaymentAttempt] = field(default_factory=list)
    paid_at: datetime | None = None
    review_reason: str | None = None
    # Optimistic-concurrency token, owned by the repository.
    version: int = 0

    @classmethod
    def new(
        cls,
        *,
        booking_id: BookingId,
        idempotency_key: str,
        booking_format: BookingFormat,
        customer: Customer,
        price: Money,
        now: datetime,
    ) -> Booking:
        return cls(
            id=booking_id,
            idempotency_key=idempotency_key,
            format=booking_format,
            customer=customer,
            price=price,
            created_at=now,
        )

    # --- queries -------------------------------------------------------------------------

    @property
    def current_attempt(self) -> PaymentAttempt | None:
        return self.attempts[-1] if self.attempts else None

    @property
    def open_checkout_url(self) -> str | None:
        """Where the customer can still pay, if a checkout is open."""
        attempt = self.current_attempt
        if self.status is BookingStatus.AWAITING_PAYMENT and attempt and attempt.is_open:
            return attempt.checkout_url
        return None

    @property
    def can_retry_payment(self) -> bool:
        attempt = self.current_attempt
        return self.status in _RETRYABLE and (
            attempt is None or attempt.status is not AttemptStatus.PENDING
        )

    def attempt(self, order_id: OrderId) -> PaymentAttempt:
        for attempt in self.attempts:
            if attempt.order_id == order_id:
                return attempt
        raise BookingError(f"booking {self.id} has no payment attempt {order_id}")

    # --- commands ------------------------------------------------------------------------

    def start_attempt(self, order_id: OrderId, provider: str, now: datetime) -> PaymentAttempt:
        if not self.can_retry_payment:
            raise BookingError(f"cannot start a payment for booking {self.id} in {self.status}")
        attempt = PaymentAttempt(
            order_id=order_id, provider=provider, price=self.price, created_at=now
        )
        self.attempts.append(attempt)
        self.status = BookingStatus.AWAITING_PAYMENT
        return attempt

    def attach_checkout(
        self, order_id: OrderId, checkout_url: str, provider_payment_id: str
    ) -> None:
        attempt = self._awaiting_checkout(order_id)
        attempt.checkout_url = checkout_url
        attempt.provider_payment_id = provider_payment_id

    def mark_checkout_failed(self, order_id: OrderId) -> None:
        self._awaiting_checkout(order_id).status = AttemptStatus.FAILED

    def apply_report(self, order_id: OrderId, report: PaymentReport, now: datetime) -> bool:
        """Record what the provider says about one order. Returns False when nothing changed."""
        attempt = self.attempt(order_id)
        if isinstance(report, Charged):
            changed = self._record_charge(attempt, report.amount, now)
            return self._record_refund(attempt, report.refunded) or changed
        return self._record_not_charged(attempt, report)

    # --- rules ---------------------------------------------------------------------------

    def _awaiting_checkout(self, order_id: OrderId) -> PaymentAttempt:
        attempt = self.attempt(order_id)
        if attempt.status is not AttemptStatus.PENDING or attempt.checkout_url is not None:
            raise BookingError(f"attempt {order_id} is not waiting for a checkout")
        return attempt

    def _record_charge(self, attempt: PaymentAttempt, amount: Money, now: datetime) -> bool:
        if attempt.status is AttemptStatus.APPROVED:
            if attempt.charged == amount:
                return False
            self._flag(
                f"order {attempt.order_id}: charge changed from {attempt.charged} to {amount}"
            )
            attempt.charged = amount
            return True
        settled_before = self.status in _SETTLED
        attempt.status = AttemptStatus.APPROVED
        attempt.charged = amount
        if amount != attempt.price:
            self._flag(f"order {attempt.order_id}: charged {amount}, expected {attempt.price}")
        elif settled_before:
            self._flag(f"order {attempt.order_id}: a second successful payment for one booking")
        elif self.status is BookingStatus.NEEDS_REVIEW:
            self._flag(f"order {attempt.order_id}: another successful payment")
        else:
            self.status = BookingStatus.PAID
            self.paid_at = now
        return True

    def _record_refund(self, attempt: PaymentAttempt, refunded: Money) -> bool:
        previous = attempt.refunded
        if previous is None and refunded.amount_minor == 0:
            return False
        if previous is not None and previous.currency is refunded.currency and refunded <= previous:
            # Totals only grow: a repeat changes nothing and a smaller one is a stale report.
            return False
        attempt.refunded = refunded
        charged = attempt.charged
        if charged is None or charged.currency is not refunded.currency or charged < refunded:
            self._flag(f"order {attempt.order_id}: refunded {refunded} of {charged}")
        elif self.status is BookingStatus.PAID and self._everything_refunded():
            self.status = BookingStatus.REFUNDED
        return True

    def _record_not_charged(self, attempt: PaymentAttempt, report: NotCharged) -> bool:
        match report.outcome:
            case Outcome.PENDING:
                return False
            case Outcome.DECLINED:
                return self._record_failure(attempt, AttemptStatus.DECLINED, BookingStatus.DECLINED)
            case Outcome.EXPIRED:
                return self._record_failure(attempt, AttemptStatus.EXPIRED, BookingStatus.EXPIRED)

    def _record_failure(
        self, attempt: PaymentAttempt, attempt_status: AttemptStatus, booking_status: BookingStatus
    ) -> bool:
        # Approval is final: a later failure for the same order is a stale report.
        if attempt.status in {attempt_status, AttemptStatus.APPROVED}:
            return False
        attempt.status = attempt_status
        if self.status is BookingStatus.AWAITING_PAYMENT and attempt is self.current_attempt:
            self.status = booking_status
        return True

    def _everything_refunded(self) -> bool:
        approved = [a for a in self.attempts if a.status is AttemptStatus.APPROVED]
        return bool(approved) and all(a.refunded_in_full for a in approved)

    def _flag(self, reason: str) -> None:
        self.status = BookingStatus.NEEDS_REVIEW
        self.review_reason = (
            reason if self.review_reason is None else f"{self.review_reason}; {reason}"
        )
