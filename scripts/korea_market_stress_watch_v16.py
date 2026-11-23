#!/usr/bin/env python3
from __future__ import annotations

import contextlib
import datetime as dt
import html
import io
import json
import math
import re
import time
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
    # A cached close is context, not proof of the current trading date.
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


def _three_day_from_confirmed_dates(market: str, trade_date: str, by_date: dict[str, float]) -> float | None:
    """Reject stale 3-day sums when a real KRX trading date is missing.

    A missing date is not a zero-flow day. Index history is used ONLY to
    establish the last three actual trading dates, never to invent a flow.
    """
    try:
        expected = sorted(d for d in _recent_trade_dates(market) if d <= trade_date)[-3:]
    except Exception:
        return None
    if len(expected) != 3 or expected[-1] != trade_date:
        return None
    if any(day not in by_date for day in expected):
        return None
    return sum(float(by_date[day]) for day in expected)


def _recompute_three_day(market: str, trade_date: str, daily_eok: float) -> tuple[float | None, list[dict[str, Any]]]:
    by_date = {row["date"]: float(row["daily_eok"]) for row in _sanitized_final_history(market)}
    by_date[trade_date] = float(daily_eok)
    rows = [{"date": d, "daily_eok": v} for d, v in sorted(by_date.items()) if d <= trade_date][-10:]
    return _three_day_from_confirmed_dates(market, trade_date, by_date), rows


def _canonicalize_flow(original, market: str, now: dt.datetime) -> dict[str, Any]:
    trade_date = _canonical_trade_date(market)
    if not trade_date:
        raise RuntimeError(f"{market} 실제 거래일 원천 조회 실패")
    if trade_date != now.date().isoformat():
        # t1601 has no observation date. At the next session's pre-open it
        # can reset to zero; never relabel that quote as yesterday's flow.
        return {
            "date": trade_date, "daily_eok": 0.0, "daily_krw": 0,
            "three_day_eok": 0.0, "three_day_krw": 0,
            "three_day_available": False, "source": core.LS_GUIDE,
            "source_label": "일자 지정 과거 수급 확인 필요",
            "unavailable": True, "unavailable_reason": "최근 거래일과 조회일이 달라 t1601 장전 초기값 사용 금지",
        }
    flow = original(now)
    validation = flow.get("ls_validation") if isinstance(flow, dict) else None
    status = str((validation or {}).get("status") or "")
    if status == "matched" and str(flow.get("date") or "") != trade_date:
        core._validation.pop(market, None)
        raise RuntimeError(f"{market} 네이버와 실제 거래일 불일치")
    if status == "ls_fallback" and trade_date:
        daily_eok = float(flow.get("daily_eok"))
        if not math.isfinite(daily_eok):
            core._validation.pop(market, None)
            raise RuntimeError(f"{market} LS 수급 숫자 오류")
        if daily_eok == 0 and not any(core.ls.fnum((validation or {}).get(k)) not in (None, 0) for k in ("foreign_buy_eok", "foreign_sell_eok")):
            core._validation.pop(market, None)
            flow["unavailable"] = True
            flow["unavailable_reason"] = "LS 매수·매도·순매수 모두 0 또는 누락 — 실거래 확인 불가"
            flow["three_day_available"] = False
            return flow
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


def _ls_fallback_confirmation_count(old: dict[str, Any], current_eok: float, trade_date: str, now: dt.datetime) -> int:
    """Keep an already confirmed same-day LS quote confirmed across restarts."""
    if now.time() < FINAL_START:
        return 0
    prev_ts = _parse_ts(old.get("checked_at"))
    if not prev_ts or prev_ts.time() < FINAL_START or str(old.get("date") or "") != trade_date:
        return 1
    try:
        previous = float(old["value_eok"])
    except (KeyError, TypeError, ValueError):
        return 1
    if abs(float(current_eok) - previous) > FALLBACK_STABILITY_TOLERANCE_EOK:
        return 1
    elapsed = (now - prev_ts).total_seconds() / 60.0
    if elapsed < 0:
        return 1
    if old.get("stable") is True and int(old.get("observations") or 0) >= FALLBACK_MIN_OBSERVATIONS:
        return max(FALLBACK_MIN_OBSERVATIONS, int(old["observations"]))
    if elapsed >= FALLBACK_MIN_MINUTES:
        return max(1, int(old.get("observations") or 1)) + 1
    return 1


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
        observations = _ls_fallback_confirmation_count(old, value, trade_date, now)
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


def _direct_capex_percentage(text: str) -> bool:
    """Never use an EPS/share-price percentage as the capex change."""
    s = html.unescape(text)
    subject = r"(?:capex|capital expenditures?|capital spending)"
    modifier = r"(?:(?:guidance|forecast|outlook|budget|estimate|spending|plan)\s+)?"
    verb = r"(?:up|down|rise[sn]?|rose|fell|fall[sn]?|increase[sd]?|decrease[sd]?|raised|raise[sd]?|cut[s]?|reduced|revised|grow[sn]?|grew|climb[sd]?)"
    pct = r"([+-]?\d+(?:\.\d+)?)\s*%"
    patterns = (
        rf"\b{subject}\s+{modifier}(?:is\s+|was\s+|will\s+|to\s+)?{verb}\s+(?:by\s+)?{pct}",
        rf"\b{verb}\s+(?:(?:its|their|2026|2027|FY\d+|AI|annual)\s+){{0,3}}{subject}\s+{modifier}(?:by\s+)?{pct}",
    )
    return any(abs(float(m.group(1))) >= 10 for p in patterns for m in re.finditer(p, s, re.I))


def add_event_strict(events, key: str, text: str, source: str) -> None:
    if key.startswith("capex:") and not _direct_capex_percentage(text):
        return
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


def _confirmed_foreign_trading_detail(market: str, flow: dict[str, Any] | None, cand: dict[str, Any]) -> str:
    """Append actual market buy/sell only after all confirmations and rounding check."""
    if not flow or cand.get("stable") is not True or flow.get("finality") == "잠정":
        return "• 외국인 매수·매도 실제 금액: 검증 대기"
    validation = flow.get("ls_validation") or {}
    try:
        buy = float(validation["foreign_buy_eok"])
        sell = float(validation["foreign_sell_eok"])
        net = float(validation["ls_daily_eok"])
        daily = float(flow["daily_eok"])
    except (KeyError, ValueError, TypeError):
        return "• 외국인 매수·매도 실제 금액: 확인 불가(매수·매도 원자료 누락)"
    if not 0 <= buy <= 300_000 or not 0 <= sell <= 300_000:
        return "• 외국인 매수·매도 실제 금액: 비정상 범위 · 판정 보류"
    if abs(buy - sell - net) > 2.0 or abs(daily - net) > 2.0:
        return "• 외국인 매수·매도 실제 금액: 매수·매도·순매수 검산 불일치"
    direction = "순매수" if net > 0 else ("순매도" if net < 0 else "순매수")
    return (
        f"• {market} 외국인 매수 <b>{buy:,.0f}억원</b> / 매도 <b>{sell:,.0f}억원</b> / "
        f"{direction} <b>{abs(net):,.0f}억원</b> "
        "— KRX시장 전체 외국인 거래대금(헤지펀드 전용 자금 흐름 아님)"
    )


def market_flow_lines_strict(
    market: str,
    idx: dict[str, Any] | None,
    flow: dict[str, Any] | None,
    daily_threshold: int,
    three_day_threshold: int,
) -> list[str]:
    if flow and flow.get("unavailable"):
        lines = _ORIGINAL_MARKET_FLOW_LINES(market, idx, None, daily_threshold, three_day_threshold)
        lines.append("• 확정 수급 확인 대기: " + html.escape(str(flow.get("unavailable_reason") or "원천값 미확인")))
        return lines
    lines = _ORIGINAL_MARKET_FLOW_LINES(market, idx, flow, daily_threshold, three_day_threshold)
    if not flow:
        return lines
    cand = _candidate_for(market)
    status = str((flow.get("ls_validation") or {}).get("status") or "")
    if flow.get("three_day_available") is False:
        for i, line in enumerate(lines):
            if line.startswith("• 외국인 3거래일 누적"):
                lines[i] = "• 외국인 3거래일 누적  <b>확정 일별 수급 부족 · 확인 불가</b>"
                if i + 1 < len(lines) and lines[i+1].startswith("  ↳"):
                    lines[i+1] = "  ↳ 누적 경보 판정 보류"
                break
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
        out.append(_confirmed_foreign_trading_detail(market, flow, cand))
        out.append("• 확정 규칙: 20:10 이후에만 최종 수급 판정 · 네이버 실패 시 LS 단독값은 20:10 이후 최소 10분 간격 2회 연속 동일 확인 필요")
        return out
    if status == "ls_fallback" and cand.get("stable"):
        lines = [
            line.replace("• LS t1601 대체값 사용", "• LS t1601 대체값 2회 안정성 확인 완료")
            for line in lines
        ]
    return [*lines, _confirmed_foreign_trading_detail(market, flow, cand)]


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
        candidate = _candidate_for(market)
        # A pre-open/no-data observation must not erase the last dated,
        # post-final LS candidate needed for safe recovery.
        old_candidate = candidate_root.get(market) or {}
        if candidate.get("status") in {"matched", "ls_fallback"} and candidate.get("observations", 0) >= 1:
            candidate_root[market] = candidate
        elif not old_candidate:
            candidate_root[market] = candidate
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

        if flow and trade_date and cand.get("stable") and not flow.get("unavailable"):
            try:
                by_date[trade_date] = float(flow.get("daily_eok"))
            except Exception:
                pass

        rows = [{"date": d, "daily_eok": v} for d, v in sorted(by_date.items())][-10:]
        final_root[market] = rows

        if flow and flow.get("unavailable"):
            flow.update({"daily_eok": None, "daily_krw": None, "three_day_eok": None,
                         "three_day_krw": None, "three_day_available": False, "finality": "확인 불가"})
            snap[key] = flow
            continue
        if flow:
            status = str((flow.get("ls_validation") or {}).get("status") or "")
            if status == "ls_fallback":
                flow["source_label"] = (
                    "LS증권 t1601 확정 대체값" if cand.get("stable") else "LS증권 t1601 잠정 대체값"
                )

            three = _three_day_from_confirmed_dates(market, trade_date, by_date) if trade_date and trade_date in by_date else None
            if three is not None and cand.get("stable"):
                flow["three_day_eok"] = three
                flow["three_day_krw"] = int(round(three * 100_000_000))
                flow["three_day_available"] = True
                flow["finality"] = "확정"
            else:
                flow["three_day_eok"] = None
                flow["three_day_krw"] = None
                flow["three_day_available"] = False
                flow["finality"] = "확정" if cand.get("stable") else "잠정"
                flow["three_day_unavailable_reason"] = "실제 최근 3거래일의 확정 일별수급이 전부 있어야 누적 판정 가능"
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


def _postprocess_missing_three_day_status() -> None:
    """Never report a missing three-session sum as a real zero in the run summary."""
    if not watch.STATUS_PATH.exists() or not watch.PENDING_PATH.exists():
        return
    try:
        pending = json.loads(watch.PENDING_PATH.read_text(encoding="utf-8"))
        snap = pending.get("snapshot") or {}
        lines = watch.STATUS_PATH.read_text(encoding="utf-8").splitlines()
    except (OSError, ValueError, TypeError):
        return

    changed = False
    for market, key in (("KOSPI", "foreign_flow"), ("KOSDAQ", "kosdaq_foreign_flow")):
        flow = snap.get(key) or {}
        if flow.get("three_day_available") is not False:
            continue
        for i, line in enumerate(lines):
            if not line.startswith(f"- {market} 외국인:"):
                continue
            if ", 3거래일 " not in line or ", 기준일 " not in line:
                continue
            before, remainder = line.split(", 3거래일 ", 1)
            _, date_text = remainder.split(", 기준일 ", 1)
            lines[i] = (
                f"{before}, 3거래일 확인 불가(확정 일별 수급 공백), 기준일 {date_text}"
            )
            changed = True
    if changed:
        watch.STATUS_PATH.write_text("\n".join(lines) + "\n", encoding="utf-8")



# Date-addressable, read-only LS history recovery. The public t1665 schema
# supplies date, foreign amount sa_17 and exchange-specific index code.
# We require exact KRX identity and two independent already-confirmed dates
# to calibrate monetary units. A second >=10-minute observation is required
# before filling a missing date; no fallback can use a different market/unit.
def _validate_historical_ls(market, response, expected_dates, anchors):
    summary = response.get("t1665OutBlock") or {}
    market_name = str(summary.get("mname") or "").replace(" ", "").upper()
    expected_code = {"KOSPI": "K001", "KOSDAQ": "K301"}[market]
    names = {"KOSPI": ("KOSPI", "코스피", "거래소", "유가증권"),
             "KOSDAQ": ("KOSDAQ", "코스닥")}[market]
    if str(summary.get("ex_upcode") or "").strip().upper() != expected_code:
        raise ValueError("KRX 거래소별 업종코드 미검증")
    if not any(name in market_name for name in names) or (market == "KOSPI" and ("KOSDAQ" in market_name or "코스닥" in market_name)):
        raise ValueError("시장명 불일치")
    rows = {}
    for row in response.get("t1665OutBlock1") or []:
        d = str(row.get("date") or "")
        if re.fullmatch(r"\d{8}", d):
            d = f"{d[:4]}-{d[4:6]}-{d[6:]}"
        if d not in expected_dates:
            continue
        value = core.ls.fnum(row.get("sa_17"))
        if value is None:
            continue
        if d in rows and rows[d] != value:
            raise ValueError("동일 거래일 금액 충돌")
        rows[d] = value
    if not rows:
        raise ValueError("일자별 금액 원천행 없음")
    matched = [(d, float(v)) for d, v in anchors.items() if d in rows and abs(float(v)) >= 100]
    if len(matched) < 2:
        raise ValueError("확정 비교일 2개 부족")
    # sa_17 is the amount field, never sv_17 (volume). The old API reference
    # does not state monetary scale. Calibrate a unique scale to known closes.
    scales = [f for f in (1.0, 0.01, 0.0001, 0.00000001)
              if all(abs(rows[d] * f - v) <= DUAL_SOURCE_TOLERANCE_EOK for d, v in matched)]
    if len(scales) != 1:
        raise ValueError("금액 단위 또는 확정 비교일 불일치")
    f = scales[0]
    return {d: round(v * f, 6) for d, v in rows.items() if abs(v * f) <= 200_000 and v != 0}, {
        "scale_to_eok": f, "anchor_dates": [d for d, _ in matched], "exchange_index": expected_code,
    }


def _recover_historical_ls(pending, old, now):
    root = pending.get("final_flow_history") or {}
    previous = old.get("ls_date_backfill_candidates") or {}
    candidates, health = {}, {}
    called = False
    for market, upcode in (("KOSPI", "001"), ("KOSDAQ", "301")):
        prior = previous.get(market) or {}
        candidates[market] = dict(prior)
        info = health[market] = {"status": "미확인", "missing_dates": []}
        try:
            valid_dates = _recent_trade_dates(market)
            completed = sorted(d for d in valid_dates if d < now.date().isoformat())
            if not completed:
                raise ValueError("실제 완료 거래일 없음")
            known = {str(r["date"]): float(r["daily_eok"]) for r in root.get(market, [])}
            wanted = [d for d in completed[-10:] if d not in known]
            info["missing_dates"] = wanted
            if not wanted:
                info["status"] = "최근 완료 거래일 이력 충분"
                continue
            anchors = {d: v for d, v in known.items() if d in valid_dates and abs(v) >= 100}
            if len(anchors) < 2:
                raise ValueError("금액 검증용 확정 거래일 부족")
            if called:
                time.sleep(1.1)
            called = True
            req = {"t1665InBlock": {"market": "1", "upcode": upcode, "gubun2": "1", "gubun3": "1",
                   "from_date": min(wanted + list(anchors)).replace("-", ""),
                   "to_date": completed[-1].replace("-", ""), "exchgubun": "K"}}
            result = core.ls.ls_rest(core._get_token(), "stock/chart", "t1665", req)
            data, proof = _validate_historical_ls(market, result, set(completed), anchors)
            info.update(proof)
            recovered = []
            for day in wanted:
                value = data.get(day)
                if value is None:
                    continue
                previous_row = prior.get(day) or {}
                ptime = _parse_ts(previous_row.get("first_checked_at"))
                same = (previous_row.get("exchange_index") == proof["exchange_index"]
                        and previous_row.get("scale_to_eok") == proof["scale_to_eok"]
                        and previous_row.get("value_eok") is not None
                        and abs(float(previous_row["value_eok"]) - value) <= DUAL_SOURCE_TOLERANCE_EOK)
                if same and ptime is not None and (now - ptime).total_seconds() >= FALLBACK_MIN_MINUTES * 60:
                    known[day] = value
                    recovered.append(day)
                    candidates[market].pop(day, None)
                elif not same or ptime is None:
                    candidates[market][day] = {"value_eok": value, "first_checked_at": now.isoformat(timespec="seconds"),
                                              "exchange_index": proof["exchange_index"], "scale_to_eok": proof["scale_to_eok"]}
            root[market] = [{"date": d, "daily_eok": v} for d, v in sorted(known.items())][-10:]
            info.update({"status": "과거값 확인 완료" if recovered else "2회 검증 대기",
                         "recovered_dates": recovered, "rows": len(data), "remaining_dates": [d for d in wanted if d not in recovered]})
        except Exception as exc:
            # Do not log request credentials; never treat collection failure as a zero.
            info["status"] = "과거 수급 조회·검증 실패"
            info["error_type"] = type(exc).__name__
            if isinstance(exc, ValueError):
                info["reason"] = str(exc)
        candidates[market] = {d: r for d, r in candidates[market].items() if d in info.get("missing_dates", [])}
    pending["final_flow_history"] = root
    pending["ls_date_backfill_candidates"] = candidates
    pending["ls_date_backfill_health"] = health
    return health


def _annotate_operating_evidence():
    """Use the final pending snapshot, not intermediate legacy status zeros."""
    if not watch.PENDING_PATH.exists():
        return
    pending = json.loads(watch.PENDING_PATH.read_text(encoding="utf-8"))
    now = dt.datetime.now(watch.KST)
    old = _state()
    health = _recover_historical_ls(pending, old, now)
    snap = pending.get("snapshot") or {}
    # Persist separately classified source health and observed dates.
    lines = []
    for market, key in (("KOSPI", "foreign_flow"), ("KOSDAQ", "kosdaq_foreign_flow")):
        flow = snap.get(key) or {}
        latest = str(flow.get("date") or _canonical_trade_date(market) or "")
        history = {str(r["date"]): float(r["daily_eok"]) for r in (pending.get("final_flow_history") or {}).get(market, [])}
        if latest and latest in history:
            three = _three_day_from_confirmed_dates(market, latest, history)
            # Historical evidence is a display context; do not synthesize a fresh alert.
            daily = history[latest]
            msg = f"{market} {latest} 확정 순수급 {daily:+,.0f}억원; "
            msg += f"3거래일 {three:+,.0f}억원" if three is not None else "3거래일 확인 불가(확정 일별값 부족)"
        elif flow and flow.get("finality") == "확정" and flow.get("daily_eok") is not None:
            msg = f"{market} {latest} 확정 순수급 {float(flow['daily_eok']):+,.0f}억원"
            msg += f"; 3거래일 {float(flow['three_day_eok']):+,.0f}억원" if flow.get("three_day_eok") is not None else "; 3거래일 확인 불가"
        else:
            msg = f"{market} {latest or '거래일 미확인'} 확정 수급 확인 불가; 3거래일 판정 보류"
        lines.append(msg)
        h = health.get(market) or {}
        print(f"market_stress_history {market} status={h.get('status')} rows={h.get('rows', 0)} missing={h.get('missing_dates', [])} recovered={h.get('recovered_dates', [])} reason={h.get('reason', h.get('error_type', ''))}")
    snap["foreign_flow_context"] = lines
    pending["snapshot"] = snap
    watch.PENDING_PATH.write_text(json.dumps(pending, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    if watch.STATUS_PATH.exists():
        raw = watch.STATUS_PATH.read_text(encoding="utf-8").splitlines()
        raw = [l for l in raw if not l.startswith(("- KOSPI 외국인:", "- KOSDAQ 외국인:"))]
        raw += ["- " + l for l in lines]
        raw += [f"- {m} 과거 일별 원천: {health[m].get('status')} / 공백 {len(health[m].get('missing_dates', []))}개" for m in health]
        watch.STATUS_PATH.write_text("\n".join(raw) + "\n", encoding="utf-8")
    if watch.ALERT_PATH.exists():
        raw = watch.ALERT_PATH.read_text(encoding="utf-8")
        u10 = snap.get("ust10") or {}
        if u10.get("prev_date") and u10.get("date"):
            raw = re.sub(r"^(• 미국 10년물 일간 (?:상승|하락):[^\n]+)$",
                         lambda m: m[1] + f" (미국 관측일 {u10['prev_date']} → {u10['date']})", raw, flags=re.M)
        if "• KOSDAQ 외국인: 1일" not in raw:
            raw = raw.replace("• KOSPI 외국인: 1일 ±1조원, 최근 3거래일 누적 ±3조원",
                              "• KOSPI 외국인: 1일 ±1조원, 최근 3거래일 누적 ±3조원\n• KOSDAQ 외국인: 1일 ±2,000억원, 최근 3거래일 누적 ±5,000억원", 1)
        # The context is always shown (including morning rates alerts), but a
        # missing source is not a separate market signal or notification.
        block = "\n<b>한국 증시 확정 수급 확인 상태</b>\n" + "\n".join("• " + html.escape(l) for l in lines) + "\n"
        raw = raw.replace("\n<b>알림 기준</b>", block + "\n<b>알림 기준</b>", 1)
        watch.ALERT_PATH.write_text(raw, encoding="utf-8")


def main() -> int:
    # Preserve real delivery dedupe keys across every scheduled restart.
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
    captured = io.StringIO()
    try:
        with contextlib.redirect_stdout(captured):
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
    _postprocess_missing_three_day_status()
    _annotate_operating_evidence()
    for line in captured.getvalue().splitlines():
        if not line.startswith(('- KOSPI 외국인:', '- KOSDAQ 외국인:')):
            print(line)
    if watch.STATUS_PATH.exists():
        for line in watch.STATUS_PATH.read_text(encoding='utf-8').splitlines():
            if line.startswith(('- KOSPI ', '- KOSDAQ ')) and ('확정 순수급' in line or '확정 수급 확인 불가' in line):
                print(line)
    return rc


if __name__ == "__main__":
    raise SystemExit(main())