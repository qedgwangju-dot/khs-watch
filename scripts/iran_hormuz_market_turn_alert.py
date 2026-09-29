#!/usr/bin/env python3
"""이란·호르무즈 지정학 완화와 시장 확인 조건을 감시한다.

외부 패키지 없이 GitHub Actions에서 실행한다. 뉴스는 Google News RSS에서
신뢰 매체의 제목을 교차 확인하고, 시장 값은 Yahoo Finance 차트 엔드포인트를
사용한다. Telegram 전송은 워크플로가 담당하며 이 스크립트는 전송용 파일과
확정 후 반영할 상태 파일을 만든다.
"""

from __future__ import annotations

import argparse
import datetime as dt
import email.utils
import hashlib
import html
import json
import math
import os
import pathlib
import re
import time
import unicodedata
import urllib.error
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from dataclasses import asdict, dataclass
from zoneinfo import ZoneInfo

KST = ZoneInfo("Asia/Seoul")
UTC = dt.timezone.utc
OUT_DIR = pathlib.Path("out")
STATE_PATH = pathlib.Path("data/iran_hormuz_market_turn_state.json")
TITLE_PATH = OUT_DIR / "iran_hormuz_market_turn_title.txt"
BODY_PATH = OUT_DIR / "iran_hormuz_market_turn_alert.md"
ALERT_JSON_PATH = OUT_DIR / "iran_hormuz_market_turn_alert.json"
SUMMARY_PATH = OUT_DIR / "iran_hormuz_market_turn_watch.md"
PENDING_STATE_PATH = OUT_DIR / "iran_hormuz_market_turn_pending_state.json"
TELEGRAM_CONFIRMED_PATH = OUT_DIR / "iran_hormuz_market_turn_telegram_confirmed.json"

YAHOO_BASES = (
    "https://query1.finance.yahoo.com/v8/finance/chart",
    "https://query2.finance.yahoo.com/v8/finance/chart",
)

KPLER_STS_URL = (
    "https://www.kpler.com/blog/"
    "saudi-export-rerouting-amid-gulf-of-oman-sts-bottlenecks-amplify-vlcc-intensity-of-meg-flows"
)

NEWS_QUERIES = (
    'Iran ceasefire agreement OR Iran truce agreement OR "US Iran ceasefire" when:3d',
    'US ends attacks Iran OR US halts strikes Iran OR US ceases military operations Iran when:3d',
    '"Strait of Hormuz reopens" OR "shipping resumes" Hormuz OR "traffic returns to normal" Hormuz when:3d',
    '"Gulf oil exports" recover OR "Middle East oil exports" rebound OR "Saudi crude shipments" September when:3d',
    '"Middle East oil exports" "highest level since" Iran war Kpler when:3d',
    '"12.8 million barrels per day" Middle East exports Kpler when:3d',
    '"Hormuz" "7.4 million bpd" Kpler September when:3d',
    '"Saudi Arabia ramps up Gulf oil exports" OR "Aramco to boost Gulf exports" when:7d',
    '"Gulf of Oman" STS record OR "ship-to-ship" Oman Saudi crude when:7d',
    'Kpler "Gulf of Oman" STS bottlenecks VLCC when:7d',
    '"Hormuz oil shipments" six-month high OR "record oil" Hormuz when:7d',
    '"East-West Pipeline" 3.5 million barrels per day Saudi when:3d',
    '"East-West Pipeline" pumping 3.5 million bpd Yanbu when:3d',
    '"East-West Pipeline" 4 million bpd Yanbu Saudi when:3d',
    '"Yanbu" crude loadings resume East-West Pipeline when:3d',
    '"Middle East crude exports" 12.8 million bpd September Kpler Reuters when:3d',
    '"Hormuz" "80% of prewar" oil flows Kpler when:3d',
    '"Gulf crude" India 1.52 million bpd Kpler September when:7d',
    '"Saudi Arabia resumes oil exports" Yanbu East-West Pipeline when:3d',
    '"East-West pipeline starts exports" Saudi Yanbu when:3d',
    '"overseas shipments have now resumed" Saudi East-West Pipeline when:3d',
)

TRUSTED_SOURCE_ALIASES = (
    "reuters",
    "associated press",
    "ap news",
    "bloomberg",
    "bbc",
    "financial times",
    "the wall street journal",
    "wall street journal",
    "the new york times",
    "new york times",
    "cnn",
    "nbc news",
    "abc news",
    "cbs news",
    "the guardian",
    "al jazeera",
    "france 24",
    "afp",
    "the white house",
    "white house",
    "u.s. department of state",
    "us department of state",
    "u.s. department of defense",
    "us department of defense",
    "u.s. central command",
    "us central command",
    "centcom",
    "international maritime organization",
    "ukmto",
    "iranian foreign ministry",
    "iran ministry of foreign affairs",
    "연합뉴스",
    "로이터",
    "ap통신",
    "블룸버그",
    "bbc 코리아",
    "kpler",
    "vortexa",
    "saudi ministry of energy",
    "ministry of energy saudi arabia",
    "saudi aramco",
    "aramco",
)

NEGATIVE_OR_TENTATIVE_PHRASES = (
    "ceasefire hopes",
    "truce hopes",
    "peace hopes",
    "hopes for",
    "in hope of",
    "could agree",
    "may agree",
    "might agree",
    "possible agreement",
    "proposed ceasefire",
    "ceasefire proposal",
    "calls for ceasefire",
    "seeks ceasefire",
    "talks continue",
    "talks resume",
    "negotiations continue",
    "considering",
    "reportedly considering",
    "hold off",
    "held off",
    "pause attacks",
    "pause strikes",
    "temporarily halt",
    "temporary halt",
    "for now",
    "not yet",
    "no agreement",
    "deal elusive",
    "휴전 기대",
    "합의 기대",
    "협상 재개",
    "협상 중",
    "공격 보류",
    "일시 중단",
    "검토 중",
    "가능성",
)

EVENT_LABELS = {
    "ceasefire": "미국·이란의 최종 휴전·합의",
    "us_attack_end": "미국의 대이란 공격 중단 공식화",
    "hormuz_normalization": "호르무즈 해협의 실질적 통행 정상화",
    "oil_flow_recovery": "중동 원유 수출·호르무즈 물류 회복",
    "sts_reroute_expansion": "걸프오브오만 STS 우회 물류 급증·병목",
    "east_west_pipeline_recovery": "사우디 East-West Pipeline 실물 회복",
    "regional_export_recovery": "중동 원유 수출 회복 단계 상향",
    "india_gulf_import_recovery": "인도 걸프산 원유 유입 회복",
}
DATA_PROVIDER_ALIASES = ("kpler", "vortexa", "jodi")


@dataclass(frozen=True)
class NewsItem:
    title: str
    source: str
    link: str
    published_utc: str
    published_epoch: float
    event_kind: str


@dataclass(frozen=True)
class SymbolSpec:
    symbol: str
    label: str
    unit: str


@dataclass(frozen=True)
class Quote:
    symbol: str
    label: str
    unit: str
    price: float
    previous_close: float
    change: float
    change_pct: float
    timestamp_utc: str
    timestamp_epoch: float


SYMBOLS = {
    "us2y": SymbolSpec("^UST2Y", "미국 2년물 국채금리", "%"),
    "dxy": SymbolSpec("DX-Y.NYB", "달러인덱스", ""),
    "wti": SymbolSpec("CL=F", "WTI", "달러/배럴"),
    "brent": SymbolSpec("BZ=F", "Brent", "달러/배럴"),
}


def now_utc() -> dt.datetime:
    return dt.datetime.now(UTC)


def normalize_text(value: str) -> str:
    value = html.unescape(value or "")
    value = unicodedata.normalize("NFKC", value)
    value = re.sub(r"\s+", " ", value).strip().lower()
    return value


def finite_number(value: object) -> float | None:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) else None


def fetch_bytes(url: str, timeout: int = 20, attempts: int = 3) -> bytes:
    headers = {
        "Accept": "application/rss+xml, application/xml, text/xml, application/json;q=0.9, */*;q=0.8",
        "User-Agent": "Mozilla/5.0 iran-hormuz-market-turn-alert/1.0",
    }
    last_error: Exception | None = None
    for attempt in range(attempts):
        try:
            request = urllib.request.Request(url, headers=headers)
            with urllib.request.urlopen(request, timeout=timeout) as response:
                return response.read()
        except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError) as exc:
            last_error = exc
            if attempt + 1 < attempts:
                time.sleep(0.5 * (2**attempt))
    raise RuntimeError(f"요청 실패: {url} · {last_error}")


def fetch_json(url: str) -> dict:
    try:
        return json.loads(fetch_bytes(url).decode("utf-8"))
    except json.JSONDecodeError as exc:
        raise RuntimeError(f"JSON 해석 실패: {url} · {exc}") from exc


def source_is_trusted(source: str) -> bool:
    low = normalize_text(source)
    return any(alias in low for alias in TRUSTED_SOURCE_ALIASES)


def classify_event(title: str) -> str | None:
    low = normalize_text(title)
    if not low or any(phrase in low for phrase in NEGATIVE_OR_TENTATIVE_PHRASES):
        return None

    has_iran = "iran" in low or "이란" in low
    has_us = any(term in low for term in ("u.s.", "us ", "united states", "america", "미국"))

    ceasefire_phrases = (
        "agree to ceasefire",
        "agreed to ceasefire",
        "ceasefire agreed",
        "cease-fire agreed",
        "ceasefire agreement",
        "cease-fire agreement",
        "truce agreed",
        "truce agreement",
        "final agreement signed",
        "final deal signed",
        "peace deal signed",
        "ceasefire takes effect",
        "cease-fire takes effect",
        "최종 휴전 합의",
        "휴전 합의 체결",
        "휴전에 합의",
        "평화협정 체결",
        "최종 합의 체결",
    )
    if has_iran and any(phrase in low for phrase in ceasefire_phrases):
        return "ceasefire"

    attack_end_phrases = (
        "ends attacks on iran",
        "ends strikes on iran",
        "halts attacks on iran",
        "halts strikes on iran",
        "stops attacks on iran",
        "stops strikes on iran",
        "ceases attacks on iran",
        "ceases military operations against iran",
        "military operations against iran have ended",
        "officially ends iran strikes",
        "대이란 공격 종료",
        "이란 공격 공식 중단",
        "이란 공습 공식 종료",
        "대이란 군사작전 종료",
    )
    if has_iran and has_us and any(phrase in low for phrase in attack_end_phrases):
        return "us_attack_end"

    regional_export_phrases = (
        "middle east crude exports", "mideast oil exports", "middle east oil exports",
        "highest since the war", "highest since the iran war", "highest since february",
        "80% of prewar", "80% of pre-war", "prewar oil flow", "pre-war oil flow",
        "중동 원유 수출", "전쟁 이전 대비", "전쟁 전 대비",
    )
    if any(term in low for term in regional_export_phrases) and any(
        term in low for term in ("12.8 million", "12.8 mbd", "80% of prewar", "80% of pre-war", "전쟁 이전", "전쟁 전")
    ):
        return "regional_export_recovery"

    india_import_phrases = (
        "gulf crude imports to india", "gulf arrivals", "gulf oil supplies to india",
        "india imports from middle east", "india's middle east imports", "인도 걸프산", "인도 중동산",
    )
    if any(term in low for term in india_import_phrases) and any(
        term in low for term in ("1.52", "recover", "recovered", "surge", "rise", "회복", "증가")
    ):
        return "india_gulf_import_recovery"

    pipeline_export_resume_phrases = (
        "resumes oil exports",
        "resume oil exports",
        "starts exports after repairs",
        "starts exports",
        "export shipments resume",
        "shipments have now resumed",
        "overseas shipments have now resumed",
        "crude loadings resume",
        "loadings resume",
        "yanbu exports resume",
        "yanbu oil exports resume",
        "수출 재개",
        "선적 재개",
    )
    if (
        any(term in low for term in ("east-west pipeline", "east west pipeline", "yanbu", "petroline", "동서 송유관"))
        and any(term in low for term in pipeline_export_resume_phrases)
    ):
        return "east_west_pipeline_recovery"

    pipeline_recovery_phrases = (
        "east-west pipeline",
        "east west pipeline",
        "petroline",
        "yanbu pipeline",
        "동서 송유관",
        "east–west pipeline",
    )
    pipeline_rate_terms = (
        "million barrels per day", "million bpd", "mbd", "barrels per day",
        "pumping", "flow", "flows", "transport", "throughput", "수송", "송유",
    )
    pipeline_recovery_terms = (
        "restart", "restarted", "resumes", "resumed", "recovery", "hits", "reaches",
        "rises to", "back to", "building up", "increase", "재가동", "회복", "증가",
    )
    if (
        any(term in low for term in pipeline_recovery_phrases)
        and any(term in low for term in pipeline_rate_terms)
        and any(term in low for term in pipeline_recovery_terms)
    ):
        return "east_west_pipeline_recovery"

    flow_recovery_phrases = (
        "ramps up gulf oil exports",
        "boost gulf exports",
        "oil shipments hit six-month high",
        "oil shipments hit a six-month high",
        "highest during the iran war",
        "highest since the iran war",
        "exports recover",
        "exports recovered",
        "export recovery",
        "oil flows rise",
        "oil flows through the strait",
        "middle east exports",
        "gulf oil exports",
        "saudi crude shipments",
        "사우디 원유 수출 회복",
        "걸프 원유 수출 회복",
        "호르무즈 원유 통과 증가",
    )
    if any(phrase in low for phrase in flow_recovery_phrases) and any(
        term in low for term in ("oil", "crude", "barrel", "export", "shipment", "원유", "석유", "수출")
    ):
        return "oil_flow_recovery"

    sts_phrases = (
        "ship-to-ship",
        "ship to ship",
        "sts bottleneck",
        "sts volumes",
        "sts activity",
        "sts transfers",
        "lightering",
        "shuttle trades",
        "gulf of oman",
        "sohar",
        "오만만",
        "선박 간 이송",
    )
    sts_change = (
        "record", "surge", "surged", "rises", "rose", "capacity", "bottleneck",
        "rerouting", "reroute", "boost", "increase", "급증", "기록", "병목", "우회",
    )
    if any(term in low for term in sts_phrases) and any(term in low for term in sts_change):
        return "sts_reroute_expansion"

    hormuz_phrases = (
        "strait of hormuz reopens",
        "hormuz strait reopens",
        "shipping resumes through the strait of hormuz",
        "shipping resumes in the strait of hormuz",
        "traffic returns to normal in the strait of hormuz",
        "hormuz traffic returns to normal",
        "normal transit resumes through hormuz",
        "full passage restored through hormuz",
        "navigation restored in hormuz",
        "호르무즈 해협 통항 정상화",
        "호르무즈 해협 운항 재개",
        "호르무즈 해협 선박 통행 정상화",
        "호르무즈 해협 재개방",
    )
    if ("hormuz" in low or "호르무즈" in low) and any(phrase in low for phrase in hormuz_phrases):
        return "hormuz_normalization"
    return None


def parse_rss(payload: bytes, current: dt.datetime, max_age_hours: int) -> list[NewsItem]:
    try:
        root = ET.fromstring(payload)
    except ET.ParseError as exc:
        raise RuntimeError(f"RSS 해석 실패: {exc}") from exc

    cutoff = current.timestamp() - max_age_hours * 3600
    results: list[NewsItem] = []
    for node in root.findall(".//item"):
        title = (node.findtext("title") or "").strip()
        link = (node.findtext("link") or "").strip()
        source_node = node.find("source")
        source = (source_node.text if source_node is not None and source_node.text else "").strip()
        if not source and " - " in title:
            source = title.rsplit(" - ", 1)[-1].strip()
        published_raw = (node.findtext("pubDate") or "").strip()
        try:
            published = email.utils.parsedate_to_datetime(published_raw)
            if published.tzinfo is None:
                published = published.replace(tzinfo=UTC)
            published = published.astimezone(UTC)
        except (TypeError, ValueError, OverflowError):
            continue
        if published.timestamp() < cutoff or published.timestamp() > current.timestamp() + 600:
            continue
        event_kind = classify_event(title)
        if not event_kind or not source_is_trusted(source):
            continue
        results.append(
            NewsItem(
                title=title,
                source=source,
                link=link,
                published_utc=published.isoformat().replace("+00:00", "Z"),
                published_epoch=published.timestamp(),
                event_kind=event_kind,
            )
        )
    return results


def google_news_url(query: str) -> str:
    params = urllib.parse.urlencode({"q": query, "hl": "en-US", "gl": "US", "ceid": "US:en"})
    return f"https://news.google.com/rss/search?{params}"


def _visible_text(raw_html: str) -> str:
    text = re.sub(r"(?is)<script\b.*?</script>|<style\b.*?</style>", " ", raw_html)
    text = re.sub(r"(?s)<[^>]+>", " ", text)
    return re.sub(r"\s+", " ", html.unescape(text)).strip()


def parse_kpler_sts_snapshot(raw_html: str, current: dt.datetime) -> NewsItem:
    text = _visible_text(raw_html)
    record = re.search(
        r"September\s+(\d{1,2})\s+to\s+date\s+currently\s+tracking\s+at\s+a\s+record\s+([0-9.]+)\s*Mbd",
        text,
        flags=re.I,
    )
    since_war = re.search(
        r"average\s+of\s+([0-9.]+)\s*Mbd\s+since\s+the\s+US-Iran\s+war",
        text,
        flags=re.I,
    )
    baseline = re.search(
        r"from\s+just\s+([0-9.]+)\s*Mbd\s+in\s+2025",
        text,
        flags=re.I,
    )
    vlcc = re.search(
        r"3\s*Mbd\s+of\s+Saudi\s+crude.*?between\s+(\d+)\s+and\s+(\d+)\s+additional\s+VLCCs",
        text,
        flags=re.I,
    )
    if not record or not since_war or not baseline:
        raise RuntimeError("Kpler STS snapshot metrics not found")
    day = int(record.group(1))
    record_mbd = float(record.group(2))
    since_war_mbd = float(since_war.group(1))
    baseline_mbd = float(baseline.group(1))
    year = current.astimezone(KST).year
    source_date = dt.date(year, 9, day)
    if source_date > current.astimezone(KST).date() + dt.timedelta(days=1):
        raise RuntimeError(f"Kpler STS source date in future: {source_date}")
    vlcc_text = f"; Saudi 3 Mbd requires {vlcc.group(1)}-{vlcc.group(2)} additional VLCCs" if vlcc else ""
    title = (
        f"Kpler Gulf of Oman STS record {record_mbd:.1f} Mbd as of {source_date.isoformat()}; "
        f"since-war average {since_war_mbd:.1f} Mbd; 2025 average {baseline_mbd:.2f} Mbd"
        f"{vlcc_text}"
    )
    return NewsItem(
        title=title,
        source="Kpler",
        link=KPLER_STS_URL,
        published_utc=current.isoformat().replace("+00:00", "Z"),
        published_epoch=current.timestamp(),
        event_kind="sts_reroute_expansion",
    )


def fetch_news(current: dt.datetime) -> tuple[list[NewsItem], list[str]]:
    max_age_hours = int(os.getenv("IRAN_HORMUZ_MAX_NEWS_AGE_HOURS", "72"))
    items: list[NewsItem] = []
    errors: list[str] = []
    for query in NEWS_QUERIES:
        try:
            items.extend(parse_rss(fetch_bytes(google_news_url(query)), current, max_age_hours))
        except Exception as exc:
            errors.append(str(exc))

    try:
        kpler_html = fetch_bytes(KPLER_STS_URL).decode("utf-8", errors="replace")
        items.append(parse_kpler_sts_snapshot(kpler_html, current))
    except Exception as exc:
        errors.append(f"Kpler STS direct: {type(exc).__name__}: {exc}")

    unique: dict[tuple[str, str, str], NewsItem] = {}
    for item in items:
        key = (normalize_text(item.source), normalize_text(item.title), item.event_kind)
        unique[key] = item
    return sorted(unique.values(), key=lambda item: item.published_epoch, reverse=True), errors


def confirm_event(items: list[NewsItem], minimum_sources: int = 2) -> tuple[str, list[NewsItem]] | None:
    by_kind: dict[str, list[NewsItem]] = {}
    for item in items:
        by_kind.setdefault(item.event_kind, []).append(item)

    candidates: list[tuple[float, str, list[NewsItem]]] = []
    for kind, rows in by_kind.items():
        source_rows: dict[str, NewsItem] = {}
        for row in sorted(rows, key=lambda item: item.published_epoch, reverse=True):
            source_rows.setdefault(normalize_text(row.source), row)
        selected = list(source_rows.values())
        has_primary_data = kind in ("oil_flow_recovery", "sts_reroute_expansion") and any(
            any(alias in normalize_text(row.source) for alias in DATA_PROVIDER_ALIASES)
            for row in selected
        )
        regional_primary = kind in ("regional_export_recovery", "india_gulf_import_recovery") and any(
            any(alias in normalize_text(row.source) for alias in ("kpler", "reuters"))
            for row in selected
        )
        pipeline_official = kind == "east_west_pipeline_recovery" and any(
            any(alias in normalize_text(row.source) for alias in (
                "saudi ministry of energy", "ministry of energy saudi arabia",
                "saudi aramco", "aramco"
            ))
            for row in selected
        )
        pipeline_cross_checked = len(selected) >= minimum_sources
        if (
            len(selected) >= minimum_sources
            or has_primary_data
            or regional_primary
            or (pipeline_official and pipeline_cross_checked)
        ):
            candidates.append((max(row.published_epoch for row in selected), kind, selected))
    if not candidates:
        return None
    _, kind, selected = max(candidates, key=lambda value: value[0])
    return kind, sorted(selected, key=lambda item: item.published_epoch, reverse=True)[:3]


def last_finite_point(timestamps: list, closes: list) -> tuple[float, float] | None:
    for timestamp, close in reversed(list(zip(timestamps, closes))):
        ts_value = finite_number(timestamp)
        close_value = finite_number(close)
        if ts_value is not None and close_value is not None:
            return ts_value, close_value
    return None


def parse_yahoo_payload(payload: dict, spec: SymbolSpec) -> Quote:
    chart = payload.get("chart") or {}
    results = chart.get("result") or []
    if not results:
        error = chart.get("error") or {}
        raise RuntimeError(f"{spec.symbol} 데이터 없음: {error.get('description', 'unknown')}")
    result = results[0]
    meta = result.get("meta") or {}
    timestamps = result.get("timestamp") or []
    quote_rows = (result.get("indicators") or {}).get("quote") or []
    closes = quote_rows[0].get("close", []) if quote_rows else []
    last_point = last_finite_point(timestamps, closes)

    price = finite_number(meta.get("regularMarketPrice"))
    if price is None and last_point:
        price = last_point[1]
    previous_close = (
        finite_number(meta.get("chartPreviousClose"))
        or finite_number(meta.get("previousClose"))
        or finite_number(meta.get("regularMarketPreviousClose"))
    )
    timestamp = finite_number(meta.get("regularMarketTime"))
    if timestamp is None and last_point:
        timestamp = last_point[0]
    if price is None or previous_close is None or previous_close == 0 or timestamp is None:
        raise RuntimeError(f"{spec.symbol} 핵심 값 누락")

    observed = dt.datetime.fromtimestamp(timestamp, tz=UTC)
    change = price - previous_close
    return Quote(
        symbol=spec.symbol,
        label=spec.label,
        unit=spec.unit,
        price=price,
        previous_close=previous_close,
        change=change,
        change_pct=(change / previous_close) * 100,
        timestamp_utc=observed.isoformat().replace("+00:00", "Z"),
        timestamp_epoch=timestamp,
    )


def fetch_quote(spec: SymbolSpec) -> Quote:
    params = urllib.parse.urlencode(
        {
            "interval": os.getenv("IRAN_HORMUZ_YAHOO_INTERVAL", "5m"),
            "range": os.getenv("IRAN_HORMUZ_YAHOO_RANGE", "5d"),
            "includePrePost": "true",
            "events": "div,splits",
        }
    )
    errors: list[str] = []
    for base in YAHOO_BASES:
        url = f"{base}/{urllib.parse.quote(spec.symbol, safe='')}?{params}"
        try:
            return parse_yahoo_payload(fetch_json(url), spec)
        except Exception as exc:
            errors.append(str(exc))
    raise RuntimeError(f"{spec.symbol} 조회 실패: {' | '.join(errors)}")


def age_minutes(quote: Quote, current: dt.datetime) -> float:
    return max(0.0, (current.timestamp() - quote.timestamp_epoch) / 60.0)


def quote_is_fresh(quote: Quote, current: dt.datetime, max_age_minutes: int) -> bool:
    return age_minutes(quote, current) <= max_age_minutes


def market_confirms(us2y: Quote, dxy: Quote) -> bool:
    return us2y.price < us2y.previous_close and dxy.price < dxy.previous_close


def load_state(path: pathlib.Path = STATE_PATH) -> dict:
    if not path.exists():
        return {"last_alert_at_kst": None, "last_event_kind": None, "last_event_id": None}
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
        return value if isinstance(value, dict) else {}
    except (OSError, json.JSONDecodeError):
        return {"last_alert_at_kst": None, "last_event_kind": None, "last_event_id": None}


def event_id(kind: str, rows: list[NewsItem]) -> str:
    combined = " ".join(normalize_text(row.title) for row in rows)
    if kind == "regional_export_recovery":
        values = [
            float(value)
            for value in re.findall(
                r"\b([0-9]+(?:\.[0-9]+)?)\s*(?:million\s+(?:barrels\s+per\s+day|bpd)|mbd)\b",
                combined,
                flags=re.I,
            )
        ]
        max_value = max(values) if values else 0.0
        if max_value >= 12.5:
            band = "12_5plus"
        elif max_value >= 10.0:
            band = "10plus"
        else:
            band = "recovery"
        prewar = "prewar80" if ("80% of prewar" in combined or "80% of pre-war" in combined) else "no80"
        digest = hashlib.sha256(f"{kind}|{band}|{prewar}".encode("utf-8")).hexdigest()[:16]
        return f"{kind}:{digest}"
    if kind == "india_gulf_import_recovery":
        digest = hashlib.sha256(f"{kind}|1_52_mbd".encode("utf-8")).hexdigest()[:16]
        return f"{kind}:{digest}"
    if kind == "regional_export_recovery":
        lines.extend([
            "중동 주요 산유국 원유 수출이 전쟁 이후 최고 수준으로 회복됐습니다.",
            "→ 그러나 12.8 Mbd는 2월 18.8 Mbd보다 약 6 Mbd 낮아 '전쟁 전 정상화'로 부르면 안 됩니다.",
            "→ 호르무즈·우회로·재고방출을 합친 회복과 실제 생산능력 정상화는 분리해서 봅니다.",
        ])
    elif kind == "india_gulf_import_recovery":
        lines.extend([
            "걸프산 원유가 인도 같은 최종 수요처까지 다시 도착하는 흐름이 강해지고 있습니다.",
            "→ 공급망 회복의 말단 확인 신호지만 2025 평균 2.24 Mbd와 비교하면 아직 완전 정상화는 아닙니다.",
            "→ 러시아산 감소와 걸프산 대체가 동시에 진행되는지 확인합니다.",
        ])
    elif kind == "east_west_pipeline_recovery":
        exports_resumed = any(
            phrase in combined
            for phrase in (
                "resumes oil exports", "resume oil exports", "starts exports after repairs",
                "starts exports", "export shipments resume", "shipments have now resumed",
                "overseas shipments have now resumed", "crude loadings resume",
                "loadings resume", "yanbu exports resume", "수출 재개", "선적 재개",
            )
        )
        rates = [
            float(value)
            for value in re.findall(
                r"\b([0-9]+(?:\.[0-9]+)?)\s*(?:million\s+(?:barrels\s+per\s+day|bpd)|mbd)\b",
                combined,
                flags=re.I,
            )
        ]
        rate = max(rates) if rates else 0.0
        if exports_resumed:
            band = "export_resume"
        elif rate >= 4.0:
            band = "4plus"
        elif rate >= 3.5:
            band = "3_5"
        elif rate >= 3.0:
            band = "3_0"
        else:
            band = "restart"
        yanbu = "yanbu" if "yanbu" in combined else "no_yanbu"
        digest = hashlib.sha256(f"{kind}|{band}|{yanbu}".encode("utf-8")).hexdigest()[:16]
        return f"{kind}:{digest}"
    if kind in (
        "oil_flow_recovery", "sts_reroute_expansion", "east_west_pipeline_recovery",
        "regional_export_recovery", "india_gulf_import_recovery"
    ):
        markers = []
        marker_terms = (
            ("saudi_export_ramp", ("saudi", "aramco", "ras tanura")),
            ("hormuz_flow_high", ("hormuz", "six-month high", "record oil")),
            ("sts_record", ("ship-to-ship", "ship to ship", "sts", "gulf of oman")),
            ("sohar_reroute", ("sohar", "oman")),
            ("yanbu_restart", ("yanbu", "east-west pipeline", "east west pipeline")),
            ("vlcc_bottleneck", ("vlcc", "bottleneck", "capacity")),
        )
        def marker_match(term: str) -> bool:
            if term.isalnum() and len(term) <= 4:
                return re.search(rf"\b{re.escape(term)}\b", combined) is not None
            return term in combined

        for name, terms in marker_terms:
            if any(marker_match(term) for term in terms):
                markers.append(name)
        volumes = [
            float(value)
            for value in re.findall(r"\b([0-9]+(?:\.[0-9]+)?)\s*mbd\b", combined, flags=re.I)
        ]
        if volumes:
            max_volume = max(volumes)
            if kind == "sts_reroute_expansion":
                markers.append(f"sts_mbd_{int(max_volume)}")
            else:
                markers.append(f"flow_mbd_{int(max_volume)}")
        if not markers:
            markers = [kind]
        digest = hashlib.sha256(f"{kind}|{'|'.join(sorted(set(markers)))}".encode("utf-8")).hexdigest()[:16]
        return f"{kind}:{digest}"
    day = dt.datetime.fromtimestamp(max(row.published_epoch for row in rows), tz=UTC).astimezone(KST).date().isoformat()
    sources = ",".join(sorted(normalize_text(row.source) for row in rows))
    digest = hashlib.sha256(f"{kind}|{day}|{sources}".encode("utf-8")).hexdigest()[:16]
    return f"{kind}:{day}:{digest}"


def cooldown_active(state: dict, current: dt.datetime, hours: int = 24) -> bool:
    raw = state.get("last_alert_at_kst")
    if not raw:
        return False
    try:
        previous = dt.datetime.fromisoformat(str(raw))
        if previous.tzinfo is None:
            previous = previous.replace(tzinfo=KST)
    except ValueError:
        return False
    return (current.astimezone(KST) - previous.astimezone(KST)).total_seconds() < hours * 3600


def clean_outputs() -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    for path in (
        TITLE_PATH,
        BODY_PATH,
        ALERT_JSON_PATH,
        PENDING_STATE_PATH,
        TELEGRAM_CONFIRMED_PATH,
    ):
        path.unlink(missing_ok=True)


def fmt_signed(value: float, digits: int = 2, suffix: str = "") -> str:
    sign = "+" if value > 0 else ""
    return f"{sign}{value:.{digits}f}{suffix}"


def fmt_quote_line(quote: Quote) -> str:
    if quote.symbol == "^UST2Y":
        bp = quote.change * 100
        direction = "하락" if quote.change < 0 else "상승" if quote.change > 0 else "보합"
        return (
            f"- {quote.label}: {quote.price:.3f}% (전 거래일 {quote.previous_close:.3f}%, "
            f"{fmt_signed(bp, 1, 'bp')}, {direction})"
        )
    if quote.symbol == "DX-Y.NYB":
        direction = "하락" if quote.change < 0 else "상승" if quote.change > 0 else "보합"
        return (
            f"- {quote.label}: {quote.price:.2f} (전 거래일 {quote.previous_close:.2f}, "
            f"{fmt_signed(quote.change_pct, 2, '%')}, {direction})"
        )
    direction = "하락" if quote.change < 0 else "상승" if quote.change > 0 else "보합"
    return (
        f"- {quote.label}: ${quote.price:.2f}/배럴 (전 거래일 ${quote.previous_close:.2f}, "
        f"{fmt_signed(quote.change_pct, 2, '%')}, {direction})"
    )


def _extract_kpler_sts_metrics(news_rows: list[NewsItem]) -> dict[str, object] | None:
    for row in news_rows:
        if "kpler" not in normalize_text(row.source):
            continue
        title = str(row.title or "")
        match = re.search(
            r"STS record\s+([0-9.]+)\s+Mbd\s+as of\s+(\d{4}-\d{2}-\d{2});\s*"
            r"since-war average\s+([0-9.]+)\s+Mbd;\s*"
            r"2025 average\s+([0-9.]+)\s+Mbd"
            r"(?:;\s*Saudi\s+([0-9.]+)\s+Mbd\s+requires\s+(\d+)-(\d+)\s+additional VLCCs)?",
            title,
            flags=re.I,
        )
        if not match:
            continue
        current = float(match.group(1))
        since_war = float(match.group(3))
        baseline_2025 = float(match.group(4))
        return {
            "current_mbd": current,
            "source_date": match.group(2),
            "since_war_mbd": since_war,
            "baseline_2025_mbd": baseline_2025,
            "vs_war_avg": current / since_war if since_war else None,
            "vs_2025_avg": current / baseline_2025 if baseline_2025 else None,
            "saudi_increment_mbd": float(match.group(5)) if match.group(5) else None,
            "vlcc_low": int(match.group(6)) if match.group(6) else None,
            "vlcc_high": int(match.group(7)) if match.group(7) else None,
            "link": row.link,
        }
    return None


def _extract_pipeline_rate(news_rows: list[NewsItem]) -> tuple[float | None, bool]:
    rates: list[float] = []
    yanbu = False
    for row in news_rows:
        title = str(row.title or "")
        low = normalize_text(title)
        if "yanbu" in low:
            yanbu = True
        for value in re.findall(
            r"\b([0-9]+(?:\.[0-9]+)?)\s*(?:million\s+(?:barrels\s+per\s+day|bpd)|mbd)\b",
            low,
            flags=re.I,
        ):
            try:
                rate = float(value)
            except ValueError:
                continue
            if 0.5 <= rate <= 10.0:
                rates.append(rate)
    return (max(rates) if rates else None, yanbu)


def _pipeline_exports_resumed(news_rows: list[NewsItem]) -> bool:
    phrases = (
        "resumes oil exports", "resume oil exports", "starts exports after repairs",
        "starts exports", "export shipments resume", "shipments have now resumed",
        "overseas shipments have now resumed", "crude loadings resume",
        "loadings resume", "yanbu exports resume", "수출 재개", "선적 재개",
    )
    text = " ".join(normalize_text(row.title) for row in news_rows)
    return any(phrase in text for phrase in phrases)


def _extract_regional_export_metrics(news_rows: list[NewsItem]) -> dict[str, float | None]:
    text = " ".join(normalize_text(row.title) for row in news_rows)
    def find_value(pattern: str):
        m = re.search(pattern, text, flags=re.I)
        return float(m.group(1)) if m else None
    current = find_value(r"(?:middle east|mideast).*?([0-9]+(?:\.[0-9]+)?)\s*(?:million\s+bpd|million\s+barrels\s+per\s+day|mbd)")
    feb = find_value(r"(?:february|prewar|pre-war).*?([0-9]+(?:\.[0-9]+)?)\s*(?:million\s+bpd|million\s+barrels\s+per\s+day|mbd)")
    hormuz = find_value(r"hormuz.*?([0-9]+(?:\.[0-9]+)?)\s*(?:million\s+bpd|million\s+barrels\s+per\s+day|mbd)")
    return {"current_mbd": current, "feb_mbd": feb, "hormuz_mbd": hormuz}


def _extract_india_gulf_metrics(news_rows: list[NewsItem]) -> dict[str, float | None]:
    text = " ".join(normalize_text(row.title) for row in news_rows)
    nums = [float(v) for v in re.findall(r"\b([0-9]+(?:\.[0-9]+)?)\s*(?:mb/d|mbd|million\s+bpd)", text)]
    current = max(nums) if nums else None
    return {"current_mbd": current}


def build_physical_flow_alert_body(
    kind: str,
    news_rows: list[NewsItem],
    oil: Quote | None,
    current: dt.datetime,
) -> str:
    metrics = _extract_kpler_sts_metrics(news_rows)
    lines = [
        current.astimezone(KST).strftime("%Y년 %m월 %d일 %H:%M KST"),
        "",
        "[한눈에]",
    ]

    pipeline_rate, pipeline_yanbu = _extract_pipeline_rate(news_rows)
    pipeline_exports_resumed = _pipeline_exports_resumed(news_rows)
    regional = _extract_regional_export_metrics(news_rows)
    india_gulf = _extract_india_gulf_metrics(news_rows)

    if kind == "regional_export_recovery":
        lines.append("중동 수출     전쟁 후 최고 수준")
        lines.append("핵심 수치     12.8 Mbd · Reuters/Kpler")
        lines.append("비교          2월 18.8 Mbd보다 약 6.0 Mbd 낮음")
        lines.append("해석          회복은 맞지만 전쟁 전 완전 정상화는 아님")
    elif kind == "india_gulf_import_recovery":
        lines.append("인도 유입     걸프산 1.52 Mbd")
        lines.append("비교          6월 1.03 → 8월 1.18 → 9월 1.52 Mbd")
        lines.append("해석          아시아 실수요처까지 물량 회복이 연결되는지 확인")
    elif kind == "east_west_pipeline_recovery":
        if pipeline_rate is not None:
            lines.append(f"East-West     {pipeline_rate:.1f} Mbd")
            lines.append(f"vs 4Mbd      약 {pipeline_rate / 4.0 * 100:.0f}% 회복")
            lines.append(f"vs 7Mbd      명목 용량의 약 {pipeline_rate / 7.0 * 100:.0f}%")
        else:
            lines.append("East-West     재가동·유량 회복 확인")
        if pipeline_exports_resumed:
            lines.append("Yanbu 수출     재개 확인")
        elif pipeline_yanbu:
            lines.append("Yanbu         기사 내 직접 언급 · 선적 재개 여부 추가 확인")
        else:
            lines.append("Yanbu 수출     실제 선적 별도 확인 필요")
    elif kind == "sts_reroute_expansion" and metrics:
        lines.append("원유 공급     회복 ↑")
        lines.append("물류 효율     병목 심화 ↓")
        lines.append(
            f"GoO STS       {float(metrics['current_mbd']):.1f} Mbd · "
            f"전쟁 후 평균 {float(metrics['since_war_mbd']):.1f} · "
            f"2025 평균 {float(metrics['baseline_2025_mbd']):.2f}"
        )
        if metrics.get("vs_war_avg") is not None and metrics.get("vs_2025_avg") is not None:
            lines.append(
                f"현재 강도     전쟁 후 평균의 {float(metrics['vs_war_avg']):.1f}배 · "
                f"2025 평균의 {float(metrics['vs_2025_avg']):.0f}배"
            )
        if metrics.get("vlcc_low") is not None:
            lines.append(
                f"VLCC 수요     Saudi +{float(metrics['saudi_increment_mbd']):.0f} Mbd 처리 시 "
                f"+{int(metrics['vlcc_low'])}~{int(metrics['vlcc_high'])}척"
            )
        lines.append(f"기준일        {metrics['source_date']} · Kpler")
    else:
        lines.append(f"변화          {EVENT_LABELS[kind]}")

    if oil is not None:
        direction = "↓" if oil.change < 0 else "↑" if oil.change > 0 else "→"
        lines.append(
            f"Brent         USD {oil.price:.2f}/배럴 · {oil.change_pct:+.2f}% {direction}"
        )

    lines.extend(["", "[핵심 의미]"])
    if kind == "regional_export_recovery":
        lines.extend([
            "중동 주요 산유국의 원유 수출이 전쟁 이후 최고 수준으로 올라왔습니다.",
            "→ Reuters/Kpler 기준 9월 12.8 Mbd로 회복했지만 2월 18.8 Mbd보다 약 6.0 Mbd 낮습니다.",
            "→ 따라서 '공급 회복'은 맞지만 '전쟁 전 완전 정상화'로 부르면 안 됩니다.",
        ])
    elif kind == "india_gulf_import_recovery":
        lines.extend([
            "걸프산 원유가 인도 같은 최종 수요처까지 다시 도착하는 흐름이 강해지고 있습니다.",
            "→ 6월 1.03 → 8월 1.18 → 9월 1.52 Mbd로 회복했습니다.",
            "→ 다만 2025 평균 2.24 Mbd보다 낮아 완전 정상화는 아닙니다.",
        ])
    elif kind == "east_west_pipeline_recovery":
        lines.extend([
            "East-West Pipeline 유량 회복은 호르무즈를 우회하는 Red Sea 공급축이 되살아나는 신호입니다.",
            "→ 3.5Mbd가 확인되면 Reuters가 언급한 전쟁 전후 우회 운송 약 4Mbd의 약 88% 수준입니다.",
            (
                "→ Yanbu 해외 선적 재개가 확인돼 송유관 회복이 실제 수출로 연결되기 시작했습니다."
                if pipeline_exports_resumed
                else "→ 다만 송유관 내부 유량과 Yanbu 실제 선적은 다릅니다. 선적 재개 확인 전 수출 정상화로 단정하지 않습니다."
            ),
        ])
    elif kind == "oil_flow_recovery":
        lines.extend([
            "원유는 다시 시장에 나오고 있습니다.",
            "다만 호르무즈가 전쟁 이전처럼 정상화됐다는 뜻은 아닙니다.",
            "→ 공급량 회복은 유가 하방, 우회 물류 지속은 운임 상방 요인입니다.",
        ])
    else:
        lines.extend([
            "원유는 다시 나오지만 정상 항로 회복이 아니라 GoO STS 우회로 빼내는 중입니다.",
            "→ 유가에는 하방 압력, VLCC 운임·물류비에는 상방 압력이 동시에 생길 수 있습니다.",
            "→ '수출 회복'과 '물류 정상화'를 같은 의미로 보면 안 됩니다.",
        ])

    lines.extend(["", "[병목]"])
    if kind == "regional_export_recovery":
        lines.extend([
            "1) 호르무즈 실제 통과량이 회복세를 유지하는지",
            "2) Ras Tanura·Yanbu 양쪽 선적이 동시에 유지되는지",
            "3) GoO STS 비용과 VLCC 운임이 낮아지는지",
            "4) 이란·후티 공격 재개로 우회망이 다시 흔들리는지",
        ])
    elif kind == "india_gulf_import_recovery":
        lines.extend([
            "1) 인도 도착 기준 1.52 Mbd가 월말까지 유지되는지",
            "2) Iraq·UAE·Kuwait·Saudi 물량 회복이 지속되는지",
            "3) STS·운임·보험 비용이 구매단가를 다시 끌어올리는지",
            "4) 러시아산 감소를 걸프산이 얼마나 대체하는지",
        ])
    elif kind == "east_west_pipeline_recovery":
        lines.extend([
            "1) 손상 펌핑스테이션 우회·복구 안정성",
            "2) Yanbu 저장탱크 재충전",
            "3) Yanbu 실제 탱커 선적 재개",
            "4) Red Sea·Bab el-Mandeb 통항 위험",
        ])
    elif kind == "sts_reroute_expansion":
        lines.extend([
            "1) Fujairah·Sohar 육상 지원능력 한계",
            "2) STS 작업 슬롯·예인선·파일럿·검사 처리능력",
            "3) VLCC 회전율 저하",
            "4) 한계 초과 시 서인도 → 말레이시아로 이송거리 확대",
            "Kpler 시나리오: 말레이시아까지 밀리면 최대 58척 수준의 VLCC가 필요할 수 있음",
        ])
    else:
        lines.extend([
            "1) 호르무즈 실제 통과량",
            "2) Ras Tanura 선적 지속 여부",
            "3) Yanbu·East-West Pipeline 복구 속도",
            "4) 보험·VLCC 운임",
        ])

    lines.extend(["", "[다음 체크]"])
    lines.extend([
        "호르무즈 실제 통과량",
        "Saudi Gulf / Red Sea 선적량",
        "GoO STS 7일 평균과 신규 최고치",
        "East-West Pipeline 유량 3.0 → 3.5 → 4.0 Mbd",
        "Yanbu 실제 선적 재개",
        "Fujairah·Sohar 병목",
        "VLCC 운임·가용선복",
        "Brent",
    ])

    lines.extend(["", "[근거]"])
    for row in news_rows[:3]:
        published = dt.datetime.fromtimestamp(row.published_epoch, tz=UTC).astimezone(KST)
        if "kpler" in normalize_text(row.source) and metrics:
            lines.append(
                f"Kpler · STS {float(metrics['current_mbd']):.1f} Mbd 기록 · "
                f"전쟁 후 평균 {float(metrics['since_war_mbd']):.1f} · "
                f"2025 평균 {float(metrics['baseline_2025_mbd']):.2f}"
            )
        else:
            lines.append(f"{row.source} · {published:%m-%d %H:%M KST} · {row.title}")
        if row.link:
            lines.append(f"원문: {row.link}")

    lines.extend(["", "[주의]"])
    lines.append("STS는 같은 배럴이 여러 번 이송될 수 있어 호르무즈 통과량·중동 전체 수출량과 합산하지 않습니다.")
    lines.append("정책 발언 처리: 대통령·정부 발언은 참고만 하고, 실물 물량·통항 데이터 없이 '정상화'로 판정하지 않습니다.")

    return "\n".join(lines).strip() + "\n"



def build_alert_body(
    kind: str,
    news_rows: list[NewsItem],
    us2y: Quote,
    dxy: Quote,
    oil: Quote | None,
    current: dt.datetime,
) -> str:
    lines = [
        current.astimezone(KST).strftime("%Y년 %m월 %d일 %H:%M KST"),
        "",
        f"확정 사건: {EVENT_LABELS[kind]}",
        "교차 확인:",
    ]
    for row in news_rows[:3]:
        published = dt.datetime.fromtimestamp(row.published_epoch, tz=UTC).astimezone(KST)
        lines.append(f"- {row.source} · {published:%m-%d %H:%M KST} · {row.title}")
    lines.extend(
        [
            "",
            "시장 확인:",
            fmt_quote_line(us2y),
            fmt_quote_line(dxy),
        ]
    )
    if oil is not None:
        lines.append(fmt_quote_line(oil))
    lines.extend(
        [
            "",
            "주식시장 의미:",
            "- 돈 버는 능력: 유가·운임 완화 시 항공·화학·운송 원가에는 우호적이고 정유·방산 위험프리미엄에는 역풍입니다.",
            "- 할인율: 미국 2년물과 달러가 함께 내려 성장주·고베타 자산의 할인율 부담이 낮아지는 방향입니다.",
            "- 수급: 지정학적 위험회피 포지션의 되돌림과 외국인 위험자산 재유입 가능성이 커집니다.",
            "- 시간표: 합의 이행, 공격 재개 여부, 선박 통행량의 지속성을 추가 확인해야 합니다.",
            "",
            "실패 경로: 합의 파기·공격 재개·통항 재차 차질 또는 2년물·달러 반등이 나타나면 완화 신호가 되돌려질 수 있습니다.",
        ]
    )
    return "\n".join(lines).strip() + "\n"


def write_summary(lines: list[str]) -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    SUMMARY_PATH.write_text("\n".join(lines).strip() + "\n", encoding="utf-8")


def create_test_alert(current: dt.datetime) -> None:
    TITLE_PATH.write_text("이란·호르무즈 시장 전환 Telegram 연결 시험\n", encoding="utf-8")
    BODY_PATH.write_text(
        current.astimezone(KST).strftime("%Y년 %m월 %d일 %H:%M KST")
        + "\n\n@hs8879887988798879_bot 연결 시험입니다. 실제 조건 알림이 아닙니다.\n",
        encoding="utf-8",
    )
    ALERT_JSON_PATH.write_text(
        json.dumps({"test_mode": True, "created_at_kst": current.astimezone(KST).isoformat()}, ensure_ascii=False, indent=2)
        + "\n",
        encoding="utf-8",
    )
    write_summary(["# 이란·호르무즈 시장 전환 감시", "Telegram 연결 시험 메시지를 생성했습니다."])


def run_monitor(current: dt.datetime) -> int:
    clean_outputs()
    if os.getenv("TELEGRAM_TEST", "false").lower() == "true":
        create_test_alert(current)
        return 0

    state = load_state()
    news_items, news_errors = fetch_news(current)
    confirmed = confirm_event(news_items)
    if confirmed is None:
        lines = [
            "# 이란·호르무즈 시장 전환 감시",
            current.astimezone(KST).strftime("확인 시각: %Y-%m-%d %H:%M KST"),
            f"신뢰 매체 후보 기사: {len(news_items)}건",
            "결과: 동일 사건을 확인한 신뢰 자료 2곳이 없어 알리지 않음",
        ]
        if news_errors:
            lines.append(f"조회 오류: {len(news_errors)}개 피드")
        write_summary(lines)
        return 0

    kind, news_rows = confirmed
    current_event_id = event_id(kind, news_rows)
    if state.get("last_event_id") == current_event_id or cooldown_active(state, current, 24):
        write_summary(
            [
                "# 이란·호르무즈 시장 전환 감시",
                current.astimezone(KST).strftime("확인 시각: %Y-%m-%d %H:%M KST"),
                f"사건: {EVENT_LABELS[kind]}",
                "결과: 이미 알린 사건 또는 24시간 중복 방지 구간이어서 알리지 않음",
            ]
        )
        return 0

    market_errors: list[str] = []
    quotes: dict[str, Quote] = {}
    for key in ("us2y", "dxy", "wti", "brent"):
        try:
            quotes[key] = fetch_quote(SYMBOLS[key])
        except Exception as exc:
            market_errors.append(f"{key}: {exc}")

    max_age_minutes = int(os.getenv("IRAN_HORMUZ_MARKET_MAX_AGE_MINUTES", "240"))

    if kind in ("oil_flow_recovery", "sts_reroute_expansion"):
        oil = None
        for key in ("brent", "wti"):
            candidate = quotes.get(key)
            if candidate is not None and quote_is_fresh(candidate, current, max_age_minutes):
                oil = candidate
                break
        body = build_physical_flow_alert_body(kind, news_rows, oil, current)
        title = "중동 원유 흐름 회복·우회 물류 변화"
        alert = {
            "test_mode": False,
            "created_at_kst": current.astimezone(KST).isoformat(timespec="seconds"),
            "event_kind": kind,
            "event_label": EVENT_LABELS[kind],
            "event_id": current_event_id,
            "news": [asdict(row) for row in news_rows],
            "market": {"oil": asdict(oil) if oil else None},
        }
        pending_state = {
            "last_alert_at_kst": current.astimezone(KST).isoformat(timespec="seconds"),
            "last_event_kind": kind,
            "last_event_id": current_event_id,
            "last_market": alert["market"],
        }
        TITLE_PATH.write_text(title + "\n", encoding="utf-8")
        BODY_PATH.write_text(body, encoding="utf-8")
        ALERT_JSON_PATH.write_text(json.dumps(alert, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        PENDING_STATE_PATH.write_text(json.dumps(pending_state, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        write_summary([
            "# 이란·호르무즈 시장 전환 감시",
            current.astimezone(KST).strftime("확인 시각: %Y-%m-%d %H:%M KST"),
            f"사건: {EVENT_LABELS[kind]}",
            "결과: 실물 원유 흐름 별도 Telegram 조건 충족",
        ])
        return 0

    us2y = quotes.get("us2y")
    dxy = quotes.get("dxy")
    if us2y is None or dxy is None:
        write_summary(
            [
                "# 이란·호르무즈 시장 전환 감시",
                current.astimezone(KST).strftime("확인 시각: %Y-%m-%d %H:%M KST"),
                f"사건: {EVENT_LABELS[kind]}",
                "결과: 미국 2년물 또는 달러인덱스 값을 확보하지 못해 알리지 않음",
                *market_errors,
            ]
        )
        return 0

    stale = [
        quote.label
        for quote in (us2y, dxy)
        if not quote_is_fresh(quote, current, max_age_minutes)
    ]
    if stale:
        write_summary(
            [
                "# 이란·호르무즈 시장 전환 감시",
                current.astimezone(KST).strftime("확인 시각: %Y-%m-%d %H:%M KST"),
                f"사건: {EVENT_LABELS[kind]}",
                f"결과: 시장 데이터가 오래됨({', '.join(stale)}) · 알리지 않음",
            ]
        )
        return 0

    if not market_confirms(us2y, dxy):
        write_summary(
            [
                "# 이란·호르무즈 시장 전환 감시",
                current.astimezone(KST).strftime("확인 시각: %Y-%m-%d %H:%M KST"),
                f"사건: {EVENT_LABELS[kind]}",
                fmt_quote_line(us2y),
                fmt_quote_line(dxy),
                "결과: 미국 2년물과 달러인덱스가 모두 전 거래일보다 낮지 않아 알리지 않음",
            ]
        )
        return 0

    oil = None
    for key in ("wti", "brent"):
        candidate = quotes.get(key)
        if candidate is not None and quote_is_fresh(candidate, current, max_age_minutes):
            oil = candidate
            break

    body = build_alert_body(kind, news_rows, us2y, dxy, oil, current)
    title = "이란·호르무즈 시장 전환 확인"
    alert = {
        "test_mode": False,
        "created_at_kst": current.astimezone(KST).isoformat(timespec="seconds"),
        "event_kind": kind,
        "event_label": EVENT_LABELS[kind],
        "event_id": current_event_id,
        "news": [asdict(row) for row in news_rows],
        "market": {
            "us2y": asdict(us2y),
            "dxy": asdict(dxy),
            "oil": asdict(oil) if oil else None,
        },
    }
    pending_state = {
        "last_alert_at_kst": current.astimezone(KST).isoformat(timespec="seconds"),
        "last_event_kind": kind,
        "last_event_id": current_event_id,
        "last_market": alert["market"],
    }
    TITLE_PATH.write_text(title + "\n", encoding="utf-8")
    BODY_PATH.write_text(body, encoding="utf-8")
    ALERT_JSON_PATH.write_text(json.dumps(alert, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    PENDING_STATE_PATH.write_text(json.dumps(pending_state, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    write_summary(
        [
            "# 이란·호르무즈 시장 전환 감시",
            current.astimezone(KST).strftime("확인 시각: %Y-%m-%d %H:%M KST"),
            f"사건: {EVENT_LABELS[kind]}",
            fmt_quote_line(us2y),
            fmt_quote_line(dxy),
            "결과: Telegram 전송 조건 충족",
        ]
    )
    return 0


def finalize_state() -> int:
    if not PENDING_STATE_PATH.exists():
        return 0
    if not TELEGRAM_CONFIRMED_PATH.exists():
        print("Telegram 전송 확인 파일이 없어 상태를 반영하지 않습니다.")
        return 0
    try:
        confirmed = json.loads(TELEGRAM_CONFIRMED_PATH.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        print("Telegram 전송 확인 파일 해석 실패")
        return 0
    if confirmed.get("status") != "confirmed":
        print("Telegram 전송이 확정되지 않아 상태를 반영하지 않습니다.")
        return 0
    STATE_PATH.parent.mkdir(parents=True, exist_ok=True)
    STATE_PATH.write_text(PENDING_STATE_PATH.read_text(encoding="utf-8"), encoding="utf-8")
    print(f"state_finalized=true message_id={confirmed.get('message_id')}")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--finalize", action="store_true")
    args = parser.parse_args()
    if args.finalize:
        return finalize_state()
    return run_monitor(now_utc())


if __name__ == "__main__":
    raise SystemExit(main())
