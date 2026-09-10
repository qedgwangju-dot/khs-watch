#!/usr/bin/env python3
from __future__ import annotations

import datetime as dt
import html
import json
from typing import Any, Callable

import korea_market_stress_watch_v12 as v12
import kospi_flow_attribution_ls as ls

watch = v12.watch
v10 = v12.v11.v10

LS_GUIDE = "https://openapi.ls-sec.co.kr/apiservice"
LS_DAILY_TOLERANCE_EOK = 100.0
LS_DAILY_TOLERANCE_PCT = 0.005

_original_kospi_flow = watch.fetch_kospi_foreign_flow
_original_kosdaq_flow = v10._fetch_kosdaq_foreign_flow
_original_add_event = watch.add_event
_original_market_flow_lines = v10._market_flow_lines
_original_kosdaq_hit_keys = v10._kosdaq_hit_keys

_ls_token: str | None = None
_validation: dict[str, dict[str, Any]] = {}
_ls_history_updates: dict[str, tuple[str, float]] = {}


def _get_token() -> str:
    global _ls_token
    if not _ls_token:
        _ls_token = ls.get_ls_token()
    return _ls_token


def _latest_ls_foreign_eok(upcode: str, market_name: str) -> dict[str, Any]:
    token = _get_token()
    series = ls.fetch_investor_series(token, "1", upcode, count=100)
    rows = series.get("rows") or []
    if not rows:
        raise RuntimeError(f"LS t1602 {market_name} 정규장 수급 행 없음")
    latest = rows[-1]
    value = ls.fnum(latest.get("sv_17"))
    if value is None:
        raise RuntimeError(f"LS t1602 {market_name} 외국인 금액(sv_17) 없음")
    if abs(value) > 200_000:
        raise RuntimeError(f"LS t1602 {market_name} 외국인 금액 비정상 범위: {value}")
    return {
        "daily_eok": float(value),
        "daily_krw": int(round(float(value) * 100_000_000)),
        "latest_time": str(latest.get("time") or ""),
        "row_count": len(rows),
        "upcode": upcode,
        "source": LS_GUIDE,
    }


def _tolerance_eok(naver_eok: float) -> float:
    return max(LS_DAILY_TOLERANCE_EOK, abs(naver_eok) * LS_DAILY_TOLERANCE_PCT)


def _load_history(market_name: str) -> list[dict[str, Any]]:
    try:
        state = watch.load_state() or {}
    except Exception:
        state = {}
    history = ((state.get("ls_flow_history") or {}).get(market_name) or [])
    out: list[dict[str, Any]] = []
    for row in history:
        if not isinstance(row, dict):
            continue
        try:
            d = str(row.get("date") or "")
            eok = float(row.get("daily_eok"))
        except Exception:
            continue
        if d:
            out.append({"date": d, "daily_eok": eok})
    return out[-10:]


def _ls_three_day(market_name: str, date: str, daily_eok: float) -> tuple[float | None, list[dict[str, Any]]]:
    history = _load_history(market_name)
    by_date = {str(row["date"]): float(row["daily_eok"]) for row in history}
    by_date[date] = daily_eok
    rows = [{"date": d, "daily_eok": v} for d, v in sorted(by_date.items())][-10:]
    _ls_history_updates[market_name] = (date, daily_eok)
    if len(rows) < 3:
        return None, rows
    return sum(float(row["daily_eok"]) for row in rows[-3:]), rows


def _verified_flow(
    now: dt.datetime,
    market_name: str,
    upcode: str,
    original: Callable[[dt.datetime], dict[str, Any]],
) -> dict[str, Any]:
    naver: dict[str, Any] | None = None
    naver_error: str | None = None
    ls_row: dict[str, Any] | None = None
    ls_error: str | None = None

    try:
        naver = original(now)
    except Exception as exc:
        naver_error = f"{type(exc).__name__}: {exc}"

    try:
        ls_row = _latest_ls_foreign_eok(upcode, market_name)
    except Exception as exc:
        ls_error = f"{type(exc).__name__}: {exc}"

    if naver is not None and ls_row is not None:
        naver_eok = float(naver["daily_eok"])
        ls_eok = float(ls_row["daily_eok"])
        diff_eok = ls_eok - naver_eok
        tolerance = _tolerance_eok(naver_eok)
        status = "matched" if abs(diff_eok) <= tolerance else "mismatch"
        naver["ls_validation"] = {
            "status": status,
            "ls_daily_eok": ls_eok,
            "naver_daily_eok": naver_eok,
            "diff_eok": diff_eok,
            "tolerance_eok": tolerance,
            "latest_time": ls_row.get("latest_time"),
            "source": LS_GUIDE,
        }
        naver["source_label"] = "네이버 장마감 + LS증권 t1602 교차검증"
        _validation[market_name] = dict(naver["ls_validation"])
        _ls_history_updates[market_name] = (str(naver["date"]), ls_eok)
        return naver

    if naver is not None:
        naver["ls_validation"] = {
            "status": "ls_unavailable",
            "error": ls_error or "LS 조회 실패",
            "source": LS_GUIDE,
        }
        naver["source_label"] = "네이버 장마감 수급 — LS 교차검증 일시 실패"
        _validation[market_name] = dict(naver["ls_validation"])
        return naver

    if ls_row is not None:
        date = now.date().isoformat()
        daily_eok = float(ls_row["daily_eok"])
        three_eok, history = _ls_three_day(market_name, date, daily_eok)
        flow = {
            "date": date,
            "daily_eok": daily_eok,
            "daily_krw": int(round(daily_eok * 100_000_000)),
            "three_day_eok": three_eok if three_eok is not None else 0.0,
            "three_day_krw": int(round(three_eok * 100_000_000)) if three_eok is not None else 0,
            "three_day_available": three_eok is not None,
            "source": LS_GUIDE,
            "source_label": "LS증권 t1602 대체값",
            "phase": "18:10 이후 LS증권 장마감 대체값",
            "ls_validation": {
                "status": "ls_fallback",
                "ls_daily_eok": daily_eok,
                "latest_time": ls_row.get("latest_time"),
                "naver_error": naver_error or "네이버 조회 실패",
                "history_count": len(history),
                "source": LS_GUIDE,
            },
        }
        _validation[market_name] = dict(flow["ls_validation"])
        return flow

    raise RuntimeError(
        f"{market_name} 수급 양쪽 조회 실패 — 네이버: {naver_error or '없음'} / LS: {ls_error or '없음'}"
    )


def fetch_kospi_verified(now: dt.datetime) -> dict[str, Any]:
    return _verified_flow(now, "KOSPI", "001", _original_kospi_flow)


def fetch_kosdaq_verified(now: dt.datetime) -> dict[str, Any]:
    return _verified_flow(now, "KOSDAQ", "301", _original_kosdaq_flow)


def add_event_verified(events, key: str, text: str, source: str) -> None:
    if key.startswith("foreign1d_") or key.startswith("foreign3d_"):
        status = (_validation.get("KOSPI") or {}).get("status")
        if status == "mismatch":
            return
        if key.startswith("foreign3d_"):
            try:
                pending_flow = (watch.load_state() or {}).get("snapshot", {}).get("foreign_flow", {})
            except Exception:
                pending_flow = {}
            # LS fallback 첫날처럼 3일 이력이 부족하면 3일 경보를 만들지 않는다.
            if isinstance(pending_flow, dict) and pending_flow.get("three_day_available") is False:
                return
    _original_add_event(events, key, text, source)


def kosdaq_hit_keys_verified(flow: dict[str, Any] | None) -> list[str]:
    if not flow:
        return []
    validation = flow.get("ls_validation") if isinstance(flow, dict) else None
    if isinstance(validation, dict) and validation.get("status") == "mismatch":
        return []
    keys = _original_kosdaq_hit_keys(flow)
    if flow.get("three_day_available") is False:
        keys = [k for k in keys if "3d" not in k]
    return keys


def market_flow_lines_verified(
    market: str,
    idx: dict[str, Any] | None,
    flow: dict[str, Any] | None,
    daily_threshold: int,
    three_day_threshold: int,
) -> list[str]:
    lines = _original_market_flow_lines(market, idx, flow, daily_threshold, three_day_threshold)
    if not flow:
        return lines

    if flow.get("three_day_available") is False:
        rebuilt: list[str] = []
        skip_next = False
        for line in lines:
            if skip_next:
                skip_next = False
                continue
            if line.startswith("• 외국인 3거래일 누적"):
                rebuilt.append("• 외국인 3거래일 누적  <b>LS 이력 축적 중 — 판정 보류</b>")
                rebuilt.append("  ↳ 3거래일 LS 일별값이 3개 쌓인 뒤 자동 판정")
                skip_next = True
            else:
                rebuilt.append(line)
        lines = rebuilt

    validation = flow.get("ls_validation") if isinstance(flow, dict) else None
    if not isinstance(validation, dict):
        return lines
    status = validation.get("status")
    if status == "matched":
        lines.append(
            f"• LS 교차검증  <b>일치</b> — LS {float(validation['ls_daily_eok']):+,.0f}억원 / "
            f"네이버 {float(validation['naver_daily_eok']):+,.0f}억원 / 차이 {float(validation['diff_eok']):+,.0f}억원"
        )
    elif status == "mismatch":
        lines.append(
            f"• LS 교차검증  <b>불일치 — 수급 임계치 판정 보류</b>"
        )
        lines.append(
            f"  ↳ LS {float(validation['ls_daily_eok']):+,.0f}억원 / 네이버 {float(validation['naver_daily_eok']):+,.0f}억원 / "
            f"차이 {float(validation['diff_eok']):+,.0f}억원"
        )
    elif status == "ls_fallback":
        lines.append(
            f"• LS 대체값 사용  <b>{float(validation['ls_daily_eok']):+,.0f}억원</b> — 네이버 장마감 수급 조회 실패"
        )
    elif status == "ls_unavailable":
        lines.append("• LS 교차검증 일시 실패 — 네이버 장마감 수급값은 유지, 다음 실행에서 재검증")
    return lines


def _persist_ls_history_and_source_note() -> None:
    if not watch.PENDING_PATH.exists():
        return
    try:
        pending = json.loads(watch.PENDING_PATH.read_text(encoding="utf-8"))
    except Exception:
        return

    old = watch.load_state() or {}
    history_root = dict(old.get("ls_flow_history") or {})
    for market_name, (date, daily_eok) in _ls_history_updates.items():
        rows = history_root.get(market_name) or []
        by_date: dict[str, float] = {}
        for row in rows:
            if not isinstance(row, dict):
                continue
            try:
                by_date[str(row.get("date") or "")] = float(row.get("daily_eok"))
            except Exception:
                continue
        by_date[date] = daily_eok
        history_root[market_name] = [
            {"date": d, "daily_eok": v} for d, v in sorted(by_date.items()) if d
        ][-10:]
    pending["ls_flow_history"] = history_root
    snap = pending.setdefault("snapshot", {})
    snap["flow_source_note"] = (
        "KOSPI·KOSDAQ 장마감 외국인 수급은 네이버 장마감값과 LS증권 OpenAPI t1602를 교차검증. "
        "네이버 실패 시 LS 대체값 사용, 유의한 불일치 시 수급 임계치 판정 보류. KRX는 공식 원천 재확인 링크로 제공."
    )
    snap["ls_flow_validation"] = _validation
    watch.PENDING_PATH.write_text(json.dumps(pending, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def _rewrite_source_note() -> None:
    if not watch.ALERT_PATH.exists():
        return
    text = watch.ALERT_PATH.read_text(encoding="utf-8")
    old = "• 수급 숫자 출처: 18:10 이후 네이버 투자자별 매매동향 / KRX 링크는 공식 원천 재확인용"
    new = (
        "• 수급 숫자 검증: <b>18:10 이후 네이버 장마감값 + LS증권 OpenAPI t1602 교차검증</b>"
        " / 네이버 실패 시 LS 대체 / 유의한 불일치 시 임계치 판정 보류"
    )
    text = text.replace(old, new)
    ls_link = f'• <a href="{html.escape(LS_GUIDE, quote=True)}">LS증권 OpenAPI 공식 가이드</a>'
    if ls_link not in text:
        text = text.rstrip() + "\n" + ls_link + "\n"
    watch.ALERT_PATH.write_text(text, encoding="utf-8")


def _append_status() -> None:
    if not watch.STATUS_PATH.exists():
        return
    lines = [watch.STATUS_PATH.read_text(encoding="utf-8").rstrip(), "- LS증권 수급 교차검증: 활성"]
    for market_name in ("KOSPI", "KOSDAQ"):
        row = _validation.get(market_name) or {}
        status = row.get("status")
        if status == "matched":
            lines.append(
                f"- {market_name} LS 검증: 일치 · LS {float(row['ls_daily_eok']):+,.0f}억원 / "
                f"네이버 {float(row['naver_daily_eok']):+,.0f}억원 / 차이 {float(row['diff_eok']):+,.0f}억원"
            )
        elif status == "mismatch":
            lines.append(
                f"- {market_name} LS 검증: 불일치 · LS {float(row['ls_daily_eok']):+,.0f}억원 / "
                f"네이버 {float(row['naver_daily_eok']):+,.0f}억원 / 수급 경보 보류"
            )
        elif status == "ls_fallback":
            lines.append(f"- {market_name} LS 검증: 네이버 실패 → LS {float(row['ls_daily_eok']):+,.0f}억원 대체")
        elif status == "ls_unavailable":
            lines.append(f"- {market_name} LS 검증: LS 일시 실패 · 네이버 값 유지")
    watch.STATUS_PATH.write_text("\n".join(lines) + "\n", encoding="utf-8")


watch.fetch_kospi_foreign_flow = fetch_kospi_verified
watch.add_event = add_event_verified
v10._fetch_kosdaq_foreign_flow = fetch_kosdaq_verified
v10._kosdaq_hit_keys = kosdaq_hit_keys_verified
v10._market_flow_lines = market_flow_lines_verified


def main() -> int:
    rc = v12.main()
    _persist_ls_history_and_source_note()
    _rewrite_source_note()
    _append_status()
    return rc


if __name__ == "__main__":
    raise SystemExit(main())
