#!/usr/bin/env python3
"""13F Telegram entrypoint with Korean display, sector, and owner overrides."""

import os

import thirteenf_sector_watch as watch

PURR_ISSUER = "HYPERLIQUID STRATEGIES"
PURR_DISPLAY = "하이퍼리퀴드 스트래티지스(PURR·HYPE 간접노출)"
PURR_SECTOR = "디지털자산·온체인 금융"

# 종목 식별 및 산업 분류 보정
watch.SECURITY_DISPLAY_RULES.insert(0, (PURR_ISSUER, PURR_DISPLAY))
watch.SECTOR_RULES.insert(0, (PURR_SECTOR, [PURR_ISSUER]))

# 텔레그램에서 '누가 이 포트폴리오를 공시했는지'를 반드시 먼저 표시한다.
PORTFOLIO_OWNER_KR = {
    "Situational Awareness": "레오폴드 아셴브레너의 시추에이셔널 어웨어니스",
    "Duquesne Family Office": "스탠리 드러켄밀러의 듀케인 패밀리 오피스",
    "Pershing Square": "빌 애크먼의 퍼싱스퀘어",
    "Third Point": "대니얼 롭의 서드포인트",
    "NVIDIA": "엔비디아",
    "Appaloosa": "데이비드 테퍼의 아팔루사",
    "Berkshire Hathaway": "버크셔 해서웨이",
}

_original_build_message = watch.build_message


def build_message_with_owner(label, filing, previous, changes, info_url):
    text = _original_build_message(label, filing, previous, changes, info_url)
    lines = text.splitlines()
    owner = PORTFOLIO_OWNER_KR.get(label, watch.MANAGER_KR.get(label, label))
    # 제목 바로 아래에 공시 주체를 고정해서 종목 수량의 주체가 혼동되지 않게 한다.
    lines.insert(1, f"포트폴리오 공시 주체: {owner}")
    return "\n".join(lines)


watch.build_message = build_message_with_owner


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
            "포트폴리오 공시 주체: 스탠리 드러켄밀러의 듀케인 패밀리 오피스",
            f"발신 봇: @{username}",
            "산업: 디지털자산·온체인 금융",
            watch.line_for(sample),
            "수량 설명: 2,941,500주는 PURR 보통주 수량이며 HYPE 토큰 수량이 아닙니다.",
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
