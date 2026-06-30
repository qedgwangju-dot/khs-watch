#!/usr/bin/env python3
"""Final delivery guard for KHS Telegram alert files.

This runs after all lane-specific renderers and before GitHub issues/Telegram.
It blocks low-impact notices and raw detector-language leaks at the delivery
boundary so a single renderer regression cannot reach Telegram.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

OUT_DIR = Path("out")


@dataclass(frozen=True)
class Lane:
    name: str
    title: Path
    body: Path
    json: Path | None = None


LANES = [
    Lane(
        "policy",
        OUT_DIR / "khs_policy_watch_alert_title.txt",
        OUT_DIR / "khs_policy_watch_alert.md",
        OUT_DIR / "khs_policy_watch_alerts.json",
    ),
    Lane(
        "korea_personnel",
        OUT_DIR / "khs_korea_presidential_personnel_title.txt",
        OUT_DIR / "khs_korea_presidential_personnel_alert.md",
        OUT_DIR / "khs_korea_presidential_personnel_alerts.json",
    ),
    Lane(
        "nuclear_policy",
        OUT_DIR / "khs_nuclear_policy_title.txt",
        OUT_DIR / "khs_nuclear_policy_alert.md",
        OUT_DIR / "khs_nuclear_policy_alerts.json",
    ),
    Lane(
        "trusted_policy_news",
        OUT_DIR / "khs_trusted_policy_news_title.txt",
        OUT_DIR / "khs_trusted_policy_news_alert.md",
        OUT_DIR / "khs_trusted_policy_news_alerts.json",
    ),
]

LOW_IMPACT_BLOCKERS = [
    "sunshine act meetings",
    "open commission meeting",
    "open commission meetings",
    "sunshine notice",
    "digital opportunity data collection",
    "modernizing the fcc form 477 data program",
    "delete, delete, delete",
    "television broadcasting services",
    "continuation of the national emergency",
    "nominations & appointments",
    "nominations sent to the senate",
    "nomination sent to the senate",
    "sent to the senate",
]

FEDERAL_REGISTER_BOILERPLATE_BLOCKERS = [
    "this document is also available in the following formats",
    "json normalized attributes and metadata",
    "json [normalized attributes and metadata",
    "xml original full text xml",
    "xml [original full text xml",
    "mods government publishing office metadata",
    "mods [government publishing office metadata",
    "normalized attributes and metadata",
    "original full text xml",
    "government publishing office metadata",
    "developer tools pages",
    "federalregister.gov/api/v1/documents",
    "federalregister.gov/documents/full_text/xml",
    "govinfo.gov/metadata/granule",
]

RAW_DETECTOR_BLOCKERS = [
    "fcc_decision_notice",
    "agency_order",
    "permit_restart",
    "presidential_action",
    "korea_presidential_personnel",
    "sanctions_tariffs_export",
    "court_order",
    "final_rule",
    "company_filing",
    "fda_decision",
    "whitehouse_alerts=",
    "policy_guardrails=",
]

VISIBLE_ENGLISH_BLOCKERS = [
    "Federal Register FCC",
    "Federal Register presidential documents",
    "Federal Register tariffs",
    "Federal Register chips export",
    "Federal Register transformers",
    "Federal Register energy",
    "Federal Register Commerce national security",
    "Federal Register DOE FERC NRC power",
    "White House Executive Order",
    "White House Fact Sheet",
    "White House Presidential Memorandum",
    "commission meeting",
    "proposed rule",
    "notice of proposed rulemaking",
    "further notice of proposed rulemaking",
    "customs enforcement",
    "executive order",
    "presidential memorandum",
]

REQUIRED_EXPLANATION_FIELDS = [
    "- 핵심 내용:",
    "- 투자 관점:",
    "- 한국장 영향:",
    "- 실패 신호:",
]

REPLACEMENTS = {
    "[Federal Register FCC]": "[미 연방관보 FCC]",
    "[Federal Register presidential documents]": "[미 연방관보 대통령문서]",
    "[Federal Register tariffs]": "[미 연방관보 관세]",
    "[Federal Register chips export]": "[미 연방관보 반도체·수출통제]",
    "[Federal Register transformers]": "[미 연방관보 변압기]",
    "[Federal Register energy]": "[미 연방관보 에너지]",
    "[Federal Register Commerce national security]": "[미 연방관보 상무부·국가안보]",
    "[Federal Register DOE FERC NRC power]": "[미 연방관보 에너지·전력·원전]",
    "[White House Executive Order]": "[백악관 행정명령]",
    "[White House Fact Sheet]": "[백악관 팩트시트]",
    "[White House Presidential Memorandum]": "[백악관 대통령각서]",
    "fcc_decision_notice": "FCC 결정·회의 공지",
    "agency_order": "기관 명령/규칙",
    "permit_restart": "인허가·임대 재개",
    "presidential_action": "대통령 정책문서",
    "sanctions_tariffs_export": "제재·관세·수출통제",
    "commission meeting": "공개위원회 회의",
    "proposed rule": "규칙 제안",
    "notice of proposed rulemaking": "규칙 제안 공고",
    "further notice of proposed rulemaking": "추가 규칙 제안 공고",
    "customs enforcement": "통관 집행",
    "executive order": "행정명령",
    "presidential memorandum": "대통령각서",
}


def remove_urls(text: str) -> str:
    return re.sub(r"https?://\S+", "", text)


def normalize_for_match(text: str) -> str:
    text = text.lower()
    text = re.sub(r"[_\-/%?=&.,:;()\[\]{}]+", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def mostly_ascii(value: str) -> bool:
    letters = [ch for ch in value if ch.isalpha()]
    if not letters:
        return False
    ascii_letters = [ch for ch in letters if ord(ch) < 128]
    return len(ascii_letters) / max(len(letters), 1) >= 0.75


def sanitize(text: str) -> str:
    for old, new in REPLACEMENTS.items():
        text = text.replace(old, new)
    return text


def read_pair(lane: Lane) -> tuple[str, str]:
    title = lane.title.read_text(encoding="utf-8") if lane.title.exists() else ""
    body = lane.body.read_text(encoding="utf-8") if lane.body.exists() else ""
    return title, body


def write_pair(lane: Lane, title: str, body: str) -> None:
    if lane.title.exists():
        lane.title.write_text(title, encoding="utf-8")
    if lane.body.exists():
        lane.body.write_text(body, encoding="utf-8")


def delete_lane(lane: Lane, reason: str) -> None:
    for path in (lane.title, lane.body, lane.json):
        if path and path.exists():
            path.unlink()
    print(f"telegram_delivery_guard=blocked lane={lane.name} reason={reason}")


def has_blocker(text: str, blockers: list[str], include_urls: bool) -> str | None:
    haystack = text if include_urls else remove_urls(text)
    low = haystack.lower()
    normalized = normalize_for_match(haystack)
    for marker in blockers:
        marker_low = marker.lower()
        marker_normalized = normalize_for_match(marker)
        if marker_low in low or marker_normalized in normalized:
            return marker
    return None


def has_raw_ascii_heading(body: str) -> bool:
    for line in body.splitlines():
        if not line.startswith("## "):
            continue
        visible = re.sub(r"^##\s+\d+\.\s+\[[^\]]+\]\s*", "", line).strip()
        if mostly_ascii(visible):
            return True
    return False


def guard_lane(lane: Lane) -> None:
    if not lane.body.exists():
        return

    title, body = read_pair(lane)
    title = sanitize(title)
    body = sanitize(body)
    combined = f"{title}\n{body}"

    marker = has_blocker(combined, LOW_IMPACT_BLOCKERS, include_urls=True)
    if marker:
        delete_lane(lane, f"low_impact:{marker}")
        return

    marker = has_blocker(combined, FEDERAL_REGISTER_BOILERPLATE_BLOCKERS, include_urls=True)
    if marker:
        delete_lane(lane, f"federal_register_boilerplate:{marker}")
        return

    visible = remove_urls(combined)
    marker = has_blocker(visible, RAW_DETECTOR_BLOCKERS, include_urls=False)
    if marker:
        delete_lane(lane, f"raw_detector:{marker}")
        return

    marker = has_blocker(visible, VISIBLE_ENGLISH_BLOCKERS, include_urls=False)
    if marker:
        delete_lane(lane, f"raw_english:{marker}")
        return

    if lane.name == "policy" and has_raw_ascii_heading(body):
        delete_lane(lane, "raw_ascii_policy_heading")
        return

    for marker in REQUIRED_EXPLANATION_FIELDS:
        if marker not in body:
            delete_lane(lane, f"missing_explanation_field:{marker}")
            return

    write_pair(lane, title, body)
    print(f"telegram_delivery_guard=passed lane={lane.name}")


def main() -> int:
    for lane in LANES:
        guard_lane(lane)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
