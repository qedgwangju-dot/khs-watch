#!/usr/bin/env python3
"""13F Telegram entrypoint with verified Korean sector/display overrides.

PURR classification basis:
- Hyperliquid Strategies Inc. (NASDAQ: PURR) is a U.S.-listed digital-asset
  treasury company focused on the Hyperliquid ecosystem.
- Its treasury exposure is primarily HYPE; PURR shares are equity shares, not
  HYPE tokens.

The SEC issuer name is preserved internally by thirteenf_sector_watch.py; only
Telegram display, sector classification, and explanatory Korean text are
overridden here.
"""

import os

import thirteenf_sector_watch as watch

PURR_ISSUER = "HYPERLIQUID STRATEGIES"
PURR_DISPLAY = "하이퍼리퀴드 스트래티지스(PURR·HYPE 간접노출)"
PURR_SECTOR = "디지털자산·온체인 금융"

OWNER_KR = {
    "Situational Awareness": "레오폴드 아셴브레너의 시추에이셔널 어웨어니스",
    "Duquesne Family Office": "스탠리 드러켄밀러의 듀케인 패밀리 오피스",
    "Pershing Square": "빌 애크먼의 퍼싱스퀘어",
    "Third Point": "대니얼 롭의 서드포인트",
    "NVIDIA": "엔비디아",
    "Appaloosa": "데이비드 테퍼의 아팔루사",
    "Berkshire Hathaway": "버크셔 해서웨이",
}

# Put the precise rule first so it wins before broader finance classifications.
watch.SECURITY_DISPLAY_RULES.insert(0, (PURR_ISSUER, PURR_DISPLAY))
watch.SECTOR_RULES.insert(0, (PURR_SECTOR, [PURR_ISSUER]))


def _is_purr(change):
    return PURR_ISSUER in (change.get("issuer", "").upper())


def _shares_plain(v):
    return f"{abs(int(round(v))):,}주"


# Make every Telegram alert explicit about WHO owns the disclosed portfolio.
_original_build_message = watch.build_message


def build_message_with_owner(label, filing, previous, changes, info_url):
    text = _original_build_message(label, filing, previous, changes, info_url)
    lines = text.splitlines()
    owner = OWNER_KR.get(label, watch.MANAGER_KR.get(label, label))
    if lines:
        lines.insert(1, f"포트폴리오 공시 주체: {owner}")

    purr_changes = [x for x in changes if _is_purr(x)]
    if purr_changes:
        lines += ["", "▶ PURR 수량을 헷갈리지 않게 보기"]
        for x in purr_changes:
            if x.get("action") == "신규 매수":
                lines.append(
                    f"• {owner}가 이번 분기에 하이퍼리퀴드 스트래티지스(PURR) "
                    f"보통주 {_shares_plain(x.get('delta_shares', 0))}를 새로 포트폴리오에 편입했습니다."
                )
            elif x.get("action") == "보유 확대":
                lines.append(
                    f"• {owner}가 PURR 보통주를 {_shares_plain(x.get('delta_shares', 0))} 추가했습니다."
                )
            elif x.get("action") == "보유 축소":
                lines.append(
                    f"• {owner}가 PURR 보통주를 {_shares_plain(x.get('delta_shares', 0))} 줄였습니다."
                )
            elif x.get("action") == "전량 청산":
                lines.append(
                    f"• {owner}가 기존 PURR 보통주 {_shares_plain(x.get('delta_shares', 0))}를 전량 청산했습니다."
                )
        lines.append("• 여기서 '주'는 PURR 상장회사 보통주 수량입니다. HYPE 토큰 개수가 아닙니다.")
        lines.append("• 분기말 평가액은 6월 30일 보유주식의 시장가치이며 실제 매수대금·평균매입단가와 같지 않습니다.")

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
    message = "\n".join(
        [
            "📊 [13F 정정 예시] 듀케인 패밀리 오피스",
            "포트폴리오 공시 주체: 스탠리 드러켄밀러의 듀케인 패밀리 오피스",
            "기준일: 2026-06-30",
            "",
            "▶ 신규 편입",
            "• 하이퍼리퀴드 스트래티지스(PURR·HYPE 간접노출)",
            "• 신규 보유: 2,941,500주(294.15만주)",
            "• 분기말 평가액: 23,149,605달러",
            "",
            "▶ 정확한 의미",
            "• 2,941,500주는 드러켄밀러의 듀케인 패밀리 오피스가 보유한 PURR 보통주 수량입니다.",
            "• HYPE 토큰 294.15만개를 샀다는 뜻이 아닙니다.",
            "• 13F 평가액은 6월 30일 시장가치이며 실제 매수대금·평균매입단가와 같지 않습니다.",
            f"발신 봇: @{username}",
        ]
    )
    watch.send_message(token, chat_id, message)
    print("PURR ownership clarification Telegram test sent successfully.")
    return True


if __name__ == "__main__":
    if not send_purr_test_if_requested():
        watch.main()
