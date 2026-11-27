from __future__ import annotations

import pytest

from ritis_api.domain.money import Currency, Money


def test_only_whole_non_negative_minor_units() -> None:
    with pytest.raises(TypeError):
        Money(19.99, Currency.EUR)  # type: ignore[arg-type]
    with pytest.raises(TypeError):
        Money(True, Currency.EUR)
    with pytest.raises(ValueError, match="negative"):
        Money(-1, Currency.EUR)


def test_arithmetic_and_comparison_refuse_mixed_currencies() -> None:
    eur, usd = Money(150, Currency.EUR), Money(150, Currency.USD)
    assert eur + Money(50, Currency.EUR) == Money(200, Currency.EUR)
    assert eur - Money(50, Currency.EUR) == Money(100, Currency.EUR)
    with pytest.raises(ValueError, match="currency mismatch"):
        _ = eur + usd
    with pytest.raises(ValueError, match="currency mismatch"):
        _ = eur < usd
    with pytest.raises(ValueError, match="negative"):
        _ = Money(1, Currency.EUR) - eur
