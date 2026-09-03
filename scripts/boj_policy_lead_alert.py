#!/usr/bin/env python3
"""BOJ 정책 선행경보: 정책 촉매를 USD/JPY 가격 경보보다 먼저 알린다."""
from __future__ import annotations

import argparse, datetime as dt, hashlib, html, json, pathlib, re, urllib.parse
import xml.etree.ElementTree as ET
from dataclasses import asdict, dataclass
from email.utils import parsedate_to_datetime
from zoneinfo import ZoneInfo
from khs_source_fetch import fetch_text, record_source_failure

KST=ZoneInfo("Asia/Seoul"); UTC=dt.timezone.utc
OUT=pathlib.Path("out"); STATE=pathlib.Path("data/boj_policy_lead_alert_state.json")
TITLE=OUT/"boj_policy_lead_alert_title.txt"; BODY=OUT/"boj_policy_lead_alert.md"; DATA=OUT/"boj_policy_lead_alert.json"
WATCH=OUT/"boj_policy_lead_watch.md"; PENDING=OUT/"boj_policy_lead_pending_state.json"; CONFIRMED=OUT/"boj_policy_lead_telegram_confirmed.json"
UA="Mozilla/5.0 khs-boj-policy-lead/1.0"
GOOGLE="https://news.google.com/rss/search"; BOJ_RSS="https://www.boj.or.jp/en/rss/whatsnew.xml"
TRUSTED={"Reuters","Bloomberg","Nikkei Asia","Financial Times"}
QUERIES=('"Bank of Japan" rate hike Reuters when:2d','BOJ rate hike yen Reuters when:2d','"Bank of Japan" tightening Bloomberg OR "Nikkei Asia" when:2d')
MAX_AGE_H=48; RESET_H=72; COOLDOWN_MIN=180; PROB_STEP=10.0; HIGH_PROB=70.0
KNOWN_RATE=1.00; KNOWN_RATE_UNTIL=dt.date(2026,9,18)

@dataclass(frozen=True)
class Item:
    title:str; source:str; link:str; published:dt.datetime; description:str
@dataclass(frozen=True)
class Signal:
    key:str; stage:int; route:str; source:str; title:str; link:str; published:dt.datetime
    probability:float|None; hike_bp:int|None; target_rate:float|None; note:str

def clean(s):
    s=re.sub(r"<[^>]+>"," ",s or ""); return re.sub(r"\s+"," ",html.unescape(s)).strip()
def pubdate(s):
    try: d=parsedate_to_datetime(s)
    except Exception: return None
    if d.tzinfo is None: d=d.replace(tzinfo=UTC)
    return d.astimezone(KST)
def parse_rss(text,default=""):
    out=[]; root=ET.fromstring(text)
    for n in root.findall(".//item"):
        d=pubdate(n.findtext("pubDate")); t=clean(n.findtext("title"))
        src=n.find("source"); src=clean(src.text if src is not None else "") or default
        if t and d: out.append(Item(t,src,clean(n.findtext("link")),d,clean(n.findtext("description"))))
    return out
def fetch_rss(url,name,now):
    text,err=fetch_text(url,UA,timeout=20,attempts=2,accept="application/rss+xml,application/xml,text/xml,*/*")
    if err or not text:
        record_source_failure(lane="boj_policy_lead",source_name=name,source_url=url,error=err or "empty",checked_at=now); return []
    try: return parse_rss(text,name)
    except Exception as e:
        record_source_failure(lane="boj_policy_lead",source_name=name,source_url=url,error=f"RSS parse: {e}",checked_at=now); return []
def news_url(q): return GOOGLE+"?"+urllib.parse.urlencode({"q":q,"hl":"en-US","gl":"US","ceid":"US:en"})
def normalize(t):
    t=re.sub(r"\s+-\s+(reuters|bloomberg|nikkei asia|financial times)$","",t.lower()); return re.sub(r"\s+"," ",re.sub(r"[^a-z0-9%]+"," ",t)).strip()
def key(i): return hashlib.sha256(f"{normalize(i.title)}|{i.source}|{i.published.date()}".encode()).hexdigest()[:20]
def prob(text):
    vals=[]; low=text.lower()
    for m in re.finditer(r"(\d{1,3}(?:\.\d+)?)\s*%",low):
        ctx=low[max(0,m.start()-60):min(len(low),m.end()+60)]
        if any(x in ctx for x in ("probability","chance","odds","priced","pricing","price")):
            v=float(m.group(1));
            if 0<=v<=100: vals.append(v)
    return max(vals) if vals else None
def bp(text):
    m=re.search(r"(\d{1,3})\s*-?\s*basis[- ]point",text.lower()) or re.search(r"(\d{1,3})\s*bp\b",text.lower())
    return int(m.group(1)) if m and 1<=int(m.group(1))<=200 else None
def target(text):
    m=re.search(r"to\s+(\d{1,2}(?:\.\d+)?)\s*%",text.lower()); return float(m.group(1)) if m else None
def classify(i):
    src=i.source.strip(); sm=re.search(r"\s+-\s+(Reuters|Bloomberg|Nikkei Asia|Financial Times)$",i.title)
    if src not in TRUSTED and sm: src=sm.group(1)
    if src not in TRUSTED: return None
    text=f"{i.title} {i.description}"; low=text.lower()
    if not (("bank of japan" in low or re.search(r"\bboj\b",low)) and any(x in low for x in ("rate hike","raise rate","raise key rate","interest rate","tightening","hike bets"))): return None
    p=prob(text); b=bp(text); tr=target(text); stage=0; route="hike_expectation"; note="고신뢰 보도 기반 시장 기대 — BOJ 공식 결정 아님"
    if "poll" in low or "expected to" in low or "raise key rate" in low: stage=1; route="reuters_poll" if src=="Reuters" else "survey_expectation"
    if any(x in low for x in ("hike bets","priced in","pricing in","probability","chance")): stage=max(stage,1); route="market_probability" if p is not None else "hike_bets"
    actor=any(x in low for x in ("boj chief","governor ueda","deputy governor","board member","takata","himino","tamura"))
    if actor and any(x in low for x in ("signals chance","chance of","calls for","advocated","timely rate hikes","agile rate hikes","rate hike")):
        stage=max(stage,2); route="official_commentary"; note="BOJ 관계자 발언을 고신뢰 보도가 확인 — 결정 자체는 미확정"
    if p is not None and p>=HIGH_PROB:
        stage=max(stage,2); route="market_probability"; note=f"다음 회의 인상 확률 {p:.0f}% 반영 — 결정 자체는 미확정"
    if stage==0 and any(x in low for x in ("hike","tightening")): stage=1
    return Signal(key(i),stage,route,src,i.title,i.link,i.published,p,b,tr,note) if stage else None

def load_state():
    try: x=json.loads(STATE.read_text()); return x if isinstance(x,dict) else {}
    except Exception: return {}
def stime(x):
    try: d=dt.datetime.fromisoformat(str(x)); return d.astimezone(KST) if d.tzinfo else d.replace(tzinfo=KST)
    except Exception: return None
def should(s,state,now):
    if s.key==state.get("last_signal_key"): return False,"동일 기사 중복"
    last=stime(state.get("last_alert_at_kst")); prev=int(state.get("stage",0) or 0)
    if last and now-last>dt.timedelta(hours=RESET_H): prev=0
    if last and s.published<=last: return False,"이전 경보보다 오래된 기사"
    if s.stage>prev: return True,"정책 경보 단계 상승"
    if s.route!=state.get("route"): return True,"새 정책 감지 경로"
    oldp=state.get("probability_pct")
    if s.probability is not None and oldp is not None and s.probability>=float(oldp)+PROB_STEP: return True,"인상 확률 +10%p 이상 상승"
    if last is None: return True,"신규 정책 선행경보"
    return (True,"새 고신뢰 보도") if now-last>=dt.timedelta(minutes=COOLDOWN_MIN) else (False,"같은 단계 재알림 대기")
def latest_signals(now):
    items=[]
    for q in QUERIES: items+=fetch_rss(news_url(q),"Google News",now)
    dedup={}
    for i in items:
        k=normalize(i.title)
        if k not in dedup or i.published>dedup[k].published: dedup[k]=i
    cut=now-dt.timedelta(hours=MAX_AGE_H)
    sig=[classify(i) for i in dedup.values() if cut<=i.published<=now+dt.timedelta(minutes=10)]
    sig=[s for s in sig if s]
    return sorted(sig,key=lambda s:(s.stage,s.probability or -1,s.published),reverse=True)
def confirms(signals,s): return [x for x in signals if x.key!=s.key and x.source!=s.source and abs((x.published-s.published).total_seconds())<=36*3600][:2]
def official(now):
    cut=now-dt.timedelta(days=7); out=[]
    for i in fetch_rss(BOJ_RSS,"Bank of Japan",now):
        low=(i.title+" "+i.description).lower()
        if i.published>=cut and any(x in low for x in ("speech","monetary policy","summary of opinions","statement on monetary policy")): out.append(i)
    return sorted(out,key=lambda i:i.published,reverse=True)
def fx_context():
    try:
        from yen_carry_fx_shock import fetch_move,determine_fast_stage,determine_sustained_stage
        m=fetch_move(); return {"price":m.latest_price,"time":dt.datetime.fromtimestamp(m.latest_epoch,UTC).astimezone(KST),"m15":m.change_15m_pct,"m30":m.change_30m_pct,"draw":m.sustained_drawdown_pct,"mins":m.sustained_duration_minutes,"fast":determine_fast_stage(m),"sustained":determine_sustained_stage(m)}
    except Exception: return None
def label(d): return d.astimezone(KST).strftime("%Y-%m-%d %H:%M KST")
def meeting(now): return "2026년 9월 17~18일" if now.date()<=dt.date(2026,9,18) else "BOJ 공식 일정 재조회"
def build(s,reason,now,cs,off,fx):
    title=f"🚨 BOJ 정책 선행경보 {s.stage}단계 · {'주의' if s.stage==1 else '강화'}"
    top=[]
    if s.probability is not None: top.append(f"다음 회의 인상 확률 {s.probability:.0f}%")
    if s.hike_bp is not None: top.append(f"+{s.hike_bp}bp 가능성")
    if s.target_rate is not None and now.date()<=KNOWN_RATE_UNTIL: top.append(f"목표 {s.target_rate:.2f}%")
    L=[" │ ".join(top) or "BOJ 인상 기대 강화","","핵심 상태",f"• 판정: {reason}",f"• 감지 경로: {s.route}",f"• 다음 금융정책결정회의: {meeting(now)}",f"• 정확한 의미: {s.note}"]
    if s.target_rate is not None and now.date()<=KNOWN_RATE_UNTIL: L.append(f"• 정책금리 경로: {KNOWN_RATE:.2f}% → {s.target_rate:.2f}% 가능성")
    elif s.hike_bp is not None: L.append(f"• 예상 조정폭: +{s.hike_bp}bp")
    L += ["","선행 정책 촉매",f"• {s.source} · {label(s.published)}",f"  {s.title}"]
    if cs:
        L.append("• 교차 확인")
        for x in cs: L.append(f"  - {x.source}: {x.title}"+(f" · 인상 확률 {x.probability:.0f}%" if x.probability is not None else ""))
    else: L.append("• 교차 확인: 추가 고신뢰 출처 확인 전 — 1차 선행신호로 취급")
    if off:
        x=off[0]; L += ["","BOJ 공식 확인",f"• 최근 공식 자료·발언 일정: {x.title}",f"• 공개: {label(x.published)}","• 공식 자료 존재와 ‘금리인상 확정’은 같은 뜻이 아님"]
    L += ["","환율 확인"]
    if fx:
        L += [f"• USD/JPY {fx['price']:.3f} · 시장 데이터 {label(fx['time'])}",f"• 15분 {fx['m15']:+.2f}% │ 30분 {fx['m30']:+.2f}% │ 고점 대비 {fx['draw']:+.2f}% · {fx['mins']:.0f}분"]
        L.append("• 판정: 정책 촉매는 발생했지만 가격 확인은 아직 미충족" if fx['fast']==0 and fx['sustained']==0 else f"• 판정: 정책 촉매가 환율로 확인 중 — 빠른 급락 {fx['fast']}단계 / 지속 하락 {fx['sustained']}단계")
    else: L.append("• USD/JPY 실시간 교차조회 실패 — 정책 선행경보 자체는 유지")
    L += ["","최종 판정","• 정책 촉매를 가격 경보보다 먼저 알림","• ‘인상 전망·확률 상승’과 ‘BOJ 공식 인상 결정’을 반드시 분리","• 이후 기존 USD/JPY 경보가 가격 확인 역할","",f"조회 시각: {label(now)}"]
    if s.link: L.append(f"원문: {s.link}")
    payload={"stage":s.stage,"reason":reason,"signal":asdict(s),"confirmation_sources":[asdict(x) for x in cs],"official_context":[asdict(x) for x in off[:2]],"fx":fx,"checked_at_kst":now.isoformat()}
    return title,"\n".join(L),payload
def clear():
    for p in (TITLE,BODY,DATA,PENDING,CONFIRMED):
        try:p.unlink()
        except FileNotFoundError:pass
def finalize():
    if not PENDING.exists() or not CONFIRMED.exists(): print("BOJ policy Telegram confirmation missing; pending state not finalized."); return
    c=json.loads(CONFIRMED.read_text())
    if c.get("status")!="confirmed" or c.get("lane")!="boj_policy": print("BOJ policy Telegram confirmation mismatch; pending state not finalized."); return
    STATE.parent.mkdir(exist_ok=True); STATE.write_text(PENDING.read_text()); print(f"Finalized BOJ policy state: {STATE}")
def main():
    ap=argparse.ArgumentParser(); ap.add_argument("--finalize",action="store_true"); a=ap.parse_args()
    if a.finalize: finalize(); return 0
    clear(); now=dt.datetime.now(KST); sigs=latest_signals(now); off=official(now); state=load_state(); OUT.mkdir(exist_ok=True)
    if not sigs:
        WATCH.write_text(f"BOJ 정책 선행감시: 새 고신뢰 인상 신호 없음 · 조회 {label(now)}\n"); print(json.dumps({"alerted":False,"reason":"no_signal"},ensure_ascii=False)); return 0
    s=sigs[0]; ok,reason=should(s,state,now); WATCH.write_text(f"BOJ 정책 선행감시: 후보 {s.stage}단계 · {s.source} · {s.title}\n판정: {'알림' if ok else '미알림'} — {reason}\n조회: {label(now)}\n")
    if not ok: print(json.dumps({"alerted":False,"reason":reason,"stage":s.stage},ensure_ascii=False)); return 0
    title,body,payload=build(s,reason,now,confirms(sigs,s),off,fx_context()); TITLE.write_text(title+"\n"); BODY.write_text(body+"\n"); DATA.write_text(json.dumps(payload,ensure_ascii=False,indent=2,default=str)+"\n")
    PENDING.write_text(json.dumps({"stage":s.stage,"route":s.route,"probability_pct":s.probability,"last_signal_key":s.key,"last_alert_at_kst":now.isoformat(),"last_published_at_kst":s.published.isoformat(),"last_source":s.source,"last_title":s.title},ensure_ascii=False,indent=2)+"\n")
    print(json.dumps({"alerted":True,"stage":s.stage,"route":s.route,"source":s.source,"probability_pct":s.probability,"reason":reason},ensure_ascii=False)); return 0
if __name__=="__main__": raise SystemExit(main())
