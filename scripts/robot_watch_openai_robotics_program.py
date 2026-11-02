#!/usr/bin/env python3
"""OpenAI physical-AI/data-center robotics program, EXISTING Telegram route.

2026-10-29 Sam Altman first-person Cheeky Pint interview: OpenAI has a
robotics program intended to help build datacenters / fab and energy components.
This is PROGRAM DIRECTION, NOT an installed robot, order, production ramp,
supplier award or signed construction contract.

Keep separate from the already existing 2026-09 OpenAI-owned humanoid/2027-demo
lane. A dated catch-up is allowed only before 2026-11-07, once, and uses a
stable semantic key. The newer lifecycle milestones need primary reporting
or named trustworthy press with explicit achieved-stage evidence.

Does not alter Telegram, Actions, recipients, cron or historical seen states.
"""
from __future__ import annotations

import datetime as dt
import hashlib
import re

RECOVERY_QUERY = "DIRECT_OPENAI_CHEEKY_PINT_ROBOTICS_DATACENTER_OCT29_2026"
RECOVERY_END_KST = dt.date(2026, 11, 6)
RECOVERY_KEY = hashlib.sha256(
    b"openai|robotics-infrastructure|cheeky-pint-2026-10-29|ceo-program-direction"
).hexdigest()
TOPIC = "openai_robotics_infrastructure_program"
CATEGORY_BASE = "OpenAI · 데이터센터·부품공장 로봇 프로그램 CEO 발언(사업 방향)"
CATEGORY_STAGES = {
    "verified_robot_demo": "OpenAI · 데이터센터 건설용 로봇 실물 시연",
    "construction_robot_deployed": "OpenAI · 데이터센터 건설 로봇 실제 현장 배치",
    "robotics_partner_contract": "OpenAI · 로봇 이용 인프라 공식 구매·공급계약",
    "robotics_component_factory": "OpenAI · 로봇 활용 부품 제조 실제 가동",
    "measured_on_site_kpi": "OpenAI · 로봇 현장 가동·작업 성공률 정량 검증",
    "program_canceled_or_delayed": "OpenAI · 로봇 인프라 프로그램 철회·연기",
}
COMPANY = {"OpenAI","OpenAI Newsroom","OpenAI 공식","Sam Altman"}
TRUSTED = {
    "Reuters","Bloomberg","Financial Times","The Next Web","CNBC",
    "TechCrunch","연합뉴스","전자신문","머니투데이","ZDNet Korea",
}
ORIGINAL_INTERVIEW = {
    "title": "샘 올트먼, OpenAI 로봇 프로그램을 데이터센터·부품 제조에 활용할 계획 언급",
    "description": (
        "2026년 10월 29일 Cheeky Pint에서 OpenAI CEO 샘 올트먼은 "
        "이미 로봇 프로그램(robotics program)을 갖고 있으며 "
        "로봇을 이용해 더 많은 데이터센터를 만들겠다는 방향을 밝혔다. "
        "인공지능으로 로봇을 제어해 부품 공장(fab)을 운영하고 "
        "터빈·태양광 설비를 만들며 데이터센터를 건설하는 장기 구상도 언급했다. "
        "하지만 실제 건설 현장 로봇 투입, 고객 납품, 구매계약, 제조 원가, "
        "양산 로봇 대수, 완공된 로봇 건설 데이터센터는 발표하지 않았다. "
        "OpenAI의 기존 자체 휴머노이드 연구와 2027년 시연 목표는 별도 사건이다. "
        "2026-10-29 공개된 Cheeky Pint 제작사 원문 전사 검색 색인과 "
        "동일 발언을 전한 10월 29일 The Next Web 보도를 대조했으며, "
        "공식 전사 페이지 직접 재열람은 접근 제한으로 완료하지 못했다. "
        "OpenAI 공식 채용자료에서는 로봇 제어 소프트웨어, 모터·액추에이터 "
        "시제품·제조검사 개발 조직을 확인할 수 있지만, "
        "이를 데이터센터 현장 로봇 납품·매출 증거로 간주하지 않는다."
    ),
    "link": "https://cheekypint.transistor.fm/39/transcript",
    "source": "Cheeky Pint 원문 전사(검색 색인) · The Next Web 대조",
}
QUERIES = (
    '("Sam Altman" OR "샘 올트먼" OR "OpenAI") (robotics OR robots OR 로봇) '
    '("data centers" OR "data centres" OR 데이터센터 OR construction OR 건설)',
    '("Cheeky Pint" OR "John Collison" OR "존 콜리슨") '
    '(robotics OR 로봇 OR industrial robots) '
    '("data center" OR "self-replicating" OR 부품공장 OR 건설)',
    '(OpenAI OR "Sam Altman") (robotics program OR 로봇 프로그램 '
    'OR actuator OR 액추에이터) (factory OR fab OR data center OR turbine '
    'OR data collection OR onsite OR 현장)',
    '(OpenAI OR 오픈AI) (robotics OR 로봇) '
    '(factory automation OR robotic construction OR first deployment '
    'OR construction site OR data center OR 고객 계약 OR 현장 투입)',
)

IDENTITY = re.compile(r"\bOpenAI\b|오픈\s*AI|샘\s*올트먼|Sam\s*Altman",re.I)
ROBOT = re.compile(r"\brobot(?:s|ic|ics)?\b|로봇|robotics?\s*program|휴머노이드",re.I)
INFRA = re.compile(
    r"data\s*cent(?:er|re)s?|데이터\s*센터|"
    r"\bfabs?\b|반도체\s*공장|부품\s*공장|"
    r"construct(?:ion|ing)?|건설|self[-\s]*replicat|"
    r"turbines?|solar\s*panels?|태양광|터빈|"
    r"industrial\s*robots?|산업용\s*로봇",
    re.I,
)
ACHIEVED = (
    ("construction_robot_deployed",re.compile(
        r"(?:robots?|로봇).{0,85}(?:actually\s*)?"
        r"(?:deployed|working|installed|투입\s*완료|배치\s*완료|실제\s*투입|가동\s*개시)"
        r".{0,65}(?:data\s*cent(?:er|re)|construction|건설|데이터\s*센터)|"
        r"(?:data\s*cent(?:er|re)|construction|건설|데이터\s*센터).{0,75}"
        r"(?:robots?|로봇).{0,35}(?:deployed|working|투입\s*완료|실제\s*투입|배치\s*완료)",
        re.I,
    )),
    ("robotics_component_factory",re.compile(
        r"(?:robot(?:ic)?s?|로봇).{0,90}"
        r"(?:factory|fab|component\s*line|제조\s*공장|부품\s*공장).{0,65}"
        r"(?:started\s*production|now\s*operating|began\s*production|실제\s*가동|생산\s*개시)|"
        r"(?:robot(?:ic)?\s*factory|로봇\s*자동화\s*공장).{0,60}"
        r"(?:began\s*production|started\s*production|양산\s*개시|가동\s*시작)",
        re.I,
    )),
    ("robotics_partner_contract",re.compile(
        r"(?:robot(?:ic)?s?|로봇).{0,100}"
        r"(?:signed\s*(?:a\s*)?(?:binding\s*)?(?:purchase|supply|construction)\s*(?:contract|agreement)|"
        r"(?:구매|공급|시공)\s*계약\s*체결|유상\s*계약\s*체결)|"
        r"(?:signed\s*(?:a\s*)?(?:binding\s*)?(?:purchase|supply|construction)\s*(?:contract|agreement)|"
        r"(?:구매|공급|시공)\s*계약\s*체결).{0,70}(?:robot(?:ic)?s?|로봇)",
        re.I,
    )),
    ("verified_robot_demo",re.compile(
        r"(?:data\s*cent(?:er|re)|데이터\s*센터|construction|건설).{0,95}"
        r"(?:robot(?:ic)?s?|로봇).{0,60}"
        r"(?:first\s*demo(?:nstration)?\s*completed|live\s*demonstration\s*completed|"
        r"실물\s*시연\s*완료|시연\s*성공)|"
        r"(?:robot(?:ic)?s?|로봇).{0,80}"
        r"(?:data\s*cent(?:er|re)|데이터\s*센터).{0,50}"
        r"(?:시연\s*완료|live\s*demo\s*completed)",
        re.I,
    )),
    ("measured_on_site_kpi",re.compile(
        r"(?:data\s*cent(?:er|re)|데이터\s*센터|건설\s*현장).{0,100}"
        r"(?:robots?|로봇).{0,110}"
        r"(?:성공률|success\s*rate|가동률|uptime).{0,22}\d{1,3}(?:\.\d+)?\s*%|"
        r"(?:robot(?:ic)?s?|로봇).{0,65}(?:건설\s*현장|construction\s*site)"
        r".{0,75}\d{1,3}(?:\.\d+)?\s*%\s*(?:성공률|가동률|success|uptime)",
        re.I,
    )),
    ("program_canceled_or_delayed",re.compile(
        r"(?:robotics?\s*program|robot(?:ics)?\s*construction|로봇\s*프로그램|"
        r"로봇\s*건설).{0,90}(?:canceled|cancelled|paused|halted|postponed|"
        r"취소|중단|철회|지연\s*확정|연기\s*결정)",
        re.I,
    )),
)
DISQUALIFY = re.compile(
    r"미확인|not\s*yet|not\s*(?:deployed|signed|built|delivered)|"
    r"아직|계획|예정|목표|전망|could|would|will\s+(?:build|deploy|sign)|"
    r"intends?\s*to|hopes?\s*to|planning|planned|aims?\s*to|"
    r"기대|논의|검토|소문|루머|denied|부인|not\s*in\s*operation",
    re.I,
)

def match(text: str) -> bool:
    return bool(IDENTITY.search(text) and ROBOT.search(text) and INFRA.search(text))

def achieved(item: dict) -> str:
    source = str(item.get("source") or "").strip()
    if source not in COMPANY and source not in TRUSTED:
        return ""
    text = " ".join(str(item.get(k) or "") for k in ("title","description"))
    for stage,pattern in ACHIEVED:
        for m in pattern.finditer(text):
            near = text[max(0,m.start()-35):min(len(text),m.end()+25)]
            if DISQUALIFY.search(near):
                continue
            return stage
    return ""

def install(base) -> None:
    previous={name:getattr(base,name) for name in (
        "query_news","topic_group","score","key","category","meaning",
        "risk","verification","tag_for","select_diverse"
    )}

    def query_news(q):
        if q == RECOVERY_QUERY:
            if base.NOW.astimezone(base.KST).date() > RECOVERY_END_KST:
                return []
            return [{**ORIGINAL_INTERVIEW,"published":None,
                     "openai_direct_program_recovery":True}]
        return previous["query_news"](q)

    def group(text):
        return TOPIC if match(text) else previous["topic_group"](text)

    def score(item):
        text = " ".join(str(item.get(k) or "") for k in ("title","description","source"))
        if not match(text):
            return previous["score"](item)
        if item.get("openai_direct_program_recovery"):
            return 57
        stage = achieved(item)
        if not stage:
            return 0
        source = str(item.get("source") or "")
        return 73 if source in COMPANY else 32

    def key(item):
        if item.get("openai_direct_program_recovery"):
            return RECOVERY_KEY
        text = " ".join(str(item.get(k) or "") for k in ("title","description","source"))
        if not match(text):
            return previous["key"](item)
        stage = achieved(item)
        if not stage:
            return hashlib.sha256(b"openai|robotics-infra|baseline").hexdigest()
        source=str(item.get("source") or "")
        grade="issuer" if source in COMPANY else "press"
        pub=str(item.get("published") or "")[:10]
        # News-syndication URLs may vary; one achieved stage per
        # evidence source/UTC week is a stable but conservative alert unit.
        try:
            day=dt.date.fromisoformat(pub)
            period=f"{day.isocalendar().year}-W{day.isocalendar().week:02d}"
        except ValueError:
            period="undated"
        return hashlib.sha256(
            f"openai|robotics-infra|{stage}|{grade}|{period}".encode()
        ).hexdigest()

    def category(text,g):
        if g == TOPIC:
            if not match(text):return CATEGORY_BASE
            stage=achieved({"title":text,"description":"","source":"OpenAI"})
            return CATEGORY_STAGES.get(stage,CATEGORY_BASE)
        return previous["category"](text,g)

    def meaning(cat):
        if cat==CATEGORY_BASE:
            return (
                "2026년 10월 29일 Cheeky Pint에서 CEO 샘 올트먼은 "
                "기존 로봇 프로그램을 데이터센터·부품 제조 확충에 활용하겠다는 "
                "방향을 직접 설명했습니다. 실물 로봇이 실제 건설현장에 "
                "투입되었다는 발표가 아닙니다. 9월 OpenAI 자체 휴머노이드 "
                "개발·2027년 시연 목표와도 독립 사건으로 관리합니다."
            )
        if cat in CATEGORY_STAGES.values():
            return (
                "기존 장기 구상에서 새로운 실제 단계로 전진·후퇴했다는 "
                "기업/언론 근거입니다. 실물 시연·현장 배치·양산·구속력 있는 "
                "계약·실제 매출을 구분하고 고객·물량·가동률을 추가 확인합니다."
            )
        return previous["meaning"](cat)

    def risk(cat):
        if cat==CATEGORY_BASE or cat in CATEGORY_STAGES.values():
            return (
                "로봇의 설치비·안전 검증·현장 작업 성공률, 부품 제조 수율, "
                "고장·정비·교체 비용, 전력망 접속·인허가 병목이 우선 위험입니다. "
                "먼저 확인할 지표는 로봇 시제품·현장 실증·구매계약과 "
                "실제 건설 처리량이며 근거 없는 생산대수·수주금액은 산정하지 않습니다."
            )
        return previous["risk"](cat)

    def verification(item,g,text):
        if g == TOPIC:
            if item.get("openai_direct_program_recovery"):
                return (
                    "10/29 Cheeky Pint 제작사 전사 검색 색인·The Next Web 별도 보도 대조, "
                    "OpenAI 공식 로봇 엔지니어·액추에이터 제조 채용자료 확인; "
                    "제작사 전사 URL 직접 재열람 실패. CEO의 계획 발언만 확인, "
                    "현장 투입·실제 수주·매출은 확인되지 않음"
                )
            source=str(item.get("source") or "")
            grade="OpenAI 직접 발표" if source in COMPANY else "신뢰 언론 보도(회사 확정 전)"
            return f"{grade}·{achieved(item) or '사업 계획 기존 기준선'}; 실제 고객·계약·현장 규모 추가 확인 전"
        return previous["verification"](item,g,text)

    def tag(g):
        return "OpenAI 로봇·데이터센터 건설" if g==TOPIC else previous["tag_for"](g)

    def select(items,seen,force,limit):
        chosen=previous["select_diverse"](items,seen,force,limit)
        candidates=items if force else [x for x in items if x.get("key") not in seen]
        qualifying=[x for x in candidates if x.get("group")==TOPIC
                    and x.get("score",0)>=11]
        qualifying.sort(key=lambda x: (
            1 if x.get("openai_direct_program_recovery") else 0,
            x.get("score",0)),reverse=True)
        hit=qualifying[0] if qualifying else None
        if hit and not any(x.get("key")==hit.get("key") for x in chosen):
            return [hit,*chosen][:limit]
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
    for query in (RECOVERY_QUERY,*QUERIES):
        if query not in base.QUERIES:
            base.QUERIES.append(query)
