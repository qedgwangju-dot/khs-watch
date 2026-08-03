#!/usr/bin/env python3
"""Configuration and data models for yen-sector reaction monitoring."""
from __future__ import annotations

import datetime as dt
import math
import statistics
from dataclasses import dataclass
from zoneinfo import ZoneInfo

UTC = dt.timezone.utc
KST = ZoneInfo("Asia/Seoul")

YAHOO_BASES = (
    "https://query1.finance.yahoo.com/v8/finance/chart",
    "https://query2.finance.yahoo.com/v8/finance/chart",
)
USER_AGENT = "Mozilla/5.0 yen-sector-reaction/1.0"
SECTOR_HEADING = "산업·업종 영향"
FINAL_MARKER = "이 경보는 기존 엔캐리 청산 확정 경보와 별개입니다."

INTRADAY_MIN_RELATIVE_PCT = 0.50
SESSION_MIN_RELATIVE_PCT = 0.80
SIGNIFICANCE_Z = 2.0
MIN_COMPONENTS_FOR_BREADTH = 2
DATA_MAX_AGE_MINUTES = 20
THIRTY_MINUTE_DELAY = 30
FOLLOWUP_RETRY_MINUTES = 60
CLOSE_CHECK_HOUR = 15
CLOSE_CHECK_MINUTE = 38
HISTORY_LIMIT = 20


@dataclass(frozen=True)
class SectorSpec:
    key: str
    name: str
    country: str
    benchmark: str
    expected_sign: int
    role: str
    primary: tuple[str, ...]
    components: tuple[str, ...]


SECTORS: tuple[SectorSpec, ...] = (
    SectorSpec(
        "jp_auto",
        "일본 자동차",
        "JP",
        "1306.T",
        -1,
        "일본 수출주",
        ("1622.T",),
        ("7203.T", "7267.T", "7201.T"),
    ),
    SectorSpec(
        "jp_electronics",
        "일본 전기·정밀",
        "JP",
        "1306.T",
        -1,
        "일본 수출주",
        ("1625.T",),
        ("6758.T", "6501.T", "6503.T"),
    ),
    SectorSpec(
        "jp_machinery",
        "일본 기계",
        "JP",
        "1306.T",
        -1,
        "일본 수출주",
        ("1624.T",),
        ("7011.T", "6301.T", "6367.T"),
    ),
    SectorSpec(
        "jp_utilities",
        "일본 전력·가스",
        "JP",
        "1306.T",
        1,
        "일본 수입원가 수혜",
        ("1627.T",),
        ("9501.T", "9502.T", "9503.T"),
    ),
    SectorSpec(
        "jp_airlines",
        "일본 항공",
        "JP",
        "1306.T",
        1,
        "일본 수입원가 수혜",
        (),
        ("9201.T", "9202.T"),
    ),
    SectorSpec(
        "jp_food",
        "일본 식품",
        "JP",
        "1306.T",
        1,
        "일본 수입원가 수혜",
        ("1617.T",),
        ("2802.T", "2502.T", "2801.T"),
    ),
    SectorSpec(
        "jp_retail",
        "일본 소매",
        "JP",
        "1306.T",
        1,
        "일본 수입원가 수혜",
        ("1630.T",),
        ("3382.T", "8267.T", "7532.T"),
    ),
    SectorSpec(
        "kr_auto",
        "한국 자동차",
        "KR",
        "^KS11",
        1,
        "한국 상대 수혜",
        ("091180.KS",),
        ("005380.KS", "000270.KS", "012330.KS"),
    ),
    SectorSpec(
        "kr_semis",
        "한국 반도체",
        "KR",
        "^KS11",
        0,
        "직접 환율 영향 판단 보류",
        ("091160.KS",),
        ("005930.KS", "000660.KS"),
    ),
)


@dataclass(frozen=True)
class QuoteSeries:
    symbol: str
    latest_price: float
    latest_epoch: float
    previous_close: float
    session_change_pct: float
    points: tuple[tuple[float, float], ...]
    exchange_timezone: str


@dataclass(frozen=True)
class SectorResult:
    key: str
    name: str
    country: str
    role: str
    expected_sign: int
    timeframe: str
    sector_change_pct: float
    benchmark_change_pct: float
    relative_pct: float
    sigma_pct: float
    zscore: float
    significant: bool
    aligned: bool | None
    contrary: bool | None
    breadth_pct: float | None
    market_status: str
    data_epoch: float
    component_prices: dict[str, float]
    benchmark_price: float
    source: str


def finite(value: object) -> float | None:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) else None


def median(values: list[float]) -> float | None:
    clean = [value for value in values if math.isfinite(value)]
    return statistics.median(clean) if clean else None


def robust_sigma(values: list[float], floor: float) -> float:
    clean = [value for value in values if math.isfinite(value)]
    if len(clean) < 4:
        return floor
    center = statistics.median(clean)
    mad = statistics.median(abs(value - center) for value in clean)
    sigma = 1.4826 * mad
    return max(floor, sigma)
