#!/usr/bin/env python3
"""Resilient market-data wrapper for Treasury CTA squeeze monitor.

CME's public website can return HTTP 403 to cloud runners. The preferred official
CME Daily Bulletin wrapper is tried first. If CME blocks the runner, use Yahoo Finance's
CBOT delayed quote layer for ZN/ZB/UB price and open interest, and label it explicitly
as a secondary/delayed feed. CFTC remains the official positioning source.
"""
from __future__ import annotations

import json
import re
import time
import urllib.parse
import urllib.request

import treasury_cta_squeeze_watch as watcher
import treasury_cta_squeeze_execution_watch as official

watcher.FORMAT_REVISION = max(int(getattr(watcher, "FORMAT_REVISION", 0)), 3)

YAHOO_QUOTE = "https://query1.finance.yahoo.com/v7/finance/quote?symbols="
YAHOO_CHART = "https://query1.finance.yahoo.com/v8/finance/chart/{ticker}?range=5d&interval=1d&includePrePost=false"
YAHOO_PAGE = "https://finance.yahoo.com/quote/{ticker}/"
TICKERS = {"ZN": "ZN=F", "ZB": "ZB=F", "UB": "UB=F"}
LABELS = {"ZN": "TY/ZN", "ZB": "US/ZB", "UB": "WN/UB"}


def _get(url: str) -> str:
    req = urllib.request.Request(url, headers={
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/151 Safari/537.36",
        "Accept": "application/json,text/html,*/*",
        "Accept-Language": "en-US,en;q=0.9",
    })
    with urllib.request.urlopen(req, timeout=25) as r:
        return r.read().decode("utf-8", errors="replace")


def _quote_batch() -> dict:
    url = YAHOO_QUOTE + urllib.parse.quote(",".join(TICKERS.values()), safe="=,")
    try:
        data = json.loads(_get(url))
        rows = ((data.get("quoteResponse") or {}).get("result") or []) if isinstance(data, dict) else []
        return {str(row.get("symbol")): row for row in rows if isinstance(row, dict)}
    except Exception:
        return {}


def _chart(ticker: str) -> dict | None:
    try:
        data = json.loads(_get(YAHOO_CHART.format(ticker=urllib.parse.quote(ticker, safe="="))))
        result = (((data.get("chart") or {}).get("result") or [None])[0])
        if not isinstance(result, dict):
            return None
        meta = result.get("meta") or {}
        ts = result.get("timestamp") or []
        quote = (((result.get("indicators") or {}).get("quote") or [{}])[0])
        closes = quote.get("close") or []
        valid = [(t, c) for t, c in zip(ts, closes) if c is not None]
        if not valid:
            return None
        last_ts, last = valid[-1]
        prev = valid[-2][1] if len(valid) >= 2 else meta.get("chartPreviousClose") or meta.get("previousClose")
        return {"last": float(last), "prev": float(prev) if prev else None, "timestamp": int(last_ts), "meta": meta}
    except Exception:
        return None


def _page_open_interest(ticker: str) -> int | None:
    try:
        page = _get(YAHOO_PAGE.format(ticker=urllib.parse.quote(ticker, safe="")))
    except Exception:
        return None
    patterns = [
        r'"openInterest"\s*:\s*\{\s*"raw"\s*:\s*([0-9]+)',
        r'"openInterest"\s*:\s*([0-9]+)',
        r'Open Interest[^0-9]{0,80}([0-9][0-9,.]*[KMB]?)',
    ]
    for pat in patterns:
        m = re.search(pat, page, re.I | re.S)
        if not m:
            continue
        raw = m.group(1).replace(",", "")
        mult = 1
        if raw.endswith("K"):
            mult, raw = 1_000, raw[:-1]
        elif raw.endswith("M"):
            mult, raw = 1_000_000, raw[:-1]
        elif raw.endswith("B"):
            mult, raw = 1_000_000_000, raw[:-1]
        try:
            return int(float(raw) * mult)
        except Exception:
            continue
    return None


def yahoo_snapshot() -> dict:
    batch = _quote_batch()
    out = {}
    for symbol, ticker in TICKERS.items():
        row = batch.get(ticker) or {}
        chart = _chart(ticker)
        last = row.get("regularMarketPrice")
        previous = row.get("regularMarketPreviousClose")
        change = row.get("regularMarketChange")
        pct = row.get("regularMarketChangePercent")
        oi = row.get("openInterest")
        volume = row.get("regularMarketVolume")
        market_time = row.get("regularMarketTime")
        if chart:
            if last is None:
                last = chart.get("last")
            if previous is None:
                previous = chart.get("prev")
            if market_time is None:
                market_time = chart.get("timestamp")
        try:
            last = float(last) if last is not None else None
        except Exception:
            last = None
        try:
            previous = float(previous) if previous is not None else None
        except Exception:
            previous = None
        if change is None and last is not None and previous is not None:
            change = last - previous
        try:
            change = float(change) if change is not None else None
        except Exception:
            change = None
        if pct is None and last is not None and previous:
            pct = (last / previous - 1) * 100
        try:
            pct = float(pct) if pct is not None else None
        except Exception:
            pct = None
        try:
            oi = int(oi) if oi is not None else None
        except Exception:
            oi = None
        if oi is None:
            oi = _page_open_interest(ticker)
        try:
            volume = int(volume) if volume is not None else 0
        except Exception:
            volume = 0
        out[symbol] = {
            "symbol": symbol,
            "display_symbol": LABELS[symbol],
            "ticker": ticker,
            "month": row.get("shortName") or row.get("longName") or "",
            "last": last,
            "settlement": last,
            "change": change,
            "pct_change": pct,
            "open_interest": oi or 0,
            "volume": volume,
            "market_time": market_time,
            "source": f"https://finance.yahoo.com/quote/{urllib.parse.quote(ticker, safe='')}/",
            "source_type": "Yahoo Finance 지연 데이터 (CBOT/CME 파생상품 2차 배포)",
        } if last is not None else None
    return out


def resilient_snapshot() -> dict:
    try:
        official_data = official.official_cme_snapshot()
        if any(official_data.values()):
            return official_data
    except Exception:
        pass
    return yahoo_snapshot()


def squeeze_evidence(current: dict, previous: dict) -> list[str]:
    signals = []
    prev_cme = previous.get("cme", {}) if isinstance(previous, dict) else {}
    for symbol, row in (current.get("cme") or {}).items():
        if not row:
            continue
        prev = prev_cme.get(symbol) or {}
        pct = row.get("pct_change")
        oi = row.get("open_interest")
        prev_oi = prev.get("open_interest")
        label = row.get("display_symbol") or symbol
        if pct is not None and pct > 0 and oi and prev_oi and oi < prev_oi:
            signals.append(f"{label} 가격↑({pct:+.2f}%) + OI↓({prev_oi:,}→{oi:,}) = 숏커버 확인 신호")
    return signals


_base_format = watcher.format_alert


def format_alert(snapshot, previous, fx, fx_date, reasons):
    title, body = _base_format(snapshot, previous, fx, fx_date, reasons)
    rows = snapshot.get("cme") or {}
    block_lines = []
    source_is_official = True
    for symbol in ("ZN", "ZB", "UB"):
        row = rows.get(symbol)
        if not row:
            block_lines.append(f"• {LABELS[symbol]}: 가격/OI 확인 불가")
            continue
        if "Yahoo" in str(row.get("source_type") or ""):
            source_is_official = False
        pct = row.get("pct_change")
        pct_text = f"{pct:+.2f}%" if pct is not None else "변화율 확인 불가"
        oi = row.get("open_interest") or 0
        block_lines.append(f"• {LABELS[symbol]}: 가격 {row.get('last'):.5f} ({pct_text}) · OI {oi:,}")
    evidence = squeeze_evidence(snapshot, previous)
    source_note = (
        "※ CME 공식 Daily Bulletin 기준"
        if source_is_official else
        "※ CME 클라우드 접근 차단 시 Yahoo Finance 지연 CBOT 데이터 사용. CFTC 공식 포지션으로 반드시 교차검증"
    )
    start = "<b>3️⃣ TY/US/WN 대응 CME 선물 — 가격 + 미결제약정</b>"
    end = "<b>4️⃣ 1σ·2σ 추세 전환 프록시</b>"
    if start in body and end in body:
        pre, rest = body.split(start, 1)
        _, post = rest.split(end, 1)
        block = [start, source_note, *block_lines,
                 *([f"• ✅ {x}" for x in evidence] if evidence else ["• 아직 가격↑ + OI↓ 동시 신호 미확인 → 기계적 숏커버 확정 전"]),
                 "", end]
        body = pre + "\n".join(block) + post
    return title, body


watcher.cme_snapshot = resilient_snapshot
watcher.squeeze_evidence = squeeze_evidence
watcher.format_alert = format_alert

if __name__ == "__main__":
    raise SystemExit(watcher.main())
