from __future__ import annotations

import logging

from ritis_api.domain.booking import Booking

log = logging.getLogger(__name__)


class LoggingNotifier:
    """Stand-in until the Telegram notifier: writes to the log, without personal data."""

    def booking_paid(self, booking: Booking) -> None:
        log.info(
            "booking paid: id=%s format=%s price=%s", booking.id, booking.format, booking.price
        )

    def booking_needs_review(self, booking: Booking) -> None:
        log.error("booking needs review: id=%s reason=%s", booking.id, booking.review_reason)
