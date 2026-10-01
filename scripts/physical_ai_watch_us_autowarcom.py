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
    'site:defense.gov ("Autonomous Warfare Command" OR AUTOWARCOM OR "Project Agincourt" OR "Project Meridian")',
    'site:congress.gov ("Autonomous Warfare Command" OR "Robotic and Autonomous Systems Combatant Command")',
    'site:diu.mil ("Project Agincourt" OR autonomy) (contract OR prototype OR award OR production)',
]:
    if q not in base.QUERIES:
        base.QUERIES.append(q)

base.OFFICIAL_OR_PRIMARY.update({
    'U.S. Department of Defense', 'Department of Defense', 'Defense.gov',
    'Defense Innovation Unit', 'DIU', 'Congress.gov', 'U.S. Congress',
    'U.S. Senate Armed Services Committee', 'Senate Armed Services Committee',
    'U.S. House Armed Services Committee', 'House Armed Services Committee',
})
base.TRUSTED.update({
    'Reuters', 'Breaking Defense', 'Defense News', 'Defense One', 'The War Zone',
    'Bloomberg', 'Associated Press', 'AP',
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
    r'\b\d[\d,.]*\s*(?:systems?|units?|drones?|robots?|aircraft|vehicles?|million|billion|%|대|개|억\s*달러|백만\s*달러)\b|'
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
AUTONOMY_POLICY = re.compile(
    r'Directive\s+3000\.09|DoD\s+Directive\s+3000\.09|'
    r'autonomy\s+in\s+weapon\s+systems|자율\s*무기\s*체계|자율무기',
    re.I,
)
POLICY_UPDATE = re.compile(
    r'updated|revised|issued|rescinded|effective|개정|업데이트|발령|시행|폐지',
    re.I,
)
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
        or (MERIDIAN.search(text) and (MUSK_GROUP.search(text) or DEFENSE_CTX.search(text)))
        or (AUTONOMY_POLICY.search(text) and DEFENSE_CTX.search(text))
    )


def _stage(text: str) -> str:
    if REVERSE.search(text):
        return 'reverse'
    if MERIDIAN_REPORT.search(text):
        return 'meridian_report'
    if AUTONOMY_POLICY.search(text) and POLICY_UPDATE.search(text):
        return 'autonomy_policy'
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
    if AGINCOURT.search(text) and CONTRACT.search(text) and QUANTITY.search(text):
        return 'agincourt_contract'
    if (AUTOWAR.search(text) or AGINCOURT.search(text)) and DEPLOYMENT.search(text) and QUANTITY.search(text):
        return 'deployment'
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
    if stage in {'baseline', 'monitor'}:
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
        'deployment': 16,
        'meridian_report': 12,
        'autonomy_policy': 11,
        'reverse': 15,
    }.get(stage, 0)
    return s


def category(text: str, group: str) -> str:
    if group != 'us_autonomous_warfare':
        return _orig_category(text, group)
    return {
        'baseline': '미국 자율전쟁 · AUTOWARCOM·Project Meridian 기준선',
        'legislation': '미국 자율전쟁 · AUTOWARCOM 법제화·승인',
        'funding': '미국 자율전쟁 · AUTOWARCOM 예산·재원 확정',
        'formal_standup': '미국 자율전쟁 · AUTOWARCOM 정식 창설·작전능력',
        'commander': '미국 자율전쟁 · AUTOWARCOM 사령관 지명·인준',
        'acquisition_authority': '미국 자율전쟁 · AUTOWARCOM 획득·조달권한',
        'agincourt_contract': '미국 자율전쟁 · Project Agincourt 시제품·양산계약',
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
        '자율·로봇 전력 실제 배치': '조달된 자율체계가 훈련·작전부대에 실제 전력화되는 단계입니다. 배치 수량, 가동률, 손실률, 임무성공률과 재발주를 추적합니다.',
        'Project Meridian 보고서·권고': '머스크·럭키·깅리치 등이 참여한 미래전 연구가 구체적인 능력격차와 조달·조직 권고로 바뀌는 단계입니다. 자문보고서와 실제 국방부 채택·예산을 분리합니다.',
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
    if raw == 'AUTOWARCOM 법제화·승인':
        return '국방부의 창설 의지만으로 전투사령부의 획득권한이 자동 생기지는 않습니다. 의회 법안·최종 법률·예산·시행을 단계별로 확인합니다.'
    if raw == 'AUTOWARCOM 획득·조달권한':
        return '권한 부여와 실제 생산계약은 다릅니다. 공급업체, 계약금액, 수량, 납기와 전력화 시험을 별도 확인합니다.'
    if raw == 'Project Agincourt 시제품·양산계약':
        return '시제품 계약은 양산 매출과 다릅니다. 시험 실패, 통신·전자전 내성, 자율성 신뢰성, 원가와 대량생산 수율이 후속 병목입니다.'
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
    if src in base.OFFICIAL_OR_PRIMARY:
        return '미 국방부·의회·DIU 공식자료 · 발표/법제화/예산/계약/배치 단계 분리'
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
    if stage == 'autonomy_policy':
        return hashlib.sha256(b'us-autowar|dod-3000.09|policy-update').hexdigest()
    if stage in {'legislation', 'funding', 'formal_standup', 'commander', 'acquisition_authority'}:
        nums = '|'.join(sorted(set(re.findall(
            r'\d[\d,.]*\s*(?:million|billion|억\s*달러|백만\s*달러|명|대|개|%|년|월|일)',
            text,
            re.I,
        )))[:5])
        return hashlib.sha256(f'us-autowar|{stage}|{nums}'.encode()).hexdigest()
    if stage == 'agincourt_contract':
        vendors = []
        for name, pat in [
            ('anduril', r'Anduril|안두릴'), ('spacex', r'SpaceX|스페이스X'),
            ('shield-ai', r'Shield\s*AI|쉴드\s*AI'), ('skydio', r'Skydio|스카이디오'),
            ('aero', r'AeroVironment|에어로바이런먼트'), ('general-atomics', r'General\s*Atomics'),
        ]:
            if re.search(pat, text, re.I):
                vendors.append(name)
        return hashlib.sha256(
            f'us-autowar|agincourt-contract|{",".join(vendors)}|{text[:180]}'.encode()
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
        'deployment': '미군 자율·로봇 전력 실제 배치 확대',
        'meridian_report': 'Project Meridian 미래전 보고서·권고 공개',
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
