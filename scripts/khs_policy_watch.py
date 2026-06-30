#!/usr/bin/env python3
"""KHS policy/regulatory high-impact watch.

Runs in GitHub Actions. Source-first watcher for official policy, legal,
regulatory, offshore wind permit, SEC EDGAR, and OpenDART signals.
"""

from __future__ import annotations

import datetime as dt
import email.utils
import hashlib
import html
import json
import os
import re
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from pathlib import Path
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parents[1]
OUT_DIR = ROOT / "out"
DATA_DIR = ROOT / "data"
SEEN_PATH = DATA_DIR / "khs_policy_watch_seen.json"
KST = ZoneInfo("Asia/Seoul")
UTC = dt.timezone.utc

SEC_USER_AGENT = os.getenv("SEC_USER_AGENT", "KHS-policy-watch/0.2 contact=please-set-SEC_USER_AGENT")
DART_API_KEY = os.getenv("DART_API_KEY", "").strip()
DART_WATCH_STOCK_CODES = {
    code.strip()
    for code in os.getenv(
        "DART_WATCH_STOCK_CODES",
        "005930,000660,373220,051910,006400,112610,267260,010120,064350,010140,329180",
    ).split(",")
    if code.strip()
}
DART_DAYS_BACK = int(os.getenv("DART_DAYS_BACK", "1"))
MAX_ALERTS = int(os.getenv("KHS_WATCH_MAX_ALERTS", "5"))
MAX_SOURCE_AGE_HOURS = int(os.getenv("KHS_SOURCE_MAX_AGE_HOURS", "72"))
DART_INCLUDE_ALL_MAJOR = os.getenv("DART_INCLUDE_ALL_MAJOR", "false").lower() in {"1", "true", "yes", "y"}
DART_ALLOW_CORRECTIONS = os.getenv("DART_ALLOW_CORRECTIONS", "false").lower() in {"1", "true", "yes", "y"}

SEC_COMPANY_WATCHLIST = {
    "NVDA": "0001045810",
    "MU": "0000723125",
    "AVGO": "0001730168",
    "AMD": "0000002488",
    "INTC": "0000050863",
    "TSM": "0001046179",
    "ASML": "0000937966",
    "ARM": "0001973239",
    "AAPL": "0000320193",
    "MSFT": "0000789019",
    "ORCL": "0001341439",
}
SEC_WATCH_FORMS = {"8-K", "6-K", "10-Q", "10-K", "20-F", "40-F", "S-3", "424B5", "SC 13D", "SC 13G"}

DART_REPORT_KEYWORDS = [
    "단일판매",
    "공급계약",
    "수주",
    "유상증자",
    "무상증자",
    "전환사채",
    "신주인수권",
    "교환사채",
    "자기주식",
    "타법인주식",
    "영업양수",
    "영업양도",
    "영업정지",
    "회사합병",
    "회사분할",
    "최대주주",
    "소송",
    "투자판단",
    "주요사항보고서",
    "불성실공시",
    "조회공시",
]
DART_CORRECTION_TERMS = [
    "\uae30\uc7ac\uc815\uc815",
    "\ucca8\ubd80\uc815\uc815",
    "\uc815\uc815",
]
MAJOR_FILING_KEYWORDS = [
    "material definitive agreement",
    "supply agreement",
    "customer agreement",
    "guidance",
    "contract",
    "merger",
    "acquisition",
    "joint venture",
    "offering",
    "convertible",
    "credit agreement",
    *DART_REPORT_KEYWORDS,
]

STAGE_KEYWORDS = {
    "court_order": [
        "court order", "ruling", "injunction", "stay", "vacated", "dismisses appeal",
        "appeal dismissed", "withdraws appeal", "voluntary dismissal", "판결", "항소 취하", "집행정지", "가처분",
    ],
    "final_rule": ["final rule", "finalizes", "effective date", "implementation", "interim final rule", "최종 규칙", "시행일"],
    "permit_restart": [
        "permit", "permitting", "approval", "authorization", "license", "lease", "leasing",
        "outer continental shelf", "ocs", "construction and operations plan", "cop", "record of decision",
        "environmental impact statement", "eis", "restarts", "resumes", "freeze", "pause", "허가", "승인", "동결 해제",
    ],
    "sanctions_tariffs_export": ["sanctions", "tariff", "section 301", "export controls", "entity list", "ofac", "bis", "관세", "제재", "수출통제"],
    "agency_order": ["order", "directive", "notice of proposed rulemaking", "nopr", "request for comments", "hearing", "comment deadline", "notice to lessees", "ntls", "명령", "의견수렴", "청문"],
    "fcc_decision_notice": [
        "open meeting", "commission meeting", "tentative agenda",
        "sunshine notice", "items on circulation", "circulation", "draft order", "report and order",
        "order on reconsideration", "declaratory ruling", "notice of proposed rulemaking", "nprm",
        "further notice of proposed rulemaking", "fnprm", "notice of inquiry", "noi", "proposed rule",
        "rulemaking", "public notice", "spectrum auction", "spectrum", "broadband", "satellite",
        "space bureau", "wireless telecommunications bureau", "wireline competition bureau",
    ],
    "presidential_action": [
        "executive order", "presidential memorandum", "presidential determination", "national security memorandum",
        "national security presidential memorandum", "presidential permit", "proclamation", "administrative order",
        "delegation of authority", "continuation of the national emergency", "행정명령", "대통령 각서", "대통령 결정",
    ],
    "company_filing": [
        "8-k", "6-k", "10-q", "10-k", "20-f", "material definitive agreement", "supply agreement",
        "customer agreement", "contract", "joint venture", "guidance", "merger", "acquisition", "offering",
        "convertible", "공급계약", "수주", "합작", "가이던스", "단일판매", "유상증자", "전환사채",
        "신주인수권", "자기주식", "타법인주식", "합병", "최대주주", "투자판단",
    ],
    "fda_decision": ["fda approves", "fda approval", "complete response letter", "crl", "rejection"],
}

SECTOR_KEYWORDS = {
    "풍력/해상풍력": ["wind", "offshore wind", "boem", "bsee", "renewable", "ocs", "lease", "cop"],
    "전력망/데이터센터": ["ferc", "grid", "transmission", "large load", "data center", "power"],
    "원전/전력기기": ["nuclear", "reactor", "uranium", "transformer"],
    "반도체/AI": ["semiconductor", "chips", "bis", "export controls", "nvidia", "hbm", "ai"],
    "2차전지/핵심광물": ["battery", "lithium", "critical minerals", "ira", "ev"],
    "방산/지정학": ["sanctions", "missile", "defense", "iran", "russia", "china", "taiwan"],
    "바이오/FDA": ["fda", "clinical", "drug", "crl"],
    "관세/수출주": ["tariff", "section 301", "ustr", "customs"],
    "통신/FCC/위성": [
        "fcc", "federal communications commission", "spectrum", "broadband", "wireless", "wireline",
        "satellite", "space bureau", "net neutrality", "universal service", "equipment authorization",
        "telecommunications", "auction",
    ],
    "행정명령/대통령문서": [
        "executive order", "presidential memorandum", "presidential determination", "national security memorandum",
        "presidential permit", "proclamation",
    ],
}

BSEE_STATIC_EXCLUDE = ["approval process", "forms", "about", "faq", "data center", "statistics"]
BSEE_STRONG_TERMS = [
    "notice to lessees", "ntls", "record of decision", "construction and operations plan", "cop",
    "lease sale", "lease area", "final rule", "injunction", "appeal", "vacated", "withdraws", "resumes",
    "restarts", "freeze", "pause", "offshore wind",
]
PRESIDENTIAL_ACTION_STATIC_EXCLUDE = [
    "nominations sent to the senate", "nomination sent to the senate", "nomination and withdrawal",
    "nominations & appointments", "remarks", "fact sheets", "briefings & statements",
    "privacy policy", "subscribe",
]
PRESIDENTIAL_ACTION_EXACT_EXCLUDE = {
    "all", "releases", "presidential actions", "executive orders", "nominations & appointments",
    "presidential memoranda", "proclamations", "fact sheets", "remarks", "research",
}
FCC_STATIC_EXCLUDE = [
    "about the fcc", "consumer", "licensing", "forms", "jobs", "contact", "privacy policy",
    "foia", "no fear act", "inspector general", "rss", "subscribe", "archive",
]
FCC_EXACT_EXCLUDE = {
    "home", "about", "proceedings & actions", "licensing & databases", "reports & research",
    "news & events", "for consumers", "browse by category", "daily digest", "public notices",
    "news releases", "speeches", "statements", "open commission meetings",
}
FCC_STRONG_TERMS = [
    "open meeting", "commission meeting", "tentative agenda", "sunshine notice", "items on circulation",
    "draft", "report and order", "order on reconsideration", "declaratory ruling", "notice of proposed rulemaking",
    "nprm", "further notice of proposed rulemaking", "fnprm", "notice of inquiry", "noi", "public notice",
    "proposed rule", "rulemaking", "spectrum", "auction", "broadband", "satellite", "space bureau",
    "wireless", "wireline", "net neutrality", "universal service", "equipment authorization",
    "covered list", "robocall", "cybersecurity", "emergency alert", "911",
]

FCC_ADMIN_REPORTING_TERMS = [
    "resilient networks",
    "disruptions to communications",
    "disaster information reporting system",
    "dirs",
    "outage reporting",
    "network outage reporting",
    "communications disruption",
    "disaster reporting",
]

@dataclass
class Source:
    name: str
    url: str
    kind: str = "rss"


SOURCES = [
    Source("Federal Register energy", "https://www.federalregister.gov/documents/search.rss?conditions%5Bterm%5D=energy+permit+final+rule"),
    Source("Federal Register chips export", "https://www.federalregister.gov/documents/search.rss?conditions%5Bterm%5D=semiconductor+export+controls+final+rule"),
    Source("Federal Register tariffs", "https://www.federalregister.gov/documents/search.rss?conditions%5Bterm%5D=tariff+section+301+final+rule"),
    Source("Federal Register FCC", "https://www.federalregister.gov/api/v1/documents.json?conditions%5Bagencies%5D%5B%5D=federal-communications-commission&order=newest&per_page=20", "federal_register_json"),
    Source("Federal Register presidential documents", "https://www.federalregister.gov/api/v1/documents.json?conditions%5Btype%5D%5B%5D=PRESDOCU&order=newest&per_page=20", "federal_register_json"),
    Source("White House executive orders", "https://www.whitehouse.gov/presidential-actions/executive-orders/", "whitehouse_html"),
    Source("White House presidential memoranda", "https://www.whitehouse.gov/presidential-actions/presidential-memoranda/", "whitehouse_html"),
    Source("White House proclamations", "https://www.whitehouse.gov/presidential-actions/proclamations/", "whitehouse_html"),
    Source("FCC open meeting", "https://www.fcc.gov/openmeeting", "fcc_html"),
    Source("FCC open commission meetings", "https://www.fcc.gov/news-events/events/open-commission-meetings", "fcc_html"),
    Source("FCC items on circulation", "https://www.fcc.gov/items-on-circulation", "fcc_html"),
    Source("FCC public notices", "https://www.fcc.gov/news-events/public-notices", "fcc_html"),
    Source("FCC daily digest", "https://www.fcc.gov/news-events/daily-digest", "fcc_html"),
    Source("FCC news releases", "https://www.fcc.gov/news-events/news-releases", "fcc_html"),
    Source("FERC news", "https://www.ferc.gov/news-events/news/rss.xml"),
    Source("DOE news", "https://www.energy.gov/rss.xml"),
    Source("USTR press releases", "https://ustr.gov/about/policy-offices/press-office/press-releases.xml"),
    Source("Commerce news", "https://www.commerce.gov/news/rss.xml"),
    Source("BIS news", "https://www.bis.doc.gov/index.php/newsroom/news-releases?format=feed&type=rss"),
    Source("OFAC recent actions", "https://ofac.treasury.gov/recent-actions/rss.xml"),
    Source("SEC press releases", "https://www.sec.gov/news/pressreleases.rss"),
    Source("FTC press releases", "https://www.ftc.gov/news-events/news/press-releases/rss.xml"),
    Source("FDA press announcements", "https://www.fda.gov/about-fda/contact-fda/stay-informed/rss-feeds/press-announcements/rss.xml"),
    Source("BOEM news", "https://www.boem.gov/webteam/rss/boem-rss.xml"),
    Source("BSEE news page", "https://www.bsee.gov/newsroom/news-items", "link_html"),
    Source("BSEE notice to lessees page", "https://www.bsee.gov/protection/notices-and-announcements-to-lessees", "link_html"),
    Source("KRX KIND today disclosure", "https://kind.krx.co.kr/disclosure/todaydisclosure.do?method=searchTodayDisclosureMain", "kind_html"),
    Source("CourtListener wind/order search", "https://www.courtlistener.com/api/rest/v4/search/?q=wind%20permit%20appeal%20injunction%20order&type=o&order_by=score%20desc", "courtlistener"),
    Source("CourtListener BOEM/BSEE wind search", "https://www.courtlistener.com/api/rest/v4/search/?q=BOEM%20BSEE%20offshore%20wind%20permit%20lease%20order&type=o&order_by=score%20desc", "courtlistener"),
    Source("CourtListener export controls search", "https://www.courtlistener.com/api/rest/v4/search/?q=export%20controls%20semiconductor%20injunction%20order&type=o&order_by=score%20desc", "courtlistener"),
]


def now_kst() -> dt.datetime:
    return dt.datetime.now(tz=KST)


def clean_text(value: str | None) -> str:
    if not value:
        return ""
    value = re.sub(r"<[^>]+>", " ", value)
    value = html.unescape(value)
    return re.sub(r"\s+", " ", value).strip()


def fetch_text(url: str, timeout: int = 20) -> tuple[str | None, str | None]:
    req = urllib.request.Request(
        url,
        headers={
            "User-Agent": SEC_USER_AGENT,
            "Accept": "application/rss+xml, application/json, text/xml, text/html;q=0.8, */*;q=0.5",
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            charset = resp.headers.get_content_charset() or "utf-8"
            return resp.read().decode(charset, errors="replace"), None
    except Exception as exc:
        return None, f"{type(exc).__name__}: {exc}"


def parse_date(value: str | None) -> dt.datetime | None:
    if not value:
        return None
    value = value.strip()
    if re.fullmatch(r"\d{8}", value):
        return dt.datetime.strptime(value, "%Y%m%d").replace(tzinfo=KST)
    try:
        parsed = email.utils.parsedate_to_datetime(value)
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=UTC)
        return parsed.astimezone(KST)
    except Exception:
        pass
    for fmt in ("%Y-%m-%dT%H:%M:%SZ", "%Y-%m-%dT%H:%M:%S%z", "%Y-%m-%d"):
        try:
            parsed = dt.datetime.strptime(value[:25], fmt)
            if parsed.tzinfo is None:
                parsed = parsed.replace(tzinfo=UTC)
            return parsed.astimezone(KST)
        except Exception:
            continue
    for fmt in ("%a, %b %d %Y", "%a, %B %d %Y", "%b %d %Y", "%B %d %Y", "%b %d, %Y", "%B %d, %Y", "%m/%d/%Y", "%m-%d-%Y"):
        try:
            parsed = dt.datetime.strptime(value, fmt).replace(tzinfo=UTC)
            return parsed.astimezone(KST)
        except Exception:
            continue
    return None


def parse_rss(text: str, source: Source) -> list[dict]:
    try:
        root = ET.fromstring(text)
    except ET.ParseError:
        return []
    items: list[dict] = []
    for item in root.findall(".//item"):
        published = parse_date(item.findtext("pubDate") or item.findtext("date"))
        items.append({"source": source.name, "title": clean_text(item.findtext("title")), "link": clean_text(item.findtext("link")) or source.url, "summary": clean_text(item.findtext("description")), "published_kst": published.isoformat() if published else ""})
    if items:
        return items
    ns = {"atom": "http://www.w3.org/2005/Atom"}
    for entry in root.findall(".//atom:entry", ns):
        link = source.url
        link_node = entry.find("atom:link", ns)
        if link_node is not None and link_node.attrib.get("href"):
            link = link_node.attrib["href"]
        published = parse_date(entry.findtext("atom:updated", namespaces=ns) or entry.findtext("atom:published", namespaces=ns))
        items.append({"source": source.name, "title": clean_text(entry.findtext("atom:title", namespaces=ns)), "link": link, "summary": clean_text(entry.findtext("atom:summary", namespaces=ns) or entry.findtext("atom:content", namespaces=ns)), "published_kst": published.isoformat() if published else ""})
    return items


def parse_courtlistener(text: str, source: Source) -> list[dict]:
    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        return []
    items = []
    for row in (data.get("results") or [])[:10]:
        absolute_url = row.get("absolute_url") or ""
        published = parse_date(row.get("dateFiled") or row.get("dateArgued") or row.get("dateReargued"))
        items.append({"source": source.name, "title": clean_text(row.get("caseName") or row.get("caseNameFull") or "CourtListener item"), "link": urllib.parse.urljoin("https://www.courtlistener.com", absolute_url) if absolute_url else source.url, "summary": clean_text(row.get("snippet") or row.get("plain_text") or ""), "published_kst": published.isoformat() if published else ""})
    return items


def parse_federal_register_json(text: str, source: Source) -> list[dict]:
    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        return []
    items = []
    for row in (data.get("results") or [])[:20]:
        title = clean_text(str(row.get("title") or row.get("citation") or "Federal Register presidential document"))
        link = clean_text(str(row.get("html_url") or row.get("pdf_url") or source.url))
        published = parse_date(str(row.get("publication_date") or row.get("signing_date") or ""))
        doc_type = clean_text(str(row.get("type") or ""))
        pres_type = clean_text(str(row.get("presidential_document_type") or ""))
        doc_number = clean_text(str(row.get("document_number") or ""))
        abstract = clean_text(str(row.get("abstract") or row.get("excerpt") or ""))
        meta = "; ".join(part for part in (doc_type, pres_type, doc_number) if part)
        summary = clean_text(f"{meta}. {abstract}") or "Federal Register presidential document"
        items.append({"source": source.name, "title": title, "link": link, "summary": summary, "published_kst": published.isoformat() if published else ""})
    return items


def parse_whitehouse_html(text: str, source: Source) -> list[dict]:
    link_pattern = re.compile(r"<a\b[^>]*href=[\"'](?P<href>[^\"']+)[\"'][^>]*>(?P<label>.*?)</a>", re.I | re.S)
    policy_terms = {
        kw.lower()
        for group in list(STAGE_KEYWORDS.values()) + list(SECTOR_KEYWORDS.values())
        for kw in group
    } | {
        "ai", "artificial intelligence", "customs", "critical", "infrastructure", "grid", "energy",
        "supply chain", "federal lands", "commercial fishing", "financial system", "regulatory",
        "national emergency", "defense production act", "national security", "sanctions", "tariff",
    }
    if "executive orders" in source.name:
        doc_type = "Executive Order"
    elif "memoranda" in source.name:
        doc_type = "Presidential Memorandum"
    elif "proclamations" in source.name:
        doc_type = "Proclamation"
    else:
        doc_type = "Presidential Action"
    deduped: dict[str, dict] = {}
    for match in link_pattern.finditer(text):
        title = clean_text(match.group("label"))
        title_lower = title.lower()
        if (
            len(title) < 8
            or title_lower in PRESIDENTIAL_ACTION_EXACT_EXCLUDE
            or any(term in title_lower for term in PRESIDENTIAL_ACTION_STATIC_EXCLUDE)
        ):
            continue
        link = urllib.parse.urljoin(source.url, html.unescape(match.group("href")))
        link_lower = link.lower()
        if "/presidential-actions/" not in link_lower or link.rstrip("/") == source.url.rstrip("/"):
            continue
        tail = clean_text(text[match.end(): match.end() + 700])
        date_match = re.search(
            r"\b(?:January|February|March|April|May|June|July|August|September|October|November|December|"
            r"Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)\s+\d{1,2},\s+20\d{2}\b",
            tail,
            re.I,
        )
        published = parse_date(date_match.group(0)) if date_match else None
        if not published:
            continue
        published = published.astimezone(KST).replace(hour=0, minute=0, second=0, microsecond=0)
        haystack = f"{title_lower} {link_lower}"
        if doc_type == "Proclamation" and not any(term in haystack for term in policy_terms):
            continue
        summary = f"White House {doc_type} official page link: {title}"
        deduped[link] = {"source": source.name, "title": title, "link": link, "summary": summary, "published_kst": published.isoformat()}
    return list(deduped.values())[:20]


def parse_fcc_html(text: str, source: Source) -> list[dict]:
    link_pattern = re.compile(r"<a\b[^>]*href=[\"'](?P<href>[^\"']+)[\"'][^>]*>(?P<label>.*?)</a>", re.I | re.S)
    date_pattern = re.compile(
        r"\b(?:January|February|March|April|May|June|July|August|September|October|November|December|"
        r"Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)\s+\d{1,2},\s+20\d{2}\b"
        r"|\b\d{1,2}[/-]\d{1,2}[/-]20\d{2}\b",
        re.I,
    )
    deduped: dict[str, dict] = {}
    for match in link_pattern.finditer(text):
        title = clean_text(match.group("label"))
        title_lower = title.lower()
        if (
            len(title) < 8
            or title_lower in FCC_EXACT_EXCLUDE
            or any(term in title_lower for term in FCC_STATIC_EXCLUDE)
        ):
            continue
        link = urllib.parse.urljoin(source.url, html.unescape(match.group("href")))
        link_lower = link.lower()
        if "fcc.gov" not in link_lower:
            continue
        if any(skip in link_lower for skip in ("/about/", "/consumer-governmental-affairs/", "/licensing-databases/")):
            continue
        tail = clean_text(text[match.end(): match.end() + 900])
        date_match = date_pattern.search(f"{title} {tail}")
        published = parse_date(date_match.group(0)) if date_match else None
        if not published:
            continue
        published = published.astimezone(KST).replace(hour=0, minute=0, second=0, microsecond=0)
        haystack = f"{title_lower} {link_lower} {tail.lower()} {source.name.lower()}"
        if not any(term in haystack for term in FCC_STRONG_TERMS):
            continue
        summary_tail = tail[:260]
        summary = clean_text(f"{source.name} official page link: {title}. {summary_tail}")
        deduped[link] = {"source": source.name, "title": title, "link": link, "summary": summary, "published_kst": published.isoformat()}
    return list(deduped.values())[:20]


def parse_link_html(text: str, source: Source) -> list[dict]:
    link_pattern = re.compile(r"<a\b[^>]*href=[\"'](?P<href>[^\"']+)[\"'][^>]*>(?P<label>.*?)</a>", re.I | re.S)
    deduped: dict[str, dict] = {}
    for match in link_pattern.finditer(text):
        title = clean_text(match.group("label"))
        title_lower = title.lower()
        if len(title) < 8:
            continue
        if source.name.startswith("BSEE"):
            if any(term in title_lower for term in BSEE_STATIC_EXCLUDE):
                continue
            if not any(term in title_lower for term in BSEE_STRONG_TERMS):
                continue
        else:
            keyword_pool = [kw.lower() for group in list(STAGE_KEYWORDS.values()) + list(SECTOR_KEYWORDS.values()) for kw in group]
            if not any(keyword in title_lower for keyword in keyword_pool):
                continue
        link = urllib.parse.urljoin(source.url, html.unescape(match.group("href")))
        deduped[link] = {"source": source.name, "title": title, "link": link, "summary": f"{source.name} official page link: {title}", "published_kst": ""}
    return list(deduped.values())[:20]


def parse_kind_html(text: str, source: Source, now: dt.datetime) -> list[dict]:
    clean = clean_text(text)
    if "오늘의공시" not in clean and "Disclosure" not in clean:
        return []
    row_pattern = re.compile(r"(?P<date>\d{2}\.\d{2})\s*\([^)]+\)\s*(?P<time>\d{2}:\d{2}).{0,120}?(?P<report>단일판매|공급계약|유상증자|전환사채|자기주식|합병|최대주주|투자판단|소송).{0,120}?", re.S)
    items = []
    for match in row_pattern.finditer(clean):
        month, day = match.group("date").split(".")
        hour, minute = match.group("time").split(":")
        published = now.replace(month=int(month), day=int(day), hour=int(hour), minute=int(minute), second=0, microsecond=0)
        title = clean_text(match.group(0))[:160]
        items.append({"source": source.name, "title": title, "link": source.url, "summary": f"KRX KIND disclosure candidate: {title}", "published_kst": published.isoformat()})
    return items[:20]


def item_age_hours(item: dict, now: dt.datetime) -> float | None:
    value = item.get("published_kst")
    if not value:
        return None
    try:
        published = dt.datetime.fromisoformat(value)
    except ValueError:
        return None
    return (now - published).total_seconds() / 3600


def parse_sec_submissions(text: str, ticker: str, cik: str) -> list[dict]:
    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        return []
    company_name = clean_text(data.get("name") or ticker)
    recent = data.get("filings", {}).get("recent", {})
    forms = recent.get("form") or []
    dates = recent.get("filingDate") or []
    accessions = recent.get("accessionNumber") or []
    docs = recent.get("primaryDocument") or []
    descriptions = recent.get("primaryDocDescription") or []
    items = []
    for idx in range(min(len(forms), len(dates), len(accessions), len(docs))):
        form = str(forms[idx]).strip()
        if form not in SEC_WATCH_FORMS:
            continue
        accession = str(accessions[idx]).strip()
        doc = str(docs[idx]).strip()
        accession_path = accession.replace("-", "")
        description = clean_text(descriptions[idx] if idx < len(descriptions) else "")
        published = parse_date(str(dates[idx]))
        items.append({"source": f"SEC EDGAR {ticker}", "title": f"{ticker} {company_name} filed {form}{': ' + description if description else ''}", "link": f"https://www.sec.gov/Archives/edgar/data/{int(cik)}/{accession_path}/{doc}", "summary": f"SEC EDGAR form {form}; accession {accession}; primary document {doc}", "published_kst": published.isoformat() if published else ""})
    return items[:10]


def collect_sec_filings(now: dt.datetime) -> tuple[list[dict], list[str]]:
    items: list[dict] = []
    notes: list[str] = []
    for ticker, cik in SEC_COMPANY_WATCHLIST.items():
        text, error = fetch_text(f"https://data.sec.gov/submissions/CIK{cik}.json")
        if error:
            notes.append(f"- SEC EDGAR {ticker}: 확인 불가 ({error})")
            continue
        parsed = parse_sec_submissions(text or "", ticker, cik)
        notes.append(f"- SEC EDGAR {ticker}: {len(parsed)}건 확인")
        for item in parsed:
            age = item_age_hours(item, now)
            if age is not None and age <= 96:
                items.append(item)
    return items, notes


def collect_dart_filings(now: dt.datetime) -> tuple[list[dict], list[str]]:
    if not DART_API_KEY:
        return [], ["- OpenDART latest disclosures: 접근 제한 (DART_API_KEY 미설정)"]
    start = (now.date() - dt.timedelta(days=DART_DAYS_BACK)).strftime("%Y%m%d")
    end = now.date().strftime("%Y%m%d")
    params = urllib.parse.urlencode({"crtfc_key": DART_API_KEY, "bgn_de": start, "end_de": end, "last_reprt_at": "N", "page_no": "1", "page_count": "100", "sort": "date", "sort_mth": "desc"})
    text, error = fetch_text(f"https://opendart.fss.or.kr/api/list.json?{params}")
    if error:
        return [], [f"- OpenDART latest disclosures: 확인 불가 ({error})"]
    try:
        data = json.loads(text or "")
    except json.JSONDecodeError:
        return [], ["- OpenDART latest disclosures: 확인 불가 (JSON 파싱 실패)"]
    if str(data.get("status", "")) != "000":
        return [], [f"- OpenDART latest disclosures: 확인 불가/status {data.get('status')} ({data.get('message', 'unknown')})"]
    rows = data.get("list") or []
    items: list[dict] = []
    for row in rows:
        stock_code = clean_text(row.get("stock_code"))
        report = clean_text(row.get("report_nm"))
        corp_name = clean_text(row.get("corp_name"))
        receipt_no = clean_text(row.get("rcept_no"))
        if not report:
            continue
        is_watch_stock = stock_code in DART_WATCH_STOCK_CODES if stock_code else False
        is_major_report = any(keyword.lower() in report.lower() for keyword in DART_REPORT_KEYWORDS)
        is_correction = any(term in report for term in DART_CORRECTION_TERMS)
        if is_correction and not DART_ALLOW_CORRECTIONS:
            continue
        if not is_watch_stock and (not DART_INCLUDE_ALL_MAJOR or not is_major_report):
            continue
        published = parse_date(clean_text(row.get("rcept_dt")))
        link = f"https://dart.fss.or.kr/dsaf001/main.do?rcpNo={receipt_no}" if receipt_no else "https://dart.fss.or.kr/"
        items.append({"source": "OpenDART latest disclosures", "title": f"{corp_name} {report}", "link": link, "summary": f"DART stock_code={stock_code or 'N/A'} receipt={receipt_no or 'N/A'} rm={clean_text(row.get('rm')) or 'N/A'}", "published_kst": published.isoformat() if published else ""})
    return items, [f"- OpenDART latest disclosures: {len(rows)}건 조회, {len(items)}건 후보"]


def classify_item(item: dict) -> dict | None:
    haystack = f"{item.get('title', '')} {item.get('summary', '')}".lower()
    matched = {bucket: [kw for kw in keywords if kw.lower() in haystack] for bucket, keywords in STAGE_KEYWORDS.items()}
    if "fda_decision" in matched and matched["fda_decision"] and "FDA" not in item.get("source", "") and "fda" not in haystack:
        matched["fda_decision"] = []
    matched = {bucket: kws for bucket, kws in matched.items() if kws}
    source_name = item.get("source", "")
    is_fcc_source = source_name.startswith("FCC") or source_name == "Federal Register FCC"
    if is_fcc_source and any(term in haystack for term in FCC_STRONG_TERMS):
        matched.setdefault("fcc_decision_notice", ["fcc official decision/notice source"])
    if not matched:
        return None
    stage_score = sum(len(v) for v in matched.values())
    has_major_filing = any(keyword.lower() in haystack for keyword in MAJOR_FILING_KEYWORDS)
    is_fcc_admin_reporting = is_fcc_source and any(term in haystack for term in FCC_ADMIN_REPORTING_TERMS)
    if is_fcc_admin_reporting:
        importance = "중"
    elif any(bucket in matched for bucket in ("court_order", "final_rule", "sanctions_tariffs_export", "presidential_action", "fda_decision")) or ("fcc_decision_notice" in matched and is_fcc_source):
        importance = "상"
    elif "company_filing" in matched and has_major_filing:
        importance = "중"
    elif stage_score >= 3:
        importance = "중"
    else:
        importance = "하"
    sectors = [sector for sector, keywords in SECTOR_KEYWORDS.items() if any(kw.lower() in haystack for kw in keywords)] or ["정책/규제 일반"]
    if is_fcc_admin_reporting:
        sectors = ["미국 통신망 복구/장애보고"]
    impacts: list[str] = []
    paths: list[str] = []
    if is_fcc_admin_reporting:
        impacts.extend(["시간표", "의사결정 영향 제한적"])
        paths.extend(["정책 타임라인", "규제 준수"])
    elif any(bucket in matched for bucket in ("court_order", "final_rule", "permit_restart", "agency_order", "presidential_action", "fcc_decision_notice")):
        impacts.extend(["시간표", "할인율"])
        paths.extend(["정책 타임라인", "할인율"])
    if any(bucket in matched for bucket in ("sanctions_tariffs_export", "company_filing", "fda_decision")):
        impacts.extend(["돈 버는 능력", "수급"])
        paths.extend(["이익", "수급"])
    if "company_filing" in matched:
        paths.append("계약 가시성")
    fingerprint = hashlib.sha256(f"{item.get('source')}|{item.get('title')}|{item.get('link')}".encode("utf-8")).hexdigest()[:16]
    return {**item, "fingerprint": fingerprint, "matched": matched, "importance": importance, "status": "예비" if item["source"].startswith(("CourtListener", "KRX KIND")) else "확정", "impacts": list(dict.fromkeys(impacts)) or ["의사결정 영향 제한적"], "paths": list(dict.fromkeys(paths)) or ["정책 타임라인"], "sectors": sectors}


def load_seen() -> dict:
    if not SEEN_PATH.exists():
        return {"seen": {}, "updated_at_kst": ""}
    try:
        return json.loads(SEEN_PATH.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {"seen": {}, "updated_at_kst": ""}


def save_seen(seen: dict) -> None:
    DATA_DIR.mkdir(exist_ok=True)
    seen["updated_at_kst"] = now_kst().isoformat(timespec="seconds")
    SEEN_PATH.write_text(json.dumps(seen, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def collect_candidates(now: dt.datetime) -> tuple[list[dict], list[str]]:
    candidates: list[dict] = []
    source_notes: list[str] = []
    for source in SOURCES:
        text, error = fetch_text(source.url)
        if error:
            source_notes.append(f"- {source.name}: 확인 불가 ({error})")
            continue
        if source.kind == "courtlistener":
            items = parse_courtlistener(text or "", source)
        elif source.kind == "kind_html":
            items = parse_kind_html(text or "", source, now)
        elif source.kind == "federal_register_json":
            items = parse_federal_register_json(text or "", source)
        elif source.kind == "whitehouse_html":
            items = parse_whitehouse_html(text or "", source)
        elif source.kind == "fcc_html":
            items = parse_fcc_html(text or "", source)
        elif source.kind == "link_html":
            items = parse_link_html(text or "", source)
        else:
            items = parse_rss(text or "", source)
        source_notes.append(f"- {source.name}: {len(items)}건 확인")
        for item in items:
            age = item_age_hours(item, now)
            if source.kind in {"rss", "courtlistener", "kind_html", "federal_register_json", "whitehouse_html", "fcc_html"} and age is None:
                continue
            if age is not None and age > MAX_SOURCE_AGE_HOURS:
                continue
            classified = classify_item(item)
            if classified:
                classified["age_hours"] = age
                candidates.append(classified)
    for extra_items, extra_notes in (collect_sec_filings(now), collect_dart_filings(now)):
        source_notes.extend(extra_notes)
        for item in extra_items:
            classified = classify_item(item)
            if classified:
                classified["age_hours"] = item_age_hours(item, now)
                candidates.append(classified)
    return candidates, source_notes


def render_report(alerts: list[dict], source_notes: list[str], now: dt.datetime) -> str:
    lines = [f"🚨 KHS 정책·규제 고충격 워치 · {now:%Y년 %m월 %d일 %H:%M KST}", ""]
    if not alerts:
        lines.extend(["고충격 정책·규제 변경 직접 확인 없음", "", "확인 범위:", *source_notes[:40], "", "💡 워치 판단: 이번 실행에서 돈 버는 능력, 할인율, 수급, 시간표를 새로 바꾼 확정 이벤트는 직접 확인되지 않았습니다.", "", "투자 조언이 아닌 참고용 정책·규제 알림입니다."])
        return "\n".join(lines) + "\n"
    for idx, alert in enumerate(alerts, 1):
        matched_terms = sorted({term for terms in alert["matched"].values() for term in terms})
        lines.extend([f"## {idx}. [{alert['importance']}·{alert['status']}] {alert['title']}", f"- 상태 변화: {', '.join(alert['matched'].keys())} 신호 확인 ({', '.join(matched_terms[:8])})", f"- 원문/출처: [{alert['source']}]({alert['link']}) · 원천시각 {alert.get('published_kst') or '확인 불가'} · 조회 {now:%H:%M KST}", f"- 한국장 영향: {', '.join(alert['impacts'])}", f"- 영향 경로: {', '.join(alert['paths'])}", f"- 영향 섹터: {', '.join(alert['sectors'])}", "- 반영 가능성: 낮음~중간. 공식 원문/신뢰 소스 확인 후 한국장 확산 여부를 장전 레이더에서 재확인해야 합니다.", "- 반대 근거: 제목·요약 기반 1차 감시라 원문 세부 조건, 시행일, 예외 조항, 개별 프로젝트 적용 여부 확인이 필요합니다.", "- 즉시 체크: 원문 전문, 시행일/마감일, 한국 밸류체인 노출, 관련 해외 티커·ETF 반응", ""])
    lines.extend(["💡 워치 판단: 이번 실행은 시간표·할인율을 바꿀 수 있는 정책/규제 상태 변화 후보를 우선 감지했습니다. 장전 레이더에서 원문 전문과 시장 반응을 재확인해야 합니다.", "", "투자 조언이 아닌 참고용 정책·규제 알림입니다."])
    return "\n".join(lines) + "\n"


def write_outputs(alerts: list[dict], source_notes: list[str], now: dt.datetime) -> None:
    OUT_DIR.mkdir(exist_ok=True)
    report = render_report(alerts, source_notes, now)
    (OUT_DIR / "khs_policy_watch.md").write_text(report, encoding="utf-8")
    if alerts:
        top = alerts[0]
        (OUT_DIR / "khs_policy_watch_alert_title.txt").write_text(f"KHS 정책 워치: [{top['importance']}] {top['title'][:70]}\n", encoding="utf-8")
        (OUT_DIR / "khs_policy_watch_alert.md").write_text(report, encoding="utf-8")
        (OUT_DIR / "khs_policy_watch_alerts.json").write_text(json.dumps(alerts, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def main() -> int:
    now = now_kst()
    seen = load_seen()
    seen_map = seen.setdefault("seen", {})
    candidates, source_notes = collect_candidates(now)
    new_alerts = []
    for item in sorted(candidates, key=lambda x: (x["importance"] != "상", x.get("age_hours") or 999)):
        if item["importance"] == "하" or item["fingerprint"] in seen_map:
            continue
        new_alerts.append(item)
        seen_map[item["fingerprint"]] = {"title": item["title"], "source": item["source"], "link": item["link"], "first_seen_kst": now.isoformat(timespec="seconds"), "importance": item["importance"]}
        if len(new_alerts) >= MAX_ALERTS:
            break
    if new_alerts:
        save_seen(seen)
    write_outputs(new_alerts, source_notes, now)
    print(f"candidates={len(candidates)} new_alerts={len(new_alerts)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
