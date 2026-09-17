#!/usr/bin/env python3
from __future__ import annotations

import datetime as dt
import json
from typing import Any

import korea_market_stress_watch_v15 as v15

watch = v15.watch
core = v15.core
v10 = core.v10

DUAL_SOURCE_TOLERANCE_EOK = 1.0
FALLBACK_STABILITY_TOLERANCE_EOK = 1.0
FALLBACK_MIN_OBSERVATIONS = 2
FALLBACK_MIN_MINUTES = 10.0
FINAL_START = dt.time(18, 10)

_ORIGINAL_ADD_EVENT = watch.add_event
_ORIGINAL_KOSDAQ_HIT_KEYS = v10._kosdaq_hit_keys
_ORIGINAL_MARKET_FLOW_LINES = v10._market_flow_lines
_ORIGINAL_FINAL_PERSIST = v15._persist_final_history
_ORIGINAL_SAFE_LS_PERSIST = v15._safe_persist_ls_history
_ORIGINAL_LS_TOL_EOK = core.LS_DAILY_TOLERANCE_EOK
_ORIGINAL_LS_TOL_PCT = core.LS_DAILY_TOLERANCE_PCT

_candidate_cache: dict[str, dict[str, Any]] = {}


def _state() -> dict[str, Any]:
    try:
        return watch.load_state() or {}
    except Exception:
        return {}


def _parse_ts(value: Any) -> dt.datetime | None:
    try:
        x = dt.datetime.fromisoformat(str(value))
        if x.tzinfo is None:
            x = x.replace(tzinfo=watch.KST)
        return x.astimezone(watch.KST)
    except Exception:
        return None


def _seed_old_candidate(state: dict[str, Any], market: str) -> dict[str, Any]:
    old = ((state.get("flow_fallback_candidate") or {}).get(market) or {})
    if old:
        return dict(old)
    snap = state.get("snapshot") or {}
    key = "foreign_flow" if market == "KOSPI" else "kosdaq_foreign_flow"
    flow = snap.get(key) or {}
    val = flow.get("ls_validation") if isinstance(flow, dict) else None
    if not isinstance(val, dict) or val.get("status") != "ls_fallback":
        return {}
    try:
        value = float(val.get("ls_daily_eok"))
    except Exception:
        return {}
    return {
        "market": market,
        "date": str(flow.get("date") or ""),
        "checked_at": str(snap.get("checked_at_kst") or state.get("updated_at_kst") or ""),
        "status": "ls_fallback",
        "value_eok": value,
        "observations": 1,
        "stable": False,
        "reason": "직전 정상 실행의 LS 단독 대체값",
    }


def _candidate_for(market: str) -> dict[str, Any]:
    if market in _candidate_cache:
        return _candidate_cache[market]

    now = dt.datetime.now(watch.KST)
    row = dict(core._validation.get(market) or {})
    status = str(row.get("status") or "")
    state = _state()
    old = _seed_old_candidate(state, market)
    result: dict[str, Any] = {
        "market": market,
        "date": now.date().isoformat(),
        "checked_at": now.isoformat(timespec="seconds"),
        "status": status,
        "stable": False,
        "observations": 0,
        "reason": "교차검증 미완료",
    }

    if status == "matched":
        result.update({
            "value_eok": float(row.get("ls_daily_eok") or 0.0),
            "stable": True,
            "observations": 2,
            "reason": "네이버 장마감값과 LS t1601이 엄격 허용오차 내 일치",
        })
    elif status == "ls_fallback":
        value = float(row.get("ls_daily_eok") or 0.0)
        observations = 1
        prev_ts = _parse_ts(old.get("checked_at"))
        same_date = str(old.get("date") or "") == now.date().isoformat()
        try:
            prev_value = float(old.get("value_eok"))
        except Exception:
            prev_value = None
        elapsed_min = (now - prev_ts).total_seconds() / 60.0 if prev_ts else -1.0
        same_value = prev_value is not None and abs(value - prev_value) <= FALLBACK_STABILITY_TOLERANCE_EOK
        if same_date and same_value and elapsed_min >= FALLBACK_MIN_MINUTES:
            observations = int(old.get("observations") or 1) + 1
        result.update({
            "value_eok": value,
            "observations": observations,
            "stable": observations >= FALLBACK_MIN_OBSERVATIONS,
            "reason": (
                "네이버 조회 실패 · LS t1601 단독값 2회 연속 안정성 확인 완료"
                if observations >= FALLBACK_MIN_OBSERVATIONS
                else "네이버 조회 실패 · LS t1601 단독값 2회 연속 확인 대기"
            ),
        })
    elif status == "mismatch":
        result["reason"] = "네이버와 LS 불일치 · 판정 보류"
    elif status == "ls_unavailable":
        result["reason"] = "LS 교차검증 실패 · 판정 보류"

    if now.time() < FINAL_START:
        result["stable"] = False
        result["reason"] = "18:10 이전 · 장마감 최종 수급 판정 전"

    _candidate_cache[market] = result
    return result


def _flow_event_allowed(market: str) -> bool:
    return bool(_candidate_for(market).get("stable"))


def add_event_strict(events, key: str, text: str, source: str) -> None:
    if key.startswith("foreign1d_") or key.startswith("foreign3d_"):
        if not _flow_event_allowed("KOSPI"):
            return
    _ORIGINAL_ADD_EVENT(events, key, text, source)


def kosdaq_hit_keys_strict(flow: dict[str, Any] | None) -> list[str]:
    if not _flow_event_allowed("KOSDAQ"):
        return []
    return _ORIGINAL_KOSDAQ_HIT_KEYS(flow)


def market_flow_lines_strict(
    market: str,
    idx: dict[str, Any] | None,
    flow: dict[str, Any] | None,
    daily_threshold: int,
    three_day_threshold: int,
) -> list[str]:
    lines = _ORIGINAL_MARKET_FLOW_LINES(market, idx, flow, daily_threshold, three_day_threshold)
    if not flow:
        return lines
    cand = _candidate_for(market)
    status = str((flow.get("ls_validation") or {}).get("status") or "")
    if status == "ls_fallback" and not cand.get("stable"):
        out: list[str] = []
        replace_next = False
        for line in lines:
            if replace_next and line.startswith("  ↳"):
                out.append("  ↳ <b>잠정값 — 수급 임계치 판정 보류</b>")
                replace_next = False
                continue
            if line.startswith("• 외국인 1일") or line.startswith("• 외국인 3거래일 누적"):
                out.append(line)
                replace_next = True
                continue
            if line.startswith("• LS t1601 대체값 사용"):
                out.append(
                    f"• LS t1601 잠정 대체값  <b>{float((flow.get('ls_validation') or {}).get('ls_daily_eok') or 0):+,.0f}억원</b>"
                    f" — 네이버 실패 · 연속 확인 {int(cand.get('observations') or 1)}/{FALLBACK_MIN_OBSERVATIONS}"
                )
                continue
            out.append(line)
        out.append("• 확정 규칙: LS 단독 대체값은 최소 10분 간격 2회 연속 동일 확인 후에만 수급 경보·3일 누적 확정")
        return out
    if status == "ls_fallback" and cand.get("stable"):
        return [
            line.replace("• LS t1601 대체값 사용", "• LS t1601 대체값 2회 안정성 확인 완료")
            for line in lines
        ]
    return lines


def _persist_candidates_and_final_history() -> None:
    if not watch.PENDING_PATH.exists():
        return
    try:
        pending = json.loads(watch.PENDING_PATH.read_text(encoding="utf-8"))
        old = _state()
    except Exception:
        return

    now = dt.datetime.now(watch.KST)
    today = now.date().isoformat()
    candidate_root = dict(old.get("flow_fallback_candidate") or {})
    for market in ("KOSPI", "KOSDAQ"):
        candidate_root[market] = _candidate_for(market)
    pending["flow_fallback_candidate"] = candidate_root
    pending.pop("ls_flow_history", None)

    old_root = old.get("final_flow_history") or {}
    final_root: dict[str, list[dict[str, Any]]] = {}
    snap = pending.get("snapshot") or {}
    for market in ("KOSPI", "KOSDAQ"):
        cand = _candidate_for(market)
        by_date: dict[str, float] = dict(v15.FINAL_FLOW_SEED.get(market) or {})
        for row in old_root.get(market) or []:
            if not isinstance(row, dict):
                continue
            try:
                d = str(row.get("date") or "")
                val = float(row.get("daily_eok"))
            except Exception:
                continue
            if d:
                by_date[d] = val

        # Never retain a current-day value from an older, less strict version
        # unless today's value has passed v16 confirmation.
        if not cand.get("stable"):
            by_date.pop(today, None)

        key = "foreign_flow" if market == "KOSPI" else "kosdaq_foreign_flow"
        flow = snap.get(key) or {}
        if now.time() >= FINAL_START and cand.get("stable"):
            try:
                d = str(flow.get("date") or "")
                val = float(flow.get("daily_eok"))
                if d:
                    by_date[d] = val
            except Exception:
                pass

        rows = [{"date": d, "daily_eok": v} for d, v in sorted(by_date.items()) if d][-10:]
        final_root[market] = rows

        if flow:
            status = str((flow.get("ls_validation") or {}).get("status") or "")
            if status == "ls_fallback":
                flow["source_label"] = (
                    "LS증권 t1601 확정 대체값" if cand.get("stable") else "LS증권 t1601 잠정 대체값"
                )
            if cand.get("stable") and len(rows) >= 3:
                three = sum(float(x["daily_eok"]) for x in rows[-3:])
                flow["three_day_eok"] = three
                flow["three_day_krw"] = int(round(three * 100_000_000))
                flow["three_day_available"] = True
                flow["finality"] = "확정"
            else:
                flow["three_day_available"] = False
                flow["finality"] = "잠정"
            snap[key] = flow

    # If either market is still provisional, do not carry today's flow keys as active.
    active = list(pending.get("active_keys") or [])
    if not _candidate_for("KOSPI").get("stable"):
        active = [x for x in active if not (today in str(x) and (str(x).startswith("foreign1d_") or str(x).startswith("foreign3d_")))]
    if not _candidate_for("KOSDAQ").get("stable"):
        active = [x for x in active if not (today in str(x) and (str(x).startswith("kosdaq_foreign1d_") or str(x).startswith("kosdaq_foreign3d_")))]
    pending["active_keys"] = active

    pending["final_flow_history"] = final_root
    snap["flow_finality_rule"] = (
        "KRX 투자자별 거래실적의 당일 최종 매매내역 제공 시각(오후 6시 이후)에 맞춰 18:10 이후 판정. "
        "네이버+LS t1601이 1억원 이내 일치하면 즉시 확정, 네이버 실패 시 LS 단독값이 최소 10분 간격 2회 연속 동일해야 확정. "
        "3거래일 누적은 final_flow_history의 확정 일별값만 합산. 기준 시장은 KRX(KOSPI/KOSDAQ)이며 KRX+NXT 합산 수치와 혼용하지 않음."
    )
    pending["snapshot"] = snap
    watch.PENDING_PATH.write_text(json.dumps(pending, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def _safe_no_ls_history() -> None:
    original = dict(core._ls_history_updates)
    try:
        core._ls_history_updates.clear()
        v15._ORIGINAL_PERSIST_LS()
    finally:
        core._ls_history_updates.clear()
        core._ls_history_updates.update(original)


def _postprocess_source_note() -> None:
    if not watch.ALERT_PATH.exists():
        return
    text = watch.ALERT_PATH.read_text(encoding="utf-8")
    old = (
        "• 수급 숫자 검증: <b>18:10 이후 네이버 장마감값 + LS증권 OpenAPI t1601 투자자별종합 교차검증</b>"
        " / 네이버 실패 시 LS 대체 / 유의한 불일치 시 임계치 판정 보류"
    )
    new = (
        "• 수급 숫자 검증: <b>KRX 시장 기준 · 18:10 이후 네이버 + LS증권 t1601 엄격 교차검증</b>"
        " / 1억원 이내 일치 시 확정 / 네이버 실패 시 LS 단독값 10분 이상 간격 2회 연속 동일 확인 후 확정"
        " / 3거래일 누적은 확정 일별값만 합산 / KRX+NXT 합산 수치와 혼용하지 않음"
    )
    text = text.replace(old, new)
    watch.ALERT_PATH.write_text(text, encoding="utf-8")


def _reset_today_bad_flow_events_once() -> None:
    state = _state()
    today = dt.datetime.now(watch.KST).date().isoformat()
    if state.get("v16_flow_reset_date") == today:
        return
    prefixes = ("foreign1d_", "foreign3d_", "kosdaq_foreign1d_", "kosdaq_foreign3d_")
    def keep(key: Any) -> bool:
        s = str(key)
        return not (s.startswith(prefixes) and today in s)
    state["seen_event_keys"] = [x for x in state.get("seen_event_keys") or [] if keep(x)]
    state["active_keys"] = [x for x in state.get("active_keys") or [] if keep(x)]
    state["v16_flow_reset_date"] = today
    watch.STATE_PATH.write_text(json.dumps(state, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def main() -> int:
    _reset_today_bad_flow_events_once()
    core.LS_DAILY_TOLERANCE_EOK = DUAL_SOURCE_TOLERANCE_EOK
    core.LS_DAILY_TOLERANCE_PCT = 0.0
    watch.add_event = add_event_strict
    v10._kosdaq_hit_keys = kosdaq_hit_keys_strict
    v10._market_flow_lines = market_flow_lines_strict
    v15._persist_final_history = _persist_candidates_and_final_history
    v15._safe_persist_ls_history = _safe_no_ls_history
    try:
        rc = v15.main()
    finally:
        core.LS_DAILY_TOLERANCE_EOK = _ORIGINAL_LS_TOL_EOK
        core.LS_DAILY_TOLERANCE_PCT = _ORIGINAL_LS_TOL_PCT
        watch.add_event = _ORIGINAL_ADD_EVENT
        v10._kosdaq_hit_keys = _ORIGINAL_KOSDAQ_HIT_KEYS
        v10._market_flow_lines = _ORIGINAL_MARKET_FLOW_LINES
        v15._persist_final_history = _ORIGINAL_FINAL_PERSIST
        v15._safe_persist_ls_history = _ORIGINAL_SAFE_LS_PERSIST
    _postprocess_source_note()
    return rc


if __name__ == "__main__":
    raise SystemExit(main())
