#!/usr/bin/env python3
"""LNG 공급·가격 감시 v25: 유럽 가스·채권금리 경보 가독성 재구성."""
from __future__ import annotations

import html
import re

import lng_supply_crisis_alert_v2 as core
import lng_supply_crisis_alert_v24 as v24

_BASE_BUILD = core.build_regular_alert
_BASE_SETUP = core.build_setup_test


def _safe_quote_text(quote: core.Quote) -> str:
    try:
        return core.format_quote(quote)
    except Exception:
        return f"{quote.label} {float(quote.price):,.2f}{quote.unit}"


def _rate_verdict(groups: list[dict[str, object]]) -> tuple[str, str]:
    rate_groups = [g for g in groups if str(g.get("category")) == "europe_rates"]
    worsening = any(str(g.get("polarity")) == "worsening" for g in rate_groups)
    easing = any(str(g.get("polarity")) == "easing" for g in rate_groups)
    if worsening and not easing:
        return (
            "에너지·ECB 재가격과 유럽 채권 매도 압력 강화",
            "가스·에너지 → 단기 인플레이션 기대 → ECB 재가격 → 유럽 장기금리",
        )
    if easing and not worsening:
        return (
            "유럽 채권·ECB 스트레스 완화 신호",
            "에너지/정책 부담 완화 → ECB 인상 기대 약화 → 장기금리 안정 여부 확인",
        )
    return (
        "유럽 금리 신호 혼재 · 원인 분리 확인 필요",
        "에너지·ECB 경로와 재정·정치/기간프리미엄 경로를 분리 확인",
    )


def _compact_verification(groups: list[dict[str, object]]) -> str:
    values: list[str] = []
    for group in groups:
        value = str(group.get("verification") or "").strip()
        if value and value not in values:
            values.append(value)
    joined = " / ".join(values)
    if "신뢰 매체 2곳 교차" in joined and "유럽 금리 조기신호" in joined:
        return "신뢰 매체 교차 + 주요 금융매체/공식기관 조기신호"
    return joined or "검증된 신규 변화"


def _evidence_lines(groups: list[dict[str, object]]) -> list[str]:
    by_category: dict[str, list[dict[str, object]]] = {}
    for group in groups:
        by_category.setdefault(str(group.get("category") or "unknown"), []).append(group)

    lines: list[str] = []
    for category, cat_groups in by_category.items():
        polarities = {str(g.get("polarity") or "") for g in cat_groups}
        if polarities == {"worsening"}:
            state = "악화"
        elif polarities == {"easing"}:
            state = "완화"
        else:
            state = "혼재"
        label = core.category_label(category)
        lines.append(f"• <b>{html.escape(label)}</b>  {state}")
        lines.append(f"  검증: {html.escape(_compact_verification(cat_groups))}")

        seen: set[tuple[str, str]] = set()
        evidence_count = 0
        for group in cat_groups:
            for item in list(group.get("evidence") or []):
                source = str(getattr(item, "source", "해외 매체") or "해외 매체")
                title = str(getattr(item, "title", "") or "")
                link = str(getattr(item, "link", "") or "")
                key = (title, link)
                if key in seen:
                    continue
                seen.add(key)
                evidence_count += 1
                source_e = html.escape(source)
                title_e = html.escape(title)
                if link:
                    link_e = html.escape(link, quote=True)
                    lines.append(f"  - <b>{source_e}</b> · {title_e} · <a href=\"{link_e}\">원문</a>")
                else:
                    lines.append(f"  - <b>{source_e}</b> · {title_e}")
                if evidence_count >= 4:
                    break
            if evidence_count >= 4:
                break
    return lines


def _extract_common_delta(quote: core.Quote) -> float | None:
    match = re.search(r"common_since_aug4_bp=([+-]?[0-9.]+)", quote.source_note or "")
    return float(match.group(1)) if match else None


def _market_lines(quotes: dict[str, core.Quote]) -> list[str]:
    lines: list[str] = []
    if "ttf" in quotes:
        lines.append(f"• <b>TTF</b> {_safe_quote_text(quotes['ttf'])}")
    if "brent" in quotes:
        lines.append(f"• <b>Brent</b> {_safe_quote_text(quotes['brent'])}")
    if "bund10" in quotes:
        lines.append(f"• <b>독일 10Y</b> {_safe_quote_text(quotes['bund10'])}")
    if "us10" in quotes:
        lines.append(f"• <b>미국 10Y</b> {_safe_quote_text(quotes['us10'])}")

    bund = quotes.get("bund10")
    us = quotes.get("us10")
    if bund is not None and us is not None:
        de = _extract_common_delta(bund)
        usa = _extract_common_delta(us)
        if de is not None and usa is not None:
            lines.append(
                f"• <b>8/4 이후 상대강도</b> 독일 {de:+.1f}bp vs 미국 {usa:+.1f}bp · 독일이 {de-usa:+.1f}bp 더 상승"
            )
    elif "bund10" not in quotes or "us10" not in quotes:
        lines.append("• <b>독일↔미국 10Y 비교</b> 공식 수치 검증 통과 전 숫자 보류")

    lines.append("• <b>감시선</b> TTF 80 → 90 → 100유로/MWh · 독일 10Y 3.30 → 3.40 → 3.50 → 3.75%")
    return lines


def _build_rate_body(groups: list[dict[str, object]], quotes: dict[str, core.Quote]) -> str:
    verdict, stage = _rate_verdict(groups)
    lines: list[str] = [
        "<b>한눈에</b>",
        f"• <b>판정</b> {verdict}",
        f"• <b>현재 단계</b> {stage}",
        "",
        "<b>무엇이 바뀌었나</b>",
    ]
    lines.extend(_evidence_lines(groups))
    lines.extend([
        "",
        "<b>시장 확인</b>",
    ])
    lines.extend(_market_lines(quotes))
    lines.extend([
        "",
        "<b>왜 중요한가</b>",
        "• <b>에너지 경로</b> TTF/Brent 상승 → 단기 인플레이션 기대 상승 → ECB 긴축 기대 강화 → Bund 상승 압력",
        "• <b>재정·정치 경로</b> 재정/정치 불안 → 기간·국가위험 프리미엄 상승 → 장기물 추가 매도 · 금리 상승을 전부 가스 탓으로 단정하지 않음",
        "",
        "<b>한국 영향</b>",
        "• LNG 조달원가 상승에 글로벌 장기금리 상승이 겹치면 국내 기업의 조달비·밸류에이션 부담이 동시에 커질 수 있음",
        "",
        "<b>투자 포인트</b>",
        "• <b>돈버는능력</b> 은행은 NIM 일부 수혜 가능 · 고부채 유틸리티·부동산·인프라는 이자비용 부담",
        "• <b>할인율</b> 유럽 장기금리가 미국보다 빠르게 오르면 글로벌 성장주·장기듀레이션 자산에 부담",
        "• <b>수급</b> 높은 가스가격이 LNG 카고 경쟁과 유럽 에너지 비용을 동시에 압박하는지 확인",
        "• <b>시간표</b> ECB 추가 인상 기대가 독일 2Y·10Y·30Y와 프랑스-독일 스프레드에 실제 반영되는지 추적",
        "",
        "<b>다음 확인</b>",
        "• TTF/Brent → 유로존 단기 인플레이션 기대 → ECB 회의·금리선물 → 독일 2Y·10Y·30Y → 프랑스-독일 10Y 스프레드 → 유럽 주식·신용스프레드",
        "",
        "<b>핵심 한 줄</b>",
        "• 유럽 가스 충격이 ECB와 장기금리로 전이되는지, 그리고 독일 금리 상승폭이 미국보다 커지는지가 핵심 비교 신호",
        "",
        "<b>검증</b> 동일 벤치마크·동일 기준일로 재계산한 수치만 사용 · 기사 누적상승률은 그대로 재사용하지 않음",
    ])

    # 같은 실행에서 TTF 장중 milestone이나 LNG 화물창 이벤트가 함께 잡힌 경우
    # 해당 전용 섹션은 유지하되 generic 본문 중복은 재생성하지 않는다.
    try:
        ttf_lines = v24.v23._ttf_intraday_section(groups, quotes)
    except Exception:
        ttf_lines = []
    if ttf_lines:
        lines.extend(["", *ttf_lines])

    try:
        cargo_lines = v24._cargo_tank_section(groups)
    except Exception:
        cargo_lines = []
    if cargo_lines:
        lines.extend(["", *cargo_lines])

    return "\n".join(lines)


def build_regular_alert_v25(groups, quotes, new_signals, cleared_signals):
    title, body, metadata = _BASE_BUILD(groups, quotes, new_signals, cleared_signals)
    if any(str(group.get("category")) == "europe_rates" for group in groups):
        title = "⚠️ 유럽 가스·채권금리 스트레스 경보"
        body = _build_rate_body(groups, quotes)
    metadata["version"] = 25
    metadata["readability_layout"] = {
        "rate_alert_order": [
            "한눈에", "무엇이 바뀌었나", "시장 확인", "왜 중요한가", "한국 영향",
            "투자 포인트", "다음 확인", "핵심 한 줄", "검증",
        ],
        "rules": [
            "same-category evidence merged into one block",
            "only one next-check section",
            "causal path split into energy and fiscal/political paths",
            "investment impact split into earning power/discount rate/supply-demand/timetable",
        ],
    }
    return title, body, metadata


def build_setup_test_v25(quotes):
    title, body, metadata = _BASE_SETUP(quotes)
    title = "✅ LNG 알림 가독성 레이아웃 v25 적용"
    body += (
        "\n\n<b>유럽 가스·채권금리 알림</b>"
        "\n• 같은 카테고리의 반복 블록은 하나로 통합하고 근거 기사만 묶어서 표시"
        "\n• 판정 → 현재 단계 → 핵심 변화 → 시장 숫자 → 한국 영향 → 투자 4축 → 다음 확인 → 핵심 한 줄 순서"
        "\n• ‘다음 확인’과 인과 경로를 여러 번 반복하지 않고 각 1회만 표시"
        "\n• 내용 자체를 삭제하기보다 긴 문장을 짧은 의미 단위로 재배치"
    )
    metadata["version"] = 25
    return title, body, metadata


core.build_regular_alert = build_regular_alert_v25
core.build_setup_test = build_setup_test_v25

if __name__ == "__main__":
    raise SystemExit(core.main())
