#!/usr/bin/env python3
from __future__ import annotations

import datetime as dt
import hashlib
import html
import json
import re
import urllib.parse
import xml.etree.ElementTree as ET
from email.utils import parsedate_to_datetime
from pathlib import Path

import requests

OUT = Path("out")
STATE = Path("data/us_hyperscaler_company_issue_state.json")
PENDING = OUT / "us_hyperscaler_company_issue_pending_state.json"
ALERT = OUT / "us_hyperscaler_company_issue_alert.txt"
STATUS = OUT / "us_hyperscaler_company_issue_status.md"

HEADERS = {"User-Agent":"khs-watch/1.0 (+https://github.com/qedgwangju-dot/khs-watch)"}
MAX_AGE_DAYS = 7
ACTIVE_DAYS = 30
FORMAT_VERSION = 1

COMPANY_QUERIES = {
    "Microsoft": [
        '"Microsoft" data center fine permit generator environmental lawsuit',
        '"Microsoft-backed" data center permit fine generator',
        'Nebius Microsoft data center permit fine generator',
    ],
    "Amazon/AWS": [
        '"AWS" data center fine permit generator environmental lawsuit',
        '"Amazon" data center permit fine generator community',
    ],
    "Google": [
        '"Google" data center fine permit generator environmental lawsuit',
        '"Google-backed" data center permit environmental',
    ],
    "Meta": [
        '"Meta" data center fine permit generator environmental lawsuit',
        '"Meta" data center community opposition permit',
    ],
    "Oracle": [
        '"Oracle" data center fine permit generator environmental lawsuit',
        '"Oracle-backed" data center permit environmental',
    ],
    "OpenAI/Stargate": [
        '"OpenAI" data center fine permit generator environmental lawsuit',
        '"Stargate" data center permit fine environmental',
    ],
    "xAI": [
        '"xAI" data center fine permit generator environmental lawsuit',
        '"xAI" gas turbine permit data center',
    ],
    "QTS": [
        '"QTS" data center fine permit environmental lawsuit',
    ],
    "CoreWeave": [
        '"CoreWeave" data center fine permit generator environmental lawsuit',
    ],
}

TRUSTED_SOURCES = (
    "Reuters", "Associated Press", "AP News", "Bloomberg", "Financial Times",
    "Wall Street Journal", "The Guardian", "WHYY", "Ars Technica", "TechRadar",
    "New Jersey Monitor", "News 12", "Utility Dive", "Data Center Dynamics",
    "DatacenterDynamics", "S&P Global", "The Register", "Wired", "ENR",
)

ISSUE_TERMS = (
    "fine", "fined", "penalty", "permit", "unpermitted", "without permit",
    "lawsuit", "sued", "blocked", "moratorium", "stop work", "stop-work",
    "violation", "violating", "pollution", "environmental", "generator",
    "gas turbine", "air permit", "noise", "community opposition", "denied",
    "rejected", "cease operations", "enforcement",
)

INDIRECT_TERMS = (
    "linked", "backed", "partner", "tenant", "customer", "supplies", "provider",
    "for microsoft", "for amazon", "for google", "for meta", "for oracle",
)

ISSUE_LABELS = (
    ("벌금·집행", ("fine", "fined", "penalty", "enforcement", "cease operations")),
    ("허가·무허가", ("permit", "unpermitted", "without permit", "stop work", "stop-work")),
    ("환경·대기", ("pollution", "air permit", "environmental", "emissions", "noise")),
    ("소송·주민반대", ("lawsuit", "sued", "community opposition", "moratorium")),
    ("프로젝트 차질", ("blocked", "denied", "rejected", "halt", "paused")),
)

def fetch(url: str, timeout: int = 25) -> requests.Response:
    r = requests.get(url, headers=HEADERS, timeout=timeout)
    r.raise_for_status()
    return r

def norm(v: str) -> str:
    return re.sub(r"\s+", " ", v or "").strip()

def sig(*parts: str) -> str:
    return hashlib.sha256("\n".join(parts).encode("utf-8")).hexdigest()

def parse_pub(v: str) -> dt.datetime | None:
    try:
        d = parsedate_to_datetime(v)
        if d.tzinfo is None:
            d = d.replace(tzinfo=dt.timezone.utc)
        return d.astimezone(dt.timezone.utc)
    except Exception:
        return None

def load_state() -> dict:
    try:
        return json.loads(STATE.read_text(encoding="utf-8"))
    except Exception:
        return {}

def source_ok(source: str) -> bool:
    low = source.lower()
    return any(s.lower() in low for s in TRUSTED_SOURCES)

def issue_label(text: str) -> str:
    low = text.lower()
    labels = [label for label, terms in ISSUE_LABELS if any(t in low for t in terms)]
    return "·".join(labels[:2]) if labels else "규제·운영"

def relationship(text: str) -> str:
    low = text.lower()
    return "파트너·고객 연계" if any(t in low for t in INDIRECT_TERMS) else "기업 연관"

def title_tokens(title: str) -> set[str]:
    stop = {"data","center","centre","the","a","an","and","of","in","on","for","with","to","new"}
    return {x for x in re.findall(r"[a-z0-9]+", title.lower()) if len(x)>=3 and x not in stop}

def similarity(a: str, b: str) -> float:
    ta,tb = title_tokens(a),title_tokens(b)
    if not ta or not tb: return 0.0
    return len(ta&tb)/len(ta|tb)

def collect(company: str, query: str) -> list[dict]:
    q = query + f" when:{MAX_AGE_DAYS}d"
    url = "https://news.google.com/rss/search?" + urllib.parse.urlencode({
        "q":q, "hl":"en-US", "gl":"US", "ceid":"US:en"
    })
    root = ET.fromstring(fetch(url).content)
    cutoff = dt.datetime.now(dt.timezone.utc)-dt.timedelta(days=MAX_AGE_DAYS)
    out=[]
    for item in root.findall(".//item")[:30]:
        title=norm(item.findtext("title") or "")
        link=norm(item.findtext("link") or "")
        pub=norm(item.findtext("pubDate") or "")
        src_node=item.find("source")
        source=norm(src_node.text if src_node is not None else "")
        published=parse_pub(pub)
        blob=f"{title} {source}".lower()
        if not title or not link or not published or published<cutoff:
            continue
        if not source_ok(source):
            continue
        if not any(t in blob for t in ISSUE_TERMS):
            continue
        out.append({
            "company":company,"title":title,"url":link,"source":source,
            "published":published.isoformat(),
            "label":issue_label(blob),"relationship":relationship(blob),
        })
    return out

def cluster_company(items: list[dict]) -> list[list[dict]]:
    clusters=[]
    for item in sorted(items,key=lambda x:x["published"],reverse=True):
        placed=False
        for c in clusters:
            if c[0]["label"]==item["label"] and max(similarity(item["title"],x["title"]) for x in c)>=0.16:
                c.append(item); placed=True; break
        if not placed:
            clusters.append([item])
    return clusters

def canonical_issue(company: str, cluster: list[dict]) -> dict | None:
    sources=list(dict.fromkeys(x["source"] for x in cluster))
    if len(sources)<2:
        return None
    titles=" ".join(x["title"] for x in cluster)
    newest=max(cluster,key=lambda x:x["published"])
    relation="파트너·고객 연계" if any(x["relationship"]=="파트너·고객 연계" for x in cluster) else "기업 연관"

    # High-confidence canonicalization for the current Vineland enforcement case.
    low=titles.lower()
    if company=="Microsoft" and any(k in low for k in ("vineland","dataone","62 gas","62 natural")):
        summary=(
            "DataOne Vineland(NJ), 62대×1,982kW 천연가스 발전기 무허가 설치·운영으로 "
            "NJDEP 107만달러 벌금·45일 내 허가 취득 또는 가동중단 명령. "
            "Microsoft는 직접 벌금 대상이 아니라 Nebius의 약 170억달러 AI 인프라 계약을 통한 연계."
        )
        relation="파트너·고객 연계"
        label="벌금·허가·환경"
    else:
        summary=re.sub(r"\s+-\s+[^-]{2,40}$","",newest["title"]).strip()
        label=newest["label"]

    fp=sig(company,label,summary.lower())
    return {
        "fingerprint":fp,"company":company,"label":label,"relationship":relation,
        "summary":summary,"published":newest["published"],"url":newest["url"],
        "sources":sources[:4],
    }

def h(v) -> str:
    return html.escape(str(v),quote=True)

def render(issues: list[dict]) -> str:
    lines=["<b>🚨 Hyperscaler 기업별 데이터센터 리스크</b>",""]
    for issue in issues:
        lines += [
            f"<b>• {h(issue['company'])}</b> │ {h(issue['label'])} │ <b>{h(issue['relationship'])}</b>",
            f"  ↳ {h(issue['summary'])}",
            f"  ↳ 교차검증 {len(issue['sources'])}개: {h(', '.join(issue['sources']))}",
            f"  ↳ <a href=\"{h(issue['url'])}\">원문</a>",
        ]
    lines += [
        "",
        "<b>📌 판정 원칙</b>",
        "• 벌금·위반 주체와 Microsoft/AWS/Google 등 연계 기업을 분리",
        "• 직접 위반이 아니면 ‘파트너·고객 연계’로 표시",
        "• 서로 다른 신뢰 출처 2곳 이상에서 같은 사건이 확인될 때만 신규 알림",
        "• 벌금·허가·환경·소송·주민반대·가동중단 명령을 기업별 위험 이력에 누적",
    ]
    return "\n".join(lines)+"\n"

def main() -> int:
    OUT.mkdir(exist_ok=True)
    for p in (PENDING,ALERT,STATUS):
        if p.exists(): p.unlink()
    old=load_state()
    all_rows=[]
    errors=[]
    for company,queries in COMPANY_QUERIES.items():
        for q in queries:
            try: all_rows.extend(collect(company,q))
            except Exception as e: errors.append(f"{company}:{type(e).__name__}")

    by_company={}
    for row in all_rows:
        by_company.setdefault(row["company"],[]).append(row)

    active=[]
    for company,rows in by_company.items():
        for cluster in cluster_company(rows):
            issue=canonical_issue(company,cluster)
            if issue: active.append(issue)

    # Keep only recent active issues.
    active_cutoff=dt.datetime.now(dt.timezone.utc)-dt.timedelta(days=ACTIVE_DAYS)
    active=[x for x in active if dt.datetime.fromisoformat(x["published"])>=active_cutoff]
    active.sort(key=lambda x:x["published"],reverse=True)

    alerted=set(old.get("alerted_fingerprints",[]))
    new=[x for x in active if x["fingerprint"] not in alerted]
    alerted.update(x["fingerprint"] for x in new)

    active_by_company={}
    for x in active:
        active_by_company.setdefault(x["company"],[]).append(x)

    pending={
        "initialized":True,"version":FORMAT_VERSION,
        "alerted_fingerprints":list(alerted)[-3000:],
        "active_issues_by_company":active_by_company,
        "source_errors":errors[:20],
        "updated_at_utc":dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"),
    }
    PENDING.write_text(json.dumps(pending,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
    if new:
        ALERT.write_text(render(new[:8]),encoding="utf-8")
    STATUS.write_text(
        "# Hyperscaler 기업별 데이터센터 리스크 감시\n\n"
        f"- 활성 이슈: **{len(active)}건**\n"
        f"- 신규 이슈: **{len(new)}건**\n"
        f"- 알림: **{'예' if new else '아니오'}**\n"
        f"- 원천 오류: **{', '.join(errors) if errors else '없음'}**\n",
        encoding="utf-8",
    )
    print(f"hyperscaler_company_issues active={len(active)} new={len(new)} errors={len(errors)}")
    return 0

if __name__=="__main__":
    raise SystemExit(main())
