from __future__ import annotations

from typing import Protocol

from ritis_api.domain.booking import Booking
from ritis_api.domain.identifiers import BookingId, OrderId


class BookingNotFoundError(Exception):
    pass


class DuplicateIdempotencyKeyError(Exception):
    """Another booking was created with the same idempotency key in the meantime."""


class ConcurrentModificationError(Exception):
    """The booking changed since it was read; re-read it and apply the change again."""


class BookingRepository(Protocol):
    def add(self, booking: Booking) -> None:
        """Store a new booking. Raises DuplicateIdempotencyKeyError if the key is taken."""
        ...

    def get(self, booking_id: BookingId) -> Booking:
        """Raises BookingNotFoundError."""
        ...

    def find_by_idempotency_key(self, key: str) -> Booking | None: ...

    def find_by_order_id(self, order_id: OrderId) -> Booking | None: ...

    def save(self, booking: Booking) -> None:
        """Store changes if nobody saved this booking since it was read.

        Raises ConcurrentModificationError otherwise. On success bumps `booking.version`.
        """
        ...
