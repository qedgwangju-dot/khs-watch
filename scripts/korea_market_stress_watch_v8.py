#!/usr/bin/env python3
from __future__ import annotations

import datetime as dt
import json
from typing import Any

import requests

import korea_market_stress_watch_v7 as v7

watch = v7.watch
_original_add_event = watch.add_event
_original_fetch_flow = watch.fetch_kospi_foreign_flow

NAVER_KOSPI_PRICE_URL = "https://m.stock.naver.com/api/index/KOSPI/price?pageSize=5&page=1"
NAVER_KOSPI_BASIC_URL = "https://m.stock.naver.com/api/index/KOSPI/basic"


def _close_phase(now: dt.datetime) -> str:
    if now.weekday() >= 5:
        return "최근 거래일 마감"
    if now.time() >= dt.time(18, 10):
        return "마감 최종 재확인"
    if now.time() >= dt.time(15, 45):
        return "정규장 마감"
    return "장중 잠정"


def fetch_kospi_foreign_flow_close_first(now: dt.datetime) -> dict[str, Any]:
    # Same public source as the original watcher, but the key policy is different:
    # intraday values are status-only; only >=15:45 values may trigger alerts.
    flow = _original_fetch_flow(now)
    flow["phase"] = _close_phase(now)
    return flow


def _fetch_kospi_index_close(now: dt.datetime) -> dict[str, Any] | None:
    if now.weekday() < 5 and now.time() < dt.time(15, 45):
        return None
    r = requests.get(NAVER_KOSPI_PRICE_URL, headers=watch.HEADERS, timeout=30)
    r.raise_for_status()
    rows = r.json()
    if not isinstance(rows, list) or not rows:
        return None
    row = rows[0]
    close = float(str(row.get("closePrice") or "0").replace(",", ""))
    pct = float(str(row.get("fluctuationsRatio") or "0").replace("%", ""))
    date = str(row.get("localTradedAt") or "")[:10]
    return {
        "date": date,
        "close": close,
        "change_pct": pct,
        "source": NAVER_KOSPI_PRICE_URL,
        "phase": _close_phase(now),
    }


def add_event_close_first(events, key: str, text: str, source: str) -> None:
    now = dt.datetime.now(watch.KST)
    if key.startswith("foreign1d_") or key.startswith("foreign3d_"):
        # User preference: close/final is authoritative. Never push intraday threshold alerts.
        if now.weekday() < 5 and now.time() < dt.time(15, 45):
            return
        phase = _close_phase(now)
        text = text.replace("장마감 확인", phase).replace("장중 잠정", phase)
    _original_add_event(events, key, text, source)


watch.fetch_kospi_foreign_flow = fetch_kospi_foreign_flow_close_first
watch.add_event = add_event_close_first


def _append_close_context() -> None:
    if not watch.PENDING_PATH.exists():
        return
    now = dt.datetime.now(watch.KST)
    if now.weekday() < 5 and now.time() < dt.time(15, 45):
        return
    try:
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
        line = f"• {idx['phase']} KOSPI 종가: {idx['close']:,.2f} ({idx['change_pct']:+.2f}%)"
        lines = text.splitlines()
        insert_at = 2 if len(lines) >= 2 else len(lines)
        lines.insert(insert_at, line)
        watch.ALERT_PATH.write_text("\n".join(lines) + "\n", encoding="utf-8")
    except Exception as exc:
        with watch.ERROR_PATH.open("a", encoding="utf-8") as f:
            f.write(f"KOSPI 종가 확인 실패: {type(exc).__name__}: {exc}\n")


def main() -> int:
    rc = v7.main()
    _append_close_context()
    return rc


if __name__ == "__main__":
    raise SystemExit(main())
