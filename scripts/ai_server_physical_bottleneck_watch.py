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

# Global Electronics Association (formerly IPC) structural PCB alert.
# One existing-route backfill is sourced to the association's 2026-11-19
# release and its original issuer-supplied GlobeNewswire distribution.
# Date is the 00:05 ET distribution time, NOT the 2026-09 statistics period.
PCB_ALERT_KEY = "gea-pcb-squeeze-2026-11-19-3406285-v1"
PCB_OFFICIAL_RELEASE = (
    "https://www.electronics.org/news-release/"
    "global-electronics-association-growing-shortages-across-pcb-supply-chain-threaten-next"
)
PCB_ORIGINAL_DISTRIBUTION = (
    "https://www.globenewswire.com/news-release/2026/11/19/3406285/0/en/"
    "global-electronics-association-growing-shortages-across-the-pcb-supply-chain-"
    "threaten-the-next-wave-of-ai-and-electronics.html"
)
PCB_ISSUER_NOTE = "https://www.electronics.org/pcb-global-advisory-explanatory-note"
PCB_ISSUED_AT_KST = "2026-11-19T14:05:00+09:00"
PCB_SOURCE_VALIDATION_MARKERS = (
    "global electronics association",
    "pcb",
    "56.1",
    "13.3",
    "2028",
)
PCB_FACT_SNAPSHOT = {
    "publication_date": "2026-11-19",
    "source_kind": "issuer_release_and_original_issuer_distribution_verified_2026_11_19",
    "pcb_typical_pc_layers": 12,
    "pcb_ai_server_layers_min": 40,
    "pcb_ai_server_layers_plus": 60,
    "high_layer_pcb_lead_time_weeks_min": 16,
    "high_layer_pcb_lead_time_weeks_max": 20,
    "lead_time_more_possible": True,
    "na_ytd_period": "2026-01_to_2026-09",
    "na_bookings_ytd_yoy_pct": 56.1,
    "na_shipments_ytd_yoy_pct": 13.3,
    "asia_global_pcb_production_share_over_pct": 90,
    "southeast_asia_pcb_plant_investment_usd_bn_min": 10,
    "china_pcb_plant_investment_usd_bn_min": 10,
    "investment_lookback_years": 3,
    "constraint_through": "2027H1_at_least",
    "meaningful_relief_not_before": "2028_mid_issuer_outlook",
    "is_confirmed_supply_failure_for_all_customers": False,
}

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
        "uqd_current_2026_shortage_confirmed": False,
        "uqd_historical_tight_supply_2024_reported": True,
        "parker_uqd_exclusive_supply_confirmed": False,
        "parker_uqd_multi_vendor_interchangeable": True,
        "parker_uqdb_radial_compensation_mm": 1.0,
        "five_micron_manifold_tolerance_confirmed": False,
        "vertiv_100kw_plus_dlc_confirmed": True,
        "vertiv_vacuum_brazed_stainless_manifold_confirmed": True,
        "nvent_stainless_manifold_parker_nsp06_confirmed": True,
        "ubs_semicap_project_leadtime_months_min": 12.0,
        "ubs_semicap_project_leadtime_months_max": 24.0,
        "ubs_semicap_metric_is_project_leadtime": True,
        "trendforce_major_semicap_tool_delivery_max_months": 12.0,
        "trendforce_semicap_component_max_leadtime_months": 40.0,
        "asml_euv_capacity_booked_through_year": 2027,
    },
    "seen_urls": [
        "https://www.trendforce.com/presscenter/news/20260415-13013.html",
        "https://www.trendforce.com/research/download/RP260903XY3",
        "https://www.trendforce.com/presscenter/news/20260817-13183.html",
        "https://www.trendforce.com/presscenter/news/20260625-13121.html",
        "https://telecom-networking.bizlinktech.com/applications/bizlink-data-center-solutions/",
        "https://www.deltaww.com/en-US/investors/chairman-statement",
        "https://image.honhai.com/upload/202605/law_talk/Hon_Hai_1Q26_Results_Transcript_English_20260514_3576.pdf",
        "https://ph.parker.com/TR/en/parker-universal-quick-disconnect-blindmate-couplings-for-liquid-cooling-uqdb-series",
        "https://www.nvent.com/en-us/hoffman/products/encrcm42001h",
        "https://www.vertiv.com/en-asia/products-catalog/thermal-management/high-density-solutions/vertiv-coolchip-fluid-network-rack-manifolds/",
        "https://www.coolitsystems.com/products-services/server-products/rack-manifolds/",
        "https://www.opencompute.org/ai-marketplace/products/498/cejn-universal-blind-mate-quick-connector-bmqc",
        "https://www.digitimes.com/news/a20240717PD200/ai-server-heat-dissipation-liquid-cooling-production-capacity.html",
        "https://www.trendforce.com/news/2026/09/18/news-chip-equipment-component-lead-times-reportedly-double-stretching-to-40-months-as-price-pressures-mount/",
        "https://www.reuters.com/business/asml-tops-q2-estimates-ai-chip-demand-2026-07-15/",
        "https://www.reuters.com/business/asml-breaks-ground-new-manufacturing-facilities-major-expansion-2026-09-08/",
    ],
    "seen_signatures": [],
    "last_checked_at_kst": "2026-10-03T21:09:00+09:00",
    "candidate_count": 0,
    "event_count": 0,
}

SEARCHES = [
    'site:electronics.org/news-release PCB supply shortage glass fabric copper foil AI 2026',
    '"Global Electronics Association" "PCB" "lead times" "materials"',
    'site:trendforce.com 2026 AI server (AEC OR "active electrical cable" OR PSU OR "power supply" OR "liquid cooling" OR CCL OR PCB OR ODM) shortage lead time capacity',
    'site:bizlinktech.com 2026 AEC "AI data center" shipment capacity qualification',
    'site:deltaww.com 2026 AI server power liquid cooling 800V shipment capacity',
    'site:honhai.com 2026 AI server rack shipment material supply capacity',
    'site:wistron.com 2026 AI server rack shipment capacity',
    'site:quantatw.com 2026 AI server rack shipment capacity',
    'site:wiwynn.com 2026 AI server rack shipment capacity',
    'site:emctw.com 2026 AI server CCL capacity shipment price',
    'site:auras.com.tw 2026 AI server liquid cooling cold plate capacity shipment',
    'site:avc.co 2026 AI server liquid cooling cold plate CDU capacity shipment',
    'site:liteon.com 2026 AI server power supply power shelf 800V capacity shipment',
    'site:tuc.com.tw 2026 AI server CCL copper clad laminate capacity shipment price',
    'site:parker.com 2026 data center liquid cooling UQD UQDB quick disconnect capacity lead time shortage shipment qualification',
    'site:nvent.com OR site:investors.nvent.com 2026 data center rack manifold liquid cooling capacity production shipment',
    'site:vertiv.com 2026 rack manifold UQD quick disconnect liquid cooling capacity shipment',
    'site:coolitsystems.com 2026 rack manifold quick disconnect liquid cooling capacity shipment',
    'site:opencompute.org 2026 UQD UQDB BMQC PBMC liquid cooling manifold interoperability',
    'site:digitimes.com 2026 UQD quick disconnect manifold liquid cooling shortage lead time AI server',
    'site:trendforce.com 2026 semiconductor equipment component lead time lithography deposition etch packaging 40 months',
    'site:asml.com 2026 EUV capacity booked production capacity AI demand',
    'site:appliedmaterials.com 2026 AI semiconductor equipment capacity backlog shipment lead time',
    'site:lamresearch.com 2026 AI wafer fabrication equipment capacity backlog shipment',
    'site:kla.com 2026 AI semiconductor process control equipment capacity backlog shipment',
    'site:tel.com 2026 semiconductor production equipment AI capacity shipment lead time',
    'site:reuters.com 2026 ASML semiconductor equipment capacity booked EUV AI',
]

OFFICIAL_DOMAINS = (
    "electronics.org",
    "trendforce.com",
    "bizlinktech.com",
    "deltaww.com",
    "honhai.com",
    "wistron.com",
    "quantatw.com",
    "wiwynn.com",
    "emctw.com",
    "auras.com.tw",
    "avc.co",
    "liteon.com",
    "tuc.com.tw",
    "parker.com",
    "nvent.com",
    "investors.nvent.com",
    "vertiv.com",
    "coolitsystems.com",
    "opencompute.org",
    "asml.com",
    "appliedmaterials.com",
    "lamresearch.com",
    "kla.com",
    "tel.com",
    "semi.org",
    "nvidia.com",
    "investor.nvidia.com",
)

TRUSTED_DOMAINS = (
    "digitimes.com",
    "reuters.com",
)

CATEGORY_ALIASES = {
    "AEC": (
        "active electrical cable", "active electrical cables", " aec ", " aecs ",
        "800g aec", "1.6t aec",
    ),
    "LIQUID_COOLING": (
        "liquid cooling", "liquid-cooled", "cold plate", "cold plates", "cdu",
        "coolant distribution unit",
    ),
    "UQD_MANIFOLD": (
        "universal quick disconnect", "universal quick disconnects",
        " uqd ", " uqds ", "uqdb", "blind mate quick", "blind-mate quick",
        "bmqc", "pbmc", "rack manifold", "rack manifolds", "coolant manifold",
        "fluid network rack manifold", "quick disconnect", "quick disconnects",
        "dripless quick", "dry-break quick",
    ),
    "SEMICAP_EQUIPMENT": (
        "semiconductor equipment", "semicap equipment", "wafer fabrication equipment",
        " wfe ", "lithography tool", "lithography tools", "euv tool", "euv tools",
        "duv tool", "duv tools", "deposition equipment", "etch equipment",
        "inspection equipment", "metrology equipment", "chipmaking equipment",
        "chip-making equipment",
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
    "avc.co": "AVC(Asia Vital Components)",
    "liteon.com": "Lite-On",
    "tuc.com.tw": "TUC",
    "parker.com": "Parker Hannifin",
    "nvent.com": "nVent",
    "investors.nvent.com": "nVent",
    "vertiv.com": "Vertiv",
    "coolitsystems.com": "CoolIT Systems (Ecolab)",
    "opencompute.org": "Open Compute Project",
    "asml.com": "ASML",
    "appliedmaterials.com": "Applied Materials",
    "lamresearch.com": "Lam Research",
    "kla.com": "KLA",
    "tel.com": "Tokyo Electron",
    "semi.org": "SEMI",
    "reuters.com": "Reuters",
    "digitimes.com": "DIGITIMES",
    "nvidia.com": "NVIDIA",
    "investor.nvidia.com": "NVIDIA",
    "trendforce.com": "TrendForce",
    "electronics.org": "Global Electronics Association",
}

BENEFICIARIES = {
    "AEC": "BizLink-KY — AEC·고속 구리 인터커넥트",
    "LIQUID_COOLING": "AVC(Asia Vital Components)·Delta Electronics·Auras Technology·BOYD — 콜드플레이트·CDU·열관리",
    "UQD_MANIFOLD": "Parker Hannifin·nVent·Vertiv·CoolIT Systems(Ecolab) — UQD/BMQC·드립리스 커플링·랙 매니폴드·유체 분배",
    "SEMICAP_EQUIPMENT": "ASML·Applied Materials·Lam Research·Tokyo Electron·KLA — 노광·증착·식각·검사·계측 장비",
    "POWER": "Delta Electronics·Lite-On — PSU·고전력 전원변환·800V HVDC",
    "PCB_CCL": "Elite Material(台光電)·TUC — 고속·저손실 CCL / AI 서버 PCB 상류",
    "ODM_RACK": "Foxconn·Wistron·Quanta·Wiwynn — AI 서버·랙 통합",
}

NEXT_CHECK = {
    "AEC": "리드타임·800G/1.6T 양산·고객 인증·생산능력",
    "LIQUID_COOLING": "콜드플레이트/CDU 인증·출하·생산능력·누수/신뢰성",
    "UQD_MANIFOLD": "UQD/BMQC 리드타임·다중 공급사 인증·매니폴드 생산능력·누설 시험·고객 승인",
    "SEMICAP_EQUIPMENT": "장비 납기·핵심 부품 납기·수주잔고·EUV/High-NA 예약연도·신공장 생산능력",
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

def is_trusted(url: str) -> bool:
    host = host_of(url)
    return any(host == d or host.endswith("." + d) for d in TRUSTED_DOMAINS)

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
        ("parker hannifin", "Parker Hannifin"), ("nvent", "nVent"), ("vertiv", "Vertiv"),
        ("coolit", "CoolIT Systems (Ecolab)"),
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
        r"\b\d{1,3}(?:,\d{3})+\s*(?:square feet|sq\.?\s*ft\.?)\b",
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
        ("capacity expansion", "생산능력 증설"),
        ("expanded capacity", "생산능력 증설"),
        ("supply constraint", "공급 병목"),
        ("shortage", "공급 부족"),
    )
    for needle, label in stages:
        if needle in low:
            return label
    return ""

def parse_event(text: str, url: str, title: str, published: str) -> dict:
    source_official = is_official(url)
    source_trusted = is_trusted(url)
    if not source_official and not source_trusted:
        return {}

    sentences = re.split(r"(?<=[.!?])\s+", text)
    candidates = []
    for sentence in sentences:
        window = clean_text(sentence)
        categories = classify_categories(window)
        if not categories or not has_supply_change(window):
            continue
        if source_trusted and not source_official and not ({"UQD_MANIFOLD", "SEMICAP_EQUIPMENT"} & set(categories)):
            continue

        low = window.lower()
        pure_forecast = (
            any(k in low for k in ("forecast", "expected to reach", "projected to reach"))
            and not any(k in low for k in (
                "lead time", "shortage", "supply constraint", "capacity constraint",
                "mass production", "customer shipments", "caps output", "sold out",
                "material availability", "shipment growth", "shipments grow",
            ))
        )
        if pure_forecast:
            continue

        metrics = metric_snippets(window)
        stage = strong_stage(window)
        if not metrics and not stage:
            continue

        score = len(metrics) * 3 + len(categories) * 2 + (3 if stage else 0)
        candidates.append((score, categories, metrics, stage, window))

    if not candidates:
        return {}

    _, categories, metrics, stage, _ = max(candidates, key=lambda x: x[0])
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

def discover(previous: dict, now: datetime, health: dict | None = None) -> list[dict]:
    seen_urls = set(previous.get("seen_urls") or []) | set(BASELINE.get("seen_urls") or [])
    seen_signatures = set(previous.get("seen_signatures") or [])
    cutoff = str(previous.get("last_checked_at_kst") or "")
    freshness = now - timedelta(days=21)
    local_urls = set()
    events = []
    fetched = 0
    rss_success = 0
    rss_failure = 0

    for query in SEARCHES:
        try:
            items = read_rss(query)
        except Exception:
            rss_failure += 1
            continue
        rss_success += 1
        for item in items:
            url = decode_google_news(item.get("link") or "")
            if not url or url in seen_urls or url in local_urls or not (is_official(url) or is_trusted(url)):
                continue
            local_urls.add(url)
            published = item.get("published_at_kst") or ""
            try:
                dt = datetime.fromisoformat(published) if published else None
            except Exception:
                dt = None
            if dt is None or dt < freshness:
                continue
            # PCB association releases can be indexed after a previous scan.
            # An unseen, fresh official issuer URL remains eligible for backfill.
            is_pcb_issuer = host_of(url) in ("electronics.org", "www.electronics.org")
            if cutoff and not newer_than(published, cutoff) and not is_pcb_issuer:
                continue
            # This exact origin is handled by its own stable fact key, once.
            if url.split("?")[0].rstrip("/") == PCB_OFFICIAL_RELEASE:
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
    if health is not None:
        health.update({
            "rss_success_count": rss_success,
            "rss_failure_count": rss_failure,
            "status": ("lookup_failed" if not rss_success else
                       "partially_degraded" if rss_failure else "checked"),
        })
    return events

def category_label(category: str) -> str:
    return {
        "AEC": "AEC(액티브 전기 케이블)",
        "LIQUID_COOLING": "액체냉각",
        "UQD_MANIFOLD": "UQD·랙 매니폴드",
        "SEMICAP_EQUIPMENT": "반도체 장비",
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
        "• GPU 수요만이 아니라 반도체 장비·케이블·냉각·전력·기판·랙 생산능력이 실제 AI 서버 증설·출하 속도를 제한하는지 확인하는 신호입니다.",
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


def pcb_publisher_probe(now: datetime) -> dict:
    """Record real issuer access separately from the externally reviewed source snapshot."""
    observations = []
    for label, url in (
        ("issuer", PCB_OFFICIAL_RELEASE),
        ("origin_distribution", PCB_ORIGINAL_DISTRIBUTION),
    ):
        try:
            raw = fetch(url, timeout=12).decode("utf-8", errors="replace")
            text = clean_text(raw).lower()
        except Exception as exc:
            observations.append({"source": label, "status": "lookup_failed", "error_type": type(exc).__name__})
            continue
        if all(marker in text for marker in PCB_SOURCE_VALIDATION_MARKERS):
            observations.append({"source": label, "status": "verified"})
            return {
                "status": "verified",
                "source": label,
                "checked_at_kst": now.isoformat(timespec="seconds"),
                "observations": observations,
            }
        observations.append({"source": label, "status": "content_incomplete"})
    status = (
        "lookup_failed"
        if observations and all(item["status"] == "lookup_failed" for item in observations)
        else "content_incomplete"
    )
    return {
        "status": status,
        "checked_at_kst": now.isoformat(timespec="seconds"),
        "observations": observations,
    }


def pcb_alert_event(previous: dict, now: datetime, probe: dict) -> dict | None:
    """Restore one independently verified release; avoid repeating by confirmed state key."""
    if not datetime.fromisoformat(PCB_ISSUED_AT_KST) <= now <= (
        datetime.fromisoformat(PCB_ISSUED_AT_KST) + timedelta(days=21)
    ):
        return None
    sent = set((previous.get("pcb_association") or {}).get("delivered_fact_keys") or [])
    if PCB_ALERT_KEY in sent:
        return None
    return {
        "event_key": PCB_ALERT_KEY,
        "source": PCB_OFFICIAL_RELEASE,
        "distributed_source": PCB_ORIGINAL_DISTRIBUTION,
        "source_status": str(probe.get("status") or "unverified"),
        "facts": copy.deepcopy(PCB_FACT_SNAPSHOT),
        "stage": "issuer_industry_warning_and_forecast_not_customer_order_or_sales",
    }


def pcb_alert_text(event: dict) -> str:
    """Differentiate North American YTD growth, multilayer PCB, and ABF substrate."""
    status = event.get("source_status") or ""
    source_line = (
        "• 원천 재조회: 이번 실행에서 발행사 보도자료를 직접 확인."
        if status == "verified" else
        "• 원천 재조회: 이번 실행에서는 직접 원문 접근이 제한됐으며, "
        "11/19 사전 대조한 협회 발표·GlobeNewswire 원문과 제공 메모를 근거로 선행경보를 복구."
    )
    lines = [
        "<b>🚨 AI 서버 초다층 PCB 공급망 공식 경보 — 글로벌전자협회</b>",
        "• <b>신규 사건:</b> 2026-11-19 협회(구 IPC) 산업 경보. AI용 초다층 기판·핵심 소재가 "
        "자동차·산업·의료·방산·통신용 공급까지 밀어내는 위험을 경고.",
        "• <b>제품 구분:</b> 일반 PC 약 12층 → AI 서버 PCB 40~60층 이상. "
        "유리섬유 직물·수지·동박·적층판 사용량 증가.",
        "• <b>공급 실측:</b> 고다층 <b>PCB</b> 리드타임 16~20주 이상. "
        "기존 ABF 반도체 패키지 기판 48~56주와 다른 제품·시계열이므로 합산·비교 금지.",
        "• <b>북미 PCB 2026년 1~9월 누적 전년 동기비:</b> 수주 +56.1%, 출하 +13.3%. "
        "전세계 통계 또는 최근 12개월 수치가 아님.",
        "• <b>공급 지역:</b> 아시아 생산비중 90% 초과; 지난 3년 동남아·중국의 신규 PCB 공장 투자는 "
        "각각 100억달러(약 13조3,110억원) 이상이지만 소재 공급은 별도 병목.",
        "• <b>협회 전망:</b> 최소 2027년 상반기까지 공급 제약, 의미 있는 완화는 "
        "2028년 중반 이전 어려울 전망. 확정 납품 실패나 개별 기업 가격 인상 공시 아님.",
        "• <b>대응·위험:</b> 적층판·프리프레그·동박 대체 공급사 인증, 수율·고객 승인, "
        "원자재와 신공장 증설 시차를 추적. 선구매 후 2027년 수요 둔화·공급과잉 가능성도 점검.",
        "• <b>판정:</b> 협회 산업 선행경보(2021년 반도체난에 비견될 수 있다는 경고), "
        "특정 제조사 수주·실제 매출 확정 아님.",
        "• 환산 기준: 2026-11-19 한국은행 ECOS 기준환율 1달러=1,331.10원; "
        "회사의 실제 투자환율이 아닌 보조 환산.",
        source_line,
        f'• <a href="{html.escape(PCB_OFFICIAL_RELEASE, quote=True)}">협회 공식 발표</a> / '
        f'<a href="{html.escape(PCB_ORIGINAL_DISTRIBUTION, quote=True)}">원문 배포</a>',
    ]
    return "\n".join(lines).strip() + "\n"


def main() -> None:
    now = datetime.now(ZoneInfo("Asia/Seoul"))
    previous = load_json(STATE_PATH) or copy.deepcopy(BASELINE)
    latest = copy.deepcopy(previous)
    latest.setdefault("facts", {})
    for key, value in (BASELINE.get("facts") or {}).items():
        latest["facts"].setdefault(key, value)
    rss_health: dict = {"rss_success_count": 0, "rss_failure_count": 0, "status": "lookup_failed"}
    events = discover(previous, now, rss_health)
    existing_pcb = dict(previous.get("pcb_association") or {})
    probe = pcb_publisher_probe(now)
    pcb_event = pcb_alert_event(previous, now, probe)

    seen_urls = set(previous.get("seen_urls") or []) | set(BASELINE.get("seen_urls") or [])
    seen_signatures = set(previous.get("seen_signatures") or [])
    for event in events:
        if event.get("url"):
            seen_urls.add(str(event["url"]))
        if event.get("signature"):
            seen_signatures.add(str(event["signature"]))

    latest["seen_urls"] = sorted(seen_urls)[-250:]
    latest["seen_signatures"] = sorted(seen_signatures)[-500:]
    latest["last_checked_at_kst"] = now.isoformat(timespec="seconds")
    if rss_health["rss_success_count"] or probe["status"] == "verified":
        latest["last_successful_source_at_kst"] = now.isoformat(timespec="seconds")
    latest["source_health"] = {
        "checked_at_kst": now.isoformat(timespec="seconds"),
        "rss": rss_health,
        "pcb_publisher": probe,
        "status": ("lookup_failed" if rss_health["status"] == "lookup_failed"
                   and probe["status"] != "verified"
                   else "partially_degraded" if rss_health["rss_failure_count"]
                   or probe["status"] != "verified" else "checked"),
    }
    latest["pcb_association"] = existing_pcb
    latest["pcb_association"]["last_source_check"] = probe
    if pcb_event:
        keys = set(existing_pcb.get("delivered_fact_keys") or [])
        latest["pcb_association"]["delivered_fact_keys"] = sorted(keys | {PCB_ALERT_KEY})
        latest["pcb_association"]["last_evidence"] = pcb_event
    latest["candidate_count"] = len(events) + int(bool(pcb_event))
    latest["event_count"] = len(events) + int(bool(pcb_event))
    write_json(PENDING_PATH, latest)

    notices = []
    if pcb_event:
        notices.append(pcb_alert_text(pcb_event).strip())
    if events:
        notices.append(build_alert(events).strip())
    if notices:
        ALERT_PATH.parent.mkdir(parents=True, exist_ok=True)
        ALERT_PATH.write_text("\n\n".join(notices) + "\n", encoding="utf-8")

    print(
        "ai_server_physical_bottleneck_watch=true "
        f"candidates={latest['candidate_count']} events={latest['event_count']} "
        f"notify={str(bool(notices)).lower()} sources={latest['source_health']['status']} "
        f"pcb_publisher={probe['status']}"
    )

if __name__ == "__main__":
    main()
