#!/usr/bin/env python3
"""USD/JPY 단기 급락(엔화 강세) 경보.

15·30분 구간은 '현재 진행형 급락'으로 텔레그램 경보를 생성한다.
60분 구간은 과거 충격 잔존 참고치로만 표시하며 단독으로 알림을 만들지 않는다.
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import math
import os
import pathlib
import urllib.parse
from dataclasses import asdict, dataclass
from zoneinfo import ZoneInfo

from khs_source_fetch import fetch_text

KST = ZoneInfo("Asia/Seoul")
UTC = dt.timezone.utc
SYMBOL = "JPY=X"

STATE_PATH = pathlib.Path("data/yen_carry_fx_shock_state.json")
OUT_DIR = pathlib.Path("out")
ALERT_TITLE_PATH = OUT_DIR / "yen_carry_fx_shock_alert_title.txt"
ALERT_BODY_PATH = OUT_DIR / "yen_carry_fx_shock_alert.md"
ALERT_JSON_PATH = OUT_DIR / "yen_carry_fx_shock_alert.json"
SUMMARY_PATH = OUT_DIR / "yen_carry_fx_shock_watch.md"
PENDING_STATE_PATH = OUT_DIR / "yen_carry_fx_shock_pending_state.json"
CONFIRMED_PATH = OUT_DIR / "yen_carry_fx_shock_telegram_confirmed.json"

YAHOO_BASES = (
    "https://query1.finance.yahoo.com/v8/finance/chart",
    "https://query2.finance.yahoo.com/v8/finance/chart",
)
USER_AGENT = "Mozilla/5.0 yen-carry-fx-shock/2.0"

# 진행형 경보: 15·30분만 사용한다.
WARNING_THRESHOLDS = {15: -0.50, 30: -0.75}
SEVERE_THRESHOLDS = {15: -1.00, 30: -1.25}

# 60분은 텔레그램 경보가 아니라 충격 잔존 참고치다.
RESIDUAL_WARNING_60M = -1.00
RESIDUAL_SEVERE_60M = -1.50

DIRECTION_EPSILON = 0.10
SAME_STAGE_COOLDOWN_MINUTES = 20
SAME_STAGE_NEW_LOW_PCT = 0.30


@dataclass(frozen=True)
class FxMove:
    latest_price: float
    latest_epoch: float
    reference_15m: float
    reference_15m_epoch: float
    change_15m_pct: float
    reference_30m: float
    reference_30m_epoch: float
    change_30m_pct: float
    reference_60m: float
    reference_60m_epoch: float
    change_60m_pct: float


def finite(value: object) -> float | None:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) else None


def valid_points(payload: dict) -> list[tuple[float, float]]:
    results = ((payload.get("chart") or {}).get("result") or [])
    if not results:
        error = (payload.get("chart") or {}).get("error") or {}
        raise RuntimeError(error.get("description") or "USD/JPY chart result missing")

    result = results[0]
    timestamps = result.get("timestamp") or []
    rows = ((result.get("indicators") or {}).get("quote") or [])
    closes = rows[0].get("close", []) if rows else []

    points: list[tuple[float, float]] = []
    for timestamp, close in zip(timestamps, closes):
        ts_value = finite(timestamp)
        close_value = finite(close)
        if ts_value is not None and close_value is not None and close_value > 0:
            points.append((ts_value, close_value))

    points.sort(key=lambda item: item[0])
    if len(points) < 13:
        raise RuntimeError("USD/JPY five-minute observations insufficient")
    return points


def rolling_reference(
    points: list[tuple[float, float]],
    minutes: int,
    *,
    max_gap_seconds: int = 480,
) -> tuple[float, float, float]:
    latest_ts, latest_price = points[-1]
    target = latest_ts - minutes * 60
    ref_ts, ref_price = min(points, key=lambda item: abs(item[0] - target))
    if abs(ref_ts - target) > max_gap_seconds or ref_price <= 0:
        raise RuntimeError(f"{minutes}-minute reference unavailable")
    return ref_ts, ref_price, ((latest_price - ref_price) / ref_price) * 100


def calculate_move(payload: dict) -> FxMove:
    points = valid_points(payload)
    latest_epoch, latest_price = points[-1]
    ref15_epoch, ref15, chg15 = rolling_reference(points, 15)
    ref30_epoch, ref30, chg30 = rolling_reference(points, 30)
    ref60_epoch, ref60, chg60 = rolling_reference(points, 60)
    return FxMove(
        latest_price=latest_price,
        latest_epoch=latest_epoch,
        reference_15m=ref15,
        reference_15m_epoch=ref15_epoch,
        change_15m_pct=chg15,
        reference_30m=ref30,
        reference_30m_epoch=ref30_epoch,
        change_30m_pct=chg30,
        reference_60m=ref60,
        reference_60m_epoch=ref60_epoch,
        change_60m_pct=chg60,
    )


def yahoo_url(base: str) -> str:
    params = urllib.parse.urlencode(
        {
            "interval": "5m",
            "range": "1d",
            "includePrePost": "true",
            "events": "div,splits",
        }
    )
    return f"{base}/{urllib.parse.quote(SYMBOL, safe='')}?{params}"


def fetch_one(base: str) -> FxMove:
    text, error = fetch_text(
        yahoo_url(base),
        USER_AGENT,
        timeout=18,
        attempts=2,
        accept="application/json",
    )
    if error or not text:
        raise RuntimeError(error or "empty USD/JPY response")
    return calculate_move(json.loads(text))


def moves_consistent(first: FxMove, second: FxMove) -> bool:
    price_gap_pct = abs(first.latest_price - second.latest_price) / max(
        first.latest_price, second.latest_price
    ) * 100
    return (
        price_gap_pct <= 0.03
        and abs(first.change_15m_pct - second.change_15m_pct) <= 0.05
        and abs(first.change_30m_pct - second.change_30m_pct) <= 0.08
        and abs(first.change_60m_pct - second.change_60m_pct) <= 0.10
        and abs(first.latest_epoch - second.latest_epoch) <= 600
    )


def fetch_move() -> FxMove:
    moves: list[FxMove] = []
    errors: list[str] = []
    for base in YAHOO_BASES:
        try:
            moves.append(fetch_one(base))
        except Exception as exc:
            errors.append(f"{base}: {type(exc).__name__}: {exc}")

    if not moves:
        raise RuntimeError(" | ".join(errors) or "USD/JPY retrieval failed")
    if len(moves) == 1:
        return moves[0]

    first, second = moves[:2]
    if not moves_consistent(first, second):
        raise RuntimeError(
            "Yahoo query1/query2 mismatch: "
            f"{first.latest_price:.3f}/{first.change_15m_pct:+.3f}% vs "
            f"{second.latest_price:.3f}/{second.change_15m_pct:+.3f}%"
        )
    return max(moves, key=lambda item: item.latest_epoch)


def _change(move: FxMove, minutes: int) -> float:
    return getattr(move, f"change_{minutes}m_pct")


def _reference_price(move: FxMove, minutes: int) -> float:
    return getattr(move, f"reference_{minutes}m")


def _reference_epoch(move: FxMove, minutes: int) -> float:
    return getattr(move, f"reference_{minutes}m_epoch")


def determine_stage(move: FxMove) -> int:
    """진행형 급락 단계. 15·30분만 사용한다."""
    if any(_change(move, m) <= v for m, v in SEVERE_THRESHOLDS.items()):
        return 2
    if any(_change(move, m) <= v for m, v in WARNING_THRESHOLDS.items()):
        return 1
    return 0


def determine_residual_stage(move: FxMove) -> int:
    """60분 충격 잔존 단계. 단독 텔레그램 경보에는 사용하지 않는다."""
    if move.change_60m_pct <= RESIDUAL_SEVERE_60M:
        return 2
    if move.change_60m_pct <= RESIDUAL_WARNING_60M:
        return 1
    return 0


def threshold_for(stage: int, minutes: int) -> float:
    return (SEVERE_THRESHOLDS if stage == 2 else WARNING_THRESHOLDS)[minutes]


def trigger_windows(stage: int, move: FxMove) -> list[int]:
    if stage not in (1, 2):
        return []
    return [
        minutes
        for minutes in (15, 30)
        if _change(move, minutes) <= threshold_for(stage, minutes)
    ]


def direction_label(change_pct: float) -> str:
    if change_pct <= -DIRECTION_EPSILON:
        return "USD/JPY 하락 = 엔화 강세"
    if change_pct >= DIRECTION_EPSILON:
        return "USD/JPY 상승 = 엔화 약세"
    return "사실상 보합"


def current_state(move: FxMove) -> str:
    c15 = move.change_15m_pct
    c30 = move.change_30m_pct

    if c15 <= -DIRECTION_EPSILON and c30 <= -DIRECTION_EPSILON:
        return "급락 진행 중 — 최근 15·30분 모두 USD/JPY 하락(엔화 강세)"
    if c15 <= -DIRECTION_EPSILON and c30 >= DIRECTION_EPSILON:
        return "반등 뒤 재하락 — 최근 15분 USD/JPY가 다시 하락"
    if c15 >= DIRECTION_EPSILON and c30 <= -DIRECTION_EPSILON:
        return "30분 급락 뒤 단기 반등 — 최근 15분은 USD/JPY 상승"
    if c15 >= DIRECTION_EPSILON and c30 >= DIRECTION_EPSILON:
        return "USD/JPY 반등 진행 중 — 최근 15·30분 모두 상승"
    if abs(c15) < DIRECTION_EPSILON and c30 <= -DIRECTION_EPSILON:
        return "최근 30분 급락 후 현재 보합 — 진행형 충격 잔존"
    if abs(c15) < DIRECTION_EPSILON and c30 >= DIRECTION_EPSILON:
        return "반등 후 현재 보합 — 지금 재급락 중은 아님"
    return "구간별 방향 혼조 — 15·30분 수치를 각각 확인"


def title_state(stage: int, move: FxMove, alert_reason: str) -> str:
    if alert_reason == "반등 후 15분 재급락":
        return "반등 후 15분 재급락"
    if alert_reason == "같은 단계 새 저점 확대":
        return "같은 단계 새 저점 확대"
    triggers = trigger_windows(stage, move)
    if 15 in triggers:
        return "15분 급락 진행"
    if 30 in triggers and move.change_15m_pct >= DIRECTION_EPSILON:
        return "30분 급락 뒤 단기 반등"
    if 30 in triggers:
        return "30분 급락 진행"
    return "진행형 급락"


def normalize_windows(value: object) -> list[int]:
    result: list[int] = []
    if not isinstance(value, (list, tuple, set)):
        return result
    for item in value:
        try:
            minutes = int(item)
        except (TypeError, ValueError):
            continue
        if minutes in (15, 30) and minutes not in result:
            result.append(minutes)
    return sorted(result)


def load_state() -> dict:
    default = {
        "stage": 0,
        "last_alert_at_kst": None,
        "last_alert_epoch": None,
        "last_alert_price": None,
        "last_alert_trigger_windows": [],
        "last_observed_trigger_windows": [],
    }
    if not STATE_PATH.exists():
        return default
    try:
        value = json.loads(STATE_PATH.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return default

    result = {**default, **value}
    if result.get("stage") not in (0, 1, 2):
        result["stage"] = 0
    result["last_alert_trigger_windows"] = normalize_windows(
        result.get("last_alert_trigger_windows", [])
    )
    result["last_observed_trigger_windows"] = normalize_windows(
        result.get("last_observed_trigger_windows", [])
    )
    return result


def write_json(path: pathlib.Path, value: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def fmt_kst(epoch: float) -> str:
    return dt.datetime.fromtimestamp(epoch, tz=UTC).astimezone(KST).strftime(
        "%Y-%m-%d %H:%M:%S KST"
    )


def fmt_hm(epoch: float) -> str:
    return dt.datetime.fromtimestamp(epoch, tz=UTC).astimezone(KST).strftime("%H:%M")


def clean_outputs() -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    for path in (
        ALERT_TITLE_PATH,
        ALERT_BODY_PATH,
        ALERT_JSON_PATH,
        PENDING_STATE_PATH,
        CONFIRMED_PATH,
    ):
        path.unlink(missing_ok=True)


def cooldown_elapsed(previous: dict, move: FxMove) -> bool:
    last_alert_epoch = finite(previous.get("last_alert_epoch"))
    if last_alert_epoch is None:
        return True
    return move.latest_epoch - last_alert_epoch >= SAME_STAGE_COOLDOWN_MINUTES * 60


def same_stage_reason(
    previous: dict,
    stage: int,
    move: FxMove,
    triggers: list[int],
) -> str | None:
    if stage not in (1, 2) or not cooldown_elapsed(previous, move):
        return None

    previous_observed = set(
        normalize_windows(previous.get("last_observed_trigger_windows", []))
    )
    if 15 in triggers and 15 not in previous_observed:
        return "반등 후 15분 재급락"

    last_alert_price = finite(previous.get("last_alert_price"))
    if last_alert_price is not None:
        new_low_threshold = last_alert_price * (1 - SAME_STAGE_NEW_LOW_PCT / 100)
        if move.latest_price <= new_low_threshold:
            return "같은 단계 새 저점 확대"

    return None


def alert_reason(previous_stage: int, stage: int, same_reason: str | None) -> str | None:
    if stage > previous_stage:
        return "상위 단계 악화" if previous_stage > 0 else "신규 진행형 급락"
    if stage == previous_stage and same_reason:
        return same_reason
    return None


def format_window_line(stage: int, move: FxMove, minutes: int) -> str:
    change = _change(move, minutes)
    threshold = threshold_for(stage, minutes)
    met = change <= threshold
    result = "충족 ← 이번 경보 원인" if met else "미충족"
    return (
        f"{minutes}분({fmt_hm(_reference_epoch(move, minutes))}→{fmt_hm(move.latest_epoch)}): "
        f"{_reference_price(move, minutes):.3f} → {move.latest_price:.3f}, {change:+.2f}% | "
        f"{direction_label(change)} | {stage}단계 기준 {threshold:+.2f}% {result}"
    )


def residual_line(move: FxMove) -> str:
    residual_stage = determine_residual_stage(move)
    if residual_stage == 2:
        state = "2단계·심각 충격 잔존"
    elif residual_stage == 1:
        state = "1단계·주의 충격 잔존"
    else:
        state = "충격 잔존 기준 미충족"
    return (
        f"60분 참고({fmt_hm(move.reference_60m_epoch)}→{fmt_hm(move.latest_epoch)}): "
        f"{move.reference_60m:.3f} → {move.latest_price:.3f}, "
        f"{move.change_60m_pct:+.2f}% | {direction_label(move.change_60m_pct)} | {state}"
    )


def build_body(
    stage: int,
    move: FxMove,
    checked_at: dt.datetime,
    *,
    reason: str,
) -> str:
    level = "2단계·심각" if stage == 2 else "1단계·주의"
    triggers = trigger_windows(stage, move)
    trigger_text = "·".join(f"{minutes}분" for minutes in triggers)
    return "\n".join(
        [
            f"조회 시각: {checked_at.astimezone(KST).strftime('%Y-%m-%d %H:%M:%S KST')}",
            f"시장 데이터 시각: {fmt_kst(move.latest_epoch)}",
            "방향 읽는 법: USD/JPY 하락 = 엔화 강세 / 상승 = 엔화 약세",
            "",
            f"현재 상태: {current_state(move)}",
            f"알림 사유: {reason}",
            f"경보 발동 근거: {trigger_text} 구간이 진행형 {level} 기준 충족",
            f"USD/JPY 현재가: {move.latest_price:.3f}",
            "",
            "진행형 구간",
            format_window_line(stage, move, 15),
            format_window_line(stage, move, 30),
            "",
            "60분 충격 잔존 참고 — 단독으로는 텔레그램을 보내지 않음",
            residual_line(move),
            "",
            f"최종 판정: USD/JPY 진행형 급락 {level}",
            "같은 단계라도 15분 급락이 새로 재발하거나, 직전 알림 가격보다 0.30% 이상 새 저점을 만들면 재알림합니다.",
            f"같은 단계 재알림 최소 간격: {SAME_STAGE_COOLDOWN_MINUTES}분",
            "",
            "이 경보는 기존 엔캐리 청산 확정 경보와 별개입니다.",
        ]
    )


def write_summary(
    move: FxMove | None,
    stage: int | None,
    residual_stage: int | None,
    previous_stage: int,
    status: str,
    error: str | None = None,
) -> None:
    lines = [
        "# USD/JPY 단기 급변 점검",
        "",
        f"- 상태: {status}",
        f"- 직전 진행형 단계: {previous_stage}",
        f"- 현재 진행형 단계: {'판정 보류' if stage is None else stage}",
        f"- 60분 충격 잔존 단계: {'판정 보류' if residual_stage is None else residual_stage}",
    ]
    if move is not None:
        lines.extend(
            [
                f"- 현재 방향: {current_state(move)}",
                f"- 현재가: {move.latest_price:.3f}",
                f"- 15분: {move.change_15m_pct:+.3f}%",
                f"- 30분: {move.change_30m_pct:+.3f}%",
                f"- 60분 참고: {move.change_60m_pct:+.3f}%",
                f"- 데이터 시각: {fmt_kst(move.latest_epoch)}",
            ]
        )
        if stage in (1, 2):
            lines.append(
                f"- 진행형 발동 구간: {', '.join(f'{item}분' for item in trigger_windows(stage, move))}"
            )
        if residual_stage in (1, 2) and stage == 0:
            lines.append("- 60분 단독 충족: 상태 참고만 기록·텔레그램 미발송")
    if error:
        lines.extend(["", f"- 오류: {error}"])
    SUMMARY_PATH.write_text("\n".join(lines) + "\n", encoding="utf-8")


def state_for_observation(
    previous: dict,
    *,
    stage: int,
    triggers: list[int],
) -> dict:
    result = dict(previous)
    result["stage"] = stage
    result["last_observed_trigger_windows"] = triggers
    return result


def should_persist_observed_windows(
    previous: dict,
    *,
    stage: int,
    triggers: list[int],
    move: FxMove,
) -> bool:
    previous_windows = normalize_windows(
        previous.get("last_observed_trigger_windows", [])
    )
    if triggers == previous_windows:
        return False

    # 같은 단계에서 새 15분 급락이 시작됐지만 재알림 쿨다운 중이면,
    # 즉시 관측 상태를 덮지 않는다. 급락이 쿨다운 이후에도 지속될 경우
    # 다음 실행에서 정확히 재알림할 수 있게 하기 위함이다.
    new_15m_during_cooldown = (
        stage == int(previous.get("stage", 0))
        and stage in (1, 2)
        and 15 in triggers
        and 15 not in previous_windows
        and not cooldown_elapsed(previous, move)
    )
    return not new_15m_during_cooldown


def run(current: dt.datetime | None = None) -> dict:
    clean_outputs()
    current = (current or dt.datetime.now(UTC)).astimezone(UTC)
    previous = load_state()
    previous_stage = int(previous.get("stage", 0))

    try:
        move = fetch_move()
    except Exception as exc:
        write_summary(
            None,
            None,
            None,
            previous_stage,
            "데이터 불일치·조회 실패로 판정 보류",
            str(exc),
        )
        return {
            "alerted": False,
            "stage": None,
            "residual_stage": None,
            "previous_stage": previous_stage,
            "error": str(exc),
        }

    max_age_minutes = int(os.getenv("YEN_CARRY_FX_SHOCK_MAX_AGE_MINUTES", "12"))
    age_minutes = max(0.0, (current.timestamp() - move.latest_epoch) / 60.0)
    if age_minutes > max_age_minutes:
        status = f"데이터가 {age_minutes:.1f}분 지연되어 판정 보류"
        write_summary(move, None, None, previous_stage, status)
        return {
            "alerted": False,
            "stage": None,
            "residual_stage": None,
            "previous_stage": previous_stage,
            "age_minutes": age_minutes,
        }

    stage = determine_stage(move)
    residual_stage = determine_residual_stage(move)
    triggers = trigger_windows(stage, move)
    same_reason = same_stage_reason(previous, stage, move, triggers)
    reason = alert_reason(previous_stage, stage, same_reason)
    checked_at_kst = current.astimezone(KST).isoformat(timespec="seconds")

    if reason is not None:
        pending = state_for_observation(previous, stage=stage, triggers=triggers)
        pending.update(
            {
                "last_alert_at_kst": checked_at_kst,
                "last_alert_epoch": move.latest_epoch,
                "last_alert_price": move.latest_price,
                "last_alert_trigger_windows": triggers,
            }
        )
        title = f"🚨 USD/JPY 진행형 급락 {stage}단계 — {title_state(stage, move, reason)}"
        body = build_body(stage, move, current, reason=reason)
        ALERT_TITLE_PATH.write_text(title + "\n", encoding="utf-8")
        ALERT_BODY_PATH.write_text(body + "\n", encoding="utf-8")
        write_json(
            ALERT_JSON_PATH,
            {
                "stage": stage,
                "residual_stage": residual_stage,
                "move": asdict(move),
                "current_state": current_state(move),
                "trigger_windows": triggers,
                "alert_reason": reason,
                "checked_at_kst": checked_at_kst,
            },
        )
        write_json(PENDING_STATE_PATH, pending)
        write_summary(
            move,
            stage,
            residual_stage,
            previous_stage,
            f"진행형 급락 경보 생성 — {reason}",
        )
        return {
            "alerted": True,
            "stage": stage,
            "residual_stage": residual_stage,
            "previous_stage": previous_stage,
            "current_state": current_state(move),
            "trigger_windows": triggers,
            "alert_reason": reason,
            "move": asdict(move),
        }

    state_changed = (
        stage != previous_stage
        or should_persist_observed_windows(
            previous,
            stage=stage,
            triggers=triggers,
            move=move,
        )
    )
    if state_changed:
        write_json(
            STATE_PATH,
            state_for_observation(previous, stage=stage, triggers=triggers),
        )

    if stage == 0 and residual_stage > 0:
        status = "진행형 급락 해제·60분 충격 잔존 참고만 기록"
    elif stage == 0:
        status = "진행형 급락 기준 미충족"
    elif stage == previous_stage:
        status = "같은 진행형 단계 유지·재알림 조건 미충족"
    else:
        status = "진행형 단계 하향 상태 갱신"

    write_summary(move, stage, residual_stage, previous_stage, status)
    return {
        "alerted": False,
        "stage": stage,
        "residual_stage": residual_stage,
        "previous_stage": previous_stage,
        "current_state": current_state(move),
        "trigger_windows": triggers,
        "move": asdict(move),
    }


def finalize() -> int:
    if not PENDING_STATE_PATH.exists():
        print("FX shock pending state missing; nothing to finalize.")
        return 0
    if not CONFIRMED_PATH.exists():
        print("FX shock Telegram confirmation missing; pending state not finalized.")
        return 0

    pending = json.loads(PENDING_STATE_PATH.read_text(encoding="utf-8"))
    write_json(STATE_PATH, pending)
    print(f"Finalized FX shock state: {STATE_PATH}")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--finalize", action="store_true")
    args = parser.parse_args()
    if args.finalize:
        return finalize()

    result = run()
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
