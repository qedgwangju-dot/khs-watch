#!/usr/bin/env python3
"""Improve readability of nuclear / Westinghouse policy Telegram alerts.

The formatter is presentation-only: it preserves source content, separates
confirmed facts from reporting/expectations, and moves the decision summary to
the top without changing watcher trigger logic.
"""

from __future__ import annotations

import re


NUCLEAR_TERMS = (
    "원전", "원자로", "원자력", "smr", "ap1000", "ap300", "apr1400",
    "westinghouse", "웨스팅하우스", "nuclear", "uranium", "우라늄",
)

SOURCE_PREFIXES = (
    "- 출처:", "- 원문/출처:", "- 원문:", "- 기사:", "- 근거:",
    "• 출처:", "• 원문/출처:", "• 원문:", "• 기사:", "• 근거:",
)

SECTION_ALIASES = {
    "change": (
        "지금 무엇이 달라졌나", "무엇이 달라졌나", "이번에 달라진 것", "핵심 변화",
        "신규 변화", "변경 사항",
    ),
    "verdict": ("현재 판정", "한눈에 보기", "현재 상태", "판정"),
    "investment": ("투자 의미", "왜 중요한가", "의미", "시장 의미"),
    "confirmed": ("확정 사실·숫자", "확정 사실", "확정 당사자", "확인된 사실", "확인 근거"),
    "unconfirmed": ("미확정", "확인 필요", "아직 미확정", "보도 단계"),
    "bottleneck": ("핵심 병목", "병목", "리스크", "주의할 점", "실패모드"),
    "trigger": ("다음 실제 트리거", "다음 확인", "후속 확인", "체크포인트"),
    "evidence": ("원문 근거", "기사별 확인", "원문", "근거 기사", "출처"),
}

CONFIRMED_HINTS = (
    "공식 발표", "공식 확인", "공식 부인", "계약 체결", "계약 서명", "합의 체결",
    "mou 체결", "loi 체결", "실사 착수", "due diligence", "본협상 개시",
    "협상 착수", "우선협상", "텀시트", "term sheet", "지분율", "인수가격",
    "매각가격", "출자액", "투자금", "의결권", "voting rights", "cfius 승인",
    "nrc 승인", "승인 완료", "인가 완료", "사업권 확정", "설계권 확정",
    "조달권 확정", "시공권 확정",
)
UNCONFIRMED_HINTS = (
    "검토", "가능성", "전망", "보도", "논의", "협의", "추진", "제안", "관측",
    "설", "미확정", "확인 필요", "교차검증", "검토 단계", "언론 보도",
)
INVESTMENT_HINTS = (
    "투자", "수혜", "매출", "실적", "이익", "마진", "수주", "밸류체인",
    "한국장", "주가", "현금흐름", "epc", "기자재", "공급망",
)
NUMBER_HINTS = (
    "금액", "규모", "용량", "기수", "gw", "mw", "억달러", "달러", "조원",
    "억원", "%", "퍼센트", "지분", "원전 10기", "원전 8기", "원전 4기",
)
BOTTLENECK_HINTS = (
    "병목", "리스크", "실패", "주의", "인허가", "규제", "지연", "보증",
    "현지화", "조달", "fid", "feed", "cfius", "nrc", "지식재산", "입찰 제한",
    "책임", "보험", "공급 부족",
)
TRIGGER_HINTS = (
    "다음 확인", "후속", "트리거", "공식 발표", "공시", "계약", "mou", "loi",
    "실사", "협상", "승인", "인가", "지분율", "인수가격", "의결권", "사업권",
)


def _clean_line(line: str) -> str:
    line = re.sub(r"\s+", " ", str(line or "")).strip()
    line = re.sub(r"^[•]\s*", "- ", line)
    return line


def _plain(value: str) -> str:
    value = re.sub(r"<[^>]+>", "", str(value or ""))
    value = value.replace("**", "").replace("__", "").replace("`", "")
    value = re.sub(r"^[#\-•\s]+", "", value)
    return re.sub(r"\s+", " ", value).strip()


def _has_any(text: str, needles: tuple[str, ...]) -> bool:
    low = _plain(text).lower()
    return any(needle.lower() in low for needle in needles)


def _dedupe(lines: list[str]) -> list[str]:
    seen: set[str] = set()
    output: list[str] = []
    for raw in lines:
        line = _clean_line(raw)
        key = re.sub(r"[^0-9a-z가-힣]+", "", _plain(line).lower())
        if not key or key in seen:
            continue
        seen.add(key)
        output.append(line)
    return output


def _split_section_prefix(line: str) -> tuple[str | None, str]:
    plain = _plain(line)
    for section, aliases in SECTION_ALIASES.items():
        for alias in sorted(aliases, key=len, reverse=True):
            if plain == alias or plain == alias + ":":
                return section, ""
            match = re.match(rf"^{re.escape(alias)}\s*[:：]\s*(.+)$", plain, re.I)
            if match:
                return section, match.group(1).strip()
    return None, ""


def _is_source(line: str) -> bool:
    stripped = line.strip()
    return stripped.startswith(SOURCE_PREFIXES) or "<a href=" in stripped.lower()


def _extract_news_count(text: str) -> int | None:
    match = re.search(r"신규\s*보도\s*[:·|]?\s*(\d+)\s*건", _plain(text), re.I)
    return int(match.group(1)) if match else None


def _extract_confirmed_count(text: str) -> int | None:
    match = re.search(r"신규\s*확정\s*사실\s*[:·|]?\s*(\d+)\s*건", _plain(text), re.I)
    return int(match.group(1)) if match else None


def _derive_verdict(buckets: dict[str, list[str]], combined: str) -> str:
    verdict_lines = _dedupe(buckets["verdict"])
    if verdict_lines:
        value = _plain(verdict_lines[0])
        value = re.sub(r"^(?:현재\s*)?판정\s*[:：]?\s*", "", value)
        if value:
            return value

    low = _plain(combined).lower()
    if any(term in low for term in ("공식 부인", "공식 정정", "사실과 다름")):
        return "공식 부인·정정 확인"
    if any(term in low for term in CONFIRMED_HINTS):
        return "확정 사실 또는 거래 단계 진전 신호 확인"
    if any(term in low for term in UNCONFIRMED_HINTS):
        return "보도·검토 단계 — 공식 거래조건 확인 전"
    return "추가 확인 필요"


def _infer_confirmed_count(buckets: dict[str, list[str]], combined: str) -> int:
    explicit = _extract_confirmed_count(combined)
    if explicit is not None:
        return explicit
    strong = [line for line in buckets["confirmed"] if _has_any(line, CONFIRMED_HINTS)]
    return len(_dedupe(strong)) if strong else 0


def restructure_nuclear_message(title: str, body: str) -> tuple[str, str]:
    """Reorder nuclear-related alerts into a decision-first Telegram layout."""
    combined = f"{title}\n{body}"
    if not any(term.lower() in combined.lower() for term in NUCLEAR_TERMS):
        return title, body

    # Idempotence: direct formatter + runtime wrapper may both call this function.
    if all(marker in body for marker in ("📌 현재 판정", "▶ 이번에 달라진 것", "🔗 원문 근거")):
        return title, body

    title_plain = _plain(title)
    lines = [_clean_line(line) for line in str(body or "").splitlines() if _clean_line(line)]
    if not lines:
        return title, body

    buckets: dict[str, list[str]] = {
        "change": [], "verdict": [], "investment": [], "confirmed": [],
        "unconfirmed": [], "bottleneck": [], "trigger": [], "evidence": [], "detail": [],
    }
    current: str | None = None

    for line in lines:
        if _plain(line) == title_plain:
            continue
        if _is_source(line):
            buckets["evidence"].append(line)
            current = None
            continue

        section, inline_value = _split_section_prefix(line)
        if section:
            if inline_value:
                buckets[section].append("- " + inline_value)
                current = None
            else:
                current = section
            continue

        if current:
            buckets[current].append(line)
            continue

        if _has_any(line, CONFIRMED_HINTS):
            buckets["confirmed"].append(line)
        elif _has_any(line, UNCONFIRMED_HINTS):
            buckets["unconfirmed"].append(line)
        elif _has_any(line, BOTTLENECK_HINTS):
            buckets["bottleneck"].append(line)
        elif _has_any(line, INVESTMENT_HINTS):
            buckets["investment"].append(line)
        elif _has_any(line, NUMBER_HINTS):
            buckets["confirmed"].append(line)
        elif _has_any(line, TRIGGER_HINTS):
            buckets["trigger"].append(line)
        else:
            buckets["detail"].append(line)

    for key in buckets:
        buckets[key] = _dedupe(buckets[key])

    if not buckets["change"]:
        lead = buckets["detail"][:3]
        buckets["change"].extend(lead)
        buckets["detail"] = buckets["detail"][len(lead):]

    # Keep the first screen compact, but never discard detail: overflow moves below.
    if len(buckets["change"]) > 3:
        buckets["detail"] = buckets["change"][3:] + buckets["detail"]
        buckets["change"] = buckets["change"][:3]
    if len(buckets["investment"]) > 2:
        buckets["detail"] = buckets["investment"][2:] + buckets["detail"]
        buckets["investment"] = buckets["investment"][:2]

    news_count = _extract_news_count(combined)
    confirmed_count = _infer_confirmed_count(buckets, combined)
    verdict = _derive_verdict(buckets, combined)

    sections: list[str] = [f"📌 현재 판정: {verdict}"]
    if news_count is not None:
        sections.append(f"📰 신규 보도: {news_count}건 | ✅ 신규 확정 사실: {confirmed_count}건")
    else:
        sections.append(f"✅ 신규 확정 사실: {confirmed_count}건")
    sections.append("")

    def add_section(name: str, values: list[str]) -> None:
        values = _dedupe(values)
        if not values:
            return
        sections.extend([name, *values, ""])

    add_section("▶ 이번에 달라진 것", buckets["change"])
    add_section("💰 투자 의미", buckets["investment"])
    add_section("✅ 확정 사실·숫자", buckets["confirmed"])
    add_section("❓ 미확정", buckets["unconfirmed"])
    add_section("⚠️ 핵심 병목", buckets["bottleneck"])
    add_section("⏭ 다음 실제 트리거", buckets["trigger"])
    add_section("📎 상세 근거", buckets["detail"])
    add_section("🔗 원문 근거", buckets["evidence"])

    return title, "\n".join(sections).strip() + "\n"


__all__ = ["restructure_nuclear_message"]
