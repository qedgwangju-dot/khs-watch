#!/usr/bin/env python3
from __future__ import annotations

import datetime as dt
import hashlib
import html
import json
import re
import urllib.parse
import xml.etree.ElementTree as ET
from collections import defaultdict
from email.utils import parsedate_to_datetime
from pathlib import Path

import requests
from bs4 import BeautifulSoup

OUT = Path("out")
STATE = Path("data/us_hyperscaler_company_risk_state.json")
PENDING = OUT / "us_hyperscaler_company_risk_pending_state.json"
ALERT = OUT / "us_hyperscaler_company_risk_alert.txt"
STATUS = OUT / "us_hyperscaler_company_risk_status.md"

FORMAT_VERSION = 4
LOOKBACK_DAYS = 10
MAX_ALERT_AGE_DAYS = 7
SIGNAL_WINDOW_DAYS = 30
HEADERS = {"User-Agent": "khs-watch/1.0 (+https://github.com/qedgwangju-dot/khs-watch)"}
NJDEP_DATAONE = "https://dep.nj.gov/newsrel/26_0044/"
NEBIUS_MICROSOFT = "https://nebius.com/newsroom/nebius-announces-multi-billion-dollar-agreement-with-microsoft-for-ai-infrastructure"

TRACKED = {
    "Amazon/AWS": ("amazon", "aws"),
    "Microsoft": ("microsoft", "azure", "nebius", "dataone", "data one", "vineland"),
    "Alphabet/Google": ("google", "alphabet"),
    "Meta": ("meta", "facebook"),
    "Oracle": ("oracle",),
    "Alibaba": ("alibaba", "aliyun"),
    "ByteDance": ("bytedance", "tiktok", "douyin"),
    "Tencent": ("tencent",),
    "xAI": ("xai", "x.ai", "colossus"),
    "CoreWeave": ("coreweave",),
    "Nebius": ("nebius", "dataone", "data one", "vineland"),
}

SEARCHES = {
    "Amazon/AWS": [
        '"Amazon" data center fine permit violation generator environmental safety',
        '"AWS" data center stop work lawsuit emissions water fire generator',
    ],
    "Microsoft": [
        '"Microsoft" data center fine permit violation generator environmental safety',
        '"Nebius" Microsoft data center fine permit generator',
        '"DataOne" Vineland Microsoft data center generator permit',
    ],
    "Alphabet/Google": [
        '"Google" data center fine permit violation generator environmental safety',
        '"Google" data center water lawsuit gas plant permit',
    ],
    "Meta": [
        '"Meta" data center fine permit violation generator environmental safety',
        '"Meta" data center water lawsuit gas power permit',
    ],
    "Oracle": [
        '"Oracle" data center fine permit violation generator environmental safety',
        '"Stargate" data center permit violation lawsuit power',
    ],
    "Alibaba": [
        '"Alibaba Cloud" data center fine permit violation environmental safety',
    ],
    "ByteDance": [
        '"ByteDance" data center fine permit violation environmental safety',
    ],
    "Tencent": [
        '"Tencent" data center fine permit violation environmental safety',
    ],
    "xAI": [
        '"xAI" data center fine permit violation generator environmental safety',
        '"Colossus" Memphis gas turbine permit violation fine',
    ],
    "CoreWeave": [
        '"CoreWeave" data center fine permit violation generator environmental safety',
    ],
    "Nebius": [
        '"Nebius" data center fine permit violation generator environmental safety',
        '"DataOne" Vineland Nebius data center generator permit',
    ],
}

RISK_TERMS = (
    "fine", "fined", "penalty", "violation", "violating", "unpermitted", "without permit",
    "permit violation", "air pollution", "emission", "environmental", "stop work", "stop-work",
    "shutdown", "cease operations", "lawsuit", "investigation", "regulator", "enforcement",
    "generator", "gas turbine", "fire", "explosion", "safety", "water", "moratorium",
    "zoning", "community opposition", "local opposition", "ratepayer", "curtailment", "noise",
    "delay", "delayed", "denied", "rejected", "force majeure", "injunction", "appeal",
    "interconnection", "grid connection", "power shortage", "pipeline", "permit denied",
)

REPUTABLE = (
    "reuters", "associated press", "ap news", "bloomberg", "financial times", "wall street journal",
    "the guardian", "ars technica", "whyy", "new jersey monitor", "utility dive",
    "data center dynamics", "datacenterdynamics", "the register", "s&p global", "cnbc",
)
OFFICIAL_HINTS = (
    "department of environmental protection", "dep", "governor", "city of ", "county",
    "public utility commission", "public service commission", "ferc", "epa", "tceq",
    "planning board", "state of ",
)

STOP = {
    "data","center","centers","centre","centres","datacenter","ai","the","a","an","and","or","of","to",
    "for","in","on","with","from","new","says","over","after","as","at","its","us","u","s","2026",
    "microsoft","amazon","aws","google","meta","oracle","alibaba","bytedance","tencent","xai","coreweave",
    "nebius",
}

def norm(v: str | None) -> str:
    return re.sub(r"\s+", " ", v or "").strip()

def sha(v: str) -> str:
    return hashlib.sha256(v.encode("utf-8")).hexdigest()

def parse_date(v: str) -> dt.datetime | None:
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

def fetch_json(url: str, timeout=20):
    r = requests.get(url, headers=HEADERS, timeout=timeout)
    r.raise_for_status()
    return r.json()

def fx_rate(old=None) -> tuple[float | None, str]:
    for url, parser, name in (
        ("https://open.er-api.com/v6/latest/USD", lambda x: x["rates"]["KRW"], "ER-API"),
        ("https://api.frankfurter.app/latest?from=USD&to=KRW", lambda x: x["rates"]["KRW"], "Frankfurter"),
    ):
        try:
            v = float(parser(fetch_json(url)))
            if 500 < v < 3000:
                return v, name
        except Exception:
            pass
    return (float(old), "직전 저장값") if old else (None, "확인 불가")

def krw(usd: float, fx: float) -> str:
    won = usd * fx
    eok = round(won / 100_000_000)
    jo, rem = divmod(eok, 10000)
    if jo and rem:
        return f"약 {jo:,}조 {rem:,}억원"
    if jo:
        return f"약 {jo:,}조원"
    return f"약 {rem:,}억원"

def _rss_rows(content: bytes, fallback_source: str) -> list[dict]:
    root = ET.fromstring(content)
    cutoff = dt.datetime.now(dt.timezone.utc) - dt.timedelta(days=MAX_ALERT_AGE_DAYS)
    rows = []
    for item in root.findall(".//item")[:50]:
        title = norm(item.findtext("title"))
        link = norm(item.findtext("link"))
        pub = norm(item.findtext("pubDate"))
        source = ""
        for child in list(item):
            if str(child.tag).lower().endswith("source"):
                source = norm(child.text)
                if source:
                    break
        if not source and " - " in title:
            source = norm(title.rsplit(" - ", 1)[-1])
        source = source or fallback_source
        d = parse_date(pub)
        if not title or not link or d is None or d < cutoff:
            continue
        low = title.lower()
        if not any(k in low for k in RISK_TERMS):
            continue
        rows.append({"title": title, "link": link, "source": source, "published": d.isoformat()})
    return rows


def google_news(query: str) -> list[dict]:
    google_url = "https://news.google.com/rss/search?" + urllib.parse.urlencode({
        "q": query + f" when:{LOOKBACK_DAYS}d",
        "hl": "en-US",
        "gl": "US",
        "ceid": "US:en",
    })
    try:
        r = requests.get(google_url, headers=HEADERS, timeout=12)
        r.raise_for_status()
        return _rss_rows(r.content, "Google News")
    except Exception as google_exc:
        # GitHub-hosted runners can be rate-limited by Google News RSS.
        # Use an independent RSS fallback rather than silently losing the company scan.
        bing_url = "https://www.bing.com/news/search?" + urllib.parse.urlencode({
            "q": query,
            "format": "RSS",
        })
        try:
            r = requests.get(
                bing_url,
                headers={**HEADERS, "User-Agent": "Mozilla/5.0 (compatible; khs-watch/1.0)"},
                timeout=12,
            )
            r.raise_for_status()
            return _rss_rows(r.content, "Bing News")
        except Exception as bing_exc:
            raise RuntimeError(
                f"news RSS failed: Google={type(google_exc).__name__}, Bing={type(bing_exc).__name__}"
            ) from bing_exc

def tokens(title: str) -> set[str]:
    words = re.findall(r"[a-z0-9]+", title.lower())
    return {w for w in words if len(w) >= 3 and w not in STOP}

def similarity(a: str, b: str) -> float:
    ta, tb = tokens(a), tokens(b)
    if not ta or not tb:
        return 0.0
    return len(ta & tb) / len(ta | tb)

def source_class(source: str) -> str:
    low = source.lower()
    if any(x in low for x in OFFICIAL_HINTS):
        return "공식"
    if any(x in low for x in REPUTABLE):
        return "신뢰보도"
    return "기타"

def resolve(link: str) -> str:
    if "news.google.com" not in link:
        return link
    try:
        # Decoder is optional. Dependency/API breakage must not stop the watcher.
        from googlenewsdecoder import gnewsdecoder
        result = gnewsdecoder(link, interval=0.1)
        if isinstance(result, dict) and result.get("status") and result.get("decoded_url"):
            return str(result["decoded_url"])
    except Exception:
        pass
    return link

def clean_title(title: str, source: str) -> str:
    value = html.unescape(re.sub(r"<[^>]+>", " ", title))
    value = re.sub(r"\s+", " ", value).strip()
    if " - " in value:
        head, tail = value.rsplit(" - ", 1)
        if re.sub(r"\W+", "", tail.lower()) in re.sub(r"\W+", "", source.lower()):
            value = head.strip()
    return value

def companies_for(text: str) -> list[str]:
    low = text.lower()
    out = []
    for company, aliases in TRACKED.items():
        if any(alias in low for alias in aliases):
            out.append(company)
    return out

def event_fingerprint(company: str, titles: list[str]) -> str:
    counts = defaultdict(int)
    for t in titles:
        for tok in tokens(t):
            counts[tok] += 1
    common = sorted(k for k, v in counts.items() if v >= max(1, min(2, len(titles))))[:18]
    return sha(company + "|" + "|".join(common))

def cluster_company(company: str, rows: list[dict]) -> list[dict]:
    clusters: list[list[dict]] = []
    for row in sorted(rows, key=lambda x: x["published"], reverse=True):
        placed = False
        for cluster in clusters:
            if any(similarity(row["title"], x["title"]) >= 0.23 for x in cluster):
                cluster.append(row)
                placed = True
                break
        if not placed:
            clusters.append([row])

    out = []
    for cluster in clusters:
        independent = {}
        for x in cluster:
            independent[re.sub(r"\W+", "", x["source"].lower())] = x["source"]
        classes = {source_class(s) for s in independent.values()}
        if len(independent) < 2 or not classes.intersection({"공식", "신뢰보도"}):
            continue

        titles = [clean_title(x["title"], x["source"]) for x in cluster]
        best = sorted(
            cluster,
            key=lambda x: (
                0 if source_class(x["source"]) == "공식" else 1 if source_class(x["source"]) == "신뢰보도" else 2,
                -len(x["title"]),
            ),
        )[0]
        out.append({
            "company": company,
            "fp": event_fingerprint(company, titles),
            "title": clean_title(best["title"], best["source"]),
            "source": best["source"],
            "url": resolve(best["link"]),
            "published": max(x["published"] for x in cluster),
            "sources": list(independent.values())[:5],
            "titles": titles[:8],
        })
    return out

def canonical_event_key(event: dict) -> str:
    blob = " ".join(event.get("titles", []) + [event.get("title", "")]).lower()
    dataone_signal = (
        ("vineland" in blob)
        or ("$1.07" in blob)
        or ("$1.1m" in blob)
        or ("$1 million" in blob and "new jersey" in blob)
    )
    generator_enforcement = (
        ("generator" in blob)
        and any(k in blob for k in ("fine", "fined", "penalty", "unpermitted", "without permit"))
    )
    if dataone_signal and generator_enforcement:
        return "dataone-vineland-generator-enforcement-20260922"
    return event.get("fp") or sha(blob)


def merge_cross_company(events: list[dict]) -> list[dict]:
    grouped: dict[str, list[dict]] = defaultdict(list)
    for event in events:
        grouped[canonical_event_key(event)].append(event)

    merged = []
    for key, group in grouped.items():
        companies = sorted({x["company"] for x in group})
        sources, titles = [], []
        for x in group:
            sources.extend(x.get("sources", []))
            titles.extend(x.get("titles", []))
        sources = list(dict.fromkeys(sources))
        titles = list(dict.fromkeys(titles))

        if key == "dataone-vineland-generator-enforcement-20260922":
            companies = ["Microsoft", "Nebius"]
            sources = list(dict.fromkeys(["New Jersey Department of Environmental Protection"] + sources))
            titles = list(dict.fromkeys([
                "NJDEP fined DataOne Vineland $1.07 million for installing and operating 62 1,982-kW natural-gas generators without required permits"
            ] + titles))
            title = "NJDEP, DataOne Vineland에 무허가 천연가스 발전기 62기 운영으로 107만달러 벌금"
            url = NJDEP_DATAONE
            published = "2026-09-22T00:00:00+00:00"
        else:
            best = sorted(
                group,
                key=lambda x: (
                    0 if source_class(x.get("source", "")) == "공식" else 1 if source_class(x.get("source", "")) == "신뢰보도" else 2,
                    -len(x.get("title", "")),
                ),
            )[0]
            title, url = best["title"], best["url"]
            published = max(x.get("published", "") for x in group)

        merged.append({
            "event_key": key,
            "companies": companies,
            "company": "·".join(companies),
            "title": title,
            "url": url,
            "published": published,
            "sources": sources[:8],
            "titles": titles[:12],
        })
    return sorted(merged, key=lambda x: x["published"], reverse=True)


def authoritative_seed_events() -> list[dict]:
    # Official enforcement + official commercial link. This is deliberately
    # separate from news search so a Google RSS outage cannot hide a material
    # regulator action.
    return [{
        "event_key": "dataone-vineland-generator-enforcement-20260922",
        "companies": ["Microsoft", "Nebius"],
        "company": "Microsoft·Nebius",
        "title": "NJDEP, DataOne Vineland에 무허가 천연가스 발전기 62기 운영으로 107만달러 벌금",
        "url": NJDEP_DATAONE,
        "published": "2026-09-22T00:00:00+00:00",
        "sources": [
            "New Jersey Department of Environmental Protection",
            "Nebius",
        ],
        "titles": [
            "NJDEP fined DataOne Vineland $1.07 million for installing and operating 62 1,982-kW natural-gas generators without required permits",
            "Nebius provides dedicated AI infrastructure capacity to Microsoft from its Vineland New Jersey data center under a five-year agreement",
        ],
    }]


def active_issue_payload(event: dict, company: str) -> dict:
    cat, relation = classify_event(event)
    if event.get("event_key") == "dataone-vineland-generator-enforcement-20260922":
        if company == "Microsoft":
            relationship = "파트너·고객 연계"
            summary = (
                "DataOne Vineland(NJ), 62대×1,982kW 천연가스 발전기 무허가 설치·운영으로 "
                "NJDEP 107만달러 벌금·45일 내 허가 취득 또는 가동중단 명령. "
                "Microsoft는 직접 벌금 대상이 아니라 Nebius의 Vineland 전용 GPU 용량 고객."
            )
        elif company == "Nebius":
            relationship = "사업·운영 연계"
            summary = (
                "DataOne이 건설·운영하는 Nebius Vineland 시설에서 62대 천연가스 발전기 "
                "무허가 설치·운영이 적발돼 NJDEP가 107만달러 벌금과 시정명령을 부과."
            )
        else:
            relationship = "기업 연관"
            summary = event["title"]
    else:
        relationship = "직접 여부 원문 확인"
        summary = event["title"]

    return {
        "fingerprint": event["event_key"],
        "company": company,
        "label": cat,
        "relationship": relationship,
        "summary": summary,
        "published": event["published"],
        "url": event["url"],
        "sources": event.get("sources", [])[:5],
    }


def classify_event(event: dict) -> tuple[str, str]:
    blob = " ".join(event["titles"]).lower()
    if any(k in blob for k in ("fine", "fined", "penalty", "violation", "unpermitted", "without permit", "enforcement")):
        cat = "규제·환경 위반"
    elif any(k in blob for k in ("fire", "explosion", "safety")):
        cat = "안전"
    elif any(k in blob for k in ("water", "air pollution", "emission", "noise")):
        cat = "환경·지역사회"
    elif any(k in blob for k in ("lawsuit", "investigation", "subpoena")):
        cat = "법적·조사"
    else:
        cat = "허가·운영"

    if event.get("event_key") == "dataone-vineland-generator-enforcement-20260922":
        relation = "직접 위반: DataOne / 연결: Nebius 인프라 → Microsoft GPU 용량 고객"
    else:
        relation = "해당 기업 직접 언급 · 직접 책임 여부는 원문 기준"
    return cat, relation

def risk_driver(event: dict) -> str:
    blob = " ".join(event.get("titles", []) + [event.get("title", "")]).lower()
    if any(k in blob for k in (
        "interconnection", "grid connection", "power shortage", "generator", "gas turbine",
        "pipeline", "force majeure", "permit denied", "denied", "rejected",
    )):
        return "전력·인허가"
    if any(k in blob for k in ("fire", "explosion", "safety")):
        return "안전"
    if any(k in blob for k in ("zoning", "community opposition", "local opposition", "moratorium")):
        return "지역사회·입지"
    if any(k in blob for k in ("water", "air pollution", "emission", "noise", "environmental")):
        return "환경"
    if any(k in blob for k in ("lawsuit", "investigation", "injunction", "appeal")):
        return "법적·소송"
    if any(k in blob for k in ("fine", "fined", "penalty", "violation", "enforcement", "unpermitted")):
        return "규제·허가"
    return "기타"


def signal_assessment(events: list[dict]) -> dict:
    cutoff = dt.datetime.now(dt.timezone.utc) - dt.timedelta(days=SIGNAL_WINDOW_DAYS)
    active = []
    for event in events:
        try:
            published = dt.datetime.fromisoformat(event.get("published", ""))
            if published.tzinfo is None:
                published = published.replace(tzinfo=dt.timezone.utc)
        except Exception:
            continue
        if published >= cutoff:
            active.append(event)

    by_driver: dict[str, dict[str, set[str]]] = defaultdict(
        lambda: {"events": set(), "companies": set()}
    )
    for event in active:
        driver = risk_driver(event)
        by_driver[driver]["events"].add(event.get("event_key", ""))
        by_driver[driver]["companies"].update(event.get("companies", []))

    if not by_driver:
        return {
            "label": "개별 노이즈",
            "driver": "없음",
            "driver_event_count": 0,
            "driver_company_count": 0,
            "active_event_count": 0,
            "window_days": SIGNAL_WINDOW_DAYS,
        }

    driver, bucket = max(
        by_driver.items(),
        key=lambda kv: (len(kv[1]["events"]), len(kv[1]["companies"]), kv[0]),
    )
    event_count = len(bucket["events"])
    company_count = len(bucket["companies"])
    if event_count >= 3 and company_count >= 3:
        label = "산업 위험 신호"
    elif event_count >= 2 and company_count >= 2:
        label = "확산 주의"
    else:
        label = "개별 노이즈"

    return {
        "label": label,
        "driver": driver,
        "driver_event_count": event_count,
        "driver_company_count": company_count,
        "active_event_count": len({x.get("event_key", "") for x in active}),
        "window_days": SIGNAL_WINDOW_DAYS,
    }


def extract_facts(event: dict, fx: float | None) -> list[str]:
    blob = " ".join(event["titles"])
    facts = []
    # Monetary fines / penalties
    m = re.search(r"\$\s*([0-9]+(?:\.[0-9]+)?)\s*(million|m|billion|b)\b", blob, re.I)
    if m and fx:
        val = float(m.group(1))
        usd = val * (1e9 if m.group(2).lower().startswith("b") else 1e6)
        facts.append(f"금액 {m.group(0)} = {krw(usd, fx)}")
    # generator count
    m = re.search(r"\b(\d{1,3})\s+(?:natural[- ]gas|gas)?\s*generators?\b", blob, re.I)
    if m:
        facts.append(f"발전기 {m.group(1)}기")
    # MW/GW
    m = re.search(r"\b([0-9]+(?:\.[0-9]+)?)\s*(MW|GW)\b", blob, re.I)
    if m:
        facts.append(f"규모 {m.group(1)}{m.group(2).upper()}")
    return facts[:3]

def render(events: list[dict], fx: float | None, fx_source: str, signal: dict) -> str:
    signal_label = signal.get("label", "개별 노이즈")
    driver = signal.get("driver", "기타")
    driver_events = int(signal.get("driver_event_count", 0) or 0)
    driver_companies = int(signal.get("driver_company_count", 0) or 0)
    lines = [
        "<b>🚨 하이퍼스케일러 기업별 규제·환경·안전 변화</b>",
        "직접 위반 당사자와 연결된 하이퍼스케일러를 분리해서 표시합니다.",
        "",
        f"<b>📡 산업 확산 판정: {html.escape(signal_label)}</b>",
        f"• 최근 {SIGNAL_WINDOW_DAYS}일 핵심 원인축: {html.escape(driver)} · 독립 사건 {driver_events}건 · 연관 기업 {driver_companies}개",
        "• 동일 사건이 파트너·고객 여러 기업에 연결돼도 독립 사건 1건으로만 계산",
        "• 2개 이상 독립 사건·2개 이상 기업이면 확산 주의, 3개 이상이면 산업 위험 신호",
        "• 이 판정은 규제·전력·허가 위험의 확산 폭이며 AI 데이터센터 수요 사이클 전체 판정은 아님",
        "",
    ]
    for event in events[:8]:
        cat, direct = classify_event(event)
        facts = extract_facts(event, fx)
        lines.append(f"<b>{html.escape(event['company'])}</b> · {html.escape(cat)}")
        lines.append(f"• 당사자 구분: <b>{html.escape(direct)}</b>")
        lines.append(f"• {html.escape(event['title'])}")
        if facts:
            lines.append("• " + " · ".join(html.escape(x) for x in facts))
        lines.append(f"• 교차검증: {len(event['sources'])}개 출처 · " + ", ".join(html.escape(x) for x in event["sources"][:3]))
        lines.append(f'• <a href="{html.escape(event["url"], quote=True)}">원문</a>')
        if event.get("event_key") == "dataone-vineland-generator-enforcement-20260922":
            ms_usd = 17.4e9
            ms_krw = f" = {krw(ms_usd, fx)}" if fx else ""
            lines.append(f"• 계약 연결: Nebius가 Vineland에서 Microsoft에 전용 GPU 용량 공급 · 기본 계약가 약 $17.4B{ms_krw}")
            lines.append("• 책임 구분: NJDEP 벌금 대상은 DataOne이며 Microsoft나 Nebius에 부과된 벌금이 아닙니다.")
        lines.append("")

    lines += [
        "<b>📌 판정 기준</b>",
        "• 벌금·허가위반·환경법·공사중지·화재·폭발·물·대기·소송·규제조사만 추적",
        "• 서로 다른 2개 이상 출처가 확인될 때만 신규 알림",
        "• 고객·임차인·계약 상대방은 직접 위반 당사자로 표시하지 않음",
        "• 같은 사건 재인용·오래된 기사 재발견은 중복 차단",
    ]
    if fx:
        lines += ["", f"💱 1달러 = {fx:,.2f}원 · {html.escape(fx_source)}"]
    return "\n".join(lines).strip() + "\n"

def main() -> int:
    OUT.mkdir(exist_ok=True)
    for p in (PENDING, ALERT, STATUS):
        if p.exists():
            p.unlink()

    old = load_state()
    fx, fx_source = fx_rate(old.get("last_fx_krw_per_usd"))
    raw: dict[str, list[dict]] = defaultdict(list)
    errors = []
    for company, queries in SEARCHES.items():
        primary = TRACKED[company][0]
        dynamic_queries = list(queries) + [
            f'"{primary}" data center permit delay interconnection local opposition force majeure'
        ]
        for q in dynamic_queries:
            try:
                raw[company].extend(google_news(q))
            except Exception as exc:
                errors.append(f"{company}: {type(exc).__name__}")

    events = []
    for company, rows in raw.items():
        unique = {(x["title"], x["source"], x["link"]): x for x in rows}
        events.extend(cluster_company(company, list(unique.values())))

    events = merge_cross_company(events)
    by_key = {x["event_key"]: x for x in events}
    for seed in authoritative_seed_events():
        by_key[seed["event_key"]] = seed
    events = sorted(by_key.values(), key=lambda x: x["published"], reverse=True)
    signal = signal_assessment(events)

    seen = set(old.get("seen_events", []))
    baseline = not old.get("initialized")
    format_upgrade = int(old.get("format_version", 0) or 0) < FORMAT_VERSION
    new_events = [x for x in events if x["event_key"] not in seen]
    if baseline or format_upgrade:
        # Send current verified incidents once so the upgraded company layer is visible.
        new_events = events[:8]

    all_seen = list(dict.fromkeys(old.get("seen_events", []) + [x["event_key"] for x in events]))[-3000:]
    active_cutoff = dt.datetime.now(dt.timezone.utc) - dt.timedelta(days=30)
    active_issues_by_company = defaultdict(list)
    for event in events:
        try:
            published = dt.datetime.fromisoformat(event["published"])
        except Exception:
            continue
        if published < active_cutoff:
            continue
        for company in event.get("companies", []):
            active_issues_by_company[company].append(active_issue_payload(event, company))

    pending = {
        "initialized": True,
        "format_version": FORMAT_VERSION,
        "seen_events": all_seen,
        "active_issues_by_company": dict(active_issues_by_company),
        "signal_assessment": signal,
        "last_fx_krw_per_usd": fx,
        "fx_source": fx_source,
        "last_event_count": len(events),
        "last_errors": errors[:20],
        "updated_at_utc": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"),
    }
    PENDING.write_text(json.dumps(pending, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    if new_events:
        ALERT.write_text(render(new_events, fx, fx_source, signal), encoding="utf-8")

    STATUS.write_text(
        "# 하이퍼스케일러 기업별 규제·환경·안전 감시\n\n"
        f"- 검증 사건: **{len(events)}건**\n"
        f"- 신규 사건: **{len(new_events)}건**\n"
        f"- 알림: **{'예' if new_events else '아니오'}**\n"
        f"- 산업 확산 판정: **{signal.get('label','개별 노이즈')}** · {signal.get('driver','기타')} · 독립 사건 {signal.get('driver_event_count',0)}건\n"
        f"- 검색 오류: **{len(errors)}건**\n",
        encoding="utf-8",
    )
    print(f"hyperscaler_company_risk events={len(events)} new={len(new_events)} baseline={baseline} errors={len(errors)}")
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
