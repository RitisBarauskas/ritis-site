from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum

from ritis_api.domain.identifiers import OrderId
from ritis_api.domain.money import Money


class PaymentState(StrEnum):
    """An order's state as the payment provider reports it."""

    PENDING = "pending"
    APPROVED = "approved"
    DECLINED = "declined"
    EXPIRED = "expired"
    # Approved, then refunded in full.
    REVERSED = "reversed"


@dataclass(frozen=True, slots=True)
class PaymentReport:
    """What the provider says about one order right now. The provider is the source of truth."""

    state: PaymentState
    charged: Money | None = None
    # Cumulative: everything refunded on this order so far.
    refunded: Money | None = None

    def __post_init__(self) -> None:
        took_money = self.state in {PaymentState.APPROVED, PaymentState.REVERSED}
        if took_money and self.charged is None:
            raise ValueError(f"a {self.state} report must say how much was charged")
        if not took_money and (self.charged is not None or self.refunded is not None):
            raise ValueError(f"a {self.state} report cannot carry amounts")

    @property
    def refunded_total(self) -> Money | None:
        if self.refunded is not None:
            return self.refunded
        # A full reversal may come without the amount; it then equals the charge.
        return self.charged if self.state is PaymentState.REVERSED else None


class AttemptStatus(StrEnum):
    PENDING = "pending"
    APPROVED = "approved"
    DECLINED = "declined"
    EXPIRED = "expired"
    # The provider never opened a checkout for this attempt (an error or a duplicate order id).
    FAILED = "failed"


@dataclass(slots=True)
class PaymentAttempt:
    """One order at the payment provider, made for one booking."""

    order_id: OrderId
    amount: Money
    refunded: Money
    created_at: datetime
    status: AttemptStatus = AttemptStatus.PENDING
    checkout_url: str | None = None
    provider_payment_id: str | None = None

    @property
    def is_open(self) -> bool:
        """A checkout exists and the customer can still pay through it."""
        return self.status is AttemptStatus.PENDING and self.checkout_url is not None

    @property
    def refundable(self) -> Money:
        if self.status is not AttemptStatus.APPROVED:
            return Money.zero(self.amount.currency)
        return self.amount - self.refunded
