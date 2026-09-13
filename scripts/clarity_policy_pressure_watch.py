#!/usr/bin/env python3
import datetime as dt
import email.utils
import hashlib
import html
import json
import pathlib
import re
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from zoneinfo import ZoneInfo

ROOT = pathlib.Path(__file__).resolve().parents[1]
STATE_PATH = ROOT / "data" / "clarity_policy_pressure_state.json"
PENDING_STATE_PATH = ROOT / "out" / "clarity_policy_pressure_pending_state.json"
ALERT_JSON = ROOT / "out" / "clarity_watch_alert.json"
STATUS_PATH = ROOT / "out" / "clarity_policy_pressure_status.json"

NEWS_RSS = "https://news.google.com/rss/search"
QUERIES = [
    '"CLARITY Act" Trump',
    '"CLARITY Act" Bessent',
    '"CLARITY Act" "White House"',
    '"CLARITY Act" Senate ethics',
]

TIER1_LABELS = {
    "reuters": "Reuters",
    "bloomberg": "Bloomberg",
    "bloomberg law": "Bloomberg Law",
    "bloomberg tax": "Bloomberg Tax",
    "coindesk": "CoinDesk",
    "the block": "The Block",
    "semafor": "Semafor",
}
TIER2_LABELS = {
    "cointelegraph": "Cointelegraph",
    "crypto briefing": "Crypto Briefing",
    "bitcoin magazine": "Bitcoin Magazine",
    "benzinga": "Benzinga",
}
DISCOVERY_ONLY_LABELS = {
    "tokenpost": "TokenPost",
}

STRICT_TOPIC_RE = re.compile(
    r"(?:\bCLARITY\s+(?:Act|Bill)\b|H\.?\s*R\.?\s*3633|Digital\s+Asset\s+Market\s+Clarity\s+Act|"
    r"digital\s+asset\s+market\s+structure|crypto\s+market\s+structure|(?:crypto|digital\s+asset)\s+(?:bill|legislation))",
    re.I,
)
ACTION_RE = re.compile(
    r"\b(?:urge[sd]?|call(?:s|ed)?\s+(?:on|for)|press(?:es|ed)?|push(?:es|ed)?|back(?:s|ed)?|support(?:s|ed)?|"
    r"advance[sd]?|pass(?:es|ed|age)?|motion\s+to\s+proceed|remain\s+at\s+the\s+negotiating\s+table|"
    r"oppose[sd]?|block(?:s|ed)?|ethics?|conflict\s+of\s+interest|national\s+security|leadership|negotiat(?:e|es|ed|ion|ions)?)\b",
    re.I,
)
RISK_RE = re.compile(r"\b(?:oppose[sd]?|block(?:s|ed)?|ethics?|conflict\s+of\s+interest|corruption)\b", re.I)

ACTORS = [
    (re.compile(r"\b(?:President\s+)?Donald\s+Trump\b|\bPresident\s+Trump\b|\bTrump\b", re.I), "Trump 대통령"),
    (re.compile(r"\bScott\s+Bessent\b|\bTreasury\s+Secretary\s+Bessent\b|\bBessent\b", re.I), "Bessent 재무장관"),
    (re.compile(r"\bWhite\s+House\b", re.I), "백악관"),
    (re.compile(r"\bPatrick\s+Witt\b", re.I), "백악관 디지털자산 고문 Patrick Witt"),
    (re.compile(r"\bJohn\s+Thune\b|\bSenate\s+Majority\s+Leader\b", re.I), "상원 다수당 지도부"),
    (re.compile(r"\bTim\s+Scott\b|\bChairman\s+Scott\b", re.I), "상원 은행위원장 Tim Scott"),
    (re.compile(r"\bElizabeth\s+Warren\b|\bSenator\s+Warren\b", re.I), "Elizabeth Warren 상원의원"),
]


def clean(value):
    return re.sub(r"\s+", " ", html.unescape(str(value or ""))).strip()


def fetch_bytes(url, timeout=15):
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 (KHS-CLARITY-Policy-Watch/1.2)"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.read()


def parse_date(value):
    try:
        parsed = email.utils.parsedate_to_datetime(clean(value))
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=ZoneInfo("UTC"))
        return parsed.astimezone(ZoneInfo("UTC"))
    except Exception:
        return None


def source_tier(label):
    low = clean(label).lower()
    for key, canonical in TIER1_LABELS.items():
        if key in low:
            return 1, canonical
    for key, canonical in TIER2_LABELS.items():
        if key in low:
            return 2, canonical
    for key, canonical in DISCOVERY_ONLY_LABELS.items():
        if key in low:
            return 3, canonical
    return 0, clean(label)


def extract_actor(text):
    for pattern, label in ACTORS:
        if pattern.search(text):
            return label
    return ""


def google_news_items(query):
    params = urllib.parse.urlencode({"q": query, "hl": "en-US", "gl": "US", "ceid": "US:en"})
    root = ET.fromstring(fetch_bytes(f"{NEWS_RSS}?{params}"))
    items = []
    for item in root.findall(".//item")[:60]:
        title = clean(item.findtext("title"))
        link = clean(item.findtext("link"))
        pub = clean(item.findtext("pubDate"))
        source_node = item.find("source")
        source = clean(source_node.text if source_node is not None else "")
        source_url = clean(source_node.attrib.get("url") if source_node is not None else "")
        items.append({
            "title": title,
            "url": link,
            "pubDate": pub,
            "source": source,
            "source_url": source_url,
            "matched_query": query,
        })
    return items


def resolve_original_url(news_url):
    """Best effort only. A working Google News redirect is kept if publisher URL cannot be extracted."""
    try:
        req = urllib.request.Request(news_url, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=8) as r:
            final = r.geturl()
            body = r.read(250000).decode("utf-8", "ignore")
        if "news.google.com" not in urllib.parse.urlparse(final).netloc:
            return final
        # Google News pages often contain the publisher URL in canonical/amp links or JSON payloads.
        for pattern in [
            r'<link[^>]+rel=["\']canonical["\'][^>]+href=["\'](https?://[^"\']+)',
            r'"url"\s*:\s*"(https?:\\/\\/[^"\\]+)"',
        ]:
            m = re.search(pattern, body, re.I)
            if m:
                candidate = html.unescape(m.group(1)).replace("\\/", "/")
                if "news.google.com" not in urllib.parse.urlparse(candidate).netloc:
                    return candidate
    except Exception:
        pass
    return news_url


def signature(actor, event_type, title):
    normalized = re.sub(r"[^a-z0-9가-힣]+", " ", clean(title).lower())
    normalized = re.sub(r"\b(?:today|yesterday|wednesday|thursday|friday|monday|tuesday|sunday|saturday)\b", " ", normalized)
    normalized = re.sub(r"\s+", " ", normalized).strip()
    return hashlib.sha256(f"{actor}|{event_type}|{normalized[:260]}".encode("utf-8")).hexdigest()


def korean_event(item, actor, event_type, source_label):
    if actor == "Trump 대통령":
        ko_title = "Trump 대통령, CLARITY 법안 처리·통과를 의회에 촉구"
    elif actor == "Bessent 재무장관":
        ko_title = "Bessent 재무장관, 상원에 CLARITY 법안 절차 진행을 촉구"
    elif event_type == "정치·윤리 표결 변수":
        ko_title = f"{actor or '미국 정치권'}, CLARITY 법안의 윤리·이해충돌 쟁점 부각"
    else:
        ko_title = f"{actor or '미국 정책 당국'}, CLARITY 법안 처리 압박 강화"

    if event_type == "정치·윤리 표결 변수":
        detail = (
            "CLARITY 법안 자체 조문 외에 대통령·정부 관계자의 암호자산 이해관계와 윤리 조항이 상원 표 확보의 변수로 부각됐습니다. "
            "이는 현재 매출보다 통과 확률과 시간표를 바꾸는 정치적 변수입니다."
        )
    else:
        detail = (
            f"{actor or '미국 고위 정책 당사자'}가 CLARITY 법안의 통과·절차 진행을 공개적으로 압박한 새 발언이 신뢰 매체에서 확인됐습니다. "
            "실제 표결이나 법률 효력 발생은 아니지만 상원 표결 시간표와 협상 압력을 바꿀 수 있는 정책 신호입니다."
        )
        if "national security" in item["title"].lower() or "allies" in item["title"].lower():
            detail += " 미국의 디지털자산 주도권과 국가안보 논리까지 연결해 처리 필요성을 강조했습니다."

    published = parse_date(item["pubDate"])
    date = published.astimezone(ZoneInfo("America/New_York")).strftime("%a, %d %b %Y %H:%M:%S %z") if published else ""
    return {
        "source": f"{source_label} 정책 발언 검증",
        "event_type": event_type,
        "title": ko_title,
        "url": resolve_original_url(item["url"]),
        "date": date,
        "detail": detail,
        "policy_actor": actor,
        "reported_title": item["title"],
    }


def load_state():
    if not STATE_PATH.exists():
        return {}
    try:
        return json.loads(STATE_PATH.read_text(encoding="utf-8"))
    except Exception:
        return {}


def main():
    now = dt.datetime.now(ZoneInfo("UTC"))
    cutoff = now - dt.timedelta(days=4)
    errors = []
    by_key = {}
    for query in QUERIES:
        try:
            for item in google_news_items(query):
                key = (item["title"], item["source"], item["pubDate"])
                if key not in by_key:
                    by_key[key] = item
                else:
                    by_key[key]["matched_query"] += " | " + query
        except Exception as exc:
            errors.append(f"{query}: {exc}")

    candidates = []
    for item in by_key.values():
        published = parse_date(item["pubDate"])
        if published is None or published < cutoff or published > now + dt.timedelta(hours=2):
            continue
        tier, source_label = source_tier(item["source"])
        if tier == 0:
            continue
        title = item["title"]
        actor = extract_actor(title)
        if not actor or not ACTION_RE.search(title) or not STRICT_TOPIC_RE.search(title):
            continue
        event_type = "정치·윤리 표결 변수" if RISK_RE.search(title) else "행정부·핵심 당사자 통과 촉구"
        candidates.append({"item": item, "actor": actor, "event_type": event_type, "tier": tier, "source_label": source_label})

    groups = {}
    for candidate in candidates:
        groups.setdefault((candidate["actor"], candidate["event_type"]), []).append(candidate)

    accepted = []
    for group in groups.values():
        tier1 = [x for x in group if x["tier"] == 1]
        if tier1:
            accepted.append(max(tier1, key=lambda x: parse_date(x["item"]["pubDate"]) or dt.datetime.min.replace(tzinfo=ZoneInfo("UTC"))))
            continue
        tier2 = [x for x in group if x["tier"] == 2]
        if len({x["source_label"] for x in tier2}) >= 2:
            accepted.append(max(tier2, key=lambda x: parse_date(x["item"]["pubDate"]) or dt.datetime.min.replace(tzinfo=ZoneInfo("UTC"))))

    state = load_state()
    baseline = not bool(state.get("initialized"))
    old_seen = set(state.get("seen_signatures") or [])
    current = []
    new_events = []
    for candidate in accepted:
        item = candidate["item"]
        sig = signature(candidate["actor"], candidate["event_type"], item["title"])
        current.append(sig)
        if baseline or sig in old_seen:
            continue
        new_events.append(korean_event(item, candidate["actor"], candidate["event_type"], candidate["source_label"]))

    merged = list(dict.fromkeys(list(state.get("seen_signatures") or []) + current))[-500:]
    PENDING_STATE_PATH.write_text(json.dumps({
        "initialized": True,
        "last_checked_utc": now.isoformat(timespec="seconds"),
        "seen_signatures": merged,
        "accepted_current": len(accepted),
        "source_errors": errors,
    }, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    existing = []
    if ALERT_JSON.exists():
        try:
            existing = json.loads(ALERT_JSON.read_text(encoding="utf-8"))
        except Exception:
            existing = []
    if new_events:
        existing.extend(new_events)
        ALERT_JSON.write_text(json.dumps(existing, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    STATUS_PATH.write_text(json.dumps({
        "baseline": baseline,
        "raw_articles": len(by_key),
        "candidates": len(candidates),
        "accepted_current": len(accepted),
        "new_events": len(new_events),
        "errors": errors,
    }, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"clarity_policy_pressure_new={len(new_events)} baseline={str(baseline).lower()} accepted={len(accepted)}")


if __name__ == "__main__":
    main()
