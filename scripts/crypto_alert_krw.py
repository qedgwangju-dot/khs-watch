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
FARSIDE_BTC_ETF_URL = "https://farside.co.uk/bitcoin-etf-flow-all-data/"
RIVER_DEMAND_URL = "https://river.com/content/btc-840k-within-five-years"
BLACKROCK_SIZING_URL = "https://www.blackrock.com/institutions/en-us/insights/thought-leadership/portfolio-design/sizing-bitcoin-in-portfolios"
RIVER_SCENARIO_DATE = "2026-09-02"
RIVER_GLOBAL_FINANCIAL_WEALTH_USD_T = 333.0
RIVER_PORTFOLIO_ADOPTION_RANGE = "20~40%"
RIVER_AVG_BTC_ALLOCATION_RANGE = "2~4%"
RIVER_POTENTIAL_LOW_USD_M = 1_300_000.0
RIVER_POTENTIAL_HIGH_USD_M = 5_300_000.0
RIVER_ADVISOR_ALLOCATION_PCT = 0.008
BLACKROCK_BTC_ALLOCATION_RANGE = "1~2%"
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
        body = f"{jo:,}조{rem:,}억원" if rem else f"{jo:,}조원"
    else:
        body = f"{rounded:,}억원"
    return f"약 {sign}{body}"


def parse_table_number(text: str) -> float | None:
    raw = (text or "").strip().replace("$", "").replace(",", "")
    if not raw or raw in {"-", "—", "N/A", "n/a"}:
        return None
    negative = raw.startswith("(") and raw.endswith(")")
    if negative:
        raw = raw[1:-1]
    m = re.search(r"[-+]?\d+(?:\.\d+)?", raw)
    if not m:
        return None
    value = float(m.group(0))
    return -abs(value) if negative else value


def farside_cumulative_total_usd_m() -> float | None:
    """Read Farside's all-period Total row and verify it against fund totals."""
    html = fetch(FARSIDE_BTC_ETF_URL).decode("utf-8", errors="replace")
    soup = BeautifulSoup(html, "html.parser")
    for tr in soup.find_all("tr"):
        cells = [" ".join(td.get_text(" ", strip=True).split()) for td in tr.find_all(["td", "th"])]
        if len(cells) < 3 or cells[0].strip().lower() != "total":
            continue
        total = parse_table_number(cells[-1])
        fund_values = [parse_table_number(x) for x in cells[1:-1]]
        valid_funds = [v for v in fund_values if v is not None]
        recomputed = sum(valid_funds)
        if total is None or len(valid_funds) < 10:
            return None
        if abs(total - recomputed) > 2.0:
            return None
        return total
    return None


def format_usd_b_from_usd_m(value_usd_m: float) -> str:
    sign = "+" if value_usd_m > 0 else "-" if value_usd_m < 0 else ""
    return f"{sign}${abs(value_usd_m) / 1000.0:,.2f}B"


def structural_krw_range(rate: float) -> str:
    low = format_krw_from_usd_m(RIVER_POTENTIAL_LOW_USD_M, rate)
    high = format_krw_from_usd_m(RIVER_POTENTIAL_HIGH_USD_M, rate)
    if high.startswith("약 "):
        high = high[2:]
    return f"{low}~{high}"


def capital_position_block(rate: float) -> str:
    try:
        cumulative = farside_cumulative_total_usd_m()
    except Exception:
        cumulative = None

    try:
        state = json.loads(STATE_PATH.read_text(encoding="utf-8"))
    except Exception:
        state = {}

    etf = state.get("btc_etf") or {}
    latest_date = str(etf.get("date") or "").strip()
    date_text = f" · 최신 유효일 {latest_date}" if latest_date else ""
    reported = int(etf.get("reported_funds", 0) or 0)
    missing = int(etf.get("missing_funds", 0) or 0)
    total_funds = reported + missing
    is_partial = str(etf.get("status") or "") == "partial" or missing > 0
    provisional = " · 잠정" if is_partial else ""

    lines = ["<b>BTC 자금 위치</b>"]
    if cumulative is None:
        lines += [
            "• <b>미국 현물 ETF 실제 누적 · 확인 불가</b>",
            "  Farside Total 행 재검산 실패 · 추정값 사용 안 함",
        ]
    else:
        direction = "순유입" if cumulative >= 0 else "순유출"
        lines += [
            f"• <b>미국 현물 ETF 실제 누적 {direction}{provisional} · {format_usd_b_from_usd_m(cumulative)} · {format_krw_from_usd_m(cumulative, rate)}</b>",
            f"  Farside 전체 집계기간 기준{date_text}",
        ]
        if is_partial:
            coverage = f"{total_funds}개 중 {reported}개 반영·{missing}개 미보고" if total_funds else "일부 ETF 미보고"
            lines += [f"  ※ 최신 일간값이 {coverage}라 누적 Total도 잠정"]

    lines += [
        "",
        "<b>구조적 수요 맥락</b>",
        f"• <b>River 잠재 순유입 · $1.3T~$5.3T</b> ({structural_krw_range(rate)})",
        (
            f"  3~5년 · 글로벌 금융자산 ${RIVER_GLOBAL_FINANCIAL_WEALTH_USD_T:.0f}T × "
            f"포트폴리오 채택 {RIVER_PORTFOLIO_ADOPTION_RANGE} × 평균 BTC 배분 {RIVER_AVG_BTC_ALLOCATION_RANGE}"
        ),
        f"• <b>현재 배분 격차</b> · River 추정 투자자문사 전체 BTC 배분 {RIVER_ADVISOR_ALLOCATION_PCT:.3f}%",
        (
            f"• <b>기관 배분 기준</b> · BlackRock {BLACKROCK_BTC_ALLOCATION_RANGE}를 합리적 범위로 제시"
            " · 2% 초과 시 포트폴리오 위험기여 급증"
        ),
        (
            f"※ River {RIVER_SCENARIO_DATE} 시나리오이며 미국 현물 ETF 실제 누적과 모집단이 다름"
            " · 잠재수요 대비 진척률로 계산하지 않음"
        ),
    ]
    return "\n".join(lines)


def enrich_text(text: str, fx: dict) -> str:
    rate = float(fx["rate"])
    pattern = re.compile(r"(?P<amount>[+-]?\d[\d,]*(?:\.\d+)?)백만달러(?!\s*\(약)")

    def repl(m: re.Match[str]) -> str:
        raw = m.group("amount")
        value = float(raw.replace(",", ""))
        return f"{raw}백만달러 ({format_krw_from_usd_m(value, rate)})"

    enriched = pattern.sub(repl, text)

    position_block = capital_position_block(rate)
    treasury_marker = "\n미 국채 —"
    if position_block and treasury_marker in enriched:
        enriched = enriched.replace(treasury_marker, f"\n\n{position_block}\n{treasury_marker.lstrip()}", 1)

    now = dt.datetime.now(KST).isoformat(timespec="seconds")
    requested = fx.get("requested_date") or fx["date"]
    date_note = fx["date"] if fx["date"] == requested else f"{fx['date']} · 요청일 {requested} 직전 공식값"
    fx_line = (
        f"원화 환산 기준: 1달러={rate:,.2f}원 | 기준일 {date_note} | {fx['source']} | "
        f"교차검증: {fx['crosscheck']} | 조회 {now}"
    )
    source_lines = "\n".join([
        f'• 원/달러 환율: <a href="{fx["source_url"]}">원문</a>',
        f'• River 구조적 수요 시나리오: <a href="{RIVER_DEMAND_URL}">원문</a>',
        f'• BlackRock BTC 배분 기준: <a href="{BLACKROCK_SIZING_URL}">원문</a>',
    ])

    marker = "\n공식·데이터 원천:\n"
    if marker in enriched:
        enriched = enriched.replace(marker, f"\n{fx_line}\n\n공식·데이터 원천:\n{source_lines}\n", 1)
    else:
        enriched = enriched.rstrip() + f"\n\n{fx_line}\n{source_lines}\n"
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
