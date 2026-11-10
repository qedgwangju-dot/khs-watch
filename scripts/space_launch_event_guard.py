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
DELAY=re.compile(r"delay|postpon|pushed back|slips?|shift.*next year|"
                 r"reschedul|defer|연기|지연",re.I)
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
        # Broker actions are independent from the underlying Neutron delay.
        if TARGET.search(t) or BROKER.search(t):return "analyst"
        if "neutron" in t and DELAY.search(t):return "development_delay"
        if re.search(r"contract|award|signed|signs|secures|secured|"
                     r"lands? (?:over |more than |\$)|launch deals?|"
                     r"booked .{0,35}launch|발사계약|발사 계약|수주|계약",t):
            return "contract"
        return "development"
    if category=="spacex_valuation":
        if TARGET.search(t) or BROKER.search(t):return "analyst"
        return "space_technology"
    if category=="moon_base_clps":
        if not re.search(r"nasa|clps|moon base|lunar|달 기지|달 수송|달 화물",t):return "unrelated"
        # A new contract/cap amendment is separate from the Nov-7 initial
        # framework selection. Do not replay the known CLPS1 2.6->4.2 change.
        if re.search(r"cancel|terminate|rescind|해지|취소|철회",t):return "cancellation_report"
        modified=re.search(r"amendment|amended|modification|revised schedule|schedule slips?|"
                           r"increases? (?:the )?(?:contract|ceiling|limit|award)|"
                           r"raises? (?:the )?(?:contract|ceiling|limit|award)|"
                           r"ceiling increased|contract extension|납기 변경|계약 증액|계약 감액|"
                           r"계약 정정|일정 연기|한도 상향|상한 증액",t)
        historic=re.search(r"4[.]2 billion|42억|2[.]6 billion|26억",t) and re.search(r"clps.?1",t)
        if modified and not historic:return "contract_change_report"
        # Baseline selections/contract ceilings create eligibility, not sales.
        if re.search(r"clps.?2|commercial lunar payload services",t) and re.search(
            r"eight|8 companies|8 firms|selected|10 billion|contract ceiling|8개사|8곳|계약 한도",t
        ):return "framework_selection"
        if re.search(r"26억|42억|2[.]6 billion|4[.]2 billion|clps.?1",t):return "framework_selection"
        if re.search(r"cancel|terminate|rescind|해지|취소|철회",t):return "cancellation_report"
        if re.search(r"task order|mission award|award.{0,45}(mission|contract)|contract.{0,45}award|"
                     r"new clps|delivery mission|purchase order|lunar lander order|임무 수주|개별 발주|"
                     r"계약 체결|신규 수주",t):return "task_order_report"
        return "unrelated"
    if category=="starlink_optical":
        if not re.search(r"starlink|spacex|스타링크|스페이스x",t):return "unrelated"
        if not re.search(r"v4|version.?4|laser|optical|subsea|undersea|해저케이블|레이저",t):return "unrelated"
        if re.search(r"(?:launch(?:ed|es)?|deploy(?:ed|s)?).{0,35}first.{0,30}(?:v4|version.?4)|"
                     r"first.{0,25}(v4|version.?4).{0,30}(launch|deploy)|"
                     r"(v4|version.?4).{0,45}(launched|deployed|in orbit)|"
                     r"(v4|version.?4).{0,25}(발사 성공|궤도 배치)",t):return "deployment_report"
        if re.search(r"fcc.{0,45}(grant|approv|authoriz)|(?:grant|approv|authoriz).{0,45}fcc|"
                     r"fcc.{0,45}승인",t) and not re.search(r"to approve|may approve|seeks|filed|신청|요청",t):
            return "fcc_approval_report"
        if re.search(r"filed|application|seeks|requested|fcc filing|신청|심사 요청",t):return "fcc_application"
        if re.search(r"(demonstrat|test).{0,55}(10\s*tb|laser|optical)|"
                     r"(10\s*tb|laser|optical).{0,55}(demonstrat|achiev|tested)|"
                     r"레이저.*(시험 성공|검증 완료)",t) and not re.search(r"plan|target|could|will|예정|목표",t):
            return "verified_test_report"
        if re.search(r"sign(?:s|ed)?.{0,45}(contract|agreement)|contract award|"
                     r"commercial deal|공급계약 체결|수주 확정",t) and re.search(r"subsea|undersea|optical|laser|해저|광통신",t):
            return "commercial_contract_report"
        if re.search(r"publishes?.{0,50}(spec|design)|unveils?.{0,40}(spec|design)|"
                     r"confirmed specifications|최종 사양 확정|설계 사양 발표",t):return "specification_report"
        # The 2026-11-06 10-versus-100 laser remark is a design ambition.
        return "projection_only"
    if category=="golden_dome":
        if not re.search(r"golden dome|골든돔",t) or not re.search(r"google|alphabet|구글|알파벳|aalyria|알리리아",t):
            return "unrelated"
        if re.search(r"award(?:ed)? contract|signs?(?:\s+a)?\s+contract|signed contract|contract awarded|수주 확정|계약 체결",t):
            return "contract_reported"
        if re.search(r"in talks|discuss|negotia|consider|weighs|to join|협의|논의|검토|추진",t):
            return "pre_contract"
        return "project_update"
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
    window=dt.timedelta(days=7) if category=="golden_dome" else dt.timedelta(hours=RECENT_HOURS)
    if not -dt.timedelta(minutes=20)<=age<=window:
        return False
    if category=="golden_dome" and kind(category,title)=="unrelated":return False
    if category in {"moon_base_clps","starlink_optical"} and kind(category,title) in {
        "unrelated","framework_selection","projection_only"
    }:return False
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
    if category=="moon_base_clps":
        # Two unrelated Moon Base missions must not corroborate one another.
        tokens=("promise","minicast","cislunar communications","blue ghost",
                "griffin","redwire","firefly","voyager","intuitive machines")
        pa={s for s in tokens if s in ta.lower()}
        pb={s for s in tokens if s in tb.lower()}
        if pa or pb:
            if not (pa&pb):return False
    if category=="golden_dome":
        # Different publishers may relay the same Bloomberg scoop; evidence
        # remains one initial source until a company/DoD notice independently confirms it.
        return kind(category,ta)!="unrelated"
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
        # Preserve 2027 dedup identity, but do not suppress a future 2028 slip.
        years=re.findall(r"\b20\d{2}\b",item["title"])
        return "semantic:rocketlab:neutron:first_flight_shift_"+(years[-1] if years else "undated")
    if category in {"moon_base_clps","starlink_optical"}:
        # Same stage and project must keep one key across republished articles.
        label="moon" if category=="moon_base_clps" else "optical"
        for term,key in (
            ("promise","promise"),("minicast","minicast"),("cislunar","cislunar"),
            ("redwire","redwire"),("firefly","firefly"),("voyager","voyager"),
            ("v4","v4"),("version 4","v4"),("100,000","100k"),
            ("subsea","subsea"),("undersea","subsea"),
        ):
            if term in item["title"].lower():
                return "semantic:"+label+":"+key+":"+event+":"+pub.strftime("%Y-%m")
    if category=="golden_dome":
        # Cross-month repeats of the same preliminary negotiation are not a new contract.
        period=(f"{pub.year}Q{(pub.month-1)//3+1}" if event=="pre_contract"
                else pub.strftime("%Y-%m"))
        return "semantic:golden_dome:google_data_security:"+event+":"+period
    monday=pub.date()-dt.timedelta(days=pub.weekday())
    return "semantic:"+category+":"+topic_key(category,item["title"])+":"+event+":"+monday.isoformat()

def self_test():
    now=dt.datetime(2026,10,17,10,tzinfo=dt.timezone.utc)
    article=lambda title,date="2026-10-16T10:00:00+00:00":dict(title=title,published=date,source="Reuters")
    assert kind("rocketlab","Rocket Lab Neutron first launch delayed to 2027")=="development_delay"
    assert kind("rocketlab","Citizens cuts Rocket Lab target after Neutron delay")=="analyst"
    assert kind("rocketlab","Rocket Lab signs Neutron launch contract for 2027")=="contract"
    assert kind("rocketlab","Rocket Lab Neutron maiden flight delayed")=="development_delay"
    assert kind("rocketlab","Rocket Lab Electron secures 20 mission contract")=="contract"
    assert kind("rocketlab","Rocket Lab lands over $515M in Neutron launch deals from constellation operators in Q3")=="contract"
    assert kind("rocketlab","Rocket Lab reports successful Neutron test firing")=="development"
    assert kind("rocketlab","Rocket Lab Neutron first flight delayed to 2027")=="development_delay"
    assert kind("spacex_valuation","Morgan Stanley raises SpaceX price target")=="analyst"
    assert kind("golden_dome","Alphabet Google in talks to join Golden Dome")=="pre_contract"
    assert kind("golden_dome","Google signs contract for Golden Dome data security")=="contract_reported"
    assert kind("golden_dome","Golden Dome rocket launch tests")=="unrelated"
    assert kind("moon_base_clps","NASA selects eight CLPS 2 companies for $10 billion")=="framework_selection"
    assert kind("moon_base_clps","NASA awards a new CLPS lunar task order to Firefly")=="task_order_report"
    assert kind("moon_base_clps","NASA raises CLPS 1 ceiling to $4.2 billion")=="framework_selection"
    assert kind("moon_base_clps","NASA raises CLPS 2 ceiling to $15 billion after amendment")=="contract_change_report"
    assert kind("moon_base_clps","NASA increases CLPS 2 contract value following amended order")=="contract_change_report"
    assert kind("moon_base_clps","NASA CLPS 2 landing schedule slips into 2029")=="contract_change_report"
    assert kind("starlink_optical","Musk projects 100k Starlink V4 satellites with 100 lasers")=="projection_only"
    assert kind("starlink_optical","SpaceX successfully launches first Starlink V4 satellite")=="deployment_report"
    assert kind("starlink_optical","SpaceX files FCC application for Starlink V4 optical satellites")=="fcc_application"
    assert kind("starlink_optical","FCC approves SpaceX Starlink V4 optical satellite deployment")=="fcc_approval_report"
    assert not eligible("starlink_optical",article("Musk predicts Starlink V4 100k 100 lasers"),now)
    assert not eligible("moon_base_clps",article("NASA selects eight CLPS 2 companies for $10 billion"),now)
    m1=article("NASA awards new CLPS task order to Firefly","2026-10-16T10:00:00+00:00")
    m2=dict(article("Firefly receives NASA CLPS task order","2026-10-16T10:00:00+00:00"),source="Bloomberg")
    m3=dict(article("NASA awards Voyager lunar Griffin task order","2026-10-16T10:00:00+00:00"),source="CNBC")
    assert semantic_pair("moon_base_clps",m1,m2)
    assert not semantic_pair("moon_base_clps",m1,m3)
    g1=article("Alphabet Google in talks to join Golden Dome","2026-10-30T20:00:00+00:00")
    g2=dict(article("Google weighs Golden Dome participation","2026-11-02T20:00:00+00:00"),source="Bloomberg")
    assert eligible("golden_dome",g1,dt.datetime(2026,11,3,tzinfo=dt.timezone.utc))
    assert semantic_pair("golden_dome",g1,g2)
    assert semantic_id("golden_dome",g1)==semantic_id("golden_dome",g2)
    assert semantic_id("golden_dome",g1)!=semantic_id("golden_dome",article("Google signs contract for Golden Dome data security","2026-10-30T20:00:00+00:00"))
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
    delayed2=article("Rocket Lab Neutron maiden flight delayed until 2027","2026-10-22T20:00:00+00:00")
    broker=article("Citizens lowers Rocket Lab target on Neutron 2027 delay","2026-10-22T20:00:00+00:00")
    delayed_2028=article("Rocket Lab Neutron maiden flight delayed until 2028","2026-10-22T20:00:00+00:00")
    assert semantic_id("rocketlab",delayed1)==semantic_id("rocketlab",delayed2)
    assert semantic_id("rocketlab",delayed1)!=semantic_id("rocketlab",delayed_2028)
    assert semantic_id("rocketlab",delayed1)!=semantic_id("rocketlab",broker)
    assert kind("rocketlab",delayed2["title"])=="development_delay"
    assert kind("rocketlab",broker["title"])=="analyst"
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
