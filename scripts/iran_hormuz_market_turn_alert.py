# China refined fuel export suspension/resumption watch
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
MIDEAST_EXPORT_SNAPSHOT_URLS = (
    "https://www.reuters.com/business/energy/"
    "mideast-oil-exports-rebound-september-saudi-arabia-boosts-shipments-2026-09-28/",
    "https://in.marketscreener.com/news/"
    "mideast-oil-exports-rebound-in-september-as-saudi-arabia-boosts-shipments-ce785addd888f724",
)
MIDEAST_PRODUCT_GAP_URLS = (
    "https://getnews.co.kr/news/articleView.html?idxno=882308",
    "https://www.moneycontrol.com/news/business/"
    "mideast-crude-oil-flows-hit-98-of-pre-war-level-jpmorgan-says-14041480.html",
    "https://www.businesstimes.com.sg/companies-markets/energy-commodities/"
    "jpmorgan-and-goldman-see-middle-east-oil-flows-near-pre-war-levels/",
)

NEWS_QUERIES = (
    'Iran ceasefire agreement OR Iran truce agreement OR "US Iran ceasefire" when:3d',
    'US ends attacks Iran OR US halts strikes Iran OR US ceases military operations Iran when:3d',
    '"Strait of Hormuz reopens" OR "shipping resumes" Hormuz OR "traffic returns to normal" Hormuz when:3d',
    '"Gulf oil exports" recover OR "Middle East oil exports" rebound OR "Saudi crude shipments" September when:3d',
    '"Middle East oil exports" "highest level since" Iran war Kpler when:3d',
    '"Middle East crude exports" Kpler September highest since war when:3d',
    '"16.328 million barrels per day" Middle East exports Kpler when:3d',
    '"Hormuz" "9.719 million bpd" Kpler September when:3d',
    '"Saudi Arabia ramps up Gulf oil exports" OR "Aramco to boost Gulf exports" when:7d',
    '"Gulf of Oman" STS record OR "ship-to-ship" Oman Saudi crude when:7d',
    'Kpler "Gulf of Oman" STS bottlenecks VLCC when:7d',
    '"Hormuz oil shipments" six-month high OR "record oil" Hormuz when:7d',
    '"East-West Pipeline" 3.5 million barrels per day Saudi when:3d',
    '"East-West Pipeline" pumping 3.5 million bpd Yanbu when:3d',
    '"East-West Pipeline" 4 million bpd Yanbu Saudi when:3d',
    '"Yanbu" crude loadings resume East-West Pipeline when:3d',
    '"Middle East crude exports" September Kpler Reuters when:3d',
    '"Hormuz" "80% of prewar" oil flows Kpler when:3d',
    '"Middle East crude" 98% pre-war JPMorgan when:3d',
    '"17.5 million barrels" JPMorgan Middle East oil when:3d',
    '"product flows" 58% diesel gasoline JPMorgan Middle East when:3d',
    'JP모건 중동 원유 수출 98% 정제유 58% when:3d',
    '"diesel export ban" Trump White House when:3d',
    '"diesel export restrictions" voluntary US when:3d',
    '"diesel export ban" considering Trump when:3d',
    '"still considering diesel export ban" Trump Reuters when:3d',
    '미국 디젤 수출 금지 검토 백악관 when:3d',
    '"Chinese refiners suspend" fuel exports PetroChina when:3d',
    '"China" fuel exports resume PetroChina October 7 when:7d',
    '"China" refined product exports suspended Beijing green light when:7d',
    '"China" gasoline jet fuel cargoes cancelled PetroChina when:7d',
    '중국 정유사 정제품 수출 중단 페트로차이나 when:7d',
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
    "business times",
    "moneycontrol",
    "livemint",
    "mint",
    "news1",
    "marketscreener",
    "s&p global",
    "platts",
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
    "crude_product_divergence": "중동 원유 98% 회복·정제품 병목",
    "us_diesel_export_policy": "미국 디젤 수출정책 단계 변화",
    "china_fuel_export_policy": "중국 정제품 수출정책 단계 변화",
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
    "usdkrw": SymbolSpec("KRW=X", "원·달러", "원/달러"),
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
    if not low:
        return None

    diesel_policy_context = any(
        term in low
        for term in (
            "diesel export ban", "diesel-export ban", "diesel export restriction",
            "diesel-export restriction", "diesel export cap", "diesel-export cap",
            "디젤 수출 금지", "디젤 수출 제한", "경유 수출 금지", "경유 수출 제한",
        )
    )
    us_policy_actor = any(
        term in low
        for term in (
            "white house", "trump", "u.s.", "united states", "energy secretary",
            "백악관", "트럼프", "미국", "에너지장관",
        )
    )
    if diesel_policy_context and us_policy_actor:
        return "us_diesel_export_policy"

    china_context = any(term in low for term in ("china", "chinese", "beijing", "petrochina", "sinopec", "zhejiang petrochemical", "중국", "베이징", "페트로차이나", "시노펙"))
    china_product_export_context = any(term in low for term in (
        "fuel exports", "oil product exports", "refined product exports",
        "gasoline exports", "diesel exports", "jet fuel exports",
        "product shipments", "fuel shipments",
        "정제품 수출", "석유제품 수출", "경유 수출", "휘발유 수출", "항공유 수출",
    ))
    china_policy_change = any(term in low for term in (
        "suspend", "suspended", "suspension", "halt", "halts", "halted",
        "cancel", "cancels", "cancelled", "canceled", "no green light",
        "restrict", "restriction", "curb", "curbs",
        "resume", "resumes", "resumed", "reopen", "restart", "allow", "permits", "permitting",
        "중단", "보류", "취소", "제한", "재개", "허용", "승인",
    ))
    if china_context and china_product_export_context and china_policy_change:
        return "china_fuel_export_policy"

    jpmorgan_recovery_context = (
        ("jpmorgan" in low or "jp모건" in low or "jp 모건" in low)
        and any(term in low for term in ("middle east", "mideast", "중동"))
        and any(term in low for term in ("98% of pre-war", "98% of prewar", "98% 복구", "98% 회복", "17.5 million"))
    )
    product_gap_context = (
        any(term in low for term in ("product flows", "refined product", "diesel and gasoline", "정제유", "정제품"))
        and any(term in low for term in ("58%", "3 million", "3.0 mbd"))
    )
    if jpmorgan_recovery_context or product_gap_context:
        return "crude_product_divergence"

    if any(phrase in low for phrase in NEGATIVE_OR_TENTATIVE_PHRASES):
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
    if any(term in low for term in regional_export_phrases):
        has_volume = re.search(
            r"\b(?:[1-9]|1[0-9]|2[0-9])(?:\.[0-9]+)?\s*(?:million\s+(?:barrels\s+per\s+day|bpd)|mbd)\b",
            low,
            flags=re.I,
        ) is not None
        has_recovery_context = any(term in low for term in (
            "highest since", "rebound", "recover", "recovered", "prewar", "pre-war",
            "전쟁 이전", "전쟁 전", "전쟁 후 최고", "snapshot"
        ))
        if has_volume and has_recovery_context:
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


def parse_mideast_export_snapshot(raw_html: str, current: dt.datetime, source_url: str) -> NewsItem:
    text = _visible_text(raw_html)

    current_patterns = (
        r"rebounded\s+in\s+September\s+to\s+([0-9.]+)\s+million\s+barrels\s+per\s+day",
        r"rebounded\s+in\s+September\s+to\s+([0-9.]+)\s+million\s+bpd",
        r"Middle\s+East\s+crude\s+exports.*?([0-9.]+)\s+million\s+(?:barrels\s+per\s+day|bpd)",
    )
    hormuz_patterns = (
        r"Strait\s+of\s+Hormuz.*?(?:about|approximately)?\s*([0-9.]+)\s+million\s+bpd",
        r"exports\s+via\s+the\s+Strait\s+of\s+Hormuz.*?([0-9.]+)\s+million\s+bpd",
    )
    feb_patterns = (
        r"from\s+([0-9.]+)\s+million\s+bpd\s+in\s+February",
        r"below\s+the\s+([0-9.]+)\s+million\s+bpd.*?February",
        r"([0-9.]+)\s+million\s+bpd\s+in\s+February",
    )
    saudi_patterns = (
        r"Saudi\s+Arabia.*?ship\s+about\s+([0-9.]+)\s+million\s+bpd",
        r"Saudi\s+Arabia.*?exports.*?([0-9.]+)\s+million\s+bpd",
    )
    ras_patterns = (
        r"Ras\s+Tanura.*?about\s+([0-9.]+)\s+million\s+bpd",
        r"Ras\s+Tanura.*?([0-9.]+)\s+million\s+bpd",
    )

    def first_number(patterns: tuple[str, ...]) -> float | None:
        for pattern in patterns:
            match = re.search(pattern, text, flags=re.I | re.S)
            if match:
                return float(match.group(1))
        return None

    current_mbd = first_number(current_patterns)
    hormuz_mbd = first_number(hormuz_patterns)
    feb_mbd = first_number(feb_patterns)
    saudi_mbd = first_number(saudi_patterns)
    ras_mbd = first_number(ras_patterns)

    if current_mbd is None or hormuz_mbd is None or feb_mbd is None:
        raise RuntimeError(
            f"regional export snapshot metrics missing current={current_mbd} "
            f"hormuz={hormuz_mbd} feb={feb_mbd}"
        )
    if not (5.0 <= current_mbd <= 25.0 and 2.0 <= hormuz_mbd <= 20.0 and 10.0 <= feb_mbd <= 30.0):
        raise RuntimeError(
            f"regional export snapshot out of range current={current_mbd} "
            f"hormuz={hormuz_mbd} feb={feb_mbd}"
        )
    if current_mbd > feb_mbd * 1.25:
        raise RuntimeError(
            f"regional export snapshot implausible current={current_mbd} feb={feb_mbd}"
        )

    gap_mbd = feb_mbd - current_mbd
    recovery_pct = current_mbd / feb_mbd * 100.0 if feb_mbd else 0.0
    extras = []
    if saudi_mbd is not None:
        extras.append(f"Saudi {saudi_mbd:.3f} Mbd")
    if ras_mbd is not None:
        extras.append(f"RasTanura {ras_mbd:.3f} Mbd")
    extra_text = "; " + "; ".join(extras) if extras else ""

    title = (
        f"Middle East crude exports snapshot {current_mbd:.3f} Mbd; "
        f"Hormuz {hormuz_mbd:.3f} Mbd; February {feb_mbd:.3f} Mbd; "
        f"gap {gap_mbd:.3f} Mbd; recovery {recovery_pct:.1f}%"
        f"{extra_text}; preliminary Kpler data may revise"
    )
    return NewsItem(
        title=title,
        source="Reuters/Kpler",
        link=source_url,
        published_utc=current.isoformat().replace("+00:00", "Z"),
        published_epoch=current.timestamp(),
        event_kind="regional_export_recovery",
    )


def fetch_mideast_export_snapshot(current: dt.datetime) -> NewsItem:
    errors: list[str] = []
    for url in MIDEAST_EXPORT_SNAPSHOT_URLS:
        try:
            raw = fetch_bytes(url, timeout=25, attempts=2).decode("utf-8", errors="replace")
            return parse_mideast_export_snapshot(raw, current, url)
        except Exception as exc:
            errors.append(f"{url}: {type(exc).__name__}: {exc}")
    raise RuntimeError(" | ".join(errors))


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

    try:
        items.append(fetch_mideast_export_snapshot(current))
    except Exception as exc:
        errors.append(f"Reuters/Kpler regional direct: {type(exc).__name__}: {exc}")

    try:
        items.append(fetch_jpmorgan_product_gap_snapshot(current))
    except Exception as exc:
        errors.append(f"JPMorgan crude/product direct: {type(exc).__name__}: {exc}")

    unique: dict[tuple[str, str, str], NewsItem] = {}
    for item in items:
        key = (normalize_text(item.source), normalize_text(item.title), item.event_kind)
        unique[key] = item
    return sorted(unique.values(), key=lambda item: item.published_epoch, reverse=True), errors


def confirm_events(items: list[NewsItem], minimum_sources: int = 2) -> list[tuple[str, list[NewsItem]]]:
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
            "kpler" in normalize_text(row.source)
            for row in selected
        )
        broker_snapshot = kind == "crude_product_divergence" and any(
            "jpmorgan via bloomberg" in normalize_text(row.source)
            for row in selected
        )
        pipeline_cross_checked = kind == "east_west_pipeline_recovery" and len(selected) >= minimum_sources

        if len(selected) >= minimum_sources or has_primary_data or regional_primary or broker_snapshot or pipeline_cross_checked:
            candidates.append((max(row.published_epoch for row in selected), kind, selected))

    candidates.sort(key=lambda value: value[0], reverse=True)
    return [
        (kind, sorted(selected, key=lambda item: item.published_epoch, reverse=True)[:3])
        for _, kind, selected in candidates
    ]


def confirm_event(items: list[NewsItem], minimum_sources: int = 2) -> tuple[str, list[NewsItem]] | None:
    events = confirm_events(items, minimum_sources)
    return events[0] if events else None


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
        finite_number(meta.get("regularMarketPreviousClose"))
        or finite_number(meta.get("previousClose"))
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
    parsed: list[Quote] = []
    errors: list[str] = []
    for base in YAHOO_BASES:
        url = f"{base}/{urllib.parse.quote(spec.symbol, safe='')}?{params}"
        try:
            parsed.append(parse_yahoo_payload(fetch_json(url), spec))
        except Exception as exc:
            errors.append(str(exc))

    if len(parsed) != 2:
        raise RuntimeError(
            f"{spec.symbol} 2개 Yahoo 엔드포인트 교차검증 실패: {' | '.join(errors)}"
        )

    first, second = parsed
    price_gap = abs(first.price - second.price) / max(abs(first.price), abs(second.price), 1e-9)
    prev_gap = abs(first.previous_close - second.previous_close) / max(
        abs(first.previous_close), abs(second.previous_close), 1e-9
    )
    time_gap = abs(first.timestamp_epoch - second.timestamp_epoch)
    if price_gap > 0.002 or prev_gap > 0.002 or time_gap > 300:
        raise RuntimeError(
            f"{spec.symbol} Yahoo 불일치 "
            f"price={price_gap:.3%} prev={prev_gap:.3%} time={time_gap:.0f}s"
        )
    return first


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

    if kind == "us_diesel_export_policy":
        stage = _diesel_policy_stage(combined)
        basis = f"{kind}|{stage}"
        return f"{kind}:{hashlib.sha256(basis.encode('utf-8')).hexdigest()[:16]}"

    if kind == "china_fuel_export_policy":
        stage = _china_fuel_export_stage(combined)
        basis = f"{kind}|{stage}"
        return f"{kind}:{hashlib.sha256(basis.encode('utf-8')).hexdigest()[:16]}"

    if kind == "crude_product_divergence":
        metrics = _extract_crude_product_gap_metrics(rows)
        crude_pct = float(metrics.get("crude_pct") or 0.0)
        product_pct = float(metrics.get("product_pct") or 0.0)
        crude_band = int(crude_pct // 5 * 5) if crude_pct else 0
        product_band = int(product_pct // 5 * 5) if product_pct else 0
        basis = f"{kind}|crude_{crude_band}|products_{product_band}"
        return f"{kind}:{hashlib.sha256(basis.encode('utf-8')).hexdigest()[:16]}"

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
        volume_band = round(max_value * 4.0) / 4.0 if max_value > 0 else 0.0
        prewar = "prewar80" if (
            "80% of prewar" in combined or "80% of pre-war" in combined or "80% 회복" in combined
        ) else "no80"
        basis = f"{kind}|mbd_{volume_band:.2f}|{prewar}"
        return f"{kind}:{hashlib.sha256(basis.encode('utf-8')).hexdigest()[:16]}"

    if kind == "india_gulf_import_recovery":
        values = [
            float(value)
            for value in re.findall(
                r"\b([0-9]+(?:\.[0-9]+)?)\s*(?:mb/d|mbd|million\s+bpd|million\s+barrels\s+per\s+day)\b",
                combined,
                flags=re.I,
            )
        ]
        max_value = max(values) if values else 0.0
        volume_band = int(max_value * 4) / 4.0 if max_value > 0 else 0.0
        basis = f"{kind}|mbd_{volume_band:.2f}"
        return f"{kind}:{hashlib.sha256(basis.encode('utf-8')).hexdigest()[:16]}"

    if kind == "east_west_pipeline_recovery":
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
        basis = f"{kind}|{band}|{yanbu}"
        return f"{kind}:{hashlib.sha256(basis.encode('utf-8')).hexdigest()[:16]}"

    if kind in ("oil_flow_recovery", "sts_reroute_expansion"):
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
            markers.append(
                f"sts_mbd_{int(max_volume)}" if kind == "sts_reroute_expansion"
                else f"flow_mbd_{int(max_volume)}"
            )
        if not markers:
            markers = [kind]
        basis = f"{kind}|{'|'.join(sorted(set(markers)))}"
        return f"{kind}:{hashlib.sha256(basis.encode('utf-8')).hexdigest()[:16]}"

    day = dt.datetime.fromtimestamp(
        max(row.published_epoch for row in rows), tz=UTC
    ).astimezone(KST).date().isoformat()
    sources = ",".join(sorted(normalize_text(row.source) for row in rows))
    digest = hashlib.sha256(f"{kind}|{day}|{sources}".encode("utf-8")).hexdigest()[:16]
    return f"{kind}:{day}:{digest}"


def _parse_kst_timestamp(raw: object) -> dt.datetime | None:
    if not raw:
        return None
    try:
        value = dt.datetime.fromisoformat(str(raw))
    except ValueError:
        return None
    if value.tzinfo is None:
        value = value.replace(tzinfo=KST)
    return value.astimezone(KST)


def event_recently_alerted(
    state: dict,
    current_event_id: str,
    current: dt.datetime,
    hours: int = 336,
) -> bool:
    alerted = state.get("alerted_events")
    if isinstance(alerted, dict):
        previous = _parse_kst_timestamp(alerted.get(current_event_id))
        if previous is not None:
            return (current.astimezone(KST) - previous).total_seconds() < hours * 3600

    if state.get("last_event_id") == current_event_id:
        previous = _parse_kst_timestamp(state.get("last_alert_at_kst"))
        if previous is None:
            return True
        return (current.astimezone(KST) - previous).total_seconds() < hours * 3600
    return False


def build_pending_state(
    state: dict,
    current_event_id: str,
    kind: str,
    current: dt.datetime,
    market: dict,
) -> dict:
    alerted = dict(state.get("alerted_events") or {})
    now_kst = current.astimezone(KST)
    cutoff = now_kst - dt.timedelta(days=45)
    cleaned: dict[str, str] = {}
    for key, raw in alerted.items():
        stamp = _parse_kst_timestamp(raw)
        if stamp is not None and stamp >= cutoff:
            cleaned[str(key)] = stamp.isoformat(timespec="seconds")
    cleaned[current_event_id] = now_kst.isoformat(timespec="seconds")
    return {
        "last_alert_at_kst": now_kst.isoformat(timespec="seconds"),
        "last_event_kind": kind,
        "last_event_id": current_event_id,
        "alerted_events": cleaned,
        "last_market": market,
    }


def select_unalerted_event(
    state: dict,
    candidates: list[tuple[str, list[NewsItem]]],
    current: dt.datetime,
) -> tuple[tuple[str, list[NewsItem], str] | None, list[str]]:
    duplicate_labels: list[str] = []
    for candidate_kind, candidate_rows in candidates:
        candidate_id = event_id(candidate_kind, candidate_rows)
        if event_recently_alerted(state, candidate_id, current):
            duplicate_labels.append(EVENT_LABELS.get(candidate_kind, candidate_kind))
            continue
        return (candidate_kind, candidate_rows, candidate_id), duplicate_labels
    return None, duplicate_labels


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
    if quote.symbol == "KRW=X":
        won = "원화 약세" if quote.change > 0 else "원화 강세" if quote.change < 0 else "보합"
        return (
            f"- {quote.label}: {quote.price:,.2f}원 "
            f"(전 거래일 {quote.previous_close:,.2f}원, "
            f"{fmt_signed(quote.change_pct, 2, '%')}, {won})"
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


def parse_jpmorgan_product_gap_snapshot(
    raw_html: str,
    current: dt.datetime,
    source_url: str,
) -> NewsItem:
    text = _visible_text(raw_html)
    crude = re.search(
        r"(?:shipments\s+of\s+crude\s+oil.*?|crude\s+(?:oil\s+)?(?:flows|shipments).*?)"
        r"([0-9]+(?:\.[0-9]+)?)\s+million\s+barrels\s+(?:a|per)\s+day.*?"
        r"([0-9]+(?:\.[0-9]+)?)\s*%\s+of\s+pre-war",
        text, flags=re.I,
    )
    products = re.search(
        r"(?:flows|shipments)\s+of\s+(?:oil\s+)?products.*?"
        r"([0-9]+(?:\.[0-9]+)?)\s+million\s+barrels\s+(?:a|per)\s+day.*?"
        r"([0-9]+(?:\.[0-9]+)?)\s*%",
        text, flags=re.I,
    )
    if not products:
        products = re.search(
            r"products\s+such\s+as\s+diesel\s+and\s+(?:gasoline|petrol).*?"
            r"([0-9]+(?:\.[0-9]+)?)\s+million\s+barrels\s+(?:a|per)\s+day.*?"
            r"([0-9]+(?:\.[0-9]+)?)\s*%",
            text, flags=re.I,
        )
    overall = re.search(r"overall\s+figure\s+was\s+([0-9]+(?:\.[0-9]+)?)\s*%\s+of\s+2025", text, flags=re.I)
    hormuz = re.search(
        r"(?:Hormuz|Strait\s+of\s+Hormuz).*?(?:nearly|about|almost)?\s*"
        r"([0-9]+(?:\.[0-9]+)?)\s+million\s+barrels\s+(?:a|per)\s+day",
        text, flags=re.I,
    )
    if not crude or not products:
        raise RuntimeError("JPMorgan crude/product gap metrics not found")
    crude_mbd = float(crude.group(1))
    crude_pct = float(crude.group(2))
    product_mbd = float(products.group(1))
    product_pct = float(products.group(2))
    overall_pct = float(overall.group(1)) if overall else None
    hormuz_mbd = float(hormuz.group(1)) if hormuz else None
    extra = []
    if overall_pct is not None:
        extra.append(f"overall {overall_pct:.0f}% of 2025")
    if hormuz_mbd is not None:
        extra.append(f"Hormuz {hormuz_mbd:.1f} Mbd")
    suffix = "; " + "; ".join(extra) if extra else ""
    title = (
        f"JPMorgan Middle East crude/product snapshot crude {crude_mbd:.1f} Mbd "
        f"{crude_pct:.0f}% pre-war; products {product_mbd:.1f} Mbd "
        f"{product_pct:.0f}% pre-war{suffix}"
    )
    return NewsItem(
        title=title,
        source="JPMorgan via Bloomberg",
        link=source_url,
        published_utc=current.isoformat().replace("+00:00", "Z"),
        published_epoch=current.timestamp(),
        event_kind="crude_product_divergence",
    )


def fetch_jpmorgan_product_gap_snapshot(current: dt.datetime) -> NewsItem:
    errors: list[str] = []
    for url in MIDEAST_PRODUCT_GAP_URLS:
        try:
            raw = fetch_bytes(url, timeout=25, attempts=2).decode("utf-8", errors="replace")
            return parse_jpmorgan_product_gap_snapshot(raw, current, url)
        except Exception as exc:
            errors.append(f"{url}: {type(exc).__name__}: {exc}")
    raise RuntimeError(" | ".join(errors))


def _extract_crude_product_gap_metrics(news_rows: list[NewsItem]) -> dict[str, float | None]:
    text = " ".join(normalize_text(row.title) for row in news_rows)

    crude_pair = re.search(
        r"\bcrude\s+([0-9]+(?:\.[0-9]+)?)\s+mbd\s+([0-9]+(?:\.[0-9]+)?)%\s+pre-war",
        text,
        flags=re.I,
    )
    product_pair = re.search(
        r"\bproducts\s+([0-9]+(?:\.[0-9]+)?)\s+mbd\s+([0-9]+(?:\.[0-9]+)?)%\s+pre-war",
        text,
        flags=re.I,
    )

    def grab(pattern: str) -> float | None:
        match = re.search(pattern, text, flags=re.I)
        return float(match.group(1)) if match else None

    crude_mbd = float(crude_pair.group(1)) if crude_pair else grab(r"\bcrude\s+([0-9]+(?:\.[0-9]+)?)\s+mbd")
    crude_pct = float(crude_pair.group(2)) if crude_pair else grab(r"([0-9]+(?:\.[0-9]+)?)%\s+(?:of\s+)?pre-war")
    product_mbd = float(product_pair.group(1)) if product_pair else grab(r"\bproducts\s+([0-9]+(?:\.[0-9]+)?)\s+mbd")
    product_pct = float(product_pair.group(2)) if product_pair else None
    overall_pct = grab(r"\boverall\s+([0-9]+(?:\.[0-9]+)?)%\s+of\s+2025")
    hormuz_mbd = grab(r"\bhormuz\s+([0-9]+(?:\.[0-9]+)?)\s+mbd")
    return {
        "crude_mbd": crude_mbd, "crude_pct": crude_pct,
        "product_mbd": product_mbd, "product_pct": product_pct,
        "overall_pct": overall_pct, "hormuz_mbd": hormuz_mbd,
        "gap_pp": crude_pct - product_pct if crude_pct is not None and product_pct is not None else None,
    }


def _diesel_policy_stage(text_or_rows: str | list[NewsItem]) -> str:
    text = normalize_text(text_or_rows) if isinstance(text_or_rows, str) else " ".join(normalize_text(row.title) for row in text_or_rows)
    if any(term in text for term in ("takes effect", "effective immediately", "ban effective", "금지 시행", "시행")):
        return "effective"
    if any(term in text for term in ("denies", "denied", "rules out", "not considering", "부인", "검토하지")):
        return "denied"
    if any(term in text for term in ("withdraw", "drops plan", "abandons", "철회", "백지화")):
        return "withdrawn"
    if any(term in text for term in ("announces ban", "announced ban", "imposes ban", "90-day ban", "금지 발표", "금지 결정")):
        return "announced"
    if any(term in text for term in ("voluntary restriction", "voluntary cap", "voluntary limit", "자발적 제한", "자율 제한")):
        return "voluntary"
    if any(term in text for term in ("supports diesel export ban", "backs the idea", "called for", "지지", "요구")):
        return "supports"
    if any(term in text for term in ("considering", "weighs", "weighing", "review", "검토", "논의")):
        return "considering"
    return "policy_change"


def _build_crude_product_gap_alert_body(
    news_rows: list[NewsItem], oil: Quote | None, current: dt.datetime, fx: Quote | None,
) -> str:
    m = _extract_crude_product_gap_metrics(news_rows)
    lines = [current.astimezone(KST).strftime("%Y년 %m월 %d일 %H:%M KST"), "", "[한눈에]"]
    if m.get("crude_mbd") is not None and m.get("crude_pct") is not None:
        lines.append(f"원유          {m['crude_mbd']:.1f} Mbd · 전쟁 전의 {m['crude_pct']:.0f}%")
    if m.get("product_mbd") is not None and m.get("product_pct") is not None:
        lines.append(f"정제품        {m['product_mbd']:.1f} Mbd · 전쟁 전의 {m['product_pct']:.0f}%")
    if m.get("gap_pp") is not None:
        lines.append(f"회복 격차     {m['gap_pp']:.0f}%p · 원유 정상화 ≠ 연료시장 정상화")
    if m.get("hormuz_mbd") is not None:
        lines.append(f"호르무즈      약 {m['hormuz_mbd']:.1f} Mbd")
    if m.get("overall_pct") is not None:
        lines.append(f"전체 흐름     2025년의 {m['overall_pct']:.0f}%")
    market=[]
    if oil is not None:
        direction="↓" if oil.change<0 else "↑" if oil.change>0 else "→"
        market.append(f"Brent USD {oil.price:.2f} {oil.change_pct:+.2f}% {direction}")
    if fx is not None:
        won="약세" if fx.change>0 else "강세" if fx.change<0 else "보합"
        market.append(f"원·달러 {fx.price:,.2f}원 {fx.change_pct:+.2f}% · 원화 {won}")
    if market:
        lines.append("시장          "+" | ".join(market))
    lines.extend([
        "", "[핵심 의미]",
        "원유 자체의 부족은 크게 완화됐지만 경유·휘발유 등 정제품 회복은 훨씬 느립니다.",
        "→ 병목이 원유 물량에서 정제시설·정제품·운송·보험으로 이동하는지 확인해야 합니다.",
        "", "[한국 전이]",
        "정유          정제품 부족이 지속되면 디젤·항공유 정제마진이 원유보다 강할 수 있음",
        "항공·운송     Brent가 내려도 실제 연료비가 같은 속도로 내려가지 않을 수 있음",
        "물가·금리     정제품 가격·원·달러가 높으면 수입물가 완화가 지연될 수 있음",
        "", "[다음 체크]",
        "정제품        58% → 70% → 85% → 95% 회복 여부",
        "실물          호르무즈 약 13 Mbd 유지 · East-West Pipeline 추가 복구",
        "시장          디젤·항공유 정제마진 · VLCC 운임 · Brent · 원·달러",
        "정책          미국 디젤 수출 제한·금지 단계 변화",
        "", "[근거]",
    ])
    for row in news_rows[:3]:
        published=dt.datetime.fromtimestamp(row.published_epoch,tz=UTC).astimezone(KST)
        lines.append(f"{row.source} · {published:%m-%d %H:%M KST}")
        if row.link:
            lines.append(f"원문: {row.link}")
    lines.extend(["", "[주의]", "JP모건 추정치와 Kpler 선박추적치는 집계 범위·다크 플로우 포함 여부가 달라 직접 치환하지 않습니다."])
    return "\n".join(lines).strip()+"\n"


def _build_us_diesel_policy_alert_body(
    news_rows: list[NewsItem], oil: Quote | None, current: dt.datetime, fx: Quote | None,
) -> str:
    stage=_diesel_policy_stage(news_rows)
    labels={"effective":"수출 금지·제한 시행","announced":"수출 금지 발표","supports":"대통령 지지·요구","considering":"정부 검토","voluntary":"정유사 자발적 제한 논의","denied":"전면 금지 보도 부인","withdrawn":"계획 철회","policy_change":"정책 단계 변화"}
    lines=[current.astimezone(KST).strftime("%Y년 %m월 %d일 %H:%M KST"),"","[한눈에]",f"미국 정책     {labels.get(stage,stage)}"]
    if oil is not None:
        direction="↓" if oil.change<0 else "↑" if oil.change>0 else "→"
        lines.append(f"Brent         USD {oil.price:.2f} · {oil.change_pct:+.2f}% {direction}")
    if fx is not None:
        won="약세" if fx.change>0 else "강세" if fx.change<0 else "보합"
        lines.append(f"원·달러       {fx.price:,.2f}원 · {fx.change_pct:+.2f}% · 원화 {won}")
    lines.extend([
        "", "[핵심 의미]",
        "이 사안은 원유 공급이 아니라 글로벌 경유 공급을 직접 바꾸는 정책 변수입니다.",
        "→ 미국 수출이 줄면 해외 디젤 공급은 타이트해질 수 있지만 미국 내 저장이 차면 정유 가동률이 낮아지는 역효과도 가능합니다.",
        "", "[한국 전이]",
        "정유          아시아 디젤 수출 스프레드 확대 가능성 확인",
        "항공·운송     글로벌 경유·항공유 가격 상승 시 비용 부담 확인",
        "물가·금리     정제품 가격 상승이 수입물가·운송비로 전이되는지 확인",
        "", "[다음 체크]",
        "정책          백악관·DOE 공식문구 · 금지/자발제한/철회 · 기간·물량",
        "미국          중간유분 수출·재고 · 정유 가동률",
        "세계          디젤·항공유 가격 · 유럽·중남미 대체조달 · 중국 수출",
        "", "[근거]",
    ])
    for row in news_rows[:3]:
        published=dt.datetime.fromtimestamp(row.published_epoch,tz=UTC).astimezone(KST)
        lines.append(f"{row.source} · {published:%m-%d %H:%M KST} · {row.title}")
        if row.link:
            lines.append(f"원문: {row.link}")
    lines.extend(["","[주의]","검토·지지·자발 제한·금지 발표·실제 시행을 서로 다른 단계로 관리합니다."])
    return "\n".join(lines).strip()+"\n"


def _china_fuel_export_stage(text_or_rows: str | list[NewsItem]) -> str:
    text = normalize_text(text_or_rows) if isinstance(text_or_rows, str) else " ".join(normalize_text(row.title) for row in text_or_rows)
    if any(term in text for term in ("resume", "resumes", "resumed", "reopen", "restart", "allow exports", "permits exports", "green light", "재개", "허용", "승인")):
        return "resumed"
    if any(term in text for term in ("extend", "extended", "until further notice", "연장", "무기한")):
        return "extended"
    if any(term in text for term in ("cancel", "cancels", "cancelled", "canceled", "취소")):
        return "cargo_cancelled"
    if any(term in text for term in ("suspend", "suspended", "suspension", "halt", "halted", "no green light", "중단", "보류")):
        return "suspended"
    if any(term in text for term in ("restrict", "restriction", "curb", "curbs", "제한")):
        return "restricted"
    return "policy_change"


def _build_china_fuel_export_policy_alert_body(
    news_rows: list[NewsItem], oil: Quote | None, current: dt.datetime, fx: Quote | None,
) -> str:
    stage = _china_fuel_export_stage(news_rows)
    labels = {
        "resumed": "수출 재개·허용",
        "extended": "수출 중단·제한 연장",
        "cargo_cancelled": "기존 10월 선적 취소",
        "suspended": "홍콩·마카오 외 수출 중단",
        "restricted": "정제품 수출 제한",
        "policy_change": "정제품 수출정책 변화",
    }
    lines = [
        current.astimezone(KST).strftime("%Y년 %m월 %d일 %H:%M KST"),
        "",
        "[한눈에]",
        f"중국 정책     {labels.get(stage, stage)}",
    ]
    if oil is not None:
        direction = "↓" if oil.change < 0 else "↑" if oil.change > 0 else "→"
        lines.append(f"Brent         USD {oil.price:.2f} · {oil.change_pct:+.2f}% {direction}")
    if fx is not None:
        won = "약세" if fx.change > 0 else "강세" if fx.change < 0 else "보합"
        lines.append(f"원·달러       {fx.price:,.2f}원 · {fx.change_pct:+.2f}% · 원화 {won}")

    lines.extend([
        "",
        "[핵심 의미]",
        "원유가 회복돼도 중국이 경유·휘발유·항공유 수출을 막으면 글로벌 정제품 공급은 다시 타이트해질 수 있습니다.",
        "→ 이번 병목은 원유 부족이 아니라 정제·제품 수출정책 쪽에서 생기는 공급 충격입니다.",
        "",
        "[한국 전이]",
        "정유          아시아 디젤·항공유 정제마진 상승 시 한국 정유사의 수출 스프레드에 우호적",
        "항공·운송     연료비 하락 지연 또는 재상승 위험",
        "물가·금리     정제품 가격 상승이 수입물가·운송비로 전이되는지 확인",
        "",
        "[다음 체크]",
        "중국          10월 7일 연휴 종료 뒤 수출 허용 여부 · PetroChina 취소 물량 재계약 여부",
        "제품          디젤·항공유·휘발유 수출량 · 중국 내 재고 · 정유 가동률",
        "아시아        Singapore gasoil crack · 10~11월 스프레드 · 한국 정유사 수출마진",
        "동시 변수     러시아 디젤 수출금지 · 미국 디젤 수출제한 검토 · 중동 정제품 회복률",
        "",
        "[근거]",
    ])
    for row in news_rows[:3]:
        published = dt.datetime.fromtimestamp(row.published_epoch, tz=UTC).astimezone(KST)
        lines.append(f"{row.source} · {published:%m-%d %H:%M KST} · {row.title}")
        if row.link:
            lines.append(f"원문: {row.link}")
    lines.extend([
        "",
        "[주의]",
        "현재 공개 보도는 관계자 전언 기반입니다. 중국 정부의 공개 명령문이 확인되기 전에는 공식 전면 금지로 표현하지 않습니다.",
    ])
    return "\n".join(lines).strip() + "\n"


def _extract_regional_export_metrics(news_rows: list[NewsItem]) -> dict[str, float | None]:
    text = " ".join(normalize_text(row.title) for row in news_rows)

    snapshot = re.search(
        r"middle east crude exports snapshot\s+([0-9.]+)\s+mbd;\s*"
        r"hormuz\s+([0-9.]+)\s+mbd;\s*"
        r"february\s+([0-9.]+)\s+mbd;\s*"
        r"gap\s+([0-9.]+)\s+mbd;\s*recovery\s+([0-9.]+)%",
        text,
        flags=re.I,
    )
    if snapshot:
        return {
            "current_mbd": float(snapshot.group(1)),
            "hormuz_mbd": float(snapshot.group(2)),
            "feb_mbd": float(snapshot.group(3)),
            "gap_mbd": float(snapshot.group(4)),
            "recovery_pct": float(snapshot.group(5)),
        }

    def find_value(pattern: str):
        match = re.search(pattern, text, flags=re.I)
        return float(match.group(1)) if match else None

    current = find_value(
        r"(?:middle east|mideast).*?([0-9]+(?:\.[0-9]+)?)\s*"
        r"(?:million\s+bpd|million\s+barrels\s+per\s+day|mbd)"
    )
    feb = find_value(
        r"(?:february|prewar|pre-war).*?([0-9]+(?:\.[0-9]+)?)\s*"
        r"(?:million\s+bpd|million\s+barrels\s+per\s+day|mbd)"
    )
    hormuz = find_value(
        r"hormuz.*?([0-9]+(?:\.[0-9]+)?)\s*"
        r"(?:million\s+bpd|million\s+barrels\s+per\s+day|mbd)"
    )
    gap = feb - current if feb is not None and current is not None else None
    recovery = current / feb * 100.0 if feb and current is not None else None
    return {
        "current_mbd": current,
        "feb_mbd": feb,
        "hormuz_mbd": hormuz,
        "gap_mbd": gap,
        "recovery_pct": recovery,
    }


def _extract_india_gulf_metrics(news_rows: list[NewsItem]) -> dict[str, float | None]:
    text = " ".join(normalize_text(row.title) for row in news_rows)
    nums = [float(v) for v in re.findall(r"\b([0-9]+(?:\.[0-9]+)?)\s*(?:mb/d|mbd|million\s+bpd)", text)]
    current = max(nums) if nums else None
    return {"current_mbd": current}



def _build_sts_compact_alert_body(
    news_rows: list[NewsItem],
    oil: Quote | None,
    current: dt.datetime,
    fx: Quote | None,
    metrics: dict[str, object],
) -> str:
    lines = [
        current.astimezone(KST).strftime("%Y년 %m월 %d일 %H:%M KST"),
        "",
        "[한눈에]",
        "원유 공급     회복 ↑",
        "물류 효율     병목 심화 ↓",
        (
            f"GoO STS       {float(metrics['current_mbd']):.1f} Mbd · "
            f"전쟁 후 평균 {float(metrics['since_war_mbd']):.1f} · "
            f"2025 평균 {float(metrics['baseline_2025_mbd']):.2f}"
        ),
    ]
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

    market_bits: list[str] = []
    if oil is not None:
        direction = "↓" if oil.change < 0 else "↑" if oil.change > 0 else "→"
        market_bits.append(f"Brent USD {oil.price:.2f} · {oil.change_pct:+.2f}% {direction}")
    if fx is not None:
        won = "약세" if fx.change > 0 else "강세" if fx.change < 0 else "보합"
        market_bits.append(f"원·달러 {fx.price:,.2f}원 · {fx.change_pct:+.2f}% · 원화 {won}")
    if market_bits:
        lines.append("시장          " + " | ".join(market_bits))

    lines.extend([
        "",
        "[핵심 의미]",
        "원유는 회복 중이지만 정상 항로 복귀가 아니라 GoO STS 우회입니다.",
        "→ 유가 하방 가능 / VLCC 운임·물류비 상방 가능 · 수출 회복 ≠ 물류 정상화",
        "",
        "[한국 전이]",
    ])
    if oil is not None and fx is not None:
        if oil.change < 0 and fx.change <= 0:
            lines.append("현재          유가 ↓ + 원화 강세/안정 → 수입물가·에너지 원가·금리 부담 완화")
        elif oil.change < 0 and fx.change > 0:
            lines.append("현재          유가 ↓ + 원화 약세 → 수입원가 완화 효과 일부 상쇄")
        elif oil.change > 0 and fx.change > 0:
            lines.append("현재          유가 ↑ + 원화 약세 → 수입물가·금리·기업 원가 부담 확대")
        else:
            lines.append("현재          유가·환율 신호 엇갈림 → 업종별 실적 영향 차별화")
    elif oil is not None:
        lines.append("현재          유가 방향 확인 · 원·달러 검증값 부재로 국내 전이 숫자 판정 보류")
    else:
        lines.append("현재          유가·원·달러 동시 검증 부재 · 국내 전이는 정성 판단만 유지")

    if fx is not None and fx.change < 0:
        lines.append("실적          원화 강세는 달러 매출 환산에 부담 · 유가 하락은 항공·전력/가스·운송·석유화학 원가에 완화")
    elif fx is not None and fx.change > 0:
        lines.append("실적          원화 약세는 달러 매출 환산에 우호적 · 원가 민감 업종은 수입비용 부담 확인")
    else:
        lines.append("실적          달러 매출 수출기업과 항공·전력/가스·운송·석유화학 원가 민감 업종을 분리 확인")
    lines.append("다음          원·달러 → 수입물가/CPI → 국고채 금리 → 3분기 실적 가이던스")

    lines.extend([
        "",
        "[병목]",
        "핵심          Fujairah·Sohar 처리능력 · STS 슬롯/예인선/파일럿/검사 · VLCC 회전율",
        "확대 시       서인도 → 말레이시아로 이송거리 확대 · Kpler 최대 58척 시나리오",
        "",
        "[다음 체크]",
        "실물          호르무즈 통과량 · Saudi Gulf/Red Sea 선적 · GoO STS 7일 평균",
        "우회/시장     East-West 3.0→3.5→4.0 Mbd · Yanbu 선적 · VLCC 운임 · Brent · 원·달러",
        "한국          수입물가/CPI · 국고채 금리 · 3분기 기업 실적 가이던스",
        "",
        "[근거]",
    ])

    for row in news_rows[:2]:
        published = dt.datetime.fromtimestamp(row.published_epoch, tz=UTC).astimezone(KST)
        if "kpler" in normalize_text(row.source):
            lines.append(
                f"Kpler · 기준 {metrics['source_date']} · STS {float(metrics['current_mbd']):.1f} Mbd"
            )
        else:
            lines.append(f"{row.source} · {published:%m-%d %H:%M KST}")
        if row.link:
            lines.append(f"원문: {row.link}")

    lines.extend([
        "",
        "[주의]",
        "STS는 같은 배럴이 여러 번 이송될 수 있어 호르무즈 통과량·중동 전체 수출량과 합산하지 않습니다.",
        "정책 발언 처리: 실물 물량·통항 데이터 없이 '정상화'로 판정하지 않습니다.",
    ])
    return "\n".join(lines).strip() + "\n"


def build_physical_flow_alert_body(
    kind: str,
    news_rows: list[NewsItem],
    oil: Quote | None,
    current: dt.datetime,
    fx: Quote | None = None,
) -> str:
    metrics = _extract_kpler_sts_metrics(news_rows)
    if kind == "crude_product_divergence":
        return _build_crude_product_gap_alert_body(news_rows, oil, current, fx)
    if kind == "us_diesel_export_policy":
        return _build_us_diesel_policy_alert_body(news_rows, oil, current, fx)
    if kind == "china_fuel_export_policy":
        return _build_china_fuel_export_policy_alert_body(news_rows, oil, current, fx)
    if kind == "sts_reroute_expansion" and metrics:
        return _build_sts_compact_alert_body(news_rows, oil, current, fx, metrics)

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
        current_mbd = regional.get("current_mbd")
        feb_mbd = regional.get("feb_mbd")
        hormuz_mbd = regional.get("hormuz_mbd")
        gap_mbd = regional.get("gap_mbd")
        recovery_pct = regional.get("recovery_pct")
        lines.append("중동 수출     전쟁 후 최고 수준")
        if current_mbd is not None:
            lines.append(f"핵심 수치     {current_mbd:.3f} Mbd · Reuters/Kpler")
        if hormuz_mbd is not None:
            lines.append(f"호르무즈      {hormuz_mbd:.3f} Mbd")
        if feb_mbd is not None and gap_mbd is not None:
            lines.append(f"비교          2월 {feb_mbd:.3f} Mbd보다 {gap_mbd:.3f} Mbd 낮음")
        if recovery_pct is not None:
            lines.append(f"회복률        2월 대비 {recovery_pct:.1f}%")
        lines.append("해석          잠정 선박추적치는 확인이 붙으며 수정될 수 있음")
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
    if fx is not None:
        won = "약세" if fx.change > 0 else "강세" if fx.change < 0 else "보합"
        lines.append(
            f"원·달러       {fx.price:,.2f}원 · {fx.change_pct:+.2f}% · 원화 {won}"
        )

    lines.extend(["", "[핵심 의미]"])
    if kind == "regional_export_recovery":
        current_mbd = regional.get("current_mbd")
        feb_mbd = regional.get("feb_mbd")
        gap_mbd = regional.get("gap_mbd")
        recovery_pct = regional.get("recovery_pct")
        lines.append("중동 주요 산유국의 원유 수출이 전쟁 이후 최고 수준으로 올라왔습니다.")
        if current_mbd is not None and feb_mbd is not None and gap_mbd is not None:
            lines.append(
                f"→ 최신 Reuters/Kpler 잠정치 {current_mbd:.3f} Mbd · "
                f"2월 {feb_mbd:.3f} Mbd보다 {gap_mbd:.3f} Mbd 낮습니다."
            )
        if recovery_pct is not None:
            lines.append(
                f"→ 현재 회복률은 2월 대비 {recovery_pct:.1f}%입니다. "
                "최근 14일 선박 데이터는 확인이 붙으며 상향 수정될 수 있습니다."
            )
        lines.append("→ 따라서 고정 숫자를 재사용하지 않고 매 실행 최신 잠정치를 다시 읽습니다.")
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

    lines.extend(["", "[한국 전이]"])
    if oil is not None and fx is not None:
        if oil.change < 0 and fx.change <= 0:
            lines.append("유가 ↓ + 원화 강세/안정 → 수입물가·에너지 원가·금리 부담 완화 방향")
        elif oil.change < 0 and fx.change > 0:
            lines.append("유가 ↓ 하지만 원화 약세 → 국내 수입원가 완화 속도는 느려질 수 있음")
        elif oil.change > 0 and fx.change > 0:
            lines.append("유가 ↑ + 원화 약세 → 수입물가·금리·기업 원가 부담이 동시에 커지는 조합")
        else:
            lines.append("유가·환율 신호가 엇갈림 → 국내 실적 영향은 업종별로 갈릴 가능성")
    elif oil is not None:
        lines.append("유가 방향은 확인됐지만 원·달러 검증값이 없어 국내 환율 전이는 숫자 판정 보류")
    else:
        lines.append("유가·원·달러 동시 검증이 없어 국내 전이는 정성 판단만 유지")

    lines.extend([
        "실적 시즌    달러 매출 비중이 큰 수출기업은 원화 약세가 원화 환산 매출에 우호적일 수 있음",
        "원가 민감    항공·전력/가스·운송·석유화학 등은 유가·달러 동반 상승 시 비용 부담 확대",
        "금리 경로    고유가·원화 약세가 수입물가를 끌어올리면 한국은행의 완화 여지가 줄 수 있음",
        "다음 확인    원·달러 → 수입물가/CPI → 국고채 금리 → 3분기 실적 가이던스",
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
        "원·달러",
        "한국 수입물가·CPI·국고채 금리",
        "3분기 기업 실적 가이던스",
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
    confirmed_candidates = confirm_events(news_items)
    if not confirmed_candidates:
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

    selected, duplicate_labels = select_unalerted_event(
        state, confirmed_candidates, current
    )

    if selected is None:
        write_summary(
            [
                "# 이란·호르무즈 시장 전환 감시",
                current.astimezone(KST).strftime("확인 시각: %Y-%m-%d %H:%M KST"),
                "결과: 확인된 사건은 모두 최근에 이미 알린 동일 단계여서 중복 발송하지 않음",
                *[f"- 중복: {label}" for label in duplicate_labels],
            ]
        )
        return 0

    kind, news_rows, current_event_id = selected

    market_errors: list[str] = []
    quotes: dict[str, Quote] = {}
    for key in ("us2y", "dxy", "wti", "brent", "usdkrw"):
        try:
            quotes[key] = fetch_quote(SYMBOLS[key])
        except Exception as exc:
            market_errors.append(f"{key}: {exc}")

    max_age_minutes = int(os.getenv("IRAN_HORMUZ_MARKET_MAX_AGE_MINUTES", "240"))

    physical_kinds = {
        "oil_flow_recovery",
        "sts_reroute_expansion",
        "east_west_pipeline_recovery",
        "regional_export_recovery",
        "crude_product_divergence",
        "us_diesel_export_policy",
        "china_fuel_export_policy",
        "india_gulf_import_recovery",
    }
    if kind in physical_kinds:
        oil = None
        for key in ("brent", "wti"):
            candidate = quotes.get(key)
            if candidate is not None and quote_is_fresh(candidate, current, max_age_minutes):
                oil = candidate
                break
        fx = quotes.get("usdkrw")
        if fx is not None and not quote_is_fresh(fx, current, max_age_minutes):
            fx = None
        body = build_physical_flow_alert_body(kind, news_rows, oil, current, fx)
        if kind == "crude_product_divergence":
            title = "중동 원유 회복·정제품 병목 변화"
        elif kind == "us_diesel_export_policy":
            title = "미국 디젤 수출정책 변화"
        elif kind == "china_fuel_export_policy":
            title = "중국 정제품 수출정책 변화"
        else:
            title = "중동 원유 흐름 회복·우회 물류 변화"
        alert = {
            "test_mode": False,
            "created_at_kst": current.astimezone(KST).isoformat(timespec="seconds"),
            "event_kind": kind,
            "event_label": EVENT_LABELS[kind],
            "event_id": current_event_id,
            "news": [asdict(row) for row in news_rows],
            "market": {
                "oil": asdict(oil) if oil else None,
                "usdkrw": asdict(fx) if fx else None,
            },
        }
        pending_state = build_pending_state(
            state, current_event_id, kind, current, alert["market"]
        )
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
    pending_state = build_pending_state(
        state, current_event_id, kind, current, alert["market"]
    )
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
