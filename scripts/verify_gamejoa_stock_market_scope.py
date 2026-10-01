#!/usr/bin/env python3
"""Keep domestic and international market news in the source-verified radar."""

from datetime import datetime, timedelta, timezone
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent))
import gamejoa_preopen_news_radar_fda_quality_runner as production

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
            block = radar.compact_alert(selected[0], 1, NOW, {}, {})
            block_errors = radar.compact_alert_block_errors(block)
            if block_errors:
                failures.append(f"rendered_summary_invalid:{title}:{block_errors}")

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
