from __future__ import annotations

import pytest

from ritis_api.adapters.memory import InMemoryBookingRepository
from ritis_api.app.confirm_payment import ConfirmPayment
from ritis_api.app.open_booking import OpenBooking
from ritis_api.domain.booking import BookingStatus
from ritis_api.domain.errors import BookingError
from ritis_api.domain.payment import AttemptStatus
from ritis_api.ports.payments import PaymentProviderError
from tests.conftest import PRICE, order_of, start_command
from tests.fakes import FakeProvider


def test_opens_a_checkout_for_the_call_price(
    open_booking: OpenBooking, provider: FakeProvider
) -> None:
    booking = open_booking.start(start_command())

    assert booking.status is BookingStatus.AWAITING_PAYMENT
    assert booking.open_checkout_url == f"https://pay.example/{order_of(booking)}"
    (request,) = provider.checkout_requests
    assert request.amount == PRICE
    assert request.return_url == f"https://ritis.dev/api/payments/flitt/return?booking={booking.id}"
    assert request.notification_url == "https://ritis.dev/api/payments/flitt/notification"
    assert request.customer_email == "client@example.com"


def test_a_telegram_handle_is_not_passed_as_email(
    open_booking: OpenBooking, provider: FakeProvider
) -> None:
    open_booking.start(start_command(contact="@client"))
    assert provider.checkout_requests[0].customer_email is None


def test_a_repeated_request_returns_the_same_checkout(
    open_booking: OpenBooking, provider: FakeProvider
) -> None:
    first = open_booking.start(start_command())
    second = open_booking.start(start_command())
    assert (second.id, second.open_checkout_url) == (first.id, first.open_checkout_url)
    assert len(provider.checkout_requests) == 1


def test_after_a_provider_failure_the_repeat_opens_a_fresh_order(
    open_booking: OpenBooking,
    provider: FakeProvider,
    repository: InMemoryBookingRepository,
) -> None:
    provider.open_errors.append(PaymentProviderError("down"))
    with pytest.raises(PaymentProviderError):
        open_booking.start(start_command())
    stored = repository.find_by_idempotency_key(start_command().idempotency_key)
    assert stored is not None
    assert [a.status for a in stored.attempts] == [AttemptStatus.FAILED]

    booking = open_booking.start(start_command())
    assert booking.id == stored.id
    assert booking.open_checkout_url is not None
    first, second = provider.checkout_requests
    assert first.order_id != second.order_id


def test_an_interrupted_start_is_finished_with_a_new_order(
    open_booking: OpenBooking,
    provider: FakeProvider,
    repository: InMemoryBookingRepository,
) -> None:
    # The process died after storing the booking and before the provider answered.
    provider.open_errors.append(RuntimeError("process died"))
    with pytest.raises(RuntimeError):
        open_booking.start(start_command())

    booking = open_booking.start(start_command())
    assert [a.status for a in booking.attempts] == [AttemptStatus.FAILED, AttemptStatus.PENDING]
    assert booking.open_checkout_url is not None
    assert repository.get(booking.id).open_checkout_url == booking.open_checkout_url


def test_pay_again_after_a_decline(
    open_booking: OpenBooking, confirm_payment: ConfirmPayment, provider: FakeProvider
) -> None:
    booking = open_booking.start(start_command())
    provider.decline(order_of(booking))
    confirm_payment.confirm(order_of(booking))

    again = open_booking.retry(booking.id)
    assert again.open_checkout_url is not None
    assert order_of(again) != order_of(booking)


def test_pay_again_while_a_checkout_is_open_returns_it(
    open_booking: OpenBooking, provider: FakeProvider
) -> None:
    booking = open_booking.start(start_command())
    assert open_booking.retry(booking.id).open_checkout_url == booking.open_checkout_url
    assert len(provider.checkout_requests) == 1


def test_a_paid_booking_cannot_be_paid_again(
    open_booking: OpenBooking, confirm_payment: ConfirmPayment, provider: FakeProvider
) -> None:
    booking = open_booking.start(start_command())
    provider.approve(order_of(booking))
    confirm_payment.confirm(order_of(booking))
    with pytest.raises(BookingError):
        open_booking.retry(booking.id)
    assert len(provider.checkout_requests) == 1
