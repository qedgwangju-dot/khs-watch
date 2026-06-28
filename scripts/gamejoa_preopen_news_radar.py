#!/usr/bin/env python3
"""GAMEJOA 06:30 KST preopen high-impact news radar for GitHub Actions."""

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
OUT_DIR = ROOT / "out"
OUT_MD = OUT_DIR / "gamejoa_preopen_news_radar.md"
OUT_JSON = OUT_DIR / "gamejoa_preopen_news_radar.json"
OUT_TITLE = OUT_DIR / "gamejoa_preopen_news_radar_title.txt"
KST = ZoneInfo("Asia/Seoul")
FRED_DFII10_CSV = "https://fred.stlouisfed.org/graph/fredgraph.csv?id=DFII10"
TE_TIPS_URL = "https://tradingeconomics.com/united-states/10-year-tips-yield"
SEC_USER_AGENT = os.getenv("SEC_USER_AGENT", "GAMEJOA-preopen-radar contact=please-set-secret")
FRED_API_KEY = os.getenv("FRED_API_KEY", "").strip()
DART_API_KEY = os.getenv("DART_API_KEY", "").strip()
MAX_AGE_HOURS = int(os.getenv("RADAR_MAX_AGE_HOURS", "48"))
DART_DAYS_BACK = int(os.getenv("DART_DAYS_BACK", "3"))
TELEGRAM_TEXT_LIMIT = 4096

OFFICIAL_SOURCES = [
    ("FERC news", "https://www.ferc.gov/news-events/news/rss.xml", "rss"),
    ("DOE news", "https://www.energy.gov/rss.xml", "rss"),
    ("Commerce news", "https://www.commerce.gov/news/rss.xml", "rss"),
    ("BIS news", "https://www.bis.doc.gov/index.php/newsroom/news-releases?format=feed&type=rss", "rss"),
    ("SEC press releases", "https://www.sec.gov/news/pressreleases.rss", "rss"),
    ("FTC press releases", "https://www.ftc.gov/news-events/news/press-releases/rss.xml", "rss"),
    ("Federal Register data centers", "https://www.federalregister.gov/api/v1/documents.json?conditions%5Bterm%5D=data%20center%20power%20grid&order=newest&per_page=15", "fr"),
    ("Federal Register export controls", "https://www.federalregister.gov/api/v1/documents.json?conditions%5Bterm%5D=semiconductor%20export%20controls&order=newest&per_page=15", "fr"),
    ("Federal Register tariffs", "https://www.federalregister.gov/api/v1/documents.json?conditions%5Bterm%5D=tariff%20section%20301&order=newest&per_page=15", "fr"),
    ("Federal Register energy permits", "https://www.federalregister.gov/api/v1/documents.json?conditions%5Bterm%5D=energy%20permit%20final%20rule&order=newest&per_page=15", "fr"),
]

TRUSTED_QUERIES = [
    ("AI/power grid", "FERC DOE AI data center power grid nuclear energy policy Reuters Bloomberg CNBC"),
    ("Local data-center bans", '"data center" ban moratorium city council residents vote zoning power Reuters Bloomberg AP USA Today'),
    ("Semiconductor/AI", "Nvidia Micron Broadcom AMD TSMC ASML AI chip guidance supply agreement Reuters Bloomberg MarketWatch"),
    ("Export controls/tariffs", "US Commerce BIS export controls tariffs China semiconductor Reuters Bloomberg AP"),
    ("Geopolitics/energy", "Iran Israel Hormuz Red Sea oil shipping sanctions Reuters Bloomberg AP CNBC MarketWatch"),
    ("Korea direct", "Samsung SK Hynix LG Energy Solution Hyundai Korea export policy supply contract Reuters Bloomberg"),
    ("FDA/biotech", "FDA approval complete response letter clinical trial pharma acquisition Reuters Bloomberg CNBC"),
]

TRUSTED_SOURCE_TERMS = [
    "reuters", "bloomberg", "associated press", "ap news", "wall street journal",
    "financial times", "cnbc", "marketwatch", "politico", "usa today",
    "panama city news herald", "columbus dispatch",
]

DART_KEYWORDS = [
    "단일판매", "공급계약", "수주", "유상증자", "무상증자", "전환사채", "신주인수권", "교환사채",
    "자기주식", "타법인주식", "영업양수", "영업양도", "영업정지", "회사합병", "회사분할",
    "최대주주", "소송", "투자판단", "주요사항보고서", "불성실공시", "조회공시",
]

HIGH_TERMS = [
    "approval", "approved", "ban", "blocked", "capex", "city council", "complete response letter",
    "contract", "court order", "crl", "customer agreement", "directive", "earnings", "entity list",
    "executive order", "export control", "export controls", "fda approves", "final rule", "guidance",
    "injunction", "joint venture", "license", "merger", "moratorium", "permit", "record of decision",
    "regulation", "rejection", "restriction", "ruling", "sanction", "sanctions", "section 301",
    "semiconductor", "supply agreement", "tariff", "tariffs", "vote", "zoning", *DART_KEYWORDS,
]

SECTORS = [
    ("반도체/AI", ["ai", "asml", "broadcom", "chip", "hbm", "micron", "nvidia", "semiconductor", "tsmc"]),
    ("데이터센터/전력망/전력기기", ["city council", "data center", "doe", "ferc", "grid", "moratorium", "power", "zoning"]),
    ("관세/수출통제", ["bis", "export control", "section 301", "tariff", "ustr"]),
    ("방산/정유/해운/지정학", ["defense", "hormuz", "iran", "israel", "oil", "red sea", "russia", "shipping", "ukraine"]),
    ("바이오/FDA", ["clinical", "crl", "drug", "fda", "pharma"]),
    ("한국 직접 공시/정책", ["samsung", "sk hynix", "korea", "lg energy", "hyundai", *DART_KEYWORDS]),
]

IMPACT_RULES = [
    ("돈 버는 능력", "이익", ["approval", "capex", "contract", "earnings", "fda approves", "guidance", "joint venture", "license", "merger", "revenue", "supply agreement", "공급계약", "수주"]),
    ("할인율", "할인율", ["ban", "blocked", "city council", "executive order", "final rule", "moratorium", "real yield", "regulation", "restriction", "tariff", "zoning"]),
    ("수급", "수급", ["adr", "buyback", "convertible", "entity list", "export control", "offering", "restriction", "sanction", "shortage", "supply", "유상증자", "전환사채", "자기주식"]),
    ("시간표", "정책 타임라인", ["city council", "comment deadline", "court order", "effective date", "fda", "hearing", "injunction", "moratorium", "permit", "record of decision", "ruling", "vote"]),
]


def now_kst() -> dt.datetime:
    return dt.datetime.now(tz=KST)


def clean(value) -> str:
    value = html.unescape(str(value or ""))
    value = re.sub(r"<!\[CDATA\[|\]\]>", " ", value)
    value = re.sub(r"<[^>]+>", " ", value)
    return re.sub(r"\s+", " ", value).strip()


def norm(value) -> str:
    return clean(value).lower()


def fetch(url: str, timeout: int = 25) -> tuple[str | None, str | None]:
    req = urllib.request.Request(url, headers={"User-Agent": SEC_USER_AGENT, "Accept": "application/rss+xml, application/json, text/html, */*"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            charset = resp.headers.get_content_charset() or "utf-8"
            return resp.read().decode(charset, "replace"), None
    except Exception as exc:
        return None, f"{type(exc).__name__}: {exc}"


def parse_date(value) -> dt.datetime | None:
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


def google_rss(query: str) -> str:
    return "https://news.google.com/rss/search?" + urllib.parse.urlencode({"q": query, "hl": "en-US", "gl": "US", "ceid": "US:en"})


def parse_rss(text: str, source: str, layer: str) -> list[dict]:
    try:
        root = ET.fromstring(text)
    except ET.ParseError:
        return []
    out = []
    for node in root.findall(".//item")[:25]:
        out.append({
            "source": source,
            "layer": layer,
            "publisher": clean(node.findtext("source")) or source,
            "title": clean(node.findtext("title")),
            "link": clean(node.findtext("link")),
            "summary": clean(node.findtext("description")),
            "published": parse_date(node.findtext("pubDate") or node.findtext("date")),
        })
    return out


def parse_fr(text: str, source: str) -> list[dict]:
    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        return []
    out = []
    for row in (data.get("results") or [])[:15]:
        out.append({
            "source": source,
            "layer": "official",
            "publisher": "Federal Register",
            "title": clean(row.get("title") or row.get("citation")),
            "link": clean(row.get("html_url") or row.get("pdf_url")),
            "summary": clean(" ".join(str(row.get(k, "")) for k in ("type", "document_number", "abstract", "excerpt"))),
            "published": parse_date(row.get("publication_date") or row.get("signing_date")),
        })
    return out


def age_hours(item: dict, now: dt.datetime) -> float | None:
    if not item.get("published"):
        return None
    return (now - item["published"]).total_seconds() / 3600


def fresh(item: dict, now: dt.datetime) -> bool:
    age = age_hours(item, now)
    if age is None:
        return item.get("layer") == "official"
    return -1 <= age <= MAX_AGE_HOURS


def trusted_source(source: str) -> bool:
    s = norm(source)
    return any(term in s for term in TRUSTED_SOURCE_TERMS)


def has_term(text: str, term: str) -> bool:
    t = norm(term)
    if re.search(r"[가-힣]", t):
        return t in text
    return re.search(rf"(^|[^a-z0-9]){re.escape(t).replace('\\ ', r'\\s+')}($|[^a-z0-9])", text) is not None


def collect_dart(now: dt.datetime) -> tuple[list[dict], str]:
    if not DART_API_KEY:
        return [], "OpenDART latest disclosures: 접근 제한 (DART_API_KEY 미설정)"
    start = (now.date() - dt.timedelta(days=DART_DAYS_BACK)).strftime("%Y%m%d")
    end = now.date().strftime("%Y%m%d")
    url = "https://opendart.fss.or.kr/api/list.json?" + urllib.parse.urlencode({
        "crtfc_key": DART_API_KEY, "bgn_de": start, "end_de": end, "last_reprt_at": "N", "page_no": "1", "page_count": "100", "sort": "date", "sort_mth": "desc"
    })
    text, error = fetch(url)
    if error:
        return [], f"OpenDART latest disclosures: 확인 불가 ({error})"
    try:
        data = json.loads(text or "")
    except json.JSONDecodeError:
        return [], "OpenDART latest disclosures: 확인 불가 (JSON 파싱 실패)"
    if str(data.get("status")) != "000":
        return [], f"OpenDART latest disclosures: 확인 불가/status {data.get('status')} ({data.get('message')})"
    out = []
    for row in data.get("list", []):
        report = clean(row.get("report_nm"))
        if not any(k in report for k in DART_KEYWORDS):
            continue
        rcp = clean(row.get("rcept_no"))
        out.append({
            "source": "OpenDART latest disclosures", "layer": "official", "publisher": "OpenDART",
            "title": f"{clean(row.get('corp_name'))} {report}",
            "link": f"https://dart.fss.or.kr/dsaf001/main.do?rcpNo={rcp}" if rcp else "https://dart.fss.or.kr/",
            "summary": f"DART filing stock_code={clean(row.get('stock_code')) or 'N/A'} receipt={rcp or 'N/A'}",
            "published": parse_date(clean(row.get("rcept_dt"))),
        })
    return out, f"OpenDART latest disclosures: {len(data.get('list', []))}건 조회, {len(out)}건 후보"


def collect_items(now: dt.datetime) -> tuple[list[dict], list[str]]:
    items, notes = [], []
    for name, url, kind in OFFICIAL_SOURCES:
        text, error = fetch(url)
        if error:
            notes.append(f"{name}: 확인 불가 ({error})")
            continue
        parsed = parse_fr(text or "", name) if kind == "fr" else parse_rss(text or "", name, "official")
        parsed = [x for x in parsed if fresh(x, now)]
        notes.append(f"{name}: {len(parsed)}건")
        items.extend(parsed)
    for name, query in TRUSTED_QUERIES:
        text, error = fetch(google_rss(f"{query} when:{max(1, MAX_AGE_HOURS // 24)}d"))
        if error:
            notes.append(f"Trusted news {name}: 확인 불가 ({error})")
            continue
        parsed = [x for x in parse_rss(text or "", f"Trusted news {name}", "trusted_news") if fresh(x, now) and trusted_source(x.get("publisher") or x.get("source"))]
        notes.append(f"Trusted news {name}: {len(parsed)}건")
        items.extend(parsed)
    dart_items, dart_note = collect_dart(now)
    notes.append(dart_note)
    items.extend([x for x in dart_items if fresh(x, now)])
    return items, notes


def classify(item: dict, now: dt.datetime) -> dict | None:
    title = clean(item.get("title"))
    if len(title) < 8:
        return None
    text = norm(f"{title} {item.get('summary')} {item.get('source')} {item.get('publisher')}")
    terms = [t for t in HIGH_TERMS if has_term(text, t)]
    if not terms:
        return None
    sectors = [label for label, terms2 in SECTORS if any(has_term(text, t) for t in terms2)]
    if not sectors:
        return None
    impacts, paths = [], []
    for impact, path, terms2 in IMPACT_RULES:
        if any(has_term(text, t) for t in terms2):
            impacts.append(impact); paths.append(path)
    impacts = list(dict.fromkeys(impacts)) or ["의사결정 영향 제한적"]
    paths = list(dict.fromkeys(paths)) or ["정책 타임라인"]
    age = age_hours(item, now)
    score = (28 if item.get("layer") == "official" else 0) + (20 if trusted_source(item.get("publisher") or item.get("source")) else 0) + min(36, len(terms) * 6) + len(impacts) * 10 + len(sectors) * 6
    if age is not None and age <= 12:
        score += 14
    if "데이터센터/전력망/전력기기" in sectors and any(t in terms for t in ["ban", "moratorium", "city council", "vote", "zoning"]):
        score += 18
    if score < 58:
        return None
    status = "확정" if item.get("layer") == "official" else "공식 확인 전"
    importance = "상" if score >= 100 else "중" if score >= 76 else "하"
    published = item["published"].isoformat(timespec="minutes") if item.get("published") else "확인 불가"
    reflection = "중간. 06:50 투자기상도에서 가격·수급 반영 재확인 필요" if age is None or age <= 24 else "높음. 이미 알려졌을 가능성 큼"
    if age is not None and age <= 6:
        reflection = "낮음. 한국 투자자 확산 전이면 장전 수급 반응이 남아 있을 수 있음"
    counter = "제목·요약 기반 1차 감지라 원문 세부조건과 공식 문서 확인 전 과대해석 가능" if status != "확정" else "시행일, 적용 대상, 금액, 기간, 독점성, 매출 인식 조건 확인 전 영향이 제한될 수 있음"
    if "데이터센터/전력망/전력기기" in sectors:
        failed = "전력기기·전선·원전·냉각·서버 밸류체인이 따라오지 않거나 공식 문서가 확인되지 않으면 재료 약화"
        interpretation = "AI 인프라 병목이 GPU만이 아니라 전력·입지·주민수용성으로 번지는지 보는 재료입니다. 한국장에서는 전력기기와 데이터센터 밸류체인 프리미엄 지속성을 점검해야 합니다."
    elif "반도체/AI" in sectors:
        failed = "SOX/MU/NVDA/메모리 가격이 반응하지 않거나 가이던스가 수요 둔화를 시사하면 실패"
        interpretation = "AI·메모리 수요 또는 공급 제한을 건드릴 수 있어 한국 반도체 대형주와 소부장 수급에 연결됩니다. 해외 티커 반응으로 이미 반영됐는지 재확인이 필요합니다."
    else:
        failed = "관련 해외 티커·원자재·금리·환율·한국 수급이 동행하지 않으면 단발성 뉴스"
        interpretation = "돈 버는 능력, 할인율, 수급, 시간표 중 하나를 바꿀 수 있는 후보입니다. 원문 조건과 가격 반응을 장전 수치에서 재확인해야 합니다."
    return {
        "score": score, "importance": importance, "status": status, "news": title, "source": item.get("source"), "publisher": item.get("publisher") or item.get("source"),
        "link": item.get("link") or "", "published_kst": published, "age_hours": age, "matched_terms": terms[:10], "impacts": impacts, "paths": paths,
        "sectors": sectors, "reflection": reflection, "counter": counter, "failed_signal": failed, "interpretation": interpretation,
        "korea_basis": "예고된 이벤트의 공식화" if status == "확정" else "외신 확산",
    }


def collect_dfii10() -> dict:
    if FRED_API_KEY:
        url = "https://api.stlouisfed.org/fred/series/observations?" + urllib.parse.urlencode({"series_id": "DFII10", "file_type": "json", "sort_order": "desc", "limit": "10", "api_key": FRED_API_KEY})
        text, error = fetch(url, 30)
        if not error and text:
            try:
                for row in json.loads(text).get("observations", []):
                    if row.get("value") and row.get("value") != ".":
                        return {"source": "FRED API DFII10", "status": "확인됨", "reference": row.get("date"), "value": float(row.get("value")), "error": None}
            except Exception as exc:
                return {"source": "FRED API DFII10", "status": "확인 불가", "reference": "확인 불가", "value": None, "error": str(exc)}
    text, error = fetch(FRED_DFII10_CSV, 60)
    if error or not text:
        return {"source": FRED_DFII10_CSV, "status": "확인 불가", "reference": "확인 불가", "value": None, "error": error}
    for row in reversed(list(csv.DictReader(text.splitlines()))):
        if row.get("DFII10") and row.get("DFII10") != ".":
            return {"source": FRED_DFII10_CSV, "status": "확인됨", "reference": row.get("observation_date"), "value": float(row.get("DFII10")), "error": None}
    return {"source": FRED_DFII10_CSV, "status": "확인 불가", "reference": "확인 불가", "value": None, "error": "latest non-empty row not found"}


def collect_te() -> dict:
    text, error = fetch(TE_TIPS_URL)
    if error or not text:
        return {"source": TE_TIPS_URL, "status": "확인 불가", "reference": "확인 불가", "value": None, "error": error}
    body = clean(text)
    row = re.search(r"US\s+10Y\s+TIPS\s+(-?\d+(?:\.\d+)?)\s+(-?\d+(?:\.\d+)?)%\s+(-?\d+(?:\.\d+)?)%\s+(-?\d+(?:\.\d+)?)%\s+([A-Za-z]{3}/\d{1,2})", body, re.I)
    meta = re.search(r"10 Year TIPS Yield.{0,150}?(-?\d+(?:\.\d+)?)\s*(?:%|percent)\s+on\s+([A-Za-z]+ \d{1,2}, \d{4})", body, re.I)
    if row:
        return {"source": TE_TIPS_URL, "status": "확인됨", "reference": row.group(5), "value": float(row.group(1)), "meta_value": float(meta.group(1)) if meta else None, "meta_reference": meta.group(2) if meta else None, "error": None}
    if meta:
        return {"source": TE_TIPS_URL, "status": "확인됨", "reference": meta.group(2), "value": float(meta.group(1)), "error": None}
    return {"source": TE_TIPS_URL, "status": "확인 불가", "reference": "확인 불가", "value": None, "error": "pattern not found"}


def real_yield_note(fred: dict, te: dict) -> str:
    if fred.get("value") is None or te.get("value") is None:
        return "FRED DFII10 또는 Trading Economics 10Y TIPS 중 하나가 확인되지 않아 할인율 교차확인 불완전"
    mismatch = abs(float(fred["value"]) - float(te["value"])) >= 0.03 or str(fred.get("reference")) != str(te.get("reference"))
    state = "지연/불일치 있음" if mismatch else "교차확인됨"
    return f"{state}: FRED DFII10 {fred['value']:.2f}%({fred.get('reference')}), Trading Economics 10Y TIPS {te['value']:.2f}%({te.get('reference')})"


def tickers(alert: dict, fred: dict, te: dict) -> str:
    out = []
    if "반도체/AI" in alert["sectors"]:
        out += ["NVDA", "MU", "AVGO", "AMD", "TSM", "ASML", "SOX"]
    if "데이터센터/전력망/전력기기" in alert["sectors"]:
        out += ["VRT", "ETN", "GEV", "CEG", "SMH"]
    if "방산/정유/해운/지정학" in alert["sectors"]:
        out += ["WTI", "Brent", "XLE", "운임"]
    if "할인율" in alert["impacts"]:
        out += [f"DFII10 {fred.get('value') if fred.get('value') is not None else '확인 불가'}", f"TE 10Y TIPS {te.get('value') if te.get('value') is not None else '확인 불가'}", "IWM/SPY 재확인"]
    return ", ".join(dict.fromkeys(map(str, out))) or "확인 가능한 직접 티커 없음"


def render_alert(alert: dict, idx: int, now: dt.datetime, fred: dict, te: dict) -> str:
    return "\n".join([
        f"## {idx}. [{alert['importance']} | {alert['status']}]",
        f"- `뉴스`: {alert['news']}",
        f"- `한국장 기준`: {alert['korea_basis']}",
        f"- `타임라인`: 최초 빌드업: 확인 불가 / 공식·원천 시각: {alert['published_kst']} / 한국 투자자 확산: {now:%Y-%m-%d %H:%M KST} 조회 기준",
        f"- `출처`: [{alert['publisher']}]({alert['link']}) · 조회 {now:%Y-%m-%d %H:%M KST}",
        f"- `의사결정 영향`: {', '.join(alert['impacts'])}",
        f"- `영향 경로`: {', '.join(alert['paths'])}",
        f"- `영향 섹터`: {', '.join(alert['sectors'])}",
        f"- `관련 해외 티커/지표`: {tickers(alert, fred, te)}",
        f"- `반영 가능성`: {alert['reflection']}",
        f"- `반대 근거`: {alert['counter']}",
        f"- `해석`: {alert['interpretation']}",
        f"- `실패 신호`: {alert['failed_signal']}", "",
    ])


def render_report(alerts: list[dict], notes: list[str], fred: dict, te: dict, now: dt.datetime) -> str:
    title = f"📰 GAMEJOA 장전 핵심 뉴스 레이더 · {now:%Y년 %m월 %d일} · 06:30"
    lines = [title, "", f"조회 기준: {now:%Y-%m-%d %H:%M KST}. GitHub Actions 외부 러너 기준이며, 로컬 Codex/PC 절전 상태와 무관하게 실행됩니다.", "", "### 자료 처리 현황표", "| 항목 | 조회 시각 | 직접 확인 | 상태 |", "|---|---:|---:|---|", f"| 장전 뉴스 원천 | {now:%H:%M KST} | {sum('확인 불가' not in n for n in notes)}개 원천 | {' / '.join(notes[:5])} |", f"| FRED DFII10 | {now:%H:%M KST} | {'예' if fred.get('value') is not None else '아니오'} | {fred.get('status')} · {fred.get('reference')} |", f"| Trading Economics 10Y TIPS | {now:%H:%M KST} | {'예' if te.get('value') is not None else '아니오'} | {te.get('status')} · {te.get('reference')} |", f"| OpenDART | {now:%H:%M KST} | {'예' if DART_API_KEY else '아니오'} | {'확인 시도' if DART_API_KEY else '접근 제한'} |", "", f"할인율 교차확인: {real_yield_note(fred, te)}", ""]
    if alerts:
        for i, alert in enumerate(alerts[:7], 1):
            lines.append(render_alert(alert, i, now, fred, te))
    else:
        lines += ["장전 고충격 뉴스 직접 확인 없음", "", "감정성 뉴스로 제외: 공식/신뢰 소스에서 돈 버는 능력, 할인율, 수급, 시간표를 명확히 바꾸는 후보가 직접 확인되지 않은 항목.", ""]
    top = alerts[0]["news"] if alerts else "장전 고충격 뉴스 직접 확인 없음"
    changed = ", ".join(alerts[0]["impacts"]) if alerts else "명확한 변화 없음"
    lines += ["💡 06:30 장전 뉴스 코멘트", f"오늘 1순위 체크는 `{top}`입니다. 오늘 가장 크게 바뀐 축은 `{changed}`이며, 한국장에서는 관련 해외 티커 반응과 국내 수급 확산 여부를 먼저 보겠습니다.", f"할인율은 FRED DFII10과 Trading Economics 10 Year TIPS Yield를 함께 확인했습니다: {real_yield_note(fred, te)}.", "06:50 투자기상도에서 수치·수급·테마와 재확인 필요.", "", "투자 조언이 아닌 참고용 뉴스 브리핑입니다.", "", "주요 출처:", *[f"- {n}" for n in notes[:18]], f"- FRED DFII10: {FRED_DFII10_CSV}", f"- Trading Economics 10Y TIPS: {TE_TIPS_URL}"]
    return "\n".join(lines).strip() + "\n"


def send_telegram(text: str) -> None:
    token, chat_id = os.getenv("TELEGRAM_BOT_TOKEN", "").strip(), os.getenv("TELEGRAM_CHAT_ID", "").strip()
    if not token or not chat_id:
        print("Telegram: TELEGRAM_BOT_TOKEN or TELEGRAM_CHAT_ID missing")
        return
    repo, run_id = os.getenv("GITHUB_REPOSITORY", ""), os.getenv("GITHUB_RUN_ID", "")
    suffix = f"\n\n전체 보고서: https://github.com/{repo}/actions/runs/{run_id}" if repo and run_id else ""
    body = urllib.parse.urlencode({"chat_id": chat_id, "text": (text[: TELEGRAM_TEXT_LIMIT - len(suffix) - 1] + suffix)[:TELEGRAM_TEXT_LIMIT], "disable_web_page_preview": "true"}).encode("utf-8")
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
    now = now_kst()
    items, notes = collect_items(now)
    alerts = [a for a in (classify(x, now) for x in items if fresh(x, now)) if a]
    alerts.sort(key=lambda a: (-a["score"], a["age_hours"] if a["age_hours"] is not None else 999))
    seen, deduped = set(), []
    for alert in alerts:
        key = (norm(alert["news"]), norm(alert["publisher"]), alert["published_kst"][:10])
        if key in seen:
            continue
        seen.add(key); deduped.append(alert)
        if len(deduped) >= 7:
            break
    fred, te = collect_dfii10(), collect_te()
    report = render_report(deduped, notes, fred, te, now)
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    OUT_MD.write_text(report, encoding="utf-8")
    OUT_TITLE.write_text(report.splitlines()[0] + "\n", encoding="utf-8")
    OUT_JSON.write_text(json.dumps({"query_time_kst": now.isoformat(timespec="seconds"), "alerts": deduped, "source_notes": notes, "fred_dfii10": fred, "tradingeconomics_tips": te}, ensure_ascii=False, indent=2, default=str) + "\n", encoding="utf-8")
    print_utf8(report)
    if os.getenv("TELEGRAM_DRY_RUN", "").lower() in {"1", "true", "yes", "y"}:
        print("Telegram: dry run")
        return 0
    if os.getenv("SEND_TELEGRAM", "").lower() in {"1", "true", "yes", "y"}:
        send_telegram(report)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
