#!/usr/bin/env python3
from __future__ import annotations

import csv
import datetime as dt
import io

from scripts import crcl_usdc_rate_watch as watch

FRED_SOFR_CSV = "https://fred.stlouisfed.org/graph/fredgraph.csv?id=SOFR"
FRED_SOFR_PAGE = "https://fred.stlouisfed.org/series/SOFR"


def fred_sofr() -> dict:
    raw = watch.fetch(FRED_SOFR_CSV).decode("utf-8", errors="replace")
    rows: list[tuple[dt.date, float]] = []
    for row in csv.DictReader(io.StringIO(raw)):
        date_text = (row.get("DATE") or row.get("observation_date") or "").strip()
        value_text = (row.get("SOFR") or "").strip()
        if not date_text or not value_text or value_text == ".":
            continue
        try:
            rows.append((dt.date.fromisoformat(date_text), float(value_text)))
        except (ValueError, TypeError):
            continue
    if len(rows) < 2:
        raise RuntimeError("FRED SOFR has fewer than two valid observations")
    rows.sort(key=lambda x: x[0])
    latest, prev = rows[-1], rows[-2]
    return {
        "date": latest[0].isoformat(),
        "rate": latest[1],
        "prev_date": prev[0].isoformat(),
        "prev_rate": prev[1],
        "daily_bp": round((latest[1] - prev[1]) * 100, 1),
        "source": "FRED 재게시·원출처 Federal Reserve Bank of New York",
        "source_url": FRED_SOFR_PAGE,
    }


# The NY Fed webpage can change its HTML structure. Use the official SOFR series
# republished by FRED (source: Federal Reserve Bank of New York) as a stable
# machine-readable fallback while preserving the NY Fed as the underlying source.
watch.nyfed_sofr = fred_sofr
watch.NYFED_SOFR_URL = FRED_SOFR_PAGE
watch.main()
