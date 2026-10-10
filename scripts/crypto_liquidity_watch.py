#!/usr/bin/env python3
from __future__ import annotations

import datetime as dt
import calendar
import hashlib
import json
import pathlib
import re
import urllib.request
from dataclasses import dataclass
from zoneinfo import ZoneInfo

from bs4 import BeautifulSoup

ROOT = pathlib.Path(__file__).resolve().parents[1]
STATE_PATH = ROOT / "data" / "crypto_liquidity_watch_state.json"
OUT_DIR = ROOT / "out"
PENDING_STATE = OUT_DIR / "crypto_liquidity_watch_pending_state.json"
ALERT_PATH = OUT_DIR / "crypto_liquidity_watch_telegram.txt"
STATUS_PATH = OUT_DIR / "crypto_liquidity_watch_status.md"

TREASURY_BUYBACK_XML = "https://home.treasury.gov/system/files/221/Tentative-Buyback-Schedule.xml"
TREASURY_BUYBACK_PAGE = "https://www.treasurydirect.gov/auctions/announcements-data-results/buy-backs/"
TREASURY_RATES_URL = "https://home.treasury.gov/resource-center/data-chart-center/interest-rates/TextView?field_tdr_date_value=2026&type=daily_treasury_yield_curve"
FARSIDE_BTC_ETF_URL = "https://farside.co.uk/btc/"
FARSIDE_BTC_HISTORY_URL = "https://farside.co.uk/bitcoin-etf-flow-all-data/"
FUND_TICKERS = ("IBIT", "FBTC", "BITB", "ARKB", "BTCO", "EZBC", "BRRR", "HODL", "BTCW", "MSBT", "GBTC", "BTC")

UA = "Mozilla/5.0 (compatible; khs-watch/1.0; +https://github.com/qedgwangju-dot/khs-watch)"
KST = ZoneInfo("Asia/Seoul")


def fetch(url: str, timeout: int = 35) -> bytes:
    req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept": "*/*"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.read()


def load_state() -> dict:
    if not STATE_PATH.exists():
        return {}
    try:
        return json.loads(STATE_PATH.read_text(encoding="utf-8"))
    except Exception:
        return {}


def atomic_write(path: pathlib.Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def sha256_bytes(data: bytes) -> str:
    normalized = b"\n".join(line.strip() for line in data.replace(b"\r\n", b"\n").split(b"\n") if line.strip())
    return hashlib.sha256(normalized).hexdigest()


def parse_number(text: str) -> float | None:
    s = (text or "").strip().replace(",", "").replace("$", "")
    if not s or s in {"-", "—", "N/A", "n/a"}:
        return None
    neg = s.startswith("(") and s.endswith(")")
    if neg:
        s = s[1:-1]
    m = re.search(r"[-+]?\d+(?:\.\d+)?", s)
    if not m:
        return None
    value = float(m.group(0))
    return -abs(value) if neg else value


def parse_date(text: str) -> dt.date | None:
    s = " ".join((text or "").split())
    for fmt in ("%m/%d/%Y", "%d %b %Y", "%d %B %Y", "%Y-%m-%d"):
        try:
            return dt.datetime.strptime(s, fmt).date()
        except ValueError:
            pass
    return None


def treasury_rates() -> dict:
    html = fetch(TREASURY_RATES_URL).decode("utf-8", errors="replace")
    soup = BeautifulSoup(html, "html.parser")
    rows: list[tuple[dt.date, float, float]] = []
    for tr in soup.find_all("tr"):
        cells = [" ".join(td.get_text(" ", strip=True).split()) for td in tr.find_all(["td", "th"])]
        if len(cells) < 4:
            continue
        d = parse_date(cells[0])
        if not d:
            continue
        y10 = parse_number(cells[-3])
        y30 = parse_number(cells[-1])
        if y10 is None or y30 is None:
            continue
        rows.append((d, y10, y30))
    if not rows:
        raise RuntimeError("Treasury 10Y/30Y rows could not be parsed")
    rows.sort(key=lambda x: x[0])
    latest = rows[-1]
    prev = rows[-2] if len(rows) >= 2 else latest
    prev5 = rows[-6] if len(rows) >= 6 else rows[0]
    return {
        "date": latest[0].isoformat(),
        "10y": latest[1],
        "30y": latest[2],
        "prev_date": prev[0].isoformat(),
        "prev_10y": prev[1],
        "prev_30y": prev[2],
        "daily_10y_bp": round((latest[1] - prev[1]) * 100, 1),
        "daily_30y_bp": round((latest[2] - prev[2]) * 100, 1),
        "prev5_date": prev5[0].isoformat(),
        "prev5_10y": prev5[1],
        "prev5_30y": prev5[2],
        "five_day_10y_bp": round((latest[1] - prev5[1]) * 100, 1),
        "five_day_30y_bp": round((latest[2] - prev5[2]) * 100, 1),
    }


def months_before(date: dt.date, months: int) -> dt.date:
    number = date.year * 12 + date.month - 1 - months
    year, month_index = divmod(number, 12)
    month = month_index + 1
    return dt.date(year, month, min(date.day, calendar.monthrange(year, month)[1]))


def flow_direction(previous: float, current: float) -> str:
    if previous >= 0 > current:
        return "순유입→순유출 전환"
    if previous <= 0 < current:
        return "순유출→순유입 전환"
    if previous > 0 and current > 0:
        return "순유입 확대" if current > previous else "순유입 둔화" if current < previous else "유지"
    if previous < 0 and current < 0:
        return "순유출 축소" if current > previous else "순유출 확대" if current < previous else "유지"
    return "혼조"


def calendar_period(rows: list[dict], start: dt.date, end: dt.date, minimum: int) -> dict:
    selected = [
        row for row in rows
        if start <= row["date"] <= end and row["total_validated"]
        and row["status"] in ("partial", "complete")
    ]
    dates = sorted(row["date"] for row in selected)
    gaps = [(b-a).days for a,b in zip(dates,dates[1:])]
    valid = bool(len(dates) >= minimum
        and dates[0] <= start + dt.timedelta(days=7)
        and dates[-1] >= end - dt.timedelta(days=7)
        and (not gaps or max(gaps) <= 7))
    return {
        "valid": valid, "start": start.isoformat(), "end": end.isoformat(),
        "trading_days": len(selected),
        "partial_days": sum(row["status"] == "partial" for row in selected),
        "value_usd_m": round(sum(row["total"] for row in selected), 1) if valid else None,
    }


def calendar_windows(rows: list[dict], latest: dt.date) -> dict:
    result = {}
    for months, label, minimum in ((1, "1m", 12), (3, "3m", 40)):
        start = months_before(latest, months) + dt.timedelta(days=1)
        prev_end = start - dt.timedelta(days=1)
        prev_start = months_before(prev_end, months) + dt.timedelta(days=1)
        current = calendar_period(rows, start, latest, minimum)
        previous = calendar_period(rows, prev_start, prev_end, minimum)
        valid = current["valid"] and previous["valid"]
        current.update({
            "valid": valid,
            "prev_start": prev_start.isoformat(), "prev_end": prev_end.isoformat(),
            "prev_trading_days": previous["trading_days"],
            "prev_partial_days": previous["partial_days"],
            "prev_value_usd_m": previous["value_usd_m"] if valid else None,
            "change_usd_m": round(current["value_usd_m"] - previous["value_usd_m"], 1) if valid else None,
            "direction": flow_direction(previous["value_usd_m"], current["value_usd_m"]) if valid else "확인 불가",
            "status": "잠정" if (current["partial_days"] or previous["partial_days"]) else "확정",
        })
        if not valid:
            current["value_usd_m"] = None
            current["status"] = "확인 불가"
        result[label] = current
    return result


def btc_etf_flow() -> dict:
    # /btc/ carries the latest rolling rows; the all-data endpoint is required
    # for true 1/3-calendar-month and previous-period comparisons.
    html = fetch(FARSIDE_BTC_ETF_URL)
    history_error = ""
    try:
        historical_html = fetch(FARSIDE_BTC_HISTORY_URL)
    except Exception as exc:
        historical_html = None
        history_error = f"Farside historical source unavailable: {exc}"
    table_rows: list[tuple[str, list[str]]] = []
    history_row_count = 0
    for source, raw in (("live", html), ("all-data", historical_html)):
        if raw is None:
            continue
        soup = BeautifulSoup(raw.decode("utf-8", errors="replace"), "html.parser")
        original_rows = [
            [" ".join(td.get_text(" ", strip=True).split()) for td in tr.find_all(["td", "th"])]
            for tr in soup.find_all("tr")
        ]
        # The all-data source sometimes has malformed/unclosed <tr> tags:
        # one BeautifulSoup row can contain thousands of sequential cells.
        # Reconstruct exact date+12-funds+total records, never guess columns.
        page_rows = []
        for cells in original_rows:
            if len(cells) <= len(FUND_TICKERS) + 2:
                page_rows.append(cells)
                continue
            dates = [i for i, cell in enumerate(cells) if parse_date(cell) is not None]
            if not dates:
                page_rows.append(cells)
                continue
            if dates[0]:
                page_rows.append(cells[:dates[0]])
            for index, offset in enumerate(dates):
                boundary = dates[index + 1] if index + 1 < len(dates) else len(cells)
                record = cells[offset:offset + 14]
                if len(record) != 14 or (index + 1 < len(dates) and boundary != offset + 14):
                    raise RuntimeError(
                        f"Farside {source} historical record width invalid at {cells[offset]}"
                    )
                page_rows.append(record)
        if not any([x.upper() for x in row[1:13]] == list(FUND_TICKERS) for row in page_rows):
            raise RuntimeError(f"Farside {source} 12-ETF header not verified")
        if source == "all-data":
            history_row_count = sum(parse_date(row[0]) is not None for row in page_rows if row)
        table_rows += [(source, cells) for cells in page_rows]
    # A layout change must never silently move totals between funds or treat
    # a missing fund report as a literal zero.
    header_matches = [
        cells for source, cells in table_rows
        if all(ticker in cells for ticker in FUND_TICKERS)
        and [cells.index(ticker) for ticker in FUND_TICKERS]
            == sorted(cells.index(ticker) for ticker in FUND_TICKERS)
    ]
    if not header_matches:
        raise RuntimeError("Farside BTC fund ticker header not verified; table layout may have changed")

    rows: list[dict] = []
    for source, cells in table_rows:
        if len(cells) < 3:
            continue
        d = parse_date(cells[0])
        if not d:
            continue

        fund_cells = cells[1:-1]
        if len(fund_cells) != len(FUND_TICKERS):
            raise RuntimeError(
                f"Farside BTC fund column drift on {d}: {len(fund_cells)} != {len(FUND_TICKERS)}"
            )
        normalized = [x.strip() for x in fund_cells]
        numeric_funds = [parse_number(x) for x in normalized if x not in {"", "-", "—"}]
        reported_count = sum(v is not None for v in numeric_funds)
        missing_count = sum(x in {"", "-", "—"} for x in normalized)
        if reported_count + missing_count != len(FUND_TICKERS):
            raise RuntimeError(f"Farside unknown BTC fund cell on {d}: {normalized}")
        missing_tickers = [
            ticker for ticker, value in zip(FUND_TICKERS, normalized)
            if value in {"", "-", "—"}
        ]
        total = parse_number(cells[-1])
        recomputed_total = round(sum(v for v in numeric_funds if v is not None), 1) if numeric_funds else None

        # Farside sometimes pre-fills a future date with a handful of "0.0"
        # values while most funds remain unreported. That is NOT a 0-flow day.
        all_reported_zero = (
            reported_count > 0
            and all(v is None or abs(float(v)) < 1e-12 for v in numeric_funds)
        )
        zero_only_partial_placeholder = (
            missing_count > 0
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
            "missing_tickers": missing_tickers,
            "zero_only_partial_placeholder": zero_only_partial_placeholder,
            "recomputed_total": recomputed_total,
            "total_gap": total_gap,
            "total_validated": total_validated,
            "source": source,
        })

    if not rows:
        raise RuntimeError("Farside BTC ETF flow rows could not be parsed")

    dedup: dict[dt.date, dict] = {}
    for row in rows:
        date = row["date"]
        existing = dedup.get(date)
        if existing is None:
            dedup[date] = row
            continue
        a, b = existing["reported_funds"], row["reported_funds"]
        if row["total_validated"] and not existing["total_validated"]:
            dedup[date] = row
        elif b > a:
            dedup[date] = row
        elif b == a and row["total_validated"] and existing["total_validated"]:
            if abs(row["total"] - existing["total"]) >= 0.1:
                raise RuntimeError(
                    f"Farside live/all-data disagreement on {date}: "
                    f"{existing['total']} vs {row['total']} (both {a}/12)"
                )
    rows = [dedup[d] for d in sorted(dedup)]
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

    windows = calendar_windows(valid_rows, latest_valid["date"])
    if history_error or history_row_count < 120:
        for window in windows.values():
            window.update({
                "valid": False, "value_usd_m": None, "prev_value_usd_m": None,
                "change_usd_m": None, "direction": "확인 불가",
                "status": "확인 불가",
                "error": history_error or "1·3개월 계산에 필요한 과거 원자료 미확보",
            })

    return {
        "date": latest_valid["date"].isoformat(),
        "total_usd_m": latest_valid["total"],
        "status": latest_valid["status"],
        "reported_funds": latest_valid["reported_funds"],
        "missing_funds": latest_valid["missing_funds"],
        "missing_tickers": latest_valid["missing_tickers"],
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
        "windows": windows,
        "history_source": FARSIDE_BTC_HISTORY_URL,
        "history_row_count": history_row_count,
        "history_error": history_error,
    }


def buyback_schedule() -> dict:
    xml = fetch(TREASURY_BUYBACK_XML)
    text = xml.decode("utf-8", errors="replace")
    compact = " ".join(re.sub(r"<[^>]+>", " ", text).split())
    snippets = []
    for pattern in (r".{0,100}10.{0,12}20.{0,160}", r".{0,100}20.{0,12}30.{0,160}"):
        m = re.search(pattern, compact, flags=re.I)
        if m:
            snippets.append(m.group(0).strip())
    return {
        "sha256": sha256_bytes(xml),
        "bytes": len(xml),
        "long_bucket_summary": " | ".join(snippets)[:700],
    }


def signed_millions(value: float) -> str:
    sign = "+" if value > 0 else ""
    return f"{sign}{value:,.1f}백만달러"


def signed_pct(value: float | None) -> str:
    if value is None:
        return "비교 불가"
    sign = "+" if value > 0 else ""
    return f"{sign}{value:,.1f}%"


def _partial_snapshot(etf: dict, observed_at_kst: str) -> dict:
    reported = int(etf.get("reported_funds", 0) or 0)
    missing = int(etf.get("missing_funds", 0) or 0)
    return {
        "observed_at_kst": observed_at_kst,
        "total_usd_m": float(etf.get("total_usd_m", 0.0) or 0.0),
        "reported_funds": reported,
        "missing_funds": missing,
        "coverage": f"{reported}/{reported + missing}" if (reported + missing) else "",
    }


def _same_snapshot(a: dict, b: dict) -> bool:
    return (
        round(float(a.get("total_usd_m", 0.0) or 0.0), 1)
        == round(float(b.get("total_usd_m", 0.0) or 0.0), 1)
        and int(a.get("reported_funds", 0) or 0) == int(b.get("reported_funds", 0) or 0)
        and int(a.get("missing_funds", 0) or 0) == int(b.get("missing_funds", 0) or 0)
    )


def carry_partial_history(old_state: dict, etf: dict, observed_at_kst: str) -> dict:
    old_etf = old_state.get("btc_etf") or {}
    new_date = str(etf.get("date") or "")
    old_date = str(old_etf.get("date") or "")
    history: list[dict] = []

    if new_date and new_date == old_date:
        history = [
            x for x in (old_etf.get("provisional_history") or [])
            if isinstance(x, dict)
        ]
        if old_etf.get("status") == "partial":
            old_snapshot = _partial_snapshot(
                old_etf,
                str(old_state.get("updated_at_kst") or observed_at_kst),
            )
            if not history or not _same_snapshot(history[-1], old_snapshot):
                history.append(old_snapshot)

    if etf.get("status") == "partial":
        current_snapshot = _partial_snapshot(etf, observed_at_kst)
        if not history or not _same_snapshot(history[-1], current_snapshot):
            history.append(current_snapshot)

    etf["provisional_history"] = history[-12:]
    return etf


def reject_etf_source_regression(old_etf: dict, new_etf: dict) -> str | None:
    """Reject stale CDN snapshots without treating a report as an outflow change."""
    if not old_etf or not new_etf:
        return None
    old_date, new_date = str(old_etf.get("date") or ""), str(new_etf.get("date") or "")
    if old_date and (not new_date or new_date < old_date):
        return f"Farside stale trade date {new_date or 'missing'} < {old_date}"
    if old_date != new_date:
        return None
    old_count = int(old_etf.get("reported_funds", 0) or 0)
    new_count = int(new_etf.get("reported_funds", 0) or 0)
    if new_count < old_count:
        return f"Farside same-day coverage regression {new_count}/{len(FUND_TICKERS)} < {old_count}/{len(FUND_TICKERS)}"
    if old_etf.get("status") == "complete" and new_etf.get("status") != "complete":
        return "Farside complete-day snapshot regressed to partial"
    old_missing = set(old_etf.get("missing_tickers") or [])
    new_missing = set(new_etf.get("missing_tickers") or [])
    if old_missing and new_missing and not new_missing.issubset(old_missing):
        return f"Farside missing-fund set changed unexpectedly: {sorted(old_missing)} -> {sorted(new_missing)}"
    return None


def market_read(rates: dict, etf: dict) -> str:
    rate_date = rates.get("date")
    etf_date = etf.get("date")
    if not rate_date or not etf_date:
        return "종합판정 보류: 기준일 확인 불가"
    if rate_date != etf_date:
        return f"종합판정 보류: 기준일 불일치(미 국채 {rate_date} / BTC ETF {etf_date})"
    if etf.get("status") != "complete":
        return f"종합판정 보류: BTC ETF {etf_date} 집계 미완료"

    r10 = rates.get("daily_10y_bp", 0.0)
    r30 = rates.get("daily_30y_bp", 0.0)
    flow = etf.get("total_usd_m", 0.0)
    if r10 <= 0 and r30 <= 0 and flow > 0:
        return f"{rate_date} 기준 위험자산에 우호적: 장기금리 하락 + BTC ETF 순유입"
    if r10 >= 0 and r30 >= 0 and flow < 0:
        return f"{rate_date} 기준 위험자산에 불리: 장기금리 상승 + BTC ETF 순유출"
    return f"{rate_date} 기준 혼조: 금리와 ETF 자금흐름이 같은 방향이 아님"


def dated_values(obj: dict) -> dict[str, float]:
    result: dict[str, float] = {}
    for dates_key, values_key in (("prev5_dates", "prev5_values_usd_m"), ("last5_dates", "last5_values_usd_m")):
        for d, value in zip(obj.get(dates_key) or [], obj.get(values_key) or []):
            if d is not None and value is not None:
                result[str(d)] = float(value)
    return result


def main() -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    ALERT_PATH.unlink(missing_ok=True)

    old = load_state()
    now_kst = dt.datetime.now(KST).isoformat(timespec="seconds")
    errors: list[str] = []

    try:
        buyback = buyback_schedule()
    except Exception as e:
        errors.append(f"buyback: {e}")
        buyback = old.get("buyback") or {}

    try:
        rates = treasury_rates()
    except Exception as e:
        errors.append(f"rates: {e}")
        rates = old.get("rates") or {}

    try:
        etf = btc_etf_flow()
        regression = reject_etf_source_regression(old.get("btc_etf") or {}, etf)
        if regression:
            errors.append(f"btc_etf: {regression}; prior validated snapshot retained")
            etf = old.get("btc_etf") or {}
    except Exception as e:
        errors.append(f"btc_etf: {e}")
        etf = old.get("btc_etf") or {}

    etf = carry_partial_history(old, etf, now_kst)

    new_state = {
        "updated_at_kst": now_kst,
        "buyback": buyback,
        "rates": rates,
        "btc_etf": etf,
        "sources": {
            "treasury_buyback_xml": TREASURY_BUYBACK_XML,
            "treasury_buyback_page": TREASURY_BUYBACK_PAGE,
            "treasury_rates": TREASURY_RATES_URL,
            "farside_btc_etf": FARSIDE_BTC_ETF_URL,
            "farside_btc_etf_all": FARSIDE_BTC_HISTORY_URL,
        },
        "errors": errors,
    }
    atomic_write(PENDING_STATE, json.dumps(new_state, ensure_ascii=False, indent=2) + "\n")

    if not old:
        status = [
            "# 크립토 유동성 웹감시",
            "",
            "- 상태: 최초 기준값 저장 예정(텔레그램 미전송)",
            f"- 조회시각(KST): {now_kst}",
            f"- 미 국채 10Y/30Y: {rates.get('10y', 'N/A')}% / {rates.get('30y', 'N/A')}% ({rates.get('date', 'N/A')})",
            f"- BTC 현물 ETF 최신/직전: {signed_millions(etf.get('total_usd_m', 0.0)) if etf else 'N/A'} / {signed_millions(etf.get('prev_total_usd_m', 0.0)) if etf else 'N/A'} ({etf.get('date', 'N/A') if etf else 'N/A'} / {etf.get('prev_date', 'N/A') if etf else 'N/A'})",
            f"- BTC ETF 최근5/이전5: {signed_millions(etf.get('last5_usd_m', 0.0)) if etf else 'N/A'} / {signed_millions(etf.get('prev5_usd_m', 0.0)) if etf and etf.get('prev5_usd_m') is not None else 'N/A'}",
            f"- 오류: {'; '.join(errors) if errors else '없음'}",
        ]
        atomic_write(STATUS_PATH, "\n".join(status) + "\n")
        return

    triggers: list[str] = []

    old_buyback = old.get("buyback") or {}
    if buyback and old_buyback and buyback.get("sha256") != old_buyback.get("sha256"):
        triggers.append("미 재무부 공식 바이백 일정 XML 변경")

    old_rates = old.get("rates") or {}
    if rates and old_rates and rates.get("date") != old_rates.get("date"):
        d10 = (rates.get("10y", 0.0) - old_rates.get("10y", rates.get("10y", 0.0))) * 100
        d30 = (rates.get("30y", 0.0) - old_rates.get("30y", rates.get("30y", 0.0))) * 100
        if max(abs(d10), abs(d30)) >= 10.0:
            triggers.append(f"미 국채 장기금리 큰 변동: 10Y {d10:+.1f}bp / 30Y {d30:+.1f}bp")

    old_etf = old.get("btc_etf") or {}
    if etf and old_etf:
        old_date = old_etf.get("date")
        new_date = etf.get("date")
        pending_date = etf.get("pending_date")
        legacy_pending_zero = (
            pending_date
            and old_date == pending_date
            and float(old_etf.get("total_usd_m", 0.0) or 0.0) == 0.0
            and new_date != old_date
        )

        same_day_value_changed = (
            new_date == old_date
            and abs(
                etf.get("total_usd_m", 0.0)
                - old_etf.get("total_usd_m", etf.get("total_usd_m", 0.0))
            ) >= 0.1
        )
        partial_to_complete = (
            new_date == old_date
            and old_etf.get("status") == "partial"
            and etf.get("status") == "complete"
        )

        if new_date != old_date and not legacy_pending_zero:
            qualifier = "잠정 집계" if etf.get("status") == "partial" else "현재 전체 집계"
            triggers.append(
                f"BTC 현물 ETF 새 일간 자금흐름({qualifier}): "
                f"{signed_millions(etf.get('total_usd_m', 0.0))}"
            )
        elif partial_to_complete:
            history = etf.get("provisional_history") or []
            first_partial = history[0] if history else _partial_snapshot(
                old_etf, str(old.get("updated_at_kst") or now_kst)
            )
            last_partial = history[-1] if history else first_partial
            final_reported = int(etf.get("reported_funds", 0) or 0)
            final_missing = int(etf.get("missing_funds", 0) or 0)
            final_total = final_reported + final_missing
            first_cov = str(first_partial.get("coverage") or "")
            last_cov = str(last_partial.get("coverage") or "")
            final_cov = f"{final_reported}/{final_total}" if final_total else ""
            if same_day_value_changed:
                triggers.append(
                    "BTC 현물 ETF 최종 확정: "
                    f"최초 잠정 {signed_millions(float(first_partial.get('total_usd_m', 0.0) or 0.0))}"
                    f"{f' ({first_cov})' if first_cov else ''} → "
                    f"직전 잠정 {signed_millions(float(last_partial.get('total_usd_m', 0.0) or 0.0))}"
                    f"{f' ({last_cov})' if last_cov else ''} → "
                    f"최종 {signed_millions(etf.get('total_usd_m', 0.0))}"
                    f"{f' ({final_cov})' if final_cov else ''}"
                )
            else:
                triggers.append(
                    "BTC 현물 ETF 최종 확정(값 동일): "
                    f"직전 잠정 {signed_millions(float(last_partial.get('total_usd_m', 0.0) or 0.0))}"
                    f"{f' ({last_cov})' if last_cov else ''} → "
                    f"최종 {signed_millions(etf.get('total_usd_m', 0.0))}"
                    f"{f' ({final_cov})' if final_cov else ''}"
                )
        elif same_day_value_changed:
            qualifier = "잠정 집계" if etf.get("status") == "partial" else "현재 집계"
            triggers.append(
                f"BTC 현물 ETF 당일 합계 수정({qualifier}): "
                f"{signed_millions(old_etf.get('total_usd_m', 0.0))} → "
                f"{signed_millions(etf.get('total_usd_m', 0.0))}"
            )

        # One-time upgrade notice is explicitly a new indicator, not a new
        # market-flow event. Revisions to older dates still affect monthly sums.
        old_windows = old_etf.get("windows") or {}
        new_windows = etf.get("windows") or {}
        if not old_windows and all((new_windows.get(key) or {}).get("valid") for key in ("1m", "3m")):
            triggers.append("BTC 현물 ETF 1개월·3개월 누적 지표 검증 완료(신규 표시)")
        elif new_date == old_date and not same_day_value_changed and not partial_to_complete:
            for key, amount in (("1m", 20.0), ("3m", 50.0)):
                old_window = old_windows.get(key) or {}
                new_window = new_windows.get(key) or {}
                if (old_window.get("valid") and new_window.get("valid")
                        and old_window.get("start") == new_window.get("start")):
                    before = float(old_window["value_usd_m"])
                    after = float(new_window["value_usd_m"])
                    if abs(after - before) >= amount or before * after < 0:
                        triggers.append(
                            f"BTC 현물 ETF {key.upper()} 과거 누적 재계산: "
                            f"{signed_millions(before)} → {signed_millions(after)}"
                        )

        old_values = dated_values(old_etf)
        new_values = dated_values(etf)
        revisions = []
        for d in sorted(set(old_values) & set(new_values)):
            # The current trading day's partial→final update is already reported
            # above. Only genuinely older dates belong in "과거 원자료 수정".
            if d == new_date:
                continue
            old_value = old_values[d]
            new_value = new_values[d]
            if abs(new_value - old_value) >= 0.1:
                revisions.append(f"{d} {signed_millions(old_value)} → {signed_millions(new_value)}")
        if revisions:
            triggers.append("BTC 현물 ETF 과거 원자료 수정: " + " / ".join(revisions))

        if new_date != old_date and old_etf.get("last5_usd_m") is not None and etf.get("last5_usd_m") is not None:
            d_last5 = round(etf.get("last5_usd_m") - old_etf.get("last5_usd_m"), 1)
            d_prev5 = (
                round(etf.get("prev5_usd_m") - old_etf.get("prev5_usd_m"), 1)
                if old_etf.get("prev5_usd_m") is not None and etf.get("prev5_usd_m") is not None
                else None
            )
            movement = (
                f"최근5 {signed_millions(old_etf.get('last5_usd_m', 0.0))} → {signed_millions(etf.get('last5_usd_m', 0.0))} ({signed_millions(d_last5)})"
            )
            if d_prev5 is not None:
                movement += (
                    f" / 이전5 {signed_millions(old_etf.get('prev5_usd_m', 0.0))} → {signed_millions(etf.get('prev5_usd_m', 0.0))} ({signed_millions(d_prev5)})"
                )
            triggers.append("BTC 현물 ETF 5거래일 구간 이동: " + movement)

    if triggers:
        lines = [
            "[크립토 유동성 변화 감지]",
            f"조회시각(KST): {now_kst}",
            "",
            *[f"• {x}" for x in triggers],
            "",
        ]
        if rates:
            lines += [
                f"미 국채 — 미 재무부 공식 수익률곡선 기준일 {rates.get('date', 'N/A')}",
                f"• 10Y {rates.get('10y', 0):.2f}% | 직전 공식일({rates.get('prev_date', 'N/A')}) 대비 {rates.get('daily_10y_bp', 0):+.1f}bp | 5거래일 {rates.get('five_day_10y_bp', 0):+.1f}bp",
                f"• 30Y {rates.get('30y', 0):.2f}% | 직전 공식일({rates.get('prev_date', 'N/A')}) 대비 {rates.get('daily_30y_bp', 0):+.1f}bp | 5거래일 {rates.get('five_day_30y_bp', 0):+.1f}bp",
                "※ 미 재무부 일일 수익률은 장중 실시간 시세가 아니라 약 3:30 PM ET 시장 호가를 바탕으로 산출되는 공식 일일값",
                "",
            ]
        if etf:
            etf_status = "잠정 집계" if etf.get("status") == "partial" else "현재 집계 완료(추후 수정 가능)"
            lines += [
                f"BTC 현물 ETF — Farside 기준 최신 유효일 {etf.get('date')}",
                f"• 최신: {etf.get('date')} {signed_millions(etf.get('total_usd_m', 0.0))} ({etf_status}, 개별 ETF 합계 재검산 {'일치' if etf.get('latest_total_validated') else '불일치'})",
                f"• 직전: {etf.get('prev_date')} {signed_millions(etf.get('prev_total_usd_m', 0.0))}",
                f"• 전일 대비: {signed_millions(etf.get('day_change_usd_m', 0.0))} ({signed_pct(etf.get('day_change_pct'))})",
            ]
            if etf.get("five_day_compare_valid"):
                last5_dates = etf.get("last5_dates") or []
                prev5_dates = etf.get("prev5_dates") or []
                last5_range = f"{last5_dates[0]}~{last5_dates[-1]}" if len(last5_dates) == 5 else "기간 확인 불가"
                prev5_range = f"{prev5_dates[0]}~{prev5_dates[-1]}" if len(prev5_dates) == 5 else "기간 확인 불가"
                direction = etf.get("five_day_direction") or "판정 불가"
                lines += [
                    f"• 최근 5거래일({last5_range}): {signed_millions(etf.get('last5_usd_m', 0.0))}",
                    f"• 이전 5거래일({prev5_range}): {signed_millions(etf.get('prev5_usd_m', 0.0))}",
                    f"• 5거래일 구간 대비: {signed_millions(etf.get('five_day_change_usd_m', 0.0))} | {direction}",
                ]
                if etf.get("five_day_change_pct") is not None:
                    lines += [f"• 5거래일 변화율: {signed_pct(etf.get('five_day_change_pct'))}"]
                elif etf.get("prev5_usd_m", 0.0) * etf.get("last5_usd_m", 0.0) < 0:
                    lines += ["• 5거래일 변화율: 부호 전환 구간이라 % 비교하지 않음"]
            else:
                lines += ["• 5거래일 구간 대비: 검증된 10개 거래일이 확보될 때까지 계산 보류"]
            # Rolling 1M/3M = literal calendar-month windows, not 21/63 assumed sessions.
            for label in ("1m", "3m"):
                item = ((etf.get("windows") or {}).get(label) or {})
                if item.get("valid"):
                    lines.append(
                        f"• 최근 {label.upper()} 달력기간({item['start']}~{item['end']}, "
                        f"{item['trading_days']}거래일): {signed_millions(item['value_usd_m'])} "
                        f"({item['status']}, 미보고 거래일 {item['partial_days']}일)"
                    )
                    lines.append(
                        f"• 직전 {label.upper()} 달력기간({item['prev_start']}~{item['prev_end']}, "
                        f"{item['prev_trading_days']}거래일): {signed_millions(item['prev_value_usd_m'])} "
                        f"| 차이 {signed_millions(item['change_usd_m'])} · {item['direction']}"
                    )
                else:
                    lines.append(f"• {label.upper()} 누적: 원자료 미확보 · 계산 보류")
            if etf.get("pending_date"):
                lines += [f"※ {etf.get('pending_date')}: 전 ETF 미보고(-) → 0.0으로 간주하지 않고 미집계 처리"]
            lines += [""]
        if rates and etf:
            lines += [f"판단: {market_read(rates, etf)}"]
        lines += [
            "",
            "공식·데이터 원천:",
            f'• 미 재무부 바이백: <a href="{TREASURY_BUYBACK_PAGE}">원문</a>',
            f'• 미 국채 금리: <a href="{TREASURY_RATES_URL}">원문</a>',
            f'• BTC 현물 ETF: <a href="{FARSIDE_BTC_ETF_URL}">원문</a>',
            "",
            "※ CLARITY Act는 기존 별도 공식 웹감시가 계속 담당합니다.",
        ]
        atomic_write(ALERT_PATH, "\n".join(lines).strip() + "\n")

    status = [
        "# 크립토 유동성 웹감시",
        "",
        f"- 조회시각(KST): {now_kst}",
        f"- 알림 트리거: {len(triggers)}개",
        f"- 바이백 XML 변경: {'예' if (buyback and old_buyback and buyback.get('sha256') != old_buyback.get('sha256')) else '아니오'}",
        f"- 미 국채 10Y/30Y: {rates.get('10y', 'N/A')}% / {rates.get('30y', 'N/A')}% ({rates.get('date', 'N/A')})",
        f"- BTC 현물 ETF: {signed_millions(etf.get('total_usd_m', 0.0)) if etf else 'N/A'} ({etf.get('date', 'N/A') if etf else 'N/A'})",
        f"- ETF 1M: {((etf.get('windows') or {}).get('1m') or {}).get('value_usd_m', 'unavailable')} (status: {((etf.get('windows') or {}).get('1m') or {}).get('status', 'unknown')})",
        f"- ETF 3M: {((etf.get('windows') or {}).get('3m') or {}).get('value_usd_m', 'unavailable')} (status: {((etf.get('windows') or {}).get('3m') or {}).get('status', 'unknown')})",
        f"- ETF history: {etf.get('history_row_count', 0)} rows; {etf.get('history_error') or 'OK'}",
        f"- 오류: {'; '.join(errors) if errors else '없음'}",
    ]
    atomic_write(STATUS_PATH, "\n".join(status) + "\n")


if __name__ == "__main__":
    main()
