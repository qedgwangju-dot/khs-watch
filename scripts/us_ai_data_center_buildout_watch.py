#!/usr/bin/env python3
from __future__ import annotations
import csv, datetime as dt, hashlib, html, io, json, re
from pathlib import Path
import requests
from bs4 import BeautifulSoup

OUT=Path("out")
STATE=Path("data/us_ai_data_center_buildout_state.json")
PENDING=OUT/"us_ai_data_center_buildout_pending_state.json"
ALERT=OUT/"us_ai_data_center_buildout_alert.txt"
STATUS=OUT/"us_ai_data_center_buildout_status.md"
DC_URL="https://epoch.ai/data/data_centers/data_centers.csv"
TL_URL="https://epoch.ai/data/data_centers/data_center_timelines.csv"
DOWNLOADS="https://epoch.ai/data/data-centers-documentation/downloads"
HEADERS={"User-Agent":"khs-watch/1.0 (+https://github.com/qedgwangju-dot/khs-watch)"}
TOP_N=15
POWER_DELTA=50.0
PROGRESS_DELTA=5.0
DATE_DELTA=60

TRACKED_NAMES=(
"Microsoft Fairwater Wisconsin",
"Anthropic-Amazon New Carlisle",
"OpenAI Stargate New Mexico",
"Meta Hyperion",
"Colossus 2",
"OpenAI Stargate Shackelford",
"QTS Cedar Rapids",
"Meta Prometheus",
"Goodnight",
"OpenAI Stargate Michigan",
"OpenAI Stargate Wisconsin",
"Google Fort Wayne",
"OpenAI Stargate Milam",
"OpenAI Stargate Abilene",
"Microsoft Fairwater Atlanta",
)

ALIASES={
"Microsoft Fairwater Wisconsin":"MS Fairwater (WI)",
"Anthropic-Amazon New Carlisle":"Amazon New Carlisle (IN)",
"OpenAI Stargate New Mexico":"Stargate Jupiter (NM)",
"Meta Hyperion":"Meta Hyperion (LA)",
"Colossus 2":"xAI Colossus 2 (TN)",
"OpenAI Stargate Shackelford":"Stargate Shackelford (TX)",
"QTS Cedar Rapids":"QTS Cedar Rapids (IA)",
"Meta Prometheus":"Meta Prometheus (OH)",
"Google Goodnight":"Google Goodnight (TX)",
"Goodnight":"Google Goodnight (TX)",
"OpenAI Stargate Michigan":"Stargate Michigan",
"OpenAI Stargate Wisconsin":"Stargate Wisconsin",
"Google Fort Wayne":"Google Fort Wayne (IN)",
"OpenAI Stargate Milam":"Stargate Milam (TX)",
"OpenAI Stargate Abilene":"Stargate Abilene (TX)",
"Microsoft Fairwater Atlanta":"MS Fairwater Atlanta (GA)",
}
ENERGY_PROFILES={
"Microsoft Fairwater Wisconsin":{
  "site":"WE Energies 계통 + 250MW 태양광 매칭",
  "future":"Microsoft 원전 835MW·Helion 핵융합 50MW+",
  "quality":"부지확정+기업전략",
},
"Anthropic-Amazon New Carlisle":{
  "site":"NIPSCO/GenCo 계통·신규발전(원별 미공개)",
  "future":"Amazon 원전 1.92GW·SMR 검토",
  "quality":"부지확정+기업전략",
},
"OpenAI Stargate New Mexico":{
  "site":"Bloom 연료전지 기반(연료원 공개 미확인)",
  "future":"Stargate 전용발전·저장",
  "quality":"부지확정",
},
"Meta Hyperion":{
  "site":"천연가스 발전 + 배터리 + 원전 증출력 + 재생에너지",
  "future":"Meta 기존·차세대 원전 확대",
  "quality":"부지확정",
},
"Colossus 2":{
  "site":"정확한 부지전원 미공개",
  "future":"xAI Memphis 계통 + 배터리 + 가스터빈 비상전원",
  "quality":"기업·지역확인",
},
"OpenAI Stargate Shackelford":{
  "site":"복수 계통전원 피드(원별 구성 미공개)",
  "future":"Stargate 전용발전·저장",
  "quality":"부지부분확인",
},
"QTS Cedar Rapids":{
  "site":"Alliant Energy 계통 + 무탄소 전원(세부 원별 미공개)",
  "future":"QTS 저탄소·무탄소 조달",
  "quality":"부지부분확인",
},
"Meta Prometheus":{
  "site":"계통전력 + 원전 공급확대(Ohio/PJM 연계)",
  "future":"Meta Vistra·TerraPower·Oklo 등 원전",
  "quality":"지역확정+기업전략",
},
"Goodnight":{
  "site":"계통 + 풍력 265MW 협약 + 933MW 가스발전 제안",
  "future":"Google 차세대원전 + 지열",
  "quality":"가스는 허가·계약 미확정",
},
"OpenAI Stargate Michigan":{
  "site":"DTE 기존 전원 + 신규 배터리 저장",
  "future":"Stargate 전용발전·저장",
  "quality":"부지확정",
},
"OpenAI Stargate Wisconsin":{
  "site":"WEC 태양광 + 풍력 + 배터리 + 재생에너지 매칭",
  "future":"Stargate 전용발전·저장",
  "quality":"부지확정",
},
"Google Fort Wayne":{
  "site":"Indiana Michigan Power 계통(원별 구성 미공개)",
  "future":"Google 차세대원전 + 지열",
  "quality":"부지부분확인+기업전략",
},
"OpenAI Stargate Milam":{
  "site":"SB Energy 신규발전 + 저장장치(원별 미공개)",
  "future":"Stargate 전용발전·저장",
  "quality":"부지확정",
},
"OpenAI Stargate Abilene":{
  "site":"ERCOT 계통 + 현장 천연가스 터빈",
  "future":"Crusoe 배터리·재생에너지·원전 옵션",
  "quality":"부지확정",
},
"Microsoft Fairwater Atlanta":{
  "site":"고신뢰 계통전력·GPU 현장발전 없음",
  "future":"Microsoft 원전 835MW·Helion 핵융합 50MW+",
  "quality":"부지확정+기업전략",
},
}

SHORT={"Microsoft":"MS","Amazon":"Amazon","Oracle":"Oracle","Meta":"Meta","Google":"Google","SpaceXAI":"xAI","Softbank":"SoftBank","SoftBank":"SoftBank","OpenAI":"OpenAI","Anthropic":"Anthropic","Google DeepMind":"Google DeepMind"}

def fetch(url,timeout=45):
    r=requests.get(url,headers=HEADERS,timeout=timeout); r.raise_for_status(); return r
def load_state():
    try:return json.loads(STATE.read_text(encoding="utf-8"))
    except Exception:return {}
def nh(s): return re.sub(r"[^a-z0-9]+"," ",(s or "").lower()).strip()
def val(row,*names):
    d={nh(k):(v or "").strip() for k,v in row.items()}
    for n in names:
        if nh(n) in d:return d[nh(n)]
    return ""
def number(v):
    try:return float(str(v).replace(",","").strip())
    except Exception:return None
def pdate(v):
    try:return dt.date.fromisoformat((v or "")[:10])
    except Exception:return None
def clean(v):
    v=re.sub(r"#(?:confident|likely|speculative)\b","",v or "",flags=re.I)
    return re.sub(r"\s+"," ",v).strip(" ,;")
def short(v):
    v=clean(v)
    if not v:return "미기재"
    parts=[x.strip() for x in re.split(r"[,;|]",v) if x.strip()]
    return "·".join(dict.fromkeys(SHORT.get(x,x) for x in parts))
def qlabel(d,progress):
    if progress>=99.5:return "완료"
    if not d:return "일정 미기재"
    return f"{d.year}.{(d.month-1)//3+1}Q"
def stage(status,current,planned,progress):
    low=(status or "").lower()
    if progress>=99.5:return "가동 완료"
    prefix="부분 가동·" if current>0 and current<planned else ""
    for keys,label in (
        (("commission","fit-out","fit out"),"시운전·내부설비"),
        (("cooling","chiller","cooling tower"),"냉각설비 설치"),
        (("roof","exterior","shell","enclosed"),"지붕·외피 공사"),
        (("steel","framing"),"철골 공사"),
        (("foundation","groundwork","ground work","footing"),"기초·토공"),
        (("land clearing","clearing"),"부지 정리"),
        (("substation",),"변전소·전력설비 공사"),
        (("operational",),"가동 확대"),
        (("construction","underway"),"건설 진행"),
    ):
        if any(k in low for k in keys): return prefix+label
    return "부분 가동·확장 공사" if current>0 else "건설 중"
def risky(status):
    low=(status or "").lower()
    return any(k in low for k in ("delay","delayed","denied","rejected","blocked","halt","paused","financing uncertain","funding uncertain"))
def updated_label():
    try:
        txt=" ".join(BeautifulSoup(fetch(DOWNLOADS,25).text,"html.parser").stripped_strings)
        idx=txt.find("AI Data Centers")
        snippet=txt[idx:idx+260] if idx>=0 else txt
        m=re.search(r"Updated\s+([A-Z][a-z]{2}\.?\s+\d{1,2},\s*\d{4})",snippet)
        if m:return m.group(1).replace(".","")
    except Exception:pass
    return "업데이트일 확인 불가"

def snapshot(dc_text,tl_text):
    dc=list(csv.DictReader(io.StringIO(dc_text)))
    tl=list(csv.DictReader(io.StringIO(tl_text)))
    meta={}
    for r in dc:
        name=val(r,"Name","Data center"); country=val(r,"Country")
        if name and "united states" in country.lower():
            meta[name]={"owner":clean(val(r,"Owner")),"users":clean(val(r,"Users","User")),"investors":clean(val(r,"Investors"))}
    groups={}
    for r in tl:
        name=val(r,"Data center","Data Center")
        d=pdate(val(r,"Date")); mw=number(val(r,"IT power (MW)","IT Power (MW)"))
        if name in meta and d and mw is not None:
            groups.setdefault(name,[]).append({"date":d,"mw":mw,"status":val(r,"Construction status","Construction Status")})
    today=dt.datetime.now(dt.timezone.utc).date(); out=[]
    for name,rows in groups.items():
        rows.sort(key=lambda x:x["date"]); planned=max(x["mw"] for x in rows)
        if planned<=0:continue
        past=[x for x in rows if x["date"]<=today]
        cur=past[-1] if past else {"mw":0.0,"status":"","date":None}
        current=max(0.0,float(cur["mw"])); progress=min(100.0,current/planned*100.0)
        full=[x for x in rows if x["mw"]>=planned*0.995]
        finish=(full[0]["date"] if full else rows[-1]["date"])
        m=meta[name]
        energy=ENERGY_PROFILES.get(name,{"site":"미확인","future":"미확인","quality":"미확인"})
        out.append({
            "name":name,"display":ALIASES.get(name,name),
            "owner":short(m["owner"]),"users":short(m["users"]),"investors":short(m["investors"]),
            "current_mw":round(current,1),"planned_mw":round(planned,1),"progress":round(progress,1),
            "completion_date":finish.isoformat(),"completion":qlabel(finish,progress),
            "stage":stage(cur.get("status",""),current,planned,progress),"risk":risky(cur.get("status","")),
            "energy_site":energy["site"],"energy_future":energy["future"],"energy_quality":energy["quality"],
        })
    by_name={x["name"]:x for x in out}
    top=[by_name[name] for name in TRACKED_NAMES if name in by_name]
    digest=hashlib.sha256(json.dumps(top,ensure_ascii=False,sort_keys=True,separators=(",",":")).encode()).hexdigest()
    return top,digest

def changes(old,new):
    prev={x.get("name"):x for x in old.get("projects",[])}
    if not prev:return ["Epoch AI 미국 핵심 15개 프로젝트 기준선 신규 연결"]
    out=[]; now={x["name"]:x for x in new}
    for n in sorted(set(now)-set(prev)):out.append(f"추적 목록 신규 진입: {now[n]['display']} {now[n]['planned_mw']:,.0f}MW")
    for n in sorted(set(prev)-set(now)):out.append(f"추적 목록 제외: {prev[n].get('display',n)}")
    for n,p in now.items():
        o=prev.get(n)
        if not o:continue
        if abs(p["current_mw"]-float(o.get("current_mw",0)))>=POWER_DELTA:out.append(f"{p['display']} 현재 IT전력 {float(o.get('current_mw',0)):,.0f}→{p['current_mw']:,.0f}MW")
        if abs(p["planned_mw"]-float(o.get("planned_mw",0)))>=POWER_DELTA:out.append(f"{p['display']} 계획 IT전력 {float(o.get('planned_mw',0)):,.0f}→{p['planned_mw']:,.0f}MW")
        if abs(p["progress"]-float(o.get("progress",0)))>=PROGRESS_DELTA:out.append(f"{p['display']} 진행률 {float(o.get('progress',0)):.0f}%→{p['progress']:.0f}%")
        od=pdate(o.get("completion_date","")); nd=pdate(p["completion_date"])
        if od and nd and abs((nd-od).days)>=DATE_DELTA:out.append(f"{p['display']} 완료시점 {o.get('completion','')}→{p['completion']} ({'지연' if nd>od else '앞당김'})")
        if p["stage"]!=o.get("stage") and p["progress"]<99.5:out.append(f"{p['display']} 공정 {o.get('stage','')}→{p['stage']}")
        if (p["owner"],p["users"],p["investors"])!=(o.get("owner"),o.get("users"),o.get("investors")):out.append(f"{p['display']} 소유·사용·투자자 정보 변경")
        if (p.get("energy_site"),p.get("energy_future"),p.get("energy_quality"))!=(o.get("energy_site"),o.get("energy_future"),o.get("energy_quality")):out.append(f"{p['display']} 전력원 정보 변경")
    return list(dict.fromkeys(out))
def badge(n):
    m={"0":"0️⃣","1":"1️⃣","2":"2️⃣","3":"3️⃣","4":"4️⃣","5":"5️⃣","6":"6️⃣","7":"7️⃣","8":"8️⃣","9":"9️⃣"}
    return "🔟" if n==10 else "".join(m[c] for c in str(n))
def h(v):return html.escape(str(v),quote=True)

def render(ps,chg,upd):
    planned=sum(x["planned_mw"] for x in ps); current=sum(x["current_mw"] for x in ps); pct=current/planned*100 if planned else 0
    lines=["<b>📊 미국 주요 AI 데이터센터 건설 현황</b>",f"출처: Epoch AI · {h(upd)}","용량 = 계획 IT전력 / 진행률 = 현재 IT전력 ÷ 계획 IT전력","","<b>🔄 이번 핵심 변화</b>"]
    lines += [f"• {h(x)}" for x in chg[:6]]
    if len(chg)>6:lines.append(f"• 그 외 {len(chg)-6}건은 상태에 반영")
    lines += ["",f"• 핵심 {len(ps)}개 계획 IT전력 합계 <b>{planned/1000:.1f}GW</b>",f"• 현재 IT전력 합계 <b>{current/1000:.1f}GW</b> · 가중 진행률 <b>{pct:.1f}%</b>",""]
    for i,p in enumerate(ps,1):
        inv=p["investors"] if p["investors"]!="미기재" else "Epoch 투자자 미기재"
        lines += [f"<b>{badge(i)} {h(p['display'])}{' ⚠️' if p['risk'] else ''}</b>",
                  f"{h(p['owner'])} → {h(p['users'])} | {h(inv)}",
                  f"<b>{p['planned_mw']:,.0f}MW</b> | {h(p['completion'])} | <b>{p['progress']:.0f}%</b> ({p['current_mw']:,.0f}/{p['planned_mw']:,.0f}MW) | {h(p['stage'])}",
                  f"⚡ 전력원 │ [{h(p['energy_quality'])}] {h(p['energy_site'])} | 장기전원: {h(p['energy_future'])}"]
    lines += ["","<b>📌 판정 기준</b>","• 진행률은 Epoch의 현재 IT전력 ÷ 계획 최종 IT전력으로 직접 계산","• 계획용량·완료시점·공정은 위성영상·허가·회사자료 기반 Epoch 추정치","• IT전력 추정은 대략 ±1.4배, 일정은 약 ±6개월 불확실성을 염두에 둠","• 50MW 이상 용량 변화, 진행률 ±5%p, 완료시점 ±60일, 상위15 진입·이탈 때 전체판 재전송","• 자금조달·전력·인허가 위험은 기존 실행병목 감시와 별도 교차검증","• 전력원은 부지 실제·계획 전원과 기업 차원의 장기전원(원전·핵융합·지열 등)을 반드시 분리하고, 미확정은 미확정으로 표시","• 천연가스와 LNG는 구분하며 LNG 공급계약·터미널·연료근거가 확인될 때만 LNG로 표기"]
    return "\n".join(lines)+"\n"

def main():
    OUT.mkdir(exist_ok=True)
    for p in (PENDING,ALERT,STATUS):
        if p.exists():p.unlink()
    old=load_state(); errs=[]
    try:
        a=fetch(DC_URL); b=fetch(TL_URL); ps,digest=snapshot(a.text,b.text)
        if len(ps)!=len(TRACKED_NAMES):raise RuntimeError(f"Epoch tracked projects missing: {len(ps)}/{len(TRACKED_NAMES)}")
        src_hash=hashlib.sha256(a.content+b"\n"+b.content).hexdigest()
    except Exception as e:
        if not old.get("projects"):raise
        ps=old["projects"]; digest=old.get("snapshot_hash",""); src_hash=old.get("source_hash",""); errs=[f"Epoch source: {type(e).__name__}"]
    upd=updated_label(); chg=changes(old,ps); baseline=not old.get("initialized"); alert=baseline or bool(chg)
    pending={"initialized":True,"version":1,"dataset_updated":upd,"source_hash":src_hash,"snapshot_hash":digest,"projects":ps,"last_changes":chg[:20],"source_errors":errs,"updated_at_utc":dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")}
    PENDING.write_text(json.dumps(pending,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
    if alert:ALERT.write_text(render(ps,chg,upd),encoding="utf-8")
    STATUS.write_text("# 미국 주요 AI 데이터센터 건설 현황 감시\n\n"+f"- Epoch 업데이트: **{upd}**\n- 상위 프로젝트: **{len(ps)}개**\n- 의미 변화: **{len(chg)}건**\n- 알림: **{'예' if alert else '아니오'}**\n- 원천 오류: **{', '.join(errs) if errs else '없음'}**\n",encoding="utf-8")
    print(f"epoch_ai_buildout top={len(ps)} changes={len(chg)} baseline={baseline} alert={alert} errors={len(errs)}")
    return 0
if __name__=="__main__":raise SystemExit(main())
