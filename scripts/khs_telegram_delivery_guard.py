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

try:
    from khs_compact_text import MAX_PROSE_CHARS
except ImportError:  # pragma: no cover - supports module-style local tests.
    from scripts.khs_compact_text import MAX_PROSE_CHARS

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

REQUIRED_EXPLANATION_FIELD_GROUPS = [
    ("- 핵심 내용:", "- 핵심:"),
    ("- 의사결정 영향:",),
    ("- 투자 관점:", "- 투자 영향:"),
    ("- 한국장 영향:", "- 한국장:"),
    ("- 실패 신호:",),
]

URL_TOPIC_REQUIREMENTS = [
    (
        ("defense-supply-chains", "domestic-acquisition-of-critical-materials"),
        ("방산", "국방", "핵심소재", "핵심 소재", "공급망", "critical materials"),
        "source_topic_missing:defense_critical_materials",
    ),
    (
        ("additional-tariffs-on-canada", "canadian-discrimination"),
        ("캐나다", "관세", "추가 50%", "50% 관세", "section 338"),
        "source_topic_missing:canada_tariffs",
    ),
    (
        ("imports-of-aluminum", "primary-aluminum"),
        ("알루미늄", "제련", "232조", "section 232"),
        "source_topic_missing:aluminum_onshoring",
    ),
    (
        ("trade-deal-with-jordan", "kingdom-of-jordan-on-reciprocal-trade"),
        ("요르단", "상호무역", "무역협정", "reciprocal trade"),
        "source_topic_missing:jordan_trade",
    ),
    (
        ("submarine-cable", "cable-landing-license", "submarine cable"),
        ("해저케이블", "해저 통신케이블", "케이블 착륙", "submarine cable", "cable landing", "landing license"),
        "source_topic_missing:submarine_cable",
    ),
    (
        ("covered-communications-equipment", "covered communications equipment"),
        ("통신장비", "보안장비", "수입", "판매", "covered communications equipment", "covered list", "importation", "marketing"),
        "source_topic_missing:covered_communications_equipment",
    ),
    (
        ("defense-investment-from-nato", "nato-allies-powering-american-industry"),
        ("nato", "방위", "방산", "동맹", "defense", "american industry", "purl", "pac-3", "amraam"),
        "source_topic_missing:nato_defense_investment",
    ),
    (
        ("small-modular-reactor", "smr"),
        ("smr", "소형모듈원전", "소형 모듈 원전", "원전", "reactor", "nuclear"),
        "source_topic_missing:smr",
    ),
    (
        ("quantum-innovation", "advanced-cryptographic-attacks"),
        ("양자", "암호", "cryptographic", "quantum", "post-quantum"),
        "source_topic_missing:quantum_crypto",
    ),
    (
        ("regenerative-agriculture", "farm-resilience"),
        ("농업", "농식품", "농장", "regenerative agriculture", "farm", "agriculture"),
        "source_topic_missing:agriculture",
    ),
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


COMPACT_PROSE_PREFIXES = (
    "- 핵심:",
    "- 핵심 내용:",
    "- 핵심 근거:",
    "- 확인 근거:",
    "- 투자 관점:",
    "- 투자 영향:",
    "- 투자 포인트:",
    "- 한국장:",
    "- 한국장 영향:",
    "- 실패 신호:",
)


def oversized_compact_prose(body: str) -> str | None:
    for line in body.splitlines():
        stripped = line.strip()
        for prefix in COMPACT_PROSE_PREFIXES:
            if stripped.startswith(prefix):
                value = stripped.removeprefix(prefix).strip()
                if len(value) > MAX_PROSE_CHARS:
                    return f"{prefix}{len(value)}"
        if stripped.startswith("- 반영/반대:"):
            value = stripped.removeprefix("- 반영/반대:").strip()
            for part in value.split(" / ", 1):
                if len(part.strip()) > MAX_PROSE_CHARS:
                    return f"- 반영/반대:{len(part.strip())}"
    return None


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

    has_bok_generic_source = any(
        marker in low_with_urls
        for marker in (
            "bok.or.kr/portal/submain/submain/fnncsafety.do",
            "bok.or.kr/portal/submain/submain/crncypolicy.do",
            "bok.or.kr/portal/submain/submain/cbdc.do",
            "bok.or.kr/portal/bbs/b0000232/list.do",
        )
    )
    has_stablecoin_policy_body = any(
        marker in combined
        for marker in (
            "스테이블코인",
            "원화 스테이블코인",
            "예금 대체",
            "준비자산",
            "상환청구권",
            "발행 주체",
            "가상자산 2단계",
            "디지털자산기본법",
        )
    )
    if has_bok_generic_source and has_stablecoin_policy_body:
        return "bok_generic_page_with_stablecoin_policy_body"

    for url_markers, required_terms, reason in URL_TOPIC_REQUIREMENTS:
        if any(marker in low_with_urls for marker in url_markers) and not any(term in visible for term in required_terms):
            return reason

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

    marker = oversized_compact_prose(body)
    if marker:
        delete_lane(lane, f"compact_prose_too_long:{marker}")
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

    for markers in REQUIRED_EXPLANATION_FIELD_GROUPS:
        if not any(marker in body for marker in markers):
            delete_lane(lane, f"missing_explanation_field:{markers[0]}")
            return

    write_pair(lane, title, body)
    print(f"telegram_delivery_guard=passed lane={lane.name}")


def main() -> int:
    for lane in LANES:
        guard_lane(lane)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
