#!/usr/bin/env python3
"""Korean display normalization for the physical-AI Telegram watcher.

Raw titles/sources are kept unchanged for deduplication and evidence matching.
Only user-visible Telegram text is normalized to Korean wording. Stable company,
brand and product names are rendered in their common Korean forms when that does
not break identification; technical model codes such as XL330, GR00T, PPAP and
ISIR remain unchanged.

For readability, the clickable original-article link is rendered on the same
line as source and timestamp instead of taking a separate line.
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import physical_ai_watch_policy_parts_2027 as pol

base = pol.base

_orig_esc_text = base.esc_text


def _time_ko(match: re.Match) -> str:
    hour = int(match.group(1))
    minute = int(match.group(2))
    ampm = match.group(3).upper()
    if ampm == 'AM':
        if hour == 12:
            prefix, khour = '오전', 0
        else:
            prefix, khour = '오전', hour
    else:
        if hour == 12:
            prefix, khour = '낮', 12
        else:
            prefix, khour = '오후', hour
    if minute:
        return f'{prefix} {khour}시 {minute}분'
    return f'{prefix} {khour}시'


def _display_ko(value: str) -> str:
    s = value or ''

    s = re.sub(r'\b9/22\b', '9월 22일', s)
    s = re.sub(r'\b(\d{1,2}):(\d{2})\s*(AM|PM)\b', _time_ko, s, flags=re.I)

    # User-visible proper names: use stable Korean forms first. Keep model codes
    # and standards unchanged where translating them would make source lookup harder.
    s = re.sub(
        r'Matthieu\s+Lapeyre\s*\(Pollen\s+Robotics/X\)',
        '마티외 라페르(폴렌 로보틱스 설립자·엑스)',
        s,
        flags=re.I,
    )
    s = re.sub(r'\bPollen\s+Robotics\b', '폴렌 로보틱스', s, flags=re.I)
    s = re.sub(r'\bMicroduck\b', '마이크로덕', s, flags=re.I)
    s = re.sub(r'\bReachy\s+Mini\b', '리치 미니', s, flags=re.I)
    s = re.sub(r'\bPollen\b', '폴렌 로보틱스', s, flags=re.I)
    s = re.sub(r'창업자\s+X\s+1차', '설립자 엑스(X) 1차', s, flags=re.I)

    s = re.sub(r'\bHumanoids Summit Seoul\b', '서울 휴머노이드 서밋', s, flags=re.I)
    s = re.sub(r'\bHumanoids Summit\b', '휴머노이드 서밋', s, flags=re.I)
    s = re.sub(r'\bSponsored Technical Workshop\b', '공동 기술 워크숍', s, flags=re.I)
    s = re.sub(r'\bR&D\s*Tech\s*Day\b', 'R&D 테크데이', s, flags=re.I)
    s = re.sub(r'\bTech\s*Day\b', '테크데이', s, flags=re.I)
    s = re.sub(r'\bROBOTIS Docs\b', '로보티즈 공식 기술문서', s, flags=re.I)
    s = re.sub(r'\bROBOTIS\b', '로보티즈', s, flags=re.I)
    s = re.sub(r'\bDYNAMIXEL\b', '다이나믹셀', s, flags=re.I)
    s = re.sub(r'\bNVIDIA Developer\b', '엔비디아 개발자 공식자료', s, flags=re.I)
    s = re.sub(r'\bNVIDIA\b', '엔비디아', s, flags=re.I)
    s = re.sub(r'\bXPENG\b', '샤오펑', s, flags=re.I)
    s = re.sub(r'\bWONIK Robotics\b', '원익로보틱스', s, flags=re.I)
    s = re.sub(r'\bWONIK Holdings\b', '원익홀딩스', s, flags=re.I)
    s = re.sub(r'\bAtlas\b', '아틀라스', s, flags=re.I)
    s = re.sub(r'\bLG Global Newsroom\b', 'LG전자 글로벌 뉴스룸', s, flags=re.I)
    s = re.sub(r'\bLG Newsroom\b', 'LG전자 뉴스룸', s, flags=re.I)
    s = re.sub(r'\bLG Electronics\b', 'LG전자', s, flags=re.I)
    s = re.sub(r'\bHyundai Mobis Newsroom\b', '현대모비스 뉴스룸', s, flags=re.I)
    s = re.sub(r'\bMOBIS Newsroom\b', '현대모비스 뉴스룸', s, flags=re.I)
    s = re.sub(r'\bHyundai Mobis\b', '현대모비스', s, flags=re.I)
    s = re.sub(r'\bHyundai Motor Group\b', '현대자동차그룹', s, flags=re.I)
    s = re.sub(r'\bHyundai Motor\b', '현대자동차', s, flags=re.I)
    s = re.sub(r'\bBoston Dynamics\b', '보스턴다이내믹스', s, flags=re.I)
    s = re.sub(r'\bNeuromeka\b', '뉴로메카', s, flags=re.I)
    s = re.sub(r'\bNewsis\b', '뉴시스', s, flags=re.I)

    s = re.sub(r'라이브\s*데모|live\s*demo', '현장 시연', s, flags=re.I)
    s = re.sub(r'엔비디아\s+스택', '엔비디아 소프트웨어 체계', s, flags=re.I)
    s = re.sub(r'\bsoftware stack\b', '소프트웨어 체계', s, flags=re.I)
    s = re.sub(r'\bsmart\s*factory\b', '스마트팩토리', s, flags=re.I)
    s = re.sub(r'\brobot\s*foundry\b', '로봇 파운드리', s, flags=re.I)
    s = re.sub(r'\bdata\s*foundry\b', '데이터 파운드리', s, flags=re.I)
    s = re.sub(r'\brobot\s*data\s*factory\b', '로봇 데이터 팩토리', s, flags=re.I)
    s = re.sub(r'\bData\s*Factory\b', '데이터팩토리', s, flags=re.I)
    s = re.sub(r'\bdata\s*flywheel\b', '데이터 선순환', s, flags=re.I)
    s = re.sub(r'\bcontract\s*manufacturing\b', '위탁생산', s, flags=re.I)
    s = re.sub(r'\bperformance\s*validation\b', '성능 검증', s, flags=re.I)
    s = re.sub(r'\brobot\s*data\s*collection\b', '로봇 데이터 수집', s, flags=re.I)
    s = re.sub(r'\bexcess\s*demand\b', '초과수요', s, flags=re.I)
    s = re.sub(r'\bbacklog\b', '수주잔고', s, flags=re.I)
    s = re.sub(r'\bmonthly\s*output\b', '월 생산량', s, flags=re.I)
    s = re.sub(r'\blead\s*time\b', '납기', s, flags=re.I)
    s = re.sub(r'\bRobot\s*Foundation\s*Model\b', '로봇 파운데이션 모델(RFM)', s, flags=re.I)
    s = re.sub(r'\bmass\s*production\b', '양산', s, flags=re.I)
    s = re.sub(r'\binitial\s*production\b', '초도 생산', s, flags=re.I)
    s = re.sub(r'\bproduction\s*line\b', '양산라인', s, flags=re.I)
    s = re.sub(r'\bproduction\s*capacity\b', '생산능력', s, flags=re.I)
    s = re.sub(r'\bqualification\b', '고객 검증', s, flags=re.I)
    s = re.sub(r'\breliability\b', '신뢰성', s, flags=re.I)
    s = re.sub(r'\bvalidation\b', '검증', s, flags=re.I)
    s = re.sub(r'\byield\b', '수율', s, flags=re.I)
    s = re.sub(r'\bactuator(?:s)?\b', '액추에이터', s, flags=re.I)
    s = re.sub(r'\bsensor(?:s)?\b', '센서', s, flags=re.I)
    s = re.sub(r'\bgripper(?:s)?\b', '그리퍼', s, flags=re.I)
    s = re.sub(r'\bcontroller(?:s)?\b', '제어기', s, flags=re.I)
    s = re.sub(r'\bbattery\s*pack(?:s)?\b', '배터리팩', s, flags=re.I)
    s = re.sub(r'\bgovernment\s*budget\s*proposal\b', '정부 예산안', s, flags=re.I)
    s = re.sub(r'\bfield\s*validation\b', '현장 실증', s, flags=re.I)
    s = re.sub(r'\buptime\b', '가동률', s, flags=re.I)
    s = re.sub(r'\bhuman\s*intervention\b', '사람 개입', s, flags=re.I)
    s = re.sub(r'기술통합', '기술 통합', s)
    s = re.sub(r'레퍼런스\s*플랫폼', '참조 플랫폼', s)
    s = re.sub(r'레퍼런스\s*등재', '참조 사례 등재', s)
    s = re.sub(r'파트너십', '협력관계', s)
    s = re.sub(r'온디바이스\s*연산', '기기 내 연산', s)
    s = re.sub(r'메인스테이지', '주요 무대', s)
    s = re.sub(r'\bCEO\b', '대표이사', s)
    s = re.sub(r'\bdeployment\b', '현장 배치', s, flags=re.I)
    s = re.sub(r'\bintegration\b', '기술 통합', s, flags=re.I)
    s = re.sub(r'\bjoint development\b', '공동개발', s, flags=re.I)
    s = re.sub(r'\breference platform\b', '참조 플랫폼', s, flags=re.I)
    s = re.sub(r'\bcertification\b', '인증', s, flags=re.I)

    s = re.sub(r'\s*\[[0-9a-f]{6,12}\]\s*$', '', s, flags=re.I)
    s = re.sub(r'\s{2,}', ' ', s).strip()
    return s


def esc_text_ko(value: str) -> str:
    return _orig_esc_text(_display_ko(value))


def _inline_original_link(text: str) -> str:
    if not text:
        return text
    lines = text.splitlines()
    out: list[str] = []
    source_idx: int | None = None
    link_re = re.compile(r'^<a href="[^"]+"><b>원문</b></a>$')
    for line in lines:
        stripped = line.strip()
        if stripped.startswith('<b>출처</b>'):
            source_idx = len(out)
            out.append(line)
            continue
        if link_re.fullmatch(stripped) and source_idx is not None:
            if '<b>원문</b>' not in out[source_idx]:
                out[source_idx] = out[source_idx].rstrip() + ' · ' + stripped
            continue
        out.append(line)
        if stripped == '──────────────────':
            source_idx = None
    return '\n'.join(out).strip()


base.esc_text = esc_text_ko

if __name__ == '__main__':
    base.main()
    if base.ALERT_PATH.exists():
        rendered = base.ALERT_PATH.read_text(encoding='utf-8')
        base.ALERT_PATH.write_text(_inline_original_link(rendered), encoding='utf-8')