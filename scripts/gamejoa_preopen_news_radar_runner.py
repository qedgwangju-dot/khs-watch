#!/usr/bin/env python3
"""Compact GAMEJOA 06:30 KST news radar runner for GitHub Actions."""

from __future__ import annotations

import csv
import concurrent.futures
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

from khs_source_fetch import fetch_text
from zoneinfo import ZoneInfo


ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "out"
KST = ZoneInfo("Asia/Seoul")
MAX_AGE_HOURS = int(os.getenv("RADAR_MAX_AGE_HOURS", "96"))
UA = os.getenv("SEC_USER_AGENT", "GAMEJOA-preopen-radar contact=please-set-secret")
FRED_API_KEY = os.getenv("FRED_API_KEY", "").strip()
TELEGRAM_LIMIT = 4096
FETCH_TIMEOUT_SECONDS = max(3, int(os.getenv("RADAR_FETCH_TIMEOUT_SECONDS", "10")))
FETCH_WORKERS = max(2, int(os.getenv("RADAR_FETCH_WORKERS", "10")))
QUERY_FETCH_WORKERS = max(1, int(os.getenv("RADAR_QUERY_FETCH_WORKERS", "4")))

FRED_CSV = "https://fred.stlouisfed.org/graph/fredgraph.csv?id=DFII10"
TE_URL = "https://tradingeconomics.com/united-states/10-year-tips-yield"

SOURCES = [
    ("Federal Register FERC", "https://www.federalregister.gov/api/v1/documents.json?conditions%5Bagencies%5D%5B%5D=federal-energy-regulatory-commission&order=newest&per_page=20", "fr"),
    ("DOE", "https://www.energy.gov/rss.xml", "official"),
    ("Federal Register Commerce", "https://www.federalregister.gov/api/v1/documents.json?conditions%5Bagencies%5D%5B%5D=commerce-department&order=newest&per_page=20", "fr"),
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
    ("AI ì „ë ¥ë§", "FERC DOE AI data center power grid nuclear energy policy Reuters Bloomberg CNBC"),
    ("DOE ì „ë ¥ë§Â·ì›ì „ ì§€ì›/ì œí•œ", "DOE Department of Energy loan guarantee conditional commitment funding opportunity nuclear reactor AP1000 power grid transformer critical materials Reuters Bloomberg"),
    ("ë°ì´í„°ì„¼í„° ì§€ì—­ ê¸ˆì§€", '"data center" ban moratorium city council residents vote zoning power Reuters Bloomberg AP USA Today'),
    ("ë°ì´í„°ì„¼í„° ì§€ì—­ ì°¨ë‹¨", '"data centers" residents vote block construction city council zoning moratorium county township local news'),
    ("ë°ì´í„°ì„¼í„° ì¸í—ˆê°€ ë°˜ëŒ€", '"data center" "planning commission" "public hearing" permit ordinance moratorium power local news'),
    ("FCC ë³´ì•ˆìž¥ë¹„/ì¸ë²„í„°", "FCC national security import ban foreign equipment inverters solar grid Reuters Bloomberg"),
    ("ë°˜ë„ì²´/AI", "Nvidia Micron Broadcom AMD Intel TSMC ASML ARM Apple Microsoft Oracle AI chip HBM data center server network cooling guidance supply agreement Reuters Bloomberg MarketWatch"),
    ("ìˆ˜ì¶œí†µì œ/ê´€ì„¸", "US Commerce BIS export controls tariffs China semiconductor Reuters Bloomberg AP"),
    ("ë¯¸êµ­ ê³ ì¶©ê²© ì •ì±…", "US policy ban tariff export control investigation subsidy loan nuclear data center power grid robotics semiconductor Reuters Bloomberg Politico"),
    ("EU/í•œêµ­ ì •ì±… ì˜í–¥", "EU South Korea tariff quota safeguard CBAM battery regulation steel export control Reuters Bloomberg European Commission Official Journal"),
    ("ì •ì±…/ê·œì œ", "USTR FTC SEC DOE FERC FCC Commerce BIS OFAC CHIPS Act IRA tariff sanctions export controls Reuters Bloomberg AP"),
    ("ê¸°ì—… ì´ë²¤íŠ¸", "MOU LOI contract supply agreement joint venture capex buyback offering convertible bond guidance Reuters Bloomberg MarketWatch Korea"),
    ("ì§€ì •í•™/ì—ë„ˆì§€", "Iran Israel Hormuz Red Sea oil shipping sanctions Reuters Bloomberg AP CNBC MarketWatch"),
    ("ì›ìžìž¬/ë§¤í¬ë¡œ", "oil natural gas copper lithium uranium gold dollar won treasury yield Fed real yield TIPS Reuters Bloomberg CNBC MarketWatch"),
    ("í•œêµ­ ì§ì ‘ ì˜í–¥", "Samsung SK Hynix LG Energy Solution Hyundai Korea export policy supply contract Reuters Bloomberg"),
    ("FDA/ë°”ì´ì˜¤", "FDA approval complete response letter clinical trial pharma acquisition Reuters Bloomberg CNBC"),
]

CORE_QUERY_BUNDLES = [
    ("íŠ¸ëŸ¼í”„ ì§ì ‘ë°œì–¸/ì •ì±…", "Trump (Iran OR Israel OR Hormuz OR tariff OR export control OR defense cost sharing) Reuters Bloomberg CNBC AP"),
    ("ë¯¸êµ­ ì •ì±…ê¸°ê´€", "(FCC OR DOE OR FERC OR Commerce OR BIS OR USTR OR FTC OR SEC) (ban OR restriction OR rule OR loan OR grant OR export control OR tariff OR investigation) Reuters Bloomberg AP"),
    ("ë°˜ë„ì²´/AI/HBM", "(Nvidia OR Micron OR Broadcom OR AMD OR Intel OR TSMC OR ASML OR HBM4) (guidance OR contract OR price OR supply OR capex) Reuters Bloomberg CNBC TrendForce"),
    ("AI ì „ë ¥/ì›ì „/ì „ë ¥ë§", "(data center OR power grid OR transformer OR nuclear OR SMR OR AP1000) (loan OR contract OR restriction OR permit OR funding) Reuters Bloomberg DOE FERC"),
    ("ì›ìžìž¬/ê¸ˆë¦¬/í™˜ìœ¨", "(oil OR natural gas OR copper OR lithium OR uranium OR gold OR treasury OR dollar) (surge OR drop OR sanctions OR supply OR rate) Reuters Bloomberg CNBC"),
    ("EU/í•œêµ­ í†µìƒ", "South Korea (tariff OR quota OR safeguard OR CBAM OR export control OR sanction OR steel OR battery) Reuters Bloomberg European Commission"),
    ("í•œêµ­ ëŒ€ê¸°ì—… ì§ì ‘ì˜í–¥", "(Samsung OR SK Hynix OR Hyundai OR Hanwha OR LIG Nex1 OR Doosan Enerbility OR Hyosung OR POSCO) (contract OR order OR capex OR guidance OR policy) Reuters Bloomberg"),
    ("K-ë°©ì‚°", "(K9 OR Chunmoo OR Redback OR KM-SAM OR Cheongung OR FA-50 OR KF-21 OR K2 tank) (contract OR order OR export OR delay OR signing) Reuters Bloomberg DAPA"),
    ("ì›ì „/SMR/ê°€ìŠ¤í„°ë¹ˆ", "(KHNP OR Doosan Enerbility OR Westinghouse OR AP1000 OR i-SMR OR gas turbine) (contract OR tender OR loan OR licensing OR deployment) Reuters Bloomberg"),
    ("ë°”ì´ì˜¤/FDA", "(FDA approval OR complete response letter OR PDUFA OR phase 3 OR biotech acquisition OR licensing deal) Reuters Bloomberg CNBC"),
    ("ì´ëž€/í˜¸ë¥´ë¬´ì¦ˆ ê¸´ê¸‰ìƒí™©", "Iran Hormuz attack ship strike ceasefire AP News Reuters CNBC"),
    ("êµ­ë‚´ ì •ì±…", "í•œêµ­ (í†µì‹ ë¹„ OR ìŠ¤í…Œì´ë¸”ì½”ì¸ OR ë””ì§€í„¸ìžì‚° OR ì›ì „ ìž…ì§€ OR ë°˜ë„ì²´ ì„¸ì•¡ê³µì œ OR ë°ì´í„°ì„¼í„°) ì •ì±… ê¸ˆìœµìœ„ì›íšŒ í•œêµ­ì€í–‰ ì‚°ì—…ë¶€ ê³¼ê¸°ì •í†µë¶€"),
    ("ì§€ì—­ ë°ì´í„°ì„¼í„° ê·œì œ", "data center (moratorium OR ban OR zoning OR permit OR public hearing OR city council) Reuters AP local news"),
    ("ë°˜ë„ì²´ ê³µê¸‰ë§ ì „ë¬¸ë§¤ì²´", "(HBM4 OR MLCC OR notebook shipments OR Intel 18A OR LPDDR5X OR high-purity CO2) TrendForce Tom's Hardware ServeTheHome"),
    (
        "ì¤‘êµ­ ìƒë¬´ë¶€ ìˆ˜ì¶œí†µì œ/ê´€ì„¸",
        "(China Ministry of Commerce OR MOFCOM) (export ban OR export suspension OR export control OR export licensing OR tariff OR anti-dumping OR countervailing) (helium OR rare earth OR gallium OR germanium OR graphite OR semiconductor OR battery OR steel) Reuters Bloomberg CNBC",
    ),
]


def trusted_query_plan() -> list[tuple[str, str]]:
    plan = list(CORE_QUERY_BUNDLES)
    for name, query in QUERIES:
        if "site:trendforce.com" in query.lower() and (name, query) not in plan:
            plan.append((name, query))
    return plan

TRUSTED = [
    "reuters", "bloomberg", "associated press", "ap news", "cnbc", "marketwatch",
    "politico", "the wall street journal", "wall street journal", "financial times",
    "usa today", "panama city news herald", "columbus dispatch",
]
LOCAL_DC_POLICY_TERMS = ["ban", "banned", "banning", "block", "blocked", "city council", "county", "moratorium", "ordinance", "permit", "planning commission", "public hearing", "residents", "township", "vote", "zoning"]
TERMS = ["approval", "ban", "banned", "banning", "block", "blocked", "buyback", "capex", "city council", "contract", "convertible", "copper", "court order", "crl", "data center", "data centers", "dollar", "earnings", "entity list", "export control", "fda", "fed", "final rule", "gold", "guidance", "injunction", "joint venture", "lithium", "loi", "merger", "moratorium", "mou", "natural gas", "offering", "oil", "ordinance", "permit", "planning commission", "public hearing", "real yield", "regulation", "residents", "sanction", "section 301", "section 232", "semiconductor", "supply agreement", "tariff", "tips", "township", "uranium", "vote", "won", "yield", "zoning", "fcc", "national security", "covered list", "equipment authorization", "foreign equipment", "inverter", "solar inverter", "doe", "department of energy", "loan guarantee", "conditional commitment", "funding opportunity", "efficiency standard", "grid deployment", "nuclear fuel", "critical materials", "robot", "robotics", "drone", "subsidy", "loan", "low-cost loan", "quota", "safeguard", "anti-dumping", "cbam", "steel", "ap1000", "westinghouse", "nuclear reactor", "critical mineral", "critical minerals"]
TERMS += [
    "mofcom", "china ministry of commerce", "export ban", "export suspension", "export licensing",
    "suspend", "suspends", "suspended", "exports",
    "dual-use items", "helium", "rare earth", "gallium", "germanium", "graphite", "antimony",
    "tungsten", "indium", "countervailing",
]
TERMS += [
    "attack", "attacks", "attacked", "airstrike", "airstrikes", "strike", "strikes",
    "retaliation", "retaliatory", "ceasefire", "ship", "vessel", "tanker", "missile",
    "drone", "closure", "closed", "reopen", "war",
]

SECTORS = [
    (
        "ì¤‘êµ­ ìˆ˜ì¶œí†µì œ/í•µì‹¬ì†Œìž¬",
        [
            "mofcom", "china ministry of commerce", "export ban", "export suspension", "export licensing",
            "helium", "rare earth", "gallium", "germanium", "graphite", "antimony", "tungsten", "indium",
        ],
    ),
    ("ë°˜ë„ì²´/AI", ["ai", "chip", "hbm", "micron", "nvidia", "semiconductor", "tsmc", "asml", "hynix", "samsung", "broadcom", "amd", "intel", "arm", "apple", "microsoft", "oracle"]),
    ("ë°ì´í„°ì„¼í„°/ì „ë ¥ë§/ì „ë ¥ê¸°ê¸°", ["data center", "data centers", "city council", "moratorium", "ordinance", "permit", "planning commission", "public hearing", "residents", "township", "zoning", "grid", "power", "ferc", "doe", "server", "network", "cooling"]),
    ("DOE ì „ë ¥ë§/ì›ì „/ì—ë„ˆì§€ì§€ì›", ["doe", "department of energy", "loan guarantee", "conditional commitment", "funding opportunity", "grid deployment", "nuclear fuel", "critical materials", "efficiency standard", "ap1000"]),
    ("ì „ë ¥ë§ ë³´ì•ˆ/FCC ìž¥ë¹„ê·œì œ", ["fcc", "national security", "covered list", "equipment authorization", "foreign equipment", "inverter", "solar inverter", "communications supply chain"]),
    ("ê´€ì„¸/ìˆ˜ì¶œí†µì œ", ["export control", "section 301", "section 232", "tariff", "quota", "safeguard", "anti-dumping", "bis", "ustr", "commerce", "ofac", "sanction"]),
    ("EU/í•œêµ­ ì •ì±… ì˜í–¥", ["eu", "european union", "european commission", "south korea", "korean", "korea", "cbam", "steel", "quota", "safeguard", "anti-dumping"]),
    ("ë°©ì‚°/ì •ìœ /í•´ìš´/ì§€ì •í•™", ["hormuz", "iran", "israel", "oil", "red sea", "shipping", "ukraine"]),
    ("ì›ìžìž¬/ë§¤í¬ë¡œ", ["oil", "natural gas", "copper", "lithium", "uranium", "gold", "dollar", "won", "yield", "fed", "real yield", "tips"]),
    ("ë°”ì´ì˜¤/FDA", ["fda", "clinical", "crl", "pharma"]),
    ("í•œêµ­ ì§ì ‘ ì˜í–¥", ["samsung", "sk hynix", "korea", "lg energy", "hyundai"]),
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


def source_content_text(row: dict) -> str:
    """Return source-authored subject text without collector query labels."""
    return norm(
        " ".join(
            str(value or "")
            for value in [
                row.get("source_title") or row.get("title"),
                row.get("source_abstract") or row.get("summary"),
                row.get("publisher"),
                row.get("link"),
            ]
        )
    )


def fetch(url: str, timeout: int | None = None) -> tuple[str | None, str | None]:
    timeout = FETCH_TIMEOUT_SECONDS if timeout is None else timeout
    if urllib.parse.urlparse(url).netloc.lower().endswith("bing.com"):
        req = urllib.request.Request(
            url,
            headers={
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/124 Safari/537.36",
                "Accept": "application/rss+xml, text/xml, */*",
            },
        )
        try:
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                charset = resp.headers.get_content_charset() or "utf-8"
                return resp.read().decode(charset, "replace"), None
        except Exception as exc:
            return None, f"{type(exc).__name__}: {exc}"
    return fetch_text(
        url,
        UA,
        timeout=timeout,
        attempts=1,
        accept="application/rss+xml, application/json, text/html, */*",
    )


def fetch_fred_csv(timeout: int = 60) -> tuple[str | None, str | None]:
    req = urllib.request.Request(FRED_CSV, headers={"User-Agent": "Mozilla/5.0", "Accept": "text/csv,*/*"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return resp.read().decode("utf-8", "replace"), None
    except Exception as exc:
        return None, f"{type(exc).__name__}: {exc}"


def parse_dateß¾´¶‰žËkºwµç}7
ß®ÂÇ²VªÒ ƒ¶n²4ƒ¶fW²vã²vÐƒ²^ªÆÃ®
`]Q$½	É•¹Ó
ß²jÓ²z
ÝUM½-I_
ß®Â§²
Ã²ŽóªÂ ƒ®>g¶Z'¶Vc²ž ƒ²V+²ró®¦Ðƒ®.£®Âs²Äƒ²Ú§®>3®†pƒ²V÷¶fPˆ(€€€•±¥˜±½…±}‘}Á½±¥äè(€€€€€€€¥¹Ñ•ÉÀ€ô€‹®¾ãªÖ´ƒ²ž²^´ƒ®.£²rƒ®6Ã²vÓ¶Ã²ó¶Àƒªâ#²ž
ß®ª£®vó¶ƒ®š³²^
ß²Žó®¾ó¶"³¶Fs®*P$Ac²v`ƒ²*ç²vàƒ².sªÂ¶Fs²f ƒ²‚®‚—®žtƒ²‚G²4ƒ¶R®š³®¾ã²^²vƒ®ÂSªúã®*Pƒ²†ÃªâÀƒ².ƒ¶bã²z®.#®.¸ƒ¶fW²‚Tƒ®ž“²Ús²v ƒ²V®.#²ž®ž0ƒ²‚®‚—ªâÃªâÃ
ß²‚²ƒ
ß®'ªÂ
ß²nC²‚¿ªÂ²*“
ß²s®Êƒ®Âã®–c²ÊÓ²vã²v`ƒ¶Vƒ²vã²r£ªÎðƒ²"c²ŽðƒªÂ².s²Ç²vƒ²‚CªÊ¶VÓ²Vðƒ¶V§®.#®.¸ˆ(€€€€€€€™…¥°€ô€‹².s²vc¶j0ƒ²V#ªÆÓ
ß²†Ã®†
ß¶"³¶Fpƒ²vó²‚Tƒ®NÄƒªÎ×².tƒ¶n²4ƒ¶fW²vã²vÐƒ²^ªÆÃ®
`ƒ®æ¶3¶°A`¿²‚®‚—ªâÃªâÀƒ²"c²Žðƒ²‚®žw²vÐƒ²rƒ²ž®Bc®¦Ðƒ²ž²^·²Äƒ®&Ó²*“®†pƒ²V÷¶fPˆ(€€€•±¥˜€‹®6Ã²vÓ¶Ã²ó¶À¿²‚®‚—®žt¿²‚®‚—ªâÃªâÀˆ¥¸Í•Ñ½ÉÌè(€€€€€€€¥¹Ñ•ÉÀ€ô€‰$ƒ²vã¶R®vðƒ®ÎG®ª§²vÐAW®ž3²vÐƒ²V®.#®vðƒ²‚®‚—
ß²z²ž
ß²Žó®¾ó²"c²j§²Ç²ró®†pƒ®Ê#²ž®*S²ž ƒ®ÎÓ®*Pƒ²z³®Ž3²z®.#®.¸ƒ¶VsªÖ·²z—²^C²s®*Pƒ²‚®‚—ªâÃªâÃ²f ƒ®6Ã²vÓ¶Ã²ó¶Àƒ®Âã®–c²ÊÓ²vàƒ¶R®š³®¾ã²^ƒ²ž²7²Ç²vƒ²‚CªÊ¶VÓ²Vðƒ¶V§®.#®.¸ˆ(€€€€€€€™…¥°€ô€‹²‚®‚—ªâÃªâÃ
ß²‚²ƒ
ß²nC²‚
ß®'ªÂ
ß²s®Êƒ®Âã®–c²ÊÓ²vã²vÐƒ®RÃ®vó²b“²ž ƒ²V+ªÆÃ®
`ƒªÎ×².tƒ®²ã²sªÂ ƒ¶fW²vã®Bc²ž ƒ²V+²ró®¦Ðƒ²z³®Ž0ƒ²V÷¶fPˆ(€€€•±¥˜€‹®Âc®>²ÊÐ½$ˆ¥¸Í•Ñ½ÉÌè(€€€€€€€¥¹Ñ•ÉÀ€ô€‰'
ß®¦S®ª£®š°ƒ²"c²jPƒ®bC®*PƒªÎ×ªâ$ƒ²‚s¶Vs²vƒªÆÓ®Ns®šÐƒ²"`ƒ²z#²ZÐƒ¶VsªÖ´ƒ®Âc®>²ÊÐƒ®2¶bW²Žó²f ƒ²3®Ú²z”ƒ²"cªâ'²^@ƒ²^ÃªÊÃ®B§®.#®.¸ƒ¶VÓ²fàƒ¶.Ã²îƒ®Âc²vG²ró®†pƒ²vÓ®¾àƒ®Âc²b®BC®*S²ž ƒ²z³¶fW²vã²vÐƒ¶V²jS¶V§®.#®.¸ˆ(€€€€€€€™…¥°€ô€‰M=`½5T½9Y¿®¦S®ª£®š°ƒªÂªÊ§²vÐƒ®Âc²vG¶Vc²ž ƒ²V+ªÆÃ®
`ƒªÂ²vÓ®6c²*“ªÂ ƒ²"c²jPƒ®FS¶fS®–ðƒ².s²
³¶Vc®¦Ðƒ².“¶2 ˆ(€€€•±¥˜€‹²nC²zC²z°¿®ž“¶³®†pˆ¥¸Í•Ñ½ÉÌè(€€€€€€€¥¹Ñ•ÉÀ€ô€‹²nC²zC²z°ƒªÂªÊ§
ß®.³®~³
ß².“²ž#ªâ#®š³®*Pƒ¶VsªÖ·²z”ƒ²vÓ²vÔƒ²ÚS²‚WªÎðƒ¶Vƒ²vã²r£²vƒ®>g².s²^@ƒ¶vS®Ns®*Pƒ²ÚW²z®.#®.¸ƒ².“²‚pƒªÂªÊ¤ƒ²ž¶Fs²f ƒ¶fc²r£²vÐƒ®>g¶Z'¶Vc®*S²ž €ÀØèÔÀƒ²"c²æc²^C²pƒ²z³¶fW²vã¶VÓ²Vðƒ¶V§®.#®.¸ˆ(€€€€€€€™…¥°€ô€‹²rƒªÂ
ßªâ#®š³
ß®.³®~³
ß²nC¶fS
ß²nC²zC²z°ƒªÂªÊ§²vÐƒ®>g¶Z'¶Vc²ž ƒ²V+ªÆÃ®
`ƒ¶Vc®Ž£²žs®š°ƒ¶^“®Ns®vó²vã²^@ƒªÞã²æc®¦Ðƒ²z³®Ž0ƒ²V÷¶fPˆ(€€€•±Í”è(€€€€€€€¥¹Ñ•ÉÀ€ô€‹®> ƒ®Ê®*Pƒ®*—®‚”°ƒ¶Vƒ²vã²r °ƒ²"cªâ$°ƒ².sªÂ¶Fpƒ²’Dƒ¶Vc®
c®–ðƒ®ÂSªþ ƒ²"`ƒ²z#®*Pƒ¶n®ÎÓ²z®.#®.¸ƒ²nC®²àƒ²†ÃªÆÓªÎðƒªÂªÊ¤ƒ®Âc²vG²vƒ²z—²‚ƒ²"c²æc²^C²pƒ²z³¶fW²vã¶VÓ²Vðƒ¶V§®.#®.¸ˆ(€€€€€€€™…¥°€ô€‹ªÒ®‚ ƒ¶VÓ²fàƒ¶.Ã²î“
ß²nC²zC²z³
ßªâ#®š³
ß¶fc²r£
ß¶VsªÖ´ƒ²"cªâ'²vÐƒ®>g¶Z'¶Vc²ž ƒ²V+²ró®¦Ðƒ®.£®Âs²Äƒ®&Ó²*ˆ(€€€É•ÑÕÉ¸ì(€€€€€€€€‰Í½É”ˆèÍ½É”°(€€€€€€€€‰¥µÁ½ÉÑ…¹”ˆè¥µÁ½ÉÑ…¹”°(€€€€€€€€‰ÍÑ…ÑÕÌˆèÍÑ…ÑÕÌ°(€€€€€€€€‰¹•ÝÌˆèÑ¥Ñ±”°(€€€€€€€€‰Í½ÕÉ•}Ñ¥Ñ±”ˆè±•…¸¡É½Ü¹•Ð ‰Í½ÕÉ•}Ñ¥Ñ±”ˆ¤½ÈÑ¥Ñ±”¤°(€€€€€€€€‰Í½ÕÉ•}…‰ÍÑÉ…Ðˆè±•…¸¡É½Ü¹•Ð ‰Í½ÕÉ•}…‰ÍÑÉ…Ðˆ¤½ÈÉ½Ü¹•Ð ‰ÍÕµµ…Éäˆ¤¤°(€€€€€€€€‰Í½ÕÉ•}‘½Õµ•¹Ñ}¹Õµ‰•Èˆè±•…¸¡É½Ü¹•Ð ‰Í½ÕÉ•}‘½Õµ•¹Ñ}¹Õµ‰•Èˆ¤¤°(€€€€€€€€‰Í½ÕÉ•}µ•Ñ…‘…Ñ…}ÕÉ°ˆè±•…¸¡É½Ü¹•Ð ‰Í½ÕÉ•}µ•Ñ…‘…Ñ…}ÕÉ°ˆ¤¤°(€€€€€€€€‰ÁÕ‰±¥Í¡•ÈˆèÉ½Ü¹•Ð ‰ÁÕ‰±¥Í¡•Èˆ¤½ÈÉ½Ü¹•Ð ‰Í½ÕÉ”ˆ¤°(€€€€€€€€‰Í½ÕÉ”ˆèÉ½Ü¹•Ð ‰Í½ÕÉ”ˆ¤°(€€€€€€€€‰±¥¹¬ˆèÉ½Ü¹•Ð ‰±¥¹¬ˆ¤½È€ˆˆ°(€€€€€€€€‰ÁÕ‰±¥Í¡•ˆèÉ½Ýl‰ÁÕ‰±¥Í¡•‰t¹¥Í½™½Éµ…Ð¡Ñ¥µ•ÍÁ•Œô‰µ¥¹ÕÑ•Ìˆ¤¥˜É½Ü¹•Ð ‰ÁÕ‰±¥Í¡•ˆ¤•±Í”€‹¶fW²vàƒ®Ú#ªÂ ˆ°(€€€€€€€€‰¥µÁ…ÑÌˆè¥µÁ…ÑÌ°(€€€€€€€€‰Á…Ñ¡Ìˆèl‹²vÓ²vÔˆ¥˜à€ôô€‹®> ƒ®Ê®*Pƒ®*—®‚”ˆ•±Í”€‹¶Vƒ²vã²r ˆ¥˜à€ôô€‹¶Vƒ²vã²r ˆ•±Í”€‹²"cªâ$ˆ¥˜à€ôô€‹²"cªâ$ˆ•±Í”€‹²‚W²Æƒ¶²z®vó²vàˆ™½Èà¥¸¥µÁ…ÑÍt°(€€€€€€€€‰Í•Ñ½ÉÌˆèÍ•Ñ½ÉÌ°(€€€€€€€€‰µ…Ñ¡•ˆèµ…Ñ¡•‘lèÄÁt°(€€€€€€€€‰±½…±}‘}Á½±¥äˆè±½…±}‘}Á½±¥ä°(€€€€€€€€‰¥É…¹}¡½ÉµÕé}•Í…±…Ñ¥½¸ˆè¥É…¹}¡½ÉµÕé}•Í…±…Ñ¥½¸°(€€€€€€€€‰É•…±Ñ¥µ•}Á½±¥å}±…¹”ˆè¥É…¹}¡½ÉµÕé}•Í…±…Ñ¥½¸°(€€€€€€€€‰É•™±•Ñ¥½¸ˆè€‹®
»²v0ˆ¥˜…”¥Ì¹½Ð9½¹”…¹…”€ðô€Ø•±Í”€‹²’GªÂˆ¥˜…”¥Ì9½¹”½È…”€ðô€ÈÐ•±Í”€‹®K²v0ˆ°(€€€€€€€€‰½Õ¹Ñ•Èˆè€‹²‚s®ª§
ß²jS²VôƒªâÃ®Â`€Ç²Â ƒªÂC²ž®vðƒ²nC®²àƒ²ã®Ú²†ÃªÆÓªÎðƒªÎ×².tƒ®²ã²pƒ¶fW²vàƒ²‚ƒªÎó®2¶VÓ²tƒªÂ®*”ˆ¥˜ÍÑ…ÑÕÌ€„ô€‹¶fW²‚Tˆ•±Í”€‹².s¶Z'²vð°ƒ²‚²j¤ƒ®2²°ƒªâ#²V„°ƒªâÃªÂ°ƒ®>²‚C²Ä°ƒ®ž“²Úpƒ²vã².tƒ²†ÃªÆÐƒ¶fW²vàƒ²‚ƒ²b¶Z—²vÐƒ²‚s¶Vs®B€ƒ²"`ƒ²z#²v0ˆ°(€€€€€€€€‰¥¹Ñ•ÉÁÉ•Ñ…Ñ¥½¸ˆè¥¹Ñ•ÉÀ°(€€€€€€€€‰™…¥±•‘}Í¥¹…°ˆè™…¥°°(€€€€€€€€‰­½É•…}‰…Í¥Ìˆè€‹²b#ªÎƒ®Bpƒ²vÓ®Ê“¶*ã²v`ƒªÎ×².w¶fPˆ¥˜ÍÑ…ÑÕÌ€ôô€‹¶fW²‚Tˆ•±Í”€‹²fã².€ƒ¶fW²
Àˆ°(€€€ô(()‘•˜½±±•Ñ}‘™¥¤ÄÀ ¤€´ø‘¥Ðè(€€€¥˜I}A%}-dè(€€€€€€€ÕÉ°€ô€‰¡ÑÑÁÌè¼½…Á¤¹ÍÑ±½Õ¥Í™•¹½Éœ½™É•½Í•É¥•Ì½½‰Í•ÉÙ…Ñ¥½¹Ìüˆ€¬ÕÉ±±¥ˆ¹Á…ÉÍ”¹ÕÉ±•¹½‘”¡ì‰Í•É¥•Í}¥ˆè€‰%$ÄÀˆ°€‰™¥±•}ÑåÁ”ˆè€‰©Í½¸ˆ°€‰Í½ÉÑ}½É‘•Èˆè€‰‘•ÍŒˆ°€‰±¥µ¥Ðˆè€ˆÄÀˆ°€‰…Á¥}­•äˆèI}A%}-eô¤(€€€€€€€Ñ•áÐ°•ÉÈ€ô™•Ñ ¡ÕÉ°°€ÌÀ¤(€€€€€€€¥˜¹½Ð•ÉÈ…¹Ñ•áÐè(€€€€€€€€€€€™½ÈÉ½Ü¥¸©Í½¸¹±½…‘Ì¡Ñ•áÐ¤¹•Ð ‰½‰Í•ÉÙ…Ñ¥½¹Ìˆ°mt¤è(€€€€€€€€€€€€€€€¥˜É½Ü¹•Ð ‰Ù…±Õ”ˆ¤…¹É½Ü¹•Ð ‰Ù…±Õ”ˆ¤€„ô€ˆ¸ˆè(€€€€€€€€€€€€€€€€€€€É•ÑÕÉ¸ì‰Í½ÕÉ”ˆè€‰IA$%$ÄÀˆ°€‰ÍÑ…ÑÕÌˆè€‹¶fW²vã®B ˆ°€‰É•™•É•¹”ˆèÉ½Ü¹•Ð ‰‘…Ñ”ˆ¤°€‰Ù…±Õ”ˆè™±½…Ð¡É½Ü¹•Ð ‰Ù…±Õ”ˆ¤¤°€‰•ÉÉ½Èˆè9½¹•ô(€€€Ñ•áÐ°•ÉÈ€ô™•Ñ¡}™É•‘}ÍØ ØÀ¤(€€€¥˜•ÉÈ½È¹½ÐÑ•áÐè(€€€€€€€É•ÑÕÉ¸ì‰Í½ÕÉ”ˆèI}MX°€‰ÍÑ…ÑÕÌˆè€‹¶fW²vàƒ®Ú#ªÂ ˆ°€‰É•™•É•¹”ˆè€‹¶fW²vàƒ®Ú#ªÂ ˆ°€‰Ù…±Õ”ˆè9½¹”°€‰•ÉÉ½Èˆè•ÉÉô(€€€™½ÈÉ½Ü¥¸É•Ù•ÉÍ•¡±¥ÍÐ¡ÍØ¹¥ÑI•…‘•È¡Ñ•áÐ¹ÍÁ±¥Ñ±¥¹•Ì ¤¤¤¤è(€€€€€€€¥˜É½Ü¹•Ð ‰%$ÄÀˆ¤…¹É½Ü¹•Ð ‰%$ÄÀˆ¤€„ô€ˆ¸ˆè(€€€€€€€€€€€É•ÑÕÉ¸ì‰Í½ÕÉ”ˆèI}MX°€‰ÍÑ…ÑÕÌˆè€‹¶fW²vã®B ˆ°€‰É•™•É•¹”ˆèÉ½Ü¹•Ð ‰½‰Í•ÉÙ…Ñ¥½¹}‘…Ñ”ˆ¤°€‰Ù…±Õ”ˆè™±½…Ð¡É½Ü¹•Ð ‰%$ÄÀˆ¤¤°€‰•ÉÉ½Èˆè9½¹•ô(€€€É•ÑÕÉ¸ì‰Í½ÕÉ”ˆèI}MX°€‰ÍÑ…ÑÕÌˆè€‹¶fW²vàƒ®Ú#ªÂ ˆ°€‰É•™•É•¹”ˆè€‹¶fW²vàƒ®Ú#ªÂ ˆ°€‰Ù…±Õ”ˆè9½¹”°€‰•ÉÉ½Èˆè€‰±…Ñ•ÍÐ¹½¸µ•µÁÑäÉ½Ü¹½Ð™½Õ¹‰ô(()‘•˜½±±•Ñ}Ñ” ¤€´ø‘¥Ðè(€€€Ñ•áÐ°•ÉÈ€ô™•Ñ ¡Q}UI0¤(€€€¥˜•ÉÈ½È¹½ÐÑ•áÐè(€€€€€€€É•ÑÕÉ¸ì‰Í½ÕÉ”ˆèQ}UI0°€‰ÍÑ…ÑÕÌˆè€‹¶fW²vàƒ®Ú#ªÂ ˆ°€‰É•™•É•¹”ˆè€‹¶fW²vàƒ®Ú#ªÂ ˆ°€‰Ù…±Õ”ˆè9½¹”°€‰•ÉÉ½Èˆè•ÉÉô(€€€‰½‘ä€ô±•…¸¡Ñ•áÐ¤(€€€É½Ü€ôÉ”¹Í•…É ¡È‰UMqÌ¬ÄÁeqÌ­Q%AMqÌ¬ ´ýq¬ üép¹q¬¤ü¥qÌ¬ ´ýq¬ üép¹q¬¤ü¤•qÌ¬ ´ýq¬ üép¹q¬¤ü¤•qÌ¬ ´ýq¬ üép¹q¬¤ü¤•qÌ¬¡mµi„µéuìÍô½q‘ìÄ°Éô¤ˆ°‰½‘ä°É”¹$¤(€€€µ•Ñ„€ôÉ”¹Í•…É ¡ÈˆÄÀe•…ÈQ%ALe¥•±¹ìÀ°ÄÔÁôü ´ýq¬ üép¹q¬¤ü¥qÌ¨ üè•ñÁ•É•¹Ð¥qÌ­½¹qÌ¬¡mµi„µét¬q‘ìÄ°Éô°q‘ìÑô¤ˆ°‰½‘ä°É”¹$¤(€€€¥˜É½Üè(€€€€€€€É•ÑÕÉ¸ì‰Í½ÕÉ”ˆèQ}UI0°€‰ÍÑ…ÑÕÌˆè€‹¶fW²vã®B ˆ°€‰É•™•É•¹”ˆèÉ½Ü¹É½ÕÀ Ô¤°€‰Ù…±Õ”ˆè™±½…Ð¡É½Ü¹É½ÕÀ Ä¤¤°€‰µ•Ñ…}Ù…±Õ”ˆè™±½…Ð¡µ•Ñ„¹É½ÕÀ Ä¤¤¥˜µ•Ñ„•±Í”9½¹”°€‰µ•Ñ…}É•™•É•¹”ˆèµ•Ñ„¹É½ÕÀ È¤¥˜µ•Ñ„•±Í”9½¹”°€‰•ÉÉ½Èˆè9½¹•ô(€€€¥˜µ•Ñ„è(€€€€€€€É•ÑÕÉ¸ì‰Í½ÕÉ”ˆèQ}UI0°€‰ÍÑ…ÑÕÌˆè€‹¶fW²vã®B ˆ°€‰É•™•É•¹”ˆèµ•Ñ„¹É½ÕÀ È¤°€‰Ù…±Õ”ˆè™±½…Ð¡µ•Ñ„¹É½ÕÀ Ä¤¤°€‰•ÉÉ½Èˆè9½¹•ô(€€€É•ÑÕÉ¸ì‰Í½ÕÉ”ˆèQ}UI0°€‰ÍÑ…ÑÕÌˆè€‹¶fW²vàƒ®Ú#ªÂ ˆ°€‰É•™•É•¹”ˆè€‹¶fW²vàƒ®Ú#ªÂ ˆ°€‰Ù…±Õ”ˆè9½¹”°€‰•ÉÉ½Èˆè€‰Á…ÑÑ•É¸¹½Ð™½Õ¹‰ô(()‘•˜É•…±}å¥•±‘}¹½Ñ”¡™É•è‘¥Ð°Ñ”è‘¥Ð¤€´øÍÑÈè(€€€¥˜™É•¹•Ð ‰Ù…±Õ”ˆ¤¥Ì9½¹”½ÈÑ”¹•Ð ‰Ù…±Õ”ˆ¤¥Ì9½¹”è(€€€€€€€É•ÑÕÉ¸€‰I%$ÄÀƒ®bC®*PQÉ…‘¥¹œ½¹½µ¥Ì€ÄÁdQ%ALƒ²’Dƒ¶Vc®
cªÂ ƒ¶fW²vã®Bc²ž ƒ²V+²Vƒ¶Vƒ²vã²r ƒªÖC²Â£¶fW²vàƒ®Ú#²f²‚ˆ(€€€µ¥Íµ…Ñ €ô…‰Ì¡™±½…Ð¡™É•‘l‰Ù…±Õ”‰t¤€´™±½…Ð¡Ñ•l‰Ù…±Õ”‰t¤¤€øô€À¸ÀÌ½ÈÍÑÈ¡™É•¹•Ð ‰É•™•É•¹”ˆ¤¤€„ôÍÑÈ¡Ñ”¹•Ð ‰É•™•É•¹”ˆ¤¤(€€€ÍÑ…Ñ”€ô€‹²ž²^À¿®Ú#²vó²æ`ƒ²z#²v0ˆ¥˜µ¥Íµ…Ñ •±Í”€‹ªÖC²Â£¶fW²vã®B ˆ(€€€É•ÑÕÉ¸˜‰íÍÑ…Ñ•ôèI%$ÄÀí™É•‘lÙ…±Õ”tè¸É™ô”¡í™É•¹•Ð É•™•É•¹”œ¥ô¤°QÉ…‘¥¹œ½¹½µ¥Ì€ÄÁdQ%ALíÑ•lÙ…±Õ”tè¸É™ô”¡íÑ”¹•Ð É•™•É•¹”œ¥ô¤ˆ(()‘•˜É•±…Ñ•¡…±•ÉÐè‘¥Ð°™É•è‘¥Ð°Ñ”è‘¥Ð¤€´øÍÑÈè(€€€½ÕÐ€ômt(€€€¥˜€‹®Âc®>²ÊÐ½$ˆ¥¸…±•ÉÑl‰Í•Ñ½ÉÌ‰tè(€€€€€€€½ÕÐ€¬ôl‰9Yˆ°€‰5Tˆ°€‰Y<ˆ°€‰5ˆ°€‰QM4ˆ°€‰M50ˆ°€‰M=`‰t(€€€¥˜€‹®6Ã²vÓ¶Ã²ó¶À¿²‚®‚—®žt¿²‚®‚—ªâÃªâÀˆ¥¸…±•ÉÑl‰Í•Ñ½ÉÌ‰tè(€€€€€€€½ÕÐ€¬ôl‰YIPˆ°€‰Q8ˆ°€‰Xˆ°€‰ˆ°€‰M5 ‰t(€€€¥˜€‰=ƒ²‚®‚—®žt¿²nC²‚¿²^C®#²ž²ž²n@ˆ¥¸…±•ÉÑl‰Í•Ñ½ÉÌ‰tè(€€€€€€€½ÕÐ€¬ôl‰=ˆ°€‰Iˆ°€‰9Iˆ°€‰@ÄÀÀÀˆ°€‰]•ÍÑ¥¹¡½ÕÍ”ˆ°€‰YIPˆ°€‰Q8ˆ°€‰Xˆ°€‰UÉ…¹¥Õ´‰t(€€€¥˜€‹²‚®‚—®žtƒ®ÎÓ²V ½ƒ²z—®æªÞs²‚pˆ¥¸…±•ÉÑl‰Í•Ñ½ÉÌ‰tè(€€€€€€€½ÕÐ€¬ôl‰M1Hˆ°€‰9A ˆ°€‰Mˆ°€‰YIPˆ°€‰Q8ˆ°€‰X‰t(€€€¥˜€‰T¿¶VsªÖ´ƒ²‚W²Æƒ²b¶Z”ˆ¥¸…±•ÉÑl‰Í•Ñ½ÉÌ‰tè(€€€€€€€½ÕÐ€¬ôl‰Tƒ²‚W²Æ®²ã²pˆ°€‹²ÊƒªÂT¿®ÂÃ¶Ã®š°¿®Âc®>²ÊÐ¿²†Ã²€ƒ²"c²Ús²Žðˆ°€‰UH½-I\‰t(€€€¥˜€‹®Â§²
À¿²‚W²r€¿¶VÓ²jÐ¿²ž²‚W¶Vdˆ¥¸…±•ÉÑl‰Í•Ñ½ÉÌ‰tè(€€€€€€€½ÕÐ€¬ôl‰]Q$ˆ°€‰	É•¹Ðˆ°€‰a1ˆ°€‹²jÓ²z‰t(€€€¥˜€‹²nC²zC²z°¿®ž“¶³®†pˆ¥¸…±•ÉÑl‰Í•Ñ½ÉÌ‰tè(€€€€€€€½ÕÐ€¬ôl‹®¾ãªÖ´€ÄÃ®®²ðˆ°€‰adˆ°€‰UM½-I\ˆ°€‰]Q$ˆ°€‰!•¹Éä!Õˆˆ°€‰½ÁÁ•Èˆ°€‰1¥Ñ¡¥Õ´ˆ°€‰UÉ…¹¥Õ´ˆ°€‰½±‰t(€€€¥˜€‹¶Vƒ²vã²r ˆ¥¸…±•ÉÑl‰¥µÁ…ÑÌ‰tè(€€€€€€€½ÕÐ€¬ôm˜‰%$ÄÀí™É•¹•Ð Ù…±Õ”œ¤¥˜™É•¹•Ð Ù…±Õ”œ¤¥Ì¹½Ð9½¹”•±Í”€Ÿ¶fW²vàƒ®Ú#ªÂ ôˆ°˜‰Q€ÄÁdQ%ALíÑ”¹•Ð Ù…±Õ”œ¤¥˜Ñ”¹•Ð Ù…±Õ”œ¤¥Ì¹½Ð9½¹”•±Í”€Ÿ¶fW²vàƒ®Ú#ªÂ ôˆ°€‰%]4½MAdƒ²z³¶fW²và‰t(€€€É•ÑÕÉ¸€ˆ°€ˆ¹©½¥¸¡‘¥Ð¹™É½µ­•åÌ¡½ÕÐ¤¤½È€‹¶fW²vàƒªÂ®*—¶Vpƒ²ž²‚Dƒ¶.Ã²îƒ²^²v0ˆ(()‘•˜É•¹‘•É}…±•ÉÐ¡…±•ÉÐè‘¥Ð°¥‘àè¥¹Ð°¹½Üè‘Ð¹‘…Ñ•Ñ¥µ”°™É•è‘¥Ð°Ñ”è‘¥Ð¤€´øÍÑÈè(€€€É•ÑÕÉ¸€‰q¸ˆ¹©½¥¸¡l(€€€€€€€˜ˆŒŒí¥‘áô¸mí…±•ÉÑl¥µÁ½ÉÑ…¹”uôðí…±•ÉÑlÍÑ…ÑÕÌuõtˆ°(€€€€€€€˜ˆ´ƒ®&Ó²*‘€èí…±•ÉÑl¹•ÝÌuôˆ°(€€€€€€€˜ˆ´ƒ¶VsªÖ·²z”ƒªâÃ²’€èí…±•ÉÑl­½É•…}‰…Í¥Ìuôˆ°(€€€€€€€˜ˆ´ƒ¶²z®vó²vá€èƒ²Ös²Ò ƒ®æ3®Ns²^èƒ¶fW²vàƒ®Ú#ªÂ €¼ƒªÎ×².w
ß²nC²Êpƒ².sªÂèí…±•ÉÑlÁÕ‰±¥Í¡•uô€¼ƒ¶VsªÖ´ƒ¶"³²zC²z@ƒ¶fW²
Àèí¹½Üè•d´•´´•€• è•4-MQôƒ²†Ã¶j0ƒªâÃ²’ ˆ°(€€€€€€€˜ˆ´ƒ²Ús²Êa€èmí…±•ÉÑlÁÕ‰±¥Í¡•Èuõt¡í…±•ÉÑl±¥¹¬uô¤ƒ
Üƒ²†Ã¶j0í¹½Üè•d´•´´•€• è•4-MQôˆ°(€€€€€€€˜ˆ´ƒ²vc²
³ªÊÃ²‚Tƒ²b¶Z•€èìœ°€œ¹©½¥¸¡…±•ÉÑl¥µÁ…ÑÌt¥ôˆ°(€€€€€€€˜ˆ´ƒ²b¶Z”ƒªÊ÷®†q€èìœ°€œ¹©½¥¸¡…±•ÉÑlÁ…Ñ¡Ìt¥ôˆ°(€€€€€€€˜ˆ´ƒ²b¶Z”ƒ²ç¶Á€èìœ°€œ¹©½¥¸¡…±•ÉÑlÍ•Ñ½ÉÌt¥ôˆ°(€€€€€€€˜ˆ´ƒªÒ®‚ ƒ¶VÓ²fàƒ¶.Ã²î¿²ž¶Fq€èíÉ•±…Ñ•¡…±•ÉÐ°™É•°Ñ”¥ôˆ°(€€€€€€€˜ˆ´ƒ®Âc²bƒªÂ®*—²Å€èí…±•ÉÑlÉ•™±•Ñ¥½¸uôˆ°(€€€€€€€˜ˆ´ƒ®Âc®2 ƒªÞóªÆÁ€èí…±•ÉÑl½Õ¹Ñ•Èuôˆ°(€€€€€€€˜ˆ´ƒ¶VÓ²u€èí…±•ÉÑl¥¹Ñ•ÉÁÉ•Ñ…Ñ¥½¸uôˆ°(€€€€€€€˜ˆ´ƒ².“¶2 ƒ².ƒ¶bá€èí…±•ÉÑl™…¥±•‘}Í¥¹…°uôˆ°(€€€€€€€€ˆˆ°(€€€t¤(()‘•˜É•¹‘•É}É•Á½ÉÐ¡…±•ÉÑÌè±¥ÍÑm‘¥Ñt°¹½Ñ•Ìè±¥ÍÑmÍÑÉt°™É•è‘¥Ð°Ñ”è‘¥Ð°¹½Üè‘Ð¹‘…Ñ•Ñ¥µ”¤€´øÍÑÈè(€€€Ñ¥Ñ±”€ô˜‹Â~NÀ5)=ƒ²z—²‚ƒ¶V×².°ƒ®&Ó²*ƒ®‚#²vÓ®6Pƒ
Üí¹½Üè•g®€•·²nP€•“²vñôƒ
Ü€ÀØèÌÀˆ(€€€±¥¹•Ì€ôl(€€€€€€€Ñ¥Ñ±”°€ˆˆ°(€€€€€€€˜‹²†Ã¶j0ƒªâÃ²’ èí¹½Üè•d´•´´•€• è•4-MQô¸¥Ñ!ÕˆÑ¥½¹Ìƒ²fã®Ú ƒ®~³® ƒªâÃ²’²vÓ®¦À°ƒ®†s²î°½‘•à½Aƒ²‚#²‚ƒ²¶s²f ƒ®²ÓªÒ¶VcªÊ0ƒ².“¶Z'®B§®.#®.¸ˆ°€ˆˆ°(€€€€€€€€ˆŒŒŒƒ²zC®Ž0ƒ²Êc®š°ƒ¶b¶f§¶Fpˆ°(€€€€€€€€‰ðƒ¶V·®ª¤ðƒ²†Ã¶j0ƒ².sªÂðƒ²ž²‚Dƒ¶fW²vàðƒ²¶pðˆ°€‰ð´´µð´´´éð´´´éð´´µðˆ°(€€€€€€€˜‰ðƒ²z—²‚ƒ®&Ó²*ƒ²nC²Êpðí¹½Üè• è•4-MQôðíÍÕ´ Ÿ¶fW²vàƒ®Ú#ªÂ œ¹½Ð¥¸¸™½È¸¥¸¹½Ñ•Ì¥÷ªÂpƒ²nC²Êpðìœ€¼€œ¹©½¥¸¡¹½Ñ•ÍlèÕt¥ôðˆ°(€€€€€€€˜‰ðI%$ÄÀðí¹½Üè• è•4-MQôðìŸ²b œ¥˜™É•¹•Ð Ù…±Õ”œ¤¥Ì¹½Ð9½¹”•±Í”€Ÿ²V®.#²bôðí™É•¹•Ð ÍÑ…ÑÕÌœ¥ôƒ
Üí™É•¹•Ð É•™•É•¹”œ¥ôðˆ°(€€€€€€€˜‰ðQÉ…‘¥¹œ½¹½µ¥Ì€ÄÁdQ%ALðí¹½Üè• è•4-MQôðìŸ²b œ¥˜Ñ”¹•Ð Ù…±Õ”œ¤¥Ì¹½Ð9½¹”•±Í”€Ÿ²V®.#²bôðíÑ”¹•Ð ÍÑ…ÑÕÌœ¥ôƒ
ÜíÑ”¹•Ð É•™•É•¹”œ¥ôðˆ°(€€€€€€€€ˆˆ°˜‹¶Vƒ²vã²r ƒªÖC²Â£¶fW²vàèíÉ•…±}å¥•±‘}¹½Ñ”¡™É•°Ñ”¥ôˆ°€ˆˆ°(€€€t(€€€¥˜…±•ÉÑÌè(€€€€€€€™½È¥‘à°…±•ÉÐ¥¸•¹Õµ•É…Ñ”¡…±•ÉÑÍlèÝt°€Ä¤è(€€€€€€€€€€€±¥¹•Ì¹…ÁÁ•¹¡É•¹‘•É}…±•ÉÐ¡…±•ÉÐ°¥‘à°¹½Ü°™É•°Ñ”¤¤(€€€•±Í”è(€€€€€€€±¥¹•Ì€¬ôl‹²z—²‚ƒªÎƒ²Ú§ªÊ¤ƒ®&Ó²*ƒ²ž²‚Dƒ¶fW²vàƒ²^²v0ˆ°€ˆˆ°€‹ªÂC²‚W²Äƒ®&Ó²*“®†pƒ²‚s²fàèƒªÎ×².t¿².ƒ®ŠÀƒ²3²*“²^C²pƒ®> ƒ®Ê®*Pƒ®*—®‚”°ƒ¶Vƒ²vã²r °ƒ²"cªâ$°ƒ².sªÂ¶Fs®–ðƒ®ª¶fW¶z ƒ®ÂSªúã®*Pƒ¶n®ÎÓªÂ ƒ²ž²‚Dƒ¶fW²vã®Bc²ž ƒ²V+²v ƒ¶V·®ª¤¸ˆ°€ˆ‰t(€€€Ñ½À€ô…±•ÉÑÍlÁul‰¹•ÝÌ‰t¥˜…±•ÉÑÌ•±Í”€‹²z—²‚ƒªÎƒ²Ú§ªÊ¤ƒ®&Ó²*ƒ²ž²‚Dƒ¶fW²vàƒ²^²v0ˆ(€€€¡…¹•€ô€ˆ°€ˆ¹©½¥¸¡…±•ÉÑÍlÁul‰¥µÁ…ÑÌ‰t¤¥˜…±•ÉÑÌ•±Í”€‹®ª¶fW¶Vpƒ®Î¶fPƒ²^²v0ˆ(€€€±¥¹•Ì€¬ôl(€€€€€€€€‹Â~J„€ÀØèÌÀƒ²z—²‚ƒ®&Ó²*ƒ²öS®¦c¶*àˆ°(€€€€€€€˜‹²b“®*`€Ç²"s²rƒ²ÊÓ¶³®*PíÑ½Áõƒ²z®.#®.¸ƒ²b“®*`ƒªÂ²z”ƒ¶³ªÊ0ƒ®ÂS®@ƒ²ÚW²v í¡…¹•‘õƒ²vÓ®¦À°ƒ¶VsªÖ·²z—²^C²s®*PƒªÒ®‚ ƒ¶VÓ²fàƒ¶.Ã²îƒ®Âc²vGªÎðƒªÖ·®
Ðƒ²"cªâ$ƒ¶fW²
Àƒ²^³®Ú®–ðƒ®¢ó²‚ ƒ®ÎÓªÊƒ²*×®.#®.¸ˆ°(€€€€€€€˜‹¶Vƒ²vã²r£²v I%$ÄÃªÎðQÉ…‘¥¹œ½¹½µ¥Ì€ÄÀe•…ÈQ%ALe¥•±“®–ðƒ¶V£ªî`ƒ¶fW²vã¶Z#²*×®.#®.èíÉ•…±}å¥•±‘}¹½Ñ”¡™É•°Ñ”¥ô¸ˆ°(€€€€€€€€ˆÀØèÔÀƒ¶"³²zCªâÃ²®>²^C²pƒ²"c²æc
ß²"cªâ'
ß¶3®ž#²f ƒ²z³¶fW²vàƒ¶V²jP¸ˆ°€ˆˆ°(€€€€€€€€‹¶"³²z@ƒ²†Ã²Zã²vÐƒ²V®.0ƒ²ÂãªÎƒ²j¤ƒ®&Ó²*ƒ®â3®š³¶VG²z®.#®.¸ˆ°€ˆˆ°(€€€€€€€€‹²Žó²jPƒ²Ús²Ê`èˆ°€©m˜ˆ´í¹ôˆ™½È¸¥¸¹½Ñ•ÍlèÄáut°˜ˆ´I%$ÄÀèíI}MYôˆ°˜ˆ´QÉ…‘¥¹œ½¹½µ¥Ì€ÄÁdQ%ALèíQ}UI1ôˆ°(€€€t(€€€É•ÑÕÉ¸€‰q¸ˆ¹©½¥¸¡±¥¹•Ì¤¹ÍÑÉ¥À ¤€¬€‰q¸ˆ(()‘•˜Í•¹‘}Ñ•±•É…´¡Ñ•áÐèÍÑÈ¤€´ø9½¹”è(€€€Ñ½­•¸€ô½Ì¹•Ñ•¹Ø ‰Q1I5}	=Q}Q=-8ˆ°€ˆˆ¤¹ÍÑÉ¥À ¤(€€€¡…Ñ}¥€ô½Ì¹•Ñ•¹Ø ‰Q1I5}!Q}%ˆ°€ˆˆ¤¹ÍÑÉ¥À ¤(€€€¥˜¹½ÐÑ½­•¸½È¹½Ð¡…Ñ}¥è(€€€€€€€ÁÉ¥¹Ð ‰Q•±•É…´èQ1I5}	=Q}Q=-8½ÈQ1I5}!Q}%µ¥ÍÍ¥¹œˆ¤(€€€€€€€É•ÑÕÉ¸(€€€É•Á¼°ÉÕ¹}¥€ô½Ì¹•Ñ•¹Ø ‰%Q!U	}IA=M%Q=Idˆ°€ˆˆ¤°½Ì¹•Ñ•¹Ø ‰%Q!U	}IU9}%ˆ°€ˆˆ¤(€€€ÍÕ™™¥à€ô˜‰q¹q»²‚²ÊÐƒ®ÎÓªÎƒ²pè¡ÑÑÁÌè¼½¥Ñ¡Õˆ¹½´½íÉ•Á½ô½…Ñ¥½¹Ì½ÉÕ¹Ì½íÉÕ¹}¥‘ôˆ¥˜É•Á¼…¹ÉÕ¹}¥•±Í”€ˆˆ(€€€‰½‘ä€ôÕÉ±±¥ˆ¹Á…ÉÍ”¹ÕÉ±•¹½‘”¡ì‰¡…Ñ}¥ˆè¡…Ñ}¥°€‰Ñ•áÐˆè€¡Ñ•áÑlèQ1I5}1%5%P€´±•¸¡ÍÕ™™¥à¤€´€Åt€¬ÍÕ™™¥à¥léQ1I5}1%5%Qt°€‰‘¥Í…‰±•}Ý•‰}Á…•}ÁÉ•Ù¥•Üˆè€‰ÑÉÕ”‰ô¤¹•¹½‘” ‰ÕÑ˜´àˆ¤(€€€É•Ä€ôÕÉ±±¥ˆ¹É•ÅÕ•ÍÐ¹I•ÅÕ•ÍÐ¡˜‰¡ÑÑÁÌè¼½…Á¤¹Ñ•±•É…´¹½Éœ½‰½ÑíÑ½­•¹ô½Í•¹‘5•ÍÍ…”ˆ°‘…Ñ„õ‰½‘ä°µ•Ñ¡½ô‰A=MPˆ¤(€€€Ý¥Ñ ÕÉ±±¥ˆ¹É•ÅÕ•ÍÐ¹ÕÉ±½Á•¸¡É•Ä°Ñ¥µ•½ÕÐôÈÔ¤…ÌÉ•ÍÀè(€€€€€€€É•ÍÀ¹É•… ¤(€€€ÁÉ¥¹Ð ‰Q•±•É…´èÍ•¹Ðˆ¤(()‘•˜ÁÉ¥¹Ñ}ÕÑ˜à¡Ñ•áÐèÍÑÈ¤€´ø9½¹”è(€€€ÑÉäè(€€€€€€€ÍåÌ¹ÍÑ‘½ÕÐ¹ÝÉ¥Ñ”¡Ñ•áÐ¤(€€€•á•ÁÐU¹¥½‘•¹½‘•ÉÉ½Èè(€€€€€€€ÍåÌ¹ÍÑ‘½ÕÐ¹‰Õ™™•È¹ÝÉ¥Ñ”¡Ñ•áÐ¹•¹½‘” ‰ÕÑ˜´àˆ°€‰É•Á±…”ˆ¤¤(()‘•˜µ…¥¸ ¤€´ø¥¹Ðè(€€€¹½Ü€ô­ÍÑ}¹½Ü ¤(€€€É½ÝÌ°¹½Ñ•Ì€ô½±±•Ñ}¥Ñ•µÌ¡¹½Ü¤(€€€…±•ÉÑÌ€ôm„™½È„¥¸€¡±…ÍÍ¥™ä¡È°¹½Ü¤™½ÈÈ¥¸É½ÝÌ¥˜™É•Í ¡È°¹½Ü¤¤¥˜…t(€€€…±•ÉÑÌ¹Í½ÉÐ¡­•äõ±…µ‰‘„„è€ µ…l‰Í½É”‰t°…l‰ÁÕ‰±¥Í¡•‰t¤¤(€€€‘•‘ÕÁ•°Í••¸€ômt°Í•Ð ¤(€€€™½È…±•ÉÐ¥¸…±•ÉÑÌè(€€€€€€€­•ä€ô€¡¹½É´¡…±•ÉÑl‰¹•ÝÌ‰t¤°¹½É´¡…±•ÉÑl‰ÁÕ‰±¥Í¡•È‰t¤°…±•ÉÑl‰ÁÕ‰±¥Í¡•‰ulèÄÁt¤(€€€€€€€¥˜­•ä¥¸Í••¸è(€€€€€€€€€€€½¹Ñ¥¹Õ”(€€€€€€€Í••¸¹…‘¡­•ä¤(€€€€€€€‘•‘ÕÁ•¹…ÁÁ•¹¡…±•ÉÐ¤(€€€€€€€¥˜±•¸¡‘•‘ÕÁ•¤€øô€Üè(€€€€€€€€€€€‰É•…¬(€€€±½…±}‘}…¹‘¥‘…Ñ•Ì€ôm„™½È„¥¸…±•ÉÑÌ¥˜„¹•Ð ‰±½…±}‘}Á½±¥äˆ¥t(€€€™½È…¹‘¥‘…Ñ”¥¸±½…±}‘}…¹‘¥‘…Ñ•Ìè(€€€€€€€±½…±}½Õ¹Ð€ôÍÕ´ Ä™½È„¥¸‘•‘ÕÁ•¥˜„¹•Ð ‰±½…±}‘}Á½±¥äˆ¤¤(€€€€€€€¥˜±½…±}½Õ¹Ð€øôµ¥¸ È°±•¸¡±½…±}‘}…¹‘¥‘…Ñ•Ì¤¤è(€€€€€€€€€€€‰É•…¬(€€€€€€€­•ä€ô€¡¹½É´¡…¹‘¥‘…Ñ•l‰¹•ÝÌ‰t¤°¹½É´¡…¹‘¥‘…Ñ•l‰ÁÕ‰±¥Í¡•È‰t¤°…¹‘¥‘…Ñ•l‰ÁÕ‰±¥Í¡•‰ulèÄÁt¤(€€€€€€€¥˜­•ä¥¸Í••¸è(€€€€€€€€€€€½¹Ñ¥¹Õ”(€€€€€€€¥˜±•¸¡‘•‘ÕÁ•¤€ð€Üè(€€€€€€€€€€€‘•‘ÕÁ•¹…ÁÁ•¹¡…¹‘¥‘…Ñ”¤(€€€€€€€€€€€Í••¸¹…‘¡­•ä¤(€€€€€€€€€€€½¹Ñ¥¹Õ”(€€€€€€€™½È¥‘à¥¸É…¹”¡±•¸¡‘•‘ÕÁ•¤€´€Ä°€´Ä°€´Ä¤è(€€€€€€€€€€€¥˜¹½Ð‘•‘ÕÁ•‘m¥‘át¹•Ð ‰±½…±}‘}Á½±¥äˆ¤è(€€€€€€€€€€€€€€€½±€ô‘•‘ÕÁ•‘m¥‘át(€€€€€€€€€€€€€€€Í••¸¹‘¥Í…É ¡¹½É´¡½±‘l‰¹•ÝÌ‰t¤°¹½É´¡½±‘l‰ÁÕ‰±¥Í¡•È‰t¤°½±‘l‰ÁÕ‰±¥Í¡•‰ulèÄÁt¤¤(€€€€€€€€€€€€€€€‘•‘ÕÁ•‘m¥‘át€ô…¹‘¥‘…Ñ”(€€€€€€€€€€€€€€€Í••¸¹…‘¡­•ä¤(€€€€€€€€€€€€€€€‰É•…¬(€€€‘•‘ÕÁ•¹Í½ÉÐ¡­•äõ±…µ‰‘„„è€ µ…l‰Í½É”‰t°…l‰ÁÕ‰±¥Í¡•‰t¤¤(€€€™É•°Ñ”€ô½±±•Ñ}‘™¥¤ÄÀ ¤°½±±•Ñ}Ñ” ¤(€€€É•Á½ÉÐ€ôÉ•¹‘•É}É•Á½ÉÐ¡‘•‘ÕÁ•°¹½Ñ•Ì°™É•°Ñ”°¹½Ü¤(€€€=UP¹µ­‘¥È¡Á…É•¹ÑÌõQÉÕ”°•á¥ÍÑ}½¬õQÉÕ”¤(€€€€¡=UP€¼€‰…µ•©½…}ÁÉ•½Á•¹}¹•ÝÍ}É…‘…È¹µˆ¤¹ÝÉ¥Ñ•}Ñ•áÐ¡É•Á½ÉÐ°•¹½‘¥¹œô‰ÕÑ˜´àˆ¤(€€€€¡=UP€¼€‰…µ•©½…}ÁÉ•½Á•¹}¹•ÝÍ}É…‘…É}Ñ¥Ñ±”¹ÑáÐˆ¤¹ÝÉ¥Ñ•}Ñ•áÐ¡É•Á½ÉÐ¹ÍÁ±¥Ñ±¥¹•Ì ¥lÁt€¬€‰q¸ˆ°•¹½‘¥¹œô‰ÕÑ˜´àˆ¤(€€€€¡=UP€¼€‰…µ•©½…}ÁÉ•½Á•¹}¹•ÝÍ}É…‘…È¹©Í½¸ˆ¤¹ÝÉ¥Ñ•}Ñ•áÐ¡©Í½¸¹‘ÕµÁÌ¡ì‰ÅÕ•Éå}Ñ¥µ•}­ÍÐˆè¹½Ü¹¥Í½™½Éµ…Ð¡Ñ¥µ•ÍÁ•Œô‰Í•½¹‘Ìˆ¤°€‰…±•ÉÑÌˆè‘•‘ÕÁ•°€‰Í½ÕÉ•}¹½Ñ•Ìˆè¹½Ñ•Ì°€‰™É•‘}‘™¥¤ÄÀˆè™É•°€‰ÑÉ…‘¥¹•½¹½µ¥Í}Ñ¥ÁÌˆèÑ•ô°•¹ÍÕÉ•}…Í¥¤õ…±Í”°¥¹‘•¹ÐôÈ°‘•™…Õ±ÐõÍÑÈ¤€¬€‰q¸ˆ°•¹½‘¥¹œô‰ÕÑ˜´àˆ¤(€€€ÁÉ¥¹Ñ}ÕÑ˜à¡É•Á½ÉÐ¤(€€€¥˜½Ì¹•Ñ•¹Ø ‰Q1I5}Ie}IU8ˆ°€ˆˆ¤¹±½Ý•È ¤¥¸ìˆÄˆ°€‰ÑÉÕ”ˆ°€‰å•Ìˆ°€‰ä‰ôè(€€€€€€€ÁÉ¥¹Ð ‰Q•±•É…´è‘ÉäÉÕ¸ˆ¤(€€€€€€€É•ÑÕÉ¸€À(€€€¥˜½Ì¹•Ñ•¹Ø ‰M9}Q1I4ˆ°€ˆˆ¤¹±½Ý•È ¤¥¸ìˆÄˆ°€‰ÑÉÕ”ˆ°€‰å•Ìˆ°€‰ä‰ôè(€€€€€€€Í•¹‘}Ñ•±•É…´¡É•Á½ÉÐ¤(€€€É•ÑÕÉ¸€À(()¥˜}}¹…µ•}|€ôô€‰}}µ…¥¹}|ˆè(€€€É…¥Í”MåÍÑ•µá¥Ð¡µ…¥¸ ¤¤(