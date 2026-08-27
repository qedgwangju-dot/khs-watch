#!/usr/bin/env python3
from __future__ import annotations

import datetime as dt
import hashlib
import html
import io
import json
import pathlib
import re
import urllib.parse
import xml.etree.ElementTree as ET
from email.utils import parsedate_to_datetime
from typing import Any
from zoneinfo import ZoneInfo

import pandas as pd
import requests
from bs4 import BeautifulSoup

from global_rates_watch import fetch_fred_series

KST = ZoneInfo("Asia/Seoul")
ROOT = pathlib.Path(__file__).resolve().parents[1]
STATE_PATH = ROOT / "data" / "korea_market_stress_watch_state.json"
OUT = ROOT / "out"
OUT.mkdir(parents=True, exist_ok=True)
ALERT_PATH = OUT / "korea_market_stress_alert.html"
STATUS_PATH = OUT / "korea_market_stress_status.md"
PENDING_PATH = OUT / "korea_market_stress_pending_state.json"
ERROR_PATH = OUT / "korea_market_stress_errors.log"

BOK_HOME_URL = "https://www.bok.or.kr/portal/main/main.do"
NAVER_FX_URL = "https://api.stock.naver.com/marketindex/exchange/FX_USDKRW/prices?page=1&pageSize=5"
NAVER_INVESTOR_URL = "https://finance.naver.com/sise/investorDealTrendDay.naver?bizdate={bizdate}&sosok=01"
FRED_UST10_URL = "https://fred.stlouisfed.org/series/DGS10"
FRED_FED_UPPER_URL = "https://fred.stlouisfed.org/series/DFEDTARU"
GOOGLE_NEWS_RSS = "https://news.google.com/rss/search"
HEADERS = {
    "User-Agent": "Mozilla/5.0 (compatible; khs-korea-market-stress-watch/4.0)",
    "Accept-Language": "ko-KR,ko;q=0.9,en-US;q=0.8,en;q=0.7",
    "Referer": "https://finance.naver.com/",
}


def load_state() -> dict[str, Any]:
    try:
        return json.loads(STATE_PATH.read_text(encoding="utf-8")) if STATE_PATH.exists() else {}
    except Exception:
        return {}


def get(url: str, timeout: int = 35) -> requests.Response:
    r = requests.get(url, headers=HEADERS, timeout=timeout)
    r.raise_for_status()
    return r


def to_float(value: Any) -> float:
    return float(str(value).replace(",", "").replace("%", "").strip())


def fetch_usdkrw() -> dict[str, Any]:
    payload = get(NAVER_FX_URL).json()
    rows = payload.get("result") if isinstance(payload, dict) else payload
    rows = rows or []
    parsed: list[tuple[str, float]] = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        d = str(row.get("localTradedAt") or row.get("localDate") or "")[:10]
        p = row.get("closePrice")
        if d and p not in (None, ""):
            parsed.append((d, to_float(p)))
    if len(parsed) < 2:
        raise RuntimeError("원/달러 비교 시세가 2개 미만")
    parsed = sorted(dict(parsed).items())
    (d0, v0), (d1, v1) = parsed[-2:]
    return {
        "date": d1,
        "value": v1,
        "prev_date": d0,
        "prev_value": v0,
        "change_krw": round(v1 - v0, 4),
        "change_pct": round((v1 / v0 - 1) * 100, 4),
        "source": NAVER_FX_URL,
    }


def fetch_ust10() -> dict[str, Any]:
    rows = fetch_fred_series("DGS10", max_rows=8)
    if len(rows) < 2:
        raise RuntimeError("미국 10년물 비교 관측치 부족")
    (d0, v0), (d1, v1) = rows[-2:]
    return {
        "date": d1,
        "value": v1,
        "prev_date": d0,
        "prev_value": v0,
        "change_bp": round((v1 - v0) * 100, 1),
        "source": FRED_UST10_URL,
    }


def fetch_bok_base_rate(now: dt.datetime) -> dict[str, Any]:
    text = BeautifulSoup(get(BOK_HOME_URL).text, "html.parser").get_text(" ", strip=True)
    # Official BOK home page renders: 한국은행기준금리 2.75%
    match = re.search(r"한국은행\s*기준금리\s*([0-9]+(?:\.[0-9]+)?)\s*%?", text)
    if not match:
        match = re.search(r"한국은행기준금리\s*([0-9]+(?:\.[0-9]+)?)\s*%?", text)
    if not match:
        raise RuntimeError("한국은행 홈페이지 현재 기준금리 파싱 실패")
    return {"date": now.date().isoformat(), "value": float(match.group(1)), "source": BOK_HOME_URL}


def fetch_policy_spread(now: dt.datetime) -> dict[str, Any]:
    fed_date, fed_upper = fetch_fred_series("DFEDTARU", max_rows=3)[-1]
    bok = fetch_bok_base_rate(now)
    return {
        "date": max(fed_date, bok["date"]),
        "fed_upper": fed_upper,
        "bok_base": bok["value"],
        "spread_pp": round(fed_upper - bok["value"], 4),
        "fed_source": FRED_FED_UPPER_URL,
        "bok_source": BOK_HOME_URL,
    }


def flatten_columns(df: pd.DataFrame) -> list[str]:
    out: list[str] = []
    for col in df.columns:
        if isinstance(col, tuple):
            parts = [str(c) for c in col if str(c) and not str(c).startswith("Unnamed")]
            out.append(parts[-1] if parts else "")
        else:
            out.append(str(col))
    return out


def fetch_kospi_foreign_flow(now: dt.datetime) -> dict[str, Any]:
    url = NAVER_INVESTOR_URL.format(bizdate=now.strftime("%Y%m%d"))
    tables = pd.read_html(io.StringIO(get(url).text))
    table = next((t for t in tables if t.shape[0] > 2 and t.shape[1] >= 5), None)
    if table is None:
        raise RuntimeError("KOSPI 투자자별 매매동향 표 없음")
    names = flatten_columns(table)
    if "날짜" not in names or "외국인" not in names:
        raise RuntimeError(f"KOSPI 수급 열 형식 변경: {names}")
    dpos, fpos = names.index("날짜"), names.index("외국인")
    rows: list[tuple[dt.date, float]] = []
    for _, row in table.iterrows():
        raw = str(row.iloc[dpos]).strip()
        parts = raw.split(".")
        if len(parts) != 3 or not all(p.isdigit() for p in parts):
            continue
        try:
            day = dt.date(2000 + int(parts[0]), int(parts[1]), int(parts[2]))
            eok = float(row.iloc[fpos])
        except Exception:
            continue
        rows.append((day, eok))
    if not rows:
        raise RuntimeError("KOSPI 외국인 순매수 행 없음")
    rows = sorted(dict(rows).items())
    day, daily_eok = rows[-1]
    three_eok = sum(v for _, v in rows[-3:])
    return {
        "date": day.isoformat(),
        "daily_eok": daily_eok,
        "three_day_eok": three_eok,
        "daily_krw": int(round(daily_eok * 100_000_000)),
        "three_day_krw": int(round(three_eok * 100_000_000)),
        "source": url,
    }


def google_news(query: str, limit: int = 12) -> list[dict[str, Any]]:
    params = urllib.parse.urlencode({"q": query, "hl": "en-US", "gl": "US", "ceid": "US:en"})
    root = ET.fromstring(get(f"{GOOGLE_NEWS_RSS}?{params}").content)
    out: list[dict[str, Any]] = []
    for item in root.findall(".//item")[:limit]:
        pub = (item.findtext("pubDate") or "").strip()
        try:
            published = parsedate_to_datetime(pub)
            if published.tzinfo is None:
                published = published.replace(tzinfo=dt.timezone.utc)
        except Exception:
            published = None
        out.append({
            "title": (item.findtext("title") or "").strip(),
            "link": (item.findtext("link") or "").strip(),
            "description": BeautifulSoup(item.findtext("description") or "", "html.parser").get_text(" ", strip=True),
            "published": pub,
            "published_dt": published,
        })
    return out


def fresh(item: dict[str, Any], now: dt.datetime, days: int = 120) -> bool:
    p = item.get("published_dt")
    return isinstance(p, dt.datetime) and p >= now.astimezone(dt.timezone.utc) - dt.timedelta(days=days)


def extract_pct(text: str) -> list[float]:
    vals: list[float] = []
    for raw in re.findall(r"(?<!\d)(-?\d+(?:\.\d+)?)\s*%", text):
        try:
            vals.append(float(raw))
        except Exception:
            pass
    return vals


def news_key(prefix: str, title: str) -> str:
    return prefix + ":" + hashlib.sha256(title.encode("utf-8")).hexdigest()[:16]


def fmt_eok(value_krw: int) -> str:
    sign = "+" if value_krw > 0 else "-" if value_krw < 0 else ""
    return f"{sign}{abs(value_krw) / 100_000_000:,.0f}억원"


def source_link(url: str) -> str:
    return f'<a href="{html.escape(url, quote=True)}">원문</a>'


def add_event(events: list[dict[str, str]], key: str, text: str, source: str) -> None:
    events.append({"key": key, "text": text, "source": source})


def main() -> int:
    ALERT_PATH.unlink(missing_ok=True)
    ERROR_PATH.unlink(missing_ok=True)
    now = dt.datetime.now(KST)
    old = load_state()
    first = old.get("watch_version") != 4
    current: dict[str, Any] = {"checked_at_kst": now.isoformat(timespec="seconds"), "watch_version": 4}
    errors: list[str] = []

    for key, fn, label in (
        ("usdkrw", fetch_usdkrw, "원/달러"),
        ("ust10", fetch_ust10, "미국 10년물"),
        ("policy_spread", lambda: fetch_policy_spread(now), "한미 정책금리차"),
        ("foreign_flow", lambda: fetch_kospi_foreign_flow(now), "KOSPI 외국인 수급"),
    ):
        try:
            current[key] = fn()
        except Exception as exc:
            errors.append(f"{label} 조회 실패: {type(exc).__name__}: {exc}")

    try:
        words = (
            "trough", "troughed", "peak", "peaked", "rise", "rises", "rising", "rose",
            "fall", "falls", "falling", "fell", "improve", "improves", "improved",
            "deteriorate", "deteriorates", "deteriorated", "positive signal", "negative signal",
        )
        gw: list[dict[str, Any]] = []
        for item in google_news('BofA "Global Wave" earnings revisions', 15):
            blob = (item["title"] + " " + item["description"]).lower()
            if fresh(item, now) and "global wave" in blob and any(w in blob for w in words):
                gw.append(item)
        current["global_wave_news"] = gw[:8]
    except Exception as exc:
        errors.append(f"BofA Global Wave 감시 실패: {type(exc).__name__}: {exc}")

    try:
        queries = [
            'Microsoft capex guidance AI data center percent',
            'Alphabet capex guidance AI data center percent',
            'Amazon capex guidance AI data center percent',
            'Meta capex guidance AI data center percent',
        ]
        capex: list[dict[str, Any]] = []
        titles: set[str] = set()
        for q in queries:
            for item in google_news(q, 10):
                if item["title"] in titles or not fresh(item, now):
                    continue
                titles.add(item["title"])
                blob = (item["title"] + " " + item["description"]).lower()
                if not any(k in blob for k in ("capex", "capital expenditure", "capital spending", "data center", "ai infrastructure")):
                    continue
                pcts = extract_pct(blob)
                if any(abs(p) >= 10 for p in pcts):
                    item = dict(item)
                    item["percentages"] = pcts
                    capex.append(item)
        current["hyperscaler_capex_news"] = capex[:12]
    except Exception as exc:
        errors.append(f"AI 설비투자 감시 실패: {type(exc).__name__}: {exc}")

    if errors:
        ERROR_PATH.write_text("\n".join(errors) + "\n", encoding="utf-8")

    events: list[dict[str, str]] = []
    active_keys: list[str] = []

    fx = current.get("usdkrw")
    if fx:
        d = fx["date"]
        if fx["change_krw"] >= 20 or fx["change_pct"] >= 1.0:
            k = f"fx_daily_up:{d}"; active_keys.append(k)
            add_event(events, k, f"• 원/달러 일간 급등: {fx['prev_value']:,.1f}원 → {fx['value']:,.1f}원 ({fx['change_krw']:+,.1f}원, {fx['change_pct']:+.2f}%)", fx["source"])
        if fx["change_krw"] <= -20 or fx["change_pct"] <= -1.0:
            k = f"fx_daily_down:{d}"; active_keys.append(k)
            add_event(events, k, f"• 원/달러 일간 급락: {fx['prev_value']:,.1f}원 → {fx['value']:,.1f}원 ({fx['change_krw']:+,.1f}원, {fx['change_pct']:+.2f}%)", fx["source"])
        if fx["value"] >= 1400:
            k = f"fx_1400_up:{d}"; active_keys.append(k)
            add_event(events, k, f"• 원/달러 1,400원 상단 진입: 현재 {fx['value']:,.1f}원", fx["source"])
        if fx["value"] <= 1350:
            k = f"fx_1350_down:{d}"; active_keys.append(k)
            add_event(events, k, f"• 원/달러 1,350원 하단 진입: 현재 {fx['value']:,.1f}원", fx["source"])

    u10 = current.get("ust10")
    if u10:
        d = u10["date"]
        if u10["change_bp"] >= 10:
            k = f"ust10_up:{d}"; active_keys.append(k)
            add_event(events, k, f"• 미국 10년물 일간 상승: {u10['prev_value']:.2f}% → {u10['value']:.2f}% ({u10['change_bp']:+.1f}bp)", u10["source"])
        if u10["change_bp"] <= -10:
            k = f"ust10_down:{d}"; active_keys.append(k)
            add_event(events, k, f"• 미국 10년물 일간 하락: {u10['prev_value']:.2f}% → {u10['value']:.2f}% ({u10['change_bp']:+.1f}bp)", u10["source"])

    flow = current.get("foreign_flow")
    if flow:
        d = flow["date"]
        tests = [
            (flow["daily_krw"] >= 1_000_000_000_000, f"foreign1d_pos:{d}", f"• KOSPI 외국인 1일 순매수 {fmt_eok(flow['daily_krw'])} — +1조원 기준 돌파"),
            (flow["daily_krw"] <= -1_000_000_000_000, f"foreign1d_neg:{d}", f"• KOSPI 외국인 1일 순매수 {fmt_eok(flow['daily_krw'])} — -1조원 기준 돌파"),
            (flow["three_day_krw"] >= 3_000_000_000_000, f"foreign3d_pos:{d}", f"• KOSPI 외국인 최근 3거래일 누적 {fmt_eok(flow['three_day_krw'])} — +3조원 기준 돌파"),
            (flow["three_day_krw"] <= -3_000_000_000_000, f"foreign3d_neg:{d}", f"• KOSPI 외국인 최근 3거래일 누적 {fmt_eok(flow['three_day_krw'])} — -3조원 기준 돌파"),
        ]
        for hit, key, text in tests:
            if hit:
                active_keys.append(key)
                add_event(events, key, text, flow["source"])

    spread = current.get("policy_spread")
    prior_spread = (old.get("snapshot") or {}).get("policy_spread") if not first else None
    if spread and prior_spread and isinstance(prior_spread.get("spread_pp"), (int, float)):
        delta = round(spread["spread_pp"] - float(prior_spread["spread_pp"]), 4)
        if abs(delta) >= 0.25:
            k = f"policy_spread:{spread['date']}:{spread['spread_pp']:.2f}"
            add_event(events, k, f"• 한미 정책금리차: {prior_spread['spread_pp']:.2f}%p → {spread['spread_pp']:.2f}%p ({delta:+.2f}%p)", spread["bok_source"])

    for item in current.get("global_wave_news", []):
        add_event(events, news_key("globalwave", item["title"]), "• BofA Global Wave 방향 전환 관련 신규 공개자료: " + html.escape(item["title"]), item["link"])
    for item in current.get("hyperscaler_capex_news", []):
        add_event(events, news_key("capex", item["title"]), "• 하이퍼스케일러 AI 설비투자 ±10% 이상 수치 포함 신규자료: " + html.escape(item["title"]), item["link"])

    old_seen = set(old.get("seen_event_keys") or []) if not first else set()
    # v4 첫 실행은 현재 활성 조건과 현재 뉴스 후보를 기준선으로만 저장해 과거 자료 발송을 막는다.
    all_keys = [e["key"] for e in events]
    new_events = [] if first else [e for e in events if e["key"] not in old_seen]
    new_seen = list(dict.fromkeys(list(old_seen) + all_keys))[-500:]

    pending = {
        "watch_version": 4,
        "updated_at_kst": now.isoformat(timespec="seconds"),
        "seen_event_keys": new_seen,
        "active_keys": active_keys,
        "snapshot": current,
    }
    PENDING_PATH.write_text(json.dumps(pending, ensure_ascii=False, indent=2, default=str) + "\n", encoding="utf-8")

    if new_events:
        lines = [
            "🚨 <b>한국 시장 스트레스·글로벌 사이클 변화 감지</b>", "",
            *[e["text"] for e in new_events], "",
            "<b>알림 기준</b>",
            "• 원/달러: 일간 ±20원 또는 ±1%, 1,400원 상단·1,350원 하단",
            "• KOSPI 외국인: 1일 ±1조원, 최근 3거래일 누적 ±3조원",
            "• 미국 10년물: 일간 ±10bp",
            "• 한미 정책금리차: 직전 감시값 대비 ±25bp",
            "• BofA Global Wave: 독점 수치 추정 금지, 최근 공개자료의 방향 전환만 감지",
            "• 하이퍼스케일러 AI 설비투자: ±10% 이상 수치가 명시된 최근 신규자료",
            "", "<b>원문</b>",
        ]
        used: set[str] = set()
        for e in new_events:
            src = e.get("source") or ""
            if src and src not in used:
                used.add(src)
                lines.append("• " + source_link(src))
        ALERT_PATH.write_text("\n".join(lines) + "\n", encoding="utf-8")

    status = [
        "# 한국 시장 스트레스·글로벌 사이클 감시", "",
        f"- 확인시각(KST): {now:%Y-%m-%d %H:%M:%S}",
        "- 감시 버전: 4",
        f"- 새 기준선 설정: {'예' if first else '아니오'}",
        f"- 신규 알림 이벤트: {len(new_events)}개",
        f"- 조회 오류: {len(errors)}건",
    ]
    if fx:
        status.append(f"- 원/달러: {fx['value']:,.1f}원, 일간 {fx['change_krw']:+,.1f}원 / {fx['change_pct']:+.2f}%, 기준일 {fx['date']}")
    if u10:
        status.append(f"- 미국 10년물: {u10['value']:.2f}%, 일간 {u10['change_bp']:+.1f}bp, 기준일 {u10['date']}")
    if flow:
        status.append(f"- KOSPI 외국인: 1일 {fmt_eok(flow['daily_krw'])}, 3거래일 {fmt_eok(flow['three_day_krw'])}, 기준일 {flow['date']}")
    if spread:
        status.append(f"- 한미 정책금리차: 미국 {spread['fed_upper']:.2f}% - 한국 {spread['bok_base']:.2f}% = {spread['spread_pp']:.2f}%p")
    status.append(f"- BofA Global Wave 최근 방향 후보: {len(current.get('global_wave_news', []))}건")
    status.append(f"- 하이퍼스케일러 AI 설비투자 ±10% 후보: {len(current.get('hyperscaler_capex_news', []))}건")
    STATUS_PATH.write_text("\n".join(status) + "\n", encoding="utf-8")
    print(STATUS_PATH.read_text(encoding="utf-8"))
    if errors:
        print(ERROR_PATH.read_text(encoding="utf-8"))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
