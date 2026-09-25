#!/usr/bin/env python3
"""Append JGB regime/flow and Bessent yen-policy interpretation to Telegram.

No new Telegram trigger is created for a Bessent quote alone. The policy/carry block is
only appended when the existing global-rates/yen-carry watcher has already produced a
report because of a real base/risk/structural event.
"""
from __future__ import annotations

import json
import pathlib
from datetime import datetime
from zoneinfo import ZoneInfo

ROOT = pathlib.Path(__file__).resolve().parents[1]
OUT = ROOT / "out"
REPORT = OUT / "global_rates_watch_telegram.md"
BLOCK = OUT / "global_rates_regime_flow_block.md"
EVENT = OUT / "global_rates_regime_flow_event.json"
RESULT = OUT / "global_rates_regime_flow.json"
KST = ZoneInfo("Asia/Seoul")

CBOE_VIX = "https://www.cboe.com/tradable-products/vix/vix-historical-data"
NASDAQ_COMP = "https://indexes.nasdaq.com/Index/Overview/COMP"
NIKKEI_225 = "https://indexes.nikkei.co.jp/en/nkave/archives/data"


def load(path: pathlib.Path, default):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return default


def source_lines(result: dict) -> list[str]:
    src = result.get("sources") or {}
    lines = []
    if src.get("weekly_flow"):
        lines.append(f"- 일본 재무성 주간 해외증권투자: {src['weekly_flow']}")

    confirmation = load(OUT / "yen_carry_confirmation.json", {})
    confirmation_data = confirmation.get("data") or {}
    if confirmation_data.get("VIXCLS"):
        lines.append(f"- Cboe VIX: {CBOE_VIX}")
    if confirmation_data.get("NASDAQCOM"):
        lines.append(f"- Nasdaq Composite: {NASDAQ_COMP}")
    if confirmation_data.get("NIKKEI225"):
        lines.append(f"- Nikkei 225: {NIKKEI_225}")
    return lines


def compact_regime_block(result: dict) -> str:
    regime = result.get("regime") or {}
    flow = result.get("flow") or {}
    absorption = result.get("absorption") or {}
    lines = ["③-1 원인·자금 흐름"]

    label = regime.get("label")
    if label:
        parts = [f"• 원인 │ {label}"]
        if regime.get("jgb10") is not None:
            parts.append(f"JGB10 {regime.get('jgb10'):.3f}%({regime.get('d10_bp', 0):+.1f}bp)")
        if regime.get("ust10") is not None:
            parts.append(f"UST10 {regime.get('ust10'):.3f}%({regime.get('ust10_change_bp', 0):+.1f}bp)")
        lines.append(" · ".join(parts))

    if flow:
        lines.append(
            f"• 일본 해외자산 │ {flow.get('period','')} {flow.get('subtotal_display','확인 불가')} · "
            f"{flow.get('label','')}"
        )

    if absorption.get("label") and absorption.get("label") != "해당 없음":
        lines.append(f"• 3%대 입찰 │ {absorption.get('label')}")

    lines.append("• 해석 │ 해외자산 순매수·엔화 약세가 이어지면 강제청산 확인 아님. 순매도 전환+엔화 급등+변동성 상승이 겹치면 경계 상향.")
    return "\n".join(lines)


def inject_before_sources(text: str, blocks: list[str], sources: list[str]) -> str:
    lines = text.splitlines()
    try:
        idx = next(i for i, line in enumerate(lines) if line.strip() == "출처")
    except StopIteration:
        idx = len(lines)
    before, after = lines[:idx], lines[idx:]
    for block in blocks:
        if not block.strip():
            continue
        if before and before[-1].strip():
            before.append("")
        before.extend(block.rstrip().splitlines())
    if before and before[-1].strip():
        before.append("")
    if after:
        existing = set(after)
        after.extend(line for line in sources if line not in existing)
    else:
        after = ["출처", *sources]
    return "\n".join(before + after).strip() + "\n"


def normalize_confirmation_label(text: str) -> str:
    return text.replace(
        "- VIX·Nikkei·Nasdaq은 FRED 일간 후행 확인값. 장중 실시간 값으로 오인하지 않음.",
        "- VIX·Nikkei·Nasdaq은 각 공식 지수 제공처의 일간 후행 확인값을 우선 사용하고, 실패 시 동일 지표 FRED 일간값만 대체 사용. 장중 실시간 값으로 오인하지 않음.",
    )


def main() -> int:
    result = load(RESULT, {})
    events = load(EVENT, {}).get("events") or []
    sources = source_lines(result)
    compact = compact_regime_block(result)

    if REPORT.exists():
        raw = normalize_confirmation_label(REPORT.read_text(encoding="utf-8"))
        if "③-1 원인·자금 흐름" not in raw:
            marker = "\n④ 판정"
            if marker in raw:
                raw = raw.replace(marker, "\n" + compact + marker, 1)
            else:
                raw = raw.rstrip() + "\n\n" + compact + "\n"
        REPORT.write_text(inject_before_sources(raw, [], sources), encoding="utf-8")
        return 0

    # Only a material regime/flow event may originate a standalone report.
    if not events:
        return 0

    regime = result.get("regime") or {}
    label = regime.get("label") or "구조 변화"
    now = datetime.now(KST).strftime("%Y-%m-%d %H:%M:%S KST")
    text = "\n".join([
        "[글로벌 금리·엔캐리] 🟡 구조 변화",
        f"판정 │ {label}",
        f"조회 │ {now}",
        "",
        compact,
        "",
        "판정",
        "• 구조 신호 하나만으로 엔캐리 청산을 확정하지 않음. 미·일 단기금리차·USD/JPY·VIX·주식 전염을 함께 확인.",
        "",
        "출처",
        *sources,
    ]) + "\n"
    REPORT.write_text(text, encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
