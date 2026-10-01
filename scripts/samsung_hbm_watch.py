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
import time
from datetime import datetime, timedelta, timezone
from email.utils import parsedate_to_datetime
from zoneinfo import ZoneInfo

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
MONTHLY_DAY = 15
COMPARE_VERSION = 4
EVENT_STATE_VERSION = 2
SHARE_TRACK_VERSION = 1
BROKER_FORECAST_TRACK_VERSION = 3
CAPITAL_RETURN_TRACK_VERSION = 1
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
    "hankyung", "한국경제",
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
        return float(s)
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


def _normalize_export_usd(value: float | None) -> float | None:
    if value is None:
        return None
    return value * 1000.0 if 0 <= value < 100_000_000 else value



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
        )
    )


def _request_with_retry(method: str, url: str, *, params=None, data=None, headers=None, attempts: int = 2):
    last_exc = None
    for attempt in range(1, attempts + 1):
        try:
            return requests.request(
                method,
                url,
                params=params,
                data=data,
                headers=headers,
                timeout=(5, 12),
            )
        except (requests.Timeout, requests.ConnectionError) as exc:
            last_exc = exc
            if attempt < attempts:
                time.sleep(1.5 * attempt)
        except Exception as exc:
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
        root = ET.fromstring(r.content)
    except Exception as exc:
        return None, _safe_error("공공데이터포털 전국 API 실패", exc)
    code = root.findtext(".//resultCode")
    msg = root.findtext(".//resultMsg") or ""
    if code != "00":
        return None, f"공공데이터포털 전국 API 오류 {code}: {msg}"

    for item in root.findall(".//item"):
        year = re.sub(r"[^0-9]", "", _xml_text(item, "year") or "")
        hs = str(_xml_text(item, "hsCode", "hsCd") or "").replace(".", "")
        if year.startswith(month) and hs == HBM_HSK10:
            amt = _number(_xml_text(item, "expDlr"))
            wgt = _number(_xml_text(item, "expWgt"))
            if amt is None:
                continue
            return {
                "month": month,
                "amount_usd": amt,
                "weight_kg": wgt,
                "hs": HBM_HSK10,
                "source": "공공데이터포털 관세청 품목별 수출입실적 API",
                "api": True,
            }, ""
    return None, f"공공데이터포털 전국 API {month} HSK {HBM_HSK10} 데이터 없음"


def fetch_data_go_sido_month(month: str, sido_cd: str) -> tuple[dict | None, str]:
    if not DATA_GO_KEY:
        return None, "공공데이터포털 API 키 미설정"
    params = {
        "serviceKey": DATA_GO_KEY,
        "strtYymm": month,
        "endYymm": month,
        "sidoCd": sido_cd,
        "hsSgn": HBM_HSK10,
    }
    try:
        r = _request_with_retry("GET", DATA_GO_SIDO_ITEM_URL, params=params)
        root = ET.fromstring(r.content)
    except Exception as exc:
        return None, _safe_error("공공데이터포털 시도 API 실패", exc)
    code = root.findtext(".//resultCode")
    msg = root.findtext(".//resultMsg") or ""
    if code != "00":
        return None, f"공공데이터포털 시도 API 오류 {code}: {msg}"

    for item in root.findall(".//item"):
        hs = str(_xml_text(item, "hsSgn", "hsCd", "hsCode") or "").replace(".", "")
        period = re.sub(r"[^0-9]", "", _xml_text(item, "priodTitle", "year") or "")
        if hs and hs != HBM_HSK10:
            continue
        if period and not period.startswith(month):
            continue
        amt = _number(_xml_text(item, "expUsdAmt", "expDlr"))
        if amt is None:
            continue
        return {
            "month": month,
            "amount_usd": amt,
            "weight_kg": None,
            "hs": HBM_HSK10,
            "source": "공공데이터포털 관세청 시도별 품목별 수출입실적 API",
            "api": True,
        }, ""
    return None, f"공공데이터포털 시도 API {sido_cd} {month} HSK {HBM_HSK10} 데이터 없음"


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
        root = ET.fromstring(r.content)
    except Exception as exc:
        return None, _safe_error(f"공공데이터포털 국가별 품목 API {cnty_cd} 실패", exc)
    code = _xml_text(root, "resultCode")
    msg = _xml_text(root, "resultMsg", "errMsg", "returnAuthMsg") or ""
    items = _xml_items(root)
    # Some Data.go gateways wrap the payload with XML namespaces or omit the
    # normal resultCode while still returning valid item rows. Prefer actual
    # rows over a missing header, but never accept a non-00 explicit error.
    if code not in (None, "", "00"):
        return None, f"공공데이터포털 국가별 품목 API {cnty_cd} 오류 {code}: {msg}"
    if not items and code != "00":
        preview = clean(r.text)[:180] if getattr(r, "text", "") else "empty"
        return None, f"공공데이터포털 국가별 품목 API {cnty_cd} 응답형식 확인 필요: {preview}"

    for item in items:
        period = re.sub(r"[^0-9]", "", _xml_text(item, "year") or "")
        hs = str(_xml_text(item, "hsCd", "hsCode") or "").replace(".", "")
        country = str(_xml_text(item, "statCd") or "").strip().upper()
        if period and not period.startswith(month):
            continue
        if hs and hs != HBM_HSK10:
            continue
        if country and country != cnty_cd.upper():
            continue
        amt = _number(_xml_text(item, "expDlr"))
        wgt = _number(_xml_text(item, "expWgt"))
        if amt is None:
            continue
        return {
            "month": month,
            "country_code": cnty_cd.upper(),
            "country_name": _xml_text(item, "statCdCntnKor1") or "말레이시아",
            "amount_usd": amt,
            "weight_kg": wgt,
            "hs": HBM_HSK10,
            "source": "공공데이터포털 관세청 품목별 국가별 수출입실적 API",
            "api": True,
        }, ""
    return None, f"공공데이터포털 국가별 품목 API {cnty_cd} {month} HSK {HBM_HSK10} 데이터 없음"


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
        r = _request_with_retry("POST", KCS_ITEM_URL, headers=headers, data=params)
        if r.status_code != 200:
            return None, f"전국 {month} KCS HTTP {r.status_code}"
        data = r.json()
    except Exception as exc:
        return None, _safe_error(f"전국 {month} KCS 조회 실패", exc)

    items = data.get("items") or []
    target = None
    for row in items:
        if str(row.get("priodTitle") or "") == "총계":
            continue
        hs = str(row.get("hsSgn") or "").replace(".", "")
        period = re.sub(r"[^0-9]", "", str(row.get("priodTitle") or ""))
        if hs == HBM_HSK10 and month in period:
            target = row
            break
    if target is None:
        return None, f"전국 {month} HSK {HBM_HSK10} 미검출: count={data.get('count')} items={len(items)}"

    amt = _normalize_export_usd(_number(target.get("expUsdAmt")))
    weight = _number(target.get("expTtwg"))
    if amt is None:
        return None, f"전국 {month} 수출금액 숫자 변환 실패"
    return {
        "month": month,
        "amount_usd": amt,
        "weight_kg": weight,
        "hs": HBM_HSK10,
        "source": "관세청 수출입무역통계",
    }, ""


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
            r = _request_with_retry("POST", KCS_REGION_URL, headers=headers, data=params)
            if r.status_code != 200:
                continue
            data = r.json()
        except Exception as exc:
            return None, _safe_error(f"{region['name']} {month} KCS 조회 실패", exc)
        last_preview = clean(json.dumps(data, ensure_ascii=False))[:400]
        items = data.get("items") or []
        if not items:
            continue

        target = None
        for row in items:
            if str(row.get("priodTitle") or "") == "총계":
                continue
            row_hs = str(row.get("hsSgn") or "").replace(".", "")
            period = re.sub(r"[^0-9]", "", str(row.get("priodTitle") or ""))
            if row_hs == hs and month in period:
                target = row
                break
        if target is None:
            target = next((row for row in items if str(row.get("priodTitle") or "") != "총계"), None)
        if target is None:
            continue

        amt = _normalize_export_usd(_number(target.get("expUsdAmt")))
        weight = _number(target.get("expTtwg"))
        if amt is None:
            continue
        return {
            "month": month,
            "region": region["name"],
            "amount_usd": amt,
            "weight_kg": weight,
            "hs": hs,
            "raw_amount": _number(target.get("expUsdAmt")),
            "source": "관세청 수출입무역통계",
            "scope_note": "지역 공개자료는 HS6 854232 메모리 전체로, HBM 전용 HSK10이 아님",
        }, ""

    return None, f"{region['name']} {month} HS6 {hs} 미검출: {last_preview}"



def fetch_official_hbm_pack(now: datetime) -> tuple[dict | None, list[str]]:
    """Fetch the newest public official HBM-related trade pack.

    Exact nationwide MCP/HBM-containing series:
      HSK10 8542323000 from Korea Customs Service.
    Public regional direction:
      HS6 854232 for Chungnam and Chungbuk.
    Icheon is best-effort only because K-stat stopped public city/county HSK10
    disclosure from 2026-09-01; city/county HS6 weight is also non-public.
    """
    errors: list[str] = []
    current = _previous_month(now)
    data: dict[str, dict[str, dict]] = {}
    selected = None
    session = requests.Session()
    session.headers.update({"User-Agent": UA})
    try:
        session.get(KCS_SOURCE_PAGE, timeout=(5, 10))
    except Exception as exc:
        errors.append(_safe_error("관세청 세션 초기화 실패", exc))

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
            row, err = fetch_data_go_sido_month(candidate, region["sido"])
            if not row:
                row, err2 = fetch_kcs_region_month(candidate, region, session=session)
                if err2:
                    err = f"{err}; fallback={err2}"
            if row:
                rows[key] = row
            else:
                local_errors.append(err)

        malaysia, merr = fetch_data_go_country_item_month(candidate)
        if malaysia:
            rows["malaysia_hsk10"] = malaysia
        elif merr:
            local_errors.append(merr)

        row, err = fetch_kcs_region_month(candidate, REGIONS["hynix_icheon"], session=session)
        if row:
            rows["hynix_icheon"] = row
        else:
            local_errors.append(err)

        if all(k in rows for k in required_keys):
            selected = candidate
            data[candidate] = rows
            errors.extend(local_errors)
            break
        errors.extend(local_errors)

        # Do not fall back to an older month when the newest candidate failed
        # because of a network/API error. Older months are only considered when
        # the current candidate explicitly has no published data.
        if any(_is_transient_source_error(item) for item in local_errors):
            return None, errors

    if not selected:
        return None, errors

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
            row, err = fetch_data_go_sido_month(month, region["sido"])
            if not row:
                row, err2 = fetch_kcs_region_month(month, region, session=session)
                if err2:
                    err = f"{err}; fallback={err2}"
            if row:
                rows[key] = row
            else:
                errors.append(err)

        malaysia, merr = fetch_data_go_country_item_month(month)
        if malaysia:
            rows["malaysia_hsk10"] = malaysia
        elif merr:
            errors.append(merr)

        row, err = fetch_kcs_region_month(month, REGIONS["hynix_icheon"], session=session)
        if row:
            rows["hynix_icheon"] = row
        else:
            errors.append(err)
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
        "region_hs": REGION_HS6,
        "source_url": KCS_SOURCE_PAGE,
        "icheon_public_available": "hynix_icheon" in data.get(selected, {}),
        "malaysia_public_available": "malaysia_hsk10" in data.get(selected, {}),
        "malaysia_source_url": "https://www.data.go.kr/data/15100475/openapi.do",
        "official_api_key_configured": bool(DATA_GO_KEY),
        "official_api_used": bool(data.get(selected, {}).get("national_hsk10", {}).get("api")),
        "errors": errors,
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


def _unit_value(amount: float | None, weight: float | None) -> float | None:
    if amount is None or weight in (None, 0):
        return None
    return amount / weight


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
    if ch.get("reasons"):
        lines.append("• 이번 변화: " + html.escape(" · ".join(ch["reasons"])))
    lines += [f"• 감지 근거: {html.escape(e.get('source') or '미표시')} · {html.escape(e.get('published_at_kst') or '확인 불가')}", f"• {href(e.get('direct_link') or '', '근거 원문')}"]
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


def build_monthly(now: datetime, rate: float | None, fx_basis: str, official: dict) -> str:
    month = official["month"]
    cur = official["series"][month]
    prev_m = _month_shift(month, -1)
    prev_q = _month_shift(month, -3)
    prev_y = _month_shift(month, -12)
    prev = official["series"].get(prev_m, {})
    qbase = official["series"].get(prev_q, {})
    ybase = official["series"].get(prev_y, {})

    nat_mom = _pct(cur["national_amount"], prev.get("national_amount"))
    nat_q = _pct(cur["national_amount"], qbase.get("national_amount"))
    nat_y = _pct(cur["national_amount"], ybase.get("national_amount"))
    nat_uv = _unit_value(cur["national_amount"], cur.get("national_weight"))
    nat_prev_uv = _unit_value(prev.get("national_amount"), prev.get("national_weight"))

    sam_mom = _pct(cur["samsung_region_amount"], prev.get("samsung_region_amount"))
    sam_q = _pct(cur["samsung_region_amount"], qbase.get("samsung_region_amount"))
    cb_mom = _pct(cur["hynix_chungbuk_amount"], prev.get("hynix_chungbuk_amount"))
    cb_q = _pct(cur["hynix_chungbuk_amount"], qbase.get("hynix_chungbuk_amount"))
    my_mom = _pct(cur.get("malaysia_amount"), prev.get("malaysia_amount"))
    my_q = _pct(cur.get("malaysia_amount"), qbase.get("malaysia_amount"))
    my_y = _pct(cur.get("malaysia_amount"), ybase.get("malaysia_amount"))
    my_uv = _unit_value(cur.get("malaysia_amount"), cur.get("malaysia_weight"))
    my_prev_uv = _unit_value(prev.get("malaysia_amount"), prev.get("malaysia_weight"))

    nat_krw = krw_large(cur["national_amount"], rate)
    sam_krw = krw_large(cur["samsung_region_amount"], rate)
    cb_krw = krw_large(cur["hynix_chungbuk_amount"], rate)
    my_krw = krw_large(cur.get("malaysia_amount"), rate) if cur.get("malaysia_amount") is not None else "확인 불가"

    lines = [
        "🚨 <b>삼성·SK하이닉스 HBM 월간 비교</b>",
        "━━━━━━━━━━━━━━━━",
        "<b>[공식 원자료 최신월]</b>",
        f"• 관세청 확정치 <b>{month[:4]}년 {int(month[4:])}월</b>을 직접 재조회했습니다.",
        "• 과거 숫자를 최신값으로 재사용하지 않고, 새 확정월이 생긴 경우에만 월간 알림을 갱신합니다.",
        "",
        "<b>[1. 전국 HBM 포함 MCP — 정확한 HSK10]</b>",
        f"• HSK <b>{official['hs']}</b> 복합구조칩 집적회로(HBM 포함): <b>{_fmt_usd(cur['national_amount'])} · {nat_krw}</b>",
        f"• 변화: 전월 <b>{_fmt_pct(nat_mom)}</b> · 3개월 전 대비 <b>{_fmt_pct(nat_q)}</b> · 전년동월 <b>{_fmt_pct(nat_y)}</b>",
    ]
    if nat_uv is not None:
        lines.append(f"• 중량당 단가: <b>\${nat_uv:,.0f}/kg</b> · 전월 <b>{_fmt_pct(_pct(nat_uv, nat_prev_uv))}</b>")
    else:
        lines.append("• 중량당 단가: <b>관세청 중량값 확인 불가</b> — 추정하지 않음")

    lines += [
        "",
        "<b>[2. 지역 방향 — 공개 가능한 HS6]</b>",
        f"• <b>충남</b> HS {official['region_hs']} 메모리 집적회로: <b>{_fmt_usd(cur['samsung_region_amount'])} · {sam_krw}</b> | 전월 {_fmt_pct(sam_mom)} | 3개월 전 {_fmt_pct(sam_q)}",
        "  → 삼성 HBM 생산·출하 방향을 보는 <b>보조 지역지표</b>",
        f"• <b>충북</b> HS {official['region_hs']} 메모리 집적회로: <b>{_fmt_usd(cur['hynix_chungbuk_amount'])} · {cb_krw}</b> | 전월 {_fmt_pct(cb_mom)} | 3개월 전 {_fmt_pct(cb_q)}",
        "  → SK하이닉스 청주 방향을 보는 <b>보조 지역지표</b>",
    ]

    if official.get("icheon_public_available") and cur.get("icheon_amount") is not None:
        lines += [
            f"• <b>이천</b> HS {official['region_hs']}: {_fmt_usd(cur['icheon_amount'])}",
            "  → 공개 원자료가 확인된 경우에만 충북과 함께 표시합니다.",
        ]
    else:
        lines += [
            "• <b>이천</b>: 현재 공개 원자료 자동조회에서 수치를 확인하지 못해 <b>0으로 처리하거나 추정하지 않습니다.</b>",
            "  → 2026년 9월 1일부터 K-stat의 시·군·구 HSK 10단위 품목통계는 전체 비공개이며, HS 2·4·6 중량도 비공개입니다.",
        ]

    lines += [
        "",
        "<b>[3. 말레이시아 HSK10 — 첨단패키징 이동 보조축]</b>",
    ]
    if official.get("malaysia_public_available") and cur.get("malaysia_amount") is not None:
        lines += [
            f"• 한국→말레이시아 HSK <b>{official['hs']}</b>: <b>{_fmt_usd(cur.get('malaysia_amount'))} · {my_krw}</b>",
            f"• 변화: 전월 <b>{_fmt_pct(my_mom)}</b> · 3개월 전 <b>{_fmt_pct(my_q)}</b> · 전년동월 <b>{_fmt_pct(my_y)}</b>",
        ]
        if my_uv is not None:
            lines.append(f"• 중량당 단가: <b>\${my_uv:,.0f}/kg</b> · 전월 <b>{_fmt_pct(_pct(my_uv, my_prev_uv))}</b>")
        else:
            lines.append("• 중량당 단가: <b>확인 불가</b> — 추정하지 않음")
        lines += [
            "• 의미: 말레이시아 첨단패키징·조립 거점으로의 HBM 포함 복합메모리 이동을 보는 <b>보조 신호</b>",
            "• 주의: 말레이시아향 HSK 8542323000 전체가 HBM 또는 Intel EMIB용이라는 뜻은 아닙니다.",
            f"• Intel EMIB {href(INTEL_EMIB_OFFICIAL)} · Intel Malaysia {href(INTEL_MALAYSIA_OFFICIAL)}",
        ]
    else:
        lines += [
            "• 관세청 국가별 HSK10 직접값을 확인하지 못했습니다. <b>0으로 처리하거나 추정하지 않습니다.</b>",
            "• 이 경우 Intel Malaysia·EMIB·HBM 관련 공식자료와 신뢰 보도를 보조 감시합니다.",
        ]

    lines += [
        "",
        "<b>[4. 회사별 정밀 대용지표]</b>",
        "• 회사별 HBM 정밀 비교는 <b>충남 HSK10 vs 충북+이천 HSK10</b>을 사용한 Bernstein 등 신뢰 리서치가 새로 공개될 때 별도로 갱신합니다.",
        "• 마지막 확인 기준선(2026년 7월): 충남은 4월 대비 <b>+122%</b>, 충북+이천은 약 <b>-27%</b>였습니다.",
        "• 이 기준선을 8월·9월 현재값처럼 재사용하지 않습니다.",
        "",
        "<b>[판정]</b>",
        "• <b>전국 HSK10</b>은 HBM 포함 MCP 업황의 가장 정밀한 공개 공식 월간축입니다.",
        "• <b>지역 HS6</b>은 메모리 전체 범주여서 삼성·SK하이닉스 HBM 매출과 1:1 대응하지 않습니다.",
        "• 따라서 HBM 방향 판정은 전국 HSK10 + 지역 방향 + HBM4/HBM4E 제품혼합 + 고객 인증·실제 출하를 함께 봅니다.",
        "",
        "<b>[다음 알림]</b>",
        "• 관세청에 새 월 HSK 8542323000 확정치가 생기는 즉시",
        "• 전국 HBM 포함 MCP 수출액·중량당 단가의 방향이 크게 바뀔 때",
        "• 충남·충북 지역 메모리 방향이 반전할 때",
        "• 한국→말레이시아 HSK10 수출액·중량당 단가 방향이 크게 바뀔 때",
        "• Intel Malaysia의 EMIB·HBM 첨단패키징 생산능력·투자·양산 상태가 바뀔 때",
        "• Bernstein 등에서 충남 vs 충북+이천 HSK10 정밀 비교가 새로 확인될 때",
        "• 삼성·SK하이닉스 HBM 매출·점유율·NVIDIA 공급물량이 새로 확인될 때",
        "",
        f"<b>환율</b>: {html.escape(fx_basis)}",
        f"<b>조회</b>: {now.strftime('%Y-%m-%d %H:%M KST')}",
        "<b>원문</b>: "
        + f"관세청 {href(official['source_url'])} · "
        + f"K-stat {href('https://stat.kita.net/')} · "
        + f"Counterpoint {href(COUNTERPOINT_HBM_SHARE)} · "
        + f"Bernstein {href(BERNSTEIN_EXPORT)} · "
        + f"말레이시아 관세청 API {href(official.get('malaysia_source_url') or 'https://www.data.go.kr/data/15100475/openapi.do')}",
    ]
    return "\n".join(lines) + "\n"



def build_event_alert(events: list[dict], now: datetime) -> str:
    selected = events[:4]
    hbm_events = [e for e in selected if not e.get("capital_return_change")]
    capital_events = [e for e in selected if e.get("capital_return_change")]
    lines: list[str] = []
    if hbm_events:
        lines += ["🚨 <b>HBM 상태 변화</b>", "━━━━━━━━━━━━━━━━", f"<b>신규 변화 {len(hbm_events)}건</b> · {now.strftime('%Y-%m-%d %H:%M KST')}", ""]
        for i, e in enumerate(hbm_events, 1):
            lines.append(f"<b>{i}.</b>")
            lines.extend(event_summary(e))
            if i < len(hbm_events):
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
    now = datetime.now(ZoneInfo("Asia/Seoul"))
    state = load_state()
    seen = set(state.get("seen_ids") or [])
    month_key = now.strftime("%Y-%m")

    events = read_events()
    cutoff = now - timedelta(hours=FRESH_HOURS)
    topic_states = dict(state.get("topic_states") or {})

    share_forecasts = dict(state.get("hbm_share_forecasts") or {})
    share_actuals = dict(state.get("hbm_share_actuals") or {})
    broker_forecasts = dict(state.get("hbm_broker_forecasts") or {})
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
            if e.get("id") in structured_share_event_ids or e.get("id") in structured_broker_event_ids or e.get("id") in structured_capital_event_ids or e.get("id") in structured_ops_event_ids:
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
        if e.get("id") in structured_share_event_ids or e.get("id") in structured_broker_event_ids or e.get("id") in structured_capital_event_ids or e.get("id") in structured_ops_event_ids:
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

    send_events = sorted(
        fresh_new + share_alert_events + broker_alert_events + capital_alert_events + ops_alert_events,
        key=lambda x: x.get("published_at_kst") or "",
    )[:4]

    rate, fx_basis = fx_quote()
    official, official_errors = fetch_official_hbm_pack(now) if now.day >= MONTHLY_DAY else (None, [])
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
    monthly_due = bool(
        official
        and (
            state.get("last_official_alert_month") != official_month
            or int(state.get("compare_version") or 0) < COMPARE_VERSION
            or malaysia_revision_due
        )
    )

    if monthly_due and official:
        ALERT.write_text(build_monthly(now, rate, fx_basis, official), encoding="utf-8")
        state["last_monthly_digest"] = month_key
        state["last_official_alert_month"] = official_month
        state["compare_version"] = COMPARE_VERSION
        # Do not consume pending topic-state changes behind a monthly alert.
        # They remain eligible on the next run.
    elif send_events:
        ALERT.write_text(build_event_alert(send_events, now), encoding="utf-8")
        for e in send_events:
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
        "last_capital_return_observation_count": 1 if latest_capital_obs else 0,
        "last_capital_return_alert_count": len([e for e in send_events if e.get("capital_return_change")]),
        "last_share_observation_count": len(latest_share_obs),
        "last_share_alert_count": len([e for e in send_events if e.get("share_change")]),
        "last_event_count": len(events),
        "last_fresh_new_count": len(fresh_new),
        "last_send_event_count": len(send_events),
        "monthly_due": monthly_due,
        "official_month": official_month,
        "official_data_ok": bool(official),
        "official_api_key_configured": bool(DATA_GO_KEY),
        "official_api_used": bool(official and official.get("official_api_used")),
        "malaysia_official_month": official_month if official else state.get("malaysia_official_month", ""),
        "malaysia_hsk10_amount_usd": current_malaysia_amount,
        "malaysia_hsk10_weight_kg": current_malaysia_weight,
        "malaysia_public_available": bool(official and official.get("malaysia_public_available")),
        "malaysia_revision_due": malaysia_revision_due,
        "official_errors": [re.sub(r"serviceKey=[^&\s]+", "serviceKey=<redacted>", str(x)) for x in official_errors[-8:]],
    })
    if official:
        state["last_successful_official_month"] = official_month
        state["last_successful_official_at_kst"] = now.isoformat(timespec="seconds")
    save_state(state)

    STATUS.write_text(
        "# Samsung HBM Watch\n"
        f"- checked_at_kst: {now.isoformat(timespec='seconds')}\n"
        f"- events: {len(events)}\n"
        f"- event_state_version: {EVENT_STATE_VERSION}\n"
        f"- topic_state_count: {len(topic_states)}\n"
        f"- share_track_version: {SHARE_TRACK_VERSION}\n"
        f"- broker_forecast_track_version: {BROKER_FORECAST_TRACK_VERSION}\n"
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
        f"- capital_return_observations: {1 if latest_capital_obs else 0}\n"
        f"- capital_return_alerts: {len([e for e in send_events if e.get('capital_return_change')])}\n"
        f"- share_observations: {len(latest_share_obs)}\n"
        f"- share_alerts: {len([e for e in send_events if e.get('share_change')])}\n"
        f"- fresh_new: {len(fresh_new)}\n"
        f"- monthly_due: {str(monthly_due).lower()}\n"
        f"- official_month: {official_month or 'none'}\n"
        f"- official_data_ok: {str(bool(official)).lower()}\n"
        f"- official_api_key_configured: {str(bool(DATA_GO_KEY)).lower()}\n"
        f"- official_api_used: {str(bool(official and official.get('official_api_used'))).lower()}\n"
        f"- malaysia_public_available: {str(bool(official and official.get('malaysia_public_available'))).lower()}\n"
        f"- malaysia_hsk10_amount_usd: {current_malaysia_amount if current_malaysia_amount is not None else 'none'}\n"
        f"- malaysia_hsk10_weight_kg: {current_malaysia_weight if current_malaysia_weight is not None else 'none'}\n"
        f"- malaysia_revision_due: {str(malaysia_revision_due).lower()}\n"
        f"- official_errors: {len(official_errors)}\n"
        f"- alert_generated: {str(monthly_due or bool(send_events)).lower()}\n",
        encoding="utf-8",
    )


if __name__ == "__main__":
    main()
