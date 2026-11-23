"""2026-11-23 Eugene Research humanoid value-chain timeline.

Narrow extension for the existing ROBOTIS GitHub Actions -> Python -> Telegram
watch. Research preferences are *relative analyst opinions*, not quantitative
sales, contracts or a date-triggered stage upgrade. Never replace existing
groups, previously-delivered event keys, routes, schedules or success state.
"""
from __future__ import annotations

import datetime as dt
import hashlib
import re
from urllib.parse import urlparse

KST = dt.timezone(dt.timedelta(hours=9))
BACKFILL = "__eugene_robot_lifecycle_20261123_once__"
START = dt.date(2026, 11, 23)
END = dt.date(2026, 11, 28)  # Exclusive; no later stale replay.
GROUP = "eugene_20261123_humanoid_lifecycle"
SI_GROUP = "robot_humanoid_si_verified_headline"
TITLE = "유진투자증권 11월 23일 휴머노이드 밸류체인 선호 변화…개발용→병목부품·SI→OEM·운영"
REPORT_URL = "https://www.eugenefn.com/common/files/amail/20261123_B2030_syyang0901_576.pdf"
REPORT_KEY = hashlib.sha256(
    b"eugene|2026-11-23|humanoid|relative-segment-preference|chart|baseline"
).hexdigest()

SI_QUERIES = (
    '("삼성SDS" OR "LG CNS" OR "현대오토에버" OR "포스코DX" OR "SK AX") (휴머노이드 OR 로봇 OR "physical AI") (시스템통합 OR 설치 OR 구축 OR 운영계약 OR 유지보수 OR 현장실증)',
    '("Samsung SDS" OR "LG CNS" OR "Hyundai AutoEver" OR "POSCO DX") (humanoid OR robotics) ("systems integration" OR "service contract" OR "robot deployment" OR "managed operations")',
)
OFFICIAL_HOSTS = {
    "삼성SDS": ("samsungsds.com",),
    "Samsung SDS": ("samsungsds.com",),
    "LG CNS": ("lgcns.com",),
    "현대오토에버": ("hyundai-autoever.com",),
    "Hyundai AutoEver": ("hyundai-autoever.com",),
    "포스코DX": ("poscodx.com",),
    "POSCO DX": ("poscodx.com",),
    "SK AX": ("skax.co.kr",),
}
ROBOT = re.compile(r"휴머노이드|humanoid|피지컬\s*AI|physical\s*AI|로봇|robotics?|아틀라스|Atlas", re.I)
SI_TERM = re.compile(r"\bSI\b|시스템\s*통합|systems?\s*integration|현장\s*(?:설치|구축)|managed\s*operations|robot\s*deployment", re.I)
OPERATIONS = re.compile(r"운영\s*(?:개시|시작|계약|서비스)|유지\s*보수\s*(?:계약|수주)|장기\s*운영|서비스\s*매출|운영\s*대수|O&M|managed\s*service|after[- ]sales\s*service", re.I)
PROJECT = re.compile(r"현장\s*(?:설치|구축|실증)|시스템\s*통합|통합\s*(?:계약|수주)|SI\s*(?:수주|계약)|deployment|integrat(?:ion|or)", re.I)
ACTUAL = re.compile(r"본계약|계약\s*체결|신규\s*수주|수주\s*확정|가동\s*개시|현장\s*설치\s*완료|검수\s*완료|운영\s*개시|signed|awarded|completed|operational|deployed", re.I)
NEGATIVE = re.compile(r"미체결|계약\s*없|계약\s*전|취소|철회|해지|미완료|아직|not\s*signed|has\s*not|no\s*contract", re.I)
FUTURE = re.compile(r"예정|계획|목표|검토|논의|협의|추진|예상|전망|가능성|준비|MOU|memorandum|planning|plans?\s+to|expected|considering|may\s+sign", re.I)
REPRINT = re.compile(r"유진투자증권|Eugene\s+(?:Securities|Research)", re.I)
REPRINT_NUM = re.compile(r"787\s*만|7[,.]?87\s*million|2030.{0,30}13\s*만|2040.{0,15}로봇", re.I)
REVISED = re.compile(r"전망\s*(?:수정|상향|하향)|예상치\s*(?:수정|상향|하향)|revis(?:ed|ion)|raise[sd]?\s+forecast|cut[s]?\s+forecast", re.I)

def _local_date(item: dict):
    try:
        value = str(item.get("published") or "")
        return dt.datetime.fromisoformat(value.replace("Z", "+00:00")).astimezone(KST).date()
    except (TypeError, ValueError, OverflowError):
        return None

def _report_reprint(item: dict):
    title = str(item.get("title") or "")
    return bool(REPRINT.search(title) and REPRINT_NUM.search(title)
                and not (REVISED.search(title) and (_local_date(item) or START) > START))

def lifecycle_lens(headline: str):
    """Nonfinancial explanatory tag only. Never used to mark a contract signed."""
    title = str(headline or "")
    if not ROBOT.search(title):
        return ""
    if NEGATIVE.search(title):
        return "미체결·취소 여부 확인"
    if FUTURE.search(title):
        return "계획·협의 단계(실제 매출 아님)"
    if OPERATIONS.search(title):
        return "현장 운영·유지보수(반복 매출 계약·설치 대수 별도 확인)"
    if PROJECT.search(title):
        return "현장 구축·시스템통합(설치·검수 완료 확인)"
    if re.search(r"감속기|토크\s*센서|촉각\s*센서|force[- ]torque|정밀\s*센서|영구\s*자석|robot\s*hand|로봇\s*손|harmonic\s*drive", title, re.I):
        return "병목 부품(고객 선정·양산 수율·납기 확인)"
    if re.search(r"개발용|시제품|프로토타입|prototype|research\s*robot|PoC|개발\s*키트", title, re.I):
        return "개발용 부품·시제품(양산 이전 수요)"
    if re.search(r"양산|생산\s*능력|완제품|OEM|현장\s*배치|본격\s*출하|mass\s*production", title, re.I):
        return "완제품·인공지능(실제 출하·작업 성공률 확인)"
    return ""

def _official_si(item: dict):
    title = str(item.get("title") or "")
    text = title + " " + str(item.get("description") or "")
    source = str(item.get("source") or "")
    url = str(item.get("source_url") or "")
    host = (urlparse(url).hostname or "").lower()
    allowed = OFFICIAL_HOSTS.get(source, ())
    day = _local_date(item)
    if not allowed or day is None or day < START:
        return ""
    if not any(host == x or host.endswith("." + x) for x in allowed):
        return ""
    if not ROBOT.search(text) or not (SI_TERM.search(text) or OPERATIONS.search(title)):
        return ""
    if NEGATIVE.search(title) or FUTURE.search(title) or not ACTUAL.search(title):
        return ""
    if OPERATIONS.search(title):
        return "operations_start_or_signed"
    if PROJECT.search(title):
        return "integration_installation_contract"
    return ""

def install(base) -> None:
    if getattr(base, "_eugene_lifecycle_installed", False):
        return
    existing = {name: getattr(base, name) for name in
                ("query_news", "topic_group", "score", "key", "category",
                 "meaning", "risk", "verification", "tag_for")}
    existing_queries = set(base.QUERIES)

    def query(q):
        if q == BACKFILL:
            day = base.NOW.astimezone(KST).date()
            if not START <= day < END:
                return []
            return [{
                "title": TITLE,
                "description": (
                    "유진투자증권 양승윤 2026-11-23 산업보고서의 정성적 선호도 도표: "
                    "2026~2028 개발용 부품과 OEM·AI 우선, 양산 페이스 전환 시 개발용 "
                    "부품 상대 선호 하락; 2029~2035 감속기·센서 등 병목 부품과 "
                    "SI 프로젝트·설치 수혜 및 OEM 가격 경쟁 심화; 2036년 이후 "
                    "가정용 로봇 보급에 선도 OEM·AI 및 SI 운영 반복매출의 "
                    "상대적 선호 확대 전망. SI는 시스템 통합 업체·설치·운영 역할을 말함. "
                    "2035년 가정용 출하가 산업용을 추월하고 2040년 서비스 매출이 "
                    "하드웨어 매출을 추월한다는 도표상 전망이며 확정 시점은 아님. "
                    "기본 시나리오 세계 누적 설치 대수는 2030년 약 13만대, "
                    "2035년 170만대, 2040년 787만대(산업용 289만대·가정용 "
                    "498만대)임. 이는 증권사 추정이며 실제 계약·출하·매출이 아님. "
                    "원문 PDF 접근 제한으로 사용자 제공 도표·유진 공식 배포 요약·"
                    "독립 언론 보도로 대조했고, 선 그래프에 정량 선호 점수·"
                    "매출 성장률 단위를 붙이지 않음."
                ),
                "source": "유진투자증권 공식 배포·로봇신문",
                "source_url": "https://t.me/s/eugene2team",
                "link": REPORT_URL,
                "published": "2026-11-23T12:00:00+09:00",
                "published_precision": "day",
                "eugene_lifecycle_report": True,
            }]
        return existing["query_news"](q)

    def group(text):
        if TITLE in text:
            return GROUP
        return existing["topic_group"](text)

    def score(item):
        if item.get("eugene_lifecycle_report"):
            day = base.NOW.astimezone(KST).date()
            return 46 if START <= day < END else 0
        if _report_reprint(item):
            return 0
        if _official_si(item):
            return 36
        text = " ".join(str(item.get(k) or "") for k in ("title", "description", "source"))
        if existing["topic_group"](text) is None and ROBOT.search(text) and (
                SI_TERM.search(text) or OPERATIONS.search(text)):
            # Discovery query alone is not an official SI order.
            return 0
        return existing["score"](item)

    def key(item):
        if item.get("eugene_lifecycle_report") or _report_reprint(item):
            return REPORT_KEY
        stage = _official_si(item)
        if stage:
            title = re.sub(r"\s+", " ", str(item.get("title") or "")).casefold().strip()
            return hashlib.sha256(("robot-si|official-headline|"+stage+"|"+
                                   str(_local_date(item))+"|"+title).encode()).hexdigest()
        return existing["key"](item)

    def category(text, group_name):
        if group_name == GROUP:
            return "유진투자증권 · 휴머노이드 밸류체인 단계별 선호도 전망"
        if group_name == SI_GROUP:
            return "휴머노이드 시스템통합 · 회사 공식 제목에서 신규 단계 발견"
        return existing["category"](text, group_name)

    def topic_group(text):
        g = group(text)
        if g is not None:
            return g
        # Only recognized official-origin milestone candidates are admitted in
        # score(), not every generic 'SI robotics' news article.
        if ROBOT.search(text) and (SI_TERM.search(text) or OPERATIONS.search(text)):
            return SI_GROUP
        return None

    def meaning(cat):
        if cat == "유진투자증권 · 휴머노이드 밸류체인 단계별 선호도 전망":
            return (
                "2026~2028 개발용 부품·OEM/AI → 2029~2035 내재화가 어려운 "
                "병목 부품·현장 SI 프로젝트 → 2036년 이후 선도 OEM·운영 SI "
                "선호 확대는 증권사 정성 전망입니다. 실제 시점은 고객 검증·"
                "발주·설치·검수·가동 대수로 재판단합니다."
            )
        if cat == "휴머노이드 시스템통합 · 회사 공식 제목에서 신규 단계 발견":
            return (
                "회사 공식 배포처의 로봇 설치·운영 관련 새 제목을 발견한 "
                "선행경보입니다. 원문 고객 계약·납품 범위·운영 책임·"
                "설치 대수·반복 매출은 아직 확정하지 않았습니다."
            )
        return existing["meaning"](cat)

    def risk(cat):
        if cat == "유진투자증권 · 휴머노이드 밸류체인 단계별 선호도 전망":
            return (
                "그래프 세로축은 선호도이며 실현 수익률·매출·시장점유율이 "
                "아닙니다. 해당 기간이 왔다는 이유만으로 계약·양산 단계가 "
                "자동 확정되지 않으며, 공급망 내재화·가격 하락·고객 채택 "
                "지연·실제 인건비 절감 미달을 점검해야 합니다."
            )
        if cat == "휴머노이드 시스템통합 · 회사 공식 제목에서 신규 단계 발견":
            return (
                "공식 홈페이지의 제목·게시자 일치만 확인한 발견 신호입니다. "
                "시스템통합 프로젝트와 장기 운영·정비 계약을 구분하고 "
                "고객·금액·현장 검수·가동률·마진·현금 회수 미확인을 명시합니다."
            )
        return existing["risk"](cat)

    def verification(item, group_name, text):
        if item.get("eugene_lifecycle_report"):
            return (
                "2026-11-23 보고서·사용자 제공 원도표, 유진투자증권 "
                "공식 배포글 및 2026-11-23 독립 언론 보도 대조; "
                "원보고서 PDF 전체 본문은 접근 제한으로 미열람; "
                "전망·정성 선호도이며 실현 매출·확정 계약 아님"
            )
        if group_name == SI_GROUP:
            return (
                "발행 기업명·공식 도메인·신규 제목에서 작업 단계 발견; 원문 전문 미열람, "
                "본문·계약서 미확인으로 고객명·물량·정기 매출 확정 금지"
            )
        prior = existing["verification"](item, group_name, text)
        lens = lifecycle_lens(item.get("title") or "")
        return (prior + " | 밸류체인 관찰: " + lens + " (제목 분류이며 본문 검증 별도)"
                if lens and group_name and prior else prior)

    def tag(group_name):
        if group_name == GROUP:
            return "유진 휴머노이드 산업 전망"
        if group_name == SI_GROUP:
            return "로봇 SI 설치·운영"
        return existing["tag_for"](group_name)

    for name, func in (
        ("query_news",query), ("topic_group",topic_group), ("score",score),
        ("key",key), ("category",category), ("meaning",meaning),
        ("risk",risk), ("verification",verification), ("tag_for",tag),
    ):
        setattr(base,name,func)
    for q in (BACKFILL, *SI_QUERIES):
        if q not in existing_queries and q not in base.QUERIES:
            base.QUERIES.append(q)
    base._eugene_lifecycle_installed=True
