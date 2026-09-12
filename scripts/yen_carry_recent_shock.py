#!/usr/bin/env python3
"""Keep yen-strength shocks visible even when GitHub schedule runs are delayed.

This layer answers three separate questions:
1) Current shock: is USD/JPY falling fast enough now to imply active unwind pressure?
2) Recent shock: did a >=1% yen-strength shock occur in the last six hours and leave
   a still-material residual move after a partial rebound?
3) Recovered missed shock: did a >=1% shock happen after the last acknowledged shock
   even if the price later recovered before the next successful scheduled run?

The historical/recovery lane is capped at yellow. It is intended to prevent a dropped
GitHub cron run from making a real intraday shock disappear from the alert system.
Stale five-minute FX observations are retained as reference data only and are never
used as a current/recent shock signal.
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
UTC = dt.timezone.utc
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

ACTIVE_WINDOW_MINUTES = 90
RECOVERY_WINDOW_MINUTES = 6 * 60
SHOCK_DRAWDOWN_PCT = -1.00
CURRENT_RESIDUAL_PCT = -1.00
RECENT_RESIDUAL_PCT = -0.50
MAX_CURRENT_REBOUND_PCT = 0.20
NEW_LOW_RE_ALERT_PCT = 0.30
GAP_ALERT_MINUTES = 20.0
MAX_LIVE_FX_AGE_SECONDS = 12 * 60
MAX_FUTURE_FX_SKEW_SECONDS = 120

SEVERITY = {"🟢": 0, "🟡": 1, "🟠": 2, "🔴": 3}
EMOJI = {0: "🟢", 1: "🟡", 2: "🟠", 3: "🔴"}


@dataclass(frozen=True)
class ShockSnapshot:
    latest_price: float
    latest_epoch: float
    change_15m_pct: float
    change_30m_pct: float

    # Backward-compatible active-window fields (90 minutes).
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

    # Recovery window fields (6 hours).
    history_peak_price: float
    history_peak_epoch: float
    history_trough_price: float
    history_trough_epoch: float
    history_max_drawdown_pct: float
    history_current_rebound_pct: float
    history_current_vs_peak_pct: float
    history_trough_age_minutes: float
    history_shock: bool


@dataclass(frozen=True)
class HistoryEvent:
    reason: str
    trough_epoch: float
    trough_price: float


def load_json(path: pathlib.Path, default):
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
        return value if isinstance(value, type(default)) else default
    except Exception:
        return default


def finite(value) -> float | None:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def peak_to_trough(
    points: list[tuple[float, float]],
    window_minutes: int | None = None,
) -> tuple[float, float, float, float, float]:
    if not points:
        raise RuntimeError("USD/JPY observations missing")

    chosen = points
    if window_minutes is not None:
        latest_ts = points[-1][0]
        cutoff = latest_ts - window_minutes * 60
        chosen = [(ts, px) for ts, px in points if ts >= cutoff]

    if len(chosen) < 4:
        label = f"{window_minutes}-minute" if window_minutes is not None else "selected"
        raise RuntimeError(f"USD/JPY {label} observations insufficient")

    peak_ts, peak_px = chosen[0]
    best_peak_ts, best_peak_px = peak_ts, peak_px
    best_trough_ts, best_trough_px = peak_ts, peak_px
    best_drawdown = 0.0

    for ts, px in chosen[1:]:
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

    (
        peak_epoch,
        peak_price,
        trough_epoch,
        trough_price,
        max_drawdown_pct,
    ) = peak_to_trough(points, ACTIVE_WINDOW_MINUTES)

    (
        history_peak_epoch,
        history_peak_price,
        history_trough_epoch,
        history_trough_price,
        history_max_drawdown_pct,
    ) = peak_to_trough(points, RECOVERY_WINDOW_MINUTES)

    current_rebound_pct = (
        (latest_price / trough_price - 1.0) * 100.0 if trough_price > 0 else 0.0
    )
    current_vs_peak_pct = (
        (latest_price / peak_price - 1.0) * 100.0 if peak_price > 0 else 0.0
    )
    trough_age_minutes = max(0.0, (latest_epoch - trough_epoch) / 60.0)

    history_current_rebound_pct = (
        (latest_price / history_trough_price - 1.0) * 100.0
        if history_trough_price > 0
        else 0.0
    )
    history_current_vs_peak_pct = (
        (latest_price / history_peak_price - 1.0) * 100.0
        if history_peak_price > 0
        else 0.0
    )
    history_trough_age_minutes = max(
        0.0, (latest_epoch - history_trough_epoch) / 60.0
    )

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

    history_shock = bool(
        history_max_drawdown_pct <= SHOCK_DRAWDOWN_PCT
        and history_trough_age_minutes <= RECOVERY_WINDOW_MINUTES
    )
    recent_shock = bool(
        not current_shock
        and history_shock
        and history_current_vs_peak_pct <= RECENT_RESIDUAL_PCT
        and history_current_rebound_pct > MAX_CURRENT_REBOUND_PCT
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
        history_peak_price=history_peak_price,
        history_peak_epoch=history_peak_epoch,
        history_trough_price=history_trough_price,
        history_trough_epoch=history_trough_epoch,
        history_max_drawdown_pct=history_max_drawdown_pct,
        history_current_rebound_pct=history_current_rebound_pct,
        history_current_vs_peak_pct=history_current_vs_peak_pct,
        history_trough_age_minutes=history_trough_age_minutes,
        history_shock=history_shock,
    )


def fx_freshness(snapshot: ShockSnapshot, now: dt.datetime) -> tuple[bool, float, str]:
    observed_utc = dt.datetime.fromtimestamp(snapshot.latest_epoch, tz=UTC)
    now_utc = now.astimezone(UTC)
    age_seconds = (now_utc - observed_utc).total_seconds()
    eligible = (
        age_seconds >= -MAX_FUTURE_FX_SKEW_SECONDS
        and age_seconds <= MAX_LIVE_FX_AGE_SECONDS
    )
    observed_kst = observed_utc.astimezone(KST).isoformat(timespec="seconds")
    return eligible, max(0.0, age_seconds), observed_kst


def stale_state(
    snapshot: ShockSnapshot,
    now: dt.datetime,
    previous: dict,
    age_seconds: float,
    observed_kst: str,
) -> dict:
    if previous.get("initialized"):
        current = dict(previous)
    else:
        current = {
            "initialized": True,
            "current_shock": False,
            "recent_shock": False,
            "history_shock": False,
            "last_history_alert_trough_epoch": None,
            "last_history_alert_trough_price": None,
            "values": {},
        }
    current.update(
        {
            "initialized": True,
            "updated_at_kst": now.astimezone(KST).isoformat(timespec="seconds"),
            "fx_signal_eligible": False,
            "fx_age_seconds": age_seconds,
            "fx_observed_at_kst": observed_kst,
            "reference_usdjpy": snapshot.latest_price,
            "reference_latest_epoch": snapshot.latest_epoch,
        }
    )
    return current


def monitor_gap_minutes(previous: dict, now: dt.datetime) -> float | None:
    if not previous.get("initialized"):
        return None
    raw = previous.get("updated_at_kst")
    if not raw:
        return None
    try:
        previous_time = dt.datetime.fromisoformat(str(raw))
        if previous_time.tzinfo is None:
            previous_time = previous_time.replace(tzinfo=KST)
        return max(
            0.0,
            (now.astimezone(KST) - previous_time.astimezone(KST)).total_seconds()
            / 60.0,
        )
    except (TypeError, ValueError):
        return None


def detect_history_event(
    previous: dict,
    snapshot: ShockSnapshot,
    points: list[tuple[float, float]],
) -> HistoryEvent | None:
    if not snapshot.history_shock:
        return None

    last_epoch = finite(previous.get("last_history_alert_trough_epoch"))
    last_price = finite(previous.get("last_history_alert_trough_price"))

    if last_epoch is None:
        return HistoryEvent(
            reason=f"최근 {RECOVERY_WINDOW_MINUTES // 60}시간 -1%급 급락 새로 확인",
            trough_epoch=snapshot.history_trough_epoch,
            trough_price=snapshot.history_trough_price,
        )

    if (
        last_price is not None
        and snapshot.history_trough_epoch > last_epoch
        and snapshot.history_trough_price
        <= last_price * (1.0 - NEW_LOW_RE_ALERT_PCT / 100.0)
    ):
        return HistoryEvent(
            reason=f"기존 급락 저점 대비 {NEW_LOW_RE_ALERT_PCT:.1f}% 이상 추가 하락",
            trough_epoch=snapshot.history_trough_epoch,
            trough_price=snapshot.history_trough_price,
        )

    latest_ts = points[-1][0]
    cutoff = max(
        latest_ts - RECOVERY_WINDOW_MINUTES * 60,
        last_epoch + 60.0,
    )
    later = [(ts, px) for ts, px in points if ts >= cutoff]
    if len(later) >= 4:
        peak_ts, peak_px, trough_ts, trough_px, drawdown = peak_to_trough(later)
        if drawdown <= SHOCK_DRAWDOWN_PCT and trough_ts > last_epoch + 60.0:
            return HistoryEvent(
                reason=f"이전 경보 이후 새 -1%급 급락 확인 ({drawdown:.2f}%)",
                trough_epoch=trough_ts,
                trough_price=trough_px,
            )
    return None


def state_from(
    snapshot: ShockSnapshot,
    now: dt.datetime,
    previous: dict,
    history_event: HistoryEvent | None,
) -> dict:
    current = {
        "initialized": True,
        "updated_at_kst": now.astimezone(KST).isoformat(timespec="seconds"),
        "fx_signal_eligible": True,
        "fx_age_seconds": max(
            0.0,
            (now.astimezone(UTC) - dt.datetime.fromtimestamp(snapshot.latest_epoch, tz=UTC)).total_seconds(),
        ),
        "fx_observed_at_kst": dt.datetime.fromtimestamp(snapshot.latest_epoch, tz=UTC)
        .astimezone(KST)
        .isoformat(timespec="seconds"),
        "current_shock": snapshot.current_shock,
        "recent_shock": snapshot.recent_shock,
        "history_shock": snapshot.history_shock,
        "last_history_alert_trough_epoch": previous.get(
            "last_history_alert_trough_epoch"
        ),
        "last_history_alert_trough_price": previous.get(
            "last_history_alert_trough_price"
        ),
        "values": asdict(snapshot),
    }
    if history_event is not None:
        current["last_history_alert_trough_epoch"] = history_event.trough_epoch
        current["last_history_alert_trough_price"] = history_event.trough_price
    return current


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
            "최근 6시간 충격 잔존 진입"
            if current.get("recent_shock")
            else "최근 6시간 충격 잔존 해제"
        )

    prev_dd = finite(((previous.get("values") or {}).get("max_drawdown_pct"))) or 0.0
    cur_dd = finite(((current.get("values") or {}).get("max_drawdown_pct"))) or 0.0
    if current.get("current_shock") and prev_dd - cur_dd >= NEW_LOW_RE_ALERT_PCT:
        reasons.append(
            f"최근 90분 최대 하락폭 {NEW_LOW_RE_ALERT_PCT:.1f}%p 이상 확대"
        )
    return reasons


def dedupe_reasons(reasons: list[str]) -> list[str]:
    output: list[str] = []
    for reason in reasons:
        if reason and reason not in output:
            output.append(reason)
    return output


def current_title_level() -> int:
    if not ALERT_TITLE.exists():
        return 0
    title = ALERT_TITLE.read_text(encoding="utf-8").strip()
    return SEVERITY.get(title[:1], 0)


def set_title_floor(level: int) -> None:
    if not ALERT_TITLE.exists():
        ALERT_TITLE.write_text(
            f"{EMOJI[level]} 엔캐리 복합 수급 알림\n", encoding="utf-8"
        )
        return
    title = ALERT_TITLE.read_text(encoding="utf-8").strip()
    if current_title_level() >= level:
        return
    title = re.sub(r"^[🟢🟡🟠🔴]\s*", f"{EMOJI[level]} ", title)
    ALERT_TITLE.write_text(title + "\n", encoding="utf-8")


def shock_section(snapshot: ShockSnapshot) -> str:
    current_line = (
        "🟠 현재 급락 진행" if snapshot.current_shock else "🟢 현재 급락 완화"
    )
    if snapshot.recent_shock:
        recent_line = "🟡 최근 6시간 충격 잔존"
    elif snapshot.history_shock:
        recent_line = "🟡 최근 6시간 -1%급 급락 이력 확인(현재는 상당 부분 회복)"
    elif snapshot.current_shock:
        recent_line = "🟠 현재 충격 진행 중"
    else:
        recent_line = "🟢 최근 6시간 -1%급 충격 미확인"

    return "\n".join(
        [
            "환율 충격 상태",
            f"- 현재 충격: {current_line}",
            f"- 최근 충격: {recent_line}",
            f"- USD/JPY {snapshot.latest_price:.3f} / 15분 {snapshot.change_15m_pct:+.2f}% / 30분 {snapshot.change_30m_pct:+.2f}%",
            f"- 최근 90분 최대 하락: {snapshot.max_drawdown_pct:.2f}% / 저점 이후 반등 {snapshot.current_rebound_pct:+.2f}%",
            f"- 최근 6시간 최대 하락: {snapshot.history_max_drawdown_pct:.2f}% / 저점 이후 반등 {snapshot.history_current_rebound_pct:+.2f}% / 고점 대비 현재 {snapshot.history_current_vs_peak_pct:.2f}%",
            f"- 6시간 구간 저점 경과: {snapshot.history_trough_age_minutes:.0f}분",
            "※ 5분 예약 실행이 일부 누락돼도 다음 성공 실행에서 최근 6시간 5분봉을 다시 훑어 -1%급 급락을 복원합니다.",
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


def standalone_body(
    snapshot: ShockSnapshot,
    now: dt.datetime,
    reasons: list[str],
) -> str:
    gap_only = bool(reasons) and all("감시 실행 공백" in item for item in reasons)
    if snapshot.current_shock:
        risk = "🟠 엔캐리 청산 경계 강화"
    elif snapshot.recent_shock:
        risk = "🟡 최근 엔화 강세 충격 잔존"
    elif snapshot.history_shock:
        risk = "🟡 최근 6시간 급락 이력 확인"
    elif gap_only:
        risk = "🟡 감시 공백 복구"
    else:
        risk = "🟢 현재 급락 경보 없음"

    reason_lines = (
        "\n".join(f"- {item}" for item in reasons)
        if reasons
        else "- 환율 충격 상태 재평가"
    )
    return (
        f"조회 시각: {now.astimezone(KST).strftime('%Y-%m-%d %H:%M:%S')} KST\n\n"
        "판정\n"
        f"- 캐리 청산 위험: {risk}\n"
        "- 엔화 재약세·캐리 재구축: 별도 복합 감시 기준 유지\n"
        "※ 최근 충격 이력은 현재 강제청산 확정이 아니라, 실행 공백 때문에 놓칠 수 있는 급락을 보존하는 보조 경보입니다.\n\n"
        "이번 변화\n"
        f"{reason_lines}\n\n"
        f"{shock_section(snapshot)}\n\n"
        "정확한 의미\n"
        "- 15·30분 급락이 지금 진행 중이면 현재 충격으로 봅니다.\n"
        "- 최근 6시간 안에 -1%급 고점→저점 하락이 있었으면 실행 누락 뒤에도 다시 찾아냅니다.\n"
        "- 일부 반등 뒤에도 고점 대비 -0.5% 이상 낮으면 최근 충격 잔존으로 표시합니다.\n"
        "- 과거 충격 이력만으로 🟠·🔴로 올리지 않으며, 미·일 금리차·일본 단기금리·변동성·포지션과 함께 판단합니다.\n\n"
        "출처\n"
        "- USD/JPY: Yahoo query1/query2 5분 데이터 교차확인(동일 공급자, 지연 가능)\n"
    )


def write_alert(snapshot: ShockSnapshot, now: dt.datetime, reasons: list[str]) -> None:
    if ALERT_BODY.exists():
        body = ALERT_BODY.read_text(encoding="utf-8")
        ALERT_BODY.write_text(
            append_or_replace_section(body, snapshot).rstrip() + "\n",
            encoding="utf-8",
        )
    else:
        level = 2 if snapshot.current_shock else (1 if reasons or snapshot.history_shock else 0)
        ALERT_TITLE.write_text(
            f"{EMOJI[level]} 엔캐리 복합 수급 알림\n", encoding="utf-8"
        )
        ALERT_BODY.write_text(
            standalone_body(snapshot, now, reasons), encoding="utf-8"
        )

    if snapshot.current_shock:
        set_title_floor(2)
    elif snapshot.history_shock or reasons:
        set_title_floor(1)

    payload = load_json(ALERT_JSON, {})
    payload["recent_fx_shock"] = {
        "active_window_minutes": ACTIVE_WINDOW_MINUTES,
        "recovery_window_minutes": RECOVERY_WINDOW_MINUTES,
        "threshold_drawdown_pct": SHOCK_DRAWDOWN_PCT,
        "current_shock": snapshot.current_shock,
        "recent_shock": snapshot.recent_shock,
        "history_shock": snapshot.history_shock,
        "snapshot": asdict(snapshot),
        "reasons": reasons,
    }
    ALERT_JSON.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def finalize() -> int:
    if not PENDING_PATH.exists():
        return 0

    # Advance state only after Telegram confirms any outgoing alert.
    if ALERT_BODY.exists() and not CONFIRMED.exists():
        print("recent_shock_state_not_advanced=telegram_unconfirmed")
        return 0

    STATE_PATH.write_text(
        PENDING_PATH.read_text(encoding="utf-8"), encoding="utf-8"
    )
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
    previous = load_json(STATE_PATH, {})
    signal_eligible, fx_age_seconds, fx_observed_at_kst = fx_freshness(snapshot, now)
    gap = monitor_gap_minutes(previous, now)

    if not signal_eligible:
        current = stale_state(
            snapshot,
            now,
            previous,
            fx_age_seconds,
            fx_observed_at_kst,
        )
        PENDING_PATH.write_text(
            json.dumps(current, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        status_lines = [
            "# 엔캐리 환율 충격 기억층",
            "",
            f"- 조회시각(KST): {now.isoformat(timespec='seconds')}",
            "- 현재·최근 6시간 충격 판정: 보류",
            f"- USD/JPY 최근 관측: {snapshot.latest_price:.3f}",
            f"- 환율 관측시각(KST): {fx_observed_at_kst}",
            f"- 환율 데이터 지연: {fx_age_seconds / 60.0:.0f}분",
            f"- 현재 신호 사용 기준: {MAX_LIVE_FX_AGE_SECONDS // 60}분 이내",
            "- 기존 충격 상태: 보존",
            f"- 직전 성공 상태와 실행 간격: {gap:.0f}분"
            if gap is not None
            else "- 직전 성공 상태와 실행 간격: 확인 불가",
            "- 상태변화 알림: 없음 — 오래된 환율로 진입·해제·감시공백 경보를 만들지 않음",
        ]
        STATUS_PATH.write_text("\n".join(status_lines) + "\n", encoding="utf-8")
        print(
            json.dumps(
                {
                    "fx_signal_eligible": False,
                    "fx_age_seconds": fx_age_seconds,
                    "fx_observed_at_kst": fx_observed_at_kst,
                    "reference_usdjpy": snapshot.latest_price,
                    "monitor_gap_minutes": gap,
                    "reasons": [],
                },
                ensure_ascii=False,
            )
        )
        return 0

    history_event = detect_history_event(previous, snapshot, points)
    current = state_from(snapshot, now, previous, history_event)

    reasons = state_change_reasons(previous, current)
    if history_event is not None:
        reasons.append(history_event.reason)

    if gap is not None and gap >= GAP_ALERT_MINUTES:
        reasons.append(
            f"감시 실행 공백 {gap:.0f}분 감지 — 최근 6시간 급락 재검사 완료"
        )

    if not previous.get("initialized"):
        reasons = []
        if snapshot.current_shock:
            reasons.append("현재 충격 상태로 감시 시작")
        elif snapshot.recent_shock:
            reasons.append("최근 6시간 충격 잔존 상태로 감시 시작")
        elif history_event is not None:
            reasons.append(history_event.reason)

    reasons = dedupe_reasons(reasons)
    PENDING_PATH.write_text(
        json.dumps(current, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )

    # Always enrich an alert already generated by the composite lane.
    # Without a base alert, create one only for a meaningful state/history/gap change.
    if ALERT_BODY.exists() or reasons:
        write_alert(snapshot, now, reasons)

    status_lines = [
        "# 엔캐리 환율 충격 기억층",
        "",
        f"- 조회시각(KST): {now.isoformat(timespec='seconds')}",
        f"- 환율 관측시각(KST): {current['fx_observed_at_kst']}",
        f"- 환율 데이터 지연: {current['fx_age_seconds'] / 60.0:.1f}분",
        "- 현재 신호 사용: 예",
        f"- 현재 충격: {'예' if snapshot.current_shock else '아니오'}",
        f"- 최근 6시간 충격 잔존: {'예' if snapshot.recent_shock else '아니오'}",
        f"- 최근 6시간 -1%급 충격 이력: {'예' if snapshot.history_shock else '아니오'}",
        f"- USD/JPY: {snapshot.latest_price:.3f}",
        f"- 15분: {snapshot.change_15m_pct:+.2f}% / 30분: {snapshot.change_30m_pct:+.2f}%",
        f"- 최근 90분 최대 하락: {snapshot.max_drawdown_pct:.2f}%",
        f"- 최근 6시간 최대 하락: {snapshot.history_max_drawdown_pct:.2f}%",
        f"- 6시간 저점 이후 반등: {snapshot.history_current_rebound_pct:+.2f}%",
        f"- 고점 대비 현재: {snapshot.history_current_vs_peak_pct:.2f}%",
        f"- 직전 성공 상태와 실행 간격: {gap:.0f}분"
        if gap is not None
        else "- 직전 성공 상태와 실행 간격: 확인 불가",
        f"- 상태변화: {', '.join(reasons) if reasons else '없음'}",
    ]
    STATUS_PATH.write_text("\n".join(status_lines) + "\n", encoding="utf-8")
    print(
        json.dumps(
            {
                "snapshot": asdict(snapshot),
                "fx_signal_eligible": True,
                "fx_age_seconds": current["fx_age_seconds"],
                "fx_observed_at_kst": current["fx_observed_at_kst"],
                "monitor_gap_minutes": gap,
                "history_event": asdict(history_event) if history_event else None,
                "reasons": reasons,
            },
            ensure_ascii=False,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
