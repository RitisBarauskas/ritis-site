"""Test doubles that honour the port contracts."""

from __future__ import annotations

import itertools
from collections.abc import Mapping
from datetime import UTC, datetime

from ritis_api.domain.booking import Booking
from ritis_api.domain.identifiers import OrderId
from ritis_api.domain.money import Money
from ritis_api.domain.payment import PaymentReport, PaymentState
from ritis_api.ports.payments import (
    Checkout,
    CheckoutRequest,
    InvalidNotificationError,
    OrderNotFoundError,
    PaymentProviderError,
    RefundStatus,
)

NOW = datetime(2026, 11, 27, 12, 0, tzinfo=UTC)


class Ids:
    """Deterministic 32-hex ids: 000…001, 000…002, …"""

    def __init__(self) -> None:
        self._counter = itertools.count(1)

    def __call__(self) -> str:
        return f"{next(self._counter):032x}"


class FakeProvider:
    """A provider whose order book the test controls."""

    def __init__(self) -> None:
        self.checkout_requests: list[CheckoutRequest] = []
        # Raised by open_checkout in order; any exception, to also stand for a crash.
        self.open_errors: list[Exception] = []
        self.report_error: PaymentProviderError | None = None
        self.report_calls = 0
        self.refund_calls: list[tuple[OrderId, Money, str]] = []
        self.refund_status = RefundStatus.APPROVED
        self._amounts: dict[OrderId, Money] = {}
        self._reports: dict[OrderId, PaymentReport] = {}

    # --- port --------------------------------------------------------------------------------

    def open_checkout(self, request: CheckoutRequest) -> Checkout:
        self.checkout_requests.append(request)
        if self.open_errors:
            raise self.open_errors.pop(0)
        self._amounts[request.order_id] = request.amount
        self._reports[request.order_id] = PaymentReport(PaymentState.PENDING)
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

    def refund(self, order_id: OrderId, amount: Money, refund_id: str) -> RefundStatus:
        self.refund_calls.append((order_id, amount, refund_id))
        if self.refund_status is RefundStatus.APPROVED:
            current = self._reports[order_id]
            assert current.charged is not None
            total = (current.refunded or Money.zero(amount.currency)) + amount
            state = PaymentState.REVERSED if total == current.charged else current.state
            self._reports[order_id] = PaymentReport(state, current.charged, total)
        return self.refund_status

    def verify_notification(self, payload: Mapping[str, object]) -> OrderId:
        if payload.get("signature") != "valid":
            raise InvalidNotificationError("bad signature")
        return OrderId(str(payload["order_id"]))

    # --- what the provider would do on its side ----------------------------------------------

    def approve(self, order_id: OrderId, charged: Money | None = None) -> None:
        self._reports[order_id] = PaymentReport(
            PaymentState.APPROVED, charged or self._amounts[order_id], None
        )

    def decline(self, order_id: OrderId) -> None:
        self._reports[order_id] = PaymentReport(PaymentState.DECLINED)

    def expire(self, order_id: OrderId) -> None:
        self._reports[order_id] = PaymentReport(PaymentState.EXPIRED)

    def reverse_in_portal(self, order_id: OrderId) -> None:
        charged = self._amounts[order_id]
        self._reports[order_id] = PaymentReport(PaymentState.REVERSED, charged, charged)


class RecordingNotifier:
    def __init__(self) -> None:
        self.paid: list[str] = []
        self.review: list[str] = []
        self.broken = False

    def booking_paid(self, booking: Booking) -> None:
        if self.broken:
            raise RuntimeError("notifier is down")
        self.paid.append(booking.id)

    def booking_needs_review(self, booking: Booking) -> None:
        self.review.append(booking.id)
