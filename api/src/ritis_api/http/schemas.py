from __future__ import annotations

from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field, field_validator

from ritis_api.domain.booking import Booking, BookingFormat, BookingStatus, Language
from ritis_api.domain.money import Currency

BOOKING_ID_PATTERN = r"^[0-9a-f]{32}$"
BookingIdParam = Annotated[str, Field(pattern=BOOKING_ID_PATTERN)]


class BookingCreate(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    format: BookingFormat
    name: str = Field(min_length=1, max_length=100)
    contact: str = Field(min_length=3, max_length=200)
    about: str = Field(default="", max_length=2000)
    links: str = Field(default="", max_length=1000)
    # The checkout requires the customer to accept the site's policies before paying.
    consent: bool
    # The refund terms keep the cost of work done only if the customer asked to start at once.
    start_immediately: bool
    # The site's language: the offer the customer read is in it, and so is the checkout.
    language: Language
    # Honeypot: hidden from people, filled in by bots.
    website: str = Field(default="", max_length=200)

    @field_validator("consent")
    @classmethod
    def _consent_given(cls, value: bool) -> bool:
        if not value:
            raise ValueError("the policies must be accepted before paying")
        return value

    @field_validator("start_immediately")
    @classmethod
    def _start_requested(cls, value: bool) -> bool:
        if not value:
            raise ValueError("work starts right after payment, and the customer must ask for it")
        return value

    @field_validator("website")
    @classmethod
    def _honeypot_empty(cls, value: str) -> str:
        if value:
            raise ValueError("rejected")
        return value


class BookingView(BaseModel):
    """What the browser may see about a booking: no personal data."""

    id: str
    status: BookingStatus
    format: BookingFormat
    amount_minor: int
    currency: Currency
    checkout_url: str | None
    can_retry_payment: bool

    @classmethod
    def of(cls, booking: Booking) -> BookingView:
        return cls(
            id=booking.id,
            status=booking.status,
            format=booking.format,
            amount_minor=booking.price.amount_minor,
            currency=booking.price.currency,
            checkout_url=booking.open_checkout_url,
            can_retry_payment=booking.can_retry_payment,
        )
