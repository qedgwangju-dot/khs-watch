#!/usr/bin/env python3
"""Send and verify LG automotive chiplet alerts through the existing Telegram bot."""
import argparse
import datetime as dt
import json
import os
import pathlib
import urllib.parse
import urllib.request
from zoneinfo import ZoneInfo

ROOT = pathlib.Path(__file__).resolve().parents[1]
OUT = ROOT / "out"
OUT.mkdir(exist_ok=True)
ALERT = OUT / "lg_auto_chiplet_alert.html"

def api(endpoint, payload=None):
    token = (os.getenv("TELEGRAM_BOT_TOKEN") or "").strip()
    if not token:
        raise RuntimeError("Telegram bot token missing")
    url = "https://api.telegram.org/bot" + token + "/" + endpoint
    body = urllib.parse.urlencode(payload).encode("utf-8") if payload else None
    req = urllib.request.Request(url, data=body, method="POST" if body else "GET")
    with urllib.request.urlopen(req, timeout=25) as response:
        data = json.loads(response.read().decode("utf-8"))
    if not data.get("ok"):
        raise RuntimeError("Telegram " + endpoint + " not confirmed")
    return data["result"]

def check():
    chat_id = (os.getenv("TELEGRAM_CHAT_ID") or "").strip()
    expected = (os.getenv("EXPECTED_TELEGRAM_BOT_USERNAME") or "").strip().lstrip("@").lower()
    if not chat_id or not expected:
        raise RuntimeError("Telegram target chat or expected bot username missing")
    me = api("getMe")
    actual = str(me.get("username") or "")
    if actual.lower() != expected:
        raise RuntimeError("Wrong Telegram bot: expected @" + expected + ", got @" + actual)
    api("getChat", {"chat_id": chat_id})
    print("lg_chiplet_bot_verified=@" + actual)
    print("lg_chiplet_chat_verified=true")
    return chat_id

def chunks(value, limit=3500):
    parts, running = [], ""
    for para in value.strip().split("\n\n"):
        proposal = para if not running else running + "\n\n" + para
        if len(proposal) <= limit:
            running = proposal
        else:
            if running:
                parts.append(running)
            if len(para) > limit:
                raise RuntimeError("One HTML alert section exceeds Telegram limit")
            running = para
    if running:
        parts.append(running)
    return parts

def deliver(text, outfile, test=False):
    chat = check()
    ids = []
    for i, part in enumerate(chunks(text), 1):
        if i > 1:
            part = "<b>차량용 칩렛 감시 (계속)</b>\n\n" + part
        result = api("sendMessage", {
            "chat_id": chat,
            "text": part,
            "parse_mode": "HTML",
            "disable_web_page_preview": "true",
        })
        if not result.get("message_id"):
            raise RuntimeError("Telegram did not return message_id")
        ids.append(result["message_id"])
    receipt = {
        "status": "confirmed", "test": test, "message_ids": ids,
        "confirmed_at_kst": dt.datetime.now(ZoneInfo("Asia/Seoul")).isoformat(timespec="seconds"),
    }
    outfile.write_text(json.dumps(receipt, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"lg_chiplet_telegram_confirmed=true test={test} message_ids={ids}")

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("action", choices=["check", "alert", "test"])
    args = parser.parse_args()
    if args.action == "check":
        check()
        return
    if args.action == "alert":
        if not ALERT.exists():
            raise RuntimeError("Missing new-event alert; refusing to send")
        return deliver(
            ALERT.read_text(encoding="utf-8").strip(),
            OUT / "lg_auto_chiplet_delivery_confirmed.json",
        )
    official = "https://www.motir.go.kr/kor/article/ATCL3f49a5a8c/172250/view"
    test_message = (
        "<b>[연결 시험 · 신규 사건 아님] 차량용 칩렛 전용 알림</b>\n\n"
        "감시: LG전자·보스반도체·하나마이크론 공동 칩렛 개발 / 보쉬 적용 논의\n"
        "확정: 2026년 9월 30일 산업통상부 개발협력 업무협약\n"
        "보쉬 구매계약·양산·매출: 아직 미확정\n"
        "향후 실제 단계 변화만 신규 알림\n"
        f'<a href="{official}">산업통상부 공식자료</a>'
    )
    deliver(test_message, OUT / "lg_auto_chiplet_route_test.json", test=True)

if __name__ == "__main__":
    main()
