#!/usr/bin/env python3
"""Meta official Q3 2026 baseline and subsequent SEC/Meta AI cash-flow events.
Never relabel a one-time legal charge as recurring operating deterioration or
a Class C stock dividend as cash financed issuance.
"""
import datetime as dt
import html
import json
import os
import pathlib
import re
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from email.utils import parsedate_to_datetime

IR_Q3="https://investor.atmeta.com/investor-news/press-release-details/2026/Meta-Reports-Third-Quarter-2026-Results/default.aspx"
PR_Q3="https://www.prnewswire.com/news-releases/meta-reports-third-quarter-2026-results-302915964.html"
REUTERS_EXPECTATIONS="https://www.investing.com/news/stock-market-news/metas-ai-spending-muse-assistant-adoption-in-focus-for-quarterly-results-4959432"
SEC_SUBMISSIONS="https://data.sec.gov/submissions/CIK0001326801.json"
META_FEED="https://about.fb.com/feed/"
NEWSROOM="https://about.fb.com/news/"
MUSE="https://about.fb.com/news/2026/09/introducing-muse-personal-ai-agent/"
MUSE_WONDER="https://about.fb.com/news/2026/10/introducing-muse-wonder-models/"
STATE=pathlib.Path("data/meta_earnings_muse_cashflow_watch_state.json")
OUT=pathlib.Path("out")
Q3_KEY="meta-q3-2026-official-2026-10-21"
Q3_MILLIONS={
 "revenue":64601,"prior_revenue":51242,
 "op_income":12988,"prior_op_income":20535,
 "legal_charge":9890,"net_income":9860,
 "cash_from_ops":32786,"ppe":33942,"finance_lease":964,
 "free_cash_flow":-2120,
 "forecast_fcf":-8520,"forecast_capex_q3":41680,
 "foa_revenue":64158,"foa_op":17117,
 "rl_revenue":443,"rl_op":-4129,
 "capex_q3":34906,
 "q4_low":73000,"q4_high":76000,
 "fy_capex_low":135000,"fy_capex_high":145000,
 "fy_capex_prev_low":130000,"fy_capex_prev_high":145000,
}

def _get(url,timeout=25):
    req=urllib.request.Request(url, headers={
      "User-Agent":os.environ.get("SEC_USER_AGENT") or "KHS-Meta-Earnings-Watch contact=github-actions",
      "Accept":"text/html,application/rss+xml,application/json,*/*",
    })
    with urllib.request.urlopen(req,timeout=timeout) as r:
        return r.read()

def _verified_q3_source():
    failures=[]
    for url,source in [(IR_Q3,"메타 공식 투자자관계"),(PR_Q3,"메타 보도자료 공식 배포본")]:
        try:
            raw=_get(url)
            text=html.unescape(raw.decode("utf-8","replace"))
            flat=re.sub(r"\s+"," ",re.sub(r"<[^>]+>"," ",text))
            required=["Meta Reports Third Quarter 2026 Results","64,601","12,988","9.89","2,120"]
            if all(k.lower() in flat.lower() for k in required):
                return url,source
            failures.append(url+": source content key mismatch")
        except Exception as e:
            failures.append(url+": "+str(e)[:150])
    raise RuntimeError("No verified Meta Q3 release from official/official-distributed source: "+"; ".join(failures))

def _fx():
    from fx_api import daily_krw
    q=daily_krw()
    return float(q.rate),q.basis

def money(millions,rate):
    usd=abs(millions)*1_000_000
    value=millions*1_000_000*rate
    eok,rem=divmod(int(usd),100_000_000)
    man,rest=divmod(rem,10_000)
    parts=[]
    if eok:
        parts.append(f"{eok:,}억")
    if man:
        parts.append(f"{man:,}만")
    if rest:
        parts.append(f"{rest:,}")
    shown="".join(parts)+"달러"
    if value<0:
        shown="-"+shown
    won=abs(value)
    if won>=1_000_000_000_000:
        kr=f"{won/1_000_000_000_000:,.2f}조원"
    elif won>=100_000_000:
        kr=f"{won/100_000_000:,.1f}억원"
    else:
        kr=f"{won/10_000:,.0f}만원"
    if value<0:kr="-"+kr
    return f"{shown}(약 {kr})"

def _link(label,url):
    return f'<a href="{html.escape(url,quote=True)}">{html.escape(label)}</a>'

def build_q3(rate,basis,source_label):
    a=lambda key:money(Q3_MILLIONS[key],rate)
    clean_op=Q3_MILLIONS["op_income"]+Q3_MILLIONS["legal_charge"]
    adj_margin=clean_op/Q3_MILLIONS["revenue"]*100
    fcf_check=Q3_MILLIONS["cash_from_ops"]-Q3_MILLIONS["ppe"]-Q3_MILLIONS["finance_lease"]
    assert fcf_check==Q3_MILLIONS["free_cash_flow"]
    lines=[
      "📊 <b>메타(META) 2026년 3분기 실적·Muse·AI 설비투자</b>",
      "<b>판정: 10월 21일 공식 실적 신규 발표 · 분기 실적과 일회성 비용 분리</b>",
      f"원천 검증: {html.escape(source_label)}",
      f"환율: 1달러={rate:,.2f}원 ({html.escape(str(basis))})",
      "",
      "<b>1단계 현재 숫자 추적 — 3분기(7~9월) 단독</b>",
      f"• 매출 {a('revenue')} / 전년 동기 +26% (환율 제외 성장률도 +26%)",
      f"• 영업이익 {a('op_income')} / 전년 동기 -37% · 영업이익률 20%(전년 40%)",
      f"• 법률 합의 관련 비용 {a('legal_charge')} 포함(일회성 회계 비용)",
      f"• 해당 비용 제외 영업이익 {money(clean_op,rate)} · 단순 조정 영업이익률 약 {adj_margin:.1f}%",
      f"• 순이익 {a('net_income')} · 전년 대비 +264% (전년 높은 세율 기저효과 주의)",
      f"• 앱 사업 매출 {a('foa_revenue')} · 사업부 영업이익 {a('foa_op')}",
      f"• 리얼리티랩스 매출 {a('rl_revenue')} · 사업부 영업손실 {a('rl_op')}",
      "",
      "<b>현금 창출과 설비투자 — 3분기 단독</b>",
      f"• 영업현금흐름 {a('cash_from_ops')}",
      f"• 유형자산 취득 {a('ppe')} + 금융리스 원금상환 {a('finance_lease')}",
      f"• 잉여현금흐름 <b>{a('free_cash_flow')}</b> (실제 마이너스 · 검산 완료)",
      f"• 분기 설비투자·금융리스 원금 합계 {a('capex_q3')}",
      f"• Reuters의 사전 시장 예상 FCF {a('forecast_fcf')}보다 실제 FCF가 {money(6400,rate)} 개선.",
      f"• Reuters가 인용한 분기 설비투자 예상 {a('forecast_capex_q3')} 대비 실제 {a('capex_q3')}로 낮았음.",
      "• 설비투자 예상 하회는 확인되지만 실제 프로젝트 이연 여부는 공식적으로 확정되지 않았습니다.",
      "",
      "<b>2단계 미래 재평가 요인 발굴</b>",
      f"• 4분기 매출 전망 {a('q4_low')}~{a('q4_high')} (현재 환율 가정 전년비 약 1%p 역풍)",
      f"• 2026년 연간 설비투자 전망 {a('fy_capex_low')}~{a('fy_capex_high')}",
      f"• 직전 설비투자 전망 하한 {a('fy_capex_prev_low')}에서 {a('fy_capex_low')}으로 상향",
      "• Muse 개인용 에이전트 출시(9월) · Muse Wonder 모델 공개(10월): 사용자 수와 유료 전환·반복매출을 구분합니다.",
      "• Muse 출시 후 첫 약 6주 동안 1,000만명 이상 이용(언론이 인용한 경영진 발언); 유료가입·실제 매출 규모는 미공개.",
      "• 2027년 1월 19일 비의결권 C종 주식 도입 예정 · A/B 1주당 C종 1주 배당 조건.",
      "• C종 주식배당 자체와 향후 신주 발행을 통한 조달·경제적 지분희석은 별개입니다.",
      "",
      "<b>숨은 역풍·실패모드</b>",
      "• 신규 AI 서비스의 실사용량·유료 전환이 느리면 설비투자가 현금흐름을 더 압박할 수 있습니다.",
      f"• 법률 관련 비용 {a('legal_charge')}은 본업 광고 성장과 구분하되, 실제 지급 일정·추가 소송 위험을 확인합니다.",
      "• Muse 개인정보·에이전트 행동 안전, 데이터센터 전력·냉각·고객 채택 지연도 감시합니다.",
      "",
      "<b>공식 출처</b>",
      _link("메타 3분기 공식 실적",IR_Q3)+" | "+_link("Muse 제품 발표",MUSE),
      _link("Muse Wonder 공식 발표",MUSE_WONDER)+" | "+_link("Reuters 시장 예상",REUTERS_EXPECTATIONS),
    ]
    return "\n".join(lines)

def _load():
    if STATE.exists():
        return json.loads(STATE.read_text(encoding="utf-8"))
    return {"version":1,"seen_events":[],"updated_at":None}

def _news_events():
    """Only first-party RSS headlines explicitly about Muse metrics/financing."""
    try:
        root=ET.fromstring(_get(META_FEED,timeout=15))
    except Exception as e:
        print(f"WARN Meta newsroom feed unavailable: {e}")
        return []
    result=[]
    for item in root.findall(".//item"):
        title=(item.findtext("title") or "").strip()
        desc=(item.findtext("description") or "").strip()
        url=(item.findtext("link") or "").strip()
        raw_date=(item.findtext("pubDate") or "").strip()
        try:
            date=parsedate_to_datetime(raw_date).date()
        except (TypeError,ValueError,IndexError):
            continue
        if date<dt.date(2026,10,22) or not url:
            continue
        combined=(title+" "+re.sub("<[^>]+>"," ",desc)).lower()
        if "muse" not in combined:
            continue
        if not any(term in combined for term in (
            "subscrib","revenue","million users","pricing","monetiz",
            "privacy","security","paid","protection","users",
        )):
            continue
        if "about.fb.com" not in urllib.parse.urlparse(url).netloc.lower():
            continue
        result.append({"key":"muse:"+url.split("?")[0],"title":title,"url":url,"date":str(date)})
    return result

def _sec_earnings():
    try:
        data=json.loads(_get(SEC_SUBMISSIONS,timeout=18))
    except Exception as e:
        print(f"WARN SEC Meta submissions unavailable: {e}")
        return []
    recent=data.get("filings",{}).get("recent",{})
    forms=recent.get("form",[])
    items=recent.get("items",[])
    dates=recent.get("filingDate",[])
    accessions=recent.get("accessionNumber",[])
    out=[]
    for idx,form in enumerate(forms):
        if idx>=len(items) or idx>=len(dates) or idx>=len(accessions):break
        if form not in ("8-K","8-K/A"):
            continue
        if "2.02" not in str(items[idx]):
            continue
        date=dates[idx]
        if date<"2026-10-22":
            continue
        accession=accessions[idx]
        url=f"https://www.sec.gov/Archives/edgar/data/1326801/{accession.replace('-','')}/"
        out.append({"key":"sec-earnings:"+accession,"title":"메타 신규 SEC 실적 공시",
                    "date":date,"url":url})
    return out

def main(probe=False):
    OUT.mkdir(exist_ok=True)
    alert=OUT/"meta_ai_earnings_alert.html"
    pending=OUT/"meta_ai_earnings_pending.json"
    alert.unlink(missing_ok=True)
    pending.unlink(missing_ok=True)

    source_url,source_label=_verified_q3_source()
    state=_load()
    seen=set(state.get("seen_events",[]))
    notices=[]

    if Q3_KEY not in seen:
        rate,basis=_fx()
        notices.append(build_q3(rate,basis,source_label))
        seen.add(Q3_KEY)

    for event in _sec_earnings()+_news_events():
        key=event["key"]
        if key in seen:
            continue
        notices.append("\n".join([
            "📊 <b>메타 실적·Muse 공식 후속 변화</b>",
            f"판정: {html.escape(event['title'])}",
            f"공개일: {html.escape(event['date'])}",
            "• 공식자료의 새 사건을 확인했습니다. 세부 금액은 원문 검증 전 임의로 인용하지 않습니다.",
            _link("공식 원문",event["url"]),
        ]))
        seen.add(key)

    if probe:
        print(f"meta_official_source_valid={source_label} fresh_notices={len(notices)}")
        if notices:
            print("meta_sample_length="+str(len(notices[0])))
        return

    if notices:
        # New announcement limit; archive additional notices for a later run.
        delivered=notices[:5]
        if len(delivered)<len(notices):
            raise RuntimeError("Too many uncheckpointed Meta events; manual reconciliation required")
        alert.write_text("\n\n────────\n\n".join(delivered),encoding="utf-8")
        pending.write_text(json.dumps({"version":1,"seen_events":sorted(seen),
            "updated_at":dt.datetime.now(dt.timezone.utc).isoformat()
        },ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
        print(f"META_ALERT_READY notices={len(delivered)}")
    else:
        print("META_NO_MATERIAL_NEW_EVENT")

if __name__=="__main__":
    main(probe="--probe" in __import__("sys").argv)
