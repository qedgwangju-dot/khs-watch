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

# Full reviewed text for this one source; rendered notification body may not silently
# drop the independently sourced scenario values, chart trajectories or caveats.
EUGENE_ALERT_DETAILS = "■ 시장 설치 전망(유진 기본 시나리오·세계 누적, 실제 출하 아님)\n2030년 13만 대 → 2035년 170만 대 → 2040년 787만 대(산업용 289만 + 가정용 498만). 2040년 산업용 중 중국 166만 대(57.5%), 한국 6.8만 대(2.4%) 추정. 2030년 산업용 설치 중 물류·창고+기타 제조 약 75%. 가정용 낙관 시나리오 2040년 4,596만 대는 기본 498만 대와 구분.\n\n■ 첨부 선호도 그래프: 6개 곡선 모두(매출·주가 축 아님)\n① 개발용 부품: 2026~28년 연구·시제품 수요 강세 → 양산 전환 시 상대 선호 급감.\n② OEM/AI(완제품·두뇌): 초기 주목 → 2029~35년 가격경쟁으로 선별 → 2036년 이후 선도업체 재부각.\n③ 병목 부품: 단기 공급망 선정 기대 → 중기 감속기·힘/토크·촉각센서 강세 → 장기 상대 선호도는 높은 수준에서 완만하게 둔화.\n④ 단순 모듈: 초기 공급망 기대 이후 가격·표준화 경쟁으로 장기 선호 하락.\n⑤ SI 프로젝트: 약 2030년대 초 현장별 구축·설치 수혜 확대 후 표준화에 따라 상대 선호 감소.\n⑥ SI 운영: 실제 설치·가동 대수 증가에 비례해 정비·운영·소프트웨어 반복매출 성장 전망.\n도표 내 '2035년 가정용 출하가 산업용 추월', '2040년 서비스 매출이 하드웨어 추월'도 모두 예상 교차 시점이며 확정이 아님.\n\n■ 가격·기술과 상용화의 현실\n부품원가 추정: 2026년 대당 15만달러(약 2억189만원) → 2040년 2.1만달러(약 2,826만원), 약 -86%. 가상 바퀴형 모델 시험에서는 평균 소비전력 -43%, 부품값 -11%, 배터리 용량 2배 이상 적용 시 가동시간 4→15.4시간(실제 제품 검증 아님). 2026년 상반기 세계 출하 약 2.2만 대 중 중국 상위 5개 업체가 86% 이상을 차지했지만 제조·물류 목적은 약 18%; 공연·교육·데이터 수집 등은 60% 이상. 공개된 131개 모델 중 이족보행 비중은 2024년 상반기 90% → 2026년 상반기 50%로 감소. 테슬라 옵티머스 외부 판매 목표 약 12개월, 3세대 공개 목표 9개월 이상 지연됐다는 평가. 중국 연 운용비 50만~70만위안(약 1.01억~1.41억원)으로 인건비 대비 경제성 확보가 아직 난제. 산업용 도입의 기본 가정은 연간 절감 인건비가 로봇 연간 총비용(설치·엔지니어링·정비 포함)의 1.75배에 이르는 것. 가정용 수요 추정은 가구 가용소득의 약 5%를 로봇 구매·운영에 지출할 수 있다고 가정.\n\n■ 기업별 증권사 판단(확정 수주와 구분)\n로보티즈: 2026년 1~3분기 누적 매출 407억원(+49% 전년동기 대비), 관절 구동장치 수주잔고 100만 개 이상 보도. 개발용 수요·다이나믹셀-Q 및 우즈베키스탄 생산 확대가 2027년 관건. 유진 '매수', 목표주가 32만원.\n레인보우로보틱스: 2026년 1~3분기 매출 353억원(+67%), 삼성전자향 118억원(2025년 연간 104억원). 삼성 협력·현장 로봇 확장 기대. 유진 '매수', 목표주가 57만원. 유진 추정 2026년 연간 매출 516억원·영업손실 58억원 → 2027년 795억원·영업이익 10억원(예상 흑자전환). 실제 고객별 계약은 미확인. 목표주가·내년 실적은 확정 실적이 아닌 증권사 추정.\n\n■ 반드시 확인할 선행지표\n부품은 고객 실명·설계채택→검증→공급계약→출하·가격·수율, OEM은 현장작업 성공률·판매대수·생산능력·가동률, SI는 유료 설치대수·검수·계약기간·유지보수 마진·실제 현금회수. 개발용 수요는 양산 전환 시 감소할 수 있고, 가정용 확산은 노동대체 효용·안전·구매력에 달림.\n\n■ 검증 범위·환산\n유진 11/23 배포글·제공 도표·당일 로봇신문·뉴스핌 보도 대조. 147쪽 PDF 본문 전체는 접근 제한으로 직접 열람하지 못함. 환산은 11/23 서울외환시장 15:30 달러 1,345.90원·위안 201.75원 기준의 참고값으로 미래 환율 전망이 아님. 자료에 없는 고객 계약·양산 확정은 만들지 않음."

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
            return EUGENE_ALERT_DETAILS
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
