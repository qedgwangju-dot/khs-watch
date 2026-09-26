#!/usr/bin/env python3
"""High-signal fusion commercialization and enabling-technology watch."""
from __future__ import annotations
import datetime as dt, email.utils, hashlib, html, json, os, pathlib, re, urllib.parse, urllib.request, xml.etree.ElementTree as ET
from zoneinfo import ZoneInfo

ROOT=pathlib.Path(__file__).resolve().parents[1]
STATE=ROOT/"data"/"fusion_commercialization_watch_state.json"
OUT=ROOT/"out"; OUT.mkdir(parents=True,exist_ok=True)
ALERT=OUT/"fusion_commercialization_watch_alert.html"
STATUS=OUT/"fusion_commercialization_watch_status.md"
PENDING=OUT/"fusion_commercialization_watch_pending_state.json"
KST=ZoneInfo("Asia/Seoul")
UA="Mozilla/5.0 (compatible; FusionCommercializationWatch/1.0; +https://github.com/qedgwangju-dot/khs-watch)"
MAX_AGE_HOURS=int(os.getenv("FUSION_WATCH_MAX_AGE_HOURS","120"))

GOOGLE_QUERIES=[
 '"American Leadership in Fusion Act" (committee OR markup OR passed OR Senate OR appropriations OR signed OR enacted)',
 '"fusion" DOE (milestone OR demonstration OR award OR funding OR "test facility" OR "Office of Fusion")',
 'fusion (HTS OR REBCO OR "high temperature superconductor" OR magnet) (contract OR capacity OR factory OR qualification OR award)',
 'fusion (tritium OR blanket OR neutron OR materials OR "fuel cycle") (facility OR award OR milestone OR demonstration)',
 'fusion ("hydrogen boron" OR p-B11 OR Helong-2 OR Helong 2) (experiment OR "first plasma" OR electricity OR milestone)',
 'fusion ("pulsed power" OR pulser OR "magnetic inertial" OR z-pinch) (milestone OR demonstration OR prototype OR facility)',
]
OFFICIAL=("House Committee on Science, Space and Technology","U.S. Department of Energy","Department of Energy","Federal Register","Congress.gov","U.S. House of Representatives","U.S. Senate")
TRUSTED=("Reuters","Bloomberg","AP News","Associated Press","CNBC","Financial Times","The Wall Street Journal","AIP","Physics Today")
TOPIC=("fusion","핵융합","american leadership in fusion act","hts","rebco","high temperature superconductor","tritium","blanket","p-b11","hydrogen boron","helong-2","helong 2","pulsed power","z-pinch")
HARD=("introduced","introduce","markup","ordered reported","reported favorably","passed","approved","senate","companion bill","appropriation","appropriations","funding","award","awarded","selected","selection","contract","procurement","construction","groundbreaking","broke ground","first plasma","demonstration","prototype","commercial","deployment","grid","factory","capacity","qualified","qualification","signed into law","enacted","office of fusion")

def now_kst(): return dt.datetime.now(KST)
def clean(v):
    v=html.unescape(re.sub(r"<[^>]+>"," ",v or ""))
    return re.sub(r"\s+"," ",v).strip()
def fetch(url,timeout=25):
    req=urllib.request.Request(url,headers={"User-Agent":UA,"Accept-Language":"en-US,en;q=0.9"})
    with urllib.request.urlopen(req,timeout=timeout) as r:
        data=r.read(); charset=r.headers.get_content_charset() or "utf-8"
    return data.decode(charset,errors="replace")
def gnews(q):
    return "https://news.google.com/rss/search?"+urllib.parse.urlencode({"q":q+" when:7d","hl":"en-US","gl":"US","ceid":"US:en"})
def pdate(v):
    try:
        x=email.utils.parsedate_to_datetime(v)
        if x.tzinfo is None: x=x.replace(tzinfo=dt.timezone.utc)
        return x.astimezone(KST)
    except Exception: return None
def publisher(item):
    n=item.find("source"); return clean(n.text if n is not None else "")
OFFICIAL_SOURCE_MARKERS=(
    "house committee on science",
    "science.house.gov",
    "democrats-science.house.gov",
    "republicans-science.house.gov",
    "congress.gov",
    "energy.gov",
    "u.s. department of energy",
    "department of energy",
    "federal register",
    "u.s. house of representatives",
    "u.s. senate",
)

def publisher_matches(publisher, names):
    low=clean(publisher).lower()
    return any(low == clean(name).lower() for name in names)

def official_publisher(publisher):
    low=clean(publisher).lower()
    return publisher_matches(publisher, OFFICIAL) or any(marker in low for marker in OFFICIAL_SOURCE_MARKERS)

def allowed(p):
    # Official government source names may carry a committee/domain suffix in
    # Google News. Trusted media remain exact-name only so a publisher such as
    # "Heatmap News" can never pass merely because it contains "AP News".
    return official_publisher(p) or publisher_matches(p, TRUSTED)

def srank(p):
    if official_publisher(p): return 0
    if publisher_matches(p, ("Reuters","Bloomberg","AP News","Associated Press")): return 1
    return 2
def text_of(t,s,p): return clean(f"{t} {s} {p}").lower()
def stage(text):
    if "american leadership in fusion act" in text:
        if "signed into law" in text or "enacted" in text: return "법률 제정",100
        if "senate" in text and ("passed" in text or "approved" in text): return "상원 통과",95
        if ("house" in text or "house of representatives" in text) and ("passed" in text or "approved" in text): return "하원 통과",94
        if "appropriation" in text or "appropriations" in text: return "실제 예산 배정",98
        if "markup" in text or "ordered reported" in text or "reported favorably" in text: return "위원회 심사 진전",90
        if "senate" in text and ("companion" in text or "introduced" in text): return "상원 동반법안 발의",88
        if "introduced" in text or "introduction" in text or "introduce" in text or "introduces" in text: return "법안 발의",82
    if "office of fusion" in text and any(x in text for x in ("establish","established","codif","launch","created")): return "DOE 전담조직 제도화",92
    if any(x in text for x in ("award","awarded","selected","selection")) and any(x in text for x in ("milestone","demonstration","test facility","funding")): return "DOE 사업 선정·자금 배정",96
    if any(x in text for x in ("groundbreaking","broke ground","construction")): return "시설 착공",92
    if "first plasma" in text: return "첫 플라즈마",96
    if any(x in text for x in ("factory","capacity","qualified","qualification","contract","procurement")) and any(x in text for x in ("hts","rebco","magnet","superconduct")): return "HTS·초전도 공급망 실행",90
    if any(x in text for x in ("hydrogen boron","p-b11","helong-2","helong 2")) and any(x in text for x in ("experiment","first plasma","electricity","milestone","construction")): return "수소-붕소 핵융합 실증 진전",91
    if any(x in text for x in ("pulsed power","pulser","magnetic inertial","z-pinch")) and any(x in text for x in ("prototype","demonstration","facility","milestone","construction")): return "펄스파워·대안 핵융합 실증 진전",89
    if any(x in text for x in ("tritium","blanket","neutron","materials","fuel cycle")) and any(x in text for x in ("test facility","facility","award","selected","demonstration")): return "재료·연료주기 병목 투자",90
    return "기타 핵융합 변화",70
def event_key(t,s,p):
    txt=text_of(t,s,p); st,_=stage(txt)
    if "american leadership in fusion act" in txt: return "american-leadership-in-fusion-act:"+st
    bucket=[]
    for name,terms in (("hts",("hts","rebco","superconduct","magnet")),("fuel",("tritium","blanket","fuel cycle","neutron","materials")),("p-b11",("hydrogen boron","p-b11","helong-2","helong 2")),("pulsed",("pulsed power","pulser","magnetic inertial","z-pinch")),("doe",("milestone","demonstration","office of fusion","test facility"))):
        if any(x in txt for x in terms): bucket.append(name)
    nt=re.sub(r"\s+-\s+[^-]{2,60}$","",clean(t).lower())
    nt=re.sub(r"[^0-9a-z가-힣]+"," ",nt)
    return f"{'+'.join(bucket) or 'fusion'}:{st}:{hashlib.sha256(nt.encode()).hexdigest()[:16]}"
def collect(now):
    rows=[]; notes=[]; urls=set()
    for q in GOOGLE_QUERIES:
        try: root=ET.fromstring(fetch(gnews(q)))
        except Exception as e:
            notes.append(f"검색 실패: {type(e).__name__}: {e}"); continue
        n=0
        for item in root.findall("./channel/item"):
            t=clean(item.findtext("title")); link=clean(item.findtext("link")); s=clean(item.findtext("description")); p=publisher(item); pub=pdate(clean(item.findtext("pubDate")))
            if not t or not link or not pub or link in urls: continue
            age=(now-pub).total_seconds()/3600
            txt=text_of(t,s,p)
            if age < -2 or age > MAX_AGE_HOURS or not allowed(p) or not any(x in txt for x in TOPIC) or not any(x in txt for x in HARD): continue
            st,score=stage(txt)
            rows.append({"title":t,"link":link,"summary":s,"publisher":p,"published_kst":pub.isoformat(timespec="seconds"),"stage":st,"score":score+(12 if srank(p)==0 else 5 if srank(p)==1 else 0),"event_key":event_key(t,s,p)})
            urls.add(link); n+=1
        notes.append(f"{q[:60]}: {n}건")
    rows.sort(key=lambda x:(-x["score"],x["published_kst"]))
    return rows,notes
def load_state():
    try:
        x=json.loads(STATE.read_text(encoding="utf-8")); return x if isinstance(x,dict) else {"seen":{}}
    except Exception: return {"seen":{}}
def esc(x): return html.escape(str(x or ""),quote=True)
def ktitle(r):
    txt=text_of(r["title"],r["summary"],r["publisher"]); st=r["stage"]
    if "american leadership in fusion act" in txt: return f"미국 핵융합 상용화 법안: {st}"
    if any(x in txt for x in ("hts","rebco","superconduct","magnet")): return f"핵융합 HTS·초전도 공급망: {st}"
    if any(x in txt for x in ("hydrogen boron","p-b11","helong-2","helong 2")): return f"수소-붕소 핵융합: {st}"
    if any(x in txt for x in ("pulsed power","pulser","magnetic inertial","z-pinch")): return f"펄스파워 핵융합: {st}"
    if any(x in txt for x in ("tritium","blanket","neutron","materials","fuel cycle")): return f"핵융합 재료·연료주기: {st}"
    return f"핵융합 상용화: {st}"
def render(rows,now):
    out=["🚨 <b>[핵융합 상용화·핵심기술]</b>",f"조회 {now:%Y-%m-%d %H:%M KST}",""]
    for i,r in enumerate(rows[:3],1):
        txt=text_of(r["title"],r["summary"],r["publisher"])
        out += [f"<b>{i}. {esc(ktitle(r))}</b>",f"• 현재 단계: {esc(r['stage'])}"]
        if "american leadership in fusion act" in txt:
            out += ["• 예산 구분: 100억달러는 현재 <b>법안상 직접투자 제안</b>. 실제 지출은 의회 통과·세출 배정·DOE 집행을 별도 확인","• 배분: 재료·연료주기 대형 시험시설 38억달러 / 신규 실증 마일스톤 30억달러 / 기존 마일스톤 20억달러 / 재료·연료주기 R&D 8억달러 / 중소형 시험시설 3억달러 / 핵심 공급망 1억달러","• 병목: HTS·REBCO, 중성자 내구재, 삼중수소·블랭킷, 시험설비, 첫 상업 실증의 자본비"]
        elif any(x in txt for x in ("hts","rebco","superconduct","magnet")): out += ["• 핵심 병목: REBCO 테이프 양산능력·길이 수율·접합·원가·납기"]
        elif any(x in txt for x in ("hydrogen boron","p-b11","helong-2","helong 2")): out += ["• 핵심 병목: p-B11은 훨씬 높은 반응조건·복사손실·실제 순에너지 검증 필요"]
        elif any(x in txt for x in ("pulsed power","pulser","magnetic inertial","z-pinch")): out += ["• 핵심 병목: 반복률·전극/챔버 수명·펄스 효율·열회수·발전계통 연결"]
        else: out += ["• 핵심 병목: 플라즈마 안정성·중성자 손상·연료주기·열회수·정비성·규제·보험·건설비"]
        out += [f"• 출처: {esc(r['publisher'])} · {esc(r['published_kst'][:16].replace('T',' '))}",f'• <a href="{esc(r["link"])}">원문</a>',""]
    out.append("※ 기사 재전송이 아니라 법안 단계·실제 예산·DOE 집행·기술 실증 단계가 바뀔 때만 알림합니다.")
    return "\n".join(out).strip()
def main():
    for p in (ALERT,PENDING): p.unlink(missing_ok=True)
    now=now_kst(); state=load_state(); seen=state.setdefault("seen",{}); rows,notes=collect(now)
    basekey="american-leadership-in-fusion-act:법안 발의"
    seen.setdefault(basekey,{"first_seen_kst":"2026-09-24T00:00:00+09:00","title":"American Leadership in Fusion Act introduced","status":"baseline-existing"})
    new=[]
    for r in rows:
        if r["event_key"] in seen: continue
        new.append(r); seen[r["event_key"]]={"first_seen_kst":now.isoformat(timespec="seconds"),"title":r["title"],"stage":r["stage"],"publisher":r["publisher"],"url":r["link"]}
    PENDING.write_text(json.dumps({"updated_at_kst":now.isoformat(timespec="seconds"),"seen":seen},ensure_ascii=False,indent=2,sort_keys=True)+"\n",encoding="utf-8")
    if new: ALERT.write_text(render(new,now),encoding="utf-8")
    STATUS.write_text("\n".join(["# 핵융합 상용화·핵심기술 감시",f"- 조회: {now:%Y-%m-%d %H:%M KST}",f"- 후보: {len(rows)}건",f"- 신규 의미 변화: {len(new)}건",f"- 알림 생성: {'예' if new else '아니오'}","- 원칙: 법안 발의 ≠ 실제 예산 집행. 위원회·본회의·세출·DOE 선정/집행을 별도 단계로 추적.",""]+[f"- {x}" for x in notes])+"\n",encoding="utf-8")
    print(f"fusion_watch candidates={len(rows)} new={len(new)} alert={ALERT.exists()}")
    return 0
if __name__=="__main__": raise SystemExit(main())
