from __future__ import annotations


class BookingError(Exception):
    """The requested change contradicts the booking's current state."""
