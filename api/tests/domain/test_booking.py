from __future__ import annotations

import pytest

from ritis_api.domain.booking import Booking, BookingFormat, BookingStatus, Customer
from ritis_api.domain.errors import BookingError
from ritis_api.domain.identifiers import BookingId, OrderId
from ritis_api.domain.money import Currency, Money
from ritis_api.domain.payment import AttemptStatus, PaymentReport, PaymentState
from tests.fakes import NOW

PRICE = Money(20000, Currency.EUR)
O1, O2 = OrderId("o1"), OrderId("o2")


def eur(minor: int) -> Money:
    return Money(minor, Currency.EUR)


def approved(charged: Money = PRICE, refunded: Money | None = None) -> PaymentReport:
    return PaymentReport(PaymentState.APPROVED, charged, refunded)


DECLINED = PaymentReport(PaymentState.DECLINED)
EXPIRED = PaymentReport(PaymentState.EXPIRED)


def status(booking: Booking) -> BookingStatus:
    # Read through a call: mypy would otherwise narrow `booking.status` across mutations.
    return booking.status


def new_booking() -> Booking:
    return Booking.new(
        booking_id=BookingId("b" * 32),
        idempotency_key="k" * 16,
        booking_format=BookingFormat.SESSION,
        customer=Customer(name="A", contact="a@b.c", about="", links=""),
        price=PRICE,
        now=NOW,
    )


def with_checkout(booking: Booking, order_id: OrderId) -> Booking:
    booking.start_attempt(order_id, NOW)
    booking.attach_checkout(order_id, f"https://pay.example/{order_id}", "p")
    return booking


def paid_booking() -> Booking:
    booking = with_checkout(new_booking(), O1)
    booking.apply_report(O1, approved(), NOW)
    return booking


class TestPaymentReport:
    def test_money_taken_must_be_stated_and_nothing_else_may_carry_amounts(self) -> None:
        with pytest.raises(ValueError, match="charged"):
            PaymentReport(PaymentState.APPROVED)
        with pytest.raises(ValueError, match="amounts"):
            PaymentReport(PaymentState.DECLINED, charged=PRICE)

    def test_a_full_reversal_without_an_amount_refunds_the_charge(self) -> None:
        assert PaymentReport(PaymentState.REVERSED, charged=PRICE).refunded_total == PRICE
        assert approved().refunded_total is None


class TestPaying:
    def test_approval_pays_once(self) -> None:
        booking = with_checkout(new_booking(), O1)
        assert booking.open_checkout_url == "https://pay.example/o1"

        assert booking.apply_report(O1, approved(), NOW) is True
        assert status(booking) is BookingStatus.PAID
        assert booking.paid_at == NOW
        assert booking.open_checkout_url is None

        assert booking.apply_report(O1, approved(), NOW) is False
        assert booking.paid == PRICE

    def test_pending_changes_nothing(self) -> None:
        booking = with_checkout(new_booking(), O1)
        assert booking.apply_report(O1, PaymentReport(PaymentState.PENDING), NOW) is False
        assert status(booking) is BookingStatus.AWAITING_PAYMENT

    def test_a_wrong_amount_is_flagged_not_paid(self) -> None:
        booking = with_checkout(new_booking(), O1)
        booking.apply_report(O1, approved(charged=eur(100)), NOW)
        assert status(booking) is BookingStatus.NEEDS_REVIEW
        assert booking.paid_at is None
        assert booking.review_reason is not None
        assert "expected" in booking.review_reason

    def test_a_second_successful_payment_is_flagged(self) -> None:
        booking = with_checkout(new_booking(), O1)
        booking.apply_report(O1, DECLINED, NOW)
        with_checkout(booking, O2)
        booking.apply_report(O2, approved(), NOW)
        # The first checkout gets paid too, from a tab left open.
        booking.apply_report(O1, approved(), NOW)
        assert status(booking) is BookingStatus.NEEDS_REVIEW
        assert booking.review_reason is not None
        assert "second successful payment" in booking.review_reason

    def test_decline_or_expiry_then_a_new_attempt(self) -> None:
        for failure, failed_status in [
            (DECLINED, BookingStatus.DECLINED),
            (EXPIRED, BookingStatus.EXPIRED),
        ]:
            booking = with_checkout(new_booking(), O1)
            assert booking.apply_report(O1, failure, NOW) is True
            assert status(booking) is failed_status
            assert booking.can_retry_payment

            with_checkout(booking, O2)
            assert status(booking) is BookingStatus.AWAITING_PAYMENT
            assert booking.open_checkout_url == "https://pay.example/o2"

    def test_the_same_order_may_succeed_after_a_decline(self) -> None:
        # The checkout lets the customer try another card on the same order.
        booking = with_checkout(new_booking(), O1)
        booking.apply_report(O1, DECLINED, NOW)
        booking.apply_report(O1, approved(), NOW)
        assert status(booking) is BookingStatus.PAID

    def test_a_failure_after_approval_is_stale(self) -> None:
        booking = paid_booking()
        assert booking.apply_report(O1, DECLINED, NOW) is False
        assert booking.apply_report(O1, EXPIRED, NOW) is False
        assert status(booking) is BookingStatus.PAID

    def test_an_old_attempt_failing_leaves_the_open_one_alone(self) -> None:
        booking = with_checkout(new_booking(), O1)
        booking.apply_report(O1, EXPIRED, NOW)
        with_checkout(booking, O2)
        booking.apply_report(O1, DECLINED, NOW)
        assert status(booking) is BookingStatus.AWAITING_PAYMENT

    def test_one_open_attempt_at_a_time(self) -> None:
        booking = with_checkout(new_booking(), O1)
        with pytest.raises(BookingError):
            booking.start_attempt(O2, NOW)
        with pytest.raises(BookingError):
            paid_booking().start_attempt(O2, NOW)

    def test_a_failed_checkout_frees_the_way_for_a_new_attempt(self) -> None:
        booking = new_booking()
        booking.start_attempt(O1, NOW)
        booking.mark_checkout_failed(O1)
        assert booking.attempt(O1).status is AttemptStatus.FAILED
        assert booking.can_retry_payment
        with pytest.raises(BookingError):
            booking.attach_checkout(O1, "https://late.example", "p")


class TestRefunds:
    def test_cumulative_totals_from_the_provider(self) -> None:
        booking = paid_booking()
        assert booking.apply_report(O1, approved(refunded=eur(5000)), NOW) is True
        assert status(booking) is BookingStatus.PAID
        assert booking.refunded == eur(5000)

        # Repeated and stale totals change nothing.
        assert booking.apply_report(O1, approved(refunded=eur(5000)), NOW) is False
        assert booking.apply_report(O1, approved(refunded=eur(1000)), NOW) is False

        reversed_report = PaymentReport(PaymentState.REVERSED, PRICE, PRICE)
        assert booking.apply_report(O1, reversed_report, NOW) is True
        assert status(booking) is BookingStatus.REFUNDED

    def test_a_refund_above_the_charge_is_refused(self) -> None:
        with pytest.raises(BookingError, match="refunded"):
            paid_booking().apply_report(O1, approved(refunded=eur(20001)), NOW)

    def test_plan_defaults_to_what_is_left(self) -> None:
        booking = paid_booking()
        assert booking.plan_refund().amount == PRICE
        booking.apply_report(O1, approved(refunded=eur(5000)), NOW)
        plan = booking.plan_refund()
        assert (plan.order_id, plan.amount) == (O1, eur(15000))

    def test_plan_refuses_unpaid_zero_and_excess(self) -> None:
        with pytest.raises(BookingError, match="nothing left"):
            with_checkout(new_booking(), O1).plan_refund()
        booking = paid_booking()
        with pytest.raises(BookingError):
            booking.plan_refund(eur(0))
        with pytest.raises(BookingError):
            booking.plan_refund(eur(20001))
