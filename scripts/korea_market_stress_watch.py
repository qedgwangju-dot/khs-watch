#!/usr/bin/env python3
from __future__ import annotations

import datetime as dt
import hashlib
import html
import json
import pathlib
import re
import urllib.parse
import xml.etree.ElementTree as ET
from typing import Any
from zoneinfo import ZoneInfo

import requests
from bs4 import BeautifulSoup
from pykrx import stock

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

BOK_RATE_URL = "https://www.bok.or.kr/portal/singl/baseRate/list.do?menuNo=200643"
KRX_INVESTOR_URL = "https://data.krx.co.kr/contents/MDC/MAIN/main/index.cmd"
FRED_USDKRW_URL = "https://fred.stlouisfed.org/series/DEXKOUS"
FRED_UST10_URL = "https://fred.stlouisfed.org/series/DGS10"
FRED_FED_UPPER_URL = "https://fred.stlouisfed.org/series/DFEDTARU"
GOOGLE_NEWS_RSS = "https://news.google.com/rss/search"
HEADERS = {
    "User-Agent": "Mozilla/5.0 (compatible; khs-korea-market-stress-watch/1.0)",
    "Accept-Language": "ko-KR,ko;q=0.9,en-US;q=0.8,en;q=0.7",
}


def get_text(url: str, timeout: int = 35) -> str:
    r = requests.get(url, headers=HEADERS, timeout=timeout)
    r.raise_for_status()
    return r.text


def load_state() -> dict[str, Any]:
    try:
        return json.loads(STATE_PATH.read_text(encoding="utf-8")) if STATE_PATH.exists() else {}
    except Exception:
        return {}


def latest_two_fred(series: str) -> list[tuple[str, float]]:
    rows = fetch_fred_series(series, max_rows=8)
    if len(rows) < 2:
        raise RuntimeError(f"FRED {series}: 비교 가능한 관측치 부족")
    return rows[-2:]


def fetch_bok_base_rate() -> dict[str, Any]:
    text = BeautifulSoup(get_text(BOK_RATE_URL), "html.parser").get_text(" ", strip=True)
    pairs = re.findall(r"(20\d{2})\s*[년]?[\s\S]{0,30}?(\d{1,2})월\s*(\d{1,2})일\s*([0-9]+(?:\.[0-9]+)?)", text)
    if not pairs:
        # Current BOK page typically renders rows as: 2026 | 07월 16일 | 2.75
        pairs = re.findall(r"(20\d{2})\s+(\d{1,2})월\s+(\d{1,2})일\s+([0-9]+(?:\.[0-9]+)?)", text)
    if not pairs:
        raise RuntimeError("한국은행 기준금리 표 파싱 실패")
    year, month, day, rate = pairs[0]
    return {
        "date": f"{int(year):04d}-{int(month):02d}-{int(day):02d}",
        "value": float(rate),
        "source": BOK_RATE_URL,
    }


def fetch_kospi_foreign_flow() -> dict[str, Any]:
    today = dt.datetime.now(KST).date()
    start = today - dt.timedelta(days=12)
    df = stock.get_market_trading_value_by_date(
        start.strftime("%Y%m%d"), today.strftime("%Y%m%d"), "KOSPI"
    )
    if df is None or df.empty:
        raise RuntimeError("KRX KOSPI 투자자별 거래대금 조회 결과 없음")
    col = "외국인합계" if "외국인합계" in df.columns else "외국인"
    if col not in df.columns:
        raise RuntimeError(f"KRX 외국인 열 없음: {list(df.columns)}")
    s = df[col].dropna().astype("int64")
    if s.empty:
        raise RuntimeError("KRX 외국인 순매수 데이터 없음")
    latest_date = s.index[-1]
    latest = int(s.iloc[-1])
    last3 = int(s.tail(3).sum())
    return {
        "date": latest_date.strftime("%Y-%m-%d"),
        "daily_krw": latest,
        "three_day_krw": last3,
        "source": KRX_INVESTOR_URL,
    }


def google_news(query: str, limit: int = 10) -> list[dict[str, str]]:
    params = urllib.parse.urlencode({"q": query, "hl": "en-US", "gl": "US", "ceid": "US:en"})
    xml = requests.get(f"{GOOGLE_NEWS_RSS}?{params}", headers=HEADERS, timeout=35)
    xml.raise_for_status()
    root = ET.fromstring(xml.content)
    out: list[dict[str, str]] = []
    for item in root.findall(".//item")[:limit]:
        title = (item.findtext("title") or "").strip()
        link = (item.findtext("link") or "").strip()
        desc = BeautifulSoup(item.findtext("description") or "", "html.parser").get_text(" ", strip=True)
        pub = (item.findtext("pubDate") or "").strip()
        out.append({"title": title, "link": link, "description": desc, "published": pub})
    return out


def news_key(prefix: str, title: str) -> str:
    return prefix + ":" + hashlib.sha256(title.encode("utf-8")).hexdigest()[:16]


def extract_pct(text: str) -> list[float]:
    vals = []
    for raw in re.findall(r"(?<!\d)(-?\d+(?:\.\d+)?)\s*%", text):
        try:
            vals.append(float(raw))
        except Exception:
            pass
    return vals


def fmt_eok(value: int) -> str:
    sign = "+" if value > 0 else "-" if value < 0 else ""
    eok = abs(value) / 100_000_000
    return f"{sign}{eok:,.0f}억원"


def direction(value: float) -> str:
    return "상승" if value > 0 else "하락" if value < 0 else "보합"


def html_link(label: str, url: str) -> str:
    return f'<a href="{html.escape(url, quote=True)}">{html.escape(label)}</a>'


def main() -> int:
    ALERT_PATH.unlink(missing_ok=True)
    ERROR_PATH.unlink(missing_ok=True)
    old = load_state()
    now = dt.datetime.now(KST)
    errors: list[str] = []
    current: dict[str, Any] = {
        "checked_at_kst": now.isoformat(timespec="seconds"),
        "watch_version": 1,
    }

    # 1) USD/KRW — Federal Reserve daily exchange-rate series.
    try:
        rows = latest_two_fred("DEXKOUS")
        (d0, v0), (d1, v1) = rows
        current["usdkrw"] = {
            "date": d1,
            "value": v1,
            "prev_date": d0,
            "prev_value": v0,
            "change_krw": round(v1 - v0, 4),
            "change_pct": round((v1 / v0 - 1) * 100, 4),
            "source": FRED_USDKRW_URL,
        }
    except Exception as exc:
        errors.append(f"USD/KRW 조회 실패: {type(exc).__name__}: {exc}")

    # 2) U.S. 10Y — Treasury/FRED daily series, 10bp meaningful move threshold.
    try:
        rows = latest_two_fred("DGS10")
        (d0, v0), (d1, v1) = rows
        current["ust10"] = {
            "date": d1,
            "value": v1,
            "prev_date": d0,
            "prev_value": v0,
            "change_bp": round((v1 - v0) * 100, 1),
            "source": FRED_UST10_URL,
        }
    except Exception as exc:
        errors.append(f"미국 10년물 조회 실패: {type(exc).__name__}: {exc}")

    # 3) Korea-U.S. policy-rate spread — Fed upper bound minus BOK base rate.
    try:
        fed = fetch_fred_series("DFEDTARU", max_rows=3)[-1]
        bok = fetch_bok_base_rate()
        current["policy_spread"] = {
            "date": max(fed[0], bok["date"]),
            "fed_upper": fed[1],
            "bok_base": bok["value"],
            "spread_pp": round(fed[1] - bok["value"], 4),
            "fed_source": FRED_FED_UPPER_URL,
            "bok_source": BOK_RATE_URL,
        }
    except Exception as exc:
        errors.append(f"한미 정책금리차 조회 실패: {type(exc).__name__}: {exc}")

    # 4) KOSPI foreign investor net flow — KRX data through pykrx.
    try:
        current["foreign_flow"] = fetch_kospi_foreign_flow()
    except Exception as exc:
        errors.append(f"KOSPI 외국인 수급 조회 실패: {type(exc).__name__}: {exc}")

    # 5) BofA Global Wave publication-change radar.
    try:
        gw_items = google_news('BofA "Global Wave" earnings revisions', limit=12)
        directional = []
        words = (
            "trough", "troughed", "peak", "peaked", "rise", "rises", "rising", "rose",
            "fall", "falls", "falling", "fell", "improve", "improves", "improved",
            "deteriorate", "deteriorates", "deteriorated", "positive signal", "negative signal",
        )
        for item in gw_items:
            blob = (item["title"] + " " + item["description"]).lower()
            if "global wave" in blob and any(w in blob for w in words):
                directional.append(item)
        current["global_wave_news"] = directional[:8]
    except Exception as exc:
        errors.append(f"BofA Global Wave 공개자료 감시 실패: {type(exc).__name__}: {exc}")

    # 6) Hyperscaler AI capex guidance radar — only items explicitly carrying >=10% percentage figures.
    try:
        capex_queries = [
            'Microsoft capex guidance AI data center percent',
            'Alphabet capex guidance AI data center percent',
            'Amazon capex guidance AI data center percent',
            'Meta capex guidance AI data center percent',
        ]
        capex_items: list[dict[str, str]] = []
        seen_titles: set[str] = set()
        for q in capex_queries:
            for item in google_news(q, limit=8):
                title = item["title"]
                if title in seen_titles:
                    continue
                seen_titles.add(title)
                blob = (title + " " + item["description"]).lower()
                if not any(k in blob for k in ("capex", "capital expenditure", "capital spending", "data center", "ai infrastructure")):
                    continue
                pcts = extract_pct(blob)
                if any(abs(p) >= 10 for p in pcts):
                    item = dict(item)
                    item["percentages"] = ", ".join(f"{p:g}%" for p in pcts)
                    capex_items.append(item)
        current["hyperscaler_capex_news"] = capex_items[:12]
    except Exception as exc:
        errors.append(f"하이퍼스케일러 설비투자 감시 실패: {type(exc).__name__}: {exc}")

    if errors:
        ERROR_PATH.write_text("\n".join(errors) + "\n", encoding="utf-8")

    events: list[dict[str, str]] = []

    fx = current.get("usdkrw")
    if fx:
        daily_hit = abs(fx["change_krw"]) >= 20 or abs(fx["change_pct"]) >= 1.0
        level_hit = (fx["prev_value"] < 1400 <= fx["value"]) or (fx["prev_value"] > 1350 >= fx["value"])
        if daily_hit or level_hit:
            events.append({
                "key": f"fx:{fx['date']}:{fx['value']}",
                "text": f"• 환율: {fx['prev_value']:,.1f}원 → {fx['value']:,.1f}원 ({fx['change_krw']:+,.1f}원, {fx['change_pct']:+.2f}%) — {direction(fx['change_krw'])}",
                "source": fx["source"],
            })

    u10 = current.get("ust10")
    if u10 and abs(u10["change_bp"]) >= 10:
        events.append({
            "key": f"ust10:{u10['date']}:{u10['value']}",
            "text": f"• 미국 10년물: {u10['prev_value']:.2f}% → {u10['value']:.2f}% ({u10['change_bp']:+.1f}bp)",
            "source": u10["source"],
        })

    flow = current.get("foreign_flow")
    if flow:
        if abs(flow["daily_krw"]) >= 1_000_000_000_000:
            events.append({
                "key": f"foreign1d:{flow['date']}:{flow['daily_krw']}",
                "text": f"• KOSPI 외국인 1일 순매수: {fmt_eok(flow['daily_krw'])} — 기준 ±1조원 돌파",
                "source": flow["source"],
            })
        if abs(flow["three_day_krw"]) >= 3_000_000_000_000:
            events.append({
                "key": f"foreign3d:{flow['date']}:{flow['three_day_krw']}",
                "text": f"• KOSPI 외국인 최근 3거래일 누적: {fmt_eok(flow['three_day_krw'])} — 기준 ±3조원 돌파",
                "source": flow["source"],
            })

    spread = current.get("policy_spread")
    old_spread = (old.get("snapshot") or {}).get("policy_spread") if old else None
    if spread and old_spread and isinstance(old_spread.get("spread_pp"), (int, float)):
        delta = round(spread["spread_pp"] - float(old_spread["spread_pp"]), 4)
        if abs(delta) >= 0.25:
            events.append({
                "key": f"spread:{spread['date']}:{spread['spread_pp']}",
                "text": f"• 한미 정책금리차(미국 상단-한국): {old_spread['spread_pp']:.2f}%p → {spread['spread_pp']:.2f}%p ({delta:+.2f}%p)",
                "source": spread["bok_source"],
            })

    # News events are publication-change alerts. Global Wave is proprietary, so do not fabricate a numeric level.
    for item in current.get("global_wave_news", []):
        events.append({
            "key": news_key("globalwave", item["title"]),
            "text": "• BofA Global Wave 방향 전환 관련 신규 공개자료: " + html.escape(item["title"]),
            "source": item["link"],
        })

    for item in current.get("hyperscaler_capex_news", []):
        events.append({
            "key": news_key("capex", item["title"]),
            "text": "• 하이퍼스케일러 AI 설비투자 ±10% 이상 수치 포함 신규자료: " + html.escape(item["title"]),
            "source": item["link"],
        })

    seen = set(old.get("seen_event_keys") or [])
    first = not bool(old)
    new_events = [] if first else [e for e in events if e["key"] not in seen]
    new_seen = list(dict.fromkeys(list(seen) + [e["key"] for e in events]))[-300:]

    pending = {
        "updated_at_kst": now.isoformat(timespec="seconds"),
        "seen_event_keys": new_seen,
        "snapshot": current,
    }
    PENDING_PATH.write_text(json.dumps(pending, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    if new_events:
        lines = [
            "🚨 <b>한국 시장 스트레스·글로벌 사이클 변화 감지</b>",
            "",
            *[e["text"] for e in new_events],
            "",
            "<b>기준</b>",
            "• USD/KRW: 일간 ±20원 또는 ±1%, 1,400원 상향·1,350원 하향 통과",
            "• KOSPI 외국인: 1일 ±1조원 또는 3거래일 누적 ±3조원",
            "• 미국 10년물: 일간 ±10bp",
            "• 한미 정책금리차: 이전 감시값 대비 ±25bp",
            "• BofA Global Wave: 독점지표 수치 추정 금지, 방향 전환 관련 신규 공개자료만 감지",
            "• 하이퍼스케일러 AI 설비투자: ±10% 이상 수치가 명시된 신규자료",
            "",
            "<b>원문</b>",
        ]
        used = set()
        for e in new_events:
            src = e.get("source") or ""
            if src and src not in used:
                used.add(src)
                lines.append("• " + html_link("원문", src))
        ALERT_PATH.write_text("\n".join(lines) + "\n", encoding="utf-8")

    status = [
        "# 한국 시장 스트레스·글로벌 사이클 감시", "",
        f"- 확인시각(KST): {now:%Y-%m-%d %H:%M:%S}",
        f"- 최초 기준선 설정: {'예' if first else '아니오'}",
        f"- 신규 알림 이벤트: {len(new_events)}개",
        f"- 조회 오류: {len(errors)}건",
    ]
    if fx:
        status.append(f"- USD/KRW: {fx['value']:,.1f}원, 일간 {fx['change_krw']:+,.1f}원 / {fx['change_pct']:+.2f}%")
    if u10:
        status.append(f"- 미국 10년물: {u10['value']:.2f}%, 일간 {u10['change_bp']:+.1f}bp")
    if flow:
        status.append(f"- KOSPI 외국인: 1일 {fmt_eok(flow['daily_krw'])}, 3거래일 {fmt_eok(flow['three_day_krw'])}")
    if spread:
        status.append(f"- 한미 정책금리차: 미국 {spread['fed_upper']:.2f}% - 한국 {spread['bok_base']:.2f}% = {spread['spread_pp']:.2f}%p")
    status.append(f"- BofA Global Wave 방향 관련 공개자료 후보: {len(current.get('global_wave_news', []))}건")
    status.append(f"- 하이퍼스케일러 AI 설비투자 ±10% 수치 후보: {len(current.get('hyperscaler_capex_news', []))}건")
    STATUS_PATH.write_text("\n".join(status) + "\n", encoding="utf-8")
    print(STATUS_PATH.read_text(encoding="utf-8"))
    if errors:
        print(ERROR_PATH.read_text(encoding="utf-8"))
    return 0 if len(current) > 1 else 2


if __name__ == "__main__":
    raise SystemExit(main())
