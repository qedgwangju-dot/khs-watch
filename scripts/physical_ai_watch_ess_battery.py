#!/usr/bin/env python3
"""Separate ESS-battery market/policy lane for the physical-AI Telegram watcher.

This keeps humanoid-battery stories in the existing battery lane, while routing
stationary ESS/BESS supply, Chinese capacity policy, cell prices, tax changes,
and MLCC power-control bottlenecks into an independent 'ESS 배터리' lane.

MLCC guardrails:
- ESS/BESS must be explicitly present; generic AI-server/automotive MLCC news is
  not promoted into the ESS lane by itself.
- Media/analyst wording such as "price could double" remains a forecast until a
  supplier notice, filing, contract, or customer transaction confirms it.
- A component shortage is not booked revenue for Samsung Electro-Mechanics or
  another supplier unless the customer/contract/volume/price path is confirmed.
- Repeated articles about the same ESS-MLCC shortage/price event are deduped,
  while a later confirmed price, LTA, capacity, lead-time or customer change is
  treated as a new event.
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
    '(ESS OR BESS OR 에너지저장장치 OR energy storage) (MLCC OR 적층세라믹커패시터 OR multilayer ceramic capacitor) (공급난 OR 부족 OR shortage OR allocation OR 납기 OR lead time OR 생산 차질 OR bottleneck)',
    '(ESS OR BESS OR 에너지저장장치 OR energy storage) (MLCC OR 적층세라믹커패시터) (가격 인상 OR price hike OR 가격 상승 OR 두 배 OR 2배 OR average selling price OR ASP)',
    '(삼성전기 OR Samsung Electro-Mechanics OR Murata OR 무라타 OR Taiyo Yuden OR 다이요유덴 OR TDK OR Yageo) (ESS OR BESS OR energy storage) (MLCC OR capacitor) (장기공급계약 OR LTA OR 공급계약 OR contract OR 증설 OR capacity OR 가동률 OR utilization OR 납기 OR lead time)',
    '(ESS OR BESS OR energy storage) (MLCC OR 적층세라믹커패시터) (이중조달 OR dual sourcing OR 재고조정 OR inventory correction OR 공급 정상화 OR normalization OR 가격 하락 OR price cut)',
    '(ESS OR BESS OR energy storage) (MLCC OR 적층세라믹커패시터) (고전압 OR high voltage OR 고신뢰성 OR high reliability OR 고온 OR high temperature OR 검사 OR test OR 수율 OR yield)',
])

base.TRUSTED.update({
    'Energy-Storage.News', 'ESS News', 'Benchmark Mineral Intelligence',
    'Reuters', 'Caixin', '전자신문', '이데일리', '연합뉴스', '한국경제',
})
base.OFFICIAL_OR_PRIMARY.update({
    '국가세무총국', '중국 재정부', 'Ministry of Finance of China',
    'State Taxation Administration of China',
    '삼성전기', 'Samsung Electro-Mechanics', 'Murata', '무라타',
    'Taiyo Yuden', '다이요유덴', 'TDK', 'Yageo',
})

_orig_topic_group = base.topic_group
_orig_score = base.score
_orig_category = base.category
_orig_meaning = base.meaning
_orig_risk = base.risk
_orig_verification = base.verification
_orig_same_event = ext._same_event

ESS_RE = re.compile(r'\bESS\b|\bBESS\b|energy storage|battery storage|에너지저장|에너지 저장|에너지저장장치|储能', re.I)
BATTERY_RE = re.compile(r'배터리|battery|cell|셀|电池|电芯|CATL|EVE Energy|宁德时代|亿纬锂能|LG에너지솔루션|삼성SDI|SK온', re.I)
MLCC_RE = re.compile(r'\bMLCC\b|적층\s*세라믹\s*커패시터|multilayer ceramic capacitor|삼성전기|Samsung Electro-Mechanics|Murata|무라타|Taiyo Yuden|다이요유덴|TDK|Yageo', re.I)
MLCC_SHORTAGE = re.compile(r'공급난|공급\s*부족|부족|shortage|allocation|배정|납기|lead\s*time|생산\s*차질|bottleneck|병목', re.I)
MLCC_PRICE = re.compile(r'가격\s*인상|가격\s*상승|price\s*hike|price\s*increase|두\s*배|2\s*배|double|ASP|average\s*selling\s*price', re.I)
MLCC_CONTRACT = re.compile(r'장기\s*공급\s*계약|장기공급계약|LTA|공급\s*계약|supply\s*contract|contract|수주|order', re.I)
MLCC_CAPACITY = re.compile(r'증설|생산\s*능력|capacity|가동률|utilization|신규\s*라인|new\s*line|생산량|output', re.I)
MLCC_RELIEF = re.compile(r'이중\s*조달|dual\s*sourcing|재고\s*조정|inventory\s*correction|공급\s*정상화|normalization|가격\s*하락|price\s*cut|lead\s*time.*shorten|납기.*단축', re.I)
MLCC_RELIABILITY = re.compile(r'고전압|high\s*voltage|고신뢰성|high\s*reliability|고온|high\s*temperature|검사|test|수율|yield|절연|insulation', re.I)
HUMANOID_RE = re.compile(r'휴머노이드|humanoid|로봇용 배터리|robot battery|robotics battery', re.I)


def _is_mlcc_ess(text: str) -> bool:
    return bool(ESS_RE.search(text) and MLCC_RE.search(text) and not HUMANOID_RE.search(text))


def _is_ess_battery(text: str) -> bool:
    ess = ESS_RE.search(text)
    supply_component = BATTERY_RE.search(text) or MLCC_RE.search(text)
    return bool(ess and supply_component and not HUMANOID_RE.search(text))


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

    if _is_mlcc_ess(text):
        s += 8
        if MLCC_SHORTAGE.search(text):
            s += 8
        if MLCC_PRICE.search(text):
            s += 6
        if MLCC_CONTRACT.search(text):
            s += 8
        if MLCC_CAPACITY.search(text):
            s += 7
        if MLCC_RELIEF.search(text):
            s += 7
        if MLCC_RELIABILITY.search(text):
            s += 4

    if source in base.OFFICIAL_OR_PRIMARY:
        s += 5
    elif source in base.TRUSTED:
        s += 3
    return s


def _raw_cat(text: str) -> str:
    if _is_mlcc_ess(text):
        if MLCC_RELIEF.search(text):
            return 'MLCC 공급완화·재고조정'
        if MLCC_CONTRACT.search(text) or MLCC_CAPACITY.search(text):
            return 'MLCC 장기계약·생산능력'
        if MLCC_PRICE.search(text):
            return 'MLCC 가격·납기 병목'
        if MLCC_SHORTAGE.search(text):
            return 'MLCC 공급 병목'
        if MLCC_RELIABILITY.search(text):
            return 'MLCC 고전압·신뢰성 병목'
        return 'MLCC 수급 구조'
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
    if raw == 'MLCC 공급 병목':
        return 'ESS 전력 제어에 필요한 MLCC가 부족해지면 원가 비중이 작아도 전체 ESS 출하가 지연될 수 있습니다. 가격 자체보다 공급 배정·납기·실제 생산차질을 우선 추적합니다.'
    if raw == 'MLCC 가격·납기 병목':
        return 'ESS용 MLCC 가격 인상과 납기 장기화가 동시에 나타나는지 추적합니다. 기사상의 가격 2배 가능성은 전망으로 두고 실제 공급사 공지·계약·거래단가 확인 시에만 확정으로 승격합니다.'
    if raw == 'MLCC 장기계약·생산능력':
        return '공급 부족이 장기공급계약·선구매·증설로 이어지는 단계입니다. 고객 실명, 계약금액, 생산능력, 가동률과 실제 ESS향 물량이 확인될 때 공급사 매출 연결 강도를 높입니다.'
    if raw == 'MLCC 공급완화·재고조정':
        return '이중조달, 납기 단축, 재고조정, 공급 정상화는 MLCC 가격·가동률 고점이 꺾이는 반대 신호입니다. ESS 수요 둔화와 공급사 증설 효과를 함께 확인합니다.'
    if raw == 'MLCC 고전압·신뢰성 병목':
        return 'ESS용 MLCC는 고전압·고온·장시간 운전 신뢰성이 중요합니다. 고전압 검사시간, 절연 불량, 수율과 고객 인증이 생산능력의 실제 병목인지 추적합니다.'
    if raw == 'MLCC 수급 구조':
        return 'AI 서버·자동차·ESS가 동시에 고사양 MLCC 생산능력을 사용하면서 공급 우선순위가 바뀌는지 추적합니다. ESS향 실제 공급·납기 변화가 확인돼야 배터리 공급망 신호로 승격합니다.'
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
    if raw == 'MLCC 공급 병목':
        return 'MLCC 공급난이 곧 삼성전기 등 특정 업체의 ESS 매출 확정을 뜻하지 않습니다. 고객·규격·물량·단가가 확인되지 않으면 직접 수혜는 후보 단계로 유지합니다.'
    if raw == 'MLCC 가격·납기 병목':
        return '언론의 두 배 가격 가능성은 확정 단가가 아닙니다. 선구매·중복주문이 섞이면 실제 최종수요보다 부족이 과장될 수 있어 공급사 공지와 고객 거래조건을 재확인합니다.'
    if raw == 'MLCC 장기계약·생산능력':
        return 'AI 서버용 장기계약이나 증설을 ESS향 매출로 자동 치환하지 않습니다. ESS 고객과 적용 규격이 확인돼야 직접 연결로 분류하며, 증설 후 공급과잉·가동률 하락 위험도 같이 봅니다.'
    if raw == 'MLCC 공급완화·재고조정':
        return '공급 정상화가 빠르면 가격 인상과 장기계약의 협상력이 약해질 수 있습니다. 재고 증가와 평균판매단가 하락이 동시에 나타나는지 확인합니다.'
    if raw == 'MLCC 고전압·신뢰성 병목':
        return '고사양 MLCC는 범용 설비 증설만으로 바로 공급이 늘지 않을 수 있습니다. 고전압 검사·절연·적층 수율이 낮으면 생산능력 숫자보다 실제 출하가 뒤처질 수 있습니다.'
    if raw == 'MLCC 수급 구조':
        return 'AI 서버 수요만 강하고 ESS향 실제 물량이 확인되지 않으면 ESS 공급망 수혜로 확대해석하지 않습니다. 고객 이중조달과 신규 공급사 인증도 기존 업체 점유율을 낮출 수 있습니다.'
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
    if _is_mlcc_ess(text):
        if source in base.OFFICIAL_OR_PRIMARY:
            return '공급사 공식자료 · ESS 적용·고객·물량·단가를 별도 확인'
        if MLCC_PRICE.search(text):
            return '신뢰 매체 보도 · 가격 인상은 공급사 공지/계약 확인 전 전망 단계'
        if MLCC_SHORTAGE.search(text):
            return '신뢰 매체 보도 · ESS 생산차질·납기·공급배정 교차확인'
        if source in base.TRUSTED:
            return '신뢰 매체 보도 · 공급사/고객사 공식자료 교차확인'
        return '보도 단계 · ESS 적용과 공급사 직접 연결 추가확인 필요'
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


def _numbers(text: str) -> set[str]:
    return set(re.findall(r'\d[\d,.]*\s*(?:조원|억원|억|만원|원|%|배|개월|주|일|GWh|MWh|GW|MW)', text, re.I))


def _same_event(a: dict, b: dict) -> bool:
    if _orig_same_event(a, b):
        return True
    if a.get('group') != 'ess_battery' or b.get('group') != 'ess_battery':
        return False
    ta = f"{a.get('title','')} {a.get('description','')}"
    tb = f"{b.get('title','')} {b.get('description','')}"

    if _is_mlcc_ess(ta) and _is_mlcc_ess(tb):
        axes = [MLCC_SHORTAGE, MLCC_PRICE, MLCC_CONTRACT, MLCC_CAPACITY, MLCC_RELIEF, MLCC_RELIABILITY]
        same_axis = any(rx.search(ta) and rx.search(tb) for rx in axes)
        if not same_axis:
            return False
        na, nb = _numbers(ta), _numbers(tb)
        # Same figures across different outlets are the same event. A later
        # changed price/lead-time/capacity/contract figure remains a new event.
        if na and nb:
            return bool(na & nb)
        return True

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
