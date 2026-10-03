from __future__ import annotations

import copy
import hashlib
import html
import json
import pathlib
import re
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta, timezone
from email.utils import parsedate_to_datetime
from urllib.parse import urlparse
from zoneinfo import ZoneInfo

try:
    from googlenewsdecoder import gnewsdecoder
except Exception:
    gnewsdecoder = None

ROOT = pathlib.Path(__file__).resolve().parents[1]
STATE_PATH = ROOT / "data" / "ai_server_physical_bottleneck_watch_state.json"
PENDING_PATH = ROOT / "out" / "ai_server_physical_bottleneck_pending_state.json"
ALERT_PATH = ROOT / "out" / "ai_server_physical_bottleneck_alert.html"
UA = "Mozilla/5.0 (compatible; khs-watch/ai-server-bottleneck)"

BASELINE = {
    "as_of": "2026-10-03",
    "facts": {
        "universal_six_month_shortage_confirmed": False,
        "trendforce_cpu_pcb_lead_time_near_one_year": True,
        "trendforce_power_supply_caps_output": True,
        "liquid_cooling_penetration_2026_pct": 53.0,
        "bizlink_aec_800g_plus_confirmed": True,
        "nvidia_vr200_power_kw": 225.0,
        "nvidia_800v_optional_vr200": True,
    },
    "seen_urls": [
        "https://www.trendforce.com/presscenter/news/20260415-13013.html",
        "https://www.trendforce.com/research/download/RP260903XY3",
        "https://www.trendforce.com/presscenter/news/20260817-13183.html",
        "https://www.trendforce.com/presscenter/news/20260625-13121.html",
        "https://telecom-networking.bizlinktech.com/applications/bizlink-data-center-solutions/",
        "https://www.deltaww.com/en-US/investors/chairman-statement",
        "https://image.honhai.com/upload/202605/law_talk/Hon_Hai_1Q26_Results_Transcript_English_20260514_3576.pdf",
    ],
    "seen_signatures": [],
    "last_checked_at_kst": "2026-10-03T21:09:00+09:00",
    "candidate_count": 0,
    "event_count": 0,
}

SEARCHES = [
    'site:trendforce.com 2026 AI server (AEC OR "active electrical cable" OR PSU OR "power supply" OR "liquid cooling" OR CCL OR PCB OR ODM) shortage lead time capacity',
    'site:bizlinktech.com 2026 AEC "AI data center" shipment capacity qualification',
    'site:deltaww.com 2026 AI server power liquid cooling 800V shipment capacity',
    'site:honhai.com 2026 AI server rack shipment material supply capacity',
    'site:wistron.com 2026 AI server rack shipment capacity',
    'site:quantatw.com 2026 AI server rack shipment capacity',
    'site:wiwynn.com 2026 AI server rack shipment capacity',
    'site:emctw.com 2026 AI server CCL capacity shipment price',
    'site:auras.com.tw 2026 AI server liquid cooling cold plate capacity shipment',
]

OFFICIAL_DOMAINS = (
    "trendforce.com",
    "bizlinktech.com",
    "deltaww.com",
    "honhai.com",
    "wistron.com",
    "quantatw.com",
    "wiwynn.com",
    "emctw.com",
    "auras.com.tw",
    "nvidia.com",
    "investor.nvidia.com",
)

CATEGORY_ALIASES = {
    "AEC": (
        "active electrical cable", "active electrical cables", " aec ", " aecs ",
        "800g aec", "1.6t aec",
    ),
    "LIQUID_COOLING": (
        "liquid cooling", "liquid-cooled", "cold plate", "cold plates", "cdu",
        "coolant distribution unit", "manifold",
    ),
    "POWER": (
        "power supply", "power supplies", "psu", "power shelf", "power shelves",
        "800v", "800vdc", "hvdc", "dc/dc", "ac/dc",
    ),
    "PCB_CCL": (
        "copper-clad laminate", "copper clad laminate", "ccl", "printed circuit board",
        "pcb",
    ),
    "ODM_RACK": (
        "ai server rack", "gpu rack", "rack shipment", "rack shipments",
        "rack-level", "rack scale", "rack-scale",
    ),
}

COMPANY_MAP = {
    "bizlinktech.com": "BizLink-KY",
    "deltaww.com": "Delta Electronics",
    "honhai.com": "Foxconn",
    "wistron.com": "Wistron",
    "quantatw.com": "Quanta",
    "wiwynn.com": "Wiwynn",
    "emctw.com": "Elite Material",
    "auras.com.tw": "Auras Technology",
    "nvidia.com": "NVIDIA",
    "investor.nvidia.com": "NVIDIA",
    "trendforce.com": "TrendForce",
}

BENEFICIARIES = {
    "AEC": "BizLink-KY — AEC·고속 구리 인터커넥트",
    "LIQUID_COOLING": "AVC(Asia Vital Components)·Delta Electronics·Auras Technology·BOYD — 콜드플레이트·CDU·열관리",
    "POWER": "Delta Electronics·Lite-On — PSU·고전력 전원변환·800V HVDC",
    "PCB_CCL": "Elite Material(台光電)·TUC — 고속·저손실 CCL / AI 서버 PCB 상류",
    "ODM_RACK": "Foxconn·Wistron·Quanta·Wiwynn — AI 서버·랙 통합",
}

NEXT_CHECK = {
    "AEC": "리드타임·800G/1.6T 양산·고객 인증·생산능력",
    "LIQUID_COOLING": "콜드플레이트/CDU 인증·출하·생산능력·누수/신뢰성",
    "POWER": "PSU 납기·전력모듈 생산능력·800V 채택·랙당 kW",
    "PCB_CCL": "CCL 납기·가격·저손실 소재 생산능력·PCB 출하",
    "ODM_RACK": "랙 출하량·부품 부족에 따른 출하 지연·가동률",
}

def fetch(url: str, timeout: int = 20) -> bytes:
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=timeout) as response:
        return response.read()

def clean_text(value: str) -> str:
    value = html.unescape(value or "")
    value = re.sub(r"<(script|style|svg|noscript)[^>]*>.*?</\1>", " ", value, flags=re.I | re.S)
    value = re.sub(r"<[^>]+>", " ", value)
    return re.sub(r"\s+", " ", value).strip()

def parse_pubdate(value: str) -> datetime | None:
    try:
        dt = parsedate_to_datetime(value)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(ZoneInfo("Asia/Seoul"))
    except Exception:
        return None

def google_news_url(query: str) -> str:
    return "https://news.google.com/rss/search?q=" + urllib.parse.quote(query) + "&hl=en-US&gl=US&ceid=US:en"

def read_rss(query: str) -> list[dict]:
    root = ET.fromstring(fetch(google_news_url(query)))
    out = []
    for item in root.findall("./channel/item"):
        title = clean_text(item.findtext("title") or "")
        link = clean_text(item.findtext("link") or "")
        description = clean_text(item.findtext("description") or "")
        dt = parse_pubdate(clean_text(item.findtext("pubDate") or ""))
        if title and link:
            out.append({
                "title": title,
                "link": link,
                "description": description,
                "published_at_kst": dt.isoformat(timespec="seconds") if dt else "",
            })
    return out

def decode_google_news(link: str) -> str:
    if "news.google.com" not in (link or ""):
        return link
    if gnewsdecoder is None:
        return ""
    try:
        result = gnewsdecoder(link, interval=0.15)
        if isinstance(result, dict) and result.get("status"):
            decoded = str(result.get("decoded_url") or "").strip()
            if decoded.startswith("http") and "news.google.com" not in decoded:
                return decoded
    except Exception:
        pass
    return ""

def article_text(url: str) -> str:
    if not url:
        return ""
    try:
        return clean_text(fetch(url, timeout=18).decode("utf-8", errors="ignore"))[:50000]
    except Exception:
        return ""

def host_of(url: str) -> str:
    return (urlparse(url).hostname or "").lower()

def is_official(url: str) -> bool:
    host = host_of(url)
    return any(host == d or host.endswith("." + d) for d in OFFICIAL_DOMAINS)

def company_for(url: str, text: str = "") -> str:
    host = host_of(url)
    for domain, company in COMPANY_MAP.items():
        if host == domain or host.endswith("." + domain):
            return company
    low = text.lower()
    for key, company in (
        ("foxconn", "Foxconn"), ("wistron", "Wistron"), ("quanta", "Quanta"),
        ("wiwynn", "Wiwynn"), ("bizlink", "BizLink-KY"), ("delta electronics", "Delta Electronics"),
        ("elite material", "Elite Material"), ("auras", "Auras Technology"),
    ):
        if key in low:
            return company
    return host or "공식자료"

def normalize_for_category(text: str) -> str:
    return " " + re.sub(r"[^a-z0-9.+/-]+", " ", (text or "").lower()) + " "

def classify_categories(text: str) -> list[str]:
    low = normalize_for_category(text)
    out = []
    for category, aliases in CATEGORY_ALIASES.items():
        if any(alias in low for alias in aliases):
            out.append(category)
    return out

def has_supply_change(text: str) -> bool:
    low = text.lower()
    return any(k in low for k in (
        "lead time", "lead times", "shortage", "shortages", "supply constraint",
        "supply constraints", "tight supply", "capacity constraint", "capacity constraints",
        "caps output", "material availability", "booked", "sold out", "allocation",
        "price increase", "price increases", "raise prices", "higher prices",
        "capacity expansion", "expand capacity", "production capacity",
        "mass production", "customer shipments", "shipments begin", "shipping",
        "qualification", "qualified", "certification", "certified",
        "order backlog", "backlog", "shipment growth", "shipments grow",
    ))

def metric_snippets(text: str) -> list[str]:
    out = []
    patterns = (
        r"\b\d+(?:\.\d+)?\s*(?:[-–~]\s*\d+(?:\.\d+)?)?\s*(?:weeks?|months?|주|개월)\b",
        r"\b\d+(?:\.\d+)?\s*%",
        r"\b\d+(?:\.\d+)?\s*(?:MW|GW|kW)\b",
        r"\b(?:more than|over|at least)\s+(?:double|twice)\b",
        r"\b\d+(?:\.\d+)?\s*(?:million|billion)?\s*(?:units?|racks?)\b",
    )
    for pattern in patterns:
        for m in re.finditer(pattern, text, re.I):
            token = clean_text(m.group(0))
            if token and token not in out:
                out.append(token)
            if len(out) >= 4:
                return out
    return out

def strong_stage(text: str) -> str:
    low = text.lower()
    stages = (
        ("mass production", "양산"),
        ("customer shipments", "고객 출하"),
        ("shipments begin", "출하 개시"),
        ("qualified", "고객·플랫폼 인증"),
        ("certified", "인증"),
        ("sold out", "생산능력 소진"),
        ("caps output", "부품 부족으로 출하 제한"),
        ("capacity constraint", "생산능력 병목"),
        ("supply constraint", "공급 병목"),
        ("shortage", "공급 부족"),
    )
    for needle, label in stages:
        if needle in low:
            return label
    return ""

def parse_event(text: str, url: str, title: str, published: str) -> dict:
    if not is_official(url):
        return {}
    categories = classify_categories(text)
    if not categories or not has_supply_change(text):
        return {}

    metrics = metric_snippets(text)
    stage = strong_stage(text)

    # 전망성 시장 침투율만으로는 병목 알림을 만들지 않는다.
    low = text.lower()
    pure_forecast = (
        any(k in low for k in ("forecast", "expected to reach", "projected to reach"))
        and not any(k in low for k in (
            "lead time", "shortage", "supply constraint", "capacity constraint",
            "mass production", "customer shipments", "caps output", "sold out",
        ))
    )
    if pure_forecast:
        return {}

    # 실제 숫자 또는 공급·양산 단계 진전 중 하나가 있어야 한다.
    if not metrics and not stage:
        return {}

    return {
        "categories": categories,
        "company": company_for(url, text),
        "title": title,
        "published_at_kst": published,
        "metrics": metrics,
        "stage": stage,
        "url": url,
    }

def signature(event: dict) -> str:
    payload = {
        "categories": event.get("categories") or [],
        "company": event.get("company") or "",
        "title": re.sub(r"\s+", " ", str(event.get("title") or "")).strip().lower(),
        "metrics": event.get("metrics") or [],
        "stage": event.get("stage") or "",
    }
    return hashlib.sha256(json.dumps(payload, sort_keys=True, ensure_ascii=False).encode()).hexdigest()[:24]

def load_json(path: pathlib.Path) -> dict:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}

def write_json(path: pathlib.Path, value: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

def newer_than(published: str, cutoff: str) -> bool:
    try:
        return datetime.fromisoformat(published) > datetime.fromisoformat(cutoff)
    except Exception:
        return False

def discover(previous: dict, now: datetime) -> list[dict]:
    seen_urls = set(previous.get("seen_urls") or [])
    seen_signatures = set(previous.get("seen_signatures") or [])
    cutoff = str(previous.get("last_checked_at_kst") or "")
    freshness = now - timedelta(days=21)
    local_urls = set()
    events = []
    fetched = 0

    for query in SEARCHES:
        try:
            items = read_rss(query)
        except Exception:
            continue
        for item in items:
            url = decode_google_news(item.get("link") or "")
            if not url or url in seen_urls or url in local_urls or not is_official(url):
                continue
            local_urls.add(url)
            published = item.get("published_at_kst") or ""
            try:
                dt = datetime.fromisoformat(published) if published else None
            except Exception:
                dt = None
            if dt is None or dt < freshness:
                continue
            if cutoff and not newer_than(published, cutoff):
                continue
            if fetched >= 14:
                continue
            fetched += 1

            base = clean_text((item.get("title") or "") + " " + (item.get("description") or ""))
            full = clean_text(base + " " + article_text(url))
            event = parse_event(full, url, item.get("title") or "", published)
            if not event:
                continue
            sig = signature(event)
            if sig in seen_signatures:
                continue
            event["signature"] = sig
            events.append(event)

    events.sort(key=lambda e: e.get("published_at_kst") or "")
    return events

def category_label(category: str) -> str:
    return {
        "AEC": "AEC(액티브 전기 케이블)",
        "LIQUID_COOLING": "액체냉각",
        "POWER": "PSU·전력",
        "PCB_CCL": "PCB·CCL",
        "ODM_RACK": "ODM·랙",
    }.get(category, category)

def event_line(event: dict) -> str:
    cats = "·".join(category_label(c) for c in event.get("categories") or [])
    detail = []
    if event.get("stage"):
        detail.append(str(event["stage"]))
    detail.extend(str(x) for x in event.get("metrics") or [])
    suffix = " / ".join(detail[:4])
    return (
        f"• <b>{html.escape(cats)}</b> — {html.escape(str(event.get('company') or '공식자료'))}"
        + (f": {html.escape(suffix)}" if suffix else "")
    )

def build_alert(events: list[dict]) -> str:
    categories = []
    source_urls = []
    for event in events:
        for c in event.get("categories") or []:
            if c not in categories:
                categories.append(c)
        url = str(event.get("url") or "")
        if url and url not in source_urls:
            source_urls.append(url)

    lines = [
        "<b>🚨 AI 서버 실물 병목 변화</b>",
        "",
        "<b>변화</b>",
        *[event_line(e) for e in events[:5]],
        "",
        "<b>의미</b>",
        "• GPU 수요만이 아니라 케이블·냉각·전력·기판·랙 생산능력이 실제 AI 서버 출하 속도를 제한하는지 확인하는 신호입니다.",
    ]

    beneficiaries = [BENEFICIARIES[c] for c in categories if c in BENEFICIARIES]
    if beneficiaries:
        lines += ["", "<b>관련 기업</b>"]
        for row in beneficiaries[:4]:
            lines.append("• " + html.escape(row))

    checks = [NEXT_CHECK[c] for c in categories if c in NEXT_CHECK]
    if checks:
        lines += ["", "<b>다음 확인</b>", "• " + html.escape(" / ".join(dict.fromkeys(checks)))]

    if source_urls:
        lines += ["", "<b>원문</b>"]
        for url in source_urls[:4]:
            lines.append(f'• <a href="{html.escape(url, quote=True)}">공식 원문</a>')

    return "\n".join(lines).strip() + "\n"

def main() -> None:
    now = datetime.now(ZoneInfo("Asia/Seoul"))
    previous = load_json(STATE_PATH) or copy.deepcopy(BASELINE)
    latest = copy.deepcopy(previous)
    events = discover(previous, now)

    seen_urls = set(previous.get("seen_urls") or [])
    seen_signatures = set(previous.get("seen_signatures") or [])
    for event in events:
        if event.get("url"):
            seen_urls.add(str(event["url"]))
        if event.get("signature"):
            seen_signatures.add(str(event["signature"]))

    latest["seen_urls"] = sorted(seen_urls)[-250:]
    latest["seen_signatures"] = sorted(seen_signatures)[-500:]
    latest["last_checked_at_kst"] = now.isoformat(timespec="seconds")
    latest["candidate_count"] = len(events)
    latest["event_count"] = len(events)
    write_json(PENDING_PATH, latest)

    if events:
        ALERT_PATH.parent.mkdir(parents=True, exist_ok=True)
        ALERT_PATH.write_text(build_alert(events), encoding="utf-8")

    print(
        "ai_server_physical_bottleneck_watch=true "
        f"candidates={len(events)} events={len(events)} notify={str(bool(events)).lower()}"
    )

if __name__ == "__main__":
    main()
