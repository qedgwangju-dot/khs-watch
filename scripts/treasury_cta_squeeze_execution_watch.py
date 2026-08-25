#!/usr/bin/env python3
"""Execution wrapper for CTA squeeze monitor using CME official Daily Bulletin.

The live CME XHR endpoints can reject automated requests. This wrapper replaces that
fragile leg with the official previous-trade-date Interest Rate Futures Daily Bulletin,
which publishes settlement, price change, volume, open interest and OI change.

User-facing legacy labels are mapped as:
- TY / ZN: 10-Year T-Note futures
- US / ZB: 30-Year Treasury Bond futures
- WN / UB: Ultra T-Bond futures
"""
from __future__ import annotations

import io
import re
import urllib.request

from pypdf import PdfReader

import treasury_cta_squeeze_watch as watcher

CME_BULLETIN = "https://www.cmegroup.com/daily_bulletin/current/Section09_Interest_Rate_Futures.pdf"

# Force one refreshed alert after switching the futures leg to the official bulletin.
watcher.FORMAT_REVISION = max(int(getattr(watcher, "FORMAT_REVISION", 0)), 2)

HEADINGS = {
    "ZN": ("TY/ZN", "10-YR NOTE FUTURES"),
    "ZB": ("US/ZB", "30Y BOND FUT"),
    "UB": ("WN/UB", "ULTRA T-BND FUT"),
}

MONTH_RE = re.compile(r"^(JAN|FEB|MAR|APR|MAY|JUN|JLY|AUG|SEP|OCT|NOV|DEC)\d{2}$")


def _download_pdf_text() -> str:
    req = urllib.request.Request(CME_BULLETIN, headers={"User-Agent": "Mozilla/5.0 khs-watch/cme-bulletin"})
    with urllib.request.urlopen(req, timeout=30) as r:
        data = r.read()
    reader = PdfReader(io.BytesIO(data))
    return "\n".join((p.extract_text() or "") for p in reader.pages)


def _parse_price(raw: str) -> float | None:
    s = str(raw or "").strip().replace("A", "").replace("B", "").replace("#", "").replace("*", "")
    if not s or s in ("-", "----"):
        return None
    sign = -1 if s.startswith("-") else 1
    s = s.lstrip("+-")
    if "'" not in s:
        try:
            return sign * float(s.replace(",", ""))
        except Exception:
            return None
    try:
        whole, frac = s.split("'", 1)
        digits = re.sub(r"\D", "", frac)
        if not digits:
            return sign * float(whole)
        thirtyseconds = int(digits[:2]) if len(digits) >= 2 else int(digits)
        extra = 0.0
        if len(digits) >= 3:
            # CBOT fractional convention: 0,2,5,7 represent 0,1/4,1/2,3/4 of 1/32.
            extra = {"0": 0.0, "2": 0.25, "5": 0.5, "7": 0.75}.get(digits[2], int(digits[2]) / 10)
        return sign * (float(whole) + (thirtyseconds + extra) / 32)
    except Exception:
        return None


def _as_int(token: str) -> int | None:
    token = str(token or "").replace(",", "").strip()
    if token in ("", "-", "----", "UNCH"):
        return None
    try:
        return int(token)
    except Exception:
        return None


def _section(text: str, heading: str) -> str:
    pos = text.find(heading)
    if pos < 0:
        return ""
    tail = text[pos + len(heading):]
    total_pos = tail.find("TOTAL " + heading)
    if total_pos >= 0:
        tail = tail[:total_pos]
    return tail


def _parse_row(line: str, symbol: str, label: str, trade_date: str) -> dict | None:
    tokens = line.split()
    if not tokens or not MONTH_RE.match(tokens[0]):
        return None
    # Expected columns: month open high low settle [sign] point-change RTH-volume Globex-volume OI [sign] OI-change ...
    if len(tokens) < 9:
        return None
    month = tokens[0]
    settle = _parse_price(tokens[4])
    if settle is None:
        return None
    idx = 5
    change_sign = 1
    if idx < len(tokens) and tokens[idx] in ("+", "-"):
        change_sign = -1 if tokens[idx] == "-" else 1
        idx += 1
    if idx >= len(tokens):
        return None
    change_abs = _parse_price(tokens[idx])
    change = change_sign * (change_abs or 0.0)
    idx += 1

    # The next three fields are RTH volume, Globex volume and open interest.
    numeric_fields = []
    while idx < len(tokens) and len(numeric_fields) < 3:
        tok = tokens[idx]
        if tok == "----" or re.fullmatch(r"[0-9,]+", tok):
            numeric_fields.append(tok)
        idx += 1
    if len(numeric_fields) < 3:
        return None
    rth = _as_int(numeric_fields[0]) or 0
    globex = _as_int(numeric_fields[1]) or 0
    oi = _as_int(numeric_fields[2]) or 0

    oi_change = None
    # Immediately after OI there is usually +/- N or UNCH.
    if idx < len(tokens):
        if tokens[idx] == "UNCH":
            oi_change = 0
        elif tokens[idx] in ("+", "-") and idx + 1 < len(tokens):
            val = _as_int(tokens[idx + 1])
            if val is not None:
                oi_change = val if tokens[idx] == "+" else -val
        elif re.fullmatch(r"[+-][0-9,]+", tokens[idx]):
            oi_change = _as_int(tokens[idx])

    prior = settle - change
    pct = change / prior * 100 if prior else None
    return {
        "symbol": symbol,
        "display_symbol": label,
        "month": month,
        "trade_date": trade_date,
        "last": settle,
        "settlement": settle,
        "change": change,
        "pct_change": pct,
        "open_interest": oi,
        "oi_change": oi_change,
        "volume": rth + globex,
        "source": CME_BULLETIN,
    }


def official_cme_snapshot() -> dict:
    text = _download_pdf_text()
    date_match = re.search(r"BULLETIN\s+#\s*\d+@\s*([^\n]+?)\s+PG09", text, re.I)
    trade_date = date_match.group(1).strip() if date_match else "확인 불가"
    out = {}
    for symbol, (label, heading) in HEADINGS.items():
        sec = _section(text, heading)
        rows = []
        for raw_line in sec.splitlines():
            row = _parse_row(raw_line.strip(), symbol, label, trade_date)
            if row:
                rows.append(row)
        # Use the most liquid/open-interest contract as active contract.
        out[symbol] = max(rows, key=lambda r: (r.get("open_interest") or 0, r.get("volume") or 0)) if rows else None
    return out


def official_squeeze_evidence(current: dict, previous: dict) -> list[str]:
    signals = []
    prev_cme = previous.get("cme", {}) if isinstance(previous, dict) else {}
    for symbol, row in (current.get("cme") or {}).items():
        if not row:
            continue
        prev = prev_cme.get(symbol) or {}
        # Alert only once per new bulletin date rather than every 15 minutes.
        if prev.get("trade_date") == row.get("trade_date"):
            continue
        chg = row.get("change")
        oi_chg = row.get("oi_change")
        label = row.get("display_symbol") or symbol
        if chg is not None and chg > 0 and oi_chg is not None and oi_chg < 0:
            signals.append(f"{label} 가격↑ + OI↓({oi_chg:+,}) = 공식 CME 일일 숏커버 확인 신호")
    return signals


_original_format_alert = watcher.format_alert


def format_alert_with_official_cme(snapshot, previous, fx, fx_date, reasons):
    title, body = _original_format_alert(snapshot, previous, fx, fx_date, reasons)
    cme = snapshot.get("cme") or {}
    lines = []
    for symbol in ("ZN", "ZB", "UB"):
        row = cme.get(symbol)
        if not row:
            continue
        label = row.get("display_symbol") or symbol
        pct = row.get("pct_change")
        pct_txt = f"{pct:+.3f}%" if pct is not None else "변화율 확인 불가"
        oi_chg = row.get("oi_change")
        oi_txt = f"{oi_chg:+,}" if oi_chg is not None else "확인 불가"
        lines.append(
            f"• {label} {row.get('month','')}: CME 공식 정산 {row.get('settlement',0):.5f} ({pct_txt}) · "
            f"OI {row.get('open_interest',0):,} (일변화 {oi_txt})"
        )
    if lines:
        start = "<b>3️⃣ TY/US/WN 대응 CME 선물 — 가격 + 미결제약정</b>"
        end = "<b>4️⃣ 1σ·2σ 추세 전환 프록시</b>"
        if start in body and end in body:
            pre, rest = body.split(start, 1)
            _, post = rest.split(end, 1)
            evidence = official_squeeze_evidence(snapshot, previous)
            block = [start,
                     "※ 공식 CME Daily Bulletin 기준: TY=ZN(10년), US=ZB(30년), WN=UB(Ultra Bond)",
                     *lines,
                     *([f"• ✅ {x}" for x in evidence] if evidence else ["• 아직 가격↑ + OI↓ 동시 신호 미확인 → 기계적 숏커버 확정 전"]),
                     "",
                     end]
            body = pre + "\n".join(block) + post
    body = body.replace(
        f'<a href="{watcher.CME_PAGES["ZN"]}">CME ZN</a> · <a href="{watcher.CME_PAGES["ZB"]}">CME ZB</a> · <a href="{watcher.CME_PAGES["UB"]}">CME UB</a>',
        f'<a href="{CME_BULLETIN}">CME 공식 일일 선물 정산·OI</a>'
    )
    return title, body


watcher.cme_snapshot = official_cme_snapshot
watcher.squeeze_evidence = official_squeeze_evidence
watcher.format_alert = format_alert_with_official_cme

if __name__ == "__main__":
    raise SystemExit(watcher.main())
