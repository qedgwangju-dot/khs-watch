#!/usr/bin/env python3
"""에너지 공급감시 v31: 전용 알림에서 동시 발생한 다른 확정 사건 누락 방지.

v30의 장기 LNG SPA 감시와 v29의 한국어·가독성 규칙을 유지한다.
전용 계약 알림이 생성되는 시점에 다른 수급·금리·정책 사건도 함께 신규 확인되면
해당 사건을 상태에만 기록하고 본문에서 누락하지 않도록 '동시 감지' 블록을 붙인다.
"""
from __future__ import annotations

import html

import lng_supply_crisis_alert_v2 as core
import lng_supply_crisis_alert_v30 as v30

v29 = v30.v29
v27 = v30.v27
v26 = v30.v26
v12 = v30.v12
v8 = v30.v8

_BASE_BUILD = core.build_regular_alert
_BASE_SETUP = core.build_setup_test


def _non_contract_groups(groups):
    return [g for g in groups if str(g.get("category") or "") != v30.CATEGORY]


def _event_stage(group) -> str:
    subtype = str(group.get("subtype") or "")
    return v26.STAGE_LABELS.get(subtype, subtype or "상태 변화")


def _event_state(group) -> str:
    polarity = str(group.get("polarity") or "")
    return "악화" if polarity == "worsening" else "완화" if polarity == "easing" else "혼재"


def _title_ko(item: core.NewsItem) -> str:
    try:
        translated = v12.translate_title_ko_strict(item).strip()
        if translated and not v12._contains_untranslated_prose(translated):
            return translated
    except Exception:
        pass
    try:
        return v12.fallback_korean_title_v12(item)
    except Exception:
        return "관련 상태 변화 확인"


def _source_ko(source: str) -> str:
    try:
        return v8.source_name_ko(source)
    except Exception:
        return "주요 매체"


def _simultaneous_change_lines(groups) -> list[str]:
    others = _non_contract_groups(groups)
    if not others:
        return []

    lines = ["<b>동시 감지된 다른 변화</b>"]
    seen: set[tuple[str, str]] = set()
    for group in sorted(others, key=lambda g: float(g.get("latest_epoch") or 0), reverse=True):
        category = str(group.get("category") or "")
        subtype = str(group.get("subtype") or "")
        key = (category, subtype)
        if key in seen:
            continue
        seen.add(key)
        try:
            category_text = core.category_label(category)
        except Exception:
            category_text = category or "관련 시장"
        lines.append(
            f"• <b>{html.escape(category_text)}</b> · "
            f"{html.escape(_event_stage(group))} · {_event_state(group)}"
        )
        verification = str(group.get("verification") or "").strip()
        if verification:
            lines.append(f"  검증: {html.escape(verification)}")
        evidence = list(group.get("evidence") or [])
        if evidence:
            item = evidence[0]
            source = _source_ko(str(getattr(item, "source", "주요 매체") or "주요 매체"))
            title = _title_ko(item)
            link = str(getattr(item, "link", "") or "").strip()
            if link:
                lines.append(
                    f'  - {html.escape(source)} · {html.escape(title)} · '
                    f'<a href="{html.escape(link, quote=True)}">원문</a>'
                )
            else:
                lines.append(f"  - {html.escape(source)} · {html.escape(title)}")
        if len(seen) >= 4:
            break
    lines.append("• 위 변화도 이번 실행에서 신규 사건으로 판정되며 각각 별도 상태·중복방지 이력으로 추적")
    return lines


def build_regular_alert_v31(groups, quotes, new_signals, cleared_signals):
    title, body, metadata = _BASE_BUILD(groups, quotes, new_signals, cleared_signals)
    contracts = v30._contract_groups(groups)
    others = _non_contract_groups(groups)
    if contracts and others:
        block = _simultaneous_change_lines(groups)
        if block:
            body = body.rstrip() + "\n\n" + "\n".join(block)
    metadata["version"] = 31
    metadata["simultaneous_event_rule"] = {
        "rule": "dedicated alert body must not suppress other new confirmed groups",
        "display": "동시 감지된 다른 변화",
        "language": "ko-strict",
    }
    return title, body, metadata


def build_setup_test_v31(quotes):
    title, body, metadata = _BASE_SETUP(quotes)
    body += (
        "\n• 장기 LNG 계약 등 전용 본문이 생성돼도 같은 실행에서 확인된 다른 신규 사건을 '동시 감지된 다른 변화'로 반드시 표시"
        "\n• 동시 사건도 한국어 제목·근거 링크·검증 단계와 함께 표시하고 중복방지 이력에 별도 저장"
    )
    metadata["version"] = 31
    return title, body, metadata


core.build_regular_alert = build_regular_alert_v31
core.build_setup_test = build_setup_test_v31

if __name__ == "__main__":
    raise SystemExit(core.main())
