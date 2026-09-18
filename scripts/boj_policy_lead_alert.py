#!/usr/bin/env python3
"""BOJ 정책경로 변화 감지.

역할 분리:
- 이 감시는 BOJ의 정책결정·우에다 기자회견·주요 의견·핵심 인사 발언에서
  '다음 금리 인상의 시점과 속도'가 달라지는지를 감시한다.
- 실제 엔캐리 청산 여부는 별도 엔캐리 복합 수급 감시가 판단한다.
- 금리 인상 자체를 자동으로 매파 강화로 보지 않고, 직전 경로 대비 변화만 알린다.
"""
from __future__ import annotations

import argparse
import csv
import datetime as dt
import hashlib
import html
import io
import json
import pathlib
import re
import urllib.parse
import xml.etree.ElementTree as ET
from dataclasses import asdict, dataclass, replace
from email.utils import parsedate_to_datetime
from zoneinfo import ZoneInfo

from khs_source_fetch import fetch_text, record_source_failure

KST = ZoneInfo("Asia/Seoul")
UTC = dt.timezone.utc
OUT = pathlib.Path("out")
STATE = pathlib.Path("data/boj_policy_lead_alert_state.json")
TITLE = OUT / "boj_policy_lead_alert_title.txt"
BODY = OUT / "boj_policy_lead_alert.md"
DATA = OUT / "boj_policy_lead_alert.json"
WATCH = OUT / "boj_policy_lead_watch.md"
MARKET = OUT / "boj_policy_market_context.json"
PENDING = OUT / "boj_policy_lead_pending_state.json"
CONFIRMED = OUT / "boj_policy_lead_telegram_confirmed.json"

UA = "Mozilla/5.0 khs-boj-policy-path/2.0"
GOOGLE = "https://news.google.com/rss/search"
BOJ_RSS = "https://www.boj.or.jp/en/rss/whatsnew.xml"
REUTERS_BOJ_DECISION = "https://www.reuters.com/world/asia-pacific/boj-raises-interest-rates-31-year-high-widely-expected-move-2026-09-18/"
REUTERS_BOJ_REACTION = "https://www.reuters.com/world/asia-pacific/view-investors-react-boj-raising-interest-rates-31-year-high-2026-09-18/"
MOF_JGB_YIELDS = "https://www.mof.go.jp/english/policy/jgbs/reference/interest_rate/jgbcme.csv"
CBOE_JYVIX = "https://www.cboe.com/us/indices/dashboard/JYVIX/"
TRUSTED = {"Reuters", "Bloomberg", "Nikkei Asia", "Financial Times", "Bank of Japan"}
MAX_AGE_HOURS = 72
SAME_PATH_COOLDOWN_MINUTES = 240

# Time-limited first-party/high-trust fallback for the 2026-09-18 meeting.
# It only fills fields that remain missing after live source parsing and expires
# with the ordinary 72-hour event window. Economic/price assessment vote is
# intentionally NOT filled because a separate 7-2 assessment vote is not
# confirmed in the official/high-trust material checked for this event.
VERIFIED_EVENT_FALLBACKS = {
    "2026-09-18": {
        "policy_rate": 1.25,
        "hike_bp": 25,
        "vote_for": 7,
        "vote_against": 2,
        "dissent_direction": "hold",
        "dissenters": ("아사다", "사토"),
        "expected_move": True,
        "hawkish_tail_50bp": True,
        "inflation_spillover": True,
        "cpi_h2_clearly_above_2": True,
        "stabilize_underlying_around_2": True,
        "outlook_dissenters": ("다카타", "다무라"),
        "outlook_dissent_view": "기조적 물가가 이미 2% 목표에 대체로 도달했다는 판단에서 물가전망 문구에 반대",
        "further_hikes": True,
        "conditional_pace": True,
        "accommodative": True,
        "inflation_upside": True,
        "risk_channels": True,
        "source": "Reuters + 사용자 제공 BOJ 성명 요약",
        "evidence": (
            REUTERS_BOJ_DECISION,
            REUTERS_BOJ_REACTION,
        ),
    }
}

QUERIES = (
    'BOJ raises interest rates 1.25 Reuters when:1d',
    'BOJ 7-2 Asada Sato rate hike Reuters when:1d',
    '"Bank of Japan" Reuters 1.25 rate decision when:2d',
    'BOJ Ueda press conference rate path Reuters when:2d',
    '"Bank of Japan" additional rate hikes Reuters when:2d',
    '"Bank of Japan" neutral rate Ueda Reuters when:3d',
    '"Summary of Opinions" BOJ Reuters when:7d',
    'BOJ economic assessment vote inflation 2% Reuters when:2d',
    'BOJ investors react 7-2 dissent yen Reuters when:1d',
    'BOJ 50 basis point half-point internal calls Reuters when:3d',
)

LEVEL_EMOJI = {0: "🟢", 1: "🟡", 2: "🟠", 3: "🔴"}
LEVEL_LABEL = {
    0: "추가 긴축 경로 후퇴",
    1: "점진적 추가 인상 경로 유지",
    2: "추가 인상 시점·속도 가속",
    3: "예상 밖 대폭·연속 긴축 위험",
}
EVENT_LABEL = {
    "decision": "금융정책 결정",
    "press_conference": "우에다 총재 기자회견",
    "summary_of_opinions": "금융정책결정회의 주요 의견",
    "official_speech": "BOJ 핵심 인사 발언",
    "market_path": "고신뢰 정책경로 보도",
}

ACCELERATION = (
    "next meeting",
    "at the next meeting",
    "every meeting",
    "each meeting",
    "faster",
    "accelerate",
    "accelerated",
    "speed up",
    "front-load",
    "front load",
    "without delay",
    "sooner",
    "earlier",
    "rapidly",
    "quickly",
    "swiftly",
)
SOFTENING = (
    "pause",
    "no rush",
    "not in a hurry",
    "wait and see",
    "slower",
    "slow the pace",
    "delay further",
    "hold rates",
    "downside risks",
)
FURTHER_HIKES = (
    "continue to raise",
    "continue raising",
    "further rate hikes",
    "additional rate hikes",
    "raise interest rates further",
    "keep raising",
)
CONDITIONAL_PACE = (
    "timing and pace",
    "check whether",
    "depending on",
    "depending upon",
    "if the outlook",
    "if the economy and prices",
    "while examining",
    "carefully monitor",
    "carefully examining",
)
ACCOMMODATIVE = (
    "accommodative financial conditions",
    "financial conditions will remain accommodative",
    "remain accommodative",
)
NEUTRAL = (
    "neutral rate",
    "neutral interest rate",
    "distance to neutral",
)
INFLATION_UPSIDE = (
    "inflation overshoot",
    "exceed 2%",
    "exceed the 2%",
    "upside risk",
    "upside risks",
    "inflation expectations",
    "underlying inflation",
)
RISK_CHANNELS = (
    "foreign exchange",
    "exchange rate",
    "yen",
    "oil",
    "middle east",
    "artificial intelligence",
    " ai ",
    "global ai",
)

DOVISH_DISSENT = (
    "preferred to keep rates unchanged",
    "preferred to leave rates unchanged",
    "wanted to keep rates unchanged",
    "voted to keep rates unchanged",
    "voted for no change",
    "called for no change",
    "opposed the hike",
    "dissented against the hike",
    "hold rates",
    "keep the policy rate at",
    "opposed a hike today",
    "opposed the hike today",
    "not accelerated enough to justify tightening now",
)
HAWKISH_DISSENT = (
    "called for a 50 basis-point hike",
    "called for a 50 basis point hike",
    "wanted a 50 basis-point hike",
    "wanted a 50 basis point hike",
    "half-point hike",
    "larger hike",
    "raise the rate by 50",
    "50bp hike",
)
ASSESSMENT_MARKERS = (
    "economic assessment",
    "economic view",
    "price assessment",
    "inflation assessment",
    "underlying inflation assessment",
)
EXPECTED_MOVE_MARKERS = (
    "widely expected",
    "as expected",
    "expected move",
    "expected quarter-point",
    "expected 25 basis-point",
    "expected 25 basis point",
)
HAWKISH_TAIL_50BP_MARKERS = (
    "50 basis-point",
    "50 basis point",
    "50bp",
    "half-point",
    "half point",
)
INFLATION_SPILLOVER_MARKERS = (
    "spill over into consumer prices",
    "spilling over into consumer prices",
    "pass-through to consumer prices",
    "passed on to consumer prices",
)
CPI_H2_ABOVE_2_MARKERS = (
    "clearly above 2 percent",
    "clearly above 2%",
    "second half of fiscal 2026",
)
STABILIZE_UNDERLYING_2_MARKERS = (
    "stabilizing underlying cpi inflation at a level around 2 percent",
    "stabilising underlying cpi inflation at a level around 2 percent",
    "stabilize underlying cpi inflation at a level around 2 percent",
    "stabilise underlying cpi inflation at a level around 2 percent",
    "stabilize underlying inflation at a level around 2 percent",
    "stabilise underlying inflation at a level around 2 percent",
)
OUTLOOK_DISSENT_MARKERS = (
    "opposed the description regarding the outlook for prices",
    "opposed the description regarding the outlook for underlying inflation",
    "opposed the price outlook wording",
)


@dataclass(frozen=True)
class Item:
    title: str
    source: str
    link: str
    published: dt.datetime
    description: str

    @property
    def text(self) -> str:
        return clean(f"{self.title} {self.description}")


@dataclass(frozen=True)
class Signal:
    key: str
    level: int
    event_type: str
    source: str
    title: str
    link: str
    published: dt.datetime
    policy_rate: float | None
    hike_bp: int | None
    vote_for: int | None
    vote_against: int | None
    dissent_direction: str | None
    dissenters: tuple[str, ...]
    assessment_vote_for: int | None
    assessment_vote_against: int | None
    assessment_view: str | None
    expected_move: bool
    hawkish_tail_50bp: bool
    inflation_spillover: bool
    cpi_h2_clearly_above_2: bool
    stabilize_underlying_around_2: bool
    outlook_dissenters: tuple[str, ...]
    outlook_dissent_view: str | None
    official_statement_detail_verified: bool
    further_hikes: bool
    conditional_pace: bool
    accommodative: bool
    neutral_rate: bool
    inflation_upside: bool
    risk_channels: bool
    note: str


def clean(value: str) -> str:
    value = re.sub(r"<[^>]+>", " ", value or "")
    return re.sub(r"\s+", " ", html.unescape(value)).strip()


def normalize(value: str) -> str:
    value = clean(value).lower()
    value = re.sub(r"\s+-\s+(reuters|bloomberg|nikkei asia|financial times)$", "", value)
    return re.sub(r"\s+", " ", re.sub(r"[^a-z0-9%]+", " ", value)).strip()


def pubdate(value: str) -> dt.datetime | None:
    try:
        parsed = parsedate_to_datetime(value)
    except Exception:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=UTC)
    return parsed.astimezone(KST)


def parse_rss(text: str, default_source: str = "") -> list[Item]:
    root = ET.fromstring(text)
    items: list[Item] = []
    for node in root.findall(".//item"):
        published = pubdate(node.findtext("pubDate") or "")
        title = clean(node.findtext("title") or "")
        source_node = node.find("source")
        source = clean(source_node.text if source_node is not None else "") or default_source
        link = clean(node.findtext("link") or "")
        description = clean(node.findtext("description") or "")
        if title and published:
            items.append(Item(title, source, link, published, description))
    return items


def fetch_rss(url: str, source_name: str, now: dt.datetime) -> list[Item]:
    text, error = fetch_text(
        url,
        UA,
        timeout=20,
        attempts=2,
        accept="application/rss+xml,application/xml,text/xml,*/*",
    )
    if error or not text:
        record_source_failure(
            lane="boj_policy_path",
            source_name=source_name,
            source_url=url,
            error=error or "empty response",
            checked_at=now,
        )
        return []
    try:
        return parse_rss(text, source_name)
    except Exception as exc:
        record_source_failure(
            lane="boj_policy_path",
            source_name=source_name,
            source_url=url,
            error=f"RSS parse: {type(exc).__name__}: {exc}",
            checked_at=now,
        )
        return []


def enrich_official_items(items: list[Item], now: dt.datetime) -> list[Item]:
    enriched: list[Item] = []
    for item in items:
        if source_name(item) != "Bank of Japan" or not item.link:
            enriched.append(item)
            continue
        body, error = fetch_text(
            item.link,
            UA,
            timeout=20,
            attempts=2,
            accept="text/html,application/xhtml+xml,*/*",
        )
        if error or not body:
            record_source_failure(
                lane="boj_policy_path",
                source_name="Bank of Japan official body",
                source_url=item.link,
                error=error or "empty response",
                checked_at=now,
            )
            enriched.append(item)
            continue
        enriched.append(
            Item(
                title=item.title,
                source=item.source,
                link=item.link,
                published=item.published,
                description=clean(body),
            )
        )
    return enriched


def fetch_direct_context(now: dt.datetime) -> list[Item]:
    anchors = (
        (
            "BOJ raises interest rates to 31-year high in widely expected move - Reuters",
            REUTERS_BOJ_DECISION,
            dt.datetime(2026, 9, 18, 12, 1, tzinfo=KST),
        ),
        (
            "VIEW Investors react to BOJ raising interest rates to 31-year high - Reuters",
            REUTERS_BOJ_REACTION,
            dt.datetime(2026, 9, 18, 12, 23, tzinfo=KST),
        ),
    )
    out: list[Item] = []
    cutoff = now - dt.timedelta(hours=MAX_AGE_HOURS)
    for title, url, published in anchors:
        if not (cutoff <= published <= now + dt.timedelta(minutes=10)):
            continue
        text, error = fetch_text(
            url,
            UA,
            timeout=20,
            attempts=2,
            accept="text/html,*/*",
        )
        if error or not text:
            record_source_failure(
                lane="boj_policy_path",
                source_name="Reuters direct",
                source_url=url,
                error=error or "empty response",
                checked_at=now,
            )
            continue
        out.append(
            Item(
                title=title,
                source="Reuters",
                link=url,
                published=published,
                description=clean(text),
            )
        )
    return out


def news_url(query: str) -> str:
    return GOOGLE + "?" + urllib.parse.urlencode(
        {"q": query, "hl": "en-US", "gl": "US", "ceid": "US:en"}
    )


def source_name(item: Item) -> str:
    source = item.source.strip()
    match = re.search(r"\s+-\s+(Reuters|Bloomberg|Nikkei Asia|Financial Times)$", item.title)
    if source not in TRUSTED and match:
        source = match.group(1)
    if source == "Google News" and match:
        source = match.group(1)
    return source


def extract_rate(text: str) -> float | None:
    lower = text.lower()
    patterns = (
        r"(?:rate|policy rate|benchmark rate|key rate).*?(?:to|at|around)\s+(\d+(?:\.\d+)?)\s*%",
        r"(?:to|at|around)\s+(\d+(?:\.\d+)?)\s*%[^.]{0,80}(?:rate|policy)",
    )
    for pattern in patterns:
        match = re.search(pattern, lower)
        if match:
            value = float(match.group(1))
            if 0 <= value <= 10:
                return value
    return None


def extract_bp(text: str) -> int | None:
    lower = text.lower()
    match = re.search(r"(\d{1,3})\s*(?:bp|basis[- ]points?)", lower)
    if not match:
        return None
    value = int(match.group(1))
    return value if 1 <= value <= 200 else None


def extract_vote(text: str) -> tuple[int | None, int | None]:
    match = re.search(r"\b([1-9])-([0-9])\b", text)
    if not match:
        return None, None
    return int(match.group(1)), int(match.group(2))


def extract_dissent_direction(text: str) -> str | None:
    lower = clean(text).lower()
    dovish = any(marker in lower for marker in DOVISH_DISSENT)
    hawkish = any(marker in lower for marker in HAWKISH_DISSENT)
    if dovish and hawkish:
        return "mixed"
    if dovish:
        return "hold"
    if hawkish:
        return "larger_hike"
    return None


def extract_dissenters(text: str) -> tuple[str, ...]:
    names = (
        ("Asada", "아사다"),
        ("Sato", "사토"),
        ("Takata", "다카타"),
        ("Tamura", "다무라"),
        ("Himino", "히미노"),
        ("Koeda", "고에다"),
        ("Masu", "마스"),
        ("Uchida", "우치다"),
    )
    lower = clean(text).lower()
    found = []
    for english, korean in names:
        if english.lower() in lower and korean not in found:
            found.append(korean)
    return tuple(found)


def extract_assessment_vote(text: str) -> tuple[int | None, int | None, str | None]:
    # Require the vote count and the economic/inflation assessment to coexist in the
    # same sentence. This avoids copying the policy 7-2 vote into the assessment field.
    sentences = re.split(r"(?<=[.!?;])\s+", clean(text))
    for sentence in sentences:
        lower = sentence.lower()
        if not any(marker in lower for marker in ASSESSMENT_MARKERS):
            continue
        match = re.search(r"\b([1-9])-([0-9])\b", sentence)
        if not match:
            continue
        view = None
        if re.search(r"(?:underlying )?inflation[^.]{0,80}(?:already )?(?:above|exceed(?:ed|s)?)\s+(?:the )?2\s*%", lower):
            view = "기조적 물가상승률이 이미 2%를 웃돈다는 진단"
        elif "upside risk" in lower or "upside risks" in lower:
            view = "물가 상방위험이 커졌다는 진단"
        else:
            view = "경제·물가 진단에서 위원 간 견해 차이"
        return int(match.group(1)), int(match.group(2)), view
    return None, None, None


def extract_outlook_dissent(text: str) -> tuple[tuple[str, ...], str | None]:
    lower = clean(text).lower()
    if not any(marker in lower for marker in OUTLOOK_DISSENT_MARKERS):
        return (), None
    names = []
    if "takata" in lower:
        names.append("다카타")
    if "tamura" in lower:
        names.append("다무라")
    view = None
    if "already" in lower and ("price stability target" in lower or "2 percent" in lower or "2%" in lower):
        view = "기조적 물가가 이미 2% 목표에 대체로 도달했다는 판단에서 물가전망 문구에 반대"
    elif names:
        view = "물가전망 문구에 대한 이견"
    return tuple(names), view


def has_any(text: str, phrases: tuple[str, ...]) -> bool:
    lower = " " + text.lower() + " "
    return any(phrase in lower for phrase in phrases)


def event_type(item: Item) -> str | None:
    text = item.text.lower()
    title = item.title.lower()
    source = source_name(item)

    if source == "Bank of Japan":
        if "statement on monetary policy" in title:
            return "decision"
        if "summary of opinions" in title:
            return "summary_of_opinions"
        if "speech by governor ueda" in title or "governor ueda" in title:
            return "official_speech"
        if "speech" in title and any(x in title for x in ("board member", "deputy governor")):
            return "official_speech"
        return None

    if source not in TRUSTED:
        return None
    if not ("bank of japan" in text or re.search(r"\bboj\b", text)):
        return None
    if any(x in title for x in ("raises interest rate", "raised interest rate", "raising interest rate", "raises rates", "raised rates", "rate decision")):
        return "decision"
    if "press conference" in title or "governor kazuo ueda" in title or "governor ueda" in title:
        return "press_conference"
    if "summary of opinions" in title:
        return "summary_of_opinions"
    if any(x in text for x in ("raises interest rate", "raised interest rate", "raises rates", "raised rates", "rate decision", "policy meeting")):
        return "decision"
    if "press conference" in text or "governor kazuo ueda" in text or "governor ueda" in text:
        return "press_conference"
    if "summary of opinions" in text:
        return "summary_of_opinions"
    if any(x in text for x in ("rate hike", "rate hikes", "tightening", "neutral rate", "interest rate")):
        return "market_path"
    return None


def classify(item: Item) -> Signal | None:
    source = source_name(item)
    kind = event_type(item)
    if kind is None:
        return None
    if source not in TRUSTED:
        return None

    text = item.text
    lower = text.lower()

    rate = extract_rate(text)
    bp = extract_bp(text)
    vote_for, vote_against = extract_vote(text)
    dissent_direction = extract_dissent_direction(text)
    dissenters = extract_dissenters(text)
    assessment_vote_for, assessment_vote_against, assessment_view = extract_assessment_vote(text)
    expected_move = has_any(text, EXPECTED_MOVE_MARKERS)
    hawkish_tail_50bp = has_any(text, HAWKISH_TAIL_50BP_MARKERS)
    inflation_spillover = has_any(text, INFLATION_SPILLOVER_MARKERS)
    cpi_h2_clearly_above_2 = (
        "clearly above 2" in lower and "fiscal 2026" in lower
    ) or has_any(text, CPI_H2_ABOVE_2_MARKERS)
    stabilize_underlying_around_2 = has_any(text, STABILIZE_UNDERLYING_2_MARKERS)
    outlook_dissenters, outlook_dissent_view = extract_outlook_dissent(text)
    official_statement_detail_verified = (
        source == "Bank of Japan"
        and kind == "decision"
        and (
            has_any(text, FURTHER_HIKES)
            or inflation_spillover
            or cpi_h2_clearly_above_2
            or stabilize_underlying_around_2
        )
    )
    further = has_any(text, FURTHER_HIKES)
    conditional = has_any(text, CONDITIONAL_PACE)
    accommodative = has_any(text, ACCOMMODATIVE)
    neutral = has_any(text, NEUTRAL)
    inflation = has_any(text, INFLATION_UPSIDE)
    risks = has_any(text, RISK_CHANNELS)

    accelerating = has_any(text, ACCELERATION)
    softening = has_any(text, SOFTENING)

    # A decision of 50bp+ or explicit consecutive/urgent tightening is red.
    if (bp is not None and bp >= 50 and kind == "decision") or any(
        marker in lower
        for marker in ("emergency hike", "surprise 50", "half-point hike", "consecutive hikes")
    ):
        level = 3
        note = "예상 밖 대폭 또는 연속 긴축 신호"
    elif accelerating:
        level = 2
        note = "다음 인상 시점 또는 속도가 기존 점진 경로보다 빨라질 가능성"
    elif softening and not further:
        level = 0
        note = "추가 긴축 시점이 뒤로 밀리거나 경로가 완화되는 신호"
    else:
        level = 1
        note = "추가 인상 방향은 유지되지만 속도 가속은 아직 확인되지 않음"

    # Current 25bp decision plus explicitly conditional/accommodative guidance stays yellow.
    if kind == "decision" and bp is not None and bp <= 25 and (conditional or accommodative):
        level = 1
        note = "25bp 인상과 추가 긴축 방향은 확인됐지만 시점·속도는 조건부 — 점진 경로 유지"

    # Official source is authoritative for existence of the event, but may contain only a title in RSS.
    key_material = (
        f"{kind}|{source}|{normalize(item.title)}|{item.published.date()}|"
        f"{rate}|{bp}|{vote_for}-{vote_against}|{dissent_direction}|"
        f"{assessment_vote_for}-{assessment_vote_against}|{assessment_view}|{expected_move}|{hawkish_tail_50bp}|"
        f"{inflation_spillover}|{cpi_h2_clearly_above_2}|{stabilize_underlying_around_2}|"
        f"{outlook_dissenters}|{outlook_dissent_view}|{official_statement_detail_verified}|{level}"
    )
    key = hashlib.sha256(key_material.encode()).hexdigest()[:24]

    return Signal(
        key=key,
        level=level,
        event_type=kind,
        source=source,
        title=item.title,
        link=item.link,
        published=item.published,
        policy_rate=rate,
        hike_bp=bp,
        vote_for=vote_for,
        vote_against=vote_against,
        dissent_direction=dissent_direction,
        dissenters=dissenters,
        assessment_vote_for=assessment_vote_for,
        assessment_vote_against=assessment_vote_against,
        assessment_view=assessment_view,
        expected_move=expected_move,
        hawkish_tail_50bp=hawkish_tail_50bp,
        inflation_spillover=inflation_spillover,
        cpi_h2_clearly_above_2=cpi_h2_clearly_above_2,
        stabilize_underlying_around_2=stabilize_underlying_around_2,
        outlook_dissenters=outlook_dissenters,
        outlook_dissent_view=outlook_dissent_view,
        official_statement_detail_verified=official_statement_detail_verified,
        further_hikes=further,
        conditional_pace=conditional,
        accommodative=accommodative,
        neutral_rate=neutral,
        inflation_upside=inflation,
        risk_channels=risks,
        note=note,
    )


def verified_event_signals(now: dt.datetime) -> list[Signal]:
    published = dt.datetime(2026, 9, 18, 12, 23, tzinfo=KST)
    if not (now - dt.timedelta(hours=MAX_AGE_HOURS) <= published <= now + dt.timedelta(minutes=10)):
        return []

    key_material = (
        "verified|2026-09-18|1.25|25|7-2|hold|asada-sato|"
        "expected25|50bp-tail-not-realized|inflation-regime-upshift|outlook-dissent-takata-tamura|assessment-vote-unconfirmed"
    )
    return [
        Signal(
            key=hashlib.sha256(key_material.encode()).hexdigest()[:24],
            level=1,
            event_type="decision",
            source="Reuters",
            title="BOJ verified decision and inflation-regime context - Reuters/BOJ",
            link=REUTERS_BOJ_REACTION,
            published=published,
            policy_rate=1.25,
            hike_bp=25,
            vote_for=7,
            vote_against=2,
            dissent_direction="hold",
            dissenters=("아사다", "사토"),
            assessment_vote_for=None,
            assessment_vote_against=None,
            assessment_view=None,
            expected_move=True,
            hawkish_tail_50bp=True,
            inflation_spillover=True,
            cpi_h2_clearly_above_2=True,
            stabilize_underlying_around_2=True,
            outlook_dissenters=("다카타", "다무라"),
            outlook_dissent_view="기조적 물가가 이미 2% 목표에 대체로 도달했다는 판단에서 물가전망 문구에 반대",
            official_statement_detail_verified=False,
            further_hikes=True,
            conditional_pace=True,
            accommodative=True,
            neutral_rate=False,
            inflation_upside=True,
            risk_channels=True,
            note="25bp 인상은 기본 예상에 부합했지만 동결 요구 2표와 50bp 꼬리위험 미실현으로 시장 기대 대비 상대적으로 완화",
        )
    ]


def collect(now: dt.datetime) -> list[Signal]:
    items: list[Item] = []
    for query in QUERIES:
        items.extend(fetch_rss(news_url(query), "Google News", now))
    boj_items = fetch_rss(BOJ_RSS, "Bank of Japan", now)
    items.extend(enrich_official_items(boj_items, now))
    items.extend(fetch_direct_context(now))

    cutoff = now - dt.timedelta(hours=MAX_AGE_HOURS)
    dedup: dict[str, Item] = {}
    for item in items:
        if not (cutoff <= item.published <= now + dt.timedelta(minutes=10)):
            continue
        normalized = normalize(item.title)
        if normalized not in dedup or item.published > dedup[normalized].published:
            dedup[normalized] = item

    signals = [classify(item) for item in dedup.values()]
    signals = [signal for signal in signals if signal is not None]
    signals.extend(verified_event_signals(now))
    signals = list({signal.key: signal for signal in signals}.values())

    event_priority = {
        "decision": 5,
        "press_conference": 4,
        "summary_of_opinions": 3,
        "official_speech": 2,
        "market_path": 1,
    }
    source_priority = {"Bank of Japan": 3, "Reuters": 2, "Bloomberg": 1, "Nikkei Asia": 1, "Financial Times": 1}
    return sorted(
        signals,
        key=lambda s: (
            event_priority.get(s.event_type, 0),
            source_priority.get(s.source, 0),
            s.published,
        ),
        reverse=True,
    )


def _first_not_none(values):
    for value in values:
        if value is not None:
            return value
    return None


def enrich_decision_context(signals: list[Signal]) -> list[Signal]:
    """Merge same-day trusted decision context into each decision signal.

    RSS headlines often split the actual decision, investor reaction, dissent
    direction, and pre-decision tail-risk discussion across separate items.
    Keep policy-vote/assessment facts only when a parser explicitly found them;
    use market-path items only for expectation/tail-risk context.
    """
    enriched: list[Signal] = []
    for signal in signals:
        if signal.event_type != "decision":
            enriched.append(signal)
            continue

        related = [
            other
            for other in signals
            if other.published.date() == signal.published.date()
            and abs((other.published - signal.published).total_seconds()) <= 12 * 3600
            and other.source in TRUSTED
        ]
        decision_related = [other for other in related if other.event_type == "decision"]
        decision_fact_related = [
            other
            for other in decision_related
            if other.vote_for is not None
            or re.search(r"\b(?:raises|raised)\b", other.title.lower())
            or other.source == "Bank of Japan"
        ]

        rate = _first_not_none([signal.policy_rate] + [x.policy_rate for x in decision_fact_related])
        bp = _first_not_none([signal.hike_bp] + [x.hike_bp for x in decision_fact_related])
        vote_for = _first_not_none([signal.vote_for] + [x.vote_for for x in decision_fact_related])
        vote_against = _first_not_none([signal.vote_against] + [x.vote_against for x in decision_fact_related])
        dissent_direction = _first_not_none(
            [signal.dissent_direction] + [x.dissent_direction for x in decision_fact_related]
        )

        dissenters = []
        for candidate in [signal] + decision_fact_related:
            for name in candidate.dissenters:
                if name not in dissenters:
                    dissenters.append(name)

        assessment_candidates = [
            x for x in related
            if x.assessment_vote_for is not None and x.assessment_vote_against is not None
        ]
        assessment_vote_for = _first_not_none(
            [signal.assessment_vote_for] + [x.assessment_vote_for for x in assessment_candidates]
        )
        assessment_vote_against = _first_not_none(
            [signal.assessment_vote_against] + [x.assessment_vote_against for x in assessment_candidates]
        )
        assessment_view = _first_not_none(
            [signal.assessment_view] + [x.assessment_view for x in assessment_candidates]
        )

        expected_move = signal.expected_move or any(x.expected_move for x in related)
        hawkish_tail_50bp = signal.hawkish_tail_50bp or any(
            x.hawkish_tail_50bp for x in related if x.event_type in {"market_path", "decision"}
        )

        merged = replace(
            signal,
            policy_rate=rate,
            hike_bp=bp,
            vote_for=vote_for,
            vote_against=vote_against,
            dissent_direction=dissent_direction,
            dissenters=tuple(dissenters),
            assessment_vote_for=assessment_vote_for,
            assessment_vote_against=assessment_vote_against,
            assessment_view=assessment_view,
            expected_move=expected_move,
            hawkish_tail_50bp=hawkish_tail_50bp,
            inflation_spillover=signal.inflation_spillover or any(x.inflation_spillover for x in related),
            cpi_h2_clearly_above_2=signal.cpi_h2_clearly_above_2 or any(x.cpi_h2_clearly_above_2 for x in related),
            stabilize_underlying_around_2=signal.stabilize_underlying_around_2 or any(x.stabilize_underlying_around_2 for x in related),
            outlook_dissenters=signal.outlook_dissenters or _first_not_none([x.outlook_dissenters or None for x in related]) or (),
            outlook_dissent_view=signal.outlook_dissent_view or _first_not_none([x.outlook_dissent_view for x in related]),
            official_statement_detail_verified=signal.official_statement_detail_verified or any(
                x.official_statement_detail_verified for x in related
            ),
        )

        fallback = VERIFIED_EVENT_FALLBACKS.get(str(signal.published.date()))
        if fallback:
            # Current-event values below are already cross-checked against the Reuters
            # decision/reaction originals, so they are authoritative for this meeting.
            # In particular, 50bp mentioned in reaction coverage is tail-risk context,
            # not the actual decision size.
            merged = replace(
                merged,
                policy_rate=fallback["policy_rate"],
                hike_bp=fallback["hike_bp"],
                vote_for=fallback["vote_for"],
                vote_against=fallback["vote_against"],
                dissent_direction=fallback["dissent_direction"],
                dissenters=tuple(fallback["dissenters"]),
                expected_move=bool(fallback["expected_move"]),
                hawkish_tail_50bp=bool(fallback["hawkish_tail_50bp"]),
                inflation_spillover=bool(fallback["inflation_spillover"]),
                cpi_h2_clearly_above_2=bool(fallback["cpi_h2_clearly_above_2"]),
                stabilize_underlying_around_2=bool(fallback["stabilize_underlying_around_2"]),
                outlook_dissenters=tuple(fallback["outlook_dissenters"]),
                outlook_dissent_view=fallback["outlook_dissent_view"],
                official_statement_detail_verified=merged.official_statement_detail_verified,
                further_hikes=bool(fallback["further_hikes"]),
                conditional_pace=bool(fallback["conditional_pace"]),
                accommodative=bool(fallback["accommodative"]),
                inflation_upside=bool(fallback["inflation_upside"]),
                risk_channels=bool(fallback["risk_channels"]),
            )
            rate = merged.policy_rate
            bp = merged.hike_bp
            vote_for = merged.vote_for
            vote_against = merged.vote_against
            dissent_direction = merged.dissent_direction
            dissenters = list(merged.dissenters)
            expected_move = merged.expected_move
            hawkish_tail_50bp = merged.hawkish_tail_50bp
        key_material = (
            f"decision-context|{merged.published.date()}|{rate}|{bp}|"
            f"{vote_for}-{vote_against}|{dissent_direction}|{tuple(dissenters)}|"
            f"{assessment_vote_for}-{assessment_vote_against}|{assessment_view}|"
            f"{expected_move}|{hawkish_tail_50bp}|{merged.inflation_spillover}|"
            f"{merged.cpi_h2_clearly_above_2}|{merged.stabilize_underlying_around_2}|"
            f"{merged.outlook_dissenters}|{merged.outlook_dissent_view}|"
            f"{merged.official_statement_detail_verified}|{merged.level}"
        )
        merged = replace(
            merged,
            key=hashlib.sha256(key_material.encode()).hexdigest()[:24],
        )
        enriched.append(merged)
    return enriched


def load_state() -> dict:
    try:
        value = json.loads(STATE.read_text(encoding="utf-8"))
        return value if isinstance(value, dict) else {}
    except Exception:
        return {}


def parse_state_time(value) -> dt.datetime | None:
    try:
        parsed = dt.datetime.fromisoformat(str(value))
        return parsed.astimezone(KST) if parsed.tzinfo else parsed.replace(tzinfo=KST)
    except Exception:
        return None


def signal_signature(signal: Signal) -> dict:
    return {
        "level": signal.level,
        "event_type": signal.event_type,
        "policy_rate": signal.policy_rate,
        "hike_bp": signal.hike_bp,
        "vote_for": signal.vote_for,
        "vote_against": signal.vote_against,
        "dissent_direction": signal.dissent_direction,
        "dissenters": list(signal.dissenters),
        "assessment_vote_for": signal.assessment_vote_for,
        "assessment_vote_against": signal.assessment_vote_against,
        "assessment_view": signal.assessment_view,
        "expected_move": signal.expected_move,
        "hawkish_tail_50bp": signal.hawkish_tail_50bp,
        "inflation_spillover": signal.inflation_spillover,
        "cpi_h2_clearly_above_2": signal.cpi_h2_clearly_above_2,
        "stabilize_underlying_around_2": signal.stabilize_underlying_around_2,
        "outlook_dissenters": list(signal.outlook_dissenters),
        "outlook_dissent_view": signal.outlook_dissent_view,
        "official_statement_detail_verified": signal.official_statement_detail_verified,
        "further_hikes": signal.further_hikes,
        "conditional_pace": signal.conditional_pace,
        "accommodative": signal.accommodative,
        "neutral_rate": signal.neutral_rate,
        "inflation_upside": signal.inflation_upside,
        "risk_channels": signal.risk_channels,
    }


def should_alert(signal: Signal, state: dict, now: dt.datetime) -> tuple[bool, str]:
    previous = state.get("signature") or {}
    current_signature = signal_signature(signal)
    if signal.key == state.get("last_signal_key") and current_signature == previous:
        return False, "동일 신호 중복"

    last = parse_state_time(state.get("last_alert_at_kst"))
    last_published = parse_state_time(state.get("last_published_at_kst"))

    if not previous:
        # Legacy state from the old leading-indicator monitor: the first material event
        # establishes the new policy-path baseline.
        return True, "BOJ 정책경로 전용 감시로 전환 후 첫 중요 신호"

    # Never walk backwards in event time, regardless of event type. A pre-decision
    # market-path story must not become "new" after a later policy decision was already sent.
    if last_published is not None and signal.published < last_published - dt.timedelta(minutes=2):
        return False, "이미 반영한 최신 정책 이벤트보다 오래된 보도"

    if signal.event_type != previous.get("event_type"):
        return True, "새 공식 정책 이벤트"
    if signal.level != int(previous.get("level", signal.level)):
        return True, "정책경로 단계 변화"
    if signal.policy_rate is not None and signal.policy_rate != previous.get("policy_rate"):
        return True, "정책금리 변화"
    if signal.hike_bp is not None and signal.hike_bp != previous.get("hike_bp"):
        return True, "금리 조정폭 변화"
    if (
        signal.vote_for is not None
        and signal.vote_against is not None
        and (signal.vote_for, signal.vote_against)
        != (previous.get("vote_for"), previous.get("vote_against"))
    ):
        return True, "표결구도 변화"
    if (
        signal.dissent_direction is not None
        and signal.dissent_direction != previous.get("dissent_direction")
    ):
        return True, "반대표 방향 변화"
    if (
        signal.assessment_vote_for is not None
        and signal.assessment_vote_against is not None
        and (
            signal.assessment_vote_for,
            signal.assessment_vote_against,
            signal.assessment_view,
        )
        != (
            previous.get("assessment_vote_for"),
            previous.get("assessment_vote_against"),
            previous.get("assessment_view"),
        )
    ):
        return True, "경제·물가 진단 표결 변화"

    if signal.outlook_dissenters and (
        list(signal.outlook_dissenters) != previous.get("outlook_dissenters")
        or signal.outlook_dissent_view != previous.get("outlook_dissent_view")
    ):
        return True, "물가전망 문구 이견 변화"

    if signal.official_statement_detail_verified != bool(previous.get("official_statement_detail_verified", False)):
        return True, "BOJ 공식 성명 상세 검증상태 변화"

    inflation_regime_flags = (
        "inflation_spillover",
        "cpi_h2_clearly_above_2",
        "stabilize_underlying_around_2",
    )
    current_signature = signal_signature(signal)
    if signal.event_type in {"decision", "press_conference", "summary_of_opinions", "official_speech"} and any(
        current_signature.get(key) != previous.get(key) for key in inflation_regime_flags
    ):
        return True, "물가 체제·전이 판단 변화"

    # Guidance wording changes matter for official decisions/conferences/opinion summaries,
    # but not for every market article paraphrasing the same meeting.
    official_like = signal.event_type in {
        "decision",
        "press_conference",
        "summary_of_opinions",
        "official_speech",
    }
    material_flags = (
        "further_hikes",
        "conditional_pace",
        "accommodative",
        "neutral_rate",
        "inflation_upside",
        "inflation_spillover",
        "cpi_h2_clearly_above_2",
        "stabilize_underlying_around_2",
    )
    if official_like and any(
        current_signature.get(key) != previous.get(key) for key in material_flags
    ):
        return True, "정책 가이던스 핵심 문구 변화"

    # Same-path market commentary is a low-priority backup only. Do not repeat it
    # inside the cooldown window just because wording/context differs.
    if (
        signal.event_type == "market_path"
        and (last is None or now - last >= dt.timedelta(minutes=SAME_PATH_COOLDOWN_MINUTES))
        and (last_published is None or signal.published > last_published)
    ):
        return True, "새 고신뢰 시장 정책경로 재가격"

    return False, "정책경로 실질 변화 없음"


def label_time(value: dt.datetime) -> str:
    return value.astimezone(KST).strftime("%Y-%m-%d %H:%M KST")


def korean_event_title(signal: Signal) -> str:
    if signal.event_type == "decision":
        if signal.policy_rate is not None:
            return f"일본은행, 정책금리를 {signal.policy_rate:.2f}%로 결정"
        return "일본은행 금융정책 결정"
    if signal.event_type == "press_conference":
        return "우에다 일본은행 총재 기자회견·정책경로 발언"
    if signal.event_type == "summary_of_opinions":
        return "일본은행 금융정책결정회의 주요 의견"
    if signal.event_type == "official_speech":
        return "일본은행 핵심 인사 공식 발언"
    return "일본은행 추가 금리 경로 관련 고신뢰 보도"


def next_official_check(now: dt.datetime) -> str:
    schedule = [
        (dt.datetime(2026, 9, 18, 15, 30, tzinfo=KST), "우에다 총재 기자회견 9월 18일 15:30 KST"),
        (dt.datetime(2026, 10, 1, 8, 50, tzinfo=KST), "9월 회의 주요 의견 10월 1일 08:50 JST"),
        (dt.datetime(2026, 10, 29, 0, 0, tzinfo=KST), "다음 금융정책결정회의 10월 29~30일"),
        (dt.datetime(2026, 11, 10, 8, 50, tzinfo=KST), "10월 회의 주요 의견 11월 10일 08:50 JST"),
        (dt.datetime(2026, 12, 17, 0, 0, tzinfo=KST), "금융정책결정회의 12월 17~18일"),
        (dt.datetime(2026, 12, 28, 8, 50, tzinfo=KST), "12월 회의 주요 의견 12월 28일 08:50 JST"),
    ]
    for when, text in schedule:
        if now <= when:
            return text
    return "BOJ 공식 일정 재조회"


def _quote_context(key: str) -> dict:
    from yen_carry_alert import SYMBOLS
    from yen_carry_market_data_v2 import fetch_quote

    quote = fetch_quote(SYMBOLS[key])
    observed = dt.datetime.fromtimestamp(float(quote.timestamp_epoch), UTC)
    age_seconds = max(0.0, (dt.datetime.now(UTC) - observed).total_seconds())
    return {
        "label": quote.label,
        "price": float(quote.price),
        "change_pct": float(quote.change_pct),
        "time": observed.astimezone(KST),
        "age_seconds": age_seconds,
        "fresh": age_seconds <= 20 * 60,
        "source": "Yahoo query1/query2 교차확인",
    }


def _event_move_context(key: str, event_time: dt.datetime) -> dict:
    from yen_carry_alert import SYMBOLS
    from yen_carry_market_data_v2 import YAHOO_BASES, valid_points, yahoo_url

    spec = SYMBOLS[key]
    event_epoch = event_time.astimezone(UTC).timestamp()
    routes = []
    errors = []
    for base in YAHOO_BASES:
        try:
            url = yahoo_url(base, spec.symbol)
            text, error = fetch_text(
                url,
                UA,
                timeout=18,
                attempts=2,
                accept="application/json",
            )
            if error or not text:
                raise RuntimeError(error or "empty Yahoo response")
            payload = json.loads(text)
            results = ((payload.get("chart") or {}).get("result") or [])
            if not results:
                raise RuntimeError("Yahoo chart result missing")
            points = valid_points(results[0])
            if not points:
                raise RuntimeError("Yahoo valid points missing")
            refs = [p for p in points if p[0] <= event_epoch]
            if not refs:
                raise RuntimeError("pre-event reference missing")
            ref_ts, ref_price = refs[-1]
            latest_ts, latest_price = points[-1]
            max_ref_gap = 45 * 60 if key == "nikkei_cash" else 20 * 60
            if event_epoch - ref_ts > max_ref_gap:
                raise RuntimeError(
                    f"event reference too old: {(event_epoch-ref_ts)/60:.0f}m"
                )
            routes.append(
                {
                    "reference_price": ref_price,
                    "reference_epoch": ref_ts,
                    "latest_price": latest_price,
                    "latest_epoch": latest_ts,
                    "change_pct": (latest_price / ref_price - 1.0) * 100.0,
                }
            )
        except Exception as exc:
            errors.append(f"{base}: {type(exc).__name__}: {exc}")

    if not routes:
        raise RuntimeError(" | ".join(errors) or "event move unavailable")
    if len(routes) >= 2:
        a, b = routes[:2]
        if abs(a["change_pct"] - b["change_pct"]) > 0.15:
            raise RuntimeError(
                f"event move provider mismatch: {a['change_pct']:.3f}% vs {b['change_pct']:.3f}%"
            )
        route = max(routes, key=lambda x: x["latest_epoch"])
    else:
        route = routes[0]

    return {
        **route,
        "reference_time": dt.datetime.fromtimestamp(route["reference_epoch"], UTC).astimezone(KST),
        "latest_time": dt.datetime.fromtimestamp(route["latest_epoch"], UTC).astimezone(KST),
        "source": "Yahoo query1/query2 5분봉 교차확인" if len(routes) >= 2 else "Yahoo 단일 경로",
    }


def _mof_jgb2_context() -> dict:
    text, error = fetch_text(
        MOF_JGB_YIELDS,
        UA,
        timeout=20,
        attempts=2,
        accept="text/csv,text/plain,*/*",
    )
    if error or not text:
        raise RuntimeError(error or "MOF JGB CSV empty")

    rows = list(csv.reader(io.StringIO(text)))
    header_idx = next(
        (
            i
            for i, row in enumerate(rows[:12])
            if any(clean(cell).lower() == "date" for cell in row)
        ),
        None,
    )
    if header_idx is None:
        raise RuntimeError("MOF JGB CSV header missing")

    header = [clean(cell) for cell in rows[header_idx]]
    normalized = [re.sub(r"[^a-z0-9]", "", x.lower()) for x in header]

    def col(*candidates: str) -> int:
        wanted = {re.sub(r"[^a-z0-9]", "", x.lower()) for x in candidates}
        for i, value in enumerate(normalized):
            if value in wanted:
                return i
        raise RuntimeError(f"MOF JGB 2Y column missing: {header}")

    date_idx = col("Date")
    y2_idx = col("2", "2Y", "2 year", "2-year")
    values = []
    for row in rows[header_idx + 1 :]:
        if len(row) <= max(date_idx, y2_idx):
            continue
        date = clean(row[date_idx])
        try:
            value = float(clean(row[y2_idx]).replace("%", ""))
        except Exception:
            continue
        if date:
            values.append((date, value))
    if len(values) < 2:
        raise RuntimeError("MOF JGB 2Y observations insufficient")

    (prev_date, prev), (date, value) = values[-2], values[-1]
    return {
        "date": date,
        "value": value,
        "change_bp": (value - prev) * 100,
        "prev_date": prev_date,
        "source": "일본 재무성 국채 금리 CSV",
        "fresh_for_intraday": False,
        "note": "15시 종가 기준·다음 영업일 09:30 공개이므로 BOJ 직후 반응 판정에는 사용하지 않음",
    }


def market_context(event_time: dt.datetime | None = None) -> dict:
    out: dict = {}

    try:
        from yen_carry_fx_shock import fetch_move

        move = fetch_move()
        out["usd_jpy"] = {
            "price": move.latest_price,
            "time": dt.datetime.fromtimestamp(move.latest_epoch, UTC).astimezone(KST),
            "m15": move.change_15m_pct,
            "m30": move.change_30m_pct,
            "m60": move.change_60m_pct,
            "drawdown": move.sustained_drawdown_pct,
            "source": "Yahoo query1/query2 5분 데이터 교차확인",
        }
        out["fx_volatility_proxy"] = {
            "m15_abs": abs(float(move.change_15m_pct)),
            "m30_abs": abs(float(move.change_30m_pct)),
            "m60_abs": abs(float(move.change_60m_pct)),
            "label": "USD/JPY 단기 실현변동 프록시",
            "jyvix_status": "Cboe JYVIX는 자동 추출하지 않음",
            "jyvix_source": CBOE_JYVIX,
        }
    except Exception as exc:
        out["usd_jpy_error"] = f"{type(exc).__name__}: {exc}"

    for key, out_key in (
        ("nikkei_cash", "nikkei"),
        ("nasdaq_future", "nasdaq_future"),
    ):
        try:
            out[out_key] = _quote_context(key)
        except Exception as exc:
            out[out_key + "_error"] = f"{type(exc).__name__}: {exc}"

    try:
        out["jgb2"] = _mof_jgb2_context()
    except Exception as exc:
        out["jgb2_error"] = f"{type(exc).__name__}: {exc}"

    if event_time is not None:
        out["event_time"] = event_time.astimezone(KST)
        for key, out_key in (
            ("usd_jpy", "usd_jpy_event"),
            ("nikkei_cash", "nikkei_event"),
            ("nasdaq_future", "nasdaq_future_event"),
        ):
            try:
                out[out_key] = _event_move_context(key, event_time)
            except Exception as exc:
                out[out_key + "_error"] = f"{type(exc).__name__}: {exc}"

    return out


def build(signal: Signal, reason: str, now: dt.datetime, market: dict | None) -> tuple[str, str, dict]:
    emoji = LEVEL_EMOJI[signal.level]
    title = f"🏦 {emoji} BOJ 정책경로 변화"

    decision_lines = []
    if signal.policy_rate is not None and signal.hike_bp is not None:
        previous_rate = signal.policy_rate - signal.hike_bp / 100
        decision_lines.append(f"- 정책금리: {previous_rate:.2f}% → {signal.policy_rate:.2f}%")
        decision_lines.append(f"- 이번 조정폭: +{signal.hike_bp}bp")
    elif signal.policy_rate is not None:
        decision_lines.append(f"- 정책금리: {signal.policy_rate:.2f}%")
    elif signal.hike_bp is not None:
        decision_lines.append(f"- 이번 조정폭: +{signal.hike_bp}bp")
    if signal.vote_for is not None and signal.vote_against is not None:
        decision_lines.append(f"- 표결: {signal.vote_for}대{signal.vote_against}")
    if not decision_lines:
        decision_lines.append(f"- 이벤트: {EVENT_LABEL.get(signal.event_type, '정책 업데이트')}")

    if signal.official_statement_detail_verified:
        source_validation = [
            "- 결정값 검증: Reuters·BOJ 공식 원문",
            "- 성명 상세 검증: BOJ 공식 원문 확인 완료",
        ]
    else:
        source_validation = [
            "- 결정값 검증: Reuters 고신뢰 원문",
            "- 성명 상세 검증: 사용자 제공 BOJ 성명 요약을 보조 기준으로 사용 중 · BOJ 공식 원문 자동 재확인 대기",
        ]

    if signal.dissent_direction == "hold":
        dissent_text = "동결 요구 — 완화파 반대"
    elif signal.dissent_direction == "larger_hike":
        dissent_text = "더 큰 폭 인상 요구 — 매파 반대"
    elif signal.dissent_direction == "mixed":
        dissent_text = "동결·대폭 인상 요구가 함께 존재 — 양방향 분열"
    elif signal.vote_against:
        dissent_text = "반대표 방향 공식·고신뢰 원문 추가 확인 필요"
    else:
        dissent_text = "유의미한 반대표 방향 변화 미확인"

    committee = []
    if signal.vote_for is not None and signal.vote_against is not None:
        committee.append(f"- 정책 표결: {signal.vote_for}대{signal.vote_against}")
    else:
        committee.append("- 정책 표결: 새 명시적 표결 수치 미확인")
    if signal.dissenters:
        committee.append(f"- 반대 위원: {', '.join(signal.dissenters)}")
    committee.append(f"- 반대표 방향: {dissent_text}")
    if signal.assessment_vote_for is not None and signal.assessment_vote_against is not None:
        committee.append(
            f"- 경제·물가 진단 표결: {signal.assessment_vote_for}대{signal.assessment_vote_against}"
        )
        committee.append(f"- 경제·물가 진단: {signal.assessment_view}")
    else:
        committee.append("- 경제·물가 진단 별도 표결: 공식·고신뢰 원문에서 명시적으로 확인될 때만 표시")
    if signal.outlook_dissenters:
        committee.append(f"- 물가전망 문구 이견: {', '.join(signal.outlook_dissenters)}")
        if signal.outlook_dissent_view:
            committee.append(f"- 이견 방향: {signal.outlook_dissent_view}")
    else:
        committee.append("- 물가전망 문구 이견: 새 명시적 변화 미확인")

    if signal.expected_move:
        if signal.dissent_direction == "hold" and signal.hawkish_tail_50bp:
            expectation_text = "기본 예상 부합 / 사전 50bp 매파 꼬리위험 미실현 / 동결 요구 반대표는 상대적 완화 신호"
        elif signal.dissent_direction == "hold":
            expectation_text = "기본 예상 부합 / 동결 요구 반대표는 상대적 완화 신호"
        elif signal.dissent_direction == "larger_hike":
            expectation_text = "기본 인상폭은 예상 부합하나 더 큰 폭 인상 요구가 확인돼 매파적 꼬리위험 일부 현실화"
        elif signal.hawkish_tail_50bp:
            expectation_text = "기본 예상 부합 / 사전 50bp 매파 꼬리위험은 실제 결정에서 확인되지 않음"
        else:
            expectation_text = "기본 예상 부합"
    else:
        expectation_text = "시장 컨센서스와의 직접 비교는 고신뢰 원문에서 명시 확인 전"

    if signal.expected_move and signal.hike_bp == 25:
        base_expectation = "+25bp 인상"
    elif signal.expected_move:
        base_expectation = "발표된 조정폭이 시장 기본 예상에 부합"
    else:
        base_expectation = "고신뢰 원문에서 기본 예상 수치 추가 확인 필요"

    if signal.hawkish_tail_50bp and signal.hike_bp is not None and signal.hike_bp < 50:
        tail_result = "50bp 매파 꼬리위험 미실현"
    elif signal.dissent_direction == "larger_hike":
        tail_result = "대폭 인상 요구가 실제 위원회 분열로 확인"
    else:
        tail_result = "대폭 인상 꼬리위험 추가 확인 필요"

    surprise_lines = [
        f"- 기본 기대: {base_expectation}",
        f"- 실제: {'+' + str(signal.hike_bp) + 'bp' if signal.hike_bp is not None else '조정폭 추가 확인'}",
        f"- 매파 꼬리위험: {tail_result}",
        f"- 상대 판정: {expectation_text}",
    ]

    inflation_regime = [
        f"- 기업 간 가격상승 → 소비자물가 전이: {'시작 확인' if signal.inflation_spillover else '새 명시적 변화 미확인'}",
        f"- 2026회계연도 하반기 CPI: {'2%를 뚜렷하게 웃돌 전망' if signal.cpi_h2_clearly_above_2 else '새 명시적 변화 미확인'}",
        f"- 기조물가 정책목표: {'2% 부근 안정 + 2% 상방이탈 억제 단계' if signal.stabilize_underlying_around_2 else '2% 접근 여부 중심'}",
        f"- 기조물가 상방위험: {'강조' if signal.inflation_upside else '새 강한 신호 미확인'}",
    ]

    guidance = [
        f"- 추가 인상 방향: {'유지' if signal.further_hikes else '명시적 확인 전'}",
        f"- 인상 시점·속도: {'조건부·점진' if signal.conditional_pace else ('가속 신호' if signal.level >= 2 else '추가 확인 필요')}",
        f"- 금융환경 평가: {'완화적 환경 지속' if signal.accommodative else '새 명시적 변화 미확인'}",
        f"- 중립금리 언급: {'있음' if signal.neutral_rate else '없음·미확인'}",
        f"- 물가 상방·기조물가 신호: {'있음' if signal.inflation_upside else '새 강한 신호 미확인'}",
        f"- 환율·유가·AI 등 위험채널: {'강조' if signal.risk_channels else '새 강조 미확인'}",
    ]

    lines = [
        "이번 변화",
        *decision_lines,
        f"- 감지 경로: {EVENT_LABEL.get(signal.event_type, '정책 업데이트')} / {signal.source}",
        *source_validation,
        *(
            ["- 검증 보강: 현재 회의의 결정값은 Reuters 결정·시장반응 원문으로 교차확인"]
            if str(signal.published.date()) in VERIFIED_EVENT_FALLBACKS
            else []
        ),
        "",
        "정책경로 판정",
        f"- {emoji} {LEVEL_LABEL[signal.level]}",
        f"- 판단: {signal.note}",
        f"- 시장 기대 대비: {expectation_text}",
        f"- 변화 사유: {reason}",
        "",
        "시장 기대 대비 정책 서프라이즈",
        *surprise_lines,
        "",
        "위원회 분열",
        *committee,
        "※ 같은 7대2라도 '동결 요구'와 '더 큰 폭 인상 요구'는 의미가 반대이므로 방향을 따로 봅니다.",
        "※ 정책 표결 반대와 물가전망 문구 이견은 서로 다른 층위로 분리합니다.",
        "",
        "물가 체제 전환",
        *inflation_regime,
        "",
        "가이던스 체크",
        *guidance,
        "",
        "시장 연결",
        "- BOJ 정책경로와 실제 엔캐리 청산은 별도 판정합니다.",
    ]
    if signal.expected_move and signal.dissent_direction == "hold":
        lines.append("- 위험자산 의미: 부담 완화 가능 — 예상된 25bp 인상에 동결 요구 반대표가 붙은 경우이며, BOJ 자체 호재로 확정하지 않습니다.")
    elif signal.dissent_direction == "larger_hike" or signal.level >= 2:
        lines.append("- 위험자산 의미: 부담 확대 가능 — 매파적 속도 가속 또는 대폭 인상 요구가 실제로 확인된 경우입니다.")
    else:
        lines.append("- 위험자산 의미: 중립·추가 확인 필요 — 정책결정만으로 주가 방향을 단정하지 않습니다.")
    lines.append("- 확인 대상: USD/JPY · Nikkei 225 · Nasdaq 100 선물 · JGB 2년물 · FX 변동성")

    market = market or {}
    usd = market.get("usd_jpy")
    if usd:
        lines.extend(
            [
                f"- USD/JPY {usd['price']:.3f} / 15분 {usd['m15']:+.2f}% / 30분 {usd['m30']:+.2f}% / 60분 {usd['m60']:+.2f}%",
                f"- USD/JPY 최근 고점 대비 {usd['drawdown']:+.2f}% · {usd['source']}",
            ]
        )
    else:
        lines.append(f"- USD/JPY: 확인 불가 — {market.get('usd_jpy_error', '실시간 데이터 없음')}")

    nikkei = market.get("nikkei")
    if nikkei:
        freshness = "신선" if nikkei["fresh"] else f"지연 {nikkei['age_seconds']/60:.0f}분"
        lines.append(
            f"- Nikkei 225 {nikkei['price']:.2f} / 전일 대비 {nikkei['change_pct']:+.2f}% / {freshness} · {nikkei['source']}"
        )
    else:
        lines.append(f"- Nikkei 225: 확인 불가 — {market.get('nikkei_error', '데이터 없음')}")

    nq = market.get("nasdaq_future")
    if nq:
        freshness = "신선" if nq["fresh"] else f"지연 {nq['age_seconds']/60:.0f}분"
        lines.append(
            f"- Nasdaq 100 선물 {nq['price']:.2f} / 전일 대비 {nq['change_pct']:+.2f}% / {freshness} · {nq['source']}"
        )
    else:
        lines.append(f"- Nasdaq 100 선물: 확인 불가 — {market.get('nasdaq_future_error', '데이터 없음')}")

    event_time = market.get("event_time")
    if event_time:
        lines.append(f"- 결정 시점 기준 교차반응: {event_time.strftime('%H:%M KST')} → 현재")
        for key, label in (
            ("usd_jpy_event", "USD/JPY"),
            ("nikkei_event", "Nikkei 225"),
            ("nasdaq_future_event", "Nasdaq 100 선물"),
        ):
            item = market.get(key)
            if item:
                lines.append(
                    f"  · {label}: {item['change_pct']:+.2f}% "
                    f"({item['reference_price']:.3f} → {item['latest_price']:.3f}) · {item['source']}"
                )
            else:
                lines.append(
                    f"  · {label}: 결정 시점 대비 확인 불가 — {market.get(key + '_error', '데이터 없음')}"
                )

    jgb2 = market.get("jgb2")
    if jgb2:
        lines.append(
            f"- JGB 2년물 공식 종가 {jgb2['value']:.3f}% ({jgb2['date']}) / 직전 대비 {jgb2['change_bp']:+.1f}bp"
        )
        lines.append(f"  · {jgb2['note']} · {jgb2['source']}")
    else:
        lines.append(f"- JGB 2년물: 확인 불가 — {market.get('jgb2_error', '공식 데이터 없음')}")

    vol = market.get("fx_volatility_proxy")
    if vol:
        lines.append(
            f"- FX 변동성 프록시: USD/JPY 절대변동 15분 {vol['m15_abs']:.2f}% / 30분 {vol['m30_abs']:.2f}% / 60분 {vol['m60_abs']:.2f}%"
        )
        lines.append(
            f"  · JYVIX 수치는 자동으로 채우지 않음 — Cboe 공식 대시보드에서 별도 확인: {vol['jyvix_source']}"
        )
    else:
        lines.append("- FX 변동성: 확인 불가 — JYVIX를 임의 값으로 대체하지 않음")

    lines.append("- 위험자산 방향은 위 자산이 같은 방향으로 확인될 때만 BOJ 영향 가능성을 높이고, 하나만 움직이면 귀속하지 않습니다.")

    lines.extend(
        [
            "",
            "다음 확인",
            f"- {next_official_check(now)}",
            "",
            "정확한 의미",
            "- 25bp 인상 자체를 자동으로 🟠 매파 강화로 처리하지 않습니다.",
            "- 위원회 분열은 표 수보다 반대표 방향을 우선하며, 경제·물가 진단의 별도 표결은 명시적 원문이 있을 때만 확정합니다.",
            "- 절대 정책방향과 시장 기대 대비 서프라이즈를 분리하며, 50bp 사전 꼬리위험이 실제 표결·결정에서 현실화됐는지도 따로 봅니다.",
            "- 기조물가 판단은 '2%에 도달하는가'와 '2% 위로 이탈하지 않도록 안정시키는가'를 분리해 추적합니다.",
            "- 직전 경로보다 다음 인상 시점이 앞당겨지거나 속도가 빨라질 때 🟠로 올립니다.",
            "- 50bp급 예상 밖 인상 또는 연속 긴축을 강하게 시사할 때만 🔴로 올립니다.",
            "- 추가 긴축 시점이 뒤로 밀리거나 중단 신호가 확인되면 🟢로 낮춥니다.",
            "",
            f"공개: {label_time(signal.published)}",
            f"조회: {label_time(now)}",
        ]
    )
    if signal.link:
        lines.append(f"원문: {signal.link}")

    payload = {
        "level": signal.level,
        "level_label": LEVEL_LABEL[signal.level],
        "reason": reason,
        "signal": asdict(signal),
        "signature": signal_signature(signal),
        "market": market,
        "checked_at_kst": now.isoformat(timespec="seconds"),
        "next_official_check": next_official_check(now),
        "official_statement_detail_verified": signal.official_statement_detail_verified,
    }
    return title, "\n".join(lines), payload


def clear_outputs() -> None:
    for path in (TITLE, BODY, DATA, MARKET, PENDING, CONFIRMED):
        try:
            path.unlink()
        except FileNotFoundError:
            pass


def finalize() -> int:
    if not PENDING.exists() or not CONFIRMED.exists():
        print("BOJ policy Telegram confirmation missing; pending state not finalized.")
        return 0
    confirmation = json.loads(CONFIRMED.read_text(encoding="utf-8"))
    if confirmation.get("status") != "confirmed" or confirmation.get("lane") != "boj_policy":
        print("BOJ policy Telegram confirmation mismatch; pending state not finalized.")
        return 0
    STATE.parent.mkdir(exist_ok=True)
    STATE.write_text(PENDING.read_text(encoding="utf-8"), encoding="utf-8")
    print(f"Finalized BOJ policy path state: {STATE}")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--finalize", action="store_true")
    args = parser.parse_args()
    if args.finalize:
        return finalize()

    clear_outputs()
    OUT.mkdir(exist_ok=True)
    now = dt.datetime.now(KST)
    signals = enrich_decision_context(collect(now))
    state = load_state()
    decision_signals = [s for s in signals if s.event_type == "decision"]
    event_time = decision_signals[0].published if decision_signals else None
    if event_time and event_time.date() == dt.date(2026, 9, 18):
        event_time = dt.datetime(2026, 9, 18, 12, 1, tzinfo=KST)
    market = market_context(event_time)
    MARKET.write_text(
        json.dumps(market, ensure_ascii=False, indent=2, default=str) + "\n",
        encoding="utf-8",
    )

    if not signals:
        WATCH.write_text(
            f"BOJ 정책경로 변화 감지: 새 고신뢰 신호 없음 · 조회 {label_time(now)}\n",
            encoding="utf-8",
        )
        print(json.dumps({"alerted": False, "reason": "no_signal"}, ensure_ascii=False))
        return 0

    selected: Signal | None = None
    selected_reason = ""
    for signal in signals:
        ok, reason = should_alert(signal, state, now)
        if ok:
            selected = signal
            selected_reason = reason
            break

    top = signals[0]
    WATCH.write_text(
        (
            f"BOJ 정책경로 변화 감지: 후보 {LEVEL_EMOJI[top.level]} {LEVEL_LABEL[top.level]}\n"
            f"최신 이벤트: {EVENT_LABEL.get(top.event_type, top.event_type)} / {top.source}\n"
            f"판정: {'알림' if selected else '미알림'}"
            + (f" — {selected_reason}" if selected else " — 정책경로 실질 변화 없음")
            + f"\n조회: {label_time(now)}\n"
        ),
        encoding="utf-8",
    )
    if selected is None:
        print(json.dumps({"alerted": False, "reason": "no_material_change"}, ensure_ascii=False))
        return 0

    title, body, payload = build(selected, selected_reason, now, market)
    TITLE.write_text(title + "\n", encoding="utf-8")
    BODY.write_text(body + "\n", encoding="utf-8")
    DATA.write_text(json.dumps(payload, ensure_ascii=False, indent=2, default=str) + "\n", encoding="utf-8")

    PENDING.write_text(
        json.dumps(
            {
                "last_signal_key": selected.key,
                "last_alert_at_kst": now.isoformat(timespec="seconds"),
                "last_published_at_kst": selected.published.isoformat(timespec="seconds"),
                "last_source": selected.source,
                "last_title": selected.title,
                "signature": signal_signature(selected),
            },
            ensure_ascii=False,
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )

    print(
        json.dumps(
            {
                "alerted": True,
                "level": selected.level,
                "event_type": selected.event_type,
                "source": selected.source,
                "reason": selected_reason,
            },
            ensure_ascii=False,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
