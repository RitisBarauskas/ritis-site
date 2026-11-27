"""What booking each format costs, how it reads at the provider, and which offer is in force.

Read from shared/catalog.json: the same file the site is built from.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Literal, Self

from pydantic import BaseModel, ConfigDict, Field, model_validator

from ritis_api.domain.booking import BookingFormat
from ritis_api.domain.money import Currency, Money


class _Format(BaseModel):
    model_config = ConfigDict(extra="forbid")
    # A format is booked either at its own price or as the format it starts with.
    price_minor: int | None = Field(default=None, gt=0)
    starts_with: BookingFormat | None = None
    description: str = Field(min_length=1, max_length=200)
    # The full price of a package, which the site shows; the booking does not charge it.
    from_minor: int | None = Field(default=None, gt=0)
    per: Literal["month"] | None = None

    @model_validator(mode="after")
    def _priced_one_way(self) -> Self:
        if (self.price_minor is None) == (self.starts_with is None):
            raise ValueError("a format has either a price of its own or a format it starts with")
        return self


class _CatalogFile(BaseModel):
    model_config = ConfigDict(extra="forbid")
    currency: Currency
    # The prices are part of the offer: a new price is a new revision of it.
    offer_revision: date
    formats: dict[BookingFormat, _Format]

    @model_validator(mode="after")
    def _every_format_bookable(self) -> Self:
        missing = set(BookingFormat) - set(self.formats)
        if missing:
            raise ValueError(f"no catalog entry for {sorted(missing)}")
        for name, entry in self.formats.items():
            if (
                entry.starts_with is not None
                and self.formats[entry.starts_with].price_minor is None
            ):
                raise ValueError(f"{name} starts with {entry.starts_with}, which has no price")
        return self


@dataclass(frozen=True, slots=True)
class Offer:
    price: Money  # charged when the format is booked
    description: str  # what the customer sees at the payment provider


@dataclass(frozen=True, slots=True)
class Catalog:
    offers: Mapping[BookingFormat, Offer]
    offer_revision: date

    def offer(self, booking_format: BookingFormat) -> Offer:
        return self.offers[booking_format]


def load_catalog(path: Path) -> Catalog:
    parsed = _CatalogFile.model_validate_json(path.read_bytes())
    own = {fmt: e.price_minor for fmt, e in parsed.formats.items() if e.price_minor is not None}

    def price(entry: _Format, booking_format: BookingFormat) -> Money:
        return Money(own[entry.starts_with or booking_format], parsed.currency)

    return Catalog(
        {fmt: Offer(price(entry, fmt), entry.description) for fmt, entry in parsed.formats.items()},
        parsed.offer_revision,
    )
