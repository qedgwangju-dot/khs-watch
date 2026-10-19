#!/usr/bin/env python3
"""Weekly US equity/10Y Treasury risk-regime check; no Telegram side effects.

Nasdaq-100 source: Nasdaq official historical daily index close API.
10-year yield: U.S. Treasury official daily par yield.
Compare previous Friday with the current completed Friday, never mixed dates.
"""
from __future__ import annotations

import csv
import datetime as dt
import io
import html
import json
import math
from urllib.parse import urlparse
from zoneinfo import ZoneInfo

import requests

from treasury_real_yield_signal import parse_feed

NASDAQ_API = "https://api.nasdaq.com/api/quote/NDX/historical"
NASDAQ_SERIES = "NASDAQ100"
TREASURY_XML = "https://home.treasury.gov/resource-center/data-chart-center/interest-rates/pages/xml"
HEADERS = {"User-Agent": "Mozilla/5.0 (compatible; khs-watch-treasury-weekly/1.0)"}


class SourceMissing(ValueError):
    pass


def completed_friday(now: dt.datetime) -> dt.date:
    now_us = now.astimezone(ZoneInfo("America/New_York"))
    candidate = now_us.date()
    days_back = (candidate.weekday() - 4) % 7
    if days_back == 0 and now_us.time() < dt.time(16, 10):
        days_back = 7
    return candidate - dt.timedelta(days=days_back)


def parse_nasdaq_csv(content: str) -> dict[str, float]:
    if content.lstrip().startswith("<"):
        raise SourceMissing("FRED returned HTML instead of Nasdaq index CSV")
    reader = csv.DictReader(io.StringIO(content))
    columns = set(reader.fieldnames or [])
    date_field = "observation_date" if "observation_date" in columns else "DATE"
    if date_field not in columns or NASDAQ_SERIES not in columns:
        raise SourceMissing("Nasdaq daily CSV headings missing")
    rows = {}
    for row in reader:
        date_text = (row.get(date_field) or "").strip()
        value_text = (row.get(NASDAQ_SERIES) or "").strip()
        if not date_text or value_text in ("", "."):
            continue
        try:
            dt.date.fromisoformat(date_text)
            value = float(value_text.replace(",", ""))
        except (ValueError, TypeError):
            continue
        if not math.isfinite(value) or value <= 0:
            raise SourceMissing("invalid Nasdaq index level")
        if date_text in rows and abs(rows[date_text] - value) > 0.001:
            raise SourceMissing("conflicting Nasdaq daily close for " + date_text)
        rows[date_text] = value
    if not rows:
        raise SourceMissing("no usable Nasdaq-100 daily closings")
    return rows


def parse_nasdaq_api(payload: dict) -> dict[str, float]:
    status = payload.get("status") or {}
    if status.get("rCode") not in (200, "200"):
        raise SourceMissing("official Nasdaq history API returned a non-success status")
    data = payload.get("data") or {}
    table = data.get("tradesTable") or {}
    rows = table.get("rows") or []
    if str(data.get("symbol") or "").upper() != "NDX" or not rows:
        raise SourceMissing("Nasdaq official NDX historical rows unavailable")
    parsed = {}
    for row in rows:
        try:
            date_key = dt.datetime.strptime((row.get("date") or "").strip(), "%m/%d/%Y").date().isoformat()
            close = float(str(row.get("close") or "").replace(",", "").replace("$", ""))
        except (ValueError, TypeError, AttributeError):
            raise SourceMissing("Nasdaq official date or closing value malformed")
        if not math.isfinite(close) or close <= 0:
            raise SourceMissing("invalid Nasdaq closing index")
        if date_key in parsed and abs(parsed[date_key]-close) > 0.001:
            raise SourceMissing("conflicting official Nasdaq index close")
        parsed[date_key]=close
    return parsed


def evaluate_week(nasdaq: dict, treasury: dict, end: dt.date) -> dict:
    if end.weekday() != 4:
        raise SourceMissing("weekly signal must use Friday's closing session")
    start = end - dt.timedelta(days=7)
    s, e = start.isoformat(), end.isoformat()
    for series_name, series in (("Nasdaq-100", nasdaq), ("10Y Treasury", treasury)):
        if s not in series or e not in series:
            raise SourceMissing(
                f"{series_name}: exact Friday close missing (expected {s}/{e}, "
                f"available latest {max(series, default='none')}); no substitute dates"
            )
    n0, n1 = nasdaq[s], nasdaq[e]
    y0, y1 = treasury[s], treasury[e]
    stock_change = (n1/n0 - 1) * 100
    yield_change_bp = (y1-y0) * 100
    if stock_change <= -5 and yield_change_bp <= -10:
        category = "안전자산 방어 신호"
        comment = "나스닥100 급락과 미국 10년물 금리 하락이 동반됨. 국채의 방어 역할이 나타난 주간"
    elif stock_change <= -5 and yield_change_bp >= 10:
        category = "주식·국채 동반 약세 경보"
        comment = "기술주 급락과 장기 국채금리 상승이 동반됨. 전통적 국채 헤지가 작동하지 않은 주간"
    elif stock_change <= -5:
        category = "기술주 급락·국채 완충 불충분"
        comment = "나스닥100은 급락했지만 장기 국채금리가 뚜렷이 하락하지 않아 방어 신호가 불충분"
    else:
        category = "주간 급락 조건 미충족"
        comment = "나스닥100 주간 -5% 임계치에 도달하지 않아 별도 경보 대상 아님"
    return dict(
        start=s, end=e, ndx_start=n0, ndx_end=n1,
        ndx_week_pct=round(stock_change, 4),
        y10_start=y0, y10_end=y1, y10_week_bp=round(yield_change_bp, 3),
        category=category, comment=comment,
        alert=category != "주간 급락 조건 미충족",
        reference_note="종가 대 종가 비교. 기사 시장호가 수익률 변화와 차이가 날 수 있음",
    )


def fetch_current_week(now: dt.datetime | None = None, client=requests) -> dict:
    now = now or dt.datetime.now(dt.timezone.utc)
    end = completed_friday(now)
    start = end - dt.timedelta(days=7)
    params = {
        "assetclass": "index",
        "limit": 60,
        "fromdate": (start - dt.timedelta(days=3)).isoformat(),
        "todate": end.isoformat(),
    }
    response = client.get(
        NASDAQ_API, params=params,
        headers={**HEADERS, "Accept": "application/json", "Origin": "https://www.nasdaq.com"},
        timeout=(7, 14),
    )
    response.raise_for_status()
    try:
        nasdaq = parse_nasdaq_api(response.json())
    except (ValueError, TypeError, KeyError) as exc:
        raise SourceMissing(f"Nasdaq official JSON unusable: {type(exc).__name__}") from exc
    treasury_url = f"{TREASURY_XML}?data=daily_treasury_yield_curve&field_tdr_date_value={end.year}"
    reply = client.get(treasury_url, headers=HEADERS, timeout=(7, 20))
    reply.raise_for_status()
    treasury = parse_feed(reply.content, "BC_10YEAR")
    result = evaluate_week(nasdaq, treasury, end)
    result["source_urls"] = [
        "https://indexes.nasdaq.com/Index/History/NDX",
        "https://api.nasdaq.com/api/quote/NDX/historical?assetclass=index",
        treasury_url,
    ]
    return result



SOURCE_LABELS = (
    ("indexes.nasdaq.com", "나스닥100 지수 이력"),
    ("api.nasdaq.com", "나스닥 공식 종가"),
    ("home.treasury.gov", "미 재무부 10년물 금리"),
)


def _source_links(result: dict) -> str:
    """Three named and validated HTTPS text links, never raw pasted URLs."""
    urls = result.get("source_urls") or []
    if len(urls) != len(SOURCE_LABELS):
        raise SourceMissing("required Nasdaq/Treasury source links missing")
    elements = []
    for url, (host, label) in zip(urls, SOURCE_LABELS):
        parsed = urlparse(str(url))
        if (
            parsed.scheme != "https" or parsed.hostname != host
            or parsed.username or parsed.password or parsed.fragment
        ):
            raise SourceMissing("unrecognized source URL for " + label)
        safe_url = html.escape(str(url), quote=True)
        elements.append(f'<a href="{safe_url}">{html.escape(label)}</a>')
    return " · ".join(elements)


def _period_line(result: dict) -> str:
    return f"기준: {result['start']} → {result['end']} (미국 현지 주간 마감)"


def _stock_line(result: dict) -> str:
    return (
        f"나스닥100: {result['ndx_start']:,.2f} → "
        f"{result['ndx_end']:,.2f} ({result['ndx_week_pct']:+.2f}%)"
    )


def _bond_line(result: dict) -> str:
    return (
        f"미 10년물 금리: {result['y10_start']:.2f}% → "
        f"{result['y10_end']:.2f}% ({result['y10_week_bp']:+.0f}bp)"
    )


def _threshold_explanation(result: dict) -> str:
    if result["category"] == "안전자산 방어 신호":
        return "나스닥100 주간 -5% 이하 + 10년물 금리 -10bp 이하"
    if result["category"] == "주식·국채 동반 약세 경보":
        return "나스닥100 주간 -5% 이하 + 10년물 금리 +10bp 이상"
    if result["category"] == "기술주 급락·국채 완충 불충분":
        return "나스닥100 주간 -5% 이하, 10년물 금리 -10bp 하락은 미충족"
    if result["category"] == "주간 급락 조건 미충족":
        return "나스닥100 주간 -5% 급락 조건 미충족"
    raise ValueError("unexpected weekly risk regime category")


def _note_lines() -> tuple[str, ...]:
    return (
        "CTA 숏커버링: CFTC 포지션·CME 미결제약정 확인 전 미확정.",
        "해당 주간 금리와 주가 움직임이며 이후 국채 수익·헤지 성과를 보장하지 않음.",
        "같은 날짜의 나스닥 종가와 미 재무부 공식 일일 수익률로 비교. 자료 불일치 시 경보 보류.",
    )


def report_text(result: dict) -> str:
    """Clean plain-text audit copy; source destinations are preserved separately."""
    rows = [
        "미 증시 급락·국채 헤지 기능 | 주간 경보",
        f"판정: {result['category']}",
        _period_line(result),
        "",
        "핵심 숫자",
        _stock_line(result),
        _bond_line(result),
        "",
        "무슨 뜻인가",
        result["comment"],
        "",
        f"경보 조건: {_threshold_explanation(result)}",
        "",
        "확인할 점",
        *_note_lines(),
        "",
        "공식 출처: 나스닥100 지수 이력 · 나스닥 공식 종가 · 미 재무부 10년물 금리",
    ]
    return "\n".join(rows)


def report_html(result: dict) -> str:
    """Telegram HTML: native bold section labels and tappable source text-links."""
    esc = html.escape
    source_links = _source_links(result)
    paragraphs = [
        "<b>미 증시 급락·국채 헤지 기능 | 주간 경보</b>",
        f"<b>판정: {esc(result['category'])}</b>",
        esc(_period_line(result)),
        "",
        "<b>핵심 숫자</b>",
        esc(_stock_line(result)),
        esc(_bond_line(result)),
        "",
        "<b>무슨 뜻인가</b>",
        esc(result["comment"]),
        "",
        f"<b>경보 조건:</b> {esc(_threshold_explanation(result))}",
        "",
        "<b>확인할 점</b>",
        *(esc(note) for note in _note_lines()),
        "",
        "<b>공식 출처</b>",
        source_links,
    ]
    output = "\n".join(paragraphs)
    # Telegram measures decoded visible text; also bound the raw payload.
    if len(output) > 3900 or len(report_text(result)) > 3800:
        raise ValueError("Telegram weekly report exceeds size budget")
    return output
