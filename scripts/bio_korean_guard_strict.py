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
    if base.has_japanese(converted) or base.untranslated_hanja(converted) or leftover:
        converted = base.translate_to_korean(converted)
        converted = base.apply_common_replacements(converted)
        leftover = base.general_english_words(converted)

    if base._MARKER_RE.search(converted):
        raise RuntimeError('고유명 보존 표식 복원 실패 — Telegram 발송 차단')
    kana = base.has_japanese(converted)
    hanja = base.untranslated_hanja(converted)
    if kana or hanja or leftover:
        reasons = leftover[:8]
        if kana:
            reasons.append('일본어 가나')
        if hanja:
            reasons.append('번역되지 않은 한자: ' + ''.join(hanja[:8]))
        raise RuntimeError(
            '한국어 송출 검증 실패 — ' + ', '.join(reasons)
        )
    return converted


def ensure_korean_text(text: str) -> str:
    return '\n'.join(strict_translate_line(line) for line in text.splitlines())
