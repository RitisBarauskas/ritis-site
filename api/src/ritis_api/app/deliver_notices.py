"""Delivering the owner notices a booking keeps: right after it changes, and in a sweep later.

At least once: a notice leaves the booking only after the messenger took it, so a crash between
the two sends it again. The sweep picks up whatever a down messenger left behind.
"""

from __future__ import annotations

import logging

from ritis_api.domain.booking import Booking
from ritis_api.ports.notifications import Notifier, NotifierError
from ritis_api.ports.storage import BookingRepository, ConcurrentModificationError

log = logging.getLogger(__name__)


class DeliverNotices:
    _SAVE_ATTEMPTS = 3
    # A sweep takes this many bookings at a time; the next run takes the rest.
    SWEEP_BATCH = 50

    def __init__(self, *, repository: BookingRepository, notifier: Notifier) -> None:
        self._repository = repository
        self._notifier = notifier

    def deliver(self, booking: Booking) -> Booking:
        sent = []
        for notice in booking.unsent_notices:
            try:
                self._notifier.send(notice, booking)
            except NotifierError as exc:
                # The messenger is down: the rest would fail the same way; the sweep retries.
                log.warning("notice for booking %s not delivered: %s", booking.id, exc)
                break
            except Exception:
                # A bug in a notifier must not fail the request that recorded the money: the
                # notice stays, and the error is in the log to be fixed.
                log.exception("notifier failed on booking %s", booking.id)
                break
            sent.append(notice)
        if not sent:
            return booking
        for _ in range(self._SAVE_ATTEMPTS):
            for notice in sent:
                booking.notice_sent(notice)
            try:
                self._repository.save(booking)
            except ConcurrentModificationError:
                booking = self._repository.get(booking.id)
                continue
            return booking
        # The notices stay recorded as unsent and go out once more: a duplicate, never a loss.
        log.warning("could not mark notices of booking %s as sent", booking.id)
        return booking

    def sweep(self) -> int:
        """Deliver what earlier attempts left; returns how many bookings still have notices."""
        left = 0
        for booking in self._repository.with_unsent_notices(self.SWEEP_BATCH):
            if self.deliver(booking).unsent_notices:
                left += 1
        return left
