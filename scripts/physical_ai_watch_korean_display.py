#!/usr/bin/env python3
"""Korean display normalization for the physical-AI Telegram watcher.

Raw titles/sources are kept unchanged for deduplication and evidence matching.
Only user-visible Telegram text is normalized to Korean explanatory wording,
while identifiers such as ROBOTIS, NVIDIA, AI Sapiens, AI Worker, Isaac,
GR00T, Jetson, DYNAMIXEL-Q, MoMA, CLOiD and RFM remain identifiable.

For readability, the clickable original-article link is rendered on the same
line as source and timestamp instead of taking a separate line.
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import physical_ai_watch_lg_factory_loop as lg

base = lg.base

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

    # Dates/times and recurring event labels.
    s = re.sub(r'\b9/22\b', '9월 22일', s)
    s = re.sub(r'\b(\d{1,2}):(\d{2})\s*(AM|PM)\b', _time_ko, s, flags=re.I)
    s = re.sub(r'\bHumanoids Summit Seoul\b', '서울 휴머노이드 서밋', s, flags=re.I)
    s = re.sub(r'\bHumanoids Summit\b', '휴머노이드 서밋', s, flags=re.I)
    s = re.sub(r'\bSponsored Technical Workshop\b', '공동 기술 워크숍', s, flags=re.I)
    s = re.sub(r'\bROBOTIS Docs\b', 'ROBOTIS 공식 기술문서', s, flags=re.I)
    s = re.sub(r'\bNVIDIA Developer\b', 'NVIDIA 개발자 공식자료', s, flags=re.I)
    s = re.sub(r'\bLG Global Newsroom\b', 'LG전자 글로벌 뉴스룸', s, flags=re.I)
    s = re.sub(r'\bLG Newsroom\b', 'LG전자 뉴스룸', s, flags=re.I)
    s = re.sub(r'\bLG Electronics\b', 'LG전자', s, flags=re.I)

    # General explanatory terms: Korean first, identifiers stay unchanged.
    s = re.sub(r'라이브\s*데모|live\s*demo', '현장 시연', s, flags=re.I)
    s = re.sub(r'NVIDIA\s+스택', 'NVIDIA 소프트웨어 체계', s, flags=re.I)
    s = re.sub(r'\bsoftware stack\b', '소프트웨어 체계', s, flags=re.I)
    s = re.sub(r'\bsmart\s*factory\b', '스마트팩토리', s, flags=re.I)
    s = re.sub(r'\bData\s*Factory\b', '데이터팩토리', s, flags=re.I)
    s = re.sub(r'\bdata\s*flywheel\b', '데이터 선순환', s, flags=re.I)
    s = re.sub(r'\bRobot\s*Foundation\s*Model\b', '로봇 파운데이션 모델(RFM)', s, flags=re.I)
    s = re.sub(r'\bmass\s*production\b', '양산', s, flags=re.I)
    s = re.sub(r'\binitial\s*production\b', '초도 생산', s, flags=re.I)
    s = re.sub(r'\bqualification\b', '고객 검증', s, flags=re.I)
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

    # Internal fingerprints are useful for dedup, not for users.
    s = re.sub(r'\s*\[[0-9a-f]{6,12}\]\s*$', '', s, flags=re.I)

    # Cosmetic spacing after transformations.
    s = re.sub(r'\s{2,}', ' ', s).strip()
    return s


def esc_text_ko(value: str) -> str:
    return _orig_esc_text(_display_ko(value))


def _inline_original_link(text: str) -> str:
    """Move each standalone HTML '원문' link onto that article's 출처 line."""
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
            # Keep source name + timestamp visible and make only '원문' clickable.
            if '<b>원문</b>' not in out[source_idx]:
                out[source_idx] = out[source_idx].rstrip() + ' · ' + stripped
            continue

        out.append(line)
        if stripped == '──────────────────':
            source_idx = None

    return '\n'.join(out).strip()


# Rendering-only hook. Raw item title/source/key remain untouched, so this does
# not create duplicate alerts when display wording changes.
base.esc_text = esc_text_ko

if __name__ == '__main__':
    base.main()
    if base.ALERT_PATH.exists():
        rendered = base.ALERT_PATH.read_text(encoding='utf-8')
        base.ALERT_PATH.write_text(_inline_original_link(rendered), encoding='utf-8')