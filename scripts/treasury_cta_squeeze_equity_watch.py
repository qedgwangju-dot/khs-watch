#!/usr/bin/env python3
"""Readable equity interpretation plus scheduled Treasury CTA reports.

Delivery policy:
- preserve the audited composite squeeze gate for event-driven alerts
- always send one Monday weekly status report
- always send one FOMC decision-eve report on the Korean evening before the
  2:00 p.m. ET decision reaches Korea
- preserve scheduled-delivery state only after Telegram delivery succeeds
"""
from __future__ import annotations

import io
import json
import os
import re
import urllib.request
from datetime import date, datetime, time, timedelta
from zoneinfo import ZoneInfo

from pypdf import PdfReader

import treasury_cta_squeeze_audited_watch as audited

watcher = audited.watcher
# Revision 10 adds the official NQ/CFTC cross-asset squeeze lane.
# The audited gate still prevents a formatting-only push from becoming an event alert.
watcher.FORMAT_REVISION = max(int(getattr(watcher, "FORMAT_REVISION", 0)), 13)
_base_format = audited.format_alert
_base_main = watcher.main

NY = ZoneInfo("America/New_York")
KST = ZoneInfo("Asia/Seoul")

# Federal Reserve published meeting-end dates.
FOMC_END_DATES = {
    "2026-01-28", "2026-03-18", "2026-04-29", "2026-06-17",
    "2026-07-29", "2026-09-16", "2026-10-28", "2026-12-09",
    "2027-01-27", "2027-03-17", "2027-04-28", "2027-06-09",
    "2027-07-28", "2027-09-15", "2027-10-28", "2027-12-08",
}
FOMC_SEP_END_DATES = {
    "2026-03-18", "2026-06-17", "2026-09-16", "2026-12-09",
    "2027-03-17", "2027-06-09", "2027-09-15", "2027-12-08",
}

TREASURY_URL = "https://home.treasury.gov/resource-center/data-chart-center/interest-rates/pages/xml?data=daily_treasury_yield_curve"
CFTC_URL = "https://www.cftc.gov/dea/futures/financial_lf.htm"
NYFED_URL = "https://markets.newyorkfed.org/api/rates/secured/sofr/last/1.json"
FED_FOMC_URL = "https://www.federalreserve.gov/monetarypolicy/fomccalendars.htm"
CTA_SECONDARY_URL = "https://a.foresightnews.pro/article/detail/99813"
BESSENT_FEVER_URL = "https://news.bgov.com/bloomberg-government-news/bessent-says-buyback-move-aimed-at-quelling-market-fever-1"
TREASURY_BUYBACK_RELEASE = "https://home.treasury.gov/news/press-releases/sb0607"
CME_NQ_URL = "https://www.cmegroup.com/markets/equities/nasdaq/e-mini-nasdaq-100.html"
CME_EQUITIES_URL = "https://www.cmegroup.com/markets/equities.html"
CME_NQ_BULLETIN = "https://www.cmegroup.com/daily_bulletin/current/Section11_Equity_And_Index_Futures.pdf"
YAHOO_NQ_URL = "https://query1.finance.yahoo.com/v8/finance/chart/NQ%3DF?range=5d&interval=1d"
US_POSITIONING_STATE = watcher.DATA / "us_positioning_state.json"
CROSS_FORMAT_REVISION = 3
_CROSS_CACHE = None

# CME contract face amounts. These convert CFTC contract counts into an intuitive
# face-value notional only; they are not margin, P/L, market value or DV01.
CONTRACT_FACE_USD = {
    "2Y": 200_000,
    "5Y": 100_000,
    "10Y": 100_000,
    "BOND": 100_000,
    "ULTRABOND": 100_000,
}


def _ints(text: str) -> list[int]:
    return [
        int(x.replace(",", ""))
        for x in re.findall(r"[-+]?(?:\d{1,3}(?:,\d{3})+|\d+)", text or "")
    ]


def _tff_fields_strict(text: str, expected: int = 14) -> list[int | None]:
    """Preserve CFTC confidential '.' placeholders so column indexes never shift."""
    tokens = re.findall(r"[-+]?(?:\d{1,3}(?:,\d{3})+|\d+)|\.", text or "")
    if len(tokens) < expected:
        raise RuntimeError(f"CFTC TFF row too short: {len(tokens)} < {expected}")
    return [
        None if tok == "." else int(tok.replace(",", ""))
        for tok in tokens[:expected]
    ]


def _nq_cftc_weekly() -> dict:
    """Official NASDAQ MINI weekly TFF lane; OI and positioning are same-scope."""
    raw = watcher.fetch(CFTC_URL)
    plain = watcher.strip_tags(raw).replace("\xa0", " ")
    report_m = re.search(
        r"Positions\s+as\s+of\s+([A-Za-z]+\s+\d{1,2},\s+20\d{2})",
        plain,
        re.I,
    )
    report_date = report_m.group(1) if report_m else "확인 불가"
    start = plain.find("NASDAQ MINI -")
    if start < 0:
        raise RuntimeError("CFTC NASDAQ MINI block not found")
    block = plain[start : start + 7000]

    oi_m = re.search(r"Open Interest is\s+([\d,]+)", block, re.I)
    pos_m = re.search(r"Positions\s+([\s\S]*?)\s+Changes from:", block, re.I)
    ch_m = re.search(
        r"Changes from:\s*([A-Za-z]+\s+\d{1,2},\s+20\d{2}).*?"
        r"Total Change is:\s*([-+]?\s*[\d,]+)\s+([\s\S]*?)\s+Percent of Open Interest",
        block,
        re.I,
    )
    if not oi_m or not pos_m or not ch_m:
        raise RuntimeError("CFTC NASDAQ MINI weekly fields missing")

    pos = _tff_fields_strict(pos_m.group(1))
    changes = _tff_fields_strict(ch_m.group(3))
    if any(pos[i] is None for i in (6, 7)) or any(changes[i] is None for i in (6, 7)):
        raise RuntimeError("CFTC NASDAQ MINI Leveraged Funds fields are confidential/missing")

    oi = int(oi_m.group(1).replace(",", ""))
    oi_wow = int(ch_m.group(2).replace(" ", "").replace(",", ""))
    lev_long, lev_short = int(pos[6]), int(pos[7])
    lev_long_wow, lev_short_wow = int(changes[6]), int(changes[7])
    return {
        "report_date": report_date,
        "previous_period": ch_m.group(1),
        "open_interest": oi,
        "open_interest_wow": oi_wow,
        "leveraged_long": lev_long,
        "leveraged_short": lev_short,
        "leveraged_net": lev_long - lev_short,
        "leveraged_net_wow": lev_long_wow - lev_short_wow,
        "leveraged_short_wow": lev_short_wow,
        "short_share_oi_pct": (lev_short / oi * 100.0) if oi else None,
        "scope": "CFTC TFF NASDAQ MINI 전체시장 주간",
    }


def _cme_daily_bulletin_nq() -> dict:
    """Official previous-trade-date NQ settlement direction from CME PG11.

    The PDF can split the final settlement decimal digit across layout lines.
    Direction and point change are nevertheless in dedicated columns, so the
    parser uses the signed point-change field and only uses settlement for an
    approximate percentage calculation.
    """
    stamp = datetime.now(NY).strftime("%Y%m%d%H")
    urls = [
        CME_NQ_BULLETIN + "?download=1&_=" + stamp,
        CME_NQ_BULLETIN + "?_=" + stamp,
        CME_NQ_BULLETIN,
    ]
    candidates = []
    errors = []
    headers = {
        "User-Agent": "Mozilla/5.0 khs-watch/cta-squeeze",
        "Accept": "application/pdf,*/*",
        "Cache-Control": "no-cache",
        "Pragma": "no-cache",
        "Referer": "https://www.cmegroup.com/market-data/daily-bulletin.html",
    }
    for url in urls:
        try:
            req = urllib.request.Request(url, headers=headers)
            with urllib.request.urlopen(req, timeout=30) as response:
                data = response.read()
            if not data.startswith(b"%PDF"):
                errors.append(f"{url}: non-PDF")
                continue
            probe = PdfReader(io.BytesIO(data))
            probe_text = "\n".join((p.extract_text() or "") for p in probe.pages[:1])
            dm = re.search(
                r"\b(?:Mon|Tue|Wed|Thu|Fri),\s+([A-Z][a-z]{2})\s+(\d{1,2}),\s+(20\d{2})\b",
                probe_text,
            )
            d = None
            if dm:
                d = datetime.strptime(
                    f"{dm.group(1)} {dm.group(2)} {dm.group(3)}",
                    "%b %d %Y",
                ).date()
            candidates.append((d, data, url))
        except Exception as exc:
            errors.append(f"{url}: {type(exc).__name__}: {exc}")
    if not candidates:
        raise RuntimeError("CME PG11 download failed: " + " | ".join(errors))
    candidates.sort(key=lambda x: (x[0] or date.min), reverse=True)
    _, raw, bulletin_url = candidates[0]

    reader = PdfReader(io.BytesIO(raw))
    layout_pages = []
    plain_pages = []
    for page in reader.pages:
        try:
            layout_pages.append(page.extract_text(extraction_mode="layout") or "")
        except TypeError:
            layout_pages.append(page.extract_text() or "")
        plain_pages.append(page.extract_text() or "")
    text = "\n".join(layout_pages)
    plain_text = "\n".join(plain_pages)
    if "EMINI NASD FUT" not in text and "EMINI NASD FUT" not in plain_text:
        raise RuntimeError("CME PG11 EMINI NASD FUT block missing")

    date_m = re.search(
        r"\b(?:Mon|Tue|Wed|Thu|Fri),\s+([A-Z][a-z]{2})\s+(\d{1,2}),\s+(20\d{2})\b",
        text,
    )
    trade_date = None
    if date_m:
        trade_date = datetime.strptime(
            f"{date_m.group(1)} {date_m.group(2)} {date_m.group(3)}",
            "%b %d %Y",
        ).date().isoformat()

    block = text.split("EMINI NASD FUT", 1)[1].split("TOTAL EMINI NASD FUT", 1)[0]
    # Front listed quarterly contract. PG11 columns:
    # CONTRACT, GLOBEX OPEN/HIGH/LOW, SETT.PRICE, +/- POINT CHANGE, volumes, OI...
    row_re = re.compile(
        r"(?m)^\s*([A-Z]{3}\d{2})\s+"
        r"(?:----|[0-9,.]+[AB]?)\s+"
        r"(?:----|[0-9,.]+[AB]?)\s+"
        r"(?:----|[0-9,.]+[AB]?)\s+"
        r"([0-9,.]+)\s+([+-])\s+([0-9]+)\b"
    )
    rows = list(row_re.finditer(block))
    if not rows:
        raise RuntimeError("CME PG11 NQ settlement row parse failed")

    m = rows[0]
    month = m.group(1)
    settle = float(m.group(2).replace(",", ""))
    sign = 1.0 if m.group(3) == "+" else -1.0
    # CME PG11 equity-index point changes are printed in hundredths without
    # the decimal point (e.g. 34650 = 346.50 index points).
    change_points = sign * (float(m.group(4)) / 100.0)
    prior = settle - change_points
    pct = (change_points / prior * 100.0) if prior else None

    if pct is None or abs(pct) > 20:
        raise RuntimeError(
            f"CME PG11 NQ percentage sanity failed: settle={settle}, change={change_points}, pct={pct}"
        )

    # Use the product TOTAL line for daily NQ open interest. This keeps the OI
    # universe consistent across all listed NQ expiries instead of mixing a
    # front-contract price with a single-contract OI.
    total_pattern = (
        r"TOTAL\s+EMINI\s+NASD\s+FUT\s+"
        r"([0-9,]+|----)\s+([0-9,]+|----)\s+([0-9,]+)\s+"
        r"(?:(UNCH)|([+-])\s*([0-9,]+))"
    )
    total_m = re.search(total_pattern, plain_text, re.I | re.S)
    if not total_m:
        total_m = re.search(total_pattern, text, re.I | re.S)
    total_oi = None
    total_oi_change = None
    if total_m:
        total_oi = int(total_m.group(3).replace(",", ""))
        if total_m.group(4):
            total_oi_change = 0
        elif total_m.group(5) and total_m.group(6):
            mag = int(total_m.group(6).replace(",", ""))
            total_oi_change = mag if total_m.group(5) == "+" else -mag
    else:
        # PyPDF's plain extraction can reorder PG11's final columns as:
        #   TOTAL EMINI NASD FUT <OI> <OI-change-magnitude><sign> <Globex volume>
        # Example observed from the official PDF: "270554 1734- 581241".
        scrambled = re.search(
            r"TOTAL\s+EMINI\s+NASD\s+FUT\s+"
            r"([0-9,]+)\s+([0-9,]+)([+-])\s+([0-9,]+)",
            plain_text,
            re.I | re.S,
        )
        if scrambled:
            candidate_oi = int(scrambled.group(1).replace(",", ""))
            candidate_delta = int(scrambled.group(2).replace(",", ""))
            if scrambled.group(3) == "-":
                candidate_delta = -candidate_delta
            if candidate_oi >= 10_000 and abs(candidate_delta) <= candidate_oi:
                total_oi = candidate_oi
                total_oi_change = candidate_delta
        if total_oi is None:
            marker = re.search(r"TOTAL\s+EMINI\s+NASD\s+FUT", plain_text, re.I)
            if marker:
                snippet = re.sub(r"\s+", " ", plain_text[marker.start():marker.start() + 350])
            else:
                snippet = "marker-missing"
            print(f"cme_nq_total_parse_failed snippet={snippet!r}")

    return {
        "price": settle,
        "previous_close": prior,
        "pct_change": pct,
        "change_points": change_points,
        "open_interest": total_oi,
        "oi_change": total_oi_change,
        "oi_scope": "CME EMINI NASD FUT total product daily",
        "source": "CME Daily Bulletin PG11 official settlement/OI",
        "official": True,
        "basis": "previous trade date settlement + total product daily OI",
        "trade_date": trade_date,
        "month": month,
        "url": bulletin_url,
    }


def _nq_price() -> dict:
    """Use dated official CME settlement/OI first; Yahoo is display-only fallback.

    The internal CME quote endpoint is excluded from production because it returns
    404 for NQ on GitHub-hosted runners. The Daily Bulletin is the confirmation
    source because settlement direction and OI change are in one dated CME file.
    """
    official_errors = []
    try:
        return _cme_daily_bulletin_nq()
    except Exception as exc:
        official_errors.append(f"CME Daily Bulletin PG11: {type(exc).__name__}: {exc}")

    # The public CME equity-index page contains a server-rendered active NQ quote.
    # This provides an official fallback when the internal quote endpoint blocks
    # cloud runners.
    try:
        text = watcher.strip_tags(watcher.fetch(CME_EQUITIES_URL))
        m = re.search(
            r"E-mini\s+Nasdaq-100\s+Futures\s+"
            r"([0-9,]+(?:\.[0-9]+)?)\s+"
            r"([0-9,]+)\s+"
            r"([+-]?[0-9,]+(?:\.[0-9]+)?)\s*"
            r"\(([+-]?[0-9.]+)%\)",
            text,
            re.I,
        )
        if not m:
            raise RuntimeError("CME equities page active NQ quote not found")
        return {
            "price": float(m.group(1).replace(",", "")),
            "previous_close": None,
            "pct_change": float(m.group(4)),
            "change": float(m.group(3).replace(",", "")),
            "volume": int(m.group(2).replace(",", "")),
            "source": "CME official equity-index page",
            "official": True,
        }
    except Exception as exc:
        official_errors.append(f"CME equity page: {type(exc).__name__}: {exc}")

    data = watcher.fetch_json(YAHOO_NQ_URL)
    result = (((data or {}).get("chart") or {}).get("result") or [None])[0]
    if not result:
        raise RuntimeError("NQ official CME unavailable and Yahoo fallback missing")
    meta = result.get("meta") or {}
    quote = (((result.get("indicators") or {}).get("quote") or [{}])[0])
    closes = [float(x) for x in (quote.get("close") or []) if x is not None]
    price = meta.get("regularMarketPrice")
    prev = meta.get("chartPreviousClose") or meta.get("previousClose")
    if price is None and closes:
        price = closes[-1]
    if prev is None and len(closes) >= 2:
        prev = closes[-2]
    price = float(price) if price is not None else None
    prev = float(prev) if prev is not None else None
    pct = ((price / prev - 1.0) * 100.0) if price is not None and prev not in (None, 0) else None
    return {
        "price": price,
        "previous_close": prev,
        "pct_change": pct,
        "source": "Yahoo distributed/delayed NQ=F fallback",
        "official": False,
        "official_errors": official_errors,
    }


def _years_back(day: date, years: int) -> date:
    try:
        return day.replace(year=day.year - years)
    except ValueError:
        return day.replace(year=day.year - years, day=28)


def _nq_history_statistics(rows: list[dict], current: dict) -> dict:
    """Independently verify the live CFTC NQ week and compute same-week percentiles."""
    latest = datetime.strptime(str(current["report_date"]), "%B %d, %Y").date()
    parsed: dict[date, dict] = {}
    for row in rows:
        try:
            d = date.fromisoformat(str(row["report_date_as_yyyy_mm_dd"])[:10])
            if d > latest:
                continue
            oi = int(float(row["open_interest_all"]))
            lng = int(float(row["lev_money_positions_long"]))
            shrt = int(float(row["lev_money_positions_short"]))
            if oi <= 0 or min(lng, shrt) < 0:
                continue
            parsed[d] = {"date": d, "oi": oi, "long": lng, "short": shrt,
                         "net": lng - shrt, "severity": max(shrt - lng, 0)}
        except (KeyError, ValueError, TypeError, OverflowError):
            continue
    ordered = [parsed[d] for d in sorted(parsed)]
    if not ordered or ordered[-1]["date"] != latest:
        raise RuntimeError(f"CFTC NQ historical latest date disagrees with live report: live={latest}, historical={ordered[-1]['date'] if ordered else 'missing'}")
    last = ordered[-1]
    for source, target in (("oi", "open_interest"), ("long", "leveraged_long"), ("short", "leveraged_short"), ("net", "leveraged_net")):
        if last[source] != int(current[target]):
            raise RuntimeError(f"CFTC NQ historical/live mismatch: {target} history={last[source]} live={current[target]}")

    try:
        expected_prev = datetime.strptime(str(current["previous_period"]), "%B %d, %Y").date()
    except (ValueError, TypeError, KeyError) as exc:
        raise RuntimeError("CFTC NQ previous report date unavailable") from exc
    prior = parsed.get(expected_prev)
    if prior is None:
        raise RuntimeError(f"CFTC NQ history previous week missing: {expected_prev}")
    for now_value, old_value, current_field in (
        ("net", "net", "leveraged_net_wow"),
        ("short", "short", "leveraged_short_wow"),
    ):
        if (last[now_value] - prior[old_value]) != int(current[current_field]):
            raise RuntimeError(f"CFTC NQ weekly delta mismatch: {current_field}")

    def window_stats(years: int) -> dict:
        start = _years_back(latest, years)
        frame = [r for r in ordered if r["date"] >= start]
        if not frame:
            raise RuntimeError(f"CFTC NQ {years}Y window empty")
        gross = [r["short"] for r in frame]
        net_severity = [r["severity"] for r in frame]
        short_share = [r["short"] / r["oi"] * 100.0 for r in frame]
        diffs = [frame[i]["short"] - frame[i - 1]["short"] for i in range(1, len(frame))]
        net_diffs = [frame[i - 1]["net"] - frame[i]["net"] for i in range(1, len(frame))]
        p = lambda seq, v: 100.0 * sum(x <= v for x in seq) / len(seq) if seq else None
        peak_net = max(net_severity)
        peak_gross = max(gross)
        gross_build = diffs[-1] if diffs else None
        net_build = net_diffs[-1] if net_diffs else None
        return {
            "sample_n": len(frame),
            "start_date": frame[0]["date"].isoformat(),
            "end_date": frame[-1]["date"].isoformat(),
            "net_short_percentile": p(net_severity, net_severity[-1]),
            "gross_short_percentile": p(gross, gross[-1]),
            "short_share_oi_percentile": p(short_share, short_share[-1]),
            "peak_net_short_contracts": peak_net,
            "peak_net_short_date": frame[net_severity.index(peak_net)]["date"].isoformat(),
            "peak_gross_short_contracts": peak_gross,
            "peak_gross_short_date": frame[gross.index(peak_gross)]["date"].isoformat(),
            "net_short_unwind_from_peak_pct": (peak_net - net_severity[-1]) * 100.0 / peak_net if peak_net else None,
            "gross_short_unwind_from_peak_pct": (peak_gross - gross[-1]) * 100.0 / peak_gross if peak_gross else None,
            "gross_short_weekly_change": gross_build,
            "net_short_weekly_build": net_build,
            "gross_short_weekly_build_percentile": p(diffs, gross_build) if gross_build is not None else None,
            "net_short_weekly_build_percentile": p(net_diffs, net_build) if net_build is not None else None,
            "max_gross_short_weekly_build": max(diffs) if diffs else None,
            "max_net_short_weekly_build": max(net_diffs) if net_diffs else None,
            "gross_short_weekly_record": bool(diffs and gross_build > 0 and gross_build >= max(diffs)),
            "net_short_weekly_record": bool(net_diffs and net_build > 0 and net_build >= max(net_diffs)),
        }

    s3 = window_stats(3)
    if s3["sample_n"] < 150:
        raise RuntimeError(f"CFTC NQ 3Y history incomplete: {s3['sample_n']} samples")
    result = {
        "basis": "CFTC TFF NASDAQ MINI futures-only",
        "history_source": "CFTC Public Reporting gpe5-46if verified against live report",
        "history_url": CFTC_HISTORY_INDEX,
        "verified_current": True,
        "sample_n": s3["sample_n"],
        "start_date": s3["start_date"],
        "end_date": s3["end_date"],
        "net_short_percentile_3y": s3["net_short_percentile"],
        "gross_short_percentile_3y": s3["gross_short_percentile"],
        "short_extreme_percentile_3y": s3["net_short_percentile"],
        "short_share_oi_percentile_3y": s3["short_share_oi_percentile"],
        "peak_net_short_contracts_3y": s3["peak_net_short_contracts"],
        "peak_net_short_date_3y": s3["peak_net_short_date"],
        "peak_gross_short_contracts_3y": s3["peak_gross_short_contracts"],
        "peak_gross_short_date_3y": s3["peak_gross_short_date"],
        "net_short_unwind_from_peak_pct": s3["net_short_unwind_from_peak_pct"],
        "gross_short_unwind_from_peak_pct": s3["gross_short_unwind_from_peak_pct"],
        "unwind_from_peak_pct": s3["net_short_unwind_from_peak_pct"],
        "leveraged_short_1w_change": last["short"] - prior["short"],
        "leveraged_net_1w_change": last["net"] - prior["net"],
    }
    s10 = window_stats(10)
    # A full ten-year comparison needs at least 500 weekly points and data
    # covering the entire ten-year period; otherwise suppress ten-year claims.
    complete10 = len([r for r in ordered if r["date"] <= _years_back(latest, 10)]) > 0 and s10["sample_n"] >= 500
    result["ten_year_complete"] = complete10
    if complete10:
        result.update({
            "sample_n_10y": s10["sample_n"],
            "start_date_10y": s10["start_date"],
            "end_date_10y": s10["end_date"],
            "net_short_percentile_10y": s10["net_short_percentile"],
            "gross_short_percentile_10y": s10["gross_short_percentile"],
            "gross_short_weekly_change_10y": s10["gross_short_weekly_change"],
            "net_short_weekly_build_10y": s10["net_short_weekly_build"],
            "gross_short_weekly_build_percentile_10y": s10["gross_short_weekly_build_percentile"],
            "net_short_weekly_build_percentile_10y": s10["net_short_weekly_build_percentile"],
            "max_gross_short_weekly_build_10y": s10["max_gross_short_weekly_build"],
            "max_net_short_weekly_build_10y": s10["max_net_short_weekly_build"],
            "gross_short_weekly_record_10y": s10["gross_short_weekly_record"],
            "net_short_weekly_record_10y": s10["net_short_weekly_record"],
        })
    return result


def _fresh_nq_history(current: dict) -> dict:
    query = urllib.parse.urlencode({
        "$where": "cftc_contract_market_code='209742'",
        "$order": "report_date_as_yyyy_mm_dd DESC",
        "$limit": "600",
        "$select": "report_date_as_yyyy_mm_dd,open_interest_all,lev_money_positions_long,lev_money_positions_short",
    })
    rows = watcher.fetch_json("https://publicreporting.cftc.gov/resource/gpe5-46if.json?" + query)
    if not isinstance(rows, list) or not rows:
        raise RuntimeError("CFTC NQ 10Y public history unavailable")
    return _nq_history_statistics(rows, current)


def _nq_cached_history(current: dict) -> dict | None:
    try:
        state = watcher.load_state()
        prior = ((state.get("snapshot") or {}).get("nasdaq_cross_asset") or {})
        nq = prior.get("nq_cftc") or {}
        hist = prior.get("history_3y") or {}
        if not hist.get("verified_current") or hist.get("end_date") != datetime.strptime(current["report_date"], "%B %d, %Y").date().isoformat():
            return None
        if any(nq.get(k) != current.get(k) for k in ("open_interest", "leveraged_long", "leveraged_short", "leveraged_net")):
            return None
        return hist
    except (TypeError, ValueError, KeyError):
        return None


def _positioning_state_cftc() -> dict:
    try:
        state = json.loads(US_POSITIONING_STATE.read_text(encoding="utf-8"))
        return ((state.get("values") or {}).get("CFTC|cot") or {})
    except Exception:
        return {}


def _positioning_history_enrichment() -> dict:
    return _positioning_state_cftc().get("history_3y") or {}


def _cross_raw() -> dict:
    global _CROSS_CACHE
    if _CROSS_CACHE is not None:
        return _CROSS_CACHE
    stored_cftc = _positioning_state_cftc()
    out = {
        "nq_cftc": None,
        "nq_price": None,
        "history_3y": {},
        "stored_nq_cftc": stored_cftc.get("nq_mini") or {},
        "stored_cftc_period": stored_cftc.get("period"),
        "history_status": "미확인",
        "errors": [],
    }
    try:
        out["nq_cftc"] = _nq_cftc_weekly()
        nq = out["nq_cftc"]
        live_iso = datetime.strptime(nq["report_date"], "%B %d, %Y").date().isoformat()
        stored = stored_cftc.get("nq_mini") or {}
        stored_hist = stored_cftc.get("history_3y") or {}
        same_stored = (
            str(stored_cftc.get("period") or "") == str(nq["report_date"])
            and stored_hist.get("end_date") == live_iso
            and all(stored.get(k) == nq.get(k) for k in ("open_interest", "leveraged_long", "leveraged_short", "leveraged_net"))
        )
        if same_stored:
            out["history_3y"] = {**stored_hist, "verified_current": True}
            out["history_status"] = "최신 저장 공식 원천 비교 일치"
        else:
            cached = _nq_cached_history(nq)
            if cached:
                out["history_3y"] = cached
                out["history_status"] = "이전 운영 실행의 공식 CFTC 현재주 검증 재사용"
            else:
                try:
                    out["history_3y"] = _fresh_nq_history(nq)
                    out["history_status"] = "CFTC 최신 주간 보고서와 10년 공식자료 교차검증"
                except Exception as exc:
                    out["errors"].append(f"NQ 최신 통계 검증 불가: {type(exc).__name__}: {exc}")
                    # Never display the stale persisted percentiles/weekly-change as current.
                    out["history_status"] = f"{live_iso} 실시간 포지션 확인, 백분위·10년 통계 갱신 대기"
    except Exception as exc:
        out["errors"].append(f"CFTC NQ: {type(exc).__name__}: {exc}")
    try:
        out["nq_price"] = _nq_price()
    except Exception as exc:
        out["errors"].append(f"NQ price: {type(exc).__name__}: {exc}")
    _CROSS_CACHE = out
    return out


def _previous_business_day(day: date) -> date:
    d = day - timedelta(days=1)
    while d.weekday() >= 5:
        d -= timedelta(days=1)
    return d


def _latest_completed_us_session_date() -> date:
    """Expected latest completed U.S. regular-session trade date.

    This is deliberately stricter than CME bulletin publication timing. If the
    official bulletin has not caught up yet, the confirmation gate stays closed.
    """
    now_ny = datetime.now(NY)
    if now_ny.weekday() >= 5:
        d = now_ny.date()
        while d.weekday() >= 5:
            d -= timedelta(days=1)
        return d
    if now_ny.time() >= time(16, 15):
        return now_ny.date()
    return _previous_business_day(now_ny.date())


def _cross_asset_snapshot(snapshot: dict, previous: dict) -> dict:
    raw = _cross_raw()
    nq = raw.get("nq_cftc") or {}
    price = raw.get("nq_price") or {}
    hist = raw.get("history_3y") or {}

    treasury10 = ((snapshot.get("cftc") or {}).get("markets") or {}).get("10Y") or {}
    treasury_short_present = bool(
        (treasury10.get("leveraged_net") or 0) < 0
        and float(treasury10.get("short_share_oi_pct") or 0) >= 35.0
    )

    net_pctile = hist.get("net_short_percentile_3y")
    gross_pctile = hist.get("gross_short_percentile_3y")
    if not isinstance(net_pctile, (int, float)):
        net_pctile = hist.get("short_extreme_percentile_3y")
    nq_history_ready = (
        isinstance(net_pctile, (int, float))
        and isinstance(gross_pctile, (int, float))
        and int(hist.get("sample_n") or 0) >= 150
    )
    nq_net_extreme = nq_history_ready and float(net_pctile) >= 90.0
    nq_gross_extreme = nq_history_ready and float(gross_pctile) >= 90.0
    nq_extreme = nq_net_extreme or nq_gross_extreme

    # Distinguish POSITION LEVEL from FLOW SHOCK. The Goldman/PB "record week"
    # thesis can be directionally supported by CFTC even when the current stock of
    # shorts is not at a 90th-percentile extreme. Only a complete 10Y official
    # history and a >=99th-percentile positive gross-short weekly build qualify.
    nq_build_pctile_10y = hist.get("gross_short_weekly_build_percentile_10y")
    nq_build_record_10y = bool(hist.get("gross_short_weekly_record_10y"))
    nq_build_change_10y = hist.get("gross_short_weekly_change_10y")
    nq_build_shock = bool(
        nq_history_ready
        and hist.get("ten_year_complete")
        and isinstance(nq_build_pctile_10y, (int, float))
        and isinstance(nq_build_change_10y, (int, float))
        and float(nq_build_pctile_10y) >= 99.0
        and int(nq_build_change_10y) > 0
    )

    try:
        report_iso = datetime.strptime(str(nq.get("report_date") or ""), "%B %d, %Y").date().isoformat()
    except Exception:
        report_iso = None
    nq_history_fresh = bool(report_iso and hist.get("end_date") == report_iso)

    # Cross-check the live CFTC parse against the independently persisted
    # US Positioning parse for the same report week. Any same-date disagreement
    # closes the squeeze gate rather than choosing one silently.
    stored_nq = raw.get("stored_nq_cftc") or {}
    stored_period = str(raw.get("stored_cftc_period") or "")
    live_period = str(nq.get("report_date") or "")
    nq_crosscheck_match = bool(hist.get("verified_current") and nq_history_fresh)
    nq_crosscheck_reason = None if nq_crosscheck_match else (
        "NQ 최신 주간 이력 대조 보류: "
        + str(raw.get("history_status") or "확인 불가")
        + (f" · 기존 저장 CFTC={stored_period}, 실시간 CFTC={live_period}" if stored_period != live_period else "")
    )

    nq_price_up = (price.get("pct_change") is not None and float(price["pct_change"]) > 0.20)
    nq_price_official = bool(price.get("official"))
    expected_session = _latest_completed_us_session_date().isoformat()
    price_trade_date = str(price.get("trade_date") or "")
    # Intraday CME quote API has no settlement trade_date and is considered fresh.
    # Daily Bulletin fallback must match the latest completed U.S. session exactly.
    nq_price_fresh = bool(
        nq_price_official
        and price_trade_date
        and price_trade_date == expected_session
    )
    nq_weekly_oi_down = (
        nq.get("open_interest_wow") is not None and int(nq["open_interest_wow"]) < 0
    )
    nq_short_cover = (
        nq.get("leveraged_net_wow") is not None and int(nq["leveraged_net_wow"]) > 0
    )
    nq_daily_oi_change = price.get("oi_change")
    nq_daily_oi_down = bool(
        nq_price_official
        and nq_price_fresh
        and nq_daily_oi_change is not None
        and int(nq_daily_oi_change) < 0
    )
    # "Confirmed" is fail-closed:
    # 1) fresh official CME same-day price↑ + product OI↓
    # 2) current CFTC week shows leveraged net-short reduction
    # 3) the three-year history is aligned to the same CFTC report.
    nq_confirmed = (
        nq_price_official
        and nq_price_fresh
        and nq_history_ready
        and nq_history_fresh
        and nq_crosscheck_match
        and nq_price_up
        and nq_daily_oi_down
        and nq_short_cover
    )

    treasury_evidence_lines = watcher.squeeze_evidence(snapshot, previous)
    treasury_10y_evidence = any(
        ("TY/ZN" in line) or line.startswith("ZN ")
        for line in treasury_evidence_lines
    )
    repo_ok, repo_worse = audited._repo_not_worse(snapshot, previous)
    data_fresh, stale_reasons = audited._data_freshness(snapshot)
    y = snapshot.get("yield10") or {}
    treasury_confirmed = (
        treasury_10y_evidence
        and repo_ok
        and data_fresh
        and float(y.get("z20") or 0) <= -1.0
    )

    # Fuel must be present in the current observation. Do not latch an old
    # extreme indefinitely after positioning has normalised.
    treasury_fuel = treasury_short_present
    nq_fuel = nq_extreme or nq_build_shock

    zn = (snapshot.get("cme") or {}).get("ZN") or {}
    treasury_price_up = (
        zn.get("pct_change") is not None and float(zn.get("pct_change")) > 0
    )
    prepared = bool(
        treasury_fuel
        and nq_fuel
        and repo_ok
        and data_fresh
        and nq_history_ready
        and nq_history_fresh
        and nq_crosscheck_match
        and nq_price_fresh
        and nq_price_official
    )

    if treasury_confirmed and nq_confirmed and treasury_fuel and nq_fuel:
        stage = 2
        label = "🔥 채권→Nasdaq 이중 숏 스퀴즈 확인"
    elif prepared:
        stage = 1
        label = "🟡 채권→Nasdaq 이중 숏 스퀴즈 연료 축적"
    else:
        stage = 0
        label = "⚪ 채권→Nasdaq 이중 숏 스퀴즈 미확인"

    return {
        **raw,
        "stage": stage,
        "label": label,
        "treasury_short_present": treasury_short_present,
        "treasury_fuel": treasury_fuel,
        "treasury_10y_evidence": treasury_10y_evidence,
        "treasury_confirmed": treasury_confirmed,
        "nq_extreme": nq_extreme,
        "nq_net_extreme": nq_net_extreme,
        "nq_gross_extreme": nq_gross_extreme,
        "nq_build_shock": nq_build_shock,
        "nq_build_pctile_10y": nq_build_pctile_10y,
        "nq_build_record_10y": nq_build_record_10y,
        "nq_build_change_10y": nq_build_change_10y,
        "nq_fuel": nq_fuel,
        "nq_history_ready": nq_history_ready,
        "nq_history_fresh": nq_history_fresh,
        "nq_crosscheck_match": nq_crosscheck_match,
        "nq_crosscheck_reason": nq_crosscheck_reason,
        "history_status": raw.get("history_status"),
        "nq_price_up": nq_price_up,
        "nq_price_official": nq_price_official,
        "nq_price_fresh": nq_price_fresh,
        "nq_price_expected_session": expected_session,
        "nq_weekly_oi_down": nq_weekly_oi_down,
        "nq_daily_oi_change": nq_daily_oi_change,
        "nq_daily_oi_down": nq_daily_oi_down,
        "nq_oi_down": nq_daily_oi_down,
        "nq_short_cover": nq_short_cover,
        "nq_confirmed": nq_confirmed,
        "repo_ok": repo_ok,
        "repo_worse": repo_worse,
        "data_fresh": data_fresh,
        "stale_reasons": stale_reasons,
    }


def _nq_notional_krw(nq: dict, price: dict, fx, field: str = "leveraged_net") -> str:
    try:
        contracts = abs(int(nq.get(field) or 0))
        index_price = float(price.get("price"))
        rate = float(fx)
        won = contracts * index_price * 20.0 * rate
        return _fmt_krw_amount(won)
    except Exception:
        return "원화 명목금액 확인 불가"


def _cross_asset_block(snapshot: dict, previous: dict, fx=None, fx_date=None, compact: bool = False) -> str:
    cross = _cross_asset_snapshot(snapshot, previous)
    nq = cross.get("nq_cftc") or {}
    price = cross.get("nq_price") or {}
    hist = cross.get("history_3y") or {}
    treasury10 = ((snapshot.get("cftc") or {}).get("markets") or {}).get("10Y") or {}

    nq_pct = price.get("pct_change")
    nq_pct_text = f"{float(nq_pct):+.2f}%" if nq_pct is not None else "가격 확인 불가"
    net_pctile = hist.get("net_short_percentile_3y")
    if not isinstance(net_pctile, (int, float)):
        net_pctile = hist.get("short_extreme_percentile_3y")
    gross_pctile = hist.get("gross_short_percentile_3y")
    net_pctile_text = f"{float(net_pctile):.0f}백분위" if isinstance(net_pctile, (int, float)) else "재조회 대기"
    gross_pctile_text = f"{float(gross_pctile):.0f}백분위" if isinstance(gross_pctile, (int, float)) else "재조회 대기"
    net_unwind = hist.get("net_short_unwind_from_peak_pct")
    if not isinstance(net_unwind, (int, float)):
        net_unwind = hist.get("unwind_from_peak_pct")
    gross_unwind = hist.get("gross_short_unwind_from_peak_pct")
    build_pct10 = hist.get("gross_short_weekly_build_percentile_10y")
    build_change10 = hist.get("gross_short_weekly_change_10y")
    build_record10 = bool(hist.get("gross_short_weekly_record_10y"))
    net_unwind_text = f"{float(net_unwind):.1f}%" if isinstance(net_unwind, (int, float)) else "확인 불가"
    gross_unwind_text = f"{float(gross_unwind):.1f}%" if isinstance(gross_unwind, (int, float)) else "확인 불가"

    if compact:
        return (
            "<b>📈 채권→Nasdaq 전이</b>\n"
            f"• {cross['label']}\n"
            f"• 10Y LF 순 {int(treasury10.get('leveraged_net') or 0):+,}계약 · "
            f"NQ LF 순 {int(nq.get('leveraged_net') or 0):+,}계약 (순숏 {net_pctile_text} / 총숏 {gross_pctile_text})\n"
            f"• NQ {nq_pct_text} · CME 일일 OI {int(price.get('oi_change') or 0):+,} · "
            f"CFTC 순포지션 주간 {int(nq.get('leveraged_net_wow') or 0):+,}\n"
            + (
                f"• NQ 총숏 주간 {int(build_change10):+,}계약 · 10년 {float(build_pct10):.0f}백분위"
                f"{' · 10년 주간 최고' if build_record10 else ''}\n"
                if isinstance(build_change10, (int, float)) and isinstance(build_pct10, (int, float))
                else ""
            )
        )

    return (
        "<b>📈 채권→Nasdaq 전이</b>\n"
        f"• 판정: <b>{cross['label']}</b>\n"
        f"• 10Y Leveraged Funds 순포지션 {_fmt_net_with_krw(treasury10.get('leveraged_net'), '10Y', fx)}\n"
        f"• NQ E-mini Leveraged Funds 순포지션 {int(nq.get('leveraged_net') or 0):+,}계약"
        f" · 3년 순숏 {net_pctile_text} · 총숏 {gross_pctile_text}\n"
        f"• 3년 극단 대비 청산률: 순숏 {net_unwind_text} · 총숏 {gross_unwind_text}\n"
        + (
            f"• 이번 주 NQ 총숏 증가 {int(build_change10):+,}계약 = 10년 {float(build_pct10):.0f}백분위"
            f"{' · <b>10년 주간 최고</b>' if build_record10 else ''}\n"
            if isinstance(build_change10, (int, float)) and isinstance(build_pct10, (int, float))
            else ""
        )
        + "• 중요: '10년 기록'은 현재 총숏 잔고가 10년 최고라는 뜻이 아니라, <b>이번 주 총숏 증가 속도</b>가 기록적이라는 뜻입니다.\n"
        + "• 이 10년 기록은 CFTC NASDAQ MINI futures-only 공식 모집단의 별도 검산값이며, Goldman/BofA Prime Brokerage의 $14.9bn 독자 집계와 같은 모집단이라고 보지 않습니다.\n"
        f"• NQ {nq_pct_text} ({price.get('source') or '가격 소스 확인 불가'})"
        f" · CME 일일 총 OI 변화 {int(price.get('oi_change') or 0):+,}계약"
        f" · CFTC 주간 총 OI 변화 {int(nq.get('open_interest_wow') or 0):+,}계약"
        f" · CFTC 순포지션 주간 {int(nq.get('leveraged_net_wow') or 0):+,}계약\n"
        f"• NQ 명목금액: 순숏 {_nq_notional_krw(nq, price, fx, 'leveraged_net')} · "
        f"총숏 {_nq_notional_krw(nq, price, fx, 'leveraged_short')}"
        " (NQ 지수×$20×계약수×환율, 실제 증거금·손익 아님)\n"
        "• 확정은 ZN 공식 같은 거래일 가격↑·OI↓ + NQ 공식 같은 거래일 가격↑·OI↓ + CFTC NQ 순숏 축소가 함께 붙을 때만 합니다.\n"
        + (
            f"• 환율 기준: {fx_date}, 1달러={float(fx):,.2f}원\n"
            if fx is not None else
            "• 환율 기준: 확인 불가 — 원화 명목금액은 확정 표시하지 않음\n"
        )
        + "※ CFTC 포지션은 주간 후행자료입니다. CME 일일 가격·OI는 같은 거래일 자료로만 묶고, 최신 완료 미국 거래일 또는 CFTC·재무부·NY Fed 신선도 기준을 통과하지 못하면 자동으로 확정 판정을 막습니다.\n"
    )


def _equity_impact(snapshot: dict, previous: dict, reasons: list[str]) -> tuple[str, str]:
    y = snapshot.get("yield10") or {}
    yld = float(y.get("yield") or 0.0)
    z = float(y.get("z20") or 0.0)
    evidence = watcher.squeeze_evidence(snapshot, previous)
    repo_ok, _ = audited._repo_not_worse(snapshot, previous)
    data_fresh, _ = audited._data_freshness(snapshot)
    prices_up = audited._price_up_count(snapshot)
    short_bias = any("CFTC 숏 축소" in r or "CFTC 주간 숏 축소" in r for r in reasons)
    if evidence and z <= -1.0 and repo_ok and data_fresh:
        return "🟢 성장주 우호 강화", "금리 하락이 포지션 청산과 함께 확인"
    if (short_bias or prices_up >= 2) and repo_ok and data_fresh:
        return "🟡 중립~약한 우호", f"숏 압력 완화 가능성은 있지만 10Y {yld:.3f}%·z={z:+.2f}σ로 추세전환 미확인"
    return "⚪ 중립", f"10Y {yld:.3f}%에서 할인율 완화 신호 미확인"


def _compact_duplicates(body: str) -> str:
    drops = (
        "• Goldman CTA DV01: 공개 공식 피드 없음 — 신뢰/명시적 2차 출처의 신규 인용만 감시\n",
        "• +2σ 채권가격 상승 시 대규모 환매 추정치가 새로 인용되면 별도 변화로 감지합니다.\n",
        "※ CME가 클라우드 러너를 차단하면 Yahoo 지연가격 + CFTC 공식 주간 OI로 교차검증. 주간 OI를 실시간 OI처럼 표시하지 않음\n",
    )
    for line in drops:
        body = body.replace(line, "")
    body = re.sub(
        r"\n<b>🔕 중복 제거 규칙</b>\n• 신규 기사 한 건, CFTC 주간 갱신 한 건, 10년물 구간 변화 한 건만으로는 텔레그램을 보내지 않습니다\.\n• <b>동일 범위 OI 감소 \+ 선물가격 상승 \+ \(CFTC 숏 축소 또는 -1σ 이하\) \+ repo 비악화</b>가 겹칠 때만 실제 스퀴즈로 격상합니다\.",
        "\n• 🔕 단독 기사·CFTC 갱신·10Y 구간 변화만으로는 재발송하지 않음.",
        body,
    )
    return body


def _checked_date(snapshot: dict) -> date:
    raw = str(snapshot.get("checked_kst") or "")
    try:
        return datetime.fromisoformat(raw).astimezone(KST).date()
    except Exception:
        return datetime.now(KST).date()


def _fomc_times(end_day: date) -> tuple[datetime, datetime]:
    decision_et = datetime.combine(end_day, time(14, 0), tzinfo=NY)
    press_et = datetime.combine(end_day, time(14, 30), tzinfo=NY)
    return decision_et.astimezone(KST), press_et.astimezone(KST)


def _easy_read_block(snapshot: dict, previous: dict, reasons: list[str]) -> str:
    y = snapshot.get("yield10") or {}
    yld = float(y.get("yield") or 0.0)
    z = float(y.get("z20") or 0.0)
    evidence = watcher.squeeze_evidence(snapshot, previous)
    repo_ok, _ = audited._repo_not_worse(snapshot, previous)
    prices_up = audited._price_up_count(snapshot)
    direction, _ = audited._direction_label(snapshot, previous, reasons)
    return (
        "<b>👀 지금 쉽게 보면</b>\n"
        f"• <b>{direction}</b> — 10년물 {yld:.3f}% · z={z:+.2f}σ\n"
        f"• 선물 {prices_up}/3 상승 · 동일범위 OI 감소 {'확인' if evidence else '미확인'} · repo {'안정' if repo_ok else '주의'}\n"
        "• 숏이 많다는 사실만으로는 부족합니다. 가격↑+OI↓가 같이 붙어야 실제 숏커버 증거가 강해집니다.\n\n"
    )


def _policy_boundary_block(compact: bool = True) -> str:
    if compact:
        return "\n".join([
            "<b>🏛 정책 목적·경계선</b>",
            "• Bessent 공식선은 <b>특정 10년·30년 금리 목표가 아니라 시장 ‘fever(과열)’·무질서한 속도 완화</b>입니다.",
            "• 따라서 CTA 숏 스퀴즈는 재무부의 공식 목표가 아니라 정책 충격 뒤 나타날 수 있는 <b>시장 결과</b>로 분리합니다.",
            "• 검증 경로: 실제 바이백 → ZN/ZB/UB·동일범위 OI → CFTC 숏 → 10·30년 명목·실질금리 → Nasdaq·AI 할인율.",
            "• 시장 기능이 정상인데도 특정 금리 수준에 맞춰 매입·발행구조를 반복 조정하면 <b>유동성 지원→사실상 금리관리</b> 경보로 격상합니다.",
            f'<a href="{BESSENT_FEVER_URL}">Bessent ‘market fever’ 발언</a> · <a href="{TREASURY_BUYBACK_RELEASE}">미 재무부 바이백 공식 발표</a>',
            "",
        ])
    return "\n".join([
        "<b>🏛 정책 목적·경계선</b>",
        "• 공식 목적: 특정 수익률·채권가격 고정이 아니라 장기물 시장의 유동성·변동성 과속 완화.",
        "• CTA·모멘텀 숏커버가 이어질 수는 있지만 이는 시장 결과이며 공식 정책목표로 단정하지 않음.",
        "• 실제 집행액과 장기 명목·실질금리가 함께 내려가야 성장주 할인율 호재로 격상.",
        "• 정상 시장에서도 특정 금리 레벨에 맞춘 반복 개입이 나오면 사실상 금리관리 위험을 별도 경보.",
        "",
    ])


def _compact_event_body(snapshot: dict, previous: dict, fx, fx_date, reasons: list[str]) -> str:
    """Fail-safe readable event alert that always fits Telegram."""
    y = snapshot.get("yield10") or {}
    cftc = ((snapshot.get("cftc") or {}).get("markets") or {})
    cme = snapshot.get("cme") or {}
    repo = snapshot.get("repo") or {}
    cross = _cross_asset_snapshot(snapshot, previous)
    impact, path = _equity_impact(snapshot, previous, reasons)
    repo_ok, repo_worse = audited._repo_not_worse(snapshot, previous)
    data_fresh, stale = audited._data_freshness(snapshot)

    def fut_line(symbol: str) -> str:
        row = cme.get(symbol) or {}
        label = row.get("display_symbol") or symbol
        pct = row.get("pct_change")
        pct_txt = f"{float(pct):+.2f}%" if pct is not None else "변화율 확인 불가"
        oi = row.get("open_interest")
        oi_txt = f"{int(oi):,}" if oi is not None else "확인 불가"
        src = row.get("oi_source") or row.get("source_type") or "출처 확인 불가"
        return f"• {label}: {pct_txt} · OI {oi_txt} [{src}]"

    t10 = cftc.get("10Y") or {}
    repo_bits = []
    for k in ("SOFR", "BGCR", "TGCR"):
        rr = repo.get(k) or {}
        if rr.get("rate") is not None:
            repo_bits.append(f"{k} {float(rr['rate']):.2f}%")

    lines = [
        "<b>👀 지금 쉽게 보면</b>",
        f"• 10년물 <b>{float(y.get('yield') or 0):.3f}%</b> · z={float(y.get('z20') or 0):+.2f}σ",
        f"• CTA/국채 스퀴즈: <b>{audited._direction_label(snapshot, previous, reasons)[0]}</b>",
        f"• 채권→Nasdaq: <b>{cross.get('label')}</b>",
        f"• 자료 신선도: {'통과' if data_fresh else '차단'}"
        + (f" ({', '.join(stale)})" if stale else ""),
        "",
        "<b>📍 핵심 포지션</b>",
        f"• 10Y Leveraged Funds 순 {int(t10.get('leveraged_net') or 0):+,}계약"
        f" · 숏/OI {float(t10.get('short_share_oi_pct') or 0):.1f}%",
        _cross_asset_block(snapshot, previous, fx=fx, fx_date=fx_date, compact=True).rstrip(),
        "",
        "<b>📉 국채 선물 확인</b>",
        fut_line("ZN"),
        fut_line("ZB"),
        fut_line("UB"),
        "• 공식 CME 같은 거래일 가격↑+OI↓를 못 받으면 스퀴즈 '확정'은 자동 차단합니다.",
        "",
        "<b>💵 자금조달</b>",
        f"• {' · '.join(repo_bits) if repo_bits else 'NY Fed repo 확인 불가'}"
        f" · 판정 {'안정' if repo_ok else '주의: ' + ', '.join(repo_worse)}",
        "",
        "<b>🧭 주식시장 해석</b>",
        f"• <b>{impact}</b> — {path}.",
        "• 금리↓가 repo·신용 스트레스 때문이면 위험자산 호재로 보지 않습니다.",
        "",
        "<b>🚦 다음 확인</b>",
        "• ZN 공식 가격↑·같은 거래일 OI↓ + NQ 공식 가격↑·같은 거래일 OI↓",
        "• 이후 CFTC 10Y·NQ 순숏 축소와 -1σ 이하가 붙을 때만 실제 이중 스퀴즈로 격상",
        "",
        "<b>⚠️ 실패모드</b>",
        "• 가격만 오르고 OI가 안 줄면 신규 롱일 수 있음",
        "• CFTC는 주간 후행자료이므로 장중 가격과 '동시 신호'로 과장하지 않음",
        "",
        "<b>📌 이번 알림 사유</b>",
        "• " + (" · ".join(reasons) if reasons else "기준선 재검증"),
        "",
        f"환율 기준: {fx_date}, 1달러={float(fx):,.2f}원" if fx is not None else "환율 기준: 확인 불가",
        f'<a href="{CFTC_URL}">CFTC</a> · <a href="{TREASURY_URL}">미 재무부 금리</a> · <a href="{NYFED_URL}">NY Fed repo</a> · <a href="{CME_NQ_URL}">CME NQ</a>',
    ]
    return "\n".join(lines)


def _compact_scheduled_report(snapshot: dict, previous: dict, reasons: list[str], fx=None, fx_date=None) -> tuple[str, str]:
    y = snapshot.get("yield10") or {}
    cftc = (snapshot.get("cftc") or {}).get("markets", {})
    repo = snapshot.get("repo") or {}
    cross = _cross_asset_snapshot(snapshot, previous)
    impact, path = _equity_impact(snapshot, previous, reasons)
    repo_ok, repo_worse = audited._repo_not_worse(snapshot, previous)
    data_fresh, stale = audited._data_freshness(snapshot)

    is_fomc = any("FOMC 전날 점검" in r for r in reasons)
    title = "🚨 미 국채 CTA · FOMC 전날 점검" if is_fomc else "📅 미 국채 CTA · 월요일 07:00 주간 점검"

    lines = [
        "<b>👀 지금 쉽게 보면</b>",
        f"• 10년물 <b>{float(y.get('yield') or 0):.3f}%</b> · z={float(y.get('z20') or 0):+.2f}σ · 4.30%까지 {max(0.0,(float(y.get('yield') or 0)-4.30)*100):.1f}bp",
        f"• 채권→Nasdaq: <b>{cross.get('label')}</b>",
        f"• 자료 신선도: {'통과' if data_fresh else '차단'}" + (f" ({', '.join(stale)})" if stale else ""),
        "",
        "<b>📍 포지션은 얼마나 쌓였나</b>",
        f"• CFTC {(snapshot.get('cftc') or {}).get('report_date','확인 불가')}: "
        f"2Y {_fmt_net_with_krw((cftc.get('2Y') or {}).get('leveraged_net'),'2Y',fx)} · "
        f"5Y {_fmt_net_with_krw((cftc.get('5Y') or {}).get('leveraged_net'),'5Y',fx)}",
        f"• 10Y {_fmt_net_with_krw((cftc.get('10Y') or {}).get('leveraged_net'),'10Y',fx)} · "
        f"Bond {_fmt_net_with_krw((cftc.get('BOND') or {}).get('leveraged_net'),'BOND',fx)} · "
        f"Ultra {_fmt_net_with_krw((cftc.get('ULTRABOND') or {}).get('leveraged_net'),'ULTRABOND',fx)}",
        "",
        _cross_asset_block(snapshot, previous, fx=fx, fx_date=fx_date, compact=True).rstrip(),
        "",
        "<b>💵 Repo</b>",
        f"• SOFR {(repo.get('SOFR') or {}).get('rate','확인 불가')}% · "
        f"BGCR {(repo.get('BGCR') or {}).get('rate','확인 불가')}% · "
        f"TGCR {(repo.get('TGCR') or {}).get('rate','확인 불가')}%"
        f" → {'안정' if repo_ok else '주의 ' + ', '.join(repo_worse)}",
    ]

    if is_fomc:
        d = _checked_date(snapshot)
        start = d - timedelta(days=1)
        decision_kst, press_kst = _fomc_times(d)
        sep = " · 점도표·경제전망 동반" if d.isoformat() in FOMC_SEP_END_DATES else ""
        lines += [
            "",
            "<b>⚡ FOMC 전날</b>",
            f"• 미국 {start:%m/%d}~{d:%m/%d}{sep}",
            f"• 결정문 한국시간 <b>{decision_kst:%m/%d %H:%M}</b> · 기자회견 {press_kst:%H:%M}",
            "• 발표 직후 가격을 먼저 보고 OI·CFTC는 후행 확인합니다.",
        ]
    else:
        lines += [
            "",
            "<b>📅 이번 주 확인</b>",
            f"• 현재 금리 레짐 기준 하향 확인선: {milestone_line} · -1σ/-2σ 진입",
            "• ZN·NQ 각각 공식 같은 거래일 가격↑+OI↓ 여부",
            "• 다음 CFTC에서 10Y·NQ 순숏이 실제로 줄었는지",
        ]

    lines += [
        "",
        "<b>🧭 주식시장 해석</b>",
        f"• <b>{impact}</b> — {path}.",
        "• repo·신용 스트레스형 금리 하락은 주식 호재로 보지 않음",
        "",
        "<b>⚠️ 실패모드</b>",
        "• 금리만 하락하고 OI가 줄지 않으면 단순 매크로 랠리",
        "• NQ 숏 잔고가 이미 낮아졌다면 기계적 매수 연료가 약할 수 있음",
        "",
        f"환율 기준: {fx_date}, 1달러={float(fx):,.2f}원" if fx is not None else "환율 기준: 확인 불가",
        f'<a href="{CFTC_URL}">CFTC</a> · <a href="{TREASURY_URL}">미 재무부 금리</a> · <a href="{NYFED_URL}">NY Fed repo</a>',
    ]
    return title, "\n".join(lines)


def format_alert(snapshot, previous, fx, fx_date, reasons):
    title, body = _base_format(snapshot, previous, fx, fx_date, reasons)
    body = _compact_duplicates(body)
    body = _easy_read_block(snapshot, previous, reasons) + _cross_asset_block(snapshot, previous, fx=fx, fx_date=fx_date, compact=True) + "\n" + body

    impact, path = _equity_impact(snapshot, previous, reasons)
    block = (
        "<b>🧭 주식시장 해석</b>\n"
        f"• <b>{impact}</b> — {path}.\n"
        "• repo·신용 스트레스형 금리 하락은 위험자산 호재로 보지 않습니다.\n\n"
    )
    block = _policy_boundary_block(compact=True) + block
    marker = "<b>한 줄 결론</b>"
    if "🧭 주식시장 해석" not in body:
        body = body.replace(marker, block + marker, 1) if marker in body else body + "\n\n" + block.rstrip()

    # Keep event alerts below Telegram's hard limit. The cross-asset lane is
    # preserved; the secondary Goldman explainer is the first removable block.
    if len(title) + 2 + len(body) > 4050:
        body = re.sub(
            r"<b>1️⃣ Goldman CTA DV01 — 스퀴즈의 연료</b>[\s\S]*?(?=<b>2️⃣ CFTC 공식 포지션)",
            "",
            body,
            count=1,
        )
    if len(title) + 2 + len(body) > 4050:
        body = _compact_event_body(snapshot, previous, fx, fx_date, reasons)
    if len(title) + 2 + len(body) > 4096:
        raise RuntimeError(f"compact CTA alert still too long: {len(title)+2+len(body)}")
    return title, body


def _fmt_pct(value) -> str:
    try:
        return f"{float(value):+.2f}%"
    except Exception:
        return "확인 불가"


def _fmt_net(value) -> str:
    try:
        return f"{int(value):+,}계약"
    except Exception:
        return "확인 불가"


def _fmt_krw_amount(won: float) -> str:
    if won >= 1_000_000_000_000:
        return f"약 {won / 1_000_000_000_000:,.1f}조원"
    if won >= 100_000_000:
        return f"약 {won / 100_000_000:,.0f}억원"
    return f"약 {won:,.0f}원"


def _fmt_net_with_krw(value, tenor: str, fx) -> str:
    """Contract count plus KRW face-value notional for readability."""
    try:
        contracts = int(value)
        rate = float(fx)
        face_usd = CONTRACT_FACE_USD[tenor]
    except Exception:
        return _fmt_net(value) + " (원화 환산 확인 불가)"
    direction = "숏" if contracts < 0 else "롱" if contracts > 0 else "중립"
    won = abs(contracts) * face_usd * rate
    return f"{contracts:+,}계약 ({direction} 액면기준 {_fmt_krw_amount(won)})"


def _yield_regime_line(yld: float) -> str:
    if yld >= 5.25:
        return "5.25% 이상 초고금리 구간 — 5.00% 하향이 첫 완화 확인선"
    if yld >= 5.00:
        return "5.00~5.25% 고금리 구간 — 5.00% 하향 돌파가 첫 완화 확인선"
    if yld >= 4.75:
        return "4.75~5.00% 구간 — 4.75% 하향 후 4.50%가 다음 확인선"
    if yld >= 4.50:
        return "4.50~4.75% 구간 — 4.50% 하향이 성장주 할인율 완화 강화선"
    return "4.50% 미만 — 과거 4.30% 시장 시나리오를 보조 하단으로만 추적"

def _yield_milestones(yld: float) -> str:
    levels = [5.25, 5.00, 4.75, 4.50, 4.30]
    below = [level for level in levels if level < yld - 1e-9]
    if not below:
        return "현재 주요 하향 경보선 아래"
    return " → ".join(f"{level:.2f}%" for level in below)

def _scheduled_report(snapshot: dict, previous: dict, reasons: list[str], fx=None, fx_date=None) -> tuple[str, str]:
    y = snapshot.get("yield10") or {}
    yld = float(y.get("yield") or 0.0)
    z = float(y.get("z20") or 0.0)
    distance = max(0.0, (yld - 4.30) * 100)
    regime_line = _yield_regime_line(yld)
    milestone_line = _yield_milestones(yld)
    direction, _ = audited._direction_label(snapshot, previous, reasons)
    impact, path = _equity_impact(snapshot, previous, reasons)
    evidence = watcher.squeeze_evidence(snapshot, previous)
    repo_ok, repo_worse = audited._repo_not_worse(snapshot, previous)

    cftc = (snapshot.get("cftc") or {}).get("markets", {})
    cftc_date = (snapshot.get("cftc") or {}).get("report_date", "확인 불가")
    cme = snapshot.get("cme") or {}
    repo = snapshot.get("repo") or {}
    cross_block = _cross_asset_block(snapshot, previous, fx=fx, fx_date=fx_date, compact=False)

    if any("FOMC 전날 점검" in r for r in reasons):
        title = "🚨 미 국채 CTA · FOMC 전날 점검"
    else:
        title = "📅 미 국채 CTA · 월요일 주간 점검"

    lines = [
        "<b>👀 지금 쉽게 보면</b>",
        f"• 판정: <b>{direction}</b>",
        f"• 10년물: <b>{yld:.3f}%</b> · 20일 z={z:+.2f}σ · {regime_line}",
        f"• 하향 확인선: {milestone_line} · 4.30%는 과거 시장 시나리오의 보조 하단({distance:.1f}bp 거리)",
        f"• 선물: ZN {_fmt_pct((cme.get('ZN') or {}).get('pct_change'))} · ZB {_fmt_pct((cme.get('ZB') or {}).get('pct_change'))} · UB {_fmt_pct((cme.get('UB') or {}).get('pct_change'))}",
        f"• 가격↑+동일범위 OI↓: {'확인' if evidence else '미확인'} · repo: {'안정' if repo_ok else '주의 ' + ', '.join(repo_worse)}",
        "",
        "<b>📍 포지션은 얼마나 쌓였나</b>",
        f"• CFTC {cftc_date}: 2Y {_fmt_net_with_krw((cftc.get('2Y') or {}).get('leveraged_net'), '2Y', fx)} · 5Y {_fmt_net_with_krw((cftc.get('5Y') or {}).get('leveraged_net'), '5Y', fx)}",
        f"• 10Y {_fmt_net_with_krw((cftc.get('10Y') or {}).get('leveraged_net'), '10Y', fx)} · Bond {_fmt_net_with_krw((cftc.get('BOND') or {}).get('leveraged_net'), 'BOND', fx)} · Ultra {_fmt_net_with_krw((cftc.get('ULTRABOND') or {}).get('leveraged_net'), 'ULTRABOND', fx)}",
        f"• SOFR {(repo.get('SOFR') or {}).get('rate', '확인 불가')}% · BGCR {(repo.get('BGCR') or {}).get('rate', '확인 불가')}% · TGCR {(repo.get('TGCR') or {}).get('rate', '확인 불가')}%",
        f"• 원화는 계약수×CME 계약 액면×환율 기준 ({fx_date or '환율일 확인 불가'}, 1달러={float(fx):,.2f}원)" if fx is not None else "• 원화 환산: 환율 확인 불가",
        "※ 2Y는 계약당 20만달러, 5Y·10Y·Bond·Ultra는 10만달러 액면 기준. 실제 투입자금·손익·DV01이 아닙니다.",
        "",
        cross_block,
    ]

    if any("FOMC 전날 점검" in r for r in reasons):
        d = _checked_date(snapshot)
        start = d - timedelta(days=1)
        decision_kst, press_kst = _fomc_times(d)
        sep = " · 점도표·경제전망 동반" if d.isoformat() in FOMC_SEP_END_DATES else ""
        lines.extend([
            "",
            "<b>⚡ 내일 FOMC가 왜 중요한가</b>",
            f"• 미국 {start:%m/%d}~{d:%m/%d} 회의{sep}",
            f"• 결정문 한국시간 <b>{decision_kst:%m/%d %H:%M}</b> · 기자회견 {press_kst:%H:%M}",
            "• FOMC가 금리 방향의 촉매는 될 수 있지만, 장기금리가 내려간다는 이유만으로 CTA 스퀴즈라고 보지는 않습니다.",
            "• 발표 직후 10Y·ZN/ZB/UB가 먼저 움직이고, OI·CFTC는 후행 확인합니다.",
        ])

    if any("월요일 정기점검" in r for r in reasons):
        lines.extend([
            "",
            "<b>📅 이번 주에 볼 것</b>",
            f"• 현재 금리 레짐 기준 하향 확인선: {milestone_line}. -1σ/-2σ 진입을 함께 봅니다.",
            "• 월요일에는 신호가 없어도 1회 보고하고, 주중에는 복합 조건이 강화될 때만 추가 발송합니다.",
        ])

    lines.extend([
        "",
        "<b>🏛 정책 목적·경계선</b>",
        "• 공식 목적은 금리 고정이 아니라 시장 과열·무질서한 속도 완화",
        "• CTA 스퀴즈는 공식 목표가 아니라 시장 결과로 분리",
        "• 실제 바이백→장기 명목·실질금리→Nasdaq·AI 할인율 순으로 검증",
        "",
        "<b>🧭 주식시장 해석</b>",
        f"• <b>{impact}</b> — {path}.",
        "• 금리↓+선물↑+OI↓가 겹치면 성장주·반도체 할인율에는 우호적입니다.",
        "• 반대로 repo·신용 스트레스 때문에 금리가 내려가면 주식 호재로 보지 않습니다.",
        "",
        "<b>🚦 다음 확인 신호</b>",
        "• 10Y -1σ 진입 또는 4.50% 하향 + 선물 상승 + 동일범위 OI 감소",
        "• 이후 CFTC 순숏 추가 축소까지 붙으면 ‘실제 숏 스퀴즈 강화’로 격상",
        "",
        "<b>⚠️ 실패모드</b>",
        "• 금리만 내려가고 OI가 줄지 않으면 단순 매크로 랠리일 수 있음",
        "• repo가 악화되면 질서 있는 숏커버가 아니라 강제 디레버리징일 수 있음",
        "",
        f'<a href="{FED_FOMC_URL}">Fed FOMC 일정</a> · <a href="{CFTC_URL}">CFTC 포지션</a> · <a href="{TREASURY_URL}">미 재무부 금리</a> · <a href="{NYFED_URL}">NY Fed repo</a> · <a href="{CTA_SECONDARY_URL}">CTA 2차 출처</a>',
    ])
    return title, "\n".join(lines)


def _scheduled_due(current_state: dict, next_state: dict) -> tuple[bool, bool, str, str]:
    snapshot = next_state.get("snapshot") or {}
    d = _checked_date(snapshot)
    iso = d.isocalendar()
    week_key = f"{iso.year}-W{iso.week:02d}"
    date_key = d.isoformat()

    trigger_event = (os.getenv("CTA_TRIGGER_EVENT") or "").strip()
    trigger_schedule = (os.getenv("CTA_TRIGGER_SCHEDULE") or "").strip()

    # Exact cron-source gating:
    # - weekly report only from the dedicated Sunday 22:00 UTC cron (= Monday 07:00 KST)
    # - FOMC eve report only from the dedicated weekday 11:40 UTC cron (= 20:40 KST)
    # A code push or ordinary 15-minute market poll can never consume these slots.
    now_kst = datetime.now(KST)
    weekly_crons = {
        "0 22 * * 0", "3 22 * * 0", "13 22 * * 0",
        "30 22 * * 0", "0 23 * * 0",
    }
    fomc_crons = {"40 11 * * 1-5", "47 11 * * 1-5"}

    weekly_missing = current_state.get("last_weekly_report_key") != week_key
    monday_due = (
        trigger_event == "schedule"
        and d.weekday() == 0
        and now_kst.time() >= time(7, 0)
        and weekly_missing
        and (
            trigger_schedule in weekly_crons
            # Final safety net: if every dedicated morning cron is dropped,
            # the first ordinary Monday scheduled poll still sends the report.
            or trigger_schedule == "*/15 12-23 * * 1-5"
        )
    )
    fomc_due = (
        trigger_event == "schedule"
        and trigger_schedule in fomc_crons
        and date_key in FOMC_END_DATES
        and current_state.get("last_fomc_eve_report") != date_key
    )
    return monday_due, fomc_due, week_key, date_key


def _cross_alert_gate(current_state: dict, cross: dict) -> tuple[bool, int, int, bool]:
    """Deduplicate a squeeze episode without letting stale data reset the alert latch."""
    stage = int(cross.get("stage", 0) or 0)
    prev_alerted = int(
        current_state.get(
            "nasdaq_cross_asset_alerted_stage",
            current_state.get("nasdaq_cross_asset_stage", 0),
        )
        or 0
    )
    fuel_present = bool(cross.get("treasury_fuel") and cross.get("nq_fuel"))
    episode_reset = bool(
        cross.get("data_fresh")
        and cross.get("nq_history_ready")
        and cross.get("nq_history_fresh")
        and not fuel_present
    )
    gate_base = 0 if episode_reset else prev_alerted
    format_due = bool(
        stage >= 1
        and int(current_state.get("nasdaq_cross_asset_format_revision", 0) or 0) < CROSS_FORMAT_REVISION
    )
    due = bool(stage >= 1 and (stage > gate_base or format_due))
    next_alerted = stage if due else gate_base
    return due, gate_base, next_alerted, episode_reset


def scheduled_main() -> int:
    current_state = watcher.load_state()
    rc = _base_main()
    if rc != 0 or not watcher.NEXT_STATE.exists():
        return rc

    next_state = json.loads(watcher.NEXT_STATE.read_text(encoding="utf-8"))
    snapshot = next_state.get("snapshot") or {}
    previous = current_state.get("snapshot") or {}
    cross = _cross_asset_snapshot(snapshot, previous)
    snapshot["nasdaq_cross_asset"] = cross
    next_state["snapshot"] = snapshot

    prev_stage = int(current_state.get("nasdaq_cross_asset_stage", 0) or 0)
    stage = int(cross.get("stage", 0) or 0)
    cross_due, cross_gate_base, next_alerted_stage, cross_episode_reset = _cross_alert_gate(
        current_state, cross
    )
    cross_format_due = bool(
        stage >= 1
        and int(current_state.get("nasdaq_cross_asset_format_revision", 0) or 0) < CROSS_FORMAT_REVISION
    )
    next_state["nasdaq_cross_asset_stage"] = stage
    next_state["nasdaq_cross_asset_alerted_stage"] = next_alerted_stage
    next_state["nasdaq_cross_asset_format_revision"] = (
        CROSS_FORMAT_REVISION if cross_due else int(current_state.get("nasdaq_cross_asset_format_revision", 0) or 0)
    )

    # Always expose the cross-asset gate in the verification status, even when no
    # Telegram is due. This makes a skipped send auditable rather than silent.
    with watcher.STATUS.open("a", encoding="utf-8") as f:
        f.write(f"- 채권→Nasdaq 현재 단계: {stage} ({cross.get('label')})\n")
        f.write(
            f"- NQ 연료: {'확인' if cross.get('nq_fuel') else '미확인'}"
            f" · 10년 주간 숏증가 충격={'확인' if cross.get('nq_build_shock') else '미확인'}"
            f" · 현재 포지션 극단={'확인' if cross.get('nq_extreme') else '미확인'}\n"
        )
        f.write(
            f"- NQ 실제 청산 확인: {'확인' if cross.get('nq_confirmed') else '미확인'}"
            f" · CME 가격↑={'예' if cross.get('nq_price_up') else '아니오'}"
            f" · CME 일일 OI↓={'예' if cross.get('nq_daily_oi_down') else '아니오'}"
            f" · CFTC 순숏 축소={'예' if cross.get('nq_short_cover') else '아니오'}\n"
        )
        f.write(
            f"- NQ 자료 신선도: CME={'확인' if cross.get('nq_price_fresh') else '미확인'}"
            f" · CFTC history={'확인' if cross.get('nq_history_fresh') else '미확인'}\n"
        )

    monday_due, fomc_due, week_key, date_key = _scheduled_due(current_state, next_state)
    base_alert_exists = watcher.ALERT.exists()
    if not (monday_due or fomc_due or cross_due):
        watcher.NEXT_STATE.write_text(json.dumps(next_state, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        return rc

    reasons: list[str] = []
    if watcher.DETAIL.exists():
        try:
            detail_existing = json.loads(watcher.DETAIL.read_text(encoding="utf-8"))
            reasons.extend(detail_existing.get("alert_reasons") or [])
        except Exception:
            pass
    if monday_due:
        reasons.append("월요일 정기점검")
    if fomc_due:
        reasons.append("FOMC 전날 점검")
    if cross_due:
        reasons.append("채권→Nasdaq 이중 숏 스퀴즈 " + ("확인" if stage >= 2 else "연료 축적"))
        if cross_format_due:
            reasons.append("정정: 10년 기록=주간 총숏 증가 속도 · NQ 확정 OI=CME 같은 거래일 일일 OI")
    reasons = list(dict.fromkeys(reasons))

    # If the audited Treasury gate already produced an event alert, format_alert()
    # has already embedded the cross-asset block. Do not overwrite it unless this is
    # a mandatory scheduled report.
    if base_alert_exists and not (monday_due or fomc_due):
        watcher.NEXT_STATE.write_text(json.dumps(next_state, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        with watcher.STATUS.open("a", encoding="utf-8") as f:
            f.write(f"- 채권→Nasdaq 전이 단계: {stage} ({cross.get('label')})\n")
            f.write(f"- 채권→Nasdaq 알림 래치: {cross_gate_base}→{next_alerted_stage} · 에피소드 리셋={'예' if cross_episode_reset else '아니오'}\n")
        return rc

    try:
        fx, fx_date = watcher.latest_fx()
    except Exception:
        fx, fx_date = None, None
    if cross_due and not (monday_due or fomc_due):
        title = "🔥 채권→Nasdaq 이중 숏 스퀴즈 감시" if stage >= 2 else "🟡 채권→Nasdaq 이중 숏 스퀴즈 연료 축적"
        body = "\n".join([
            "<b>👀 지금 쉽게 보면</b>",
            f"• <b>{cross.get('label')}</b>",
            "• 채권 숏과 Nasdaq 숏이 함께 쌓인 상태에서 실제 청산이 같은 방향으로 번지는지 확인합니다.",
            "• 정책 구분: <b>CTA 스퀴즈는 공식 금리목표가 아니라 시장 결과</b>이며, Bessent의 공식선은 시장 과열·무질서한 속도 완화입니다.",
            "",
            _cross_asset_block(snapshot, previous, fx=fx, fx_date=fx_date, compact=False),
            "<b>🚦 다음 확인</b>",
            "• ZN 공식 같은 거래일 가격↑·OI↓ + NQ 공식 같은 거래일 가격↑·CME 일일 OI↓ + CFTC NQ 순숏 축소가 겹치면 이중 스퀴즈 확인으로 격상합니다.",
            "• CFTC는 주간 후행 자료이므로 장중 가격이나 CFTC 주간 OI 감소 하나만으로 확정하지 않습니다.",
            "",
            f'<a href="{CFTC_URL}">CFTC 포지션</a> · <a href="{CME_NQ_URL}">CME NQ</a> · <a href="{CME_NQ_BULLETIN}">CME 공식 일일결제</a> · <a href="{TREASURY_URL}">미 재무부 금리</a>',
        ])
    else:
        title, body = _scheduled_report(snapshot, previous, reasons, fx=fx, fx_date=fx_date)
    if len(title) + 2 + len(body) > 4050:
        title, body = _compact_scheduled_report(snapshot, previous, reasons, fx=fx, fx_date=fx_date)
    if len(title) + 2 + len(body) > 4096:
        raise RuntimeError(f"Telegram scheduled report too long after compact fallback: {len(title)+2+len(body)}")

    watcher.TITLE.write_text(title + "\n", encoding="utf-8")
    watcher.ALERT.write_text(body + "\n", encoding="utf-8")
    watcher.DETAIL.write_text(
        json.dumps(
            {
                **snapshot,
                "dedupe_gate": next_state.get("last_gate") or {},
                "alert_reasons": reasons,
                "scheduled_delivery": {"monday_weekly": monday_due, "fomc_eve": fomc_due},
            },
            ensure_ascii=False,
            indent=2,
        ) + "\n",
        encoding="utf-8",
    )

    if monday_due:
        next_state["last_weekly_report_key"] = week_key
    if fomc_due:
        next_state["last_fomc_eve_report"] = date_key
    watcher.NEXT_STATE.write_text(json.dumps(next_state, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    with watcher.STATUS.open("a", encoding="utf-8") as f:
        if monday_due:
            f.write("- 예약 발송: 월요일 주간 점검\n")
        if fomc_due:
            f.write("- 예약 발송: FOMC 전날 점검\n")
        if cross_due:
            f.write(f"- 채권→Nasdaq 전이 단계 상승: {cross_gate_base}→{stage} ({cross.get('label')})\n")
        elif cross_episode_reset:
            f.write("- 채권→Nasdaq 이중 스퀴즈 에피소드 종료 확인 · 알림 래치 0으로 재설정\n")
    return rc


audited.format_alert = format_alert
watcher.main = scheduled_main

if __name__ == "__main__":
    raise SystemExit(watcher.main())
