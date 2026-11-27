"""Prices, read from shared/catalog.json: the same file the site is built from."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from pydantic import BaseModel, ConfigDict, Field

from ritis_api.domain.money import Currency, Money


class _Call(BaseModel):
    model_config = ConfigDict(extra="forbid")
    amount_minor: int = Field(gt=0)


class _CatalogFile(BaseModel):
    # Package prices are display-only for the site; the API charges for the call alone.
    model_config = ConfigDict(extra="ignore")
    currency: Currency
    call: _Call


@dataclass(frozen=True, slots=True)
class Catalog:
    call_price: Money


def load_catalog(path: Path) -> Catalog:
    parsed = _CatalogFile.model_validate_json(path.read_bytes())
    return Catalog(call_price=Money(parsed.call.amount_minor, parsed.currency))
