#!/usr/bin/env python3
"""Add concise Bessent-policy and stock-impact interpretation to audited CTA alerts."""
from __future__ import annotations

import treasury_cta_squeeze_audited_watch as audited

watcher = audited.watcher
watcher.FORMAT_REVISION = max(int(getattr(watcher, "FORMAT_REVISION", 0)), 9)
_base_format = audited.format_alert


def _equity_impact(snapshot: dict, previous: dict, reasons: list[str]) -> tuple[str, str]:
    y = snapshot.get("yield10") or {}
    yld = float(y.get("yield") or 0.0)
    z = float(y.get("z20") or 0.0)
    evidence = watcher.squeeze_evidence(snapshot, previous)
    repo_ok, _ = audited._repo_not_worse(snapshot, previous)
    prices_up = audited._price_up_count(snapshot)
    short_bias = any("CFTC 숏 축소" in r or "CFTC 주간 숏 축소" in r for r in reasons)
    if evidence and z <= -1.0 and repo_ok:
        return "🟢 성장주 우호 강화", "금리↓가 포지션과 함께 확인 → 나스닥·반도체 할인율 우호. 경기침체형 하락은 제외."
    if (short_bias or prices_up >= 2) and repo_ok:
        return "🟡 중립~약한 우호", f"숏은 완화됐지만 10Y {yld:.3f}%·z={z:+.2f}σ로 추세전환 미확인."
    return "⚪ 중립", f"10Y {yld:.3f}%: 할인율 완화 미확인."


def format_alert(snapshot, previous, fx, fx_date, reasons):
    title, body = _base_format(snapshot, previous, fx, fx_date, reasons)
    impact, path = _equity_impact(snapshot, previous, reasons)
    block = (
        "<b>🧭 정책·주식 해석</b>\n"
        "• Bessent 공식선=<b>유동성·변동성 완화</b>; 4.30%·수익률통제·QE는 공식 목표 아님. CTA 숏커버는 시장 결과이며, 정상시장 특정 금리 대응 반복 시 🟠 사실상 금리관리 경보.\n"
        f"• 주식: <b>{impact}</b> — {path}\n"
        "• 10Y 4.50% 하향/-1σ+선물↑면 우호 격상; repo·신용스트레스형 금리↓는 위험자산 악재. 발언 한 건만으로 재발송하지 않음.\n\n"
    )
    marker = "<b>한 줄 결론</b>"
    if "🧭 정책·주식 해석" not in body:
        body = body.replace(marker, block + marker, 1) if marker in body else body + "\n\n" + block.rstrip()
    return title, body


audited.format_alert = format_alert

if __name__ == "__main__":
    raise SystemExit(watcher.main())
