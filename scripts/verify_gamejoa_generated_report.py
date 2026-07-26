#!/usr/bin/env python3
"""Verify the generated GAMEJOA preopen radar before Telegram delivery."""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "out"
REPORT = OUT / "gamejoa_preopen_news_radar.md"
JSON_REPORT = OUT / "gamejoa_preopen_news_radar.json"
TITLE = OUT / "gamejoa_preopen_news_radar_title.txt"

REQUIRED_ITEM_MARKERS = [
    "- 핵심:",
    "- 출처:",
]
FIELD_LIMITS = {
    "- 핵심:": 50,
}

FORBIDDEN_TEXT = [
    "- 기준/시각:",
    "- 경로/섹터:",
    "- 투자 포인트:",
    "- 원제:",
    "- 상태 변화:",
    "- 즉시 체크:",
    "- 의사결정 영향:",
    "- 한국장:",
    "- 반영/반대:",
    "- 실패 신호:",
    "의사결정 영향 제한적",
    "공식 문서 또는 신뢰 보도에서 한국장 가격 변수 후보가 확인됐습니다.",
    "돈 버는 능력, 할인율, 수급, 시간표 중 무엇이 실제로 바뀌는지 원문과 시장 반응으로 재확인해야 합니다.",
    "한국장 직접 영향은 원문에 근거가 있는 업종과 종목군으로만 제한해 확인합니다.",
    "This document is also available in the following formats",
    "Normalized attributes and metadata",
    "Original full text XML",
    "Government Publishing Office metadata",
    "developer tools pages",
    "💡 실시간 뉴스 코멘트",
    "외화 환산:",
    "≈",
]


def mostly_ascii(value: str) -> bool:
    letters = [ch for ch in value if ch.isalpha()]
    if not letters:
        return False
    ascii_letters = [ch for ch in letters if ord(ch) < 128]
    return len(ascii_letters) / max(len(letters), 1) >= 0.7


def normalize_title(value: str) -> str:
    text = re.sub(r"^\d+\)\s+\[[^\]]+\]\s*", "", value).strip()
    text = re.sub(r"\(\d+건 묶음\)$", "", text).strip()
    text = re.sub(r"\s+", " ", text)
    return text.lower()


def item_blocks(lines: list[str]) -> list[tuple[str, list[str]]]:
    blocks: list[tuple[str, list[str]]] = []
    current_title = ""
    current: list[str] = []
    for line in lines:
        if re.match(r"^\d+\)\s+\[", line):
            if current_title:
                blocks.append((current_title, current))
            current_title = line
            current = []
        elif current_title:
            if line.startswith("💡 "):
                break
            current.append(line)
    if current_title:
        blocks.append((current_title, current))
    return blocks


def value_after(line: str, marker: str) -> str:
    return line.split(marker, 1)[1].strip() if marker in line else ""


def assert_item_quality(title: str, block: list[str], errors: list[str]) -> None:
    clean_title = normalize_title(title)
    if mostly_ascii(clean_title):
        errors.append(f"raw English item heading leaked: {title[:100]}")

    body = "\n".join(block)
    for marker in REQUIRED_ITEM_MARKERS:
        if marker not in body:
            errors.append(f"{title[:80]} missing marker {marker}")
            continue
        line = next((line for line in block if line.startswith(marker)), "")
        if marker not in {"- 출처:"} and not value_after(line, marker):
            errors.append(f"{title[:80]} has empty marker {marker}")
    for marker, limit in FIELD_LIMITS.items():
        line = next((line for line in block if line.startswith(marker)), "")
        value = value_after(line, marker)
        if len(value) > limit:
            errors.append(f"{title[:80]} {marker} exceeds {limit} chars")
        if "…" in value or re.search(r"\.{3,}", value):
            errors.append(f"{title[:80]} {marker} contains truncation")
        if re.search(r"\[[^\]]{0,60}\s*기자\]", value):
            errors.append(f"{title[:80]} {marker} contains publisher/reporter boilerplate")


def main() -> int:
    errors: list[str] = []
    if not REPORT.exists():
        errors.append(f"missing generated report: {REPORT.relative_to(ROOT)}")
    if not JSON_REPORT.exists():
        errors.append(f"missing generated JSON: {JSON_REPORT.relative_to(ROOT)}")
    if not TITLE.exists():
        errors.append(f"missing generated title: {TITLE.relative_to(ROOT)}")
    if errors:
        return fail(errors)

    text = REPORT.read_text(encoding="utf-8")
    title_text = TITLE.read_text(encoding="utf-8").strip()
    valid_title = (
        text.startswith("📰 GAMEJOA 장전 핵심 뉴스 레이더 · ")
        or text.startswith("📰 실시간 핵심 뉴스 레이더 · ")
    )
    if not valid_title:
        errors.append("report title contract broken")
    if re.search(r"^조회:\s*", text, re.MULTILINE):
        errors.append("duplicate query-time line must not be displayed")
    if title_text != text.splitlines()[0].strip():
        errors.append("title file does not match report first line")

    sys.path.insert(0, str(ROOT / "scripts"))
    import gamejoa_preopen_news_radar_fda_quality_runner as prod

    try:
        prod.runner.guard_preopen_report(text)
    except Exception as exc:  # noqa: BLE001 - this is a reporting guard
        errors.append(f"runner guard failed: {exc}")

    low = text.lower()
    for forbidden in FORBIDDEN_TEXT:
        haystack = low if forbidden.lower() == forbidden else text
        needle = forbidden if forbidden.lower() != forbidden else forbidden.lower()
        if needle in haystack:
            errors.append(f"forbidden text leaked: {forbidden}")

    lines = text.splitlines()
    blocks = item_blocks(lines)
    if re.search(r"선별:\s*핵심\s*0건", text):
        if blocks:
            errors.append("empty-radar text appears together with item blocks")
    else:
        if not blocks:
            errors.append("non-empty radar missing item blocks")
        seen_titles: set[str] = set()
        for title, block in blocks:
            key = normalize_title(title)
            if key in seen_titles:
                errors.append(f"duplicate visible item heading: {title}")
            seen_titles.add(key)
            assert_item_quality(title, block, errors)

    try:
        data = json.loads(JSON_REPORT.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        errors.append(f"generated JSON is invalid: {exc}")
    else:
        if "query_time_kst" not in data:
            errors.append("generated JSON missing query_time_kst")
        json_alerts = data.get("alerts")
        if not isinstance(json_alerts, list):
            errors.append("generated JSON alerts is not a list")
            json_alerts = []
        if blocks and not json_alerts:
            errors.append("report has item blocks but generated JSON alerts is empty")
        if len(blocks) != len(json_alerts):
            errors.append(
                f"report/JSON selected count mismatch: report={len(blocks)} json={len(json_alerts)}"
            )
        for alert in json_alerts:
            if not prod.runner.source_output_aligned(alert):
                errors.append(
                    "source/body alignment failed: "
                    f"{alert.get('source_title') or alert.get('original_news') or alert.get('news')}"
                )
            source_text = " ".join(
                str(alert.get(key) or "")
                for key in (
                    "policy_plain_summary",
                    "telegram_core_fact",
                    "source_title",
                    "original_news",
                    "news",
                )
            )
            foreign_amounts = prod.runner.extract_foreign_amounts(source_text)
            if foreign_amounts:
                conversion = alert.get("fx_conversion")
                converted = conversion.get("amounts") if isinstance(conversion, dict) else None
                if not isinstance(converted, list) or len(converted) < len(foreign_amounts):
                    errors.append(
                        "foreign-currency article missing same-run KRW conversion evidence: "
                        f"{alert.get('source_title') or alert.get('news')}"
                    )
        diagnostics = data.get("selection_diagnostics")
        if not isinstance(diagnostics, dict):
            errors.append("generated JSON missing selection_diagnostics")
        else:
            if diagnostics.get("selected_alerts") != len(json_alerts):
                errors.append(
                    "selection diagnostics count mismatch: "
                    f"diagnostics={diagnostics.get('selected_alerts')} json={len(json_alerts)}"
                )
            candidate_count = diagnostics.get("deduped_candidates")
            excluded = diagnostics.get("excluded_alerts")
            if isinstance(candidate_count, int) and candidate_count > len(json_alerts):
                if not isinstance(excluded, list) or len(excluded) < candidate_count - len(json_alerts):
                    errors.append("selection diagnostics missing excluded candidate reasons")

    if errors:
        return fail(errors)

    print("GAMEJOA generated report quality OK")
    return 0


def fail(errors: list[str]) -> int:
    for error in errors:
        print(f"GAMEJOA generated report quality error: {error}")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
