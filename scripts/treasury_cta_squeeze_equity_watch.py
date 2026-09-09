#!/usr/bin/env python3
"""Add policy-boundary and stock-market interpretation to the audited Treasury CTA squeeze alert.

This layer does not create a new CTA trigger. It enriches only alerts already approved
by the audited deduplication gate (plus the watcher's one-time format-revision resend).
"""
from __future__ import annotations

import treasury_cta_squeeze_audited_watch as audited

watcher = audited.watcher
watcher.FORMAT_REVISION = max(int(getattr(watcher, "FORMAT_REVISION", 0)), 9)
_base_format = audited.format_alert


def _equity_impact(snapshot: dict, previous: dict, reasons: list[str]) -> tuple[str, str, str]:
    y = snapshot.get("yield10") or {}
    yld = float(y.get("yield") or 0.0)
    z = float(y.get("z20") or 0.0)
    evidence = watcher.squeeze_evidence(snapshot, previous)
    repo_ok, _ = audited._repo_not_worse(snapshot, previous)
    prices_up = audited._price_up_count(snapshot)
    short_bias = any("CFTC 숏 축소" in r or "CFTC 주간 숏 축소" in r for r in reasons)

    if evidence and z <= -1.0 and repo_ok:
        return (
            "🟢 성장주·나스닥 우호 강화",
            "채권가격 상승·장기금리 하락이 함께 확인돼 할인율 부담이 실제로 낮아지는 단계입니다. 나스닥·반도체·소프트웨어·REIT에 우호적입니다.",
            "경기침체·신용스트레스로 금리가 내려가는 경우에는 주식 호재로 보지 않습니다.",
        )

    if (short_bias or prices_up >= 2) and repo_ok:
        return (
            "🟡 중립~약한 우호",
            f"숏 축소는 채권 매도압력을 낮추지만 10년물 {yld:.3f}%·z={z:+.2f}σ에서 실제 금리 하락 추세는 아직 미확인입니다.",
            "10년물 4.50% 하향 또는 -1σ 진입과 선물가격 상승이 겹치면 성장주 우호를 격상합니다.",
        )

    return (
        "⚪ 주식시장 영향 중립",
        f"10년물 {yld:.3f}%에서 채권가격 상승·동일범위 OI 감소가 확인되지 않아 할인율 완화 신호가 아직 없습니다.",
        "금리 재상승은 성장주 부담, 경기침체형 금리하락은 위험자산 악재로 구분합니다.",
    )


def format_alert(snapshot, previous, fx, fx_date, reasons):
    title, body = _base_format(snapshot, previous, fx, fx_date, reasons)
    impact, path, caveat = _equity_impact(snapshot, previous, reasons)

    policy_block = (
        "<b>🧭 베센트 정책 경계선</b>\n"
        "• 공식선: <b>유동성·변동성 완화</b>. 10년물 4.30% 고정·수익률통제·Fed QE는 공식 목표가 아닙니다.\n"
        "• CTA 숏커버는 <b>시장 결과</b>로 분리. 정상시장에서도 특정 금리에 맞춰 매입·발행을 반복 조정하면 <b>🟠 사실상 금리관리</b> 경보.\n"
        "• 발언 한 건만으로 CTA 알림을 새로 보내지 않고, 실제 바이백 집행은 기존 집행 알림에서 확인합니다.\n\n"
    )

    equity_block = (
        "<b>📈 주식시장 영향</b>\n"
        f"• 현재 판정: <b>{impact}</b>\n"
        f"• 경로: {path}\n"
        f"• 뒤집는 조건: {caveat}\n\n"
    )

    marker = "<b>한 줄 결론</b>"
    if marker in body:
        additions = ""
        if "🧭 베센트 정책 경계선" not in body:
            additions += policy_block
        if "📈 주식시장 영향" not in body:
            additions += equity_block
        if additions:
            body = body.replace(marker, additions + marker, 1)
    else:
        if "🧭 베센트 정책 경계선" not in body:
            body += "\n\n" + policy_block.rstrip()
        if "📈 주식시장 영향" not in body:
            body += "\n\n" + equity_block.rstrip()
    return title, body


audited.format_alert = format_alert

if __name__ == "__main__":
    raise SystemExit(watcher.main())
