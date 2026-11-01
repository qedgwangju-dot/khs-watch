#!/usr/bin/env python3
"""Nov-02 source-graded commercial-stage additions to EXISTING robot Telegram watch.

No new workflow, chat, bot, cadence, state migration, or force delivery. Historical
press summaries cannot be mistaken for contracts, production, or booked revenue.
The Oct-28 official ROBOTIS disclosure correction is only shown when the old
incorrect 'signed procurement' key is present in the persisted seen state.
"""
from __future__ import annotations

import datetime as dt
import hashlib
import re

OLD_WRONG_MICRODUCK_KEY = "11f5f316367157a7d48442d23b1fa7dab41410b1572d2a0bb11d95401106c3ce"
CATCHUP_END_KST = dt.date(2026, 11, 6)
DART_ROBOTIS = "https://dart.fss.or.kr/dsaf001/main.do?rcpNo=20261028900684"
LG_AUG_SOURCE = "https://lg.co.kr/media/release/30461"
LG_CONCALL_SOURCE = "https://search.newspim.com/news/view/20261028001512"
WONIK_SOURCE = "https://zdnet.co.kr/view/?no=20261029180425"
DAEDONG_SOURCE = "https://ko.daedong.co.kr/news/daedongnews/2383"
IL_DART = "https://dart.fss.or.kr/dsaf001/main.do?rcpNo=20261029000052"
LG_NEWS = "https://zdnet.co.kr/view/?no=20261031010426"

EVENTS = {
    "microduck_official_correction": {
        "date":"2026-10-28","group":"robotis_microduck_dart_no_order","score":89,
        "source":"로보티즈 10월 28일 DART 해명공시(인용본 교차확인)",
        "title":"[계약 정정] 로보티즈·Pollen MicroDuck 기념 서명식, 공급계약·주문 없음",
        "description": (
            "2026-10-28 로보티즈 DART 공시 20261028900684: 10월 26일 Pollen Robotics SAS와 "
            "MicroDuck 액추에이터의 사양·기술사항 협의를 위해 만나 향후 공급관계를 위한 "
            "기념 서명식을 진행했다. 당시 공급계약 체결도 구매주문도 없었다. "
            "따라서 이전 '공급계약 체결' 알림은 오기였다. "
            "로봇 50000대×대당 15개=750000개 잠재 소요와 "
            "750000×26400원=198억원 증권사 추정은 확정 계약·실제 출하·매출이 아니다. "
            "공식 재공시 예정일 2026-11-27. 신규 계약이 실제 체결되면 그때 별도 감지."
        ),
        "link":DART_ROBOTIS,
        "category":"정정 · 로보티즈–Pollen 공급계약/주문 미체결(10월 28일)",
        "meaning": (
            "10월 26일에 기념 서명식은 있었지만, 10월 28일 회사 공시 기준 계약과 주문은 없었습니다. "
            "기존 감시의 '공급계약 체결' 판정을 정정합니다. "
            "실제 고객 발주와 11월 27일 재공시는 별도 이정표입니다."
        ),
        "risk": (
            "기념 서명과 실제 구매주문서 혼동, 로봇 5만대 목표×15개 잠재 부품 수요의 "
            "확정 매출 오인, 향후 주문 지연·사양 협상 중단. "
            "먼저 확인할 지표는 후속 공시·계약금액·확정 주문·초도 출하입니다."
        ),
        "verification":"공시 접수번호 20261028900684의 회사 해명 문구를 독립 공시 인용본들로 대조; 공식 DART 웹 원문 직접 열람은 제한됨"
    },
    "lg_cloid_prototype_inhouse": {
        "date":"2026-10-31","group":"lg_cloid_inhouse_assembly","score":53,
        "source":"ZDNet Korea 10월 31일 취재(원문 검색 색인·재전재확인)",
        "title":"LG 클로이드 양재 연구용 자체 조립 보도…위탁→내재화 진전, 양산 아님",
        "description":(
            "2026-10-31 ZDNet Korea 취재: 과거 중국 애지봇과 로보스타의 시제품 위탁 조립 "
            "이후 LG전자가 서울 양재 데이터팩토리에서 연구개발용 CLOiD를 직접 제작 중이라는 "
            "업계 관계자 보도. 공장 자동 생산라인 양산이나 고객 수주는 아직 아니다. "
            "2026-08-18 LG 그룹 공식 발표에서도 이미 자체 제작·검증한 CLOiD를 "
            "양재 데이터팩토리 학습에 투입했다고 밝혔다. "
            "이번 언론 취재는 정확한 조립 장소와 위탁에서 자체 조립으로의 이행을 추가 서술한 "
            "사건이며 회사의 신규 대량생산 공시가 아니다."
        ),
        "link":LG_NEWS,
        "category":"LG전자 · CLOiD 양재 연구용 자체조립 언론 보도(양산 전)",
        "meaning":(
            "이전에는 협력사 제작 모델을 활용했다는 취재와 달리 "
            "LG전자가 양재에서 연구용 로봇 조립까지 직접 한다는 보도입니다. "
            "공식 8월 자료의 '자체 제작'과 연결되는 실행 단계이며 "
            "생산라인 완공·양산·외부 판매를 뜻하지 않습니다."
        ),
        "risk":(
            "수작업 시제품과 자동화 양산의 생산성·원가·수율 차이, 로봇손·액추에이터 "
            "품질인증, 고객 검증·외부 발주 확인. 자체조립이 국내 부품사 확정 수주라는 뜻은 아닙니다."
        ),
        "verification":"10월 31일 언론 보도 검색 색인과 동일 내용 재구성 기사, 8월 18일 LG 공식자료로 자체 제작 기확인; 해당 제조공정 위치는 공식 별도 확인 전"
    },
    "lg_robot_data_500k_plan": {
        "date":"2026-10-28","group":"lg_robot_learning_hours_target","score":50,
        "source":"LG전자 3분기 컨퍼런스콜 보도·뉴스핌",
        "title":"LG 로봇 데이터 연말 확보 목표 10만→50만 시간(5배) 상향 보도",
        "description":(
            "LG전자는 2026-08-18 공식자료에서 양재 데이터팩토리의 "
            "직접 수집+합성 학습데이터를 2026년 말 총 100000시간으로 예상했다. "
            "2026-10-28 3분기 컨퍼런스콜 보도에서 NVIDIA 협력 등으로 "
            "2026년 안에 500000시간 데이터를 확보할 체계를 구축하겠다는 "
            "발언을 전했다. 기준 데이터 범위와 실제 확보량은 회사 자료로 추가 확인 필요. "
            "두 숫자가 같은 정의라면 목표치는 5배, 400000시간 증가한 것으로 해석 가능. "
            "두 수치 모두 달성된 실제 데이터량이 아니다. "
            "LG전자 2030년 가정용 휴머노이드 진출은 중장기 목표."
        ),
        "link":LG_CONCALL_SOURCE,
        "category":"LG전자 · 로봇 학습 데이터 50만시간 목표(실제 확보 전)",
        "meaning":(
            "8월 공식 자료상 10만시간 연말 예상에서 10월 컨퍼런스콜 보도상 "
            "50만시간 확보 체계로 확대된 계획입니다. 데이터 범위 동일성은 추가 확인 대상이며 "
            "실제 50만시간 데이터를 수집 완료했다는 의미가 아닙니다."
        ),
        "risk":(
            "실물 데이터와 합성 데이터 중복계산, 품질·다양성 저하, 실제 작업 성공률 개선 미달. "
            "연말 확정 생성시간·고객 작업 성공률·검증 로봇 대수가 확인 지표입니다."
        ),
        "verification":"LG 2026-08-18 공식 10만시간 목표와 2026-10-28 컨퍼런스콜 보도상 50만시간 체계 비교; 동일 분모 공식 재확인 전"
    },
    "wonik_hand_components_report": {
        "date":"2026-10-29","group":"wonik_robot_hand_components","score":43,
        "source":"ZDNet Korea 원익로보틱스 인터뷰 보도",
        "title":"원익로보틱스 로봇 손 액추에이터·촉각센서 자체 개발…연말 시제품 목표",
        "description":(
            "2026-10-29 보도: 원익로보틱스가 로봇 손 구동용 액추에이터와 "
            "촉각센서를 직접 개발하고 있으며 액추에이터 시제품을 2026년 말 목표로 준비 중. "
            "기존 메타 촉각센서 기반 로봇손 개발·제품통합 사례와 구분. "
            "CES 2027 공개는 가능성이지 참가·완성 확정이 아니다. "
            "신규 고객 계약·양산·실제 매출은 미확인."
        ),
        "link":WONIK_SOURCE,
        "category":"원익로보틱스 · 로봇 손 액추에이터·촉각센서 개발(시제품 목표)",
        "meaning":(
            "로봇 손 완제품뿐 아니라 내부 구동부품과 촉각센서까지 만들려는 전략입니다. "
            "자체 부품의 실제 성능·가격 경쟁력이 확보되면 조달·원가 개선 가능성이 있지만, "
            "시제품 완성·양산·고객 수주는 별도 단계입니다."
        ),
        "risk":(
            "모터 발열·감속기·힘줄 장력, 센서 신뢰성·정밀도, 시제품 개발 지연, "
            "독립 고객 인증 부족. 연말 시제품 공개와 실작업 시험 결과를 먼저 확인합니다."
        ),
        "verification":"ZDNet 10월 29일 보도 검색 색인·동일기사 인용; 시제품 양산/고객계약은 회사 공식 자료 미확인"
    },
    "daedong_eyou_mou": {
        "date":"2026-10-29","group":"daedong_eyou_robot_actuator","score":62,
        "source":"대동그룹 공식 보도자료 2026-10-29",
        "title":"대동기어–중국 EYOU 액추에이터 공동개발 MOU…2027년 합작사·2029년 국내 양산 목표",
        "description":(
            "2026-10-28 대동기어·대동로보틱스는 중국 이유로보틱스(EYOU)와 "
            "액추에이터 공동개발·농업용 로봇 현장실증을 위한 양해각서를 체결했다. "
            "2027년 1월까지 중국 JV 설립 추진, 합작사 연간 30000세트 생산능력 구축 구상, "
            "2027년 상반기 1세대 구동기 출시, 2028년까지 대동 농업용 로봇 적용 목표, "
            "2029년 대동기어 국내 양산 목표. "
            "JV 설립 완료·라인 가동·외부 확정 수주는 아직 아니다."
        ),
        "link":DAEDONG_SOURCE,
        "category":"대동기어–EYOU · 공식 양해각서·합작사 추진(실제 설립 전)",
        "meaning":(
            "중국 현지에서 공동개발·시제품을 검증하고 2029년 국내 생산으로 "
            "옮기려는 단계별 계획입니다. 2027년 1월 실제 JV 설립 등기가 첫 검증 시점입니다."
        ),
        "risk":(
            "현지 합작법인 설립 지연, IP·공급망·품질 책임, 연간 3만세트 목표 대비 "
            "주문 부족·수율 미달. MOU를 이미 생산·매출이 발생한 계약으로 표현하지 않습니다."
        ),
        "verification":"대동그룹 2026-10-29 회사 공식 자료와 뉴시스 동일 행사 보도 교차확인; 연간 3만세트는 설비 목표"
    },
    "il_robot_segment_revenue": {
        "date":"2026-10-29","group":"il_robot_revenue_2026q3","score":57,
        "source":"아이엘 2026년 3분기 DART 보고서·공시인용 분석",
        "title":"아이엘 '로봇 판매 외' 1~9월 누적 26억2800만원…3분기 휴머노이드 27억과 구분",
        "description":(
            "아이엘 2026-10-29 제출 3분기 보고서 접수번호 20261029000052: "
            "2026년 1~9월 연결 매출 834억9300만원, "
            "로봇 판매 외 매출 26억2800만원(전체 3%·공시 분류). "
            "언론은 3분기 휴머노이드 매출 27억원으로 소개했지만, "
            "공시상 26억2800만원은 연초부터 9월까지의 누적 부문이고 "
            "휴머노이드 완성품만 분리해 제시하지 않았다. "
            "아이엘봇은 해외 플랫폼 기반 출시 준비·제조현장 실증 단계이며 "
            "판매 대수, 개별 고객, 자체 생산 비율은 미공개."
        ),
        "link":IL_DART,
        "category":"아이엘 · 1~9월 로봇 부문 매출 26억2800만원(휴머노이드만 아님)",
        "meaning":(
            "회사 전체가 3분기 334억원을 매출로 올렸다는 사실과 "
            "로봇 사업의 1~9월 누적 26억2800만원을 분리했습니다. "
            "언론의 '3분기 휴머노이드 매출 27억'과 공시상 분모·기간이 다릅니다."
        ),
        "risk":(
            "해외 플랫폼 재판매 비중·부품 원가·제품 자사화 정도·실증 후 반복 주문 미확인. "
            "다음 분기 누적/분기 분리, 고객 발주·마진과 실제 출하대수를 추적합니다."
        ),
        "verification":"DART 20261029000052 인용 원문 표·독립 언론 보도 비교; DART 웹 원문 직접 접근 제한"
    },
}

# Strict, source-specific advancement checks. Press headlines / plans and
# interviews are NOT transformed into a binding contract or completed SOP.
EXTRA_QUERIES = (
    '(LG전자 OR "LG Electronics") (CLOiD OR 클로이드) '
    '(양재 데이터팩토리 OR 자체 조립 OR 직접 생산 OR 양산 개시 OR 가동률 OR 수주)',
    '(LG전자 OR "LG Electronics") (로봇 데이터팩토리 OR robot data factory) '
    '(50만 시간 OR 500000 hours OR 학습 데이터 실적 OR 공식 가동)',
    '(원익로보틱스 OR "Wonik Robotics") (로봇 손 OR robotic hand) '
    '(액추에이터 OR tactile sensor OR 촉각 센서) (시제품 완료 OR 양산 OR 고객 승인 OR 계약)',
    '(대동기어 OR Daedong Gear) (EYOU OR 이유로보틱스) '
    '(합작법인 설립 완료 OR 1세대 액추에이터 출시 OR 국내 양산 개시 OR 공식 고객 공급계약)',
    '(아이엘 OR ILBOT OR "IL Co") (로봇 매출 OR humanoid sales) '
    '(분기보고서 OR 로봇 판매 OR 신규 공급계약 OR 출하)',
)

OFFICIAL = {
    "lg_cloid_inhouse_assembly":{"LG전자","LG Electronics","LG그룹","LG"},
    "lg_robot_learning_hours_target":{"LG전자","LG Electronics","LG그룹","LG"},
    "wonik_robot_hand_components":{"원익로보틱스","Wonik Robotics"},
    "daedong_eyou_robot_actuator":{"대동기어","Daedong Gear","대동그룹","Daedong"},
    "il_robot_revenue_2026q3":{"아이엘","IL Co","IL Co., Ltd."},
}
RESTRICTED_BASELINE = re.compile(
    r"목표|전망|예정|계획|추진|협의|검토|준비|미확인|not\s+(?:yet|signed|confirmed)|"
    r"would|will|aims?|plans?|expected|target", re.I,
)

def _group_from_text(text: str) -> str:
    if re.search(r"로보티즈|ROBOTIS",text,re.I) and re.search(r"Pollen|폴렌|MicroDuck",text,re.I) and re.search(r"10월\s*28일|20261028900684|기념\s*서명식",text,re.I):
        if re.search(r"계약.*없|미체결|계약/주문\s*없",text,re.I):
            return "robotis_microduck_dart_no_order"
    if re.search(r"LG전자|LG\s*Electronics",text,re.I) and re.search(r"클로이드|CLOiD",text,re.I):
        if re.search(r"양재|데이터팩토리|데이터\s*팩토리",text,re.I):
            return "lg_cloid_inhouse_assembly"
    if re.search(r"LG전자|LG\s*Electronics",text,re.I) and re.search(r"로봇.*(?:학습\s*)?데이터|robot.{0,20}data",text,re.I):
        if re.search(r"50만\s*시간|500[\s,]?000\s*hours|500000\s*시간",text,re.I):
            return "lg_robot_learning_hours_target"
    if re.search(r"원익로보틱스|Wonik\s*Robotics",text,re.I):
        if re.search(r"로봇\s*손|로봇손|robot(?:ic)?\s*hand",text,re.I) and re.search(r"액추에이터|actuator|촉각|tactile",text,re.I):
            return "wonik_robot_hand_components"
    if re.search(r"대동기어|Daedong\s*Gear",text,re.I) and re.search(r"EYOU|이유\s*로보틱스|이유로보틱스",text,re.I):
        return "daedong_eyou_robot_actuator"
    if re.search(r"아이엘|ILBOT|IL\s*Co",text,re.I) and re.search(r"로봇|robot|휴머노이드",text,re.I):
        if re.search(r"매출|revenue|분기보고서|공급계약",text,re.I):
            return "il_robot_revenue_2026q3"
    return ""

def _live_milestone(item: dict, group: str) -> str:
    source = str(item.get("source") or "").strip()
    if source not in OFFICIAL.get(group,set()):
        return ""
    text = " ".join(str(item.get(k) or "") for k in ("title","description"))
    if RESTRICTED_BASELINE.search(text):
        return ""
    if group=="lg_cloid_inhouse_assembly" and re.search(
        r"클로이드.{0,65}(?:양산\s*(?:개시|시작)|생산라인\s*가동)|"
        r"(?:양산\s*(?:개시|시작)|생산라인\s*가동).{0,65}클로이드",text,re.I
    ):return "company_confirmed_cloid_mass_production"
    if group=="lg_robot_learning_hours_target" and re.search(
        r"50만\s*시간.{0,32}(?:확보\s*완료|달성)|"
        r"(?:확보\s*완료|달성).{0,32}50만\s*시간",text,re.I
    ):return "actual_500k_hours_achieved"
    if group=="wonik_robot_hand_components" and re.search(
        r"(?:액추에이터|촉각\s*센서).{0,65}(?:시제품\s*완성|시제품\s*개발\s*완료|양산\s*개시|공급계약\s*체결)|"
        r"(?:시제품\s*완성|시제품\s*개발\s*완료|양산\s*개시|공급계약\s*체결).{0,65}"
        r"(?:액추에이터|촉각\s*센서)",text,re.I
    ):return "prototype_or_sop_official"
    if group=="daedong_eyou_robot_actuator":
        if re.search(r"(?:합작법인|JV).{0,50}(?:설립\s*완료|등기\s*완료|established)",text,re.I):
            return "jv_legal_established"
        if re.search(r"(?:액추에이터|구동기).{0,60}(?:정식\s*출시|양산\s*개시|첫\s*고객\s*출하)",text,re.I):
            return "product_launched_or_production"
    if group=="il_robot_revenue_2026q3" and re.search(
        r"2026.{0,20}(?:4분기|12월).{0,60}(?:로봇\s*(?:부문\s*)?매출|robot\s*revenue).{0,30}\d",text,re.I
    ):
        return "2026q4_reported_robot_revenue"
    return ""

def install(base) -> None:
    prev = {k:getattr(base,k) for k in (
        "query_news","topic_group","score","key","category","meaning",
        "risk","verification","tag_for","select_diverse"
    )}
    lookup={v["group"]:v for v in EVENTS.values()}
    keys={v["group"]:name for name,v in EVENTS.items()}
    prefix="DIRECT_ROBOT_NOV02_"

    def query_news(q):
        if q.startswith(prefix):
            name=q[len(prefix):]
            item=EVENTS.get(name)
            if item is None or base.NOW.astimezone(base.KST).date()>CATCHUP_END_KST:
                return []
            if name=="microduck_official_correction":
                if OLD_WRONG_MICRODUCK_KEY not in set(base.load_state().get("seen",[])):
                    return []
            return [dict(
                title=item["title"],description=item["description"],
                source=item["source"],link=item["link"],published=None,
                nov02_event=name,
            )]
        return prev["query_news"](q)

    def group(text):
        return _group_from_text(text) or prev["topic_group"](text)

    def score(item):
        event=item.get("nov02_event")
        if event in EVENTS:
            return EVENTS[event]["score"]
        content=" ".join(str(item.get(k) or "") for k in ("title","description","source"))
        g=_group_from_text(content)
        if not g:
            return prev["score"](item)
        return 34 if _live_milestone(item,g) else 0

    def key(item):
        event=item.get("nov02_event")
        if event in EVENTS:
            v=EVENTS[event]
            return hashlib.sha256(f"robot-watch-nov02|{event}|{v['date']}|{v['group']}".encode()).hexdigest()
        content=" ".join(str(item.get(k) or "") for k in ("title","description","source"))
        g=_group_from_text(content)
        if g:
            stage=_live_milestone(item,g) or "baseline"
            return hashlib.sha256(f"robot-watch-nov02-live|{g}|{stage}".encode()).hexdigest()
        return prev["key"](item)

    upgrade_names = {
        "company_confirmed_cloid_mass_production":
            "LG전자 · CLOiD 양산라인 가동 회사 공식 확인",
        "actual_500k_hours_achieved":
            "LG전자 · 로봇 데이터 50만시간 실제 확보 공식 확인",
        "prototype_or_sop_official":
            "원익로보틱스 · 로봇 손 부품 시제품/상용화 다음 단계 공식 확인",
        "jv_legal_established":
            "대동기어–EYOU · 합작법인 실제 설립·등기 완료",
        "product_launched_or_production":
            "대동기어–EYOU · 로봇 액추에이터 제품 출시/양산 공식 확인",
        "2026q4_reported_robot_revenue":
            "아이엘 · 2026년 4분기 로봇 부문 신규 실적 공시",
    }
    def category(text,g):
        if g in lookup:
            stage = _live_milestone(
                {"title":text,"description":"","source":
                 sorted(OFFICIAL[g])[0] if g in OFFICIAL else ""},g
            )
            if stage in upgrade_names:return upgrade_names[stage]
            return lookup[g]["category"]
        return prev["category"](text,g)

    def meaning(cat):
        if cat in upgrade_names.values():
            return ("회사 명의로 새로운 달성 이정표가 발표된 단계입니다. "
                    "검증·시제품·설립·양산·실제 고객 출하·매출 중 어느 단계인지는 "
                    "원문에서 각각 분리하며 직전 목표를 소급 달성으로 취급하지 않습니다.")
        for v in EVENTS.values():
            if cat==v["category"]:return v["meaning"]
        return prev["meaning"](cat)

    def risk(cat):
        if cat in upgrade_names.values():
            return ("실제 고객 구매주문·인도·수율·검수·대금 회수 확인 전에는 "
                    "새 완료 이정표를 곧바로 확정 매출로 간주하지 않습니다.")
        for v in EVENTS.values():
            if cat==v["category"]:return v["risk"]
        return prev["risk"](cat)

    def verification(item,g,text):
        if g in lookup:
            if item.get("nov02_event") in EVENTS:
                return lookup[g]["verification"]
            return ("회사 명의 공식 신규 완료 단계로 분류하되 공개 검색 색인 한계가 있으므로 "
                    "기계판정 후 원문·고객·수량·일정 추가 검증 필요")
        return prev["verification"](item,g,text)

    def tag(g):
        tags={
          "robotis_microduck_dart_no_order":"로보티즈 계약 정정",
          "lg_cloid_inhouse_assembly":"LG 클로이드 자체조립",
          "lg_robot_learning_hours_target":"LG 로봇 학습데이터",
          "wonik_robot_hand_components":"원익로보틱스 로봇손",
          "daedong_eyou_robot_actuator":"대동기어–EYOU",
          "il_robot_revenue_2026q3":"아이엘 로봇 매출",
        }
        return tags.get(g) or prev["tag_for"](g)

    def select(items,seen,force,limit):
        chosen=prev["select_diverse"](items,seen,force,limit)
        eligible=items if force else [x for x in items if x.get("key") not in seen]
        ranked=sorted((x for x in eligible if x.get("nov02_event") in EVENTS
                       and x.get("score",0)>=11),
                      key=lambda x:x.get("score",0),reverse=True)
        # Reserve at most three slots per invocation. Unselected new keys are
        # NOT added to seen: existing repair_pending_seen(pre_state) enforces it.
        for item in reversed(ranked[:3]):
            if not any(x.get("key")==item.get("key") for x in chosen):
                chosen=[item,*chosen][:limit]
        return chosen

    base.query_news=query_news
    base.topic_group=group
    base.score=score
    base.key=key
    base.category=category
    base.meaning=meaning
    base.risk=risk
    base.verification=verification
    base.tag_for=tag
    base.select_diverse=select
    for q in (*[prefix+n for n in EVENTS],*EXTRA_QUERIES):
        if q not in base.QUERIES:base.QUERIES.append(q)
