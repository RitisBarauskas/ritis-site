"""Owner notices: delivered right after the change, kept when the messenger is down, swept later."""

from __future__ import annotations

from ritis_api.adapters.memory import InMemoryBookingRepository
from ritis_api.app.confirm_payment import ConfirmPayment
from ritis_api.app.deliver_notices import DeliverNotices
from ritis_api.app.open_booking import OpenBooking
from ritis_api.domain.booking import Booking, BookingStatus, NoticeKind, OwnerNotice
from tests.conftest import make_confirm_payment, order_of, start_command
from tests.fakes import Clock, FakeProvider, RacingRepository, RecordingNotifier


def test_a_delivered_notice_leaves_the_stored_booking(
    open_booking: OpenBooking,
    confirm_payment: ConfirmPayment,
    provider: FakeProvider,
    notifier: RecordingNotifier,
    repository: InMemoryBookingRepository,
) -> None:
    booking = open_booking.start(start_command())
    provider.approve(order_of(booking))

    confirm_payment.confirm(order_of(booking))

    assert notifier.paid == [booking.id]
    assert repository.get(booking.id).unsent_notices == []


def test_a_notice_waits_out_a_down_messenger_and_the_sweep_delivers_it(
    open_booking: OpenBooking,
    confirm_payment: ConfirmPayment,
    provider: FakeProvider,
    notifier: RecordingNotifier,
    repository: InMemoryBookingRepository,
) -> None:
    booking = open_booking.start(start_command())
    provider.approve(order_of(booking))
    notifier.broken = True

    confirm_payment.confirm(order_of(booking))

    stored = repository.get(booking.id)
    assert stored.status is BookingStatus.PAID, "a down messenger must not lose the payment"
    assert [n.kind for n in stored.unsent_notices] == [NoticeKind.PAID]

    sweep = DeliverNotices(repository=repository, notifier=notifier)
    assert sweep.sweep() == 1, "still down: the booking keeps its notice"
    notifier.broken = False
    assert sweep.sweep() == 0

    assert notifier.paid == [booking.id]
    assert repository.get(booking.id).unsent_notices == []


def test_marking_a_notice_sent_survives_a_concurrent_change(
    open_booking: OpenBooking,
    confirm_payment: ConfirmPayment,
    provider: FakeProvider,
    notifier: RecordingNotifier,
    repository: InMemoryBookingRepository,
) -> None:
    booking = open_booking.start(start_command())
    provider.approve(order_of(booking))
    notifier.broken = True
    confirm_payment.confirm(order_of(booking))
    notifier.broken = False

    def competitor() -> None:
        # A note by someone else lands between our read and our write of the booking.
        other = repository.get(booking.id)
        other.review_reason = "looked at by hand"
        repository.save(other)

    racing = RacingRepository(repository, competitor, race_on="save")
    DeliverNotices(repository=racing, notifier=notifier).sweep()

    stored = repository.get(booking.id)
    assert stored.unsent_notices == []
    assert stored.review_reason == "looked at by hand", "and their change is kept"
    assert notifier.paid == [booking.id]


class CrashingNotifier:
    """A notifier with a bug: it fails with something other than NotifierError."""

    def send(self, notice: OwnerNotice, booking: Booking) -> None:
        raise KeyError(f"no message template for {notice.kind} of {booking.format}")


def test_a_bug_in_the_notifier_does_not_fail_the_recorded_payment(
    open_booking: OpenBooking,
    provider: FakeProvider,
    repository: InMemoryBookingRepository,
    clock: Clock,
) -> None:
    booking = open_booking.start(start_command())
    provider.approve(order_of(booking))
    confirm = make_confirm_payment(repository, provider, CrashingNotifier(), clock)

    assert confirm.confirm(order_of(booking)).status is BookingStatus.PAID

    stored = repository.get(booking.id)
    assert stored.status is BookingStatus.PAID
    assert [n.kind for n in stored.unsent_notices] == [NoticeKind.PAID], "kept for the sweep"
