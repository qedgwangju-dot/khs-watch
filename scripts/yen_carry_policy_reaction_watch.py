#!/usr/bin/env python3
"""Track BOJ policy changes against the subsequent USD/JPY response.

This event-reaction lane is separate from the fast yen-shock and structural
real-rate lanes. It does not duplicate the BOJ decision alert. A new BOJ hike
silently arms a six-hour USD/JPY reaction window.

Thresholds:
- USD/JPY +0.75% vs the pre-event monitor price: yellow policy-effect warning.
- USD/JPY +1.00%: orange escalation.
- First run at/after six hours: one final assessment.
- Fed and BOJ policy changes over the previous seven days are netted so
  synchronized global tightening is not mislabeled as a pure BOJ failure.
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import pathlib
from zoneinfo import ZoneInfo

KST = ZoneInfo("Asia/Seoul")
ROOT = pathlib.Path(__file__).resolve().parents[1]
DATA = ROOT / "data"
OUT = ROOT / "out"
DATA.mkdir(exist_ok=True)
OUT.mkdir(exist_ok=True)

COMPOSITE_STATE = DATA / "yen_carry_composite_state.json"
COMPOSITE_PENDING = OUT / "yen_carry_composite_pending_state.json"

STATE_PATH = DATA / "yen_carry_policy_reaction_state.json"
PENDING_PATH = OUT / "yen_carry_policy_reaction_pending_state.json"
CONTEXT_JSON = OUT / "yen_carry_policy_reaction_context.json"
CONTEXT_MD = OUT / "yen_carry_policy_reaction_context.md"
ALERT_TITLE = OUT / "yen_carry_policy_reaction_alert_title.txt"
ALERT_BODY = OUT / "yen_carry_policy_reaction_alert.md"
CONFIRMED = OUT / "yen_carry_policy_reaction_telegram_confirmed.json"

BOJ_SOURCE = "https://www.boj.or.jp/en/mopo/mpmdeci/state_2026/index.htm"
FED_SOURCE = "https://www.federalreserve.gov/newsevents/pressreleases/2026-press-fomc.htm"
YAHOO_SOURCE = "https://finance.yahoo.com/quote/JPY=X/"

TRACK_MINUTES = 6 * 60
RECENT_POLICY_DAYS = 7
WARNING_YEN_WEAK_PCT = 0.75
SEVERE_YEN_WEAK_PCT = 1.00
CONFIRMED_YEN_STRONG_PCT = -0.50
RELATIVE_POLICY_NEUTRAL_PP = 0.10
POLICY_DELTA_EPSILON = 0.001


def load_json(path: pathlib.Path, default):
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
        return value if isinstance(value, type(default)) else default
    except Exception:
        return default


def write_json(path: pathlib.Path, value: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def num(value):
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def parse_time(value) -> dt.datetime | None:
    text = str(value or "").strip()
    if not text:
        return None
    try:
        parsed = dt.datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=KST)
    return parsed.astimezone(KST)


def current_policy_rates(composite: dict) -> dict | None:
    real = composite.get("real_rate_overlay") or {}
    if not real.get("available"):
        return None
    inputs = real.get("inputs") or {}
    fed = num(inputs.get("fed_midpoint"))
    boj = num(inputs.get("boj_policy_rate"))
    if fed is None or boj is None:
        return None
    return {"fed_midpoint": fed, "boj_policy_rate": boj}


def fresh_fx_price(composite: dict) -> float | None:
    if not composite.get("fx_signal_eligible"):
        return None
    return num((composite.get("values") or {}).get("usdjpy"))


def policy_event(bank: str, delta: float, old: float, new: float, now: dt.datetime) -> dict:
    return {
        "bank": bank,
        "delta_pp": delta,
        "from_rate": old,
        "to_rate": new,
        "detected_at_kst": now.astimezone(KST).isoformat(timespec="seconds"),
    }


def prune_events(events: list[dict], now: dt.datetime) -> list[dict]:
    cutoff = now.astimezone(KST) - dt.timedelta(days=RECENT_POLICY_DAYS)
    out: list[dict] = []
    for event in events:
        when = parse_time(event.get("detected_at_kst"))
        if when is not None and when >= cutoff:
            out.append(event)
    return out


def relative_policy_change(events: list[dict]) -> tuple[float, float, float]:
    fed = sum(float(event.get("delta_pp") or 0.0) for event in events if event.get("bank") == "Fed")
    boj = sum(float(event.get("delta_pp") or 0.0) for event in events if event.get("bank") == "BOJ")
    return fed, boj, fed - boj


def relative_policy_label(net_gap_change_pp: float) -> str:
    if net_gap_change_pp >= RELATIVE_POLICY_NEUTRAL_PP:
        return "Fed 상대 긴축 우위 — 엔화 약세 압력"
    if net_gap_change_pp <= -RELATIVE_POLICY_NEUTRAL_PP:
        return "BOJ 상대 긴축 우위 — 엔화 강세 지원"
    return "Fed·BOJ 최근 정책변화 대체로 상쇄"


def select_baseline(previous_composite: dict, current_composite: dict, now: dt.datetime) -> tuple[float | None, str | None, str]:
    prev_px = fresh_fx_price(previous_composite)
    if prev_px is not None:
        stamp = previous_composite.get("updated_at_kst")
        return prev_px, str(stamp or ""), "직전 정상 감시값"
    current_px = fresh_fx_price(current_composite)
    if current_px is not None:
        return current_px, now.astimezone(KST).isoformat(timespec="seconds"), "정책변화 감지 후 첫 정상값"
    return None, None, "기준 환율 확인 불가"


def arm_boj_event(
    *,
    old_rate: float,
    new_rate: float,
    delta: float,
    previous_composite: dict,
    current_composite: dict,
    now: dt.datetime,
) -> dict:
    baseline, baseline_at, baseline_kind = select_baseline(previous_composite, current_composite, now)
    values = previous_composite.get("values") or {}
    baseline_spread = num(values.get("us_jp_2y_spread"))
    return {
        "id": f"BOJ-{now.astimezone(KST).strftime('%Y%m%dT%H%M%S')}-{new_rate:.3f}",
        "bank": "BOJ",
        "from_rate": old_rate,
        "to_rate": new_rate,
        "delta_pp": delta,
        "detected_at_kst": now.astimezone(KST).isoformat(timespec="seconds"),
        "baseline_usdjpy": baseline,
        "baseline_at_kst": baseline_at,
        "baseline_kind": baseline_kind,
        "baseline_us_jp_2y_spread": baseline_spread,
        "max_opposite_level_sent": 0,
        "final_sent": False,
        "last_reaction_pct": None,
        "last_elapsed_minutes": 0.0,
    }


def reaction_snapshot(active: dict, composite: dict, recent_events: list[dict], now: dt.datetime) -> dict:
    detected = parse_time(active.get("detected_at_kst")) or now.astimezone(KST)
    elapsed = max(0.0, (now.astimezone(KST) - detected).total_seconds() / 60.0)
    current_px = fresh_fx_price(composite)
    baseline_px = num(active.get("baseline_usdjpy"))

    if baseline_px is None and current_px is not None:
        active["baseline_usdjpy"] = current_px
        active["baseline_at_kst"] = now.astimezone(KST).isoformat(timespec="seconds")
        active["baseline_kind"] = "정책변화 감지 후 첫 정상값"
        baseline_px = current_px

    reaction = None
    if current_px is not None and baseline_px is not None and baseline_px > 0:
        reaction = (current_px / baseline_px - 1.0) * 100.0

    current_spread = num((composite.get("values") or {}).get("us_jp_2y_spread"))
    baseline_spread = num(active.get("baseline_us_jp_2y_spread"))
    spread_change_bp = None
    if current_spread is not None and baseline_spread is not None:
        spread_change_bp = (current_spread - baseline_spread) * 100.0

    fed7, boj7, net7 = relative_policy_change(recent_events)
    real = composite.get("real_rate_overlay") or {}
    metrics = real.get("metrics") or {}
    real_gap = num(metrics.get("us_jp_real_gap"))
    real_gap_change = num(metrics.get("real_gap_change_pp"))
    real_direction = str(metrics.get("real_rate_direction") or "확인 대기")
    market_direction = str(metrics.get("market_rate_direction") or "확인 대기")
    signal_alignment = str(metrics.get("signal_alignment") or "확인 대기")

    conflict = bool(
        reaction is not None
        and reaction >= WARNING_YEN_WEAK_PCT
        and (
            (real_gap_change is not None and real_gap_change <= -0.10)
            or real_direction == "엔화 강세 방향"
            or net7 <= -RELATIVE_POLICY_NEUTRAL_PP
        )
    )

    return {
        "elapsed_minutes": elapsed,
        "baseline_usdjpy": baseline_px,
        "current_usdjpy": current_px,
        "reaction_pct": reaction,
        "current_us_jp_2y_spread": current_spread,
        "spread_change_bp": spread_change_bp,
        "fed_change_7d_pp": fed7,
        "boj_change_7d_pp": boj7,
        "net_policy_gap_change_7d_pp": net7,
        "relative_policy_label": relative_policy_label(net7),
        "us_jp_real_gap": real_gap,
        "real_gap_change_pp": real_gap_change,
        "real_rate_direction": real_direction,
        "market_rate_direction": market_direction,
        "signal_alignment": signal_alignment,
        "signal_conflict": conflict,
        "fx_fresh": current_px is not None,
    }


def final_label(snapshot: dict) -> str:
    reaction = num(snapshot.get("reaction_pct"))
    if reaction is None:
        return "6시간 환율 반응 확인 불가"
    net7 = float(snapshot.get("net_policy_gap_change_7d_pp") or 0.0)
    if reaction >= WARNING_YEN_WEAK_PCT:
        if net7 <= -RELATIVE_POLICY_NEUTRAL_PP or snapshot.get("signal_conflict"):
            return "정책 효과 불발·신호 충돌"
        if abs(net7) < RELATIVE_POLICY_NEUTRAL_PP:
            return "정책 효과 제한 — Fed·BOJ 상대 긴축 상쇄"
        return "정책 효과 불발 — 엔화 약세 지속"
    if reaction <= CONFIRMED_YEN_STRONG_PCT:
        return "정책 효과 확인 — 엔화 강세 반응"
    return "정책 효과 제한·미확인"


def alert_decision(active: dict, snapshot: dict) -> tuple[str | None, int]:
    reaction = num(snapshot.get("reaction_pct"))
    elapsed = float(snapshot.get("elapsed_minutes") or 0.0)
    if reaction is None:
        return None, 0

    if elapsed >= TRACK_MINUTES and not active.get("final_sent"):
        return "final", 1

    sent = int(active.get("max_opposite_level_sent") or 0)
    if reaction >= SEVERE_YEN_WEAK_PCT and sent < 2:
        return "severe", 2
    if reaction >= WARNING_YEN_WEAK_PCT and sent < 1:
        return "warning", 1
    return None, 0


def format_bp(delta_pp: float) -> str:
    return f"{delta_pp * 100:+.0f}bp"


def build_alert(active: dict, snapshot: dict, mode: str, now: dt.datetime) -> tuple[str, str]:
    reaction = float(snapshot.get("reaction_pct") or 0.0)
    if mode == "severe":
        title = f"🟠 BOJ 정책 ↔ 엔화 반응 괴리 — USD/JPY {reaction:+.2f}%"
        verdict = "정책 효과 불발 경계 강화"
    elif mode == "warning":
        title = f"🟡 BOJ 정책 효과 불발 경계 — USD/JPY {reaction:+.2f}%"
        verdict = "BOJ 인상 뒤 엔화가 오히려 약세"
    else:
        verdict = final_label(snapshot)
        if reaction >= WARNING_YEN_WEAK_PCT:
            emoji = "🟠" if reaction >= SEVERE_YEN_WEAK_PCT else "🟡"
        elif reaction <= CONFIRMED_YEN_STRONG_PCT:
            emoji = "🟢"
        else:
            emoji = "🟡"
        title = f"{emoji} BOJ 정책 6시간 반응 — {verdict}"

    elapsed = float(snapshot.get("elapsed_minutes") or 0.0)
    fed7 = float(snapshot.get("fed_change_7d_pp") or 0.0)
    boj7 = float(snapshot.get("boj_change_7d_pp") or 0.0)
    net7 = float(snapshot.get("net_policy_gap_change_7d_pp") or 0.0)
    real_gap = snapshot.get("us_jp_real_gap")
    real_change = snapshot.get("real_gap_change_pp")
    spread_change = snapshot.get("spread_change_bp")

    lines = [
        f"조회 시각: {now.astimezone(KST).strftime('%Y-%m-%d %H:%M:%S KST')}",
        "",
        "판정",
        f"- BOJ 정책 반응: {verdict}",
        f"- 신호 충돌: {'예' if snapshot.get('signal_conflict') else '아니오'}",
        "",
        "정책 변화",
        f"- BOJ 정책금리: {float(active.get('from_rate') or 0):.2f}% → {float(active.get('to_rate') or 0):.2f}% ({format_bp(float(active.get('delta_pp') or 0))})",
        f"- 최근 7일 Fed 정책변화: {format_bp(fed7)} / BOJ 정책변화: {format_bp(boj7)}",
        f"- 최근 7일 Fed-BOJ 상대 정책격차 변화: {net7:+.2f}%p → {snapshot.get('relative_policy_label')}",
        "",
        "USD/JPY 정책 반응",
        f"- 기준: {float(snapshot.get('baseline_usdjpy') or 0):.3f} ({active.get('baseline_at_kst') or '시각 확인 불가'}, {active.get('baseline_kind')})",
        f"- 현재: {float(snapshot.get('current_usdjpy') or 0):.3f}",
        f"- 경과 {elapsed:.0f}분: {reaction:+.2f}% (USD/JPY 상승 = 엔화 약세)",
    ]
    if spread_change is not None:
        lines.append(f"- 미·일 2년 금리차: 기준 대비 {float(spread_change):+.1f}bp")
    lines += ["", "실질금리·시장금리"]
    if real_gap is not None:
        lines.append(
            f"- 미·일 사후 실질정책금리 갭: {float(real_gap):+.2f}%p"
            + (f" / 직전 공식 이벤트 대비 {float(real_change):+.2f}%p" if real_change is not None else "")
        )
    else:
        lines.append("- 미·일 사후 실질정책금리 갭: 확인 불가")
    lines.append(
        f"- 신호 비교: 실질금리 {snapshot.get('real_rate_direction')} / "
        f"미·일 2년 금리 {snapshot.get('market_rate_direction')} → {snapshot.get('signal_alignment')}"
    )
    lines += [
        "",
        "해석",
        "- BOJ 인상 그 자체보다 Fed 대비 상대 정상화 속도와 실제 USD/JPY 반응을 우선 확인합니다.",
        "- BOJ가 상대적으로 더 긴축했는데도 USD/JPY가 +0.75% 이상 오르면 정책 효과 불발·신호 충돌로 봅니다.",
        "- Fed와 BOJ가 비슷한 폭으로 함께 올렸다면 엔화 약세를 순수한 BOJ 실패로 단정하지 않고 상대 긴축 상쇄로 구분합니다.",
        "",
        "출처",
        f"- BOJ 정책결정: {BOJ_SOURCE}",
        f"- Fed FOMC: {FED_SOURCE}",
        f"- USD/JPY 정책반응: {YAHOO_SOURCE}",
    ]
    return title, "\n".join(lines)


def context_markdown(state: dict) -> str:
    active = state.get("active_event")
    events = state.get("recent_policy_events") or []
    fed7, boj7, net7 = relative_policy_change(events)
    lines = [
        "# BOJ 정책 ↔ 엔화 반응 감시",
        "",
        f"- 조회시각(KST): {state.get('updated_at_kst')}",
        f"- 최근 7일 Fed 정책변화: {format_bp(fed7)}",
        f"- 최근 7일 BOJ 정책변화: {format_bp(boj7)}",
        f"- 상대 정책격차 변화: {net7:+.2f}%p ({relative_policy_label(net7)})",
    ]
    if active:
        snap = state.get("reaction_snapshot") or {}
        lines += [
            f"- BOJ 6시간 반응 추적: 진행 중 ({float(snap.get('elapsed_minutes') or 0):.0f}분 경과)",
            f"- 기준 USD/JPY: {active.get('baseline_usdjpy')}",
            f"- 현재 반응: {snap.get('reaction_pct')}",
            f"- 최종판정 전송: {'예' if active.get('final_sent') else '아니오'}",
        ]
    else:
        lines.append("- BOJ 6시간 반응 추적: 대기")
    lines += [
        "",
        "※ 정책결정 자체는 기존 중앙은행 알림에 맡기고, 여기서는 실제 엔화 반응의 확인·불발·충돌만 감시합니다.",
    ]
    return "\n".join(lines) + "\n"


def evaluate(
    previous: dict,
    previous_composite: dict,
    current_composite: dict,
    now: dt.datetime,
) -> tuple[dict, str | None, str | None]:
    rates = current_policy_rates(current_composite)
    if rates is None:
        state = dict(previous) if previous else {}
        state.update({
            "initialized": bool(previous.get("initialized")),
            "updated_at_kst": now.astimezone(KST).isoformat(timespec="seconds"),
            "error": "실질금리 공식 입력 미확인 — 정책반응 감시 상태 유지",
        })
        return state, None, None

    if not previous.get("initialized"):
        state = {
            "initialized": True,
            "updated_at_kst": now.astimezone(KST).isoformat(timespec="seconds"),
            "last_policy_rates": rates,
            "recent_policy_events": [],
            "active_event": None,
            "reaction_snapshot": None,
        }
        return state, None, None

    state = dict(previous)
    state.pop("error", None)
    events = prune_events(list(previous.get("recent_policy_events") or []), now)
    prev_rates = previous.get("last_policy_rates") or rates
    prev_fed = num(prev_rates.get("fed_midpoint"))
    prev_boj = num(prev_rates.get("boj_policy_rate"))
    fed = rates["fed_midpoint"]
    boj = rates["boj_policy_rate"]

    if prev_fed is not None and abs(fed - prev_fed) >= POLICY_DELTA_EPSILON:
        events.append(policy_event("Fed", fed - prev_fed, prev_fed, fed, now))
    new_boj_hike = False
    if prev_boj is not None and abs(boj - prev_boj) >= POLICY_DELTA_EPSILON:
        delta = boj - prev_boj
        events.append(policy_event("BOJ", delta, prev_boj, boj, now))
        if delta > 0:
            state["active_event"] = arm_boj_event(
                old_rate=prev_boj,
                new_rate=boj,
                delta=delta,
                previous_composite=previous_composite,
                current_composite=current_composite,
                now=now,
            )
            new_boj_hike = True

    events = prune_events(events, now)
    active = state.get("active_event")
    alert_title = None
    alert_body = None
    snapshot = None

    if active:
        snapshot = reaction_snapshot(active, current_composite, events, now)
        active["last_reaction_pct"] = snapshot.get("reaction_pct")
        active["last_elapsed_minutes"] = snapshot.get("elapsed_minutes")
        mode, level = alert_decision(active, snapshot)
        if mode:
            alert_title, alert_body = build_alert(active, snapshot, mode, now)
            if mode == "final":
                active["final_sent"] = True
            else:
                active["max_opposite_level_sent"] = max(
                    int(active.get("max_opposite_level_sent") or 0), level
                )
        if active.get("final_sent") and float(snapshot.get("elapsed_minutes") or 0) >= TRACK_MINUTES + 30:
            active = None
            state["active_event"] = None
        else:
            state["active_event"] = active

    state.update({
        "initialized": True,
        "updated_at_kst": now.astimezone(KST).isoformat(timespec="seconds"),
        "last_policy_rates": rates,
        "recent_policy_events": events,
        "reaction_snapshot": snapshot,
        "new_boj_hike_detected": new_boj_hike,
    })
    return state, alert_title, alert_body


def finalize() -> int:
    if not PENDING_PATH.exists():
        return 0
    if ALERT_BODY.exists() and not CONFIRMED.exists():
        print("policy_reaction_state_not_advanced=telegram_unconfirmed")
        return 0
    STATE_PATH.write_text(PENDING_PATH.read_text(encoding="utf-8"), encoding="utf-8")
    print("policy_reaction_state_finalized=true")
    return 0


def clean_outputs() -> None:
    for path in (ALERT_TITLE, ALERT_BODY, CONFIRMED):
        path.unlink(missing_ok=True)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--finalize", action="store_true")
    args = parser.parse_args()
    if args.finalize:
        return finalize()

    clean_outputs()
    now = dt.datetime.now(KST)
    previous = load_json(STATE_PATH, {})
    previous_composite = load_json(COMPOSITE_STATE, {})
    current_composite = load_json(COMPOSITE_PENDING, {})
    if not current_composite:
        print("policy reaction watch: composite pending state missing")
        return 0

    state, title, body = evaluate(previous, previous_composite, current_composite, now)
    write_json(PENDING_PATH, state)
    write_json(CONTEXT_JSON, state)
    CONTEXT_MD.write_text(context_markdown(state), encoding="utf-8")

    if title and body:
        ALERT_TITLE.write_text(title + "\n", encoding="utf-8")
        ALERT_BODY.write_text(body.rstrip() + "\n", encoding="utf-8")
        print(f"policy_reaction_alert=true title={title}")
    else:
        print("policy_reaction_alert=false")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
