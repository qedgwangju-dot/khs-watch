"""Reviewed Nov 19–23 robotics events and narrow already-delivered reprint aliases.

Existing ROBOTIS watch only. No new schedule, route, bot, state schema or common
modules. Pinned baseline reports are not automatically promoted to contracts.
"""
from __future__ import annotations

import datetime as dt
import hashlib
import re

KST = dt.timezone(dt.timedelta(hours=9))
SENTINEL = "__robot_watch_20261123_reviewed_events_only__"
START = dt.datetime(2026,11,23,0,0,tzinfo=KST)
END = dt.datetime(2026,11,27,0,0,tzinfo=KST)
# Keys below are evidenced by complete Nov-20 and Nov-18 delivery artifacts.
POLLEN_DELIVERED = "44e38c418d8b624501e53e833075280cbb24234df30454c4e1425da953799ffb"
GF_DELIVERED = "83d7fed4807294b0de7d1b2215798785f8ba441daa5fc420ad6c65bc092e0787"
JSLINK_EXISTING = "eea1e1a4e99a025446b0ef5eb960c2decc3d54f1d762e116a51b8f2f6e7140db"
ROOT = "nov23_"
STAGE_LABEL = {"three_party_execution_contract":"3사 본계약","chip_application_intent":"로봇용 AI 칩 적용 방향","potential_equity_investment":"투자 검토·유동성 위험","reported_supply_constraint":"영구자석 공급 병목","broker_earnings_review":"증권사 실적 전망","magnet_supply_mou":"영구자석 업무협약"}
STORIES = {
  "hurim_contract": {
    "title":"휴림로봇·한화로보틱스·울트라이노베이션, 삼성전기 장비 자동화용 3사 본계약",
    "date":"2026-11-23", "stage":"three_party_execution_contract",
    "source":"휴림로봇 발표 인용·뉴스핌·이데일리",
    "link":"https://www.newspim.com/news/view/20261123000088",
    "meaning":"7월 3사 업무협약에서 11월 23일 3사 본계약으로 진전했습니다. 휴림로봇은 장비 전면 자동화 모듈(EFEM)에 쓰이는 이송로봇(TR로봇)·직각좌표 로봇 설계와 제조, 한화로보틱스는 고객 제안·계약·사후관리, 울트라이노베이션은 베트남 현지 설치·예비부품·유지보수를 맡습니다. 삼성전기 베트남 생산법인도 목표 적용처입니다.",
    "risk":"3사 간 사업수행 본계약이지 삼성전기와의 직접 구매계약 또는 확정 납품액 발표라는 뜻은 아닙니다. 고객 발주서·수량·단가·검수·매출 시점은 미공개입니다.",
    "verification":"2026-11-23 휴림로봇 제공 보도자료를 뉴스핌·이데일리가 각각 보도; 계약 주체와 최종 고객 발주·금액을 분리"
  },
  "musk_ai5": {
    "title":"머스크, 차에는 AI4 충분·AI5는 Optimus용 계획 언급",
    "date":"2026-11-22","stage":"chip_application_intent",
    "source":"Elon Musk X 발언·재인용",
    "link":"https://x.com/elonmusk/status/2124475458150334900",
    "meaning":"11월 22일 머스크는 자율주행 차량에는 AI4 연산칩으로 충분하고 차세대 AI5는 옵티머스에 쓰일 것이라고 밝혔다는 발언입니다. 자율주행 소프트웨어 FSD v15 언급과 로봇용 실제 반도체 물량은 구분합니다.",
    "risk":"AI5의 설계 방향·적용처 발언일 뿐 양산 시작·로봇 탑재 수량·실제 출하·반도체 공급 계약은 확인되지 않았습니다.",
    "verification":"2026-11-22 X 게시물은 직접 본문 열람에 제한이 있어 인용 보도와 제공 링크로 확인; 생산량·일정 공식 사양 미검증"
  },
  "base_foundation": {
    "title":"베이스그룹, Foundation에 1.5억달러(보도 환산 약 2,000억원) 투자 검토…급여 미지급 위험",
    "date":"2026-11-19","report_date":"2026-11-20","stage":"potential_equity_investment",
    "source":"Reuters·연합뉴스·한겨레",
    "link":"https://www.reuters.com/world/south-korean-firm-plans-150-million-lifeline-eric-trump-backed-robot-maker-2026-11-19/",
    "meaning":"11월 19일 보도: 베이스그룹이 Foundation Future Industries의 1억5,000만달러(기사 보도 환산 약 2,000억원) 자금조달 투자를 검토 중이라고 인정했습니다. 로봇용 알루미늄과 배터리용 리튬 공급 합작법인도 구상 단계이며, 대상 회사는 직원 급여 미지급으로 유동성 위험이 드러났습니다.",
    "risk":"검토·추진은 인수·투자금 납입·매출 발생이 아닙니다. 이해충돌 관련 미 의회 감시, 계약 성사·자금 회수·현금 부족 위험을 구분합니다.",
    "verification":"Reuters 2026-11-19 취재와 11월 20일 한국 보도 대조; 베이스 측은 검토를 확인, 납입 완료는 미확인"
  },
  "rareearth_shortage": {
    "title":"중국 희토류·영구자석 수출 제한, 로봇 액추에이터 생산 병목 부각",
    "date":"2026-11-22","stage":"reported_supply_constraint",
    "source":"조선비즈",
    "link":"https://v.daum.net/v/20261122060240744",
    "meaning":"11월 22일 업계 취재에서 중국산 자석 의존과 수출 허가 지연이 산업용 로봇의 모터·액추에이터 생산 및 납기에 부담으로 제시됐습니다. 로보티즈 수주잔고 약 100만개 중 저가형 약 90%, 뉴로메카 자석 확보에 8개월 사례는 언론 취재 수치입니다.",
    "risk":"회사 공시 기준 재고·수주잔고·생산중단 확정이 아닙니다. 실제 수출허가 발급·대체 자석 고객 검증·단가·출하 지연을 확인합니다.",
    "verification":"조선비즈 2026-11-22 산업 취재로 확인; 개별 회사의 공시·조달 원문 독립 확인 전"
  },
  "rainbow_broker": {
    "title":"레인보우로보틱스 1~3분기 매출 +67%·삼성 협력 확대, 2027년 양산은 기대",
    "date":"2026-11-23","stage":"broker_earnings_review",
    "source":"유진투자증권 분석 인용·프라임경제",
    "link":"https://www.newsprime.co.kr/news/article/?no=755980&sec_no=67",
    "meaning":"11월 23일 유진투자증권 분석은 레인보우로보틱스의 2026년 1~3분기 누적 매출 353억원(전년 동기 대비 +67%)과 삼성전자 협력 확대를 조명했습니다. 신규 목표주가 57만원과 2027년 산업용·휴머노이드 로봇 확대 전망은 증권사 평가이지 신규 공급계약이 아닙니다.",
    "risk":"삼성전자가 최대주주인 사실과 실제 삼성향 납품·양산 승인·반복 매출은 다릅니다. 분기 실적 원공시·현금흐름·제품별 수율 확인이 필요합니다.",
    "verification":"2026-11-23 유진투자증권 보고서 인용 보도; 보고서 전문·회사 분기 공시 수치 별도 대조 전"
  },
  "jslink_mou": {
    "title":"제이에스링크·로보티즈 휴머노이드 영구자석 MOU…일부 품질 검증",
    "date":"2026-11-20","stage":"magnet_supply_mou",
    "source":"제이에스링크 회사 연혁·서울경제TV",
    "link":"https://sentv.co.kr/article/view/sentv202611200037",
    "meaning":"11월 20일 로보티즈와 휴머노이드용 영구자석 공동개발·안정적인 조달 협력을 위한 업무협약을 체결했습니다. 일부 자석 품목은 품질검증을 거쳤다는 보도이며 향후 추가 고성능 제품 평가가 이어질 예정입니다.",
    "risk":"업무협약과 품질검증을 확정 구매계약·독점 공급·양산 매출로 해석하지 않습니다. 제품 규격·물량·구매단가·납품 시점은 미공개입니다.",
    "verification":"제이에스링크 공식 연혁·2026-11-20 서울경제TV 보도 상호 확인, 해당 기사 웹 본문은 직접 열람에 제한"
  }
}
# Narrow reprint facts, no new customer, contracted volume, physical shipment or amendment.
POLLEN_REPRINT = re.compile(r"로보티즈|ROBOTIS", re.I)
POLLEN_SECOND = re.compile(r"폴렌(?:\s*로보틱스)?|Pollen\s*Robotics|39[.,]?[78]\s*억|40\s*억|39억7812|39억7813|39\s*억\s*원|DYNAMIXEL[- ]X|다이나믹셀\s*X",re.I)
POLLEN_CHANGE = re.compile(r"별도\s*(?:신규|추가)?\s*계약|추가\s*(?:계약|수주|발주)|계약\s*(?:증액|감액|정정|변경|해지|철회)|초도\s*(?:출하|납품)|첫\s*(?:출하|납품)|실제\s*출하|매출\s*인식|새로운\s*고객|신규\s*고객|(?:20[3-9]\d)\s*GWh|202[8-9]\s*년",re.I)
GF_CHANGE = re.compile(r"현장\s*(?:시험|실증|운용)\s*(?:개시|시작|완료)|테스트\s*(?:개시|시작|완료)|추가\s*발주|양산\s*(?:계약|납품)|대수\s*확정|유료\s*납품",re.I)
GF_HEAD = re.compile(r"아틀라스|Atlas|Boston\s*Dynamics|보스턴다이내믹스",re.I)
GF_CHIP = re.compile(r"GlobalFoundries|글로벌파운드리|반도체\s*(?:공장|팹|제조)|chip\s*plant|semiconductor\s*fab",re.I)

def _stamp(item):
    v=item.get("published")
    if not v: return None
    try: return dt.datetime.fromisoformat(str(v).replace("Z","+00:00")).astimezone(KST).date()
    except (TypeError,ValueError,OverflowError): return None

def _already_delivered_reprint(item, fallback):
    day=_stamp(item)
    if not day or not dt.date(2026,11,17)<=day<=dt.date(2026,11,25):
        return fallback
    title=str(item.get("title") or "")
    desc=str(item.get("description") or "")
    text=title+" "+desc
    # Only the exact Nov-19 contract and its media aliases. Changes retain the upstream key.
    if dt.date(2026,11,19)<=day<=dt.date(2026,11,23) and POLLEN_REPRINT.search(title) and POLLEN_SECOND.search(title):
        if not POLLEN_CHANGE.search(text):
            return POLLEN_DELIVERED
    # The Nov-17 Boston Dynamics/GlobalFoundries planned Atlas trial was already
    # sent Nov-18; no new trial completion is implied by syndication.
    if GF_HEAD.search(title) and GF_CHIP.search(title) and not GF_CHANGE.search(text):
        return GF_DELIVERED
    return fallback


def _nov23_reprint_name(item):
    """Narrow event-level reprints; changed contracts and achieved stages escape."""
    day=_stamp(item)
    if day is None or not dt.date(2026,11,19)<=day<=dt.date(2026,11,25):
        return None
    title=str(item.get("title") or "")
    desc=str(item.get("description") or "")
    combined=title+" "+desc
    if re.search(r"휴림로봇|Hurim",title,re.I) and re.search(r"삼성전기|Samsung Electro",title,re.I) and re.search(r"한화로보틱스|Hanwha|본계약",combined,re.I):
        if day>=dt.date(2026,11,23) and not re.search(r"추가\s*발주|납품\s*완료|구매\s*주문서|추가\s*계약\s*체결|계약금액\s*확정|contract\s*value",combined,re.I):
            return "hurim_contract"
    if re.search(r"머스크|Musk|테슬라|Tesla",title,re.I) and re.search(r"AI[-\s]*5",title,re.I) and re.search(r"Optimus|옵티머스",combined,re.I):
        if day>=dt.date(2026,11,22) and not re.search(r"AI5\s*(?:생산|양산|출하|탑재)\s*(?:개시|완료|시작)|공급계약\s*체결",combined,re.I):
            return "musk_ai5"
    if re.search(r"베이스그룹|Base\s*Group",title,re.I) and re.search(r"파운데이션|Foundation",combined,re.I):
        if not re.search(r"투자\s*(?:완료|납입|확정)|지분\s*취득\s*완료|funding\s*closed|invested",combined,re.I):
            return "base_foundation"
    if re.search(r"제이에스링크|JS\s*Link",title,re.I) and re.search(r"로보티즈|ROBOTIS",combined,re.I) and re.search(r"자석|magnet",combined,re.I):
        if not re.search(r"공급\s*본계약|납품\s*완료|첫\s*출하|실제\s*양산|정식\s*발주",combined,re.I):
            return "jslink_mou"
    if re.search(r"레인보우로보틱스|Rainbow\s*Robotics",title,re.I) and re.search(r"삼성전자|Samsung",combined,re.I) and re.search(r"유진투자|57만원|매출\s*67%|실적\s*전망",combined,re.I):
        if day>=dt.date(2026,11,23) and not re.search(r"신규\s*공급계약|삼성전자\s*발주|고객\s*양산\s*승인",combined,re.I):
            return "rainbow_broker"
    if re.search(r"中|중국|China",title,re.I) and re.search(r"희토류|영구자석|rare\s*earth",combined,re.I) and re.search(r"로봇|robot",combined,re.I):
        if day>=dt.date(2026,11,22) and not re.search(r"신규\s*(?:규제|수출금지)|실제\s*생산중단|허가\s*승인|긴급\s*금수",combined,re.I):
            return "rareearth_shortage"
    return None

def install(base):
    if getattr(base,"_nov23_event_scope_installed",False): return
    old={name:getattr(base,name) for name in
        ("query_news","topic_group","key","score","category","meaning","risk","verification","tag_for","clean_title")}
    seen=set(base.load_state().get("seen") or [])
    # Keep the actual previously-seen MOU feed key to avoid replaying a Nov-20
    # fact that is already in the legacy seen-state without a verified receipt map.
    pin_keys={name:hashlib.sha256(("robot-nov23-reviewed|"+name+"|"+spec["date"]+"|"+spec["stage"]).encode()).hexdigest()
              for name,spec in STORIES.items()}
    if JSLINK_EXISTING in seen:
        pin_keys["jslink_mou"]=JSLINK_EXISTING
    captions={name:ROOT+name for name in STORIES}

    def query(q):
        if q == SENTINEL:
            if not START<=base.NOW.astimezone(KST)<END: return []
            return [
                {"nov23_event":name,"title":spec["title"],"description":spec["meaning"],
                 "source":spec["source"],"link":spec["link"],
                 "published":spec.get("report_date",spec["date"])+"T12:00:00+09:00","published_precision":"day"}
                for name,spec in STORIES.items()
            ]
        return old["query_news"](q)

    def group(text):
        for name,spec in STORIES.items():
            if spec["title"] in text: return captions[name]
        return old["topic_group"](text)

    def key(item):
        name=item.get("nov23_event")
        if name in STORIES: return pin_keys[name]
        alias=_nov23_reprint_name(item)
        if alias: return pin_keys[alias]
        return _already_delivered_reprint(item,old["key"](item))

    def score(item):
        if item.get("nov23_event") in STORIES:
            return 48 if START<=base.NOW.astimezone(KST)<END else 0
        return old["score"](item)

    def cat(text,group_name):
        for name,spec in STORIES.items():
            if group_name == captions[name]: return "로봇 후속 확인 · "+STAGE_LABEL[spec["stage"]]
        return old["category"](text,group_name)

    def meaning(category):
        for spec in STORIES.values():
            if category=="로봇 후속 확인 · "+STAGE_LABEL[spec["stage"]]:return spec["meaning"]
        return old["meaning"](category)

    def risk(category):
        for spec in STORIES.values():
            if category=="로봇 후속 확인 · "+STAGE_LABEL[spec["stage"]]:return spec["risk"]
        return old["risk"](category)

    def verification(item,group_name,text):
        name=item.get("nov23_event")
        if name in STORIES:
            return f"사건일 {STORIES[name]['date']}·확인 {STORIES[name]['verification']}"
        return old["verification"](item,group_name,text)

    def tag(group_name):
        if group_name in captions.values():return "로봇 후속 확인"
        return old["tag_for"](group_name)

    protected={spec["title"] for spec in STORIES.values()}
    def clean_title(title,source):
        if title in protected: return title
        return old["clean_title"](title,source)

    for name,fn in (("query_news",query),("topic_group",group),("key",key),
                    ("score",score),("category",cat),("meaning",meaning),
                    ("risk",risk),("verification",verification),("tag_for",tag),
                    ("clean_title",clean_title)):
        setattr(base,name,fn)
    if SENTINEL not in base.QUERIES:
        base.QUERIES.append(SENTINEL)
    base._nov23_event_scope_installed=True
