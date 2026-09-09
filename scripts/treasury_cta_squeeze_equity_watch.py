#!/usr/bin/env python3
"""Add compact Bessent-policy and stock-market interpretation to audited CTA alerts."""
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
        return "🟢 성장주 우호 강화", "채권가격↑·장기금리↓가 확인돼 나스닥·반도체 등 할인율 부담 완화. 경기침체형 금리하락은 제외."
    if (short_bias or prices_up >= 2) and repo_ok:
        return "🟡 중립~약한 우호", f"숏 압력은 완화됐지만 10년물 {yld:.3f}%·z={z:+.2f}σ로 금리 하락 추세는 아직 미확인."
    return "⚪ 중립", f"10년물 {yld:.3f}%에서 실제 할인율 완화 신호 미확인."


def format_alert(snapshot, previous, fx, fx_date, reasons):
    title, body = _base_format(snapshot, previous, fx, fx_date, reasons)
    impact, path = _equity_impact(snapshot, previous, reasons)
    policy_block = (
        "<b>🧭 베센트 정책 경계선</b>\n"
        "• 공식선은 <b>유동성·변동성 완화</b>. 4.30% 고정·수익률통제·Fed QE는 공식 목표가 아님.\n"
        "• CTA 숏커버는 시장 결과로 분리. 정상시장에서도 특정 금리에 맞춘 매입·발행 반복 시 <b>🟠 사실상 금리관리</b> 경보. 발언 한 건만으로 재발송하지 않음.\n\n"
    )
    equity_block = (
        "<b>📈 주식시장 영향</b>\n"
        f"• <b>{impact}</b> — {path}\n"
        "• 격상: 10Y 4.50% 하향 또는 -1σ + 선물가격↑. 반대로 repo·신용스트레스 동반 금리하락은 위험자산 악재.\n\n"
    )
    marker = "<b>한 줄 결론</b>"
    additions = ""
    if "🧭 베센트 정책 경계선" not in body:
        additions += policy_block
    if "📈 주식시장 영향" not in body:
        additions += equity_block
    if additions:
        body = body.replace(marker, additions + marker, 1) if marker in body else body + "\n\n" + additions.rstrip()
    return title, body


audited.format_alert = format_alert

if __name__ == "__main__":
    raise SystemExit(watcher.main())
