#!/usr/bin/env python3
from __future__ import annotations

import datetime as dt
import html
import json
import pathlib
import re

import korea_market_stress_watch_v6 as v6

watch = v6.watch
_original_add_event = watch.add_event
_original_fmt_eok = watch.fmt_eok


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


def _event_date(key: str) -> dt.date | None:
    m = re.search(r":(20\d{2}-\d{2}-\d{2})(?::|$)", key)
    if not m:
        return None
    try:
        return dt.date.fromisoformat(m.group(1))
    except Exception:
        return None


def _flow_phase(key: str) -> str:
    now = dt.datetime.now(watch.KST)
    event_date = _event_date(key)
    if event_date == now.date() and now.weekday() < 5 and now.time() < dt.time(15, 40):
        return "장중 잠정"
    if event_date == now.date() and now.weekday() < 5:
        return "장마감 확인"
    return "최근 거래일"


def add_event_precise(events, key: str, text: str, source: str) -> None:
    if key.startswith("foreign1d_") or key.startswith("foreign3d_"):
        phase = _flow_phase(key)
        # 음수 값을 '순매수 -...'라고 쓰지 않고 방향 자체를 순매도로 표시한다.
        text = re.sub(r"KOSPI 외국인 1일 순매수 -([^—]+)", rf"KOSPI 외국인 {phase}: 1일 순매도 \1", text)
        text = re.sub(r"KOSPI 외국인 1일 순매수 \+([^—]+)", rf"KOSPI 외국인 {phase}: 1일 순매수 \1", text)
        text = re.sub(r"KOSPI 외국인 최근 3거래일 누적 -([^—]+)", rf"KOSPI 외국인 {phase}: 최근 3거래일 누적 순매도 \1", text)
        text = re.sub(r"KOSPI 외국인 최근 3거래일 누적 \+([^—]+)", rf"KOSPI 외국인 {phase}: 최근 3거래일 누적 순매수 \1", text)
        text = text.replace("— -1조원 기준 돌파", "— 순매도 1조원 기준 돌파")
        text = text.replace("— +1조원 기준 돌파", "— 순매수 1조원 기준 돌파")
        text = text.replace("— -3조원 기준 돌파", "— 누적 순매도 3조원 기준 돌파")
        text = text.replace("— +3조원 기준 돌파", "— 누적 순매수 3조원 기준 돌파")
    _original_add_event(events, key, text, source)


def _flow_threshold_state(flow: dict) -> dict[str, bool]:
    return {
        "foreign1d_pos": int(flow.get("daily_krw") or 0) >= 1_000_000_000_000,
        "foreign1d_neg": int(flow.get("daily_krw") or 0) <= -1_000_000_000_000,
        "foreign3d_pos": int(flow.get("three_day_krw") or 0) >= 3_000_000_000_000,
        "foreign3d_neg": int(flow.get("three_day_krw") or 0) <= -3_000_000_000_000,
    }


def _write_close_correction(old: dict, pending: dict) -> None:
    now = dt.datetime.now(watch.KST)
    if now.weekday() >= 5 or now.time() < dt.time(15, 40):
        return

    old_flow = ((old.get("snapshot") or {}).get("foreign_flow") or {})
    new_flow = ((pending.get("snapshot") or {}).get("foreign_flow") or {})
    if not old_flow or not new_flow:
        return
    if new_flow.get("date") != now.date().isoformat():
        return

    old_state = _flow_threshold_state(old_flow)
    new_state = _flow_threshold_state(new_flow)
    corrections: list[str] = []

    if old_state["foreign1d_neg"] and not new_state["foreign1d_neg"]:
        corrections.append(
            f"• KOSPI 외국인 장마감 정정: 장중 순매도 {_fmt_amount(int(old_flow['daily_krw'])).lstrip('-')} → "
            f"최종 순매도 {_fmt_amount(int(new_flow['daily_krw'])).lstrip('-')} — 1조원 기준 이탈"
        )
    elif old_state["foreign1d_pos"] and not new_state["foreign1d_pos"]:
        corrections.append(
            f"• KOSPI 외국인 장마감 정정: 장중 순매수 {_fmt_amount(int(old_flow['daily_krw'])).lstrip('+')} → "
            f"최종 순매수 {_fmt_amount(int(new_flow['daily_krw'])).lstrip('+')} — 1조원 기준 이탈"
        )

    if old_state["foreign3d_neg"] and not new_state["foreign3d_neg"]:
        corrections.append(
            f"• 최근 3거래일 누적 장마감 정정: 장중 순매도 {_fmt_amount(int(old_flow['three_day_krw'])).lstrip('-')} → "
            f"최종 순매도 {_fmt_amount(int(new_flow['three_day_krw'])).lstrip('-')} — 3조원 기준 이탈"
        )
    elif old_state["foreign3d_pos"] and not new_state["foreign3d_pos"]:
        corrections.append(
            f"• 최근 3거래일 누적 장마감 정정: 장중 순매수 {_fmt_amount(int(old_flow['three_day_krw'])).lstrip('+')} → "
            f"최종 순매수 {_fmt_amount(int(new_flow['three_day_krw'])).lstrip('+')} — 3조원 기준 이탈"
        )

    if not corrections:
        return

    source = str(new_flow.get("source") or "")
    lines = [
        "🔄 <b>KOSPI 외국인 수급 장마감 정정</b>",
        f"• 조회: {now:%Y-%m-%d %H:%M} KST",
        "",
        *corrections,
        "",
        "• 장중 수급은 잠정치이므로 마감 전 임계치를 넘었다가 종가 기준으로 다시 내려올 수 있습니다.",
        "• 앞으로 장중 알림에는 ‘장중 잠정’, 마감 후에는 ‘장마감 확인’을 명시합니다.",
    ]
    if source:
        lines += ["", f'• <a href="{html.escape(source, quote=True)}">원문</a>']
    watch.ALERT_PATH.write_text("\n".join(lines) + "\n", encoding="utf-8")


def _prepend_query_time() -> None:
    if not watch.ALERT_PATH.exists():
        return
    text = watch.ALERT_PATH.read_text(encoding="utf-8").strip()
    if not text or "• 조회:" in text:
        return
    now = dt.datetime.now(watch.KST)
    lines = text.splitlines()
    lines.insert(1, f"• 조회: {now:%Y-%m-%d %H:%M} KST")
    watch.ALERT_PATH.write_text("\n".join(lines) + "\n", encoding="utf-8")


watch.fmt_eok = _fmt_amount
watch.add_event = add_event_precise


def main() -> int:
    old = watch.load_state()
    rc = watch.main()
    if watch.PENDING_PATH.exists():
        try:
            pending = json.loads(watch.PENDING_PATH.read_text(encoding="utf-8"))
            _write_close_correction(old, pending)
        except Exception as exc:
            with watch.ERROR_PATH.open("a", encoding="utf-8") as f:
                f.write(f"장마감 수급 정정 확인 실패: {type(exc).__name__}: {exc}\n")
    _prepend_query_time()
    return rc


if __name__ == "__main__":
    raise SystemExit(main())
