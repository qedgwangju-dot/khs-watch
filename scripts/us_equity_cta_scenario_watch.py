#!/usr/bin/env python3
"""Secondary Goldman US-equity CTA scenarios; separate from CFTC and Treasury."""
from __future__ import annotations
import argparse, datetime as dt, hashlib, html, json, os, re
from pathlib import Path
from urllib.parse import quote, urlparse, urlencode
from urllib.request import Request, urlopen
import xml.etree.ElementTree as ET
from zoneinfo import ZoneInfo
from bs4 import BeautifulSoup

ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/"out"
STATE=ROOT/"data/us_equity_cta_scenario_state.json"
STATUS=OUT/"us_equity_cta_scenario_status.json"
PENDING=OUT/"us_equity_cta_scenario_pending.json"
RECEIPT=OUT/"us_equity_cta_scenario_receipt.json"
EXPECTED_BOT="khs887900887900008879_bot"
NY=ZoneInfo("America/New_York")
KST=ZoneInfo("Asia/Seoul")
TRUSTED={"reuters.com","investing.com","marketwatch.com","cnbc.com","bloomberg.com",
         "qz.com","benzinga.com","finance.yahoo.com","hankyung.com",
         "mk.co.kr","edaily.co.kr","geukjin.com"}
NUM=r"(\d{1,4}(?:,\d{3})*(?:\.\d+)?)"
GLOBAL=re.compile(r"글로벌\s*주식(?:\s*기준)?[^0-9]{0,35}"+NUM+r"\s*억\s*달러")
US=re.compile(r"미국\s*주식(?:에서는|에서|으로는|에는)?[^0-9]{0,35}"+NUM+r"\s*억\s*달러")

def fetch(url, timeout=9):
    req=Request(url,headers={"User-Agent":"Mozilla/5.0 (khs-watch)", "Accept-Language":"ko,en;q=0.8"})
    with urlopen(req,timeout=timeout) as r:
        return r.geturl(),r.read(1600000).decode("utf-8","replace")

def publisher(url):
    host=(urlparse(url).hostname or "").lower().removeprefix("www.")
    if host in ("sg.finance.yahoo.com","finance.yahoo.com"):
        return "yahoo.com"
    return next((x for x in TRUSTED if host==x or host.endswith("."+x)),None)

def rss_discovery(reader=fetch):
    from email.utils import parsedate_to_datetime
    items={}
    feed_ok=0
    feed_failed=0
    queries=('"Goldman" "CTA" "flat tape" "buy"','"Eq Positioning and Key Levels" CTA',
             '"골드만삭스" "CTA" "횡보" "매수"')
    for q in queries:
        for url in ("https://www.bing.com/news/search?q="+quote(q)+"&format=rss",
                    "https://news.google.com/rss/search?q="+quote(q)+"&hl=ko&gl=KR&ceid=KR:ko"):
            try:
                _,xml=reader(url,timeout=7)
                root=ET.fromstring(xml)
                feed_ok+=1
                for item in root.findall(".//item")[:12]:
                    link=(item.findtext("link") or "").strip()
                    title=(item.findtext("title") or "")
                    if not link.startswith("https://") or not re.search("cta|골드만|Goldman",title,re.I):
                        continue
                    try:date=parsedate_to_datetime(item.findtext("pubDate")).date()
                    except (TypeError,ValueError,OverflowError):continue
                    items[link]=(link,date,title)
            except (OSError,ET.ParseError,ValueError,RuntimeError):
                feed_failed+=1
                continue
    # Direct dated public index is a single secondary publisher, not an
    # independent Goldman note. Expire this known 2026-11-17 index observation.
    now=dt.datetime.now(NY).date()
    if dt.date(2026,11,17)<=now<=dt.date(2026,11,24):
        url="https://geukjin.com/telegram"
        items.setdefault(url,(url,dt.date(2026,11,17),"YM리서치 11월17일 CTA 공개요약"))
    print(f"cta_public_feeds_ok={feed_ok} failed={feed_failed} candidates={len(items)}")
    return list(items.values())[:24]


def datetime_month(s):
    names=("jan","feb","mar","apr","may","jun","jul","aug","sep","oct","nov","dec")
    return names.index(s[:3].lower())+1

def parse_note(text,published):
    text=" ".join(html.unescape(text or "").split())
    if not re.search(r"(?:골드만삭스|Goldman Sachs)",text,re.I) or not re.search("CTA",text,re.I):
        return None
    dated=re.search(r"11월\s*17일\s*골드만삭스",text)
    # Report date must be in body; publication metadata is not an observed CTA date.
    if dated and published.year==2026:
        report=dt.date(2026,11,17)
    else:
        pattern=re.search(r"(20\d{2}-\d{2}-\d{2}).{0,90}(?:Goldman|골드만)",text,re.I)
        report=None
        if pattern:
            try:report=dt.date.fromisoformat(pattern.group(1))
            except ValueError:pass
        if report is None:
            named=re.search(
                r"(?:Goldman Sachs.{0,110}?)?\b(Jan(?:uary)?|Feb(?:ruary)?|Mar(?:ch)?|Apr(?:il)?|"
                r"May|Jun(?:e)?|Jul(?:y)?|Aug(?:ust)?|Sep(?:tember)?|Oct(?:ober)?|"
                r"Nov(?:ember)?|Dec(?:ember)?)\.?\s*(\d{1,2}),?\s*(20\d{2})\b",
                text,re.I)
            if named:
                try:
                    month=datetime_month(named.group(1))
                    report=dt.date(int(named.group(3)),month,int(named.group(2)))
                except ValueError:pass
        if report is None:return None
    if not 0<=(published-report).days<=7:
        return None
    start=re.search(r"향후\s*1\s*주일.{0,80}(?:CTA|수급)|over\s+the\s+next\s+1\s+week",text,re.I)
    if not start:return None
    remainder=text[start.end():]
    stop=re.search(r"향후\s*1\s*개월|over\s+the\s+next\s+1\s+month",remainder,re.I)
    if not stop:return None
    week=remainder[:stop.start()][:1900]
    month=remainder[stop.start():stop.start()+750]
    pats={"up":r"상승할\s*경우|상승\s*시|Up\s*tape",
          "flat":r"횡보하는\s*상황에서도|횡보\s*시|Flat\s*tape",
          "down":r"하락\s*시나리오에서는|하락\s*시|Down\s*tape"}
    hit={k:re.search(v,week,re.I) for k,v in pats.items()}
    if any(v is None for v in hit.values()):return None
    u,f,d=(hit[k].start() for k in ("up","flat","down"))
    if not u<f<d:return None
    chunks={"up":week[u:f],"flat":week[f:d],"down":week[d:]}
    result={}
    for key,chunk in chunks.items():
        g,s=GLOBAL.search(chunk),US.search(chunk)
        if g and s:
            numbers=[float(v.group(1).replace(",",""))/10 for v in (g,s)]
        else:
            figs=re.findall(r"\$\s*(\d+(?:\.\d+)?)\s*(?:bn|billion)",chunk,re.I)
            if len(figs)<2 or not re.search(r"\bUS\b|\bU\.S\.\b",chunk,re.I):return None
            numbers=[float(figs[0]),float(figs[1])]
        if not all(0<x<500 for x in numbers):return None
        sign=-1 if key=="down" else 1
        result[key]=[round(sign*n,2) for n in numbers]
    up_mark=re.search(r"(?:상승\s*시|up tape)",month,re.I)
    down_mark=re.search(r"(?:하락\s*시|down tape)",month,re.I)
    if not up_mark or not down_mark or down_mark.start()<=up_mark.start():return None
    up=month[up_mark.start():down_mark.start()]
    down=month[down_mark.start():down_mark.start()+220]
    def monthly(s):
        m=re.search(NUM+r"\s*억\s*달러",s)
        if m:return float(m.group(1).replace(",",""))/10
        m=re.search(r"\$\s*(\d+(?:\.\d+)?)\s*(?:bn|billion)",s,re.I)
        return float(m.group(1)) if m else None
    a,b=monthly(up),monthly(down)
    if a is None or b is None or not(0<a<500 and 0<b<500):return None
    return {"report":report.isoformat(),"week":result,
            "month":{"up_global":round(a,2),"down_global":-round(b,2)}}

def semantic_key(e):
    return hashlib.sha256(json.dumps(e,sort_keys=True,separators=(",",":")).encode()).hexdigest()

def collect(*,today=None, discovery=rss_discovery, reader=fetch):
    today=today or dt.datetime.now(NY).date()
    votes={}
    counters={"candidate":0,"parsed":0,"publishers":0}
    for url,pub,title in discovery():
        if not 0<=(today-pub).days<=7 or not publisher(url):continue
        counters["candidate"]+=1
        try:
            final,raw=reader(url,timeout=9)
            dom=publisher(final)
            if not dom:continue
            soup=BeautifulSoup(raw,"html.parser")
            for tag in soup(["script","style","nav","footer"]):tag.decompose()
            body=(soup.find("article") or soup.find("main") or soup).get_text(" ",strip=True)
            note=parse_note(body,pub)
            if note is None:continue
            counters["parsed"]+=1
            votes.setdefault(semantic_key(note),{})[dom]=(final,note,body[:3000])
        except (OSError,ValueError,RuntimeError,TypeError):
            continue
    candidates=[]
    for key,by_domain in votes.items():
        bodies={hashlib.sha256(" ".join(obj[2].split()).encode()).hexdigest()
                for obj in by_domain.values()}
        note=next(iter(by_domain.values()))[1]
        if len(by_domain)>=2 and len(bodies)>=2:
            candidates.append((2,note["report"],key,by_domain,note))
        elif len(by_domain)==1:
            candidates.append((1,note["report"],key,by_domain,note))
    # Inconsistent publishers quoting the same report must not generate even
    # a one-source preliminary direction alert.
    if len(votes)>=2:
        all_dates={next(iter(x.values()))[1]["report"] for x in votes.values()}
        if len(all_dates)==1:
            return {"status":"withheld","reason":"같은 골드만삭스 기준일에 상충하는 시나리오 수치",
                    "diagnostics":counters}
    if not candidates:
        return {"status":"withheld","reason":"기준일·전망치 검증 가능한 공개 기사 미확보",
                "diagnostics":counters}
    tier,_,key,by_domain,note=max(candidates)
    counters["publishers"]=len(by_domain)
    level="verified_secondary" if tier==2 else "reported_single"
    return {"status":level,"key":level+":"+key,"note":note,
            "sources":[v[0] for v in by_domain.values()],"diagnostics":counters}

def format_won(bn,rate):
    if rate is None:return "원화 환산 보류"
    from decimal import Decimal,ROUND_HALF_UP
    amount=(Decimal(str(abs(bn)))*Decimal(str(rate))*10).quantize(Decimal("1"),rounding=ROUND_HALF_UP)
    jo,eok=divmod(int(amount),10000)
    return "약 "+(f"{jo:,}조 {eok:,}억원" if jo and eok else
                  f"{jo:,}조원" if jo else f"{eok:,}억원")

def rate_for_today(today):
    try:
        from us_positioning_fx import collect_fx,checked_fx
        class Reader:
            def get(self,url,*,evidence_url=None):return fetch(url)[1]
        snapshot=checked_fx(collect_fx(Reader(),today.isoformat()),today.isoformat())
        return (snapshot["krw_per_usd"],snapshot["date"]) if snapshot else (None,None)
    except Exception:return (None,None)

def render(data,rate=None,fxdate=None):
    n=data["note"];w=n["week"];m=n["month"]
    def fmt(v):
        return ("+" if v>0 else "-" if v<0 else "")+f"{abs(v)*10:,.0f}억달러({format_won(v,rate)})"
    bias="횡보에도 매수 우위 전망" if w["flat"][1]>0 else "횡보에서도 매도 위험"
    preliminary=data["status"]=="reported_single"
    stage="[미국 주식 CTA 단일 보도 선행경보·미확정]" if preliminary else "[미국 주식 CTA 보도 교차확인 경보]"
    provenance=("단일 공개 보도·골드만삭스 원본 미확인" if preliminary else
                "서로 다른 공개 발행처 2곳 수치 일치·골드만삭스 원본 미확인")
    lines=[
        f"<b>{stage} {bias}</b>",
        f"• 보고 기준일 {n['report']} · {provenance}",
        f"• 미국 주식 1주일: 상승 {fmt(w['up'][1])} / 횡보 {fmt(w['flat'][1])} / 하락 {fmt(w['down'][1])}",
        f"• 글로벌 주식 1주일: 상승 {fmt(w['up'][0])} / 횡보 {fmt(w['flat'][0])} / 하락 {fmt(w['down'][0])}",
        f"• 글로벌 주식 1개월: 상승 {fmt(m['up_global'])} / 하락 {fmt(m['down_global'])}",
        "• 실제 체결된 CTA 매수·매도가 아니라 모델 예상 수급; 1주일과 1개월을 혼동하지 않음",
        "• CFTC Leveraged Funds는 별도 모집단이며 골드만삭스의 CTA 원본 수치와 동일시하지 않음",
        f"• 환율: 한국은행 {fxdate} 1달러={rate}원" if rate else "• 원화 환산: 한국은행 동일 날짜 자료 미확인",
        "• 판정: 가격·모멘텀 개선 여부 추가 확인 전, 상승 추세 확정 불가",
        "• 출처: "+" / ".join('<a href="'+html.escape(url,quote=True)+'">공개보도'+str(i+1)+'</a>'
                                for i,url in enumerate(data["sources"][:3])),
    ]
    result="\n".join(lines)
    if len(result)>3900:raise ValueError("Telegram payload too large")
    return result

def read_state(path):
    if not path.exists():return {"sent_keys":[]}
    state=json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(state,dict) or not isinstance(state.get("sent_keys"),list):
        raise ValueError("Existing CTA state invalid; refuse reset")
    return state

def send(text):
    token=os.environ.get("TELEGRAM_BOT_TOKEN","").strip()
    chat=os.environ.get("TELEGRAM_CHAT_ID","").strip()
    if not token or not chat:raise RuntimeError("Existing Telegram credentials absent")
    who=json.loads(fetch("https://api.telegram.org/bot"+token+"/getMe")[1])
    bot=(who.get("result") or {}).get("username")
    expected=os.environ.get("EXPECTED_TELEGRAM_BOT_USERNAME",EXPECTED_BOT)
    if not who.get("ok") or str(bot).lower()!=expected.lower():
        raise RuntimeError("Telegram bot does not match existing US Positioning route")
    req=Request("https://api.telegram.org/bot"+token+"/sendMessage",
        data=urlencode({"chat_id":chat,"text":text,"parse_mode":"HTML",
                        "disable_web_page_preview":"true"}).encode(),method="POST")
    # No retry: an accepted response can time out locally.
    with urlopen(req,timeout=30) as response:
        payload=json.loads(response.read().decode())
    obj=payload.get("result") or {}
    msgid=obj.get("message_id")
    remote=obj.get("chat") or {}
    rid=remote.get("id")
    match=(str(rid)==chat if chat.lstrip("-").isdigit() else
           str(remote.get("username","")).lower()==chat[1:].lower() if chat.startswith("@") else False)
    if not payload.get("ok") or type(msgid)!=int or msgid<=0 or type(rid)!=int or not match:
        raise RuntimeError("Telegram delivery or target not confirmed")
    return {"bot_username":bot,"chat_id_returned":True,"chat_id_match":True,"message_id":msgid}

def run(*,validate_only=False,today=None,discovery=rss_discovery,reader=fetch,
        state_path=STATE,sender=send,fx_reader=rate_for_today):
    OUT.mkdir(parents=True,exist_ok=True)
    for file in (STATUS,PENDING,RECEIPT):file.unlink(missing_ok=True)
    state=read_state(state_path)
    found=collect(today=today,discovery=discovery,reader=reader)
    if found["status"] not in ("verified_secondary","reported_single"):
        status={"status":"source_withheld","telegram_sent":False,
                "reason":found["reason"],"diagnostics":found["diagnostics"]}
    else:
        key=found["key"]
        due=key not in state["sent_keys"]
        status={"status":"alert_due" if due else "duplicate_suppressed",
                "stage":found["status"], "report":found["note"]["report"],
                "key":key,"telegram_sent":False}
        if due:
            rate,date=fx_reader(dt.datetime.now(KST).date())
            content=render(found,rate,date)
            if not validate_only:
                receipt=sender(content)
                state["sent_keys"]=(state["sent_keys"]+[key])[-80:]
                state["last_alert"]={**receipt,"key":key,"report":found["note"]["report"]}
                PENDING.write_text(json.dumps(state,ensure_ascii=False,indent=2)+"\n")
                RECEIPT.write_text(json.dumps(state["last_alert"],ensure_ascii=False,indent=2)+"\n")
                status["telegram_sent"]=True
                status["message_id"]=receipt["message_id"]
            status["rendered"]=True
            status["validate_only"]=validate_only
    STATUS.write_text(json.dumps(status,ensure_ascii=False,indent=2)+"\n")
    print("us_equity_cta_status="+json.dumps(status,ensure_ascii=False))
    return status

if __name__=="__main__":
    ap=argparse.ArgumentParser()
    ap.add_argument("--validate-only",action="store_true")
    cli=ap.parse_args()
    run(validate_only=cli.validate_only)
