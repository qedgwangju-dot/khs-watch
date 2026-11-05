#!/usr/bin/env python3
"""Verify and send NVIDIA/Korea AI startup milestone alerts via the existing bot."""
from __future__ import annotations
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

def api(method, fields=None):
    token = (os.getenv("TELEGRAM_BOT_TOKEN") or "").strip()
    if not token:
        raise RuntimeError("NVIDIA K-startup bot token missing")
    payload = urllib.parse.urlencode(fields).encode() if fields is not None else None
    req = urllib.request.Request("https://api.telegram.org/bot" + token + "/" + method,
                                 data=payload, method="POST" if payload is not None else "GET")
    with urllib.request.urlopen(req, timeout=25) as res:
        data=json.loads(res.read().decode("utf-8"))
    if not data.get("ok"):
        raise RuntimeError("Telegram " + method + " failed: " + str(data.get("description")))
    return data["result"]

def route():
    chat=(os.getenv("TELEGRAM_CHAT_ID") or "").strip()
    expected=(os.getenv("EXPECTED_TELEGRAM_BOT_USERNAME") or "").strip().lstrip("@").lower()
    if not chat or not expected:
        raise RuntimeError("Telegram target chat or expected bot missing")
    ident=api("getMe")
    actual=str(ident.get("username") or "")
    if actual.lower()!=expected:
        raise RuntimeError(f"Wrong Telegram bot: expected @{expected}; got @{actual}")
    api("getChat", {"chat_id":chat})
    print(f"nvidia_kstartup_bot_verified=@{actual}")
    print("nvidia_kstartup_chat_verified=true")
    return chat

def sections(text, limit=3500):
    pieces, running=[], ""
    for para in text.strip().split("\n\n"):
        candidate=para if not running else running+"\n\n"+para
        if len(candidate)<=limit:
            running=candidate
        else:
            if len(para)>limit:
                raise RuntimeError("An individual HTML message section exceeds Telegram safe length")
            if running:
                pieces.append(running)
            running=para
    if running:
        pieces.append(running)
    return pieces

def send(text, receipt_file, test):
    chat=route()
    ids=[]
    for i, block in enumerate(sections(text), 1):
        if i>1:
            block="<b>엔비디아–한국 AI 스타트업 감시 (계속)</b>\n\n"+block
        result=api("sendMessage",{"chat_id":chat,"text":block,"parse_mode":"HTML",
                                  "disable_web_page_preview":"true"})
        mid=result.get("message_id")
        if not isinstance(mid,int) or mid<=0:
            raise RuntimeError("Telegram delivery missing a valid message_id")
        ids.append(mid)
    receipt={"status":"confirmed","test":test,"message_ids":ids,
             "confirmed_at_kst":dt.datetime.now(ZoneInfo("Asia/Seoul")).isoformat(timespec="seconds")}
    receipt_file.write_text(json.dumps(receipt,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
    print(f"nvidia_kstartup_delivery_confirmed=true test={test} message_ids={ids}")

def main():
    p=argparse.ArgumentParser()
    p.add_argument("mode",choices=("check","alert","test"))
    arg=p.parse_args()
    if arg.mode=="check":
        route()
    elif arg.mode=="alert":
        source=OUT/"nvidia_kstartup_global_alert.html"
        if not source.exists():
            raise RuntimeError("No new event alert exists; refuse to send")
        send(source.read_text(encoding="utf-8"),OUT/"nvidia_kstartup_global_delivery_confirmed.json",False)
    else:
        message=(
            "<b>[연결 시험 · 신규 사건 아님] 엔비디아–한국 AI 스타트업 해외사업 감시</b>\n\n"
            "기준선: 2026-11-05 한국경제 간담회 보도(본문 미열람)\n"
            "별도 기준선: 6월 8일 과거 간담회 · 8월 초기 협력논의 · 11월 9~10일 공식 AI Day\n"
            "간담회·초청은 실제 투자·공급계약·해외매출과 구분합니다.\n"
            "알림 조건: 신규 공식 참석·프로그램 선정·유료 검증·계약·투자·해외 수주\n"
            '<a href="https://www.nvidia.com/ko-kr/ai-days/">엔비디아 공식 행사 안내</a>'
        )
        send(message,OUT/"nvidia_kstartup_global_route_test.json",True)

if __name__=="__main__":
    main()
