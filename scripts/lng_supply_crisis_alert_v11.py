#!/usr/bin/env python3
"""LNG 공급·전략 촉매 감시 v11.

v10의 탐지·검증 규칙은 그대로 유지하고 Telegram 출력만 '스캔 우선' 구조로 바꾼다.
목표는 정보를 줄이는 것이 아니라 같은 정보를 첫 화면에서 바로 읽히게 만드는 것이다.

출력 원칙
1) 판정 → 현재 단계/핵심 변화 → 근거 → 가격 → 한국 영향 → 투자 포인트 → 다음 확인 순서.
2) 핵심 단어와 수치만 굵게 표시하고 긴 문장은 섹션별로 분리한다.
3) 알래스카 LNG는 정책 발언과 실제 계약·FID·발주를 첫 화면에서 명확히 구분한다.
4) 원문 링크·검증 수준·가격 원천·기존 상세 해석은 삭제하지 않는다.
"""

from __future__ import annotations

import html
from dataclasses import asdict

import lng_supply_crisis_alert_v2 as core
import lng_supply_crisis_alert_v10 as v10
import lng_supply_crisis_alert_v9 as v9


def _status_word(group: dict[str, object]) -> str:
    if str(group.get("category")) == "alaska_lng":
        return "정책·사업 진전" if group.get("polarity") == "easing" else "지연·후퇴"
    return "악화" if group.get("polarity") == "worsening" else "완화"


def _context_verdict(context: str) -> str:
    labels = {
        "strategic_supply_progress": "정책 촉매 강화 · 실제 계약/수주 확정 전",
        "strategic_supply_setback": "전략 프로젝트 가시성 후퇴 · 일정 재확인 필요",
        "strategic_supply_mixed": "정책 지원과 사업 제약 혼재 · 실제 계약 확인 필요",
        "supply_worsening": "LNG 공급·운송 리스크 확대",
        "supply_easing": "LNG 공급·운송 리스크 완화",
        "price_worsening": "가격 스트레스 확대",
        "price_easing": "가격 스트레스 완화",
        "mixed": "뉴스·가격 신호 혼재",
    }
    return labels.get(context, "새로운 LNG 수급·정책 변화 확인")


def _next_check(context: str) -> str:
    if context == "strategic_supply_progress":
        return "한국 측 공식 참여 확인 → MOU/정부 합의 → 오프테이크·SPA → FID → EPC·강관/설비 발주"
    if context == "strategic_supply_setback":
        return "지연 원인 확인 → 자금조달/오프테이크 → FID 재설정 → EPC·발주 재개 여부"
    if context == "strategic_supply_mixed":
        return "정치 발언과 상업 계약을 분리해 MOU·오프테이크·FID·발주 순서로 확인"
    if context in {"supply_worsening", "price_worsening"}:
        return "카타르 LNG 출하·Force Majeure·호르무즈/홍해 운송·TTF/Brent 재진입 여부"
    if context in {"supply_easing", "price_easing"}:
        return "정상화 지속 여부와 가격 임계치 재진입 여부"
    return "새 확정 뉴스와 가격 임계치의 재진입·이탈 여부"


def build_regular_alert_v11(
    groups: list[dict[str, object]],
    quotes: dict[str, core.Quote],
    new_signals: set[str],
    cleared_signals: set[str],
) -> tuple[str, str, dict[str, object]]:
    context = core.classify_alert_context(groups, new_signals, cleared_signals)
    title = "⚠️ LNG·천연가스 변화 감지"
    lines: list[str] = []

    lines.append("<b>한눈에</b>")
    lines.append(f"• <b>판정</b>  {html.escape(_context_verdict(context))}")

    alaska_groups = [g for g in groups if str(g.get("category")) == "alaska_lng"]
    if alaska_groups:
        lines.append("• <b>현재 단계</b>  정책 발언 ① / ⑤")
        lines.append("• <b>아직 아님</b>  한국 투자 확정 · 오프테이크/SPA · FID · EPC/발주")

    if groups:
        lines.extend(["", "<b>무엇이 바뀌었나</b>"])
        for group in groups[:3]:
            category = html.escape(core.category_label(str(group["category"])))
            status = html.escape(_status_word(group))
            verification = html.escape(str(group["verification"]))
            lines.append(f"• <b>{category}</b>  {status}")
            lines.append(f"  검증: {verification}")
            for item in group["evidence"][:2]:
                source = html.escape(v10.v9.v8.source_name_ko(item.source))
                translated = html.escape(v10.v9.v8.translate_title_ko(item))
                link = html.escape(item.link, quote=True)
                lines.append(f"  - <b>{source}</b> · {translated} · <a href=\"{link}\">원문</a>")
    else:
        lines.extend(["", "<b>무엇이 바뀌었나</b>", "• 공급·운송 관련 새 확정 뉴스 없음"])

    if new_signals or cleared_signals:
        lines.extend(["", "<b>가격 신호</b>"])
        for signal in sorted(new_signals):
            lines.append(f"• <b>신규 진입</b>  {html.escape(core.signal_label(signal))}")
        for signal in sorted(cleared_signals):
            lines.append(f"• <b>조건 이탈</b>  {html.escape(core.signal_label(signal, cleared=True))}")
        for quote in quotes.values():
            lines.append(f"• {html.escape(core.format_quote(quote))}")
        lines.append("• 지정 원천의 검증 규칙을 통과한 가격만 표시")

    korea, investment, one_line = core.impact_text(context)
    lines.extend(
        [
            "",
            "<b>한국 영향</b>",
            f"• {html.escape(korea)}",
            "",
            "<b>투자 포인트</b>",
            f"• {html.escape(investment)}",
            "",
            "<b>다음 확인</b>",
            f"• {html.escape(_next_check(context))}",
            "",
            f"<b>핵심 한 줄</b>  {html.escape(one_line)}",
        ]
    )

    metadata = {
        "version": 11,
        "kind": "material_change",
        "context": context,
        "news_event_ids": [group["event_id"] for group in groups],
        "new_market_signals": sorted(new_signals),
        "cleared_market_signals": sorted(cleared_signals),
        "quotes": {key: asdict(quote) for key, quote in quotes.items()},
        "telegram_format": "HTML",
        "headline_language": "ko",
        "raw_urls_hidden": True,
        "readability_layout": [
            "한눈에", "무엇이 바뀌었나", "가격 신호", "한국 영향", "투자 포인트", "다음 확인", "핵심 한 줄"
        ],
    }
    return title, "\n".join(lines), metadata


def build_setup_test_v11(quotes):
    title, body, metadata = v10.build_setup_test_v10(quotes)
    title = "✅ LNG·천연가스 감시 가독성 규칙 v11 적용"
    body += (
        "\n\n<b>표시 순서</b>"
        "\n• 판정 → 현재 단계 → 핵심 변화 → 근거 → 가격 → 한국 영향 → 투자 포인트 → 다음 확인"
        "\n• 정보량은 줄이지 않고 핵심어·단계·숫자를 먼저 보이게 재배치"
        "\n• 알래스카 LNG는 정책 발언과 실제 계약/FID/발주를 첫 화면에서 분리"
    )
    metadata["version"] = 11
    return title, body, metadata


# v10의 탐지·검증 로직은 유지하고 출력 포맷만 v11로 교체한다.
core.fetch_news_item_set = v10.fetch_news_item_set_v10
core.confirmed_news_groups = v10.confirmed_news_groups_v10
core.category_label = v9.category_label_v9
core.classify_polarity = v9.classify_polarity_v9
core.classify_alert_context = v9.classify_alert_context_v9
core.impact_text = v9.impact_text_v9
core.fetch_market_quotes = v9.v8.v7.fetch_market_quotes_v7
core.format_quote = v9.v8.v7.v6.format_quote_v6
core.signal_label = v9.signal_label_v9
core.build_regular_alert = build_regular_alert_v11
core.build_setup_test = build_setup_test_v11


if __name__ == "__main__":
    raise SystemExit(core.main())
