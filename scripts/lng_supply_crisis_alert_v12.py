#!/usr/bin/env python3
"""LNG·전력 인프라 공급망 감시 v12.

기존 v11의 수급·가격·가독성 규칙과 v12의 한국어 전용 송출 규칙을 유지하면서
가스터빈·변압기·HVDC 등 발전/전력 설비의 조달 병목과 무역장벽까지 감시한다.

핵심 원칙
- 영문 기사 제목은 반드시 한국어 번역 후 송출한다.
- 번역 실패·불완전 번역이면 영문을 내보내지 않고 한국어 사건 요약으로 대체한다.
- LNG·TTF·JKM·FID·EPC·SPA·MOU 같은 표준 약어만 예외적으로 허용한다.
- 가스터빈/전력기기 조달에서 무역전쟁·관세·공급자 배제·장기 납기·제조 슬롯 병목을 조기 경보한다.
- 주요 매체 1곳만 확인된 조달 이슈는 '조달·공급망 조기신호'로 명확히 낮춰 표시하고,
  실제 계약·발주·취소 확정은 공식 원천 또는 기존 교차검증 기준을 우선한다.
"""

from __future__ import annotations

import html
import re

import lng_supply_crisis_alert_v2 as core
import lng_supply_crisis_alert_v11 as v11


v8 = v11.v10.v9.v8
_base_translate_title_ko = v8.translate_title_ko
_base_fallback_korean_title = v8.fallback_korean_title
_base_category_label = v11.v9.category_label_v9
_base_classify_polarity = v11.v9.classify_polarity_v9
_base_classify_context = v11.v9.classify_alert_context_v9
_base_impact_text = v11.v9.impact_text_v9
_base_confirmed_news_groups = v11.v10.confirmed_news_groups_v10
_base_v11_context_verdict = v11._context_verdict
_base_v11_next_check = v11._next_check
_base_v11_status_word = v11._status_word


# 발전설비 조달·공급망을 LNG 가격/호르무즈와 별개 축으로 추적한다.
POWER_EQUIPMENT_QUERIES = (
    ("power_equipment_supply", '"gas turbine" procurement tariff "trade war" utility delay when:3d'),
    ("power_equipment_supply", '"gas turbine" GE Vernova reservation agreement lead time utility when:7d'),
    ("power_equipment_supply", '"Manitoba Hydro" "GE Vernova" gas turbines trade war when:7d'),
    ("power_equipment_supply", '"gas turbine" Siemens Energy Mitsubishi Power backlog delivery slot when:7d'),
    ("power_equipment_supply", '"power transformer" procurement tariff trade war delay utility when:3d'),
    ("power_equipment_supply", 'HVDC transformer procurement supplier delay tariff utility when:7d'),
    ("power_equipment_supply", '가스터빈 조달 관세 무역전쟁 발전소 GE 버노바 납기 when:7d'),
    ("power_equipment_supply", '변압기 HVDC 조달 관세 공급망 병목 납기 발전소 when:7d'),
)
core.NEWS_QUERIES = tuple(core.NEWS_QUERIES) + POWER_EQUIPMENT_QUERIES

core.TRUSTED_SOURCE_ALIASES = tuple(core.TRUSTED_SOURCE_ALIASES) + (
    "cbc", "cbc news", "winnipeg free press", "manitoba hydro",
    "province of manitoba", "government of manitoba", "public utilities board",
    "pub manitoba", "ge vernova", "siemens energy", "mitsubishi power",
)
core.OFFICIAL_SOURCE_ALIASES = tuple(core.OFFICIAL_SOURCE_ALIASES) + (
    "manitoba hydro", "province of manitoba", "government of manitoba",
    "public utilities board", "pub manitoba",
)

core.WORSENING_TERMS["power_equipment_supply"] = (
    "trade war", "tariff", "tariffs", "complicates", "complicated", "delay", "delayed",
    "doubt", "not a done deal", "financial impact", "financial impacts", "ineligible",
    "procurement restriction", "procurement restrictions", "long lead time", "long lead times",
    "seven years", "7 years", "backlog", "bottleneck", "supply chain", "shortage",
    "cannot proceed", "may not proceed", "supplier exclusion", "supplier excluded",
    "무역전쟁", "관세", "조달 차질", "구매 차질", "납기 지연", "공급망 병목",
    "구매 재검토", "공급자 배제", "공급 부족", "제조 슬롯 부족", "발주 지연",
)
core.EASING_TERMS["power_equipment_supply"] = (
    "reservation agreement", "supplier selected", "order awarded", "secured turbines",
    "delivery slot", "manufacturing slot", "procurement approved", "contract signed",
    "purchase agreement", "accelerate delivery", "alternative supplier", "capacity secured",
    "조달 확정", "공급자 선정", "구매계약", "발주 확정", "제조 슬롯 확보",
    "납기 단축", "대체 공급자", "공급 확보",
)

core.SUBTYPE_TERMS = (
    ("power_trade_barrier", ("trade war", "tariff", "tariffs", "무역전쟁", "관세", "공급자 배제")),
    ("gas_turbine_procurement", ("gas turbine", "combustion turbine", "ge vernova", "siemens energy", "mitsubishi power", "가스터빈")),
    ("transformer_procurement", ("power transformer", "transformer", "hvdc", "변압기")),
    ("power_delivery_slot", ("delivery slot", "manufacturing slot", "lead time", "backlog", "제조 슬롯", "납기")),
) + tuple(core.SUBTYPE_TERMS)


# 영문 매체/헤드라인은 한국어로만 표시한다.
v8.SOURCE_KO.update(
    {
        "cbc": "캐나다 CBC",
        "cbc news": "캐나다 CBC",
        "winnipeg free press": "위니펙 프리프레스",
        "manitoba hydro": "매니토바 하이드로",
        "province of manitoba": "매니토바주 정부",
        "government of manitoba": "매니토바주 정부",
        "public utilities board": "매니토바 공공요금위원회",
        "ge vernova": "GE 버노바",
        "siemens energy": "지멘스 에너지",
        "mitsubishi power": "미쓰비시 파워",
    }
)

v8.KNOWN_TRANSLATIONS.update(
    {
        "Canada-U.S. trade war complicates Hydro plan to purchase gas turbines from U.S. manufacturer":
            "캐나다·미국 무역전쟁, 매니토바 하이드로의 미국산 가스터빈 구매 계획에 차질",
        "Canada-U.S. trade war complicates Hydro plan to purchase gas turbines from U.S. manufacturer - CBC":
            "캐나다·미국 무역전쟁, 매니토바 하이드로의 미국산 가스터빈 구매 계획에 차질",
        "Canada-U.S. trade war complicates Hydro plan to purchase gas turbines from U.S. manufacturer - CBC News":
            "캐나다·미국 무역전쟁, 매니토바 하이드로의 미국산 가스터빈 구매 계획에 차질",
    }
)

ALLOWED_TECHNICAL_ASCII = {
    "LNG", "JKM", "TTF", "EU", "GIE", "IEA", "AP", "BBC", "CBC", "CNBC", "S&P",
    "FID", "EPC", "SPA", "MOU", "LOI", "HVDC",
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
    ("Manitoba Hydro", "매니토바 하이드로"),
    ("Manitoba", "매니토바"),
    ("GE Vernova", "GE 버노바"),
    ("Siemens Energy", "지멘스 에너지"),
    ("Mitsubishi Power", "미쓰비시 파워"),
    ("gas turbine", "가스터빈"),
    ("gas turbines", "가스터빈"),
)


def _contains_untranslated_prose(text: str) -> bool:
    scrubbed = text
    for token in sorted(ALLOWED_TECHNICAL_ASCII, key=len, reverse=True):
        scrubbed = scrubbed.replace(token, "")
    return bool(re.search(r"[A-Za-z]{2,}", scrubbed))


def fallback_korean_title_v12(item: core.NewsItem) -> str:
    if item.category == "power_equipment_supply":
        if item.polarity == "worsening":
            if item.subtype == "power_trade_barrier":
                return "무역장벽으로 발전설비 조달·구매 계획에 차질"
            if item.subtype == "gas_turbine_procurement":
                return "가스터빈 조달·납기 차질 확대"
            if item.subtype == "transformer_procurement":
                return "변압기·HVDC 전력기기 조달 병목 확대"
            return "발전·전력 설비 조달 공급망 차질 확인"
        if item.subtype == "gas_turbine_procurement":
            return "가스터빈 공급자·제조 슬롯 확보 진전"
        if item.subtype == "transformer_procurement":
            return "변압기·HVDC 전력기기 조달 개선"
        return "발전·전력 설비 조달 공급망 개선 확인"
    return _base_fallback_korean_title(item)


def translate_title_ko_strict(item: core.NewsItem) -> str:
    translated = _base_translate_title_ko(item).strip()
    for before, after in POST_TRANSLATION_REPLACEMENTS:
        translated = translated.replace(before, after)

    if not translated or _contains_untranslated_prose(translated):
        translated = fallback_korean_title_v12(item)
    return translated


def category_label_v12(category: str) -> str:
    if category == "power_equipment_supply":
        return "발전설비·가스터빈 조달 공급망"
    return _base_category_label(category)


def classify_polarity_v12(category: str, title: str) -> str | None:
    if category != "power_equipment_supply":
        return _base_classify_polarity(category, title)
    normalized = core.normalize_text(title)
    # 'reservation agreement'가 함께 있어도 무역전쟁·관세·지연이 있으면 순효과는 조달 악화로 우선 판정한다.
    if any(term in normalized for term in core.WORSENING_TERMS[category]):
        return "worsening"
    if any(term in normalized for term in core.EASING_TERMS[category]):
        return "easing"
    return None


EARLY_POWER_SOURCE_ALIASES = (
    "cbc", "cbc news", "reuters", "bloomberg", "financial times", "associated press",
    "ap news", "cnbc", "winnipeg free press",
)


def confirmed_news_groups_v12(items: list[core.NewsItem]):
    confirmed = _base_confirmed_news_groups(items)
    existing = {
        (str(group["category"]), str(group["polarity"]), str(group["subtype"]), str(group["event_id"]))
        for group in confirmed
    }

    # 가스터빈/전력기기 조달은 제조 슬롯이 수년 단위로 움직일 수 있어 정책·조달 변화를 조기에 포착한다.
    # 단일 주요 매체는 '조기신호'로만 표시한다. 실제 계약 확정으로 표현하지 않는다.
    for item in sorted(items, key=lambda value: value.published_epoch, reverse=True):
        if item.category != "power_equipment_supply":
            continue
        if not (item.official or core.source_matches(item.source, EARLY_POWER_SOURCE_ALIASES)):
            continue
        key = (item.category, item.polarity, item.subtype, item.event_id)
        if key in existing:
            continue
        confirmed.append(
            {
                "category": item.category,
                "polarity": item.polarity,
                "subtype": item.subtype,
                "event_id": item.event_id,
                "latest_epoch": item.published_epoch,
                "evidence": [item],
                "verification": "조달·공급망 조기신호·주요 매체/공식 1곳",
            }
        )
        existing.add(key)

    confirmed.sort(key=lambda group: float(group["latest_epoch"]), reverse=True)
    return confirmed


def classify_alert_context_v12(groups, new_signals, cleared_signals) -> str:
    power = [group for group in groups if group.get("category") == "power_equipment_supply"]
    if power:
        has_worsening = any(group.get("polarity") == "worsening" for group in power)
        has_easing = any(group.get("polarity") == "easing" for group in power)
        if has_worsening and not has_easing:
            return "power_equipment_bottleneck"
        if has_easing and not has_worsening:
            return "power_equipment_easing"
        return "power_equipment_mixed"
    return _base_classify_context(groups, new_signals, cleared_signals)


def impact_text_v12(context: str):
    if context == "power_equipment_bottleneck":
        return (
            "글로벌 가스터빈·변압기 조달 병목과 관세·조달 규칙 변화는 한국 발전사·가스발전·데이터센터 전력 인프라의 CAPEX와 준공 일정에 전이될 수 있습니다. "
            "공급자 다변화가 확대되면 한국 발전설비·변압기·전력기기 업체에는 대체 공급 기회가 생길 수 있습니다.",
            "돈 버는 능력: 가스터빈 OEM은 높은 백로그와 제조 슬롯 부족으로 가격 결정력이 강화될 수 있고 대체 공급업체도 기회를 얻습니다. "
            "할인율: 설비비·전력비 상승은 프로젝트 수익성과 물가에 부담입니다. "
            "수급: 핵심은 가스터빈·대형 변압기 제조 슬롯과 납기입니다. "
            "시간표: 공급자 예약 → 관세·조달 적격성 → 최종 발주 → 제조 슬롯 → 납품 → 시운전 순으로 확인합니다.",
            "발전설비 조달 병목이 커지고 있습니다. 공급자 예약과 최종 발주를 구분하고 제조 슬롯·납기·대체 공급자 수혜를 함께 봅니다.",
        )
    if context == "power_equipment_easing":
        return (
            "가스터빈·변압기 등 핵심 발전설비의 공급자 또는 제조 슬롯 확보가 진전되면 한국 발전·데이터센터 전력 프로젝트의 일정·원가 불확실성도 완화될 수 있습니다.",
            "돈 버는 능력: 발주처·EPC의 일정 가시성이 좋아지는 반면 장비 공급자의 초과 가격 결정력은 일부 낮아질 수 있습니다. "
            "수급: 실제 제조 슬롯과 납품일을 확인합니다. "
            "시간표: 공급자 선정 → 최종 발주 → 제조 → 납품 → 시운전으로 확인합니다.",
            "발전설비 조달 여건이 개선됐지만 실제 발주·납품 일정까지 확인해야 합니다.",
        )
    if context == "power_equipment_mixed":
        return (
            "발전설비 조달에서 공급 확보와 무역·납기 제약이 동시에 나타났습니다. 공급자 예약과 실제 발주·납품을 분리해 봐야 합니다.",
            "OEM의 백로그 수혜와 발주처의 CAPEX·일정 부담이 동시에 존재합니다. 관세·조달 적격성·제조 슬롯을 함께 추적합니다.",
            "발전설비 공급망 신호가 엇갈려 최종 발주와 제조 슬롯 확인이 필요합니다.",
        )
    return _base_impact_text(context)


def v11_context_verdict_v12(context: str) -> str:
    if context == "power_equipment_bottleneck":
        return "발전설비 조달 병목 확대 · 프로젝트 일정/원가 리스크"
    if context == "power_equipment_easing":
        return "발전설비 조달 개선 · 제조 슬롯/납기 가시성 상승"
    if context == "power_equipment_mixed":
        return "발전설비 조달 신호 혼재 · 최종 발주/납기 확인 필요"
    return _base_v11_context_verdict(context)


def v11_next_check_v12(context: str) -> str:
    if context in {"power_equipment_bottleneck", "power_equipment_easing", "power_equipment_mixed"}:
        return "공급자 예약 → 관세·조달 적격성 → 최종 발주 → 제조 슬롯 → 납품 → 시운전"
    return _base_v11_next_check(context)


def v11_status_word_v12(group: dict[str, object]) -> str:
    if str(group.get("category")) == "power_equipment_supply":
        return "조달 차질·병목" if group.get("polarity") == "worsening" else "조달 개선·확보"
    return _base_v11_status_word(group)


def build_regular_alert_v12(groups, quotes, new_signals, cleared_signals):
    title, body, metadata = v11.build_regular_alert_v11(
        groups, quotes, new_signals, cleared_signals
    )

    power_groups = [group for group in groups if str(group.get("category")) == "power_equipment_supply"]
    if power_groups:
        title = "⚠️ LNG·전력 인프라 변화 감지"
        marker = "• <b>판정</b>  "
        insert = (
            "• <b>핵심 병목</b>  가스터빈·변압기 조달 · 관세/무역장벽 · 제조 슬롯/납기\n"
            "• <b>현재 단계</b>  공급자 예약·조달 검토 → 최종 구매·납품 전"
        )
        lines = body.splitlines()
        for index, line in enumerate(lines):
            if line.startswith(marker):
                lines[index + 1:index + 1] = [insert]
                break
        body = "\n".join(lines)

    # 방어적 최종검사: 영문 문장형 원제목이 그대로 들어가면 Telegram 송출 전에 차단한다.
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
    metadata["power_equipment_watch"] = [
        "가스터빈", "대형 변압기/HVDC", "무역전쟁/관세", "조달 적격성",
        "제조 슬롯/납기", "공급자 변경", "최종 발주/납품/시운전",
    ]
    return title, body, metadata


def build_setup_test_v12(quotes):
    title, body, metadata = v11.build_setup_test_v11(quotes)
    title = "✅ LNG·전력 인프라 감시 규칙 v12 적용"
    body += (
        "\n\n<b>한국어 송출</b>"
        "\n• 영문 기사 제목은 반드시 한국어 번역 후 표시"
        "\n• 번역 실패·불완전 번역이면 영문을 내보내지 않고 한국어 사건 요약으로 대체"
        "\n• LNG·TTF·JKM·FID·EPC·SPA·MOU·HVDC 같은 표준 약어만 예외 허용"
        "\n\n<b>발전설비 공급망</b>"
        "\n• 가스터빈·대형 변압기/HVDC의 무역전쟁·관세·조달 차질·제조 슬롯·장기 납기를 병렬 감시"
        "\n• 주요 매체 1곳이면 '조달·공급망 조기신호'로 먼저 알림, 실제 계약 확정으로 과장하지 않음"
        "\n• 확인 순서: 공급자 예약 → 관세/적격성 → 최종 발주 → 제조 슬롯 → 납품 → 시운전"
    )
    metadata["version"] = 12
    return title, body, metadata


# 한국어 전용 번역·가독성 헬퍼를 교체한다.
v8.fallback_korean_title = fallback_korean_title_v12
v8.translate_title_ko = translate_title_ko_strict
v11._context_verdict = v11_context_verdict_v12
v11._next_check = v11_next_check_v12
v11._status_word = v11_status_word_v12

# 기존 수급/가격/알래스카 규칙을 유지하면서 발전설비 조달 축을 추가한다.
core.fetch_news_item_set = v11.v10.fetch_news_item_set_v10
core.confirmed_news_groups = confirmed_news_groups_v12
core.category_label = category_label_v12
core.classify_polarity = classify_polarity_v12
core.classify_alert_context = classify_alert_context_v12
core.impact_text = impact_text_v12
core.fetch_market_quotes = v11.v9.v8.v7.fetch_market_quotes_v7
core.format_quote = v11.v9.v8.v7.v6.format_quote_v6
core.signal_label = v11.v9.signal_label_v9
core.build_regular_alert = build_regular_alert_v12
core.build_setup_test = build_setup_test_v12


if __name__ == "__main__":
    raise SystemExit(core.main())
