#!/usr/bin/env python3
"""Final audit and deduplication layer for the Treasury CTA squeeze alert.

The underlying watcher still collects every input on schedule, but Telegram is now gated:
- no alert for a new media quote alone
- no alert for a CFTC weekly refresh alone
- no alert for a 10Y yield bucket move alone
- alert only when futures short-cover evidence is confirmed by positioning/trend evidence
  without a material repo deterioration, then only again when the same episode strengthens.
"""
from __future__ import annotations

import json
import re

import treasury_cta_squeeze_watch as watcher
import treasury_cta_squeeze_market_watch  # noqa: F401  # installs resilient market-data formatter

watcher.FORMAT_REVISION = max(int(getattr(watcher, "FORMAT_REVISION", 0)), 7)

SECONDARY_CTA_SOURCE = "https://a.foresightnews.pro/article/detail/99813"

_base_format = watcher.format_alert


def _krw_per_bp(usd_dv01: float, fx: float) -> str:
    won = usd_dv01 * fx
    if won >= 100_000_000:
        return f"약 {won / 100_000_000:,.0f}억원/bp"
    return f"약 {won:,.0f}원/bp"


def format_alert(snapshot, previous, fx, fx_date, reasons):
    title, body = _base_format(snapshot, previous, fx, fx_date, reasons)

    marker = "<b>1️⃣ Goldman CTA DV01 — 스퀴즈의 연료</b>\n"
    baseline = (
        f"• <b>2차 출처 기준선:</b> 글로벌 채권 CTA 순숏 약 1억5,500만달러 DV01"
        f"(1bp당 {_krw_per_bp(155_000_000, fx)})\n"
        f"• 채권가격이 1개월 내 +2σ 상승할 경우 약 1억5,000만달러 DV01"
        f"(1bp당 {_krw_per_bp(150_000_000, fx)}) 규모의 환매·재매수 추정\n"
        "• 위 수치는 Goldman Futures Desk를 인용한 2차 출처 기준선이며 Goldman 공개 공식 피드로 직접 검증된 값은 아닙니다.\n"
    )
    if marker in body and "2차 출처 기준선:" not in body:
        body = body.replace(marker, marker + baseline, 1)

    body = body.replace(
        "<b>3️⃣ TY/US/WN 대응 CME 선물 — 가격 + 미결제약정</b>",
        "<b>3️⃣ TY/US/WN 선물 — 가격 + CFTC 주간 전체 시장 OI</b>",
    )
    oi_note = (
        "※ 현재 OI가 CFTC 주간 전체 시장 OI로 표시되는 경우 <b>당일 실시간 OI가 아닙니다.</b> "
        "따라서 가격↑·OI↓는 다음 CFTC 갱신에서 확인되는 주간 숏커버 확인 신호로만 사용합니다."
    )
    section3 = "<b>3️⃣ TY/US/WN 선물 — 가격 + CFTC 주간 전체 시장 OI</b>"
    if section3 in body and oi_note not in body:
        body = body.replace(section3, section3 + "\n" + oi_note, 1)

    y = snapshot.get("yield10") or {}
    if y.get("yield") is not None:
        distance = max(0.0, (float(y["yield"]) - 4.30) * 100)
        body = re.sub(
            r"• 현재 공식 10년물 [0-9.]+% → 4\.30%까지 [+-]?[0-9.]+bp",
            f"• 현재 공식 10년물 {float(y['yield']):.3f}% → 4.30%까지 <b>{distance:.1f}bp 하락 필요</b>",
            body,
            count=1,
        )

    daily_note = (
        "※ 미 재무부 공식 10년물은 일일 고시값입니다. 15분 감시의 장중 방향은 선물가격으로 보고, "
        "4.50·4.40·4.35·4.30% 공식 경보선 확정은 재무부 고시값으로 잠급니다."
    )
    sec6 = "<b>6️⃣ 10년물 4.3% 접근</b>"
    if sec6 in body and daily_note not in body:
        body = body.replace(sec6, sec6 + "\n" + daily_note, 1)

    gate_note = (
        "\n<b>🔕 중복 제거 규칙</b>\n"
        "• 신규 기사 한 건, CFTC 주간 갱신 한 건, 10년물 구간 변화 한 건만으로는 텔레그램을 보내지 않습니다.\n"
        "• <b>선물 가격↑·OI↓ + (CFTC 숏 축소 또는 -1σ 이하) + repo 비악화</b>가 겹칠 때만 실제 스퀴즈 단계 알림을 보냅니다."
    )
    if "🔕 중복 제거 규칙" not in body:
        body += gate_note

    if "CTA 2차 출처" not in body:
        body += f'\n<a href="{SECONDARY_CTA_SOURCE}">CTA 2차 출처</a>'

    return title, body


def _cftc_short_reduction(current: dict, previous: dict) -> tuple[bool, list[str]]:
    curr = (current.get("cftc") or {}).get("markets", {})
    prev = (previous.get("cftc") or {}).get("markets", {})
    lines: list[str] = []
    for key in ("10Y", "BOND", "ULTRABOND"):
        c = curr.get(key) or {}
        p = prev.get(key) or {}
        c_short = c.get("leveraged_short")
        p_short = p.get("leveraged_short")
        if c_short is None or p_short is None:
            continue
        if int(c_short) < int(p_short):
            lines.append(f"{key} Leveraged Funds 숏 {int(p_short):,}→{int(c_short):,}계약")
    return bool(lines), lines


def _repo_not_worse(current: dict, previous: dict) -> tuple[bool, list[str]]:
    curr = current.get("repo") or {}
    prev = previous.get("repo") or {}
    worsened: list[str] = []
    for key in ("SOFR", "BGCR", "TGCR"):
        c = (curr.get(key) or {}).get("rate")
        p = (prev.get(key) or {}).get("rate")
        if c is None or p is None:
            continue
        # +10bp 이상이면 펀딩 스트레스 악화로 간주해 스퀴즈 확인 알림을 보류.
        if float(c) - float(p) >= 0.10:
            worsened.append(f"{key} {float(p):.2f}%→{float(c):.2f}%")
    return not worsened, worsened


def deduped_main() -> int:
    watcher.DATA.mkdir(parents=True, exist_ok=True)
    watcher.OUT.mkdir(parents=True, exist_ok=True)
    for p in (watcher.ALERT, watcher.TITLE, watcher.DETAIL):
        try:
            p.unlink()
        except FileNotFoundError:
            pass

    state = watcher.load_state()
    fx, fx_date = watcher.latest_fx()
    snapshot = {
        "checked_kst": watcher.datetime.now(watcher.KST).isoformat(timespec="seconds"),
        "cta_media": watcher.cta_news(),
        "cftc": watcher.cftc_snapshot(),
        "cme": watcher.cme_snapshot(),
        "yield10": watcher.treasury_10y_snapshot(),
        "repo": watcher.repo_snapshot(),
        "format_revision": watcher.FORMAT_REVISION,
    }

    prev_snapshot = state.get("snapshot") or {}
    cftc_date = snapshot["cftc"].get("report_date")
    prev_cftc_date = state.get("cftc_date")

    media_id = None
    if snapshot.get("cta_media"):
        media_id = snapshot["cta_media"].get("link") or snapshot["cta_media"].get("title")

    short_bias_active = bool(state.get("short_bias_active", False))
    short_reduction_lines: list[str] = []
    if prev_cftc_date and cftc_date != prev_cftc_date:
        short_bias_active, short_reduction_lines = _cftc_short_reduction(snapshot, prev_snapshot)

    evidence = watcher.squeeze_evidence(snapshot, prev_snapshot)
    z = float(snapshot["yield10"]["z20"])
    z_active = z <= -1.0
    repo_ok, repo_worsened = _repo_not_worse(snapshot, prev_snapshot)

    composite_confirmed = bool(evidence and (short_bias_active or z_active) and repo_ok)

    y = float(snapshot["yield10"]["yield"])
    stage = 0
    if composite_confirmed:
        stage = 1
        if z <= -2.0:
            stage = max(stage, 2)
        if y <= 4.35:
            stage = max(stage, 3)
        if y <= 4.30:
            stage = max(stage, 4)

    prev_episode_active = bool(state.get("episode_active", False))
    prev_stage = int(state.get("episode_stage", 0) or 0) if prev_episode_active else 0
    should_alert = bool(composite_confirmed and (not prev_episode_active or stage > prev_stage))

    reasons: list[str] = []
    if should_alert:
        reasons.append("선물 가격↑ + OI↓ 숏커버 확인")
        if short_bias_active:
            if short_reduction_lines:
                reasons.append("CFTC 숏 축소: " + ", ".join(short_reduction_lines))
            else:
                reasons.append("최근 CFTC 주간 숏 축소 상태 유지")
        if z_active:
            reasons.append(f"10년물 추세 프록시 {z:+.2f}σ")
        reasons.append("repo 스트레스 비악화")
        if stage >= 4:
            reasons.append("10년물 4.30% 이하 단계")
        elif stage >= 3:
            reasons.append("10년물 4.35% 이하 단계")
        elif stage >= 2:
            reasons.append("-2σ 이하 강화 단계")
        else:
            reasons.append("복합 스퀴즈 1차 확인")

    if composite_confirmed:
        episode_active = True
        episode_stage = max(stage, prev_stage if prev_episode_active else 0)
    else:
        episode_active = False
        episode_stage = 0

    bucket = watcher.threshold_bucket(y)
    next_state = {
        **state,
        "last_checked_kst": snapshot["checked_kst"],
        "media_id": media_id,
        "cftc_date": cftc_date,
        "yield_bucket": bucket,
        "snapshot": snapshot,
        "format_revision": watcher.FORMAT_REVISION,
        "short_bias_active": short_bias_active,
        "episode_active": episode_active,
        "episode_stage": episode_stage,
        "last_gate": {
            "futures_price_oi": bool(evidence),
            "cftc_short_bias": short_bias_active,
            "z_below_minus_1": z_active,
            "repo_not_worse": repo_ok,
            "composite_confirmed": composite_confirmed,
            "stage": stage,
        },
    }

    if should_alert:
        title, body = format_alert(snapshot, prev_snapshot, fx, fx_date, reasons)
        if len(title) + 2 + len(body) > 4096:
            raise RuntimeError(f"Telegram message too long: {len(title)+2+len(body)}")
        watcher.TITLE.write_text(title + "\n", encoding="utf-8")
        watcher.ALERT.write_text(body + "\n", encoding="utf-8")
        detail = {
            **snapshot,
            "dedupe_gate": next_state["last_gate"],
            "alert_reasons": reasons,
        }
        watcher.DETAIL.write_text(json.dumps(detail, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    suppressed = []
    if media_id and media_id != state.get("media_id"):
        suppressed.append("신규 CTA/Goldman 인용 단독")
    if prev_cftc_date and cftc_date != prev_cftc_date and not short_bias_active:
        suppressed.append("CFTC 주간 갱신 단독")
    prev_bucket = state.get("yield_bucket")
    if prev_bucket and bucket != prev_bucket and not should_alert:
        suppressed.append("10년물 경보구간 변화 단독")
    if repo_worsened:
        suppressed.append("repo 10bp 이상 악화로 복합 확인 보류")

    watcher.NEXT_STATE.write_text(json.dumps(next_state, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    watcher.STATUS.write_text(
        "# 미 국채 CTA 숏 스퀴즈 감시 — 중복 제거 모드\n\n"
        f"- 조회시각: {snapshot['checked_kst']}\n"
        f"- CFTC 기준일: {cftc_date}\n"
        f"- 10년물: {y:.3f}% / {bucket}\n"
        f"- 20일 z: {z:+.2f}σ\n"
        f"- 선물 가격↑·OI↓: {'확인' if evidence else '미확인'}\n"
        f"- 최근 CFTC 숏 축소: {'확인' if short_bias_active else '미확인'}\n"
        f"- repo 비악화: {'확인' if repo_ok else '미확인'}\n"
        f"- 복합 스퀴즈: {'확인' if composite_confirmed else '미확인'} / 단계 {stage}\n"
        f"- 텔레그램: {'전송' if should_alert else '미전송'}\n"
        f"- 억제된 단독 신호: {', '.join(suppressed) if suppressed else '없음'}\n",
        encoding="utf-8",
    )
    return 0


watcher.format_alert = format_alert
watcher.main = deduped_main

if __name__ == "__main__":
    raise SystemExit(watcher.main())
