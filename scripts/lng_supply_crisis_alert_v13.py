#!/usr/bin/env python3
from __future__ import annotations

import lng_supply_crisis_alert_v2 as core
import lng_supply_crisis_alert_v12 as v12


def build_regular_alert_v13(groups, quotes, new_signals, cleared_signals):
    title, body, metadata = v12.build_regular_alert_v12(groups, quotes, new_signals, cleared_signals)
    evidence_text = " ".join(
        f"{item.title} {item.source}"
        for group in groups
        for item in group.get("evidence", [])
    ).lower()
    if ("manitoba" in evidence_text or "매니토바" in evidence_text) and ("gas turbine" in evidence_text or "가스터빈" in evidence_text or "ge vernova" in evidence_text):
        details = [
            "<b>핵심 내용</b>",
            "• <b>사업</b> 매니토바 하이드로 브랜던 발전소 확장 · 총 <b>30억 캐나다달러</b> 규모 · 공식 제안 설비용량 <b>750MW</b>",
            "• <b>장비</b> 가스터빈 <b>3기</b>",
            "• <b>공급사/단계</b> GE 버노바와 <b>예약계약</b>으로 공급 순번 확보 · 최종 구매 확정은 아님",
            "• <b>차질 원인</b> 캐나다·미국 무역전쟁과 미국 업체 조달정책으로 주정부가 구매를 재검토",
            "• <b>대안</b> 지멘스 에너지도 후보군에 포함됐던 것으로 보도 · 공급자 변경 시 비용·일정 영향 확인 필요",
            "• <b>납기</b> 글로벌 가스터빈 수요 급증으로 제조·납품 대기가 <b>최대 7년</b>에 이를 수 있다는 업계 추정",
            "• <b>구분</b> 예약계약 ≠ 최종 발주 · 재검토 ≠ 계약 취소 확정",
        ]
        lines = body.splitlines()
        try:
            pos = lines.index("<b>한국 영향</b>")
            lines[pos:pos] = ["", *details, ""]
        except ValueError:
            lines.extend(["", *details])
        body = "\n".join(lines)
    metadata["version"] = 13
    metadata["required_procurement_facts"] = ["사업규모", "용량", "장비수", "공급사", "계약단계", "차질원인", "대안", "납기", "확정여부"]
    return title, body, metadata


def build_setup_test_v13(quotes):
    title, body, metadata = v12.build_setup_test_v12(quotes)
    metadata["version"] = 13
    return title, body, metadata


core.fetch_news_item_set = v12.v11.v10.fetch_news_item_set_v10
core.confirmed_news_groups = v12.confirmed_news_groups_v12
core.category_label = v12.category_label_v12
core.classify_polarity = v12.classify_polarity_v12
core.classify_alert_context = v12.classify_alert_context_v12
core.impact_text = v12.impact_text_v12
core.fetch_market_quotes = v12.v11.v9.v8.v7.fetch_market_quotes_v7
core.format_quote = v12.v11.v9.v8.v7.v6.format_quote_v6
core.signal_label = v12.v11.v9.signal_label_v9
core.build_regular_alert = build_regular_alert_v13
core.build_setup_test = build_setup_test_v13

if __name__ == "__main__":
    raise SystemExit(core.main())
