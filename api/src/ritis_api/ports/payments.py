from __future__ import annotations

from dataclasses import dataclass
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


class PaymentProviderError(Exception):
    """The provider failed or answered something we cannot use."""


class OrderNotFoundError(PaymentProviderError):
    """The provider has no order with this id."""


class PaymentProvider(Protocol):
    """A card-payment provider with a hosted checkout page.

    One checkout is one try: once the order is declined or expired it stays so, and paying
    again takes a new order. Adapters configure their provider to behave this way.
    """

    @property
    def name(self) -> str:
        """Stored on every attempt: an order is settled only with the provider that holds it."""
        ...

    def open_checkout(self, request: CheckoutRequest) -> Checkout: ...

    def report(self, order_id: OrderId) -> PaymentReport:
        """What the provider says about the order now, read from the provider itself."""
        ...
