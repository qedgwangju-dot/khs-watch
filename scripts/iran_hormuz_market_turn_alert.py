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

NEWS_QUERIES = (
    'Iran ceasefire agreement OR Iran truce agreement OR "US Iran ceasefire" when:3d',
    'US ends attacks Iran OR US halts strikes Iran OR US ceases military operations Iran when:3d',
    '"Strait of Hormuz reopens" OR "shipping resumes" Hormuz OR "traffic returns to normal" Hormuz when:3d',
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
}


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


def fetch_news(current: dt.datetime) -> tuple[list[NewsItem], list[str]]:
    max_age_hours = int(os.getenv("IRAN_HORMUZ_MAX_NEWS_AGE_HOURS", "72"))
    items: list[NewsItem] = []
    errors: list[str] = []
    for query in NEWS_QUERIES:
        try:
            items.extend(parse_rss(fetch_bytes(google_news_url(query)), current, max_age_hours))
        except Exception as exc:
            errors.append(str(exc))

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
        if len(selected) >= minimum_sources:
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
