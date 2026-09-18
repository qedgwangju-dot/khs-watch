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
import datetime as dt
import hashlib
import html
import json
import pathlib
import re
import urllib.parse
import xml.etree.ElementTree as ET
from dataclasses import asdict, dataclass
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
PENDING = OUT / "boj_policy_lead_pending_state.json"
CONFIRMED = OUT / "boj_policy_lead_telegram_confirmed.json"

UA = "Mozilla/5.0 khs-boj-policy-path/2.0"
GOOGLE = "https://news.google.com/rss/search"
BOJ_RSS = "https://www.boj.or.jp/en/rss/whatsnew.xml"
TRUSTED = {"Reuters", "Bloomberg", "Nikkei Asia", "Financial Times", "Bank of Japan"}
MAX_AGE_HOURS = 72
SAME_PATH_COOLDOWN_MINUTES = 240

QUERIES = (
    '"Bank of Japan" Reuters 1.25 rate decision when:2d',
    'BOJ Ueda press conference rate path Reuters when:2d',
    '"Bank of Japan" additional rate hikes Reuters when:2d',
    '"Bank of Japan" neutral rate Ueda Reuters when:3d',
    '"Summary of Opinions" BOJ Reuters when:7d',
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
    if "press conference" in text or "governor kazuo ueda" in text or "governor ueda" in text:
        return "press_conference"
    if "summary of opinions" in text:
        return "summary_of_opinions"
    if any(x in text for x in ("raises interest rate", "raised interest rate", "raises rates", "raised rates", "rate decision", "policy meeting")):
        return "decision"
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
        f"{rate}|{bp}|{vote_for}-{vote_against}|{level}"
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
        further_hikes=further,
        conditional_pace=conditional,
        accommodative=accommodative,
        neutral_rate=neutral,
        inflation_upside=inflation,
        risk_channels=risks,
        note=note,
    )


def collect(now: dt.datetime) -> list[Signal]:
    items: list[Item] = []
    for query in QUERIES:
        items.extend(fetch_rss(news_url(query), "Google News", now))
    items.extend(fetch_rss(BOJ_RSS, "Bank of Japan", now))

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
        "further_hikes": signal.further_hikes,
        "conditional_pace": signal.conditional_pace,
        "accommodative": signal.accommodative,
        "neutral_rate": signal.neutral_rate,
        "inflation_upside": signal.inflation_upside,
        "risk_channels": signal.risk_channels,
    }


def should_alert(signal: Signal, state: dict, now: dt.datetime) -> tuple[bool, str]:
    if signal.key == state.get("last_signal_key"):
        return False, "동일 신호 중복"

    previous = state.get("signature") or {}
    last = parse_state_time(state.get("last_alert_at_kst"))

    if not previous:
        # Legacy state from the old leading-indicator monitor: official decision/conference
        # is a new regime and should alert once.
        return True, "BOJ 정책경로 전용 감시로 전환 후 첫 중요 신호"

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

    material_flags = (
        "further_hikes",
        "conditional_pace",
        "accommodative",
        "neutral_rate",
        "inflation_upside",
        "risk_channels",
    )
    current_signature = signal_signature(signal)
    if any(current_signature.get(key) != previous.get(key) for key in material_flags):
        return True, "정책 가이던스 핵심 문구 변화"

    if last is None or now - last >= dt.timedelta(minutes=SAME_PATH_COOLDOWN_MINUTES):
        if signal.event_type in {"decision", "press_conference", "summary_of_opinions", "official_speech"}:
            return True, "새 BOJ 공식·준공식 정책 업데이트"
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
        (dt.datetime(2026, 9, 24, 8, 50, tzinfo=KST), "9월 회의 기자회견 기록 공개 9월 24일"),
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


def fx_context() -> dict | None:
    try:
        from yen_carry_fx_shock import fetch_move

        move = fetch_move()
        return {
            "price": move.latest_price,
            "time": dt.datetime.fromtimestamp(move.latest_epoch, UTC).astimezone(KST),
            "m15": move.change_15m_pct,
            "m30": move.change_30m_pct,
            "drawdown": move.sustained_drawdown_pct,
        }
    except Exception:
        return None


def build(signal: Signal, reason: str, now: dt.datetime, fx: dict | None) -> tuple[str, str, dict]:
    emoji = LEVEL_EMOJI[signal.level]
    title = f"🏦 {emoji} BOJ 정책경로 변화"

    decision_lines = []
    if signal.policy_rate is not None:
        decision_lines.append(f"- 정책금리: {signal.policy_rate:.2f}%")
    if signal.hike_bp is not None:
        decision_lines.append(f"- 이번 조정폭: +{signal.hike_bp}bp")
    if signal.vote_for is not None and signal.vote_against is not None:
        decision_lines.append(f"- 표결: {signal.vote_for}대{signal.vote_against}")
    if not decision_lines:
        decision_lines.append(f"- 이벤트: {EVENT_LABEL.get(signal.event_type, '정책 업데이트')}")

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
        "",
        "정책경로 판정",
        f"- {emoji} {LEVEL_LABEL[signal.level]}",
        f"- 판단: {signal.note}",
        f"- 변화 사유: {reason}",
        "",
        "가이던스 체크",
        *guidance,
        "",
        "시장 연결",
        "- BOJ 정책경로와 실제 엔캐리 청산은 별도 판정합니다.",
    ]
    if fx:
        lines.extend(
            [
                f"- USD/JPY {fx['price']:.3f} / 15분 {fx['m15']:+.2f}% / 30분 {fx['m30']:+.2f}%",
                f"- 최근 고점 대비 변화 {fx['drawdown']:+.2f}%",
                "- 환율 급변·미일 단기금리차·변동성·캐리 투자통화 확산은 기존 엔캐리 복합 수급 알림에서 확인합니다.",
            ]
        )
    else:
        lines.append("- USD/JPY 실시간 교차조회 실패 — 정책경로 판정에는 사용하지 않음")

    lines.extend(
        [
            "",
            "다음 확인",
            f"- {next_official_check(now)}",
            "",
            "정확한 의미",
            "- 25bp 인상 자체를 자동으로 🟠 매파 강화로 처리하지 않습니다.",
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
        "fx": fx,
        "checked_at_kst": now.isoformat(timespec="seconds"),
        "next_official_check": next_official_check(now),
    }
    return title, "\n".join(lines), payload


def clear_outputs() -> None:
    for path in (TITLE, BODY, DATA, PENDING, CONFIRMED):
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
    signals = collect(now)
    state = load_state()

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

    title, body, payload = build(selected, selected_reason, now, fx_context())
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
