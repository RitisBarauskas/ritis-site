from __future__ import annotations

from datetime import timedelta

import pytest

from ritis_api.adapters.memory import InMemoryBookingRepository
from ritis_api.app.catalog import Catalog
from ritis_api.app.confirm_payment import ConfirmPayment
from ritis_api.app.open_booking import CheckoutSettings, OpenBooking, StartBooking
from ritis_api.domain.booking import Booking, BookingFormat, Customer
from ritis_api.domain.identifiers import OrderId
from ritis_api.domain.money import Currency, Money
from ritis_api.ports.storage import BookingRepository
from tests.fakes import Clock, FakeProvider, Ids, RecordingNotifier

PRICE = Money(20000, Currency.EUR)
RECHECK = timedelta(seconds=5)
SETTINGS = CheckoutSettings(
    return_url_template="https://api.example/return?booking={booking_id}",
    notification_url="https://api.example/notify",
    lifetime_seconds=3600,
)


@pytest.fixture
def provider() -> FakeProvider:
    return FakeProvider()


@pytest.fixture
def notifier() -> RecordingNotifier:
    return RecordingNotifier()


@pytest.fixture
def repository() -> InMemoryBookingRepository:
    return InMemoryBookingRepository()


@pytest.fixture
def clock() -> Clock:
    return Clock()


@pytest.fixture
def confirm_payment(
    repository: InMemoryBookingRepository,
    provider: FakeProvider,
    notifier: RecordingNotifier,
    clock: Clock,
) -> ConfirmPayment:
    return make_confirm_payment(repository, provider, notifier, clock)


@pytest.fixture
def open_booking(
    repository: InMemoryBookingRepository,
    provider: FakeProvider,
    confirm_payment: ConfirmPayment,
    clock: Clock,
) -> OpenBooking:
    return make_open_booking(repository, provider, confirm_payment, clock)


def make_confirm_payment(
    repository: BookingRepository,
    provider: FakeProvider,
    notifier: RecordingNotifier,
    clock: Clock,
) -> ConfirmPayment:
    return ConfirmPayment(
        repository=repository,
        provider=provider,
        notifier=notifier,
        clock=clock,
        recheck_interval=RECHECK,
    )


def make_open_booking(
    repository: BookingRepository,
    provider: FakeProvider,
    confirm_payment: ConfirmPayment,
    clock: Clock,
    settings: CheckoutSettings = SETTINGS,
) -> OpenBooking:
    return OpenBooking(
        repository=repository,
        provider=provider,
        confirm_payment=confirm_payment,
        catalog=Catalog(call_price=PRICE),
        settings=settings,
        clock=clock,
        new_id=Ids(),
    )


def start_command(
    key: str = "key-0000000000000001", contact: str = "client@example.com", name: str = "Анна"
) -> StartBooking:
    return StartBooking(
        idempotency_key=key,
        booking_format=BookingFormat.FOUNDATION,
        customer=Customer(name=name, contact=contact, about="MVP на FastAPI", links=""),
    )


def order_of(booking: Booking) -> OrderId:
    assert booking.current_attempt is not None
    return booking.current_attempt.order_id
