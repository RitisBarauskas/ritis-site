from __future__ import annotations

from datetime import date, timedelta

import pytest

from ritis_api.domain.booking import (
    Booking,
    BookingFormat,
    BookingStatus,
    Customer,
    Language,
    NoticeKind,
    OwnerNotice,
)
from ritis_api.domain.errors import BookingError
from ritis_api.domain.identifiers import BookingId, OrderId
from ritis_api.domain.money import Currency, Money
from ritis_api.domain.payment import AttemptStatus, Charged, NotCharged, Outcome
from tests.fakes import NOW

PRICE = Money(20000, Currency.EUR)
O1, O2 = OrderId("o1"), OrderId("o2")
PENDING = NotCharged(Outcome.PENDING)
DECLINED = NotCharged(Outcome.DECLINED)
EXPIRED = NotCharged(Outcome.EXPIRED)


def eur(minor: int) -> Money:
    return Money(minor, Currency.EUR)


def charged(amount: Money = PRICE, refunded: Money | None = None) -> Charged:
    return Charged(amount, refunded or Money.zero(amount.currency))


def status(booking: Booking) -> BookingStatus:
    # Read through a call: mypy would otherwise narrow `booking.status` across mutations.
    return booking.status


def new_booking() -> Booking:
    return Booking.new(
        booking_id=BookingId("b" * 32),
        idempotency_key="k" * 16,
        booking_format=BookingFormat.START,
        customer=Customer(name="A", contact="a@b.c", about="", links=""),
        price=PRICE,
        offer_revision=date(2026, 11, 27),
        language=Language.RU,
        now=NOW,
    )


def with_checkout(booking: Booking, order_id: OrderId) -> Booking:
    booking.start_attempt(order_id, "fake", NOW)
    booking.attach_checkout(order_id, f"https://pay.example/{order_id}", "p")
    return booking


def paid_booking() -> Booking:
    booking = with_checkout(new_booking(), O1)
    booking.apply_report(O1, charged(), NOW)
    return booking


def flagged_booking() -> Booking:
    booking = with_checkout(new_booking(), O1)
    booking.apply_report(O1, charged(eur(30000)), NOW)
    assert status(booking) is BookingStatus.NEEDS_REVIEW
    return booking


def test_a_report_cannot_refund_in_another_currency_than_it_charged() -> None:
    with pytest.raises(ValueError, match="refund in USD"):
        Charged(PRICE, Money(0, Currency.USD))


class TestPaying:
    def test_a_charge_of_the_price_pays_once(self) -> None:
        booking = with_checkout(new_booking(), O1)
        assert booking.open_checkout_url == "https://pay.example/o1"

        assert booking.apply_report(O1, charged(), NOW) is True
        assert status(booking) is BookingStatus.PAID
        assert booking.paid_at == NOW
        assert booking.attempt(O1).charged == PRICE
        assert booking.open_checkout_url is None

        assert booking.apply_report(O1, charged(), NOW) is False

    def test_pending_changes_nothing(self) -> None:
        booking = with_checkout(new_booking(), O1)
        assert booking.apply_report(O1, PENDING, NOW) is False
        assert status(booking) is BookingStatus.AWAITING_PAYMENT

    def test_a_charge_other_than_the_price_is_flagged_and_kept(self) -> None:
        booking = with_checkout(new_booking(), O1)
        booking.apply_report(O1, charged(eur(30000)), NOW)
        assert status(booking) is BookingStatus.NEEDS_REVIEW
        assert booking.paid_at is None
        assert booking.attempt(O1).charged == eur(30000), "a human reconciles the real charge"
        assert booking.review_reason is not None
        assert "expected" in booking.review_reason

    def test_a_charge_in_another_currency_is_flagged(self) -> None:
        booking = with_checkout(new_booking(), O1)
        booking.apply_report(O1, charged(Money(20000, Currency.USD)), NOW)
        assert status(booking) is BookingStatus.NEEDS_REVIEW

    @pytest.mark.parametrize("settled", ["paid", "refunded"])
    def test_a_second_successful_payment_is_flagged(self, settled: str) -> None:
        booking = with_checkout(new_booking(), O1)
        booking.apply_report(O1, DECLINED, NOW)
        with_checkout(booking, O2)
        booking.apply_report(O2, charged(), NOW)
        if settled == "refunded":
            booking.apply_report(O2, charged(refunded=PRICE), NOW)
            assert status(booking) is BookingStatus.REFUNDED
        # The first checkout gets paid too, from a tab left open.
        booking.apply_report(O1, charged(), NOW)
        assert status(booking) is BookingStatus.NEEDS_REVIEW
        assert booking.review_reason is not None
        assert "second successful payment" in booking.review_reason

    def test_a_provider_changing_a_recorded_charge_is_flagged(self) -> None:
        booking = paid_booking()
        assert booking.apply_report(O1, charged(eur(19000)), NOW) is True
        assert status(booking) is BookingStatus.NEEDS_REVIEW
        assert booking.attempt(O1).charged == eur(19000)

    @pytest.mark.parametrize(
        ("failure", "failed_status"),
        [(DECLINED, BookingStatus.DECLINED), (EXPIRED, BookingStatus.EXPIRED)],
    )
    def test_a_failure_then_a_new_attempt(
        self, failure: NotCharged, failed_status: BookingStatus
    ) -> None:
        booking = with_checkout(new_booking(), O1)
        assert booking.apply_report(O1, failure, NOW) is True
        assert status(booking) is failed_status
        assert booking.can_retry_payment

        with_checkout(booking, O2)
        assert status(booking) is BookingStatus.AWAITING_PAYMENT
        assert booking.open_checkout_url == "https://pay.example/o2"

    def test_a_late_success_of_a_failed_order_still_counts(self) -> None:
        # Money taken is money taken, whatever we believed about the order before.
        booking = with_checkout(new_booking(), O1)
        booking.apply_report(O1, DECLINED, NOW)
        booking.apply_report(O1, charged(), NOW)
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
        with pytest.raises(BookingError):
            with_checkout(new_booking(), O1).start_attempt(O2, "fake", NOW)
        with pytest.raises(BookingError):
            paid_booking().start_attempt(O2, "fake", NOW)

    def test_a_failed_checkout_frees_the_way_for_a_new_attempt(self) -> None:
        booking = new_booking()
        booking.start_attempt(O1, "fake", NOW)
        booking.mark_checkout_failed(O1)
        assert booking.attempt(O1).status is AttemptStatus.FAILED
        assert booking.can_retry_payment
        with pytest.raises(BookingError):
            booking.attach_checkout(O1, "https://late.example", "p")


class TestReviewIsSticky:
    """Whatever the provider reports afterwards, a flagged booking waits for a human."""

    def test_a_failure_while_flagged_keeps_the_flag(self) -> None:
        booking = with_checkout(new_booking(), O1)
        booking.apply_report(O1, DECLINED, NOW)
        with_checkout(booking, O2)
        # Contradicting reports: the declined order turns out charged, with a wrong amount...
        booking.apply_report(O1, charged(eur(30000)), NOW)
        # ...and then the open checkout is declined.
        assert booking.apply_report(O2, DECLINED, NOW) is True

        assert status(booking) is BookingStatus.NEEDS_REVIEW
        assert not booking.can_retry_payment, "no new checkout while a human sorts it out"

    def test_a_correct_payment_after_a_flag_does_not_clear_it(self) -> None:
        booking = with_checkout(new_booking(), O1)
        booking.apply_report(O1, DECLINED, NOW)
        with_checkout(booking, O2)
        # The old tab's order turns out charged with a wrong amount...
        booking.apply_report(O1, charged(eur(30000)), NOW)
        # ...and then the open checkout is paid correctly.
        assert booking.apply_report(O2, charged(), NOW) is True

        assert status(booking) is BookingStatus.NEEDS_REVIEW
        assert booking.paid_at is None
        assert booking.review_reason is not None
        assert "o2" in booking.review_reason, "the human must see both payments"


class TestRefunds:
    def test_running_totals_from_the_provider(self) -> None:
        booking = paid_booking()
        assert booking.apply_report(O1, charged(refunded=eur(5000)), NOW) is True
        assert status(booking) is BookingStatus.PAID
        assert booking.attempt(O1).refunded == eur(5000)

        # Repeated and stale totals change nothing.
        assert booking.apply_report(O1, charged(refunded=eur(5000)), NOW) is False
        assert booking.apply_report(O1, charged(refunded=eur(1000)), NOW) is False

        assert booking.apply_report(O1, charged(refunded=PRICE), NOW) is True
        assert status(booking) is BookingStatus.REFUNDED

    def test_a_zero_refund_is_no_change(self) -> None:
        booking = paid_booking()
        version_of_truth = booking.attempt(O1).refunded
        assert booking.apply_report(O1, charged(), NOW) is False
        assert booking.attempt(O1).refunded == version_of_truth

    def test_a_refund_above_the_charge_is_flagged_not_raised(self) -> None:
        booking = paid_booking()
        assert booking.apply_report(O1, charged(PRICE, eur(20001)), NOW) is True
        assert status(booking) is BookingStatus.NEEDS_REVIEW

    def test_refunding_an_overcharge_keeps_the_flag(self) -> None:
        # Charged 300 for a 200 booking, then refunded in full: still a case for a human.
        booking = flagged_booking()
        assert booking.apply_report(O1, charged(eur(30000), eur(30000)), NOW) is True
        assert status(booking) is BookingStatus.NEEDS_REVIEW
        assert booking.attempt(O1).refunded == eur(30000)

    def test_refunding_part_of_an_overcharge_does_not_settle_it(self) -> None:
        booking = flagged_booking()
        booking.apply_report(O1, charged(eur(30000), PRICE), NOW)
        assert status(booking) is BookingStatus.NEEDS_REVIEW, "100 still charged"

    def test_a_refund_in_another_currency_is_flagged(self) -> None:
        booking = paid_booking()
        booking.apply_report(O1, Charged(Money(20000, Currency.USD), Money(100, Currency.USD)), NOW)
        assert status(booking) is BookingStatus.NEEDS_REVIEW


# --- retention: the privacy policy keeps an unpaid booking's form for 30 days ----------------


def test_a_booking_nobody_paid_for_goes_after_thirty_days() -> None:
    booking = with_checkout(new_booking(), O1)

    booking.apply_report(O1, DECLINED, NOW)

    assert booking.discard_after == NOW + timedelta(days=30)


def test_a_booking_that_took_money_is_kept() -> None:
    booking = with_checkout(new_booking(), O1)

    booking.apply_report(O1, charged(refunded=PRICE), NOW)

    # Refunded in full, yet money moved: records and disputes need the booking.
    assert booking.status is BookingStatus.REFUNDED
    assert booking.discard_after is None


# --- owner notices: stored with the booking, so none is lost when the messenger is down ------


def test_a_payment_leaves_one_notice_for_the_owner() -> None:
    booking = with_checkout(new_booking(), O1)

    booking.apply_report(O1, charged(), NOW)
    booking.apply_report(O1, charged(), NOW)
    booking.apply_report(O1, charged(refunded=eur(5000)), NOW)

    # A repeat and a partial refund leave it paid: still the one notice.
    assert booking.unsent_notices == [OwnerNotice(NoticeKind.PAID, NOW)]


def test_each_new_problem_leaves_a_notice_with_its_reason() -> None:
    booking = with_checkout(new_booking(), O1)

    booking.apply_report(O1, charged(eur(30000)), NOW)
    first = booking.review_reason
    booking.apply_report(O1, charged(eur(30000), refunded=eur(30001)), NOW)
    booking.apply_report(O1, charged(eur(30000), refunded=eur(30001)), NOW)  # a repeat: no news

    assert booking.unsent_notices == [
        OwnerNotice(NoticeKind.NEEDS_REVIEW, NOW, first),
        OwnerNotice(NoticeKind.NEEDS_REVIEW, NOW, booking.review_reason),
    ]
    assert first != booking.review_reason


def test_a_failed_payment_leaves_no_notice() -> None:
    booking = with_checkout(new_booking(), O1)

    booking.apply_report(O1, DECLINED, NOW)

    assert booking.unsent_notices == []


def test_a_sent_notice_leaves_the_booking() -> None:
    booking = with_checkout(new_booking(), O1)
    booking.apply_report(O1, charged(), NOW)
    (notice,) = booking.unsent_notices

    booking.notice_sent(notice)
    booking.notice_sent(notice)  # sent by a concurrent run as well: nothing to do

    assert booking.unsent_notices == []
