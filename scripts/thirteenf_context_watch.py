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
    return f"{v/1_000_000:,.3f}백만달러(약 {k:,.1f}억원)"

def link(label,url):
    return f'<a href="{html.escape(url,quote=True)}">{html.escape(label)}</a>'

def build(rate,basis):
    return "\n".join([
       "📊 <b>드러켄밀러 13F 후속 분석 — CDW 신규 편입</b>",
       "<b>판정: 10월 8일 신동아 기업 분석 · 새 SEC 13F 공시 아님</b>",
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
