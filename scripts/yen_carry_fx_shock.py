#!/usr/bin/env python3
"""독립적인 USD/JPY 급락(엔화 급등) 경보를 생성한다.

기존 엔캐리 확정 경보와 별도로 USD/JPY의 15·30·60분 움직임을 감시한다.
알림은 '현재 진행 방향'과 '경보를 울린 과거 비교 구간'을 분리해 표시한다.
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
USER_AGENT = "Mozilla/5.0 yen-carry-fx-shock/1.1"

WARNING_THRESHOLDS = {15: -0.50, 30: -0.75, 60: -1.00}
SEVERE_THRESHOLDS = {15: -1.00, 30: -1.25, 60: -1.50}
DIRECTION_EPSILON = 0.10


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
    price_gap_pct = abs(first.latest_price - second.latest_price) / max(first.latest_price, second.latest_price) * 100
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
    if any(_change(move, minutes) <= threshold for minutes, threshold in SEVERE_THRESHOLDS.items()):
        return 2
    if any(_change(move, minutes) <= threshold for minutes, threshold in WARNING_THRESHOLDS.items()):
        return 1
    return 0


def threshold_for(stage: int, minutes: int) -> float:
    return (SEVERE_THRESHOLDS if stage == 2 else WARNING_THRESHOLDS)[minutes]


def trigger_windows(stage: int, move: FxMove) -> list[int]:
    return [minutes for minutes in (15, 30, 60) if _change(move, minutes) <= threshold_for(stage, minutes)]


def direction_label(change_pct: float) -> str:
    if change_pct <= -DIRECTION_EPSILON:
        return "USD/JPY 하락 = 엔화 강세"
    if change_pct >= DIRECTION_EPSILON:
        return "USD/JPY 상승 = 엔화 약세"
    return "사실상 보합"


def current_state(move: FxMove) -> str:
    c15 = move.change_15m_pct
    c30 = move.change_30m_pct
    c60 = move.change_60m_pct

    if c15 <= -DIRECTION_EPSILON and c30 <= -DIRECTION_EPSILON:
        return "급락 진행 중 — 최근 15·30분 모두 USD/JPY 하락(엔화 강세)"
    if c15 <= -DIRECTION_EPSILON and c30 >= DIRECTION_EPSILON:
        return "반등 뒤 재하락 — 최근 15분에 USD/JPY가 다시 하락"
    if c15 >= DIRECTION_EPSILON and c30 <= -DIRECTION_EPSILON:
        return "급락 뒤 단기 반등 — 최근 15분은 USD/JPY 상승"
    if c15 >= DIRECTION_EPSILON and c30 >= DIRECTION_EPSILON:
        if c60 < 0:
            return "반등 진행 중 — 최근 15·30분은 상승했지만 60분 급락 충격은 남아 있음"
        return "USD/JPY 반등 진행 중 — 최근 15·30분 모두 상승"
    if abs(c15) < DIRECTION_EPSILON and c30 >= DIRECTION_EPSILON:
        return "반등 후 현재 보합 — 지금 재급락 중은 아님"
    if abs(c15) < DIRECTION_EPSILON and c30 <= -DIRECTION_EPSILON:
        return "최근 30분 급락 후 현재 보합 — 단기 충격 잔존"
    if abs(c15) < DIRECTION_EPSILON and abs(c30) < DIRECTION_EPSILON and c60 <= WARNING_THRESHOLDS[60]:
        return "현재 보합 — 60분 급락 충격만 잔존"
    if c15 >= DIRECTION_EPSILON and c60 < 0:
        return "단기 반등 중 — 60분 기준 엔화 강세 충격은 남아 있음"
    return "구간별 방향 혼조 — 15·30·60분 수치를 각각 확인"


def title_state(stage: int, move: FxMove) -> str:
    triggers = trigger_windows(stage, move)
    if 15 in triggers:
        return "15분 급락 진행"
    if 30 in triggers:
        if move.change_15m_pct >= DIRECTION_EPSILON:
            return "30분 급락 뒤 단기 반등"
        return "30분 급락 충격"
    if 60 in triggers:
        if move.change_30m_pct >= DIRECTION_EPSILON:
            return "반등 중·60분 급락 충격 잔존"
        if abs(move.change_15m_pct) < DIRECTION_EPSILON:
            return "현재 보합·60분 급락 충격 잔존"
        return "60분 급락 충격 잔존"
    return "구간별 급변"


def load_state() -> dict:
    if not STATE_PATH.exists():
        return {"stage": 0, "last_alert_at_kst": None}
    try:
        value = json.loads(STATE_PATH.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {"stage": 0, "last_alert_at_kst": None}
    value["stage"] = value.get("stage") if value.get("stage") in (1, 2) else 0
    return value


def write_json(path: pathlib.Path, value: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def fmt_kst(epoch: float) -> str:
    return dt.datetime.fromtimestamp(epoch, tz=UTC).astimezone(KST).strftime("%Y-%m-%d %H:%M:%S KST")


def fmt_hm(epoch: float) -> str:
    return dt.datetime.fromtimestamp(epoch, tz=UTC).astimezone(KST).strftime("%H:%M")


def clean_outputs() -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    for path in (ALERT_TITLE_PATH, ALERT_BODY_PATH, ALERT_JSON_PATH, PENDING_STATE_PATH, CONFIRMED_PATH):
        path.unlink(missing_ok=True)


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


def build_body(stage: int, move: FxMove, checked_at: dt.datetime) -> str:
    level = "2단계·심각" if stage == 2 else "1단계·주의"
    triggers = trigger_windows(stage, move)
    trigger_text = "·".join(f"{minutes}분" for minutes in triggers)
    state_text = current_state(move)
    return "\n".join(
        [
            f"조회 시각: {checked_at.astimezone(KST).strftime('%Y-%m-%d %H:%M:%S KST')}",
            f"시장 데이터 시각: {fmt_kst(move.latest_epoch)}",
            "방향 읽는 법: USD/JPY 하락 = 엔화 강세 / 상승 = 엔화 약세",
            "",
            f"현재 상태: {state_text}",
            f"경보 발동 근거: {trigger_text} 구간이 {level} 기준 충족",
            f"USD/JPY 현재가: {move.latest_price:.3f}",
            "",
            "구간별 비교",
            format_window_line(stage, move, 15),
            format_window_line(stage, move, 30),
            format_window_line(stage, move, 60),
            "",
            f"최종 판정: USD/JPY 급변 {level}",
            "주의: 경보 단계는 최근 15·30·60분 중 기준을 넘은 구간의 충격 크기입니다.",
            "지금 이 순간의 진행 방향은 위 '현재 상태'를 우선해서 보십시오.",
            "",
            "이 경보는 기존 엔캐리 청산 확정 경보와 별개입니다.",
            "같은 단계가 유지되는 동안에는 중복 전송하지 않습니다.",
        ]
    )


def write_summary(move: FxMove | None, stage: int | None, previous_stage: int, status: str, error: str | None = None) -> None:
    lines = [
        "# USD/JPY 단기 급변 점검",
        "",
        f"- 상태: {status}",
        f"- 직전 단계: {previous_stage}",
        f"- 현재 단계: {'판정 보류' if stage is None else stage}",
    ]
    if move is not None:
        lines.extend(
            [
                f"- 현재 방향: {current_state(move)}",
                f"- 현재가: {move.latest_price:.3f}",
                f"- 15분: {move.change_15m_pct:+.3f}%",
                f"- 30분: {move.change_30m_pct:+.3f}%",
                f"- 60분: {move.change_60m_pct:+.3f}%",
                f"- 데이터 시각: {fmt_kst(move.latest_epoch)}",
            ]
        )
        if stage in (1, 2):
            lines.append(f"- 발동 구간: {', '.join(f'{item}분' for item in trigger_windows(stage, move))}")
    if error:
        lines.extend(["", f"- 오류: {error}"])
    SUMMARY_PATH.write_text("\n".join(lines) + "\n", encoding="utf-8")


def run(current: dt.datetime | None = None) -> dict:
    clean_outputs()
    current = (current or dt.datetime.now(UTC)).astimezone(UTC)
    previous = load_state()
    previous_stage = int(previous.get("stage", 0))
    try:
        move = fetch_move()
    except Exception as exc:
        write_summary(None, None, previous_stage, "데이터 불일치·조회 실패로 판정 보류", str(exc))
        return {"alerted": False, "stage": None, "previous_stage": previous_stage, "error": str(exc)}

    max_age_minutes = int(os.getenv("YEN_CARRY_FX_SHOCK_MAX_AGE_MINUTES", "20"))
    age_minutes = max(0.0, (current.timestamp() - move.latest_epoch) / 60.0)
    if age_minutes > max_age_minutes:
        status = f"데이터가 {age_minutes:.1f}분 지연되어 판정 보류"
        write_summary(move, None, previous_stage, status)
        return {"alerted": False, "stage": None, "previous_stage": previous_stage, "age_minutes": age_minutes}

    stage = determine_stage(move)
    checked_at_kst = current.astimezone(KST).isoformat(timespec="seconds")
    state_text = current_state(move)
    triggers = trigger_windows(stage, move) if stage in (1, 2) else []
    pending = {
        "stage": stage,
        "last_alert_at_kst": previous.get("last_alert_at_kst"),
        "last_checked_at_kst": checked_at_kst,
        "latest_price": move.latest_price,
        "change_15m_pct": move.change_15m_pct,
        "change_30m_pct": move.change_30m_pct,
        "change_60m_pct": move.change_60m_pct,
        "current_state": state_text,
        "trigger_windows": triggers,
    }

    if stage > previous_stage:
        pending["last_alert_at_kst"] = checked_at_kst
        title = f"🚨 USD/JPY 급변 {stage}단계 — {title_state(stage, move)}"
        body = build_body(stage, move, current)
        ALERT_TITLE_PATH.write_text(title + "\n", encoding="utf-8")
        ALERT_BODY_PATH.write_text(body + "\n", encoding="utf-8")
        write_json(
            ALERT_JSON_PATH,
            {
                "stage": stage,
                "move": asdict(move),
                "current_state": state_text,
                "trigger_windows": triggers,
                "checked_at_kst": checked_at_kst,
            },
        )
        write_json(PENDING_STATE_PATH, pending)
        write_summary(move, stage, previous_stage, "신규 또는 상위 단계 급변 경보 생성")
        return {
            "alerted": True,
            "stage": stage,
            "previous_stage": previous_stage,
            "current_state": state_text,
            "trigger_windows": triggers,
            "move": asdict(move),
        }

    if stage != previous_stage:
        write_json(STATE_PATH, pending)
        status = "급변 해제·하향 단계 상태 갱신"
    else:
        status = "같은 단계 유지·중복 알림 없음"
    write_summary(move, stage, previous_stage, status)
    return {
        "alerted": False,
        "stage": stage,
        "previous_stage": previous_stage,
        "current_state": state_text,
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
