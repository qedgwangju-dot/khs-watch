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
            "ASE": ("ase technology", "advanced semiconductor engineering", "aseh", "日月光"),
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
            "DISCO": ("disco corporation", "disco corp", "ディスコ", "디스코"),
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
    "semi", "tsmc", "ase", "sk hynix", "sk하이닉스", "samsung", "samsung electronics",
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
        r"export control", r"export restriction", r"ban", r"restriction",
        r"covered list", r"national security", r"sanction", r"license requirement",
        r"수출.?통제", r"수출.?규제", r"규제", r"금지", r"제재",
    ),
    "disruption": (
        r"earthquake", r"power outage", r"blackout", r"fire", r"halt(?:ed|s)? production",
        r"production halt", r"shutdown", r"disruption", r"停产", r"地震",
        r"지진", r"정전", r"화재", r"생산.?중단", r"가동.?중단",
    ),
    "capacity": (
        r"capacity expansion", r"expand(?:ing|s|ed)? capacity", r"new fab", r"new plant",
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
    r"2nm", r"3nm", r"coWoS", r"advanced packaging", r"3dfabric", r"focos",
    r"hbm4", r"hbm", r"tc bonder", r"optical transceiver", r"800g", r"1\.6t", r"3\.2t",
    r"coater.?developer", r"euv", r"semiconductor tester", r"memory tester", r"dicing", r"grinding",
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


def _load_state() -> dict:
    if not STATE_PATH.exists():
        return {}
    return json.loads(STATE_PATH.read_text(encoding="utf-8"))


def write_outputs(items: list[dict], errors: list[str]) -> None:
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
    if not eligible:
        return

    lines = [
        "<b>[AI 반도체 지역 병목 변화]</b>",
        f"조회 {now.strftime('%Y-%m-%d %H:%M')} KST · 신규 구조 변화 {len(eligible)}건",
        "",
        "한눈에: <b>지역별 독점·과점 구조가 실제 생산능력·규제·가동중단·대체공급에서 바뀔 때만 알림</b>",
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
    write_outputs(items, errors)
    print(f"regional_chokepoint_candidates={len(items)} errors={len(errors)}")
    print(f"alert_exists={ALERT_PATH.exists()}")


if __name__ == "__main__":
    main()
