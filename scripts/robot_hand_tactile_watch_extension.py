#!/usr/bin/env python3
"""Dexterous-hand commercialization milestones on the EXISTING Physical-AI route.

Tacta's July 2026 launch, Singapore glove facility and early-2027 delivery
target; 1X's July 2026 25-DOF/5:1-15:1 hand; and reports of Tesla's planned
replaceable sensing glove are BASELINES, not newly achieved sales or tests.
No separate workflow, receiver, state file, manual backfill, or forced send.
"""
from __future__ import annotations

import datetime as dt
import hashlib
import re

GROUPS = {
    "tacta_dexterous_hand": "탁타 유체식 로봇 손·촉각",
    "one_x_neo_dexterous_hand": "1X NEO 저감속비 로봇 손",
    "tesla_optimus_hand_service": "테슬라 Optimus 손·교체형 촉각",
}
CATEGORIES = {
    "tacta_dexterous_hand": "탁타 · 로봇 손 고객 검증·계약·실제 인도",
    "one_x_neo_dexterous_hand": "1X · NEO 손 고객 실증·계약·내구성",
    "tesla_optimus_hand_service": "테슬라 · 로봇 손 촉각·조립 실제 적용",
}
OFFICIAL = {
    "tacta_dexterous_hand": {"Tacta Systems", "Tacta", "Tacta Systems Inc."},
    "one_x_neo_dexterous_hand": {"1X", "1X Technologies", "1X Technologies Inc."},
    "tesla_optimus_hand_service": {"Tesla", "Tesla, Inc.", "Tesla Investor Relations"},
}
TRUSTED = {
    "Reuters", "Bloomberg", "The Information", "The Robot Report",
    "연합뉴스", "전자신문", "조선일보", "Chosun", "ChosunBiz",
    "Automate", "Association for Advancing Automation", "TechCrunch",
    "Business Insider", "매일경제", "한국경제",
}
CONTRACT = re.compile(
    r"(?:signed|executed|entered into|signs)\s+(?:an?\s+)?(?:binding\s+)?"
    r"(?:new\s+)?(?:supply|purchase|commercial)\s+(?:agreement|contract)|"
    r"(?:공급|구매)\s*계약\s*(?:체결|확정|서명)|"
    r"(?:정식|본)\s*계약\s*(?:체결|확정)|"
    r"(?:confirmed|received)\s+(?:a\s+)?(?:new\s+)?purchase\s+order|"
    r"(?:초도|첫)\s*(?:양산\s*)?수주\s*(?:확정|완료)",
    re.I,
)
SHIPMENT = re.compile(
    r"(?:first|initial)\s+(?:customer\s+)?(?:shipments?|deliveries?)"
    r"\s+(?:started|began|completed|confirmed)|"
    r"(?:started|began|completed)\s+(?:first|initial)\s+"
    r"(?:customer\s+)?(?:shipments?|deliveries?)|"
    r"(?:shipped|delivered|ships)\s+(?:its\s+)?(?:first|initial)\s+"
    r".{0,45}(?:customer|factory|manufacturer)|"
    r"(?:초도|첫|최초)\s*(?:고객\s*)?(?:출하|납품|인도)"
    r".{0,20}(?:완료|개시|시작|확인)|"
    r"(?:출하|납품|인도)\s*(?:완료|개시|시작)",
    re.I,
)
PAID_PILOT = re.compile(
    r"(?:paid|유료).{0,35}(?:pilot|proof.of.concept|PoC|실증|검증)"
    r".{0,30}(?:completed|passed|finished|완료|통과)|"
    r"(?:pilot|proof.of.concept|PoC|실증|검증).{0,30}"
    r"(?:completed|passed|finished|완료|통과).{0,20}(?:paid|유료)",
    re.I,
)
INDEPENDENT_ENDURANCE = re.compile(
    r"(?:independent|third.party|외부\s*기관|제3자).{0,70}"
    r"(?:certif(?:ied|ication)|passed|validated|인증|통과|검증).{0,65}"
    r"(?:\d[\d,.]*\s*(?:million|백만|만|cycles?|회)|반복|내구)|"
    r"(?:\d[\d,.]*\s*(?:million|백만|만|cycles?|회)).{0,60}"
    r"(?:independent|third.party|제3자|외부\s*기관).{0,50}"
    r"(?:certif(?:ied|ication)|passed|validated|인증|통과)",
    re.I,
)
ACTUAL_GLOVE = re.compile(
    r"(?:replaceable|replac(?:ed|ement)|교체형|교환형).{0,38}"
    r"(?:sensing|tactile|touch|촉각|센서).{0,25}"
    r"(?:glove|장갑|skin|피부).{0,65}"
    r"(?:installed|integrated|deployed|production|적용|장착|탑재|양산)|"
    r"(?:sensing|tactile|touch|촉각).{0,20}(?:glove|장갑).{0,60}"
    r"(?:installed|integrated|deployed|production|양산\s*적용|장착|탑재)",
    re.I,
)
ACTUAL_ASSEMBLY = re.compile(
    r"(?:robot\s*hand|Optimus\s*hand|로봇\s*손|손\s*조립).{0,65}"
    r"(?:assembly\s*line|조립\s*공정).{0,38}"
    r"(?:automated|automation\s*completed|commissioned|자동화\s*완료|가동\s*개시)|"
    r"(?:hand\s*assembly|손\s*조립).{0,25}"
    r"(?:자동화\s*완료|라인\s*가동\s*개시|commissioned)",
    re.I,
)
NEGATION = re.compile(
    r"\b(?:not|never|denied|deny|unconfirmed|without|no)\b|"
    r"아직|미확인|부인|체결하지|납품하지|실시하지|완료되지|사실이\s*아닌", re.I
)
FUTURE = re.compile(
    r"\b(?:will|would|may|could|plans?|planned|planning|expected|"
    r"target(?:s|ed)?|aims?|scheduled|hopes?)\b|"
    r"예정|계획|목표|기대|전망|추진|검토|향후|내년|차후", re.I
)
QUERIES = (
    '(Tacta Systems OR TactaBot OR "Tacta Hand") '
    '(fluidic tendon OR paid pilot OR first shipment OR customer contract OR '
    'commercial deployment OR 촉각 OR 초도 납품 OR 고객 검증)',
    '(탁타 시스템즈 OR 탁타 핸드) '
    '(유체식 힘줄 OR 촉각 장갑 OR 고객 계약 OR 실제 납품 OR 반복 작업 내구성)',
    '("1X Technologies" OR "1X NEO") '
    '(robot hands OR tendon drive OR hand reliability OR customer deployment OR '
    'independent endurance OR force control)',
    '(Tesla Optimus OR 테슬라 옵티머스) '
    '(replaceable sensing glove OR hand assembly automation OR tactile sensor '
    'integration OR 교체형 촉각 센서 OR 로봇 손 조립 자동화)',
)

def identity(text: str) -> str:
    if re.search(r"Tacta\s*(?:Systems|Hand|Bot|Glove)|탁타\s*(?:시스템즈|핸드)", text, re.I):
        if re.search(r"hand|glove|robot|tendon|손|로봇|촉각|유체", text, re.I):
            return "tacta_dexterous_hand"
    if re.search(r"(?:\b1X\b|1X\s*Technologies)", text, re.I):
        if re.search(r"NEO|robot.*hand|robot.*finger|tendon|tactile|"
                     r"로봇\s*손|힘줄|촉각|손가락", text, re.I):
            return "one_x_neo_dexterous_hand"
    if re.search(r"Tesla|테슬라", text, re.I) and re.search(r"Optimus|옵티머스", text, re.I):
        if re.search(r"특허|patent|US20260310299", text, re.I):
            return ""  # Existing Tesla patent lane keeps its own evidence/key.
        if re.search(r"sensing\s*glove|tactile\s*glove|replaceable\s*(?:touch|tactile)"
                     r"|hand\s*assembly|robot\s*hand\s*(?:sensors?|reliability)"
                     r"|교체형\s*(?:촉각|센서)|손\s*조립\s*자동화", text, re.I):
            return "tesla_optimus_hand_service"
    return ""

def _verified_phrase(text: str, pattern: re.Pattern) -> bool:
    for match in pattern.finditer(text):
        before = text[max(0, match.start() - 44):match.start()]
        after = text[match.end():match.end() + 18]
        if NEGATION.search(before[-36:] + after):
            continue
        if FUTURE.search(before[-24:] + after[:12]):
            continue
        return True
    return False

def milestone(item: dict, group: str) -> str:
    text = " ".join(str(item.get(k) or "") for k in ("title", "description"))
    if not group:
        return ""
    if _verified_phrase(text, SHIPMENT):
        return "customer_shipment"
    if _verified_phrase(text, CONTRACT):
        return "binding_contract"
    if _verified_phrase(text, PAID_PILOT):
        return "paid_pilot_completed"
    if _verified_phrase(text, INDEPENDENT_ENDURANCE):
        return "independent_endurance_passed"
    if group == "tesla_optimus_hand_service":
        if _verified_phrase(text, ACTUAL_GLOVE):
            return "replaceable_glove_in_production"
        if _verified_phrase(text, ACTUAL_ASSEMBLY):
            return "hand_assembly_automation_started"
    return "baseline"

def tier(item: dict, group: str) -> str:
    source = str(item.get("source") or "").strip()
    if source in OFFICIAL.get(group, set()):
        return "official"
    if source in TRUSTED:
        return "reported"
    return ""

def _identity_key(item: dict, group: str, stage: str, evidence: str) -> str:
    text = " ".join(str(item.get(k) or "") for k in ("title", "description"))
    match = re.search(r"(?<!\d)(20\d{2})[-./](\d{1,2})[-./](\d{1,2})(?!\d)", text)
    stamp = ""
    if match:
        try:
            stamp = dt.date(*(int(v) for v in match.groups())).isoformat()
        except ValueError:
            pass
    if not stamp:
        stamp = str(item.get("published") or "")[:10]
    try:
        day = dt.date.fromisoformat(stamp)
        period = f"{day.isocalendar().year}-W{day.isocalendar().week:02d}"
    except ValueError:
        period = "undated-" + hashlib.sha256(
            re.sub(r"\s+", " ", str(item.get("title") or "").lower()).encode()
        ).hexdigest()[:12]
    # Same company/stage/evidence within a published event week is one alert,
    # across media syndications. Reported and official are different evidence
    # upgrades. New weeks can alert on a new milestone of the same type.
    raw = f"dexterous-hand-v1|{group}|{stage}|{evidence}|{period}"
    return hashlib.sha256(raw.encode()).hexdigest()

def install(base) -> None:
    previous = {
        "group": base.topic_group, "score": base.score, "key": base.key,
        "category": base.category, "meaning": base.meaning, "risk": base.risk,
        "verification": base.verification, "tag": base.tag_for,
        "select": base.select_diverse,
    }

    def group(text):
        return identity(text) or previous["group"](text)

    def score(item):
        text = " ".join(str(item.get(k) or "") for k in ("title", "description", "source"))
        g = identity(text)
        if not g:
            return previous["score"](item)
        m = milestone(item, g)
        t = tier(item, g)
        if not t or m == "baseline":
            return 0
        if m in {"customer_shipment", "binding_contract"}:
            return 74 if t == "official" else 36
        if m == "paid_pilot_completed":
            return 55 if t == "official" else 30
        if m in {"independent_endurance_passed",
                 "replaceable_glove_in_production", "hand_assembly_automation_started"}:
            return 52 if t == "official" else 27
        return 0

    def key(item):
        text = " ".join(str(item.get(k) or "") for k in ("title", "description", "source"))
        g = identity(text)
        if not g:
            return previous["key"](item)
        m = milestone(item, g)
        t = tier(item, g)
        return _identity_key(item, g, m, t or "unverified")

    def category(text, g):
        return CATEGORIES[g] if g in GROUPS else previous["category"](text, g)

    def meaning(cat):
        if cat == CATEGORIES["tacta_dexterous_hand"]:
            return ("탁타 손·유체식 힘줄·촉각 장갑의 2026년 공개는 기존 사실입니다. "
                    "새로운 고객의 유료 검증, 구속력 있는 계약, 실제 인도와 매출을 단계별로 확인합니다. "
                    "2027년 초 인도 목표는 완료 실적이 아닙니다.")
        if cat == CATEGORIES["one_x_neo_dexterous_hand"]:
            return ("1X NEO의 25자유도, 감속비 5:1~15:1은 2026년 7월 공개된 기존 기술입니다. "
                    "새로운 유료 실증·고객 발주·반복 작업 성능의 확인 여부가 핵심입니다.")
        if cat == CATEGORIES["tesla_optimus_hand_service"]:
            return ("교체형 촉각 장갑의 개발 계획과 실제 양산 손에 적용한 사실을 분리합니다. "
                    "손 조립 공정 자동화·센서 교체주기·불량률은 옵티머스 원가와 가동률에 직결됩니다.")
        return previous["meaning"](cat)

    def risk(cat):
        if cat == CATEGORIES["tacta_dexterous_hand"]:
            return ("밀봉·유체 누출, 압력 응답 지연, 피스톤 수명, 손끝 촉각센서 드리프트와 "
                    "고객 공장 검수·실제 매출 인식 여부를 확인합니다.")
        if cat == CATEGORIES["one_x_neo_dexterous_hand"]:
            return ("낮은 감속비에서 필요한 전류·발열, 케이블 마모·장력 보정, "
                    "현장 안전성·고장 간 평균 운전시간을 확인합니다.")
        if cat == CATEGORIES["tesla_optimus_hand_service"]:
            return ("교체형 장갑 계획을 설치 완료로 혼동하지 않고, 손 조립 수율·센서 "
                    "수명·교체비·반복 작업 실패율을 확인합니다.")
        return previous["risk"](cat)

    def verification(item, g, text):
        if g in GROUPS:
            state = milestone(item, g)
            level = tier(item, g)
            source = str(item.get("source") or "출처 미확인")
            kind = "기업 직접 발표" if level == "official" else (
                "신뢰 언론 보도" if level == "reported" else "독립 확인 전")
            return (f"{source} · {kind} · {state}. 공급계약·시험 통과·실제 출하 중 "
                    "보도된 단계만 표시; 고객 실명·물량·매출은 별도 검증")
        return previous["verification"](item, g, text)

    def tag(g):
        return GROUPS[g] if g in GROUPS else previous["tag"](g)

    def select(items, seen, force, limit):
        selected = previous["select"](items, seen, force, limit)
        eligible = items if force else [x for x in items if x.get("key") not in seen]
        special = [x for x in eligible if x.get("group") in GROUPS
                   and x.get("score", 0) >= 11]
        special.sort(key=lambda x: x.get("score", 0), reverse=True)
        for item in reversed(special[:3]):
            if not any(x.get("key") == item.get("key") for x in selected):
                selected = [item, *selected][:limit]
        # Never let a lower-confidence press retelling displace a same-period
        # company announcement for the same company and achieved stage.
        chosen = []
        official = { (x.get("group"), milestone(x, x.get("group")))
                     for x in selected if x.get("group") in GROUPS
                     and tier(x, x.get("group")) == "official" }
        for x in selected:
            if (x.get("group") in GROUPS
                and tier(x, x.get("group")) == "reported"
                and (x.get("group"), milestone(x, x.get("group"))) in official):
                continue
            chosen.append(x)
        return chosen

    base.topic_group = group
    base.score = score
    base.key = key
    base.category = category
    base.meaning = meaning
    base.risk = risk
    base.verification = verification
    base.tag_for = tag
    base.select_diverse = select
    for query in QUERIES:
        if query not in base.QUERIES:
            base.QUERIES.append(query)
