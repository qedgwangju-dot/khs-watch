#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import html
import json
import os
import re
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, Iterable, List, Tuple
from urllib.parse import urljoin, urlparse

import requests
from bs4 import BeautifulSoup

ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = ROOT / "data"
OUT_DIR = ROOT / "out"
STATE_PATH = DATA_DIR / "janus_watch_state.json"
PENDING_STATE_PATH = OUT_DIR / "janus_watch_state_pending.json"
ALERT_PATH = OUT_DIR / "janus_alert.html"
STATUS_PATH = OUT_DIR / "janus_status.md"
ERROR_PATH = OUT_DIR / "janus_errors.log"
CONNECTION_TEST_PATH = OUT_DIR / "janus_connection_test.html"

UA = os.getenv("JANUS_WATCH_USER_AGENT", "KHS-Janus-Watch/1.0 (+GitHub Actions)")
TIMEOUT = 25

SOURCES = [
    {
        "name": "미 육군 Janus 공식 허브",
        "url": "https://www.army.mil/ASAIEE",
        "kind": "official",
    },
    {
        "name": "미 육군 Janus 계약 발표",
        "url": "https://www.army.mil/article/294891/army_reaches_agreement_with_private_industry_for_nuclear_micro_reactors",
        "kind": "official_detail",
    },
    {
        "name": "미 전쟁부 Janus 발표",
        "url": "https://www.war.gov/News/News-Stories/Article/Article/4584583/army-selects-vendors-sites-for-nuclear-microreactors/",
        "kind": "official_detail",
    },
    {
        "name": "Antares Nuclear 업데이트",
        "url": "https://antaresindustries.com/updates",
        "kind": "vendor",
    },
    {
        "name": "BWXT 뉴스",
        "url": "https://www.bwxt.com/media/news/",
        "kind": "vendor",
    },
    {
        "name": "General Atomics Janus 발표",
        "url": "https://www.ga.com/ga-microreactor-selected-for-us-army-janus-program",
        "kind": "vendor_detail",
    },
    {
        "name": "Radiant 뉴스",
        "url": "https://www.radiantnuclear.com/news",
        "kind": "vendor",
    },
    {
        "name": "Westinghouse 뉴스",
        "url": "https://info.westinghousenuclear.com/news",
        "kind": "vendor",
    },
    {
        "name": "Fort Drum Janus 공식 페이지",
        "url": "https://home.army.mil/drum/about/news/news-archives-august-2026/fort-drum-selected-janus-program",
        "kind": "official_detail",
    },
]

# Janus 자체, 5개 초기 기지, 공급망/연료, 각 선정 제품명을 중심으로 노이즈를 줄인다.
RELEVANCE_TERMS = [
    "janus",
    "microreactor",
    "micro-reactor",
    "fort bragg",
    "fort campbell",
    "fort hood",
    "fort benning",
    "fort drum",
    "kaleidos",
    "evinci",
    "ga-tes",
    "triso",
    "haleu",
    "criticality",
    "fuel supply",
    "fuel agreement",
    "uranium",
]

HIGH_SIGNAL_TERMS = [
    "award",
    "agreement",
    "contract",
    "selected",
    "selection",
    "milestone",
    "funding",
    "construction",
    "construct",
    "site planning",
    "siting",
    "permit",
    "regulatory",
    "authorization",
    "approval",
    "criticality",
    "fuel",
    "triso",
    "haleu",
    "uranium",
    "manufactur",
    "factory",
    "deploy",
    "operation",
    "commercial",
    "delay",
    "cancel",
    "termination",
    "schedule",
    "timeline",
]

VENDOR_HOSTS = {
    "antaresindustries.com",
    "www.bwxt.com",
    "bwxt.com",
    "www.ga.com",
    "ga.com",
    "www.radiantnuclear.com",
    "radiantnuclear.com",
    "info.westinghousenuclear.com",
    "westinghousenuclear.com",
}

SELECTED_PAIRS = [
    ("Antares Nuclear", "Fort Bragg"),
    ("BWXT Advanced Technologies", "Fort Campbell"),
    ("General Atomics Electromagnetic Systems", "Fort Hood"),
    ("Radiant Industries", "Fort Benning"),
    ("Westinghouse Government Services", "Fort Drum"),
]


def now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def norm(text: str) -> str:
    return re.sub(r"\s+", " ", text or "").strip()


def fingerprint(source: str, title: str, url: str) -> str:
    payload = f"{source}\n{norm(title).lower()}\n{url.strip()}".encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def fetch(url: str) -> str:
    r = requests.get(
        url,
        headers={
            "User-Agent": UA,
            "Accept-Language": "en-US,en;q=0.8",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        },
        timeout=TIMEOUT,
    )
    r.raise_for_status()
    return r.text


def is_relevant(title: str, href: str, source_kind: str) -> bool:
    hay = f"{title} {href}".lower()
    if not any(term in hay for term in RELEVANCE_TERMS):
        return False

    # 공식 Army/DoW 페이지의 Janus 링크는 그대로 허용한다.
    if source_kind.startswith("official") and any(
        term in hay
        for term in ["janus", "microreactor", "micro-reactor", "fort bragg", "fort campbell", "fort hood", "fort benning", "fort drum"]
    ):
        return True

    # 업체 페이지는 Janus/마이크로원자로/선정 제품 또는 연료·공급망 + 고신호 조합만 허용한다.
    if any(term in hay for term in ["janus", "microreactor", "micro-reactor", "kaleidos", "evinci", "ga-tes"]):
        return True
    return any(term in hay for term in ["triso", "haleu", "fuel supply", "fuel agreement", "criticality", "uranium"]) and any(
        term in hay for term in HIGH_SIGNAL_TERMS
    )


def extract_items(source: Dict[str, str], page_html: str) -> List[Dict[str, str]]:
    soup = BeautifulSoup(page_html, "html.parser")
    items: List[Dict[str, str]] = []
    seen_local = set()
    for a in soup.find_all("a", href=True):
        title = norm(a.get_text(" ", strip=True))
        if len(title) < 8:
            continue
        href = urljoin(source["url"], a.get("href", ""))
        if not href.startswith("http"):
            continue
        if not is_relevant(title, href, source["kind"]):
            continue
        key = (title.lower(), href)
        if key in seen_local:
            continue
        seen_local.add(key)
        items.append(
            {
                "source": source["name"],
                "title": title[:500],
                "url": href,
                "kind": source["kind"],
            }
        )
    return items


def fact_snapshot(page_text: str) -> Dict[str, List[str]]:
    text = norm(page_text)
    low = text.lower()
    facts: Dict[str, List[str]] = {}

    money = sorted(set(re.findall(r"\$\s?\d+(?:\.\d+)?\s*(?:billion|million)", text, flags=re.I)))
    if money:
        facts["금액"] = money

    deadlines = sorted(set(re.findall(r"(?:September\s+30,\s+2028|by\s+2028|no later than\s+September\s+30,\s+2028)", text, flags=re.I)))
    if deadlines:
        facts["일정"] = deadlines

    counts = sorted(set(re.findall(r"(?:more than|over|up to)\s+\d+\s+(?:total\s+)?(?:nuclear\s+)?microreactors?", text, flags=re.I)))
    if counts:
        facts["물량"] = counts

    pairs = []
    for vendor, site in SELECTED_PAIRS:
        if vendor.lower() in low and site.lower() in low:
            pairs.append(f"{vendor} - {site}")
    if pairs:
        facts["선정 당사자"] = sorted(pairs)

    return facts


def load_state() -> Dict:
    if not STATE_PATH.exists():
        return {"version": 1, "seen": [], "facts": {}, "initialized": False}
    try:
        return json.loads(STATE_PATH.read_text(encoding="utf-8"))
    except Exception:
        return {"version": 1, "seen": [], "facts": {}, "initialized": False}


def classify(title: str) -> str:
    t = title.lower()
    if any(x in t for x in ["fuel", "triso", "haleu", "uranium"]):
        return "공급망·연료"
    if any(x in t for x in ["fort ", "site", "siting", "location"]):
        return "기지·입지"
    if any(x in t for x in ["criticality", "approval", "permit", "authorization", "regulatory"]):
        return "인허가·기술 일정"
    if any(x in t for x in ["award", "agreement", "contract", "funding", "selected", "selection"]):
        return "계약·예산"
    if any(x in t for x in ["construct", "manufactur", "factory", "deploy", "operation", "schedule", "timeline", "delay"]):
        return "제작·배치 일정"
    return "Janus 핵심 변화"


def meaning(category: str) -> str:
    return {
        "공급망·연료": "HALEU·TRISO 등 연료 확보는 2028년 배치 일정의 핵심 병목 후보입니다.",
        "기지·입지": "초기 5개 기지 이후 후속 배치 확대 여부와 실제 설치 물량에 직접 연결됩니다.",
        "인허가·기술 일정": "Army 규제 승인과 임계·시험 일정은 2028년 운전 목표의 실현 가능성을 바꿉니다.",
        "계약·예산": "마일스톤 계약금·민간자금·업체별 확정 물량이 실제 매출 연결 강도를 결정합니다.",
        "제작·배치 일정": "공장·제작·현장 공정 진척은 매출 인식과 실제 전원 인가 시점을 앞당기거나 늦춥니다.",
        "Janus 핵심 변화": "공식 Janus 사업 범위·당사자·일정 변화로 후속 수주와 공급망 수요를 재평가할 사안입니다.",
    }.get(category, "Janus 사업의 계약·일정·공급망·후속 배치에 영향을 줄 수 있는 변화입니다.")


def render_alert(events: List[Dict[str, str]], fact_changes: List[Dict[str, str]]) -> str:
    lines = ["<b>[Janus 웹감시] 신규 변화</b>", ""]
    for event in events[:12]:
        cat = classify(event["title"])
        lines.extend(
            [
                f"• <b>분류:</b> {html.escape(cat)}",
                f"• <b>출처:</b> {html.escape(event['source'])}",
                f"• <b>새 사실:</b> {html.escape(event['title'])}",
                f"• <b>의미:</b> {html.escape(meaning(cat))}",
                f"• <a href=\"{html.escape(event['url'], quote=True)}\">원문</a>",
                "",
            ]
        )
    for fc in fact_changes[:6]:
        lines.extend(
            [
                "• <b>분류:</b> 공식 핵심 수치·당사자 변경",
                f"• <b>출처:</b> {html.escape(fc['source'])}",
                f"• <b>변경:</b> {html.escape(fc['summary'])}",
                f"• <a href=\"{html.escape(fc['url'], quote=True)}\">원문</a>",
                "",
            ]
        )
    total = len(events) + len(fact_changes)
    shown = min(len(events), 12) + min(len(fact_changes), 6)
    if total > shown:
        lines.append(f"• 추가 {total-shown}건은 다음 실행에서 상태와 함께 계속 추적")
    return "\n".join(lines).strip()


def diff_facts(old: Dict, new: Dict) -> str:
    parts = []
    for key in sorted(set(old) | set(new)):
        if old.get(key) != new.get(key):
            parts.append(f"{key}: {old.get(key, [])} → {new.get(key, [])}")
    return "; ".join(parts)


def run_check() -> int:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    for p in [ALERT_PATH, STATUS_PATH, ERROR_PATH, CONNECTION_TEST_PATH, PENDING_STATE_PATH]:
        try:
            p.unlink()
        except FileNotFoundError:
            pass

    state = load_state()
    initialized = bool(state.get("initialized"))
    seen = set(state.get("seen") or [])
    old_facts = state.get("facts") or {}
    current_facts: Dict[str, Dict] = {}
    all_items: List[Dict[str, str]] = []
    errors: List[str] = []
    sources_ok = 0

    for source in SOURCES:
        try:
            page = fetch(source["url"])
            sources_ok += 1
            soup = BeautifulSoup(page, "html.parser")
            text = soup.get_text(" ", strip=True)
            items = extract_items(source, page)
            all_items.extend(items)
            if source["kind"] in {"official_detail", "vendor_detail"}:
                current_facts[source["name"]] = fact_snapshot(text)
        except Exception as exc:
            errors.append(f"{source['name']} | {source['url']} | {type(exc).__name__}: {exc}")

    if sources_ok == 0:
        ERROR_PATH.write_text("\n".join(errors), encoding="utf-8")
        STATUS_PATH.write_text("# Janus 웹감시\n\n- 결과: 실패\n- 성공 출처: 0\n", encoding="utf-8")
        return 2

    deduped: Dict[str, Dict[str, str]] = {}
    for item in all_items:
        fp = fingerprint(item["source"], item["title"], item["url"])
        item["fp"] = fp
        deduped[fp] = item

    current_fps = set(deduped)
    new_events = [deduped[fp] for fp in sorted(current_fps - seen)] if initialized else []

    fact_changes: List[Dict[str, str]] = []
    if initialized:
        for source in SOURCES:
            name = source["name"]
            if name not in current_facts:
                continue
            old = old_facts.get(name, {})
            new = current_facts.get(name, {})
            if old and new and old != new:
                summary = diff_facts(old, new)
                if summary:
                    fact_changes.append({"source": name, "summary": summary[:1200], "url": source["url"]})

    if new_events or fact_changes:
        ALERT_PATH.write_text(render_alert(new_events, fact_changes), encoding="utf-8")

    if not initialized:
        CONNECTION_TEST_PATH.write_text(
            "\n".join(
                [
                    "<b>[Janus 웹감시] 텔레그램 연결 정상</b>",
                    "",
                    "• 수신 봇: @khs8879887988798879_bot",
                    "• 확인 주기: 15분",
                    "• 감시: 미 육군·미 전쟁부 공식 Janus 발표 + 5개 선정업체 공식 뉴스",
                    "• 핵심 조건: 계약·예산, 2028 일정, Army 규제·시험, HALEU·TRISO 연료, 제작·배치, 후속 기지·업체 추가",
                    "• 현재 공개자료는 기준선으로만 저장하고 신규 변화부터 알림",
                    "• 같은 링크·같은 제목은 중복 발송하지 않음",
                ]
            ),
            encoding="utf-8",
        )

    # 현재 목록을 누적 seen에 저장해 재발송을 차단한다. 과거 상태는 최대 2000건 유지.
    merged_seen = list(dict.fromkeys(list(state.get("seen") or []) + sorted(current_fps)))
    if len(merged_seen) > 2000:
        merged_seen = merged_seen[-2000:]

    pending = {
        "version": 1,
        "initialized": True,
        "initialized_at": state.get("initialized_at") or now_iso(),
        "last_checked_at": now_iso(),
        "seen": merged_seen,
        "facts": current_facts,
        "source_count": len(SOURCES),
        "sources_ok": sources_ok,
    }
    PENDING_STATE_PATH.write_text(json.dumps(pending, ensure_ascii=False, indent=2), encoding="utf-8")

    if errors:
        ERROR_PATH.write_text("\n".join(errors), encoding="utf-8")

    status_lines = [
        "# Janus 웹감시",
        "",
        f"- 성공 출처: {sources_ok}/{len(SOURCES)}",
        f"- 기준선 항목: {len(current_fps)}",
        f"- 신규 이벤트: {len(new_events)}",
        f"- 공식 핵심 사실 변경: {len(fact_changes)}",
        f"- 부분 오류: {len(errors)}",
        f"- 기준선 초기화: {'예' if not initialized else '아니오'}",
    ]
    STATUS_PATH.write_text("\n".join(status_lines) + "\n", encoding="utf-8")
    return 0


def self_test() -> int:
    assert classify("Radiant signs TRISO fuel supply agreement") == "공급망·연료"
    assert classify("Army awards Janus contract") == "계약·예산"
    assert is_relevant("Janus Program update", "https://army.mil/x", "official")
    assert not is_relevant("Quarterly dividend", "https://example.com/x", "vendor")
    print("janus_self_test=ok")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--mode", choices=["check", "self-test"], default="check")
    args = parser.parse_args()
    return self_test() if args.mode == "self-test" else run_check()


if __name__ == "__main__":
    sys.exit(main())
