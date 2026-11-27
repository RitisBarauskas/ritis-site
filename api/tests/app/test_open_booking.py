from __future__ import annotations

import pytest

from ritis_api.adapters.memory import InMemoryBookingRepository
from ritis_api.app.catalog import Catalog, Offer
from ritis_api.app.confirm_payment import ConfirmPayment
from ritis_api.app.open_booking import IdempotencyKeyReusedError, OpenBooking
from ritis_api.domain.booking import BookingFormat, BookingStatus
from ritis_api.domain.errors import BookingError
from ritis_api.domain.money import Currency, Money
from ritis_api.domain.payment import AttemptStatus
from ritis_api.ports.payments import PaymentProviderError
from tests.conftest import PRICE, make_open_booking, order_of, start_command
from tests.fakes import Clock, FakeProvider, RacingRepository


def test_charges_and_names_the_format_that_was_booked(
    repository: InMemoryBookingRepository, provider: FakeProvider, clock: Clock
) -> None:
    catalog = Catalog(
        {
            BookingFormat.START: Offer(Money(20000, Currency.EUR), "старт"),
            BookingFormat.LAUNCH: Offer(Money(50000, Currency.EUR), "запуск"),
            BookingFormat.FOUNDATION: Offer(Money(20000, Currency.EUR), "старт фундамента"),
            BookingFormat.SUBSCRIPTION: Offer(Money(20000, Currency.EUR), "старт подписки"),
        }
    )
    open_booking = make_open_booking(repository, provider, clock, catalog=catalog)

    booking = open_booking.start(start_command(booking_format=BookingFormat.LAUNCH))

    (request,) = provider.checkout_requests
    assert (request.amount, request.description) == (Money(50000, Currency.EUR), "запуск")
    assert booking.price == Money(50000, Currency.EUR)


def test_opens_a_checkout_for_the_booked_price(
    open_booking: OpenBooking, provider: FakeProvider
) -> None:
    booking = open_booking.start(start_command())

    assert booking.status is BookingStatus.AWAITING_PAYMENT
    assert booking.open_checkout_url == f"https://pay.example/{order_of(booking)}"
    assert booking.current_attempt is not None
    assert booking.current_attempt.provider == provider.name
    (request,) = provider.checkout_requests
    assert request.amount == PRICE
    assert request.return_url == f"https://api.example/return?booking={booking.id}"
    assert request.notification_url == "https://api.example/notify"
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


def test_a_key_reused_for_another_request_is_refused(
    open_booking: OpenBooking, provider: FakeProvider
) -> None:
    open_booking.start(start_command())
    with pytest.raises(IdempotencyKeyReusedError):
        open_booking.start(start_command(contact="typo-fixed@example.com"))
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
    assert repository.get(booking.id).open_checkout_url == booking.open_checkout_url


class TestConcurrentStarts:
    def test_a_twin_request_answers_with_the_winners_checkout(
        self,
        repository: InMemoryBookingRepository,
        provider: FakeProvider,
        clock: Clock,
    ) -> None:
        winner = make_open_booking(repository, provider, clock)
        racing = RacingRepository(repository, lambda: winner.start(start_command()), race_on="add")
        loser = make_open_booking(racing, provider, clock)

        answer = loser.start(start_command())

        stored = repository.find_by_idempotency_key(start_command().idempotency_key)
        assert stored is not None
        assert (answer.id, answer.open_checkout_url) == (stored.id, stored.open_checkout_url)
        assert answer.open_checkout_url is not None
        assert len(provider.checkout_requests) == 1, "the loser never reached the provider"

    def test_losing_the_write_answers_with_the_stored_state(
        self,
        repository: InMemoryBookingRepository,
        provider: FakeProvider,
        clock: Clock,
    ) -> None:
        competitor = make_open_booking(repository, provider, clock)
        # The competitor repeats the request while ours waits for the provider: it retires our
        # attempt, opens its own checkout and saves first.
        racing = RacingRepository(
            repository, lambda: competitor.start(start_command()), race_on="save"
        )
        ours = make_open_booking(racing, provider, clock)

        answer = ours.start(start_command())

        stored = repository.get(answer.id)
        assert [a.status for a in stored.attempts] == [AttemptStatus.FAILED, AttemptStatus.PENDING]
        assert answer.open_checkout_url == stored.open_checkout_url
        assert answer.open_checkout_url == f"https://pay.example/{order_of(stored)}"


class TestRetry:
    def test_pay_again_after_a_decline(
        self, open_booking: OpenBooking, confirm_payment: ConfirmPayment, provider: FakeProvider
    ) -> None:
        booking = open_booking.start(start_command())
        provider.decline(order_of(booking))
        confirm_payment.confirm(order_of(booking))

        again = open_booking.retry(booking.id)
        assert again.open_checkout_url is not None
        assert order_of(again) != order_of(booking)

    def test_an_open_checkout_is_returned_as_is(
        self, open_booking: OpenBooking, provider: FakeProvider
    ) -> None:
        booking = open_booking.start(start_command())
        assert open_booking.retry(booking.id).open_checkout_url == booking.open_checkout_url
        assert len(provider.checkout_requests) == 1

    def test_pay_again_after_an_expiry(
        self, open_booking: OpenBooking, confirm_payment: ConfirmPayment, provider: FakeProvider
    ) -> None:
        booking = open_booking.start(start_command())
        provider.expire(order_of(booking))
        confirm_payment.confirm(order_of(booking))

        again = open_booking.retry(booking.id)
        assert order_of(again) != order_of(booking)
        assert again.open_checkout_url is not None


def test_a_paid_booking_cannot_be_paid_again(
    open_booking: OpenBooking, confirm_payment: ConfirmPayment, provider: FakeProvider
) -> None:
    booking = open_booking.start(start_command())
    provider.approve(order_of(booking))
    confirm_payment.confirm(order_of(booking))
    with pytest.raises(BookingError):
        open_booking.retry(booking.id)
    assert len(provider.checkout_requests) == 1
