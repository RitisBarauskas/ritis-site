"""Test doubles. FakeProvider is held to the same contract suite as the real Flitt adapter."""

from __future__ import annotations

import itertools
from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from typing import Literal

from ritis_api.adapters.memory import InMemoryBookingRepository
from ritis_api.domain.booking import Booking, NoticeKind, OwnerNotice
from ritis_api.domain.identifiers import BookingId, OrderId
from ritis_api.domain.money import Money
from ritis_api.domain.payment import Charged, NotCharged, Outcome, PaymentReport
from ritis_api.ports.notifications import NotifierError
from ritis_api.ports.payments import (
    Checkout,
    CheckoutRequest,
    OrderNotFoundError,
    PaymentProviderError,
)

NOW = datetime(2026, 11, 27, 12, 0, tzinfo=UTC)


class Clock:
    def __init__(self) -> None:
        self.now = NOW

    def __call__(self) -> datetime:
        return self.now

    def advance(self, seconds: float) -> None:
        self.now += timedelta(seconds=seconds)


class Ids:
    """Deterministic 32-hex ids: 000…001, 000…002, …"""

    def __init__(self) -> None:
        self._counter = itertools.count(1)

    def __call__(self) -> str:
        return f"{next(self._counter):032x}"


class FakeProvider:
    """A provider whose orders the test settles, as a customer and the provider would."""

    name = "fake"

    def __init__(self) -> None:
        self.checkout_requests: list[CheckoutRequest] = []
        # Raised by open_checkout in order; any exception, to also stand for a crash.
        self.open_errors: list[Exception] = []
        # The next order is created, but its reply never reaches us (a timeout after the fact).
        self.lose_next_reply = False
        self.report_error: PaymentProviderError | None = None
        self.report_calls = 0
        self._prices: dict[OrderId, Money] = {}
        self._reports: dict[OrderId, PaymentReport] = {}

    def open_checkout(self, request: CheckoutRequest) -> Checkout:
        self.checkout_requests.append(request)
        if self.open_errors:
            raise self.open_errors.pop(0)
        if request.order_id in self._reports:
            raise PaymentProviderError(f"duplicate order {request.order_id}")
        self._prices[request.order_id] = request.amount
        self._reports[request.order_id] = NotCharged(Outcome.PENDING)
        if self.lose_next_reply:
            self.lose_next_reply = False
            raise PaymentProviderError("timeout: the order was created, the reply was lost")
        return Checkout(
            checkout_url=f"https://pay.example/{request.order_id}",
            provider_payment_id=f"pay-{request.order_id}",
        )

    def report(self, order_id: OrderId) -> PaymentReport:
        self.report_calls += 1
        if self.report_error is not None:
            raise self.report_error
        if order_id not in self._reports:
            raise OrderNotFoundError(order_id)
        return self._reports[order_id]

    # --- what happens on the provider's side -------------------------------------------------

    def approve(self, order_id: OrderId, charged: Money | None = None) -> None:
        self._still_open(order_id)
        amount = charged or self._prices[order_id]
        self._reports[order_id] = Charged(amount, Money.zero(amount.currency))

    def decline(self, order_id: OrderId) -> None:
        self._still_open(order_id)
        self._reports[order_id] = NotCharged(Outcome.DECLINED)

    def expire(self, order_id: OrderId) -> None:
        self._still_open(order_id)
        self._reports[order_id] = NotCharged(Outcome.EXPIRED)

    def _still_open(self, order_id: OrderId) -> None:
        # The port's contract: one checkout is one try, a settled order never changes outcome.
        assert self._reports[order_id] == NotCharged(Outcome.PENDING), f"{order_id} is settled"

    def refund(self, order_id: OrderId, amount: Money) -> None:
        """A refund made in the provider's merchant portal."""
        current = self._reports[order_id]
        assert isinstance(current, Charged)
        self._reports[order_id] = Charged(current.amount, current.refunded + amount)


class RacingRepository:
    """A real repository that lets a competitor write first, once, right before our write.

    Nothing is faked about the conflict: the competitor's write moves the stored version or
    takes the idempotency key, and the inner repository refuses ours as a database would.
    """

    def __init__(
        self,
        inner: InMemoryBookingRepository,
        competitor: Callable[[], object],
        *,
        race_on: Literal["add", "save"],
    ) -> None:
        self._inner = inner
        self._competitor = competitor
        self._race_on = race_on
        self.raced = False

    def add(self, booking: Booking) -> None:
        if self._race_on == "add":
            self._race()
        self._inner.add(booking)

    def save(self, booking: Booking) -> None:
        if self._race_on == "save":
            self._race()
        self._inner.save(booking)

    def get(self, booking_id: BookingId) -> Booking:
        return self._inner.get(booking_id)

    def find_by_idempotency_key(self, key: str) -> Booking | None:
        return self._inner.find_by_idempotency_key(key)

    def find_by_order_id(self, order_id: OrderId) -> Booking | None:
        return self._inner.find_by_order_id(order_id)

    def with_unsent_notices(self, limit: int) -> list[Booking]:
        return self._inner.with_unsent_notices(limit)

    def _race(self) -> None:
        if not self.raced:
            self.raced = True
            self._competitor()


class RecordingNotifier:
    """Records what the owner was told; `broken` makes the messenger refuse every message."""

    def __init__(self) -> None:
        self.paid: list[str] = []
        self.review: list[str] = []
        self.broken = False

    def send(self, notice: OwnerNotice, booking: Booking) -> None:
        if self.broken:
            raise NotifierError("messenger is down")
        match notice.kind:
            case NoticeKind.PAID:
                self.paid.append(booking.id)
            case NoticeKind.NEEDS_REVIEW:
                self.review.append(booking.id)
