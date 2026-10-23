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


def build_status_message(now, reason):
    if reason == "workflow_step_failed":
        details = (
            "• 정기 보고의 조회·검증 실행이 정상 완료되지 않아 전체 수치 보고를 보류했습니다.\n"
            "• 실행 오류가 해소되기 전까지 이전 날짜의 수치로 대체하지 않습니다."
        )
    else:
        details = (
            "• 공식 자료의 기준일 또는 필드 검증을 통과하지 못해 전체 수치 보고를 보류했습니다.\n"
            "• 이전 날짜의 수치로 대체하지 않았습니다."
        )
    return (
        "⚠️ 미 국채·회사채 방향성 정기 보고 보류\n"
        "━━━━━━━━━━━━━━━━\n"
        f"• 확인 시각: {now:%Y-%m-%d %H:%M KST}\n"
        f"{details}\n"
        "• 07:45 KST에 재시도하며, 검증이 통과하면 전체 보고를 발송합니다."
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

    message = build_status_message(now, reason)
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
