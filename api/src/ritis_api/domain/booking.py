"""A paid booking of a call: the aggregate that owns its payment attempts.

The payment provider is the source of truth about money. The booking applies the provider's
reports, refuses contradictions and flags what it cannot reconcile on its own (a wrong amount,
a second successful payment) for a human, instead of guessing.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass, field
from datetime import datetime
from enum import StrEnum

from ritis_api.domain.errors import BookingError
from ritis_api.domain.identifiers import BookingId, OrderId
from ritis_api.domain.money import Money
from ritis_api.domain.payment import AttemptStatus, PaymentAttempt, PaymentReport, PaymentState


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


@dataclass(frozen=True, slots=True)
class RefundPlan:
    order_id: OrderId
    amount: Money


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

    @property
    def paid(self) -> Money:
        return self._sum(a.amount for a in self.attempts if a.status is AttemptStatus.APPROVED)

    @property
    def refunded(self) -> Money:
        return self._sum(a.refunded for a in self.attempts)

    def attempt(self, order_id: OrderId) -> PaymentAttempt:
        for attempt in self.attempts:
            if attempt.order_id == order_id:
                return attempt
        raise BookingError(f"booking {self.id} has no payment attempt {order_id}")

    # --- commands ------------------------------------------------------------------------

    def start_attempt(self, order_id: OrderId, now: datetime) -> PaymentAttempt:
        if not self.can_retry_payment:
            raise BookingError(f"cannot start a payment for booking {self.id} in {self.status}")
        attempt = PaymentAttempt(
            order_id=order_id,
            amount=self.price,
            refunded=Money.zero(self.price.currency),
            created_at=now,
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
        """Apply the provider's report on one order. Returns False when nothing changed."""
        match report.state:
            case PaymentState.PENDING:
                return False
            case PaymentState.DECLINED:
                return self._record_failure(
                    order_id, AttemptStatus.DECLINED, BookingStatus.DECLINED
                )
            case PaymentState.EXPIRED:
                return self._record_failure(order_id, AttemptStatus.EXPIRED, BookingStatus.EXPIRED)
            case PaymentState.APPROVED | PaymentState.REVERSED:
                return self._record_charge(order_id, report, now)

    def plan_refund(self, amount: Money | None = None) -> RefundPlan:
        """Which order to refund and by how much: the latest paid one, in full by default."""
        attempt = next((a for a in reversed(self.attempts) if a.refundable.amount_minor), None)
        if attempt is None:
            raise BookingError(f"booking {self.id} has nothing left to refund")
        to_refund = attempt.refundable if amount is None else amount
        if to_refund.amount_minor <= 0 or attempt.refundable < to_refund:
            raise BookingError(f"cannot refund {to_refund}: {attempt.refundable} left")
        return RefundPlan(order_id=attempt.order_id, amount=to_refund)

    # --- rules ---------------------------------------------------------------------------

    def _record_charge(self, order_id: OrderId, report: PaymentReport, now: datetime) -> bool:
        if (
            report.charged is None
        ):  # PaymentReport forbids it; checked so it can never pass silently
            raise BookingError(f"order {order_id}: {report.state} report without an amount")
        changed = self._record_approved(order_id, report.charged, now)
        refunded = report.refunded_total
        if refunded is not None and refunded.amount_minor > 0:
            changed |= self._record_refunded_total(order_id, refunded)
        return changed

    def _awaiting_checkout(self, order_id: OrderId) -> PaymentAttempt:
        attempt = self.attempt(order_id)
        if attempt.status is not AttemptStatus.PENDING or attempt.checkout_url is not None:
            raise BookingError(f"attempt {order_id} is not waiting for a checkout")
        return attempt

    def _record_approved(self, order_id: OrderId, charged: Money, now: datetime) -> bool:
        attempt = self.attempt(order_id)
        if attempt.status is AttemptStatus.APPROVED:
            return False
        paid_before = self.status in _SETTLED
        attempt.status = AttemptStatus.APPROVED
        if charged != attempt.amount:
            self._flag(f"order {order_id}: charged {charged}, expected {attempt.amount}")
        elif paid_before:
            self._flag(f"order {order_id}: a second successful payment for one booking")
        elif self.status is not BookingStatus.NEEDS_REVIEW:
            self.status = BookingStatus.PAID
            self.paid_at = now
        return True

    def _record_failure(
        self, order_id: OrderId, attempt_status: AttemptStatus, booking_status: BookingStatus
    ) -> bool:
        attempt = self.attempt(order_id)
        # Approval is final: a later failure for the same order is a stale report.
        if attempt.status in {attempt_status, AttemptStatus.APPROVED}:
            return False
        attempt.status = attempt_status
        if self.status is BookingStatus.AWAITING_PAYMENT and attempt is self.current_attempt:
            self.status = booking_status
        return True

    def _record_refunded_total(self, order_id: OrderId, refunded_total: Money) -> bool:
        # Totals only grow, so a repeated report is harmless and a stale one is ignored.
        attempt = self.attempt(order_id)
        if refunded_total <= attempt.refunded:
            return False
        if attempt.amount < refunded_total:
            raise BookingError(f"order {order_id}: refunded {refunded_total} of {attempt.amount}")
        attempt.refunded = refunded_total
        if self.status is BookingStatus.PAID and self.refunded == self.paid:
            self.status = BookingStatus.REFUNDED
        return True

    def _flag(self, reason: str) -> None:
        self.status = BookingStatus.NEEDS_REVIEW
        self.review_reason = (
            reason if self.review_reason is None else f"{self.review_reason}; {reason}"
        )

    def _sum(self, amounts: Iterable[Money]) -> Money:
        total = Money.zero(self.price.currency)
        for amount in amounts:
            total += amount
        return total
