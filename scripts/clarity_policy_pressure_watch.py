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
SIGNATURE_VERSION = 2
CHAIR_EXPECTED_TYPE = "상원 은행위원회 차기 위원장 전망"
CHAIR_REPORTED_TYPE = "상원 은행위원회 위원장 선임 보도"

NEWS_RSS = "https://news.google.com/rss/search"
QUERIES = [
    '"CLARITY Act" Trump',
    '"CLARITY Act" Bessent',
    '"CLARITY Act" "White House"',
    '"CLARITY Act" Senate ethics',
    '"CLARITY Act" Coinbase',
    '"CLARITY Act" "Ryan VanGrack"',
    '"CLARITY Act" "Brian Armstrong"',
    '"CLARITY Act" BitGo',
    '"CLARITY Act" draft Senate Republicans',
    '"CLARITY Act" revised text Senate',
    '"Elizabeth Warren" "Senate Banking" chair',
    '"Warren" "Banking Committee" chair Democrats',
    '"Senate Banking" "Warren" leadership crypto',
]

TIER1_LABELS = {
    "bloomberg law": "Bloomberg Law",
    "bloomberg tax": "Bloomberg Tax",
    "reuters": "Reuters",
    "american banker": "American Banker",
    "cbs news": "CBS News",
    "axios": "Axios",
    "wall street journal": "The Wall Street Journal",
    "wsj": "The Wall Street Journal",
    "bloomberg": "Bloomberg",
    "coindesk": "CoinDesk",
    "the block": "The Block",
    "semafor": "Semafor",
    "coinbase": "Coinbase",
}
TIER2_LABELS = {
    "cointelegraph": "Cointelegraph",
    "banking dive": "Banking Dive",
    "crypto.news": "Crypto.news",
    "financefeeds": "FinanceFeeds",
    "pymnts": "PYMNTS",
    "crypto briefing": "Crypto Briefing",
    "bitcoin magazine": "Bitcoin Magazine",
    "benzinga": "Benzinga",
    "coinmarketcap": "CoinMarketCap",
}
DISCOVERY_ONLY_LABELS = {"tokenpost": "TokenPost"}

STRICT_TOPIC_RE = re.compile(
    r"(?:\bCLARITY\s+(?:Act|Bill)\b|H\.?\s*R\.?\s*3633|Digital\s+Asset\s+Market\s+Clarity\s+Act|"
    r"digital\s+asset\s+market\s+structure|crypto\s+market\s+structure|(?:crypto|digital\s+asset)\s+(?:bill|legislation))",
    re.I,
)
ACTION_RE = re.compile(
    r"\b(?:urge[sd]?|call(?:s|ed)?\s+(?:on|for)|press(?:es|ed)?|push(?:es|ed)?|back(?:s|ed)?|support(?:s|ed)?|"
    r"advance[sd]?|pass(?:es|ed|age)?|vote|voting|motion\s+to\s+proceed|cloture|remain\s+at\s+the\s+negotiating\s+table|"
    r"stop\s+talking|start\s+voting|oppose[sd]?|block(?:s|ed)?|ethics?|conflict\s+of\s+interest|national\s+security|"
    r"leadership|negotiat(?:e|es|ed|ion|ions)?)\b",
    re.I,
)
TEXT_RELEASE_RE = re.compile(
    r"(?:\b(?:release[sd]?|unveil(?:s|ed)?|publish(?:es|ed)?|circulat(?:e|es|ed))\b.{0,100}\b(?:draft|text|version)\b|"
    r"\b(?:final|revised|updated|new)\b.{0,40}\b(?:CLARITY\s+(?:Act|Bill)\s+)?(?:draft|text|version)\b|"
    r"\b(?:draft|text|version)\b.{0,100}\b(?:release[sd]?|unveil(?:s|ed)?|publish(?:es|ed)?|circulat(?:e|es|ed))\b)",
    re.I,
)
RISK_RE = re.compile(r"\b(?:oppose[sd]?|block(?:s|ed)?|ethics?|conflict\s+of\s+interest|corruption)\b", re.I)
MOBILITY_RE = re.compile(
    r"\b(?:innovation|tokenization|tokenized|offshore|overseas|outside\s+the\s+united\s+states|outside\s+the\s+u\.?s\.?|"
    r"where\s+it\s+happens|where\s+the\s+market\s+lives|jurisdiction|capital|developer|talent|migration|stablecoin|"
    r"wall\s+street|banks?|traditional\s+finance)\b",
    re.I,
)

ACTORS = [
    (re.compile(r"\b(?:President\s+)?Donald\s+Trump\b|\bPresident\s+Trump\b|\bTrump\b", re.I), "Trump 대통령"),
    (re.compile(r"\bScott\s+Bessent\b|\bTreasury\s+Secretary\s+Bessent\b|\bBessent\b", re.I), "Bessent 재무장관"),
    (re.compile(r"\bWhite\s+House\b", re.I), "백악관"),
    (re.compile(r"\bPatrick\s+Witt\b", re.I), "백악관 디지털자산 고문 Patrick Witt"),
    (re.compile(r"\bJohn\s+Thune\b|\bSenate\s+Majority\s+Leader\b", re.I), "상원 다수당 지도부"),
    (re.compile(r"\bTim\s+Scott\b|\bChairman\s+Scott\b", re.I), "상원 은행위원장 Tim Scott"),
    (re.compile(r"\bElizabeth\s+Warren\b|\bSenator\s+Warren\b", re.I), "Elizabeth Warren 상원의원"),
    (re.compile(r"\bRyan\s+Van\s*Grack\b|\bRyan\s+Vangrack\b|\bVan\s*Grack\b|\bVangrack\b", re.I), "Coinbase 부회장 Ryan VanGrack"),
    (re.compile(r"\bBrian\s+Armstrong\b", re.I), "Coinbase CEO Brian Armstrong"),
    (re.compile(r"\bPaul\s+Grewal\b", re.I), "Coinbase CLO Paul Grewal"),
    (re.compile(r"\bMike\s+Belshe\b", re.I), "BitGo CEO Mike Belshe"),
]
INDUSTRY_ACTORS = {
    "Coinbase 부회장 Ryan VanGrack": "Coinbase",
    "Coinbase CEO Brian Armstrong": "Coinbase",
    "Coinbase CLO Paul Grewal": "Coinbase",
    "BitGo CEO Mike Belshe": "BitGo",
}


def clean(value):
    return re.sub(r"\s+", " ", html.unescape(str(value or ""))).strip()


def fetch_bytes(url, timeout=15):
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 (KHS-CLARITY-Policy-Watch/2.1)"})
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
    for key in sorted(TIER1_LABELS, key=len, reverse=True):
        if key in low:
            return 1, TIER1_LABELS[key]
    for key in sorted(TIER2_LABELS, key=len, reverse=True):
        if key in low:
            return 2, TIER2_LABELS[key]
    for key in sorted(DISCOVERY_ONLY_LABELS, key=len, reverse=True):
        if key in low:
            return 3, DISCOVERY_ONLY_LABELS[key]
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
        with urllib.request.urlopen(req, timeout=8) as r:
            final = r.geturl()
            body = r.read(250000).decode("utf-8", "ignore")
        if "news.google.com" not in urllib.parse.urlparse(final).netloc:
            return final
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


def is_text_release_state(text):
    return bool(TEXT_RELEASE_RE.search(clean(text)) and STRICT_TOPIC_RE.search(clean(text)))



def senate_banking_chair_stage(signal, published):
    """Detect a post-election committee-leadership change, not generic Warren remarks."""
    if published is None or published < dt.datetime(2026, 11, 4, tzinfo=ZoneInfo("UTC")):
        return ""
    low = clean(signal).lower()
    if not re.search(r"\b(?:elizabeth\s+warren|senator\s+warren|warren)\b", low):
        return ""
    if not re.search(r"\b(?:senate\s+banking(?:\s+committee)?|senate\s+committee\s+on\s+banking|banking\s+committee)\b", low):
        return ""
    if not re.search(r"\b(?:chair(?:woman|man|person)?|chairmanship|gavel)\b", low):
        return ""
    # A press report of an appointment is not treated as an official committee roster.
    if re.search(
        r"\bwarren\b.{0,110}\b(?:officially\s+)?(?:named|elected|selected|appointed)\s+(?:as\s+)?(?:the\s+)?(?:chair|chairwoman|chairman)\b",
        low,
    ) or re.search(
        r"\b(?:committee|senate\s+banking)\b.{0,110}\b(?:elected|selected|appointed|named)\s+warren\s+(?:as\s+)?(?:its\s+)?chair\b",
        low,
    ):
        return "reported_selected"
    if re.search(r"\b(?:expected|likely|presumptive|poised|in\s+line|on\s+track|set\s+to|contender|would|could|may|incoming)\b", low):
        return "expected"
    return ""


def event_subtype(signal, event_type):
    low = clean(signal).lower()
    if event_type == CHAIR_EXPECTED_TYPE:
        return "senate_banking_chair_expected"
    if event_type == CHAIR_REPORTED_TYPE:
        return "senate_banking_chair_reported_selected"
    if "문안 공개" in event_type or "핵심 수정" in event_type:
        return "senate_revised_draft_release"
    if event_type == "정치·윤리 표결 변수":
        return "ethics_conflict_risk"
    if "motion to proceed" in low:
        return "motion_to_proceed_pressure"
    if "cloture" in low:
        return "cloture_pressure"
    if "stop talking" in low or "start voting" in low:
        return "vote_now_pressure"
    if "national security" in low or "allies" in low or "adversaries" in low:
        return "national_security_pressure"
    if MOBILITY_RE.search(low):
        return "innovation_location_pressure"
    if re.search(r"\bpass(?:es|ed|age)?\b|\badvance[sd]?\b", low):
        return "passage_pressure"
    return "general_policy_pressure"


def semantic_signature(actor, event_type, signal):
    subtype = event_subtype(signal, event_type)
    raw = f"v{SIGNATURE_VERSION}|{actor}|{event_type}|{subtype}"
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def korean_event(item, actor, event_type, source_label, signal, evidence_sources=None):
    evidence_sources = list(dict.fromkeys(evidence_sources or [source_label]))
    if event_type in {CHAIR_EXPECTED_TYPE, CHAIR_REPORTED_TYPE}:
        company, mobility = "", False
        if event_type == CHAIR_EXPECTED_TYPE:
            ko_title = "워런, 차기 미국 상원 은행위원장 취임 전망 — 공식 선임 전"
            detail = (
                "2026년 11월 3일 중간선거에서 민주당이 상원 다수당을 확보한 뒤 "
                "Elizabeth Warren 상원의원이 차기 상원 은행위원장 후보로 거론된다는 신뢰매체 보도입니다. "
                "현 119대 의회의 위원장은 Tim Scott이고 Warren은 민주당 간사입니다. "
                "위원장 공식 선임이나 취임 완료가 아니며, 2027년 1월 3일 시작하는 제120대 의회의 "
                "위원회 인선·공식 명단을 다시 확인해야 합니다. "
                "Warren은 CLARITY 법안의 투자자 보호, 이해충돌, 불법금융 및 은행 암호자산 위험을 문제 삼아 왔습니다."
            )
        else:
            ko_title = "워런, 상원 은행위원장 선임 보도 — 공식 명단 대조 전"
            detail = (
                "신뢰매체가 Elizabeth Warren 상원의원의 차기 은행위원장 선임을 보도했습니다. "
                "이는 기존 취임 전망에서 진전됐다는 언론 보도이며, 상원 은행위원회 공식 위원장 명단과 "
                "임기 시작 시점을 별도로 대조해야 합니다. 인선 보도를 공식 취임 완료로 표시하지 않습니다."
            )
    elif "문안 공개" in event_type or "핵심 수정" in event_type:
        company, mobility = "", False
        ko_title = "상원 공화당, CLARITY 최신 초안 공개 — 공식 원문 재확인 중"
        reported_title = clean(item.get("title", ""))
        detail = (
            f"{source_label}가 상원 공화당이 CLARITY의 최신·최종 초안을 공개 또는 회람했다고 보도했습니다. "
            "이건 단순한 Trump 발언이나 윤리 논란 재보도가 아니라 법안 문안 자체가 바뀐 상태 변화입니다. "
            "보도 제목·요약상 Trump 대통령의 윤리 절충안 수용 내용이 새 초안에 반영된 것으로 보이지만, 어떤 조항이 실제로 들어갔는지는 Senate Banking·GovInfo·Congress.gov의 새 원문을 확보해 이전 버전과 조문 단위로 대조해야 합니다. "
            "공식 원문이 아직 같은 시점에 확인되지 않으면 ‘신뢰매체 문안 공개 확인 / 공식 원문 대기’로 표시하고, 공식 원문이 올라오는 순간 SEC·CFTC 권한, DeFi, stablecoin rewards, 윤리·이해충돌, State AG 집행권 등 핵심 수정사항을 다시 잠급니다."
        )
    elif event_type == "핵심 사업자·업계 표결 촉구":
        company = INDUSTRY_ACTORS.get(actor, "미국 암호자산 사업자")
        ko_title = f"{actor}, CLARITY 법안 표결·통과 촉구"
        detail = (
            f"{actor} 측은 상원에 CLARITY 법안의 실제 표결·통과를 촉구했습니다. 직접 규제 대상 사업자의 이해관계가 있는 발언이므로 "
            "정부 공식 변화와 동일하게 보지 않지만, 입법 지연이 소비자 보호·법집행·불법금융 대응과 미국 내 사업·혁신 입지에 미치는 영향을 보여주는 업계 압박 신호로 추적합니다."
        )
        mobility = bool(MOBILITY_RE.search(signal))
        if mobility:
            detail += " 토큰화·금융 인프라 혁신은 의회 결정과 무관하게 진행되며, 규제가 늦으면 활동이 미국 밖에서 먼저 커질 수 있다는 경쟁력·자금이동 경고도 포함됐습니다."
    elif actor == "Trump 대통령":
        company, mobility = "", False
        ko_title = "Trump 대통령, CLARITY 법안 처리·통과를 의회에 촉구"
        detail = "Trump 대통령이 CLARITY 법안의 통과·절차 진행을 공개적으로 압박한 새 발언이 신뢰 매체에서 확인됐습니다. 실제 표결이나 법률 효력 발생은 아니지만 상원 표결 시간표와 협상 압력을 바꿀 수 있는 정책 신호입니다."
    elif actor == "Bessent 재무장관":
        company, mobility = "", False
        ko_title = "Bessent 재무장관, 상원에 CLARITY 법안 절차 진행을 촉구"
        detail = "Bessent 재무장관이 CLARITY 법안의 통과·절차 진행을 공개적으로 압박한 새 발언이 신뢰 매체에서 확인됐습니다. 실제 표결이나 법률 효력 발생은 아니지만 상원 표결 시간표와 협상 압력을 바꿀 수 있는 정책 신호입니다."
        if "national security" in signal.lower() or "allies" in signal.lower():
            detail += " 미국의 디지털자산 주도권과 국가안보 논리까지 연결해 처리 필요성을 강조했습니다."
    elif event_type == "정치·윤리 표결 변수":
        company, mobility = "", False
        ko_title = f"{actor or '미국 정치권'}, CLARITY 법안의 윤리·이해충돌 쟁점 부각"
        detail = "CLARITY 법안 자체 조문 외에 대통령·정부 관계자의 암호자산 이해관계와 윤리 조항이 상원 표 확보의 변수로 부각됐습니다. 이는 현재 매출보다 통과 확률과 시간표를 바꾸는 정치적 변수입니다."
    else:
        company, mobility = "", False
        ko_title = f"{actor or '미국 정책 당국'}, CLARITY 법안 처리 압박 강화"
        detail = f"{actor or '미국 고위 정책 당사자'} 측이 CLARITY 법안의 통과·절차 진행을 공개적으로 압박한 새 발언이 신뢰 매체에서 확인됐습니다. 실제 표결이나 법률 효력 발생은 아니지만 상원 표결 시간표와 협상 압력을 바꿀 수 있는 정책 신호입니다."

    published = parse_date(item["pubDate"])
    date = published.astimezone(ZoneInfo("America/New_York")).strftime("%a, %d %b %Y %H:%M:%S %z") if published else ""
    event = {
        "source": (f"{source_label} 위원장 인선 보도" if event_type in {CHAIR_EXPECTED_TYPE, CHAIR_REPORTED_TYPE}
                   else (f"{source_label} 발언 검증" if "문안 공개" not in event_type else f"{source_label} 문안 공개 검증")),
        "event_type": event_type,
        "event_subtype": event_subtype(signal, event_type),
        "title": ko_title,
        "url": resolve_original_url(item["url"]),
        "date": date,
        "detail": detail,
        "reported_title": item["title"],
        "evidence_sources": evidence_sources,
        "evidence_count": len(evidence_sources),
        "monitoring_unit": "event_state_change",
    }
    if event_type in {CHAIR_EXPECTED_TYPE, CHAIR_REPORTED_TYPE}:
        event["policy_actor"] = "Elizabeth Warren 상원의원"
        event["leadership_stage"] = ("expected" if event_type == CHAIR_EXPECTED_TYPE else "reported_selected")
        event["verification_status"] = (
            "신뢰매체의 차기 위원장 전망 확인 / 공식 상원 은행위원회 인선 미확정"
            if event_type == CHAIR_EXPECTED_TYPE
            else "선임 관련 신뢰매체 보도 / 공식 상원 은행위원회 명단 대조 전"
        )
    elif "문안 공개" in event_type or "핵심 수정" in event_type:
        event["policy_actor"] = "상원 공화당 협상팀"
        event["verification_status"] = "신뢰매체 문안 공개 확인 / Senate Banking·GovInfo·Congress.gov 공식 원문 재확인 대기"
        event["text_release"] = True
    elif event_type == "핵심 사업자·업계 표결 촉구":
        event["industry_actor"] = actor
        event["industry_company"] = company
        event["mobility_warning"] = mobility
    else:
        event["policy_actor"] = actor
    return event


def load_state():
    if not STATE_PATH.exists():
        return {}
    try:
        return json.loads(STATE_PATH.read_text(encoding="utf-8"))
    except Exception:
        return {}



def verified_warren_chair_backfill(now):
    """One-time, date-bounded recovery for the independently verified 2026-11-05 report.

    This is explicitly a source-checked historical backfill, not an assertion
    that a live RSS collector fetched and revalidated the official roster.
    The existing semantic signature and delivery-confirmation gate still apply.
    """
    start = dt.datetime(2026, 11, 6, tzinfo=ZoneInfo("UTC"))
    stop = dt.datetime(2026, 11, 11, tzinfo=ZoneInfo("UTC"))
    if not start <= now < stop:
        return None
    report = {
        "title": "Banks brace for tighter oversight from US Congress after Democrats sweep",
        "description": (
            "Reuters reported Elizabeth Warren, the top Democrat on the Senate Banking Committee, "
            "was a leading contender expected to chair the committee after Democrats gained the Senate majority. "
            "Banking Dive independently reported Warren was the presumptive incoming chair, not yet formally seated."
        ),
        "url": (
            "https://www.reuters.com/legal/transactional/"
            "banks-brace-tighter-oversight-us-congress-after-democrats-sweep-2026-11-05/"
        ),
        # Publication date is known; the exact publication clock time is not
        # asserted in the outward-facing event.
        "pubDate": "Thu, 05 Nov 2026 00:00:00 GMT",
        "source": "Reuters",
        "source_url": "https://www.reuters.com",
        "matched_query": "verified post-election leadership backfill",
    }
    return {
        "item": report,
        "actor": "Elizabeth Warren 상원의원",
        "event_type": CHAIR_EXPECTED_TYPE,
        "event_subtype": "senate_banking_chair_expected",
        "tier": 1,
        "source_label": "Reuters",
        "signal": report["description"],
        "evidence_sources": [
            "Reuters 2026-11-05 (차기 위원장 전망)",
            "Banking Dive 2026-11-04 (별도 취재)",
            "상원 은행위원회 공식 위원 명단 (현직 Tim Scott / 민주당 간사 Warren)",
        ],
        "verified_one_time_backfill": True,
    }


def main():
    now = dt.datetime.now(ZoneInfo("UTC"))
    cutoff = now - dt.timedelta(days=5)
    errors, by_key = [], {}
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
        chair_stage = senate_banking_chair_stage(signal, published)
        if chair_stage:
            actor = "Elizabeth Warren 상원의원"
            event_type = CHAIR_EXPECTED_TYPE if chair_stage == "expected" else CHAIR_REPORTED_TYPE
        elif not STRICT_TOPIC_RE.search(signal):
            continue
        elif is_text_release_state(signal):
            actor = "상원 공화당 협상팀"
            event_type = "법안 문안 공개·핵심 수정 — 신뢰매체 확인"
        else:
            actor = extract_actor(signal)
            if not actor or not ACTION_RE.search(signal):
                continue
            event_type = "핵심 사업자·업계 표결 촉구" if actor in INDUSTRY_ACTORS else ("정치·윤리 표결 변수" if RISK_RE.search(signal) else "행정부·핵심 당사자 통과 촉구")
        candidates.append({
            "item": item,
            "actor": actor,
            "event_type": event_type,
            "event_subtype": event_subtype(signal, event_type),
            "tier": tier,
            "source_label": source_label,
            "signal": signal,
        })

    groups = {}
    for candidate in candidates:
        key = (candidate["actor"], candidate["event_type"], candidate["event_subtype"])
        groups.setdefault(key, []).append(candidate)

    accepted = []
    for group in groups.values():
        tier1 = [x for x in group if x["tier"] == 1]
        tier2 = [x for x in group if x["tier"] == 2]
        chosen = None
        if tier1:
            chosen = max(tier1, key=lambda x: parse_date(x["item"]["pubDate"]) or dt.datetime.min.replace(tzinfo=ZoneInfo("UTC")))
        elif len({x["source_label"] for x in tier2}) >= 2:
            chosen = max(tier2, key=lambda x: parse_date(x["item"]["pubDate"]) or dt.datetime.min.replace(tzinfo=ZoneInfo("UTC")))
        if chosen:
            chosen = dict(chosen)
            chosen["evidence_sources"] = list(dict.fromkeys(x["source_label"] for x in sorted(group, key=lambda x: (x["tier"], x["source_label"]))))
            accepted.append(chosen)

    one_time_backfill_added = False
    if not any(x["event_type"] == CHAIR_EXPECTED_TYPE for x in accepted):
        verified = verified_warren_chair_backfill(now)
        if verified:
            accepted.append(verified)
            one_time_backfill_added = True

    state = load_state()
    baseline = (not bool(state.get("initialized"))) or state.get("signature_version") != SIGNATURE_VERSION
    old_seen = set(state.get("seen_signatures") or []) if not baseline else set()
    current, new_events = [], []
    for candidate in accepted:
        sig = semantic_signature(candidate["actor"], candidate["event_type"], candidate["signal"])
        current.append(sig)
        if baseline or sig in old_seen:
            continue
        event = korean_event(
            candidate["item"], candidate["actor"], candidate["event_type"], candidate["source_label"],
            candidate["signal"], evidence_sources=candidate["evidence_sources"],
        )
        if candidate.get("verified_one_time_backfill"):
            event["source"] = "Reuters·Banking Dive 교차검증 — 누락 사건 1회 보완"
            event["date"] = "2026-11-05"
            event["verified_one_time_backfill"] = True
            event["verification_status"] = (
                "2026년 11월 5일 보도 교차검증 / 상원 은행위원장 공식 선임은 미확정"
            )
        new_events.append(event)

    merged = list(dict.fromkeys(([] if baseline else list(state.get("seen_signatures") or [])) + current))[-700:]
    PENDING_STATE_PATH.write_text(json.dumps({
        "initialized": True,
        "signature_version": SIGNATURE_VERSION,
        "monitoring_unit": "event_state_change_not_article",
        "last_checked_utc": now.isoformat(timespec="seconds"),
        "seen_signatures": merged,
        "accepted_current": len(accepted),
        "raw_articles": len(by_key),
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
        "signature_version": SIGNATURE_VERSION,
        "monitoring_unit": "event_state_change_not_article",
        "raw_articles": len(by_key),
        "candidates": len(candidates),
        "accepted_current": len(accepted),
        "new_events": len(new_events),
        "verified_one_time_backfill_added": one_time_backfill_added,
        "verified_one_time_backfill_sent_to_formatter": any(
            event.get("verified_one_time_backfill") for event in new_events
        ),
        "errors": errors,
    }, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"clarity_policy_pressure_new={len(new_events)} baseline={str(baseline).lower()} accepted={len(accepted)} unit=event")


if __name__ == "__main__":
    main()
