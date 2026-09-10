#!/usr/bin/env python3
"""Add 2027 humanoid core-parts policy-budget commercialization lane.

Tracks: 2026 KRW 11.6bn -> 2027 government proposal KRW 62.0bn for sensors,
actuators and humanoid batteries; National Assembly finalization; detailed
program notices; selected performers; government/private matching; field
validation; customer approval; and commercialization.

Guardrails:
- KRW 62.0bn is the 2027 government budget proposal until final Assembly passage.
- A vice-minister site visit to ROBOTIS is not beneficiary selection.
- Analyst/press beneficiary lists are not official award lists.
- R&D/field-validation support is not booked product revenue.
- Repeat articles about the 11.6bn->62.0bn increase are one event; later final
  budget, notice, award, validation and customer-production approval are new.
"""
from __future__ import annotations
import re, sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent))
import physical_ai_watch_korea_foundry_data_demand as kd

base, ext = kd.base, kd.ext

base.QUERIES.extend([
    '(휴머노이드 OR humanoid) (센서 OR sensor OR 액추에이터 OR actuator OR 이차전지 OR 배터리 OR battery) (620억 OR 62,000,000,000 OR 116억 OR 11,600,000,000) (예산 OR budget OR 정부안 OR 국회)',
    '(센서 OR sensor OR 액추에이터 OR actuator OR 휴머노이드용 이차전지 OR humanoid battery) (국산화 OR localization OR 핵심부품 OR core components) (예산 OR R&D OR 실증 OR validation OR 신뢰성 OR reliability)',
    '(휴머노이드 핵심부품 OR 로봇 핵심부품 OR humanoid core components) (국회 OR 예산안 OR 예산 확정 OR budget passage OR 본회의 OR 증액 OR 감액) (620억 OR 센서 OR 액추에이터 OR 이차전지)',
    '(휴머노이드 OR humanoid) (센서 OR 액추에이터 OR 배터리) (과제 공고 OR 사업 공고 OR 수행기관 OR 주관기관 OR 선정기업 OR 협약 OR 정부출연금 OR 민간매칭 OR 실증기관)',
    '(로보티즈 OR ROBOTIS OR 삼현 OR 에스비비테크 OR SBB테크 OR 에스피지 OR 원익로보틱스 OR 삼성SDI OR LG에너지솔루션) (휴머노이드 OR 로봇) (정부 과제 OR 국책과제 OR 실증 OR 고객 승인 OR 양산 승인 OR 수주 OR award OR PPAP)',
])
base.TRUSTED.update({'뉴스핌','전자신문','연합뉴스','뉴시스','한국경제','매일경제','이데일리'})
base.OFFICIAL_OR_PRIMARY.update({'재정경제부','기획재정부','산업통상자원부','산업부','과학기술정보통신부','중소벤처기업부','대한민국 정책브리핑','국회','로보티즈','ROBOTIS'})

_orig_topic_group, _orig_score = base.topic_group, base.score
_orig_category, _orig_meaning = base.category, base.meaning
_orig_risk, _orig_verification = base.risk, base.verification
_orig_same_event = ext._same_event

POLICY_PARTS = re.compile(r'휴머노이드|humanoid|로봇\s*핵심\s*부품|robot\s*core\s*components?', re.I)
PARTS = re.compile(r'센서|sensor|액추에이터|actuator|이차전지|배터리|battery', re.I)
BUDGET = re.compile(r'620\s*억|62,?000,?000,?000|116\s*억|11,?600,?000,?000|예산|budget', re.I)
ASSEMBLY = re.compile(r'국회|본회의|예산\s*확정|확정\s*예산|budget\s*pass|의결|증액|감액|삭감', re.I)
NOTICE = re.compile(r'과제\s*공고|사업\s*공고|공모|RFP|지원\s*계획|세부\s*사업|품목별\s*예산|배분', re.I)
AWARD = re.compile(r'수행\s*기관|주관\s*기관|선정\s*기업|선정\s*기관|협약|정부\s*출연금|민간\s*매칭|선정\s*결과|award|selected', re.I)
VALIDATION = re.compile(r'실증|현장\s*실증|신뢰성|reliability|내구|durability|시험|test|성능\s*검증|validation', re.I)
CUSTOMER_GATE = re.compile(r'고객\s*승인|양산\s*승인|PPAP|ISIR|본양산|mass\s*production|수주|order|contract|award', re.I)
VISIT = re.compile(r'차관|장관|방문|현장\s*방문|업계\s*점검|간담회', re.I)
BENEFICIARY = re.compile(r'로보티즈|ROBOTIS|삼현|에스비비테크|SBB|에스피지|원익로보틱스|삼성SDI|LG에너지솔루션', re.I)
PRICE_ONLY = re.compile(r'주가|급등|상한가|특징주|수혜주|목표주가', re.I)


def _is_policy_parts(text):
    return bool(POLICY_PARTS.search(text) and PARTS.search(text) and (BUDGET.search(text) or ASSEMBLY.search(text) or NOTICE.search(text) or AWARD.search(text) or VALIDATION.search(text)))


def topic_group(text):
    if _is_policy_parts(text): return 'humanoid_parts_policy_2027'
    return _orig_topic_group(text)


def score(item):
    title=item.get('title',''); text=f"{title} {item.get('description','')} {item.get('source','')}"; g=topic_group(text)
    if g!='humanoid_parts_policy_2027': return _orig_score(item)
    operational = ASSEMBLY.search(text) or NOTICE.search(text) or AWARD.search(text) or VALIDATION.search(text) or CUSTOMER_GATE.search(text)
    if PRICE_ONLY.search(title) and not operational: return -20
    src=item.get('source') or ''; s=18
    if base.NUMERIC.search(text): s+=3
    if src in base.OFFICIAL_OR_PRIMARY: s+=8
    elif src in base.TRUSTED: s+=3
    if re.search(r'116\s*억',text) and re.search(r'620\s*억',text): s+=6
    if ASSEMBLY.search(text): s+=10
    if NOTICE.search(text): s+=9
    if AWARD.search(text): s+=10
    if VALIDATION.search(text): s+=7
    if CUSTOMER_GATE.search(text): s+=11
    if BENEFICIARY.search(text): s+=4
    return s


def _subcat(text):
    if CUSTOMER_GATE.search(text) and BENEFICIARY.search(text): return '핵심부품 고객승인·양산수주'
    if AWARD.search(text): return '핵심부품 수행기업·지원금 선정'
    if NOTICE.search(text): return '핵심부품 세부과제·공고'
    if ASSEMBLY.search(text): return '2027년 핵심부품 예산 국회확정'
    if VALIDATION.search(text): return '핵심부품 성능·신뢰성 현장실증'
    return '휴머노이드 핵심부품 예산 확대'


def category(text, group):
    if group=='humanoid_parts_policy_2027': return f"정부·휴머노이드 부품 · {_subcat(text)}"
    return _orig_category(text, group)


def meaning(cat):
    raw=cat.split(' · ',1)[-1]
    m={
      '휴머노이드 핵심부품 예산 확대':'센서·액추에이터·휴머노이드용 이차전지 지원이 2026년 116억원에서 2027년 정부안 620억원으로 확대되는 정책 신호입니다. 금액보다 연구개발→성능·신뢰성→현장실증→고객 양산승인의 경로를 추적합니다.',
      '2027년 핵심부품 예산 국회확정':'정부안 620억원이 실제 집행 가능한 확정예산으로 바뀌는 첫 문턱입니다. 최종 확정액과 증감, 품목별 배분을 정부안과 비교합니다.',
      '핵심부품 세부과제·공고':'620억원 총액이 센서·액추에이터·휴머노이드용 이차전지별 실제 과제와 지원조건으로 분해되는 단계입니다. 과제 수, 정부출연금, 민간매칭, 실증 목표와 일정을 추적합니다.',
      '핵심부품 수행기업·지원금 선정':'정책 수혜 가능성이 실제 수행기업·지원금으로 바뀌는 단계입니다. 기업별 정부출연금과 민간부담, 실증기관, 고객 연결을 확인한 뒤 직접수혜로 승격합니다.',
      '핵심부품 성능·신뢰성 현장실증':'정부 지원 기술이 실제 구동환경에서 수명·발열·정밀도·수율·안전 기준을 통과하는 단계입니다. 단순 연구개발 완료보다 고객 채택 가능성을 높이는 신호입니다.',
      '핵심부품 고객승인·양산수주':'정책지원이 실제 반복매출로 연결되는 최종 확인 단계입니다. PPAP·ISIR·고객승인·본양산 수주와 물량×단가를 확인합니다.'}
    if raw in m: return m[raw]
    return _orig_meaning(cat)


def risk(cat):
    raw=cat.split(' · ',1)[-1]
    r={
      '휴머노이드 핵심부품 예산 확대':'620억원은 현재 정부안입니다. 국회 확정 전에는 집행액으로 표시하지 않고, 로보티즈 현장방문도 수혜기업 선정으로 보지 않습니다.',
      '2027년 핵심부품 예산 국회확정':'최종 총액이 확정돼도 품목별 배분과 실제 공고가 지연될 수 있습니다. 예산 확정과 기업 매출을 분리합니다.',
      '핵심부품 세부과제·공고':'공고 금액은 수주가 아닙니다. 자부담 비율·지원기간·성능 목표가 높으면 기업의 추가 연구개발비와 설비투자가 먼저 늘 수 있습니다.',
      '핵심부품 수행기업·지원금 선정':'정부과제 선정은 고객 양산계약이 아닙니다. 지원금 의존, 실증 실패, 후속 고객 부재를 함께 봅니다.',
      '핵심부품 성능·신뢰성 현장실증':'액추에이터 발열·백래시·내구수명, 센서 드리프트, 배터리 열폭주·에너지밀도·충방전 수명이 먼저 실패할 수 있습니다.',
      '핵심부품 고객승인·양산수주':'고객 승인 후에도 초기 수율·검사시간·반품·교환 접수·보증충당금이 악화되면 정책지원이 이익으로 연결되지 않을 수 있습니다.'}
    if raw in r: return r[raw]
    return _orig_risk(cat)


def verification(item, group, text):
    if group!='humanoid_parts_policy_2027': return _orig_verification(item,group,text)
    src=item.get('source') or ''
    if src in base.OFFICIAL_OR_PRIMARY:
        return '공식자료 · 정부안/확정예산/공고/선정단계를 분리 확인'
    if VISIT.search(text) and BENEFICIARY.search(text):
        return '현장방문 보도 · 방문기업과 정책 수혜기업 선정은 분리 확인'
    if AWARD.search(text):
        return '보도 단계 · 수행기업·지원금은 정부 공고/협약자료 재확인 필요'
    return '신뢰 매체 보도 · 재정·산업부·국회 공식자료 교차확인'


def _numbers(t): return set(re.findall(r'\d[\d,.]*\s*(?:조원|억원|억|만원|원|%|개|대)',t))

def _same_event(a,b):
    if _orig_same_event(a,b): return True
    if a.get('group')!=b.get('group') or a.get('group')!='humanoid_parts_policy_2027': return False
    ta=f"{a.get('title','')} {a.get('description','')}"; tb=f"{b.get('title','')} {b.get('description','')}"
    # Current 116->620 budget-proposal/site-visit story is one event across rewrites.
    current=lambda t: BUDGET.search(t) and (re.search(r'620\s*억',t) or (VISIT.search(t) and BENEFICIARY.search(t)))
    if current(ta) and current(tb) and not (ASSEMBLY.search(ta) or ASSEMBLY.search(tb) or NOTICE.search(ta) or NOTICE.search(tb) or AWARD.search(ta) or AWARD.search(tb)): return True
    for sig in [ASSEMBLY,NOTICE,AWARD,VALIDATION,CUSTOMER_GATE]:
        if sig.search(ta) and sig.search(tb):
            na,nb=_numbers(ta),_numbers(tb)
            if na==nb or not na or not nb: return True
    return False

base.topic_group=topic_group; base.score=score; base.category=category
base.meaning=meaning; base.risk=risk; base.verification=verification
ext._same_event=_same_event

if __name__=='__main__': base.main()
