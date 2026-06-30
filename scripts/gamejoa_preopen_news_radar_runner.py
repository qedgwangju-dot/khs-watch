#!/usr/bin/env python3
"""Compact GAMEJOA 06:30 KST news radar runner for GitHub Actions."""

from __future__ import annotations

import csv
import datetime as dt
import email.utils
import html
import json
import os
import re
import sys
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from pathlib import Path
from zoneinfo import ZoneInfo


ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "out"
KST = ZoneInfo("Asia/Seoul")
MAX_AGE_HOURS = int(os.getenv("RADAR_MAX_AGE_HOURS", "48"))
UA = os.getenv("SEC_USER_AGENT", "GAMEJOA-preopen-radar contact=please-set-secret")
FRED_API_KEY = os.getenv("FRED_API_KEY", "").strip()
DART_API_KEY = os.getenv("DART_API_KEY", "").strip()
DART_DAYS_BACK = max(1, int(os.getenv("DART_DAYS_BACK", "3")))
DART_WATCH_STOCK_CODES = {code.strip() for code in os.getenv("DART_WATCH_STOCK_CODES", "").split(",") if code.strip()}
TELEGRAM_LIMIT = 4096

FRED_CSV = "https://fred.stlouisfed.org/graph/fredgraph.csv?id=DFII10"
TE_URL = "https://tradingeconomics.com/united-states/10-year-tips-yield"

SOURCES = [
    ("FERC", "https://www.ferc.gov/news-events/news/rss.xml", "official"),
    ("DOE", "https://www.energy.gov/rss.xml", "official"),
    ("Commerce", "https://www.commerce.gov/news/rss.xml", "official"),
    ("BIS", "https://www.bis.doc.gov/index.php/newsroom/news-releases?format=feed&type=rss", "official"),
    ("SEC", "https://www.sec.gov/news/pressreleases.rss", "official"),
    ("FTC", "https://www.ftc.gov/news-events/news/press-releases/rss.xml", "official"),
    ("Federal Register data center", "https://www.federalregister.gov/api/v1/documents.json?conditions%5Bterm%5D=data%20center%20power%20grid&order=newest&per_page=15", "fr"),
    ("Federal Register export controls", "https://www.federalregister.gov/api/v1/documents.json?conditions%5Bterm%5D=semiconductor%20export%20controls&order=newest&per_page=15", "fr"),
    ("Federal Register tariffs", "https://www.federalregister.gov/api/v1/documents.json?conditions%5Bterm%5D=tariff%20section%20301&order=newest&per_page=15", "fr"),
    ("Federal Register USTR", "https://www.federalregister.gov/api/v1/documents.json?conditions%5Bagencies%5D%5B%5D=trade-representative-office-of-united-states&order=newest&per_page=15", "fr"),
    ("Federal Register sanctions", "https://www.federalregister.gov/api/v1/documents.json?conditions%5Bterm%5D=OFAC%20sanctions%20export%20controls&order=newest&per_page=15", "fr"),
    ("Federal Register FDA material", "https://www.federalregister.gov/api/v1/documents.json?conditions%5Bagencies%5D%5B%5D=food-and-drug-administration&conditions%5Bterm%5D=BLA%20NDA%20PDUFA%20advisory%20committee%20complete%20response%20letter%20clinical%20hold&order=newest&per_page=15", "fr"),
    ("Federal Register FTC", "https://www.federalregister.gov/api/v1/documents.json?conditions%5Bagencies%5D%5B%5D=federal-trade-commission&order=newest&per_page=15", "fr"),
]

QUERIES = [
    ("AI 전력망", "FERC DOE AI data center power grid nuclear energy policy Reuters Bloomberg CNBC"),
    ("데이터센터 지역 금지", '"data center" ban moratorium city council residents vote zoning power Reuters Bloomberg AP USA Today'),
    ("데이터센터 지역 차단", '"data centers" residents vote block construction city council zoning moratorium county township local news'),
    ("데이터센터 인허가 반대", '"data center" "planning commission" "public hearing" permit ordinance moratorium power local news'),
    ("FCC 보안장비/인버터", "FCC national security import ban foreign equipment inverters solar grid Reuters Bloomberg"),
    ("반도체/AI", "Nvidia Micron Broadcom AMD Intel TSMC ASML ARM Apple Microsoft Oracle AI chip HBM data center server network cooling guidance supply agreement Reuters Bloomberg MarketWatch"),
    ("수출통제/관세", "US Commerce BIS export controls tariffs China semiconductor Reuters Bloomberg AP"),
    ("미국 고충격 정책", "US policy ban tariff export control investigation subsidy loan nuclear data center power grid robotics semiconductor Reuters Bloomberg Politico"),
    ("EU/한국 정책 영향", "EU South Korea tariff quota safeguard CBAM battery regulation steel export control Reuters Bloomberg Yonhap"),
    ("정책/규제", "USTR FTC SEC DOE FERC FCC Commerce BIS OFAC CHIPS Act IRA tariff sanctions export controls Reuters Bloomberg AP"),
    ("기업 이벤트", "MOU LOI contract supply agreement joint venture capex buyback offering convertible bond guidance Reuters Bloomberg MarketWatch Korea"),
    ("지정학/에너지", "Iran Israel Hormuz Red Sea oil shipping sanctions Reuters Bloomberg AP CNBC MarketWatch"),
    ("원자재/매크로", "oil natural gas copper lithium uranium gold dollar won treasury yield Fed real yield TIPS Reuters Bloomberg CNBC MarketWatch"),
    ("한국 직접 영향", "Samsung SK Hynix LG Energy Solution Hyundai Korea export policy supply contract Reuters Bloomberg"),
    ("FDA/바이오", "FDA approval complete response letter clinical trial pharma acquisition Reuters Bloomberg CNBC"),
]

TRUSTED = [
    "reuters", "bloomberg", "associated press", "ap news", "cnbc", "marketwatch",
    "politico", "the wall street journal", "wall street journal", "financial times",
    "yonhap", "yonhap news", "the korea economic daily", "korea economic daily",
    "usa today", "panama city news herald", "columbus dispatch",
]
LOCAL_DC_POLICY_TERMS = ["ban", "banned", "banning", "block", "blocked", "city council", "county", "moratorium", "ordinance", "permit", "planning commission", "public hearing", "residents", "township", "vote", "zoning"]
DART_KEYWORDS = ["단일판매", "공급계약", "수주", "유상증자", "전환사채", "신주인수권", "자기주식", "타법인주식", "회사합병", "회사분할", "주요사항보고서", "투자판단", "최대주주", "소송"]
TERMS = ["approval", "ban", "banned", "banning", "block", "blocked", "buyback", "capex", "city council", "contract", "convertible", "copper", "court order", "crl", "data center", "data centers", "dollar", "earnings", "entity list", "export control", "fda", "fed", "final rule", "gold", "guidance", "injunction", "joint venture", "lithium", "loi", "merger", "moratorium", "mou", "natural gas", "offering", "oil", "ordinance", "permit", "planning commission", "public hearing", "real yield", "regulation", "residents", "sanction", "section 301", "section 232", "semiconductor", "supply agreement", "tariff", "tips", "township", "treasury", "uranium", "vote", "won", "yield", "zoning", "fcc", "national security", "covered list", "equipment authorization", "foreign equipment", "inverter", "solar inverter", "robot", "robotics", "drone", "subsidy", "loan", "low-cost loan", "quota", "safeguard", "anti-dumping", "cbam", "steel", "ap1000", "westinghouse", "nuclear reactor", "critical mineral", "critical minerals", *DART_KEYWORDS]

SECTORS = [
    ("반도체/AI", ["ai", "chip", "hbm", "micron", "nvidia", "semiconductor", "tsmc", "asml", "hynix", "samsung", "broadcom", "amd", "intel", "arm", "apple", "microsoft", "oracle"]),
    ("데이터센터/전력망/전력기기", ["data center", "data centers", "city council", "moratorium", "ordinance", "permit", "planning commission", "public hearing", "residents", "township", "zoning", "grid", "power", "ferc", "doe", "server", "network", "cooling"]),
    ("전력망 보안/FCC 장비규제", ["fcc", "national security", "covered list", "equipment authorization", "foreign equipment", "inverter", "solar inverter", "communications supply chain"]),
    ("관세/수출통제", ["export control", "section 301", "section 232", "tariff", "quota", "safeguard", "anti-dumping", "bis", "ustr", "commerce", "ofac", "sanction"]),
    ("EU/한국 정책 영향", ["eu", "european union", "european commission", "south korea", "korean", "korea", "cbam", "steel", "quota", "safeguard", "anti-dumping"]),
    ("방산/정유/해운/지정학", ["hormuz", "iran", "israel", "oil", "red sea", "shipping", "ukraine"]),
    ("원자재/매크로", ["oil", "natural gas", "copper", "lithium", "uranium", "gold", "dollar", "won", "treasury", "yield", "fed", "real yield", "tips"]),
    ("바이오/FDA", ["fda", "clinical", "crl", "pharma"]),
    ("한국 직접 영향", ["samsung", "sk hynix", "korea", "lg energy", "hyundai", *DART_KEYWORDS]),
]


def kst_now() -> dt.datetime:
    return dt.datetime.now(tz=KST)


def clean(value: object) -> str:
    text = html.unescape(str(value or ""))
    text = re.sub(r"<!\[CDATA\[|\]\]>", " ", text)
    text = re.sub(r"<[^>]+>", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def norm(value: object) -> str:
    return clean(value).lower()


def fetch(url: str, timeout: int = 25) -> tuple[str | None, str | None]:
    req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept": "application/rss+xml, application/json, text/html, */*"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            charset = resp.headers.get_content_charset() or "utf-8"
            return resp.read().decode(charset, "replace"), None
    except Exception as exc:
        return None, f"{type(exc).__name__}: {exc}"


def fetch_fred_csv(timeout: int = 60) -> tuple[str | None, str | None]:
    req = urllib.request.Request(FRED_CSV, headers={"User-Agent": "Mozilla/5.0", "Accept": "text/csv,*/*"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return resp.read().decode("utf-8", "replace"), None
    except Exception as exc:
        return None, f"{type(exc).__name__}: {exc}"


def parse_date(value: object) -> dt.datetime | None:
    text = clean(value)
    if not text:
        return None
    try:
        parsed = email.utils.parsedate_to_datetime(text)
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=dt.timezone.utc)
        return parsed.astimezone(KST)
    except Exception:
        pass
    for fmt in ("%Y-%m-%d", "%Y-%m-%dT%H:%M:%SZ", "%Y-%m-%dT%H:%M:%S%z"):
        try:
            parsed = dt.datetime.strptime(text[:25], fmt)
            if parsed.tzinfo is None:
                parsed = parsed.replace(tzinfo=dt.timezone.utc)
            return parsed.astimezone(KST)
        except Exception:
            continue
    return None


def parse_rss(text: str, source: str, layer: str) -> list[dict]:
    try:
        root = ET.fromstring(text)
    except ET.ParseError:
        return []
    rows = []
    for node in root.findall(".//item")[:25]:
        rows.append({
            "source": source,
            "layer": layer,
            "publisher": clean(node.findtext("source")) or source,
            "title": clean(node.findtext("title")),
            "link": clean(node.findtext("link")),
            "summary": clean(node.findtext("description")),
            "published": parse_date(node.findtext("pubDate") or node.findtext("date")),
        })
    return rows


def parse_fr(text: str, source: str) -> list[dict]:
    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        return []
    rows = []
    for row in (data.get("results") or [])[:15]:
        rows.append({
            "source": source,
            "layer": "official",
            "publisher": "Federal Register",
            "title": clean(row.get("title") or row.get("citation")),
            "link": clean(row.get("html_url") or row.get("pdf_url")),
            "summary": clean(" ".join(str(row.get(k, "")) for k in ("type", "document_number", "abstract", "excerpt"))),
            "published": parse_date(row.get("publication_date") or row.get("signing_date")),
        })
    return rows


def google_url(query: str) -> str:
    return "https://news.google.com/rss/search?" + urllib.parse.urlencode({"q": query, "hl": "en-US", "gl": "US", "ceid": "US:en"})


def age_hours(row: dict, now: dt.datetime) -> float | None:
    if not row.get("published"):
        return None
    return (now - row["published"]).total_seconds() / 3600


def fresh(row: dict, now: dt.datetime) -> bool:
    age = age_hours(row, now)
    if age is None:
        return row.get("layer") == "official"
    return -1 <= age <= MAX_AGE_HOURS


def trusted(source: str) -> bool:
    s = norm(source)
    return any(t in s for t in TRUSTED)


def has(text: str, term: str) -> bool:
    escaped = re.escape(term.lower()).replace(r"\ ", r"\s+")
    return re.search(rf"(^|[^a-z0-9]){escaped}($|[^a-z0-9])", text) is not None


def is_local_dc_policy(row: dict) -> bool:
    text = norm(f"{row.get('title')} {row.get('summary')} {row.get('publisher')} {row.get('source')}")
    has_dc = has(text, "data center") or has(text, "data centers")
    has_local_policy = any(has(text, term) for term in LOCAL_DC_POLICY_TERMS)
    return has_dc and has_local_policy


def collect_dart(now: dt.datetime) -> tuple[list[dict], str]:
    if not DART_API_KEY:
        return [], "OpenDART: 접근 제한 (DART_API_KEY 미설정)"
    start = (now.date() - dt.timedelta(days=DART_DAYS_BACK)).strftime("%Y%m%d")
    end = now.date().strftime("%Y%m%d")
    url = "https://opendart.fss.or.kr/api/list.json?" + urllib.parse.urlencode({
        "crtfc_key": DART_API_KEY,
        "bgn_de": start,
        "end_de": end,
        "last_reprt_at": "N",
        "page_no": "1",
        "page_count": "100",
        "sort": "date",
        "sort_mth": "desc",
    })
    text, err = fetch(url, 30)
    if err:
        return [], f"OpenDART: 확인 불가 ({err})"
    try:
        data = json.loads(text or "")
    except json.JSONDecodeError:
        return [], "OpenDART: 확인 불가 (JSON 파싱 실패)"
    if str(data.get("status")) != "000":
        return [], f"OpenDART: 확인 불가/status {data.get('status')} ({data.get('message')})"
    rows = []
    for item in data.get("list", []):
        stock_code = clean(item.get("stock_code"))
        if DART_WATCH_STOCK_CODES and stock_code not in DART_WATCH_STOCK_CODES:
            continue
        report = clean(item.get("report_nm"))
        if not any(keyword in report for keyword in DART_KEYWORDS):
            continue
        receipt = clean(item.get("rcept_no"))
        rows.append({
            "source": "OpenDART",
            "layer": "official",
            "publisher": "OpenDART",
            "title": f"{clean(item.get('corp_name'))} {report}",
            "link": f"https://dart.fss.or.kr/dsaf001/main.do?rcpNo={receipt}" if receipt else "https://dart.fss.or.kr/",
            "summary": f"stock_code={stock_code or 'N/A'} receipt={receipt or 'N/A'}",
            "published": parse_date(clean(item.get("rcept_dt"))),
        })
    return rows, f"OpenDART: {len(data.get('list', []))}건 조회, {len(rows)}건 후보"


def collect_items(now: dt.datetime) -> tuple[list[dict], list[str]]:
    rows, notes = [], []
    for name, url, kind in SOURCES:
        text, err = fetch(url)
        if err:
            notes.append(f"{name}: 확인 불가 ({err})")
            continue
        parsed = parse_fr(text or "", name) if kind == "fr" else parse_rss(text or "", name, "official")
        parsed = [r for r in parsed if fresh(r, now)]
        notes.append(f"{name}: {len(parsed)}건")
        rows.extend(parsed)
    dart_rows, dart_note = collect_dart(now)
    notes.append(dart_note)
    rows.extend(dart_rows)
    for name, query in QUERIES:
        text, err = fetch(google_url(f"{query} when:{max(1, MAX_AGE_HOURS // 24)}d"))
        if err:
            notes.append(f"Trusted news {name}: 확인 불가 ({err})")
            continue
        local_dc_query = "데이터센터" in name
        parsed = [
            r for r in parse_rss(text or "", f"Trusted news {name}", "trusted")
            if fresh(r, now) and (trusted(r.get("publisher") or r.get("source")) or (local_dc_query and is_local_dc_policy(r)))
        ]
        notes.append(f"Trusted news {name}: {len(parsed)}건")
        rows.extend(parsed)
    return rows, notes


def classify(row: dict, now: dt.datetime) -> dict | None:
    title = clean(row.get("title"))
    if len(title) < 8:
        return None
    text = norm(f"{title} {row.get('summary')} {row.get('publisher')} {row.get('source')}")
    local_dc_policy = is_local_dc_policy(row)
    matched = [t for t in TERMS if has(text, t)]
    sectors = [label for label, keys in SECTORS if any(has(text, k) for k in keys)]
    if not matched or not sectors:
        return None
    impacts = []
    if any(t in matched for t in ["contract", "earnings", "guidance", "approval", "supply agreement", "fda", "capex", "oil", "natural gas", "copper", "lithium", "uranium", "inverter", "robot", "robotics", "subsidy", "loan", "low-cost loan", "quota", "safeguard", "anti-dumping", "cbam", "steel", "ap1000", "westinghouse", "nuclear reactor", "단일판매", "공급계약", "수주", "투자판단"]):
        impacts.append("돈 버는 능력")
    if any(t in matched for t in ["ban", "banned", "banning", "block", "blocked", "city council", "dollar", "fed", "gold", "moratorium", "ordinance", "real yield", "regulation", "tariff", "section 232", "quota", "safeguard", "anti-dumping", "national security", "covered list", "tips", "treasury", "won", "yield", "zoning"]):
        impacts.append("할인율")
    if any(t in matched for t in ["buyback", "convertible", "entity list", "export control", "offering", "sanction", "supply", "ban", "inverter", "robotics", "quota", "safeguard", "유상증자", "전환사채", "신주인수권", "자기주식", "최대주주"]):
        impacts.append("수급")
    if any(t in matched for t in ["city council", "court order", "final rule", "injunction", "joint venture", "loi", "merger", "mou", "permit", "planning commission", "public hearing", "residents", "township", "vote", "subsidy", "loan", "low-cost loan", "equipment authorization", "fcc", "타법인주식", "회사합병", "회사분할", "주요사항보고서", "소송"]):
        impacts.append("시간표")
    impacts = list(dict.fromkeys(impacts)) or ["의사결정 영향 제한적"]
    age = age_hours(row, now)
    score = (28 if row.get("layer") == "official" else 0) + (20 if trusted(row.get("publisher") or row.get("source")) else 0) + min(36, len(matched) * 6) + len(impacts) * 10 + len(sectors) * 6
    if age is not None and age <= 12:
        score += 14
    if "데이터센터/전력망/전력기기" in sectors and any(t in matched for t in ["ban", "banned", "banning", "block", "blocked", "moratorium", "city council", "residents", "vote", "zoning"]):
        score += 18
    if local_dc_policy:
        score += 36
    if score < 58:
        return None
    status = "확정" if row.get("layer") == "official" else "공식 확인 전"
    importance = "상" if score >= 100 else "중" if score >= 76 else "하"
    if local_dc_policy:
        interp = "미국 지역 단위 데이터센터 금지·모라토리엄·주민투표는 AI CAPEX의 승인 시간표와 전력망 접속 프리미엄을 바꾸는 조기 신호입니다. 확정 매출은 아니지만 전력기기·전선·냉각·원전/가스·서버 밸류체인의 할인율과 수주 가시성을 점검해야 합니다."
        fail = "시의회 안건·조례·투표 일정 등 공식 후속 확인이 없거나 빅테크 CAPEX/전력기기 수주 전망이 유지되면 지역성 뉴스로 약화"
    elif "데이터센터/전력망/전력기기" in sectors:
        interp = "AI 인프라 병목이 GPU만이 아니라 전력·입지·주민수용성으로 번지는지 보는 재료입니다. 한국장에서는 전력기기와 데이터센터 밸류체인 프리미엄 지속성을 점검해야 합니다."
        fail = "전력기기·전선·원전·냉각·서버 밸류체인이 따라오지 않거나 공식 문서가 확인되지 않으면 재료 약화"
    elif "반도체/AI" in sectors:
        interp = "AI·메모리 수요 또는 공급 제한을 건드릴 수 있어 한국 반도체 대형주와 소부장 수급에 연결됩니다. 해외 티커 반응으로 이미 반영됐는지 재확인이 필요합니다."
        fail = "SOX/MU/NVDA/메모리 가격이 반응하지 않거나 가이던스가 수요 둔화를 시사하면 실패"
    elif "원자재/매크로" in sectors:
        interp = "원자재 가격·달러·실질금리는 한국장 이익 추정과 할인율을 동시에 흔드는 축입니다. 실제 가격 지표와 환율이 동행하는지 06:50 수치에서 재확인해야 합니다."
        fail = "유가·금리·달러·원화·원자재 가격이 동행하지 않거나 하루짜리 헤드라인에 그치면 재료 약화"
    else:
        interp = "돈 버는 능력, 할인율, 수급, 시간표 중 하나를 바꿀 수 있는 후보입니다. 원문 조건과 가격 반응을 장전 수치에서 재확인해야 합니다."
        fail = "관련 해외 티커·원자재·금리·환율·한국 수급이 동행하지 않으면 단발성 뉴스"
    return {
        "score": score,
        "importance": importance,
        "status": status,
        "news": title,
        "publisher": row.get("publisher") or row.get("source"),
        "source": row.get("source"),
        "link": row.get("link") or "",
        "published": row["published"].isoformat(timespec="minutes") if row.get("published") else "확인 불가",
        "impacts": impacts,
        "paths": ["이익" if x == "돈 버는 능력" else "할인율" if x == "할인율" else "수급" if x == "수급" else "정책 타임라인" for x in impacts],
        "sectors": sectors,
        "matched": matched[:10],
        "local_dc_policy": local_dc_policy,
        "reflection": "낮음" if age is not None and age <= 6 else "중간" if age is None or age <= 24 else "높음",
        "counter": "제목·요약 기반 1차 감지라 원문 세부조건과 공식 문서 확인 전 과대해석 가능" if status != "확정" else "시행일, 적용 대상, 금액, 기간, 독점성, 매출 인식 조건 확인 전 영향이 제한될 수 있음",
        "interpretation": interp,
        "failed_signal": fail,
        "korea_basis": "예고된 이벤트의 공식화" if status == "확정" else "외신 확산",
    }


def collect_dfii10() -> dict:
    if FRED_API_KEY:
        url = "https://api.stlouisfed.org/fred/series/observations?" + urllib.parse.urlencode({"series_id": "DFII10", "file_type": "json", "sort_order": "desc", "limit": "10", "api_key": FRED_API_KEY})
        text, err = fetch(url, 30)
        if not err and text:
            for row in json.loads(text).get("observations", []):
                if row.get("value") and row.get("value") != ".":
                    return {"source": "FRED API DFII10", "status": "확인됨", "reference": row.get("date"), "value": float(row.get("value")), "error": None}
    text, err = fetch_fred_csv(60)
    if err or not text:
        return {"source": FRED_CSV, "status": "확인 불가", "reference": "확인 불가", "value": None, "error": err}
    for row in reversed(list(csv.DictReader(text.splitlines()))):
        if row.get("DFII10") and row.get("DFII10") != ".":
            return {"source": FRED_CSV, "status": "확인됨", "reference": row.get("observation_date"), "value": float(row.get("DFII10")), "error": None}
    return {"source": FRED_CSV, "status": "확인 불가", "reference": "확인 불가", "value": None, "error": "latest non-empty row not found"}


def collect_te() -> dict:
    text, err = fetch(TE_URL)
    if err or not text:
        return {"source": TE_URL, "status": "확인 불가", "reference": "확인 불가", "value": None, "error": err}
    body = clean(text)
    row = re.search(r"US\s+10Y\s+TIPS\s+(-?\d+(?:\.\d+)?)\s+(-?\d+(?:\.\d+)?)%\s+(-?\d+(?:\.\d+)?)%\s+(-?\d+(?:\.\d+)?)%\s+([A-Za-z]{3}/\d{1,2})", body, re.I)
    meta = re.search(r"10 Year TIPS Yield.{0,150}?(-?\d+(?:\.\d+)?)\s*(?:%|percent)\s+on\s+([A-Za-z]+ \d{1,2}, \d{4})", body, re.I)
    if row:
        return {"source": TE_URL, "status": "확인됨", "reference": row.group(5), "value": float(row.group(1)), "meta_value": float(meta.group(1)) if meta else None, "meta_reference": meta.group(2) if meta else None, "error": None}
    if meta:
        return {"source": TE_URL, "status": "확인됨", "reference": meta.group(2), "value": float(meta.group(1)), "error": None}
    return {"source": TE_URL, "status": "확인 불가", "reference": "확인 불가", "value": None, "error": "pattern not found"}


def real_yield_note(fred: dict, te: dict) -> str:
    if fred.get("value") is None or te.get("value") is None:
        return "FRED DFII10 또는 Trading Economics 10Y TIPS 중 하나가 확인되지 않아 할인율 교차확인 불완전"
    mismatch = abs(float(fred["value"]) - float(te["value"])) >= 0.03 or str(fred.get("reference")) != str(te.get("reference"))
    state = "지연/불일치 있음" if mismatch else "교차확인됨"
    return f"{state}: FRED DFII10 {fred['value']:.2f}%({fred.get('reference')}), Trading Economics 10Y TIPS {te['value']:.2f}%({te.get('reference')})"


def related(alert: dict, fred: dict, te: dict) -> str:
    out = []
    if "반도체/AI" in alert["sectors"]:
        out += ["NVDA", "MU", "AVGO", "AMD", "TSM", "ASML", "SOX"]
    if "데이터센터/전력망/전력기기" in alert["sectors"]:
        out += ["VRT", "ETN", "GEV", "CEG", "SMH"]
    if "전력망 보안/FCC 장비규제" in alert["sectors"]:
        out += ["FSLR", "ENPH", "SEDG", "VRT", "ETN", "GEV"]
    if "EU/한국 정책 영향" in alert["sectors"]:
        out += ["EU 정책문서", "철강/배터리/반도체/조선 수출주", "EUR/KRW"]
    if "방산/정유/해운/지정학" in alert["sectors"]:
        out += ["WTI", "Brent", "XLE", "운임"]
    if "원자재/매크로" in alert["sectors"]:
        out += ["미국 10년물", "DXY", "USD/KRW", "WTI", "Henry Hub", "Copper", "Lithium", "Uranium", "Gold"]
    if "할인율" in alert["impacts"]:
        out += [f"DFII10 {fred.get('value') if fred.get('value') is not None else '확인 불가'}", f"TE 10Y TIPS {te.get('value') if te.get('value') is not None else '확인 불가'}", "IWM/SPY 재확인"]
    return ", ".join(dict.fromkeys(out)) or "확인 가능한 직접 티커 없음"


def render_alert(alert: dict, idx: int, now: dt.datetime, fred: dict, te: dict) -> str:
    return "\n".join([
        f"## {idx}. [{alert['importance']} | {alert['status']}]",
        f"- `뉴스`: {alert['news']}",
        f"- `한국장 기준`: {alert['korea_basis']}",
        f"- `타임라인`: 최초 빌드업: 확인 불가 / 공식·원천 시각: {alert['published']} / 한국 투자자 확산: {now:%Y-%m-%d %H:%M KST} 조회 기준",
        f"- `출처`: [{alert['publisher']}]({alert['link']}) · 조회 {now:%Y-%m-%d %H:%M KST}",
        f"- `의사결정 영향`: {', '.join(alert['impacts'])}",
        f"- `영향 경로`: {', '.join(alert['paths'])}",
        f"- `영향 섹터`: {', '.join(alert['sectors'])}",
        f"- `관련 해외 티커/지표`: {related(alert, fred, te)}",
        f"- `반영 가능성`: {alert['reflection']}",
        f"- `반대 근거`: {alert['counter']}",
        f"- `해석`: {alert['interpretation']}",
        f"- `실패 신호`: {alert['failed_signal']}",
        "",
    ])


def render_report(alerts: list[dict], notes: list[str], fred: dict, te: dict, now: dt.datetime) -> str:
    title = f"📰 GAMEJOA 장전 핵심 뉴스 레이더 · {now:%Y년 %m월 %d일} · 06:30"
    lines = [
        title, "",
        f"조회 기준: {now:%Y-%m-%d %H:%M KST}. GitHub Actions 외부 러너 기준이며, 로컬 Codex/PC 절전 상태와 무관하게 실행됩니다.", "",
        "### 자료 처리 현황표",
        "| 항목 | 조회 시각 | 직접 확인 | 상태 |", "|---|---:|---:|---|",
        f"| 장전 뉴스 원천 | {now:%H:%M KST} | {sum('확인 불가' not in n for n in notes)}개 원천 | {' / '.join(notes[:5])} |",
        f"| FRED DFII10 | {now:%H:%M KST} | {'예' if fred.get('value') is not None else '아니오'} | {fred.get('status')} · {fred.get('reference')} |",
        f"| Trading Economics 10Y TIPS | {now:%H:%M KST} | {'예' if te.get('value') is not None else '아니오'} | {te.get('status')} · {te.get('reference')} |",
        "", f"할인율 교차확인: {real_yield_note(fred, te)}", "",
    ]
    if alerts:
        for idx, alert in enumerate(alerts[:7], 1):
            lines.append(render_alert(alert, idx, now, fred, te))
    else:
        lines += ["장전 고충격 뉴스 직접 확인 없음", "", "감정성 뉴스로 제외: 공식/신뢰 소스에서 돈 버는 능력, 할인율, 수급, 시간표를 명확히 바꾸는 후보가 직접 확인되지 않은 항목.", ""]
    top = alerts[0]["news"] if alerts else "장전 고충격 뉴스 직접 확인 없음"
    changed = ", ".join(alerts[0]["impacts"]) if alerts else "명확한 변화 없음"
    lines += [
        "💡 06:30 장전 뉴스 코멘트",
        f"오늘 1순위 체크는 `{top}`입니다. 오늘 가장 크게 바뀐 축은 `{changed}`이며, 한국장에서는 관련 해외 티커 반응과 국내 수급 확산 여부를 먼저 보겠습니다.",
        f"할인율은 FRED DFII10과 Trading Economics 10 Year TIPS Yield를 함께 확인했습니다: {real_yield_note(fred, te)}.",
        "06:50 투자기상도에서 수치·수급·테마와 재확인 필요.", "",
        "투자 조언이 아닌 참고용 뉴스 브리핑입니다.", "",
        "주요 출처:", *[f"- {n}" for n in notes[:18]], f"- FRED DFII10: {FRED_CSV}", f"- Trading Economics 10Y TIPS: {TE_URL}",
    ]
    return "\n".join(lines).strip() + "\n"


def send_telegram(text: str) -> None:
    token = os.getenv("TELEGRAM_BOT_TOKEN", "").strip()
    chat_id = os.getenv("TELEGRAM_CHAT_ID", "").strip()
    if not token or not chat_id:
        print("Telegram: TELEGRAM_BOT_TOKEN or TELEGRAM_CHAT_ID missing")
        return
    repo, run_id = os.getenv("GITHUB_REPOSITORY", ""), os.getenv("GITHUB_RUN_ID", "")
    suffix = f"\n\n전체 보고서: https://github.com/{repo}/actions/runs/{run_id}" if repo and run_id else ""
    body = urllib.parse.urlencode({"chat_id": chat_id, "text": (text[: TELEGRAM_LIMIT - len(suffix) - 1] + suffix)[:TELEGRAM_LIMIT], "disable_web_page_preview": "true"}).encode("utf-8")
    req = urllib.request.Request(f"https://api.telegram.org/bot{token}/sendMessage", data=body, method="POST")
    with urllib.request.urlopen(req, timeout=25) as resp:
        resp.read()
    print("Telegram: sent")


def print_utf8(text: str) -> None:
    try:
        sys.stdout.write(text)
    except UnicodeEncodeError:
        sys.stdout.buffer.write(text.encode("utf-8", "replace"))


def main() -> int:
    now = kst_now()
    rows, notes = collect_items(now)
    alerts = [a for a in (classify(r, now) for r in rows if fresh(r, now)) if a]
    alerts.sort(key=lambda a: (-a["score"], a["published"]))
    deduped, seen = [], set()
    for alert in alerts:
        key = (norm(alert["news"]), norm(alert["publisher"]), alert["published"][:10])
        if key in seen:
            continue
        seen.add(key)
        deduped.append(alert)
        if len(deduped) >= 7:
            break
    local_dc_candidates = [a for a in alerts if a.get("local_dc_policy")]
    for candidate in local_dc_candidates:
        local_count = sum(1 for a in deduped if a.get("local_dc_policy"))
        if local_count >= min(2, len(local_dc_candidates)):
            break
        ckey = (norm(candidate["news"]), norm(candidate["publisher"]), candidate["published"][:10])
        if ckey in seen:
            continue
        if len(deduped) < 7:
            deduped.append(candidate)
            seen.add(ckey)
            continue
        for idx in range(len(deduped) - 1, -1, -1):
            if not deduped[idx].get("local_dc_policy"):
                old = deduped[idx]
                seen.discard((norm(old["news"]), norm(old["publisher"]), old["published"][:10]))
                deduped[idx] = candidate
                seen.add(ckey)
                break
    deduped.sort(key=lambda a: (-a["score"], a["published"]))
    fred, te = collect_dfii10(), collect_te()
    report = render_report(deduped, notes, fred, te, now)
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "gamejoa_preopen_news_radar.md").write_text(report, encoding="utf-8")
    (OUT / "gamejoa_preopen_news_radar_title.txt").write_text(report.splitlines()[0] + "\n", encoding="utf-8")
    (OUT / "gamejoa_preopen_news_radar.json").write_text(json.dumps({"query_time_kst": now.isoformat(timespec="seconds"), "alerts": deduped, "source_notes": notes, "fred_dfii10": fred, "tradingeconomics_tips": te}, ensure_ascii=False, indent=2, default=str) + "\n", encoding="utf-8")
    print_utf8(report)
    if os.getenv("TELEGRAM_DRY_RUN", "").lower() in {"1", "true", "yes", "y"}:
        print("Telegram: dry run")
        return 0
    if os.getenv("SEND_TELEGRAM", "").lower() in {"1", "true", "yes", "y"}:
        send_telegram(report)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
