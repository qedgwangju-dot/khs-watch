#!/usr/bin/env python3
"""One-time in-place link formatting repair for the already-sent Oct 16 QRA dealer alert.

Never send a new message and never change the QRA trigger, frequency or bot.
Requires the exact known heading, bot, and confirmed message ID.
"""
from __future__ import annotations

import json
import os
import urllib.parse
import urllib.request
from datetime import datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

from qra_recurring_alert import dealer_telegram_html
from qra_long_end_issuance import CITI_20261009

ROOT=Path(__file__).resolve().parents[1]
STATE=ROOT/"data"/"qra_recurring_alert_state.json"
OUT=ROOT/"out"/"qra_dealer_link_repair_confirmed.json"
EXPECTED_HEADING="DOCUMENTS RELEASED at 12:00 PM Friday, October 16, 2026"
EXPECTED_BOT="hs8879887988798879_bot"
EXPECTED_MESSAGE_ID=297
OFFICIAL="https://home.treasury.gov/system/files/221/Dealer-Agenda-November-2026.pdf"
KST=ZoneInfo("Asia/Seoul")


def build_original_message() -> str:
    title="미 재무부 딜러 자료 | 장기국채 공급 검토 신호"
    body="\n".join([
        "확정 단계: 공식 딜러 설문·의제 공개. 장기채 감축 결정이 아닙니다.",
        "• 공식 공개일: 2026-10-16 · 확인 주제: 20년물·30년물·국채 경매규모",
        "• Citi 미확정 예상: 20년·30년물 각각 회당 30억달러(약 3조9,963억원) 감축 → 3개월 180억달러(약 23조9,778억원) 공급 감축·단기국채 대체 가능. 20년물 발행 중단은 추가 시나리오.",
        "• 정부 질문·설문은 정책 검토의 증거이지 시행 결정이 아닙니다.",
        "• 다음 확인: 11/2 분기 차입추정, 11/4 QRA 확정 발행표·가이던스.",
        "• 역풍: 단기국채 차환 위험·대형 기술기업 회사채 경쟁·인플레이션·기간프리미엄.",
        "공식 문서: "+OFFICIAL,
        "시장 예상: "+CITI_20261009,
    ])
    return dealer_telegram_html(
        title,body,{"type":"dealer_long_end_survey_official_document","official_url":OFFICIAL}
    )


def main():
    OUT.parent.mkdir(parents=True,exist_ok=True)
    OUT.unlink(missing_ok=True)
    state=json.loads(STATE.read_text(encoding="utf-8"))
    if state.get("dealer_links_edited_message_id")==EXPECTED_MESSAGE_ID:
        print("dealer_original_link_repair=already_completed")
        return
    if (state.get("last_heading")!=EXPECTED_HEADING or
        state.get("bot_username")!=EXPECTED_BOT or
        state.get("telegram_message_id")!=EXPECTED_MESSAGE_ID):
        print("dealer_original_link_repair=skip_message_identity_changed")
        return
    sent=datetime.fromisoformat(str(state["last_sent_at_kst"]))
    now=datetime.now(KST)
    if now-sent>timedelta(hours=40):
        print("dealer_original_link_repair=skip_original_too_old")
        return
    token=(os.getenv("TELEGRAM_BOT_TOKEN") or "").strip()
    chat=(os.getenv("TELEGRAM_CHAT_ID") or "").strip()
    if not token or not chat:
        raise RuntimeError("Existing QRA Telegram bot credentials absent")
    with urllib.request.urlopen(
        "https://api.telegram.org/bot"+token+"/getMe",timeout=25
    ) as response:
        identity=json.loads(response.read().decode("utf-8"))
    actual=(identity.get("result") or {}).get("username")
    if not identity.get("ok") or actual!=EXPECTED_BOT:
        raise RuntimeError("QRA Telegram bot identity mismatch")
    message=build_original_message()
    data=urllib.parse.urlencode({
        "chat_id":chat,
        "message_id":EXPECTED_MESSAGE_ID,
        "text":message,
        "parse_mode":"HTML",
        "disable_web_page_preview":"true",
    }).encode("utf-8")
    req=urllib.request.Request(
        "https://api.telegram.org/bot"+token+"/editMessageText",
        data=data,method="POST"
    )
    with urllib.request.urlopen(req,timeout=25) as response:
        result=json.loads(response.read().decode("utf-8"))
    found=(result.get("result") or {})
    if not result.get("ok") or found.get("message_id")!=EXPECTED_MESSAGE_ID:
        raise RuntimeError("Telegram in-place edit not acknowledged")
    state["dealer_links_edited_message_id"]=EXPECTED_MESSAGE_ID
    state["dealer_links_format"]="html_v1"
    state["dealer_links_edited_at_kst"]=now.isoformat(timespec="seconds")
    STATE.write_text(json.dumps(state,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
    OUT.write_text(json.dumps({
        "status":"confirmed","method":"editMessageText",
        "message_id":EXPECTED_MESSAGE_ID,"bot_username":actual,
        "format":"html_v1","edited_at_kst":now.isoformat(timespec="seconds"),
    },ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
    print("qra_dealer_link_repair=confirmed editMessageText message_id=297")

if __name__=="__main__":
    main()
