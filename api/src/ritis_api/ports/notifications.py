from __future__ import annotations

from typing import Protocol

from ritis_api.domain.booking import Booking


class Notifier(Protocol):
    """Tells the owner about bookings that need a human."""

    def booking_paid(self, booking: Booking) -> None: ...

    def booking_needs_review(self, booking: Booking) -> None: ...
