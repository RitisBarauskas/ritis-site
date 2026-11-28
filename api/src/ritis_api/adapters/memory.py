from __future__ import annotations

import copy
import threading
from collections.abc import Callable

from ritis_api.domain.booking import Booking
from ritis_api.domain.identifiers import BookingId, OrderId
from ritis_api.ports.storage import (
    BookingNotFoundError,
    ConcurrentModificationError,
    DuplicateIdempotencyKeyError,
)


class InMemoryBookingRepository:
    """BookingRepository in process memory, for tests and local development.

    It hands out copies, as a database would, so a forgotten `save` shows up in tests.
    Not for Cloud Run: instances do not share memory.
    """

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._bookings: dict[BookingId, Booking] = {}

    def add(self, booking: Booking) -> None:
        with self._lock:
            if self._find(lambda b: b.idempotency_key == booking.idempotency_key):
                raise DuplicateIdempotencyKeyError(booking.idempotency_key)
            if booking.id in self._bookings:
                raise ValueError(f"booking {booking.id} already exists")
            booking.version = 1
            self._bookings[booking.id] = copy.deepcopy(booking)

    def get(self, booking_id: BookingId) -> Booking:
        with self._lock:
            if booking_id not in self._bookings:
                raise BookingNotFoundError(booking_id)
            return copy.deepcopy(self._bookings[booking_id])

    def find_by_idempotency_key(self, key: str) -> Booking | None:
        with self._lock:
            return self._find(lambda b: b.idempotency_key == key)

    def find_by_order_id(self, order_id: OrderId) -> Booking | None:
        with self._lock:
            return self._find(lambda b: any(a.order_id == order_id for a in b.attempts))

    def with_unsent_notices(self, limit: int) -> list[Booking]:
        with self._lock:
            found = [b for b in self._bookings.values() if b.unsent_notices][:limit]
            return [copy.deepcopy(b) for b in found]

    def save(self, booking: Booking) -> None:
        with self._lock:
            stored = self._bookings.get(booking.id)
            if stored is None:
                raise BookingNotFoundError(booking.id)
            if stored.version != booking.version:
                raise ConcurrentModificationError(booking.id)
            booking.version += 1
            self._bookings[booking.id] = copy.deepcopy(booking)

    def _find(self, matches: Callable[[Booking], bool]) -> Booking | None:
        found = next((b for b in self._bookings.values() if matches(b)), None)
        return copy.deepcopy(found) if found is not None else None
