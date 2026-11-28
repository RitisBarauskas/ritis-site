from __future__ import annotations

import copy
import json
from collections.abc import Callable
from datetime import date
from pathlib import Path
from typing import Any

import pytest
from pydantic import ValidationError

from ritis_api.app.catalog import load_catalog
from ritis_api.domain.booking import BookingFormat, Language
from ritis_api.domain.money import Currency, Money

SHARED_CATALOG = Path(__file__).resolve().parents[3] / "shared" / "catalog.json"


def described(name: str) -> dict[str, str]:
    return {"ru": f"{name} ru", "ka": f"{name} ka", "en": f"{name} en"}


VALID: dict[str, Any] = {
    "currency": "EUR",
    "offer_revision": "2026-11-27",
    "formats": {
        "start": {"price_minor": 100, "description": described("start")},
        "launch": {"price_minor": 300, "description": described("launch")},
        "foundation": {
            "starts_with": "start",
            "from_minor": 1000,
            "description": described("foundation"),
        },
        "subscription": {
            "starts_with": "start",
            "from_minor": 500,
            "per": "month",
            "description": described("subscription"),
        },
    },
}


def write(tmp_path: Path, content: dict[str, Any]) -> Path:
    path = tmp_path / "catalog.json"
    path.write_text(json.dumps(content), encoding="utf-8")
    return path


def test_reads_the_catalog_the_site_is_built_from() -> None:
    catalog = load_catalog(SHARED_CATALOG)

    euros = {fmt: catalog.offer(fmt).price for fmt in BookingFormat}
    assert euros == {
        BookingFormat.START: Money(60000, Currency.GEL),
        BookingFormat.LAUNCH: Money(150000, Currency.GEL),
        BookingFormat.FOUNDATION: Money(60000, Currency.GEL),
        BookingFormat.SUBSCRIPTION: Money(60000, Currency.GEL),
    }
    assert catalog.offer_revision == date(2026, 11, 27)
    # The customer sees at the payment provider which format they paid for, in their language.
    descriptions = {
        catalog.offer(fmt).description(lang) for fmt in BookingFormat for lang in Language
    }
    assert len(descriptions) == len(BookingFormat) * len(Language)
    assert catalog.offer(BookingFormat.START).description(Language.EN).startswith("ritis.dev — ")


def test_a_package_is_booked_at_the_price_of_the_format_it_starts_with(tmp_path: Path) -> None:
    catalog = load_catalog(write(tmp_path, VALID))

    assert catalog.offer(BookingFormat.FOUNDATION).price == Money(100, Currency.EUR)
    assert catalog.offer(BookingFormat.LAUNCH).price == Money(300, Currency.EUR)
    assert catalog.offer(BookingFormat.FOUNDATION).description(Language.KA) == "foundation ka"


def _drop_format(c: dict[str, Any]) -> None:
    del c["formats"]["launch"]


def _unknown_format(c: dict[str, Any]) -> None:
    c["formats"]["teardown"] = {"price_minor": 100, "description": described("free")}


def _both_prices(c: dict[str, Any]) -> None:
    c["formats"]["foundation"]["price_minor"] = 100


def _no_price(c: dict[str, Any]) -> None:
    del c["formats"]["foundation"]["starts_with"]


def _starts_with_a_package(c: dict[str, Any]) -> None:
    c["formats"]["foundation"]["starts_with"] = "subscription"


def _zero_price(c: dict[str, Any]) -> None:
    c["formats"]["start"]["price_minor"] = 0


def _other_currency(c: dict[str, Any]) -> None:
    c["currency"] = "RUB"


def _unknown_field(c: dict[str, Any]) -> None:
    c["formats"]["start"]["discount"] = 5


def _old_layout(c: dict[str, Any]) -> None:
    c["call"] = {"amount_minor": 20000}


def _empty_description(c: dict[str, Any]) -> None:
    c["formats"]["launch"]["description"]["en"] = ""


def _no_georgian_description(c: dict[str, Any]) -> None:
    del c["formats"]["launch"]["description"]["ka"]


def _description_in_an_unknown_language(c: dict[str, Any]) -> None:
    c["formats"]["launch"]["description"]["de"] = "launch de"


def _no_offer_revision(c: dict[str, Any]) -> None:
    del c["offer_revision"]


@pytest.mark.parametrize(
    "breakage",
    [
        _drop_format,
        _unknown_format,
        _both_prices,
        _no_price,
        _starts_with_a_package,
        _zero_price,
        _other_currency,
        _unknown_field,
        _old_layout,
        _empty_description,
        _no_georgian_description,
        _description_in_an_unknown_language,
        _no_offer_revision,
    ],
)
def test_rejects_a_broken_catalog(
    tmp_path: Path, breakage: Callable[[dict[str, Any]], None]
) -> None:
    content = copy.deepcopy(VALID)
    breakage(content)
    with pytest.raises(ValidationError):
        load_catalog(write(tmp_path, content))
