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
except Exception:  # pragma: no cover
    gnewsdecoder = None

ROOT = pathlib.Path(__file__).resolve().parents[1]
STATE_PATH = ROOT / "data" / "rubin_hbm_watch_state.json"
PENDING_PATH = ROOT / "out" / "rubin_hbm_pending_state.json"
ALERT_PATH = ROOT / "out" / "rubin_hbm_alert.md"

UA = "Mozilla/5.0 (compatible; khs-watch/2.0; +https://github.com/qedgwangju-dot/khs-watch)"
BASELINE_DATE = "2026-09-21"
BASELINE = {
    "as_of": BASELINE_DATE,
    "source": "https://insights.trendforce.com/p/weekly-radar-002",
    "components": {
        "GPU": {"status": "Balanced", "current": "30-40", "balanced": "30-40"},
        "DRAM": {"status": "Very Tight", "current": "20", "balanced": "8"},
        "NAND(eSSD)": {"status": "Tight", "current": "16", "balanced": "8"},
        "HDD": {"status": "Very Tight", "current": "50", "balanced": "16"},
        "ABF": {"status": "Very Tight", "current": "48-56", "balanced": "12"},
        "MLCC": {"status": "Tight", "current": "32", "balanced": "12"},
    },
    "signals": {
        "GPU": "Rubin 사양 조정 → Blackwell보다 리드타임 장기화 가능성",
        "DRAM": "미국 CSP의 2027년 서버 증설 대비 RDIMM 수요 증가",
        "NAND(eSSD)": "수요 증가 → 공급사가 기업용 SSD로 생산능력 재배분, 전체 공급은 여전히 부족",
        "HDD": "에이전틱 AI 수요 급증 → 2027년 말까지 리드타임 개선 제한",
        "ABF": "2027년 일본 Low-CTE 유리섬유 천 증설로 소재 병목 완화 가능, 기판 생산능력은 예약 포화",
        "MLCC": "신학기 수요 부진 → 저가 범용 유통가격 하락, 고급 소비자용 가격은 안정",
    },
    "seen_urls": ["https://insights.trendforce.com/p/weekly-radar-002"],
}

# TrendForce Weekly Radar 004 (2026-10-05) exact table lock.
# The seven row values below are transcribed from the user-provided TrendForce original screenshot.
# This lock only applies to Weekly Radar 004 and prevents partial HTML/search-index parsing from
# silently carrying an older weekly value into the current snapshot.
WEEKLY_004_LOCK = {
    "as_of": "2026-10-05",
    "source": "https://insights.trendforce.com/p/weekly-radar-004",
    "source_kind": "TrendForce Weekly Radar 004 / 사용자 제공 원본 캡처 직접 판독",
    "components": {
        "CPU": {"status": "Tight", "current": "25-30", "balanced": "16-20"},
        "GPU": {"status": "Balanced", "current": "30-40", "balanced": "30-40"},
        "DRAM": {"status": "Very Tight", "current": "20", "balanced": "8"},
        "NAND(eSSD)": {"status": "Tight", "current": "16", "balanced": "8"},
        "HDD": {"status": "Very Tight", "current": "50", "balanced": "16"},
        "ABF": {"status": "Very Tight", "current": "48-56", "balanced": "12"},
        "MLCC": {"status": "Tight", "current": "35", "balanced": "12"},
    },
    "signals": {
        "CPU": "AI 추론 부하가 서버 CPU 수요를 지지하며 공급 제약이 지속",
        "GPU": "Blackwell은 2026년 주력 출하·수요 1H27 연장, Rubin은 시스템 테스트·검증 이슈로 4Q26~1Q27부터 점진 램프",
        "DRAM": "4Q26 계약가격 협상에서 인상 신호가 이어지고 미국 CSP 수요가 견조",
        "NAND(eSSD)": "DRAM 부족이 일부 NAND 업체의 기업용 SSD 지원 능력까지 제약",
        "HDD": "HDD 50주 병목 → TrendForce는 시장 완화가 빨라도 2027년 말이라고 전망. Toshiba 공식은 10/2 증설 nearline HDD 라인 첫 출하와 FY2027 생산능력 약 2배 목표를 확인",
        "ABF": "수급 격차가 단기간 닫히기 어렵고 3Q26~4Q27 장기계약 가격은 분기당 10~15% 인상 전망",
        "MLCC": "저가 소비자용은 둔화하지만 AI용 고급 0805는 부족해 수요 양극화",
    },
}



# Separate manufacturer's quoted order backlog from the TrendForce MLCC
# industry composite (35 weeks on 2026-10-19). Never overwrite that composite.
MLCC_VENDOR_VERSION = 2
MLCC_VENDOR_URL = "https://www.digitimes.com.tw/tech/dt/n/shwnws.asp?id=772371"
MLCC_OFFICIAL_LTA_URL = "https://sem.samsung.com/kr/newsroom/news/view.do?id=10501"
PH_GOV_MLCC_TIMING_URL = "https://pco.gov.ph/news_releases/samsungs-over-php50-b-investment-is-first-beneficiary-of-create-more-presidential-approval/"
PH_NEWS_MLCC_TIMING_URL = "https://en.sedaily.com/finance/2026/08/02/samsung-electro-mechanics-fast-tracks-philippine-mlcc-plant"
MLCC_OFFICIAL_Q2_URL = "https://www.sem.samsung.com/kr/newsroom/news/view.do?id=10461"
MLCC_OFFICIAL_FCBGA_URL = "https://www.sem.samsung.com/global/newsroom/news/view.do?id=10562"
CASPA_ORIGINAL_URL = "https://newsletter.chipstrat.com/p/my-conversation-with-dylan-patel"
CASPA_VIDEO_URL = "https://www.youtube.com/watch?v=NXv0qvam9yg"
CASPA_PANEL_CONTEXT_VERSION = 2
CASPA_AGENDA_URL = "https://caspaceosummit.com/agenda/"
SHARON_SEC_URL = "https://www.sec.gov/Archives/edgar/data/2068385/000149315226037203/forms-1a.htm"
MLCC_VENDOR_QUERIES = (
    "삼성전기 MLCC 납기 52주 61주 2026",
    "Samsung Electro Mechanics MLCC lead time weeks 2026 supply",
)
MLCC_VENDOR_HOSTS = ("digitimes.com.tw", "heraldcorp.com", "reuters.com",
                     "thelec.net", "trendforce.com", "sem.samsung.com")
MLCC_VENDOR_BASELINE = {
    "version": 2, "as_of": "2026-10-23", "manufacturer": "삼성전기",
    "maker_weeks": 52, "channel_max_weeks": 61,
    "scope": "manufacturer_order_vs_selected_distribution",
    "evidence": "신뢰 언론보도; 삼성전기 공식 납기표 아님",
    "source_url": MLCC_VENDOR_URL, "industry_reference_weeks": 35,
    "industry_reference_date": "2026-10-19",
    "sep_prior_claim": "30주 이상(정확한 직전값 공개되지 않음)",
    "official_2027_lta_krw": 1_072_200_000_000,
    "official_lta_url": MLCC_OFFICIAL_LTA_URL,
    "q2_2026_component_revenue_eok": 16494,
    "q2_2026_sales_eok": 34572,
    "q2_2026_op_profit_eok": 4404,
    "h1_2026_utilization_pct_reported": 91,
    "q3_earnings_expected": "2026-10-28",
    "philippines_factory": {
        "official_government_goal": "2027-07",
        "official_scope": "전장용 MLCC 신설시설",
        "source_url": PH_GOV_MLCC_TIMING_URL,
        "later_report_earliest": "2027-Q1말",
        "later_report_source": PH_NEWS_MLCC_TIMING_URL,
        "ai_grade_customer_mass_production_verified": False,
    },
}
CASPA_PANEL_BASELINE = {
    "version": 2, "as_of": "2026-10-23", "source_url": CASPA_ORIGINAL_URL,
    "video_url": CASPA_VIDEO_URL,
    "video_verification_level": "event and moderator's transcript corroborated; video full audiovisual comparison not independently certified",
    "bottleneck_ranking": ["패키지기판·PCB 소재", "메모리", "광결합·레이저"],
    "power_constraint_exists": True,
    "power_on_site_generation_partial_workaround_not_universal": True,
    "supply_relief_initial_2027_then_more_2028_2029": True,
    "hbm_3_4x_denominator_same_capacity_with_wafer_budget_fixed": True,
    "memory_total_output_decline_unconditional": False,
    "hyperscaler_offtake_mitigates_risk_not_automatic_credit_guarantee": True,
    "neocloud_debt_risk_not_eliminated_by_offtake": True,
    "nvidia_can_gain_absolute_profit_despite_losing_component_spend_share": True,
    "source_kind": "2026-10-23 CASPA participant statements; not company guidance",
    "kind": "panel_opinion_not_signed_purchase_order",
    "wafer_hbm_relative_ddr5_min": 3, "wafer_hbm_relative_ddr5_max": 4,
    "dc_2024_1gw_usd_bn": 40, "dc_2026_1gw_usd_bn_over": 60,
    "dc_components_without_design_margin_usd_bn": 20,
    "capital_yield_example_pct": "13~15",
    "sharon_nvidia_40k_gpu_72mw_sec_verified": True,
    "sharon_sec_url": SHARON_SEC_URL,
}

# 2026-10-19 Weekly Radar 006: exact seven-row source image supplied by user.
# Values and labels are evidence from that screenshot, NOT parsed from prose.
# This issue-specific lock must never override Weekly Radar 007 or newer.
WEEKLY_006_LOCK = {
    "as_of": "2026-10-19",
    "source": "https://insights.trendforce.com/p/weekly-radar-006",
    "source_kind": "TrendForce Weekly Radar 006 / 사용자 제공 원본 이미지 직접 판독",
    "components": {
        "CPU": {"status": "Tight", "current": "25-30", "balanced": "16-20"},
        "GPU": {"status": "Balanced", "current": "30-40", "balanced": "30-40"},
        "DRAM": {"status": "Very Tight", "current": "20", "balanced": "8"},
        "NAND(eSSD)": {"status": "Tight", "current": "16", "balanced": "8"},
        "HDD": {"status": "Very Tight", "current": "50", "balanced": "16"},
        "ABF": {"status": "Very Tight", "current": "48-56", "balanced": "12"},
        "MLCC": {"status": "Tight", "current": "35", "balanced": "12"},
    },
}




# Weekly Radar 006 official narrative, separate from the image's seven numeric rows.
WEEKLY_006_HDD_OUTLOOK = (
    "HDD 현재 50주 / 균형 16주 · 대형 클라우드 고객은 "
    "2028년 장기계약 체결 후에도 공급 부족을 예상 (TrendForce 10/19)"
)

# Previous confirmed Week 005 checkpoint (saved 2026-10-19 14:01 KST).
# Referenced only for issue 006 correction; NOT a generic baseline for future issues.
# GitHub historical source: ece7bb88ce9c64050dc9910b12a4e729ff041d60.
WEEKLY_005_ARCHIVED_COMPONENTS = {
    "CPU": {"status": "Tight", "current": "25-30", "balanced": "16-20"},
    "GPU": {"status": "Balanced", "current": "30-40", "balanced": "30-40"},
    "DRAM": {"status": "Very Tight", "current": "20", "balanced": "8"},
    "NAND(eSSD)": {"status": "Tight", "current": "16", "balanced": "8"},
    "HDD": {"status": "Very Tight", "current": "50", "balanced": "16"},
    "ABF": {"status": "Very Tight", "current": "48-56", "balanced": "12"},
    "MLCC": {"status": "Tight", "current": "35", "balanced": "12"},
}

TOSHIBA_HDD_OFFICIAL = {
    "as_of": "2026-10-02",
    "source": "https://toshiba.semicon-storage.com/ap-en/company/news/news-topics/2026/10/storage-20261002-1.html",
    "expanded_nearline_line_first_shipment": True,
    "fy2027_capacity_target_vs_fy2025": "nearly_double",
    "scope_note": (
        "Toshiba 공식자료는 Laguna Technopark 증설 nearline HDD 라인의 생산·첫 출하 시작과 "
        "FY2027 생산능력 약 2배 목표를 확인한다. TrendForce의 'late 2027 relief'는 시장 전체 "
        "리드타임 정상화 전망으로 분리하며, Toshiba 라인이 2027년 말까지 전혀 가동되지 않는다는 뜻으로 해석하지 않는다."
    ),
}

NAND_2027_DIVERGENCE_OFFICIAL = {
    "as_of": "2026-07-30",
    "source": "https://www.trendforce.com/presscenter/news/20260730-13158.html",
    "general_nand_supply_easing_2h27_expected": True,
    "enterprise_storage_primary_growth_engine": True,
    "scope_note": (
        "TrendForce는 전체 NAND Flash 수급이 신규 생산능력과 공정 전환으로 2H27부터 완화될 수 있다고 본다. "
        "동시에 기업용 SSD는 AI 서버 수요의 핵심 성장축으로 남는다. 따라서 현재 기업용 SSD 제약을 "
        "전체 NAND가 2027년 말까지 동일하게 부족하다는 주장으로 확대하지 않는다."
    ),
}

UBS_PROJECT_LEADTIME_BASELINE = {
    "as_of": "2026-09",
    "source_kind": "사용자 제공 UBS 차트",
    "source_caption": "Company reports, UBS, P Equity Research, as of Sep 2026",
    "metric": "company-reported project lead time",
    "unit": "months",
    "directly_comparable_to_component_delivery_lead_time": False,
    "segments": {
        "Foundry": {"min_months": 36, "max_months": 48},
        "Semicap equipment": {"min_months": 12, "max_months": 24},
        "Adv. packaging / substrates": {"min_months": 12, "max_months": 18},
        "Storage systems": {"min_months": 12, "max_months": 24},
        "GPUs / AI accelerators": {"min_months": 6, "max_months": 12},
        "Memory (HBM / DRAM)": {"min_months": 6, "max_months": 12},
        "Optical transceivers / networking": {"min_months": 3, "max_months": 9},
        "CPUs": {"min_months": 3, "max_months": 6},
        "Servers": {"min_months": 1, "max_months": 2},
    },
}

UBS_COMPONENT_SEGMENT = {
    "CPU": "CPUs",
    "GPU": "GPUs / AI accelerators",
    "DRAM": "Memory (HBM / DRAM)",
    "NAND(eSSD)": "Storage systems",
    "HDD": "Storage systems",
    "ABF": "Adv. packaging / substrates",
}

SEARCHES = [
    ("trendforce_feed", ""),
    (
        "google_news",
        'TrendForce ("lead time" OR "lead times" OR "리드타임") (CPU OR ABF OR MLCC OR HDD OR DRAM OR NAND OR GPU) "AI infrastructure"',
    ),
    ("bing_web", 'site:insights.trendforce.com/p/weekly-radar TrendForce "Weekly Radar"'),
    ("bing_web", 'site:x.com/trendforce "lead time" "AI infrastructure" ABF MLCC'),
    ("bing_web", 'site:trendforce.com TrendForce "lead time" CPU ABF DRAM NAND HDD MLCC GPU'),
    ("bing_web", '"current vs balanced lead times" TrendForce'),
    ("bing_web", '"TrendForce" CPU GPU DRAM NAND HDD ABF MLCC 리드타임'),
    ("bing_web", '"TrendForce" "Weekly Radar" CPU GPU DRAM NAND HDD ABF MLCC'),
    ("google_news", 'TrendForce ("NAND controller" OR "SSD controller") (DRAM shortage OR DRAM tightness) enterprise SSD'),
    ("bing_web", 'site:trendforce.com ("NAND controller" OR "SSD controller") DRAM enterprise SSD shortage'),
]

ALIASES = {
    "CPU": ("server CPUs", "server CPU", "CPU"),
    "GPU": ("GPU",),
    "DRAM": ("DRAM",),
    "NAND(eSSD)": ("NAND", "eSSD", "enterprise SSD"),
    "HDD": ("HDD", "hard disk"),
    "ABF": ("ABF substrates", "ABF substrate", "ABF"),
    "MLCC": ("MLCCs", "MLCC"),
}

STATUS_KO = {
    "Very Tight": "심각한 공급 부족",
    "Tight": "공급 제약",
    "Balanced": "균형",
}

STATUS_SEVERITY = {"Balanced": 0, "Tight": 1, "Very Tight": 2}

REVENUE_PATHS = {
    "CPU": "에이전틱 AI·가상머신·도구 호출 증가 → 서버 CPU 주문·출하 → FC-BGA·RDIMM·스토리지 동반 수요 → 서버 매출",
    "GPU": "AI 가속기 출하 → 첨단패키징·HBM·기판·전력·냉각 동반 수요 → 시스템 매출",
    "DRAM": "서버·RDIMM 수요 → 출하량·평균판매단가·제품 혼합 개선 → 메모리 매출·마진",
    "NAND(eSSD)": "기업용 SSD 수요 → NAND 생산능력 재배분 → eSSD 출하·평균판매단가 → 스토리지 매출",
    "HDD": "에이전틱 AI 데이터·로그·장기보관 증가 → nearline HDD 용량·출하 → 스토리지 매출",
    "ABF": "GPU·ASIC·CPU 대형·고다층화 → FC-BGA/ABF 유효 생산능력 소모 → 고부가 기판 출하·제품 혼합 개선",
    "MLCC": "AI 서버·네트워크 전력밀도 상승 → 고용량·고신뢰성 MLCC 탑재량 증가 → 고부가 부품 매출",
}

COMPANY_WATCH = {
    "CPU": "AMD·Intel·Arm·서버 ODM/OEM — 서버 CPU·에이전틱 AI 오케스트레이션 수요",
    "GPU": "NVIDIA·AMD — AI 가속기 수요축",
    "DRAM": "삼성전자·SK하이닉스·Micron — 서버 DRAM/RDIMM",
    "NAND(eSSD)": "삼성전자·SK하이닉스/Solidigm·Micron — 기업용 SSD/NAND",
    "HDD": "Seagate·Western Digital — nearline HDD",
    "ABF": "삼성전기·Ibiden·Unimicron·Nan Ya PCB — 고성능 FC-BGA/ABF 기판",
    "MLCC": "삼성전기·Murata·Taiyo Yuden — 고용량·고신뢰성 MLCC",
}

FAILURE_MODES = {
    "CPU": ("수요는 늘어도 웨이퍼·기판·후공정 공급이 따라오지 못해 주문이 실제 서버 출하로 연결되지 않는 경로", "CPU 리드타임·ASP·OEM 주문·FC-BGA 가동률", "6~12개월"),
    "GPU": ("사양 변경·플랫폼 전환 지연", "샘플→양산 일정·랙 출하", "6~12개월"),
    "DRAM": ("선주문 이후 실제 서버 출하가 따라오지 않아 재고가 다시 쌓이는 경로", "RDIMM 가격·재고·출하", "6~12개월"),
    "NAND(eSSD)": ("eSSD로 생산능력을 옮겼지만 실제 수요가 둔화돼 가격과 가동률이 동시에 꺾이는 경로", "기업용 SSD 가격·가동률·재고", "6~12개월"),
    "HDD": ("대용량 드라이브 수율·생산능력 확대가 지연돼 납기만 길어지는 경로", "출하 EB·리드타임·고객 재고", "6~12개월"),
    "ABF": ("T-glass·압합장비·휨·수율·고객 인증이 증설 속도를 따라오지 못하는 경로", "리드타임·SAP 가동률·수율·고객 승인", "12~24개월"),
    "MLCC": ("범용 수요 약세가 AI용 고사양 가격 방어보다 커져 제품 혼합 효과가 약화되는 경로", "고사양/범용 가격·BB비율·가동률", "6~12개월"),
}

WEEK = r"(\d{1,2}(?:\s*[-–—~]\s*\d{1,2})?)\s*(?:weeks?|w|주)\b"


def fetch(url: str, timeout: int = 20) -> bytes:
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.read()


def clean_text(value: str) -> str:
    value = html.unescape(value or "")
    value = re.sub(r"<(script|style|svg|noscript)[^>]*>.*?</\1>", " ", value, flags=re.I | re.S)
    value = re.sub(r"<[^>]+>", " ", value)
    return re.sub(r"\s+", " ", value).strip()


def normalize_week(value: str) -> str:
    return re.sub(r"\s*[-–—~]\s*", "-", (value or "").strip())


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


def bing_rss_url(query: str) -> str:
    q = urllib.parse.quote(query)
    return f"https://www.bing.com/search?format=rss&q={q}"


def read_rss(kind: str, query: str) -> list[dict]:
    if kind == "trendforce_feed":
        url = "https://insights.trendforce.com/feed"
    elif kind == "google_news":
        url = google_news_url(query)
    else:
        url = bing_rss_url(query)
    root = ET.fromstring(fetch(url))
    out: list[dict] = []
    for item in root.findall("./channel/item"):
        title = clean_text(item.findtext("title") or "")
        link = clean_text(item.findtext("link") or "")
        desc = clean_text(item.findtext("description") or "")
        pub = clean_text(item.findtext("pubDate") or "")
        dt = parse_pubdate(pub)
        if title and link:
            out.append(
                {
                    "kind": kind,
                    "title": title,
                    "link": link,
                    "description": desc,
                    "published_at_kst": dt.isoformat(timespec="seconds") if dt else "",
                }
            )
    return out


def decode_google_news(link: str) -> str:
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


def candidate_url(item: dict) -> str:
    if item.get("kind") == "google_news":
        return decode_google_news(item.get("link") or "")
    return item.get("link") or ""


def is_trendforce_source(url: str, text: str) -> bool:
    host = (urlparse(url).hostname or "").lower()
    low = text.lower()
    return (
        host == "trendforce.com" or host.endswith(".trendforce.com")
        or (host.endswith("x.com") and "/trendforce" in url.lower())
        or "trendforce" in low
    )


def is_relevant(text: str) -> bool:
    low = text.lower()
    component_hits = sum(1 for aliases in ALIASES.values() if any(a.lower() in low for a in aliases))
    lead_hit = any(k in low for k in ("lead time", "lead times", "balanced lead", "current lead", "리드타임", "납기"))
    weekly_phrase = (
        "six ai infrastructure components" in low
        or "seven ai infrastructure components" in low
        or "current vs balanced" in low
        or "we track cpu, gpu, dram, nand, hdd, abf, and mlcc" in low
    )
    return lead_hit and (component_hits >= 2 or weekly_phrase)


def article_text(url: str) -> str:
    if not url:
        return ""
    host = (urlparse(url).hostname or "").lower()
    if host.endswith("x.com"):
        return ""
    try:
        raw = fetch(url, timeout=18).decode("utf-8", errors="ignore")
        return clean_text(raw)[:24000]
    except Exception:
        return ""


def status_from_exact(value: str) -> str:
    low = (value or "").lower()
    if "very tight" in low or "severe shortage" in low or "심각한 공급 부족" in value or "심각한 부족" in value:
        return "Very Tight"
    if re.search(r"\btight\b", low) or "constrained supply" in low or "공급 제약" in value:
        return "Tight"
    if "balanced" in low or "균형" in value:
        return "Balanced"
    return ""


def extract_structured_row(text: str, alias: str) -> dict:
    # 표가 실제 텍스트로 노출된 경우에만 사용한다.
    # 컴포넌트명 뒤에 상태→현재 납기→균형 납기가 연속해서 붙은 경우만 인정한다.
    pattern = (
        rf"\b{re.escape(alias)}\b"
        rf"(?:\s+substrates?)?\s*[:|\-]?\s*"
        rf"(Very\s+Tight|Tight|Balanced)\s*"
        rf"{WEEK}\s*{WEEK}"
    )
    m = re.search(pattern, text, re.I)
    if not m:
        return {}
    return {
        "status": status_from_exact(m.group(1)),
        "current": normalize_week(m.group(2)),
        "balanced": normalize_week(m.group(3)),
    }


def extract_labeled_narrative(text: str, alias: str) -> dict:
    # 영문 원문과 국내 재전달 문구를 모두 읽되, 숫자는 alias 이후 문맥에서만 채택한다.
    positions = [m for m in re.finditer(re.escape(alias), text, re.I)]
    best: dict = {}
    for m in positions:
        chunk = text[m.start() : min(len(text), m.end() + 420)]
        entry: dict[str, str] = {}

        b = re.search(
            rf"(?:balanced(?:\s+market|\s+lead\s+time|\s+lead\s+times)?|균형(?:\s*리드타임|\s*수준)?)"
            rf"[^.\n]{{0,120}}?{WEEK}",
            chunk,
            re.I,
        )
        if b:
            entry["balanced"] = normalize_week(b.group(1))

        c = re.search(
            rf"(?:current(?:\s+lead\s+time|\s+lead\s+times)?|리드타임(?:은|는|:)?|납기(?:는|:)?|현재(?:\s*리드타임)?)"
            rf"[^.\n]{{0,80}}?{WEEK}",
            chunk,
            re.I,
        )
        if c:
            entry["current"] = normalize_week(c.group(1))

        # 상태는 표의 구조화 행 또는 "X는 Very Tight/Tight/Balanced"처럼
        # 부품명과 상태가 직접 연결된 명시 문구에서만 갱신한다.
        # "balanced lead time" 같은 벤치마크 문구를 상태로 오인하지 않는다.

        if len(entry) > len(best):
            best = entry
    return best


def extract_group_statuses(text: str) -> dict[str, str]:
    # 예: "DRAM·HDD·ABF는 심각한 공급 부족, NAND eSSD·MLCC는 공급 제약 상태"
    token = r"(?:CPU|GPU|DRAM|NAND(?:\s*\(eSSD\)|\s+eSSD)?|eSSD|HDD|ABF|MLCC)"
    group = rf"({token}(?:\s*[·,/＋+&]\s*{token})*)"
    out: dict[str, str] = {}

    for m in re.finditer(
        rf"{group}\s*(?:은|는|이|가|is|are|remain)?\s*"
        r"(심각한 공급 부족|심각한 부족|공급 제약(?: 상태)?|균형(?: 상태)?|Very\s+Tight|Tight|Balanced|severe shortage|constrained supply)",
        text,
        re.I,
    ):
        status = status_from_exact(m.group(2))
        names = m.group(1)
        for name, aliases in ALIASES.items():
            if any(re.search(re.escape(a), names, re.I) for a in aliases):
                out[name] = status

    # 예: "균형 상태인 품목은 GPU뿐"처럼 상태와 품목군이 문법적으로 직접 연결된 경우만 인정한다.
    # 쉼표 뒤의 다음 상태군을 앞 상태가 덮어쓰지 않도록 임의 거리 매칭은 사용하지 않는다.
    for m in re.finditer(
        r"(심각한 공급 부족|공급 제약|균형|Very\s+Tight|Tight|Balanced)"
        r"(?:\s+상태)?(?:인)?\s+품목(?:은|이|으로는)?\s*"
        rf"{group}",
        text,
        re.I,
    ):
        status = status_from_exact(m.group(1))
        names = m.group(2)
        for name, aliases in ALIASES.items():
            if any(re.search(re.escape(a), names, re.I) for a in aliases):
                out[name] = status
    return out


def extract_components(text: str) -> dict:
    result: dict[str, dict] = {}
    normalized = text.replace("–", "-").replace("—", "-")
    for name, aliases in ALIASES.items():
        best: dict = {}
        for alias in aliases:
            structured = extract_structured_row(normalized, alias)
            if structured:
                best = structured
                break
            narrative = extract_labeled_narrative(normalized, alias)
            if len(narrative) > len(best):
                best = narrative
        if best.get("current") or best.get("balanced") or best.get("status"):
            result[name] = best

    for name, status in extract_group_statuses(normalized).items():
        result.setdefault(name, {})["status"] = status
    return result


def extract_signals(text: str, source_url: str = "") -> dict[str, str]:
    low = (text or "").lower()
    signals: dict[str, str] = {}

    if (
        "cpu" in low
        and ("25" in low and "30" in low)
        and any(k in low for k in ("agentic", "agent", "csp", "server cpu"))
    ):
        signals["CPU"] = "에이전틱 AI·CSP 인하우스 설계 확대로 서버 CPU 조달 압력이 부각"

    if "rubin" in low and ("specification" in low or "adjustment" in low or "사양 조정" in text):
        signals["GPU"] = "Rubin 사양 조정 → Blackwell보다 리드타임 장기화 가능성"

    if "rdimm" in low and "2027" in low and any(k in low for k in ("demand", "pick up", "수요")):
        signals["DRAM"] = "미국 CSP의 2027년 서버 증설 대비 RDIMM 수요 증가"

    if (
        "dram" in low
        and any(k in low for k in ("enterprise ssds", "enterprise ssd", "essd"))
        and any(k in low for k in (
            "limiting some nand suppliers",
            "nand suppliers' ability",
            "nand suppliers’ ability",
            "support enterprise ssd",
            "dram shortage",
            "dram tightness",
            "dram 공급 부족",
        ))
    ):
        signals["NAND(eSSD)"] = "DRAM 공급 부족 → 일부 NAND 공급사의 기업용 SSD 솔루션 지원 능력 제약"
    elif (
        any(k in low for k in ("enterprise ssds", "enterprise ssd", "essd"))
        and any(k in low for k in ("reallocat", "capacity toward", "생산능력 재배분", "캐파 재배분"))
    ):
        signals["NAND(eSSD)"] = "수요 증가 → 공급사가 기업용 SSD로 생산능력 재배분, 전체 공급은 여전히 부족"

    if (
        "hdd" in low
        and ("50 weeks" in low or "50w" in low or "50주" in text)
        and ("late 2027" in low or "2027년 말" in text)
    ):
        signals["HDD"] = "HDD 50주 병목 → 공급 완화는 빨라도 2027년 말"
    elif "hdd" in low and "agentic ai" in low:
        if "late 2027" in low or "2027년 말" in text:
            signals["HDD"] = "에이전틱 AI 수요 급증 → 2027년 말까지 리드타임 개선 제한"
        else:
            signals["HDD"] = "에이전틱 AI 수요 증가 → HDD 공급 압박 지속"

    if (
        "abf" in low
        and any(k in low for k in ("low-cte", "low cte"))
        and any(k in low for k in ("glass fiber", "유리섬유"))
    ):
        signals["ABF"] = "2027년 일본 Low-CTE 유리섬유 천 증설로 소재 병목 완화 가능, 기판 생산능력은 예약 포화"

    if "mlcc" in low and any(k in low for k in ("back-to-school", "신학기")):
        signals["MLCC"] = "신학기 수요 부진 → 저가 범용 유통가격 하락, 고급 소비자용 가격은 안정"

    if source_url.rstrip("/").endswith("weekly-radar-002"):
        for name, value in BASELINE["signals"].items():
            signals.setdefault(name, value)

    if source_url.rstrip("/").endswith("weekly-radar-004"):
        # Weekly Radar 004's table is image-led. Keep the directly read screenshot narrative
        # as the source-specific fallback when the HTML/index exposes only partial row text.
        for name, value in WEEKLY_004_LOCK["signals"].items():
            signals.setdefault(name, value)

    if source_url.rstrip("/") == WEEKLY_006_LOCK["source"]:
        # The 2028 outlook is narrative evidence, not a change to 50-week lead time.
        signals["HDD"] = WEEKLY_006_HDD_OUTLOOK

    return signals


def extract_nand_controller_direct_constraint(text: str) -> bool:
    """Only confirm a DRAM-caused controller bottleneck when one sentence states it directly."""
    if not text:
        return False
    sentences = re.split(r"(?<=[.!?])\s+|[\n\r]+", clean_text(text))
    for sentence in sentences:
        low = sentence.lower()
        controller_hit = any(k in low for k in (
            "nand controller", "ssd controller", "enterprise ssd controller",
            "낸드 컨트롤러", "ssd 컨트롤러", "기업용 ssd 컨트롤러",
        ))
        dram_hit = any(k in low for k in (
            "dram shortage", "dram tightness", "dram supply shortage", "dram constraint",
            "dram 공급 부족", "dram 부족", "dram 공급 제약",
        ))
        causal_hit = any(k in low for k in (
            "constrain", "constraining", "limit", "limiting", "restrict", "bottleneck", "shortage",
            "제약", "제한", "병목", "부족",
        ))
        if controller_hit and dram_hit and causal_hit:
            return True
    return False


def canonical_component(entry: dict) -> tuple[str, str, str]:
    return (
        str(entry.get("status") or ""),
        str(entry.get("current") or ""),
        str(entry.get("balanced") or ""),
    )


def changed_components(old: dict, new: dict) -> list[str]:
    changed = []
    for name, new_entry in new.items():
        old_entry = old.get(name) or {}
        if canonical_component(old_entry) != canonical_component(new_entry):
            changed.append(name)
    return changed


def midpoint_week(value: str) -> float | None:
    nums = [float(x) for x in re.findall(r"\d+(?:\.\d+)?", value or "")]
    if not nums:
        return None
    return sum(nums) / len(nums)


def ratio_value(current: str, balanced: str) -> float | None:
    c = midpoint_week(current)
    b = midpoint_week(balanced)
    if c is None or b in (None, 0):
        return None
    return c / b


def biggest_current_change(old: dict, new: dict) -> tuple[str, float] | None:
    ranked: list[tuple[float, str, float]] = []
    for name, new_entry in new.items():
        old_entry = old.get(name) or {}
        before = midpoint_week(str(old_entry.get("current") or ""))
        after = midpoint_week(str(new_entry.get("current") or ""))
        if before is None or after is None or before == after:
            continue
        ranked.append((abs(after - before), name, after - before))
    if not ranked:
        return None
    ranked.sort(reverse=True)
    _, name, delta = ranked[0]
    return name, delta


def bottleneck_ranking(components: dict) -> list[tuple[float, str, dict]]:
    ranked: list[tuple[float, str, dict]] = []
    for name, entry in components.items():
        ratio = ratio_value(str(entry.get("current") or ""), str(entry.get("balanced") or ""))
        if ratio is not None:
            ranked.append((ratio, name, entry))
    ranked.sort(reverse=True)
    return ranked


def memory_storage_chain_state(
    components: dict,
    signals: dict,
    nand_controller_direct_constraint_confirmed: bool = False,
) -> dict:
    """Track the DRAM -> enterprise-SSD -> HDD storage bottleneck as a causal chain.

    TrendForce Weekly Radar 004 says DRAM tightness limits some NAND suppliers'
    ability to support enterprise SSD solutions. It does not, by itself, establish
    a separate NAND-controller shipment shortage, so that claim is kept false
    unless a future direct source explicitly confirms it.
    """
    dram = components.get("DRAM") or {}
    nand = components.get("NAND(eSSD)") or {}
    hdd = components.get("HDD") or {}
    dram_ratio = ratio_value(str(dram.get("current") or ""), str(dram.get("balanced") or ""))
    nand_ratio = ratio_value(str(nand.get("current") or ""), str(nand.get("balanced") or ""))
    hdd_ratio = ratio_value(str(hdd.get("current") or ""), str(hdd.get("balanced") or ""))

    nand_signal = str((signals or {}).get("NAND(eSSD)") or "")
    hdd_signal = str((signals or {}).get("HDD") or "")
    dram_to_essd = (
        ("DRAM 공급 부족" in nand_signal or "DRAM 부족" in nand_signal)
        and "기업용 SSD" in nand_signal
    )
    hdd_late_2027 = (
        ("2027년 말" in hdd_signal or "2028년" in hdd_signal)
        and ("50주" in hdd_signal or str(hdd.get("current") or "") == "50")
    )
    active = bool(
        str(dram.get("status") or "") == "Very Tight"
        and (dram_ratio or 0) >= 2.0
        and str(nand.get("status") or "") in {"Tight", "Very Tight"}
        and (nand_ratio or 0) >= 1.5
        and str(hdd.get("status") or "") == "Very Tight"
        and (hdd_ratio or 0) >= 2.5
        and dram_to_essd
        and hdd_late_2027
    )
    return {
        "version": 3,
        "active": active,
        "dram_lead_ratio": round(dram_ratio, 3) if dram_ratio is not None else None,
        "nand_essd_lead_ratio": round(nand_ratio, 3) if nand_ratio is not None else None,
        "hdd_lead_ratio": round(hdd_ratio, 3) if hdd_ratio is not None else None,
        "dram_to_enterprise_ssd_constraint_confirmed": dram_to_essd,
        "hdd_relief_late_2027_or_later": hdd_late_2027,
        "hdd_relief_is_market_normalization_outlook": hdd_late_2027,
        "toshiba_expanded_nearline_line_first_shipment_confirmed": bool(TOSHIBA_HDD_OFFICIAL["expanded_nearline_line_first_shipment"]),
        "toshiba_fy2027_capacity_nearly_double_target": TOSHIBA_HDD_OFFICIAL["fy2027_capacity_target_vs_fy2025"] == "nearly_double",
        "toshiba_official_source": TOSHIBA_HDD_OFFICIAL["source"],
        "nand_general_supply_easing_2h27_expected": bool(NAND_2027_DIVERGENCE_OFFICIAL["general_nand_supply_easing_2h27_expected"]),
        "enterprise_storage_primary_growth_engine": bool(NAND_2027_DIVERGENCE_OFFICIAL["enterprise_storage_primary_growth_engine"]),
        "nand_2027_divergence_source": NAND_2027_DIVERGENCE_OFFICIAL["source"],
        "nand_essd_divergence_guard_enabled": True,
        "nand_controller_direct_constraint_detection_enabled": True,
        "nand_controller_direct_constraint_confirmed": bool(nand_controller_direct_constraint_confirmed),
        "scope_note": (
            "확인 범위는 DRAM 부족이 일부 NAND 공급사의 기업용 SSD 솔루션 지원 능력을 제약한다는 것. "
            "NAND 컨트롤러 출하 자체의 직접 병목은 별도 확인 전까지 확정하지 않음. "
            "전체 NAND Flash는 2H27부터 수급 완화 가능성이 있어 기업용 SSD 병목과 분리함. "
            "HDD 2027년 말 이후·2028년 공급 제약 전망은 시장 전체 조달 전망이며 Toshiba 증설 라인 첫 출하 사실과 별도 관리."
        ),
    }


def build_memory_storage_chain_alert(chain: dict, components: dict, source_url: str) -> str:
    dram = components.get("DRAM") or {}
    nand = components.get("NAND(eSSD)") or {}
    hdd = components.get("HDD") or {}
    lines = [
        "<b>🔗 메모리·스토리지 연쇄 병목 감시 추가</b>",
        "",
        "TrendForce 10/5 기준으로 개별 부품이 아니라 DRAM→기업용 SSD→HDD의 연쇄 병목을 기존 알림에서 함께 추적합니다.",
        f"• <b>DRAM:</b> {html.escape(fmt_week(dram.get('current')))} / 균형 {html.escape(fmt_week(dram.get('balanced')))} · {chain.get('dram_lead_ratio', 0):.1f}배 · {html.escape(fmt_status(dram))}",
        f"• <b>기업용 SSD:</b> {html.escape(fmt_week(nand.get('current')))} / 균형 {html.escape(fmt_week(nand.get('balanced')))} · DRAM 부족이 일부 NAND 공급사의 eSSD 솔루션 지원 능력을 제약",
        f"• <b>HDD:</b> {html.escape(fmt_week(hdd.get('current')))} / 균형 {html.escape(fmt_week(hdd.get('balanced')))} · {chain.get('hdd_lead_ratio', 0):.1f}배 · TrendForce 시장 전망상 정상화는 빨라도 2027년 말",
        f"• <b>Toshiba 공식:</b> 10/2 Laguna 증설 nearline HDD 라인 첫 출하 완료 · FY2027 생산능력은 FY2025 대비 약 2배 목표",
        "",
        "<b>정확도 경계</b>",
        "• TrendForce 확인 범위는 ‘DRAM 부족 → 일부 NAND 공급사의 기업용 SSD 솔루션 지원 제약’입니다.",
        (
            "• <b>NAND 컨트롤러:</b> DRAM 부족이 컨트롤러 출하를 직접 제약한다는 문장이 공식 원문에서 확인됐습니다."
            if chain.get("nand_controller_direct_constraint_confirmed")
            else "• <b>NAND 컨트롤러 출하가 DRAM 때문에 직접 제한된다는 주장은 이번 원문에서 확인되지 않아 알림 확정조건에 넣지 않았습니다.</b>"
        ),
        "• <b>NAND 전체 수급:</b> TrendForce는 신규 생산능력·공정 전환으로 2H27부터 완화 가능성을 봅니다. 기업용 SSD 병목을 전체 NAND의 2027년 말까지 동일한 부족으로 확대하지 않습니다.",
        "• Toshiba는 이미 증설 라인에서 첫 출하를 시작했습니다. 따라서 ‘2027년 말’은 개별 Toshiba 라인의 미가동 시점이 아니라 시장 전체 리드타임 정상화 전망으로만 추적합니다.",
        "",
        "<b>다음 확인</b>",
        "• DRAM 리드타임·서버 DRAM 가격 / eSSD 리드타임·가격·출하 / HDD 리드타임·증설 가동시점이 함께 꺾이는지 확인",
    ]
    if source_url:
        lines.append(f'• <a href="{html.escape(source_url, quote=True)}">TrendForce 원문</a>')
    lines.append(f'• <a href="{html.escape(TOSHIBA_HDD_OFFICIAL["source"], quote=True)}">Toshiba 공식 HDD 증설·첫 출하</a>')
    lines.append(f'• <a href="{html.escape(NAND_2027_DIVERGENCE_OFFICIAL["source"], quote=True)}">TrendForce 2027 NAND 수급 전망</a>')
    return "\n".join(lines).strip() + "\n"



def supply_component_direction(before: dict, after: dict) -> str:
    """Count real lead-time moves, or explicitly confirmed status-tier moves.

    A balanced-market baseline adjustment alone never counts as an actual
    delivery lead-time improvement. Unknown statuses cannot become zero.
    When explicit status and lead time contradict, hold direction for review.
    """
    a = midpoint_week(str(before.get("current") or ""))
    b = midpoint_week(str(after.get("current") or ""))
    before_level = STATUS_SEVERITY.get(str(before.get("status") or ""))
    after_level = STATUS_SEVERITY.get(str(after.get("status") or ""))
    current_move = (1 if b > a + 0.05 else -1 if b < a - 0.05 else 0) if a is not None and b is not None else 0
    status_move = ((1 if after_level > before_level else -1 if after_level < before_level else 0)
                   if before_level is not None and after_level is not None else 0)
    if current_move and status_move and current_move != status_move:
        return "uncertain"
    move = current_move or status_move
    return "worse" if move > 0 else "better" if move < 0 else "same"


def supply_direction_details(old: dict, new: dict) -> dict[str, list[str]]:
    details: dict[str, list[str]] = {"worse": [], "better": [], "uncertain": []}
    for name in ("CPU", "GPU", "DRAM", "NAND(eSSD)", "HDD", "ABF", "MLCC"):
        if name not in old or name not in new:
            continue  # Newly monitored component is not a week-over-week change.
        before, after = old[name] or {}, new[name] or {}
        direction = supply_component_direction(before, after)
        if direction == "same":
            continue
        a, b = str(before.get("current") or ""), str(after.get("current") or "")
        before_mid, after_mid = midpoint_week(a), midpoint_week(b)
        if a != b and before_mid is not None and after_mid is not None:
            move = after_mid - before_mid
            movement = f"{fmt_week(a)}→{fmt_week(b)} ({abs(move):g}주 {'연장' if move > 0 else '단축'})"
        else:
            movement = f"납기 {fmt_week(b)} 유지" if a and a == b else "납기 비교 불충분"
        before_status = fmt_status(before)
        after_status = fmt_status(after)
        if before_status != after_status:
            movement += f", 상태 {before_status}→{after_status}"
        details[direction].append(f"{name}: {movement}")
    return details


def supply_direction(old: dict, new: dict) -> tuple[str, int, int]:
    details = supply_direction_details(old, new)
    worse, better = len(details["worse"]), len(details["better"])
    if worse > better:
        return "↗ 병목 확대", worse, better
    if better > worse:
        return "↘ 병목 완화", worse, better
    return "→ 변화 제한", worse, better


def focus_components(changed: list[str], signal_names: list[str], components: dict, limit: int = 4) -> list[str]:
    out: list[str] = []
    ranked = bottleneck_ranking(components)

    # 가장 강한 병목은 변화 여부와 무관하게 항상 투자판단 초점에 남긴다.
    if ranked:
        strongest_name = ranked[0][1]
        if strongest_name in components:
            out.append(strongest_name)

    for name in [*changed, *signal_names]:
        if name in components and name not in out:
            out.append(name)
        if len(out) >= limit:
            return out[:limit]

    for _, name, _ in ranked:
        if name not in out:
            out.append(name)
        if len(out) >= limit:
            break
    return out[:limit]


def source_tier(url: str, text: str = "") -> int:
    host = (urlparse(url).hostname or "").lower()
    if host == "trendforce.com" or host.endswith(".trendforce.com"):
        return 3
    if host.endswith("x.com") and "/trendforce" in url.lower():
        return 2
    if "trendforce" in (text or "").lower():
        return 1
    return 0


def candidate_sort_key(item: dict) -> tuple[int, str, int]:
    # Source quality first; within the same source tier the newest Weekly Radar
    # must beat an older issue even if the older page exposes more table fields.
    return (
        source_tier(str(item.get("direct_url") or ""), str(item.get("full_text") or "")),
        str(item.get("published_at_kst") or ""),
        int(item.get("score") or 0),
    )


def source_score(url: str, components: dict, text: str) -> int:
    host = (urlparse(url).hostname or "").lower()
    score = len(components) * 10
    # 공식 원문이 일부 필드만 노출하더라도 2차 재인용보다 항상 우선한다.
    if host == "trendforce.com" or host.endswith(".trendforce.com"):
        score += 1000
    elif host.endswith("x.com") and "/trendforce" in url.lower():
        score += 900
    elif "trendforce" in text.lower():
        score += 100
    if "current vs balanced" in text.lower():
        score += 20
    if "weekly radar" in text.lower():
        score += 20
    return score


def load_json(path: pathlib.Path) -> dict:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}


def write_json(path: pathlib.Path, obj: dict) -> None:
    path.write_text(json.dumps(obj, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def repair_bad_initial_state(previous: dict) -> dict:
    # 2026-09-15 최초 배포 검증 중 서문에 있던 '56W'를 GPU 값으로 오인한 상태를 자동 복구한다.
    comps = previous.get("components") or {}
    if (
        str(previous.get("source") or "").endswith("/weekly-radar-001")
        and str((comps.get("GPU") or {}).get("current") or "") == "56"
    ):
        fixed = copy.deepcopy(BASELINE)
        fixed["seen_urls"] = list(previous.get("seen_urls") or [])
        return fixed
    return previous


def repair_weekly_002_state(previous: dict) -> tuple[dict, list[str]]:
    # Weekly Radar 002 공식 표(사용자 제공 TrendForce 원본 캡처) 기준 상태를 잠근다.
    # 2026-09-22 배포본에서 "균형 리드타임" 문구를 공급 상태로 잘못 읽은 회귀를 복구한다.
    if not str(previous.get("source") or "").rstrip("/").endswith("weekly-radar-002"):
        return previous, []
    comps = previous.get("components") or {}
    expected = BASELINE["components"]
    repaired = copy.deepcopy(previous)
    repaired.setdefault("components", {})
    changed: list[str] = []
    for name, exp in expected.items():
        cur = dict(repaired["components"].get(name) or {})
        # 숫자는 Weekly Radar 002 기준값과 일치할 때만 상태를 강제 복구한다.
        if (
            str(cur.get("current") or "") == str(exp.get("current") or "")
            and str(cur.get("balanced") or "") == str(exp.get("balanced") or "")
            and str(cur.get("status") or "") != str(exp.get("status") or "")
        ):
            cur["status"] = exp["status"]
            repaired["components"][name] = cur
            changed.append(name)
    repaired["signals"] = copy.deepcopy(BASELINE.get("signals") or repaired.get("signals") or {})
    return repaired, changed


def repair_weekly_004_state(previous: dict) -> tuple[dict, list[str], list[str]]:
    """Lock Weekly Radar 004 to the seven rows directly visible in the provided TrendForce table."""
    if not str(previous.get("source") or "").rstrip("/").endswith("weekly-radar-004"):
        return previous, [], []

    repaired = copy.deepcopy(previous)
    repaired.setdefault("components", {})
    component_changes: list[str] = []
    for name, expected in WEEKLY_004_LOCK["components"].items():
        current = dict(repaired["components"].get(name) or {})
        if canonical_component(current) != canonical_component(expected):
            repaired["components"][name] = copy.deepcopy(expected)
            component_changes.append(name)

    old_signals = dict(repaired.get("signals") or {})
    signal_changes = [
        name for name, value in WEEKLY_004_LOCK["signals"].items()
        if str(old_signals.get(name) or "") != str(value)
    ]
    repaired["signals"] = copy.deepcopy(WEEKLY_004_LOCK["signals"])
    repaired["as_of"] = WEEKLY_004_LOCK["as_of"]
    repaired["source"] = WEEKLY_004_LOCK["source"]
    return repaired, component_changes, signal_changes




def mlcc_vendor_trusted_url(url: str) -> bool:
    host = (urlparse(url).hostname or "").lower()
    return any(host == x or host.endswith("." + x) for x in MLCC_VENDOR_HOSTS)


def mlcc_vendor_new_fact(item: dict) -> dict | None:
    url = str(item.get("direct_url") or item.get("link") or "")
    if not mlcc_vendor_trusted_url(url):
        return None
    published = str(item.get("published_at_kst") or "")[:10]
    if not published or published < "2026-10-25":
        return None  # Historical syndicated 52-week baseline is not a fresh event.
    title = clean_text(str(item.get("title") or ""))
    text = (title + " " + clean_text(str(item.get("description") or ""))).lower()
    if "mlcc" not in text and "적층세라믹" not in text and "積層陶瓷" not in text:
        return None
    if not any(x in text for x in ("samsung electro", "semco", "삼성전기", "三星電機", "三星电机")):
        return None
    if not any(x in text for x in ("lead time", "납기", "리드타임", "交期", "delivery wait")):
        return None
    vals = [int(x) for x in re.findall(r"(?<!\d)(\d{2,3})\s*(?:weeks?\b|w\b|주|週)", text)
            if 15 <= int(x) <= 120]
    if not vals:
        return None
    # Reporting both 52 and 61 means maker 52 / distribution peak 61.
    if 52 in vals and 61 in vals:
        return None  # Already covered by baseline, no time-series revision.
    channel = any(x in text for x in ("distributor", "distribution", "유통", "通路", "代理"))
    return {"scope": "channel" if channel else "maker", "weeks": vals[0],
            "as_of": published, "url": url, "title": title}


def mlcc_vendor_update(previous: dict, incoming: list[dict]) -> tuple[dict, list[dict]]:
    record = copy.deepcopy(previous or {})
    events = []
    existing_version = int(record.get("version") or 0)
    if existing_version == 0:
        record = copy.deepcopy(MLCC_VENDOR_BASELINE)
        events.append({"kind": "initial"})
    elif existing_version < MLCC_VENDOR_VERSION:
        # Preserve the already-reported 52/61-week baseline and its delivery
        # identity; migrate only the additional government timeline evidence.
        record["version"] = MLCC_VENDOR_VERSION
        record["philippines_factory"] = copy.deepcopy(MLCC_VENDOR_BASELINE["philippines_factory"])
        events.append({"kind": "philippines_timing_correction"})
    seen = set(record.get("seen_facts") or [])
    for item in sorted(incoming, key=lambda x: x.get("published_at_kst") or ""):
        obs = mlcc_vendor_new_fact(item)
        if not obs:
            continue
        key = f"{obs['scope']}|{obs['weeks']}|{obs['as_of']}"
        if key in seen:
            continue
        seen.add(key)
        field = "maker_weeks" if obs["scope"] == "maker" else "channel_max_weeks"
        old_value = int(record.get(field) or 0)
        if abs(obs["weeks"] - old_value) < 4:
            continue
        record[field] = obs["weeks"]
        record["as_of"] = obs["as_of"]
        events.append({"kind": "revision", "before": old_value, **obs})
    record["seen_facts"] = sorted(seen)[-120:]
    return record, events


def mlcc_vendor_notice(event: dict, record: dict, industry: dict) -> str:
    if event["kind"] == "philippines_timing_correction":
        return "\n".join([
            "<b>MLCC 증설 일정 정정 — 필리핀 정부 공식</b>",
            "• 필리핀 정부 2025년 발표: 전장용 MLCC 신설시설 <b>2027년 7월까지 상업가동 목표</b>.",
            "• 2026년 8월 업계보도: 이르면 <b>2027년 1분기 말</b> 신공장 가동 예상.",
            "• 따라서 '2027년 이후에야 가동'을 확정 일정으로 쓰지 않습니다.",
            "• 2027년 가동 목표와 AI용 세부규격 양산·고객 인증·실제 출하는 별도 확인합니다.",
            "• 삼성전기 52주 및 일부 유통 61주 보도와 TrendForce 산업 35주 지표는 변경하지 않음.",
            "• 다음 확인: 10월 28일 3분기 실적, 필리핀 공장 시운전·제품별 생산·양품률.",
            f'• <a href="{PH_GOV_MLCC_TIMING_URL}">필리핀 정부 발표</a>'
            f' / <a href="{PH_NEWS_MLCC_TIMING_URL}">2026년 8월 조기 가동 보도</a>',
        ])
    if event["kind"] == "revision":
        label = "삼성전기 제조사" if event["scope"] == "maker" else "일부 유통 채널"
        a, b = event["before"], event["weeks"]
        return "\n".join([
            "<b>MLCC 업체별 납기 추가 변화 — 보도 단계</b>",
            f"• {label}: <b>{a}주 → {b}주 ({abs(b-a)}주 {'연장' if b>a else '단축'})</b>",
            "• 산업 통계와 제조사·유통 제품 납기를 동일 시계열로 합산하지 않음.",
            f'• <a href="{html.escape(event["url"],quote=True)}">신규 보도</a>',
        ])
    industry_current = str((industry.get("MLCC") or {}).get("current") or "미확인").replace("-", "~")
    return "\n".join([
        "<b>MLCC 납기 악화 — 삼성전기 제조사·유통 별도 추적</b>",
        "• 2026년 10월 삼성전기 주문 납기 <b>52주</b> (DIGITIMES 보도).",
        "• 일부 유통 채널 제품은 최장 <b>61주</b> (같은 제조사 전체 제품 아님).",
        f"• TrendForce 10/19 산업 지표: <b>{html.escape(industry_current)}주</b> (산업 공통 평균 범위).",
        "• 중요: 35주→52주를 산업 리드타임 악화(+17주)로 계산하지 않음.",
        "• 9월 '30주 이상'도 정확한 직전값이 없어 +22주 확정 계산 금지.",
        "• 삼성전기 공식: AI 서버용 MLCC <b>1조 722억원</b> 2027년 1~12월 공급계약.",
        "• 2Q26 컴포넌트 매출 1조6,494억원(분기), 전사 매출 3조4,572억원·영업이익 4,404억원.",
        "• 상반기 가동률 91%는 보도치. 제품별 생산·고객 단가와 다름.",
        "• 필리핀 정부 전장용 MLCC 신공장 상업가동 목표는 2027년 7월까지; AI용 세부제품 양산은 별도 검증.",
        "• 세종·베트남 설비투자 6조7,800억원은 <b>FC-BGA 기판용</b>, MLCC와 분리.",
        "• 다음 확인: 10/28 3분기 잠정실적, MLCC 평균판매단가·생산능력·필리핀 공장 일정.",
        f'• <a href="{MLCC_VENDOR_URL}">납기 보도</a>'
        f' / <a href="{MLCC_OFFICIAL_LTA_URL}">공식 공급계약</a>',
    ])


def usd_bn_krw_text(bn: float, rate: float | None) -> str:
    if rate is None or not (800 <= float(rate) <= 2500):
        return ""
    eok = round(bn * 1_000_000_000 * float(rate) / 100_000_000)
    jo, rem = divmod(eok, 10000)
    return f"약 {jo}조{rem:,}억원" if jo else f"약 {rem:,}억원"


def caspa_panel_update(previous: dict, fx: dict) -> tuple[dict, str]:
    old_version = int((previous or {}).get("version") or 0)
    if old_version >= CASPA_PANEL_CONTEXT_VERSION:
        return previous, ""
    if old_version == 1:
        # Migration of a delivered 10/25 baseline: only material corrections,
        # no replay of 1GW cost estimates or previous initial notification.
        record = copy.deepcopy(previous)
        for key, value in CASPA_PANEL_BASELINE.items():
            if key not in record:
                record[key] = copy.deepcopy(value)
        record["version"] = CASPA_PANEL_CONTEXT_VERSION
        note = [
            "<b>CASPA 2026 병목 발언 후속 검증 — 기존 알림 보강</b>",
            "• <b>판단:</b> 패키지기판·PCB 소재 → 메모리 → CPO 레이저·광섬유 결합은 Dylan Patel의 산업 병목 순위 전망입니다. 모든 프로젝트의 실측 순위는 아닙니다.",
            "• <b>전력:</b> 여전히 중요한 제약. 터빈·왕복동 엔진·연료전지로 일부 우회할 수 있으나 계통접속·인허가·전원 인가가 없어지는 것은 아닙니다.",
            "• <b>HBM:</b> 일반 DDR5와 동일 저장 용량 대비 웨이퍼 사용량 3~4배라는 발표자 비교. 총 메모리 생산량 감소는 웨이퍼 총투입이 고정될 때의 조건부 해석입니다.",
            "• <b>클린룸:</b> 2027년 일부 공급 가능, 2028~2029년 확대라는 전망. 2028년 이전 일괄 증설 불가로 단정하지 않습니다.",
            "• <b>금융:</b> 네오클라우드는 신용도 높은 장기 이용계약이 필요할 수 있으나 차입금리 13~15% 사례처럼 계약만으로 금융 위험이 사라지지 않습니다.",
            "• <b>가치 배분:</b> 메모리·기판·광학 공급사의 협상력이 좋아져도 NVIDIA 절대이익 감소가 필연적이지 않습니다.",
            "• <b>알림 구분:</b> 발언·전망 / 공식 투자·공급계약 / 실제 출하·단가·현금흐름을 각각 독립 추적합니다.",
            f'• <a href="{CASPA_VIDEO_URL}">CASPA 영상</a> / <a href="{CASPA_ORIGINAL_URL}">사회자 공개 대담록</a>',
        ]
        return record, "\n".join(note)
    record = copy.deepcopy(CASPA_PANEL_BASELINE)
    rate = (fx or {}).get("rate")
    a, b, c = [usd_bn_krw_text(x, rate) for x in (40, 60, 20)]
    lines = [
        "<b>CASPA 2026 반도체 공급·금융 병목 검증 알림</b>",
        "• 10월 23일 Dylan Patel·Stacy Rasgon 대담. 계약 공시가 아닌 발언·전망.",
        "• 전력은 큰 제약이나 현장 발전이 일부 우회 가능. 기판·메모리·CPO를 산업 관점의 최우선 공급 병목으로 지목.",
        "• 신규 클린룸 공급은 2027년 일부, 2028~2029년 확대 전망. 증설 완전 불가능 주장 아님.",
        "• 장기 이용계약은 자금조달의 필요조건일 수 있으나 과잉증설·손실을 원천 차단하지 않음.",
        "• 공급사 협상력 강화와 NVIDIA의 절대이익 증가가 동시에 가능.",
        "• 기판·PCB 소재, HBM, 광학 연결이 주요 병목. 자금조달과 전력 접속은 별도 제약.",
        "• HBM의 웨이퍼 사용량은 DDR5 같은 용량 대비 <b>3~4배</b>; 전달문 '34배'는 원문 오기.",
        "• 네오클라우드 금융비용 13~15%는 대담에서 제시한 일부 사례이지 산업 전체 일률 금리 아님.",
        "• NVIDIA·Sharon AI 수익배분과 신용지원 협력은 SEC 공시 확인. 최대 4만 GPU/72MW는 계획.",
        "• 차세대 반도체 장비는 소재·밸브·질량유량제어기·PCB까지 병목 전이 가능.",
    ]
    if a and b and c:
        lines.append(f"• 1GW 전체 구축비 추정: 400억달러({a})→600억달러 이상({b} 이상).")
        lines.append(f"• 설계업체 마진 제외 부품비 추정 200억달러({c}); 건설·전력 포함 총비와 분모가 다름.")
        lines.append(f"• 환율: 1달러={float(rate):,.2f}원 (기존 검증 환율 기준, 보조 추산).")
    else:
        lines.append("• 외화 구축비 추정치는 환율 검증 실패로 이번 Telegram 원화 계산에서 제외.")
    lines += [
        "• 수익배분율·GPU당 3.50달러는 대담 진술이며 계약상 정산단위 공개자료와 미대조.",
        "• 다음 확인: 수주→발주→클린룸 설치·수율, 금융 종결·차입비용·실제 전원 인가.",
        f'• <a href="{CASPA_VIDEO_URL}">공식 발표 영상</a> / <a href="{CASPA_ORIGINAL_URL}">진행자 공개 원문</a>'
        f' / <a href="{SHARON_SEC_URL}">Sharon AI SEC 공시</a>',
    ]
    return record, "\n".join(lines)


def repair_weekly_006_state(previous: dict) -> tuple[dict, list[str]]:
    """Repair the one mislabeled 10/19 issue without changing any other vintage."""
    if str(previous.get("source") or "").rstrip("/") != WEEKLY_006_LOCK["source"]:
        return previous, []
    fixed = copy.deepcopy(previous)
    fixed.setdefault("components", {})
    changed: list[str] = []
    for name, expected in WEEKLY_006_LOCK["components"].items():
        original = fixed["components"].get(name) or {}
        if canonical_component(original) != canonical_component(expected):
            fixed["components"][name] = copy.deepcopy(expected)
            changed.append(name)
    fixed["as_of"] = WEEKLY_006_LOCK["as_of"]
    fixed["source"] = WEEKLY_006_LOCK["source"]
    fixed["image_verified_issue"] = "weekly-radar-006"
    fixed.setdefault("signals", {})
    fixed["signals"]["HDD"] = WEEKLY_006_HDD_OUTLOOK
    return fixed, changed


def build_weekly_006_correction_alert(before: dict, after: dict, changed: list[str]) -> str:
    """One-off factual correction, emitted only when stored 006 values were wrong."""
    direction, worse, better = supply_direction(WEEKLY_005_ARCHIVED_COMPONENTS, after)
    lines = [
        "<b>AI 부품 리드타임 정정 — 10월 19일</b>",
        "",
        "기존 알림의 ‘완화 1개’는 HDD 공급 상태를 잘못 판독한 결과입니다.",
        "• <b>정정된 전주 대비: 악화 0개 (없음) / 완화 0개 (없음)</b>"
        if worse == 0 and better == 0 else
        f"• <b>전주 대비: 악화 {worse}개 / 완화 {better}개</b>",
    ]
    for name in changed:
        old = before.get(name) or {}
        new = after.get(name) or {}
        lines.append(
            f"• <b>{html.escape(name)}:</b> 저장 오류 {html.escape(fmt_status(old))} → "
            f"정정 {html.escape(fmt_status(new))}, 현재 {html.escape(fmt_week(new.get('current')))}"
            f" / 균형 {html.escape(fmt_week(new.get('balanced')))}"
        )
    lines += [
        "• HDD: 지난주 Very Tight·50주 → 이번 주 Very Tight·50주. <b>완화 아님</b>.",
        "• 별도 전망: 대형 고객은 2028년 장기계약 이후에도 HDD 공급 부족을 예상. 납기 감소와 구분.",
        "",
        "<b>10월 19일 이미지 기준 7개 품목</b>",
    ]
    lines.extend(_compact_status_groups(after))
    lines += [
        "",
        "• 잘못된 원인: 원문 내 부분 문구를 주간 공급 상태로 오인해 이전 심각 상태를 덮어씀.",
        "• 방지: 7개 행 직접 대조, 출처 미확인 상태 변경 차단, 악화·완화 품목명과 납기 변화 표시.",
        f'• <a href="{html.escape(WEEKLY_006_LOCK["source"], quote=True)}">TrendForce Weekly Radar 006</a>',
    ]
    return "\n".join(lines).strip() + "\n"


def merge_verified_weekly_components(previous: dict, extracted: dict) -> tuple[dict, dict[str, set[str]]]:
    """Never infer a direction from status-only snippets with no same-issue lead times."""
    merged = copy.deepcopy(previous)
    evidence: dict[str, set[str]] = {}
    for name, entry in extracted.items():
        if name not in ALIASES:
            continue
        record = dict(merged.get(name) or {})
        full_row = all(entry.get(k) for k in ("status", "current", "balanced"))
        accepted: set[str] = set()
        for key in ("status", "current", "balanced"):
            value = entry.get(key)
            if not value:
                continue
            if (key == "status" and record.get("status")
                    and str(record["status"]) != str(value) and not full_row):
                continue
            record[key] = value
            accepted.add(key)
        if accepted:
            merged[name] = record
            evidence[name] = accepted
    return merged, evidence


def build_weekly_004_correction_alert(
    old: dict,
    corrected: dict,
    component_names: list[str],
    signal_names: list[str],
) -> str:
    lines = [
        "<b>⚠️ AI 부품 리드타임 감시 — 10/5 원본 표 재대조</b>",
        "",
        "TrendForce Weekly Radar 004 원본 표와 저장값을 다시 대조해 파서 누락·이월값을 바로잡았습니다.",
    ]

    if "DRAM" in component_names:
        before = old.get("DRAM") or {}
        after = corrected.get("DRAM") or {}
        lines.append(
            f"• <b>DRAM 상태 정정:</b> {html.escape(fmt_status(before))} → {html.escape(fmt_status(after))} "
            f"(현재 {html.escape(fmt_week(after.get('current')))} / 균형 {html.escape(fmt_week(after.get('balanced')))})"
        )
    if "MLCC" in component_names:
        before = old.get("MLCC") or {}
        after = corrected.get("MLCC") or {}
        old_mid = midpoint_week(str(before.get("current") or ""))
        new_mid = midpoint_week(str(after.get("current") or ""))
        delta = "" if old_mid is None or new_mid is None else f" · {new_mid-old_mid:+.0f}주"
        lines.append(
            f"• <b>MLCC 최신값:</b> {html.escape(fmt_week(before.get('current')))} → "
            f"{html.escape(fmt_week(after.get('current')))}{delta} / 균형 {html.escape(fmt_week(after.get('balanced')))}"
        )

    other = [name for name in component_names if name not in {"DRAM", "MLCC"}]
    for name in other:
        lines.append(f"• <b>{html.escape(name)}:</b> {html.escape(fmt_entry(corrected.get(name) or {}))}")

    lines += ["", "<b>10/5 확정 표 — 7개 품목</b>"]
    lines.extend(_compact_status_groups(corrected))

    if signal_names:
        lines += ["", "<b>원인·시간표 업데이트</b>"]
        for name in ("CPU", "GPU", "DRAM", "NAND(eSSD)", "HDD", "ABF", "MLCC"):
            if name in signal_names:
                lines.append(f"• <b>{html.escape(name)}:</b> {html.escape(WEEKLY_004_LOCK['signals'][name])}")

    lines += [
        "",
        "• 교차검증: TrendForce 공식 Weekly Radar 004는 DRAM 20주/균형 8주·Very Tight를 명시하고, "
        "9/30 공식 메모리 자료는 4Q26 서버 DRAM·기업용 SSD의 공급 제약을 별도로 확인합니다.",
        f'• <a href="{html.escape(WEEKLY_004_LOCK["source"], quote=True)}">TrendForce 원문</a>',
    ]
    return "\n".join(lines).strip() + "\n"


def build_status_correction_alert(old: dict, corrected: dict, names: list[str], source_url: str) -> str:
    lines = [
        "<b>⚠️ AI 부품 리드타임 감시 — 상태 정정</b>",
        "",
        "직전 알림에서 균형 리드타임 문구를 공급 상태로 잘못 읽은 항목을 정정합니다.",
    ]
    for name in names:
        old_status = fmt_status(old.get(name) or {})
        new_status = fmt_status(corrected.get(name) or {})
        lines.append(f"• <b>{html.escape(name)}</b>: {html.escape(old_status)} → {html.escape(new_status)}")
    lines += ["", "<b>정정 후 6개 품목 상태</b>"]
    for name in ("GPU", "DRAM", "NAND(eSSD)", "HDD", "ABF", "MLCC"):
        entry = corrected.get(name) or {}
        lines.append(
            f"• <b>{html.escape(name)}</b> | 현재 {html.escape(fmt_week(entry.get('current')))} | "
            f"균형 {html.escape(fmt_week(entry.get('balanced')))} | 상태 {html.escape(fmt_status(entry))}"
        )
    if source_url:
        safe_url = html.escape(source_url, quote=True)
        lines.append(f'• <a href="{safe_url}">TrendForce 원문</a>')
    return "\n".join(lines).strip() + "\n"


def fmt_week(value: str) -> str:
    value = str(value or "확인 불가").replace("-", "~")
    return value if value == "확인 불가" else value + "주"


def fmt_status(entry: dict) -> str:
    status = str(entry.get("status") or "")
    return STATUS_KO.get(status, status or "상태 미확인")


def fmt_entry(entry: dict) -> str:
    return f"현재 {fmt_week(entry.get('current'))} / 균형 {fmt_week(entry.get('balanced'))} / 상태 {fmt_status(entry)}"


def fmt_change(old_entry: dict, new_entry: dict) -> str:
    parts = []
    old_current = str(old_entry.get("current") or "")
    new_current = str(new_entry.get("current") or "")
    if old_current != new_current:
        parts.append(f"{fmt_week(old_current)} → {fmt_week(new_current)}")

    old_balanced = str(old_entry.get("balanced") or "")
    new_balanced = str(new_entry.get("balanced") or "")
    if old_balanced != new_balanced:
        parts.append(f"균형 {fmt_week(old_balanced)} → {fmt_week(new_balanced)}")

    old_status = fmt_status(old_entry)
    new_status = fmt_status(new_entry)
    if old_status != new_status:
        parts.append(f"상태 {old_status} → {new_status}")
    return ", ".join(parts) if parts else "동일"


def evidence_note(name: str, evidence: dict[str, set[str]] | None, field: str) -> str:
    if evidence is None:
        return ""
    fields = evidence.get(name) or set()
    if field in fields:
        return ""
    return " (직전 확정값 유지·이번 주 직접 판독 미확인)"


def _compact_metric(name: str, entry: dict) -> str:
    current = fmt_week(entry.get("current"))
    balanced = fmt_week(entry.get("balanced"))
    ratio = ratio_value(str(entry.get("current") or ""), str(entry.get("balanced") or ""))
    ratio_text = f"{ratio:.1f}배" if ratio is not None else "격차 확인 불가"
    return f"{name} {current}/{balanced} ({ratio_text})"


def _compact_status_groups(components: dict) -> list[str]:
    groups = [
        ("심각", "Very Tight"),
        ("제약", "Tight"),
        ("균형", "Balanced"),
    ]
    rows = []
    for label, status in groups:
        names = []
        for name in ("CPU", "GPU", "DRAM", "NAND(eSSD)", "HDD", "ABF", "MLCC"):
            entry = components.get(name) or {}
            if str(entry.get("status") or "") == status:
                names.append(_compact_metric(name, entry))
        if names:
            rows.append(f"• <b>{label}:</b> " + " · ".join(html.escape(x) for x in names))
    return rows


def build_alert(
    old: dict,
    new: dict,
    changed: list[str],
    source_url: str,
    published: str,
    signal_only: bool,
    signals: dict[str, str] | None = None,
    changed_signals: list[str] | None = None,
    evidence: dict[str, set[str]] | None = None,
) -> str:
    signals = signals or {}
    changed_signals = changed_signals or []
    ranked = bottleneck_ranking(new or old)
    strongest = ranked[0] if ranked else None
    direction, worse_count, better_count = supply_direction(old, new)
    added = [name for name in changed if name not in old and name in new]

    lines = [
        "<b>🚨 AI 부품 리드타임 변화</b>",
        "",
        "<b>핵심 변화</b>",
    ]

    if added:
        for name in added:
            entry = new.get(name) or {}
            lines.append(
                f"• <b>신규 추적 {html.escape(name)}:</b> "
                f"{html.escape(fmt_week(entry.get('current')))} / 균형 {html.escape(fmt_week(entry.get('balanced')))} / "
                f"{html.escape(fmt_status(entry))}"
            )

    existing_changes = [name for name in changed if name in old]
    details = supply_direction_details(old, new)
    if worse_count or better_count:
        worse_label = (f"악화 {worse_count}개 (" + "; ".join(details["worse"]) + ")"
                       if worse_count else "악화 0개 (없음)")
        better_label = (f"완화 {better_count}개 (" + "; ".join(details["better"]) + ")"
                        if better_count else "완화 0개 (없음)")
        lines.append(
            f"• <b>전주 대비:</b> {html.escape(direction)} — "
            + html.escape(worse_label + " / " + better_label)
        )
    elif not added:
        lines.append("• <b>전주 대비:</b> 납기·공급 상태 변화 없음 (악화 0개 / 완화 0개, 해당 없음)")
    if details["uncertain"]:
        lines.append(
            "• <b>방향 판정 보류:</b> " + html.escape("; ".join(details["uncertain"]))
        )

    if strongest:
        ratio, name, entry = strongest
        lines.append(
            f"• <b>최대 병목:</b> {html.escape(name)} "
            f"{html.escape(fmt_week(entry.get('current')))} / 균형 {html.escape(fmt_week(entry.get('balanced')))} "
            f"({ratio:.1f}배)"
        )

    if evidence is not None:
        directly_read = [
            name for name in ("CPU", "GPU", "DRAM", "NAND(eSSD)", "HDD", "ABF", "MLCC")
            if {"status", "current", "balanced"} <= (evidence.get(name) or set())
        ]
        carried = [
            name for name in ("CPU", "GPU", "DRAM", "NAND(eSSD)", "HDD", "ABF", "MLCC")
            if name in (new or old) and name not in directly_read
        ]
        if directly_read:
            lines.append("• 이번 주 직접 확인: " + ", ".join(html.escape(x) for x in directly_read))
        if carried:
            lines.append("• 이전 확정값 유지: " + ", ".join(html.escape(x) for x in carried))

    lines += ["", "<b>현재 숫자</b>"]
    lines.extend(_compact_status_groups(new or old))

    # 새로 바뀐 품목의 UBS 구조 시간축만 붙인다. 주문→납기와 프로젝트 시간축은 절대 같은 지표로 취급하지 않는다.
    structural_rows = []
    for name in changed:
        segment = UBS_COMPONENT_SEGMENT.get(name)
        if not segment:
            continue
        row = (UBS_PROJECT_LEADTIME_BASELINE["segments"] or {}).get(segment) or {}
        if row:
            structural_rows.append(
                f"{name} {float(row['min_months']):g}~{float(row['max_months']):g}개월"
            )
    if structural_rows:
        lines += [
            "",
            "<b>구조 시간축</b>",
            "• UBS 프로젝트 기준: " + " · ".join(html.escape(x) for x in structural_rows)
            + " <i>(부품 주문→납기와 직접 비교 금지)</i>",
        ]

    lines += ["", "<b>미래 재평가</b>"]
    signal_names = []
    for name in [*changed_signals, *added]:
        if name in signals and name not in signal_names:
            signal_names.append(name)
    if strongest and strongest[1] in signals and strongest[1] not in signal_names:
        signal_names.append(strongest[1])
    if signal_names:
        for name in signal_names[:3]:
            lines.append(f"• <b>{html.escape(name)}:</b> {html.escape(signals[name])}")
    else:
        lines.append("• 새 원인·시간표 변화 없음")

    lines += ["", "<b>관련 기업</b>"]
    company_names = []
    for name in [*added, *existing_changes]:
        if name not in company_names:
            company_names.append(name)
    if strongest and strongest[1] not in company_names:
        company_names.append(strongest[1])
    if not company_names and strongest:
        company_names.append(strongest[1])
    for name in company_names[:3]:
        watch = COMPANY_WATCH.get(name)
        if watch:
            lines.append(f"• <b>{html.escape(name)}:</b> {html.escape(watch)}")

    lines += ["", "<b>역풍·다음 확인</b>"]
    checks = []
    for name in company_names[:2]:
        failure, indicator, risk_window = FAILURE_MODES.get(
            name, ("공급능력·수율·고객 채택 지연", "리드타임·가격·가동률", "6~12개월")
        )
        checks.append(
            f"{name}: {indicator} ({risk_window})"
        )
    if checks:
        lines.append("• " + " / ".join(html.escape(x) for x in checks))
    else:
        lines.append("• 리드타임·가격·신규수주·가동률")

    if signal_only:
        lines.append("• 일부 값은 이번 주 직접 판독되지 않아 이전 확정값을 유지했습니다.")

    if source_url:
        safe_url = html.escape(source_url, quote=True)
        lines += ["", f'• <a href="{safe_url}">TrendForce 원문</a>']

    return "\n".join(lines).strip() + "\n"

def main() -> None:
    now = datetime.now(ZoneInfo("Asia/Seoul"))
    state = load_json(STATE_PATH)
    pending = load_json(PENDING_PATH)
    # An isolated/rerun invocation may not have the earlier Rubin collector's
    # pending file. Preserve the full existing production state in that case;
    # do not overwrite Telegram receipts or unrelated HBM modules with {}.
    # When upstream has already created pending, its updated values take priority.
    if not pending and state:
        pending = copy.deepcopy(state)
    raw_previous = repair_bad_initial_state(state.get("ai_component_leadtime") or copy.deepcopy(BASELINE))
    raw_previous_components = copy.deepcopy(raw_previous.get("components") or BASELINE["components"])
    weekly_002_previous, repaired_status_names = repair_weekly_002_state(raw_previous)
    weekly_002_components = copy.deepcopy(weekly_002_previous.get("components") or BASELINE["components"])
    weekly_004_previous, repaired_004_components, repaired_004_signals = repair_weekly_004_state(weekly_002_previous)
    before_006 = copy.deepcopy(weekly_004_previous.get("components") or BASELINE["components"])
    previous, repaired_006_components = repair_weekly_006_state(weekly_004_previous)
    previous_components = previous.get("components") or BASELINE["components"]
    seen_urls = set(previous.get("seen_urls") or [])

    candidates: list[dict] = []
    errors: list[str] = []
    cutoff = now - timedelta(days=21)

    for kind, query in SEARCHES:
        try:
            items = read_rss(kind, query)
        except Exception as exc:
            errors.append(f"{kind}: {type(exc).__name__}: {exc}")
            continue
        for item in items:
            direct = candidate_url(item)
            if not direct:
                continue
            base_text = f"{item.get('title','')} {item.get('description','')}"
            if not is_trendforce_source(direct, base_text):
                continue
            dt = None
            if item.get("published_at_kst"):
                try:
                    dt = datetime.fromisoformat(item["published_at_kst"])
                except Exception:
                    pass
            if dt is not None and dt < cutoff:
                continue
            body = article_text(direct)
            full_text = clean_text(f"{base_text} {body}")
            if not is_relevant(full_text):
                continue
            components = extract_components(full_text)
            if direct.rstrip("/").endswith("weekly-radar-003"):
                cpu = components.setdefault("CPU", {})
                cpu.setdefault("status", "Tight")
                cpu.setdefault("current", "25-30")
                cpu.setdefault("balanced", "16-20")
            if direct.rstrip("/").endswith("weekly-radar-004"):
                # The 10/5 source is image-led; use the directly transcribed seven-row table
                # instead of allowing a partial HTML/index parse to inherit stale prior values.
                components = copy.deepcopy(WEEKLY_004_LOCK["components"])
            if direct.rstrip("/") == WEEKLY_006_LOCK["source"]:
                # The 10/19 screenshot shows all seven complete rows. Narrative snippets
                # must NOT downgrade HDD from Very Tight to Tight while 50 weeks holds.
                components = copy.deepcopy(WEEKLY_006_LOCK["components"])
            signals = extract_signals(full_text, direct)
            candidates.append(
                {
                    **item,
                    "direct_url": direct,
                    "full_text": full_text,
                    "components": components,
                    "signals": signals,
                    "nand_controller_direct_constraint": extract_nand_controller_direct_constraint(full_text),
                    "score": source_score(direct, components, full_text) + len(signals) * 3,
                }
            )

    candidates.sort(key=candidate_sort_key, reverse=True)
    best = candidates[0] if candidates else None

    previous_signals = previous.get("signals") or BASELINE.get("signals") or {}
    latest_components = copy.deepcopy(previous_components)
    latest_signals = copy.deepcopy(previous_signals)
    latest_source = previous.get("source") or BASELINE["source"]
    latest_as_of = previous.get("as_of") or BASELINE_DATE
    previous_chain = previous.get("memory_storage_chain") or {}
    controller_direct_confirmed = bool(previous_chain.get("nand_controller_direct_constraint_confirmed"))
    notify_text = ""
    if repaired_status_names:
        notify_text = build_status_correction_alert(
            raw_previous_components,
            weekly_002_components,
            repaired_status_names,
            str(weekly_002_previous.get("source") or BASELINE["source"]),
        )
    if repaired_004_components or repaired_004_signals:
        correction = build_weekly_004_correction_alert(
            weekly_002_components,
            weekly_004_previous.get("components") or BASELINE["components"],
            repaired_004_components,
            repaired_004_signals,
        )
        notify_text = (notify_text.rstrip() + "\n\n" + correction.strip()).strip() + "\n" if notify_text else correction
    if repaired_006_components:
        correction = build_weekly_006_correction_alert(before_006, previous_components, repaired_006_components)
        notify_text = (notify_text.rstrip() + "\n\n" + correction.strip()).strip() + "\n" if notify_text else correction
    new_seen = set(seen_urls)

    if best:
        url = best.get("direct_url") or ""
        published = best.get("published_at_kst") or ""
        if url:
            new_seen.add(url)
        extracted = best.get("components") or {}
        extracted_signals = best.get("signals") or {}
        candidate_controller_direct = bool(best.get("nand_controller_direct_constraint"))
        merged, evidence = merge_verified_weekly_components(previous_components, extracted)

        merged_signals = copy.deepcopy(previous_signals)
        merged_signals.update({k: v for k, v in extracted_signals.items() if v})
        changed = changed_components(previous_components, merged)
        changed_signals = [
            name for name, value in extracted_signals.items()
            if value and str(previous_signals.get(name) or "") != str(value)
        ]
        published_date = published[:10] if published else ""
        previous_as_of = str(previous.get("as_of") or BASELINE_DATE)
        is_new_url = bool(url and url not in seen_urls)
        is_new_release = bool(published_date and published_date > previous_as_of)
        if candidate_controller_direct and (is_new_url or is_new_release):
            controller_direct_confirmed = True
        exact_weekly_signal = (
            "current vs balanced" in (best.get("full_text") or "").lower()
            or "six ai infrastructure components" in (best.get("full_text") or "").lower()
            or "weekly radar" in (best.get("title") or "").lower()
        )

        # 이미 저장한 같은 주차/과거 주차 자료를 다시 파싱해 상태를 덮어쓰지 않는다.
        # 새 주차(발행일이 직전 기준일보다 뒤)일 때만 숫자·상태·원인 신호를 승격한다.
        if is_new_release and (changed or changed_signals):
            fresh_alert = build_alert(
                previous_components,
                merged,
                changed,
                url,
                published,
                signal_only=False,
                signals=merged_signals,
                # 새 Weekly Radar에서는 이번 주 확인된 원인·병목 신호를 모두 보여준다.
                changed_signals=[name for name in ("CPU", "GPU", "DRAM", "NAND(eSSD)", "HDD", "ABF", "MLCC") if name in extracted_signals],
                evidence=evidence,
            )
            notify_text = (notify_text.rstrip() + "\n\n" + fresh_alert.strip()).strip() + "\n" if notify_text else fresh_alert
            latest_components = merged
            latest_signals = merged_signals
            latest_source = url or latest_source
            latest_as_of = published_date
        elif is_new_release and is_new_url and exact_weekly_signal:
            fresh_alert = build_alert(
                previous_components,
                merged,
                [],
                url,
                published,
                signal_only=True,
                signals=extracted_signals,
                changed_signals=[name for name in ("CPU", "GPU", "DRAM", "NAND(eSSD)", "HDD", "ABF", "MLCC") if name in extracted_signals],
                evidence=evidence,
            )
            notify_text = (notify_text.rstrip() + "\n\n" + fresh_alert.strip()).strip() + "\n" if notify_text else fresh_alert
            latest_signals = merged_signals
            latest_source = url or latest_source
            latest_as_of = published_date

    latest_chain = memory_storage_chain_state(
        latest_components,
        latest_signals,
        nand_controller_direct_constraint_confirmed=controller_direct_confirmed,
    )
    if (
        latest_chain.get("active")
        and (
            not previous_chain.get("active")
            or int(previous_chain.get("version") or 0) < int(latest_chain.get("version") or 1)
            or (
                latest_chain.get("nand_controller_direct_constraint_confirmed")
                and not previous_chain.get("nand_controller_direct_constraint_confirmed")
            )
        )
        and str(latest_source or "").rstrip("/").endswith("weekly-radar-004")
    ):
        chain_alert = build_memory_storage_chain_alert(latest_chain, latest_components, str(latest_source or ""))
        notify_text = (notify_text.rstrip() + "\n\n" + chain_alert.strip()).strip() + "\n" if notify_text else chain_alert

    vendor_items = []
    for query in MLCC_VENDOR_QUERIES:
        try:
            for item in read_rss("google_news", query)[:12]:
                url = candidate_url(item)
                if url and mlcc_vendor_trusted_url(url):
                    vendor_items.append({**item, "direct_url": url})
        except Exception as exc:
            errors.append("mlcc_vendor_source:" + type(exc).__name__)
    vendor_state, vendor_events = mlcc_vendor_update(
        previous.get("mlcc_vendor_watch") or {}, vendor_items,
    )
    for ev in vendor_events:
        block = mlcc_vendor_notice(ev, vendor_state, latest_components)
        notify_text = (notify_text.rstrip() + "\n\n" + block).strip() if notify_text else block
    caspa_state, caspa_notice = caspa_panel_update(
        previous.get("caspa_panel_watch") or {},
        pending.get("usdkrw") or state.get("usdkrw") or {},
    )
    if caspa_notice:
        notify_text = (notify_text.rstrip() + "\n\n" + caspa_notice).strip() if notify_text else caspa_notice

    pending["ai_component_leadtime"] = {
        "as_of": latest_as_of,
        "source": latest_source,
        "components": latest_components,
        "signals": latest_signals,
        "memory_storage_chain": latest_chain,
        "ubs_project_leadtime_baseline": copy.deepcopy(UBS_PROJECT_LEADTIME_BASELINE),
        "seen_urls": sorted(new_seen)[-120:],
        "last_checked_at_kst": now.isoformat(timespec="seconds"),
        "candidate_count": len(candidates),
        "mlcc_vendor_watch": vendor_state,
        "caspa_panel_watch": caspa_state,
        "image_verified_issue": "weekly-radar-006" if latest_source.rstrip("/") == WEEKLY_006_LOCK["source"] else "",
        "errors": errors[-10:],
    }
    write_json(PENDING_PATH, pending)

    if notify_text:
        existing = ALERT_PATH.read_text(encoding="utf-8").strip() if ALERT_PATH.exists() else ""
        merged_alert = (existing + "\n\n" + notify_text.strip()).strip() if existing else notify_text.strip()
        ALERT_PATH.write_text(merged_alert + "\n", encoding="utf-8")

    print(
        "ai_component_leadtime_watch=true "
        f"candidates={len(candidates)} notify={str(bool(notify_text)).lower()} "
        f"source={best.get('direct_url') if best else 'none'}"
    )


if __name__ == "__main__":
    main()
