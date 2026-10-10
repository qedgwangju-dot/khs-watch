#!/usr/bin/env python3
"""Foundry -> fabless -> downstream price-pass-through watcher.

Tracks whether foundry and backend cost inflation is actually being transmitted
into PMIC/DDIC/MCU and other fabless selling prices.

Evidence rules:
- TrendForce Press/Research = official TrendForce research.
- TrendForce News = editorial/news aggregation, not the TrendForce research team.
- Economic Daily News / Reuters / Bloomberg / major trade media = report-level.
- Individual fabless price hikes are only marked "official" when the vendor itself
  publishes the price action/effective date.

Baseline, 2026-10-05/06:
- TrendForce News citing Economic Daily News: PMIC, driver IC and MCU suppliers
  are considering a second price hike in late 2026 to early 2027, 5% to
  double-digit percentages.
- Economic Daily News: TSMC mature-node pricing reportedly rises ~3-10% from Jan 2027.
- TrendForce research: top-10 foundry 8-inch utilization 88% in 2026 and 90% in 2H26;
  8-inch foundry prices had risen ~5-15% from 1Q to 2Q26.
- TrendForce research: selected constrained 12-inch mature nodes showed ~5-10%
  increases between 2Q and 3Q26.
"""
from __future__ import annotations

import datetime as dt
import hashlib
import html
import json
import pathlib
import re
import time
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from email.utils import parsedate_to_datetime
from zoneinfo import ZoneInfo

try:
    from googlenewsdecoder import gnewsdecoder
except Exception:  # pragma: no cover
    gnewsdecoder = None

ROOT = pathlib.Path(__file__).resolve().parents[1]
STATE_PATH = ROOT / "data" / "foundry_fabless_price_passthrough_state.json"
OUT_DIR = ROOT / "out"
ALERT_PATH = OUT_DIR / "foundry_fabless_price_passthrough_alert.html"
PENDING_PATH = OUT_DIR / "foundry_fabless_price_passthrough_pending_state.json"
STATUS_PATH = OUT_DIR / "foundry_fabless_price_passthrough_status.md"
KST = ZoneInfo("Asia/Seoul")
TRACK_VERSION = 1

TREND_NEWS_URL = (
    "https://www.trendforce.com/news/2026/10/05/"
    "news-ic-designers-reportedly-eye-5-to-double-digit-price-hikes-in-late-2026-early-2027-as-foundry-costs-rise/"
)
ECONOMIC_DAILY_URL = "https://money.udn.com/money/amp/story/5612/9794455"
TREND_FOUNDRY_JUN30_URL = "https://www.trendforce.com/presscenter/news/20260630-13127.html"
TREND_FOUNDRY_OCT5_URL = "https://www.trendforce.com/research/download/RP261005QL3"
TREND_TSMC_PREVIEW_URL = (
    "https://www.trendforce.com/news/2026/10/05/"
    "news-tsmc-earnings-preview-terafab-talks-price-hikes-and-a14-intel-race-lead-five-key-themes/"
)

BASELINE = {
    "fabless_hike_status": "검토·보도 단계",
    "fabless_hike_min_pct": 5.0,
    "fabless_hike_upper_kind": "두 자릿수",
    "fabless_hike_timing": "2026년 말~2027년 초",
    "fabless_scope": ["PMIC", "DDIC", "MCU"],
    "fabless_official_company_confirmed": False,
    "tsmc_mature_2027_hike_min_pct": 3.0,
    "tsmc_mature_2027_hike_max_pct": 10.0,
    "tsmc_mature_effective": "2027-01",
    "tsmc_mature_official_company_confirmed": False,
    "tsmc_advanced_2027_estimate_min_pct": 5.0,
    "tsmc_advanced_2027_estimate_max_pct": 10.0,
    "tsmc_packaging_2027_estimate_min_pct": 10.0,
    "tsmc_packaging_2027_estimate_max_pct": 15.0,
    "tsmc_advanced_packaging_source_kind": "기관 추정치 인용 보도",
    "eight_inch_util_2026_pct": 88.0,
    "eight_inch_util_2h26_pct": 90.0,
    "eight_inch_foundry_hike_1q_to_2q_min_pct": 5.0,
    "eight_inch_foundry_hike_1q_to_2q_max_pct": 15.0,
    "twelve_inch_selected_hike_2q_to_3q_min_pct": 5.0,
    "twelve_inch_selected_hike_2q_to_3q_max_pct": 10.0,
    "order_pull_in_reported": True,
    "broad_demand_recovery_confirmed": False,
    "inventory_risk_flag": True,
    "source": "TrendForce research + TrendForce News + Economic Daily News",
    "source_kind": (
        "공식 TrendForce 연구수치와 TrendForce News/경제일보 보도를 분리 보존; "
        "fabless 5%~두 자릿수 인상은 아직 개별 회사 공식 확정 아님"
    ),
    "trend_news_url": TREND_NEWS_URL,
    "economic_daily_url": ECONOMIC_DAILY_URL,
    "trend_foundry_url": TREND_FOUNDRY_JUN30_URL,
    "trend_foundry_oct5_url": TREND_FOUNDRY_OCT5_URL,
    "trend_tsmc_preview_url": TREND_TSMC_PREVIEW_URL,
    "as_of": "2026-10-05",
}


# Semiconductor equipment spares are a distinct cost layer from foundry wafer
# price pass-through. ASML's 10% report is NOT a first-party price announcement.
SEMICAP_SOURCE_URL = "https://www.thelec.kr/news/articleView.html?idxno=63515"
SEMICAP_BASELINE_KEY = "ASML|spares|10|2027-01|reported"
SEMICAP_BASELINE_DATE = "2026-10-10"
SEMICAP_QUERIES = [
    ("ko", "ASML 노광장비 유지보수 교체부품 가격 인상 2027 삼성 SK"),
    ("en", "ASML lithography spare parts replacement price increase 2027"),
    ("en", "ASML Applied Materials Tokyo Electron semiconductor equipment spare parts price hikes"),
]
SEMICAP_VENDOR_DOMAINS = {
    "ASML": ("asml.com",),
    "Applied Materials": ("appliedmaterials.com",),
    "Tokyo Electron": ("tel.com",),
    "Advanced Energy": ("advancedenergy.com",),
    "KLA": ("kla.com",),
    "Lam Research": ("lamresearch.com",),
}
SEMICAP_MEDIA_DOMAINS = ("thelec.kr", "reuters.com", "bloomberg.com", "nikkei.com", "digitimes.com", "theinformation.com")
SEMICAP_VENDOR_ALIASES = {
    "ASML": ("asml", "에이에스엠엘"),
    "Applied Materials": ("applied materials", "어플라이드머티리얼즈"),
    "Tokyo Electron": ("tokyo electron", "도쿄일렉트론", "東京エレクトロン"),
    "Advanced Energy": ("advanced energy", "어드밴스드에너지"),
    "KLA": ("kla corporation", "kla corp", "케이엘에이"),
    "Lam Research": ("lam research", "램리서치"),
}

FABLESS = {
    "Novatek": ("novatek", "聯詠", "联咏"),
    "Sitronix": ("sitronix", "矽創", "矽创"),
    "FocalTech": ("focaltech", "敦泰"),
    "Anpec": ("anpec", "茂達", "茂达"),
    "Global Mixed-mode": ("global mixed-mode", "gmt", "致新"),
    "Silergy": ("silergy", "矽力", "硅力"),
    "Holtek": ("holtek", "盛群"),
    "Texas Instruments": ("texas instruments", " tx ", "德州儀器", "德州仪器"),
    "Renesas": ("renesas", "瑞薩", "瑞萨"),
    "onsemi": ("onsemi", "on semiconductor", "安森美"),
}

FOUNDRIES = {
    "TSMC": ("tsmc", "台積電", "台积电"),
    "UMC": ("umc", "聯電", "联电"),
    "Vanguard": ("vanguard international semiconductor", "vis", "世界先進", "世界先进"),
    "PSMC": ("psmc", "powerchip", "力積電", "力积电"),
    "SMIC": ("smic", "中芯"),
    "Samsung Foundry": ("samsung foundry", "三星晶圓", "三星晶圆", "삼성 파운드리"),
}

QUERIES = [
    ("en", '"IC designers" 5% double-digit price hikes foundry costs PMIC driver IC MCU'),
    ("en", 'TrendForce PMIC driver IC MCU second price hike late 2026 early 2027'),
    ("en", 'TSMC mature node price increase January 2027 3% 10% foundry'),
    ("en", 'TSMC advanced node price increase 2027 5% 10% advanced packaging 10% 15%'),
    ("en", '8-inch foundry price increase PMIC DDIC MCU capacity utilization 90% TrendForce'),
    ("en", 'PMIC DDIC MCU official price increase 2027 foundry cost pass through'),
    ("en", 'Novatek Sitronix FocalTech Anpec Silergy Holtek price increase 2027'),
    ("en", 'Renesas onsemi Texas Instruments price increase power IC 2027'),
    ("ko", '파운드리 가격 인상 PMIC DDI MCU 팹리스 판가 인상 2027'),
    ("ko", 'TSMC 성숙공정 2027 1월 3% 10% 가격 인상'),
    ("ko", 'TSMC 선단공정 첨단패키징 가격 인상 2027 5% 10% 15%'),
    ("zh", '晶圓代工 漲價 IC 設計 5% 雙位數 PMIC 驅動IC MCU 2027'),
    ("zh", '台積電 成熟製程 2027 1月 漲價 3% 10% IC設計'),
    ("zh", '聯詠 矽創 敦泰 茂達 致新 矽力 盛群 漲價 2027'),
]

OFFICIAL_DOMAINS = {
    "trendforce.com",
    "tsmc.com", "umc.com", "vis.com.tw", "powerchip.com", "smic.com",
    "novatek.com.tw", "sitronix.com.tw", "focaltech-electronics.com",
    "anpec.com.tw", "gmt.com.tw", "silergy.com", "holtek.com",
    "ti.com", "renesas.com", "onsemi.com",
}
TIER1_DOMAINS = {
    "money.udn.com", "reuters.com", "bloomberg.com", "nikkei.com",
    "digitimes.com", "01.co", "cna.com.tw",
}

def _clean(v: str | None) -> str:
    v = html.unescape(v or "")
    v = re.sub(r"<[^>]+>", " ", v)
    return re.sub(r"\s+", " ", v).strip()

def _rss_url(lang: str, query: str) -> str:
    if lang == "ko":
        p = {"q": query, "hl": "ko", "gl": "KR", "ceid": "KR:ko"}
    elif lang == "zh":
        p = {"q": query, "hl": "zh-TW", "gl": "TW", "ceid": "TW:zh-Hant"}
    else:
        p = {"q": query, "hl": "en-US", "gl": "US", "ceid": "US:en"}
    return "https://news.google.com/rss/search?" + urllib.parse.urlencode(p)

def _fetch(url: str) -> bytes:
    req = urllib.request.Request(
        url,
        headers={"User-Agent": "Mozilla/5.0 (compatible; khs-foundry-pass-through-watch/1.0)"},
    )
    err = None
    for attempt in range(3):
        try:
            with urllib.request.urlopen(req, timeout=25) as r:
                return r.read()
        except Exception as exc:
            err = exc
            if attempt < 2:
                time.sleep(1 + attempt)
    raise err

def _decode(link: str) -> str:
    if "news.google.com" not in (link or "") or gnewsdecoder is None:
        return link
    try:
        out = gnewsdecoder(link, interval=0.15)
        if isinstance(out, dict):
            u = str(out.get("decoded_url") or "").strip()
            if u.startswith("http") and "news.google.com" not in u:
                return u
    except Exception:
        pass
    return link

def _pub_kst(raw: str) -> str:
    try:
        d = parsedate_to_datetime(raw)
        if d.tzinfo is None:
            d = d.replace(tzinfo=dt.timezone.utc)
        return d.astimezone(KST).isoformat(timespec="seconds")
    except Exception:
        return ""

def _host(url: str) -> str:
    try:
        return urllib.parse.urlparse(url).netloc.lower()
    except Exception:
        return ""

def _source_rank(item: dict) -> int:
    host = _host(str(item.get("link") or ""))
    if any(host == d or host.endswith("." + d) for d in OFFICIAL_DOMAINS):
        return 3
    if any(host == d or host.endswith("." + d) for d in TIER1_DOMAINS):
        return 2
    src = _clean(str(item.get("source") or "")).lower()
    if src in {"trendforce", "tsmc", "umc", "renesas", "onsemi", "texas instruments"}:
        return 3
    if any(k in src for k in ("economic daily news", "經濟日報", "reuters", "bloomberg", "nikkei")):
        return 2
    return 0

def _normalize_title(v: str) -> str:
    v = _clean(v).lower()
    v = re.sub(r"\s+[-–—|]\s+[^-–—|]{1,80}$", "", v)
    v = re.sub(r"[^0-9a-z가-힣一-龥]+", " ", v)
    return re.sub(r"\s+", " ", v).strip()

def _fingerprint(title: str, source: str) -> str:
    return hashlib.sha256((_normalize_title(title) + "|" + source.lower()).encode()).hexdigest()[:24]

def _named(text: str, table: dict[str, tuple[str, ...]]) -> list[str]:
    low = " " + text.lower() + " "
    out = []
    for name, aliases in table.items():
        if any(alias.lower() in low or alias in text for alias in aliases):
            out.append(name)
    return out

def _is_relevant(item: dict) -> bool:
    text = _clean(f"{item.get('title','')} {item.get('description','')}")
    low = text.lower()
    price = any(k in low for k in (
        "price increase", "price hike", "raise prices", "pricing", "漲價", "涨价",
        "가격 인상", "판가 인상", "報價調升", "报价调升",
    ))
    manufacturing = any(k in low for k in (
        "foundry", "wafer", "backend", "osat", "晶圓代工", "晶圆代工",
        "封測", "封测", "파운드리", "웨이퍼", "후공정",
    ))
    fabless = any(k in low for k in (
        "pmic", "driver ic", "display driver", "ddic", "mcu", "microcontroller",
        "ic design", "fabless", "電源管理", "电源管理", "驅動ic", "驱动ic",
        "微控制器", "팹리스", "전력관리", "디스플레이 드라이버",
    ))
    capacity = any(k in low for k in (
        "capacity", "utilization", "3nm", "2nm", "8-inch", "8 inch",
        "產能", "产能", "稼動率", "가동률", "캐파",
    ))
    return bool(price and (manufacturing or fabless or capacity))

def _extract_state(item: dict) -> dict | None:
    if not _is_relevant(item) or _source_rank(item) < 2:
        return None
    text = _clean(f"{item.get('title','')} {item.get('description','')}")
    low = text.lower()
    obs: dict = {}

    # Fabless pass-through. Keep "double-digit" non-numeric rather than inventing 10%.
    if (
        any(k in low for k in ("ic design", "fabless", "pmic", "driver ic", "mcu"))
        and re.search(r"5\s*%[^.]{0,100}?(?:double[- ]digit|雙位數|双位数|두 자릿수)", text, re.I)
    ):
        obs["fabless_hike_min_pct"] = 5.0
        obs["fabless_hike_upper_kind"] = "두 자릿수"
        obs["fabless_hike_status"] = "검토·보도 단계"
        obs["fabless_official_company_confirmed"] = False

    # Individual company official hike: vendor source + effective-date/raise language.
    named_fabless = _named(text, FABLESS)
    if named_fabless and _source_rank(item) >= 3 and any(k in low for k in ("effective", "new prices", "will raise", "price increase", "漲價", "涨价")):
        obs["fabless_official_company_confirmed"] = True
        obs["official_fabless_vendors"] = ", ".join(named_fabless)

    # TSMC mature-node report.
    if "tsmc" in low or "台積電" in text or "台积电" in text:
        m = re.search(r"(?:mature[- ]node|成熟製程|成熟制程)[^.%]{0,120}?(\d{1,2})\s*%[^.%]{0,20}?(?:to|[-~–—至])\s*(\d{1,2})\s*%", text, re.I)
        if not m:
            m = re.search(r"(\d{1,2})\s*%[^.%]{0,20}?(?:to|[-~–—至])\s*(\d{1,2})\s*%[^.]{0,100}?(?:mature[- ]node|成熟製程|成熟制程)", text, re.I)
        if m:
            lo, hi = float(m.group(1)), float(m.group(2))
            if 0 < lo <= hi <= 30:
                obs["tsmc_mature_2027_hike_min_pct"] = lo
                obs["tsmc_mature_2027_hike_max_pct"] = hi
                obs["tsmc_mature_official_company_confirmed"] = "tsmc.com" in _host(str(item.get("link") or ""))

    # Utilization / foundry pricing from TrendForce research.
    m88 = re.search(r"(?:8[- ]inch)[^.]{0,180}?(88(?:\.0)?)\s*%", text, re.I)
    if m88:
        obs["eight_inch_util_2026_pct"] = float(m88.group(1))
    m90 = re.search(r"(?:8[- ]inch)[^.]{0,180}?(90(?:\.0)?)\s*%", text, re.I)
    if m90:
        obs["eight_inch_util_2h26_pct"] = float(m90.group(1))

    if any(k in low for k in ("pulling in orders", "pull-in orders", "advance procurement", "提前拉貨", "提前拉货", "주문을 앞당")):
        obs["order_pull_in_reported"] = True
    if any(k in low for k in ("not reflect a broad-based recovery", "not a broad-based recovery", "非全面復甦", "전반적인 수요 회복이 아니")):
        obs["broad_demand_recovery_confirmed"] = False
        obs["inventory_risk_flag"] = True

    if not obs:
        return None
    obs.update({
        "source": item.get("source") or "출처 미표시",
        "source_url": item.get("link") or "",
        "source_rank": _source_rank(item),
        "as_of": (item.get("published_kst") or "")[:10],
    })
    return obs

def _merge(old: dict, obs: dict) -> dict:
    merged = dict(old)
    old_rank = int(merged.get("source_rank") or 0)
    new_rank = int(obs.get("source_rank") or 0)
    for k, v in obs.items():
        if v in (None, ""):
            continue
        if k in ("source", "source_url", "as_of", "source_rank") and new_rank < old_rank:
            continue
        # Do not let a secondary article clear a previously official confirmation.
        if k in ("fabless_official_company_confirmed", "tsmc_mature_official_company_confirmed") and merged.get(k) is True and v is False:
            continue
        merged[k] = v
    return merged

def _changes(old: dict, new: dict) -> list[str]:
    out = []
    for key, label, threshold in (
        ("fabless_hike_min_pct", "팹리스 가격 인상 하단", 2.0),
        ("tsmc_mature_2027_hike_min_pct", "TSMC 2027 성숙공정 인상 하단", 2.0),
        ("tsmc_mature_2027_hike_max_pct", "TSMC 2027 성숙공정 인상 상단", 2.0),
        ("eight_inch_util_2026_pct", "8인치 가동률", 3.0),
        ("eight_inch_util_2h26_pct", "2H26 8인치 가동률", 3.0),
    ):
        a, b = old.get(key), new.get(key)
        if b is None:
            continue
        if a is None:
            out.append(f"{label}: {float(b):.1f}% 신규 확인")
        elif abs(float(b) - float(a)) >= threshold:
            out.append(f"{label}: {float(a):.1f}%→{float(b):.1f}%")

    a, b = old.get("fabless_hike_upper_kind"), new.get("fabless_hike_upper_kind")
    if b is not None and a != b:
        out.append(f"팹리스 인상 상단: {a or '미확인'}→{b}")

    for key, label in (
        ("fabless_official_company_confirmed", "팹리스 가격 인상 공식확인"),
        ("tsmc_mature_official_company_confirmed", "TSMC 성숙공정 인상 공식확인"),
        ("broad_demand_recovery_confirmed", "전방 수요회복 판정"),
    ):
        a, b = old.get(key), new.get(key)
        if b is not None and a is not None and bool(a) != bool(b):
            out.append(f"{label}: {a}→{b}")
    if new.get("official_fabless_vendors") and new.get("official_fabless_vendors") != old.get("official_fabless_vendors"):
        out.append("공식 가격 인상 팹리스: " + str(new["official_fabless_vendors"]))
    return out

def _event(item: dict) -> dict | None:
    if not _is_relevant(item) or _source_rank(item) < 2:
        return None
    if _extract_state(item):
        # Numeric/typed changes are handled by the state machine.
        return None
    text = _clean(f"{item.get('title','')} {item.get('description','')}")
    low = text.lower()
    foundries = _named(text, FOUNDRIES)
    fabless = _named(text, FABLESS)
    kinds = []
    if any(k in low for k in ("price increase", "price hike", "漲價", "涨价", "가격 인상")):
        kinds.append("가격")
    if any(k in low for k in ("capacity", "3nm", "2nm", "8-inch", "utilization", "產能", "产能", "캐파", "가동률")):
        kinds.append("생산능력")
    if any(k in low for k in ("pull-in", "pulling in", "advance procurement", "inventory", "提前拉貨", "提前拉货", "재고", "주문을 앞당")):
        kinds.append("주문·재고")
    if not kinds:
        return None
    key = "|".join(sorted(kinds)) + "|" + ",".join(sorted(foundries + fabless or ["industry"]))
    return {
        **item,
        "event_key": key,
        "event_types": sorted(set(kinds)),
        "foundries": foundries,
        "fabless": fabless,
        "source_rank": _source_rank(item),
    }


def _semicap_host_matches(host: str, domain: str) -> bool:
    return host == domain or host.endswith("." + domain)


def _semicap_source_grade(item: dict, vendor: str) -> str:
    # A claimed publisher label must not turn third-party text into official vendor evidence.
    host = _host(str(item.get("link") or ""))
    if any(_semicap_host_matches(host, x) for x in SEMICAP_VENDOR_DOMAINS[vendor]):
        return "official"
    if any(_semicap_host_matches(host, x) for x in SEMICAP_MEDIA_DOMAINS):
        return "reported"
    # Google News RSS sometimes does not resolve the original link. Such
    # reporting is always lower-grade and never company-confirmed.
    source = _clean(str(item.get("source") or "")).lower()
    if _semicap_host_matches(host, "news.google.com") and source in (
        "디일렉", "the elec", "reuters", "bloomberg", "nikkei", "digitimes",
    ):
        return "reported"
    return ""


def _semicap_month(text: str) -> str:
    low = text.lower()
    m = re.search(r"2027[년\s./-]*(0?[1-9]|1[0-2])(?:월|\b)", low)
    if m:
        return f"2027-{int(m.group(1)):02d}"
    if "2027" in low and ("january" in low or "jan " in low or "1월" in low):
        return "2027-01"
    if "내년 1월" in low:
        return "2027-01"
    return "미확인"


def _semicap_observation(item: dict) -> dict | None:
    title = _clean(str(item.get("title") or ""))
    details = _clean(str(item.get("description") or ""))
    text = f"{title} {details}"
    low = text.lower()
    pub = str(item.get("published_kst") or "")[:10]
    if pub and pub < SEMICAP_BASELINE_DATE:
        return None
    vendor = next((name for name, aliases in SEMICAP_VENDOR_ALIASES.items()
                   if any(re.search(r"(?<![a-z])" + re.escape(a.lower()) + r"(?![a-z])", low)
                          for a in aliases)), None)
    if not vendor:
        return None
    grade = _semicap_source_grade(item, vendor)
    if not grade:
        return None
    if not any(p in low for p in (
        "price increase", "price hike", "raise prices", "raised prices",
        "higher prices", "price adjustment", "가격 인상", "값 인상",
        "가격 조정", "인상 확정", "値上げ", "涨价", "漲價",
    )):
        return None
    if any(p in low for p in ("share price", "stock price", "주가 상승", "목표주가")):
        return None
    spares = any(p in low for p in (
        "spare part", "replacement part", "maintenance part", "service part",
        "consumable part", "교체부품", "교체용", "유지보수", "소모성 부품", "부품값", "부품 가격",
    ))
    systems = any(p in low for p in (
        "equipment", "new system", "lithography system", "scanner", "노광장비",
        "장비값", "신규 장비", "제조장비", "판매 중인 장비", "semiconductor tool",
    ))
    if not (spares or systems):
        return None
    tentative = any(p in low for p in (
        "in talks", "negotiat", "consider", "proposal", "propos",
        "논의", "협의 중", "검토", "가능성", "추진",
    ))
    # New tool prices must have first-party firm wording, not negotiation headlines.
    if not spares and (grade != "official" or tentative):
        return None
    m = re.search(r"(?<!\d)(\d{1,2}(?:\.\d+)?)\s*[%％]", text)
    pct = float(m.group(1)) if m else None
    if pct is not None and not (0 < pct <= 50):
        return None
    if spares and pct is None:
        return None
    if vendor != "ASML" and grade != "official":
        return None
    month = _semicap_month(text)
    scope = "spares" if spares else "systems"
    if vendor == "ASML" and scope == "spares" and grade == "reported" and pct == 10:
        if month in ("2027-01", "미확인"):
            return None  # Same material fact as separately attributed baseline.
    key = "|".join((vendor, scope, f"{pct:g}" if pct is not None else "unquoted", month, grade))
    return {
        "key": key, "vendor": vendor, "scope": scope,
        "rate": f"{pct:g}%" if pct is not None else "인상률 미공개",
        "month": month, "grade": grade, "title": title,
        "link": str(item.get("link") or ""),
    }


def _semicap_plan(items: list[dict], previous: dict) -> tuple[dict, list[dict]]:
    # Only the existing workflow's successful send path commits this pending state.
    current = dict(previous or {})
    delivered = set(current.get("delivered_keys") or [])
    alerts = []
    if SEMICAP_BASELINE_KEY not in delivered:
        alerts.append({
            "key": SEMICAP_BASELINE_KEY, "vendor": "ASML", "scope": "spares",
            "rate": "10%", "month": "2027-01", "grade": "reported",
            "title": "한국향 EUV·DUV 교체부품 10% 인상 보도",
            "link": SEMICAP_SOURCE_URL, "initial": True,
        })
        delivered.add(SEMICAP_BASELINE_KEY)
    for item in sorted(items, key=lambda x: x.get("published_kst") or ""):
        obs = _semicap_observation(item)
        if obs and obs["key"] not in delivered:
            alerts.append(obs)
            delivered.add(obs["key"])
    current["delivered_keys"] = sorted(delivered)[-300:]
    current["baseline_source"] = SEMICAP_SOURCE_URL
    current["source_status"] = "ASML 부품 인상: 보도 단계 / 신규 장비: 협의 단계"
    return current, alerts


def _semicap_alert_lines(events: list[dict]) -> list[str]:
    lines = []
    for ev in events:
        grade = "업체 공식자료" if ev["grade"] == "official" else "언론보도(업체 공식 공지 미확인)"
        kind = "교체·유지보수 부품" if ev["scope"] == "spares" else "신규 제조장비"
        lines.extend((
            "",
            "• <b>" + html.escape(ev["vendor"] + " " + kind) + "</b>",
            "  가격: " + html.escape(ev["rate"]) + " · 적용월: " + html.escape(ev["month"]),
            "  확인등급: " + html.escape(grade),
            "  " + html.escape(ev["title"]),
        ))
        if ev.get("initial"):
            lines.extend((
                "  디일렉 단독: 삼성전자·SK하이닉스 구매조직의 수용 보도. "
                "세 회사의 개별 공식 가격표·계약조건은 미공개.",
                "  ASML 신규 노광장비 가격 인상은 아직 협의 단계이며 위 10% 범위에 포함하지 않음.",
                "  고객 원가증가 = 해당 고객의 ASML 교체부품 구입액 × 10%. "
                "ASML 설치장비 관리 매출 전체에 10%를 적용하지 않음.",
            ))
        if ev.get("link"):
            lines.append('  <a href="' + html.escape(ev["link"], quote=True) + '">근거 링크</a>')
    lines.extend((
        "",
        "다음 확인: ASML·고객 공식 가격표, 신규 장비 가격 확정, "
        "부품 교체주기·가동률, 동종 장비 업체 인상, 고객 원가·마진 전가.",
    ))
    return lines

def collect(cutoff: dt.datetime) -> tuple[list[dict], list[str]]:
    items, errors, seen = [], [], set()
    for lang, query in QUERIES + SEMICAP_QUERIES:
        try:
            root = ET.fromstring(_fetch(_rss_url(lang, query)))
        except Exception as exc:
            errors.append(f"{query[:45]}: {type(exc).__name__}: {exc}")
            continue
        for node in root.findall(".//item")[:35]:
            title = _clean(node.findtext("title"))
            desc = _clean(node.findtext("description"))
            source = _clean(node.findtext("source"))
            link = _decode(_clean(node.findtext("link")))
            pub = _pub_kst(_clean(node.findtext("pubDate")))
            try:
                pd = dt.datetime.fromisoformat(pub) if pub else None
            except Exception:
                pd = None
            if pd and pd < cutoff:
                continue
            fp = _fingerprint(title, source)
            if fp in seen:
                continue
            seen.add(fp)
            item = {
                "title": title, "description": desc, "source": source, "link": link,
                "published_kst": pub, "fingerprint": fp, "query": query,
            }
            if _is_relevant(item) or _semicap_observation(item):
                items.append(item)
    return items, errors

def _load() -> dict:
    if not STATE_PATH.exists():
        return {}
    return json.loads(STATE_PATH.read_text(encoding="utf-8"))

def write_outputs(items: list[dict], errors: list[str]) -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    state = _load()
    now = dt.datetime.now(KST)
    current = dict(state.get("current") or BASELINE)
    seen = set(state.get("seen_fingerprints") or [])
    delivered = set(state.get("delivered_event_keys") or [])
    semicap_state, semicap_events = _semicap_plan(items, state.get("semicap_watch") or {})

    changes, source_url = [], ""
    for item in sorted(items, key=lambda x: x.get("published_kst") or ""):
        obs = _extract_state(item)
        if not obs:
            continue
        merged = _merge(current, obs)
        cur = _changes(current, merged)
        current = merged
        if cur:
            changes.extend(cur)
            source_url = current.get("source_url") or source_url

    new_events = []
    for item in items:
        ev = _event(item)
        if not ev:
            continue
        if ev["fingerprint"] in seen or ev["event_key"] in delivered:
            continue
        new_events.append(ev)
    new_events = new_events[:4]

    for item in items:
        seen.add(item["fingerprint"])
    pending_delivered = set(delivered)
    pending_delivered.update(x["event_key"] for x in new_events)

    pending = {
        "initialized": True,
        "track_version": TRACK_VERSION,
        "current": current,
        "updated_at_kst": now.isoformat(timespec="seconds"),
        "last_scan_count": len(items),
        "last_typed_change_count": len(changes),
        "last_new_event_count": len(new_events),
        "seen_fingerprints": sorted(seen)[-1200:],
        "delivered_event_keys": sorted(pending_delivered)[-500:],
        "semicap_watch": semicap_state,
    }
    for k in ("last_successful_delivery_kst", "telegram_message_ids", "telegram_message_id", "bot_username", "delivery_receipt"):
        if state.get(k) is not None:
            pending[k] = state[k]
    PENDING_PATH.write_text(json.dumps(pending, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    status = [
        "# 파운드리→팹리스 가격 전가 감시",
        "",
        f"- 조회시각(KST): {now.isoformat(timespec='seconds')}",
        f"- 후보: {len(items)}건",
        f"- 숫자·공식성 변화: {len(changes)}건",
        f"- 신규 구조 이벤트: {len(new_events)}건",
        f"- 반도체 장비 가격 이벤트: {len(semicap_events)}건",
        f"- 원천 오류: {len(errors)}건",
        "- 기준: 팹리스 5%~두 자릿수 인상은 검토·보도 단계, 개별 회사 공식 인상 아님",
        "- 기준: TSMC 성숙공정 3~10% 인상도 보도 단계, TSMC 공식 공지와 분리",
        "- 공식 TrendForce 연구: 2026년 8인치 가동률 88%, 2H26 90%; 1Q→2Q 가격 5~15% 상승",
    ]
    STATUS_PATH.write_text("\n".join(status) + "\n", encoding="utf-8")

    ALERT_PATH.unlink(missing_ok=True)
    if not changes and not new_events and not semicap_events:
        return

    lines = [
        "<b>[파운드리→팹리스 가격 전가 변화]</b>",
        f"조회 {now.strftime('%Y-%m-%d %H:%M')} KST",
    ]
    if changes:
        lines += ["", "• <b>추적 상태 변화</b>"]
        for c in dict.fromkeys(changes):
            lines.append("  " + html.escape(c))
    lines += [
        "",
        "• <b>현재 기준선</b>",
        "  팹리스: PMIC·DDIC·MCU 업체들의 <b>5%~두 자릿수</b> 2차 인상 검토 · 2026년 말~2027년 초 · 아직 개별 회사 공식 확정 아님",
        "  TSMC 성숙공정: 2027년 1월부터 <b>약 3~10%</b> 인상 보도 · TSMC 공식 공지 전",
        "  TrendForce 연구: 2026년 8인치 평균 가동률 <b>88%</b>, 2H26 <b>90%</b> 전망 · 1Q→2Q 파운드리 가격 <b>+5~15%</b>",
        "  12인치 성숙공정: 일부 타이트한 노드가 2Q→3Q <b>+5~10%</b> 신호",
        "  해석: 3nm/선단·첨단패키징 AI 수요와 성숙공정 축소가 동시에 진행돼 원가 압력이 PMIC·DDIC·MCU까지 전이",
        "  함정: 주문 앞당김은 전반적 수요회복과 동일하지 않음 — 고객 과잉주문·재고조정 여부를 별도 확인",
        "  다음 확인: 실제 가격표·효력일·고객 수용 · TSMC/UMC/VIS/PSMC 가동률 · PMIC/DDIC/MCU 판가 · 주문취소/재고",
    ]
    if source_url:
        lines.append('  <a href="' + html.escape(str(source_url), quote=True) + '">이번 변화 근거</a>')
    lines.append('  <a href="' + html.escape(TREND_NEWS_URL, quote=True) + '">TrendForce News</a>')
    lines.append('  <a href="' + html.escape(TREND_FOUNDRY_JUN30_URL, quote=True) + '">TrendForce 공식 파운드리 연구</a>')
    lines.append('  <a href="' + html.escape(ECONOMIC_DAILY_URL, quote=True) + '">Economic Daily News 원보도</a>')

    for ev in new_events:
        names = ", ".join(ev["foundries"] + ev["fabless"]) or "산업 전체"
        lines += [
            "",
            "• <b>신규 구조 이벤트</b>",
            "  유형: " + html.escape(", ".join(ev["event_types"])),
            "  당사자: " + html.escape(names),
            "  제목: " + html.escape(_clean(ev["title"])),
        ]
        if ev.get("link"):
            lines.append('  <a href="' + html.escape(str(ev["link"]), quote=True) + '">근거 원문</a>')

    lines += [
        "",
        "※ TrendForce News는 TrendForce 리서치팀과 독립된 뉴스 큐레이션 페이지입니다. "
        "보도 인용 수치와 TrendForce 자체 연구수치를 같은 확정등급으로 처리하지 않습니다.",
    ]
    if semicap_events:
        if changes or new_events:
            lines += ["", "━━━━━━━━━━━━", "<b>[반도체 제조장비·교체부품 가격]</b>"]
        else:
            lines = [
                "<b>[반도체 제조장비·교체부품 가격]</b>",
                f"조회 {now.strftime('%Y-%m-%d %H:%M')} KST",
            ]
        lines += _semicap_alert_lines(semicap_events)
    ALERT_PATH.write_text("\n".join(lines).strip() + "\n", encoding="utf-8")

def main() -> None:
    items, errors = collect(dt.datetime.now(KST) - dt.timedelta(days=10))
    write_outputs(items, errors)
    print(f"foundry_passthrough_candidates={len(items)} errors={len(errors)} alert_exists={ALERT_PATH.exists()}")

if __name__ == "__main__":
    main()
