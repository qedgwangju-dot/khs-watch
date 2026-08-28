#!/usr/bin/env python3
"""Deep Fission 중요 변화 감시 v4.

원칙
- 페이지 전체 HTML 해시 변화는 알림하지 않는다.
- 공식 신규 문서 또는 실제 상태 전환만 알린다.
- 예정·계획 표현을 완료로 오인하지 않는다.
- 같은 사건은 event_id로 1회만 전송한다.
- 텔레그램 본문 설명은 한국어로 작성한다.
"""
from __future__ import annotations

import argparse
import datetime as dt
import html
from html.parser import HTMLParser
import json
import os
import pathlib
import re
import time
import urllib.error
import urllib.request
from urllib.parse import urljoin

ROOT = pathlib.Path(__file__).resolve().parents[1]
DATA = ROOT / "data"
OUT = ROOT / "out"
STATE = DATA / "deep_fission_watch_v4_state.json"
PENDING = OUT / "deep_fission_watch_v4_state_pending.json"
ALERT = OUT / "deep_fission_alert_v4.md"
STATUS = OUT / "deep_fission_status_v4.md"
ERRORS = OUT / "deep_fission_errors_v4.log"

PRESS_URL = "https://www.deepfission.com/pr-media-kit/press-releases"
PARSONS_URL = "https://www.deepfission.com/sites/parsons"
NRC_URL = "https://www.nrc.gov/reactors/new-reactors/advanced/who-were-working-with/pre-application-activities/deep-fission"
DOE_URL = "https://www.energy.gov/ne/us-department-energy-reactor-pilot-program"
SEC_URL = "https://data.sec.gov/submissions/CIK0001918102.json"
UA = os.environ.get("DEEP_FISSION_WATCH_USER_AGENT", "KHS-Deep-Fission-Watch/4.0 contact=github-actions")
IMPORTANT_FORMS = {"8-K", "10-Q", "10-K", "S-1", "S-1/A", "424B4", "EFFECT"}


class Parser(HTMLParser):
    def __init__(self):
        super().__init__(); self.parts=[]; self.links=[]; self.href=None; self.anchor=[]
    def handle_starttag(self, tag, attrs):
        t=tag.lower()
        if t=="a": self.href=dict(attrs).get("href"); self.anchor=[]
        if t in {"p","div","li","tr","td","th","br","h1","h2","h3","h4"}: self.parts.append("\n")
    def handle_endtag(self, tag):
        t=tag.lower()
        if t=="a" and self.href:
            self.links.append((self.href," ".join(self.anchor).strip())); self.href=None; self.anchor=[]
        if t in {"p","div","li","tr","td","th","h1","h2","h3","h4"}: self.parts.append("\n")
    def handle_data(self, data):
        v=html.unescape(data); self.parts.append(v)
        if self.href is not None: self.anchor.append(v)
    def text(self):
        raw="".join(self.parts)
        raw=re.sub(r"[\t\r ]+"," ",raw); raw=re.sub(r"\n\s*\n+","\n",raw)
        return raw.strip()


def fetch(url, accept="text/html,application/json", timeout=30):
    req=urllib.request.Request(url,headers={"User-Agent":UA,"Accept":accept,"Accept-Language":"en-US,en;q=0.8"})
    last=None
    for n in range(3):
        try:
            with urllib.request.urlopen(req,timeout=timeout) as r: return r.read().decode("utf-8",errors="replace")
        except (urllib.error.URLError,urllib.error.HTTPError,TimeoutError) as e:
            last=e; time.sleep(1.5*(n+1))
    raise RuntimeError(f"원천 조회 실패 {url}: {last}")


def parse(raw):
    p=Parser(); p.feed(raw); return p.text(),p.links

def norm(v): return re.sub(r"\s+"," ",html.unescape(v).lower().replace("™","")).strip()
def lines(v): return [re.sub(r"\s+"," ",x).strip() for x in v.splitlines() if x.strip()]
def now_kst(): return dt.datetime.now(dt.timezone(dt.timedelta(hours=9))).strftime("%Y-%m-%d %H:%M KST")

def load_state():
    if not STATE.exists(): return {}
    try: return json.loads(STATE.read_text(encoding="utf-8"))
    except Exception: return {}


def press_items(raw):
    _,links=parse(raw); out={}
    for href,label in links:
        if "/press-releases/detail/" not in href: continue
        title=re.sub(r"\s+"," ",label).strip()
        if len(title)>=8: out[urljoin(PRESS_URL,href)]=title
    return out


def sec_recent():
    obj=json.loads(fetch(SEC_URL,accept="application/json")); r=(obj.get("filings") or {}).get("recent") or {}
    arr=[r.get(k) or [] for k in ("accessionNumber","form","filingDate","primaryDocument")]
    accs,forms,dates,docs=arr; out={}
    for i,acc in enumerate(accs):
        form=forms[i] if i<len(forms) else ""
        if form not in IMPORTANT_FORMS: continue
        doc=docs[i] if i<len(docs) else ""; nodash=acc.replace("-","")
        url=f"https://www.sec.gov/Archives/edgar/data/1918102/{nodash}/{doc}" if doc else "https://www.sec.gov/edgar/browse/?CIK=1918102"
        out[acc]={"form":form,"date":dates[i] if i<len(dates) else "","url":url}
    return out


def extract_nrc(text):
    low=norm(text)
    phase="향후 통합허가 신청을 위한 사전협의" if "pre-application activities associated with a future combined license application" in low or "currently engaged in pre-application activities" in low else "확인 불가"
    if re.search(r"deep fission.{0,200}(?:submitted|filed).{0,120}(?:combined license application|col application)",low): phase="통합허가 신청서 제출"
    if re.search(r"(?:combined license application|col application).{0,180}(?:accepted for review|docketed)",low): phase="통합허가 신청서 접수·심사 착수"
    compact=" | ".join(lines(text)); statuses={}
    docs={
        "규제협의계획":"NRC Regulatory Engagement Plan",
        "개념설계 검토":"Conceptual Design Review",
        "개념설계 설명서":"Conceptual Design Description",
    }
    trans={"No Review Requested":"검토 요청 없음","Review Complete":"검토 완료","Review in Progress":"검토 진행 중","Accepted":"접수","Docketed":"정식 접수","Closed":"종료","Open":"진행 중"}
    for key,label in docs.items():
        i=compact.lower().find(label.lower())
        if i<0: continue
        w=compact[i:i+800]
        for eng,ko in trans.items():
            if eng.lower() in w.lower(): statuses[key]=ko; break
    m=re.search(r"NRC Docket\s+(\d+)",text,re.I)
    return {"단계":phase,"심사상태":statuses,"사건번호":m.group(1) if m else ""}


def explicit_df_line(text,pattern):
    for line in lines(text):
        low=norm(line)
        if "deep fission" in low and re.search(pattern,low): return True
    return False


def extract_doe(text):
    return {
        "임계도달":explicit_df_line(text,r"(?:reached|achieved|successfully achieved)\s+(?:first\s+)?criticality"),
        "연료장전":explicit_df_line(text,r"(?:completed|began|started|authorized).{0,30}(?:nuclear )?fuel loading"),
        "전출력":explicit_df_line(text,r"(?:reached|achieved|completed).{0,50}full[- ]power"),
    }


def extract_parsons(text):
    low=norm(text)
    return {
        "자료취득시추공6000피트완료": "6,000 feet" in low and ("completed drilling" in low or "data acquisition well complete" in low or "drilling of the data acquisition well" in low),
        "시제품원자로용기현장반입": "reactor canister on site" in low or bool(re.search(r"prototype reactor canister.{0,150}(?:received|arrived|delivered).{0,120}(?:parsons|project site|site)",low)),
        "두번째시추공지상준비완료": "ground preparations complete for our second test well" in low or "finished ground preparations for our second test well" in low,
        "2500피트시추착수": bool(re.search(r"(?:began|has begun|started|has started|commenced|spudded|drilling is underway).{0,200}(?:2,500|2500|proof of concept|commercial-scale borehole)",low) or re.search(r"(?:2,500|2500|proof of concept|commercial-scale borehole).{0,200}(?:began drilling|started drilling|commenced drilling|spudded|drilling is underway)",low)),
        "2500피트목표깊이도달": bool(re.search(r"(?:reached|completed).{0,140}(?:2,500|2500)\s*(?:foot|feet|ft)",low)),
        "시제품지하배치": bool(re.search(r"(?:lowered|installed|deployed|emplaced).{0,160}prototype.{0,160}(?:underground|borehole|2,500|2500)",low)),
        "비핵실증완료": bool(re.search(r"(?:completed|successfully completed).{0,160}non-nuclear.{0,120}(?:test|testing|demonstration)",low)),
        "에너지부건설운전승인": bool(re.search(r"doe.{0,100}(?:authorized|approved|granted).{0,200}(?:construct|construction).{0,140}(?:operate|operation)",low)),
        "원자력규제위원회통합허가제출": bool(re.search(r"(?:submitted|filed).{0,120}(?:combined license application|commercial operating license application)",low)),
    }


def link_line(url): return f"- 링크: {url}"

def msg(fact,previous,current,stage,axes,next_check,source,url,risk="기술·규제 진전이 실제 상업계약·매출로 연결되기 전에 일정 지연이나 추가 자금조달이 발생할 수 있음"):
    return (
        f"[Deep Fission 중요 변화 | {now_kst()}]\n"
        "- 판정: 신규 공식 변화 확인\n"
        f"- 새 사실: {fact}\n"
        f"- 이전 → 현재: {previous} → {current}\n"
        f"- 단계: {stage}\n"
        f"- 바뀐 축: {axes}\n"
        "- 한국 기업 연결: 두산에너빌리티·수산이앤에스 신규 직접계약은 이번 변화만으로 확인되지 않음\n"
        f"- 실패 경로: {risk}\n"
        f"- 다음 확인: {next_check}\n"
        f"- 출처: {source}\n"
        + link_line(url)
    )


def classify_press(title,text,url):
    low=norm(title+"\n"+text); out=[]
    if "nuclear safety design agreement" in low and "approves" in norm(title):
        out.append(("보도자료:"+url,msg("미국 에너지부가 Gravity 원자로의 원자력 안전설계협약(NSDA)을 승인","안전설계협약 검토 단계","원자력 안전설계협약 승인·후속 승인 단계","인허가·실증","할인율·시간표","후속 미국 에너지부 안전검토·건설 및 운전 승인·파슨스 실증","Deep Fission 공식 보도자료",url)))
    elif re.search(r"prototype reactor canister.{0,100}(?:arrives|arrived|delivered)",low):
        out.append(("보도자료:"+url,msg("시제품 원자로 용기의 제작·시험·파슨스 현장 도착이 공식 확인","제작·시험","현장 반입·설치 준비","공정·실증","시간표","약 2,500피트 개념검증 시추공 착수·시제품 지하 배치","Deep Fission 공식 보도자료",url)))
    elif "customer pipeline" in low and ("18.5" in low or "gigawatt" in low):
        out.append(("보도자료:"+url,msg("발전용량 기준 최대 18.5GW 고객 후보군을 공식 공개","고객 수요 정량 미공개","최대 18.5GW 고객 후보군 공개","고객·계약","돈 버는 능력·시간표","고객 실명·구속력 있는 전력구매계약·최종투자결정","Deep Fission 공식 보도자료",url,"고객 후보군이 확정 계약·실제 매출로 전환되지 않을 수 있음")))
    elif "public offering" in low or "primary offering" in low:
        out.append(("보도자료:"+url,msg("신규 주식발행·자금조달 관련 공식 발표","기존 자금조달 상태","신규 주식발행 절차","자금조달","수급·시간표","발행 주식수·가격·순유입 현금·희석률·자금 사용처","Deep Fission 공식 보도자료",url,"상업매출 발생 전 추가 증자로 기존 주주 희석이 커질 수 있음")))
    elif re.search(r"(?:began|started|commenced|spudded).{0,180}(?:2,500|2500|proof of concept|commercial-scale borehole)",low):
        out.append(("보도자료:"+url,msg("약 2,500피트 개념검증 시추공의 실제 시추 착수","착수 예정·준비","실제 시추 착수","공정","시간표","목표 깊이 도달·시추공 안정성·시제품 하강","Deep Fission 공식 보도자료",url)))
    return out


def self_test():
    nrc="""What: Pre-Application activities associated with a future combined license application.\nNRC Regulatory Engagement Plan | No Review Requested\nConceptual Design Review | Review Complete\nConceptual Design Description | Review in Progress\nNRC Docket 99902126"""
    s=extract_nrc(nrc)
    assert s["단계"]=="향후 통합허가 신청을 위한 사전협의"
    assert s["심사상태"].get("개념설계 설명서")=="검토 진행 중"
    future="We are targeting Q3 of 2026 to begin drilling our 2,500 foot proof of concept borehole."
    assert not extract_parsons(future)["2500피트시추착수"]
    true="Deep Fission has begun drilling its 2,500 foot proof of concept borehole."
    assert extract_parsons(true)["2500피트시추착수"]
    print("deep_fission_v4_self_test=success")


def main():
    ap=argparse.ArgumentParser(); ap.add_argument("--mode",choices=["check","self-test"],default="check"); a=ap.parse_args()
    if a.mode=="self-test": self_test(); return 0
    DATA.mkdir(parents=True,exist_ok=True); OUT.mkdir(parents=True,exist_ok=True)
    for p in (PENDING,ALERT,STATUS,ERRORS):
        if p.exists(): p.unlink()
    old=load_state(); first=not bool(old)
    state={"version":4,"updated_at":dt.datetime.now(dt.timezone.utc).replace(microsecond=0).isoformat(),"press_urls":dict(old.get("press_urls") or {}),"sec_filings":dict(old.get("sec_filings") or {}),"nrc":dict(old.get("nrc") or {}),"doe":dict(old.get("doe") or {}),"parsons":dict(old.get("parsons") or {}),"sent_event_ids":list(old.get("sent_event_ids") or [])}
    sent=set(state["sent_event_ids"]); current_ids=set(); events=[]; errors=[]; fetched=0
    def add(eid,text):
        if eid in sent or eid in current_ids: return
        current_ids.add(eid); events.append(text)
    try:
        raw=fetch(PRESS_URL); fetched+=1
        for url,title in press_items(raw).items():
            if url in state["press_urls"]: continue
            state["press_urls"][url]=title
            if first: continue
            try:
                detail=fetch(url); fetched+=1; text,_=parse(detail)
                for eid,m in classify_press(title,text,url): add(eid,m)
            except Exception as e: errors.append(f"보도자료 상세 조회 실패 {url}: {e}")
    except Exception as e: errors.append(f"보도자료 목록 조회 실패: {e}")
    try:
        fs=sec_recent(); fetched+=1
        for acc,meta in fs.items():
            if acc in state["sec_filings"]: continue
            state["sec_filings"][acc]=meta
            if first: continue
            form=meta["form"]
            add("공시:"+acc,msg(f"미국 증권거래위원회에 {form} 신규 공시 제출","해당 공시 미제출",f"{form} 제출","공시·자금조달","돈 버는 능력·수급·시간표","현금잔고·영업현금 유출·증자·차입·자금 사용처","미국 증권거래위원회(SEC)",meta["url"],"공시상 자금조달 변화가 원자로 실증 진전과 별개일 수 있음"))
    except Exception as e: errors.append(f"미국 증권거래위원회 조회 실패: {e}")
    try:
        text,_=parse(fetch(NRC_URL)); fetched+=1; cur=extract_nrc(text); prev=state["nrc"]
        if not first and prev:
            if cur.get("단계")!="확인 불가" and cur.get("단계")!=prev.get("단계"):
                add(f"NRC단계:{prev.get('단계')}->{cur.get('단계')}",msg("미국 원자력규제위원회 공식 인허가 단계가 변경",str(prev.get("단계")),str(cur.get("단계")),"인허가","할인율·시간표","정식 접수 여부·심사 일정·추가정보요구·환경영향평가·청문","미국 원자력규제위원회(NRC)",NRC_URL))
            ps=prev.get("심사상태") or {}
            for k,v in (cur.get("심사상태") or {}).items():
                if k in ps and ps[k]!=v:
                    add(f"NRC심사:{k}:{ps[k]}->{v}",msg(f"{k} 심사 상태가 변경",ps[k],v,"인허가","할인율·시간표","다음 심사단계·통합허가 실제 제출 여부","미국 원자력규제위원회(NRC)",NRC_URL))
        state["nrc"]=cur
    except Exception as e: errors.append(f"미국 원자력규제위원회 조회 실패: {e}")
    try:
        text,_=parse(fetch(DOE_URL)); fetched+=1; cur=extract_doe(text); prev=state["doe"]
        if not first and prev:
            meta={"임계도달":("Deep Fission 원자로의 실제 임계 도달이 미국 에너지부 공식 페이지에서 확인","임계 미도달","임계 도달","출력시험·후속 승인·상업허가"),"연료장전":("Deep Fission 원자로의 실제 연료 장전이 미국 에너지부 공식 페이지에서 확인","연료 장전 전","연료 장전 착수·완료","임계 도달·안전시험"),"전출력":("Deep Fission 원자로의 전출력 단계가 미국 에너지부 공식 페이지에서 확인","전출력 전","전출력 단계","상업운전 전환·원자력규제위원회 허가")}
            for k,(fact,p,c,nxt) in meta.items():
                if cur.get(k) and not prev.get(k): add("DOE:"+k,msg(fact,p,c,"실증","할인율·시간표",nxt,"미국 에너지부(DOE)",DOE_URL))
        state["doe"]=cur
    except Exception as e: errors.append(f"미국 에너지부 조회 실패: {e}")
    try:
        text,_=parse(fetch(PARSONS_URL)); fetched+=1; cur=extract_parsons(text); prev=state["parsons"]
        labels={"2500피트시추착수":("약 2,500피트 개념검증 시추공의 실제 시추 착수","착수 예정·준비","실제 시추 착수","공정","시간표","목표 깊이·시추공 안정성·시제품 하강"),"2500피트목표깊이도달":("약 2,500피트 목표 깊이 도달","시추 진행","목표 깊이 도달","공정","시간표","케이싱·시멘팅·시제품 하강 준비"),"시제품지하배치":("시제품 원자로 용기의 실제 지하 배치","현장 대기","지하 배치","공정·실증","할인율·시간표","구조건전성·인양 가능성·열수력 시험"),"비핵실증완료":("비핵 실증 시험 완료가 공식 확인","실증 진행","실증 완료","실증","할인율·시간표","열수력·구조건전성 결과·후속 승인"),"에너지부건설운전승인":("미국 에너지부가 시범원자로 건설·운전을 실제 승인","후속 승인 필요","건설·운전 승인 확보","인허가·실증","할인율·시간표","착공·연료 장전·안전시험·임계 도달"),"원자력규제위원회통합허가제출":("미국 원자력규제위원회 통합허가 신청서 실제 제출","사전협의","통합허가 신청서 제출","인허가","할인율·시간표","정식 접수·심사 일정·추가정보요구·환경영향평가")}
            for k,(fact,p,c,stage,axes,nxt) in labels.items():
                if cur.get(k) and not prev.get(k): add("파슨스:"+k,msg(fact,p,c,stage,axes,nxt,"Deep Fission 파슨스 공식 페이지",PARSONS_URL))
        state["parsons"]=cur
    except Exception as e: errors.append(f"파슨스 공식 페이지 조회 실패: {e}")
    if first: events=[]; current_ids.clear()
    state["sent_event_ids"]=(state["sent_event_ids"]+sorted(current_ids))[-500:]
    PENDING.write_text(json.dumps(state,ensure_ascii=False,indent=2,sort_keys=True),encoding="utf-8")
    if events: ALERT.write_text("\n\n---\n\n".join(events[:8])+"\n",encoding="utf-8")
    if errors: ERRORS.write_text("\n".join(errors)+"\n",encoding="utf-8")
    STATUS.write_text(f"# Deep Fission 감시 상태\n- 확인 시각: {now_kst()}\n- 원천 조회 성공: {fetched}회\n- 신규 중요 변화: {len(events)}건\n- 오류: {len(errors)}건\n- 판정 방식: 페이지 전체 해시 미사용, 실제 상태 전환·신규 공식 문서만 사용\n- 중복 방지: event_id 영구 저장\n- 링크 형식: 원문 뉴스보기 클릭형 링크\n",encoding="utf-8")
    print(f"deep_fission_v4_fetched={fetched}"); print(f"deep_fission_v4_events={len(events)}"); print(f"deep_fission_v4_errors={len(errors)}")
    return 0

if __name__=="__main__": raise SystemExit(main())
