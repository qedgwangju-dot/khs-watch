#!/usr/bin/env python3
"""Anthropic/Harvard quantum-circuit milestones: official-source gated, no baseline replay."""
from __future__ import annotations
import datetime as dt
import hashlib
import html
from html.parser import HTMLParser
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
STATE=ROOT/"data/quantum_ai_circuit_watch_state.json"
PENDING=OUT/"quantum_ai_circuit_pending.json"
ALERT=OUT/"quantum_ai_circuit_alert.html"
STATUS=OUT/"quantum_ai_circuit_status.md"
KST=ZoneInfo("Asia/Seoul")
CUTOFF=dt.date(2026,10,16)
PREPRINT="2610.22367"
ANTHROPIC_ORIGINAL="https://www.anthropic.com/research/designing-efficient-quantum-circuits"
QUERA_ORIGINAL="https://www.quera.com/press-releases/quera-computing-uses-ai-to-automate-a-critical-quantum-computer-subsystem-enabling-the-acceleration-of-commercial-grade-quantum-computing-deployments-from-quera"
INDEXES=(
 ("Anthropic 공식 연구","https://www.anthropic.com/research"),
 ("Anthropic 공식 보도","https://www.anthropic.com/news"),
 ("QuEra 공식 연구·뉴스","https://www.quera.com/news"),
)
ARXIV="https://export.arxiv.org/api/query?id_list="+PREPRINT
CODE_RELEASES="https://api.github.com/repos/andigu/uncompute/releases?per_page=20"
GOOD_HOSTS={"www.anthropic.com","anthropic.com","www.quera.com","quera.com"}
HEADERS={"User-Agent":"Mozilla/5.0 (compatible; QuantumCircuitMilestoneWatch/1.0)","Accept":"text/html,application/atom+xml,application/json"}

def now_kst():
    return dt.datetime.now(KST)

def get(url):
    req=urllib.request.Request(url,headers=HEADERS)
    with urllib.request.urlopen(req,timeout=22) as response:
        return response.read(2500000).decode("utf-8","replace")

def official_url(raw,base=""):
    url=urllib.parse.urljoin(base,html.unescape(raw.strip()))
    u=urllib.parse.urlsplit(url)
    if u.scheme!="https" or u.hostname not in GOOD_HOSTS:
        return ""
    if not (u.path.startswith("/research/") or u.path.startswith("/news/") or u.path.startswith("/press-releases/")):
        return ""
    return urllib.parse.urlunsplit(("https",u.netloc.lower(),u.path.rstrip("/"),"",""))

def text_only(s):
    s=re.sub(r"<(script|style|svg)\b[^>]*>.*?</\1>"," ",s or "",flags=re.I|re.S)
    return re.sub(r"\s+"," ",html.unescape(re.sub(r"<[^>]*>"," ",s))).strip()

class Links(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.current=None
        self.depth=0
        self.found=[]
    def handle_starttag(self,tag,attrs):
        if tag.lower()=="a" and self.current is None:
            self.current={"href":dict(attrs).get("href",""),"words":[]}
            self.depth=1
        elif self.current and tag.lower()=="a":
            self.depth+=1
    def handle_data(self,data):
        if self.current:
            self.current["words"].append(data)
    def handle_endtag(self,tag):
        if self.current and tag.lower()=="a":
            self.depth-=1
            if self.depth==0:
                self.found.append((self.current["href"]," ".join(self.current["words"])))
                self.current=None

def published_date(body):
    patterns=(
        r'["\x27]datePublished["\x27]\s*:\s*["\x27]([^"\x27]+)',
        r'<meta[^>]+(?:property|name)=["\x27](?:article:published_time|pubdate|datePublished)["\x27][^>]+content=["\x27]([^"\x27]+)',
        r'<time[^>]+datetime=["\x27]([^"\x27]+)',
    )
    for pat in patterns:
        hit=re.search(pat,body,re.I)
        if hit:
            try:
                stamp=dt.datetime.fromisoformat(hit.group(1).replace("Z","+00:00"))
                return stamp.date() if not stamp.tzinfo else stamp.astimezone(KST).date()
            except ValueError:
                pass
    match=re.search(r'\b(Oct(?:ober)?|Nov(?:ember)?|Dec(?:ember)?)\s+(\d{1,2}),?\s+(2026|2027|2028)\b',text_only(body)[:10000],re.I)
    if match:
        month={"oct":10,"nov":11,"dec":12}[match.group(1)[:3].lower()]
        return dt.date(int(match.group(3)),month,int(match.group(2)))
    return None

def stage(title,body):
    title=text_only(title).lower()
    body=text_only(body).lower()[:32000]
    combined=title+" "+body
    if not re.search(r"\b(quantum|qubit|toffoli|qpu|fault.tolerant)\b",combined):
        return None
    if not re.search(r"\b(claude|anthropic|artificial intelligence|ai agent|large language model|llm)\b",combined):
        return None
    if re.search(r"\b(retract|retraction|withdraw|correction|corrected|replication failed|could not reproduce)\b",title):
        return "논문·결과 정정 또는 재현 실패"
    if re.search(r"\b(contract|paid|license|commercial|customer|production deployment|revenue)\b",title) and re.search(r"\b(quantum|circuit|compiler|qubit)\b",title):
        return "양자 설계·제어 유료 계약 또는 상용 채택"
    if re.search(r"\b(replicat\w*|reproduc\w*|independent validation|independently verified)\b",title):
        return "독립 재현·검증"
    if re.search(r"\b(hardware|processor|computer|qpu|physical qubits|laser control)\b",title) and re.search(r"\b(demonstrat|deploy|implement|execut|run|control|automat|operate|tested|validated|stabili)\w*",title):
        if re.search(r"\b(demonstrat|deploy|implement|execut|run|control|automat|operat|test|validat)\w*",body):
            return "실물 양자 하드웨어 적용·자동화"
    if re.search(r"\b(circuit|toffoli|quantum algorithm|quantum compiler)\b",title) and re.search(r"\b(reduc|improv|cut|fewer|efficient|record|breakthrough|optimiz)\w*",title):
        if re.search(r"\b(toffoli|qubit|gate count|gate depth)\b",body) and re.search(r"\b(\d+(?:\.\d+)?\s*(?:times|x|fold|%|million|thousand)|\d[\d,]{3,})\b",body):
            if re.search(r"\b(predict|propos|could|might|may|will|plan)\w*",title):
                return None
            return "AI 양자회로 자원 절감 후속 실증"
    return None

def baseline_event(url):
    return url.rstrip("/") in {ANTHROPIC_ORIGINAL,QUERA_ORIGINAL}

def collect(now,getter=get):
    notes=[]
    found={}
    success=0
    primary_sources_ok=0
    for label,index in INDEXES:
        try:
            html_text=getter(index)
            success+=1
            primary_sources_ok+=1
            parser=Links()
            parser.feed(html_text)
            possible={}
            for href,title in parser.found:
                link=official_url(href,index)
                if link and not baseline_event(link) and re.search(r"quantum|qubit|toffoli|claude|circuit|fault.tolerant",title,re.I):
                    possible.setdefault(link,text_only(title))
            notes.append(f"{label}: 공식 목록 조회 성공, 주제 후보 {len(possible)}건")
        except Exception as exc:
            notes.append(f"{label}: 조회 실패 {type(exc).__name__} {str(exc)[:90]}")
            continue
        for link,title in list(possible.items())[:15]:
            if link in found:
                continue
            try:
                detail=getter(link)
                date=published_date(detail)
                if date is None:
                    notes.append("게시일 미확인으로 보류: "+link)
                    continue
                if date<=CUTOFF or date>now.date():
                    continue
                kind=stage(title,detail)
                if not kind:
                    continue
                found[link]={"key":"ai-qc:"+hashlib.sha256(link.encode()).hexdigest()[:24],
                    "title":title,"stage":kind,"date":date.isoformat(),
                    "url":link,"evidence":"공식 기업·연구기관 발표"}
            except Exception as exc:
                notes.append(f"공식 원문 조회 실패: {link} {type(exc).__name__}")
    try:
        raw=getter(ARXIV)
        root=ET.fromstring(raw)
        n="{http://www.w3.org/2005/Atom}"
        entries=root.findall(n+"entry")
        if not entries:
            raise ValueError("Empty arXiv atom entry")
        entry=entries[0]
        title=text_only(entry.findtext(n+"title") or "")
        if "quantum circuits" not in title.lower():
            raise ValueError("Unexpected arXiv paper")
        refs=" ".join((entry.findtext(n+"id") or "",*[(e.attrib.get("href") or "") for e in entry.findall(n+"link")]))
        revisions=[int(x) for x in re.findall(r"2610\.22367v(\d+)",refs)]
        revision=max(revisions,default=1)
        notes.append("arXiv 원문 버전 조회 성공: v"+str(revision))
        success+=1
        if revision>1:
            url="https://arxiv.org/abs/"+PREPRINT+"v"+str(revision)
            found[url]={"key":"ai-qc:arxiv:"+PREPRINT+":v"+str(revision),
                "title":"Discovering state-of-the-art quantum circuits with large language models",
                "stage":"논문 개정판 공개(개선·정정 내용 별도 검증 필요)",
                "date":(entry.findtext(n+"updated") or now.isoformat())[:10],
                "url":url,"evidence":"arXiv 공식 논문 개정"}
    except Exception as exc:
        notes.append(f"arXiv 원문 조회 실패: {type(exc).__name__} {str(exc)[:100]}")
    try:
        items=json.loads(getter(CODE_RELEASES))
        if not isinstance(items,list):
            raise ValueError("Unexpected GitHub release structure")
        success+=1
        notes.append(f"연구자 공식 공개코드: 릴리스 {len(items)}건 확인")
        for entry in items:
            if entry.get("draft") or entry.get("prerelease"):
                continue
            date=(entry.get("published_at") or "")[:10]
            if not date or date<=CUTOFF.isoformat() or date>now.date().isoformat():
                continue
            title=str(entry.get("name") or entry.get("tag_name") or "")
            body=str(entry.get("body") or "")
            if not re.search(r"\b(toffoli|qubit|circuit|proof|lean|benchmark|replicat|correct|evalua)\w*",title+" "+body,re.I):
                continue
            url=entry.get("html_url") or ""
            if not url.startswith("https://github.com/andigu/uncompute/releases/"):
                continue
            found[url]={"key":"ai-qc:official-code:"+hashlib.sha256(url.encode()).hexdigest()[:24],
                "title":title,"stage":"연구자 검증코드 정식 릴리스(성능 개선 여부 별도 확인)",
                "date":date,"url":url,"evidence":"논문 저자 공개 저장소"}
    except Exception as exc:
        notes.append(f"연구자 공개코드 조회 실패: {type(exc).__name__} {str(exc)[:100]}")
    if not success:
        raise RuntimeError("모든 공식 원천 조회 실패: "+"; ".join(notes))
    if not primary_sources_ok or success<2:
        raise RuntimeError("공식 연구·보도 원천 부족, 정상조회 판정 차단: "+ "; ".join(notes))
    return sorted(found.values(),key=lambda x:(x["date"],x["key"])),notes,success

def load_state():
    try:
        state=json.loads(STATE.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise RuntimeError("기존 중복방지 상태 파일 없음: 재전송 차단") from exc
    except (OSError,ValueError) as exc:
        raise RuntimeError("기존 중복방지 상태 손상: 재전송 방지 위해 중단") from exc
    if not isinstance(state,dict) or not isinstance(state.get("seen"),dict):
        raise RuntimeError("중복방지 상태 형식 불일치: 중단")
    return state

def render(events,now):
    lines=["[Anthropic·Harvard 양자회로 최적화] 새 기술 단계",
        "기준사건: 2026-10-16 Claude Mythos 5 회로 설계 연구. 서로 다른 53시간 타원곡선 재설계와 Toffoli 510만→44만 개 절감을 혼합하지 않습니다.",
        "최초 논문 재전송이 아니라 공식 후속 변화를 감지했습니다."]
    for x in events:
        lines.extend(("", "변화: "+x["stage"], "확인된 제목: "+x["title"],
            "공개일: "+x["date"],"단계: "+x["evidence"],
            "의미: 설계·시뮬레이션, 실제 하드웨어 적용, 유료 고객·매출을 구분해서 판단",
            "검증 원문: "+x["url"]))
    lines.append("조회: "+now.strftime("%Y-%m-%d %H:%M KST"))
    return html.escape("\n".join(lines))

def main():
    ALERT.unlink(missing_ok=True)
    PENDING.unlink(missing_ok=True)
    now=now_kst()
    previous=load_state()
    seen=dict(previous["seen"])
    seen.setdefault("ai-qc:baseline:anthropic-2026-10-16",{"url":ANTHROPIC_ORIGINAL,"status":"최초 연구 기준사건"})
    seen.setdefault("ai-qc:baseline:arxiv:2610.22367v1",{"url":"https://arxiv.org/abs/2610.22367","status":"최초 논문 기준사건"})
    seen.setdefault("ai-qc:baseline:quera-2026-08-27",{"url":QUERA_ORIGINAL,"status":"기존 물리 하드웨어 실증 기준사건"})
    try:
        rows,notes,healthy=collect(now)
    except Exception as exc:
        STATUS.write_text("# Anthropic 양자회로 공식 원천 장애\n- "+str(exc)+"\n",encoding="utf-8")
        raise
    fresh=[x for x in rows if x["key"] not in seen][:2]
    pending={**previous,"seen":{**seen,**{x["key"]:x for x in fresh}},
        "checked_at_kst":now.isoformat(timespec="seconds"),
        "official_sources_ok":healthy,"official_sources_total":len(INDEXES)+2}
    PENDING.write_text(json.dumps(pending,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
    if fresh:
        ALERT.write_text(render(fresh,now),encoding="utf-8")
    STATUS.write_text("\n".join(["# Anthropic·Harvard AI 양자회로 단계 감시",
        "- 조회: "+now.isoformat(timespec="seconds"),
        f"- 공식 조회 성공: {healthy}/{len(INDEXES)+2}",
        f"- 기술단계 후보: {len(rows)}건, 신규 알림: {len(fresh)}건",
        "- 최초 논문·기존 QuEra 자동화는 중복 알림 차단",
        *["- "+x for x in notes]])+"\n",encoding="utf-8")
    print(f"quantum_ai_circuit sources={healthy}/{len(INDEXES)+2} candidates={len(rows)} new={len(fresh)} alert={bool(fresh)}")

if __name__=="__main__":
    main()
