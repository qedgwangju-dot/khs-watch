#!/usr/bin/env python3
from __future__ import annotations

import datetime as dt
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
FARSIDE_BTC_ETF_URL = "https://farside.co.uk/bitcoin-etf-flow-all-data/"

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
    # Normalize line endings and surrounding whitespace so harmless transport changes do not alert.
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
        # Treasury daily par yield table ends with 10Y, 20Y, 30Y.
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
    return {
        "date": latest[0].isoformat(),
        "10y": latest[1],
        "30y": latest[2],
        "prev_date": prev[0].isoformat(),
        "prev_10y": prev[1],
        "prev_30y": prev[2],
        "daily_10y_bp": round((latest[1] - prev[1]) * 100, 1),
        "daily_30y_bp": round((latest[2] - prev[2]) * 100, 1),
    }


def btc_etf_flow() -> dict:
    html = fetch(FARSIDE_BTC_ETF_URL).decode("utf-8", errors="replace")
    soup = BeautifulSoup(html, "html.parser")
    rows: list[dict] = []
    for tr in soup.find_all("tr"):
        cells = [" ".join(td.get_text(" ", strip=True).split()) for td in tr.find_all(["td", "th"])]
        if len(cells) < 3:
            continue
        d = parse_date(cells[0])
        if not d:
            continue

        fund_cells = cells[1:-1]
        normalized = [x.strip() for x in fund_cells]
        numeric_funds = [parse_number(x) for x in normalized if x not in {"", "-", "—"}]
        reported_count = sum(v is not None for v in numeric_funds)
        missing_count = sum(x in {"", "-", "—"} for x in normalized)
        total = parse_number(cells[-1])

        # Farside creates the current trading-day row before issuer flow data is
        # available. In that state every fund column is "-" while Total is
        # mechanically displayed as 0.0. That is "not reported yet", not a
        # genuine zero-flow observation.
        if reported_count == 0 and missing_count == len(normalized):
            status = "pending"
            total = None
        elif missing_count > 0:
            status = "partial"
        else:
            status = "complete"

        rows.append({
            "date": d,
            "total": total,
            "status": status,
            "reported_funds": reported_count,
            "missing_funds": missing_count,
        })

    if not rows:
        raise RuntimeError("Farside BTC ETF flow rows could not be parsed")

    rows.sort(key=lambda x: x["date"])
    source_latest = rows[-1]
    valid_rows = [x for x in rows if x["total"] is not None and x["status"] != "pending"]
    if not valid_rows:
        raise RuntimeError("Farside has no reported BTC ETF flow rows")

    latest_valid = valid_rows[-1]
    complete_rows = [x for x in rows if x["total"] is not None and x["status"] == "complete"]
    last5 = complete_rows[-5:] if len(complete_rows) >= 5 else valid_rows[-5:]

    return {
        "date": latest_valid["date"].isoformat(),
        "total_usd_m": latest_valid["total"],
        "status": latest_valid["status"],
        "reported_funds": latest_valid["reported_funds"],
        "missing_funds": latest_valid["missing_funds"],
        "source_latest_date": source_latest["date"].isoformat(),
        "source_latest_status": source_latest["status"],
        "pending_date": source_latest["date"].isoformat() if source_latest["status"] == "pending" else None,
        "last5_usd_m": round(sum(x["total"] for x in last5), 1),
        "last5_dates": [x["date"].isoformat() for x in last5],
    }


def buyback_schedule() -> dict:
    xml = fetch(TREASURY_BUYBACK_XML)
    text = xml.decode("utf-8", errors="replace")
    # Keep only the long-duration buckets and dollar limits in a human-readable summary when possible.
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


def market_read(rates: dict, etf: dict) -> str:
    r10 = rates.get("daily_10y_bp", 0.0)
    r30 = rates.get("daily_30y_bp", 0.0)
    flow = etf.get("total_usd_m", 0.0)
    if r10 <= 0 and r30 <= 0 and flow > 0:
        return "위험자산에 우호적: 장기금리 하락 + BTC ETF 순유입"
    if r10 >= 0 and r30 >= 0 and flow < 0:
        return "위험자산에 불리: 장기금리 상승 + BTC ETF 순유출"
    return "혼조: 금리와 ETF 자금흐름이 같은 방향이 아님"


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
    except Exception as e:
        errors.append(f"btc_etf: {e}")
        etf = old.get("btc_etf") or {}

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
        },
        "errors": errors,
    }
    atomic_write(PENDING_STATE, json.dumps(new_state, ensure_ascii=False, indent=2) + "\n")

    # First successful run is a silent baseline; only subsequent changes alert.
    if not old:
        status = [
            "# 크립토 유동성 웹감시",
            "",
            "- 상태: 최초 기준값 저장 예정(텔레그램 미전송)",
            f"- 조회시각(KST): {now_kst}",
            f"- 미 국채 10Y/30Y: {rates.get('10y', 'N/A')}% / {rates.get('30y', 'N/A')}% ({rates.get('date', 'N/A')})",
            f"- BTC 현물 ETF: {signed_millions(etf.get('total_usd_m', 0.0)) if etf else 'N/A'} ({etf.get('date', 'N/A') if etf else 'N/A'})",
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
        # Avoid daily noise; alert only when either long yield moves at least 10 bp from the last stored official observation.
        if max(abs(d10), abs(d30)) >= 10.0:
            triggers.append(f"미 국채 장기금리 큰 변동: 10Y {d10:+.1f}bp / 30Y {d30:+.1f}bp")

    old_etf = old.get("btc_etf") or {}
    if etf and old_etf:
        # Do not alert merely because Farside has opened a new trading-day row
        # with all issuer cells still "-" and a synthetic Total=0.0.
        if etf.get("date") != old_etf.get("date"):
            qualifier = "잠정" if etf.get("status") == "partial" else "확정 집계"
            triggers.append(f"BTC 현물 ETF 새 일간 자금흐름({qualifier}): {signed_millions(etf.get('total_usd_m', 0.0))}")
        elif abs(etf.get("total_usd_m", 0.0) - old_etf.get("total_usd_m", etf.get("total_usd_m", 0.0))) >= 0.1:
            qualifier = "잠정" if etf.get("status") == "partial" else "집계"
            triggers.append(f"BTC 현물 ETF 당일 합계 수정({qualifier}): {signed_millions(etf.get('total_usd_m', 0.0))}")

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
                f"미 국채: 10Y {rates.get('10y', 0):.2f}% ({rates.get('daily_10y_bp', 0):+.1f}bp), 30Y {rates.get('30y', 0):.2f}% ({rates.get('daily_30y_bp', 0):+.1f}bp)",
            ]
        if etf:
            etf_status = "잠정 집계" if etf.get("status") == "partial" else "집계 완료"
            lines += [
                f"BTC 현물 ETF: {etf.get('date')} {signed_millions(etf.get('total_usd_m', 0.0))} ({etf_status}), 최근 5개 완료 거래일 합계 {signed_millions(etf.get('last5_usd_m', 0.0))}",
            ]
            if etf.get("pending_date"):
                lines += [f"※ {etf.get('pending_date')} Farside 행은 전 종목 미보고(-) 상태라 0.0을 실제 자금흐름으로 사용하지 않음"]
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
        f"- 오류: {'; '.join(errors) if errors else '없음'}",
    ]
    atomic_write(STATUS_PATH, "\n".join(status) + "\n")


if __name__ == "__main__":
    main()
