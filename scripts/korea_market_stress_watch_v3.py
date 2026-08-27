#!/usr/bin/env python3
from __future__ import annotations

from typing import Any

import requests

import korea_market_stress_watch_v2 as watch

# Canonical BOK base-rate history page. The older menu route can expose a partial table.
watch.BOK_RATE_URL = "https://www.bok.or.kr/portal/singl/baseRate/list.do?menuNo=200656"

NAVER_FX_PRICES_URL = (
    "https://api.stock.naver.com/marketindex/exchange/FX_USDKRW/prices?page=1&pageSize=5"
)


def fetch_usdkrw_verified() -> dict[str, Any]:
    r = requests.get(NAVER_FX_PRICES_URL, headers=watch.HEADERS, timeout=35)
    r.raise_for_status()
    payload = r.json()
    rows = payload.get("result") if isinstance(payload, dict) else payload
    rows = rows or []
    parsed: list[tuple[str, float]] = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        d = str(row.get("localTradedAt") or row.get("localDate") or "")[:10]
        p = row.get("closePrice")
        if d and p not in (None, ""):
            parsed.append((d, watch.as_float(p)))
    if len(parsed) < 2:
        raise RuntimeError("네이버 원/달러 일별 시세가 2개 미만")
    parsed = sorted(dict(parsed).items())
    (d0, v0), (d1, v1) = parsed[-2:]
    return {
        "date": d1,
        "value": v1,
        "prev_date": d0,
        "prev_value": v0,
        "change_krw": round(v1 - v0, 4),
        "change_pct": round((v1 / v0 - 1) * 100, 4),
        "source": NAVER_FX_PRICES_URL,
    }


watch.fetch_usdkrw = fetch_usdkrw_verified

if __name__ == "__main__":
    raise SystemExit(watch.main())
