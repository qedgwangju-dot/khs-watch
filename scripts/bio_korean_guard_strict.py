from __future__ import annotations

import re

import bio_korean_guard as base


def strict_translate_line(line: str) -> str:
    stripped = line.strip()
    if not stripped:
        return line
    if stripped.startswith('- 원문:') or '원문 뉴스보기' in stripped or re.fullmatch(r'https?://\S+', stripped):
        return line

    converted = base.translate_line(line)
    leftover = base.general_english_words(converted)
    if base.has_japanese(converted) or leftover:
        converted = base.translate_to_korean(converted)
        converted = base.apply_common_replacements(converted)
        leftover = base.general_english_words(converted)

    if base.has_japanese(converted) or leftover:
        raise RuntimeError(
            '한국어 송출 검증 실패 — 일반 영어/일본어 설명어가 남아 있어 발송 차단: '
            + ', '.join(leftover[:8])
        )
    return converted


def ensure_korean_text(text: str) -> str:
    return '\n'.join(strict_translate_line(line) for line in text.splitlines())
