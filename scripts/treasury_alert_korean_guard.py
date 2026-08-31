#!/usr/bin/env python3
"""Ensure user-facing Treasury Telegram alert labels are Korean and append the current Bessent policy-boundary test.

The official watcher still owns policy detection. This guard only upgrades the
user-facing interpretation so market outcome and stated Treasury purpose are
kept separate.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ALERT = ROOT / "out" / "treasury_buyback_policy_alert.html"
DETAIL = ROOT / "out" / "treasury_buyback_policy_detail.json"
TITLE = ROOT / "out" / "treasury_buyback_policy_title.txt"

BESSENT_REUTERS = "https://www.reuters.com/business/bessent-pushes-back-fears-over-us-debt-market-strains-2026-08-31/"
TREASURY_RELEASE = "https://home.treasury.gov/news/press-releases/sb0607"
BUYBACK_FAQ = "https://www.treasurydirect.gov/help-center/faqs/buyback-faqs/"
UPGRADE_MARKER = "<b>정책 목적·경계선</b>"

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


def upgrade_block() -> str:
    return "\n".join([
        "",
        "<b>정책 목적·경계선</b>",
        "• Bessent는 Reuters 인터뷰에서 자신이 시장의 균형가격을 바꿀 수 있다고 보지 않으며, 재무부 역할은 움직임의 속도를 늦춰 시장이 무질서해지는 것을 막는 것이라고 설명했습니다.",
        "• 따라서 현재 공식선은 <b>특정 금리·가격 통제</b>가 아니라 <b>유동성·변동성 완화</b>입니다.",
        "• 앞으로 시장 기능이 정상인데도 특정 금리 수준에 맞춰 바이백·발행구조를 반복 조정하면 ‘유동성 지원 → 사실상 금리관리’로 정책선 이탈 경보를 올립니다.",
        "",
        "<b>Bessent 금리상승 원인설 검증</b>",
        "• Bessent는 최근 장기금리 상승의 상당 부분을 이란발 에너지 가격·인플레이션 압력과 견조한 성장으로 설명했습니다.",
        "• 유가↓ + 기대인플레이션↓ + 10년물↓ → 설명 지지",
        "• 유가↓ + 기대인플레이션↓인데 10년물 고착·상승 → 재정·국채공급·기간 프리미엄 영향이 더 강한 것으로 판정",
        "• 유가↑ + 기대인플레이션↑ + 10년물↑ → 에너지·인플레이션 설명과 부합",
        "",
        "<b>실행 확인</b>",
        "• 정책 변경 효력은 9월 9일, Bessent가 밝힌 확대 운영 시작은 9월 10일입니다.",
        "• 첫 확대 운영에서 실제 매입액·총 제시액·상한 소진율을 확인하고, 이후 +1일·+3일·+5일 10년·30년 명목금리와 실질금리 지속성을 봅니다.",
        "• CTA 숏 스퀴즈가 발생해도 그것은 시장 결과로 분리하며, Bessent의 공식 정책목표로 단정하지 않습니다.",
        "",
        f'<a href="{BESSENT_REUTERS}">Bessent Reuters 인터뷰</a> · <a href="{TREASURY_RELEASE}">미 재무부 공식 발표</a> · <a href="{BUYBACK_FAQ}">바이백 공식 설명</a>',
    ])


def main() -> int:
    if not ALERT.exists():
        return 0

    text = ALERT.read_text(encoding="utf-8")
    original_title = None
    source_url = ""
    if DETAIL.exists():
        try:
            detail = json.loads(DETAIL.read_text(encoding="utf-8"))
            source = detail.get("source") or {}
            original_title = source.get("title")
            source_url = str(source.get("url") or "")
        except Exception:
            original_title = None

    if original_title:
        translated = translate_title(str(original_title))
        text = text.replace(
            f"• 공식 출처: <b>{original_title}</b>",
            f"• 공식 출처: <b>{translated}</b>",
        )

    pattern = re.compile(r"(• 공식 출처: <b>)([^<]+)(</b>)")
    def repl(match: re.Match[str]) -> str:
        shown = match.group(2).strip()
        if re.search(r"[A-Za-z]{4,}", shown):
            shown = translate_title(shown)
            if re.search(r"[A-Za-z]{4,}", shown):
                shown = "미 재무부 공식 발표"
        return match.group(1) + shown + match.group(3)

    text = pattern.sub(repl, text)

    if UPGRADE_MARKER not in text:
        text = text.rstrip() + "\n" + upgrade_block() + "\n"

    if source_url.rstrip("/") == TREASURY_RELEASE.rstrip("/") and TITLE.exists():
        TITLE.write_text(
            "🇺🇸 미 재무부 장기물 바이백 — 베센트, ‘금리 통제 아닌 변동성 완화’ 정책선 명확화\n",
            encoding="utf-8",
        )

    if re.search(r"• 공식 출처: <b>[^<]*\b(Treasury|Buyback|Refunding)\b", text, re.I):
        raise RuntimeError("공식 출처 제목의 한국어 변환이 완료되지 않았습니다.")

    if len(text) > 3900:
        raise RuntimeError(f"업그레이드된 재무부 알림 본문이 너무 깁니다: {len(text)}")

    ALERT.write_text(text, encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
