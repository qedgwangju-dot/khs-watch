#!/usr/bin/env python3
"""Deep Fission high-signal web watcher.

Monitors official/primary sources and emits a Telegram-ready Korean alert only when
there is a genuinely new, investment-relevant development. Historical items are
baselined on first run so the watcher does not spam old news.
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
    "KHS-Deep-Fission-Watch/1.0 contact=github-actions",
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
    # licensing / regulatory
    "license", "licensing", "combined license", "standard design", "design approval",
    "application", "submitted", "accepted", "docket", "review complete", "approval",
    "approved", "authorization", "permit", "environmental impact", "eis", "nrc",
    # DOE / physical milestones
    "criticality", "fuel loading", "fuel", "construction", "groundbreaking", "drilling",
    "borehole", "canister", "prototype", "full power", "power test", "thermal", "hydraulic",
    "reactor pilot", "demonstration", "milestone",
    # commercial / financing
    "power purchase", "ppa", "final investment", "fid", "binding", "contract", "order",
    "customer", "gigawatt", "financing", "offering", "loan", "grant", "cash", "going concern",
    # Korea supply-chain linkage
    "doosan", "doosan enerbility", "soosan", "soosan e&s", "kentech", "korea",
]

KOREA_TERMS = ["doosan", "doosan enerbility", "soosan", "soosan e&s", "kentech", "korea"]
NEGATIVE_TERMS = ["delay", "delayed", "lawsuit", "opposition", "groundwater", "contamination", "denied", "rejected", "shortfall", "going concern"]


class TextParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.parts: list[str] = []
        self.links: list[tuple[str, str]] = []
        self._href: str | None = None
        self._anchor_parts: list[str] = []

    def handle_starttag(self, tag: str, attrs):
        if tag.lower() == "a":
            attrs_d = dict(attrs)
            self._href = attrs_d.get("href")
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
        s = html.unescape(data)
        self.parts.append(s)
        if self._href is not None:
            self._anchor_parts.append(s)

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
    raise RuntimeError(f"fetch failed {url}: {last}")


def parse_html(raw: str) -> tuple[str, list[tuple[str, str]]]:
    p = TextParser()
    p.feed(raw)
    return p.text(), p.links


def normalized(s: str) -> str:
    s = html.unescape(s).lower()
    s = re.sub(r"\s+", " ", s)
    return s.strip()


def digest(s: str) -> str:
    return hashlib.sha256(normalized(s).encode("utf-8")).hexdigest()


def relevant_excerpt(text: str, keyword: str = "deep fission", radius: int = 1800) -> str:
    low = text.lower()
    indexes = [m.start() for m in re.finditer(re.escape(keyword.lower()), low)]
    if not indexes:
        return ""
    chunks = []
    for idx in indexes[:10]:
        chunks.append(text[max(0, idx - radius): idx + radius])
    return "\n".join(chunks)


def contains_signal(text: str) -> bool:
    low = normalized(text)
    return any(term in low for term in HIGH_SIGNAL)


def classify(text: str) -> list[str]:
    low = normalized(text)
    tags = []
    if any(x in low for x in ["license", "application", "nrc", "permit", "design approval", "docket", "eis"]):
        tags.append("인허가")
    if any(x in low for x in ["doe", "reactor pilot", "criticality", "fuel loading", "full power", "demonstration"]):
        tags.append("실증")
    if any(x in low for x in ["drilling", "borehole", "canister", "prototype", "parsons"]):
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
        url = f"https://www.sec.gov/Archives/edgar/data/1918102/{acc_nodash}/{doc}" if doc else "https://www.sec.gov/edgar/browse/?CIK=1918102"
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


def korean_summary(title: str, body: str, source_name: str, url: str) -> str:
    tags = classify(title + "\n" + body)
    low = normalized(title + " " + body)
    axis = []
    if any(x in tags for x in ["고객·계약", "자금조달", "한국 공급망"]):
        axis.append("돈 버는 능력")
    if any(x in tags for x in ["인허가", "실증", "위험"]):
        axis.append("할인율")
    if any(x in tags for x in ["인허가", "실증", "공정", "고객·계약"]):
        axis.append("시간표")
    if "자금조달" in tags:
        axis.append("수급")
    axis = list(dict.fromkeys(axis)) or ["시간표"]

    korea = ""
    if any(x in low for x in ["doosan", "doosan enerbility"]):
        korea += "\n- 한국 연결: 두산에너빌리티 실명 등장 — 직접 계약 범위를 원문에서 재확인 필요"
    if any(x in low for x in ["soosan", "soosan e&s"]):
        korea += "\n- 한국 연결: 수산이앤에스 실명 등장 — 직접 계약 범위를 원문에서 재확인 필요"
    if "kentech" in low or "korea institute of energy technology" in low:
        korea += "\n- 한국 연결: 한국에너지공대 관련 업데이트"
    if not korea:
        korea = "\n- 한국 연결: 두산에너빌리티·수산이앤에스 신규 직접계약은 이 사건만으로 확인되지 않음"

    risk = "규제·실증·자금조달 일정이 실제 상업매출보다 먼저 움직일 수 있음"
    if "위험" in tags:
        risk = "일정 지연·환경/주민 반대·자금조달 중 하나가 먼저 악화될 가능성"

    return (
        f"[Deep Fission 중요 변화]\n"
        f"- 새 사실: {title.strip()}\n"
        f"- 분류: {', '.join(tags)}\n"
        f"- 바뀐 축: {', '.join(axis)}"
        f"{korea}\n"
        f"- 실패 경로: {risk}\n"
        f"- 출처: {source_name}\n"
        f"- 링크: {url}"
    )


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--mode", default="check", choices=["check"])
    args = parser.parse_args()
    del args

    OUT.mkdir(parents=True, exist_ok=True)
    DATA.mkdir(parents=True, exist_ok=True)
    for p in (ALERT, SETUP, ERRORS, PENDING):
        if p.exists():
            p.unlink()

    old = load_state()
    first_run = not bool(old)
    now = dt.datetime.now(dt.timezone.utc).replace(microsecond=0).isoformat()
    new_state = {
        "version": 1,
        "updated_at": now,
        "press_urls": dict(old.get("press_urls") or {}),
        "sec_filings": dict(old.get("sec_filings") or {}),
        "source_hashes": dict(old.get("source_hashes") or {}),
    }
    events: list[str] = []
    errors: list[str] = []
    fetched = 0

    # 1) Official Deep Fission press releases.
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
                errors.append(f"press detail {url}: {exc}")
                body = title
            if contains_signal(title + "\n" + body):
                events.append(korean_summary(title, body, "Deep Fission 공식 보도자료", url))
    except Exception as exc:
        errors.append(f"press list: {exc}")

    # 2) SEC filings.
    try:
        filings = sec_recent()
        fetched += 1
        for accession, meta in filings.items():
            if accession in new_state["sec_filings"]:
                continue
            new_state["sec_filings"][accession] = meta
            if first_run:
                continue
            title = f"SEC {meta['form']} 신규 공시 ({meta['date']})"
            body = meta.get("description") or meta["form"]
            events.append(korean_summary(title, body, "미국 증권거래위원회", meta["url"]))
    except Exception as exc:
        errors.append(f"SEC submissions: {exc}")

    # 3) Primary pages where a meaningful change itself matters.
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
            h = digest(watched)
            prior = new_state["source_hashes"].get(name)
            new_state["source_hashes"][name] = {"hash": h, "url": url, "checked_at": now}
            if first_run or not prior or prior.get("hash") == h:
                continue
            if watched and contains_signal(watched):
                if name == "미국 원자력규제위원회":
                    title = "NRC Deep Fission 인허가 페이지가 변경됨"
                elif name == "미국 에너지부":
                    title = "DOE 원자로 시범 프로그램의 Deep Fission 항목이 변경됨"
                elif name == "캔자스주 파슨스 실증":
                    title = "파슨스 실증사업 현장 업데이트가 변경됨"
                else:
                    title = "Deep Fission 규제·인허가 공식 페이지가 변경됨"
                events.append(korean_summary(title, watched[:5000], name, url))
        except Exception as exc:
            errors.append(f"{name}: {exc}")

    # Cap retained history so state remains small.
    if len(new_state["press_urls"]) > 120:
        new_state["press_urls"] = dict(list(new_state["press_urls"].items())[-120:])
    if len(new_state["sec_filings"]) > 120:
        new_state["sec_filings"] = dict(list(new_state["sec_filings"].items())[:120])

    save_pending(new_state)

    if first_run:
        SETUP.write_text(
            "[Deep Fission 감시] 연결 및 기준선 설정\n\n"
            "Deep Fission 지하원전 웹 감시를 시작했습니다.\n"
            "- NRC: 정식 인허가 신청·접수·심사·승인/거절\n"
            "- DOE: 후속 안전승인·건설·연료장전·임계·전출력 시험\n"
            "- 파슨스: 시추·원자로 용기 설치·열수력 시험·환경/주민 이슈\n"
            "- SEC/회사: 자금조달·구속력 있는 고객계약·최종투자결정\n"
            "- 한국 연결: 두산에너빌리티·수산이앤에스 실명 계약/공급사 선정\n"
            "기존 과거 뉴스는 알리지 않고 앞으로 새로 바뀌는 중요 사건만 전송합니다.\n",
            encoding="utf-8",
        )

    if events:
        # Dedupe same-run repeated primary-page echoes by exact rendered text.
        deduped = list(dict.fromkeys(events))[:8]
        ALERT.write_text("\n\n---\n\n".join(deduped) + "\n", encoding="utf-8")

    if errors:
        ERRORS.write_text("\n".join(errors) + "\n", encoding="utf-8")

    write_status([
        "# Deep Fission 감시 상태",
        f"- 확인 시각(UTC): {now}",
        f"- 원천 조회 성공 횟수: {fetched}",
        f"- 신규 중요 사건: {len(events)}건",
        f"- 오류: {len(errors)}건",
        f"- 최초 기준선 설정: {'예' if first_run else '아니오'}",
    ])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
