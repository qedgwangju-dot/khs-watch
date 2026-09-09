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


def bessent_yen_policy_block() -> str:
    return "\n".join([
        "②-3 미·일 정책공조·엔캐리 시장영향",
        "- Bessent 발언은 우선 <b>구두개입·정책공조 신호</b>로 분류. 미·일 당국의 실제 외환거래가 공식 확인되기 전에는 새로운 ‘실개입’으로 표시하지 않음.",
        "- BOJ 확인: 정책금리·가이던스가 실제 엔 강세 방향을 뒷받침하는지 별도 확인. 미국 측 발언만으로 BOJ 결정까지 확정하지 않음.",
        "- 환율 방어선: 공식 선언이 없는 한 특정 USD/JPY 숫자를 미국·일본 정부의 고정 방어선으로 간주하지 않음.",
        "- 🟢 질서 있는 엔 강세: USD/JPY 하락 + BOJ 정상화/금리차 축소 + VIX·주식 안정 → 과도한 엔 숏 축소로 보고 주식은 중립~약한 우호.",
        "- 🔴 엔캐리 강제청산: USD/JPY 급락 + VIX 급등 + Nikkei·Nasdaq 등 위험자산 동반 약세 → 레버리지 회수·위험자산 수급 악재로 격상.",
        "- 주식 전달경로: 질서 있는 엔 강세는 환율 정상화에 가깝지만, 급격한 엔캐리 청산이면 Nasdaq·반도체·KOSPI/KOSDAQ·고베타 자산까지 매도 압력이 번질 수 있음.",
        "- 중복 방지: ‘I am the house now’ 같은 Bessent 발언 한 건만으로 새 Telegram을 만들지 않고, 기존 글로벌 금리·엔캐리 이벤트가 발생했을 때 해석 블록으로만 반영.",
    ])


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


def main() -> int:
    result = load(RESULT, {})
    events = load(EVENT, {}).get("events") or []
    sources = source_lines(result)
    policy = bessent_yen_policy_block()

    if REPORT.exists():
        raw = REPORT.read_text(encoding="utf-8")
        blocks: list[str] = []
        if BLOCK.exists() and "②-2 JGB 3% 체제·실제 자금이동" not in raw:
            blocks.append(BLOCK.read_text(encoding="utf-8"))
        if "②-3 미·일 정책공조·엔캐리 시장영향" not in raw:
            blocks.append(policy)
        if blocks:
            REPORT.write_text(inject_before_sources(raw, blocks, sources), encoding="utf-8")
        return 0

    # Do not create a standalone alert merely for the Bessent policy interpretation.
    # Only an already-material JGB regime/flow event can originate a report here.
    if not BLOCK.exists() or not events:
        return 0

    block = BLOCK.read_text(encoding="utf-8")
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
        policy,
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
