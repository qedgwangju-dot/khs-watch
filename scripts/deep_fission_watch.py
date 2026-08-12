#!/usr/bin/env python3
"""Deep Fission 핵심 변화 웹 감시기.

공식·1차 원천의 변화를 감지하되 텔레그램에는 한국어로 재구성한 문장만 보낸다.
회사명·모델명·NRC·DOE·SEC·SMR·PPA·FID처럼 식별에 필요한 표기만 원문을 허용한다.
과거 자료는 최초 실행에서 기준선으로 저장해 재탕 알림을 막는다.
"""

from __future__ import annotations

import argparse
import datetime as dt
import hashlib
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
STATE = DATA / "deep_fission_watch_state.json"
PENDING = OUT / "deep_fission_watch_state_pending.json"
ALERT = OUT / "deep_fission_alert.md"
SETUP = OUT / "deep_fission_setup.md"
STATUS = OUT / "deep_fission_status.md"
ERRORS = OUT / "deep_fission_errors.log"

UA = os.environ.get(
    "DEEP_FISSION_WATCH_USER_AGENT",
    "KHS-Deep-Fission-Watch/2.0 contact=github-actions",
)

PRESS_URL = "https://www.deepfission.com/pr-media-kit/press-releases"
REGULATORY_URL = "https://www.deepfission.com/regulatory"
PARSONS_URL = "https://www.deepfission.com/sites/parsons"
NRC_URL = "https://www.nrc.gov/reactors/new-reactors/advanced/who-were-working-with/pre-application-activities/deep-fission"
DOE_URL = "https://www.energy.gov/ne/us-department-energy-reactor-pilot-program"
SEC_SUBMISSIONS = "https://data.sec.gov/submissions/CIK0001918102.json"

PRIMARY_SOURCES = {
    "Deep Fission 규제": REGULATORY_URL,
    "캔자스주 파슨스 실증": PARSONS_URL,
    "미국 원자력규제위원회": NRC_URL,
    "미국 에너지부": DOE_URL,
}

IMPORTANT_FORMS = {"8-K", "10-Q", "10-K", "S-1", "S-1/A", "424B4", "424B3", "EFFECT"}

HIGH_SIGNAL = [
    "license", "licensing", "combined license", "standard design", "design approval",
    "application", "submitted", "accepted", "docket", "review complete", "approval",
    "approved", "authorization", "permit", "environmental impact", "eis", "nrc",
    "nuclear safety design agreement", "nsda",
    "criticality", "fuel loading", "fuel", "construction", "groundbreaking", "drilling",
    "borehole", "canister", "prototype", "full power", "power test", "thermal", "hydraulic",
    "reactor pilot", "demonstration", "milestone",
    "power purchase", "ppa", "final investment", "fid", "binding", "contract", "order",
    "customer", "gigawatt", "financing", "offering", "loan", "grant", "cash", "going concern",
    "doosan", "doosan enerbility", "soosan", "soosan e&s", "kentech", "korea institute of energy technology",
    "delay", "delayed", "lawsuit", "opposition", "groundwater", "contamination", "denied", "rejected", "shortfall",
]

KOREA_TERMS = [
    "doosan", "doosan enerbility", "soosan", "soosan e&s", "kentech",
    "korea institute of energy technology",
]
NEGATIVE_TERMS = [
    "delay", "delayed", "lawsuit", "opposition", "groundwater", "contamination",
    "denied", "rejected", "shortfall", "going concern",
]

# 텔레그램 본문에서 허용하는 식별 표기. URL은 별도 제거 후 검사한다.
ALLOWED_ASCII_WORDS = {
    "deep", "fission", "gravity", "nrc", "doe", "sec", "smr", "ppa", "fid",
    "nsda", "fisn", "mmis", "kentech", "8-k", "10-q", "10-k", "s-1", "effect",
    "mw", "mwe", "gw", "gwe", "kw",
}


class TextParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.parts: list[str] = []
        self.links: list[tuple[str, str]] = []
        self._href: str | None = None
        self._anchor_parts: list[str] = []

    def handle_starttag(self, tag: str, attrs):
        if tag.lower() == "a":
            self._href = dict(attrs).get("href")
            self._anchor_parts = []
        elif tag.lower() in {"p", "div", "li", "tr", "br", "h1", "h2", "h3", "h4", "td", "th"}:
            self.parts.append("\n")

    def handle_endtag(self, tag: str):
        if tag.lower() == "a" and self._href:
            label = " ".join(self._anchor_parts).strip()
            self.links.append((self._href, label))
            self._href = None
            self._anchor_parts = []
        elif tag.lower() in {"p", "div", "li", "tr", "h1", "h2", "h3", "h4"}:
            self.parts.append("\n")

    def handle_data(self, data: str):
        value = html.unescape(data)
        self.parts.append(value)
        if self._href is not None:
            self._anchor_parts.append(value)

    def text(self) -> str:
        raw = "".join(self.parts)
        raw = re.sub(r"[\t\r ]+", " ", raw)
        raw = re.sub(r"\n\s*\n+", "\n", raw)
        return raw.strip()


def fetch(url: str, timeout: int = 25, accept: str = "text/html,application/json") -> str:
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


def parse_html(raw: str) -> tuple[str, list[tuple[str, str]]]:
    parser = TextParser()
    parser.feed(raw)
    return parser.text(), parser.links


def normalized(value: str) -> str:
    value = html.unescape(value).lower()
    value = re.sub(r"\s+", " ", value)
    return value.strip()


def digest(value: str) -> str:
    return hashlib.sha256(normalized(value).encode("utf-8")).hexdigest()


def relevant_excerpt(text: str, keyword: str = "deep fission", radius: int = 1800) -> str:
    low = text.lower()
    indexes = [m.start() for m in re.finditer(re.escape(keyword.lower()), low)]
    if not indexes:
        return ""
    return "\n".join(text[max(0, idx - radius): idx + radius] for idx in indexes[:10])


def contains_signal(text: str) -> bool:
    low = normalized(text)
    return any(term in low for term in HIGH_SIGNAL)


def classify(text: str) -> list[str]:
    low = normalized(text)
    tags: list[str] = []
    if any(x in low for x in [
        "license", "application", "nrc", "permit", "design approval", "standard design",
        "docket", "eis", "environmental impact", "nuclear safety design agreement", "nsda",
    ]):
        tags.append("인허가")
    if any(x in low for x in [
        "doe", "reactor pilot", "criticality", "fuel loading", "full power", "demonstration",
    ]):
        tags.append("실증")
    if any(x in low for x in ["drilling", "borehole", "canister", "prototype", "parsons", "construction", "groundbreaking"]):
        tags.append("공정")
    if any(x in low for x in ["power purchase", "ppa", "contract", "order", "binding", "customer", "gigawatt", "fid"]):
        tags.append("고객·계약")
    if any(x in low for x in ["financing", "offering", "loan", "grant", "cash", "going concern"]):
        tags.append("자금조달")
    if any(x in low for x in KOREA_TERMS):
        tags.append("한국 공급망")
    if any(x in low for x in NEGATIVE_TERMS):
        tags.append("위험")
    return tags or ["기타 중요 변화"]


def press_items(raw: str) -> dict[str, str]:
    _, links = parse_html(raw)
    out: dict[str, str] = {}
    for href, label in links:
        if "/press-releases/detail/" not in href:
            continue
        url = urljoin(PRESS_URL, href)
        title = re.sub(r"\s+", " ", label).strip()
        if title and len(title) > 8:
            out[url] = title
    return out


def sec_recent() -> dict[str, dict[str, str]]:
    raw = fetch(SEC_SUBMISSIONS, accept="application/json")
    obj = json.loads(raw)
    recent = (obj.get("filings") or {}).get("recent") or {}
    accessions = recent.get("accessionNumber") or []
    forms = recent.get("form") or []
    dates = recent.get("filingDate") or []
    docs = recent.get("primaryDocument") or []
    descriptions = recent.get("primaryDocDescription") or []
    result: dict[str, dict[str, str]] = {}
    for i, accession in enumerate(accessions):
        form = forms[i] if i < len(forms) else ""
        if form not in IMPORTANT_FORMS:
            continue
        acc_nodash = accession.replace("-", "")
        doc = docs[i] if i < len(docs) else ""
        url = (
            f"https://www.sec.gov/Archives/edgar/data/1918102/{acc_nodash}/{doc}"
            if doc else "https://www.sec.gov/edgar/browse/?CIK=1918102"
        )
        result[accession] = {
            "form": form,
            "date": dates[i] if i < len(dates) else "",
            "description": descriptions[i] if i < len(descriptions) else "",
            "url": url,
        }
    return result


def load_state() -> dict:
    if not STATE.exists():
        return {}
    try:
        return json.loads(STATE.read_text(encoding="utf-8"))
    except Exception:
        return {}


def save_pending(state: dict) -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    PENDING.write_text(json.dumps(state, ensure_ascii=False, indent=2, sort_keys=True), encoding="utf-8")


def write_status(lines: list[str]) -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    STATUS.write_text("\n".join(lines).strip() + "\n", encoding="utf-8")


def _has(low: str, *phrases: str) -> bool:
    return any(p in low for p in phrases)


def korean_event_fact(text: str, source_name: str, sec_form: str = "", sec_date: str = "") -> str:
    """영문 원문을 그대로 노출하지 않고 사건을 한국어로 재구성한다."""
    low = normalized(text)
    facts: list[str] = []

    if sec_form:
        date_part = f"({sec_date})" if sec_date else ""
        facts.append(f"미국 증권거래위원회에 {sec_form} 신규 공시가 제출됨{date_part}")

    if _has(low, "nuclear safety design agreement", "nsda"):
        facts.append("원자력 안전설계협약 관련 공식 단계가 변경됨")
    if _has(low, "combined license"):
        facts.append("NRC 통합허가 관련 절차가 변경됨")
    elif _has(low, "standard design", "design approval"):
        facts.append("NRC 표준설계·설계승인 관련 절차가 변경됨")
    elif _has(low, "application", "submitted") and "nrc" in low:
        facts.append("NRC 인허가 신청·제출 관련 단계가 변경됨")
    elif _has(low, "accepted", "docket") and "nrc" in low:
        facts.append("NRC 신청서 접수·심사 착수 관련 단계가 변경됨")
    elif _has(low, "license", "permit") and "nrc" in low:
        facts.append("NRC 인허가 관련 공식 단계가 변경됨")

    if _has(low, "environmental impact", "eis"):
        facts.append("환경영향평가 관련 절차가 변경됨")
    if _has(low, "approved", "approval", "authorization"):
        facts.append("승인·허가 관련 공식 상태가 변경됨")
    if _has(low, "denied", "rejected"):
        facts.append("승인·허가가 거절되거나 부정적 결정이 확인됨")

    if _has(low, "criticality"):
        facts.append("원자로 임계 도달 관련 실증 단계가 변경됨")
    if _has(low, "fuel loading"):
        facts.append("원자로 연료 장전 관련 단계가 변경됨")
    if _has(low, "full power", "power test"):
        facts.append("전출력 시험·출력시험 관련 단계가 변경됨")
    if _has(low, "reactor pilot", "demonstration"):
        facts.append("미국 에너지부 원자로 시범·실증 프로그램 관련 단계가 변경됨")
    if _has(low, "drilling", "borehole"):
        facts.append("캔자스주 파슨스 시추·시추공 공정 관련 상태가 변경됨")
    if _has(low, "canister", "prototype"):
        facts.append("시제품 원자로 용기 설치·시험 관련 상태가 변경됨")
    if _has(low, "groundbreaking", "construction"):
        facts.append("착공·건설 공정 관련 상태가 변경됨")
    if _has(low, "thermal", "hydraulic"):
        facts.append("열수력·냉각 성능 검증 관련 상태가 변경됨")

    if _has(low, "power purchase", "ppa"):
        facts.append("전력구매계약 관련 조건 또는 계약 상태가 변경됨")
    if _has(low, "final investment", "fid"):
        facts.append("최종투자결정 관련 상태가 변경됨")
    if _has(low, "binding"):
        facts.append("구속력 있는 계약 여부에 변화가 확인됨")
    if _has(low, "contract", "order"):
        facts.append("계약·발주 관련 공식 변화가 확인됨")
    if _has(low, "customer"):
        facts.append("고객·수요처 관련 공식 변화가 확인됨")

    if _has(low, "financing", "offering"):
        facts.append("자금조달·주식발행 관련 변화가 확인됨")
    if _has(low, "loan"):
        facts.append("대출·차입 관련 변화가 확인됨")
    if _has(low, "grant"):
        facts.append("정부 보조금·지원금 관련 변화가 확인됨")
    if _has(low, "going concern"):
        facts.append("계속기업 불확실성 관련 공시 변화가 확인됨")

    if _has(low, "doosan", "doosan enerbility"):
        facts.append("두산에너빌리티가 공식 원문에 실명으로 등장함")
    if _has(low, "soosan", "soosan e&s"):
        facts.append("수산이앤에스가 공식 원문에 실명으로 등장함")
    if _has(low, "kentech", "korea institute of energy technology"):
        facts.append("한국에너지공대 관련 공식 협력 내용이 변경됨")

    if _has(low, "delay", "delayed"):
        facts.append("사업 일정 지연 신호가 확인됨")
    if _has(low, "lawsuit"):
        facts.append("소송 관련 위험 신호가 확인됨")
    if _has(low, "opposition"):
        facts.append("지역사회 반대 관련 위험 신호가 확인됨")
    if _has(low, "groundwater", "contamination"):
        facts.append("지하수·환경오염 관련 위험 신호가 확인됨")

    if not facts:
        if source_name == "미국 원자력규제위원회":
            facts.append("NRC의 Deep Fission 인허가 공식 페이지에 중요한 변경이 확인됨")
        elif source_name == "미국 에너지부":
            facts.append("미국 에너지부의 Deep Fission 관련 공식 페이지에 중요한 변경이 확인됨")
        elif source_name == "캔자스주 파슨스 실증":
            facts.append("캔자스주 파슨스 실증사업 공식 페이지에 중요한 변경이 확인됨")
        elif source_name == "미국 증권거래위원회":
            facts.append("Deep Fission의 미국 증권거래위원회 공시에 중요한 변경이 확인됨")
        else:
            facts.append("Deep Fission 공식 자료에 투자 판단상 중요한 변경이 확인됨")

    # 같은 의미의 중복 문장을 제거하고 최대 4개만 노출한다.
    return " / ".join(list(dict.fromkeys(facts))[:4])


def _axes(tags: list[str]) -> list[str]:
    axes: list[str] = []
    if any(x in tags for x in ["고객·계약", "자금조달", "한국 공급망"]):
        axes.append("돈 버는 능력")
    if any(x in tags for x in ["인허가", "실증", "위험"]):
        axes.append("할인율")
    if "자금조달" in tags:
        axes.append("수급")
    if any(x in tags for x in ["인허가", "실증", "공정", "고객·계약"]):
        axes.append("시간표")
    return list(dict.fromkeys(axes)) or ["시간표"]


def korean_summary(
    title: str,
    body: str,
    source_name: str,
    url: str,
    sec_form: str = "",
    sec_date: str = "",
) -> str:
    combined = title + "\n" + body
    tags = classify(combined)
    low = normalized(combined)
    fact = korean_event_fact(combined, source_name, sec_form=sec_form, sec_date=sec_date)

    if _has(low, "doosan", "doosan enerbility"):
        korea = "두산에너빌리티 실명 확인. 다만 공급사 선정·발주·수주 범위는 공식 원문에서 별도 확인"
    elif _has(low, "soosan", "soosan e&s"):
        korea = "수산이앤에스 실명 확인. 다만 공급사 선정·발주·수주 범위는 공식 원문에서 별도 확인"
    elif _has(low, "kentech", "korea institute of energy technology"):
        korea = "한국에너지공대 관련 공식 협력 변화 확인"
    else:
        korea = "두산에너빌리티·수산이앤에스의 신규 직접계약은 이번 변화만으로 확인되지 않음"

    if "위험" in tags:
        risk = "인허가 지연·지역사회 반대·환경 문제·자금조달 부담 중 하나가 먼저 일정에 반영될 가능성"
        early = "NRC 추가정보요구, 파슨스 공정 지연, 소송·주민반대, 현금잔고와 신규 자금조달"
    elif "자금조달" in tags:
        risk = "상업매출 발생 전 현금소진이 빨라져 추가 증자·차입이 필요해질 가능성"
        early = "분기 현금잔고, 영업현금 유출, 신규 주식발행·대출"
    else:
        risk = "규제·실증 일정이 진전돼도 상업계약과 실제 매출 연결이 지연될 가능성"
        early = "NRC 심사 일정, 실증 결과, 구속력 있는 고객계약, 실제 공급사 명단"

    message = (
        "[Deep Fission 중요 변화]\n"
        f"- 새 사실: {fact}\n"
        f"- 단계: {', '.join(tags)}\n"
        f"- 바뀐 축: {', '.join(_axes(tags))}\n"
        f"- 한국 기업 연결: {korea}\n"
        f"- 실패 경로: {risk}\n"
        f"- 먼저 볼 지표: {early}\n"
        f"- 출처: {source_name}\n"
        f"- 링크: {url}"
    )
    assert_korean_alert(message)
    return message


def assert_korean_alert(message: str) -> None:
    """식별 표기와 URL을 제외한 영문 일반 설명어가 있으면 전송을 막는다."""
    without_urls = re.sub(r"https?://\S+", "", message)
    words = re.findall(r"[A-Za-z][A-Za-z0-9&.-]*", without_urls)
    bad = []
    for word in words:
        key = word.lower().strip(".,:;()[]{}")
        if key in ALLOWED_ASCII_WORDS:
            continue
        # Deep Fission 두 단어, 서식 식별번호, 물리 단위는 허용한다.
        if re.fullmatch(r"\d+(?:-?[A-Za-z]+)", word):
            continue
        bad.append(word)
    if bad:
        raise RuntimeError("한국어 알림 검증 실패: 번역되지 않은 영문 설명어=" + ", ".join(sorted(set(bad))))


def self_test() -> None:
    sample_title = "Department of Energy approves Nuclear Safety Design Agreement for Deep Fission Gravity reactor"
    sample_body = (
        "NRC licensing application submitted. The project includes drilling, prototype canister, "
        "power purchase agreement, financing and groundwater opposition. Doosan Enerbility was mentioned."
    )
    rendered = korean_summary(sample_title, sample_body, "미국 에너지부", "https://example.com/test")
    assert "Department" not in rendered
    assert "approves" not in rendered
    assert "drilling" not in rendered
    assert "원자력 안전설계협약" in rendered
    assert "두산에너빌리티" in rendered
    assert_korean_alert(rendered)
    print("deep_fission_korean_alert_self_test=success")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--mode", default="check", choices=["check", "self-test"])
    args = parser.parse_args()
    if args.mode == "self-test":
        self_test()
        return 0

    OUT.mkdir(parents=True, exist_ok=True)
    DATA.mkdir(parents=True, exist_ok=True)
    for path in (ALERT, SETUP, ERRORS, PENDING):
        if path.exists():
            path.unlink()

    old = load_state()
    first_run = not bool(old)
    now = dt.datetime.now(dt.timezone.utc).replace(microsecond=0).isoformat()
    new_state = {
        "version": 2,
        "updated_at": now,
        "press_urls": dict(old.get("press_urls") or {}),
        "sec_filings": dict(old.get("sec_filings") or {}),
        "source_hashes": dict(old.get("source_hashes") or {}),
    }
    events: list[str] = []
    errors: list[str] = []
    fetched = 0

    # 1) Deep Fission 공식 보도자료
    try:
        raw = fetch(PRESS_URL)
        fetched += 1
        items = press_items(raw)
        for url, title in items.items():
            if url in new_state["press_urls"]:
                continue
            new_state["press_urls"][url] = title
            if first_run:
                continue
            try:
                detail_raw = fetch(url)
                fetched += 1
                body, _ = parse_html(detail_raw)
            except Exception as exc:
                errors.append(f"공식 보도자료 상세 조회 실패 {url}: {exc}")
                body = title
            if contains_signal(title + "\n" + body):
                try:
                    events.append(korean_summary(title, body, "Deep Fission 공식 보도자료", url))
                except Exception as exc:
                    errors.append(f"한국어 변환 검증 실패 {url}: {exc}")
    except Exception as exc:
        errors.append(f"공식 보도자료 목록 조회 실패: {exc}")

    # 2) 미국 증권거래위원회 공시
    try:
        filings = sec_recent()
        fetched += 1
        for accession, meta in filings.items():
            if accession in new_state["sec_filings"]:
                continue
            new_state["sec_filings"][accession] = meta
            if first_run:
                continue
            raw_text = (meta.get("description") or "") + " " + meta.get("form", "")
            try:
                events.append(korean_summary(
                    "미국 증권거래위원회 신규 공시",
                    raw_text,
                    "미국 증권거래위원회",
                    meta["url"],
                    sec_form=meta.get("form", ""),
                    sec_date=meta.get("date", ""),
                ))
            except Exception as exc:
                errors.append(f"공시 한국어 변환 검증 실패 {accession}: {exc}")
    except Exception as exc:
        errors.append(f"미국 증권거래위원회 공시 조회 실패: {exc}")

    # 3) 핵심 공식 페이지 변화
    for name, url in PRIMARY_SOURCES.items():
        try:
            raw = fetch(url)
            fetched += 1
            text, _ = parse_html(raw)
            if name == "미국 에너지부":
                watched = relevant_excerpt(text, "Deep Fission")
            elif name == "미국 원자력규제위원회":
                watched = relevant_excerpt(text, "Deep Fission") or text
            else:
                watched = text
            current_hash = digest(watched)
            prior = new_state["source_hashes"].get(name)
            new_state["source_hashes"][name] = {"hash": current_hash, "url": url, "checked_at": now}
            if first_run or not prior or prior.get("hash") == current_hash:
                continue
            if watched and contains_signal(watched):
                try:
                    events.append(korean_summary("공식 페이지 중요 변경", watched[:6000], name, url))
                except Exception as exc:
                    errors.append(f"{name} 한국어 변환 검증 실패: {exc}")
        except Exception as exc:
            errors.append(f"{name} 조회 실패: {exc}")

    if len(new_state["press_urls"]) > 120:
        new_state["press_urls"] = dict(list(new_state["press_urls"].items())[-120:])
    if len(new_state["sec_filings"]) > 120:
        new_state["sec_filings"] = dict(list(new_state["sec_filings"].items())[:120])

    save_pending(new_state)

    if first_run:
        SETUP.write_text(
            "[Deep Fission 감시] 연결 및 기준선 설정\n\n"
            "Deep Fission 지하원전 웹 감시를 시작했습니다.\n"
            "- NRC: 정식 인허가 신청·접수·심사·승인·거절\n"
            "- DOE: 후속 안전승인·건설·연료 장전·임계 도달·전출력 시험\n"
            "- 파슨스: 시추·원자로 용기 설치·열수력 시험·환경·주민 이슈\n"
            "- 미국 증권거래위원회·회사: 자금조달·구속력 있는 고객계약·최종투자결정\n"
            "- 한국 연결: 두산에너빌리티·수산이앤에스 실명 계약·공급사 선정\n"
            "- 언어 규칙: 회사명·모델명·NRC·DOE·SEC·SMR 등 식별 표기만 원문 유지하고 일반 설명은 한국어로만 전송\n"
            "기존 과거 뉴스는 알리지 않고 앞으로 새로 바뀌는 중요 사건만 전송합니다.\n",
            encoding="utf-8",
        )
        assert_korean_alert(SETUP.read_text(encoding="utf-8"))

    if events:
        deduped = list(dict.fromkeys(events))[:8]
        alert_text = "\n\n---\n\n".join(deduped) + "\n"
        assert_korean_alert(alert_text)
        ALERT.write_text(alert_text, encoding="utf-8")

    if errors:
        ERRORS.write_text("\n".join(errors) + "\n", encoding="utf-8")

    write_status([
        "# Deep Fission 감시 상태",
        f"- 확인 시각(UTC): {now}",
        f"- 원천 조회 성공 횟수: {fetched}",
        f"- 신규 중요 사건: {len(events)}건",
        f"- 오류: {len(errors)}건",
        f"- 한국어 알림 검증: {'통과' if not any('한국어 변환 검증 실패' in e for e in errors) else '실패'}",
        f"- 최초 기준선 설정: {'예' if first_run else '아니오'}",
    ])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
