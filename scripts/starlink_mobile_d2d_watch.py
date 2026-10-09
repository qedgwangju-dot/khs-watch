#!/usr/bin/env python3
"""Starlink Mobile / US direct-to-device competition: fail-closed Telegram watch.

This watcher keeps the 2026-07 T-Mobile->Grain 800 MHz FCC approval separate
from the still-pending 2026-10 Grain->SpaceX license assignment. News RSS is
discovery, not a regulatory docket or proof of a completed acquisition.
"""
from __future__ import annotations
import datetime as dt
import email.utils
import hashlib
import html
from html.parser import HTMLParser
import json
import os
from pathlib import Path
import re
import socket
import time
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode, urlsplit
from urllib.request import Request, urlopen
import xml.etree.ElementTree as ET
from zoneinfo import ZoneInfo

ROOT=Path(__file__).resolve().parents[1]
STATE=ROOT/"data/starlink_mobile_d2d_watch_state.json"
PENDING=ROOT/"out/starlink_mobile_d2d_watch_pending.json"
ALERT=ROOT/"out/starlink_mobile_d2d_watch_telegram.txt"
SUMMARY=ROOT/"out/starlink_mobile_d2d_watch_status.md"
NOW=dt.datetime.now(dt.timezone.utc)
KST=ZoneInfo("Asia/Seoul")
HEADER="📡 Starlink Mobile·미국 위성-휴대전화 직접통신 감시"
RECENT=dt.timedelta(hours=84)
MAX_ITEMS=4
AGENT="Mozilla/5.0 (compatible; khs-starlink-mobile-watch/1.0)"
SOURCES=(
 ("SpaceX 공식 발표","https://www.spacex.com/updates/starship-moon-announcement",("BUILDING THE WORLD","800 MHz","14 megahertz")),
 ("Grain Management 매각 공식 발표","https://graingp.com/grain-management-announces-definitive-agreement-to-sell-nationwide-800-mhz-spectrum-portfolio-to-spacex/",("SpaceX","800 MHz","FCC approval")),
 ("Grain Management 배포 보도자료","https://www.prnewswire.com/news-releases/grain-management-announces-definitive-agreement-to-sell-nationwide-800-mhz-spectrum-portfolio-to-spacex-302902974.html",("SpaceX","800 MHz","FCC approval")),
 ("AT&T·T-Mobile·Verizon 합작법인 공식 발표","https://about.att.com/story/2026/jv-help-end-dead-zones.html",("October 01, 2026","AT&T","Verizon")),
 ("T-Mobile 주파수 매각 공식 발표","https://www.t-mobile.com/news/business/t-mobile-completes-sale-of-800-mhz-spectrum-portfolio-to-grain-management",("Grain","800","2026")),
 ("AT&T·AST SpaceMobile 상업계약 공식 발표","https://about.att.com/story/2024/ast-spacemobile-commercial-agreement.html",("AST SpaceMobile","2030")),
)
FCC_JULY="https://docs.fcc.gov/public/attachments/DA-26-653A1.pdf"
FCC_JAN="https://docs.fcc.gov/public/attachments/DOC-417881A1.pdf"
OFFICIAL_BASE=(
 ("[거래 계약·승인 대기]","SpaceX와 Grain Management가 전국 단위 800MHz 면허 묶음(시장별 최대 14MHz의 쌍방향 주파수)을 인수하는 계약을 2026년 10월 8일 발표했습니다. Grain→SpaceX 이전은 FCC 승인 대기이며 거래 완료가 아닙니다.","https://graingp.com/grain-management-announces-definitive-agreement-to-sell-nationwide-800-mhz-spectrum-portfolio-to-spacex/"),
 ("[기존 주파수 이전과 구분]","FCC가 2026년 7월 1일 승인한 거래는 T-Mobile→Grain 800MHz 이전 및 역방향 600MHz 교환입니다. 이번 Grain→SpaceX 거래에 그 승인을 적용하지 않습니다.",FCC_JULY),
 ("[위성망 승인과 구분]","FCC 2026년 1월 발표는 Gen2 위성 7,500기 추가 승인(총 15,000기)입니다. 위성망 승인과 800MHz 면허 이전 승인을 합쳐 해석하지 않습니다.",FCC_JAN),
 ("[통신사 대응]","AT&T·T-Mobile·Verizon의 위성-휴대전화 직접통신 합작법인은 2026년 10월 1일 출범을 발표했습니다. 3사는 기존 위성통신 협력계약을 유지할 수 있습니다.","https://about.att.com/story/2026/jv-help-end-dead-zones.html"),
 ("[AST SpaceMobile 연결]","AST SpaceMobile(ASTS)은 AT&T와 2030년까지 이어지는 상업계약이 있고 Verizon과도 상업계약을 발표했습니다. 경쟁사 신사업 진입이 이 기존 계약의 즉시 해지를 의미하지 않습니다.","https://about.att.com/story/2024/ast-spacemobile-commercial-agreement.html"),
)
TRADE_PRICE_NOTE="SpaceX-Grain 거래금액: 당사자 공식 발표에서 미공개. 외신 추정액을 확정 계약금으로 사용하지 않습니다."
# Existing October 2026 facts are a baseline, not novel future FCC approvals.
# In particular, do NOT seed license:grain_spacex_800:fcc_approval or :close.
KNOWN_BASELINE_KEYS=(
 "license:grain_spacex_800:agreement",
 "fcc:gen2_15000:permission",
 "fcc:2ghz:permission",
 "carriers:att_tmus_vz_joint_venture:venture",
 "asts:att_verizon_contract:supply",
)
NOISE=re.compile(r"lawsuit|class action|option volume|price target|buy rating|stock split|earnings preview|crypto|celebrity|trump coin|meme stock",re.I)
TRUSTED=(
 "Reuters","Financial Times","The Wall Street Journal","Bloomberg",
 "The Verge","SpaceNews","Via Satellite","AP News","Associated Press",
 "CNBC","Barron's","MarketWatch","Fierce Network","Fierce Wireless",
 "IEEE","TechCrunch","Reuters","연합뉴스","전자신문","한국경제","서울경제",
 "ZDNet","Axios","Ars Technica",
)
STOP=set(("spacex starlink mobile satellite wireless carriers carrier direct spectrum mhz ghz "
          "fcc us america united states company service phone smartphones device devices "
          "telecom satellites network announces announced say says after with from under "
          "has a an of to its the this will new deal following agreement news stock stocks "
          "million billion how expand expansion launch launches more is for by and ").split())
TOKEN=re.compile(r"[a-z0-9]+")
NO_CHANGE=re.compile(r"what to know|how shares moved|stock plunges|stocks drop|stock slides|"
                     r"why shares|analyst says|investors react|sector outlook|opinion",re.I)

TOPICS={
 "license": {
  "title":"[주파수·인허가] Grain→SpaceX 800MHz",
  "queries":(
    '"SpaceX" "Grain" ("800 MHz" OR spectrum OR FCC) when:4d',
    '"SpaceX" "800 MHz" (approval OR closes OR blocked OR contract) when:4d',
    'site:fcc.gov "SpaceX" "Grain" "800 MHz" when:10d',
  ),
  "meaning":"면허 이전 승인·거래 종결 후 위성망과 지상망 연결, 가입자 전환율·평균판매단가가 실제 매출을 좌우합니다.",
  "risk":"FCC 이전 승인 지연, 지상 기지국 투자와 건물 내부 품질 검증 지연",
  "indicator":"FCC WT 사건번호·면허 양도 승인·거래 종결 공시·실내 통화 품질",
 },
 "fcc": {
  "title":"[위성·FCC] Gen2·2GHz 직접통신",
  "queries":(
    '"SpaceX" ("FCC" OR authorization) ("satellites" OR "2 GHz") when:4d',
    '"Starlink Mobile" (Gen2 OR 2GHz OR FCC OR capacity) when:4d',
  ),
  "meaning":"허가된 위성 기수와 실제 운용 기수·단말 호환성은 다릅니다. 상용 가입자와 단말당 트래픽을 확인합니다.",
  "risk":"발사·주파수 간섭·위성 용량·단말 호환성과 통신품질 인증 지연",
  "indicator":"FCC 허가 범위·실제 발사/가동 기수·휴대전화 속도·전파 간섭",
 },
 "carriers": {
  "title":"[기존 통신사] AT&T·T-Mobile·Verizon 합작법인",
  "queries":(
    '"AT&T" "Verizon" "T-Mobile" (satellite OR joint venture OR direct to device) when:4d',
    '"satellite joint venture" (Paul Roth OR AT&T OR Verizon) when:4d',
  ),
  "meaning":"합작법인 지분투자·주파수 공동 활용과 기존 가입자 유지, 위성망 도매·소매 매출을 구분합니다.",
  "risk":"경쟁법·주파수 공유 규제, 각 회사 기존 위성 협력사와의 중복 투자",
  "indicator":"법인 투자액·신규 계약 주체·가입자 해지율·월 가입자당 매출",
 },
 "asts": {
  "title":"[경쟁 위성기업] AST SpaceMobile(ASTS)",
  "queries":(
    '"AST SpaceMobile" (AT&T OR Verizon OR satellite OR commercial) when:4d',
    '"AST SpaceMobile" (SpaceX OR Starlink OR FCC OR BlueBird) when:4d',
  ),
  "meaning":"기존 AT&T·Verizon 계약의 실제 사용량·도매수입과 BlueBird 상용서비스 가동 시점을 구분합니다.",
  "risk":"위성 발사·안테나 전력·스펙트럼 상호운용성·서비스 품질 인증 지연",
  "indicator":"가동 BlueBird 기수·상용 가입자당 사용량·인식 매출·계약 연장",
 },
 "ground": {
  "title":"[지상망·설비투자] 기지국·철탑·전송망",
  "queries":(
    '"SpaceX" ("cell towers" OR "base stations" OR terrestrial OR fiber) when:4d',
    '"Starlink Mobile" (tower lease OR ground infrastructure OR cellular infrastructure) when:4d',
  ),
  "meaning":"실제 기지국 임차·안테나·광섬유 전송망·관제 계약이 나와야 철탑 및 장비 업체 매출로 연결됩니다.",
  "risk":"장소·송전·임차 비용, 통신 음영지역과 건물 실내 품질 개선 속도",
  "indicator":"계약 철탑 수·기지국 개통 수·가구당 평균판매단가·설비투자액",
 },
}
LABELS={
 "agreement":"계약 발표(규제승인·거래 종결 미확인)",
 "fcc_approval":"FCC가 해당 800MHz 이전을 승인했다는 보도(공식 결정문 직접 확인 전 미확정)",
 "close":"해당 800MHz 거래 종결 보도(공시·당사자 원문 직접 확인 전 미확정)",
 "deny":"해당 800MHz 승인 거부·지연 보도(결정문 직접 확인 전 미확정)",
 "permission":"별도의 위성망·2GHz FCC 승인·조정 보도(800MHz 매각 승인과 다름)",
 "new_service":"상용서비스·위성망 추가 구축 보도(실제 개통·고객 수 별도 확인)",
 "venture":"합작법인 확대·협력 발표(신규 매출과 다름)",
 "supply":"위성 공급·계약·발사 보도(검수 매출과 다름)",
 "tower":"지상망·철탑 계약/투자 보도(규모 확인 필요)",
}
MONTHS={"Jan":"01","Feb":"02","Mar":"03","Apr":"04","May":"05","Jun":"06",
        "Jul":"07","Aug":"08","Sep":"09","Oct":"10","Nov":"11","Dec":"12"}

class HTMLText(HTMLParser):
 def __init__(self):super().__init__();self.parts=[];self.hide=0
 def handle_starttag(self,tag,attrs):
  if tag in ("script","style","noscript"):self.hide+=1
 def handle_endtag(self,tag):
  if tag in ("script","style","noscript") and self.hide:self.hide-=1
 def handle_data(self,text):
  if not self.hide and text.strip():self.parts.append(text)

def http_read(url:str,attempts:int=2)->bytes:
 if urlsplit(url).scheme!="https":raise ValueError("HTTPS only")
 error=None
 for i in range(attempts):
  req=Request(url,headers={"User-Agent":AGENT,"Accept":"text/html,application/rss+xml,*/*"})
  try:
   with urlopen(req,timeout=20) as response:
    final=urlsplit(response.geturl())
    if final.scheme!="https":raise RuntimeError("unexpected non-HTTPS redirect")
    data=response.read(2500000)
    if not data:raise RuntimeError("empty response")
    return data
  except (HTTPError,URLError,TimeoutError,socket.timeout,RuntimeError) as e:
   error=e
   if isinstance(e,HTTPError) and e.code not in (429,500,502,503,504):break
   if i+1<attempts:time.sleep(2**i)
 raise RuntimeError(f"source unavailable ({type(error).__name__})")

def verified_primary_sources()->tuple[list[str],list[str]]:
 verified=[]
 failed=[]
 for name,url,markers in SOURCES:
  try:
   raw=http_read(url)
   parser=HTMLText()
   parser.feed(raw.decode("utf-8",errors="replace"))
   txt=" ".join(parser.parts)
   txt=html.unescape(re.sub(r"\s+"," ",txt)).casefold()
   if not all(marker.casefold() in txt for marker in markers):
    raise ValueError("required exact company/date/frequency markers absent")
   verified.append(name)
  except Exception as e:
   failed.append(f"{name}: {type(e).__name__}")
 return verified,failed

def rss(query:str)->list[dict]:
 params=urlencode({"q":query,"hl":"en","gl":"US","ceid":"US:en"})
 root=ET.fromstring(http_read("https://news.google.com/rss/search?"+params))
 rows=[]
 for e in root.findall(".//item"):
  title=html.unescape(re.sub(r"<[^>]+>"," ",e.findtext("title") or "")).strip()
  url=(e.findtext("link") or "").strip()
  src=e.find("source")
  source=(src.text or "").strip() if src is not None else ""
  if not title or not url.startswith("https://"):continue
  try:
   date=email.utils.parsedate_to_datetime(e.findtext("pubDate") or "")
   if not date.tzinfo:date=date.replace(tzinfo=dt.timezone.utc)
   date=date.astimezone(dt.timezone.utc)
  except Exception:continue
  rows.append({"title":title,"url":url,"publisher":source,"pub":date})
 return rows

def independent_publisher(item:dict)->bool:
 # Google News merely tags publishers. A government-looking RSS source is not
 # direct verification of an FCC proceeding and is excluded from media pairs.
 s=item["publisher"].lower()
 if any(x in s for x in ("fcc","federal communications commission","prnewswire",
                       "business wire","globenewswire","spacex","grain management")):
  return False
 return any(x.lower() in s for x in TRUSTED)

def stem_title(title:str)->str:
 return re.sub(r"\s+[-|]\s+[^-|]{1,60}$","",title).lower().strip()

def stage(topic:str,title:str)->str|None:
 t=stem_title(title)
 if NOISE.search(t) or NO_CHANGE.search(t):return None
 if topic=="license":
  if not re.search(r"spacex|starlink",t) or not re.search(r"grain|800[\s-]*mhz",t):return None
  if not re.search(r"spectrum|license|800[\s-]*mhz|grain",t):return None
  # This is NOT the old T-Mobile -> Grain deal.
  if re.search(r"t-mobile (?:sells|sold|transfers?|swaps?|completes).{0,60}grain",t):return None
  if re.search(r"fcc (?:approves?|approved|authori[sz]es?|grants?)",t):
   if re.search(r"(?:grain|800[\s-]*mhz).{0,55}(?:license|transfer|sale|acquisit|assign|deal)|"
                r"(?:license|transfer|sale|acquisit|assign|deal).{0,55}(?:grain|800[\s-]*mhz)",t):
    if not re.search(r"(15,?000|7500|7,?500|gen2).*satellit",t):
     return "fcc_approval"
  if re.search(r"reject|denied|block|investigation|delay",t):return "deny"
  if re.search(r"complet(?:e|ed|ion)|clos(?:e|ed|ing) (?:the )?(?:deal|transaction|purchase)|"
               r"finaliz(?:e|ed)|sale closed",t):
   return "close"
  if re.search(r"acquir|buy|bought|purchas|agreement|deal|signs",t):return "agreement"
  return None
 if topic=="fcc":
  if not re.search(r"spacex|starlink",t):return None
  if not re.search(r"fcc|regulator|license|approved|2 ?ghz|gen2",t):return None
  if re.search(r"approve|approved|authorization|permit|fcc|application|modification",t):
   return "permission"
  if re.search(r"launch|deploy|commercial|test",t):return "new_service"
  return None
 if topic=="carriers":
  if not re.search(r"at&t|verizon|t-mobile",t):return None
  if not re.search(r"joint venture|venture|satellite|d2d|direct.to.device",t):return None
  return "venture"
 if topic=="asts":
  if not re.search(r"ast spacemobile|bluebird|asts",t):return None
  if not re.search(r"contract|deal|satellite|commercial|service|verizon|at&t|launch",t):return None
  return "supply"
 if topic=="ground":
  if not re.search(r"spacex|starlink",t) or not re.search(r"tower|terrestrial|fiber|base station|ground",t):return None
  if not re.search(r"deal|lease|contract|invest|capex|construction|build|deploy|plan",t):return None
  return "tower"
 return None

def keywords(title:str)->set[str]:
 s=re.sub(r"(\d+)\s*(mhz|ghz)",r"\1\2",stem_title(title))
 return {w for w in TOKEN.findall(s) if len(w)>=3 and w not in STOP}

def match_articles(a:dict,b:dict)->bool:
 if a["publisher"].strip().lower()==b["publisher"].strip().lower():return False
 if abs((a["pub"]-b["pub"]).total_seconds())>72*3600:return False
 x,y=keywords(a["title"]),keywords(b["title"])
 common=x&y
 # Shared issuer names and the same event-specific objects, not generic SpaceX.
 return len(common)>=2 and len(common)/max(1,len(x|y))>=0.24

def event_id(category:str,status:str,title:str)->str:
 t=stem_title(title)
 if category=="license":return f"license:grain_spacex_800:{status}"
 if category=="fcc":
  if re.search(r"15,?000|7500|7,?500",t):return f"fcc:gen2_15000:{status}"
  if re.search(r"2[\s-]*ghz",t):return f"fcc:2ghz:{status}"
 if category=="carriers" and re.search(r"joint venture|venture",t):
  return f"carriers:att_tmus_vz_joint_venture:{status}"
 if category=="asts" and re.search(r"verizon|at&t",t):
  return f"asts:att_verizon_contract:{status}"
 if category=="ground" and re.search(r"tower|terrestrial",t):
  return f"ground:starlink_terrestrial:{status}"
 # To allow different deployments/contracts, use stable material headwords,
 # without date or publisher-specific wording.
 terms=sorted(keywords(title))
 return f"{category}:{status}:"+hashlib.sha256("|".join(terms).encode()).hexdigest()[:14]

def bootstrap()->str:
 sections=[HEADER, "기준: "+NOW.astimezone(KST).strftime("%Y-%m-%d %H:%M KST"),
  "최초 1회 정책·사업 기준선입니다. 과거 기사를 새 수주나 승인으로 알리는 것이 아닙니다."]
 for heading,meaning,url in OFFICIAL_BASE:
  sections.append("\n"+heading+"\n• "+meaning+"\n• 원문: "+url)
 sections += [
  "\n[경제성·실패 경로]\n• "+TRADE_PRICE_NOTE,
  "• 위성 직접통신만으로 도심 실내망 구축이 완료되는 것은 아닙니다. 지상 기지국·전송망·요금제·가입자 확보를 따로 추적합니다.",
  "• 먼저 볼 지표: Grain→SpaceX FCC 승인, 실제 기지국·철탑 계약, ASTS 가동률, AT&T·VZ·TMUS 가입자 이탈률.",
  "• 매출 구분: 주파수 매입은 자산취득이며 장비·건설업체 매출과 통신 가입자 반복매출을 혼합하지 않습니다."
 ]
 return "\n".join(sections).strip()+"\n"

def render(topic:str,status:str,item:dict,pair:dict)->str:
 meta=TOPICS[topic]
 timestamp=item["pub"].astimezone(KST).strftime("%Y-%m-%d %H:%M KST")
 return "\n".join([
  meta["title"],
  "• 사건 단계: "+LABELS[status],
  "• 제목: "+item["title"],
  "• 검증: 서로 다른 2개 언론 보도의 같은 사건 교차확인, 정부·계약당사자 최종 원문은 별도 확인 필요",
  "• 시각: "+timestamp+" | 매체: "+item["publisher"]+" / "+pair["publisher"],
  "• 매출 연결: "+meta["meaning"],
  "• 실패 경로: "+meta["risk"],
  "• 먼저 볼 지표: "+meta["indicator"],
  "• "+TRADE_PRICE_NOTE,
  "• 원문: "+item["url"],
  "• 원문: "+pair["url"],
 ])

def load_state()->tuple[dict,bool]:
 if not STATE.exists():return {"version":1,"created_at":NOW.isoformat(),"seen":{}},True
 try:
  s=json.loads(STATE.read_text(encoding="utf-8"))
  if not isinstance(s,dict) or not isinstance(s.get("seen"),dict):raise ValueError("schema")
  if any(not isinstance(k,str) or not isinstance(v,str) for k,v in s["seen"].items()):raise ValueError("dedup schema")
  return s,False
 except Exception as exc:
  raise RuntimeError("기존 중복방지 상태 손상: 알림 대신 실패 처리(수동 복구 필요)") from exc

def collect(rss_fn=rss)->tuple[dict,list[str],int]:
 collected={name:{} for name in TOPICS}
 errors=[]
 good=0
 for name,topic in TOPICS.items():
  for query in topic["queries"]:
   try:
    items=rss_fn(query)
    good+=1
    for item in items:
     age=NOW-item["pub"]
     if age>dt.timedelta(days=7) or age<dt.timedelta(minutes=-15):continue
     sta=stage(name,item["title"])
     if not sta:continue
     k=f'{item["publisher"].lower()}|{stem_title(item["title"])}'
     collected[name][k]=(sta,item)
   except Exception as exc:
    errors.append(f"{name}: {type(exc).__name__}")
 return collected,errors,good

def choose_events(group:dict,seen:dict,bootstrap_run:bool,force:bool=False)->tuple[list[str],dict]:
 alerts=[]
 updated=dict(seen)
 for topic,candidates in group.items():
  ordered=sorted(candidates.values(),key=lambda z:z[1]["pub"],reverse=True)
  for status,item in ordered:
   # A single RSS headline is not a license, signed contract, or FCC approval.
   if not independent_publisher(item):continue
   eid=event_id(topic,status,item["title"])
   if eid in updated and not force:continue
   peers=[p for s,p in ordered if s==status and
          independent_publisher(p) and match_articles(item,p)]
   if not peers:continue
   if bootstrap_run:
    updated[eid]=NOW.isoformat()
    continue
   if NOW-item["pub"]>RECENT:continue
   alerts.append((item["pub"],eid,render(topic,status,item,peers[0])))
   updated[eid]=NOW.isoformat()
 alerts.sort(key=lambda z:z[0],reverse=True)
 # Do not lose validated unreported events; keep them unread for next cycle.
 chosen=alerts[:MAX_ITEMS]
 for _,eid,_ in alerts[MAX_ITEMS:]:
  updated.pop(eid,None)
 return [x[2] for x in chosen],updated

def test()->int:
 assert stage("license","SpaceX to buy Grain's 800 MHz spectrum, subject to FCC approval")=="agreement"
 assert stage("license","FCC approves 15,000 SpaceX satellites for mobile, 800 MHz Grain deal pending")!="fcc_approval"
 assert stage("license","T-Mobile completes transfer of 800MHz licenses to Grain Management") is None
 assert stage("license","FCC approves Grain-to-SpaceX 800 MHz spectrum license transfer")=="fcc_approval"
 assert stage("license","SpaceX completes Grain 800MHz spectrum deal")=="close"
 assert stage("license","SpaceX's Grain 800 MHz spectrum purchase is delayed")=="deny"
 assert stage("fcc","FCC approves SpaceX 15,000 Gen2 satellites in 2GHz")=="permission"
 assert event_id("license","agreement","SpaceX to buy Grain 800MHz") == event_id("license","agreement","SpaceX acquires Grain 800 MHz spectrum")
 a={"title":"SpaceX and Grain sign nationwide 800 MHz spectrum deal", "publisher":"Reuters","pub":NOW,"url":"https://a.example"}
 b={"title":"Grain spectrum 800MHz agreement with SpaceX across the US", "publisher":"Financial Times","pub":NOW,"url":"https://b.example"}
 c={"title":a["title"],"publisher":"Reuters","pub":NOW,"url":"https://c.example"}
 assert match_articles(a,b) and not match_articles(a,c)
 assert not independent_publisher({"publisher":"FCC"})
 assert not independent_publisher({"publisher":"PRNewswire"})
 assert not independent_publisher({"publisher":"Unknown stock blog"})
 records={"license":{"a":("agreement",a),"b":("agreement",b)}}
 first,updated=choose_events(records,{},True)
 assert not first and "license:grain_spacex_800:agreement" in updated
 second,_=choose_events(records,updated,False)
 assert not second
 other,post=choose_events(records,{},False)
 assert len(other)==1 and "정부·계약당사자 최종 원문" in other[0]
 assert "거래금액: 당사자 공식 발표에서 미공개" in bootstrap()
 assert "2026년 7월 1일" in bootstrap()
 assert "2026년 10월 1일" in bootstrap()
 assert STATE!=PENDING!=ALERT
 assert "license:grain_spacex_800:agreement" in KNOWN_BASELINE_KEYS
 assert "license:grain_spacex_800:fcc_approval" not in KNOWN_BASELINE_KEYS
 assert "license:grain_spacex_800:close" not in KNOWN_BASELINE_KEYS
 print("starlink_mobile_d2d_self_test=ok approvals_separated=1 government_rss_excluded=1 media_duo=1 no_duplicates=1 known_baseline=1")
 return 0

def main()->int:
 if os.environ.get("STARLINK_D2D_SELF_TEST")=="1":return test()
 state,initial=load_state()
 official,failed=verified_primary_sources()
 groups,errors,good=collect()
 if good<5:
  raise RuntimeError(f"뉴스조회 불충분: {good} 성공·{len(errors)} 실패; 상태 유지")
 # Government/legal/official primary sources are checked independently of RSS.
 # On startup insist on two real corporate originals; do not send cached claims.
 if len(official)<2:
  raise RuntimeError(f"공식 원문 직접 접근 {len(official)}곳: 알림 차단. {failed}")
 force=os.getenv("FORCE_NOTIFY","").strip().lower() in ("true","1","yes")
 events,next_seen=choose_events(groups,state["seen"],initial,force)
 # Idempotent migration fixes an original bug: the first broadcast delivered
 # known October headlines while an empty dedup state could replay them later.
 # Never pre-mark the still-pending FCC assignment approval or sale closing.
 seeded=0
 for k in KNOWN_BASELINE_KEYS:
  if k not in next_seen:
   next_seen[k]=NOW.isoformat()
   seeded+=1
 state["seen"]=next_seen
 # Avoid 48 contentless commits/day and related repo push-trigger storms.
 if initial or events or seeded:
  state["updated_at"]=NOW.isoformat()
  state["official_sources_verified"]=official
 if initial:
  report=bootstrap()
 elif events:
  report=HEADER+"\n기준: "+NOW.astimezone(KST).strftime("%Y-%m-%d %H:%M KST")+"\n\n"+"\n\n".join(events)+"\n"
 else:report=""
 ALERT.parent.mkdir(parents=True,exist_ok=True)
 if report:ALERT.write_text(report,encoding="utf-8")
 else:ALERT.unlink(missing_ok=True)
 PENDING.write_text(json.dumps(state,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
 SUMMARY.write_text("\n".join([
  "# Starlink Mobile·미국 이동통신 경쟁 감시",
  f"- 점검 시각: {NOW.astimezone(KST).isoformat()}",
  f"- 공식 발표 원문 검증: {len(official)}/{len(SOURCES)} ({', '.join(official)})",
  f"- 뉴스 피드 정상: {good}/{sum(len(x['queries']) for x in TOPICS.values())}",
  f"- 뉴스 피드 장애: {len(errors)}",
  f"- 최초 기준선: {initial}, 이번 알림 사건: {len(events)}",
  "- FCC 2026-07 T-Mobile→Grain 승인과 2026-10 Grain→SpaceX 승인 대기를 혼동하지 않음",
  "- 언론 교차 보도는 정부 승인·거래 종결로 확정하지 않음",
  "- 중복 기록은 Telegram 전송 성공 뒤에만 반영",
  ""
 ]),encoding="utf-8")
 print(f"starlink_mobile_d2d_scan=ok official_verified={len(official)} rss_ok={good} initial={initial} events={len(events)} alert={bool(report)}")
 return 0

if __name__=="__main__":
 raise SystemExit(main())
