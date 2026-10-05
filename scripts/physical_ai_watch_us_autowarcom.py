#!/usr/bin/env python3
"""U.S. Autonomous Warfare Command / Project Meridian commercialization lane.

Extends the existing Physical-AI watcher. No new workflow, Telegram bot or state
file is created.

Baseline locked as of 2026-09-30:
- Defense Secretary Pete Hegseth announced a planned four-star Autonomous Warfare
  Command (AUTOWARCOM) to scale autonomous and robotic capabilities across the
  joint force.
- Project Agincourt is the interim autonomy/acquisition construct led by Defense
  Innovation Unit director Owen West and Max Strasiser while the department works
  with Congress toward the new command, with an October 2027 stand-up target
  reported from the official memo.
- Project Meridian is a future-warfare study co-led by Elon Musk, Palmer Luckey
  and Newt Gingrich; its role is advisory/study, not operational command. The
  reported due date for the study is 2027-01-28.
- On 2026-10-05 MITRE and Agility Robotics confirmed Peggy Johnson as a Project
  Meridian participant in an individual consultant capacity. Agility explicitly
  says this is separate from its commercial operations; this known participation
  is a silent baseline, not a defense contract or Digit deployment.
- Repeated articles about those announcements are silent baselines.

New alerts require an execution-stage change: legislation/authorization/funding,
formal stand-up and commander appointment, acquisition authority, Project
Agincourt contract/prototype/production awards, quantified field deployment,
Project Meridian report/recommendations, autonomy-policy changes, or a reverse
signal such as delay/cancellation/funding cut.
"""
from __future__ import annotations

import hashlib
import re

import physical_ai_watch_korea_robot_scale as korea

qty = korea.qty
base = korea.base

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
    '("Autonomous Warfare Command" OR AUTOWARCOM OR "Project Agincourt") (Pentagon OR "Department of Defense" OR Hegseth OR autonomy OR robotic OR drone)',
    '("Autonomous Warfare Command" OR AUTOWARCOM) (Congress OR NDAA OR authorization OR legislation OR funding OR budget OR commander OR "four-star" OR stand-up OR operational)',
    '("Project Agincourt") (contract OR award OR prototype OR production OR procurement OR quantity OR deployment OR DIU OR "Defense Innovation Unit")',
    '("Project Meridian") ("Elon Musk" OR "Palmer Luckey" OR "Newt Gingrich") (report OR recommendation OR January 28 2027 OR capability gap OR future warfare)',
    '("Project Meridian") (Pentagon OR "Department of Defense") (released OR report OR recommendations OR procurement OR autonomy OR robotics OR AI)',
    '("Project Meridian") (participant OR member OR selected OR joins OR advisor OR consultant) (robotics OR humanoid OR autonomy OR AI OR logistics OR defense technology)',
    '("Project Meridian") ("Agility Robotics" OR "Peggy Johnson" OR Digit OR humanoid OR robotics OR logistics)',
    '("Agility Robotics" OR Digit) (Pentagon OR "Department of War" OR "Department of Defense" OR MITRE OR military) (contract OR award OR procurement OR pilot OR trial OR evaluation OR deployment OR logistics)',
    '("Defense Autonomous Warfare Group" OR DAWG) (budget OR procurement OR contract OR award OR production OR deployment OR autonomous OR robotic OR drone)',
    '("Autonomous Warfare Command" OR AUTOWARCOM OR "Defense Autonomous Warfare Group") (Anduril OR SpaceX OR "Shield AI" OR Skydio OR AeroVironment OR contract OR award OR order OR production)',
    '("SOUTHCOM" OR "U.S. Southern Command") "Autonomous Warfare Command" (deployment OR fielded OR contract OR exercise OR operational)',
    'site:defense.gov ("Autonomous Warfare Command" OR AUTOWARCOM OR "Project Agincourt" OR "Project Meridian" OR "Defense Autonomous Warfare Group")',
    'site:war.gov ("Autonomous Warfare Command" OR AUTOWARCOM OR "Project Meridian" OR "Defense Autonomous Warfare Group" OR "Drone Dominance Requirement")',
    'site:congress.gov ("Autonomous Warfare Command" OR "Robotic and Autonomous Systems Combatant Command")',
    'site:diu.mil ("Project Agincourt" OR autonomy) (contract OR prototype OR award OR production)',
    'site:comptroller.war.gov ("Drone Dominance Requirement" OR "Collaborative Autonomy" OR "Defense Autonomous Warfare")',
]:
    if q not in base.QUERIES:
        base.QUERIES.append(q)

base.OFFICIAL_OR_PRIMARY.update({
    'U.S. Department of Defense', 'Department of Defense', 'Defense.gov',
    'U.S. Department of War', 'Department of War', 'War.gov',
    'U.S. Southern Command', 'SOUTHCOM', 'U.S. Special Operations Command', 'USSOCOM',
    'Defense Innovation Unit', 'DIU', 'Congress.gov', 'U.S. Congress',
    'MITRE', 'The MITRE Corporation', 'Agility Robotics',
    'U.S. Senate Armed Services Committee', 'Senate Armed Services Committee',
    'U.S. House Armed Services Committee', 'House Armed Services Committee',
})
base.TRUSTED.update({
    'Reuters', 'Breaking Defense', 'Defense News', 'Defense One', 'Defense Daily', 'The War Zone',
    'Air & Space Forces Magazine', 'The Wall Street Journal', 'Financial Times',
    'Bloomberg', 'Associated Press', 'AP', 'PR Newswire', 'Business Wire', '서울경제',
})

PRICE_ONLY = re.compile(
    r'주가|급등|특징주|수혜주|stock\s*price|shares?\s*(?:jump|rise|surge)',
    re.I,
)

AUTOWAR = re.compile(
    r'Autonomous\s+Warfare\s+Command|AUTOWARCOM|'
    r'Robotic\s+and\s+Autonomous\s+Systems\s+Combatant\s+Command|'
    r'자율전쟁사령부|자율\s*전쟁\s*사령부',
    re.I,
)
AGINCOURT = re.compile(r'Project\s+Agincourt|프로젝트\s*아쟁쿠르|아쟁쿠르', re.I)
MERIDIAN = re.compile(r'Project\s+Meridian|프로젝트\s*메리디언|메리디언', re.I)
DAWG = re.compile(r'Defense\s+Autonomous\s+Warfare\s+Group|\bDAWG\b|국방\s*자율전쟁\s*그룹', re.I)
SOUTHCOM = re.compile(r'U\.S\.\s*Southern\s+Command|SOUTHCOM|Southcom|미\s*남부사령부', re.I)
SOUTHCOM_AWC = re.compile(r'(?:SOUTHCOM|Southern\s+Command|미\s*남부사령부).{0,100}(?:Autonomous\s+Warfare\s+Command|자율\s*전쟁\s*사령부)|(?:Autonomous\s+Warfare\s+Command|자율\s*전쟁\s*사령부).{0,100}(?:SOUTHCOM|Southern\s+Command|미\s*남부사령부)', re.I)
DRONE_BUDGET_BASELINE = re.compile(r'Drone\s+Dominance\s+Requirement|\$?\s*53\.6\s*(?:billion|bn)|53,?600\s*(?:million|m)', re.I)
MUSK_GROUP = re.compile(
    r'Elon\s+Musk|일론\s*머스크|Palmer\s+Luckey|팔머\s*럭키|'
    r'Newt\s+Gingrich|뉴트\s*깅리치',
    re.I,
)
DEFENSE_CTX = re.compile(
    r'Pentagon|Department\s+of\s+Defense|Defense\s+Department|DoD|'
    r'Department\s+of\s+War|Hegseth|국방부|펜타곤|헤그세스|미군',
    re.I,
)

BASELINE = re.compile(
    r'(?:announc|plan|create|establish|신설|창설|발표|계획).{0,120}'
    r'(?:Autonomous\s+Warfare\s+Command|AUTOWARCOM|자율전쟁사령부)|'
    r'(?:Project\s+Meridian|프로젝트\s*메리디언).{0,180}'
    r'(?:Elon\s+Musk|일론\s*머스크|Palmer\s+Luckey|Newt\s+Gingrich)|'
    r'(?:Project\s+Agincourt|프로젝트\s*아쟁쿠르).{0,120}'
    r'(?:interim|temporary|중간\s*단계|임시|전환)',
    re.I | re.S,
)
LEGISLATION = re.compile(
    r'Congress|congressional|NDAA|National\s+Defense\s+Authorization|'
    r'authorization|authoriz(?:e|ed|ation)|legislation|bill|법안|국회|의회|'
    r'상원|하원|국방수권법|승인',
    re.I,
)
LEGISLATION_PASSED = re.compile(
    r'passed|enacted|signed\s+into\s+law|authorized|approved|adopted|'
    r'통과|가결|법제화|서명|승인',
    re.I,
)
FUNDING = re.compile(
    r'appropriat|funding|budget|million|billion|\$\s*\d|'
    r'예산|배정|세출|억\s*달러|십억\s*달러|백만\s*달러',
    re.I,
)
FORMAL_STANDUP = re.compile(
    r'formally\s+(?:established|stood\s+up|activated)|'
    r'officially\s+(?:established|activated)|activation|initial\s+operating\s+capability|'
    r'full\s+operating\s+capability|IOC|FOC|정식\s*(?:창설|출범)|'
    r'공식\s*(?:창설|출범)|초기\s*작전능력|완전\s*작전능력',
    re.I,
)
COMMANDER = re.compile(
    r'commander|commanding\s+general|four[-\s]?star|4[-\s]?star|'
    r'사령관|4성|대장',
    re.I,
)
ACQ_AUTHORITY = re.compile(
    r'acquisition\s+authorit|procurement\s+authorit|service[-\s]?like\s+authorit|'
    r'rapid\s+acquisition|warfighting\s+acquisition|획득\s*권한|조달\s*권한|'
    r'서비스급\s*권한|신속\s*획득',
    re.I,
)
CONTRACT = re.compile(
    r'contract|award|purchase\s+order|task\s+order|prototype\s+agreement|'
    r'production\s+award|procurement|수주|계약|발주|조달|시제품\s*계약|양산\s*계약',
    re.I,
)
QUANTITY = re.compile(
    r'\b\d[\d,.]*\s*(?:(?:autonomous|unmanned|robotic|attritable|one[-\s]*way(?:\s+attack)?)\s+)?'
    r'(?:systems?|units?|drones?|robots?|aircraft|vehicles?|million|billion|%|대|개|억\s*달러|백만\s*달러)\b|'
    r'\$\s*\d[\d,.]*(?:\s*(?:million|billion|m|bn))?',
    re.I,
)
DEPLOYMENT = re.compile(
    r'deploy|fielded|operational\s+deployment|combat\s+deployment|field\s+test|'
    r'exercise|실전\s*배치|현장\s*배치|배치\s*개시|전력화|야전\s*시험|훈련\s*투입',
    re.I,
)
MERIDIAN_REPORT = re.compile(
    r'(?:Project\s+Meridian|프로젝트\s*메리디언).{0,120}'
    r'(?:report|recommendation|findings?|released|published|제언|권고|보고서|결과\s*발표)',
    re.I | re.S,
)

MERIDIAN_MEMBER_ACTION = re.compile(
    r'selected\s+to\s+join|selected\s+for|joins?\s+Project\s+Meridian|'
    r'will\s+participate|new\s+participant|added\s+to|appointed\s+(?:to|as)|'
    r'named\s+(?:to|as)|participant(?:s)?|member(?:s)?|advisor|consultant|'
    r'참여\s*선정|참여한다|참여\s*예정|신규\s*참여|위원\s*선정|자문',
    re.I,
)
MERIDIAN_ROBOTICS_CTX = re.compile(
    r'Agility\s+Robotics|Peggy\s+Johnson|Digit\b|humanoid|robotics?|autonomous|'
    r'physical\s+AI|logistics?|operational\s+support|휴머노이드|로봇|자율|군수|물류',
    re.I,
)
MERIDIAN_PEGGY_BASELINE = re.compile(
    r'(?:Peggy\s+Johnson|Agility\s+Robotics).{0,260}(?:Project\s+Meridian|메리디언)|'
    r'(?:Project\s+Meridian|메리디언).{0,260}(?:Peggy\s+Johnson|Agility\s+Robotics)',
    re.I | re.S,
)
MERIDIAN_ROLE_UPGRADE = re.compile(
    r'co[-\s]*director|director|chair|lead(?:er|ing)?|expanded\s+role|'
    r'공동\s*책임자|공동\s*디렉터|책임자|의장|역할\s*확대',
    re.I,
)
AGILITY_DEFENSE = re.compile(r'Agility\s+Robotics|\bDigit(?:\s*5)?\b|Peggy\s+Johnson', re.I)
AGILITY_DEFENSE_CONTRACT = re.compile(
    r'contract|award|purchase\s+order|task\s+order|procurement|production\s+award|'
    r'공급\s*계약|본계약|수주|발주|조달|구매\s*계약|양산\s*계약',
    re.I,
)
AGILITY_DEFENSE_PILOT = re.compile(
    r'pilot\s+program|field\s+trial|operational\s+evaluation|military\s+evaluation|'
    r'defense\s+trial|deployed\s+(?:to|at|with)|deployment\s+(?:to|at|with)|'
    r'군\s*실증|군수\s*실증|현장\s*시험|운용\s*평가|군\s*배치',
    re.I,
)
MERIDIAN_INDIVIDUAL_CAPACITY = re.compile(
    r'individual\s+consultant|individual\s+capacity|separate\s+from\s+Agility(?:\'s)?\s+commercial\s+operations|'
    r'개인\s*컨설턴트|개인\s*자격|상업\s*사업과\s*독립|상업\s*운영과\s*분리',
    re.I,
)
AUTONOMY_POLICY = re.compile(
    r'Directive\s+3000\.09|DoD\s+Directive\s+3000\.09|'
    r'autonomy\s+in\s+weapon\s+systems|자율\s*무기\s*체계|자율무기',
    re.I,
)
POLICY_UPDATE = re.compile(
    r'updated|revised|issued|rescinded|effective|개정|업데이트|발령|시행|폐지',
    re.I,
)
BUDGET_PROPOSAL = re.compile(r'proposal|request|budget\s+request|PB\s*2027|FY\s*2027|예산안|정부안|요구액', re.I)
PRODUCTION = re.compile(r'mass\s+production|production\s+rate|monthly\s+output|annual\s+capacity|양산|월\s*생산|연간\s*생산능력', re.I)
SOUTHCOM_BASELINE = re.compile(r'April\s+23,?\s*2026|Apr\.?\s*23,?\s*2026|2026.{0,20}4월\s*23', re.I)
REVERSE = re.compile(
    r'(?:AUTOWARCOM|Autonomous\s+Warfare\s+Command|Project\s+Agincourt|Project\s+Meridian|자율전쟁사령부).{0,120}'
    r'(?:delay|postpone|cancel|blocked|rejected|cut|defund|suspend|연기|지연|취소|'
    r'무산|차단|부결|삭감|중단)|'
    r'(?:funding|budget|authorization|예산|승인).{0,100}(?:cut|rejected|blocked|삭감|부결|차단)',
    re.I | re.S,
)


def _is_lane(text: str) -> bool:
    return bool(
        AUTOWAR.search(text)
        or AGINCOURT.search(text)
        or DAWG.search(text)
        or SOUTHCOM_AWC.search(text)
        or (DRONE_BUDGET_BASELINE.search(text) and DEFENSE_CTX.search(text))
        or (MERIDIAN.search(text) and (MUSK_GROUP.search(text) or DEFENSE_CTX.search(text) or MERIDIAN_ROBOTICS_CTX.search(text)))
        or (AGILITY_DEFENSE.search(text) and DEFENSE_CTX.search(text))
        or (AUTONOMY_POLICY.search(text) and DEFENSE_CTX.search(text))
    )


def _stage(text: str) -> str:
    if REVERSE.search(text):
        return 'reverse'
    if MERIDIAN_REPORT.search(text):
        return 'meridian_report'
    # Company execution is stronger than advisory participation. Keep a future
    # Agility/Digit defense award or military pilot out of the current
    # Peggy-Johnson advisory baseline.
    if AGILITY_DEFENSE.search(text) and DEFENSE_CTX.search(text) and AGILITY_DEFENSE_CONTRACT.search(text):
        return 'agility_defense_contract'
    if AGILITY_DEFENSE.search(text) and DEFENSE_CTX.search(text) and AGILITY_DEFENSE_PILOT.search(text):
        return 'agility_defense_pilot'
    if MERIDIAN.search(text) and MERIDIAN_MEMBER_ACTION.search(text) and MERIDIAN_ROBOTICS_CTX.search(text):
        if (
            MERIDIAN_PEGGY_BASELINE.search(text)
            and not MERIDIAN_ROLE_UPGRADE.search(text)
            and not AGILITY_DEFENSE_CONTRACT.search(text)
            and not AGILITY_DEFENSE_PILOT.search(text)
        ):
            return 'meridian_participant_baseline'
        return 'meridian_participant_change'
    if AUTONOMY_POLICY.search(text) and POLICY_UPDATE.search(text):
        return 'autonomy_policy'
    if SOUTHCOM_AWC.search(text) and (
        SOUTHCOM_BASELINE.search(text)
        or (BASELINE.search(text) and not CONTRACT.search(text) and not DEPLOYMENT.search(text))
    ):
        return 'southcom_baseline'
    if DRONE_BUDGET_BASELINE.search(text) and BUDGET_PROPOSAL.search(text) and not re.search(
        r'enacted|signed\s+into\s+law|appropriated|Congress.{0,40}(?:passed|approved)|의회.{0,40}(?:통과|승인)|예산\s*확정',
        text,
        re.I,
    ):
        return 'budget_baseline'
    if FORMAL_STANDUP.search(text):
        return 'formal_standup'
    if AUTOWAR.search(text) and COMMANDER.search(text) and re.search(
        r'appointed|nominated|confirmed|selected|named|지명|임명|인준|선정', text, re.I
    ):
        return 'commander'
    if AUTOWAR.search(text) and ACQ_AUTHORITY.search(text) and re.search(
        r'granted|approved|authorized|received|부여|승인|확정', text, re.I
    ):
        return 'acquisition_authority'
    if AUTOWAR.search(text) and LEGISLATION.search(text) and LEGISLATION_PASSED.search(text):
        return 'legislation'
    if AUTOWAR.search(text) and FUNDING.search(text) and re.search(
        r'appropriat|approved|authorized|funded|배정|확정|승인', text, re.I
    ):
        return 'funding'
    # Production and deployment are stronger operating milestones than the
    # award language that may appear in the same article, so classify them first.
    if (AUTOWAR.search(text) or AGINCOURT.search(text) or DAWG.search(text)) and PRODUCTION.search(text) and QUANTITY.search(text):
        return 'production'
    if (AUTOWAR.search(text) or AGINCOURT.search(text) or DAWG.search(text) or SOUTHCOM_AWC.search(text)) and DEPLOYMENT.search(text) and QUANTITY.search(text):
        return 'deployment'
    if AGINCOURT.search(text) and CONTRACT.search(text) and QUANTITY.search(text):
        return 'agincourt_contract'
    if (AUTOWAR.search(text) or DAWG.search(text)) and CONTRACT.search(text) and QUANTITY.search(text):
        return 'autowar_contract'
    if BASELINE.search(text):
        return 'baseline'
    return 'monitor'


def topic_group(text: str) -> str | None:
    if _is_lane(text):
        return 'us_autonomous_warfare'
    return _orig_topic_group(text)


def score(item: dict) -> int:
    title = item.get('title', '')
    text = f"{title} {item.get('description','')} {item.get('source','')}"
    if topic_group(text) != 'us_autonomous_warfare':
        return _orig_score(item)

    stage = _stage(text)
    if stage in {'baseline', 'southcom_baseline', 'budget_baseline', 'meridian_participant_baseline', 'monitor'}:
        return 0
    if PRICE_ONLY.search(title):
        return -20

    src = item.get('source') or ''
    s = 20
    if base.NUMERIC.search(text):
        s += 3
    if src in base.OFFICIAL_OR_PRIMARY:
        s += 8
    elif src in base.TRUSTED:
        s += 4
    s += {
        'legislation': 13,
        'funding': 12,
        'formal_standup': 16,
        'commander': 13,
        'acquisition_authority': 14,
        'agincourt_contract': 15,
        'autowar_contract': 16,
        'production': 14,
        'deployment': 16,
        'meridian_report': 12,
        'meridian_participant_change': 10,
        'agility_defense_pilot': 15,
        'agility_defense_contract': 18,
        'autonomy_policy': 11,
        'reverse': 15,
    }.get(stage, 0)
    return s


def category(text: str, group: str) -> str:
    if group != 'us_autonomous_warfare':
        return _orig_category(text, group)
    return {
        'baseline': '미국 자율전쟁 · AUTOWARCOM·Project Meridian 기준선',
        'southcom_baseline': '미국 자율전쟁 · SOUTHCOM 지역사령부 기준선',
        'budget_baseline': '미국 자율전쟁 · FY2027 드론예산 제안 기준선',
        'meridian_participant_baseline': '미국 자율전쟁 · Project Meridian 휴머노이드 자문 참여 기준선',
        'meridian_participant_change': '미국 자율전쟁 · Project Meridian 로봇·AI 자문진 확대',
        'agility_defense_pilot': '미국 자율전쟁 · Agility Digit 국방 실증·운용평가',
        'agility_defense_contract': '미국 자율전쟁 · Agility Digit 국방 조달·수주',
        'legislation': '미국 자율전쟁 · AUTOWARCOM 법제화·승인',
        'funding': '미국 자율전쟁 · AUTOWARCOM 예산·재원 확정',
        'formal_standup': '미국 자율전쟁 · AUTOWARCOM 정식 창설·작전능력',
        'commander': '미국 자율전쟁 · AUTOWARCOM 사령관 지명·인준',
        'acquisition_authority': '미국 자율전쟁 · AUTOWARCOM 획득·조달권한',
        'agincourt_contract': '미국 자율전쟁 · Project Agincourt 시제품·양산계약',
        'autowar_contract': '미국 자율전쟁 · AUTOWARCOM·DAWG 실제 조달·수주',
        'production': '미국 자율전쟁 · 드론·로봇 양산 확대',
        'deployment': '미국 자율전쟁 · 자율·로봇 전력 실제 배치',
        'meridian_report': '미국 자율전쟁 · Project Meridian 보고서·권고',
        'autonomy_policy': '미국 자율전쟁 · 자율무기 정책 개정',
        'reverse': '미국 자율전쟁 · 일정·예산·승인 후퇴',
    }.get(_stage(text), '미국 자율전쟁 · 후속 실행')


def meaning(cat: str) -> str:
    if not cat.startswith('미국 자율전쟁'):
        return _orig_meaning(cat)
    raw = cat.split(' · ', 1)[-1]
    mapping = {
        'AUTOWARCOM 법제화·승인': '9월 30일 창설 발표가 의회의 법적 승인으로 넘어가는 단계입니다. AUTOWARCOM의 조직형태, 권한, 창설시점과 국방수권법 문구를 확인합니다.',
        'AUTOWARCOM 예산·재원 확정': '자율전쟁 사령부 구상이 실제 예산으로 바뀌는 단계입니다. 총액보다 드론·지상로봇·해양무인체계·AI·통신·시험평가에 돈이 어떻게 배분되는지 봅니다.',
        'AUTOWARCOM 정식 창설·작전능력': '계획 단계에서 실제 조직·작전운영 단계로 전환되는 핵심 시간표 신호입니다. IOC·FOC, 편제, 인력과 초기 장비물량을 확인합니다.',
        'AUTOWARCOM 사령관 지명·인준': '4성급 지휘체계가 실제 인선으로 구체화되는 조직 실행 신호입니다. 지명·상원 인준·취임일과 권한 범위를 분리해 확인합니다.',
        'AUTOWARCOM 획득·조달권한': '전투사령부가 자율·로봇 체계의 요구·시험·조달을 빠르게 연결할 수 있는 권한을 실제로 받는 단계입니다. 계약 속도와 생산량이 다음 매출 연결 지표입니다.',
        'Project Agincourt 시제품·양산계약': '중간 전환조직이 실제 업체·계약금액·수량으로 연결되는 첫 직접 매출 신호입니다. 시제품과 양산, 단발 계약과 반복조달을 분리합니다.',
        'AUTOWARCOM·DAWG 실제 조달·수주': '사령부·획득조직 구상이 실제 공급업체·계약금액·물량으로 전환되는 직접 매출 신호입니다. SpaceX·Anduril 등 참여기업의 자문·기존계약과 이번 자율전쟁 조달을 구분합니다.',
        '드론·로봇 양산 확대': '계약이 월 생산량·공장 증설·연간 생산능력으로 이어지는 단계입니다. 명목 생산능력과 실제 주문·출하량을 분리합니다.',
        '자율·로봇 전력 실제 배치': '조달된 자율체계가 훈련·작전부대에 실제 전력화되는 단계입니다. 배치 수량, 가동률, 손실률, 임무성공률과 재발주를 추적합니다.',
        'Project Meridian 보고서·권고': '머스크·럭키·깅리치 등이 참여한 미래전 연구가 구체적인 능력격차와 조달·조직 권고로 바뀌는 단계입니다. 자문보고서와 실제 국방부 채택·예산을 분리합니다.',
        'Project Meridian 휴머노이드 자문 참여 기준선': '2026년 10월 5일 MITRE와 Agility Robotics가 Peggy Johnson의 Project Meridian 참여를 확인했습니다. 개인 컨설턴트 자격이며 Agility의 상업사업과 분리된 자문 참여이므로 국방 매출·Digit 조달로 해석하지 않습니다.',
        'Project Meridian 로봇·AI 자문진 확대': 'Project Meridian의 참여구성이 로봇·AI·자율체계 전문가 쪽으로 추가 확대되는 정책·시간표 신호입니다. 자문 참여가 실제 권고문·시험평가·조달품목으로 이어지는지를 별도로 확인합니다.',
        'Agility Digit 국방 실증·운용평가': 'Agility의 상업 배치 경험이 개인 자문을 넘어 실제 군수·지원 현장의 Digit 시험·운용평가로 전환되는 단계입니다. 로봇 대수·시험장소·임무·가동률·안전평가와 후속 조달 여부를 확인합니다.',
        'Agility Digit 국방 조달·수주': '개인 자문과 별개로 Agility Robotics가 실제 국방 계약·구매주문·조달을 확보한 직접 매출 신호입니다. 계약금액·Digit 대수·납기·반복조달과 서비스·유지보수 범위를 분리합니다.',
        '자율무기 정책 개정': 'AI·자율무기 도입의 승인·시험·인간통제 기준이 바뀌는 규제 신호입니다. 정책 완화·강화가 실제 배치속도와 시험기간에 미치는 영향을 봅니다.',
        '일정·예산·승인 후퇴': 'AUTOWARCOM·Agincourt·Meridian의 법제화·예산·창설 시간표가 뒤로 밀리는 역방향 신호입니다. 지연원인이 의회, 예산, 기술검증, 안전인지 분리합니다.',
    }
    return mapping.get(
        raw,
        '9월 30일 AUTOWARCOM 창설 발표, Project Agincourt 전환계획, Project Meridian 연구그룹은 현재 기준선입니다. 반복 보도는 침묵합니다.',
    )


def risk(cat: str) -> str:
    if not cat.startswith('미국 자율전쟁'):
        return _orig_risk(cat)
    raw = cat.split(' · ', 1)[-1]
    if raw == 'Project Meridian 보고서·권고':
        return 'Project Meridian은 미래전 연구·자문기구입니다. 머스크 등이 군 지휘권이나 조달권을 직접 가진다고 해석하지 않고, 보고서 권고와 실제 국방부 채택·계약을 분리합니다.'
    if raw == 'Project Meridian 휴머노이드 자문 참여 기준선':
        return 'Peggy Johnson은 개인 컨설턴트 자격으로 참여하며 Agility Robotics는 이 활동이 자사 상업운영과 분리돼 있다고 명시했습니다. 따라서 현재 단계의 직접 국방매출은 0으로 두고, 회사 명의의 실증·계약이 나올 때만 상업 단계로 승격합니다.'
    if raw == 'Project Meridian 로봇·AI 자문진 확대':
        return '자문위원 추가는 계약이나 예산 배정이 아닙니다. 먼저 볼 지표는 MITRE 공식 명단 변경, 최종 보고서의 로봇·군수 권고, 국방부 채택 여부이며 실제 조달 전에는 매출로 계산하지 않습니다.'
    if raw == 'Agility Digit 국방 실증·운용평가':
        return '실증은 양산조달과 다릅니다. 안전성·가동률·원격지원·정비비용·군 환경 신뢰성 시험이 부족하면 후속 발주가 지연될 수 있습니다.'
    if raw == 'Agility Digit 국방 조달·수주':
        return '계약 총액과 실제 인식매출은 다를 수 있습니다. 옵션 물량·검수·성능보증·납기·취소조항을 확인하고 장기 유지보수 계약 포함 여부를 분리합니다.'
    if raw == 'AUTOWARCOM 법제화·승인':
        return '국방부의 창설 의지만으로 전투사령부의 획득권한이 자동 생기지는 않습니다. 의회 법안·최종 법률·예산·시행을 단계별로 확인합니다.'
    if raw == 'AUTOWARCOM 획득·조달권한':
        return '권한 부여와 실제 생산계약은 다릅니다. 공급업체, 계약금액, 수량, 납기와 전력화 시험을 별도 확인합니다.'
    if raw in {'Project Agincourt 시제품·양산계약', 'AUTOWARCOM·DAWG 실제 조달·수주'}:
        return '자문위원 참여·정책 발표와 실제 계약은 다릅니다. 계약번호·금액·수량·납기와 경쟁절차를 확인하고 시제품 계약과 양산 매출을 분리합니다.'
    if raw == '자율·로봇 전력 실제 배치':
        return '배치수량보다 실제 임무성공률·가동률·손실률이 중요합니다. GPS·통신 교란, 적대적 전자전, 오인식·안전 문제가 재발주를 막을 수 있습니다.'
    if raw == '자율무기 정책 개정':
        return '정책 문구 변경이 모든 무기체계 승인기간을 동일하게 줄이는 것은 아닙니다. 체계별 시험·법률검토·교전규칙과 인간통제 요구를 따로 봅니다.'
    if raw == '일정·예산·승인 후퇴':
        return '가장 현실적인 실패 경로는 의회가 조직·획득권한을 충분히 부여하지 않거나 예산을 늦춰 2027년 창설목표가 미뤄지는 경우입니다.'
    return '현재 AUTOWARCOM은 발표·설계 단계이며 정식 전투사령부 창설, 예산, 사령관, 획득권한과 실제 업체 수주는 아직 각각 별도 확인이 필요합니다.'


def verification(item: dict, group: str, text: str) -> str:
    if group != 'us_autonomous_warfare':
        return _orig_verification(item, group, text)
    src = item.get('source') or ''
    stage = _stage(text)
    if stage == 'meridian_participant_baseline':
        return 'MITRE·Agility Robotics 공식 확인 · Peggy Johnson 개인 컨설턴트 참여, Agility 상업운영과 분리 · 계약/조달 아님'
    if stage == 'meridian_participant_change' and src in {'MITRE', 'The MITRE Corporation', 'Agility Robotics'}:
        return 'MITRE 또는 참여기업 공식자료 · 자문 참여와 회사 계약·조달을 분리'
    if src in base.OFFICIAL_OR_PRIMARY:
        return '미 국방부·의회·DIU·MITRE·참여기업 공식자료 · 자문/정책/계약/배치 단계 분리'
    if src in base.TRUSTED:
        return '신뢰 국방·통신 보도 · 미 국방부·의회·DIU 공식자료 교차확인'
    return '보도 단계 · 미 국방부·의회·DIU 1차 자료 후속 확인'


def key(item: dict) -> str:
    text = f"{item.get('title','')} {item.get('description','')} {item.get('source','')}"
    if topic_group(text) != 'us_autonomous_warfare':
        return _orig_key(item)
    stage = _stage(text)
    if stage == 'baseline':
        return hashlib.sha256(b'us-autowar|2026-09-30|baseline').hexdigest()
    if stage == 'meridian_report':
        return hashlib.sha256(b'us-autowar|project-meridian|report').hexdigest()
    if stage == 'meridian_participant_baseline':
        return hashlib.sha256(b'us-autowar|project-meridian|peggy-johnson|individual-consultant|2026-10-05').hexdigest()
    if stage == 'meridian_participant_change':
        m = re.search(
            r'(?:CEO|CTO|President|Founder|General|Dr\.?|Ms\.?|Mr\.?)\s+'
            r'([A-Z][A-Za-z.\'-]+(?:\s+[A-Z][A-Za-z.\'-]+){1,3})\s+'
            r'(?:selected|joins?|appointed|named|will\s+participate)',
            text,
            re.I,
        )
        if not m:
            m = re.search(
                r'([A-Z][A-Za-z.\'-]+(?:\s+[A-Z][A-Za-z.\'-]+){1,3})\s+'
                r'(?:selected\s+to\s+join|joins?|appointed|named).{0,40}Project\s+Meridian',
                text,
                re.I,
            )
        who = re.sub(r'[^a-z0-9]+', '-', (m.group(1) if m else clean_title(item.get('title',''), item.get('source',''))).lower()).strip('-')
        return hashlib.sha256(f'us-autowar|project-meridian|participant|{who}'.encode()).hexdigest()
    if stage in {'agility_defense_pilot', 'agility_defense_contract'}:
        nums = '|'.join(sorted(set(re.findall(
            r'\$?\s*\d[\d,.]*\s*(?:million|billion|m|bn|robots?|units?|Digit|대|개)?',
            text,
            re.I,
        )))[:6])
        return hashlib.sha256(f'us-autowar|agility-digit|{stage}|{nums}'.encode()).hexdigest()
    if stage == 'autonomy_policy':
        return hashlib.sha256(b'us-autowar|dod-3000.09|policy-update').hexdigest()
    if stage in {'legislation', 'funding', 'formal_standup', 'commander', 'acquisition_authority'}:
        nums = '|'.join(sorted(set(re.findall(
            r'\d[\d,.]*\s*(?:million|billion|억\s*달러|백만\s*달러|명|대|개|%|년|월|일)',
            text,
            re.I,
        )))[:5])
        return hashlib.sha256(f'us-autowar|{stage}|{nums}'.encode()).hexdigest()
    if stage in {'agincourt_contract', 'autowar_contract', 'production'}:
        vendors = []
        for name, pat in [
            ('anduril', r'Anduril|안두릴'), ('spacex', r'SpaceX|스페이스X'),
            ('shield-ai', r'Shield\s*AI|쉴드\s*AI'), ('skydio', r'Skydio|스카이디오'),
            ('aero', r'AeroVironment|에어로바이런먼트'), ('general-atomics', r'General\s*Atomics'),
        ]:
            if re.search(pat, text, re.I):
                vendors.append(name)
        nums = '|'.join(sorted(set(re.findall(
            r'\$?\s*\d[\d,.]*\s*(?:million|billion|m|bn|systems?|units?|drones?|robots?|대|개)?',
            text,
            re.I,
        )))[:6])
        return hashlib.sha256(
            f'us-autowar|{stage}|{",".join(vendors)}|{nums}'.encode()
        ).hexdigest()
    if stage == 'deployment':
        return hashlib.sha256(f'us-autowar|deployment|{text[:220]}'.encode()).hexdigest()
    if stage == 'reverse':
        sig = 'funding' if re.search(r'budget|funding|예산|삭감', text, re.I) else 'schedule-or-approval'
        return hashlib.sha256(f'us-autowar|reverse|{sig}'.encode()).hexdigest()
    return _orig_key(item)


def tag_for(group: str) -> str:
    if group == 'us_autonomous_warfare':
        return '미국자율전쟁'
    return _orig_tag_for(group)


def clean_title(title: str, source: str) -> str:
    text = f"{title} {source}"
    if topic_group(text) != 'us_autonomous_warfare':
        return _orig_clean_title(title, source)
    return {
        'legislation': '미 의회, AUTOWARCOM 창설·권한 법제화 진전',
        'funding': '미 AUTOWARCOM 자율·로봇 전력 예산 확정',
        'formal_standup': '미 AUTOWARCOM 정식 창설·작전능력 진전',
        'commander': '미 AUTOWARCOM 4성 사령관 인선 진전',
        'acquisition_authority': '미 AUTOWARCOM 자율체계 획득·조달권한 확정',
        'agincourt_contract': 'Project Agincourt, 자율체계 시제품·양산계약 발생',
        'autowar_contract': '미 AUTOWARCOM·DAWG 자율체계 실제 조달·수주',
        'production': '미 자율전쟁 드론·로봇 양산 확대',
        'deployment': '미군 자율·로봇 전력 실제 배치 확대',
        'meridian_report': 'Project Meridian 미래전 보고서·권고 공개',
        'meridian_participant_baseline': 'Agility CEO Peggy Johnson, Project Meridian 개인자문 참여 기준선',
        'meridian_participant_change': 'Project Meridian 로봇·AI 자문진 구성 변경',
        'agility_defense_pilot': 'Agility Digit, 미 국방 실증·운용평가 단계 진입',
        'agility_defense_contract': 'Agility Digit, 미 국방 조달·수주 발생',
        'autonomy_policy': '미 국방부 자율무기 정책 개정',
        'reverse': '미 AUTOWARCOM·자율전력 계획 일정·예산 후퇴',
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
