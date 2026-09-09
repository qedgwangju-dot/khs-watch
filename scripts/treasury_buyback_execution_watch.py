#!/usr/bin/env python3
"""Execution-only Treasury buyback watcher.

This wrapper deliberately removes the overlap with the separate official-policy watcher.
The policy watcher owns announcements and schedule changes. This watcher sends Telegram
only when the official TreasuryDirect buyback result fingerprint changes.
"""
from __future__ import annotations

import hashlib
import json
from datetime import date

import treasury_buyback_media_watch_v2 as watcher

_original_digest = watcher.digest
_original_load_state = watcher.load_state

# A format bump must not create a Telegram alert by itself in execution-only mode.
watcher.FORMAT_REVISION = max(int(getattr(watcher, "FORMAT_REVISION", 0)), 9)
BASELINE_LINK = watcher.BUYBACK_RESULTS_PAGE
MIGRATION_KEY = "execution_results_dedupe_v1"
SEP9_BUYBACK_REUTERS = "https://www.reuters.com/world/us-treasury-buy-up-6-billion-sept-10-buyback-operation-2026-09-09/"
SEP9_MARKET_REUTERS = "https://www.reuters.com/world/china/global-markets-global-markets-2026-09-09/"


def _stable_results_digest(value: str) -> str:
    """Hash parsed official result numbers instead of volatile page HTML when possible."""
    stats = watcher.extract_buyback_stats(value)
    if stats and stats.get("accepted") is not None and stats.get("offered") is not None:
        payload = {
            "max": stats.get("max"),
            "accepted": stats.get("accepted"),
            "offered": stats.get("offered"),
            "cap_use_pct": round(float(stats.get("cap_use_pct") or 0), 8),
            "accept_pct": round(float(stats.get("accept_pct") or 0), 8),
            "offer_multiple": round(float(stats.get("offer_multiple") or 0), 8),
        }
        return hashlib.sha256(
            json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
        ).hexdigest()
    return _original_digest(value)


def news_items_execution_only() -> list[dict]:
    # Keep one synthetic signal so the base watcher can render an alert when the
    # official result changes, but do not import media/TGA/vigilante headlines here.
    return [{
        "title": "Treasury official buyback execution baseline",
        "link": BASELINE_LINK,
        "description": "Treasury general account TGA buyback official execution monitoring baseline",
        "source": "TreasuryDirect official results monitor",
        "pubDate": "",
    }]


def load_state_execution_only() -> dict:
    state = _original_load_state()

    # The policy watcher owns schedule changes. Pin the schedule hash to the current
    # value before the base comparison so a schedule edit cannot trigger this channel.
    try:
        schedule_xml = watcher.fetch(watcher.TENTATIVE_SCHEDULE_XML)
        state["schedule_hash"] = _original_digest(schedule_xml)
    except Exception:
        pass

    seen = list(state.get("seen", []) or [])
    if BASELINE_LINK not in seen:
        seen.append(BASELINE_LINK)
    state["seen"] = seen[-200:]

    # One-time migration to the stable parsed-result fingerprint without sending a
    # false "new result" alert just because the hashing method changed.
    if not state.get(MIGRATION_KEY):
        try:
            results_page = watcher.fetch(watcher.BUYBACK_RESULTS_PAGE)
            state["results_hash"] = _stable_results_digest(results_page)
        except Exception:
            pass
        state[MIGRATION_KEY] = True

    # Do not resend merely because formatting code changed.
    state["format_revision"] = watcher.FORMAT_REVISION
    return state


def _fmt_krw_from_usd(usd: float, fx: float) -> str:
    krw = usd * fx
    if krw >= 1_000_000_000_000:
        return f"약 {krw / 1_000_000_000_000:,.2f}조원"
    if krw >= 100_000_000:
        return f"약 {krw / 100_000_000:,.0f}억원"
    if krw >= 10_000:
        return f"약 {krw / 10_000:,.0f}만원"
    return f"약 {krw:,.0f}원"


def _fmt_usd_krw(usd: float | None, fx: float) -> str:
    if usd is None:
        return "확인 불가"
    return f"${usd:,.0f}({_fmt_krw_from_usd(usd, fx)})"


def _sep10_market_context(maximum: float | None) -> list[str]:
    """Event-specific baseline for the first $6B 10Y-20Y operation only.

    Do not recycle this market reaction into later buyback operations. The date guard
    keeps the block tied to the Sep. 10, 2026 operation/result window.
    """
    if maximum is None:
        return []
    today = date.today()
    if not (5_500_000_000 <= float(maximum) <= 6_500_000_000):
        return []
    if today < date(2026, 9, 10) or today > date(2026, 9, 12):
        return []
    return [
        "",
        "<b>발표 뒤 시장 기준선</b>",
        "• 9월 9일 최대 60억달러 공지 뒤 10년물은 장중 4.8528%까지 상승해 2023년 11월 이후 최고치를 기록했습니다.",
        "• 20년물은 약 5.314%, 30년물은 약 5.307%까지 올라 60억달러가 일부 시장 기대(80억~100억달러)의 하단이라는 실망이 먼저 반영됐습니다.",
        "• 다만 같은 날 390억달러 10년물 입찰은 High Yield 4.834%, Bid-to-Cover 2.71로 강했고 이후 금리는 고점에서 일부 되돌렸습니다. 따라서 ‘바이백 발표=완전 실패’로 단정하지 않습니다.",
        "• 실제 60억달러 운영은 9월 10일 13:40~14:00 ET(한국시간 9월 11일 02:40~03:00)입니다. <b>60억달러는 사전 상한이고, 아래 실제 매입액이 집행 결과입니다.</b>",
        f'<a href="{SEP9_BUYBACK_REUTERS}">60억달러 바이백 공지 검증</a> · <a href="{SEP9_MARKET_REUTERS}">발표 뒤 시장 반응</a>',
    ]


def build_execution_alert(
    tga_item: dict | None,
    vigilante_item: dict | None,
    fx: float,
    fx_date: str,
    schedule_changed: bool,
    results_changed: bool,
    stats: dict | None,
):
    stats = stats or {}
    offered = stats.get("offered")
    accepted = stats.get("accepted")
    maximum = stats.get("max")
    cap_use = stats.get("cap_use_pct")
    accept_pct = stats.get("accept_pct")
    multiple = stats.get("offer_multiple")

    title = "🇺🇸 미 재무부 장기물 바이백 — 실제 집행 결과 변경"
    lines = [
        "<b>🎯 이번 알림은 정책 발표가 아니라 실제 바이백 결과가 바뀌었을 때만 전송합니다.</b>",
        "",
        "<b>실제 집행</b>",
        f"• 총 제시액: {_fmt_usd_krw(float(offered) if offered is not None else None, fx)}",
        f"• 실제 매입액: {_fmt_usd_krw(float(accepted) if accepted is not None else None, fx)}",
        f"• 매입상한: {_fmt_usd_krw(float(maximum) if maximum is not None else None, fx)}",
    ]
    if cap_use is not None:
        lines.append(f"• 상한 소진율: {float(cap_use):.1f}%")
    if accept_pct is not None:
        lines.append(f"• 제시액 대비 매입률: {float(accept_pct):.1f}%")
    if multiple is not None:
        lines.append(f"• 초과 제시배수: {float(multiple):.2f}배")

    lines.extend(_sep10_market_context(float(maximum) if maximum is not None else None))

    lines += [
        "",
        "<b>판정 기준</b>",
        "• 상한 소진율이 높고 초과 제시배수가 높으면 장기 비지표물의 매도 수요·딜러 재고 부담이 컸다는 신호입니다.",
        "• 반대로 상한을 크게 늘렸는데도 제시액이 약하면 유동성 지원 수요 자체가 약한 것으로 봅니다.",
        "• 최종 효과는 집행 직후 10·20·30년 금리와 다음 20·30년 신규 입찰의 꼬리·간접낙찰·딜러 인수까지 함께 확인합니다.",
        "",
        "<b>중복 제거 규칙</b>",
        "• 바이백 확대·축소 발표와 잠정 일정 변경 → 별도 ‘정책’ 감시가 담당",
        "• TGA 활용 가능성·언론 발언 → 이 알림에서는 전송하지 않음",
        "• CTA 숏커버·10년물 구간 변화 → 별도 ‘CTA’ 감시가 복합 확인 때만 담당",
        "",
        f"환율 기준: {fx_date}, 1달러={fx:,.2f}원",
        f'<a href="{watcher.BUYBACK_RESULTS_PAGE}">미 재무부 공식 바이백 결과</a>',
    ]
    body = "\n".join(lines)
    detail = {
        "fx": fx,
        "fx_date": fx_date,
        "buyback_stats": stats,
        "results_changed": bool(results_changed),
        "schedule_changed_suppressed": bool(schedule_changed),
        "mode": "execution_results_only",
        "format_revision": watcher.FORMAT_REVISION,
    }
    return title, body, detail


watcher.digest = _stable_results_digest
watcher.news_items = news_items_execution_only
watcher.load_state = load_state_execution_only
watcher.build_alert = build_execution_alert

if __name__ == "__main__":
    raise SystemExit(watcher.main())
