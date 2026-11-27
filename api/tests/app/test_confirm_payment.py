from __future__ import annotations

import pytest

from ritis_api.adapters.memory import InMemoryBookingRepository
from ritis_api.app.confirm_payment import ConfirmPayment, UnknownOrderError
from ritis_api.app.open_booking import OpenBooking
from ritis_api.domain.booking import Booking, BookingStatus
from ritis_api.domain.identifiers import OrderId
from ritis_api.domain.money import Currency, Money
from ritis_api.ports.payments import PaymentProviderError
from tests.conftest import PRICE, make_confirm_payment, order_of, start_command
from tests.fakes import Clock, FakeProvider, RacingRepository, RecordingNotifier


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


def test_a_partial_refund_is_not_announced_as_a_payment(
    confirm_payment: ConfirmPayment,
    provider: FakeProvider,
    notifier: RecordingNotifier,
    booking: Booking,
) -> None:
    provider.approve(order_of(booking))
    confirm_payment.confirm(order_of(booking))
    provider.refund(order_of(booking), Money(5000, Currency.EUR))
    assert confirm_payment.confirm(order_of(booking)).status is BookingStatus.PAID
    assert notifier.paid == [booking.id]


def test_every_new_problem_is_announced_for_review(
    confirm_payment: ConfirmPayment,
    provider: FakeProvider,
    notifier: RecordingNotifier,
    booking: Booking,
) -> None:
    provider.approve(order_of(booking), charged=Money(30000, Currency.EUR))
    assert confirm_payment.confirm(order_of(booking)).status is BookingStatus.NEEDS_REVIEW
    provider.refund(order_of(booking), Money(30001, Currency.EUR))
    confirm_payment.confirm(order_of(booking))
    assert notifier.paid == []
    assert notifier.review == [booking.id, booking.id]


def test_a_refund_made_in_the_provider_portal_is_picked_up(
    confirm_payment: ConfirmPayment, provider: FakeProvider, booking: Booking
) -> None:
    provider.approve(order_of(booking))
    provider.refund(order_of(booking), PRICE)
    assert confirm_payment.confirm(order_of(booking)).status is BookingStatus.REFUNDED


def test_unknown_orders_and_orders_of_another_provider(
    confirm_payment: ConfirmPayment,
    repository: InMemoryBookingRepository,
    booking: Booking,
) -> None:
    with pytest.raises(UnknownOrderError):
        confirm_payment.confirm(OrderId("nobody-knows"))

    stored = repository.get(booking.id)
    stored.attempts[0].provider = "another-provider"
    repository.save(stored)
    with pytest.raises(UnknownOrderError):
        confirm_payment.confirm(order_of(booking))


def test_a_payment_survives_a_concurrent_change_of_the_booking(
    repository: InMemoryBookingRepository,
    provider: FakeProvider,
    notifier: RecordingNotifier,
    clock: Clock,
    confirm_payment: ConfirmPayment,
    open_booking: OpenBooking,
) -> None:
    # The first checkout was created at the provider but its reply was lost, so a repeat of the
    # request opened a second one. The customer pays the second; the orphan expires, and its
    # notification races with the payment's.
    provider.lose_next_reply = True
    with pytest.raises(PaymentProviderError):
        open_booking.start(start_command())
    booking = open_booking.start(start_command())
    orphan, paid = booking.attempts[0].order_id, order_of(booking)
    provider.expire(orphan)
    provider.approve(paid)

    racing = RacingRepository(repository, lambda: confirm_payment.confirm(orphan), race_on="save")
    ours = make_confirm_payment(racing, provider, notifier, clock)

    assert ours.confirm(paid).status is BookingStatus.PAID
    stored = repository.get(booking.id)
    assert stored.status is BookingStatus.PAID, "the payment must be written, not lost"
    assert stored.attempt(orphan).status.value == "expired", "and so must the competitor's change"
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

    def test_asks_the_provider_at_most_once_per_interval(
        self,
        confirm_payment: ConfirmPayment,
        provider: FakeProvider,
        clock: Clock,
        booking: Booking,
    ) -> None:
        for _ in range(10):
            confirm_payment.refresh(booking.id)
        assert provider.report_calls == 1

        clock.advance(5.1)
        provider.approve(order_of(booking))
        assert confirm_payment.refresh(booking.id).status is BookingStatus.PAID
        assert provider.report_calls == 2

    def test_a_clock_set_back_does_not_lock_out_rechecks(
        self,
        confirm_payment: ConfirmPayment,
        provider: FakeProvider,
        clock: Clock,
        booking: Booking,
    ) -> None:
        confirm_payment.refresh(booking.id)
        clock.advance(-3600)
        confirm_payment.refresh(booking.id)
        assert provider.report_calls == 2

    def test_a_refresh_leaves_another_providers_order_alone(
        self,
        confirm_payment: ConfirmPayment,
        provider: FakeProvider,
        repository: InMemoryBookingRepository,
        booking: Booking,
    ) -> None:
        stored = repository.get(booking.id)
        stored.attempts[0].provider = "another-provider"
        repository.save(stored)
        provider.approve(order_of(booking))

        assert confirm_payment.refresh(booking.id).status is BookingStatus.AWAITING_PAYMENT
        assert provider.report_calls == 0

    def test_answers_during_a_provider_outage(
        self, confirm_payment: ConfirmPayment, provider: FakeProvider, booking: Booking
    ) -> None:
        provider.report_error = PaymentProviderError("down")
        assert confirm_payment.refresh(booking.id).status is BookingStatus.AWAITING_PAYMENT

    def test_leaves_a_settled_booking_alone(
        self,
        confirm_payment: ConfirmPayment,
        provider: FakeProvider,
        clock: Clock,
        booking: Booking,
    ) -> None:
        provider.approve(order_of(booking))
        confirm_payment.refresh(booking.id)
        clock.advance(60)
        calls = provider.report_calls
        confirm_payment.refresh(booking.id)
        assert provider.report_calls == calls
