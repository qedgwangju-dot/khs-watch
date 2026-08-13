#!/usr/bin/env python3
"""Deep Fission semantic milestone watcher v3.

Principles:
- No alert for raw HTML/hash changes.
- Alert only for a new official document or a semantic state transition.
- Planned/future wording is never treated as completed.
- Company attribution is required for DOE criticality/fuel-loading events.
- Event IDs are persisted so the same event is sent only once.
"""

from __future__ import annotations

import argparse
import datetime as dt
import html
from html.parser import HTMLParser
import json
import os
import pathlib
import re
import time
import urllib.error
import urllib.request
from urllib.parse import urljoin

ROOT = pathlib.Path(__file__).resolve().parents[1]
DATA = ROOT / "data"
OUT = ROOT / "out"
STATE = DATA / "deep_fission_watch_v3_state.json"
PENDING = OUT / "deep_fission_watch_v3_state_pending.json"
ALERT = OUT / "deep_fission_alert_v3.md"
STATUS = OUT / "deep_fission_status_v3.md"
ERRORS = OUT / "deep_fission_errors_v3.log"

PRESS_URL = "https://www.deepfission.com/pr-media-kit/press-releases"
PARSONS_URL = "https://www.deepfission.com/sites/parsons"
NRC_URL = "https://www.nrc.gov/reactors/new-reactors/advanced/who-were-working-with/pre-application-activities/deep-fission"
DOE_URL = "https://www.energy.gov/ne/us-department-energy-reactor-pilot-program"
SEC_SUBMISSIONS = "https://data.sec.gov/submissions/CIK0001918102.json"

UA = os.environ.get(
    "DEEP_FISSION_WATCH_USER_AGENT",
    "KHS-Deep-Fission-Watch/3.0 contact=github-actions",
)

IMPORTANT_FORMS = {"8-K", "10-Q", "10-K", "S-1", "S-1/A", "424B4"}
MONTHS = {
    "january": "01", "february": "02", "march": "03", "april": "04",
    "may": "05", "june": "06", "july": "07", "august": "08",
    "september": "09", "october": "10", "november": "11", "december": "12",
}


class PageParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.parts: list[str] = []
        self.links: list[tuple[str, str]] = []
        self._href: str | None = None
        self._anchor: list[str] = []

    def handle_starttag(self, tag: str, attrs):
        t = tag.lower()
        if t == "a":
            self._href = dict(attrs).get("href")
            self._anchor = []
        if t in {"p", "div", "li", "tr", "td", "th", "br", "h1", "h2", "h3", "h4"}:
            self.parts.append("\n")

    def handle_endtag(self, tag: str):
        t = tag.lower()
        if t == "a" and self._href:
            label = " ".join(self._anchor).strip()
            self.links.append((self._href, label))
            self._href = None
            self._anchor = []
        if t in {"p", "div", "li", "tr", "td", "th", "h1", "h2", "h3", "h4"}:
            self.parts.append("\n")

    def handle_data(self, data: str):
        value = html.unescape(data)
        self.parts.append(value)
        if self._href is not None:
            self._anchor.append(value)

    def text(self) -> str:
        raw = "".join(self.parts)
        raw = re.sub(r"[\t\r ]+", " ", raw)
        raw = re.sub(r"\n\s*\n+", "\n", raw)
        return raw.strip()


def fetch(url: str, accept: str = "text/html,application/json", timeout: int = 30) -> str:
    req = urllib.request.Request(
        url,
        headers={
            "User-Agent": UA,
            "Accept": accept,
            "Accept-Language": "en-US,en;q=0.8",
        },
    )
    last: Exception | None = None
    for attempt in range(3):
        try:
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                return resp.read().decode("utf-8", errors="replace")
        except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError) as exc:
            last = exc
            time.sleep(1.5 * (attempt + 1))
    raise RuntimeError(f"원천 조회 실패 {url}: {last}")


def parse_page(raw: str) -> tuple[str, list[tuple[str, str]]]:
    p = PageParser()
    p.feed(raw)
    return p.text(), p.links


def norm(value: str) -> str:
    value = html.unescape(value).lower()
    value = value.replace("™", "")
    return re.sub(r"\s+", " ", value).strip()


def load_state() -> dict:
    if not STATE.exists():
        return {}
    try:
        return json.loads(STATE.read_text(encoding="utf-8"))
    except Exception:
        return {}


def release_date(text: str) -> str:
    m = re.search(
        r"Released\s+(January|February|March|April|May|June|July|August|September|October|November|December)\s+(\d{1,2}),\s+(20\d{2})",
        text,
        re.I,
    )
    if not m:
        return ""
    return f"{m.group(3)}-{MONTHS[m.group(1).lower()]}-{int(m.group(2)):02d}"


def kst_now() -> str:
    tz = dt.timezone(dt.timedelta(hours=9))
    return dt.datetime.now(tz).strftime("%Y-%m-%d %H:%M KST")


def lines(text: str) -> list[str]:
    return [re.sub(r"\s+", " ", x).strip() for x in text.splitlines() if x.strip()]


def press_items(raw: str) -> dict[str, str]:
    _, links = parse_page(raw)
    out: dict[str, str] = {}
    for href, label in links:
        if "/press-releases/detail/" not in href:
            continue
        url = urljoin(PRESS_URL, href)
        title = re.sub(r"\s+", " ", label).strip()
        if len(title) >= 8:
            out[url] = title
    return out


def extract_nrc_state(text: str) -> dict:
    low = norm(text)
    phase = "pre-application" if (
        "currently engaged in pre-application activities" in low
        or "pre-application activities associated with a future combined license application" in low
    ) else "unknown"
    if re.search(r"deep fission.{0,180}(?:submitted|filed).{0,100}(?:combined license application|col application)", low):
        phase = "combined-license-submitted"
    if re.search(r"(?:combined license application|col application).{0,160}(?:accepted for review|docketed)", low):
        phase = "combined-license-docketed"

    statuses: dict[str, str] = {}
    compact = " | ".join(lines(text))
    docs = {
        "regulatory_engagement_plan": "NRC Regulatory Engagement Plan",
        "conceptual_design_review": "Conceptual Design Review",
        "conceptual_design_description": "Conceptual Design Description",
    }
    allowed = [
        "No Review Requested", "Review Complete", "Review in Progress",
        "Accepted", "Docketed", "Closed", "Open",
    ]
    for key, label in docs.items():
        idx = compact.lower().find(label.lower())
        if idx < 0:
            continue
        window = compact[idx: idx + 900]
        for status in allowed:
            if status.lower() in window.lower():
                statuses[key] = status
                break

    docket = ""
    m = re.search(r"NRC Docket\s+(\d+)", text, re.I)
    if m:
        docket = m.group(1)
    return {"phase": phase, "statuses": statuses, "docket": docket}


def _explicit_deep_fission_line(text: str, action_pattern: str) -> bool:
    for line in lines(text):
        low = norm(line)
        if "deep fission" not in low:
            continue
        if re.search(action_pattern, low):
            return True
    return False


def extract_doe_state(text: str) -> dict:
    return {
        "selected": any("deep fission" in norm(x) for x in lines(text)),
        "criticality": _explicit_deep_fission_line(
            text, r"(?:reached|achieved|successfully achieved|first)\s+(?:first\s+)?criticality"
        ),
        "fuel_loading": _explicit_deep_fission_line(
            text, r"(?:completed|began|started|authorized)\s+(?:nuclear\s+)?fuel\s+loading"
        ),
        "full_power": _explicit_deep_fission_line(
            text, r"(?:reached|achieved|completed).{0,40}(?:full[- ]power|full power)"
        ),
    }


def extract_parsons_state(text: str) -> dict[str, bool]:
    low = norm(text)
    return {
        "data_well_6000_complete": bool(re.search(
            r"(?:completed drilling|drilling of the data acquisition well.{0,40}complete).{0,180}(?:6,000|6000)\s*feet",
            low,
        )),
        "prototype_canister_on_site": bool(
            re.search(r"prototype reactor canister.{0,120}(?:received|arriv(?:ed|al)|deliver(?:ed|y)).{0,100}(?:parsons|project site|site)", low)
            or "reactor canister on site" in low
            or re.search(r"fabrication, hydrostatic testing, and delivery to project site.{0,80}prototype canister", low)
        ),
        "second_well_ground_prep_complete": (
            "ground preparations complete for our second test well" in low
            or "finished ground preparations for our second test well" in low
        ),
        "poc_drilling_started": bool(
            re.search(r"(?:began|has begun|started|has started|commenced|is drilling|drilling is underway|spudded).{0,180}(?:2,500|2500|proof of concept|second test well|commercial-scale borehole)", low)
            or re.search(r"(?:2,500|2500|proof of concept|second test well|commercial-scale borehole).{0,180}(?:began drilling|started drilling|commenced drilling|drilling is underway|spudded)", low)
        ),
        "poc_depth_reached": bool(
            re.search(r"(?:reached|completed).{0,120}(?:2,500|2500)\s*(?:foot|feet|ft)", low)
            or re.search(r"(?:2,500|2500)\s*(?:foot|feet|ft).{0,120}(?:depth reached|drilling complete|completed)", low)
        ),
        "prototype_underground_deployed": bool(
            re.search(r"(?:lowered|installed|deployed|emplaced).{0,120}prototype.{0,120}(?:underground|borehole|2,500|2500)", low)
            or re.search(r"prototype.{0,120}(?:lowered|installed|deployed|emplaced).{0,120}(?:underground|borehole|2,500|2500)", low)
        ),
        "non_nuclear_demo_complete": bool(
            re.search(r"(?:completed|successfully completed).{0,140}(?:non-nuclear).{0,100}(?:test|testing|demonstration)", low)
            or re.search(r"(?:non-nuclear).{0,100}(?:test|testing|demonstration).{0,140}(?:completed|complete|successful)", low)
        ),
        "doe_construct_operate_authorized": bool(
            re.search(r"doe.{0,80}(?:has )?(?:authorized|approved|granted).{0,180}(?:construct|construction).{0,120}(?:operate|operation)", low)
            or re.search(r"authorization to construct and operate.{0,100}(?:obtained|granted|approved)", low)
        ),
        "nrc_col_submitted": bool(
            re.search(r"(?:submitted|filed).{0,100}(?:combined license application|commercial operating license application)", low)
            or re.search(r"(?:combined license application|commercial operating license application).{0,100}(?:submitted|filed)", low)
        ),
        "deep_fission_criticality": _explicit_deep_fission_line(
            text, r"(?:reached|achieved|successfully achieved)\s+(?:first\s+)?criticality"
        ),
    }


MILESTONE_META = {
    "poc_drilling_started": (
        "파슨스 약 2,500ft 상업규모 PoC borehole이 실제 시추 착수",
        "시추 준비·착수 예정", "실제 시추 착수",
        "공정", "시간표",
        "시추 깊이·공경 유지, 목표 깊이 도달 여부, borehole 안정성",
        PARSONS_URL, "Deep Fission Parsons"
    ),
    "poc_depth_reached": (
        "파슨스 PoC borehole이 약 2,500ft 목표 깊이에 도달",
        "시추 진행/예정", "목표 깊이 도달",
        "공정", "시간표",
        "borehole integrity, 케이싱·시멘팅, prototype 하강 준비",
        PARSONS_URL, "Deep Fission Parsons"
    ),
    "prototype_underground_deployed": (
        "non-nuclear prototype이 borehole 지하에 실제 설치·하강",
        "prototype 현장 대기", "지하 설치·하강",
        "실증·공정", "할인율, 시간표",
        "설치 안정성, 인양·회수 가능성, 열수력 시험 결과",
        PARSONS_URL, "Deep Fission Parsons"
    ),
    "non_nuclear_demo_complete": (
        "파슨스 non-nuclear 실증 시험 완료가 공식 확인",
        "실증 진행/예정", "실증 완료",
        "실증", "할인율, 시간표",
        "열수력·구조건전성 결과와 DOE 후속 authorization",
        PARSONS_URL, "Deep Fission Parsons"
    ),
    "doe_construct_operate_authorized": (
        "DOE가 Deep Fission pilot reactor의 건설·운전을 실제 승인",
        "후속 DOE authorization 필요", "건설·운전 authorization 확보",
        "인허가·실증", "할인율, 시간표",
        "착공, 연료 장전, 안전시험, 임계 도달",
        PARSONS_URL, "Deep Fission Parsons/DOE"
    ),
    "nrc_col_submitted": (
        "NRC Combined License 신청서가 실제 제출됨",
        "NRC pre-application", "Combined License 제출",
        "인허가", "할인율, 시간표",
        "NRC docketing, review schedule, RAI, hearing/EIS 일정",
        NRC_URL, "NRC/Deep Fission"
    ),
    "deep_fission_criticality": (
        "Deep Fission 원자로가 실제 임계 도달했다고 공식 확인",
        "임계 미도달", "임계 도달",
        "실증", "할인율, 시간표",
        "출력시험, DOE 후속 authorization, NRC 상업허가",
        DOE_URL, "DOE/Deep Fission"
    ),
}


def axes_for(stage: str) -> str:
    axes = []
    if "계약" in stage or "자금" in stage:
        axes.append("돈 버는 능력")
    if "인허가" in stage or "실증" in stage:
        axes.append("할인율")
    if "자금" in stage:
        axes.append("수급")
    if any(x in stage for x in ["인허가", "실증", "공정", "계약"]):
        axes.append("시간표")
    return ", ".join(dict.fromkeys(axes)) if axes else "시간표"


def message(
    fact: str,
    previous: str,
    current: str,
    official_date: str,
    stage: str,
    next_check: str,
    source: str,
    url: str,
    korea: str = "두산에너빌리티·수산이앤에스 신규 직접계약은 이번 변화만으로 확인되지 않음",
    risk: str = "기술·규제 진전이 상업계약·매출로 연결되기 전에 일정 지연 또는 추가 자금조달이 발생할 수 있음",
) -> str:
    return (
        f"[Deep Fission 중요 변화 | {kst_now()}]\n"
        f"- 판정: 신규 공식 변화 확인\n"
        f"- 새 사실: {fact}\n"
        f"- 이전 → 현재: {previous} → {current}\n"
        f"- 공식일: {official_date or '공식 원문 날짜 미표시'}\n"
        f"- 단계: {stage}\n"
        f"- 바뀐 축: {axes_for(stage)}\n"
        f"- 한국 기업 연결: {korea}\n"
        f"- 실패 경로: {risk}\n"
        f"- 다음 확인: {next_check}\n"
        f"- 출처: {source}\n"
        f"- 링크: {url}"
    )


def classify_press(title: str, text: str, url: str) -> list[tuple[str, str]]:
    low = norm(title + "\n" + text)
    d = release_date(text)
    out: list[tuple[str, str]] = []

    if (
        "nuclear safety design agreement" in low
        and ("approves" in norm(title) or re.search(r"doe.{0,100}has approved.{0,180}(?:nuclear safety design agreement|nsda)", low))
    ):
        eid = f"nsda-approved:{d or url}"
        out.append((eid, message(
            "DOE가 Gravity Reactor의 Nuclear Safety Design Agreement(NSDA)를 승인",
            "NSDA 검토/조건부 단계", "NSDA 승인·후속 DOE authorization 단계",
            d, "인허가·실증",
            "후속 DOE safety review·건설/운전 authorization, Parsons PoC 실증",
            "Deep Fission 공식 보도자료", url,
        )))
        return out

    if re.search(r"prototype reactor canister.{0,80}(?:arrives|arrived|delivered)", low):
        eid = f"prototype-canister-on-site:{d or url}"
        out.append((eid, message(
            "prototype reactor canister의 제작·시험·Parsons 현장 도착이 공식 확인",
            "prototype 제작/시험", "현장 도착·PoC 설치 준비",
            d, "공정·실증",
            "약 2,500ft PoC borehole 시추 착수와 prototype 지하 하강",
            "Deep Fission 공식 보도자료", url,
        )))
        return out

    if "customer pipeline" in low and ("18.5" in low or "gigawatt" in low):
        eid = f"customer-pipeline:{d or url}"
        binding = "non-binding" not in low
        out.append((eid, message(
            "고객 pipeline 최대 18.5GW 공개" + ("; 구속력 계약 표현 확인" if binding else "; LOI는 non-binding"),
            "고객 수요 정량 공개 전", "최대 18.5GW pipeline 공개",
            d, "고객·계약",
            "named customer, binding PPA/offtake, MW·가격·착공시점",
            "Deep Fission 공식 보도자료", url,
            risk="non-binding LOI가 definitive agreement·PPA·실제 매출로 전환되지 않을 수 있음",
        )))
        return out

    if "urenco" in low and re.search(r"(?:signs|signed|agreement|fuel deal)", low):
        eid = f"urenco-fuel:{d or url}"
        out.append((eid, message(
            "Urenco USA와 핵연료 공급 관련 공식 계약/합의가 발표됨",
            "연료 공급 계약 미확인", "Urenco USA 연료 공급 관계 공식화",
            d, "공급망·계약",
            "연료 규격·수량·인도시점·DOE/NRC 승인과 실제 pilot fuel loading",
            "Deep Fission 공식 보도자료", url,
        )))
        return out

    if re.search(r"(?:began|started|commenced|spudded).{0,160}(?:2,500|2500|proof of concept|commercial-scale borehole)", low):
        eid = f"poc-drilling-started:{d or url}"
        out.append((eid, message(
            "약 2,500ft PoC borehole 시추가 실제 착수",
            "착수 예정/준비", "실제 시추 착수",
            d, "공정",
            "목표 깊이 도달, borehole integrity, prototype 하강",
            "Deep Fission 공식 보도자료", url,
        )))
        return out

    if _explicit_deep_fission_line(text, r"(?:reached|achieved|successfully achieved)\s+(?:first\s+)?criticality"):
        eid = f"deep-fission-criticality:{d or url}"
        out.append((eid, message(
            "Deep Fission 원자로의 실제 임계 도달이 공식 발표됨",
            "임계 미도달", "임계 도달",
            d, "실증",
            "출력시험, DOE 후속 승인, NRC commercial licensing",
            "Deep Fission 공식 보도자료", url,
        )))
        return out

    if any(x in norm(title) for x in [
        "public offering", "financing", "power purchase", "ppa", "contract",
        "order", "final investment decision", "combined license",
    ]):
        eid = f"press:{url}"
        out.append((eid, message(
            f"신규 공식 보도자료 발표: {title}",
            "미공개", "공식 발표",
            d, "자금조달·고객·계약" if "offering" in norm(title) else "고객·계약",
            "금액·구속력·counterparty·실제 매출/현금흐름 연결 여부",
            "Deep Fission 공식 보도자료", url,
        )))
    return out


def sec_recent() -> dict[str, dict[str, str]]:
    raw = fetch(SEC_SUBMISSIONS, accept="application/json")
    obj = json.loads(raw)
    recent = (obj.get("filings") or {}).get("recent") or {}
    out: dict[str, dict[str, str]] = {}
    accessions = recent.get("accessionNumber") or []
    forms = recent.get("form") or []
    dates = recent.get("filingDate") or []
    docs = recent.get("primaryDocument") or []
    descriptions = recent.get("primaryDocDescription") or []
    for i, accession in enumerate(accessions):
        form = forms[i] if i < len(forms) else ""
        if form not in IMPORTANT_FORMS:
            continue
        doc = docs[i] if i < len(docs) else ""
        acc = accession.replace("-", "")
        url = f"https://www.sec.gov/Archives/edgar/data/1918102/{acc}/{doc}" if doc else "https://www.sec.gov/edgar/browse/?CIK=1918102"
        out[accession] = {
            "form": form,
            "date": dates[i] if i < len(dates) else "",
            "description": descriptions[i] if i < len(descriptions) else "",
            "url": url,
        }
    return out


def sec_message(accession: str, meta: dict) -> tuple[str, str]:
    form = meta.get("form", "")
    date = meta.get("date", "")
    url = meta.get("url", "")
    if form in {"10-Q", "10-K"}:
        stage = "재무·자금조달"
        next_check = "매출, 현금잔고, 영업현금유출, R&D, going concern, pilot CAPEX"
    elif form in {"S-1", "S-1/A", "424B4"}:
        stage = "자금조달"
        next_check = "발행 주식수·가격·순유입 현금·희석률·자금 사용처"
    else:
        stage = "공시"
        next_check = "8-K Item과 계약·인허가·경영진·자금조달의 실제 변경 내용"
    eid = f"sec:{accession}"
    return eid, message(
        f"SEC Form {form} 신규 제출",
        "해당 accession 미제출", f"{form} 제출",
        date, stage, next_check, "U.S. SEC", url,
        risk="신규 공시의 회계·자금조달 항목은 본업 실증 진전과 분리해 해석해야 함",
    )


def self_test() -> None:
    doe_false = """
    Program goal: reaching criticality for at least three concepts.
    Deep Fission Inc.
    Antares Nuclear successfully reached criticality.
    """
    assert not extract_doe_state(doe_false)["criticality"]

    doe_true = "Deep Fission Inc. successfully achieved first criticality at its Parsons reactor."
    assert extract_doe_state(doe_true)["criticality"]

    parsons_future = """
    We are targeting Q3 of 2026 to begin drilling our ~2,500 foot proof of concept borehole.
    Next Step: Apply for a Combined License under 10 CFR Part 52 with the NRC.
    """
    p = extract_parsons_state(parsons_future)
    assert not p["poc_drilling_started"]
    assert not p["nrc_col_submitted"]

    parsons_true = """
    Deep Fission has begun drilling its 2,500 foot proof of concept borehole.
    The company submitted a Combined License application to the NRC.
    """
    p = extract_parsons_state(parsons_true)
    assert p["poc_drilling_started"]
    assert p["nrc_col_submitted"]

    criticality_negation = "Deep Fission's Parsons project is not designed as a one-time criticality test."
    assert not _explicit_deep_fission_line(
        criticality_negation,
        r"(?:reached|achieved|successfully achieved)\s+(?:first\s+)?criticality",
    )
    print("deep_fission_v3_self_test=success")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--mode", choices=["check", "self-test"], default="check")
    args = ap.parse_args()
    if args.mode == "self-test":
        self_test()
        return 0

    DATA.mkdir(parents=True, exist_ok=True)
    OUT.mkdir(parents=True, exist_ok=True)
    for p in (PENDING, ALERT, STATUS, ERRORS):
        if p.exists():
            p.unlink()

    old = load_state()
    first_run = not bool(old)
    state = {
        "version": 3,
        "updated_at": dt.datetime.now(dt.timezone.utc).replace(microsecond=0).isoformat(),
        "press_urls": dict(old.get("press_urls") or {}),
        "sec_filings": dict(old.get("sec_filings") or {}),
        "nrc": dict(old.get("nrc") or {}),
        "doe": dict(old.get("doe") or {}),
        "parsons": dict(old.get("parsons") or {}),
        "sent_event_ids": list(old.get("sent_event_ids") or []),
    }
    sent_ids = set(state["sent_event_ids"])
    in_run_ids: set[str] = set()
    events: list[str] = []
    errors: list[str] = []
    fetched = 0

    def add_event(eid: str, msg: str):
        if eid in sent_ids or eid in in_run_ids:
            return
        in_run_ids.add(eid)
        events.append(msg)

    try:
        raw = fetch(PRESS_URL)
        fetched += 1
        items = press_items(raw)
        for url, title in items.items():
            if url in state["press_urls"]:
                continue
            state["press_urls"][url] = title
            if first_run:
                continue
            try:
                detail = fetch(url)
                fetched += 1
                text, _ = parse_page(detail)
                for eid, msg in classify_press(title, text, url):
                    add_event(eid, msg)
            except Exception as exc:
                errors.append(f"보도자료 상세 조회 실패 {url}: {exc}")
    except Exception as exc:
        errors.append(f"보도자료 목록 조회 실패: {exc}")

    try:
        filings = sec_recent()
        fetched += 1
        for accession, meta in filings.items():
            if accession in state["sec_filings"]:
                continue
            state["sec_filings"][accession] = meta
            if first_run:
                continue
            eid, msg = sec_message(accession, meta)
            add_event(eid, msg)
    except Exception as exc:
        errors.append(f"SEC 조회 실패: {exc}")

    try:
        raw = fetch(NRC_URL)
        fetched += 1
        text, _ = parse_page(raw)
        current = extract_nrc_state(text)
        previous = state["nrc"]
        if not first_run and previous:
            prev_phase = previous.get("phase")
            cur_phase = current.get("phase")
            if cur_phase and cur_phase != "unknown" and cur_phase != prev_phase:
                eid = f"nrc-phase:{prev_phase}->{cur_phase}"
                add_event(eid, message(
                    "NRC의 Deep Fission licensing phase가 공식 변경",
                    str(prev_phase), str(cur_phase), "",
                    "인허가", "NRC docketing·review schedule·RAI/EIS/hearing",
                    "U.S. NRC", NRC_URL,
                ))
            prev_status = previous.get("statuses") or {}
            for key, cur in (current.get("statuses") or {}).items():
                prev = prev_status.get(key)
                if prev and cur != prev:
                    eid = f"nrc-status:{key}:{prev}->{cur}"
                    add_event(eid, message(
                        f"NRC 문서 심사 상태 변경: {key}",
                        prev, cur, "", "인허가",
                        "다음 NRC review milestone과 Combined License 실제 제출 여부",
                        "U.S. NRC", NRC_URL,
                    ))
        state["nrc"] = current
    except Exception as exc:
        errors.append(f"NRC 조회 실패: {exc}")

    try:
        raw = fetch(DOE_URL)
        fetched += 1
        text, _ = parse_page(raw)
        current = extract_doe_state(text)
        previous = state["doe"]
        if not first_run and previous:
            for key in ["criticality", "fuel_loading", "full_power"]:
                if current.get(key) and not previous.get(key):
                    if key == "criticality":
                        fact = "DOE 공식 페이지에서 Deep Fission의 실제 임계 도달이 확인됨"
                        prev, cur, nxt = "임계 미도달", "임계 도달", "출력시험·후속 DOE authorization·NRC 상업허가"
                    elif key == "fuel_loading":
                        fact = "DOE 공식 페이지에서 Deep Fission의 실제 fuel loading이 확인됨"
                        prev, cur, nxt = "연료 장전 전", "연료 장전 착수/완료", "criticality·안전시험"
                    else:
                        fact = "DOE 공식 페이지에서 Deep Fission의 full-power milestone이 확인됨"
                        prev, cur, nxt = "전출력 전", "전출력 milestone", "상업운전 전환·NRC 허가"
                    add_event(f"doe:{key}", message(
                        fact, prev, cur, "", "실증", nxt, "U.S. DOE", DOE_URL,
                    ))
        state["doe"] = current
    except Exception as exc:
        errors.append(f"DOE 조회 실패: {exc}")

    try:
        raw = fetch(PARSONS_URL)
        fetched += 1
        text, _ = parse_page(raw)
        current = extract_parsons_state(text)
        previous = state["parsons"]
        if not first_run and previous:
            for key, meta in MILESTONE_META.items():
                if key not in current:
                    continue
                if current.get(key) and not previous.get(key):
                    fact, prev, cur, stage, _axes_unused, nxt, url, source = meta
                    add_event(f"parsons:{key}", message(
                        fact, prev, cur, "", stage, nxt, source, url,
                    ))
        state["parsons"] = current
    except Exception as exc:
        errors.append(f"Parsons 조회 실패: {exc}")

    if first_run:
        events = []
        in_run_ids.clear()

    state["sent_event_ids"] = (state["sent_event_ids"] + sorted(in_run_ids))[-500:]
    PENDING.write_text(json.dumps(state, ensure_ascii=False, indent=2, sort_keys=True), encoding="utf-8")

    if events:
        ALERT.write_text("\n\n---\n\n".join(events[:8]) + "\n", encoding="utf-8")

    if errors:
        ERRORS.write_text("\n".join(errors) + "\n", encoding="utf-8")

    STATUS.write_text(
        "# Deep Fission v3 감시 상태\n"
        f"- 확인 시각: {kst_now()}\n"
        f"- 원천 조회 수: {fetched}\n"
        f"- 신규 알림 수: {len(events)}\n"
        f"- 최초 기준선: {'예' if first_run else '아니오'}\n"
        f"- 오류 수: {len(errors)}\n"
        "- 판정 방식: raw HTML hash 미사용, 공식 신규 문서/semantic milestone transition만 사용\n",
        encoding="utf-8",
    )
    print(f"deep_fission_v3_fetched={fetched}")
    print(f"deep_fission_v3_events={len(events)}")
    print(f"deep_fission_v3_errors={len(errors)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
