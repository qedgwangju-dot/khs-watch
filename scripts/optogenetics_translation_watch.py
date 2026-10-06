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
GENSIGHT_NEWS = "https://www.gensight-biologics.com/subject/gs030/"

TRIALS = {
    "NCT06460844": {"company": "Ray Therapeutics", "program": "RTx-015"},
    "NCT06162585": {"company": "Nanoscope Therapeutics", "program": "MOGENRY/MCO-010"},
    "NCT04945772": {"company": "Nanoscope Therapeutics", "program": "MOGENRY/MCO-010"},
    "NCT03326336": {"company": "GenSight Biologics", "program": "GS030"},
}

COMPANY_SOURCES = [
    ("Nanoscope Therapeutics", NANOSCOPE_NEWS, ("mogenry", "mco-010", "sonpiretigene", "optogen")),
    ("Ray Therapeutics", RAY_NEWS, ("rtx-015", "rtx-021", "optogen")),
    ("GenSight Biologics", GENSIGHT_NEWS, ("gs030", "optogen")),
]

ACTION_TERMS = (
    "fda", "bla", "pdufa", "approval", "approved", "acceptance", "accepted", "priority review",
    "complete response", "crl", "rmat", "prime", "pmda", "mhlw", "nda", "sakigake",
    "phase 1", "phase 2", "phase 3", "phase 2/3", "clinical trial", "trial", "dosing", "dosed",
    "patient", "topline", "data", "results", "endpoint", "manufacturing", "commercial",
    "launch", "partnership", "license", "licensing", "financing", "series b", "series c",
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
    if ("fda" in low and "bla" in low and ("accept" in low or "file" in low)):
        return "FDA 허가심사", "FDA가 생물의약품 허가신청(BLA)을 접수·심사 단계로 전환"
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
    if any(x in low for x in ("manufacturing", "commercial", "launch")):
        return "상용화 준비", "제조·상용화·출시 준비 단계 변화"
    if any(x in low for x in ("partnership", "license", "licensing")):
        return "사업협력", "기술이전·라이선스·사업협력 변화"
    if any(x in low for x in ("financing", "series b", "series c")):
        return "개발자금", "임상·상용화를 위한 신규 자금조달"
    return "광유전학 임상", "광유전학 임상·규제 단계 변화"


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
            "program": "RTx-015/RTx-021" if company == "Ray Therapeutics" else "광유전학",
            "stage": stage,
            "meaning": meaning,
            "title": title,
            "url": link,
            "source": "회사 공식 RSS",
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
            "program": next((p for p in ("MOGENRY/MCO-010", "RTx-015/RTx-021", "GS030") if (
                ("mogenry" in low or "mco-010" in low) and p == "MOGENRY/MCO-010"
                or ("rtx-015" in low or "rtx-021" in low) and p == "RTx-015/RTx-021"
                or "gs030" in low and p == "GS030"
            )), "광유전학"),
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


def validate_nobel() -> bool:
    text = clean(re.sub(r"<[^>]+>", " ", fetch_text(KI_NOBEL))).lower()
    required = ("2026", "peter hegemann", "georg nagel", "karl deisseroth", "optogenetics", "channelrhodopsin")
    return all(x in text for x in required)


def render_alert(items: list[dict], trial_updates: list[dict], new_cns_trials: list[dict], now: dt.datetime) -> str:
    lines = [
        "[바이오 감시] 광유전학 임상·허가 구조 변화",
        f"조회 시각: {now.strftime('%Y-%m-%d %H:%M KST')}",
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
        "- 뇌·BCI: 아직 노벨상 수상 자체를 임상 상용화로 승격하지 않습니다. 비망막 인간 임상 등록·IND·환자투여가 생길 때 별도 핵심 알림으로 올립니다.",
        "- 연구장비: Bruker/Inscopix 같은 연구도구는 직접 임상·상용화 매출과 분리하며, 단순 노벨상 테마 뉴스에는 알림하지 않습니다.",
    ]
    return "\n".join(lines).strip() + "\n"


def self_test() -> None:
    stage, _ = classify_press("Nanoscope FDA Acceptance of BLA for MOGENRY")
    assert stage == "FDA 허가심사"
    stage, _ = classify_press("Ray Therapeutics Receives FDA RMAT Designation for RTx-015")
    assert stage == "FDA RMAT"
    stage, _ = classify_press("MOGENRY PDUFA Date Announced")
    assert stage == "FDA 심사기한"
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

    for company, url, terms in COMPANY_SOURCES:
        try:
            if company == "Ray Therapeutics":
                try:
                    rows = meaningful_press_links(company, url, terms)
                except Exception:
                    rows = meaningful_rss_links(company, RAY_FEED, terms)
                events.extend(rows)
            else:
                events.extend(meaningful_press_links(company, url, terms))
            successful += 1
        except Exception as exc:
            errors.append(f"{company}: {type(exc).__name__}")

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

    cns_trials: list[dict] = []
    try:
        cns_trials = discover_nonretinal_trials()
        successful += 1
    except Exception as exc:
        errors.append(f"ClinicalTrials optogenetics discovery: {type(exc).__name__}")

    if successful < 6 or not nobel_ok:
        STATUS.write_text(
            "# 광유전학 임상·허가 감시 상태\n\n"
            f"- 공식 소스 정상 조회: {successful}/9\n"
            f"- 노벨상 공식 검증: {'성공' if nobel_ok else '실패'}\n"
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

    source_version = int(old.get("source_version") or 0)
    if initialized and source_version < 2:
        # Ray's official RSS fallback was added after the initial baseline.
        # Do not resend already-known 2026 RMAT/PRIME/financing items as new events.
        new_items = [x for x in new_items if x.get("company") != "Ray Therapeutics"]

    pending = {
        "initialized": True,
        "version": 1,
        "source_version": 2,
        "last_checked_kst": dt.datetime.now(KST).isoformat(timespec="seconds"),
        "nobel_2026_verified": nobel_ok,
        "seen_event_keys": current_keys,
        "trial_snapshots": snapshots,
        "cns_trial_ids": cns_ids,
        "relevant_press_events": len(events),
        "source_errors": errors,
    }
    for k in ("last_successful_delivery_kst", "telegram_message_ids", "bot_username"):
        if old.get(k) is not None:
            pending[k] = old[k]
    save_json(PENDING, pending)

    now = dt.datetime.now(KST)
    if initialized and (new_items or trial_updates or new_cns):
        ALERT.write_text(render_alert(new_items[:8], trial_updates[:8], new_cns[:4], now), encoding="utf-8")

    STATUS.write_text(
        "# 광유전학 임상·허가 감시 상태\n\n"
        f"- 노벨상 공식 검증: **{'성공' if nobel_ok else '실패'}**\n"
        f"- 공식 소스 정상 조회: **{successful}/9**\n"
        f"- 공식 기업 이벤트 기준선: **{len(events)}건**\n"
        f"- 추적 임상: **{len(snapshots)}건**\n"
        f"- 비망막 중추신경계 광유전학 임상: **{len(cns_trials)}건**\n"
        f"- 신규 알림: **{len(new_items) + len(trial_updates) + len(new_cns)}건**\n"
        f"- 오류: **{len(errors)}건**\n",
        encoding="utf-8",
    )

    print(
        f"optogenetics_watch initialized_before={initialized} press={len(events)} "
        f"trial_updates={len(trial_updates)} cns_new={len(new_cns)} "
        f"alert={int(ALERT.exists())} errors={len(errors)}"
    )
    if errors:
        print("optogenetics_source_errors=" + json.dumps(errors, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
