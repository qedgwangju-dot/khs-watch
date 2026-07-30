from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal


@dataclass(frozen=True)
class Conversion:
    original_amount: Decimal
    currency: str
    rate_date: str | None
    rate: Decimal | None
    amount_krw: int | None
    formula: str


def convert_to_krw(amount: Decimal, currency: str, rate: Decimal | None, rate_date: str | None) -> Conversion:
    if currency.upper() == "KRW":
        return Conversion(amount, "KRW", rate_date, Decimal(1), int(amount), f"{amount} × 1")
    if rate is None:
        return Conversion(amount, currency.upper(), None, None, None, "환율 미확인")
    return Conversion(amount, currency.upper(), rate_date, rate, int(amount * rate), f"{amount} × {rate}")

