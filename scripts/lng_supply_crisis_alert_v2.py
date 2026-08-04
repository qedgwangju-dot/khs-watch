#!/usr/bin/env python3
"""LNG 공급 차질·유럽 가스 가격·아시아 조달 위험 감시 v2.

핵심 원칙
1) 공급·운송 정상화는 뉴스의 공식 원문 1곳 또는 신뢰 매체 2곳으로만 판정한다.
2) 가격 하락·급락 조건 해제는 공급 정상화로 해석하지 않는다.
3) Yahoo Finance query1/query2는 독립 2소스가 아니라 같은 제공사의 2개 엔드포인트다.
4) 평일 4시간을 넘긴 시세는 새 가격 신호 판정에서 제외하고 기존 상태를 유지한다.
5) ±5% 신호에는 히스테리시스를 적용하고, 단순 조건 해제만으로 Telegram을 보내지 않는다.
"""

from __future__ import annotations

import argparse
import datetime as dt
import email.utils
import hashlib
import html
import json
import math
import pathlib
import re
import time
import unicodedata
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from dataclasses import asdict, dataclass
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
    ("qatar_supply", '"Qatar LNG" outage OR QatarEnergy force majeure OR Ras Laffan LNG exports when:3d'),
    ("qatar_supply", '"Qatar LNG" resumes OR QatarEnergy restart OR "lifts force majeure" when:3d'),
    ("hormuz_shipping", '"Strait of Hormuz" LNG shipping closure OR reopening OR tanker insurance when:3d'),
    ("hormuz_shipping", '"Red Sea" LNG tanker reroute OR Suez LNG shipping disruption when:3d'),
    ("europe_storage", '"Europe gas storage" emergency OR target OR LNG shortage when:3d'),
    ("asia_procurement", 'Asia LNG JKM Korea Japan spot cargo tender shortage when:3d'),
    ("korea_supply", 'Korea LNG supply KOGAS ministry emergency procurement when:7d'),
    ("korea_supply", '한국 LNG 수급 가스공사 산업통상자원부 비상 조달 when:7d'),
)

TRUSTED_SOURCE_ALIASES = (
    "reuters", "associated press", "ap news", "bloomberg", "financial times",
    "the wall street journal", "wall street journal", "bbc", "cnbc",
    "nikkei asia", "s&p global commodity insights", "argus media", "montel",
    "upstream", "the guardian", "afp", "연합뉴스", "로이터", "블룸버그",
    "파이낸셜타임스", "니혼게이자이", "qatarenergy", "qatar energy",
    "european commission", "gas infrastructure europe", "gie",
    "international energy agency", "iea", "korea gas corporation", "kogas",
    "한국가스공사", "ministry of trade, industry and energy", "motie",
    "산업통상자원부", "산업부",
)

OFFICIAL_SOURCE_ALIASES = (
    "qatarenergy", "qatar energy", "european commission",
    "gas infrastructure europe", "international energy agency", "iea",
    "korea gas corporation", "kogas", "한국가스공사",
    "ministry of trade, industry and energy", "motie", "산업통상자원부", "산업부",
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
        "tight supply", "재고 부족", "목표 미달", "비상", "공급 부족", "재고 감소",
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

PRICE_SPECS = {
    "ttf": {
        "symbol": "TTF=F",
        "label": "Yahoo TTF=F 달력월물",
        "unit": "유로/MWh",
        "levels": (50.0, 60.0, 70.0, 80.0),
        "exit_buffer": 1.0,
    },
    "brent": {
        "symbol": "BZ=F",
        "label": "Yahoo Brent 선물",
        "unit": "달러/배럴",
        "levels": (90.0, 100.0, 120.0),
        "exit_buffer": 1.5,
    },
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
    age_minutes: int
    source_note: str


def now_utc() -> dt.datetime:
    return dt.datetime.now(UTC)


def normalize_text(value: str) -> str:
    value = html.unescape(value or "")
    value = unicodedata.normalize("NFKC", value)
    return re.sub(r"\s+", " ", value).strip().lower()


def finite_number(value: object) -> float | None:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) else None


def fetch_bytes(url: str, timeout: int = 25, attempts: int = 3) -> bytes:
    headers = {
        "Accept": "application/rss+xml, application/xml, text/xml, application/json;q=0.9, */*;q=0.8",
        "User-Agent": "Mozilla/5.0 khs-lng-supply-crisis-alert/2.0",
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
        token
        for token in re.findall(r"[a-z0-9가-힣]+", normalized)
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
        params = urllib.parse.urlencode({"q": query, "hl": "en-US", "gl": "US", "ceid": "US:en"})
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
            if not title or not link or not source or published is None or published < cutoff:
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
                    official=source_matches(source, OFFICIAL_SOURCE_ALIASES),
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
        recent = [item for item in group if latest.published_epoch - item.published_epoch <= 48 * 3600]
        official_items = [item for item in recent if item.official]
        distinct_sources = {normalize_text(item.source) for item in recent}
        if not official_items and len(distinct_sources) < 2:
            continue

        if official_items:
            evidence = official_items[:1]
            verification = "공식 원문"
        else:
            evidence = []
            used: set[str] = set()
            for item in recent:
                source_key = normalize_text(item.source)
                if source_key in used:
                    continue
                evidence.append(item)
                used.add(source_key)
                if len(evidence) == 2:
                    break
            verification = "신뢰 매체 2곳 교차"

        confirmed.append(
            {
                "category": category,
                "polarity": polarity,
                "subtype": subtype,
                "event_id": latest.event_id,
                "latest_epoch": latest.published_epoch,
                "evidence": evidence,
                "verification": verification,
            }
        )

    confirmed.sort(key=lambda group: float(group["latest_epoch"]), reverse=True)
    return confirmed


def parse_yahoo_quote(key: str, base: str) -> Quote:
    spec = PRICE_SPECS[key]
    symbol = str(spec["symbol"])
    encoded = urllib.parse.quote(symbol, safe="")
    params = urllib.parse.urlencode({"interval": "5m", "range": "5d", "includePrePost": "true"})
    payload = json.loads(fetch_bytes(f"{base}/{encoded}?{params}").decode("utf-8"))
    result = payload.get("chart", {}).get("result")
    if not result:
        raise RuntimeError(f"{symbol}: no chart result")
    meta = result[0].get("meta", {})
    price = finite_number(meta.get("regularMarketPrice"))
    previous_close = finite_number(meta.get("chartPreviousClose"))
    timestamp = finite_number(meta.get("regularMarketTime"))
    if price is None or previous_close is None or previous_close <= 0 or timestamp is None:
        raise RuntimeError(f"{symbol}: incomplete market metadata")

    observed = dt.datetime.fromtimestamp(timestamp, UTC)
    age_minutes = max(0, int((now_utc() - observed).total_seconds() // 60))
    return Quote(
        key=key,
        symbol=symbol,
        label=str(spec["label"]),
        unit=str(spec["unit"]),
        price=price,
        previous_close=previous_close,
        change_pct=(price / previous_close - 1.0) * 100.0,
        timestamp_epoch=timestamp,
        timestamp_utc=observed.isoformat(timespec="seconds"),
        age_minutes=age_minutes,
        source_note="Yahoo Finance 지연 시세·동일 제공사 2엔드포인트 대조",
    )


def quote_max_age() -> dt.timedelta:
    weekday = now_utc().weekday()
    return dt.timedelta(hours=84 if weekday in (0, 5, 6) else 4)


def fetch_verified_quote(key: str) -> Quote:
    first, second = [parse_yahoo_quote(key, base) for base in YAHOO_BASES]
    price_gap = abs(first.price - second.price) / max(abs(first.price), abs(second.price), 1e-9)
    time_gap = abs(first.timestamp_epoch - second.timestamp_epoch)
    if price_gap > 0.002 or time_gap > 300:
        raise RuntimeError(
            f"{first.symbol}: Yahoo endpoint mismatch "
            f"price_gap={price_gap:.3%} time_gap={time_gap:.0f}s"
        )
    observed = dt.datetime.fromtimestamp(first.timestamp_epoch, UTC)
    age = now_utc() - observed
    if age < dt.timedelta(0) or age > quote_max_age():
        raise RuntimeError(
            f"{first.symbol}: stale quote age={int(age.total_seconds() // 60)}m "
            f"timestamp={first.timestamp_utc}"
        )
    return first


def fetch_market_quotes() -> tuple[dict[str, Quote], list[str]]:
    quotes: dict[str, Quote] = {}
    errors: list[str] = []
    for key in PRICE_SPECS:
        try:
            quotes[key] = fetch_verified_quote(key)
        except Exception as exc:
            errors.append(f"{key}: {type(exc).__name__}: {exc}")
    return quotes, errors


def apply_hysteresis(
    quotes: dict[str, Quote],
    previous_signals: set[str],
) -> set[str]:
    current = set(previous_signals)

    for key, spec in PRICE_SPECS.items():
        quote = quotes.get(key)
        if quote is None:
            continue

        up_signal = f"{key}_up_5"
        down_signal = f"{key}_down_5"

        if quote.change_pct >= 5.0:
            current.add(up_signal)
        elif quote.change_pct < 3.0:
            current.discard(up_signal)

        if quote.change_pct <= -5.0:
            current.add(down_signal)
        elif quote.change_pct > -3.0:
            current.discard(down_signal)

        levels = tuple(float(level) for level in spec["levels"])
        exit_buffer = float(spec["exit_buffer"])
        for level in levels:
            signal = f"{key}_above_{int(level)}"
            if quote.price >= level:
                current.add(signal)
            elif quote.price < level - exit_buffer:
                current.discard(signal)

    return current


def signal_label(signal: str, cleared: bool = False) -> str:
    labels = {
        "ttf_up_5": "TTF Yahoo 이전 종가 대비 +5% 이상",
        "ttf_down_5": "TTF Yahoo 이전 종가 대비 -5% 이하",
        "ttf_above_50": "TTF 50유로/MWh 상회",
        "ttf_above_60": "TTF 60유로/MWh 상회",
        "ttf_above_70": "TTF 70유로/MWh 상회",
        "ttf_above_80": "TTF 80유로/MWh 상회",
        "brent_up_5": "Brent Yahoo 이전 종가 대비 +5% 이상",
        "brent_down_5": "Brent Yahoo 이전 종가 대비 -5% 이하",
        "brent_above_90": "Brent 90달러/배럴 상회",
        "brent_above_100": "Brent 100달러/배럴 상회",
        "brent_above_120": "Brent 120달러/배럴 상회",
    }
    base = labels.get(signal, signal)
    return f"{base} 종료" if cleared else base


def category_label(category: str) -> str:
    return {
        "qatar_supply": "카타르 LNG 생산·수출",
        "hormuz_shipping": "호르무즈·홍해 운송",
        "europe_storage": "유럽 가스 재고",
        "asia_procurement": "동북아 LNG 조달",
        "korea_supply": "한국 LNG 수급",
    }.get(category, category)


def format_quote(quote: Quote) -> str:
    observed_kst = dt.datetime.fromtimestamp(quote.timestamp_epoch, UTC).astimezone(KST)
    return (
        f"{quote.label} {quote.price:,.2f}{quote.unit} "
        f"(Yahoo 이전 종가 {quote.previous_close:,.2f} 대비 {quote.change_pct:+.2f}%, "
        f"기준 {observed_kst:%Y-%m-%d %H:%M KST}, {quote.age_minutes}분 전)"
    )


def classify_alert_context(
    groups: list[dict[str, object]],
    new_signals: set[str],
    cleared_signals: set[str],
) -> str:
    fundamental_worsening = any(group["polarity"] == "worsening" for group in groups)
    fundamental_easing = any(group["polarity"] == "easing" for group in groups)

    price_stress = any(
        signal.endswith("_up_5") or "_above_" in signal
        for signal in new_signals
    )
    price_relief = any(signal.endswith("_down_5") for signal in new_signals)
    price_relief = price_relief or any("_above_" in signal for signal in cleared_signals)

    if fundamental_worsening and not fundamental_easing:
        return "fundamental_worsening"
    if fundamental_easing and not fundamental_worsening:
        return "fundamental_easing"
    if fundamental_worsening and fundamental_easing:
        return "mixed_fundamental"
    if price_stress and not price_relief:
        return "price_stress_only"
    if price_relief and not price_stress:
        return "price_relief_only"
    return "mixed_or_threshold"


def impact_text(context: str) -> tuple[str, str, str]:
    if context == "fundamental_worsening":
        return (
            "카타르 생산·선적 또는 핵심 해상 통로의 악화가 공식 원문이나 신뢰 매체 교차로 확인됐습니다. "
            "한국은 즉시 물량 고갈보다 현물 LNG 대체구매 단가와 발전연료비 상승이 먼저 나타날 가능성이 큽니다.",
            "돈 버는 능력: LNG 판매자·비호르무즈 공급원 우위, 수입·가스발전 원가 부담. "
            "할인율: 에너지 물가가 금리 인하를 늦출 위험. "
            "수급·시간표: 실제 선적량, 호르무즈 통항, 유럽 저장률로 지속성을 확인합니다.",
            "공급·운송 악화가 확인돼 유럽과 동북아의 LNG 조달 경쟁이 심해질 수 있습니다.",
        )
    if context == "fundamental_easing":
        return (
            "공급·운송 정상화가 공식 원문이나 신뢰 매체 교차로 확인됐습니다. "
            "한국의 현물 조달 프리미엄과 발전연료비 상승 압력은 낮아질 수 있지만 실제 선적 재개가 뒤따라야 합니다.",
            "돈 버는 능력: LNG 부족 수혜주는 되돌림 위험, 수입·가스발전 원가 부담은 완화. "
            "수급·시간표: 발표가 아니라 선적량·통항량·JKM·TTF 후속 하락으로 재검증합니다.",
            "정상화 뉴스가 확인됐으며 실제 물량 회복과 가격 하락의 지속 여부가 최종 확인점입니다.",
        )
    if context == "price_stress_only":
        return (
            "가격 스트레스는 확인됐지만 카타르 선적이나 해상 통로의 추가 악화가 확인된 것은 아닙니다. "
            "한국에는 조달비·발전연료비 상승 압력으로 해석하되 물량 부족으로 단정하지 않습니다.",
            "할인율과 원가에는 부정적이지만, 공급 사건이 확인되지 않은 가격 신호만으로 LNG 생산자 수혜를 확정하지 않습니다.",
            "가격은 악화됐지만 공급·운송의 새 확정 사건은 없습니다.",
        )
    if context == "price_relief_only":
        return (
            "가격 하락은 확인됐지만 공급·운송 정상화가 확인된 것은 아닙니다. "
            "한국의 원가 압력은 단기 완화될 수 있으나 카타르 선적·호르무즈 통항이 그대로면 재상승 위험이 남습니다.",
            "할인율·수입 원가에는 단기 긍정적입니다. 다만 LNG 부족 수혜주의 구조적 논리가 끝났다고 판단할 근거는 아직 없습니다.",
            "가격 완화와 공급 정상화를 분리해서 봐야 하며, 이번 신호만으로 수급 정상화를 단정할 수 없습니다.",
        )
    return (
        "뉴스와 가격이 엇갈리거나 임계값만 이동했습니다. 한국 영향은 확정 수급 자료가 나오기 전 중립적으로 봅니다.",
        "단순 임계값 변화는 투자 방향 신호로 사용하지 않고, 공식 사건·실제 선적·JKM·TTF의 같은 방향 확인을 기다립니다.",
        "임계값 변화만으로는 공급 정상화나 악화를 확정할 수 없습니다.",
    )


def should_alert(
    new_groups: list[dict[str, object]],
    new_signals: set[str],
    cleared_signals: set[str],
) -> bool:
    if new_groups:
        return True
    if new_signals:
        return True
    if any("_above_" in signal for signal in cleared_signals):
        return True
    return False


def build_regular_alert(
    groups: list[dict[str, object]],
    quotes: dict[str, Quote],
    new_signals: set[str],
    cleared_signals: set[str],
) -> tuple[str, str, dict[str, object]]:
    context = classify_alert_context(groups, new_signals, cleared_signals)
    title = "⚠️ LNG·천연가스 수급 경보"
    lines: list[str] = []

    if groups:
        lines.append("[새 확정 변화]")
        for group in groups[:3]:
            polarity = "악화" if group["polarity"] == "worsening" else "완화"
            lines.append(
                f"• {category_label(str(group['category']))}: {polarity} "
                f"({group['verification']})"
            )
            for item in group["evidence"][:2]:
                lines.append(f"  - {item.source}: {item.title}")
                lines.append(f"    {item.link}")
    else:
        lines.append("[새 확정 변화]")
        lines.append("• 공급·운송 관련 새 확정 뉴스 없음")

    if new_signals or cleared_signals:
        lines.extend(["", "[가격 신호]"])
        for signal in sorted(new_signals):
            lines.append(f"• 진입: {signal_label(signal)}")
        for signal in sorted(cleared_signals):
            lines.append(f"• 이탈: {signal_label(signal, cleared=True)}")
        for quote in quotes.values():
            lines.append(f"• {format_quote(quote)}")
        lines.append("• 수치 출처: Yahoo Finance 동일 제공사의 query1/query2 일치값이며 독립 2소스 교차가 아닙니다.")

    korea, investment, one_line = impact_text(context)
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
    metadata = {
        "version": 2,
        "kind": "material_change",
        "context": context,
        "news_event_ids": [group["event_id"] for group in groups],
        "new_market_signals": sorted(new_signals),
        "cleared_market_signals": sorted(cleared_signals),
        "quotes": {key: asdict(quote) for key, quote in quotes.items()},
    }
    return title, "\n".join(lines), metadata


def build_setup_test(quotes: dict[str, Quote]) -> tuple[str, str, dict[str, object]]:
    title = "✅ LNG·천연가스 감시 정확도 규칙 적용"
    lines = [
        "전송 대상: @hs8879887988798879_bot",
        "확인 주기: 매시간 1회",
        "",
        "정확도 규칙:",
        "• 공급·운송 정상화는 공식 원문 1곳 또는 신뢰 매체 2곳으로만 판정",
        "• 가격 하락·-5% 조건 해제를 공급 정상화로 해석하지 않음",
        "• 평일 4시간을 넘긴 시세는 새 신호 판정에서 제외",
        "• ±5% 신호는 ±3%까지 되돌아와야 해제되는 히스테리시스 적용",
        "• 단순 ±5% 조건 해제만으로는 Telegram 미전송",
        "• Yahoo query1/query2는 동일 제공사 대조로 명시",
    ]
    if quotes:
        lines.extend(["", "현재 유효값:"])
        for quote in quotes.values():
            lines.append(f"• {format_quote(quote)}")
    metadata = {
        "version": 2,
        "kind": "setup_test",
        "quotes": {key: asdict(quote) for key, quote in quotes.items()},
    }
    return title, "\n".join(lines), metadata


def load_state() -> dict[str, object]:
    default = {
        "version": 2,
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
    if isinstance(loaded, dict):
        default.update(loaded)
    return default


def clean_outputs() -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    for path in (TITLE_PATH, BODY_PATH, ALERT_JSON_PATH, PENDING_STATE_PATH, TELEGRAM_CONFIRMED_PATH):
        try:
            path.unlink()
        except FileNotFoundError:
            pass


def write_alert(title: str, body: str, metadata: dict[str, object]) -> None:
    TITLE_PATH.write_text(title + "\n", encoding="utf-8")
    BODY_PATH.write_text(body.strip() + "\n", encoding="utf-8")
    ALERT_JSON_PATH.write_text(json.dumps(metadata, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


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
        "# LNG 공급 위기 감시 v2",
        "",
        f"- 실행시각(KST): {timestamp}",
        f"- 신뢰 뉴스 후보: {news_count}건",
        f"- 확정 변화 묶음: {confirmed_count}건",
        f"- 유효 시장값: {quote_count}개",
        f"- Telegram 알림 파일: {'생성' if alert_created else '없음'}",
        f"- 판정: {reason}",
    ]
    if news_errors:
        lines.append(f"- 뉴스 조회 오류: {'; '.join(news_errors[:4])}")
    if market_errors:
        lines.append(f"- 시장값 제외 사유: {'; '.join(market_errors[:4])}")
    SUMMARY_PATH.write_text("\n".join(lines) + "\n", encoding="utf-8")


def finalize() -> int:
    if not PENDING_STATE_PATH.exists():
        print("pending_state=false")
        return 0

    if BODY_PATH.exists() and not TELEGRAM_CONFIRMED_PATH.exists():
        print("telegram_confirmed=false state_not_updated=true")
        return 0

    pending = json.loads(PENDING_STATE_PATH.read_text(encoding="utf-8"))
    STATE_PATH.parent.mkdir(parents=True, exist_ok=True)
    STATE_PATH.write_text(json.dumps(pending, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print("state_updated=true")
    return 0


def run(setup_test: bool) -> int:
    clean_outputs()
    state = load_state()

    news, news_errors = fetch_news_item_set()
    confirmed = confirmed_news_groups(news)
    quotes, market_errors = fetch_market_quotes()

    previous_event_ids = {
        str(value)
        for value in state.get("alerted_event_ids", [])
        if isinstance(value, str)
    }
    previous_signals = {
        str(value)
        for value in state.get("active_market_signals", [])
        if isinstance(value, str)
    }

    current_signals = apply_hysteresis(quotes, previous_signals)
    new_groups = [group for group in confirmed if str(group["event_id"]) not in previous_event_ids]
    new_signals = current_signals - previous_signals
    cleared_signals = previous_signals - current_signals

    pending = dict(state)
    pending["version"] = 2
    pending["active_market_signals"] = sorted(current_signals)

    merged_ids = list(previous_event_ids)
    merged_ids.extend(str(group["event_id"]) for group in new_groups)
    pending["alerted_event_ids"] = merged_ids[-400:]

    alert_created = False
    reason = "새 확정 변화 없음"

    should_test = setup_test and not state.get("setup_test_v2_sent_at_kst")
    if should_test:
        title, body, metadata = build_setup_test(quotes)
        write_alert(title, body, metadata)
        sent_at = dt.datetime.now(KST).isoformat(timespec="seconds")
        pending["setup_test_v2_sent_at_kst"] = sent_at
        pending["last_alert_at_kst"] = sent_at
        alert_created = True
        reason = "v2 정확도 규칙 연결 시험"
    elif should_alert(new_groups, new_signals, cleared_signals):
        title, body, metadata = build_regular_alert(new_groups, quotes, new_signals, cleared_signals)
        write_alert(title, body, metadata)
        pending["last_alert_at_kst"] = dt.datetime.now(KST).isoformat(timespec="seconds")
        alert_created = True
        reason = "새 확정 뉴스 또는 의미 있는 가격 구간 변화"
    else:
        if cleared_signals and not new_groups and not new_signals:
            reason = "노이즈성 ±5% 조건 해제: 상태만 갱신, Telegram 미전송"

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
        f"news={len(news)} confirmed={len(confirmed)} quotes={len(quotes)} "
        f"new_signals={sorted(new_signals)} cleared_signals={sorted(cleared_signals)}"
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
