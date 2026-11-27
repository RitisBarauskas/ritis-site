"""Opening a paid booking: create it and give the customer a checkout to pay through."""

from __future__ import annotations

import re
from dataclasses import dataclass

from ritis_api.app.catalog import Catalog
from ritis_api.app.runtime import Clock, IdFactory
from ritis_api.domain.booking import Booking, BookingFormat, BookingStatus, Customer
from ritis_api.domain.errors import BookingError
from ritis_api.domain.identifiers import BookingId, OrderId
from ritis_api.domain.payment import AttemptStatus
from ritis_api.ports.payments import CheckoutRequest, PaymentProvider, PaymentProviderError
from ritis_api.ports.storage import (
    BookingRepository,
    ConcurrentModificationError,
    DuplicateIdempotencyKeyError,
)

_EMAIL = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


@dataclass(frozen=True, slots=True)
class CheckoutSettings:
    # Public base URL of this API: the provider notifies and returns the customer here.
    api_base_url: str
    lifetime_seconds: int
    language: str = "ru"
    description: str = "ritis.dev — звонок 60 минут"

    def return_url(self, booking_id: BookingId) -> str:
        return f"{self._base}/api/payments/flitt/return?booking={booking_id}"

    def notification_url(self) -> str:
        return f"{self._base}/api/payments/flitt/notification"

    @property
    def _base(self) -> str:
        return self.api_base_url.rstrip("/")


@dataclass(frozen=True, slots=True)
class StartBooking:
    # From the client: repeating a request with the same key must not create a second booking.
    idempotency_key: str
    booking_format: BookingFormat
    customer: Customer


class OpenBooking:
    def __init__(
        self,
        *,
        repository: BookingRepository,
        provider: PaymentProvider,
        catalog: Catalog,
        settings: CheckoutSettings,
        clock: Clock,
        new_id: IdFactory,
    ) -> None:
        self._repository = repository
        self._provider = provider
        self._catalog = catalog
        self._settings = settings
        self._clock = clock
        self._new_id = new_id

    def start(self, command: StartBooking) -> Booking:
        existing = self._repository.find_by_idempotency_key(command.idempotency_key)
        if existing is not None:
            return self._ensure_checkout(existing)
        booking = Booking.new(
            booking_id=BookingId(self._new_id()),
            idempotency_key=command.idempotency_key,
            booking_format=command.booking_format,
            customer=command.customer,
            price=self._catalog.call_price,
            now=self._clock(),
        )
        order_id = self._new_attempt(booking)
        try:
            self._repository.add(booking)
        except DuplicateIdempotencyKeyError:
            # The same request is being served concurrently and is opening the checkout itself.
            twin = self._repository.find_by_idempotency_key(command.idempotency_key)
            if twin is None:
                raise
            return twin
        return self._open_checkout(booking, order_id)

    def retry(self, booking_id: BookingId) -> Booking:
        """Pay again after a declined or expired checkout; an open checkout is returned as is."""
        booking = self._ensure_checkout(self._repository.get(booking_id))
        if booking.open_checkout_url is None:
            raise BookingError(f"booking {booking_id} cannot be paid in {booking.status}")
        return booking

    def _ensure_checkout(self, booking: Booking) -> Booking:
        if booking.open_checkout_url is not None:
            return booking
        attempt = booking.current_attempt
        if (
            booking.status is BookingStatus.AWAITING_PAYMENT
            and attempt is not None
            and attempt.status is AttemptStatus.PENDING
        ):
            # An earlier call stopped before the provider answered. Its order is abandoned
            # rather than re-sent: a fresh order id can never collide at the provider.
            booking.mark_checkout_failed(attempt.order_id)
        if not booking.can_retry_payment:
            return booking
        return self._open_checkout(booking, self._new_attempt(booking))

    def _open_checkout(self, booking: Booking, order_id: OrderId) -> Booking:
        try:
            checkout = self._provider.open_checkout(self._checkout_request(booking, order_id))
        except PaymentProviderError:
            booking.mark_checkout_failed(order_id)
            self._save_or_reload(booking)
            raise
        booking.attach_checkout(order_id, checkout.checkout_url, checkout.provider_payment_id)
        return self._save_or_reload(booking)

    def _new_attempt(self, booking: Booking) -> OrderId:
        return booking.start_attempt(OrderId(self._new_id()), self._clock()).order_id

    def _checkout_request(self, booking: Booking, order_id: OrderId) -> CheckoutRequest:
        contact = booking.customer.contact.strip()
        return CheckoutRequest(
            order_id=order_id,
            amount=booking.price,
            description=self._settings.description,
            return_url=self._settings.return_url(booking.id),
            notification_url=self._settings.notification_url(),
            lifetime_seconds=self._settings.lifetime_seconds,
            language=self._settings.language,
            customer_email=contact if _EMAIL.match(contact) else None,
        )

    def _save_or_reload(self, booking: Booking) -> Booking:
        try:
            self._repository.save(booking)
        except ConcurrentModificationError:
            # A concurrent repeat of the same request won; its state is the answer.
            return self._repository.get(booking.id)
        return booking
