#!/usr/bin/env python3
"""13F Telegram entrypoint with Korean display, owner, sector, and KRW conversion."""

import datetime as dt
import json
import os
import urllib.request

import thirteenf_sector_watch as watch
import thirteenf_sector_rank as sector_rank

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

# 업종 방향 알림은 SEC 신고 법인명/정확한 제품·사업에 한정해 분류한다.
# 과거 13F 신고는 보존하고, 새 보고서에서만 확대된 분류를 적용한다.
EXTRA_SECTORS = [
    ("메모리·저장장치", ["SEAGATE", "SANDISK", "MICRON TECHNOLOGY", "WESTERN DIGITAL", "PURE STORAGE"]),
    ("AI 데이터센터·전력", ["SHARONAI", "FERMI INC", "BLOOM ENERGY",
                         "COREWEAVE", "NEBIUS", "APPLIED DIGITAL"]),
    ("금·귀금속", ["NEWMONT", "AGNICO EAGLE", "BARRICK", "SKEENA RESOURCES", "GOLD FIELDS"]),
    ("게임·3D 소프트웨어", ["UNITY SOFTWARE", "ROBLOX"]),
    ("기업·응용 소프트웨어", ["PALANTIR", "BENDING SPOONS", "VERISIGN"]),
    ("우주·위성·발사체", ["SPACE EXPLORATION", "SPACEX", "SPCX"]),
    ("암호화폐 채굴·인프라", ["CLEANSPARK", "BITDEER", "RIOT PLATFORMS", "IREN LIMITED"]),
    ("소비재·가구", ["SOMNIGROUP", "MACYS", "MACY'S"]),
]
for sec, phrases in reversed(EXTRA_SECTORS):
    watch.SECTOR_RULES.insert(0, (sec, phrases))

EXTRA_NAMES = [
    ("SEAGATE", "시게이트(STX)"),
    ("UNITY SOFTWARE", "유니티(U)"),
    ("NEWMONT", "뉴몬트(NEM)"),
    ("AGNICO EAGLE", "애그니코이글(AEM)"),
    ("BARRICK", "배릭(B)"),
    ("SHARONAI", "샤론AI(SHAZ)"),
    ("FERMI INC", "페르미(FRMI)"),
    ("COREWEAVE", "코어위브(CRWV)"),
    ("BLOOM ENERGY", "블룸에너지(BE)"),
    ("PALANTIR", "팔란티어(PLTR)"),
    ("SPACE EXPLORATION", "스페이스X"),
    ("BENDING SPOONS", "벤딩스푼스"),
    ("SOMNIGROUP", "솜니그룹(SGI)"),
]
for needle, name in reversed(EXTRA_NAMES):
    watch.SECURITY_DISPLAY_RULES.insert(0, (needle, name))



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
    """Send the industry-direction summary FIRST and omit long per-ticker listings.

    Full underlying 13F parsing and original report builder remain untouched;
    this changes only the manager Telegram presentation, not dedup or routing.
    """
    owner = PORTFOLIO_OWNER_KR.get(label, watch.MANAGER_KR.get(label, label))
    validated = sector_rank.verified_change_values(changes,label,filing,previous)
    rate, basis = ensure_fx()
    lines = [
        f"[13F 업종별 보유 확대·축소] {owner}",
        f"보유 기준 {filing['report_date']} · 공시 {filing['filing_date']} · "
        f"비교 {previous['report_date'] if previous else '직전 분기 미확인'}",
        f"평가액 원화환산: 1달러={rate:,.2f}원 ({basis})",
        "",
        sector_rank.build_sector_direction(
            validated, watch.security_name_kr, top_n=3,
            money=money_with_krw),
        f"SEC 공식 원문: {info_url}",
    ]
    message="\n".join(lines)
    if len(message)>3700:
        raise RuntimeError("13F sector amount report exceeds single Telegram message; no partial delivery")
    return message


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
        # Preserve the original SEC → 13F Telegram route first.
        watch.main()
        # Separate quarter-end ownership from newer editorial analysis.
        import thirteenf_context_watch
        thirteenf_context_watch.main()
        # Distinct cross-manager 2026-Q3 SEC source reconciliation, once only.
        # Preview is always no-send until the existing workflow explicitly enables it.
        thirteenf_context_watch.q3_crosscheck_main()
