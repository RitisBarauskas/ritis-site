"""What only the Firestore repository has to prove: retention fields and real concurrency."""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta

import pytest
from google.cloud import firestore

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


def race_adding(client: firestore.Client, count: int) -> list[str]:
    repository = FirestoreBookingRepository(client)
    twins = [booking(booking_id=f"{n:032x}") for n in range(1, count + 1)]

    def add(twin: Booking) -> str:
        try:
            repository.add(twin)
        except DuplicateIdempotencyKeyError:
            return "refused"
        except ConcurrentModificationError:
            return "busy"
        return "added"

    with ThreadPoolExecutor(max_workers=count) as pool:
        return sorted(pool.map(add, twins))


def race_saving(client: firestore.Client, count: int) -> tuple[list[str], int]:
    repository = FirestoreBookingRepository(client)
    repository.add(booking())
    copies = [repository.get(BookingId("a" * 32)) for _ in range(count)]

    def save(copy: Booking) -> str:
        try:
            repository.save(copy)
        except ConcurrentModificationError:
            return "refused"
        return "saved"

    with ThreadPoolExecutor(max_workers=count) as pool:
        outcomes = sorted(pool.map(save, copies))
    return outcomes, repository.get(BookingId("a" * 32)).version


def test_a_double_click_makes_one_booking() -> None:
    assert race_adding(emulated_firestore(), 2) == ["added", "refused"]


def test_twins_crowding_one_key_never_make_two_bookings() -> None:
    # Twelve at once exhaust the client's retries on the emulator: some may hear "busy, try
    # again", which is honest. What may never happen is a second booking for the key.
    client = emulated_firestore()

    outcomes = race_adding(client, 12)

    added = outcomes.count("added")
    assert added <= 1
    assert len(list(client.collection(BOOKINGS).stream())) == added
    assert set(outcomes) <= {"added", "refused", "busy"}


def test_two_writers_from_one_read_keep_one_change() -> None:
    outcomes, version = race_saving(emulated_firestore(), 2)

    assert (outcomes, version) == (["refused", "saved"], 2)


def test_writers_crowding_one_read_never_both_write() -> None:
    outcomes, version = race_saving(emulated_firestore(), 12)

    saved = outcomes.count("saved")
    assert saved <= 1
    assert version == 1 + saved, "every write that went through moved the version once"
