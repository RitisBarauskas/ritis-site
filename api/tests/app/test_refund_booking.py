from __future__ import annotations

import pytest

from ritis_api.app.confirm_payment import ConfirmPayment
from ritis_api.app.open_booking import OpenBooking
from ritis_api.app.refund_booking import RefundBooking, RefundDeclinedError
from ritis_api.domain.booking import Booking, BookingStatus
from ritis_api.domain.errors import BookingError
from ritis_api.domain.money import Currency, Money
from ritis_api.ports.payments import RefundStatus
from tests.conftest import PRICE, order_of, start_command
from tests.fakes import FakeProvider, RecordingNotifier


@pytest.fixture
def paid(
    open_booking: OpenBooking, confirm_payment: ConfirmPayment, provider: FakeProvider
) -> Booking:
    booking = open_booking.start(start_command())
    provider.approve(order_of(booking))
    return confirm_payment.confirm(order_of(booking))


def test_full_refund_by_default(
    refund_booking: RefundBooking, provider: FakeProvider, paid: Booking
) -> None:
    refunded = refund_booking.refund(paid.id, refund_id="r1")
    assert refunded.status is BookingStatus.REFUNDED
    assert provider.refund_calls == [(order_of(paid), PRICE, "r1")]


def test_partial_then_the_rest(
    refund_booking: RefundBooking,
    provider: FakeProvider,
    notifier: RecordingNotifier,
    paid: Booking,
) -> None:
    part = refund_booking.refund(paid.id, refund_id="r1", amount=Money(5000, Currency.EUR))
    assert (part.status, part.refunded) == (BookingStatus.PAID, Money(5000, Currency.EUR))
    assert notifier.paid == [paid.id], "a partial refund is not a new payment"

    rest = refund_booking.refund(paid.id, refund_id="r2")
    assert rest.status is BookingStatus.REFUNDED
    assert provider.refund_calls[-1][1] == Money(15000, Currency.EUR)


def test_a_declined_refund_changes_nothing(
    refund_booking: RefundBooking,
    confirm_payment: ConfirmPayment,
    provider: FakeProvider,
    paid: Booking,
) -> None:
    provider.refund_status = RefundStatus.DECLINED
    with pytest.raises(RefundDeclinedError):
        refund_booking.refund(paid.id, refund_id="r1")
    assert confirm_payment.refresh(paid.id).status is BookingStatus.PAID


def test_nothing_reaches_the_provider_for_an_impossible_refund(
    refund_booking: RefundBooking,
    open_booking: OpenBooking,
    provider: FakeProvider,
    paid: Booking,
) -> None:
    unpaid = open_booking.start(start_command(key="key-0000000000000002"))
    with pytest.raises(BookingError):
        refund_booking.refund(unpaid.id, refund_id="r1")
    with pytest.raises(BookingError):
        refund_booking.refund(paid.id, refund_id="r2", amount=Money(20001, Currency.EUR))
    assert provider.refund_calls == []
