#!/usr/bin/env python3
"""Google Quantum AI magic-state lifecycle watch. Baseline is NOT a new event."""
from __future__ import annotations
import datetime as dt
import email.utils
import hashlib
import html
import json
from pathlib import Path
import re
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from zoneinfo import ZoneInfo

ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/"out"
OUT.mkdir(exist_ok=True)
STATE=ROOT/"data/google_quantum_magic_watch_state.json"
PENDING=OUT/"google_quantum_magic_pending.json"
ALERT=OUT/"google_quantum_magic_alert.html"
STATUS=OUT/"google_quantum_magic_status.md"
KST=ZoneInfo("Asia/Seoul")
BASELINE_DATE=dt.date(2026,10,15)
BASE_KEY="google-qec:willow:magic-state-cultivation:2026-10-15"
BASE_URL="https://blog.google/innovation-and-ai/models-and-research/quantum-computing/magic-state-cultivation-quantum-computing/"
FEEDS=(
 ("Google Quantum AI 공식 피드","https://blog.google/innovation-and-ai/models-and-research/quantum-computing/rss/"),
 ("Google 공식 블로그 피드","https://blog.google/rss/"),
 ("Google Research 공식 피드","https://research.google/blog/rss/"),
)
HOSTS={"blog.google","research.google","www.research.google"}
LOOKBACK_DAYS=45

def now_kst():
    return dt.datetime.now(KST)

def clean(s):
    return re.sub(r"\s+"," ",html.unescape(re.sub(r"<[^>]*>"," ",s or ""))).strip()

def canonical(url):
    try:
        v=urllib.parse.urlsplit(url.strip())
        if v.scheme!="https" or v.hostname not in HOSTS:
            return ""
        return urllib.parse.urlunsplit(("https",v.netloc.lower(),v.path.rstrip("/")+"/","",""))
    except (ValueError,AttributeError):
        return ""

def fetch(url):
    req=urllib.request.Request(url,headers={"User-Agent":"Mozilla/5.0 (compatible; QECWatch/1.0)","Accept-Language":"en-US,en;q=0.8"})
    with urllib.request.urlopen(req,timeout=24) as r:
        if not canonical(r.geturl()):
            raise RuntimeError("Google source redirected outside allowlisted official domains")
        return r.read().decode("utf-8","replace")

def parse_date(s):
    try:
        value=email.utils.parsedate_to_datetime(s)
        return value.astimezone(KST) if value.tzinfo else value.replace(tzinfo=KST)
    except Exception:
        try:
            value=dt.datetime.fromisoformat(s.replace("Z","+00:00"))
            return value.astimezone(KST) if value.tzinfo else value.replace(tzinfo=KST)
        except Exception:
            return None

def parse_feed(text):
    root=ET.fromstring(text)
    rows=[]
    if root.tag.endswith("rss") or root.find("channel") is not None:
        for item in root.findall("./channel/item"):
            rows.append({
                "title":clean(item.findtext("title")),
                "summary":clean(item.findtext("description")),
                "url":canonical(item.findtext("link") or ""),
                "published":parse_date(item.findtext("pubDate") or "")
            })
    elif root.tag.endswith("feed"):
        n="{http://www.w3.org/2005/Atom}"
        for item in root.findall(n+"entry"):
            link=next((e.get("href","") for e in item.findall(n+"link") if e.get("rel","alternate")=="alternate"),"")
            rows.append({
                "title":clean(item.findtext(n+"title")),
                "summary":clean(item.findtext(n+"summary") or item.findtext(n+"content")),
                "url":canonical(link),
                "published":parse_date(item.findtext(n+"published") or item.findtext(n+"updated") or "")
            })
    else:
        raise ValueError("Unsupported Google feed format")
    return [x for x in rows if x["url"] and x["published"]]

def topic(text):
    return bool(re.search(r"magic[ -]state|cultivation|logical[ -]t[ -]gate|non[ -]clifford",text,re.I))

def stage(title,summary):
    t=clean(title).lower()
    s=clean(title+" "+summary).lower()
    if not topic(s):
        return None
    if re.search(r"\b(aims?|plans?|planned|proposes?|proposed|predicts?|expects?|expected|could|may|might|will|targets?|forecast|simulation|simulated)\b",t):
        return None
    if re.search(r"\b(retracts?|retracted|withdraws?|withdrawn|corrects?|corrected|fails? replication|replication failure)\b",t):
        return "과학적 정정·재현성 변화"
    if not re.search(r"\b(demonstrates?|demonstrated|achieves?|achieved|reports?|reported|raises?|raised|improves?|improved|reduces?|reduced|integrates?|integrated|implements?|implemented|deploys?|deployed|validates?|validated|reproduces?|reproduced|realizes?|realized)\b",t):
        return None
    if any(x in s for x in ("40-fold","40x","40 times")) and re.search(r"99\.99(?!\d)",s) and not re.search(r"\b(new|second|subsequent|higher|larger)\b",t):
        return None
    if re.search(r"(?:real[ -]time|fault[ -]tolerant|logical)\s+(?:non[ -]clifford|t[ -]gate)|integrat\w*\s+.*?t[ -]gate",s):
        return "논리적 T 게이트 실제 연산 적용"
    if re.search(r"commercial contract|paid deployment|first paying customer|signed supply agreement",s):
        return "유료 고객·상용화 확인"
    if re.search(r"distance[ -]?(?:[7-9]|[1-9]\d)\b",s) and "cultivat" in s:
        return "오류정정 코드 확장 실증"
    if re.search(r"(?:more than|over|above|using|with)\s+(?:5[5-9]|[6-9]\d|\d{3,})\s+(?:physical\s+)?qubits?",s) and "cultivat" in s:
        return "매직 상태 공정 물리 큐비트 확대"
    a=re.findall(r"\b(\d+(?:\.\d+)?)\s*%\s*(?:of\s+attempts\s+)?(?:retained|retention|acceptance|post.selection\s+yield)",s)
    a+=re.findall(r"(?:retains?|retention|acceptance|post.selection\s+yield)\s*(?:of\s+)?(\d+(?:\.\d+)?)\s*%",s)
    if any(float(x)>8 for x in a):
        return "후선택 통과율 개선 실증"
    a=re.findall(r"\b(\d{2}\.\d{2,})\s*%\s*(?:logical\s+)?(?:t[ -]state\s+)?fidelity",s)
    a+=re.findall(r"(?:logical\s+)?(?:t[ -]state\s+)?fidelity\s*(?:of\s+)?(\d{2}\.\d{2,})\s*%",s)
    if any(float(x)>99.99 for x in a):
        return "논리적 T-상태 충실도 개선 실증"
    if re.search(r"\b(leakage|population leakage)\b",s) and re.search(r"\b(removes?|removed|reduces?|reduced|suppresses?|suppressed|eliminates?|eliminated)\b",s):
        return "큐비트 누설 억제 실증"
    if "cultivat" in s and re.search(r"\b(realtime decoder|real-time decoding|continuous operation)\b",s):
        return "오류정정 실시간화 실증"
    return None

def collect(now,getter=fetch):
    notes=[]
    found={}
    healthy=0
    for label,url in FEEDS:
        try:
            feed=parse_feed(getter(url))
            healthy+=1
            notes.append(f"{label}: 조회 성공, {len(feed)}건")
        except Exception as exc:
            notes.append(f"{label}: 원천 오류 {type(exc).__name__} {str(exc)[:100]}")
            continue
        for item in feed:
            if not (BASELINE_DATE<item["published"].date()<=now.date()):
                continue
            if item["published"]>now+dt.timedelta(hours=1) or (now-item["published"]).days>LOOKBACK_DAYS:
                continue
            url=item["url"]
            if url==BASE_URL or url in found or not topic(item["title"]+" "+item["summary"]):
                continue
            kind=stage(item["title"],item["summary"])
            if not kind:
                continue
            try:
                if not topic(clean(getter(url))):
                    notes.append("공식 원문 내용 불일치: "+url)
                    continue
            except Exception as exc:
                notes.append(f"공식 원문 직접 열람 실패: {url} {type(exc).__name__}")
                continue
            found[url]={
                "key":"google-qec:"+hashlib.sha256(url.encode()).hexdigest()[:24],
                "stage":kind,"url":url,"title":item["title"],
                "published_kst":item["published"].isoformat(timespec="seconds")
            }
    if not healthy:
        raise RuntimeError("All Google official feeds failed: "+"; ".join(notes))
    return sorted(found.values(),key=lambda x:x["published_kst"]),notes

def load_state():
    try:
        state=json.loads(STATE.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return {"seen":{}}
    except (OSError,ValueError) as exc:
        raise RuntimeError("Existing quantum watch state unreadable; refuse replay") from exc
    if not isinstance(state,dict) or not isinstance(state.get("seen"),dict):
        raise RuntimeError("Existing quantum watch state invalid; refuse replay")
    return state

def render(new,now):
    lines=[
        "[Google Quantum AI] 매직 상태·오류정정 기술 단계 변화",
        "기준: 2026-10-15 Willow 105 물리 큐비트·실험 54개·오류 약 40배 절감·T-상태 충실도 99.99%·후선택 유지율 8%",
        "기존 논문 재전송이 아닌 새로운 공식 후속 단계입니다."
    ]
    for x in new:
        lines.extend((
            "", "신규 단계: "+x["stage"],
            "공개 시각: "+x["published_kst"][:16].replace("T"," ")+" KST",
            "사업 판단: 실험 성과와 양산·상용계약·실제 매출은 구분",
            "후속 점검: 후선택 유지율·논리 오류율·누설·코드 규모·실시간 실행·유상 고객",
            "공식 원문: "+x["url"]
        ))
    lines.append("조회: "+now.strftime("%Y-%m-%d %H:%M KST"))
    return html.escape("\n".join(lines))

def main():
    ALERT.unlink(missing_ok=True)
    PENDING.unlink(missing_ok=True)
    now=now_kst()
    previous=load_state()
    seen=dict(previous.get("seen") or {})
    seen.setdefault(BASE_KEY,{"stage":"2026-10-15 Science 최초 실증","url":BASE_URL,"status":"기준사건"})
    try:
        rows,notes=collect(now)
    except Exception as exc:
        STATUS.write_text("# Google Quantum AI 공식 원천 조회 실패\n- "+str(exc)+"\n",encoding="utf-8")
        raise
    new=[x for x in rows if x["key"] not in seen][:2]
    pending={
        **previous,
        "seen":{**seen,**{x["key"]:{"stage":x["stage"],"published_kst":x["published_kst"],"url":x["url"]} for x in new}},
        "checked_at_kst":now.isoformat(timespec="seconds"),
        "official_feeds_ok":sum("조회 성공" in n for n in notes),
    }
    PENDING.write_text(json.dumps(pending,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
    if new:
        ALERT.write_text(render(new,now),encoding="utf-8")
    STATUS.write_text("\n".join([
        "# Google Quantum AI 마법 상태 연구 감시",
        "- 조회: "+now.isoformat(timespec="seconds"),
        "- 실증 후속 후보: "+str(len(rows))+"건",
        "- 신규 단계: "+str(len(new))+"건",
        "- 2026-10-15 Science 기준사건 중복 차단",
        *["- "+x for x in notes]
    ])+"\n",encoding="utf-8")
    print(f"google_quantum_magic sources={pending['official_feeds_ok']} candidates={len(rows)} new={len(new)} alert={bool(new)}")

if __name__=="__main__":
    main()
