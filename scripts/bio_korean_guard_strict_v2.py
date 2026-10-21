from __future__ import annotations

import re

import bio_korean_guard_strict as base


DISPLAY_REPLACEMENTS = (
    (r'(?<!미국 식품의약국\()\bFDA\b', '미국 식품의약국(FDA)'),
    (r'(?<!유럽의약품청\()\bEMA\b', '유럽의약품청(EMA)'),
    (r'(?<!허가 신청\()\bsBLA\b', '추가 생물학적 제제 허가 신청(sBLA)'),
    (r'(?<!결정 예정일\()\bPDUFA\b', '허가 결정 예정일(PDUFA)'),
    (r'(?<!공동심사 프로그램\()\bProject Orbis\b', '국제 공동심사 프로그램(Project Orbis)'),
    (r'\bNational Priority Voucher(?: program)?\b', '국가 우선 바우처 프로그램'),
    (r'\bCommissioner[’\']s National Priority Voucher(?: program)?\b', '미국 식품의약국 국가 우선 바우처 프로그램'),
)


def korean_first_regulatory_terms(text: str) -> str:
    out = text
    for pattern, replacement in DISPLAY_REPLACEMENTS:
        out = re.sub(pattern, replacement, out, flags=re.I)
    return out


def strict_translate_line(line: str) -> str:
    stripped = line.strip()
    # 규제 약어의 한국어 우선표기는 문장에만 적용한다.
    # - 원문: 공식 주소는 EMA 등 식별자가 도메인에 들어가므로 절대 재작성하지 않는다.
    if stripped.startswith("- 원문:") or "원문 뉴스보기" in stripped or re.fullmatch(r"https?://\\S+", stripped):
        return line
    return korean_first_regulatory_terms(base.strict_translate_line(line))


def ensure_korean_text(text: str) -> str:
    return '\n'.join(strict_translate_line(line) for line in text.splitlines())
