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
OFFICIAL_SNAPSHOT_SCHEMA_VERSION = 3
OFFICIAL_CHANGE_CONFIRM_RUNS = 2
OFFICIAL_CHANGE_CONFIRM_SECONDS = 600

# Published government/reference documents are immutable baselines. Their
# rendered HTML may vary due to rotating related-content/navigation blocks, but
# those presentation changes must never generate a policy alert. Follow-up
# policy changes are discovered as new official documents/news items instead.
IMMUTABLE_OFFICIAL_REFERENCE_PAGES = {
    "미 하원의장실 White House Accord 공식 발표",
    "백악관 Super Intelligence 행정명령",
    "백악관 Super Intelligence 팩트시트",
    "Anthropic Cyber Mission 공식 출범",
}

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
    'NVIDIA Sentry standalone SKU pricing license subscription BlueField-4',
    '"BlueField-4" Sentry attach rate shipments units revenue contribution',
    '(OpenShell OR Sentry) default integration bundled "AI Enterprise" Microsoft SAP Red Hat Canonical',
    '"BlueField-4" Sentry Arm Intel x86 server deployment non-NVIDIA',
    '"hardware isolation" AI agents procurement insurance regulation DPU BlueField',
    '("Open Agent Safety Platform" OR OpenShell OR Sentry) partner customer production deployment contract paid',
    '("BlueField-4" OR Sentry) Rubin included baseline incremental deployment x86 Arm customer',
    '(OpenAI OR Anthropic OR Google OR Meta) "Safety Case" training approval gate senior leadership veto',
    '(OpenAI OR Anthropic OR Google OR Meta) frontier AI independent audit external evaluator safety case',
    '(OpenAI OR Anthropic OR Google OR Meta) safety case procurement insurance certification requirement',
    '(OpenAI OR Anthropic OR Google OR Meta) safety case adopted implementation frontier training',
    'government procurement insurance "Safety Case" frontier AI training',
    '"Joint Commitment on Frontier Responsibilities" AI',
    '"White House Accord on Super Intelligence" AI',
    '"Frontier Responsibilities" Google Anthropic Meta OpenAI xAI NVIDIA',
    '"morally binding" AI accord signatory auditor board committee',
    '"AI accord" signatory added withdrew external auditor board oversight',
    '"frontier AI" common standards best practices external audit board committee',
    '"AI safety" independent board committee external audit requirement',
    '"AI accord" codified law regulation procurement insurance certification',
    '"super intelligence" accord law regulation audit procurement insurance',
    'site:whitehouse.gov "Super Intelligence" safety regulation accord',
    'site:federalregister.gov "Super Intelligence" executive order regulation',
    'site:congress.gov "Super Intelligence" AI safety bill',
    '(Anthropic "Cyber Mission" OR "Critical Infrastructure Defense Program" OR "OSS Scanner") (partners OR deployments OR customers OR scanner OR funding)',
    '"Thomas Lind" OpenAI ONCD cyber strategic risk',
    '"Dean Ball" OpenAI OSTP Strategic Futures AI Action Plan',
    '(OpenAI OR Anthropic OR Google DeepMind OR xAI OR Meta) (ONCD OR OSTP OR NSA OR NSC OR Pentagon) (hire OR hired OR joins OR joined OR appoint OR appointed) "national security"',
    '(OpenAI OR Anthropic OR Google DeepMind OR xAI OR Meta) former White House cyber AI policy official national security hire',
]

OFFICIAL_SOURCE_HINTS = (
    "openai", "anthropic", "nipa", "과학기술정보통신부", "msit", "kisa", "한국인터넷진흥원",
    "nists", "nist", "cisa", "gov.uk", "aisi", "european commission",
    "europa.eu", "oecd", "white house", "whitehouse.gov", "commerce department", "ntia",
    "house.gov", "u.s. house", "house of representatives",
    "federalregister.gov", "federal register", "congress.gov", "congress",
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
    "associated press", "ap news", "guardian", "cbs news", "wall street journal", "wsj",
    "crowdstrike", "ibm", "nvidia", "microsoft",
)

AI_TOPIC_TERMS = (
    "ai safety", "artificial intelligence", "frontier model", "frontier ai",
    "recursive self-improvement", "rsi", "cybersecurity ai", "ai cybersecurity",
    "ai security", "foundation model", "preparedness framework", "model evaluation",
    "joint commitment on frontier responsibilities", "white house accord on super intelligence",
    "frontier responsibilities", "super intelligence", "superintelligence",
    "인공지능", "ai", "사이버보안", "보안 ai", "파운데이션 모델", "안전연구소",
    "프런티어 책임", "공동 서약", "공동 합의", "감독위원회",
    "anthropic cyber mission", "critical infrastructure defense program",
    "oss scanner", "사이버 방어 사업", "핵심 기반시설 방어",
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
    "license", "licensing", "pricing", "sku", "standalone", "bundle", "bundled",
    "paid support", "enterprise support", "attach rate", "shipment", "shipments",
    "unit", "units", "revenue contribution", "default integration", "default-on",
    "hardware isolation", "mandatory isolation", "insurance", "certification",
    "active sandbox", "active sandboxes", "telemetry", "sandboxes created",
    "sandbox creation failures", "actions denied", "network activity events",
    "provider profiles", "deployment", "deployments",
    "product launch", "launched", "always-on", "continuous", "24/7", "soc",
    "autonomous security", "security agent", "runtime firewall", "bluefield", "nemotron",
    "safety case", "training approval gate", "senior leadership veto",
    "independent review", "independent audit", "external evaluator",
    "external evaluation", "governance gate", "fail-closed", "fail closed",
    "joint commitment", "accord", "signatory", "signatories", "oversight board",
    "board committee", "independent board", "self-police", "self-regulation",
    "codify", "codified", "best practices", "common standards",
    "critical infrastructure defense program", "oss scanner", "cyber mission",
    "defense program", "security scanning",
    "hire", "hired", "joins", "joined", "appoint", "appointed",
    "national security policy", "strategic risk", "head of policy",
    "oncd", "office of the national cyber director", "ostp",
    "office of science and technology policy", "nsa", "national security agency",
    # Korean.
    "표준", "의무", "규제", "법안", "법률", "사고보고", "감사", "인증",
    "평가", "벤치마크", "프레임워크", "예산", "지원", "gpu", "선정",
    "중간평가", "실증", "조달", "입찰", "수주", "계약", "상용화",
    "유료", "매출", "반복매출", "구독", "고객", "라이선스", "가격",
    "단독 상품", "별도 판매", "번들", "기본 탑재", "장착률", "출하량",
    "수량", "매출 기여", "하드웨어 격리", "의무화", "보험", "인증",
    "유료 지원", "기업 지원", "배포", "활성 샌드박스", "텔레메트리",
    "제품 출시", "출시", "상시", "24시간", "보안관제", "자율형 보안", "컨소시엄", "참여사", "협력", "협약",
    "세이프티 케이스", "학습 승인", "학습 거부권", "독립 검토", "독립 감사",
    "외부 평가", "거버넌스 게이트", "조달 요건", "보험 요건",
    "공동 서약", "공동 합의", "서명 기업", "서명자", "감독위원회",
    "이사회 위원회", "독립 이사회", "공통 표준", "모범 사례", "성문화",
    "영입", "합류", "임명", "국가안보 정책", "전략적 리스크", "사이버 정책",
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
    "safety case", "training approval gate", "senior leadership veto",
    "independent review", "independent audit", "external evaluator",
    "procurement requirement", "insurance requirement", "certification requirement",
    "joint commitment", "accord", "signed", "signatory", "oversight board",
    "board committee", "independent board", "common standards", "best practices",
    "codified", "codify", "법제화", "성문화", "감독위원회", "이사회 위원회",
    "사이버 방어 사업", "오픈소스 보안", "취약점 검사", "핵심 기반시설",
    "hired", "joined", "appointed", "national security policy", "strategic risk",
    "영입", "합류", "임명", "국가안보 정책", "전략적 리스크",
    "표준 제정", "공고", "선정", "계약", "수주", "조달", "입찰",
    "예산", "지원", "실증", "착수", "중간평가", "상용화",
)

CATEGORY_PATTERNS = [
    ("Anthropic 핵심 기반시설·오픈소스 방어 사업", (
        "anthropic cyber mission", "critical infrastructure defense program",
        "cidp", "oss scanner", "핵심 기반시설 방어", "오픈소스 취약점 검사",
    )),
    ("프런티어 AI 국가안보·정책 핵심인사 이동", (
        "thomas lind", "dean ball",
        "office of the national cyber director", " oncd",
        "office of science and technology policy", " ostp",
        "national security policy", "cyber and strategic risk",
        "head of strategic futures", "former white house",
        "former nsa", "national security agency",
        "국가안보 정책", "전략적 리스크", "백악관 출신", "정부 인사 영입",
    )),
    ("백악관 Super Intelligence 정책·법제화", (
        "inaugurating the era of super intelligence",
        "super intelligence executive order",
        "federal definition", "legislative language",
        "행정명령", "연방 정의", "입법 문구",
    )),
    ("프런티어 AI 공동 서약·서명기업 변화", (
        "joint commitment on frontier responsibilities",
        "white house accord on super intelligence",
        "frontier responsibilities", "signatory", "signatories",
        "signed accord", "morally binding", "공동 서약", "공동 합의",
        "서명 기업", "서명자",
    )),
    ("공동 안전표준·모범사례", (
        "common standards", "safety standards", "best practices",
        "shared standards", "joint standards", "common framework",
        "공통 표준", "공동 표준", "모범 사례",
    )),
    ("외부감사 규격·감사기관", (
        "independent auditor", "external auditor", "external audit",
        "third-party auditor", "auditor qualification", "audit frequency",
        "audit scope", "auditor access", "감사기관", "외부 감사",
        "감사 주기", "감사 범위", "감사 자격",
    )),
    ("독립 이사회·감독위원회", (
        "oversight board", "board committee", "independent board",
        "independent committee", "oversight committee", "10-person oversight",
        "ten-member oversight", "감독위원회", "이사회 위원회", "독립 이사회",
    )),
    ("자율서약→법·조달·보험 성문화", (
        "codified into law", "codify into law", "codified", "legislation",
        "regulation", "procurement requirement", "insurance requirement",
        "certification requirement", "법제화", "성문화", "조달 요건",
        "보험 요건", "인증 요건",
    )),
    ("Safety Case 실제 학습 승인 게이트", (
        "safety case", "training approval gate", "governance gate",
        "senior leadership veto", "training veto", "fail-closed", "fail closed",
        "세이프티 케이스", "학습 승인", "학습 거부권",
    )),
    ("Safety Case 독립감사·외부평가", (
        "independent review", "independent audit", "external evaluator",
        "external evaluation", "third-party audit", "독립 검토", "독립 감사", "외부 평가",
    )),
    ("Safety Case 조달·보험·인증 편입", (
        "procurement requirement", "insurance requirement", "certification requirement",
        "government procurement", "regulated industry",
        "조달 요건", "보험 요건", "인증 요건", "공공 조달",
    )),
    ("Safety Case 업계 채택", (
        "adopted safety case", "safety case adopted", "implemented safety case",
        "safety case framework", "세이프티 케이스 도입", "세이프티 케이스 채택",
    )),
    ("파트너→유료고객·운영전환", (
        "production deployment", "production use", "paid customer", "customer deployment",
        "enterprise deployment", "contract", "purchase", "order", "rolled out",
        "in production", "유료 고객", "상용 배포", "운영 전환", "본계약", "발주",
    )),
    ("OpenShell 실사용·채택 지표", (
        "openshell telemetry", "sandboxes created", "sandbox creation failures",
        "actions denied", "network activity events", "provider profiles",
        "kubernetes", "docker", "policy decisions", "실사용 텔레메트리",
        "샌드박스 생성", "생성 실패율", "행동 차단",
    )),
    ("Sentry SKU·가격·라이선스", (
        "sentry", "sku", "standalone", "pricing", "license", "licensing",
        "subscription", "bundle", "bundled", "ai enterprise",
        "단독 상품", "별도 판매", "가격", "라이선스", "구독", "번들",
    )),
    ("BlueField 증분 장착·DPU 수익화", (
        "bluefield-4", "bluefield", "dpu", "attach rate", "shipment", "shipments",
        "unit", "units", "revenue contribution", "non-nvidia", "x86", "arm",
        "장착률", "출하량", "수량", "매출 기여",
    )),
    ("OpenShell 기본내장·지원 확대", (
        "openshell", "default integration", "default-on", "bundled",
        "supported agents", "full coverage", "partial coverage", "no coverage",
        "microsoft", "sap", "red hat", "canonical",
        "기본 내장", "기본 탑재", "지원 확대", "지원 에이전트",
    )),
    ("하드웨어 격리 의무·조달", (
        "hardware isolation", "mandatory isolation", "procurement requirement",
        "insurance", "certification", "regulated industry", "public sector",
        "하드웨어 격리", "의무화", "조달 요건", "보험", "인증",
    )),
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
    "openai", "anthropic", "google", "meta", "microsoft", "nvidia", "xai",
    "white house", "trump", "joint commitment on frontier responsibilities",
    "white house accord on super intelligence",
    "anthropic cyber mission", "critical infrastructure defense program",
    "oss scanner", "oncd", "office of the national cyber director", "ostp",
    "office of science and technology policy", "nsa", "national security agency",
    "thomas lind", "dean ball",
    "palo alto", "unit 42", "crowdstrike", "ibm", "openshell",
    "nemoclaw", "sentry", "sap", "canonical", "red hat",
    "naver", "네이버클라우드", "lg cns", "lg ai", "s2w", "샌즈랩",
    "과학기술정보통신부", "nipa", "kisa", "ai safety institute",
    "naaimes", "nist",
)

KNOWN_OFFICIAL_PAGES = {
    "미 하원의장실 White House Accord 공식 발표": "https://mikejohnson.house.gov/news/documentsingle.aspx?DocumentID=2939",
    "Anthropic Cyber Mission 공식 출범": "https://www.anthropic.com/news/anthropic-cyber-mission",
    "백악관 Super Intelligence 행정명령": "https://www.whitehouse.gov/presidential-actions/2026/09/inaugurating-the-era-of-super-intelligence/",
    "백악관 Super Intelligence 팩트시트": "https://www.whitehouse.gov/fact-sheets/2026/09/fact-sheet-president-donald-j-trump-inaugurates-the-era-of-super-intelligence/",
    "OpenAI 프런티어 학습 Safety Case": "https://openai.com/index/towards-safety-cases-for-frontier-ai-training/",
    "NIPA 사이버보안 특화 AI 사업": "https://nipa.kr/home/bsnsAll/00/detail?bsnsDtlsIemNo=909",
    "NVIDIA OpenShell 개요·지원": "https://raw.githubusercontent.com/NVIDIA/OpenShell/main/README.md",
    "NVIDIA OpenShell 지원정책": "https://raw.githubusercontent.com/NVIDIA/OpenShell/main/docs/about/support-matrix.mdx",
    "NVIDIA OpenShell 보안정책": "https://raw.githubusercontent.com/NVIDIA/OpenShell/main/SECURITY.md",
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
        try:
            raw = fetch_bytes(url).decode("utf-8", "ignore")
        except Exception as exc:
            # One vendor page can block automated access (for example HTTP 403).
            # Do not let that disable all of the other official-page checks.
            print(f"ai_policy_official_page_skip={name}: {type(exc).__name__}: {exc}")
            continue
        text = strip_html(raw)
        material = " ".join(re.findall(
            r".{0,70}(?:B200|H200|256장|32노드|2026|2027|10개월|사업예산|추진일정|중간평가|GPU|OpenShell|Sentry|BlueField-4|BlueField|pricing|price|license|subscription|AI Enterprise|partner|customer|supported agents|Full coverage|Partial coverage|No coverage|production use|security release|Codex|Claude Code|OpenCode|Safety Case|Super Intelligence|Joint Commitment|morally binding|signatory|common standards|best practices|oversight board|board committee|training approval|senior leadership|veto|independent review|audit|auditor|external evaluator|procurement|insurance|certification|codif|legislation|regulation|fail-closed).{0,140}",
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

def fetch_openshell_telemetry() -> dict:
    api = "https://api.github.com/repos/NVIDIA/OpenShell/contents/telemetry?ref=main"
    payload = json.loads(fetch_bytes(api).decode("utf-8"))
    reports = []
    for row in payload if isinstance(payload, list) else []:
        name = str(row.get("name") or "")
        if re.fullmatch(r"\d{4}-\d{2}-\d{2}\.md", name):
            reports.append(row)
    if not reports:
        raise RuntimeError("OpenShell telemetry reports not found")
    latest = sorted(reports, key=lambda x: x["name"])[-1]
    url = str(latest.get("download_url") or "")
    if not url:
        raise RuntimeError("OpenShell telemetry raw URL missing")
    body = fetch_bytes(url).decode("utf-8", "ignore")

    def metric(label: str) -> str | None:
        pat = r"\|\s*" + re.escape(label) + r"\s*\|\s*([\d,]+)\s*\|\s*([\d,]+)\s*\|\s*([+-]?[\d.]+%)\s*\|"
        m = re.search(pat, body, flags=re.I)
        return m.group(1) if m else None

    created = metric("Sandboxes created")
    failures = metric("Sandbox creation failures")
    denied = metric("Actions denied")
    network = metric("Network activity events")
    failure_rate = None
    if created and failures:
        try:
            failure_rate = 100.0 * int(failures.replace(",", "")) / int(created.replace(",", ""))
        except Exception:
            failure_rate = None

    driver = re.search(r"Kubernetes\s*\(([\d,]+)\).*?Docker\s*\(([\d,]+)\).*?Podman\s*(?:third at\s*)?\(([\d,]+)\)", body, flags=re.I | re.S)
    providers = re.search(r"\*\*Providers\.\*\*\s*(.+?)(?:\n\n|```)", body, flags=re.I | re.S)
    policy = re.search(r"Roughly\s*([\d.]+)%\s*of policy decisions were approved", body, flags=re.I)

    summary = []
    if created:
        summary.append(f"샌드박스 생성 {created}건")
    if failure_rate is not None:
        summary.append(f"생성 실패율 {failure_rate:.1f}%")
    if denied:
        summary.append(f"행동 차단 {denied}건")
    if network:
        summary.append(f"네트워크 이벤트 {network}건")

    details = []
    if driver:
        details.append(f"Kubernetes {driver.group(1)} / Docker {driver.group(2)} / Podman {driver.group(3)}")
    if providers:
        details.append("프로바이더: " + " ".join(providers.group(1).split())[:300])
    if policy:
        details.append(f"정책 승인율 약 {policy.group(1)}%")

    return {
        "name": latest["name"],
        "url": str(latest.get("html_url") or "https://github.com/NVIDIA/OpenShell/tree/main/telemetry"),
        "digest": hashlib.sha256(body.encode("utf-8")).hexdigest(),
        "title": " · ".join(summary) if summary else latest["name"],
        "detail": " | ".join(details),
    }

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
        ("백악관·프런티어 AI 공동서약", (
            "joint commitment on frontier responsibilities",
            "white house accord on super intelligence",
            "morally binding", "signed accord", "공동 서약", "공동 합의",
        )),
        ("OpenAI 국가안보 정책팀", (
            "thomas lind", "dean ball", "national security policy team",
            "cyber and strategic risk", "strategic futures",
        )),
        ("백악관 Super Intelligence 정책", (
            "super intelligence", "superintelligence", "white house", "백악관",
        )),
        ("네이버클라우드", ("네이버클라우드", "naver cloud")),
        ("OpenAI", ("openai",)),
        ("Anthropic", ("anthropic cyber mission", "anthropic", "oss scanner", "critical infrastructure defense program")),
        ("NIPA", ("nipa", "정보통신산업진흥원")),
        ("과학기술정보통신부", ("과학기술정보통신부", "과기정통부", "msit")),
        ("S2W", ("s2w",)),
        ("샌즈랩", ("샌즈랩", "sandlab")),
        ("LG CNS", ("lg cns",)),
        ("LG AI연구원", ("lg ai", "exaone")),
        ("NAAIMES", ("naaimes",)),
        ("AI 안전연구소 네트워크", ("ai safety institute", "안전연구소")),
        ("NIST", ("nist",)),
        ("NVIDIA Sentry/BlueField", ("bluefield-4", "bluefield", "nvidia sentry")),
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


def is_anthropic_mission_launch_baseline(item: dict) -> bool:
    url = (item.get("url") or "").lower()
    title = (item.get("title") or "").lower()
    return (
        "anthropic.com/news/anthropic-cyber-mission" in url
        or "introducing the anthropic cyber mission" in title
    )


def material(item: dict) -> bool:
    if is_anthropic_mission_launch_baseline(item):
        return False
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
        return {
            "initialized": False,
            "seen": {},
            "official_pages": {},
            "openshell_telemetry": {},
            "official_snapshot_schema_version": 0,
        }
    try:
        obj = json.loads(STATE_PATH.read_text(encoding="utf-8"))
        obj.setdefault("initialized", False)
        obj.setdefault("seen", {})
        obj.setdefault("official_pages", {})
        obj.setdefault("openshell_telemetry", {})
        obj.setdefault("official_snapshot_schema_version", 0)
        return obj
    except Exception:
        return {
            "initialized": False,
            "seen": {},
            "official_pages": {},
            "openshell_telemetry": {},
            "official_snapshot_schema_version": 0,
        }


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
        ("white house","백악관"), ("house of representatives","미 하원"),
        ("u.s. house","미 하원"), ("associated press","AP"), ("ap news","AP"),
        ("reuters","Reuters"), ("연합뉴스","연합뉴스"), ("yonhap","연합뉴스"),
        ("openai","OpenAI"), ("anthropic","Anthropic"), ("nvidia","NVIDIA"), ("nipa","NIPA"), ("과학기술정보통신부","과기정통부"),
        ("naver","NAVER"), ("s2w","S2W"), ("lg cns","LG CNS"),
        ("zdnet","ZDNet"), ("전자신문","전자신문"), ("etnews","전자신문"),
        ("파이낸셜뉴스","파이낸셜뉴스"), ("한국경제","한국경제"),
        ("매일경제","매일경제"), ("이데일리","이데일리"),
    )
    for needle, label in mapping:
        if needle in low:
            return label
    return re.sub(r"^www\.", "", source)[:24] or "원문"


def official_page_source(name: str) -> str:
    if name.startswith("Anthropic"):
        return "Anthropic"
    if name.startswith("NVIDIA"):
        return "NVIDIA"
    if name.startswith("NIPA"):
        return "NIPA"
    if name.startswith("OpenAI"):
        return "OpenAI"
    if name.startswith("백악관"):
        return "White House"
    if name.startswith("미 하원의장실"):
        return "U.S. House of Representatives"
    return "공식 원천"


def forced_official_page_category(name: str) -> str:
    mapping = {
        "Anthropic Cyber Mission 공식 출범": "Anthropic 핵심 기반시설·오픈소스 방어 사업",
        "미 하원의장실 White House Accord 공식 발표": "프런티어 AI 공동 서약·서명기업 변화",
        "백악관 Super Intelligence 행정명령": "백악관 Super Intelligence 정책·법제화",
        "백악관 Super Intelligence 팩트시트": "백악관 Super Intelligence 정책·법제화",
        "OpenAI 프런티어 학습 Safety Case": "Safety Case 실제 학습 승인 게이트",
        "NIPA 사이버보안 특화 AI 사업": "예산·GPU·국책사업",
        "NVIDIA OpenShell 개요·지원": "OpenShell 기본내장·지원 확대",
        "NVIDIA OpenShell 지원정책": "OpenShell 기본내장·지원 확대",
        "NVIDIA OpenShell 보안정책": "에이전트 안전 런타임·신뢰 플랫폼",
    }
    return mapping.get(name, "정책·사업화 변화")


def forced_official_page_entity(name: str) -> str:
    mapping = {
        "Anthropic Cyber Mission 공식 출범": "Anthropic",
        "미 하원의장실 White House Accord 공식 발표": "백악관·프런티어 AI 공동서약",
        "백악관 Super Intelligence 행정명령": "백악관 Super Intelligence 정책",
        "백악관 Super Intelligence 팩트시트": "백악관 Super Intelligence 정책",
        "OpenAI 프런티어 학습 Safety Case": "OpenAI",
        "NIPA 사이버보안 특화 AI 사업": "NIPA",
        "NVIDIA OpenShell 개요·지원": "NVIDIA OpenShell",
        "NVIDIA OpenShell 지원정책": "NVIDIA OpenShell",
        "NVIDIA OpenShell 보안정책": "NVIDIA OpenShell",
    }
    return mapping.get(name, "AI 안전·보안 생태계")


def _parse_iso_utc(value: str | None) -> dt.datetime | None:
    if not value:
        return None
    try:
        return dt.datetime.fromisoformat(str(value).replace("Z", "+00:00")).astimezone(UTC)
    except Exception:
        return None


def advance_official_page_state(
    name: str,
    previous: dict | None,
    snapshot: dict,
    now: dt.datetime,
    *,
    rebaseline: bool = False,
) -> tuple[dict, bool]:
    """Return (new_state, should_alert) for one official page snapshot.

    Immutable published reference documents never alert on in-place HTML
    changes. Mutable pages require the same changed digest to persist across at
    least two observations spanning ten minutes before an alert is accepted.
    This blocks CDN/A-B/render jitter and workflow bursts from becoming alerts.
    """
    digest = str(snapshot.get("digest") or "")
    url = str(snapshot.get("url") or "")
    previous = dict(previous or {})

    if rebaseline or not previous.get("digest"):
        return {
            "digest": digest,
            "url": url,
            "updated_at": now.isoformat(),
            "candidate_digest": None,
            "candidate_count": 0,
            "candidate_first_seen_at": None,
        }, False

    if name in IMMUTABLE_OFFICIAL_REFERENCE_PAGES:
        # Keep the confirmed baseline digest fixed. The page may render
        # different related-content/navigation fragments between requests.
        previous["url"] = url or previous.get("url")
        previous["candidate_digest"] = None
        previous["candidate_count"] = 0
        previous["candidate_first_seen_at"] = None
        return previous, False

    confirmed = str(previous.get("digest") or "")
    if digest == confirmed:
        previous["url"] = url or previous.get("url")
        previous["candidate_digest"] = None
        previous["candidate_count"] = 0
        previous["candidate_first_seen_at"] = None
        return previous, False

    candidate = str(previous.get("candidate_digest") or "")
    if candidate == digest:
        count = int(previous.get("candidate_count") or 0) + 1
        first_seen = _parse_iso_utc(previous.get("candidate_first_seen_at")) or now
    else:
        count = 1
        first_seen = now

    previous["url"] = url or previous.get("url")
    previous["candidate_digest"] = digest
    previous["candidate_count"] = count
    previous["candidate_first_seen_at"] = first_seen.isoformat()

    age = max(0.0, (now - first_seen).total_seconds())
    if count >= OFFICIAL_CHANGE_CONFIRM_RUNS and age >= OFFICIAL_CHANGE_CONFIRM_SECONDS:
        previous["digest"] = digest
        previous["updated_at"] = now.isoformat()
        previous["candidate_digest"] = None
        previous["candidate_count"] = 0
        previous["candidate_first_seen_at"] = None
        return previous, True

    return previous, False


HANGUL_RE = re.compile(r"[가-힣]")
LATIN_WORD_RE = re.compile(r"[A-Za-z]{2,}")
TRANSLATE_GOOGLE = "https://translate.googleapis.com/translate_a/single"
TRANSLATE_MYMEMORY = "https://api.mymemory.translated.net/get"
ALERT_IDENTIFIER_TERMS = (
    "OpenAI", "Anthropic", "Claude", "ChatGPT", "Codex", "Gemini",
    "Microsoft", "Copilot", "Meta", "Grok", "xAI", "AWS", "GitHub",
    "NVIDIA", "OpenShell", "NemoClaw", "Sentry", "BlueField-4", "BlueField",
    "SAP", "Canonical", "Red Hat", "Palo Alto Networks", "CrowdStrike", "IBM",
)


def _needs_korean_translation(text: str) -> bool:
    value = strip_html(text)
    return not HANGUL_RE.search(value) and len(LATIN_WORD_RE.findall(value)) >= 3


def _preserve_identifiers(original: str, translated: str) -> str:
    found: list[str] = []
    low = original.lower()
    for term in ALERT_IDENTIFIER_TERMS:
        if term.lower() in low and term.lower() not in translated.lower():
            found.append(term)
    for token in re.findall(r"\\b(?:CVE-\\d{4}-\\d+|GLM-\\d+(?:\\.\\d+)*(?:-[A-Za-z0-9]+)?)\\b", original, flags=re.I):
        if token.lower() not in translated.lower() and token.lower() not in {x.lower() for x in found}:
            found.append(token)
    if found:
        return " · ".join(found) + " · " + translated
    return translated


def _translate_google(text: str) -> str:
    params = urllib.parse.urlencode({
        "client": "gtx",
        "sl": "auto",
        "tl": "ko",
        "dt": "t",
        "q": text,
    })
    req = urllib.request.Request(
        TRANSLATE_GOOGLE + "?" + params,
        headers={"User-Agent": USER_AGENT, "Accept": "application/json,text/plain,*/*"},
    )
    with urllib.request.urlopen(req, timeout=20) as resp:
        payload = json.loads(resp.read().decode("utf-8"))
    chunks = payload[0] if isinstance(payload, list) and payload else []
    return "".join(str(part[0]) for part in chunks if isinstance(part, list) and part and part[0]).strip()


def _translate_mymemory(text: str) -> str:
    params = urllib.parse.urlencode({"q": text, "langpair": "en|ko"})
    req = urllib.request.Request(
        TRANSLATE_MYMEMORY + "?" + params,
        headers={"User-Agent": USER_AGENT, "Accept": "application/json"},
    )
    with urllib.request.urlopen(req, timeout=20) as resp:
        payload = json.loads(resp.read().decode("utf-8"))
    return str((payload.get("responseData") or {}).get("translatedText") or "").strip()


def translate_alert_text(text: str) -> str:
    value = " ".join(strip_html(text).split())
    if not _needs_korean_translation(value):
        return value

    errors: list[str] = []
    for translator in (_translate_google, _translate_mymemory):
        for _attempt in range(2):
            try:
                translated = " ".join(strip_html(translator(value)).split())
                if translated and HANGUL_RE.search(translated):
                    return _preserve_identifiers(value, translated)
                errors.append(f"{translator.__name__}: no Hangul in result")
            except Exception as exc:
                errors.append(f"{translator.__name__}: {type(exc).__name__}: {exc}")

    raise RuntimeError("Korean translation failed: " + " | ".join(errors[-4:]))


def concise_fact(item: dict) -> str:
    title = re.sub(r"\s+-\s+[^-]{1,40}$", "", item.get("title","")).strip()
    title = re.sub(
        r"^(?:Anthropic Research|OpenAI Alignment)\\s*:\\s*",
        "",
        title,
        flags=re.I,
    ).strip()
    try:
        title = translate_alert_text(title)
    except Exception as exc:
        print(f"ai_policy_translation_fallback={type(exc).__name__}: {exc}")
        title = f"{item.get('entity') or 'AI 안전·보안 생태계'} 관련 {item.get('category') or '정책·사업화 변화'} 공식 업데이트"
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
        if rep["category"] == "Anthropic 핵심 기반시설·오픈소스 방어 사업":
            lines.append("• <b>의미</b>: 핵심 기반시설 방어 프로그램(CIDP)의 실제 참여기관·현장 적용과 OSS Scanner의 무료 보안검사 채택량을 추적. 무료 서비스·연구지원과 확인된 유료 계약·반복매출을 구분")
        elif rep["category"] == "프런티어 AI 국가안보·정책 핵심인사 이동":
            lines.append("• <b>의미</b>: 정부의 AI·사이버·정보기관 정책 설계자가 프런티어 AI 기업의 국가안보 조직으로 이동해 규제 대응·정부 사전검토·사이버 전략과 기업 의사결정의 연결이 강화되는지 확인")
        elif rep["category"] == "백악관 Super Intelligence 정책·법제화":
            lines.append("• <b>의미</b>: Super Intelligence 공식 정의·연방 후속조치·입법 문구가 바뀌어 자율 안전협약이 실제 법·규제 체계로 이동하는지 확인")
        elif rep["category"] == "프런티어 AI 공동 서약·서명기업 변화":
            lines.append("• <b>의미</b>: 자율 서약의 참여 범위가 넓어지거나 축소되는지, 특정 기업의 가입·탈퇴가 공동 안전기준의 사실상 적용 범위를 바꾸는지 확인")
        elif rep["category"] == "공동 안전표준·모범사례":
            lines.append("• <b>의미</b>: 선언적 원칙이 실제 공통 기술표준·평가항목·운영절차로 구체화되는 첫 전환점인지 확인")
        elif rep["category"] == "외부감사 규격·감사기관":
            lines.append("• <b>의미</b>: 감사기관 자격·접근권·주기·범위가 정해져 반복 감사시장과 실제 기업 준수비용으로 연결되는지 확인")
        elif rep["category"] == "독립 이사회·감독위원회":
            lines.append("• <b>의미</b>: 독립 감독기구가 실제 설치되고 감사결과·학습·배포 중단 권한을 행사하는지 확인")
        elif rep["category"] == "자율서약→법·조달·보험 성문화":
            lines.append("• <b>의미</b>: 자율 원칙이 법률·규정·연방조달·보험·인증 조건으로 바뀌어 강제 지출과 준수비용을 만드는지 확인")
        elif rep["category"] == "파트너→유료고객·운영전환":
            lines.append("• <b>의미</b>: 단순 생태계 참여가 실제 상용 배포·본계약·유료고객으로 전환됐는지 확인")
        elif rep["category"] == "OpenShell 실사용·채택 지표":
            lines.append("• <b>의미</b>: 발표·GitHub 관심도가 아니라 실제 샌드박스 사용량·실패율·차단량·프로바이더 믹스로 기업 채택을 확인")
        elif rep["category"] == "Sentry SKU·가격·라이선스":
            lines.append("• <b>의미</b>: Sentry가 BlueField 부가 기능에 머무는지, 별도 SKU·라이선스·구독매출로 독립 수익화되는지 확인")
        elif rep["category"] == "BlueField 증분 장착·DPU 수익화":
            lines.append("• <b>의미</b>: Rubin NVL72 기본 BlueField-4 물량은 기준선으로 제외하고, 비-NVIDIA·기존 서버의 추가 장착만 증분 DPU 수요로 확인")
        elif rep["category"] == "OpenShell 기본내장·지원 확대":
            lines.append("• <b>의미</b>: OpenShell이 선택 설치를 넘어 주요 에이전트·기업 플랫폼의 기본 런타임으로 굳어지는지 확인")
        elif rep["category"] == "하드웨어 격리 의무·조달":
            lines.append("• <b>의미</b>: 금융·공공·의료 조달·보험·인증에서 하드웨어 격리가 사실상 필수요건이 되는지 확인")
        elif rep["category"] == "에이전트 안전 런타임·신뢰 플랫폼":
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
    lines += ["", "<b>다음 확인</b>: 프런티어 AI 기업의 ONCD·OSTP·NSA·국방부 출신 핵심인사 영입 및 직무범위 · 공동서약 서명기업 가입·탈퇴 · 첫 공동 안전표준·모범사례 · 외부감사기관 자격/접근권/주기/범위 · 독립 이사회·감독위원회 설치 · 법률·규정·연방조달·보험·인증 성문화 · Safety Case 실제 학습 승인 · 파트너→유료고객 전환 · OpenShell/Sentry/BlueField 실사용·수익화"]
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
    # Snapshot extraction rules are versioned. Published reference documents
    # never alert on in-place HTML changes, and mutable pages require a stable
    # changed digest across multiple observations separated by time.
    official_pages = dict(state.get("official_pages") or {})
    prior_snapshot_schema = int(state.get("official_snapshot_schema_version") or 0)
    rebaseline_official_pages = prior_snapshot_schema != OFFICIAL_SNAPSHOT_SCHEMA_VERSION
    try:
        snapshots = official_page_snapshots()
        for name, snap in snapshots.items():
            previous = official_pages.get(name)
            page_state, should_alert = advance_official_page_state(
                name,
                previous,
                snap,
                now,
                rebaseline=rebaseline_official_pages,
            )
            official_pages[name] = page_state

            if should_alert:
                item = normalize({
                    "kind":"official",
                    "query":"official page change",
                    "title":f"{name} 공식 페이지 변경 감지",
                    "description":snap.get("material",""),
                    "source":official_page_source(name),
                    "url":snap["url"],
                    "published_at":now.isoformat(),
                })
                item["category"] = forced_official_page_category(name)
                item["entity"] = forced_official_page_entity(name)
                new_items.append(item)
                print(f"ai_policy_official_change_confirmed={name}")
            elif (
                previous
                and str(previous.get("digest") or "") != str(snap.get("digest") or "")
                and name in IMMUTABLE_OFFICIAL_REFERENCE_PAGES
            ):
                print(f"ai_policy_immutable_render_jitter_ignored={name}")

        if rebaseline_official_pages:
            print(
                f"ai_policy_official_pages_rebaselined=true "
                f"schema={OFFICIAL_SNAPSHOT_SCHEMA_VERSION}"
            )
    except Exception as exc:
        errors.append(f"공식 사업페이지 감시 실패: {type(exc).__name__}: {exc}")

    openshell_telemetry = dict(state.get("openshell_telemetry") or {})
    try:
        telemetry = fetch_openshell_telemetry()
        previous_telemetry = dict(openshell_telemetry)
        if previous_telemetry and (
            previous_telemetry.get("name") != telemetry.get("name")
            or previous_telemetry.get("digest") != telemetry.get("digest")
        ):
            new_items.append(normalize({
                "kind":"official",
                "query":"OpenShell official telemetry",
                "title":f"NVIDIA OpenShell 실사용 텔레메트리 {telemetry['name']}: {telemetry['title']}",
                "description":telemetry.get("detail",""),
                "source":"NVIDIA",
                "url":telemetry["url"],
                "published_at":now.isoformat(),
            }))
        openshell_telemetry = {
            "name": telemetry.get("name"),
            "digest": telemetry.get("digest"),
            "url": telemetry.get("url"),
            "title": telemetry.get("title"),
            "detail": telemetry.get("detail"),
            "updated_at": now.isoformat(),
        }
    except Exception as exc:
        errors.append(f"OpenShell 텔레메트리 감시 실패: {type(exc).__name__}: {exc}")

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
        "official_snapshot_schema_version": OFFICIAL_SNAPSHOT_SCHEMA_VERSION,
        "openshell_telemetry": openshell_telemetry,
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
        f"- OpenShell 텔레메트리 최신: {openshell_telemetry.get('name') or '확인 불가'}",
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
