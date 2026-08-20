#!/usr/bin/env python3
"""13F Telegram entrypoint with verified Korean sector/display overrides.

PURR classification basis:
- Hyperliquid Strategies Inc. (NASDAQ: PURR) describes itself as a digital asset
  treasury platform focused on the Hyperliquid ecosystem.
- Its primary treasury asset is HYPE, with staking/validator activity.

The SEC issuer name is preserved internally by thirteenf_sector_watch.py; only
Telegram display and sector classification are overridden here.
"""

import os

import thirteenf_sector_watch as watch

PURR_ISSUER = "HYPERLIQUID STRATEGIES"
PURR_DISPLAY = "하이퍼리퀴드 스트래티지스(PURR·HYPE 간접노출)"
PURR_SECTOR = "디지털자산·온체인 금융"

# Put the precise rule first so it wins before broader finance classifications.
watch.SECURITY_DISPLAY_RULES.insert(0, (PURR_ISSUER, PURR_DISPLAY))
watch.SECTOR_RULES.insert(0, (PURR_SECTOR, [PURR_ISSUER]))


def send_purr_test_if_requested() -> bool:
    if os.environ.get("THIRTEENF_PURR_TEST", "false").lower() != "true":
        return False

    token = (
        os.environ.get("THIRTEENF_TELEGRAM_BOT_TOKEN")
        or os.environ.get("KHS_POLICY_TELEGRAM_BOT_TOKEN")
        or ""
    )
    chat_id = (
        os.environ.get("THIRTEENF_TELEGRAM_CHAT_ID")
        or os.environ.get("KHS_POLICY_TELEGRAM_CHAT_ID")
        or ""
    )
    if not token or not chat_id:
        raise RuntimeError("13F Telegram 비밀값이 없습니다.")

    username = watch.verify_bot(token)
    sample = {
        "issuer": "HYPERLIQUID STRATEGIES INC",
        "title": "COM",
        "putcall": "",
        "action": "신규 매수",
        "delta_shares": 2_941_500,
        "cur_value": 23_149_605,
        "prev_value": 0,
    }
    message = "\n".join(
        [
            "✅ [13F PURR 분류 테스트]",
            f"발신 봇: @{username}",
            "산업: 디지털자산·온체인 금융",
            watch.line_for(sample),
            "설명: PURR는 Hyperliquid 생태계의 HYPE 보유·스테이킹·검증자 사업에 간접 노출되는 미국 상장사입니다.",
            "※ 13F 분기말 평가액은 실제 매수대금과 같지 않습니다.",
        ]
    )
    watch.send_message(token, chat_id, message)
    print("PURR Korean classification Telegram test sent successfully.")
    return True


if __name__ == "__main__":
    if not send_purr_test_if_requested():
        watch.main()
