#!/usr/bin/env python3
"""Separate Korean military space / force-support acquisition watch.

Conservative alert rules:
- An actual command establishment, budget allocation, or procurement award
  must come from a government primary publication; article headlines alone
  never convert policy plans into executed contracts.
- Industry/media coverage requires two distinct trusted publishers describing
  the same event and is always labelled as coverage, not a government decision.
- No change => no Telegram output. State is persisted only after delivery.
"""
from __future__ import annotations

import datetime as dt
import email.utils
import hashlib
import html
import json
import os
import pathlib
import re
import socket
import time
import urllib.error
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from zoneinfo import ZoneInfo

ROOT=pathlib.Path(__file__).resolve().parents[1]
STATE=ROOT/"data/k_defense_space_watch_state.json"
PENDING=ROOT/"out/k_defense_space_watch_pending_state.json"
ALERT=ROOT/"out/k_defense_space_watch_telegram.txt"
STATUS=ROOT/"out/k_defense_space_watch_status.md"
NOW=dt.datetime.now(dt.timezone.utc)
KST=ZoneInfo("Asia/Seoul")
AGENT="Mozilla/5.0 (compatible; khs-defense-space/1.0)"
MAX_AGE=dt.timedelta(days=12)
RECENT=dt.timedelta(hours=96)

GOV_DOMAINS=(
  "mnd.go.kr","dapa.go.kr","korea.kr","msit.go.kr","nabo.go.kr",
  "law.go.kr","ntis.go.kr","pps.go.kr","g2b.go.kr","kasa.go.kr",
)
COMPANY_DOMAINS=(
  "hanwhasystems.com","kai-web.com","lignex1.com",
  "satreci.com","hanwhaaerospace.com",
)
TRUSTED_PUBLISHERS=(
  "연합뉴스","뉴시스","뉴스1","아시아투데이","한국경제","매일경제",
  "서울경제","전자신문","ZDNet","디지털타임스","국방일보","방위산업",
  "Reuters","SpaceNews","KBS","SBS","MBC","YTN","머니투데이","이데일리",
)

FOCUS=re.compile(
  r"우주전략사령부|우주사령부|국방우주|군\s*정찰위성|425\s*사업|"
  r"초소형\s*위성|초소형위성|군집\s*위성|저궤도\s*위성통신|"
  r"위성\s*지상체|위성\s*지상국|군\s*위성통신|군\s*통신위성|"
  r"우주감시|우주\s*상황인식|우주\s*인증센터|"
  r"국방.{0,12}전력지원|위성.{0,12}전력지원|"
  r"우주.{0,15}지휘통제|위성.{0,12}조달|"
  r"(?:KAI|한화시스템|LIG넥스원|쎄트렉아이|인텔리안테크|AP위성).{0,28}"
  r"(?:군\s*위성|군\s*정찰|국방우주|우주전력)",
  re.I
)
CHANGE=re.compile(
  r"창설|신설|직제|개정|법령|승인|확정|발효|발표|예산|증액|배정|"
  r"공고|입찰|낙찰|선정|수주|계약|양산|구축|전력화|시험|검증|"
  r"발사|착수|전력지원|운용|유지보수|정비|인수|완료|이전|"
  r"협의회|발족|출범|협약|군집|중단|취소|지연",
  re.I
)
NOISE=re.compile(
  r"단순\s*주가|목표주가|정치테마|급등|급락|증권가\s*관심|"
  r"관련주\s*폭등|상한가|코인|가상화폐|연예|야구|축구",
  re.I
)
FORMAL=re.compile(
  r"우주전략사령부|우주사령부|창설|설치|사령관|직제|대통령령|"
  r"국방예산|예산\s*확정|낙찰|계약\s*체결|수주|우선협상",
  re.I
)
KOREAN=re.compile(r"[가-힣]")
MONEY=re.compile(r"(?:\d[\d,]*(?:\.\d+)?\s?(?:조\s?\d*[\d,]*\s?억|조|억|만)?원|\d[\d,]*\s?기|\d[\d,]*\s?회)")
WORDFILTER={"국방","우주","우주전략","사령부","우주사령부","2026","추진","계획","사업","정부","올해","위한","관련","강화","사업자","확대","한국","국내","국가","산업","체계","본격","발표","기업","방위","군사","개발"}


@dataclass(frozen=True)
class Topic:
  code:str
  tag:str
  title:str
  queries:tuple[str,...]
  pattern:re.Pattern[str]
  meaning:str
  danger:str
  next_check:str

TOPICS=(
  Topic("command","[조직·정책]","우주전략사령부·국방 조직 개편",(
      '"우주전략사령부" (창설 OR 직제 OR 설치 OR 예산) when:14d',
      'site:mnd.go.kr "우주전략사령부" when:30d',
      'site:korea.kr "우주전략사령부" when:30d',
    ),re.compile(r"우주전략사령부|우주사령부",re.I),
    "조직 개편 자체보다 직제·인력·예산·장비소요 확정이 발주로 연결되는지를 추적합니다.",
    "정책 계획만 존재하고 시행령·예산·소요결정이 늦어지면 실제 매출이 발생하지 않습니다.",
    "국방부 창설 확정 발표·대통령령·예산 세부항목·전력소요"),
  Topic("satellite","[정찰위성]","425사업·초소형위성·지상체",(
      '"425사업" (위성 OR 지상체 OR 전력화 OR 계약) when:14d',
      '"초소형위성체계" (방위사업청 OR SAR OR 지상체 OR 발사) when:14d',
      'site:dapa.go.kr 초소형위성체계 군 정찰위성 when:30d',
    ),re.compile(r"425\s*사업|정찰위성|초소형\s*위성|군집\s*위성|영상레이더|위성\s*지상체",re.I),
    "위성 제작 수주와 지상 수신·영상처리·연동·운영유지 계약을 나눠 매출 인식을 확인합니다.",
    "발사·인수시험 또는 해상도·영상전송 검증 지연 시 납기와 검수 매출이 밀립니다.",
    "방위사업청 계약 원문·검증위성 발사·지상체 인수시험·데이터링크 성능"),
  Topic("communications","[군 위성통신]","저궤도통신·보안·지휘통제",(
      '"저궤도위성통신산업협의회" (방위사업청 OR 계약 OR 실증) when:30d',
      '"군 위성통신" (사업 OR 수주 OR 조달 OR 지상국) when:14d',
      'site:dapa.go.kr 위성통신 지상국 통신체계 when:30d',
    ),re.compile(r"저궤도\s*위성통신|위성통신|군\s*통신위성|통신\s*지상국|지휘통제",re.I),
    "단말·안테나 납품 이후 보안망 운영·지상국 유지보수·소프트웨어 갱신 여부를 구분합니다.",
    "보안 인증·군 통신망 상호운용성·주파수 허가가 지연되면 실제 전력화가 늦어집니다.",
    "군 전용 조달계약·보안인증·단말 수량·지상국 연동시험"),
  Topic("sustainment","[전력지원]","군수·정비·운용·전력지원체계",(
      '"전력지원체계" (우주 OR 위성 OR 국방) when:14d',
      '"국방우주" (운용 유지보수 OR 정비 OR 성능개량 OR 군수) when:14d',
      'site:dapa.go.kr 위성 체계지원 운용 유지보수 when:30d',
    ),re.compile(r"전력지원체계|전력지원|군수|정비|운용유지|유지보수|성능개량|체계지원",re.I),
    "초기 장비·구축 매출과 후속 소모품·수리·성능개선·장기 유지보수 계약을 분리합니다.",
    "보증·품질·운용 가동률 미달과 예산 전용으로 후속 계약이 지연될 수 있습니다.",
    "군수지원 계약범위·정비주기·보증충당금·연간 운영예산"),
  Topic("surveillance","[우주감시·인증]","우주상황인식·레이더·시험인증",(
      '"국방 우주" (우주감시 OR 우주상황인식 OR 우주 인증센터) when:14d',
      'site:dapa.go.kr 우주감시 인증센터 레이더 when:30d',
      'site:mnd.go.kr 우주감시 상황인식 when:30d',
    ),re.compile(r"우주감시|우주\s*상황인식|우주\s*인증센터|우주\s*레이더|시험인증",re.I),
    "감시센서·분석 소프트웨어·관제시스템과 장기 운용계약으로 이어지는지를 추적합니다.",
    "탐지 성능·표적 식별 정확도·장비 인증 실패가 인수시험과 매출을 지연시킬 수 있습니다.",
    "관제·레이더 발주공고·시험평가 합격·현장 인수·운영유지 계약"),
)
OFFICIAL_BASE=(
  ("국방부 국정과제","https://www.mnd.go.kr/mnd/497/subview.do"),
  ("국방부 2026 국방예산","https://mnd.go.kr/mnd/780/subview.do"),
  ("방위사업청 425사업 5호기 발사","https://www.dapa.go.kr/dapa/doc/selectDoc.do?bbsSeq=326&docSeq=57695&menuSeq=3069"),
  ("방위사업청 저궤도위성통신 협의회","https://www.dapa.go.kr/dapa/doc/selectDoc.do?bbsSeq=326&docSeq=58127&menuSeq=3069"),
)

def hostname(url:str)->str:
  return (urllib.parse.urlsplit(url).hostname or "").lower()

def matching(host:str, names:tuple[str,...])->bool:
  return any(host==x or host.endswith("."+x) for x in names)

def request_bytes(url:str, attempts:int=3)->bytes:
  last=None
  for i in range(attempts):
    req=urllib.request.Request(url,headers={"User-Agent":AGENT,"Accept":"application/rss+xml,*/*"})
    try:
      with urllib.request.urlopen(req,timeout=22) as res:
        return res.read()
    except urllib.error.HTTPError as e:
      last=e
      if e.code not in (429,500,502,503,504) or i==attempts-1: raise
    except (urllib.error.URLError,socket.timeout,TimeoutError) as e:
      last=e
      if i==attempts-1: raise
    time.sleep(min(2**i,5))
  raise RuntimeError(str(last))

def google_rss(query:str)->list[dict]:
  params=urllib.parse.urlencode({"q":query,"hl":"ko","gl":"KR","ceid":"KR:ko"})
  raw=request_bytes("https://news.google.com/rss/search?"+params)
  root=ET.fromstring(raw)
  items=[]
  for e in root.findall(".//item"):
    name=html.unescape(re.sub(r"<[^>]*>"," ",e.findtext("title") or "")).strip()
    url=html.unescape(e.findtext("link") or "").strip()
    if not name or not url.startswith("https://"): continue
    src=e.find("source")
    publisher=(src.text or "").strip() if src is not None else ""
    pub_link=(src.get("url") or "") if src is not None else ""
    try:
      pub_time=email.utils.parsedate_to_datetime(e.findtext("pubDate") or "")
      if pub_time.tzinfo is None:pub_time=pub_time.replace(tzinfo=dt.timezone.utc)
      pub_time=pub_time.astimezone(dt.timezone.utc)
    except Exception:continue
    items.append({"title":name,"url":url,"publisher":publisher,"publisher_url":pub_link,
                 "time":pub_time.isoformat()})
  return items

def official_class(item:dict)->str:
  host=hostname(item.get("publisher_url",""))
  if matching(host,GOV_DOMAINS):return "정부 공식"
  if matching(host,COMPANY_DOMAINS):return "기업 공식"
  return ""

def trusted(item:dict)->bool:
  if official_class(item):return True
  s=item["publisher"].lower()
  return any(x.lower() in s for x in TRUSTED_PUBLISHERS)

def normalize(text:str)->str:
  s=re.sub(r"\s+[-|]\s+[^-|]{1,45}$","",text.strip())
  s=re.sub(r"\([^)]*\)"," ",s)
  return re.sub(r"[^0-9가-힣A-Za-z]+"," ",s).strip().lower()

def fingerprints(title:str)->set[str]:
  s=normalize(title)
  words=[w for w in s.split() if len(w)>=2 and w not in WORDFILTER]
  return set(words)

def event_match(a:dict,b:dict)->bool:
  if a["publisher"].lower()==b["publisher"].lower():return False
  x=fingerprints(a["title"])
  y=fingerprints(b["title"])
  common=x&y
  if len(common)<2:return False
  return len(common)/max(1,len(x|y))>=0.28

def key(topic:Topic,item:dict)->str:
  raw=f'{topic.code}|{normalize(item["title"])}'
  return hashlib.sha256(raw.encode()).hexdigest()[:24]

def classify(item:dict,topic:Topic)->bool:
  title=item["title"]
  return (bool(FOCUS.search(title)) and bool(CHANGE.search(title)) and
          bool(topic.pattern.search(title)) and not bool(NOISE.search(title)))

def judge(topic:Topic,item:dict,peers:list[dict])->tuple[bool,str,list[dict]]:
  role=official_class(item)
  if role=="정부 공식":
    return True,"정부 공식 원문",[]
  if role=="기업 공식":
    # Company disclosures cannot certify a government order or grant by themselves.
    if topic.code=="command" or re.search(r"정부.{0,12}창설|직제\s*확정",item["title"]):
      return False,"",[]
    related=[p for p in peers if official_class(p)=="정부 공식" and event_match(item,p)]
    if related:
      return True,"기업 발표·정부 발표 교차",related[:1]
    return False,"",[]
  if topic.code=="command":
    return False,"",[] # Organizational change requires government confirmation.
  if not trusted(item):return False,"",[]
  related=[p for p in peers if trusted(p) and event_match(item,p)]
  # An independent, same-event second publisher is mandatory for news reports.
  if related:
    return True,"독립된 복수 보도(공식 계약 미확정)",related[:1]
  return False,"",[]

def load_state()->dict:
  if not STATE.exists(): return {"version":1,"created_at":NOW.isoformat(),"seen":{}}
  try:
    s=json.loads(STATE.read_text(encoding="utf-8"))
    if isinstance(s,dict) and isinstance(s.get("seen"),dict):return s
  except Exception:pass
  raise RuntimeError("기존 중복방지 상태파일 오류: 자동 초기화 대신 실행 중단")

def report_header()->str:
  return "🛰️ 국내 국방우주·전력지원체계 웹감시\n기준: "+NOW.astimezone(KST).strftime("%Y-%m-%d %H:%M KST")

def bootstrap_report()->str:
  return (report_header()+"\n\n"+
    "[정책 기준선] 국방부는 ‘우주전략사령부’의 중장기 단계적 창설을 정책으로 명시했습니다. "+
    "창설 완료나 신규 수주 확정으로 해석하지 않습니다.\n"+
    "• 원문: "+OFFICIAL_BASE[0][1]+"\n\n"+
    "[예산 기준선] 2026년 국방예산 65조8,642억원 중 방위력개선비는 19조9,653억원입니다. "+
    "전체를 국방우주 예산으로 간주하지 않으며, 분야별 실제 편성·조달액을 별도로 확인합니다.\n"+
    "• 원문: "+OFFICIAL_BASE[1][1]+"\n\n"+
    "[확정 당사자] 방위사업청 발표에 따르면 425 군 정찰위성 5호기 개발에는 "+
    "국방과학연구소, 한국항공우주산업, 한화시스템, 쎄트렉아이 등이 참여했습니다. "+
    "새 우주전략사령부 사업 수주자로 선정됐다는 뜻은 아닙니다.\n"+
    "• 원문: "+OFFICIAL_BASE[2][1]+"\n\n"+
    "[공정 병목] 위성 본체 제작 외에도 지상체·암호 통신망 연동, 품질 인증, "+
    "인수시험과 유지보수 예산이 실제 매출의 선행조건입니다.\n"+
    "• 먼저 볼 지표: 시행령·세부예산·입찰공고·계약상대방·검수 완료·운영계약\n"+
    "• 실패 경로: 조직만 개편되고 발주와 전력화 일정이 늦어지는 경우\n"+
    "• 원문: "+OFFICIAL_BASE[3][1]+"\n\n"+
    "[기사 참고] 아시아투데이 2026년 10월 8일 기사 제목을 감시 촉발 요인으로 포함했습니다. "+
    "해당 기사 본문은 직접 열람에 제한이 있어 공식 출처로 확인된 부분과 구분했습니다.\n"+
    "• 원문: https://m.asiatoday.co.kr/kn/view.php?key=20261008010002539")

def render(topic:Topic,item:dict,grade:str,related:list[dict])->str:
  title=re.sub(r"\s+[-|]\s+[^-|]{1,55}$","",item["title"])
  published=dt.datetime.fromisoformat(item["time"]).astimezone(KST).strftime("%Y-%m-%d %H:%M KST")
  numbers=list(dict.fromkeys(MONEY.findall(title)))
  if len(numbers)>5:numbers=numbers[:5]
  parts=[f'{topic.tag} {topic.title}',f'• 제목: {title}',
        f'• 확인 수준: {grade} | 출처: {item["publisher"]} | {published}']
  if numbers:parts.append("• 기사 제목에 있는 숫자: "+", ".join(numbers)+" (계약대금으로 단정 금지)")
  parts += [f'• 매출 연결: {topic.meaning}',f'• 실패 경로: {topic.danger}',
            f'• 먼저 볼 지표: {topic.next_check}',
            "• 기업 구분: 기계약·기납품 업체와 이번 신규 수주 확정 업체를 구분해야 합니다.",
            "• 원문: "+item["url"]]
  for p in related:
    parts.append("• 원문: "+p["url"])
  return "\n".join(parts)

def self_test()->None:
  p=TOPICS[0]
  item={"title":"우주전략사령부 창설 단계적 추진 - 연합뉴스","publisher":"연합뉴스",
        "publisher_url":"https://www.yna.co.kr","url":"https://example.com/a",
        "time":NOW.isoformat()}
  assert classify(item,p)
  assert not judge(p,item,[])[0], "언론 기사만으로 창설 확정 방지"
  government={**item,"publisher":"국방부","publisher_url":"https://mnd.go.kr"}
  assert judge(p,government,[])[0]
  unrelated={"title":"우주전략사령부 창설 정책 검토 - 뉴시스","publisher":"뉴시스",
        "publisher_url":"https://newsis.com","url":"https://example.com/b",
        "time":NOW.isoformat()}
  assert not judge(p,unrelated,[])[0]
  assert "2026년 국방예산 65조8,642억원" in bootstrap_report()
  assert "우주전략사령부" in bootstrap_report()
  assert STATE!=PENDING
  print("k_defense_space_watch_self_test=ok")

def main()->int:
  if os.environ.get("K_DEFENSE_WATCH_SELF_TEST")=="1":
    self_test()
    return 0
  force=os.environ.get("FORCE_NOTIFY","").lower() in {"true","1","yes"}
  initial=not STATE.exists()
  state=load_state()
  seen=state["seen"]
  selections=[]
  statuses=[]
  failures=0
  successes=0
  across={}
  for topic in TOPICS:
    candidates={}
    for query in topic.queries:
      try:
        rows=google_rss(query)
        successes+=1
        for item in rows:
          if not classify(item,topic):continue
          date=dt.datetime.fromisoformat(item["time"])
          if NOW-date>MAX_AGE or date>NOW+dt.timedelta(minutes=20):continue
          k=key(topic,item)
          prev=candidates.get(k)
          if prev is None or official_class(item) and not official_class(prev):
            candidates[k]=item
      except Exception as exc:
        failures+=1
        statuses.append(f"{topic.code} 조회오류: {type(exc).__name__}: {str(exc)[:120]}")
    across[topic.code]=list(candidates.values())
    statuses.append(f"{topic.code}: 키워드 필터 적합 기사 {len(candidates)}건")

  if not successes:
    raise RuntimeError("모든 뉴스 조회 실패: 중복 상태와 알림은 보존")
  for topic in TOPICS:
    peers=across[topic.code]
    chosen=[]
    for item in peers:
      confirmed,grade,related=judge(topic,item,peers)
      if not confirmed:continue
      eid=key(topic,item)
      # Register already-published items on bootstrap, without describing them
      # as brand-new events. After bootstrap, only 96h fresh coverage counts.
      if initial:
        seen[eid]=NOW.isoformat()
        continue
      pub=dt.datetime.fromisoformat(item["time"])
      if pub<NOW-RECENT:continue
      if eid in seen and not force:continue
      chosen.append((item,grade,related))
    chosen.sort(key=lambda t:t[0]["time"],reverse=True)
    for item,grade,related in chosen[:2]:
      selections.append(render(topic,item,grade,related))
      seen[key(topic,item)]=NOW.isoformat()

  # A baseline is one-time only. Never send historic news as new on startup.
  if initial:
    text=bootstrap_report()
  elif selections:
    text=report_header()+"\n\n"+"\n\n".join(selections)
  else:
    text=""

  ALERT.parent.mkdir(parents=True,exist_ok=True)
  if text:
    ALERT.write_text(text+"\n",encoding="utf-8")
  else:
    ALERT.unlink(missing_ok=True)

  PENDING.parent.mkdir(parents=True,exist_ok=True)
  state["updated_at"]=NOW.isoformat()
  if len(seen)>2400:
    state["seen"]=dict(sorted(seen.items(),key=lambda kv:kv[1],reverse=True)[:1800])
  PENDING.write_text(json.dumps(state,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
  STATUS.write_text("\n".join([
    "# 국내 국방우주·전력지원체계 감시",
    f"- 점검: {NOW.astimezone(KST).isoformat()}",
    f"- 조회 성공: {successes}, 실패: {failures}",
    f"- 알림: {('최초 기준선' if initial else str(len(selections))+'건')}",
    "- 정부 창설/계약 확정 주장: 정부 공식 출처만 인정",
    "- 언론 보도: 복수 보도와 정부 공식 발표 구분",
    *("- "+x for x in statuses),
    ""
  ]),encoding="utf-8")
  print(f"k_defense_space_scan=ok news_queries_success={successes} alert={bool(text)} verified_events={len(selections)}")
  return 0

if __name__=="__main__":
  raise SystemExit(main())
