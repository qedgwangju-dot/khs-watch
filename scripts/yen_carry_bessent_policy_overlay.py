#!/usr/bin/env python3
"""Add Bessent US-Japan policy coordination and equity-impact interpretation to yen-carry alerts.

This is an interpretation overlay only. It does not create a new standalone alert.
It edits an already-generated yen-carry composite alert so the same event is not sent twice.

Policy baseline:
- Bessent's 2026-09-09 "I am the house now" remark is treated as policy signalling,
  not as an official fixed USD/JPY target.
- Actual FX intervention, BOJ decisions, and market carry-unwind evidence remain separate facts.
- Equity impact distinguishes orderly yen strengthening from disorderly carry deleveraging.
"""

from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "out"
DATA = ROOT / "data"
ALERT = OUT / "yen_carry_composite_alert.md"
PENDING = OUT / "yen_carry_composite_pending_state.json"
STATE = DATA / "yen_carry_composite_state.json"
CONTEXT = OUT / "yen_carry_bessent_policy_context.md"

BESSENT_YEN_SOURCE = "https://www.marketwatch.com/story/bessent-says-i-am-the-house-now-what-it-means-for-the-yen-and-u-s-stocks-9ef63bc3"
REUTERS_POLICY_SOURCE = "https://www.reuters.com/world/asia-pacific/how-bessent-americas-bond-salesman-cornered-japan-big-spending-2026-09-17/"


def load_json(path: Path) -> dict:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
        return value if isinstance(value, dict) else {}
    except Exception:
        return {}


def n(value, default=0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def stock_impact(state: dict) -> tuple[str, list[str]]:
    values = state.get("values") or {}
    unwind_level = int(state.get("unwind_level", 0) or 0)
    rebuild_level = int(state.get("rebuild_level", 0) or 0)
    target = state.get("target_currency") or {}
    stressed = int(target.get("stressed_count", 0) or 0)
    usdjpy = n(values.get("usdjpy"))
    move_60 = n(values.get("usdjpy_60m_pct"))
    drawdown_12h = n(values.get("usdjpy_12h_drawdown_pct"))

    if unwind_level >= 2 or move_60 <= -1.0 or drawdown_12h <= -1.5 or stressed >= 2:
        verdict = "🔴 위험자산 수급 부담 확대"
        lines = [
            "• 엔화 강세가 너무 빠르면 엔캐리 포지션의 강제축소가 미국 기술주·AI·암호자산·한국 위험자산 매도로 번질 수 있습니다.",
            "• 이 경우 ‘엔 강세=호재’가 아니라 <b>레버리지 축소 충격</b>을 우선합니다.",
        ]
    elif unwind_level == 1 or move_60 <= -0.5 or drawdown_12h <= -0.75:
        verdict = "🟠 혼조 — 할인율보다 캐리청산 속도 점검"
        lines = [
            "• 질서 있는 엔 강세는 과도한 숏을 줄이는 정상화지만, 속도가 빨라지면 Nasdaq·AI·KOSPI 수급에는 부담이 될 수 있습니다.",
            "• 주식은 USD/JPY 자체보다 <b>엔캐리 청산 속도와 변동성</b>을 함께 봅니다.",
        ]
    elif rebuild_level >= 1 and unwind_level == 0:
        verdict = "🟡 위험자산 유동성에는 우호적이나 엔 약세 재확대 주의"
        lines = [
            "• 캐리 재구축 여지가 남아 있으면 글로벌 위험자산 수급에는 단기 우호적일 수 있습니다.",
            "• 다만 엔화 재약세가 정책당국의 추가 구두개입·실개입·BOJ 긴축을 부르면 이후 변동성이 다시 커질 수 있습니다.",
        ]
    else:
        verdict = "⚪ 주식시장 영향 중립"
        lines = [
            "• 현재 엔캐리 청산·재구축 어느 쪽도 강하게 확인되지 않아 주식 수급 신호로 격상하지 않습니다.",
            "• 다음 판단은 USD/JPY 속도, CFTC 엔 포지션, 미·일 2년 금리차, 실제 정책조치가 같은 방향으로 겹치는지 확인합니다.",
        ]

    header = f"• 현재 USD/JPY: {usdjpy:.2f}" if usdjpy else "• 현재 USD/JPY: 확인 가능한 최신값 사용"
    return verdict, [header, *lines]


def build_block(state: dict) -> str:
    evidence = state.get("evidence") or {}
    policy_recent = bool(evidence.get("unwind::최근 공식 공동개입·추가개입 경고"))
    verdict, equity_lines = stock_impact(state)
    return "\n".join([
        "",
        "미·일 정책공조·시장 영향",
        "• Bessent의 ‘I am the house now’ 발언은 <b>엔화 약세 베팅에 대한 강한 정책 신호</b>로 보되, 특정 USD/JPY 수준을 공식 방어선으로 선언한 것으로 해석하지 않습니다.",
        f"• 실제 정책 확인: {'최근 공식 공동개입·추가개입 경고 신호 있음' if policy_recent else '현재 복합상태에서 신규 공식 공동개입·추가개입 경고는 미확인'}",
        "• 구두개입 → 실제 미·일 FX 개입 → BOJ 정책결정 → CFTC 엔 포지션 → USD/JPY 반응을 순서대로 분리합니다. 발언 하나만으로 실개입이나 BOJ 결정을 확정하지 않습니다.",
        "",
        f"주식시장 영향 — {verdict}",
        *equity_lines,
        "• 질서 있는 엔 강세는 과도한 레버리지 정상화일 수 있지만, 급격한 엔캐리 청산은 성장주·암호자산·한국 증시의 수급 악재가 될 수 있어 방향을 따로 판정합니다.",
        "",
        f"- Bessent 엔화 발언: {BESSENT_YEN_SOURCE}",
        f"- 미·일 정책공조 검증: {REUTERS_POLICY_SOURCE}",
    ])


def main() -> int:
    state = load_json(PENDING) or load_json(STATE)
    block = build_block(state)
    CONTEXT.parent.mkdir(parents=True, exist_ok=True)
    CONTEXT.write_text(block.strip() + "\n", encoding="utf-8")

    if not ALERT.exists():
        return 0

    text = ALERT.read_text(encoding="utf-8")
    if "미·일 정책공조·시장 영향" in text:
        return 0

    updated = text.rstrip() + "\n" + block + "\n"
    ALERT.write_text(updated, encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
