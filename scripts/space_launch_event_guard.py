#!/usr/bin/env python3
"""Conservative semantic guard for the independent space-launch Telegram watch."""
import datetime as dt
import hashlib
import re

RECENT_HOURS=48
TARGET=re.compile(r"price target|target price|목표주가|애널리스트 목표",re.I)
BROKER=re.compile(r"morgan stanley|pivotal research|citizens|citigroup|citi|"
                  r"keybanc|cantor fitzgerald|barclays|stifel|needham|"
                  r"analyst|애널리스트|증권사|목표주가",re.I)
DELAY=re.compile(r"delay|postpon|2027|pushed back|slips?|shift.*next year|"
                 r"연기|지연",re.I)
NOISE=re.compile(r"lawsuit|class action|options activity|why stock|insider sale|"
                 r"price prediction|주가 급등만|주가 전망만",re.I)
STOP=set(("rocket lab rocketlab spacex starship neutron electron flight first launch"
          " shares share price target stock stocks year 2026 2027 2028 the of to for"
          " and on in a an after by from with new company analyst said says may"
          " rocket satellite space story investing bloomberg reuters").split())
WORDS=re.compile(r"[a-zA-Z0-9가-힣]+")

def material_words(title):
    title=re.sub(r"\s+[-|]\s+[^-|]{1,65}$","",title.lower())
    return {w for w in WORDS.findall(title) if len(w)>2 and w not in STOP}

def kind(category,title):
    t=title.lower()
    if category=="rocketlab":
        if "neutron" in t and DELAY.search(t):return "development_delay"
        if TARGET.search(t) or BROKER.search(t):return "analyst"
        if re.search(r"contract|award|signed|secures|수주|계약",t):return "contract"
        return "development"
    if category=="spacex_valuation":
        if TARGET.search(t) or BROKER.search(t):return "analyst"
        return "space_technology"
    return "sector"

def eligible(category,item,now):
    title=str(item.get("title") or "")
    if not title or NOISE.search(title):return False
    date=item.get("published")
    if not date:return False
    try:pub=dt.datetime.fromisoformat(date)
    except (TypeError,ValueError):return False
    if pub.tzinfo is None:return False
    age=now-pub.astimezone(dt.timezone.utc)
    if not -dt.timedelta(minutes=20)<=age<=dt.timedelta(hours=RECENT_HOURS):
        return False
    if category=="rocketlab":
        if kind(category,title) in ("development_delay","analyst"):return False
        if not re.search(r"rocket lab|electron|neutron|synspective",title,re.I):return False
    if category=="spacex_valuation" and kind(category,title)=="analyst":
        return False
    return True

def semantic_pair(category,a,b):
    sa=str(a.get("source") or "").casefold().strip()
    sb=str(b.get("source") or "").casefold().strip()
    if not sa or not sb or sa==sb:return False
    ta,tb=str(a.get("title") or ""),str(b.get("title") or "")
    if NOISE.search(ta) or NOISE.search(tb):return False
    if kind(category,ta)!=kind(category,tb):return False
    x,y=material_words(ta),material_words(tb)
    common=x&y
    return len(common)>=2 and len(common)/max(1,len(x|y))>=0.4

def topic_key(category,title):
    s=title.lower()
    if category=="rocketlab" and "synspective" in s:
        return "electron_synspective"
    if category=="rocketlab" and "neutron" in s:
        return "neutron_development"
    if category=="spacex_valuation" and "flight 15" in s:
        return "flight15"
    word="|".join(sorted(material_words(title)))
    return hashlib.sha256(word.encode("utf-8")).hexdigest()[:14]

def semantic_id(category,item):
    pub=dt.datetime.fromisoformat(item["published"])
    event=kind(category,item["title"])
    # A single first-launch delay must retain its semantic identity when
    # follow-up coverage crosses a week boundary; different headlines are not
    # new development milestones. Date-scoped IDs are kept for other stories.
    if category=="rocketlab" and event=="development_delay" and "neutron" in item["title"].lower():
        return "semantic:rocketlab:neutron:first_flight_shift_2027"
    monday=pub.date()-dt.timedelta(days=pub.weekday())
    return "semantic:"+category+":"+topic_key(category,item["title"])+":"+event+":"+monday.isoformat()

def self_test():
    now=dt.datetime(2026,10,17,10,tzinfo=dt.timezone.utc)
    article=lambda title,date="2026-10-16T10:00:00+00:00":dict(title=title,published=date,source="Reuters")
    assert kind("rocketlab","Rocket Lab Neutron first launch delayed to 2027")=="development_delay"
    assert kind("rocketlab","Citizens cuts Rocket Lab target after Neutron delay")=="development_delay"
    assert kind("rocketlab","Rocket Lab Neutron maiden flight delayed")=="development_delay"
    assert kind("rocketlab","Rocket Lab Electron secures 20 mission contract")=="contract"
    assert kind("spacex_valuation","Morgan Stanley raises SpaceX price target")=="analyst"
    assert not eligible("rocketlab",article("Rocket Lab Neutron debut delayed to 2027"),now)
    assert not eligible("rocketlab",article("Citizens lowers Rocket Lab price target on Neutron delay"),now)
    assert not eligible("spacex_valuation",article("Morgan Stanley raises SpaceX target price"),now)
    assert eligible("rocketlab",article("Rocket Lab signs Synspective Electron launch contract"),now)
    assert not eligible("rocketlab",article("Rocket Lab signs Synspective Electron launch contract","2026-10-12T10:00:00+00:00"),now)
    a=article("Rocket Lab secures Synspective 20-launch contract")
    b=dict(article("Synspective secures Rocket Lab 20-launch contract"),source="Bloomberg")
    c=dict(article("Citizens cuts Rocket Lab target after Neutron launch delay"),source="Bloomberg")
    assert semantic_pair("rocketlab",a,b) and not semantic_pair("rocketlab",a,c)
    assert semantic_id("rocketlab",a)==semantic_id("rocketlab",b)
    delayed1=article("Rocket Lab Neutron first flight delayed to 2027","2026-10-14T20:00:00+00:00")
    delayed2=article("Citizens lowers Rocket Lab target on Neutron 2027 delay","2026-10-22T20:00:00+00:00")
    assert semantic_id("rocketlab",delayed1)==semantic_id("rocketlab",delayed2)
    assert kind("rocketlab",delayed2)=="development_delay"
    print("space_launch_event_guard_self_test=ok stale=1 categories=1 semantic_dedup=1")
# Historical mislabelled notifications; unique IDs ensure each correction once.
FACT_CASES = (
  ("audit:20261017:neutron_2027", "Rocket Lab Neutron 2027",
   "https://www.sec.gov/Archives/edgar/data/1819994/000181999426000067/rklb-20261014.htm",
   ("Neutron","October 14, 2026","next year")),
  ("audit:20261017:morgan_300_unchanged", "Morgan Stanley SpaceX",
   "https://www.pricetargets.com/NASDAQ/SPCX/",
   ("Morgan Stanley","$300","Overweight")),
  ("audit:20261017:citizens_130_90", "Citizens Rocket Lab",
   "https://finance.yahoo.com/markets/stocks/articles/rklb-stock-citizens-cuts-target-122451102.html",
   ("Citizens","$90","$130")),
)

def source_valid(text,required):
    import html
    clean=html.unescape(re.sub(r"\s+"," ",re.sub(r"<[^>]*>"," ",text)))
    return all(word.lower() in clean.lower() for word in required)

def correction_notices(seen,fetch,rate):
    alerts=[]
    errors=[]
    def kr(amount):
        money="$"+str(amount)
        return money+(f"(약 {round(amount*rate):,}원)" if rate else "(원화 환산 미확인)")
    for key,label,url,markers in FACT_CASES:
        if key in seen:continue
        try:
            raw=fetch(url)
            txt=raw.decode("utf-8",errors="replace") if isinstance(raw,bytes) else raw
            if not source_valid(txt,markers):
                raise ValueError("원문 인물·숫자 또는 변경상태 문구 불일치")
        except Exception as exc:
            errors.append(label+": "+type(exc).__name__)
            continue
        if "neutron" in key:
            text=(
             "[개발·일정 지연] Rocket Lab Neutron 첫 비행 2027년으로 연기\n"
             "• 2026년 10월 14일 Rocket Lab 공식 발표. Electron 발사 수주가 아니라 차세대 발사체 개발 일정 변경입니다.\n"
             "• 병목: 1단 탄소복합재 탱크 제작·품질 검증, 재제작과 시험 일정.\n"
             "• 매출 연결: Neutron 상용 발사 매출 시점 지연 가능성. Electron 기존 계약과 구분.\n"
             "• 원문: "+url)
        elif "morgan" in key:
            text=(
             "[증권사·목표주가 유지] Morgan Stanley, SpaceX\n"
             "• 2026년 10월 14일 비중확대 의견과 목표주가 "+kr(300)+" 유지. 일부 기사 제목의 '상향'은 본문과 다릅니다.\n"
             "• 미래 요인: 분산 추론과 궤도 AI 컴퓨팅 기대이며 고객 계약·매출 확정과는 별개입니다.\n"
             "• 원문: "+url)
        elif "citizens" in key:
            text=(
             "[증권사·목표주가 하향] Citizens, Rocket Lab(RKLB)\n"
             "• 2026년 10월 16일 목표주가 "+kr(130)+"→"+kr(90)+"(-30.8%), 시장수익률 상회 의견 유지.\n"
             "• 원인: Neutron 2027년 지연·탄소복합재 탱크 품질 문제. Citizens는 Citigroup이 아닙니다.\n"
             "• 원문: "+url)
        else:
            text=(
             "[증권사·목표주가 상향] Pivotal Research, SpaceX\n"
             "• 2026년 10월 12일 목표주가 "+kr(220)+"→"+kr(230)+"(+4.5%), 매수 의견 유지.\n"
             "• 이유: Starlink Mobile 가입자 추정 상향. 직접 무선망 구축과 승인 완료를 뜻하지 않습니다.\n"
             "• 원문: "+url)
        alerts.append((key,text))
    return alerts,errors

def correction_self_test():
    mapping={entry[2]: " ".join(entry[3]) for entry in FACT_CASES}
    def fake(url):
        if url not in mapping:raise RuntimeError("unknown")
        return mapping[url].encode()
    alerts,errors=correction_notices({},fake,1300)
    assert len(alerts)==3 and not errors
    assert "117,000원" in alerts[2][1]
    assert not correction_notices({key:"sent" for key,_,_,_ in FACT_CASES},fake,1300)[0]
    alerts2,err2=correction_notices({},lambda x: b"invalid",1300)
    assert not alerts2 and len(err2)==3
    print("space_launch_correction_self_test=ok source_guard=1 once_per_event=1 price=1")

if __name__=="__main__":
 self_test()
 correction_self_test()
