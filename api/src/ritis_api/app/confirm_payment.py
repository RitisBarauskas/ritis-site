"""Recording what the provider says about an order.

Every trigger ends here: the provider's notification, the customer coming back from the
checkout, later a scheduled reconciliation. Repeating a confirmation is harmless.
"""

from __future__ import annotations

import logging

from ritis_api.app.runtime import Clock
from ritis_api.domain.booking import Booking, BookingStatus
from ritis_api.domain.identifiers import BookingId, OrderId
from ritis_api.ports.notifications import Notifier
from ritis_api.ports.payments import PaymentProvider, PaymentProviderError
from ritis_api.ports.storage import BookingRepository, ConcurrentModificationError

log = logging.getLogger(__name__)


class UnknownOrderError(Exception):
    """A provider order that none of our bookings knows about."""


class ConfirmPayment:
    _SAVE_ATTEMPTS = 3

    def __init__(
        self,
        *,
        repository: BookingRepository,
        provider: PaymentProvider,
        notifier: Notifier,
        clock: Clock,
    ) -> None:
        self._repository = repository
        self._provider = provider
        self._notifier = notifier
        self._clock = clock

    def confirm(self, order_id: OrderId) -> Booking:
        booking = self._repository.find_by_order_id(order_id)
        if booking is None:
            raise UnknownOrderError(order_id)
        report = self._provider.report(order_id)
        for _ in range(self._SAVE_ATTEMPTS):
            before = booking.status
            if not booking.apply_report(order_id, report, self._clock()):
                return booking
            try:
                self._repository.save(booking)
            except ConcurrentModificationError:
                # Someone else changed the booking; apply the same report to their version.
                booking = self._repository.get(booking.id)
                continue
            self._announce(before, booking)
            return booking
        raise ConcurrentModificationError(booking.id)

    def refresh(self, booking_id: BookingId) -> Booking:
        """The customer is back from the checkout: re-check the open payment, if there is one."""
        booking = self._repository.get(booking_id)
        attempt = booking.current_attempt
        if booking.status is not BookingStatus.AWAITING_PAYMENT or not (
            attempt and attempt.is_open
        ):
            return booking
        try:
            return self.confirm(attempt.order_id)
        except PaymentProviderError:
            # The page shows "still checking"; the provider's notification will settle it.
            log.warning("could not re-check order %s", attempt.order_id, exc_info=True)
            return booking

    def _announce(self, before: BookingStatus, booking: Booking) -> None:
        # A failed notification must not undo a recorded payment. Guaranteed delivery (an
        # outbox) arrives with the Telegram notifier.
        try:
            if booking.status is BookingStatus.PAID and before is not BookingStatus.PAID:
                self._notifier.booking_paid(booking)
            elif (
                booking.status is BookingStatus.NEEDS_REVIEW
                and before is not BookingStatus.NEEDS_REVIEW
            ):
                self._notifier.booking_needs_review(booking)
        except Exception:
            log.exception("notification failed for booking %s", booking.id)
