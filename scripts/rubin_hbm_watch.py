from __future__ import annotations

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
except Exception:  # pragma: no cover - dependency failure is handled explicitly
    gnewsdecoder = None

ROOT = pathlib.Path(__file__).resolve().parents[1]
DATA = ROOT / "data" / "rubin_hbm_watch_state.json"
OUT = ROOT / "out"
OUT.mkdir(exist_ok=True)

UA = "Mozilla/5.0 (compatible; khs-watch/2.0; +https://github.com/qedgwangju-dot/khs-watch)"
FX_URL = "https://api.frankfurter.dev/v2/rate/USD/KRW"

OFFICIAL_RUBIN_GB = 288
RUMORED_ULTRA_GB = 192
BREAKEVEN_GPU_GROWTH = OFFICIAL_RUBIN_GB / RUMORED_ULTRA_GB - 1
BERNSTEIN_RUBIN_PREVIOUS_GB = 1024
BERNSTEIN_RUBIN_CURRENT_GB = 640
BERNSTEIN_RUBIN_REDUCTION_PCT = (BERNSTEIN_RUBIN_CURRENT_GB / BERNSTEIN_RUBIN_PREVIOUS_GB - 1) * 100
BERNSTEIN_RUBIN_BREAK_EVEN_GPU_GROWTH = BERNSTEIN_RUBIN_PREVIOUS_GB / BERNSTEIN_RUBIN_CURRENT_GB - 1
BASE_NVLINK_GPU = 72
ULTRA_NVLINK_GPU = 576
BASE_SYSTEM_GB = BASE_NVLINK_GPU * OFFICIAL_RUBIN_GB
ULTRA_SYSTEM_GB = ULTRA_NVLINK_GPU * RUMORED_ULTRA_GB
SYSTEM_HBM_GROWTH = ULTRA_SYSTEM_GB / BASE_SYSTEM_GB - 1
SEND_FRESHNESS_HOURS = 72
SAMSUNG_HBM4_PRICE_TRACK_VERSION = 1
SAMSUNG_HBM4_PRICE_BASELINE = {
    "stage": "negotiation",
    "offered_price_band": "mid_to_high_4_usd_per_gb",
    "offered_price_usd_per_gb_min": None,
    "offered_price_usd_per_gb_max": None,
    "reference_hbm3e_usd_per_gb": 1.5,
    "price_multiple_floor": 3.0,
    "volume_stage": "largely_agreed",
    "target_close_month": "2026-10",
    "source": "매일경제 단독",
    "source_url": "https://www.mk.co.kr/news/business/12167164",
    "as_of": "2026-10-02",
    "note": "4달러대 중후반은 기사 표현 그대로 보존. 정확한 상·하단 가격으로 임의 환산하지 않음.",
}
SAMSUNG_HBM4E_THERMAL_TRACK_VERSION = 1
SAMSUNG_HBM4E_THERMAL_BASELINE = {
    "industry_current_interposer_reticle_x": 5.5,
    "reported_future_interposer_reticle_x": 40.0,
    "reported_future_interposer_stage": "industry_projection",
    "tsmc_official_2028_cowos_reticle_x": 14.0,
    "hbm4e_thermal_resistance_improvement_pct": 14.0,
    "hcb_thermal_resistance_improvement_pct": 20.0,
    "hcb_stage": "technology_showcase",
    "hpb_stage": "hbm4e_validation",
    "hpb_target_generation": "hbm5",
    "package_system_cooling_stage": "reported_review",
    "source": "조선비즈 + 삼성전자 공식자료 + TSMC 공식자료",
    "source_url": "https://biz.chosun.com/it-science/ict/2026/10/02/MHAFNCALYJDI5P3MKV3F3MXINE/?outputType=amp",
    "as_of": "2026-10-02",
    "note": "40배는 장비업계의 장기 전망으로 저장하고 삼성 HBM4E 확정 로드맵으로 승격하지 않음. TSMC 공식 CoWoS 로드맵은 2028년 14배, 2029년 14배 초과이며 40배는 SoW-X 별도 구조.",
}
CITI_HBM_TRACK_VERSION = 1
CITI_HBM_BASELINE = {
    "demand_2027_yoy_pct": 62.0,
    "demand_2027_100m_gb": 752.0,
    "demand_2028_yoy_pct": 69.0,
    "demand_2028_100m_gb": 1270.0,
    "supply_2027_yoy_pct": 64.0,
    "supply_2027_100m_gb": 593.0,
    "supply_2028_yoy_pct": 36.0,
    "supply_2028_100m_gb": 809.0,
    "deficit_2027_pct": -21.0,
    "deficit_2028_pct": -36.0,
    "samsung_2027_wpm": 240000.0,
    "skhynix_2027_wpm": 270000.0,
    "micron_2027_wpm": 140000.0,
    "samsung_2027_capacity_yoy_pct": 50.0,
    "skhynix_2027_capacity_yoy_pct": 67.0,
    "micron_2027_capacity_yoy_pct": 52.0,
    "hbm4_12hi_usd_per_gb_min": 4.0,
    "hbm4_12hi_usd_per_gb_max": 5.0,
    "hbm4_12hi_price_yoy_min_pct": 100.0,
    "hbm4_12hi_price_yoy_max_pct": 150.0,
    "eight_hi_premium_min_pct": 20.0,
    "eight_hi_premium_max_pct": 30.0,
    "source": "Citi 리서치 재인용",
    "source_url": "https://www.aastocks.com/tc/stocks/news/aafn-con/NOW.1547209/latest-news/AAFN",
    "secondary_source_url": "https://newsis.com/view/NISX20260930_0003808711",
    "as_of": "2026-09-30",
}
STRUCTURE_BASELINE_VERSION = 3
KNOWN_STRUCTURE_FACT_KEYS = {
    "hbm_capacity_kv_offload_mainstream_8hi_12hi_niche_4hi",
    "bernstein_rubin_ultra_model_1024_to_640_8hi50_12hi50",
    "bernstein_hbm_supplier_relative_samsung_up_skhynix_down",
    "bernstein_hbm_supplier_relative_samsung_up",
    "bernstein_hbm_supplier_relative_skhynix_down",
}

QUERIES = [
    (
        "rubin_spec",
        '"Rubin Ultra" (HBM OR HBM4 OR HBM4E OR 192GB OR 288GB OR 1TB OR 8-Hi OR 12-Hi)',
    ),
    (
        "rubin_broker_model",
        '"Rubin Ultra" Bernstein (1024GB OR 640GB OR "8-Hi" OR "12-Hi" OR HBM)',
    ),
    (
        "hbm_supplier_relative",
        'Bernstein HBM Samsung share "SK hynix" progress pricing market share',
    ),
    (
        "hbm4e_validation",
        'HBM4E (qualification OR validation OR sample OR mass production OR production) (Samsung OR "SK hynix" OR Micron)',
    ),
    (
        "hbm4e_thermal_package",
        'Samsung HBM4E (thermal OR heat OR cooling OR HCB OR HPB OR "hybrid bonding" OR interposer OR reticle OR package OR 발열 OR 냉각 OR 하이브리드본딩 OR 하이브리드 본딩 OR 인터포저 OR 열저항 OR 패키지)',
    ),
    (
        "rubin_shipments",
        '"Rubin Ultra" (NVL576 OR shipment OR production OR deployment OR order OR ramp OR customer)',
    ),
    (
        "samsung_hbm4_price",
        'Samsung HBM4 2027 (price OR pricing OR contract OR negotiation OR annual supply OR 4 dollars OR 3x OR triple OR 가격 OR 협상 OR 공급가)',
    ),
    (
        "hbm_2027_contract",
        '2027 HBM (contract OR price OR pricing OR LTA OR supply OR allocation OR volume OR negotiation OR agreement) (Samsung OR "SK hynix" OR Micron OR NVIDIA)',
    ),
    (
        "citi_hbm_outlook",
        'Citi HBM 2027 2028 (demand OR supply OR deficit OR shortage OR wafer OR WPM OR 12-Hi OR 8-Hi OR 752 OR 593 OR 1270 OR 809)',
    ),
    (
        "hbm_wafer_economics",
        '(HBM AND DDR5) (wafer revenue OR profitability OR economics OR "64GB RDIMM" OR 웨이퍼 매출 OR 수익성 OR 채산성) (TrendForce OR contract OR pricing OR allocation)',
    ),
    (
        "memory_migration",
        '(Rubin OR "Rubin Ultra" OR HBM) (DDR5 OR SOCAMM2 OR eSSD OR "enterprise SSD" OR "KV cache" OR offload OR pooling OR "8-Hi" OR "12-Hi" OR "4-Hi" OR 8단 OR 12단 OR 4단)',
    ),
    (
        "memory_migration",
        'TrendForce HBM "KV cache" (offload OR offloading OR HBF OR "SSD POD" OR CMX OR "8-Hi" OR "12-Hi" OR "4-Hi")',
    ),
]

CATEGORY_KO = {
    "rubin_spec": "Rubin Ultra 최종 HBM 사양",
    "rubin_broker_model": "Bernstein Rubin Ultra HBM 모델 가정",
    "hbm_supplier_relative": "삼성전자↔SK하이닉스 HBM 상대 변화",
    "hbm4e_validation": "HBM4E 고객 검증·양산",
    "hbm4e_thermal_package": "삼성 HBM4E 발열·인터포저·패키징 병목",
    "rubin_shipments": "Rubin Ultra·NVL576 실제 출하",
    "samsung_hbm4_price": "삼성전자 2027 HBM4 계약가격",
    "hbm_2027_contract": "2027 HBM 계약가격·물량",
    "citi_hbm_outlook": "Citi HBM 2027~2028 수요·공급·가격",
    "hbm_wafer_economics": "HBM↔DDR5 웨이퍼 경제성",
    "memory_migration": "별도 알림 · HBM 용량 축소→KV 캐시 외부 메모리 전환",
}

OFFICIAL_SOURCE_HINTS = (
    "nvidia", "samsung newsroom", "삼성전자 뉴스룸", "sk hynix", "sk하이닉스 뉴스룸",
    "micron technology", "micron newsroom",
)
TRUSTED_SOURCE_HINTS = (
    "trendforce", "reuters", "bloomberg", "the information", "semianalysis", "digitimes",
    "tom's hardware", "toms hardware", "financial times", "wall street journal", "wsj", "cnbc",
    "investing.com",
    "thelec", "the elec", "연합뉴스", "yonhap", "매일경제", "mk.co.kr",
)
LOW_VALUE_SOURCE_HINTS = (
    "finance.biggo", "aol", "24/7 wall st", "247wallst", "cryptobriefing",
)


def fetch(url: str, timeout: int = 25) -> bytes:
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.read()


def clean_text(value: str) -> str:
    value = html.unescape(value or "")
    value = re.sub(r"<[^>]+>", " ", value)
    return re.sub(r"\s+", " ", value).strip()


def rss_url(query: str, lang: str) -> str:
    q = urllib.parse.quote(query)
    if lang == "ko":
        return f"https://news.google.com/rss/search?q={q}&hl=ko&gl=KR&ceid=KR:ko"
    return f"https://news.google.com/rss/search?q={q}&hl=en-US&gl=US&ceid=US:en"


def parse_pubdate(value: str) -> datetime | None:
    try:
        dt = parsedate_to_datetime(value)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(ZoneInfo("Asia/Seoul"))
    except Exception:
        return None


def relevant(category: str, text: str) -> bool:
    low = text.lower()
    if category == "rubin_spec":
        return "rubin ultra" in low and any(k in low for k in ("hbm", "192gb", "288gb", "768gb", "1tb", "8-hi", "8hi", "12-hi", "12hi"))
    if category == "rubin_broker_model":
        return (
            "rubin ultra" in low
            and ("bernstein" in low or "伯恩斯坦" in text)
            and "hbm" in low
            and any(k in low for k in ("1024gb", "1,024gb", "640gb", "8-hi", "8hi", "12-hi", "12hi"))
        )
    if category == "hbm_supplier_relative":
        return (
            ("bernstein" in low or "伯恩斯坦" in text)
            and "hbm" in low
            and "samsung" in low
            and any(k in low for k in ("sk hynix", "sk하이닉스"))
            and any(k in low for k in ("share", "market share", "progress", "pricing", "점유율", "진척", "가격"))
        )
    if category == "hbm4e_validation":
        return "hbm4e" in low and any(k in low for k in ("samsung", "sk hynix", "sk하이닉스", "micron")) and any(k in low for k in ("qualification", "validation", "sample", "mass production", "production", "yield", "수율", "양산", "검증", "샘플"))
    if category == "hbm4e_thermal_package":
        return (
            ("samsung" in low or "삼성전자" in low or "삼성" in low)
            and "hbm4e" in low
            and any(k in low for k in (
                "thermal", "heat", "cooling", "hcb", "hpb", "hybrid bonding",
                "interposer", "reticle", "package", "발열", "냉각", "열저항",
                "하이브리드 본딩", "하이브리드본딩", "인터포저", "패키지",
            ))
        )
    if category == "rubin_shipments":
        return ("rubin ultra" in low or "nvl576" in low) and any(k in low for k in ("shipment", "ship", "production", "deployment", "order", "ramp", "customer", "출하", "양산", "도입", "주문"))
    if category == "samsung_hbm4_price":
        return (
            ("samsung" in low or "삼성전자" in low or "삼성" in low)
            and "hbm4" in low
            and any(k in low for k in ("2027", "내년", "next year"))
            and any(k in low for k in ("price", "pricing", "contract", "negotiation", "annual supply", "가격", "공급가", "협상", "계약"))
        )
    if category == "hbm_2027_contract":
        return "2027" in low and "hbm" in low and any(k in low for k in ("contract", "price", "pricing", "lta", "supply", "allocation", "volume", "agreement", "negotiation", "계약", "가격", "공급", "물량", "협상", "타결"))
    if category == "citi_hbm_outlook":
        return (
            ("citi" in low or "citigroup" in low or "씨티" in low or "花旗" in text)
            and "hbm" in low
            and any(k in low for k in ("2027", "2028"))
            and any(k in low for k in ("demand", "supply", "deficit", "shortage", "wafer", "wpm", "12-hi", "12hi", "8-hi", "8hi", "수요", "공급", "부족", "웨이퍼"))
        )
    if category == "hbm_wafer_economics":
        return "hbm" in low and "ddr5" in low and any(k in low for k in ("wafer revenue", "profitability", "economics", "64gb rdimm", "웨이퍼 매출", "수익성", "채산성"))
    if category == "memory_migration":
        return any(k in low for k in ("rubin", "hbm")) and any(k in low for k in ("ddr5", "socamm2", "essd", "enterprise ssd", "kv cache", "offload", "pooling", "오프로드", "풀링"))
    return False


def source_quality(source: str) -> str:
    low = (source or "").lower().strip()
    if any(k in low for k in OFFICIAL_SOURCE_HINTS):
        return "공식·회사자료"
    if any(k in low for k in TRUSTED_SOURCE_HINTS):
        return "신뢰 리서치·보도"
    return "일반 보도"


def quality_rank(value: str) -> int:
    if value.startswith("공식"):
        return 4
    if "Reuters" in value or value.startswith("신뢰"):
        return 3
    if value.startswith("교차검증"):
        return 2
    return 1


def normalized_title(title: str) -> str:
    value = clean_text(title).lower()
    if " - " in value:
        value = value.rsplit(" - ", 1)[0]
    value = re.sub(r"[^a-z0-9가-힣]+", " ", value)
    return re.sub(r"\s+", " ", value).strip()


def event_id(category: str, title: str, link: str) -> str:
    raw = f"{category}|{title}|{link}".encode("utf-8")
    return hashlib.sha256(raw).hexdigest()[:24]


def is_fresh_for_send(event: dict, now: datetime) -> bool:
    raw = event.get("published_at_kst") or ""
    if not raw:
        return False
    try:
        dt = datetime.fromisoformat(raw)
    except Exception:
        return False
    return now - timedelta(hours=SEND_FRESHNESS_HOURS) <= dt <= now + timedelta(minutes=10)


def read_feed(category: str, query: str, lang: str) -> tuple[list[dict], list[str]]:
    errors: list[str] = []
    out: list[dict] = []
    url = rss_url(query, lang)
    try:
        root = ET.fromstring(fetch(url))
        for item in root.findall("./channel/item"):
            title = clean_text(item.findtext("title") or "")
            link = clean_text(item.findtext("link") or "")
            desc = clean_text(item.findtext("description") or "")
            pub = clean_text(item.findtext("pubDate") or "")
            source_node = item.find("source")
            source = clean_text(source_node.text if source_node is not None and source_node.text else "")
            text = f"{title} {desc}"
            if not title or not link or not relevant(category, text):
                continue
            dt = parse_pubdate(pub)
            out.append({
                "id": event_id(category, title, link),
                "category": category,
                "title": title,
                "link": link,
                "source": source or "출처 미표시",
                "published_at_kst": dt.isoformat(timespec="seconds") if dt else "",
                "description": desc[:900],
                "quality": source_quality(source),
                "lang": lang,
            })
    except Exception as e:
        errors.append(f"{category}/{lang}: {type(e).__name__}: {e}")
    return out, errors


def decode_google_news_url(link: str) -> str:
    if "news.google.com" not in (link or ""):
        return link
    if gnewsdecoder is None:
        return ""
    try:
        result = gnewsdecoder(link, interval=0.2)
        if isinstance(result, dict) and result.get("status"):
            decoded = str(result.get("decoded_url") or "").strip()
            if decoded.startswith("http") and "news.google.com" not in decoded:
                return decoded
    except Exception:
        pass
    return ""


def meta_content(raw_html: str, key: str) -> str:
    patterns = [
        rf'<meta[^>]+(?:property|name)=["\']{re.escape(key)}["\'][^>]+content=["\']([^"\']+)["\']',
        rf'<meta[^>]+content=["\']([^"\']+)["\'][^>]+(?:property|name)=["\']{re.escape(key)}["\']',
    ]
    for pattern in patterns:
        m = re.search(pattern, raw_html, re.I)
        if m:
            return clean_text(m.group(1))
    return ""


def article_text_from_html(raw_html: str) -> str:
    value = re.sub(r"<(script|style|svg|noscript)[^>]*>.*?</\1>", " ", raw_html, flags=re.I | re.S)
    value = re.sub(r"<!--.*?-->", " ", value, flags=re.S)
    value = clean_text(value)
    return value[:16000]


def enrich_event(event: dict) -> dict:
    e = dict(event)
    direct = decode_google_news_url(e.get("link") or "")
    e["direct_link"] = direct
    e["link_verified"] = bool(direct)
    e["article_title"] = e.get("title") or ""
    e["article_description"] = e.get("description") or ""
    e["article_text"] = ""
    e["origin_source"] = e.get("source") or "출처 미표시"

    if not direct:
        return e

    try:
        raw = fetch(direct, timeout=18).decode("utf-8", errors="ignore")
        og_title = meta_content(raw, "og:title") or meta_content(raw, "twitter:title")
        desc = meta_content(raw, "og:description") or meta_content(raw, "description")
        body = article_text_from_html(raw)
        if og_title:
            e["article_title"] = og_title
        if desc:
            e["article_description"] = desc
        e["article_text"] = body

        source_low = (e.get("source") or "").lower()
        direct_host = (urlparse(direct).hostname or "").lower()
        body_low = body.lower()
        if "reuters" in body_low and "reuters" not in source_low:
            republisher = e.get("source") or direct_host
            e["origin_source"] = f"Reuters (재전재: {republisher})"
            e["quality"] = "신뢰 리서치·보도"
        elif "thelec" in direct_host:
            e["origin_source"] = "THE ELEC"
            e["quality"] = "신뢰 리서치·보도"
        elif "news.skhynix.com" in direct_host or "skhynix.com" in direct_host:
            e["origin_source"] = "SK하이닉스 공식자료"
            e["quality"] = "공식·회사자료"
    except Exception as ex:
        e["enrich_error"] = f"{type(ex).__name__}: {ex}"
    return e


def compact_fact_text(event: dict) -> str:
    return " ".join(
        x for x in (
            event.get("title") or "",
            event.get("description") or "",
            event.get("article_title") or "",
            event.get("article_description") or "",
            event.get("article_text") or "",
        ) if x
    )


def pct_tokens(text: str) -> list[str]:
    return list(dict.fromkeys(re.findall(r"[+-]?\d+(?:\.\d+)?%", text)))


def money_tokens(text: str) -> list[str]:
    return list(dict.fromkeys(re.findall(r"\$\s*\d+(?:\.\d+)?\s*(?:billion|million|B|M)\b", text, re.I)))



def _bernstein_rubin_model_values(text: str) -> tuple[int | None, int | None, int | None, int | None]:
    low = clean_text(text).lower().replace(",", "")
    old_gb = new_gb = None
    patterns = (
        r"(?:from|기존|종전|由)\s*(\d{3,4})\s*gb[^.]{0,90}?(?:to|에서|→|하향|下调至|降至)\s*(\d{3,4})\s*gb",
        r"(\d{3,4})\s*gb\s*(?:→|->|에서)\s*(\d{3,4})\s*gb",
    )
    for pat in patterns:
        m = re.search(pat, low, re.I)
        if m:
            old_gb, new_gb = int(m.group(1)), int(m.group(2))
            break
    if old_gb is None and "1024gb" in low and "640gb" in low:
        old_gb, new_gb = 1024, 640

    share_8 = share_12 = None
    has_8 = any(k in low for k in ("8-hi", "8hi", "8-layer", "8 layer", "8단", "8层"))
    has_12 = any(k in low for k in ("12-hi", "12hi", "12-layer", "12 layer", "12단", "12层"))
    half_split = any(k in low for k in ("half", "50%", "50 percent", "절반", "一半"))
    if has_8 and has_12 and half_split:
        share_8 = share_12 = 50
    return old_gb, new_gb, share_8, share_12


def _bernstein_supplier_relative_signature(text: str) -> str:
    low = clean_text(text).lower()
    if not (("bernstein" in low or "伯恩斯坦" in text) and "hbm" in low and "samsung" in low):
        return ""
    if not any(k in low for k in ("sk hynix", "sk하이닉스")):
        return ""
    samsung_up = any(k in low for k in ("gaining hbm share", "gain share", "share gain", "점유율 확대", "점유율 상승"))
    sk_down = (
        ("sk hynix" in low or "sk하이닉스" in low)
        and any(k in low for k in ("more conservative", "conservative assumptions", "progress and pricing", "진척", "가격 가정 하향", "목표주가 하향"))
    )
    if samsung_up and sk_down:
        return "bernstein_hbm_supplier_relative_samsung_up_skhynix_down"
    if samsung_up:
        return "bernstein_hbm_supplier_relative_samsung_up"
    if sk_down:
        return "bernstein_hbm_supplier_relative_skhynix_down"
    return ""



def _citi_pct(text: str, year: int, words: tuple[str, ...]) -> float | None:
    low = clean_text(text).lower()
    word = "(?:" + "|".join(re.escape(x.lower()) for x in words) + ")"
    for pat in (
        rf"{year}[^.%]{{0,140}}?{word}[^.%]{{0,120}}?([+-]?\d{{1,3}}(?:\.\d+)?)\s*%",
        rf"{word}[^.%]{{0,120}}?{year}[^.%]{{0,120}}?([+-]?\d{{1,3}}(?:\.\d+)?)\s*%",
    ):
        m = re.search(pat, low, re.I)
        if m:
            return float(m.group(1))
    return None


def _citi_100m_gb(text: str, year: int, words: tuple[str, ...]) -> float | None:
    low = clean_text(text).lower().replace(",", "")
    word = "(?:" + "|".join(re.escape(x.lower()) for x in words) + ")"
    for pat in (
        rf"{year}[^.]{{0,180}}?{word}[^.]{{0,160}}?(\d+(?:\.\d+)?)\s*(?:억|億)\s*gb",
        rf"{word}[^.]{{0,160}}?{year}[^.]{{0,160}}?(\d+(?:\.\d+)?)\s*(?:억|億)\s*gb",
    ):
        m = re.search(pat, low, re.I)
        if m:
            return float(m.group(1))
    for pat in (
        rf"{year}[^.]{{0,180}}?{word}[^.]{{0,160}}?(\d+(?:\.\d+)?)\s*billion\s*gb",
        rf"{word}[^.]{{0,160}}?{year}[^.]{{0,160}}?(\d+(?:\.\d+)?)\s*billion\s*gb",
    ):
        m = re.search(pat, low, re.I)
        if m:
            return float(m.group(1)) * 10.0
    return None


def _citi_wpm(text: str, aliases: tuple[str, ...]) -> float | None:
    low = clean_text(text).lower().replace(",", "")
    alias = "(?:" + "|".join(re.escape(x.lower()) for x in aliases) + ")"
    for pat in (
        rf"{alias}[^.]{{0,140}}?(\d+(?:\.\d+)?)\s*만\s*(?:장|wafers?)",
        rf"{alias}[^.]{{0,140}}?(\d+(?:\.\d+)?)\s*(?:k|thousand)\s*(?:wafers?)",
        rf"{alias}[^.]{{0,140}}?(\d{{5,6}})\s*(?:wpm|wafers?\s*per\s*month|wafers?/month)",
    ):
        m = re.search(pat, low, re.I)
        if m:
            value = float(m.group(1))
            if "만" in m.group(0):
                return value * 10000.0
            if re.search(r"(?:k|thousand)", m.group(0), re.I):
                return value * 1000.0
            return value
    return None


def extract_citi_hbm_outlook(event: dict) -> dict | None:
    text = compact_fact_text(event)
    low = text.lower()
    if not relevant("citi_hbm_outlook", text):
        return None
    obs: dict = {}
    for year in (2027, 2028):
        obs[f"demand_{year}_yoy_pct"] = _citi_pct(text, year, ("demand", "수요", "需求"))
        obs[f"supply_{year}_yoy_pct"] = _citi_pct(text, year, ("supply", "공급", "供給", "供应"))
        obs[f"deficit_{year}_pct"] = _citi_pct(text, year, ("deficit", "shortage", "공급부족률", "공급 부족률", "缺口", "短缺"))
        obs[f"demand_{year}_100m_gb"] = _citi_100m_gb(text, year, ("demand", "수요", "需求"))
        obs[f"supply_{year}_100m_gb"] = _citi_100m_gb(text, year, ("supply", "공급", "供給", "供应"))
    obs["samsung_2027_wpm"] = _citi_wpm(text, ("samsung", "삼성전자", "삼성"))
    obs["skhynix_2027_wpm"] = _citi_wpm(text, ("sk hynix", "sk하이닉스", "하이닉스"))
    obs["micron_2027_wpm"] = _citi_wpm(text, ("micron", "마이크론"))
    for field, aliases in (
        ("samsung_2027_capacity_yoy_pct", ("samsung", "삼성전자", "삼성")),
        ("skhynix_2027_capacity_yoy_pct", ("sk hynix", "sk하이닉스", "하이닉스")),
        ("micron_2027_capacity_yoy_pct", ("micron", "마이크론")),
    ):
        alias = "(?:" + "|".join(re.escape(x.lower()) for x in aliases) + ")"
        m = re.search(rf"{alias}[^.%]{{0,120}}?2027[^.%]{{0,120}}?([+-]?\d{{1,3}}(?:\.\d+)?)\s*%", low, re.I)
        if not m:
            m = re.search(rf"{alias}[^.%]{{0,160}}?([+-]?\d{{1,3}}(?:\.\d+)?)\s*%[^.]{{0,80}}?(?:2027|yoy)", low, re.I)
        obs[field] = float(m.group(1)) if m else None
    price = re.search(
        r"(?:hbm4[^.]{0,80}?12\s*[- ]?(?:hi|단)|12\s*[- ]?(?:hi|단)[^.]{0,80}?hbm4)[^$\d]{0,80}?\$?\s*(\d+(?:\.\d+)?)\s*(?:~|[-–—]|to)\s*\$?\s*(\d+(?:\.\d+)?)\s*/?\s*gb",
        low, re.I,
    )
    if price:
        obs["hbm4_12hi_usd_per_gb_min"] = float(price.group(1))
        obs["hbm4_12hi_usd_per_gb_max"] = float(price.group(2))
    price_yoy = re.search(
        r"(?:hbm4[^.]{0,100}?12\s*[- ]?(?:hi|단)|12\s*[- ]?(?:hi|단)[^.]{0,100}?hbm4)[^%]{0,180}?(\d{2,3})\s*(?:~|[-–—]|to)\s*(\d{2,3})\s*%",
        low, re.I,
    )
    if price_yoy:
        obs["hbm4_12hi_price_yoy_min_pct"] = float(price_yoy.group(1))
        obs["hbm4_12hi_price_yoy_max_pct"] = float(price_yoy.group(2))
    premium = re.search(
        r"8\s*[- ]?(?:hi|단)[^.]{0,160}?12\s*[- ]?(?:hi|단)[^.]{0,160}?(\d{1,2})\s*(?:~|[-–—]|to)\s*(\d{1,2})\s*%[^.]{0,80}?(?:higher|premium|높|비싸)",
        low, re.I,
    )
    if premium:
        obs["eight_hi_premium_min_pct"] = float(premium.group(1))
        obs["eight_hi_premium_max_pct"] = float(premium.group(2))
    if not any(v is not None for v in obs.values()):
        return None
    obs.update({
        "source": event.get("origin_source") or event.get("source") or "Citi 관련 보도",
        "source_url": event.get("direct_link") or event.get("link") or "",
        "as_of": (event.get("published_at_kst") or "")[:10],
        "observed_at": event.get("published_at_kst") or "",
    })
    return obs


def merge_citi_hbm_outlook(old: dict, obs: dict) -> dict:
    if old.get("as_of") and obs.get("as_of") and obs["as_of"] < old["as_of"]:
        return dict(old)
    merged = dict(old or {})
    for key, value in obs.items():
        if value is not None and value != "":
            merged[key] = value
    return merged


def citi_hbm_material_changes(old: dict, new: dict) -> list[str]:
    changes: list[str] = []
    for year in (2027, 2028):
        for kind, label in (("demand", "수요 증가율"), ("supply", "공급 증가율")):
            key = f"{kind}_{year}_yoy_pct"
            a, b = old.get(key), new.get(key)
            if a is not None and b is not None and abs(float(b) - float(a)) >= 10:
                changes.append(f"{year}년 {label} {float(a):+.0f}%→{float(b):+.0f}% ({float(b)-float(a):+.0f}%p)")
        key = f"deficit_{year}_pct"
        a, b = old.get(key), new.get(key)
        if a is not None and b is not None and abs(float(b) - float(a)) >= 5:
            changes.append(f"{year}년 수급 부족률 {float(a):+.0f}%→{float(b):+.0f}% ({float(b)-float(a):+.0f}%p)")
        for kind, label in (("demand", "수요"), ("supply", "공급")):
            key = f"{kind}_{year}_100m_gb"
            a, b = old.get(key), new.get(key)
            if a and b and abs(float(b) / float(a) - 1.0) >= 0.10:
                changes.append(f"{year}년 {label} {float(a):,.0f}억→{float(b):,.0f}억 Gb")
    for key, label in (
        ("samsung_2027_wpm", "삼성전자"),
        ("skhynix_2027_wpm", "SK하이닉스"),
        ("micron_2027_wpm", "Micron"),
    ):
        a, b = old.get(key), new.get(key)
        if a and b and abs(float(b) / float(a) - 1.0) >= 0.10:
            changes.append(f"{label} 2027 월 웨이퍼 생산능력 {float(a):,.0f}→{float(b):,.0f}장")
    for key, label in (
        ("samsung_2027_capacity_yoy_pct", "삼성전자 생산능력 증가율"),
        ("skhynix_2027_capacity_yoy_pct", "SK하이닉스 생산능력 증가율"),
        ("micron_2027_capacity_yoy_pct", "Micron 생산능력 증가율"),
        ("hbm4_12hi_price_yoy_min_pct", "HBM4 12단 가격 상승률 하단"),
        ("hbm4_12hi_price_yoy_max_pct", "HBM4 12단 가격 상승률 상단"),
    ):
        a, b = old.get(key), new.get(key)
        if a is not None and b is not None and abs(float(b) - float(a)) >= 10:
            changes.append(f"{label} {float(a):.0f}%→{float(b):.0f}%")
    for key, label in (
        ("hbm4_12hi_usd_per_gb_min", "HBM4 12단 가격 하단"),
        ("hbm4_12hi_usd_per_gb_max", "HBM4 12단 가격 상단"),
    ):
        a, b = old.get(key), new.get(key)
        if a is not None and b is not None and abs(float(b) - float(a)) >= 0.5:
            changes.append(f"{label} {float(a):.1f}→{float(b):.1f}달러/Gb")
    for key, label in (
        ("eight_hi_premium_min_pct", "8단 프리미엄 하단"),
        ("eight_hi_premium_max_pct", "8단 프리미엄 상단"),
    ):
        a, b = old.get(key), new.get(key)
        if a is not None and b is not None and abs(float(b) - float(a)) >= 5:
            changes.append(f"{label} {float(a):.0f}%→{float(b):.0f}%")
    return changes


def citi_hbm_change_event(state: dict, changes: list[str]) -> dict:
    bullets = [
        f"• 수요: 2027년 +{state.get('demand_2027_yoy_pct', 0):.0f}% · {state.get('demand_2027_100m_gb', 0):,.0f}억 Gb / 2028년 +{state.get('demand_2028_yoy_pct', 0):.0f}% · {state.get('demand_2028_100m_gb', 0):,.0f}억 Gb",
        f"• 공급: 2027년 +{state.get('supply_2027_yoy_pct', 0):.0f}% · {state.get('supply_2027_100m_gb', 0):,.0f}억 Gb / 2028년 +{state.get('supply_2028_yoy_pct', 0):.0f}% · {state.get('supply_2028_100m_gb', 0):,.0f}억 Gb",
        f"• 수급 부족률: 2027년 {state.get('deficit_2027_pct', 0):+.0f}% → 2028년 {state.get('deficit_2028_pct', 0):+.0f}%",
        f"• 2027 월 웨이퍼 생산능력: 삼성전자 {state.get('samsung_2027_wpm', 0):,.0f}장(+{state.get('samsung_2027_capacity_yoy_pct', 0):.0f}%) / SK하이닉스 {state.get('skhynix_2027_wpm', 0):,.0f}장(+{state.get('skhynix_2027_capacity_yoy_pct', 0):.0f}%) / Micron {state.get('micron_2027_wpm', 0):,.0f}장(+{state.get('micron_2027_capacity_yoy_pct', 0):.0f}%)",
        f"• 8단 Gb당 프리미엄: 12단 대비 +{state.get('eight_hi_premium_min_pct', 0):.0f}~{state.get('eight_hi_premium_max_pct', 0):.0f}%",
        "• 이번 변화: " + " · ".join(changes),
    ]
    return {
        "id": "typed|citi_hbm_outlook",
        "category": "citi_hbm_outlook",
        "headline_ko": "Citi HBM 수급·가격 전망 상태 변화",
        "fact_bullets": bullets,
        "verdict": "Citi 전망은 TrendForce 시장 Blended ASP와 별도 관리합니다. 수요·공급·가격·생산능력의 실제 수정만 재알림합니다.",
        "verification": "Citi 리서치 재인용 상태값",
        "origin_source": state.get("source") or "Citi",
        "source": state.get("source") or "Citi",
        "published_at_kst": state.get("observed_at") or state.get("as_of") or "",
        "direct_link": state.get("source_url") or "",
        "article_text": "",
        "citi_state": state,
    }

SAMSUNG_HBM4_STAGE_RANK = {
    "reported_offer": 0,
    "negotiation": 1,
    "final_stage": 2,
    "signed": 3,
}


def _relative_month_from_event(event: dict) -> str:
    stamp = event.get("published_at_kst") or ""
    try:
        dt = datetime.fromisoformat(stamp)
        return f"{dt.year:04d}-{dt.month:02d}"
    except Exception:
        return ""


def extract_samsung_hbm4_price(event: dict) -> dict | None:
    text = compact_fact_text(event)
    low = text.lower()
    if not relevant("samsung_hbm4_price", text):
        return None

    obs: dict = {}
    if any(k in low for k in ("계약 체결", "가격 확정", "협상 타결", "contract signed", "price finalized", "pricing finalized", "negotiations concluded")):
        obs["stage"] = "signed"
    else:
        future_final = bool(re.search(
            r"(?:마무리\s*수순|final\s+stages|nearing\s+completion|close\s+to\s+finalizing)"
            r"[^.]{0,50}?(?:전망|예상|것으로|expected|likely|planned)"
            r"|(?:전망|예상|것으로|expected|likely|planned)[^.]{0,50}?"
            r"(?:마무리\s*수순|final\s+stages|nearing\s+completion|close\s+to\s+finalizing)",
            low, re.I
        ))
        if any(k in low for k in ("마무리 수순", "final stages", "nearing completion", "close to finalizing")) and not future_final:
            obs["stage"] = "final_stage"
        elif any(k in low for k in ("협상", "negotiation", "negotiating")):
            obs["stage"] = "negotiation"
        elif any(k in low for k in ("제시", "offered", "quoted")):
            obs["stage"] = "reported_offer"
        else:
            return None
    # Exact range only when the article gives explicit endpoints.
    pm = re.search(
        r"(?:hbm4[^.]{0,120}?)(?:\$|미화\s*)?([0-9]+(?:\.[0-9]+)?)\s*(?:~|[-–—]|to)\s*(?:\$|미화\s*)?([0-9]+(?:\.[0-9]+)?)\s*(?:/\s*)?gb",
        low, re.I,
    )
    if pm:
        obs["offered_price_usd_per_gb_min"] = float(pm.group(1))
        obs["offered_price_usd_per_gb_max"] = float(pm.group(2))

    if re.search(r"4\s*달러대\s*중후반|mid[- ]?to[- ]?high\s*\$?4", text, re.I):
        obs["offered_price_band"] = "mid_to_high_4_usd_per_gb"

    ref = re.search(r"(?:hbm3e)[^.]{0,100}?([0-9]+(?:\.[0-9]+)?)\s*(?:달러|\$)[^.]{0,30}?(?:/\s*)?gb", low, re.I)
    if not ref:
        ref = re.search(r"(?:hbm3e)[^.]{0,100}?(?:gb당|per\s+gb)[^0-9]{0,30}?([0-9]+(?:\.[0-9]+)?)\s*(?:달러|\$)", low, re.I)
    if ref:
        obs["reference_hbm3e_usd_per_gb"] = float(ref.group(1))

    mult = re.search(r"([0-9]+(?:\.[0-9]+)?)\s*배\s*이상|(?:more\s+than|over|at\s+least)\s*([0-9]+(?:\.[0-9]+)?)\s*(?:times|x)", text, re.I)
    if mult:
        obs["price_multiple_floor"] = float(mult.group(1) or mult.group(2))

    if any(k in low for k in ("물량이 상당 부분", "물량 상당 부분", "substantial portion of volume", "most volume")) and any(k in low for k in ("협의가 끝", "agreed", "settled")):
        obs["volume_stage"] = "largely_agreed"
    elif any(k in low for k in ("물량 확정", "volume finalized", "volume contracted")):
        obs["volume_stage"] = "finalized"

    if any(k in low for k in ("이달 중", "this month")) and any(k in low for k in ("마무리", "finaliz", "conclud")):
        obs["target_close_month"] = _relative_month_from_event(event)

    if not any(k in obs for k in ("offered_price_band", "offered_price_usd_per_gb_min", "price_multiple_floor", "stage")):
        return None
    obs.update({
        "source": event.get("origin_source") or event.get("source") or "",
        "source_url": event.get("direct_link") or "",
        "observed_at": event.get("published_at_kst") or "",
    })
    return obs


def merge_samsung_hbm4_price(old: dict, obs: dict) -> dict:
    out = dict(old or {})
    for key, value in obs.items():
        if value not in (None, ""):
            out[key] = value
    return out


def samsung_hbm4_price_changes(old: dict, new: dict) -> list[str]:
    reasons: list[str] = []
    old_stage, new_stage = old.get("stage"), new.get("stage")
    if old_stage != new_stage and new_stage:
        reasons.append(f"계약가격 단계 {old_stage or '미확인'}→{new_stage}")

    for field, label in (
        ("offered_price_usd_per_gb_min", "제시가격 하단"),
        ("offered_price_usd_per_gb_max", "제시가격 상단"),
    ):
        a, b = old.get(field), new.get(field)
        if a is not None and b is not None:
            pct = (float(b) / float(a) - 1.0) * 100 if float(a) else 0
            if abs(float(b)-float(a)) >= 0.20 or abs(pct) >= 5:
                reasons.append(f"{label} {float(a):.2f}→{float(b):.2f}달러/Gb")
        elif a is None and b is not None:
            reasons.append(f"{label} {float(b):.2f}달러/Gb 신규 확인")

    if old.get("offered_price_band") != new.get("offered_price_band") and new.get("offered_price_band"):
        reasons.append(f"제시가격 밴드 {old.get('offered_price_band') or '미확인'}→{new.get('offered_price_band')}")

    a, b = old.get("reference_hbm3e_usd_per_gb"), new.get("reference_hbm3e_usd_per_gb")
    if a is not None and b is not None and abs(float(b)-float(a)) >= 0.10:
        reasons.append(f"HBM3E 비교가격 {float(a):.2f}→{float(b):.2f}달러/Gb")

    a, b = old.get("price_multiple_floor"), new.get("price_multiple_floor")
    if a is not None and b is not None and abs(float(b)-float(a)) >= 0.25:
        reasons.append(f"HBM3E 대비 가격배수 하한 {float(a):.2f}배→{float(b):.2f}배")

    if old.get("volume_stage") != new.get("volume_stage") and new.get("volume_stage"):
        reasons.append(f"물량 협의 단계 {old.get('volume_stage') or '미확인'}→{new.get('volume_stage')}")
    if old.get("target_close_month") != new.get("target_close_month") and new.get("target_close_month"):
        reasons.append(f"가격협상 마무리 목표 {old.get('target_close_month') or '미확인'}→{new.get('target_close_month')}")
    return reasons


def samsung_hbm4_price_event(state: dict, reasons: list[str]) -> dict:
    return {
        "category": "samsung_hbm4_price",
        "fact_key": "samsung_hbm4_price_" + (state.get("stage") or "state") + "_" + (state.get("observed_at") or state.get("as_of") or ""),
        "headline_ko": "삼성전자 2027 HBM4 계약가격 변화",
        "fact_bullets": reasons,
        "verdict": "🟢 계약 체결·가격 확정이면 실제 2027 ASP에 직접 연결됩니다." if state.get("stage") == "signed" else "🟡 현재는 제시·협상 가격입니다. 고객과 확정된 체결가격으로 승격하지 않습니다.",
        "verification": "상태값 변화",
        "quality": "신뢰 리서치·보도",
        "origin_source": state.get("source") or "",
        "source": state.get("source") or "",
        "published_at_kst": state.get("observed_at") or state.get("as_of") or "",
        "direct_link": state.get("source_url") or "",
        "article_text": "",
        "samsung_hbm4_price_state": state,
    }


def extract_samsung_hbm4e_thermal_package(event: dict) -> dict | None:
    text = compact_fact_text(event)
    low = text.lower()
    if not relevant("hbm4e_thermal_package", text):
        return None

    obs: dict = {}

    current = re.search(
        r"(?:현재|current(?:ly)?)[^.]{0,100}?(?:interposer|인터포저)[^.]{0,100}?([0-9]+(?:\.[0-9]+)?)\s*(?:배|x|times)",
        text, re.I,
    )
    if not current:
        current = re.search(
            r"(?:interposer|인터포저)[^.]{0,100}?(?:현재|current(?:ly)?)[^.]{0,80}?([0-9]+(?:\.[0-9]+)?)\s*(?:배|x|times)",
            text, re.I,
        )
    if current:
        obs["industry_current_interposer_reticle_x"] = float(current.group(1))

    future = re.search(
        r"(?:interposer|인터포저)[^.]{0,180}?(?:까지|as\s+much\s+as|up\s+to)[^0-9]{0,20}?([0-9]+(?:\.[0-9]+)?)\s*(?:배|x|times)",
        text, re.I,
    )
    if not future:
        future = re.search(
            r"([0-9]+(?:\.[0-9]+)?)\s*(?:배|x|times)[^.]{0,80}?(?:interposer|인터포저)",
            text, re.I,
        )
    if future:
        obs["reported_future_interposer_reticle_x"] = float(future.group(1))
        if any(k in low for k in ("보인다", "전망", "예상", "looks set", "expected", "projected")):
            obs["reported_future_interposer_stage"] = "industry_projection"

    tm = re.search(
        r"(?:hbm4e)[^.]{0,160}?(?:열\s*저항|thermal\s+resistance)[^%]{0,80}?([0-9]+(?:\.[0-9]+)?)\s*%",
        text, re.I,
    )
    if tm:
        obs["hbm4e_thermal_resistance_improvement_pct"] = float(tm.group(1))

    hm = re.search(
        r"(?:hcb|hybrid\s+copper\s+bonding|하이브리드\s*구리\s*본딩)[^.]{0,180}?(?:열\s*저항|thermal\s+resistance)[^%]{0,80}?([0-9]+(?:\.[0-9]+)?)\s*%",
        text, re.I,
    )
    if hm:
        obs["hcb_thermal_resistance_improvement_pct"] = float(hm.group(1))

    if any(k in low for k in ("hcb", "hybrid copper bonding", "하이브리드 구리 본딩", "하이브리드 본딩")):
        if (
            "hbm4e" in low
            and any(k in low for k in ("양산 적용", "양산에 적용", "mass production adoption", "adopted for mass production"))
        ):
            obs["hcb_stage"] = "hbm4e_mass_production"
        elif (
            "hbm4e" in low
            and any(k in low for k in ("일부 사업화", "partial commercialization", "commercialization starting"))
        ):
            obs["hcb_stage"] = "hbm4e_partial_commercialization"
        elif any(k in low for k in ("customer sample", "샘플을 고객", "고객사에 보냈")):
            obs["hcb_stage"] = "customer_sample"
        elif any(k in low for k in ("gtc 2026", "소개했다", "showcase", "showcased", "공개했다")):
            obs["hcb_stage"] = "technology_showcase"

    if "hpb" in low or "heat path block" in low or "히트패스블록" in low:
        if (
            "hbm4e" in low
            and any(k in low for k in ("양산 적용", "양산에 적용", "mass production adoption", "adopted for mass production"))
        ):
            obs["hpb_stage"] = "hbm4e_mass_production"
        elif "hbm4e" in low and any(k in low for k in ("검증 중", "검증중", "validating", "validation")):
            obs["hpb_stage"] = "hbm4e_validation"
        if "hbm5" in low and any(k in low for k in ("적용 계획", "적용할 계획", "plans to adopt", "planned for")):
            obs["hpb_target_generation"] = "hbm5"

    package_system = (
        ("패키지" in text and ("시스템" in text or "server" in low))
        and ("냉각" in text or "cooling" in low)
    )
    if package_system:
        if any(k in low for k in ("도입했다", "도입한다", "adopted", "deployed", "in production")):
            obs["package_system_cooling_stage"] = "adopted"
        elif any(k in low for k in ("검토", "가능성", "consider", "under review", "possibility")):
            obs["package_system_cooling_stage"] = "reported_review"

    if not obs:
        return None
    obs.update({
        "source": event.get("origin_source") or event.get("source") or "",
        "source_url": event.get("direct_link") or "",
        "observed_at": event.get("published_at_kst") or "",
    })
    return obs


def merge_samsung_hbm4e_thermal_package(old: dict, obs: dict) -> dict:
    out = dict(old or {})
    for key, value in obs.items():
        if value not in (None, ""):
            out[key] = value
    return out


def samsung_hbm4e_thermal_changes(old: dict, new: dict) -> list[str]:
    reasons: list[str] = []

    for field, label, threshold in (
        ("industry_current_interposer_reticle_x", "현재 인터포저 면적", 0.5),
        ("reported_future_interposer_reticle_x", "장기 인터포저 전망", 2.0),
        ("hbm4e_thermal_resistance_improvement_pct", "HBM4E 열저항 개선", 2.0),
        ("hcb_thermal_resistance_improvement_pct", "HCB 열저항 개선", 2.0),
    ):
        a, b = old.get(field), new.get(field)
        if a is not None and b is not None and abs(float(b) - float(a)) >= threshold:
            suffix = "배" if "reticle" in field else "%p"
            reasons.append(f"{label} {float(a):g}→{float(b):g}{suffix}")
        elif a is None and b is not None:
            suffix = "배" if "reticle" in field else "%"
            reasons.append(f"{label} {float(b):g}{suffix} 신규 확인")

    for field, label in (
        ("hcb_stage", "HCB 단계"),
        ("hpb_stage", "HPB 단계"),
        ("hpb_target_generation", "HPB 목표 세대"),
        ("package_system_cooling_stage", "패키지·시스템 냉각 단계"),
    ):
        a, b = old.get(field), new.get(field)
        if a != b and b:
            reasons.append(f"{label} {a or '미확인'}→{b}")

    return reasons


def samsung_hbm4e_thermal_event(state: dict, reasons: list[str]) -> dict:
    advanced = any(
        state.get(k) in ("hbm4e_mass_production", "adopted")
        for k in ("hcb_stage", "hpb_stage", "package_system_cooling_stage")
    )
    return {
        "category": "hbm4e_thermal_package",
        "fact_key": "samsung_hbm4e_thermal_" + (state.get("observed_at") or state.get("as_of") or ""),
        "headline_ko": "삼성 HBM4E 발열·인터포저·패키징 병목 변화",
        "fact_bullets": reasons,
        "verdict": (
            "HBM4E 양산 열관리 수단의 실제 채택 단계가 올라갔습니다. 수율·신뢰성·고객 승인과 함께 확인해야 합니다."
            if advanced else
            "발열·패키징 구조의 상태 변화입니다. 장기 인터포저 전망과 실제 HBM4E 양산 적용을 분리해 봅니다."
        ),
        "verification": "상태값 변화",
        "quality": "공식자료·신뢰보도 교차",
        "origin_source": state.get("source") or "",
        "source": state.get("source") or "",
        "published_at_kst": state.get("observed_at") or state.get("as_of") or "",
        "direct_link": state.get("source_url") or "",
        "article_text": "",
        "hbm4e_thermal_state": state,
    }


def make_fact(event: dict) -> dict | None:
    e = dict(event)
    text = compact_fact_text(e)
    low = text.lower()
    cat = e.get("category") or ""
    bullets: list[str] = []
    headline = ""
    verdict = ""
    fact_key = ""

    if cat == "rubin_broker_model":
        old_gb, new_gb, share_8, share_12 = _bernstein_rubin_model_values(text)
        if old_gb is None or new_gb is None or old_gb <= 0 or new_gb <= 0:
            return None
        reduction_pct = (new_gb / old_gb - 1.0) * 100.0
        break_even = old_gb / new_gb - 1.0
        split = f"_8hi{share_8}_12hi{share_12}" if share_8 is not None and share_12 is not None else ""
        fact_key = f"bernstein_rubin_ultra_model_{old_gb}_to_{new_gb}{split}"
        headline = f"Bernstein Rubin Ultra HBM 모델 가정 {old_gb:,}GB→{new_gb:,}GB"
        bullets.append(f"• 증권사 모델 가정: 평균 HBM 용량을 {old_gb:,}GB→{new_gb:,}GB로 조정했습니다. NVIDIA 공식 최종 사양과 분리합니다.")
        bullets.append(f"• 변화율: {reduction_pct:.1f}% · 같은 HBM 비트 수요를 유지하려면 GPU 출하량이 약 +{break_even*100:.1f}% 필요합니다.")
        if share_8 is not None and share_12 is not None:
            bullets.append(f"• 적층 가정: 8단 {share_8}% / 12단 {share_12}%로 분리합니다.")
        if "server dram" in low or "conventional dram" in low:
            bullets.append("• 대체 경로: 줄어든 HBM 웨이퍼 여력이 conventional server DRAM으로 이동할 수 있다는 가정을 함께 확인합니다.")
        verdict = "🟡 HBM 비트 수요의 구조 변화 신호이지만 증권사 모델 가정입니다. NVIDIA 최종 사양·GPU 출하량·HBM4 고객 승인을 함께 확인합니다."

    elif cat == "hbm_supplier_relative":
        fact_key = _bernstein_supplier_relative_signature(text)
        if not fact_key:
            return None
        headline = "Bernstein HBM 공급사 상대가정 변화 — 삼성전자 점유율↑·SK하이닉스 진척/가격 가정↓"
        if "samsung" in low:
            bullets.append("• 삼성전자: Bernstein이 HBM 점유율 확대 방향을 반영했습니다.")
        if "sk hynix" in low or "sk하이닉스" in low:
            bullets.append("• SK하이닉스: HBM 진척·가격에 더 보수적인 가정을 반영한 신호입니다.")
        if "3.3 million" in low and "2.7 million" in low:
            bullets.append("• 목표주가 변화는 결과값으로만 기록하고, 알림 트리거는 HBM 점유율·진척·가격 가정 변화로 제한합니다.")
        verdict = "🟡 목표주가 변경만으로는 발송하지 않습니다. 공급사별 HBM 점유율·가격·고객 승인·양산 가정이 실제로 바뀐 경우에만 상태 변화로 봅니다."

    # SK hynix Indiana HBM4E: classify it correctly as a packaging/production-base event,
    # not as customer qualification.
    elif cat == "hbm4e_validation" and "hbm4e" in low and "indiana" in low and "2029" in low and ("sk hynix" in low or "sk hynix" in low.replace("-", " ")):
        fact_key = "skhynix_indiana_hbm4e_2029"
        headline = "SK하이닉스, 인디애나 HBM4E 첨단 패키징 양산을 2029년 3분기에 시작 계획"
        bullets.append("• 확인된 사실: 미국 인디애나 거점에서 차세대 HBM4E의 첨단 패키징·양산을 2029년 3분기부터 시작할 계획입니다.")
        if "cleanroom" in low and "2028" in low:
            bullets.append("• 일정: 클린룸은 2028년 하반기 가동을 목표로 합니다.")
        if "hundreds of thousands" in low and "wafer" in low:
            bullets.append("• 생산 규모: 장기적으로 연간 수십만 장 수준의 웨이퍼를 처리하는 생산능력을 목표로 제시했습니다.")
        if ("$4 billion" in low or "$4b" in low or "4 billion" in low) and "indiana" in low:
            bullets.append("• 투자: 인디애나 프로젝트는 40억달러 이상 규모입니다.")
        if "shortage" in low and "2030" in low:
            bullets.append("• 수요 신호: 곽노정 CEO는 메모리 공급 부족이 2030년 말까지 이어질 것으로 전망했습니다.")
        bullets.append("• 구분: 이 소식은 2027년 HBM4E 고객 인증 완료 뉴스가 아니라, 2029년 미국 후공정·첨단패키징 생산기지 일정입니다.")
        verdict = "🟢 중장기 HBM 공급 확대와 수요 강도를 확인하는 긍정 신호. 다만 단기 고객 인증 완료 신호로 해석하면 안 됩니다."

    elif cat == "hbm4e_validation" and "hbm4e" in low:
        company = ""
        if "sk hynix" in low or "sk하이닉스" in low:
            company = "SK하이닉스"
        elif "samsung" in low or "삼성전자" in low:
            company = "삼성전자"
        elif "micron" in low:
            company = "Micron"
        if not company:
            return None

        if any(k in low for k in ("qualification completed", "qualified", "validation completed", "certification completed", "인증 완료", "검증 완료")):
            fact_key = f"{company}_hbm4e_customer_validation"
            headline = f"{company}, HBM4E 고객 검증 완료 신호"
            bullets.append("• 확인된 사실: 기사에서 HBM4E 고객 검증·인증 완료를 명시했습니다.")
            verdict = "🟢 가장 중요한 강세 조건 중 하나인 고객 인증 완료에 해당합니다. 실제 양산 개시일과 계약물량을 다음으로 확인해야 합니다."
        elif any(k in low for k in ("yield", "수율")):
            ym = re.search(r"(?:yield|수율)[^%]{0,80}?([0-9]{1,3}(?:\.[0-9]+)?)\s*%", text, re.I)
            if not ym:
                ym = re.search(r"([0-9]{1,3}(?:\.[0-9]+)?)\s*%[^.]{0,80}?(?:yield|수율)", text, re.I)
            state = "개선" if any(k in low for k in ("improve", "improved", "ramp", "개선", "상승")) else "병목" if any(k in low for k in ("low yield", "bottleneck", "constraint", "낮은 수율", "병목", "제약")) else "변화"
            suffix = f"_{ym.group(1).replace('.','p')}pct" if ym else f"_{state}"
            fact_key = f"{company}_hbm4e_yield{suffix}"
            headline = f"{company}, HBM4E 수율 {state} 신호"
            if ym:
                bullets.append(f"• 수율: 기사에서 HBM4E 수율 {ym.group(1)}%가 제시됐습니다.")
            else:
                bullets.append(f"• 수율: 기사에서 HBM4E 수율 {state}가 명시됐습니다.")
            bullets.append("• 구분: 수율 변화는 고객 인증·양산 물량과 별도 상태로 추적합니다.")
            verdict = "🟡 수율이 개선되면 Rubin Ultra 공급 병목 완화 신호이고, 낮은 수율·병목이면 고객 승인과 양산 램프 지연 위험 신호입니다."
        elif any(k in low for k in ("mass production", "volume production", "양산")):
            year = next(iter(re.findall(r"20\d{2}", text)), "")
            q = ""
            if any(k in low for k in ("third quarter", "q3", "3분기")):
                q = " 3분기"
            elif any(k in low for k in ("second half", "h2", "하반기")):
                q = " 하반기"
            fact_key = f"{company}_hbm4e_mass_production_{year}_{q.strip()}"
            headline = f"{company}, HBM4E 양산 일정 구체화{(' — ' + year + q) if year else ''}"
            bullets.append(f"• 확인된 사실: HBM4E 양산 일정이 {year + q if year else '기사에서 구체화'}됐습니다.")
            verdict = "🟢 양산 일정 구체화는 긍정적이지만, 고객 인증 완료·실제 출하와는 별도로 확인합니다."
        elif any(k in low for k in ("sample", "samples", "샘플")):
            year = next(iter(re.findall(r"20\d{2}", text)), "")
            fact_key = f"{company}_hbm4e_sample_{year}"
            headline = f"{company}, HBM4E 샘플 공급 일정 확인"
            bullets.append("• 확인된 사실: HBM4E 샘플 공급·출하 단계에 관한 일정이 확인됐습니다.")
            verdict = "🟡 샘플 출하는 개발 진척 신호지만 고객 인증 완료나 매출 인식과 동일하지 않습니다."
        else:
            return None

    elif cat == "rubin_spec" and "rubin ultra" in low:
        capacities = [x for x in ("192GB", "288GB", "768GB", "1TB") if x.lower() in low]
        layers = []
        if "8-hi" in low or "8hi" in low or "8단" in low:
            layers.append("8hi")
        if "12-hi" in low or "12hi" in low or "12단" in low:
            layers.append("12hi")
        if not capacities and not layers:
            return None
        final_spec = any(k in low for k in ("final specification", "final spec", "finalized", "confirmed specification", "사양 확정", "최종 사양", "확정 사양"))
        stage = "final" if final_spec else "evaluation"
        key_bits = [stage] + [x.lower() for x in capacities] + layers
        fact_key = "rubin_ultra_spec_" + "_".join(key_bits)
        cap = "/".join(capacities)
        headline = f"Rubin Ultra HBM {'최종 사양 확정' if final_spec else '사양 변화 감지'}" + (f" — {cap}" if cap else "")
        if capacities:
            bullets.append(f"• 확인된 사양 후보: {cap}")
        bullets.append(f"• 단계: {'최종 사양 확정' if final_spec else '평가·검토 단계'}로 분리해 저장합니다.")
        if "8hi" in layers:
            bullets.append("• 적층 후보: 8단 HBM 구성이 언급됐습니다.")
        if "12hi" in layers:
            bullets.append("• 적층 후보: 12단 HBM 구성이 언급됐습니다.")
        bw = re.findall(r"\d+(?:\.\d+)?\s*TB/s", text, re.I)
        if bw:
            bullets.append(f"• 대역폭: {', '.join(dict.fromkeys(bw))}")
        if "192gb" in low:
            bullets.append(f"• 숫자: 288GB→192GB면 GPU당 HBM은 -33.3%, 총 비트 수요 상쇄에는 GPU 출하 +{BREAKEVEN_GPU_GROWTH*100:.0f}%가 필요합니다.")
            verdict = "🟡 192GB만으로 수요 붕괴 판정 금지. 최종 사양·대역폭·GPU 총출하를 함께 확인해야 합니다."
        elif final_spec:
            verdict = "🟢 Rubin Ultra 최종 HBM 적층·용량 사양이 확정된 신호입니다. 공급사 고객 승인과 양산 물량을 다음 단계로 확인합니다."
        else:
            verdict = "🟡 공급망 사양 정보입니다. NVIDIA 공식 확정 여부를 별도로 확인합니다."

    elif cat == "rubin_shipments" and ("rubin ultra" in low or "nvl576" in low):
        if not any(k in low for k in ("shipment", "ship", "deployment", "order", "production", "ramp", "출하", "도입", "주문", "양산")):
            return None
        fact_key = "rubin_ultra_nvl576_shipments_" + "_".join(re.findall(r"20\d{2}", text)[:1])
        headline = "Rubin Ultra·NVL576 출하·도입 변화 확인"
        bullets.append("• 확인된 사실: Rubin Ultra 또는 NVL576의 출하·도입·양산 일정 변화가 기사에서 명시됐습니다.")
        numbers = re.findall(r"\b\d{2,6}\s*(?:GPU|GPUs|대)\b", text, re.I)
        if numbers:
            bullets.append(f"• 물량 단서: {', '.join(dict.fromkeys(numbers))}")
        bullets.append(f"• 상쇄선: GPU당 HBM이 288GB→192GB로 줄면 전체 HBM 비트를 유지하려면 GPU 출하가 최소 +{BREAKEVEN_GPU_GROWTH*100:.0f}% 늘어야 합니다.")
        verdict = "🟢 실제 출하·고객 도입 확대면 HBM 총수요 판단에 직접 반영합니다. 단순 로드맵 재언급은 제외합니다."

    elif cat == "hbm_2027_contract" and "2027" in low and "hbm" in low:
        pcts = pct_tokens(text)
        has_price = any(k in low for k in ("price", "pricing", "asp", "가격", "판가"))
        has_volume = any(k in low for k in ("volume", "allocation", "supply", "contract", "lta", "agreement", "물량", "공급", "계약"))
        signed = any(k in low for k in ("contract signed", "agreement signed", "agreement finalized", "deal finalized", "negotiations concluded", "계약 체결", "협상 타결", "가격 확정", "계약 확정"))
        stalled = any(k in low for k in ("stalled", "unresolved", "deadlock", "협상 교착", "미타결", "협상 난항"))
        if not (has_price or has_volume or signed or stalled):
            return None
        if not pcts and not (signed or stalled):
            return None
        stage = "signed" if signed else "stalled" if stalled else "quoted"
        key_parts = [stage] + [p.replace("%", "pct") for p in pcts[:3]]
        fact_key = "hbm_2027_contract_" + "_".join(key_parts)
        suffix = f" — {' / '.join(pcts[:3])}" if pcts else ""
        headline = f"2027 HBM 계약가격·물량 변화 ({'체결·확정' if signed else '협상 교착' if stalled else '가격 제시'}){suffix}"
        if pcts and has_price:
            bullets.append(f"• 가격: 기사에서 2027년 HBM 가격·평균판매단가 관련 수치 {' / '.join(pcts[:3])}가 제시됐습니다.")
        if signed:
            bullets.append("• 계약 단계: 협상 전망이 아니라 계약 체결·가격 확정 단계로 올라갔습니다.")
        elif stalled:
            bullets.append("• 계약 단계: 2027년 공급·가격 협상이 아직 타결되지 않은 상태입니다.")
        if has_volume:
            bullets.append("• 물량: 계약물량·공급배정이 유지 또는 증가하는지 반드시 가격과 함께 판정합니다.")
        verdict = "🟢 가격 상승과 계약물량 유지·증가가 동시에 확인되면 강한 신호입니다." if signed else "🟡 협상 단계에서는 전망치와 실제 계약가격·물량을 분리합니다."

    elif cat == "hbm_wafer_economics" and "hbm" in low and "ddr5" in low:
        if not any(k in low for k in ("wafer revenue", "profitability", "economics", "64gb rdimm", "웨이퍼 매출", "수익성", "채산성")):
            return None
        hbm_below = any(k in low for k in ("overtaken by ddr5", "fell below", "lower than ddr5", "ddr5 overtook", "ddr5가 추월", "ddr5보다 낮"))
        hbm_above = any(k in low for k in ("hbm overtook", "hbm surpassed", "hbm higher than", "hbm이 추월", "hbm이 상회"))
        state = "hbm_below_ddr5" if hbm_below else "hbm_above_ddr5" if hbm_above else "economics_update"
        fact_key = "hbm_ddr5_wafer_economics_" + state
        headline = "HBM↔DDR5 웨이퍼 경제성 변화"
        if hbm_below:
            bullets.append("• 현재 방향: HBM의 웨이퍼당 매출·수익성이 DDR5 64GB RDIMM보다 낮아진 신호입니다.")
        elif hbm_above:
            bullets.append("• 현재 방향: HBM의 웨이퍼당 매출·수익성이 DDR5보다 다시 높아진 신호입니다.")
        else:
            bullets.append("• 현재 방향: HBM과 DDR5의 웨이퍼당 매출·수익성 비교가 새로 갱신됐습니다.")
        bullets.append("• 의미: 이 격차가 HBM 가격 협상과 DRAM 웨이퍼 배분의 경제적 기준이 됩니다.")
        verdict = "🟡 HBM 경제성이 DDR5보다 낮으면 HBM 가격 인상 압력·배분 제약이 커지고, 다시 상회하면 HBM 증산 유인이 개선됩니다."

    elif cat == "memory_migration":
        if (
            "kv cache" in low
            and any(k in low for k in ("offload", "offloading", "오프로드"))
            and "hbm" in low
            and any(k in low for k in (
                "capacity", "reduce", "reduction", "lower", "smaller",
                "용량", "축소", "하향", "줄", "8-hi", "8hi", "12-hi", "12hi", "4-hi", "4hi", "8단", "12단", "4단",
            ))
        ):
            stacks = []
            for label, aliases in (
                ("4단", ("4-hi", "4hi", "4단")),
                ("8단", ("8-hi", "8hi", "8단")),
                ("12단", ("12-hi", "12hi", "12단")),
            ):
                if any(a in low for a in aliases):
                    stacks.append(label)
            capacities = list(dict.fromkeys(re.findall(r"\b\d+(?:\.\d+)?\s*(?:GB|TB)\b", text, re.I)))[:4]
            mainstream = []
            niche = []
            if any(k in low for k in ("mainstream", "주류", "중심", "유지")):
                if "8단" in stacks:
                    mainstream.append("8hi")
                if "12단" in stacks:
                    mainstream.append("12hi")
            if any(k in low for k in ("niche", "limited", "제한", "니치")) and "4단" in stacks:
                niche.append("4hi")

            if mainstream or niche:
                key_parts = []
                if mainstream:
                    key_parts.append("mainstream_" + "_".join(mainstream))
                if niche:
                    key_parts.append("niche_" + "_".join(niche))
            else:
                key_parts = [x.replace("단", "hi") for x in stacks]
            key_parts += [re.sub(r"\s+", "", x).lower() for x in capacities]
            fact_key = "hbm_capacity_kv_offload_" + ("_".join(key_parts) if key_parts else "shift")
            headline = "HBM 용량 축소·KV 캐시 오프로딩 구조 변화"
            bullets.append("• 상태 변화: GPU 내부 HBM 용량을 줄이는 방향과 KV 캐시를 외부 메모리 계층으로 넘기는 오프로딩이 함께 거론됐습니다.")
            if stacks:
                bullets.append(f"• 적층 구성: {', '.join(stacks)} HBM 구성이 언급됐습니다.")
            if capacities:
                bullets.append(f"• 용량 단서: {', '.join(capacities)}")
            if any(k in low for k in ("cpu ram", "host memory", "cxl", "ssd pod", "enterprise ssd", "essd", "local ssd")):
                tiers = []
                for label, aliases in (
                    ("CPU 메모리", ("cpu ram", "host memory")),
                    ("CXL", ("cxl",)),
                    ("기업용 eSSD", ("enterprise ssd", "essd")),
                    ("SSD POD", ("ssd pod",)),
                    ("로컬 SSD", ("local ssd",)),
                ):
                    if any(a in low for a in aliases):
                        tiers.append(label)
                if tiers:
                    bullets.append(f"• 대체 계층: {', '.join(tiers)}로 KV 캐시 수요가 이동하는 신호입니다.")
            bullets.append("• 해석: HBM 용량 감소를 HBM 수요 감소로 바로 등치하지 않습니다. 대역폭 요구, GPU 출하량, CPU 메모리·CXL·eSSD 수요 이동을 함께 봅니다.")
            verdict = "🟡 HBM 비트 수요에는 역풍이 될 수 있지만, KV 캐시 오프로딩이 CPU 메모리·CXL·eSSD 수요를 키우는 구조적 이동 신호입니다."
        elif "hbm3e" in low and "ddr5" in low and ("3x" in low or "3 x" in low or "three times" in low or "3배" in low):
            fact_key = "hbm3e_wafer_capacity_3x_ddr5"
            headline = "Micron: HBM3E가 DDR5보다 웨이퍼 생산능력을 약 3배 더 소모"
            bullets.append("• 확인된 사실: HBM3E는 같은 비트 생산 기준으로 DDR5보다 웨이퍼 생산능력을 약 3배 더 소모한다는 설명입니다.")
            bullets.append("• 의미: HBM 세대가 올라갈수록 웨이퍼 투입 부담이 커져, 공급 확대 속도가 비트 수요 증가를 따라가기 어려울 수 있습니다.")
            verdict = "🟢 HBM 공급 제약과 가격결정력을 뒷받침하는 신호. 다만 DDR5·SOCAMM2·eSSD 수요 이동과는 별개의 공급효율 이슈입니다."
        elif "socamm2" in low and any(k in low for k in ("mass production", "shipment", "supply", "order", "양산", "출하", "공급", "주문")):
            fact_key = "socamm2_demand_supply_" + "_".join(re.findall(r"20\d{2}", text)[:1])
            headline = "SOCAMM2 공급·주문 변화 확인"
            bullets.append("• 확인된 사실: SOCAMM2의 양산·출하·공급 또는 주문 변화가 기사에서 명시됐습니다.")
            verdict = "🟢 HBM 밖으로 내려가는 대용량 메모리 계층 수요가 실제 주문으로 연결되는지 확인하는 긍정 신호입니다."
        elif any(k in low for k in ("enterprise ssd", "essd")) and any(k in low for k in ("demand", "order", "shipment", "supply", "수요", "주문", "출하", "공급")):
            fact_key = "enterprise_ssd_ai_demand_" + "_".join(re.findall(r"20\d{2}", text)[:1])
            headline = "기업용 eSSD AI 수요·주문 변화 확인"
            bullets.append("• 확인된 사실: 기업용 eSSD의 AI 관련 수요·주문·출하 변화가 기사에서 명시됐습니다.")
            verdict = "🟢 HBM 용량 보완 계층으로 기업용 SSD 수요가 실제 증가하는지 확인하는 신호입니다."
        else:
            return None
    else:
        return None

    e["fact_key"] = fact_key
    e["headline_ko"] = headline
    e["fact_bullets"] = bullets
    e["verdict"] = verdict
    return e


def fact_signature_from_raw(event: dict) -> str:
    text = f"{event.get('title','')} {event.get('description','')}".lower()
    cat = event.get("category") or ""
    if "hbm4e" in text and "indiana" in text and "2029" in text and "sk hynix" in text:
        return "skhynix_indiana_hbm4e_2029"
    if (
        "kv cache" in text
        and any(k in text for k in ("offload", "offloading", "오프로드"))
        and "hbm" in text
        and any(k in text for k in ("capacity", "reduce", "reduction", "용량", "축소", "하향", "8-hi", "8hi", "12-hi", "12hi", "4-hi", "4hi", "8단", "12단", "4단"))
    ):
        stacks = []
        for label, aliases in (
            ("4hi", ("4-hi", "4hi", "4단")),
            ("8hi", ("8-hi", "8hi", "8단")),
            ("12hi", ("12-hi", "12hi", "12단")),
        ):
            if any(a in text for a in aliases):
                stacks.append(label)
        mainstream = []
        niche = []
        if any(k in text for k in ("mainstream", "주류", "중심", "유지")):
            if "8hi" in stacks:
                mainstream.append("8hi")
            if "12hi" in stacks:
                mainstream.append("12hi")
        if any(k in text for k in ("niche", "limited", "제한", "니치")) and "4hi" in stacks:
            niche.append("4hi")
        if mainstream or niche:
            parts = []
            if mainstream:
                parts.append("mainstream_" + "_".join(mainstream))
            if niche:
                parts.append("niche_" + "_".join(niche))
            return "hbm_capacity_kv_offload_" + "_".join(parts)
        return "hbm_capacity_kv_offload_" + ("_".join(stacks) if stacks else "shift")
    if "hbm3e" in text and "ddr5" in text and ("3x" in text or "three times" in text or "3배" in text):
        return "hbm3e_wafer_capacity_3x_ddr5"
    if cat == "rubin_broker_model":
        old_gb, new_gb, share_8, share_12 = _bernstein_rubin_model_values(text)
        if old_gb is not None and new_gb is not None:
            split = f"_8hi{share_8}_12hi{share_12}" if share_8 is not None and share_12 is not None else ""
            return f"bernstein_rubin_ultra_model_{old_gb}_to_{new_gb}{split}"
    if cat == "hbm_supplier_relative":
        return _bernstein_supplier_relative_signature(text)
    if cat == "rubin_spec" and "rubin ultra" in text:
        caps = [x for x in ("192gb", "288gb", "768gb", "1tb") if x in text]
        if caps:
            return "rubin_ultra_spec_" + "_".join(caps)
    if cat == "hbm_2027_contract" and "2027" in text:
        pcts = re.findall(r"[+-]?\d+(?:\.\d+)?%", text)
        if pcts:
            return "hbm_2027_contract_" + "_".join(p.replace("%", "pct") for p in pcts[:3])
    return ""


def verification_for(event: dict, raw_events: list[dict]) -> str:
    quality = event.get("quality") or ""
    origin = event.get("origin_source") or ""
    if quality.startswith("공식"):
        return "공식자료 확인"
    if "Reuters" in origin:
        return "Reuters 원문/재전재 확인"
    if quality.startswith("신뢰"):
        return "신뢰 보도 확인"

    key = event.get("fact_key") or ""
    if not key:
        return ""
    sources = set()
    for raw in raw_events:
        if fact_signature_from_raw(raw) == key:
            sources.add((raw.get("source") or "").lower())
    sources.discard("")
    if len(sources) >= 2:
        return f"교차검증 {len(sources)}곳"
    return ""


def choose_verified_events(fresh_unseen: list[dict], raw_events: list[dict], seen_fact_keys: set[str]) -> tuple[list[dict], list[str]]:
    errors: list[str] = []
    candidates: list[dict] = []
    for raw in fresh_unseen:
        if raw.get("category") in ("citi_hbm_outlook", "samsung_hbm4_price", "hbm4e_thermal_package"):
            continue
        source_low = (raw.get("source") or "").lower()
        if any(k in source_low for k in LOW_VALUE_SOURCE_HINTS):
            # 저품질 집계 사이트는 단독 발송 금지. 같은 사실의 더 나은 출처가 있으면 그쪽을 사용한다.
            continue
        enriched = enrich_event(raw)
        if not enriched.get("link_verified"):
            errors.append(f"원문 URL 확인 실패: {raw.get('source')} | {raw.get('title')}")
            continue
        fact = make_fact(enriched)
        if not fact:
            errors.append(f"핵심 사실 자동추출 실패로 발송 제외: {raw.get('source')} | {raw.get('title')}")
            continue
        if fact.get("fact_key") in seen_fact_keys:
            continue
        verification = verification_for(fact, raw_events)
        if not verification:
            errors.append(f"교차검증 부족으로 발송 제외: {raw.get('source')} | {raw.get('title')}")
            continue
        fact["verification"] = verification
        candidates.append(fact)

    # 같은 사실이 여러 매체에 재전재된 경우 가장 좋은 출처 한 건만 남긴다.
    chosen: dict[str, dict] = {}
    for e in candidates:
        key = e.get("fact_key") or normalized_title(e.get("headline_ko") or e.get("title") or "")
        old = chosen.get(key)
        if old is None:
            chosen[key] = e
            continue
        if quality_rank(e.get("quality") or "") > quality_rank(old.get("quality") or ""):
            chosen[key] = e
        elif quality_rank(e.get("quality") or "") == quality_rank(old.get("quality") or "") and (e.get("published_at_kst") or "") > (old.get("published_at_kst") or ""):
            chosen[key] = e
    return sorted(chosen.values(), key=lambda x: x.get("published_at_kst") or ""), errors


def fetch_fx():
    from fx_api import daily_krw
    try:
        q = daily_krw()
        return {"rate": q.rate, "date": q.basis, "source": q.source, "error": ""}
    except RuntimeError as exc:
        return {"rate": None, "date": "", "source": "환율 API", "error": str(exc)}


def load_state() -> tuple[dict, bool]:
    if not DATA.exists():
        return {}, True
    try:
        return json.loads(DATA.read_text(encoding="utf-8")), False
    except Exception:
        return {}, True


def write_json(path: pathlib.Path, obj: dict) -> None:
    path.write_text(json.dumps(obj, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def fmt_krw_usd(value: float, rate: float | None) -> str:
    if rate is None:
        return "원화 환산 불가"
    won = value * rate
    return f"약 {won:,.0f}원"


def krw_large_usd(value: float, rate: float | None) -> str:
    if rate is None:
        return "원화 환산 불가"
    won = value * rate
    eok = int(round(won / 100_000_000))
    if eok >= 10000:
        jo, rem = divmod(eok, 10000)
        return f"약 {jo:,}조{rem:,}억원" if rem else f"약 {jo:,}조원"
    return f"약 {eok:,}억원"


def extract_price_notes(text: str, rate: float | None) -> list[str]:
    notes: list[str] = []
    seen: set[str] = set()
    for m in re.finditer(r"\$\s*([0-9]+(?:\.[0-9]+)?)\s*/\s*(GB|Gb)", text, re.I):
        usd = float(m.group(1))
        unit = m.group(2)
        key = f"{usd}/{unit}"
        if key not in seen:
            seen.add(key)
            notes.append(f"• 가격 환산: ${usd:g}/{unit} = {fmt_krw_usd(usd, rate)}/{unit}")
    for m in re.finditer(r"\$\s*([0-9]+(?:\.[0-9]+)?)\s*(billion|million|B|M)\b", text, re.I):
        suffix = m.group(2).lower()
        val = float(m.group(1)) * (1_000_000_000 if suffix in ("b", "billion") else 1_000_000)
        key = f"{val}usd"
        if key not in seen:
            seen.add(key)
            notes.append(f"• 금액 환산: {m.group(0)} = {krw_large_usd(val, rate)}")
    return notes


def build_alert(now: datetime, events: list[dict], fx: dict) -> str:
    rate = fx.get("rate")
    lines = [
        "🚨 Rubin/HBM 구조 변화 감시",
        "",
        f"조회시각: {now.strftime('%Y-%m-%d %H:%M:%S KST')}",
        f"신규 핵심 변화: {len(events)}건",
        f"기준선: 일반 Rubin 288GB HBM4 / 디스펙 상쇄선 GPU 출하 +{BREAKEVEN_GPU_GROWTH*100:.0f}%",
    ]
    if rate is not None:
        lines.append(f"원화 환산: 1달러={rate:,.2f}원 / 기준일 {fx.get('date') or '미표시'}")

    grouped: dict[str, list[dict]] = {}
    for e in events:
        grouped.setdefault(e["category"], []).append(e)

    n = 1
    for category in ("rubin_spec", "rubin_broker_model", "hbm_supplier_relative", "hbm4e_validation", "hbm4e_thermal_package", "rubin_shipments", "samsung_hbm4_price", "hbm_2027_contract", "citi_hbm_outlook", "hbm_wafer_economics", "memory_migration"):
        group = grouped.get(category) or []
        if not group:
            continue
        if category == "hbm4e_thermal_package" and n > 1:
            lines += ["", "<<<TELEGRAM_MESSAGE_BREAK>>>", "🚨 삼성 HBM4E 발열·패키징 병목 감시", ""]
        if category == "samsung_hbm4_price" and n > 1:
            lines += ["", "<<<TELEGRAM_MESSAGE_BREAK>>>", "🚨 삼성전자 2027 HBM4 계약가격 감시", ""]
        if category == "citi_hbm_outlook" and n > 1:
            lines += ["", "<<<TELEGRAM_MESSAGE_BREAK>>>", "🚨 Citi HBM 2027~2028 수급·가격 감시", ""]
        if category == "memory_migration" and n > 1:
            lines += ["", "<<<TELEGRAM_MESSAGE_BREAK>>>", "🚨 HBM 용량 축소→KV 캐시 외부 메모리 전환", ""]
        lines += ["", f"■ {CATEGORY_KO[category]}"]
        for e in group[:5]:
            full_text = compact_fact_text(e)
            lines += [
                f"{n}. {e['headline_ko']}",
                f"- 출처: {e.get('origin_source') or e.get('source')} / {e.get('verification')}",
                f"- 공개시각: {e.get('published_at_kst') or '확인 불가'}",
            ]
            lines.extend(e.get("fact_bullets") or [])
            if category == "samsung_hbm4_price" and e.get("samsung_hbm4_price_state"):
                ss = e["samsung_hbm4_price_state"]
                band = ss.get("offered_price_band")
                if band == "mid_to_high_4_usd_per_gb":
                    lines.append("• 삼성 제시가격: 1Gb당 4달러대 중후반(기사 표현 그대로, 임의 범위 환산 안 함)")
                lo, hi = ss.get("offered_price_usd_per_gb_min"), ss.get("offered_price_usd_per_gb_max")
                if lo is not None and hi is not None:
                    if rate is not None:
                        lines.append(f"• 확정 공개 숫자: {float(lo):.2f}~{float(hi):.2f}달러/Gb (약 {float(lo)*rate:,.0f}~{float(hi)*rate:,.0f}원/Gb)")
                    else:
                        lines.append(f"• 확정 공개 숫자: {float(lo):.2f}~{float(hi):.2f}달러/Gb")
                if ss.get("reference_hbm3e_usd_per_gb") is not None:
                    lines.append(f"• 비교 HBM3E: 약 {float(ss['reference_hbm3e_usd_per_gb']):.2f}달러/Gb")
                if ss.get("price_multiple_floor") is not None:
                    lines.append(f"• 가격배수: HBM3E 대비 {float(ss['price_multiple_floor']):.1f}배 이상")
                lines.append(f"• 계약 단계: {ss.get('stage') or '미확인'} · 물량 단계: {ss.get('volume_stage') or '미확인'}")
                if ss.get("target_close_month"):
                    lines.append(f"• 협상 마무리 목표: {ss['target_close_month']}")
                lines.append("• 구분: 제시가격·협상가격과 실제 체결가격을 절대 같은 값으로 취급하지 않습니다.")
            if category == "hbm4e_thermal_package" and e.get("hbm4e_thermal_state"):
                ts = e["hbm4e_thermal_state"]
                if ts.get("industry_current_interposer_reticle_x") is not None:
                    lines.append(f"• 현재 인터포저 면적: reticle 기준 약 {float(ts['industry_current_interposer_reticle_x']):g}배")
                if ts.get("reported_future_interposer_reticle_x") is not None:
                    lines.append(
                        f"• 장기 전망: 최대 {float(ts['reported_future_interposer_reticle_x']):g}배 "
                        f"({ts.get('reported_future_interposer_stage') or '단계 미확인'})"
                    )
                lines.append(
                    f"• HCB: {ts.get('hcb_stage') or '미확인'} · "
                    f"HPB: {ts.get('hpb_stage') or '미확인'} · "
                    f"패키지·시스템 냉각: {ts.get('package_system_cooling_stage') or '미확인'}"
                )
                lines.append("• 구분: 40배는 장기 업계 전망이며 삼성 HBM4E 확정 양산 로드맵으로 승격하지 않습니다.")
            if category == "citi_hbm_outlook" and e.get("citi_state"):
                cs = e["citi_state"]
                lo, hi = cs.get("hbm4_12hi_usd_per_gb_min"), cs.get("hbm4_12hi_usd_per_gb_max")
                if lo is not None and hi is not None:
                    if rate is not None:
                        lines.append(
                            f"• HBM4 12단 가격: {float(lo):g}~{float(hi):g}달러/Gb "
                            f"(약 {float(lo)*rate:,.0f}~{float(hi)*rate:,.0f}원/Gb)"
                        )
                    else:
                        lines.append(f"• HBM4 12단 가격: {float(lo):g}~{float(hi):g}달러/Gb (원화 환산 불가)")
                pymin, pymax = cs.get("hbm4_12hi_price_yoy_min_pct"), cs.get("hbm4_12hi_price_yoy_max_pct")
                if pymin is not None and pymax is not None:
                    lines.append(f"• HBM4 12단 가격 상승률 전망: +{float(pymin):.0f}~{float(pymax):.0f}% YoY")
            lines += extract_price_notes(full_text, rate)
            lines.append(f"• 판정: {e.get('verdict')}")
            lines.append(f"- 원문: {e.get('direct_link')}")
            n += 1

    lines += [
        "",
        "■ 자동 판정 원칙",
        "• 원문 URL을 직접 확인하지 못한 기사는 발송하지 않습니다.",
        "• 일반 매체 단독 보도는 발송하지 않고 공식자료·Reuters·신뢰 매체 또는 2곳 이상 교차검증이 있어야 발송합니다.",
        "• 기사 제목만 전달하지 않고, 원문에서 확인된 핵심 사실·일정·물량·금액·판정을 함께 적습니다.",
        "• 192GB 확정만으로 HBM 수요 붕괴로 판정하지 않습니다.",
        f"• GPU당 288→192GB(-33.3%)일 때 GPU 출하가 +{BREAKEVEN_GPU_GROWTH*100:.0f}% 이상이면 총 HBM 비트 수요는 상쇄 가능합니다.",
        f"• Bernstein의 {BERNSTEIN_RUBIN_PREVIOUS_GB:,}→{BERNSTEIN_RUBIN_CURRENT_GB:,}GB는 증권사 모델 가정으로 별도 관리하며, NVIDIA 공식 사양으로 승격하지 않습니다.",
    ]
    return "\n".join(lines).strip() + "\n"


def main() -> None:
    now = datetime.now(ZoneInfo("Asia/Seoul"))
    history_cutoff = now - timedelta(days=14)
    state, first_run = load_state()
    seen_before = set(state.get("seen_ids") or [])
    seen_fact_keys = set(state.get("seen_fact_keys") or [])
    if int(state.get("structure_baseline_version") or 0) < STRUCTURE_BASELINE_VERSION:
        seen_fact_keys.update(KNOWN_STRUCTURE_FACT_KEYS)
        state["structure_baseline_version"] = STRUCTURE_BASELINE_VERSION

    raw_events_by_id: dict[str, dict] = {}
    errors: list[str] = []
    for category, query in QUERIES:
        for lang in ("en", "ko"):
            events, errs = read_feed(category, query, lang)
            errors.extend(errs)
            for e in events:
                try:
                    dt = datetime.fromisoformat(e["published_at_kst"])
                    if dt < history_cutoff:
                        continue
                except Exception:
                    pass
                raw_events_by_id[e["id"]] = e

    raw_events = sorted(raw_events_by_id.values(), key=lambda x: x.get("published_at_kst") or "")
    current_ids = {e["id"] for e in raw_events}
    unseen_raw = [e for e in raw_events if e["id"] not in seen_before]
    fresh_unseen = [e for e in unseen_raw if is_fresh_for_send(e, now)]

    verified_events, verify_errors = choose_verified_events(fresh_unseen, raw_events, seen_fact_keys)
    errors.extend(verify_errors)

    samsung_price_state = dict(state.get("samsung_hbm4_price") or {})
    samsung_price_track_version = int(state.get("samsung_hbm4_price_track_version") or 0)
    if samsung_price_track_version < SAMSUNG_HBM4_PRICE_TRACK_VERSION:
        seeded = dict(SAMSUNG_HBM4_PRICE_BASELINE)
        seeded.update({k: v for k, v in samsung_price_state.items() if v not in (None, "")})
        samsung_price_state = seeded
        samsung_price_track_version = SAMSUNG_HBM4_PRICE_TRACK_VERSION

    samsung_price_changes: list[str] = []
    for raw in raw_events:
        if raw.get("category") != "samsung_hbm4_price":
            continue
        enriched = enrich_event(raw)
        if not enriched.get("link_verified"):
            continue
        obs = extract_samsung_hbm4_price(enriched)
        if not obs:
            continue
        merged = merge_samsung_hbm4_price(samsung_price_state, obs)
        changes = samsung_hbm4_price_changes(samsung_price_state, merged)
        samsung_price_state = merged
        if changes:
            samsung_price_changes.extend(changes)
    if samsung_price_changes and not first_run:
        verified_events.append(samsung_hbm4_price_event(samsung_price_state, list(dict.fromkeys(samsung_price_changes))))

    thermal_state = dict(state.get("samsung_hbm4e_thermal_package") or {})
    thermal_track_version = int(state.get("samsung_hbm4e_thermal_track_version") or 0)
    if thermal_track_version < SAMSUNG_HBM4E_THERMAL_TRACK_VERSION:
        seeded = dict(SAMSUNG_HBM4E_THERMAL_BASELINE)
        seeded.update({k: v for k, v in thermal_state.items() if v not in (None, "")})
        thermal_state = seeded
        thermal_track_version = SAMSUNG_HBM4E_THERMAL_TRACK_VERSION

    thermal_changes: list[str] = []
    for raw in raw_events:
        if raw.get("category") != "hbm4e_thermal_package":
            continue
        enriched = enrich_event(raw)
        if not enriched.get("link_verified"):
            continue
        obs = extract_samsung_hbm4e_thermal_package(enriched)
        if not obs:
            continue
        merged = merge_samsung_hbm4e_thermal_package(thermal_state, obs)
        changes = samsung_hbm4e_thermal_changes(thermal_state, merged)
        thermal_state = merged
        if changes:
            thermal_changes.extend(changes)
    if thermal_changes and not first_run:
        verified_events.append(samsung_hbm4e_thermal_event(thermal_state, list(dict.fromkeys(thermal_changes))))

    citi_state = dict(state.get("citi_hbm_outlook") or {})
    citi_track_version = int(state.get("citi_hbm_track_version") or 0)
    if citi_track_version < CITI_HBM_TRACK_VERSION:
        seeded = dict(CITI_HBM_BASELINE)
        seeded.update({k: v for k, v in citi_state.items() if v not in (None, "")})
        citi_state = seeded
        citi_track_version = CITI_HBM_TRACK_VERSION

    citi_changes: list[str] = []
    for raw in raw_events:
        if raw.get("category") != "citi_hbm_outlook":
            continue
        enriched = enrich_event(raw)
        if not enriched.get("link_verified"):
            continue
        obs = extract_citi_hbm_outlook(enriched)
        if not obs:
            continue
        merged = merge_citi_hbm_outlook(citi_state, obs)
        changes = citi_hbm_material_changes(citi_state, merged)
        citi_state = merged
        if changes:
            citi_changes.extend(changes)
    if citi_changes and not first_run:
        verified_events.append(citi_hbm_change_event(citi_state, list(dict.fromkeys(citi_changes))))

    fx = fetch_fx()
    if fx.get("error"):
        errors.append(fx["error"])

    send_events = [] if first_run else verified_events
    send_events = send_events[-12:]
    new_fact_keys = {e.get("fact_key") for e in verified_events if e.get("fact_key")}

    # 첫 실행은 최근 기사들의 인식 가능한 사실키도 기준선에 저장해 재전재 폭탄을 막는다.
    if first_run:
        for raw in raw_events:
            key = fact_signature_from_raw(raw)
            if key:
                new_fact_keys.add(key)

    pending = {
        "updated_at_kst": now.isoformat(timespec="seconds"),
        "seen_ids": sorted((seen_before | current_ids))[-1200:],
        "seen_fact_keys": sorted(seen_fact_keys | new_fact_keys)[-500:],
        "structure_baseline_version": STRUCTURE_BASELINE_VERSION,
        "samsung_hbm4_price_track_version": samsung_price_track_version,
        "samsung_hbm4_price": samsung_price_state,
        "samsung_hbm4e_thermal_track_version": thermal_track_version,
        "samsung_hbm4e_thermal_package": thermal_state,
        "citi_hbm_track_version": citi_track_version,
        "citi_hbm_outlook": citi_state,
        "last_unseen_raw_count": len(unseen_raw),
        "last_verified_event_count": len(verified_events),
        "last_send_event_count": len(send_events),
        "freshness_hours": SEND_FRESHNESS_HOURS,
        "usdkrw": fx,
        "errors": errors,
    }
    write_json(OUT / "rubin_hbm_pending_state.json", pending)

    if first_run:
        (OUT / "rubin_hbm_rebaseline.txt").write_text(
            f"Initial verified baseline at {now.isoformat(timespec='seconds')}; {len(raw_events)} recent items stored; no Telegram alert sent.\n",
            encoding="utf-8",
        )

    if send_events:
        (OUT / "rubin_hbm_alert.md").write_text(build_alert(now, send_events, fx), encoding="utf-8")

    status = [
        "# Rubin HBM Watch",
        f"- checked_at_kst: {now.isoformat(timespec='seconds')}",
        f"- first_run_baseline: {str(first_run).lower()}",
        f"- recent_raw_events: {len(raw_events)}",
        f"- unseen_raw_events: {len(unseen_raw)}",
        f"- verified_events: {len(verified_events)}",
        f"- Samsung HBM4 price typed changes: {len(samsung_price_changes)}",
        f"- Samsung HBM4E thermal/package typed changes: {len(thermal_changes)}",
        f"- Citi HBM typed changes: {len(citi_changes)}",
        f"- send_events: {len(send_events)}",
        f"- freshness_hours: {SEND_FRESHNESS_HOURS}",
        f"- break_even_gpu_growth: {BREAKEVEN_GPU_GROWTH*100:.1f}%",
        f"- source_errors_or_suppressed: {len(errors)}",
    ]
    for e in errors[:12]:
        status.append(f"  - {e}")
    (OUT / "rubin_hbm_status.md").write_text("\n".join(status) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
