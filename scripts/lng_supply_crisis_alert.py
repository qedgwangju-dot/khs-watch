#!/usr/bin/env python3
"""LNG 공급 차질·유럽 가스 가격·아시아 조달 위험을 감시한다.

외부 패키지 없이 GitHub Actions에서 실행한다. 뉴스는 Google News RSS에서
공식기관 또는 신뢰 매체 교차 확인으로 검증하고, TTF·Brent는 Yahoo Finance
차트 엔드포인트 두 곳의 값이 일치할 때만 사용한다. Telegram 전송은 workflow가
담당하며, 이 스크립트는 알림 파일과 전송 성공 후 반영할 상태 파일을 만든다.
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
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from zoneinfo import ZoneInfo

KST = ZoneInfo("Asia/Seoul")
UTC = dt.timezone.utc

OUT_DIR = pathlib.Path("out")
STATE_PATH = pathlib.Path("data/lng_supply_crisis_state.json")
TITLE_PATH = OUT_DIR / "lng_supply_crisis_title.txt"
BODY_PATH = OUT_DIR / "lng_supply_crisis_alert.md"
ALERT_JSON_PATH = OUT_DIR / "lng_supply_crisis_alert.json"
SUMMARY_PATH = OUT_DIR / "lng_supply_crisis_watch.md"
PENDING_STATE_PATH = OUT_DIR / "lng_supply_crisis_pending_state.json"
TELEGRAM_CONFIRMED_PATH = OUT_DIR / "lng_supply_crisis_telegram_confirmed.json"

YAHOO_BASES = (
    "https://query1.finance.yahoo.com/v8/finance/chart",
    "https://query2.finance.yahoo.com/v8/finance/chart",
)

NEWS_QUERIES = (
    (
        "qatar_supply",
        '"Qatar LNG" outage OR QatarEnergy force majeure OR Ras Laffan LNG exports when:3d',
    ),
    (
        "qatar_supply",
        '"Qatar LNG" resumes OR QatarEnergy restart OR "lifts force majeure" when:3d',
    ),
    (
        "hormuz_shipping",
        '"Strait of Hormuz" LNG shipping closure OR reopening OR tanker insurance when:3d',
    ),
    (
        "hormuz_shipping",
        '"Red Sea" LNG tanker reroute OR Suez LNG shipping disruption when:3d',
    ),
    (
        "europe_storage",
        '"Europe gas storage" emergency OR target OR LNG shortage when:3d',
    ),
    (
        "asia_procurement",
        'Asia LNG JKM Korea Japan spot cargo tender shortage when:3d',
    ),
    (
        "korea_supply",
        'Korea LNG supply KOGAS ministry emergency procurement when:7d',
    ),
    (
        "korea_supply",
        '한국 LNG 수급 가스공사 산업통상자원부 비상 조달 when:7d',
    ),
)

TRUSTED_SOURCE_ALIASES = (
    "reuters",
    "associated press",
    "ap news",
    "bloomberg",
    "financial times",
    "the wall street journal",
    "wall street journal",
    "bbc",
    "cnbc",
    "nikkei asia",
    "s&p global commodity insights",
    "argus media",
    "montel",
    "upstream",
    "the guardian",
    "afp",
    "연합뉴스",
    "로이터",
    "블룸버그",
    "파이낸셜타임스",
    "니혼게이자이",
    "qatarenergy",
    "qatar energy",
    "european commission",
    "gas infrastructure europe",
    "gie",
    "international energy agency",
    "iea",
    "korea gas corporation",
    "kogas",
    "한국가스공사",
    "ministry of trade, industry and energy",
    "motie",
    "산업통상자원부",
    "산업부",
)

OFFICIAL_SOURCE_ALIASES = (
    "qatarenergy",
    "qatar energy",
    "european commission",
    "gas infrastructure europe",
    "international energy agency",
    "iea",
    "korea gas corporation",
    "kogas",
    "한국가스공사",
    "ministry of trade, industry and energy",
    "motie",
    "산업통상자원부",
    "산업부",
)

WORSENING_TERMS = {
    "qatar_supply": (
        "outage", "shutdown", "shut down", "halt", "stopped", "suspend",
        "force majeure", "damage", "attack", "export collapse", "production cut",
        "disruption", "delay", "extends force majeure", "중단", "가동 중단",
        "불가항력", "피해", "수출 급감", "수출 중단", "연장",
    ),
    "hormuz_shipping": (
        "closed", "closure", "blocked", "blockade", "attack", "seized",
        "insurance withdrawn", "war risk premium", "reroute", "divert",
        "traffic halted", "disruption", "봉쇄", "통항 중단", "공격",
        "보험 중단", "우회", "운항 중단",
    ),
    "europe_storage": (
        "low storage", "storage shortfall", "miss target", "below target",
        "emergency", "shortage", "rationing", "inventory draw", "stocks fall",
        "tight supply", "재고 부족", "목표 미달", "비상", "공급 부족",
        "재고 감소",
    ),
    "asia_procurement": (
        "jkm surges", "jkm jumps", "price spike", "record high", "shortage",
        "cargo competition", "tender rush", "supply tight", "diverted to europe",
        "spot cargo", "가격 급등", "물량 부족", "조달 경쟁", "입찰 급증",
        "유럽행", "현물 구매",
    ),
    "korea_supply": (
        "emergency procurement", "supply concern", "shortage", "tender",
        "spot purchase", "inventory falls", "contingency", "비상 조달",
        "수급 우려", "공급 부족", "긴급 입찰", "현물 구매", "재고 감소",
    ),
}

EASING_TERMS = {
    "qatar_supply": (
        "resumes", "resume", "restart", "restarts", "production restored",
        "exports recover", "lifts force majeure", "force majeure lifted",
        "returns to service", "재개", "가동 회복", "수출 회복",
        "불가항력 해제", "정상화",
    ),
    "hormuz_shipping": (
        "reopens", "reopened", "shipping resumes", "traffic resumes",
        "normal traffic", "insurance restored", "safe passage", "통항 재개",
        "운항 재개", "정상 통행", "보험 복원", "안전 통항",
    ),
    "europe_storage": (
        "reaches target", "above target", "stocks rise", "storage increases",
        "inventory rebuild", "supply secured", "목표 달성", "재고 증가",
        "비축 확대", "공급 확보",
    ),
    "asia_procurement": (
        "jkm falls", "price drops", "cargo abundant", "demand weakens",
        "supply eases", "cargo returns to asia", "가격 하락", "물량 여유",
        "수급 완화", "아시아행",
    ),
    "korea_supply": (
        "supply stable", "no shortage", "cargo secured", "inventory sufficient",
        "contingency lifted", "수급 안정", "공급 차질 없음", "물량 확보",
        "재고 충분", "비상 해제",
    ),
}

SUBTYPE_TERMS = (
    ("force_majeure", ("force majeure", "불가항력")),
    ("export_resume", ("exports recover", "exports resume", "수출 재개", "수출 회복")),
    ("production_restart", ("restart", "restarts", "production restored", "가동 재개", "가동 회복")),
    ("production_outage", ("outage", "shutdown", "halt", "가동 중단", "수출 중단")),
    ("facility_damage", ("damage", "attack", "피해", "공격")),
    ("hormuz_reopen", ("reopens", "reopened", "shipping resumes", "통항 재개", "운항 재개")),
    ("hormuz_closure", ("closed", "closure", "blocked", "blockade", "봉쇄", "통항 중단")),
    ("insurance", ("insurance", "war risk", "보험")),
    ("reroute", ("reroute", "divert", "우회", "유럽행")),
    ("storage", ("storage", "inventory", "stocks", "재고", "비축")),
    ("jkm_price", ("jkm", "가격 급등", "가격 하락")),
    ("cargo_tender", ("tender", "spot cargo", "입찰", "현물")),
    ("korea_supply", ("kogas", "korea gas", "한국가스공사", "산업통상자원부", "산업부")),
)

STOPWORDS = {
    "the", "a", "an", "and", "or", "to", "of", "in", "on", "for", "from",
    "with", "as", "at", "by", "after", "amid", "over", "says", "say",
    "qatar", "lng", "gas", "natural", "europe", "asia", "korea",
}


@dataclass(frozen=True)
class NewsItem:
    category: str
    polarity: str
    subtype: str
    title: str
    source: str
    link: str
    published_utc: str
    published_epoch: float
    official: bool
    event_id: str


@dataclass(frozen=True)
class Quote:
    key: str
    symbol: str
    label: str
    unit: str
    price: float
    previous_close: float
    change_pct: float
    timestamp_epoch: float
    timestamp_utc: str


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


def fetch_bytes(url: str, timeout: int = 25, attempts: int = 3) -> bytes:
    headers = {
        "Accept": "application/rss+xml, application/xml, text/xml, application/json;q=0.9, */*;q=0.8",
        "User-Agent": "Mozilla/5.0 khs-lng-supply-crisis-alert/1.0",
    }
    last_error: Exception | None = None
    for attempt in range(attempts):
        try:
            request = urllib.request.Request(url, headers=headers)
            with urllib.request.urlopen(request, timeout=timeout) as response:
                return response.read()
        except Exception as exc:
            last_error = exc
            if attempt + 1 < attempts:
                time.sleep(1.2 * (attempt + 1))
    raise RuntimeError(f"fetch failed: {url}: {last_error}")


def parse_date(value: str) -> dt.datetime | None:
    if not value:
        return None
    try:
        parsed = email.utils.parsedate_to_datetime(value)
    except (TypeError, ValueError):
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=UTC)
    return parsed.astimezone(UTC)


def source_matches(source: str, aliases: tuple[str, ...]) -> bool:
    normalized = normalize_text(source)
    return any(alias in normalized for alias in aliases)


def classify_polarity(category: str, title: str) -> str | None:
    normalized = normalize_text(title)
    easing = any(term in normalized for term in EASING_TERMS[category])
    worsening = any(term in normalized for term in WORSENING_TERMS[category])
    if easing and not worsening:
        return "easing"
    if worsening and not easing:
        return "worsening"
    if easing and worsening:
        last_easing = max(normalized.rfind(term) for term in EASING_TERMS[category] if term in normalized)
        last_worsening = max(normalized.rfind(term) for term in WORSENING_TERMS[category] if term in normalized)
        return "easing" if last_easing > last_worsening else "worsening"
    return None


def classify_subtype(title: str) -> str:
    normalized = normalize_text(title)
    for subtype, terms in SUBTYPE_TERMS:
        if any(term in normalized for term in terms):
            return subtype
    tokens = [
        token for token in re.findall(r"[a-z0-9가-힣]+", normalized)
        if len(token) >= 3 and token not in STOPWORDS
    ]
    return "_".join(tokens[:3]) or "general"


def make_event_id(category: str, polarity: str, subtype: str, published: dt.datetime) -> str:
    bucket = int(published.timestamp() // (72 * 3600))
    basis = f"{category}|{polarity}|{subtype}|{bucket}"
    return hashlib.sha256(basis.encode("utf-8")).hexdigest()[:20]


def fetch_news_item_set(max_age_hours: int = 84) -> tuple[list[NewsItem], list[str]]:
    cutoff = now_utc() - dt.timedelta(hours=max_age_hours)
    items: list[NewsItem] = []
    errors: list[str] = []
    seen: set[tuple[str, str, str]] = set()

    for category, query in NEWS_QUERIES:
        params = urllib.parse.urlencode(
            {"q": query, "hl": "en-US", "gl": "US", "ceid": "US:en"}
        )
        url = f"https://news.google.com/rss/search?{params}"
        try:
            root = ET.fromstring(fetch_bytes(url))
        except Exception as exc:
            errors.append(f"{category}: {type(exc).__name__}")
            continue

        for item in root.findall(".//item"):
            title = (item.findtext("title") or "").strip()
            link = (item.findtext("link") or "").strip()
            source = (item.findtext("source") or "").strip()
            published = parse_date((item.findtext("pubDate") or "").strip())
            if not title or not link or not source or published is None:
                continue
            if published < cutoff:
                continue
            if not source_matches(source, TRUSTED_SOURCE_ALIASES):
                continue
            polarity = classify_polarity(category, title)
            if polarity is None:
                continue
            subtype = classify_subtype(title)
            key = (category, normalize_text(title), normalize_text(source))
            if key in seen:
                continue
            seen.add(key)
            official = source_matches(source, OFFICIAL_SOURCE_ALIASES)
            items.append(
                NewsItem(
                    category=category,
                    polarity=polarity,
                    subtype=subtype,
                    title=title,
                    source=source,
                    link=link,
                    published_utc=published.isoformat(timespec="seconds"),
                    published_epoch=published.timestamp(),
                    official=official,
                    event_id=make_event_id(category, polarity, subtype, published),
                )
            )

    items.sort(key=lambda item: item.published_epoch, reverse=True)
    return items, errors


def confirmed_news_groups(items: list[NewsItem]) -> list[dict[str, object]]:
    buckets: dict[tuple[str, str, str], list[NewsItem]] = {}
    for item in items:
        buckets.setdefault((item.category, item.polarity, item.subtype), []).append(item)

    confirmed: list[dict[str, object]] = []
    for (category, polarity, subtype), group in buckets.items():
        group.sort(key=lambda item: item.published_epoch, reverse=True)
        latest = group[0]
        recent = [
            item for item in group
            if latest.published_epoch - item.published_epoch <= 48 * 3600
        ]
        distinct_sources = {normalize_text(item.source) for item in recent}
        official_items = [item for item in recent if item.official]
        if not official_items and len(distinct_sources) < 2:
            continue
        evidence = official_items[:1] if official_items else recent[:3]
        if not official_items:
            selected: list[NewsItem] = []
            used: set[str] = set()
            for item in recent:
                source_key = normalize_text(item.source)
                if source_key in used:
                    continue
                selected.append(item)
                used.add(source_key)
                if len(selected) == 2:
                    break
            evidence = selected
        confirmed.append(
            {
                "category": category,
                "polarity": polarity,
                "subtype": subtype,
                "event_id": latest.event_id,
                "latest_epoch": latest.published_epoch,
                "evidence": evidence,
                "verification": "공식 원문" if official_items else "신뢰 매체 2곳 교차",
            }
        )

    confirmed.sort(key=lambda group: float(group["latest_epoch"]), reverse=True)
    return confirmed


def parse_yahoo_quote(key: str, symbol: str, label: str, unit: str, base: str) -> Quote:
    encoded = urllib.parse.quote(symbol, safe="")
    params = urllib.parse.urlencode({"interval": "5m", "range": "5d", "includePrePost": "true"})
    payload = json.loads(fetch_bytes(f"{base}/{encoded}?{params}").decode("utf-8"))
    result = payload.get("chart", {}).get("result")
    if not result:
        raise RuntimeError(f"{symbol}: no chart result")
    chart = result[0]
    meta = chart.get("meta", {})
    price = finite_number(meta.get("regularMarketPrice"))
    previous_close = finite_number(meta.get("chartPreviousClose"))
    timestamp = finite_number(meta.get("regularMarketTime"))
    if price is None or previous_close is None or previous_close <= 0 or timestamp is None:
        raise RuntimeError(f"{symbol}: incomplete market metadata")
    change_pct = (price / previous_close - 1.0) * 100.0
    observed = dt.datetime.fromtimestamp(timestamp, UTC)
    return Quote(
        key=key,
        symbol=symbol,
        label=label,
        unit=unit,
        price=price,
        previous_close=previous_close,
        change_pct=change_pct,
        timestamp_epoch=timestamp,
        timestamp_utc=observed.isoformat(timespec="seconds"),
    )


def quote_is_recent(quote: Quote) -> bool:
    observed = dt.datetime.fromtimestamp(quote.timestamp_epoch, UTC)
    age = now_utc() - observed
    weekday = now_utc().weekday()
    max_age = dt.timedelta(hours=84 if weekday in (0, 5, 6) else 16)
    return dt.timedelta(0) <= age <= max_age


def fetch_verified_quote(key: str, symbol: str, label: str, unit: str) -> Quote:
    quotes = [parse_yahoo_quote(key, symbol, label, unit, base) for base in YAHOO_BASES]
    first, second = quotes
    price_gap = abs(first.price - second.price) / max(abs(first.price), abs(second.price), 1e-9)
    time_gap = abs(first.timestamp_epoch - second.timestamp_epoch)
    if price_gap > 0.015 or time_gap > 7200:
        raise RuntimeError(
            f"{symbol}: endpoint mismatch price_gap={price_gap:.3%} time_gap={time_gap:.0f}s"
        )
    if not quote_is_recent(first):
        raise RuntimeError(f"{symbol}: stale quote {first.timestamp_utc}")
    return first


def fetch_market_quotes() -> tuple[dict[str, Quote], list[str]]:
    specs = (
        ("ttf", "TTF=F", "유럽 TTF 천연가스", "유로/MWh"),
        ("brent", "BZ=F", "Brent 유가", "달러/배럴"),
    )
    quotes: dict[str, Quote] = {}
    errors: list[str] = []
    for key, symbol, label, unit in specs:
        try:
            quotes[key] = fetch_verified_quote(key, symbol, label, unit)
        except Exception as exc:
            errors.append(f"{symbol}: {type(exc).__name__}: {exc}")
    return quotes, errors


def market_signals(quotes: dict[str, Quote]) -> set[str]:
    signals: set[str] = set()
    ttf = quotes.get("ttf")
    if ttf:
        if ttf.change_pct >= 5.0:
            signals.add("ttf_up_5")
        if ttf.change_pct <= -5.0:
            signals.add("ttf_down_5")
        for level in (50, 60, 70, 80):
            if ttf.price >= level:
                signals.add(f"ttf_above_{level}")
    brent = quotes.get("brent")
    if brent:
        if brent.change_pct >= 5.0:
            signals.add("brent_up_5")
        if brent.change_pct <= -5.0:
            signals.add("brent_down_5")
        for level in (90, 100, 120):
            if brent.price >= level:
                signals.add(f"brent_above_{level}")
    return signals


def load_state() -> dict[str, object]:
    default = {
        "version": 1,
        "setup_test_sent_at_kst": None,
        "last_alert_at_kst": None,
        "alerted_event_ids": [],
        "active_market_signals": [],
    }
    if not STATE_PATH.exists():
        return default
    try:
        loaded = json.loads(STATE_PATH.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return default
    if not isinstance(loaded, dict):
        return default
    default.update(loaded)
    return default


def clean_outputs() -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    for path in (
        TITLE_PATH,
        BODY_PATH,
        ALERT_JSON_PATH,
        PENDING_STATE_PATH,
        TELEGRAM_CONFIRMED_PATH,
    ):
        try:
            path.unlink()
        except FileNotFoundError:
            pass


def signal_label(signal: str, cleared: bool = False) -> str:
    labels = {
        "ttf_up_5": "TTF 전일 대비 +5% 이상",
        "ttf_down_5": "TTF 전일 대비 -5% 이하",
        "ttf_above_50": "TTF 50유로/MWh 상회",
        "ttf_above_60": "TTF 60유로/MWh 상회",
        "ttf_above_70": "TTF 70유로/MWh 상회",
        "ttf_above_80": "TTF 80유로/MWh 상회",
        "brent_up_5": "Brent 전일 대비 +5% 이상",
        "brent_down_5": "Brent 전일 대비 -5% 이하",
        "brent_above_90": "Brent 90달러/배럴 상회",
        "brent_above_100": "Brent 100달러/배럴 상회",
        "brent_above_120": "Brent 120달러/배럴 상회",
    }
    base = labels.get(signal, signal)
    return f"{base} 조건 해제" if cleared else base


def category_label(category: str) -> str:
    return {
        "qatar_supply": "카타르 LNG 생산·수출",
        "hormuz_shipping": "호르무즈·홍해 운송",
        "europe_storage": "유럽 가스 재고",
        "asia_procurement": "동북아 LNG 조달",
        "korea_supply": "한국 LNG 수급",
    }.get(category, category)


def format_quote(quote: Quote) -> str:
    return (
        f"{quote.label} {quote.price:,.2f}{quote.unit} "
        f"({quote.change_pct:+.2f}%, 기준 {quote.timestamp_utc[:16].replace('T', ' ')} UTC)"
    )


def explain_impact(
    news_groups: list[dict[str, object]],
    new_signals: set[str],
    cleared_signals: set[str],
) -> tuple[str, str, str]:
    worsening = any(group["polarity"] == "worsening" for group in news_groups)
    easing = any(group["polarity"] == "easing" for group in news_groups)
    worsening = worsening or any(
        signal.endswith("_up_5") or "above_" in signal for signal in new_signals
    )
    easing = easing or any(signal.endswith("_down_5") for signal in new_signals)
    easing = easing or bool(cleared_signals)

    if worsening and not easing:
        korea = (
            "한국은 즉시 물량 고갈보다 현물 LNG 대체구매 단가 상승이 먼저 나타납니다. "
            "유럽이 더 높은 가격을 제시하면 미국·대서양 화물이 유럽으로 이동해 "
            "JKM과 한국 발전연료비가 뒤따라 오를 수 있습니다."
        )
        investment = (
            "수급: LNG 판매자·비호르무즈 공급원 우위, 한국가스공사·한국전력·가스발전 원가 부담. "
            "할인율: 에너지 물가가 금리 인하를 늦출 위험. "
            "시간표: 카타르 수출 재개·호르무즈 통항·유럽 저장률이 반전 조건입니다."
        )
        one_line = "공급 차질과 가격 상승이 겹쳐 하반기 유럽·동북아 LNG 조달 경쟁이 악화되는 신호입니다."
    elif easing and not worsening:
        korea = (
            "공급 또는 운송 정상화가 확인되면 한국의 현물 조달 프리미엄과 발전연료비 상승 압력이 낮아집니다. "
            "다만 실제 선적 재개와 가격 하락이 동반되는지 재확인이 필요합니다."
        )
        investment = (
            "수급: LNG 부족 수혜주는 되돌림 위험, 수입·가스발전 원가 부담은 완화. "
            "할인율: 에너지 물가 압력이 낮아질 가능성. "
            "시간표: 발표가 아니라 선적·통항·재고 숫자로 확인해야 합니다."
        )
        one_line = "완화 신호가 발생했지만 실제 LNG 선적과 TTF·JKM 하락이 이어지는지가 최종 확인점입니다."
    else:
        korea = (
            "공급 뉴스와 시장 가격 신호가 엇갈립니다. 한국은 현물 화물 확보 가격과 "
            "KOGAS·산업부의 공식 수급 발표를 우선 확인해야 합니다."
        )
        investment = (
            "수급과 가격이 같은 방향으로 확인되기 전에는 LNG 생산자·조선·가스발전의 "
            "단순 방향성 매매를 피해야 합니다."
        )
        one_line = "뉴스와 가격이 혼재해 추가 확인이 필요하며, 확정 수급 숫자를 우선합니다."
    return korea, investment, one_line


def build_regular_alert(
    groups: list[dict[str, object]],
    quotes: dict[str, Quote],
    new_signals: set[str],
    cleared_signals: set[str],
) -> tuple[str, str, dict[str, object]]:
    title = "⚠️ LNG·천연가스 수급 경보"
    lines: list[str] = ["[새 변화]"]

    for group in groups[:3]:
        polarity = "악화" if group["polarity"] == "worsening" else "완화"
        lines.append(
            f"• {category_label(str(group['category']))}: {polarity} "
            f"({group['verification']})"
        )
        evidence = group["evidence"]
        for item in evidence[:2]:
            lines.append(f"  - {item.source}: {item.title}")
            lines.append(f"    {item.link}")

    if new_signals or cleared_signals:
        lines.append("")
        lines.append("[가격 신호]")
        for signal in sorted(new_signals):
            lines.append(f"• {signal_label(signal)}")
        for signal in sorted(cleared_signals):
            lines.append(f"• {signal_label(signal, cleared=True)}")
        for quote in quotes.values():
            lines.append(f"• {format_quote(quote)}")

    korea, investment, one_line = explain_impact(groups, new_signals, cleared_signals)
    lines.extend(
        [
            "",
            "[한국 영향]",
            korea,
            "",
            "[투자 영향]",
            investment,
            "",
            f"핵심 한 줄: {one_line}",
        ]
    )
    body = "\n".join(lines)
    metadata = {
        "kind": "material_change",
        "news_event_ids": [group["event_id"] for group in groups],
        "new_market_signals": sorted(new_signals),
        "cleared_market_signals": sorted(cleared_signals),
        "quotes": {key: quote.__dict__ for key, quote in quotes.items()},
    }
    return title, body, metadata


def build_setup_test(quotes: dict[str, Quote]) -> tuple[str, str, dict[str, object]]:
    title = "✅ LNG·천연가스 감시 연결 완료"
    lines = [
        "전송 대상: @hs8879887988798879_bot",
        "확인 주기: 매시간 1회",
        "",
        "알림 조건:",
        "• 카타르 LNG 생산·수출 중단·재개, Force Majeure 연장·해제",
        "• 호르무즈·홍해 통항, 보험, 우회 운항의 확정 변화",
        "• 유럽 저장률 비상·동북아 JKM 조달 경쟁·한국 공식 수급 발표",
        "• TTF 하루 ±5% 또는 50·60·70·80유로/MWh 구간 진입·이탈",
        "• Brent 하루 ±5% 또는 90·100·120달러/배럴 구간 진입·이탈",
        "",
        "검증 원칙: 공식 원문 1곳 또는 신뢰 매체 2곳 교차 확인. 수치가 오래됐거나 서로 다르면 알림을 보류합니다.",
        "같은 조건이 유지되는 동안 반복 발송하지 않고, 재진입·추가 악화·정상화 때 다시 알립니다.",
    ]
    if quotes:
        lines.append("")
        lines.append("현재 확인값:")
        for quote in quotes.values():
            lines.append(f"• {format_quote(quote)}")
    metadata = {
        "kind": "setup_test",
        "quotes": {key: quote.__dict__ for key, quote in quotes.items()},
    }
    return title, "\n".join(lines), metadata


def write_alert(title: str, body: str, metadata: dict[str, object]) -> None:
    TITLE_PATH.write_text(title + "\n", encoding="utf-8")
    BODY_PATH.write_text(body.strip() + "\n", encoding="utf-8")
    ALERT_JSON_PATH.write_text(
        json.dumps(metadata, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def write_summary(
    *,
    news_count: int,
    confirmed_count: int,
    quote_count: int,
    news_errors: list[str],
    market_errors: list[str],
    alert_created: bool,
    reason: str,
) -> None:
    timestamp = dt.datetime.now(KST).isoformat(timespec="seconds")
    lines = [
        "# LNG 공급 위기 감시",
        "",
        f"- 실행시각(KST): {timestamp}",
        f"- 신뢰 뉴스 후보: {news_count}건",
        f"- 확정 변화 묶음: {confirmed_count}건",
        f"- 검증 시장값: {quote_count}개",
        f"- Telegram 알림 파일: {'생성' if alert_created else '없음'}",
        f"- 판정: {reason}",
    ]
    if news_errors:
        lines.append(f"- 뉴스 조회 오류: {'; '.join(news_errors[:4])}")
    if market_errors:
        lines.append(f"- 시장값 오류·보류: {'; '.join(market_errors[:4])}")
    SUMMARY_PATH.write_text("\n".join(lines) + "\n", encoding="utf-8")


def finalize() -> int:
    if not PENDING_STATE_PATH.exists():
        print("pending_state=false")
        return 0

    alert_required = BODY_PATH.exists()
    if alert_required and not TELEGRAM_CONFIRMED_PATH.exists():
        print("telegram_confirmed=false state_not_updated=true")
        return 0

    pending = json.loads(PENDING_STATE_PATH.read_text(encoding="utf-8"))
    STATE_PATH.parent.mkdir(parents=True, exist_ok=True)
    STATE_PATH.write_text(
        json.dumps(pending, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print("state_updated=true")
    return 0


def run(setup_test: bool) -> int:
    clean_outputs()
    state = load_state()
    news, news_errors = fetch_news_item_set()
    confirmed = confirmed_news_groups(news)
    quotes, market_errors = fetch_market_quotes()

    previous_event_ids = {
        str(value) for value in state.get("alerted_event_ids", [])
        if isinstance(value, str)
    }
    previous_signals = {
        str(value) for value in state.get("active_market_signals", [])
        if isinstance(value, str)
    }

    current_signals = market_signals(quotes)
    if "ttf" not in quotes:
        current_signals.update(signal for signal in previous_signals if signal.startswith("ttf_"))
    if "brent" not in quotes:
        current_signals.update(signal for signal in previous_signals if signal.startswith("brent_"))

    new_groups = [
        group for group in confirmed
        if str(group["event_id"]) not in previous_event_ids
    ]
    new_signals = current_signals - previous_signals
    cleared_signals = previous_signals - current_signals

    pending = dict(state)
    pending["version"] = 1
    pending["active_market_signals"] = sorted(current_signals)

    alert_created = False
    reason = "새 확정 변화 없음"

    should_test = setup_test and not state.get("setup_test_sent_at_kst")
    if should_test:
        title, body, metadata = build_setup_test(quotes)
        write_alert(title, body, metadata)
        pending["setup_test_sent_at_kst"] = dt.datetime.now(KST).isoformat(timespec="seconds")
        pending["last_alert_at_kst"] = pending["setup_test_sent_at_kst"]
        pending["alerted_event_ids"] = [
            str(group["event_id"]) for group in confirmed
        ][-400:]
        alert_created = True
        reason = "최초 연결 시험"
    elif new_groups or new_signals or cleared_signals:
        title, body, metadata = build_regular_alert(
            new_groups, quotes, new_signals, cleared_signals
        )
        write_alert(title, body, metadata)
        merged_ids = list(previous_event_ids)
        merged_ids.extend(str(group["event_id"]) for group in new_groups)
        pending["alerted_event_ids"] = merged_ids[-400:]
        pending["last_alert_at_kst"] = dt.datetime.now(KST).isoformat(timespec="seconds")
        alert_created = True
        reason = "새 확정 뉴스 또는 가격 조건 변화"
    else:
        pending["alerted_event_ids"] = list(previous_event_ids)[-400:]

    PENDING_STATE_PATH.write_text(
        json.dumps(pending, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    write_summary(
        news_count=len(news),
        confirmed_count=len(confirmed),
        quote_count=len(quotes),
        news_errors=news_errors,
        market_errors=market_errors,
        alert_created=alert_created,
        reason=reason,
    )
    print(
        f"alert_created={str(alert_created).lower()} "
        f"news={len(news)} confirmed={len(confirmed)} quotes={len(quotes)}"
    )
    return 0


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--finalize", action="store_true")
    parser.add_argument("--setup-test", action="store_true")
    args = parser.parse_args()
    if args.finalize:
        return finalize()
    return run(setup_test=args.setup_test)


if __name__ == "__main__":
    raise SystemExit(main())
