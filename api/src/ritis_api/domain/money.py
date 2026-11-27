from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum


class Currency(StrEnum):
    EUR = "EUR"
    USD = "USD"
    GEL = "GEL"


@dataclass(frozen=True, slots=True)
class Money:
    """An amount in minor units (cents, tetri) of one currency. Never a float."""

    amount_minor: int
    currency: Currency

    def __post_init__(self) -> None:
        # bool is an int subclass; True must not silently become 1 cent.
        if isinstance(self.amount_minor, bool) or not isinstance(self.amount_minor, int):
            raise TypeError(f"amount_minor must be an int, got {type(self.amount_minor).__name__}")
        if self.amount_minor < 0:
            raise ValueError("amount_minor must not be negative")

    @classmethod
    def zero(cls, currency: Currency) -> Money:
        return cls(0, currency)

    def _check_same_currency(self, other: Money) -> None:
        if self.currency is not other.currency:
            raise ValueError(f"currency mismatch: {self.currency} vs {other.currency}")

    def __add__(self, other: Money) -> Money:
        self._check_same_currency(other)
        return Money(self.amount_minor + other.amount_minor, self.currency)

    def __sub__(self, other: Money) -> Money:
        self._check_same_currency(other)
        return Money(self.amount_minor - other.amount_minor, self.currency)

    def __lt__(self, other: Money) -> bool:
        self._check_same_currency(other)
        return self.amount_minor < other.amount_minor

    def __le__(self, other: Money) -> bool:
        self._check_same_currency(other)
        return self.amount_minor <= other.amount_minor

    def __str__(self) -> str:
        return f"{self.amount_minor / 100:.2f} {self.currency}"
