"""What only the Firestore repository has to prove: retention fields and real concurrency."""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta

import pytest

from ritis_api.adapters.firestore import BOOKINGS, IDEMPOTENCY_KEYS, FirestoreBookingRepository
from ritis_api.domain.booking import Booking
from ritis_api.domain.identifiers import BookingId, OrderId
from ritis_api.domain.money import Currency, Money
from ritis_api.domain.payment import Charged
from ritis_api.ports.storage import ConcurrentModificationError, DuplicateIdempotencyKeyError
from tests.adapters.test_booking_repository import booking, emulated_firestore
from tests.fakes import NOW

pytestmark = pytest.mark.firestore


def test_an_unpaid_booking_and_its_key_carry_their_deletion_date() -> None:
    client = emulated_firestore()
    repository = FirestoreBookingRepository(client)
    stored = booking()

    repository.add(stored)

    deadline = NOW + timedelta(days=30)
    assert client.collection(BOOKINGS).document(stored.id).get().get("expire_at") == deadline
    (key,) = client.collection(IDEMPOTENCY_KEYS).stream()
    assert key.get("expire_at") == deadline


def test_a_paid_booking_is_kept() -> None:
    client = emulated_firestore()
    repository = FirestoreBookingRepository(client)
    stored = booking()
    repository.add(stored)
    stored.attach_checkout(OrderId("order-1"), "https://pay.example/order-1", "p-1")
    price = Money(20000, Currency.EUR)

    stored.apply_report(OrderId("order-1"), Charged(price, Money.zero(Currency.EUR)), NOW)
    repository.save(stored)

    assert client.collection(BOOKINGS).document(stored.id).get().get("expire_at") is None


def test_twins_racing_with_one_key_make_one_booking() -> None:
    repository = FirestoreBookingRepository(emulated_firestore())
    twins = [booking(booking_id=f"{n:032x}") for n in range(1, 6)]

    def add(twin: Booking) -> str:
        try:
            repository.add(twin)
        except DuplicateIdempotencyKeyError:
            return "refused"
        return "added"

    with ThreadPoolExecutor(max_workers=len(twins)) as pool:
        outcomes = sorted(pool.map(add, twins))

    assert outcomes == ["added"] + ["refused"] * (len(twins) - 1)


def test_writers_racing_from_one_read_keep_one_change() -> None:
    repository = FirestoreBookingRepository(emulated_firestore())
    repository.add(booking())
    copies = [repository.get(BookingId("a" * 32)) for _ in range(5)]

    def save(copy: Booking) -> str:
        try:
            repository.save(copy)
        except ConcurrentModificationError:
            return "refused"
        return "saved"

    with ThreadPoolExecutor(max_workers=len(copies)) as pool:
        outcomes = sorted(pool.map(save, copies))

    assert outcomes == ["refused"] * (len(copies) - 1) + ["saved"]
    assert repository.get(BookingId("a" * 32)).version == 2
