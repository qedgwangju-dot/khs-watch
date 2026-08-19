#!/usr/bin/env python3
"""Operational runner for yen policy-news alerts with source-fidelity guardrails."""

from __future__ import annotations

import re
import sys

import yen_policy_news_alert as base

WSJ_MARKERS = (
    "wall street journal",
    "the wall street journal",
    "wsj",
    "wsj.com",
    "dow jones newswires",
)

FORECAST_MARKERS = (
    "has chance to",
    "could",
    "may",
    "might",
    "strategist",
    "analyst",
    "forecast",
    "forecasts",
    "expects",
    "expectation",
    "hsbc",
    "전망",
    "예상",
    "가능성",
)

KOREAN_MODAL_MARKERS = (
    "가능",
    "기회",
    "전망",
    "예상",
    "수 있",
    "할 수",
)

# Exact, high-impact headlines that previously exposed a modality/attribution risk.
VERIFIED_LITERAL_TRANSLATIONS = {
    "boj has chance to support yen with september rate hike":
        "BOJ는 9월 금리 인상으로 엔화를 지지할 기회가 있다",
}

_original_source_group = base.source_group
_original_classify = base.classify
_original_translate_headline = base.translate_headline_to_korean
_original_build_message = base.build_message


def _contains(text: str, markers: tuple[str, ...]) -> bool:
    lowered = (text or "").lower()
    return any(marker in lowered for marker in markers)


def _normalized_headline(value: str) -> str:
    return base.normalize_text(value)


def source_group(source: str, full_text: str) -> str:
    if _contains(f"{source} {full_text}", WSJ_MARKERS):
        return "Wall Street Journal"
    return _original_source_group(source, full_text)


def classify(item: base.NewsItem) -> base.ClassifiedItem | None:
    result = _original_classify(item)
    if result is None:
        return None
    if result.topic == "BOJ 9월 인상 기대·신호" and _contains(item.text, FORECAST_MARKERS):
        return base.ClassifiedItem(
            item=result.item,
            topic="BOJ 9월 인상 전망·시장 기대",
            material_score=result.material_score,
            source_level=result.source_level,
            source_group=result.source_group,
        )
    return result


def translate_headline_to_korean(
    title: str,
    source: str,
    topic: str,
    current,
) -> tuple[str, str]:
    """Translate without upgrading possibility/forecast wording into a fact."""
    headline = base.clean_headline(title, source)
    normalized = _normalized_headline(headline)
    literal = VERIFIED_LITERAL_TRANSLATIONS.get(normalized)
    if literal:
        return literal, "verified_literal"

    translated, status = _original_translate_headline(title, source, topic, current)

    # A modal headline must remain modal in Korean. If the machine translation
    # drops that distinction, use a conservative Korean summary rather than a
    # stronger factual statement.
    if _contains(headline, ("has chance to", "could", "may", "might")) and not _contains(
        translated, KOREAN_MODAL_MARKERS
    ):
        if (
            "boj" in normalized
            and "september" in normalized
            and "rate hike" in headline.lower()
            and "yen" in normalized
        ):
            return "BOJ의 9월 금리 인상으로 엔화를 지지할 가능성에 관한 전망", "fidelity_fallback"
        return base.fallback_korean_headline(topic), "fidelity_fallback"
    return translated, status


def _source_nature(topic: str, rank: int) -> str:
    if "전망·시장 기대" in topic:
        return "시장 전망·분석 — BOJ 공식 결정이나 확정 신호 아님"
    if rank >= 3:
        return "공식자료·당국 발언"
    if "기대·신호" in topic:
        return "주요매체 보도·시장 신호 — 공식 결정 여부는 별도 확인"
    return "주요매체 보도 — 사실관계와 공식 확인 여부를 분리"


def build_message(selected, current):
    """Make source translation and our market interpretation visibly separate."""
    title, body, payload = _original_build_message(selected, current)
    rows = body.splitlines()
    output: list[str] = []
    item_index = -1
    interpretation_label_added = False
    axis_pattern = re.compile(r"^(?:수급|할인율|돈 버는 능력|시간표):")

    for line in rows:
        if re.match(r"^\d+\)\s", line):
            item_index += 1
            interpretation_label_added = False
            output.append(line)
            continue

        if line.startswith("헤드라인: "):
            output.append("원문 번역: " + line[len("헤드라인: "):])
            output.append("확인 범위: 원문 헤드라인·Google News RSS 요약 기준")
            if 0 <= item_index < len(selected):
                classified, rank, _groups = selected[item_index]
                output.append(f"원문 성격: {_source_nature(classified.topic, rank)}")
            continue

        if axis_pattern.match(line) and not interpretation_label_added:
            output.append("시장 해석(원문 외 연결):")
            interpretation_label_added = True

        output.append(line)

    for index, item_payload in enumerate(payload.get("items") or []):
        item_payload["evidence_scope"] = "headline_and_google_news_rss_summary"
        item_payload["source_translation_separated_from_market_interpretation"] = True
        if index < len(selected):
            classified, rank, _groups = selected[index]
            item_payload["source_nature"] = _source_nature(classified.topic, rank)

    payload["fidelity_policy"] = {
        "translation": "preserve modality, timing, actor and attribution from source",
        "interpretation": "market interpretation is labeled separately and must not be presented as source text",
        "full_text_rule": "do not infer article-body details when only headline/RSS summary is available",
    }
    return title, "\n".join(output), payload


def install() -> None:
    if not any("Wall Street Journal" in query for _lang, query in base.RSS_QUERIES):
        base.RSS_QUERIES = base.RSS_QUERIES + (
            ("en", '"Bank of Japan" September rate hike yen "Wall Street Journal"'),
            ("en", 'BOJ September rate hike support yen WSJ'),
        )
    for marker in WSJ_MARKERS:
        if marker not in base.MAJOR_SOURCE_MARKERS:
            base.MAJOR_SOURCE_MARKERS = base.MAJOR_SOURCE_MARKERS + (marker,)
    base.source_group = source_group
    base.classify = classify
    base.translate_headline_to_korean = translate_headline_to_korean
    base.build_message = build_message


install()


def main() -> int:
    return base.main()


if __name__ == "__main__":
    sys.exit(main())
