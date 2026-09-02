#!/usr/bin/env python3
"""Capture exact event-time Treasury-yield and oil reaction around a GDPNow update.

Purpose
- Never report a later/current market value as if it were the value at the GDPNow event.
- Resolve the exact latest FRED GDPNow update timestamp when available.
- Pull 1-minute Cboe TNX/TYX and Brent/WTI futures observations around that timestamp.
- Save release-time, pre-event, +5 minute, +30 minute values.
- For oil, also compare the event-time price with the prior daily close so the alert can
  distinguish an independent inflation impulse from the GDPNow signal itself.

The intraday feed is for event-time context. U.S. Treasury official daily par yields
remain the end-of-day validation source in the main watcher.
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
USER_AGENT = "Mozilla/5.0 khs-watch-gdpnow-rates/1.1"
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
        headers={"User-Agent": USER_AGENT, "Accept": "*/*", "Cache-Control": "no-cache"},
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
    raw = http_get(FRED_GDPNOW).decode("utf-8", errors="replace")
    p = TextExtractor(); p.feed(raw)
    text = " ".join(p.parts)
    m = re.search(
        r"Updated:\s*([A-Za-z]{3,9}\s+\d{1,2},\s+\d{4}\s+\d{1,2}:\d{2}\s+[AP]M)\s+(C[DS]T)",
        text,
        flags=re.I,
    )
    if not m:
        return None, "FRED GDPNow exact update timestamp not found"
    raw_time = m.group(1)
    for fmt in ("%b %d, %Y %I:%M %p", "%B %d, %Y %I:%M %p"):
        try:
            naive = dt.datetime.strptime(raw_time, fmt)
            break
        except ValueError:
            naive = None
    if naive is None:
        return None, "FRED timestamp parse failed"
    aware = naive.replace(tzinfo=CHICAGO)
    if aware.date().isoformat() != event_date:
        return None, f"FRED latest timestamp date {aware.date().isoformat()} != GDPNow event date {event_date}"
    return aware, None


def fetch_chart(symbol: str, start: dt.datetime, end: dt.datetime, interval: str = "1m") -> list[tuple[dt.datetime, float]]:
    params = urllib.parse.urlencode({
        "period1": int(start.timestamp()),
        "period2": int(end.timestamp()),
        "interval": interval,
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
                points.append((dt.datetime.fromtimestamp(int(ts), tz=UTC), float(close)))
            if not points:
                raise RuntimeError(f"no {interval} points")
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


def pack_yield_point(p: tuple[dt.datetime, float] | None) -> dict[str, Any] | None:
    if p is None:
        return None
    ts, value = p
    return {
        "timestamp_utc": ts.astimezone(UTC).isoformat(timespec="seconds"),
        "timestamp_et": ts.astimezone(NEW_YORK).isoformat(timespec="seconds"),
        "timestamp_kst": ts.astimezone(KST).isoformat(timespec="seconds"),
        "yield_pct": round(value, 4),
    }


def pack_price_point(p: tuple[dt.datetime, float] | None) -> dict[str, Any] | None:
    if p is None:
        return None
    ts, value = p
    return {
        "timestamp_utc": ts.astimezone(UTC).isoformat(timespec="seconds"),
        "timestamp_et": ts.astimezone(NEW_YORK).isoformat(timespec="seconds"),
        "timestamp_kst": ts.astimezone(KST).isoformat(timespec="seconds"),
        "price_usd": round(value, 4),
    }


def bp(after: tuple[dt.datetime, float] | None, before: tuple[dt.datetime, float] | None) -> float | None:
    if after is None or before is None:
        return None
    return round((after[1] - before[1]) * 100.0, 2)


def pct(after: tuple[dt.datetime, float] | None, before: tuple[dt.datetime, float] | None) -> float | None:
    if after is None or before is None or before[1] == 0:
        return None
    return round((after[1] / before[1] - 1.0) * 100.0, 3)


def classify_rates(ten: dict[str, Any], thirty: dict[str, Any], key: str) -> str:
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


def prior_daily_close(symbol: str, release_utc: dt.datetime) -> tuple[dt.datetime, float] | None:
    points = fetch_chart(symbol, release_utc - dt.timedelta(days=8), release_utc + dt.timedelta(days=1), interval="1d")
    event_date_et = release_utc.astimezone(NEW_YORK).date()
    eligible = [p for p in points if p[0].astimezone(NEW_YORK).date() < event_date_et]
    return eligible[-1] if eligible else None


def analyze_yield(symbol: str, release_utc: dt.datetime) -> dict[str, Any]:
    points = fetch_chart(symbol, release_utc - dt.timedelta(hours=2), release_utc + dt.timedelta(hours=3))
    pre = point_before(points, release_utc - dt.timedelta(seconds=1), max_age_min=15)
    at = point_nearest(points, release_utc, max_gap_min=3)
    p5 = point_nearest(points, release_utc + dt.timedelta(minutes=5), max_gap_min=8)
    p30 = point_nearest(points, release_utc + dt.timedelta(minutes=30), max_gap_min=8)
    return {
        "symbol": symbol,
        "pre": pack_yield_point(pre),
        "at_release": pack_yield_point(at),
        "plus_5m": pack_yield_point(p5),
        "plus_30m": pack_yield_point(p30),
        "change_at_bp": bp(at, pre),
        "change_5m_bp": bp(p5, pre),
        "change_30m_bp": bp(p30, pre),
    }


def analyze_oil(symbol: str, release_utc: dt.datetime) -> dict[str, Any]:
    points = fetch_chart(symbol, release_utc - dt.timedelta(hours=3), release_utc + dt.timedelta(hours=3))
    pre = point_before(points, release_utc - dt.timedelta(seconds=1), max_age_min=15)
    at = point_nearest(points, release_utc, max_gap_min=3)
    p5 = point_nearest(points, release_utc + dt.timedelta(minutes=5), max_gap_min=8)
    p30 = point_nearest(points, release_utc + dt.timedelta(minutes=30), max_gap_min=8)
    prev_close = prior_daily_close(symbol, release_utc)
    return {
        "symbol": symbol,
        "previous_close": pack_price_point(prev_close),
        "pre": pack_price_point(pre),
        "at_release": pack_price_point(at),
        "plus_5m": pack_price_point(p5),
        "plus_30m": pack_price_point(p30),
        "day_change_at_pct": pct(at, prev_close),
        "change_5m_pct": pct(p5, pre),
        "change_30m_pct": pct(p30, pre),
    }


def classify_oil(brent: dict[str, Any], wti: dict[str, Any]) -> str:
    vals = [brent.get("day_change_at_pct"), wti.get("day_change_at_pct")]
    if any(v is None for v in vals):
        return "유가 방향 확인 불가"
    a, b = float(vals[0]), float(vals[1])
    if a >= 2.0 and b >= 2.0:
        return "유가 급등 — 인플레이션·장기금리 상승 압력 강화"
    if a >= 0.5 and b >= 0.5:
        return "유가 상승 — 장기금리 상승 보조"
    if a <= -2.0 and b <= -2.0:
        return "유가 급락 — 인플레이션·장기금리 하락 압력 강화"
    if a <= -0.5 and b <= -0.5:
        return "유가 하락 — 장기금리 하락 보조"
    return "유가 혼합/보합 — 금리 방향 기여 제한적"


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
        "rate_intraday_source": "Cboe TNX/TYX via Yahoo Finance 1-minute chart data",
        "oil_intraday_source": "Brent BZ=F / WTI CL=F via Yahoo Finance 1-minute chart data",
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

    errors: list[str] = []
    try:
        ten = analyze_yield("^TNX", release_utc)
        thirty = analyze_yield("^TYX", release_utc)
        out["ten_year"] = ten
        out["thirty_year"] = thirty
        out["market_confirmation_at"] = classify_rates(ten, thirty, "change_at_bp")
        out["market_confirmation_5m"] = classify_rates(ten, thirty, "change_5m_bp")
        out["market_confirmation_30m"] = classify_rates(ten, thirty, "change_30m_bp")
    except Exception as exc:
        errors.append(f"rates: {type(exc).__name__}: {exc}")

    try:
        brent = analyze_oil("BZ=F", release_utc)
        wti = analyze_oil("CL=F", release_utc)
        out["brent"] = brent
        out["wti"] = wti
        out["oil_rate_signal"] = classify_oil(brent, wti)
    except Exception as exc:
        errors.append(f"oil: {type(exc).__name__}: {exc}")

    out["error"] = " | ".join(errors) if errors else None
    RESULT.write_text(json.dumps(out, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
