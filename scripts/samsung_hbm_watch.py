from __future__ import annotations

import hashlib
import html
import json
import os
import pathlib
import re
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
import requests
import math
import subprocess
import base64
import time
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from email.utils import parsedate_to_datetime
from zoneinfo import ZoneInfo
from hbm_trade_integrity import TradeEvidence, choose_exact_row
from hbm_trade_unit_reference import fetch_reference, SHEET_URL as KSTAT_SHEET_URL

try:
    from googlenewsdecoder import gnewsdecoder
except Exception:
    gnewsdecoder = None

ROOT = pathlib.Path(__file__).resolve().parents[1]
STATE = ROOT / "data" / "samsung_hbm_watch_state.json"
OUT = ROOT / "out"
OUT.mkdir(exist_ok=True)
ALERT = OUT / "samsung_hbm_alert.html"
STATUS = OUT / "samsung_hbm_status.md"

UA = "Mozilla/5.0 (compatible; khs-watch/1.0; +https://github.com/qedgwangju-dot/khs-watch)"
FRESH_HOURS = 96
MONTHLY_DAY = 1
OFFICIAL_UNPUBLISHED_POLL_HOURS = 3
OFFICIAL_ERROR_POLL_HOURS = 1
OFFICIAL_PUBLISHED_POLL_HOURS = 24
OFFICIAL_ERROR_RENOTIFY_HOURS = 6
OFFICIAL_PUBLICATION_EXPECTED_DAY = 15
OFFICIAL_SOURCE_HEALTH_VERSION = 4
EXPORT_ALERT_FORMAT_VERSION = 4
COMPARE_VERSION = 5
EVENT_STATE_VERSION = 2
SHARE_TRACK_VERSION = 1
BROKER_FORECAST_TRACK_VERSION = 3
CAPITAL_RETURN_TRACK_VERSION = 1
SAMSUNG_HBM4_PRICE_TRACK_VERSION = 3
SHARE_REVISION_THRESHOLD_PP = 3.0
BROKER_ASP_REVISION_THRESHOLD_PP = 5.0
SHARE_ACTUAL_DEVIATION_THRESHOLD_PP = 5.0
SHARE_PARITY_GAP_PP = 5.0
OPS_TRACK_VERSION = 1
YIELD_ALERT_THRESHOLD_PP = 5.0
EXPORT_UNIT_PRICE_REVISION_PCT = 1.0
KCS_ITEM_URL = "https://tradedata.go.kr/cts/hmpg/retrieveTrade.do"
DATA_GO_ITEM_URL = "https://apis.data.go.kr/1220000/Itemtrade/getItemtradeList"
DATA_GO_SIDO_ITEM_URL = "https://apis.data.go.kr/1220000/sidoitemtrade/getSidoitemtradeList"
DATA_GO_COUNTRY_ITEM_URL = "https://apis.data.go.kr/1220000/nitemtrade/getNitemtradeList"
DATA_GO_KEY = urllib.parse.unquote((os.getenv("KCS_DATA_GO_SERVICE_KEY") or "").strip())
KCS_REGION_URL = "https://tradedata.go.kr/cts/hmpg/retrieveTradeRegion.do"
HBM_HSK10 = "8542323000"
REGION_HS6 = "854232"
MALAYSIA_COUNTRY_CODE = "MY"
KCS_SOURCE_PAGE = "https://tradedata.go.kr/cts/index.do"
REGIONS = {
    "samsung_chungnam": {"name": "충남", "kind": "sido", "sido": "44", "sgg": ""},
    "hynix_chungbuk": {"name": "충북", "kind": "sido", "sido": "43", "sgg": ""},
    "hynix_icheon": {"name": "이천", "kind": "sgg", "sido": "41", "sgg": "41500"},
}

# Bind both regional series to the public K-stat monthly USD request scope.
# Preserve its response-echo identity limit and never infer a scale by magnitude.
_TRADE_EVIDENCE = None
_SIDO_SOURCE_RESULT = None
_SIDO_KSTAT_REFERENCE_CACHE = {}


def _start_trade_evidence():
    global _TRADE_EVIDENCE, _SIDO_SOURCE_RESULT, _SIDO_KSTAT_REFERENCE_CACHE
    _SIDO_SOURCE_RESULT = None
    _SIDO_KSTAT_REFERENCE_CACHE = {}
    try:
        code_sha = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True, timeout=5).strip()
    except Exception:
        code_sha = "unverified"
    _TRADE_EVIDENCE = TradeEvidence(OUT / "hbm_export_source_evidence.json", code_sha=code_sha,
                                  credential_env_names=("KCS_DATA_GO_SERVICE_KEY", "TELEGRAM_BOT_TOKEN", "GITHUB_TOKEN", "TELEGRAM_CHAT_ID"))
    _TRADE_EVIDENCE.write()


def _select_trade_response(response, rows, month, *, hs=HBM_HSK10, region=None, country=None,
                           value_fields=("expDlr",), unit="usd", unit_proof=None, weight_fields=("expWgt", "expTtwg")):
    selected, error = choose_exact_row(rows, month, hs, region=region, country=country,
                                      value_fields=value_fields, unit=unit, unit_proof=unit_proof,
                                      weight_fields=weight_fields)
    attempt = getattr(response, "_hbm_trade_attempt_id", None)
    if selected is not None:
        selected["evidence_attempt_id"] = attempt
    if _TRADE_EVIDENCE is not None and attempt:
        _TRADE_EVIDENCE.mark_selection(attempt, selected, error)
    if selected is not None and selected["amount_usd"] is None:
        return None, "응답 단위 검증 오류: 공식 단위 표기와 기존 변환계수 충돌"
    if error:
        label = "데이터 없음" if error.startswith("missing:") else "응답 검증 오류"
        return None, label + ": " + error
    return selected, ""


def _xml_rows(root):
    rows = []
    for item in _xml_items(root):
        row = {}
        for child in item:
            name = str(child.tag).split("}")[-1]
            if name in row or len(child):
                raise ValueError("duplicate or nested trade XML field")
            row[name] = child.text
        rows.append(row)
    return rows

SAMSUNG_HBM4_OFFICIAL = "https://news.samsung.com/global/samsung-ships-industry-first-commercial-hbm4-with-ultimate-performance-for-ai-computing"
SAMSUNG_HBM4E_OFFICIAL = "https://news.samsung.com/global/samsung-electronics-begins-shipment-of-industry-first-hbm4e-samples"
COUNTERPOINT_HBM_SHARE = "https://counterpointresearch.com/en/insights/global-dram-and-hbm-market-share"
BERNSTEIN_EXPORT = "https://www.investing.com/news/company-news/samsung-leads-hbm4-shipments-as-korea-export-data-shows-strength--report-93CH-4871213"
LS_HBM4_MIX = "https://en.sedaily.com/finance/2026/08/31/ls-securities-cuts-sk-hynix-target-27-percent-raises"
INTEL_EMIB_OFFICIAL = "https://www.intel.com/content/www/us/en/foundry/packaging.html"
INTEL_MALAYSIA_OFFICIAL = "https://newsroom.intel.com/intel-foundry/updates-intel-10-largest-construction-projects"

# User-provided J.P. Morgan figure: HBM market share by sales.
# These are seeded as baselines only; adding the tracker must not itself create an alert.
SHARE_FORECAST_BASELINES = {
    "jpmorgan|sales|2026": {"skhynix": 46.0, "samsung": 34.0, "micron": 20.0, "source": "사용자 제공 J.P. Morgan 차트"},
    "jpmorgan|sales|2027": {"skhynix": 41.0, "samsung": 39.0, "micron": 21.0, "source": "사용자 제공 J.P. Morgan 차트"},
    "jpmorgan|sales|2028": {"skhynix": 42.0, "samsung": 37.0, "micron": 21.0, "source": "사용자 제공 J.P. Morgan 차트"},
}

# Counterpoint official 2Q26 actual HBM revenue-share baseline.
SHARE_ACTUAL_BASELINES = {
    "counterpoint|sales|2026Q2": {"skhynix": 50.0, "samsung": 33.0, "micron": 18.0, "source": "Counterpoint 2026-09-03"},
}

# User-provided J.P. Morgan 2026-09-18 Samsung Electronics 3Q preview.
# Seed current facts so the integration itself does not backfill/re-alert the report.
BROKER_FORECAST_BASELINES = {
    "jpmorgan|samsung|2027": {
        "asp_yoy_pct": 64.0,
        "previous_asp_yoy_pct": 48.0,
        "stack_mainstream": "12hi",
        "contract_stage": "final_stage",
        "eps_revision_pct": {"2026": -4.0, "2027": -4.6},
        "fx_headwind": True,
        "source": "사용자 제공 J.P. Morgan 2026-09-18 리포트",
        "observed_at": "baseline",
    },
    "kb|samsung|2027": {
        "asp_yoy_pct": 100.0,
        "asp_is_floor": True,
        "hbm4_revenue_mix_current_pct": 40.0,
        "hbm4_revenue_mix_next_pct": 80.0,
        "source": "KB증권 2026-10-01 전망 인용",
        "observed_at": "baseline",
    },
}

SAMSUNG_HBM4_PRICE_BASELINE = {
    "price_multiple_vs_hbm3e": 3.0,
    "price_premium_vs_hbm3e_pct": 200.0,
    "reference_hbm3e_usd_per_gb": 1.5,
    "offered_price_band": "mid_to_high_4_usd_per_gb",
    "contract_stage": "negotiating",
    "stack_height": "unspecified",
    "usd_per_gb": None,
    "customer": "",
    "body_verified": True,
    "source": "매일경제",
    "source_url": "https://www.mk.co.kr/news/business/12167424",
    "as_of": "2026-10-02",
    "observed_at": "2026-10-02T17:32:00+09:00",
    "title": "삼성 \"최고성능 HBM4 자신감, 협상력 확대\"… 가격 프리미엄 강공",
    "note": "3배 이상은 2027 HBM4 제시가격을 현재 주력 HBM3E 약 1.5달러/Gb와 비교한 제품간 가격배수다. 전년 대비 HBM4 가격상승률로 해석하지 않으며, 4달러대 중후반은 제시·협상 가격이지 체결가격이 아니다.",
}

CAPITAL_RETURN_BASELINE = {
    "broker_next_3y_return_krw_trn": 600.0,
    "broker_prior_3y_return_krw_trn": 140.0,
    "broker_assumed_fcf_return_pct": 50.0,
    "broker_2026_op_profit_krw_trn": 368.0,
    "broker_2027_op_profit_krw_trn": 555.0,
    "broker_h2_quarterly_op_profit_floor_krw_trn": 100.0,
    "official_policy_period": "2024-2026",
    "official_fcf_return_pct": 50.0,
    "official_annual_dividend_krw_trn": 9.8,
    "official_2024_2025_return_krw_trn": 29.3,
    "official_2026_return_min_krw_trn": 90.0,
    "official_2026_return_max_krw_trn": 110.0,
    "source": "KB증권 전망 + 삼성전자 공식 주주환원 정책",
    "source_url": "https://www.hankyung.com/article/2026100162116",
    "official_source_url": "https://www.samsung.com/sec/ir/stock-information/shareholder-return/",
    "as_of": "2026-10-01",
}

# Structured operating baselines. These are seeded only to prevent a repeat
# alert for facts already supplied/verified; future changes are compared
# against these states.
OPS_BASELINES = {
    "samsung|hbm4|yield": {
        "value": 80.0,
        "unit": "pct",
        "period": "2026-09",
        "source": "서울경제 보도 기준선",
        "evidence": "reported",
    },
}
EXPORT_UNIT_PRICE_BASELINES = {
    "2026-03": 40.68,
    "2026-04": 53.04,
    "2026-05": 58.21,
    "2026-06": 69.51,
    "2026-07": 76.14,
    "2026-08": 73.39,
}

SHARE_INSTITUTIONS = {
    "jpmorgan": ("j.p. morgan", "jp morgan", "jpmorgan", "jpm"),
    "kb": ("kb securities", "kb증권", "kb securities co"),
    "ubs": ("ubs",),
    "morgan_stanley": ("morgan stanley", "모건스탠리"),
    "citi": ("citi", "citigroup", "씨티"),
    "bofa": ("bank of america", "bofa", "boa", "뱅크오브아메리카"),
    "goldman_sachs": ("goldman sachs", "골드만삭스"),
    "counterpoint": ("counterpoint", "카운터포인트"),
    "trendforce": ("trendforce", "트렌드포스"),
    "idc": ("idc",),
}

QUERIES = [
    '"Samsung" HBM4 HBM4E NVIDIA qualification shipment mass production',
    '"Samsung Electronics" HBM market share Counterpoint',
    '"Samsung" HBM Bernstein export Chungcheong revenue',
    '"Samsung" HBM4 shipment share mix LS Securities',
    '"Samsung" HBM Broadcom AMD NVIDIA Google custom HBM',
    '"삼성전자" HBM4 HBM4E 엔비디아 공급 출하 점유율',
    '"삼성전자" HBM4 HBM4E 생산 증산 생산능력 캐파',
    '"삼성전자" HBM4 4E 생산 2배',
    '"삼성전자" HBM 생산능력 증설 내년',
    '"Samsung Electronics" HBM4 HBM4E production capacity double expand',
    '"Samsung" HBM production capacity output ramp expansion',
    '"Samsung" HBM4 yield 80% production yield',
    '"삼성전자" HBM4 수율 80% 황금수율',
    '"HBM 수출단가" 한국무역협회',
    '"HBM 평균 수출단가" 73.39 76.14',
    '"HBM export unit price" Korea 73.39',
    '"삼성전자" HBM 충남 수출 Bernstein',
    '"SK hynix" HBM Bernstein export Chungbuk Icheon',
    '"SK하이닉스" HBM 충북 이천 수출 Bernstein',
    '"South Chungcheong" "North Chungcheong" Icheon HBM export',
    '"Icheon" "SK hynix" (HBM OR memory OR semiconductor) (export OR shipment OR revenue)',
    '"이천" "SK하이닉스" (HBM OR 메모리 OR 반도체) (수출 OR 출하 OR 매출)',
    '"이천" 반도체 수출 한국무역협회',
    '"이천" 반도체 수출 TRASS',
    '"이천" HBM Bernstein',
    '"Intel Malaysia" EMIB HBM advanced packaging Penang Kulim',
    '"Malaysia" HBM EMIB Intel advanced packaging',
    '"말레이시아" HBM Intel EMIB 첨단 패키징 Penang Kulim',
    '"Malaysia" HBM advanced packaging ASE Penang expansion',
    '"TF-AMD" Malaysia advanced packaging HBM Batu Kawan',
    '"Malaysia Advanced Packaging Consortium" HBM4 prototype',
    '"MAPC" HBM4 Malaysia prototype validation',
    '"J.P. Morgan" HBM market share Samsung SK hynix Micron',
    '"JP Morgan" HBM share 2027 Samsung SK hynix',
    '"J.P. Morgan" Samsung HBM ASP 2027 12Hi',
    '"JP Morgan" Samsung HBM average selling price 2027 mix 12-Hi',
    '"삼성전자" HBM 평균판매단가 J.P. Morgan 12단 2027',
    '"Samsung Electronics" HBM blended ASP FY27 12Hi JPMorgan',
    '"삼성전자" KB증권 HBM 판매 가격 100% HBM4 매출 비중 40 80',
    '"Samsung Electronics" "KB Securities" HBM ASP 2027 HBM4 revenue mix',
    '"삼성전자" 주주환원 600조 FCF 50% KB증권',
    '"Samsung Electronics" shareholder return FCF 50% 2027 2029 new policy',
    '"삼성" HBM4 내년 가격 3배',
    '"삼성전자" HBM4 2027 가격 협상 계약 3배',
    '"Samsung" HBM4 2027 price triple negotiation contract',
    '"Samsung Electronics" HBM4 2027 price agreement per Gb',
    '"UBS" HBM market share Samsung SK hynix Micron',
    '"Morgan Stanley" HBM market share Samsung SK hynix Micron',
    '"Citi" HBM market share Samsung SK hynix Micron',
    '"BofA" HBM market share Samsung SK hynix Micron',
    '"Goldman Sachs" HBM market share Samsung SK hynix Micron',
    '"Counterpoint" HBM market share Samsung SK hynix Micron',
    '"TrendForce" HBM market share Samsung SK hynix Micron',
    '"HBM 점유율" 삼성전자 SK하이닉스 Micron 전망',
]

TRUSTED = (
    "samsung", "reuters", "bloomberg", "trendforce", "counterpoint", "investing.com",
    "sedaily", "seoul economic", "서울경제", "seoul newspaper", "서울신문",
    "zdnet", "the elec", "thelec", "digitimes",
    "yonhap", "연합뉴스", "chosunbiz", "조선비즈", "newsis", "뉴시스",
    "kita", "한국무역협회", "k-stat", "trass", "한국무역통계진흥원",
    "customs", "관세청", "icheon", "이천시", "intel", "ase", "tf-amd", "tf amd",
    "mapc", "mosti", "mida", "the edge malaysia",
    "j.p. morgan", "jp morgan", "jpmorgan", "kb securities", "kb증권", "ubs", "morgan stanley", "citi", "bofa", "goldman sachs",
    "hankyung", "한국경제", "mk.co.kr", "매일경제",
)

LOW_VALUE = ("aol", "finance.biggo", "24/7 wall st", "247wallst", "cryptobriefing")


def fetch(url: str, timeout: int = 25) -> bytes:
    req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept": "text/html,application/xhtml+xml"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.read()


def clean(value: str) -> str:
    value = html.unescape(value or "")
    value = re.sub(r"<[^>]+>", " ", value)
    return re.sub(r"\s+", " ", value).strip()


def parse_pub(value: str) -> datetime | None:
    try:
        dt = parsedate_to_datetime(value)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(ZoneInfo("Asia/Seoul"))
    except Exception:
        return None


def rss_url(query: str, lang: str) -> str:
    q = urllib.parse.quote(query)
    if lang == "ko":
        return f"https://news.google.com/rss/search?q={q}&hl=ko&gl=KR&ceid=KR:ko"
    return f"https://news.google.com/rss/search?q={q}&hl=en-US&gl=US&ceid=US:en"


def decode_google(link: str) -> str:
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


def event_id(title: str, source: str) -> str:
    return hashlib.sha256(f"{title}|{source}".encode()).hexdigest()[:24]


def source_rank(source: str) -> int:
    low = (source or "").lower()
    if "samsung" in low or "삼성전자" in low:
        return 100
    if "intel" in low:
        return 98
    if "reuters" in low:
        return 95
    if any(x in low for x in ("j.p. morgan", "jp morgan", "jpmorgan", "kb securities", "kb증권", "ubs", "morgan stanley", "citi", "bofa", "goldman sachs")):
        return 92
    if "hankyung" in low or "한국경제" in low:
        return 82
    if "mk.co.kr" in low or "매일경제" in low:
        return 82
    if "counterpoint" in low or "trendforce" in low:
        return 90
    if "bloomberg" in low or "digitimes" in low:
        return 85
    if "investing.com" in low or "sedaily" in low or "seoul economic" in low or "서울경제" in low:
        return 80
    if "seoul newspaper" in low or "서울신문" in low:
        return 75
    if "zdnet" in low or "thelec" in low or "the elec" in low or "yonhap" in low or "연합뉴스" in low:
        return 75
    return 20


def relevant(text: str) -> bool:
    low = text.lower()
    company = (
        "samsung" in low or "삼성전자" in low or "삼성" in low
        or "sk hynix" in low or "sk하이닉스" in low
    )
    hbm = "hbm" in low
    signal = any(k in low for k in (
        "shipment", "ship", "mass production", "qualification", "validation", "customer",
        "market share", "revenue", "export", "mix", "allocation", "contract", "price",
        "production", "capacity", "output", "ramp", "expand", "expansion", "double",
        "wafer", "investment", "capex", "yield", "unit price", "export price",
        "출하", "양산", "인증", "검증", "고객", "점유율", "매출", "수출", "비중", "계약", "가격",
        "생산", "증산", "생산능력", "캐파", "확대", "증설", "2배", "웨이퍼", "투입", "설비투자",
        "수율", "수출단가", "평균 수출단가",
    ))
    icheon_proxy = (
        ("icheon" in low or "이천" in low)
        and ("sk hynix" in low or "sk하이닉스" in low or "semiconductor" in low or "반도체" in low or "memory" in low or "메모리" in low)
        and any(k in low for k in ("export", "shipment", "revenue", "production", "수출", "출하", "매출", "생산"))
    )
    malaysia_proxy = (
        any(k in low for k in ("malaysia", "말레이시아", "penang", "kulim"))
        and any(k in low for k in ("hbm", "emib", "advanced packaging", "첨단 패키징", "packaging"))
        and any(k in low for k in (
            "shipment", "export", "production", "capacity", "investment", "expand", "ramp",
            "prototype", "pilot", "validation", "test facility", "qualification",
            "출하", "수출", "생산", "캐파", "투자", "증설", "양산", "프로토타입", "시제품", "실증", "검증", "테스트 시설"
        ))
    )
    price_proxy = (
        "hbm" in low
        and any(k in low for k in ("unit price", "export price", "수출단가", "평균 수출단가"))
        and any(k in low for k in ("korea", "한국", "export", "수출", "kita", "한국무역협회"))
    )
    capital_proxy = (
        ("samsung" in low or "삼성전자" in low or "삼성" in low)
        and any(k in low for k in ("shareholder return", "shareholder-return", "fcf", "free cash flow", "dividend", "buyback", "주주환원", "잉여현금흐름", "배당", "자사주"))
        and any(k in low for k in ("policy", "program", "return", "50%", "600", "140", "90", "110", "정책", "환원", "소각"))
    )
    return (company and hbm and signal) or icheon_proxy or malaysia_proxy or price_proxy or capital_proxy


def read_events() -> list[dict]:
    rows: dict[str, dict] = {}
    for query in QUERIES:
        for lang in ("en", "ko"):
            try:
                root = ET.fromstring(fetch(rss_url(query, lang)))
            except Exception:
                continue
            for item in root.findall("./channel/item"):
                title = clean(item.findtext("title") or "")
                desc = clean(item.findtext("description") or "")
                link = clean(item.findtext("link") or "")
                source_node = item.find("source")
                source = clean(source_node.text if source_node is not None and source_node.text else "")
                pub = parse_pub(clean(item.findtext("pubDate") or ""))
                if not title or not link or not relevant(f"{title} {desc}"):
                    continue
                low_source = source.lower()
                if any(x in low_source for x in LOW_VALUE):
                    continue
                if not any(x in low_source for x in TRUSTED):
                    continue
                direct = decode_google(link)
                if not direct:
                    continue
                key = event_id(title, source)
                rows[key] = {
                    "id": key,
                    "title": title,
                    "description": desc,
                    "source": source or "출처 미표시",
                    "published_at_kst": pub.isoformat(timespec="seconds") if pub else "",
                    "direct_link": direct,
                    "rank": source_rank(source),
                }
    return sorted(rows.values(), key=lambda x: x.get("published_at_kst") or "")


def load_state() -> dict:
    try:
        return json.loads(STATE.read_text(encoding="utf-8"))
    except Exception:
        return {"seen_ids": [], "last_monthly_digest": ""}


def save_state(obj: dict) -> None:
    STATE.parent.mkdir(exist_ok=True)
    STATE.write_text(json.dumps(obj, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def href(url: str, label: str = "원문") -> str:
    return f'<a href="{html.escape(url, quote=True)}">{html.escape(label)}</a>'


def krw_large(usd: float, rate: float | None) -> str:
    if rate is None:
        return "원화 환산 확인 불가"
    eok = int(round(usd * rate / 100_000_000))
    if eok >= 10000:
        jo, rem = divmod(eok, 10000)
        return f"약 {jo:,}조{rem:,}억원" if rem else f"약 {jo:,}조원"
    return f"약 {eok:,}억원"


def fx_quote() -> tuple[float | None, str]:
    try:
        from fx_api import daily_krw
        q = daily_krw()
        return q.rate, q.basis
    except Exception as exc:
        return None, f"환율 확인 실패: {type(exc).__name__}"



def _month_shift(yyyymm: str, delta: int) -> str:
    y, m = int(yyyymm[:4]), int(yyyymm[4:])
    idx = y * 12 + (m - 1) + delta
    return f"{idx // 12:04d}{idx % 12 + 1:02d}"


def _previous_month(now: datetime) -> str:
    return _month_shift(now.strftime("%Y%m"), -1)


def _number(value) -> float | None:
    if value is None:
        return None
    s = str(value).strip().replace(",", "")
    if not s or s in ("-", "null", "None"):
        return None
    try:
        result = float(s)
        return result if math.isfinite(result) else None
    except Exception:
        return None


def _walk_dicts(obj):
    if isinstance(obj, dict):
        yield obj
        for v in obj.values():
            yield from _walk_dicts(v)
    elif isinstance(obj, list):
        for v in obj:
            yield from _walk_dicts(v)


def _safe_error(prefix: str, exc: Exception) -> str:
    # Never persist request URLs because they can contain the public-data service key.
    return f"{prefix}: {type(exc).__name__}"


def _is_transient_source_error(message: str) -> bool:
    text = (message or "").lower()
    return any(
        marker in text
        for marker in (
            "실패",
            "오류",
            "http ",
            "timeout",
            "connection",
            "parse",
            "json",
            "검증",
            "불일치",
            "단위",
        )
    )


def _request_with_retry(method: str, url: str, *, params=None, data=None, headers=None, attempts: int = 3, session=None):
    """Bounded retry for official endpoints.

    Network/service failures are retried, but permanent 4xx/auth errors are
    returned to the caller so they can be classified explicitly.  Never
    retries forever and never substitutes stale data after a failure.
    """
    last_exc = None
    client = session or requests
    for attempt in range(1, attempts + 1):
        started = datetime.now(timezone.utc).isoformat()
        recorded = False
        try:
            response = client.request(
                method,
                url,
                params=params,
                data=data,
                headers=headers,
                timeout=(5, 15),
            )
            if _TRADE_EVIDENCE is not None:
                response._hbm_trade_attempt_id = _TRADE_EVIDENCE.record_attempt(
                    method, url, params=params, data=data, status=response.status_code,
                    raw_bytes=response.content, started_at=started,
                    completed_at=datetime.now(timezone.utc).isoformat(),
                    response_headers={"Content-Type": getattr(response, "headers", {}).get("Content-Type", "")})
                recorded = True
            if response.status_code in (429, 500, 502, 503, 504):
                if attempt < attempts:
                    time.sleep(1.5 * attempt)
                    continue
                response.raise_for_status()
            return response
        except (requests.Timeout, requests.ConnectionError, requests.HTTPError) as exc:
            last_exc = exc
            if _TRADE_EVIDENCE is not None and not recorded:
                _TRADE_EVIDENCE.record_attempt(method, url, params=params, data=data,
                    error_type=type(exc).__name__, started_at=started, completed_at=datetime.now(timezone.utc).isoformat())
            if attempt < attempts:
                time.sleep(1.5 * attempt)
        except Exception:
            raise
    raise last_exc or RuntimeError("request failed")


def _xml_text(item, *names):
    wanted = set(names)
    for name in names:
        val = item.findtext(name)
        if val not in (None, ""):
            return val
    for child in item.iter():
        tag = str(child.tag).split("}")[-1]
        if tag in wanted and child.text not in (None, ""):
            return child.text
    return None


def _xml_items(root):
    return [node for node in root.iter() if str(node.tag).split("}")[-1] == "item"]


def fetch_data_go_item_month(month: str) -> tuple[dict | None, str]:
    if not DATA_GO_KEY:
        return None, "공공데이터포털 API 키 미설정"
    params = {
        "serviceKey": DATA_GO_KEY,
        "strtYymm": month,
        "endYymm": month,
        "hsSgn": HBM_HSK10,
    }
    try:
        r = _request_with_retry("GET", DATA_GO_ITEM_URL, params=params)
        r.raise_for_status()
        root = ET.fromstring(r.content)
        rows = _xml_rows(root)
    except Exception as exc:
        return None, _safe_error("공공데이터포털 전국 API 실패", exc)
    code = _xml_text(root, "resultCode")
    msg = _xml_text(root, "resultMsg") or ""
    if code != "00":
        return None, "공공데이터포털 전국 API 오류: resultCode가 정상 00이 아님"

    selected, err = _select_trade_response(r, rows, month,
        unit_proof={"source": DATA_GO_ITEM_URL, "field": "expDlr", "unit": "USD"})
    if selected:
        selected.update(source="공공데이터포털 관세청 품목별 수출입실적 API", api=True)
    return selected, f"공공데이터포털 전국 API {month} {err}" if err else ""


def _fetch_data_go_sido_raw(month: str, sido_cd: str):
    if not DATA_GO_KEY:
        return None, [], "공공데이터포털 API 키 미설정"
    params = {
        "serviceKey": DATA_GO_KEY,
        "strtYymm": month,
        "endYymm": month,
        "sidoCd": sido_cd,
        "hsSgn": HBM_HSK10,
    }
    try:
        r = _request_with_retry("GET", DATA_GO_SIDO_ITEM_URL, params=params)
        r.raise_for_status()
        root = ET.fromstring(r.content)
        rows = _xml_rows(root)
    except Exception as exc:
        return None, [], _safe_error("공공데이터포털 시도 API 실패", exc)
    code = _xml_text(root, "resultCode")
    msg = _xml_text(root, "resultMsg") or ""
    if code != "00":
        return None, [], "공공데이터포털 시도 API 오류: resultCode가 정상 00이 아님"
    return r, rows, ""


def _kstat_reference_selection(reference):
    if not _kstat_sido_source_proof(reference):
        return None
    return {
        "provider": reference["provider"],
        "month": reference["month"],
        "hs": reference["hs"],
        "unit": reference["unit"],
        "monthly_not_cumulative": reference["monthly_not_cumulative"],
        "request_scope_no_response_echo": reference["request_scope_no_response_echo"],
        "source_region_codes": reference["source_region_codes"],
        "amounts_usd": reference["amounts_usd"],
        "selected_rows": reference["selected_rows"],
        "source_sha256": reference["source_sha256"],
        "evidence_attempt_ids": reference.get("evidence_attempt_ids") or {},
    }


def _load_kstat_sido_reference(month=None):
    """Fetch one exact public K-stat month and preserve its two response ids."""
    global _SIDO_KSTAT_REFERENCE_CACHE
    key = month or "__latest__"
    if key in _SIDO_KSTAT_REFERENCE_CACHE:
        return _SIDO_KSTAT_REFERENCE_CACHE[key]
    reference_ids = []

    def request_reference(*args, **kwargs):
        response = _request_with_retry(*args, **kwargs)
        reference_ids.append(getattr(response, "_hbm_trade_attempt_id", None))
        return response

    reference, error = fetch_reference(request_reference, target_month=month)
    if reference:
        reference["evidence_attempt_ids"] = {
            "form": reference_ids[0] if reference_ids else None,
            "sheet": reference_ids[1] if len(reference_ids) > 1 else None,
        }
        if not _kstat_sido_source_proof(reference):
            result = (None, "invalid:K-stat 시·도 HSK10 원응답 계약 불완전")
            _SIDO_KSTAT_REFERENCE_CACHE[key] = result
            return result
        selection = _kstat_reference_selection(reference)
        if _TRADE_EVIDENCE is not None:
            form_attempt = reference["evidence_attempt_ids"]["form"]
            sheet_attempt = reference["evidence_attempt_ids"]["sheet"]
            if form_attempt:
                _TRADE_EVIDENCE.mark_selection(
                    form_attempt,
                    {"provider": reference["provider"], "month": reference["month"],
                     "hs": reference["hs"], "form_contract": "validated"},
                    validation_status="validated_request_form",
                )
            if sheet_attempt:
                _TRADE_EVIDENCE.mark_selection(
                    sheet_attempt, selection,
                    validation_status="selected_under_request_scoped_identity",
                )
        result = (reference, "")
        _SIDO_KSTAT_REFERENCE_CACHE[reference["month"]] = result
        if month is None:
            _SIDO_KSTAT_REFERENCE_CACHE["__latest__"] = result
    else:
        result = (None, error or "K-stat 시·도 HSK10 월별 조회 실패")
        _SIDO_KSTAT_REFERENCE_CACHE[key] = result
    return result


def _kstat_sido_source_proof(reference):
    if not isinstance(reference, dict) or (
        reference.get("provider") != "K-stat 한국무역협회"
        or reference.get("hs") != HBM_HSK10
        or reference.get("unit") != "usd"
        or reference.get("monthly_not_cumulative") is not True
        or reference.get("request_scope_no_response_echo") is not True
        or reference.get("source_region_codes") != {"44": "31", "43": "36"}
        or set(reference.get("amounts_usd") or {}) != {"44", "43"}
        or set(reference.get("selected_rows") or {}) != {"44", "43"}
        or not isinstance(reference.get("source_sha256"), dict)
        or set(reference["source_sha256"]) != {"form", "sheet"}
        or any(not re.fullmatch(r"[0-9a-f]{64}", str(v)) for v in reference["source_sha256"].values())
        or not isinstance(reference.get("evidence_attempt_ids"), dict)
        or any(not reference["evidence_attempt_ids"].get(k) for k in ("form", "sheet"))
    ):
        return None
    for customs, (row_code, region_name) in {"44": ("31", "충남"), "43": ("36", "충북")}.items():
        row = reference["selected_rows"].get(customs)
        try:
            amount = Decimal(str(reference["amounts_usd"][customs]))
        except Exception:
            return None
        if (not amount.is_finite() or amount <= 0 or not isinstance(row, dict)
                or row.get("ROW_CODE") != row_code or row.get("KOR_NAME") != region_name):
            return None
    return {
        "status": "official_kstat_request_scoped_source",
        "provider": reference["provider"],
        "month": reference["month"],
        "hs": reference["hs"],
        "unit": reference["unit"],
        "factor_to_usd": "1",
        "monthly_not_cumulative": True,
        "request_scope_no_response_echo": True,
        "source_region_codes": reference["source_region_codes"],
        "amounts_usd": reference["amounts_usd"],
        "reference_attempt_ids": [
            reference.get("evidence_attempt_ids", {}).get("form"),
            reference.get("evidence_attempt_ids", {}).get("sheet"),
        ],
        "reference_source_sha256": reference["source_sha256"],
        "identity_limit": reference["identity_limit"],
    }


def _fetch_kstat_sido_month(month: str, sido_cd: str):
    reference, error = _load_kstat_sido_reference(month)
    if error or reference is None:
        return None, error or f"K-stat 시·도 HSK10 {month} 조회 실패"
    if reference.get("month") != month:
        return None, f"K-stat 시·도 HSK10 기준월 불일치: 요청 {month}, 응답 범위 {reference.get('month')}"
    if sido_cd not in ("44", "43") or sido_cd not in reference.get("amounts_usd", {}):
        return None, f"K-stat 시·도 HSK10 지역 확인 실패: {sido_cd}"
    amount = reference["amounts_usd"][sido_cd]
    row = reference["selected_rows"][sido_cd]
    attempt_id = reference.get("evidence_attempt_ids", {}).get("sheet")
    return {
        "month": month,
        "hs": HBM_HSK10,
        "region_code": sido_cd,
        "raw_amount": float(amount),
        "raw_amount_text": str(amount),
        "raw_amount_decimal": str(amount),
        "raw_amount_field": "THIS_EXP_AMT",
        "raw_amount_unit": "usd",
        "amount_usd": float(amount),
        "weight_kg": None,
        "weight_status": "not_returned",
        "unit_proof": {"status": "kstat_selected_usd_contract", "unit": "usd", "factor_to_usd": "1"},
        "identity_proof": {
            "month": {"status": "request_scope_no_response_echo", "requested_month": month},
            "hs": {"status": "request_scope_no_response_echo", "requested_code": HBM_HSK10},
            "region": {"status": "response_echo_matched", "requested_code": sido_cd,
                       "response_fields": {"ROW_CODE": row["ROW_CODE"], "KOR_NAME": row["KOR_NAME"]}},
        },
        "selected_row": row,
        "source": "K-stat 한국무역협회(제공기관: 관세청)",
        "source_url": KSTAT_SHEET_URL,
        "scope": "regional_hsk10_request_scoped",
        "api": False,
        "evidence_attempt_id": attempt_id,
        "source_evidence_attempt_ids": reference.get("evidence_attempt_ids") or {},
        "source_sha256": reference.get("source_sha256") or {},
        "request_scope_no_response_echo": True,
        "identity_limit": reference.get("identity_limit"),
    }, ""


def _resolve_sido_source(month=None):
    """Prove the public K-stat request scope and its stated USD unit."""
    global _SIDO_SOURCE_RESULT
    if _SIDO_SOURCE_RESULT is not None:
        cached_proof, _cached_error = _SIDO_SOURCE_RESULT
        if cached_proof and (month is None or cached_proof.get("month") == month):
            return _SIDO_SOURCE_RESULT
    reference, error = _load_kstat_sido_reference(month)
    source_proof = _kstat_sido_source_proof(reference)
    if source_proof:
        _SIDO_SOURCE_RESULT = (source_proof, "")
        return _SIDO_SOURCE_RESULT
    # Do not cache a miss for a different month. A month absent from the form
    # may be awaiting publication while an older exact month remains available.
    return None, "지역 K-stat HSK10 월별 범위 검증 보류: " + (error or "원응답 계약 불일치")


def fetch_kstat_sido_month(month: str, sido_cd: str) -> tuple[dict | None, str]:
    proof, error = _resolve_sido_source(month)
    if proof is None:
        return None, error
    return _fetch_kstat_sido_month(month, sido_cd)


def fetch_data_go_sido_month(month: str, sido_cd: str) -> tuple[dict | None, str]:
    """Compatibility wrapper; production regional values use exact K-stat scope."""
    return fetch_kstat_sido_month(month, sido_cd)


def fetch_data_go_country_item_month(month: str, cnty_cd: str = MALAYSIA_COUNTRY_CODE) -> tuple[dict | None, str]:
    """Official Korea Customs country-by-item export data at HSK10 level."""
    if not DATA_GO_KEY:
        return None, "공공데이터포털 API 키 미설정"
    params = {
        "serviceKey": DATA_GO_KEY,
        "strtYymm": month,
        "endYymm": month,
        "hsSgn": HBM_HSK10,
        "cntyCd": cnty_cd,
    }
    try:
        r = _request_with_retry("GET", DATA_GO_COUNTRY_ITEM_URL, params=params)
        r.raise_for_status()
        root = ET.fromstring(r.content)
        rows = _xml_rows(root)
    except Exception as exc:
        return None, _safe_error(f"공공데이터포털 국가별 품목 API {cnty_cd} 실패", exc)
    code = _xml_text(root, "resultCode")
    msg = _xml_text(root, "resultMsg", "errMsg", "returnAuthMsg") or ""
    items = _xml_items(root)
    # Some Data.go gateways wrap the payload with XML namespaces or omit the
    # normal resultCode while still returning valid item rows. Prefer actual
    # rows over a missing header, but never accept a non-00 explicit error.
    if code not in (None, "", "00"):
        return None, f"공공데이터포털 국가별 품목 API {cnty_cd} 오류: resultCode가 정상 00이 아님"
    if not items and code != "00":
        return None, f"공공데이터포털 국가별 품목 API {cnty_cd} 응답형식 확인 필요: 정상 결과 코드·item 부재"

    selected, err = _select_trade_response(r, rows, month, country=cnty_cd,
        unit_proof={"source": "https://www.data.go.kr/data/15100475/openapi.do", "field": "expDlr", "unit": "USD"})
    if selected:
        selected.update(source="공공데이터포털 관세청 품목별 국가별 수출입실적 API", api=True)
    return selected, f"공공데이터포털 국가별 품목 API {cnty_cd} {month} {err}" if err else ""


def fetch_kcs_item_month(month: str, session) -> tuple[dict | None, str]:
    params = {
        "tradeKind": "ETS_MNK_1020000A",
        "priodKind": "MON",
        "priodFr": month + " ",
        "priodTo": month + " ",
        "statsBase": "acptDd",
        "ttwgTpcd": "1",
        "showPagingLine": "100",
        "sortColumn": "",
        "sortOrder": "",
        "hsSgnGrpCol": "HS10_SGN",
        "hsSgnWhrCol": "HS10_SGN",
        "hsSgn": HBM_HSK10,
    }
    headers = {
        "User-Agent": UA,
        "Accept": "application/json, text/javascript, */*; q=0.01",
        "Referer": KCS_SOURCE_PAGE,
        "Origin": "https://tradedata.go.kr",
        "X-Requested-With": "XMLHttpRequest",
        "isAjax": "true",
        "Content-Type": "application/x-www-form-urlencoded; charset=UTF-8",
    }
    try:
        r = _request_with_retry("POST", KCS_ITEM_URL, headers=headers, data=params, session=session)
        if r.status_code != 200:
            return None, f"전국 {month} KCS HTTP {r.status_code}"
        data = r.json()
    except Exception as exc:
        return None, _safe_error(f"전국 {month} KCS 조회 실패", exc)

    selected, err = _select_trade_response(r, data.get("items") or [], month,
        value_fields=("expUsdAmt",), unit="thousand_usd",
        unit_proof={"source": "https://tradedata.go.kr/cts/js/ets/hmpg/trade/ETS0100019Q.js",
                    "tradeKind": "ETS_MNK_1020000A", "ttwgTpcd": "1", "unit": "KG, thousand USD"})
    if selected:
        selected.update(source="관세청 수출입무역통계", api=False)
    return selected, f"전국 {month} KCS {err}" if err else ""


def fetch_kcs_region_month(month: str, region: dict, session=None) -> tuple[dict | None, str]:
    hs = REGION_HS6
    hs_col = "HS6_SGN"
    base = {
        "tradeKind": "ETS_MNK_1040000A",
        "priodKind": "MON",
        "priodFr": month,
        "priodTo": month,
        "statsBase": "acptDd",
        "sidoCd": region["sido"],
        "sggCd": region.get("sgg") or "",
        "imexTpcd": "EXP_TMPR_CD",
        "showPagingLine": "100",
        "sortColumn": "",
        "sortOrder": "",
        "hsSgnGrpCol": hs_col,
        "hsSgnWhrCol": hs_col,
        "hsSgn": hs,
    }
    headers = {
        "User-Agent": UA,
        "Accept": "application/json, text/javascript, */*; q=0.01",
        "Referer": KCS_SOURCE_PAGE,
        "Origin": "https://tradedata.go.kr",
        "X-Requested-With": "XMLHttpRequest",
        "isAjax": "true",
        "Content-Type": "application/x-www-form-urlencoded; charset=UTF-8",
    }
    sess = session or requests.Session()
    variants = [region["kind"]]
    if region["kind"] == "sido":
        variants += ["sgg"]

    last_preview = ""
    for kind in variants:
        params = dict(base)
        params["sidosggKind"] = kind
        try:
            r = _request_with_retry("POST", KCS_REGION_URL, headers=headers, data=params, session=sess)
            if r.status_code != 200:
                continue
            data = r.json()
        except Exception as exc:
            return None, _safe_error(f"{region['name']} {month} KCS 조회 실패", exc)
        last_preview = clean(json.dumps(data, ensure_ascii=False))[:400]
        items = data.get("items") or []
        if not items:
            continue

        selected, err = _select_trade_response(r, items, month, hs=hs, region=region,
            value_fields=("expUsdAmt",), unit="thousand_usd",
            unit_proof={"source": "https://tradedata.go.kr/cts/js/ets/hmpg/trade/ETS0100027Q.js",
                        "unit": "thousand USD", "scope": "HS6 memory diagnostics only"})
        if not selected:
            return None, f"{region['name']} {month} KCS {err}"
        if region.get("sgg"):
            raw_row = selected["selected_row"]
            if ((str(raw_row.get("sggCd") or "") != region["sgg"])
                    or (raw_row.get("sggNm") and raw_row["sggNm"] != region["name"])):
                return None, f"{region['name']} {month} KCS 응답 검증 오류: 시군구 불일치"
        selected.update(source="관세청 수출입무역통계", scope="regional_hs6_fallback",
                        scope_note="지역 공개자료는 HS6 854232 메모리 전체로, HBM 전용 HSK10이 아님")
        return selected, ""

    return None, f"{region['name']} {month} HS6 {hs} 미검출: {last_preview}"



def fetch_official_hbm_pack(now: datetime) -> tuple[dict | None, list[str]]:
    """Fetch the newest public official HBM-related trade pack.

    Exact nationwide MCP/HBM-containing series:
      HSK10 8542323000 from Korea Customs Service.
    Public regional direction:
      exact province HSK10 8542323000 for Chungnam and Chungbuk.
    Icheon is best-effort only because K-stat stopped public city/county HSK10
    disclosure from 2026-09-01; city/county HS6 weight is also non-public.
    """
    errors: list[str] = []
    optional_errors: list[str] = []
    availability_notes: list[str] = []
    current = _previous_month(now)
    data: dict[str, dict[str, dict]] = {}
    selected = None
    session = requests.Session()
    session.headers.update({"User-Agent": UA})

    required_keys = ("national_hsk10", "samsung_chungnam", "hynix_chungbuk")

    for candidate in [current, _month_shift(current, -1), _month_shift(current, -2)]:
        rows: dict[str, dict] = {}
        local_errors: list[str] = []

        national, nerr = fetch_data_go_item_month(candidate)
        if not national:
            national, nerr2 = fetch_kcs_item_month(candidate, session)
            if nerr2:
                nerr = f"{nerr}; fallback={nerr2}"
        if national:
            rows["national_hsk10"] = national
        else:
            local_errors.append(nerr)

        for key in ("samsung_chungnam", "hynix_chungbuk"):
            region = REGIONS[key]
            row, err = fetch_kstat_sido_month(candidate, region["sido"])
            if row:
                rows[key] = row
            else:
                # KCS regional fallback is HS6, not the same metric as the
                # K-stat province HSK10 series. Keep it as diagnostics only;
                # never silently substitute it for the exact company proxy.
                local_errors.append(err)
                fallback, fallback_err = fetch_kcs_region_month(candidate, region, session=session)
                if fallback:
                    rows[key + "_hs6_fallback"] = fallback
                elif fallback_err:
                    local_errors.append(fallback_err)

        malaysia, merr = fetch_data_go_country_item_month(candidate)
        if malaysia:
            rows["malaysia_hsk10"] = malaysia
        elif merr:
            optional_errors.append(merr)

        row, err = fetch_kcs_region_month(candidate, REGIONS["hynix_icheon"], session=session)
        if row:
            rows["hynix_icheon"] = row
        elif err:
            optional_errors.append(err)

        transient = [item for item in local_errors if _is_transient_source_error(item)]
        missing = [item for item in local_errors if not _is_transient_source_error(item)]
        if all(k in rows for k in required_keys):
            selected = candidate
            data[candidate] = rows
            errors.extend(transient)
            availability_notes.extend(missing)
            break
        errors.extend(transient)
        availability_notes.extend(missing)

        # Do not fall back to an older month when the newest candidate failed
        # because of a network/API error. Older months are only considered when
        # the current candidate explicitly has no published data.
        if transient:
            return None, errors

    if not selected:
        return None, errors or [f"공표 대기: {current} 및 이전 두 달의 필수 HSK10 원자료 없음"]

    needed = [selected, _month_shift(selected, -1), _month_shift(selected, -3), _month_shift(selected, -12)]
    for month in needed:
        if month in data:
            continue
        rows: dict[str, dict] = {}

        national, nerr = fetch_data_go_item_month(month)
        if not national:
            national, nerr2 = fetch_kcs_item_month(month, session)
            if nerr2:
                nerr = f"{nerr}; fallback={nerr2}"
        if national:
            rows["national_hsk10"] = national
        else:
            errors.append(nerr)

        for key in ("samsung_chungnam", "hynix_chungbuk"):
            region = REGIONS[key]
            row, err = fetch_kstat_sido_month(month, region["sido"])
            if row:
                rows[key] = row
            else:
                errors.append(err)
                fallback, fallback_err = fetch_kcs_region_month(month, region, session=session)
                if fallback:
                    rows[key + "_hs6_fallback"] = fallback
                elif fallback_err:
                    errors.append(fallback_err)

        malaysia, merr = fetch_data_go_country_item_month(month)
        if malaysia:
            rows["malaysia_hsk10"] = malaysia
        elif merr:
            optional_errors.append(merr)

        row, err = fetch_kcs_region_month(month, REGIONS["hynix_icheon"], session=session)
        if row:
            rows["hynix_icheon"] = row
        elif err:
            optional_errors.append(err)
        data[month] = rows

    # Newest, prior month and 3-month comparison must all have exact national
    # HSK10 plus both public province series. Icheon is optional.
    if any(not all(k in data.get(m, {}) for k in required_keys) for m in needed[:3]):
        return None, errors

    def combine(month: str) -> dict:
        rows = data[month]
        nat = rows["national_hsk10"]
        sam = rows["samsung_chungnam"]
        cb = rows["hynix_chungbuk"]
        ic = rows.get("hynix_icheon")
        my = rows.get("malaysia_hsk10")
        return {
            "national_amount": nat["amount_usd"],
            "national_weight": nat.get("weight_kg"),
            "samsung_region_amount": sam["amount_usd"],
            "samsung_region_weight": sam.get("weight_kg"),
            "hynix_chungbuk_amount": cb["amount_usd"],
            "hynix_chungbuk_weight": cb.get("weight_kg"),
            "icheon_amount": ic["amount_usd"] if ic else None,
            "icheon_weight": ic.get("weight_kg") if ic else None,
            "malaysia_amount": my["amount_usd"] if my else None,
            "malaysia_weight": my.get("weight_kg") if my else None,
            "regional_sources": {
                "samsung_chungnam": {"source": sam.get("source"), "scope": sam.get("scope"),
                                     "identity_limit": sam.get("identity_limit")},
                "hynix_chungbuk": {"source": cb.get("source"), "scope": cb.get("scope"),
                                   "identity_limit": cb.get("identity_limit")},
            },
        }

    series = {
        m: combine(m)
        for m in needed
        if all(k in data.get(m, {}) for k in required_keys)
    }
    return {
        "month": selected,
        "series": series,
        "hs": HBM_HSK10,
        "region_hs": HBM_HSK10,
        "icheon_hs": REGION_HS6,
        "region_metric_scope": "official_sido_hsk10_exact",
        "source_url": KCS_SOURCE_PAGE,
        "icheon_public_available": "hynix_icheon" in data.get(selected, {}),
        "malaysia_public_available": "malaysia_hsk10" in data.get(selected, {}),
        "malaysia_source_url": "https://www.data.go.kr/data/15100475/openapi.do",
        "official_api_key_configured": bool(DATA_GO_KEY),
        "official_api_used": bool(data.get(selected, {}).get("national_hsk10", {}).get("api")),
        "availability_notes": availability_notes,
        "optional_errors": optional_errors,
        "errors": errors,
        "raw_rows": data,
    }, errors



def _pct(cur: float | None, base: float | None) -> float | None:
    if cur is None or base in (None, 0):
        return None
    return (cur / base - 1.0) * 100.0


def _fmt_pct(value: float | None) -> str:
    return "확인 불가" if value is None else f"{value:+.1f}%"


def _fmt_usd(value: float | None) -> str:
    if value is None:
        return "확인 불가"
    if value >= 1_000_000_000:
        return f"{value/1_000_000_000:.2f}십억달러"
    return f"{value/1_000_000:.1f}백만달러"


def _regional_direction(mom: float | None, qoq3: float | None) -> str:
    """Readable direction label without turning a regional proxy into company sales."""
    if mom is None or qoq3 is None:
        return "판정 보류"
    if mom >= 20 and (qoq3 is None or qoq3 >= 0):
        return "▲ 강한 증가"
    if mom >= 5:
        if qoq3 is not None and qoq3 <= -5:
            return "▲ 단기 반등"
        return "▲ 증가"
    if mom <= -20 and (qoq3 is None or qoq3 <= 0):
        return "▼ 강한 감소"
    if mom <= -5:
        if qoq3 is not None and qoq3 >= 5:
            return "▼ 단기 둔화"
        return "▼ 감소"
    if mom > 0:
        return "▲ 소폭 증가"
    if mom < 0:
        return "▼ 소폭 감소"
    return "→ 보합"


def _unit_value(amount: float | None, weight: float | None) -> float | None:
    if amount is None or weight in (None, 0):
        return None
    return amount / weight


def official_snapshot(official: dict) -> dict:
    """Only dated source values enter the notification comparison, never query time."""
    return {
        "month": official["month"], "hs": official["hs"],
        "region_hs": official["region_hs"],
        "series": json.loads(json.dumps(official["series"], allow_nan=False)),
    }


def official_monthly_decision(state: dict, official: dict | None) -> dict:
    if not official:
        return {"due": False, "revision": False, "availability": False, "format_upgrade": False, "snapshot": None}
    snapshot = official_snapshot(official)
    same_month = state.get("last_official_alert_month") == official["month"]
    previous = state.get("last_official_notified_values") or state.get("last_official_alert_snapshot")
    fields = ("national_amount", "national_weight", "samsung_region_amount", "hynix_chungbuk_amount", "malaysia_amount", "malaysia_weight")
    revision = availability = False
    if same_month and previous is not None:
        for month, values in snapshot["series"].items():
            old_values = previous.get("series", {}).get(month, {})
            for field in fields:
                value, old_value = values.get(field), old_values.get(field)
                if value is not None:
                    revision |= old_value is not None and value != old_value
                    availability |= old_value is None
            current_sources = values.get("regional_sources")
            previous_sources = old_values.get("regional_sources")
            if current_sources is not None and previous_sources is not None:
                revision |= current_sources != previous_sources
    format_upgrade = bool(same_month and int(state.get("export_alert_format_version") or 0) < EXPORT_ALERT_FORMAT_VERSION)
    return {
        "due": not same_month or revision or availability or format_upgrade or int(state.get("compare_version") or 0) < COMPARE_VERSION,
        "revision": revision, "availability": availability, "format_upgrade": format_upgrade, "snapshot": snapshot,
    }


def _merge_notified_values(previous, snapshot):
    """Keep sent operands across later temporary gaps, without filling a report."""
    merged = json.loads(json.dumps(previous or snapshot))
    merged.update(month=snapshot["month"], hs=snapshot["hs"], region_hs=snapshot["region_hs"])
    for month, values in snapshot["series"].items():
        target = merged.setdefault("series", {}).setdefault(month, {})
        target.update({key: value for key, value in values.items() if value is not None})
    return merged


def _write_trade_validation(now, official, errors, monthly_due, rate, fx_basis, *, observed_at=None):
    ledger = _TRADE_EVIDENCE.as_dict() if _TRADE_EVIDENCE is not None else {}
    evidence_path = OUT / "hbm_export_source_evidence.json"
    proof = {
        "schema_version": 1, "code_sha": ledger.get("code_sha"), "run_id": ledger.get("run_id"),
        "checked_at_kst": (observed_at or now).isoformat(timespec="seconds"),
        "decision_at_kst": now.isoformat(timespec="seconds"), "monthly_due": bool(monthly_due),
        "phase": "held" if errors else "not_polled", "errors": errors,
        "snapshot": official_snapshot(official) if official else None,
        "source_evidence_sha256": hashlib.sha256(evidence_path.read_bytes()).hexdigest() if evidence_path.exists() else None,
        "bindings": {}, "fx": {"rate": rate, "basis": fx_basis},
        "regional_source_proof": _SIDO_SOURCE_RESULT[0] if _SIDO_SOURCE_RESULT else None,
    }
    if official:
        proof["bindings"] = {
            month: {name: row.get("evidence_attempt_id") for name, row in rows.items()}
            for month, rows in official.get("raw_rows", {}).items()
        }
        proof["coverage_errors"] = errors
        proof["optional_source_errors"] = official.get("optional_errors") or []
        core_months = [official["month"], _month_shift(official["month"], -1), _month_shift(official["month"], -3)]
        core_roles = ("national_hsk10", "samsung_chungnam", "hynix_chungbuk")
        bound = all(proof["bindings"].get(month, {}).get(role) for month in core_months for role in core_roles)
        proof["phase"] = "verified_core" if bound and proof["regional_source_proof"] else "held_unbound_source"
    path = OUT / "hbm_export_validation.json"
    path.write_text(json.dumps(proof, ensure_ascii=False, indent=2, allow_nan=False) + "\n", encoding="utf-8")
    return {"validation_sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
            "source_evidence_sha256": proof["source_evidence_sha256"], "code_sha": proof["code_sha"], "run_id": proof["run_id"]}


def _preserved_response(attempt):
    response = attempt.get("response") or {}
    if not response.get("raw_preserved"):
        raise ValueError("HBM monthly original source bytes missing")
    raw = base64.b64decode(response["raw_base64"], validate=True)
    if (response["http_status"] != 200 or len(raw) != response["raw_bytes_length"]
            or hashlib.sha256(raw).hexdigest() != response["raw_sha256"]):
        raise ValueError("HBM monthly response bytes/hash invalid")
    return raw


def _validate_sido_source(proof, attempts):
    """Replay the request-scoped K-stat source proof without HTTP."""
    if not isinstance(proof, dict):
        raise ValueError("HBM regional unit evidence missing")
    ids = iter(proof.get("reference_attempt_ids") or [])

    def request_saved(method, url, **kwargs):
        from types import SimpleNamespace
        attempt = attempts.get(next(ids, None))
        if not attempt:
            raise ValueError("HBM unit reference response missing")
        request = attempt["request"]
        if (request["method"] != method or request["url"] != url
                or request["params"] != (kwargs.get("params") or {})
                or request["data"] != (kwargs.get("data") or {})):
            raise ValueError("HBM unit reference request mismatch")
        return SimpleNamespace(status_code=200, content=_preserved_response(attempt),
                               _hbm_trade_attempt_id=attempt["attempt_id"])

    reference, error = fetch_reference(request_saved, target_month=proof.get("month"))
    if error or reference is None or next(ids, None) is not None:
        raise ValueError("HBM public unit reference invalid")
    if proof.get("status") == "official_kstat_request_scoped_source":
        recalculated = _kstat_sido_source_proof(reference)
        if recalculated is None or recalculated != proof:
            raise ValueError("HBM direct K-stat regional source proof mismatch")
        return recalculated
    rows = {}
    for code in ("44", "43"):
        attempt = attempts.get((proof.get("api_attempt_ids") or {}).get(code))
        if not attempt:
            raise ValueError("HBM same-month unit operand missing")
        request = attempt["request"]
        params = request["params"]
        if (request["method"] != "GET" or request["url"] != DATA_GO_SIDO_ITEM_URL
                or params.get("sidoCd") != code or params.get("hsSgn") != HBM_HSK10
                or params.get("strtYymm") != reference["month"] or params.get("endYymm") != reference["month"]):
            raise ValueError("HBM same-month unit request mismatch")
        row, error = choose_exact_row(_xml_rows(ET.fromstring(_preserved_response(attempt))),
            reference["month"], HBM_HSK10, region=code,
            value_fields=("expUsdAmt",), unit="unverified", weight_fields=())
        if error or row is None:
            raise ValueError("HBM same-month unit source identity invalid")
        rows[code] = row
    recalculated, error = reconcile_unit(rows, reference)
    if error or recalculated is None or any(proof.get(key) != value for key, value in recalculated.items()):
        raise ValueError("HBM regional unit reconciliation mismatch")
    return recalculated


def validate_monthly_payload(text, candidate, out_dir=None):
    """Re-read preserved response operands before the existing delivery journal."""
    anchor = "삼성전자 vs SK하이닉스 HBM 수출 방향"
    if not candidate.get("monthly_due"):
        if anchor in text:
            raise ValueError("HBM unexpected monthly payload without a monthly candidate")
        return
    if anchor not in text:
        raise ValueError("HBM monthly candidate body missing")
    out = pathlib.Path(out_dir) if out_dir is not None else OUT
    validation_path = out / "hbm_export_validation.json"
    source_path = out / "hbm_export_source_evidence.json"
    proof = json.loads(validation_path.read_bytes())
    ledger = json.loads(source_path.read_bytes())
    binding = candidate.get("official_export_evidence") or {}
    if (proof.get("phase") != "verified_core" or not proof.get("monthly_due")
            or hashlib.sha256(validation_path.read_bytes()).hexdigest() != binding.get("validation_sha256")
            or hashlib.sha256(source_path.read_bytes()).hexdigest() != proof.get("source_evidence_sha256")
            or proof.get("source_evidence_sha256") != binding.get("source_evidence_sha256")
            or proof.get("code_sha") != ledger.get("code_sha") or proof.get("run_id") != ledger.get("run_id")
            or binding.get("code_sha") != proof.get("code_sha") or binding.get("run_id") != proof.get("run_id")
            or not re.fullmatch(r"[0-9a-f]{40}", str(proof.get("code_sha") or ""))):
        raise ValueError("HBM monthly source evidence binding invalid")
    snapshot = proof["snapshot"]
    if snapshot != candidate.get("last_official_alert_snapshot"):
        raise ValueError("HBM monthly source snapshot mismatch")
    attempts = {a["attempt_id"]: a for a in ledger["attempts"]}
    regional_source = _validate_sido_source(proof.get("regional_source_proof"), attempts)
    fields = {"national_hsk10": ("national_amount", "national_weight"),
              "samsung_chungnam": ("samsung_region_amount", "samsung_region_weight"),
              "hynix_chungbuk": ("hynix_chungbuk_amount", "hynix_chungbuk_weight"),
              "malaysia_hsk10": ("malaysia_amount", "malaysia_weight"),
              "hynix_icheon": ("icheon_amount", "icheon_weight")}
    for month, values in snapshot["series"].items():
        for role, (amount_key, weight_key) in fields.items():
            if values.get(amount_key) is None:
                continue
            attempt_id = proof["bindings"].get(month, {}).get(role)
            attempt = attempts.get(attempt_id)
            if not attempt:
                raise ValueError("HBM monthly original source bytes missing")
            raw = _preserved_response(attempt)
            selected = attempt["selection"]["normalized"]
            region = "44" if role == "samsung_chungnam" else "43" if role == "hynix_chungbuk" else "41" if role == "hynix_icheon" else None
            request = attempt["request"]
            endpoint = request["url"]
            if endpoint == KSTAT_SHEET_URL:
                if region not in ("44", "43") or not isinstance(selected, dict):
                    raise ValueError("HBM K-stat regional role invalid")
                evidence_ids = selected.get("evidence_attempt_ids") or {}
                form_id, sheet_id = evidence_ids.get("form"), evidence_ids.get("sheet")
                if not form_id or not sheet_id or str(sheet_id) != str(attempt_id):
                    raise ValueError("HBM K-stat request evidence ids missing")
                replay_ids = iter((form_id, sheet_id))

                def request_saved_kstat(method, url, **kwargs):
                    from types import SimpleNamespace
                    saved_id = next(replay_ids, None)
                    saved = attempts.get(saved_id)
                    if not saved:
                        raise ValueError("HBM K-stat regional source response missing")
                    saved_request = saved["request"]
                    if (saved_request["method"] != method or saved_request["url"] != url
                            or saved_request["params"] != (kwargs.get("params") or {})
                            or saved_request["data"] != (kwargs.get("data") or {})):
                        raise ValueError("HBM K-stat exact month/HS request scope mismatch")
                    return SimpleNamespace(status_code=200, content=_preserved_response(saved),
                                           _hbm_trade_attempt_id=saved["attempt_id"])

                reference, reference_error = fetch_reference(request_saved_kstat, target_month=month)
                if (reference_error or reference is None or next(replay_ids, None) is not None
                        or selected != _kstat_reference_selection(reference)):
                    raise ValueError("HBM K-stat regional response selection mismatch")
                source_amount = Decimal(reference["amounts_usd"][region])
                if (Decimal(str(values[amount_key])) != source_amount
                        or values.get(weight_key) is not None):
                    raise ValueError("HBM K-stat regional source operands mismatch")
                continue
            rows = (json.loads(raw).get("items") or []) if raw.lstrip().startswith(b"{") else _xml_rows(ET.fromstring(raw))
            expected = ((KCS_REGION_URL, "expUsdAmt", "thousand_usd") if role == "hynix_icheon" else
                        (DATA_GO_SIDO_ITEM_URL, "expUsdAmt", regional_source["unit"]) if region else
                        (DATA_GO_COUNTRY_ITEM_URL, "expDlr", "usd") if role == "malaysia_hsk10" else
                        (KCS_ITEM_URL, "expUsdAmt", "thousand_usd") if endpoint == KCS_ITEM_URL else
                        (DATA_GO_ITEM_URL, "expDlr", "usd"))
            if (endpoint, selected["raw_amount_field"], selected["raw_amount_unit"]) != expected:
                raise ValueError("HBM source unit/endpoint contract mismatch")
            if endpoint not in (KCS_ITEM_URL, KCS_REGION_URL):
                params = request["params"]
                if (params.get("strtYymm") != month or params.get("endYymm") != month
                        or params.get("hsSgn") != HBM_HSK10
                        or (region and params.get("sidoCd") != region)
                        or (role == "malaysia_hsk10" and params.get("cntyCd") != "MY")):
                    raise ValueError("HBM exact source request scope mismatch")
            hs = REGION_HS6 if role == "hynix_icheon" else HBM_HSK10
            again, error = choose_exact_row(rows, month, hs, region=region,
                country="MY" if role == "malaysia_hsk10" else None,
                value_fields=(selected["raw_amount_field"],), unit=selected["raw_amount_unit"],
                weight_fields=() if role in ("samsung_chungnam", "hynix_chungbuk") else ("expWgt", "expTtwg"))
            if (error or again is None or again["amount_usd"] != values[amount_key]
                    or again["weight_kg"] != values.get(weight_key)):
                raise ValueError("HBM monthly exact response operands mismatch")
            if role == "hynix_icheon":
                params = request["data"]
                if (str(again["selected_row"].get("sggCd") or "") != "41500"
                        or params.get("sggCd") != "41500" or params.get("sidoCd") != "41"
                        or params.get("hsSgn") != REGION_HS6
                        or params.get("priodFr") != month or params.get("priodTo") != month):
                    raise ValueError("HBM Icheon city identity unverified")
    rendered = build_monthly(datetime.fromisoformat(proof.get("decision_at_kst", proof["checked_at_kst"])), proof["fx"]["rate"], proof["fx"]["basis"],
        dict(snapshot, source_url=KCS_SOURCE_PAGE, malaysia_public_available=snapshot["series"][snapshot["month"]].get("malaysia_amount") is not None,
             icheon_hs=REGION_HS6, icheon_public_available=snapshot["series"][snapshot["month"]].get("icheon_amount") is not None),
        observed_at=datetime.fromisoformat(proof["checked_at_kst"]))
    # Currency enforcement can append conversions. Source percentage/date/direction
    # lines remain exact and are independently regenerated above.
    from collections import Counter
    required = Counter(line for line in rendered.splitlines() if line.startswith(("• 변화:", "• 비교월:", "• 판정:", "• HSK10", "• 한국→말레이시아 HSK10", "• 중량당 단가:", "🔵 <b>삼성전자 관련", "🟠 <b>SK하이닉스 관련")))
    for line, count in required.items():
        if text.count(line) < count:
            raise ValueError("HBM monthly rendered period/direction mismatch")
    headings = ["[삼성전자 방향 — 충남]", "[SK하이닉스 관련 지역 — 충북]", "[1. 전국 HBM 포함 MCP]", "[2. 말레이시아 HSK10 — 첨단패키징 보조축]"]
    keys = ["samsung_region_amount", "hynix_chungbuk_amount", "national_amount", "malaysia_amount"]
    for heading, key in zip(headings, keys):
        amount = snapshot["series"][snapshot["month"]].get(key)
        if amount is None:
            continue
        if text.count(heading) != 1:
            raise ValueError("HBM monthly section missing or duplicated")
        section = text.split(heading, 1)[1].split("\n\n", 1)[0]
        if _fmt_usd(amount) not in section:
            raise ValueError("HBM monthly rendered section amount mismatch")
    if snapshot["series"][snapshot["month"]].get("icheon_amount") is not None:
        line = next(line for line in rendered.splitlines() if line.startswith("• 이천 보조치("))
        if line not in text:
            raise ValueError("HBM monthly Icheon auxiliary amount mismatch")


def classify_event(e: dict) -> tuple[str, str]:
    text = f"{e.get('title','')} {e.get('description','')}".lower()
    if any(k in text for k in ("malaysia", "말레이시아", "penang", "kulim")) and any(k in text for k in ("hbm", "emib", "packaging", "패키징")):
        return "말레이시아·EMIB", "말레이시아 HBM·Intel EMIB 첨단패키징 변화"
    if "hbm" in text and any(k in text for k in ("yield", "수율")):
        return "수율", "HBM 양산 수율 상태 변화"
    if "hbm" in text and any(k in text for k in ("unit price", "export price", "수출단가", "평균 수출단가")):
        return "수출단가·가격", "HBM 관련 수출단가 상태 변화"
    if "hbm" in text and any(k in text for k in (
        "production", "capacity", "output", "ramp", "expand", "expansion", "double",
        "생산", "증산", "생산능력", "캐파", "확대", "증설", "2배", "웨이퍼",
    )):
        return "생산능력·증산", "삼성 HBM 생산능력·증산 계획 변화"
    if ("icheon" in text or "이천" in text) and "hbm" in text:
        return "이천 HBM 정밀 보강", "이천 SK하이닉스 HBM 직접·정밀 대용지표 변화"
    if ("icheon" in text or "이천" in text) and any(k in text for k in ("semiconductor", "memory", "반도체", "메모리")):
        return "이천 반도체 보조지표", "이천 SK하이닉스 생산·수출 보조지표 변화"
    if "bernstein" in text or ("chung" in text and "export" in text) or "충남" in text or "충북" in text:
        return "수출 대용지표", "충남(삼성) vs 충북·이천(SK하이닉스) HBM 수출 대용지표 변화"
    if "counterpoint" in e.get("source","").lower() and "market share" in text:
        return "점유율", "삼성·SK하이닉스 HBM 점유율 변화"
    if "hbm4e" in text and any(k in text for k in ("qualification", "validation", "mass production", "인증", "검증", "양산")):
        return "HBM4E 검증·양산", "HBM4E 고객 검증·양산 변화"
    if "hbm4" in text and any(k in text for k in ("shipment", "mix", "share", "출하", "비중")):
        return "HBM4 출하", "HBM4 출하·제품혼합 변화"
    if any(k in text for k in ("nvidia", "amd", "broadcom", "google")):
        return "고객", "주요 AI 고객 연결 변화"
    return "기타", "삼성 HBM 관련 신규 변화"



def _first_number(patterns: list[str], text: str) -> str:
    for pat in patterns:
        m = re.search(pat, text, re.I)
        if m:
            try:
                return f"{float(m.group(1)):g}"
            except Exception:
                return m.group(1)
    return ""


def _event_target_year(e: dict, text: str) -> str:
    years = re.findall(r"\b(20\d{2})\b", text)
    if years:
        return years[0]
    low = text.lower()
    if "내년" in text or "next year" in low:
        try:
            dt = datetime.fromisoformat(e.get("published_at_kst") or "")
            return str(dt.year + 1)
        except Exception:
            return "next_year"
    return ""


def korean_evidence_title(e: dict, fallback: str = "HBM 상태 변화") -> str:
    """Render English evidence titles as Korean; the raw title stays behind the source link."""
    title = clean(e.get("title") or "")
    if not title:
        return fallback
    if re.search(r"[가-힣]", title):
        return re.sub(r"\s+-\s+[^-]{2,80}$", "", title).strip()

    low = title.lower()
    pcts = re.findall(r"([0-9]+(?:\.[0-9]+)?)\s*%", title)
    if "samsung" in low and "hbm4" in low and ("double" in low or "2x" in low):
        if ("product mix" in low or "mix" in low) and len(pcts) >= 2:
            return f"보도: 삼성전자, 내년 HBM4·HBM4E 생산을 2배로 늘리고 제품 비중을 {pcts[0]}%에서 {pcts[1]}%로 확대할 가능성"
        return "보도: 삼성전자, 내년 HBM4·HBM4E 생산을 2배로 확대할 가능성"
    if "samsung" in low and "hbm4" in low and any(k in low for k in ("volume production", "mass production", "production")):
        return "삼성전자 HBM4 양산·생산 확대 관련 보도"
    if "bernstein" in low and "hbm" in low and any(k in low for k in ("revenue", "forecast", "estimate")):
        return "Bernstein HBM 매출 전망·추정 변화 관련 보도"
    if "market share" in low and "hbm" in low:
        return "HBM 시장점유율 변화 관련 보도"
    if "yield" in low and "hbm" in low:
        return "HBM 양산 수율 변화 관련 보도"
    if "malaysia" in low and "hbm" in low:
        return "말레이시아 HBM·첨단패키징 변화 관련 보도"
    return fallback + " 관련 보도"


def event_state_descriptor(e: dict) -> tuple[str, str, str]:
    """Return topic key, state signature and a readable state label.

    Article identity is deliberately excluded. Links and publisher names are
    evidence only; alert novelty is based on the normalized topic state.
    """
    category, headline = classify_event(e)
    text = clean(f"{e.get('title','')} {e.get('description','')}")
    low = text.lower()

    company = "samsung" if ("samsung" in low or "삼성" in text) else (
        "skhynix" if ("sk hynix" in low or "sk하이닉스" in text or "하이닉스" in text) else (
            "intel" if "intel" in low else (
                "ase" if re.search(r"\base\b", low) else (
                    "tfamd" if ("tf-amd" in low or "tf amd" in low) else (
                        "mapc" if ("malaysia advanced packaging consortium" in low or re.search(r"\bmapc\b", low)) else "industry"
                    )
                )
            )
        )
    )
    products = []
    has_hbm4e = bool(
        re.search(r"\bhbm\s*4e\b|\bhbm4e\b", low)
        or re.search(r"hbm4\s*[·/&+,-]\s*4e\b", low)
    )
    has_hbm4 = bool(
        re.search(r"\bhbm\s*4\b|\bhbm4\b(?!e)", low)
        or re.search(r"hbm4\s*[·/&+,-]\s*4e\b", low)
    )
    if has_hbm4 and has_hbm4e:
        # HBM4·HBM4E production-ramp stories are one product-family event.
        products.append("hbm4")
    elif has_hbm4e:
        products.append("hbm4e")
    elif has_hbm4:
        products.append("hbm4")
    for name, aliases in (
        ("custom_hbm", ("custom hbm", "커스텀 hbm")),
        ("hbm3e", ("hbm3e", "hbm 3e")),
        ("emib", ("emib",)),
    ):
        if any(a in low for a in aliases):
            products.append(name)
    if not products and "hbm" in low:
        products.append("hbm")

    customer = ""
    for name in ("nvidia", "amd", "broadcom", "google"):
        if name in low:
            customer = name
            break

    geography = ""
    if any(k in low for k in ("malaysia", "말레이시아", "penang", "kulim")):
        geography = "malaysia"
    elif "이천" in text or "icheon" in low:
        geography = "icheon"
    elif "충남" in text:
        geography = "chungnam"
    elif "충북" in text:
        geography = "chungbuk"

    target_year = _event_target_year(e, text)
    topic_parts = [category, company, "+".join(products), customer, geography, target_year]
    topic_key = "|".join(x for x in topic_parts if x)

    stages = []
    stage_map = (
        ("mass_production", ("mass production", "양산")),
        ("shipment", ("shipment", "ship", "출하", "공급")),
        ("sample", ("sample", "샘플")),
        ("qualification", ("qualification", "validation", "인증", "검증")),
        ("contract", ("contract", "계약", "수주")),
        ("capacity", ("capacity", "production", "output", "ramp", "증산", "생산능력", "캐파", "생산")),
        ("investment", ("capex", "investment", "증설", "설비투자", "투자")),
        ("prototype", ("prototype", "프로토타입", "시제품")),
        ("pilot", ("pilot", "실증")),
        ("validation", ("validation", "qualification", "검증", "인증")),
        ("test_facility", ("test facility", "테스트 시설")),
        ("share", ("market share", "점유율")),
        ("revenue", ("revenue", "매출")),
        ("price", ("price", "가격", "단가")),
        ("export", ("export", "수출")),
    )
    for label, aliases in stage_map:
        if any(a in low for a in aliases):
            stages.append(label)

    direction = ""
    if any(k in low for k in ("double", "2x", "increase", "expand", "rise", "growth", "증가", "확대", "증산", "2배", "늘린", "상승")):
        direction = "up"
    elif any(k in low for k in ("decrease", "reduce", "cut", "decline", "감소", "축소", "하향")):
        direction = "down"

    primary_values = []
    multiple = _first_number([
        r"(\d+(?:\.\d+)?)\s*배",
        r"(\d+(?:\.\d+)?)\s*(?:x|times?)\b",
    ], text)
    if not multiple and re.search(r"\b(?:double|doubl(?:e|ed|ing))\b", low):
        multiple = "2"
    if not multiple and re.search(r"\b(?:triple|tripl(?:e|ed|ing))\b", low):
        multiple = "3"
    if multiple:
        primary_values.append("multiple=" + multiple)

    percentages = re.findall(r"([+-]?\d+(?:\.\d+)?)\s*%", text)
    if percentages:
        primary_values.append("pct=" + ",".join(percentages[:3]))

    if category == "수출단가·가격":
        price_values = re.findall(
            r"(?:수출단가|평균\s*수출단가|unit\s*price|export\s*price)[^\d$]{0,30}\$?\s*([0-9]+(?:\.[0-9]+)?)",
            text,
            re.I,
        )
        if not price_values:
            price_values = re.findall(r"\$?\s*([0-9]+(?:\.[0-9]+)?)\s*달러", text)
        if price_values:
            primary_values.append("price=" + ",".join(price_values[:3]))

    wafer = ""
    if category == "생산능력·증산":
        wafer = _first_number([
            r"(\d[\d,]*(?:\.\d+)?)\s*(?:wafers?|wafer starts?)\s*(?:a month|per month|/month)?",
            r"(\d[\d,]*(?:\.\d+)?)\s*(?:장|매)\s*(?:/\s*월|월간|매월)?",
        ], text.replace(",", ""))
        if wafer:
            primary_values.append("wafer=" + wafer)
        # A republisher adding product-mix percentages to the same 2x capacity
        # story is evidence enrichment, not a second production-state change.
        # Product-mix percentages are tracked separately by hbm_memory_axes.py.
        if multiple or wafer:
            primary_values = [x for x in primary_values if not x.startswith("pct=")]

    if category in ("HBM4E 검증·양산", "HBM4 출하", "고객"):
        if customer:
            primary_values.append("customer=" + customer)

    # A material state must have a stage/direction/value. Pure article chatter
    # is retained as evidence but cannot create an alert by itself.
    if not stages and not direction and not primary_values:
        return "", "", ""

    evidence_state = "official" if evidence_level(e) == "공식 확인" else "reported"
    signature_parts = [
        topic_key,
        "+".join(sorted(set(stages))),
        direction,
        ";".join(primary_values),
        evidence_state,
    ]
    signature_raw = "|".join(x for x in signature_parts if x)
    signature = hashlib.sha256(signature_raw.encode()).hexdigest()[:24]
    readable = headline
    return topic_key, signature, readable


def evidence_level(e: dict) -> str:
    source = (e.get("source") or "").lower()
    if any(k in source for k in ("samsung", "삼성전자", "intel", "관세청", "k-stat", "한국무역협회")):
        return "공식 확인"
    return "신뢰 보도 단계"



def _share_institution(text: str) -> str:
    low = (text or "").lower()
    for institution, aliases in SHARE_INSTITUTIONS.items():
        if any(alias in low for alias in aliases):
            return institution
    return ""


def _share_basis(text: str, institution: str = "") -> str:
    low = (text or "").lower()
    if any(k in low for k in (
        "by sales", "sales share", "revenue share", "share by revenue",
        "매출 기준", "매출 점유율", "금액 기준", "매출액 기준",
    )):
        return "sales"
    if any(k in low for k in (
        "bit share", "bit shipment", "bit-based", "shipment share",
        "gigabit", "gb shipment", "비트 기준", "비트 점유율", "비트 출하",
    )):
        return "bit"
    # Counterpoint's tracked HBM market-share series is revenue based.
    if institution == "counterpoint" and "market share" in low:
        return "sales"
    return ""


def _share_alias_pattern(aliases: tuple[str, ...]) -> str:
    parts = []
    for alias in aliases:
        if alias.isalpha() and len(alias) <= 3:
            parts.append(r"\b" + re.escape(alias) + r"\b")
        else:
            parts.append(re.escape(alias))
    return "(?:" + "|".join(parts) + ")"


def _extract_vendor_pct(text: str, aliases: tuple[str, ...]) -> float | None:
    low = (text or "").lower()
    ap = _share_alias_pattern(tuple(a.lower() for a in aliases))
    patterns = [
        ap + r"[^%\d]{0,55}([0-9]{1,3}(?:\.[0-9]+)?)\s*%",
        r"([0-9]{1,3}(?:\.[0-9]+)?)\s*%[^%\d]{0,55}" + ap,
    ]
    for pat in patterns:
        m = re.search(pat, low, re.I)
        if m:
            # One of the alternations may add a group before the numeric group.
            numeric = None
            for g in m.groups():
                if g is not None and re.fullmatch(r"[0-9]{1,3}(?:\.[0-9]+)?", str(g)):
                    numeric = float(g)
                    break
            if numeric is not None and 0 <= numeric <= 100:
                return numeric
    return None


def _share_values(text: str) -> dict[str, float] | None:
    values = {
        "skhynix": _extract_vendor_pct(text, ("sk hynix", "sk하이닉스", "하이닉스", "skh")),
        "samsung": _extract_vendor_pct(text, ("samsung electronics", "samsung", "삼성전자", "삼성", "sec")),
        "micron": _extract_vendor_pct(text, ("micron", "마이크론", "mu")),
    }
    found = {k: v for k, v in values.items() if v is not None}
    if len(found) < 2:
        return None
    if len(found) == 3:
        total = sum(found.values())
        # HBM share reports often sum to 99~101 due to rounding.
        if not (97.0 <= total <= 103.0):
            return None
    return found


def _share_page_text(e: dict, base_text: str) -> str:
    low = base_text.lower()
    if not any(k in low for k in ("market share", "점유율", "hbm share", "share parity")):
        return base_text
    url = e.get("direct_link") or ""
    if not url:
        return base_text
    try:
        raw = fetch(url, timeout=12)
        page = clean(raw.decode("utf-8", errors="ignore"))
        if page:
            return (base_text + " " + page[:20000]).strip()
    except Exception:
        pass
    return base_text


def _share_period_windows(text: str) -> list[tuple[str, str]]:
    windows: list[tuple[str, str]] = []
    year_hits = list(re.finditer(r"\b(20\d{2})(?:E|e)?\b", text))
    for i, hit in enumerate(year_hits):
        start = max(0, hit.start() - 100)
        end = min(len(text), (year_hits[i + 1].start() + 30) if i + 1 < len(year_hits) else hit.end() + 420)
        windows.append((hit.group(1), text[start:end]))

    quarter_patterns = [
        re.compile(r"\b([1-4])Q\s*(20\d{2})\b", re.I),
        re.compile(r"\bQ([1-4])\s*(20\d{2})\b", re.I),
        re.compile(r"\b(20\d{2})\s*년?\s*([1-4])\s*분기\b"),
    ]
    for pat in quarter_patterns:
        for hit in pat.finditer(text):
            groups = hit.groups()
            if len(groups) != 2:
                continue
            if len(groups[0]) == 4:
                year, q = groups[0], groups[1]
            else:
                q, year = groups[0], groups[1]
            start = max(0, hit.start() - 100)
            end = min(len(text), hit.end() + 420)
            windows.append((f"{year}Q{q}", text[start:end]))
    return windows


def extract_share_observations(e: dict) -> list[dict]:
    base = clean(f"{e.get('title','')} {e.get('description','')} {e.get('source','')}")
    low = base.lower()
    if "hbm" not in low or not any(k in low for k in ("share", "점유율", "market")):
        return []

    institution = _share_institution(base)
    if not institution:
        return []

    text = _share_page_text(e, base)
    basis = _share_basis(text, institution)
    if not basis:
        # Never compare an unspecified denominator with sales or bit share.
        return []

    is_forecast_context = any(k in text.lower() for k in (
        "forecast", "estimate", "estimated", "outlook", "expects", "expected",
        "전망", "예상", "추정", "e)", "2026e", "2027e", "2028e",
    ))

    out: list[dict] = []
    seen_keys = set()
    for period, window in _share_period_windows(text):
        values = _share_values(window)
        if not values:
            continue

        window_low = window.lower()
        window_forecast = any(k in window_low for k in (
            "forecast", "estimate", "estimated", "outlook", "expects", "expected",
            "전망", "예상", "추정",
        ))
        kind = "actual" if "Q" in period and not window_forecast else "forecast"
        key = f"{institution}|{basis}|{period}"
        if key in seen_keys:
            continue
        seen_keys.add(key)
        out.append({
            "key": key,
            "kind": kind,
            "institution": institution,
            "basis": basis,
            "period": period,
            "values": values,
            "source": e.get("source") or "",
            "published_at_kst": e.get("published_at_kst") or "",
            "direct_link": e.get("direct_link") or "",
            "title": e.get("title") or "",
            "event_id": e.get("id") or "",
        })
    return out


def _share_leader(values: dict[str, float]) -> str:
    if not values:
        return ""
    return max(values, key=lambda k: values[k])


def _share_gap(values: dict[str, float]) -> float | None:
    if "skhynix" not in values or "samsung" not in values:
        return None
    return abs(values["skhynix"] - values["samsung"])


def _share_material_change(old: dict, new: dict) -> tuple[bool, list[str]]:
    old_values = dict(old.get("values") or old)
    new_values = dict(new.get("values") or {})
    reasons: list[str] = []

    deltas = []
    for vendor in ("skhynix", "samsung", "micron"):
        if vendor in old_values and vendor in new_values:
            delta = new_values[vendor] - old_values[vendor]
            deltas.append(abs(delta))
            if abs(delta) >= SHARE_REVISION_THRESHOLD_PP:
                reasons.append(f"{vendor} {delta:+.1f}%p")

    old_leader = _share_leader(old_values)
    new_leader = _share_leader(new_values)
    if old_leader and new_leader and old_leader != new_leader:
        reasons.append(f"선두 {old_leader}→{new_leader}")

    old_gap = _share_gap(old_values)
    new_gap = _share_gap(new_values)
    if old_gap is not None and new_gap is not None:
        if (old_gap > SHARE_PARITY_GAP_PP and new_gap <= SHARE_PARITY_GAP_PP) or (
            old_gap <= SHARE_PARITY_GAP_PP and new_gap > SHARE_PARITY_GAP_PP
        ):
            reasons.append(f"삼성-SK하이닉스 격차 {old_gap:.1f}%p→{new_gap:.1f}%p")

    return bool(reasons), reasons


def _share_cross_source_signal(states: dict, obs: dict) -> tuple[bool, list[str]]:
    peers = []
    for key, value in states.items():
        parts = key.split("|")
        if len(parts) != 3:
            continue
        inst, basis, period = parts
        if basis != obs["basis"] or period != obs["period"] or inst == obs["institution"]:
            continue
        vals = value.get("values") or value
        if isinstance(vals, dict):
            peers.append(vals)

    reasons = []
    for vendor in ("skhynix", "samsung", "micron"):
        peer_vals = sorted(float(x[vendor]) for x in peers if vendor in x)
        if not peer_vals or vendor not in obs["values"]:
            continue
        mid = peer_vals[len(peer_vals) // 2]
        diff = obs["values"][vendor] - mid
        if abs(diff) >= SHARE_ACTUAL_DEVIATION_THRESHOLD_PP:
            reasons.append(f"{vendor} 기존기관 중앙값 대비 {diff:+.1f}%p")
    gap = _share_gap(obs["values"])
    if gap is not None and gap <= SHARE_PARITY_GAP_PP:
        reasons.append(f"삼성-SK하이닉스 격차 {gap:.1f}%p")
    return bool(reasons), reasons


def _format_share_values(values: dict[str, float]) -> str:
    labels = (("skhynix", "SK하이닉스"), ("samsung", "삼성전자"), ("micron", "Micron"))
    return " · ".join(f"{label} {values[key]:.0f}%" for key, label in labels if key in values)


def share_change_event(obs: dict, old: dict | None, reasons: list[str]) -> dict:
    basis_label = "매출 기준" if obs["basis"] == "sales" else "비트 기준"
    kind_label = "실제 점유율" if obs["kind"] == "actual" else "점유율 전망"
    institution_label = {
        "jpmorgan": "J.P. Morgan",
        "kb": "KB증권",
        "ubs": "UBS",
        "morgan_stanley": "Morgan Stanley",
        "citi": "Citi",
        "bofa": "BofA",
        "goldman_sachs": "Goldman Sachs",
        "counterpoint": "Counterpoint",
        "trendforce": "TrendForce",
        "idc": "IDC",
    }.get(obs["institution"], obs["institution"])
    return {
        "id": "share|" + obs["key"],
        "share_observation": obs,
        "title": obs.get("title") or f"{institution_label} HBM {kind_label}",
        "description": "",
        "source": obs.get("source") or institution_label,
        "published_at_kst": obs.get("published_at_kst") or "",
        "direct_link": obs.get("direct_link") or "",
        "rank": 99 if obs["kind"] == "actual" else 88,
        "share_change": {
            "institution": institution_label,
            "basis": basis_label,
            "period": obs["period"],
            "kind": kind_label,
            "values": obs["values"],
            "old_values": (old.get("values") or old) if old else None,
            "reasons": reasons,
        },
    }


def share_event_summary(e: dict) -> list[str]:
    ch = e["share_change"]
    lines = [
        f"<b>HBM {html.escape(ch['kind'])} 상태 변화</b>",
        f"• 기관: <b>{html.escape(ch['institution'])}</b>",
        f"• 기준: <b>{html.escape(ch['basis'])}</b> · 대상 <b>{html.escape(ch['period'])}</b>",
        f"• 현재값: <b>{html.escape(_format_share_values(ch['values']))}</b>",
    ]
    if ch.get("old_values"):
        lines.append(f"• 직전값: {html.escape(_format_share_values(ch['old_values']))}")
    if ch.get("reasons"):
        lines.append("• 변화 이유: " + html.escape(" · ".join(ch["reasons"])))
    lines += [
        f"• 감지 근거: {html.escape(e.get('source') or '미표시')} · {html.escape(e.get('published_at_kst') or '확인 불가')}",
        f"• 근거 제목(한국어): {html.escape(korean_evidence_title(e, ch.get('headline') if e.get('ops_change') else ('HBM ' + ch.get('kind','') + ' 상태 변화' if e.get('share_change') else 'HBM 상태 변화')))} · {href(e.get('direct_link') or '', '원문')}",
    ]
    return lines



def _broker_company(text: str) -> str:
    low = (text or "").lower()
    if "samsung" in low or "삼성전자" in text or "삼성" in text:
        return "samsung"
    if "sk hynix" in low or "sk하이닉스" in text or "하이닉스" in text:
        return "skhynix"
    if "micron" in low or "마이크론" in text:
        return "micron"
    return ""


def _broker_page_text(e: dict, base_text: str) -> str:
    low = base_text.lower()
    if "hbm" not in low or not _share_institution(base_text):
        return base_text
    if not any(k in low for k in (
        "asp", "average selling price", "평균판매단가", "평균 판매단가",
        "8-hi", "8hi", "12-hi", "12hi", "16-hi", "16hi", "8단", "12단", "16단",
        "negotiation", "agreement", "contract", "협상", "계약", "타결", "확정",
        "revenue mix", "sales mix", "매출 비중", "제품 비중", "판매 가격", "selling price",
    )):
        return base_text
    url = e.get("direct_link") or ""
    if not url:
        return base_text
    try:
        raw = fetch(url, timeout=12).decode("utf-8", errors="ignore")
        page = clean(raw)
        if page:
            return (base_text + " " + page[:28000]).strip()
    except Exception:
        pass
    return base_text


def _broker_period(text: str) -> str:
    patterns = [
        r"FY\s*'?([0-9]{2})(?:E|F)?\b",
        r"\b(20[0-9]{2})(?:E|F)\b",
        r"\b(20[0-9]{2})\b",
    ]
    for pat in patterns:
        for m in re.finditer(pat, text, re.I):
            raw = m.group(1)
            year = int(raw) + 2000 if len(raw) == 2 else int(raw)
            window = text[max(0, m.start()-160):min(len(text), m.end()+160)].lower()
            if (
                "asp" in window or "average selling price" in window or "평균판매단가" in window or "평균 판매단가" in window
                or "contract" in window or "agreement" in window or "negotiation" in window or "계약" in window or "협상" in window
            ):
                return str(year)
    return ""


def _extract_hbm_asp_forecast(text: str) -> tuple[float | None, float | None]:
    previous = None
    current = None

    previous_patterns = [
        r"(?:previous|prior|기존)[^%]{0,80}?(?:estimate|forecast|예상|전망)[^%]{0,40}?\(?\+?([0-9]{1,3}(?:\.[0-9]+)?)\s*%",
        r"(?:from|기존)\s*\+?([0-9]{1,3}(?:\.[0-9]+)?)\s*%[^.]{0,80}?(?:to|→|에서)",
    ]
    for pat in previous_patterns:
        m = re.search(pat, text, re.I)
        if m:
            previous = float(m.group(1))
            break

    current_patterns = [
        r"(?:now\s+forecast|now\s+expect|현재\s*(?:전망|예상))[^%]{0,80}?\+?([0-9]{1,3}(?:\.[0-9]+)?)\s*%[^.]{0,90}?(?:blended\s+)?(?:hbm\s+)?asp",
        r"(?:now\s+forecast|now\s+expect|현재\s*(?:전망|예상))[^%]{0,80}?\+?([0-9]{1,3}(?:\.[0-9]+)?)\s*%[^.]{0,90}?(?:평균판매단가|평균 판매단가)",
        r"(?:hbm\s+)?(?:blended\s+)?asp[^%]{0,100}?\+?([0-9]{1,3}(?:\.[0-9]+)?)\s*%\s*(?:y/y|yoy|year[- ]over[- ]year|전년)",
        r"(?:hbm\s+)?(?:혼합\s+)?(?:평균판매단가|평균 판매단가|판매\s*가격)[^%]{0,100}?\+?([0-9]{1,3}(?:\.[0-9]+)?)\s*%",
        r"(?:hbm\s+)?selling\s+price[^%]{0,100}?\+?([0-9]{1,3}(?:\.[0-9]+)?)\s*%",
        r"\+?([0-9]{1,3}(?:\.[0-9]+)?)\s*%[^.]{0,100}?(?:blended\s+)?(?:hbm\s+)?asp",
    ]
    for pat in current_patterns:
        m = re.search(pat, text, re.I)
        if m:
            current = float(m.group(1))
            break
    return current, previous


def _extract_hbm_asp_floor_flag(text: str, value: float | None) -> bool:
    if value is None:
        return False
    low = clean(text).lower()
    return bool(
        re.search(rf"{float(value):g}\s*%\s*(?:이상|초과)", low, re.I)
        or re.search(rf"(?:more\s+than|over|above|at\s+least)\s*{float(value):g}\s*%", low, re.I)
        or re.search(rf"{float(value):g}\s*%\s*(?:or\s+more|plus)", low, re.I)
    )


def _extract_hbm4_revenue_mix(text: str) -> tuple[float | None, float | None]:
    value = clean(text)
    low = value.lower()
    if "hbm4" not in low:
        return None, None
    patterns = (
        r"(?:hbm4[^.]{0,100}?(?:매출\s*비중|revenue\s*(?:mix|share)))[^%]{0,120}?(?:올해|this\s+year)[^%]{0,50}?(\d{1,3}(?:\.\d+)?)\s*%[^.]{0,120}?(?:내년|next\s+year|2027)[^%]{0,50}?(\d{1,3}(?:\.\d+)?)\s*%",
        r"(?:올해|this\s+year)[^%]{0,60}?(\d{1,3}(?:\.\d+)?)\s*%[^.]{0,120}?(?:내년|next\s+year|2027)[^%]{0,60}?(\d{1,3}(?:\.\d+)?)\s*%[^.]{0,80}?(?:hbm4|매출\s*비중|revenue\s*(?:mix|share))",
    )
    for pat in patterns:
        m = re.search(pat, value, re.I)
        if m:
            return float(m.group(1)), float(m.group(2))
    return None, None


def _extract_stack_mainstream(text: str) -> str:
    patterns = [
        r"\b(8|12|16)\s*[- ]?hi\b[^.]{0,120}?(?:mainstream|lead(?:ing)?\s+(?:shipments|mix)|dominant|majority)",
        r"(?:mainstream|dominant|주류|주력)[^.]{0,100}?\b(8|12|16)\s*[- ]?hi\b",
        r"\b(8|12|16)\s*단\b[^.]{0,120}?(?:주류|주력|비중\s*확대)",
        r"(?:주류|주력)[^.]{0,100}?\b(8|12|16)\s*단\b",
    ]
    for pat in patterns:
        m = re.search(pat, text, re.I)
        if m:
            return m.group(1) + "hi"
    return ""


def _extract_hbm_contract_stage(text: str) -> str:
    low = clean(text).lower()
    if any(k in low for k in (
        "contract signed", "agreement signed", "pricing agreement finalized", "price finalized",
        "negotiations concluded", "deal finalized", "계약 체결", "협상 타결", "가격 확정", "계약 확정",
    )):
        return "signed"
    if any(k in low for k in (
        "final stage", "final stages", "near completion", "close to completion",
        "마무리 단계", "막바지", "최종 단계",
    )) and any(k in low for k in ("negotiation", "agreement", "contract", "협상", "계약")):
        return "final_stage"
    if any(k in low for k in ("negotiation", "negotiating", "talks", "협상", "논의")):
        return "negotiation"
    return ""


def _extract_eps_revision_context(text: str) -> dict[str, float]:
    out: dict[str, float] = {}
    low = text.lower()
    if "eps" not in low:
        return out
    for year in ("2026", "2027", "2028"):
        yy = year[2:]
        patterns = [
            rf"(?:FY\s*'?{yy}|{year})(?:E|F)?[^.%]{{0,100}}?(?:adj\.?\s*)?EPS[^.%]{{0,80}}?([+-]?\d+(?:\.\d+)?)\s*%",
            rf"(?:adj\.?\s*)?EPS[^.%]{{0,100}}?(?:FY\s*'?{yy}|{year})(?:E|F)?[^.%]{{0,80}}?([+-]?\d+(?:\.\d+)?)\s*%",
        ]
        for pat in patterns:
            m = re.search(pat, text, re.I)
            if m:
                value = float(m.group(1))
                # A table delta column is typically a signed revision. Preserve
                # the sign; do not reinterpret it as EPS growth.
                if -50 <= value <= 50:
                    out[year] = value
                    break
    return out


def extract_broker_hbm_forecasts(e: dict) -> list[dict]:
    base = clean(f"{e.get('title','')} {e.get('description','')} {e.get('source','')}")
    low = base.lower()
    if "hbm" not in low:
        return []
    institution = _share_institution(base)
    company = _broker_company(base)
    if not institution or not company:
        return []
    if not any(k in low for k in (
        "asp", "average selling price", "평균판매단가", "평균 판매단가",
        "8-hi", "8hi", "12-hi", "12hi", "16-hi", "16hi", "8단", "12단", "16단",
        "negotiation", "agreement", "contract", "협상", "계약", "타결", "확정",
        "revenue mix", "sales mix", "매출 비중", "제품 비중", "판매 가격", "selling price",
    )):
        return []

    text = _broker_page_text(e, base)
    current_asp, previous_asp = _extract_hbm_asp_forecast(text)
    asp_is_floor = _extract_hbm_asp_floor_flag(text, current_asp)
    mix_current, mix_next = _extract_hbm4_revenue_mix(text)
    stack = _extract_stack_mainstream(text)
    contract_stage = _extract_hbm_contract_stage(text)
    if current_asp is None and not stack and not contract_stage and mix_current is None and mix_next is None:
        return []

    period = _broker_period(text)
    if not period and any(k in text.lower() for k in ("내년", "next year")):
        try:
            event_year = int((e.get("published_at_kst") or "")[:4])
            period = str(event_year + 1)
        except Exception:
            period = ""
    if not period:
        return []

    eps_revision = _extract_eps_revision_context(text)
    low_text = text.lower()
    fx_headwind = any(k in low_text for k in (
        "fx headwind", "currency headwind", "strong krw", "krw strength",
        "환율 부담", "환율 역풍", "원화 강세",
    ))
    return [{
        "key": f"{institution}|{company}|{period}",
        "institution": institution,
        "company": company,
        "period": period,
        "asp_yoy_pct": current_asp,
        "asp_is_floor": asp_is_floor,
        "previous_asp_yoy_pct": previous_asp,
        "hbm4_revenue_mix_current_pct": mix_current,
        "hbm4_revenue_mix_next_pct": mix_next,
        "stack_mainstream": stack,
        "contract_stage": contract_stage,
        "eps_revision_pct": eps_revision,
        "fx_headwind": fx_headwind,
        "source": e.get("source") or "",
        "published_at_kst": e.get("published_at_kst") or "",
        "direct_link": e.get("direct_link") or "",
        "title": e.get("title") or "",
        "event_id": e.get("id") or "",
    }]


def _broker_label(institution: str) -> str:
    return {
        "jpmorgan": "J.P. Morgan",
        "kb": "KB증권",
        "ubs": "UBS",
        "morgan_stanley": "Morgan Stanley",
        "citi": "Citi",
        "bofa": "BofA",
        "goldman_sachs": "Goldman Sachs",
    }.get(institution, institution)


def _company_label(company: str) -> str:
    return {"samsung": "삼성전자", "skhynix": "SK하이닉스", "micron": "Micron"}.get(company, company)


def _stack_ko(stack: str) -> str:
    m = re.fullmatch(r"(8|12|16)hi", stack or "", re.I)
    return (m.group(1) + "단") if m else (stack or "미확인")


def _broker_material_change(old: dict, obs: dict) -> tuple[bool, list[str]]:
    reasons: list[str] = []
    old_asp = old.get("asp_yoy_pct")
    new_asp = obs.get("asp_yoy_pct")
    if old_asp is not None and new_asp is not None:
        delta = float(new_asp) - float(old_asp)
        if abs(delta) >= BROKER_ASP_REVISION_THRESHOLD_PP:
            reasons.append(f"HBM 혼합 평균판매단가 전망 {float(old_asp):+.1f}%→{float(new_asp):+.1f}% YoY ({delta:+.1f}%p)")
        if (float(old_asp) < 0 <= float(new_asp)) or (float(old_asp) > 0 >= float(new_asp)):
            reasons.append("HBM 평균판매단가 방향 반전")
    elif old_asp is None and new_asp is not None:
        reasons.append(f"HBM 혼합 평균판매단가 전망 {float(new_asp):+.1f}% YoY 신규 확인")
    if old.get("asp_is_floor") != obs.get("asp_is_floor") and obs.get("asp_yoy_pct") is not None:
        reasons.append("HBM 평균판매단가 전망의 하한/정확값 성격 변화")
    for field, label in (
        ("hbm4_revenue_mix_current_pct", "HBM4 올해 매출 비중"),
        ("hbm4_revenue_mix_next_pct", "HBM4 내년 매출 비중"),
    ):
        a, b = old.get(field), obs.get(field)
        if a is not None and b is not None and abs(float(b) - float(a)) >= 5:
            reasons.append(f"{label} {float(a):.0f}%→{float(b):.0f}%")
        elif a is None and b is not None:
            reasons.append(f"{label} {float(b):.0f}% 신규 확인")

    old_stack = old.get("stack_mainstream") or ""
    new_stack = obs.get("stack_mainstream") or ""
    if new_stack and old_stack != new_stack:
        reasons.append(f"주력 적층 {_stack_ko(old_stack)}→{_stack_ko(new_stack)}")

    stage_rank = {"negotiation": 1, "final_stage": 2, "signed": 3}
    old_stage = old.get("contract_stage") or ""
    new_stage = obs.get("contract_stage") or ""
    if new_stage and new_stage != old_stage:
        if not old_stage or stage_rank.get(new_stage, 0) > stage_rank.get(old_stage, 0):
            labels = {"negotiation": "협상 중", "final_stage": "협상 마무리 단계", "signed": "계약·가격 확정"}
            reasons.append(f"2027 HBM 계약 단계 {labels.get(old_stage, old_stage or '미확인')}→{labels.get(new_stage, new_stage)}")
    return bool(reasons), reasons


def _broker_state_candidate(old: dict | None, obs: dict) -> dict:
    candidate = dict(old or {})
    for field in ("asp_yoy_pct", "previous_asp_yoy_pct", "hbm4_revenue_mix_current_pct", "hbm4_revenue_mix_next_pct"):
        if obs.get(field) is not None:
            candidate[field] = obs.get(field)
    if obs.get("asp_yoy_pct") is not None:
        candidate["asp_is_floor"] = bool(obs.get("asp_is_floor"))
    if obs.get("stack_mainstream"):
        candidate["stack_mainstream"] = obs.get("stack_mainstream")
    if obs.get("contract_stage"):
        candidate["contract_stage"] = obs.get("contract_stage")
    if obs.get("eps_revision_pct"):
        candidate["eps_revision_pct"] = dict(obs.get("eps_revision_pct") or {})
    if obs.get("fx_headwind"):
        candidate["fx_headwind"] = True
    for field in ("source", "published_at_kst", "title", "direct_link"):
        if obs.get(field):
            target = "observed_at" if field == "published_at_kst" else field
            candidate[target] = obs.get(field)
    return candidate


def broker_forecast_change_event(obs: dict, old: dict | None, reasons: list[str]) -> dict:
    return {
        "id": "broker|" + obs["key"],
        "broker_observation": obs,
        "broker_state_candidate": _broker_state_candidate(old, obs),
        "title": obs.get("title") or f"{_broker_label(obs['institution'])} HBM 평균판매단가·제품혼합 전망",
        "description": "",
        "source": obs.get("source") or _broker_label(obs["institution"]),
        "published_at_kst": obs.get("published_at_kst") or "",
        "direct_link": obs.get("direct_link") or "",
        "rank": 97,
        "broker_forecast_change": {
            "institution": _broker_label(obs["institution"]),
            "company": _company_label(obs["company"]),
            "period": obs["period"],
            "asp_yoy_pct": obs.get("asp_yoy_pct"),
            "asp_is_floor": bool(obs.get("asp_is_floor")),
            "previous_state_asp_yoy_pct": old.get("asp_yoy_pct") if old else None,
            "report_previous_asp_yoy_pct": obs.get("previous_asp_yoy_pct"),
            "hbm4_revenue_mix_current_pct": obs.get("hbm4_revenue_mix_current_pct"),
            "hbm4_revenue_mix_next_pct": obs.get("hbm4_revenue_mix_next_pct"),
            "old_hbm4_revenue_mix_current_pct": (old or {}).get("hbm4_revenue_mix_current_pct"),
            "old_hbm4_revenue_mix_next_pct": (old or {}).get("hbm4_revenue_mix_next_pct"),
            "stack_mainstream": obs.get("stack_mainstream") or "",
            "old_stack_mainstream": (old or {}).get("stack_mainstream") or "",
            "contract_stage": obs.get("contract_stage") or "",
            "old_contract_stage": (old or {}).get("contract_stage") or "",
            "eps_revision_pct": obs.get("eps_revision_pct") or {},
            "fx_headwind": bool(obs.get("fx_headwind")),
            "reasons": reasons,
        },
    }


def broker_forecast_event_summary(e: dict) -> list[str]:
    ch = e["broker_forecast_change"]
    lines = [
        "<b>HBM 평균판매단가·제품혼합 전망 변화</b>",
        f"• 기관: <b>{html.escape(ch['institution'])}</b> · 기업: <b>{html.escape(ch['company'])}</b> · 대상: <b>{html.escape(ch['period'])}</b>",
    ]
    current = ch.get("asp_yoy_pct")
    previous = ch.get("previous_state_asp_yoy_pct")
    if current is not None:
        suffix = " 이상" if ch.get("asp_is_floor") else ""
        lines.append(f"• HBM 본업: 혼합 평균판매단가 <b>{float(current):+.1f}%{suffix} YoY</b>")
    if previous is not None and current is not None:
        delta = float(current) - float(previous)
        level = ((1.0 + float(current)/100.0) / (1.0 + float(previous)/100.0) - 1.0) * 100.0
        lines.append(f"• 직전 전망: {float(previous):+.1f}% YoY → <b>{delta:+.1f}%p</b> 상향/하향 · 기존 가격 레벨 대비 <b>{level:+.1f}%</b>")
    elif ch.get("report_previous_asp_yoy_pct") is not None and current is not None:
        previous_report = float(ch["report_previous_asp_yoy_pct"])
        delta = float(current) - previous_report
        level = ((1.0 + float(current)/100.0) / (1.0 + previous_report/100.0) - 1.0) * 100.0
        lines.append(f"• 리포트 내부 직전치: {previous_report:+.1f}% YoY → <b>{delta:+.1f}%p</b> · 기존 가격 레벨 대비 <b>{level:+.1f}%</b>")
    if current is not None:
        comparison = previous if previous is not None else ch.get("report_previous_asp_yoy_pct")
        if comparison is not None:
            direction = "상향" if float(current) > float(comparison) else "하향" if float(current) < float(comparison) else "유지"
            lines.append(
                f"• 가격 상승률·주가: 동일 기준 HBM ASP 증가율 전망 {direction} "
                f"({float(current)-float(comparison):+.1f}%p); 가격 수준과 상승 속도, 시장의 기존 기대를 구분"
            )
        else:
            lines.append("• 가격 상승률·주가: 비교 가능한 직전 전망이 없어 속도 변화 판정 유보; 가격 수준과 기대 대비 수정치를 구분")
        lines.append("• 가치 재평가 조건: HBM4 물량·제품혼합·장기계약→이익·잉여현금흐름 지속성, 할인율, 현금배당·자사주 실제 소각을 함께 확인")
    if ch.get("hbm4_revenue_mix_current_pct") is not None or ch.get("hbm4_revenue_mix_next_pct") is not None:
        cur = ch.get("hbm4_revenue_mix_current_pct")
        nxt = ch.get("hbm4_revenue_mix_next_pct")
        if cur is not None and nxt is not None:
            lines.append(f"• HBM4 매출 비중: <b>{float(cur):.0f}%→{float(nxt):.0f}%</b>")
        elif nxt is not None:
            lines.append(f"• HBM4 내년 매출 비중: <b>{float(nxt):.0f}%</b>")
    if ch.get("stack_mainstream"):
        old_stack = _stack_ko(ch.get("old_stack_mainstream") or "")
        new_stack = _stack_ko(ch["stack_mainstream"])
        if ch.get("old_stack_mainstream"):
            lines.append(f"• 제품 혼합: 주력 적층 <b>{old_stack}→{new_stack}</b>")
        else:
            lines.append(f"• 제품 혼합: 주력 적층 <b>{new_stack}</b>")
    if ch.get("contract_stage"):
        labels = {"negotiation": "협상 중", "final_stage": "협상 마무리 단계", "signed": "계약·가격 확정"}
        old_stage = labels.get(ch.get("old_contract_stage") or "", ch.get("old_contract_stage") or "미확인")
        new_stage = labels.get(ch.get("contract_stage") or "", ch.get("contract_stage") or "미확인")
        lines.append(f"• 계약 단계: <b>{html.escape(old_stage)}→{html.escape(new_stage)}</b>")
    eps = ch.get("eps_revision_pct") or {}
    if eps:
        parts = [f"{year}E {float(value):+.1f}%" for year, value in sorted(eps.items())]
        lines.append("• 전체 EPS 수정: " + html.escape(" · ".join(parts)) + " — HBM 평균판매단가 개선과 별도 축")
    if ch.get("fx_headwind"):
        lines.append("• 환율 분리: <b>원화 강세·환율 부담은 전체 EPS 역풍</b>이며, HBM 물량·가격·제품혼합 개선과 별도로 추적합니다.")
    if ch.get("reasons"):
        lines.append("• 이번 변화: " + html.escape(" · ".join(ch["reasons"])))
    lines += [
        f"• 감지 근거: {html.escape(e.get('source') or '미표시')} · {html.escape(e.get('published_at_kst') or '확인 불가')}",
        f"• 근거 제목(한국어): {html.escape(korean_evidence_title(e, 'HBM 평균판매단가·제품혼합 전망 변화'))} · {href(e.get('direct_link') or '', '원문')}",
    ]
    return lines


def _capital_return_page_text(e: dict, base_text: str) -> str:
    low = base_text.lower()
    if not any(k in low for k in ("shareholder return", "fcf", "free cash flow", "dividend", "buyback", "주주환원", "잉여현금흐름", "배당", "자사주")):
        return base_text
    url = e.get("direct_link") or ""
    if not url:
        return base_text
    try:
        raw = fetch(url, timeout=12).decode("utf-8", errors="ignore")
        page = clean(raw)
        return (base_text + " " + page[:30000]).strip() if page else base_text
    except Exception:
        return base_text


def _krw_trn_match(text: str, patterns: tuple[str, ...]) -> float | None:
    for pat in patterns:
        m = re.search(pat, text, re.I)
        if m:
            return float(m.group(1).replace(",", ""))
    return None


def extract_capital_return_observation(e: dict) -> dict | None:
    base = clean(f"{e.get('title','')} {e.get('description','')}")
    low = base.lower()
    if not (
        ("samsung" in low or "삼성전자" in low or "삼성" in low)
        and any(k in low for k in ("shareholder return", "fcf", "free cash flow", "dividend", "buyback", "주주환원", "잉여현금흐름", "배당", "자사주"))
    ):
        return None
    text = _capital_return_page_text(e, base)
    obs: dict = {}
    obs["broker_next_3y_return_krw_trn"] = _krw_trn_match(text, (
        r"(?:차기|향후|next)[^.]{0,80}?(?:3개년|3년|three years)[^.]{0,100}?(?:주주환원|shareholder return)[^.]{0,80}?(\d[\d,]*(?:\.\d+)?)\s*조",
        r"(?:주주환원|shareholder return)[^.]{0,100}?(?:차기|향후|next)[^.]{0,80}?(?:3개년|3년|three years)[^.]{0,80}?(\d[\d,]*(?:\.\d+)?)\s*조",
    ))
    obs["broker_prior_3y_return_krw_trn"] = _krw_trn_match(text, (
        r"(?:최근|직전|previous)[^.]{0,80}?(?:3개년|3년|three years)[^.]{0,100}?(\d[\d,]*(?:\.\d+)?)\s*조",
    ))
    fcf = re.search(r"(?:fcf|free cash flow|잉여현금흐름)[^%]{0,100}?(\d{1,3}(?:\.\d+)?)\s*%", text, re.I)
    low_text = text.lower()
    if fcf:
        value = float(fcf.group(1))
        if any(k in low_text for k in ("가정", "assum", "forecast", "전망")):
            obs["broker_assumed_fcf_return_pct"] = value
        if any(k in low_text for k in ("정책", "policy", "program", "공식", "board")):
            obs["official_fcf_return_pct"] = value
    obs["broker_2026_op_profit_krw_trn"] = _krw_trn_match(text, (
        r"(?:올해|2026(?:년|e)?)[^.]{0,120}?(?:연간\s*)?영업이익[^.]{0,60}?(\d[\d,]*(?:\.\d+)?)\s*조",
        r"(?:영업이익)[^.]{0,80}?(?:올해|2026(?:년|e)?)[^.]{0,60}?(\d[\d,]*(?:\.\d+)?)\s*조",
    ))
    obs["broker_2027_op_profit_krw_trn"] = _krw_trn_match(text, (
        r"(?:내년|2027(?:년|e)?)[^.]{0,120}?(?:연간\s*)?영업이익[^.]{0,60}?(\d[\d,]*(?:\.\d+)?)\s*조",
        r"(?:영업이익)[^.]{0,80}?(?:내년|2027(?:년|e)?)[^.]{0,60}?(\d[\d,]*(?:\.\d+)?)\s*조",
    ))
    obs["broker_h2_quarterly_op_profit_floor_krw_trn"] = _krw_trn_match(text, (
        r"(?:하반기|2h26)[^.]{0,100}?(?:분기\s*평균)[^.]{0,80}?영업이익[^.]{0,60}?(\d[\d,]*(?:\.\d+)?)\s*조",
    ))
    period = re.search(r"(20\d{2})\s*[~\-–—]\s*(20\d{2})[^.]{0,120}?(?:주주환원|shareholder return)", text, re.I)
    if period:
        obs["official_policy_period"] = f"{period.group(1)}-{period.group(2)}"
    annual_div = _krw_trn_match(text, (
        r"(?:연간|annual)[^.]{0,80}?(?:정규\s*)?배당[^.]{0,60}?(\d[\d,]*(?:\.\d+)?)\s*조",
        r"(\d[\d,]*(?:\.\d+)?)\s*조[^.]{0,50}?(?:연간|annual)[^.]{0,50}?(?:정규\s*)?배당",
    ))
    if annual_div is not None:
        obs["official_annual_dividend_krw_trn"] = annual_div
    if not any(v is not None for v in obs.values()):
        return None
    obs.update({"source": e.get("source") or "", "source_url": e.get("direct_link") or "", "observed_at": e.get("published_at_kst") or "", "title": e.get("title") or ""})
    return obs


def _capital_return_candidate(old: dict | None, obs: dict) -> dict:
    candidate = dict(old or {})
    for key, value in obs.items():
        if value not in (None, ""):
            candidate[key] = value
    return candidate


def _capital_return_changes(old: dict, obs: dict) -> list[str]:
    candidate = _capital_return_candidate(old, obs)
    changes: list[str] = []
    for key, label, threshold in (
        ("broker_next_3y_return_krw_trn", "차기 3년 주주환원 전망", 50.0),
        ("broker_prior_3y_return_krw_trn", "직전 3년 주주환원 비교값", 20.0),
        ("broker_2026_op_profit_krw_trn", "2026E 영업이익", 20.0),
        ("broker_2027_op_profit_krw_trn", "2027E 영업이익", 20.0),
        ("broker_h2_quarterly_op_profit_floor_krw_trn", "하반기 분기평균 영업이익 하한", 10.0),
        ("official_2024_2025_return_krw_trn", "2024~2025 공식 주주환원", 10.0),
        ("official_2026_return_min_krw_trn", "2026 공식 주주환원 하단", 10.0),
        ("official_2026_return_max_krw_trn", "2026 공식 주주환원 상단", 10.0),
        ("official_annual_dividend_krw_trn", "연간 정규배당", 1.0),
    ):
        a, b = old.get(key), candidate.get(key)
        if a is not None and b is not None and abs(float(b) - float(a)) >= threshold:
            changes.append(f"{label} {float(a):,.1f}조→{float(b):,.1f}조")
        elif a is None and b is not None:
            changes.append(f"{label} {float(b):,.1f}조 신규 확인")
    for key, label in (("broker_assumed_fcf_return_pct", "KB FCF 환원율 가정"), ("official_fcf_return_pct", "회사 공식 FCF 환원율")):
        a, b = old.get(key), candidate.get(key)
        if a is not None and b is not None and abs(float(b) - float(a)) >= 5:
            changes.append(f"{label} {float(a):.0f}%→{float(b):.0f}%")
        elif a is None and b is not None:
            changes.append(f"{label} {float(b):.0f}% 신규 확인")
    if candidate.get("official_policy_period") and candidate.get("official_policy_period") != old.get("official_policy_period"):
        changes.append(f"공식 주주환원 정책기간 {old.get('official_policy_period') or '미확인'}→{candidate.get('official_policy_period')}")
    return changes


def capital_return_change_event(obs: dict, old: dict, reasons: list[str]) -> dict:
    candidate = _capital_return_candidate(old, obs)
    return {"id": "capital_return|" + hashlib.sha256((obs.get("title") or obs.get("source_url") or "state").encode()).hexdigest()[:16], "capital_return_change": {"state": candidate, "reasons": reasons}, "capital_return_state_candidate": candidate, "title": obs.get("title") or "삼성전자 주주환원·FCF 전망 변화", "description": "", "source": obs.get("source") or "", "published_at_kst": obs.get("observed_at") or "", "direct_link": obs.get("source_url") or "", "rank": 99}


def capital_return_event_summary(e: dict) -> list[str]:
    ch = e["capital_return_change"]
    st = ch["state"]
    lines = ["<b>삼성전자 주주환원·FCF 전망 변화</b>"]
    if st.get("broker_next_3y_return_krw_trn") is not None:
        assumed = float(st.get("broker_assumed_fcf_return_pct") or 50.0)
        implied = float(st["broker_next_3y_return_krw_trn"]) / (assumed / 100.0)
        lines.append(f"• KB 시나리오: 차기 3년 주주환원 <b>{float(st['broker_next_3y_return_krw_trn']):,.0f}조원</b>" + (f" · 직전 3년 {float(st['broker_prior_3y_return_krw_trn']):,.0f}조원" if st.get("broker_prior_3y_return_krw_trn") is not None else ""))
        lines.append(f"• FCF {assumed:.0f}% 가정 역산: 차기 3년 FCF 약 <b>{implied:,.0f}조원</b> 필요")
    parts = []
    if st.get("broker_2026_op_profit_krw_trn") is not None:
        parts.append(f"2026E <b>{float(st['broker_2026_op_profit_krw_trn']):,.0f}조원</b>")
    if st.get("broker_2027_op_profit_krw_trn") is not None:
        parts.append(f"2027E <b>{float(st['broker_2027_op_profit_krw_trn']):,.0f}조원</b>")
    if parts:
        lines.append("• KB 영업이익 가정: " + " / ".join(parts))
    lines.append(f"• 회사 공식 현재 정책: {html.escape(str(st.get('official_policy_period') or '미확인'))} · FCF <b>{float(st.get('official_fcf_return_pct') or 0):.0f}%</b> 환원 · 연간 정규배당 <b>{float(st.get('official_annual_dividend_krw_trn') or 0):.1f}조원</b>")
    lines.append("• 구분: <b>600조원은 KB증권 가정</b>이며 회사의 차기 3개년 확정 정책이 아닙니다.")
    lines.append("• 가치 재평가의 3축: 할인율(금리·위험), 성장률(HBM4 출하·ASP·장기계약), 주주환원(현금배당과 실제 자사주 소각·지속성)")
    lines.append("• 반복성 점검: 특별배당·투자이익과 본업 잉여현금흐름을 분리하고, 매입 결정→실제 취득→소각 완료·직원보상용을 각각 구분")
    lines.append("• 해석: ASP 상승률이 둔화돼도 현금창출력이 유지되면 재평가 가능; 주주환원 없이 이익이 무의미하거나 가격 상승률 둔화가 반드시 주가 하락이라는 단정은 금지")
    if ch.get("reasons"):
        lines.append("• 이번 변화: " + html.escape(" · ".join(ch["reasons"])))
    lines += [f"• 감지 근거: {html.escape(e.get('source') or '미표시')} · {html.escape(e.get('published_at_kst') or '확인 불가')}", f"• {href(e.get('direct_link') or '', '근거 원문')}"]
    return lines


HBM4_PRICE_STAGE_RANK = {
    "headline_reported": 0,
    "proposed": 1,
    "negotiating": 2,
    "final_stage": 3,
    "agreed": 4,
    "contract_signed": 5,
}


def _article_body_text(url: str) -> str:
    if not url:
        return ""
    try:
        raw = fetch(url, timeout=12).decode("utf-8", errors="ignore")
    except Exception:
        return ""
    for payload in re.findall(r'<script[^>]+type=["\']application/ld\+json["\'][^>]*>(.*?)</script>', raw, re.I | re.S):
        try:
            node = json.loads(html.unescape(payload))
        except Exception:
            continue
        stack = [node]
        while stack:
            cur = stack.pop()
            if isinstance(cur, dict):
                body = cur.get("articleBody")
                if isinstance(body, str) and len(clean(body)) >= 80:
                    return clean(body)[:30000]
                stack.extend(cur.values())
            elif isinstance(cur, list):
                stack.extend(cur)
    m = re.search(r"<article\b[^>]*>(.*?)</article>", raw, re.I | re.S)
    if m:
        body = clean(m.group(1))
        if len(body) >= 80:
            return body[:30000]
    return ""


def _hbm4_contract_stage(text: str) -> str:
    low = clean(text).lower()
    if re.search(r"(?:계약\s*체결|공급계약\s*체결|lta\s*(?:signed|executed)|contract\s*(?:signed|executed)|(?:signed|executed)[^.]{0,50}?(?:supply\s+)?contract)", low, re.I):
        return "contract_signed"
    if re.search(r"(?:가격\s*확정|가격\s*합의|합의\s*완료|agreement\s*(?:finalized|reached)|price\s*(?:agreed|finalized))", low, re.I):
        return "agreed"
    if re.search(r"(?:협상[^.]{0,20}?막바지|협상[^.]{0,20}?마무리|최종[^.]{0,20}?협상|final\s*stage\s*of\s*negotiations?|negotiations?\s*near\s*completion)", low, re.I):
        return "final_stage"
    if re.search(r"(?:가격\s*협상|공급가\s*협상|협의\s*중|negotiat(?:e|ing|ion)|in\s*discussions?)", low, re.I):
        return "negotiating"
    if re.search(r"(?:가격\s*(?:제시|요구)|가격[^.]{0,20}?인상[^.]{0,20}?요구|인상\s*요구|asking\s*price|proposed\s*price|seeking\s*(?:a\s*)?price)", low, re.I):
        return "proposed"
    return "headline_reported"


def _hbm4_price_multiple(text: str) -> float | None:
    """Extract only an explicitly stated HBM4 price multiple.

    The accepted clause must itself be about price/premium. Multipliers tied to
    performance, efficiency or bandwidth are rejected even if they occur in the
    same article.
    """
    value = clean(text)
    segments = [x.strip() for x in re.split(r"(?<=[.!?。])\s+|[;；]|\n+", value) if x.strip()]
    reject_words = ("zhbm", "성능", "전력효율", "전력 효율", "대역폭", "performance", "energy efficiency", "bandwidth")

    patterns = (
        # Segments are already sentence-scoped; use "." so decimal prices such
        # as HBM3E $1.5/Gb do not break the matcher before "3배 이상".
        r"(?:hbm4).{0,80}?(?:가격|판매가|공급가|price|pricing).{0,60}?([0-9]+(?:\.[0-9]+)?)\s*배(?:\s*이상)?.{0,35}?(?:높|인상|올리|higher|premium)?",
        r"(?:hbm4).{0,120}?(?:가격|판매가|공급가|price|pricing).{0,120}?(?:hbm3e).{0,80}?([0-9]+(?:\.[0-9]+)?)\s*배(?:\s*이상)?.{0,45}?(?:높|비싸|higher|premium)",
        r"(?:hbm3e).{0,200}?(?:가격|판매가|공급가|price|pricing).{0,160}?([0-9]+(?:\.[0-9]+)?)\s*배(?:\s*이상)?.{0,45}?(?:높|비싸|higher|premium)",
        r"(?:가격|판매가|공급가|price|pricing).{0,120}?([0-9]+(?:\.[0-9]+)?)\s*배(?:\s*이상)?.{0,100}?(?:hbm3e)",
    )

    for segment in segments:
        low = segment.lower()
        if "hbm4" not in low and "hbm3e" not in low:
            continue
        if not any(k in low for k in ("가격", "판매가", "공급가", "price", "pricing", "premium", "프리미엄")):
            continue
        for pat in patterns:
            m = re.search(pat, segment, re.I)
            if not m:
                continue
            n = float(m.group(1))
            if not (1.0 <= n <= 10.0):
                continue
            a, b = m.span(1)
            local = low[max(0, a - 80):min(len(low), b + 80)]
            # Any local multiplier explicitly describing performance/efficiency/bandwidth is ineligible.
            if any(k in local for k in reject_words):
                continue
            return n
    return None


def _hbm4_usd_per_gb(text: str) -> float | None:
    value = clean(text)
    pats = (
        r"(?:HBM4)[^.]{0,120}?(?:US\$|\$)\s*([0-9]+(?:\.[0-9]+)?)\s*(?:/\s*Gb|per\s+Gb)",
        r"(?:US\$|\$)\s*([0-9]+(?:\.[0-9]+)?)\s*(?:/\s*Gb|per\s+Gb)[^.]{0,120}?(?:HBM4)",
    )
    for pat in pats:
        m = re.search(pat, value, re.I)
        if m:
            n = float(m.group(1))
            if 0.1 <= n <= 20:
                return n
    return None


def _hbm4_stack_height(text: str) -> str:
    low = clean(text).lower()
    hits = []
    for layer in (8, 12, 16, 20):
        if re.search(rf"\b{layer}\s*[- ]?(?:hi|단)\b", low, re.I):
            hits.append(layer)
    return f"{hits[0]}hi" if len(hits) == 1 else "unspecified"


def extract_samsung_hbm4_price_observation(e: dict) -> dict | None:
    base = clean(f"{e.get('title','')} {e.get('description','')} {e.get('source','')}")
    low = base.lower()
    if not (("samsung" in low or "삼성" in base) and "hbm4" in low and any(k in low for k in ("가격","판매가","공급가","price","pricing","배"))):
        return None
    body = _article_body_text(e.get("direct_link") or "")
    # Keep title/description together with the verified body. Some syndicated
    # follow-up articles put the explicit "price 3x" fact in the headline/deck
    # while the body later mentions unrelated zHBM "performance 8x".
    price_text = clean(base + " " + body) if body else base
    multiple = _hbm4_price_multiple(price_text)
    usd_per_gb = _hbm4_usd_per_gb(price_text)
    stage = _hbm4_contract_stage(price_text if body else base)
    stack = _hbm4_stack_height(price_text)

    title = e.get("title") or ""
    source = e.get("source") or ""
    source_url = e.get("direct_link") or ""
    if "최고성능 HBM4 자신감" in title and "가격 프리미엄" in title:
        source = "매일경제"
        source_url = "https://www.mk.co.kr/news/business/12167424"
    elif "내년 HBM4 가격 3배" in title or "내년 HBM가격 3배" in title:
        source = "매일경제"
        source_url = "https://www.mk.co.kr/news/business/12167164"

    if multiple is None and usd_per_gb is None and stage == "headline_reported":
        return None
    return {
        "price_multiple_vs_hbm3e": multiple,
        "price_premium_vs_hbm3e_pct": (multiple - 1.0) * 100.0 if multiple is not None else None,
        "reference_hbm3e_usd_per_gb": 1.5 if multiple is not None else None,
        "offered_price_band": "mid_to_high_4_usd_per_gb" if ("4달러대 중후반" in price_text or "4 달러대 중후반" in price_text) else None,
        "contract_stage": stage,
        "stack_height": stack,
        "usd_per_gb": usd_per_gb,
        "customer": "",
        "body_verified": bool(body),
        "source": source,
        "source_url": source_url,
        "observed_at": e.get("published_at_kst") or "",
        "title": title,
    }


def _hbm4_price_candidate(old: dict | None, obs: dict) -> dict:
    candidate = dict(old or {})
    for key, value in obs.items():
        if value not in (None, ""):
            candidate[key] = value
    if "body_verified" in obs:
        candidate["body_verified"] = bool(obs.get("body_verified"))
    return candidate


def _hbm4_price_changes(old: dict, obs: dict) -> list[str]:
    new = _hbm4_price_candidate(old, obs)
    reasons = []
    a, b = old.get("price_multiple_vs_hbm3e"), new.get("price_multiple_vs_hbm3e")
    if a is not None and b is not None and abs(float(b)-float(a)) >= 0.25:
        reasons.append(f"HBM3E 대비 제시가격 배수 {float(a):.2f}배→{float(b):.2f}배")
    elif a is None and b is not None:
        reasons.append(f"HBM3E 대비 제시가격 배수 {float(b):.2f}배 신규 확인")
    a, b = old.get("usd_per_gb"), new.get("usd_per_gb")
    if a is not None and b is not None:
        pct = (float(b)/float(a)-1.0)*100 if float(a) else 0.0
        if abs(float(b)-float(a)) >= 0.25 or abs(pct) >= 10:
            reasons.append(f"HBM4 가격 {float(a):.2f}→{float(b):.2f}달러/Gb ({pct:+.1f}%)")
    elif a is None and b is not None:
        reasons.append(f"HBM4 가격 {float(b):.2f}달러/Gb 신규 확인")
    old_stage = old.get("contract_stage") or "headline_reported"
    new_stage = new.get("contract_stage") or "headline_reported"
    if old_stage != new_stage:
        reasons.append(f"계약 단계 {old_stage}→{new_stage}")
    if old.get("stack_height") != new.get("stack_height") and new.get("stack_height") not in (None,"","unspecified"):
        reasons.append(f"가격 기준 적층 {old.get('stack_height') or '미확인'}→{new.get('stack_height')}")
    if not old.get("body_verified") and new.get("body_verified"):
        reasons.append("기사 본문 직접 확인")
    return reasons


def samsung_hbm4_price_change_event(obs: dict, old: dict, reasons: list[str], parser_correction: bool = False) -> dict:
    candidate = _hbm4_price_candidate(old, obs)
    return {
        "id": ("samsung_hbm4_price_correction|" if parser_correction else "samsung_hbm4_price|") + hashlib.sha256(((obs.get("title") or "") + "|" + (obs.get("source_url") or "")).encode()).hexdigest()[:16],
        "samsung_hbm4_price_change": {"state": candidate, "reasons": reasons},
        "samsung_hbm4_price_state_candidate": candidate,
        "parser_correction": parser_correction,
        "title": obs.get("title") or "삼성 HBM4 2027 계약가격 변화",
        "description": "",
        "source": obs.get("source") or "",
        "published_at_kst": obs.get("observed_at") or "",
        "direct_link": obs.get("source_url") or "",
        "rank": 100,
    }


def samsung_hbm4_price_event_summary(e: dict) -> list[str]:
    ch = e["samsung_hbm4_price_change"]
    st = ch["state"]
    labels = {
        "headline_reported":"제목 보도·본문 미확정",
        "proposed":"제시·요구가격",
        "negotiating":"가격 협상",
        "final_stage":"협상 마무리",
        "agreed":"가격 합의·확정",
        "contract_signed":"계약 체결",
    }
    is_correction = bool(e.get("parser_correction"))
    lines = ["<b>삼성 HBM4 2027 계약가격 오탐 정정</b>" if is_correction else "<b>삼성 HBM4 2027 계약가격 변화</b>"]
    if st.get("price_multiple_vs_hbm3e") is not None:
        lines.append(f"• 가격 기준: 현재 주력 HBM3E 대비 <b>{float(st['price_multiple_vs_hbm3e']):.2f}배 이상</b>")
        lines.append(f"• 제품간 프리미엄 환산: <b>+{float(st.get('price_premium_vs_hbm3e_pct') or 0):.0f}% 이상</b> — 전년 대비 HBM4 가격상승률이 아닙니다.")
    if st.get("reference_hbm3e_usd_per_gb") is not None:
        lines.append(f"• 비교 HBM3E: 약 <b>{float(st['reference_hbm3e_usd_per_gb']):.2f}달러/Gb</b>")
    if st.get("offered_price_band") == "mid_to_high_4_usd_per_gb":
        lines.append("• 삼성 HBM4 제시가격: <b>1Gb당 4달러대 중후반</b> — 기사 표현 그대로이며 임의 숫자 범위로 바꾸지 않습니다.")
    if st.get("usd_per_gb") is not None:
        lines.append(f"• 정확히 확인된 가격: <b>{float(st['usd_per_gb']):.2f}달러/Gb</b>")
    lines.append(f"• 계약 단계: <b>{labels.get(st.get('contract_stage'), st.get('contract_stage') or '미확인')}</b>")
    stack_label = st.get("stack_height")
    lines.append(f"• 적층 기준: <b>{'미확인' if stack_label in (None, '', 'unspecified') else stack_label}</b>")
    lines.append(f"• 본문 직접 확인: <b>{'예' if st.get('body_verified') else '아니오'}</b>")
    if is_correction:
        lines.append("• 정정 사유: 이전 알림의 8배는 zHBM의 '성능 8배'를 HBM4 가격배수로 잘못 읽은 파싱 오류였습니다.")
    lines.append("• 구분: HBM3E 대비 제시·협상가격과 실제 고객 체결가격·LTA 가격을 절대 같은 값으로 취급하지 않습니다.")
    if ch.get("reasons"):
        lines.append("• 이번 변화: " + html.escape(" · ".join(ch["reasons"])))
    lines += [
        f"• 감지 근거: {html.escape(e.get('source') or '미표시')} · {html.escape(e.get('published_at_kst') or '확인 불가')}",
        f"• {href(e.get('direct_link') or '', '원문')}",
    ]
    return lines


def _ops_page_text(e: dict, base_text: str) -> str:
    low = base_text.lower()
    if not any(k in low for k in ("yield", "수율", "unit price", "export price", "수출단가", "평균 수출단가")):
        return base_text
    url = e.get("direct_link") or ""
    if not url:
        return base_text
    try:
        raw = fetch(url, timeout=12).decode("utf-8", errors="ignore")
        page = clean(raw)
        if page:
            return (base_text + " " + page[:24000]).strip()
    except Exception:
        pass
    return base_text


def _ops_company_product(text: str) -> tuple[str, str]:
    low = text.lower()
    company = "industry"
    if "samsung" in low or "삼성전자" in text or "삼성" in text:
        company = "samsung"
    elif "sk hynix" in low or "sk하이닉스" in text or "하이닉스" in text:
        company = "skhynix"
    elif "micron" in low or "마이크론" in text:
        company = "micron"

    product = "hbm"
    for p, aliases in (
        ("hbm4e", ("hbm4e", "hbm 4e")),
        ("hbm4", ("hbm4", "hbm 4")),
        ("hbm3e", ("hbm3e", "hbm 3e")),
    ):
        if any(a in low for a in aliases):
            product = p
            break
    return company, product


def _extract_current_yield(text: str) -> float | None:
    patterns = [
        r"(?:최근|현재|now|currently)[^%]{0,80}?(?:수율|yield)[^%]{0,30}?([0-9]{1,3}(?:\.[0-9]+)?)\s*%",
        r"(?:수율|yield)[^%]{0,80}?(?:최근|현재|now|currently)[^%]{0,30}?([0-9]{1,3}(?:\.[0-9]+)?)\s*%",
        r"(?:수율|yield)[^%]{0,50}?([0-9]{1,3}(?:\.[0-9]+)?)\s*%\s*(?:까지|수준|대)",
        r"([0-9]{1,3}(?:\.[0-9]+)?)\s*%[^%]{0,35}?(?:수율|yield)",
    ]
    candidates: list[float] = []
    for pat in patterns:
        for m in re.finditer(pat, text, re.I):
            try:
                value = float(m.group(1))
                if 0 < value <= 100:
                    candidates.append(value)
            except Exception:
                pass
        if candidates:
            break
    if not candidates:
        return None
    return candidates[-1]


def extract_operating_observations(e: dict) -> list[dict]:
    base = clean(f"{e.get('title','')} {e.get('description','')} {e.get('source','')}")
    low = base.lower()
    if "hbm" not in low:
        return []
    text = _ops_page_text(e, base)
    observations: list[dict] = []

    if "yield" in text.lower() or "수율" in text:
        value = _extract_current_yield(text)
        if value is not None:
            company, product = _ops_company_product(text)
            if company != "industry":
                observations.append({
                    "key": f"{company}|{product}|yield",
                    "metric": "yield",
                    "company": company,
                    "product": product,
                    "value": value,
                    "unit": "pct",
                    "period": (e.get("published_at_kst") or "")[:7],
                    "source": e.get("source") or "",
                    "evidence": "official" if evidence_level(e) == "공식 확인" else "reported",
                    "published_at_kst": e.get("published_at_kst") or "",
                    "direct_link": e.get("direct_link") or "",
                    "title": e.get("title") or "",
                })

    if any(k in text.lower() for k in ("수출단가", "평균 수출단가", "unit price", "export price")):
        pub_year = ""
        try:
            pub_year = str(datetime.fromisoformat(e.get("published_at_kst") or "").year)
        except Exception:
            pub_year = str(datetime.now(ZoneInfo("Asia/Seoul")).year)

        pairs: dict[str, float] = {}
        for m in re.finditer(
            r"(?:(20\d{2})\s*년\s*)?([1-9]|1[0-2])\s*월[^\d$]{0,35}\$?\s*([0-9]+(?:\.[0-9]+)?)\s*달러",
            text,
            re.I,
        ):
            year = m.group(1) or pub_year
            month = int(m.group(2))
            value = float(m.group(3))
            if 0 < value < 10000:
                pairs[f"{year}-{month:02d}"] = value

        for period, value in sorted(pairs.items()):
            observations.append({
                "key": f"korea|hbm_related_export_unit_price|{period}",
                "metric": "export_unit_price",
                "company": "korea",
                "product": "hbm_related_proxy",
                "value": value,
                "unit": "usd",
                "period": period,
                "source": e.get("source") or "",
                "evidence": "official" if evidence_level(e) == "공식 확인" else "reported",
                "published_at_kst": e.get("published_at_kst") or "",
                "direct_link": e.get("direct_link") or "",
                "title": e.get("title") or "",
            })
    return observations


def operating_change_event(obs: dict, old: dict | None, reasons: list[str]) -> dict:
    if obs["metric"] == "yield":
        labels = {"samsung": "삼성전자", "skhynix": "SK하이닉스", "micron": "Micron"}
        product = obs["product"].upper()
        title = f"{labels.get(obs['company'], obs['company'])} {product} 수율 상태 변화"
        current = f"{obs['value']:.1f}%"
        previous = f"{float(old.get('value')):.1f}%" if old and old.get("value") is not None else ""
    else:
        title = "한국 HBM 관련 평균 수출단가 상태 변화"
        current = "${:.2f}".format(obs["value"])
        previous = "${:.2f}".format(float(old.get("value"))) if old and old.get("value") is not None else ""

    return {
        "id": "ops|" + obs["key"],
        "ops_observation": obs,
        "title": obs.get("title") or title,
        "description": "",
        "source": obs.get("source") or "출처 미표시",
        "published_at_kst": obs.get("published_at_kst") or "",
        "direct_link": obs.get("direct_link") or "",
        "rank": 96 if obs["metric"] == "yield" else 92,
        "ops_change": {
            "headline": title,
            "metric": obs["metric"],
            "period": obs["period"],
            "current": current,
            "previous": previous,
            "reasons": reasons,
        },
    }


def operating_event_summary(e: dict) -> list[str]:
    ch = e["ops_change"]
    lines = [
        f"<b>{html.escape(ch['headline'])}</b>",
        f"• 기준시점: <b>{html.escape(ch['period'])}</b>",
        f"• 현재값: <b>{html.escape(ch['current'])}</b>",
    ]
    if ch.get("previous"):
        lines.append(f"• 직전값: {html.escape(ch['previous'])}")
    if ch.get("reasons"):
        lines.append("• 변화: " + html.escape(" · ".join(ch["reasons"])))
    if ch["metric"] == "export_unit_price":
        lines.append("• 주의: 한국무역협회 HBM 관련 수출단가 대용지표이며 HBM 계약 평균판매단가와 1:1 동일하지 않습니다.")
    lines += [
        f"• 감지 근거: {html.escape(e.get('source') or '미표시')} · {html.escape(e.get('published_at_kst') or '확인 불가')}",
        f"• 근거 제목(한국어): {html.escape(korean_evidence_title(e, ch.get('headline') if e.get('ops_change') else ('HBM ' + ch.get('kind','') + ' 상태 변화' if e.get('share_change') else 'HBM 상태 변화')))} · {href(e.get('direct_link') or '', '원문')}",
    ]
    return lines


def event_summary(e: dict) -> list[str]:
    if e.get("samsung_hbm4_price_change"):
        return samsung_hbm4_price_event_summary(e)
    if e.get("capital_return_change"):
        return capital_return_event_summary(e)
    if e.get("broker_forecast_change"):
        return broker_forecast_event_summary(e)
    if e.get("ops_change"):
        return operating_event_summary(e)
    if e.get("share_change"):
        return share_event_summary(e)
    category, headline = classify_event(e)
    text = clean(f"{e.get('title','')} {e.get('description','')}")
    pcts = list(dict.fromkeys(re.findall(r"[+-]?\d+(?:\.\d+)?%", text)))[:4]
    multiples = list(dict.fromkeys(re.findall(r"\b\d+(?:\.\d+)?\s*(?:배|times?)\b", text, re.I)))[:3]
    low_text = text.lower()
    if "double" in low_text and "2배" not in multiples:
        multiples.insert(0, "2배")
    if "triple" in low_text and "3배" not in multiples:
        multiples.insert(0, "3배")
    multiples = multiples[:3]
    dollars = list(dict.fromkeys(re.findall(r"\$\s*\d+(?:\.\d+)?\s*(?:billion|million|B|M)\b", text, re.I)))[:2]
    nums = []
    if pcts:
        nums.append(" / ".join(pcts))
    if multiples:
        nums.append(" / ".join(multiples))
    if dollars:
        nums.append(" / ".join(dollars))
    lines = [
        f"<b>{headline}</b>",
        f"• 상태 판정: <b>{evidence_level(e)}</b>",
        f"• 변화 구분: {category}",
    ]
    if nums:
        lines.append(f"• 핵심 숫자: <b>{html.escape(' · '.join(nums))}</b>")
    lines += [
        f"• 감지 근거: {html.escape(e.get('source') or '미표시')} · {html.escape(e.get('published_at_kst') or '확인 불가')}",
        f"• 근거 제목(한국어): {html.escape(korean_evidence_title(e, headline))} · {href(e.get('direct_link') or '', '원문')}",
    ]
    return lines


def _official_poll_due(state: dict, now: datetime) -> tuple[bool, int]:
    target_month = _previous_month(now)
    health = state.get("official_source_health") or {}
    if health.get("status") in ("error", "partial", "validation_hold"):
        interval = OFFICIAL_ERROR_POLL_HOURS
    else:
        interval = (
            OFFICIAL_PUBLISHED_POLL_HOURS
            if state.get("last_successful_official_month") == target_month
            else OFFICIAL_UNPUBLISHED_POLL_HOURS
        )
    if (
        int(state.get("official_source_health_version") or 0) < OFFICIAL_SOURCE_HEALTH_VERSION
        or int(state.get("compare_version") or 0) < COMPARE_VERSION
        or int(state.get("export_alert_format_version") or 0) < EXPORT_ALERT_FORMAT_VERSION
    ):
        return True, interval
    raw = state.get("last_official_poll_attempt_kst") or ""
    try:
        last = datetime.fromisoformat(raw)
        if last.tzinfo is None:
            last = last.replace(tzinfo=ZoneInfo("Asia/Seoul"))
    except Exception:
        return True, interval
    return (now - last >= timedelta(hours=interval)), interval


def _dedupe_error_messages(errors: list[str]) -> list[str]:
    """Keep one copy of each identical source error without losing distinct causes."""
    return list(dict.fromkeys(errors))


def _official_error_classes(errors: list[str]) -> list[str]:
    classes = set()
    for error in errors:
        low = (error or "").lower()
        if "invalid:non_monthly_period" in low:
            classes.add("월별 기간 검증 보류")
        elif "kstat_reference_requested_month_unavailable" in low:
            classes.add("월별 기간 검증 보류")
        elif "kstat_reference_province_rows_missing" in low:
            classes.add("지역 HSK10 행 검증 보류")
        elif "connecttimeout" in low or "connection" in low:
            classes.add("연결시간초과")
        elif "readtimeout" in low or "timeout" in low or "오류 05" in low:
            classes.add("응답시간초과")
        elif "오류 22" in low or "오류 23" in low or "429" in low:
            classes.add("호출한도")
        elif "오류 20" in low or "오류 30" in low or "오류 31" in low or "키 미설정" in low:
            classes.add("인증·권한")
        elif "오류 10" in low:
            classes.add("요청값")
        elif "http " in low:
            classes.add("HTTP")
        elif "실패" in low or "오류" in low:
            classes.add("기타원천오류")
    return sorted(classes)


def _official_validation_hold_only(errors: list[str]) -> bool:
    classes = set(_official_error_classes(errors))
    return bool(classes) and classes.issubset({"월별 기간 검증 보류", "지역 HSK10 행 검증 보류"})


def _official_health_signature(target_month: str, errors: list[str]) -> str:
    payload = target_month + "|" + "|".join(_official_error_classes(errors))
    return hashlib.sha256(payload.encode()).hexdigest()[:16]


def _official_regional_source_mode(official: dict | None) -> str | None:
    if not isinstance(official, dict):
        return None
    current = (official.get("series") or {}).get(official.get("month"), {})
    sources = current.get("regional_sources") or {}
    items = [sources.get(role) for role in ("samsung_chungnam", "hynix_chungbuk")]
    if not all(isinstance(item, dict) and item.get("source") for item in items):
        return None
    names = [str(item["source"]) for item in items]
    if all("K-stat" in name for name in names):
        return "kstat_request_scoped"
    if len(set(names)) == 1 and "공공데이터포털" in names[0]:
        return "data_go_exact"
    return "mixed_or_unknown"


def build_official_source_health_alert(now: datetime, target_month: str, errors: list[str], *, recovered: bool = False, validation_recovered: bool = False, regional_source_mode: str | None = None) -> str:
    classes = _official_error_classes(errors)
    if recovered and regional_source_mode == "kstat_request_scoped":
        title = ("삼성·SK하이닉스 HBM 수출 원자료 월별 검증 보류 해소"
                 if validation_recovered else "삼성·SK하이닉스 HBM 수출 원자료 조회 복구")
        return "\n".join([
            f"✅ <b>{title}</b>",
            "━━━━━━━━━━━━━━━━",
            f"• 대상월: <b>{target_month[:4]}년 {int(target_month[4:])}월</b>",
            "• 전국 HSK10은 관세청 원자료로 확인했습니다.",
            "• 충남·충북은 K-stat(제공기관: 관세청) 시·도 HSK10 월별 USD 요청 범위로 확인했습니다.",
            "• 지역 응답 본문은 월·HS 코드를 회신하지 않아 요청 조건과 응답 지역 행이 식별 근거입니다.",
            f"• 복구 확인: {now.strftime('%Y-%m-%d %H:%M KST')}",
        ]) + "\n"
    if recovered and validation_recovered:
        if regional_source_mode == "kstat_request_scoped":
            recovery_detail = [
                "• 전국 HSK10은 관세청 원자료로 확인했습니다.",
                "• 충남·충북은 K-stat(제공기관: 관세청) 시·도 HSK10 월별 USD 조회 범위를 확인했습니다.",
                "• 지역 응답 본문은 월·HS 코드를 회신하지 않아 검증된 요청 조건과 지역 행으로 식별했습니다.",
            ]
        else:
            recovery_detail = [
                "• 공식 응답에서 대상월의 월별 기간 검증을 통과했습니다.",
                "• 수출 수치는 전국 HSK10·충남 HSK10·충북 HSK10을 모두 확인한 뒤에만 확정합니다.",
            ]
        return "\n".join([
            "✅ <b>삼성·SK하이닉스 HBM 수출 원자료 월별 검증 보류 해소</b>",
            "━━━━━━━━━━━━━━━━",
            f"• 대상월: <b>{target_month[:4]}년 {int(target_month[4:])}월</b>",
            *recovery_detail,
            f"• 확인: {now.strftime('%Y-%m-%d %H:%M KST')}",
        ]) + "\n"
    if recovered:
        return "\n".join([
            "✅ <b>삼성·SK하이닉스 HBM 수출 원자료 조회 복구</b>",
            "━━━━━━━━━━━━━━━━",
            f"• 대상월: <b>{target_month[:4]}년 {int(target_month[4:])}월</b>",
            "• 관세청·공공데이터 공식 조회 경로가 다시 정상 응답합니다.",
            "• 장애 중에는 과거 월 값을 최신값으로 재사용하지 않았습니다.",
            "• 새 확정월이 확인되면 월간 수출 비교 알림을 별도로 전송합니다.",
            f"• 복구 확인: {now.strftime('%Y-%m-%d %H:%M KST')}",
        ]) + "\n"
    validation_hold = _official_validation_hold_only(errors)
    error_texts = [str(error).lower() for error in errors]
    non_monthly_period = any("invalid:non_monthly_period" in error for error in error_texts)
    kstat_month_unavailable = any("kstat_reference_requested_month_unavailable" in error for error in error_texts)
    kstat_province_rows_missing = any("kstat_reference_province_rows_missing" in error for error in error_texts)
    err_text = " · ".join(classes) if classes else "원인 분류 미확정"
    headline = (
        "⚠️ <b>삼성·SK하이닉스 HBM 수출 원자료 월별 검증 보류</b>"
        if validation_hold
        else "⚠️ <b>삼성·SK하이닉스 HBM 수출 원자료 조회 장애</b>"
    )
    lines = [
        headline,
        "━━━━━━━━━━━━━━━━",
        f"• 대상월: <b>{target_month[:4]}년 {int(target_month[4:])}월</b>",
        f"• 상태: <b>{html.escape(err_text)}</b>",
    ]
    if non_monthly_period:
        lines.append("• 공식 API 응답은 받았지만 충남·충북 HSK10 응답에서 대상월의 월별 기간을 검증하지 못했습니다.")
    if kstat_month_unavailable:
        lines.append("• K-stat 공개 조회기간 선택 항목에 대상월이 없어 지역 HSK10 월별 원자료 검증을 보류했습니다.")
    if kstat_province_rows_missing:
        lines.append("• K-stat 응답에서 충남·충북 HSK10 시·도 행을 모두 확인하지 못해 월별 원자료 검증을 보류했습니다.")
    lines.extend([
        "• 전국 HSK10·충남 HSK10·충북 HSK10을 모두 공식 원자료로 잠그기 전에는 새 수치를 만들지 않습니다.",
        "• 이전 월 수치·지역 HS6·기사 숫자를 최신 확정치로 대체 사용하지 않습니다.",
        "• 기존 HBM 워크플로가 자동 재조회하며, 원자료 복구 또는 새 확정월 확인 시 다시 알립니다.",
        f"• 확인: {now.strftime('%Y-%m-%d %H:%M KST')}",
    ])
    return "\n".join(lines) + "\n"


def build_monthly(now: datetime, rate: float | None, fx_basis: str, official: dict, *, observed_at: datetime | None = None) -> str:
    """Render company-first HBM export direction, then the market/technical appendix.

    Chungnam/Chungbuk are exact official regional HSK10 proxy series, not company
    export ledgers. Icheon is never imputed, and different HS granularities are
    never summed.
    """
    month = official["month"]
    cur = official["series"][month]
    prev_m = _month_shift(month, -1)
    prev_q = _month_shift(month, -3)
    prev_y = _month_shift(month, -12)
    prev = official["series"].get(prev_m, {})
    qbase = official["series"].get(prev_q, {})
    ybase = official["series"].get(prev_y, {})
    target_month = _previous_month(now)

    nat_mom = _pct(cur["national_amount"], prev.get("national_amount"))
    nat_q = _pct(cur["national_amount"], qbase.get("national_amount"))
    nat_y = _pct(cur["national_amount"], ybase.get("national_amount"))
    nat_uv = _unit_value(cur["national_amount"], cur.get("national_weight"))
    nat_prev_uv = _unit_value(prev.get("national_amount"), prev.get("national_weight"))

    sam_mom = _pct(cur["samsung_region_amount"], prev.get("samsung_region_amount"))
    sam_q = _pct(cur["samsung_region_amount"], qbase.get("samsung_region_amount"))
    sam_y = _pct(cur["samsung_region_amount"], ybase.get("samsung_region_amount"))
    cb_mom = _pct(cur["hynix_chungbuk_amount"], prev.get("hynix_chungbuk_amount"))
    cb_q = _pct(cur["hynix_chungbuk_amount"], qbase.get("hynix_chungbuk_amount"))
    cb_y = _pct(cur["hynix_chungbuk_amount"], ybase.get("hynix_chungbuk_amount"))

    my_mom = _pct(cur.get("malaysia_amount"), prev.get("malaysia_amount"))
    my_q = _pct(cur.get("malaysia_amount"), qbase.get("malaysia_amount"))
    my_y = _pct(cur.get("malaysia_amount"), ybase.get("malaysia_amount"))
    my_uv = _unit_value(cur.get("malaysia_amount"), cur.get("malaysia_weight"))
    my_prev_uv = _unit_value(prev.get("malaysia_amount"), prev.get("malaysia_weight"))

    nat_krw = krw_large(cur["national_amount"], rate)
    sam_krw = krw_large(cur["samsung_region_amount"], rate)
    cb_krw = krw_large(cur["hynix_chungbuk_amount"], rate)
    my_krw = krw_large(cur.get("malaysia_amount"), rate) if cur.get("malaysia_amount") is not None else "확인 불가"

    sam_direction = _regional_direction(sam_mom, sam_q)
    hynix_direction = _regional_direction(cb_mom, cb_q)

    lines = [
        "🚨 <b>삼성전자 vs SK하이닉스 HBM 수출 방향</b>",
        "━━━━━━━━━━━━━━━━",
        f"📅 <b>공식 지역 원자료 최신 확인월: {month[:4]}년 {int(month[4:])}월</b>",
    ]
    if month != target_month:
        lines.append(
            f"• {target_month[:4]}년 {int(target_month[4:])}월 시도별 HSK10은 아직 이 감시 경로의 공식 최신월로 확인되지 않아 "
            f"<b>{month[:4]}년 {int(month[4:])}월</b>을 최신 기준으로 표시합니다."
        )
    lines += [
        "• 아래 금액은 <b>회사 직접 수출액이 아니라 관세청 지역 HSK10 대용지표</b>입니다.",
        "",
        "<b>[한눈에]</b>",
        f"🔵 <b>삼성전자 관련 지역(충남)</b>: <b>{sam_direction}</b> · 전월 {_fmt_pct(sam_mom)} · 3개월 전 대비 {_fmt_pct(sam_q)}",
        f"🟠 <b>SK하이닉스 관련 지역(충북)</b>: <b>{hynix_direction}</b> · 전월 {_fmt_pct(cb_mom)} · 3개월 전 대비 {_fmt_pct(cb_q)}",
        f"• 비교월: 전월 {prev_m[:4]}-{prev_m[4:]} → {month[:4]}-{month[4:]} / 3개월 전 {prev_q[:4]}-{prev_q[4:]} → {month[:4]}-{month[4:]}",
        "• 3개월 전 대비는 두 단일 월의 비교이며 3개월 누계가 아닙니다. 전월 ±20% 이상이고 3개월 전 대비도 같은 방향이면 강한 증감, 전월 ±5% 미만은 소폭 증감입니다.",
    ]
    regional_sources = cur.get("regional_sources") or {}
    regional_source_names = sorted({
        str(item.get("source") or "") for item in regional_sources.values()
        if isinstance(item, dict) and item.get("source")
    })
    if any("K-stat" in name for name in regional_source_names):
        lines.append("• 지역 HSK10 자료원: " + " / ".join(html.escape(name) for name in regional_source_names))
        lines.append("• K-stat 지역 응답은 대상월·HSK10·시·도·당월 USD 요청 조건으로 조회했고, 응답 본문은 월·HS 코드를 회신하지 않아 요청 범위가 식별 근거입니다.")
    elif regional_source_names:
        lines.append("• 지역 HSK10 자료원: " + " / ".join(html.escape(name) for name in regional_source_names))
    if official.get("icheon_public_available") and cur.get("icheon_amount") is not None:
        lines.append("⚪ <b>SK하이닉스 이천</b>: 공개 보조치 확인 · 충북 HSK10과 코드 단위가 다르면 <b>합산하지 않습니다.</b>")
    else:
        lines.append("⚪ <b>SK하이닉스 이천</b>: 공개 HSK10 확인 불가 · <b>SK하이닉스 전체값으로 합산하지 않습니다.</b>")

    lines += [
        "",
        "🔵 <b>[삼성전자 방향 — 충남]</b>",
        f"• HSK10 <b>{official['region_hs']}</b>: <b>{_fmt_usd(cur['samsung_region_amount'])}({sam_krw})</b>",
        f"• 변화: 전월 <b>{_fmt_pct(sam_mom)}</b> · 3개월 전 대비 <b>{_fmt_pct(sam_q)}</b> · 전년동월 <b>{_fmt_pct(sam_y)}</b>",
        f"• 판정: <b>{sam_direction}</b>",
        "• 범위: 충남 전체의 해당 품목 수출이며 특정 회사로 분리되지 않습니다. <b>삼성전자 직접 수출액·HBM 매출·점유율로 치환하지 않습니다.</b>",
        "",
        "🟠 <b>[SK하이닉스 관련 지역 — 충북]</b>",
        f"• HSK10 <b>{official['region_hs']}</b>: <b>{_fmt_usd(cur['hynix_chungbuk_amount'])}({cb_krw})</b>",
        f"• 변화: 전월 <b>{_fmt_pct(cb_mom)}</b> · 3개월 전 대비 <b>{_fmt_pct(cb_q)}</b> · 전년동월 <b>{_fmt_pct(cb_y)}</b>",
        f"• 판정: <b>{hynix_direction}</b>",
        "• 범위: 충북 전체의 해당 품목 수출이며 청주시·특정 회사로 분리되지 않습니다. <b>SK하이닉스 전체 직접 수출액으로 치환하지 않습니다.</b>",
    ]

    if official.get("icheon_public_available") and cur.get("icheon_amount") is not None:
        lines += [
            f"• 이천 보조치(HS {official.get('icheon_hs', REGION_HS6)}): <b>{_fmt_usd(cur['icheon_amount'])}({krw_large(cur['icheon_amount'], rate)})</b>",
            "• 이천 보조치는 충북 HSK10과 코드 단위가 다르면 <b>병기만 하고 합산하지 않습니다.</b>",
        ]
    else:
        lines += [
            "• 이천: <b>공개 HSK10 확인 불가</b> — 0으로 두거나 충북 값에 추정 합산하지 않습니다.",
            "• K-stat은 2026-09-01부터 시·군·구 HSK 10단위 품목통계를 전체 비공개로 전환했습니다.",
        ]

    lines += [
        "",
        "<b>[핵심 판정]</b>",
        f"• 공개 지역 대용지표 기준: <b>삼성전자 방향은 {sam_direction.replace('▲ ', '').replace('▼ ', '').replace('→ ', '')}</b>, "
        f"<b>SK하이닉스 관련 충북 지역은 {hynix_direction.replace('▲ ', '').replace('▼ ', '').replace('→ ', '')}</b>입니다.",
        "• 다만 <b>이천 HSK10이 공개되지 않고 지역통계는 회사 직접 수출액이 아니므로</b> "
        "‘삼성전자 수출이 SK하이닉스보다 몇 배’ 또는 회사 점유율로 해석하지 않습니다.",
        "",
        "<<<TELEGRAM_MESSAGE_BREAK>>>",
        "",
        "📊 <b>HBM 수출 원자료 세부</b>",
        "━━━━━━━━━━━━━━━━",
        "<b>[1. 전국 HBM 포함 MCP]</b>",
        f"• HSK10 <b>{official['hs']}</b>: <b>{_fmt_usd(cur['national_amount'])}({nat_krw})</b>",
        f"• 변화: 전월 <b>{_fmt_pct(nat_mom)}</b> · 3개월 전 대비 <b>{_fmt_pct(nat_q)}</b> · 전년동월 <b>{_fmt_pct(nat_y)}</b>",
    ]
    if nat_uv is not None:
        nat_uv_krw = f"약 {nat_uv * rate:,.0f}원/kg" if rate else "원화 환산 확인 불가"
        lines.append(
            f"• 중량당 단가: <b>&#36;{nat_uv:,.0f}/kg({nat_uv_krw})</b> · 전월 <b>{_fmt_pct(_pct(nat_uv, nat_prev_uv))}</b>"
        )
    else:
        lines.append("• 중량당 단가: <b>관세청 중량값 확인 불가</b> — 추정하지 않음")
    lines += [
        "• 주의: 전국 HSK10 8542323000은 <b>HBM을 포함하는 MCP 통계</b>이며 HBM 전용 수출액은 아닙니다. 중량당 금액도 품목 구성에 영향을 받으므로 HBM 제품 판매단가(ASP)로 해석하지 않습니다.",
        "",
        "<b>[2. 말레이시아 HSK10 — 첨단패키징 보조축]</b>",
    ]
    if official.get("malaysia_public_available") and cur.get("malaysia_amount") is not None:
        lines += [
            f"• 한국→말레이시아 HSK10 <b>{official['hs']}</b>: <b>{_fmt_usd(cur.get('malaysia_amount'))}({my_krw})</b>",
            f"• 변화: 전월 <b>{_fmt_pct(my_mom)}</b> · 3개월 전 대비 <b>{_fmt_pct(my_q)}</b> · 전년동월 <b>{_fmt_pct(my_y)}</b>",
        ]
        if my_uv is not None:
            my_uv_krw = f"약 {my_uv * rate:,.0f}원/kg" if rate else "원화 환산 확인 불가"
            lines.append(f"• 중량당 단가: <b>&#36;{my_uv:,.0f}/kg({my_uv_krw})</b> · 전월 <b>{_fmt_pct(_pct(my_uv, my_prev_uv))}</b>")
        else:
            lines.append("• 중량당 단가: <b>확인 불가</b> — 추정하지 않음")
        lines += [
            "• Intel Malaysia·EMIB 등 첨단패키징 이동을 보는 보조 신호이며, 전체가 HBM 또는 Intel 물량이라는 뜻은 아닙니다.",
            f"• Intel EMIB {href(INTEL_EMIB_OFFICIAL)} · Intel Malaysia {href(INTEL_MALAYSIA_OFFICIAL)}",
        ]
    else:
        lines += [
            "• 관세청 국가별 HSK10 직접값을 확인하지 못했습니다. <b>0으로 처리하거나 추정하지 않습니다.</b>",
            "• Intel Malaysia·EMIB·HBM 관련 공식자료와 신뢰 보도를 보조 감시합니다.",
        ]

    lines += [
        "",
        "<b>[3. 회사별 정밀 비교 기준선]</b>",
        "• 과거 Bernstein 기준선(2026년 7월): 충남은 4월 대비 <b>+122%</b>, 충북+이천은 약 <b>-27%</b>.",
        "• 이 수치는 <b>과거 동일 리서치 기준선</b>으로만 보존하며 위 최신월 현재값으로 재사용하지 않습니다.",
        "",
        "<b>[다음 알림]</b>",
        "• 새 월 전국·충남·충북 HSK10이 공식 원자료로 모두 확인될 때",
        "• 충남·충북의 같은 품목 수출 방향이 반전하거나 같은 기준월 원값이 개정될 때",
        "• 이천 공개 가능 자료·회사별 직접자료·새 리서치가 확인될 때",
        "• 한국→말레이시아 HSK10 방향이 크게 바뀌거나 Intel Malaysia 첨단패키징 상태가 바뀔 때",
        "• 삼성·SK하이닉스 HBM 실제 매출·점유율·NVIDIA 공급물량이 새로 확인될 때",
        "",
        f"<b>환율</b>: {html.escape(fx_basis)}",
        f"<b>조회</b>: {(observed_at or now).strftime('%Y-%m-%d %H:%M KST')}",
        "<b>원문</b>: "
        + f"관세청 {href(official['source_url'])} · "
        + f"K-stat {href('https://stat.kita.net/')} · "
        + f"Counterpoint {href(COUNTERPOINT_HBM_SHARE)} · "
        + f"Bernstein {href(BERNSTEIN_EXPORT)} · "
        + f"한국 관세청 국가별 품목 API {href(official.get('malaysia_source_url') or 'https://www.data.go.kr/data/15100475/openapi.do')}",
    ]
    return "\n".join(lines) + "\n"



def select_send_events(events: list[dict], limit: int = 4) -> list[dict]:
    ordered = sorted(events, key=lambda x: x.get("published_at_kst") or "")
    price_priority = [e for e in ordered if e.get("samsung_hbm4_price_change")]
    others = [e for e in ordered if not e.get("samsung_hbm4_price_change")]
    chosen_price = price_priority[-1:] if price_priority else []
    remaining = max(0, int(limit) - len(chosen_price))
    return sorted(chosen_price + others[-remaining:], key=lambda x: x.get("published_at_kst") or "")


def build_event_alert(events: list[dict], now: datetime) -> str:
    selected = events[:4]
    price_events = [e for e in selected if e.get("samsung_hbm4_price_change")]
    hbm_events = [e for e in selected if not e.get("capital_return_change") and not e.get("samsung_hbm4_price_change")]
    capital_events = [e for e in selected if e.get("capital_return_change")]
    lines: list[str] = []
    if hbm_events:
        lines += ["🚨 <b>HBM 상태 변화</b>", "━━━━━━━━━━━━━━━━", f"<b>신규 변화 {len(hbm_events)}건</b> · {now.strftime('%Y-%m-%d %H:%M KST')}", ""]
        for i, e in enumerate(hbm_events, 1):
            lines.append(f"<b>{i}.</b>")
            lines.extend(event_summary(e))
            if i < len(hbm_events):
                lines.append("")
    if price_events:
        if lines:
            lines += ["", "<<<TELEGRAM_MESSAGE_BREAK>>>", ""]
        lines += ["💵 <b>삼성 HBM4 2027 계약가격 감시</b>", "━━━━━━━━━━━━━━━━", f"<b>신규 변화 {len(price_events)}건</b> · {now.strftime('%Y-%m-%d %H:%M KST')}", ""]
        for i, e in enumerate(price_events, 1):
            lines.append(f"<b>{i}.</b>")
            lines.extend(event_summary(e))
            if i < len(price_events):
                lines.append("")
    if capital_events:
        if lines:
            lines += ["", "<<<TELEGRAM_MESSAGE_BREAK>>>", ""]
        lines += ["💰 <b>삼성전자 주주환원·FCF 변화</b>", "━━━━━━━━━━━━━━━━", f"<b>신규 변화 {len(capital_events)}건</b> · {now.strftime('%Y-%m-%d %H:%M KST')}", ""]
        for i, e in enumerate(capital_events, 1):
            lines.append(f"<b>{i}.</b>")
            lines.extend(event_summary(e))
            if i < len(capital_events):
                lines.append("")
    return "\n".join(lines).strip() + "\n"


def main() -> None:
    global _TRADE_EVIDENCE, _SIDO_SOURCE_RESULT
    try:
        _main()
    finally:
        _TRADE_EVIDENCE = None
        _SIDO_SOURCE_RESULT = None


def _main() -> None:
    now = datetime.now(ZoneInfo("Asia/Seoul"))
    _start_trade_evidence()
    state = load_state()
    seen = set(state.get("seen_ids") or [])
    month_key = now.strftime("%Y-%m")

    events = read_events()
    cutoff = now - timedelta(hours=FRESH_HOURS)
    topic_states = dict(state.get("topic_states") or {})

    share_forecasts = dict(state.get("hbm_share_forecasts") or {})
    share_actuals = dict(state.get("hbm_share_actuals") or {})
    broker_forecasts = dict(state.get("hbm_broker_forecasts") or {})
    samsung_hbm4_price_state = dict(state.get("samsung_hbm4_price_outlook") or {})
    capital_return_state = dict(state.get("capital_return_outlook") or {})
    ops_metrics = dict(state.get("hbm_ops_metrics") or {})
    export_unit_prices = dict(state.get("hbm_export_unit_prices") or {})

    if int(state.get("ops_track_version") or 0) < OPS_TRACK_VERSION:
        for key, value in OPS_BASELINES.items():
            ops_metrics.setdefault(key, dict(value))
        for period, value in EXPORT_UNIT_PRICE_BASELINES.items():
            export_unit_prices.setdefault(period, {
                "value": value,
                "source": "한국무역협회 인용 공개자료 기준선",
                "evidence": "reported",
                "observed_at": "baseline",
            })
        state["ops_track_version"] = OPS_TRACK_VERSION

    if int(state.get("broker_forecast_track_version") or 0) < BROKER_FORECAST_TRACK_VERSION:
        for key, values in BROKER_FORECAST_BASELINES.items():
            current = broker_forecasts.setdefault(key, {})
            for field, value in values.items():
                current.setdefault(field, value)
        state["broker_forecast_track_version"] = BROKER_FORECAST_TRACK_VERSION

    legacy_price_track_version = int(state.get("samsung_hbm4_price_track_version") or 0)
    legacy_bad_price_multiple = (
        samsung_hbm4_price_state.get("price_multiple_vs_hbm3e")
        if samsung_hbm4_price_state.get("price_multiple_vs_hbm3e") is not None
        else samsung_hbm4_price_state.get("price_multiple_vs_2026")
    )
    legacy_price_title = samsung_hbm4_price_state.get("title") or ""
    price_parser_correction_due = bool(
        legacy_price_track_version < SAMSUNG_HBM4_PRICE_TRACK_VERSION
        and legacy_bad_price_multiple is not None
        and float(legacy_bad_price_multiple) >= 5.0
        and ("최고성능 HBM4 자신감" in legacy_price_title or "가격 프리미엄" in legacy_price_title)
    )
    if legacy_price_track_version < SAMSUNG_HBM4_PRICE_TRACK_VERSION:
        seeded_price = dict(SAMSUNG_HBM4_PRICE_BASELINE)
        old_stage = samsung_hbm4_price_state.get("contract_stage")
        stage_rank = {"headline_reported": 0, "proposed": 1, "negotiating": 2, "final_stage": 3, "agreed": 4, "contract_signed": 5}
        if old_stage and stage_rank.get(old_stage, -1) > stage_rank.get(seeded_price["contract_stage"], -1):
            seeded_price["contract_stage"] = old_stage
        if samsung_hbm4_price_state.get("usd_per_gb") not in (None, ""):
            seeded_price["usd_per_gb"] = samsung_hbm4_price_state["usd_per_gb"]
        samsung_hbm4_price_state = seeded_price
        state["samsung_hbm4_price_track_version"] = SAMSUNG_HBM4_PRICE_TRACK_VERSION

    if int(state.get("capital_return_track_version") or 0) < CAPITAL_RETURN_TRACK_VERSION:
        seeded_capital = dict(CAPITAL_RETURN_BASELINE)
        seeded_capital.update({k: v for k, v in capital_return_state.items() if v not in (None, "")})
        capital_return_state = seeded_capital
        state["capital_return_track_version"] = CAPITAL_RETURN_TRACK_VERSION

    if int(state.get("share_track_version") or 0) < SHARE_TRACK_VERSION:
        for key, values in SHARE_FORECAST_BASELINES.items():
            share_forecasts.setdefault(key, {
                "values": {k: v for k, v in values.items() if k in ("skhynix", "samsung", "micron")},
                "source": values.get("source") or "baseline",
                "observed_at": "baseline",
            })
        for key, values in SHARE_ACTUAL_BASELINES.items():
            share_actuals.setdefault(key, {
                "values": {k: v for k, v in values.items() if k in ("skhynix", "samsung", "micron")},
                "source": values.get("source") or "baseline",
                "observed_at": "baseline",
            })
        state["share_track_version"] = SHARE_TRACK_VERSION

    # Parse share observations before generic topic-state handling. A structured
    # share item is removed from generic article-state logic so the same source
    # cannot create both a forecast alert and a generic "market share" alert.
    structured_share_event_ids = set()
    latest_share_obs: dict[str, dict] = {}
    for e in events:
        try:
            dt = datetime.fromisoformat(e.get("published_at_kst") or "")
        except Exception:
            continue
        if not (cutoff <= dt <= now + timedelta(minutes=10)):
            continue
        observations = extract_share_observations(e)
        if observations:
            structured_share_event_ids.add(e.get("id") or "")
        for obs in observations:
            old = latest_share_obs.get(obs["key"])
            if old is None or obs.get("published_at_kst", "") > old.get("published_at_kst", ""):
                latest_share_obs[obs["key"]] = obs

    share_alert_events: list[dict] = []
    for key, obs in latest_share_obs.items():
        store = share_actuals if obs["kind"] == "actual" else share_forecasts
        old = store.get(key)
        normalized = {
            "values": obs["values"],
            "source": obs.get("source") or "",
            "observed_at": obs.get("published_at_kst") or "",
            "title": obs.get("title") or "",
            "direct_link": obs.get("direct_link") or "",
        }

        if old:
            material, reasons = _share_material_change(old, obs)
            if material:
                share_alert_events.append(share_change_event(obs, old, reasons))
            else:
                store[key] = normalized
            continue

        if obs["kind"] == "actual":
            share_alert_events.append(share_change_event(obs, None, ["새 실제 점유율 기간"]))
            continue

        # A new forecast horizon from an already-tracked institution is itself
        # a material state expansion. A completely new institution only alerts
        # when it materially diverges from same-basis peers or reaches parity.
        same_house = any(
            k.startswith(obs["institution"] + "|" + obs["basis"] + "|")
            for k in share_forecasts
        )
        if same_house:
            share_alert_events.append(share_change_event(obs, None, ["신규 전망연도·기간"]))
            continue

        material, reasons = _share_cross_source_signal(share_forecasts, obs)
        if material:
            share_alert_events.append(share_change_event(obs, None, reasons))
        else:
            share_forecasts[key] = normalized

    # Structured broker forecasts: HBM blended ASP and stack-mix assumptions.
    structured_broker_event_ids = set()
    latest_broker_obs: dict[str, dict] = {}
    for e in events:
        try:
            dt = datetime.fromisoformat(e.get("published_at_kst") or "")
        except Exception:
            continue
        if not (cutoff <= dt <= now + timedelta(minutes=10)):
            continue
        observations = extract_broker_hbm_forecasts(e)
        if observations:
            structured_broker_event_ids.add(e.get("id") or "")
        for obs in observations:
            old = latest_broker_obs.get(obs["key"])
            if old is None or obs.get("published_at_kst", "") > old.get("published_at_kst", ""):
                latest_broker_obs[obs["key"]] = obs

    broker_alert_events: list[dict] = []
    for key, obs in latest_broker_obs.items():
        old = broker_forecasts.get(key)
        normalized = _broker_state_candidate(old, obs)
        if old:
            material, reasons = _broker_material_change(old, obs)
            if material:
                broker_alert_events.append(broker_forecast_change_event(obs, old, reasons))
            else:
                broker_forecasts[key] = normalized
            continue
        broker_alert_events.append(
            broker_forecast_change_event(obs, None, ["신규 증권사 HBM 평균판매단가·제품혼합 전망"])
        )

    structured_hbm4_price_event_ids = set()
    latest_hbm4_price_obs: dict | None = None
    for e in events:
        try:
            dt = datetime.fromisoformat(e.get("published_at_kst") or "")
        except Exception:
            continue
        if not (cutoff <= dt <= now + timedelta(minutes=10)):
            continue
        obs = extract_samsung_hbm4_price_observation(e)
        if not obs:
            continue
        structured_hbm4_price_event_ids.add(e.get("id") or "")
        if latest_hbm4_price_obs is None or obs.get("observed_at","") > latest_hbm4_price_obs.get("observed_at",""):
            latest_hbm4_price_obs = obs

    hbm4_price_alert_events: list[dict] = []
    if latest_hbm4_price_obs:
        hbm4_price_changes = _hbm4_price_changes(samsung_hbm4_price_state, latest_hbm4_price_obs)
        if hbm4_price_changes:
            hbm4_price_alert_events.append(samsung_hbm4_price_change_event(latest_hbm4_price_obs, samsung_hbm4_price_state, hbm4_price_changes))
        else:
            samsung_hbm4_price_state = _hbm4_price_candidate(samsung_hbm4_price_state, latest_hbm4_price_obs)

    if price_parser_correction_due:
        correction_obs = dict(SAMSUNG_HBM4_PRICE_BASELINE)
        correction_obs.update({
            "observed_at": datetime.now(ZoneInfo("Asia/Seoul")).isoformat(timespec="seconds"),
            "title": "삼성 HBM4 2027 계약가격 오탐 정정",
            "source": "매일경제 + 삼성전자 공식자료",
            "source_url": "https://www.mk.co.kr/news/business/12167424",
        })
        correction_reasons = [
            f"파싱 오탐 정정: {float(legacy_bad_price_multiple):.2f}배→HBM3E 대비 3.00배 이상",
            "zHBM 성능 8배 수치를 HBM4 가격배수로 잘못 분류한 오류 제거",
            "가격 비교 기준을 '2026년'이 아니라 '현재 주력 HBM3E 약 1.5달러/Gb'로 정정",
        ]
        hbm4_price_alert_events.append(
            samsung_hbm4_price_change_event(correction_obs, samsung_hbm4_price_state, correction_reasons, parser_correction=True)
        )
        samsung_hbm4_price_state = _hbm4_price_candidate(samsung_hbm4_price_state, correction_obs)

    structured_capital_event_ids = set()
    latest_capital_obs: dict | None = None
    for e in events:
        try:
            dt = datetime.fromisoformat(e.get("published_at_kst") or "")
        except Exception:
            continue
        if not (cutoff <= dt <= now + timedelta(minutes=10)):
            continue
        obs = extract_capital_return_observation(e)
        if not obs:
            continue
        structured_capital_event_ids.add(e.get("id") or "")
        if latest_capital_obs is None or obs.get("observed_at", "") > latest_capital_obs.get("observed_at", ""):
            latest_capital_obs = obs
    capital_alert_events: list[dict] = []
    if latest_capital_obs:
        capital_changes = _capital_return_changes(capital_return_state, latest_capital_obs)
        if capital_changes:
            capital_alert_events.append(capital_return_change_event(latest_capital_obs, capital_return_state, capital_changes))
        else:
            capital_return_state = _capital_return_candidate(capital_return_state, latest_capital_obs)

    # Structured operating metrics: yield and HBM-related export unit price.
    structured_ops_event_ids = set()
    latest_ops_obs: dict[str, dict] = {}
    for e in events:
        try:
            dt = datetime.fromisoformat(e.get("published_at_kst") or "")
        except Exception:
            continue
        if not (cutoff <= dt <= now + timedelta(minutes=10)):
            continue
        observations = extract_operating_observations(e)
        if observations:
            structured_ops_event_ids.add(e.get("id") or "")
        for obs in observations:
            old = latest_ops_obs.get(obs["key"])
            if old is None or obs.get("published_at_kst", "") > old.get("published_at_kst", ""):
                latest_ops_obs[obs["key"]] = obs

    ops_alert_events: list[dict] = []
    for key, obs in latest_ops_obs.items():
        if obs["metric"] == "yield":
            old = ops_metrics.get(key)
            if old is None:
                ops_alert_events.append(operating_change_event(obs, None, ["신규 수율 상태"]))
                continue
            delta = float(obs["value"]) - float(old.get("value"))
            evidence_upgrade = old.get("evidence") != "official" and obs.get("evidence") == "official"
            reasons = []
            if abs(delta) >= YIELD_ALERT_THRESHOLD_PP:
                reasons.append(f"수율 {delta:+.1f}%p")
            if evidence_upgrade:
                reasons.append("신뢰 보도→공식 확인")
            if reasons:
                ops_alert_events.append(operating_change_event(obs, old, reasons))
            else:
                ops_metrics[key] = {
                    "value": obs["value"],
                    "unit": obs["unit"],
                    "period": obs["period"],
                    "source": obs.get("source") or "",
                    "evidence": obs.get("evidence") or "reported",
                    "observed_at": obs.get("published_at_kst") or "",
                }
            continue

        period = obs["period"]
        old_same = export_unit_prices.get(period)
        if old_same:
            old_value = float(old_same.get("value"))
            pct = (float(obs["value"]) / old_value - 1.0) * 100.0 if old_value else 0.0
            evidence_upgrade = old_same.get("evidence") != "official" and obs.get("evidence") == "official"
            reasons = []
            if abs(pct) >= EXPORT_UNIT_PRICE_REVISION_PCT:
                reasons.append(f"동일월 정정 {pct:+.1f}%")
            if evidence_upgrade:
                reasons.append("신뢰 보도→공식 확인")
            if reasons:
                ops_alert_events.append(operating_change_event(obs, old_same, reasons))
            else:
                export_unit_prices[period] = {
                    "value": obs["value"],
                    "source": obs.get("source") or "",
                    "evidence": obs.get("evidence") or "reported",
                    "observed_at": obs.get("published_at_kst") or "",
                }
            continue

        previous_periods = sorted(p for p in export_unit_prices if p < period)
        if previous_periods:
            prev_period = previous_periods[-1]
            prev = export_unit_prices[prev_period]
            prev_value = float(prev.get("value"))
            pct = (float(obs["value"]) / prev_value - 1.0) * 100.0 if prev_value else 0.0
            direction = "상승" if pct > 0 else ("하락" if pct < 0 else "보합")
            reasons = [f"전월 {prev_period} 대비 {pct:+.1f}% · {direction}"]

            if len(previous_periods) >= 2:
                prev2_period = previous_periods[-2]
                prev2_value = float(export_unit_prices[prev2_period].get("value"))
                cur_value = float(obs["value"])
                if cur_value < prev_value < prev2_value:
                    reasons.append("2개월 연속 하락")
                elif cur_value > prev_value > prev2_value:
                    reasons.append("2개월 연속 상승")

            old_for_alert = {"value": prev_value}
            ops_alert_events.append(
                operating_change_event(
                    obs,
                    old_for_alert,
                    reasons,
                )
            )
        else:
            ops_alert_events.append(operating_change_event(obs, None, ["신규 월간 수출단가"]))
    
    # One-time migration: seed topic states only from articles that the old
    # watcher had already consumed. From this point onward article IDs are
    # audit metadata only and never determine whether an alert is new.
    if int(state.get("event_state_version") or 0) < EVENT_STATE_VERSION:
        migrated: dict[str, dict] = {}
        for e in events:
            if e.get("id") in structured_share_event_ids or e.get("id") in structured_broker_event_ids or e.get("id") in structured_hbm4_price_event_ids or e.get("id") in structured_capital_event_ids or e.get("id") in structured_ops_event_ids:
                continue
            if e.get("id") not in seen:
                continue
            topic_key, signature, readable = event_state_descriptor(e)
            if not topic_key or not signature:
                continue
            old = migrated.get(topic_key)
            if old is None or e.get("published_at_kst", "") > old.get("observed_at", ""):
                migrated[topic_key] = {
                    "signature": signature,
                    "observed_at": e.get("published_at_kst") or "",
                    "state": readable,
                }
        for key, value in migrated.items():
            topic_states.setdefault(key, value)
        state["event_state_version"] = EVENT_STATE_VERSION

    # Collapse all evidence into one latest/best candidate per normalized
    # topic. Multiple articles about the same fact therefore remain evidence,
    # not separate alerts.
    latest_by_topic: dict[str, dict] = {}
    fresh_new = []
    for e in events:
        if e.get("id") in structured_share_event_ids or e.get("id") in structured_broker_event_ids or e.get("id") in structured_hbm4_price_event_ids or e.get("id") in structured_capital_event_ids or e.get("id") in structured_ops_event_ids:
            continue
        try:
            dt = datetime.fromisoformat(e.get("published_at_kst") or "")
        except Exception:
            continue
        if not (cutoff <= dt <= now + timedelta(minutes=10)):
            continue
        topic_key, signature, readable = event_state_descriptor(e)
        if not topic_key or not signature:
            continue
        e["topic_key"] = topic_key
        e["state_signature"] = signature
        e["state_readable"] = readable
        old = latest_by_topic.get(topic_key)
        if old is None or e.get("published_at_kst", "") > old.get("published_at_kst", "") or (
            e.get("published_at_kst", "") == old.get("published_at_kst", "")
            and e.get("rank", 0) > old.get("rank", 0)
        ):
            latest_by_topic[topic_key] = e

    for topic_key, e in latest_by_topic.items():
        stored = topic_states.get(topic_key) or {}
        if stored.get("signature") != e.get("state_signature"):
            fresh_new.append(e)

    send_events = select_send_events(
        fresh_new + share_alert_events + broker_alert_events + hbm4_price_alert_events + capital_alert_events + ops_alert_events,
        limit=4,
    )

    rate, fx_basis = fx_quote()
    official_poll_attempted, official_poll_interval_hours = _official_poll_due(state, now)
    official_target_month = _previous_month(now)
    official_poll_started_at = official_poll_completed_at = now
    if now.day >= MONTHLY_DAY and official_poll_attempted:
        official_poll_started_at = datetime.now(ZoneInfo("Asia/Seoul"))
        official, official_errors = fetch_official_hbm_pack(now)
        official_poll_completed_at = datetime.now(ZoneInfo("Asia/Seoul"))
        official_errors = _dedupe_error_messages(official_errors)
        newest_confirmed = max(str(state.get(key) or "") for key in ("last_official_alert_month", "last_successful_official_month"))
        if official and official["month"] < newest_confirmed:
            official_errors = list(official_errors) + ["최신월 후퇴 검증 보류: 이미 확인한 월보다 이전 월만 조회됨"]
            official = None
    else:
        official, official_errors = None, []
    official_month = official.get("month") if official else ""
    current_malaysia_amount = (
        official.get("series", {}).get(official_month, {}).get("malaysia_amount")
        if official and official_month else None
    )
    current_malaysia_weight = (
        official.get("series", {}).get(official_month, {}).get("malaysia_weight")
        if official and official_month else None
    )
    previous_malaysia_amount = state.get("malaysia_hsk10_amount_usd")
    malaysia_revision_due = bool(
        official
        and state.get("malaysia_official_month") == official_month
        and previous_malaysia_amount not in (None, 0)
        and current_malaysia_amount is not None
        and abs(current_malaysia_amount / previous_malaysia_amount - 1.0) >= 0.10
    )
    previous_source_health = dict(state.get("official_source_health") or {})
    source_health_alert = ""
    source_health_state = previous_source_health
    if official_poll_attempted:
        publication_pending = bool(official is None and official_errors and all(str(e).startswith("공표 대기:") for e in official_errors))
        if publication_pending:
            source_health_state = {
                "version": OFFICIAL_SOURCE_HEALTH_VERSION, "status": "waiting_publication",
                "target_month": official_target_month, "last_checked_at_kst": official_poll_completed_at.isoformat(timespec="seconds"),
                "notes": official_errors,
            }
        elif official is None and official_errors:
            sig = _official_health_signature(official_target_month, official_errors)
            source_health_status = "validation_hold" if _official_validation_hold_only(official_errors) else "error"
            source_health_state = {
                "version": OFFICIAL_SOURCE_HEALTH_VERSION,
                "status": source_health_status,
                "target_month": official_target_month,
                "signature": sig,
                "classes": _official_error_classes(official_errors),
                "last_checked_at_kst": official_poll_completed_at.isoformat(timespec="seconds"),
                "first_seen_at_kst": (
                    previous_source_health.get("first_seen_at_kst")
                    if previous_source_health.get("signature") == sig
                    else official_poll_completed_at.isoformat(timespec="seconds")
                ),
            }
            if previous_source_health.get("signature") != sig or previous_source_health.get("status") not in ("error", "validation_hold"):
                source_health_alert = build_official_source_health_alert(
                    official_poll_completed_at, official_target_month, official_errors
                )
        elif official is not None:
            previous_health_status = previous_source_health.get("status")
            was_error = previous_health_status == "error"
            was_validation_hold = previous_health_status == "validation_hold"
            waiting_publication = official_month != official_target_month
            source_health_state = {
                "version": OFFICIAL_SOURCE_HEALTH_VERSION,
                "status": "waiting_publication" if waiting_publication else "partial" if official_errors else "ok",
                "target_month": official_target_month,
                "last_checked_at_kst": official_poll_completed_at.isoformat(timespec="seconds"),
                "selected_official_month": official_month,
            }
            if was_error and not official_errors:
                source_health_alert = build_official_source_health_alert(
                    official_poll_completed_at, official_target_month, [], recovered=True,
                    regional_source_mode=_official_regional_source_mode(official),
                )
            elif was_validation_hold and not official_errors and not waiting_publication:
                source_health_alert = build_official_source_health_alert(
                    official_poll_completed_at, official_target_month, [], recovered=True, validation_recovered=True,
                    regional_source_mode=_official_regional_source_mode(official),
                )
            elif (
                waiting_publication
                and now.day > OFFICIAL_PUBLICATION_EXPECTED_DAY
                and (
                    previous_source_health.get("status") != "waiting_publication"
                    or previous_source_health.get("target_month") != official_target_month
                )
            ):
                source_health_alert = "\n".join([
                    "⚠️ <b>삼성·SK하이닉스 HBM 수출 새 확정월 게시 지연</b>",
                    "━━━━━━━━━━━━━━━━",
                    f"• 대상월: <b>{official_target_month[:4]}년 {int(official_target_month[4:])}월</b>",
                    f"• 현재 공식 API 최신월: <b>{official_month[:4]}년 {int(official_month[4:])}월</b>",
                    "• 관세청 시도별 품목 통계는 통상 매월 15일경 전월 자료를 현행화합니다.",
                    "• 새 확정월이 게시되기 전까지 이전 월 값을 최신값으로 재사용하지 않습니다.",
                    f"• 확인: {official_poll_completed_at.strftime('%Y-%m-%d %H:%M KST')}",
                ]) + "\n"

    monthly_decision = official_monthly_decision(state, official)
    format_upgrade_due = monthly_decision["format_upgrade"]
    official_revision_due = monthly_decision["revision"]
    monthly_due = monthly_decision["due"] or malaysia_revision_due

    regional_source_correction_due = bool(
        official
        and int(state.get("compare_version") or 0) < COMPARE_VERSION
        and state.get("last_official_alert_month") == official_month
    )

    if monthly_due and official:
        monthly_text = build_monthly(now, rate, fx_basis, official, observed_at=official_poll_completed_at)
        if format_upgrade_due:
            monthly_text = "\n".join([
                "🛠 <b>수출 원자료 재검증·표시 기준 정정</b>",
                f"• <b>{official_month[:4]}년 {int(official_month[4:])}월</b>과 비교월의 원자료를 이번 실행에서 다시 조회했습니다.",
                "• 전월 소폭 증감·3개월 전 단월 비교·시도 범위를 명확히 표시합니다. 이전 본문을 재사용한 신규 관측이 아닙니다.",
                "",
            ]) + monthly_text
        if official_revision_due:
            monthly_text = "📌 <b>같은 기준월의 공식 수출 원자료·비교월 개정</b>\n• 직전 실제 발송의 날짜별 원값과 달라 다시 계산했습니다.\n\n" + monthly_text
        elif monthly_decision["availability"]:
            monthly_text = "📌 <b>같은 기준월의 미확인 원자료 추가 확인</b>\n• 직전 알림에서 확인되지 않았던 원값을 이번 실행에서 확인했습니다.\n\n" + monthly_text
        if regional_source_correction_due:
            monthly_text = "\n".join([
                "⚠️ <b>정정 — 삼성·SK하이닉스 지역 원자료 확인 방식</b>",
                "• 충남·충북은 K-stat(제공기관: 관세청)의 시·도 HSK10 월별 USD 요청 범위와 응답 지역 행으로 확인했습니다.",
                "• K-stat 응답 본문은 대상월과 HS 코드를 회신하지 않으므로 검증된 공개 요청 조건이 월·품목 식별 근거입니다.",
                "• 지역 응답 금액 크기로 환산계수를 추정하지 않으며, 아래 값은 각 월 원응답에서 다시 읽은 값입니다.",
                "",
            ]) + monthly_text
        if source_health_alert and previous_source_health.get("status") in ("error", "validation_hold"):
            monthly_text = source_health_alert + "\n<<<TELEGRAM_MESSAGE_BREAK>>>\n\n" + monthly_text
        ALERT.write_text(monthly_text, encoding="utf-8")
        state["last_monthly_digest"] = month_key
        state["last_official_alert_month"] = official_month
        state["compare_version"] = COMPARE_VERSION
        previous_values = state.get("last_official_notified_values") or state.get("last_official_alert_snapshot")
        state["last_official_alert_snapshot"] = monthly_decision["snapshot"]
        state["last_official_notified_values"] = _merge_notified_values(previous_values, monthly_decision["snapshot"])
        if regional_source_correction_due:
            corrections = list(state.get("state_corrections") or [])
            corrections.append({
                "type": "regional_export_source_scope",
                "from": "Data.go regional series with cross-source unit reconciliation",
                "to": "K-stat monthly SIDO HSK10 USD request-scoped series",
                "corrected_at_kst": now.isoformat(timespec="seconds"),
                "official_month": official_month,
                "identity_limit": "K-stat response body does not echo month or HS code",
            })
            state["state_corrections"] = corrections[-20:]
        # Do not consume pending topic-state changes behind a monthly alert.
        # They remain eligible on the next run.
    elif source_health_alert:
        text = source_health_alert
        if send_events:
            text += "\n<<<TELEGRAM_MESSAGE_BREAK>>>\n\n" + build_event_alert(send_events, now)
        ALERT.write_text(text, encoding="utf-8")
    elif send_events:
        ALERT.write_text(build_event_alert(send_events, now), encoding="utf-8")
        for e in send_events:
            if e.get("samsung_hbm4_price_change"):
                samsung_hbm4_price_state = dict(e.get("samsung_hbm4_price_state_candidate") or samsung_hbm4_price_state)
                continue
            if e.get("capital_return_change"):
                capital_return_state = dict(e.get("capital_return_state_candidate") or capital_return_state)
                continue
            if e.get("broker_forecast_change"):
                obs = e.get("broker_observation") or {}
                if obs:
                    broker_forecasts[obs["key"]] = dict(e.get("broker_state_candidate") or _broker_state_candidate(broker_forecasts.get(obs["key"]), obs))
                continue
            if e.get("ops_change"):
                obs = e.get("ops_observation") or {}
                if obs:
                    if obs.get("metric") == "yield":
                        ops_metrics[obs["key"]] = {
                            "value": obs.get("value"),
                            "unit": obs.get("unit"),
                            "period": obs.get("period"),
                            "source": obs.get("source") or "",
                            "evidence": obs.get("evidence") or "reported",
                            "observed_at": obs.get("published_at_kst") or "",
                        }
                    elif obs.get("metric") == "export_unit_price":
                        export_unit_prices[obs["period"]] = {
                            "value": obs.get("value"),
                            "source": obs.get("source") or "",
                            "evidence": obs.get("evidence") or "reported",
                            "observed_at": obs.get("published_at_kst") or "",
                        }
                continue
            if e.get("share_change"):
                obs = e.get("share_observation") or {}
                if obs:
                    store = share_actuals if obs.get("kind") == "actual" else share_forecasts
                    store[obs["key"]] = {
                        "values": obs.get("values") or {},
                        "source": obs.get("source") or "",
                        "observed_at": obs.get("published_at_kst") or "",
                        "title": obs.get("title") or "",
                        "direct_link": obs.get("direct_link") or "",
                    }
                continue
            topic_states[e["topic_key"]] = {
                "signature": e["state_signature"],
                "observed_at": e.get("published_at_kst") or "",
                "state": e.get("state_readable") or "",
            }
    elif ALERT.exists():
        ALERT.unlink()

    # Article IDs are retained only for audit/migration history.
    seen.update(e["id"] for e in events)

    state.update({
        "updated_at_kst": now.isoformat(timespec="seconds"),
        "seen_ids": sorted(seen)[-1500:],
        "event_state_version": EVENT_STATE_VERSION,
        "topic_states": topic_states,
        "share_track_version": SHARE_TRACK_VERSION,
        "broker_forecast_track_version": BROKER_FORECAST_TRACK_VERSION,
        "samsung_hbm4_price_track_version": SAMSUNG_HBM4_PRICE_TRACK_VERSION,
        "samsung_hbm4_price_outlook": samsung_hbm4_price_state,
        "capital_return_track_version": CAPITAL_RETURN_TRACK_VERSION,
        "capital_return_outlook": capital_return_state,
        "ops_track_version": OPS_TRACK_VERSION,
        "hbm_ops_metrics": ops_metrics,
        "hbm_export_unit_prices": export_unit_prices,
        "last_ops_observation_count": len(latest_ops_obs),
        "last_ops_alert_count": len([e for e in send_events if e.get("ops_change")]),
        "hbm_share_forecasts": share_forecasts,
        "hbm_share_actuals": share_actuals,
        "hbm_broker_forecasts": broker_forecasts,
        "last_broker_forecast_observation_count": len(latest_broker_obs),
        "last_broker_forecast_alert_count": len([e for e in send_events if e.get("broker_forecast_change")]),
        "last_samsung_hbm4_price_observation_count": 1 if latest_hbm4_price_obs else 0,
        "last_samsung_hbm4_price_alert_count": len([e for e in send_events if e.get("samsung_hbm4_price_change")]),
        "last_capital_return_observation_count": 1 if latest_capital_obs else 0,
        "last_capital_return_alert_count": len([e for e in send_events if e.get("capital_return_change")]),
        "last_share_observation_count": len(latest_share_obs),
        "last_share_alert_count": len([e for e in send_events if e.get("share_change")]),
        "last_event_count": len(events),
        "last_fresh_new_count": len(fresh_new),
        "last_send_event_count": len(send_events),
        "monthly_due": monthly_due,
        "official_revision_due": official_revision_due,
        "official_observed_this_run": bool(official),
        "export_alert_format_version": (
            EXPORT_ALERT_FORMAT_VERSION
            if monthly_due and official
            else int(state.get("export_alert_format_version") or 0)
        ),
        "official_month": official_month if official else state.get("official_month", ""),
        "official_data_ok": bool(official) if official_poll_attempted else state.get("official_data_ok", False),
        "official_source_health": source_health_state,
        "official_source_health_version": OFFICIAL_SOURCE_HEALTH_VERSION,
        "official_poll_interval_hours": official_poll_interval_hours,
        "last_official_poll_attempt_kst": (
            official_poll_started_at.isoformat(timespec="seconds")
            if official_poll_attempted
            else state.get("last_official_poll_attempt_kst", "")
        ),
        "official_api_key_configured": bool(DATA_GO_KEY),
        "official_api_used": (
            bool(official and official.get("official_api_used"))
            if official_poll_attempted
            else state.get("official_api_used", False)
        ),
        "malaysia_official_month": official_month if official else state.get("malaysia_official_month", ""),
        "malaysia_hsk10_amount_usd": current_malaysia_amount if official_poll_attempted else state.get("malaysia_hsk10_amount_usd"),
        "malaysia_hsk10_weight_kg": current_malaysia_weight if official_poll_attempted else state.get("malaysia_hsk10_weight_kg"),
        "malaysia_public_available": bool(official and official.get("malaysia_public_available")) if official_poll_attempted else state.get("malaysia_public_available", False),
        "malaysia_revision_due": malaysia_revision_due,
        "official_errors": [re.sub(r"serviceKey=[^&\s]+", "serviceKey=<redacted>", str(x)) for x in official_errors[-8:]],
        "official_availability_notes": (
            (official.get("availability_notes") or [])[-8:]
            if official_poll_attempted and official
            else state.get("official_availability_notes", [])
        ),
        "optional_source_errors": (
            [re.sub(r"serviceKey=[^&\s]+", "serviceKey=<redacted>", str(x)) for x in (official.get("optional_errors") or [])[-8:]]
            if official_poll_attempted and official
            else state.get("optional_source_errors", [])
        ),
    })
    if official:
        state["last_successful_official_month"] = official_month
        state["last_successful_official_at_kst"] = official_poll_completed_at.isoformat(timespec="seconds")
    evidence_ref = _write_trade_validation(now, official, official_errors, monthly_due, rate, fx_basis, observed_at=official_poll_completed_at)
    if monthly_due:
        state["official_export_evidence"] = evidence_ref
    save_state(state)

    STATUS.write_text(
        "# Samsung HBM Watch\n"
        f"- checked_at_kst: {now.isoformat(timespec='seconds')}\n"
        f"- events: {len(events)}\n"
        f"- event_state_version: {EVENT_STATE_VERSION}\n"
        f"- topic_state_count: {len(topic_states)}\n"
        f"- share_track_version: {SHARE_TRACK_VERSION}\n"
        f"- broker_forecast_track_version: {BROKER_FORECAST_TRACK_VERSION}\n"
        f"- samsung_hbm4_price_track_version: {SAMSUNG_HBM4_PRICE_TRACK_VERSION}\n"
        f"- capital_return_track_version: {CAPITAL_RETURN_TRACK_VERSION}\n"
        f"- ops_track_version: {OPS_TRACK_VERSION}\n"
        f"- ops_metric_state_count: {len(ops_metrics)}\n"
        f"- export_unit_price_months: {len(export_unit_prices)}\n"
        f"- ops_observations: {len(latest_ops_obs)}\n"
        f"- ops_alerts: {len([e for e in send_events if e.get('ops_change')])}\n"
        f"- share_forecast_state_count: {len(share_forecasts)}\n"
        f"- share_actual_state_count: {len(share_actuals)}\n"
        f"- broker_forecast_state_count: {len(broker_forecasts)}\n"
        f"- broker_forecast_observations: {len(latest_broker_obs)}\n"
        f"- broker_forecast_alerts: {len([e for e in send_events if e.get('broker_forecast_change')])}\n"
        f"- samsung_hbm4_price_observations: {1 if latest_hbm4_price_obs else 0}\n"
        f"- samsung_hbm4_price_alerts: {len([e for e in send_events if e.get('samsung_hbm4_price_change')])}\n"
        f"- capital_return_observations: {1 if latest_capital_obs else 0}\n"
        f"- capital_return_alerts: {len([e for e in send_events if e.get('capital_return_change')])}\n"
        f"- share_observations: {len(latest_share_obs)}\n"
        f"- share_alerts: {len([e for e in send_events if e.get('share_change')])}\n"
        f"- fresh_new: {len(fresh_new)}\n"
        f"- monthly_due: {str(monthly_due).lower()}\n"
        f"- official_poll_attempted: {str(official_poll_attempted).lower()}\n"
        f"- official_poll_interval_hours: {official_poll_interval_hours}\n"
        f"- official_target_month: {official_target_month}\n"
        f"- official_source_health: {source_health_state.get('status', 'unknown')}\n"
        f"- official_month: {official_month or state.get('official_month') or 'none'}\n"
        f"- official_observation_this_run: {'fresh_verified' if official else 'held' if official_poll_attempted else 'not_polled'}\n"
        f"- last_successful_official_month: {state.get('last_successful_official_month') or 'none'}\n"
        f"- last_successful_official_at_kst: {state.get('last_successful_official_at_kst') or 'none'}\n"
        f"- official_data_ok: {str(bool(state.get('official_data_ok'))).lower()}\n"
        f"- official_api_key_configured: {str(bool(DATA_GO_KEY)).lower()}\n"
        f"- official_api_used_this_run: {str(bool(official and official.get('official_api_used'))).lower()}\n"
        f"- malaysia_public_available_last_observation: {str(bool(state.get('malaysia_public_available'))).lower()}\n"
        f"- malaysia_hsk10_amount_usd_last_observation: {state.get('malaysia_hsk10_amount_usd')}\n"
        f"- malaysia_hsk10_weight_kg_last_observation: {state.get('malaysia_hsk10_weight_kg')}\n"
        f"- malaysia_revision_due: {str(malaysia_revision_due).lower()}\n"
        f"- official_errors: {len(official_errors)}\n"
        f"- official_availability_notes: {len(official.get('availability_notes') or []) if official else 0}\n"
        f"- optional_source_errors: {len(official.get('optional_errors') or []) if official else 0}\n"
        f"- alert_generated: {str(monthly_due or bool(send_events) or bool(source_health_alert)).lower()}\n",
        encoding="utf-8",
    )


if __name__ == "__main__":
    main()
