#!/usr/bin/env python3
"""Official U.S. Treasury 30Y JPM level-crossing alert.

One compact event message per newly crossed level, not a periodic market report.
The levels are user-supplied JPM technical reference points, not official policy levels.
"""
from __future__ import annotations

import datetime as dt
import hashlib
import html
import json
import os
from pathlib import Path
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from zoneinfo import ZoneInfo

import requests

from treasury_credit_flow_watch_ishares import get_curve_pair
from global_rates_watch import fetch_ust_curve

ROOT = Path(__file__).resolve().parents[1]
STATE = ROOT / "data" / "treasury_30y_jpm_level_state.json"
OUT = ROOT / "out"
KST = ZoneInfo("Asia/Seoul")
NY = ZoneInfo("America/New_York")
XML_BASE = "https://home.treasury.gov/resource-center/data-chart-center/interest-rates/pages/xml"
SOURCE_URL = "https://home.treasury.gov/resource-center/data-chart-center/interest-rates/TextView?type=daily_treasury_yield_curve"
REARM = 0.05  # Five basis points in percentage-point units.
UP = (5.59, 5.78, 6.00)
DOWN = (5.25, 5.15)
REASONS = {
    ("up", 5.59): "장기국채 약세 압력이 커질 수 있는 JPM 1차 기술 기준",
    ("up", 5.78): "JPM의 추가 장기채 약세 목표 구간에 진입",
    ("up", 6.00): "장기금리 극단 스트레스 구간에 진입",
    ("down", 5.25): "장기채 숏커버·추세추종 매수 가능성을 점검할 첫 반전 후보",
    ("down", 5.15): "장기채 반등 추세가 강화되는지 점검할 추가 기준",
}


def k(direction: str, level: float) -> str:
    return f"{direction}:{level:.2f}"


def official_series(now: dt.datetime | None = None) -> list[tuple[str, float]]:
    """Full chronology avoids missing a crossing between delayed scheduled runs."""
    current = (now or dt.datetime.now(KST)).year
    points = {}
    for year in (current - 1, current):
        response = requests.get(
            XML_BASE,
            params={"data": "daily_treasury_yield_curve", "field_tdr_date_value": str(year)},
            headers={"User-Agent": "Mozilla/5.0 Treasury-JPM30Y-Watch/1.0"},
            timeout=(8, 35),
        )
        response.raise_for_status()
        root = ET.fromstring(response.content)
        ns = {"a": "http://www.w3.org/2005/Atom", "d": "http://schemas.microsoft.com/ado/2007/08/dataservices"}
        for entry in root.findall("a:entry", ns):
            date = entry.find(".//d:NEW_DATE", ns)
            value = entry.find(".//d:BC_30YEAR", ns)
            if date is None or value is None or not date.text or not value.text:
                continue
            day = date.text[:10]
            try:
                dt.date.fromisoformat(day)
                rate = float(value.text)
            except (ValueError, TypeError):
                continue
            if not 0.1 < rate < 20:
                raise RuntimeError(f"Official Treasury 30-year rate out of range: {day} {rate}")
            if day in points and points[day] != rate:
                raise RuntimeError(f"Official Treasury duplicate conflicting observation: {day}")
            points[day] = rate
    result = sorted(points.items())
    if len(result) < 2:
        raise RuntimeError("Official Treasury 30-year history has fewer than two complete observations")
    return result


def crosscheck_latest(points: list[tuple[str, float]]) -> None:
    # Two parsers, one official original data source. This is a parsing crosscheck,
    # not independent confirmation of the Treasury publication.
    current, previous = get_curve_pair()
    latest_date, latest_rate = points[-1]
    if latest_date != current["date"] or abs(latest_rate - current["30Y"]) > 0.00001:
        raise RuntimeError("U.S. Treasury raw-history and daily-market parser mismatch")
    if previous is not None and (
        points[-2][0] != previous["date"] or abs(points[-2][1] - previous["30Y"]) > 0.00001
    ):
        raise RuntimeError("U.S. Treasury previous-session parser mismatch")
    other = fetch_ust_curve()
    if other["ust30"].date != latest_date or abs(other["ust30"].value - latest_rate) > 0.00001:
        raise RuntimeError("U.S. Treasury global-rates reader mismatch")


def latest_expected_date(now: dt.datetime) -> str:
    day = now.astimezone(NY).date()
    while day.weekday() >= 5:
        day -= dt.timedelta(days=1)
    return day.isoformat()


def load_state() -> dict:
    if not STATE.exists():
        return {}
    result = json.loads(STATE.read_text(encoding="utf-8"))
    if not isinstance(result, dict):
        raise RuntimeError("JPM 30Y alert state is invalid")
    return result


def save_state(value: dict) -> None:
    STATE.parent.mkdir(parents=True, exist_ok=True)
    STATE.write_text(json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def bootstrap(date: str, rate: float) -> dict:
    """Do not announce an already-crossed level during initial deployment."""
    active = {}
    global_state = ROOT / "data" / "global_rates_watch_state.json"
    old = {}
    if global_state.exists():
        prior = json.loads(global_state.read_text(encoding="utf-8"))
        old = prior.get("active") or {}
    for level in UP:
        latched = old.get(f"ust30:jpm_up:{level}:latched")
        active[k("up", level)] = (
            not latched and rate < level if latched is not None else rate < level
        )
    for level in DOWN:
        latched = old.get(f"ust30:jpm_down:{level}:latched")
        active[k("down", level)] = (
            not latched and rate > level if latched is not None else rate > level
        )
    return {"version": 1, "last_date": date, "last_rate": rate, "armed": active, "last_alert": None}


def transition(state: dict, points: list[tuple[str, float]]) -> tuple[dict, list[dict]]:
    """Compute crossings on official daily observations; no same-date resend."""
    if not state:
        date, rate = points[-1]
        return bootstrap(date, rate), []

    next_state = dict(state)
    last_date = str(state.get("last_date") or "")
    if not last_date:
        raise RuntimeError("State exists but last_date is missing")
    older = [(d, v) for d, v in points if d == last_date]
    if not older:
        raise RuntimeError(f"Previous alert state date {last_date} unavailable in official history")
    if abs(older[-1][1] - float(state["last_rate"])) > 0.00001:
        raise RuntimeError("Revised Treasury observation differs from last confirmed state")

    armed = {str(name): bool(flag) for name, flag in (state.get("armed") or {}).items()}
    events = []
    previous_rate = float(state["last_rate"])
    for date, rate in points:
        if date <= last_date:
            continue
        # A latched upper level can rearm only after a five-basis-point retreat;
        # an upper crossing must also occur on a new official observation.
        for level in UP:
            key = k("up", level)
            on = armed.get(key, previous_rate < level)
            if not on and rate <= level - REARM:
                on = True
            if on and previous_rate < level <= rate:
                events.append({"date": date, "direction": "up", "level": level, "prev": previous_rate, "rate": rate})
                on = False
            armed[key] = on
        for level in DOWN:
            key = k("down", level)
            on = armed.get(key, previous_rate > level)
            if not on and rate >= level + REARM:
                on = True
            if on and previous_rate > level >= rate:
                events.append({"date": date, "direction": "down", "level": level, "prev": previous_rate, "rate": rate})
                on = False
            armed[key] = on
        previous_rate = rate
        next_state["last_date"] = date
        next_state["last_rate"] = rate
    next_state["armed"] = armed
    return next_state, events


def format_alert(events: list[dict], current_date: str, current_rate: float) -> str:
    by_date = {}
    for e in events:
        by_date.setdefault(e["date"], []).append(e)
    lines = [
        "[미국 30년 국채 — JPM 기술선 조건부 경보]",
        f"공식 관측: {current_date} | 30년물 {current_rate:.2f}%",
        "※ 미국 재무부 일별 확정 관측값이며 장중 실시간 돌파 알림은 아닙니다.",
        "",
    ]
    for date, items in by_date.items():
        for e in items:
            wording = "상향 돌파" if e["direction"] == "up" else "하향 돌파"
            sign = "+" if (e["rate"] - e["prev"]) >= 0 else ""
            lines += [
                f"{date} | {e['level']:.2f}% {wording}",
                f"→ 전회 {e['prev']:.2f}% → {e['rate']:.2f}% ({sign}{(e['rate']-e['prev'])*100:.0f}bp)",
                f"→ {REASONS[(e['direction'],e['level'])]}",
            ]
    lines += [
        "",
        "시장 의미: 금리↑는 장기채 가격·성장주 할인율에 부담, 금리↓는 완화 방향.",
        "채권 추세가 실제로 바뀌었는지는 TLT·CFTC 포지션·Repo·신용스프레드로 추가 검증.",
        "재알림: 같은 선을 5bp 이상 반대로 이탈한 뒤 다시 돌파할 때만.",
        "기술 기준: 사용자 제공 JPM 2026-09-29 분석(공식 정부 경계선 아님)",
        f"공식 금리: {SOURCE_URL}",
    ]
    return "\n".join(lines)


def send_telegram(text: str) -> int:
    token = (os.environ.get("TELEGRAM_BOT_TOKEN") or "").strip()
    chat = (os.environ.get("TELEGRAM_CHAT_ID") or "").strip()
    expected = "khs8879887988798879_bot"
    if not token or not chat:
        raise RuntimeError("Telegram route secrets missing")
    with urllib.request.urlopen(f"https://api.telegram.org/bot{token}/getMe", timeout=25) as response:
        user = json.loads(response.read().decode("utf-8"))
    if not user.get("ok") or (user.get("result") or {}).get("username", "").lower() != expected:
        raise RuntimeError("Telegram bot identity does not match designated bond alert bot")
    with urllib.request.urlopen(
        f"https://api.telegram.org/bot{token}/getChat?" + urllib.parse.urlencode({"chat_id": chat}),
        timeout=25,
    ) as response:
        target = json.loads(response.read().decode("utf-8"))
    if not target.get("ok") or str((target.get("result") or {}).get("id")) != chat:
        raise RuntimeError("Telegram chat identity verification failed")

    payload = urllib.parse.urlencode({
        "chat_id": chat,
        "text": "<b>" + html.escape(text.splitlines()[0]) + "</b>\n" + html.escape("\n".join(text.splitlines()[1:])),
        "parse_mode": "HTML",
        "disable_web_page_preview": "true",
    }).encode("utf-8")
    if len(payload) > 10000 or len(text) > 3800:
        raise RuntimeError("Alert text exceeds compact Telegram limit")
    req = urllib.request.Request(f"https://api.telegram.org/bot{token}/sendMessage", data=payload, method="POST")
    with urllib.request.urlopen(req, timeout=30) as response:
        answer = json.loads(response.read().decode("utf-8"))
    if not answer.get("ok") or not (answer.get("result") or {}).get("message_id"):
        raise RuntimeError("Telegram sendMessage returned no confirmed message ID")
    return int(answer["result"]["message_id"])


def main() -> None:
    now = dt.datetime.now(KST)
    points = official_series(now)
    crosscheck_latest(points)
    current_date, current_rate = points[-1]
    expected = latest_expected_date(now)
    if current_date > expected:
        raise RuntimeError(f"Treasury official observation in future: {current_date} > {expected}")
    if current_date < expected:
        print(f"official_treasury_not_yet_published=true expected={expected} latest={current_date}")
        return

    state = load_state()
    updated, events = transition(state, points)
    audit = (os.getenv("AUDIT_ONLY") or "").strip().lower() in ("1", "true", "yes")
    OUT.mkdir(exist_ok=True)
    diagnosis = {
        "as_of": current_date,
        "rate": current_rate,
        "previous": points[-2],
        "events": events,
        "audit_only": audit,
        "last_processed": state.get("last_date"),
        "report": format_alert(events, current_date, current_rate) if events else None,
    }
    OUT.joinpath("treasury_30y_jpm_audit.json").write_text(
        json.dumps(diagnosis, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    if audit:
        print(f"treasury_30y_jpm_audit_only=true source_date={current_date} rate={current_rate:.2f}% would_send={len(events)}")
        return

    if events:
        text = format_alert(events, current_date, current_rate)
        mid = send_telegram(text)
        updated["last_alert"] = {
            "source_date": current_date,
            "events": [f"{e['date']}:{k(e['direction'],e['level'])}" for e in events],
            "telegram_message_id": mid,
            "confirmed_at_kst": now.isoformat(),
        }
        print(f"telegram_delivery_confirmed=true message_id={mid} jpm_30y_events={len(events)} source_date={current_date}")
    elif not state:
        print(f"jpm_30y_baseline_initialized=true date={current_date} rate={current_rate:.2f}")
    else:
        print(f"jpm_30y_no_new_crossing=true date={current_date} rate={current_rate:.2f}")

    if updated != state:
        save_state(updated)


if __name__ == "__main__":
    main()
