#!/usr/bin/env python3
"""Final readability/dedup layer for the physical-AI Telegram watcher."""
from __future__ import annotations

import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import physical_ai_watch_extensions as ext

base = ext.base
_orig_same_event = ext._same_event
_orig_meaning = ext.meaning
_orig_risk = ext.risk
_orig_verification = ext.verification


def _raw_category(text: str, group: str) -> str:
    if group == "battery":
        if re.search(r"유일로보틱스|Yuil Robotics", text, re.I) and re.search(r"SK온|SK On", text, re.I):
            return "공동개발·고객 검증"
        if re.search(r"에코프로|EcoPro", text, re.I):
            return "소재·양산 준비"
    return ext._raw_category(text, group)


def category(text: str, group: str) -> str:
    return f"{ext._lane_label(group)} · {_raw_category(text, group)}"


def meaning(cat: str) -> str:
    raw = cat.split(" · ", 1)[-1]
    if raw == "공동개발·고객 검증":
        return "SK온의 전고체 배터리 기술이 유일로보틱스 휴머노이드 적용으로 연결되는 단계입니다. 실제 셀 규격·시제품 성능·현장 검증 일정이 확정 수요로 이어지는지 봅니다."
    if raw == "소재·양산 준비":
        return "에코프로가 휴머노이드를 하이니켈·전고체 소재의 신규 수요처로 명시한 신호입니다. 고체전해질 양산 준비가 고객 채택과 실제 소재 출하로 이어지는지가 핵심입니다."
    return _orig_meaning(cat)


def risk(cat: str) -> str:
    raw = cat.split(" · ", 1)[-1]
    if raw == "공동개발·고객 검증":
        return "공동개발은 양산계약과 다릅니다. 셀당 와트시·작동시간·안전성·인증·실제 로봇 투입 대수가 확인되지 않으면 매출 시점이 늦어질 수 있습니다."
    if raw == "소재·양산 준비":
        return "소재 양산 준비와 휴머노이드향 확정 발주는 다릅니다. 고객 실명·채택량·양산 수율·고체전해질 실제 출하량을 확인해야 합니다."
    return _orig_risk(cat)


def _has(text: str, pattern: str) -> bool:
    return bool(re.search(pattern, text or "", re.I))


def same_event(a: dict, b: dict) -> bool:
    if _orig_same_event(a, b):
        return True
    if a.get("group") != b.get("group"):
        return False

    ta = f"{a.get('title','')} {a.get('description','')}"
    tb = f"{b.get('title','')} {b.get('description','')}"
    entities = ext._entity_features(ta) & ext._entity_features(tb)

    # EcoPro's humanoid-battery strategy was rewritten into several headlines
    # (high-nickel, all-solid-state, robot-first market). Treat as one event.
    if a.get("group") == "battery" and "ecopro" in entities:
        theme = r"휴머노이드|로봇|배터리|전고체|고체전해질|하이니켈|삼원계"
        if _has(ta, theme) and _has(tb, theme):
            return True

    # The CEO share reduction disclosure and the 100bn-won club block deal are
    # two descriptions of the same ROBOTIS ownership event.
    if a.get("group") == "robotis" and "robotis" in entities:
        block = r"블록딜|클럽딜|외국계\s*2곳|1000\s*억|1,?000\s*억"
        stake = r"36만\s*6525|366,?525|21\.1[89]%|지분율\s*21|김병수"
        if (_has(ta, block) and _has(tb, stake)) or (_has(tb, block) and _has(ta, stake)):
            return True

    return False


# Install the final overrides. ext._dedupe_events resolves _same_event dynamically.
ext._same_event = same_event
ext.category = category
ext.meaning = meaning
ext.risk = risk
base.category = category
base.meaning = meaning
base.risk = risk

if __name__ == "__main__":
    base.main()
