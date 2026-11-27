from __future__ import annotations

from pathlib import Path

import pytest
from pydantic import ValidationError

from ritis_api.app.catalog import load_catalog
from ritis_api.domain.money import Currency, Money

SHARED_CATALOG = Path(__file__).resolve().parents[3] / "shared" / "catalog.json"


def test_reads_the_catalog_the_site_is_built_from() -> None:
    assert load_catalog(SHARED_CATALOG).call_price == Money(20000, Currency.EUR)


@pytest.mark.parametrize(
    "content",
    [
        '{"currency": "EUR", "call": {"amount_minor": 0}}',
        '{"currency": "RUB", "call": {"amount_minor": 100}}',
        '{"currency": "EUR", "call": {"amount_minor": 100, "discount": 5}}',
    ],
)
def test_rejects_a_broken_catalog(tmp_path: Path, content: str) -> None:
    path = tmp_path / "catalog.json"
    path.write_text(content, encoding="utf-8")
    with pytest.raises(ValidationError):
        load_catalog(path)
