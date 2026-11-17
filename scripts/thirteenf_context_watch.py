#!/usr/bin/env python3
"""One-time verified manager commentary, distinct from a new SEC 13F filing."""
import html
import os
import thirteenf_sector_watch as w

KEY="13f-context:duquesne:2026-06-30:CDW:shindonga-2026-10-08"
SEC_ACC="0001536411-26-000006"
SHIN="https://shindonga.donga.com/economy/article/all/13/6410242/1"
SEC="https://www.sec.gov/Archives/edgar/data/1536411/000153641126000006/0001536411-26-000006-index.htm"
IR="https://investor.cdw.com/news/news-details/2026/CDW-Reports-Second-Quarter-2026-Earnings/default.aspx"

def should_send(state):
    m=state.get("managers",{}).get("Duquesne Family Office",{})
    return (KEY not in state.get("seen_context_events",[])
            and m.get("report_date")=="2026-06-30" and m.get("accession")==SEC_ACC)

def amount(v,r):
    k=v*r/100_000_000
    n=int(v)
    eok, rem=divmod(n,100_000_000)
    man, rest=divmod(rem,10_000)
    parts=[]
    if eok:
        parts.append(f"{eok:,}억")
    if man:
        parts.append(f"{man:,}만")
    if rest:
        parts.append(f"{rest:,}")
    return f"{''.join(parts)}달러(약 {k:,.1f}억원)"

def link(label,url):
    return f'<a href="{html.escape(url,quote=True)}">{html.escape(label)}</a>'

def build(rate,basis):
    return "\n".join([
       "📊 <b>드러켄밀러 13F 후속 분석 — CDW 신규 편입</b>",
       "<b>판정: 10월 8일 신동아 기업 분석 · 새 13F 공시 아님</b>",
       "공시 주체: 스탠리 드러켄밀러의 듀케인 패밀리 오피스",
       "SEC 기준: 2026년 6월 30일 보유현황 · 8월 14일 제출",
       "",
       "<b>확인된 분기말 숫자</b>",
       f"• CDW 보통주 신규: <b>743,950주 · {amount(104_629_000,rate)}</b>",
       f"• CDW 별도 콜옵션 신규: 기초주식 환산 <b>250,000주 · {amount(35_160_000,rate)}</b>",
       "• 콜옵션 13F 신고가치는 옵션 매입 비용이나 평균매입단가가 아닙니다.",
       f"• CDW 2분기 매출: {amount(6_572_200_000,rate)} · 전년 동기 +10.0%",
       "• 매출총이익률: 20.1%(전년 20.8%); 영업이익률: 6.5%(전년 7.0%).",
       "",
       "<b>재평가 조건과 역풍</b>",
       "• 기업용 AI 도입이 서버·네트워크·보안·서비스 수주로 연결되는지 추적.",
       "• 하드웨어 매출 증가만으로는 마진 개선이 보장되지 않습니다.",
       "• 13F는 분기말 정보여서 10월 현재 보유를 입증하지 않습니다.",
       f"환율: 1달러={rate:,.2f}원 ({html.escape(str(basis))})",
       "",
       f"{link('신동아 원문',SHIN)} | {link('SEC 13F 원문',SEC)}",
       link("CDW 공식 분기실적",IR),
    ])

def main():
    state=w.load_state()
    if not should_send(state):
        print("13F CDW context: unchanged / filing not yet grounded")
        return False
    from fx_api import daily_krw
    q=daily_krw()
    rate=float(q.rate)
    token=(os.getenv("THIRTEENF_TELEGRAM_BOT_TOKEN") or "").strip()
    chat=(os.getenv("THIRTEENF_TELEGRAM_CHAT_ID") or os.getenv("KHS_POLICY_TELEGRAM_CHAT_ID") or "").strip()
    if not token or not chat:
        raise RuntimeError("13F Telegram secrets missing")
    username=w.verify_bot(token)
    if username.lower()!="khs887988798879_bot":
        raise RuntimeError("Unexpected 13F Telegram sender")
    receipt=w.telegram_api(token,"sendMessage",{
        "chat_id":chat,"text":build(rate,q.basis),"parse_mode":"HTML","disable_web_page_preview":"true"
    })
    message_id=(receipt or {}).get("message_id")
    if message_id is None:
        raise RuntimeError("13F context alert not confirmed")
    state["seen_context_events"]=sorted(set(state.get("seen_context_events",[]))|{KEY})
    w.save_state(state)
    print(f"13F CDW context delivered: message_id={message_id}")
    return True

if __name__=="__main__":
    main()


# A distinct, one-time cross-manager reconciliation of public 2026-Q3 SEC
# holdings. It is NOT a second alert for each already-sent individual 13F.
Q3_REPORT_DATE = "2026-09-30"
Q3_COMPARE_KEY = "verified-13f-crossmanager-2026q3-20261117-v1"
Q3_FOCUS_MANAGERS = (
    "Situational Awareness", "Duquesne Family Office", "Appaloosa",
    "Third Point", "NVIDIA", "Berkshire Hathaway",
)

def q3_ready(state):
    if Q3_COMPARE_KEY in state.get("seen_context_events", []):
        return False
    managers=state.get("managers", {})
    return all(
        (managers.get(label) or {}).get("report_date")==Q3_REPORT_DATE
        and (managers.get(label) or {}).get("accession")
        for label in Q3_FOCUS_MANAGERS
    )

def _reported_shares(positions, term, pc=""):
    """Aggregate equal-issuer classes for this alert; CALL/PUT are distinct."""
    needle=term.upper()
    return int(round(sum(
        float(row.get("shares") or 0)
        for row in positions.values()
        if needle in str(row.get("issuer") or "").upper()
        and str(row.get("putcall") or "").upper()==pc
    )))

def _movement(snapshots, label, term, short, pc=""):
    prev,cur=snapshots[label]["previous"],snapshots[label]["current"]
    old=_reported_shares(prev,term,pc)
    new=_reported_shares(cur,term,pc)
    if old==new:
        return f"{short} 유지 {new:,}주" if new else f"{short} 신고 없음"
    if old==0:
        return f"{short} 신규보고 {new:,}주"
    if new==0:
        return f"{short} 신고상 소멸 {old:,}주"
    pct=100*(new/old-1)
    return f"{short} {pct:+.1f}% ({old:,}→{new:,}주)"

def _q3_snapshots(state):
    """Fetch each manager's SEC current and *prior* 13F XML, not media totals."""
    snapshots={}
    for label in Q3_FOCUS_MANAGERS:
        accepted=state["managers"][label]
        cik=accepted["cik"]
        filings=w.recent_13f(cik)
        latest=next((f for f in filings if f["accession"]==accepted["accession"]
                     and f["report_date"]==Q3_REPORT_DATE
                     and f["form"] in {"13F-HR","13F-HR/A"}),None)
        previous=next((f for f in filings if f["report_date"]=="2026-06-30"
                       and f["form"] in {"13F-HR","13F-HR/A"}),None)
        if not latest or not previous:
            raise RuntimeError("SEC source Q3/Q2 matching failed for "+label)
        current,link=w.parse_holdings(cik,latest["accession"])
        prior,_=w.parse_holdings(cik,previous["accession"])
        if not current or not prior:
            raise RuntimeError("SEC current or prior positions empty for "+label)
        snapshots[label]={"current":current,"previous":prior,
                          "url":link,"accession":latest["accession"]}
        print(f"Q3_COMPARE_SEC_VERIFIED manager={label} current={len(current)} "
              f"previous={len(prior)} accession={latest['accession']}")
    return snapshots

def build_q3_cross_report(snapshots, *, fx_rate=1334.87):
    """Concise source-separated SEC comparison + verified November 16 context.

    The foreign-currency rate is the 2026-11-16 rate from the user's message,
    NOT a live quote or a universal report FX rate. Suppress unverified SEC
    reported values, because different filings may have inconsistent units.
    """
    d="Duquesne Family Office"
    a="Situational Awareness"
    tp="Third Point"
    ap="Appaloosa"
    nv="NVIDIA"
    br="Berkshire Hathaway"
    for manager in Q3_FOCUS_MANAGERS:
        if manager not in snapshots:
            raise ValueError("Missing SEC verified snapshot: "+manager)
    c=lambda manager,term,short,pc="":_movement(snapshots,manager,term,short,pc)
    sndk_call=_reported_shares(snapshots[a]["current"],"SANDISK","CALL")
    nbis_call=_reported_shares(snapshots[a]["current"],"NEBIUS","CALL")
    aws_value=5_000_000_000*fx_rate/1_000_000_000_000
    lines=[
        "[SEC 13F 교차대조 | 2026년 3분기 | 신규 비교 보고]",
        "보유 기준 09-30 · 제출 11-16 · 2분기 대비 신고주수 변화",
        "※ 각 기관의 공시를 직접 비교하며, 13F는 실제 체결내역이 아닙니다.",
        "",
        "■ 메모리·AI 투자 방향은 기관별로 엇갈림",
        "시추에이셔널: "+
        " / ".join([c(a,"MICRON","마이크론"),c(a,"SANDISK","샌디스크"),
                   c(a,"BLOOM ENERGY","블룸에너지")]),
        "아팔루사: "+c(ap,"MICRON","마이크론")+" / "+c(ap,"NVIDIA","엔비디아"),
        "서드포인트: "+c(tp,"NVIDIA","엔비디아"),
        "",
        "■ 시추에이셔널: 보통주 철수와 옵션 보유를 구분",
        c(a,"SHARONAI","샤론AI")+" / "+c(a,"NEBIUS","네비우스"),
        f"샌디스크 콜옵션 기초주식 {sndk_call:,}주, 네비우스 콜옵션 {nbis_call:,}주 (옵션 매입대금 아님)",
        "",
        "■ 듀케인: 메모리·소프트웨어 확대, 일부 파운드리 축소",
        " / ".join([c(d,"SEAGATE","시게이트"),c(d,"UNITY SOFTWARE","유니티"),
                    c(d,"AMAZON","아마존"),c(d,"TAIWAN SEMICONDUCTOR","TSMC")]),
        "",
        "■ 엔비디아 자체 포트폴리오",
        c(nv,"INTEL","인텔")+" / "+c(nv,"SPACE EXPLORATION","스페이스X"),
        "",
        "■ 버크셔: 항공·주택 확대",
        c(br,"DELTA AIR","델타항공")+" / "+c(br,"LENNAR","레나"),
        "비공개 취급 가능 종목은 미신고만으로 매도 확정 금지.",
        "",
        "■ 13F 밖의 11월 16일 독립 발표",
        "블랙록 모델포트폴리오 주식 초과편입 1%→3%(Bloomberg 보도·실제 거래 아님).",
        f"블랙스톤 BXDC·AWS: 데이터센터 총자산가치 50억달러(약 {aws_value:.2f}조원),"
        " BXDC 합작법인 지분 75.1%, AWS 24.9%, 13개 건물·647MW, 계약 체결/완료 전.",
        "로이터: 데이터센터 신규편입 119곳·청산 138곳, 전력주 신규 96곳·청산 212곳.",
        "",
        "※ SEC는 2023년부터 13F 평가액을 달러 단위로 신고하도록 규정."
        " 듀케인 원문 신고액과 시장 평가액 사이 1,000배 차이가 있어 금액 순위는 보류.",
        "※ 나테라(NTRA) 비중 약 29%와 약 31.5%는 포함 자산의 분모가 서로 다릅니다.",
        "출처(SEC): "+snapshots[d]["url"],
        "SEC 시추에이셔널: "+snapshots[a]["url"],
        "SEC 엔비디아: "+snapshots[nv]["url"],
        "공식 BXDC: https://www.blackstone.com/news/press/blackstone-digital-infrastructure-trust-announces-5-billion-acquisition-of-stabilized-data-center-portfolio/",
        "BlackRock 보도: https://uk.finance.yahoo.com/news/blackrock-shifts-ai-bets-adds-135559245.html",
        "Reuters: https://www.reuters.com/legal/transactional/investors-cooled-data-center-stocks-third-quarter-filings-show-2026-11-16/",
    ]
    message="\n".join(lines)
    if len(message)>3750:
        # The alert must be a single atomic Telegram message to limit partial
        # delivery and ambiguous multi-chunk duplicate risk.
        raise RuntimeError(f"Q3 comparison exceeds single-message budget: {len(message)}")
    return message

def q3_crosscheck_main():
    state=w.load_state()
    if not q3_ready(state):
        print("Q3_CROSSCHECK_NO_ACTION already_delivered_or_incomplete_baseline")
        return False
    snapshots=_q3_snapshots(state)
    body=build_q3_cross_report(snapshots)
    if (os.getenv("THIRTEENF_Q3_COMPARE_PROBE_ONLY","true").lower()=="true"
            or os.getenv("THIRTEENF_Q3_COMPARE_ENABLED","false").lower()!="true"):
        print("Q3_CROSSCHECK_VERIFIED_PROBE no_Telegram_send "
              f"managers={len(snapshots)} chars={len(body)}")
        print("Q3_CROSSCHECK_PREVIEW_BEGIN\n"+body+"\nQ3_CROSSCHECK_PREVIEW_END")
        return False
    token=(os.getenv("THIRTEENF_TELEGRAM_BOT_TOKEN") or "").strip()
    chat=(os.getenv("THIRTEENF_TELEGRAM_CHAT_ID") or
          os.getenv("KHS_POLICY_TELEGRAM_CHAT_ID") or "").strip()
    if not token or not chat:
        raise RuntimeError("Q3 compare Telegram route not configured")
    bot=w.verify_bot(token)
    if bot.lower()!="khs887988798879_bot":
        raise RuntimeError("Unexpected Q3 compare Telegram bot")
    # One attempt only. Ambiguous timeout must be reconciled manually.
    receipt=w.telegram_api(token,"sendMessage",{
        "chat_id":chat,"text":body,"disable_web_page_preview":"true",
    })
    mid=(receipt or {}).get("message_id")
    confirmed_chat=str((receipt.get("chat") or {}).get("id") or "")
    if mid is None or not confirmed_chat or (chat.lstrip("-").isdigit() and confirmed_chat!=chat):
        raise RuntimeError("Q3 compare response did not verify chat.id and message_id")
    state["seen_context_events"]=sorted(set(state.get("seen_context_events",[]))|{Q3_COMPARE_KEY})
    state.setdefault("context_receipts",{})[Q3_COMPARE_KEY]={
        "message_id":mid,"bot":bot,
        "accessions":{k:v["accession"] for k,v in snapshots.items()},
        "sent_utc":__import__("datetime").datetime.now(__import__("datetime").timezone.utc).isoformat(),
    }
    w.save_state(state)
    print(f"Q3_CROSSCHECK_TELEGRAM_CONFIRMED chat_match=true message_id={mid}")
    return True
