#!/usr/bin/env python3
"""Shared KRW conversion helpers using same-date Federal Reserve H.10 FX data."""
from __future__ import annotations

import csv
import datetime as dt
import io
import time
import urllib.parse
import urllib.request
from dataclasses import dataclass

FRED_CSV = "https://fred.stlouisfed.org/graph/fredgraph.csv"
FRED_USDKRW = "https://fred.stlouisfed.org/series/DEXKOUS"
FRED_USDJPY = "https://fred.stlouisfed.org/series/DEXJPUS"
UA = "Mozilla/5.0 khs-watch-krw-fx/1.1"


@dataclass(frozen=True)
class JpyKrwQuote:
    date: str
    usdkrw: float
    usdjpy: float
    krw_per_yen: float

    @property
    def krw_per_100_yen(self) -> float:
        return self.krw_per_yen * 100.0


def _fred_rows(series_id: str, max_rows: int = 60) -> dict[str, float]:
    # fredgraph.csv without a date bound can return decades of history and has
    # occasionally timed out on GitHub-hosted runners.  We only need the latest
    # common H.10 date, so bound the request to recent observations and retry.
    today = dt.datetime.now(dt.timezone.utc).date()
    start = today - dt.timedelta(days=120)
    params = urllib.parse.urlencode({
        "id": series_id,
        "cosd": start.isoformat(),
        "coed": today.isoformat(),
    })
    url = f"{FRED_CSV}?{params}"
    last_error: Exception | None = None
    text = ""
    for attempt in range(1, 4):
        try:
            req = urllib.request.Request(
                url,
                headers={"User-Agent": UA, "Cache-Control": "no-cache", "Accept": "text/csv,*/*"},
            )
            with urllib.request.urlopen(req, timeout=30) as response:
                text = response.read().decode("utf-8-sig", errors="replace")
            if text:
                break
        except Exception as exc:
            last_error = exc
            if attempt < 3:
                time.sleep(attempt * 1.5)
    if not text:
        raise RuntimeError(f"FRED {series_id} retrieval failed: {last_error}")

    rows: list[tuple[str, float]] = []
    for row in csv.DictReader(io.StringIO(text)):
        day = (row.get("DATE") or row.get("observation_date") or "").strip()
        raw = (row.get(series_id) or "").strip()
        if not day or not raw or raw == ".":
            continue
        try:
            rows.append((day, float(raw)))
        except ValueError:
            continue
    if not rows:
        raise RuntimeError(f"FRED {series_id} returned no recent observations")
    return dict(rows[-max_rows:])


def latest_jpy_krw() -> JpyKrwQuote:
    """Return the latest common-date JPY/KRW cross rate.

    DEXKOUS = KRW per USD, DEXJPUS = JPY per USD.
    JPY/KRW = DEXKOUS / DEXJPUS. Different observation dates are never mixed.
    """
    krw = _fred_rows("DEXKOUS")
    jpy = _fred_rows("DEXJPUS")
    common = sorted(set(krw) & set(jpy))
    if not common:
        raise RuntimeError("FRED DEXKOUS/DEXJPUS have no common observation date")
    day = common[-1]
    usdkrw = krw[day]
    usdjpy = jpy[day]
    from fx_api import _validate
    now = dt.datetime.now(dt.timezone.utc)
    usdkrw, day = _validate(usdkrw, day, now)
    usdjpy, _ = _validate(usdjpy, day, now)
    return JpyKrwQuote(day, usdkrw, usdjpy, usdkrw / usdjpy)


def yen_to_krw(yen_amount: float, quote: JpyKrwQuote) -> float:
    return float(yen_amount) * quote.krw_per_yen


def format_krw(won: float) -> str:
    """Format KRW in Korean large-number units without decimal-trillion notation."""
    sign = "-" if won < 0 else ""
    value = int(round(abs(won)))
    jo, rem = divmod(value, 1_000_000_000_000)
    eok, rem = divmod(rem, 100_000_000)
    man, won_rest = divmod(rem, 10_000)
    parts: list[str] = []
    if jo:
        parts.append(f"{jo:,}조")
    if eok:
        parts.append(f"{eok:,}억")
    if not parts and man:
        parts.append(f"{man:,}만")
    if not parts:
        parts.append(f"{won_rest:,}")
    return sign + "".join(parts) + "원"


def format_trillion_yen(trillion_yen: float, quote: JpyKrwQuote, digits: int = 2) -> str:
    won = yen_to_krw(trillion_yen * 1_000_000_000_000.0, quote)
    return f"{trillion_yen:,.{digits}f}조엔 (약 {format_krw(won)})"
