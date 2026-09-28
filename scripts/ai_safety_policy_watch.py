#!/usr/bin/env python3
"""Low-noise AI safety standards / cyber-security industry policy watcher.

Purpose:
- Keep incident/vulnerability alerts separate from policy/commercialization.
- Alert only on concrete changes: standards, regulation, mandatory reporting,
  budget/GPU support, evaluation gates, pilots, procurement, paid contracts,
  consortium changes.
- Prefer official sources; permit high-quality reporting as secondary evidence.
- Cluster duplicate coverage into one compact Telegram event.
"""
from __future__ import annotations

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
from collections import defaultdict
from zoneinfo import ZoneInfo

KST = ZoneInfo("Asia/Seoul")
UTC = dt.timezone.utc
ROOT = pathlib.Path(__file__).resolve().parents[1]
DATA = ROOT / "data"
OUT = ROOT / "out"
DATA.mkdir(exist_ok=True)
OUT.mkdir(exist_ok=True)

STATE_PATH = DATA / "ai_safety_policy_watch_state.json"
PENDING_PATH = OUT / "ai_safety_policy_watch_pending_state.json"
ALERT_TITLE = OUT / "ai_safety_policy_watch_alert_title.txt"
ALERT_BODY = OUT / "ai_safety_policy_watch_alert.html"
STATUS_PATH = OUT / "ai_safety_policy_watch_status.md"
CONFIRMED_PATH = OUT / "ai_safety_policy_watch_telegram_confirmed.json"

GOOGLE_NEWS = "https://news.google.com/rss/search"
USER_AGENT = "Mozilla/5.0 khs-ai-safety-policy-watch/1.0"
MAX_AGE_HOURS = 168
SEEN_RETENTION_DAYS = 90
MAX_ALERT_EVENTS = 5

NEWS_QUERIES = [
    # International standards / mandatory requirements.
    'OpenAI AI safety standard recursive self-improvement incident reporting capability regulation',
    '"AI Safety Institute" standard evaluation incident reporting frontier model',
    'NAAIMES AI measurement evaluation standard safety institute',
    'NIST frontier AI safety standard evaluation cybersecurity model',
    'EU AI frontier model safety standard incident reporting',
    # Korea: official project / procurement / commercialization.
    '"사이버보안 특화 AI" 네이버클라우드 과기정통부 NIPA',
    '"특화 인공지능 파운데이션 모델" 사이버 보안 B200',
    '"AI 보안모델" 조달 실증 수주 계약',
    '네이버클라우드 S2W 샌즈랩 LG CNS 사이버보안 AI 계약 실증',
    '"AI 안전연구소" 한국 국제 표준 평가',
    # English company / paid-contract paths.
    '(NAVER Cloud OR S2W OR SandLab OR "LG CNS") cybersecurity AI contract pilot procurement',
    'AI cybersecurity foundation model government procurement pilot contract Korea',
    '(Palo Alto Networks OR CrowdStrike OR IBM OR Microsoft OR NVIDIA) AI cybersecurity product launch ARR contract customer',
    '("Unit 42" OR "Frontier AI Defense" OR SafeMind OR "AI Runtime Firewall") cybersecurity customer contract subscription',
    '(Palo Alto Networks OR CrowdStrike) AI security ARR annual recurring revenue bookings guidance',
    '(IBM OR Microsoft) AI cybersecurity autonomous SOC paid contract government procurement',
    '(NVIDIA OR BlueField OR Nemotron) cybersecurity inference always-on 24/7 SOC security agent',
    'AI security agent autonomous SOC continuous monitoring subscription revenue customer',
    'NVIDIA "Open Agent Safety Platform" OpenShell Sentry partner enterprise pricing',
    '(NVIDIA OpenShell OR "agent safety runtime") enterprise customer deployment contract subscription',
    '(NVIDIA OpenShell OR NemoClaw) Microsoft SAP Canonical Red Hat integration partner customer',
    '(OpenShell OR "Open Agent Safety Platform") AI Enterprise pricing license support cloud service',
    '(OpenShell OR "agent safety runtime") telemetry active sandboxes enterprise adoption',
]

OFFICIAL_SOURCE_HINTS = (
    "openai", "nipa", "과학기술정보통신부", "msit", "kisa", "한국인터넷진흥원",
    "nists", "nist", "cisa", "gov.uk", "aisi", "european commission",
    "europa.eu", "oecd", "white house", "commerce department", "ntia",
    "naver", "lg cns", "s2w", "샌즈랩", "palo alto", "unit 42",
    "crowdstrike", "ibm", "nvidia", "microsoft", "openshell",
    "nemoclaw", "sentry", "sap", "canonical", "red hat",
)

TRUSTED_SOURCE_HINTS = (
    "reuters", "axios", "the information", "yonhap", "연합뉴스", "financial times", "bloomberg",
    "the information", "zdnet", "전자신문", "etnews", "파이낸셜뉴스",
    "매일경제", "한국경제", "머니투데이", "이데일리", "조선비즈",
    "서울경제", "디지털데일리", "디지털타임스", "the verge",
    "techcrunch", "wired", "securityweek", "palo alto", "unit 42",
    "crowdstrike", "ibm", "nvidia", "microsoft",
)

AI_TOPIC_TERMS = (
    "ai safety", "artificial intelligence", "frontier model", "frontier ai",
    "recursive self-improvement", "rsi", "cybersecurity ai", "ai cybersecurity",
    "ai security", "foundation model", "preparedness framework", "model evaluation",
    "인공지능", "ai", "사이버보안", "보안 ai", "파운데이션 모델", "안전연구소",
)

ACTION_TERMS = (
    # Standards / regulation / reporting.
    "standard", "standards", "adopt", "adopts", "adopted", "mandatory",
    "regulation", "regulatory", "law", "legislation", "bill", "requirement",
    "incident reporting", "reporting requirement", "audit", "auditor",
    "evaluation standard", "benchmark", "framework", "threshold",
    "guidance", "guideline", "memorandum", "agreement",
    # Funding / procurement / pilots / contracts.
    "budget", "funding", "gpu", "b200", "h200", "grant", "support",
    "procurement", "tender", "contract", "award", "selected", "selection",
    "pilot", "deployment", "demonstration", "commercialization", "paid",
    "revenue", "arr", "annual recurring revenue", "bookings", "subscription",
    "customer", "customers", "order", "consortium", "partner", "partnership",
    "license", "licensing", "pricing", "paid support", "enterprise support",
    "active sandbox", "active sandboxes", "telemetry", "deployment", "deployments",
    "product launch", "launched", "always-on", "continuous", "24/7", "soc",
    "autonomous security", "security agent", "runtime firewall", "bluefield", "nemotron",
    # Korean.
    "표준", "의무", "규제", "법안", "법률", "사고보고", "감사", "인증",
    "평가", "벤치마크", "프레임워크", "예산", "지원", "gpu", "선정",
    "중간평가", "실증", "조달", "입찰", "수주", "계약", "상용화",
    "유료", "매출", "반복매출", "구독", "고객", "라이선스", "가격",
    "유료 지원", "기업 지원", "배포", "활성 샌드박스", "텔레메트리",
    "제품 출시", "출시", "상시", "24시간", "보안관제", "자율형 보안", "컨소시엄", "참여사", "협력", "협약",
)

LOW_VALUE_SPEECH_TERMS = (
    "urges", "calls for", "says", "remarks", "speech", "interview",
    "강조", "촉구", "발언", "인터뷰", "기조연설",
)

CONCRETE_ACTION_TERMS = (
    "adopted", "published", "issued", "signed", "enacted", "approved",
    "launched", "awarded", "selected", "contract", "procurement", "tender",
    "budget", "funding", "b200", "h200", "pilot", "deployment",
    "launched", "product launch", "arr", "annual recurring revenue", "bookings",
    "subscription", "customer", "paid", "revenue", "license", "pricing",
    "paid support", "enterprise support", "deployment",
    "표준 제정", "공고", "선정", "계약", "수주", "조달", "입찰",
    "예산", "지원", "실증", "착수", "중간평가", "상용화",
)

CATEGORY_PATTERNS = [
    ("에이전트 안전 런타임·신뢰 플랫폼", (
        "open agent safety platform", "openshell", "nemoclaw", "agent safety runtime",
        "secure agent runtime", "sentry", "ai enterprise", "paid support",
        "enterprise support", "pricing", "license", "active sandbox",
        "활성 샌드박스", "유료 지원", "라이선스", "가격",
    )),
    ("국제 안전표준·평가", (
        "standard", "standards", "evaluation", "benchmark", "framework",
        "threshold", "ai safety institute", "naaimes", "평가", "표준",
        "벤치마크", "안전연구소",
    )),
    ("법규·의무 보고·감사", (
        "mandatory", "regulation", "law", "legislation", "bill",
        "incident reporting", "audit", "auditor", "requirement",
        "의무", "규제", "법안", "법률", "사고보고", "감사", "인증",
    )),
    ("예산·GPU·국책사업", (
        "budget", "funding", "gpu", "b200", "h200", "grant", "support",
        "예산", "지원", "국책", "gpu", "b200", "h200",
    )),
    ("실증·중간평가·조달", (
        "pilot", "deployment", "demonstration", "procurement", "tender",
        "award", "selected", "selection", "실증", "중간평가", "조달",
        "입찰", "선정", "착수",
    )),
    ("AI 보안 제품·ARR·유료계약", (
        "product launch", "launched", "frontier ai defense", "safemind",
        "ai runtime firewall", "contract", "paid", "revenue", "arr",
        "annual recurring revenue", "bookings", "subscription", "customer",
        "order", "commercialization", "제품 출시", "출시", "수주", "계약",
        "유료", "매출", "반복매출", "구독", "고객", "상용화",
    )),
    ("24시간 보안추론·SOC 자동화", (
        "always-on", "continuous", "24/7", "soc", "autonomous security",
        "security agent", "runtime firewall", "bluefield", "nemotron",
        "상시", "24시간", "보안관제", "자율형 보안",
    )),
    ("컨소시엄·참여사 변경", (
        "consortium", "partner", "partnership", "member", "participating",
        "컨소시엄", "참여사", "협력", "협약",
    )),
]

WATCH_ENTITIES = (
    "openai", "anthropic", "google", "meta", "microsoft", "nvidia",
    "palo alto", "unit 42", "crowdstrike", "ibm", "openshell",
    "nemoclaw", "sentry", "sap", "canonical", "red hat",
    "naver", "네이버클라우드", "lg cns", "lg ai", "s2w", "샌즈랩",
    "과학기술정보통신부", "nipa", "kisa", "ai safety institute",
    "naaimes", "nist",
)

KNOWN_OFFICIAL_PAGES = {
    "NIPA 사이버보안 특화 AI 사업": "https://nipa.kr/home/bsnsAll/00/detail?bsnsDtlsIemNo=909",
}


def fetch_bytes(url: str, timeout: int = 25) -> bytes:
    req = urllib.request.Request(
        url,
        headers={
            "User-Agent": USER_AGENT,
            "Accept": "application/rss+xml,application/xml,text/html,application/json,*/*",
        },
    )
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return resp.read()


def strip_html(value: str) -> str:
    value = html.unescape(re.sub(r"<[^>]+>", " ", value or ""))
    return " ".join(value.replace("\xa0", " ").split())


def parse_pubdate(value: str | None) -> dt.datetime | None:
    if not value:
        return None
    try:
        parsed = email.utils.parsedate_to_datetime(value)
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=UTC)
        return parsed.astimezone(UTC)
    except Exception:
        return None


def google_news_url(query: str) -> str:
    return GOOGLE_NEWS + "?" + urllib.parse.urlencode({
        "q": query,
        "hl": "ko",
        "gl": "KR",
        "ceid": "KR:ko",
    })


def parse_google_news(query: str, now: dt.datetime) -> list[dict]:
    root = ET.fromstring(fetch_bytes(google_news_url(query)))
    out = []
    for node in root.findall(".//item"):
        title = strip_html(node.findtext("title") or "")
        desc = strip_html(node.findtext("description") or "")
        link = (node.findtext("link") or "").strip()
        source_node = node.find("source")
        source = strip_html(source_node.text if source_node is not None and source_node.text else "")
        published = parse_pubdate(node.findtext("pubDate"))
        if not title or not link:
            continue
        if published and now - published > dt.timedelta(hours=MAX_AGE_HOURS):
            continue
        out.append({
            "kind": "news",
            "query": query,
            "title": title,
            "description": desc,
            "source": source or "Google News",
            "url": link,
            "published_at": published.isoformat() if published else None,
        })
    return out


def official_page_snapshots() -> dict[str, dict]:
    out = {}
    for name, url in KNOWN_OFFICIAL_PAGES.items():
        raw = fetch_bytes(url).decode("utf-8", "ignore")
        text = strip_html(raw)
        # Limit noise from volatile layout but retain policy numbers/terms.
        material = " ".join(re.findall(
            r".{0,70}(?:B200|H200|256장|32노드|2026|2027|10개월|사업예산|추진일정|중간평가|GPU).{0,120}",
            text,
            flags=re.I,
        ))
        if not material:
            material = text[:12000]
        out[name] = {
            "url": url,
            "digest": hashlib.sha256(material.encode("utf-8")).hexdigest(),
            "material": material[:1800],
        }
    return out


def source_official(source: str) -> bool:
    low = source.lower()
    return any(x in low for x in OFFICIAL_SOURCE_HINTS)


def source_trusted(source: str) -> bool:
    low = source.lower()
    return source_official(source) or any(x in low for x in TRUSTED_SOURCE_HINTS)


def detect_category(text: str) -> str:
    low = text.lower()
    scores = []
    for label, patterns in CATEGORY_PATTERNS:
        score = sum(1 for p in patterns if p in low)
        if score:
            scores.append((score, label))
    if not scores:
        return "정책·사업화 변화"
    scores.sort(reverse=True)
    return scores[0][1]


def detect_entity(text: str) -> str:
    low = text.lower()
    mapping = (
        ("네이버클라우드", ("네이버클라우드", "naver cloud")),
        ("OpenAI", ("openai",)),
        ("NIPA", ("nipa", "정보통신산업진흥원")),
        ("과학기술정보통신부", ("과학기술정보통신부", "과기정통부", "msit")),
        ("S2W", ("s2w",)),
        ("샌즈랩", ("샌즈랩", "sandlab")),
        ("LG CNS", ("lg cns",)),
        ("LG AI연구원", ("lg ai", "exaone")),
        ("NAAIMES", ("naaimes",)),
        ("AI 안전연구소 네트워크", ("ai safety institute", "안전연구소")),
        ("NIST", ("nist",)),
        ("NVIDIA OpenShell", ("openshell", "open agent safety platform", "nemoclaw")),
        ("Sentry", ("sentry",)),
        ("SAP", ("sap",)),
        ("Canonical", ("canonical", "ubuntu")),
        ("Red Hat", ("red hat",)),
        ("Palo Alto Networks", ("palo alto", "unit 42", "frontier ai defense")),
        ("CrowdStrike", ("crowdstrike", "safemind")),
        ("IBM", ("ibm", "autonomous security")),
        ("NVIDIA", ("nvidia", "bluefield", "nemotron", "ai runtime firewall")),
        ("Anthropic", ("anthropic",)),
        ("Google", ("google",)),
        ("Meta", ("meta",)),
        ("Microsoft", ("microsoft",)),
    )
    for label, patterns in mapping:
        if any(p in low for p in patterns):
            return label
    return "AI 안전·보안 생태계"


def material(item: dict) -> bool:
    combined = f" {item.get('title','')} {item.get('description','')} "
    low = combined.lower()
    if not any(x in low for x in AI_TOPIC_TERMS):
        return False
    if not any(x in low for x in ACTION_TERMS):
        return False
    if not source_trusted(item.get("source", "")):
        return False

    # Generic speeches are excluded unless accompanied by an actual policy,
    # standard, budget, procurement, selection, deployment, or contract change.
    if any(x in low for x in LOW_VALUE_SPEECH_TERMS):
        if not any(x in low for x in CONCRETE_ACTION_TERMS):
            return False

    # Require either a watched entity or a concrete government/standards term.
    if not any(x in low for x in WATCH_ENTITIES):
        if not any(x in low for x in (
            "government", "ministry", "standard", "regulation", "procurement",
            "정부", "과제", "국책", "조달", "표준", "규제",
        )):
            return False
    return True


def fingerprint(item: dict) -> str:
    raw = "|".join([item.get("url",""), item.get("title",""), item.get("source","")])
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:24]


def token_set(text: str) -> set[str]:
    words = re.findall(r"[a-z0-9가-힣][a-z0-9가-힣+._-]{2,}", text.lower())
    stop = {
        "the","and","for","with","from","that","this","new","says","said",
        "ai","인공지능","관련","대한","통해","위한","사업","정부",
    }
    return {w for w in words if w not in stop}


def similarity(a: str, b: str) -> float:
    aa, bb = token_set(a), token_set(b)
    if not aa or not bb:
        return 0.0
    return len(aa & bb) / len(aa | bb)


def normalize(item: dict) -> dict:
    combined = f"{item.get('title','')} {item.get('description','')}"
    out = dict(item)
    out["fingerprint"] = fingerprint(item)
    out["category"] = detect_category(combined)
    out["entity"] = detect_entity(combined)
    out["official"] = source_official(item.get("source",""))
    return out


def load_state() -> dict:
    if not STATE_PATH.exists():
        return {"initialized": False, "seen": {}, "official_pages": {}}
    try:
        obj = json.loads(STATE_PATH.read_text(encoding="utf-8"))
        obj.setdefault("initialized", False)
        obj.setdefault("seen", {})
        obj.setdefault("official_pages", {})
        return obj
    except Exception:
        return {"initialized": False, "seen": {}, "official_pages": {}}


def save_json(path: pathlib.Path, value: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def previously_similar(item: dict, seen: dict) -> bool:
    for old in seen.values():
        if old.get("entity") != item.get("entity"):
            continue
        if old.get("category") != item.get("category"):
            continue
        if similarity(item.get("title",""), old.get("title","")) >= 0.45:
            return True
    return False


def cluster_events(items: list[dict]) -> list[list[dict]]:
    clusters: list[list[dict]] = []
    for item in sorted(items, key=lambda x: (bool(x.get("official")), x.get("published_at") or ""), reverse=True):
        placed = False
        for cluster in clusters:
            rep = cluster[0]
            if rep.get("entity") == item.get("entity") and rep.get("category") == item.get("category"):
                if similarity(rep.get("title",""), item.get("title","")) >= 0.18:
                    cluster.append(item)
                    placed = True
                    break
        if not placed:
            clusters.append([item])
    return clusters[:MAX_ALERT_EVENTS]


def source_label(source: str) -> str:
    low = source.lower()
    mapping = (
        ("reuters","Reuters"), ("연합뉴스","연합뉴스"), ("yonhap","연합뉴스"),
        ("openai","OpenAI"), ("nipa","NIPA"), ("과학기술정보통신부","과기정통부"),
        ("naver","NAVER"), ("s2w","S2W"), ("lg cns","LG CNS"),
        ("zdnet","ZDNet"), ("전자신문","전자신문"), ("etnews","전자신문"),
        ("파이낸셜뉴스","파이낸셜뉴스"), ("한국경제","한국경제"),
        ("매일경제","매일경제"), ("이데일리","이데일리"),
    )
    for needle, label in mapping:
        if needle in low:
            return label
    return re.sub(r"^www\.", "", source)[:24] or "원문"


def concise_fact(item: dict) -> str:
    title = re.sub(r"\s+-\s+[^-]{1,40}$", "", item.get("title","")).strip()
    if len(title) > 105:
        title = title[:104].rstrip() + "…"
    return title


def build_alert(events: list[list[dict]], now: dt.datetime) -> tuple[str,str]:
    title = f"📌 <b>AI 안전표준·보안산업 정책 Watch</b> · 중요 변화 {len(events)}건"
    lines = [f"<i>{now.astimezone(KST).strftime('%m/%d %H:%M KST')}</i>"]
    for idx, cluster in enumerate(events, 1):
        rep = cluster[0]
        lines += [
            "",
            f"<b>{idx}. {html.escape(rep['entity'])} · {html.escape(rep['category'])}</b>",
            f"• {html.escape(concise_fact(rep))}",
        ]
        if rep["category"] == "에이전트 안전 런타임·신뢰 플랫폼":
            lines.append("• <b>의미</b>: OpenShell·Open Agent Safety Platform이 기업 표준 런타임으로 채택되고 유료 지원·GPU/AI Enterprise 매출로 연결되는지 확인")
        elif rep["category"] in ("AI 보안 제품·ARR·유료계약","24시간 보안추론·SOC 자동화"):
            lines.append("• <b>의미</b>: 제품 출시가 ARR·유료고객·반복 추론매출로 실제 연결되는지 확인")
        elif rep["category"] in ("예산·GPU·국책사업","실증·중간평가·조달"):
            lines.append("• <b>의미</b>: 실제 자금·현장 적용·매출 연결 여부를 우선 확인")
        else:
            lines.append("• <b>의미</b>: 안전 요구가 자율 권고에서 공통 기준·의무 기준으로 이동하는지 확인")

        sources = []
        official = False
        for item in cluster:
            label = source_label(item.get("source",""))
            if label not in [x[0] for x in sources]:
                sources.append((label,item.get("url","")))
            official = official or bool(item.get("official"))
        level = "공식 원천 포함" if official else (f"복수 출처 {len(sources)}곳" if len(sources)>=2 else "신뢰보도 1건")
        lines.append(f"• <b>확인</b>: {html.escape(level)}")
        links = [
            f'<a href="{html.escape(url,quote=True)}">{html.escape(label)}</a>'
            for label,url in sources[:4] if url
        ]
        if links:
            lines.append("🔗 " + " · ".join(links))
    lines += ["", "<b>다음 확인</b>: OpenShell 파트너/지원범위 · 가격/라이선스 · 활성 배포 · 유료지원/계약 · GPU/AI Enterprise 매출 연결 · ARR/조달"]
    return title, "\n".join(lines)


def prune_seen(seen: dict, now: dt.datetime) -> dict:
    cutoff = now - dt.timedelta(days=SEEN_RETENTION_DAYS)
    out = {}
    for k,v in seen.items():
        stamp = v.get("first_seen_at") or v.get("published_at")
        try:
            when = dt.datetime.fromisoformat(str(stamp).replace("Z","+00:00")).astimezone(UTC)
        except Exception:
            when = now
        if when >= cutoff:
            out[k] = v
    return out


def main() -> int:
    for p in (ALERT_TITLE, ALERT_BODY, CONFIRMED_PATH):
        p.unlink(missing_ok=True)

    now = dt.datetime.now(UTC)
    state = load_state()
    raw: list[dict] = []
    errors: list[str] = []

    for query in NEWS_QUERIES:
        try:
            raw.extend(parse_google_news(query, now))
        except Exception as exc:
            errors.append(f"Google News 실패: {query[:55]} / {type(exc).__name__}: {exc}")

    normalized = {}
    for row in raw:
        item = normalize(row)
        if material(item):
            normalized[item["fingerprint"]] = item
    current = list(normalized.values())

    seen = prune_seen(dict(state.get("seen") or {}), now)
    new_items = []
    for item in current:
        if item["fingerprint"] in seen or previously_similar(item, seen):
            continue
        new_items.append(item)

    # Track direct official page changes separately.
    official_pages = dict(state.get("official_pages") or {})
    try:
        snapshots = official_page_snapshots()
        for name,snap in snapshots.items():
            previous = official_pages.get(name)
            if previous and previous.get("digest") != snap["digest"]:
                new_items.append(normalize({
                    "kind":"official",
                    "query":"official page change",
                    "title":f"{name} 공식 사업페이지 변경 감지",
                    "description":snap.get("material",""),
                    "source":"NIPA",
                    "url":snap["url"],
                    "published_at":now.isoformat(),
                }))
            official_pages[name] = {
                "digest":snap["digest"],
                "updated_at":now.isoformat(),
                "url":snap["url"],
            }
    except Exception as exc:
        errors.append(f"공식 사업페이지 감시 실패: {type(exc).__name__}: {exc}")

    baseline = not bool(state.get("initialized"))
    if baseline:
        new_items = []

    first_seen = now.isoformat()
    for item in current:
        seen.setdefault(item["fingerprint"], {
            "title":item["title"], "source":item["source"], "url":item["url"],
            "entity":item["entity"], "category":item["category"],
            "published_at":item.get("published_at"), "first_seen_at":first_seen,
        })

    events = cluster_events(new_items)
    pending = {
        "initialized": True,
        "updated_at_kst": now.astimezone(KST).isoformat(timespec="seconds"),
        "seen": seen,
        "official_pages": official_pages,
        "last_collection": {
            "raw_items":len(raw),
            "material_items":len(current),
            "new_articles":len(new_items),
            "new_events":len(events),
            "errors":errors,
        },
    }
    save_json(PENDING_PATH, pending)

    if events:
        title,body = build_alert(events,now)
        ALERT_TITLE.write_text(title+"\n",encoding="utf-8")
        ALERT_BODY.write_text(body.rstrip()+"\n",encoding="utf-8")

    status = [
        "# AI 안전표준·보안산업 정책 Watch",
        "",
        f"- 조회시각: {now.astimezone(KST).strftime('%Y-%m-%d %H:%M:%S KST')}",
        f"- 최초 기준선: {'예' if baseline else '아니오'}",
        f"- 웹 수집: {len(raw)}건",
        f"- 중요 필터 통과: {len(current)}건",
        f"- 신규 중요 사건: {len(events)}건",
        f"- 오류: {len(errors)}건",
    ]
    if errors:
        status += ["", "## 오류"] + [f"- {x}" for x in errors[:10]]
    STATUS_PATH.write_text("\n".join(status)+"\n",encoding="utf-8")
    print(
        f"ai_policy_baseline={str(baseline).lower()} material={len(current)} "
        f"new_articles={len(new_items)} new_events={len(events)} errors={len(errors)}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
