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
watcher.FORMAT_REVISION = max(int(getattr(watcher, "FORMAT_REVISION", 0)), 10)
BASELINE_LINK = watcher.BUYBACK_RESULTS_PAGE
MIGRATION_KEY = "execution_results_dedupe_v1"
SEP9_BUYBACK_REUTERS = "https://www.reuters.com/world/us-treasury-buy-up-6-billion-sept-10-buyback-operation-2026-09-09/"
SEP9_MARKET_REUTERS = "https://www.reuters.com/world/china/global-markets-global-markets-2026-09-09/"
SEP9_10Y_AUCTION = "https://www.marketscreener.com/news/u-s-10-year-treasury-auction-shows-strong-demand-ce785bd9d088f222"
TREASURY_AUCTION_API = "https://www.treasurydirect.gov/TA_WS/securities/auctioned?format=json&type=Bond&day=240"
TREASURY_AUCTION_QUERY = "https://www.treasurydirect.gov/auctions/auction-query/"


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


def _num(value) -> float | None:
    if value is None or value == "":
        return None
    try:
        return float(str(value).replace(",", "").replace("$", ""))
    except Exception:
        return None


def _is_30y_bond(row: dict) -> bool:
    security_type = str(row.get("securityType") or row.get("type") or "").lower()
    term = str(row.get("securityTerm") or row.get("term") or "").lower()
    return "bond" in security_type and (term.startswith("30-year") or term.startswith("29-year"))


def _share(row: dict, key: str) -> float | None:
    accepted = _num(row.get("competitiveAccepted"))
    value = _num(row.get(key))
    if not accepted or value is None:
        return None
    return value / accepted * 100.0


def _latest_30y_auction_context() -> dict | None:
    """Read official TreasuryDirect auction API and return Sep. 10 30Y results + 6-auction averages.

    This is deliberately best-effort. If TreasuryDirect has not published the result yet,
    the buyback alert still sends and marks the 30Y comparison as pending.
    """
    try:
        rows = json.loads(watcher.fetch(TREASURY_AUCTION_API))
    except Exception:
        return None
    if not isinstance(rows, list):
        return None

    bonds = [row for row in rows if isinstance(row, dict) and _is_30y_bond(row)]
    bonds.sort(key=lambda row: str(row.get("auctionDate") or ""), reverse=True)
    current = next((row for row in bonds if str(row.get("auctionDate") or "") == "2026-09-10"), None)
    if not current:
        return None

    previous = [row for row in bonds if str(row.get("auctionDate") or "") < "2026-09-10"][:6]

    def avg(field: str) -> float | None:
        values = [_num(row.get(field)) for row in previous]
        clean = [value for value in values if value is not None]
        return sum(clean) / len(clean) if clean else None

    def avg_share(field: str) -> float | None:
        values = [_share(row, field) for row in previous]
        clean = [value for value in values if value is not None]
        return sum(clean) / len(clean) if clean else None

    return {
        "auction_date": str(current.get("auctionDate") or ""),
        "term": str(current.get("securityTerm") or current.get("term") or "30년물"),
        "offering_amount": _num(current.get("offeringAmount")),
        "high_yield": _num(current.get("highYield")),
        "btc": _num(current.get("bidToCoverRatio")),
        "indirect_pct": _share(current, "indirectBidderAccepted"),
        "direct_pct": _share(current, "directBidderAccepted"),
        "dealer_pct": _share(current, "primaryDealerAccepted"),
        "avg_btc_6": avg("bidToCoverRatio"),
        "avg_indirect_pct_6": avg_share("indirectBidderAccepted"),
        "avg_direct_pct_6": avg_share("directBidderAccepted"),
        "avg_dealer_pct_6": avg_share("primaryDealerAccepted"),
        "sample_n": len(previous),
    }


def _execution_strength(cap_use: float | None, multiple: float | None) -> tuple[str, str]:
    if cap_use is None:
        return "⚪", "집행 강도 확인 불가"
    if cap_use >= 90 and (multiple is None or multiple >= 1.0):
        if multiple is not None and multiple >= 1.5:
            return "🟢", "상한 대부분 소진 + 초과 제시 강함"
        return "🟢", "상한 대부분 소진"
    if cap_use >= 60:
        return "🟡", "상한의 과반 이상 집행"
    return "🔴", "확대된 상한 대비 실제 집행은 약함"


def _fmt_cmp(value: float | None, average: float | None, suffix: str = "") -> str:
    if value is None:
        return "확인 불가"
    text = f"{value:.1f}{suffix}"
    if average is not None:
        delta = value - average
        text += f" (직전 6회 평균 {average:.1f}{suffix}, {delta:+.1f}{suffix})"
    return text


def _sep10_market_context(maximum: float | None) -> list[str]:
    """Event-specific baseline for the first $6B 10Y-20Y operation only."""
    if maximum is None:
        return []
    today = date.today()
    if not (5_500_000_000 <= float(maximum) <= 6_500_000_000):
        return []
    if today < date(2026, 9, 10) or today > date(2026, 9, 12):
        return []

    lines = [
        "",
        "<b>발표 → 시장 반응 → 실제 집행</b>",
        "• 정책 규모: 기존 회당 20억달러 → 이번 10~20년물 최대 60억달러로 3배 확대. <b>60억달러는 실제 매입액이 아니라 사전 상한</b>입니다.",
        "• 예상 대비: 일부 월가 전망은 80억~100억달러까지 열어뒀기 때문에 60억달러 발표 직후 ‘기대보다 작다’는 실망이 먼저 반영됐습니다.",
        "• 금리 반응: Reuters 기준 10년물은 발표 뒤 장중 4.8528%까지 올라 2023년 11월 이후 최고치를 기록했습니다.",
        "• 동시 압력: Brent가 배럴당 100달러를 넘어 인플레이션·기간 프리미엄 압력도 함께 높아졌습니다. 따라서 금리 상승을 바이백 규모 하나만의 결과로 단정하지 않습니다.",
        "• 반대 신호: 같은 날 390억달러 10년물 입찰은 High Yield 4.834%, Bid-to-Cover 2.71로 강했습니다. 즉 장기 국채 최종수요가 전면 붕괴한 상황은 아닙니다.",
        "• 운영 시각: 9월 10일 13:40~14:00 ET(한국시간 9월 11일 02:40~03:00). <b>아래 실제 매입액이 정책의 첫 집행 강도 시험</b>입니다.",
        f'<a href="{SEP9_BUYBACK_REUTERS}">60억달러 공지</a> · <a href="{SEP9_MARKET_REUTERS}">시장 반응</a> · <a href="{SEP9_10Y_AUCTION}">10년물 입찰</a>',
    ]

    auction = _latest_30y_auction_context()
    lines += ["", "<b>30년물 신규 공급 대조군</b>"]
    if not auction:
        lines += [
            "• 9월 10일 30년물 입찰 결과가 아직 공식 API에 확인되지 않았습니다. 결과 확인 전에는 바이백이 장기물 수급을 이겼다고 판정하지 않습니다.",
            f'<a href="{TREASURY_AUCTION_QUERY}">미 재무부 국채 입찰 결과</a>',
        ]
        return lines

    btc = auction.get("btc")
    avg_btc = auction.get("avg_btc_6")
    indirect = auction.get("indirect_pct")
    direct = auction.get("direct_pct")
    dealer = auction.get("dealer_pct")
    avg_indirect = auction.get("avg_indirect_pct_6")
    avg_direct = auction.get("avg_direct_pct_6")
    avg_dealer = auction.get("avg_dealer_pct_6")
    high_yield = auction.get("high_yield")
    n = int(auction.get("sample_n") or 0)

    if btc is not None and avg_btc is not None and indirect is not None and avg_indirect is not None and dealer is not None and avg_dealer is not None:
        if btc >= avg_btc and indirect >= avg_indirect and dealer <= avg_dealer:
            auction_verdict = "🟢 최종수요 강함 — 바이백과 신규 공급이 동시에 소화되는 쪽"
        elif btc < avg_btc and indirect < avg_indirect and dealer > avg_dealer:
            auction_verdict = "🔴 최종수요 약함 — 바이백 확대에도 신규 장기채 공급 부담이 더 큼"
        else:
            auction_verdict = "🟡 혼조 — 바이백 효과와 신규 공급 부담이 엇갈림"
    else:
        auction_verdict = "⚪ 일부 지표 확인 불가 — 단정 보류"

    lines += [
        f"• 30년물 High Yield: {high_yield:.3f}%" if high_yield is not None else "• 30년물 High Yield: 확인 불가",
        f"• Bid-to-Cover: {_fmt_cmp(btc, avg_btc, '배')}",
        f"• 간접낙찰: {_fmt_cmp(indirect, avg_indirect, '%')}",
        f"• 직접낙찰: {_fmt_cmp(direct, avg_direct, '%')}",
        f"• Primary Dealer 인수: {_fmt_cmp(dealer, avg_dealer, '%')}",
        f"• 판정: <b>{auction_verdict}</b>" + (f" · 비교 표본 직전 {n}회" if n else ""),
        "• 입찰 꼬리는 실시간 WI 원천이 공식 API에 없으므로 이 결합 알림에서는 임의 추정하지 않습니다. 별도 국채 입찰 알림의 WI 꼬리 판정을 우선합니다.",
        f'<a href="{TREASURY_AUCTION_QUERY}">미 재무부 30년물 입찰 원천</a>',
    ]
    return lines


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

    cap_use_f = float(cap_use) if cap_use is not None else None
    multiple_f = float(multiple) if multiple is not None else None
    icon, strength = _execution_strength(cap_use_f, multiple_f)

    if accepted is not None and maximum is not None:
        title = f"{icon} 미 재무부 장기물 바이백 실제 집행 — 상한 소진율 {cap_use_f:.1f}%" if cap_use_f is not None else "🇺🇸 미 재무부 장기물 바이백 — 실제 집행 결과 변경"
    else:
        title = "🇺🇸 미 재무부 장기물 바이백 — 실제 집행 결과 변경"

    lines = [
        "<b>🎯 핵심 판단</b>",
        f"{icon} <b>{strength}</b>",
        "• 이 알림은 정책 발표나 기사만으로 보내지 않고 <b>TreasuryDirect 공식 실제 바이백 결과가 바뀌었을 때만</b> 전송합니다.",
        "",
        "<b>실제 집행 숫자</b>",
        f"• 총 제시액: {_fmt_usd_krw(float(offered) if offered is not None else None, fx)}",
        f"• 실제 매입액: {_fmt_usd_krw(float(accepted) if accepted is not None else None, fx)}",
        f"• 매입상한: {_fmt_usd_krw(float(maximum) if maximum is not None else None, fx)}",
    ]
    if cap_use is not None:
        lines.append(f"• 상한 소진율: <b>{float(cap_use):.1f}%</b>")
    if accept_pct is not None:
        lines.append(f"• 제시액 대비 매입률: {float(accept_pct):.1f}%")
    if multiple is not None:
        lines.append(f"• 제시액 ÷ 상한: {float(multiple):.2f}배")

    if maximum is not None and 5_500_000_000 <= float(maximum) <= 6_500_000_000:
        lines += [
            f"• 기존 20억달러 대비 상한: <b>3배</b> — 20억달러({_fmt_krw_from_usd(2_000_000_000, fx)}) → 60억달러({_fmt_krw_from_usd(6_000_000_000, fx)})",
        ]

    lines.extend(_sep10_market_context(float(maximum) if maximum is not None else None))

    lines += [
        "",
        "<b>해석 규칙</b>",
        "• 상한 소진율↑ + 제시액÷상한↑ → 재무부가 확대된 한도를 적극 사용했고 시장의 비지표 장기물 매도 제시도 많았다는 뜻입니다.",
        "• 상한 소진율↓ → ‘60억달러’ 헤드라인보다 실제 흡수 규모가 작았다는 뜻입니다.",
        "• 다만 상한을 거의 다 써도 10·30년 금리가 계속 오르면 <b>유동성 개선보다 유가·인플레이션·재정 공급·기간 프리미엄이 더 강한 실패 경로</b>로 봅니다.",
        "",
        "<b>다음 확인</b>",
        "① 집행 직후 10·20·30년 금리 — 발표 전 기준선 대비 실제 하락 여부",
        "② 30년물 입찰 — Bid-to-Cover·간접낙찰·직접낙찰·Primary Dealer 인수",
        "③ 결제일 TGA — 바이백 결제 뒤 실제 현금 감소 여부",
        "④ 이후 Bill·CMB — TGA 재충전 과정에서 단기물 공급으로 부담이 이동하는지",
        "⑤ 다음 QRA — 장기 바이백 상한·횟수와 쿠폰채 발행 가이던스가 다시 변하는지",
        "",
        "<b>중복 제거</b>",
        "• 바이백 확대·축소 발표와 잠정 일정 변경 → 기존 ‘정책’ 감시가 담당",
        "• 실제 매입 결과 → 이 ‘집행’ 감시가 담당",
        "• 20·30년 입찰 전체 분석과 WI 꼬리 → 기존 국채 입찰 알림이 담당",
        "• 같은 사건을 기사 제목만 바꿔 다시 보내지 않습니다.",
        "",
        f"환율 기준: {fx_date}, 1달러={fx:,.2f}원",
        f'<a href="{watcher.BUYBACK_RESULTS_PAGE}">미 재무부 공식 바이백 결과</a> · <a href="{TREASURY_AUCTION_QUERY}">미 재무부 국채 입찰</a> · <a href="{SEP9_BUYBACK_REUTERS}">60억달러 공지 검증</a> · <a href="{SEP9_MARKET_REUTERS}">시장 반응 검증</a>',
    ]
    body = "\n".join(lines)
    detail = {
        "fx": fx,
        "fx_date": fx_date,
        "buyback_stats": stats,
        "results_changed": bool(results_changed),
        "schedule_changed_suppressed": bool(schedule_changed),
        "mode": "execution_results_only",
        "execution_strength": strength,
        "format_revision": watcher.FORMAT_REVISION,
    }
    return title, body, detail


watcher.digest = _stable_results_digest
watcher.news_items = news_items_execution_only
watcher.load_state = load_state_execution_only
watcher.build_alert = build_execution_alert

if __name__ == "__main__":
    raise SystemExit(watcher.main())
