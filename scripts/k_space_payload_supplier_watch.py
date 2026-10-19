#!/usr/bin/env python3
"""Verified commercial Korea space-AI payload and SpaceX supplier alert.

Standalone watcher. Never treat cooperation, proposed launch, and production
orders as the same financial event. Existing notices are one-time baseline
only. False positive/silent state loss must fail closed.
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
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from zoneinfo import ZoneInfo

ROOT=Path(__file__).resolve().parents[1]
STATE=ROOT/"data/k_space_payload_supplier_state.json"
PENDING=ROOT/"out/k_space_payload_supplier_pending.json"
ALERT=ROOT/"out/k_space_payload_supplier_telegram.txt"
STATUS=ROOT/"out/k_space_payload_supplier_status.md"
NOW=dt.datetime.now(dt.timezone.utc)
KST=ZoneInfo("Asia/Seoul")
TITLE="🛰️ 국내 위성 AI·SpaceX 부품 공급망 감시"
AGENT="Mozilla/5.0 (compatible; khs-payload-supplier-watch/1.0)"
MAX_NEWS_AGE=dt.timedelta(days=8)
LIVE_WINDOW=dt.timedelta(hours=84)

COMPANY_SOURCES=(
 ("텔레픽스 공식 사업·보도","https://www.telepix.ai/news-eng",("telepix","space")),
 ("켄코아 미국 자회사 공식 사업실적","https://kencoaaerospace.com/markets/space-systems-exploration/",("kencoa","spacex dragon")),
)
BASELINE_LINKS=(
 "https://www.yna.co.kr/view/AKR20260723040400017",
 "https://www.yna.co.kr/view/AKR20260928042100017",
 "https://www.yna.co.kr/view/AKR20260529061900017",
 "https://www.unicornfactory.co.kr/article/2026062511063330956",
 "https://kencoaaerospace.com/markets/space-systems-exploration/",
 "https://www.yna.co.kr/view/AKR20251030045100017",
)
KEY_BASELINE=(
 "telepix_contract:antaris:signed",
 "telepix_contract:huleo:signed",
 "telepix_contract:skyserve:signed",
 "telepix_flight:antaris:planned:2027",
 "telepix_flight:chouette:planned:2027",
 "telepix_flight:bellatrix:planned:2028",
 "kencoa_supplier:spacex:confirmed_supply",
 "kencoa_supplier:blue_origin:confirmed_supply",
 "lk_samyang:startracker:orbital_verified",
)
TRUSTED=(
 "연합뉴스","이데일리","조선비즈","머니투데이","뉴스핌",
 "ZDNet","한국경제","매일경제","전자신문","동아사이언스",
 "DIGITIMES","Reuters","Bloomberg","SpaceNews","Payload",
 "Financial Times","Aviation Week","The Korea Economic Daily",
)
STOP=set((
 "telepix kencoa aerospace space spacex satellite satellites "
 "ai optical payload korea korean global export contract wins 2026 "
 "2027 2028 the a an for to with and new of on in from company "
 "companies plans planning launches spaceflight rocket startup "
 "suppliers future new upcoming"
).split())
NOISE=re.compile(r"주가\s*급등|주가\s*하락|목표주가|class action|options activity|insider sale|why shares|"
                 r"stock soars|stock jumps|analyst rating|tesla shares|meme",re.I)

QUERIES={
 "telepix_contract":(
  '"TelePIX" ("Antaris" OR "SkyServe" OR "HULEO" OR "Remred" OR contract) when:7d',
  '텔레픽스 (안타리스 OR 스카이서브 OR 렘레드 OR 헝가리 OR 수출 OR 계약) when:7d',
 ),
 "telepix_flight":(
  '"TelePIX" ("JANUS-2" OR "Chouette" OR "Bellatrix" OR "2027" OR "2028") when:7d',
  '텔레픽스 (슈에뜨 OR 재너스 OR 벨라트릭스 OR 광학탑재체 OR 발사 OR 실증) when:7d',
 ),
 "kencoa_supplier":(
  '"Kencoa" ("SpaceX" OR "Blue Origin" OR titanium OR supply OR contract) when:7d',
  '켄코아에어로 (스페이스X OR 블루오리진 OR 티타늄 OR 부품 OR 공급 OR 수주) when:7d',
 ),
 "kencoa_roadster":(
  '"Kencoa" "Roadster" (thrusters OR contract OR supplier) when:10d',
  '켄코아 (로드스터 OR 추력기 OR 테슬라) (납품 OR 공급 OR 계약) when:10d',
 ),
 "lk_samyang":(
  'LK삼양 텔레픽스 (별추적기 OR 양산 OR 공급 OR 수주) when:14d',
  '"LK Samyang" "TelePIX" (production OR star tracker OR contract) when:14d',
 ),
}
TERM={
 "telepix_contract":re.compile(r"telepix|텔레픽스",re.I),
 "telepix_flight":re.compile(r"telepix|텔레픽스",re.I),
 "kencoa_supplier":re.compile(r"kencoa|켄코아",re.I),
 "kencoa_roadster":re.compile(r"kencoa|켄코아",re.I),
 "lk_samyang":re.compile(r"(lk\s*삼양|lk[\s-]*samyang|엘케이삼양).*(telepix|텔레픽스)|(telepix|텔레픽스).*(lk\s*삼양|lk[\s-]*samyang|엘케이삼양)",re.I),
}
PARTNERS={
 "antaris":re.compile(r"antaris|안타리스",re.I),
 "skyserve":re.compile(r"skyserve|스카이서브",re.I),
 "huleo":re.compile(r"huleo|remred|헝가리|렘레드",re.I),
 "bellatrix":re.compile(r"bellatrix|벨라트릭스",re.I),
 "chouette":re.compile(r"chouette|슈에뜨",re.I),
 "spacex":re.compile(r"spacex|스페이스.?x|스페이스엑스",re.I),
 "blue_origin":re.compile(r"blue.?origin|블루오리진",re.I),
 "roadster":re.compile(r"roadster|로드스터",re.I),
}
SIGNED=re.compile(r"contract|signed|deal|award|purchase order|sales agreement|수출\s*계약|공급\s*계약|"
                  r"계약\s*체결|수주|공급망\s*등록|납품\s*계약",re.I)
SUPPLIER=re.compile(r"supplies|supplying|supplier|supply agreement|deliver(?:ing|y|ed)?|"
                    r"공급|납품|수주|원소재|티타늄",re.I)
TEST=re.compile(r"flown|demonstration|orbital test|flight|launch|validate|"
                r"발사|실증|검증|운용|탑재",re.I)
NEXT=re.compile(r"2027|2028|2030|2029")
CANCEL=re.compile(r"cancel|terminated|delayed|postponed|failure|failed|"
                  r"연기|취소|해지|실패|재계약|추가\s*수주|확대|"
                  r"completed|operational|actual launch|상용화|양산",re.I)

class Readable(HTMLParser):
 def __init__(self):super().__init__();self.block=0;self.data=[]
 def handle_starttag(self,tag,attrs):
  if tag in ("script","style","noscript"):self.block+=1
 def handle_endtag(self,tag):
  if tag in ("script","style","noscript") and self.block:self.block-=1
 def handle_data(self,data):
  if not self.block and data.strip():self.data.append(data)

def plain(raw:bytes)->str:
 p=Readable();p.feed(raw.decode("utf-8",errors="replace"))
 return html.unescape(re.sub(r"\s+"," "," ".join(p.data))).strip()

def fetch(url:str,retries:int=2)->bytes:
 if urllib.parse.urlsplit(url).scheme!="https":raise ValueError("Secure HTTPS URL required")
 for retry in range(retries):
  req=urllib.request.Request(url,headers={"User-Agent":AGENT,"Accept":"text/html,application/rss+xml,*/*"})
  try:
   with urllib.request.urlopen(req,timeout=22) as resp:
    data=resp.read(2000000)
    if not data:raise RuntimeError("Empty source")
    return data
  except (urllib.error.HTTPError,urllib.error.URLError,TimeoutError,socket.timeout) as exc:
   if isinstance(exc,urllib.error.HTTPError) and exc.code not in (429,500,502,503,504):raise
   if retry>=retries-1:raise
   time.sleep(1+retry)

def official_check()->tuple[list[str],list[str]]:
 success=[];errors=[]
 for name,url,markers in COMPANY_SOURCES:
  try:
   content=plain(fetch(url)).lower()
   if not all(word.lower() in content for word in markers):
    raise ValueError("Expected primary-source markers missing")
   success.append(name)
  except Exception as e:errors.append(name+": "+type(e).__name__)
 return success,errors

def rss(query:str)->list[dict]:
 params=urllib.parse.urlencode({"q":query,"hl":"ko","gl":"KR","ceid":"KR:ko"})
 root=ET.fromstring(fetch("https://news.google.com/rss/search?"+params))
 items=[]
 for x in root.findall(".//item"):
  title=html.unescape(re.sub(r"<[^>]*>"," ",x.findtext("title") or "")).strip()
  url=(x.findtext("link") or "").strip()
  node=x.find("source")
  source=(node.text or "").strip() if node is not None else ""
  src_url=(node.get("url") or "") if node is not None else ""
  try:
   at=email.utils.parsedate_to_datetime(x.findtext("pubDate") or "")
   if at.tzinfo is None:at=at.replace(tzinfo=dt.timezone.utc)
   at=at.astimezone(dt.timezone.utc)
  except Exception:continue
  if title and url.startswith("https://"):
   items.append({"title":title,"source":source,"source_url":src_url,"url":url,"published":at})
 return items

def trustworthy(x:dict)->bool:
 s=x["source"].casefold()
 # Syndications, company press-release mirrors and article aggregators
 # must not count as independent journalism.
 if any(q in s for q in ("prnewswire","business wire","globenewswire","뉴스피드","newsis ai")):return False
 return any(q.casefold() in s for q in TRUSTED)

def partner(text:str)->str|None:
 for k,p in PARTNERS.items():
  if p.search(text):return k
 return None

def classify(group:str,title:str)->str|None:
 s=re.sub(r"\s+[-|]\s+[^-|]{1,50}$","",title).strip()
 if not TERM[group].search(s) or NOISE.search(s):return None
 p=partner(s)
 if group=="telepix_contract":
  if p not in ("antaris","skyserve","huleo"):return None
  if re.search(r"MOU|memorandum|업무협약",s,re.I):return None
  if re.search(r"(?:추가|신규)\s*(?:수주|계약|발주)|새(?:로운)?\s*계약|계약\s*(?:연장|갱신)|renewal|extension|expanded contract|new(?: follow-on)? contract|additional order",s,re.I):
   return f"telepix_contract:{p}:change"
  if SIGNED.search(s):return f"telepix_contract:{p}:signed"
  if CANCEL.search(s):return f"telepix_contract:{p}:change"
 if group=="telepix_flight":
  if not TEST.search(s):return None
  if PARTNERS["bellatrix"].search(s):p="bellatrix"
  elif PARTNERS["antaris"].search(s):p="antaris"
  elif PARTNERS["chouette"].search(s):p="chouette"
  else:return None
  y=NEXT.search(s)
  if CANCEL.search(s) and re.search(r"delay|postpone|연기|취소|failed|실패",s,re.I):
   phase="delayed"
  elif re.search(r"성공|completed|operational|발사\s*성공|in orbit",s,re.I):
   phase="flight_confirmed"
  else:phase="planned"
  if not y and phase=="planned":return None
  return f"telepix_flight:{p}:{phase}:{y.group(0) if y else 'date_pending'}"
 if group=="kencoa_supplier":
  if not SUPPLIER.search(s) and not (
    SIGNED.search(s) and re.search(r"부품|parts|components?|material|발사체|rocket",s,re.I)
  ):return None
  if PARTNERS["roadster"].search(s):return None  # Roadster needs direct signed evidence.
  if p not in ("spacex","blue_origin"):return None
  if re.search(r"(?:신규|추가|새로운)\s*(?:계약|수주|공급|발주)|new(?:ly signed)? contract|"
               r"signs? (?:new )?(?:supply )?contract|purchase order|contract award|"
               r"공급\s*계약\s*체결|계약\s*체결",s,re.I):
   phase="new_contract"
  elif CANCEL.search(s):
   phase="change"
  else:
   phase="confirmed_supply"
  return f"kencoa_supplier:{p}:{phase}"
 if group=="kencoa_roadster":
  # Any hypothetical Tesla Roadster supply requires first-party proof.
  if PARTNERS["roadster"].search(s) and SIGNED.search(s):
   return "kencoa_roadster:potential_supply" # Never auto-send as confirmation.
 if group=="lk_samyang":
  if re.search(r"양산\s*계약|양산\s*수주|mass.production|production contract",s,re.I):
   return "lk_samyang:startracker:production_contract"
  if TEST.search(s):return "lk_samyang:startracker:orbital_verified"
 return None

def signature(group:str,event:str,item:dict)->str:
 # Distinguish independent contract/flight milestones from cached articles;
 # never deduplicate signed contracts with test/mou phases.
 return f"{group}:{event}"

def independent_pair(group:str,event:str,a:dict,b:dict)->bool:
 if not trustworthy(a) or not trustworthy(b):return False
 if a["source"].casefold()==b["source"].casefold():return False
 if abs((a["published"]-b["published"]).total_seconds())>4*86400:return False
 # Both report the same named buyer, stage, and mission; not a generic "space AI"
 return classify(group,a["title"])==event and classify(group,b["title"])==event

def korean_summary(group:str,event:str)->tuple[str,str,str]:
 p=event.split(":")
 stage=p[2]
 if group=="telepix_contract":
  label={"antaris":"미국 Antaris","skyserve":"인도 SkyServe","huleo":"헝가리 HULEO"}[p[1]]
  return ("[위성 AI·해외 계약] "+label,
          "해외 고객 계약 관련 신규 보도입니다. 계약서·금액·실제 납품·매출 인식은 별도 공식 확인 전 확정하지 않습니다.",
          "고객 검수·발사 일정 지연과 AI 처리기 성능 검증, 계약 갱신 조건")
 if group=="telepix_flight":
  label={"antaris":"Antaris JANUS-2","chouette":"광학 탑재체 Chouette","bellatrix":"Bellatrix 초저궤도 협력"}[p[1]]
  return ("[발사·실증] "+label,
          f"보도에 등장한 {p[3]}년 목표·비행 상태 변경 후보입니다. 2027년 Antaris와 2028년 Bellatrix는 서로 다른 일정입니다.",
          "발사체 확보·탑재체 열/전력·방사선 신뢰성·인수시험 미달")
 if group=="kencoa_supplier":
  target="SpaceX" if p[1]=="spacex" else "Blue Origin"
  return ("[우주발사체·원소재 공급] 켄코아→"+target,
          "부품·원소재 공급 확대 관련 보도입니다. 실제 수주금액과 납품 대상·계열사 매출 구분이 필요합니다.",
          "원소재 가격·고온 신뢰성 검증·납기·품질보증·고객 발사일정 지연")
 if group=="lk_samyang":
  return ("[상장 공급망·광학] LK삼양·텔레픽스",
          "AI 별추적기 우주 실증과 신규 양산계약은 별개입니다. 새 계약을 확인한 후에만 확정 매출로 분류합니다.",
          "방사선 검증·광학 정렬·별 인식 정밀도·인수시험 지연")
 raise ValueError("Unapproved event for message")

def baseline()->str:
 source_lines="\n".join("• 원문: "+url for url in BASELINE_LINKS)
 return (
  TITLE+"\n기준: "+NOW.astimezone(KST).strftime("%Y-%m-%d %H:%M KST")+
  "\n※ 첫 1회 검증 기준선입니다. 과거 계약을 신규 수주로 알리는 것이 아닙니다.\n\n"
  "[텔레픽스·확정 계약]\n"
  "• 미국 Antaris: 4.8m급 광학 카메라+위성 AI 탑재체 수출계약. 2027년 JANUS-2 궤도 실증 목표.\n"
  "• 헝가리 HULEO: 고해상도 광학 카메라 수출계약. 금액은 수천만 달러 수준이라는 보도이며 정확한 계약대금은 미공개.\n"
  "• 인도 SkyServe: 위성 내 AI 모델 원격 탑재·운용 서비스 계약. 6개 이상 모델 확대는 검토 단계, 확정 발주 아님.\n\n"
  "[서로 다른 발사 일정]\n"
  "• 2027년 Antaris·광학 탑재체 실증 목표와 2028년 Bellatrix 초저궤도 협력 목표를 혼동하지 않습니다.\n"
  "• Bellatrix는 공동개발 업무협약 단계. 2028년 위성 발사 성공이나 매출 확정이 아닙니다.\n\n"
  "[켄코아·실제 공급과 별도 기술]\n"
  "• 켄코아 경영진은 SpaceX에 특수 티타늄 등 원소재를 공급한다고 공개 발언. 미국 자회사는 SpaceX Dragon 수행 이력을 공식 표기.\n"
  "• Tesla Roadster의 SpaceX 냉가스 추력기 시연은 별도 사실. 켄코아가 Roadster 추력기를 납품했다는 계약 증거는 확인되지 않았습니다.\n"
  "• LK삼양·텔레픽스 별추적기는 2025년 궤도 실증 완료, 본격 양산 수주는 별도 확인 필요.\n\n"
  "[선행지표·실패 경로]\n"
  "• 계약대금·고객 검수·2027년 발사·궤도상 소프트웨어 반복 사용료·켄코아 계열사별 실제 출하를 추적합니다.\n"
  "• 발사 지연, 방사선·열·광학 정렬 신뢰성, 고객 승인·수율·재작업 비용을 확인합니다.\n"
  +source_lines+"\n"
 )

def load()->tuple[dict,bool]:
 if not STATE.exists():return {"version":1,"created_at":NOW.isoformat(),"seen":{}},True
 try:
  s=json.loads(STATE.read_text(encoding="utf-8"))
  if not isinstance(s,dict) or not isinstance(s.get("seen"),dict):raise ValueError("bad state schema")
  return s,False
 except Exception as e:raise RuntimeError("중복 방지 상태 손상: 자동 초기화 금지") from e

def collect(rss_fetch=rss):
 candidates={group:{} for group in QUERIES}
 errors=[];success=0
 for group,queries in QUERIES.items():
  for query in queries:
   try:
    rows=rss_fetch(query)
    success+=1
    for row in rows:
     elapsed=NOW-row["published"]
     if elapsed>MAX_NEWS_AGE or elapsed < -dt.timedelta(minutes=20):continue
     event=classify(group,row["title"])
     if not event:continue
     fp=row["source"].casefold()+"|"+row["title"].casefold()
     candidates[group][fp]=(event,row)
   except Exception as e:
    errors.append(group+": "+type(e).__name__)
 return candidates,errors,success

def decide(candidates:dict,seen:dict,first:bool):
 selected=[]
 next_seen=dict(seen)
 for group,reported in candidates.items():
  ordered=sorted(reported.values(),key=lambda x:x[1]["published"],reverse=True)
  for event,row in ordered:
   if group=="kencoa_roadster":continue  # Never auto-claim Roadster supply from headlines.
   if event in next_seen:continue
   peers=[other for ev,other in ordered if ev==event and independent_pair(group,event,row,other)]
   if not peers:continue
   if first:
    next_seen[event]=NOW.isoformat()
    continue
   if NOW-row["published"]>LIVE_WINDOW:continue
   if any(event==e for _,e,_ in selected):continue
   title,statement,risk=korean_summary(group,event)
   stamp=row["published"].astimezone(KST).strftime("%Y-%m-%d %H:%M")
   message="\n".join([
    title,"• 시각: "+stamp+" KST",
    "• 확인: 서로 다른 두 취재 매체가 같은 고객·사건을 보도. 공식 신규 계약금액 확인 전 확정 수주액으로 계산하지 않습니다.",
    "• 핵심: "+statement,
    "• 매출 연결: 납품·검수 또는 서비스 사용량 확인 후 실제 매출 발생 여부를 구분합니다.",
    "• 실패 경로: "+risk,
    "• 원문: "+row["url"],
    "• 원문: "+peers[0]["url"],
   ])
   selected.append((row["published"],event,message))
 selected.sort(key=lambda z:z[0],reverse=True)
 # Do not lose validated events when multiple events arrive at once.
 # The unsent items remain unseen for the next 30-minute run.
 chosen=selected[:2]
 for _,event,_ in chosen:
  next_seen[event]=NOW.isoformat()
 return [x[2] for x in chosen],next_seen

def self_test()->int:
 cases={
  "telepix_contract:antaris:signed":("telepix_contract","TelePIX signs Antaris Space payload contract"),
  "telepix_contract:skyserve:signed":("telepix_contract","텔레픽스 인도 스카이서브 서비스 공급 계약 체결"),
  "telepix_contract:huleo:signed":("telepix_contract","TelePIX wins Hungary HULEO supply contract"),
  "telepix_flight:antaris:planned:2027":("telepix_flight","TelePIX Antaris JANUS-2 optical flight scheduled for 2027"),
  "telepix_flight:bellatrix:planned:2028":("telepix_flight","텔레픽스 Bellatrix 초저궤도 위성 2028년 발사 추진"),
  "kencoa_supplier:spacex:confirmed_supply":("kencoa_supplier","켄코아 SpaceX 발사체 티타늄 소재 공급"),
  "kencoa_roadster:potential_supply":("kencoa_roadster","Kencoa signs Roadster supply contract"),
  "lk_samyang:startracker:orbital_verified":("lk_samyang","LK삼양 텔레픽스 별추적기 우주 발사 실증 완료"),
 }
 for want,(group,title) in cases.items():
  got=classify(group,title)
  assert got==want,(title,want,got)
 assert classify("kencoa_supplier","Tesla Roadster uses SpaceX thrusters") is None
 assert classify("kencoa_supplier","켄코아 SpaceX 티타늄 공급 로드스터 추력기 시연") is None
 assert classify("telepix_contract","TelePIX Bellatrix signs MOU") is None
 assert classify("telepix_flight","TelePIX Antaris JANUS-2 2027 launch")=="telepix_flight:antaris:planned:2027"
 assert classify("telepix_contract","TelePIX and SkyServe announce additional contract renewal")=="telepix_contract:skyserve:change"
 assert classify("telepix_contract","텔레픽스 SkyServe 신규 계약 체결")=="telepix_contract:skyserve:change"
 assert classify("kencoa_supplier","켄코아 SpaceX 신규 부품 공급 계약 체결")=="kencoa_supplier:spacex:new_contract"
 assert classify("kencoa_supplier","Kencoa signs new SpaceX rocket parts contract")=="kencoa_supplier:spacex:new_contract"
 assert "kencoa_supplier:spacex:new_contract" not in KEY_BASELINE
 assert set(KEY_BASELINE).isdisjoint({"kencoa_roadster:potential_supply"})
 assert len(BASELINE_LINKS)<=10 and len(baseline())<3400
 a={"source":"연합뉴스","published":NOW,"title":"텔레픽스 인도 스카이서브 서비스 공급 계약 체결","url":"https://a.example"}
 b={"source":"이데일리","published":NOW,"title":"텔레픽스 스카이서브 신규 공급 계약 체결","url":"https://b.example"}
 assert independent_pair("telepix_contract","telepix_contract:skyserve:signed",a,b)
 assert not independent_pair("telepix_contract","telepix_contract:skyserve:signed",a,dict(a))
 selection,seen=decide({"telepix_contract":{"a":("telepix_contract:skyserve:signed",a),"b":("telepix_contract:skyserve:signed",b)}},{},False)
 assert len(selection)==1 and len(seen)==1
 selection2,_=decide({"telepix_contract":{"a":("telepix_contract:skyserve:signed",a),"b":("telepix_contract:skyserve:signed",b)}},seen,False)
 assert not selection2
 print("k_space_payload_supplier_self_test=ok milestones=1 source_pair=1 roadster_false_positive_block=1 dedup=1 one_message=1")
 return 0

def main()->int:
 if len(sys.argv)==2 and sys.argv[1]=="--self-test":return self_test()
 if len(sys.argv)!=1:raise SystemExit("usage: k_space_payload_supplier_watch.py [--self-test]")
 state,first=load()
 verified,original_errors=official_check()
 candidates,errors,rss_ok=collect()
 if len(verified)<1 or rss_ok<6:
  raise RuntimeError(f"출처 검증 부족(기업 원문 {len(verified)}, 뉴스 조회 {rss_ok}): 알림 보류·상태 유지")
 events,seen=decide(candidates,state["seen"],first)
 # Seed existing, already publicly known contract and historic flight-stage
 # milestones. Roadster supply is NOT seeded: it is unconfirmed.
 for event in KEY_BASELINE:
  if event not in seen:seen[event]=NOW.isoformat()
 state["seen"]=seen
 if first:
  report=baseline()
 elif events:
  report=TITLE+"\n기준: "+NOW.astimezone(KST).strftime("%Y-%m-%d %H:%M KST")+"\n\n"+"\n\n".join(events)+"\n"
 else:report=""
 ALERT.parent.mkdir(parents=True,exist_ok=True)
 if report:ALERT.write_text(report,encoding="utf-8")
 else:ALERT.unlink(missing_ok=True)
 PENDING.write_text(json.dumps(state,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
 STATUS.write_text("\n".join([
  "# 국내 위성 AI·SpaceX 공급망 감시 상태",
  "- 확인 시각: "+NOW.astimezone(KST).isoformat(),
  f"- 직접 열람한 기업 원문: {len(verified)}/2 ({', '.join(verified)})",
  f"- 뉴스 검색 성공: {rss_ok}/10 (실패: {len(errors)})",
  f"- 처음 등록: {first}; 신규 사건: {len(events)}; 알림 생성: {bool(report)}",
  "- Roadster SpaceX 기술 협력과 켄코아의 직접 추력기 납품은 분리 판정",
  "- Antaris 2027 계획과 Bellatrix 2028 MOU는 별개",
  ""
 ]),encoding="utf-8")
 print(f"k_space_payload_supplier_scan=ok official={len(verified)} rss_ok={rss_ok} initial={first} events={len(events)} alert={bool(report)}")
 return 0

if __name__=="__main__":raise SystemExit(main())
