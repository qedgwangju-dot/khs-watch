#!/usr/bin/env python3
"""Integrate actual sector reaction tracking into the existing FX alert lane."""
from __future__ import annotations

import datetime as dt
import json
import os
import pathlib

from yen_sector_config import *
from yen_sector_data import capture_snapshot
from yen_sector_format import *

FX_ALERT_TITLE = pathlib.Path("out/yen_carry_fx_shock_alert_title.txt")
FX_ALERT_JSON = pathlib.Path("out/yen_carry_fx_shock_alert.json")
FX_ALERT_BODY = pathlib.Path("out/yen_carry_fx_shock_alert.md")
FX_STATE_PATH = pathlib.Path("data/yen_carry_fx_shock_state.json")
FX_PENDING_STATE_PATH = pathlib.Path("out/yen_carry_fx_shock_pending_state.json")
FX_SUMMARY_PATH = pathlib.Path("out/yen_carry_fx_shock_watch.md")

def read_json(path: pathlib.Path, default: dict) -> dict:
    if not path.exists():
        return dict(default)
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return dict(default)
    return value if isinstance(value, dict) else dict(default)


def write_json(path: pathlib.Path, value: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def append_summary(status: str, extra: list[str] | None = None) -> None:
    lines = ["", "## 업종 실측", f"- 상태: {status}"]
    if extra:
        lines.extend(f"- {item}" for item in extra)
    FX_SUMMARY_PATH.parent.mkdir(parents=True, exist_ok=True)
    with FX_SUMMARY_PATH.open("a", encoding="utf-8") as handle:
        handle.write("\n".join(lines) + "\n")


def event_close_epoch(alert_time: dt.datetime) -> float:
    local = alert_time.astimezone(KST)
    return local.replace(
        hour=CLOSE_CHECK_HOUR,
        minute=CLOSE_CHECK_MINUTE,
        second=0,
        microsecond=0,
    ).timestamp()


def new_event(
    fx_alert: dict,
    results: list[SectorResult],
    current: dt.datetime,
) -> dict:
    alert_time = parse_datetime(fx_alert.get("checked_at_kst")) or current
    local = alert_time.astimezone(KST)
    market_open = any(item.market_status == "장중" for item in results)
    close_epoch = event_close_epoch(alert_time)
    thirty_due = (
        alert_time.timestamp() + THIRTY_MINUTE_DELAY * 60
        if market_open and (local.hour, local.minute) <= (15, 0)
        else None
    )
    close_due = (
        close_epoch if market_open and alert_time.timestamp() < close_epoch else None
    )
    return {
        "event_id": f"{int(alert_time.timestamp())}-{fx_alert.get('stage', 0)}",
        "alert_epoch": alert_time.timestamp(),
        "alert_at_kst": alert_time.astimezone(KST).isoformat(timespec="seconds"),
        "event_date_kst": local.date().isoformat(),
        "fx_stage": int(fx_alert.get("stage") or 0),
        "fast_stage": int(fx_alert.get("fast_stage") or 0),
        "sustained_stage": int(fx_alert.get("sustained_stage") or 0),
        "fx_price": finite((fx_alert.get("move") or {}).get("latest_price")),
        "baseline": result_baseline(results),
        "immediate_confidence": confidence_label(results),
        "thirty_due_epoch": thirty_due,
        "close_due_epoch": close_due,
        "thirty_done": thirty_due is None,
        "close_done": close_due is None,
        "thirty_confidence": None,
        "close_confidence": None,
        "created_at_kst": current.astimezone(KST).isoformat(timespec="seconds"),
    }


def install_new_event(state: dict, event: dict) -> dict:
    state = dict(state)
    history = list(state.get("sector_reaction_history") or [])
    previous = state.get("sector_reaction")
    if isinstance(previous, dict):
        archived = dict(previous)
        archived["status"] = "superseded_by_new_fx_alert"
        history.append(archived)
    state["sector_reaction"] = event
    state["sector_reaction_history"] = history[-HISTORY_LIMIT:]
    return state


def archive_if_complete(state: dict) -> dict:
    state = dict(state)
    event = state.get("sector_reaction")
    if not isinstance(event, dict):
        return state
    if event.get("thirty_done") and event.get("close_done"):
        archived = dict(event)
        archived["status"] = "completed"
        history = list(state.get("sector_reaction_history") or [])
        history.append(archived)
        state["sector_reaction_history"] = history[-HISTORY_LIMIT:]
        state["sector_reaction"] = None
    return state


def aggregate_since_baseline(
    result: SectorResult,
    baseline: dict,
    quotes: dict[str, QuoteSeries],
) -> tuple[float, float, float] | None:
    component_returns: list[float] = []
    for symbol, base_price in (baseline.get("component_prices") or {}).items():
        quote = quotes.get(symbol)
        price = finite(base_price)
        if quote is not None and price is not None and price > 0:
            component_returns.append(((quote.latest_price - price) / price) * 100)
    sector_return = median(component_returns)
    benchmark_symbol = "^TOPX" if result.country == "JP" else "^KS11"
    benchmark_quote = quotes.get(benchmark_symbol)
    benchmark_base = finite(baseline.get("benchmark_price"))
    if (
        sector_return is None
        or benchmark_quote is None
        or benchmark_base is None
        or benchmark_base <= 0
    ):
        return None
    benchmark_return = (
        (benchmark_quote.latest_price - benchmark_base) / benchmark_base
    ) * 100
    return sector_return, benchmark_return, sector_return - benchmark_return


def followup_rows(
    event: dict,
    current: dt.datetime,
    kind: str,
) -> tuple[list[dict], dict[str, str]]:
    results, errors, quotes = capture_snapshot(current)
    baseline = event.get("baseline") or {}
    specs = {spec.key: spec for spec in SECTORS}
    rows: list[dict] = []
    for result in results:
        base = baseline.get(result.key)
        if not base:
            continue
        since = aggregate_since_baseline(result, base, quotes)
        if since is None:
            continue
        sector_return, benchmark_return, relative = since
        threshold = (
            INTRADAY_MIN_RELATIVE_PCT
            if kind == "30분"
            else SESSION_MIN_RELATIVE_PCT
        )
        significant = abs(relative) >= threshold
        spec = specs[result.key]
        aligned = (
            spec.expected_sign != 0
            and significant
            and relative * spec.expected_sign > 0
        )
        contrary = (
            spec.expected_sign != 0
            and significant
            and relative * spec.expected_sign < 0
        )
        rows.append(
            {
                "key": result.key,
                "name": result.name,
                "role": result.role,
                "expected_sign": spec.expected_sign,
                "sector_return_pct": sector_return,
                "benchmark_return_pct": benchmark_return,
                "relative_pct": relative,
                "significant": significant,
                "aligned": aligned,
                "contrary": contrary,
                "market_status": result.market_status,
            }
        )
    return rows, errors


def followup_confidence(rows: list[dict]) -> str:
    aligned = sum(bool(row.get("aligned")) for row in rows)
    contrary = sum(bool(row.get("contrary")) for row in rows)
    if contrary >= 2 or (aligned > 0 and contrary > 0):
        return "혼재"
    if aligned >= 3 and contrary == 0:
        return "높음"
    if aligned >= 2:
        return "중간"
    return "미확인"


def followup_line(row: dict) -> str:
    if row.get("expected_sign") == 0:
        verdict = "환율 직접 영향 판단 보류"
    elif row.get("aligned"):
        verdict = "예상 방향 확인"
    elif row.get("contrary"):
        verdict = "예상과 반대"
    else:
        verdict = "유의한 상대변동 미확인"
    return (
        f"• {row['name']}: 경보 후 {row['sector_return_pct']:+.2f}% / "
        f"시장 {row['benchmark_return_pct']:+.2f}% → "
        f"상대 {row['relative_pct']:+.2f}%p · {verdict}"
    )


def build_followup_message(
    event: dict,
    rows: list[dict],
    kind: str,
    current: dt.datetime,
) -> tuple[str, str, dict]:
    confidence = followup_confidence(rows)
    ordered = sorted(
        rows,
        key=lambda row: (row.get("significant", False), abs(row["relative_pct"])),
        reverse=True,
    )
    semis = [row for row in ordered if row["key"] == "kr_semis"]
    others = [row for row in ordered if row["key"] != "kr_semis"]
    display = others[:5] + semis[:1]
    title = f"📊 엔화 강세 업종 반응 — {kind} 확인"
    body = "\n".join(
        [
            f"확인 시각: {current.astimezone(KST).strftime('%Y-%m-%d %H:%M:%S KST')}",
            f"원 경보: {event.get('alert_at_kst')} · USD/JPY {event.get('fx_price')}",
            "기준: 경보 시점 이후 업종 수익률 - TOPIX·KOSPI 수익률",
            "",
            *(followup_line(row) for row in display),
            "",
            f"종합 판정: 엔화 강세 연동 가능성 {confidence}",
            "주의: 상대수익률은 연동 가능성을 보여줄 뿐 환율이 유일한 원인임을 뜻하지 않습니다.",
        ]
    )
    payload = {
        "sector_followup": True,
        "kind": kind,
        "event_id": event.get("event_id"),
        "confidence": confidence,
        "rows": rows,
        "checked_at_kst": current.astimezone(KST).isoformat(timespec="seconds"),
    }
    return title, body, payload


def handle_new_fx_alert(current: dt.datetime) -> dict:
    fx_alert = read_json(FX_ALERT_JSON, {})
    results, errors, _quotes = capture_snapshot(current)
    body = FX_ALERT_BODY.read_text(encoding="utf-8")
    FX_ALERT_BODY.write_text(
        replace_sector_block(body, observed_sector_block(results, errors)),
        encoding="utf-8",
    )
    pending = read_json(
        FX_PENDING_STATE_PATH,
        read_json(FX_STATE_PATH, {"stage": 0}),
    )
    pending = install_new_event(pending, new_event(fx_alert, results, current))
    write_json(FX_PENDING_STATE_PATH, pending)
    append_summary(
        "새 환율 경보에 실제 업종 스냅샷 추가",
        [
            f"업종 결과 {len(results)}개",
            f"조회 실패 {len(errors)}개",
            f"연동 가능성 {confidence_label(results)}",
        ],
    )
    return {
        "mode": "new_fx_alert",
        "results": len(results),
        "errors": len(errors),
    }


def handle_followup(current: dt.datetime) -> dict:
    state = read_json(FX_STATE_PATH, {"stage": 0})
    event = state.get("sector_reaction")
    if not isinstance(event, dict):
        append_summary("활성 업종 추적 이벤트 없음")
        return {"mode": "idle"}

    now = current.timestamp()
    due_kind: str | None = None
    due_epoch: float | None = None
    if not event.get("thirty_done") and event.get("thirty_due_epoch") is not None:
        due_epoch = float(event["thirty_due_epoch"])
        if now >= due_epoch:
            due_kind = "30분"
    if (
        due_kind is None
        and not event.get("close_done")
        and event.get("close_due_epoch") is not None
    ):
        due_epoch = float(event["close_due_epoch"])
        if now >= due_epoch:
            due_kind = "장 마감"

    if due_kind is None:
        append_summary("업종 후속 확인 대기", [f"이벤트 {event.get('event_id')}"])
        return {"mode": "waiting"}

    rows, errors = followup_rows(event, current, due_kind)
    if (
        len(rows) < 3
        and due_epoch is not None
        and now < due_epoch + FOLLOWUP_RETRY_MINUTES * 60
    ):
        append_summary(
            f"{due_kind} 데이터 부족·재시도 대기",
            [f"유효 업종 {len(rows)}개", f"조회 실패 {len(errors)}개"],
        )
        return {"mode": "retry", "kind": due_kind, "rows": len(rows)}

    event = dict(event)
    confidence = followup_confidence(rows)
    if due_kind == "30분":
        event["thirty_done"] = True
        event["thirty_confidence"] = confidence
    else:
        event["close_done"] = True
        event["close_confidence"] = confidence

    updated = dict(state)
    updated["sector_reaction"] = event
    should_send = bool(rows) and (
        confidence != "미확인"
        or int(event.get("sustained_stage") or 0) > 0
    )
    if should_send:
        title, body, payload = build_followup_message(
            event, rows, due_kind, current
        )
        FX_ALERT_TITLE.write_text(title + "\n", encoding="utf-8")
        FX_ALERT_BODY.write_text(body + "\n", encoding="utf-8")
        write_json(FX_ALERT_JSON, payload)
        write_json(FX_PENDING_STATE_PATH, archive_if_complete(updated))
        append_summary(
            f"{due_kind} 업종 반응 알림 생성",
            [f"유효 업종 {len(rows)}개", f"연동 가능성 {confidence}"],
        )
        return {
            "mode": "alert",
            "kind": due_kind,
            "confidence": confidence,
        }

    updated = archive_if_complete(updated)
    write_json(FX_STATE_PATH, updated)
    append_summary(
        f"{due_kind} 업종 반응 기록·텔레그램 생략",
        [f"유효 업종 {len(rows)}개", f"연동 가능성 {confidence}"],
    )
    return {
        "mode": "recorded",
        "kind": due_kind,
        "confidence": confidence,
    }


def process(current: dt.datetime | None = None) -> dict:
    current = (current or dt.datetime.now(UTC)).astimezone(UTC)
    if FX_ALERT_JSON.exists() and FX_ALERT_BODY.exists():
        alert = read_json(FX_ALERT_JSON, {})
        if not alert.get("sector_followup"):
            return handle_new_fx_alert(current)

    followup = handle_followup(current)
    if (
        followup.get("mode") == "idle"
        and os.getenv("TELEGRAM_DRY_RUN", "false").strip().lower() == "true"
    ):
        results, errors, _ = capture_snapshot(current)
        confidence = confidence_label(results)
        append_summary(
            "PR 업종 실측 검증",
            [
                f"유효 업종 {len(results)}개",
                f"조회 실패 {len(errors)}개",
                f"환율 연동 가능성 {confidence}",
            ],
        )
        return {
            "mode": "validation",
            "results": len(results),
            "errors": len(errors),
            "confidence": confidence,
        }
    return followup
