#!/usr/bin/env python3
"""Deep Fission NRC 오탐 방지 필터.

NRC 페이지 전체 HTML/내비게이션 변화가 아니라 실제 프로젝트 핵심 상태만 비교한다.
동일 상태이면 기존 broad-hash 알림을 제거하고, 실질 변화가 있을 때만 정확한 한국어 알림으로 교체한다.
"""
from __future__ import annotations

import hashlib
import html
from html.parser import HTMLParser
import json
import pathlib
import re
import urllib.request

ROOT = pathlib.Path(__file__).resolve().parents[1]
DATA = ROOT / "data"
OUT = ROOT / "out"
STATE = DATA / "deep_fission_nrc_semantic_state.json"
PENDING = OUT / "deep_fission_nrc_semantic_state_pending.json"
ALERT = OUT / "deep_fission_alert.md"
NRC_URL = "https://www.nrc.gov/reactors/new-reactors/advanced/who-were-working-with/pre-application-activities/deep-fission"
UA = "KHS-Deep-Fission-NRC-Semantic-Watch/1.0 contact=github-actions"


class Parser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.parts: list[str] = []

    def handle_starttag(self, tag: str, attrs):
        if tag.lower() in {"p", "div", "li", "tr", "br", "h1", "h2", "h3", "h4", "td", "th"}:
            self.parts.append("\n")

    def handle_endtag(self, tag: str):
        if tag.lower() in {"p", "div", "li", "tr", "h1", "h2", "h3", "h4", "td", "th"}:
            self.parts.append("\n")

    def handle_data(self, data: str):
        self.parts.append(html.unescape(data))

    def text(self) -> str:
        raw = "".join(self.parts)
        raw = re.sub(r"[\t\r ]+", " ", raw)
        raw = re.sub(r"\n\s*\n+", "\n", raw)
        return raw.strip()


def fetch() -> str:
    req = urllib.request.Request(NRC_URL, headers={"User-Agent": UA, "Accept-Language": "en-US,en;q=0.8"})
    with urllib.request.urlopen(req, timeout=30) as r:
        raw = r.read().decode("utf-8", errors="replace")
    p = Parser()
    p.feed(raw)
    return p.text()


def one_space(value: str) -> str:
    return re.sub(r"\s+", " ", value).strip()


def capture(pattern: str, text: str) -> str:
    m = re.search(pattern, text, re.I | re.S)
    return one_space(m.group(1)) if m else ""


def status_ko(value: str) -> str:
    table = {
        "No Review Requested": "검토 요청 없음",
        "Review Complete": "검토 완료",
        "Review in Progress": "검토 진행 중",
        "Accepted": "접수 완료",
        "Docketed": "정식 접수",
    }
    return table.get(value, value)


def extract_state(text: str) -> dict:
    flat = one_space(text)
    what = capture(r"What:\s*(.*?)\s*When:", flat)
    when = capture(r"When:\s*(.*?)\s*Website:", flat)
    last_updated_matches = re.findall(r"Page Last Reviewed/Updated\s+([^\n]+)", text, re.I)
    last_updated = one_space(last_updated_matches[-1]) if last_updated_matches else ""

    activity_patterns = {
        "NRC 규제협의계획": r"NRC Regulatory Engagement Plan\s+Regulatory Engagement Plan\s+(ML\w+)\s+(No Review Requested|Review Complete|Review in Progress|Accepted|Docketed)",
        "심층 시추형 가압경수로 개념설계 검토": r"Conceptual Design Review of the Deep Borehole Pressurized Water Reactor \(DB-PWR\)\s+White Paper\s+(ML\w+)\s+(No Review Requested|Review Complete|Review in Progress|Accepted|Docketed)",
        "개념설계 설명서": r"Conceptual Design Description\s+White Paper\s+(ML\w+)\s+(No Review Requested|Review Complete|Review in Progress|Accepted|Docketed)",
    }
    activities: dict[str, dict[str, str]] = {}
    for label, pattern in activity_patterns.items():
        m = re.search(pattern, flat, re.I)
        if m:
            activities[label] = {"reference": m.group(1), "status": status_ko(m.group(2))}

    metrics = {
        "최소 시추공 지름": capture(r"minimum diameter of approximately\s*([0-9.]+\s*inches?)", flat),
        "원자로 설치 깊이": capture(r"depth of approximately\s*([0-9.]+\s*mile[s]?)", flat),
        "수압": capture(r"approximately\s*([0-9.]+\s*atm)", flat),
        "열출력": capture(r"Each reactor produces\s*([0-9.]+\s*megawatts thermal[^\)]*\))", flat),
        "전기출력": capture(r"up to\s*([0-9.]+\s*megawatts of electric power[^\)]*\))", flat),
    }
    metrics = {k: v for k, v in metrics.items() if v}

    core = {"what": what, "when": when, "activities": activities, "metrics": metrics}
    semantic_hash = hashlib.sha256(json.dumps(core, ensure_ascii=False, sort_keys=True).encode("utf-8")).hexdigest()
    return {**core, "last_updated": last_updated, "semantic_hash": semantic_hash}


def load_state() -> dict:
    if not STATE.exists():
        return {}
    try:
        return json.loads(STATE.read_text(encoding="utf-8"))
    except Exception:
        return {}


def substantive_changes(old: dict, new: dict) -> list[str]:
    changes: list[str] = []
    if old.get("what") and new.get("what") and old.get("what") != new.get("what"):
        changes.append("NRC의 인허가 절차 설명이 실제로 변경됨")
    if old.get("when") and new.get("when") and old.get("when") != new.get("when"):
        changes.append("NRC 사전협의 기간·일정 표기가 변경됨")

    old_acts = old.get("activities") or {}
    new_acts = new.get("activities") or {}
    for key in sorted(set(old_acts) | set(new_acts)):
        before = (old_acts.get(key) or {}).get("status", "미등재")
        after = (new_acts.get(key) or {}).get("status", "미등재")
        before_ref = (old_acts.get(key) or {}).get("reference", "")
        after_ref = (new_acts.get(key) or {}).get("reference", "")
        if before != after:
            changes.append(f"{key}: {before} → {after}")
        elif before_ref != after_ref and after_ref:
            changes.append(f"{key}: 심사 문서가 {after_ref}로 변경됨")

    old_metrics = old.get("metrics") or {}
    new_metrics = new.get("metrics") or {}
    for key in sorted(set(old_metrics) | set(new_metrics)):
        before = old_metrics.get(key, "미표기")
        after = new_metrics.get(key, "미표기")
        if before != after:
            changes.append(f"{key}: {before} → {after}")
    return changes


def remove_nrc_blocks(text: str) -> str:
    blocks = [b.strip() for b in text.split("\n\n---\n\n") if b.strip()]
    kept = [b for b in blocks if "- 출처: 미국 원자력규제위원회" not in b]
    return "\n\n---\n\n".join(kept).strip()


def build_precise_alert(changes: list[str], state: dict) -> str:
    change_text = " / ".join(changes[:4])
    return (
        "[Deep Fission 중요 변화]\n"
        f"- 새 사실: {change_text}\n"
        "- 단계: 인허가\n"
        "- 바뀐 축: 할인율, 시간표\n"
        "- 한국 기업 연결: 두산에너빌리티·수산이앤에스의 신규 직접계약은 이번 NRC 변화만으로 확인되지 않음\n"
        "- 실패 경로: NRC 심사에서 추가정보요구가 늘어나면 상업화 일정이 다시 지연될 가능성\n"
        "- 먼저 볼 지표: 통합허가 정식 신청, 신청서 접수, 사전협의 문서 상태, NRC 추가정보요구\n"
        f"- NRC 페이지 공식 갱신일: {state.get('last_updated') or '확인 필요'}\n"
        "- 출처: 미국 원자력규제위원회\n"
        f"- 링크: {NRC_URL}"
    )


def main() -> int:
    OUT.mkdir(parents=True, exist_ok=True)
    DATA.mkdir(parents=True, exist_ok=True)
    text = fetch()
    current = extract_state(text)
    old = load_state()

    PENDING.write_text(json.dumps(current, ensure_ascii=False, indent=2, sort_keys=True), encoding="utf-8")

    existing = ALERT.read_text(encoding="utf-8").strip() if ALERT.exists() else ""
    has_nrc_alert = "- 출처: 미국 원자력규제위원회" in existing

    # 새 필터 최초 도입 시 현재 공식상태를 기준선으로만 저장하고 broad-hash 오탐은 버린다.
    if not old:
        if has_nrc_alert:
            filtered = remove_nrc_blocks(existing)
            if filtered:
                ALERT.write_text(filtered + "\n", encoding="utf-8")
            else:
                ALERT.unlink(missing_ok=True)
        print("deep_fission_nrc_semantic_filter=baseline_no_alert")
        return 0

    changes = substantive_changes(old, current)
    if not changes:
        if has_nrc_alert:
            filtered = remove_nrc_blocks(existing)
            if filtered:
                ALERT.write_text(filtered + "\n", encoding="utf-8")
            else:
                ALERT.unlink(missing_ok=True)
        print("deep_fission_nrc_semantic_filter=no_substantive_change_suppressed")
        return 0

    # 실질 변화가 있을 때만 broad-hash 블록을 제거하고 정확한 변화 문장으로 교체한다.
    filtered = remove_nrc_blocks(existing)
    precise = build_precise_alert(changes, current)
    combined = (filtered + "\n\n---\n\n" + precise).strip() if filtered else precise
    ALERT.write_text(combined + "\n", encoding="utf-8")
    print("deep_fission_nrc_semantic_filter=precise_change_alert")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
