#!/usr/bin/env python3
"""Acknowledge source/delivery failures and recovery without alert storms.

One failure notification per KST date and one recovery notification once the
source and Telegram delivery path have recovered. No stale GDP values are sent.
The state is persisted by GitHub Actions after this step.
"""
from __future__ import annotations
import datetime as dt
import json
import os
import pathlib
import urllib.parse
import urllib.request
from zoneinfo import ZoneInfo

ROOT = pathlib.Path(__file__).resolve().parents[1]
STATE = ROOT / "data" / "gdpnow_watch_health_state.json"
OUT = ROOT / "out"
OUT.mkdir(parents=True, exist_ok=True)
PENDING = OUT / "gdpnow_watch_health_pending_state.json"
EXPECTED = "khs8879887988798879_bot"
KST = ZoneInfo("Asia/Seoul")


def state_read() -> dict:
    if not STATE.exists():
        return {}
    try:
        value = json.loads(STATE.read_text(encoding="utf-8"))
        return value if isinstance(value, dict) else {}
    except (ValueError, OSError):
        return {}


def send_message(message: str) -> int:
    token = (os.getenv("TELEGRAM_BOT_TOKEN") or "").strip()
    chat_id = (os.getenv("TELEGRAM_CHAT_ID") or "").strip()
    if not token or not chat_id:
        raise RuntimeError("Dedicated Telegram bot token/chat ID missing; no fallback permitted")
    with urllib.request.urlopen(
        f"https://api.telegram.org/bot{token}/getMe", timeout=20
    ) as response:
        identity = json.loads(response.read().decode("utf-8"))
    actual = str((identity.get("result") or {}).get("username") or "")
    if not identity.get("ok") or actual.lower() != EXPECTED.lower():
        raise RuntimeError("Wrong destination bot; refusing delivery")
    req = urllib.request.Request(
        f"https://api.telegram.org/bot{token}/sendMessage",
        data=urllib.parse.urlencode({
            "chat_id": chat_id, "text": message,
            "disable_web_page_preview": "true",
        }).encode("utf-8"),
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=20) as response:
        result = json.loads(response.read().decode("utf-8"))
    if not result.get("ok"):
        raise RuntimeError("Telegram sendMessage refused health alert")
    msgid = (result.get("result") or {}).get("message_id")
    if msgid is None:
        raise RuntimeError("Telegram missing confirmed message ID")
    return int(msgid)


def main() -> int:
    now = dt.datetime.now(KST)
    day = now.date().isoformat()
    source_outcome = (os.getenv("SOURCE_OUTCOME") or "").lower()
    send_outcome = (os.getenv("SEND_OUTCOME") or "").lower()
    source_good = source_outcome == "success"
    delivery_good = send_outcome in ("success", "skipped")
    failing = not source_good or not delivery_good
    prior = state_read()
    new = dict(prior)
    new["last_check_kst"] = now.isoformat(timespec="seconds")
    new["last_source_outcome"] = source_outcome
    new["last_telegram_outcome"] = send_outcome
    new["failing"] = failing

    if failing:
        if not prior.get("failing"):
            new["failure_since"] = now.isoformat(timespec="seconds")
        if prior.get("last_failure_alert_date") != day:
            which = "GDPNow 공식 자료 조회·검증 실패" if not source_good else "텔레그램 발송/경로 검증 실패"
            message = (
                "[GDPNow 감시 장애]\n"
                f"기준: {now.strftime('%Y-%m-%d %H:%M KST')}\n"
                f"상태: {which}\n"
                "GDPNow·금리·유가 최신 알림을 정상 발송했다고 판단하지 않습니다.\n"
                "오류 시 과거값 재사용·임의 추정 금지. GitHub Actions 로그 확인 필요.\n"
                "출처: https://github.com/qedgwangju-dot/khs-watch/actions/workflows/gdpnow-long-rates-telegram-watch.yml"
            )
            msgid = send_message(message)
            new["last_failure_alert_date"] = day
            new["last_failure_message_id"] = msgid
            print(f"gdpnow_health_failure_notification_confirmed={msgid}")
    elif prior.get("failing"):
        message = (
            "[GDPNow 감시 복구]\n"
            f"기준: {now.strftime('%Y-%m-%d %H:%M KST')}\n"
            "공식 자료 조회 및 연결된 알림 실행 단계가 정상 종료됐습니다.\n"
            "과거 누락 관측을 1회 발표 변화로 합산하지 않습니다.\n"
            "새로운 관측에 대한 금리 방향·당시값은 별도 GDPNow 알림을 확인하세요."
        )
        msgid = send_message(message)
        new["last_recovery_message_id"] = msgid
        new["failure_since"] = None
        print(f"gdpnow_health_recovery_notification_confirmed={msgid}")
    else:
        new["failure_since"] = None
    PENDING.write_text(json.dumps(new, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"gdpnow_health_status={'failing' if failing else 'healthy'}")
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
