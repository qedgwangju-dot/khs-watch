#!/usr/bin/env python3
"""Official U.S. Treasury 30-year EOD JPM scenario crossing watch.

Separate from the daily ETF report and the weekly TFF positioning report.
Only *new* official daily par-yield observations can create alerts.
"""
from __future__ import annotations

import datetime as dt
import hashlib
import html
import json
import os
import pathlib
import time
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from decimal import Decimal
from zoneinfo import ZoneInfo

import requests
import treasury_etf_flow_watch as treasury

ROOT = pathlib.Path(__file__).resolve().parents[1]
STATE = ROOT / "data" / "treasury_30y_jpm_level_state.json"
OUT = ROOT / "out"
OUT.mkdir(exist_ok=True)
STATE.parent.mkdir(exist_ok=True)
KST = ZoneInfo("Asia/Seoul")
NY = ZoneInfo("America/New_York")
SOURCE = "https://home.treasury.gov/resource-center/data-chart-center/interest-rates/pages/xml"
UP = (559, 578, 600)    # 5.59%, 5.78%, 6.00%
DOWN = (525, 515)       # 5.25%, 5.15%
REARM_BP = 5
ROUTE = "khs8879887988798879_bot"


def bp_from_percent(value):
    result = Decimal(str(value)) * 100
    if not result.is_finite() or result != result.to_integral_value() or not 0 <= result <= 1500:
        raise RuntimeError("Official Treasury 30Y yield precision/range invalid")
    return int(result)


def pct(bp):
    return f"{Decimal(bp) / 100:.2f}%"


def load_state():
    if not STATE.exists():
        return None
    payload = json.loads(STATE.read_text(encoding="utf-8"))
    if payload.get("version") != 1:
        raise RuntimeError("Unknown 30Y alert state version: manual review required")
    return payload


def save_state(payload):
    temp = STATE.with_suffix(".json.tmp")
    temp.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    temp.replace(STATE)


def days_since_business_date(value, now_ny=None):
    today = now_ny or dt.datetime.now(NY).date()
    day = dt.date.fromisoformat(value)
    if day > today:
        raise RuntimeError("Official 30Y quote has a future observation date")
    count = 0
    while day < today:
        day += dt.timedelta(days=1)
        if day.weekday() < 5:
            count += 1
    return count


def fetch_official_observations():
    year = dt.datetime.now(NY).year
    url = f"{SOURCE}?data=daily_treasury_yield_curve&field_tdr_date_value={year}"
    ns_data = "{http://schemas.microsoft.com/ado/2007/08/dataservices}"
    ns_atom = "{http://www.w3.org/2005/Atom}"
    rows = {}

    def ingest_year(y):
        year_url = f"{SOURCE}?data=daily_treasury_yield_curve&field_tdr_date_value={y}"
        response = requests.get(year_url, headers=treasury.HEADERS, timeout=(8, 35))
        response.raise_for_status()
        root = ET.fromstring(response.content)
        for entry in root.findall(ns_atom + "entry"):
            field_date = entry.find(".//" + ns_data + "NEW_DATE")
            field_y = entry.find(".//" + ns_data + "BC_30YEAR")
            if field_date is None or field_date.text is None:
                continue
            if field_y is None or not field_y.text:
                continue
            d = field_date.text[:10]
            dt.date.fromisoformat(d)
            b = bp_from_percent(field_y.text)
            if d in rows and rows[d] != b:
                raise RuntimeError("Inconsistent Treasury 30Y data for same observation date")
            rows[d] = b

    ingest_year(year)
    if len(rows) < 10:
        ingest_year(year - 1)  # Avoid losing December→January crossings.

    if len(rows) < 2:
        raise RuntimeError("Official 30Y Treasury history too short")
    observations = sorted(rows.items())
    last_date, last_bp = observations[-1]
    if days_since_business_date(last_date) > 3:
        raise RuntimeError(f"Official Treasury 30Y observation is stale: {last_date}")

    # A second independently implemented parser must agree on the official day
    # and the quote. The year-boundary time-zone mismatch is handled above.
    if dt.datetime.now(KST).year == year:
        parsed = treasury.get_treasury_curve()
        if parsed.get("date") != last_date or bp_from_percent(parsed.get("30Y")) != last_bp:
            raise RuntimeError("Official Treasury 30Y independent-parser mismatch")
    return observations, url


def initial_state(date, current_bp):
    return {
        "version": 1,
        "last_processed_date": date,
        "last_processed_bp": current_bp,
        "armed_up": {str(t): current_bp < t for t in UP},
        "armed_down": {str(t): current_bp > t for t in DOWN},
        "last_sent_event": None,
        "last_message_id": None,
        "last_send_confirmed_at_kst": None,
    }


def evaluate(state, date, current_bp, previous_date, previous_bp):
    """Pure transition. Never converts a level already held into a new crossing."""
    if date < state["last_processed_date"]:
        raise RuntimeError("Treasury observation date regressed; refusing alert")
    if date == state["last_processed_date"]:
        if current_bp != state["last_processed_bp"]:
            raise RuntimeError("Previously processed 30Y quote was revised; manual review required")
        return dict(state), []

    if previous_date != state["last_processed_date"] or previous_bp != state["last_processed_bp"]:
        raise RuntimeError(
            "Official data gap/revision since last accepted observation; "
            "do not manufacture crossing alerts from stale history"
        )

    result = json.loads(json.dumps(state))
    triggers = []
    for t in UP:
        key = str(t)
        if current_bp <= t - REARM_BP:
            result["armed_up"][key] = True
        elif previous_bp < t <= current_bp and result["armed_up"].get(key, False):
            triggers.append(("상향", t))
            result["armed_up"][key] = False
    for t in DOWN:
        key = str(t)
        if current_bp >= t + REARM_BP:
            result["armed_down"][key] = True
        elif previous_bp > t >= current_bp and result["armed_down"].get(key, False):
            triggers.append(("하향", t))
            result["armed_down"][key] = False

    result["last_processed_date"] = date
    result["last_processed_bp"] = current_bp
    return result, triggers


def crossing_message(date, current_bp, previous_date, previous_bp, triggers, url):
    parts = []
    for direction, t in triggers:
        if direction == "상향":
            why = {
                559: "채권 가격 약세·장기 할인율 압력 재확인",
                578: "JPM 장기 약세 목표 구간 진입",
                600: "장기금리 6%대 스트레스 진입",
            }[t]
        else:
            why = {
                525: "숏커버·CTA 매수전환 가능성 점검",
                515: "채권 가격 반전 가능성 강화",
            }[t]
        parts.append(f"• {pct(t)} {direction} 통과 → {why}")

    if all(x[0] == "상향" for x in triggers):
        status = "장기채 약세 위험 강화"
        market = "TLT·장기 국채 가격에는 부담, 고밸류 성장주의 할인율도 경계"
    else:
        status = "장기채 기술적 반등 후보"
        market = "금리 하락은 장기채 가격에 우호적이나 CTA 실제 전환은 미확인"

    text = "\n".join([
        "[미 국채 30년물 기술선 신규 돌파]",
        f"전체 판정: {status}",
        f"공식 종가: {previous_date} {pct(previous_bp)} → {date} {pct(current_bp)}",
        "새로 확인된 기준선:",
        *parts,
        f"시장 의미: {market}",
        "검증: 미 재무부 일별 30년물 기준. 장중 실시간 돌파가 아닌 공식 일별 관측치.",
        "주의: JPM 2026-09-29 기술적 기준이며 목표 도달·CTA 주문 실행이 확정됐다는 뜻은 아님.",
        f"원문: {url}",
    ])
    return text


def send_telegram(text):
    token = (os.environ.get("TELEGRAM_BOT_TOKEN") or "").strip()
    chat = (os.environ.get("TELEGRAM_CHAT_ID") or "").strip()
    if not token or not chat:
        raise RuntimeError("Telegram route secrets missing")
    with urllib.request.urlopen(f"https://api.telegram.org/bot{token}/getMe", timeout=25) as f:
        account = json.loads(f.read().decode("utf-8"))
    username = str((account.get("result") or {}).get("username") or "")
    if not account.get("ok") or username.lower() != ROUTE.lower():
        raise RuntimeError("Telegram bot identity mismatch; refusing wrong route")
    chat_query = urllib.parse.urlencode({"chat_id": chat})
    with urllib.request.urlopen(f"https://api.telegram.org/bot{token}/getChat?{chat_query}", timeout=25) as f:
        target = json.loads(f.read().decode("utf-8"))
    if not target.get("ok") or str((target.get("result") or {}).get("id")) != chat:
        raise RuntimeError("Telegram target chat verification failed")

    output = []
    for line in text.splitlines():
        line = html.escape(line, quote=False)
        if line.startswith(("전체 판정:", "공식 종가:", "시장 의미:", "새로 확인된 기준선:")):
            line = "<b>" + line + "</b>"
        output.append(line)
    payload = urllib.parse.urlencode({
        "chat_id": chat,
        "text": "\n".join(output),
        "parse_mode": "HTML",
        "disable_web_page_preview": "true",
    }).encode()
    req = urllib.request.Request(
        f"https://api.telegram.org/bot{token}/sendMessage", data=payload, method="POST"
    )
    with urllib.request.urlopen(req, timeout=30) as f:
        response = json.loads(f.read().decode("utf-8"))
    message_id = (response.get("result") or {}).get("message_id")
    if not response.get("ok") or not message_id:
        raise RuntimeError("Telegram send not confirmed; alert state left pending")
    return int(message_id)


def main():
    observations, url = fetch_official_observations()
    latest_date, latest_bp = observations[-1]
    prior_date, prior_bp = observations[-2]

    state = load_state()
    if state is None:
        state = initial_state(latest_date, latest_bp)
        save_state(state)
        print(f"treasury_30y_bootstrap=true date={latest_date} yield={pct(latest_bp)} telegram_sent=false")
        return

    # Replay any missed official dates to repair state automatically after a
    # GitHub scheduling outage. Only latest-day crossings may create alerts.
    history = dict(observations)
    saved_date = state["last_processed_date"]
    if saved_date not in history:
        raise RuntimeError("Accepted Treasury baseline is outside official history; manual review required")
    if history[saved_date] != state["last_processed_bp"]:
        raise RuntimeError("Official Treasury baseline revised; refusing an unverified crossing")
    updated = dict(state)
    events = []
    missed_events = 0
    prev_date, prev_bp = saved_date, history[saved_date]
    for day, new_bp in observations:
        if day <= saved_date:
            continue
        updated, candidates = evaluate(updated, day, new_bp, prev_date, prev_bp)
        if day == latest_date:
            events = candidates
        else:
            missed_events += len(candidates)
        prev_date, prev_bp = day, new_bp
    if missed_events:
        print(f"treasury_30y_replayed_old_crossings_without_retro_alert={missed_events}")
    if not events:
        if updated != state:
            save_state(updated)
        print(f"treasury_30y_no_new_crossing=true date={latest_date} yield={pct(latest_bp)}")
        return

    report = crossing_message(latest_date, latest_bp, prior_date, prior_bp, events, url)
    OUT.joinpath("treasury_30y_jpm_crossing_preview.txt").write_text(
        report + "\n", encoding="utf-8"
    )
    if os.getenv("TREASURY_30Y_VALIDATE_ONLY") == "1":
        print("treasury_30y_validation_only=true telegram_sent=false\n" + report)
        return

    mid = send_telegram(report)
    updated["last_sent_event"] = {
        "date": latest_date,
        "direction_and_levels": [[a, t] for a, t in events],
        "fingerprint": hashlib.sha256(report.encode("utf-8")).hexdigest(),
    }
    updated["last_message_id"] = mid
    updated["last_send_confirmed_at_kst"] = dt.datetime.now(KST).isoformat()
    save_state(updated)
    print(f"telegram_delivery_confirmed=true bot=@{ROUTE} message_id={mid} official_date={latest_date}")


if __name__ == "__main__":
    main()
