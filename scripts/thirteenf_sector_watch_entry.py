#!/usr/bin/env python3
"""13F Telegram entrypoint with Korean display, owner, sector, and KRW conversion."""

import datetime as dt
import json
import os
import urllib.request

import thirteenf_sector_watch as watch

# SEC 13F 감시 대상 확장.
# 금융기관은 특정 CEO의 개인 베팅으로 오해하지 않도록 법인 공시 주체명으로 표시한다.
watch.MANAGERS.update({
    "Tudor Investment": ["0000923093"],
    "Morgan Stanley": ["0000895421"],
    "JPMorgan Chase": ["0000019617"],
    "UBS Group": ["0001610520"],
    # BlackRock은 2026년 현재 새 CIK 0002012383으로 13F를 제출한다.
    # 과거 이력 연속성을 위해 이전 CIK 0001364742도 함께 조회한다.
    "BlackRock": ["0002012383", "0001364742"],
    "Brevan Howard": ["0001512857"],
})
watch.MANAGER_KR.update({
    "Tudor Investment": "튜더 인베스트먼트",
    "Morgan Stanley": "모건스탠리",
    "JPMorgan Chase": "JP모건체이스",
    "UBS Group": "UBS 그룹",
    "BlackRock": "블랙록",
    "Brevan Howard": "브레반 하워드 캐피털 매니지먼트",
})

# 디지털자산 관련 13F 종목은 일반 금융/기타가 아니라 별도 산업축으로 분리한다.
CRYPTO_DISPLAY_RULES = [
    ("HYPERLIQUID STRATEGIES", "하이퍼리퀴드 스트래티지스(PURR·HYPE 간접노출)"),
    ("ISHARES BITCOIN", "아이셰어즈 비트코인 트러스트(IBIT)"),
    ("GRAYSCALE BITCOIN", "그레이스케일 비트코인 트러스트(GBTC)"),
    ("FIDELITY WISE ORIGIN BITCOIN", "피델리티 와이즈 오리진 비트코인 펀드(FBTC)"),
    ("ARK 21SHARES BITCOIN", "ARK 21셰어즈 비트코인 ETF(ARKB)"),
    ("STRATEGY INC", "스트래티지(MSTR·비트코인 재무전략)"),
    ("CIRCLE INTERNET", "서클 인터넷 그룹(CRCL·USDC)"),
    ("COINBASE GLOBAL", "코인베이스(COIN)"),
    ("ISHARES ETHEREUM", "아이셰어즈 이더리움 트러스트(ETHA)"),
    ("GRAYSCALE ETHEREUM", "그레이스케일 이더리움 트러스트"),
    ("SOLANA", "솔라나 관련 상장상품"),
]
for rule in reversed(CRYPTO_DISPLAY_RULES):
    watch.SECURITY_DISPLAY_RULES.insert(0, rule)

CRYPTO_ISSUER_NEEDLES = [
    "HYPERLIQUID STRATEGIES",
    "ISHARES BITCOIN",
    "GRAYSCALE BITCOIN",
    "FIDELITY WISE ORIGIN BITCOIN",
    "ARK 21SHARES BITCOIN",
    "STRATEGY INC",
    "CIRCLE INTERNET",
    "COINBASE GLOBAL",
    "ISHARES ETHEREUM",
    "GRAYSCALE ETHEREUM",
    "SOLANA",
]
watch.SECTOR_RULES.insert(0, ("디지털자산·온체인 금융", CRYPTO_ISSUER_NEEDLES))

# 텔레그램에서 '누가 이 포트폴리오를 공시했는지'를 반드시 먼저 표시한다.
PORTFOLIO_OWNER_KR = {
    "Situational Awareness": "레오폴드 아셴브레너의 시추에이셔널 어웨어니스",
    "Duquesne Family Office": "스탠리 드러켄밀러의 듀케인 패밀리 오피스",
    "Pershing Square": "빌 애크먼의 퍼싱스퀘어",
    "Third Point": "대니얼 롭의 서드포인트",
    "NVIDIA": "엔비디아",
    "Appaloosa": "데이비드 테퍼의 아팔루사",
    "Berkshire Hathaway": "버크셔 해서웨이",
    "Tudor Investment": "폴 튜더 존스의 튜더 인베스트먼트",
    "Morgan Stanley": "모건스탠리",
    "JPMorgan Chase": "JP모건체이스",
    "UBS Group": "UBS 그룹",
    "BlackRock": "블랙록",
    "Brevan Howard": "브레반 하워드 캐피털 매니지먼트",
}

# 모든 외화 평가액은 한국 원화로 반드시 병기한다.
# 1순위: 공개 USD/KRW 환율 조회, 2순위: 연준 H.10(FRED DEXKOUS),
# 최종 실패 시 환경변수/내장 대체환율을 사용하고 대체 사용 사실을 표시한다.
FX_RATE = None
FX_BASIS = None


def _fetch_usdkrw():
    from fx_api import daily_krw
    q = daily_krw()
    return q.rate, q.basis


def ensure_fx():
    global FX_RATE, FX_BASIS
    if FX_RATE is None:
        FX_RATE, FX_BASIS = _fetch_usdkrw()
    return FX_RATE, FX_BASIS


def _usd_text(v):
    a = abs(v)
    if a >= 1_000_000_000:
        return f"{v/1_000_000_000:.2f}십억달러"
    if a >= 100_000_000:
        return f"{v/100_000_000:.2f}억달러"
    if a >= 1_000_000:
        return f"{v/1_000_000:.1f}백만달러"
    if a >= 1_000:
        return f"{v/1_000:.1f}천달러"
    return f"{v:,.0f}달러"


def _krw_text(won):
    a = abs(won)
    if a >= 1_000_000_000_000:
        return f"약 {won/1_000_000_000_000:,.2f}조원"
    if a >= 100_000_000:
        return f"약 {won/100_000_000:,.1f}억원"
    if a >= 10_000:
        return f"약 {won/10_000:,.0f}만원"
    return f"약 {won:,.0f}원"


def money_with_krw(v):
    rate, _ = ensure_fx()
    return f"{_usd_text(v)} ({_krw_text(v * rate)})"


watch.money = money_with_krw

_original_build_message = watch.build_message


def build_message_with_owner(label, filing, previous, changes, info_url):
    text = _original_build_message(label, filing, previous, changes, info_url)
    lines = text.splitlines()
    owner = PORTFOLIO_OWNER_KR.get(label, watch.MANAGER_KR.get(label, label))
    rate, basis = ensure_fx()
    lines.insert(1, f"포트폴리오 공시 주체: {owner}")
    lines.insert(2, f"원화 환산 기준: 1달러={rate:,.2f}원 ({basis})")
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
    rate, basis = ensure_fx()
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
            f"원화 환산 기준: 1달러={rate:,.2f}원 ({basis})",
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
