"""The BookingRepository contract. Every implementation must pass it (Firestore joins later)."""

from __future__ import annotations

from dataclasses import replace
from datetime import date

import pytest

from ritis_api.adapters.memory import InMemoryBookingRepository
from ritis_api.domain.booking import Booking, BookingFormat, Customer, Language
from ritis_api.domain.identifiers import BookingId, OrderId
from ritis_api.domain.money import Currency, Money
from ritis_api.ports.storage import (
    BookingNotFoundError,
    BookingRepository,
    ConcurrentModificationError,
    DuplicateIdempotencyKeyError,
)
from tests.fakes import NOW


@pytest.fixture(params=["memory"])
def repository(request: pytest.FixtureRequest) -> BookingRepository:
    assert request.param == "memory"
    return InMemoryBookingRepository()


def booking(booking_id: str = "a" * 32, key: str = "key-0000000000000001") -> Booking:
    new = Booking.new(
        booking_id=BookingId(booking_id),
        idempotency_key=key,
        booking_format=BookingFormat.START,
        customer=Customer(name="A", contact="a@b.c", about="", links=""),
        price=Money(20000, Currency.EUR),
        offer_revision=date(2026, 11, 27),
        language=Language.KA,
        now=NOW,
    )
    new.start_attempt(OrderId("order-1"), "fake", NOW)
    return new


def test_reads_back_what_was_stored(repository: BookingRepository) -> None:
    # Every field counts: the accepted offer revision settles refund and chargeback disputes.
    stored = booking()
    repository.add(stored)

    loaded = repository.get(stored.id)

    assert replace(loaded, version=0) == replace(stored, version=0)


def test_changes_are_kept_only_when_saved(repository: BookingRepository) -> None:
    stored = booking()
    repository.add(stored)
    loaded = repository.get(stored.id)
    loaded.mark_checkout_failed(OrderId("order-1"))
    assert repository.get(stored.id).attempts[0].status.value == "pending"

    repository.save(loaded)
    assert repository.get(stored.id).attempts[0].status.value == "failed"


def test_finds_by_idempotency_key_and_order(repository: BookingRepository) -> None:
    repository.add(booking())
    by_key = repository.find_by_idempotency_key("key-0000000000000001")
    by_order = repository.find_by_order_id(OrderId("order-1"))
    assert by_key is not None
    assert by_order is not None
    assert by_key.id == by_order.id == "a" * 32
    assert repository.find_by_idempotency_key("key-0000000000000002") is None
    assert repository.find_by_order_id(OrderId("order-2")) is None


def test_one_booking_per_idempotency_key(repository: BookingRepository) -> None:
    repository.add(booking())
    with pytest.raises(DuplicateIdempotencyKeyError):
        repository.add(booking(booking_id="b" * 32))


def test_a_stale_copy_cannot_overwrite_a_newer_one(repository: BookingRepository) -> None:
    repository.add(booking())
    first = repository.get(BookingId("a" * 32))
    second = repository.get(BookingId("a" * 32))
    repository.save(first)
    with pytest.raises(ConcurrentModificationError):
        repository.save(second)


def test_unknown_booking(repository: BookingRepository) -> None:
    with pytest.raises(BookingNotFoundError):
        repository.get(BookingId("f" * 32))
