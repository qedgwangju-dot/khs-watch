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
STATE_PATH = ROOT / "data" / "clarity_industry_pressure_state.json"
PENDING_STATE_PATH = ROOT / "out" / "clarity_industry_pressure_pending_state.json"
ALERT_JSON = ROOT / "out" / "clarity_watch_alert.json"
STATUS_PATH = ROOT / "out" / "clarity_industry_pressure_status.json"

NEWS_RSS = "https://news.google.com/rss/search"
QUERIES = [
    '"CLARITY Act" Coinbase',
    '"CLARITY Act" "Ryan VanGrack"',
    '"CLARITY Act" "Brian Armstrong"',
    '"CLARITY Act" BitGo',
    '"CLARITY Act" crypto industry vote',
    '"Digital Asset Market Clarity Act" Coinbase',
]

TIER1_LABELS = {
    "bloomberg": "Bloomberg",
    "reuters": "Reuters",
    "coindesk": "CoinDesk",
    "the block": "The Block",
    "semafor": "Semafor",
    "coinbase": "Coinbase",
}
TIER2_LABELS = {
    "cointelegraph": "Cointelegraph",
    "crypto briefing": "Crypto Briefing",
    "bitcoin magazine": "Bitcoin Magazine",
    "benzinga": "Benzinga",
    "coinmarketcap": "CoinMarketCap",
}
DISCOVERY_ONLY_LABELS = {"tokenpost": "TokenPost"}

STRICT_TOPIC_RE = re.compile(
    r"(?:\bCLARITY\s+(?:Act|Bill)\b|H\.?\s*R\.?\s*3633|Digital\s+Asset\s+Market\s+Clarity\s+Act|"
    r"digital\s+asset\s+market\s+structure|crypto\s+market\s+structure)",
    re.I,
)
ACTION_RE = re.compile(
    r"\b(?:vote|voting|pass|passes|passed|passage|urge|urges|urged|call\s+for|calls\s+for|push|pushes|pushed|"
    r"support|supports|supported|advance|advances|advanced|finish|finalize|act\s+now|stop\s+talking|start\s+voting|"
    r"one-yard\s+line|one\s+yard\s+line)\b",
    re.I,
)
MOBILITY_RE = re.compile(
    r"\b(?:innovation|tokenization|tokenized|offshore|overseas|outside\s+the\s+united\s+states|outside\s+the\s+u\.?s\.?|"
    r"where\s+it\s+happens|where\s+the\s+market\s+lives|jurisdiction|capital|developer|talent|migration|stablecoin|"
    r"wall\s+street|banks?|traditional\s+finance)\b",
    re.I,
)

ACTORS = [
    (re.compile(r"\bRyan\s+Van\s*Grack\b|\bRyan\s+Vangrack\b|\bVan\s*Grack\b|\bVangrack\b", re.I), "Coinbase 부회장 Ryan VanGrack", "Coinbase"),
    (re.compile(r"\bBrian\s+Armstrong\b", re.I), "Coinbase CEO Brian Armstrong", "Coinbase"),
    (re.compile(r"\bPaul\s+Grewal\b", re.I), "Coinbase CLO Paul Grewal", "Coinbase"),
    (re.compile(r"\bMike\s+Belshe\b", re.I), "BitGo CEO Mike Belshe", "BitGo"),
]


def clean(value):
    return re.sub(r"\s+", " ", html.unescape(str(value or ""))).strip()


def fetch_bytes(url, timeout=15):
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 (KHS-CLARITY-Industry-Watch/1.0)"})
    with urllib.request.urlopen(req, timeout=timeout) as response:
        return response.read()


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
    for pattern, label, company in ACTORS:
        if pattern.search(text):
            return label, company
    return "", ""


def google_news_items(query):
    params = urllib.parse.urlencode({"q": query, "hl": "en-US", "gl": "US", "ceid": "US:en"})
    root = ET.fromstring(fetch_bytes(f"{NEWS_RSS}?{params}"))
    items = []
    for item in root.findall(".//item")[:60]:
        source_node = item.find("source")
        items.append({
            "title": clean(item.findtext("title")),
            "description": clean(item.findtext("description")),
            "url": clean(item.findtext("link")),
            "pubDate": clean(item.findtext("pubDate")),
            "source": clean(source_node.text if source_node is not None else ""),
            "source_url": clean(source_node.attrib.get("url") if source_node is not None else ""),
            "matched_query": query,
        })
    return items


def resolve_original_url(news_url):
    try:
        req = urllib.request.Request(news_url, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=8) as response:
            final = response.geturl()
            body = response.read(250000).decode("utf-8", "ignore")
        if "news.google.com" not in urllib.parse.urlparse(final).netloc:
            return final
        for pattern in [
            r'<link[^>]+rel=["\']canonical["\'][^>]+href=["\'](https?://[^"\']+)',
            r'"url"\s*:\s*"(https?:\\/\\/[^"\\]+)"',
        ]:
            match = re.search(pattern, body, re.I)
            if match:
                candidate = html.unescape(match.group(1)).replace("\\/", "/")
                if "news.google.com" not in urllib.parse.urlparse(candidate).netloc:
                    return candidate
    except Exception:
        pass
    return news_url


def signature(actor, company, title):
    normalized = re.sub(r"[^a-z0-9가-힣]+", " ", clean(title).lower())
    normalized = re.sub(r"\b(?:today|yesterday|monday|tuesday|wednesday|thursday|friday|saturday|sunday)\b", " ", normalized)
    normalized = re.sub(r"\s+", " ", normalized).strip()
    return hashlib.sha256(f"{actor}|{company}|industry_pressure|{normalized[:260]}".encode("utf-8")).hexdigest()


def make_event(item, actor, company, source_label, signal):
    published = parse_date(item["pubDate"])
    date = published.astimezone(ZoneInfo("America/New_York")).strftime("%a, %d %b %Y %H:%M:%S %z") if published else ""
    mobility = bool(MOBILITY_RE.search(signal))
    detail = (
        f"{actor}이(가) 상원에 CLARITY 법안의 실제 표결·통과를 촉구했습니다. "
        "직접 규제 대상 사업자의 이해관계가 있는 발언이므로 정부 공식 변화와 동일하게 보지 않지만, "
        "입법 지연이 소비자 보호·법집행·불법금융 대응과 미국 내 사업·혁신 입지에 미치는 영향을 보여주는 업계 압박 신호로 추적합니다."
    )
    if mobility:
        detail += " 특히 토큰화·금융 인프라 혁신은 의회 결정과 무관하게 진행되며, 규제가 늦으면 활동이 미국 밖에서 먼저 커질 수 있다는 경쟁력·자금이동 경고가 포함됐습니다."
    return {
        "source": f"{source_label} 업계 발언 검증",
        "event_type": "핵심 사업자·업계 표결 촉구",
        "title": f"{actor}, CLARITY 법안 표결·통과 촉구",
        "url": resolve_original_url(item["url"]),
        "date": date,
        "detail": detail,
        "industry_actor": actor,
        "industry_company": company,
        "reported_title": item["title"],
        "mobility_warning": mobility,
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
    cutoff = now - dt.timedelta(days=5)
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
        signal = clean(f"{item['title']} {item['description']}")
        actor, company = extract_actor(signal)
        if not actor or not STRICT_TOPIC_RE.search(signal) or not ACTION_RE.search(signal):
            continue
        candidates.append({
            "item": item,
            "actor": actor,
            "company": company,
            "tier": tier,
            "source_label": source_label,
            "signal": signal,
        })

    groups = {}
    for candidate in candidates:
        groups.setdefault((candidate["actor"], candidate["company"]), []).append(candidate)

    accepted = []
    for group in groups.values():
        tier1 = [item for item in group if item["tier"] == 1]
        if tier1:
            accepted.append(max(tier1, key=lambda x: parse_date(x["item"]["pubDate"]) or dt.datetime.min.replace(tzinfo=ZoneInfo("UTC"))))
            continue
        tier2 = [item for item in group if item["tier"] == 2]
        if len({item["source_label"] for item in tier2}) >= 2:
            accepted.append(max(tier2, key=lambda x: parse_date(x["item"]["pubDate"]) or dt.datetime.min.replace(tzinfo=ZoneInfo("UTC"))))

    state = load_state()
    baseline = not bool(state.get("initialized"))
    old_seen = set(state.get("seen_signatures") or [])
    current_signatures = []
    new_events = []
    for candidate in accepted:
        item = candidate["item"]
        sig = signature(candidate["actor"], candidate["company"], item["title"])
        current_signatures.append(sig)
        if baseline or sig in old_seen:
            continue
        new_events.append(make_event(item, candidate["actor"], candidate["company"], candidate["source_label"], candidate["signal"]))

    merged = list(dict.fromkeys(list(state.get("seen_signatures") or []) + current_signatures))[-500:]
    pending = {
        "initialized": True,
        "last_checked_utc": now.isoformat(timespec="seconds"),
        "seen_signatures": merged,
        "accepted_current": len(accepted),
        "source_errors": errors,
    }
    PENDING_STATE_PATH.write_text(json.dumps(pending, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

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
    print(f"clarity_industry_pressure_new={len(new_events)} baseline={str(baseline).lower()} accepted={len(accepted)}")


if __name__ == "__main__":
    main()
