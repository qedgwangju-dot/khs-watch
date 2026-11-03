#!/usr/bin/env python3
"""Send one truthful status notice when the scheduled Treasury daily report is withheld."""
import datetime as dt
import os
from zoneinfo import ZoneInfo

import treasury_credit_flow_watch_ishares as watch
import treasury_etf_flow_watch as base
from treasury_credit_flow_delivery import (
    daily_delivery_complete,
    should_send_daily_status,
)

KST = ZoneInfo("Asia/Seoul")


def build_status_message(now, reason, state=None):
    if reason == "workflow_step_failed":
        details = (
            "• 정기 보고의 조회·검증 실행이 정상 완료되지 않아 전체 수치 보고를 보류했습니다.\n"
            "• 실행 오류가 해소되기 전까지 이전 날짜의 수치로 대체하지 않습니다."
        )
    elif reason == "unchanged":
        details = (
            "• 오늘 정기 확인에서 새 수치·판정 변화가 없어 수치 본문을 다시 보내지 않았습니다.\n"
            "• 이는 시장에 변화가 없다는 보증이 아니라, 이번 조회의 중복·변경 없음 상태입니다."
        )
    elif reason == "recheck_skipped":
        details = (
            "• 이번 예약 실행은 자료 재조회를 생략했습니다. 오늘 자료의 최신성은 이 실행만으로 확인되지 않습니다.\n"
            "• 이전 날짜의 수치를 오늘 값으로 표시하지 않았습니다."
        )
    else:
        details = (
            "• 공식 자료의 기준일 또는 필드 검증을 통과하지 못해 전체 수치 보고를 보류했습니다.\n"
            "• 이전 날짜의 수치로 대체하지 않았습니다."
        )
    last = (state or {}).get("last_delivery") or {}
    last_dates = []
    if last.get("treasury_date"):
        last_dates.append(f"미 국채 ETF {last['treasury_date']}")
    if last.get("credit_oas_date"):
        last_dates.append(f"회사채 OAS {last['credit_oas_date']}")
    last_date_line = (
        "• 마지막 확인된 수치 보고의 기준일(오늘 조회값 아님): " + " / ".join(last_dates) + "\n"
        if last_dates else "• 마지막 발송 기준일: 확인 불가\n"
    )
    retry_line = (
        "• 자료 검증이 통과하면 전체 보고를 발송합니다.\n"
        if reason not in ("recheck_skipped", "unchanged") else ""
    )
    title = (
        "🇺🇸 미 국채·회사채 방향성 오전 상태"
        if reason in ("unchanged", "recheck_skipped")
        else "⚠️ 미 국채·회사채 방향성 정기 보고 보류"
    )
    return (
        f"{title}\n"
        "━━━━━━━━━━━━━━━━\n"
        f"• 확인 시각: {now:%Y-%m-%d %H:%M KST}\n"
        f"{details}\n"
        f"{last_date_line}"
        f"{retry_line}"
        "• 정기 확인은 07:30·07:45 KST 예약으로 시도합니다.\n"
        "• 예약 실행은 지연·누락될 수 있어 08:00 전 도착을 보장하지 않습니다."
    )


def main():
    now = dt.datetime.now(KST).replace(microsecond=0)
    delivery_date = now.date().isoformat()
    reason = os.getenv("TREASURY_STATUS_REASON", "official_source_date_or_field_validation_withheld")
    state = base.load_state()

    if daily_delivery_complete(state, delivery_date):
        print(f"daily_status_notification_suppressed=true date_kst={delivery_date} reason=daily_report_already_sent")
        return
    if not should_send_daily_status(state, delivery_date):
        print(f"daily_status_notification_suppressed=true date_kst={delivery_date} reason=status_already_sent")
        return

    message = build_status_message(now, reason, state)
    username, message_ids = watch.send_exact(message)
    state["daily_status_notification"] = {
        "date_kst": delivery_date,
        "at_kst": now.isoformat(timespec="seconds"),
        "bot_username": username,
        "message_ids": message_ids,
        "reason": reason,
    }
    base.save_state(state)
    print(
        "daily_status_notification_sent=true "
        f"date_kst={delivery_date} bot=@{username} message_ids={message_ids}"
    )


if __name__ == "__main__":
    main()
