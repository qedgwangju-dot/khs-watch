#!/usr/bin/env python3
"""Add an explicit ROBOTIS × NVIDIA summit / technical-integration lane.

Tracks:
- Sep 22 Humanoids Summit Seoul NVIDIA × ROBOTIS workshop
- AI Sapiens / AI Worker live demos
- Isaac GR00T / Isaac Lab / Jetson integration upgrades
- Any move from technical compatibility to reference-platform, joint development,
  certification, commercial partnership, customer deployment, or measured task performance.

The official summit agenda is polled directly so the event does not depend on
Google News indexing. News/RSS still covers follow-up announcements and demos.
"""
from __future__ import annotations

import datetime as dt
import hashlib
import re
import sys
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import physical_ai_watch_grid as grid

base = grid.base
ext = grid.ext

AGENDA_URL = "https://apple-blackbird-dttf.squarespace.com/seoul-1"
ROBOTIS_TECH_URL = "https://docs.robotis.com/docs/systems/aisapiens/resources/technical_story/building_humanoid_skills/"
DIRECT_SENTINEL = "DIRECT_ROBOTIS_NVIDIA_SUMMIT_2026"

base.QUERIES.extend([
    DIRECT_SENTINEL,
    '(ROBOTIS OR 로보티즈) (NVIDIA OR 엔비디아) (Humanoids Summit OR 휴머노이드 서밋 OR COEX OR 코엑스 OR workshop OR 워크숍)',
    '(ROBOTIS OR 로보티즈) (NVIDIA OR 엔비디아) (AI Sapiens OR AI Worker) (demo OR 데모 OR 시연 OR GR00T OR Isaac OR Jetson)',
    '(ROBOTIS OR 로보티즈) (GR00T OR Isaac Lab OR Isaac Sim OR Jetson Orin OR Jetson Thor) (AI Sapiens OR AI Worker OR humanoid OR 휴머노이드)',
    '(ROBOTIS OR 로보티즈) (NVIDIA OR 엔비디아) (reference platform OR 레퍼런스 플랫폼 OR joint development OR 공동개발 OR certification OR 인증 OR partnership OR 협력 OR deployment OR 배치)',
])

base.OFFICIAL_OR_PRIMARY.update({
    'Humanoids Summit', 'ROBOTIS Docs', 'NVIDIA', 'NVIDIA Developer',
})

_orig_query_news = base.query_news
_orig_score = base.score
_orig_category = base.category
_orig_meaning = base.meaning
_orig_risk = base.risk
_orig_verification = base.verification
_orig_same_event = ext._same_event


def _fetch_text(url: str) -> str:
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 khs-watch/3.0"})
    with urllib.request.urlopen(req, timeout=25) as r:
        return r.read().decode("utf-8", errors="ignore")


def _direct_official_items() -> list[dict]:
    items: list[dict] = []
    now_iso = base.NOW.isoformat()
    try:
        agenda = _fetch_text(AGENDA_URL)
        # HTML is enough for robust keyword checks; exact page structure may change.
        if re.search(r'NVIDIA\s*[×xX&]\s*ROBOTIS|NVIDIA.*ROBOTIS.*Sponsored Technical Workshop', agenda, re.I | re.S):
            time_match = re.search(r'(\d{1,2}:\d{2}\s*(?:AM|PM)).{0,180}NVIDIA\s*[×xX&]\s*ROBOTIS', agenda, re.I | re.S)
            time_txt = time_match.group(1).upper() if time_match else '12:00 PM'
            title = f"ROBOTIS–NVIDIA, 9/22 {time_txt} Humanoids Summit Seoul 공동 기술 워크숍"
            details = []
            if re.search(r'Qi\s+Wang', agenda, re.I): details.append('NVIDIA Qi Wang')
            if re.search(r'Byoungsoo\s+Kim|Byoungsoo Kim', agenda, re.I): details.append('ROBOTIS 김병수 CEO 메인스테이지 발표')
            desc = (
                f"Humanoids Summit Seoul 공식 일정에서 9월 22일 {time_txt} NVIDIA × ROBOTIS Sponsored Technical Workshop 확인. "
                + (', '.join(details) + '. ' if details else '')
                + "ROBOTIS–NVIDIA 공동 세션의 실제 기술통합·데모·후속 파트너십 여부를 추적."
            )
            items.append({
                'title': title,
                'link': AGENDA_URL,
                'description': desc,
                'published': now_iso,
                'source': 'Humanoids Summit',
            })
    except Exception:
        pass

    try:
        tech = _fetch_text(ROBOTIS_TECH_URL)
        if re.search(r'NVIDIA\s+software', tech, re.I) and re.search(r'AI\s+Sapiens', tech, re.I) and re.search(r'AI\s+Worker', tech, re.I):
            stack = []
            for token in ['Isaac Lab', 'GR00T N1.7', 'Jetson Orin NX', 'Jetson AGX Orin']:
                if re.search(re.escape(token), tech, re.I):
                    stack.append(token)
            # This official technical story is a supporting evidence item. It is
            # deliberately lower-signal than the summit announcement unless the
            # stack changes in a future revision.
            sig = '|'.join(stack) or 'NVIDIA-stack'
            digest = hashlib.sha1(sig.encode()).hexdigest()[:7]
            items.append({
                'title': f"ROBOTIS, NVIDIA 스택 기반 AI Sapiens·AI Worker 기술통합 확인 [{digest}]",
                'link': ROBOTIS_TECH_URL,
                'description': "ROBOTIS 공식 기술자료: " + ', '.join(stack) + ". 공동 워크숍 전후로 스택 버전·모델·실제 작업 성능 변화 추적.",
                'published': now_iso,
                'source': 'ROBOTIS Docs',
            })
    except Exception:
        pass
    return items


def query_news(q: str) -> list[dict]:
    if q == DIRECT_SENTINEL:
        return _direct_official_items()
    return _orig_query_news(q)


def _is_robotis_nvidia(text: str) -> bool:
    return bool(
        re.search(r'ROBOTIS|로보티즈', text, re.I)
        and re.search(r'NVIDIA|엔비디아|GR00T|Isaac\s+(?:Lab|Sim)|Jetson', text, re.I)
        and re.search(r'Humanoids Summit|휴머노이드 서밋|workshop|워크숍|AI\s+Sapiens|AI\s+Worker|demo|데모|시연|기술통합|integration', text, re.I)
    )


def score(item: dict) -> int:
    text = f"{item.get('title','')} {item.get('description','')} {item.get('source','')}"
    if not _is_robotis_nvidia(text):
        return _orig_score(item)
    s = 18
    if item.get('source') in {'Humanoids Summit', 'ROBOTIS Docs', 'NVIDIA', 'NVIDIA Developer'}:
        s += 6
    if re.search(r'9/22|September\s+22|12:00|workshop|워크숍', text, re.I):
        s += 4
    if re.search(r'AI\s+Sapiens|AI\s+Worker', text, re.I):
        s += 3
    if re.search(r'GR00T|Isaac\s+Lab|Isaac\s+Sim|Jetson', text, re.I):
        s += 4
    if re.search(r'live\s*demo|라이브\s*데모|시연|success rate|성공률|latency|지연|task|작업', text, re.I):
        s += 5
    if re.search(r'joint development|공동개발|reference platform|레퍼런스 플랫폼|certification|인증|contract|계약|deployment|배치', text, re.I):
        s += 6
    return s


def _subcat(text: str) -> str:
    if re.search(r'joint development|공동개발|reference platform|레퍼런스 플랫폼|certification|인증|contract|계약|deployment|배치', text, re.I):
        return 'NVIDIA 파트너십·상용화 전환'
    if re.search(r'live\s*demo|라이브\s*데모|시연|success rate|성공률|latency|지연|task|작업', text, re.I):
        return 'AI Sapiens·AI Worker 라이브 데모'
    return 'NVIDIA 공동 워크숍·기술통합'


def category(text: str, group: str) -> str:
    if group == 'robotis' and _is_robotis_nvidia(text):
        return f"로보티즈 · {_subcat(text)}"
    return _orig_category(text, group)


def meaning(cat: str) -> str:
    raw = cat.split(' · ', 1)[-1]
    if raw == 'NVIDIA 공동 워크숍·기술통합':
        return 'ROBOTIS가 NVIDIA Isaac·GR00T·Jetson 스택을 단순 호환이 아니라 공동 기술 세션과 실제 휴머노이드 구현으로 연결하는 신호입니다. 워크숍 이후 공식 레퍼런스·공동개발·고객 배치로 확대되는지가 재평가 포인트입니다.'
    if raw == 'AI Sapiens·AI Worker 라이브 데모':
        return 'AI Sapiens와 AI Worker가 NVIDIA 스택으로 실제 보행·조작 작업을 수행하는지 확인하는 현장 검증 신호입니다. 작업 성공률·지연시간·반복 안정성·온디바이스 연산 구성이 공개되면 기술 기대가 양산·고객 검증으로 한 단계 올라갑니다.'
    if raw == 'NVIDIA 파트너십·상용화 전환':
        return '공동 워크숍이 공식 레퍼런스 플랫폼·공동개발·인증·상업 배치로 전환되는 단계입니다. 이 경우 DYNAMIXEL-Q와 ROBOTIS 플랫폼의 외부 개발자·OEM 채택 경로가 강해질 수 있습니다.'
    return _orig_meaning(cat)


def risk(cat: str) -> str:
    raw = cat.split(' · ', 1)[-1]
    if raw == 'NVIDIA 공동 워크숍·기술통합':
        return '공동 행사와 NVIDIA 소프트웨어 사용은 공급계약·독점 파트너십을 뜻하지 않습니다. NVIDIA 공식 파트너/레퍼런스 등재, 공동개발 범위, 고객 실명과 상용 계약을 별도로 확인해야 합니다.'
    if raw == 'AI Sapiens·AI Worker 라이브 데모':
        return '무대 데모 1회 성공과 산업현장 반복 가동은 다릅니다. 작업 성공률, 연속 가동시간, 실패 복구, 안전성, 실제 고객 현장 재현 여부가 확인되지 않으면 기술 시연 단계에 머물 수 있습니다.'
    if raw == 'NVIDIA 파트너십·상용화 전환':
        return '파트너십 발표가 매출로 바로 이어지지는 않습니다. 외부 OEM 채택·DYNAMIXEL-Q 물량·Jetson/GR00T 기반 고객 프로젝트와 매출 인식 시점을 확인해야 합니다.'
    return _orig_risk(cat)


def verification(item: dict, group: str, text: str) -> str:
    if group == 'robotis' and _is_robotis_nvidia(text):
        src = item.get('source') or ''
        if src == 'Humanoids Summit':
            return 'Humanoids Summit 공식 일정'
        if src == 'ROBOTIS Docs':
            return 'ROBOTIS 공식 기술자료'
        if src in {'NVIDIA', 'NVIDIA Developer'}:
            return 'NVIDIA 공식자료'
        return '보도자료 · Humanoids Summit/ROBOTIS/NVIDIA 공식자료 교차확인'
    return _orig_verification(item, group, text)


def _same_event(a: dict, b: dict) -> bool:
    if _orig_same_event(a, b):
        return True
    if a.get('group') != 'robotis' or b.get('group') != 'robotis':
        return False
    ta = f"{a.get('title','')} {a.get('description','')}"
    tb = f"{b.get('title','')} {b.get('description','')}"
    summit = r'Humanoids Summit|휴머노이드 서밋|9/22|September\s+22'
    nv = r'NVIDIA|엔비디아|GR00T|Isaac'
    if re.search(summit, ta, re.I) and re.search(summit, tb, re.I) and re.search(nv, ta, re.I) and re.search(nv, tb, re.I):
        return True
    return False


base.query_news = query_news
base.score = score
base.category = category
base.meaning = meaning
base.risk = risk
base.verification = verification
ext._same_event = _same_event

if __name__ == '__main__':
    base.main()
