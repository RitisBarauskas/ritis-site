from __future__ import annotations

import pytest

from ritis_api.adapters.memory import InMemoryBookingRepository
from ritis_api.app.confirm_payment import ConfirmPayment, UnknownOrderError
from ritis_api.app.open_booking import OpenBooking
from ritis_api.domain.booking import Booking, BookingStatus
from ritis_api.domain.identifiers import BookingId, OrderId
from ritis_api.domain.money import Currency, Money
from ritis_api.ports.payments import PaymentProviderError
from ritis_api.ports.storage import ConcurrentModificationError
from tests.conftest import order_of, start_command
from tests.fakes import NOW, FakeProvider, RecordingNotifier


@pytest.fixture
def booking(open_booking: OpenBooking) -> Booking:
    return open_booking.start(start_command())


def test_a_payment_is_recorded_and_announced_once(
    confirm_payment: ConfirmPayment,
    provider: FakeProvider,
    notifier: RecordingNotifier,
    repository: InMemoryBookingRepository,
    booking: Booking,
) -> None:
    provider.approve(order_of(booking))
    assert confirm_payment.confirm(order_of(booking)).status is BookingStatus.PAID
    version = repository.get(booking.id).version

    assert confirm_payment.confirm(order_of(booking)).status is BookingStatus.PAID
    assert notifier.paid == [booking.id]
    assert repository.get(booking.id).version == version, "a repeat must not write"


def test_a_wrong_amount_is_sent_for_review(
    confirm_payment: ConfirmPayment,
    provider: FakeProvider,
    notifier: RecordingNotifier,
    booking: Booking,
) -> None:
    provider.approve(order_of(booking), charged=Money(100, Currency.EUR))
    assert confirm_payment.confirm(order_of(booking)).status is BookingStatus.NEEDS_REVIEW
    assert (notifier.paid, notifier.review) == ([], [booking.id])


def test_a_refund_made_in_the_provider_portal_is_picked_up(
    confirm_payment: ConfirmPayment, provider: FakeProvider, booking: Booking
) -> None:
    provider.reverse_in_portal(order_of(booking))
    assert confirm_payment.confirm(order_of(booking)).status is BookingStatus.REFUNDED


def test_an_unknown_order(confirm_payment: ConfirmPayment) -> None:
    with pytest.raises(UnknownOrderError):
        confirm_payment.confirm(OrderId("nobody-knows"))


def test_concurrent_confirmations_announce_once(
    repository: InMemoryBookingRepository,
    provider: FakeProvider,
    notifier: RecordingNotifier,
    confirm_payment: ConfirmPayment,
    booking: Booking,
) -> None:
    order_id = order_of(booking)
    provider.approve(order_id)

    class RacingRepository(InMemoryBookingRepository):
        """Lets a competing confirmation land between our read and our write, once."""

        raced = False

        def find_by_order_id(self, order_id: OrderId) -> Booking | None:
            return repository.find_by_order_id(order_id)

        def get(self, booking_id: BookingId) -> Booking:
            return repository.get(booking_id)

        def save(self, booking: Booking) -> None:
            if not self.raced:
                self.raced = True
                confirm_payment.confirm(order_id)  # the competitor wins the write
                raise ConcurrentModificationError(booking.id)
            repository.save(booking)

    racing = ConfirmPayment(
        repository=RacingRepository(), provider=provider, notifier=notifier, clock=lambda: NOW
    )
    assert racing.confirm(order_id).status is BookingStatus.PAID
    assert notifier.paid == [booking.id]


def test_a_broken_notifier_does_not_lose_the_payment(
    confirm_payment: ConfirmPayment,
    provider: FakeProvider,
    notifier: RecordingNotifier,
    repository: InMemoryBookingRepository,
    booking: Booking,
) -> None:
    provider.approve(order_of(booking))
    notifier.broken = True
    confirm_payment.confirm(order_of(booking))
    assert repository.get(booking.id).status is BookingStatus.PAID


class TestRefresh:
    def test_rechecks_an_open_payment(
        self, confirm_payment: ConfirmPayment, provider: FakeProvider, booking: Booking
    ) -> None:
        provider.approve(order_of(booking))
        assert confirm_payment.refresh(booking.id).status is BookingStatus.PAID

    def test_answers_during_a_provider_outage(
        self, confirm_payment: ConfirmPayment, provider: FakeProvider, booking: Booking
    ) -> None:
        provider.report_error = PaymentProviderError("down")
        assert confirm_payment.refresh(booking.id).status is BookingStatus.AWAITING_PAYMENT

    def test_leaves_a_settled_booking_alone(
        self, confirm_payment: ConfirmPayment, provider: FakeProvider, booking: Booking
    ) -> None:
        provider.approve(order_of(booking))
        confirm_payment.refresh(booking.id)
        calls = provider.report_calls
        confirm_payment.refresh(booking.id)
        assert provider.report_calls == calls
