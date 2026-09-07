#!/usr/bin/env python3
from __future__ import annotations

import datetime as dt
import html
import os
from typing import Any

import requests

import korea_market_stress_watch_v10 as v10

watch = v10.watch
_original_fetch_usdkrw = watch.fetch_usdkrw
_original_add_event = watch.add_event

ECOS_API_HOME = "https://ecos.bok.or.kr/api/"
ECOS_STAT_CODE = "731Y001"
ECOS_ITEM_CODE_USD = "0000001"

_last_fx: dict[str, Any] = {}


def fetch_ecos_usdkrw(now: dt.datetime | None = None) -> dict[str, Any]:
    """Fetch the latest official BOK ECOS daily USD/KRW reference rate.

    ECOS 731Y001 / 0000001 = 원/미국달러(매매기준율), daily.
    This is an official daily validation series, not an intraday trigger feed.
    The API key is never persisted or emitted in logs/state/source URLs.
    """
    now = now or dt.datetime.now(watch.KST)
    api_key = (os.getenv("ECOS_API_KEY") or "").strip()
    if not api_key:
        raise RuntimeError("ECOS_API_KEY missing")

    start = (now.date() - dt.timedelta(days=14)).strftime("%Y%m%d")
    end = now.date().strftime("%Y%m%d")
    url = (
        "https://ecos.bok.or.kr/api/StatisticSearch/"
        f"{api_key}/json/kr/1/100/{ECOS_STAT_CODE}/D/{start}/{end}/{ECOS_ITEM_CODE_USD}"
    )
    r = requests.get(
        url,
        headers={
            "User-Agent": "Mozilla/5.0 (compatible; khs-korea-market-stress-watch/11.0)",
            "Accept": "application/json",
        },
        timeout=30,
    )
    r.raise_for_status()
    payload = r.json()
    block = payload.get("StatisticSearch") if isinstance(payload, dict) else None
    rows = (block or {}).get("row") if isinstance(block, dict) else None
    if not isinstance(rows, list) or not rows:
        result = payload.get("RESULT") if isinstance(payload, dict) else None
        msg = ""
        if isinstance(result, dict):
            msg = str(result.get("MESSAGE") or result.get("CODE") or "")
        raise RuntimeError(f"ECOS 731Y001 응답에 환율 행 없음{': ' + msg if msg else ''}")

    parsed: list[tuple[str, float, str, str]] = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        raw_time = str(row.get("TIME") or "").strip()
        raw_value = row.get("DATA_VALUE")
        if len(raw_time) != 8 or not raw_time.isdigit() or raw_value in (None, ""):
            continue
        try:
            value = float(str(raw_value).replace(",", ""))
            day = dt.datetime.strptime(raw_time, "%Y%m%d").date().isoformat()
        except Exception:
            continue
        item_name = str(row.get("ITEM_NAME1") or "원/미국달러(매매기준율)").strip()
        unit = str(row.get("UNIT_NAME") or "원").strip()
        parsed.append((day, value, item_name, unit))

    if not parsed:
        raise RuntimeError("ECOS 원/달러 일별 환율 파싱 실패")

    day, value, item_name, unit = max(parsed, key=lambda x: x[0])
    return {
        "date": day,
        "value": value,
        "item_name": item_name,
        "unit": unit,
        "stat_code": ECOS_STAT_CODE,
        "item_code": ECOS_ITEM_CODE_USD,
        "source": ECOS_API_HOME,
        "role": "한국은행 공식 일일 검증값(장중 경보 판정에는 사용하지 않음)",
    }


def fetch_usdkrw() -> dict[str, Any]:
    fx = _original_fetch_usdkrw()
    try:
        fx["ecos_official"] = fetch_ecos_usdkrw()
        fx.pop("ecos_error", None)
    except Exception as exc:
        # Keep intraday monitoring alive if ECOS is temporarily unavailable.
        fx["ecos_error"] = f"{type(exc).__name__}: {exc}"
    _last_fx.clear()
    _last_fx.update(fx)
    return fx


def add_event_crossing_only(events, key: str, text: str, source: str) -> None:
    """Threshold labels mean a real crossing, not simply remaining beyond a level."""
    if key.startswith("fx_1350_down:"):
        prev = _last_fx.get("prev_value")
        cur = _last_fx.get("value")
        if not isinstance(prev, (int, float)) or not isinstance(cur, (int, float)):
            return
        if not (prev > 1350 and cur <= 1350):
            return
    elif key.startswith("fx_1400_up:"):
        prev = _last_fx.get("prev_value")
        cur = _last_fx.get("value")
        if not isinstance(prev, (int, float)) or not isinstance(cur, (int, float)):
            return
        if not (prev < 1400 and cur >= 1400):
            return
    _original_add_event(events, key, text, source)


def _append_ecos_context() -> None:
    ecos = _last_fx.get("ecos_official") if isinstance(_last_fx, dict) else None
    ecos_error = _last_fx.get("ecos_error") if isinstance(_last_fx, dict) else None

    if watch.STATUS_PATH.exists():
        try:
            status = watch.STATUS_PATH.read_text(encoding="utf-8").rstrip()
            if isinstance(ecos, dict):
                status += (
                    f"\n- 한국은행 ECOS 원/달러 공식 일일값: {ecos['value']:,.2f}원, "
                    f"기준일 {ecos['date']} · {ECOS_STAT_CODE}/{ECOS_ITEM_CODE_USD}"
                )
            elif ecos_error:
                status += f"\n- 한국은행 ECOS 환율 검증: 조회 실패({ecos_error})"
            watch.STATUS_PATH.write_text(status + "\n", encoding="utf-8")
        except Exception:
            pass

    if ecos_error:
        try:
            with watch.ERROR_PATH.open("a", encoding="utf-8") as f:
                f.write(f"한국은행 ECOS 원/달러 검증 실패: {ecos_error}\n")
        except Exception:
            pass

    if not watch.ALERT_PATH.exists():
        return
    try:
        text = watch.ALERT_PATH.read_text(encoding="utf-8").strip()
        if "원/달러" not in text:
            return
        lines = text.splitlines()
        insert_at = next((i for i, line in enumerate(lines) if "<b>원문</b>" in line), len(lines))
        additions: list[str] = []
        if isinstance(ecos, dict):
            current_date = str(_last_fx.get("date") or "")
            label = "동일 기준일 공식값" if ecos.get("date") == current_date else "최근 공식 일일값"
            additions.append(
                f"• 한국은행 ECOS {label}: {ecos['date']} {ecos['value']:,.2f}원 "
                f"({html.escape(str(ecos.get('item_name') or '원/미국달러(매매기준율)'))})"
            )
            additions.append("• 판정 역할: 장중 임계치 감지는 실시간 피드, ECOS는 공식 일일값 검증만 사용")
        elif ecos_error:
            additions.append("• 한국은행 ECOS 공식 일일값: 이번 실행 조회 실패 — 장중 경보값과 혼합하지 않음")
        if additions and not any("한국은행 ECOS" in line for line in lines):
            lines[insert_at:insert_at] = additions + [""]
        if isinstance(ecos, dict):
            ecos_link = f'• <a href="{html.escape(ECOS_API_HOME, quote=True)}">한국은행 ECOS Open API</a>'
            if ecos_link not in lines:
                lines.append(ecos_link)
        watch.ALERT_PATH.write_text("\n".join(lines) + "\n", encoding="utf-8")
    except Exception as exc:
        try:
            with watch.ERROR_PATH.open("a", encoding="utf-8") as f:
                f.write(f"ECOS 알림 문구 보강 실패: {type(exc).__name__}: {exc}\n")
        except Exception:
            pass


watch.fetch_usdkrw = fetch_usdkrw
watch.add_event = add_event_crossing_only


def main() -> int:
    rc = v10.main()
    _append_ecos_context()
    return rc


if __name__ == "__main__":
    raise SystemExit(main())
