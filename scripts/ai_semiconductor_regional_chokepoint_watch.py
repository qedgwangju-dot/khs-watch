#!/usr/bin/env python3
"""AI semiconductor regional chokepoint watcher.

Purpose:
- Track structural geographic concentration changes in the AI semiconductor supply chain.
- Taiwan: advanced logic/foundry + advanced packaging.
- Korea: HBM + HBM manufacturing equipment.
- China: AI optical transceivers / interconnect scale and policy risk.
- Japan: semiconductor equipment + critical materials.
- Global: comparable concentration metrics, geographic diversification, export controls,
  and production disruptions.

This watcher is intentionally conservative. It does not alert on ordinary stock moves,
routine earnings, or product announcements unless they change capacity, geography,
regulation, production continuity, or a critical supply-chain share.
"""
from __future__ import annotations

import datetime as dt
import hashlib
import html
import json
import os
import pathlib
import re
import time
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from email.utils import parsedate_to_datetime
from zoneinfo import ZoneInfo

try:
    from googlenewsdecoder import gnewsdecoder
except Exception:  # pragma: no cover
    gnewsdecoder = None

ROOT = pathlib.Path(__file__).resolve().parents[1]
STATE_PATH = ROOT / "data" / "ai_semiconductor_regional_chokepoint_state.json"
OUT_DIR = ROOT / "out"
ALERT_PATH = OUT_DIR / "ai_semiconductor_regional_chokepoint_alert.html"
PENDING_PATH = OUT_DIR / "ai_semiconductor_regional_chokepoint_pending_state.json"
STATUS_PATH = OUT_DIR / "ai_semiconductor_regional_chokepoint_status.md"
KST = ZoneInfo("Asia/Seoul")
BASELINE_VERSION = 1

SEMI_300MM_VERSION = 2
SEMI_300MM_PRESS = ("https://www.semi.org/en/semi-press-release/"
    "global-300mm-fab-equipment-spending-to-reach-227-billion-in-2029-as-buildout-accelerates-semi-projects")
SEMI_300MM_OUTLOOK = "https://www.semi.org/en/products-services/market-data/300mm-fab-outlook"
SEMI_300MM_ISSUER_INDEX = "https://www.prnewswire.com/news/semi/"
SEMI_300MM_DISTRIBUTION = ("https://www.prnewswire.com/news-releases/"
    "global-300mm-fab-equipment-spending-to-reach-227-billion-in-2029-as-buildout-accelerates-semi-projects-302906628.html")
SEMI_300MM_APRIL = ("https://www.semi.org/en/semi-press-release/"
    "semi-projects-double-digit-growth-in-global-300mm-fab-equipment-spending-for-2026-and-2027")


BASELINE = {
    "historical_concentration": {
        "east_asia_china_semiconductor_manufacturing_capacity_pct": 75.0,
        "vintage": "2021",
        "scope": "전체 반도체 제조능력에 대한 SIA·BCG 당시 추정",
        "current_live_metric": False,
        "source": "SIA / BCG",
        "source_url": "https://www.semiconductors.org/strengthening-the-global-semiconductor-supply-chain-in-an-uncertain-era/",
    },
    "taiwan": {
        "role": "선단 로직 파운드리·첨단 패키징",
        "leaders": ["TSMC", "ASE"],
        "notes": [
            "TSMC는 선단 로직 파운드리뿐 아니라 3DFabric/CoWoS 등 첨단 패키징도 핵심",
            "ASE는 대형 OSAT·첨단 패키징/테스트 핵심사",
        ],
    },
    "korea": {
        "role": "HBM·고성능 메모리",
        "leaders": ["SK hynix", "Samsung Electronics"],
        "adjacent_equipment": ["Hanmi Semiconductor"],
        "notes": [
            "Micron은 미국 업체이지만 글로벌 HBM 3대 공급사 중 하나",
            "Hanmi Semiconductor는 HBM 메모리 제조사가 아니라 TC bonder 장비사",
        ],
    },
    "china": {
        "role": "AI 데이터센터 광트랜시버·광인터커넥트 대량생산",
        "leaders": ["Zhongji Innolight", "Eoptolink"],
        "notes": [
            "중국 업체의 모듈 대량생산 강점과 미국 규제·고객 다변화 리스크를 동시에 추적",
        ],
    },
    "japan": {
        "role": "반도체 제조장비·검사·정밀가공·핵심 소재",
        "leaders": ["Tokyo Electron", "Advantest", "DISCO", "Lasertec"],
        "materials": ["Shin-Etsu Chemical", "SUMCO", "JSR", "Tokyo Ohka Kogyo"],
        "notes": [
            "장비뿐 아니라 실리콘 웨이퍼·포토레지스트 등 핵심 소재 집중도도 별도 추적",
        ],
    },
    "current_public_context": {
        "semi_q3_2026": "SEMI Q3 2026 World Fab Forecast 공개 요약상 중국은 2026·2027 설치 생산능력 1위 전망",
        "comparable_75pct_refresh_public": False,
    },
}

REGION_ENTITIES = {
    "taiwan": {
        "label": "대만",
        "function": "선단 로직 파운드리·첨단 패키징",
        "entities": {
            "TSMC": ("tsmc", "台積電", "台积电"),
            "ASE": ("ase ", "ase technology", "advanced semiconductor engineering", "aseh", "日月光"),
        },
    },
    "korea": {
        "label": "한국",
        "function": "HBM·고성능 메모리·HBM 후공정 장비",
        "entities": {
            "SK hynix": ("sk hynix", "sk하이닉스", "하이닉스"),
            "Samsung Electronics": ("samsung electronics", "삼성전자"),
            "Hanmi Semiconductor": ("hanmi semiconductor", "한미반도체"),
        },
    },
    "china": {
        "label": "중국",
        "function": "AI 광트랜시버·광인터커넥트 대량생산",
        "entities": {
            "Zhongji Innolight": ("zhongji innolight", "innolight", "中际旭创", "中際旭創"),
            "Eoptolink": ("eoptolink", "新易盛"),
        },
    },
    "japan": {
        "label": "일본",
        "function": "반도체 제조장비·검사·정밀가공·핵심 소재",
        "entities": {
            "Tokyo Electron": ("tokyo electron", "tel ", "東京エレクトロン", "도쿄일렉트론"),
            "Advantest": ("advantest", "アドバンテスト", "어드밴테스트"),
            "DISCO": ("disco ", "disco corporation", "disco corp", "ディスコ", "디스코"),
            "Lasertec": ("lasertec", "レーザーテック", "레이저텍"),
            "Shin-Etsu Chemical": ("shin-etsu", "shin etsu", "信越化学", "신에츠"),
            "SUMCO": ("sumco", "섬코"),
            "JSR": ("jsr",),
            "Tokyo Ohka Kogyo": ("tokyo ohka", "tok", "東京応化工業", "도쿄오카공업"),
        },
    },
}

QUERIES = [
    ("en", '"semiconductor manufacturing capacity" (East Asia OR China) (SIA OR BCG OR SEMI OR concentration)'),
    ("en", '(TSMC OR ASE) (2nm OR CoWoS OR "advanced packaging" OR capacity OR fab OR outage OR earthquake OR power OR expansion)'),
    ("en", '("SK hynix" OR Samsung OR "Hanmi Semiconductor") (HBM OR HBM4 OR "TC bonder") (capacity OR mass production OR shortage OR allocation OR expansion OR disruption)'),
    ("en", '("Zhongji Innolight" OR Innolight OR Eoptolink) ("optical transceiver" OR 800G OR 1.6T OR 3.2T) (capacity OR restriction OR ban OR FCC OR Congress OR export OR Thailand OR production)'),
    ("en", '("Tokyo Electron" OR Advantest OR DISCO OR Lasertec) semiconductor (capacity OR shortage OR export control OR restriction OR production OR market share OR disruption)'),
    ("en", '("Shin-Etsu" OR SUMCO OR JSR OR "Tokyo Ohka") semiconductor (wafer OR photoresist OR material) (capacity OR shortage OR export control OR production OR market share)'),
    ("en", '"AI semiconductor" supply chain (Taiwan OR Korea OR China OR Japan) (restriction OR outage OR capacity OR diversification OR reshoring OR shortage)'),
    ("ko", '대만 TSMC ASE 반도체 선단공정 첨단패키징 CoWoS 생산능력 증설 정전 지진'),
    ("ko", '한국 SK하이닉스 삼성전자 한미반도체 HBM HBM4 TC본더 생산능력 증설 공급부족'),
    ("ko", '중국 이노라이트 Eoptolink 광트랜시버 800G 1.6T 규제 금지 생산능력'),
    ("ko", '일본 도쿄일렉트론 어드밴테스트 디스코 레이저텍 반도체 장비 생산능력 수출규제 공급부족'),
    ("ko", '일본 신에츠 SUMCO JSR 도쿄오카 반도체 소재 웨이퍼 포토레지스트 공급부족 증설'),
]

OFFICIAL_DOMAINS = {
    "semiconductors.org", "bcg.com", "semi.org",
    "tsmc.com", "aseglobal.com",
    "skhynix.com", "news.skhynix.co.kr", "samsung.com", "news.samsung.com",
    "hanmisemi.com", "zj-innolight.com", "eoptolink.com",
    "tel.com", "advantest.com", "disco.co.jp", "lasertec.co.jp",
    "shinetsu.co.jp", "sumcosi.com", "jsr.co.jp", "tok.co.jp",
    "meti.go.jp", "commerce.gov", "bis.gov", "fcc.gov", "congress.gov", "sec.gov",
}
OFFICIAL_SOURCE_EXACT = {
    "semi", "sia", "bcg", "tsmc", "ase", "sk hynix", "sk하이닉스", "samsung", "samsung electronics",
    "hanmi semiconductor", "zhongji innolight", "eoptolink", "tokyo electron", "advantest",
    "disco", "lasertec", "shin-etsu chemical", "sumco", "jsr", "tokyo ohka kogyo",
    "meti", "fcc", "u.s. congress", "semiconductor industry association",
    "boston consulting group",
}
OFFICIAL_SOURCE_MARKERS = (
    "semiconductor industry association", "boston consulting group",
    "taiwan semiconductor manufacturing", "ase technology holding",
    "ministry of economy, trade and industry", "federal communications commission",
)
TIER1_DOMAINS = {
    "reuters.com", "bloomberg.com", "ft.com", "wsj.com", "nikkei.com", "trendforce.com",
    "cnbc.com", "counterpointresearch.com", "theregister.com",
}
TIER1_SOURCE_MARKERS = (
    "reuters", "bloomberg", "financial times", "wall street journal", "nikkei",
    "trendforce", "cnbc", "counterpoint", "the register",
)

STRUCTURAL_PATTERNS = {
    "regulation": (
        r"export control", r"export restriction", r"\bban\b", r"restriction",
        r"covered list", r"national security", r"sanction", r"license requirement",
        r"수출.?통제", r"수출.?규제", r"규제", r"금지", r"제재",
    ),
    "disruption": (
        r"earthquake", r"power outage", r"blackout", r"\bfire\b", r"halt(?:ed|s)? production",
        r"production halt", r"shutdown", r"disruption", r"停产", r"地震",
        r"지진", r"정전", r"화재", r"생산.?중단", r"가동.?중단",
    ),
    "capacity": (
        r"capacity expansion", r"expand(?:ing|s|ed)? capacity", r"expand(?:ing|s|ed)?[^.]{0,100}?capacity", r"new fab", r"new plant",
        r"mass production", r"volume production", r"production line", r"ramp(?:ing)?",
        r"wafer starts", r"capacity reservation", r"capacity increase",
        r"생산능력", r"증설", r"신규.?팹", r"신공장", r"양산", r"램프",
    ),
    "concentration": (
        r"market share", r"global share", r"capacity share", r"manufacturing capacity",
        r"single point of failure", r"concentration", r"dominant", r"leadership",
        r"점유율", r"집중도", r"제조능력", r"생산능력.?비중", r"지배적",
    ),
    "diversification": (
        r"reshor", r"localiz", r"diversif", r"outside taiwan", r"outside china",
        r"thailand", r"malaysia", r"singapore", r"arizona", r"japan fab", r"overseas plant",
        r"현지화", r"다변화", r"해외.?공장", r"미국.?공장", r"태국.?공장", r"말레이시아",
    ),
}

ROUTINE_NOISE = (
    r"stock rises", r"stock falls", r"shares jump", r"shares fall", r"price target",
    r"analyst rating", r"earnings preview", r"dividend", r"buyback",
    r"주가", r"목표주가", r"배당", r"자사주",
)

CRITICAL_FUNCTION_PATTERNS = (
    r"\b2nm\b", r"\b3nm\b", r"\bcoWoS\b", r"advanced packaging", r"3dfabric", r"focos",
    r"\bhbm4\b", r"\bhbm\b", r"tc bonder", r"optical transceiver", r"\b800g\b", r"\b1\.6t\b", r"\b3\.2t\b",
    r"coater.?developer", r"\beuv\b", r"semiconductor tester", r"memory tester", r"dicing", r"grinding",
    r"mask inspection", r"silicon wafer", r"photoresist",
    r"첨단.?패키징", r"선단", r"에이치비엠", r"광트랜시버", r"테스터", r"웨이퍼", r"포토레지스트",
)


def _clean(value: str | None) -> str:
    text = html.unescape(value or "")
    text = re.sub(r"<[^>]+>", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def _rss_url(lang: str, query: str) -> str:
    if lang == "ko":
        params = {"q": query, "hl": "ko", "gl": "KR", "ceid": "KR:ko"}
    else:
        params = {"q": query, "hl": "en-US", "gl": "US", "ceid": "US:en"}
    return "https://news.google.com/rss/search?" + urllib.parse.urlencode(params)


def _fetch(url: str) -> bytes:
    req = urllib.request.Request(
        url,
        headers={
            "User-Agent": "Mozilla/5.0 (compatible; khs-ai-semiconductor-chokepoint-watch/1.0)",
            "Accept": "application/rss+xml,application/xml,text/xml,text/html,*/*",
        },
    )
    last_error = None
    for attempt in range(3):
        try:
            with urllib.request.urlopen(req, timeout=25) as response:
                return response.read()
        except Exception as exc:
            last_error = exc
            if attempt < 2:
                time.sleep(1.0 + attempt)
    raise last_error


def _decode_google_news_link(link: str) -> str:
    if "news.google.com" not in (link or "") or gnewsdecoder is None:
        return link
    try:
        result = gnewsdecoder(link, interval=0.15)
        if isinstance(result, dict):
            decoded = str(result.get("decoded_url") or "").strip()
            if decoded.startswith("http") and "news.google.com" not in decoded:
                return decoded
    except Exception:
        pass
    return link


def _published_kst(raw: str) -> str:
    try:
        parsed = parsedate_to_datetime(raw)
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=dt.timezone.utc)
        return parsed.astimezone(KST).isoformat(timespec="seconds")
    except Exception:
        return ""


def _normalize_title(value: str) -> str:
    text = _clean(value).lower()
    text = re.sub(r"\s+[-–—|]\s+[^-–—|]{1,80}$", "", text)
    text = re.sub(r"[^0-9a-z가-힣一-龥]+", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def _fingerprint(title: str, source: str) -> str:
    blob = _normalize_title(title) + "|" + _clean(source).lower()
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()[:24]


def _host(link: str) -> str:
    try:
        return urllib.parse.urlparse(link).netloc.lower().split(":")[0]
    except Exception:
        return ""


def _source_level(item: dict) -> str:
    host = _host(str(item.get("link") or ""))
    source = _clean(str(item.get("source") or "")).lower()
    if any(host == d or host.endswith("." + d) for d in OFFICIAL_DOMAINS):
        return "official"
    # When Google News decoding fails, publisher identity still provides a useful
    # official signal, but require a reasonably specific organization marker.
    if source in OFFICIAL_SOURCE_EXACT:
        return "official"
    if any(marker in source for marker in OFFICIAL_SOURCE_MARKERS):
        return "official"
    if any(host == d or host.endswith("." + d) for d in TIER1_DOMAINS):
        return "tier1"
    if any(marker in source for marker in TIER1_SOURCE_MARKERS):
        return "tier1"
    return "other"


def _entities_for_region(region: str, text: str) -> list[str]:
    low = " " + text.lower() + " "
    found = []
    for canonical, aliases in REGION_ENTITIES[region]["entities"].items():
        if any(alias.lower() in low for alias in aliases):
            found.append(canonical)
    return found


def _regions(text: str) -> list[str]:
    low = " " + text.lower() + " "
    found = []
    for region in ("taiwan", "korea", "china", "japan"):
        if _entities_for_region(region, text):
            found.append(region)
    if not found:
        if any(k in low for k in ("east asia", "china and east asia", "semiconductor manufacturing capacity", "single point of failure")):
            found.append("global")
    return found


def _event_type(text: str) -> str | None:
    low = text.lower()
    for event in ("regulation", "disruption", "capacity", "diversification", "concentration"):
        if any(re.search(pat, low, re.I) for pat in STRUCTURAL_PATTERNS[event]):
            return event
    return None


def _critical_function(text: str) -> bool:
    return any(re.search(pat, text, re.I) for pat in CRITICAL_FUNCTION_PATTERNS)


def _is_noise(text: str) -> bool:
    low = text.lower()
    if any(re.search(pat, low, re.I) for pat in ROUTINE_NOISE):
        # Allow if the same text clearly contains a structural event.
        return _event_type(text) is None
    return False


def _event_key(region: str, event_type: str, entities: list[str], text: str) -> str:
    # Keep the key stable across publisher wording while preserving meaningful
    # product generation / geography / regulation differences.
    entity = ",".join(sorted(entities)) if entities else "regional"
    tokens = []
    for pat, label in (
        (r"\b2nm\b", "2nm"), (r"\b3nm\b", "3nm"), (r"\bcowos\b", "cowos"),
        (r"\bhbm4\b", "hbm4"), (r"tc bonder", "tc-bonder"),
        (r"\b800g\b", "800g"), (r"\b1\.6t\b", "1.6t"), (r"\b3\.2t\b", "3.2t"),
        (r"coater.?developer", "coater-developer"), (r"\beuv\b", "euv"),
        (r"photoresist", "photoresist"), (r"silicon wafer", "silicon-wafer"),
        (r"arizona", "arizona"), (r"thailand", "thailand"), (r"malaysia", "malaysia"),
        (r"covered list", "covered-list"), (r"national security", "national-security"),
    ):
        if re.search(pat, text, re.I):
            tokens.append(label)
    suffix = ",".join(tokens[:3]) if tokens else "core"
    return f"{region}|{event_type}|{entity}|{suffix}"


def _numbers(text: str) -> list[str]:
    vals = []
    for m in re.finditer(
        r"(?<!\w)(?:US\$|\$|NT\$|¥)?\s*[0-9]+(?:\.[0-9]+)?\s*(?:%|GW|MW|GWh|WPM|wpm|million|billion|trillion|nm|G|T)?",
        text,
        re.I,
    ):
        v = re.sub(r"\s+", " ", m.group(0)).strip()
        if v and v not in vals:
            vals.append(v)
    return vals[:8]


def _classify(item: dict) -> dict | None:
    text = _clean(f"{item.get('title','')} {item.get('description','')}")
    if not text or _is_noise(text):
        return None
    event = _event_type(text)
    if event is None:
        return None
    regs = _regions(text)
    if not regs:
        return None

    # A company-specific structural event should also touch a relevant critical
    # semiconductor function; global concentration studies are exempt.
    if regs != ["global"] and event in {"capacity", "concentration"} and not _critical_function(text):
        return None

    region = regs[0]
    entities = [] if region == "global" else _entities_for_region(region, text)
    level = _source_level(item)
    key = _event_key(region, event, entities, text)
    return {
        **item,
        "region": region,
        "region_label": "글로벌" if region == "global" else REGION_ENTITIES[region]["label"],
        "function": "반도체 제조능력 지역 집중도" if region == "global" else REGION_ENTITIES[region]["function"],
        "entities": entities,
        "event_type": event,
        "event_key": key,
        "source_level": level,
        "numbers": _numbers(text),
    }


def _event_label(event: str) -> str:
    return {
        "regulation": "규제·수출통제 변화",
        "disruption": "생산 차질·가동중단 위험",
        "capacity": "생산능력·양산 변화",
        "concentration": "점유율·지역 집중도 변화",
        "diversification": "생산거점 다변화·대체공급 변화",
    }.get(event, "구조 변화")


def _meaning(region: str, event: str) -> str:
    base = {
        "global": "지역 집중도가 실제로 완화되는지, 아니면 AI 투자로 특정 지역 병목이 더 강화되는지 확인",
        "taiwan": "선단 로직과 CoWoS·FOCoS·OSAT 패키징 병목이 AI 가속기 출하 일정에 미치는 영향 확인",
        "korea": "HBM 생산능력·수율·TSV·TC bonder 병목이 HBM 공급량과 평균판매단가에 미치는 영향 확인",
        "china": "800G·1.6T·3.2T 광모듈 대량생산 강점과 미국 규제·대체 공급능력 사이의 병목 확인",
        "japan": "EUV 트랙·테스트·정밀가공·마스크검사·웨이퍼·포토레지스트의 공급 차질이 전세계 팹 가동에 미치는 영향 확인",
    }[region]
    if event == "diversification":
        return base + " — 해외 증설이 기존 단일지역 의존도를 실제로 낮추는지가 핵심"
    if event == "disruption":
        return base + " — 생산중단 시간과 고객 재고일수가 실제 출하 차질을 결정"
    if event == "regulation":
        return base + " — 규제 시행일·적용품목·대체 공급사의 인증/생산능력이 핵심"
    return base


def _counter_axis(region: str) -> str:
    return {
        "global": "미국·유럽·동남아의 신규 팹/패키징/부품 생산능력 증가가 집중도를 낮출 수 있음",
        "taiwan": "TSMC 미국·일본 증설, 삼성·Intel 및 대체 패키징 공급 확대",
        "korea": "Micron HBM 증설과 고객 멀티벤더, 하이브리드 본딩 전환",
        "china": "Coherent·Lumentum·AAOI 등 대체 광공급사 증설과 CPO 전환",
        "japan": "미국·유럽·한국·대만의 소재·장비 국산화와 멀티소싱",
    }[region]


def _baseline_context(region: str) -> str:
    if region == "global":
        return "75% 수치는 2021년 SIA·BCG 추정치이며 2026년 실시간 점유율로 사용하지 않음"
    if region == "korea":
        return "한국은 SK hynix·Samsung의 HBM 강점이 핵심이며 Micron도 글로벌 주요 HBM 공급사; Hanmi는 TC bonder 장비사"
    if region == "taiwan":
        return "TSMC 선단 로직 + TSMC/ASE 첨단 패키징을 함께 추적; ASE만 패키징 병목으로 보지 않음"
    if region == "china":
        return "Innolight·Eoptolink의 광모듈 대량생산 강점과 미국 규제 위험을 동시에 추적"
    return "TEL·Advantest·DISCO·Lasertec 장비와 Shin-Etsu·SUMCO·JSR·TOK 소재를 함께 추적"


def _passes_evidence_gate(group: list[dict]) -> tuple[bool, str]:
    if any(x["source_level"] == "official" for x in group):
        return True, "공식자료 확인"
    tiers = [x for x in group if x["source_level"] == "tier1"]
    pubs = {(_clean(str(x.get("source") or "")) or _host(str(x.get("link") or ""))).lower() for x in tiers}
    event = group[0]["event_type"]
    if event == "regulation":
        if len(pubs) >= 2:
            return True, "신뢰자료 2곳 교차확인"
        return False, "규제 이슈는 공식자료 또는 신뢰자료 2곳 필요"
    if len(tiers) >= 1:
        return True, "신뢰자료 확인"
    return False, "출처 신뢰도 부족"


def collect(cutoff: dt.datetime) -> tuple[list[dict], list[str]]:
    items: list[dict] = []
    errors: list[str] = []
    seen = set()
    for lang, query in QUERIES:
        try:
            root = ET.fromstring(_fetch(_rss_url(lang, query)))
        except Exception as exc:
            errors.append(f"{query[:42]}: {type(exc).__name__}: {exc}")
            continue
        for node in root.findall(".//item")[:35]:
            title = _clean(node.findtext("title"))
            description = _clean(node.findtext("description"))
            source = _clean(node.findtext("source"))
            raw_link = _clean(node.findtext("link"))
            link = _decode_google_news_link(raw_link)
            pub = _published_kst(_clean(node.findtext("pubDate")))
            try:
                pub_dt = dt.datetime.fromisoformat(pub) if pub else None
            except Exception:
                pub_dt = None
            if pub_dt and pub_dt < cutoff:
                continue
            fp = _fingerprint(title, source)
            if fp in seen:
                continue
            seen.add(fp)
            item = {
                "title": title,
                "description": description,
                "source": source,
                "link": link,
                "published_kst": pub,
                "fingerprint": fp,
                "query": query,
            }
            classified = _classify(item)
            if classified:
                items.append(classified)
    items.sort(key=lambda x: x.get("published_kst") or "", reverse=True)
    return items, errors




def _semi_300mm_release_urls(index_html: str) -> list[str]:
    """Discover global 300mm equipment releases from SEMI issuer's own index."""
    links = set()
    for m in re.finditer(r'''href=["']([^"']+\.html)["']''', index_html, re.I):
        href = html.unescape(m.group(1)).strip()
        url = urllib.parse.urljoin(SEMI_300MM_ISSUER_INDEX, href)
        parsed = urllib.parse.urlparse(url)
        path = parsed.path.lower()
        if parsed.netloc not in ("www.prnewswire.com", "prnewswire.com"):
            continue
        if all(k in path for k in ("300mm", "fab", "equipment")) and "global" in path and "memory" not in path:
            links.add("https://www.prnewswire.com" + parsed.path)
    def index_num(url):
        m = re.search(r"-(\d{9})\.html$", url)
        return int(m.group(1)) if m else 0
    return sorted(links, key=index_num, reverse=True)


def _semi_number(pattern: str, text: str) -> float | None:
    m = re.search(pattern, text, re.I | re.S)
    return float(m.group(1)) if m else None


def _semi_300mm_parse(press_html: str, outlook_html: str = "") -> dict | None:
    """Only call on SEMI originals; return nothing for invalid or mixed editions."""
    p, o = _clean(press_html), _clean(outlook_html)
    if "global 300mm front-end fab equipment spending" not in p.lower():
        return None
    m = re.search(
        r"global 300mm front-end fab equipment spending.{0,120}?"
        r"(?:US)?\$?\s*(\d+(?:\.\d+)?)\s+billion\s+in\s+(20\d{2})", p, re.I
    )
    target = re.search(
        r"through\s+(20\d{2}).{0,100}?reaching\s+(?:US)?\$?\s*(\d+(?:\.\d+)?)\s+billion",
        p, re.I
    )
    if not m or not target:
        return None
    first_year, first_value = int(m.group(2)), float(m.group(1))
    final_year, final_value = int(target.group(1)), float(target.group(2))
    if first_year > final_year or not 50 <= first_value <= 1000 or not 50 <= final_value <= 1500:
        return None
    date_match = re.search(
        r"\b(January|February|March|April|May|June|July|August|September|October|"
        r"November|December|Jan|Feb|Mar|Apr|Jun|Jul|Aug|Sep|Sept|Oct|Nov|Dec)"
        r"\.?\s+(\d{1,2}),?\s+(20\d{2})\b", p, re.I
    )
    if date_match is None:
        return None
    try:
        release_date = dt.datetime.strptime(
            date_match.group(1).capitalize()[:3] + " " + date_match.group(2) +
            " " + date_match.group(3), "%b %d %Y"
        ).strftime("%Y-%m-%d")
    except ValueError:
        return None
    edition = re.search(r"\b([1-4])Q(\d{2})\s+edition", p, re.I)
    result = {
        "vintage": (edition.group(1) + "Q" + edition.group(2)) if edition else release_date,
        "release_date": release_date,
        "primary_forecast_year": first_year,
        "terminal_forecast_year": final_year,
        f"equipment_{first_year}_usd_b": first_value,
        f"equipment_{final_year}_usd_b": final_value,
        "equipment_2026_yoy_pct": _semi_number(r"up (\d+(?:\.\d+)?)% year.over.year", p),
        "construction_2026_usd_b": _semi_number(
            r"construction spending is projected to rise.{0,80}?to \$?(\d+(?:\.\d+)?) billion in 2026", p),
        "construction_2027_usd_b": _semi_number(
            r"another 33% to \$?(\d+(?:\.\d+)?) billion in 2027", p),
        "construction_2028_usd_b": _semi_number(
            r"before reaching \$?(\d+(?:\.\d+)?) billion in 2028", p),
        "americas_2026_usd_b": _semi_number(
            r"americas.{0,250}?from \$?(\d+(?:\.\d+)?) billion in 2026", p),
        "americas_2029_usd_b": _semi_number(
            r"americas.{0,250}?from \$?\d+(?:\.\d+)? billion in 2026 to \$?(\d+(?:\.\d+)?) billion in 2029", p),
        "source_url": SEMI_300MM_PRESS,
        "source_kind": "SEMI 공식 전망 · 실제 장비수주와 구분",
    }
    starts = re.search(
        r"(\d+) new 300mm fabs or lines to begin construction worldwide in 2026 and (\d+) in 2027", p, re.I)
    operating = re.search(
        r"(\d+) new 300mm fabs or lines worldwide to begin operations or ship first silicon in 2026,"
        r"\s*increasing to (\d+) in 2027", p, re.I)
    if starts:
        result.update(starts_2026=int(starts.group(1)), starts_2027=int(starts.group(2)))
    if operating:
        result.update(first_silicon_2026=int(operating.group(1)),
                      first_silicon_2027=int(operating.group(2)))
    if o:
        edition = re.search(r"current edition:\s*Q([1-4])\s*(20\d{2})", o, re.I)
        if edition and result["vintage"] != (edition.group(1) + "Q" + edition.group(2)[-2:]):
            return None  # Older press release cannot overwrite a newer official edition.
        val_o = _semi_number(
            r"global 300mm front-end fab equipment spending.{0,110}?(?:US)?\$?(\d+(?:\.\d+)?) billion in " + str(first_year), o)
        if val_o is not None and abs(val_o - first_value) > 0.1:
            return None
        result["capacity_growth_2026_pct"] = _semi_number(
            r"total installed 300mm capacity.{0,110}?increase by (\d+(?:\.\d+)?)% in 2026", o)
        result["capacity_growth_2027_29_pct"] = _semi_number(
            r"total installed 300mm capacity.{0,220}?approximately (\d+(?:\.\d+)?)% annually", o)
        result["equipment_2030_decline_pct"] = _semi_number(
            r"extended forecast through 2031.{0,110}?(\d+(?:\.\d+)?)% decline in 2030", o)
        result["memory_equipment_2026_growth_pct"] = _semi_number(
            r"memory equipment spending.{0,110}?grow by (\d+(?:\.\d+)?)% in 2026", o)
    return result


def _semi_300mm_material_changes(old: dict, new: dict) -> list[str]:
    if not new:
        return []
    if not old:
        return ["SEMI 300mm 공식 투자·착공·가동 전망 최초 반영"]
    changes = []
    for key, threshold, label in (
        ("construction_2026_usd_b", 5, "2026년 건설비"),
        ("construction_2027_usd_b", 5, "2027년 건설비"),
        ("starts_2026", 3, "2026년 착공"),
        ("starts_2027", 3, "2027년 착공"),
        ("first_silicon_2026", 3, "2026년 첫 가동"),
        ("first_silicon_2027", 3, "2027년 첫 가동"),
        ("capacity_growth_2026_pct", 1.5, "2026년 설치 생산능력 증가율"),
    ):
        if old.get(key) is None or new.get(key) is None:
            continue
        if abs(float(new[key]) - float(old[key])) >= threshold:
            changes.append(label + ": " + str(old[key]) + " → " + str(new[key]))
    for key, value in new.items():
        m = re.fullmatch(r"equipment_(20\d{2})_usd_b", key)
        if not m or not isinstance(value, (int, float)):
            continue
        if old.get(key) is not None and abs(float(value) - float(old[key])) >= 5:
            changes.append(f"{m.group(1)}년 장비투자 전망: {old[key]}→{value}십억달러")
        elif old.get(key) is None and new.get("release_date", "") > old.get("release_date", ""):
            changes.append(f"{m.group(1)}년 신규 장비투자 전망: {value}십억달러")
    return changes


def _semi_300mm_fetch() -> tuple[dict | None, list[str]]:
    fetched, errors = {}, []
    try:
        fetched["보도자료"] = _fetch(SEMI_300MM_PRESS).decode("utf-8", errors="replace")
        fetched["원천"] = SEMI_300MM_PRESS
    except Exception as exc:
        errors.append("SEMI semi.org 원문 접근 제한: " + type(exc).__name__
                      + " " + str(getattr(exc, "code", "")))
        # SEMI itself published this exact release through PR Newswire.
        # A news article that merely mentions SEMI is not an accepted substitute.
        try:
            raw = _fetch(SEMI_300MM_DISTRIBUTION).decode("utf-8", errors="replace")
            plain = _clean(raw).lower()
            if ("news provided by semi" in plain or "source semi" in plain) and (
                "global 300mm front-end fab equipment spending" in plain
            ):
                fetched["보도자료"] = raw
                fetched["원천"] = SEMI_300MM_DISTRIBUTION
            else:
                errors.append("SEMI 배포본의 발행주체 확인 실패: 알림 보류")
        except Exception as fallback_exc:
            errors.append("SEMI PR Newswire 배포본 열람 실패: " +
                          type(fallback_exc).__name__ + " " +
                          str(getattr(fallback_exc, "code", "")))
    try:
        fetched["상세전망"] = _fetch(SEMI_300MM_OUTLOOK).decode("utf-8", errors="replace")
    except Exception as exc:
        errors.append("SEMI 분기 전망 상세 원문 접근 제한: " + type(exc).__name__
                      + " " + str(getattr(exc, "code", "")))
    if "보도자료" not in fetched:
        return None, errors
    record = _semi_300mm_parse(fetched["보도자료"], fetched.get("상세전망", ""))
    if record is None:
        errors.append("SEMI 공식 배포 판본·수치 일치 미확인: 신규 알림 보류")
        return None, errors
    record["source_url"] = fetched["원천"]
    if fetched["원천"] != SEMI_300MM_PRESS:
        record["source_kind"] = "SEMI 직접 배포 PR Newswire 원문 · semi.org 직접 접근 제한"
    record["outlook_direct_checked"] = "상세전망" in fetched
    return record, errors



def _load_state() -> dict:
    if not STATE_PATH.exists():
        return {}
    return json.loads(STATE_PATH.read_text(encoding="utf-8"))


def write_outputs(items: list[dict], errors: list[str], semi_record: dict | None = None) -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    state = _load_state()
    now = dt.datetime.now(KST)
    cutoff_raw = str(state.get("baseline_cutoff_kst") or "2026-10-05T19:05:00+09:00")
    cutoff = dt.datetime.fromisoformat(cutoff_raw)
    if cutoff.tzinfo is None:
        cutoff = cutoff.replace(tzinfo=KST)

    seen_fps = set(state.get("seen_fingerprints") or [])
    delivered_keys = set(state.get("delivered_event_keys") or [])

    groups: dict[str, list[dict]] = {}
    for item in items:
        groups.setdefault(item["event_key"], []).append(item)

    eligible: list[dict] = []
    held: list[dict] = []
    for key, group in groups.items():
        # Same structural event from multiple publishers is one event.
        group.sort(key=lambda x: x.get("published_kst") or "", reverse=True)
        newest = group[0]
        pubs = []
        for x in group:
            p = _clean(str(x.get("source") or "")) or _host(str(x.get("link") or ""))
            if p and p not in pubs:
                pubs.append(p)
        newest["corroborating_publishers"] = pubs[:4]
        passed, evidence = _passes_evidence_gate(group)
        newest["evidence_status"] = evidence

        try:
            published = dt.datetime.fromisoformat(newest.get("published_kst") or "")
        except Exception:
            published = None
        is_after_baseline = bool(published and published > cutoff)
        is_new_key = key not in delivered_keys
        unseen_group = any(x["fingerprint"] not in seen_fps for x in group)

        if passed and is_after_baseline and is_new_key and unseen_group:
            eligible.append(newest)
        elif not passed and is_after_baseline and unseen_group:
            held.append(newest)


    # SEMI has a distinct numeric key: reworded news or generic event-key dedupe
    # must not suppress a material forecast revision, and a failed send must not
    # advance the delivered baseline.
    semi_previous = dict(state.get("semi_300mm") or {})
    semi_changes = _semi_300mm_material_changes(semi_previous, semi_record or {})
    if semi_previous.get("release_date", "") > (semi_record or {}).get("release_date", ""):
        semi_record, semi_changes = None, []
    semi_due = bool(semi_record and semi_changes)

    # Mark all currently observed stories as seen; do not mark an event delivered
    # unless Telegram actually has something to send.
    for item in items:
        seen_fps.add(item["fingerprint"])

    eligible = eligible[:4]
    pending_delivered = set(delivered_keys)
    pending_delivered.update(x["event_key"] for x in eligible)

    pending = {
        "initialized": True,
        "baseline_version": BASELINE_VERSION,
        "baseline_cutoff_kst": cutoff.isoformat(timespec="seconds"),
        "baseline": BASELINE,
        "updated_at_kst": now.isoformat(timespec="seconds"),
        "last_scan_count": len(items),
        "semi_300mm_track_version": SEMI_300MM_VERSION,
        "semi_300mm": semi_record if semi_due else semi_previous,
        "semi_300mm_last_observed": semi_record or state.get("semi_300mm_last_observed") or {},
        "last_eligible_count": len(eligible),
        "last_held_count": len(held),
        "seen_fingerprints": list(sorted(seen_fps))[-1200:],
        "delivered_event_keys": list(sorted(pending_delivered))[-500:],
        "last_held": [
            {
                "event_key": x["event_key"],
                "source": x.get("source"),
                "reason": x.get("evidence_status"),
                "published_kst": x.get("published_kst"),
            }
            for x in held[:12]
        ],
    }
    for key in ("last_successful_delivery_kst", "telegram_message_ids", "telegram_message_id", "bot_username", "delivery_receipt"):
        if state.get(key) is not None:
            pending[key] = state[key]

    PENDING_PATH.write_text(json.dumps(pending, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    status = [
        "# AI 반도체 지역 집중·병목 감시",
        "",
        f"- 조회시각(KST): {now.isoformat(timespec='seconds')}",
        f"- 구조 후보: {len(items)}건",
        f"- 알림 대상 신규: {len(eligible)}건",
        f"- SEMI 300mm 공식자료 수치확인: {'확인' if semi_record else '미확인'}",
        f"- SEMI 신규 경보: {int(semi_due)}건",
        f"- 추가 검증 대기: {len(held)}건",
        f"- 원천 오류: {len(errors)}건",
        "- 75% 기준: 2021년 SIA·BCG 역사 기준으로만 보존, 2026 실시간 수치로 사용하지 않음",
        "- 기존 Memory/Optics 워처와 중복 방지: 가격·일반 제품뉴스가 아니라 지역 집중·생산능력·규제·가동중단·대체공급 변화만 알림",
    ]
    if held:
        status += ["", "## 검증 대기"]
        for x in held[:6]:
            status.append(f"- {x['region_label']} / {_event_label(x['event_type'])} / {x['evidence_status']} / {x.get('source') or '출처 미표시'}")
    if errors:
        status += ["", "## 오류", *[f"- {x}" for x in errors[:6]]]
    STATUS_PATH.write_text("\n".join(status) + "\n", encoding="utf-8")

    ALERT_PATH.unlink(missing_ok=True)
    if not eligible and not semi_due:
        return

    lines = [
        "<b>[AI 반도체 생산·300mm 설비투자 변화]</b>",
        f"조회 {now.strftime('%Y-%m-%d %H:%M')} KST · 지역 {len(eligible)}건 · SEMI {int(semi_due)}건",
        "",
        "한눈에: <b>지역별 독점·과점 구조가 실제 생산능력·규제·가동중단·대체공급에서 바뀔 때만 알림</b>",
    ]

    if semi_due:
        s = semi_record
        def amount(key):
            v = s.get(key)
            return "$" + f"{float(v):g} billion" if v is not None else "확인 불가"
        lines += [
            "",
            "• <b>SEMI 공식 300mm 전공정 장비투자·공장 시간표</b>",
            "  성격: " + html.escape(s["source_kind"]) + " · 전망치, 확정 발주 아님",
            "  2026년 장비투자: " + amount("equipment_2026_usd_b")
            + " · 전년 대비 +" + str(s.get("equipment_2026_yoy_pct") or "확인 불가") + "%",
            "  2029년 장비투자: " + amount("equipment_2029_usd_b"),
            "  4월 전망 대비 2026년: $133 billion → " + amount("equipment_2026_usd_b"),
            "  4월 전망 대비 2029년: $172 billion → " + amount("equipment_2029_usd_b"),
            "  공장 건설비 2026/2027/2028: " + amount("construction_2026_usd_b")
            + " / " + amount("construction_2027_usd_b") + " / " + amount("construction_2028_usd_b"),
        ]
        for reason in semi_changes:
            lines.append("  신규 변화: " + html.escape(reason))
        if all(s.get(k) is not None for k in (
            "starts_2026", "starts_2027", "first_silicon_2026", "first_silicon_2027"
        )):
            lines.append(
                f"  2026년 착공 {s['starts_2026']}곳·가동/첫 웨이퍼 {s['first_silicon_2026']}곳"
                f" → 2027년 착공 {s['starts_2027']}곳·가동/첫 웨이퍼 {s['first_silicon_2027']}곳"
            )
        if s.get("capacity_growth_2026_pct") is not None:
            lines.append(
                f"  설치 생산능력: 2026년 +{float(s['capacity_growth_2026_pct']):g}%"
                + (f" · 2027~2029년 매년 약 +{float(s['capacity_growth_2027_29_pct']):g}%"
                   if s.get("capacity_growth_2027_29_pct") is not None else "")
            )
        if s.get("equipment_2030_decline_pct") is not None:
            lines.append("  역풍: 2030년 장비투자 감소 전망 -" +
                         f"{float(s['equipment_2030_decline_pct']):g}%")
        lines += [
            "  구분: 건설비와 전공정 장비투자비는 서로 다른 분류, 착공과 가동도 다른 시설 집단",
            "  매출 경로: 실제 장비 발주→납품·검수→장비사 매출→공장 가동→웨이퍼 투입→메모리 공급",
            "  실패·지연 경로: 전력·초순수·허가·장비 납기·공정 수율·고객 승인",
            "  먼저 볼 지표: 업체별 장비 수주잔고·웨이퍼 투입량·DRAM/NAND 계약가",
            '  <a href="' + html.escape(s["source_url"], quote=True) + '">SEMI 2026-10-13 실제 확인한 발표 경로</a>',
            '  <a href="' + html.escape(SEMI_300MM_OUTLOOK, quote=True) + '">SEMI 300mm 분기별 전망</a>',
            '  <a href="' + html.escape(SEMI_300MM_APRIL, quote=True) + '">SEMI 2026-04-01 기존 전망</a>',
        ]

    for idx, item in enumerate(eligible, 1):
        entities = ", ".join(item["entities"]) if item["entities"] else "지역 전체"
        lines += [
            "",
            f"• <b>{idx}. {html.escape(item['region_label'])} · {html.escape(_event_label(item['event_type']))}</b>",
            f"  기능: {html.escape(item['function'])}",
            f"  당사자: {html.escape(entities)}",
            f"  확인: <b>{html.escape(item['evidence_status'])}</b>",
        ]
        if item.get("numbers"):
            lines.append("  감지 숫자: " + html.escape(", ".join(item["numbers"])))
        lines += [
            "  의미: " + html.escape(_meaning(item["region"], item["event_type"])),
            "  반대축: " + html.escape(_counter_axis(item["region"])),
            "  기준: " + html.escape(_baseline_context(item["region"])),
        ]
        pubs = item.get("corroborating_publishers") or []
        if pubs:
            lines.append("  확인 출처: " + html.escape(", ".join(pubs)))
        link = str(item.get("link") or "")
        if link:
            lines.append('  <a href="' + html.escape(link, quote=True) + '">근거 원문</a>')

    lines += [
        "",
        "※ 2021년 SIA·BCG의 ‘중국·동아시아 약 75%’는 역사적 기준입니다. 최신 동일분모 통계가 나오기 전에는 현재 점유율로 재사용하지 않습니다.",
        "※ 한국 지도에서 Hanmi Semiconductor는 HBM 제조사가 아니라 TC bonder 장비사로 분리합니다.",
    ]
    ALERT_PATH.write_text("\n".join(lines).strip() + "\n", encoding="utf-8")


def main() -> None:
    now = dt.datetime.now(KST)
    cutoff = now - dt.timedelta(days=10)
    items, errors = collect(cutoff)
    semi_record, semi_errors = _semi_300mm_fetch()
    print(f"semi_300mm_primary_valid={bool(semi_record)} source_errors={semi_errors[:3]}")
    write_outputs(items, errors + semi_errors, semi_record)
    print(f"regional_chokepoint_candidates={len(items)} errors={len(errors)}")
    print(f"alert_exists={ALERT_PATH.exists()}")


if __name__ == "__main__":
    main()
