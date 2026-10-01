#!/usr/bin/env python3
"""U.S. autonomous-warfare commercialization / acquisition lane.

Extends the existing Physical-AI watcher. No new workflow, Telegram bot or state
file is created.

Current baselines locked:
- 2026-09-30 Pentagon announcement of a four-star Autonomous Warfare Command
  (AUTOWARCOM) with service-like authorities, targeted to stand up by 2027-10-01;
- Project Meridian formation with Elon Musk, Palmer Luckey and Newt Gingrich to
  study future warfare; the announcement itself is not a procurement award;
- the older 2026-04-23 SOUTHCOM Autonomous Warfare Command is a separate regional
  command and must not be confused with the later Pentagon-wide four-star command;
- FY2027 "Drone Dominance Requirement" proposal of $53.6bn is a proposal baseline,
  not enacted spending or realized supplier revenue.

Alert only on execution: formal establishment/IOC/FOC, commander nomination or
confirmation, final appropriations, named acquisition authorities, competitions,
awards/orders, vendor/customer quantities, operational deployments, Project
Meridian report/recommendations tied to concrete programs, or material reversals.
"""
from __future__ import annotations

import hashlib
import re

import physical_ai_watch_korea_robot_scale as current

base = current.base

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
    '("Autonomous Warfare Command" OR AUTOWARCOM OR "Autowarcom") (Pentagon OR "Department of War" OR Hegseth) (four-star OR combatant OR autonomous OR robotic OR drone OR procurement OR operational)',
    '("Project Meridian" AND (Musk OR "Palmer Luckey" OR Gingrich)) (Pentagon OR defense OR warfare OR weapons OR systems OR report OR recommendations)',
    '("Defense Autonomous Warfare Group" OR "Autonomous Warfare Group") (Pentagon OR "Department of War") (budget OR procurement OR acquisition OR contract OR order OR drone OR robot OR autonomous)',
    '("Autonomous Warfare Command" OR AUTOWARCOM) (commander OR nomination OR Senate OR confirmed OR headquarters OR "initial operational capability" OR "full operational capability" OR activated OR stood up)',
    '("Autonomous Warfare Command" OR "Project Meridian" OR "Defense Autonomous Warfare Group") (contract OR award OR order OR procurement OR competition OR vendor OR fielded OR deployed OR production)',
    'site:war.gov ("Autonomous Warfare Command" OR "Project Meridian" OR "Defense Autonomous Warfare Group" OR "Drone Dominance Requirement")',
    'site:comptroller.war.gov ("Drone Dominance Requirement" OR "Collaborative Autonomy" OR "Defense Autonomous Warfare")',
]:
    if q not in base.QUERIES:
        base.QUERIES.append(q)

base.OFFICIAL_OR_PRIMARY.update({
    'U.S. Department of War', 'Department of War', 'U.S. Department of Defense',
    'Department of Defense', 'Pentagon', 'U.S. Southern Command', 'SOUTHCOM',
    'U.S. Special Operations Command', 'USSOCOM', 'Congress', 'U.S. Congress',
})
base.TRUSTED.update({
    'Reuters', 'Associated Press', 'AP', 'Defense One', 'Breaking Defense',
    'Defense Daily', 'Air & Space Forces Magazine', 'The Wall Street Journal',
    'Financial Times', '서울경제',
})

PRICE_ONLY = re.compile(r'주가|급등|특징주|수혜주|shares?\s*(?:jump|rise|surge)|stock\s*price', re.I)

AUTOWARCOM = re.compile(r'Autonomous\s+Warfare\s+Command|AUTOWARCOM|AutoWarCom|자율\s*전쟁\s*사령부', re.I)
SOUTHCOM = re.compile(r'U\.S\.\s*Southern\s*Command|SOUTHCOM|Southcom|미\s*남부사령부', re.I)
MERIDIAN = re.compile(r'Project\s+Meridian|프로젝트\s*메리디언', re.I)
DAWG = re.compile(r'Defense\s+Autonomous\s+Warfare\s+Group|Autonomous\s+Warfare\s+Group|국방\s*자율전쟁\s*그룹', re.I)
PENTAGON = re.compile(r'Pentagon|Department\s+of\s+(?:War|Defense)|War\s+Department|미\s*국방|국방부', re.I)
AUTONOMY = re.compile(r'autonomous|robotic|robots?|drone|unmanned|AI|자율|로봇|드론|무인|인공지능', re.I)
MUSK_PANEL = re.compile(r'Elon\s+Musk|일론\s*머스크|Palmer\s+Luckey|팔머\s*럭키|Newt\s+Gingrich|뉴트\s*깅리치', re.I)

BASELINE_ANNOUNCE = re.compile(
    r'announc(?:e|ed|es|ing)|creation\s+of|create\s+(?:a\s+)?new|plans?\s+to\s+(?:create|establish)|'
    r'신설\s*(?:계획|발표)|창설\s*(?:계획|발표)|신설한다|창설한다',
    re.I,
)
BASELINE_DEADLINE = re.compile(r'2027.{0,20}(?:10월\s*1일|Oct(?:ober)?\.?\s*1)|Oct(?:ober)?\.?\s*1,?\s*2027', re.I)
SOUTHCOM_BASELINE = re.compile(r'2026.{0,30}(?:April|Apr\.?|4월)\s*23|April\s+23,?\s*2026', re.I)
BUDGET_BASELINE = re.compile(r'Drone\s+Dominance\s+Requirement|53\.6\s*billion|\$\s*53\.6\s*(?:billion|bn)|53,?600\s*million', re.I)

FORMAL_ESTABLISH = re.compile(
    r'(?:formally\s+)?(?:established|activated|stood\s+up|stands?\s+up|operational)|'
    r'(?:정식\s*)?(?:창설\s*완료|출범|가동\s*개시|운용\s*개시)',
    re.I,
)
IOC_FOC = re.compile(r'initial\s+operational\s+capability|full\s+operational\s+capability|\bIOC\b|\bFOC\b|초기\s*운용능력|완전\s*운용능력', re.I)
COMMANDER = re.compile(r'(?:four[-\s]?star|4성|대장).{0,80}(?:commander|지휘관)|(?:commander|지휘관).{0,80}(?:nominated|confirmed|assumed\s+command|취임|지명|인준)', re.I)
HQ_STAFF = re.compile(r'headquarters|본부\s*위치|본부\s*설치|staffing|정원|인력\s*배치|service[-\s]*like\s+authorit', re.I)

MERIDIAN_REPORT = re.compile(
    r'Project\s+Meridian.{0,140}(?:report|recommendation|findings|delivered|submitted|released|unveiled)|'
    r'(?:report|recommendation|findings|보고서|권고안|제안).{0,140}Project\s+Meridian|'
    r'프로젝트\s*메리디언.{0,140}(?:보고서|권고안|제출|공개)',
    re.I,
)
MERIDIAN_BASELINE = re.compile(
    r'Project\s+Meridian.{0,140}(?:Musk|Luckey|Gingrich|study\s+the\s+future\s+of\s+warfare)|'
    r'프로젝트\s*메리디언.{0,140}(?:머스크|럭키|깅리치|미래\s*전쟁)',
    re.I,
)

FINAL_BUDGET = re.compile(
    r'appropriat(?:e|ed|ion)|enacted|signed\s+into\s+law|Congress.{0,60}(?:approved|passed)|'
    r'의회.{0,60}(?:통과|승인)|예산.{0,40}(?:확정|법안\s*통과)|세출.{0,40}(?:확정|승인)',
    re.I,
)
ACQUISITION_AUTHORITY = re.compile(r'acquisition\s+authorit|procurement\s+authorit|budget\s+authorit|rapid\s+acquisition|warfighting\s+acquisition|조달\s*권한|획득\s*권한|예산\s*권한', re.I)
PROCUREMENT = re.compile(r'contract|award(?:ed)?|order|procurement|purchase\s+order|selected\s+vendor|competition|downselect|OT[Aa]?|IDIQ|수주|계약\s*체결|발주|조달\s*계약|업체\s*선정|경쟁\s*사업', re.I)
FIELDING = re.compile(r'fielded|deployed|deployment|operational\s+use|combat\s+deployment|thousands?\s+of\s+drones|수천\s*대|실전\s*배치|현장\s*배치|작전\s*배치|전력화', re.I)
PRODUCTION = re.compile(r'mass\s+production|production\s+rate|monthly\s+output|annual\s+capacity|양산|월\s*생산|연간\s*생산능력', re.I)

REVERSE = re.compile(
    r'(?:AUTOWARCOM|Autonomous\s+Warfare\s+Command|Project\s+Meridian|Defense\s+Autonomous\s+Warfare\s+Group).{0,140}'
    r'(?:delay|delayed|postpone|blocked|cancel|cut|rejected|hold|suspend|연기|지연|차단|취소|삭감|보류|중단)|'
    r'(?:Congress|의회|Senate|상원).{0,120}(?:block|reject|cut|hold|delay|차단|거부|삭감|보류|지연).{0,80}'
    r'(?:autonomous|drone|robot|AUTOWARCOM|자율|드론|로봇)',
    re.I,
)


def _is_us_autowar(text: str) -> bool:
    anchor = AUTOWARCOM.search(text) or MERIDIAN.search(text) or DAWG.search(text)
    southcom_anchor = SOUTHCOM.search(text) and re.search(r'Autonomous\s+Warfare\s+Command|자율\s*전쟁\s*사령부', text, re.I)
    return bool((anchor or southcom_anchor) and (PENTAGON.search(text) or SOUTHCOM.search(text) or MUSK_PANEL.search(text)) and AUTONOMY.search(text))


def _stage(text: str) -> str:
    if REVERSE.search(text):
        return 'reverse'
    if MERIDIAN_REPORT.search(text):
        return 'meridian_report'
    if COMMANDER.search(text):
        return 'commander'
    if IOC_FOC.search(text):
        return 'operational_capability'
    if FORMAL_ESTABLISH.search(text) and not BASELINE_ANNOUNCE.search(text):
        return 'formal_establishment'
    if PROCUREMENT.search(text) and (AUTOWARCOM.search(text) or DAWG.search(text) or MERIDIAN.search(text)):
        return 'procurement'
    if FIELDING.search(text) and (AUTOWARCOM.search(text) or DAWG.search(text) or SOUTHCOM.search(text)):
        return 'fielding'
    if PRODUCTION.search(text) and (AUTOWARCOM.search(text) or DAWG.search(text)):
        return 'production'
    if FINAL_BUDGET.search(text) and (BUDGET_BASELINE.search(text) or AUTOWARCOM.search(text) or DAWG.search(text)):
        return 'final_budget'
    if ACQUISITION_AUTHORITY.search(text) and (AUTOWARCOM.search(text) or DAWG.search(text)):
        return 'authority'
    if HQ_STAFF.search(text) and AUTOWARCOM.search(text):
        return 'standup_progress'
    if SOUTHCOM.search(text) and SOUTHCOM_BASELINE.search(text):
        return 'southcom_baseline'
    if MERIDIAN_BASELINE.search(text) and not MERIDIAN_REPORT.search(text):
        return 'meridian_baseline'
    if BUDGET_BASELINE.search(text) and not FINAL_BUDGET.search(text):
        return 'budget_baseline'
    if AUTOWARCOM.search(text) and BASELINE_ANNOUNCE.search(text):
        return 'autowarcom_baseline'
    return 'monitor'


def topic_group(text: str) -> str | None:
    if _is_us_autowar(text):
        return 'us_autonomous_warfare'
    return _orig_topic_group(text)


def score(item: dict) -> int:
    title = item.get('title', '')
    text = f"{title} {item.get('description','')} {item.get('source','')}"
    if topic_group(text) != 'us_autonomous_warfare':
        return _orig_score(item)

    stage = _stage(text)
    if stage in {'autowarcom_baseline', 'meridian_baseline', 'southcom_baseline', 'budget_baseline', 'monitor'}:
        return 0
    if PRICE_ONLY.search(title):
        return -20

    src = item.get('source') or ''
    s = 21
    if base.NUMERIC.search(text): s += 3
    if src in base.OFFICIAL_OR_PRIMARY: s += 8
    elif src in base.TRUSTED: s += 4
    s += {
        'standup_progress': 8,
        'commander': 12,
        'formal_establishment': 14,
        'operational_capability': 15,
        'final_budget': 12,
        'authority': 11,
        'procurement': 16,
        'production': 14,
        'fielding': 16,
        'meridian_report': 13,
        'reverse': 15,
    }.get(stage, 0)
    return s


def category(text: str, group: str) -> str:
    if group != 'us_autonomous_warfare':
        return _orig_category(text, group)
    return {
        'autowarcom_baseline': '미국 자율전쟁 · AUTOWARCOM 창설 발표 기준선',
        'meridian_baseline': '미국 자율전쟁 · Project Meridian 기준선',
        'southcom_baseline': '미국 자율전쟁 · SOUTHCOM 지역사령부 기준선',
        'budget_baseline': '미국 자율전쟁 · FY2027 드론예산 제안 기준선',
        'standup_progress': '미국 자율전쟁 · AUTOWARCOM 조직·권한 구체화',
        'commander': '미국 자율전쟁 · 4성 지휘관 지명·인준',
        'formal_establishment': '미국 자율전쟁 · AUTOWARCOM 정식 출범',
        'operational_capability': '미국 자율전쟁 · 초기·완전 운용능력',
        'final_budget': '미국 자율전쟁 · 의회 확정예산',
        'authority': '미국 자율전쟁 · 조달·획득 권한 확대',
        'procurement': '미국 자율전쟁 · 자율무기 실제 조달·수주',
        'production': '미국 자율전쟁 · 드론·로봇 양산 확대',
        'fielding': '미국 자율전쟁 · 드론·로봇 실전 배치',
        'meridian_report': '미국 자율전쟁 · Project Meridian 권고안 공개',
        'reverse': '미국 자율전쟁 · 예산·조직·일정 후퇴',
    }.get(_stage(text), '미국 자율전쟁 · 후속 실행')


def meaning(cat: str) -> str:
    if not cat.startswith('미국 자율전쟁'):
        return _orig_meaning(cat)
    raw = cat.split(' · ', 1)[-1]
    return {
        'AUTOWARCOM 조직·권한 구체화': '9월30일 창설 발표가 실제 본부·인력·service-like authority·획득권한으로 내려오는 단계입니다. 조직표, 예산권, 조달권과 실행일을 확인합니다.',
        '4성 지휘관 지명·인준': '신설 사령부가 실제 지휘체계를 갖추는 단계입니다. 지명자, 상원 인준, 취임일과 기존 DAWG·각 군의 권한 이관을 확인합니다.',
        'AUTOWARCOM 정식 출범': '발표를 넘어 사령부가 법적·조직적으로 실제 가동되는 단계입니다. 초기 조직·예산·사업 포트폴리오와 첫 조달을 추적합니다.',
        '초기·완전 운용능력': '조직 신설이 실제 전력 운용능력으로 바뀌는 단계입니다. 무인기·로봇·AI 지휘통제의 작전 임무와 배치 물량을 확인합니다.',
        '의회 확정예산': 'FY2027 자율전쟁·드론 예산이 제안에서 실제 집행 가능한 세출로 바뀌는 단계입니다. 제안액 대비 증감과 세부 지출처를 확인합니다.',
        '조달·획득 권한 확대': '자율체계 구매 의사결정과 자금이 기존 관료 절차에서 현장·사령부로 더 가까이 이동하는 신호입니다. 계약기간 단축과 경쟁사업 규모를 추적합니다.',
        '자율무기 실제 조달·수주': '자율전쟁 구상이 업체·계약금액·물량으로 바뀌는 가장 직접적인 매출 신호입니다. SpaceX·Anduril 등을 포함해 업체 실명, 계약번호, 수량, 납기와 반복발주를 분리합니다.',
        '드론·로봇 양산 확대': '조달 계획이 생산속도·월출하량·공장 증설로 바뀌는 단계입니다. 실제 주문보다 설비가 먼저 늘어나는지 함께 확인합니다.',
        '드론·로봇 실전 배치': '시제품·시험을 넘어 작전 현장에서 실제 사용되는 단계입니다. 배치대수, 임무, 소모율, 재발주와 유지보수 수요를 확인합니다.',
        'Project Meridian 권고안 공개': '머스크·럭키·깅리치의 미래전 연구가 구체 무기체계·예산·조달 우선순위로 바뀌는 단계입니다. 권고와 실제 계약을 반드시 분리합니다.',
        '예산·조직·일정 후퇴': '의회·국방부 내부 절차에서 사령부 출범, 예산, 조달권한 또는 프로젝트 일정이 밀리는 역방향 신호입니다.',
    }.get(raw, '9월30일 AUTOWARCOM·Project Meridian 발표와 기존 SOUTHCOM 지역 자율전쟁사령부는 기준선입니다. 반복 헤드라인은 침묵하고 실제 조직·예산·조달·배치 변화만 알립니다.')


def risk(cat: str) -> str:
    if not cat.startswith('미국 자율전쟁'):
        return _orig_risk(cat)
    raw = cat.split(' · ', 1)[-1]
    if raw == '자율무기 실제 조달·수주':
        return '위원회 참여·정책 자문과 계약 수주는 다릅니다. Musk·SpaceX 또는 Luckey·Anduril 이름이 함께 등장해도 계약번호·금액·물량·납기가 없으면 매출로 승격하지 않습니다.'
    if raw == 'Project Meridian 권고안 공개':
        return '권고안은 조달결정이 아닙니다. 실제 예산 반영, 경쟁사업 공고, 업체선정과 계약 체결을 후속 단계로 분리합니다.'
    if raw in {'AUTOWARCOM 정식 출범', '초기·완전 운용능력'}:
        return '사령부 출범과 무인체계 실전 신뢰성은 별개입니다. 통신교란·GPS 거부환경·오인식·사이버공격·사람의 통제권과 책임소재가 핵심 실패모드입니다.'
    if raw == '드론·로봇 실전 배치':
        return '실전 투입은 소모율·오인식·통신두절·전자전 환경에서 성능이 악화될 수 있습니다. 임무성공률과 손실률, 재발주 속도를 함께 봅니다.'
    if raw == '예산·조직·일정 후퇴':
        return '신설 사령부는 의회 예산·인준·권한조정에 영향을 받습니다. 발표된 2027년 일정이 법적·예산상 확정된 날짜와 같은 의미는 아닙니다.'
    return '정책 발표·자문위원 위촉·예산제안은 실제 수주가 아닙니다. 최종 세출, 조달공고, 업체선정, 계약, 생산, 배치를 순서대로 확인합니다.'


def verification(item: dict, group: str, text: str) -> str:
    if group != 'us_autonomous_warfare':
        return _orig_verification(item, group, text)
    src = item.get('source') or ''
    if src in base.OFFICIAL_OR_PRIMARY:
        return '미 국방·의회 공식자료 · 발표/예산제안/조달/배치 단계를 분리'
    if src == 'Reuters':
        return '로이터 보도 · 미 국방부 공식자료·예산문서 교차확인'
    if src in base.TRUSTED:
        return '신뢰 매체 보도 · 미 국방부·의회·계약 원문 교차확인'
    return '보도 단계 · 미 국방부·의회·계약 원문 재확인 필요'


def _numbers(text: str) -> str:
    nums = sorted(set(re.findall(r'\$?\s*\d[\d,.]*\s*(?:billion|bn|million|m|%|대|개|달러)?', text, re.I)))
    return '|'.join(nums[:6]) if nums else 'no-number'


def key(item: dict) -> str:
    text = f"{item.get('title','')} {item.get('description','')} {item.get('source','')}"
    if topic_group(text) != 'us_autonomous_warfare':
        return _orig_key(item)
    stage = _stage(text)
    actors = []
    for name, pat in [
        ('musk', r'Musk|머스크'), ('luckey', r'Luckey|럭키'), ('gingrich', r'Gingrich|깅리치'),
        ('spacex', r'SpaceX'), ('anduril', r'Anduril'), ('southcom', r'SOUTHCOM|Southern\s+Command'),
    ]:
        if re.search(pat, text, re.I): actors.append(name)
    return hashlib.sha256(
        f"us-autonomous-warfare|{stage}|{','.join(actors)}|{_numbers(text)}".encode()
    ).hexdigest()


def tag_for(group: str) -> str:
    if group == 'us_autonomous_warfare':
        return '미국자율전쟁'
    return _orig_tag_for(group)


def clean_title(title: str, source: str) -> str:
    text = f"{title} {source}"
    if not _is_us_autowar(text):
        return _orig_clean_title(title, source)
    return {
        'standup_progress': '미국 AUTOWARCOM, 조직·조달권한 구체화',
        'commander': '미국 AUTOWARCOM 4성 지휘관 지명·인준 진전',
        'formal_establishment': '미국 AUTOWARCOM 정식 출범',
        'operational_capability': '미국 AUTOWARCOM 초기·완전 운용능력 진전',
        'final_budget': '미국 자율전쟁·드론 예산, 의회 확정 단계',
        'authority': '미국 AUTOWARCOM 조달·획득 권한 확대',
        'procurement': '미국 자율전쟁, 자율무기 실제 조달·계약 발생',
        'production': '미국 자율전쟁, 드론·로봇 양산 확대',
        'fielding': '미국 자율전쟁, 드론·로봇 실전 배치 확대',
        'meridian_report': 'Project Meridian 미래전 권고안 공개',
        'reverse': '미국 자율전쟁 사령부·예산·일정 후퇴',
    }.get(_stage(text), _orig_clean_title(title, source))


def select_diverse(items: list[dict], seen: set[str], force: bool, limit: int) -> list[dict]:
    chosen = _orig_select_diverse(items, seen, force, limit)
    candidates = items if force else [x for x in items if x.get('key') not in seen]
    hit = next((x for x in candidates if x.get('group') == 'us_autonomous_warfare'), None)
    if not hit or any(x.get('key') == hit.get('key') for x in chosen):
        return chosen
    if len(chosen) < limit:
        return [hit, *chosen]
    return [hit, *chosen[:-1]]


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
