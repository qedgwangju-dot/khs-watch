#!/usr/bin/env python3
"""13F Telegram entrypoint with Korean display, owner, sector, and KRW conversion."""

import datetime as dt
import json
import os
import re
from html import escape, unescape
from urllib.parse import urlsplit
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
    ("디지털 광고·AI 앱 플랫폼", ["APPLOVIN"]),
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
    ("APPLOVIN", "앱러빈(APP)"),
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
    # Presentation only. Do not round before computing holdings/FX conversion.
    return sector_rank.compact_usd(v)


def _krw_text(won):
    return sector_rank.compact_krw(won)


def money_with_krw(v):
    rate, _ = ensure_fx()
    return f"{_usd_text(v)} ({_krw_text(v * rate)})"


watch.money = money_with_krw

_original_build_message = watch.build_message


def build_amendment_with_owner(owner, filing, previous, changes, info_url, current_holdings):
    meta=filing.get("amendment") or {}
    kind=meta.get("type")
    if kind not in ("RESTATEMENT","NEW HOLDINGS","NEW HOLDINGS ENTRIES"):
        raise RuntimeError("정정공시 표지 검증 없이 발송할 수 없습니다.")
    title="기존 보고서 정정" if kind=="RESTATEMENT" else "보유증권 추가 신고"
    lines=[
        f"[13F 정정공시] {owner}",
        f"보유 기준 {filing['report_date']} · 제출 {filing['filing_date']}",
        f"공시 유형: 13F-HR/A · {title}",
        "■ 정정 내용",
    ]
    reason=" ".join(str(meta.get("reason") or "").split())
    # A filing cover is authoritative. Preserve the source wording, and only
    # translate this precise known English construction when it is present.
    if reason:
        match=re.fullmatch(r"(.+?) is restating its 13F due to the erroneous inclusion of holdings in CUSIPs? ([A-Za-z0-9 ,and]+)\. There are no other changes to the positions reported\.",reason,re.I)
        if match:
            ids=re.findall(r"\b[A-Z0-9]{9}\b",match.group(2),re.I)
            if ids:
                lines.append("• 잘못 포함한 증권 식별번호(CUSIP) 정정: "+", ".join(ids))
                lines.append("• 공시 표지상 그 외 신고 포지션 변경 없음")
            else:
                lines.append("• 회사 공시 정정 사유(원문): "+reason)
        else:
            lines.append("• 회사 공시 정정 사유(원문): "+reason)
    else:
        lines.append("• 공시 표지의 별도 정정 사유 미기재")
    if previous and kind=="RESTATEMENT":
        lines.append(f"비교 기준: 동일 분기 직전 제출본 ({previous['filing_date']})")
        lines.append(f"■ 보유수량 정정 {len(changes):,}행")
        if changes:
            labels={"신규 매수":"신고 추가","전량 청산":"신고 삭제","보유 확대":"수량 상향 정정","보유 축소":"수량 하향 정정"}
            ranked=sorted(changes,key=lambda row:max(float(row.get("cur_value") or 0),float(row.get("prev_value") or 0)),reverse=True)
            for row in ranked[:12]:
                n=abs(int(round(row.get("delta_shares") or 0)))
                name=watch.security_name_kr(row)+watch.option_name_kr(row.get("putcall"))
                lines.append(f"• {name} · {labels.get(row.get('action'),'정정')} {n:,}주"
                             f" · CUSIP {row.get('cusip','미확인')}")
            if len(ranked)>12:
                lines.append(f"• 나머지 {len(ranked)-12:,}행: SEC 정보표에서 확인")
        else:
            lines.append("• 수량 변경으로 분류된 행 없음")
    elif kind=="RESTATEMENT":
        lines.append("• 동일 분기 이전 완전 신고본 미확인: 증권별 변경 판정 보류")
    else:
        lines.append(f"• 이번 추가 신고 정보표 {len(current_holdings or {}):,}개 증권 항목")
        lines.append("• 추가 신고는 신규 매수나 기존 증권의 보유 종료를 뜻하지 않음")
    lines.extend([
        "※ 정정공시는 과거 보유현황 수정이며 이번 제출일의 거래가 아닙니다.",
        "SEC 정정공시 표지: "+meta["url"],
        "SEC 공식 원문: "+info_url,
    ])
    message="\n".join(lines)
    if len(message)>3700:
        raise RuntimeError("13F 정정공시 메시지 길이 초과; 내용 절단 없이 확인 필요")
    return message


def format_13f_telegram_html(message):
    """Change presentation only: retain all selected rows, escape HTML, hide URLs."""
    rendered=[]
    for line in message.splitlines():
        if line.startswith(("SEC 공식 원문: ","SEC 정정공시 표지: ")):
            label,url=line.split(": ",1)
            parsed=urlsplit(url)
            if parsed.scheme!="https" or parsed.hostname not in ("www.sec.gov","sec.gov","data.sec.gov") or parsed.username or parsed.password:
                raise RuntimeError("13F 출처는 SEC 공식 HTTPS 주소만 허용")
            if not rendered or rendered[-1]!="":
                rendered.append("")
            rendered.append(f'<a href="{escape(url,quote=True)}">{escape(label)}</a>')
            continue
        escaped=escape(line,quote=False)
        if line.startswith(("[13F 핵심 변화 자동 추출]","[13F 정정공시]")):
            rendered.append("<b>"+escaped+"</b>")
        elif line.startswith(("■","▶")):
            if rendered and rendered[-1]!="":
                rendered.append("")
            rendered.append("<b>"+escaped+"</b>")
        elif line.startswith("※"):
            if rendered and not rendered[-1].startswith("※") and rendered[-1]!="":
                rendered.append("")
            rendered.append(escaped)
        else:
            # Bold just the issuer, not all numbers or notes. Do not change
            # the selected security rows, quantities, currencies, or signs.
            m=re.match(r"^(• )(.+?)( (?=(?:신규 |신고상 종료 |[+-]\d))| · (?=(?:신고 추가|신고 삭제|수량 상향 정정|수량 하향 정정)))",line)
            if m:
                prefix,issuer,sep=m.groups()
                rendered.append(escape(prefix,quote=False)+"<b>"+escape(issuer,quote=False)+"</b>"+
                                escape(sep+line[m.end():],quote=False))
            else:
                rendered.append(escaped)
    result="\n".join(rendered)
    # Telegram counts text after HTML entity parsing; UTF-16 is conservative
    # for emoji/non-BMP codepoints. Never split in the middle of an HTML tag.
    visible=unescape(re.sub(r"<[^>]+>","",result))
    if len(visible.encode("utf-16-le"))//2>4096:
        raise RuntimeError("13F Telegram 본문 표시 한도 초과; 일부 내용 누락 방지")
    return result


_original_send_message = watch.send_message

def send_13f_message(token,chat_id,message):
    # Keep unrelated context notices and established test routes unchanged.
    if not message.startswith(("[13F 핵심 변화 자동 추출]","[13F 정정공시]")):
        return _original_send_message(token,chat_id,message)
    html=format_13f_telegram_html(message)
    configured=str(chat_id).strip()
    if configured.lstrip("-").isdigit():
        expected=int(configured)
    else:
        chat=watch.telegram_api(token,"getChat",{"chat_id":configured})
        expected=chat.get("id")
        if type(expected) is not int:
            raise RuntimeError("13F Telegram 수신처 확인 실패")
    receipt=watch.telegram_api(token,"sendMessage",{
        "chat_id":chat_id,"text":html,"parse_mode":"HTML",
        "link_preview_options":json.dumps({"is_disabled":True}),
    })
    mid=receipt.get("message_id")
    if type(mid) is not int or mid<=0 or (receipt.get("chat") or {}).get("id")!=expected:
        raise RuntimeError("13F Telegram 전송 응답 미확인; 성공 처리 금지")
    print(f"13F_HTML_DELIVERY_CONFIRMED message_id={mid} recipient_verified=true")
    return receipt



def build_message_with_owner(label, filing, previous, changes, info_url,
                             current_holdings=None, previous_holdings=None):
    """Automatic SEC 13F position intelligence, not a hand-entered news alert.

    Every changed security is inspected BEFORE sectors or specific names are
    ranked. The public information table supplies holdings and valuations;
    media headlines are neither prerequisites nor substituted for SEC rows.
    """
    owner=PORTFOLIO_OWNER_KR.get(label,watch.MANAGER_KR.get(label,label))
    if filing.get("form")=="13F-HR/A":
        return build_amendment_with_owner(owner,filing,previous,changes,info_url,current_holdings)
    validated=sector_rank.verified_change_values(changes,label,filing,previous)
    rate,basis=ensure_fx()
    if current_holdings is not None:
        # Quarterly public filing: source-based, works for every watched manager.
        summary=sector_rank.build_automatic_13f_digest(
            validated,current_holdings,watch.security_name_kr,money_with_krw,
            report_scale=sector_rank.verified_scale(label,filing),max_chars=2950)
    else:
        # Preserve direct legacy callsites that only pass an existing diff.
        summary=sector_rank.build_sector_direction(
            validated,watch.security_name_kr,top_n=3,money=money_with_krw)
    lines=[
        f"[13F 핵심 변화 자동 추출] {owner}",
        f"보유 기준 {filing['report_date']} · 제출 {filing['filing_date']} · "
        f"직전 {previous['report_date'] if previous else '비교 불가'}",
        f"환율 1달러={rate:,.2f}원 ({basis})",
        "",
        summary,
        f"SEC 공식 원문: {info_url}",
    ]
    message="\n".join(lines)
    if len(message)>3700:
        raise RuntimeError("13F automatic message too long; refuse partial/duplicate sending")
    return message


watch.build_message = build_message_with_owner
watch.send_message = send_13f_message


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
        # Separate once-only verified 13F valuation addendum, no previous alerts replayed.
        thirteenf_context_watch.q3_amount_followup_main()
        # WallstreetCN article is verified against Q2+Q3 SEC XML.
        # By default this is read-only and produces no Telegram message.
        thirteenf_context_watch.duq_article_followup_main()
