from __future__ import annotations

import logging

from ritis_api.domain.booking import Booking, NoticeKind, OwnerNotice

log = logging.getLogger(__name__)


class LoggingNotifier:
    """For running locally without a messenger: writes to the log, without personal data."""

    def send(self, notice: OwnerNotice, booking: Booking) -> None:
        match notice.kind:
            case NoticeKind.PAID:
                log.info(
                    "booking paid: id=%s format=%s price=%s",
                    booking.id,
                    booking.format,
                    booking.price,
                )
            case NoticeKind.NEEDS_REVIEW:
                log.error("booking needs review: id=%s reason=%s", booking.id, notice.reason)
