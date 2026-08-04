#!/usr/bin/env python3
"""KHS policy/regulatory high-impact watch.

Runs in GitHub Actions. Source-first watcher for official policy, legal,
regulatory, offshore wind permit, SEC EDGAR, and trusted policy signals.
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

try:
    from khs_policy_alert_explainer import ensure_explained, explanation_lines
    from khs_article_detail import extract_article_detail
    from khs_source_fetch import fetch_text as shared_fetch_text
except ImportError:  # pragma: no cover - supports module-style local tests.
    from scripts.khs_policy_alert_explainer import ensure_explained, explanation_lines
    from scripts.khs_article_detail import extract_article_detail
    from scripts.khs_source_fetch import fetch_text as shared_fetch_text

ROOT = Path(__file__).resolve().parents[1]
OUT_DIR = ROOT / "out"
DATA_DIR = ROOT / "data"
SEEN_PATH = DATA_DIR / "khs_policy_watch_seen.json"
PENDING_SEEN_PATH = OUT_DIR / "khs_policy_watch_pending_seen.json"
KST = ZoneInfo("Asia/Seoul")
UTC = dt.timezone.utc

SEC_USER_AGENT = os.getenv("SEC_USER_AGENT", "KHS-policy-watch/0.2 contact=please-set-SEC_USER_AGENT")
MAX_ALERTS = int(os.getenv("KHS_WATCH_MAX_ALERTS", "5"))
MAX_SOURCE_AGE_HOURS = int(os.getenv("KHS_SOURCE_MAX_AGE_HOURS", "72"))
WHITEHOUSE_MAX_AGE_HOURS = int(os.getenv("KHS_WHITEHOUSE_MAX_AGE_HOURS", "120"))
WHITEHOUSE_DETAIL_LIMIT = int(os.getenv("KHS_WHITEHOUSE_DETAIL_LIMIT", "56"))
WHITEHOUSE_DETAIL_PER_SOURCE = int(os.getenv("KHS_WHITEHOUSE_DETAIL_PER_SOURCE", "8"))
MOFCOM_YEAR = dt.datetime.now(tz=KST).year

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
    "china_trade_controls": [
        "export ban", "export bans", "export suspension", "suspend exports", "suspended exports",
        "export restriction", "export restrictions", "export licensing", "dual-use items",
        "anti-dumping", "antidumping", "countervailing", "tariff", "tariffs",
        "出口管制", "暂停出口", "停止出口", "禁止出口", "出口禁令", "出口许可",
        "暂停", "停止", "禁止", "出口",
        "两用物项", "关税", "反倾销", "反补贴", "不可靠实体清单", "管控名单",
    ],
    "agency_order": ["order", "directive", "notice of proposed rulemaking", "nopr", "request for comments", "hearing", "comment deadline", "notice to lessees", "ntls", "명령", "의견수렴", "청문"],
    "energy_security_policy": [
        "department of energy", "doe", "loan", "loans", "loan guarantee", "conditional commitment",
        "low-cost loan", "funding opportunity", "notice of intent", "grant", "award", "selected",
        "prohibit", "prohibition", "restriction", "ban", "efficiency standard", "emergency order",
        "grid deployment", "transmission facilitation", "critical materials", "nuclear fuel",
    ],
    "state_smr_moc_policy": [
        "state department", "department of state", "office of the spokesperson",
        "memorandum of cooperation", "moc", "trilateral", "small modular reactor",
        "small modular reactors", "smr", "bwrx-300", "first program",
        "samsung c&t", "ge vernova", "hitachi", "sge", "indo-pacific",
        "smr regional training hub",
    ],
    "agriculture_supply_policy": [
        "fertilizer", "phosphate", "phosphate fertilizer", "agriculture", "farm resilience",
        "regenerative agriculture", "biofuel", "biofuel feedstock", "feedstocks", "food supply",
        "duty-free importation", "temporary duty-free", "비료", "인산", "농업", "바이오연료", "식량",
    ],
    "fcc_decision_notice": [
        "open meeting", "commission meeting", "tentative agenda",
        "sunshine notice", "items on circulation", "circulation", "draft order", "report and order",
        "order on reconsideration", "declaratory ruling", "notice of proposed rulemaking", "nprm",
        "further notice of proposed rulemaking", "fnprm", "notice of inquiry", "noi", "proposed rule",
        "rulemaking", "public notice", "spectrum auction", "spectrum", "broadband", "satellite",
        "space bureau", "wireless telecommunications bureau", "wireline competition bureau",
        "covered list", "equipment authorization", "national security", "foreign adversary",
        "secure equipment", "communications supply chain", "connected device", "connected devices",
        "internet of things", "iot", "cyber trust mark", "inverter", "energy inverter",
    ],
    "presidential_action": [
        "executive order", "presidential memorandum", "presidential determination", "national security memorandum",
        "national security presidential memorandum", "presidential permit", "proclamation", "administrative order",
        "delegation of authority", "continuation of the national emergency",
        "fact sheet", "remarks by president", "remarks by president trump", "statement from president",
        "president donald j. trump", "president trump", "trump administration",
        "iran", "israel", "middle east", "hormuz", "strait of hormuz", "red sea", "houthi",
        "missile", "strike", "ceasefire", "war powers", "oil", "brent", "wti", "tanker", "shipping",
        "행정명령", "대통령 각서", "대통령 결정", "트럼프 대통령", "백악관 발언",
    ],
    "company_filing": [
        "8-k", "6-k", "10-q", "10-k", "20-f", "material definitive agreement", "supply agreement",
        "customer agreement", "contract", "joint venture", "guidance", "merger", "acquisition", "offering",
        "convertible", "공급계약", "수주", "합작", "가이던스", "단일판매", "유상증자", "전환사채",
        "신주인수권", "자기주식", "타법인주식", "합병", "최대주주", "투자판단",
    ],
    "fda_decision": ["fda approves", "fda approval", "complete response letter", "crl", "rejection"],
    "treasury_borrowing": [
        "marketable borrowing estimates", "privately-held net marketable debt",
        "quarterly refunding", "borrowing estimate", "cash balance",
    ],
}

SECTOR_KEYWORDS = {
    "풍력/해상풍력": ["wind", "offshore wind", "boem", "bsee", "renewable", "ocs", "lease", "cop"],
    "전력망/데이터센터": ["ferc", "doe", "department of energy", "grid", "electric grid", "transmission", "large load", "data center", "power", "inverter", "energy inverter", "grid deployment", "transmission facilitation"],
    "원전/전력기기": [
        "doe", "department of energy", "department of state", "state department",
        "nuclear", "reactor", "uranium", "nuclear fuel", "transformer", "ap1000",
        "smr", "small modular reactor", "small modular reactors", "bwrx-300",
        "first program", "ge vernova", "hitachi", "samsung c&t",
    ],
    "반도체/AI": ["semiconductor", "chips", "bis", "export controls", "nvidia", "hbm", "ai"],
    "2차전지/핵심광물": ["battery", "lithium", "critical minerals", "ira", "ev"],
    "방산/지정학": [
        "sanctions", "missile", "defense", "iran", "israel", "middle east", "hormuz",
        "strait of hormuz", "red sea", "houthi", "strike", "ceasefire", "war powers",
        "russia", "ukraine", "nato", "china", "taiwan", "north korea", "usfk",
    ],
    "정유/화학/해운": [
        "oil", "brent", "wti", "crude", "lng", "natural gas", "hormuz", "strait of hormuz",
        "red sea", "houthi", "tanker", "shipping", "freight", "maritime",
    ],
    "바이오/FDA": ["fda", "clinical", "drug", "crl"],
    "관세/수출주": ["tariff", "section 301", "section 232", "ustr", "customs", "duty", "quota", "safeguard", "anti-dumping"],
    "중국 수출통제/핵심소재": [
        "mofcom", "china ministry of commerce", "chinese ministry of commerce", "商务部",
        "出口管制", "暂停出口", "停止出口", "禁止出口", "出口禁令", "两用物项",
        "helium", "氦", "rare earth", "稀土", "gallium", "镓", "germanium", "锗",
        "graphite", "石墨", "antimony", "锑", "tungsten", "钨", "indium", "铟",
    ],
    "반도체/디스플레이/산업가스": [
        "helium", "氦", "gallium", "镓", "germanium", "锗", "indium", "铟",
        "semiconductor material", "semiconductor materials", "industrial gas", "industrial gases",
    ],
    "비료/농화학/음식료 원가": ["fertilizer", "phosphate", "agriculture", "farm", "regenerative agriculture", "biofuel", "feedstock", "food supply", "비료", "인산", "농업", "바이오연료", "식량"],
    "통신/FCC/위성": [
        "fcc", "federal communications commission", "spectrum", "broadband", "wireless", "wireline",
        "satellite", "space bureau", "net neutrality", "universal service", "equipment authorization",
        "telecommunications", "auction", "covered list", "national security", "foreign adversary",
        "secure equipment", "communications supply chain", "connected device", "connected devices",
        "internet of things", "iot", "cyber trust mark", "inverter",
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
    "nominations & appointments",
    "privacy policy", "subscribe",
]
PRESIDENTIAL_ACTION_EXACT_EXCLUDE = {
    "all", "releases", "presidential actions", "executive orders", "nominations & appointments",
    "presidential memoranda", "proclamations", "fact sheets", "remarks", "research",
}
TRUMP_MARKET_MOVING_TERMS = [
    "tariff", "tariffs", "section 301", "section 232", "export control", "export controls",
    "sanctions", "china", "taiwan", "korea", "south korea", "north korea", "usfk",
    "defense", "burden sharing", "nato", "semiconductor", "semiconductors", "chip", "chips",
    "ai", "artificial intelligence", "data center", "power grid", "electric grid", "nuclear",
    "reactor", "uranium", "energy", "oil", "brent", "wti", "lng", "natural gas", "iran",
    "israel", "middle east", "hormuz", "strait of hormuz", "red sea", "houthi", "missile",
    "strike", "ceasefire", "war", "war powers", "tanker", "shipping", "russia", "ukraine",
    "fed", "federal reserve", "rate", "rates", "dollar", "steel", "copper", "transformer",
    "pharma", "drug price", "drug prices", "autos", "ev", "supply chain",
]
TRUMP_OFFICIAL_REMARK_STRONG_TERMS = [
    "tariff", "tariffs", "section 301", "section 232", "export control", "export controls",
    "sanctions", "defense spending", "burden sharing", "usfk", "semiconductor", "semiconductors",
    "chip", "chips", "ai", "artificial intelligence", "data center", "power grid", "electric grid",
    "nuclear", "reactor", "uranium", "energy", "oil", "brent", "wti", "lng", "natural gas",
    "hormuz", "strait of hormuz", "red sea", "houthi", "missile", "strike", "ceasefire",
    "war powers", "tanker", "shipping", "fed", "federal reserve", "rate", "rates", "dollar",
    "steel", "copper", "transformer", "pharma", "drug price", "drug prices", "autos", "ev",
    "supply chain",
]
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
    "covered list", "national security", "foreign adversary", "secure equipment",
    "communications supply chain", "inverter", "energy inverter", "solar inverter",
    "connected device", "connected devices", "internet of things", "iot", "cyber trust mark",
    "drone", "camera", "router", "robocall", "cybersecurity", "emergency alert", "911",
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
    Source(
        "China MOFCOM announcements",
        f"https://www.mofcom.gov.cn/zcfb/blgg/gg/{MOFCOM_YEAR}/index.html",
        "mofcom_html",
    ),
    Source("Federal Register energy", "https://www.federalregister.gov/documents/search.rss?conditions%5Bterm%5D=energy+permit+final+rule"),
    Source("Federal Register chips export", "https://www.federalregister.gov/documents/search.rss?conditions%5Bterm%5D=semiconductor+export+controls+final+rule"),
    Source("Federal Register tariffs", "https://www.federalregister.gov/documents/search.rss?conditions%5Bterm%5D=tariff+section+301+final+rule"),
    Source("Federal Register Commerce national security", "https://www.federalregister.gov/documents/search.rss?conditions%5Bterm%5D=commerce+national+security+import+export+controls+tariff+semiconductor+robot+inverter"),
    Source("Federal Register DOE FERC NRC power", "https://www.federalregister.gov/documents/search.rss?conditions%5Bterm%5D=doe+ferc+nrc+power+grid+nuclear+data+center+transformer+reactor+loan"),
    Source("Federal Register DOE restrictions loans", "https://www.federalregister.gov/documents/search.rss?conditions%5Bterm%5D=department+of+energy+loan+guarantee+funding+opportunity+restriction+ban+efficiency+standard+critical+materials"),
    Source("Federal Register agriculture supply", "https://www.federalregister.gov/documents/search.rss?conditions%5Bterm%5D=fertilizer+phosphate+agriculture+biofuel+feedstock+food+supply+tariff+emergency"),
    Source("Federal Register FCC", "https://www.federalregister.gov/api/v1/documents.json?conditions%5Bagencies%5D%5B%5D=federal-communications-commission&order=newest&per_page=20", "federal_register_json"),
    Source("Federal Register presidential documents", "https://www.federalregister.gov/api/v1/documents.json?conditions%5Btype%5D%5B%5D=PRESDOCU&order=newest&per_page=20", "federal_register_json"),
    Source("White House executive orders", "https://www.whitehouse.gov/presidential-actions/executive-orders/", "whitehouse_html"),
    Source("White House presidential memoranda", "https://www.whitehouse.gov/presidential-actions/presidential-memoranda/", "whitehouse_html"),
    Source("White House proclamations", "https://www.whitehouse.gov/presidential-actions/proclamations/", "whitehouse_html"),
    Source("White House fact sheets", "https://www.whitehouse.gov/fact-sheets/", "whitehouse_html"),
    Source("White House remarks", "https://www.whitehouse.gov/remarks/", "whitehouse_html"),
    Source("White House videos", "https://www.whitehouse.gov/videos/", "whitehouse_html"),
    Source("White House briefings statements", "https://www.whitehouse.gov/briefings-statements/", "whitehouse_html"),
    Source("State Department office spokesperson", "https://www.state.gov/releases/office-of-the-spokesperson/", "state_html"),
    Source("State Department press releases", "https://www.state.gov/press-releases/", "state_html"),
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
    Source(
        "U.S. Treasury press releases",
        "https://home.treasury.gov/news/press-releases",
        "treasury_html",
    ),
    Source(
        "U.S. Treasury press releases",
        "https://home.treasury.gov/news/press-releases/sb0584",
        "treasury_html",
    ),
    Source("SEC press releases", "https://www.sec.gov/news/pressreleases.rss"),
    Source("FTC press releases", "https://www.ftc.gov/news-events/news/press-releases/rss.xml"),
    Source("FDA press announcements", "https://www.fda.gov/about-fda/contact-fda/stay-informed/rss-feeds/press-announcements/rss.xml"),
    Source("BOEM news", "https://www.boem.gov/webteam/rss/boem-rss.xml"),
    Source("BSEE news page", "https://www.bsee.gov/newsroom/news-items", "link_html"),
    Source("BSEE notice to lessees page", "https://www.bsee.gov/protection/notices-and-announcements-to-lessees", "link_html"),
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


def keyword_in_text(text: str, keyword: str) -> bool:
    keyword = keyword.lower()
    if re.fullmatch(r"[a-z0-9]+", keyword):
        return re.search(rf"\b{re.escape(keyword)}\b", text) is not None
    return keyword in text


def fetch_text(url: str, timeout: int = 8) -> tuple[str | None, str | None]:
    return shared_fetch_text(
        url,
        SEC_USER_AGENT,
        timeout=timeout,
        attempts=1,
        accept="application/rss+xml, application/json, text/xml, text/html;q=0.8, */*;q=0.5",
    )


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
    elif "fact sheets" in source.name:
        doc_type = "Fact Sheet"
    elif "remarks" in source.name or "videos" in source.name:
        doc_type = "Trump Remarks"
    elif "briefings" in source.name:
        doc_type = "White House Statement"
    else:
        doc_type = "Presidential Action"
    if "fact sheets" in source.name:
        required_path = "/fact-sheets/"
    elif "remarks" in source.name or "videos" in source.name:
        required_path = ("/remarks/", "/videos/")
    elif "briefings" in source.name:
        required_path = "/briefings-statements/"
    else:
        required_path = "/presidential-actions/"
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
        required_paths = required_path if isinstance(required_path, tuple) else (required_path,)
        if not any(path in link_lower for path in required_paths) or link.rstrip("/") == source.url.rstrip("/"):
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
        summary = f"White House {doc_type} listing: {title}"
        deduped[link] = {
            "source": source.name,
            "title": title,
            "link": link,
            "summary": summary,
            "published_kst": published.isoformat(),
            "document_type": doc_type,
            "body_verified": False,
        }
    return list(deduped.values())[:20]


def parse_state_html(text: str, source: Source) -> list[dict]:
    link_pattern = re.compile(r"<a\b[^>]*href=[\"'](?P<href>[^\"']+)[\"'][^>]*>(?P<label>.*?)</a>", re.I | re.S)
    date_pattern = re.compile(
        r"\b(?:January|February|March|April|May|June|July|August|September|October|November|December|"
        r"Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)\s+\d{1,2},\s+20\d{2}\b",
        re.I,
    )
    deduped: dict[str, dict] = {}
    for match in link_pattern.finditer(text):
        title = clean_text(match.group("label"))
        title_lower = title.lower()
        if len(title) < 12:
            continue
        link = urllib.parse.urljoin(source.url, html.unescape(match.group("href")))
        link_lower = link.lower()
        if "state.gov" not in link_lower:
            continue
        if not any(path in link_lower for path in ("/releases/", "/press-releases/")):
            continue
        tail = clean_text(text[match.end(): match.end() + 900])
        haystack = f"{title_lower} {link_lower} {tail.lower()}"
        if not any(keyword_in_text(haystack, term) for term in STAGE_KEYWORDS["state_smr_moc_policy"]):
            continue
        date_match = date_pattern.search(f"{title} {tail}")
        published = parse_date(date_match.group(0)) if date_match else None
        if not published:
            month_match = re.search(r"/(20\d{2})/(\d{2})/", link_lower)
            if month_match:
                year, month = month_match.groups()
                current = now_kst()
                if int(year) == current.year and int(month) == current.month:
                    published = current
                else:
                    published = dt.datetime(int(year), int(month), 1, tzinfo=KST)
        summary = clean_text(f"{source.name} official page link: {title}. {tail[:260]}")
        deduped[link] = {
            "source": source.name,
            "title": title,
            "link": link,
            "summary": summary,
            "published_kst": published.isoformat() if published else "",
        }
    return list(deduped.values())[:20]


def parse_treasury_html(text: str, source: Source) -> list[dict]:
    link_pattern = re.compile(
        r"<a\b[^>]*href=[\"'](?P<href>[^\"']+)[\"'][^>]*>(?P<label>.*?)</a>",
        re.I | re.S,
    )
    date_pattern = re.compile(
        r"\b(?:January|February|March|April|May|June|July|August|September|October|November|December)"
        r"\s+\d{1,2},\s+20\d{2}\b",
        re.I,
    )
    deduped: dict[str, dict] = {}
    for match in link_pattern.finditer(text):
        title = clean_text(match.group("label"))
        link = urllib.parse.urljoin(source.url, html.unescape(match.group("href")))
        if (
            len(title) < 12
            or "home.treasury.gov/news/press-releases/" not in link.lower()
            or link.rstrip("/") == source.url.rstrip("/")
        ):
            continue
        before = text[max(0, match.start() - 600):match.start()]
        datetime_matches = re.findall(r'<time\b[^>]*datetime=["\']([^"\']+)', before, re.I)
        tail = clean_text(text[match.end(): match.end() + 900])
        date_match = date_pattern.search(f"{title} {tail}")
        published = parse_date(datetime_matches[-1]) if datetime_matches else (
            parse_date(date_match.group(0)) if date_match else None
        )
        deduped[link] = {
            "source": source.name,
            "title": title,
            "link": link,
            "summary": f"U.S. Treasury official press release: {title}",
            "published_kst": published.isoformat() if published else "",
            "body_verified": False,
        }
    return list(deduped.values())[:30]


def enrich_treasury_items(items: list[dict]) -> list[dict]:
    enriched: list[dict] = []
    for raw in items:
        item = dict(raw)
        title = str(item.get("title") or "")
        if "marketable borrowing estimates" not in title.lower():
            enriched.append(item)
            continue
        detail_html, detail_error = fetch_text(str(item.get("link") or ""), timeout=16)
        if detail_error or not detail_html:
            item["detail_error"] = detail_error or "empty detail response"
            enriched.append(item)
            continue
        detail = extract_article_detail(detail_html, title)
        if not detail.get("body_verified"):
            item["detail_error"] = "Treasury title/body verification failed"
            enriched.append(item)
            continue
        item.update(
            {
                "source_title": detail.get("title") or title,
                "source_abstract": detail.get("abstract") or "",
                "source_body": detail.get("body") or "",
                "summary": clean_text(
                    f"{detail.get('abstract') or ''} {str(detail.get('body') or '')[:24000]}"
                ),
                "published_kst": item.get("published_kst") or detail.get("published_kst"),
                "body_verified": True,
            }
        )
        enriched.append(item)
    return enriched


def apply_treasury_borrowing_profile(item: dict, haystack: str) -> None:
    if not (
        str(item.get("source") or "") == "U.S. Treasury press releases"
        and item.get("body_verified")
        and "marketable borrowing estimates" in haystack
    ):
        return
    body = clean_text(str(item.get("source_body") or item.get("summary") or ""))
    quarter_matches = re.findall(
        r"During the ([A-Za-z]+)[–—-]([A-Za-z]+) (20\d{2}) quarter, Treasury expects to borrow "
        r"\$([\d,.]+) billion.*?cash balance of \$([\d,.]+) billion",
        body,
        re.I,
    )
    change_match = re.search(
        r"borrowing estimate is \$([\d,.]+) billion (higher|lower) than announced",
        body,
        re.I,
    )
    refunding_match = re.search(
        r"Additional financing details relating to Treasury.s Quarterly Refunding will be released "
        r"at ([\d:]+ [ap]\.m\.) on ([A-Za-z]+), ([A-Za-z]+ \d{1,2}, 20\d{2})",
        body,
        re.I,
    )

    def format_billion_usd(value: str) -> str:
        return f"{float(value.replace(',', '')) * 10:,.0f}억달러"

    month_ko = {
        "january": "1월", "february": "2월", "march": "3월", "april": "4월",
        "may": "5월", "june": "6월", "july": "7월", "august": "8월",
        "september": "9월", "october": "10월", "november": "11월", "december": "12월",
    }

    facts = []
    for start, end, year, borrowing, cash in quarter_matches[:2]:
        facts.append(
            f"{year}년 {month_ko[start.lower()]}~{month_ko[end.lower()]} 순시장성 차입 {format_billion_usd(borrowing)}, "
            f"분기말 현금잔고 {format_billion_usd(cash)} 가정"
        )
    if change_match:
        direction = "증가" if change_match.group(2).lower() == "higher" else "감소"
        facts.append(f"이전 전망보다 {format_billion_usd(change_match.group(1))} {direction}")
    if refunding_match:
        refunding_date = parse_date(refunding_match.group(3))
        refunding_date_ko = (
            f"{refunding_date.year}년 {refunding_date.month}월 {refunding_date.day}일"
            if refunding_date else refunding_match.group(3)
        )
        facts.append(
            f"분기 리펀딩 세부안은 {refunding_date_ko} {refunding_match.group(1)}(미 동부시간) 발표"
        )
    summary = ". ".join(facts) + "." if facts else body[:420]
    item.update(
        {
            "importance": "상",
            "status": "확정",
            "title_ko": "미 재무부, 분기별 순시장성 차입 전망 발표",
            "policy_plain_summary": summary,
            "impacts": ["밸류에이션/할인율", "수급", "시간표"],
            "paths": ["미 국채 공급", "장기금리", "달러", "외국인 수급", "분기환급 일정"],
            "sectors": ["미국 국채/금리/달러", "한국 성장주", "반도체/수출주", "금융주"],
            "investment_view": (
                "예상 차입 증가와 장기물 발행 확대는 미 국채 기간프리미엄과 장기금리를 높여 "
                "한국 성장주 할인율과 외국인 수급에 부담이 될 수 있습니다."
            ),
            "korea_market_impact": (
                "한국장에서는 미국 10년·30년 금리, 원/달러, 외국인 선물·현물 수급과 "
                "반도체·고밸류 성장주의 동행 여부를 확인합니다."
            ),
            "priced_in": "중간. 총차입 추정치는 즉시 반영되지만 만기별 발행 규모는 후속 분기환급계획에서 확정됩니다.",
            "counter": "단기물 중심 조달, 연준 수요, 세수 개선 또는 현금잔고 변화가 장기물 공급 충격을 완화할 수 있습니다.",
            "failure_signal": "후속 분기환급계획에서 장기물 경매 규모가 늘지 않고 미 장기금리·달러가 반응하지 않으면 영향이 약해집니다.",
        }
    )


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
        if not any(keyword_in_text(haystack, term) for term in FCC_STRONG_TERMS):
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


MOFCOM_ACTION_TERMS = [
    "出口管制", "暂停出口", "停止出口", "禁止出口", "出口禁令", "出口许可",
    "两用物项", "关税", "反倾销", "反补贴", "不可靠实体清单", "管控名单",
    "贸易壁垒调查", "保障措施", "制裁", "禁令",
]
MOFCOM_BROAD_CONTROL_TERMS = [
    "出口管制", "暂停出口", "停止出口", "禁止出口", "出口禁令", "出口许可",
    "两用物项", "不可靠实体清单", "管控名单", "制裁", "禁令",
]
MOFCOM_TRADE_REMEDY_TERMS = ["关税", "反倾销", "反补贴", "保障措施", "贸易壁垒调查"]
MOFCOM_KOREA_OR_STRATEGIC_TERMS = [
    "韩国", "韩国产", "氦", "稀土", "镓", "锗", "石墨", "锑", "钨", "铟", "钼",
    "萤石", "碳化硅", "半导体", "芯片", "电池", "正极", "负极", "钢铁", "变压器",
    "机器人", "无人机", "光伏", "太阳能", "天然气", "石油",
]


def parse_mofcom_html(text: str, source: Source) -> list[dict]:
    """Parse material trade-control announcements from the official MOFCOM index."""
    link_pattern = re.compile(r"<a\b[^>]*href=[\"'](?P<href>[^\"']+)[\"'][^>]*>(?P<label>.*?)</a>", re.I | re.S)
    deduped: dict[str, dict] = {}
    for match in link_pattern.finditer(text):
        title = clean_text(match.group("label"))
        export_action_phrase = "出口" in title and any(term in title for term in ["管制", "暂停", "停止", "禁止", "许可", "禁令"])
        if len(title) < 8 or not (any(term in title for term in MOFCOM_ACTION_TERMS) or export_action_phrase):
            continue
        broad_control = any(term in title for term in MOFCOM_BROAD_CONTROL_TERMS) or export_action_phrase
        material_trade_remedy = (
            any(term in title for term in MOFCOM_TRADE_REMEDY_TERMS)
            and any(term in title for term in MOFCOM_KOREA_OR_STRATEGIC_TERMS)
        )
        if not broad_control and not material_trade_remedy:
            continue
        link = urllib.parse.urljoin(source.url, html.unescape(match.group("href")))
        link_lower = link.lower()
        if "mofcom.gov.cn" not in link_lower or "/art/" not in link_lower:
            continue
        tail = clean_text(text[match.end(): match.end() + 260])
        date_match = re.search(r"\b20\d{2}-\d{2}-\d{2}\b", tail)
        published = parse_date(date_match.group(0)) if date_match else None
        if not published:
            continue
        summary = clean_text(f"中国商务部正式公告: {title}")
        deduped[link] = {
            "source": source.name,
            "title": title,
            "link": link,
            "summary": summary,
            "published_kst": published.astimezone(KST).replace(hour=0, minute=0, second=0, microsecond=0).isoformat(),
        }
    return list(deduped.values())[:30]


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


def whitehouse_story_key(item: dict) -> str:
    text = clean_text(
        " ".join(
            str(item.get(key) or "")
            for key in ("title", "source_title", "source_abstract", "source_body")
        )
    ).lower()
    if "defense supply chain" in text and "critical material" in text:
        return "defense-critical-materials"
    if (
        "canada" in text
        and "section 338" in text
        and ("additional tariff" in text or "additional duties" in text)
    ):
        return "canada-section-338-tariffs"
    if "jordan" in text and (
        "trade deal with jordan" in text
        or "reciprocal trade" in text
    ):
        return "jordan-reciprocal-trade"
    if "imports of aluminum" in text or "primary aluminum" in text:
        return "aluminum-section-232-onshoring"
    if "commercial aircraft" in text and "jet engine" in text:
        return "commercial-aircraft-imports"
    slug = urllib.parse.urlparse(str(item.get("link") or "")).path.rstrip("/").rsplit("/", 1)[-1]
    slug = re.sub(r"^(?:fact-sheet-)?president-donald-j-trump-", "", slug)
    return slug or hashlib.sha256(text.encode("utf-8")).hexdigest()[:20]


def should_fetch_whitehouse_detail(item: dict) -> bool:
    doc_type = str(item.get("document_type") or "")
    title = str(item.get("title") or "").lower()
    if doc_type == "Trump Remarks":
        return any(keyword_in_text(title, term) for term in TRUMP_MARKET_MOVING_TERMS)
    return doc_type in {
        "Executive Order",
        "Presidential Memorandum",
        "Proclamation",
        "Fact Sheet",
        "White House Statement",
    }


def enrich_whitehouse_items(
    items: list[dict],
    now: dt.datetime,
    detail_budget: dict,
) -> tuple[list[dict], dict[str, int]]:
    stats = {"listed": len(items), "attempted": 0, "verified": 0, "failed": 0, "deferred": 0}
    enriched: list[dict] = []
    for raw in items:
        item = dict(raw)
        age = item_age_hours(item, now)
        if age is None or age > WHITEHOUSE_MAX_AGE_HOURS or not should_fetch_whitehouse_detail(item):
            stats["deferred"] += 1
            enriched.append(item)
            continue
        source_name = str(item.get("source") or "White House")
        per_source = detail_budget.setdefault("by_source", {})
        if (
            int(detail_budget.get("total", 0)) >= WHITEHOUSE_DETAIL_LIMIT
            or int(per_source.get(source_name, 0)) >= WHITEHOUSE_DETAIL_PER_SOURCE
        ):
            stats["deferred"] += 1
            enriched.append(item)
            continue

        detail_budget["total"] = int(detail_budget.get("total", 0)) + 1
        per_source[source_name] = int(per_source.get(source_name, 0)) + 1
        stats["attempted"] += 1
        detail_html, detail_error = fetch_text(str(item.get("link") or ""), timeout=16)
        if detail_error or not detail_html:
            item["detail_error"] = detail_error or "empty detail response"
            stats["failed"] += 1
            enriched.append(item)
            continue

        detail = extract_article_detail(detail_html, str(item.get("title") or ""))
        if not detail.get("body_verified"):
            item["detail_error"] = (
                "title/body verification failed "
                f"title_aligned={detail.get('title_aligned')} body_chars={len(str(detail.get('body') or ''))}"
            )
            stats["failed"] += 1
            enriched.append(item)
            continue

        item.update(
            {
                "source_title": detail.get("title") or item.get("title"),
                "source_abstract": detail.get("abstract") or "",
                "source_body": detail.get("body") or "",
                "summary": clean_text(
                    f"{detail.get('abstract') or ''} {str(detail.get('body') or '')[:24000]}"
                ),
                "published_kst": detail.get("published_kst") or item.get("published_kst"),
                "body_verified": True,
            }
        )
        item["whitehouse_story_key"] = whitehouse_story_key(item)
        stats["verified"] += 1
        enriched.append(item)
    return enriched, stats


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


def classify_item(item: dict) -> dict | None:
    haystack = " ".join(
        str(item.get(key) or "")
        for key in ("title", "source_title", "source_abstract", "summary", "source_body")
    ).lower()
    source_name = item.get("source", "")
    source_lower = source_name.lower()
    link_lower = str(item.get("link") or "").lower()
    is_whitehouse_source = source_lower.startswith("white house") or "whitehouse.gov/" in link_lower
    if is_whitehouse_source and not item.get("body_verified"):
        return None
    is_treasury_source = source_name == "U.S. Treasury press releases"
    if is_treasury_source and not item.get("body_verified"):
        return None
    if is_treasury_source:
        treasury_title = str(item.get("source_title") or item.get("title") or "").lower()
        if "marketable borrowing estimates" not in treasury_title:
            return None
        haystack = " ".join(
            str(item.get(key) or "")
            for key in ("title", "source_title", "source_abstract")
        ).lower()
    is_whitehouse_remark_or_video = (
        source_lower in {"white house remarks", "white house videos"}
        or "whitehouse.gov/remarks/" in link_lower
        or "whitehouse.gov/videos/" in link_lower
    )
    if is_whitehouse_remark_or_video and not any(keyword_in_text(haystack, term) for term in TRUMP_OFFICIAL_REMARK_STRONG_TERMS):
        return None
    matched = {bucket: [kw for kw in keywords if keyword_in_text(haystack, kw)] for bucket, keywords in STAGE_KEYWORDS.items()}
    if is_treasury_source:
        matched = {"treasury_borrowing": matched.get("treasury_borrowing", [])}
    if "fda_decision" in matched and matched["fda_decision"] and "FDA" not in item.get("source", "") and "fda" not in haystack:
        matched["fda_decision"] = []
    is_fcc_source = source_name.startswith("FCC") or source_name == "Federal Register FCC"
    # "national security" appears in White House memoranda frequently. It is
    # not an FCC signal unless the primary source itself is the FCC.
    if not is_fcc_source:
        matched["fcc_decision_notice"] = []
    matched = {bucket: kws for bucket, kws in matched.items() if kws}
    if is_fcc_source and any(keyword_in_text(haystack, term) for term in FCC_STRONG_TERMS):
        matched.setdefault("fcc_decision_notice", ["fcc official decision/notice source"])
    if not matched:
        return None
    stage_score = sum(len(v) for v in matched.values())
    has_major_filing = any(keyword_in_text(haystack, keyword) for keyword in MAJOR_FILING_KEYWORDS)
    is_fcc_admin_reporting = is_fcc_source and any(keyword_in_text(haystack, term) for term in FCC_ADMIN_REPORTING_TERMS)
    if is_fcc_admin_reporting:
        importance = "중"
    elif any(bucket in matched for bucket in ("court_order", "final_rule", "sanctions_tariffs_export", "china_trade_controls", "energy_security_policy", "state_smr_moc_policy", "presidential_action", "fda_decision", "treasury_borrowing")) or ("fcc_decision_notice" in matched and is_fcc_source):
        importance = "상"
    elif "agriculture_supply_policy" in matched:
        importance = "중"
    elif "company_filing" in matched and has_major_filing:
        importance = "중"
    elif stage_score >= 3:
        importance = "중"
    else:
        importance = "하"
    sectors = [sector for sector, keywords in SECTOR_KEYWORDS.items() if any(keyword_in_text(haystack, kw) for kw in keywords)] or ["정책/규제 일반"]
    if is_fcc_admin_reporting:
        sectors = ["미국 통신망 복구/장애보고"]
    impacts: list[str] = []
    paths: list[str] = []
    if is_fcc_admin_reporting:
        impacts.extend(["시간표", "의사결정 영향 제한적"])
        paths.extend(["정책 타임라인", "규제 준수"])
    elif any(bucket in matched for bucket in ("court_order", "final_rule", "permit_restart", "agency_order", "energy_security_policy", "state_smr_moc_policy", "presidential_action", "fcc_decision_notice")):
        impacts.extend(["시간표", "할인율"])
        paths.extend(["정책 타임라인", "할인율"])
    if any(bucket in matched for bucket in ("sanctions_tariffs_export", "china_trade_controls", "energy_security_policy", "state_smr_moc_policy", "agriculture_supply_policy", "company_filing", "fda_decision")):
        impacts.extend(["돈 버는 능력", "수급"])
        paths.extend(["이익", "수급"])
    if "china_trade_controls" in matched:
        impacts.extend(["시간표"])
        paths.extend(["공급망", "정책 타임라인", "원자재 비용"])
    if "state_smr_moc_policy" in matched:
        paths.extend(["계약 가시성", "밸류체인", "프로젝트 파이낸싱"])
    if "company_filing" in matched:
        paths.append("계약 가시성")
    if is_whitehouse_source:
        story_key = item.get("whitehouse_story_key") or whitehouse_story_key(item)
        fingerprint_input = f"whitehouse-detail-v2|{story_key}"
    else:
        fingerprint_input = f"{item.get('source')}|{item.get('title')}|{item.get('link')}"
    fingerprint = hashlib.sha256(fingerprint_input.encode("utf-8")).hexdigest()[:16]
    result = {**item, "fingerprint": fingerprint, "matched": matched, "importance": importance, "status": "예비" if item["source"].startswith(("CourtListener", "KRX KIND")) else "확정", "impacts": list(dict.fromkeys(impacts)) or ["의사결정 영향 제한적"], "paths": list(dict.fromkeys(paths)) or ["정책 타임라인"], "sectors": sectors}
    apply_treasury_borrowing_profile(result, haystack)
    return result


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
    whitehouse_detail_budget = {"total": 0, "by_source": {}}
    whitehouse_totals = {"listed": 0, "attempted": 0, "verified": 0, "failed": 0, "deferred": 0, "classified": 0}
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
        elif source.kind == "state_html":
            items = parse_state_html(text or "", source)
        elif source.kind == "mofcom_html":
            items = parse_mofcom_html(text or "", source)
        elif source.kind == "treasury_html":
            items = enrich_treasury_items(parse_treasury_html(text or "", source))
        elif source.kind == "link_html":
            items = parse_link_html(text or "", source)
        else:
            items = parse_rss(text or "", source)
        if source.kind == "whitehouse_html":
            items, detail_stats = enrich_whitehouse_items(items, now, whitehouse_detail_budget)
            for key, value in detail_stats.items():
                whitehouse_totals[key] += value
            print(
                f"whitehouse_source={source.name!r} listed={detail_stats['listed']} "
                f"detail_attempted={detail_stats['attempted']} detail_verified={detail_stats['verified']} "
                f"detail_failed={detail_stats['failed']} detail_deferred={detail_stats['deferred']}"
            )
        source_notes.append(f"- {source.name}: {len(items)}건 확인")
        for item in items:
            age = item_age_hours(item, now)
            if source.kind in {"rss", "courtlistener", "kind_html", "federal_register_json", "whitehouse_html", "fcc_html", "state_html", "mofcom_html", "treasury_html"} and age is None:
                continue
            max_age = WHITEHOUSE_MAX_AGE_HOURS if source.kind == "whitehouse_html" else MAX_SOURCE_AGE_HOURS
            if age is not None and age > max_age:
                continue
            classified = classify_item(item)
            if classified:
                ensure_explained(classified)
                classified["age_hours"] = age
                candidates.append(classified)
                if source.kind == "whitehouse_html":
                    whitehouse_totals["classified"] += 1
    for extra_items, extra_notes in (collect_sec_filings(now),):
        source_notes.extend(extra_notes)
        for item in extra_items:
            classified = classify_item(item)
            if classified:
                ensure_explained(classified)
                classified["age_hours"] = item_age_hours(item, now)
                candidates.append(classified)
    source_notes.append(
        "- White House detail verification: "
        f"listed={whitehouse_totals['listed']} attempted={whitehouse_totals['attempted']} "
        f"verified={whitehouse_totals['verified']} failed={whitehouse_totals['failed']} "
        f"deferred={whitehouse_totals['deferred']} classified={whitehouse_totals['classified']}"
    )
    print(
        "whitehouse_totals "
        f"listed={whitehouse_totals['listed']} attempted={whitehouse_totals['attempted']} "
        f"verified={whitehouse_totals['verified']} failed={whitehouse_totals['failed']} "
        f"deferred={whitehouse_totals['deferred']} classified={whitehouse_totals['classified']}"
    )
    return candidates, source_notes


def render_report(alerts: list[dict], source_notes: list[str], now: dt.datetime) -> str:
    lines = [f"🚨 KHS 정책·규제 고충격 워치 · {now:%Y년 %m월 %d일 %H:%M KST}", ""]
    if not alerts:
        lines.extend(["고충격 정책·규제 변경 직접 확인 없음", "", "확인 범위:", *source_notes[:40], "", "💡 워치 판단: 이번 실행에서 매출·마진·현금흐름, 밸류에이션/할인율, 수급, 시간표를 새로 바꾼 확정 이벤트는 직접 확인되지 않았습니다.", "", "투자 조언이 아닌 참고용 정책·규제 알림입니다."])
        return "\n".join(lines) + "\n"
    for idx, alert in enumerate(alerts, 1):
        ensure_explained(alert)
        matched_terms = sorted({term for terms in alert["matched"].values() for term in terms})
        display_title = alert.get("title_ko") or alert["title"]
        lines.extend(
            [
                f"## {idx}. [{alert['importance']}·{alert['status']}] {display_title}",
                f"- 원제: {alert['title']}",
                f"- 상태 변화: {', '.join(alert['matched'].keys())} 신호 확인 ({', '.join(matched_terms[:8])})",
                f"- 원문/출처: [{alert['source']}]({alert['link']}) · 원천시각 {alert.get('published_kst') or '확인 불가'} · 조회 {now:%H:%M KST}",
                *explanation_lines(alert),
                "- 즉시 체크: 원문 전문, 시행일/마감일, 한국 밸류체인 노출, 관련 해외 티커·ETF 반응",
                "",
            ]
        )
    lines.extend(["💡 워치 판단: 이번 실행은 매출·마진·현금흐름, 밸류에이션/할인율, 수급, 시간표 중 실제로 바뀐 축과 한국 밸류체인 연결을 기준으로 정책/규제 후보를 선별했습니다.", "", "투자 조언이 아닌 참고용 정책·규제 알림입니다."])
    return "\n".join(lines) + "\n"


def write_outputs(alerts: list[dict], source_notes: list[str], now: dt.datetime) -> None:
    OUT_DIR.mkdir(exist_ok=True)
    report = render_report(alerts, source_notes, now)
    (OUT_DIR / "khs_policy_watch.md").write_text(report, encoding="utf-8")
    if alerts:
        top = alerts[0]
        ensure_explained(top)
        (OUT_DIR / "khs_policy_watch_alert_title.txt").write_text(f"KHS 정책 워치: [{top['importance']}] {(top.get('title_ko') or top['title'])[:70]}\n", encoding="utf-8")
        (OUT_DIR / "khs_policy_watch_alert.md").write_text(report, encoding="utf-8")
        (OUT_DIR / "khs_policy_watch_alerts.json").write_text(json.dumps(alerts, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    else:
        for path in (
            OUT_DIR / "khs_policy_watch_alert_title.txt",
            OUT_DIR / "khs_policy_watch_alert.md",
            OUT_DIR / "khs_policy_watch_alerts.json",
            PENDING_SEEN_PATH,
        ):
            try:
                path.unlink()
            except FileNotFoundError:
                pass


def write_pending_seen(alerts: list[dict], now: dt.datetime) -> None:
    if not alerts:
        return
    pending = {
        "created_at_kst": now.isoformat(timespec="seconds"),
        "seen": {
            item["fingerprint"]: {
                "title": item["title"],
                "source": item["source"],
                "link": item["link"],
                "first_seen_kst": now.isoformat(timespec="seconds"),
                "importance": item["importance"],
            }
            for item in alerts
        },
    }
    PENDING_SEEN_PATH.write_text(
        json.dumps(pending, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def candidate_source_rank(item: dict) -> int:
    source = str(item.get("source") or "").lower()
    if item.get("whitehouse_story_key"):
        if source == "white house fact sheets":
            return 0
        if source in {
            "white house executive orders",
            "white house presidential memoranda",
            "white house proclamations",
            "white house briefings statements",
        }:
            return 1
    return 2


def dedupe_candidate_fingerprints(candidates: list[dict]) -> list[dict]:
    selected: dict[str, dict] = {}
    order: list[str] = []
    for item in candidates:
        fingerprint = str(item.get("fingerprint") or "").strip()
        key = fingerprint or hashlib.sha256(
            f"{item.get('source')}|{item.get('title')}|{item.get('link')}".encode("utf-8")
        ).hexdigest()[:16]
        if key not in selected:
            selected[key] = item
            order.append(key)
            continue
        current = selected[key]
        if candidate_source_rank(item) < candidate_source_rank(current):
            selected[key] = item
    return [selected[key] for key in order]


def main() -> int:
    now = now_kst()
    seen = load_seen()
    seen_map = seen.setdefault("seen", {})
    candidates, source_notes = collect_candidates(now)
    candidates = dedupe_candidate_fingerprints(candidates)
    new_alerts = []
    selected_fingerprints: set[str] = set()
    for item in sorted(candidates, key=lambda x: (x["importance"] != "상", x.get("age_hours") or 999)):
        if (
            item["importance"] == "하"
            or item["fingerprint"] in seen_map
            or item["fingerprint"] in selected_fingerprints
        ):
            continue
        new_alerts.append(item)
        selected_fingerprints.add(item["fingerprint"])
        if len(new_alerts) >= MAX_ALERTS:
            break
    write_outputs(new_alerts, source_notes, now)
    write_pending_seen(new_alerts, now)
    for item in new_alerts:
        print(
            "policy_selected "
            f"source={item.get('source')!r} title={item.get('title')!r} "
            f"matched={sorted((item.get('matched') or {}).keys())!r}"
        )
    whitehouse_candidates = sum(
        str(item.get("source") or "").lower().startswith("white house")
        for item in candidates
    )
    whitehouse_new = sum(
        str(item.get("source") or "").lower().startswith("white house")
        for item in new_alerts
    )
    whitehouse_seen_filtered = sum(
        str(item.get("source") or "").lower().startswith("white house")
        and item.get("fingerprint") in seen_map
        for item in candidates
    )
    print(
        f"candidates={len(candidates)} new_alerts={len(new_alerts)} "
        f"whitehouse_candidates={whitehouse_candidates} whitehouse_new={whitehouse_new} "
        f"whitehouse_seen_filtered={whitehouse_seen_filtered} seen_state=pending_delivery"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
