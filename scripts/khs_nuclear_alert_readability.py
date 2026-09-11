#!/usr/bin/env python3
"""Improve readability of nuclear / Westinghouse policy Telegram alerts."""

from __future__ import annotations

import re


NUCLEAR_TERMS = (
    "원전", "원자로", "원자력", "smr", "ap1000", "ap300", "apr1400",
    "westinghouse", "웨스팅하우스", "nuclear", "uranium", "우라늄",
)

SOURCE_PREFIXES = ("- 출처:", "- 원문/출처:", "- 원문:")
CORE_HINTS = (
    "핵심", "한눈에", "지금 무엇", "무엇이 달라", "현재 판정", "변화",
    "확정", "확인 근거", "알림 사유", "현재 상태",
)
NUMBER_HINTS = (
    "금액", "규모", "용량", "기수", "gw", "mw", "억달러", "달러",
    "조원", "억원", "%", "기 ", "원전 10기", "원전 8기", "원전 4기",
)
COMPANY_HINTS = (
    "당사자", "기업", "한국", "수혜", "매출", "epc", "공급", "밸류체인",
    "두산", "현대", "한전", "한수원", "삼성", "westinghouse", "웨스팅하우스",
    "brookfield", "cameco",
)
RISK_HINTS = (
    "병목", "리스크", "실패", "주의", "다음 확인", "인허가", "nrc", "규제",
    "지연", "보증", "현지화", "조달", "fid", "feed",
)


def _clean_line(line: str) -> str:
    line = re.sub(r"\s+", " ", str(line or "")).strip()
    line = re.sub(r"^[-•]\s*", "- ", line)
    return line


def _has_any(text: str, needles: tuple[str, ...]) -> bool:
    low = text.lower()
    return any(needle.lower() in low for needle in needles)


def _dedupe(lines: list[str]) -> list[str]:
    seen: set[str] = set()
    output: list[str] = []
    for line in lines:
        key = re.sub(r"[^0-9a-z가-힣]+", "", line.lower())
        if not key or key in seen:
            continue
        seen.add(key)
        output.append(line)
    return output


def restructure_nuclear_message(title: str, body: str) -> tuple[str, str]:
    """Reorder only nuclear-related alerts into a compact Telegram-first structure."""
    combined = f"{title}\n{body}".lower()
    if not any(term.lower() in combined for term in NUCLEAR_TERMS):
        return title, body

    raw_lines = [_clean_line(line) for line in str(body or "").splitlines()]
    lines = [line for line in raw_lines if line]
    if not lines:
        return title, body

    core: list[str] = []
    numbers: list[str] = []
    companies: list[str] = []
    risks: list[str] = []
    sources: list[str] = []
    other: list[str] = []

    for line in lines:
        stripped = line.strip()
        if stripped.startswith(SOURCE_PREFIXES):
            sources.append(line)
        elif _has_any(line, CORE_HINTS):
            core.append(line)
        elif _has_any(line, NUMBER_HINTS):
            numbers.append(line)
        elif _has_any(line, COMPANY_HINTS):
            companies.append(line)
        elif _has_any(line, RISK_HINTS):
            risks.append(line)
        else:
            other.append(line)

    core = _dedupe(core + other[:2])[:5]
    numbers = _dedupe(numbers)[:5]
    companies = _dedupe(companies)[:5]
    risks = _dedupe(risks)[:5]
    sources = _dedupe(sources)[:5]

    sections: list[str] = []
    if core:
        sections.extend(["핵심 변화", *core])
    if numbers:
        sections.extend(["", "숫자·사업규모", *numbers])
    if companies:
        sections.extend(["", "한국 기업·매출 연결", *companies])
    if risks:
        sections.extend(["", "병목·다음 확인", *risks])
    if sources:
        sections.extend(["", "원문", *sources])

    result = "\n".join(sections).strip() + "\n"
    return title, result


__all__ = ["restructure_nuclear_message"]
