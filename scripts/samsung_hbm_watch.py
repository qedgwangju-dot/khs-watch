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
KCS_ITEM_URL = "https://tradedata.go.kr/cts/hmpg/retrieveTrade.do"
DATA_GO_ITEM_URL = "https://apis.data.go.kr/1220000/Itemtrade/getItemtradeList"
DATA_GO_SIDO_ITEM_URL = "https://apis.data.go.kr/1220000/sidoitemtrade/getSidoitemtradeList"
DATA_GO_KEY = urllib.parse.unquote((os.getenv("KCS_DATA_GO_SERVICE_KEY") or "").strip())
KCS_REGION_URL = "https://tradedata.go.kr/cts/hmpg/retrieveTradeRegion.do"
HBM_HSK10 = "8542323000"
REGION_HS6 = "854232"
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

QUERIES = [
    '"Samsung" HBM4 HBM4E NVIDIA qualification shipment mass production',
    '"Samsung Electronics" HBM market share Counterpoint',
    '"Samsung" HBM Bernstein export Chungcheong revenue',
    '"Samsung" HBM4 shipment share mix LS Securities',
    '"Samsung" HBM Broadcom AMD NVIDIA Google custom HBM',
    '"삼성전자" HBM4 HBM4E 엔비디아 공급 출하 점유율',
    '"삼성전자" HBM 충남 수출 Bernstein',
    '"SK hynix" HBM Bernstein export Chungbuk Icheon',
    '"SK하이닉스" HBM 충북 이천 수출 Bernstein',
    '"South Chungcheong" "North Chungcheong" Icheon HBM export',
    '"Icheon" "SK hynix" (HBM OR memory OR semiconductor) (export OR shipment OR revenue)',
    '"이천" "SK하이닉스" (HBM OR 메모리 OR 반도체) (수출 OR 출하 OR 매출)',
    '"이천" 반도체 수출 한국무역협회',
    '"이천" 반도체 수출 TRASS',
    '"이천" HBM Bernstein',
]

TRUSTED = (
    "samsung", "reuters", "bloomberg", "trendforce", "counterpoint", "investing.com",
    "sedaily", "seoul economic", "zdnet", "the elec", "thelec", "digitimes",
    "yonhap", "연합뉴스", "chosunbiz", "조선비즈", "newsis", "뉴시스",
    "kita", "한국무역협회", "k-stat", "trass", "한국무역통계진흥원",
    "customs", "관세청", "icheon", "이천시",
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
    if "reuters" in low:
        return 95
    if "counterpoint" in low or "trendforce" in low:
        return 90
    if "bloomberg" in low or "digitimes" in low:
        return 85
    if "investing.com" in low or "sedaily" in low or "seoul economic" in low:
        return 80
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
        "출하", "양산", "인증", "검증", "고객", "점유율", "매출", "수출", "비중", "계약", "가격",
    ))
    icheon_proxy = (
        ("icheon" in low or "이천" in low)
        and ("sk hynix" in low or "sk하이닉스" in low or "semiconductor" in low or "반도체" in low or "memory" in low or "메모리" in low)
        and any(k in low for k in ("export", "shipment", "revenue", "production", "수출", "출하", "매출", "생산"))
    )
    return (company and hbm and signal) or icheon_proxy


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



def _xml_text(item, *names):
    for name in names:
        val = item.findtext(name)
        if val not in (None, ""):
            return val
    return None


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
        r = requests.get(DATA_GO_ITEM_URL, params=params, timeout=(5, 15))
        root = ET.fromstring(r.content)
    except Exception as exc:
        return None, f"공공데이터포털 전국 API 실패: {type(exc).__name__}: {exc}"
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
        r = requests.get(DATA_GO_SIDO_ITEM_URL, params=params, timeout=(5, 15))
        root = ET.fromstring(r.content)
    except Exception as exc:
        return None, f"공공데이터포털 시도 API 실패: {type(exc).__name__}: {exc}"
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
        r = session.post(KCS_ITEM_URL, headers=headers, data=params, timeout=(5, 12))
        if r.status_code != 200:
            return None, f"전국 {month} KCS HTTP {r.status_code}"
        data = r.json()
    except Exception as exc:
        return None, f"전국 {month} KCS 조회 실패: {type(exc).__name__}: {exc}"

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
            r = sess.post(KCS_REGION_URL, headers=headers, data=params, timeout=(5, 12))
            if r.status_code != 200:
                continue
            data = r.json()
        except Exception as exc:
            return None, f"{region['name']} {month} KCS 조회 실패: {type(exc).__name__}: {exc}"
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
        errors.append(f"관세청 세션 초기화 실패: {type(exc).__name__}: {exc}")

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
        return {
            "national_amount": nat["amount_usd"],
            "national_weight": nat.get("weight_kg"),
            "samsung_region_amount": sam["amount_usd"],
            "samsung_region_weight": sam.get("weight_kg"),
            "hynix_chungbuk_amount": cb["amount_usd"],
            "hynix_chungbuk_weight": cb.get("weight_kg"),
            "icheon_amount": ic["amount_usd"] if ic else None,
            "icheon_weight": ic.get("weight_kg") if ic else None,
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


def event_summary(e: dict) -> list[str]:
    category, headline = classify_event(e)
    text = clean(f"{e.get('title','')} {e.get('description','')}")
    pcts = list(dict.fromkeys(re.findall(r"[+-]?\d+(?:\.\d+)?%", text)))[:4]
    dollars = list(dict.fromkeys(re.findall(r"\$\s*\d+(?:\.\d+)?\s*(?:billion|million|B|M)\b", text, re.I)))[:2]
    nums = []
    if pcts:
        nums.append(" / ".join(pcts))
    if dollars:
        nums.append(" / ".join(dollars))
    lines = [
        f"<b>{headline}</b>",
        f"• 구분: {category}",
        f"• 출처: {html.escape(e.get('source') or '미표시')} · 공개 {html.escape(e.get('published_at_kst') or '확인 불가')}",
    ]
    if nums:
        lines.append(f"• 핵심 숫자: <b>{html.escape(' · '.join(nums))}</b>")
    lines += [
        f"• 제목: {html.escape(e.get('title') or '')}",
        href(e.get("direct_link") or ""),
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

    nat_krw = krw_large(cur["national_amount"], rate)
    sam_krw = krw_large(cur["samsung_region_amount"], rate)
    cb_krw = krw_large(cur["hynix_chungbuk_amount"], rate)

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
        "<b>[3. 회사별 정밀 대용지표]</b>",
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
        "• Bernstein 등에서 충남 vs 충북+이천 HSK10 정밀 비교가 새로 확인될 때",
        "• 삼성·SK하이닉스 HBM 매출·점유율·NVIDIA 공급물량이 새로 확인될 때",
        "",
        f"<b>환율</b>: {html.escape(fx_basis)}",
        f"<b>조회</b>: {now.strftime('%Y-%m-%d %H:%M KST')}",
        f"<b>관세청 원자료</b>: {href(official['source_url'])}",
        f"Counterpoint {href(COUNTERPOINT_HBM_SHARE)} · Bernstein 방법론 참고 {href(BERNSTEIN_EXPORT)}",
    ]
    return "\n".join(lines) + "\n"



def build_event_alert(events: list[dict], now: datetime) -> str:
    lines = [
        "🚨 <b>삼성전자 HBM 신규 변화</b>",
        "━━━━━━━━━━━━━━━━",
        f"<b>신규 변화 {len(events)}건</b> · {now.strftime('%Y-%m-%d %H:%M KST')}",
        "",
    ]
    for i, e in enumerate(events[:4], 1):
        lines.append(f"<b>{i}.</b>")
        lines.extend(event_summary(e))
        lines.append("")
    lines += [
        "<b>판정 원칙</b>",
        "• 기사 제목만으로 호재·악재를 정하지 않고 <b>물량·가격·고객 인증·실제 출하</b>를 같이 봅니다.",
        "• 충남 수출과 증권사 추정은 <b>삼성 공식 HBM 매출과 분리</b>해서 표시합니다.",
    ]
    return "\n".join(lines).strip() + "\n"


def main() -> None:
    now = datetime.now(ZoneInfo("Asia/Seoul"))
    state = load_state()
    seen = set(state.get("seen_ids") or [])
    month_key = now.strftime("%Y-%m")

    events = read_events()
    cutoff = now - timedelta(hours=FRESH_HOURS)
    fresh_new = []
    for e in events:
        try:
            dt = datetime.fromisoformat(e.get("published_at_kst") or "")
        except Exception:
            continue
        if cutoff <= dt <= now + timedelta(minutes=10) and e["id"] not in seen:
            fresh_new.append(e)

    chosen: dict[str, dict] = {}
    for e in fresh_new:
        category, _ = classify_event(e)
        old = chosen.get(category)
        if old is None or e["rank"] > old["rank"] or (
            e["rank"] == old["rank"] and e.get("published_at_kst","") > old.get("published_at_kst","")
        ):
            chosen[category] = e
    send_events = sorted(chosen.values(), key=lambda x: x.get("published_at_kst") or "")

    rate, fx_basis = fx_quote()
    official, official_errors = fetch_official_hbm_pack(now) if now.day >= MONTHLY_DAY else (None, [])
    official_month = official.get("month") if official else ""
    monthly_due = bool(
        official
        and (
            state.get("last_official_alert_month") != official_month
            or int(state.get("compare_version") or 0) < COMPARE_VERSION
        )
    )

    if monthly_due and official:
        ALERT.write_text(build_monthly(now, rate, fx_basis, official), encoding="utf-8")
        state["last_monthly_digest"] = month_key
        state["last_official_alert_month"] = official_month
        state["compare_version"] = COMPARE_VERSION
        seen.update(e["id"] for e in events)
    elif send_events:
        ALERT.write_text(build_event_alert(send_events, now), encoding="utf-8")
        seen.update(e["id"] for e in events)
    elif ALERT.exists():
        ALERT.unlink()

    state.update({
        "updated_at_kst": now.isoformat(timespec="seconds"),
        "seen_ids": sorted(seen)[-1500:],
        "last_event_count": len(events),
        "last_fresh_new_count": len(fresh_new),
        "last_send_event_count": len(send_events),
        "monthly_due": monthly_due,
        "official_month": official_month,
        "official_data_ok": bool(official),
        "official_api_key_configured": bool(DATA_GO_KEY),
        "official_api_used": bool(official and official.get("official_api_used")),
        "official_errors": official_errors[-8:],
    })
    save_state(state)

    STATUS.write_text(
        "# Samsung HBM Watch\n"
        f"- checked_at_kst: {now.isoformat(timespec='seconds')}\n"
        f"- events: {len(events)}\n"
        f"- fresh_new: {len(fresh_new)}\n"
        f"- monthly_due: {str(monthly_due).lower()}\n"
        f"- official_month: {official_month or 'none'}\n"
        f"- official_data_ok: {str(bool(official)).lower()}\n"
        f"- official_api_key_configured: {str(bool(DATA_GO_KEY)).lower()}\n"
        f"- official_api_used: {str(bool(official and official.get('official_api_used'))).lower()}\n"
        f"- official_errors: {len(official_errors)}\n"
        f"- alert_generated: {str(monthly_due or bool(send_events)).lower()}\n",
        encoding="utf-8",
    )


if __name__ == "__main__":
    main()
