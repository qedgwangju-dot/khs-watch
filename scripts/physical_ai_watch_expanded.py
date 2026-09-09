#!/usr/bin/env python3
"""Expanded high-signal layer for the physical-AI Telegram watcher.

Adds four lanes:
- Samhyun humanoid actuator customer / prototype / mass-production funnel
- XPENG IRON production-line and commercialization milestones
- LG Electronics AXIUM / Bear Robotics commercialization and valuation events
- Frontier-AI -> robotics only when an explicit robot integration / action-model link exists

Generic frontier-model launches are deliberately excluded from robot alerts.
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import physical_ai_watch_readable as readable

ext = readable.ext
base = readable.base

base.QUERIES.extend([
    '(삼현 OR SAMHYUN) (휴머노이드 OR humanoid OR 로봇 OR robot) (액추에이터 OR actuator OR 모터 OR 감속기 OR 제어기) (20곳 OR 20개 OR 4건 OR 프로토타입 OR prototype OR 양산 OR 수주 OR 고객 OR 공급)',
    '(삼현 OR SAMHYUN) (액추에이터 OR actuator) (생산능력 OR capacity OR 50만 OR 100만 OR 150만 OR 창원 2공장 OR 5PPM)',
    '(XPENG OR 샤오펑 OR 小鹏) (IRON OR 휴머노이드 OR humanoid OR 人形机器人) (양산 OR mass production OR 생산라인 OR production line OR 출하 OR delivery OR 2026 OR 2027)',
    '(LG전자 OR "LG Electronics") (AXIUM OR 악시움 OR 액추에이터 OR actuator) (빅테크 OR "Big Tech" OR 수주 OR 공급 OR 고객 OR 10월 OR October OR 양산 OR mass production)',
    '(베어로보틱스 OR "Bear Robotics") (상장 OR IPO OR Nasdaq OR 나스닥 OR 프리IPO OR pre-IPO OR 투자유치 OR valuation)',
    '(GPT-6 Astra OR OpenAI OR "Gemini Robotics" OR "frontier AI" OR 프런티어AI) (robotics OR 로보틱스 OR robot OR 로봇 OR humanoid OR 휴머노이드 OR embodied AI OR 피지컬AI) (planning OR reasoning OR action model OR 행동모델 OR VLA OR RFM OR robot foundation model OR 배치 OR deployment OR integration OR 통합)',
])

base.TRUSTED.update({
    '이데일리', 'EDAILY', '뉴스핌', 'Investors Business Daily', 'Reuters',
})
base.OFFICIAL_OR_PRIMARY.update({
    'XPENG', 'XPeng', '小鹏汽车', 'LG전자', 'LG Electronics',
})
base.MAX_ALERTS = 8

_orig_topic_group = base.topic_group
_orig_score = base.score
_orig_category = base.category
_orig_meaning = base.meaning
_orig_risk = base.risk
_orig_verification = base.verification
_orig_same_event = ext._same_event


def topic_group(text: str) -> str | None:
    if re.search(r'삼현|SAMHYUN', text, re.I) and re.search(r'휴머노이드|humanoid|로봇|robot|액추에이터|actuator', text, re.I):
        return 'samhyun'
    if re.search(r'XPENG|샤오펑|小鹏', text, re.I) and re.search(r'IRON|휴머노이드|humanoid|人形机器人', text, re.I):
        return 'xpeng'
    if re.search(r'LG전자|LG Electronics|베어로보틱스|Bear Robotics', text, re.I) and re.search(r'AXIUM|악시움|액추에이터|actuator|베어로보틱스|Bear Robotics|상장|IPO|프리IPO|pre-IPO', text, re.I):
        return 'lg_robotics'
    if re.search(r'GPT-6\s*Astra|OpenAI|Gemini Robotics|frontier AI|프런티어\s*AI', text, re.I):
        robot = re.search(r'robotics|로보틱스|robot|로봇|humanoid|휴머노이드|embodied AI|피지컬\s*AI', text, re.I)
        action = re.search(r'planning|reasoning|action\s*model|행동\s*모델|VLA|RFM|robot\s*foundation\s*model|배치|deployment|integration|통합|제어', text, re.I)
        if robot and action:
            return 'frontier_ai'
    return _orig_topic_group(text)


def score(item: dict) -> int:
    title = item.get('title', '')
    text = f"{title} {item.get('description','')} {item.get('source','')}"
    group = topic_group(text)
    source = item.get('source') or ''

    if group == 'samhyun':
        s = 10
        if base.NUMERIC.search(text): s += 3
        if re.search(r'20\s*(?:곳|개|companies)|20곳\s*이상', text, re.I): s += 4
        if re.search(r'4\s*건|글로벌\s*2건|국내\s*2건|prototype|프로토타입|Award|수주\s*성공', text, re.I): s += 5
        if re.search(r'양산|mass production|창원\s*2공장|50만|100만|150만|5\s*PPM', text, re.I): s += 4
        if source in base.TRUSTED: s += 2
        return s

    if group == 'xpeng':
        s = 11
        if base.NUMERIC.search(text): s += 3
        if re.search(r'생산라인|production line|产线|양산|mass production|量产|80%', text, re.I): s += 5
        if re.search(r'2026|2027|delivery|인도|출하|rolls off|walks off', text, re.I): s += 3
        if source in base.OFFICIAL_OR_PRIMARY: s += 5
        elif source in base.TRUSTED: s += 3
        return s

    if group == 'lg_robotics':
        s = 10
        if base.NUMERIC.search(text): s += 3
        if re.search(r'AXIUM|악시움|액추에이터|actuator', text, re.I): s += 3
        if re.search(r'빅테크|Big Tech|10월|October|수주|공급|고객|양산|mass production', text, re.I): s += 5
        if re.search(r'베어로보틱스|Bear Robotics', text, re.I) and re.search(r'상장|IPO|프리IPO|pre-IPO|Nasdaq|나스닥|결정된\s*바\s*없', text, re.I): s += 4
        if source in base.OFFICIAL_OR_PRIMARY: s += 4
        elif source in base.TRUSTED: s += 2
        return s

    if group == 'frontier_ai':
        # A model launch by itself is NOT a robot signal. Require an explicit
        # robot action/planning/deployment/integration link in the story text.
        robot = re.search(r'robotics|로보틱스|robot|로봇|humanoid|휴머노이드|embodied AI|피지컬\s*AI', text, re.I)
        action = re.search(r'planning|reasoning|action\s*model|행동\s*모델|VLA|RFM|robot\s*foundation\s*model|배치|deployment|integration|통합|제어', text, re.I)
        if not (robot and action):
            return -30
        s = 9
        if re.search(r'실제\s*로봇|real[- ]world|현장|deployment|배치|통합|integration|채택|adopt', text, re.I): s += 5
        if re.search(r'성공률|success rate|비용|cost|latency|지연|benchmark|벤치마크', text, re.I): s += 3
        if source in base.OFFICIAL_OR_PRIMARY or source in base.TRUSTED: s += 3
        return s

    return _orig_score(item)


def _raw_cat(text: str, group: str) -> str:
    if group == 'samhyun':
        if re.search(r'생산능력|capacity|창원\s*2공장|50만|100만|150만', text, re.I):
            return '생산능력·양산 준비'
        return '고객 파이프라인·양산 프로토타입'
    if group == 'xpeng':
        return 'IRON 생산라인·양산 전환'
    if group == 'lg_robotics':
        if re.search(r'베어로보틱스|Bear Robotics', text, re.I) and re.search(r'상장|IPO|프리IPO|pre-IPO|Nasdaq|나스닥', text, re.I):
            return '베어로보틱스 가치·상장 상태'
        return 'AXIUM 고객·수주 전환'
    if group == 'frontier_ai':
        return '프런티어AI→로봇 지능'
    return _orig_category(text, group).split(' · ', 1)[-1]


def _lane(group: str) -> str:
    return {
        'samhyun': '삼현',
        'xpeng': '샤오펑 IRON',
        'lg_robotics': 'LG 로보틱스',
        'frontier_ai': '프런티어 AI',
    }.get(group, '')


def category(text: str, group: str) -> str:
    if group in {'samhyun','xpeng','lg_robotics','frontier_ai'}:
        return f"{_lane(group)} · {_raw_cat(text, group)}"
    return _orig_category(text, group)


def meaning(cat: str) -> str:
    raw = cat.split(' · ', 1)[-1]
    mapping = {
        '고객 파이프라인·양산 프로토타입': '삼현이 단순 샘플 협의를 넘어 양산 프로토타입 계약과 다수 글로벌 고객 파이프라인을 확보하는지 봅니다. 4건의 Award가 실제 양산 수주·납품 물량으로 전환되는지가 핵심입니다.',
        '생산능력·양산 준비': '고객 요청에 앞서 액추에이터·모터 생산능력을 선제 확대하는 단계입니다. 가동률과 수율이 동반되면 외부 휴머노이드 OEM 주문을 빠르게 매출로 전환할 수 있습니다.',
        'IRON 생산라인·양산 전환': '샤오펑 IRON이 연구 시제품에서 실제 생산라인 제조로 넘어간 신호입니다. 2026년 말 양산과 2027년 외부 고객 인도가 물량·부품 발주로 연결되는지 봅니다.',
        'AXIUM 고객·수주 전환': 'LG전자가 AXIUM을 기술 공개 단계에서 글로벌 고객 수주 단계로 옮기는 신호입니다. 10월 빅테크 기술·생산 미팅 이후 고객 실명·계약 물량이 나오는지가 핵심입니다.',
        '베어로보틱스 가치·상장 상태': '베어로보틱스의 외부 가치평가·자금조달·상장 상태가 LG전자 로봇 자산의 시장가치 기준점으로 작용할 수 있습니다.',
        '프런티어AI→로봇 지능': '프런티어 모델 자체 성능이 아니라 실제 로봇의 계획·추론·행동모델·현장 배치에 연결되는지를 봅니다. 로봇 성공률·시도비용·지연시간이 개선될 때만 구조 변화로 판단합니다.',
    }
    return mapping.get(raw, _orig_meaning(cat))


def risk(cat: str) -> str:
    raw = cat.split(' · ', 1)[-1]
    mapping = {
        '고객 파이프라인·양산 프로토타입': '프로토타입 계약은 대량 양산 계약과 다릅니다. 고객 실명·단가·납기·반복 발주와 실제 양산 수주 전환을 확인해야 합니다.',
        '생산능력·양산 준비': '증설이 주문보다 앞서면 가동률·감가상각 부담이 먼저 커질 수 있습니다. 생산능력보다 실제 양산 수주가 더 중요합니다.',
        'IRON 생산라인·양산 전환': '생산라인 가동과 대량 판매는 다릅니다. 수율·주간 생산량·실제 인도 대수·안전성 검증이 늦어지면 상용화 일정이 밀릴 수 있습니다.',
        'AXIUM 고객·수주 전환': '현재는 수주 협의 단계이며 특정 빅테크 계약은 아직 확정되지 않았습니다. 10월 미팅 이후 고객 인증·납품 단가·수량을 확인해야 합니다.',
        '베어로보틱스 가치·상장 상태': '상장 보도와 확정 일정은 구분해야 합니다. LG전자는 해외 상장에 대해 결정된 바 없다고 공시한 만큼 실제 이사회·공시·투자조건을 우선합니다.',
        '프런티어AI→로봇 지능': 'GPT-6 Astra 같은 모델의 일반 추론 성능만으로 로봇 상용화를 확정할 수 없습니다. 실제 로봇 통합·행동 성공률·지연·안전 검증이 없으면 알림하지 않습니다.',
    }
    return mapping.get(raw, _orig_risk(cat))


def verification(item: dict, group: str, text: str) -> str:
    source = item.get('source') or ''
    if group == 'samhyun':
        return 'CEO 간담회·증권사 기반 보도 · 양산 수주 전환 확인 필요'
    if group == 'xpeng':
        return 'XPENG 공식자료' if source in base.OFFICIAL_OR_PRIMARY else '공식 일정과 교차확인된 보도'
    if group == 'lg_robotics':
        if re.search(r'결정된\s*바\s*없', text, re.I):
            return 'LG전자 해명공시 기반'
        if re.search(r'AXIUM|악시움|액추에이터|actuator', text, re.I):
            return 'LG전자 임원 발언·복수 보도 · 계약 전'
    if group == 'frontier_ai':
        return '로봇 적용 근거가 명시된 자료만 통과'
    return _orig_verification(item, group, text)


def same_event(a: dict, b: dict) -> bool:
    if _orig_same_event(a, b):
        return True
    if a.get('group') != b.get('group'):
        return False
    ta = f"{a.get('title','')} {a.get('description','')}"
    tb = f"{b.get('title','')} {b.get('description','')}"
    g = a.get('group')
    if g == 'samhyun':
        if re.search(r'20\s*(?:곳|개)|4\s*건|프로토타입|prototype|양산', ta, re.I) and re.search(r'20\s*(?:곳|개)|4\s*건|프로토타입|prototype|양산', tb, re.I):
            return True
    if g == 'xpeng' and re.search(r'IRON', ta, re.I) and re.search(r'IRON', tb, re.I):
        if re.search(r'생산라인|production line|양산|mass production|2026|2027', ta, re.I) and re.search(r'생산라인|production line|양산|mass production|2026|2027', tb, re.I):
            return True
    if g == 'lg_robotics':
        ax_a = re.search(r'AXIUM|악시움|액추에이터|actuator', ta, re.I)
        ax_b = re.search(r'AXIUM|악시움|액추에이터|actuator', tb, re.I)
        if ax_a and ax_b and re.search(r'빅테크|Big Tech|10월|October|수주', ta, re.I) and re.search(r'빅테크|Big Tech|10월|October|수주', tb, re.I):
            return True
        bear_a = re.search(r'베어로보틱스|Bear Robotics', ta, re.I) and re.search(r'상장|IPO|프리IPO|pre-IPO|Nasdaq|나스닥', ta, re.I)
        bear_b = re.search(r'베어로보틱스|Bear Robotics', tb, re.I) and re.search(r'상장|IPO|프리IPO|pre-IPO|Nasdaq|나스닥', tb, re.I)
        if bear_a and bear_b:
            return True
    return False


def select_diverse(items: list[dict], seen: set[str], force: bool, limit: int) -> list[dict]:
    candidates = items if force else [x for x in items if x['key'] not in seen]
    candidates = ext._dedupe_events(candidates)
    if not candidates:
        return []
    chosen: list[dict] = []
    used: set[str] = set()
    priority = ['tesla','xpeng','samhyun','lg_robotics','robotis','battery','frontier_ai','wonik','byd_paxini']
    for group in priority:
        for x in candidates:
            if x.get('group') == group and x['key'] not in used:
                chosen.append(x); used.add(x['key']); break
        if len(chosen) >= limit:
            return chosen
    for x in candidates:
        if x['key'] in used:
            continue
        chosen.append(x); used.add(x['key'])
        if len(chosen) >= limit:
            break
    return chosen

# Dynamic hooks used by base.main() and ext._dedupe_events().
ext._same_event = same_event
base.topic_group = topic_group
base.score = score
base.category = category
base.meaning = meaning
base.risk = risk
base.verification = verification
base.select_diverse = select_diverse

if __name__ == '__main__':
    base.main()
