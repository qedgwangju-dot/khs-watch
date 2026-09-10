#!/usr/bin/env python3
"""Add an LG Electronics physical-AI factory/data/actuator monetization lane.

This lane follows the actual value chain rather than generic robot headlines:
smart-factory orders -> MoMA/CLOiD deployment -> real factory/logistics data ->
Data Factory + NVIDIA augmentation -> RFM improvement -> actuator/customer
qualification -> external robot/smart-factory sales.

Guardrails:
- Smart-factory order intake is not humanoid revenue.
- 100,000 training hours may include synthetic/augmented data; it is not
  automatically 100,000 hours of real robot operation.
- LG ownership/affiliation with Bear Robotics, Robostar or ROBOTIS does not
  prove a component supply contract.
- Pilot/initial actuator production is separated from mass-production orders.
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import physical_ai_watch_robotis_nvidia as nv

base = nv.base
ext = nv.ext

base.QUERIES.extend([
    '("LG전자" OR "LG Electronics") (스마트팩토리 OR "smart factory") (수주 OR order OR 매출 OR revenue OR MoMA OR CLOiD OR 로봇 OR robot)',
    '("LG전자" OR "LG Electronics") (데이터팩토리 OR "Data Factory" OR "100,000 hours" OR "100000 hours" OR "10만 시간" OR "10,000 square meters" OR "1만㎡") (NVIDIA OR 엔비디아 OR Cosmos OR Omniverse OR Isaac OR RFM OR 로봇)',
    '("LG전자" OR "LG Electronics") (액추에이터 OR actuator) (초도생산 OR "initial production" OR 시험생산 OR pilot OR 양산 OR "mass production" OR 수주 OR order OR 고객 OR customer OR qualification OR 검증 OR 10월)',
    '("LG전자" OR "LG Electronics") (MoMA OR CLOiD OR 클로이드 OR 이동형로봇 OR "mobile manipulator") (공장 OR factory OR 물류 OR logistics OR 배치 OR deployment OR 가동률 OR uptime OR 고객 OR customer)',
    '("LG CNS" OR "LG이노텍" OR "LG Innotek" OR "Bear Robotics" OR 베어로보틱스 OR 로보스타 OR ROBOTIS OR 로보티즈) ("LG전자" OR "LG Electronics") (피지컬AI OR "physical AI" OR 데이터팩토리 OR "Data Factory" OR 로봇 OR robotics OR actuator OR 액추에이터)',
    '("LG전자" OR "LG Electronics") (NVIDIA OR 엔비디아) (로봇 OR robotics OR 피지컬AI OR "physical AI") (데이터 OR data OR RFM OR Cosmos OR Omniverse OR Isaac OR 상용화 OR commercialization)',
])

base.TRUSTED.update({
    '전자신문', '연합뉴스', '서울경제', '한국경제', '매일경제', '이데일리',
    'ZDNet Korea', 'The Korea Economic Daily', 'Maeil Business Newspaper',
})
base.OFFICIAL_OR_PRIMARY.update({
    'LG전자', 'LG Electronics', 'LG Newsroom', 'LG Global Newsroom',
    'LG CNS', 'LG Innotek', 'NVIDIA', 'NVIDIA Developer',
})

_orig_topic_group = base.topic_group
_orig_score = base.score
_orig_category = base.category
_orig_meaning = base.meaning
_orig_risk = base.risk
_orig_verification = base.verification
_orig_same_event = ext._same_event

LG = re.compile(r'LG전자|LG Electronics', re.I)
SMART_FACTORY = re.compile(r'스마트\s*팩토리|smart\s*factory', re.I)
DATA_FACTORY = re.compile(r'데이터\s*팩토리|Data\s*Factory|100,?000\s*hours|100000\s*hours|10만\s*시간|10,?000\s*(?:square\s*meters|㎡)|1만\s*㎡|data\s*flywheel|데이터\s*플라이휠', re.I)
ACTUATOR = re.compile(r'액추에이터|actuator', re.I)
FIELD_ROBOT = re.compile(r'\bMoMA\b|\bCLOiD\b|클로이드|mobile\s*manipulator|이동형\s*로봇|로봇팔', re.I)
NVIDIA_STACK = re.compile(r'NVIDIA|엔비디아|Cosmos|Omniverse|Isaac|\bRFM\b|Robot\s*Foundation\s*Model', re.I)
MONETIZATION = re.compile(r'수주|order|contract|계약|매출|revenue|고객|customer|양산|mass\s*production|초도생산|initial\s*production|생산능력|capacity|배치|deployment|가동률|uptime|납품|shipment|검증|qualification', re.I)
GROUP_ECOSYSTEM = re.compile(r'LG\s*CNS|LG이노텍|LG\s*Innotek|Bear\s*Robotics|베어로보틱스|로보스타|ROBOTIS|로보티즈', re.I)
PRICE_ONLY = re.compile(r'주가|급등|상한가|특징주|수혜주|목표주가|stock\s*price|shares?\s*(?:jump|rise|surge)', re.I)


def _is_lg_factory_loop(text: str) -> bool:
    if not LG.search(text):
        return False
    core = SMART_FACTORY.search(text) or DATA_FACTORY.search(text) or ACTUATOR.search(text) or FIELD_ROBOT.search(text)
    # NVIDIA-only LG articles are accepted only when explicitly tied to robotics/data/RFM.
    nv_robot = NVIDIA_STACK.search(text) and re.search(r'로봇|robotics|robot\s*learning|피지컬\s*AI|physical\s*AI|RFM', text, re.I)
    eco = GROUP_ECOSYSTEM.search(text) and re.search(r'로봇|robot|피지컬\s*AI|physical\s*AI|데이터\s*팩토리|Data\s*Factory', text, re.I)
    return bool(core or nv_robot or eco)


def topic_group(text: str) -> str | None:
    if _is_lg_factory_loop(text):
        return 'lg_factory_loop'
    return _orig_topic_group(text)


def score(item: dict) -> int:
    title = item.get('title', '')
    text = f"{title} {item.get('description','')} {item.get('source','')}"
    if topic_group(text) != 'lg_factory_loop':
        return _orig_score(item)

    # Suppress pure valuation/price commentary unless a new operational fact is present.
    if PRICE_ONLY.search(title) and not MONETIZATION.search(text) and not DATA_FACTORY.search(text):
        return -20

    source = item.get('source') or ''
    s = 15
    if base.NUMERIC.search(text):
        s += 3
    if source in base.OFFICIAL_OR_PRIMARY:
        s += 6
    elif source in base.TRUSTED:
        s += 3

    # Current cash-generation / commercial proof.
    if SMART_FACTORY.search(text) and re.search(r'수주|order|매출|revenue|누적|cumulative|고객|customer', text, re.I):
        s += 7
    # Data-flywheel milestones.
    if DATA_FACTORY.search(text):
        s += 5
    if re.search(r'100,?000\s*hours|100000\s*hours|10만\s*시간|10,?000\s*(?:square\s*meters|㎡)|1만\s*㎡|hundreds?\s+of\s+robots|수백\s*대', text, re.I):
        s += 5
    if NVIDIA_STACK.search(text) and DATA_FACTORY.search(text):
        s += 4
    # Actuator monetization transition.
    if ACTUATOR.search(text) and re.search(r'초도생산|initial\s*production|시험생산|pilot|양산|mass\s*production', text, re.I):
        s += 6
    if ACTUATOR.search(text) and re.search(r'수주|order|contract|계약|고객|customer|qualification|검증|납품|shipment', text, re.I):
        s += 8
    # Actual field use matters more than a stage demo.
    if FIELD_ROBOT.search(text) and re.search(r'공장|factory|물류|logistics|배치|deployment|가동률|uptime|현장|field', text, re.I):
        s += 6
    if re.search(r'작업\s*성공률|task\s*success|가동률|uptime|사람\s*개입|human\s*intervention|연속\s*가동|runtime', text, re.I):
        s += 6
    return s


def _raw_cat(text: str) -> str:
    if ACTUATOR.search(text) and re.search(r'수주|order|contract|계약|고객|customer|qualification|검증|초도생산|initial\s*production|양산|mass\s*production', text, re.I):
        return '액추에이터 양산·고객 검증'
    if FIELD_ROBOT.search(text) and re.search(r'공장|factory|물류|logistics|배치|deployment|가동률|uptime|현장|field', text, re.I):
        return 'MoMA·CLOiD 현장 배치'
    if DATA_FACTORY.search(text) or (NVIDIA_STACK.search(text) and re.search(r'RFM|robot\s*learning|로봇\s*학습|데이터', text, re.I)):
        return '데이터팩토리·RFM 학습'
    if SMART_FACTORY.search(text):
        return '스마트팩토리 현금창출·수주'
    if GROUP_ECOSYSTEM.search(text):
        return '그룹 데이터·로봇 생태계'
    return '피지컬AI 생산회로'


def category(text: str, group: str) -> str:
    if group == 'lg_factory_loop':
        return f"LG 피지컬AI · {_raw_cat(text)}"
    return _orig_category(text, group)


def meaning(cat: str) -> str:
    raw = cat.split(' · ', 1)[-1]
    if raw == '스마트팩토리 현금창출·수주':
        return 'LG의 현재 현금창출형 로봇 사업을 확인하는 신호입니다. 외부 스마트팩토리 수주가 로봇·자동화 장비와 실제 제조 데이터를 함께 늘리고, 이후 RFM·휴머노이드 학습으로 되먹임되는지 봅니다.'
    if raw == '데이터팩토리·RFM 학습':
        return '제조·물류 현장의 실제 데이터와 NVIDIA Cosmos·Omniverse·Isaac 기반 합성·증강 데이터를 묶어 RFM을 고도화하는 단계입니다. 데이터 양보다 실제 작업 일반화·성공률 개선으로 이어지는지가 핵심입니다.'
    if raw == '액추에이터 양산·고객 검증':
        return '시험생산·초도생산에서 외부 고객 검증과 양산 수주로 넘어가는 매출 전환 신호입니다. 고객 실명·대당 액추에이터 수·평균판매단가·발주 물량이 확인되면 재평가 강도가 크게 높아집니다.'
    if raw == 'MoMA·CLOiD 현장 배치':
        return '무대 시연이 아니라 공장·물류 현장에서 반복 작업을 수행하는지 확인하는 단계입니다. 가동률·작업 성공률·사람 개입률이 개선되면 스마트팩토리 수주와 데이터 축적이 동시에 강화됩니다.'
    if raw == '그룹 데이터·로봇 생태계':
        return 'LG CNS·LG이노텍·Bear Robotics·로보스타·ROBOTIS 등과의 데이터·하드웨어 연결고리를 확인하는 신호입니다. 실제 공급계약·매출 연결 여부는 지분관계나 협력관계와 분리해 봅니다.'
    if raw == '피지컬AI 생산회로':
        return '스마트팩토리에서 돈과 작업 데이터를 만들고, 데이터팩토리·RFM을 거쳐 로봇 성능과 액추에이터 판매를 다시 키우는 LG의 피지컬AI 생산회로가 실제 사업으로 닫히는지 확인합니다.'
    return _orig_meaning(cat)


def risk(cat: str) -> str:
    raw = cat.split(' · ', 1)[-1]
    if raw == '스마트팩토리 현금창출·수주':
        return '수주액과 매출액은 다릅니다. 고객 설비투자 지연·설치·검수·인수 시험이 늦어지면 매출 인식과 현금 회수가 뒤로 밀릴 수 있습니다.'
    if raw == '데이터팩토리·RFM 학습':
        return '10만 시간 목표에는 실제 로봇 데이터뿐 아니라 합성·증강 데이터가 포함될 수 있습니다. 이를 실제 로봇 10만 시간 가동으로 해석하지 않고, 실환경 작업 성공률·실패 복구·안전성으로 검증합니다.'
    if raw == '액추에이터 양산·고객 검증':
        return '초도생산은 양산 수주가 아닙니다. 감속기 수명·백래시·발열·소음·수율과 고객 인증이 늦어지면 설비투자·운전자본 부담이 먼저 커질 수 있습니다.'
    if raw == 'MoMA·CLOiD 현장 배치':
        return 'PoC·시연 1회와 무인 반복 가동은 다릅니다. 충돌 안전·고장 간 평균시간·사람 개입률·작업 전환 시간이 기준을 못 맞추면 외부 고객 확대가 지연될 수 있습니다.'
    if raw == '그룹 데이터·로봇 생태계':
        return '지분 보유·관계사·공동행사만으로 부품 납품을 확정하지 않습니다. 특히 LG의 ROBOTIS 지분 보유는 DYNAMIXEL 공급계약을 뜻하지 않으므로 고객·부품·물량 원문을 별도로 확인합니다.'
    if raw == '피지컬AI 생산회로':
        return '가장 현실적인 실패 경로는 스마트팩토리 수주는 늘지만 액추에이터 고객 승인이 지연되고, 학습 데이터가 복잡한 실작업 성능으로 전환되지 않아 휴머노이드가 PoC에 머무는 경우입니다.'
    return _orig_risk(cat)


def verification(item: dict, group: str, text: str) -> str:
    if group != 'lg_factory_loop':
        return _orig_verification(item, group, text)
    source = item.get('source') or ''
    if source in {'LG전자', 'LG Electronics', 'LG Newsroom', 'LG Global Newsroom'}:
        return 'LG전자 공식자료'
    if source in {'NVIDIA', 'NVIDIA Developer'}:
        return 'NVIDIA 공식자료 · LG전자 자료 교차확인'
    if source in {'LG CNS', 'LG Innotek'}:
        return 'LG그룹 공식자료'
    if source in base.TRUSTED:
        if ACTUATOR.search(text) and re.search(r'글로벌\s*빅테크|global\s*big\s*tech|고객|customer', text, re.I):
            return '신뢰 매체 보도 · 고객 실명/수주 공시 확인 필요'
        return '신뢰 매체 보도 · LG전자 공식자료 교차확인'
    return '보도 단계 · LG전자/고객사 원문 재확인 필요'


def _same_event(a: dict, b: dict) -> bool:
    if _orig_same_event(a, b):
        return True
    if a.get('group') != 'lg_factory_loop' or b.get('group') != 'lg_factory_loop':
        return False
    ta = f"{a.get('title','')} {a.get('description','')}"
    tb = f"{b.get('title','')} {b.get('description','')}"

    # Same Data Factory/NVIDIA/100k-hour milestone across rewrites.
    data_sig = r'데이터\s*팩토리|Data\s*Factory|100,?000\s*hours|100000\s*hours|10만\s*시간'
    if re.search(data_sig, ta, re.I) and re.search(data_sig, tb, re.I) and NVIDIA_STACK.search(ta) and NVIDIA_STACK.search(tb):
        return True

    # Same actuator customer-qualification / October inspection story.
    act_sig = r'액추에이터|actuator'
    qual_sig = r'10월|October|고객|customer|빅테크|big\s*tech|검증|qualification|수주\s*협의|order\s*discussion'
    if re.search(act_sig, ta, re.I) and re.search(act_sig, tb, re.I) and re.search(qual_sig, ta, re.I) and re.search(qual_sig, tb, re.I):
        return True

    # Same smart-factory order-intake milestone across syndicated headlines.
    sf_sig = r'스마트\s*팩토리|smart\s*factory'
    order_sig = r'수주|order|4,?000억|400\s*billion|5,?000억|500\s*billion|1조\s*2,?000억|1\.2\s*trillion'
    if re.search(sf_sig, ta, re.I) and re.search(sf_sig, tb, re.I) and re.search(order_sig, ta, re.I) and re.search(order_sig, tb, re.I):
        return True

    # Same MoMA/CLOiD field-deployment story only when the robot family matches.
    for robot in ['MoMA', 'CLOiD', '클로이드']:
        if re.search(robot, ta, re.I) and re.search(robot, tb, re.I):
            if re.search(r'공장|factory|물류|logistics|배치|deployment|현장|field', ta, re.I) and re.search(r'공장|factory|물류|logistics|배치|deployment|현장|field', tb, re.I):
                return True
    return False


base.topic_group = topic_group
base.score = score
base.category = category
base.meaning = meaning
base.risk = risk
base.verification = verification
ext._same_event = _same_event

if __name__ == '__main__':
    base.main()
