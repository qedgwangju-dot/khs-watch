#!/usr/bin/env python3
"""Extension layer for the physical-AI Telegram watcher.

Adds two high-signal lanes without duplicating the base watcher:
1) Microduck / Reachy Mini sales milestones -> implied ROBOTIS actuator demand
2) WONIK Holdings / WONIK Robotics commercialization, policy and customer expansion
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import robotis_physical_ai_watch as base

# Broaden discovery while keeping the existing dedup state/output format.
base.QUERIES.extend([
    '(Microduck OR 마이크로덕 OR "Reachy Mini" OR 리치미니) (판매 OR 판매량 OR sold OR sales OR orders OR 주문 OR 15000 OR 15,000 OR 20000 OR 20,000) (ROBOTIS OR 로보티즈 OR DYNAMIXEL OR 액추에이터)',
    '(Microduck OR 마이크로덕) (15000 OR 15,000 OR 1만5000 OR 1.5만 OR 600만달러 OR "6 million")',
    '(원익홀딩스 OR 원익로보틱스 OR "WONIK Robotics" OR "WONIK Holdings") (로봇 OR 휴머노이드 OR humanoid OR 피지컬AI OR "physical AI") (상용화 OR 양산 OR 공급 OR 수주 OR 고객 OR 사업확장 OR 사업 확장 OR 정책 OR 예산 OR 육성)',
    '(원익로보틱스 OR "WONIK Robotics") (Allegro Hand OR 알레그로핸드 OR 알레그로 OR AMMR OR AMR OR 로봇핸드 OR 모바일휴머노이드 OR 모바일 휴머노이드 OR Roboligent OR 로볼리전트)',
    '(원익홀딩스 OR 원익로보틱스) (지능형로봇 OR 지능형 로봇 OR 정부 OR 산업부 OR 과기정통부 OR 정책 OR 예산 OR 규제 OR 실증 OR 조달)',
])

base.TRUSTED.update({
    "아이뉴스24", "iNews24", "The Information",
})
base.OFFICIAL_OR_PRIMARY.update({
    "원익로보틱스", "WONIK Robotics",
})
base.MAX_ALERTS = max(base.MAX_ALERTS, 9)

_orig_topic_group = base.topic_group
_orig_score = base.score
_orig_category = base.category
_orig_tag_for = base.tag_for
_orig_meaning = base.meaning
_orig_risk = base.risk
_orig_verification = base.verification


def topic_group(text: str) -> str | None:
    if re.search(r"원익홀딩스|원익로보틱스|WONIK Holdings|WONIK Robotics|Allegro Hand|알레그로핸드", text, re.I):
        return "wonik"
    return _orig_topic_group(text)


def score(item: dict) -> int:
    text = f"{item.get('title','')} {item.get('description','')} {item.get('source','')}"
    group = topic_group(text)

    if group == "wonik":
        source = item.get("source") or ""
        s = 7
        if base.NUMERIC.search(text):
            s += 2
        if source in base.OFFICIAL_OR_PRIMARY:
            s += 5
        elif source in base.TRUSTED:
            s += 3
        if re.search(r"상용화|정책|예산|육성|규제|실증|조달|정부|산업부|과기정통부", text, re.I):
            s += 4
        if re.search(r"공급|수주|고객|양산|생산|배치|투입|계약|MOU|협력|사업\s*확장|신제품|출시", text, re.I):
            s += 5
        if re.search(r"Allegro Hand|알레그로|AMMR|AMR|Roboligent|로볼리전트", text, re.I):
            s += 3
        return s

    s = _orig_score(item)
    if group == "robotis" and re.search(r"Microduck|마이크로덕|Reachy Mini|리치미니", text, re.I):
        if re.search(r"판매|판매량|sold|sales|orders|주문|15000|15,000|1만5000|1\.5만", text, re.I):
            s += 5
        if re.search(r"15개|15\s*(?:actuators?|motors?)|22\.5만|225,?000", text, re.I):
            s += 3
    return s


def category(text: str, group: str) -> str:
    if group == "wonik":
        if re.search(r"정책|예산|육성|규제|정부|산업부|과기정통부|조달", text, re.I):
            return "정책·상용화"
        return "원익로보틱스 사업 확장"
    if group == "robotis" and re.search(r"Microduck|마이크로덕|Reachy Mini|리치미니", text, re.I) and re.search(r"판매|판매량|sold|sales|orders|주문", text, re.I):
        return "판매량×액추에이터 수요"
    return _orig_category(text, group)


def tag_for(group: str) -> str:
    if group == "wonik":
        return "원익로보틱스"
    return _orig_tag_for(group)


def meaning(cat: str) -> str:
    if cat == "판매량×액추에이터 수요":
        return "완제품 판매대수에 대당 액추에이터 탑재량을 곱해 ROBOTIS의 잠재 부품 수요를 바로 검산합니다. 예를 들어 Microduck 1.5만대×15개면 22.5만개로, 지난해 ROBOTIS 연간 실제 출하량 약 22만개와 맞먹는 규모입니다."
    if cat == "정책·상용화":
        return "정부 로봇 상용화·실증·예산 확대가 원익로보틱스의 Allegro Hand·AMR·AMMR·모바일 휴머노이드 사업에 실제 고객·조달·양산으로 연결되는지 봅니다."
    if cat == "원익로보틱스 사업 확장":
        return "원익로보틱스가 로봇핸드 중심 연구개발 사업에서 AMR·AMMR·모바일 휴머노이드와 산업 자동화 고객으로 매출 경로를 넓히는 신호인지 확인합니다."
    return _orig_meaning(cat)


def risk(cat: str) -> str:
    if cat == "판매량×액추에이터 수요":
        return "22.5만개는 판매대수×15개로 계산한 내재 수요입니다. ROBOTIS가 22.5만개를 이미 출하·매출 인식했다는 뜻은 아니므로 실제 납품·생산·재고 변화를 따로 확인해야 합니다."
    if cat == "정책·상용화":
        return "정책 수혜 기대와 확정 매출은 다릅니다. 세부 예산 집행, 조달 공고, 고객 실명, 납품 대수와 원익로보틱스 수주 공시가 없으면 주가 테마에 그칠 수 있습니다."
    if cat == "원익로보틱스 사업 확장":
        return "MOU·전시·시제품만으로 양산 매출을 확정할 수 없습니다. 반복 주문, 설치 대수, 가동률과 유지보수 매출을 확인해야 합니다."
    return _orig_risk(cat)


def verification(item: dict, group: str, text: str) -> str:
    if group == "wonik":
        source = item.get("source") or ""
        if source in base.OFFICIAL_OR_PRIMARY:
            return "회사 공식자료"
        if source in base.TRUSTED:
            return "신뢰 매체 보도 · 회사/정부 원문 재확인"
        return "보도 단계 · 회사/정부 원문 재확인 필요"
    if group == "robotis" and re.search(r"Microduck|마이크로덕", text, re.I) and re.search(r"판매|sold|sales|orders", text, re.I):
        return "판매 보도 + 대당 15개 탑재 교차확인 · 실제 ROBOTIS 출하량은 별도"
    return _orig_verification(item, group, text)


def select_diverse(items: list[dict], seen: set[str], force: bool, limit: int) -> list[dict]:
    candidates = items if force else [x for x in items if x["key"] not in seen]
    if not candidates:
        return []
    chosen: list[dict] = []
    used: set[str] = set()
    for group in ["tesla", "battery", "robotis", "wonik", "byd_paxini"]:
        for x in candidates:
            if x.get("group") == group and x["key"] not in used:
                chosen.append(x)
                used.add(x["key"])
                break
        if len(chosen) >= limit:
            return chosen
    for x in candidates:
        if x["key"] in used:
            continue
        chosen.append(x)
        used.add(x["key"])
        if len(chosen) >= limit:
            break
    return chosen


# Monkey-patch extension hooks used by base.main().
base.topic_group = topic_group
base.score = score
base.category = category
base.tag_for = tag_for
base.meaning = meaning
base.risk = risk
base.verification = verification
base.select_diverse = select_diverse

if __name__ == "__main__":
    base.main()
