from __future__ import annotations

import copy
import html
import io
import json
import os
import pathlib
import re
import socket
import zipfile
import urllib.error
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
STATE_PATH = ROOT / "data" / "us_ai_grid_bottleneck_state.json"
PENDING_PATH = ROOT / "out" / "us_ai_grid_bottleneck_pending_state.json"
ALERT_PATH = ROOT / "out" / "us_ai_grid_bottleneck_alert.txt"
STATUS_PATH = ROOT / "out" / "us_ai_grid_bottleneck_status.md"

UA = "Mozilla/5.0 (compatible; khs-watch/1.1; +https://github.com/qedgwangju-dot/khs-watch)"


# Separate Korean FOB exports from U.S. Census importer-country data.  Reported
# article basket is not the same as the U.S. all-liquid 850421/22/23 basket.
KOREA_EXPORT_VERSION = 1
KOREA_EXPORT_FETCH_REVISION = 3
KOREA_EXPORT_HS6 = ("850422", "850423", "850434")
KOREA_EXPORT_REFERENCE = {
    "month": "2026-09",
    "status": "reported_provisional_not_officially_reconciled",
    "source_kind": "아이뉴스24 2026-10-06 보도; 머니레시피 보조 확인",
    "source_url": "https://v.daum.net/v/BM1bxtjJvW",
    "secondary_url": "https://moneyrecipe.blog/export-statistics/transformer-large/",
    "reported_scope_codes": list(KOREA_EXPORT_HS6),
    "scope_confirmed_with_customs": False,
    "monthly_usd": 278_000_000,
    "yoy_pct": 54.8,
    "mom_pct": 12.7,
    "unit_price_yoy_pct": 0.8,
    "unit_price_mom_pct": -15.8,
    "rolling_12m_usd": 2_355_000_000,
    "rolling_12m_yoy_pct": 16.4,
    "caution": (
        "850422는 650kVA 초과 10,000kVA 이하, 850423만 10,000kVA 초과 "
        "액체절연 변압기, 850434는 기타 500kVA 초과. 보도 묶음은 전부 "
        "10,000kVA 초과가 아니며 국내 기업별 매출·미국 수입통계와 동치가 아님."
    ),
}
KOREA_EXPORT_API_URL = "https://apis.data.go.kr/1220000/nitemtrade/getNitemtradeList"
KOREA_EXPORT_API_DOC = "https://www.data.go.kr/data/15100475/openapi.do"
KOREA_EXPORT_BASELINE = {
    "version": KOREA_EXPORT_VERSION,
    "reference": KOREA_EXPORT_REFERENCE,
    "baseline_notified": False,
    "official_us_by_month": {},
    "latest_official_us_month": "",
    "last_attempt_day": "",
    "last_attempt_at_kst": "",
    "fetch_revision": 0,
    "last_checked_at_kst": "",
    "last_status": "not_checked",
    "last_error_kind": "",
    "source_blocker_notified": False,
}

TRANSFORMER_IMPORT_VERSION = 1
TRANSFORMER_PRIMARY_HS6 = ("850423",)
TRANSFORMER_LIQUID_HS6 = ("850421", "850422", "850423")
TRANSFORMER_OTHER_LARGE_HS6 = ("850434",)
COUNTRY_NAMES = {
    "1220": "캐나다",
    "2010": "멕시코",
    "3510": "브라질",
    "4210": "네덜란드",
    "4280": "독일",
    "4330": "오스트리아",
    "4370": "헝가리",
    "4419": "스위스",
    "4700": "스페인",
    "4759": "이탈리아",
    "4791": "크로아티아",
    "4890": "튀르키예",
    "5330": "인도",
    "5490": "태국",
    "5520": "베트남",
    "5700": "중국",
    "5800": "한국",
    "5830": "대만",
    "5880": "일본",
}
TRANSFORMER_IMPORT_BASELINE = {
    "version": TRANSFORMER_IMPORT_VERSION,
    "source": {
        "kind": "U.S. Census Bureau Port HS6 monthly general imports",
        "layout": "https://www.census.gov/foreign-trade/reference/products/layouts/dporths6i.html",
        "data_products": "https://www.census.gov/foreign-trade/data/dataproducts.html",
        "country_codes": "https://www.census.gov/foreign-trade/schedules/c/countrycodes.html",
    },
    "scope": {
        "primary": "HS 850423 액체절연 변압기, 10,000kVA 초과",
        "liquid_total": "HS 850421~850423 액체절연 변압기 전체",
        "other_large_context": "HS 850434 기타 변압기, 500kVA 초과",
        "bps_guard": "HTS는 전압·Covered Foreign Entity 여부를 직접 식별하지 못하므로 HS 수입통계를 EO 14421 적용 물량과 동일시하지 않음",
    },
    "policy": {
        "eo": "Executive Order 14421",
        "date": "2026-08-26",
        "whitehouse": "https://www.whitehouse.gov/presidential-actions/2026/08/declaring-a-national-emergency-to-secure-the-united-states-bulk-power-system/",
        "doe": "https://www.energy.gov/ceser/declaring-national-emergency-secure-united-states-bulk-power-system-executive-order",
        "interpretation": "전면 수입금지가 아니라 DOE가 Covered Foreign Entity 연계와 국가안보 위험을 판단한 거래를 금지·제한할 수 있는 표적형 조치",
        "causality_guard": "2026-08은 8월 26일 시행 후 월말 5일뿐이므로 정책효과 월로 판정하지 않음. 2026-09 이후 연속 월별 구조 변화와 실제 DOE 조치·기업 수주를 함께 확인",
    },
    "historical_context": {
        "source_kind": "Critical Materials Atlas의 U.S. Census API 재계산치; 경향 확인용 보조자료",
        "source": "https://criticalmaterialsatlas.org/grid-trade",
        "liquid_transformers_850421_23": {
            "2020": {"china_share_pct": 2.8},
            "2021": {"china_share_pct": 0.7, "korea_share_pct": 10.0},
        },
    },
    "latest_month": "",
    "history": {},
    "last_checked_at_kst": "",
    "last_error": "",
}

BASELINE = {
    "as_of": "2026-09-27",
    "metrics": {
        "dc_electricity_2024_twh": 192.0,
        "dc_electricity_2030_twh": 649.0,
        "dc_electricity_2030_low_twh": 521.0,
        "dc_electricity_2030_high_twh": 843.0,
        "dc_share_2030_pct": 11.8,
        "transformer_avg_lead_weeks": 120.0,
        "large_transformer_low_weeks": 80.0,
        "large_transformer_high_weeks": 210.0,
        "queue_projects": 8200.0,
        "queue_gw": 2060.0,
        "transmission_345kv_plus_miles_2024": 888.0,
        "bushing_lead_low_weeks_secondary": 135.0,
        "bushing_lead_high_weeks_secondary": 145.0,
        "ms_it_power_2025_gw": 9.19,
        "ms_it_power_2026_gw": 17.96,
        "ms_it_power_2027_gw": 35.46,
        "ms_it_power_2028_gw": 52.31,
        "ms_it_power_2029_gw": 78.57,
        "ms_new_power_need_2026_2028_gw": 97.0,
        "ms_under_construction_gw": 21.0,
        "ms_grid_available_gw": 19.0,
        "ms_gross_gap_gw": 57.0,
        "ms_mitigation_gw": 24.0,
        "ms_residual_gap_gw": 33.0,
        "cw_padmount_transformer_low_weeks": 68.0,
        "cw_padmount_transformer_high_weeks": 113.0,
        "cw_generator_low_weeks": 60.0,
        "cw_generator_high_weeks": 100.0,
        "cw_mv_switchgear_low_weeks": 38.0,
        "cw_mv_switchgear_high_weeks": 63.0,
        "cw_lv_switchgear_low_weeks": 36.0,
        "cw_lv_switchgear_high_weeks": 60.0,
        "cw_ups_low_weeks": 36.0,
        "cw_ups_high_weeks": 42.0,
    },
    "sources": {
        "dc_demand": {
            "url": "https://escholarship.org/uc/item/33m6w3x0",
            "kind": "Lawrence Berkeley National Laboratory 공식 보고서",
        },
        "queue": {
            "url": "https://emp.lbl.gov/queues",
            "kind": "Lawrence Berkeley National Laboratory 공식",
        },
        "transformer": {
            "url": "https://www.nerc.com/globalassets/programs/rapa/ra/nerc_sra_2025.pdf",
            "kind": "NERC 2025 Summer Reliability Assessment",
        },
        "transmission": {
            "url": "https://www.cleanenergygrid.org/new-report-reveals-u-s-transmission-buildout-lagging-far-behind-national-needs/",
            "kind": "ACEG/Grid Strategies 공개자료",
        },
        "bushing": {
            "url": "",
            "kind": "사용자 제공 2차 기준선·공식 원천 확인 전",
        },
        "cw_equipment_2026": {
            "url": "https://www.cushmanwakefield.com/en/united-states/insights/data-center-development-cost-guide",
            "kind": "Cushman & Wakefield 2026 Data Center Development Cost Guide / 사용자 제공 현대차증권 도표 교차기준",
        },
        "jll_equipment_2026": {
            "url": "https://www.jll.com/content/dam/jllcom/en/global/documents/reports/research-reports/26-research-global-data-center-outlook-new.pdf",
            "kind": "JLL 2026 Global Data Center Outlook 교차검증",
        },
    },
    "seen_urls": [],
    "last_checked_at_kst": "",
}

SEARCHES = [
    ("google", 'site:lbl.gov OR site:escholarship.org "data center" 2030 649 TWh electricity'),
    ("google", 'site:emp.lbl.gov queues 2025 interconnection 8200 2060 GW'),
    ("google", 'site:nerc.com transformer lead times 120 weeks 80 210'),
    ("google", 'site:energy.gov large power transformer lead time 36 60 months'),
    ("google", '"power transformer" lead time data center 2026 Reuters'),
    ("google", '"generator step-up" transformer lead time 2026'),
    ("google", '"transformer bushing" lead time weeks 2026 high voltage'),
    ("google", 'site:cushmanwakefield.com 2026 data center transformer generator switchgear UPS lead time'),
    ("google", 'site:jll.com 2026 data center equipment lead time transformer generator switchgear UPS PDU chiller'),
    ("google", '"medium voltage switchgear" "lead time" data center 2026'),
    ("google", '"low voltage switchgear" "lead time" data center 2026'),
    ("google", '"UPS" "lead time" data center 2026'),
    ("google", '"data center" generator lead time 2026 Caterpillar Cummins Rolls-Royce'),
    ("google", 'site:eaton.com 2026 data center switchgear factory production'),
    ("google", 'site:se.com 2026 data center switchgear supply capacity agreement'),
    ("google", '"345 kV" transmission miles 2026 United States'),
    ("google", 'site:ferc.gov data center large load interconnection transmission 2026'),
    ("google", 'site:nerc.com large load data center reliability guideline 2026'),
    ("google", 'site:pjm.com data center large load interconnection 2026'),
    ("google", 'site:misoenergy.org large load data center interconnection 2026'),
    ("google", 'site:ercot.com large load data center interconnection 2026'),
    ("google", 'site:whitehouse.gov "bulk-power system" transformer "Executive Order 14421"'),
    ("google", 'site:energy.gov "bulk-power system" transformer "Covered Foreign Entity"'),
    ("google", 'site:federalregister.gov "bulk-power system" transformer foreign equipment 2026'),
    ("google", 'Hitachi Energy transformer factory United States 2026'),
    ("google", 'GE Vernova transformer factory expansion United States 2026'),
    ("google", 'Siemens Energy transformer capacity expansion United States 2026'),
    ("google", 'LS ELECTRIC data center transformer order United States 2026'),
    ("google", 'Hyosung Heavy Industries US transformer data center 2026'),
    ("google", 'HD Hyundai Electric US transformer data center 2026'),
    ("google", '"모건스탠리" data center 78.57 GW 2029 97 GW power shortfall'),
    ("google", '"모건스탠리" data center power 57 GW 33 GW 2026 2028'),
]

OFFICIAL_DOMAINS = (
    "lbl.gov", "escholarship.org", "emp.lbl.gov", "nerc.com", "energy.gov", "ferc.gov",
    "pjm.com", "misoenergy.org", "ercot.com", "hitachienergy.com", "gevernova.com",
    "siemens-energy.com", "ls-electric.com", "hyosungheavyindustries.com",
    "hd-hyundaielectric.com", "eaton.com", "se.com", "abb.com", "vertiv.com",
    "cat.com", "cummins.com", "rolls-royce.com", "cushmanwakefield.com", "jll.com",
    "whitehouse.gov", "federalregister.gov", "commerce.gov",
    "hyosung.com", "hyundai-electric.com", "lsholdings.com",
)

TRUSTED_DOMAINS = (
    "reuters.com", "utilitydive.com", "datacenterdynamics.com", "cleanenergygrid.org",
    "woodmac.com", "spglobal.com", "bloomberg.com", "ft.com",
    "finance.yahoo.com", "investing.com", "credaily.com", "datacenterscouts.com",
)

MATERIAL_TERMS = (
    "transformer", "bushing", "transmission", "interconnection", "grid", "substation",
    "energization", "energized", "large load", "data center", "datacenter",
    "switchgear", "generator", "ups", "pdu", "power distribution", "electrical equipment",
    "bulk-power system", "covered foreign entity", "executive order 14421",
    "변압기", "부싱", "송전", "계통", "변전소", "전원", "배전반", "발전기", "무정전전원",
)


def fetch(url: str, timeout: int = 20) -> bytes:
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.read()


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
    q = urllib.parse.quote(query)
    return f"https://news.google.com/rss/search?q={q}&hl=en-US&gl=US&ceid=US:en"


def read_rss(kind: str, query: str) -> list[dict]:
    root = ET.fromstring(fetch(google_news_url(query)))
    out = []
    for item in root.findall("./channel/item"):
        title = clean_text(item.findtext("title") or "")
        link = clean_text(item.findtext("link") or "")
        desc = clean_text(item.findtext("description") or "")
        dt = parse_pubdate(clean_text(item.findtext("pubDate") or ""))
        if title and link:
            out.append({
                "kind": kind,
                "title": title,
                "link": link,
                "description": desc,
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


def direct_url(item: dict) -> str:
    return decode_google_news(item.get("link") or "")


def article_text(url: str) -> str:
    if not url:
        return ""
    try:
        return clean_text(fetch(url, timeout=18).decode("utf-8", errors="ignore"))[:36000]
    except Exception:
        return ""


def load_json(path: pathlib.Path) -> dict:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}


def write_json(path: pathlib.Path, value: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def host_of(url: str) -> str:
    return (urlparse(url).hostname or "").lower()


def source_rank(url: str) -> int:
    host = host_of(url)
    if any(host == d or host.endswith("." + d) for d in OFFICIAL_DOMAINS):
        return 3
    if any(host == d or host.endswith("." + d) for d in TRUSTED_DOMAINS):
        return 2
    return 1


def num(value: str) -> float | None:
    try:
        return float(str(value).replace(",", ""))
    except Exception:
        return None


def parse_metrics(text: str) -> dict:
    low = text.lower()
    out: dict[str, float] = {}

    m = re.search(r"2030[^.]{0,180}?(\d{3})\s*TWh", text, re.I)
    if m and "data center" in low:
        v = num(m.group(1))
        if v and 300 <= v <= 1200:
            out["dc_electricity_2030_twh"] = v

    m = re.search(r"(\d{1,2}(?:\.\d+)?)\s*%[^.]{0,100}?(?:U\.?S\.?\s+electricity|total.*electricity)", text, re.I)
    if m and "2030" in text and "data center" in low:
        v = num(m.group(1))
        if v and 5 <= v <= 30:
            out["dc_share_2030_pct"] = v

    m = re.search(r"(?:lead times? for transformers|transformer lead times?)[^.]{0,140}?(?:averag(?:e|ing)|average)[^.]{0,60}?(\d{2,3})\s*weeks", text, re.I)
    if m:
        v = num(m.group(1))
        if v and 30 <= v <= 300:
            out["transformer_avg_lead_weeks"] = v

    m = re.search(r"large transformer lead times?[^.]{0,120}?(\d{2,3})\s*[-–]\s*(\d{2,3})\s*weeks", text, re.I)
    if m:
        lo, hi = num(m.group(1)), num(m.group(2))
        if lo and hi and 30 <= lo < hi <= 400:
            out["large_transformer_low_weeks"] = lo
            out["large_transformer_high_weeks"] = hi

    m = re.search(r"(?:GSU|generator step[- ]up)[^.]{0,150}?(\d{2,3})\s*weeks", text, re.I)
    if m:
        v = num(m.group(1))
        if v and 40 <= v <= 350:
            out["gsu_lead_weeks"] = v

    m = re.search(r"(?:bushing|bushings)[^.]{0,140}?(\d{2,3})\s*[-–]\s*(\d{2,3})\s*weeks", text, re.I)
    if m:
        lo, hi = num(m.group(1)), num(m.group(2))
        if lo and hi and 20 <= lo < hi <= 350:
            out["bushing_lead_low_weeks_secondary"] = lo
            out["bushing_lead_high_weeks_secondary"] = hi

    equipment_patterns = {
        "cw_padmount_transformer": [
            r"pad[- ]mounted transformers?[^.]{0,120}?(\d{2,3})\s*(?:to|[-–])\s*(\d{2,3})\s*weeks",
        ],
        "cw_generator": [
            r"generators?[^.]{0,120}?(\d{2,3})\s*(?:to|[-–])\s*(\d{2,3})\s*weeks",
        ],
        "cw_mv_switchgear": [
            r"(?:medium[- ]voltage|MV) switchgear[^.]{0,120}?(\d{2,3})\s*(?:to|[-–])\s*(\d{2,3})\s*weeks",
        ],
        "cw_lv_switchgear": [
            r"(?:low[- ]voltage|LV) switchgear[^.]{0,120}?(\d{2,3})\s*(?:to|[-–])\s*(\d{2,3})\s*weeks",
        ],
        "cw_ups": [
            r"(?:UPS systems?|uninterruptible power supplies?)[^.]{0,120}?(\d{2,3})\s*(?:to|[-–])\s*(\d{2,3})\s*weeks",
        ],
    }
    for prefix, patterns in equipment_patterns.items():
        for pat in patterns:
            m = re.search(pat, text, re.I)
            if not m:
                continue
            lo, hi = num(m.group(1)), num(m.group(2))
            if lo and hi and 4 <= lo < hi <= 180:
                out[prefix + "_low_weeks"] = lo
                out[prefix + "_high_weeks"] = hi
                break

    if "interconnection" in low or "queue" in low:
        m = re.search(r"(?:about|approximately|roughly)?\s*([0-9,]{4,6})\s+(?:projects|active projects)", text, re.I)
        if m:
            v = num(m.group(1))
            if v and 1000 <= v <= 50000:
                out["queue_projects"] = v
        m = re.search(r"([0-9,]{3,5}(?:\.\d+)?)\s*GW", text, re.I)
        if m:
            v = num(m.group(1))
            if v and 500 <= v <= 10000:
                out["queue_gw"] = v

    if "345" in text and ("mile" in low or "transmission" in low):
        m = re.search(r"(\d{2,4}(?:,\d{3})?)\s*(?:miles?|mi)[^.]{0,100}?(?:345\s*kV|345-kV|345 kV)", text, re.I)
        if not m:
            m = re.search(r"(?:345\s*kV|345-kV|345 kV)[^.]{0,100}?(\d{2,4}(?:,\d{3})?)\s*(?:miles?|mi)", text, re.I)
        if m:
            v = num(m.group(1))
            if v and 50 <= v <= 5000:
                out["transmission_345kv_plus_miles_latest"] = v

    if "morgan stanley" in low and ("data center" in low or "datacenter" in low):
        year_patterns = {
            2025: "ms_it_power_2025_gw",
            2026: "ms_it_power_2026_gw",
            2027: "ms_it_power_2027_gw",
            2028: "ms_it_power_2028_gw",
            2029: "ms_it_power_2029_gw",
        }
        for year, key_name in year_patterns.items():
            m = re.search(rf"{year}[^.]{{0,120}}?([0-9]{{1,3}}(?:\.[0-9]+)?)\s*GW", text, re.I)
            if not m:
                m = re.search(rf"([0-9]{{1,3}}(?:\.[0-9]+)?)\s*GW[^.]{{0,120}}?{year}", text, re.I)
            if m:
                v = num(m.group(1))
                if v and 0.1 <= v <= 200:
                    out[key_name] = v

        semantic_patterns = [
            (
                "ms_new_power_need_2026_2028_gw",
                [
                    r"(?:2026\s*(?:to|through|[-–])\s*2028|2026[^.]{0,40}2028)[^.]{0,180}?([0-9]{1,3}(?:\.[0-9]+)?)\s*GW[^.]{0,100}?(?:power|electricity|demand|require|need)",
                    r"(?:require|need|demand)[^.]{0,120}?([0-9]{1,3}(?:\.[0-9]+)?)\s*GW[^.]{0,120}?(?:2026\s*(?:to|through|[-–])\s*2028|2026[^.]{0,40}2028)",
                ],
                40, 160,
            ),
            (
                "ms_under_construction_gw",
                [
                    r"([0-9]{1,3}(?:\.[0-9]+)?)\s*GW[^.]{0,100}?(?:under construction|being built|construction)",
                    r"(?:under construction|being built|construction)[^.]{0,100}?([0-9]{1,3}(?:\.[0-9]+)?)\s*GW",
                ],
                5, 80,
            ),
            (
                "ms_grid_available_gw",
                [
                    r"([0-9]{1,3}(?:\.[0-9]+)?)\s*GW[^.]{0,120}?(?:grid capacity|grid.*available|available.*grid)",
                    r"(?:grid capacity|grid.*available|available.*grid)[^.]{0,120}?([0-9]{1,3}(?:\.[0-9]+)?)\s*GW",
                ],
                5, 80,
            ),
            (
                "ms_gross_gap_gw",
                [
                    r"([0-9]{1,3}(?:\.[0-9]+)?)\s*GW[^.]{0,120}?(?:initial|potential)?\s*(?:gap|shortfall|deficit)",
                    r"(?:initial|potential)?\s*(?:gap|shortfall|deficit)[^.]{0,120}?([0-9]{1,3}(?:\.[0-9]+)?)\s*GW",
                ],
                10, 120,
            ),
            (
                "ms_residual_gap_gw",
                [
                    r"([0-9]{1,3}(?:\.[0-9]+)?)\s*GW[^.]{0,120}?(?:residual|remaining)[^.]{0,50}?(?:gap|shortfall|deficit)",
                    r"(?:residual|remaining)[^.]{0,80}?(?:gap|shortfall|deficit)[^.]{0,120}?([0-9]{1,3}(?:\.[0-9]+)?)\s*GW",
                ],
                5, 100,
            ),
        ]
        for key_name, patterns, lo, hi in semantic_patterns:
            for pat in patterns:
                m = re.search(pat, text, re.I)
                if not m:
                    continue
                v = num(m.group(1))
                if v is not None and lo <= v <= hi:
                    out[key_name] = v
                    break

    return out


def pct_change(new: float, old: float) -> float:
    return (new / old - 1.0) * 100.0 if old else 0.0


def material_metric_changes(old: dict, new: dict) -> list[dict]:
    rules = {
        "dc_electricity_2030_twh": ("2030 데이터센터 전력수요", "pct", 10.0),
        "dc_share_2030_pct": ("2030 미국 전력 비중", "pp", 1.5),
        "transformer_avg_lead_weeks": ("변압기 평균 납기", "abs", 10.0),
        "large_transformer_high_weeks": ("대형변압기 최장 납기", "abs", 10.0),
        "gsu_lead_weeks": ("발전기 승압용 변압기 납기", "abs", 10.0),
        "bushing_lead_high_weeks_secondary": ("초고압 부싱 납기", "abs", 10.0),
        "cw_padmount_transformer_high_weeks": ("데이터센터 지상형 변압기 최장 납기", "abs", 8.0),
        "cw_generator_high_weeks": ("데이터센터 발전기 최장 납기", "abs", 8.0),
        "cw_mv_switchgear_high_weeks": ("데이터센터 중압배전반 최장 납기", "abs", 6.0),
        "cw_lv_switchgear_high_weeks": ("데이터센터 저압배전반 최장 납기", "abs", 6.0),
        "cw_ups_high_weeks": ("데이터센터 UPS 최장 납기", "abs", 6.0),
        "queue_projects": ("계통연결 대기 프로젝트", "pct", 10.0),
        "queue_gw": ("계통연결 대기 용량", "pct", 10.0),
        "transmission_345kv_plus_miles_latest": ("345kV+ 송전선 연간 준공", "pct", 25.0),
        "ms_it_power_2029_gw": ("모건스탠리 2029 데이터센터 IT 전력", "pct", 10.0),
        "ms_new_power_need_2026_2028_gw": ("모건스탠리 2026~2028 신규 전력 필요량", "abs", 10.0),
        "ms_gross_gap_gw": ("모건스탠리 1차 전력 부족분", "abs", 5.0),
        "ms_residual_gap_gw": ("모건스탠리 대체전원 반영 후 부족분", "abs", 5.0),
    }
    out = []
    for key, (label, mode, threshold) in rules.items():
        if key not in old or key not in new:
            continue
        before = float(old[key]); after = float(new[key])
        if mode == "pp":
            delta = after - before
        elif mode == "abs":
            delta = after - before
        else:
            delta = pct_change(after, before)
        if abs(delta) >= threshold:
            out.append({"key": key, "label": label, "mode": mode, "before": before, "after": after, "delta": delta})
    return out


def structural_event(text: str, url: str) -> str:
    low = text.lower()
    if source_rank(url) < 2:
        return ""
    if any(k in low for k in ("new factory", "new plant", "breaks ground", "expansion", "expand capacity", "capacity expansion")) and "transformer" in low:
        return "변압기 생산능력 증설·신공장 일정 변화"
    if any(k in low for k in ("production begins", "production starts", "opens new", "new factory", "new plant", "capacity expansion")) and any(k in low for k in ("switchgear", "ups", "generator")):
        return "데이터센터 전력기기 생산능력·생산개시 변화"
    if "supply capacity agreement" in low and "data center" in low and any(k in low for k in ("switchgear", "ups", "power")):
        return "데이터센터 전력기기 장기 공급능력 계약"
    if any(k in low for k in ("energization delayed", "energization delay", "power-on delayed", "utility upgrade", "energized")) and any(k in low for k in ("data center", "datacenter")):
        return "데이터센터 전원 인가 일정 변화"
    if any(k in low for k in ("large load", "data center")) and any(k in low for k in ("interconnection rule", "tariff", "queue reform", "reliability guideline", "ferc order")):
        return "대형부하·데이터센터 계통접속 규칙 변화"
    if "transmission" in low and any(k in low for k in ("approved", "construction", "in service", "energized")) and any(k in low for k in ("345 kv", "500 kv", "765 kv")):
        return "345kV+ 송전망 승인·착공·준공 변화"
    if "bulk-power system" in low and any(k in low for k in ("covered foreign entity", "prohibit", "prohibition", "restrict", "restriction", "prequalification", "vendor")):
        return "미국 BPS 외국산 전력기기 규제·공급사 심사 변화"
    if any(k in low for k in ("transformer", "power transformer", "substation transformer")) and any(k in low for k in ("contract", "order", "award", "supply agreement", "수주", "공급계약")) and any(k in low for k in ("united states", "u.s.", "north america", "미국", "북미")):
        return "북미 변압기 신규 수주·공급계약 변화"
    return ""


def format_metric(key: str, value: float) -> str:
    if key.endswith("_twh"):
        return f"{value:,.0f}TWh"
    if key.endswith("_pct"):
        return f"{value:.1f}%"
    if "weeks" in key:
        return f"{value:,.0f}주"
    if key == "queue_projects":
        return f"{value:,.0f}개"
    if key == "queue_gw":
        return f"{value:,.0f}GW"
    if "miles" in key:
        return f"{value:,.0f}마일"
    if key.endswith("_gw") or "_gw" in key:
        return f"{value:,.2f}GW" if abs(value - round(value)) > 1e-6 else f"{value:,.0f}GW"
    return f"{value:,.1f}"


def build_alert(changes: list[dict], events: list[dict], state: dict) -> str:
    m = state.get("metrics") or {}
    lines = [
        "<b>⚡ AI 데이터센터 전력기기·전원 병목 변화</b>",
        "",
        "<b>변화</b>",
    ]
    for ch in changes[:6]:
        suffix = "%p" if ch["mode"] == "pp" else ("주" if ch["mode"] == "abs" and "납기" in ch["label"] else "%")
        lines.append(
            f"• <b>{html.escape(ch['label'])}</b>: "
            f"{html.escape(format_metric(ch['key'], ch['before']))} → "
            f"{html.escape(format_metric(ch['key'], ch['after']))} "
            f"({ch['delta']:+.1f}{suffix})"
        )
    for ev in events[:4]:
        lines.append(f"• <b>구조 변화:</b> {html.escape(ev['event'])}")
        if ev.get("url"):
            lines.append(f'  <a href="{html.escape(ev["url"], quote=True)}">원문</a>')
    if not changes and not events:
        lines.append("• 의미 있는 신규 변화 없음")

    lines += [
        "",
        "<b>현재 병목</b>",
        f"• 지상형 변압기 {float(m.get('cw_padmount_transformer_low_weeks') or 0):.0f}~{float(m.get('cw_padmount_transformer_high_weeks') or 0):.0f}주"
        f" / 발전기 {float(m.get('cw_generator_low_weeks') or 0):.0f}~{float(m.get('cw_generator_high_weeks') or 0):.0f}주",
        f"• 중압배전반 {float(m.get('cw_mv_switchgear_low_weeks') or 0):.0f}~{float(m.get('cw_mv_switchgear_high_weeks') or 0):.0f}주"
        f" / 저압배전반 {float(m.get('cw_lv_switchgear_low_weeks') or 0):.0f}~{float(m.get('cw_lv_switchgear_high_weeks') or 0):.0f}주"
        f" / UPS {float(m.get('cw_ups_low_weeks') or 0):.0f}~{float(m.get('cw_ups_high_weeks') or 0):.0f}주",
        f"• 대형변압기 별도 기준 {float(m.get('large_transformer_low_weeks') or 0):.0f}~{float(m.get('large_transformer_high_weeks') or 0):.0f}주"
        f" / 계통대기 {float(m.get('queue_projects') or 0):,.0f}개·{float(m.get('queue_gw') or 0):,.0f}GW",
        "",
        "<b>의미</b>",
        "• 건물·GPU가 준비돼도 변압기→배전반→발전기→UPS→계통접속 중 가장 늦은 장비가 실제 전원 인가 시점을 결정합니다.",
        "",
        "<b>관련 기업</b>",
        "• 변압기: Hitachi Energy·GE Vernova·Siemens Energy / 효성중공업·HD현대일렉트릭·LS ELECTRIC",
        "• 배전반·UPS: Schneider Electric·Eaton·ABB·Vertiv·LS ELECTRIC",
        "• 발전기: Caterpillar·Cummins·Rolls-Royce mtu",
        "",
        "<b>다음 확인</b>",
        "• 납기 범위 변화 / 생산개시·증설 / 대형 공급계약 / 데이터센터 전원 인가일",
    ]

    urls = []
    for ev in events:
        url = str(ev.get("url") or "")
        if url and url not in urls:
            urls.append(url)
    if urls:
        lines += ["", "<b>원문</b>"]
        for url in urls[:3]:
            lines.append(f'• <a href="{html.escape(url, quote=True)}">근거 원문</a>')

    return "\n".join(lines).strip() + "\n"

def discover(now: datetime, seen_urls: set[str]) -> tuple[list[dict], list[dict]]:
    metric_obs: list[dict] = []
    events: list[dict] = []
    cutoff = now - timedelta(days=90)
    local_seen = set()
    fetch_budget = 18
    fetched = 0

    for kind, query in SEARCHES:
        try:
            items = read_rss(kind, query)
        except Exception:
            continue
        for item in items:
            url = direct_url(item)
            if not url or url in local_seen:
                continue
            local_seen.add(url)
            pub = item.get("published_at_kst") or ""
            try:
                dt = datetime.fromisoformat(pub) if pub else None
            except Exception:
                dt = None
            if dt and dt < cutoff:
                continue
            base = clean_text(f"{item.get('title','')} {item.get('description','')}")
            low = base.lower()
            if not any(term in low for term in MATERIAL_TERMS):
                continue
            if fetched >= fetch_budget:
                continue
            fetched += 1
            body = article_text(url)
            text = clean_text(f"{base} {body}")
            metrics = parse_metrics(text)
            if metrics:
                metric_obs.append({
                    "url": url, "published_at_kst": pub, "metrics": metrics,
                    "rank": source_rank(url), "title": item.get("title") or "",
                })
            if url not in seen_urls:
                ev = structural_event(text, url)
                if ev:
                    events.append({
                        "event": ev, "url": url, "published_at_kst": pub,
                        "title": item.get("title") or "", "rank": source_rank(url),
                    })

    metric_obs.sort(key=lambda x: (x["rank"], x.get("published_at_kst") or ""), reverse=True)
    events.sort(key=lambda x: (x["rank"], x.get("published_at_kst") or ""), reverse=True)
    return metric_obs, events


def merge_verified_metrics(previous: dict, observations: list[dict]) -> tuple[dict, list[str]]:
    latest = copy.deepcopy(previous)
    evidence = []
    claimed = set()
    for obs in observations:
        if obs["rank"] < 2:
            continue
        for key, value in (obs.get("metrics") or {}).items():
            if key in claimed:
                continue
            if key.startswith("bushing_") and obs["rank"] < 3:
                continue
            latest[key] = value
            claimed.add(key)
            evidence.append(obs["url"])
    return latest, list(dict.fromkeys(evidence))


def month_shift(year: int, month: int, delta: int) -> tuple[int, int]:
    total = year * 12 + (month - 1) + delta
    return total // 12, total % 12 + 1


def month_key(year: int, month: int) -> str:
    return f"{year:04d}-{month:02d}"


def census_port_hs6_zip_url(year: int, month: int) -> str:
    yy = year % 100
    return (
        f"https://www.census.gov/trade/downloads/{year}/Port/im_hs6_m/"
        f"PORTHS6MM{yy:02d}{month:02d}.ZIP"
    )


def parse_fixed_int(value: str) -> int:
    value = (value or "").strip()
    if not value:
        return 0
    return int(value)


def parse_census_port_hs6_zip(raw: bytes, year: int, month: int) -> dict:
    target = set(TRANSFORMER_LIQUID_HS6 + TRANSFORMER_OTHER_LARGE_HS6)
    totals: dict[str, dict[str, int]] = {code: {} for code in target}
    with zipfile.ZipFile(io.BytesIO(raw)) as zf:
        suffixes = (
            f"PORTHS6MM{year % 100:02d}{month:02d}.TXT",
            f"DPORTHS6I{year % 100:02d}{month:02d}.TXT",
        )
        names = [
            name for name in zf.namelist()
            if any(name.upper().endswith(sfx) for sfx in suffixes)
        ]
        if not names:
            names = [
                name for name in zf.namelist()
                if name.upper().endswith(".TXT")
                and any(k in name.upper() for k in ("PORTHS6MM", "DPORTHS6I"))
            ]
        if not names:
            raise ValueError(f"Census Port HS6 import data file not found in ZIP; names={zf.namelist()[:20]}")
        with zf.open(names[0]) as fh:
            for raw_line in fh:
                line = raw_line.decode("ascii", errors="ignore").rstrip("\r\n")
                if len(line) < 35:
                    continue
                commodity = line[0:6]
                if commodity not in target:
                    continue
                cty_code = line[6:10]
                rec_year = parse_fixed_int(line[14:18])
                rec_month = parse_fixed_int(line[18:20])
                if rec_year != year or rec_month != month:
                    continue
                value_mo = parse_fixed_int(line[20:35])
                if value_mo < 0:
                    raise ValueError("negative Census import value")
                totals[commodity][cty_code] = totals[commodity].get(cty_code, 0) + value_mo

    if not any(totals[code] for code in target):
        raise ValueError("no target transformer HS6 rows found in Census file")
    return totals


def summarize_trade_scope(totals: dict[str, dict[str, int]], codes: tuple[str, ...]) -> dict:
    by_country: dict[str, int] = {}
    for code in codes:
        for cty, value in (totals.get(code) or {}).items():
            by_country[cty] = by_country.get(cty, 0) + int(value)
    world = sum(by_country.values())
    if world <= 0:
        return {"world_usd": 0, "china_usd": 0, "korea_usd": 0, "china_share_pct": 0.0, "korea_share_pct": 0.0, "top_origins": []}
    china = by_country.get("5700", 0)
    korea = by_country.get("5800", 0)
    top = sorted(by_country.items(), key=lambda kv: kv[1], reverse=True)[:6]
    return {
        "world_usd": world,
        "china_usd": china,
        "korea_usd": korea,
        "china_share_pct": china / world * 100.0,
        "korea_share_pct": korea / world * 100.0,
        "top_origins": [
            {
                "cty_code": cty,
                "name": COUNTRY_NAMES.get(cty, f"국가코드 {cty}"),
                "usd": value,
                "share_pct": value / world * 100.0,
            }
            for cty, value in top
        ],
    }


def fetch_transformer_trade_month(year: int, month: int) -> dict:
    url = census_port_hs6_zip_url(year, month)
    raw = fetch(url, timeout=60)
    totals = parse_census_port_hs6_zip(raw, year, month)
    return {
        "month": month_key(year, month),
        "source_url": url,
        "source_kind": "U.S. Census Bureau Port HS6 monthly general imports",
        "primary_850423": summarize_trade_scope(totals, TRANSFORMER_PRIMARY_HS6),
        "liquid_850421_23": summarize_trade_scope(totals, TRANSFORMER_LIQUID_HS6),
        "other_large_850434": summarize_trade_scope(totals, TRANSFORMER_OTHER_LARGE_HS6),
    }


def trade_share_delta(current: dict, previous: dict, field: str) -> float | None:
    if not current or not previous:
        return None
    return float(current.get(field) or 0.0) - float(previous.get(field) or 0.0)


def trade_substitution_signal(current: dict, previous: dict) -> bool:
    ch = trade_share_delta(current, previous, "china_share_pct")
    kr = trade_share_delta(current, previous, "korea_share_pct")
    return ch is not None and kr is not None and ch <= -1.0 and kr >= 1.0


def transformer_policy_effect_status(latest_month: str, history: dict) -> str:
    if not latest_month:
        return "수입통계 미확보"
    if latest_month <= "2026-08":
        return "정책효과 판단 보류 — EO 14421 시행은 2026년 8월 26일이라 8월 수입과 인과관계를 단정하지 않음"
    keys = sorted(k for k in history if k >= "2026-09")
    if len(keys) >= 2:
        k1, k2 = keys[-2], keys[-1]
        y1, m1 = map(int, k1.split("-"))
        py, pm = month_shift(y1, m1, -1)
        prev0 = history.get(month_key(py, pm), {}).get("liquid_850421_23") or {}
        cur1 = history.get(k1, {}).get("liquid_850421_23") or {}
        cur2 = history.get(k2, {}).get("liquid_850421_23") or {}
        if trade_substitution_signal(cur1, prev0) and trade_substitution_signal(cur2, cur1):
            return "중국↓·한국↑ 대체 패턴이 2개월 연속 관찰됨 — 정책과 방향은 일치하지만 DOE 개별 조치·기업 수주 확인 전 인과관계는 미확정"
    return "정책 이후 수입구조 추적 중 — 최소 2개월 연속 중국↓·한국↑와 실제 DOE 조치·기업 수주를 함께 확인"


def update_transformer_import_watch(now: datetime, previous: dict) -> tuple[dict, list[dict]]:
    latest = copy.deepcopy(previous or TRANSFORMER_IMPORT_BASELINE)
    if int(latest.get("version") or 0) < TRANSFORMER_IMPORT_VERSION:
        latest = copy.deepcopy(TRANSFORMER_IMPORT_BASELINE)
    latest.setdefault("history", {})
    events: list[dict] = []
    history = latest["history"]
    prior_latest = str(latest.get("latest_month") or "")

    if prior_latest:
        y, m = map(int, prior_latest.split("-"))
        candidates = [month_shift(y, m, 1)]
    else:
        candidates = [
            month_shift(now.year, now.month, -1),
            month_shift(now.year, now.month, -2),
            month_shift(now.year, now.month, -3),
        ]

    new_month: dict | None = None
    errors = []
    pending_month = ""
    for y, m in candidates:
        key = month_key(y, m)
        if key in history:
            continue
        try:
            new_month = fetch_transformer_trade_month(y, m)
            history[key] = new_month
            latest["latest_month"] = key
            pending_month = ""
            break
        except Exception as e:
            if getattr(e, "code", None) == 404:
                pending_month = key
                continue
            errors.append(f"{key}: {type(e).__name__}: {str(e)[:180]}")

    if new_month and not prior_latest:
        cy, cm = map(int, new_month["month"].split("-"))
        for delta in (-1, -2, -12):
            y, m = month_shift(cy, cm, delta)
            key = month_key(y, m)
            if key in history:
                continue
            try:
                history[key] = fetch_transformer_trade_month(y, m)
            except Exception as e:
                errors.append(f"{key}: {type(e).__name__}")

    latest["history"] = {k: history[k] for k in sorted(history)[-18:]}
    latest["pending_month"] = pending_month
    latest["last_checked_at_kst"] = now.isoformat(timespec="seconds")
    latest["last_error"] = "; ".join(errors[-5:])

    if new_month:
        kind = "bootstrap" if not prior_latest else "monthly_release"
        events.append({"type": kind, "month": new_month["month"], "source_url": new_month["source_url"]})
    return latest, events


def usdkrw_rate() -> tuple[float | None, str]:
    try:
        raw = json.loads(fetch("https://api.frankfurter.app/latest?from=USD&to=KRW", timeout=12).decode("utf-8"))
        rate = float((raw.get("rates") or {}).get("KRW"))
        date = str(raw.get("date") or "")
        if 500 <= rate <= 3000:
            return rate, date
    except Exception:
        pass
    return None, ""


def usd_text(value: float, rate: float | None) -> str:
    usd_m = float(value) / 1_000_000.0
    if rate is None:
        return f"{usd_m:,.1f}백만달러"
    krw_eok = float(value) * rate / 100_000_000.0
    if krw_eok >= 10000:
        jo = int(krw_eok // 10000)
        rem = int(round(krw_eok - jo * 10000))
        won = f"약 {jo}조{rem:,}억원" if rem else f"약 {jo}조원"
    else:
        won = f"약 {krw_eok:,.0f}억원"
    return f"{usd_m:,.1f}백만달러({won})"


def build_transformer_import_alert(event: dict, trade_state: dict) -> str:
    history = trade_state.get("history") or {}
    key = str(event.get("month") or trade_state.get("latest_month") or "")
    current = history.get(key) or {}
    if not current:
        return ""
    y, m = map(int, key.split("-"))
    py, pm = month_shift(y, m, -1)
    yy, ym = month_shift(y, m, -12)
    prev = history.get(month_key(py, pm)) or {}
    yoy = history.get(month_key(yy, ym)) or {}
    cur_large = current.get("primary_850423") or {}
    cur_liquid = current.get("liquid_850421_23") or {}
    prev_liquid = prev.get("liquid_850421_23") or {}
    yoy_liquid = yoy.get("liquid_850421_23") or {}
    prev_large = prev.get("primary_850423") or {}
    ch_large_mom = trade_share_delta(cur_large, prev_large, "china_share_pct")
    kr_large_mom = trade_share_delta(cur_large, prev_large, "korea_share_pct")
    ch_mom = trade_share_delta(cur_liquid, prev_liquid, "china_share_pct")
    kr_mom = trade_share_delta(cur_liquid, prev_liquid, "korea_share_pct")
    ch_yoy = trade_share_delta(cur_liquid, yoy_liquid, "china_share_pct")
    kr_yoy = trade_share_delta(cur_liquid, yoy_liquid, "korea_share_pct")
    rate, rate_date = usdkrw_rate()
    top = cur_liquid.get("top_origins") or []
    top_text = " / ".join(f"{x['name']} {float(x['share_pct']):.1f}%" for x in top[:4])
    policy_status = transformer_policy_effect_status(key, history)

    lines = [
        "<b>⚡ 미국 변압기 수입구조 월간 추적 — Census 공식값</b>",
        "",
        f"• <b>기준월:</b> {key} / U.S. Census Port HS6 일반수입·원산지 기준",
        f"• <b>대형 액체절연 변압기 HS 850423:</b> 중국 {float(cur_large.get('china_share_pct') or 0):.1f}%·{usd_text(float(cur_large.get('china_usd') or 0), rate)} / 한국 {float(cur_large.get('korea_share_pct') or 0):.1f}%·{usd_text(float(cur_large.get('korea_usd') or 0), rate)}",
        f"• <b>액체절연 전체 HS 850421~850423:</b> 중국 {float(cur_liquid.get('china_share_pct') or 0):.1f}%·{usd_text(float(cur_liquid.get('china_usd') or 0), rate)} / 한국 {float(cur_liquid.get('korea_share_pct') or 0):.1f}%·{usd_text(float(cur_liquid.get('korea_usd') or 0), rate)}",
    ]
    if ch_large_mom is not None and kr_large_mom is not None:
        lines.append(f"• <b>HS 850423 전월 대비:</b> 중국 {ch_large_mom:+.1f}%p / 한국 {kr_large_mom:+.1f}%p")
    if ch_mom is not None and kr_mom is not None:
        lines.append(f"• <b>HS 850421~850423 전월 대비:</b> 중국 {ch_mom:+.1f}%p / 한국 {kr_mom:+.1f}%p")
        if ch_mom <= -1.0 and kr_mom >= 1.0:
            if ch_large_mom is not None and kr_large_mom is not None and not (ch_large_mom <= -1.0 and kr_large_mom >= 1.0):
                lines.append("• <b>현재 판정:</b> 액체절연 전체에서는 중국↓·한국↑가 보이지만, 10,000kVA 초과 HS 850423에서는 같은 대체 패턴이 확인되지 않아 ‘대형변압기 한국 대체’로 확대해석하지 않습니다.")
            else:
                lines.append("• <b>현재 판정:</b> 중국↓·한국↑ 대체 방향이 관찰됐지만 한 달 자료만으로 구조적 전환이나 정책 인과관계를 확정하지 않습니다.")
    if ch_yoy is not None and kr_yoy is not None:
        lines.append(f"• <b>전년동월 대비 점유율:</b> 중국 {ch_yoy:+.1f}%p / 한국 {kr_yoy:+.1f}%p")
    if top_text:
        lines.append(f"• <b>상위 원산지:</b> {html.escape(top_text)}")
    lines += [
        "",
        "<b>정책 판정</b>",
        f"• {html.escape(policy_status)}",
        "• EO 14421은 모든 중국산 변압기의 일괄 금지가 아닙니다. HTS 통계에는 전압·Covered Foreign Entity·DOE 개별 위험판정이 없어 수입감소를 정책효과로 자동 승격하지 않습니다.",
        "",
        "<b>한국 업체 실적 연결</b>",
        "• 중국 비중↓ + 한국 비중↑가 연속 확인되고 효성중공업·HD현대일렉트릭·LS ELECTRIC의 북미 신규수주·수주잔고·가격·가동률이 함께 증가할 때 실적 전환 신뢰도를 높입니다.",
        "",
        f'• <a href="{html.escape(str(current.get("source_url") or ""), quote=True)}">U.S. Census 원자료</a>',
        f'• <a href="{html.escape(str((trade_state.get("policy") or {}).get("whitehouse") or ""), quote=True)}">EO 14421 원문</a>',
    ]
    if rate is not None:
        lines.append(f"• 환율 기준: 1달러={rate:,.2f}원, {html.escape(rate_date or '최신 확인값')}")
    return "\n".join(lines).strip() + "\n"



def parse_korea_kcs_hs6_response(xml_bytes: bytes, hs6: str, ym: str, country: str = "US") -> dict:
    """Fail closed on bad API response, missing period, mixed six/ten-digit levels."""
    try:
        root = ET.fromstring(xml_bytes)
    except ET.ParseError as exc:
        raise ValueError("kcs_invalid_xml") from exc
    code = (root.findtext(".//resultCode") or "").strip()
    if code != "00":
        raise ValueError("kcs_result_" + (code or "missing"))
    rows = []
    for item in root.findall(".//item"):
        h = (item.findtext("hsCd") or "").strip().replace(".", "")
        period = (item.findtext("year") or "").strip().replace(".", "").replace("-", "")
        cty = (item.findtext("statCd") or "").strip().upper()
        if not h.startswith(hs6) or period != ym or (cty and cty != country):
            continue
        if len(h) not in (6, 10):
            continue
        usd = int((item.findtext("expDlr") or "0").replace(",", ""))
        weight = int((item.findtext("expWgt") or "0").replace(",", ""))
        if usd < 0 or weight < 0:
            raise ValueError("negative_official_export_amount")
        rows.append((h, usd, weight))
    # Both parent HS6 totals and HSK10 child codes can appear.  Never double-count.
    six = [x for x in rows if x[0] == hs6]
    ten = [x for x in rows if len(x[0]) == 10]
    if six:
        if len(six) != 1:
            raise ValueError("ambiguous_official_hs6_duplicate")
        selected = six
    elif ten:
        ids = [x[0] for x in ten]
        if len(set(ids)) != len(ids):
            raise ValueError("ambiguous_official_hsk10_duplicate")
        selected = ten
    else:
        raise LookupError("no_official_row_for_period")
    return {
        "hs6": hs6, "month": ym[:4] + "-" + ym[4:],
        "country": country, "export_usd": sum(x[1] for x in selected),
        "net_weight_kg": sum(x[2] for x in selected),
        "level": "HS6" if six else "HSK10_SUM",
    }


def fetch_korea_kcs_hs6_month(hs6: str, ym: str, country: str = "US") -> dict:
    secret = os.environ.get("KCS_DATA_GO_SERVICE_KEY", "").strip()
    if not secret:
        raise PermissionError("kcs_service_key_missing")
    # Public Data Portal keys are sometimes stored URL-encoded.
    secret = urllib.parse.unquote(secret)
    params = {
        "serviceKey": secret, "strtYymm": ym, "endYymm": ym,
        "hsSgn": hs6, "cntyCd": country,
    }
    req = urllib.request.Request(
        KOREA_EXPORT_API_URL + "?" + urllib.parse.urlencode(params),
        headers={"User-Agent": UA},
    )
    # The URL can contain a credential; never log req.full_url or HTTPError.url.
    with urllib.request.urlopen(req, timeout=14) as result:
        payload = result.read(800_000)
    if len(payload) >= 800_000:
        raise ValueError("kcs_truncated_response")
    return parse_korea_kcs_hs6_response(payload, hs6, ym, country)


def assemble_korea_export_month(observations: list[dict], ym: str) -> dict:
    required = set(KOREA_EXPORT_HS6)
    by_code: dict[str, dict] = {}
    for row in observations:
        h = row.get("hs6")
        if h not in required or row.get("month") != ym:
            raise ValueError("kcs_wrong_scope_or_period")
        if h in by_code:
            raise ValueError("kcs_duplicate_hs")
        if row.get("country") != "US":
            raise ValueError("kcs_wrong_destination")
        by_code[h] = row
    if set(by_code) != required:
        raise ValueError("kcs_incomplete_hs_basket")
    usd = sum(by_code[h]["export_usd"] for h in required)
    kg = sum(by_code[h]["net_weight_kg"] for h in required)
    if usd <= 0 or kg <= 0:
        raise LookupError("kcs_no_complete_us_export_value_or_weight")
    return {
        "month": ym, "destination": "US",
        "source_kind": "관세청 국가·품목별 수출통계, 미국향 FOB 신고금액 및 순중량",
        "source_url": KOREA_EXPORT_API_DOC,
        "hs_codes": list(KOREA_EXPORT_HS6),
        "export_usd": usd, "net_weight_kg": kg, "average_usd_per_kg": usd / kg,
        "by_hs": {h: {"usd": by_code[h]["export_usd"], "kg": by_code[h]["net_weight_kg"]}
                  for h in sorted(required)},
    }


def korea_export_growth(current: dict, earlier: dict) -> dict | None:
    if not current or not earlier or current.get("hs_codes") != earlier.get("hs_codes"):
        return None
    if current.get("destination") != earlier.get("destination"):
        return None
    if not all(earlier.get(k, 0) > 0 and current.get(k, 0) > 0
               for k in ("export_usd", "net_weight_kg")):
        return None
    value = (current["export_usd"] / earlier["export_usd"] - 1) * 100
    weight = (current["net_weight_kg"] / earlier["net_weight_kg"] - 1) * 100
    price = (current["average_usd_per_kg"] / earlier["average_usd_per_kg"] - 1) * 100
    # Algebraic unit-value identity: 1+value=(1+weight)*(1+price).
    if abs((1 + weight / 100) * (1 + price / 100) - (1 + value / 100)) > 1e-8:
        raise ArithmeticError("kcs_unit_value_reconciliation")
    return {"value_pct": value, "weight_pct": weight, "unit_value_pct": price}


def korea_claim_implied_weight_growth(value_change: float, unit_change: float) -> float:
    if unit_change <= -100:
        raise ValueError("zero_or_negative_unit_value")
    return ((1 + value_change / 100) / (1 + unit_change / 100) - 1) * 100


def kcs_error_category(exc: Exception) -> str:
    """Only stable, credential-free error categories are written to state."""
    if isinstance(exc, urllib.error.HTTPError):
        if exc.code in (401, 403):
            return "kcs_http_access_denied"
        if exc.code in (429, 500, 502, 503, 504):
            return "kcs_http_retryable"
        return "kcs_http_error"
    if isinstance(exc, urllib.error.URLError):
        reason = getattr(exc, "reason", None)
        if isinstance(reason, socket.gaierror):
            return "kcs_dns_unavailable"
        if isinstance(reason, (socket.timeout, TimeoutError)):
            return "kcs_network_timeout"
        return "kcs_network_unavailable"
    if isinstance(exc, PermissionError):
        return "kcs_key_missing"
    if isinstance(exc, ValueError):
        error_code = str(exc)
        if error_code in ("kcs_result_20", "kcs_result_21"):
            return "kcs_service_access_denied"
        if error_code == "kcs_result_30":
            return "kcs_key_unregistered"
        if error_code == "kcs_result_31":
            return "kcs_key_expired"
        if error_code in ("kcs_result_22", "kcs_result_23"):
            return "kcs_http_retryable"
        return "kcs_invalid_response"
    if isinstance(exc, LookupError):
        return "kcs_no_official_rows"
    return "kcs_unexpected_error"


def kcs_retry_due(now: datetime, previous: dict, key_available: bool, force: bool = False) -> bool:
    if not key_available:
        return previous.get("last_status") != "kcs_key_missing"
    if force:
        return True
    if previous.get("fetch_revision") != KOREA_EXPORT_FETCH_REVISION:
        return True
    if previous.get("last_status") == "kcs_key_missing":
        return True
    if previous.get("last_attempt_day") != now.strftime("%Y-%m-%d"):
        return True
    if previous.get("last_error_kind") not in (
        "kcs_dns_unavailable", "kcs_network_timeout", "kcs_network_unavailable",
        "kcs_http_retryable",
    ):
        return False
    try:
        past = datetime.fromisoformat(str(previous["last_attempt_at_kst"]))
        return (now - past).total_seconds() >= 90 * 60
    except (ValueError, KeyError, TypeError):
        return True


def record_kcs_connection_recovery(now: datetime, latest: dict, events: list[dict]) -> None:
    """A verified prior month proves API access, even if the latest month has no rows."""
    if latest.get("last_status") not in ("verified", "month_unpublished"):
        return
    history = latest.get("official_us_by_month") or {}
    if not history:
        return
    if not latest.get("source_blocker_notified"):
        return
    latest["source_blocker_notified"] = False
    if latest.get("connection_restored_notified"):
        return
    try:
        fetched_at = datetime.fromisoformat(str(latest.get("last_attempt_at_kst") or ""))
        recent = 0 <= (now - fetched_at).total_seconds() <= 24 * 3600
    except (ValueError, TypeError):
        recent = False
    if recent:
        latest["connection_restored_notified"] = True
        events.append({
            "kind": "kcs_connection_restored",
            "month": str(latest.get("latest_official_us_month") or sorted(history)[-1]),
        })


def update_korea_export_watch(now: datetime, previous: dict) -> tuple[dict, list[dict]]:
    latest = copy.deepcopy(previous) if int(previous.get("version") or 0) >= KOREA_EXPORT_VERSION else copy.deepcopy(KOREA_EXPORT_BASELINE)
    latest.setdefault("official_us_by_month", {})
    events = []
    if not latest.get("baseline_notified"):
        events.append({"kind": "article_reference", "month": "2026-09"})
        latest["baseline_notified"] = True

    today = now.strftime("%Y-%m-%d")
    key_available = bool(os.environ.get("KCS_DATA_GO_SERVICE_KEY", "").strip())
    # A deliberate GitHub Actions re-run must actually recheck credentials.
    # Ordinary scheduled/push runs still respect the daily backoff.
    attempt = os.environ.get("GITHUB_RUN_ATTEMPT", "1").strip()
    forced_by_rerun = attempt.isdecimal() and int(attempt) > 1
    if not kcs_retry_due(now, latest, key_available, force=forced_by_rerun):
        # Migration guard: a prior access-denied state is still a material
        # operator blocker even if this attempt is throttled for the same day.
        denied = {
            "kcs_http_access_denied", "kcs_service_access_denied",
            "kcs_key_unregistered", "kcs_key_expired",
        }
        if (key_available and latest.get("last_error_kind") in denied
                and not latest.get("source_blocker_notified")):
            latest["last_status"] = "kcs_access_denied"
            latest["source_blocker_notified"] = True
            latest["connection_restored_notified"] = False
            y, m = month_shift(now.year, now.month, -1)
            events.append({"kind": "kcs_access_blocker", "month": month_key(y, m)})
        record_kcs_connection_recovery(now, latest, events)
        return latest, events
    latest["last_checked_at_kst"] = now.isoformat(timespec="seconds")
    if not key_available:
        latest["last_status"] = "kcs_key_missing"
        latest["last_error_kind"] = "kcs_key_missing"
        return latest, events
    latest["last_attempt_day"] = today
    latest["last_attempt_at_kst"] = now.isoformat(timespec="seconds")
    latest["fetch_revision"] = KOREA_EXPORT_FETCH_REVISION

    y, m = month_shift(now.year, now.month, -1)
    months = [
        month_key(y, m),
        month_key(*month_shift(y, m, -1)),
        month_key(*month_shift(y, m, -12)),
    ]
    errors = []
    valid = {}
    for month in months:
        ym = month.replace("-", "")
        observations = []
        for code in KOREA_EXPORT_HS6:
            try:
                observations.append(fetch_korea_kcs_hs6_month(code, ym))
            except Exception as exc:
                # Do not surface credential-bearing URL or potentially sensitive raw payloads.
                errors.append(kcs_error_category(exc))
                break
        if len(observations) != len(KOREA_EXPORT_HS6):
            continue
        try:
            snap = assemble_korea_export_month(observations, month)
            valid[month] = snap
        except (ValueError, LookupError):
            errors.append("incomplete_or_invalid_official_month")

    store = latest["official_us_by_month"]
    for month, snap in valid.items():
        before = store.get(month)
        store[month] = snap
        if month < "2026-09":
            continue  # Earlier periods are comparisons, not new news.
        if not before:
            events.append({"kind": "official_us_month", "month": month})
        elif (abs(snap["export_usd"] - before["export_usd"]) >= 1_000_000
              or abs(snap["net_weight_kg"] / before["net_weight_kg"] - 1) >= 0.01):
            events.append({"kind": "official_us_revision", "month": month})
    latest["official_us_by_month"] = {k: store[k] for k in sorted(store)[-18:]}
    if store:
        latest["latest_official_us_month"] = sorted(store)[-1]
    access_denied = {
        "kcs_http_access_denied", "kcs_service_access_denied",
        "kcs_key_unregistered", "kcs_key_expired",
    }
    if month_key(y, m) in valid:
        latest["last_status"] = "verified"
        latest["source_blocker_notified"] = False
    elif any(err in access_denied for err in errors):
        latest["last_status"] = "kcs_access_denied"
    elif "kcs_no_official_rows" in errors and len(set(errors)) == 1:
        latest["last_status"] = "month_unpublished"
    elif errors:
        latest["last_status"] = "kcs_upstream_unavailable"
    else:
        latest["last_status"] = "no_data"
    latest["last_error_kind"] = errors[0] if errors else ""
    if latest["last_status"] == "kcs_access_denied" and not previous.get("source_blocker_notified"):
        latest["source_blocker_notified"] = True
        latest["connection_restored_notified"] = False
        events.append({"kind": "kcs_access_blocker", "month": month_key(y, m)})
    record_kcs_connection_recovery(now, latest, events)
    return latest, events


def build_korea_export_alert(event: dict, data: dict, us_imports: dict) -> str:
    if event.get("kind") == "kcs_connection_restored":
        months = sorted((data.get("official_us_by_month") or {}).keys())
        verified = ", ".join(months[-3:]) if months else "없음"
        return (
            "<b>관세청 미국향 변압기 수출통계 API 연결 확인</b>\n"
            f"• 공식 조회 성공 기준월: {html.escape(verified)}. "
            "HS 850422·850423·850434의 미국향 수출금액·순중량을 실제로 받았습니다.\n"
            "• 2026년 9월 원자료는 아직 완전한 품목별 조회 결과가 없어 "
            "보도 수치를 공식 확정값으로 처리하지 않습니다.\n"
            "• 기존 2시간 간격 조회를 유지하며, 공식 월별 수치 확보 후 알립니다.\n"
            f'• <a href="{KOREA_EXPORT_API_DOC}">관세청 공식 API</a>\n'
        )
    if event.get("kind") == "kcs_access_blocker":
        return (
            "<b>한국 변압기 수출통계 검증 장애 — 접근 권한 확인 필요</b>\n"
            "• 관세청 품목별·국가별 수출입실적(GW) API에서 접근 거부 응답을 확인했습니다. "
            "기존 공공데이터 인증키는 전달되지만 이 서비스 이용 권한 또는 접속 제한이 확인되지 않습니다.\n"
            "• 필요한 조치: 공공데이터포털에서 '관세청_품목별 국가별 수출입실적(GW)' 활용신청·승인·키 등록·만료 및 서버 접근 제한을 확인하세요.\n"
            "• 미검증: 2026년 9월 미국향 HS 850422·850423·850434 실제 수출액·중량. "
            "기사의 2억7,800만 달러는 전 세계 수출 보도 수치로만 유지합니다.\n"
            "• 원자료가 확인될 때만 최초 공식 수치 알림을 전송하며, 같은 장애의 중복 알림은 차단합니다.\n"
            f'• <a href="{KOREA_EXPORT_API_DOC}">공공데이터포털 API 활용신청</a>\n'
        )
    claim = data.get("reference") or KOREA_EXPORT_REFERENCE
    rate, rate_day = usdkrw_rate()
    lines = [
        "<b>한국 중대형 변압기 수출·미국향 출하 검증</b>",
        f"• 구분: {'기사 기준선 신규 등록' if event['kind'] == 'article_reference' else '관세청 원자료 미국향 변압기 수출'}",
        "• 품목: HS 850422·850423·850434(보도 분류 기준). HS 850423은 10,000kVA 초과 액체절연 제품이며 다른 두 품목에는 중형 제품도 포함.",
    ]
    if event["kind"] == "article_reference":
        yoy_qty = korea_claim_implied_weight_growth(claim["yoy_pct"], claim["unit_price_yoy_pct"])
        mom_qty = korea_claim_implied_weight_growth(claim["mom_pct"], claim["unit_price_mom_pct"])
        lines.extend([
            f"• 2026년 9월 수출액: {usd_text(claim['monthly_usd'], rate)} / 전년동월 +{claim['yoy_pct']:.1f}% / 전월 +{claim['mom_pct']:.1f}% (기사 잠정치, 공식 HS 원자료 미대조).",
            f"• 수출단가: 전년동월 +{claim['unit_price_yoy_pct']:.1f}%, 전월 {claim['unit_price_mom_pct']:+.1f}% / 동일 분모 가정 환산 물량 변화: 전년 +{yoy_qty:.1f}%, 전월 +{mom_qty:.1f}%.",
            f"• 최근 12개월 수출액: {usd_text(claim['rolling_12m_usd'], rate)} / 증가율 +{claim['rolling_12m_yoy_pct']:.1f}% (기사 기준선).",
            "• 위 숫자는 기업별 매출, 제품 대수, 미국향 단독 실적이 아님. 공식 API 접근·품목범위가 확인되기 전까지 '공식 확정'으로 표시하지 않음.",
        ])
    month = event["month"]
    official = (data.get("official_us_by_month") or {}).get(month)
    if official and event["kind"] != "article_reference":
        lines.append(f"• 관세청 {month} 미국향 3개 HS 합계: {usd_text(official['export_usd'], rate)}, 순중량 {official['net_weight_kg']:,.0f}kg, 중량당 수출단가 {official['average_usd_per_kg']:.2f}달러/kg.")
        y, m = map(int, month.split("-"))
        history = data.get("official_us_by_month") or {}
        for delta, label in [(-1, "전월 대비"), (-12, "전년동월 대비")]:
            yy, mm = month_shift(y, m, delta)
            comparison = korea_export_growth(official, history.get(month_key(yy, mm)) or {})
            if comparison:
                lines.append(f"• {label}: 수출액 {comparison['value_pct']:+.1f}%, 순중량 {comparison['weight_pct']:+.1f}%, 단가 {comparison['unit_value_pct']:+.1f}%.")
        lines.append("• 관세청 미국향 FOB 수출과 U.S. Census 원산지 기준 수입은 도착시차·평가기준·품목범위가 달라 직접 합산·동일월 일치 판정 금지.")
    else:
        lines.append(f"• 관세청 미국향 검증상태: {html.escape(str(data.get('last_status') or '확인 전'))}; 값 확인 전 0달러로 대체하지 않음.")
    us_period = us_imports.get("latest_month") or "미확인"
    lines.extend([
        f"• 미국 원산지별 변압기 수입 최신 기준월: {us_period}. 서로 다른 기준월의 중국↓·한국↑와 한국 수출↑를 동일 사건으로 단정하지 않음.",
        "• 실적 연결: HD현대일렉트릭·효성중공업·LS ELECTRIC의 북미 수주잔고 → 실제 납품 → 검수·매출인식 → 현금회수 순으로 확인. 미국 현지공장 생산은 한국 수출에 포함되지 않음.",
        "• 실패 경로: 계약수주 증가에도 설비 증설·시험·인증 또는 검수 지연으로 출하·마진이 개선되지 않는 경우(위험 6~12개월).",
        f'• <a href="{html.escape(claim["source_url"], quote=True)}">기사 원문</a> / <a href="{KOREA_EXPORT_API_DOC}">관세청 통계 API 명세</a>',
    ])
    if rate is not None:
        lines.append(f"• 환율: 1달러={rate:,.2f}원({html.escape(rate_day)} 기준)")
    return "\n".join(lines).strip() + "\n"


def main() -> None:
    now = datetime.now(ZoneInfo("Asia/Seoul"))
    state = load_json(STATE_PATH) or copy.deepcopy(BASELINE)
    previous_metrics = copy.deepcopy(state.get("metrics") or BASELINE["metrics"])
    for k, v in BASELINE["metrics"].items():
        previous_metrics.setdefault(k, v)
    seen_urls = set(state.get("seen_urls") or [])

    observations, events = discover(now, seen_urls)
    new_metrics, evidence_urls = merge_verified_metrics(previous_metrics, observations)
    changes = material_metric_changes(previous_metrics, new_metrics)
    transformer_imports, trade_events = update_transformer_import_watch(
        now,
        state.get("transformer_imports") or {},
    )
    korean_exports, export_events = update_korea_export_watch(
        now, state.get("korea_transformer_exports") or {},
    )

    latest = copy.deepcopy(state)
    latest["metrics"] = new_metrics
    latest["transformer_imports"] = transformer_imports
    latest["korea_transformer_exports"] = korean_exports
    latest["seen_urls"] = sorted(seen_urls | {x.get("url") for x in observations + events if x.get("url")})[-300:]
    latest["last_checked_at_kst"] = now.isoformat(timespec="seconds")
    latest["metric_observation_count"] = len(observations)
    latest["event_count"] = len(events)
    latest["latest_evidence_urls"] = evidence_urls[-20:]

    write_json(PENDING_PATH, latest)

    notify = bool(changes or events or trade_events or export_events)
    if notify:
        ALERT_PATH.parent.mkdir(parents=True, exist_ok=True)
        blocks = []
        if changes or events:
            blocks.append(build_alert(changes, events, latest).strip())
        for trade_event in trade_events:
            block = build_transformer_import_alert(trade_event, transformer_imports).strip()
            if block:
                blocks.append(block)
        for export_event in export_events:
            block = build_korea_export_alert(export_event, korean_exports, transformer_imports).strip()
            if block:
                blocks.append(block)
        ALERT_PATH.write_text("\n\n".join(blocks).strip() + "\n", encoding="utf-8")
    else:
        ALERT_PATH.unlink(missing_ok=True)

    STATUS_PATH.parent.mkdir(parents=True, exist_ok=True)
    STATUS_PATH.write_text(
        "# 미국 AI 전력망 병목 감시\n\n"
        f"- 확인시각: {now.isoformat(timespec='seconds')}\n"
        f"- 지표 관측: {len(observations)}개\n"
        f"- 구조 이벤트: {len(events)}개\n"
        f"- 중요 변화: {len(changes)}개\n"
        f"- 변압기 수입 월간 이벤트: {len(trade_events)}개\n"
        f"- 변압기 최신 기준월: {transformer_imports.get('latest_month') or '확인 불가'}\n"
        f"- 다음 공개 대기월: {transformer_imports.get('pending_month') or '없음'}\n"
        f"- 변압기 원자료 오류: {transformer_imports.get('last_error') or '없음'}\n"
        f"- 한국 변압기 수출 확인상태: {korean_exports.get('last_status') or '미확인'}\n"
        f"- 한국 변압기 수출 확인월: {korean_exports.get('latest_official_us_month') or '미확인'}\n"
        f"- 한국 변압기 수출 이벤트: {len(export_events)}개\n"
        f"- 알림: {'예' if notify else '아니오'}\n",
        encoding="utf-8",
    )

    print(
        "us_ai_grid_bottleneck_watch=true "
        f"observations={len(observations)} events={len(events)} changes={len(changes)} "
        f"transformer_trade_events={len(trade_events)} transformer_latest={transformer_imports.get('latest_month') or 'none'} "
        f"korea_export_events={len(export_events)} korea_export_status={korean_exports.get('last_status') or 'none'} "
        f"notify={str(notify).lower()}"
    )


if __name__ == "__main__":
    main()
