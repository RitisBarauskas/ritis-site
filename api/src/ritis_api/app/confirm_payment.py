"""Recording what the provider says about an order.

Every trigger ends here: the provider's notification, the customer's booking page asking, a
retry. Repeating a confirmation is harmless.
"""

from __future__ import annotations

import logging
import threading
from datetime import datetime, timedelta

from ritis_api.app.runtime import Clock
from ritis_api.domain.booking import Booking, BookingStatus
from ritis_api.domain.identifiers import BookingId, OrderId
from ritis_api.domain.payment import PaymentAttempt
from ritis_api.ports.notifications import Notifier
from ritis_api.ports.payments import PaymentProvider, PaymentProviderError
from ritis_api.ports.storage import BookingRepository, ConcurrentModificationError

log = logging.getLogger(__name__)


class UnknownOrderError(Exception):
    """An order that no booking of ours made with this provider."""


class ConfirmPayment:
    _SAVE_ATTEMPTS = 3

    def __init__(
        self,
        *,
        repository: BookingRepository,
        provider: PaymentProvider,
        notifier: Notifier,
        clock: Clock,
        recheck_interval: timedelta,
    ) -> None:
        self._repository = repository
        self._provider = provider
        self._notifier = notifier
        self._clock = clock
        self._rechecks = _RecheckGate(clock, recheck_interval)

    def confirm(self, order_id: OrderId) -> Booking:
        booking = self._repository.find_by_order_id(order_id)
        if booking is None or not self._holds(booking.attempt(order_id)):
            raise UnknownOrderError(order_id)
        return self._settle(booking, order_id)

    def refresh(self, booking_id: BookingId) -> Booking:
        """Re-check the open payment of a booking, at most once per interval per order.

        The booking page polls this; the provider's notification remains the main path.
        """
        booking = self._repository.get(booking_id)
        attempt = booking.current_attempt
        if booking.status is not BookingStatus.AWAITING_PAYMENT or not (
            attempt and attempt.is_open and self._holds(attempt)
        ):
            return booking
        if not self._rechecks.admit(attempt.order_id):
            return booking
        try:
            return self._settle(booking, attempt.order_id)
        except PaymentProviderError:
            log.warning("could not re-check order %s", attempt.order_id, exc_info=True)
            return booking

    def _holds(self, attempt: PaymentAttempt) -> bool:
        """Only the provider that holds an order may settle it."""
        return attempt.provider == self._provider.name

    def _settle(self, booking: Booking, order_id: OrderId) -> Booking:
        report = self._provider.report(order_id)
        for _ in range(self._SAVE_ATTEMPTS):
            before = (booking.status, booking.review_reason)
            if not booking.apply_report(order_id, report, self._clock()):
                return booking
            try:
                self._repository.save(booking)
            except ConcurrentModificationError:
                # Someone else changed the booking; apply the same report to their version.
                booking = self._repository.get(booking.id)
                continue
            self._announce(*before, booking)
            return booking
        raise ConcurrentModificationError(booking.id)

    def _announce(self, status: BookingStatus, reason: str | None, booking: Booking) -> None:
        # A failed notification must not undo a recorded payment. Guaranteed delivery (an
        # outbox) arrives with the Telegram notifier.
        try:
            if booking.status is BookingStatus.PAID and status is not BookingStatus.PAID:
                self._notifier.booking_paid(booking)
            elif booking.status is BookingStatus.NEEDS_REVIEW and booking.review_reason != reason:
                self._notifier.booking_needs_review(booking)
        except Exception:
            log.exception("notification failed for booking %s", booking.id)


class _RecheckGate:
    """Lets one provider read per order through per interval, within this process.

    Polling pages share the request thread pool with the provider's notifications; without the
    gate a page polling fast turns into as many signed calls to the provider.
    """

    def __init__(self, clock: Clock, interval: timedelta) -> None:
        self._clock = clock
        self._interval = interval
        self._lock = threading.Lock()
        self._last: dict[OrderId, datetime] = {}

    def admit(self, order_id: OrderId) -> bool:
        now = self._clock()
        with self._lock:
            # A clock set back must not lock re-checks out: a read "from the future" has expired.
            self._last = {
                o: t for o, t in self._last.items() if timedelta(0) <= now - t < self._interval
            }
            if order_id in self._last:
                return False
            self._last[order_id] = now
            return True
