#!/usr/bin/env python3
from __future__ import annotations

import datetime as dt
import json
import os
import pathlib
import re
import urllib.parse
import urllib.request
from urllib.parse import quote, urljoin
from zoneinfo import ZoneInfo

from bs4 import BeautifulSoup

ROOT = pathlib.Path(__file__).resolve().parents[1]
ALERT_PATH = ROOT / "out" / "crypto_liquidity_watch_telegram.txt"
STATE_PATH = ROOT / "out" / "crypto_liquidity_watch_pending_state.json"

ECOS_BASE = "https://ecos.bok.or.kr/api/StatisticSearch"
ECOS_HOME = "https://ecos.bok.or.kr/"
ECOS_STAT_CODE = "731Y001"
ECOS_ITEM_CODE = "0000001"
ECOS_CYCLE = "D"
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


def ecos_usdkrw(target: dt.date) -> dict | None:
    """Fetch official BOK ECOS USD/KRW daily reference rate.

    731Y001 / 0000001 = 주요국 통화의 대원화환율 / 원·미국달러(매매기준율).
    If target is not a Korean business day, use the most recent ECOS observation
    not later than target and expose the actual ECOS date explicitly.
    """
    api_key = (os.getenv("BOK_ECOS_API_KEY") or "").strip()
    if not api_key:
        return None

    start = target - dt.timedelta(days=7)
    key_segment = quote(api_key, safe="")
    url = (
        f"{ECOS_BASE}/{key_segment}/json/kr/1/20/"
        f"{ECOS_STAT_CODE}/{ECOS_CYCLE}/{start:%Y%m%d}/{target:%Y%m%d}/{ECOS_ITEM_CODE}"
    )

    try:
        payload = json.loads(fetch(url).decode("utf-8"))
    except Exception:
        return None

    block = payload.get("StatisticSearch") or {}
    rows = block.get("row") or []
    if not rows:
        return None

    valid: list[tuple[dt.date, float]] = []
    for row in rows:
        try:
            if str(row.get("STAT_CODE") or "") != ECOS_STAT_CODE:
                continue
            if str(row.get("ITEM_CODE1") or "") != ECOS_ITEM_CODE:
                continue
            item_name = str(row.get("ITEM_NAME1") or "")
            unit_name = str(row.get("UNIT_NAME") or "")
            if "미국달러" not in item_name:
                continue
            if unit_name and "원" not in unit_name:
                continue
            obs_date = dt.datetime.strptime(str(row.get("TIME") or ""), "%Y%m%d").date()
            if obs_date > target:
                continue
            rate = float(str(row.get("DATA_VALUE") or "").replace(",", ""))
            if not 800.0 <= rate <= 2500.0:
                continue
            valid.append((obs_date, rate))
        except Exception:
            continue

    if not valid:
        return None

    obs_date, rate = sorted(valid, key=lambda x: x[0])[-1]
    return {
        "rate": rate,
        "date": obs_date.isoformat(),
        "requested_date": target.isoformat(),
        "source": "한국은행 ECOS 원/미국달러(매매기준율)",
        "source_url": ECOS_HOME,
        "official": True,
    }


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
        candidate = dt.date(post_year, month, day)
        if month == 12 and dt.datetime.now(KST).month == 1:
            candidate = dt.date(post_year - 1, month, day)
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
    if not 800.0 <= rate <= 2500.0:
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
        page_url = urljoin(BOK_MARKET_LIST, href)
        if page_url not in candidates:
            candidates.append(page_url)

    for page_url in candidates[:20]:
        try:
            result = extract_bok_rate_from_page(page_url, target)
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
    ecos = ecos_usdkrw(target)
    if ecos:
        obs_date = dt.date.fromisoformat(ecos["date"])
        yahoo = None
        try:
            yahoo = yahoo_usdkrw(obs_date)
        except Exception:
            yahoo = None
        if yahoo:
            gap_pct = abs(ecos["rate"] - yahoo[0]) / ecos["rate"] * 100
            if gap_pct <= 1.0:
                crosscheck = f"Yahoo Finance {yahoo[0]:,.2f}원, 차이 {gap_pct:.2f}%"
            else:
                crosscheck = f"Yahoo Finance {yahoo[0]:,.2f}원, 차이 {gap_pct:.2f}% · 기준 차이 주의"
        else:
            crosscheck = "Yahoo Finance 교차검증 접근 불가"
        return {**ecos, "crosscheck": crosscheck}

    try:
        from .fx_api import historical_krw
    except ImportError:
        from fx_api import historical_krw
    q = historical_krw("USD", target)
    return {
        "rate": q.rate,
        "date": q.date,
        "requested_date": target.isoformat(),
        "source": q.source + " 일일 기준환율",
        "source_url": "https://api.frankfurter.dev/v2/rates?base=USD&quotes=KRW&providers=ECB&date=" + q.date,
        "crosscheck": q.check,
        "official": True,
    }


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
    requested = fx.get("requested_date") or fx["date"]
    date_note = fx["date"] if fx["date"] == requested else f"{fx['date']} · 요청일 {requested} 직전 공식값"
    fx_line = (
        f"원화 환산 기준: 1달러={rate:,.2f}원 | 기준일 {date_note} | {fx['source']} | "
        f"교차검증: {fx['crosscheck']} | 조회 {now}"
    )
    source_line = f'• 원/달러 환율: <a href="{fx["source_url"]}">원문</a>'

    marker = "\n공식·데이터 원천:\n"
    if marker in enriched:
        enriched = enriched.replace(marker, f"\n{fx_line}\n\n공식·데이터 원천:\n{source_line}\n", 1)
    else:
        enriched = enriched.rstrip() + f"\n\n{fx_line}\n{source_line}\n"
    return enriched


def append_fx_failure(text: str, reason: str) -> str:
    now = dt.datetime.now(KST).isoformat(timespec="seconds")
    safe_reason = " ".join(str(reason).split())[:180]
    line = f"원화 환산 보류: 한국은행 ECOS 및 보조 환율 원천 확인 실패 | 조회 {now} | {safe_reason}"
    marker = "\n공식·데이터 원천:\n"
    if marker in text:
        return text.replace(marker, f"\n{line}\n\n공식·데이터 원천:\n", 1)
    return text.rstrip() + f"\n\n{line}\n"


def main() -> None:
    if not ALERT_PATH.exists():
        return
    if not STATE_PATH.exists():
        raise RuntimeError("pending state 파일이 없어 원화 환산 기준일을 확정할 수 없음")
    target = parse_target_date()
    text = ALERT_PATH.read_text(encoding="utf-8")
    try:
        fx = get_usdkrw(target)
    except Exception as exc:
        ALERT_PATH.write_text(append_fx_failure(text, str(exc)), encoding="utf-8")
        print(json.dumps({"krw_conversion": "deferred", "reason": str(exc)}, ensure_ascii=False))
        return

    ALERT_PATH.write_text(enrich_text(text, fx), encoding="utf-8")
    print(json.dumps(fx, ensure_ascii=False))


if __name__ == "__main__":
    main()
