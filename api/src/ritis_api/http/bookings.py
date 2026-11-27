from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Header, Path

from ritis_api.app.confirm_payment import ConfirmPayment
from ritis_api.app.open_booking import OpenBooking, StartBooking
from ritis_api.domain.booking import Customer
from ritis_api.domain.identifiers import BookingId
from ritis_api.http.schemas import BookingCreate, BookingIdParam, BookingView

IdempotencyKey = Annotated[
    str, Header(alias="Idempotency-Key", min_length=16, max_length=100, pattern=r"^[A-Za-z0-9_-]+$")
]


def bookings_router(open_booking: OpenBooking, confirm_payment: ConfirmPayment) -> APIRouter:
    router = APIRouter(prefix="/api/bookings")

    @router.post("", status_code=201)
    def create(body: BookingCreate, idempotency_key: IdempotencyKey) -> BookingView:
        customer = Customer(
            name=body.name, contact=body.contact, about=body.about, links=body.links
        )
        command = StartBooking(
            idempotency_key=idempotency_key, booking_format=body.format, customer=customer
        )
        return BookingView.of(open_booking.start(command))

    @router.get("/{booking_id}")
    def status(booking_id: Annotated[BookingIdParam, Path()]) -> BookingView:
        # The booking page polls this after the checkout, so it re-checks an open payment.
        return BookingView.of(confirm_payment.refresh(BookingId(booking_id)))

    @router.post("/{booking_id}/payments")
    def pay_again(booking_id: Annotated[BookingIdParam, Path()]) -> BookingView:
        return BookingView.of(open_booking.retry(BookingId(booking_id)))

    return router
