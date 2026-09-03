#!/usr/bin/env python3
"""Keep recent yen-strength shocks visible after the immediate move partially rebounds.

This layer separates two different questions:
1) Current shock: is USD/JPY still falling fast enough *now* to imply active unwind pressure?
2) Recent shock: did a >=1% yen-strength shock occur within the last 90 minutes and leave
   a still-material residual move after a partial rebound?

The recent-shock lane is deliberately capped at yellow. It can preserve a warning after
an orange current shock fades, but it cannot by itself promote the alert to orange/red.
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import pathlib
import re
from dataclasses import asdict, dataclass
from zoneinfo import ZoneInfo

import yen_carry_composite_watch as composite
import yen_carry_fx_shock as fx

KST = ZoneInfo("Asia/Seoul")
ROOT = pathlib.Path(__file__).resolve().parents[1]
DATA = ROOT / "data"
OUT = ROOT / "out"
DATA.mkdir(exist_ok=True)
OUT.mkdir(exist_ok=True)

STATE_PATH = DATA / "yen_carry_recent_shock_state.json"
PENDING_PATH = OUT / "yen_carry_recent_shock_pending_state.json"
STATUS_PATH = OUT / "yen_carry_recent_shock_status.md"
ALERT_TITLE = OUT / "yen_carry_composite_alert_title.txt"
ALERT_BODY = OUT / "yen_carry_composite_alert.md"
ALERT_JSON = OUT / "yen_carry_composite_alert.json"
CONFIRMED = OUT / "yen_carry_composite_telegram_confirmed.json"

WINDOW_MINUTES = 90
SHOCK_DRAWDOWN_PCT = -1.00
CURRENT_RESIDUAL_PCT = -1.00
RECENT_RESIDUAL_PCT = -0.50
MAX_CURRENT_REBOUND_PCT = 0.20
NEW_LOW_RE_ALERT_PCT = 0.30

SEVERITY = {"🟢": 0, "🟡": 1, "🟠": 2, "🔴": 3}
EMOJI = {0: "🟢", 1: "🟡", 2: "🟠", 3: "🔴"}


@dataclass(frozen=True)
class ShockSnapshot:
    latest_price: float
    latest_epoch: float
    change_15m_pct: float
    change_30m_pct: float
    peak_price: float
    peak_epoch: float
    trough_price: float
    trough_epoch: float
    max_drawdown_pct: float
    current_rebound_pct: float
    current_vs_peak_pct: float
    trough_age_minutes: float
    current_shock: bool
    recent_shock: bool


def load_json(path: pathlib.Path, default):
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
        return value if isinstance(value, type(default)) else default
    except Exception:
        return default


def recent_peak_to_trough(points: list[tuple[float, float]]) -> tuple[float, float, float, float, float]:
    latest_ts = points[-1][0]
    cutoff = latest_ts - WINDOW_MINUTES * 60
    window = [(ts, px) for ts, px in points if ts >= cutoff]
    if len(window) < 4:
        raise RuntimeError("USD/JPY recent 90-minute observations insufficient")

    peak_ts, peak_px = window[0]
    best_peak_ts, best_peak_px = peak_ts, peak_px
    best_trough_ts, best_trough_px = peak_ts, peak_px
    best_drawdown = 0.0

    for ts, px in window[1:]:
        if px > peak_px:
            peak_ts, peak_px = ts, px
        drawdown = (px / peak_px - 1.0) * 100.0
        if drawdown < best_drawdown:
            best_drawdown = drawdown
            best_peak_ts, best_peak_px = peak_ts, peak_px
            best_trough_ts, best_trough_px = ts, px

    return best_peak_ts, best_peak_px, best_trough_ts, best_trough_px, best_drawdown


def calculate(points: list[tuple[float, float]]) -> ShockSnapshot:
    latest_epoch, latest_price = points[-1]
    _, _, change_15m_pct = fx.rolling_reference(points, 15)
    _, _, change_30m_pct = fx.rolling_reference(points, 30)
    peak_epoch, peak_price, trough_epoch, trough_price, max_drawdown_pct = recent_peak_to_trough(points)

    current_rebound_pct = (latest_price / trough_price - 1.0) * 100.0 if trough_price > 0 else 0.0
    current_vs_peak_pct = (latest_price / peak_price - 1.0) * 100.0 if peak_price > 0 else 0.0
    trough_age_minutes = max(0.0, (latest_epoch - trough_epoch) / 60.0)

    fast_now = (
        change_15m_pct <= fx.FAST_WARNING_THRESHOLDS[15]
        or change_30m_pct <= fx.FAST_WARNING_THRESHOLDS[30]
    )
    residual_now = (
        max_drawdown_pct <= SHOCK_DRAWDOWN_PCT
        and current_vs_peak_pct <= CURRENT_RESIDUAL_PCT
        and current_rebound_pct <= MAX_CURRENT_REBOUND_PCT
    )
    current_shock = bool(fast_now or residual_now)

    recent_shock = bool(
        not current_shock
        and max_drawdown_pct <= SHOCK_DRAWDOWN_PCT
        and trough_age_minutes <= WINDOW_MINUTES
        and current_vs_peak_pct <= RECENT_RESIDUAL_PCT
        and current_rebound_pct > MAX_CURRENT_REBOUND_PCT
    )

    return ShockSnapshot(
        latest_price=latest_price,
        latest_epoch=latest_epoch,
        change_15m_pct=change_15m_pct,
        change_30m_pct=change_30m_pct,
        peak_price=peak_price,
        peak_epoch=peak_epoch,
        trough_price=trough_price,
        trough_epoch=trough_epoch,
        max_drawdown_pct=max_drawdown_pct,
        current_rebound_pct=current_rebound_pct,
        current_vs_peak_pct=current_vs_peak_pct,
        trough_age_minutes=trough_age_minutes,
        current_shock=current_shock,
        recent_shock=recent_shock,
    )


def state_from(snapshot: ShockSnapshot, now: dt.datetime) -> dict:
    return {
        "initialized": True,
        "updated_at_kst": now.astimezone(KST).isoformat(timespec="seconds"),
        "current_shock": snapshot.current_shock,
        "recent_shock": snapshot.recent_shock,
        "values": asdict(snapshot),
    }


def state_change_reasons(previous: dict, current: dict) -> list[str]:
    if not previous.get("initialized"):
        return []
    reasons: list[str] = []
    if bool(previous.get("current_shock")) != bool(current.get("current_shock")):
        reasons.append(
            "현재 충격 진입" if current.get("current_shock") else "현재 충격 완화"
        )
    if bool(previous.get("recent_shock")) != bool(current.get("recent_shock")):
        reasons.append(
            "최근 90분 충격 잔존 진입" if current.get("recent_shock") else "최근 90분 충격 잔존 해제"
        )
    prev_dd = float(((previous.get("values") or {}).get("max_drawdown_pct") or 0.0))
    cur_dd = float(((current.get("values") or {}).get("max_drawdown_pct") or 0.0))
    if current.get("current_shock") and prev_dd - cur_dd >= NEW_LOW_RE_ALERT_PCT:
        reasons.append(f"최근 90분 최대 하락폭 {NEW_LOW_RE_ALERT_PCT:.1f}%p 이상 확대")
    return reasons


def current_title_level() -> int:
    if not ALERT_TITLE.exists():
        return 0
    title = ALERT_TITLE.read_text(encoding="utf-8").strip()
    return SEVERITY.get(title[:1], 0)


def set_title_floor(level: int) -> None:
    if not ALERT_TITLE.exists():
        ALERT_TITLE.write_text(f"{EMOJI[level]} 엔캐리 복합 수급 알림\n", encoding="utf-8")
        return
    title = ALERT_TITLE.read_text(encoding="utf-8").strip()
    if current_title_level() >= level:
        return
    title = re.sub(r"^[🟢🟡🟠🔴]\s*", f"{EMOJI[level]} ", title)
    ALERT_TITLE.write_text(title + "\n", encoding="utf-8")


def shock_section(snapshot: ShockSnapshot) -> str:
    current_line = (
        "🟠 현재 급락 진행" if snapshot.current_shock
        else "🟢 현재 급락 완화"
    )
    recent_line = (
        "🟡 최근 90분 충격 잔존" if snapshot.recent_shock
        else ("🟠 현재 충격이 최근 90분 구간에도 포함" if snapshot.current_shock else "🟢 최근 90분 충격 잔존 미확인")
    )
    return "\n".join(
        [
            "환율 충격 상태",
            f"- 현재 충격: {current_line}",
            f"- 최근 충격: {recent_line}",
            f"- USD/JPY {snapshot.latest_price:.3f} / 15분 {snapshot.change_15m_pct:+.2f}% / 30분 {snapshot.change_30m_pct:+.2f}%",
            f"- 최근 90분 최대 하락: {snapshot.max_drawdown_pct:.2f}% / 저점 이후 반등 {snapshot.current_rebound_pct:+.2f}% / 고점 대비 현재 {snapshot.current_vs_peak_pct:.2f}%",
            f"- 최근 저점 경과: {snapshot.trough_age_minutes:.0f}분",
            "※ 현재 충격은 지금 진행 중인 급락, 최근 충격은 -1%급 급락 후 일부 반등했지만 충격이 아직 남아 있는 상태를 뜻합니다.",
        ]
    )


def append_or_replace_section(body: str, snapshot: ShockSnapshot) -> str:
    section = shock_section(snapshot)
    pattern = r"\n\n환율 충격 상태\n.*?(?=\n\n(?:출처|자료 확인 상태|$))"
    if re.search(pattern, body, flags=re.DOTALL):
        return re.sub(pattern, "\n\n" + section, body, flags=re.DOTALL)
    marker = "\n\n출처\n"
    if marker in body:
        return body.replace(marker, "\n\n" + section + marker, 1)
    return body.rstrip() + "\n\n" + section + "\n"


def standalone_body(snapshot: ShockSnapshot, now: dt.datetime, reasons: list[str]) -> str:
    if snapshot.current_shock:
        risk = "🟠 엔캐리 청산 경계 강화"
    elif snapshot.recent_shock:
        risk = "🟡 최근 엔화 강세 충격 잔존"
    else:
        risk = "🟢 최근 엔화 강세 충격 해제"
    reason_lines = "\n".join(f"- {item}" for item in reasons) or "- 환율 충격 상태 재평가"
    return (
        f"조회 시각: {now.astimezone(KST).strftime('%Y-%m-%d %H:%M:%S')} KST\n\n"
        "판정\n"
        f"- 캐리 청산 위험: {risk}\n"
        "- 엔화 재약세·캐리 재구축: 별도 복합 감시 기준 유지\n"
        "※ 최근 충격은 현재 강제청산 확정이 아니라, 직전 급락의 잔존 위험을 기억하는 보조 경보입니다.\n\n"
        "이번 변화\n"
        f"{reason_lines}\n\n"
        f"{shock_section(snapshot)}\n\n"
        "정확한 의미\n"
        "- 15·30분 급락이 지금 진행 중이면 현재 충격으로 봅니다.\n"
        "- 최근 90분 안에 -1%급 하락이 있었고 일부 반등 뒤에도 고점 대비 -0.5% 이상 낮으면 최근 충격으로 남깁니다.\n"
        "- 최근 충격만으로 🟠·🔴로 올리지 않으며, 미·일 금리차·일본 단기금리·변동성·포지션과 함께 판단합니다.\n\n"
        "출처\n"
        "- USD/JPY: Yahoo query1/query2 5분 데이터 교차확인(동일 공급자, 지연 가능)\n"
    )


def write_alert(snapshot: ShockSnapshot, now: dt.datetime, reasons: list[str]) -> None:
    if ALERT_BODY.exists():
        body = ALERT_BODY.read_text(encoding="utf-8")
        ALERT_BODY.write_text(append_or_replace_section(body, snapshot).rstrip() + "\n", encoding="utf-8")
    else:
        level = 2 if snapshot.current_shock else (1 if snapshot.recent_shock else 0)
        ALERT_TITLE.write_text(f"{EMOJI[level]} 엔캐리 복합 수급 알림\n", encoding="utf-8")
        ALERT_BODY.write_text(standalone_body(snapshot, now, reasons), encoding="utf-8")

    if snapshot.current_shock:
        set_title_floor(2)
    elif snapshot.recent_shock:
        set_title_floor(1)

    payload = load_json(ALERT_JSON, {})
    payload["recent_fx_shock"] = {
        "window_minutes": WINDOW_MINUTES,
        "threshold_drawdown_pct": SHOCK_DRAWDOWN_PCT,
        "current_shock": snapshot.current_shock,
        "recent_shock": snapshot.recent_shock,
        "snapshot": asdict(snapshot),
        "reasons": reasons,
    }
    ALERT_JSON.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def finalize() -> int:
    if not PENDING_PATH.exists():
        return 0
    # Advance only when there was no outgoing alert, or Telegram delivery was confirmed.
    if ALERT_BODY.exists() and not CONFIRMED.exists():
        print("recent_shock_state_not_advanced=telegram_unconfirmed")
        return 0
    STATE_PATH.write_text(PENDING_PATH.read_text(encoding="utf-8"), encoding="utf-8")
    print("recent_shock_state_finalized=true")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--finalize", action="store_true")
    args = parser.parse_args()
    if args.finalize:
        return finalize()

    now = dt.datetime.now(KST)
    points = composite.fetch_fx_points()
    snapshot = calculate(points)
    current = state_from(snapshot, now)
    previous = load_json(STATE_PATH, {})
    PENDING_PATH.write_text(json.dumps(current, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    reasons = state_change_reasons(previous, current)
    if not previous.get("initialized"):
        reasons = []

    # Always enrich an alert already generated by the composite lane.
    # If there is no base alert, create one only when the recent/current shock state changes.
    if ALERT_BODY.exists() or reasons:
        write_alert(snapshot, now, reasons)

    STATUS_PATH.write_text(
        "\n".join(
            [
                "# 엔캐리 환율 충격 기억층",
                "",
                f"- 조회시각(KST): {now.isoformat(timespec='seconds')}",
                f"- 현재 충격: {'예' if snapshot.current_shock else '아니오'}",
                f"- 최근 90분 충격 잔존: {'예' if snapshot.recent_shock else '아니오'}",
                f"- USD/JPY: {snapshot.latest_price:.3f}",
                f"- 15분: {snapshot.change_15m_pct:+.2f}% / 30분: {snapshot.change_30m_pct:+.2f}%",
                f"- 최근 90분 최대 하락: {snapshot.max_drawdown_pct:.2f}%",
                f"- 저점 이후 반등: {snapshot.current_rebound_pct:+.2f}%",
                f"- 고점 대비 현재: {snapshot.current_vs_peak_pct:.2f}%",
                f"- 상태변화: {', '.join(reasons) if reasons else '없음'}",
            ]
        ) + "\n",
        encoding="utf-8",
    )
    print(json.dumps({"snapshot": asdict(snapshot), "reasons": reasons}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
