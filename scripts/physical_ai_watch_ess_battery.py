#!/usr/bin/env python3
"""Separate ESS-battery market/policy lane for the physical-AI Telegram watcher.

This keeps humanoid-battery stories in the existing battery lane, while routing
stationary ESS/BESS supply, Chinese capacity policy, cell prices and tax changes
into an independent 'ESS 배터리' lane.
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import physical_ai_watch_expanded_safe as safe

expanded = safe.expanded
base = safe.base
ext = expanded.ext

base.QUERIES.extend([
    '(중국 OR China OR 中国) (ESS OR BESS OR 에너지저장 OR 储能) (배터리셀 OR 배터리 셀 OR cell OR 电芯 OR 공장 OR factory) (승인 중단 OR 승인 보류 OR 신규 승인 OR pause approvals OR approval pause OR 产能 OR 审批)',
    '(CATL OR 宁德时代 OR EVE Energy OR 亿纬锂能 OR 이브에너지) (ESS OR BESS OR storage OR 储能) (314Ah OR 0.414 OR 0.423 OR 가격 인상 OR price hike OR 提价 OR 소비세 OR consumption tax)',
    '(중국 OR China OR 中国) (배터리 OR battery OR 电池) (소비세 OR consumption tax OR 消费税) (2% OR 4% OR 2026 OR 2027) (ESS OR BESS OR 에너지저장 OR 储能)',
    '(LG에너지솔루션 OR 삼성SDI OR SK온 OR "LG Energy Solution" OR "Samsung SDI" OR "SK On") (ESS OR BESS OR 에너지저장) (수주 OR 계약 OR 공급 OR 생산능력 OR 가격 OR LFP OR 미국 OR 북미)',
    '(에코프로비엠 OR 포스코퓨처엠 OR 엘앤에프 OR EcoPro BM OR POSCO Future M) (ESS OR BESS OR 에너지저장) (LFP OR 양극재 OR 공급 OR 수주 OR 가격)',
])

base.TRUSTED.update({
    'Energy-Storage.News', 'ESS News', 'Benchmark Mineral Intelligence',
    'Reuters', 'Caixin', '전자신문', '이데일리', '연합뉴스', '한국경제',
})
base.OFFICIAL_OR_PRIMARY.update({
    '국가세무총국', '중국 재정부', 'Ministry of Finance of China',
    'State Taxation Administration of China',
})

_orig_topic_group = base.topic_group
_orig_score = base.score
_orig_category = base.category
_orig_meaning = base.meaning
_orig_risk = base.risk
_orig_verification = base.verification
_orig_same_event = ext._same_event


def _is_ess_battery(text: str) -> bool:
    ess = re.search(r'\bESS\b|\bBESS\b|energy storage|battery storage|에너지저장|에너지 저장|储能', text, re.I)
    batt = re.search(r'배터리|battery|cell|셀|电池|电芯|CATL|EVE Energy|宁德时代|亿纬锂能|LG에너지솔루션|삼성SDI|SK온', text, re.I)
    # Do not steal humanoid-battery stories from the existing dedicated lane.
    humanoid = re.search(r'휴머노이드|humanoid|로봇용 배터리|robot battery|robotics battery', text, re.I)
    return bool(ess and batt and not humanoid)


def topic_group(text: str) -> str | None:
    if _is_ess_battery(text):
        return 'ess_battery'
    return _orig_topic_group(text)


def score(item: dict) -> int:
    title = item.get('title', '')
    text = f"{title} {item.get('description','')} {item.get('source','')}"
    if topic_group(text) != 'ess_battery':
        return _orig_score(item)

    source = item.get('source') or ''
    s = 9
    if base.NUMERIC.search(text):
        s += 3
    if re.search(r'승인\s*(?:중단|보류)|pause.*approval|approval.*pause|신규\s*공장|greenfield|미착공|产能|审批', text, re.I):
        s += 6
    if re.search(r'소비세|consumption tax|消费税|2%|4%', text, re.I):
        s += 5
    if re.search(r'314\s*Ah|0\.414|0\.423|가격\s*인상|price\s*hike|提价|Wh당|/Wh', text, re.I):
        s += 6
    if re.search(r'수주|계약|공급|order|contract|supply|생산능력|capacity', text, re.I):
        s += 4
    if source in base.OFFICIAL_OR_PRIMARY:
        s += 5
    elif source in base.TRUSTED:
        s += 3
    return s


def _raw_cat(text: str) -> str:
    if re.search(r'승인\s*(?:중단|보류)|pause.*approval|approval.*pause|신규\s*공장|greenfield|미착공|审批', text, re.I):
        return '중국 증설·승인 규제'
    if re.search(r'314\s*Ah|0\.414|0\.423|가격\s*인상|price\s*hike|提价|소비세|consumption tax|消费税', text, re.I):
        return '셀 가격·소비세'
    if re.search(r'LG에너지솔루션|삼성SDI|SK온|LG Energy Solution|Samsung SDI|SK On|에코프로비엠|포스코퓨처엠|엘앤에프', text, re.I):
        return '한국 공급망·수주'
    return '수급·가격 구조'


def category(text: str, group: str) -> str:
    if group == 'ess_battery':
        return f"ESS 배터리 · {_raw_cat(text)}"
    return _orig_category(text, group)


def meaning(cat: str) -> str:
    raw = cat.split(' · ', 1)[-1]
    if raw == '중국 증설·승인 규제':
        return '중국의 미착공 ESS 배터리 신규 생산능력 확대가 제동되면 장기간의 공급과잉·가격하락 압력이 완화될 수 있습니다. 한국 배터리의 반사이익은 북미·유럽 ESS 수주와 현지 생산 가동률이 실제로 늘어나는지까지 확인합니다.'
    if raw == '셀 가격·소비세':
        return '중국 ESS 셀 가격이 하락 일변도에서 반등하는지 추적합니다. 314Ah 셀 가격·소비세 전가·중소업체 후속 인상이 시스템통합업체 원가와 프로젝트 견적에 어떻게 전달되는지가 핵심입니다.'
    if raw == '한국 공급망·수주':
        return '중국 공급조절·가격 반등이 한국 셀·소재 업체의 실제 ESS 주문, 생산능력 가동, 평균판매단가 개선으로 연결되는지 확인합니다.'
    if raw == '수급·가격 구조':
        return 'ESS 셀의 공급량·가격·세금·증설 정책이 동시에 바뀌는지 보고 한국 배터리의 가격 경쟁력과 수주 환경 재평가 가능성을 확인합니다.'
    return _orig_meaning(cat)


def risk(cat: str) -> str:
    raw = cat.split(' · ', 1)[-1]
    if raw == '중국 증설·승인 규제':
        return '현재 신규 승인 중단은 중앙정부의 공개된 공식 전면 금지령이 아니라 업계·현지 매체를 통해 확인되는 잠정 조치입니다. 이미 건설 중인 프로젝트는 계속될 수 있어 즉각적인 공급부족으로 해석하면 안 됩니다.'
    if raw == '셀 가격·소비세':
        return 'CATL의 0.414→0.423위안/Wh 인상과 EVE의 2% 할증은 중국 내수 중심입니다. 수출은 세금 환급 구조가 달라 글로벌 수출가격이 같은 폭으로 오르는 것은 아닙니다.'
    if raw == '한국 공급망·수주':
        return '중국의 공급조절만으로 한국 업체 매출이 자동 증가하지 않습니다. 고객 실명·GWh 수주·단가·현지 생산 가동률이 확인되지 않으면 반사이익은 기대감 단계입니다.'
    if raw == '수급·가격 구조':
        return '단기 세금 전가와 구조적인 공급 부족을 구분해야 합니다. 중국 내수 가격 반등이 수출 가격과 글로벌 ESS 프로젝트 가격까지 이어지는지 확인해야 합니다.'
    return _orig_risk(cat)


def verification(item: dict, group: str, text: str) -> str:
    if group != 'ess_battery':
        return _orig_verification(item, group, text)
    source = item.get('source') or ''
    if re.search(r'소비세|consumption tax|消费税', text, re.I) and source in base.OFFICIAL_OR_PRIMARY:
        return '중국 세무·재정 공식자료'
    if re.search(r'승인\s*(?:중단|보류)|pause.*approval|approval.*pause', text, re.I):
        return 'Reuters·중국 매체 교차보도 · 중앙정부 공식 공고는 미확인'
    if re.search(r'0\.414|0\.423|314\s*Ah|가격\s*인상|price\s*hike', text, re.I):
        return '전문매체·업계 가격자료 · 업체 공지/세금 정책 교차확인'
    if source in base.OFFICIAL_OR_PRIMARY:
        return '공식자료'
    if source in base.TRUSTED:
        return '신뢰 매체 보도 · 공식자료 교차확인'
    return '보도 단계 · 추가 교차검증 필요'


def _same_event(a: dict, b: dict) -> bool:
    if _orig_same_event(a, b):
        return True
    if a.get('group') != 'ess_battery' or b.get('group') != 'ess_battery':
        return False
    ta = f"{a.get('title','')} {a.get('description','')}"
    tb = f"{b.get('title','')} {b.get('description','')}"
    approval = r'승인\s*(?:중단|보류)|pause.*approval|approval.*pause|미착공|greenfield'
    price = r'314\s*Ah|0\.414|0\.423|가격\s*인상|price\s*hike|2%\s*(?:소비세|할증)|소비세.*2%'
    if re.search(approval, ta, re.I) and re.search(approval, tb, re.I):
        return True
    if re.search(price, ta, re.I) and re.search(price, tb, re.I):
        # Keep approval-pause and price/tax as two separate ESS events.
        if not (re.search(approval, ta, re.I) or re.search(approval, tb, re.I)):
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
