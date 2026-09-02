#!/usr/bin/env python3
"""Capture the exact event-time Treasury-yield reaction around a new GDPNow update.

Purpose
- Never report the latest Treasury yield as if it were the yield at the GDPNow event.
- Resolve the exact latest FRED GDPNow update timestamp when available.
- Pull 1-minute Cboe TNX/TYX observations (via Yahoo Finance chart endpoint) around that timestamp.
- Save release-time, pre-event, +5 minute, +30 minute values and basis-point changes.

The intraday feed is used for event-time market reaction only. The main watcher still
keeps U.S. Treasury official daily par yields as an end-of-day validation source.
"""
from __future__ import annotations

import datetime as dt
import json
import pathlib
import re
import urllib.parse
import urllib.request
from html.parser import HTMLParser
from typing import Any
from zoneinfo import ZoneInfo

ROOT = pathlib.Path(__file__).resolve().parents[1]
OUT = ROOT / "out"
OUT.mkdir(parents=True, exist_ok=True)
PENDING = OUT / "gdpnow_long_rates_pending_state.json"
RESULT = OUT / "gdpnow_intraday_rate_reaction.json"

FRED_GDPNOW = "https://fred.stlouisfed.org/series/GDPNOW"
YAHOO_CHART = "https://query1.finance.yahoo.com/v8/finance/chart/{symbol}"
YAHOO_CHART_FALLBACK = "https://query2.finance.yahoo.com/v8/finance/chart/{symbol}"
USER_AGENT = "Mozilla/5.0 khs-watch-gdpnow-rates/1.0"
UTC = dt.timezone.utc
KST = ZoneInfo("Asia/Seoul")
CHICAGO = ZoneInfo("America/Chicago")
NEW_YORK = ZoneInfo("America/New_York")


class TextExtractor(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.parts: list[str] = []

    def handle_data(self, data: str) -> None:
        text = re.sub(r"\s+", " ", data).strip()
        if text:
            self.parts.append(text)


def http_get(url: str, timeout: int = 30) -> bytes:
    req = urllib.request.Request(
        url,
        headers={
            "User-Agent": USER_AGENT,
            "Accept": "*/*",
            "Cache-Control": "no-cache",
        },
    )
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.read()


def load_event_date() -> str | None:
    if not PENDING.exists():
        return None
    try:
        data = json.loads(PENDING.read_text(encoding="utf-8"))
        return str(((data.get("latest") or {}).get("date")) or "").strip() or None
    except Exception:
        return None


def fetch_fred_updated_at(event_date: str) -> tuple[dt.datetime | None, str | None]:
    """Return exact FRED update timestamp if the page timestamp matches event_date."""
    raw = http_get(FRED_GDPNOW).decode("utf-8", errors="replace")
    p = TextExtractor(); p.feed(raw)
    text = " ".join(p.parts)

    # Example: Updated: Sep 1, 2026 11:02 AM CDT
    m = re.search(
        r"Updated:\s*([A-Za-z]{3,9}\s+\d{1,2},\s+\d{4}\s+\d{1,2}:\d{2}\s+[AP]M)\s+(C[DS]T)",
        text,
        flags=re.I,
    )
    if not m:
        return None, "FRED GDPNow exact update timestamp not found"
    raw_time = m.group(1)
    try:
        naive = dt.datetime.strptime(raw_time, "%b %d, %Y %I:%M %p")
    except ValueError:
        try:
            naive = dt.datetime.strptime(raw_time, "%B %d, %Y %I:%M %p")
        except ValueError as exc:
            return None, f"FRED timestamp parse failed: {exc}"
    aware = naive.replace(tzinfo=CHICAGO)
    if aware.date().isoformat() != event_date:
        return None, f"FRED latest timestamp date {aware.date().isoformat()} != GDPNow event date {event_date}"
    return aware, None


def fetch_chart(symbol: str, start: dt.datetime, end: dt.datetime) -> list[tuple[dt.datetime, float]]:
    params = urllib.parse.urlencode({
        "period1": int(start.timestamp()),
        "period2": int(end.timestamp()),
        "interval": "1m",
        "includePrePost": "true",
        "events": "div,splits",
    })
    errors: list[str] = []
    for base in (YAHOO_CHART, YAHOO_CHART_FALLBACK):
        url = base.format(symbol=urllib.parse.quote(symbol, safe="")) + "?" + params
        try:
            payload = json.loads(http_get(url, timeout=25).decode("utf-8"))
            result = (((payload.get("chart") or {}).get("result") or [None])[0])
            if not result:
                raise RuntimeError(str((payload.get("chart") or {}).get("error") or "empty chart result"))
            timestamps = result.get("timestamp") or []
            quote = (((result.get("indicators") or {}).get("quote") or [{}])[0])
            closes = quote.get("close") or []
            points: list[tuple[dt.datetime, float]] = []
            for ts, close in zip(timestamps, closes):
                if ts is None or close is None:
                    continue
                try:
                    points.append((dt.datetime.fromtimestamp(int(ts), tz=UTC), float(close)))
                except Exception:
                    continue
            if not points:
                raise RuntimeError("no 1-minute points")
            return points
        except Exception as exc:
            errors.append(f"{base}: {type(exc).__name__}: {exc}")
    raise RuntimeError(" | ".join(errors))


def point_before(points: list[tuple[dt.datetime, float]], target: dt.datetime, max_age_min: int = 15) -> tuple[dt.datetime, float] | None:
    eligible = [p for p in points if p[0] <= target]
    if not eligible:
        return None
    p = eligible[-1]
    if (target - p[0]).total_seconds() > max_age_min * 60:
        return None
    return p


def point_nearest(points: list[tuple[dt.datetime, float]], target: dt.datetime, max_gap_min: int = 8) -> tuple[dt.datetime, float] | None:
    if not points:
        return None
    p = min(points, key=lambda x: abs((x[0] - target).total_seconds()))
    if abs((p[0] - target).total_seconds()) > max_gap_min * 60:
        return None
    return p


def pack_point(p: tuple[dt.datetime, float] | None) -> dict[str, Any] | None:
    if p is None:
        return None
    ts, value = p
    return {
        "timestamp_utc": ts.astimezone(UTC).isoformat(timespec="seconds"),
        "timestamp_et": ts.astimezone(NEW_YORK).isoformat(timespec="seconds"),
        "timestamp_kst": ts.astimezone(KST).isoformat(timespec="seconds"),
        "yield_pct": round(value, 4),
    }


def bp(after: tuple[dt.datetime, float] | None, before: tuple[dt.datetime, float] | None) -> float | None:
    if after is None or before is None:
        return None
    return round((after[1] - before[1]) * 100.0, 2)


def classify(ten: dict[str, Any], thirty: dict[str, Any], key: str) -> str:
    vals = [ten.get(key), thirty.get(key)]
    if any(v is None for v in vals):
        return "확인 불가"
    a, b = float(vals[0]), float(vals[1])
    if a >= 1.0 and b >= 1.0:
        return "금리 상승 확인"
    if a <= -1.0 and b <= -1.0:
        return "금리 하락 확인"
    if abs(a) < 1.0 and abs(b) < 1.0:
        return "반응 제한적"
    return "혼합"


def analyze_symbol(symbol: str, release_utc: dt.datetime) -> dict[str, Any]:
    points = fetch_chart(symbol, release_utc - dt.timedelta(hours=2), release_utc + dt.timedelta(hours=3))
    pre = point_before(points, release_utc - dt.timedelta(seconds=1), max_age_min=15)
    at = point_nearest(points, release_utc, max_gap_min=3)
    p5 = point_nearest(points, release_utc + dt.timedelta(minutes=5), max_gap_min=8)
    p30 = point_nearest(points, release_utc + dt.timedelta(minutes=30), max_gap_min=8)
    return {
        "symbol": symbol,
        "pre": pack_point(pre),
        "at_release": pack_point(at),
        "plus_5m": pack_point(p5),
        "plus_30m": pack_point(p30),
        "change_at_bp": bp(at, pre),
        "change_5m_bp": bp(p5, pre),
        "change_30m_bp": bp(p30, pre),
    }


def main() -> int:
    if RESULT.exists():
        RESULT.unlink()
    event_date = load_event_date()
    if not event_date:
        return 0

    release_ct, error = fetch_fred_updated_at(event_date)
    out: dict[str, Any] = {
        "event_date": event_date,
        "source_release_timestamp": "FRED GDPNow Updated timestamp",
        "intraday_source": "Cboe TNX/TYX via Yahoo Finance 1-minute chart data",
        "official_daily_validation": "U.S. Treasury daily par yield curve in main watcher",
        "error": error,
    }
    if release_ct is None:
        RESULT.write_text(json.dumps(out, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        return 0

    release_utc = release_ct.astimezone(UTC)
    out.update({
        "release_timestamp_ct": release_ct.isoformat(timespec="seconds"),
        "release_timestamp_et": release_ct.astimezone(NEW_YORK).isoformat(timespec="seconds"),
        "release_timestamp_kst": release_ct.astimezone(KST).isoformat(timespec="seconds"),
    })

    try:
        ten = analyze_symbol("^TNX", release_utc)
        thirty = analyze_symbol("^TYX", release_utc)
        out["ten_year"] = ten
        out["thirty_year"] = thirty
        out["market_confirmation_at"] = classify(ten, thirty, "change_at_bp")
        out["market_confirmation_5m"] = classify(ten, thirty, "change_5m_bp")
        out["market_confirmation_30m"] = classify(ten, thirty, "change_30m_bp")
        out["error"] = None
    except Exception as exc:
        out["error"] = f"{type(exc).__name__}: {exc}"

    RESULT.write_text(json.dumps(out, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
