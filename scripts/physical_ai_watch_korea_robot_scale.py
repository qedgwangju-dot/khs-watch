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

Lane C — robot/physical-AI compute semiconductor competition
Baseline locked:
- Marc Raibert's 2026-10-06 SLW comment that Samsung/Google/AMD/Arm could expand
  into robot-specialized compute is an expert outlook, not confirmation of a
  Samsung/Google chip program.
- NVIDIA Jetson Thor/T3000/T2000 robotics compute, AMD Ryzen AI Embedded/Kria/
  Versal robotics offerings, and Arm Total Design for Physical AI/Robotics
  Capability Framework are already-public baselines.

New alerts require a company-level state change: official robot-chip program or
roadmap, named silicon launch, tapeout/sample, robot-OEM design win, foundry
contract, mass production/shipment, quantified performance-per-watt breakthrough,
or cancellation/delay.
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
    '(삼성전자 OR "Samsung Electronics" OR "Samsung System LSI" OR "System LSI") (로봇 OR robotics OR humanoid OR "physical AI" OR 피지컬AI) (칩 OR 반도체 OR processor OR SoC OR NPU OR accelerator OR silicon) (개발 OR roadmap OR program OR tapeout OR sample OR 양산 OR 채택 OR 고객 OR 수주)',
    '(NVIDIA OR AMD OR "Advanced Micro Devices" OR Arm OR "Arm Holdings" OR Google OR "Google DeepMind") (robotics OR robot OR humanoid OR "physical AI" OR 로봇 OR 휴머노이드 OR 피지컬AI) (chip OR processor OR SoC OR NPU OR GPU OR accelerator OR silicon OR Jetson OR Ryzen OR Versal OR Kria OR Zena) (launch OR roadmap OR program OR tapeout OR sample OR design win OR adopt OR integrate OR production OR shipment OR benchmark)',
    '("Marc Raibert" OR 마크 레이버트) (Samsung OR 삼성 OR Google OR 구글 OR AMD OR Arm) (robot OR robotics OR 로봇) (chip OR semiconductor OR processor OR 반도체 OR 칩)',
]:
    if q not in base.QUERIES:
        base.QUERIES.append(q)

base.OFFICIAL_OR_PRIMARY.update({
    '산업통상부', '국무조정실', '대한민국 정책브리핑', '정부24', '조달청', '나라장터',
    '삼성전자', 'Samsung Electronics', 'Samsung Newsroom', '삼성전자 뉴스룸',
    'Samsung AI Forum', '삼성 AI Forum', 'Samsung Semiconductor', 'Samsung System LSI',
    'NVIDIA', 'AMD', 'Advanced Micro Devices', 'Arm', 'Arm Holdings',
    'Google', 'Google DeepMind', 'Boston Dynamics',
})
base.TRUSTED.update({
    '연합뉴스', '뉴시스', '전자신문', '한국경제', '매일경제', '머니투데이',
    '조선일보', '서울경제', '이데일리', '뉴스1', 'News1', 'Reuters', 'Bloomberg',
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


ROBOT_COMPUTE_ACTOR = re.compile(
    r'NVIDIA|엔비디아|삼성전자|Samsung\s*Electronics|Samsung\s*System\s*LSI|System\s*LSI|'
    r'Google(?:\s*DeepMind)?|구글|AMD|Advanced\s*Micro\s*Devices|\bArm\b|Arm\s*Holdings',
    re.I,
)
ROBOT_COMPUTE_CTX = re.compile(
    r'robotics?|humanoid|physical\s*AI|로보틱스|로봇|휴머노이드|피지컬\s*AI|피지컬AI',
    re.I,
)
ROBOT_COMPUTE_CHIP = re.compile(
    r'chip|processor|SoC|NPU|GPU|accelerator|silicon|semiconductor|Jetson|'
    r'Ryzen\s*AI\s*Embedded|Versal|Kria|Zena|Cortex|반도체|칩|프로세서|가속기|실리콘',
    re.I,
)
ROBOT_COMPUTE_EXPERT = re.compile(r'Marc\s+Raibert|마크\s*레이버트', re.I)
ROBOT_COMPUTE_SPECULATIVE = re.compile(
    r'could|may|might|possible|potential|could\s+have|may\s+have|'
    r'전망|내다봤|가능|있을\s*수|할\s*수|시작할\s*것|뛰어들\s*수|프로그램이\s*있을',
    re.I,
)
ROBOT_COMPUTE_RAIBERT_BASELINE = re.compile(
    r'(?:Marc\s+Raibert|마크\s*레이버트).{0,500}'
    r'(?:Samsung|삼성).{0,300}(?:Google|구글|AMD|Arm)|'
    r'(?:Samsung|삼성).{0,500}(?:Marc\s+Raibert|마크\s*레이버트)',
    re.I | re.S,
)
ROBOT_COMPUTE_NVIDIA_BASELINE = re.compile(
    r'(?:NVIDIA|엔비디아).{0,220}(?:Jetson\s*(?:AGX\s*)?Thor|T3000|T2000).{0,220}'
    r'(?:robot|humanoid|physical\s*AI|로봇|휴머노이드)|'
    r'(?:Boston\s+Dynamics|Figure|Agility\s+Robotics).{0,220}Jetson\s*(?:AGX\s*)?Thor',
    re.I | re.S,
)
ROBOT_COMPUTE_AMD_BASELINE = re.compile(
    r'(?:AMD|Advanced\s*Micro\s*Devices).{0,240}'
    r'(?:Ryzen\s*AI\s*Embedded|Kria\s*AI|Versal\s*AI\s*Edge|Embedded\+).{0,220}'
    r'(?:robot|physical\s*AI|로봇|피지컬\s*AI)',
    re.I | re.S,
)
ROBOT_COMPUTE_ARM_BASELINE = re.compile(
    r'(?:\bArm\b|Arm\s*Holdings).{0,260}'
    r'(?:Total\s*Design\s+for\s+Physical\s+AI|Robotics\s+Capability\s+Framework|'
    r'Zena\s*(?:CSS)?|physical\s*AI).{0,220}(?:robot|robotics|로봇|휴머노이드|humanoid)',
    re.I | re.S,
)
ROBOT_COMPUTE_PROGRAM = re.compile(
    r'(?:robot(?:ics)?|humanoid|physical\s*AI|로봇|휴머노이드|피지컬\s*AI).{0,140}'
    r'(?:dedicated|purpose[-\s]*built|specialized|custom).{0,80}'
    r'(?:chip|processor|SoC|NPU|accelerator|silicon|칩|프로세서|반도체|가속기)|'
    r'(?:chip|processor|SoC|NPU|accelerator|silicon|칩|프로세서|반도체|가속기).{0,140}'
    r'(?:robot(?:ics)?|humanoid|physical\s*AI|로봇|휴머노이드|피지컬\s*AI)',
    re.I,
)
ROBOT_COMPUTE_ANNOUNCED = re.compile(
    r'announc|unveil|introduc|launch|roadmap|official|developing|development\s+program|'
    r'confirmed|공식|발표|공개|개발\s*(?:착수|중|계획)|로드맵|프로그램\s*(?:가동|착수)',
    re.I,
)
ROBOT_COMPUTE_TAPEOUT = re.compile(
    r'tape[-\s]*out|first\s+silicon|engineering\s+sample|customer\s+sample|'
    r'prototype\s+silicon|시제품\s*칩|초도\s*실리콘|테이프아웃|샘플\s*(?:공급|출하|검증)',
    re.I,
)
ROBOT_COMPUTE_LAUNCH = re.compile(
    r'launch|launched|introduc|unveil|released|general\s+availability|출시|공개|'
    r'정식\s*발표|양산형\s*제품',
    re.I,
)
ROBOT_COMPUTE_OEM = re.compile(
    r'Boston\s+Dynamics|Figure\s*AI|Figure\s*0?3|Agility\s+Robotics|Unitree|'
    r'Apptronik|XPENG|샤오펑|삼성전자\s*로봇|현대차|Hyundai|ROBOTIS|로보티즈',
    re.I,
)
ROBOT_COMPUTE_DESIGN_WIN = re.compile(
    r'adopt|integrat|select|design\s*win|design[-\s]*in|customer\s+award|'
    r'채택|탑재|선정|디자인윈|고객\s*승인|공급사\s*선정',
    re.I,
)
ROBOT_COMPUTE_FOUNDRY = re.compile(
    r'foundry|fab|wafer|contract\s+manufactur|파운드리|위탁\s*생산|웨이퍼|'
    r'생산\s*수주|파운드리\s*계약',
    re.I,
)
ROBOT_COMPUTE_PRODUCTION = re.compile(
    r'mass\s*production|volume\s*production|shipments?\s*(?:started|began)|'
    r'commercial\s*shipment|양산\s*(?:개시|시작|돌입)|대량\s*생산|출하\s*(?:개시|시작)',
    re.I,
)
ROBOT_COMPUTE_BENCHMARK = re.compile(
    r'\d[\d,.]*\s*(?:TOPS|TFLOPS|W|watts?)|performance\s*per\s*watt|'
    r'energy\s*efficien|latency|성능\s*당\s*와트|전성비|지연시간',
    re.I,
)
ROBOT_COMPUTE_REVERSE = re.compile(
    r'(?:robot(?:ics)?|humanoid|physical\s*AI|로봇|휴머노이드|피지컬\s*AI).{0,160}'
    r'(?:chip|processor|SoC|NPU|accelerator|silicon|칩|프로세서|반도체|가속기).{0,160}'
    r'(?:delay|postpone|cancel|halt|suspend|cut\s+back|지연|연기|취소|중단|축소)',
    re.I | re.S,
)


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


def _is_robot_compute(text: str) -> bool:
    if ROBOT_COMPUTE_RAIBERT_BASELINE.search(text):
        return True
    return bool(
        ROBOT_COMPUTE_ACTOR.search(text)
        and ROBOT_COMPUTE_CTX.search(text)
        and ROBOT_COMPUTE_CHIP.search(text)
    )


def _robot_compute_stage(text: str, source: str = '') -> str:
    if ROBOT_COMPUTE_REVERSE.search(text):
        return 'reverse'
    if ROBOT_COMPUTE_RAIBERT_BASELINE.search(text) and ROBOT_COMPUTE_SPECULATIVE.search(text):
        return 'expert_outlook_baseline'
    if ROBOT_COMPUTE_NVIDIA_BASELINE.search(text):
        return 'known_vendor_baseline'
    if ROBOT_COMPUTE_AMD_BASELINE.search(text):
        return 'known_vendor_baseline'
    if ROBOT_COMPUTE_ARM_BASELINE.search(text):
        return 'known_vendor_baseline'
    if (
        re.search(r'Samsung\s*(?:Electronics|System\s*LSI)|삼성전자|System\s*LSI', text, re.I)
        and ROBOT_COMPUTE_FOUNDRY.search(text)
        and re.search(r'contract|award|selected|수주|계약|선정', text, re.I)
        and ROBOT_COMPUTE_CTX.search(text)
    ):
        return 'foundry_contract'
    if ROBOT_COMPUTE_OEM.search(text) and ROBOT_COMPUTE_DESIGN_WIN.search(text):
        return 'robot_oem_design_win'
    if ROBOT_COMPUTE_PRODUCTION.search(text):
        return 'mass_production_or_shipment'
    if ROBOT_COMPUTE_TAPEOUT.search(text):
        return 'tapeout_or_sample'
    if ROBOT_COMPUTE_PROGRAM.search(text) and ROBOT_COMPUTE_LAUNCH.search(text):
        return 'silicon_launch'
    if ROBOT_COMPUTE_PROGRAM.search(text) and ROBOT_COMPUTE_ANNOUNCED.search(text):
        return 'official_program'
    if ROBOT_COMPUTE_BENCHMARK.search(text) and ROBOT_COMPUTE_PROGRAM.search(text):
        return 'quantified_performance'
    return 'monitor'


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
    if _is_robot_compute(text):
        return 'robot_compute_semiconductor'
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

    if group == 'robot_compute_semiconductor':
        src = item.get('source') or ''
        stage = _robot_compute_stage(text, src)
        if stage in {'expert_outlook_baseline', 'known_vendor_baseline', 'monitor'}:
            return 0
        if PRICE_ONLY.search(title):
            return -20
        # Accuracy first: rumors/blogs cannot create robot-chip state changes.
        if src not in base.OFFICIAL_OR_PRIMARY and src not in base.TRUSTED:
            return 0
        s = 20
        if base.NUMERIC.search(text): s += 3
        if src in base.OFFICIAL_OR_PRIMARY: s += 8
        elif src in base.TRUSTED: s += 4
        s += {
            'official_program': 10,
            'silicon_launch': 15,
            'tapeout_or_sample': 13,
            'robot_oem_design_win': 17,
            'foundry_contract': 17,
            'mass_production_or_shipment': 18,
            'quantified_performance': 11,
            'reverse': 15,
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

    if group == 'robot_compute_semiconductor':
        return {
            'expert_outlook_baseline': '로봇 반도체 · 레이버트 전망 기준선',
            'known_vendor_baseline': '로봇 반도체 · 기존 상용 플랫폼 기준선',
            'official_program': '로봇 반도체 · 공식 개발·로드맵 착수',
            'silicon_launch': '로봇 반도체 · 신규 전용칩·프로세서 공개',
            'tapeout_or_sample': '로봇 반도체 · 테이프아웃·고객 샘플',
            'robot_oem_design_win': '로봇 반도체 · 로봇 OEM 채택·디자인윈',
            'foundry_contract': '로봇 반도체 · 삼성 파운드리 생산수주',
            'mass_production_or_shipment': '로봇 반도체 · 양산·상업 출하',
            'quantified_performance': '로봇 반도체 · 전성비·지연 정량 개선',
            'reverse': '로봇 반도체 · 개발·양산 일정 후퇴',
        }.get(_robot_compute_stage(text), '로봇 반도체 · 후속 변화')

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


    if cat.startswith('로봇 반도체'):
        raw = cat.split(' · ', 1)[-1]
        return {
            '레이버트 전망 기준선': '2026년 10월 6일 마크 레이버트가 삼성·Google·AMD·Arm 등도 로봇 특화 반도체에 참여할 수 있다고 전망한 발언입니다. 삼성·Google의 로봇 전용칩 공식 프로그램으로 승격하지 않습니다.',
            '기존 상용 플랫폼 기준선': 'NVIDIA Jetson Thor 계열, AMD Ryzen AI Embedded·Kria·Versal 로봇용 컴퓨트, Arm의 Physical AI 플랫폼은 이미 공개된 기준선입니다. 반복 소개는 침묵합니다.',
            '공식 개발·로드맵 착수': '전망이 아니라 회사가 로봇·피지컬AI 전용 실리콘 개발 또는 로드맵을 직접 확인한 단계입니다. 제품명·공정·연산성능·전력·샘플 일정과 양산 시점을 추적합니다.',
            '신규 전용칩·프로세서 공개': '로봇 두뇌 경쟁이 실제 제품으로 구체화되는 단계입니다. TOPS/TFLOPS, 메모리 대역폭, 소비전력, 센서·모터 제어 통합과 소프트웨어 생태계를 비교합니다.',
            '테이프아웃·고객 샘플': '로드맵이 실제 실리콘과 고객 평가 단계로 넘어가는 신호입니다. 테이프아웃 공정, 샘플 고객, 평가기간, 수율과 양산 전환 일정을 확인합니다.',
            '로봇 OEM 채택·디자인윈': '칩 성능이 실제 로봇 제조사 선택으로 전환되는 핵심 매출 신호입니다. 로봇 모델·대수·칩 탑재수량·평균판매단가·SOP와 반복 발주를 연결합니다.',
            '삼성 파운드리 생산수주': '삼성이 자체 로봇칩을 만드는 것과 별개로 외부 로봇·피지컬AI 칩의 파운드리 매출을 확보하는 경로입니다. 고객·공정노드·웨이퍼 물량·양산 시점을 분리합니다.',
            '양산·상업 출하': '샘플·디자인윈이 반복 가능한 출하 매출로 전환되는 단계입니다. 실제 출하량·가동률·수율·고객 재주문을 확인합니다.',
            '전성비·지연 정량 개선': '휴머노이드에서 제한적인 전력·발열 예산 안에 더 큰 모델과 센서 처리를 넣을 수 있는지 보는 핵심 기술 재평가 신호입니다. 동일 조건의 성능/와트·지연시간을 비교합니다.',
            '개발·양산 일정 후퇴': '로봇 전용 실리콘은 소프트웨어 포팅·전력·발열·안전·고객 검증 때문에 일정이 밀릴 수 있습니다. 새 샘플·양산 일정을 확인합니다.',
        }.get(raw, '전문가 전망과 회사의 실제 제품·고객·양산 단계를 엄격히 분리합니다.')

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


    if cat.startswith('로봇 반도체'):
        raw = cat.split(' · ', 1)[-1]
        if raw == '레이버트 전망 기준선':
            return '전문가의 산업전망은 기업의 실제 개발계획이 아닙니다. 삼성·Google은 공식 로봇 전용 실리콘 발표가 나오기 전까지 기대감 단계로 고정합니다.'
        if raw == '로봇 OEM 채택·디자인윈':
            return '디자인윈도 고객 로봇의 양산 지연·이중조달·소프트웨어 변경으로 실제 출하가 늦어질 수 있습니다. 고객 SOP와 반복 주문을 확인합니다.'
        if raw == '삼성 파운드리 생산수주':
            return '파운드리 수주와 삼성 자체 로봇칩 사업은 다른 수익경로입니다. 고객 칩의 양산수율·웨이퍼 투입량·단가와 자체 System LSI 제품을 분리합니다.'
        if raw == '전성비·지연 정량 개선':
            return '벤치마크 조건이 다르면 우위를 과대평가할 수 있습니다. 같은 모델·정밀도·전력한도·열설계 조건에서 검증하고 로봇의 실제 연속가동 성능을 봅니다.'
        return '칩 성능만으로 로봇 플랫폼 채택이 결정되지 않습니다. CUDA/ROCm/Arm 생태계, 실시간 제어, 센서 I/O, 기능안전, 발열과 공급 안정성이 함께 병목이 됩니다.'

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
    if group == 'robot_compute_semiconductor':
        stage = _robot_compute_stage(text, src)
        if stage == 'expert_outlook_baseline':
            return '뉴스1의 마크 레이버트 현장 직접발언 + SLW·서울시 공식 행사 확인 · 기업별 로봇칩 프로그램은 미확정'
        if src in base.OFFICIAL_OR_PRIMARY:
            return '반도체·로봇 기업 공식자료 · 개발/샘플/채택/양산 단계 분리'
        if src in base.TRUSTED:
            return '신뢰 매체 보도 · 해당 반도체사·로봇 OEM 공식자료로 단계 교차확인'
        return '미확인 보도 · 단독 알림 금지'
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


    if group == 'robot_compute_semiconductor':
        stage = _robot_compute_stage(text, item.get('source') or '')
        if stage == 'expert_outlook_baseline':
            return hashlib.sha256(b'robot-compute|raibert|slw2026|samsung-google-amd-arm-outlook').hexdigest()
        if stage == 'known_vendor_baseline':
            vendor = 'nvidia' if re.search(r'NVIDIA|엔비디아', text, re.I) else (
                'amd' if re.search(r'AMD|Advanced\\s*Micro', text, re.I) else 'arm'
            )
            return hashlib.sha256(f'robot-compute|known-baseline|{vendor}'.encode()).hexdigest()
        vendors = []
        for name, pat in [
            ('samsung', r'삼성전자|Samsung\\s*Electronics|Samsung\\s*System\\s*LSI|System\\s*LSI'),
            ('nvidia', r'NVIDIA|엔비디아'), ('amd', r'AMD|Advanced\\s*Micro\\s*Devices'),
            ('arm', r'\\bArm\\b|Arm\\s*Holdings'), ('google', r'Google|구글'),
        ]:
            if re.search(pat, text, re.I): vendors.append(name)
        oems = sorted(set(re.findall(
            r'Boston\\s+Dynamics|Figure\\s*AI|Agility\\s+Robotics|Unitree|Apptronik|XPENG|ROBOTIS|로보티즈|현대차|Hyundai',
            text, re.I,
        )))
        nums = '|'.join(sorted(set(re.findall(
            r'\\d[\\d,.]*\\s*(?:TOPS|TFLOPS|W|watts?|nm|대|개|만대|million|billion)',
            text,
            re.I,
        )))[:6])
        return hashlib.sha256(
            f"robot-compute|{stage}|{','.join(vendors)}|{','.join(oems)}|{nums}".encode()
        ).hexdigest()

    return _orig_key(item)


def tag_for(group: str) -> str:
    if group == 'korea_robot_scale_policy':
        return '한국로봇정책'
    if group == 'samsung_robot_scale':
        return '삼성전자로봇'
    if group == 'robot_compute_semiconductor':
        return '로봇반도체'
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
    if _is_robot_compute(text):
        return {
            'official_program': '로봇 반도체, 공식 개발·로드맵 신규 확인',
            'silicon_launch': '로봇 반도체, 신규 전용칩·프로세서 공개',
            'tapeout_or_sample': '로봇 반도체, 테이프아웃·고객 샘플 단계 진입',
            'robot_oem_design_win': '로봇 반도체, 로봇 OEM 채택·디자인윈 확인',
            'foundry_contract': '삼성 파운드리, 로봇·피지컬AI 칩 생산수주 확인',
            'mass_production_or_shipment': '로봇 반도체, 실제 양산·상업 출하 시작',
            'quantified_performance': '로봇 반도체, 전성비·지연 정량 개선 확인',
            'reverse': '로봇 반도체, 개발·양산 일정 후퇴',
        }.get(_robot_compute_stage(text, source), _orig_clean_title(title, source))
    return _orig_clean_title(title, source)


def select_diverse(items: list[dict], seen: set[str], force: bool, limit: int) -> list[dict]:
    chosen = _orig_select_diverse(items, seen, force, limit)
    candidates = items if force else [x for x in items if x.get('key') not in seen]
    for group in ('korea_robot_scale_policy', 'samsung_robot_scale', 'robot_compute_semiconductor'):
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
