"""What a payment provider reports about an order, and one payment attempt of a booking."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum

from ritis_api.domain.identifiers import OrderId
from ritis_api.domain.money import Money


class Outcome(StrEnum):
    PENDING = "pending"
    DECLINED = "declined"
    EXPIRED = "expired"


@dataclass(frozen=True, slots=True)
class NotCharged:
    """The provider has taken no money on the order: not yet, or not at all."""

    outcome: Outcome


@dataclass(frozen=True, slots=True)
class Charged:
    """The provider took `amount`; `refunded` is everything returned since, in total."""

    amount: Money
    refunded: Money

    def __post_init__(self) -> None:
        if self.refunded.currency is not self.amount.currency:
            raise ValueError(
                f"refund in {self.refunded.currency} of a charge in {self.amount.currency}"
            )


# The provider is the source of truth about money; a report is what it says right now.
PaymentReport = NotCharged | Charged


class AttemptStatus(StrEnum):
    PENDING = "pending"
    APPROVED = "approved"
    DECLINED = "declined"
    EXPIRED = "expired"
    # The provider never handed out a checkout for this attempt.
    FAILED = "failed"


@dataclass(slots=True)
class PaymentAttempt:
    """One order at one provider, made for one booking."""

    order_id: OrderId
    provider: str
    price: Money
    created_at: datetime
    status: AttemptStatus = AttemptStatus.PENDING
    # As the provider reports them; may differ from `price`, which is then a case for a human.
    charged: Money | None = None
    refunded: Money | None = None
    checkout_url: str | None = None
    # For finding the payment in the provider's merchant portal.
    provider_payment_id: str | None = None

    @property
    def is_open(self) -> bool:
        """A checkout exists and the customer can still pay through it."""
        return self.status is AttemptStatus.PENDING and self.checkout_url is not None

    @property
    def refunded_in_full(self) -> bool:
        return self.charged is not None and self.refunded == self.charged
