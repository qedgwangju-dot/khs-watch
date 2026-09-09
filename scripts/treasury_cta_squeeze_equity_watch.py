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
            "채권가격 상승과 장기금리 하락이 함께 확인되면 할인율이 내려가 고평가 성장주·반도체·소프트웨어에 가장 직접적인 우호 요인입니다. REIT·주택 등 금리민감주도 우호적이며, 은행은 장단기 금리곡선에 따라 혼조일 수 있습니다.",
            "단, 경기침체·실적 하향 때문에 금리가 내려가는 경우에는 같은 금리하락이라도 주식 호재로 보지 않습니다.",
        )

    if (short_bias or prices_up >= 2) and repo_ok:
        return (
            "🟡 중립~약한 우호",
            f"숏 포지션 축소는 채권 매도압력을 줄여 주식 할인율에는 우호적일 수 있지만, 현재 10년물 {yld:.3f}%·z={z:+.2f}σ처럼 실제 금리 하락 추세가 확인되지 않으면 나스닥·반도체의 강한 상승 신호로 격상하지 않습니다.",
            "10년물 4.50% 하향 돌파 또는 -1σ 진입과 선물가격 상승이 함께 나오면 성장주·반도체·REIT 우호를 한 단계 높입니다.",
        )

    return (
        "⚪ 주식시장 영향 중립",
        f"10년물 {yld:.3f}%에서 채권가격 상승·동일범위 OI 감소가 확인되지 않아 할인율 부담 완화가 아직 주식시장 추세 신호로 이어지지 않았습니다.",
        "금리 재상승이면 성장주 부담이 다시 커지고, 반대로 금리 하락이 경기침체 신호인지 포지션 정상화인지 원인을 분리해 판단합니다.",
    )


def format_alert(snapshot, previous, fx, fx_date, reasons):
    title, body = _base_format(snapshot, previous, fx, fx_date, reasons)
    impact, path, caveat = _equity_impact(snapshot, previous, reasons)

    policy_block = (
        "<b>🧭 베센트 정책 목적·경계선</b>\n"
        "• 현재 정책선: 장기 비지표물 바이백은 <b>유동성·변동성 완화와 시장 과속 억제</b>가 목적이라는 설명을 기준으로 판정합니다.\n"
        "• 공식 목표 아님: <b>10년물 4.30% 고정 · 수익률 통제 · Fed QE</b>. 4.30%는 시장의 CTA 스퀴즈 시나리오일 뿐입니다.\n"
        "• 의도와 결과 분리: CTA 숏커버가 실제 발생해도 이를 곧바로 ‘재무부의 공식 CTA 스퀴즈 목표’로 해석하지 않습니다.\n"
        "• 정책선 이탈 경보: 시장 기능이 정상인데도 특정 금리 수준에 맞춰 바이백·발행구조를 반복 변경하면 <b>🟠 유동성 지원 → 사실상 금리관리 가능성</b>으로 격상합니다.\n"
        "• 중복 방지: Bessent 발언 한 건만으로 CTA 알림을 새로 보내지 않으며, 실제 바이백 금액·제시액·매입액은 기존 바이백 집행 알림이 담당합니다.\n\n"
    )

    equity_block = (
        "<b>📈 주식시장 영향</b>\n"
        f"• 현재 판정: <b>{impact}</b>\n"
        f"• 경로: {path}\n"
        f"• 뒤집는 조건: {caveat}\n"
        "• 해석 원칙: <b>질서 있는 금리 하락</b>은 성장주 할인율에 우호적이지만, 경기침체·신용스트레스·repo 악화에 따른 금리 하락은 위험자산 악재일 수 있습니다.\n\n"
    )

    marker = "<b>한 줄 결론</b>"
    if marker in body:
        additions = ""
        if "🧭 베센트 정책 목적·경계선" not in body:
            additions += policy_block
        if "📈 주식시장 영향" not in body:
            additions += equity_block
        if additions:
            body = body.replace(marker, additions + marker, 1)
    else:
        if "🧭 베센트 정책 목적·경계선" not in body:
            body += "\n\n" + policy_block.rstrip()
        if "📈 주식시장 영향" not in body:
            body += "\n\n" + equity_block.rstrip()
    return title, body


audited.format_alert = format_alert

if __name__ == "__main__":
    raise SystemExit(watcher.main())
