#!/usr/bin/env python3
import datetime as dt
import hashlib
import html
import json
import pathlib
import re
import time
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from dataclasses import asdict, dataclass
from zoneinfo import ZoneInfo

from bs4 import BeautifulSoup

ROOT = pathlib.Path(__file__).resolve().parents[1]
STATE_PATH = ROOT / "data" / "clarity_watch_state.json"
OUT_DIR = ROOT / "out"
OUT_DIR.mkdir(parents=True, exist_ok=True)
SOURCE_VERSION = 2

HEADERS = {
    "User-Agent": "Mozilla/5.0 (compatible; KHS-CLARITY-Watch/2.0; +https://github.com/qedgwangju-dot/khs-watch)",
    "Accept-Language": "en-US,en;q=0.9",
    "Accept": "text/html,application/xhtml+xml,application/xml,application/json;q=0.9,*/*;q=0.8",
}
OFFICIAL_DOMAINS = {
    "www.govinfo.gov",
    "www.senate.gov",
    "www.banking.senate.gov",
    "www.agriculture.senate.gov",
    "www.sec.gov",
    "data.sec.gov",
    "www.cftc.gov",
    "www.federalregister.gov",
    "www.reginfo.gov",
    "www.whitehouse.gov",
    "www.cboe.com",
    "www.volatilityshares.com",
}
TOPIC_RE = re.compile(
    r"\b(?:CLARITY(?:\s+Act)?|H\.?\s*R\.?\s*3633|Digital\s+Asset\s+Market\s+Clarity|digital\s+asset\s+market\s+structure|crypto\s+asset\s+market\s+structure)\b",
    re.I,
)
CRYPTO_RE = re.compile(
    r"\b(?:crypto(?:currency| asset)?s?|digital assets?|digital commodities?|blockchain|tokeni[sz](?:e|ed|ation)?|non-security crypto asset|stablecoin|decentralized finance|DeFi)\b",
    re.I,
)
REG_ACTION_RE = re.compile(
    r"\b(?:rule|rulemaking|propos(?:e|ed|al)|adopt(?:s|ed|ion)|final rule|interpretation|guidance|no-action|order|staff letter|framework|registration|market structure|jurisdiction|enforcement|exemptive relief|exemption|exemptions|exempt(?:ed|ion)?)\b",
    re.I,
)
SEC_VERIFIED_SRO_BACKFILL = [
    {
        "source": "SEC 거래소 규칙 승인명령",
        "event_type": "SEC 거래소 상장·거래 승인",
        "title": "Order Granting Approval of a Proposed Rule Change to List and Trade Shares of the 3x Gold ETF, 3x Silver ETF, 3x Bitcoin ETF, 3x Ether ETF, 3x Crude Oil ETF, and 3x Natural Gas ETF",
        "url": "https://www.sec.gov/files/rules/sro/cboebzx/2026/34-106577.pdf",
        "date": "Oct 2, 2026",
        "detail": "Release No. 34-106577; File No. SR-CboeBZX-2026-065; correction-v3-standalone: BITH and ETHK confirmed in VS Trust S-1; futures-based daily 3x products; actual trading start not yet confirmed; separate Volatility Shares Trust 485BXT dates are not launch dates for this VS Trust ETP approval",
    },
]

SEC_DIRECT_ORDER_PROBES = [
    {
        "url": "https://www.sec.gov/files/rules/sro/cboebzx/2026/34-106577.pdf",
        "title": "Order Granting Approval of a Proposed Rule Change to List and Trade Shares of the 3x Gold ETF, 3x Silver ETF, 3x Bitcoin ETF, 3x Ether ETF, 3x Crude Oil ETF, and 3x Natural Gas ETF",
        "date": "Oct 2, 2026",
        "detail": "Release No. 34-106577; File No. SR-CboeBZX-2026-065; correction-v3-standalone: BITH and ETHK confirmed in VS Trust S-1; futures-based daily 3x products; actual trading start not yet confirmed",
    },
]

SEC_EXCHANGE_ORDERS_URLS = [
    "https://www.sec.gov/rules-regulations/self-regulatory-organization-rulemaking/national-securities-exchanges",
    "https://www.sec.gov/taxonomy/term/193081?order=field_publish_date&page=0&sort=desc",
    "https://www.cboe.com/us/equities/regulation/rule_filings/BZX/",
]
VOLATILITY_SHARES_PRODUCTS_URL = "https://www.volatilityshares.com/etf-product-list.php"
VS_TRUST_SUBMISSIONS_URL = "https://data.sec.gov/submissions/CIK0001793497.json"
VS_TRUST_CIK = "1793497"

LEG_ACTION_RE = re.compile(
    r"\b(?:markup|mark-up|vote|voted|advance(?:d)?|pass(?:ed|age)?|fail(?:ed|ure)?|reject(?:ed)?|cloture|floor|calendar|schedule|consideration|amendment|amended|new text|bill text|revised text|reported|referred|signed|signature|veto|became law|enacted|session adjourn|sine die|read twice)\b",
    re.I,
)


@dataclass(frozen=True)
class Event:
    source: str
    event_type: str
    title: str
    url: str
    date: str = ""
    detail: str = ""

    @property
    def key(self):
        raw = "|".join([self.source, self.event_type, self.title, self.url, self.date, self.detail])
        return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def now_kst():
    return dt.datetime.now(ZoneInfo("Asia/Seoul"))


def now_et():
    return dt.datetime.now(ZoneInfo("America/New_York"))


def clean(text):
    return re.sub(r"\s+", " ", html.unescape(text or "")).strip()


def fetch(url, timeout=30):
    host = urllib.parse.urlparse(url).netloc.lower()
    if host not in OFFICIAL_DOMAINS:
        raise RuntimeError(f"non-official domain blocked: {host}")
    last = None
    for attempt in range(3):
        try:
            req = urllib.request.Request(url, headers=HEADERS)
            with urllib.request.urlopen(req, timeout=timeout) as response:
                return response.read()
        except Exception as exc:
            last = exc
            if attempt < 2:
                time.sleep(2 ** attempt)
    raise RuntimeError(f"fetch failed: {url}: {last}")


def soup_for(url):
    return BeautifulSoup(fetch(url), "html.parser")


def abs_url(base, href):
    return urllib.parse.urljoin(base, href)


def local_tag(tag):
    return str(tag).split("}")[-1]


def classify_leg(text):
    t = text.lower()
    if "cloture" in t:
        return "상원 토론종결·절차 표결"
    if any(x in t for x in ["passed", "passage", "agreed to", "rejected", "failed", "yeas", "nays", "vote"]):
        return "표결 결과"
    if any(x in t for x in ["new text", "revised text", "bill text", "amendment", "amended"]):
        return "법안 원문·핵심 조항 수정"
    if any(x in t for x in ["markup", "mark-up", "reported", "advance"]):
        return "위원회 표결·마크업"
    if any(x in t for x in ["calendar", "schedule", "floor", "consideration"]):
        return "상원 본회의 일정"
    if any(x in t for x in ["signed", "signature", "veto", "became law", "enacted"]):
        return "대통령 최종 조치"
    if any(x in t for x in ["adjourn", "sine die"]):
        return "회기 종료·지연"
    return "공식 입법 진행 변화"


def collect_govinfo(errors):
    events = []
    status_url = "https://www.govinfo.gov/bulkdata/BILLSTATUS/119/hr/BILLSTATUS-119hr3633.xml"
    try:
        root = ET.fromstring(fetch(status_url))
        for item in root.iter():
            if local_tag(item.tag) != "item":
                continue
            vals = {}
            for node in item.iter():
                tag = local_tag(node.tag)
                if node.text and tag not in vals:
                    vals[tag] = clean(node.text)
            text = vals.get("text", "")
            date = vals.get("actionDate", "") or vals.get("date", "")
            code = vals.get("actionCode", "")
            if not text or not LEG_ACTION_RE.search(text):
                continue
            if not (TOPIC_RE.search(text) or re.search(r"\b(?:Senate|House|Committee|President)\b", text, re.I)):
                continue
            detail = clean(" | ".join(x for x in [date, code] if x))
            events.append(Event("GovInfo BILLSTATUS", classify_leg(text), text[:900], status_url, date=date, detail=detail))
    except Exception as exc:
        errors.append(f"GovInfo BILLSTATUS: {exc}")

    related_url = "https://www.govinfo.gov/app/details/BILLS-119hr3633rs/related"
    try:
        soup = soup_for(related_url)
        seen = set()
        for a in soup.find_all("a", href=True):
            href = abs_url(related_url, a["href"])
            if "/app/details/BILLS-119hr3633" not in href:
                continue
            href = href.split("?")[0].rstrip("/")
            if href.endswith("/related"):
                href = href[:-8].rstrip("/")
            title = clean(a.get_text(" ", strip=True)) or href.rsplit("/", 1)[-1]
            key = (title, href)
            if key in seen:
                continue
            seen.add(key)
            events.append(Event("GovInfo 법안 원문", "법안 원문 버전", title[:500], href))
        detail_url = "https://www.govinfo.gov/app/details/BILLS-119hr3633rs"
        body = clean(soup_for(detail_url).get_text(" ", strip=True))
        m = re.search(r"Last Action Date Listed\s+(.{1,80}?)\s+Actions?\s+(.{1,700}?)(?=Bill Number|Bill Version|Short Title)", body, re.I)
        if m:
            date, action = clean(m.group(1)), clean(m.group(2))
            events.append(Event("GovInfo 법안 원문", classify_leg(action), action, detail_url, date=date))
    except Exception as exc:
        errors.append(f"GovInfo bill versions: {exc}")
    return events


def collect_banking(errors):
    url = "https://www.banking.senate.gov/search/?q=Clarity+Act"
    events = []
    try:
        soup = soup_for(url)
        pairs = []
        for a in soup.find_all("a", href=True):
            title = clean(a.get_text(" ", strip=True))
            href = abs_url(url, a["href"])
            if not title or "banking.senate.gov" not in urllib.parse.urlparse(href).netloc:
                continue
            if not TOPIC_RE.search(title) or ("/newsroom/" not in href and "/hearings/" not in href):
                continue
            pairs.append((title, href))
        for title, href in list(dict.fromkeys(pairs))[:30]:
            try:
                body = clean(soup_for(href).get_text(" ", strip=True))
            except Exception:
                body = title
            signal = f"{title} {body[:7000]}"
            if not LEG_ACTION_RE.search(signal):
                continue
            dm = re.search(r"\b(?:January|February|March|April|May|June|July|August|September|October|November|December)\s+\d{1,2},\s+2026\b", body)
            events.append(Event("상원 은행위원회", classify_leg(signal), title, href, date=dm.group(0) if dm else ""))
    except Exception as exc:
        errors.append(f"Senate Banking: {exc}")
    return events


def collect_agriculture(errors):
    events = []
    for url in ["https://www.agriculture.senate.gov/newsroom", "https://www.agriculture.senate.gov/hearings"]:
        try:
            soup = soup_for(url)
            for a in soup.find_all("a", href=True):
                title = clean(a.get_text(" ", strip=True))
                href = abs_url(url, a["href"])
                if not title or "agriculture.senate.gov" not in urllib.parse.urlparse(href).netloc:
                    continue
                if not (TOPIC_RE.search(title) or (CRYPTO_RE.search(title) and LEG_ACTION_RE.search(title))):
                    continue
                events.append(Event("상원 농업위원회", classify_leg(title), title, href))
        except Exception as exc:
            errors.append(f"Senate Agriculture {url}: {exc}")
    return list({e.key: e for e in events}.values())


def collect_floor(errors):
    sources = [
        ("상원 본회의", "https://www.senate.gov/floor/index.htm"),
        ("상원 의사기록", "https://www.senate.gov/legislative/LIS/floor_activity/all-floor-activity-files.htm"),
        ("상원 표결기록", "https://www.senate.gov/legislative/LIS/roll_call_lists/vote_menu_119_2.htm"),
    ]
    events = []
    for source, url in sources:
        try:
            soup = soup_for(url)
            for node in soup.find_all(["tr", "li", "p", "div"]):
                text = clean(node.get_text(" ", strip=True))
                if not text or len(text) > 1400 or not TOPIC_RE.search(text) or not LEG_ACTION_RE.search(text):
                    continue
                a = node.find("a", href=True)
                events.append(Event(source, classify_leg(text), text[:900], abs_url(url, a["href"]) if a else url))
        except Exception as exc:
            errors.append(f"{source}: {exc}")
    return list({e.key: e for e in events}.values())


def parse_rss(url, source, errors):
    events = []
    try:
        root = ET.fromstring(fetch(url))
        items = root.findall(".//item") or root.findall(".//{http://www.w3.org/2005/Atom}entry")
        for item in items[:100]:
            def text_of(names):
                for name in names:
                    node = item.find(name)
                    if node is not None and node.text:
                        return clean(node.text)
                return ""
            title = text_of(["title", "{http://www.w3.org/2005/Atom}title"])
            desc = text_of(["description", "summary", "{http://www.w3.org/2005/Atom}summary"])
            pub = text_of(["pubDate", "published", "updated", "{http://www.w3.org/2005/Atom}published", "{http://www.w3.org/2005/Atom}updated"])
            link = text_of(["link"])
            if not link:
                node = item.find("{http://www.w3.org/2005/Atom}link")
                if node is not None:
                    link = node.attrib.get("href", "")
            signal = clean(f"{title} {desc}")
            if not (TOPIC_RE.search(signal) or (CRYPTO_RE.search(signal) and REG_ACTION_RE.search(signal))):
                continue
            if not REG_ACTION_RE.search(signal):
                continue
            events.append(Event(source, "SEC·CFTC 공식 규칙·해석·집행지침", title or signal[:180], link or url, date=pub, detail=desc[:700]))
    except Exception as exc:
        errors.append(f"{source}: {exc}")
    return events


def collect_federal_register(errors):
    events = []
    searches = [
        ("CFTC Federal Register 제안규칙", "commodity-futures-trading-commission", "PRORULE"),
        ("CFTC Federal Register 최종규칙", "commodity-futures-trading-commission", "RULE"),
        ("SEC Federal Register 제안규칙", "securities-and-exchange-commission", "PRORULE"),
        ("SEC Federal Register 최종규칙", "securities-and-exchange-commission", "RULE"),
    ]
    for source, agency, doc_type in searches:
        query = urllib.parse.urlencode({
            "conditions[agencies][]": agency,
            "conditions[search_type_id]": "3",
            "conditions[type][]": doc_type,
            "order": "newest",
            "format": "json",
        })
        url = f"https://www.federalregister.gov/documents/search?{query}"
        try:
            payload = json.loads(fetch(url).decode("utf-8"))
            for row in (payload.get("results") or [])[:60]:
                title = clean(row.get("title") or "")
                abstract = clean(row.get("abstract") or "")
                signal = f"{title} {abstract}"
                if not (TOPIC_RE.search(signal) or (CRYPTO_RE.search(signal) and REG_ACTION_RE.search(signal))):
                    continue
                detail_parts = []
                if abstract:
                    detail_parts.append(abstract[:520])
                if row.get("document_number"):
                    detail_parts.append(f"Document Number: {clean(row.get('document_number'))}")
                if row.get("publication_date"):
                    detail_parts.append(f"Publication Date: {clean(row.get('publication_date'))}")
                if row.get("comments_close_on"):
                    detail_parts.append(f"Comments Close: {clean(row.get('comments_close_on'))}")
                if row.get("effective_on"):
                    detail_parts.append(f"Effective Date: {clean(row.get('effective_on'))}")
                if row.get("citation"):
                    detail_parts.append(f"Citation: {clean(row.get('citation'))}")
                events.append(Event(
                    source,
                    "SEC·CFTC 공식 규칙·해석·집행지침",
                    title,
                    row.get("html_url") or url,
                    date=row.get("publication_date") or "",
                    detail=" | ".join(detail_parts)[:900],
                ))
        except Exception as exc:
            errors.append(f"{source}: {exc}")
    return events



def parse_reginfo_review_text(text):
    text = clean(text)
    pattern = re.compile(
        r"AGENCY:\s*(?P<agency>.+?)\s+RIN:\s*(?P<rin>\d{4}-[A-Z]{2}\d+)\s+"
        r"Status:\s*(?P<status>Pending Review|Concluded)\s+"
        r"TITLE:\s*(?P<title>.+?)\s+"
        r"STAGE:\s*(?P<stage>Prerule|Proposed Rule|Final Rule|Other)\s+"
        r"Economically Significant:\s*(?P<econ>.+?)\s+"
        r"(?:\*+\s*)?RECEIVED DATE:\s*(?P<received>\d{2}/\d{2}/\d{4})\s+"
        r"LEGAL DEADLINE:\s*(?P<deadline>.*?)(?=\s+AGENCY:|$)",
        re.I,
    )
    rows = []
    for m in pattern.finditer(text):
        econ_tokens = re.findall(r"\b(?:Yes|No)\b", m.group("econ"), re.I)
        econ = econ_tokens[-1].title() if econ_tokens else ""
        deadline = clean(m.group("deadline"))
        if len(deadline) > 120:
            deadline = deadline[:120]
        rows.append({
            "agency": clean(m.group("agency")),
            "rin": clean(m.group("rin")).upper(),
            "status": clean(m.group("status")),
            "title": clean(m.group("title")),
            "stage": clean(m.group("stage")),
            "economically_significant": econ,
            "received_date": clean(m.group("received")),
            "legal_deadline": deadline,
        })
    return rows


def parse_reginfo_table_rows(soup):
    rows = []
    for tr in soup.find_all("tr"):
        cells = [clean(td.get_text(" ", strip=True)) for td in tr.find_all(["td", "th"])]
        if not cells:
            continue
        joined = " | ".join(cells)
        rin_match = re.search(r"\b(\d{4}-[A-Z]{2}\d+)\b", joined, re.I)
        date_match = re.search(r"\b(\d{2}/\d{2}/\d{4})\b", joined)
        status_match = re.search(r"\b(Pending Review|Concluded)\b", joined, re.I)
        if not rin_match or not date_match or not status_match:
            continue
        rin = rin_match.group(1).upper()
        title = ""
        for cell in cells:
            if rin in cell.upper() or re.fullmatch(r"\d{2}/\d{2}/\d{4}", cell) or "CFTC" in cell.upper() or "SEC" == cell.upper():
                continue
            if re.search(r"Pending Review|Concluded|Consistent", cell, re.I):
                continue
            if len(cell) > len(title):
                title = cell
        rows.append({
            "agency": "",
            "rin": rin,
            "status": status_match.group(1).title(),
            "title": title,
            "stage": "",
            "economically_significant": "",
            "received_date": date_match.group(1),
            "legal_deadline": "",
        })
    return rows


def collect_reginfo_reviews(errors):
    events = []
    agencies = [
        ("CFTC", "3038"),
        ("SEC", "3235"),
    ]
    for agency_name, agency_code in agencies:
        pending_url = f"https://www.reginfo.gov/public/do/eoReviewSearch?agencyCode={agency_code}"
        search_url = (
            "https://www.reginfo.gov/public/Forward?"
            f"Image61.x=0&Image61.y=0&SearchTarget=RegReview&textfield={agency_code}"
        )
        rows_by_key = {}
        for url in (pending_url, search_url):
            try:
                raw = fetch(url).decode("utf-8", "ignore")
                soup = BeautifulSoup(raw, "html.parser")
                page_text = clean(soup.get_text(" ", strip=True))
                rows = parse_reginfo_review_text(page_text)
                rows.extend(parse_reginfo_table_rows(soup))
                for row in rows:
                    title = clean(row.get("title") or "")
                    signal = f"{title} {row.get('rin','')}"
                    if not (TOPIC_RE.search(signal) or CRYPTO_RE.search(signal)):
                        continue
                    key = (
                        clean(row.get("rin") or "").upper(),
                        clean(row.get("status") or "").lower(),
                    )
                    if not key[0]:
                        continue
                    prior = rows_by_key.get(key)
                    prior_score = 0 if prior is None else sum(bool(clean(prior.get(k) or "")) for k in ("stage", "economically_significant", "legal_deadline", "title"))
                    row_score = sum(bool(clean(row.get(k) or "")) for k in ("stage", "economically_significant", "legal_deadline", "title"))
                    if prior is None or row_score > prior_score:
                        row = dict(row)
                        row["source_url"] = url
                        rows_by_key[key] = row
            except Exception as exc:
                errors.append(f"RegInfo {agency_name} {url}: {exc}")

        for row in rows_by_key.values():
            title = clean(row.get("title") or "")
            stage = clean(row.get("stage") or "") or "OIRA review"
            status = clean(row.get("status") or "")
            rin = clean(row.get("rin") or "")
            received = clean(row.get("received_date") or "")
            econ = clean(row.get("economically_significant") or "")
            deadline = clean(row.get("legal_deadline") or "")
            detail_parts = [
                f"RIN {rin}",
                f"Status: {status}",
                f"Stage: {stage}",
            ]
            if econ:
                detail_parts.append(f"Economically Significant: {econ}")
            if deadline:
                detail_parts.append(f"Legal Deadline: {deadline}")
            events.append(Event(
                f"OIRA/RegInfo — {agency_name}",
                f"{agency_name} OIRA 규제검토 — {stage}",
                title,
                clean(row.get("source_url") or pending_url),
                date=received,
                detail=" | ".join(detail_parts),
            ))
    return list({e.key: e for e in events}.values())


def collect_sec_newsroom_crypto_orders(errors):
    events = []
    url = "https://www.sec.gov/newsroom"
    try:
        soup = soup_for(url)
        for a in soup.find_all("a", href=True):
            title = clean(a.get_text(" ", strip=True))
            if not title or not CRYPTO_RE.search(title):
                continue
            if not re.search(r"\b(?:Order|Approval|Approving|Approved|List|Listing|Trade|Trading|Shares|ETF|ETP)\b", title, re.I):
                continue
            href = abs_url(url, a.get("href"))
            container = a.find_parent(["article", "li", "div"])
            detail = clean(container.get_text(" ", strip=True))[:900] if container else title
            date = ""
            m = re.search(
                r"\b(Jan(?:uary)?|Feb(?:ruary)?|Mar(?:ch)?|Apr(?:il)?|May|Jun(?:e)?|Jul(?:y)?|Aug(?:ust)?|Sep(?:t(?:ember)?)?|Oct(?:ober)?|Nov(?:ember)?|Dec(?:ember)?)\.?\s+\d{1,2},\s+20\d{2}\b",
                detail,
                re.I,
            )
            if m:
                date = m.group(0).replace(".", "")
            events.append(Event(
                "SEC Newsroom 공식 업데이트",
                "SEC 거래소 상장·거래 승인",
                title,
                href,
                date=date,
                detail=detail,
            ))
    except Exception as exc:
        errors.append(f"SEC Newsroom crypto orders: {exc}")
    return list({e.key: e for e in events}.values())


def collect_sec_exchange_orders(errors):
    events = [
        Event(
            row["source"],
            row["event_type"],
            row["title"],
            row["url"],
            date=row["date"],
            detail=row["detail"],
        )
        for row in SEC_VERIFIED_SRO_BACKFILL
    ]
    # Direct probes are used for high-impact orders when SEC index pages block
    # automated runners. The event is emitted only if the official SEC PDF is reachable.
    for probe in SEC_DIRECT_ORDER_PROBES:
        try:
            fetch(probe["url"], timeout=20)
            events.append(Event(
                "SEC 거래소 규칙 승인명령",
                "SEC 거래소 상장·거래 승인",
                probe["title"],
                probe["url"],
                date=probe["date"],
                detail=probe["detail"],
            ))
        except Exception:
            pass

    last_errors = []
    for url in SEC_EXCHANGE_ORDERS_URLS:
        try:
            soup = soup_for(url)
        except Exception as exc:
            last_errors.append(f"{url}: {exc}")
            continue

        seen = set()
        for a in soup.find_all("a", href=True):
            title = clean(a.get_text(" ", strip=True))
            href = abs_url(url, a.get("href"))
            if not title or href in seen:
                continue
            signal = title
            if not CRYPTO_RE.search(signal):
                continue
            if not re.search(r"\b(?:Order|Approval|Approving|Approved|List|Listing|Trade|Trading|Shares|ETF|ETP)\b", signal, re.I):
                continue

            # Cboe fallback page can include still-pending filings; require an
            # approval marker unless the source URL is the SEC page.
            if "cboe.com" in urllib.parse.urlparse(url).netloc.lower():
                parent_text = clean((a.parent or a).get_text(" ", strip=True))
                nearby = clean((a.find_parent("div") or a.parent or a).get_text(" ", strip=True))
                combined = f"{title} {parent_text} {nearby}"
                if not re.search(r"approved|approval|effective", combined, re.I):
                    continue

            seen.add(href)
            date = ""
            detail = ""
            tr = a.find_parent("tr")
            if tr is not None:
                row_text = clean(tr.get_text(" ", strip=True))
                detail = row_text[:900]
                m = re.search(
                    r"\b(Jan(?:uary)?|Feb(?:ruary)?|Mar(?:ch)?|Apr(?:il)?|May|Jun(?:e)?|Jul(?:y)?|Aug(?:ust)?|Sep(?:t(?:ember)?)?|Oct(?:ober)?|Nov(?:ember)?|Dec(?:ember)?)\s+\d{1,2},\s+20\d{2}\b",
                    row_text,
                    re.I,
                )
                if m:
                    date = m.group(0)
            if not detail:
                container = a.find_parent(["li", "div", "article"])
                detail = clean(container.get_text(" ", strip=True))[:900] if container else title

            events.append(Event(
                "SEC 거래소 규칙 승인명령" if "sec.gov" in urllib.parse.urlparse(url).netloc.lower() else "Cboe BZX 공식 규칙변경",
                "SEC 거래소 상장·거래 승인",
                title,
                href,
                date=date,
                detail=detail,
            ))

        if events:
            break

    if not events and last_errors:
        errors.append("SEC/Cboe exchange orders: " + " || ".join(last_errors[:3]))
    return list({e.key: e for e in events}.values())


def recent_submission_rows(payload):
    recent = ((payload or {}).get("filings") or {}).get("recent") or {}
    keys = [
        "accessionNumber", "filingDate", "form", "fileNumber",
        "primaryDocument", "primaryDocDescription",
    ]
    size = max((len(recent.get(k) or []) for k in keys), default=0)
    rows = []
    for i in range(size):
        row = {}
        for key in keys:
            values = recent.get(key) or []
            row[key] = clean(values[i]) if i < len(values) else ""
        rows.append(row)
    return rows


def sec_archive_url(accession, primary_document):
    acc = clean(accession).replace("-", "")
    doc = clean(primary_document)
    if not acc or not doc:
        return ""
    return f"https://www.sec.gov/Archives/edgar/data/{VS_TRUST_CIK}/{acc}/{doc}"


def collect_vs_trust_3x_registration_milestones(errors):
    events = []
    try:
        payload = json.loads(fetch(VS_TRUST_SUBMISSIONS_URL, timeout=25).decode("utf-8"))
    except Exception as exc:
        errors.append(f"VS Trust SEC submissions: {exc}")
        return events

    rows = recent_submission_rows(payload)
    target_file_numbers = set()
    relevant_docs = {}

    # First identify the registration file numbers that actually contain both
    # BITH and ETHK / 3x Bitcoin and 3x Ether.
    for row in rows:
        form = row.get("form", "")
        if form not in {"S-1", "S-1/A", "424B3", "424B4"}:
            continue
        filing_date = row.get("filingDate", "")
        if filing_date and filing_date < "2026-08-17":
            continue
        url = sec_archive_url(row.get("accessionNumber", ""), row.get("primaryDocument", ""))
        if not url:
            continue
        try:
            body = clean(BeautifulSoup(fetch(url, timeout=20), "html.parser").get_text(" ", strip=True))
        except Exception:
            continue
        signal = body.lower()
        if not (
            ("3x bitcoin etf" in signal and "3x ether etf" in signal)
            or ("bith" in signal and "ethk" in signal)
        ):
            continue
        file_no = clean(row.get("fileNumber", ""))
        if file_no:
            target_file_numbers.add(file_no)
        relevant_docs[row.get("accessionNumber", "")] = (row, url, body)

    # Final prospectus / amended registration filing is a launch-readiness milestone.
    for accession, (row, url, body) in relevant_docs.items():
        form = row.get("form", "")
        if form not in {"424B3", "424B4"}:
            continue
        events.append(Event(
            "SEC EDGAR — VS Trust",
            "3배 BTC·ETH ETP 최종 투자설명서",
            "VS Trust, BITH·ETHK final prospectus filed",
            url,
            date=row.get("filingDate", ""),
            detail=f"Form {form}; File No. {row.get('fileNumber','')}; Accession {accession}; BITH/ETHK confirmed in final prospectus",
        ))

    # EFFECT is the critical Securities Act effectiveness milestone. Tie it to
    # the registration file number already verified above, instead of treating
    # any VS Trust EFFECT filing as relevant.
    for row in rows:
        if row.get("form", "") != "EFFECT":
            continue
        filing_date = row.get("filingDate", "")
        if filing_date and filing_date < "2026-08-17":
            continue
        file_no = clean(row.get("fileNumber", ""))
        if target_file_numbers and file_no not in target_file_numbers:
            continue
        url = sec_archive_url(row.get("accessionNumber", ""), row.get("primaryDocument", ""))
        effective_date = filing_date
        if url:
            try:
                raw = fetch(url, timeout=20).decode("utf-8", "ignore")
                m = re.search(r"(?:EFFECTIVE[- ]DATE|effectiveDate)[^0-9]*(20\d{2}[-/]\d{2}[-/]\d{2}|\d{8})", raw, re.I)
                if m:
                    value = m.group(1)
                    if re.fullmatch(r"\d{8}", value):
                        value = f"{value[:4]}-{value[4:6]}-{value[6:]}"
                    effective_date = value.replace("/", "-")
            except Exception:
                pass
        events.append(Event(
            "SEC EDGAR — VS Trust",
            "3배 BTC·ETH ETP 등록 효력 발생",
            "VS Trust BITH·ETHK registration statement effective",
            url or VS_TRUST_SUBMISSIONS_URL,
            date=effective_date or filing_date,
            detail=f"Form EFFECT; File No. {file_no}; Accession {row.get('accessionNumber','')}; registration effectiveness milestone for verified BITH/ETHK filing",
        ))

    return list({e.key: e for e in events}.values())


def collect_volatility_shares_3x_crypto_launch(errors):
    events = []
    try:
        soup = soup_for(VOLATILITY_SHARES_PRODUCTS_URL)
        text = clean(soup.get_text(" ", strip=True))
    except Exception as exc:
        errors.append(f"Volatility Shares product list: {exc}")
        return events

    found = {}
    for ticker, name in (("BITH", "3x Bitcoin ETF"), ("ETHK", "3x Ether ETF")):
        m = re.search(rf"\b{ticker}\b\s+{re.escape(name)}\b", text, re.I)
        if not m:
            continue
        snippet = clean(text[m.start(): m.start() + 700])
        inception = ""
        date_match = re.search(r"\b(\d{2}/\d{2}/20\d{2})\b", snippet)
        if date_match:
            inception = date_match.group(1)
        found[ticker] = {"name": name, "inception": inception}

    if not found:
        return events

    title = " / ".join(f"{ticker} {row['name']}" for ticker, row in found.items())
    detail = " | ".join(
        f"{ticker} issuer product page listed" + (f"; inception {row['inception']}" if row["inception"] else "")
        for ticker, row in found.items()
    )
    stable_dates = sorted({row["inception"] for row in found.values() if row.get("inception")})
    event_date = stable_dates[-1] if stable_dates else ""
    events.append(Event(
        "Volatility Shares 공식 상품목록",
        "3배 BTC·ETH ETP 실제 상품목록·거래개시 추적",
        title,
        VOLATILITY_SHARES_PRODUCTS_URL,
        date=event_date,
        detail=detail,
    ))
    return events


def collect_regulators(errors):
    events = []
    feeds = [
        ("SEC 보도자료", "https://www.sec.gov/news/pressreleases.rss"),
        ("SEC 발언·성명", "https://www.sec.gov/news/speeches-statements.rss"),
        ("CFTC 보도자료", "https://www.cftc.gov/RSS/RSSGP/rssgp.xml"),
    ]
    for source, url in feeds:
        events.extend(parse_rss(url, source, errors))
    events.extend(collect_federal_register(errors))
    events.extend(collect_reginfo_reviews(errors))
    events.extend(collect_sec_newsroom_crypto_orders(errors))
    events.extend(collect_sec_exchange_orders(errors))
    events.extend(collect_vs_trust_3x_registration_milestones(errors))
    events.extend(collect_volatility_shares_3x_crypto_launch(errors))
    return list({e.key: e for e in events}.values())


def collect_whitehouse(errors):
    events = []
    for url in ["https://www.whitehouse.gov/presidential-actions/", "https://www.whitehouse.gov/briefings-statements/", "https://www.whitehouse.gov/releases/"]:
        try:
            soup = soup_for(url)
            for a in soup.find_all("a", href=True):
                title = clean(a.get_text(" ", strip=True))
                href = abs_url(url, a["href"])
                if not title or "whitehouse.gov" not in urllib.parse.urlparse(href).netloc or not TOPIC_RE.search(title):
                    continue
                try:
                    body = clean(soup_for(href).get_text(" ", strip=True))
                except Exception:
                    body = title
                signal = f"{title} {body[:5000]}"
                if re.search(r"\b(?:sign(?:ed|s)?|veto|law|enact|statement|presidential action)\b", signal, re.I):
                    events.append(Event("백악관", "대통령 최종 조치", title, href))
        except Exception as exc:
            errors.append(f"White House {url}: {exc}")
    return list({e.key: e for e in events}.values())


def load_state():
    if not STATE_PATH.exists():
        return {}
    try:
        return json.loads(STATE_PATH.read_text(encoding="utf-8"))
    except Exception:
        return {}


def impact_hint(event):
    text = f"{event.event_type} {event.title} {event.detail}".lower()
    if any(x in text for x in ["passed", "advance", "agreed to", "signed", "became law", "enacted"]):
        return "입법 시간표가 앞당겨지는 변화로 해석. 미국 내 규제 불확실성 축소 방향."
    if any(x in text for x in ["failed", "rejected", "veto", "adjourn", "sine die"]):
        return "입법 시간표가 늦춰지는 변화로 해석. 법률 공백이 길어질 가능성."
    if any(x in text for x in ["new text", "amendment", "amended", "revised text"]):
        return "핵심 조항 재평가 필요. SEC·CFTC 권한 배분, DeFi·중개업자·윤리 조항 변경 여부를 우선 확인."
    if any(x in text for x in ["cloture", "floor", "calendar"]):
        return "상원 본회의 시간표가 구체화된 변화. 실제 최종 표결 가능성이 이전보다 높아졌는지 확인."
    if event.source.startswith(("SEC", "CFTC")):
        return "법 통과와 별개로 규칙 제정을 통해 규제 공백이 줄어드는 경로."
    return "공식 진행 단계 변화. 다음 절차와 규제 공백 기간을 재평가."


def build_alert(events):
    kst, et = now_kst(), now_et()
    lines = [
        "🔔 CLARITY 법안 공식 변화", "",
        f"확인 시각: 미국 동부 {et:%Y-%m-%d %H:%M %Z} / 한국 {kst:%Y-%m-%d %H:%M KST}", "",
    ]
    for i, event in enumerate(events[:10], 1):
        lines += [
            f"{i}. 사건 유형: {event.event_type}",
            f"공식 출처: {event.source}",
            f"내용: {event.title}",
        ]
        if event.date:
            lines.append(f"공식 날짜: {event.date}")
        if event.detail:
            lines.append(f"확인 내용: {clean(event.detail)[:600]}")
        lines += [f"해석: {impact_hint(event)}", f"원문: {event.url}", ""]
    lines += [
        "투자 4축",
        "- 돈 버는 능력: Coinbase·Circle 등 미국 규제권 내 사업자의 규제비용·상품 확장 가능성 변화 여부를 확인.",
        "- 할인율: 법안 자체보다 국채금리·유동성이 직접 변수. 이번 알림은 규제 불확실성 변화만 분리.",
        "- 수급: 법적 명확성이 기관·개발자·자본의 미국 잔류·유입 조건을 바꾸는지 후속 공식 자료로 확인.",
        "- 시간표: 상원 최종 표결 → 필요 시 하원 재처리 → 대통령 조치의 순서를 얼마나 앞당기거나 늦추는지가 핵심.", "",
        "원인 분리: 시장 가격·거래량은 별도 검증 없이 이번 공식 변화의 결과라고 단정하지 않음.",
        "후속 확인: SEC·CFTC 규칙·해석·집행지침, 상원 본회의 일정·cloture·표결, 백악관 서명·거부권.", "",
        "핵심 한 줄 요약: 새 공식 문서·표결·일정·규칙이 실제 확인된 경우에만 전송하며, 전망·루머·기사 재인용은 알림 대상에서 제외.",
    ]
    return "\n".join(lines).strip() + "\n"


def main():
    errors, events = [], []
    for collector in [collect_govinfo, collect_banking, collect_agriculture, collect_floor, collect_regulators, collect_whitehouse]:
        events.extend(collector(errors))
    events = sorted({e.key: e for e in events}.values(), key=lambda e: (e.source, e.event_type, e.date, e.title))
    state = load_state()
    baseline = (not state.get("initialized")) or state.get("source_version") != SOURCE_VERSION
    seen = set(state.get("seen_event_keys") or [])
    new_events = [] if baseline else [e for e in events if e.key not in seen]
    merged = sorted(set(state.get("seen_event_keys") or []) | {e.key for e in events})
    if len(merged) > 2000:
        merged = merged[-2000:]
    pending = {
        "initialized": True,
        "source_version": SOURCE_VERSION,
        "bill": "H.R. 3633 — Digital Asset Market Clarity Act",
        "last_checked_kst": now_kst().isoformat(timespec="seconds"),
        "last_checked_et": now_et().isoformat(timespec="seconds"),
        "seen_event_keys": merged,
        "event_count": len(events),
        "source_errors": errors,
    }
    (OUT_DIR / "clarity_watch_pending_state.json").write_text(json.dumps(pending, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    rebaseline_path = OUT_DIR / "clarity_watch_rebaseline.txt"
    if baseline:
        rebaseline_path.write_text("source-version baseline refresh\n", encoding="utf-8")
    elif rebaseline_path.exists():
        rebaseline_path.unlink()

    status = [
        "# CLARITY Watch 상태", "", "- 기준 법안: H.R. 3633",
        f"- 확인 시각: {pending['last_checked_kst']}",
        f"- 공식 항목 수: {len(events)}", f"- 신규 공식 변화: {len(new_events)}",
        f"- 기준선 갱신: {'예' if baseline else '아니오'}",
        f"- Telegram 전송 대상: {'없음' if not new_events else '있음'}",
    ]
    if errors:
        status.append("- 일부 공식 출처 접근 오류: " + " | ".join(errors[:10]))
    (OUT_DIR / "clarity_watch_status.md").write_text("\n".join(status) + "\n", encoding="utf-8")

    alert_path = OUT_DIR / "clarity_watch_alert.md"
    alert_json = OUT_DIR / "clarity_watch_alert.json"
    for path in [alert_path, alert_json]:
        if path.exists():
            path.unlink()
    if new_events:
        alert_path.write_text(build_alert(new_events), encoding="utf-8")
        alert_json.write_text(json.dumps([asdict(e) | {"key": e.key} for e in new_events], ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        print(f"clarity_new_official_change=true count={len(new_events)}")
    else:
        print("clarity_new_official_change=false")
    if baseline:
        print("clarity_rebaseline=true")
    if errors:
        print("source_errors=" + " || ".join(errors[:10]))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
