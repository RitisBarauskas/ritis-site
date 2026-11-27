from __future__ import annotations

import pytest

from ritis_api.adapters.memory import InMemoryBookingRepository
from ritis_api.app.catalog import Catalog
from ritis_api.app.confirm_payment import ConfirmPayment
from ritis_api.app.open_booking import CheckoutSettings, OpenBooking, StartBooking
from ritis_api.app.refund_booking import RefundBooking
from ritis_api.domain.booking import Booking, BookingFormat, Customer
from ritis_api.domain.identifiers import OrderId
from ritis_api.domain.money import Currency, Money
from tests.fakes import NOW, FakeProvider, Ids, RecordingNotifier

PRICE = Money(20000, Currency.EUR)


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
def open_booking(repository: InMemoryBookingRepository, provider: FakeProvider) -> OpenBooking:
    return OpenBooking(
        repository=repository,
        provider=provider,
        catalog=Catalog(call_price=PRICE),
        settings=CheckoutSettings(api_base_url="https://ritis.dev/", lifetime_seconds=3600),
        clock=lambda: NOW,
        new_id=Ids(),
    )


@pytest.fixture
def confirm_payment(
    repository: InMemoryBookingRepository, provider: FakeProvider, notifier: RecordingNotifier
) -> ConfirmPayment:
    return ConfirmPayment(
        repository=repository, provider=provider, notifier=notifier, clock=lambda: NOW
    )


@pytest.fixture
def refund_booking(
    repository: InMemoryBookingRepository,
    provider: FakeProvider,
    confirm_payment: ConfirmPayment,
) -> RefundBooking:
    return RefundBooking(repository=repository, provider=provider, confirm=confirm_payment)


def start_command(
    key: str = "key-0000000000000001", contact: str = "client@example.com"
) -> StartBooking:
    return StartBooking(
        idempotency_key=key,
        booking_format=BookingFormat.FOUNDATION,
        customer=Customer(name="Анна", contact=contact, about="MVP на FastAPI", links=""),
    )


def order_of(booking: Booking) -> OrderId:
    assert booking.current_attempt is not None
    return booking.current_attempt.order_id
