#!/usr/bin/env python3
"""에너지 공급감시 v34: 정제제품 경보 한국어·가독성·시점 안전성 보강.

v33의 정제제품 사건축을 유지하면서 다음만 수정한다.
- 월스트리트저널 연료위기 제목이 LNG 일반 대체문으로 떨어지지 않도록 전용 한국어 제목 사용
- Yahoo/Vitol 같은 영문 표시를 한국어 표기로 정리
- 2026-09-04 EIA 주간값은 9월 16일 다음 발표 이후 자동으로 고정값 노출 차단
- Alaska LNG·Polar LNG·AGDC·Glenfarne 및 545억달러·800억달러 규모 변화 감시
"""
from __future__ import annotations

import datetime as dt
import html

import lng_supply_crisis_alert_v2 as core
import lng_supply_crisis_alert_v33 as v33

v32 = v33.v32
v12 = v33.v12
v8 = v33.v8

_BASE_BUILD = core.build_regular_alert
_BASE_SETUP = core.build_setup_test
_BASE_POLARITY_V34 = core.classify_polarity
_BASE_CATEGORY_LABEL_V34 = core.category_label

ALASKA_CATEGORY = "alaska_lng_supply"
ALASKA_LNG_QUERIES = (
    (ALASKA_CATEGORY, '"Alaska LNG" Glenfarne AGDC when:7d'),
    (ALASKA_CATEGORY, '"Polar LNG" Alaska when:7d'),
    (ALASKA_CATEGORY, '"Alaska LNG" "54.5 billion" OR "80 billion" when:14d'),
    (ALASKA_CATEGORY, '알래스카 LNG 글렌파른 AGDC 545억달러 800억달러 when:14d'),
)
for item in ALASKA_LNG_QUERIES:
    if item not in core.NEWS_QUERIES:
        core.NEWS_QUERIES = tuple(core.NEWS_QUERIES) + (item,)

core.TRUSTED_SOURCE_ALIASES = tuple(core.TRUSTED_SOURCE_ALIASES) + (
    "alaska gasline development corporation", "agdc", "glenfarne", "polar lng",
    "federal energy regulatory commission", "ferc",
)
core.OFFICIAL_SOURCE_ALIASES = tuple(core.OFFICIAL_SOURCE_ALIASES) + (
    "alaska gasline development corporation", "agdc", "glenfarne", "polar lng",
    "federal energy regulatory commission", "ferc",
)

core.WORSENING_TERMS[ALASKA_CATEGORY] = (
    "delay", "delayed", "postpone", "postponed", "hold", "stalled", "stall",
    "cost overrun", "cost increase", "financing gap", "funding gap", "tax incentive failed",
    "failed to pass", "sanction", "sanctions", "permit challenge", "lawsuit", "cancelled", "canceled",
    "지연", "연기", "중단", "보류", "비용 증가", "자금조달 난항", "제재", "허가 지연", "취소",
)
core.EASING_TERMS[ALASKA_CATEGORY] = (
    "final investment decision", "fid", "signed", "agreement", "offtake", "gas sales",
    "secured", "committed", "funding", "financing", "final engineering", "feed", "construction",
    "groundbreaking", "supply agreement", "strategic partner", "investment", "export terminal",
    "최종투자결정", "계약", "협약", "구매", "공급", "자금조달", "투자", "착공", "최종 설계",
)
core.SUBTYPE_TERMS = (
    ("alaska_lng_cost_scale", ("54.5 billion", "80 billion", "545억달러", "800억달러")),
    ("polar_lng_project", ("polar lng",)),
    ("alaska_lng_project", ("alaska lng", "glenfarne", "agdc", "alaska gasline development corporation")),
) + tuple(core.SUBTYPE_TERMS)


def classify_polarity_v34(category: str, title: str) -> str | None:
    if category != ALASKA_CATEGORY:
        return _BASE_POLARITY_V34(category, title)
    normalized = core.normalize_text(title)
    if any(term in normalized for term in core.WORSENING_TERMS[ALASKA_CATEGORY]):
        return "worsening"
    if any(term in normalized for term in core.EASING_TERMS[ALASKA_CATEGORY]):
        return "easing"
    if any(term in normalized for term in ("alaska lng", "polar lng", "glenfarne", "agdc", "54.5 billion", "80 billion", "545억달러", "800억달러")):
        return "easing"
    return None


def category_label_v34(category: str) -> str:
    if category == ALASKA_CATEGORY:
        return "알래스카 LNG·대체공급 프로젝트"
    return _BASE_CATEGORY_LABEL_V34(category)


core.classify_polarity = classify_polarity_v34
core.category_label = category_label_v34


def _title_ko_v34(item: core.NewsItem) -> str:
    raw = str(getattr(item, "title", "") or "").strip()
    normalized = core.normalize_text(raw)
    if item.category == ALASKA_CATEGORY:
        if any(term in normalized for term in core.WORSENING_TERMS[ALASKA_CATEGORY]):
            return "알래스카 LNG 프로젝트 지연·사업성 위험 신규 변화"
        if "polar lng" in normalized:
            return "Polar LNG 알래스카 노스슬로프 프로젝트 신규 변화"
        if any(term in normalized for term in ("54.5 billion", "80 billion", "545억달러", "800억달러")):
            return "알래스카 LNG 대형 프로젝트 투자비·사업성 관련 신규 변화"
        return "Alaska LNG·Glenfarne·AGDC 대체공급 프로젝트 신규 변화"
    if "great fuel crisis is here" in normalized:
        return "미국 석유업계 경영진, 글로벌 연료 위기가 이미 시작됐다고 경고"
    if "global diesel supply to stay tight through winter" in normalized:
        return "글로벌 디젤 공급, 겨울까지 빠듯할 전망…업계 경영진 경고"
    if item.category == v33.CATEGORY:
        subtype = str(item.subtype or "")
        return {
            "fuel_crisis_systemic": "글로벌 연료 공급 위기 단계 상승",
            "refined_inventory_draw": "상업용 연료·중간유분 재고 감소 심화",
            "diesel_shortage": "디젤·중간유분 공급 부족 심화",
            "refinery_capacity_tight": "정유설비 여유능력 부족·가동 차질 확대",
            "fuel_buffer_rebuild": "연료재고·정제능력 회복 진전",
        }.get(subtype, "정제제품·연료 공급망의 확정 변화")
    return v32._strict_title(item)


def _evidence_lines_v34(groups) -> list[str]:
    lines: list[str] = []
    seen: set[tuple[str, str]] = set()
    for group in sorted(groups, key=lambda g: float(g.get("latest_epoch") or 0), reverse=True):
        for item in list(group.get("evidence") or []):
            raw_title = str(getattr(item, "title", "") or "").strip()
            link = str(getattr(item, "link", "") or "").strip()
            key = (raw_title, link)
            if key in seen:
                continue
            seen.add(key)
            source = v32._source_ko(str(getattr(item, "source", "주요 매체") or "주요 매체"))
            title = _title_ko_v34(item)
            line = f"• <b>{html.escape(source)}</b> · {html.escape(title)}"
            if link:
                line += f' · <a href="{html.escape(link, quote=True)}">원문</a>'
            lines.append(line)
            if len(lines) >= 3:
                return lines
    return lines


# v33 본문 빌더가 호출하는 근거 렌더러를 전용 한국어 버전으로 교체한다.
v33._title_ko = _title_ko_v34
v33._evidence_lines = _evidence_lines_v34


def _build_fuel_body_v34(groups, quotes) -> str:
    body = v33._build_fuel_body(groups, quotes)
    body = body.replace("Yahoo Brent 선물 ", "")
    body = body.replace("Yahoo 이전 종가", "이전 종가")
    body = body.replace("Yahoo", "야후 파이낸스")
    body = body.replace("Vitol", "비톨")

    # 9/16 다음 주간 EIA 발표 이후에는 9/4 수치를 현재값처럼 계속 노출하지 않는다.
    today_kst = dt.datetime.now(core.KST).date()
    if today_kst > dt.date(2026, 9, 16):
        kept: list[str] = []
        inserted = False
        for line in body.splitlines():
            if "<b>미국 중간유분 재고</b>" in line or "<b>미국 전략비축유</b>" in line:
                if not inserted:
                    kept.append("• <b>EIA 주간 재고</b> 9/4 고정값 재사용 차단 · 최신 공식 주간값 확인 전 숫자 송출 보류")
                    inserted = True
                continue
            kept.append(line)
        body = "\n".join(kept)
    return body


def build_regular_alert_v34(groups, quotes, new_signals, cleared_signals):
    title, body, metadata = _BASE_BUILD(groups, quotes, new_signals, cleared_signals)
    if v33._fuel_groups(groups):
        title = "🚨 글로벌 연료·정제제품 공급경보"
        body = _build_fuel_body_v34(groups, quotes)
    body = v32._replace_evidence_text(body, groups)
    leaks = v32._raw_english_evidence_remaining(body, groups)
    if leaks:
        raise RuntimeError("영문 기사 제목 송출 차단: " + " | ".join(leaks[:3]))
    metadata["version"] = 34
    metadata.setdefault("refined_fuel_watch", {})["output_guard"] = (
        "fuel-specific Korean evidence + Yahoo/Vitol Korean display + stale EIA fixed-value block"
    )
    metadata["alaska_lng_watch"] = {
        "category": ALASKA_CATEGORY,
        "keywords": ["Alaska LNG", "Polar LNG", "AGDC", "Glenfarne", "545억달러", "800억달러"],
        "state_file_preserved": str(core.STATE_PATH),
    }
    return title, body, metadata


def build_setup_test_v34(quotes):
    title, body, metadata = _BASE_SETUP(quotes)
    body += (
        "\n• 정제제품 경보의 근거기사 제목을 연료 사건 전용 한국어로 표시"
        "\n• 야후 파이낸스·비톨 등 사용자 노출 문구도 한국어 표기로 정리"
        "\n• EIA 9/4 숫자는 다음 공식 발표 뒤 자동으로 현재값 재사용을 차단"
        "\n• Alaska LNG·Polar LNG·AGDC·Glenfarne·545억달러·800억달러 신규 변화 감시"
    )
    metadata["version"] = 34
    metadata["alaska_lng_watch"] = True
    return title, body, metadata


core.build_regular_alert = build_regular_alert_v34
core.build_setup_test = build_setup_test_v34

if __name__ == "__main__":
    raise SystemExit(core.main())
