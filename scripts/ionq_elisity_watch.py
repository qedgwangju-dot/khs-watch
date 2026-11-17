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
OFFICIAL_IONQ_CLOSING="https://www.ionq.com/news/ionq-completes-acquisition-of-elisity-extending-quantum-security-for-enterprises-and-government"
CLOSING_KEY="ionq-elisity:closing:2026-11-03"
OFFICIAL_INDEXES=(("IonQ 공식 뉴스","https://www.ionq.com/news"),("Elisity 공식 뉴스","https://www.elisity.com/news"))
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

def official_url(value):
    """Do not turn a Google News relay or lookalike host into an official link."""
    try:
        u=urllib.parse.urlsplit(str(value or "").strip())
        if u.scheme!="https" or u.username or u.password or u.port not in (None,443):
            return ""
        if (u.hostname or "").lower() not in {
            "www.ionq.com","ionq.com","investors.ionq.com",
            "www.elisity.com","elisity.com","www.sec.gov","sec.gov",
        } or not u.path or u.path=="/":
            return ""
        return urllib.parse.urlunsplit(("https",u.netloc.lower(),u.path,u.query,""))
    except (ValueError,TypeError):
        return ""

def direct_official_closing(getter=None):
    """Validate issuer announcement independently of the Google News search feed."""
    raw=(getter or get)(OFFICIAL_IONQ_CLOSING)
    body=clean(raw).lower()
    if not ("ionq completes acquisition of elisity" in body
        and "completed its acquisition of elisity" in body
        and "november 4, 2026" in body):
        raise RuntimeError("IonQ official release did not confirm completed Elisity transaction")
    return {
        "key":CLOSING_KEY,"stage":"인수 거래 종결",
        "title":"IonQ Completes Acquisition of Elisity, Extending Quantum Security for Enterprises and Government",
        "publisher":"IonQ 공식 보도자료","url":OFFICIAL_IONQ_CLOSING,
        "published_kst":"2026-11-04","event_date":"2026-11-03",
    }

def published_day(source):
    """Take the article's publication date from primary-source metadata."""
    for expression in (
        r'["\x27]datePublished["\x27]\s*:\s*["\x27](20\d{2}-\d{2}-\d{2})',
        r'<time[^>]+datetime=["\x27](20\d{2}-\d{2}-\d{2})',
        r'(?:article:published_time|pubdate)[^>]{0,150}?content=["\x27](20\d{2}-\d{2}-\d{2})',
    ):
        found=re.search(expression,source,re.I|re.S)
        if found:
            try: return dt.date.fromisoformat(found.group(1))
            except ValueError: pass
    return None

def verified_official_indexes(now,getter=None):
    """Search original publishers in addition to delayed Google News discovery."""
    getter=getter or get
    rows=[];notes=[]
    for label,index in OFFICIAL_INDEXES:
        try:
            listing=getter(index)
            links=[]
            for m in re.finditer(r'<a\b[^>]*href=(["\x27])(?P<href>.*?)\1[^>]*>(?P<label>.*?)</a>',listing,re.I|re.S):
                title=clean(m.group("label"))
                if "elisity" not in title.lower() or stage(title) is None: continue
                url=official_url(urllib.parse.urljoin(index,html.unescape(m.group("href"))))
                if url and url not in (official_url(OFFICIAL_IONQ_AGREEMENT),official_url(OFFICIAL_IONQ_CLOSING)):
                    links.append((url,title))
            passed=0
            for url,title in list(dict.fromkeys(links))[:20]:
                try:
                    article=getter(url)
                    plain=clean(article).lower()
                    if not ("ionq" in plain and "elisity" in plain): continue
                    result=stage(title)
                    if result is None: continue
                    day=published_day(article)
                    if day is None or not 0<=(now.date()-day).days<=AGE_DAYS: continue
                    key,stage_name,_=result
                    digest=hashlib.sha256(url.encode()).hexdigest()[:16]
                    rows.append({"key":f"ionq-elisity:{key}:{digest}","stage":stage_name,
                        "title":title,"publisher":label,"url":url,
                        "published_kst":day.isoformat(),"event_date":day.isoformat()})
                    passed+=1
                except Exception as exc:
                    notes.append(f"{label} 상세 원문 접근 실패: {type(exc).__name__}")
            notes.append(f"{label}: 확인된 후속 원문 {passed}건")
        except Exception as exc:
            notes.append(f"{label}: 공식 뉴스 목록 접근 실패 {type(exc).__name__}")
    return rows,notes

def already_seen(seen,row):
    key=str(row.get("key") or "")
    if key in seen: return True
    # November 4 was the RSS publication date, not the November 3 closing date.
    # Respect the earlier, already delivered Nov 4 key as the same one-time event.
    return bool(key==CLOSING_KEY and any(
        k.startswith("ionq-elisity:closing:") for k in seen
    ))

def verify_telegram_ack(reply,chat):
    """Require positive message_id and matching destination, without exposing chat IDs."""
    record=reply.get("result") or {}
    mid=record.get("message_id")
    actual=record.get("chat") or {}
    if reply.get("ok") is not True or type(mid) is not int or mid<=0:
        raise RuntimeError("Telegram sendMessage acknowledgment missing")
    destination=str(chat).strip()
    if destination.lstrip("-").isdigit():
        matched=str(actual.get("id"))==destination
    elif destination.startswith("@"):
        matched=str(actual.get("username") or "").lower()==destination[1:].lower()
    else:
        raise RuntimeError("Invalid configured Telegram destination")
    if not matched:
        raise RuntimeError("Telegram chat.id differs from configured destination")
    return mid

def collect(now):
    rows=[];notes=[];official_ok=0
    try:
        rows.append(direct_official_baseline())
        official_ok+=1
        notes.append("IonQ 기존 인수 본계약: 공식 원문 직접 확인")
    except Exception as exc:
        notes.append(f"IonQ 기존 인수 본계약 공식 조회 실패: {type(exc).__name__}")
    # Explicit primary-source watch closes the 13-day Google RSS discovery gap.
    if 0<=(now.date()-dt.date(2026,11,4)).days<=AGE_DAYS:
        try:
            rows.append(direct_official_closing())
            official_ok+=1
            notes.append("IonQ 인수 종결: 공식 원문 확인, 실제 거래일 2026-11-03")
        except Exception as exc:
            notes.append(f"IonQ 인수 종결 공식 조회·검증 실패: {type(exc).__name__}")
    originals,observations=verified_official_indexes(now)
    rows+=originals;notes+=observations
    official_ok+=len(originals)
    for query in QUERIES:
        try:
            candidates=extract(ET.fromstring(get(query_url(query))),now)
            verified=0
            for row in candidates:
                url=official_url(row["url"])
                if not url or url in (official_url(OFFICIAL_IONQ_AGREEMENT),official_url(OFFICIAL_IONQ_CLOSING)):
                    continue
                try:
                    page=get(url)
                    if not ("ionq" in clean(page).lower() and "elisity" in clean(page).lower()):
                        continue
                    date=published_day(page)
                    if date is None or not 0<=(now.date()-date).days<=AGE_DAYS: continue
                    kind=stage(row["title"])
                    if kind is None: continue
                    digest=hashlib.sha256(url.encode()).hexdigest()[:16]
                    rows.append({**row,"key":f"ionq-elisity:{kind[0]}:{digest}",
                        "url":url,"published_kst":date.isoformat(),"event_date":date.isoformat()})
                    verified+=1
                except Exception as exc:
                    notes.append(f"RSS 후보 공식 원문 재확인 실패: {type(exc).__name__}")
            notes.append(f"Google 뉴스 검색 {query[:32]}: 후보 {len(candidates)}건, 직접 검증 {verified}건")
        except Exception as exc:
            notes.append(f"Google 뉴스 참고 조회 실패 {query[:32]}: {type(exc).__name__}")
    if not official_ok:
        raise RuntimeError("IonQ 공식 원문 전체 접근 실패: 정상 감시·중복 상태 갱신 거부")
    unique={}
    for row in sorted(rows,key=lambda x:(x["published_kst"],x["publisher"])):
        unique.setdefault(row["key"],row)
    return list(unique.values()),notes


def load():
    try:
        obj=json.loads(STATE.read_text(encoding="utf-8"))
    except (OSError,ValueError) as exc:
        raise RuntimeError("IonQ 기존 중복방지 상태 접근 실패: 재발송을 막기 위해 중단") from exc
    if not isinstance(obj,dict) or not isinstance(obj.get("seen"),dict):
        raise RuntimeError("IonQ 중복방지 상태 형식 오류: 재발송 차단")
    return obj


def report(rows,now):
    esc=lambda v:html.escape(str(v),quote=True)
    lines=[esc(f"아이온큐·Elisity 인수 및 양자보안 중요 변화 | 조회 {now:%Y-%m-%d %H:%M KST}")]
    for row in rows[:3]:
        url=official_url(row.get("url"))
        if not url: raise ValueError("검증된 공식 원문 URL 누락: Telegram 전송 거부")
        lines.extend([
            esc(f"• 단계: {row['stage']}"),
            "• 당사자: IonQ / Elisity",
            "• 수익 연결: 인수와 실제 보안 사용권·구독·고객 배치·교차판매 매출을 구분",
            "• 역풍: 전액 주식 대가 희석, 인수 통합비, 기술·보안 인증, 고객 유지율",
            esc(f"• 공식 1차 출처: {row['publisher']} · 공개 {row['published_kst'][:16].replace('T',' ')}"),
        ])
        if row.get("event_date") and row["event_date"]!=row["published_kst"][:10]:
            lines.append(esc(f"• 실제 거래일: {row['event_date']}"))
        lines.append(f'• 원문: <a href="{esc(url)}">원문</a>')
    message="\n".join(lines)
    if len(message)>4096:
        raise ValueError("Telegram 메시지 길이 초과: 확정 원문 누락 없이 검토 필요")
    return message


def main():
    ALERT.unlink(missing_ok=True);PENDING.unlink(missing_ok=True)
    now=now_kst();state=load()
    seen=state["seen"]
    if BASELINE not in seen:
        raise RuntimeError("IonQ 기존 계약 기준사건 누락: 중복 재발송 위험으로 중단")
    rows,notes=collect(now)
    news=[row for row in rows if not already_seen(seen,row)]
    status=[
        f"# IonQ Elisity 인수 감시 · {now:%Y-%m-%d %H:%M KST}",
        f"- 공식 원문 후보: {len(rows)}건",f"- 신규 단계: {len(news)}건",
        f"- 발송 준비: {'예' if news else '아니오'}",
        "- 인수 완료와 실제 구독·고객·반복매출을 구분해 감시",
        "- Google 뉴스 RSS는 발견용이며 직접 확인한 공식 원문만 Telegram에 발송",
        *[f"- {n}" for n in notes],
    ]
    STATUS.write_text("\n".join(status)+"\n",encoding="utf-8")
    if news:
        pending={**state,"seen":{**seen,**{
            row["key"]:{"stage":row["stage"],"published_kst":row["published_kst"],
                "event_date":row.get("event_date",row["published_kst"][:10]),
                "url":row["url"]} for row in news}},
            "checked_at_kst":now.isoformat(timespec="seconds")}
        PENDING.write_text(json.dumps(pending,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
        ALERT.write_text(report(news,now),encoding="utf-8")
    # No new event => no pending commit and no duplicate Telegram transmission.
    print(f"ionq_elisity_watch official_candidates={len(rows)} new={len(news)} alert={ALERT.exists()}")
    return 0


if __name__=="__main__":raise SystemExit(main())
