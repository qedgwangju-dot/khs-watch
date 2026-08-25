#!/usr/bin/env python3
"""Final audit layer for the Treasury CTA squeeze Telegram alert.

Adds three accuracy guards:
1) Preserve the quoted Goldman CTA baseline as a clearly labelled secondary-source benchmark.
2) Do not call CFTC weekly total open interest a real-time CME OI signal.
3) Express the 4.30% target distance as a required yield decline, not +bp.
"""
from __future__ import annotations

import re

import treasury_cta_squeeze_watch as watcher
import treasury_cta_squeeze_market_watch  # noqa: F401  # installs resilient market-data formatter

watcher.FORMAT_REVISION = max(int(getattr(watcher, "FORMAT_REVISION", 0)), 6)

SECONDARY_CTA_SOURCE = "https://a.foresightnews.pro/article/detail/99813"

_base_format = watcher.format_alert


def _krw_per_bp(usd_dv01: float, fx: float) -> str:
    won = usd_dv01 * fx
    if won >= 100_000_000:
        return f"약 {won / 100_000_000:,.0f}억원/bp"
    return f"약 {won:,.0f}원/bp"


def format_alert(snapshot, previous, fx, fx_date, reasons):
    title, body = _base_format(snapshot, previous, fx, fx_date, reasons)

    # 1) Keep the Goldman-quoted numbers visible, but never present them as an official feed.
    marker = "<b>1️⃣ Goldman CTA DV01 — 스퀴즈의 연료</b>\n"
    baseline = (
        f"• <b>2차 출처 기준선:</b> 글로벌 채권 CTA 순숏 약 1억5,500만달러 DV01"
        f"(1bp당 {_krw_per_bp(155_000_000, fx)})\n"
        f"• 채권가격이 1개월 내 +2σ 상승할 경우 약 1억5,000만달러 DV01"
        f"(1bp당 {_krw_per_bp(150_000_000, fx)}) 규모의 환매·재매수 추정\n"
        "• 위 수치는 Goldman Futures Desk를 인용한 2차 출처 기준선이며 Goldman 공개 공식 피드로 직접 검증된 값은 아닙니다.\n"
    )
    if marker in body and "2차 출처 기준선:" not in body:
        body = body.replace(marker, marker + baseline, 1)

    # 2) The runtime fallback uses delayed futures prices + CFTC weekly TOTAL market OI.
    body = body.replace(
        "<b>3️⃣ TY/US/WN 대응 CME 선물 — 가격 + 미결제약정</b>",
        "<b>3️⃣ TY/US/WN 선물 — 가격 + CFTC 주간 전체 시장 OI</b>",
    )
    oi_note = (
        "※ 현재 OI가 CFTC 주간 전체 시장 OI로 표시되는 경우 <b>당일 실시간 OI가 아닙니다.</b> "
        "따라서 가격↑·OI↓는 다음 CFTC 갱신에서 확인되는 주간 숏커버 확인 신호로만 사용합니다."
    )
    section3 = "<b>3️⃣ TY/US/WN 선물 — 가격 + CFTC 주간 전체 시장 OI</b>"
    if section3 in body and oi_note not in body:
        body = body.replace(section3, section3 + "\n" + oi_note, 1)

    # 3) 4.70 -> 4.30 is a 40bp DECLINE. Avoid the ambiguous +40bp label.
    y = snapshot.get("yield10") or {}
    if y.get("yield") is not None:
        distance = max(0.0, (float(y["yield"]) - 4.30) * 100)
        body = re.sub(
            r"• 현재 공식 10년물 [0-9.]+% → 4\.30%까지 [+-]?[0-9.]+bp",
            f"• 현재 공식 10년물 {float(y['yield']):.3f}% → 4.30%까지 <b>{distance:.1f}bp 하락 필요</b>",
            body,
            count=1,
        )

    daily_note = (
        "※ 미 재무부 공식 10년물은 일일 고시값입니다. 15분 감시의 장중 방향은 선물가격으로 보고, "
        "4.50·4.40·4.35·4.30% 공식 경보선 확정은 재무부 고시값으로 잠급니다."
    )
    sec6 = "<b>6️⃣ 10년물 4.3% 접근</b>"
    if sec6 in body and daily_note not in body:
        body = body.replace(sec6, sec6 + "\n" + daily_note, 1)

    # Keep the secondary-source baseline clickable without cluttering the headline sections.
    if "CTA 2차 출처" not in body:
        body += f'\n<a href="{SECONDARY_CTA_SOURCE}">CTA 2차 출처</a>'

    return title, body


watcher.format_alert = format_alert

if __name__ == "__main__":
    raise SystemExit(watcher.main())
