#!/usr/bin/env python3
"""IonQ / Elisity acquisition lifecycle: official-source, event-key, send-then-commit."""
from __future__ import annotations
import datetime as dt
import email.utils
import hashlib
import html
import json
import os
from pathlib import Path
import re
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from zoneinfo import ZoneInfo

ROOT=Path(__file__).resolve().parents[1]
STATE=ROOT/"data/ionq_elisity_watch_state.json"
OUT=ROOT/"out"
OUT.mkdir(exist_ok=True)
PENDING=OUT/"ionq_elisity_pending.json"
ALERT=OUT/"ionq_elisity_alert.html"
STATUS=OUT/"ionq_elisity_status.md"
KST=ZoneInfo("Asia/Seoul")
BASELINE="ionq-elisity:agreement:2026-10-12"
AGE_DAYS=14
OFFICIAL_IONQ_AGREEMENT="https://ionq.com/news/ionq-to-acquire-elisity-to-accelerate-zero-trust-for-the-quantum-era"
QUERIES=(
    'site:ionq.com/news/ Elisity IonQ acquisition',
    'site:investors.ionq.com/news/ Elisity IonQ acquisition',
    'site:sec.gov IonQ Elisity acquisition 8-K',
    'site:elisity.com/news/ IonQ Elisity acquisition',
)

def now_kst(): return dt.datetime.now(KST)
def clean(v):
    return re.sub(r"\s+"," ",html.unescape(re.sub(r"<[^>]*>"," ",v or ""))).strip()
def parse_date(v):
    try:
        x=email.utils.parsedate_to_datetime(v)
        if x.tzinfo is None: x=x.replace(tzinfo=dt.timezone.utc)
        return x.astimezone(KST)
    except Exception: return None
def get(url):
    req=urllib.request.Request(url,headers={"User-Agent":"Mozilla/5.0 IonQElisityWatch/1.0","Accept-Language":"en-US,en;q=0.9"})
    with urllib.request.urlopen(req,timeout=20) as r: return r.read().decode("utf-8","replace")
def query_url(q):
    return "https://news.google.com/rss/search?"+urllib.parse.urlencode({"q":q+" when:14d","hl":"en-US","gl":"US","ceid":"US:en"})
def publisher_allowed(p):
    p=p.strip().lower()
    # The article must originate with a primary-source publisher.
    return p in {"ionq","ionq, inc.","ionq investor relations","elisity","u.s. securities and exchange commission","sec.gov"}
def stage(title):
    t=clean(title).lower()
    if not ("elisity" in t and ("ionq" in t or "acquisition" in t or "merger" in t)): return None
    # Only a completed act is a new milestone: expectations, applications and
    # anticipated closing must not be reported as completion or approval.
    if re.search(r"\b(terminates|terminated|cancels|cancelled|abandons|abandoned)\b",t):
        return ("termination","인수 계약 종료",95)
    closing=bool(re.search(r"\b(completes|completed|closes|closed)\b",t) or
                 re.search(r"\b(announces|announced|official|successful)\s+(the\s+)?closing\b",t))
    closing_future=bool(re.search(
        r"\b(expected|expects|anticipates|planned|planning|pending|scheduled|set|due|will|may|might|could|aims|intends|seeks)\b.{0,45}\b(to\s+be\s+)?(close|closing|closes|closed|complete|completion|completes|completed)\b",t
    ) or re.search(r"\bto\s+be\s+(closed|completed)\b",t))
    if closing and not closing_future and any(x in t for x in ("acqui","deal","transaction")):
        return ("closing","인수 거래 종결",100)
    if ("regulatory" in t or "antitrust" in t or "clearance" in t) and ("approval" in t or "clearance" in t or "approved" in t):
        if re.search(r"\b(receives|received|obtains|obtained|secures|secured|grants|granted|approves|approved|clears|cleared|wins|won)\b",t) and not re.search(r"\b(approval|clearance)\s+(expected|pending|anticipated|planned|sought)\b",t):
            return ("regulatory","규제 승인",93)
    if ("shareholder" in t or "stockholder" in t) and ("approval" in t or "approved" in t):
        if re.search(r"\b(receives|received|obtains|obtained|secures|secured|grants|granted|approves|approved|wins|won)\b",t) and not re.search(r"\bapproval\s+(expected|pending|anticipated)\b",t):
            return ("shareholder","주주 승인",92)
    if ("agreement" in t or "terms" in t or "deal" in t) and re.search(r"\b(amends|amended|revises|revised|modifies|modified)\b",t):
        return ("amendment","거래 조건 변경",96)
    if ("earnout" in t or "earn-out" in t) and re.search(r"\b(paid|pays|achieves|achieved|earns|earned|receives|received)\b",t):
        return ("earnout","조건부 대가 실현",92)
    if any(x in t for x in ("revenue","customer deployment","integrated platform","cross-selling","cross selling","subscription","recurring revenue")):
        if re.search(r"\b(reports|reported|recognizes|recognized|records|recorded|launches|launched|deploys|deployed|signs|signed|wins|won|generates|generated|integrates)\b",t):
            return ("commercial","실제 고객·반복매출 변화",85)
    if ("to acquire" in t or "agreement to acquire" in t or "announces acquisition" in t):
        return ("agreement","인수 본계약 발표",70)
    return None

def extract(root,now):
    rows=[]
    for item in root.findall("./channel/item"):
        title=clean(item.findtext("title"))
        url=clean(item.findtext("link"))
        pub=clean(item.findtext("pubDate"))
        node=item.find("source")
        publisher=clean(node.text if node is not None else "")
        date=parse_date(pub)
        if not url or not date or not publisher_allowed(publisher): continue
        age=(now-date).total_seconds()/86400
        if not (-1<=age<=AGE_DAYS): continue
        result=stage(title)
        if result is None: continue
        key,stage_name,_confidence=result
        # A dated semantic stage key prevents a rehashed announcement from appearing new.
        identity=BASELINE if key=="agreement" else f"ionq-elisity:{key}:{date.date().isoformat()}"
        rows.append({"key":identity,"stage":stage_name,"title":title,"publisher":publisher,"url":url,"published_kst":date.isoformat(timespec="seconds")})
    return rows

def direct_official_baseline():
    # A live request to the canonical issuer document is mandatory; RSS may be empty.
    body=get(OFFICIAL_IONQ_AGREEMENT)
    plain=clean(body).lower()
    if not ("elisity" in plain and "ionq" in plain and "acquire" in plain):
        raise RuntimeError("Official IonQ release did not match the actual acquisition")
    return {"key":BASELINE,"stage":"인수 본계약 발표","title":"IonQ to Acquire Elisity to Accelerate Zero Trust for the Quantum Era","publisher":"IonQ 공식 보도자료","url":OFFICIAL_IONQ_AGREEMENT,"published_kst":"2026-10-12T00:00:00+09:00"}

def collect(now):
    rows=[]; notes=[]
    try:
        rows.append(direct_official_baseline())
        notes.append("IonQ 공식 계약 발표: 직접 열람·내용 검증 성공")
    except Exception as exc:
        notes.append(f"IonQ 공식 계약 발표: 직접 확인 실패 {type(exc).__name__}: {exc}")
    for query in QUERIES:
        try:
            parsed=extract(ET.fromstring(get(query_url(query))),now)
            rows+=parsed; notes.append(f"검색 확인 {query[:40]}: {len(parsed)}건")
        except Exception as exc:
            notes.append(f"원천 접근 실패 {query[:40]}: {type(exc).__name__}: {exc}")
    unique={}
    for row in sorted(rows,key=lambda x:(x["published_kst"],x["publisher"])):
        unique.setdefault(row["key"],row)
    return list(unique.values()),notes

def load():
    try:
        obj=json.loads(STATE.read_text(encoding="utf-8"))
        if isinstance(obj,dict) and isinstance(obj.get("seen"),dict): return obj
    except Exception: pass
    return {"seen":{}}
def report(rows,now):
    lines=[f"아이온큐·Elisity 인수 및 양자보안 중요 변화 | 조회 {now:%Y-%m-%d %H:%M KST}"]
    for row in rows[:3]:
        lines.extend([
            f"• 단계: {row['stage']}",
            f"• 당사자: IonQ / Elisity",
            "• 수익 연결: 인수 자체와 실제 보안 사용권·구독·고객 배치·교차판매 매출을 구분",
            "• 역풍: 전액 주식 대가 희석, 규제 지연, 인수 통합비, 기술·보안 인증, 고객 유지율",
            f"• 공식 1차 출처: {row['publisher']} · 공개 {row['published_kst'][:16].replace('T',' ')}",
            f"• 원문: {row['url']}",
        ])
    return html.escape("\n".join(lines))
def main():
    ALERT.unlink(missing_ok=True);PENDING.unlink(missing_ok=True)
    now=now_kst(); state=load()
    seen=state.setdefault("seen",{})
    seen.setdefault(BASELINE,{"stage":"인수 본계약 발표","event_date":"2026-10-12","status":"기준사건"})
    rows,notes=collect(now)
    if not any(row["key"]==BASELINE and row["publisher"]=="IonQ 공식 보도자료" for row in rows):
        raise RuntimeError("Official IonQ acquisition baseline inaccessible: refuse to report normal monitoring")
    news=[r for r in rows if r["key"] not in seen]
    status=[
        f"# IonQ Elisity 인수 감시 · {now:%Y-%m-%d %H:%M KST}",
        f"- 원천 후보: {len(rows)}건",f"- 신규 단계: {len(news)}건",
        f"- 발송 준비: {'예' if news else '아니오'}",
        "- 본계약은 기준사건이며 승인·종결·조건변경·매출 연결을 별도 감시",
        *[f"- {n}" for n in notes],
    ]
    STATUS.write_text("\n".join(status)+"\n",encoding="utf-8")
    pending={"seen":{**seen,**{r["key"]:{"stage":r["stage"],"published_kst":r["published_kst"],"url":r["url"]} for r in news}},"checked_at_kst":now.isoformat(timespec="seconds")}
    PENDING.write_text(json.dumps(pending,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
    if news: ALERT.write_text(report(news,now),encoding="utf-8")
    print(f"ionq_elisity_watch candidates={len(rows)} new={len(news)} alert={ALERT.exists()}")
    return 0
if __name__=="__main__":raise SystemExit(main())
