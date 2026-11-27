from __future__ import annotations

from datetime import date, timedelta

import pytest

from ritis_api.adapters.memory import InMemoryBookingRepository
from ritis_api.app.catalog import Catalog, Offer
from ritis_api.app.confirm_payment import ConfirmPayment
from ritis_api.app.open_booking import CheckoutSettings, OpenBooking, StartBooking
from ritis_api.domain.booking import Booking, BookingFormat, Customer, Language
from ritis_api.domain.identifiers import OrderId
from ritis_api.domain.money import Currency, Money
from ritis_api.ports.storage import BookingRepository
from tests.fakes import Clock, FakeProvider, Ids, RecordingNotifier

PRICE = Money(20000, Currency.EUR)
OFFER_REVISION = date(2026, 11, 27)
CATALOG = Catalog(
    {
        fmt: Offer(PRICE, {lang: f"ritis.dev — {fmt.value} [{lang}]" for lang in Language})
        for fmt in BookingFormat
    },
    OFFER_REVISION,
)
RECHECK = timedelta(seconds=5)
SETTINGS = CheckoutSettings(
    return_url_template="https://api.example/return?booking={booking_id}&lang={language}",
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
    repository: InMemoryBookingRepository, provider: FakeProvider, clock: Clock
) -> OpenBooking:
    return make_open_booking(repository, provider, clock)


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
    clock: Clock,
    settings: CheckoutSettings = SETTINGS,
    catalog: Catalog = CATALOG,
) -> OpenBooking:
    return OpenBooking(
        repository=repository,
        provider=provider,
        catalog=catalog,
        settings=settings,
        clock=clock,
        new_id=Ids(),
    )


def start_command(
    key: str = "key-0000000000000001",
    contact: str = "client@example.com",
    name: str = "Анна",
    booking_format: BookingFormat = BookingFormat.FOUNDATION,
    language: Language = Language.RU,
) -> StartBooking:
    return StartBooking(
        idempotency_key=key,
        booking_format=booking_format,
        customer=Customer(name=name, contact=contact, about="MVP на FastAPI", links=""),
        language=language,
    )


def order_of(booking: Booking) -> OrderId:
    assert booking.current_attempt is not None
    return booking.current_attempt.order_id
