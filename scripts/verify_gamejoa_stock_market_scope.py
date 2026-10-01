#!/usr/bin/env python3
"""Keep domestic and international market news in the source-verified radar."""

from datetime import datetime, timedelta, timezone
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent))
import gamejoa_preopen_news_radar_fda_quality_runner as production
from khs_article_detail import extract_article_detail

radar = production.runner
NOW = datetime(2026, 10, 1, 17, 0, tzinfo=timezone(timedelta(hours=9)))
CASES = (
    (
        "유럽중앙은행, 기준금리 0.25%포인트 인하",
        "유럽중앙은행은 기준금리를 0.25%포인트 인하했습니다. 물가 둔화에 대응해 통화정책을 조정했습니다.",
        "rates_fx_liquidity",
    ),
    (
        "일본은행, 기준금리 동결 결정",
        "일본은행은 기준금리를 연 0.5%로 동결했습니다. 추가 인상 시점은 임금과 물가 지표를 확인한 뒤 판단합니다.",
        "rates_fx_liquidity",
    ),
    (
        "미국 비농업 고용지표 예상 하회…국채금리 하락",
        "미국 비농업 고용이 예상치를 밑돌았습니다. 미 국채금리는 고용지표 발표 후 하락했습니다.",
        "rates_fx_liquidity",
    ),
    (
        "美 8월 PCE 물가 전년 대비 3.4% 상승",
        "국제유가 변동성으로 미국 국채금리가 급등하는 가운데 미 물가지수가 상승폭을 줄였습니다. "
        "8월 개인소비지출(PCE) 물가지수는 전년 대비 3.4% 상승하며 예상치 3.7%를 밑돌았습니다. "
        "전달 대비로는 0.3% 상승했습니다. 근원PCE는 3.0% 올랐습니다.",
        "rates_fx_liquidity",
    ),
    (
        "중국, 유럽산 자동차 관세 인상 검토",
        "중국 정부는 유럽산 자동차의 수입 관세 인상을 검토 중입니다. 적용 범위와 시행일은 아직 확정하지 않았습니다.",
        "trade_policy_supply_chain",
    ),
    (
        "국제유가 급등…원유 공급 차질 확대",
        "국제유가가 원유 공급 차질 확대로 급등했습니다. 산유국 생산과 해상 운송 회복 여부가 남은 변수입니다.",
        "energy_commodities_transport",
    ),
    (
        "이란 추가 공격 경고…호르무즈 통항 차질 우려",
        "미국의 이란 추가 공격 경고에 호르무즈 통항 차질 우려가 커졌습니다. 유조선 운항과 휴전 유지 여부는 확인 중입니다.",
        "geopolitical_risk",
    ),
    (
        "자동차 부품사, 연간 영업이익 가이던스 상향",
        "자동차 부품사는 신규 고객 주문 증가를 반영해 연간 영업이익 가이던스를 상향했습니다. 공급계약 물량은 단계적으로 납품합니다.",
        "earnings_investment",
    ),
    (
        "국내 식품기업, 영업이익 증가·배당 확대",
        "국내 식품기업은 원가 하락으로 영업이익이 증가했다고 발표했습니다. 이사회는 배당 확대를 결정했습니다.",
        "earnings_investment",
    ),
    (
        "외국인 ETF 순매수 증가…연기금 자금 유입",
        "외국인의 국내 ETF 순매수가 증가했습니다. 연기금 자금도 유입됐으며 거래대금과 설정액은 별도 지표로 집계했습니다.",
        "capital_flows",
    ),
    (
        "원·달러 환율, 5.6원 오른 1358.4원 마감",
        "원·달러 환율은 5.6원 오른 1358.4원으로 거래를 마무리했다. "
        "미국과 이란의 협상이 지지부진하며 국제유가가 반등하는 상황도 위험회피 심리를 자극했다.",
        "rates_fx_liquidity",
    ),
    (
        "증시 조정에 일단 주차…파킹형 ETF 4종에 1.2조 몰렸다",
        "주요 주식형 상장지수펀드(ETF)가 최근 일주일간 마이너스 수익률을 기록한 가운데 "
        "파킹형 ETF 4종에 약 1조2000억원이 유입됐다. 증시 방향성을 살피는 투자 대기자금이 모였다.",
        "capital_flows",
    ),
    (
        "SK하이닉스, 솔리다임 자금조달 방식 미정…주주가치 최우선",
        "SK하이닉스는 솔리다임의 경쟁력 강화를 위한 여러 방안을 검토하고 있으나 확정된 사항은 없다고 설명했다. "
        "AI 데이터센터 수요 확대에 따라 생산능력과 기술 경쟁력 확보를 위한 투자를 검토하고 있다. "
        "고대역폭메모리(HBM), 서버용 D램, eSSD 투자 수요를 고려하되 모든 의사결정에서 주주가치 제고를 우선한다고 밝혔다.",
        "earnings_investment",
    ),
)


def main() -> int:
    failures = []
    for index, (title, body, channel) in enumerate(CASES):
        row = {
            "source": "국내외 증시 감시 회귀검사", "layer": "trusted", "publisher": "연합뉴스",
            "title": title, "source_title": title, "source_body": body,
            "source_abstract": body, "summary": body, "body_verified": True,
            "published": NOW, "link": f"https://www.yna.co.kr/view/market-scope-fixture-{index}",
        }
        alert = production.contract.strict.classify(row, NOW)
        if not alert:
            failures.append(f"classification_missing:{title}")
            continue
        if channel not in radar.stock_market_channels(alert):
            failures.append(f"source_channel_missing:{title}")
        selected = radar.quality_display_alerts([alert], 1)
        if not selected:
            normalized = radar.normalize_alert_for_output(alert)
            failures.append(
                f"final_selection_missing:{title}:{alert.get('_exclusion_reason')}:"
                f"headline={normalized.get('news')}:core={normalized.get('telegram_core_fact')}"
            )
        elif channel not in selected[0].get("stock_market_channels", []):
            failures.append(f"channel_audit_missing:{title}")
        else:
            if selected[0].get("news") != title:
                failures.append(f"verified_article_title_overwritten_by_legacy_overlay:{title}")
            block = radar.compact_alert(selected[0], 1, NOW, {}, {})
            block_errors = radar.compact_alert_block_errors(block)
            if block_errors:
                failures.append(f"rendered_summary_invalid:{title}:{block_errors}")
            if "8월 PCE" in title:
                core = selected[0].get("telegram_core_fact") or ""
                if not all(term in core for term in ("PCE", "3.4%", "3.7%")):
                    failures.append(f"macro_release_lost_indicator_and_comparison:{core}")
                if "중동발" in core or "국내 물가" in core:
                    failures.append(f"macro_release_replaced_by_oil_template:{core}")
                poisoned = dict(selected[0])
                poisoned["telegram_core_fact"] = "중동발 유가 불안이 국내 물가·환율·금리 부담으로 번지고 있습니다."
                if radar.source_output_aligned(poisoned):
                    failures.append("pce_oil_template_passed_source_alignment")
                bad_block = f"1) {title}\n- 핵심: {poisoned['telegram_core_fact']}\n"
                if "macro_release_mismatch" not in radar.compact_alert_block_errors(bad_block):
                    failures.append("pce_oil_template_passed_final_send_guard")
            if "솔리다임" in title and "280%" in str(selected[0].get("telegram_core_fact")):
                failures.append("unrelated_memory_revenue_template_replaced_solidigm_article")

    for title, body in (
        ("SNS에서 화제인 요리사", "한 유명 요리사가 새로운 요리법을 공개했습니다."),
        ("시민문화축제 일정 안내", "지역 축제가 열립니다. 투자와 금리라는 행사 이름이 언급됐습니다."),
        ("유럽중앙은행 직원 문화행사", "중앙은행 직원들이 미술전시회에 참가했습니다."),
        ("유럽중앙은행 직원 문화행사 발표", "직원 문화행사 일정을 발표했습니다."),
        ("푸틴, 문화축제 일정 발표", "러시아의 문화축제 일정을 발표했습니다."),
        ("외국인 문화행사 참가 증가", "외국인의 문화행사 참가가 증가했습니다."),
    ):
        alert = {
            "source_title": title, "source_abstract": body,
            "source": "연준 관세 전쟁 기업 실적 감시",
            "policy_plain_summary": "금리 인하와 반도체 실적 상향 발표입니다.",
            "korea_market_impact": "삼성전자·SK하이닉스 수급에 영향을 줍니다.",
        }
        if radar.stock_market_channels(alert):
            failures.append(f"generated_commentary_leaked_into_market_channel:{title}")

    for title, summary in (
        ("ECB cuts interest rates after inflation falls", "The European Central Bank cut interest rates as inflation fell."),
        ("US payrolls miss forecasts, Treasury yields fall", "Payrolls rose less than expected and Treasury yields fell."),
        ("Bank of Japan announces interest rate decision", "The Bank of Japan kept interest rates unchanged."),
    ):
        row = {"title": title, "summary": summary, "publisher": "Reuters", "layer": "trusted", "published": NOW}
        alert = radar.base.classify(row, NOW)
        if not alert or "할인율" not in alert.get("impacts", []):
            failures.append(f"foreign_macro_discovery_missing:{title}")
        elif not radar.has_stock_market_link(alert):
            failures.append(f"foreign_macro_requires_korean_company:{title}")

    marked = {"news": "이란 공격", "realtime_policy_lane": True}
    ordinary = {"news": "기업 실적"}
    for live_mode in (True, False):
        remaining, routed = production.telegram.partition_realtime_policy_alerts([marked, ordinary], live_mode)
        if remaining != [marked, ordinary] or routed:
            failures.append(f"policy_news_blackhole:live={live_mode}")
    if radar.macro_release_core_aligned("PCE 물가 3% 상승", "PCE 물가는 13% 상승했습니다."):
        failures.append("macro_percent_substring_accepted_as_equal_value")
    if radar.macro_release_core_aligned("CPI 물가 -0.1%", "소비자물가는 0.1% 변동했습니다."):
        failures.append("macro_negative_percent_sign_lost")
    if not radar.macro_release_core_aligned("PCE 물가 3.0% 상승", "개인소비지출 물가는 3% 상승했습니다."):
        failures.append("macro_equivalent_percent_and_indicator_alias_rejected")

    release = {
        "source_title": "美 8월 PCE 물가 전년 대비 3.4% 상승",
        "published": "2026-10-01T18:08:00+09:00",
        "link": "https://www.mk.co.kr/news/world/release-fixture",
    }
    syndicated = {
        **release,
        "source_title": "美 8월 PCE 물가 3.4%↑…전망 밑돌며 10월 금리인상 부담 완화(종합)",
        "link": "https://www.yna.co.kr/view/release-fixture",
    }
    release_key = production.telegram.macro_release_theme(release)
    if not release_key or release_key != production.telegram.macro_release_theme(syndicated):
        failures.append("same_macro_release_not_deduplicated_across_publishers")
    if not set(production.telegram.alert_seen_keys(release)).intersection(
        production.telegram.alert_seen_keys(syndicated)
    ):
        failures.append("same_macro_release_has_no_shared_seen_key")
    legacy_state = {"seen": {"legacy": {
        "title": release["source_title"], "first_seen_kst": release["published"],
    }}}
    production.telegram.migrate_seen_title_aliases(legacy_state)
    if f"event:{production.telegram.digest_seen(release_key)}" not in legacy_state["seen"]:
        failures.append("legacy_macro_release_seen_state_not_migrated")
    for title in (
        "美 8월 PCE 물가 3.2% 상승", "美 9월 PCE 물가 3.4% 상승",
        "美 8월 근원 PCE 물가 3.4% 상승", "중국 8월 CPI 물가 3.4% 상승",
        "美 8월 PCE 물가 전월 대비 3.4% 상승",
        "美 8월 PCE 물가 -3.4% 하락",
    ):
        if production.telegram.macro_release_theme({**release, "source_title": title}) == release_key:
            failures.append(f"new_macro_fact_incorrectly_deduplicated:{title}")
    if production.telegram.macro_release_theme({
        **release, "source_title": "美 8월 PCE 물가 3.4% 상승 예상",
    }):
        failures.append("macro_forecast_treated_as_announced_release")

    article_body = (
        "신한자산운용은 커버드콜 ETF의 9월 분배금으로 주당 170원을 지급했다고 밝혔다. "
        "이 상품은 코스피200 구성 종목의 배당수익과 주간 옵션 프리미엄을 재원으로 활용한다. "
        "지난 3월 상장 후 매달 분배를 이어가고 있으며 이번 월 분배율은 1.43%다. "
        "일반계좌와 연금계좌의 과세 방식은 다르므로 지급 금액과 수익률은 구분해 집계한다."
    )
    fixture_html = (
        '<meta property="og:title" content="커버드콜 ETF 분배금 지급">'
        f'<article>{article_body}<br>Copyright © NEWSIS.COM, 무단 전재 및 재배포 금지'
        '<br>많이 본 뉴스<br>이란 추가 공격 임박, 원전 투자, 메모리 반독점 소송</article>'
    )
    detail = extract_article_detail(fixture_html, "커버드콜 ETF 분배금 지급")
    if not detail.get("body_verified") or "170원" not in detail.get("body", ""):
        failures.append("real_article_lost_while_trimming_related_stories")
    if any(term in detail.get("body", "") for term in ("추가 공격", "반독점", "Copyright")):
        failures.append("publisher_footer_or_related_stories_leaked_into_article_body")

    financial_core = radar.financial_result_fact("마이크론 분기 실적 발표", [
        "마이크론의 4분기 매출은 542억달러로 집계되며 시장 예상치 510억달러를 웃돌았다.",
    ])
    if not radar.core_sentence_is_complete(financial_core) or "전망" in financial_core or "542억달러" not in financial_core:
        failures.append(f"reported_foreign_revenue_lost_or_changed_to_forecast:{financial_core}")
    conversion = {"amounts": [
        {"original": "542억달러", "krw_text": "73조원", "krw_value": 73e12},
        {"original": "33.42달러", "krw_text": "4.5만원", "krw_value": 45000},
    ]}
    converted = radar.compact_converted_core(financial_core, conversion)
    if not radar.core_sentence_is_complete(converted) or "매출" not in converted or "542억달러(약 73조원)" not in converted:
        failures.append(f"foreign_conversion_lost_metric_context:{converted}")
    if "33.42달러" in converted:
        failures.append("unrelated_abstract_amount_appended_to_compact_core")
    if radar.core_sentence_is_complete("를 넘어섰다 542억달러(약 73조원)입니다."):
        failures.append("clipped_foreign_amount_fragment_passed_complete_sentence_guard")
    if radar.core_sentence_is_complete("삼성전자는 그동안 자사주를 매입해왔는데요."):
        failures.append("broadcast_conversation_fragment_passed_summary_guard")
    if "기자" in radar.clean_article_summary_text("[기자] 네, 삼성전자가 자사주 매입을 마무리했습니다."):
        failures.append("broadcast_speaker_label_not_removed_from_summary")
    bad_block = "1) 자사주 매입 마무리\n- 핵심: [기자] 매입이 마무리됐습니다.\n"
    if "article_ui_boilerplate" not in radar.compact_alert_block_errors(bad_block):
        failures.append("per_article_guard_failed_to_block_reporter_label")

    searches = dict(radar.base.trusted_query_plan())
    for name in ("글로벌 금리·물가·고용·유동성", "글로벌 증시 실적·투자·자본행사", "글로벌 통상·제재·원자재 공급"):
        if name not in searches:
            failures.append(f"global_search_missing:{name}")
    industry_query = dict(radar.KOREAN_BUSINESS_SEARCH_SOURCES).get("전업종 실적·수주·투자·주주환원", "")
    if not industry_query or any(term in industry_query for term in ("삼성전자", "SK하이닉스", "HBM")):
        failures.append("all_industry_search_is_missing_or_company_restricted")
    workflow = (Path(__file__).resolve().parents[1] / ".github/workflows/gamejoa-preopen-news-radar.yml").read_text(encoding="utf-8")
    if "python scripts/verify_gamejoa_stock_market_scope.py" not in workflow:
        failures.append("stock_market_scope_guard_not_in_production")

    if failures:
        print("GAMEJOA stock-market scope contract failed:")
        for failure in failures:
            print(f"- {failure}")
        return 1
    print("GAMEJOA stock-market scope contract OK: domestic/international, six channels, source evidence, radar policy delivery.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
