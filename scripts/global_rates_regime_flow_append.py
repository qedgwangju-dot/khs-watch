#!/usr/bin/env python3
"""Append the JGB-regime / Japan-overseas-flow block to the Telegram report.

If the upgrade itself produced a material event while the base formatter produced no
report, create a compact standalone report so the new signal can still be delivered.
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


def load(path: pathlib.Path, default):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return default


def source_lines(result: dict) -> list[str]:
    src = result.get("sources") or {}
    lines = []
    if src.get("jgb"):
        lines.append(f"- 일본 재무성 JGB 금리: {src['jgb']}")
    if src.get("weekly_flow"):
        lines.append(f"- 일본 재무성 주간 해외증권투자: {src['weekly_flow']}")
    if src.get("weekly_schedule"):
        lines.append(f"- 일본 재무성 주간 수급 발표일정: {src['weekly_schedule']}")
    auction = (load(OUT / "global_rates_structural.json", {}).get("auction") or {})
    if auction.get("url"):
        lines.append(f"- 일본 재무성 JGB 입찰 결과: {auction['url']}")
    return lines


def inject_before_sources(text: str, block: str, sources: list[str]) -> str:
    lines = text.splitlines()
    try:
        idx = next(i for i, line in enumerate(lines) if line.strip() == "출처")
    except StopIteration:
        idx = len(lines)
    before, after = lines[:idx], lines[idx:]
    if before and before[-1].strip():
        before.append("")
    before.extend(block.rstrip().splitlines())
    before.append("")
    if after:
        existing = set(after)
        after.extend(line for line in sources if line not in existing)
    else:
        after = ["출처", *sources]
    return "\n".join(before + after).strip() + "\n"


def main() -> int:
    if not BLOCK.exists():
        return 0
    block = BLOCK.read_text(encoding="utf-8")
    result = load(RESULT, {})
    events = load(EVENT, {}).get("events") or []
    sources = source_lines(result)

    if REPORT.exists():
        raw = REPORT.read_text(encoding="utf-8")
        if "②-2 JGB 3% 체제·실제 자금이동" not in raw:
            REPORT.write_text(inject_before_sources(raw, block, sources), encoding="utf-8")
        return 0

    if not events:
        return 0

    regime = result.get("regime") or {}
    label = regime.get("label") or "구조 변화"
    now = datetime.now(KST).strftime("%Y-%m-%d %H:%M:%S KST")
    text = "\n".join([
        "[글로벌 금리·엔캐리 경보] 🟡",
        f"판정: 구조 신호 변화 — {label}",
        f"조회: {now}",
        "",
        block.rstrip(),
        "",
        "정확한 의미",
        "- 구조 신호 하나만으로 엔캐리 청산을 확정하지 않습니다. 미·일 단기금리차·USD/JPY·변동성·주식 전염이 동반되는지 기존 확인축에서 별도 검산합니다.",
        "",
        "출처",
        *sources,
    ]) + "\n"
    REPORT.write_text(text, encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
