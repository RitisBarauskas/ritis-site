from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from enum import StrEnum
from typing import Protocol

from ritis_api.domain.identifiers import OrderId
from ritis_api.domain.money import Money
from ritis_api.domain.payment import PaymentReport


@dataclass(frozen=True, slots=True)
class CheckoutRequest:
    order_id: OrderId
    amount: Money
    description: str
    return_url: str
    notification_url: str
    lifetime_seconds: int
    language: str
    customer_email: str | None = None


@dataclass(frozen=True, slots=True)
class Checkout:
    checkout_url: str
    provider_payment_id: str


class RefundStatus(StrEnum):
    PENDING = "pending"
    APPROVED = "approved"
    DECLINED = "declined"


class PaymentProviderError(Exception):
    """The provider failed or answered something we did not expect."""

    def __init__(self, message: str, *, code: str | None = None) -> None:
        super().__init__(message)
        self.code = code


class OrderNotFoundError(PaymentProviderError):
    """The provider has no order with this id."""


class InvalidNotificationError(Exception):
    """A notification is not from the provider or not for this merchant."""


class PaymentProvider(Protocol):
    """A card-payment provider with a hosted checkout. One adapter per provider."""

    def open_checkout(self, request: CheckoutRequest) -> Checkout: ...

    def report(self, order_id: OrderId) -> PaymentReport:
        """The order's current state, read from the provider (never from a notification)."""
        ...

    def refund(self, order_id: OrderId, amount: Money, refund_id: str) -> RefundStatus:
        """`refund_id` makes a retried refund safe: the provider applies it once."""
        ...

    def verify_notification(self, payload: Mapping[str, object]) -> OrderId:
        """Check that a notification comes from the provider and return its order id.

        Even a verified notification is only a signal to call `report`.
        """
        ...
