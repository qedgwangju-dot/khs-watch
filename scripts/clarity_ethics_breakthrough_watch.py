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
STATE_PATH = ROOT / "data" / "clarity_ethics_breakthrough_state.json"
PENDING_STATE_PATH = ROOT / "out" / "clarity_ethics_breakthrough_pending_state.json"
STATUS_PATH = ROOT / "out" / "clarity_ethics_breakthrough_status.json"
ALERT_JSON = ROOT / "out" / "clarity_watch_alert.json"
SIGNATURE_VERSION = 2

NEWS_RSS = "https://news.google.com/rss/search"
AP_DIRECT_URL = "https://apnews.com/article/521fd5986eb107413064018f7a468c51"
QUERIES = [
    '"CLARITY Act" Trump ethics',
    '"CLARITY Act" Tillis Gallego ethics',
    '"Trump agrees" crypto bill ethics',
    '"Trump accepts" crypto bill ethics',
    '"new bipartisan ethics provision" crypto bill Trump',
]

TIER1 = {
    "associated press": "Associated Press",
    "ap news": "Associated Press",
    "reuters": "Reuters",
    "bloomberg law": "Bloomberg Law",
    "bloomberg": "Bloomberg",
    "coindesk": "CoinDesk",
    "the block": "The Block",
    "semafor": "Semafor",
}
TIER2 = {
    "benzinga": "Benzinga",
    "cointelegraph": "Cointelegraph",
    "crypto briefing": "Crypto Briefing",
}

AGREEMENT_RE = re.compile(r"\b(?:agree(?:s|d)?|accept(?:s|ed)?|approve(?:s|d)?|sign(?:s|ed)?\s+off|backs?)\b", re.I)
ETHICS_RE = re.compile(r"\b(?:ethics?|conflict(?:s)?\s+of\s+interest|Tillis|Gallego)\b", re.I)
CRYPTO_BILL_RE = re.compile(
    r"(?:\bCLARITY\s+(?:Act|Bill)\b|H\.?\s*R\.?\s*3633|Digital\s+Asset\s+Market\s+Clarity|"
    r"\bcrypto(?:currency)?\s+(?:bill|legislation)|digital\s+asset\s+market\s+structure)", re.I,
)
TRUMP_RE = re.compile(r"\b(?:President\s+)?Donald\s+Trump\b|\bPresident\s+Trump\b|\bTrump\b", re.I)


def clean(value):
    return re.sub(r"\s+", " ", html.unescape(str(value or ""))).strip()


def fetch_bytes(url, timeout=15):
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 (KHS-CLARITY-Ethics-Watch/2.0)"})
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


def google_news_items(query):
    params = urllib.parse.urlencode({"q": query, "hl": "en-US", "gl": "US", "ceid": "US:en"})
    root = ET.fromstring(fetch_bytes(f"{NEWS_RSS}?{params}"))
    rows = []
    for item in root.findall(".//item")[:60]:
        source_node = item.find("source")
        rows.append({
            "title": clean(item.findtext("title")),
            "description": clean(item.findtext("description")),
            "url": clean(item.findtext("link")),
            "pubDate": clean(item.findtext("pubDate")),
            "source": clean(source_node.text if source_node is not None else ""),
            "matched_query": query,
            "seeded": False,
        })
    return rows


def current_ap_backfill(now):
    if now.date() > dt.date(2026, 9, 17):
        return []
    return [{
        "title": "Trump agrees to new bipartisan ethics provision in massive crypto bill, GOP aide says",
        "description": (
            "CLARITY Act ethics compromise negotiated by Sens. Thom Tillis and Ruben Gallego. "
            "A senior GOP aide says Trump accepted about 80% of the proposal, including state attorneys general enforcement."
        ),
        "url": AP_DIRECT_URL,
        "pubDate": "Mon, 14 Sep 2026 00:00:00 GMT",
        "source": "Associated Press",
        "matched_query": '"CLARITY Act" Trump ethics',
        "seeded": True,
    }]


def source_tier(label):
    low = clean(label).lower()
    for key in sorted(TIER1, key=len, reverse=True):
        if key in low:
            return 1, TIER1[key]
    for key in sorted(TIER2, key=len, reverse=True):
        if key in low:
            return 2, TIER2[key]
    return 0, clean(label)


def is_ethics_breakthrough(text):
    text = clean(text)
    return bool(TRUMP_RE.search(text) and ETHICS_RE.search(text) and AGREEMENT_RE.search(text) and CRYPTO_BILL_RE.search(text))


def semantic_signature():
    raw = f"v{SIGNATURE_VERSION}|trump|tillis-gallego|ethics-compromise|substantial-acceptance"
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def kst_label(pub_date):
    parsed = parse_date(pub_date)
    if not parsed:
        return ""
    kst = parsed.astimezone(ZoneInfo("Asia/Seoul"))
    return f"{kst.year}년 {kst.month}월 {kst.day}일 {kst:%H:%M} KST"


def event_from(item, source_label, evidence_sources=None):
    evidence_sources = list(dict.fromkeys(evidence_sources or [source_label]))
    reported = "" if item.get("seeded") else kst_label(item.get("pubDate", ""))
    title_lower = clean(item.get("title", "")).lower()
    ap_specific = source_label == "Associated Press" or "new bipartisan ethics provision" in title_lower
    if ap_specific:
        detail = (
            "Associated Press가 고위 공화당 보좌관을 인용해 Trump 대통령이 Tillis–Gallego 양당 윤리 절충안의 약 80%를 수용했다고 보도했습니다. "
            "수용 범위에는 그동안 백악관이 반대해온 주 검찰총장(state attorneys general)의 집행 권한도 포함된 것으로 전해졌습니다. "
            "AP에 따르면 공개 예정인 개정안은 고위 공직자가 암호자산 발행 기업에 보유한 중대한 이해관계를 매각하거나 독립적인 블라인드 트러스트에 두도록 하고, "
            "주 검찰총장이 법안 규정을 위반한 암호화폐 거래소를 상대로 소송할 수 있도록 하는 내용을 포함할 예정입니다. "
            "다만 백악관의 공개 확인은 아직 없고 개정 법안 원문도 아직 공개 전이므로, 현재 단계는 ‘핵심 협상 진전’이지 최종 조항 확정은 아닙니다."
        )
        url = AP_DIRECT_URL
    else:
        detail = (
            "Trump 대통령이 Tillis–Gallego 양당 윤리 절충안의 핵심 내용을 수용했다는 신뢰 매체 보도가 확인됐습니다. "
            "윤리 조항은 CLARITY 법안의 60표 확보를 가로막던 핵심 쟁점이었기 때문에 시간표와 통과 가능성을 재평가할 만한 변화입니다. "
            "다만 공개된 상원 개정 법안 원문으로 조항을 다시 확인하기 전까지는 최종 합의로 단정하지 않습니다."
        )
        url = clean(item.get("url", ""))
    if reported:
        detail = f"보도 시각(한국시간): {reported}. " + detail
    return {
        "source": f"{source_label} 윤리합의 검증",
        "event_type": "행정부·핵심 당사자 통과 촉구 — 윤리 합의 진전",
        "event_subtype": "tillis_gallego_ethics_compromise",
        "title": "Trump 대통령, Tillis–Gallego 윤리안 핵심 조항 수용 — 공식 문안 확인 대기",
        "url": url,
        "date": "",
        "detail": detail,
        "policy_actor": "Trump 대통령",
        "verification_status": "보좌관·신뢰매체 확인 / 백악관 공개 확인 및 개정 원문 대기",
        "reported_title": clean(item.get("title", "")),
        "evidence_sources": evidence_sources,
        "evidence_count": len(evidence_sources),
        "monitoring_unit": "event_state_change",
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
    cutoff = now - dt.timedelta(days=3)
    errors, by_key = [], {}
    for query in QUERIES:
        try:
            for item in google_news_items(query):
                key = (item["title"], item["source"], item["pubDate"])
                by_key.setdefault(key, item)
        except Exception as exc:
            errors.append(f"{query}: {exc}")
    for item in current_ap_backfill(now):
        key = (item["title"], item["source"], item["pubDate"])
        by_key.setdefault(key, item)

    candidates = []
    for item in by_key.values():
        published = parse_date(item.get("pubDate", ""))
        if published is None or published < cutoff or published > now + dt.timedelta(hours=2):
            continue
        tier, source_label = source_tier(item.get("source", ""))
        if tier == 0:
            continue
        signal = clean(f"{item.get('title','')} {item.get('description','')} {item.get('matched_query','')}")
        if is_ethics_breakthrough(signal):
            candidates.append({"item": item, "tier": tier, "source_label": source_label})

    accepted = []
    if candidates:
        tier1 = [row for row in candidates if row["tier"] == 1]
        tier2 = [row for row in candidates if row["tier"] == 2]
        chosen = None
        if tier1:
            chosen = max(tier1, key=lambda row: parse_date(row["item"].get("pubDate", "")) or cutoff)
        elif len({row["source_label"] for row in tier2}) >= 2:
            chosen = max(tier2, key=lambda row: parse_date(row["item"].get("pubDate", "")) or cutoff)
        if chosen:
            chosen = dict(chosen)
            chosen["evidence_sources"] = list(dict.fromkeys(row["source_label"] for row in sorted(candidates, key=lambda row: (row["tier"], row["source_label"]))))
            accepted.append(chosen)

    state = load_state()
    baseline = (not bool(state.get("initialized"))) or state.get("signature_version") != SIGNATURE_VERSION
    seen = set(state.get("seen_signatures") or []) if not baseline else set()
    current, new_events = [], []
    for row in accepted:
        sig = semantic_signature()
        current.append(sig)
        if baseline or sig in seen:
            continue
        new_events.append(event_from(row["item"], row["source_label"], evidence_sources=row["evidence_sources"]))

    merged = list(dict.fromkeys(([] if baseline else list(state.get("seen_signatures") or [])) + current))[-200:]
    pending = {
        "initialized": True,
        "signature_version": SIGNATURE_VERSION,
        "monitoring_unit": "event_state_change_not_article",
        "last_checked_utc": now.isoformat(timespec="seconds"),
        "seen_signatures": merged,
        "accepted_current": len(accepted),
        "raw_articles": len(by_key),
        "source_errors": errors,
    }
    PENDING_STATE_PATH.parent.mkdir(parents=True, exist_ok=True)
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
        "signature_version": SIGNATURE_VERSION,
        "monitoring_unit": "event_state_change_not_article",
        "raw_articles": len(by_key),
        "candidates": len(candidates),
        "accepted_current": len(accepted),
        "new_events": len(new_events),
        "errors": errors,
    }, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"clarity_ethics_breakthrough_new={len(new_events)} baseline={str(baseline).lower()} accepted={len(accepted)} unit=event")


if __name__ == "__main__":
    main()
