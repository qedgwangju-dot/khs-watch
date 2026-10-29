from __future__ import annotations

import copy
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
STATE_PATH = ROOT / "data" / "rubin_hbm_watch_state.json"
PENDING_PATH = ROOT / "out" / "rubin_hbm_pending_state.json"
ALERT_PATH = ROOT / "out" / "rubin_hbm_alert.md"
UA = "Mozilla/5.0 (compatible; khs-watch/4.1; +https://github.com/qedgwangju-dot/khs-watch)"
NVIDIA_ABF_SOURCE = "https://nvidianews.nvidia.com/news/nvidia-and-supply-chain-partners-expand-capacity-to-accelerate-ai-infrastructure-buildout"
SAMSUNG_ABF_SOURCE = "https://samsungsem.com/kr/newsroom/news/view.do?id=10613"
NVIDIA_ABF_ARTICLE = "https://english.cw.com.tw/article/article.action?id=5082"


BASELINE = {
    "as_of": "2026-09-27",
    "official": {
        "ibiden_ai_server_demand_exceeds_capacity": True,
        "ibiden_sap_capacity_fy2027_multiple_min": 2.0,
        "ibiden_capex_fy2026_2028_jpy_bn": 500.0,
        "ibiden_gama_capex_jpy_bn": 220.0,
        "ibiden_gama_mass_production_start_fy": 2027,
        "ibiden_asic_share_fy2026_floor_pct": 10.0,
        "ibiden_major_cpu_customer_demand_strong": True,
        "ibiden_pricing_stance": "현 판매가격 유지 + 원재료비 고객 전가",
        "ibiden_customer_sales_fy2024_jpy_bn": {
            "Intel": 76.709,
            "AMD": 40.707,
            "NVIDIA": 75.077,
        },
    },
    "research": {
        "macquarie_intel_abf_share_pct": 30.0,
        "macquarie_amd_abf_share_pct": 15.0,
        "macquarie_nvidia_cpu_substrate_shipping": True,
        "macquarie_note": "사용자 제공 Macquarie 발췌; Ibiden 공식 확인 전",
    },
    "facts": {
        "official_nvidia_cpu_substrate_confirmed": False,
        "official_intel_abf_share_confirmed": False,
        "official_amd_abf_share_confirmed": False,
        "official_abf_price_increase_confirmed": False,
        "samsung_server_cpu_fcbga_confirmed": True,
    },
    "seen_urls": [
        "https://www.ibiden.com/company/2026/02/notice-regarding-capital-investment-plan-for-high-performance-ic-package-substrates.html",
        "https://www.ibiden.com/ir/items/en_QY20251st.pdf",
        "https://www.ibiden.com/ir/items/en_QA_FY25Q4.pdf",
        "https://www.ibiden.com/ir/items/FinancialReview2025.pdf",
        "https://www.ibiden.com/ir/items/en_kessannsetsumeiFY2025.pdf",
        "https://www.pcbshop.org/en/articles/detail.asp?serno=371",
        "https://www.xxquant.com/en/institution/institutional-research/e9049647f76459043c0fe4af2e72ff82",
        "https://www.xxquant.com/en/institution/institutional-research/312ff73397896d147f13d89219902ad7",
        "https://www.xxquant.com/en/institution/institutional-research/b7354d4184725eb0c616cb00da83d87e",
    ],
}


# The 10/21/42% series is Goldman's February 2026 vintage, not the
# October 27 2026 outlook. The September-reported 14/34/51% estimates
# are already in area_structure.research_forecast. Preserve both vintages.
ABF_VINTAGE_CONTEXT_VERSION = 1
ABF_VINTAGE_CONTEXT = {
    "version": 1,
    "article_date": "2026-10-27",
    "article_url": "https://finance.technews.tw/2026/10/27/taiwan-pcb-output-value-breaks-trillion-mark-faces-ai-challenges/",
    "original_article_full_text_access": "blocked_by_robots",
    "issuer": "Goldman Sachs",
    "old_estimate_vintage": "2026-02-03",
    "old_estimate_scope": "2026H2/2027/2028; broker estimate, not observed supply",
    "old_shortfall_pct": {"2026H2": 10.0, "2027": 21.0, "2028": 42.0},
    "old_secondary_url": "https://money.udn.com/money/story/5607/9309170",
    "recent_public_recap_as_of": "2026-09-30",
    "recent_shortfall_pct": {"2026H2": 14.0, "2027": 34.0, "2028": 51.0},
    "recent_secondary_url": "https://www.skis.com.tw/Report/industry/20260930.html",
    "source_class": "secondary_recap_of_broker_forecasts",
    "denominator_and_product_mix_not_fully_disclosed": True,
    "pcb_industry_total_is_not_abf_tam": True,
    "tpca_industry_scope_source": "https://www.cna.com.tw/news/afe/202609240233.aspx",
    "tpca_2026_taiwan_pcb_output_ntd_100m": 11365,
    "event_id": "goldman-feb-vs-sep-2026|10-21-42|14-34-51",
    "process_bottleneck_vs_grid_energization_separate": True,
}
GOLDMAN_SHORTFALL_KEYS = (
    "goldman_abf_shortfall_2h2026_pct",
    "goldman_abf_shortfall_2027_pct",
    "goldman_abf_shortfall_2028_pct",
)


# 2026-10-28 unnamed Taiwanese brokerage price-target recap is NOT a
# factory selling-price change or a signed NVIDIA supply agreement.
# Preserve independent 2026-10-27 stock-exchange material disclosure.
UNIMICRON_TARGET_CONTEXT_VERSION = 1
UNIMICRON_REFERENCE_KRW_PER_TWD = 41.434
UNIMICRON_REFERENCE_FX_DAY = "2026-10-28"
UNIMICRON_REFERENCE_FX_URL = "https://kr.investing.com/currencies/twd-krw-historical-data"
UNIMICRON_SOURCE_ARTICLE = "https://wantrich.chinatimes.com/news/20261028900159-420101"
UNIMICRON_SOURCE_CORROBORATION = "https://www.ftnn.com.tw/news/591016"
UNIMICRON_TWSE_DISCLOSURE = "https://news.cnyes.com/news/id/6638756"
UNIMICRON_TWSE_SECONDARY = "https://www.moneydj.com/kmdj/news/newsviewer.aspx?a=dd152f8a-da87-4241-b1e3-10a9546ecb0a"
UNIMICRON_TARGET_CONTEXT = {
    "version": 1,
    "company": "Unimicron Technology",
    "ticker": "3037.TW",
    "story_as_of": "2026-10-28",
    "source_url": UNIMICRON_SOURCE_ARTICLE,
    "source_kind": "2026-10-28 news recap of a broker note, not a company target or guaranteed return",
    "broker_identity": "unnamed leading Taiwanese securities research unit; cannot match UBS/Bernstein/other sell-side targets",
    "recommendation": "Buy (broker estimate)",
    "target_previous_twd": 1010,
    "target_new_twd": 1300,
    "reported_target_raise_pct_rounded": 29,
    "broker_pe_prior": 28,
    "broker_pe_current": 30,
    "broker_eps_2026_twd": 25.22,
    "broker_eps_2027_twd": 43.36,
    "q3_2026_revenue_twd_100m": 526.5,
    "q3_2026_gross_margin_pct_reported": 28.8,
    "q3_2026_margin_one_time_staff_compensation_reported": True,
    "broker_abf_hdi_sales_share_est_pct": 80,
    "broker_abf_capacity_util_pct_floor": 90,
    "broker_q4_2026_margin_forecast_pct": 31.9,
    "broker_q1_2027_margin_forecast_pct": 32.8,
    "long_lead_equipment_disclosure_as_of": "2026-10-27",
    "board_incremental_preorder_twd_100m": 509,
    "board_preorder_not_cash_paid_or_committed_customer_revenue": True,
    "preorder_funding": "own funds and bank financing",
    "preorder_scope": "new factories and process capability; not exclusively ABF/NVIDIA",
    "official_contract_price_change_confirmed": False,
    "reference_twdkrw": UNIMICRON_REFERENCE_KRW_PER_TWD,
    "reference_twdkrw_as_of": UNIMICRON_REFERENCE_FX_DAY,
    "reference_fx_url": UNIMICRON_REFERENCE_FX_URL,
    "mops_reposted_url": UNIMICRON_TWSE_DISCLOSURE,
    "mops_secondary_url": UNIMICRON_TWSE_SECONDARY,
    "independent_study_forecast_not_supply_gap_measurement": True,
}

# Structural ABF capacity baseline added from the user's 2026-10-06 follow-up.
# Keep physical/official facts separate from broker forecasts.  The 2021 and 2028
# shortage percentages are not treated as a like-for-like consensus series.
ABF_AREA_STRUCTURE_BASELINE = {
    "version": 3,
    "primary_capacity_metric": "substrate_area_x_buildup_layers_and_SAP_process_load",
    "official": {
        # Ajinomoto business briefing / integrated report: PC=1 area index and 6 ABF layers;
        # HPC=3.5 area index and 18 ABF layers, consuming more than 10x ABF in total.
        "ajinomoto_pc_substrate_area_index": 1.0,
        "ajinomoto_hpc_substrate_area_index": 3.5,
        "ajinomoto_pc_abf_layers": 6,
        "ajinomoto_hpc_abf_layers": 18,
        "ajinomoto_hpc_abf_use_multiple_min": 10.0,
        "ajinomoto_source": "https://www.ajinomoto.co.jp/company/en/ir/event/business_briefing/main/01113/teaserItems1/01/linkList/00/link/3_ICT_E.pdf",
        # Ibiden officially states that larger, multilayer substrates increase SAP load and
        # can create a shortage of SAP capacity for cutting-edge products.
        "ibiden_area_multilayer_increases_sap_load": True,
        "ibiden_cutting_edge_sap_shortage_risk_confirmed": True,
        "ibiden_ai_server_sap_load_cy2024_index": 1.0,
        "ibiden_ai_server_sap_load_cy2026_index": 1.8,
        "ibiden_ai_server_sap_load_cy2028_index": 2.5,
        "ibiden_source": "https://www.ibiden.com/ir/items/en_QA_FY2025Q3.pdf",
        "ibiden_sap_load_source": "https://www.ibiden.com/ir/items/en_kessannsetsumeiFY2025.pdf",
    },
    "historical_benchmark": {
        "year": 2021,
        "abf_shortfall_pct_min": 25.0,
        "source_kind": "DigiTimes industry-source estimate; historical benchmark, not company guidance",
        "source": "https://www.digitimes.com/news/a20210303PD200.html",
    },
    "bofa_model": {
        "issuer": "Bank of America (BofA Global Research)",
        "prior_user_chart": {
            "source_kind": "user-provided screenshot of BofA Global Research estimates; original report not directly fetched",
            "metric": "supply_demand_ratio_pct",
            "supply_demand_ratio_pct": {
                "2018": -1.0, "2019": -3.0, "2020": -8.0, "2021": -13.0,
                "2022": -10.0, "2023": 16.0, "2024": 13.0, "2025": 6.0,
                "2026": -4.0, "2027": -10.0, "2028": -16.0,
            },
            "same_chart_2021_ratio_pct": -13.0,
            "same_chart_2028_ratio_pct": -16.0,
            "same_chart_2028_shortage_minus_2021_pp": 3.0,
            "same_chart_like_for_like": True,
        },
        "current_public_recap": {
            "abf_shortfall_2026_pct": 7.0,
            "abf_shortfall_2027_pct": 14.0,
            "abf_shortfall_2028_pct": 19.0,
            "prior_abf_shortfall_2026_pct": 4.0,
            "prior_abf_shortfall_2027_pct": 10.0,
            "prior_abf_shortfall_2028_pct": 16.0,
            "revision_2026_pp": 3.0,
            "revision_2027_pp": 4.0,
            "revision_2028_pp": 3.0,
            "server_cpu_abf_demand_share_2026_pct": 17.0,
            "server_cpu_abf_demand_share_2027_pct": 21.0,
            "server_cpu_abf_demand_share_2028_pct": 21.0,
            "prior_server_cpu_abf_demand_share_2026_pct": 13.0,
            "prior_server_cpu_abf_demand_share_2027_pct": 14.0,
            "prior_server_cpu_abf_demand_share_2028_pct": 14.0,
            "source_kind": "BofA research relayed by public research summary; not original BofA report",
            "source": "https://www.xxquant.com/en/institution/institutional-research/e9049647f76459043c0fe4af2e72ff82",
        },
        "comparison_guard": {
            "prior_chart_2021_vs_2028_direct_same_chart": True,
            "current_2028_vs_2021_direct_same_chart": False,
            "note": (
                "The user-provided BofA chart directly compares 2021 -13% with prior 2028 -16%, "
                "so the 3pp deeper shortage is a valid same-chart comparison. "
                "The later 2028 19% figure comes from a newer public recap, therefore 19% vs 13% "
                "is a cross-vintage derived comparison and must not be phrased as the same-chart figure."
            ),
        },
    },
    "research_forecast": {
        # Public summaries of Goldman Sachs' Taiwan ABF research.  Keep source-specific.
        "issuer": "Goldman Sachs",
        "abf_shortfall_2h2026_pct": 14.0,
        "abf_shortfall_2027_pct": 34.0,
        "abf_shortfall_2028_pct": 51.0,
        "source_kind": "broker estimate relayed by public securities/research summaries; not industry consensus",
        "source": "https://www.skis.com.tw/Report/industry/20260930.html",
        # Meritz estimate for next-generation AI accelerator substrate area.
        "feynman_2028_area_vs_2026_min_multiple": 3.0,
        "feynman_2028_area_vs_2026_max_multiple": 5.0,
        "feynman_source_kind": "Meritz Securities estimate relayed by public news; not NVIDIA official specification",
        "feynman_source": "https://www2.edaily.co.kr/News/Read?mediaCodeNo=257&newsId=01987686645550600",
    },
    "comparison_guard": {
        "numerical_2028_minus_2021_pct_points": 26.0,
        "like_for_like_comparison_confirmed": False,
        "note": (
            "Goldman estimates 2H26/2027/2028 ABF shortfalls at 14%/34%/51%. "
            "The 2028 51% estimate is numerically above the 2021 ≥25% historical estimate, "
            "but source, product mix and model scope differ. Never phrase this as a universal/consensus fact."
        ),
    },
}

SEARCHES = [
    ("google", 'site:nvidianews.nvidia.com NVIDIA Kinsus ABF substrate official signed supply agreement'),
    ("google", 'site:samsungsem.com 삼성전기 NVIDIA FC-BGA 기판 출하 양산'),
    ("google", 'site:ibiden.com 2026 CPU customer IC package substrate SAP capacity Gama Ono pricing'),
    ("google", 'site:ibiden.com 2026 Intel AMD NVIDIA package substrate customer sales'),
    ("google", 'site:ibiden.com 2026 server CPU demand IC package substrate price operating margin'),
    ("google", 'site:unimicron.com 2026 ABF server CPU AI price increase gross margin'),
    ("google", 'site:samsungsem.com 2026 server CPU FCBGA ABF customer margin'),
    ("google", '"Macquarie" Ibiden Intel AMD NVIDIA CPU substrate 2026'),
    ("google", 'Ibiden NVIDIA CPU substrate shipment ABF 2026'),
    ("google", 'Unimicron ABF price increase server CPU 2026'),
    ("google", 'ABF substrate price increase server CPU Ibiden Unimicron 2026'),
    ("google", '"Goldman Sachs" ABF substrate 2026 14% 2027 34% 2028 51% supply gap'),
    ("google", '"BofA" ABF substrate 2026 7% 2027 14% 2028 19% shortage'),
    ("google", '"Bank of America" ABF substrate 4% 10% 16% 7% 14% 19%'),
    ("google", '"server CPU" ABF demand 17% 21% 21% BofA'),
    ("google", '"ABF substrate" Feynman 2028 area 3 5 times 2026'),
    ("google", '"ABF substrate" 2021 25% shortage 2028 supply gap'),
    ("google", 'site:ajinomoto.com OR site:ajinomoto.co.jp ABF substrate area 3.5 18 layers 10 times HPC'),
]

OFFICIAL_DOMAINS = (
    "ibiden.com", "unimicron.com", "samsungsem.com", "nvidianews.nvidia.com", "ajinomoto.com", "ajinomoto.co.jp",
)
TRUSTED_DOMAINS = (
    "reuters.com", "hankyung.com", "mt.co.kr", "biz.chosun.com", "sedaily.com",
    "etnews.com", "digitimes.com", "nikkei.com", "asia.nikkei.com", "pcbshop.org",
    "skis.com.tw", "edaily.co.kr", "newspim.com", "xxquant.com",
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
        return clean_text(fetch(url, timeout=18).decode("utf-8", errors="ignore"))[:40000]
    except Exception:
        return ""

def host_of(url: str) -> str:
    return (urlparse(url).hostname or "").lower()

def source_rank(url: str) -> int:
    host = host_of(url)
    if any(host == d or host.endswith("." + d) for d in OFFICIAL_DOMAINS):
        return 3
    if any(host == d or host.endswith("." + d) for d in TRUSTED_DOMAINS):
        return 2
    return 1

def load_json(path: pathlib.Path) -> dict:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}

def write_json(path: pathlib.Path, value: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

def number_near(text: str, labels: tuple[str, ...], unit: str = "") -> float | None:
    low = text.lower()
    for label in labels:
        pos = low.find(label.lower())
        if pos < 0:
            continue
        chunk = text[max(0, pos - 80): min(len(text), pos + 220)]
        if unit == "pct":
            m = re.search(r"(\d+(?:\.\d+)?)\s*%", chunk)
        elif unit == "jpy_bn":
            m = re.search(r"(?:JPY|¥|yen|엔)?\s*(\d+(?:\.\d+)?)\s*(?:billion|bn|십억)", chunk, re.I)
        elif unit == "multiple":
            m = re.search(r"(?:more than\s+)?(\d+(?:\.\d+)?)\s*(?:x|times|배)", chunk, re.I)
        else:
            m = re.search(r"(\d+(?:\.\d+)?)", chunk)
        if m:
            return float(m.group(1))
    return None

def parse_official_update(text: str, url: str) -> dict:
    if source_rank(url) != 3:
        return {}
    low = text.lower()
    out: dict[str, object] = {"kind": "official_update"}

    if "ibiden.com" in host_of(url):
        capex = None
        capex_patterns = [
            r"(?:FY|fiscal year)\s*2026[^.]{0,180}?(?:FY|fiscal year)\s*2028[^.]{0,180}?(?:JPY|¥)?\s*(\d+(?:\.\d+)?)\s*(?:billion|bn)",
            r"(?:invest|investment)[^.]{0,120}?(?:JPY|¥)?\s*(\d+(?:\.\d+)?)\s*(?:billion|bn)[^.]{0,120}?(?:FY|fiscal year)\s*2026[^.]{0,120}?(?:FY|fiscal year)\s*2028",
        ]
        for pat in capex_patterns:
            m = re.search(pat, text, re.I)
            if m:
                capex = float(m.group(1))
                break
        if capex is not None and 100 <= capex <= 1000:
            out["ibiden_capex_fy2026_2028_jpy_bn"] = capex

        gama = None
        for label in ("gama plant", "gama"):
            pos = low.find(label)
            if pos < 0:
                continue
            after = text[pos: min(len(text), pos + 260)]
            vals = []
            for pat in (
                r"(?:JPY|¥)\s*(\d+(?:\.\d+)?)\s*(?:billion|bn)",
                r"(\d+(?:\.\d+)?)\s*(?:billion|bn)\s*(?:yen|JPY)",
            ):
                vals.extend(re.finditer(pat, after, re.I))
            if vals:
                nearest = min(vals, key=lambda x: x.start())
                gama = float(nearest.group(1))
                break
        if gama is not None and 100 <= gama <= 500:
            out["ibiden_gama_capex_jpy_bn"] = gama

        if "fy2027" in low and "sap" in low and any(k in low for k in ("more than double", "double", "2.0")):
            out["ibiden_sap_capacity_fy2027_multiple_min"] = 2.0

        # Ibiden's official FY2025 results presentation expresses AI-server substrate
        # production load in SAP terms (CY24=1.0, CY26=1.8, CY28=2.5).
        # This is a process-load index, not unit shipments.
        sap_load = re.search(
            r"CY24\s*1\.0[^\n]{0,260}?CY26\s*(?:x\s*)?(\d+(?:\.\d+)?)"
            r"[^\n]{0,260}?CY28\s*(?:x\s*)?(\d+(?:\.\d+)?)",
            text,
            re.I,
        )
        if sap_load:
            cy26, cy28 = float(sap_load.group(1)), float(sap_load.group(2))
            if 1.0 <= cy26 <= 5.0 and 1.0 <= cy28 <= 8.0:
                out["ibiden_ai_server_sap_load_cy2024_index"] = 1.0
                out["ibiden_ai_server_sap_load_cy2026_index"] = cy26
                out["ibiden_ai_server_sap_load_cy2028_index"] = cy28

        fy = re.search(r"(?:mass production|operation)[^.]{0,100}?(?:from|in)\s+(?:fiscal year|fy)\s*(20\d{2})", text, re.I)
        if fy:
            out["ibiden_gama_mass_production_start_fy"] = int(fy.group(1))

        asic = re.search(r"ASIC[^.]{0,140}?(?:more than|over)\s*(\d+(?:\.\d+)?)\s*%", text, re.I)
        if asic:
            out["ibiden_asic_share_fy2026_floor_pct"] = float(asic.group(1))

        if "major cpu customers" in low and "strong" in low:
            out["ibiden_major_cpu_customer_demand_strong"] = True

        if any(k in low for k in ("price increase", "higher selling price", "selling prices increased", "raise prices")):
            out["official_abf_price_increase_confirmed"] = True
            out["pricing_stance"] = "가격 인상 확인"
        elif "maintaining current selling prices" in low or "maintain current selling prices" in low:
            out["pricing_stance"] = "현 판매가격 유지 + 원재료비 고객 전가"

        for sentence in re.split(r"(?<=[.!?])\s+", text):
            s = sentence.lower()
            if (
                "nvidia" in s
                and "cpu" in s
                and any(k in s for k in ("mass production", "shipment", "shipping", "supply", "started shipments", "began shipments"))
                and any(k in s for k in ("substrate", "package", "abf", "ic package"))
            ):
                out["official_nvidia_cpu_substrate_confirmed"] = True
                break

        # Official major-customer revenue values. These are company sales to the customer,
        # not "ABF revenue share"; keep the distinction explicit.
        customer_aliases = {
            "Intel": ("Intel", "Intel Corp."),
            "AMD": ("AMD", "Advanced Micro Devices"),
            "NVIDIA": ("NVIDIA", "NVIDIA Corp."),
        }
        for name, aliases in customer_aliases.items():
            for alias in aliases:
                pat = rf"{re.escape(alias)}[^0-9]{{0,80}}(?:JPY|¥)?\s*([0-9,]{{4,9}})\s*(?:million|millions)"
                m = re.search(pat, text, re.I)
                if m:
                    out.setdefault("customer_sales_jpy_bn", {})[name] = float(m.group(1).replace(",", "")) / 1000.0
                    break

        # Only accept explicit official share language.
        for name, key in (("Intel", "official_intel_abf_share_pct"), ("AMD", "official_amd_abf_share_pct")):
            pat = rf"{name}[^.]+?(\d{{1,2}}(?:\.\d+)?)\s*%[^.]*?(?:ABF|package substrate)"
            m = re.search(pat, text, re.I)
            if m:
                out[key] = float(m.group(1))

    if "unimicron.com" in host_of(url):
        price = re.search(r"(?:ABF[^.]{0,100}?)?(?:price|pricing)[^.]{0,100}?(\d+(?:\.\d+)?)\s*%", text, re.I)
        if price:
            out["unimicron_abf_price_change_pct"] = float(price.group(1))
        margin = re.search(r"(?:gross margin|operating margin)[^.]{0,80}?(\d+(?:\.\d+)?)\s*%", text, re.I)
        if margin:
            out["unimicron_margin_pct"] = float(margin.group(1))

    if "samsungsem.com" in host_of(url):
        if "server cpu" in low and "fcbga" in low and any(k in low for k in ("mass production", "supply", "sales")):
            out["samsung_server_cpu_fcbga_confirmed"] = True
        cpu_share = re.search(r"CPU[^.]{0,100}?(\d+(?:\.\d+)?)\s*%[^.]{0,80}?(?:ABF|FCBGA)", text, re.I)
        if cpu_share:
            out["samsung_cpu_abf_share_pct"] = float(cpu_share.group(1))

    return out if len(out) > 1 else {}

def parse_research_update(text: str, url: str) -> dict:
    if source_rank(url) < 2:
        return {}
    low = text.lower()
    if not any(k in low for k in ("abf", "package substrate", "fcbga")):
        return {}
    out: dict[str, object] = {"kind": "research_update"}

    if "ibiden" in low:
        intel = re.search(r"Intel[^.]{0,120}?(\d+(?:\.\d+)?)\s*%[^.]{0,100}?(?:ABF|substrate)", text, re.I)
        if not intel:
            intel = re.search(r"(?:ABF|substrate)[^.]{0,100}?Intel[^.]{0,100}?(\d+(?:\.\d+)?)\s*%", text, re.I)
        amd = re.search(r"AMD[^.]{0,120}?(\d+(?:\.\d+)?)\s*%[^.]{0,100}?(?:ABF|substrate)", text, re.I)
        if not amd:
            amd = re.search(r"(?:ABF|substrate)[^.]{0,100}?AMD[^.]{0,100}?(\d+(?:\.\d+)?)\s*%", text, re.I)
        if intel:
            out["macquarie_intel_abf_share_pct"] = float(intel.group(1))
        if amd:
            out["macquarie_amd_abf_share_pct"] = float(amd.group(1))
        if "nvidia" in low and "cpu" in low and any(k in low for k in ("shipment", "shipping", "supply", "started")):
            out["macquarie_nvidia_cpu_substrate_shipping"] = True

    if "unimicron" in low:
        price = re.search(r"ABF[^.]{0,100}?(?:price|pricing)[^.]{0,100}?(\d+(?:\.\d+)?)\s*%", text, re.I)
        if price:
            out["unimicron_abf_price_change_pct"] = float(price.group(1))
        margin = re.search(r"(?:gross margin|operating margin)[^.]{0,100}?(\d+(?:\.\d+)?)\s*%", text, re.I)
        if margin:
            out["unimicron_margin_pct"] = float(margin.group(1))

    # BofA source-specific ABF model. Keep report vintages separate.
    if any(k in low for k in ("bofa", "bank of america")):
        triplet = r"(\d{1,2}(?:\.\d+)?)\s*%\s*/\s*(\d{1,2}(?:\.\d+)?)\s*%\s*/\s*(\d{1,2}(?:\.\d+)?)\s*%"
        sentences = [x.strip() for x in re.split(r"(?<=[.!?])\s+", text) if x.strip()]

        gap_sentence = next(
            (
                x for x in sentences
                if "abf" in x.lower()
                and any(k in x.lower() for k in ("shortfall", "shortage", "supply-demand gap", "supply demand gap", "부족"))
            ),
            "",
        )
        if gap_sentence:
            triples = re.findall(triplet, gap_sentence, re.I)
            if len(triples) >= 2:
                first = tuple(float(x) for x in triples[0])
                second = tuple(float(x) for x in triples[1])
                low_chunk = gap_sentence.lower()
                if ("from" in low_chunk and " to " in low_chunk) or ("기존" in gap_sentence and "에서" in gap_sentence):
                    prior_vals, current_vals = first, second
                else:
                    current_vals, prior_vals = first, second
                for year, prior_v, current_v in zip((2026, 2027, 2028), prior_vals, current_vals):
                    out[f"bofa_prior_abf_shortfall_{year}_pct"] = prior_v
                    out[f"bofa_abf_shortfall_{year}_pct"] = current_v
            elif len(triples) == 1:
                vals = tuple(float(x) for x in triples[0])
                for year, current_v in zip((2026, 2027, 2028), vals):
                    out[f"bofa_abf_shortfall_{year}_pct"] = current_v

        cpu_sentence = next(
            (
                x for x in sentences
                if any(k in x.lower() for k in ("server cpu", "서버 cpu"))
                and "abf" in x.lower()
                and any(k in x.lower() for k in ("demand", "수요"))
            ),
            "",
        )
        if cpu_sentence:
            triples = re.findall(triplet, cpu_sentence, re.I)
            if len(triples) >= 2:
                first = tuple(float(x) for x in triples[0])
                second = tuple(float(x) for x in triples[1])
                low_chunk = cpu_sentence.lower()
                if ("from" in low_chunk and " to " in low_chunk) or ("기존" in cpu_sentence and "에서" in cpu_sentence):
                    prior_vals, current_vals = first, second
                else:
                    current_vals, prior_vals = first, second
                for year, prior_v, current_v in zip((2026, 2027, 2028), prior_vals, current_vals):
                    out[f"bofa_prior_server_cpu_abf_demand_share_{year}_pct"] = prior_v
                    out[f"bofa_server_cpu_abf_demand_share_{year}_pct"] = current_v

    # Source-specific ABF shortage model.  Do not collapse this into an industry consensus number.
    if "goldman" in low and any(k in low for k in ("shortfall", "undersupply", "supply gap", "supply-demand gap", "공급 부족", "供給缺口")):
        # Goldman September 2026 public recaps specify a 2H26 figure separately
        # from full-year 2026 estimates published by other firms. Keep that scope explicit.
        for pat in (
            # English recaps often write "14% in 2H26"; prefer this form first so
            # a later "34% in 2027" cannot be pulled backward into the 2H26 slot.
            r"(\d{1,2}(?:\.\d+)?)\s*%[^,.;]{0,35}?(?:2H\s*26|2H\s*2026|2026\s*년\s*하반기|2026年下半年)",
            r"(?:2H\s*26|2H\s*2026|2026\s*년\s*하반기|2026年下半年)[^,.;0-9%]{0,40}?(\d{1,2}(?:\.\d+)?)\s*%",
        ):
            m = re.search(pat, text, re.I)
            if m:
                value = float(m.group(1))
                if 5 <= value <= 80:
                    out["goldman_abf_shortfall_2h2026_pct"] = value
                    break

        for year, key in ((2027, "goldman_abf_shortfall_2027_pct"), (2028, "goldman_abf_shortfall_2028_pct")):
            # Bind the percentage tightly to its year.  A broad cross-year pattern can
            # incorrectly assign 2028's 51% to 2027 when both years appear in one sentence.
            patterns = (
                rf"(\d{{1,2}}(?:\.\d+)?)\s*%\s*(?:in|for)?\s*{year}\b",
                rf"{year}\s*(?:년|年)?[^0-9%]{{0,30}}?(\d{{1,2}}(?:\.\d+)?)\s*%",
                rf"(?:shortfall|undersupply|supply(?:-demand)?\s+gap|공급 부족|供給缺口)[^.;]{{0,55}}?(\d{{1,2}}(?:\.\d+)?)\s*%[^.;]{{0,25}}?{year}\b",
            )
            for pat in patterns:
                m = re.search(pat, text, re.I)
                if m:
                    value = float(m.group(1))
                    if 5 <= value <= 80:
                        out[key] = value
                        break

    if "feynman" in low and "2028" in low and any(k in low for k in ("area", "substrate", "면적", "기판")):
        m = re.search(r"(?:3\s*(?:to|[-–~])\s*5|3\s*~\s*5)\s*(?:x|times|배)", text, re.I)
        if m:
            out["feynman_2028_area_vs_2026_min_multiple"] = 3.0
            out["feynman_2028_area_vs_2026_max_multiple"] = 5.0

    return out if len(out) > 1 else {}


def parse_nvidia_abf_official(body: str, url: str) -> dict:
    """Issuer-bound proof: joint official announcements, not a news reprint."""
    h=host_of(url)
    low=clean_text(body or "").lower()
    if h=="nvidianews.nvidia.com" and url.rstrip("/")==NVIDIA_ABF_SOURCE:
        if not all(w in low for w in ("nvidia and supply chain partners expand capacity",
                                      "samsung electro-mechanics","ibiden","unimicron",
                                      "2.5x","capacity reservation agreement")):
            return {}
        return {"issuer":"nvidia","global_capacity_3yr_multiple":2.5,
                "official_substrate_suppliers":["IBIDEN","Samsung Electro-Mechanics","Unimicron"],
                "ibiden_ono_ramp_year":2028,"unimicron_start_year":2027,
                "unimicron_start_quarter":2,"unimicron_full_ramp_year":2028,
                "kinsus_in_oct21_supplier_list":False}
    if h in ("samsungsem.com","www.samsungsem.com") and url.rstrip("/")==SAMSUNG_ABF_SOURCE:
        if not all(w in low for w in ("삼성전기","엔비디아","전략적 비즈니스 파트너십",
                                      "2026년부터","다년간","세종","부산")):
            return {}
        return {"issuer":"samsung","official_multiyear_agreement":True,
                "first_supply_plan_year":2026,"sites":["세종","부산"],
                "compute_substrates":True,"network_switch_substrates":True,
                "nvidia_volume_growth_double_digit_forecast":True,
                "nvidia_2028_capacity_share_numeric":None,
                "shipments_completed_verified":False,
                "nvidia_contract_amount_krw":None,
                "customer_capex_support_exact_krw":None}
    return {}


def verify_nvidia_abf_press(reader=None) -> tuple[dict,dict]:
    reader = reader or article_text
    proofs,status={},{}
    for issuer,url in (("nvidia",NVIDIA_ABF_SOURCE),("samsung",SAMSUNG_ABF_SOURCE)):
        try:
            parsed=parse_nvidia_abf_official(reader(url),url)
            status[issuer]="verified" if parsed else "body_unverified"
            if parsed: proofs[issuer]=parsed
        except Exception as exc:
            status[issuer]="error_"+type(exc).__name__
    if len(proofs)!=2:
        return {},status
    return {"verified_by_two_issuers":True,"fact_date":"2026-10-21",
            "global_supply_capacity_3yr_multiple":2.5,"samsung_supply_plan_year":2026,
            "samsung_multiyear_signed":True,"samsung_sites":["세종","부산"],
            "compute_and_switch_fc_bga":True,
            "unimicron_capacity_reservation":True,"ibiden_capacity_reservation":True,
            "unimicron_extra_capacity_quarter":"2027Q2","unimicron_full_ramp":"2028_mid",
            "ibiden_ono_ramp":"2028Q1","samsung_2028_capacity_share":"significant_no_pct",
            "kinsus_stage":"industry_candidate_not_oct21_official_partner",
            "customer_shipments_confirmed":False,
            "nvidia_specific_contract_amount_krw":None,
            "samsung_preexisting_sejong_capex_eok_krw":42700,
            "samsung_preexisting_vietnam_capex_eok_krw":25100,
            "oct19_other_memory_substrate_contract_eok_krw":3605,
            "oct19_contract_attributed_to_nvidia":False,
            "source_urls":[NVIDIA_ABF_SOURCE,SAMSUNG_ABF_SOURCE]},status


def parse_future_nvidia_abf_milestone(body: str, url: str) -> str:
    if host_of(url) not in ("nvidianews.nvidia.com","samsungsem.com","www.samsungsem.com"):
        return ""
    for clause in re.split(r"(?<=[.!?])\s+|[。；;\r\n]+",clean_text(body or "")):
        if re.search(r"\b(?:plan|plans|will|expected|expect|target|aim)\b|계획|예정|전망|목표",clause,re.I):
            continue
        if (re.search("NVIDIA|엔비디아",clause,re.I) and re.search("Kinsus|景碩|景硕",clause,re.I)
                and re.search("ABF|FC.?BGA|substrate|기판",clause,re.I)
                and re.search("has signed|signed a.*agreement|계약.*체결",clause,re.I)):
            return "kinsus_official_contract"
        if (re.search("NVIDIA|엔비디아",clause,re.I)
                and re.search("Samsung Electro.Mechanics|삼성전기",clause,re.I)
                and re.search("ABF|FC.?BGA|substrate|기판",clause,re.I)
                and re.search("began shipping|has started shipments|began deliveries|출하.*시작|납품.*개시",clause,re.I)):
            return "samsung_actual_shipments"
    return ""


def nvidia_abf_changes(prior: dict, current: dict, future: list[str]) -> list[str]:
    changes=[]
    if current and not prior.get("verified_by_two_issuers"):
        changes.append("official_20261021")
    if current and prior.get("verified_by_two_issuers"):
        old=prior.get("global_supply_capacity_3yr_multiple")
        new=current.get("global_supply_capacity_3yr_multiple")
        if old is not None and new is not None and abs(float(new)-float(old))>=0.2:
            changes.append("global_capacity_revised")
    for event in future:
        if not (prior.get("milestones") or {}).get(event) and event not in changes:
            changes.append(event)
    return changes


def build_nvidia_abf_alert(changes: list[str], progress: dict) -> str:
    lines=["<b>삼성전기·NVIDIA ABF 기판 공식 공급계약 감시</b>","",
      "• 확정: 삼성전기·NVIDIA 2026년 10월 21일 다년 공급 파트너십. AI 연산 칩셋·네트워크 스위치용 FC-BGA/ABF 공급.",
      "• 2026년부터 공급 예정·세종/부산 전용 생산라인 추진. 실제 고객별 출하 수량·매출·계약금액은 미공개.",
      "• NVIDIA의 3년간 기판 능력 2.5배 확대는 IBIDEN·Unimicron·삼성전기를 포함한 전체 공급망 목표이며 삼성전기 단독 2.5배가 아님.",
      "• IBIDEN Ono는 2028년 1분기부터 증설, Unimicron KF는 2027년 2분기 추가 능력·2028년 중반 완전 가동 목표.",
      "• Kinsus는 공급망 진입 추진 보도. 10월 21일 공식 발표의 확정 기판 공급사 명단에 포함되지 않았음.",
      "• 과거 설비투자: 세종 4조2,700억원, 베트남 2조5,100억원. 고객 지원금과 동일 금액을 중복 합산하지 않음.",
      "• 10월 19일 3,605억원 메모리 기판 계약은 별개. 이번 NVIDIA 계약액으로 간주하지 않음.",
      "• 병목: SAP 미세회로·ABF 적층·기판 휨·수율·고온 동작 검사 및 고객 신뢰성 검증.",
      "• 다음 확인: 실제 납품·고객 검수·계약금액·생산능력·Kinsus 공식 수주·가격·마진."]
    if "global_capacity_revised" in changes:
        lines.append("• NVIDIA 공식 전체 기판 공급능력 목표 변경 확인(최신 공식자료 재검증 필요).")
    if "kinsus_official_contract" in changes:
        lines.append("• 신규 확정: Kinsus NVIDIA 기판 계약 원문 확인.")
    if "samsung_actual_shipments" in changes:
        lines.append("• 신규 확정: 삼성전기 NVIDIA 기판 실제 출하 원문 확인.")
    lines += ["",f'• <a href="{NVIDIA_ABF_SOURCE}">NVIDIA 공식 발표</a>',
              f'• <a href="{SAMSUNG_ABF_SOURCE}">삼성전기 공식 발표</a>']
    return "\n".join(lines)+"\n"



def explicit_goldman_report_vintage(text: str) -> str:
    """A fresh article publication date is NOT the cited research report date.

    Accept a firm-attributed full YYYY-MM-DD research-vintage only. This
    deliberately misses ambiguous research recaps rather than corrupting an
    already verified baseline with a recycled forecast.
    """
    clean = clean_text(text or "")
    firm = r"(?:Goldman(?:\s+Sachs)?|高盛|골드만삭스)"
    # A general "forecast" or "issued" word anywhere in the article is not
    # enough to bind its publication date to the sell-side research report.
    report = r"(?:research\s+report|research\s+note|report|研究報告|研究报告|리서치\s+보고서|리포트|보고서)"
    date = r"(?<!\d)(20\d{2})[\-/년.]\s*(\d{1,2})[\-/월.]\s*(\d{1,2})(?!\d)"
    # The report date must appear IMMEDIATELY after its named attribution
    # and a dated/issued/as-of cue, never later in a recap sentence.
    date_intro = r"\s*(?:(?:issued|dated|on|as\s+of|발간|발표)\s*)?[:：(\s]*"
    bound = re.compile(firm + r"[^.;\n]{0,90}?" + report + date_intro + date, re.I)
    for match in bound.finditer(clean):
        yy, mm, dd = [int(x) for x in match.groups()]
        try:
            return datetime(yy, mm, dd).strftime("%Y-%m-%d")
        except ValueError:
            continue
    return ""


def guard_stale_goldman_recap(item: dict) -> dict:
    """Filter out unverified Goldman 'revisions' from republished old models.

    Keep unrelated BofA, Ibiden and Nvidia evidence untouched.
    """
    updated = dict(item)
    parsed = dict(item.get("parsed") or {})
    goldman_keys = [k for k in GOLDMAN_SHORTFALL_KEYS if k in parsed]
    if not goldman_keys:
        return updated
    report_vintage = explicit_goldman_report_vintage(
        str(item.get("full_text") or item.get("title") or "")
    )
    trusted = source_rank(str(item.get("url") or "")) >= 2
    confirmed_new = trusted and report_vintage > ABF_VINTAGE_CONTEXT["recent_public_recap_as_of"]
    if not confirmed_new:
        for key in goldman_keys:
            parsed.pop(key, None)
        if len(parsed) == 1 and parsed.get("kind") == "research_update":
            parsed = {}
    else:
        parsed["goldman_report_vintage"] = report_vintage
    updated["parsed"] = parsed
    return updated


def build_abf_vintage_context_alert(state: dict) -> str:
    """One-time compact historical-model correction, separate from new forecast alerts."""
    ctx = state.get("goldman_vintage_context") or ABF_VINTAGE_CONTEXT
    old = ctx["old_shortfall_pct"]
    newer = ctx["recent_shortfall_pct"]
    parts = [f"{int(newer[period]-old[period]):+d}%p" for period in ("2026H2","2027","2028")]
    lines = [
        "<b>ABF 기판 공급부족 전망 — 구형 수치 재인용 점검</b>",
        "• <b>판정: 10%·21%·42%는 2026년 2월 Goldman Sachs 추정치</b>이며 신규 확정 통계가 아님.",
        f"• 과거: 2026 하반기 {old['2026H2']:.0f}% / 2027 {old['2027']:.0f}% / 2028 {old['2028']:.0f}%.",
        f"• 최근(9월 말 공개 재인용): {newer['2026H2']:.0f}% / {newer['2027']:.0f}% / {newer['2028']:.0f}%.",
        f"• 동일 기관의 인용 추정치 차이: {parts[0]}, {parts[1]}, {parts[2]}. 실제 확정 부족률 아님.",
        "• 분모·규격 혼합은 원 보고서 미열람으로 완전 확인되지 않아 물리적 부족수량·매출을 단정하지 않음.",
        "• 10/27 TechNews 기사 직접 본문은 접속 제한. 기사 날짜로 2월 추정치를 최신값으로 승격 금지.",
        "• 별도 산업자료: TPCA 2026 대만 PCB 제조업 생산액 전망은 ABF만의 매출·부족률이 아님.",
        "• NVIDIA 10/21 공식: IBIDEN·삼성전기·Unimicron 공급망의 기판능력 3년간 2.5배 목표.",
        "  삼성전기 세종·부산 전용라인 2026년부터 공급 계획, 실제 고객검수·매출은 별도 점검.",
        "• 공정 병목: T-glass·ABF 소재 → 적층·SAP·휨 → 검사·신뢰성·수율 → 고객 승인.",
        "  전력 병목: 계통접속·변전소·전원 인가·냉각. 기판 제약과 전력 제약은 별개.",
        "• 조기경보: 최신 리서치 버전, 2027년 기판 실출하·평균판매단가·수율·고객 승인.",
        f'• <a href="{html.escape(ctx["old_secondary_url"],quote=True)}">2월 인용 기사</a>'
        f' / <a href="{html.escape(ctx["recent_secondary_url"],quote=True)}">9월말 전망 인용</a>',
        f'• <a href="{NVIDIA_ABF_SOURCE}">NVIDIA 공식 공급망 확대</a>',
    ]
    return "\n".join(lines)



def _unimicron_twd_reference(amount: float) -> str:
    """Historic TWD→KRW reference from 2026-10-28, not a live exchange quote."""
    return f"약 {round(amount * UNIMICRON_REFERENCE_KRW_PER_TWD):,}원"


def _unimicron_capex_reference(large_twd_100m: float) -> str:
    won_eok = round(large_twd_100m * UNIMICRON_REFERENCE_KRW_PER_TWD)
    jo, rest = divmod(won_eok, 10000)
    return f"약 {jo}조{rest:,}억원" if jo else f"약 {rest:,}억원"


def unimicron_broker_notice(state: dict) -> str:
    """One factual recap per underlying analyst note and stock-exchange decision."""
    old = int(state["target_previous_twd"])
    new = int(state["target_new_twd"])
    pct = (new / old - 1) * 100
    if abs(pct - 28.7128712871) > 0.01:
        raise ValueError("unimicron_broker_target_delta_mismatch")
    if state.get("board_preorder_not_cash_paid_or_committed_customer_revenue") is not True:
        raise ValueError("unimicron_preorder_accounting_scope_not_secured")
    latest = _unimicron_twd_reference(new)
    previous = _unimicron_twd_reference(old)
    capex = _unimicron_capex_reference(state["board_incremental_preorder_twd_100m"])
    q3_sales = _unimicron_capex_reference(state["q3_2026_revenue_twd_100m"])
    lines = [
        "<b>Unimicron(3037.TW) — ABF 패키지기판 이익 전망·설비 선주문 분리 알림</b>",
        "",
        "<b>1. 증권사 전망(회사 공식 판매가격 아님)</b>",
        f"• 목표주가: <b>{old:,}대만달러({previous}) → {new:,}대만달러({latest})</b>"
        f" (정확히 +{pct:.1f}%, 기사 반올림 +29%).",
        f"• 적용 PER: {state['broker_pe_prior']}배 → {state['broker_pe_current']}배."
        " EPS 추정 상향·평가배수 상향을 함께 반영.",
        f"• 2026·2027 예상 EPS: {state['broker_eps_2026_twd']:.2f}대만달러"
        f"({_unimicron_twd_reference(state['broker_eps_2026_twd'])}) / "
        f"{state['broker_eps_2027_twd']:.2f}대만달러"
        f"({_unimicron_twd_reference(state['broker_eps_2027_twd'])}).",
        "• 인용 기사상 증권사 실명 미공개. UBS·Bernstein 등 다른 증권사 목표주가와 동일 기관 수정치로 합치지 않음.",
        "",
        "<b>2. 실제 3Q26 실적과 공시 범위</b>",
        f"• 3분기 매출 {state['q3_2026_revenue_twd_100m']:,.1f}억대만달러({q3_sales}); "
        f"매출총이익률 {state['q3_2026_gross_margin_pct_reported']:.1f}%."
        " 직원보수 일회성 반영 보도와 본업 수율·판가를 분리.",
        f"• 10/27 이사회: 장기 납기 설비 선주문 금액 <b>추가 "
        f"{state['board_incremental_preorder_twd_100m']:,.0f}억대만달러({capex})</b> 승인.",
        "  신규공장·공정능력 목적. <b>실제 지급액·ABF 전용 투자액·확정 고객매출 아님.</b>",
        "  자금 조달: 자체 자금 + 은행 융자. 실제 지급과 장비 반입·검수 시점 별도 추적.",
        "",
        "<b>3. 다음 감시·실패경로</b>",
        "• 고부가 ABF·HDI 장비 반입 → 수율·고객승인 → 실제 납품·평균판매단가·현금흐름 순으로 검증.",
        "• 6~24개월 위험: 저열팽창 유리섬유·ABF 소재·SAP·휨·고온 신뢰성 검증 지연.",
        "• 이는 10/23 CASPA 병목 발언 및 Goldman 14/34/51% 전망과 별개 증거.",
        f"• 환율 참고: 1대만달러={UNIMICRON_REFERENCE_KRW_PER_TWD:.3f}원"
        f" ({UNIMICRON_REFERENCE_FX_DAY} 종가; 현재 실시간 환율 아님).",
        f'• <a href="{UNIMICRON_SOURCE_ARTICLE}">사용자 제공 기사</a> / '
        f'<a href="{UNIMICRON_SOURCE_CORROBORATION}">교차 확인 기사</a>',
        f'• <a href="{UNIMICRON_TWSE_DISCLOSURE}">509억대만달러 공시 재게시</a>',
    ]
    return "\n".join(lines)


def unimicron_broker_update(previous: dict) -> tuple[dict, str]:
    """Send exactly one attributable baseline; do not infer future broker prices."""
    if int((previous or {}).get("version") or 0) >= UNIMICRON_TARGET_CONTEXT_VERSION:
        return previous, ""
    latest = copy.deepcopy(previous or {})
    for key, value in UNIMICRON_TARGET_CONTEXT.items():
        if key not in latest:
            latest[key] = copy.deepcopy(value)
    latest["version"] = UNIMICRON_TARGET_CONTEXT_VERSION
    return latest, unimicron_broker_notice(latest)


def material_events(previous: dict, updates: list[dict]) -> list[dict]:
    official = previous.get("official") or {}
    research = previous.get("research") or {}
    facts = previous.get("facts") or {}
    area = previous.get("area_structure") or {}
    area_research = area.get("research_forecast") or {}
    area_bofa = area.get("bofa_model") or {}
    area_bofa_current = area_bofa.get("current_public_recap") or {}
    area_official = area.get("official") or {}
    events: list[dict] = []

    for item in updates:
        u = item.get("parsed") or {}
        if not u:
            continue
        if u.get("kind") == "official_update":
            for key, threshold in (
                ("ibiden_capex_fy2026_2028_jpy_bn", 0.10),
                ("ibiden_gama_capex_jpy_bn", 0.10),
                ("ibiden_sap_capacity_fy2027_multiple_min", 0.10),
            ):
                if key in u and key in official and official[key]:
                    before, after = float(official[key]), float(u[key])
                    if abs(after / before - 1.0) >= threshold:
                        events.append({"type": "official_metric", "key": key, "before": before, "after": after, "url": item["url"]})

            if "ibiden_gama_mass_production_start_fy" in u:
                before = int(official.get("ibiden_gama_mass_production_start_fy") or 0)
                after = int(u["ibiden_gama_mass_production_start_fy"])
                if before and after != before:
                    events.append({"type": "official_metric", "key": "ibiden_gama_mass_production_start_fy", "before": before, "after": after, "url": item["url"]})

            for key in (
                "ibiden_ai_server_sap_load_cy2026_index",
                "ibiden_ai_server_sap_load_cy2028_index",
            ):
                if key in u and area_official.get(key):
                    before, after = float(area_official[key]), float(u[key])
                    if abs(after / before - 1.0) >= 0.10:
                        events.append({"type": "official_metric", "key": key, "before": before, "after": after, "url": item["url"]})

            if u.get("official_nvidia_cpu_substrate_confirmed") and not facts.get("official_nvidia_cpu_substrate_confirmed"):
                events.append({"type": "official_confirmation", "key": "official_nvidia_cpu_substrate_confirmed", "url": item["url"]})
            if u.get("official_abf_price_increase_confirmed") and not facts.get("official_abf_price_increase_confirmed"):
                events.append({"type": "official_confirmation", "key": "official_abf_price_increase_confirmed", "url": item["url"]})
            if "official_intel_abf_share_pct" in u and not facts.get("official_intel_abf_share_confirmed"):
                events.append({"type": "official_share", "key": "Intel", "value": float(u["official_intel_abf_share_pct"]), "url": item["url"]})
            if "official_amd_abf_share_pct" in u and not facts.get("official_amd_abf_share_confirmed"):
                events.append({"type": "official_share", "key": "AMD", "value": float(u["official_amd_abf_share_pct"]), "url": item["url"]})
            if u.get("samsung_server_cpu_fcbga_confirmed") and not facts.get("samsung_server_cpu_fcbga_confirmed"):
                events.append({"type": "official_confirmation", "key": "samsung_server_cpu_fcbga_confirmed", "url": item["url"]})
            if "samsung_cpu_abf_share_pct" in u:
                events.append({"type": "official_share", "key": "삼성전기 CPU향", "value": float(u["samsung_cpu_abf_share_pct"]), "url": item["url"]})
            if "unimicron_abf_price_change_pct" in u and abs(float(u["unimicron_abf_price_change_pct"])) >= 5:
                events.append({"type": "price", "key": "Unimicron ABF", "value": float(u["unimicron_abf_price_change_pct"]), "url": item["url"]})

            sales = u.get("customer_sales_jpy_bn") or {}
            old_sales = official.get("ibiden_customer_sales_fy2024_jpy_bn") or {}
            for name, after_v in sales.items():
                before_v = old_sales.get(name)
                if before_v and abs(float(after_v) / float(before_v) - 1.0) >= 0.10:
                    events.append({"type": "customer_sales", "key": name, "before": float(before_v), "after": float(after_v), "url": item["url"]})

        elif u.get("kind") == "research_update":
            for key, threshold in (
                ("macquarie_intel_abf_share_pct", 5.0),
                ("macquarie_amd_abf_share_pct", 5.0),
            ):
                if key in u and key in research:
                    before, after = float(research[key]), float(u[key])
                    if abs(after - before) >= threshold:
                        events.append({"type": "research_share", "key": key, "before": before, "after": after, "url": item["url"]})
            if "unimicron_abf_price_change_pct" in u and abs(float(u["unimicron_abf_price_change_pct"])) >= 10:
                events.append({"type": "price", "key": "Unimicron ABF(리서치)", "value": float(u["unimicron_abf_price_change_pct"]), "url": item["url"]})

            for year in (2026, 2027, 2028):
                key = f"bofa_abf_shortfall_{year}_pct"
                if key in u:
                    before = area_bofa_current.get(f"abf_shortfall_{year}_pct")
                    after = float(u[key])
                    if before is not None and abs(after - float(before)) >= 3.0:
                        events.append({"type": "bofa_supply_gap_forecast", "key": key, "before": float(before), "after": after, "url": item["url"]})
                share_key = f"bofa_server_cpu_abf_demand_share_{year}_pct"
                if share_key in u:
                    before = area_bofa_current.get(f"server_cpu_abf_demand_share_{year}_pct")
                    after = float(u[share_key])
                    if before is not None and abs(after - float(before)) >= 3.0:
                        events.append({"type": "bofa_server_cpu_share_forecast", "key": share_key, "before": float(before), "after": after, "url": item["url"]})

            for key in ("goldman_abf_shortfall_2h2026_pct", "goldman_abf_shortfall_2027_pct", "goldman_abf_shortfall_2028_pct"):
                if key in u:
                    before = area_research.get(key.replace("goldman_", ""))
                    # Stored baseline keys omit the 'goldman_' prefix.
                    if before is None:
                        before = area_research.get(key)
                    after = float(u[key])
                    if before is not None and abs(after - float(before)) >= 5.0:
                        events.append({"type": "supply_gap_forecast", "key": key, "before": float(before), "after": after, "url": item["url"]})
            if "feynman_2028_area_vs_2026_min_multiple" in u and "feynman_2028_area_vs_2026_max_multiple" in u:
                before_min = area_research.get("feynman_2028_area_vs_2026_min_multiple")
                before_max = area_research.get("feynman_2028_area_vs_2026_max_multiple")
                after_min = float(u["feynman_2028_area_vs_2026_min_multiple"])
                after_max = float(u["feynman_2028_area_vs_2026_max_multiple"])
                if before_min is not None and before_max is not None and (abs(after_min-float(before_min)) >= 0.5 or abs(after_max-float(before_max)) >= 0.5):
                    events.append({"type": "area_forecast", "key": "feynman_2028_area_vs_2026", "before": [float(before_min), float(before_max)], "after": [after_min, after_max], "url": item["url"]})

    return events

def merge_state(previous: dict, updates: list[dict], events: list[dict]) -> dict:
    latest = copy.deepcopy(previous)
    latest.setdefault("official", {})
    latest.setdefault("research", {})
    latest.setdefault("facts", {})
    latest.setdefault("area_structure", copy.deepcopy(ABF_AREA_STRUCTURE_BASELINE))
    latest.setdefault("seen_urls", [])

    for item in updates:
        u = item.get("parsed") or {}
        if u.get("kind") == "official_update":
            for key in (
                "ibiden_capex_fy2026_2028_jpy_bn", "ibiden_gama_capex_jpy_bn",
                "ibiden_sap_capacity_fy2027_multiple_min", "ibiden_gama_mass_production_start_fy",
                "ibiden_asic_share_fy2026_floor_pct", "ibiden_major_cpu_customer_demand_strong",
                "pricing_stance",
            ):
                if key in u:
                    mapped = "ibiden_pricing_stance" if key == "pricing_stance" else key
                    latest["official"][mapped] = u[key]
            if u.get("customer_sales_jpy_bn"):
                latest["official"]["ibiden_customer_sales_fy2024_jpy_bn"] = u["customer_sales_jpy_bn"]

            area_off = latest.setdefault("area_structure", copy.deepcopy(ABF_AREA_STRUCTURE_BASELINE)).setdefault("official", {})
            for key in (
                "ibiden_ai_server_sap_load_cy2024_index",
                "ibiden_ai_server_sap_load_cy2026_index",
                "ibiden_ai_server_sap_load_cy2028_index",
            ):
                if key in u:
                    area_off[key] = u[key]
            for key in (
                "official_nvidia_cpu_substrate_confirmed", "official_abf_price_increase_confirmed",
                "samsung_server_cpu_fcbga_confirmed",
            ):
                if u.get(key):
                    latest["facts"][key] = True
            if "official_intel_abf_share_pct" in u:
                latest["facts"]["official_intel_abf_share_confirmed"] = True
                latest["facts"]["official_intel_abf_share_pct"] = u["official_intel_abf_share_pct"]
            if "official_amd_abf_share_pct" in u:
                latest["facts"]["official_amd_abf_share_confirmed"] = True
                latest["facts"]["official_amd_abf_share_pct"] = u["official_amd_abf_share_pct"]
            if "unimicron_abf_price_change_pct" in u:
                latest["facts"]["unimicron_abf_price_change_pct"] = u["unimicron_abf_price_change_pct"]
            if "unimicron_margin_pct" in u:
                latest["facts"]["unimicron_margin_pct"] = u["unimicron_margin_pct"]
            if "samsung_cpu_abf_share_pct" in u:
                latest["facts"]["samsung_cpu_abf_share_pct"] = u["samsung_cpu_abf_share_pct"]
        elif u.get("kind") == "research_update":
            for key in ("macquarie_intel_abf_share_pct", "macquarie_amd_abf_share_pct", "macquarie_nvidia_cpu_substrate_shipping"):
                if key in u:
                    latest["research"][key] = u[key]
            if "unimicron_abf_price_change_pct" in u:
                latest["research"]["unimicron_abf_price_change_pct"] = u["unimicron_abf_price_change_pct"]
            if "unimicron_margin_pct" in u:
                latest["research"]["unimicron_margin_pct"] = u["unimicron_margin_pct"]
            area_latest = latest.setdefault("area_structure", copy.deepcopy(ABF_AREA_STRUCTURE_BASELINE))
            bofa_current = area_latest.setdefault("bofa_model", copy.deepcopy(ABF_AREA_STRUCTURE_BASELINE["bofa_model"])).setdefault("current_public_recap", {})
            for year in (2026, 2027, 2028):
                key = f"bofa_abf_shortfall_{year}_pct"
                if key in u:
                    bofa_current[f"abf_shortfall_{year}_pct"] = u[key]
                pkey = f"bofa_prior_abf_shortfall_{year}_pct"
                if pkey in u:
                    bofa_current[f"prior_abf_shortfall_{year}_pct"] = u[pkey]
                share_key = f"bofa_server_cpu_abf_demand_share_{year}_pct"
                if share_key in u:
                    bofa_current[f"server_cpu_abf_demand_share_{year}_pct"] = u[share_key]
                pshare_key = f"bofa_prior_server_cpu_abf_demand_share_{year}_pct"
                if pshare_key in u:
                    bofa_current[f"prior_server_cpu_abf_demand_share_{year}_pct"] = u[pshare_key]
            ar = area_latest.setdefault("research_forecast", {})
            if "goldman_abf_shortfall_2h2026_pct" in u:
                ar["abf_shortfall_2h2026_pct"] = u["goldman_abf_shortfall_2h2026_pct"]
            if "goldman_abf_shortfall_2027_pct" in u:
                ar["abf_shortfall_2027_pct"] = u["goldman_abf_shortfall_2027_pct"]
            if "goldman_abf_shortfall_2028_pct" in u:
                ar["abf_shortfall_2028_pct"] = u["goldman_abf_shortfall_2028_pct"]
            if "feynman_2028_area_vs_2026_min_multiple" in u:
                ar["feynman_2028_area_vs_2026_min_multiple"] = u["feynman_2028_area_vs_2026_min_multiple"]
            if "feynman_2028_area_vs_2026_max_multiple" in u:
                ar["feynman_2028_area_vs_2026_max_multiple"] = u["feynman_2028_area_vs_2026_max_multiple"]

    latest["seen_urls"] = sorted(set(latest["seen_urls"]) | {i["url"] for i in updates if i.get("url")})[-250:]
    return latest

def jpy_krw_rate() -> tuple[float | None, str]:
    try:
        raw = json.loads(fetch("https://api.frankfurter.app/latest?from=JPY&to=KRW", timeout=12).decode("utf-8"))
        rate = float((raw.get("rates") or {}).get("KRW"))
        date = str(raw.get("date") or "")
        if 2 < rate < 20:
            return rate, date
    except Exception:
        pass
    return None, ""

def jpy_bn_text(v: float, rate: float | None) -> str:
    eok_yen = v * 10.0
    if rate is None:
        return f"{eok_yen:,.0f}억엔"
    krw_eok = v * 1_000_000_000 * rate / 100_000_000
    if krw_eok >= 10000:
        jo = int(krw_eok // 10000)
        rem = int(round(krw_eok - jo * 10000))
        won = f"약 {jo}조{rem:,}억원" if rem else f"약 {jo}조원"
    else:
        won = f"약 {krw_eok:,.0f}억원"
    return f"{eok_yen:,.0f}억엔({won})"

def build_alert(events: list[dict], state: dict) -> str:
    off = state.get("official") or {}
    res = state.get("research") or {}
    facts = state.get("facts") or {}
    area = state.get("area_structure") or ABF_AREA_STRUCTURE_BASELINE
    area_off = area.get("official") or {}
    area_hist = area.get("historical_benchmark") or {}
    area_bofa = area.get("bofa_model") or {}
    bofa_prior = area_bofa.get("prior_user_chart") or {}
    bofa_current = area_bofa.get("current_public_recap") or {}
    bofa_guard = area_bofa.get("comparison_guard") or {}
    area_res = area.get("research_forecast") or {}
    area_guard = area.get("comparison_guard") or {}
    rate, rate_date = jpy_krw_rate()

    lines = [
        "<b>🚨 CPU·ABF 공급사 수익화 게이트 — 변화 감지</b>",
        "",
        "<b>핵심 변화</b>",
    ]
    label = {
        "ibiden_capex_fy2026_2028_jpy_bn": "Ibiden FY26~28 전자사업 설비투자",
        "ibiden_gama_capex_jpy_bn": "Ibiden Gama 투자",
        "ibiden_sap_capacity_fy2027_multiple_min": "Ibiden FY2027 SAP 생산능력",
        "ibiden_ai_server_sap_load_cy2026_index": "AI서버 기판당 SAP 공정부하 CY2026",
        "ibiden_ai_server_sap_load_cy2028_index": "AI서버 기판당 SAP 공정부하 CY2028",
        "ibiden_gama_mass_production_start_fy": "Ibiden Gama 양산개시",
    }
    for ev in events:
        t = ev["type"]
        if t == "official_metric":
            key = ev["key"]
            if "jpy_bn" in key:
                lines.append(f"• <b>{label.get(key, key)}</b>: {jpy_bn_text(ev['before'], rate)} → {jpy_bn_text(ev['after'], rate)}")
            elif "multiple" in key:
                lines.append(f"• <b>{label.get(key, key)}</b>: {ev['before']:.1f}배 → {ev['after']:.1f}배")
            else:
                lines.append(f"• <b>{label.get(key, key)}</b>: FY{int(ev['before'])} → FY{int(ev['after'])}")
        elif t == "official_confirmation":
            key = ev["key"]
            text_map = {
                "official_nvidia_cpu_substrate_confirmed": "NVIDIA CPU용 기판 출하·양산이 공식자료에서 확인",
                "official_abf_price_increase_confirmed": "ABF 가격 인상이 공식자료에서 확인",
                "samsung_server_cpu_fcbga_confirmed": "삼성전기 서버 CPU FCBGA 공급이 새 공식자료에서 재확인",
            }
            lines.append(f"• <b>공식 확인:</b> {text_map.get(key, key)}")
        elif t == "official_share":
            lines.append(f"• <b>공식 고객 비중:</b> {html.escape(str(ev['key']))} {float(ev['value']):.1f}%")
        elif t == "research_share":
            lines.append(f"• <b>리서치 추정 변경:</b> {html.escape(str(ev['key']))} {ev['before']:.1f}% → {ev['after']:.1f}%")
        elif t == "price":
            lines.append(f"• <b>가격 변화:</b> {html.escape(str(ev['key']))} {float(ev['value']):+.1f}%")
        elif t == "customer_sales":
            lines.append(f"• <b>Ibiden 고객매출:</b> {html.escape(str(ev['key']))} {jpy_bn_text(ev['before'], rate)} → {jpy_bn_text(ev['after'], rate)}")
        elif t == "area_structure_baseline":
            if str(ev.get("key") or "").endswith("v3"):
                lines.append("• <b>ABF 수급 모델 업그레이드:</b> BofA 동일지표 과거 차트와 최신 리서치 리비전을 별도 버전으로 추적합니다.")
                lines.append("• 사용자 제공 BofA 차트 안에서는 2021 -13% → 2028 -16%로 2028 부족이 3%p 더 큽니다. 최신 19% 전망은 후속 리포트라 같은 차트 직접비교로 섞지 않습니다.")
            else:
                lines.append("• <b>기판 병목 기준 업그레이드:</b> 완제품 개수보다 기판 면적×층수·SAP 공정부하를 우선 추적합니다.")
        elif t == "bofa_supply_gap_forecast":
            lines.append(f"• <b>BofA ABF 공급부족 전망 변경:</b> {html.escape(str(ev['key']))} {ev['before']:.0f}% → {ev['after']:.0f}% <i>(BofA 리서치 추정)</i>")
        elif t == "bofa_server_cpu_share_forecast":
            lines.append(f"• <b>BofA 서버 CPU ABF 수요비중 변경:</b> {html.escape(str(ev['key']))} {ev['before']:.0f}% → {ev['after']:.0f}% <i>(BofA 리서치 추정)</i>")
        elif t == "supply_gap_forecast":
            lines.append(f"• <b>ABF 공급부족 전망 변경:</b> {html.escape(str(ev['key']))} {ev['before']:.0f}% → {ev['after']:.0f}% <i>(리서치 추정)</i>")
        elif t == "area_forecast":
            lines.append(f"• <b>2028 기판 면적 전망 변경:</b> {ev['before'][0]:.1f}~{ev['before'][1]:.1f}배 → {ev['after'][0]:.1f}~{ev['after'][1]:.1f}배 <i>(리서치 추정)</i>")
        if ev.get("url"):
            lines.append(f'  <a href="{html.escape(ev["url"], quote=True)}">원문</a>')

    lines += [
        "",
        "<b>수익구조</b>",
        "• Agentic AI CPU·GPU·ASIC 증가 → 대면적·고다층 ABF의 SAP 공정 부하 증가 → 가동률·가격·제품 혼합 → 기판업체 매출·마진.",
        "• 이 게이트는 CPU 전망 자체가 아니라 그 수요가 Ibiden·Unimicron·삼성전기의 실제 가격·물량·마진으로 전환되는지를 확인합니다.",
        "",
        "<b>1단계 현재 숫자 추적</b>",
        f"• Ibiden FY26~28 전자사업 설비투자: {jpy_bn_text(float(off.get('ibiden_capex_fy2026_2028_jpy_bn') or 0), rate)}",
        f"• Gama 투자: {jpy_bn_text(float(off.get('ibiden_gama_capex_jpy_bn') or 0), rate)} / FY{int(off.get('ibiden_gama_mass_production_start_fy') or 0)}부터 순차 양산",
        f"• SAP 생산능력: FY2024 상반기말=1.0 대비 FY2027말 {float(off.get('ibiden_sap_capacity_fy2027_multiple_min') or 0):.1f}배 이상",
        f"• ASIC: FY2026 전자사업 매출의 {float(off.get('ibiden_asic_share_fy2026_floor_pct') or 0):.0f}% 초과 예상",
        f"• 면적 기준 공식 물리량: Ajinomoto HPC 기판 면적지수 {float(area_off.get('ajinomoto_hpc_substrate_area_index') or 0):.1f}배(PC=1.0), ABF 층수 {int(area_off.get('ajinomoto_pc_abf_layers') or 0)}→{int(area_off.get('ajinomoto_hpc_abf_layers') or 0)}층, 총 ABF 사용량 10배+.",
        f"• Ibiden 공식 AI서버 기판당 SAP 공정부하: CY2024 {float(area_off.get('ibiden_ai_server_sap_load_cy2024_index') or 0):.1f} → CY2026 {float(area_off.get('ibiden_ai_server_sap_load_cy2026_index') or 0):.1f} → CY2028 {float(area_off.get('ibiden_ai_server_sap_load_cy2028_index') or 0):.1f}. 기판 개수보다 면적×층수·SAP 부하가 실제 생산능력을 더 잘 설명합니다.",
        f"• BofA 사용자 제공 동일 차트: 공급/수요 비율 2021 {float(bofa_prior.get('same_chart_2021_ratio_pct') or 0):.0f}% → 2028 {float(bofa_prior.get('same_chart_2028_ratio_pct') or 0):.0f}%. 같은 차트 안에서는 2028 부족이 {float(bofa_prior.get('same_chart_2028_shortage_minus_2021_pp') or 0):.0f}%p 더 큽니다.",
        f"• BofA 후속 공개 리서치 요약: 2026/2027/2028 ABF 공급부족 {float(bofa_current.get('prior_abf_shortfall_2026_pct') or 0):.0f}%/{float(bofa_current.get('prior_abf_shortfall_2027_pct') or 0):.0f}%/{float(bofa_current.get('prior_abf_shortfall_2028_pct') or 0):.0f}% → {float(bofa_current.get('abf_shortfall_2026_pct') or 0):.0f}%/{float(bofa_current.get('abf_shortfall_2027_pct') or 0):.0f}%/{float(bofa_current.get('abf_shortfall_2028_pct') or 0):.0f}%로 상향. 후속 리포트 빈티지이므로 2021 -13%와 19%를 같은 차트 직접비교로 표현하지 않습니다.",
        f"• Goldman 출처별 공급부족 전망: 2H26 {float(area_res.get('abf_shortfall_2h2026_pct') or 0):.0f}% → 2027 {float(area_res.get('abf_shortfall_2027_pct') or 0):.0f}% → 2028 {float(area_res.get('abf_shortfall_2028_pct') or 0):.0f}% <i>(리서치 추정·컨센서스 아님)</i>.",
        f"• 2021 역사 기준: ABF 공급부족 ≥{float(area_hist.get('abf_shortfall_pct_min') or 0):.0f}% <i>(DigiTimes 업계 추정)</i> / Goldman 2028 전망 {float(area_res.get('abf_shortfall_2028_pct') or 0):.0f}% <i>(리서치 추정·동일 범위 직접비교 금지)</i>.",
        f"• FY2025 공개 주요고객 매출: Intel {jpy_bn_text(float((off.get('ibiden_customer_sales_fy2024_jpy_bn') or {}).get('Intel') or 0), rate)} / "
        f"AMD {jpy_bn_text(float((off.get('ibiden_customer_sales_fy2024_jpy_bn') or {}).get('AMD') or 0), rate)} / "
        f"NVIDIA {jpy_bn_text(float((off.get('ibiden_customer_sales_fy2024_jpy_bn') or {}).get('NVIDIA') or 0), rate)}",
        "",
        "<b>2단계 미래 재평가 요인 발굴</b>",
        f"• Macquarie 추정 기준선: Intel향 ABF 약 {float(res.get('macquarie_intel_abf_share_pct') or 0):.0f}% / AMD향 약 {float(res.get('macquarie_amd_abf_share_pct') or 0):.0f}% / NVIDIA CPU용 기판 출하 시작. 공식 확인 전 추정으로 유지합니다.",
        f"• BofA 서버 CPU의 ABF 수요비중 전망도 2026/2027/2028 {float(bofa_current.get('prior_server_cpu_abf_demand_share_2026_pct') or 0):.0f}%/{float(bofa_current.get('prior_server_cpu_abf_demand_share_2027_pct') or 0):.0f}%/{float(bofa_current.get('prior_server_cpu_abf_demand_share_2028_pct') or 0):.0f}% → {float(bofa_current.get('server_cpu_abf_demand_share_2026_pct') or 0):.0f}%/{float(bofa_current.get('server_cpu_abf_demand_share_2027_pct') or 0):.0f}%/{float(bofa_current.get('server_cpu_abf_demand_share_2028_pct') or 0):.0f}%로 상향돼 CPU가 부족 심화의 직접 수요축으로 강화됐습니다.",
        f"• Goldman 모델은 2H26 {float(area_res.get('abf_shortfall_2h2026_pct') or 0):.0f}% → 2027 {float(area_res.get('abf_shortfall_2027_pct') or 0):.0f}% → 2028 {float(area_res.get('abf_shortfall_2028_pct') or 0):.0f}%로 악화를 예상합니다. 2028 수치는 2021 ≥{float(area_hist.get('abf_shortfall_pct_min') or 0):.0f}%보다 크지만 제품군·분모·모델이 달라 ‘2021보다 확정적으로 더 부족’이라는 보편적 사실로 승격하지 않습니다.",
        f"• Meritz 추정: 2028 Feynman 등 차세대 AI 가속기 기판 면적이 2026 대비 {float(area_res.get('feynman_2028_area_vs_2026_min_multiple') or 0):.0f}~{float(area_res.get('feynman_2028_area_vs_2026_max_multiple') or 0):.0f}배. NVIDIA 공식 기판 면적 사양으로 취급하지 않습니다.",
        "• 공식 재평가 조건: NVIDIA CPU용 양산 확인, Intel·AMD 고객 비중 공식 공개, SAP 증설 상향, 가격 인상·마진 개선의 회사자료 확인.",
        "",
        "<b>관련 기업 지도</b>",
        "• 직접 사업: Ibiden — AI 서버·고성능 서버용 IC 패키지기판; 현재 양산·매출 발생.",
        "• 직접 사업: Unimicron — AI 서버 ABF; 가격·가동률·마진 변화 추적.",
        "• 직접 사업: 삼성전기 — 서버 CPU·AI 가속기 FCBGA; CPU향 매출 실현 게이트와 교차검증.",
        "• 고객 검증: Intel·AMD·NVIDIA — 고객매출·신규 CPU 세대·양산 확인.",
        "• 간접 생태계: T-glass·압합·검사장비 — 기판 증설을 실제 양품으로 바꾸는 공정 병목.",
        "",
        "<b>공정 병목 후보</b>",
        "• SAP | 대형·고다층으로 동일 기판 수량의 공정부하 증가 | 지표: SAP 생산능력·가동률 | 위험 12~24개월",
        "• 압합·휨·수율 | 층수와 면적 증가 | 지표: 수율·고객승인·검사시간 | 위험 6~18개월",
        "• T-glass | 저열팽창 소재 부족 | 지표: 소재 납기·가격 | 위험 6~18개월",
        "",
        "<b>숨은 역풍·실패모드</b>",
        "• 실패 경로: CPU 수요와 ABF 가격은 오르지만 장비·소재·수율 때문에 양품 출하가 못 늘어 매출 전환이 지연되는 경우.",
        "• 조기경보: SAP 증설 지연, 수율 악화, 고객 승인 지연, 가격 인상에도 출하량·마진이 개선되지 않는 경우.",
        "• 위험 구간: 6~12개월 가격·고객승인, 12~24개월 Gama/Ono 증설 램프와 감가상각.",
        "",
        "<b>알림 기준</b>",
        "• Ibiden·Unimicron·삼성전기 CPU/ABF 고객 비중이 ±5%p 이상 변경 또는 공식 최초 공개.",
        "• NVIDIA CPU용 기판 양산·출하가 공식 확인되면 즉시 알림.",
        "• ABF 가격 ±5% 이상 공식 변화, 신뢰 리서치 ±10% 이상 변화.",
        "• Ibiden SAP 생산능력·설비투자 ±10%, Gama 양산시점 변경, 주요 고객매출 ±10% 이상.",
        "• Goldman 2H26·2027·2028 ABF 공급부족 전망이 동일 리서치 기준 ±5%p 이상 변경하면 출처별로 알림.",
        "• BofA 2026·2027·2028 ABF 공급부족 전망 또는 서버 CPU ABF 수요비중이 같은 BofA 기준 ±3%p 이상 바뀌면 알림.",
        "• Ibiden AI서버 기판당 SAP 공정부하 지수(CY26 1.8·CY28 2.5)가 ±10% 이상 바뀌거나 기판 면적·층수의 공식 로드맵이 변경되면 알림.",
        "• Feynman 면적 추정이 ±0.5배 이상 바뀌면 별도 리서치 추정 변화로 알림.",
        "• 동일 Muse 기사·주가 급등·목표주가만 반복되면 알리지 않습니다.",
        "",
        "<b>결론</b>",
        "• CPU 수요가 실제 ABF 공급사의 가격·가동률·고객매출·마진으로 전환되는지 확인하는 수익화 게이트입니다.",
        "",
        "<b>핵심 한 줄 요약</b>",
        f"• 현재 공식 기준은 Ibiden AI서버 기판 수요>생산능력, FY26~28 5,000억엔 투자, SAP 공정부하 CY24 1.0→CY26 {float(area_off.get('ibiden_ai_server_sap_load_cy2026_index') or 0):.1f}→CY28 {float(area_off.get('ibiden_ai_server_sap_load_cy2028_index') or 0):.1f}입니다. BofA 사용자 차트는 2021 -13%→2028 -16%로 같은 차트상 3%p 더 부족하며, 후속 BofA 공개 요약은 2026/27/28 부족 전망을 4/10/16%→7/14/19%로 상향했습니다. Goldman 14/34/51%는 별도 리서치 모델로 분리 추적합니다.",
    ]
    if rate is not None:
        lines.append(f"• 환율 기준: 1엔={rate:.4f}원, {html.escape(rate_date or '최신 확인값')}")
    return "\n".join(lines).strip() + "\n"

def discover(now: datetime, seen_urls: set[str]) -> list[dict]:
    out = []
    local_seen = set()
    cutoff = now - timedelta(days=120)
    fetch_budget = 18
    fetched = 0
    for kind, query in SEARCHES:
        try:
            items = read_rss(kind, query)
        except Exception:
            continue
        for item in items:
            url = direct_url(item)
            if not url or url in seen_urls or url in local_seen:
                continue
            local_seen.add(url)
            published = item.get("published_at_kst") or ""
            try:
                dt = datetime.fromisoformat(published) if published else None
            except Exception:
                dt = None
            if dt and dt < cutoff:
                continue
            base = clean_text(f"{item.get('title','')} {item.get('description','')}")
            if fetched >= fetch_budget:
                continue
            fetched += 1
            text = clean_text(f"{base} {article_text(url)}")
            milestone = parse_future_nvidia_abf_milestone(text,url) if source_rank(url)==3 else ""
            parsed = ({"kind":"nvidia_abf_milestone","milestone":milestone} if milestone else
                      (parse_official_update(text,url) if source_rank(url)==3 else parse_research_update(text,url)))
            if parsed:
                out.append({
                    "url": url,
                    "published_at_kst": published,
                    "title": item.get("title") or "",
                    "rank": source_rank(url),
                    "parsed": parsed,
                    "full_text": text,
                })
    out.sort(key=lambda x: (x["rank"], x.get("published_at_kst") or ""), reverse=True)
    return [guard_stale_goldman_recap(item) for item in out]

def main() -> None:
    now = datetime.now(ZoneInfo("Asia/Seoul"))
    committed = load_json(STATE_PATH)
    pending = load_json(PENDING_PATH)
    # Standalone collectors must preserve existing HBM route receipts and all
    # unrelated monitored modules if an upstream pending file is absent.
    if not pending and committed:
        pending = copy.deepcopy(committed)
    previous = committed.get("abf_cpu_monetization") or copy.deepcopy(BASELINE)
    seen_urls = set(previous.get("seen_urls") or [])

    updates = [guard_stale_goldman_recap(u) for u in discover(now, seen_urls)]
    events = material_events(previous, updates)
    verified, source_checks = verify_nvidia_abf_press()
    old_partner = previous.get("nvidia_substrate_supply") or {}
    future = [e["parsed"]["milestone"] for e in updates if e.get("parsed",{}).get("kind")=="nvidia_abf_milestone"]
    new_partner_events = nvidia_abf_changes(old_partner,verified,future)
    structure_upgrade = int((previous.get("area_structure") or {}).get("version") or 0) < int(ABF_AREA_STRUCTURE_BASELINE["version"])
    if structure_upgrade:
        upgrade_url = ABF_AREA_STRUCTURE_BASELINE["bofa_model"]["current_public_recap"]["source"] if int(ABF_AREA_STRUCTURE_BASELINE["version"]) >= 3 else ABF_AREA_STRUCTURE_BASELINE["official"]["ibiden_sap_load_source"]
        events.insert(0, {"type": "area_structure_baseline", "key": f"area_structure_v{ABF_AREA_STRUCTURE_BASELINE['version']}", "url": upgrade_url})
    latest = merge_state(previous, updates, events)
    partner = copy.deepcopy(old_partner)
    if verified:
        partner.update(verified)
    partner.setdefault("milestones",{})
    for evt in future:
        partner["milestones"][evt]=True
    latest["nvidia_substrate_supply"] = partner
    latest["nvidia_substrate_source_checks"] = {
        "checked_at_kst":now.isoformat(timespec="seconds"),
        "nvidia":source_checks.get("nvidia"),
        "samsung":source_checks.get("samsung"),
        "fully_verified":bool(verified),
    }
    if structure_upgrade:
        latest["area_structure"] = copy.deepcopy(ABF_AREA_STRUCTURE_BASELINE)
    vintage_upgrade = int((previous.get("goldman_vintage_context") or {}).get("version") or 0) < ABF_VINTAGE_CONTEXT_VERSION
    if vintage_upgrade:
        latest["goldman_vintage_context"] = copy.deepcopy(ABF_VINTAGE_CONTEXT)
    broker_state, broker_alert = unimicron_broker_update(
        previous.get("unimicron_broker_context") or {},
    )
    latest["unimicron_broker_context"] = broker_state
    latest["last_checked_at_kst"] = now.isoformat(timespec="seconds")
    latest["candidate_count"] = len(updates)
    latest["event_count"] = len(events) + len(new_partner_events) + int(vintage_upgrade) + int(bool(broker_alert))

    pending["abf_cpu_monetization"] = latest
    write_json(PENDING_PATH, pending)

    if events or new_partner_events or vintage_upgrade or broker_alert:
        blocks = []
        if events:
            blocks.append(build_alert(events,latest).strip())
        if new_partner_events:
            blocks.append(build_nvidia_abf_alert(new_partner_events,partner).strip())
        if vintage_upgrade:
            blocks.append(build_abf_vintage_context_alert(latest).strip())
        if broker_alert:
            blocks.append(broker_alert.strip())
        block = "\n\n<<<TELEGRAM_MESSAGE_BREAK>>>\n\n".join(blocks)
        existing = ALERT_PATH.read_text(encoding="utf-8").strip() if ALERT_PATH.exists() else ""
        merged = (existing + "\n\n<<<TELEGRAM_MESSAGE_BREAK>>>\n\n" + block).strip() if existing else block
        ALERT_PATH.write_text(merged + "\n",encoding="utf-8")

    print(
        "abf_cpu_monetization_watch=true "
        f"candidates={len(updates)} events={len(events)+len(new_partner_events)+int(vintage_upgrade)+int(bool(broker_alert))} notify={str(bool(events or new_partner_events or vintage_upgrade or broker_alert)).lower()} official_checks={source_checks}"
    )

if __name__ == "__main__":
    main()
