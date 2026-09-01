#!/usr/bin/env python3
from __future__ import annotations

import datetime as dt
import html
import json
import re
from typing import Any

import requests

import korea_market_stress_watch_v6 as v6

watch = v6.watch
_original_add_event = watch.add_event
_original_fetch_flow = watch.fetch_kospi_foreign_flow

NAVER_FLOW_URL = "https://finance.naver.com/sise/investorDealTrendDay.naver"
NAVER_KOSPI_PRICE_URL = "https://m.stock.naver.com/api/index/KOSPI/price?pageSize=5&page=1"
KRX_FLOW_PAGE = "https://data.krx.co.kr/contents/MDC/MDI/outerLoader/index.cmd?screenId=MDCSTAT022"


def _fmt_amount(value_krw: int) -> str:
    eok = int(round(abs(value_krw) / 100_000_000))
    jo, rem = divmod(eok, 10_000)
    if jo and rem:
        amount = f"{jo}조{rem:,}억원"
    elif jo:
        amount = f"{jo}조원"
    else:
        amount = f"{rem:,}억원"
    if value_krw > 0:
        return "+" + amount
    if value_krw < 0:
        return "-" + amount
    return "0억원"


def _phase(now: dt.datetime) -> str:
    if now.weekday() >= 5:
        return "최근 거래일"
    if now.time() >= dt.time(18, 10):
        return "마감 후 재조회"
    if now.time() >= dt.time(15, 45):
        return "정규장 마감 확인"
    return "장중 참고"


def fetch_flow(now: dt.datetime) -> dict[str, Any]:
    flow = _original_fetch_flow(now)
    flow["phase"] = _phase(now)
    flow["source_note"] = "네이버 투자자별 매매동향 재조회"
    return flow


def _rewrite_foreign_text(text: str, phase: str) -> str:
    text = re.sub(r"KOSPI 외국인 1일 순매수 -([^—]+)", rf"KOSPI 외국인 {phase}: 1일 순매도 \1", text)
    text = re.sub(r"KOSPI 외국인 1일 순매수 \+([^—]+)", rf"KOSPI 외국인 {phase}: 1일 순매수 \1", text)
    text = re.sub(r"KOSPI 외국인 최근 3거래일 누적 -([^—]+)", rf"KOSPI 외국인 {phase}: 최근 3거래일 누적 순매도 \1", text)
    text = re.sub(r"KOSPI 외국인 최근 3거래일 누적 \+([^—]+)", rf"KOSPI 외국인 {phase}: 최근 3거래일 누적 순매수 \1", text)
    text = text.replace("— -1조원 기준 돌파", "— 순매도 1조원 기준 돌파")
    text = text.replace("— +1조원 기준 돌파", "— 순매수 1조원 기준 돌파")
    text = text.replace("— -3조원 기준 돌파", "— 누적 순매도 3조원 기준 돌파")
    text = text.replace("— +3조원 기준 돌파", "— 누적 순매수 3조원 기준 돌파")
    return text


def add_event_close_first(events, key: str, text: str, source: str) -> None:
    now = dt.datetime.now(watch.KST)
    if key.startswith("foreign1d_") or key.startswith("foreign3d_"):
        # 사용자 기준: 장중 잠정 수급은 투자 경보로 보내지 않고, 정규장 마감 뒤에만 판정한다.
        if now.weekday() < 5 and now.time() < dt.time(15, 45):
            return
        phase = _phase(now)
        text = _rewrite_foreign_text(text, phase)
        suffix = "postclose" if phase == "마감 후 재조회" else "close"
        key = f"{key}:{suffix}"
    _original_add_event(events, key, text, source)


def _fetch_kospi_close() -> dict[str, Any] | None:
    r = requests.get(NAVER_KOSPI_PRICE_URL, headers=watch.HEADERS, timeout=30)
    r.raise_for_status()
    rows = r.json()
    if not isinstance(rows, list) or not rows:
        return None
    row = rows[0]
    close = float(str(row.get("closePrice") or "0").replace(",", ""))
    pct = float(str(row.get("fluctuationsRatio") or "0").replace(",", ""))
    return {
        "date": str(row.get("localTradedAt") or "")[:10],
        "close": close,
        "change_pct": pct,
        "source": NAVER_KOSPI_PRICE_URL,
    }


def _thresholds(flow: dict[str, Any]) -> dict[str, bool]:
    d = int(flow.get("daily_krw") or 0)
    t = int(flow.get("three_day_krw") or 0)
    return {
        "foreign1d_pos": d >= 1_000_000_000_000,
        "foreign1d_neg": d <= -1_000_000_000_000,
        "foreign3d_pos": t >= 3_000_000_000_000,
        "foreign3d_neg": t <= -3_000_000_000_000,
    }


def _write_postclose_correction_if_needed(old: dict, pending: dict) -> None:
    now = dt.datetime.now(watch.KST)
    if now.weekday() >= 5 or now.time() < dt.time(18, 10):
        return
    old_flow = ((old.get("snapshot") or {}).get("foreign_flow") or {})
    new_flow = ((pending.get("snapshot") or {}).get("foreign_flow") or {})
    if not old_flow or not new_flow or new_flow.get("date") != now.date().isoformat():
        return
    old_state = _thresholds(old_flow)
    new_state = _thresholds(new_flow)
    lines = []
    if old_state["foreign1d_neg"] and not new_state["foreign1d_neg"]:
        lines.append(f"• 1일 수급: 정규장 마감 순매도 {_fmt_amount(int(old_flow['daily_krw'])).lstrip('-')} → 마감 후 재조회 {_fmt_amount(int(new_flow['daily_krw'])).lstrip('-')} — 1조원 기준 이탈")
    elif old_state["foreign1d_pos"] and not new_state["foreign1d_pos"]:
        lines.append(f"• 1일 수급: 정규장 마감 순매수 {_fmt_amount(int(old_flow['daily_krw'])).lstrip('+')} → 마감 후 재조회 {_fmt_amount(int(new_flow['daily_krw'])).lstrip('+')} — 1조원 기준 이탈")
    if old_state["foreign3d_neg"] and not new_state["foreign3d_neg"]:
        lines.append(f"• 3거래일: 정규장 마감 누적 순매도 {_fmt_amount(int(old_flow['three_day_krw'])).lstrip('-')} → 마감 후 재조회 {_fmt_amount(int(new_flow['three_day_krw'])).lstrip('-')} — 3조원 기준 이탈")
    elif old_state["foreign3d_pos"] and not new_state["foreign3d_pos"]:
        lines.append(f"• 3거래일: 정규장 마감 누적 순매수 {_fmt_amount(int(old_flow['three_day_krw'])).lstrip('+')} → 마감 후 재조회 {_fmt_amount(int(new_flow['three_day_krw'])).lstrip('+')} — 3조원 기준 이탈")
    if not lines:
        return
    idx = _fetch_kospi_close()
    msg = ["🔄 <b>KOSPI 외국인 수급 마감 후 정정</b>", f"• 조회: {now:%Y-%m-%d %H:%M} KST"]
    if idx:
        msg.append(f"• KOSPI 종가: {idx['close']:,.2f} ({idx['change_pct']:+.2f}%)")
    msg += ["", *lines, "", "• 장중 잠정치는 경보에 사용하지 않습니다. 정규장 마감 이후 값을 우선하고, 18:10 이후 한 번 더 재조회해 변동 시 정정합니다.", f'• <a href="{html.escape(KRX_FLOW_PAGE, quote=True)}">KRX 투자자별 거래실적 페이지</a>']
    watch.ALERT_PATH.write_text("\n".join(msg) + "\n", encoding="utf-8")


def _append_close_context(pending: dict) -> None:
    now = dt.datetime.now(watch.KST)
    if now.weekday() < 5 and now.time() < dt.time(15, 45):
        return
    idx = _fetch_kospi_close()
    if idx:
        pending.setdefault("snapshot", {})["kospi_close"] = idx
        watch.PENDING_PATH.write_text(json.dumps(pending, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    if not watch.ALERT_PATH.exists() or not idx:
        return
    text = watch.ALERT_PATH.read_text(encoding="utf-8").strip()
    if "KOSPI 종가:" in text:
        return
    phase = _phase(now)
    lines = text.splitlines()
    lines.insert(2 if len(lines) >= 2 else len(lines), f"• {phase} KOSPI 종가: {idx['close']:,.2f} ({idx['change_pct']:+.2f}%)")
    watch.ALERT_PATH.write_text("\n".join(lines) + "\n", encoding="utf-8")


watch.fmt_eok = _fmt_amount
watch.fetch_kospi_foreign_flow = fetch_flow
watch.add_event = add_event_close_first


def main() -> int:
    old = watch.load_state()
    rc = watch.main()
    if watch.PENDING_PATH.exists():
        try:
            pending = json.loads(watch.PENDING_PATH.read_text(encoding="utf-8"))
            _write_postclose_correction_if_needed(old, pending)
            _append_close_context(pending)
        except Exception as exc:
            with watch.ERROR_PATH.open("a", encoding="utf-8") as f:
                f.write(f"마감/재조회 수급 확인 실패: {type(exc).__name__}: {exc}\n")
    return rc


if __name__ == "__main__":
    raise SystemExit(main())
