#!/usr/bin/env python3
"""Korea robot-demand policy + Samsung robot learning/scale lane.

Extends the existing Physical-AI watcher without creating a new workflow, bot or
state file.

Lane A — Korea 2030 AI-robot diffusion policy
Baseline locked:
- 2030 total 200,000 AI robots;
- 2027 central-government purchase of 1,700+ units;
- public/private expansion narrative including 15,000 public / 185,000 private;
- Daegu-Gyeongbuk (Gumi/Pohang) robot strategic-industry cluster designation;
- KRW 5.3839tn leading-company investment plan;
- Saemangeum / Daegyeong mass-production-base narrative.

New alerts are execution events: detailed procurement notices, awards/contracts,
actual field deployments, detailed private subsidy/rental programs, plant/capex
execution, quantified field-data/model release, or target/budget slippage.

Lane B — Samsung Electronics robotics
Baseline locked:
- RX Business Office manufacturing-first -> home/service expansion;
- "millions of robots" long-run sales potential;
- >100 factories / >100 product lines as internal validation base;
- 99.99% manufacturing reliability requirement as a target, not an achieved KPI;
- World Action Models / Human Motion Retargeting and human-video learning direction.

New alerts require measured execution: named-factory deployment, achieved
reliability/uptime, quantitative human-video scaling, actual task-engineering cost
reduction, mass-production/product launch, customer/supplier awards, or delay/safety
reversals.
"""
from __future__ import annotations

import hashlib
import re

import physical_ai_watch_quantity_enrichment as qty

base = qty.base

_orig_topic_group = base.topic_group
_orig_score = base.score
_orig_category = base.category
_orig_meaning = base.meaning
_orig_risk = base.risk
_orig_verification = base.verification
_orig_clean_title = base.clean_title
_orig_tag_for = base.tag_for
_orig_key = base.key
_orig_select_diverse = base.select_diverse

for q in [
    '(AI 로봇 OR 피지컬AI OR "physical AI") (20만대 OR 200000 OR 200,000 OR 1700대 OR 1,700대 OR 1만5000대 OR 18만5000대) (정부 OR 산업통상부 OR 국무조정실 OR 조달 OR 보급 OR 특화단지)',
    '(대구 OR 경북 OR 구미 OR 포항 OR 새만금) (휴머노이드 OR AI로봇 OR 로봇) (특화단지 OR 생산거점 OR 양산기반 OR 착공 OR 투자 OR 공장 OR 생산능력)',
    '(AI로봇 OR 휴머노이드) (구매보조 OR 렌탈지원 OR 조달공고 OR 입찰 OR 낙찰 OR 나라장터 OR 구매계약 OR 보급완료) (정부 OR 공기업 OR 지자체)',
    '(삼성전자 OR "Samsung Electronics") (RX사업추진실 OR 로보틱스 OR 휴머노이드 OR 로봇) (제조 OR 공장 OR 가정 OR 홈 OR 양산 OR 배치 OR 판매 OR 수백만대)',
    '(삼성전자 OR "Samsung Electronics") (로봇 OR robotics OR humanoid) ("World Action Model" OR "World Action Models" OR "Human Motion Retargeting" OR 인간 행동 영상 OR 사전학습 OR zero-shot OR 스케일링)',
    '(삼성전자 OR "Samsung Electronics") (로봇 OR robotics OR humanoid) (99.99 OR 성공률 OR 실패율 OR 가동률 OR 사람 개입 OR cycle time OR 작업개발비 OR NRE OR 학습비 OR 훈련시간)',
    '(삼성전자 OR "Samsung Electronics") (로봇 OR humanoid) (공급계약 OR 발주 OR 수주 OR 협력사 OR 공급사 OR 액추에이터 OR 감속기 OR 센서 OR 로봇손 OR 배터리)',
]:
    if q not in base.QUERIES:
        base.QUERIES.append(q)

base.OFFICIAL_OR_PRIMARY.update({
    '산업통상부', '국무조정실', '대한민국 정책브리핑', '정부24', '조달청', '나라장터',
    '삼성전자', 'Samsung Electronics', 'Samsung Newsroom', '삼성전자 뉴스룸',
    'Samsung AI Forum', '삼성 AI Forum',
})
base.TRUSTED.update({
    '연합뉴스', '뉴시스', '전자신문', '한국경제', '매일경제', '머니투데이',
    '조선일보', '서울경제', '이데일리', 'Reuters',
})

PRICE_ONLY = re.compile(r'주가|급등|상한가|특징주|수혜주|목표주가|stock\s*price|shares?\s*(?:jump|rise|surge)', re.I)

KOREA_ROBOT = re.compile(r'AI\s*로봇|인공지능\s*로봇|피지컬\s*AI|physical\s*AI|휴머노이드|humanoid|로봇', re.I)
KOREA_POLICY = re.compile(
    r'20\s*만\s*대|200,?000|1,?700\s*대|1\s*만\s*5,?000\s*대|15,?000\s*(?:대|units?)|'
    r'18\s*만\s*5,?000\s*대|185,?000\s*(?:대|units?)|국가첨단전략산업\s*특화단지|'
    r'대구.{0,20}경북|구미|포항|새만금|구매\s*보조|렌탈\s*지원',
    re.I,
)
POLICY_BASELINE = re.compile(
    r'2030.{0,50}(?:20\s*만\s*대|200,?000)|(?:20\s*만\s*대|200,?000).{0,50}2030|'
    r'내년.{0,50}1,?700\s*대|2027.{0,50}1,?700\s*대|'
    r'(?:대구|경북|구미|포항).{0,80}(?:특화단지|휴머노이드\s*생산거점)|'
    r'5\s*조\s*3,?839\s*억|5\.3839\s*조|12\s*조\s*9,?877\s*억',
    re.I,
)
PROC_NOTICE = re.compile(r'조달\s*공고|구매\s*공고|입찰\s*공고|입찰에\s*부쳐|나라장터|RFP|제안요청서|구매\s*계획\s*공고', re.I)
PROC_AWARD = re.compile(r'낙찰|계약\s*체결|구매\s*계약|공급\s*계약|선정\s*업체|우선협상대상|조달\s*계약|수주', re.I)
ACTUAL_DEPLOY = re.compile(r'보급\s*(?:완료|개시|시작)|배치\s*(?:완료|개시|시작)|현장\s*(?:투입|운영)\s*(?:개시|시작)|실제\s*설치|운영\s*개시', re.I)
PRIVATE_PROGRAM = re.compile(r'(?:구매\s*보조|렌탈\s*지원).{0,80}(?:공고|접수|신청|지원금|지원율|한도|대당|억원|만원)|(?:공고|접수|신청).{0,80}(?:구매\s*보조|렌탈\s*지원)', re.I)
PLANT_EXEC = re.compile(r'착공|장비\s*반입|생산라인\s*(?:구축|가동)|공장\s*(?:착공|가동)|생산능력\s*(?:확정|증설)|설비\s*투자\s*(?:결정|확정|공시)', re.I)
DATA_MODEL = re.compile(r'현장\s*데이터.{0,80}(?:공개|학습|파운데이션\s*모델|foundation\s*model)|피지컬\s*AI.{0,80}(?:모델\s*공개|벤치마크|성공률)|foundation\s*model.{0,80}(?:released|benchmark|success)', re.I)
POLICY_REVERSE = re.compile(r'(?:20\s*만\s*대|200,?000|1,?700\s*대|보급|조달|특화단지|양산기반).{0,80}(?:연기|지연|축소|감액|삭감|취소|철회|하향)|(?:예산|목표|보급).{0,80}(?:cut|delay|postpone|reduce|cancel)', re.I)

SAMSUNG = re.compile(r'삼성전자|Samsung\s*Electronics', re.I)
SAMSUNG_ROBOT = re.compile(r'RX사업추진실|로보틱스|robotics|휴머노이드|humanoid|로봇', re.I)
SAMSUNG_BASELINE = re.compile(
    r'수백만\s*대|millions?\s+of\s+robots?|100\s*개.{0,20}공장|100\s*개.{0,20}제품|'
    r'99\.99\s*%|World\s*Action\s*Models?|Human\s*Motion\s*Retargeting|'
    r'제조\s*현장.{0,60}(?:가정|홈|서비스)|(?:가정|홈|서비스).{0,60}제조\s*현장',
    re.I,
)
FACTORY_DEPLOY = re.compile(
    r'(?:공장|사업장|생산라인|fab|factory|plant).{0,100}(?:파일럿|실증|배치|투입|운영\s*개시|상시\s*운영)|'
    r'(?:파일럿|실증|배치|투입|운영\s*개시).{0,100}(?:공장|사업장|생산라인|fab|factory|plant)',
    re.I,
)
ACHIEVED_RELIABILITY = re.compile(
    r'(?:달성|기록|측정|확인|achiev|measured|recorded).{0,80}(?:99\.9{2,}\s*%|성공률|실패율|가동률|사람\s*개입|human\s*intervention|uptime)|'
    r'(?:99\.9{2,}\s*%|성공률|실패율|가동률|human\s*intervention|uptime).{0,80}(?:달성|기록|측정|확인|achiev|measured|recorded)',
    re.I,
)
TARGET_WORD = re.compile(r'목표|필요|요구|해야|계획|잠재|target|required|need|plan|potential', re.I)
SCALING_RESULT = re.compile(
    r'(?:인간\s*행동\s*영상|human\s*(?:behavior|action)\s*video|사전학습|pretrain|dataset|데이터).{0,140}'
    r'(?:배|x|영상|시간|개|만|zero[-\s]*shot|제로샷|성공률|실패율|일반화|generaliz|scaling\s*law|스케일링\s*법칙)',
    re.I,
)
COST_RESULT = re.compile(
    r'(?:작업\s*개발비|NRE|학습\s*비용|훈련\s*시간|training\s*time|engineering\s*cost).{0,100}'
    r'(?:감소|절감|단축|하락|줄|reduce|cut|down|improv)',
    re.I,
)
SAMSUNG_SOP = re.compile(r'로봇.{0,80}(?:양산\s*(?:개시|시작)|mass\s*production\s*(?:start|begin|commenc)|생산라인\s*가동)|(?:양산\s*(?:개시|시작)|mass\s*production).{0,80}로봇', re.I)
PRODUCT_LAUNCH = re.compile(r'(?:가정용|홈|서비스).{0,60}로봇.{0,80}(?:출시|판매\s*개시|사전예약|가격\s*공개|launch|sales)|(?:출시|판매\s*개시|launch).{0,80}(?:가정용|홈|서비스).{0,60}로봇', re.I)
SUPPLIER_AWARD = re.compile(r'(?:로봇|휴머노이드).{0,100}(?:공급사\s*선정|벤더\s*선정|발주|공급\s*계약|수주)|(?:공급사\s*선정|발주|공급\s*계약|수주).{0,100}(?:로봇|휴머노이드)', re.I)
SAMSUNG_REVERSE = re.compile(r'(?:로봇|휴머노이드|RX사업).{0,100}(?:연기|지연|중단|취소|사고|안전\s*문제|리콜|delay|postpone|suspend|cancel|accident|recall)', re.I)


def _is_korea_policy(text: str) -> bool:
    execution = (
        KOREA_POLICY.search(text) or PROC_NOTICE.search(text) or PROC_AWARD.search(text)
        or ACTUAL_DEPLOY.search(text) or PRIVATE_PROGRAM.search(text)
        or (PLANT_EXEC.search(text) and re.search(r'대구|경북|구미|포항|새만금|대경권', text, re.I))
        or DATA_MODEL.search(text) or POLICY_REVERSE.search(text)
    )
    explicit_policy_actor = re.search(
        r'정부|산업통상부|국무조정실|조달청|나라장터|소방청|우정|국방|공공|지자체|공기업|'
        r'국가첨단전략산업|특화단지|20\s*만\s*대|200,?000|보급\s*계획|구매\s*보조|렌탈\s*지원',
        text,
        re.I,
    )
    # A private company simply operating in Gumi/Daegu-Gyeongbuk is not a
    # government-policy event. Region names alone are sufficient only when the
    # text explicitly says cluster/special-zone/mass-production-base execution.
    regional_policy = bool(
        re.search(r'대구|경북|구미|포항|새만금|대경권', text, re.I)
        and re.search(r'특화단지|양산\s*기반|생산\s*거점|국가첨단전략산업|정부\s*지원', text, re.I)
    )
    return bool(KOREA_ROBOT.search(text) and execution and (explicit_policy_actor or regional_policy))


def _is_samsung_robot(text: str) -> bool:
    return bool(SAMSUNG.search(text) and SAMSUNG_ROBOT.search(text))


def _policy_stage(text: str) -> str:
    if POLICY_REVERSE.search(text):
        return 'reverse'
    if PROC_AWARD.search(text):
        return 'procurement_award'
    if PROC_NOTICE.search(text):
        return 'procurement_notice'
    if ACTUAL_DEPLOY.search(text):
        return 'actual_deployment'
    if PRIVATE_PROGRAM.search(text):
        return 'private_support'
    if PLANT_EXEC.search(text) and re.search(r'대구|경북|구미|포항|새만금|대경권', text, re.I):
        return 'plant_execution'
    if DATA_MODEL.search(text):
        return 'field_data_model'
    if POLICY_BASELINE.search(text):
        return 'baseline'
    return 'monitor'


def _samsung_stage(text: str) -> str:
    if SAMSUNG_REVERSE.search(text):
        return 'reverse'
    if PRODUCT_LAUNCH.search(text):
        return 'home_launch'
    if SAMSUNG_SOP.search(text):
        return 'mass_production'
    if SUPPLIER_AWARD.search(text):
        return 'supplier_award'
    if FACTORY_DEPLOY.search(text):
        return 'factory_deployment'
    if ACHIEVED_RELIABILITY.search(text) and not TARGET_WORD.search(text):
        return 'reliability_achieved'
    if COST_RESULT.search(text) and re.search(r'\d', text):
        return 'cost_reduction'
    if SCALING_RESULT.search(text) and re.search(r'(?:\d|zero[-\s]*shot|제로샷|scaling\s*law|스케일링\s*법칙)', text, re.I):
        return 'scaling_result'
    if SAMSUNG_BASELINE.search(text):
        return 'baseline'
    return 'monitor'


def topic_group(text: str) -> str | None:
    if _is_korea_policy(text):
        return 'korea_robot_scale_policy'
    if _is_samsung_robot(text):
        return 'samsung_robot_scale'
    return _orig_topic_group(text)


def score(item: dict) -> int:
    title = item.get('title', '')
    text = f"{title} {item.get('description','')} {item.get('source','')}"
    group = topic_group(text)

    if group == 'korea_robot_scale_policy':
        stage = _policy_stage(text)
        if stage in {'baseline', 'monitor'}:
            return 0
        if PRICE_ONLY.search(title):
            return -20
        src = item.get('source') or ''
        s = 20
        if base.NUMERIC.search(text): s += 3
        if src in base.OFFICIAL_OR_PRIMARY: s += 8
        elif src in base.TRUSTED: s += 4
        s += {
            'procurement_notice': 10,
            'procurement_award': 15,
            'actual_deployment': 12,
            'private_support': 9,
            'plant_execution': 12,
            'field_data_model': 11,
            'reverse': 14,
        }.get(stage, 0)
        return s

    if group == 'samsung_robot_scale':
        stage = _samsung_stage(text)
        if stage in {'baseline', 'monitor'}:
            return 0
        if PRICE_ONLY.search(title):
            return -20
        src = item.get('source') or ''
        s = 20
        if base.NUMERIC.search(text): s += 3
        if src in base.OFFICIAL_OR_PRIMARY: s += 8
        elif src in base.TRUSTED: s += 4
        s += {
            'factory_deployment': 12,
            'reliability_achieved': 13,
            'scaling_result': 14,
            'cost_reduction': 12,
            'mass_production': 15,
            'home_launch': 15,
            'supplier_award': 13,
            'reverse': 14,
        }.get(stage, 0)
        return s

    return _orig_score(item)


def category(text: str, group: str) -> str:
    if group == 'korea_robot_scale_policy':
        return {
            'baseline': '정부 AI로봇 20만대 · 정책 기준선',
            'procurement_notice': '정부 AI로봇 20만대 · 실제 조달공고',
            'procurement_award': '정부 AI로봇 20만대 · 낙찰·구매계약',
            'actual_deployment': '정부 AI로봇 20만대 · 실제 현장보급',
            'private_support': '정부 AI로봇 20만대 · 민간 구매보조·렌탈 집행',
            'plant_execution': '정부 AI로봇 20만대 · 대경권·새만금 양산설비 실행',
            'field_data_model': '정부 AI로봇 20만대 · 현장데이터→피지컬AI 모델',
            'reverse': '정부 AI로봇 20만대 · 목표·예산·일정 후퇴',
        }.get(_policy_stage(text), '정부 AI로봇 20만대 · 후속 실행')

    if group == 'samsung_robot_scale':
        return {
            'baseline': '삼성전자 로봇 · 제조→가정·인간영상 학습 기준선',
            'factory_deployment': '삼성전자 로봇 · 실제 공장 배치',
            'reliability_achieved': '삼성전자 로봇 · 산업 신뢰성 정량 달성',
            'scaling_result': '삼성전자 로봇 · 인간영상 사전학습 정량 스케일링',
            'cost_reduction': '삼성전자 로봇 · 작업 학습비·시간 절감',
            'mass_production': '삼성전자 로봇 · 실제 양산 개시',
            'home_launch': '삼성전자 로봇 · 가정·서비스 제품 출시',
            'supplier_award': '삼성전자 로봇 · 핵심부품 공급사·발주',
            'reverse': '삼성전자 로봇 · 일정·안전·신뢰성 후퇴',
        }.get(_samsung_stage(text), '삼성전자 로봇 · 사업 단계 변화')

    return _orig_category(text, group)


def meaning(cat: str) -> str:
    if cat.startswith('정부 AI로봇 20만대'):
        raw = cat.split(' · ', 1)[-1]
        return {
            '실제 조달공고': '20만대 정책 목표가 기관별 수량·예산·사양을 가진 실제 조달로 내려오는 첫 매출 문턱입니다. 조달기관, 로봇 종류, 대수, 총예산, 단가와 납품기한을 추적합니다.',
            '낙찰·구매계약': '정책 수혜 기대가 실제 업체·계약금액·물량으로 바뀌는 단계입니다. 낙찰기업별 물량×단가와 설치·유지보수 범위를 분리합니다.',
            '실제 현장보급': '계약을 넘어 로봇이 현장에 배치되어 사용 데이터가 쌓이는 단계입니다. 실제 설치대수, 가동률, 작업성공률과 후속 추가구매를 봅니다.',
            '민간 구매보조·렌탈 집행': '민간 18만5,000대 목표가 실제 지원조건·지원금·신청기업으로 구체화되는 단계입니다. 보조율, 기업 자부담, 대당 단가와 예산 소진 속도를 확인합니다.',
            '대경권·새만금 양산설비 실행': '특화단지·양산기반 계획이 착공·장비반입·생산능력으로 바뀌는 설비투자 단계입니다. 투자기업, 투자액, 생산능력과 가동일을 확인합니다.',
            '현장데이터→피지컬AI 모델': '보급 로봇에서 쌓인 실제 작업데이터가 국내 피지컬AI 모델 성능으로 연결되는 재평가 단계입니다. 데이터 규모, 모델명, 벤치마크와 실제 로봇 성능을 확인합니다.',
            '목표·예산·일정 후퇴': '20만대 확산 경로가 예산·조달·특화단지 실행에서 뒤로 밀리는 역방향 신호입니다. 감액액, 축소 물량과 새 일정을 우선 확인합니다.',
        }.get(raw, '2030년 AI로봇 20만대, 2027년 정부 1,700대 이상 구매, 대구·경북 특화단지 지정은 현재 기준선입니다. 같은 정책 반복 보도는 침묵합니다.')

    if cat.startswith('삼성전자 로봇'):
        raw = cat.split(' · ', 1)[-1]
        return {
            '실제 공장 배치': '제조 우선 전략이 특정 삼성 공장·공정의 실제 로봇 배치로 이동하는 단계입니다. 배치대수, 작업, 성공률, 사람 개입률과 가동시간을 확인합니다.',
            '산업 신뢰성 정량 달성': '99.99%가 목표 문구가 아니라 실제 측정값으로 확인되는 단계입니다. 동일 작업의 시행횟수, 실패건수, 가동률과 복구시간을 함께 봅니다.',
            '인간영상 사전학습 정량 스케일링': 'Figure Index와 비교 가능한 핵심 검증 단계입니다. 인간영상·데이터가 늘 때 zero-shot·일반화·작업 성공률이 정량적으로 개선되는지를 확인합니다.',
            '작업 학습비·시간 절감': '새 작업마다 들어가는 엔지니어링 비용·학습시간이 실제로 낮아져 로봇 경제성이 개선되는 단계입니다. 기존 대비 절감률과 적용 작업 수를 봅니다.',
            '실제 양산 개시': '내부 연구·파일럿에서 반복 가능한 양산으로 이동한 단계입니다. 생산능력, 초기수율, 출하량과 부품 공급망을 확인합니다.',
            '가정·서비스 제품 출시': '제조 내부시장 이후 외부 소비자·서비스 시장으로 사업이 확장되는 단계입니다. 가격, 예약·판매량, 유지보수·서비스 수익모델을 확인합니다.',
            '핵심부품 공급사·발주': '삼성 로봇의 부품 수혜가 실제 공급사 선정·발주로 확인되는 단계입니다. 액추에이터·감속기·센서·로봇손·배터리의 업체, 물량, 단가와 양산일을 추적합니다.',
            '일정·안전·신뢰성 후퇴': '로봇 양산·현장배치가 신뢰성·안전·사고·개발지연 때문에 뒤로 밀리는 역방향 신호입니다. 실패 원인과 새 일정, 보증·보험 영향을 확인합니다.',
        }.get(raw, 'RX사업추진실의 제조→가정 전략, 수백만대 잠재력, 99.99% 필요 수준, World Action Models·Human Motion Retargeting은 현재 기준선이며 반복 보도는 침묵합니다.')

    return _orig_meaning(cat)


def risk(cat: str) -> str:
    if cat.startswith('정부 AI로봇 20만대'):
        raw = cat.split(' · ', 1)[-1]
        if raw == '낙찰·구매계약':
            return '정부 구매는 반복 민간수요와 다릅니다. 보조금·조달매출과 본업 민간매출을 분리하고 유지보수·재구매가 붙는지 확인합니다.'
        if raw == '실제 현장보급':
            return '설치대수와 실제 가동대수는 다릅니다. 성능 미흡·현장 방치·안전사고가 발생하면 추가 조달이 지연될 수 있습니다.'
        if raw == '대경권·새만금 양산설비 실행':
            return '생산능력은 주문이 아닙니다. 수요보다 설비가 먼저 늘면 감가상각·운전자본 부담과 저가동률이 총자산이익률을 훼손할 수 있습니다.'
        if raw == '현장데이터→피지컬AI 모델':
            return '데이터 규모 확대가 곧 일반화 성능 개선을 뜻하지 않습니다. 중복·편향·라벨 품질과 실제 로봇 작업성공률을 함께 봅니다.'
        if raw == '목표·예산·일정 후퇴':
            return '정책 총목표 유지 여부보다 연도별 조달예산과 실제 계약대수가 먼저 실적에 영향을 줍니다. 감액·이월·입찰유찰을 분리합니다.'
        return '20만대는 2030년 정책목표이지 확정 주문이 아닙니다. 2027년 기관별 조달공고→낙찰→설치→가동까지 순차 확인합니다.'

    if cat.startswith('삼성전자 로봇'):
        raw = cat.split(' · ', 1)[-1]
        if raw == '산업 신뢰성 정량 달성':
            return '99.99%는 시험조건이 중요합니다. 단순 작업·짧은 시험에서 달성한 수치를 복잡한 제조공정의 장기 가동률로 확대해석하지 않습니다.'
        if raw == '인간영상 사전학습 정량 스케일링':
            return '영상 데이터 증가가 시뮬레이션에서는 좋아도 실제 로봇의 접촉·힘제어·안전 일반화로 이어지지 않을 수 있습니다. 실제 현장 검증을 별도로 봅니다.'
        if raw == '실제 공장 배치':
            return '파일럿 배치와 상시 무인운영은 다릅니다. 안전요원, 사람 개입률, 사이클타임, 고장률과 정비비용이 먼저 실패할 수 있습니다.'
        if raw == '가정·서비스 제품 출시':
            return '가정은 제조공장보다 환경 다양성과 안전책임이 큽니다. 보험·사고책임·원격지원·AS비용이 채택 속도를 제한할 수 있습니다.'
        if raw == '핵심부품 공급사·발주':
            return '샘플·공동개발과 양산 발주는 다릅니다. 고객선정, 물량, 단가, 양산일이 없는 협력기사는 기대 단계로 남깁니다.'
        if raw == '일정·안전·신뢰성 후퇴':
            return '가장 현실적인 실패 경로는 사람 개입률·고장률이 높아 99.99% 산업 신뢰성에 못 미치는 경우입니다. 배치 확대와 가정 진출이 함께 지연될 수 있습니다.'
        return '수백만대는 잠재시장 표현이지 판매가이던스가 아닙니다. 공장별 실제 배치대수와 양산제품·가격·외부판매를 별도로 확인합니다.'

    return _orig_risk(cat)


def verification(item: dict, group: str, text: str) -> str:
    src = item.get('source') or ''
    if group == 'korea_robot_scale_policy':
        if src in base.OFFICIAL_OR_PRIMARY:
            return '정부·조달 공식자료 · 정책목표/공고/낙찰/실제보급 단계 분리'
        return '신뢰 매체 보도 · 산업통상부·국무조정실·조달청 공식자료 교차확인'
    if group == 'samsung_robot_scale':
        if src in base.OFFICIAL_OR_PRIMARY:
            return '삼성전자·삼성 AI Forum 공식자료'
        return '신뢰 매체 보도 · 삼성전자 공식자료와 실제 공장·제품 단계 교차확인'
    return _orig_verification(item, group, text)


def _sig_numbers(text: str) -> str:
    nums = sorted(set(re.findall(r'\d[\d,.]*\s*(?:조원|억원|억|만원|원|%|대|개|시간|건)', text, re.I)))
    return '|'.join(nums[:6]) if nums else 'no-number'


def key(item: dict) -> str:
    text = f"{item.get('title','')} {item.get('description','')} {item.get('source','')}"
    group = topic_group(text)
    if group == 'korea_robot_scale_policy':
        stage = _policy_stage(text)
        places = []
        for name, pat in [
            ('daegu', r'대구'), ('gyeongbuk', r'경북'), ('gumi', r'구미'),
            ('pohang', r'포항'), ('saemangeum', r'새만금'),
            ('fire', r'소방|화재|인명구조'), ('postal', r'우편|우정'),
            ('defense', r'국방'), ('agri', r'농업'), ('welfare', r'복지'),
        ]:
            if re.search(pat, text, re.I): places.append(name)
        return hashlib.sha256(
            f"korea-robot-scale|{stage}|{','.join(places)}|{_sig_numbers(text)}".encode()
        ).hexdigest()

    if group == 'samsung_robot_scale':
        stage = _samsung_stage(text)
        anchors = []
        for name, pat in [
            ('gumi', r'구미'), ('gwangju', r'광주'), ('pyeongtaek', r'평택'),
            ('semiconductor', r'반도체|fab'), ('home', r'가정|홈|home'),
            ('wam', r'World\s*Action'), ('retarget', r'Human\s*Motion\s*Retargeting'),
        ]:
            if re.search(pat, text, re.I): anchors.append(name)
        return hashlib.sha256(
            f"samsung-robot-scale|{stage}|{','.join(anchors)}|{_sig_numbers(text)}".encode()
        ).hexdigest()

    return _orig_key(item)


def tag_for(group: str) -> str:
    if group == 'korea_robot_scale_policy':
        return '한국로봇정책'
    if group == 'samsung_robot_scale':
        return '삼성전자로봇'
    return _orig_tag_for(group)


def clean_title(title: str, source: str) -> str:
    text = f"{title} {source}"
    if _is_korea_policy(text):
        return {
            'procurement_notice': '정부 AI로봇 20만대 계획, 실제 조달공고 단계 진입',
            'procurement_award': '정부 AI로봇 보급, 낙찰·구매계약 확정',
            'actual_deployment': '정부 AI로봇, 실제 현장 보급·운영 개시',
            'private_support': 'AI로봇 민간 구매보조·렌탈 세부사업 집행',
            'plant_execution': '대경권·새만금 로봇 양산설비 실제 집행',
            'field_data_model': '정부 보급 로봇 현장데이터, 피지컬AI 모델로 연결',
            'reverse': '정부 AI로봇 20만대 계획, 목표·예산·일정 후퇴',
        }.get(_policy_stage(text), _orig_clean_title(title, source))
    if _is_samsung_robot(text):
        return {
            'factory_deployment': '삼성전자 로봇, 실제 제조공장 배치 단계 진입',
            'reliability_achieved': '삼성전자 로봇, 산업 신뢰성 정량 성과 확인',
            'scaling_result': '삼성전자, 인간행동 영상 기반 로봇 스케일링 정량 검증',
            'cost_reduction': '삼성전자 로봇, 새 작업 학습비·시간 실질 절감',
            'mass_production': '삼성전자 로봇, 실제 양산 개시',
            'home_launch': '삼성전자 로봇, 가정·서비스 시장 제품 출시',
            'supplier_award': '삼성전자 로봇 핵심부품 공급사·발주 확인',
            'reverse': '삼성전자 로봇, 일정·안전·신뢰성 역방향 변화',
        }.get(_samsung_stage(text), _orig_clean_title(title, source))
    return _orig_clean_title(title, source)


def select_diverse(items: list[dict], seen: set[str], force: bool, limit: int) -> list[dict]:
    chosen = _orig_select_diverse(items, seen, force, limit)
    candidates = items if force else [x for x in items if x.get('key') not in seen]
    for group in ('korea_robot_scale_policy', 'samsung_robot_scale'):
        hit = next((x for x in candidates if x.get('group') == group), None)
        if not hit or any(x.get('key') == hit.get('key') for x in chosen):
            continue
        if len(chosen) < limit:
            chosen = [hit, *chosen]
        else:
            chosen = [hit, *chosen[:-1]]
    return chosen


base.topic_group = topic_group
base.score = score
base.category = category
base.meaning = meaning
base.risk = risk
base.verification = verification
base.clean_title = clean_title
base.tag_for = tag_for
base.key = key
base.select_diverse = select_diverse

if __name__ == '__main__':
    base.main()
