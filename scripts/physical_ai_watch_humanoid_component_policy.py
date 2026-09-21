#!/usr/bin/env python3
"""Add humanoid core-component policy/budget commercialization lane.

Tracks the policy-to-revenue chain rather than generic robot-policy headlines:
2027 budget proposal -> National Assembly final budget -> detailed program notice
-> named company/project award -> field reliability validation -> customer
qualification / mass-production linkage.

Guardrails:
- KRW 62bn for 2027 is treated as a government budget proposal until the final
  National Assembly appropriation is confirmed.
- The budget is not company revenue and is not allocated equally across sensor,
  actuator and humanoid-secondary-battery categories unless an official notice
  explicitly says so.
- A minister/vice-minister site visit is not beneficiary selection.
- Analyst/thematic beneficiary lists are not promoted to official award facts.
- R&D/field demonstration is separated from customer qualification, mass
  production, shipment and booked revenue.
"""
from __future__ import annotations

import hashlib
import json
import re
import sys
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import physical_ai_watch_korea_foundry_data_demand as kd

base, ext = kd.base, kd.ext

base.QUERIES.extend([
    '(휴머노이드 OR humanoid OR 피지컬AI OR "physical AI") (센서 OR sensor OR 액추에이터 OR actuator OR 이차전지 OR 배터리 OR battery) (620억 OR 62,000,000,000 OR 116억 OR 11,600,000,000 OR 예산 OR 정부안)',
    '(휴머노이드 OR humanoid) (핵심 부품 OR 핵심부품 OR core components) (국산화 OR localization) (예산 OR R&D OR 실증 OR 신뢰성 OR reliability OR 성능 OR performance)',
    '(초혁신경제 OR 경제성장전략 OR 미래성장산업) (센서 OR 액추에이터 OR 휴머노이드용 이차전지 OR humanoid battery) (신규 프로젝트 OR 예산 OR 공고 OR 실증)',
    '(휴머노이드 OR humanoid) (부품 실증사업 OR 핵심 부품 실증 OR component demonstration OR 로봇산업핵심기술개발) (공고 OR 선정 OR 주관기관 OR 수행기관 OR 협약 OR 총 연구개발비)',
    '(로보티즈 OR ROBOTIS OR 삼현 OR 하이젠알앤엠 OR 에스비비테크 OR 에스피지 OR 원익로보틱스 OR 현대모비스 OR 삼성SDI OR LG에너지솔루션) (휴머노이드 OR humanoid) (국책과제 OR 정부지원 OR 실증사업 OR 과제 선정 OR 수행기관 OR 주관기관)',
    '(국회 OR 정부) (2027년 OR 2027) (휴머노이드 OR 로봇) (620억 OR 핵심부품 OR 액추에이터 OR 센서 OR 이차전지) (확정 OR 통과 OR 의결 OR 증액 OR 감액)',
    '(humanoid OR 휴머노이드 OR 人形机器人) ("harmonic reducer" OR 하모닉감속기 OR 谐波减速器 OR "planetary roller screw" OR 롤러스크루 OR "frameless torque motor" OR 프레임리스 토크모터) (order OR backlog OR contract OR supplier OR nomination OR mass production OR capacity OR yield OR lead time OR 수주 OR 수주잔고 OR 공급 OR 고객 OR 양산 OR 생산능력 OR 수율 OR 납기)',
    '(humanoid OR 휴머노이드 OR 人形机器人) ("torque sensor" OR "force sensor" OR "6-axis force" OR 촉각센서 OR "tactile sensor" OR encoder OR 인코더 OR IMU OR lidar OR 라이다 OR "3D camera") (customer OR qualification OR order OR contract OR mass production OR capacity OR yield OR 수주 OR 고객검증 OR 고객승인 OR 양산 OR 생산능력 OR 수율)',
    '("Leader Harmonic Drive" OR Leaderdrive OR "Zhejiang Laifu" OR Laifual OR "Zhongda Leader" OR Inovance OR MOONS OR Orbbec OR RoboSense OR Hesai) (humanoid OR 人形机器人) (order OR backlog OR customer OR supplier OR capacity OR mass production OR yield OR 수주 OR 양산 OR 생산능력 OR 产能 OR 订单)',
    '("LG이노텍" OR "LG Innotek" OR TDK OR 에스비비테크 OR "SBB Tech" OR 에스피지 OR SPG OR 하이젠알앤엠 OR "Higen RNM" OR 삼현 OR "SOS LAB" OR 에스오에스랩) (휴머노이드 OR humanoid) (감속기 OR actuator OR 액추에이터 OR encoder OR 인코더 OR torque sensor OR force sensor OR 촉각 OR tactile OR lidar OR 라이다) (수주 OR 공급 OR 고객 OR 양산 OR 생산능력 OR 수율 OR 검증 OR contract OR order OR mass production OR capacity OR yield OR qualification)',

])

base.TRUSTED.update({
    '뉴스핌', '연합뉴스', '전자신문', '이데일리', '한국경제', '매일경제',
    '서울경제', '머니투데이', '조선비즈', '뉴시스', 'Newsis',
    'Reuters', 'Bloomberg', 'Nikkei Asia', 'The Robot Report', '36Kr', '界面新闻', '第一财经',
})
base.OFFICIAL_OR_PRIMARY.update({
    '재정경제부', '기획재정부', '대한민국 정책브리핑', '산업통상자원부',
    '과학기술정보통신부', '한국로봇산업진흥원', '국회', '국회예산정책처',
    '로보티즈', 'ROBOTIS', '삼현', '하이젠알앤엠', '에스비비테크',
    '에스피지', '원익로보틱스', '현대모비스', '삼성SDI', 'LG에너지솔루션',
    'LG이노텍', 'LG Innotek', 'TDK', 'Boston Dynamics',
})

_orig_topic_group, _orig_score = base.topic_group, base.score
_orig_category, _orig_meaning = base.category, base.meaning
_orig_risk, _orig_verification = base.risk, base.verification
_orig_tag_for, _orig_key = base.tag_for, base.key
_orig_select_diverse = base.select_diverse
_orig_same_event = ext._same_event

HUMANOID = re.compile(r'휴머노이드|humanoid|피지컬\s*AI|physical\s*AI', re.I)
COMPONENT = re.compile(r'센서|sensor|액추에이터|actuator|이차전지|배터리|battery|감속기|reducer|로봇\s*핸드|robot\s*hand|그리퍼|gripper', re.I)
POLICY = re.compile(r'정부|재정경제부|기획재정부|산업통상자원부|과학기술정보통신부|국회|예산|정부안|국비|국책|정책|초혁신경제|경제성장전략|지원사업|실증사업|공고|과제', re.I)
BUDGET_620 = re.compile(r'620\s*억|62\s*0{8,}|62,?000,?000,?000|116\s*억|11,?600,?000,?000', re.I)
BUDGET_PROPOSAL = re.compile(r'정부\s*안|예산\s*안|내년\s*예산|2027년\s*예산|예산을?.*(?:확대|편성)|국회\s*제출', re.I)
FINAL_BUDGET = re.compile(r'국회.{0,20}(?:통과|의결|확정)|본회의.{0,20}(?:통과|의결)|최종\s*확정|확정\s*예산|예산안\s*통과', re.I)
PROGRAM_NOTICE = re.compile(r'사업\s*공고|과제\s*공고|신규\s*과제|공모|접수|지원\s*대상|지원\s*조건|민간\s*부담|정부\s*출연금|출연\s*금|RFP', re.I)
AWARD = re.compile(r'과제\s*선정|주관\s*기관|수행\s*기관|공동\s*연구개발\s*기관|수혜\s*기업|협약\s*체결|최종\s*선정', re.I)
VALIDATION = re.compile(r'현장\s*실증|실증\s*환경|성능\s*검증|신뢰성\s*(?:시험|검증)|수명\s*시험|내구\s*시험|고객\s*검증|고객\s*승인|qualification|reliability|validation|PPAP|ISIR', re.I)
MASS_PROD = re.compile(r'양산|mass\s*production|본계약|공급\s*계약|수주|order|shipment|출하', re.I)
SITE_VISIT = re.compile(r'현장\s*방문|기업\s*방문|업계\s*점검|간담회|차관.{0,15}방문|장관.{0,15}방문', re.I)
PRICE_ONLY = re.compile(r'주가|급등|상한가|특징주|수혜주|목표주가|stock\s*price|shares?\s*(?:jump|rise|surge)', re.I)
ANALYST = re.compile(r'증권|리포트|research|analyst|목표주가|투자의견', re.I)

GLOBAL_COMPONENT = re.compile(
    r'하모닉\\s*감속기|harmonic\\s*reducer|谐波减速器|RV\\s*감속기|RV\\s*reducer|'
    r'유성\\s*롤러\\s*스크루|planetary\\s*roller\\s*screw|滚柱丝杠|'
    r'프레임리스\\s*토크\\s*모터|frameless\\s*torque\\s*motor|无框力矩电机|'
    r'코어리스\\s*모터|coreless\\s*motor|인코더|encoder|'
    r'토크\\s*센서|torque\\s*sensor|힘\\s*센서|force\\s*sensor|6축\\s*힘|6[- ]axis\\s*force|'
    r'촉각\\s*센서|tactile\\s*sensor|전자피부|electronic\\s*skin|e[- ]skin|'
    r'3D\\s*카메라|3D\\s*camera|라이다|LiDAR|IMU|관성\\s*센서|inertial\\s*sensor',
    re.I,
)
GLOBAL_COMMERCIAL = re.compile(
    r'수주\\s*잔고|backlog|수주|order|계약|contract|공급\\s*계약|supply\\s*agreement|'
    r'공급업체\\s*선정|supplier\\s*(?:selected|nominated|award)|design\\s*win|고객\\s*선정|customer\\s*award|'
    r'양산|mass\\s*production|series\\s*production|SOP|출하|shipment|'
    r'생산\\s*능력|capacity|증설|expansion|신규\\s*라인|new\\s*line|공장|plant|'
    r'고객\\s*승인|customer\\s*qualification|qualification|PPAP|ISIR|신뢰성|reliability|validation|검증|'
    r'수율|yield|납기|lead\\s*time|평균판매단가|ASP|가격\\s*(?:인상|하락)|price\\s*(?:increase|cut|hike)',
    re.I,
)
GLOBAL_QUAL = re.compile(r'고객\\s*승인|customer\\s*qualification|qualification|PPAP|ISIR|신뢰성|reliability|validation|검증', re.I)
GLOBAL_ORDER = re.compile(r'수주\\s*잔고|backlog|수주|order|계약|contract|공급\\s*계약|supply\\s*agreement|공급업체\\s*선정|supplier\\s*(?:selected|nominated|award)|design\\s*win|고객\\s*선정|customer\\s*award', re.I)
GLOBAL_MASS = re.compile(r'양산|mass\\s*production|series\\s*production|\\bSOP\\b|출하|shipment', re.I)
GLOBAL_CAPA = re.compile(r'생산\\s*능력|capacity|증설|expansion|신규\\s*라인|new\\s*line|공장|plant|장비\\s*반입|equipment\\s*move[- ]in', re.I)
GLOBAL_OPS = re.compile(r'수율|yield|납기|lead\\s*time|평균판매단가|\\bASP\\b|가격\\s*(?:인상|하락)|price\\s*(?:increase|cut|hike)', re.I)

GLOBAL_COMPANY_PATTERNS = [
    ('현대모비스', r'현대모비스|Hyundai\\s*Mobis'),
    ('로보티즈', r'로보티즈|ROBOTIS'),
    ('LG이노텍', r'LG이노텍|LG\\s*Innotek'),
    ('TDK', r'\\bTDK\\b'),
    ('에스비비테크', r'에스비비테크|SBB\\s*Tech'),
    ('에스피지', r'에스피지|\\bSPG\\b'),
    ('하이젠알앤엠', r'하이젠알앤엠|Higen\\s*RNM'),
    ('삼현', r'삼현|SAMHYUN'),
    ('에스오에스랩', r'에스오에스랩|SOS\\s*LAB'),
    ('Leaderdrive', r'Leader\\s*Harmonic\\s*Drive|Leaderdrive|绿的谐波'),
    ('Zhejiang Laifu', r'Zhejiang\\s*Laifu|Laifual|来福谐波'),
    ('Zhongda Leader', r'Zhongda\\s*Leader|中大力德'),
    ('Inovance', r'Inovance|汇川技术'),
    ('MOONS', r'MOONS|鸣志电器'),
    ('Orbbec', r'Orbbec|奥比中光'),
    ('RoboSense', r'RoboSense|速腾聚创'),
    ('Hesai', r'Hesai|禾赛'),
]


def _component_family(text: str) -> str:
    if re.search(r'하모닉|harmonic|谐波|RV\\s*감속기|RV\\s*reducer|롤러\\s*스크루|roller\\s*screw|滚柱丝杠', text, re.I):
        return '감속기·롤러스크루'
    if re.search(r'프레임리스|frameless|코어리스|coreless|인코더|encoder', text, re.I):
        return '모터·인코더'
    if re.search(r'토크\\s*센서|torque\\s*sensor|힘\\s*센서|force\\s*sensor|6축|6[- ]axis|촉각|tactile|전자피부|e[- ]skin', text, re.I):
        return '힘·토크·촉각센서'
    if re.search(r'3D\\s*카메라|3D\\s*camera|라이다|LiDAR|IMU|관성\\s*센서|inertial\\s*sensor', text, re.I):
        return '비전·3D·라이다·관성센서'
    return '핵심부품'


def _component_stage(text: str) -> str:
    if GLOBAL_ORDER.search(text):
        return '고객선정·수주·수주잔고'
    if GLOBAL_MASS.search(text):
        return '양산·출하'
    if GLOBAL_QUAL.search(text):
        return '고객승인·신뢰성검증'
    if GLOBAL_CAPA.search(text):
        return '생산능력·증설'
    if GLOBAL_OPS.search(text):
        return '수율·납기·가격'
    return '제품화'


def _global_companies(text: str) -> set[str]:
    return {name for name, pat in GLOBAL_COMPANY_PATTERNS if re.search(pat, text, re.I)}


def _is_global_component(text: str) -> bool:
    return bool(HUMANOID.search(text) and GLOBAL_COMPONENT.search(text) and GLOBAL_COMMERCIAL.search(text))


_FX_CACHE: dict[str, float | None] = {}


def _fx_krw(currency: str) -> float | None:
    currency = currency.upper()
    if currency == 'KRW':
        return 1.0
    if currency in _FX_CACHE:
        return _FX_CACHE[currency]
    try:
        req = urllib.request.Request(
            f'https://open.er-api.com/v6/latest/{currency}',
            headers={'User-Agent': 'Mozilla/5.0 khs-watch/2.0'},
        )
        with urllib.request.urlopen(req, timeout=6) as r:
            data = json.loads(r.read().decode('utf-8'))
        rate = float(data.get('rates', {}).get('KRW'))
        if 0 < rate < 100000:
            _FX_CACHE[currency] = rate
            return rate
    except Exception:
        pass
    _FX_CACHE[currency] = None
    return None


def _component_demand_note(text: str) -> str | None:
    robot_qty = None
    for pat in [
        r'(?<![\\d,])(\\d{1,3}(?:,\\d{3})+|\\d+)\\s*대',
        r'(?<![\\d,])(\\d{1,3}(?:,\\d{3})+|\\d+)\\s*(?:robots?|humanoids?)',
    ]:
        m = re.search(pat, text, re.I)
        if m:
            robot_qty = int(m.group(1).replace(',', ''))
            break

    per_robot = None
    for pat in [
        r'대당\\s*(\\d{1,3})\\s*개',
        r'(\\d{1,3})\\s*개\\s*/\\s*대',
        r'(\\d{1,3})\\s*(?:units?|pcs?)\\s*(?:per\\s+robot|/\\s*robot)',
    ]:
        m = re.search(pat, text, re.I)
        if m:
            per_robot = int(m.group(1))
            break

    if not robot_qty or not per_robot:
        return None

    total = robot_qty * per_robot
    note = f'{robot_qty:,}대 × {per_robot:,}개/대 = {total:,}개'

    price = None
    currency = None
    for pat, cur, mul in [
        (r'(?:개당|단가).{0,12}(\\d[\\d,.]*)\\s*만원', 'KRW', 10000.0),
        (r'(?:개당|단가).{0,12}(\\d[\\d,.]*)\\s*원', 'KRW', 1.0),
        (r'\\$\\s*(\\d[\\d,.]*)\\s*(?:/\\s*(?:개|unit|pc)|per\\s+(?:unit|pc))', 'USD', 1.0),
        (r'(?:RMB|CNY|위안)\\s*(\\d[\\d,.]*)\\s*(?:/\\s*(?:개|unit|pc)|per\\s+(?:unit|pc))?', 'CNY', 1.0),
        (r'(\\d[\\d,.]*)\\s*위안\\s*/\\s*(?:개|unit|pc)', 'CNY', 1.0),
    ]:
        m = re.search(pat, text, re.I)
        if m:
            price = float(m.group(1).replace(',', '')) * mul
            currency = cur
            break

    if price is None or currency is None:
        return note + ' · 단위단가 미공개로 매출은 미추정'

    fx = _fx_krw(currency)
    if fx is None:
        return note + f' · 개당 {price:,.2f} {currency} · 환율 확인 실패로 원화 총액 미추정'

    total_krw = total * price * fx
    if total_krw >= 1_000_000_000_000:
        total_str = f'{total_krw/1_000_000_000_000:,.2f}조원'
    elif total_krw >= 100_000_000:
        total_str = f'{total_krw/100_000_000:,.1f}억원'
    else:
        total_str = f'{total_krw:,.0f}원'
    return note + f' · 개당 {price:,.2f} {currency} → 총 {total_str} 단순환산'


COMPANY_PATTERNS = [
    '로보티즈', 'ROBOTIS', '삼현', '하이젠알앤엠', '에스비비테크', '에스피지',
    '원익로보틱스', '원익홀딩스', '현대모비스', '삼성SDI', 'LG에너지솔루션',
    '레인보우로보틱스', '크레스트', '로브로스',
]


def _is_component_policy(text: str) -> bool:
    if not HUMANOID.search(text):
        return False
    if not COMPONENT.search(text):
        return False
    return bool(POLICY.search(text) or BUDGET_620.search(text) or PROGRAM_NOTICE.search(text) or AWARD.search(text))


def topic_group(text: str) -> str | None:
    if _is_component_policy(text):
        return 'humanoid_component_policy'
    existing = _orig_topic_group(text)
    if existing is not None:
        return existing
    if _is_global_component(text):
        return 'humanoid_component_global'
    return None


def _stage(text: str) -> str:
    if FINAL_BUDGET.search(text):
        return '휴머노이드 핵심부품 예산 확정'
    if AWARD.search(text):
        return '핵심부품 수행기업·과제 선정'
    if PROGRAM_NOTICE.search(text):
        return '핵심부품 세부과제·지원조건 공고'
    if VALIDATION.search(text):
        return '핵심부품 현장 실증·신뢰성 검증'
    if MASS_PROD.search(text) and re.search(r'정부|국책|실증|과제', text, re.I):
        return '정책과제→양산·수주 연결'
    return '휴머노이드 핵심부품 620억원 정부안'


def score(item: dict) -> int:
    title = item.get('title', '')
    text = f"{title} {item.get('description','')} {item.get('source','')}"
    group = topic_group(text)
    if group == 'humanoid_component_global':
        source = item.get('source') or ''
        s = 18
        if base.NUMERIC.search(text):
            s += 3
        if source in base.OFFICIAL_OR_PRIMARY:
            s += 8
        elif source in base.TRUSTED:
            s += 3
        stage = _component_stage(text)
        s += {
            '고객선정·수주·수주잔고': 12,
            '양산·출하': 11,
            '고객승인·신뢰성검증': 10,
            '생산능력·증설': 9,
            '수율·납기·가격': 8,
            '제품화': 4,
        }.get(stage, 0)
        if _global_companies(text):
            s += 4
        note = _component_demand_note(text)
        if note:
            item['component_demand_note'] = note
            s += 3
        return s
    if group != 'humanoid_component_policy':
        return _orig_score(item)

    operational = FINAL_BUDGET.search(text) or PROGRAM_NOTICE.search(text) or AWARD.search(text) or VALIDATION.search(text) or MASS_PROD.search(text) or BUDGET_620.search(text)
    if PRICE_ONLY.search(title) and not operational:
        return -20

    source = item.get('source') or ''
    s = 18
    if base.NUMERIC.search(text):
        s += 3
    if source in base.OFFICIAL_OR_PRIMARY:
        s += 8
    elif source in base.TRUSTED:
        s += 3

    if BUDGET_620.search(text):
        s += 7
    if BUDGET_PROPOSAL.search(text):
        s += 3
    if FINAL_BUDGET.search(text):
        s += 12
    if PROGRAM_NOTICE.search(text):
        s += 10
    if AWARD.search(text):
        s += 12
    if VALIDATION.search(text):
        s += 9
    if MASS_PROD.search(text):
        s += 9
    if re.search(r'620\s*억', text) and re.search(r'116\s*억', text):
        s += 4
    if re.search(r'5\s*배|434(?:\.5)?\s*%|504\s*억', text, re.I):
        s += 3
    # Site visits matter only as policy-intent evidence, not as beneficiary awards.
    if SITE_VISIT.search(text) and not (PROGRAM_NOTICE.search(text) or AWARD.search(text) or FINAL_BUDGET.search(text)):
        s -= 2
    return s


def category(text: str, group: str) -> str:
    if group == 'humanoid_component_policy':
        return f"휴머노이드 핵심부품 정책 · {_stage(text)}"
    if group == 'humanoid_component_global':
        return f"글로벌 휴머노이드 부품 · {_component_family(text)} · {_component_stage(text)}"
    return _orig_category(text, group)


def meaning(cat: str) -> str:
    raw = cat.split(' · ', 1)[-1]
    mapping = {
        '휴머노이드 핵심부품 620억원 정부안': '센서·액추에이터·휴머노이드용 이차전지의 성능·신뢰성과 현장 실증에 정부 자금을 집중하는 정책 신호입니다. 2026년 116억원에서 2027년 정부안 620억원으로 확대됐지만 아직 기업별 매출이나 최종 국회 확정액은 아닙니다.',
        '휴머노이드 핵심부품 예산 확정': '정부안이 국회 최종 예산으로 바뀌는 첫 번째 실집행 문턱입니다. 확정액이 620억원과 달라졌는지, 센서·액추에이터·이차전지별 세부 배분이 생겼는지 바로 비교합니다.',
        '핵심부품 세부과제·지원조건 공고': '예산 총액이 실제 과제·지원금으로 쪼개지는 단계입니다. 정부출연금, 민간매칭, 과제 기간, 목표 성능, 실증장소와 지원대상 품목을 확인해야 실제 수혜 범위를 좁힐 수 있습니다.',
        '핵심부품 수행기업·과제 선정': '정책 기대가 기업별 확정 지원금과 고객 검증 일정으로 바뀌는 단계입니다. 선정기업, 정부출연금, 민간부담금, 공동기관과 실증 수요처를 분리해 매출 연결 가능성을 봅니다.',
        '핵심부품 현장 실증·신뢰성 검증': '국산 부품이 실제 로봇 구동환경에서 수명·발열·정밀도·안전성을 통과하는 단계입니다. 실증 성공보다 고객 승인과 양산 적용 여부가 최종 매출 문턱입니다.',
        '정책과제→양산·수주 연결': '국책과제 또는 실증이 실제 고객 본계약·양산·출하로 이어지는 가장 중요한 재평가 구간입니다. 정부지원금과 상업 매출을 분리해 표시합니다.',
    }
    if raw in mapping:
        return mapping[raw]
    if cat.startswith('글로벌 휴머노이드 부품 · '):
        parts = cat.split(' · ')
        family = parts[1] if len(parts) > 1 else '핵심부품'
        stage = parts[2] if len(parts) > 2 else '제품화'
        if family == '감속기·롤러스크루':
            return f'관절 정밀도·수명·백래시를 좌우하는 구동 핵심부품의 {stage} 변화입니다. 완성 로봇 생산대수보다 고객선정·수주잔고·수율·납기와 실제 양산 전환을 우선 추적합니다.'
        if family == '모터·인코더':
            return f'토크밀도와 위치정밀도를 결정하는 모터·인코더의 {stage} 변화입니다. OEM 다변화와 대당 탑재량, 평균판매단가, 생산수율이 매출 민감도를 좌우합니다.'
        if family == '힘·토크·촉각센서':
            return f'사람과 접촉하는 휴머노이드의 힘 제어·그립·안전성을 좌우하는 센서의 {stage} 변화입니다. 고객 승인, 드리프트·온도보상, 반복정밀도와 실제 양산 채택을 봅니다.'
        if family == '비전·3D·라이다·관성센서':
            return f'환경 인지·거리·자세 추정을 담당하는 센서의 {stage} 변화입니다. 고객 실명, 로봇 모델, 탑재 수량과 양산 시점을 확인해 실제 매출 연결을 판단합니다.'
        return f'휴머노이드 핵심부품의 {stage} 변화입니다. 고객·물량·단가·수율·납기를 함께 확인합니다.'
    return _orig_meaning(cat)


def risk(cat: str) -> str:
    raw = cat.split(' · ', 1)[-1]
    mapping = {
        '휴머노이드 핵심부품 620억원 정부안': '620억원은 2027년 정부안이지 현재 전액 집행 확정금이 아닙니다. 차관의 로보티즈 방문도 로보티즈의 직접 수혜기업 선정을 뜻하지 않으며, 품목별 배분액도 아직 임의로 나누지 않습니다.',
        '휴머노이드 핵심부품 예산 확정': '총액이 확정돼도 실제 과제 공고·협약·집행까지 시차가 있습니다. 국회 심의에서 증감된 금액과 집행 시기를 다시 확인합니다.',
        '핵심부품 세부과제·지원조건 공고': '정부출연금이 커도 민간매칭, 인증, 실증 수요처 조건이 무거우면 중소 부품사의 실질 수혜가 제한될 수 있습니다.',
        '핵심부품 수행기업·과제 선정': '과제 선정은 제품 양산 승인이나 매출 계약이 아닙니다. 연구개발비 인식과 고객 매출을 섞지 않고 과제 종료 후 본계약 여부를 추적합니다.',
        '핵심부품 현장 실증·신뢰성 검증': '실증에서 발열·감속기 수명·백래시·센서 드리프트·배터리 안전·수율 문제가 나오면 고객 승인과 양산 일정이 밀릴 수 있습니다.',
        '정책과제→양산·수주 연결': '보조금으로 개발된 부품도 가격·수명·수율이 중국·일본 경쟁사를 못 이기면 고객 본계약으로 이어지지 않을 수 있습니다. 첫 반복수주와 실제 출하량을 확인합니다.',
    }
    if raw in mapping:
        return mapping[raw]
    if cat.startswith('글로벌 휴머노이드 부품 · '):
        parts = cat.split(' · ')
        family = parts[1] if len(parts) > 1 else '핵심부품'
        if family == '감속기·롤러스크루':
            return '가장 현실적인 실패 경로는 OEM 양산 지연 전에 증설이 먼저 진행돼 가동률·총자산이익률이 악화되는 경우입니다. 수명·백래시·온도상승·소음과 고객 승인 지연을 먼저 봅니다.'
        if family == '모터·인코더':
            return '토크밀도·발열·인코더 정밀도·원가가 동시에 맞지 않으면 고객 채택이 지연될 수 있습니다. 생산능력보다 수율·납기·반복 주문을 우선 확인합니다.'
        if family == '힘·토크·촉각센서':
            return '센서 드리프트·교차간섭·온도보상·내구성 문제가 양산에서 먼저 드러날 수 있습니다. 고객 검증과 대량 교정 시간이 지연되면 평균판매단가가 높아도 매출 인식이 늦어집니다.'
        if family == '비전·3D·라이다·관성센서':
            return '시연 성능과 대량양산 신뢰성은 다릅니다. 가격 하락, 고객 이중조달, 교정·안전 인증 지연이 점유율과 마진을 압박할 수 있습니다.'
        return '부품 증설과 실제 OEM 양산 사이 시차가 가장 큰 역풍입니다. 고객 승인·수율·출하·반복수주를 확인합니다.'
    return _orig_risk(cat)


def verification(item: dict, group: str, text: str) -> str:
    if group == 'humanoid_component_global':
        src = item.get('source') or ''
        if src in base.OFFICIAL_OR_PRIMARY:
            return '기업 공식자료 · 고객/물량/단가/양산시점 직접 확인'
        if src in base.TRUSTED:
            return '신뢰 매체 보도 · 공급사·고객사 공식자료 교차확인'
        return '보도 단계 · 고객선정·수주·양산·수율을 1차 자료로 추가 확인'
    if group != 'humanoid_component_policy':
        return _orig_verification(item, group, text)
    src = item.get('source') or ''
    if src in base.OFFICIAL_OR_PRIMARY:
        if FINAL_BUDGET.search(text):
            return '정부·국회 공식자료 · 최종 확정액/세부사업 재검증'
        if AWARD.search(text) or PROGRAM_NOTICE.search(text):
            return '주관부처·전담기관 공식자료 · 선정기업/지원금/실증조건 확인'
        return '정부 공식자료 · 정부안과 최종 예산 단계 분리'
    if AWARD.search(text):
        return '신뢰 매체 보도 · 주관부처/한국로봇산업진흥원 선정 공고 교차확인'
    if BUDGET_620.search(text):
        return '신뢰 매체 보도 · 정부 예산안/정책 공식자료 교차확인'
    if ANALYST.search(text):
        return '증권사 분석 · 직접 수혜기업 선정 여부는 공식 과제공고로 별도 검증'
    return '신뢰 매체 보도 · 정부·전담기관 공식자료 교차확인'


def _companies(text: str) -> set[str]:
    return {name for name in COMPANY_PATTERNS if re.search(re.escape(name), text, re.I)}


def _same_event(a: dict, b: dict) -> bool:
    if _orig_same_event(a, b):
        return True
    if a.get('group') != b.get('group'):
        return False

    ta = f"{a.get('title','')} {a.get('description','')}"
    tb = f"{b.get('title','')} {b.get('description','')}"

    if a.get('group') == 'humanoid_component_global':
        if _component_family(ta) != _component_family(tb) or _component_stage(ta) != _component_stage(tb):
            return False
        ca, cb = _global_companies(ta), _global_companies(tb)
        if ca and cb and not ca.intersection(cb):
            return False
        nums_a = set(re.findall(r'\d[\d,.]*\s*(?:억원|억|만원|원|%|개|대|개월|주|일|CNY|RMB|USD|달러|위안)', ta, re.I))
        nums_b = set(re.findall(r'\d[\d,.]*\s*(?:억원|억|만원|원|%|개|대|개월|주|일|CNY|RMB|USD|달러|위안)', tb, re.I))
        return bool((not nums_a and not nums_b) or nums_a.intersection(nums_b))

    if a.get('group') != 'humanoid_component_policy':
        return False

    # Current 116 -> 620bn government-proposal story is one event across media.
    initial_a = bool(BUDGET_620.search(ta) and not (FINAL_BUDGET.search(ta) or PROGRAM_NOTICE.search(ta) or AWARD.search(ta)))
    initial_b = bool(BUDGET_620.search(tb) and not (FINAL_BUDGET.search(tb) or PROGRAM_NOTICE.search(tb) or AWARD.search(tb)))
    if initial_a and initial_b:
        return True

    # Final-budget rewrites are one event, but never merged with the proposal.
    if FINAL_BUDGET.search(ta) and FINAL_BUDGET.search(tb):
        return True

    # Program notices are merged only when the same amount/project wording recurs.
    if PROGRAM_NOTICE.search(ta) and PROGRAM_NOTICE.search(tb):
        nums_a = set(re.findall(r'\d[\d,.]*\s*(?:억원|억|만원|원|%|개월|년)', ta))
        nums_b = set(re.findall(r'\d[\d,.]*\s*(?:억원|억|만원|원|%|개월|년)', tb))
        if nums_a == nums_b or not nums_a or not nums_b:
            return True

    # Company awards are separate by company; syndicated copies of one award merge.
    if AWARD.search(ta) and AWARD.search(tb):
        ca, cb = _companies(ta), _companies(tb)
        if ca and cb and ca.intersection(cb):
            nums_a = set(re.findall(r'\d[\d,.]*\s*(?:억원|억|만원|원|%|개월|년)', ta))
            nums_b = set(re.findall(r'\d[\d,.]*\s*(?:억원|억|만원|원|%|개월|년)', tb))
            if nums_a == nums_b or not nums_a or not nums_b:
                return True

    return False


def tag_for(group: str) -> str:
    if group == 'humanoid_component_global':
        return '휴머노이드부품'
    return _orig_tag_for(group)


def key(item: dict) -> str:
    text = f"{item.get('title','')} {item.get('description','')} {item.get('source','')}"
    if topic_group(text) != 'humanoid_component_global':
        return _orig_key(item)
    family = _component_family(text)
    stage = _component_stage(text)
    companies = ','.join(sorted(_global_companies(text))) or 'market'
    nums = sorted(set(re.findall(r'\d[\d,.]*\s*(?:억원|억|만원|원|%|개|대|개월|주|일|CNY|RMB|USD|달러|위안)', text, re.I)))
    num_sig = '|'.join(nums[:4]) if nums else 'no-number'
    return hashlib.sha256(f'humanoid-component|{family}|{stage}|{companies}|{num_sig}'.encode()).hexdigest()


def select_diverse(items: list[dict], seen: set[str], force: bool, limit: int) -> list[dict]:
    chosen = _orig_select_diverse(items, seen, force, limit)
    candidates = items if force else [x for x in items if x.get('key') not in seen]
    component = next((x for x in candidates if x.get('group') == 'humanoid_component_global'), None)
    if not component or any(x.get('key') == component.get('key') for x in chosen):
        return chosen
    if len(chosen) < limit:
        return [component, *chosen]
    return [component, *chosen[:-1]]


base.topic_group = topic_group
base.score = score
base.category = category
base.meaning = meaning
base.risk = risk
base.verification = verification
base.tag_for = tag_for
base.key = key
base.select_diverse = select_diverse
ext._same_event = _same_event

if __name__ == '__main__':
    base.main()
