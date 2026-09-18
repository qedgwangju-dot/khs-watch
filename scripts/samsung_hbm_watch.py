from __future__ import annotations

import hashlib
import html
import json
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
COMPARE_VERSION = 2
KCS_REGION_URL = "https://tradedata.go.kr/cts/hmpg/retrieveTradeRegion.do"
HBM_HSK10 = "8542323000"
KCS_SOURCE_PAGE = "https://tradedata.go.kr/cts/index.do"
REGIONS = {
    "samsung_chungnam": {"name": "충남", "kind": "sido", "sido": "44", "sgg": ""},
    "hynix_chungbuk": {"name": "충북", "kind": "sido", "sido": "43", "sgg": ""},
    "hynix_icheon": {"name": "이천", "kind": "sgg", "sido": "41", "sgg": "500"},
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
]

TRUSTED = (
    "samsung", "reuters", "bloomberg", "trendforce", "counterpoint", "investing.com",
    "sedaily", "seoul economic", "zdnet", "the elec", "thelec", "digitimes",
    "yonhap", "연합뉴스", "chosunbiz", "조선비즈",
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
        or "sk hynix" in low or "sk hynix" in low or "sk하이닉스" in low
    )
    hbm = "hbm" in low
    signal = any(k in low for k in (
        "shipment", "ship", "mass production", "qualification", "validation", "customer",
        "market share", "revenue", "export", "mix", "allocation", "contract", "price",
        "출하", "양산", "인증", "검증", "고객", "점유율", "매출", "수출", "비중", "계약", "가격",
    ))
    return company and hbm and signal


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


def fetch_kcs_region_month(month: str, region: dict, hs: str = HBM_HSK10, session=None) -> tuple[dict | None, str]:
    hs_col = f"HS{len(hs)}_SGN"
    params = {
        "tradeKind": "ETS_MNK_1040000A",
        "sidosggKind": region["kind"],
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
    }
    own = session is None
    sess = session or requests.Session()
    try:
        if own:
            sess.headers.update({"User-Agent": UA})
            sess.get(KCS_SOURCE_PAGE, timeout=(5, 10))
        r = sess.post(KCS_REGION_URL, headers=headers, params=params, timeout=(5, 12))
        if r.status_code != 200:
            return None, f"{region['name']} {month} KCS HTTP {r.status_code}"
        data = r.json()
    except Exception as exc:
        return None, f"{region['name']} {month} KCS 조회 실패: {type(exc).__name__}: {exc}"

    candidates = []
    for row in _walk_dicts(data):
        keys = {str(k).lower(): k for k in row.keys()}
        amt_key = next((keys[k] for k in ("expusdamt", "expdlr", "expamt") if k in keys), None)
        if amt_key is None:
            continue
        row_hs = str(row.get(keys.get("hssgn", ""), "") or "").replace(".", "")
        period = str(row.get(keys.get("priodtitle", ""), row.get(keys.get("year", ""), "")) or "")
        score = 0
        if row_hs == hs:
            score += 10
        if month in re.sub(r"[^0-9]", "", period):
            score += 5
        if row_hs:
            score += 1
        candidates.append((score, row, keys, amt_key))

    if not candidates:
        preview = clean(json.dumps(data, ensure_ascii=False))[:500]
        return None, f"{region['name']} {month} KCS 응답에서 수출금액 행 미검출: {preview}"

    _, row, keys, amt_key = max(candidates, key=lambda x: x[0])
    amt_raw = _number(row.get(amt_key))
    amount_usd = _normalize_export_usd(amt_raw)
    wgt_key = next((keys[k] for k in ("expwgt", "expwgtamt", "wgt") if k in keys), None)
    weight_kg = _number(row.get(wgt_key)) if wgt_key else None
    hs_returned = str(row.get(keys.get("hssgn", ""), "") or "").replace(".", "")
    if hs_returned and hs_returned != hs:
        return None, f"{region['name']} {month} 요청 HSK {hs}와 응답 {hs_returned} 불일치"
    if amount_usd is None:
        return None, f"{region['name']} {month} 수출금액 숫자 변환 실패"

    return {
        "month": month,
        "region": region["name"],
        "amount_usd": amount_usd,
        "weight_kg": weight_kg,
        "hs": hs,
        "raw_amount": amt_raw,
        "source": "관세청 수출입무역통계",
    }, ""

def fetch_official_hbm_pack(now: datetime) -> tuple[dict | None, list[str]]:
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

    for candidate in [current, _month_shift(current, -1), _month_shift(current, -2)]:
        rows = {}
        local_errors = []
        for key, region in REGIONS.items():
            row, err = fetch_kcs_region_month(candidate, region, session=session)
            if row:
                rows[key] = row
            else:
                local_errors.append(err)
        if len(rows) == len(REGIONS):
            selected = candidate
            data[candidate] = rows
            break
        errors.extend(local_errors)

    if not selected:
        return None, errors

    needed = [selected, _month_shift(selected, -1), _month_shift(selected, -3), _month_shift(selected, -12)]
    for month in needed:
        if month in data:
            continue
        rows = {}
        for key, region in REGIONS.items():
            row, err = fetch_kcs_region_month(month, region, session=session)
            if row:
                rows[key] = row
            else:
                errors.append(err)
        data[month] = rows

    if any(len(data.get(m, {})) != len(REGIONS) for m in needed[:3]):
        return None, errors

    def combine(month: str) -> dict:
        rows = data[month]
        sam = rows["samsung_chungnam"]
        cb = rows["hynix_chungbuk"]
        ic = rows["hynix_icheon"]
        hynix_amount = cb["amount_usd"] + ic["amount_usd"]
        hynix_weight = None
        if cb.get("weight_kg") is not None and ic.get("weight_kg") is not None:
            hynix_weight = cb["weight_kg"] + ic["weight_kg"]
        return {
            "samsung_amount": sam["amount_usd"],
            "samsung_weight": sam.get("weight_kg"),
            "hynix_amount": hynix_amount,
            "hynix_weight": hynix_weight,
            "chungbuk_amount": cb["amount_usd"],
            "icheon_amount": ic["amount_usd"],
        }

    series = {m: combine(m) for m in needed if len(data.get(m, {})) == len(REGIONS)}
    return {
        "month": selected,
        "series": series,
        "hs": HBM_HSK10,
        "source_url": KCS_SOURCE_PAGE,
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
    if "bernstein" in text or ("chung" in text and "export" in text) or "충남" in text or "충북" in text or "이천" in text:
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

    sam_mom = _pct(cur["samsung_amount"], prev.get("samsung_amount"))
    sam_q = _pct(cur["samsung_amount"], qbase.get("samsung_amount"))
    sam_y = _pct(cur["samsung_amount"], ybase.get("samsung_amount"))
    hyn_mom = _pct(cur["hynix_amount"], prev.get("hynix_amount"))
    hyn_q = _pct(cur["hynix_amount"], qbase.get("hynix_amount"))
    hyn_y = _pct(cur["hynix_amount"], ybase.get("hynix_amount"))

    sam_uv = _unit_value(cur["samsung_amount"], cur.get("samsung_weight"))
    sam_prev_uv = _unit_value(prev.get("samsung_amount"), prev.get("samsung_weight"))
    hyn_uv = _unit_value(cur["hynix_amount"], cur.get("hynix_weight"))
    hyn_prev_uv = _unit_value(prev.get("hynix_amount"), prev.get("hynix_weight"))

    sam_krw = krw_large(cur["samsung_amount"], rate)
    hyn_krw = krw_large(cur["hynix_amount"], rate)

    lines = [
        "🚨 <b>삼성·SK하이닉스 HBM 월간 비교</b>",
        "━━━━━━━━━━━━━━━━",
        "<b>[공식 원자료 최신월]</b>",
        f"• 관세청 HSK <b>{official['hs']}</b> 복합구조칩 집적회로 · <b>{month[:4]}년 {int(month[4:])}월</b>",
        "• 매 실행마다 관세청 원자료에서 직접 다시 조회하며, 이전 달 값을 최신값처럼 재사용하지 않습니다.",
        "",
        "<b>[한눈에 보기]</b>",
        f"• <b>삼성 대용지역 · 충남</b>: {_fmt_usd(cur['samsung_amount'])} · {sam_krw} | 전월 {_fmt_pct(sam_mom)} | 3개월 전 대비 {_fmt_pct(sam_q)} | 전년동월 {_fmt_pct(sam_y)}",
        f"• <b>SK하이닉스 대용지역 · 충북+이천</b>: {_fmt_usd(cur['hynix_amount'])} · {hyn_krw} | 전월 {_fmt_pct(hyn_mom)} | 3개월 전 대비 {_fmt_pct(hyn_q)} | 전년동월 {_fmt_pct(hyn_y)}",
        f"  └ 충북 {_fmt_usd(cur['chungbuk_amount'])} + 이천 {_fmt_usd(cur['icheon_amount'])}",
        "",
        "<b>[중량당 단가]</b>",
    ]

    if sam_uv is not None:
        lines.append(f"• 삼성 충남: <b>\${sam_uv:,.0f}/kg</b> | 전월 {_fmt_pct(_pct(sam_uv, sam_prev_uv))}")
    else:
        lines.append("• 삼성 충남: <b>공식 중량 확인 불가</b> — 추정하지 않음")
    if hyn_uv is not None:
        lines.append(f"• SK하이닉스 충북+이천: <b>\${hyn_uv:,.0f}/kg</b> | 전월 {_fmt_pct(_pct(hyn_uv, hyn_prev_uv))}")
    else:
        lines.append("• SK하이닉스 충북+이천: <b>공식 중량 확인 불가</b> — 시군구 중량 비공개 시 대체 추정 금지")

    lines += [
        "",
        "<b>[해석]</b>",
        "• 충남은 삼성 HBM, 충북+이천은 SK하이닉스 HBM 출하를 추적하는 <b>지역 대용지표</b>입니다.",
        "• HSK 8542323000에는 HBM 외 다른 복합구조 메모리도 포함될 수 있어 <b>회사 공식 HBM 매출과 1:1 동일하지 않습니다.</b>",
        "• 방향은 <b>수출액 + 중량당 단가 + HBM4/HBM4E 제품혼합 + 고객 인증</b>을 함께 확인합니다.",
        "",
        "<b>[현재 기준선]</b>",
        "• 최신 시장점유율: <b>SK하이닉스 50% · 삼성 33% · Micron 18%</b> (2026년 2분기, Counterpoint)",
        "• 삼성 HBM4: 공식 <b>양산·상업 출하</b> / HBM4E: <b>12단 샘플 출하</b>",
        "",
        "<b>[다음 알림]</b>",
        "• 관세청에 새 월 HSK 8542323000 지역별 확정치가 생기는 즉시",
        "• 충남 vs 충북+이천 수출액 방향이 반전하거나 격차가 크게 변할 때",
        "• 중량당 단가가 급변해 HBM4/HBM4E 제품혼합 변화가 의심될 때",
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
        f"- official_errors: {len(official_errors)}\n"
        f"- alert_generated: {str(monthly_due or bool(send_events)).lower()}\n",
        encoding="utf-8",
    )


if __name__ == "__main__":
    main()
