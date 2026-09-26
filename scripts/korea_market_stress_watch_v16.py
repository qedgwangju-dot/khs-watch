#!/usr/bin/env python3
from __future__ import annotations

import datetime as dt
import json
import re
from typing import Any

import requests

import korea_market_stress_watch_v15 as v15

watch = v15.watch
core = v15.core
v10 = core.v10

DUAL_SOURCE_TOLERANCE_EOK = 1.0
FALLBACK_STABILITY_TOLERANCE_EOK = 1.0
FALLBACK_MIN_OBSERVATIONS = 2
FALLBACK_MIN_MINUTES = 10.0
# KRX current public page says same-day final investor trading data are provided after 20:00.
# Use 20:10 KST as a conservative confirmation gate.
FINAL_START = dt.time(20, 10)

# USD/KRW re-alerts: first at the existing +1% / +20 won threshold, then
# re-alert whenever severity worsens by another +0.5%p or +10 won.
FX_STAGE_KRW_BASE = 20.0
FX_STAGE_KRW_STEP = 10.0
FX_STAGE_PCT_BASE = 1.0
FX_STAGE_PCT_STEP = 0.5

_ORIGINAL_ADD_EVENT = watch.add_event
_ORIGINAL_KOSDAQ_HIT_KEYS = v10._kosdaq_hit_keys
_ORIGINAL_MARKET_FLOW_LINES = v10._market_flow_lines
_ORIGINAL_FINAL_PERSIST = v15._persist_final_history
_ORIGINAL_SAFE_LS_PERSIST = v15._safe_persist_ls_history
_ORIGINAL_LS_TOL_EOK = core.LS_DAILY_TOLERANCE_EOK
_ORIGINAL_LS_TOL_PCT = core.LS_DAILY_TOLERANCE_PCT
_ORIGINAL_FETCH_KOSPI_FLOW = watch.fetch_kospi_foreign_flow
_ORIGINAL_FETCH_KOSDAQ_FLOW = v10._fetch_kosdaq_foreign_flow
_ORIGINAL_V15_LOAD_FINAL = v15._load_final_history

_INDEX_HISTORY_URLS = {
    "KOSPI": "https://m.stock.naver.com/api/index/KOSPI/price?pageSize=30&page=1",
    "KOSDAQ": "https://m.stock.naver.com/api/index/KOSDAQ/price?pageSize=30&page=1",
}

_candidate_cache: dict[str, dict[str, Any]] = {}
_recent_trade_dates_cache: dict[str, set[str]] = {}


def _state() -> dict[str, Any]:
    try:
        return watch.load_state() or {}
    except Exception:
        return {}


def _recent_trade_dates(market: str) -> set[str]:
    if market in _recent_trade_dates_cache:
        return set(_recent_trade_dates_cache[market])
    url = _INDEX_HISTORY_URLS[market]
    r = requests.get(url, headers=watch.HEADERS, timeout=20)
    r.raise_for_status()
    rows = r.json()
    if not isinstance(rows, list) or not rows:
        raise RuntimeError(f"{market} 최근 거래일 목록 조회 실패")
    dates = {
        str(row.get("localTradedAt") or "")[:10]
        for row in rows
        if re.fullmatch(r"\d{4}-\d{2}-\d{2}", str(row.get("localTradedAt") or "")[:10])
    }
    if not dates:
        raise RuntimeError(f"{market} 최근 거래일 날짜 없음")
    _recent_trade_dates_cache[market] = set(dates)
    return set(dates)


def _canonical_trade_date(market: str) -> str | None:
    try:
        dates = _recent_trade_dates(market)
        if dates:
            return max(dates)
    except Exception:
        pass
    state = _state()
    snap = state.get("snapshot") or {}
    key = "kospi_close" if market == "KOSPI" else "kosdaq_close"
    row = snap.get(key) or {}
    d = str(row.get("date") or "")
    if re.fullmatch(r"\d{4}-\d{2}-\d{2}", d):
        return d
    return None


def _sanitized_final_history(market: str) -> list[dict[str, Any]]:
    rows = _ORIGINAL_V15_LOAD_FINAL(market)
    try:
        valid_dates = _recent_trade_dates(market)
    except Exception:
        valid_dates = set()
    latest = _canonical_trade_date(market)
    out: list[dict[str, Any]] = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        try:
            d = str(row.get("date") or "")
            value = float(row.get("daily_eok"))
            day = dt.date.fromisoformat(d)
        except Exception:
            continue
        if valid_dates:
            if d not in valid_dates:
                continue
        else:
            if day.weekday() >= 5:
                continue
            if latest and d > latest:
                continue
        out.append({"date": d, "daily_eok": value})
    by_date = {row["date"]: float(row["daily_eok"]) for row in out}
    return [{"date": d, "daily_eok": v} for d, v in sorted(by_date.items())][-10:]


def _recompute_three_day(market: str, trade_date: str, daily_eok: float) -> tuple[float | None, list[dict[str, Any]]]:
    by_date = {row["date"]: float(row["daily_eok"]) for row in _sanitized_final_history(market)}
    by_date[trade_date] = float(daily_eok)
    rows = [{"date": d, "daily_eok": v} for d, v in sorted(by_date.items()) if d <= trade_date][-10:]
    if len(rows) < 3:
        return None, rows
    return sum(float(row["daily_eok"]) for row in rows[-3:]), rows


def _canonicalize_flow(original, market: str, now: dt.datetime) -> dict[str, Any]:
    flow = original(now)
    trade_date = _canonical_trade_date(market)
    validation = flow.get("ls_validation") if isinstance(flow, dict) else None
    status = str((validation or {}).get("status") or "")
    if status == "ls_fallback" and trade_date:
        daily_eok = float(flow.get("daily_eok") or 0.0)
        three_eok, rows = _recompute_three_day(market, trade_date, daily_eok)
        flow["date"] = trade_date
        flow["three_day_eok"] = three_eok if three_eok is not None else 0.0
        flow["three_day_krw"] = int(round(three_eok * 100_000_000)) if three_eok is not None else 0
        flow["three_day_available"] = three_eok is not None
        flow["phase"] = f"LS증권 t1601 대체값 · 실제 거래일 {trade_date} 기준"
        if isinstance(validation, dict):
            validation["canonical_trade_date"] = trade_date
            validation["history_count"] = len(rows)
    return flow


def _fetch_kospi_canonical(now: dt.datetime) -> dict[str, Any]:
    return _canonicalize_flow(_ORIGINAL_FETCH_KOSPI_FLOW, "KOSPI", now)


def _fetch_kosdaq_canonical(now: dt.datetime) -> dict[str, Any]:
    return _canonicalize_flow(_ORIGINAL_FETCH_KOSDAQ_FLOW, "KOSDAQ", now)


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


def _history_value(state: dict[str, Any], market: str, trade_date: str) -> float | None:
    for row in (state.get("final_flow_history") or {}).get(market) or []:
        if not isinstance(row, dict) or str(row.get("date") or "") != trade_date:
            continue
        try:
            return float(row.get("daily_eok"))
        except Exception:
            return None
    return None


def _candidate_for(market: str) -> dict[str, Any]:
    if market in _candidate_cache:
        return _candidate_cache[market]

    now = dt.datetime.now(watch.KST)
    row = dict(core._validation.get(market) or {})
    status = str(row.get("status") or "")
    state = _state()
    old = _seed_old_candidate(state, market)
    trade_date = _canonical_trade_date(market)
    result: dict[str, Any] = {
        "market": market,
        "date": trade_date or "",
        "checked_at": now.isoformat(timespec="seconds"),
        "status": status,
        "stable": False,
        "observations": 0,
        "reason": "교차검증 미완료",
    }

    if not trade_date:
        result["reason"] = "실제 거래일 확인 실패 · 수급 임계치 판정 보류"
        _candidate_cache[market] = result
        return result

    try:
        trade_day = dt.date.fromisoformat(trade_date)
    except Exception:
        result["reason"] = "실제 거래일 형식 오류 · 수급 임계치 판정 보류"
        _candidate_cache[market] = result
        return result

    try:
        current_value = float(row.get("ls_daily_eok"))
    except Exception:
        current_value = None

    historical = _history_value(state, market, trade_date)
    if trade_day < now.date():
        if (
            status in {"matched", "ls_fallback"}
            and current_value is not None
            and historical is not None
            and abs(current_value - historical) <= FALLBACK_STABILITY_TOLERANCE_EOK
        ):
            result.update({
                "value_eok": current_value,
                "stable": True,
                "observations": 2,
                "reason": f"최근 실제 거래일 {trade_date} 확정값 재조회 · 휴장일 신규 일별값 생성 금지",
            })
        else:
            if current_value is not None:
                result["value_eok"] = current_value
            result["reason"] = f"휴장·비거래일 · 최신 실제 거래일 {trade_date} 재조회값은 신규 수급 판정에 사용하지 않음"
        _candidate_cache[market] = result
        return result

    if trade_day > now.date():
        result["reason"] = "거래일 날짜가 현재일보다 미래 · 판정 보류"
        _candidate_cache[market] = result
        return result

    if status == "matched":
        result.update({
            "value_eok": float(row.get("ls_daily_eok") or 0.0),
            "stable": now.time() >= FINAL_START,
            "observations": 2 if now.time() >= FINAL_START else 0,
            "reason": (
                "네이버 장마감값과 LS t1601이 엄격 허용오차 내 일치"
                if now.time() >= FINAL_START
                else "20:10 이전 · KRX 최종 수급 확인 전"
            ),
        })
    elif status == "ls_fallback":
        value = float(row.get("ls_daily_eok") or 0.0)
        observations = 0 if now.time() < FINAL_START else 1
        prev_ts = _parse_ts(old.get("checked_at"))
        same_date = str(old.get("date") or "") == trade_date
        prev_is_post_final = bool(prev_ts and prev_ts.time() >= FINAL_START)
        try:
            prev_value = float(old.get("value_eok"))
        except Exception:
            prev_value = None
        elapsed_min = (now - prev_ts).total_seconds() / 60.0 if prev_ts else -1.0
        same_value = prev_value is not None and abs(value - prev_value) <= FALLBACK_STABILITY_TOLERANCE_EOK
        if (
            now.time() >= FINAL_START
            and same_date
            and prev_is_post_final
            and same_value
            and elapsed_min >= FALLBACK_MIN_MINUTES
        ):
            observations = max(1, int(old.get("observations") or 1)) + 1
        stable = now.time() >= FINAL_START and observations >= FALLBACK_MIN_OBSERVATIONS
        result.update({
            "value_eok": value,
            "observations": observations,
            "stable": stable,
            "reason": (
                "네이버 조회 실패 · 20:10 이후 LS t1601 단독값 2회 연속 안정성 확인 완료"
                if stable
                else (
                    "20:10 이전 · KRX 최종 수급 확인 전"
                    if now.time() < FINAL_START
                    else "네이버 조회 실패 · 20:10 이후 LS t1601 2회 연속 확인 대기"
                )
            ),
        })
    elif status == "mismatch":
        result["reason"] = "네이버와 LS 불일치 · 판정 보류"
    elif status == "ls_unavailable":
        result["reason"] = "LS 교차검증 실패 · 판정 보류"

    if now.time() < FINAL_START:
        result["stable"] = False
        result["observations"] = 0
        result["reason"] = "20:10 이전 · KRX 최종 수급 확인 전"

    _candidate_cache[market] = result
    return result

def _flow_event_allowed(market: str) -> bool:
    return bool(_candidate_for(market).get("stable"))


def _fx_escalation_event(key: str, text: str) -> tuple[str, str]:
    if not (key.startswith("fx_daily_up:") or key.startswith("fx_daily_down:")):
        return key, text

    m = re.search(r"\(([+-]?[0-9,.]+)원,\s*([+-]?[0-9.]+)%\)", text)
    if not m:
        return key, text
    try:
        change_krw = abs(float(m.group(1).replace(",", "")))
        change_pct = abs(float(m.group(2)))
    except Exception:
        return key, text

    stage_krw = 0
    if change_krw >= FX_STAGE_KRW_BASE:
        stage_krw = int((change_krw - FX_STAGE_KRW_BASE) // FX_STAGE_KRW_STEP) + 1
    stage_pct = 0
    if change_pct >= FX_STAGE_PCT_BASE:
        stage_pct = int((change_pct - FX_STAGE_PCT_BASE) // FX_STAGE_PCT_STEP) + 1
    stage = max(stage_krw, stage_pct)
    if stage <= 0:
        return key, text

    prefix, date = key.split(":", 1)
    staged_key = f"{prefix}_stage{stage}:{date}"
    staged_text = text + f" · <b>환율 변화 {stage}단계</b>"
    return staged_key, staged_text


def _canonicalize_event_key(key: str, market: str) -> str:
    trade_date = str(_candidate_for(market).get("date") or "")
    if not trade_date:
        return key
    return re.sub(r"\d{4}-\d{2}-\d{2}", trade_date, key, count=1)


def add_event_strict(events, key: str, text: str, source: str) -> None:
    if key.startswith("foreign1d_") or key.startswith("foreign3d_"):
        if not _flow_event_allowed("KOSPI"):
            return
        key = _canonicalize_event_key(key, "KOSPI")
    key, text = _fx_escalation_event(key, text)
    _ORIGINAL_ADD_EVENT(events, key, text, source)


def kosdaq_hit_keys_strict(flow: dict[str, Any] | None) -> list[str]:
    if not _flow_event_allowed("KOSDAQ"):
        return []
    if not flow:
        return []
    fixed = dict(flow)
    trade_date = str(_candidate_for("KOSDAQ").get("date") or "")
    if trade_date:
        fixed["date"] = trade_date
    return _ORIGINAL_KOSDAQ_HIT_KEYS(fixed)


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
    if not cand.get("stable"):
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
                    f" — 최종 확인 전 · 20:10 이후 연속 확인 {int(cand.get('observations') or 0)}/{FALLBACK_MIN_OBSERVATIONS}"
                )
                continue
            out.append(line)
        out.append("• 확정 규칙: 20:10 이후에만 최종 수급 판정 · 네이버 실패 시 LS 단독값은 20:10 이후 최소 10분 간격 2회 연속 동일 확인 필요")
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

    candidate_root = dict(old.get("flow_fallback_candidate") or {})
    for market in ("KOSPI", "KOSDAQ"):
        candidate_root[market] = _candidate_for(market)
    pending["flow_fallback_candidate"] = candidate_root
    pending.pop("ls_flow_history", None)

    final_root: dict[str, list[dict[str, Any]]] = {}
    snap = pending.get("snapshot") or {}
    for market in ("KOSPI", "KOSDAQ"):
        cand = _candidate_for(market)
        trade_date = str(cand.get("date") or "")
        by_date = {row["date"]: float(row["daily_eok"]) for row in _sanitized_final_history(market)}

        key = "foreign_flow" if market == "KOSPI" else "kosdaq_foreign_flow"
        flow = snap.get(key) or {}
        if flow and trade_date:
            flow["date"] = trade_date

        if flow and trade_date and cand.get("stable"):
            try:
                by_date[trade_date] = float(flow.get("daily_eok"))
            except Exception:
                pass

        rows = [{"date": d, "daily_eok": v} for d, v in sorted(by_date.items())][-10:]
        final_root[market] = rows

        if flow:
            status = str((flow.get("ls_validation") or {}).get("status") or "")
            if status == "ls_fallback":
                flow["source_label"] = (
                    "LS증권 t1601 확정 대체값" if cand.get("stable") else "LS증권 t1601 잠정 대체값"
                )

            eligible = [row for row in rows if not trade_date or row["date"] <= trade_date]
            if trade_date and trade_date in by_date and len(eligible) >= 3:
                three = sum(float(x["daily_eok"]) for x in eligible[-3:])
                flow["three_day_eok"] = three
                flow["three_day_krw"] = int(round(three * 100_000_000))
                flow["three_day_available"] = True
                flow["finality"] = "확정" if cand.get("stable") else "잠정"
            else:
                flow["three_day_available"] = False
                flow["finality"] = "잠정"
            snap[key] = flow

    today = dt.datetime.now(watch.KST).date().isoformat()
    active = list(pending.get("active_keys") or [])
    for prefix in ("foreign1d_", "foreign3d_", "kosdaq_foreign1d_", "kosdaq_foreign3d_"):
        active = [x for x in active if not (str(x).startswith(prefix) and today in str(x))]
    pending["active_keys"] = active

    pending["final_flow_history"] = final_root
    snap["flow_finality_rule"] = (
        "KRX 투자자별 거래실적의 현재 공개 안내(당일 최종 매매내역 오후 8시 이후)에 맞춰 20:10 이후에만 당일 최종 판정. "
        "거래일 날짜는 KOSPI·KOSDAQ 지수의 실제 최근 종가 거래일과 일치시켜 주말·공휴일을 신규 일별 수급으로 저장하지 않음. "
        "네이버+LS t1601이 1억원 이내 일치하면 확정, 네이버 실패 시 실제 거래일 당일 20:10 이후 LS 단독값이 최소 10분 간격 2회 연속 동일해야 확정. "
        "3거래일 누적은 실제 거래일로 정제된 final_flow_history의 확정 일별값만 합산. 기준 시장은 KRX(KOSPI/KOSDAQ)이며 KRX+NXT 합산 수치와 혼용하지 않음."
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
    text = text.replace(
        "• 판정 시점: 두 시장 모두 18:10 이후 장마감 수급 피드",
        "• 판정 시점: 두 시장 모두 <b>20:10 이후 최종 수급 확인</b> — 그 전 값은 잠정",
    )
    old = (
        "• 수급 숫자 검증: <b>18:10 이후 네이버 장마감값 + LS증권 OpenAPI t1601 투자자별종합 교차검증</b>"
        " / 네이버 실패 시 LS 대체 / 유의한 불일치 시 임계치 판정 보류"
    )
    new = (
        "• 수급 숫자 검증: <b>KRX 시장 기준 · 20:10 이후 네이버 + LS증권 t1601 엄격 교차검증</b>"
        " / 1억원 이내 일치 시 확정 / 네이버 실패 시 20:10 이후 LS 단독값을 10분 이상 간격으로 2회 연속 동일 확인 후 확정"
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
    watch.fetch_kospi_foreign_flow = _fetch_kospi_canonical
    v10._fetch_kosdaq_foreign_flow = _fetch_kosdaq_canonical
    watch.add_event = add_event_strict
    v10._kosdaq_hit_keys = kosdaq_hit_keys_strict
    v10._market_flow_lines = market_flow_lines_strict
    v15._load_final_history = _sanitized_final_history
    v15._persist_final_history = _persist_candidates_and_final_history
    v15._safe_persist_ls_history = _safe_no_ls_history
    try:
        rc = v15.main()
    finally:
        core.LS_DAILY_TOLERANCE_EOK = _ORIGINAL_LS_TOL_EOK
        core.LS_DAILY_TOLERANCE_PCT = _ORIGINAL_LS_TOL_PCT
        watch.fetch_kospi_foreign_flow = _ORIGINAL_FETCH_KOSPI_FLOW
        v10._fetch_kosdaq_foreign_flow = _ORIGINAL_FETCH_KOSDAQ_FLOW
        watch.add_event = _ORIGINAL_ADD_EVENT
        v10._kosdaq_hit_keys = _ORIGINAL_KOSDAQ_HIT_KEYS
        v10._market_flow_lines = _ORIGINAL_MARKET_FLOW_LINES
        v15._load_final_history = _ORIGINAL_V15_LOAD_FINAL
        v15._persist_final_history = _ORIGINAL_FINAL_PERSIST
        v15._safe_persist_ls_history = _ORIGINAL_SAFE_LS_PERSIST
    _postprocess_source_note()
    return rc


if __name__ == "__main__":
    raise SystemExit(main())