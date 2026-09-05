#!/usr/bin/env python3
from __future__ import annotations

import datetime as dt

from bs4 import BeautifulSoup

from scripts import crypto_liquidity_watch as watch


def btc_etf_flow_strict() -> dict:
    """Parse Farside while rejecting zero-only partial placeholder rows.

    Farside can pre-create a new date with several 0.0 cells while other ETFs
    are still '-'. That is not a real zero-flow print. Treat it as pending so
    it cannot become the latest valid day or shift 5-day windows.
    """
    html = watch.fetch(watch.FARSIDE_BTC_ETF_URL).decode("utf-8", errors="replace")
    soup = BeautifulSoup(html, "html.parser")
    rows: list[dict] = []

    for tr in soup.find_all("tr"):
        cells = [" ".join(td.get_text(" ", strip=True).split()) for td in tr.find_all(["td", "th"])]
        if len(cells) < 3:
            continue
        d = watch.parse_date(cells[0])
        if not d:
            continue

        fund_cells = cells[1:-1]
        normalized = [x.strip() for x in fund_cells]
        numeric_funds = [watch.parse_number(x) for x in normalized if x not in {"", "-", "—"}]
        reported_count = sum(v is not None for v in numeric_funds)
        missing_count = sum(x in {"", "-", "—"} for x in normalized)
        total = watch.parse_number(cells[-1])
        recomputed_total = round(sum(v for v in numeric_funds if v is not None), 1) if numeric_funds else None

        all_reported_zero = bool(numeric_funds) and all((v is None or abs(float(v)) < 1e-12) for v in numeric_funds)
        zero_only_partial_placeholder = (
            missing_count > 0
            and reported_count > 0
            and all_reported_zero
            and (total is None or abs(float(total)) < 1e-12)
        )

        if (reported_count == 0 and missing_count == len(normalized)) or zero_only_partial_placeholder:
            status = "pending"
            total = None
            total_gap = None
            total_validated = False
        else:
            status = "partial" if missing_count > 0 else "complete"
            total_gap = round(total - recomputed_total, 1) if total is not None and recomputed_total is not None else None
            total_validated = total_gap is not None and abs(total_gap) <= 0.6

        rows.append({
            "date": d,
            "total": total,
            "status": status,
            "reported_funds": reported_count,
            "missing_funds": missing_count,
            "recomputed_total": recomputed_total,
            "total_gap": total_gap,
            "total_validated": total_validated,
            "zero_only_partial_placeholder": zero_only_partial_placeholder,
        })

    if not rows:
        raise RuntimeError("Farside BTC ETF flow rows could not be parsed")

    rows.sort(key=lambda x: x["date"])
    source_latest = rows[-1]
    valid_rows = [
        x for x in rows
        if x["total"] is not None and x["status"] != "pending" and x.get("total_validated")
    ]
    if not valid_rows:
        raise RuntimeError("Farside has no validated BTC ETF flow rows")

    latest_valid = valid_rows[-1]
    prev_valid = valid_rows[-2] if len(valid_rows) >= 2 else latest_valid

    last5 = valid_rows[-5:]
    prev5 = valid_rows[-10:-5] if len(valid_rows) >= 10 else []
    last5_sum = round(sum(x["total"] for x in last5), 1)
    prev5_sum = round(sum(x["total"] for x in prev5), 1) if prev5 else None

    day_change = round(latest_valid["total"] - prev_valid["total"], 1)
    day_change_pct = (
        round(day_change / abs(prev_valid["total"]) * 100, 1)
        if prev_valid["total"] not in (None, 0)
        else None
    )
    five_day_compare_valid = len(last5) == 5 and len(prev5) == 5
    five_day_change = round(last5_sum - prev5_sum, 1) if five_day_compare_valid and prev5_sum is not None else None
    five_day_change_pct = (
        round(five_day_change / abs(prev5_sum) * 100, 1)
        if five_day_compare_valid and prev5_sum not in (None, 0) and last5_sum * prev5_sum > 0
        else None
    )

    five_day_direction = None
    if five_day_compare_valid and prev5_sum is not None:
        if prev5_sum < 0 < last5_sum:
            five_day_direction = "순유출→순유입 전환"
        elif prev5_sum > 0 > last5_sum:
            five_day_direction = "순유입→순유출 전환"
        elif last5_sum > prev5_sum:
            five_day_direction = "순자금흐름 개선"
        elif last5_sum < prev5_sum:
            five_day_direction = "순자금흐름 악화"
        else:
            five_day_direction = "변화 없음"

    return {
        "date": latest_valid["date"].isoformat(),
        "total_usd_m": latest_valid["total"],
        "status": latest_valid["status"],
        "reported_funds": latest_valid["reported_funds"],
        "missing_funds": latest_valid["missing_funds"],
        "prev_date": prev_valid["date"].isoformat(),
        "prev_total_usd_m": prev_valid["total"],
        "day_change_usd_m": day_change,
        "day_change_pct": day_change_pct,
        "source_latest_date": source_latest["date"].isoformat(),
        "source_latest_status": source_latest["status"],
        "pending_date": source_latest["date"].isoformat() if source_latest["status"] == "pending" else None,
        "latest_recomputed_total_usd_m": latest_valid.get("recomputed_total"),
        "latest_total_gap_usd_m": latest_valid.get("total_gap"),
        "latest_total_validated": latest_valid.get("total_validated"),
        "last5_usd_m": last5_sum,
        "last5_dates": [x["date"].isoformat() for x in last5],
        "last5_values_usd_m": [x["total"] for x in last5],
        "prev5_usd_m": prev5_sum,
        "prev5_dates": [x["date"].isoformat() for x in prev5],
        "prev5_values_usd_m": [x["total"] for x in prev5],
        "five_day_compare_valid": five_day_compare_valid,
        "five_day_change_usd_m": five_day_change,
        "five_day_change_pct": five_day_change_pct,
        "five_day_direction": five_day_direction,
    }


watch.btc_etf_flow = btc_etf_flow_strict
watch.main()
