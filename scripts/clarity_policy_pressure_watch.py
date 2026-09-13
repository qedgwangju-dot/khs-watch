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
from zoneinfo import ZoneInfo

from bs4 import BeautifulSoup

ROOT = pathlib.Path(__file__).resolve().parents[1]
STATE_PATH = ROOT / "data" / "clarity_policy_pressure_state.json"
PENDING_STATE_PATH = ROOT / "out" / "clarity_policy_pressure_pending_state.json"
ALERT_JSON = ROOT / "out" / "clarity_watch_alert.json"
STATUS_PATH = ROOT / "out" / "clarity_policy_pressure_status.json"

GDELT_ENDPOINT = "https://api.gdeltproject.org/api/v2/doc/doc"
QUERIES = [
    '"CLARITY Act" Trump',
    '"CLARITY Act" Bessent',
    '"CLARITY Act" "White House"',
    '"CLARITY Act" Senate ethics',
    '"Digital Asset Market Clarity Act" Senate',
]

# Tier 1 can trigger on one fresh report because these outlets routinely report directly
# from official remarks/documents. Tier 2 needs corroboration by another accepted outlet.
TIER1_DOMAINS = {
    "reuters.com": "Reuters",
    "bloomberg.com": "Bloomberg",
    "news.bloomberglaw.com": "Bloomberg Law",
    "news.bloombergtax.com": "Bloomberg Tax",
    "coindesk.com": "CoinDesk",
    "theblock.co": "The Block",
    "semafor.com": "Semafor",
}
TIER2_DOMAINS = {
    "cointelegraph.com": "Cointelegraph",
    "cryptobriefing.com": "Crypto Briefing",
    "bitcoinmagazine.com": "Bitcoin Magazine",
    "benzinga.com": "Benzinga",
}
DISCOVERY_ONLY_DOMAINS = {
    "tokenpost.kr": "TokenPost",
    "tokenpost.com": "TokenPost",
}

STRICT_TOPIC_RE = re.compile(
    r"(?:\bCLARITY\s+(?:Act|Bill)\b|H\.?\s*R\.?\s*3633|Digital\s+Asset\s+Market\s+Clarity\s+Act|digital\s+asset\s+market\s+structure|crypto\s+market\s+structure)",
    re.I,
)
ACTION_RE = re.compile(
    r"\b(?:urge[sd]?|call(?:s|ed)?\s+(?:on|for)|press(?:es|ed)?|push(?:es|ed)?|back(?:s|ed)?|support(?:s|ed)?|"
    r"advance[sd]?|pass(?:es|ed|age)?|motion\s+to\s+proceed|remain\s+at\s+the\s+negotiating\s+table|"
    r"oppose[sd]?|block(?:s|ed)?|ethics?|conflict\s+of\s+interest|national\s+security|leadership)\b",
    re.I,
)
SUPPORT_RE = re.compile(
    r"\b(?:urge[sd]?|call(?:s|ed)?\s+(?:on|for)|press(?:es|ed)?|push(?:es|ed)?|back(?:s|ed)?|support(?:s|ed)?|advance[sd]?|pass(?:es|ed|age)?|motion\s+to\s+proceed|negotiat)\b",
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


def fetch_json(url, timeout=30):
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 (KHS-CLARITY-Policy-Watch/1.0)"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read().decode("utf-8", "ignore"))


def fetch_text(url, timeout=20):
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.read().decode("utf-8", "ignore"), r.geturl()


def parse_seen_date(value):
    value = clean(value)
    if not value:
        return None
    # GDELT commonly returns YYYYMMDDTHHMMSSZ.
    for fmt in ("%Y%m%dT%H%M%SZ", "%Y%m%dT%H%M%S", "%Y-%m-%dT%H:%M:%SZ", "%Y-%m-%d %H:%M:%S"):
        try:
            return dt.datetime.strptime(value, fmt).replace(tzinfo=ZoneInfo("UTC"))
        except ValueError:
            pass
    try:
        parsed = email.utils.parsedate_to_datetime(value)
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=ZoneInfo("UTC"))
        return parsed.astimezone(ZoneInfo("UTC"))
    except Exception:
        return None


def domain_label(url):
    host = urllib.parse.urlparse(url).netloc.lower().removeprefix("www.")
    for domain, label in {**TIER1_DOMAINS, **TIER2_DOMAINS, **DISCOVERY_ONLY_DOMAINS}.items():
        d = domain.removeprefix("www.")
        if host == d or host.endswith("." + d):
            tier = 1 if domain in TIER1_DOMAINS else (2 if domain in TIER2_DOMAINS else 3)
            return tier, label
    return 0, host


def extract_actor(text):
    for pattern, label in ACTORS:
        if pattern.search(text):
            return label
    return ""


def article_body(url):
    try:
        raw, final_url = fetch_text(url)
        soup = BeautifulSoup(raw, "html.parser")
        for tag in soup(["script", "style", "noscript", "svg"]):
            tag.decompose()
        text = clean(soup.get_text(" ", strip=True))
        return text[:12000], final_url
    except Exception:
        return "", url


def gdelt_articles(query):
    params = urllib.parse.urlencode({
        "query": query,
        "mode": "ArtList",
        "maxrecords": 75,
        "format": "json",
        "sort": "DateDesc",
    })
    payload = fetch_json(f"{GDELT_ENDPOINT}?{params}")
    return payload.get("articles") or []


def make_signature(actor, title, event_type):
    # Deliberately omit publisher/date: recaps of the same pressure statement should not alert again.
    normalized = re.sub(r"[^a-z0-9가-힣]+", " ", clean(title).lower())
    normalized = re.sub(r"\b(?:today|yesterday|wednesday|thursday|friday|monday|tuesday|sunday|saturday)\b", " ", normalized)
    normalized = re.sub(r"\s+", " ", normalized).strip()
    raw = f"{actor}|{event_type}|{normalized[:260]}"
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def korean_event(article, actor, event_type, source_label, body):
    title = clean(article.get("title"))
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
            "이는 법안의 현재 매출 효과보다 통과 확률과 시간표를 바꾸는 정치적 변수입니다."
        )
    else:
        detail = (
            f"{actor or '미국 고위 정책 당사자'}가 CLARITY 법안의 통과·절차 진행을 공개적으로 압박한 새 발언이 신뢰 매체에서 확인됐습니다. "
            "실제 표결이나 법률 효력 발생은 아니지만, 행정부가 입법 우선순위를 재확인했다는 점에서 상원 표결 시간표와 협상 압력에 영향을 줄 수 있습니다."
        )
    if "national security" in body.lower():
        detail += " 특히 디지털자산 오용 대응을 국가안보 수단과 연결해 법안 처리 필요성을 강조했습니다."

    seen = parse_seen_date(article.get("seendate"))
    date = seen.astimezone(ZoneInfo("America/New_York")).strftime("%a, %d %b %Y %H:%M:%S %z") if seen else ""
    url = clean(article.get("url"))
    return {
        "source": f"{source_label} 정책 발언 검증",
        "event_type": event_type,
        "title": ko_title,
        "url": url,
        "date": date,
        "detail": detail,
        "policy_actor": actor,
        "reported_title": title,
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
    freshness_cutoff = now - dt.timedelta(days=4)
    raw = []
    errors = []
    for query in QUERIES:
        try:
            raw.extend(gdelt_articles(query))
        except Exception as exc:
            errors.append(f"{query}: {exc}")

    # URL-level dedupe first.
    by_url = {}
    for article in raw:
        url = clean(article.get("url"))
        if url:
            by_url[url] = article

    candidates = []
    for article in by_url.values():
        url = clean(article.get("url"))
        tier, source_label = domain_label(url)
        if tier == 0:
            continue
        seen = parse_seen_date(article.get("seendate"))
        if seen is None or seen < freshness_cutoff or seen > now + dt.timedelta(hours=2):
            continue

        title = clean(article.get("title"))
        actor = extract_actor(title)
        if not actor:
            continue
        body, final_url = article_body(url)
        article["url"] = final_url or url
        signal = clean(f"{title} {body}")
        if not STRICT_TOPIC_RE.search(signal) or not ACTION_RE.search(signal):
            continue

        event_type = "정치·윤리 표결 변수" if RISK_RE.search(signal) else "행정부·핵심 당사자 통과 촉구"
        candidates.append({
            "article": article,
            "actor": actor,
            "event_type": event_type,
            "tier": tier,
            "source_label": source_label,
            "signal": signal,
        })

    # Tier 1: one fresh direct report is sufficient. Tier 2: require two independent accepted publishers
    # for the same actor/event type within the freshness window. Discovery-only sources never trigger alone.
    accepted = []
    groups = {}
    for item in candidates:
        groups.setdefault((item["actor"], item["event_type"]), []).append(item)
    for group_items in groups.values():
        tier1 = [x for x in group_items if x["tier"] == 1]
        if tier1:
            accepted.append(sorted(tier1, key=lambda x: parse_seen_date(x["article"].get("seendate")) or dt.datetime.min.replace(tzinfo=ZoneInfo("UTC")), reverse=True)[0])
            continue
        corroborating = [x for x in group_items if x["tier"] == 2]
        publishers = {x["source_label"] for x in corroborating}
        if len(publishers) >= 2:
            accepted.append(sorted(corroborating, key=lambda x: parse_seen_date(x["article"].get("seendate")) or dt.datetime.min.replace(tzinfo=ZoneInfo("UTC")), reverse=True)[0])

    state = load_state()
    baseline = not bool(state.get("initialized"))
    seen_keys = set(state.get("seen_signatures") or [])
    current_signatures = []
    new_events = []
    for item in accepted:
        article = item["article"]
        sig = make_signature(item["actor"], article.get("title", ""), item["event_type"])
        current_signatures.append(sig)
        if baseline or sig in seen_keys:
            continue
        new_events.append(korean_event(article, item["actor"], item["event_type"], item["source_label"], item["signal"]))

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
        "raw_articles": len(by_url),
        "accepted_current": len(accepted),
        "new_events": len(new_events),
        "errors": errors,
    }, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"clarity_policy_pressure_new={len(new_events)} baseline={str(baseline).lower()} accepted={len(accepted)}")


if __name__ == "__main__":
    main()
