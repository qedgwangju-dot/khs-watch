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
        "appeal dismissed", "withdraws appeal", "voluntary dismissal", "íŒê²°", "í•­ì†Œ ì·¨í•˜", "ì§‘í–‰ì •ì§€", "ê°€ì²˜ë¶„",
    ],
    "final_rule": ["final rule", "finalizes", "effective date", "implementation", "interim final rule", "ìµœì¢… ê·œì¹™", "ì‹œí–‰ì¼"],
    "permit_restart": [
        "permit", "permitting", "approval", "authorization", "license", "lease", "leasing",
        "outer continental shelf", "ocs", "construction and operations plan", "cop", "record of decision",
        "environmental impact statement", "eis", "restarts", "resumes", "freeze", "pause", "í—ˆê°€", "ìŠ¹ì¸", "ë™ê²° í•´ì œ",
    ],
    "sanctions_tariffs_export": ["sanctions", "tariff", "section 301", "export controls", "entity list", "ofac", "bis", "ê´€ì„¸", "ì œì¬", "ìˆ˜ì¶œí†µì œ"],
    "china_trade_controls": [
        "export ban", "export bans", "export suspension", "suspend exports", "suspended exports",
        "export restriction", "export restrictions", "export licensing", "dual-use items",
        "anti-dumping", "antidumping", "countervailing", "tariff", "tariffs",
        "å‡ºå£ç®¡åˆ¶", "æš‚åœå‡ºå£", "åœæ­¢å‡ºå£", "ç¦æ­¢å‡ºå£", "å‡ºå£ç¦ä»¤", "å‡ºå£è®¸å¯",
        "æš‚åœ", "åœæ­¢", "ç¦æ­¢", "å‡ºå£",
        "ä¸¤ç”¨ç‰©é¡¹", "å…³ç¨", "åå€¾é”€", "åè¡¥è´´", "ä¸å¯é å®ä½“æ¸…å•", "ç®¡æ§åå•",
    ],
    "agency_order": ["order", "directive", "notice of proposed rulemaking", "nopr", "request for comments", "hearing", "comment deadline", "notice to lessees", "ntls", "ëª…ë ¹", "ì˜ê²¬ìˆ˜ë ´", "ì²­ë¬¸"],
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
        "duty-free importation", "temporary duty-free", "ë¹„ë£Œ", "ì¸ì‚°", "ë†ì—…", "ë°”ì´ì˜¤ì—°ë£Œ", "ì‹ëŸ‰",
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
        "í–‰ì •ëª…ë ¹", "ëŒ€í†µë ¹ ê°ì„œ", "ëŒ€í†µë ¹ ê²°ì •", "íŠ¸ëŸ¼í”„ ëŒ€í†µë ¹", "ë°±ì•…ê´€ ë°œì–¸",
    ],
    "company_filing": [
        "8-k", "6-k", "10-q", "10-k", "20-f", "material definitive agreement", "supply agreement",
        "customer agreement", "contract", "joint venture", "guidance", "merger", "acquisition", "offering",
        "convertible", "ê³µê¸‰ê³„ì•½", "ìˆ˜ì£¼", "í•©ì‘", "ê°€ì´ë˜ìŠ¤", "ë‹¨ì¼íŒë§¤", "ìœ ìƒì¦ì", "ì „í™˜ì‚¬ì±„",
        "ì‹ ì£¼ì¸ìˆ˜ê¶Œ", "ìê¸°ì£¼ì‹", "íƒ€ë²•ì¸ì£¼ì‹", "í•©ë³‘", "ìµœëŒ€ì£¼ì£¼", "íˆ¬ìíŒë‹¨",
    ],
    "fda_decision": ["fda approves", "fda approval", "complete response letter", "crl", "rejection"],
}

SECTOR_KEYWORDS = {
    "í’ë ¥/í•´ìƒí’ë ¥": ["wind", "offshore wind", "boem", "bsee", "renewable", "ocs", "lease", "cop"],
    "ì „ë ¥ë§/ë°ì´í„°ì„¼í„°": ["ferc", "doe", "department of energy", "grid", "electric grid", "transmission", "large load", "data center", "power", "inverter", "energy inverter", "grid deployment", "transmission facilitation"],
    "ì›ì „/ì „ë ¥ê¸°ê¸°": [
        "doe", "department of energy", "department of state", "state department",
        "nuclear", "reactor", "uranium", "nuclear fuel", "transformer", "ap1000",
        "smr", "small modular reactor", "small modular reactors", "bwrx-300",
        "first program", "ge vernova", "hitachi", "samsung c&t",
    ],
    "ë°˜ë„ì²´/AI": ["semiconductor", "chips", "bis", "export controls", "nvidia", "hbm", "ai"],
    "2ì°¨ì „ì§€/í•µì‹¬ê´‘ë¬¼": ["battery", "lithium", "critical minerals", "ira", "ev"],
    "ë°©ì‚°/ì§€ì •í•™": [
        "sanctions", "missile", "defense", "iran", "israel", "middle east", "hormuz",
        "strait of hormuz", "red sea", "houthi", "strike", "ceasefire", "war powers",
        "russia", "ukraine", "nato", "china", "taiwan", "north korea", "usfk",
    ],
    "ì •ìœ /í™”í•™/í•´ìš´": [
        "oil", "brent", "wti", "crude", "lng", "natural gas", "hormuz", "strait of hormuz",
        "red sea", "houthi", "tanker", "shipping", "freight", "maritime",
    ],
    "ë°”ì´ì˜¤/FDA": ["fda", "clinical", "drug", "crl"],
    "ê´€ì„¸/ìˆ˜ì¶œì£¼": ["tariff", "section 301", "section 232", "ustr", "customs", "duty", "quota", "safeguard", "anti-dumping"],
    "ì¤‘êµ­ ìˆ˜ì¶œí†µì œ/í•µì‹¬ì†Œì¬": [
        "mofcom", "china ministry of commerce", "chinese ministry of commerce", "å•†åŠ¡éƒ¨",
        "å‡ºå£ç®¡åˆ¶", "æš‚åœå‡ºå£", "åœæ­¢å‡ºå£", "ç¦æ­¢å‡ºå£", "å‡ºå£ç¦ä»¤", "ä¸¤ç”¨ç‰©é¡¹",
        "helium", "æ°¦", "rare earth", "ç¨€åœŸ", "gallium", "é•“", "germanium", "é”—",
        "graphite", "çŸ³å¢¨", "antimony", "é”‘", "tungsten", "é’¨", "indium", "é“Ÿ",
    ],
    "ë°˜ë„ì²´/ë””ìŠ¤í”Œë ˆì´/ì‚°ì—…ê°€ìŠ¤": [
        "helium", "æ°¦", "gallium", "é•“", "germanium", "é”—", "indium", "é“Ÿ",
        "semiconductor material", "semiconductor materials", "industrial gas", "industrial gases",
    ],
    "ë¹„ë£Œ/ë†í™”í•™/ìŒì‹ë£Œ ì›ê°€": ["fertilizer", "phosphate", "agriculture", "farm", "regenerative agriculture", "biofuel", "feedstock", "food supply", "ë¹„ë£Œ", "ì¸ì‚°", "ë†ì—…", "ë°”ì´ì˜¤ì—°ë£Œ", "ì‹ëŸ‰"],
    "í†µì‹ /FCC/ìœ„ì„±": [
        "fcc", "federal communications commission", "spectrum", "broadband", "wireless", "wireline",
        "satellite", "space bureau", "net neutrality", "universal service", "equipment authorization",
        "telecommunications", "auction", "covered list", "national security", "foreign adversary",
        "secure equipment", "communications supply chain", "connected device", "connected devices",
        "internet of things", "iot", "cyber trust mark", "inverter",
    ],
    "í–‰ì •ëª…ë ¹/ëŒ€í†µë ¹ë¬¸ì„œ": [
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
class×MµîÚ$z{-®éÜj×W&Ò’f÷"FW&Ò–âE%TÕôôdd”4”Åõ$TÔ$µõ5E$ôäuõDU$Õ2“ Ğ¢&WGW&âæöæPĞ¢ÖF6†VBÒ¶'V6¶WC¢¶·rf÷"·r–â¶W—v÷&G2–b¶W—v÷&Eö–å÷FW‡B††—7F6²Â·r•Òf÷"'V6¶WBÂ¶W—v÷&G2–â5DtUô´U•tõ$E2æ—FV×2‚—ĞĞ¢–b&fFöFV6—6–öâ"–âÖF6†VBæBÖF6†VE²&fFöFV6—6–öâ%ÒæB$dD"æ÷B–â—FVÒævWB‚'6÷W&6R"Â""’æB&fF"æ÷B–â†—7F6³ Ğ¢ÖF6†VE²&fFöFV6—6–öâ%ÒÒµĞĞ¢—5öf65÷6÷W&6RÒ6÷W&6UöæÖRç7F'G7v—F‚‚$d42"’÷"6÷W&6UöæÖRÓÒ$fVFW&Â&Vv—7FW"d42 Ğ¢2&æF–öæÂ6V7W&—G’"V'2–âv†—FR†÷W6RÖVÖ÷&æFg&WVVçFÇ’â—B—0Ğ¢2æ÷Bâd426–væÂVæÆW72F†R&–Ö'’6÷W&6R—G6VÆb—2F†Rd42àĞ¢–bæ÷B—5öf65÷6÷W&6S Ğ¢ÖF6†VE²&f65öFV6—6–öåöæ÷F–6R%ÒÒµĞĞ¢ÖF6†VBÒ¶'V6¶WC¢·w2f÷"'V6¶WBÂ·w2–âÖF6†VBæ—FV×2‚’–b·w7ĞĞ¢–b—5öf65÷6÷W&6RæBç’†¶W—v÷&Eö–å÷FW‡B††—7F6²ÂFW&Ò’f÷"FW&Ò–âd45õ5E$ôäuõDU$Õ2“ Ğ¢ÖF6†VBç6WFFVfVÇB‚&f65öFV6—6–öåöæ÷F–6R"Â²&f62öff–6–ÂFV6—6–öâöæ÷F–6R6÷W&6R%ÒĞ¢–bæ÷BÖF6†VC Ğ¢&WGW&âæöæPĞ¢7FvU÷66÷&RÒ7VÒ†ÆVâ‡b’f÷"b–âÖF6†VBçfÇVW2‚’Ğ¢†5öÖ¦÷%öf–Æ–ærÒç’†¶W—v÷&Eö–å÷FW‡B††—7F6²Â¶W—v÷&B’f÷"¶W—v÷&B–âÔ¤õ%ôd”Ä”äuô´U•tõ$E2Ğ¢—5öf65öFÖ–å÷&W÷'F–ærÒ—5öf65÷6÷W&6RæBç’†¶W—v÷&Eö–å÷FW‡B††—7F6²ÂFW&Ò’f÷"FW&Ò–âd45ôDÔ”åõ$Uõ%D”äuõDU$Õ2Ğ¢–b—5öf65öFÖ–å÷&W÷'F–æs Ğ¢–×÷'Fæ6RÒ.ÊI Ğ¢VÆ–bç’†'V6¶WB–âÖF6†VBf÷"'V6¶WB–â‚&6÷W'Eö÷&FW""Â&f–æÅ÷'VÆR"Â'6æ7F–öç5÷F&–fg5öW‡÷'B"Â&6†–æ÷G&FUö6öçG&öÇ2"Â&VæW&w•÷6V7W&—G•÷öÆ–7’"Â'7FFU÷6×%öÖö5÷öÆ–7’"Â'&W6–FVçF–Åö7F–öâ"Â&fFöFV6—6–öâ"’’÷"‚&f65öFV6—6–öåöæ÷F–6R"–âÖF6†VBæB—5öf65÷6÷W&6R“ Ğ¢–×÷'Fæ6RÒ.È8 Ğ¢VÆ–b&w&–7VÇGW&U÷7WÇ•÷öÆ–7’"–âÖF6†VC Ğ¢–×÷'Fæ6RÒ.ÊI Ğ¢VÆ–b&6ö×ç•öf–Æ–ær"–âÖF6†VBæB†5öÖ¦÷%öf–Æ–æs Ğ¢–×÷'Fæ6RÒ.ÊI Ğ¢VÆ–b7FvU÷66÷&RãÒ3 Ğ¢–×÷'Fæ6RÒ.ÊI Ğ¢VÇ6S Ğ¢–×÷'Fæ6RÒ.ÙY‚ Ğ¢6V7F÷'2Ò·6V7F÷"f÷"6V7F÷"Â¶W—v÷&G2–â4T5Dõ%ô´U•tõ$E2æ—FV×2‚’–bç’†¶W—v÷&Eö–å÷FW‡B††—7F6²Â·r’f÷"·r–â¶W—v÷&G2•Ò÷"².Ê	^ËRş«yÎÊ	ÂÉÛÎ»	‚%ĞĞ¢–b—5öf65öFÖ–å÷&W÷'F–æs Ğ¢6V7F÷'2Ò².ºû«ZÒØk^ÈººyÒ»;^«ZÂşÉê^ÉZ»;N«:%ĞĞ¢–×7G3¢Æ—7E·7G%ÒÒµĞĞ¢F‡3¢Æ—7E·7G%ÒÒµĞĞ¢–b—5öf65öFÖ–å÷&W÷'F–æs Ğ¢–×7G2æW‡FVæB…².È¹Î«NÙÂ"Â.ÉÙÈ*Î«+Ê	RÉˆÙjRÊ	ÎÙYÎÊ%ÒĞ¢F‡2æW‡FVæB…².Ê	^ËRØ8ÉèN¹ÛÎÉÛ‚"Â.«yÎÊ	ÂÊHÈ‰‚%ÒĞ¢VÆ–bç’†'V6¶WB–âÖF6†VBf÷"'V6¶WB–â‚&6÷W'Eö÷&FW""Â&f–æÅ÷'VÆR"Â'W&Ö—E÷&W7F'B"Â&vVæ7•ö÷&FW""Â&VæW&w•÷6V7W&—G•÷öÆ–7’"Â'7FFU÷6×%öÖö5÷öÆ–7’"Â'&W6–FVçF–Åö7F–öâ"Â&f65öFV6—6–öåöæ÷F–6R"’“ Ğ¢–×7G2æW‡FVæB…².È¹Î«NÙÂ"Â.ÙZÉÛÉÊ‚%ÒĞ¢F‡2æW‡FVæB…².Ê	^ËRØ8ÉèN¹ÛÎÉÛ‚"Â.ÙZÉÛÉÊ‚%ÒĞ¢–bç’†'V6¶WB–âÖF6†VBf÷"'V6¶WB–â‚'6æ7F–öç5÷F&–fg5öW‡÷'B"Â&6†–æ÷G&FUö6öçG&öÇ2"Â&VæW&w•÷6V7W&—G•÷öÆ–7’"Â'7FFU÷6×%öÖö5÷öÆ–7’"Â&w&–7VÇGW&U÷7WÇ•÷öÆ–7’"Â&6ö×ç•öf–Æ–ær"Â&fFöFV6—6–öâ"’“ Ğ¢–×7G2æW‡FVæB…².¸ø‚»(N¸©B¸ª^º
R"Â.È‰«ˆ’%ÒĞ¢F‡2æW‡FVæB…².ÉÛNÉÛR"Â.È‰«ˆ’%ÒĞ¢–b&6†–æ÷G&FUö6öçG&öÇ2"–âÖF6†VC Ğ¢–×7G2æW‡FVæB…².È¹Î«NÙÂ%ÒĞ¢F‡2æW‡FVæB…².«;^«ˆºyÒ"Â.Ê	^ËRØ8ÉèN¹ÛÎÉÛ‚"Â.É¹ÉéÉêÂ»˜NÉª’%ÒĞ¢–b'7FFU÷6×%öÖö5÷öÆ–7’"–âÖF6†VC Ğ¢F‡2æW‡FVæB…².«8NÉ[Ò«È¹ÎÈK"Â.»ºYË+NÉÛ‚"Â.ÙHNºÎÊ	ŞØ«‚ØÈÎÉÛN¸+È»%ÒĞ¢–b&6ö×ç•öf–Æ–ær"–âÖF6†VC Ğ¢F‡2æVæB‚.«8NÉ[Ò«È¹ÎÈK"Ğ¢–b—5÷v†—FV†÷W6U÷6÷W&6S ¢7F÷'•ö¶W’Ò—FVÒævWB‚'v†—FV†÷W6U÷7F÷'•ö¶W’"’÷"v†—FV†÷W6U÷7F÷'•ö¶W’†—FVÒ¢f–ævW'&–çEö–çWBÒb'v†—FV†÷W6RÖFWF–Â×c'Ç·7F÷'•ö¶W—Ò ¢VÇ6S ¢f–ævW'&–çEö–çWBÒb'¶—FVÒævWB‚w6÷W&6Rr—×Ç¶—FVÒævWB‚wF—FÆRr—×Ç¶—FVÒævWB‚vÆ–æ²r—Ò ¢f–ævW'&–çBÒ†6†Æ–"ç6†#Sb†f–ævW'&–çEö–çWBæVæ6öFR‚'WFbÓ‚"’’æ†W†F–vW7B‚•³£eĞ¢&WGW&â²¢¦—FVÒÂ&f–ævW'&–çB#¢f–ævW'&–çBÂ&ÖF6†VB#¢ÖF6†VBÂ&–×÷'Fæ6R#¢–×÷'Fæ6RÂ'7FGW2#¢.Éˆ»˜B"–b—FVÕ²'6÷W&6R%Òç7F'G7v—F‚‚‚$6÷W'DÆ—7FVæW""Â$µ%‚´”äB"’’VÇ6R.Ù™^Ê	R"Â&–×7G2#¢Æ—7B†F–7Bæg&öÖ¶W—2†–×7G2’’÷"².ÉÙÈ*Î«+Ê	RÉˆÙjRÊ	ÎÙYÎÊ%ÒÂ'F‡2#¢Æ—7B†F–7Bæg&öÖ¶W—2‡F‡2’’÷"².Ê	^ËRØ8ÉèN¹ÛÎÉÛ‚%ÒÂ'6V7F÷'2#¢6V7F÷'7Ğ Ğ Ğ¦FVbÆöE÷6VVâ‚’ÓâF–7C Ğ¢–bæ÷B4TTåõD‚æW†—7G2‚“ Ğ¢&WGW&â²'6VVâ#¢·ÒÂ'WFFVEöEö·7B#¢"'ĞĞ¢G'“ Ğ¢&WGW&â§6öâæÆöG2…4TTåõD‚ç&VE÷FW‡B†Væ6öF–æsÒ'WFbÓ‚"’Ğ¢W†6WB§6öâä¥4ôäFV6öFTW'&÷# Ğ¢&WGW&â²'6VVâ#¢·ÒÂ'WFFVEöEö·7B#¢"'ĞĞ Ğ Ğ¦FVb6fU÷6VVâ‡6VVã¢F–7B’ÓâæöæS Ğ¢DDôD•"æÖ¶F—"†W†—7Eöö³ÕG'VRĞ¢6VVå²'WFFVEöEö·7B%ÒÒæ÷uö·7B‚’æ—6öf÷&ÖB‡F–ÖW7V3Ò'6V6öæG2"Ğ¢4TTåõD‚çw&—FU÷FW‡B†§6öâæGV×2‡6VVâÂVç7W&Uö66–“ÔfÇ6RÂ–æFVçCÓ"Â6÷'Eö¶W—3ÕG'VR’²%Æâ"ÂVæ6öF–æsÒ'WFbÓ‚"Ğ Ğ Ğ¦FVb6öÆÆV7Eö6æF–FFW2†æ÷s¢GBæFFWF–ÖR’ÓâGWÆU¶Æ—7E¶F–7EÒÂÆ—7E·7G%ÕÓ ¢6æF–FFW3¢Æ—7E¶F–7EÒÒµĞ¢6÷W&6Uöæ÷FW3¢Æ—7E·7G%ÒÒµĞ¢v†—FV†÷W6UöFWF–Åö'VFvWBÒ²'F÷FÂ#¢Â&'•÷6÷W&6R#¢·×Ğ¢v†—FV†÷W6U÷F÷FÇ2Ò²&Æ—7FVB#¢Â&GFV×FVB#¢Â'fW&–f–VB#¢Â&f–ÆVB#¢Â&FVfW'&VB#¢Â&6Æ76–f–VB#¢Ğ¢f÷"6÷W&6R–â4õU$4U3 ¢FW‡BÂW'&÷"ÒfWF6…÷FW‡B‡6÷W&6RçW&Â¢–bW'&÷# Ğ¢6÷W&6Uöæ÷FW2æVæB†b"Ò·6÷W&6RææÖWÓ¢Ù™^ÉÛ‚»h«‡¶W'&÷'Ò’"Ğ¢6öçF–çVPĞ¢–b6÷W&6Ræ¶–æBÓÒ&6÷W'FÆ—7FVæW"# Ğ¢—FV×2Ò'6Uö6÷W'FÆ—7FVæW"‡FW‡B÷"""Â6÷W&6RĞ¢VÆ–b6÷W&6Ræ¶–æBÓÒ&¶–æEö‡FÖÂ# Ğ¢—FV×2Ò'6Uö¶–æEö‡FÖÂ‡FW‡B÷"""Â6÷W&6RÂæ÷rĞ¢VÆ–b6÷W&6Ræ¶–æBÓÒ&fVFW&Å÷&Vv—7FW%ö§6öâ# Ğ¢—FV×2Ò'6UöfVFW&Å÷&Vv—7FW%ö§6öâ‡FW‡B÷"""Â6÷W&6RĞ¢VÆ–b6÷W&6Ræ¶–æBÓÒ'v†—FV†÷W6Uö‡FÖÂ# Ğ¢—FV×2Ò'6U÷v†—FV†÷W6Uö‡FÖÂ‡FW‡B÷"""Â6÷W&6RĞ¢VÆ–b6÷W&6Ræ¶–æBÓÒ&f65ö‡FÖÂ# Ğ¢—FV×2Ò'6Uöf65ö‡FÖÂ‡FW‡B÷"""Â6÷W&6RĞ¢VÆ–b6÷W&6Ræ¶–æBÓÒ'7FFUö‡FÖÂ# Ğ¢—FV×2Ò'6U÷7FFUö‡FÖÂ‡FW‡B÷"""Â6÷W&6RĞ¢VÆ–b6÷W&6Ræ¶–æBÓÒ&Ööf6öÕö‡FÖÂ# Ğ¢—FV×2Ò'6UöÖöf6öÕö‡FÖÂ‡FW‡B÷"""Â6÷W&6RĞ¢VÆ–b6÷W&6Ræ¶–æBÓÒ&Æ–æµö‡FÖÂ# Ğ¢—FV×2Ò'6UöÆ–æµö‡FÖÂ‡FW‡B÷"""Â6÷W&6RĞ¢VÇ6S ¢—FV×2Ò'6U÷'72‡FW‡B÷"""Â6÷W&6R¢–b6÷W&6Ræ¶–æBÓÒ'v†—FV†÷W6Uö‡FÖÂ# ¢—FV×2ÂFWF–Å÷7FG2ÒVç&–6…÷v†—FV†÷W6Uö—FV×2†—FV×2Âæ÷rÂv†—FV†÷W6UöFWF–Åö'VFvWB¢f÷"¶W’ÂfÇVR–âFWF–Å÷7FG2æ—FV×2‚“ ¢v†—FV†÷W6U÷F÷FÇ5¶¶W•Ò³ÒfÇVP¢&–çB€¢b'v†—FV†÷W6U÷6÷W&6S×·6÷W&6RææÖR'ÒÆ—7FVC×¶FWF–Å÷7FG5²vÆ—7FVBu×Ò ¢b&FWF–ÅöGFV×FVC×¶FWF–Å÷7FG5²vGFV×FVBu×ÒFWF–Å÷fW&–f–VC×¶FWF–Å÷7FG5²wfW&–f–VBu×Ò ¢b&FWF–Åöf–ÆVC×¶FWF–Å÷7FG5²vf–ÆVBu×ÒFWF–ÅöFVfW'&VC×¶FWF–Å÷7FG5²vFVfW'&VBu×Ò ¢¢6÷W&6Uöæ÷FW2æVæB†b"Ò·6÷W&6RææÖWÓ¢¶ÆVâ†—FV×2—Ş«BÙ™^ÉÛ‚"¢f÷"—FVÒ–â—FV×3 ¢vRÒ—FVÕövUö†÷W'2†—FVÒÂæ÷r¢–b6÷W&6Ræ¶–æB–â²''72"Â&6÷W'FÆ—7FVæW""Â&¶–æEö‡FÖÂ"Â&fVFW&Å÷&Vv—7FW%ö§6öâ"Â'v†—FV†÷W6Uö‡FÖÂ"Â&f65ö‡FÖÂ"Â'7FFUö‡FÖÂ"Â&Ööf6öÕö‡FÖÂ'ÒæBvR—2æöæS ¢6öçF–çVP¢Ö…övRÒt„•DT„õU4UôÔ…ôtUô„õU%2–b6÷W&6Ræ¶–æBÓÒ'v†—FV†÷W6Uö‡FÖÂ"VÇ6RÔ…õ4õU$4UôtUô„õU%0¢–bvR—2æ÷BæöæRæBvRâÖ…övS ¢6öçF–çVP¢6Æ76–f–VBÒ6Æ76–g•ö—FVÒ†—FVÒ¢–b6Æ76–f–VC ¢Vç7W&UöW‡Æ–æVB†6Æ76–f–VB¢6Æ76–f–VE²&vUö†÷W'2%ÒÒvP¢6æF–FFW2æVæB†6Æ76–f–VB¢–b6÷W&6Ræ¶–æBÓÒ'v†—FV†÷W6Uö‡FÖÂ# ¢v†—FV†÷W6U÷F÷FÇ5²&6Æ76–f–VB%Ò³Ò¢f÷"W‡G&ö—FV×2ÂW‡G&öæ÷FW2–â†6öÆÆV7E÷6V5öf–Æ–æw2†æ÷r’Â“ Ğ¢6÷W&6Uöæ÷FW2æW‡FVæB†W‡G&öæ÷FW2Ğ¢f÷"—FVÒ–âW‡G&ö—FV×3 Ğ¢6Æ76–f–VBÒ6Æ76–g•ö—FVÒ†—FVÒĞ¢–b6Æ76–f–VC Ğ¢Vç7W&UöW‡Æ–æVB†6Æ76–f–VBĞ¢6Æ76–f–VE²&vUö†÷W'2%ÒÒ—FVÕövUö†÷W'2†—FVÒÂæ÷rĞ¢6æF–FFW2æVæB†6Æ76–f–VBĞ¢6÷W&6Uöæ÷FW2æVæB€¢"Òv†—FR†÷W6RFWF–ÂfW&–f–6F–öã¢ ¢b&Æ—7FVC×·v†—FV†÷W6U÷F÷FÇ5²vÆ—7FVBu×ÒGFV×FVC×·v†—FV†÷W6U÷F÷FÇ5²vGFV×FVBu×Ò ¢b'fW&–f–VC×·v†—FV†÷W6U÷F÷FÇ5²wfW&–f–VBu×Òf–ÆVC×·v†—FV†÷W6U÷F÷FÇ5²vf–ÆVBu×Ò ¢b&FVfW'&VC×·v†—FV†÷W6U÷F÷FÇ5²vFVfW'&VBu×Ò6Æ76–f–VC×·v†—FV†÷W6U÷F÷FÇ5²v6Æ76–f–VBu×Ò ¢¢&–çB€¢'v†—FV†÷W6U÷F÷FÇ2 ¢b&Æ—7FVC×·v†—FV†÷W6U÷F÷FÇ5²vÆ—7FVBu×ÒGFV×FVC×·v†—FV†÷W6U÷F÷FÇ5²vGFV×FVBu×Ò ¢b'fW&–f–VC×·v†—FV†÷W6U÷F÷FÇ5²wfW&–f–VBu×Òf–ÆVC×·v†—FV†÷W6U÷F÷FÇ5²vf–ÆVBu×Ò ¢b&FVfW'&VC×·v†—FV†÷W6U÷F÷FÇ5²vFVfW'&VBu×Ò6Æ76–f–VC×·v†—FV†÷W6U÷F÷FÇ5²v6Æ76–f–VBu×Ò ¢¢&WGW&â6æF–FFW2Â6÷W&6Uöæ÷FW0 Ğ Ğ¦FVb&VæFW%÷&W÷'B†ÆW'G3¢Æ—7E¶F–7EÒÂ6÷W&6Uöæ÷FW3¢Æ—7E·7G%ÒÂæ÷s¢GBæFFWF–ÖR’Óâ7G# Ğ¢Æ–æW2Ò¶b/	ùª‚´…2Ê	^Ë\+~«yÎÊ	Â«:Ëj«*’É¸ÎË™‚+r¶æ÷s¢U¸XBVŞÉ¹BVNÉÛÂTƒ¢TÒµ5GÒ"Â"%ĞĞ¢–bæ÷BÆW'G3 Ğ¢Æ–æW2æW‡FVæB…².«:Ëj«*’Ê	^Ë\+~«yÎÊ	Â»8«+ÒÊxÊ	Ù™^ÉÛ‚ÉxnÉØÂ"Â""Â.Ù™^ÉÛ‚»)NÉÈC¢"Â§6÷W&6Uöæ÷FW5³£CÒÂ""Â/	ù*É¸ÎË™‚ØÉ¸ºƒ¢ÉÛN»(‚ÈºNÙhÉyÈIÂºzNËiÌ+~ºxÊxL+~ÙˆN«ˆÙÙºhBÂ»ºYÉyÉÛNÈY‚şÙZÉÛÉÊ‚ÂÈ‰«ˆ’ÂÈ¹Î«NÙÎº[ÂÈ8ºÂ»	N«ëÂÙ™^Ê	RÉÛN»*NØ«¸©BÊxÊ	Ù™^ÉÛ¹	ÊxÉX®ÉYÈ«^¸¸¸ºBâ"Â""Â.ØŠÎÉéÊÉkÉÛBÉXN¸¸ÂË«:Éª’Ê	^Ë\+~«yÎÊ	ÂÉXÎºkÎÉè^¸¸¸ºBâ%ÒĞ¢&WGW&â%Æâ"æ¦ö–â†Æ–æW2’²%Æâ Ğ¢f÷"–G‚ÂÆW'B–âVçVÖW&FR†ÆW'G2Â“ Ğ¢Vç7W&UöW‡Æ–æVB†ÆW'BĞ¢ÖF6†VE÷FW&×2Ò6÷'FVB‡·FW&Òf÷"FW&×2–âÆW'E²&ÖF6†VB%ÒçfÇVW2‚’f÷"FW&Ò–âFW&×7ÒĞ¢F—7Æ•÷F—FÆRÒÆW'BævWB‚'F—FÆUö¶ò"’÷"ÆW'E²'F—FÆR%ĞĞ¢Æ–æW2æW‡FVæB€Ğ¢°Ğ¢b"22¶–G‡Òâ·¶ÆW'E²v–×÷'Fæ6Ru×Ü+w¶ÆW'E²w7FGW2u×ÕÒ¶F—7Æ•÷F—FÆWÒ"ÀĞ¢b"ÒÉ¹Ê	Ã¢¶ÆW'E²wF—FÆRu×Ò"ÀĞ¢b"ÒÈ8Ø9Â»8Ù™C¢²rÂræ¦ö–â†ÆW'E²vÖF6†VBuÒæ¶W—2‚’—ÒÈºÙ‹‚Ù™^ÉÛ‚‡²rÂræ¦ö–â†ÖF6†VE÷FW&×5³£…Ò—Ò’"ÀĞ¢b"ÒÉ¹ºË‚şËiÎË)ƒ¢·¶ÆW'E²w6÷W&6Ru×ÕÒ‡¶ÆW'E²vÆ–æ²u×Ò’+rÉ¹Ë)ÎÈ¹Î«¶ÆW'BævWB‚wV&Æ—6†VEö·7Br’÷"~Ù™^ÉÛ‚»h«wÒ+rÊÙ¨Â¶æ÷s¢Tƒ¢TÒµ5GÒ"ÀĞ¢¦W‡ÆæF–öåöÆ–æW2†ÆW'B’ÀĞ¢"ÒÊhÈ¹ÂË+NØÃ¢É¹ºË‚ÊNºË‚ÂÈ¹ÎÙhÉÛÂşºx«	ÉÛÂÂÙYÎ«ZÒ»ºYË+NÉÛ‚¸[ËiÂÂ«Hº
‚Ù[NÉ›‚Ø»ËºL+tUDb»	ÉÙ"ÀĞ¢""ÀĞ¢ĞĞ¢Ğ¢Æ–æW2æW‡FVæB…²/	ù*É¸ÎË™‚ØÉ¸ºƒ¢ÉÛN»(‚ÈºNÙhÉØºzNËiÌ+~ºxÊxL+~ÙˆN«ˆÙÙºhBÂ»ºYÉyÉÛNÈY‚şÙZÉÛÉÊ‚ÂÈ‰«ˆ’ÂÈ¹Î«NÙÂÊIÈºNÊ	ÎºÂ»	N¸	Ëi^«;ÂÙYÎ«ZÒ»ºYË+NÉÛ‚É{«+ÉØB«‹ÊHÉËÎºÂÊ	^ËRş«yÎÊ	ÂÙ¸N»;Nº[ÂÈJ»8NÙhÈ«^¸¸¸ºBâ"Â""Â.ØŠÎÉéÊÉkÉÛBÉXN¸¸ÂË«:Éª’Ê	^Ë\+~«yÎÊ	ÂÉXÎºkÎÉè^¸¸¸ºBâ%ÒĞ¢&WGW&â%Æâ"æ¦ö–â†Æ–æW2’²%Æâ Ğ Ğ Ğ¦FVbw&—FUö÷WGWG2†ÆW'G3¢Æ—7E¶F–7EÒÂ6÷W&6Uöæ÷FW3¢Æ—7E·7G%ÒÂæ÷s¢GBæFFWF–ÖR’ÓâæöæS ¢õUEôD•"æÖ¶F—"†W†—7Eöö³ÕG'VR¢&W÷'BÒ&VæFW%÷&W÷'B†ÆW'G2Â6÷W&6Uöæ÷FW2Âæ÷r¢„õUEôD•"ò&¶‡5÷öÆ–7•÷vF6‚æÖB"’çw&—FU÷FW‡B‡&W÷'BÂVæ6öF–æsÒ'WFbÓ‚"¢–bÆW'G3 ¢F÷ÒÆW'G5³ĞĞ¢Vç7W&UöW‡Æ–æVB‡F÷Ğ¢„õUEôD•"ò&¶‡5÷öÆ–7•÷vF6…öÆW'E÷F—FÆRçG‡B"’çw&—FU÷FW‡B†b$´…2Ê	^ËRÉ¸ÎË™ƒ¢··F÷²v–×÷'Fæ6Ru×ÕÒ²‡F÷ævWB‚wF—FÆUö¶òr’÷"F÷²wF—FÆRuÒ•³£s×ÕÆâ"ÂVæ6öF–æsÒ'WFbÓ‚"¢„õUEôD•"ò&¶‡5÷öÆ–7•÷vF6…öÆW'BæÖB"’çw&—FU÷FW‡B‡&W÷'BÂVæ6öF–æsÒ'WFbÓ‚"¢„õUEôD•"ò&¶‡5÷öÆ–7•÷vF6…öÆW'G2æ§6öâ"’çw&—FU÷FW‡B†§6öâæGV×2†ÆW'G2ÂVç7W&Uö66–“ÔfÇ6RÂ–æFVçCÓ"’²%Æâ"ÂVæ6öF–æsÒ'WFbÓ‚"¢VÇ6S ¢f÷"F‚–â€¢õUEôD•"ò&¶‡5÷öÆ–7•÷vF6…öÆW'E÷F—FÆRçG‡B"À¢õUEôD•"ò&¶‡5÷öÆ–7•÷vF6…öÆW'BæÖB"À¢õUEôD•"ò&¶‡5÷öÆ–7•÷vF6…öÆW'G2æ§6öâ"À¢TäD”äuõ4TTåõD‚À¢“ ¢G'“ ¢F‚çVæÆ–æ²‚¢W†6WBf–ÆTæ÷Df÷VæDW'&÷# ¢70  ¦FVbw&—FU÷VæF–æu÷6VVâ†ÆW'G3¢Æ—7E¶F–7EÒÂæ÷s¢GBæFFWF–ÖR’ÓâæöæS ¢–bæ÷BÆW'G3 ¢&WGW&à¢VæF–ærÒ°¢&7&VFVEöEö·7B#¢æ÷ræ—6öf÷&ÖB‡F–ÖW7V3Ò'6V6öæG2"’À¢'6VVâ#¢°¢—FVÕ²&f–ævW'&–çB%Ó¢°¢'F—FÆR#¢—FVÕ²'F—FÆR%ÒÀ¢'6÷W&6R#¢—FVÕ²'6÷W&6R%ÒÀ¢&Æ–æ²#¢—FVÕ²&Æ–æ²%ÒÀ¢&f—'7E÷6VVåö·7B#¢æ÷ræ—6öf÷&ÖB‡F–ÖW7V3Ò'6V6öæG2"’À¢&–×÷'Fæ6R#¢—FVÕ²&–×÷'Fæ6R%ÒÀ¢Ğ¢f÷"—FVÒ–âÆW'G0¢ÒÀ¢Ğ¢TäD”äuõ4TTåõD‚çw&—FU÷FW‡B€¢§6öâæGV×2‡VæF–ærÂVç7W&Uö66–“ÔfÇ6RÂ–æFVçCÓ"Â6÷'Eö¶W—3ÕG'VR’²%Æâ"À¢Væ6öF–æsÒ'WFbÓ‚"À¢  ¦FVb6æF–FFU÷6÷W&6U÷&æ²†—FVÓ¢F–7B’Óâ–çC ¢6÷W&6RÒ7G"†—FVÒævWB‚'6÷W&6R"’÷"""’æÆ÷vW"‚¢–b—FVÒævWB‚'v†—FV†÷W6U÷7F÷'•ö¶W’"“ ¢–b6÷W&6RÓÒ'v†—FR†÷W6Rf7B6†VWG2# ¢&WGW&â ¢–b6÷W&6R–â°¢'v†—FR†÷W6RW†V7WF—fR÷&FW'2"À¢'v†—FR†÷W6R&W6–FVçF–ÂÖVÖ÷&æF"À¢'v†—FR†÷W6R&ö6ÆÖF–öç2"À¢'v†—FR†÷W6R'&–Vf–æw27FFVÖVçG2"À¢Ó ¢&WGW&â¢&WGW&â   ¦FVbFVGWUö6æF–FFUöf–ævW'&–çG2†6æF–FFW3¢Æ—7E¶F–7EÒ’ÓâÆ—7E¶F–7EÓ ¢6VÆV7FVC¢F–7E·7G"ÂF–7EÒÒ·Ğ¢÷&FW#¢Æ—7E·7G%ÒÒµĞ¢f÷"—FVÒ–â6æF–FFW3 ¢f–ævW'&–çBÒ7G"†—FVÒævWB‚&f–ævW'&–çB"’÷"""’ç7G&—‚¢¶W’Òf–ævW'&–çB÷"†6†Æ–"ç6†#Sb€¢b'¶—FVÒævWB‚w6÷W&6Rr—×Ç¶—FVÒævWB‚wF—FÆRr—×Ç¶—FVÒævWB‚vÆ–æ²r—Ò"æVæ6öFR‚'WFbÓ‚"¢’æ†W†F–vW7B‚•³£eĞ¢–b¶W’æ÷B–â6VÆV7FVC ¢6VÆV7FVE¶¶W•ÒÒ—FVĞ¢÷&FW"æVæB†¶W’¢6öçF–çVP¢7W'&VçBÒ6VÆV7FVE¶¶W•Ğ¢–b6æF–FFU÷6÷W&6U÷&æ²†—FVÒ’Â6æF–FFU÷6÷W&6U÷&æ²†7W'&VçB“ ¢6VÆV7FVE¶¶W•ÒÒ—FVĞ¢&WGW&â·6VÆV7FVE¶¶W•Òf÷"¶W’–â÷&FW%Ğ  ¦FVbÖ–â‚’Óâ–çC ¢æ÷rÒæ÷uö·7B‚¢6VVâÒÆöE÷6VVâ‚¢6VVåöÖÒ6VVâç6WFFVfVÇB‚'6VVâ"Â·Ò¢6æF–FFW2Â6÷W&6Uöæ÷FW2Ò6öÆÆV7Eö6æF–FFW2†æ÷r¢6æF–FFW2ÒFVGWUö6æF–FFUöf–ævW'&–çG2†6æF–FFW2¢æWuöÆW'G2ÒµĞ¢6VÆV7FVEöf–ævW'&–çG3¢6WE·7G%ÒÒ6WB‚¢f÷"—FVÒ–â6÷'FVB†6æF–FFW2Â¶W“ÖÆÖ&Fƒ¢‡…²&–×÷'Fæ6R%ÒÒ.È8"Â‚ævWB‚&vUö†÷W'2"’÷"““’’“ ¢–b€¢—FVÕ²&–×÷'Fæ6R%ÒÓÒ.ÙY‚ ¢÷"—FVÕ²&f–ævW'&–çB%Ò–â6VVåöÖ ¢÷"—FVÕ²&f–ævW'&–çB%Ò–â6VÆV7FVEöf–ævW'&–çG0¢“ ¢6öçF–çVP¢æWuöÆW'G2æVæB†—FVÒ¢6VÆV7FVEöf–ævW'&–çG2æFB†—FVÕ²&f–ævW'&–çB%Ò¢–bÆVâ†æWuöÆW'G2’ãÒÔ…ôÄU%E3 ¢'&V°¢w&—FUö÷WGWG2†æWuöÆW'G2Â6÷W&6Uöæ÷FW2Âæ÷r¢w&—FU÷VæF–æu÷6VVâ†æWuöÆW'G2Âæ÷r¢v†—FV†÷W6Uö6æF–FFW2Ò7VÒ€¢7G"†—FVÒævWB‚'6÷W&6R"’÷"""’æÆ÷vW"‚’ç7F'G7v—F‚‚'v†—FR†÷W6R"¢f÷"—FVÒ–â6æF–FFW0¢¢v†—FV†÷W6UöæWrÒ7VÒ€¢7G"†—FVÒævWB‚'6÷W&6R"’÷"""’æÆ÷vW"‚’ç7F'G7v—F‚‚'v†—FR†÷W6R"¢f÷"—FVÒ–âæWuöÆW'G0¢¢v†—FV†÷W6U÷6VVåöf–ÇFW&VBÒ7VÒ€¢7G"†—FVÒævWB‚'6÷W&6R"’÷"""’æÆ÷vW"‚’ç7F'G7v—F‚‚'v†—FR†÷W6R"¢æB—FVÒævWB‚&f–ævW'&–çB"’–â6VVåöÖ ¢f÷"—FVÒ–â6æF–FFW0¢¢&–çB€¢b&6æF–FFW3×¶ÆVâ†6æF–FFW2—ÒæWuöÆW'G3×¶ÆVâ†æWuöÆW'G2—Ò ¢b'v†—FV†÷W6Uö6æF–FFW3×·v†—FV†÷W6Uö6æF–FFW7Òv†—FV†÷W6UöæWs×·v†—FV†÷W6UöæWwÒ ¢b'v†—FV†÷W6U÷6VVåöf–ÇFW&VC×·v†—FV†÷W6U÷6VVåöf–ÇFW&VGÒ6VVå÷7FFS×VæF–æuöFVÆ—fW'’ ¢¢&WGW&â  Ğ Ğ¦–bõöæÖUõòÓÒ%õöÖ–åõò# Ğ¢&—6R7—7FVÔW†—B†Ö–â‚’Ğ