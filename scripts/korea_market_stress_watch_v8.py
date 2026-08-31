#!/usr/bin/env python3
from __future__ import annotations

import datetime as dt
from typing import Any

from pykrx import stock

import korea_market_stress_watch_v7 as v7

watch = v7.watch
_original_add_event = watch.add_event
_original_fetch_flow = watch.fetch_kospi_foreign_flow

KRX_FLOW_URL = "https://data.krx.co.kr/contents/MDC/MDI/outerLoader/index.cmd?screenId=MDCSTAT022"
KRX_INDEX_URL = "https://data.krx.co.kr/contents/MDC/MDI/outerLoader/index.cmd?screenId=MDCSTAT003"


def _krx_close_phase(now: dt.datetime) -> str:
    if now.weekday() >= 5:
        return "최근 거래일"
    if now.time() >= dt.time(18, 10):
        return "KRX 최종 확정"
    if now.time() >= dt.time(15, 45):
        return "KRX 정규장 마감"
    return "장중 잠정"


def _fetch_krx_flow(now: dt.datetime) -> dict[str, Any]:
    end = now.strftime("%Y%m%d")
    start = (now.date() - dt.timedelta(days=10)).strftime("%Y%m%d")
    df = stock.get_market_trading_value_by_date(start, end, "KOSPI")
    if df is None or df.empty:
        raise RuntimeError("KRX KOSPI 투자자별 거래대금 조회 결과 없음")
    col = "외국인합계" if "외국인합계" in df.columns else "외국인"
    if col not in df.columns:
        raise RuntimeError(f"KRX 외국인 열 없음: {list(df.columns)}")
    s = df[col].dropna().astype("int64")
    if s.empty:
        raise RuntimeError("KRX 외국인 순매수 데이터 없음")
    latest_date = s.index[-1]
    latest = int(s.iloc[-1])
    last3 = int(s.tail(3).sum())
    return {
        "date": latest_date.strftime("%Y-%m-%d"),
        "daily_krw": latest,
        "three_day_krw": last3,
        "daily_eok": latest / 100_000_000,
        "three_day_eok": last3 / 100_000_000,
        "source": KRX_FLOW_URL,
        "phase": _krx_close_phase(now),
    }


def fetch_kospi_foreign_flow_authoritative(now: dt.datetime) -> dict[str, Any]:
    # KRX says regular-market data are reflected after about 15:45 and final data after about 18:00.
    # Before that, keep intraday data only for status display; never use it to trigger a foreign-flow alert.
    if now.weekday() < 5 and now.time() >= dt.time(15, 45):
        return _fetch_krx_flow(now)
    flow = _original_fetch_flow(now)
    flow["phase"] = "장중 잠정"
    return flow


def _fetch_kospi_index_close(now: dt.datetime) -> dict[str, Any] | None:
    if now.weekday() < 5 and now.time() < dt.time(15, 45):
        return None
    end = now.strftime("%Y%m%d")
    start = (now.date() - dt.timedelta(days=7)).strftime("%Y%m%d")
    df = stock.get_index_ohlcv_by_date(start, end, "1001")
    if df is None or df.empty:
        return None
    row = df.iloc[-1]
    date = df.index[-1].strftime("%Y-%m-%d")
    close = float(row["종가"])
    prev_close = float(df.iloc[-2]["종가"]) if len(df) >= 2 else 0.0
    pct = ((close / prev_close) - 1) * 100 if prev_close else 0.0
    return {
        "date": date,
        "close": close,
        "change_pct": pct,
        "source": KRX_INDEX_URL,
        "phase": _krx_close_phase(now),
    }


def add_event_close_first(events, key: str, text: str, source: str) -> None:
    now = dt.datetime.now(watch.KST)
    if key.startswith("foreign1d_") or key.startswith("foreign3d_"):
        # Do not send intraday foreign-flow threshold alerts. Close/final is authoritative.
        if now.weekday() < 5 and now.time() < dt.time(15, 45):
            return
        phase = "KRX 최종 확정" if now.time() >= dt.time(18, 10) else "KRX 정규장 마감"
        text = text.replace("장마감 확인", phase).replace("장중 잠정", phase)
    _original_add_event(events, key, text, source)


watch.fetch_kospi_foreign_flow = fetch_kospi_foreign_flow_authoritative
watch.add_event = add_event_close_first


def _append_close_context() -> None:
    if not watch.PENDING_PATH.exists():
        return
    now = dt.datetime.now(watch.KST)
    if now.weekday() < 5 and now.time() < dt.time(15, 45):
        return
    try:
        import json
        pending = json.loads(watch.PENDING_PATH.read_text(encoding="utf-8"))
        idx = _fetch_kospi_index_close(now)
        if idx:
            pending.setdefault("snapshot", {})["kospi_close"] = idx
            watch.PENDING_PATH.write_text(json.dumps(pending, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        if not watch.ALERT_PATH.exists() or not idx:
            return
        text = watch.ALERT_PATH.read_text(encoding="utf-8").strip()
        if "KOSPI 종가" in text:
            return
        phase = idx["phase"]
        line = f"• {phase} KOSPI 종가: {idx['close']:,.2f} ({idx['change_pct']:+.2f}%)"
        lines = text.splitlines()
        insert_at = 2 if len(lines) >= 2 else len(lines)
        lines.insert(insert_at, line)
        watch.ALERT_PATH.write_text("\n".join(lines) + "\n", encoding="utf-8")
    except Exception as exc:
        with watch.ERROR_PATH.open("a", encoding="utf-8") as f:
            f.write(f"KRX KOSPI 종가 확인 실패: {type(exc).__name__}: {exc}\n")


def main() -> int:
    rc = v7.main()
    _append_close_context()
    return rc


if __name__ == "__main__":
    raise SystemExit(main())
