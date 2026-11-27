from __future__ import annotations

from ritis_api.app.confirm_payment import ConfirmPayment
from ritis_api.domain.booking import Booking
from ritis_api.domain.identifiers import BookingId
from ritis_api.domain.money import Money
from ritis_api.ports.payments import PaymentProvider, RefundStatus
from ritis_api.ports.storage import BookingRepository


class RefundDeclinedError(Exception):
    pass


class RefundBooking:
    """Refund a paid booking, then record the provider's new totals."""

    def __init__(
        self,
        *,
        repository: BookingRepository,
        provider: PaymentProvider,
        confirm: ConfirmPayment,
    ) -> None:
        self._repository = repository
        self._provider = provider
        self._confirm = confirm

    def refund(
        self, booking_id: BookingId, *, refund_id: str, amount: Money | None = None
    ) -> Booking:
        """`refund_id` comes from the caller: retrying with the same id refunds once."""
        plan = self._repository.get(booking_id).plan_refund(amount)
        status = self._provider.refund(plan.order_id, plan.amount, refund_id)
        if status is RefundStatus.DECLINED:
            raise RefundDeclinedError(f"the provider declined refund {refund_id}")
        return self._confirm.confirm(plan.order_id)
