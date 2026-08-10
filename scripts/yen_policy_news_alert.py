#!/usr/bin/env python3
"""Monitor high-impact yen/BOJ/intervention news and create verified Telegram alerts."""

from __future__ import annotations

import argparse
import datetime as dt
import email.utils
import hashlib
import html
import json
import pathlib
import re
import urllib.parse
import xml.etree.ElementTree as ET
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from zoneinfo import ZoneInfo

from khs_source_fetch import fetch_text, record_source_failure

UTC = dt.timezone.utc
KST = ZoneInfo("Asia/Seoul")
USER_AGENT = "Mozilla/5.0 khs-yen-policy-news/1.3"
MAX_ITEM_AGE_HOURS = 12
CLUSTER_COOLDOWN_HOURS = 24
MAX_ALERT_ITEMS = 3

STATE_PATH = pathlib.Path("data/yen_policy_news_state.json")
PENDING_PATH = pathlib.Path("out/yen_policy_news_pending_state.json")
ALERT_TITLE_PATH = pathlib.Path("out/yen_policy_news_alert_title.txt")
ALERT_BODY_PATH = pathlib.Path("out/yen_policy_news_alert.md")
ALERT_JSON_PATH = pathlib.Path("out/yen_policy_news_alert.json")
CONFIRM_PATH = pathlib.Path("out/yen_policy_news_telegram_confirmed.json")
SUMMARY_PATH = pathlib.Path("out/yen_policy_news_watch.md")

RSS_QUERIES = (
    ("en", '"Bank of Japan" yen intervention U.S. Treasury'),
    ("en", '"Bank of Japan" September rate hike yen'),
    ("en", 'Japan yen joint intervention U.S.'),
    ("en", 'yen rate check Japan intervention'),
    ("ja", '日銀 9月 利上げ 円 為替介入 米国'),
    ("ja", '日米 協調介入 円 日銀 利上げ'),
    ("ja", '共同通信 日銀 9月 利上げ 米国 為替介入'),
)

OFFICIAL_MARKERS = (
    "bank of japan",
    "日本銀行",
    "ministry of finance",
    "財務省",
    "u.s. department of the treasury",
    "us department of the treasury",
    "federal reserve",
    "連邦準備",
)

MAJOR_SOURCE_MARKERS = (
    "reuters",
    "kyodo",
    "共同通信",
    "bloomberg",
    "financial times",
    "nikkei",
    "日本経済新聞",
    "nhk",
    "associated press",
    "ap news",
)

SYNDICATION_MARKERS = (
    "共同通信ニュース",
    "共同通信社提供",
    "kyodo news",
    "reuters",
)

CONTEXT_MARKERS = (
    "yen",
    "円",
    "usd/jpy",
    "ドル円",
    "bank of japan",
    "boj",
    "日銀",
    "foreign exchange",
    "forex",
    "為替",
)

INTERVENTION_MARKERS = (
    "intervention",
    "intervene",
    "yen-buying",
    "yen buying",
    "rate check",
    "為替介入",
    "市場介入",
    "円買い介入",
    "協調介入",
    "レートチェック",
)

ENGLISH_INTERVENTION_ACTIONS = (
    "intervene",
    "intervened",
    "join",
    "joins",
    "joined",
    "participate",
    "participated",
    "participation",
    "support",
    "supports",
    "supported",
    "conduct",
    "conducted",
    "carry out",
    "carried out",
    "buy yen",
    "bought yen",
)

JAPANESE_INTERVENTION_ACTIONS = (
    "介入した",
    "介入を実施",
    "介入を行",
    "介入へ",
    "介入に参加",
    "介入参加",
    "参加した",
)

JOINT_CONTEXT_MARKERS = (
    "joint",
    "coordinated",
    "共同",
    "協調",
)

US_MARKERS = (
    "u.s.",
    " us ",
    "united states",
    "treasury",
    "federal reserve",
    "fed ",
    "米国",
    "米財務省",
    "米政府",
    "frb",
    "連邦準備",
    "ベッセント",
)

HIKE_MARKERS = (
    "rate hike",
    "rate hikes",
    "hike rates",
    "raise rates",
    "higher rates",
    "tightening",
    "利上げ",
    "政策金利",
    "金融引き締め",
)

SEPTEMBER_MARKERS = (
    "september",
    "9月",
)

ACCELERATION_MARKERS = (
    "next meeting",
    "next policy meeting",
    "faster",
    "accelerate",
    "accelerated",
    "earlier",
    "soon",
    "前倒し",
    "加速",
    "早め",
    "次回会合",
)

PREPARATION_MARKERS = (
    "ready to intervene",
    "prepared to intervene",
    "rate check",
    "decisive action",
    "stand ready",
    "介入準備",
    "断固たる措置",
    "レートチェック",
)

CONFIRM_MARKERS = (
    "confirmed",
    "confirms",
    "officially",
    "確認",
    "正式",
)


@dataclass(frozen=True)
class NewsItem:
    title: str
    link: str
    source: str
    description: str
    published: dt.datetime

    @property
    def text(self) -> str:
        return " ".join((self.title, self.description, self.source)).strip()

    @property
    def item_id(self) -> str:
        normalized = normalize_text(f"{self.source}|{self.title}|{self.link}")
        return hashlib.sha256(normalized.encode("utf-8")).hexdigest()[:24]


@dataclass(frozen=True)
class ClassifiedItem:
    item: NewsItem
    topic: str
    material_score: int
    source_level: int
    source_group: str


def normalize_text(value: str) -> str:
    value = html.unescape(value or "").lower()
    value = re.sub(r"<[^>]+>", " ", value)
    value = re.sub(r"[^0-9a-z가-힣ぁ-んァ-ン一-龥]+", " ", value)
    return re.sub(r"\s+", " ", value).strip()


def contains_any(text: str, markers: tuple[str, ...]) -> bool:
    lowered = html.unescape(text or "").lower()
    return any(marker.lower() in lowered for marker in markers)


def contains_normalized_phrase(text: str, markers: tuple[str, ...]) -> bool:
    normalized = f" {normalize_text(text)} "
    return any(f" {normalize_text(marker)} " in normalized for marker in markers)


def source_group(source: str, full_text: str) -> str:
    lowered = html.unescape(f"{source} {full_text}").lower()
    mapping = (
        (("reuters",), "Reuters"),
        (("kyodo", "共同通信"), "Kyodo"),
        (("bloomberg",), "Bloomberg"),
        (("financial times",), "Financial Times"),
        (("nikkei", "日本経済新聞"), "Nikkei"),
        (("nhk",), "NHK"),
        (("associated press", "ap news"), "AP"),
        (("bank of japan", "日本銀行"), "BOJ"),
        (("ministry of finance", "財務省"), "Japan MOF"),
        (("u.s. department of the treasury", "us department of the treasury"), "US Treasury"),
        (("federal reserve", "連邦準備"), "Federal Reserve"),
    )
    for markers, label in mapping:
        if any(marker in lowered for marker in markers):
            return label
    return source.strip() or "unknown"


def source_level(item: NewsItem) -> int:
    source_text = item.source.lower()
    full = item.text.lower()
    if any(marker.lower() in source_text for marker in OFFICIAL_MARKERS):
        return 3
    if any(marker.lower() in source_text for marker in MAJOR_SOURCE_MARKERS):
        return 1
    if any(marker.lower() in full for marker in SYNDICATION_MARKERS):
        return 1
    return 0


def classify(item: NewsItem) -> ClassifiedItem | None:
    text = item.text
    if not contains_any(text, CONTEXT_MARKERS):
        return None

    intervention = contains_any(text, INTERVENTION_MARKERS)
    intervention_action = intervention and (
        contains_normalized_phrase(text, ENGLISH_INTERVENTION_ACTIONS)
        or contains_any(text, JAPANESE_INTERVENTION_ACTIONS)
    )
    preparation = contains_any(text, PREPARATION_MARKERS)
    joint = intervention and contains_any(text, JOINT_CONTEXT_MARKERS)
    confirmed = contains_any(text, CONFIRM_MARKERS)
    us = contains_any(f" {text} ", US_MARKERS)
    hike = contains_any(text, HIKE_MARKERS)
    september = contains_any(text, SEPTEMBER_MARKERS)
    acceleration = contains_any(text, ACCELERATION_MARKERS)

    # Mere market commentary about the aftermath of an old intervention is not a new catalyst.
    if intervention and not intervention_action and not preparation and not confirmed:
        return None

    if intervention and us and joint and (intervention_action or confirmed):
        topic, score = "미·일 공동개입/미국 참여", 5
    elif intervention and us and intervention_action:
        topic, score = "미국의 엔화 개입 참여·지원", 5
    elif intervention and preparation:
        topic, score = "엔화 개입 준비·레이트체크", 4
    elif intervention and (intervention_action or confirmed):
        topic, score = "엔화 시장개입", 4
    elif hike and september and us:
        topic, score = "BOJ 9월 인상·미국 연계", 4
    elif hike and acceleration and us:
        topic, score = "BOJ 조기·가속 인상·미국 연계", 4
    elif hike and september:
        topic, score = "BOJ 9월 인상 기대·신호", 3
    elif hike and acceleration:
        topic, score = "BOJ 조기·가속 인상 기대·신호", 3
    elif hike:
        topic, score = "BOJ 금리인상 신호", 2
    else:
        return None

    level = source_level(item)
    if level == 0:
        return None
    return ClassifiedItem(item, topic, score, level, source_group(item.source, item.text))


def google_news_rss_url(language: str, query: str) -> str:
    if language == "ja":
        params = {"q": query, "hl": "ja", "gl": "JP", "ceid": "JP:ja"}
    else:
        params = {"q": query, "hl": "en-US", "gl": "US", "ceid": "US:en"}
    return "https://news.google.com/rss/search?" + urllib.parse.urlencode(params)


def parse_pubdate(value: str) -> dt.datetime | None:
    try:
        parsed = email.utils.parsedate_to_datetime(value)
    except (TypeError, ValueError):
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=UTC)
    return parsed.astimezone(UTC)


def parse_rss(xml_text: str) -> list[NewsItem]:
    root = ET.fromstring(xml_text)
    items: list[NewsItem] = []
    for node in root.findall(".//item"):
        title = (node.findtext("title") or "").strip()
        link = (node.findtext("link") or "").strip()
        description = (node.findtext("description") or "").strip()
        pub = parse_pubdate((node.findtext("pubDate") or "").strip())
        source_node = node.find("source")
        source = (source_node.text or "").strip() if source_node is not None else ""
        if title and link and pub is not None:
            items.append(NewsItem(title, link, source, description, pub))
    return items


def fetch_query(language: str, query: str, current: dt.datetime) -> tuple[list[NewsItem], str | None]:
    url = google_news_rss_url(language, query)
    text, error = fetch_text(
        url,
        USER_AGENT,
        timeout=18,
        attempts=2,
        accept="application/rss+xml,application/xml,text/xml,*/*",
    )
    if error or not text:
        record_source_failure(
            lane="yen_policy_news",
            source_name=f"Google News RSS {language}",
            source_url=url,
            error=error or "empty response",
            checked_at=current.astimezone(KST),
        )
        return [], error or "empty response"
    try:
        return parse_rss(text), None
    except Exception as exc:
        error = f"{type(exc).__name__}: {exc}"
        record_source_failure(
            lane="yen_policy_news",
            source_name=f"Google News RSS {language}",
            source_url=url,
            error=error,
            checked_at=current.astimezone(KST),
        )
        return [], error


def collect_items(current: dt.datetime) -> tuple[list[NewsItem], list[str]]:
    unique: dict[str, NewsItem] = {}
    errors: list[str] = []
    with ThreadPoolExecutor(max_workers=4) as executor:
        futures = {
            executor.submit(fetch_query, language, query, current): (language, query)
            for language, query in RSS_QUERIES
        }
        for future in as_completed(futures):
            language, query = futures[future]
            try:
                items, error = future.result()
            except Exception as exc:
                items, error = [], f"{type(exc).__name__}: {exc}"
            if error:
                errors.append(f"{language}:{query}: {error}")
            for item in items:
                unique[item.item_id] = item
    cutoff = current - dt.timedelta(hours=MAX_ITEM_AGE_HOURS)
    return sorted(
        (item for item in unique.values() if cutoff <= item.published <= current + dt.timedelta(minutes=10)),
        key=lambda item: item.published,
        reverse=True,
    ), errors


def topic_key(topic: str) -> str:
    return hashlib.sha256(topic.encode("utf-8")).hexdigest()[:12]


def corroboration_rank(item: ClassifiedItem, universe: list[ClassifiedItem]) -> tuple[int, list[str]]:
    if item.source_level >= 3:
        return 3, [item.source_group]
    window_start = item.item.published - dt.timedelta(hours=6)
    window_end = item.item.published + dt.timedelta(hours=6)
    groups = sorted(
        {
            other.source_group
            for other in universe
            if other.topic == item.topic
            and other.source_level >= 1
            and window_start <= other.item.published <= window_end
        }
    )
    if len(groups) >= 2:
        return 2, groups
    return 1, groups or [item.source_group]


def rank_label(rank: int) -> str:
    return {3: "공식 확인", 2: "복수 주요매체 확인", 1: "미확인 주요보도"}.get(rank, "미확인")


def read_state(path: pathlib.Path = STATE_PATH) -> dict:
    if not path.exists():
        return {"seen_item_ids": [], "clusters": {}}
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {"seen_item_ids": [], "clusters": {}}
    if not isinstance(value, dict):
        return {"seen_item_ids": [], "clusters": {}}
    value.setdefault("seen_item_ids", [])
    value.setdefault("clusters", {})
    return value


def should_alert(
    item: ClassifiedItem,
    rank: int,
    state: dict,
    current: dt.datetime,
) -> bool:
    if item.item.item_id in set(state.get("seen_item_ids") or []):
        return False
    if item.material_score < 3 and rank < 2:
        return False
    key = topic_key(item.topic)
    cluster = (state.get("clusters") or {}).get(key) or {}
    previous_rank = int(cluster.get("rank") or 0)
    previous_score = int(cluster.get("material_score") or 0)
    previous_epoch = float(cluster.get("sent_epoch") or 0)
    elapsed = current.timestamp() - previous_epoch if previous_epoch else 10**9
    return (
        elapsed >= CLUSTER_COOLDOWN_HOURS * 3600
        or rank > previous_rank
        or item.material_score > previous_score
    )


def select_alerts(
    classified: list[ClassifiedItem], state: dict, current: dt.datetime
) -> list[tuple[ClassifiedItem, int, list[str]]]:
    ranked: list[tuple[ClassifiedItem, int, list[str]]] = []
    for item in classified:
        rank, groups = corroboration_rank(item, classified)
        if should_alert(item, rank, state, current):
            ranked.append((item, rank, groups))
    ranked.sort(
        key=lambda row: (row[1], row[0].material_score, row[0].item.published.timestamp()),
        reverse=True,
    )
    selected: list[tuple[ClassifiedItem, int, list[str]]] = []
    used_topics: set[str] = set()
    for row in ranked:
        if row[0].topic in used_topics:
            continue
        selected.append(row)
        used_topics.add(row[0].topic)
        if len(selected) >= MAX_ALERT_ITEMS:
            break
    return selected


def axis_lines(topic: str) -> list[str]:
    lines: list[str] = []
    if "개입" in topic or "미국" in topic:
        lines.append("수급: 엔화 숏커버·엔캐리 청산 압력 상승 가능")
    if "인상" in topic or "BOJ" in topic:
        lines.append("할인율: 일본 정책금리·JGB 금리 상방 위험 확대")
    lines.append("돈 버는 능력: 엔고가 지속되면 일본 수출주 부담·수입업종 원가 완화")
    lines.append("시간표: BOJ 차기 회의·미일 당국 후속 발언에서 사실 확인 필요")
    return lines


def build_message(
    selected: list[tuple[ClassifiedItem, int, list[str]]], current: dt.datetime
) -> tuple[str, str, dict]:
    top_rank = max(rank for _, rank, _ in selected)
    prefix = "🚨" if top_rank >= 2 else "⚠️"
    title = f"{prefix} 엔화 정책 촉매 알림 — {rank_label(top_rank)}"
    body_lines = [
        f"조회 시각: {current.astimezone(KST).strftime('%Y-%m-%d %H:%M:%S KST')}",
        "가격 조건과 별개인 선행 정책·개입 뉴스 경보입니다.",
        "",
    ]
    payload_items: list[dict] = []
    for index, (classified, rank, groups) in enumerate(selected, start=1):
        item = classified.item
        headline = html.unescape(re.sub(r"<[^>]+>", " ", item.title)).strip()
        body_lines.extend(
            [
                f"{index}) {classified.topic} · {rank_label(rank)}",
                f"출처: {item.source or classified.source_group} · {item.published.astimezone(KST).strftime('%m-%d %H:%M KST')}",
                f"헤드라인: {headline}",
                f"교차확인: {', '.join(groups)}",
                *axis_lines(classified.topic),
                "",
            ]
        )
        payload_items.append(
            {
                "item_id": item.item_id,
                "topic": classified.topic,
                "material_score": classified.material_score,
                "rank": rank,
                "rank_label": rank_label(rank),
                "source": item.source,
                "source_group": classified.source_group,
                "corroborating_groups": groups,
                "headline": item.title,
                "link": item.link,
                "published_at_kst": item.published.astimezone(KST).isoformat(timespec="seconds"),
            }
        )
    body_lines.append(
        "주의: 단일 주요매체 보도는 ‘미확인 주요보도’로만 전송하며 공식 확인 시 확인도 상향 재알림합니다."
    )
    return title, "\n".join(body_lines).strip(), {"items": payload_items}


def pending_state(state: dict, selected: list[tuple[ClassifiedItem, int, list[str]]], current: dt.datetime) -> dict:
    updated = json.loads(json.dumps(state))
    seen = list(updated.get("seen_item_ids") or [])
    clusters = dict(updated.get("clusters") or {})
    for classified, rank, _groups in selected:
        item = classified.item
        if item.item_id not in seen:
            seen.append(item.item_id)
        clusters[topic_key(classified.topic)] = {
            "topic": classified.topic,
            "rank": rank,
            "material_score": classified.material_score,
            "sent_epoch": current.timestamp(),
            "headline": item.title,
            "source_group": classified.source_group,
        }
    updated["seen_item_ids"] = seen[-200:]
    updated["clusters"] = clusters
    updated["updated_at_kst"] = current.astimezone(KST).isoformat(timespec="seconds")
    return updated


def write_json(path: pathlib.Path, value: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def write_summary(status: str, *, candidates: int = 0, errors: int = 0) -> None:
    SUMMARY_PATH.parent.mkdir(parents=True, exist_ok=True)
    SUMMARY_PATH.write_text(
        "\n".join(
            [
                "# 엔화 정책 촉매 감시",
                f"- 상태: {status}",
                f"- 유효 후보: {candidates}",
                f"- 소스 오류: {errors}",
            ]
        )
        + "\n",
        encoding="utf-8",
    )


def process(current: dt.datetime | None = None) -> dict:
    current = (current or dt.datetime.now(UTC)).astimezone(UTC)
    items, errors = collect_items(current)
    classified = [result for item in items if (result := classify(item)) is not None]
    state = read_state()
    selected = select_alerts(classified, state, current)
    if not selected:
        write_summary("새 정책 촉매 없음", candidates=len(classified), errors=len(errors))
        return {"alerted": False, "candidates": len(classified), "errors": len(errors)}

    title, body, payload = build_message(selected, current)
    ALERT_TITLE_PATH.parent.mkdir(parents=True, exist_ok=True)
    ALERT_TITLE_PATH.write_text(title + "\n", encoding="utf-8")
    ALERT_BODY_PATH.write_text(body + "\n", encoding="utf-8")
    payload.update(
        {
            "policy_news_alert": True,
            "checked_at_kst": current.astimezone(KST).isoformat(timespec="seconds"),
        }
    )
    write_json(ALERT_JSON_PATH, payload)
    write_json(PENDING_PATH, pending_state(state, selected, current))
    write_summary("정책 촉매 알림 생성", candidates=len(classified), errors=len(errors))
    return {"alerted": True, "items": len(selected), "candidates": len(classified), "errors": len(errors)}


def finalize() -> bool:
    if not PENDING_PATH.exists() or not CONFIRM_PATH.exists():
        print("Yen policy news Telegram confirmation missing; pending state not finalized.")
        return False
    confirmation = read_state(CONFIRM_PATH)
    if confirmation.get("status") != "confirmed" or confirmation.get("lane") != "yen_policy_news":
        print("Yen policy news confirmation invalid; pending state not finalized.")
        return False
    pending = read_state(PENDING_PATH)
    write_json(STATE_PATH, pending)
    print(f"Finalized yen policy news state: {STATE_PATH}")
    return True


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--finalize", action="store_true")
    args = parser.parse_args()
    result = {"finalized": finalize()} if args.finalize else process()
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
