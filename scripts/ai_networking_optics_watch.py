#!/usr/bin/env python3
"""AI networking / optics structural-change web watcher.

Sources are Google News RSS queries spanning official company releases and major media.
The watcher is deliberately event-driven: first run establishes a baseline and later
runs emit Telegram-ready HTML only for new, high-signal items.
"""

from __future__ import annotations

import datetime as dt
import email.utils
import hashlib
import html
import json
import pathlib
import re
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from zoneinfo import ZoneInfo

ROOT = pathlib.Path(__file__).resolve().parents[1]
STATE_PATH = ROOT / "data" / "ai_networking_optics_watch_state.json"
PENDING_PATH = ROOT / "out" / "ai_networking_optics_watch_pending_state.json"
ALERT_PATH = ROOT / "out" / "ai_networking_optics_watch_telegram.html"
STATUS_PATH = ROOT / "out" / "ai_networking_optics_watch_status.md"

KST = ZoneInfo("Asia/Seoul")
NOW = dt.datetime.now(dt.timezone.utc)

COMPANIES = {
    "NVIDIA": {
        "ticker": "NVDA",
        "aliases": ["NVIDIA", "Nvidia"],
        "query": 'NVIDIA (Spectrum-X OR NVLink OR BlueField OR networking OR Ethernet OR CPO OR "co-packaged optics" OR "silicon photonics" OR 1.6T OR 3.2T)',
    },
    "Broadcom": {
        "ticker": "AVGO",
        "aliases": ["Broadcom"],
        "query": 'Broadcom (AI Ethernet OR Tomahawk OR Thor OR networking OR optical OR CPO OR "co-packaged optics" OR 1.6T OR 3.2T)',
    },
    "Arista Networks": {
        "ticker": "ANET",
        "aliases": ["Arista Networks", "Arista"],
        "query": '"Arista Networks" (AI networking OR Ethernet OR 800G OR 1.6T OR 3.2T OR optics OR optical OR cluster OR hyperscaler)',
    },
    "Marvell": {
        "ticker": "MRVL",
        "aliases": ["Marvell"],
        "query": 'Marvell (optical DSP OR SerDes OR interconnect OR networking OR 800G OR 1.6T OR 3.2T OR CPO OR "co-packaged optics" OR "Celestial AI" OR "photonic fabric")',
    },
    "Lumentum": {
        "ticker": "LITE",
        "aliases": ["Lumentum"],
        "query": 'Lumentum (AI datacenter OR data center OR optical OR laser OR CPO OR 800G OR 1.6T OR 3.2T OR transceiver)',
    },
    "Coherent": {
        "ticker": "COHR",
        "aliases": ["Coherent"],
        "query": 'Coherent (PhotonLink OR "integrated optics" OR "complete optical solution" OR "end-to-end" OR "vertical integration" OR CPO OR NPO OR "chip-to-chip" OR "silicon photonics" OR SiPh OR InP OR "specialty fiber" OR "polarization-maintaining fiber" OR "mode-matching fiber" OR "multicore fiber" OR "customer engagement" OR "long-term agreement" OR "content opportunity" OR 800G OR 1.6T OR 3.2T)',
    },
    "US Optical Policy": {
        "ticker": "FCC/의회",
        "aliases": ["FCC", "Federal Communications Commission", "U.S. Senate", "Congress"],
        "queries": [
            '"optical transceiver" (FCC OR "Federal Communications Commission") (China OR Chinese OR restriction OR rule OR "Covered List" OR 3.2T OR "domestic content" OR 65% OR 75%)',
            '"optical transceiver" (Senate OR Congress OR "national security systems") (China OR Chinese OR Innolight OR Eoptolink)',
            '"optical transceiver" ("Buy American" OR "domestic end product" OR HBOM OR SBOM)',
            '("Morgan Stanley" OR "Marc Lehman") (FCC OR optical OR transceiver) (3.2T OR 65% OR 75% OR Lumentum OR Coherent OR AAOI)',
        ],
    },
    "AXT": {
        "ticker": "AXTI",
        "aliases": ["AXT", "AXT Inc.", "AXT-Tongmei", "Tongmei"],
        "queries": [
            'AXT (InP OR "indium phosphide") (substrate OR shortage OR "export license" OR capacity OR "data center" OR optical)',
            'AXT ("6-inch InP" OR "6 inch InP") (Coherent OR Lumentum OR Casela OR "capacity reservation" OR prepayment OR "long-term supply")',
            'AXT InP (capacity reservation OR deposit OR prepayment OR "crystal growth" OR pilot OR yield OR "mass production")',
        ],
    },
    "InP Supply Chain": {
        "ticker": "InP 공급망",
        "aliases": ["InP", "indium phosphide", "Sumitomo Electric", "IQE", "Casela"],
        "queries": [
            '"indium phosphide" substrate ("data center" OR optical OR transceiver OR CPO OR 1.6T OR 3.2T) (shortage OR "lead time" OR capacity OR price OR export)',
            '"InP substrate" (shortage OR capacity OR "export license" OR "lead time" OR "capacity reservation" OR prepayment) (laser OR transceiver OR AI OR CPO)',
            '("6-inch InP" OR "6 inch InP") (Coherent OR Lumentum OR Casela OR capacity OR agreement OR prepayment)',
        ],
    },
    "GaAs Optical Supply Chain": {
        "ticker": "GaAs 광통신",
        "aliases": ["GaAs", "gallium arsenide", "WIN Semiconductors", "WIN Semi", "VPEC", "Visual Photonics Epitaxy"],
        "queries": [
            '("GaAs" OR "gallium arsenide" OR "WIN Semiconductors" OR "WIN Semi" OR VPEC) ("1.6T" OR "3.2T" OR CPO OR optical OR transceiver OR photodiode OR laser) (capacity OR shipment OR demand OR order OR shortage OR pricing OR qualification)',
            '("砷化鎵" OR "穩懋" OR "全新") ("光通訊" OR "1.6T" OR CPO) (出貨 OR 產能 OR 訂單 OR 需求 OR 漲價 OR 驗證)',
        ],
        "locales": [
            {"hl": "en-US", "gl": "US", "ceid": "US:en"},
            {"hl": "zh-TW", "gl": "TW", "ceid": "TW:zh-Hant"},
        ],
    },
    "Applied Optoelectronics": {
        "ticker": "AAOI",
        "aliases": ["Applied Optoelectronics", "AOI", "AAOI"],
        "query": '"Applied Optoelectronics" (800G OR 1.6T OR 3.2T OR transceiver OR optical OR hyperscaler OR customer OR capacity OR shipment OR FCC OR China)',
    },
    "Opticore": {
        "ticker": "380540.KQ",
        "aliases": ["옵티코어", "Opticore"],
        "queries": [
            '"옵티코어" ("광트랜시버" OR "400G" OR "800G" OR "1.6T") (수주 OR 공급계약 OR 발주 OR 검수 OR 납품 OR 계약기간 OR 정정 OR "AI 데이터센터")',
            '"Opticore" ("optical transceiver" OR 400G OR 800G OR 1.6T) (order OR contract OR shipment OR qualification OR "data center")',
        ],
        "locales": [
            {"hl": "ko", "gl": "KR", "ceid": "KR:ko"},
            {"hl": "en-US", "gl": "US", "ceid": "US:en"},
        ],
    },
    "OE Solutions": {
        "ticker": "138080.KQ",
        "aliases": ["오이솔루션", "OE Solutions"],
        "queries": [
            '"오이솔루션" (800G OR 1.6T OR ELSFP OR EML OR 광트랜시버) (샘플 OR 검증 OR 인증 OR 양산 OR 수주 OR 공급 OR 출하 OR 고객)',
            '"OE Solutions" (800G OR 1.6T OR ELSFP OR EML OR transceiver) (sample OR qualification OR certification OR shipment OR production OR customer OR order)',
        ],
        "locales": [
            {"hl": "ko", "gl": "KR", "ceid": "KR:ko"},
            {"hl": "en-US", "gl": "US", "ceid": "US:en"},
        ],
    },
    "Volantis": {
        "ticker": "비상장",
        "aliases": ["Volantis", "Volantis Semiconductor"],
        "queries": [
            'Volantis',
            '"Volantis" ("Series A" OR funding OR financing OR raises OR A-1 OR photonic OR VCSEL)',
            '"Volantis" (A-1 OR "photonic memory" OR "optical memory" OR "memory wall" OR "optical fabric" OR VCSEL OR inference) (customer OR sampling OR silicon OR tapeout OR benchmark OR commercialization OR delivery OR production OR partnership OR funding OR raises)',
            '"Volantis" ("10,000 tokens" OR "20 trillion" OR "240 TB/s" OR "10 TB" OR "1 pJ/bit" OR "220 memory chips")',
        ],
    },
    "Lightmatter": {
        "ticker": "비상장",
        "aliases": ["Lightmatter", "Passage"],
        "query": 'Lightmatter (Passage OR photonic OR optical OR CPO OR NPO OR "NVLink Fusion") (sampling OR customer OR deployment OR production OR shipment OR validation OR benchmark OR partnership)',
    },
    "Ayar Labs": {
        "ticker": "비상장",
        "aliases": ["Ayar Labs", "TeraPHY", "SuperNova"],
        "query": '"Ayar Labs" (TeraPHY OR SuperNova OR optical OR CPO OR "NVLink Fusion" OR "extended memory") (customer OR deployment OR production OR shipment OR validation OR qualification OR sampling OR partnership)',
    },
    "Xscape Photonics": {
        "ticker": "비상장",
        "aliases": ["Xscape Photonics", "FalconX", "ChromX", "CombX"],
        "query": '"Xscape Photonics" (FalconX OR ChromX OR CombX OR photonic OR optical OR laser) (production OR shipment OR customer OR sampling OR qualification OR partnership OR capacity OR funding)',
    },
    "Astera Labs": {
        "ticker": "ALAB",
        "aliases": ["Astera Labs", "Astera"],
        "query": '"Astera Labs" (PCIe OR CXL OR Scorpio OR fabric OR interconnect OR retimer OR AI rack OR networking)',
    },
    "Corning": {
        "ticker": "GLW",
        "aliases": ["Corning"],
        "query": 'Corning (AI data center OR datacenter OR optical communications OR fiber OR fibre OR cable OR connector OR CPO OR "co-packaged optics" OR photonics OR "glass substrate" OR advanced packaging)',
    },
    "Samsung Electronics": {
        "ticker": "005930.KS",
        "aliases": ["Samsung Electronics", "Samsung Foundry"],
        "query": '"Samsung Foundry" ("silicon photonics" OR SiPh OR PIC OR "optical module" OR "optical engine" OR CPO OR NPO OR "photonics foundry" OR "design win" OR "mass production")',
    },
    "CPO Equipment Supply Chain": {
        "ticker": "장비 공급망",
        "aliases": [
            "Chieftek", "Chieftek Precision", "直得",
            "GMT Global", "GMT GLOBAL", "高明鐵",
            "TOYO Automation", "TOYO", "東佑達",
            "ficonTEC", "Suruga Seiki", "Allring Tech", "FitTech", "萬潤",
        ],
        "queries": [
            'CPO 設備 直得 高明鐵 東佑達',
            'CPO 設備 出貨 擴產',
            'CPO 光耦合 對位 設備 訂單 能見度',
            '矽光子 設備 直得 高明鐵 東佑達',
            '高明鐵 CPO 訂單 產能',
            '東佑達 CPO 訂單 驗證',
            '直得 CPO 對位 線性馬達',
            '萬潤 CPO 光耦合 設備',
            '"Chieftek" CPO alignment equipment',
            '"GMT Global" CPO optical coupling',
            '"TOYO Automation" CPO optical coupling',
            'ficonTEC CPO optical coupling alignment',
            '"Suruga Seiki" CPO optical coupling',
        ],
        "locales": [
            {"hl": "zh-TW", "gl": "TW", "ceid": "TW:zh-Hant"},
            {"hl": "en-US", "gl": "US", "ceid": "US:en"},
        ],
    },
}

DISPLAY_NAMES_KO = {
    "NVIDIA": "엔비디아",
    "Broadcom": "브로드컴",
    "Arista Networks": "아리스타 네트웍스",
    "Marvell": "마벨",
    "Lumentum": "루멘텀",
    "Coherent": "코히런트",
    "US Optical Policy": "미국 광트랜시버 정책",
    "AXT": "AXT",
    "InP Supply Chain": "InP 기판 공급망",
    "GaAs Optical Supply Chain": "GaAs 광통신 기판 공급망",
    "Applied Optoelectronics": "어플라이드 옵토일렉트로닉스",
    "Opticore": "옵티코어",
    "OE Solutions": "오이솔루션",
    "Volantis": "볼란티스",
    "Lightmatter": "라이트매터",
    "Ayar Labs": "아야르 랩스",
    "Xscape Photonics": "엑스케이프 포토닉스",
    "Astera Labs": "아스테라 랩스",
    "Corning": "코닝",
    "Samsung Electronics": "삼성전자",
    "CPO Equipment Supply Chain": "CPO 장비 공급망",
}

TRUSTED_SOURCES = {
    "Reuters", "Bloomberg", "Financial Times", "The Wall Street Journal", "CNBC",
    "DigiTimes", "DIGITIMES", "Investing.com", "Barron's", "MarketWatch",
    "NVIDIA Blog", "NVIDIA Newsroom", "Broadcom", "Arista Networks", "Marvell",
    "Lumentum", "Coherent", "AXT", "WIN Semiconductors", "VPEC", "Applied Optoelectronics",
    "Opticore", "옵티코어", "OE Solutions", "오이솔루션",
    "Volantis", "Lightmatter", "Ayar Labs", "Xscape Photonics",
    "KIND", "KRX", "한국거래소",
    "연합뉴스", "전자신문", "ETNews", "Federal Communications Commission", "FCC",
    "U.S. Senate", "Congress.gov", "Astera Labs", "Corning",
    "TrendForce", "MoneyDJ", "Economic Daily News", "UDN", "經濟日報",
    "GMT GLOBAL INC.", "TOYO Automation", "Chieftek Precision",
}

HIGH_SIGNAL_PATTERNS = [
    r"\b3\.2\s*[Tt]\b", r"\b1\.6\s*[Tt]\b", r"\b800\s*[Gg]\b",
    r"co[- ]?packaged optics?", r"\bCPO\b", r"silicon photonics?",
    r"mass production", r"volume production", r"volume shipment", r"shipments?",
    r"customer qualification", r"customer certification", r"qualified", r"certified",
    r"adopt(?:ed|ion)?", r"deploy(?:ed|ment)?", r"production ramp", r"ramp(?:ing)?",
    r"backlog", r"bookings?", r"orders?", r"guidance", r"revenue",
    r"capacity expansion", r"expand(?:ing|s|ed)? capacity", r"new factory", r"new plant",
    r"shortage", r"constraint", r"bottleneck", r"supply tight", r"pricing", r"price increase",
    r"copper", r"optical", r"fiber", r"fibre", r"transceiver", r"laser",
    r"data movement", r"interconnect", r"fabric", r"retimer", r"PCIe", r"CXL",
    r"photonic memory", r"optical memory", r"memory wall", r"memory pooling",
    r"photonic AI", r"photonic inference", r"AI inference system",
    r"compute[- ]to[- ]memory", r"optical fabric", r"micro[- ]?VCSEL", r"VCSEL",
    r"tokens? per second", r"tok/s", r"20\s*trillion", r"10\s*trillion",
    r"240\s*TB/s", r"10\s*TB", r"1\s*pJ/bit", r"220\s*memory chips",
    r"integrated inference engines?", r"customer sampling", r"silicon validation", r"tape[- ]?out", r"benchmark",
    r"PhotonLink", r"integrated optics?", r"complete optical solutions?", r"end[- ]to[- ]end",
    r"vertical integration", r"one[- ]stop", r"\bNPO\b", r"chip[- ]to[- ]chip",
    r"customer engagements?", r"long[- ]term agreements?", r"anchor customers?",
    r"content opportunity", r"content per", r"100\s*Tbps", r"specialty fibers?",
    r"polarization[- ]maintaining", r"mode[- ]matching", r"multicore fibers?",
    r"\bInP\b", r"indium phosphide", r"InP substrate", r"export licen[cs]e",
    r"\bGaAs\b", r"gallium arsenide", r"砷化鎵",
    r"6[- ]inch InP", r"capacity reservation", r"prepayment", r"deposit",
    r"long[- ]term supply", r"crystal growth", r"pilot production", r"wafer substrate",
    r"\bSiPh\b", r"photonics foundry", r"design win",
    r"\bFCC\b", r"Federal Communications Commission", r"Covered List",
    r"equipment authorization", r"Chinese[- ]made", r"China[- ]based",
    r"domestic content", r"domestic end product", r"Buy American",
    r"\b65\s*%\b", r"\b75\s*%\b", r"exempt(?:ion|ions)?", r"restrictions?",
    r"national security systems?", r"Inn[o]?light", r"Eoptolink",
    r"광트랜시버", r"광통신", r"AI 데이터센터", r"ELSFP", r"EML",
    r"공급계약", r"수주", r"검수", r"납품", r"계약기간", r"샘플", r"samples?", r"sampling", r"양산", r"출하",
    r"optical coupling", r"active alignment", r"alignment modules?", r"aligners?",
    r"motion platforms?", r"linear motors?", r"6[- ]axis", r"nanometer", r"50\s*nm",
    r"\bFAU\b", r"\bOSAT\b", r"order visibility", r"delivery visibility",
    r"production capacity", r"\bCAPA\b", r"new lines?", r"assembly lines?",
    r"factory expansion", r"capacity doubles?", r"utilization", r"qualification",
    r"validation", r"verification", r"ahead[- ]of[- ]time orders?",
]

ACTION_PATTERNS = [
    r"mass production", r"volume production", r"shipment", r"customer", r"qualified",
    r"certified", r"adopt", r"deploy", r"ramp", r"backlog", r"booking", r"order",
    r"guidance", r"revenue", r"capacity", r"factory", r"plant", r"shortage",
    r"constraint", r"bottleneck", r"price", r"pricing", r"launch", r"introduc",
    r"engagement", r"agreement", r"anchor customer", r"content opportunity",
    r"integrated optics", r"vertical integration", r"one[- ]stop", r"chip[- ]to[- ]chip",
    r"specialty fiber", r"silicon photonics", r"photonics foundry", r"design win",
    r"optical coupling", r"alignment", r"aligner", r"motion platform", r"linear motor",
    r"FAU", r"OSAT", r"order visibility", r"delivery visibility", r"new line",
    r"assembly line", r"factory expansion", r"capacity", r"CAPA", r"utilization",
    r"qualification", r"validation", r"verification", r"sampling", r"sample",
    r"silicon", r"tape[- ]?out", r"benchmark", r"commercialization", r"delivery",
    r"funding", r"financing", r"raises?", r"series\s+[abc]",
    r"final rule", r"proposed rule", r"rulemaking", r"adopt(?:s|ed)?", r"effective",
    r"restrict(?:s|ed|ion|ions)?", r"ban(?:s|ned)?", r"prohibit(?:s|ed|ion)?",
    r"introduc(?:es|ed)? bill", r"legislation", r"covered list", r"equipment authorization",
    r"domestic content", r"domestic end product", r"buy american", r"exempt(?:ion|ions)?",
    r"export licen[cs]e", r"capacity reservation", r"prepayment", r"deposit",
    r"long[- ]term supply", r"crystal growth", r"pilot production",
    r"공급계약", r"단일판매", r"수주", r"발주서", r"검수", r"납품", r"계약기간",
    r"정정", r"샘플", r"samples?", r"sampling", r"고객.{0,12}(검증|평가|인증)", r"양산", r"출하", r"생산능력", r"증설",
    r"訂單", r"能見度", r"出貨", r"量產", r"擴產", r"產能", r"產能利用率",
    r"驗證", r"認證", r"導入", r"光耦合", r"對位", r"線性馬達", r"六軸",
]

NOISE_PATTERNS = [
    r"stock price", r"price target", r"analyst rating", r"upgrade[s]? .* stock",
    r"downgrade[s]? .* stock", r"options activity", r"insider sells?", r"dividend",
    r"investment story", r"investment case", r"why .* stock", r"simply wall st",
    r"futu niu niu", r"stockstory", r"seeking alpha quant",
    # Market-price/reaction stories are not structural AI-optics events.
    r"\bshares?\b", r"\bstock\b.{0,40}\b(rise|rises|jump|jumps|gain|gains|surge|surges|rally|rallies)",
    r"\b(boost|boosts|lift|lifts|send|sends|drive|drives)\b.{0,60}\bshares?\b",
    r"kucoin", r"marsbit", r"huoxing", r"hyperliquid", r"altcoins?",
    r"관련주", r"테마주", r"주가.{0,30}(급등|상승|강세)", r"(급등|상한가).{0,30}주가",
]

SOURCE_PRIORITY = {
    "Coherent": 100, "NVIDIA Blog": 100, "NVIDIA Newsroom": 100,
    "Broadcom": 100, "Arista Networks": 100, "Marvell": 100,
    "Lumentum": 100, "AXT": 100, "Applied Optoelectronics": 100,
    "Volantis": 100, "Lightmatter": 100, "Ayar Labs": 100, "Xscape Photonics": 100,
    "Opticore": 100, "옵티코어": 100, "OE Solutions": 100, "오이솔루션": 100,
    "KIND": 100, "KRX": 100, "한국거래소": 100, "연합뉴스": 90, "전자신문": 85, "ETNews": 85,
    "Federal Communications Commission": 100, "FCC": 100,
    "U.S. Senate": 100, "Congress.gov": 100, "Astera Labs": 100, "Corning": 100,
    "Samsung Electronics": 100, "Samsung Global Newsroom": 100,
    "Reuters": 95, "Bloomberg": 94, "Financial Times": 93,
    "The Wall Street Journal": 93, "CNBC": 88, "DigiTimes": 85, "DIGITIMES": 85,
    "GlobeNewswire": 84, "PR Newswire": 82,
    "TrendForce": 92, "GMT GLOBAL INC.": 100, "TOYO Automation": 100,
    "Chieftek Precision": 100, "Economic Daily News": 82, "UDN": 82,
    "經濟日報": 82, "MoneyDJ": 78,
    "HPCwire": 70, "Compound Semiconductor": 70, "Investing.com": 65,
}

STORY_STOPWORDS = {
    "a", "an", "and", "are", "as", "at", "be", "by", "for", "from", "has",
    "how", "in", "into", "is", "it", "its", "of", "on", "or", "the", "to",
    "with", "will", "new", "next", "generation", "corp", "corporation",
    "launch", "launches", "launched", "unveil", "unveils", "unveiled",
    "platform", "supports", "support", "enable", "enables", "enabling",
}


def fetch(url: str, timeout: int = 25) -> bytes:
    req = urllib.request.Request(
        url,
        headers={
            "User-Agent": "Mozilla/5.0 khs-watch/1.0",
            "Accept": "application/rss+xml, application/xml, text/xml, */*",
        },
    )
    with urllib.request.urlopen(req, timeout=timeout) as response:
        return response.read()


def parse_date(value: str | None) -> dt.datetime | None:
    if not value:
        return None
    try:
        parsed = email.utils.parsedate_to_datetime(value)
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=dt.timezone.utc)
        return parsed.astimezone(dt.timezone.utc)
    except Exception:
        return None


def normalize_text(value: str) -> str:
    value = html.unescape(value or "")
    value = re.sub(r"\s+", " ", value).strip()
    return value


def event_key(company: str, title: str, source: str) -> str:
    normalized = f"{company}|{title.lower()}|{source.lower()}"
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()


def story_tokens(title: str) -> set[str]:
    value = html.unescape(title or "").lower()
    value = re.sub(r"\s+-\s+[^-]{2,80}$", " ", value)
    value = re.sub(r"[^a-z0-9.\uac00-\ud7a3\u4e00-\u9fff]+", " ", value)
    tokens = {
        token for token in value.split()
        if len(token) >= 3 and token not in STORY_STOPWORDS
    }
    return tokens


def canonical_story_key(company: str, title: str) -> str | None:
    text = html.unescape(title or "").lower()
    if company == "Volantis":
        if re.search(r"series\s*a|\$?88\s*m|funding|financing", text, re.I):
            return "volantis|funding|series-a"
        if re.search(r"customer sampling|customer delivery|customer deployment|integrated inference engines?", text, re.I):
            return "volantis|a1|customer"
        if re.search(r"silicon|tape[- ]?out|benchmark|measured|prototype|240\s*tb/s|10\s*tb|1\s*pj/bit|tokens? per second|tok/s", text, re.I):
            return "volantis|a1|silicon-performance"
        if re.search(r"vcsel|micro[- ]?vcsel|foundry|wafer|laser|supply chain", text, re.I):
            return "volantis|a1|vcsel-supply"
        if re.search(r"a-1|photonic memory|optical memory|memory wall|optical fabric|memory pooling", text, re.I):
            return "volantis|a1|architecture"
    if company == "US Optical Policy":
        if re.search(r"senate|congress|bill|legislation|national security systems?", text, re.I):
            if re.search(r"signed|enacted|becomes? law", text, re.I):
                return "us-optical-policy|congress|enacted"
            if re.search(r"pass(?:es|ed)?", text, re.I):
                return "us-optical-policy|congress|passed"
            return "us-optical-policy|congress|bill"
        if re.search(r"effective|takes? effect|implementation date", text, re.I):
            return "us-optical-policy|fcc|effective"
        if re.search(r"final rule|finaliz(?:e|es|ed|ing)|adopt(?:s|ed)?", text, re.I):
            return "us-optical-policy|fcc|final"
        if re.search(r"proposed rule|rulemaking|notice|comment|draft|consider", text, re.I):
            return "us-optical-policy|fcc|proposal"
        if re.search(r"3\.2\s*t|65\s*%|75\s*%|domestic content|buy american|exempt", text, re.I):
            parts = []
            if re.search(r"3\.2\s*t", text, re.I):
                parts.append("3.2t")
            if re.search(r"65\s*%", text, re.I):
                parts.append("65")
            if re.search(r"75\s*%", text, re.I):
                parts.append("75")
            if re.search(r"domestic content|domestic end product|buy american", text, re.I):
                parts.append("domestic")
            if re.search(r"exempt", text, re.I):
                parts.append("exemption")
            return "us-optical-policy|fcc|content-scenario|" + "-".join(parts or ["generic"])
        return None
    if company in {"AXT", "InP Supply Chain"} and re.search(r"\binp\b|indium phosphide", text, re.I):
        if re.search(r"export licen[cs]e|restriction|china", text, re.I):
            return "axt|inp|export-policy"
        if re.search(r"shortage|tight|capacity|expand|substrate", text, re.I):
            return "axt|inp|capacity-shortage"
    if company == "Coherent" and "photonlink" in text:
        if re.search(r"customer engagements?|long[- ]term(?:\s+\w+){0,6}\s+agreements?|anchor customers?|design win|secures?.{0,60}agreements?", text, re.I):
            return "coherent|photonlink|customer-contract"
        if re.search(r"content opportunity|content per|100\s*tbps|15,?000", text, re.I):
            return "coherent|photonlink|content-value"
        if re.search(r"chip[- ]to[- ]chip", text, re.I):
            return "coherent|photonlink|chip-to-chip"
        if re.search(r"specialty fibers?|polarization[- ]maintaining|mode[- ]matching|multicore fibers?", text, re.I):
            return "coherent|photonlink|specialty-fiber"
        if re.search(r"\binp\b.*(?:capacity|expand)|(?:capacity|expand).*\binp\b", text, re.I):
            return "coherent|photonlink|inp-capacity"
        if re.search(r"revenue|guidance|mass production|volume production|shipments?|production ramp|ramp(?:ing)?", text, re.I):
            return "coherent|photonlink|commercial-ramp"
        return "coherent|photonlink|launch"
    return None


def source_priority(source: str) -> int:
    source = normalize_text(source)
    source_lower = source.lower()
    for name, priority in SOURCE_PRIORITY.items():
        name_lower = name.lower()
        if source_lower == name_lower or name_lower in source_lower:
            return priority
    if re.search(r"simply wall|futu|stockstory|kucoin|marsbit|huoxing|tradingbeats", source, re.I):
        return 5
    return 50


def same_underlying_story(a: dict, b: dict) -> bool:
    if a.get("company") != b.get("company"):
        return False

    if a.get("company") == "CPO Equipment Supply Chain":
        # Sector articles are often rewritten with different supplier names/headlines.
        # Treat near-same-date stories with the same commercial stage as one event,
        # while keeping orders, capacity, qualification and shipment as separate events.
        if a.get("category") != b.get("category"):
            return False
        try:
            ap = dt.datetime.fromisoformat(a.get("published") or "")
            bp = dt.datetime.fromisoformat(b.get("published") or "")
            if abs((ap - bp).total_seconds()) > 72 * 3600:
                return False
        except Exception:
            pass
        ta = story_tokens(a.get("title", ""))
        tb = story_tokens(b.get("title", ""))
        overlap = len(ta & tb)
        union = len(ta | tb)
        smaller = min(len(ta), len(tb)) if ta and tb else 0
        jaccard = overlap / union if union else 0.0
        containment = overlap / smaller if smaller else 0.0
        shared_anchor = bool(re.search(
            r"chieftek|gmt|toyo|suruga|ficontec|allring|fittech|2027|q2|1\.6t|800g",
            " ".join(sorted(ta & tb)),
            re.I,
        ))
        return (shared_anchor and (jaccard >= 0.20 or containment >= 0.38)) or jaccard >= 0.42

    a_key = canonical_story_key(a.get("company", ""), a.get("title", ""))
    b_key = canonical_story_key(b.get("company", ""), b.get("title", ""))
    if a_key and b_key:
        return a_key == b_key
    if a.get("category") != b.get("category"):
        return False
    ta = story_tokens(a.get("title", ""))
    tb = story_tokens(b.get("title", ""))
    if not ta or not tb:
        return False
    overlap = len(ta & tb)
    union = len(ta | tb)
    smaller = min(len(ta), len(tb))
    jaccard = overlap / union if union else 0.0
    containment = overlap / smaller if smaller else 0.0
    return jaccard >= 0.48 or containment >= 0.72


def prefer_story_item(candidate: dict, current: dict) -> bool:
    c_rank = source_priority(candidate.get("source") or "")
    o_rank = source_priority(current.get("source") or "")
    if c_rank != o_rank:
        return c_rank > o_rank
    if candidate.get("score", 0) != current.get("score", 0):
        return candidate.get("score", 0) > current.get("score", 0)
    return (candidate.get("published") or "") > (current.get("published") or "")


def query_google_news(
    query: str,
    hl: str = "en-US",
    gl: str = "US",
    ceid: str = "US:en",
) -> list[dict]:
    params = urllib.parse.urlencode({
        "q": query,
        "hl": hl,
        "gl": gl,
        "ceid": ceid,
    })
    url = f"https://news.google.com/rss/search?{params}"
    root = ET.fromstring(fetch(url))
    items: list[dict] = []
    for item in root.findall("./channel/item")[:20]:
        title = normalize_text(item.findtext("title") or "")
        link = normalize_text(item.findtext("link") or "")
        pub = parse_date(item.findtext("pubDate"))
        source_node = item.find("source")
        source = normalize_text(source_node.text if source_node is not None and source_node.text else "")
        source_url = normalize_text(source_node.attrib.get("url", "") if source_node is not None else "")
        if title and link:
            items.append({
                "title": title,
                "link": link,
                "published": pub.isoformat() if pub else None,
                "source": source,
                "source_url": source_url,
            })
    return items


def is_noise(text: str) -> bool:
    return any(re.search(pattern, text, flags=re.I) for pattern in NOISE_PATTERNS)


def signal_score(title: str, source: str) -> int:
    text = f"{title} {source}"
    if is_noise(text):
        return -10
    score = 0
    if re.search(r"\b3\.2\s*[Tt]\b", text, re.I):
        score += 6
    if re.search(r"\b1\.6\s*[Tt]\b", text, re.I):
        score += 5
    if re.search(r"co[- ]?packaged optics?|\bCPO\b|silicon photonics?", text, re.I):
        score += 5
    if re.search(r"PhotonLink|integrated optics?|complete optical solutions?|end[- ]to[- ]end|vertical integration|one[- ]stop", text, re.I):
        score += 7
    if re.search(r"\bNPO\b|chip[- ]to[- ]chip", text, re.I):
        score += 5
    if re.search(r"customer engagements?|long[- ]term agreements?|anchor customers?", text, re.I):
        score += 5
    if re.search(r"content opportunity|content per|100\s*Tbps", text, re.I):
        score += 5
    if re.search(r"specialty fibers?|polarization[- ]maintaining|mode[- ]matching|multicore fibers?", text, re.I):
        score += 4
    if re.search(r"\bInP\b|indium phosphide|InP substrate|\bGaAs\b|gallium arsenide|砷化鎵|\bSiPh\b|photonics foundry|design win", text, re.I):
        score += 4
    if re.search(r"photonic memory|optical memory|memory wall|memory pooling|compute[- ]to[- ]memory|optical fabric|micro[- ]?VCSEL|VCSEL|photonic AI|photonic inference|AI inference system", text, re.I):
        score += 6
    if re.search(r"funding|financing|raises?|series\s+[abc]", text, re.I):
        score += 3
    if re.search(r"tokens? per second|tok/s|20\s*trillion|10\s*trillion|240\s*TB/s|10\s*TB|1\s*pJ/bit|220\s*memory chips", text, re.I):
        score += 4
    if re.search(r"customer sampling|integrated inference engines?|silicon validation|tape[- ]?out|benchmark|commercialization", text, re.I):
        score += 5
    if re.search(r"6[- ]inch InP|capacity reservation|prepayment|deposit|long[- ]term supply|crystal growth|pilot production|wafer substrate", text, re.I):
        score += 5
    if re.search(r"\bFCC\b|Federal Communications Commission|Covered List|equipment authorization", text, re.I):
        score += 7
    if re.search(r"Chinese[- ]made|China[- ]based|domestic content|domestic end product|Buy American|\b65\s*%\b|\b75\s*%\b|Inn[o]?light|Eoptolink", text, re.I):
        score += 4
    if re.search(r"final rule|proposed rule|rulemaking|restrict(?:ion|ions)?|ban|prohibit|legislation|national security systems?", text, re.I):
        score += 5
    if re.search(r"export licen[cs]e", text, re.I):
        score += 5
    if re.search(r"optical coupling|active alignment|alignment modules?|aligners?|motion platforms?|linear motors?|6[- ]axis|nanometer|50\s*nm|\bFAU\b", text, re.I):
        score += 5
    if re.search(r"\bOSAT\b|qualification|validation|verification", text, re.I):
        score += 4
    if re.search(r"order visibility|delivery visibility|backlog|ahead[- ]of[- ]time orders?", text, re.I):
        score += 5
    if re.search(r"production capacity|\bCAPA\b|new lines?|assembly lines?|factory expansion|capacity doubles?|utilization", text, re.I):
        score += 4
    if re.search(r"訂單|能見度|出貨|量產|擴產|產能|產能利用率", text):
        score += 5
    if re.search(r"光耦合|對位|線性馬達|六軸|驗證|認證|導入", text):
        score += 4
    if re.search(r"mass production|volume production|customer qualification|customer certification|qualified|certified", text, re.I):
        score += 5
    if re.search(r"adopt|deploy|ramp|shipment", text, re.I):
        score += 4
    if re.search(r"backlog|bookings?|orders?|guidance|revenue", text, re.I):
        score += 4
    if re.search(r"shortage|constraint|bottleneck|supply tight|price increase|pricing", text, re.I):
        score += 4
    if re.search(r"capacity expansion|factory|plant|capex", text, re.I):
        score += 3
    if re.search(r"copper|optical|fiber|fibre|transceiver|laser|data movement|interconnect|fabric|retimer|PCIe|CXL", text, re.I):
        score += 2
    if re.search(r"광트랜시버|광통신|AI 데이터센터", text, re.I):
        score += 3
    if re.search(r"공급계약|단일판매|수주|발주서|\bPO\b", text, re.I):
        score += 5
    if re.search(r"검수|납품|계약기간|정정", text, re.I):
        score += 4
    if re.search(r"샘플|samples?|sampling|고객.{0,20}(검증|평가|인증)|검증|인증|양산|출하|증설|생산능력", text, re.I):
        score += 4
    if re.search(r"AI|data ?center|datacenter|hyperscaler|GPU|XPU", text, re.I):
        score += 2
    if any(source.lower() == trusted.lower() for trusted in TRUSTED_SOURCES):
        score += 2
    return score


def stage_for(title: str) -> str:
    if re.search(r"customer delivery|customer deployment|integrated inference engines?", title, re.I):
        return "고객 샘플·배치"
    if re.search(r"silicon validation|silicon demonstrates?|tape[- ]?out|benchmark|measured|prototype", title, re.I):
        return "실리콘·성능 검증"
    if re.search(r"commercialization|mass production|volume production|production ramp", title, re.I):
        return "상용화·양산"
    if re.search(r"final rule|finaliz(?:e|es|ed|ing)|adopt(?:s|ed)?|effective|takes? effect|signed|enacted", title, re.I):
        return "최종 규칙·시행"
    if re.search(r"proposed rule|rulemaking|notice|comment period|draft rule|considering", title, re.I):
        return "규칙 제안·검토"
    if re.search(r"senate|congress|introduc(?:es|ed)? bill|legislation", title, re.I):
        return "법안 발의·입법"
    if re.search(r"export licen[cs]e|export restriction", title, re.I):
        return "수출허가·공급망 규제"
    if re.search(r"계약기간.{0,20}(변경|연장)|검수.{0,20}(지연|조정|변경)|납품.{0,20}(지연|조정|변경)|정정", title, re.I):
        return "납기·검수 변경"
    if re.search(r"공급계약|단일판매|수주|발주서|\bPO\b", title, re.I):
        return "수주·가시성"
    if re.search(r"샘플|samples?|sampling|고객.{0,20}(검증|평가|인증)|검증|인증", title, re.I):
        return "고객 검증·양산 도입"
    if re.search(r"양산|출하", title, re.I):
        return "양산·출하"
    if re.search(r"증설|생산능력", title, re.I):
        return "설비투자"
    if re.search(r"驗證|認證|導入|\bOSAT\b|qualification|validation|verification|passes?.{0,40}certification", title, re.I):
        return "고객 검증·양산 도입"
    if re.search(r"訂單|能見度|order visibility|delivery visibility|backlog|orders?|bookings?", title, re.I):
        return "수주·가시성"
    if re.search(r"擴產|產能|產能利用率|new line|factory|capacity|CAPA|utilization", title, re.I):
        return "설비투자"
    if re.search(r"出貨|量產|mass production|volume production|shipment|ramp", title, re.I):
        return "양산·출하"
    if re.search(r"\bOSAT\b|qualification|validation|verification|passes?.{0,40}certification", title, re.I):
        return "고객 검증·양산 도입"
    if re.search(r"order visibility|delivery visibility|backlog|orders?|bookings?", title, re.I):
        return "수주·가시성"
    if re.search(r"long[- ]term(?:\s+\w+){0,6}\s+agreement|anchor customer|secures?.{0,60}agreement", title, re.I):
        return "장기계약·고객 확정"
    if re.search(r"customer engagements?|design win|qualified|certified|adopt|deploy", title, re.I):
        return "고객 검증·채택"
    if re.search(r"revenue|guidance|backlog|bookings?|orders?", title, re.I):
        return "실적·수주 확인"
    if re.search(r"mass production|volume production|shipment|ramp", title, re.I):
        return "양산·출하"
    if re.search(r"qualified|certified|customer qualification|customer certification|adopt|deploy", title, re.I):
        return "고객 검증·채택"
    if re.search(r"shortage|constraint|bottleneck|supply tight|pricing|price increase", title, re.I):
        return "공급 병목·가격"
    if re.search(r"capacity expansion|factory|plant|capex", title, re.I):
        return "설비투자"
    return "기술·제품 준비"


def category_for(title: str, company: str) -> str:
    if company == "Volantis":
        if re.search(r"customer sampling|customer delivery|customer deployment|integrated inference engines?", title, re.I):
            return "광메모리 고객검증·상용화"
        if re.search(r"silicon|tape[- ]?out|benchmark|measured|prototype|240\s*TB/s|10\s*TB|1\s*pJ/bit|tokens? per second|tok/s", title, re.I):
            return "광메모리 성능·검증"
        if re.search(r"VCSEL|micro[- ]?VCSEL|supply chain|foundry|wafer|laser", title, re.I):
            return "VCSEL 광메모리 공급망"
        return "광메모리·추론 아키텍처"
    if company in {"Lightmatter", "Ayar Labs", "Xscape Photonics"}:
        if re.search(r"customer|deployment|production|shipment|sampling|qualification|validation", title, re.I):
            return "광컴퓨팅 상용화·고객검증"
        return "광컴퓨팅·스케일업 인터커넥트"
    if company == "US Optical Policy":
        if re.search(r"senate|congress|bill|legislation|national security systems?", title, re.I):
            return "미국 광트랜시버 규제·법안"
        return "FCC 광트랜시버 규제"
    if company in {"AXT", "InP Supply Chain"} and re.search(r"capacity reservation|prepayment|deposit|long[- ]term supply|agreement", title, re.I):
        return "InP 기판 장기계약·생산능력"
    if company in {"AXT", "InP Supply Chain"} and re.search(r"export licen[cs]e|export restriction", title, re.I):
        return "InP 수출허가·공급망"
    if company in {"AXT", "InP Supply Chain"} and re.search(r"\bInP\b|indium phosphide|substrate|6[- ]inch", title, re.I):
        return "InP 기판 병목"
    if company == "GaAs Optical Supply Chain":
        return "GaAs 광통신 기판·파운드리"
    if company == "Opticore":
        if re.search(r"계약기간|검수|납품.{0,20}(지연|조정)|정정", title, re.I):
            return "국내 AI 광트랜시버 납기·검수"
        if re.search(r"공급계약|단일판매|수주|발주서|\bPO\b|400G|800G", title, re.I):
            return "국내 AI 광트랜시버 수주"
        return "국내 AI 광트랜시버"
    if company == "OE Solutions":
        if re.search(r"1\.6\s*T|ELSFP|EML", title, re.I) and re.search(r"샘플|samples?|sampling|검증|qualification|certification|고객", title, re.I):
            return "국내 1.6T 고객검증·샘플"
        if re.search(r"수주|공급|order|shipment|양산|출하", title, re.I):
            return "국내 광통신 수주·양산"
        return "국내 광통신"
    if company == "CPO Equipment Supply Chain":
        if re.search(r"驗證|認證|導入|\bOSAT\b|qualification|validation|verification|certif", title, re.I):
            return "CPO 장비 고객검증·도입"
        if re.search(r"擴產|產能|產能利用率|production capacity|\bCAPA\b|factory|new lines?|assembly lines?|expand|acquisition|utilization|capacity doubles?", title, re.I):
            return "CPO 장비 증설·가동률"
        if re.search(r"出貨|量產|shipments?|mass production|volume production|ramp", title, re.I):
            return "CPO 장비 출하·양산"
        if re.search(r"訂單|能見度|order visibility|delivery visibility|backlog|orders?|bookings?|ahead[- ]of[- ]time orders?", title, re.I):
            return "CPO 장비 수주·가시성"
        return "CPO 정밀정렬·광결합 장비"
    if company == "Coherent" and re.search(r"PhotonLink|integrated optics?|complete optical solutions?|end[- ]to[- ]end|vertical integration|one[- ]stop", title, re.I):
        return "광 링크 통합·수직계열화"
    if re.search(r"customer engagements?|long[- ]term(?:\s+\w+){0,6}\s+agreements?|anchor customers?|secures?.{0,60}agreements?", title, re.I):
        return "고객·장기계약"
    if re.search(r"content opportunity|content per|100\s*Tbps", title, re.I):
        return "광학 콘텐츠 가치"
    if re.search(r"chip[- ]to[- ]chip", title, re.I):
        return "칩 간 광연결"
    if re.search(r"specialty fibers?|polarization[- ]maintaining|mode[- ]matching|multicore fibers?", title, re.I):
        return "특수광섬유"
    if company == "Samsung Electronics" and re.search(r"silicon photonics|\bSiPh\b|PIC|photonics foundry|optical module|optical engine|design win", title, re.I):
        return "SiPh 파운드리"
    if re.search(r"\b3\.2\s*[Tt]\b", title, re.I):
        return "3.2T 전환"
    if re.search(r"co[- ]?packaged optics?|\bCPO\b|silicon photonics?", title, re.I):
        return "CPO·실리콘 포토닉스"
    if re.search(r"\b1\.6\s*[Tt]\b", title, re.I):
        return "1.6T 전환"
    if re.search(r"shortage|constraint|bottleneck|supply tight|pricing|price increase", title, re.I):
        return "공급 병목·가격"
    if re.search(r"backlog|bookings?|orders?|guidance|revenue", title, re.I):
        return "수주·실적"
    if company == "Corning" and re.search(r"glass substrate|advanced packaging", title, re.I):
        return "유리기판·첨단 패키징"
    if re.search(r"fiber|fibre|optical|transceiver|laser", title, re.I):
        return "광통신"
    if re.search(r"PCIe|CXL|retimer|fabric|interconnect", title, re.I):
        return "랙 내부 인터커넥트"
    return "AI 네트워킹"


def meaning_for(category: str) -> str:
    mapping = {
        "광메모리·추론 아키텍처": "광학을 랙 간 네트워크가 아니라 가속기와 메모리 사이까지 끌어오면 HBM 용량·대역폭의 물리적 한계를 우회할 수 있어 추론 시스템 구조 자체를 바꾸는 신호입니다.",
        "광메모리 고객검증·상용화": "설계 목표를 넘어 실제 고객 샘플·통합 추론엔진·배치 일정이 확인되면 광메모리 아키텍처가 연구단계에서 매출 가능 단계로 넘어가는 핵심 검증 신호입니다.",
        "광메모리 성능·검증": "토큰 처리량·메모리 대역폭·용량·비트당 에너지가 실제 실리콘 또는 독립 벤치마크로 확인되면 광메모리의 경제성이 검증되는 신호입니다.",
        "VCSEL 광메모리 공급망": "볼란티스처럼 InP 외부레이저 대신 GaAs 기반 micro-VCSEL을 쓰는 구조가 양산되면 VCSEL 에피·레이저·패키징 공급망에 새로운 AI 매출 경로가 열릴 수 있습니다.",
        "광컴퓨팅 상용화·고객검증": "라이트매터·아야르 랩스·엑스케이프 등에서 샘플링·고객검증·생산·배치가 확인되면 광인터커넥트가 기술 시연에서 실제 AI 시스템 매출로 이동하는 신호입니다.",
        "광컴퓨팅·스케일업 인터커넥트": "GPU·XPU·메모리 사이 데이터 이동 병목을 광링크로 줄이는 구조가 확산되면 AI 인프라 가치가 연산칩에서 광엔진·레이저·패키징까지 넓어지는 신호입니다.",
        "FCC 광트랜시버 규제": "완제품 국적보다 부품 원산지·가치비중까지 규제가 내려오면 3.2T 세대의 공급사 선정과 레이저·InP·DSP 가치배분이 직접 바뀌는 정책 신호입니다.",
        "미국 광트랜시버 규제·법안": "FCC 상업시장 규제와 연방 국가안보시스템 조달 제한은 범위가 다르므로, 법안 통과·적용대상 확대 여부가 중국 광모듈의 실제 미국 매출 접근성을 바꾸는 신호입니다.",
        "InP 기판 병목": "InP 기판 수급·수출허가·증설은 EML·CW 레이저와 1.6T·3.2T 광모듈 출하량의 상류 한계를 결정해 LITE·COHR·AXTI의 물량·가격·가동률에 직접 연결됩니다.",
        "InP 기판 장기계약·생산능력": "Coherent·Lumentum 같은 광부품사가 6인치 InP 생산능력을 선지급·예약하면 1.6T·3.2T·CPO용 레이저 기판 수요가 단순 전망에서 실제 장기 발주로 넘어갔다는 강한 검증 신호입니다.",
        "InP 수출허가·공급망": "InP 수출허가·원산지·납기 변화는 광레이저와 1.6T·3.2T 광모듈의 실제 출하량을 좌우하는 상류 공급망 신호입니다.",
        "GaAs 광통신 기판·파운드리": "1.6T·CPO 전환으로 GaAs 기반 광소자·포토다이오드·레이저·파운드리 수요가 늘면 InP 병목을 보완하는 단거리 광링크와 광통신 소재 공급망의 별도 매출축이 커지는 신호입니다.",
        "국내 AI 광트랜시버 수주": "옵티코어의 400G·800G AI 데이터센터 광트랜시버가 실제 PO·공급계약으로 확인되면 국내 광통신 테마가 아니라 현재 매출로 연결되는 직접 신호입니다.",
        "국내 AI 광트랜시버 납기·검수": "납품·검수 일정 변경은 수주금액 자체보다 매출 인식 시점을 바꾸므로 계약기간 연장·검수 완료 여부를 별도 추적해야 합니다.",
        "국내 AI 광트랜시버": "국내 AI 데이터센터용 400G·800G 광트랜시버의 고객·수주·양산 연결을 확인하는 신호입니다.",
        "국내 1.6T 고객검증·샘플": "오이솔루션의 ELSFP·EML 샘플이 고객 검증을 거쳐 양산 채택되면 1.6T AI 네트워킹 매출이 개발 단계에서 실제 주문 단계로 넘어가는 신호입니다.",
        "국내 광통신 수주·양산": "국내 광통신 신제품이 실제 수주·출하·양산으로 전환되는지 확인하는 매출 검증 신호입니다.",
        "국내 광통신": "국내 광통신 업체의 800G·1.6T 제품 개발이 고객 검증·주문으로 연결되는지 확인하는 신호입니다.",
        "3.2T 전환": "차세대 광링크가 시제품에서 고객 검증·양산으로 넘어가면 광 DSP·레이저·모듈의 다음 매출 사이클 선행신호입니다.",
        "CPO·실리콘 포토닉스": "스위치와 광학을 더 가깝게 결합해 전력·대역폭 병목을 줄이는 구조 변화로, 기존 플러거블 광모듈의 가치 배분까지 바꿀 수 있습니다.",
        "1.6T 전환": "800G에서 1.6T로 실제 출하가 이동하는 신호로, 광 DSP·레이저·고밀도 연결부품의 현재 매출 증가와 직접 연결됩니다.",
        "공급 병목·가격": "수요가 공급능력을 앞서는지 확인하는 신호입니다. 평균판매단가에는 긍정적일 수 있지만 고객 데이터센터 가동 지연은 역풍입니다.",
        "수주·실적": "기술 기대가 실제 고객 주문·백로그·매출로 전환되는지 확인하는 가장 강한 검증 신호입니다.",
        "유리기판·첨단 패키징": "고밀도 AI 패키징의 휨·배선·열 문제를 줄이는 방향으로 채택이 늘면 Corning의 신규 AI 매출 경로가 열릴 수 있습니다.",
        "광통신": "GPU 수 증가로 랙·데이터센터 사이 데이터 이동량이 커지면서 구리 대신 광 연결 비중이 상승하는 구조적 수혜 신호입니다.",
        "랙 내부 인터커넥트": "GPU·CPU·메모리 사이 데이터 이동 지연을 줄여 비싼 가속기의 실제 이용률을 높이는 부품 수요와 연결됩니다.",
        "AI 네트워킹": "AI 성능 병목이 단일 GPU 연산력에서 데이터 이동·네트워크 전체로 넓어지는 흐름을 확인하는 신호입니다.",
        "광 링크 통합·수직계열화": "레이저·정밀광학·실리콘포토닉스·특수광섬유·수신부를 한 회사가 통합 공급하면 AI 광학의 가치가 개별 부품에서 전체 링크 설계·조립·테스트로 이동하는 신호입니다.",
        "고객·장기계약": "고객 협업이 장기계약과 앵커 고객으로 전환되면 기술 기대가 반복 가능한 양산 매출로 넘어가는 강한 검증 신호입니다.",
        "광학 콘텐츠 가치": "스위치·xPU당 광학 콘텐츠 금액이 높아지면 같은 AI 설비투자 안에서도 광학 부품·어셈블리의 매출 몫이 커지는 신호입니다.",
        "칩 간 광연결": "광 연결이 랙·패키지 경계를 넘어 칩 간 연결로 들어가면 2029~2030년 이후 메모리·가속기 패키징 구조까지 바꿀 수 있는 장기 재평가 신호입니다.",
        "특수광섬유": "범용 광섬유가 아니라 편광유지·모드매칭·멀티코어 같은 고부가 특수광섬유의 증설·양산이 확인되면 CPO·NPO 내부 콘텐츠 확대와 직접 연결됩니다.",
        "SiPh 파운드리": "대형 광모듈사의 실리콘포토닉스 설계가 외부 파운드리 양산으로 연결되면 삼성전자 등 파운드리의 신규 AI 매출 경로가 열리는 신호입니다.",
        "CPO 장비 수주·가시성": "CPO·SiPh 양산 전에 정밀 정렬·광 결합 장비 주문이 먼저 차는 선행신호입니다. 주문 가시성이 늘면 고객이 실제 양산 설비투자 예산을 집행하고 있다는 뜻에 가깝습니다.",
        "CPO 장비 증설·가동률": "장비업체가 신규 라인·공장·조립능력을 늘리는 것은 수주가 단기 샘플을 넘어 반복 양산 수요로 전환될 가능성을 보여주는 설비투자 신호입니다.",
        "CPO 장비 출하·양산": "정밀 모션·광 결합 장비가 실제 출하·양산으로 넘어가면 CPO 기술 발표가 제조현장 CAPEX와 매출로 연결됐다는 직접 증거입니다.",
        "CPO 장비 고객검증·도입": "글로벌 광통신 고객이나 OSAT 인증·검증 통과는 장비가 시험평가를 넘어 실제 생산라인에 채택될 가능성을 높이는 핵심 관문입니다.",
        "CPO 정밀정렬·광결합 장비": "CPO 제조의 나노미터급 정렬·광 결합·FAU 공정 장비 수요가 늘면 광학 부품뿐 아니라 생산장비까지 AI 인프라 설비투자 수혜가 확산되는 신호입니다.",
    }
    return mapping[category]


def risk_for(category: str) -> str:
    mapping = {
        "광메모리·추론 아키텍처": "현재 공개 수치는 대부분 회사의 설계목표이므로 실리콘 존재 여부·메모리 종류·패키징 수율·실제 토큰당 비용이 검증되지 않으면 기대가 매출로 이어지지 않을 수 있습니다.",
        "광메모리 고객검증·상용화": "2027 고객 인도 일정이 지연되거나 고객 실명이 공개되지 않은 채 샘플 단계에 머물면 상용화 시점이 뒤로 밀릴 수 있습니다.",
        "광메모리 성능·검증": "시뮬레이션·설계목표와 실측치를 혼동하면 안 되며, 대형 모델에서의 지연시간·전력·오류율·메모리 일관성 검증이 실패할 수 있습니다.",
        "VCSEL 광메모리 공급망": "micro-VCSEL 수율·열안정성·수명·웨이퍼 공급과 고밀도 패키징 정렬 난도가 병목이 되면 InP 회피 효과가 줄어들 수 있습니다.",
        "광컴퓨팅 상용화·고객검증": "고객검증·패키징 수율·레이저 신뢰성·표준화 일정이 늦어지면 대량배치가 지연될 수 있습니다.",
        "광컴퓨팅·스케일업 인터커넥트": "광링크가 구리 대비 비용·전력·유지보수 우위를 충분히 입증하지 못하거나 표준 경쟁이 길어지면 채택 속도가 늦어질 수 있습니다.",
        "FCC 광트랜시버 규제": "3.2T·65% 같은 시장 시나리오가 최종 규정에서 바뀌거나, 미국 제조요건이 더 엄격해지면 예상 수혜기업과 공급망 구조가 달라질 수 있습니다.",
        "미국 광트랜시버 규제·법안": "연방 국가안보시스템 조달 제한을 전체 상업용 데이터센터 금지로 확대해석하면 실적 민감도를 과대평가할 수 있습니다.",
        "InP 기판 병목": "중국 수출허가·원산지 규제가 강화되면 InP 가격 상승의 수혜보다 공급중단·고객 이원화가 먼저 나타날 수 있습니다.",
        "InP 기판 장기계약·생산능력": "선지급·예약 계약이 있어도 6인치 결정성장 수율·파일럿→양산 전환·수출허가가 지연되면 고객의 예약 물량을 실제 출하하지 못할 수 있습니다.",
        "InP 수출허가·공급망": "허가 완화가 공급 정상화로 이어지면 가격·리드타임 프리미엄이 빠르게 축소될 수 있고, 반대로 규제 강화 시 출하 자체가 막힐 수 있습니다.",
        "GaAs 광통신 기판·파운드리": "GaAs 수요가 1.6T 광통신이 아니라 스마트폰·위성 등 다른 응용에 더 크게 좌우되면 AI 데이터센터 수혜 민감도를 과대평가할 수 있습니다.",
        "국내 AI 광트랜시버 수주": "반복 PO가 이어지지 않거나 고객 집중도가 높으면 단일 계약의 매출 기여가 일회성에 그칠 수 있습니다.",
        "국내 AI 광트랜시버 납기·검수": "검수 지연이 반복되면 매출 인식이 뒤로 밀리고 재고·운전자본 부담이 먼저 커질 수 있습니다.",
        "국내 AI 광트랜시버": "고객 실명·반복수주·검수 완료가 확인되지 않으면 실제 AI 데이터센터 매출 민감도를 과대평가할 수 있습니다.",
        "국내 1.6T 고객검증·샘플": "샘플 출하가 고객 인증·양산 PO로 이어지지 않거나 ELSFP 열·신뢰성 검증이 늦어지면 매출 시점이 지연될 수 있습니다.",
        "국내 광통신 수주·양산": "초기 수주가 반복계약으로 이어지지 않거나 가격 하락이 빠르면 외형 증가 대비 마진 개선이 제한될 수 있습니다.",
        "국내 광통신": "제품 발표만 있고 고객 검증·수주가 없으면 투자 기대가 실제 매출보다 앞설 수 있습니다.",
        "3.2T 전환": "고객 인증·대량생산 수율이 지연되면 매출 시점이 뒤로 밀릴 수 있습니다.",
        "CPO·실리콘 포토닉스": "레이저 신뢰성·수율·현장 교체 난도와 플러거블 대비 경제성이 핵심 실패 경로입니다.",
        "1.6T 전환": "물량 증가보다 평균판매단가 하락이 빠르면 매출 성장 폭이 제한될 수 있습니다.",
        "공급 병목·가격": "가격 상승이 고객의 AI 랙 배치를 늦추면 단기 출하량에는 오히려 역풍이 될 수 있습니다.",
        "수주·실적": "한두 고객 집중이나 선주문이 실제 반복매출로 이어지지 않는지 확인해야 합니다.",
        "유리기판·첨단 패키징": "고객 인증·수율·기존 유기기판 대비 원가 우위가 확보되지 않으면 채택이 늦어질 수 있습니다.",
        "광통신": "전력·열·레이저 공급 및 고객 설계 전환 일정이 광부품 출하 시점을 늦출 수 있습니다.",
        "랙 내부 인터커넥트": "PCIe/CXL 세대 전환 지연이나 고객 자체 설계가 범용 부품 시장을 축소할 수 있습니다.",
        "AI 네트워킹": "GPU 설비투자가 둔화하거나 하이퍼스케일러가 네트워크 투자를 뒤로 미루면 수혜 시점이 지연될 수 있습니다.",
        "광 링크 통합·수직계열화": "통합 공급사가 부품을 내재화할수록 독립 레이저·렌즈·아이솔레이터·특수광섬유 업체의 외부 공급 기회가 줄어들 수 있습니다.",
        "고객·장기계약": "협업 고객 수가 늘어도 실제 양산 발주와 반복매출로 전환되지 않으면 매출 가시성이 과대평가될 수 있습니다.",
        "광학 콘텐츠 가치": "최대 콘텐츠 기회와 실제 평균판매단가는 다르므로 고객 믹스·수율·가격 인하로 실현 금액이 낮아질 수 있습니다.",
        "칩 간 광연결": "패키지 내 광연결은 수율·열·정렬 정밀도·신뢰성 검증이 어려워 2029~2030년 일정이 지연될 수 있습니다.",
        "특수광섬유": "특수광섬유 증설이 실제 CPO·NPO 채택보다 빠르면 가동률과 가격이 먼저 압박받을 수 있습니다.",
        "SiPh 파운드리": "고객 실명이 공개되지 않거나 시험생산 물량에 그치면 대형 양산 수주로 보기 어렵고 기존 선발 파운드리와의 경쟁도 남습니다.",
        "CPO 장비 수주·가시성": "6~12개월 선발주나 중복 발주가 실제 최종 CPO 수요보다 앞서면 수주잔고가 향후 취소·납기 연기로 바뀔 수 있습니다.",
        "CPO 장비 증설·가동률": "증설 속도가 실제 CPO 양산보다 빠르면 신규 공장 가동률과 고정비 부담이 먼저 악화될 수 있습니다.",
        "CPO 장비 출하·양산": "장비 출하 후 고객 검수·설치·수율 확보가 늦어지면 매출 인식과 후속 주문이 지연될 수 있습니다.",
        "CPO 장비 고객검증·도입": "OSAT·광모듈 고객의 검증을 통과해도 양산 라인 적용이나 반복 발주까지 이어지지 않으면 매출 규모는 제한될 수 있습니다.",
        "CPO 정밀정렬·광결합 장비": "정렬 정밀도·검사시간·수율이 목표에 못 미치거나 CPO 채택 일정이 늦어지면 장비 투자가 뒤로 밀릴 수 있습니다.",
    }
    return mapping[category]


def _self_test_korean_optics_alerts() -> None:
    opticore_order = "옵티코어 AI 데이터센터용 400G 800G 광트랜시버 공급계약 체결"
    assert signal_score(opticore_order, "전자신문") >= 7
    assert category_for(opticore_order, "Opticore") == "국내 AI 광트랜시버 수주"
    assert stage_for(opticore_order) == "수주·가시성"

    opticore_delay = "옵티코어 400G 800G 광트랜시버 고객사 검수 일정 조정으로 계약기간 변경"
    assert signal_score(opticore_delay, "한국거래소") >= 7
    assert category_for(opticore_delay, "Opticore") == "국내 AI 광트랜시버 납기·검수"
    assert stage_for(opticore_delay) == "납기·검수 변경"

    oe_sample = "OE Solutions begins Q3 2026 customer sampling of ELSFP for 1.6T AI networking"
    assert signal_score(oe_sample, "OE Solutions") >= 7
    assert category_for(oe_sample, "OE Solutions") == "국내 1.6T 고객검증·샘플"
    assert stage_for(oe_sample) == "고객 검증·양산 도입"

    assert len(story_tokens("옵티코어 AI 데이터센터 광트랜시버 공급계약")) >= 3
    assert source_priority("전자신문") >= 65
    assert source_priority("OE Solutions") >= 65


def load_state() -> dict:
    if not STATE_PATH.exists():
        return {"initialized": False, "seen_keys": []}
    try:
        return json.loads(STATE_PATH.read_text(encoding="utf-8"))
    except Exception:
        return {"initialized": False, "seen_keys": []}


def main() -> None:
    _self_test_korean_optics_alerts()
    (ROOT / "out").mkdir(parents=True, exist_ok=True)
    (ROOT / "data").mkdir(parents=True, exist_ok=True)

    state = load_state()
    seen = set(state.get("seen_keys") or [])
    all_relevant: list[dict] = []
    errors: list[str] = []

    cutoff = NOW - dt.timedelta(days=7)
    for company, meta in COMPANIES.items():
        try:
            feed_items = []
            locales = meta.get("locales") or [{"hl": "en-US", "gl": "US", "ceid": "US:en"}]
            queries = meta.get("queries") or [meta.get("query")]
            for query in [q for q in queries if q]:
                for locale in locales:
                    feed_items.extend(query_google_news(
                        query,
                        hl=locale.get("hl", "en-US"),
                        gl=locale.get("gl", "US"),
                        ceid=locale.get("ceid", "US:en"),
                    ))
        except Exception as exc:
            errors.append(f"{company}: {type(exc).__name__}: {exc}")
            continue
        for item in feed_items:
            published = dt.datetime.fromisoformat(item["published"]) if item.get("published") else None
            if published and published < cutoff:
                continue
            title = item["title"]
            source = item.get("source") or ""

            # Optical-material alert is intentionally separate from power semiconductors.
            # Exclude SiC/800V-HVDC-only stories unless they also contain a direct
            # optical-transceiver / InP / GaAs / CPO / 1.6T / 3.2T connection.
            if company in {"AXT", "InP Supply Chain", "GaAs Optical Supply Chain"}:
                power_only = bool(re.search(r"\bSiC\b|silicon carbide|800V|HVDC|power semiconductor", title, re.I))
                optical_link = bool(re.search(r"\bInP\b|indium phosphide|\bGaAs\b|gallium arsenide|砷化鎵|optical|transceiver|CPO|1\.6T|3\.2T|laser|photodiode", title, re.I))
                if power_only and not optical_link:
                    continue

            score = signal_score(title, source)
            # Require both a technology/data-movement term and a concrete commercial/action term.
            # CPO mentions alone are not enough: this prevents stock-reaction/commentary articles
            # from becoming alerts. Only a 3.2T milestone may bypass the action requirement.
            has_high = any(re.search(p, title, re.I) for p in HIGH_SIGNAL_PATTERNS)
            has_action = any(re.search(p, title, re.I) for p in ACTION_PATTERNS)
            very_strong = bool(re.search(r"\b3\.2\s*[Tt]\b", title, re.I))
            if score < 7 or not has_high or (not has_action and not very_strong):
                continue
            key = event_key(company, title, source)
            item.update({
                "company": company,
                "ticker": meta["ticker"],
                "score": score,
                "key": key,
                "stage": stage_for(title),
                "category": category_for(title, company),
            })
            all_relevant.append(item)

    # Source-quality gate: unknown/low-quality sources cannot trigger by themselves.
    # They are admitted only when a higher-quality source independently reports the same event.
    def source_is_corroborated(item: dict) -> bool:
        if source_priority(item.get("source") or "") >= 65:
            return True
        return any(
            other is not item
            and source_priority(other.get("source") or "") >= 65
            and same_underlying_story(item, other)
            for other in all_relevant
        )

    all_relevant = [item for item in all_relevant if source_is_corroborated(item)]

    # Stable order: newest first, then score.
    def sort_key(item: dict):
        published = item.get("published") or "1970-01-01T00:00:00+00:00"
        return (published, item.get("score", 0))

    all_relevant.sort(key=sort_key, reverse=True)

    # Collapse syndicated/mirrored articles about the same underlying event.
    # Prefer the company release or higher-quality reporting instead of counting
    # each headline/source as a separate "new change".
    deduped: list[dict] = []
    for item in all_relevant:
        matched_index = next(
            (idx for idx, existing in enumerate(deduped) if same_underlying_story(item, existing)),
            None,
        )
        if matched_index is None:
            deduped.append(item)
            continue
        if prefer_story_item(item, deduped[matched_index]):
            deduped[matched_index] = item

    initialized = bool(state.get("initialized"))
    dedupe_version = int(state.get("dedupe_version") or 0)
    seen_story_keys = set(state.get("seen_story_keys") or [])
    seen_story_records = list(state.get("seen_story_records") or [])

    for item in deduped:
        item["story_key"] = canonical_story_key(item["company"], item["title"])

    def already_seen(item: dict) -> bool:
        if item["key"] in seen:
            return True
        story_key = item.get("story_key")
        if story_key and story_key in seen_story_keys:
            return True
        for previous in seen_story_records:
            if previous.get("company") != item.get("company"):
                continue
            # Never let a previously-sent low-quality/market-reaction source suppress
            # a later official or high-quality structural event.
            if source_priority(previous.get("source") or "") < 65:
                continue
            try:
                prev_dt = dt.datetime.fromisoformat(previous.get("published") or "")
                item_dt = dt.datetime.fromisoformat(item.get("published") or "")
                if abs((item_dt - prev_dt).total_seconds()) > 7 * 24 * 3600:
                    continue
            except Exception:
                pass
            if same_underlying_story(item, previous):
                return True
        return False

    new_items = [item for item in deduped if not already_seen(item)]

    updated_seen = list(dict.fromkeys([item["key"] for item in deduped] + list(seen)))[:1500]
    updated_story_keys = list(dict.fromkeys(
        [item["story_key"] for item in deduped if item.get("story_key")] + list(seen_story_keys)
    ))[:500]
    new_story_records = [{
        "company": item.get("company"),
        "category": item.get("category"),
        "title": item.get("title"),
        "source": item.get("source"),
        "published": item.get("published"),
    } for item in deduped if source_priority(item.get("source") or "") >= 65]

    # Clean legacy state: remove low-quality reaction sources and collapse
    # syndicated/mirrored records by underlying event, not just exact text.
    merged_story_records = []
    for record in new_story_records + seen_story_records:
        if source_priority(record.get("source") or "") < 65:
            continue
        if any(same_underlying_story(record, existing) for existing in merged_story_records):
            continue
        merged_story_records.append(record)
        if len(merged_story_records) >= 500:
            break

    pending = {
        "initialized": True,
        "dedupe_version": 2,
        "quality_version": 3,
        "photonic_compute_version": 3,
        "optical_material_version": 1,
        "cpo_equipment_version": 2,
        "optical_policy_version": 2,
        "korea_optics_version": 1,
        "last_checked_kst": dt.datetime.now(KST).isoformat(timespec="seconds"),
        "seen_keys": updated_seen,
        "seen_story_keys": updated_story_keys,
        "seen_story_records": merged_story_records,
        "relevant_item_count": len(deduped),
        "source_errors": errors,
    }
    PENDING_PATH.write_text(json.dumps(pending, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    # One-time migration: establish the semantic/event baseline silently so the
    # dedupe upgrade itself cannot resend already reported stories.
    if dedupe_version < 2:
        alert_items = []
    else:
        equipment_version = int(state.get("cpo_equipment_version") or 0)
        if equipment_version < 2:
            new_items = [item for item in new_items if item.get("company") != "CPO Equipment Supply Chain"]
        optical_policy_version = int(state.get("optical_policy_version") or 0)
        if optical_policy_version < 1:
            new_items = [item for item in new_items if item.get("company") not in {"US Optical Policy", "AXT"}]
        if optical_policy_version < 2:
            new_items = [item for item in new_items if item.get("company") != "InP Supply Chain"]
        korea_optics_version = int(state.get("korea_optics_version") or 0)
        if korea_optics_version < 1:
            new_items = [item for item in new_items if item.get("company") not in {"Opticore", "OE Solutions"}]
        photonic_compute_version = int(state.get("photonic_compute_version") or 0)
        if photonic_compute_version < 3:
            new_items = [item for item in new_items if item.get("company") not in {"Volantis", "Lightmatter", "Ayar Labs", "Xscape Photonics"}]
        alert_items = new_items[:8] if initialized else []
    if ALERT_PATH.exists():
        ALERT_PATH.unlink()

    if alert_items:
        policy_only = all(item.get("company") == "US Optical Policy" for item in alert_items)
        korea_optics_only = all(item.get("company") in {"Opticore", "OE Solutions"} for item in alert_items)
        photonic_compute_only = all(item.get("company") in {"Volantis", "Lightmatter", "Ayar Labs", "Xscape Photonics"} for item in alert_items)
        if policy_only:
            alert_header = "🚨 <b>미국 광트랜시버 규제 변화 감지</b>"
        elif korea_optics_only:
            alert_header = "🚨 <b>국내 AI 광통신 수주·검증 변화 감지</b>"
        elif photonic_compute_only:
            alert_header = "🚨 <b>AI 광컴퓨팅·광메모리 구조 변화 감지</b>"
        else:
            alert_header = "🚨 <b>AI 네트워킹·광통신 구조 변화 감지</b>"
        lines = [
            alert_header,
            f"조회시각(KST): {html.escape(dt.datetime.now(KST).strftime('%Y-%m-%d %H:%M:%S'))}",
            f"신규 변화: <b>{len(alert_items)}건</b>",
            "",
        ]
        for idx, item in enumerate(alert_items, 1):
            pub = ""
            if item.get("published"):
                try:
                    pub_dt = dt.datetime.fromisoformat(item["published"]).astimezone(KST)
                    pub = pub_dt.strftime("%Y-%m-%d %H:%M KST")
                except Exception:
                    pub = item["published"]
            category = item["category"]
            lines.extend([
                f"<b>{idx}) {html.escape(DISPLAY_NAMES_KO.get(item['company'], item['company']))} ({html.escape(item['ticker'])}) — {html.escape(category)}</b>",
                f"• 단계: {html.escape(item['stage'])}",
                f"• 원문 제목: {html.escape(item['title'])}",
                f"• 출처·시각: {html.escape(item.get('source') or '미표기')} / {html.escape(pub or '시각 미표기')}",
                f"• 투자 의미: {html.escape(meaning_for(category))}",
                f"• 역풍 확인: {html.escape(risk_for(category))}",
                f"• <a href=\"{html.escape(item['link'], quote=True)}\">원문 링크</a>",
                "",
            ])
        lines.extend([
            "<b>감시 기준</b>",
            "1.6T 대량출하·고객 채택 / 3.2T 고객 인증·양산 / AAOI 800G·1.6T·3.2T 생산능력·고객·출하 / 볼란티스 A-1 고객샘플·2027 인도·실리콘·벤치마크·광메모리 대역폭·용량·토큰속도 / 라이트매터·아야르 랩스·엑스케이프 광인터커넥트 고객검증·생산·배치 / VCSEL 광메모리 공급망·패키징·수율 / FCC 중국산 광트랜시버 최종규칙·3.2T 적용세대·미국산 콘텐츠 65%·75%·예외·시행일 / 상원·의회 국가안보시스템 광트랜시버 법안 범위 / InP 기판 공급부족·수출허가·증설·가격 / 옵티코어 400G·800G 신규 PO·계약금액·검수·납기변경 / 오이솔루션 1.6T ELSFP·EML 샘플·고객검증·양산 PO / 엔비디아 CPO 실제 배치 / 코히런트 포톤링크 고객·장기계약·양산·콘텐츠 가치 / CPO 제조장비 수주·2027년 2분기 가시성·생산능력 증설·가동률·OSAT 검증·광결합 정렬장비 출하 / CPO·NPO 수직통합과 외부 부품 대체 / 특수광섬유·InP 증설 / 칩 간 광연결 2029~2030년 / 삼성전자 SiPh 파운드리 고객 실명·양산 물량 / 광부품·DSP·레이저·리타이머 병목·가격 / 하이퍼스케일러 네트워크 수주·수주잔고 / 코닝 광통신·유리기판 신규 AI 매출 경로",
        ])
        ALERT_PATH.write_text("\n".join(lines).strip() + "\n", encoding="utf-8")

    status_lines = [
        "# AI 네트워킹·광통신 감시 상태",
        "",
        f"- 조회시각(KST): {dt.datetime.now(KST).isoformat(timespec='seconds')}",
        f"- 기준선 초기화 여부: {'예' if initialized else '아니오 — 이번 실행은 기준선만 저장'}",
        f"- 관련 신규 사건 후보: {len(new_items)}건",
        f"- Telegram 발송 사건: {len(alert_items)}건",
        f"- 중복 기사 통합 후 사건 기준선: {len(deduped)}건",
        f"- 중복 제거 방식: 동일 사건 의미 클러스터 + PhotonLink 사건키 v2",
        f"- 소스 오류: {len(errors)}건",
    ]
    if errors:
        status_lines.extend(["", "## 소스 오류"] + [f"- {e}" for e in errors])
    STATUS_PATH.write_text("\n".join(status_lines).strip() + "\n", encoding="utf-8")

    print(f"initialized_before={initialized}")
    print(f"relevant={len(deduped)} new={len(new_items)} alert={len(alert_items)} errors={len(errors)}")


if __name__ == "__main__":
    main()
