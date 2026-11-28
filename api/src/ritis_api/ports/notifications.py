from __future__ import annotations

from typing import Protocol

from ritis_api.domain.booking import Booking, OwnerNotice


class NotifierError(Exception):
    """The messenger did not take the message; the notice stays unsent and is tried again."""


class Notifier(Protocol):
    """Tells the owner about bookings that need a human."""

    def send(self, notice: OwnerNotice, booking: Booking) -> None:
        """Deliver the notice, or raise NotifierError."""
        ...
