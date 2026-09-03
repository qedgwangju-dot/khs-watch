#!/usr/bin/env python3
"""LNG 공급·전략 촉매 감시 v12.

v11의 탐지·검증·가독성 규칙을 유지하면서 영문 뉴스 노출을 차단한다.
- 영문 기사 제목은 반드시 한국어 번역 후 송출한다.
- 번역이 실패하거나 영문 서술어가 남으면 한국어 사건 요약으로 대체한다.
- 영문 매체명은 한국어 매체명으로 바꾸고, 미등록 해외 매체는 '해외 매체'로 표시한다.
- LNG·TTF·JKM·FID·EPC·SPA·MOU 같은 표준 약어만 예외적으로 허용한다.
"""

from __future__ import annotations

import html
import re

import lng_supply_crisis_alert_v2 as core
import lng_supply_crisis_alert_v11 as v11


v8 = v11.v10.v9.v8
_base_translate_title_ko = v8.translate_title_ko

ALLOWED_TECHNICAL_ASCII = {
    "LNG", "JKM", "TTF", "EU", "GIE", "IEA", "AP", "BBC", "CNBC", "S&P",
    "FID", "EPC", "SPA", "MOU", "LOI",
}

POST_TRANSLATION_REPLACEMENTS = (
    ("Force Majeure", "불가항력 선언"),
    ("force majeure", "불가항력 선언"),
    ("Brent", "브렌트"),
    ("Alaska", "알래스카"),
    ("Trump", "트럼프"),
    ("South Korea", "한국"),
    ("S. Korea", "한국"),
    ("Korea", "한국"),
    ("Japan", "일본"),
    ("QatarEnergy", "카타르에너지"),
    ("Qatar Energy", "카타르에너지"),
    ("Qatar", "카타르"),
    ("Strait of Hormuz", "호르무즈 해협"),
    ("Hormuz", "호르무즈"),
    ("Red Sea", "홍해"),
    ("United States", "미국"),
    ("U.S.", "미국"),
    ("US", "미국"),
)


def _contains_untranslated_prose(text: str) -> bool:
    scrubbed = text
    for token in sorted(ALLOWED_TECHNICAL_ASCII, key=len, reverse=True):
        scrubbed = scrubbed.replace(token, "")
    return bool(re.search(r"[A-Za-z]{2,}", scrubbed))


def translate_title_ko_strict(item: core.NewsItem) -> str:
    translated = _base_translate_title_ko(item).strip()
    for before, after in POST_TRANSLATION_REPLACEMENTS:
        translated = translated.replace(before, after)

    # 번역 결과에 일반 영문 문구가 남아 있으면 원문을 노출하지 않고 한국어 요약으로 대체한다.
    if not translated or _contains_untranslated_prose(translated):
        translated = v8.fallback_korean_title(item)

    return translated


def build_regular_alert_v12(groups, quotes, new_signals, cleared_signals):
    title, body, metadata = v11.build_regular_alert_v11(
        groups, quotes, new_signals, cleared_signals
    )

    # 방어적 최종검사: 'LNG' 같은 표준 약어는 허용하되, 영문 문장형 원제목이 그대로 들어가면 차단한다.
    for group in groups:
        for item in group.get("evidence", []):
            raw_title = str(item.title).strip()
            if _contains_untranslated_prose(raw_title):
                if html.escape(raw_title) in body or raw_title in body:
                    raise RuntimeError("영문 기사 원제목 노출 감지: Telegram 송출 차단")

    metadata["version"] = 12
    metadata["headline_language"] = "ko-strict"
    metadata["english_headline_policy"] = "translate_or_korean_fallback; raw English blocked"
    metadata["allowed_technical_ascii"] = sorted(ALLOWED_TECHNICAL_ASCII)
    return title, body, metadata


def build_setup_test_v12(quotes):
    title, body, metadata = v11.build_setup_test_v11(quotes)
    title = "✅ LNG·천연가스 감시 한국어 송출 규칙 v12 적용"
    body += (
        "\n\n<b>한국어 송출</b>"
        "\n• 영문 기사 제목은 반드시 한국어 번역 후 표시"
        "\n• 번역 실패·불완전 번역이면 영문을 내보내지 않고 한국어 사건 요약으로 대체"
        "\n• 영문 매체명도 한국어 표기, 미등록 매체는 '해외 매체'로 표시"
        "\n• LNG·TTF·JKM·FID·EPC·SPA·MOU 같은 표준 약어만 예외 허용"
    )
    metadata["version"] = 12
    return title, body, metadata


# v11이 참조하는 v8 모듈의 번역 함수를 엄격 버전으로 교체한다.
v8.translate_title_ko = translate_title_ko_strict

# v10/v11의 탐지·검증·가독성 규칙은 그대로 유지하고 최종 출력만 v12로 감싼다.
core.fetch_news_item_set = v11.v10.fetch_news_item_set_v10
core.confirmed_news_groups = v11.v10.confirmed_news_groups_v10
core.category_label = v11.v9.category_label_v9
core.classify_polarity = v11.v9.classify_polarity_v9
core.classify_alert_context = v11.v9.classify_alert_context_v9
core.impact_text = v11.v9.impact_text_v9
core.fetch_market_quotes = v11.v9.v8.v7.fetch_market_quotes_v7
core.format_quote = v11.v9.v8.v7.v6.format_quote_v6
core.signal_label = v11.v9.signal_label_v9
core.build_regular_alert = build_regular_alert_v12
core.build_setup_test = build_setup_test_v12


if __name__ == "__main__":
    raise SystemExit(core.main())
