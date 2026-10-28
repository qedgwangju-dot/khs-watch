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
    '"PHP" "사이버위기 경보" (과학기술정보통신부 OR 과기정통부 OR KISA) (상향 OR 하향 OR 해제)',
    '"PHP" (범부처 종합대책 OR 의무 점검 OR 정부 지원 예산 OR 보안 의무화) (확정 OR 발표 OR 시행)',
    '네이버클라우드 S2W 샌즈랩 LG CNS 사이버보안 AI 계약 실증',
    '"파이오링크" (MDR OR "관리형 탐지" OR 보안관제) (고객 OR 계약 OR 유료 OR 확대)',
    '"파이오링크" "PHP2Shell" (점검 OR 계약 OR 유료)',
    '"이스트시큐리티" "PHP2Shell" (무료 OR 점검 OR 계약 OR 유료)',
    '"SGA솔루션즈" "PHP2Shell" (가상패치 OR 유료 OR 계약)',
    '"엑스게이트" (PHP2Shell OR "PHP 취약점") (수주 OR 방화벽 OR 계약)',
    '"111개 기관" "172개" 기반시설 점검',
    '"주요정보통신기반시설" (점검 완료 OR 낙찰 OR 계약 OR 결과)',

    '("지니언스" OR "Genians") ("넥서스 프레임워크" OR "Nexus Framework") (고객 OR 계약 OR 수주 OR 실증 OR 상용 운영)',
    '("케이사인" OR "KSign") ("전기차 충전" OR "EV charging") (취약점 OR 보안) (계약 OR 상용화 OR 고객 실증)',
    '("샌즈랩" OR "SandLab") ("네이버클라우드" OR "보안 특화 AI") (유료 OR 계약 OR 실증 OR 수주 OR 상용)',

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
    '"Super Intelligence Force" "incident" "notification" "remediation" AI',
    '(Federal Register OR NIST OR FTC) "AI model" "incident" "reporting" "remediation" rule',
    '(Anthropic "Cyber Mission" OR "Critical Infrastructure Defense Program" OR "OSS Scanner") (partners OR deployments OR customers OR scanner OR funding)',
    '"Thomas Lind" OpenAI ONCD cyber strategic risk',
    '"Dean Ball" OpenAI OSTP Strategic Futures AI Action Plan',
    '(OpenAI OR Anthropic OR Google DeepMind OR xAI OR Meta) (ONCD OR OSTP OR NSA OR NSC OR Pentagon) (hire OR hired OR joins OR joined OR appoint OR appointed) "national security"',
    '(OpenAI OR Anthropic OR Google DeepMind OR xAI OR Meta) former White House cyber AI policy official national security hire',
    '"OpenAI" "Trail of Bits" (acquisition OR buy OR agreement OR deal OR talks OR completed OR withdrawn)',
    '("Patch the Planet" OR "Codex Security") "Trail of Bits" (paid OR customers OR subscription OR contract OR license OR expansion)',
    # Separate reported physical-security M&A from cyber incidents.
    '("SoftBank" "Allied Universal") (acquisition OR takeover OR negotiations OR agreement OR completion)',
    '"SoftBank" "Allied Universal" (robots OR data center security) (contract OR deployment OR acquisition)',
    # A private industry draft is not an introduced/enacted congressional bill.
    '"Anthropic" "AI safety bill" (lawmakers OR Congress OR proposal OR introduced OR enacted)',
    '"Anthropic" "frontier AI" (bill OR legislation) (Commerce OR Congress OR independent evaluators)',
    # Cohere–AISLE acquisition stages and commercialization; not a cyber incident.
    '"Cohere" "AISLE" ("letter of intent" OR acquisition OR "definitive agreement" OR closing OR terminated)',
    '"Cohere Cyber" "AISLE" (customer OR contract OR product OR deployment OR license OR subscription)',
    '"Aidan Gomez" "AISLE" (CNBC OR "rogue agents" OR cybersecurity)',
    '"CrowdStrike" "NVIDIA" "Falcon Guardian" ("OpenShell" OR "Sentry" OR deployment OR integration)',
    '"Falcon Guardian" "BlueField-4" (availability OR rollout OR paid OR customer OR contract OR Sentry)',
    # FTC civil subpoenas are not findings of liability; follow real enforcement milestones.
    '"FTC" ("OpenAI" OR "Anthropic") (subpoena OR complaint OR settlement OR consent order)',
    '"FTC" ("OpenAI" OR "Anthropic") ("AI agents" OR "AI model") (enforcement OR investigation OR lawsuit)',
]

# Historical reports supplied and cross-checked on 2026-10-17.
# These existing stages are silently seeded so syndicated reprints cannot
# masquerade as a new agreement or an enacted rule.
POLICY_EVENT_BASELINES = {
    "infra172:inspection_started_20261028": {"source_url":"https://www.yna.co.kr/view/AKR20261028025200017","status":"111 institutions, 172 facilities, existing government inspection; incremental procurement unconfirmed"},
    "piolink_mdr:expansion_announced_20261028": {"source_url":"https://www.newsis.com/view/NISX20261028_0003844426","status":"Multivendor EDR + MDR expansion; no standalone paid contract amount verified"},
    "piolink_php:free_check_page_20261023": {"source_url":"https://www.piolink.com/kr/company/News.php?bbsCode=media_press&idx=925&vType=view","status":"Free PHP2Shell public check page, not paid contract"},
    "estsecurity_php:free_scanner_20261028": {"source_url":"https://www.estsecurity.com/public/security-center/download","status":"Free four-mode scanner supports three CVEs, no direct revenue confirmed"},
    "sga_php:virtual_patch_free_20261028": {"source_url":"https://www.etnews.com/20261028000059","status":"vAegis and RedCastle virtual patch support, trial not paid revenue"},
    "axgate_php:theme_reaction_20261028": {"source_url":"https://www.financialpost.co.kr/news/articleView.html?idxno=282981","status":"Intraday rally on PHP security theme, no new issuer PHP-specific contract"},

    "genians_nexus:development_complete_20260916": {
        "source_url": "https://www.genians.co.kr/pr-room/press/260916",
        "status": "2026-09-16 issuer announcement: Nexus Framework developed and demonstrated at GISEC; no disclosed incremental Nexus-only paid contract",
    },
    "ksign_evsec:demonstration_announced_20261020": {
        "source_url": "https://www.newswire.co.kr/newsRead.php?no=1045070",
        "status": "2026-10-20 issuer-distributed EV charging security analysis demo at KOAA SHOW Oct 21-23; demo is not customer purchase",
    },
    "ksign_sandslab:naver_security_model_selected_20260903": {
        "source_url": "https://www.yna.co.kr/view/AKR20260903037252017",
        "status": "2026-09-03 NAVER Cloud consortium selected; SandLab participating and KSign owns 42.01% of SandLab (not separate KSign contract)",
    },
    "php_korea_response:caution_elevated_20261022": {
        "source_url": "https://www.korea.kr/news/policyNewsView.do?newsId=148974113",
        "status": "2026-10-22 12:00 KST: 민간 분야 사이버위기 경보 관심→주의 상향; 기존 기준선",
    },
    "php_korea_response:comprehensive_plan_proposed_20261023": {
        "source_url": "https://imnews.imbc.com/news/2026/econo/article/6860231_36933.html",
        "status": "2026-10-23 범부처 종합대책 마련·조직 정비 검토 발언; 시행 확정 아님",
    },
    "cohere_aisle:letter_of_intent_announced": {
        "source_url": "https://cohere.com/blog/cohere-and-aisle-sign-letter-of-intent-to-advance-cyber-resilient-sovereign-ai",
        "status": "2026-10-15 Cohere and AISLE signed an LOI only; no definitive contract, closing, price or incremental revenue confirmed",
    },
    "softbank_allied:initial_talks_reported": {
        "source_url": "https://www.ft.com/content/e44a17f9-5be0-4a78-89fb-41c4578838ca",
        "status": "2026-10-17 FT / 2026-10-16 Bloomberg and Reuters early discussions; no signed deal",
    },
    "anthropic_frontier_bill:private_draft_reported": {
        "source_url": "https://www.reuters.com/legal/litigation/anthropic-quietly-pitches-its-own-ai-safety-bill-lawmakers-politico-reports-2026-10-16/",
        "status": "2026-10-16 Politico/Reuters private draft; not introduced or enacted",
    },
    **{
        f"ftc_ai_safety_{subject}:subpoenas_reported": {
            "source_url": "https://www.reuters.com/business/us-ftc-subpoenas-openai-anthropic-over-consumer-harms-axios-reports-2026-10-15/",
            "status": "2026-10-15 Axios/Reuters civil subpoena reporting only; investigation is not a liability finding",
        }
        for subject in ("both", "openai", "anthropic")
    },
}

OFFICIAL_SOURCE_HINTS = (
    "openai", "anthropic", "nipa", "과학기술정보통신부", "msit", "kisa", "한국인터넷진흥원",
    "nists", "nist", "cisa", "gov.uk", "aisi", "european commission",
    "europa.eu", "oecd", "white house", "whitehouse.gov", "commerce department", "ntia",
    "house.gov", "u.s. house", "house of representatives",
    "federalregister.gov", "federal register", "congress.gov", "congress",
    "naver", "lg cns", "s2w", "샌즈랩", "palo alto", "unit 42",
    "crowdstrike", "ibm", "nvidia", "microsoft", "openshell",
    "nemoclaw", "sentry", "sap", "canonical", "red hat",
    "trail of bits", "trailofbits.com", "cohere", "aisle",
    "piolink", "파이오링크", "estsecurity", "이스트시큐리티", "axgate", "엑스게이트",
    "genians", "지니언스", "ksign", "케이사인", "sandslab",
)

TRUSTED_SOURCE_HINTS = (
    "reuters", "axios", "politico", "the information", "softbank group", "allied universal", "yonhap", "연합뉴스", "financial times", "bloomberg",
    "the information", "zdnet", "전자신문", "etnews", "파이낸셜뉴스",
    "매일경제", "한국경제", "머니투데이", "이데일리", "조선비즈",
    "서울경제", "디지털데일리", "디지털타임스", "the verge",
    "techcrunch", "wired", "securityweek", "palo alto", "unit 42",
    "associated press", "ap news", "guardian", "cbs news", "wall street journal", "wsj",
    "crowdstrike", "ibm", "nvidia", "microsoft", "mbc", "ytn",
    "trail of bits", "trailofbits.com", "cnbc",
    "piolink", "파이오링크", "estsecurity", "이스트시큐리티",
    "axgate", "엑스게이트", "sga솔루션즈", "SGA솔루션즈",
    "뉴시스", "newsis", "보안뉴스", "파이낸셜포스트",
    "genians", "지니언스", "ksign", "케이사인", "sandslab", "newswire", "뉴스와이어", "thelec", "디일렉",
)

AI_TOPIC_TERMS = (
    "ai safety", "artificial intelligence", "frontier model", "frontier ai",
    "recursive self-improvement", "rsi", "cybersecurity ai", "ai cybersecurity",
    "ai security", "foundation model", "preparedness framework", "model evaluation",
    "joint commitment on frontier responsibilities", "white house accord on super intelligence",
    "frontier responsibilities", "super intelligence", "superintelligence",
    "super intelligence force", "incident disclosure", "incident reporting",
    "notification and remediation", "ai model incidents",
    "인공지능", "ai", "사이버보안", "보안 ai", "파운데이션 모델", "안전연구소",
    "프런티어 책임", "공동 서약", "공동 합의", "감독위원회",
    "anthropic cyber mission", "critical infrastructure defense program",
    "oss scanner", "사이버 방어 사업", "핵심 기반시설 방어",
    "openai", "trail of bits", "patch the planet", "codex security",
)

ACTION_TERMS = (
    # Standards / regulation / reporting.
    "standard", "standards", "adopt", "adopts", "adopted", "mandatory",
    "regulation", "regulatory", "law", "legislation", "bill", "requirement",
    "incident reporting", "reporting requirement", "audit", "auditor",
    "notify", "notification", "remediate", "remediation", "disclose", "disclosure",
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
    "immediately disclose", "swift remedial action", "incident notification",
    "external evaluation", "governance gate", "fail-closed", "fail closed",
    "joint commitment", "accord", "signatory", "signatories", "oversight board",
    "board committee", "independent board", "self-police", "self-regulation",
    "codify", "codified", "best practices", "common standards",
    "acquisition", "acquire", "acquired", "merger", "deal talks",
    "definitive agreement", "transaction closed", "exclusive negotiations",
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
    "acquisition", "agreed to acquire", "deal closed",
    "definitive agreement", "exclusive negotiations",
    "인수 협상", "본계약", "인수 완료",
    "사이버 방어 사업", "오픈소스 보안", "취약점 검사", "핵심 기반시설",
    "hired", "joined", "appointed", "national security policy", "strategic risk",
    "영입", "합류", "임명", "국가안보 정책", "전략적 리스크",
    "표준 제정", "공고", "선정", "계약", "수주", "조달", "입찰",
    "예산", "지원", "실증", "착수", "중간평가", "상용화",
)

CATEGORY_PATTERNS = [
    ("OpenAI–Trail of Bits 인수·계약 단계", (
        "trail of bits", "early acquisition talks",
        "definitive agreement", "acquisition completed",
        "openai to acquire", "인수 협상", "인수 완료",
    )),
    ("OpenAI–Trail of Bits 취약점 수정 사업화", (
        "patch the planet", "codex security", "paid security engagement",
        "security customers", "subscription",
    )),
    ("미국 AI 사고 신고·시정 요구 발표", (
        "white house ai reporting mandate", "anthropic breaches spark",
        "notification and remediation process", "immediately disclose incidents",
        "report and remediate", "si force incident reporting",
        "백악관 인공지능 사고 신고", "사고 즉시 신고", "신고·시정 요구",
    )),
    ("Anthropic 핵심 기반시설·오픈소스 방어 사업", (
        "anthropic cyber mission", "critical infrastructure defense program",
        "cidp", "oss scanner", "핵심 기반시설 방어", "오픈소스 취약점 검사",
    )),
    ("프런티어 AI 국가안보·정책 핵심인사 이동", (
        "thomas lind", "dean ball",
    "trail of bits", "patch the planet", "codex security",
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
    "super intelligence force", "incident notification", "model incident reporting",
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
    # Keep existing Korean feeds unchanged. Search the two newly added US
    # company/legislative storylines in the edition where they originate.
    global_story = (
        ("SoftBank" in query and "Allied Universal" in query)
        or ("Anthropic" in query and (
            "AI safety bill" in query or "frontier AI" in query and "bill" in query
        ))
    )
    return GOOGLE_NEWS + "?" + urllib.parse.urlencode({
        "q": query,
        "hl": "en-US" if global_story else "ko",
        "gl": "US" if global_story else "KR",
        "ceid": "US:en" if global_story else "KR:ko",
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
            "publisher_url": (source_node.attrib.get("url") or "").strip() if source_node is not None else "",
            "url": link,
            "published_at": published.isoformat() if published else None,
        })
    return out


def official_page_snapshots(*, skipped: list[str] | None = None) -> dict[str, dict]:
    out = {}
    for name, url in KNOWN_OFFICIAL_PAGES.items():
        try:
            raw = fetch_bytes(url).decode("utf-8", "ignore")
        except Exception as exc:
            # One vendor page can block automated access (for example HTTP 403).
            # Do not let that disable all of the other official-page checks.
            print(f"ai_policy_official_page_skip={name}: {type(exc).__name__}: {exc}")
            if skipped is not None:
                skipped.append(f"{name}: {type(exc).__name__}: {exc}")
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
    # The publisher's maintained report index is the primary discovery source.
    # Avoid the unauthenticated GitHub contents API on every scheduled run:
    # its shared rate limit can yield HTTP 403 while the raw files work.
    index_url = "https://raw.githubusercontent.com/NVIDIA/OpenShell/main/telemetry/README.md"
    raw_base = "https://raw.githubusercontent.com/NVIDIA/OpenShell/main/telemetry/"
    reports = []
    try:
        index = fetch_bytes(index_url).decode("utf-8", "ignore")
        names = re.findall(r"\]\(\s*(\d{4}-\d{2}-\d{2}\.md)\s*\)", index)
        for name in set(names):
            reports.append({
                "name": name,
                "download_url": raw_base + name,
                "html_url": "https://github.com/NVIDIA/OpenShell/blob/main/telemetry/" + name,
            })
        if not reports:
            raise ValueError("No dated report links in publisher README")
    except Exception as index_error:
        # Preserve the old API path as a fallback rather than hiding failures.
        try:
            api = "https://api.github.com/repos/NVIDIA/OpenShell/contents/telemetry?ref=main"
            payload = json.loads(fetch_bytes(api).decode("utf-8"))
            for row in payload if isinstance(payload, list) else []:
                name = str(row.get("name") or "")
                if re.fullmatch(r"\d{4}-\d{2}-\d{2}\.md", name):
                    reports.append(row)
        except Exception as api_error:
            raise RuntimeError(
                f"OpenShell telemetry discovery failed: index={index_error}; api={api_error}"
            ) from api_error
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

def cohere_aisle_publisher_verified(item: dict) -> bool:
    """Company-branded news is official only with its matching publisher host.

    Google News source labels are self-descriptions, not proof that the source
    is controlled by Cohere or AISLE. Do not promote a spoofed label into a
    signed/closed acquisition milestone.
    """
    label = str(item.get("source") or "").strip().lower()
    if not label.startswith(("cohere", "aisle")):
        return True  # Trusted independent media has its own source checks.
    link = (item.get("publisher_url") or "").strip()
    if not link and item.get("kind") == "official_direct":
        link = (item.get("url") or "").strip()
    try:
        host = (urllib.parse.urlsplit(link).hostname or "").lower()
    except ValueError:
        return False
    if label.startswith("cohere"):
        return host in ("cohere.com", "www.cohere.com")
    return host in ("aisle.com", "www.aisle.com")


def crowdstrike_nvidia_publisher_verified(item: dict) -> bool:
    """Company-branded feeds must resolve to the verified issuer domain."""
    source = str(item.get("source") or "").strip().lower()
    if not (source.startswith("crowdstrike") or source == "nvidia"):
        return True
    link = str(item.get("publisher_url") or "").strip()
    if not link and item.get("kind") in ("official", "official_direct"):
        link = str(item.get("url") or "").strip()
    try:
        host = (urllib.parse.urlsplit(link).hostname or "").lower()
    except ValueError:
        return False
    domain = "crowdstrike.com" if source.startswith("crowdstrike") else "nvidia.com"
    return host == domain or host.endswith("." + domain)


def source_official(source: str) -> bool:
    low = source.lower()
    return any(x in low for x in OFFICIAL_SOURCE_HINTS)


def source_trusted(source: str) -> bool:
    low = source.lower()
    return source_official(source) or any(x in low for x in TRUSTED_SOURCE_HINTS)


def is_trail_mna_pair(item: dict) -> bool:
    low = f" {item.get('title','')} {item.get('description','')} ".lower()
    return "openai" in low and "trail of bits" in low


def trail_of_bits_mna_stage(item: dict) -> str | None:
    """Stable corporate milestones, not speculative prices or conditional verbs."""
    if not is_trail_mna_pair(item):
        return None
    low = f" {item.get('title','')} {item.get('description','')} ".lower()
    if not any(word in low for word in (
        "acquisition", "acquire", "acquired", "merger", "takeover",
        "buy security startup", "buy trail of bits", "purchase trail of bits",
        "to buy trail of bits", "인수",
    )):
        return None
    official = source_official(item.get("source", ""))
    # Keep 'could fall apart' as an initial-stage caveat, not deal cancellation.
    if any(phrase in low for phrase in (
        "talks have ended", "talks ended", "deal collapsed", "deal terminated",
        "abandoned acquisition", "ends acquisition talks", "협상 결렬",
    )):
        return "talks_ended" if official else "talks_ended_reported"
    if any(phrase in low for phrase in (
        "completed acquisition", "completes acquisition",
        "completes its acquisition", "has completed acquisition",
        "acquisition completed", "acquisition closed", "closed acquisition",
        "closed its acquisition", "has acquired trail of bits",
        "acquires trail of bits", "인수 완료",
    )):
        return "closed" if official else "closed_reported"
    if any(phrase in low for phrase in (
        "signed a definitive agreement", "definitive agreement to acquire",
        "agreed to acquire trail of bits", "agreement to buy trail of bits",
        "인수 본계약", "인수 계약 체결",
    )):
        return "signed" if official else "signed_reported"
    if any(phrase in low for phrase in (
        "exclusive talks", "exclusive negotiations",
        "exclusive acquisition negotiations", "exclusive acquisition talks",
        "advanced acquisition negotiations", "advanced acquisition talks",
        "close to acquiring trail of bits", "협상 진전", "독점 협상",
    )):
        return "advanced_talks_reported"
    return "initial_talks"



def is_php_korea_policy(item: dict) -> bool:
    text = f" {item.get('title','')} {item.get('description','')} ".lower()
    return (
        any(x in text for x in ("php2shell", "php 취약점", "php 보안", "php vulnerability"))
        and any(x in text for x in (
            "과기정통부", "과학기술정보통신부", "kisa",
            "한국인터넷진흥원", "대한민국 정책브리핑", "정부", "사이버위기",
            "ministry", "cyber alert",
        ))
    )


def php_korea_publisher_verified(item: dict) -> bool:
    """Official ministry-branded syndicated news must resolve to the issuer."""
    if not is_php_korea_policy(item):
        return True
    source = str(item.get("source") or "").lower()
    if not any(x in source for x in (
        "과기정통부", "과학기술정보통신부", "kisa",
        "한국인터넷진흥원", "대한민국 정책브리핑",
    )):
        return True
    url = str(item.get("publisher_url") or item.get("url") or "")
    try:
        host = (urllib.parse.urlsplit(url).hostname or "").lower()
    except ValueError:
        return False
    return any(host == d or host.endswith("." + d) for d in (
        "msit.go.kr", "kisa.or.kr", "korea.kr",
    ))



def k_security_business_stage(item: dict) -> tuple[str, str] | None:
    """Track commercial stages, never equate demonstrations with contracts."""
    title = str(item.get("title") or "").lower()
    context = f" {title} {item.get('description','')} ".lower()
    nexus = (("genians" in context or "지니언스" in context) and
             ("nexus framework" in context or "넥서스 프레임워크" in context))
    evsec = (("ksign" in context or "케이사인" in context) and
             any(x in context for x in ("전기차 충전", "ev charging", "charging infrastructure")) and
             any(x in context for x in ("보안", "security", "취약점", "vulnerabil")))
    sandslab = (("샌즈랩" in context or "sandslab" in context) and
                any(x in context for x in ("네이버클라우드", "naver cloud", "navercloud", "보안 특화 ai",
                                           "사이버보안 특화 ai", "cybersecurity foundation")))
    if not (nexus or evsec or sandslab):
        return None
    group = "genians_nexus" if nexus else "ksign_evsec" if evsec else "ksign_sandslab"

    # Speculative headlines cannot be promoted from plans to actual orders.
    uncertain = any(x in title for x in (
        "예정", "추진", "검토", "논의", "기대", "전망", "목표", "계획",
        "may ", "could ", "plans ", "planning", "expected", "proposes",
        "rumor", "rumour", "가능성", "협의",
    ))
    if not uncertain:
        if any(x in title for x in (
            "유료 계약 체결", "유료 공급 계약", "유료 공급계약", "고객 계약 체결",
            "공급계약 체결", "공급 계약 체결", "상용 계약 체결", "신규 수주",
            "signed paid", "signs paid", "signed customer contract",
            "commercial contract signed", "wins enterprise contract",
        )):
            return group, "paid_customer_contract_reported"
        if any(x in title for x in (
            "현장 상용 운영 개시", "고객 운영 개시", "정식 서비스 출시",
            "상용 서비스 출시", "정식 출시", "production deployment live",
            "production rollout live", "commercial service launched",
            "generally available",
        )):
            return group, "production_live_reported"
        if any(x in title for x in (
            "고객 실증 착수", "유료 실증 착수", "유료 실증 계약",
            "유료 개념검증", "pilot customer signed",
            "paid pilot begins", "customer pilot starts", "고객 검증 완료",
        )):
            return group, "customer_pilot_reported"
    if group == "genians_nexus":
        return group, "development_complete_20260916"
    if group == "ksign_evsec":
        return group, "demonstration_announced_20261020"
    return group, "naver_security_model_selected_20260903"


def k_security_business_publisher_verified(item: dict) -> bool:
    """Check corporate-branded feeds against issuer/publisher domain."""
    stage = k_security_business_stage(item)
    if not stage:
        return True
    source = str(item.get("source") or "").strip().lower()
    link = str(item.get("publisher_url") or item.get("url") or "").strip()
    try:
        host = (urllib.parse.urlsplit(link).hostname or "").lower()
    except ValueError:
        return False
    if not host:
        return False
    def is_domain(domain):
        return host == domain or host.endswith("." + domain)
    if source in ("genians", "지니언스", "genians inc.", "genians inc"):
        return is_domain("genians.co.kr")
    if source in ("ksign", "케이사인"):
        return is_domain("ksign.com") or is_domain("newswire.co.kr")
    if source in ("sandslab", "샌즈랩"):
        return is_domain("sandslab.io") or is_domain("sandslab.co.kr")
    if source in ("naver cloud", "navercloud", "네이버클라우드"):
        return is_domain("navercorp.com") or is_domain("ncloud.com")
    publisher_domains = (
        (("전자신문", "etnews"), "etnews.com"),
        (("thelec", "디일렉", "더일렉"), "thelec.kr"),
        (("연합뉴스", "yonhap"), "yna.co.kr"),
        (("뉴스와이어", "newswire"), "newswire.co.kr"),
        (("한국경제", "hankyung"), "hankyung.com"),
        (("zdnet",), "zdnet.co.kr"),
    )
    for aliases, domain in publisher_domains:
        if any(alias in source for alias in aliases):
            return is_domain(domain)
    return True


def k_security_business_official(item: dict) -> bool:
    stage = k_security_business_stage(item)
    if not stage:
        return True
    source = str(item.get("source") or "").lower().strip()
    try:
        host = (urllib.parse.urlsplit(str(item.get("publisher_url") or item.get("url") or "")).hostname or "").lower()
    except ValueError:
        return False
    if source in ("genians", "지니언스", "genians inc.", "genians inc"):
        return host == "genians.co.kr" or host.endswith(".genians.co.kr")
    if source in ("ksign", "케이사인"):
        return host == "ksign.com" or host.endswith(".ksign.com")
    if source in ("sandslab", "샌즈랩"):
        return host in ("sandslab.io", "sandslab.co.kr") or host.endswith((".sandslab.io", ".sandslab.co.kr"))
    if source in ("naver cloud", "navercloud", "네이버클라우드"):
        return host in ("navercorp.com", "ncloud.com") or host.endswith((".navercorp.com", ".ncloud.com"))
    return not source_official(source)

def php_business_event_stage(item: dict) -> tuple[str, str] | None:
    """Commercial and public-inspection stages, separated from PHP exploitation."""
    title = str(item.get("title") or "").lower()
    body = f"{title} {item.get('description','')}".lower()
    php = any(x in body for x in ("php2shell", "php 취약점", "php투셸"))
    if (any(x in body for x in ("기반시설", "information infrastructure"))
            and any(x in body for x in ("172", "170여", "111개"))
            and any(x in body for x in ("점검", "inspection", "취약점"))):
        group = "infra172"
    elif any(x in body for x in ("piolink", "파이오링크")):
        group = "piolink_mdr" if any(x in body for x in ("mdr", "관리형 탐지", "멀티 edr")) else "piolink_php" if php else None
    elif any(x in body for x in ("estsecurity", "이스트시큐리티")) and php:
        group = "estsecurity_php"
    elif any(x in body for x in ("sga솔루션즈", "sga solutions")) and php:
        group = "sga_php"
    elif any(x in body for x in ("axgate", "엑스게이트")) and php:
        group = "axgate_php"
    else:
        group = None
    if not group:
        return None
    plans = any(x in title for x in ("계획", "예정", "검토", "추진", "전망", "기대", "목표", "협의", "could ", "may ", "plans ", "expected "))
    if group == "infra172":
        for stage, words in (
            ("inspection_completed_reported", ("점검 완료", "점검 종료")),
            ("inspection_results_reported", ("점검 결과 발표", "점검 결과 공개")),
            ("procurement_awarded_reported", ("낙찰", "조달 계약", "계약 체결")),
            ("budget_approved_reported", ("예산 확정", "사업비 확정")),
            ("checklist_sent_reported", ("체크리스트 배포 완료", "점검 동의 확보")),
        ):
            if any(w in title for w in words) and not plans:
                return group, stage
        return group, "inspection_started_20261028"
    if not plans:
        for stage, words in (
            ("paid_contract_reported", ("유료 공급계약", "유료 공급 계약", "신규 수주 확정", "공급 계약 체결", "유료 고객 계약 체결", "paid contract signed", "customer contract awarded")),
            ("renewal_reported", ("재계약 체결", "유료 계약 갱신", "subscription renewal signed")),
            ("customer_pilot_reported", ("고객 실증 착수", "유료 실증 계약", "customer pilot started")),
            ("paying_customers_reported", ("유료 고객 수 공개", "유료 고객 확보", "paid customers disclosed")),
            ("production_live_reported", ("상용 운영 개시", "정식 유료 서비스 출시", "production rollout live")),
        ):
            if any(w in title for w in words):
                return group, stage
    historical = {
        "piolink_mdr": "expansion_announced_20261028",
        "piolink_php": "free_check_page_20261023",
        "estsecurity_php": "free_scanner_20261028",
        "sga_php": "virtual_patch_free_20261028",
        "axgate_php": "theme_reaction_20261028",
    }
    return group, historical[group]


def php_business_publisher_verified(item: dict) -> bool:
    """Verify brand attribution, not a syndicated RSS label alone."""
    if not php_business_event_stage(item):
        return True
    source = str(item.get("source") or "").lower()
    url = str(item.get("publisher_url") or item.get("url") or "")
    try:
        host = (urllib.parse.urlsplit(url).hostname or "").lower()
    except ValueError:
        return False
    if not host:
        return False
    for aliases, domain in (
        (("파이오링크", "piolink"), "piolink.com"),
        (("이스트시큐리티", "estsecurity"), "estsecurity.com"),
        (("엑스게이트", "axgate"), "axgate.com"),
        (("연합뉴스", "yonhap"), "yna.co.kr"),
        (("뉴시스", "newsis"), "newsis.com"),
        (("전자신문", "etnews"), "etnews.com"),
        (("파이낸셜포스트", "financialpost"), "financialpost.co.kr"),
        (("보안뉴스",), "boannews.com"),
    ):
        if any(x in source for x in aliases):
            return host == domain or host.endswith("." + domain)
    return source_trusted(source)


def tracked_policy_event_stage(item: dict) -> tuple[str, str] | None:
    """Classify a new *reported* milestone from the headline, never from a
    speculative paragraph about what could happen. No issuer/legislative
    confirmation is inferred from a syndicated RSS publisher label.
    """
    title = str(item.get("title") or "").lower()
    context = f"{item.get('title','')} {item.get('description','')}".lower()

    business = php_business_event_stage(item)
    if business:
        return business
    commercial_stage = k_security_business_stage(item)
    if commercial_stage:
        return commercial_stage

    # The known October 22/23 notices are historical baselines, not fresh
    # regulations or a second emergency broadcast.
    if is_php_korea_policy(item):
        if any(x in title for x in ("사이버위기 경보 해제", "사이버위기경보 해제", "경보 해제", "warning lifted")):
            return ("php_korea_response", "warning_lifted_reported")
        if any(x in title for x in ("사이버위기 경보 하향", "경보 하향", "warning lowered")):
            return ("php_korea_response", "warning_lowered_reported")
        if any(x in title for x in ("'심각'", "‘심각’", " 심각 단계", "경보 심각", "critical alert")) and any(x in title for x in ("상향", "발령", "raised", "declared")):
            return ("php_korea_response", "critical_elevated_reported")
        if any(x in title for x in ("'경계'", "‘경계’", " 경계 단계", "경보 경계", "alert level warning")) and any(x in title for x in ("상향", "발령", "raised", "declared")):
            return ("php_korea_response", "warning_elevated_reported")
        if any(x in title for x in ("'주의'", "‘주의’", " 주의 단계", "경보 주의", "alert raised to caution")) and any(x in title for x in ("상향", "발령", "raised")):
            return ("php_korea_response", "caution_elevated_20261022")
        if any(x in title for x in ("의무 점검", "점검 의무화", "패치 의무화", "mandatory patch", "mandatory inspection")) and any(x in title for x in ("시행", "확정", "명령", "의무화", "ordered", "enacted")):
            return ("php_korea_response", "mandatory_remediation_reported")
        if "종합대책" in title and any(x in title for x in ("확정", "발표", "공표", "시행")) and not any(x in title for x in ("예정", "검토", "마련할", "계획", "추진")):
            return ("php_korea_response", "comprehensive_plan_released_reported")
        if any(x in title for x in ("추가 예산 확정", "보안 예산 편성", "긴급 지원금 확정")):
            return ("php_korea_response", "funding_announced_reported")
        if "종합대책" in title and any(x in title for x in ("마련할", "마련 필요", "검토", "준비", "계획", "추진")):
            return ("php_korea_response", "comprehensive_plan_proposed_20261023")
        return None

    # Original Oct-21 collaboration is not a finished Sentry deployment.
    if (
        "crowdstrike" in context and "nvidia" in context
        and any(x in context for x in ("falcon guardian", "openshell", "sentry", "bluefield-4"))
    ):
        if any(x in title for x in (
            "terminates falcon guardian integration", "ends openshell partnership",
            "cancels sentry integration", "partnership terminated", "협력 종료", "연동 중단",
        )):
            return ("crowdstrike_nvidia_guardian", "integration_ended_reported")
        if any(x in title for x in (
            "signs paid", "paid enterprise deployment", "paid customer contract",
            "wins enterprise contract", "commercial contract signed",
            "유료 고객 계약 체결", "상용 보안 계약 수주",
        )) and not any(x in title for x in ("may ", "could ", "plans to", "expected to")):
            return ("crowdstrike_nvidia_guardian", "paid_customer_reported")
        if any(x in title for x in (
            "sentry integration completed", "sentry integration now live",
            "deploys falcon guardian on bluefield", "hardware enforcement now available",
            "in-silicon enforcement generally available", "sentry 연동 완료",
        )) and not any(x in title for x in ("will ", "plans", "expected", "may ", "could ")):
            return ("crowdstrike_nvidia_guardian", "sentry_live_reported")
        if any(x in title for x in (
            "openshell integration now available", "falcon guardian generally available",
            "falcon guardian openshell ga", "openshell integration goes live",
            "falcon guardian openshell production release", "openshell 상용 통합 완료",
        )) and not any(x in title for x in ("will ", "plans", "expected", "may ", "could ")):
            return ("crowdstrike_nvidia_guardian", "openshell_available_reported")
        return ("crowdstrike_nvidia_guardian", "integration_announced")

    # Separate existing civil subpoenas from a later formal complaint,
    # consent order or closure. News attribution is never an FTC ruling.
    if (
        re.search(r"\bftc\b", context)
        and ("openai" in title or "anthropic" in title)
        and any(x in context for x in ("ai", "model", "agent", "consumer", "safety"))
    ):
        subject = (
            "both" if "openai" in title and "anthropic" in title
            else "openai" if "openai" in title else "anthropic"
        )
        event = f"ftc_ai_safety_{subject}"
        if any(x in title for x in (
            "probe closed", "investigation closed", "drops investigation",
            "closes investigation", "dismisses complaint", "investigation ends",
        )):
            return event, "investigation_closed_reported"
        if any(x in title for x in (
            "consent order", "consent decree", "settles", "settlement",
            "agrees to pay fine", "agrees to pay penalty",
        )):
            return event, "settlement_reported"
        if any(x in title for x in (
            "ftc sues", "ftc files complaint", "ftc charges",
            "ftc formally charges", "ftc brings lawsuit",
        )):
            return event, "formal_complaint_reported"
        if any(x in title for x in (
            "subpoena", "civil investigative demand",
        )):
            if any(x in title for x in (
                "could subpoena", "may subpoena", "might subpoena",
                "urges subpoena", "urges ftc to subpoena",
            )):
                return None
            return event, "subpoenas_reported"
        return None

    if re.search(r"\bcohere\b", context) and re.search(r"\baisle\b", context):
        # Do not misclassify an LOI, a proposed purchase, or a CNBC interview
        # as a definitive deal or a real-world security incident.
        if any(x in title for x in (
            "deal terminated", "acquisition terminated", "calls off acquisition",
            "ends acquisition", "abandons acquisition", "deal collapses",
            "인수 철회", "인수 무산",
        )):
            return ("cohere_aisle", "terminated_reported")
        if any(x in title for x in (
            "completes acquisition", "completed acquisition", "acquisition completed",
            "acquisition closed", "closes acquisition", "deal closed",
            "transaction completed", "인수 완료", "인수 종결",
        )) and not any(x in title for x in ("expected to", "could", "may ", "plans to")):
            return ("cohere_aisle", "closed_reported")
        if any(x in title for x in (
            "regulatory clearance", "antitrust clearance",
            "regulators approve acquisition", "regulatory approval granted",
            "인수 승인",
        )):
            return ("cohere_aisle", "regulatory_approval_reported")
        if any(x in title for x in (
            "signs definitive agreement", "signed definitive agreement",
            "definitive acquisition agreement", "agrees to acquire aisle",
            "agreed to acquire aisle", "reaches deal to buy aisle",
            "인수 본계약 체결",
        )) and not any(x in title for x in ("could", "may ", "expected", "plans", "talks")):
            return ("cohere_aisle", "definitive_agreement_reported")
        if any(x in title for x in (
            "launches commercial aisle service", "commercially launches aisle",
            "cohere cyber launches aisle", "cohere launches aisle security",
            "aisle paid security contract", "cohere cyber signs paying customer",
            "유료 보안 서비스 출시", "상용 서비스 출시",
        )) and not any(x in title for x in ("plans to", "could", "may ", "expects to")):
            return ("cohere_aisle", "commercial_service_reported")
        if any(x in context for x in (
            "letter of intent", "signed an loi", "signs loi", "signed loi",
            "intent to acquire aisle", "proposed acquisition", "plans to acquire aisle",
            "to buy aisle", "to acquire aisle", "aisle acquisition", "acquisition of aisle",
            "cohere aisle acquisition", "aisle 인수", "인수 의향서",
        )):
            return ("cohere_aisle", "letter_of_intent_announced")
        return None

    if "softbank" in context and "allied universal" in context:
        if not any(x in context for x in (
            "acquisition", "acquire", "takeover", "merger", "buy", "bid",
            "deal", "인수", "robot deployment", "security robot deployment",
        )):
            return None
        if any(x in title for x in (
            "talks collapse", "talks collapsed", "talks end", "talks ended",
            "calls off", "walks away", "abandoned acquisition",
            "acquisition terminated", "deal terminated", "인수 협상 결렬",
        )):
            return ("softbank_allied", "talks_ended_reported")
        if any(x in title for x in (
            "completes acquisition", "completed acquisition",
            "closes acquisition", "closed acquisition",
            "acquisition completed", "acquisition closed", "deal closes",
            "인수 완료", "인수 종결",
        )):
            return ("softbank_allied", "closed_reported")
        if any(x in title for x in (
            "regulatory", "antitrust", "ftc ", "justice department",
        )) and any(x in title for x in (
            "approval", "clearance", "approved", "cleared", "clears",
        )):
            return ("softbank_allied", "regulatory_clearance_reported")
        if any(x in title for x in (
            "signs definitive", "signed definitive", "definitive agreement",
            "agrees to buy", "agreed to buy", "agrees to acquire",
            "agreed to acquire", "signed acquisition agreement",
            "signs deal to buy", "signs deal to acquire",
            "reaches deal to buy", "reaches agreement to buy",
            "인수 본계약", "인수 계약 체결",
        )) and not any(x in title for x in (
            "could sign", "may sign", "expected to sign", "talks to sign",
        )):
            return ("softbank_allied", "signed_reported")
        if any(x in title for x in (
            "begins deploying security robots", "deploys security robots",
            "launches robot security service", "begins robot patrols",
            "로봇 보안서비스 상용화",
        )) and any(x in context for x in ("customer", "security", "deployment", "contract", "고객", "배치")):
            return ("softbank_allied", "operational_deployment_reported")
        if any(x in title for x in (
            "exclusive talks", "exclusive negotiations", "advanced talks",
            "advanced negotiations", "enters exclusive", "독점 협상", "협상 진전",
        )):
            return ("softbank_allied", "advanced_talks_reported")
        if any(x in context for x in (
            "acquisition", "acquire", "takeover", "merger", "buy",
            "bid", "deal", "인수",
        )):
            return ("softbank_allied", "initial_talks_reported")
        return None

    if "anthropic" in context and any(x in context for x in (
        "ai safety bill", "frontier ai safety bill",
        "frontier ai legislation", "ai safety legislation",
        "인공지능 안전 법안", "ai 안전 법안",
    )):
        if any(x in title for x in (
            "bill withdrawn", "withdraws safety bill", "bill abandoned",
            "bill shelved", "법안 철회",
        )):
            return ("anthropic_frontier_bill", "withdrawn_reported")
        if any(x in title for x in (
            "signed into law", "enacted into law", "bill becomes law",
            "bill enacted", "법률 공포", "법안 발효",
        )):
            return ("anthropic_frontier_bill", "enacted_reported")
        if any(x in title for x in (
            "passes congress", "clears congress",
            "passes both chambers", "clears both chambers",
        )):
            return ("anthropic_frontier_bill", "passed_congress_reported")
        if re.search(
            r"(?:house|senate).{0,45}(?:passes|passed|approves|approved)"
            r"|(?:passes|passed|approved).{0,45}(?:house|senate)",
            title,
        ):
            return ("anthropic_frontier_bill", "passed_chamber_reported")
        if "committee" in title and any(x in title for x in (
            "advances", "advanced", "approves", "approved", "votes to",
        )):
            return ("anthropic_frontier_bill", "committee_advanced_reported")
        if any(x in title for x in (
            "introduced in congress", "introduced in the house",
            "introduced in the senate", "formally introduced",
            "bill filed in congress", "bill filed in the house",
            "bill filed in the senate", "정식 발의", "법안 발의",
        )):
            return ("anthropic_frontier_bill", "introduced_reported")
        if any(x in title for x in (
            "releases draft text", "publishes draft bill",
            "publishes bill text", "releases proposed bill text",
            "법안 초안 전문 공개",
        )):
            return ("anthropic_frontier_bill", "draft_text_published_reported")
        if any(x in title for x in (
            "revises draft bill", "revises safety bill", "amends draft bill",
            "updates safety bill proposal", "threshold revised",
            "초안 수정", "법안 초안 수정",
        )):
            return ("anthropic_frontier_bill", "draft_revised_reported")
        # Pitched proposals / repeats remain a historical baseline.
        return ("anthropic_frontier_bill", "private_draft_reported")
    return None


def tracked_policy_event_key(item: dict) -> str | None:
    stage = tracked_policy_event_stage(item)
    return f"{stage[0]}:{stage[1]}" if stage else None


def detect_category(text: str) -> str:
    low = text.lower()
    if re.search(r"\bftc\b", low) and ("openai" in low or "anthropic" in low) and any(
        t in low for t in ("subpoena", "complaint", "investigation", "sues", "settlement", "consent order")
    ):
        return "FTC 프런티어 AI 소비자보호 조사·집행 단계"
    business = php_business_event_stage({"title": text})
    if business:
        return {
            "infra172": "민간 기반시설 172개 보안 점검·조달 단계",
            "piolink_mdr": "파이오링크 관리형 탐지·대응 상용화 단계",
            "piolink_php": "파이오링크 PHP 보안 점검 사업화 단계",
            "estsecurity_php": "이스트시큐리티 PHP 점검 도구·유료 전환 단계",
            "sga_php": "SGA솔루션즈 PHP 가상패치 사업화 단계",
            "axgate_php": "엑스게이트 PHP 방화벽 수주 검증 단계",
        }[business[0]]
    commercial_stage = k_security_business_stage({"title": text})
    if commercial_stage:
        return {
            "genians_nexus": "지니언스 AI 보안 운영 자동화·사업화 단계",
            "ksign_evsec": "케이사인 충전 인프라 AI 취약점 검사·사업화 단계",
            "ksign_sandslab": "샌즈랩·네이버클라우드 보안 특화 AI 사업화 단계",
        }[commercial_stage[0]]
    if is_php_korea_policy({"title": text}):
        return "국내 PHP 보안위기 대응·정책 단계"
    if "cohere" in low and re.search(r"\baisle\b", low):
        return "Cohere–AISLE AI 보안 인수·상용화 단계"
    if "crowdstrike" in low and "nvidia" in low and any(x in low for x in ("falcon guardian", "openshell", "sentry", "bluefield-4")):
        return "CrowdStrike–NVIDIA AI 에이전트 보안 통합 단계"
    if "softbank" in low and "allied universal" in low:
        return "SoftBank–Allied Universal 물리보안·로봇 인수 단계"
    if "anthropic" in low and any(x in low for x in (
        "ai safety bill", "frontier ai safety bill", "frontier ai legislation",
        "ai safety legislation", "인공지능 안전 법안", "ai 안전 법안",
    )):
        return "Anthropic 프런티어 AI 안전법안 입법 단계"
    if trail_of_bits_mna_stage({"title":text,"source":"The Information"}):
        return "OpenAI–Trail of Bits 인수·계약 단계"
    if "trail of bits" in low and "patch the planet" in low:
        return "OpenAI–Trail of Bits 취약점 수정 사업화"
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
    if re.search(r"\bftc\b", low) and ("openai" in low or "anthropic" in low) and any(
        t in low for t in ("subpoena", "complaint", "investigation", "sues", "settlement", "consent order")
    ):
        if "openai" in low and "anthropic" in low:
            return "FTC–OpenAI·Anthropic"
        return "FTC–OpenAI" if "openai" in low else "FTC–Anthropic"
    business = php_business_event_stage({"title": text})
    if business:
        return {
            "infra172": "과학기술정보통신부",
            "piolink_mdr": "파이오링크",
            "piolink_php": "파이오링크",
            "estsecurity_php": "이스트시큐리티",
            "sga_php": "SGA솔루션즈",
            "axgate_php": "엑스게이트",
        }[business[0]]
    commercial_stage = k_security_business_stage({"title": text})
    if commercial_stage:
        return {
            "genians_nexus": "지니언스",
            "ksign_evsec": "케이사인",
            "ksign_sandslab": "샌즈랩·네이버클라우드(케이사인 관계)",
        }[commercial_stage[0]]
    if is_php_korea_policy({"title": text}):
        return "과학기술정보통신부·한국인터넷진흥원"
    if "cohere" in low and re.search(r"\baisle\b", low):
        return "Cohere–AISLE"
    if "crowdstrike" in low and "nvidia" in low and any(x in low for x in ("falcon guardian", "openshell", "sentry", "bluefield-4")):
        return "CrowdStrike–NVIDIA"
    if "softbank" in low and "allied universal" in low:
        return "SoftBank–Allied Universal"
    if "anthropic" in low and any(x in low for x in (
        "ai safety bill", "frontier ai safety bill", "frontier ai legislation",
        "ai safety legislation", "인공지능 안전 법안", "ai 안전 법안",
    )):
        return "Anthropic AI 안전법안"
    if "openai" in low and "trail of bits" in low:
        return "OpenAI–Trail of Bits"
    mapping = (
        ("백악관 Super Intelligence Force", (
            "super intelligence force", "si force", "anthropic breaches spark white house ai reporting mandate",
        )),
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


def is_reported_si_original(item: dict) -> bool:
    """The original Axios report is handled by the existing SIF stage monitor."""
    text = f"{item.get('title','')} {item.get('description','')}".lower()
    return (
        "anthropic breaches spark white house ai reporting mandate" in text
        or "axios.com/2026/10/09/anthropic-ai-security-white-house" in str(item.get("url", "")).lower()
    )


def is_patch_the_planet_original(item: dict) -> bool:
    url = (item.get("url") or "").lower()
    title = (item.get("title") or "").lower()
    return (
        "openai.com/index/patch-the-planet/" in url
        or "trailofbits.com/2026/06/22/introducing-patch-the-planet" in url
        or "introducing patch the planet" in title
    )


def material(item: dict) -> bool:
    if is_patch_the_planet_original(item):
        return False
    if is_anthropic_mission_launch_baseline(item) or is_reported_si_original(item):
        return False
    milestone = tracked_policy_event_stage(item)
    if milestone:
        if milestone[0] in ("infra172", "piolink_mdr", "piolink_php", "estsecurity_php", "sga_php", "axgate_php") and not php_business_publisher_verified(item):
            return False
        if milestone[0] in ("genians_nexus", "ksign_evsec", "ksign_sandslab") and not k_security_business_publisher_verified(item):
            return False
        if milestone[0] == "cohere_aisle" and not cohere_aisle_publisher_verified(item):
            return False
        if milestone[0] == "php_korea_response" and not php_korea_publisher_verified(item):
            return False
        if milestone[0] == "crowdstrike_nvidia_guardian" and not crowdstrike_nvidia_publisher_verified(item):
            return False
        return source_trusted(item.get("source", ""))
    stage = trail_of_bits_mna_stage(item)
    if stage:
        # 2026-10-13 The Information initial talks are a historical,
        # unconfirmed baseline. They are neither a definitive contract nor
        # a completed acquisition; alerts resume only on a new stage.
        if stage == "initial_talks":
            return False
        return source_trusted(item.get("source", ""))
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
    out["official"] = (source_official(item.get("source","")) and
        cohere_aisle_publisher_verified(item) and crowdstrike_nvidia_publisher_verified(item)
        and php_korea_publisher_verified(item)
        and k_security_business_publisher_verified(item)
        and k_security_business_official(item)
        and php_business_publisher_verified(item))
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
                item_milestone = tracked_policy_event_key(item)
                existing_milestone = tracked_policy_event_key(rep)
                if item_milestone or existing_milestone:
                    # Never merge a signed/closed/withdrawn legal milestone into
                    # the headline of a different stage, then checkpoint both.
                    # Articles for the SAME stage are one event regardless
                    # of different newspaper headlines.
                    match = bool(item_milestone and item_milestone == existing_milestone)
                else:
                    match = similarity(rep.get("title",""), item.get("title","")) >= 0.18
                if match:
                    cluster.append(item)
                    placed = True
                    break
        if not placed:
            clusters.append([item])
    return clusters



def select_policy_alert_events(items: list[dict]) -> tuple[list[list[dict]], set[str], int]:
    """Select a bounded alert batch and preserve unreported events for retry."""
    all_events = cluster_events(items)
    selected = all_events[:MAX_ALERT_EVENTS]
    deferred_fingerprints = {
        item["fingerprint"]
        for cluster in all_events[MAX_ALERT_EVENTS:]
        for item in cluster
    }
    return selected, deferred_fingerprints, len(all_events) - len(selected)


def source_label(source: str) -> str:
    low = source.lower()
    mapping = (
        ("white house","백악관"), ("house of representatives","미 하원"),
        ("u.s. house","미 하원"), ("associated press","AP"), ("ap news","AP"),
        ("the information","The Information"), ("trail of bits","Trail of Bits"),
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
    """Translate ordinary words without letting a service rename companies."""
    value = " ".join(strip_html(text).split())
    if not _needs_korean_translation(value):
        return value

    protected = sorted(
        (*ALERT_IDENTIFIER_TERMS,
         "Anthropic Cyber Mission", "Critical Infrastructure Defense Program",
         "OSS Scanner", "CIDP"),
        key=len, reverse=True,
    )
    pattern = "(" + "|".join(re.escape(term) for term in protected) + ")"
    parts = re.split(pattern, value, flags=re.I)
    canonical = {x.lower(): x for x in protected}
    assembled = []
    errors = []
    for part in parts:
        if not part:
            continue
        if part.lower() in canonical:
            assembled.append(canonical[part.lower()])
            continue
        if not LATIN_WORD_RE.search(part):
            assembled.append(part)
            continue
        result = ""
        for translator in (_translate_google, _translate_mymemory):
            for _attempt in range(2):
                try:
                    candidate = " ".join(strip_html(translator(part)).split())
                    if candidate and HANGUL_RE.search(candidate):
                        result = candidate
                        break
                    errors.append(f"{translator.__name__}: no Hangul")
                except Exception as exc:
                    errors.append(f"{translator.__name__}: {type(exc).__name__}: {exc}")
            if result:
                break
        if not result:
            raise RuntimeError("Korean translation failed: " + " | ".join(errors[-4:]))
        assembled.append(
            (" " if part[0].isspace() else "") + result
            + (" " if part[-1].isspace() else "")
        )
    rendered = " ".join("".join(assembled).split())
    if "anthropic" in value.lower() and "인류학" in rendered:
        raise RuntimeError("Anthropic company name was mistranslated")
    return rendered

def concise_fact(item: dict) -> str:
    title = re.sub(r"\s+-\s+[^-]{1,40}$", "", item.get("title","")).strip()
    title = re.sub(
        r"^(?:Anthropic News|Anthropic Research|OpenAI Alignment)[ \t]*:[ \t]*",
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
        if rep["category"] in (
            "민간 기반시설 172개 보안 점검·조달 단계",
            "파이오링크 관리형 탐지·대응 상용화 단계",
            "파이오링크 PHP 보안 점검 사업화 단계",
            "이스트시큐리티 PHP 점검 도구·유료 전환 단계",
            "SGA솔루션즈 PHP 가상패치 사업화 단계",
            "엑스게이트 PHP 방화벽 수주 검증 단계",
        ):
            stage = php_business_event_stage(rep)
            lines.append(f"• <b>새 진행 단계</b>: {html.escape(stage[1] if stage else '확인 필요')} · 시장 테마·무료 점검·유료 계약 구분")
            if stage and stage[0] == "infra172":
                lines.append("• <b>기존 기준선</b>: 111개 기관·약 172개 민간 기반시설 점검. 연말 완료 목표, 신규 발주예산·낙찰사는 아직 확인되지 않음")
            elif stage and stage[0] == "piolink_mdr":
                lines.append("• <b>기존 기준선</b>: 다중 제조사 단말 탐지·대응을 결합한 관리형 탐지·대응 사업 확대. 추가 유료 고객·계약금액·정기 갱신은 미확인")
            elif stage and stage[0] == "estsecurity_php":
                lines.append("• <b>기존 기준선</b>: PHP2Shell 무료 점검 도구 공개. 서버·원격·컨테이너·이미지 4가지 검사 지원. 무료 배포를 매출로 계산하지 않음")
            else:
                lines.append("• <b>기존 기준선</b>: PHP 보안 테마 반응·무료 점검·임시 패치 지원과 신규 유료 공급계약은 별개")
            lines.append("• <b>수익 확인</b>: 계약고객·원화 계약액·검수·구독료·관리형 관제 월 과금·장기 유지보수 계약·갱신률")
        elif rep["category"] in (
            "지니언스 AI 보안 운영 자동화·사업화 단계",
            "케이사인 충전 인프라 AI 취약점 검사·사업화 단계",
            "샌즈랩·네이버클라우드 보안 특화 AI 사업화 단계",
        ):
            stage = tracked_policy_event_stage(rep)
            labels = {
                "paid_customer_contract_reported": "유료 고객 공급계약 보도",
                "customer_pilot_reported": "고객 실증·유료 검증 보도",
                "production_live_reported": "고객 현장 상용 운영 개시 보도",
            }
            detail = labels.get(stage[1], "과거 공개 사업 재확인") if stage else "사업 단계 추가 검증"
            lines.append(f"• <b>신규 단계</b>: {html.escape(detail)} · 공급계약 원문과 실제 매출을 별도 확인")
            if stage and stage[0] == "genians_nexus":
                lines.append("• <b>기존 기준선</b>: 2026년 9월 16일 Nexus Framework 개발 완료·GISEC 공개. 종전 NAC·EDR 유료 매출을 새 플랫폼 신규 매출로 오인 금지")
            elif stage and stage[0] == "ksign_evsec":
                lines.append("• <b>기존 기준선</b>: 2026년 10월 20일 충전 인프라 취약점 분석 솔루션 시연 발표. 시연은 유료 계약 아님")
            else:
                lines.append("• <b>기존 기준선</b>: 2026년 9월 3일 네이버클라우드 AI 보안 컨소시엄 선정. 샌즈랩은 케이사인 종속회사이나 케이사인 본체 직접 계약과 구분")
            lines.append("• <b>실적 확인</b>: 개별 고객·계약액·검수·유료 운영 대수·유지보수·사용권 갱신·현금 회수·재계약 여부")
        elif rep["category"] == "국내 PHP 보안위기 대응·정책 단계":
            stage = tracked_policy_event_stage(rep)
            labels = {
                "warning_elevated_reported": "사이버위기 경보 경계 상향 보도",
                "critical_elevated_reported": "사이버위기 경보 심각 상향 보도",
                "warning_lowered_reported": "사이버위기 경보 하향 보도",
                "warning_lifted_reported": "사이버위기 경보 해제 보도",
                "mandatory_remediation_reported": "보안 점검·수정 의무화 보도",
                "comprehensive_plan_released_reported": "범부처 종합대책 발표 보도",
                "funding_announced_reported": "PHP 취약점 대응 예산 편성 보도",
            }
            detail = labels.get(stage[1], "정부 추가 대응") if stage else "정부 추가 대응"
            lines.append(f"• <b>신규 정책 단계</b>: {html.escape(detail)} · 공식 정부 문서의 실제 시행 여부 별도 검증")
            lines.append("• <b>기존 기준선</b>: 10월 22일 관심→주의, 10월 23일 종합대책 검토 발언은 재발송하지 않음")
            lines.append("• <b>다음 확인</b>: 과기정통부·KISA 공식 경보·법적 의무·대상·기한·예산·조달·실제 침해 규모")
        elif rep["category"] == "CrowdStrike–NVIDIA AI 에이전트 보안 통합 단계":
            stage = tracked_policy_event_stage(rep)
            labels = {
                "integration_announced": "협력 확대 공식 발표",
                "openshell_available_reported": "OpenShell 정식 연동 출시 보도",
                "sentry_live_reported": "Sentry 반도체 연동 완료 보도",
                "paid_customer_reported": "유료 기업고객 계약 보도",
                "integration_ended_reported": "협력 종료 보도",
            }
            detail = labels.get(stage[1], "추가 검증") if stage else "추가 검증"
            lines.append(f"• <b>신규 단계</b>: {html.escape(detail)} · 당사자 공식 발표와 미래 계획을 분리")
            lines.append("• <b>기술 단계</b>: Falcon Guardian의 NVIDIA OpenShell 통합은 진행 중. NVIDIA Sentry·BlueField-4 반도체 정책 강제 연동은 계획 단계이며 고객 현장 가동 확정 아님")
            lines.append("• <b>수익구조</b>: 소프트웨어 사용권·유료 기업고객·반복 갱신과 추가 DPU 출하가 실제 확인될 때만 증분 매출로 집계. 계약금액·유료 고객 수·양산 물량 미공개")
            lines.append("• <b>다음 확인</b>: OpenShell 정식 출시·Sentry 실장·고객 승인·실제 보안 차단·유료계약·신규 출하·유지보수·오탐·성능 비용")
        elif rep["category"] == "Cohere–AISLE AI 보안 인수·상용화 단계":
            milestone = tracked_policy_event_stage(rep)
            detail = milestone[1].replace("_", " ") if milestone else "추가 검증"
            verification = "당사자 공식 발표" if rep.get("official") else "신뢰보도 · 공식 발표와 별도 검증"
            lines.append(f"• <b>신규 단계</b>: {html.escape(detail)} · {verification}")
            lines.append("• <b>기준선</b>: 2026년 10월 15일 Cohere·AISLE 인수 의향서 체결. 본계약·인수 종결 아님, 거래금액 미공개")
            lines.append("• <b>기술·매출</b>: AISLE의 취약점 발견·악용 가능성 검증·자동수정·MCP 연동·패키지 방화벽과 Cohere North의 기업용 보안 운영을 구분. 유료 계약·반복매출은 개별 확인 필요")
            lines.append("• <b>다음 확인</b>: 본계약·인수 완료·거래금액·고객 검증·실제 배치·유료 사용권·구독 갱신·품질·오탐 및 접근권한 위험")
        elif rep["category"] == "SoftBank–Allied Universal 물리보안·로봇 인수 단계":
            stage = tracked_policy_event_stage(rep)
            detail = stage[1].replace("_", " ") if stage else "추가 검증"
            lines.append(f"• <b>신규 단계</b>: {html.escape(detail)} · 신뢰보도 단계이며 당사자 공식 확정과 구분")
            lines.append("• <b>사업 구조</b>: 기존 Allied Universal의 데이터센터 현장 경비·출입통제·원격관제 및 로봇 서비스를 인수 협상과 분리. 미체결 거래를 연결매출로 인정하지 않음")
            lines.append("• <b>다음 확인</b>: 본계약·차입과 승계부채·반독점 승인·거래종결·실제 로봇 배치·보안 인력 비용·반복 계약")
        elif rep["category"] == "FTC 프런티어 AI 소비자보호 조사·집행 단계":
            stage = tracked_policy_event_stage(rep)
            detail = stage[1].replace("_", " ") if stage else "추가 검증"
            lines.append(f"• <b>신규 단계</b>: {html.escape(detail)} · 보도 단계이며 공식 FTC 처분과 구분")
            lines.append("• <b>법적 구분</b>: 민사 소환장·자료 제출 요구는 위법 확정·모델 출시 중단·과징금 부과가 아님")
            lines.append("• <b>다음 확인</b>: FTC 사건번호·공식 소장·청문회·명령·합의·제재금·회사 대응·영업 영향")
        elif rep["category"] == "Anthropic 프런티어 AI 안전법안 입법 단계":
            stage = tracked_policy_event_stage(rep)
            detail = stage[1].replace("_", " ") if stage else "추가 검증"
            lines.append(f"• <b>신규 단계</b>: {html.escape(detail)} · 보도 단계. 의회 법안번호·공식 발의·입법 및 시행과 분리")
            lines.append("• <b>기존 초안</b>: 10월 16일 Politico 보도상 중대한 피해 기준·독립 평가·평가 후 72시간 이내 통지 제안. 확정 법률 아님")
            lines.append("• <b>다음 확인</b>: Anthropic 초안 전문·의회 공식 법안번호·소관 위원회·찬반·통과·시행일·규제기관 권한")
        elif rep["category"] == "OpenAI–Trail of Bits 인수·계약 단계":
            lines.append("• <b>계약 검증</b>: 초기 협상·독점 협상·언론의 계약 보도·발행사 본계약·거래종결·협상 결렬을 단계별로 분리. 공식 발표 없으면 계약 확정으로 표기 금지")
            lines.append("• <b>매출 경로</b>: 기존 Patch the Planet 공동 프로젝트와 향후 인수 후 유료 보안검사·취약점 검증·수정 서비스 수익을 구분. 인수가격·계약금액은 직접 확인된 경우에만 표시")
        elif rep["category"] == "OpenAI–Trail of Bits 취약점 수정 사업화":
            lines.append("• <b>의미</b>: 공동 무료 연구·오픈소스 지원과 실제 유료 사용권·보안 검증·유지보수·고객 계약을 구분")
        elif rep["category"] == "미국 AI 사고 신고·시정 요구 발표":
            lines.append("• <b>현재 단계</b>: 백악관 Super Intelligence Force 발언·요구 보도. 법률·최종 규정 성문화 여부는 별도 확인")
            lines.append("• <b>다음 확인</b>: 사고 유형·신고 대상·기한·수신 기관·정부 공식 고시·집행 근거·벌칙·실제 시정조치")
        elif rep["category"] == "Anthropic 핵심 기반시설·오픈소스 방어 사업":
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
            fetched = parse_google_news(query, now)
            raw.extend(fetched)
            if ("SoftBank" in query and "Allied Universal" in query) or (
                "Anthropic" in query and ("AI safety bill" in query or ("frontier AI" in query and "bill" in query))
            ):
                relevant = sum(bool(tracked_policy_event_stage(item)) for item in fetched)
                print(f"ai_policy_new_topic_feed total={len(fetched)} relevant={relevant}")
        except Exception as exc:
            errors.append(f"Google News 실패: {query[:55]} / {type(exc).__name__}: {exc}")

    # Official CrowdStrike Oct-21 announcement, with stable stage dedup.
    raw.append({
        "kind": "official",
        "query": "CrowdStrike first-party Falcon Guardian OpenShell announcement",
        "title": "CrowdStrike and NVIDIA Expand AI Agent Security from Software to Silicon",
        "description": "Falcon Guardian integrating with NVIDIA OpenShell software; NVIDIA Sentry BlueField-4 in-silicon enforcement integration planned, not yet a production deployment or paid contract",
        "source": "CrowdStrike",
        "publisher_url": "https://ir.crowdstrike.com/",
        "url": "https://ir.crowdstrike.com/news-releases/news-release-details/crowdstrike-and-nvidia-expand-ai-agent-security-software-silicon",
        "published_at": "2026-10-21T00:00:00+00:00",
    })

    normalized = {}
    for row in raw:
        item = normalize(row)
        if material(item):
            normalized[item["fingerprint"]] = item
    current = list(normalized.values())

    seen = prune_seen(dict(state.get("seen") or {}), now)
    trail_mna_seen = dict(state.get("trail_of_bits_mna_seen") or {})
    tracked_stages = dict(state.get("tracked_policy_event_stages") or {})
    for baseline_key, baseline_info in POLICY_EVENT_BASELINES.items():
        tracked_stages.setdefault(baseline_key, dict(baseline_info))
    # Correct the issuer-verification status of the previously sent official
    # collaboration announcement; this is NOT a new stage or resend.
    recorded = tracked_stages.get("crowdstrike_nvidia_guardian:integration_announced")
    if (isinstance(recorded, dict) and recorded.get("source") == "CrowdStrike"
        and str(recorded.get("source_url") or "").startswith("https://ir.crowdstrike.com/")):
        recorded["status"] = "issuer_official_announced_openshell_integrating_sentry_planned"
    trail_mna_seen.setdefault("initial_talks", {
        "source_url": "https://www.theinformation.com/articles/openai-early-talks-buy-security-startup-trail-bits",
        "status": "The Information 2026-10-13 reported early talks; unconfirmed",
    })
    trail_mna_seen.setdefault("existing_partnership", {
        "source_url": "https://openai.com/index/patch-the-planet/",
        "status": "2026-06-22 confirmed Patch the Planet collaboration; no acquisition",
    })
    new_items = []
    for item in current:
        if item["fingerprint"] in seen:
            continue
        tracked_key = tracked_policy_event_key(item)
        if tracked_key:
            if tracked_key in tracked_stages:
                continue
            new_items.append(item)
            continue
        stage = trail_of_bits_mna_stage(item)
        if stage:
            if stage in trail_mna_seen:
                continue
            trail_mna_seen[stage] = {
                "source_url": item.get("url"),
                "source": item.get("source"),
                "status": "official" if source_official(item.get("source","")) else "reported_not_confirmed",
                "first_seen_at": now.isoformat(),
            }
            new_items.append(item)
            continue
        if previously_similar(item, seen):
            continue
        new_items.append(item)

    # Track direct official page changes separately.
    # Snapshot extraction rules are versioned. Published reference documents
    # never alert on in-place HTML changes, and mutable pages require a stable
    # changed digest across multiple observations separated by time.
    official_pages = dict(state.get("official_pages") or {})
    official_page_skips: list[str] = []
    prior_snapshot_schema = int(state.get("official_snapshot_schema_version") or 0)
    rebaseline_official_pages = prior_snapshot_schema != OFFICIAL_SNAPSHOT_SCHEMA_VERSION
    try:
        snapshots = official_page_snapshots(skipped=official_page_skips)
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

    events, deferred_fingerprints, deferred_event_count = select_policy_alert_events(new_items)
    # Only a selected event becomes an acknowledged milestone. Deferred
    # milestones are retried on the next run, without losing state.
    for cluster in events:
        for item in cluster:
            tracked_key = tracked_policy_event_key(item)
            if tracked_key:
                tracked_stages.setdefault(tracked_key, {
                    "source_url": item.get("url"),
                    "source": item.get("source"),
                    "first_seen_at": now.isoformat(),
                    "status": "issuer_official" if item.get("official") else "trusted_report_not_issuer_or_legislative_confirmation",
                })
    first_seen = now.isoformat()
    for item in current:
        if item["fingerprint"] in deferred_fingerprints:
            continue
        seen.setdefault(item["fingerprint"], {
            "title":item["title"], "source":item["source"], "url":item["url"],
            "entity":item["entity"], "category":item["category"],
            "published_at":item.get("published_at"), "first_seen_at":first_seen,
        })

    pending = {
        "initialized": True,
        "updated_at_kst": now.astimezone(KST).isoformat(timespec="seconds"),
        "seen": seen,
        "trail_of_bits_mna_seen": trail_mna_seen,
        "tracked_policy_event_stages": tracked_stages,
        "official_pages": official_pages,
        "official_snapshot_schema_version": OFFICIAL_SNAPSHOT_SCHEMA_VERSION,
        "openshell_telemetry": openshell_telemetry,
        "last_collection": {
            "raw_items":len(raw),
            "material_items":len(current),
            "new_articles":len(new_items),
            "new_events":len(events),
            "deferred_events":deferred_event_count,
            "official_page_skips":official_page_skips,
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
        f"- 한도 초과 다음 회차 이월 사건: {deferred_event_count}건",
        f"- 공식문서 접근 누락: {len(official_page_skips)}건",
        f"- 오류: {len(errors)}건",
    ]
    if official_page_skips:
        status += ["", "## 원천 접근 제한"] + [f"- {x}" for x in official_page_skips[:10]]
    if errors:
        status += ["", "## 오류"] + [f"- {x}" for x in errors[:10]]
    STATUS_PATH.write_text("\n".join(status)+"\n",encoding="utf-8")
    print(
        f"ai_policy_baseline={str(baseline).lower()} material={len(current)} "
        f"new_articles={len(new_items)} new_events={len(events)} "
        f"official_page_skips={len(official_page_skips)} errors={len(errors)}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
