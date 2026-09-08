#!/usr/bin/env python3
from __future__ import annotations

import datetime as dt
import html
import json
import os
import time
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

import requests

from kospi_flow_attribution_ls import attribution_html_lines, fetch_attribution

KST = ZoneInfo("Asia/Seoul")
STATE_PATH = Path("data/kospi_rapid_fallback_state.json")
PENDING_PATH = Path("out/kospi_rapid_fallback_pending_state.json")
STATUS_PATH = Path("out/kospi_rapid_fallback_status.md")

KOSPI_API = "https://m.stock.naver.com/api/index/KOSPI/basic"
KOSPI_POLLING_API = "https://polling.finance.naver.com/api/realtime?query=SERVICE_INDEX:KOSPI"
KOSPI_URL = "https://m.stock.naver.com/domestic/index/KOSPI/total"

SESSION_HIGH_DD = -1.50
FAST_15M = -1.00
FAST_30M = -1.25
START_TIME = dt.time(9, 0)
END_TIME = dt.time(15, 35)


def fnum(v: Any) -> float | None:
    try:
        if v is None or str(v).strip() == "":
            return None
        return float(str(v).replace(",", "").strip())
    except Exception:
        return None


def pct(a: float | None, b: float | None) -> float | None:
    if a is None or b is None or a == 0:
        return None
    return (b / a - 1.0) * 100.0


def load_state(today: str) -> dict[str, Any]:
    try:
        state = json.loads(STATE_PATH.read_text(encoding="utf-8"))
    except Exception:
        state = {}
    if state.get("date") != today:
        state = {"date": today, "samples": [], "session_high": None,
                 "sent_session_high": False, "sent_fast": False,
                 "last_alert_ts": None}
    return state


def save_pending(state: dict[str, Any]) -> None:
    PENDING_PATH.parent.mkdir(parents=True, exist_ok=True)
    PENDING_PATH.write_text(json.dumps(state, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def fetch_kospi() -> dict[str, Any]:
    headers = {"User-Agent": "Mozilla/5.0"}
    try:
        r = requests.get(KOSPI_POLLING_API, headers=headers, timeout=15)
        r.raise_for_status()
        payload = r.json()
        row = (((payload.get("result") or {}).get("areas") or [{}])[0].get("datas") or [{}])[0]
        if isinstance(row, dict) and row.get("nv") is not None:
            return {
                "closePrice": (fnum(row.get("nv")) or 0.0) / 100.0,
                "highPrice": (fnum(row.get("hv")) or 0.0) / 100.0 if row.get("hv") is not None else None,
                "openPrice": (fnum(row.get("ov")) or 0.0) / 100.0 if row.get("ov") is not None else None,
                "lowPrice": (fnum(row.get("lv")) or 0.0) / 100.0 if row.get("lv") is not None else None,
                "fluctuationsRatio": fnum(row.get("cr")),
                "marketStatus": row.get("ms"), "source": "naver_polling",
            }
    except Exception:
        pass
    r = requests.get(KOSPI_API, headers=headers, timeout=15)
    r.raise_for_status()
    data = r.json()
    if not isinstance(data, dict):
        raise RuntimeError("Naver KOSPI response is not an object")
    data["source"] = "naver_basic"
    return data


def get_price(data: dict[str, Any]) -> float | None:
    for key in ("closePrice", "currentPrice", "now", "price"):
        value = fnum(data.get(key))
        if value is not None and value > 0:
            return value
    return None


def get_high(data: dict[str, Any]) -> float | None:
    for key in ("highPrice", "dayHighPrice", "high"):
        value = fnum(data.get(key))
        if value is not None and value > 0:
            return value
    return None


def nearest_sample(samples: list[dict[str, Any]], seconds_ago: int, now_ts: float) -> float | None:
    if not samples:
        return None
    target = now_ts - seconds_ago
    row = min(samples, key=lambda x: abs(float(x.get("ts", 0)) - target))
    if now_ts - float(row.get("ts", now_ts)) < seconds_ago * 0.65:
        return None
    return fnum(row.get("price"))


def telegram_send(text: str) -> int:
    token = (os.getenv("DERIV_TELEGRAM_BOT_TOKEN") or "").strip()
    chat_id = (os.getenv("DERIV_TELEGRAM_CHAT_ID") or "").strip()
    expected = (os.getenv("DERIV_EXPECTED_TELEGRAM_BOT_USERNAME") or "khs887900887900008879_bot").strip().lstrip("@")
    if not token or not chat_id:
        raise RuntimeError("KOSPI derivative Telegram secrets missing")
    with urllib.request.urlopen(f"https://api.telegram.org/bot{token}/getMe", timeout=20) as response:
        identity = json.loads(response.read().decode("utf-8"))
    actual = str((identity.get("result") or {}).get("username") or "")
    if not identity.get("ok") or actual.lower() != expected.lower():
        raise RuntimeError(f"Wrong derivative Telegram bot: expected @{expected}, got @{actual or 'unknown'}")
    payload = urllib.parse.urlencode({"chat_id": chat_id, "text": text,
        "parse_mode": "HTML", "disable_web_page_preview": "true"}).encode("utf-8")
    req = urllib.request.Request(f"https://api.telegram.org/bot{token}/sendMessage", data=payload, method="POST")
    with urllib.request.urlopen(req, timeout=30) as response:
        result = json.loads(response.read().decode("utf-8"))
    if not result.get("ok"):
        raise RuntimeError(f"Telegram rejected fallback alert: {result}")
    return int(result["result"]["message_id"])


def build_alert(now: dt.datetime, cur: float, high: float, dd: float,
                m15: float | None, m30: float | None, reasons: list[str],
                attribution: dict[str, Any] | None, attribution_error: str | None) -> str:
    lines = ["🚨 <b>코스피 급락·매도주체 경보</b>", f"<code>{now:%Y-%m-%d %H:%M:%S} KST</code>", "",
             "<b>현재 움직임</b>", f"• KOSPI <b>{cur:,.2f}</b>",
             f"• 장중 고점 <b>{high:,.2f}</b> → 현재 <b>{cur:,.2f}</b> · 고점 대비 <b>{dd:+.2f}%</b>"]
    if m15 is not None:
        lines.append(f"• 15분 <b>{m15:+.2f}%</b>")
    if m30 is not None:
        lines.append(f"• 30분 <b>{m30:+.2f}%</b>")
    lines += ["", "<b>경보 사유</b>"] + [f"• {html.escape(r)}" for r in reasons] + [""]
    if attribution:
        lines += attribution_html_lines(attribution)
    else:
        lines += ["<b>누가 밀었나 · 급락구간 수급</b>",
                  f"• LS 주체별 수급 조회 실패 — 가격 경보는 유지하고 원인 주체는 확정하지 않음{': ' + html.escape(attribution_error) if attribution_error else ''}"]
    lines += ["", "<b>읽는 법</b>",
              "• <b>급락구간 변화량</b>이 원인 판정의 우선 기준입니다. 하루 누적 순매수만 보고 '누가 밀었다'고 단정하지 않습니다.",
              "• 외국인·기관·개인의 현물 매도와 KOSPI200·선물 동조, 프로그램 매도까지 겹칠수록 원인 확신도를 높입니다.",
              "• 수급은 원인 후보이며 뉴스·대형주 급락과 함께 교차 확인합니다.", "",
              f'• <a href="{KOSPI_URL}">KOSPI 확인</a>']
    return "\n".join(lines)


def write_status(now: dt.datetime, status: str, details: dict[str, Any] | None = None) -> None:
    STATUS_PATH.parent.mkdir(parents=True, exist_ok=True)
    lines = ["# 코스피 급락 안전망", "", f"- 조회: {now:%Y-%m-%d %H:%M:%S} KST", f"- 상태: {status}"]
    for k, v in (details or {}).items():
        lines.append(f"- {k}: {v}")
    STATUS_PATH.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> int:
    now = dt.datetime.now(KST)
    today = now.date().isoformat()
    state = load_state(today)
    if now.weekday() >= 5 or not (START_TIME <= now.time() <= END_TIME):
        save_pending(state)
        write_status(now, "장외 시간 — 발송 없음")
        return 0

    data = fetch_kospi()
    cur = get_price(data)
    if cur is None:
        raise RuntimeError(f"KOSPI current price missing; keys={sorted(data.keys())[:50]}")
    api_high = get_high(data)
    prev_high = fnum(state.get("session_high"))
    session_high = max(x for x in (api_high, prev_high, cur) if x is not None)
    state["session_high"] = session_high

    now_ts = time.time()
    samples = list(state.get("samples") or [])
    samples.append({"ts": now_ts, "price": cur})
    cutoff = now_ts - 3 * 60 * 60
    samples = [x for x in samples if float(x.get("ts", 0)) >= cutoff]
    state["samples"] = samples[-30:]
    p15 = nearest_sample(samples[:-1], 15 * 60, now_ts)
    p30 = nearest_sample(samples[:-1], 30 * 60, now_ts)
    m15, m30 = pct(p15, cur), pct(p30, cur)
    dd = pct(session_high, cur) or 0.0

    session_hit = dd <= SESSION_HIGH_DD
    fast15_hit = m15 is not None and m15 <= FAST_15M
    fast30_hit = m30 is not None and m30 <= FAST_30M
    fast_hit = fast15_hit or fast30_hit
    reasons: list[str] = []
    if session_hit and not state.get("sent_session_high"):
        reasons.append(f"장중 고점 대비 {dd:+.2f}% ≤ {SESSION_HIGH_DD:.2f}%")
    if fast_hit and not state.get("sent_fast"):
        if fast15_hit:
            reasons.append(f"15분 {m15:+.2f}% ≤ {FAST_15M:.2f}%")
        if fast30_hit:
            reasons.append(f"30분 {m30:+.2f}% ≤ {FAST_30M:.2f}%")

    msg_id = None
    attribution = None
    attribution_error = None
    window = 15 if fast15_hit else 30
    if reasons:
        try:
            attribution = fetch_attribution(window_minutes=window)
        except Exception as exc:
            attribution_error = f"{type(exc).__name__}: {exc}"
        msg_id = telegram_send(build_alert(now, cur, session_high, dd, m15, m30,
                                           reasons, attribution, attribution_error))
        if session_hit:
            state["sent_session_high"] = True
        if fast_hit:
            state["sent_fast"] = True
        state["last_alert_ts"] = now.isoformat(timespec="seconds")
        state["last_message_id"] = msg_id

    save_pending(state)
    cls = (attribution or {}).get("classification") or {}
    write_status(now, "경보 발송" if msg_id else "정상 감시 — 신규 조건 없음", {
        "데이터 경로": data.get("source"), "KOSPI": f"{cur:,.2f}",
        "장중 고점": f"{session_high:,.2f}", "고점 대비": f"{dd:+.2f}%",
        "15분": "계산 대기" if m15 is None else f"{m15:+.2f}%",
        "30분": "계산 대기" if m30 is None else f"{m30:+.2f}%",
        "수급 판정": cls.get("verdict") or ("조회 실패" if attribution_error else "미조회"),
        "텔레그램 ID": msg_id,
    })
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
