#!/usr/bin/env python3
from __future__ import annotations

import datetime as dt
import json
import pathlib
import re
import urllib.parse
import urllib.request
from urllib.parse import urljoin
from zoneinfo import ZoneInfo

from bs4 import BeautifulSoup

ROOT = pathlib.Path(__file__).resolve().parents[1]
ALERT_PATH = ROOT / "out" / "crypto_liquidity_watch_telegram.txt"
STATE_PATH = ROOT / "out" / "crypto_liquidity_watch_pending_state.json"

BOK_MARKET_LIST = "https://www.bok.or.kr/portal/main/contents.do?menuNo=200366"
YAHOO_CHART = "https://query1.finance.yahoo.com/v8/finance/chart/KRW=X"
UA = "Mozilla/5.0 (compatible; khs-watch/1.0; +https://github.com/qedgwangju-dot/khs-watch)"
KST = ZoneInfo("Asia/Seoul")


def fetch(url: str, timeout: int = 30) -> bytes:
    req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept": "*/*"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.read()


def parse_target_date() -> dt.date:
    state = json.loads(STATE_PATH.read_text(encoding="utf-8"))
    value = ((state.get("btc_etf") or {}).get("date") or "").strip()
    if not value:
        raise RuntimeError("BTC ETF 기준일을 확인할 수 없음")
    return dt.date.fromisoformat(value)


def parse_reference_date(text: str, post_year: int) -> dt.date | None:
    patterns = [
        r"수익률\s*\(\s*(\d{1,2})\.(\d{1,2})\s*,?\s*이하 같음",
        r"\(\s*(\d{1,2})\.(\d{1,2})\s*,?\s*이하 같음",
    ]
    for pattern in patterns:
        m = re.search(pattern, text)
        if not m:
            continue
        month, day = int(m.group(1)), int(m.group(2))
        year = post_year
        today = dt.date(post_year, 12, 31)
        candidate = dt.date(year, month, day)
        if month == 12 and dt.datetime.now(KST).month == 1:
            candidate = dt.date(year - 1, month, day)
        return candidate
    return None


def extract_bok_rate_from_page(url: str, target: dt.date) -> tuple[float, str] | None:
    html = fetch(url).decode("utf-8", errors="replace")
    soup = BeautifulSoup(html, "html.parser")
    text = " ".join(soup.get_text(" ", strip=True).split())

    post_date_match = re.search(r"등록일\s*(20\d{2})\.(\d{2})\.(\d{2})", text)
    post_year = int(post_date_match.group(1)) if post_date_match else target.year
    reference_date = parse_reference_date(text, post_year)
    if reference_date != target:
        return None

    m = re.search(
        r"원\s*/\s*달러\s*환율.*?\(([\d,]+(?:\.\d+)?)원?\s*(?:→|->)\s*([\d,]+(?:\.\d+)?)원?\)",
        text,
    )
    if not m:
        return None
    rate = float(m.group(2).replace(",", ""))
    if not (800.0 <= rate <= 2500.0):
        return None
    return rate, url


def bok_usdkrw(target: dt.date) -> tuple[float, str] | None:
    html = fetch(BOK_MARKET_LIST).decode("utf-8", errors="replace")
    soup = BeautifulSoup(html, "html.parser")
    candidates: list[str] = []
    for a in soup.find_all("a", href=True):
        text = " ".join(a.get_text(" ", strip=True).split())
        href = a.get("href") or ""
        if "금융시장 주요지표" not in text:
            continue
        if "P0002018" not in href and "view.do" not in href:
            continue
        url = urljoin(BOK_MARKET_LIST, href)
        if url not in candidates:
            candidates.append(url)

    for url in candidates[:20]:
        try:
            result = extract_bok_rate_from_page(url, target)
        except Exception:
            continue
        if result:
            return result
    return None


def yahoo_usdkrw(target: dt.date) -> tuple[float, str] | None:
    start = dt.datetime.combine(target - dt.timedelta(days=3), dt.time.min, tzinfo=dt.timezone.utc)
    end = dt.datetime.combine(target + dt.timedelta(days=4), dt.time.min, tzinfo=dt.timezone.utc)
    params = urllib.parse.urlencode({
        "period1": int(start.timestamp()),
        "period2": int(end.timestamp()),
        "interval": "1d",
        "events": "history",
        "includeAdjustedClose": "true",
    })
    url = f"{YAHOO_CHART}?{params}"
    data = json.loads(fetch(url).decode("utf-8"))
    result = (((data.get("chart") or {}).get("result") or [None])[0])
    if not result:
        return None
    timestamps = result.get("timestamp") or []
    closes = (((result.get("indicators") or {}).get("quote") or [{}])[0]).get("close") or []
    for ts, close in zip(timestamps, closes):
        if close is None:
            continue
        d = dt.datetime.fromtimestamp(ts, tz=dt.timezone.utc).date()
        if d == target:
            rate = float(close)
            if 800.0 <= rate <= 2500.0:
                return rate, "https://finance.yahoo.com/quote/KRW=X/"
    return None


def get_usdkrw(target: dt.date) -> dict:
    bok = None
    yahoo = None
    try:
        bok = bok_usdkrw(target)
    except Exception:
        bok = None
    try:
        yahoo = yahoo_usdkrw(target)
    except Exception:
        yahoo = None

    if bok and yahoo:
        gap_pct = abs(bok[0] - yahoo[0]) / bok[0] * 100
        if gap_pct > 1.0:
            raise RuntimeError(
                f"USD/KRW 교차검증 불일치: 한국은행 {bok[0]:,.2f}원 vs Yahoo {yahoo[0]:,.2f}원 ({gap_pct:.2f}%)"
            )
        return {
            "rate": bok[0],
            "date": target.isoformat(),
            "source": "한국은행 일일 금융시장 주요지표",
            "source_url": bok[1],
            "crosscheck": f"Yahoo Finance {yahoo[0]:,.2f}원, 차이 {gap_pct:.2f}%",
        }
    if bok:
        return {
            "rate": bok[0],
            "date": target.isoformat(),
            "source": "한국은행 일일 금융시장 주요지표",
            "source_url": bok[1],
            "crosscheck": "Yahoo Finance 교차검증 접근 불가",
        }
    if yahoo:
        return {
            "rate": yahoo[0],
            "date": target.isoformat(),
            "source": "Yahoo Finance USD/KRW 일일 종가(한국은행 원문 자동조회 실패 시 보조값)",
            "source_url": yahoo[1],
            "crosscheck": "한국은행 원문 자동조회 실패",
        }
    raise RuntimeError("USD/KRW 환율을 확인하지 못해 원화 환산을 중단함")


def format_krw_from_usd_m(value_usd_m: float, rate: float) -> str:
    eok = value_usd_m * rate / 100.0
    sign = "-" if eok < 0 else "+" if eok > 0 else ""
    amount = abs(eok)
    rounded = int(round(amount))
    jo, rem = divmod(rounded, 10000)
    if jo:
        body = f"{jo}조{rem:,}억원" if rem else f"{jo}조원"
    else:
        body = f"{rounded:,}억원"
    return f"약 {sign}{body}"


def enrich_text(text: str, fx: dict) -> str:
    rate = float(fx["rate"])
    pattern = re.compile(r"(?P<amount>[+-]?\d[\d,]*(?:\.\d+)?)백만달러(?!\s*\(약)")

    def repl(m: re.Match[str]) -> str:
        raw = m.group("amount")
        value = float(raw.replace(",", ""))
        return f"{raw}백만달러 ({format_krw_from_usd_m(value, rate)})"

    enriched = pattern.sub(repl, text)
    now = dt.datetime.now(KST).isoformat(timespec="seconds")
    fx_line = (
        f"원화 환산 기준: 1달러={rate:,.2f}원 | 기준일 {fx['date']} | {fx['source']} | "
        f"교차검증: {fx['crosscheck']} | 조회 {now}"
    )
    source_line = f'• 원/달러 환율: <a href="{fx["source_url"]}">원문</a>'

    marker = "\n공식·데이터 원천:\n"
    if marker in enriched:
        enriched = enriched.replace(marker, f"\n{fx_line}\n\n공식·데이터 원천:\n{source_line}\n", 1)
    else:
        enriched = enriched.rstrip() + f"\n\n{fx_line}\n{source_line}\n"
    return enriched


def main() -> None:
    if not ALERT_PATH.exists():
        return
    if not STATE_PATH.exists():
        raise RuntimeError("pending state 파일이 없어 원화 환산 기준일을 확정할 수 없음")
    target = parse_target_date()
    fx = get_usdkrw(target)
    text = ALERT_PATH.read_text(encoding="utf-8")
    enriched = enrich_text(text, fx)
    ALERT_PATH.write_text(enriched, encoding="utf-8")
    print(json.dumps(fx, ensure_ascii=False))


if __name__ == "__main__":
    main()
