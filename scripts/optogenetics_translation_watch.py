from __future__ import annotations

import datetime as dt
import hashlib
import html
import json
import os
import pathlib
import re
import sys
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from html.parser import HTMLParser
from urllib.parse import urljoin
from zoneinfo import ZoneInfo

ROOT = pathlib.Path(__file__).resolve().parents[1]
STATE = ROOT / "data" / "optogenetics_translation_watch_state.json"
PENDING = ROOT / "out" / "optogenetics_translation_watch_pending_state.json"
ALERT = ROOT / "out" / "optogenetics_translation_alert.md"
STATUS = ROOT / "out" / "optogenetics_translation_status.md"

KST = ZoneInfo("Asia/Seoul")
UA = "Mozilla/5.0 (compatible; khs-watch-optogenetics/1.0)"

KI_NOBEL = "https://news.ki.se/the-2026-nobel-prize-in-physiology-or-medicine-to-peter-hegemann-georg-nagel-and-karl-deisseroth"
NANOSCOPE_NEWS = "https://nanostherapeutics.com/nanoscope-press-release/"
RAY_NEWS = "https://raytherapeutics.com/category/press-release/"
RAY_FEED = "https://raytherapeutics.com/feed/"
RAY_GOOGLE_QUERY = '"Ray Therapeutics" (RTx-015 OR RTx-021 OR optogenetic) (FDA OR EMA OR RMAT OR PRIME OR trial OR phase OR dosing OR data OR results OR financing OR partnership)'
GENSIGHT_NEWS = "https://www.gensight-biologics.com/subject/gs030/"
RESTORE_VISION_NEWS = "https://restore-vis.com/en/news/2026/"
AUGELUX_NEWS = "https://www.augeluxtherapeutics.com/en/news/"
MAPLIGHT_RSS = "https://ir.maplightrx.com/rss/news-releases.xml"
MAPLIGHT_TRACK_VERSION = 1
MAPLIGHT_BASELINE_MILESTONES = {
    "maplight|nobel-optogenetics-bridge",
    "maplight|ml007|zephyr-phase2-positive",
    "maplight|ml004|iris-phase2-results",
    "maplight|ml007|adp-fast-track",
    "maplight|financing|pipe-150m",
    "maplight|portfolio|discovery-paused",
}
JRCT_RV001 = "https://jrct.mhlw.go.jp/en-latest-detail/jRCT2033240611"

TRIALS = {
    "NCT06460844": {"company": "Ray Therapeutics", "program": "RTx-015"},
    "NCT07439887": {"company": "Ray Therapeutics", "program": "RTx-021/AURORA"},
    "NCT06162585": {"company": "Nanoscope Therapeutics", "program": "MOGENRY/MCO-010 장기추적"},
    "NCT04945772": {"company": "Nanoscope Therapeutics", "program": "MOGENRY/MCO-010 RESTORE"},
    "NCT05417126": {"company": "Nanoscope Therapeutics", "program": "MOGENRY/MCO-010 STARLIGHT"},
    "NCT03326336": {"company": "GenSight Biologics", "program": "GS030"},
    "NCT04278131": {"company": "Bionic Sight", "program": "BS01"},
    "NCT06292650": {"company": "Augelux Therapeutics", "program": "ZM-02/MOON"},
    "NCT07282457": {"company": "Augelux Therapeutics", "program": "ZM-02/PRISM"},
}

COMPANY_SOURCES = [
    ("Nanoscope Therapeutics", NANOSCOPE_NEWS, ("mogenry", "mco-010", "sonpiretigene", "optogen")),
    ("GenSight Biologics", GENSIGHT_NEWS, ("gs030", "optogen")),
    ("Restore Vision", RESTORE_VISION_NEWS, ("rv-001", "optogen", "chimeric rhodopsin")),
    ("Augelux Therapeutics", AUGELUX_NEWS, ("zm-02", "optogen", "moon", "prism")),
]

ACTION_TERMS = (
    "fda", "bla", "pdufa", "approval", "approved", "acceptance", "accepted", "priority review",
    "complete response", "crl", "rmat", "prime", "pmda", "mhlw", "nda", "sakigake",
    "phase 1", "phase 2", "phase 3", "phase 2/3", "clinical trial", "trial", "dosing", "dosed",
    "patient", "topline", "data", "results", "endpoint", "manufacturing", "commercial",
    "launch", "partnership", "license", "licensing", "financing", "series b", "series c",
    "first patient", "first-in-human", "interim", "52-week", "52 week", "ind clearance", "ind cleared",
    "orphan drug", "grant", "cgmp", "commercial supply", "priority review", "late-stage", "late stage",
    "advisory committee", "adcom", "clinical hold", "hold lifted", "serious adverse event", "sae",
    "fast track", "end-of-phase 2", "end of phase 2", "eop2", "registrational",
    "dose-limiting toxicity", "dlt", "inspection", "pre-approval inspection", "cmc", "validation",
)

RETINAL_TERMS = (
    "retina", "retinal", "retinitis", "vision", "visual", "blind", "stargardt",
    "choroideremia", "macular", "geographic atrophy", "eye", "ophthalm",
)


class LinkParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.links: list[tuple[str, str]] = []
        self._href = ""
        self._text: list[str] = []

    def handle_starttag(self, tag: str, attrs) -> None:
        if tag.lower() == "a":
            self._href = dict(attrs).get("href", "")
            self._text = []

    def handle_data(self, data: str) -> None:
        if self._href:
            self._text.append(data)

    def handle_endtag(self, tag: str) -> None:
        if tag.lower() == "a" and self._href:
            text = " ".join(" ".join(self._text).split())
            if text:
                self.links.append((text, self._href))
            self._href = ""
            self._text = []


def fetch_text(url: str, timeout: int = 25) -> str:
    req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept-Language": "en-US,en;q=0.9"})
    with urllib.request.urlopen(req, timeout=timeout) as response:
        raw = response.read(2_000_000)
        enc = response.headers.get_content_charset() or "utf-8"
    return raw.decode(enc, errors="replace")


def fetch_json(url: str, timeout: int = 25) -> dict:
    req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept": "application/json"})
    with urllib.request.urlopen(req, timeout=timeout) as response:
        return json.loads(response.read().decode("utf-8"))


def clean(value: str) -> str:
    return " ".join(html.unescape(value or "").split())


def key_for(*parts: str) -> str:
    return hashlib.sha256("|".join(parts).encode("utf-8")).hexdigest()[:24]


def load_state() -> dict:
    try:
        return json.loads(STATE.read_text(encoding="utf-8"))
    except Exception:
        return {}


def save_json(path: pathlib.Path, obj: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(obj, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def classify_press(title: str) -> tuple[str, str]:
    low = title.lower()
    if "end-of-phase 2" in low or "end of phase 2" in low or "eop2" in low:
        return "FDA 임상2상 종료 미팅", "FDA와 후기임상 설계·허가 경로를 조율하는 임상2상 종료 미팅 단계 변화"
    if "fast track" in low:
        return "FDA Fast Track", "FDA 신속개발·심사 지원 지정으로 규제 시간표가 구체화"
    if "clinical hold" in low:
        return "임상 보류", "규제기관 임상 보류로 개발 일정·안전성 위험이 확대"
    if "hold lifted" in low:
        return "임상 보류 해제", "규제기관 임상 보류 해제로 임상 재개 가능"
    if "advisory committee" in low or "adcom" in low:
        return "FDA 자문위원회", "FDA 자문위원회 일정·권고가 허가 확률과 심사 시간표를 변경"
    if "serious adverse event" in low or re.search(r"\bsae\b", low) or "dose-limiting toxicity" in low or re.search(r"\bdlt\b", low):
        return "임상 안전성", "중대한 이상반응 또는 용량제한독성 변화"
    if "pre-approval inspection" in low or ("inspection" in low and ("fda" in low or "manufactur" in low)) or re.search(r"\bcmc\b", low):
        return "CMC·제조심사", "허가 전 제조·품질·CMC 심사 또는 실사 단계 변화"
    if ("fda" in low and "bla" in low and ("accept" in low or "file" in low)):
        return "FDA 허가심사", "FDA가 생물의약품 허가신청(BLA)을 접수·심사 단계로 전환"
    if "ind" in low and ("clear" in low or "cleared" in low):
        return "IND 임상허가", "규제기관이 임상시험계획(IND)을 허용해 인간 임상 진입이 가능해짐"
    if "first patient" in low or "first-in-human" in low or "first in human" in low:
        return "첫 환자 투여", "최초 인간 투여 또는 첫 환자 투여로 임상 실행 단계 진입"
    if "pdufa" in low:
        return "FDA 심사기한", "FDA 심사기한(PDUFA) 또는 심사 일정 변화"
    if ("fda" in low and ("approval" in low or "approved" in low)):
        return "FDA 허가", "FDA 판매허가 결정"
    if "complete response" in low or re.search(r"\bcrl\b", low):
        return "FDA 보완요구", "FDA 보완요구서(CRL) 또는 허가 지연"
    if "pmda" in low and "priority" in low:
        return "일본 우선심사", "일본 PMDA 접수·우선심사 단계 변화"
    if "mhlw" in low and ("approval" in low or "approved" in low):
        return "일본 허가", "일본 후생노동성 허가 결정"
    if "rmat" in low:
        return "FDA RMAT", "FDA 재생의료첨단치료제(RMAT) 지정"
    if "prime" in low:
        return "EMA PRIME", "유럽의약품청(EMA) PRIME 지정"
    if re.search(r"phase\s*(?:2/3|3)", low):
        return "후기 임상", "2/3상·3상 진입 또는 임상 결과"
    if re.search(r"phase\s*2", low):
        return "2상 임상", "2상 진입 또는 임상 결과"
    if re.search(r"phase\s*1", low):
        return "1상 임상", "1상 진입·첫 환자 투여 또는 초기 결과"
    if any(x in low for x in ("topline", "endpoint", "results", "data")):
        return "임상 데이터", "유효성·안전성 임상 데이터 공개"
    if any(x in low for x in ("manufacturing", "commercial", "launch", "cgmp", "commercial supply")):
        return "상용화 준비", "제조·cGMP·상용공급·출시 준비 단계 변화"
    if any(x in low for x in ("partnership", "license", "licensing")):
        return "사업협력", "기술이전·라이선스·사업협력 변화"
    if any(x in low for x in ("financing", "series b", "series c", "grant")):
        return "개발자금", "임상·제조·상용화를 위한 신규 자금조달·지원금"
    return "광유전학 임상", "광유전학 임상·규제 단계 변화"


def program_label(company: str, low_title: str) -> str:
    if company == "MapLight Therapeutics":
        if "ml-007c-ma" in low_title or "zephyr" in low_title or "vista" in low_title:
            return "ML-007C-MA · 광유전학 기반 약물발굴(간접)"
        if "ml-004" in low_title or "iris" in low_title:
            return "ML-004 · 광유전학 기반 약물발굴(간접)"
        if "ml-009" in low_title:
            return "ML-009 · 광유전학 기반 회로지도 후속 파이프라인"
        if "ml-055" in low_title:
            return "ML-055 · 광유전학 기반 회로지도 후속 파이프라인"
        if "ml-021" in low_title:
            return "ML-021 · 광유전학 기반 회로지도 후속 파이프라인"
        return "회로지도 기반 약물발굴 · 광유전학 간접 상용화"
    if company == "Ray Therapeutics":
        return "RTx-015/RTx-021"
    if "mogenry" in low_title or "mco-010" in low_title:
        return "MOGENRY/MCO-010"
    if "rtx-015" in low_title or "rtx-021" in low_title:
        return "RTx-015/RTx-021"
    if "gs030" in low_title:
        return "GS030"
    return "광유전학"


def meaningful_rss_links(company: str, feed_url: str, program_terms: tuple[str, ...]) -> list[dict]:
    xml = fetch_text(feed_url)
    root = ET.fromstring(xml)
    out: list[dict] = []
    seen: set[str] = set()
    for item in root.findall(".//item"):
        title = clean(item.findtext("title") or "")
        link = clean(item.findtext("link") or "")
        low = title.lower()
        if not title or not link:
            continue
        if not any(term in low for term in program_terms):
            continue
        if not any(term in low for term in ACTION_TERMS):
            continue
        k = key_for(company, link.rstrip("/"), title.lower())
        if k in seen:
            continue
        seen.add(k)
        stage, meaning = classify_press(title)
        out.append({
            "key": k,
            "company": company,
            "program": program_label(company, low),
            "stage": stage,
            "meaning": meaning,
            "title": title,
            "url": link,
            "source": "회사 공식 RSS",
        })
    return out


def meaningful_google_official_links(company: str, query: str, official_domain: str, program_terms: tuple[str, ...]) -> list[dict]:
    url = "https://news.google.com/rss/search?" + urllib.parse.urlencode({
        "q": query,
        "hl": "en-US",
        "gl": "US",
        "ceid": "US:en",
    })
    root = ET.fromstring(fetch_text(url))
    out: list[dict] = []
    seen: set[str] = set()
    for item in root.findall("./channel/item")[:30]:
        title = clean(item.findtext("title") or "")
        link = clean(item.findtext("link") or "")
        src = item.find("source")
        source_name = clean(src.text if src is not None and src.text else "")
        source_url = clean(src.attrib.get("url", "") if src is not None else "")
        low = title.lower()
        if official_domain not in source_url.lower() and company.lower() not in source_name.lower():
            continue
        if not any(term in low for term in program_terms):
            continue
        if not any(term in low for term in ACTION_TERMS):
            continue
        k = key_for(company, title.lower(), "official-index")
        if k in seen:
            continue
        seen.add(k)
        stage, meaning = classify_press(title)
        out.append({
            "key": k,
            "company": company,
            "program": "RTx-015/RTx-021",
            "stage": stage,
            "meaning": meaning,
            "title": title,
            "url": link,
            "source": "Ray Therapeutics 공식 도메인 색인",
        })
    return out


def meaningful_press_links(company: str, base_url: str, program_terms: tuple[str, ...]) -> list[dict]:
    page = fetch_text(base_url)
    parser = LinkParser()
    parser.feed(page)
    out: list[dict] = []
    seen: set[str] = set()
    for text, href in parser.links:
        title = clean(text)
        low = title.lower()
        if len(title) < 18:
            continue
        if not any(term in low for term in program_terms):
            continue
        if not any(term in low for term in ACTION_TERMS):
            continue
        url = urljoin(base_url, href)
        if not url.startswith(("http://", "https://")):
            continue
        k = key_for(company, url.rstrip("/"), title.lower())
        if k in seen:
            continue
        seen.add(k)
        stage, meaning = classify_press(title)
        out.append({
            "key": k,
            "company": company,
            "program": program_label(company, low),
            "stage": stage,
            "meaning": meaning,
            "title": title,
            "url": url,
            "source": "회사 공식자료",
        })
    return out


def trial_snapshot(nct: str) -> tuple[dict, dict]:
    data = fetch_json(f"https://clinicaltrials.gov/api/v2/studies/{nct}")
    p = data.get("protocolSection") or {}
    ident = p.get("identificationModule") or {}
    status = p.get("statusModule") or {}
    design = p.get("designModule") or {}
    contacts = p.get("contactsLocationsModule") or {}
    conds = (p.get("conditionsModule") or {}).get("conditions") or []
    phases = design.get("phases") or []
    enrollment = (design.get("enrollmentInfo") or {}).get("count")
    snap = {
        "brief_title": clean(ident.get("briefTitle") or ""),
        "overall_status": status.get("overallStatus") or "",
        "phases": phases,
        "enrollment": enrollment,
        "start_date": (status.get("startDateStruct") or {}).get("date") or "",
        "primary_completion": (status.get("primaryCompletionDateStruct") or {}).get("date") or "",
        "study_completion": (status.get("completionDateStruct") or {}).get("date") or "",
        "last_update": (status.get("lastUpdatePostDateStruct") or {}).get("date") or "",
        "conditions": conds,
        "locations": len(contacts.get("locations") or []),
    }
    return data, snap


def trial_changes(old: dict, new: dict) -> list[str]:
    labels = {
        "overall_status": "모집·진행상태",
        "phases": "임상 단계",
        "enrollment": "등록 환자수",
        "primary_completion": "1차 완료 예정",
        "study_completion": "전체 완료 예정",
        "locations": "임상기관 수",
    }
    changes = []
    for key, label in labels.items():
        if key not in old:
            continue
        if old.get(key) != new.get(key):
            changes.append(f"{label}: {old.get(key)} → {new.get(key)}")
    return changes


def rv001_registry_snapshot() -> dict:
    text = clean(re.sub(r"<[^>]+>", " ", fetch_text(JRCT_RV001)))
    low = text.lower()
    status = ""
    for candidate in ("Recruiting", "Active, not recruiting", "Completed", "Suspended", "Terminated", "Withdrawn"):
        if candidate.lower() in low:
            status = candidate
            break
    sample = None
    m = re.search(r"Target sample size\s*([0-9,]+)", text, re.I)
    if m:
        sample = int(m.group(1).replace(",", ""))
    modified = ""
    m = re.search(r"Last modified on\s*([A-Za-z]+\.?\s*[0-9]{1,2},?\s*[0-9]{4})", text, re.I)
    if m:
        modified = clean(m.group(1))
    return {
        "trial_id": "jRCT2033240611",
        "company": "Restore Vision",
        "program": "RV-001",
        "status": status,
        "target_sample_size": sample,
        "last_modified": modified,
    }


def registry_changes(old: dict, new: dict) -> list[str]:
    labels = {
        "status": "모집·진행상태",
        "target_sample_size": "목표 환자수",
        "last_modified": "등록정보 수정일",
    }
    changes = []
    for key, label in labels.items():
        if key in old and old.get(key) != new.get(key):
            changes.append(f"{label}: {old.get(key)} → {new.get(key)}")
    return changes


def discover_nonretinal_trials() -> list[dict]:
    url = "https://clinicaltrials.gov/api/v2/studies?" + urllib.parse.urlencode({
        "format": "json",
        "pageSize": 100,
        "query.term": "optogenetic OR optogenetics",
    })
    data = fetch_json(url)
    out = []
    for row in data.get("studies") or []:
        p = row.get("protocolSection") or {}
        ident = p.get("identificationModule") or {}
        design = p.get("designModule") or {}
        status = p.get("statusModule") or {}
        conds = (p.get("conditionsModule") or {}).get("conditions") or []
        title = clean(ident.get("briefTitle") or "")
        nct = ident.get("nctId") or ""
        study_type = design.get("studyType") or p.get("designModule", {}).get("studyType") or ""
        blob = " ".join([title] + [str(x) for x in conds]).lower()
        if not nct or "optogen" not in json.dumps(row).lower():
            continue
        if all(term not in blob for term in ("brain", "neuro", "parkinson", "epilep", "psychi", "spinal", "motor cortex", "cns")):
            continue
        if any(term in blob for term in RETINAL_TERMS) and not any(term in blob for term in ("brain", "parkinson", "epilep", "spinal", "motor cortex")):
            continue
        out.append({
            "nct": nct,
            "title": title,
            "conditions": conds,
            "status": status.get("overallStatus") or "",
            "phases": design.get("phases") or [],
            "study_type": study_type,
        })
    return out


def discover_maplight_trials() -> list[dict]:
    url = "https://clinicaltrials.gov/api/v2/studies?" + urllib.parse.urlencode({
        "format": "json",
        "pageSize": 100,
        "query.term": '"MapLight Therapeutics"',
    })
    data = fetch_json(url)
    out: list[dict] = []
    for row in data.get("studies") or []:
        p = row.get("protocolSection") or {}
        sponsor = ((p.get("sponsorCollaboratorsModule") or {}).get("leadSponsor") or {}).get("name") or ""
        if "maplight therapeutics" not in sponsor.lower():
            continue
        blob = json.dumps(row, ensure_ascii=False).lower()
        if "ml-007c-ma" in blob:
            program = "ML-007C-MA"
        elif "ml-004" in blob:
            program = "ML-004"
        elif "ml-009" in blob:
            program = "ML-009"
        elif "ml-055" in blob:
            program = "ML-055"
        elif "ml-021" in blob:
            program = "ML-021"
        else:
            continue
        ident = p.get("identificationModule") or {}
        status = p.get("statusModule") or {}
        design = p.get("designModule") or {}
        contacts = p.get("contactsLocationsModule") or {}
        conds = (p.get("conditionsModule") or {}).get("conditions") or []
        nct = ident.get("nctId") or ""
        if not nct:
            continue
        snapshot = {
            "brief_title": clean(ident.get("briefTitle") or ""),
            "overall_status": status.get("overallStatus") or "",
            "phases": design.get("phases") or [],
            "enrollment": (design.get("enrollmentInfo") or {}).get("count"),
            "start_date": (status.get("startDateStruct") or {}).get("date") or "",
            "primary_completion": (status.get("primaryCompletionDateStruct") or {}).get("date") or "",
            "study_completion": (status.get("completionDateStruct") or {}).get("date") or "",
            "last_update": (status.get("lastUpdatePostDateStruct") or {}).get("date") or "",
            "conditions": conds,
            "locations": len(contacts.get("locations") or []),
        }
        out.append({
            "nct": nct,
            "program": program,
            "title": snapshot["brief_title"],
            "snapshot": snapshot,
        })
    return out


def validate_nobel() -> bool:
    text = clean(re.sub(r"<[^>]+>", " ", fetch_text(KI_NOBEL))).lower()
    required = ("2026", "peter hegemann", "georg nagel", "karl deisseroth", "optogenetics", "channelrhodopsin")
    return all(x in text for x in required)


def maplight_milestone_keys(title: str, body: str) -> list[str]:
    text = clean(f"{title} {body}").lower()
    keys: list[str] = []

    def add(key: str) -> None:
        if key not in keys:
            keys.append(key)

    if "nobel prize" in title.lower() and "optogen" in text:
        add("maplight|nobel-optogenetics-bridge")

    if "ml-007c-ma" in text or "zephyr" in text or "vista" in text:
        if "zephyr" in text and re.search(r"positive.{0,80}(topline|results)|met (?:its )?primary endpoint", text, re.I):
            add("maplight|ml007|zephyr-phase2-positive")
        if "vista" in text and "fast track" in text and re.search(r"received|granted|designation", text, re.I):
            add("maplight|ml007|adp-fast-track")
        if re.search(r"end[- ]of[- ]phase\s*2|\beop2\b", text, re.I) and re.search(
            r"completed|held|met with|meeting (?:was )?(?:completed|held)|agreement with (?:the )?fda|feedback from (?:the )?fda",
            text,
            re.I,
        ):
            add("maplight|ml007|fda-eop2-completed")
        if "zephyr-2" in text and re.search(
            r"initiated|began|started|first patient|first participant|first subject|dosed|enrollment (?:has )?begun|recruiting",
            text,
            re.I,
        ):
            add("maplight|ml007|zephyr2-started")
        if "zephyr-2" in text and re.search(r"topline|primary endpoint|results?", text, re.I):
            add("maplight|ml007|zephyr2-results")
        if "vista" in text and re.search(r"enrollment (?:is )?complete|completed enrollment|fully enrolled", text, re.I):
            add("maplight|ml007|vista-enrollment-complete")
        if "vista" in text and re.search(r"topline|primary endpoint|results?", text, re.I):
            add("maplight|ml007|vista-results")
        if re.search(r"new drug application|\bnda\b", text, re.I) and re.search(r"submit|submission|filed|accepted|review", text, re.I):
            add("maplight|ml007|nda")

    if "ml-004" in text or "iris" in text:
        if "iris" in text and re.search(r"did not meet.{0,80}primary endpoint|topline results", text, re.I):
            add("maplight|ml004|iris-phase2-results")
        if re.search(r"end[- ]of[- ]phase\s*2|\beop2\b", text, re.I) and re.search(
            r"completed|held|met with|meeting (?:was )?(?:completed|held)|agreement with (?:the )?fda|feedback from (?:the )?fda",
            text,
            re.I,
        ):
            add("maplight|ml004|fda-eop2-completed")
        if re.search(r"phase\s*3|registrational", text, re.I) and re.search(
            r"initiated|began|started|first patient|first participant|first subject|dosed|enrollment (?:has )?begun",
            text,
            re.I,
        ):
            add("maplight|ml004|phase3-started")
        if re.search(r"partnership|collaboration|license|licensing|strategic (?:collaboration|partner)", text, re.I):
            add("maplight|ml004|partnering")

    if re.search(r"clinical hold|hold placed|suspend(?:ed)?|terminate(?:d)?|discontinue(?:d)?", text, re.I):
        program = "ml007" if ("ml-007c-ma" in text or "zephyr" in text or "vista" in text) else "ml004" if ("ml-004" in text or "iris" in text) else "pipeline"
        add(f"maplight|{program}|hold-stop")

    if re.search(r"\$150\s*million|150\s*million", text, re.I) and re.search(r"private placement|pipe|financing", text, re.I):
        add("maplight|financing|pipe-150m")
    if re.search(r"paus(?:e|ed|ing).{0,80}(preclinical|discovery)|foregoing advancement", text, re.I):
        add("maplight|portfolio|discovery-paused")
    if re.search(r"resum(?:e|ed|ing)|restart(?:ed|ing)?", text, re.I) and re.search(r"preclinical|discovery|ml-009|ml-055|ml-021", text, re.I):
        add("maplight|portfolio|discovery-resumed")

    if not keys and re.search(r"ml-007c-ma|ml-004|ml-009|ml-055|ml-021|zephyr|vista|iris", title, re.I):
        if any(term in text for term in ACTION_TERMS):
            add("maplight|program-release|" + key_for(title.lower())[:16])
    return keys


def maplight_stage_and_meaning(keys: list[str], title: str) -> tuple[str, str]:
    joined = " ".join(keys)
    if "fda-eop2-completed" in joined:
        return "FDA EOP2 완료", "FDA와 후기임상·허가 경로가 실제로 조율된 단계 변화"
    if "zephyr2-started" in joined or "phase3-started" in joined:
        return "3상 실행", "계획이 아니라 등록 임상 실행 단계로 전환"
    if "zephyr2-results" in joined or "vista-results" in joined:
        return "핵심 임상 결과", "후기 임상 유효성·안전성 결과가 기업가치와 허가 확률을 직접 변경"
    if "vista-enrollment-complete" in joined:
        return "임상 모집 완료", "VISTA 데이터 판독 시간표의 불확실성이 낮아짐"
    if "|nda" in joined:
        return "NDA 허가경로", "신약허가신청 제출·접수 단계로 상용화 시간표가 전진"
    if "hold-stop" in joined:
        return "개발 중단·보류", "임상 또는 파이프라인 일정이 후퇴하는 핵심 실패 신호"
    if "partnering" in joined:
        return "사업협력", "ML-004의 자체개발 외 자금·파트너 경로가 구체화"
    if "discovery-resumed" in joined:
        return "후속 파이프라인 재개", "중단했던 회로기반 초기 파이프라인의 투자 재개"
    return classify_press(title)


def validate_maplight_bridge_and_events() -> tuple[bool, list[dict]]:
    # MapLight's IR HTML pages can intermittently time out from GitHub-hosted runners.
    # Use the company's own Q4-hosted RSS feed as the primary machine-readable official source.
    xml = fetch_text(MAPLIGHT_RSS, timeout=35)
    low = clean(re.sub(r"<[^>]+>", " ", xml)).lower()
    bridge_required = ("maplight", "karl deisseroth", "optogenetics", "circuit")
    pipeline_ok = "ml-007c-ma" in low and any(x in low for x in ("zephyr", "vista", "schizophrenia"))
    bridge_ok = all(x in low for x in bridge_required) and pipeline_ok

    root = ET.fromstring(xml)
    out: list[dict] = []
    seen: set[str] = set()
    terms = ("ml-007c-ma", "ml-004", "ml-009", "ml-055", "ml-021", "zephyr", "iris", "vista")
    for item in root.findall(".//item"):
        title = clean(item.findtext("title") or "")
        link = clean(item.findtext("link") or "")
        description = clean(re.sub(r"<[^>]+>", " ", item.findtext("description") or ""))
        content_parts = []
        for child in list(item):
            if child.tag.endswith("encoded") and child.text:
                content_parts.append(clean(re.sub(r"<[^>]+>", " ", child.text)))
        body = clean(" ".join([description] + content_parts))
        combined = f"{title} {body}".lower()
        if not title or not link:
            continue
        if not any(term in combined for term in terms):
            continue
        milestone_keys = maplight_milestone_keys(title, body)
        if not milestone_keys:
            continue
        if "nobel prize" in title.lower():
            milestone_keys = [k for k in milestone_keys if k != "maplight|nobel-optogenetics-bridge"]
            if not milestone_keys:
                continue
        event_identity = "|".join(sorted(milestone_keys))
        k = key_for("MapLight Therapeutics", event_identity)
        if k in seen:
            continue
        seen.add(k)
        stage, meaning = maplight_stage_and_meaning(milestone_keys, title)
        out.append({
            "key": k,
            "milestone_keys": milestone_keys,
            "company": "MapLight Therapeutics",
            "program": program_label("MapLight Therapeutics", combined),
            "stage": stage,
            "meaning": meaning,
            "title": title,
            "url": link,
            "source": "MapLight Therapeutics 공식 RSS",
        })
    return bridge_ok, out


def render_alert(
    items: list[dict],
    trial_updates: list[dict],
    registry_updates: list[dict],
    maplight_press_updates: list[dict],
    maplight_updates: list[dict],
    new_maplight_trials: list[dict],
    new_cns_trials: list[dict],
    now: dt.datetime,
) -> str:
    non_maplight_count = len(items) + len(trial_updates) + len(registry_updates) + len(new_cns_trials)
    maplight_count = len(maplight_press_updates) + len(maplight_updates) + len(new_maplight_trials)
    header = (
        "[바이오 감시] MapLight(MPLT) 광유전학 기반 약물발굴 전환"
        if maplight_count and not non_maplight_count
        else "[바이오 감시] 광유전학 임상·허가 구조 변화"
    )
    lines = [
        header,
        f"조회 시각: {now.strftime('%Y-%m-%d %H:%M')} 한국시간",
        "",
        "판정 원칙: 노벨상·논문·행사 자체는 재알림하지 않고, 인간 임상·허가·환자투여·유효성·제조·상용화 단계가 실제로 바뀔 때만 알립니다.",
    ]
    idx = 1
    for item in items:
        lines += [
            "",
            f"{idx}. {item['company']} · {item['program']}",
            f"- 단계: {item['stage']}",
            f"- 변화: {item['meaning']}",
            "- 확인 수준: 회사 공식자료",
            f"- 원문: {item['url']}",
        ]
        idx += 1
    for item in trial_updates:
        meta = TRIALS[item["nct"]]
        lines += [
            "",
            f"{idx}. {meta['company']} · {meta['program']} · {item['nct']}",
            "- 단계: ClinicalTrials.gov 공식 임상등록 변경",
            f"- 변화: {' / '.join(item['changes'])}",
            "- 확인 수준: 미국 국립의학도서관 ClinicalTrials.gov 공식 등록",
            f"- 원문: https://clinicaltrials.gov/study/{item['nct']}",
        ]
        idx += 1
    for item in registry_updates:
        lines += [
            "",
            f"{idx}. Restore Vision · RV-001 · {item['trial_id']}",
            "- 단계: 일본 jRCT 공식 임상등록 변경",
            f"- 변화: {' / '.join(item['changes'])}",
            "- 확인 수준: 일본 임상연구등제출·공개시스템(jRCT) 공식 등록",
            f"- 원문: {JRCT_RV001}",
        ]
        idx += 1
    if maplight_press_updates or maplight_updates or new_maplight_trials:
        lines += [
            "",
            "[MapLight(MPLT) 전용 추적]",
            "- 구분: 직접 광치료가 아니라 optogenetics·회로지도 → 표적 발굴 → 경구 CNS 약물 임상의 간접 상용화",
        ]
    for item in maplight_press_updates:
        lines += [
            "",
            f"{idx}. MapLight Therapeutics · {item['program']}",
            f"- 단계: {item['stage']}",
            f"- 변화: {item['meaning']}",
            "- 확인 수준: MapLight 공식 IR RSS",
            f"- 원문: {item['url']}",
        ]
        idx += 1
    for item in maplight_updates:
        lines += [
            "",
            f"{idx}. MapLight Therapeutics · {item['program']} · {item['nct']}",
            "- 단계: 광유전학 기반 회로지도 → 경구 CNS 약물의 간접 상용화",
            f"- 변화: {' / '.join(item['changes'])}",
            "- 확인 수준: ClinicalTrials.gov 공식 등록",
            "- 구분: 직접 광치료가 아니라 광유전학으로 찾은 회로·표적을 약물로 번역하는 간접 사업",
            f"- 원문: https://clinicaltrials.gov/study/{item['nct']}",
        ]
        idx += 1
    for item in new_maplight_trials:
        lines += [
            "",
            f"{idx}. MapLight Therapeutics · {item['program']} · {item['nct']}",
            "- 단계: 신규 인간 임상 등록",
            f"- 변화: 광유전학 기반 회로지도에서 도출된 약물 후보의 신규 임상 등록 · 상태 {item['snapshot']['overall_status']} · 임상단계 {item['snapshot']['phases']}",
            "- 확인 수준: ClinicalTrials.gov 공식 등록",
            "- 구분: 직접 광치료가 아니라 광유전학 기반 약물발굴의 간접 상용화",
            f"- 원문: https://clinicaltrials.gov/study/{item['nct']}",
        ]
        idx += 1
    for item in new_cns_trials:
        lines += [
            "",
            f"{idx}. 비망막 중추신경계 광유전학 인간 임상 신규 등록 · {item['nct']}",
            "- 단계: BCI·신경조절 임상 전환 감시",
            f"- 변화: 신규 인간 대상 임상 등록 · 상태 {item['status']} · 임상단계 {item['phases']}",
            f"- 적응증: {', '.join(item['conditions'][:4])}",
            "- 확인 수준: ClinicalTrials.gov 공식 등록",
            f"- 원문: https://clinicaltrials.gov/study/{item['nct']}",
        ]
        idx += 1
    lines += [
        "",
        "투자 해석",
        "- 망막 광유전학: MOGENRY 허가결정·RTx-015 후기임상 전환이 가장 가까운 상용화 검증 신호입니다.",
        "- 뇌·BCI: 아직 인간 치료의 중심은 전기식 BCI·DBS이며, 일반 BCI 뉴스를 광유전학 수혜로 묶지 않습니다. 비망막 인간 광유전학 임상 등록·IND·첫 환자투여가 생길 때만 별도 핵심 알림으로 올립니다.",
        "- 시각복원: MOGENRY·RTx-015/021·GS030·BS01·ZM-02·RV-001은 opsin·표적세포·보조광학장치 의존성이 서로 달라 한 묶음으로 보지 않습니다.",
        "- MapLight(MPLT): 별도 하위 감시로 분리합니다. FDA EOP2 실제 완료, 3상 등록·첫 환자, VISTA·ZEPHYR-2 결과, ML-004 후기개발·파트너링, 개발중단·재개만 핵심 알림으로 올리고 노벨상 재탕·행사·단순 계획 반복은 제외합니다.",
        "- 연구장비: Bruker/Inscopix·레이저·광섬유 같은 연구도구는 직접 임상·상용화 매출과 분리하며, 단순 노벨상 테마 뉴스에는 알림하지 않습니다.",
    ]
    return "\n".join(lines).strip() + "\n"


def self_test() -> None:
    stage, _ = classify_press("Nanoscope FDA Acceptance of BLA for MOGENRY")
    assert stage == "FDA 허가심사"
    stage, _ = classify_press("Ray Therapeutics Receives FDA RMAT Designation for RTx-015")
    assert stage == "FDA RMAT"
    stage, _ = classify_press("MOGENRY PDUFA Date Announced")
    assert stage == "FDA 심사기한"
    stage, _ = classify_press("MapLight ML-007C-MA End-of-Phase 2 Meeting with FDA")
    assert stage == "FDA 임상2상 종료 미팅"
    stage, _ = classify_press("MapLight Therapeutics Receives Fast Track Designation for ML-007C-MA")
    assert stage == "FDA Fast Track"
    assert program_label("MapLight Therapeutics", "positive zephyr results for ml-007c-ma").startswith("ML-007C-MA")
    planned = "MapLight plans to engage with FDA at an End-of-Phase 2 meeting for ML-007C-MA"
    completed = "MapLight completed its End-of-Phase 2 meeting with FDA for ML-007C-MA"
    assert "maplight|ml007|fda-eop2-completed" not in maplight_milestone_keys(planned, "")
    assert "maplight|ml007|fda-eop2-completed" in maplight_milestone_keys(completed, "")
    phase3 = "MapLight initiates ZEPHYR-2 Phase 3 and doses first patient with ML-007C-MA"
    assert "maplight|ml007|zephyr2-started" in maplight_milestone_keys(phase3, "")
    nobel_only = "MapLight celebrates Nobel Prize for optogenetics"
    assert maplight_milestone_keys(nobel_only, "") == ["maplight|nobel-optogenetics-bridge"]
    assert not any(x in "2026 nobel prize for optogenetics".lower() for x in ("pdufa", "approval", "phase 3"))


def main() -> int:
    self_test()
    ROOT.joinpath("out").mkdir(exist_ok=True)
    ROOT.joinpath("data").mkdir(exist_ok=True)
    ALERT.unlink(missing_ok=True)
    PENDING.unlink(missing_ok=True)

    old = load_state()
    initialized = bool(old.get("initialized"))
    old_seen = set(old.get("seen_event_keys") or [])
    old_trials = old.get("trial_snapshots") or {}
    old_rv001 = old.get("rv001_registry_snapshot") or {}
    old_maplight = old.get("maplight_trial_snapshots") or {}
    old_maplight_milestones = set(old.get("maplight_seen_milestone_keys") or []) | set(MAPLIGHT_BASELINE_MILESTONES)
    old_maplight_version = int(old.get("maplight_track_version") or 0)
    old_cns = set(old.get("cns_trial_ids") or [])

    errors: list[str] = []
    successful = 0
    events: list[dict] = []

    nobel_ok = False
    try:
        nobel_ok = validate_nobel()
        successful += 1
        if not nobel_ok:
            errors.append("Karolinska Institutet 노벨상 공식문구 검증 실패")
    except Exception as exc:
        errors.append(f"Karolinska Institutet: {type(exc).__name__}")

    maplight_bridge_ok = False
    maplight_rss_ok = False
    maplight_events: list[dict] = []
    maplight_errors: list[str] = []
    try:
        maplight_bridge_ok, maplight_events = validate_maplight_bridge_and_events()
        maplight_rss_ok = True
        if not maplight_bridge_ok:
            maplight_errors.append("MapLight 광유전학→회로지도→약물발굴 공식 연결 검증 실패")
    except Exception as exc:
        maplight_errors.append(f"MapLight 공식 RSS: {type(exc).__name__}")

    for company, url, terms in COMPANY_SOURCES:
        try:
            events.extend(meaningful_press_links(company, url, terms))
            successful += 1
        except Exception as exc:
            errors.append(f"{company}: {type(exc).__name__}")

    ray_official_index_ok = False
    try:
        ray_rows = meaningful_google_official_links(
            "Ray Therapeutics",
            RAY_GOOGLE_QUERY,
            "raytherapeutics.com",
            ("rtx-015", "rtx-021", "optogen"),
        )
        events.extend(ray_rows)
        ray_official_index_ok = True
        successful += 1
    except Exception as exc:
        errors.append(f"Ray Therapeutics 공식도메인 색인: {type(exc).__name__}")

    snapshots: dict[str, dict] = {}
    trial_updates: list[dict] = []
    for nct in TRIALS:
        try:
            _, snap = trial_snapshot(nct)
            snapshots[nct] = snap
            successful += 1
            if initialized and nct in old_trials:
                changes = trial_changes(old_trials[nct], snap)
                if changes:
                    trial_updates.append({"nct": nct, "changes": changes})
        except Exception as exc:
            errors.append(f"{nct}: {type(exc).__name__}")

    rv001_snapshot: dict = {}
    rv001_updates: list[dict] = []
    try:
        rv001_snapshot = rv001_registry_snapshot()
        successful += 1
        if initialized and old_rv001:
            changes = registry_changes(old_rv001, rv001_snapshot)
            if changes:
                rv001_updates.append({"trial_id": "jRCT2033240611", "changes": changes})
    except Exception as exc:
        errors.append(f"jRCT RV-001: {type(exc).__name__}")

    maplight_trials: list[dict] = []
    maplight_snapshots: dict[str, dict] = {}
    maplight_updates: list[dict] = []
    new_maplight_trials: list[dict] = []
    maplight_trials_ok = False
    try:
        maplight_trials = discover_maplight_trials()
        maplight_snapshots = {item["nct"]: item["snapshot"] for item in maplight_trials}
        maplight_trials_ok = True
        if initialized:
            for item in maplight_trials:
                nct = item["nct"]
                if nct not in old_maplight:
                    new_maplight_trials.append(item)
                    continue
                changes = trial_changes(old_maplight[nct], item["snapshot"])
                if changes:
                    maplight_updates.append({
                        "nct": nct,
                        "program": item["program"],
                        "changes": changes,
                    })
    except Exception as exc:
        maplight_errors.append(f"ClinicalTrials MapLight discovery: {type(exc).__name__}")

    cns_trials: list[dict] = []
    try:
        cns_trials = discover_nonretinal_trials()
        successful += 1
    except Exception as exc:
        errors.append(f"ClinicalTrials optogenetics discovery: {type(exc).__name__}")

    expected_sources = 1 + len(COMPANY_SOURCES) + 1 + len(TRIALS) + 1 + 1
    minimum_successful = max(8, (expected_sources * 2 + 2) // 3)
    maplight_health_ok = maplight_rss_ok and maplight_bridge_ok and maplight_trials_ok
    if successful < minimum_successful or not nobel_ok:
        STATUS.write_text(
            "# 광유전학 임상·허가 감시 상태\n\n"
            f"- 공식 소스 정상 조회: {successful}/{expected_sources} · 최소 통과 {minimum_successful}\n"
            f"- 노벨상 공식 검증: {'성공' if nobel_ok else '실패'}\n"
            f"- MapLight 전용 감시: {'정상' if maplight_health_ok else '독립 보류 — 기존 MapLight 기준선 유지'}\n"
            "- 상태 기준선: 갱신하지 않음\n"
            "- Telegram: 송출하지 않음\n"
            + ("\n".join(f"- 오류: {e}" for e in errors) + "\n" if errors else ""),
            encoding="utf-8",
        )
        raise RuntimeError("optogenetics source health failed; baseline intentionally not advanced")

    current_keys = list(dict.fromkeys([x["key"] for x in events] + list(old_seen)))[:1000]
    cns_ids = sorted({x["nct"] for x in cns_trials} | old_cns)
    new_items = [x for x in events if x["key"] not in old_seen] if initialized else []
    new_cns = [x for x in cns_trials if x["nct"] not in old_cns] if initialized else []

    maplight_press_updates: list[dict] = []
    current_maplight_milestones = set(old_maplight_milestones)
    if maplight_health_ok:
        for item in maplight_events:
            keys = set(item.get("milestone_keys") or [])
            unseen = keys - old_maplight_milestones
            if initialized and old_maplight_version >= MAPLIGHT_TRACK_VERSION and unseen:
                maplight_press_updates.append(item)
            current_maplight_milestones.update(keys)
    else:
        maplight_snapshots = old_maplight
        maplight_updates = []
        new_maplight_trials = []

    source_version = int(old.get("source_version") or 0)
    if initialized and source_version < 6:
        # Source coverage expanded after the first baseline. Do not replay
        # historical GS030/Nanoscope/Ray/Restore Vision/Augelux/MapLight items as new events.
        new_items = []
        rv001_updates = []
        maplight_updates = []
        new_maplight_trials = []

    if old_maplight_version < MAPLIGHT_TRACK_VERSION:
        maplight_press_updates = []
        maplight_updates = []
        new_maplight_trials = []

    pending = {
        "initialized": True,
        "version": 1,
        "source_version": 7,
        "ray_official_index_verified": ray_official_index_ok,
        "maplight_track_version": MAPLIGHT_TRACK_VERSION,
        "maplight_health_ok": maplight_health_ok,
        "maplight_optogenetics_bridge_verified": maplight_bridge_ok,
        "maplight_seen_milestone_keys": sorted(current_maplight_milestones) if maplight_health_ok else sorted(old_maplight_milestones),
        "last_checked_kst": dt.datetime.now(KST).isoformat(timespec="seconds"),
        "nobel_2026_verified": nobel_ok,
        "seen_event_keys": current_keys,
        "trial_snapshots": snapshots,
        "rv001_registry_snapshot": rv001_snapshot,
        "maplight_trial_snapshots": maplight_snapshots,
        "cns_trial_ids": cns_ids,
        "relevant_press_events": len(events),
        "source_errors": errors,
        "maplight_source_errors": maplight_errors,
    }
    for k in ("last_successful_delivery_kst", "telegram_message_ids", "bot_username"):
        if old.get(k) is not None:
            pending[k] = old[k]
    save_json(PENDING, pending)

    now = dt.datetime.now(KST)
    if initialized and (new_items or trial_updates or rv001_updates or maplight_press_updates or maplight_updates or new_maplight_trials or new_cns):
        ALERT.write_text(
            render_alert(
                new_items[:8],
                trial_updates[:8],
                rv001_updates[:4],
                maplight_press_updates[:8],
                maplight_updates[:8],
                new_maplight_trials[:4],
                new_cns[:4],
                now,
            ),
            encoding="utf-8",
        )

    STATUS.write_text(
        "# 광유전학 임상·허가 감시 상태\n\n"
        f"- 노벨상 공식 검증: **{'성공' if nobel_ok else '실패'}**\n"
        f"- MapLight 전용 감시: **{'정상' if maplight_health_ok else '보류 — MapLight 기준선 미갱신'}**\n"
        f"- MapLight 광유전학 기반 약물발굴 연결: **{'성공' if maplight_bridge_ok else '실패'}**\n"
        f"- 공식 소스 정상 조회: **{successful}/{expected_sources}** · 최소 통과 **{minimum_successful}**\n"
        f"- 공식 기업 이벤트 기준선: **{len(events)}건**\n"
        f"- 추적 ClinicalTrials.gov 임상: **{len(snapshots)}건**\n"
        f"- 일본 jRCT RV-001 등록: **{'확인' if rv001_snapshot else '확인 실패'}**\n"
        f"- MapLight 광유전학 기반 약물발굴 임상: **{len(maplight_snapshots)}건**\n"
        f"- MapLight 신규 변화: **{len(maplight_press_updates) + len(maplight_updates) + len(new_maplight_trials)}건**\n"
        f"- 비망막 중추신경계 광유전학 임상: **{len(cns_trials)}건**\n"
        f"- 신규 알림: **{len(new_items) + len(trial_updates) + len(rv001_updates) + len(maplight_press_updates) + len(maplight_updates) + len(new_maplight_trials) + len(new_cns)}건**\n"
        f"- 일반 소스 오류: **{len(errors)}건** · MapLight 소스 오류: **{len(maplight_errors)}건**\n",
        encoding="utf-8",
    )

    print(
        f"optogenetics_watch initialized_before={initialized} press={len(events)} "
        f"trial_updates={len(trial_updates)} rv001_updates={len(rv001_updates)} "
        f"maplight_press={len(maplight_press_updates)} maplight_updates={len(maplight_updates)} "
        f"maplight_new={len(new_maplight_trials)} maplight_health={int(maplight_health_ok)} cns_new={len(new_cns)} "
        f"alert={int(ALERT.exists())} errors={len(errors)} maplight_errors={len(maplight_errors)}"
    )
    if errors:
        print("optogenetics_source_errors=" + json.dumps(errors, ensure_ascii=False))
    if maplight_errors:
        print("maplight_source_errors=" + json.dumps(maplight_errors, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
