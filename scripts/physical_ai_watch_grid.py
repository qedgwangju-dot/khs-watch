#!/usr/bin/env python3
"""Add power-grid / interconnection milestones to the robotics-battery watcher.

The lane focuses on MISO ERAS and the concrete monetization path:
ERAS study -> interconnection agreement (GIA) -> OEM/EPC equipment awards ->
construction/energization -> commercial operation.
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import physical_ai_watch_ess_battery as ess

base = ess.base
ext = ess.ext

base.QUERIES.extend([
    '(MISO OR "Midcontinent Independent System Operator") (ERAS OR "Expedited Resource Addition Study") (7.3 GW OR 7.3GW OR 29 GW OR 18 GW OR interconnection OR 계통접속 OR GIA)',
    '(MISO OR "Midcontinent Independent System Operator") (ERAS OR interconnection) (battery storage OR BESS OR gas generation OR combined cycle) (EPC OR turbine OR transformer OR switchgear OR 공급사 OR 발주 OR contract OR award)',
    '("Bayou Point Combined Cycle" OR "Calcasieu Parish Combined Cycle" OR "Rapides Parish" OR "Point Coupee Combined Cycle" OR "Sullivan County" OR "Malden Battery Energy Storage System" OR "Merom Energy Storage" OR "Steamboat Energy Storage" OR "Crosley Energy Storage") (EPC OR turbine OR transformer OR switchgear OR BESS OR battery OR PCS OR inverter OR supplier OR contract OR award OR interconnection)',
    '(NextEra Energy OR "Entergy Louisiana" OR NIPSCO OR "Cleco Power" OR "DOUBLEC Energy Center") (MISO OR ERAS) (interconnection agreement OR GIA OR EPC OR turbine OR transformer OR switchgear OR battery storage OR BESS OR contract OR award)',
    '(MISO ERAS) (commercial operation OR in-service OR energization OR 전원 인가 OR 상업운전 OR 2029)',
])

base.TRUSTED.update({
    'American Public Power Association', 'Utility Dive', 'Power Engineering',
    'POWER Magazine', 'Energy-Storage.News', 'Reuters', 'S&P Global',
})
base.OFFICIAL_OR_PRIMARY.update({
    'MISO', 'Midcontinent Independent System Operator', 'Entergy Louisiana',
    'NIPSCO', 'Cleco Power', 'NextEra Energy',
})

_orig_topic_group = base.topic_group
_orig_score = base.score
_orig_category = base.category
_orig_meaning = base.meaning
_orig_risk = base.risk
_orig_verification = base.verification
_orig_same_event = ext._same_event

PROJECT_NAMES = re.compile(
    r'Bayou Point|Calcasieu Parish|Rapides Parish|Point Coupee|Sullivan County|'
    r'Malden Battery|Merom Energy Storage|Steamboat Energy Storage|Crosley Energy Storage|'
    r'DOUBLEC Energy Center|Little Rock Wind|Sandcut|Tradewater', re.I
)


def _is_grid_event(text: str) -> bool:
    miso = re.search(r'\bMISO\b|Midcontinent Independent System Operator', text, re.I)
    eras = re.search(r'\bERAS\b|Expedited Resource Addition Study', text, re.I)
    grid = re.search(
        r'interconnection|계통\s*접속|계통연계|\bGIA\b|generation interconnection agreement|'
        r'transformer|변압기|switchgear|스위치기어|gas turbine|가스터빈|\bEPC\b|'
        r'energization|전원\s*인가|commercial operation|상업운전', text, re.I
    )
    return bool((miso and eras) or (PROJECT_NAMES.search(text) and grid))


def topic_group(text: str) -> str | None:
    if _is_grid_event(text):
        return 'grid_interconnection'
    return _orig_topic_group(text)


def score(item: dict) -> int:
    title = item.get('title', '')
    text = f"{title} {item.get('description','')} {item.get('source','')}"
    if topic_group(text) != 'grid_interconnection':
        return _orig_score(item)

    source = item.get('source') or ''
    s = 16
    if base.NUMERIC.search(text):
        s += 4
    if re.search(r'7\.3\s*GW|7,?297\.5\s*MW|15\s*projects|15개|29\s*GW|18\s*GW', text, re.I):
        s += 5
    if re.search(r'\bGIA\b|generation interconnection agreement|interconnection agreement|계통연계계약|계통접속', text, re.I):
        s += 6
    if re.search(r'award|contract|발주|수주|supplier|공급사|EPC|turbine|가스터빈|transformer|변압기|switchgear|스위치기어|PCS|inverter', text, re.I):
        s += 7
    if re.search(r'commercial operation|in-service|energization|상업운전|전원\s*인가|2029', text, re.I):
        s += 4
    if source in base.OFFICIAL_OR_PRIMARY:
        s += 6
    elif source in base.TRUSTED:
        s += 3
    return s


def _raw_cat(text: str) -> str:
    if re.search(r'award|contract|발주|수주|supplier|공급사|EPC|turbine|가스터빈|transformer|변압기|switchgear|스위치기어|PCS|inverter', text, re.I):
        return '장비·EPC 발주'
    if re.search(r'commercial operation|in-service|energization|상업운전|전원\s*인가', text, re.I):
        return '전원 인가·상업운전'
    return 'MISO ERAS·계통접속'


def category(text: str, group: str) -> str:
    if group == 'grid_interconnection':
        return f"전력망·계통접속 · {_raw_cat(text)}"
    return _orig_category(text, group)


def meaning(cat: str) -> str:
    raw = cat.split(' · ', 1)[-1]
    if raw == 'MISO ERAS·계통접속':
        return 'MISO가 수요 급증 지역의 발전·BESS 계통접속 시간을 단축하는 단계입니다. ERAS 심사가 실제 GIA 체결로 넘어가면 가스터빈·변압기·스위치기어·BESS·EPC 발주 가능성이 커지는지 추적합니다.'
    if raw == '장비·EPC 발주':
        return '계통접속 계획이 실제 장비 매출로 전환되는 단계입니다. 가스터빈 OEM, 대형 변압기·스위치기어, BESS 셀·PCS·시스템통합, EPC 계약의 공급사·용량·계약금액을 확인합니다.'
    if raw == '전원 인가·상업운전':
        return '계통연계와 공사가 실제 전원 인가·상업운전으로 이어지는 마지막 시간표입니다. 계획 용량이 실제 가동 자산과 반복 유지보수·부품 매출로 전환되는지 확인합니다.'
    return _orig_meaning(cat)


def risk(cat: str) -> str:
    raw = cat.split(' · ', 1)[-1]
    if raw == 'MISO ERAS·계통접속':
        return 'ERAS 심사 대상은 확정 수주가 아닙니다. GIA 체결, 송전 보강, 인허가, 장비 납기와 2029년 전원 인가 시점이 지연되면 발주 시간표도 밀릴 수 있습니다.'
    if raw == '장비·EPC 발주':
        return '프로젝트 용량만으로 특정 한국 업체 수혜를 확정하면 안 됩니다. OEM·EPC·변압기·BESS 공급사 실명, 계약금액, 납기와 매출 인식 시점을 확인해야 합니다.'
    if raw == '전원 인가·상업운전':
        return '공사가 완료돼도 송전선·변전소·시험운전·허가 병목으로 상업운전이 늦어질 수 있습니다. 최초 전원 인가와 실제 상업운전 날짜를 분리해 봅니다.'
    return _orig_risk(cat)


def verification(item: dict, group: str, text: str) -> str:
    if group != 'grid_interconnection':
        return _orig_verification(item, group, text)
    source = item.get('source') or ''
    if source in {'MISO', 'Midcontinent Independent System Operator'}:
        return 'MISO 공식자료'
    if source in base.OFFICIAL_OR_PRIMARY:
        return '사업자 공식자료 · MISO 일정 교차확인'
    if source in base.TRUSTED:
        return '신뢰 매체 보도 · MISO/사업자 공식자료 교차확인'
    return '보도 단계 · MISO/사업자 원문 재확인 필요'


def _same_event(a: dict, b: dict) -> bool:
    if _orig_same_event(a, b):
        return True
    if a.get('group') != 'grid_interconnection' or b.get('group') != 'grid_interconnection':
        return False
    ta = f"{a.get('title','')} {a.get('description','')}"
    tb = f"{b.get('title','')} {b.get('description','')}"
    # All rewrites of the same fifth ERAS 7.3 GW announcement are one event.
    fifth = r'(?:fifth|5th|제5차|5차).*(?:ERAS)|(?:ERAS).*(?:7\.3\s*GW|15\s*projects|15개)'
    if re.search(fifth, ta, re.I) and re.search(fifth, tb, re.I):
        return True
    # Equipment awards are only deduped when they refer to the same named project.
    for name in ['Bayou Point','Calcasieu Parish','Rapides Parish','Point Coupee','Sullivan County','Malden','Merom','Steamboat','Crosley','DOUBLEC']:
        if re.search(name, ta, re.I) and re.search(name, tb, re.I):
            award = r'award|contract|발주|수주|supplier|EPC|turbine|transformer|switchgear|PCS|inverter'
            if re.search(award, ta, re.I) and re.search(award, tb, re.I):
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
