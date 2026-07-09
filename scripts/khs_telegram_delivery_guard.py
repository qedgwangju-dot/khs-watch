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
MAX_TITLE_CHARS = 120
MAX_BODY_LINE_CHARS = 420
MAX_ENGLISH_WORD_RUN = 8
ALLOWED_DOMAIN_ENGLISH_TERMS = {
    "AI",
    "AMRAAM",
    "ANDURIL",
    "AP",
    "ATACMS",
    "BARRACUDA",
    "BOEING",
    "BWRX",
    "GE",
    "GRUMMAN",
    "HITACHI",
    "JV",
    "JVS",
    "LOCKHEED",
    "MQ",
    "NATO",
    "NORTHROP",
    "PAC",
    "PURL",
    "RAYTHEON",
    "RHEINMETALL",
    "RTX",
    "SAMSUNG",
    "SDB",
    "SDBI",
    "SMR",
    "STINGER",
    "TRITON",
}


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
    "petition for reconsideration",
    "petition for reconsideration of action in rulemaking proceeding",
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
    "Petition for Reconsideration",
    "Petition for Reconsideration of Action in Rulemaking Proceeding",
    "Prohibiting Importation and Marketing",
    "Previously Authorized Covered Communications Equipment",
    "Request for Comments and Notice of Public Hearing",
    "Technical Guidelines for the Production",
    "Bureau of Ocean Energy Management Seeks",
    "Federal Register FCC",
    "Federal Register presidential documents",
    "Federal Register tariffs",
    "Federal Register chips export",
    "Federal Register transformers",
    "Federal Register energy",
    "Federal Register Commerce national security",
    "Federal Register DOE FERC NRC power",
    "Federal Register DOE restrictions loans",
    "White House Executive Order",
    "White House Fact Sheet",
    "White House fact sheets",
    "White House Presidential Memorandum",
    "White House proclamations",
    "White House Remarks",
    "White House briefings statements",
    "commission meeting",
    "proposed rule",
    "notice of proposed rulemaking",
    "further notice of proposed rulemaking",
    "customs enforcement",
    "executive order",
    "presidential memorandum",
]

RAW_LINE_PREFIX_BLOCKERS = [
    "- 원제:",
    "- 원문 제목:",
    "- Original title:",
    "- Original Title:",
    "- 상태 변화:",
    "- 즉시 체크:",
]

REQUIRED_EXPLANATION_FIELDS = [
    "- 핵심 내용:",
    "- 투자 관점:",
    "- 한국장 영향:",
    "- 실패 신호:",
]

REQUIRED_EXPLANATION_FIELDS = [
    "- 핵심:",
    "- 의사결정 영향:",
    "- 투자 영향:",
    "- 한국장:",
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
    "[Federal Register DOE restrictions loans]": "[미 연방관보 DOE 대출·제한·효율규제]",
    "[White House Executive Order]": "[백악관 행정명령]",
    "[White House Fact Sheet]": "[백악관 팩트시트]",
    "[White House fact sheets]": "[백악관 팩트시트]",
    "[White House Presidential Memorandum]": "[백악관 대통령각서]",
    "[White House proclamations]": "[백악관 포고문]",
    "[White House remarks]": "[백악관 트럼프 발언]",
    "[White House briefings statements]": "[백악관 브리핑·성명]",
    "[State Department office spokesperson]": "[미 국무부 대변인실]",
    "[State Department press releases]": "[미 국무부 보도자료]",
    "fcc_decision_notice": "FCC 결정·회의 공지",
    "agency_order": "기관 명령/규칙",
    "energy_security_policy": "에너지부 전력·원전·대출/제한 정책",
    "state_smr_moc_policy": "국무부 SMR 국제협력 MOC",
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


def clip_text(value: str, limit: int) -> str:
    text = re.sub(r"\s+", " ", str(value or "")).strip()
    if len(text) <= limit:
        return text
    return text[: max(0, limit - 1)].rstrip() + "…"


def compact_body(body: str) -> str:
    compacted: list[str] = []
    for line in body.splitlines():
        if len(line) > MAX_BODY_LINE_CHARS:
            compacted.append(clip_text(line, MAX_BODY_LINE_CHARS))
        else:
            compacted.append(line)
    return "\n".join(compacted).rstrip() + ("\n" if body.endswith("\n") else "")


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


def has_raw_line_prefix(body: str) -> str | None:
    for line in body.splitlines():
        stripped = line.strip()
        for marker in RAW_LINE_PREFIX_BLOCKERS:
            if stripped.startswith(marker):
                return marker
    return None


def has_long_english_run(text: str) -> str | None:
    visible = remove_urls(text)
    for line in visible.splitlines():
        if not line.strip():
            continue
        words = [
            word
            for word in re.findall(r"\b[A-Za-z][A-Za-z'-]{2,}\b", line)
            if not is_allowed_domain_english_term(word)
        ]
        if len(words) >= MAX_ENGLISH_WORD_RUN:
            return " ".join(words[:MAX_ENGLISH_WORD_RUN])
    return None


def is_allowed_domain_english_term(word: str) -> bool:
    normalized = re.sub(r"[^A-Za-z]", "", word.upper())
    if normalized.endswith("S") and normalized[:-1] in ALLOWED_DOMAIN_ENGLISH_TERMS:
        normalized = normalized[:-1]
    return normalized in ALLOWED_DOMAIN_ENGLISH_TERMS


def policy_heading_text(line: str) -> str:
    text = re.sub(r"^##\s+\d+\.\s+\[[^\]]+\]\s*", "", line).strip()
    return normalize_for_match(text)


def duplicate_policy_heading(body: str) -> str | None:
    seen: set[str] = set()
    for line in body.splitlines():
        if not line.startswith("## "):
            continue
        heading = policy_heading_text(line)
        if not heading:
            continue
        if heading in seen:
            return heading
        seen.add(heading)
    return None


def duplicate_policy_body_signature(body: str) -> str | None:
    blocks = re.split(r"(?m)^##\s+", body)
    seen: set[str] = set()
    for block in blocks:
        if not block.strip():
            continue
        lines = []
        for line in block.splitlines():
            stripped = line.strip()
            if not stripped.startswith("- "):
                continue
            normalized = normalize_for_match(stripped)
            if not normalized or normalized.startswith(("출처", "원문 출처", "source")):
                continue
            lines.append(normalized)
        if len(lines) < 3:
            continue
        signature = "|".join(lines[:6])
        if signature in seen:
            return signature[:120]
        seen.add(signature)
    return None


def has_source_body_mismatch(title: str, body: str) -> str | None:
    combined = f"{title}\n{body}"
    low_with_urls = combined.lower()
    visible = remove_urls(combined).lower()
    visible_normalized = normalize_for_match(remove_urls(combined))

    has_boem_source = "boem.gov" in low_with_urls or re.search(r"\bboem\b", visible) is not None
    has_fcc_body = (
        re.search(r"\bfcc\b", visible) is not None
        or "federal communications commission" in visible
        or "covered communications equipment" in visible
        or "covered list" in visible
        or "inverter" in visible
        or "energy inverter" in visible
    )
    if has_boem_source and has_fcc_body:
        return "boem_source_with_fcc_body"

    has_fcc_source = (
        "federalregister.gov" in low_with_urls and "fcc" in visible
    ) or "fcc.gov" in low_with_urls
    has_boem_body = (
        "outer continental shelf space" in visible
        or "space launch" in visible
        or "launch recovery" in visible_normalized
        or "launch and recovery" in visible
    )
    if has_fcc_source and has_boem_body:
        return "fcc_source_with_boem_body"

    has_fcc_submarine_source = (
        "submarine-cable-landing-license" in low_with_urls
        or "review-of-submarine-cable-landing-license" in low_with_urls
        or "submarine cable landing license" in visible
        or "submarine cable" in visible
        or "cable landing" in visible
        or "landing license" in visible
        or "해저케이블" in visible
        or "해저 통신케이블" in visible
    )
    has_inverter_or_equipment_ban_body = (
        "energy inverter" in visible
        or "solar inverter" in visible
        or "inverter" in visible
        or "인버터" in visible
        or "전력변환장치" in visible
        or "covered communications equipment" in visible
        or (
            "covered list" in visible
            and ("importation" in visible or "marketing" in visible or "수입" in visible or "판매" in visible)
        )
    )
    if has_fcc_submarine_source and has_inverter_or_equipment_ban_body:
        return "fcc_submarine_cable_source_with_inverter_or_equipment_ban_body"

    return None


def guard_lane(lane: Lane) -> None:
    if not lane.body.exists():
        return

    title, body = read_pair(lane)
    title = clip_text(sanitize(title), MAX_TITLE_CHARS)
    body = compact_body(sanitize(body))
    combined = f"{title}\n{body}"

    marker = has_source_body_mismatch(title, body)
    if marker:
        delete_lane(lane, f"source_body_mismatch:{marker}")
        return

    marker = has_blocker(combined, LOW_IMPACT_BLOCKERS, include_urls=True)
    if marker:
        delete_lane(lane, f"low_impact:{marker}")
        return

    marker = has_blocker(combined, FEDERAL_REGISTER_BOILERPLATE_BLOCKERS, include_urls=True)
    if marker:
        delete_lane(lane, f"federal_register_boilerplate:{marker}")
        return

    visible = remove_urls(combined)

    marker = has_raw_line_prefix(body)
    if marker:
        delete_lane(lane, f"raw_line_prefix:{marker}")
        return

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

    if lane.name == "policy":
        marker = duplicate_policy_heading(body)
        if marker:
            delete_lane(lane, f"duplicate_policy_heading:{marker}")
            return
        marker = duplicate_policy_body_signature(body)
        if marker:
            delete_lane(lane, f"duplicate_policy_body:{marker}")
            return
        marker = has_long_english_run(body)
        if marker:
            delete_lane(lane, f"long_english_run:{marker}")
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
