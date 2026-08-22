#!/usr/bin/env python3
"""Ensure user-facing Treasury Telegram alert labels are Korean.

The watcher preserves the original source URL/metadata internally, but the
Telegram body must not expose an untranslated English press-release title.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ALERT = ROOT / "out" / "treasury_buyback_policy_alert.html"
DETAIL = ROOT / "out" / "treasury_buyback_policy_detail.json"

EXACT_TITLES = {
    "Treasury Announces Increased Sizes of Nominal Long-End Liquidity Support Buybacks Beginning September 9":
        "미 재무부, 장기 명목국채 유동성 지원 바이백 규모 확대 — 9월 9일 시행",
}


def translate_title(title: str) -> str:
    title = re.sub(r"\s+", " ", title).strip()
    if title in EXACT_TITLES:
        return EXACT_TITLES[title]

    low = title.lower()
    if "buyback" in low and ("long-end" in low or "long end" in low):
        if "increase" in low or "increased" in low or "expand" in low:
            return "미 재무부, 장기 명목국채 유동성 지원 바이백 규모 확대"
        if "decrease" in low or "reduce" in low:
            return "미 재무부, 장기 명목국채 유동성 지원 바이백 규모 축소"
        return "미 재무부, 장기 명목국채 유동성 지원 바이백 정책 변경"
    if "quarterly refunding" in low or "refunding" in low:
        return "미 재무부 분기 차환·자금조달 계획 발표"
    if "treasury" in low:
        return "미 재무부 공식 발표"
    return title


def main() -> int:
    if not ALERT.exists():
        return 0

    text = ALERT.read_text(encoding="utf-8")
    original_title = None
    if DETAIL.exists():
        try:
            detail = json.loads(DETAIL.read_text(encoding="utf-8"))
            source = detail.get("source") or {}
            original_title = source.get("title")
        except Exception:
            original_title = None

    if original_title:
        translated = translate_title(str(original_title))
        text = text.replace(
            f"• 공식 출처: <b>{original_title}</b>",
            f"• 공식 출처: <b>{translated}</b>",
        )

    # Fallback for any remaining English Treasury headline in the display line.
    pattern = re.compile(r"(• 공식 출처: <b>)([^<]+)(</b>)")
    def repl(match: re.Match[str]) -> str:
        shown = match.group(2).strip()
        if re.search(r"[A-Za-z]{4,}", shown):
            shown = translate_title(shown)
            if re.search(r"[A-Za-z]{4,}", shown):
                shown = "미 재무부 공식 발표"
        return match.group(1) + shown + match.group(3)

    text = pattern.sub(repl, text)

    # User-facing guard: do not send raw Treasury headline boilerplate in English.
    if re.search(r"• 공식 출처: <b>[^<]*\b(Treasury|Buyback|Refunding)\b", text, re.I):
        raise RuntimeError("공식 출처 제목의 한국어 변환이 완료되지 않았습니다.")

    ALERT.write_text(text, encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
