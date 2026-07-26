#!/usr/bin/env python3
"""Guard the GAMEJOA preopen radar delivery contract.

The radar must be delivered to the hs8879 policy Telegram lane. This guard is
intentionally strict so future edits cannot silently reroute the morning radar
to another bot or make Telegram failures look successful.
"""

from __future__ import annotations

import datetime as dt
import importlib
import os
import re
import sys
import urllib.parse
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]

WORKFLOW_FILES = [
    ROOT / ".github" / "workflows" / "gamejoa-preopen-news-radar.yml",
    ROOT / ".github" / "workflows" / "gamejoa-preopen-news-radar-test.yml",
]

RUNNER_FILE = ROOT / "scripts" / "gamejoa_preopen_news_radar_full_compact_runner.py"
SEMISUPPLY_RUNNER_FILE = ROOT / "scripts" / "gamejoa_preopen_news_radar_semisupply_runner.py"
TELEGRAM_RUNNER_FILE = ROOT / "scripts" / "gamejoa_preopen_news_radar_telegram_runner.py"
BASE_RUNNER_FILE = ROOT / "scripts" / "gamejoa_preopen_news_radar_runner.py"
GENERATED_REPORT_GUARD_FILE = ROOT / "scripts" / "verify_gamejoa_generated_report.py"
RUNTIME_DELIVERY_GUARD_FILE = ROOT / "scripts" / "verify_gamejoa_delivery_result.py"
MAINTENANCE_CONTRACT_FILE = ROOT / "docs" / "gamejoa_maintenance_contract.md"
PRODUCTION_RUNNER = "gamejoa_preopen_news_radar_fda_quality_runner"
LOCKED_TELEGRAM_MODULE = "gamejoa_preopen_news_radar_full_compact_runner"
COMPACT_PROSE_PREFIXES = (
    "- 핵심:",
)
COMPACT_PROSE_LIMITS = {
    "- 핵심:": 50,
}
FORBIDDEN_COMPACT_MARKERS = (
    "- 기준/시각:",
    "- 경로/섹터:",
    "- 투자 포인트:",
    "- 의사결정 영향:",
    "- 한국장:",
    "- 반영/반대:",
    "- 실패 신호:",
)

REQUIRED_WORKFLOW_SNIPPETS = [
    "TELEGRAM_BOT_TOKEN: ${{ secrets.KHS_POLICY_TELEGRAM_BOT_TOKEN }}",
    "TELEGRAM_CHAT_ID: ${{ secrets.KHS_POLICY_TELEGRAM_CHAT_ID }}",
    'SEND_TELEGRAM: "true"',
    'RADAR_TRENDFORCE_RESEARCH_MAX_AGE_DAYS: "3"',
    'PREOPEN_SEND_WINDOW_START_KST: "05:30"',
    "allow_off_window_telegram:",
    "ALLOW_OFF_WINDOW_TELEGRAM:",
    'SEND_EMPTY_RADAR: "false"',
    "radar_run_mode:",
    "RADAR_RUN_MODE:",
    "Preflight",
    "python scripts/verify_gamejoa_generated_report.py",
    "python scripts/verify_gamejoa_delivery_result.py",
    "KHS_SOURCE_PROXY_URL:",
    "KHS_SOURCE_PROXY_FIRST:",
    'RADAR_QUERY_FETCH_WORKERS: "4"',
    'RADAR_DISPLAY_LIMIT: "7"',
    'GAMEJOA_KOREAN_BUSINESS_DETAIL_LIMIT: "72"',
    'GAMEJOA_KOREAN_BUSINESS_DETAIL_WORKERS: "8"',
]

REQUIRED_PRODUCTION_WORKFLOW_SNIPPETS = [
    "Commit GAMEJOA radar seen state",
    "data/gamejoa_preopen_news_radar_seen.json",
]

FORBIDDEN_WORKFLOW_SNIPPETS = [
    "GAMEJOA_TELEGRAM_BOT_TOKEN",
    "GAMEJOA_TELEGRAM_CHAT_ID",
    "secrets.TELEGRAM_BOT_TOKEN",
    "secrets.TELEGRAM_CHAT_ID",
    "|| secrets.KHS_POLICY_TELEGRAM_BOT_TOKEN",
    "|| secrets.KHS_POLICY_TELEGRAM_CHAT_ID",
]

REQUIRED_RUNNER_SNIPPETS = [
    "guard_preopen_report(text)",
    "preopen_send_window_open",
    "raise RuntimeError(\"Telegram delivery blocked:",
    "raise RuntimeError(f\"Telegram delivery failed:",
    "forbidden_compact_marker",
    "headline_repeated_as_summary",
    "generic_policy_explanation_displayed",
    "write_delivery_status(\"skipped_empty\"",
    "write_delivery_status(\"sent\"",
    "RADAR_RUN_MODE",
    "telegram.final_alerts_for_output = quality_display_alerts",
    "telegram.canonical_alert_for_seen = normalize_alert_for_output",
    "source_output_aligned(normalized)",
    "SOURCE_OUTPUT_ALIGNMENT_THEMES",
    "korea_market_link_guard",
    "federal_register_uae_ear",
    "ALLOW_OFF_WINDOW_TELEGRAM",
    "https://rss.etoday.co.kr/eto/etoday_news_all.xml",
    "https://rss.etoday.co.kr/eto/market_news.xml",
    "https://rss.etnews.com/Section901.xml",
    "https://rss.etnews.com/Section902.xml",
    "KOREAN_BUSINESS_SEARCH_SOURCES",
    "edaily.co.kr",
    "mk.co.kr",
    "mt.co.kr",
    "biz.heraldcorp.com",
    "yna.co.kr",
    "hankyung.com",
    "build_hyundai_nvidia_meeting_alert",
    "build_single_stock_leverage_rule_alert",
    "build_global_semiconductor_market_alert",
    "build_ai_infrastructure_steel_alert",
    "build_global_semiconductor_leader_signal",
    "build_skhynix_earnings_consensus_alert",
    "build_kstartup_global_vc_access_alert",
    "build_samsung_openai_meeting_alert",
    "build_korea_nvidia_ecosystem_alert",
    "build_bigtech_ai_layoff_alert",
    "build_korea_oil_fx_inflation_alert",
    "build_fomc_rate_outlook_alert",
    "build_china_memory_ipo_alert",
    "build_korea_etf_net_buy_alert",
    "build_ai_factory_deployment_alert",
    "build_sk_ms_memory_supply_alert",
    'supply_chain_theme": f"us_semiconductor_selloff:',
    "GAMEJOA_CORE_MAX_CHARS = 50",
    "semantic_event_theme",
    "collect_fx_snapshot",
    "build_alert_fx_conversion",
    "foreign_currency_not_converted",
    "📰 실시간 핵심 뉴스 레이더 ·",
]


def compact_prose_errors(body: str) -> list[str]:
    errors: list[str] = []
    for line in body.splitlines():
        for prefix in COMPACT_PROSE_PREFIXES:
            if line.startswith(prefix):
                value = line.removeprefix(prefix).strip()
                limit = COMPACT_PROSE_LIMITS[prefix]
                if len(value) > limit:
                    errors.append(f"{prefix} {len(value)}자")
                if "…" in value or "..." in value:
                    errors.append(f"{prefix} 말줄임")
                if re.search(r"\[[^\]]{0,60}\s*기자\]", value):
                    errors.append(f"{prefix} 매체·기자 표기")
    return errors

REQUIRED_TELEGRAM_RUNNER_SNIPPETS = [
    "gamejoa_preopen_news_radar_seen.json",
    "gamejoa_preopen_news_radar_delivery.json",
    "filter_previously_seen_alerts(classified, now, \"live\")",
    "filter_alerts_for_run_mode(classified, now, live_mode)",
    "preopen_digest_seen_bypass",
    "seen_filter_scope",
    "_preopen_live_seen_bypass",
    "record_seen_alerts(final_alerts, now)",
    "delivery_confirmed_sent()",
    "reset_delivery_status()",
    "seen_state_not_recorded",
    "preopen_send_window_open(now)",
    "RADAR_RUN_MODE",
    "final_alerts_for_output(deduped, limit)",
    "canonical_alert_for_seen",
    'canonical.get("supply_chain_theme")',
    "migrate_seen_title_aliases",
    '"selection_diagnostics": diagnostics',
    '"source_failures": source_failures',
]

REQUIRED_SEMISUPPLY_RUNNER_SNIPPETS = [
    "upstream_collect_items = contract.strict.collect_items",
    "rows, notes = upstream_collect_items(now)",
]

FORBIDDEN_SEMISUPPLY_RUNNER_SNIPPETS = [
    "rows, notes = base.collect_items(now)",
]

REQUIRED_GENERATED_GUARD_SNIPPETS = [
    "prod.runner.guard_preopen_report(text)",
    "REQUIRED_ITEM_MARKERS",
    "FORBIDDEN_TEXT",
    "GAMEJOA generated report quality OK",
    "report/JSON selected count mismatch",
    "selection_diagnostics",
    "📰 실시간 핵심 뉴스 레이더 ·",
]

REQUIRED_RUNTIME_GUARD_SNIPPETS = [
    "runtime report/JSON count mismatch",
    "runtime Telegram status mismatch",
    "GAMEJOA runtime delivery verified",
    "ALLOW_OFF_WINDOW_TELEGRAM",
]

REQUIRED_MAINTENANCE_CONTRACT_SNIPPETS = [
    "원인 규명",
    "재발 방지 회귀 테스트",
    "반영 완료",
    "재검증 완료",
    "실제 송출 상태",
    "skipped_empty",
    "Actions 성공만으로 완료 처리하지 않는다",
    "실제 신규 알림 송출 미관찰",
    "전날 장전판 항목 재송출 금지",
]

REQUIRED_BASE_SOURCE_SNIPPETS = [
    "Federal Register FERC",
    "federal-energy-regulatory-commission",
    "Federal Register Commerce",
    "commerce-department",
    "from khs_source_fetch import fetch_text",
    "def trusted_query_plan",
    "CORE_QUERY_BUNDLES",
    "def news_search_url",
    "www.bing.com/news/search",
    "def unwrap_news_link",
    'netloc.lower().endswith("bing.com")',
    "def source_content_text",
]


def main() -> int:
    errors: list[str] = []
    for path in WORKFLOW_FILES:
        text = path.read_text(encoding="utf-8")
        for snippet in REQUIRED_WORKFLOW_SNIPPETS:
            if snippet not in text:
                errors.append(f"{path.relative_to(ROOT)} missing required snippet: {snippet}")
        if path.name == "gamejoa-preopen-news-radar.yml":
            for snippet in REQUIRED_PRODUCTION_WORKFLOW_SNIPPETS:
                if snippet not in text:
                    errors.append(f"{path.relative_to(ROOT)} missing required snippet: {snippet}")
        for snippet in FORBIDDEN_WORKFLOW_SNIPPETS:
            if snippet in text:
                errors.append(f"{path.relative_to(ROOT)} contains forbidden reroute snippet: {snippet}")

    runner = RUNNER_FILE.read_text(encoding="utf-8")
    for snippet in REQUIRED_RUNNER_SNIPPETS:
        if snippet not in runner:
            errors.append(f"{RUNNER_FILE.relative_to(ROOT)} missing required guard snippet: {snippet}")
    if "📰 GAMEJOA 실시간 핵심 뉴스 레이더 ·" in runner:
        errors.append("legacy GAMEJOA live radar title remains in the production renderer")

    semisupply_runner = SEMISUPPLY_RUNNER_FILE.read_text(encoding="utf-8")
    for snippet in REQUIRED_SEMISUPPLY_RUNNER_SNIPPETS:
        if snippet not in semisupply_runner:
            errors.append(
                f"{SEMISUPPLY_RUNNER_FILE.relative_to(ROOT)} missing upstream collector guard: {snippet}"
            )
    for snippet in FORBIDDEN_SEMISUPPLY_RUNNER_SNIPPETS:
        if snippet in semisupply_runner:
            errors.append(
                f"{SEMISUPPLY_RUNNER_FILE.relative_to(ROOT)} bypasses upstream collector: {snippet}"
            )

    telegram_runner = TELEGRAM_RUNNER_FILE.read_text(encoding="utf-8")
    for snippet in REQUIRED_TELEGRAM_RUNNER_SNIPPETS:
        if snippet not in telegram_runner:
            errors.append(f"{TELEGRAM_RUNNER_FILE.relative_to(ROOT)} missing required guard snippet: {snippet}")

    base_runner = BASE_RUNNER_FILE.read_text(encoding="utf-8")
    for snippet in REQUIRED_BASE_SOURCE_SNIPPETS:
        if snippet not in base_runner:
            errors.append(f"{BASE_RUNNER_FILE.relative_to(ROOT)} missing required source snippet: {snippet}")

    if not GENERATED_REPORT_GUARD_FILE.exists():
        errors.append(f"{GENERATED_REPORT_GUARD_FILE.relative_to(ROOT)} is missing")
    else:
        generated_guard = GENERATED_REPORT_GUARD_FILE.read_text(encoding="utf-8")
        for snippet in REQUIRED_GENERATED_GUARD_SNIPPETS:
            if snippet not in generated_guard:
                errors.append(f"{GENERATED_REPORT_GUARD_FILE.relative_to(ROOT)} missing required guard snippet: {snippet}")
        if "📰 GAMEJOA 실시간 핵심 뉴스 레이더 ·" in generated_guard:
            errors.append("generated-report guard still accepts the legacy GAMEJOA live title")

    if not RUNTIME_DELIVERY_GUARD_FILE.exists():
        errors.append(f"{RUNTIME_DELIVERY_GUARD_FILE.relative_to(ROOT)} is missing")
    else:
        runtime_guard = RUNTIME_DELIVERY_GUARD_FILE.read_text(encoding="utf-8")
        for snippet in REQUIRED_RUNTIME_GUARD_SNIPPETS:
            if snippet not in runtime_guard:
                errors.append(f"{RUNTIME_DELIVERY_GUARD_FILE.relative_to(ROOT)} missing required guard snippet: {snippet}")

    if not MAINTENANCE_CONTRACT_FILE.exists():
        errors.append(f"{MAINTENANCE_CONTRACT_FILE.relative_to(ROOT)} is missing")
    else:
        maintenance_contract = MAINTENANCE_CONTRACT_FILE.read_text(encoding="utf-8")
        for snippet in REQUIRED_MAINTENANCE_CONTRACT_SNIPPETS:
            if snippet not in maintenance_contract:
                errors.append(
                    f"{MAINTENANCE_CONTRACT_FILE.relative_to(ROOT)} "
                    f"missing required maintenance invariant: {snippet}"
                )

    sys.path.insert(0, str(ROOT / "scripts"))
    production = importlib.import_module(PRODUCTION_RUNNER)
    compact = importlib.import_module(LOCKED_TELEGRAM_MODULE)
    runtime_delivery = importlib.import_module("verify_gamejoa_delivery_result")
    send_module = getattr(production.telegram.send_telegram, "__module__", "")
    compact_module = getattr(production.telegram.compact_report, "__module__", "")
    final_selection_module = getattr(production.telegram.final_alerts_for_output, "__module__", "")
    canonical_seen_module = getattr(production.telegram.canonical_alert_for_seen, "__module__", "")
    query_plan = production.base.trusted_query_plan()
    if len(query_plan) > 18:
        errors.append(f"trusted query plan is too large for stable polling: {len(query_plan)} > 18")
    required_query_labels = {"트럼프 직접발언/정책", "이란/호르무즈 긴급상황", "반도체/AI/HBM", "K-방산", "국내 정책", "바이오/FDA"}
    query_labels = {name for name, _query in query_plan}
    required_query_labels.add("중국 상무부 수출통제/관세")
    missing_query_labels = sorted(required_query_labels - query_labels)
    if missing_query_labels:
        errors.append(f"trusted query plan missing coverage: {', '.join(missing_query_labels)}")
    korean_source_labels = {name for name, _url, _kind in production.base.SOURCES}
    required_korean_source_labels = {
        "국내 신뢰매체 AI·반도체 협력",
        "국내 신뢰매체 미국 증시·반도체",
        "국내 신뢰매체 자본시장 정책",
        "국내 신뢰매체 산업수요·CAPEX",
        "이데일리 기업·AI",
        "이데일리 미국 증시",
        "매일경제 자본시장",
        "머니투데이 글로벌시장",
        "헤럴드경제 산업수요",
        "현대차·엔비디아 AI 협력",
        "AI 인프라 철강 수요",
    }
    missing_korean_sources = sorted(required_korean_source_labels - korean_source_labels)
    if missing_korean_sources:
        errors.append(
            "Korean trusted-media source coverage missing: "
            + ", ".join(missing_korean_sources)
        )
    for domain in ("edaily.co.kr", "mk.co.kr", "mt.co.kr", "biz.heraldcorp.com"):
        probe = {
            "source": "국내 신뢰매체 회귀점검",
            "publisher": "",
            "link": f"https://{domain}/regression-fixture",
        }
        if not production.runner.is_korean_business_row(probe):
            errors.append(f"Korean trusted domain was not routed to article verification: {domain}")

    target = "https://www.reuters.com/world/example"
    bing_link = "https://www.bing.com/news/apiclick.aspx?" + urllib.parse.urlencode({"url": target})
    bing_fixture = f'''<rss xmlns:news="https://www.bing.com/news/search?q=x&amp;format=rss"><channel><item>
        <title>Reuters test headline</title><link>{bing_link.replace('&', '&amp;')}</link>
        <description>test</description><pubDate>Thu, 09 Jul 2026 19:26:00 GMT</pubDate>
        <news:Source>Reuters</news:Source></item></channel></rss>'''
    parsed_fixture = production.base.parse_rss(bing_fixture, "Bing fixture", "trusted")
    if not parsed_fixture or parsed_fixture[0].get("publisher") != "Reuters":
        errors.append("Bing RSS publisher source was not parsed")
    elif parsed_fixture[0].get("link") != target:
        errors.append("Bing RSS redirect was not unwrapped to the source URL")

    now = production.base.kst_now()
    assert_compact_live_output_contract(compact, now, errors)
    assert_current_high_impact_article_coverage(production, compact, now, errors)
    china_mofcom_row = {
        "source": "Trusted news 중국 상무부 수출통제/관세",
        "layer": "trusted",
        "publisher": "Reuters",
        "title": "China Ministry of Commerce temporarily suspends helium exports starting today",
        "link": "https://www.reuters.com/world/china/example-helium-export-suspension",
        "summary": "MOFCOM said the temporary export suspension applies immediately, pending further notice.",
        "published": now,
    }
    china_alert = production.contract.strict.classify(china_mofcom_row, now)
    if not china_alert:
        errors.append("China MOFCOM helium export suspension was not classified")
    else:
        normalized_china = compact.normalize_alert_for_output(china_alert)
        if "중국 상무부" not in str(normalized_china.get("news") or "") or "헬륨" not in str(normalized_china.get("news") or ""):
            errors.append("China MOFCOM helium alert did not render a specific Korean title")
        if not compact.has_direct_market_path("", normalized_china):
            errors.append("China MOFCOM strategic-material alert lost its Korea-market path")
        if not compact.has_decision_impact(normalized_china):
            errors.append("China MOFCOM strategic-material alert lost its decision-impact classification")

    # Regression fixture for the July 14 UAE EAR rule.  Its official abstract
    # mentions civil nuclear generation among several dual-use items, but the
    # source subject is an EAR treatment rule and must never render as nuclear.
    uae_ear_row = {
        "source": "Federal Register Commerce",
        "layer": "official",
        "publisher": "Federal Register",
        "title": "Enhanced Favorable Treatment for the United Arab Emirates Under the Export Administration Regulations",
        "source_title": "Enhanced Favorable Treatment for the United Arab Emirates Under the Export Administration Regulations",
        "source_document_number": "2026-14132",
        "source_metadata_url": "https://www.federalregister.gov/api/v1/documents/2026-14132",
        "link": "https://www.federalregister.gov/documents/2026/07/14/2026-14132/enhanced-favorable-treatment-for-the-united-arab-emirates-under-the-export-administration",
        "summary": (
            "Final rule 2026-14132. BIS removes the UAE from Country Groups D:3 and D:4 "
            "and adds it to Country Group A:5. Strategic Trade Authorization becomes available "
            "for approved entities, including dual-use items for civil nuclear power generation."
        ),
        "source_abstract": (
            "BIS removes the UAE from Country Groups D:3 and D:4 and adds it to Country Group A:5. "
            "Strategic Trade Authorization becomes available for approved entities, including dual-use "
            "items for civil nuclear power generation."
        ),
        "published": now,
    }
    uae_ear_alert = production.contract.strict.classify(uae_ear_row, now)
    if not uae_ear_alert:
        errors.append("Federal Register UAE EAR final rule was not classified")
    else:
        normalized_uae_ear = compact.normalize_alert_for_output(uae_ear_alert)
        rendered_uae_ear = " ".join(
            str(normalized_uae_ear.get(key) or "")
            for key in ["news", "policy_plain_summary", "investment_view", "korea_market_impact"]
        )
        if "UAE" not in rendered_uae_ear or "수출관리규정" not in rendered_uae_ear or "BIS" not in rendered_uae_ear:
            errors.append(f"Federal Register UAE EAR rule lost its source subject: {rendered_uae_ear}")
        if any(term in str(normalized_uae_ear.get("news") or "") for term in ["원전", "SMR", "가스터빈", "두산"]):
            errors.append(f"Federal Register UAE EAR rule rendered as an unrelated nuclear alert: {normalized_uae_ear.get('news')}")
        if not compact.source_output_aligned(normalized_uae_ear):
            errors.append("Federal Register UAE EAR source/body alignment guard did not pass")
        selected_uae_ear = compact.quality_display_alerts([uae_ear_alert], 5)
        if len(selected_uae_ear) != 1 or not compact.source_output_aligned(selected_uae_ear[0]):
            errors.append("Federal Register UAE EAR alert failed final selection source/body align…14379 tokens truncated…거래일 대비 406.27포인트(5.72%) 내렸고 "
        "코스닥은 42.06포인트(5.32%) 하락해 "
        "두 시장에 매도 사이드카가 발동됐다. 외국인과 기관이 각각 "
        "3조2828억원, 1조9513억원 순매도했다. 삼성전자와 SK하이닉스는 "
        "각각 7.59%, 8.34% 하락했다. 유가와 미국채 금리 상승이 위험선호를 낮췄다."
    )
    kospi_row = dict(
        bigtech_row,
        title=kospi_title,
        source_title=kospi_title,
        source_body=kospi_body,
        source_abstract=kospi_body,
        summary=kospi_body,
        link="https://www.mt.co.kr/stock/2026/07/24/2026072416053045575",
    )
    kospi_alert = production.contract.strict.classify(kospi_row, now)
    if not kospi_alert:
        errors.append("KOSPI selloff article was not classified")
    else:
        kospi_rendered = compact.compact_alert(
            compact.normalize_alert_for_output(kospi_alert),
            1,
            now,
            {},
            {},
        )
        kospi_core = next(
            (line for line in kospi_rendered.splitlines() if line.startswith("- 핵심:")),
            "",
        )
        kospi_view = next(
            (line for line in kospi_rendered.splitlines() if line.startswith("- 투자 포인트:")),
            "",
        )
        if not all(term in kospi_core for term in ("5.72%", "5.32%", "3조2828억원", "1조9513억원")):
            errors.append(f"KOSPI selloff core lost index or flow facts: {kospi_core}")
        if not all(term in kospi_view for term in ("외국인·기관", "유가·금리", "지수 수급")):
            errors.append(f"KOSPI selloff investment point was not market-specific: {kospi_view}")
        if "다음 분기 매출" in kospi_view:
            errors.append(f"KOSPI selloff reused a company-earnings template: {kospi_view}")

    generic_title = "증설은 더딘데 AI 수요는 폭증…삼성전기, MLCC 장기계약 잇달아"
    generic_body = (
        "AI 서버 투자 확대로 고용량 MLCC 수요가 빠르게 늘고 있다. "
        "삼성전기는 글로벌 고객사와 MLCC 장기공급 계약을 확대하고 있으며 생산능력 증설도 검토한다. "
        "다만 구체 계약금액과 고객사별 매출 인식 시점은 공개되지 않았다."
    )
    generic_detail = compact.extract_article_detail(
        fixture(generic_title, generic_body),
        generic_title,
    )
    generic_row = {
        "source": "이투데이 산업",
        "layer": "trusted",
        "publisher": "이투데이",
        "title": generic_title,
        "source_title": generic_detail["title"],
        "source_body": generic_detail["body"],
        "source_abstract": generic_detail["body"],
        "summary": generic_detail["body"],
        "link": "https://www.etoday.co.kr/news/view/2606800",
        "published": now,
        "body_verified": True,
    }
    generic_alert = production.contract.strict.classify(generic_row, now)
    if not generic_alert:
        errors.append("verified generic Korean business article was not classified")
    else:
        normalized = compact.normalize_alert_for_output(generic_alert)
        if normalized.get("korean_business_kind") != "verified_source_summary":
            errors.append("generic Korean article did not use verified source summary profile")
        if normalized.get("news") != generic_title:
            errors.append("generic Korean article exact title was overwritten")
        if not compact.source_output_aligned(normalized):
            errors.append("generic Korean article source/output alignment failed")
        rendered = compact.compact_alert(normalized, 1, now, {}, {})
        if generic_title not in rendered or "원문 뉴스보기" not in rendered:
            errors.append("generic Korean article compact rendering lost title or source link")
        if "공식 문서 또는 신뢰 보도에서" in rendered:
            errors.append("generic Korean article fell back to stale generic policy copy")

    body_only_material_row = dict(generic_row)
    body_only_material_row.update(
        {
            "title": "헤지스, 9월에 홍콩 간다",
            "source_title": "헤지스, 9월에 홍콩 간다",
            "source_body": (
                "브랜드가 AI 오더 시스템을 도입했다. 본문에는 과거 수주와 매출 목표가 언급됐지만 "
                "제목에는 실적·계약·증설 같은 새로운 가격 변수가 없다."
            ),
            "source_abstract": (
                "브랜드가 AI 오더 시스템을 도입했다. 본문에는 과거 수주와 매출 목표가 언급됐다."
            ),
            "summary": "브랜드가 AI 오더 시스템을 도입했다.",
            "link": "https://www.etoday.co.kr/news/view/2606629",
        }
    )
    if production.contract.strict.classify(body_only_material_row, now):
        errors.append("Korean body-only background terms bypassed the material headline gate")

    person_name_false_positive_row = dict(generic_row)
    person_name_false_positive_row.update(
        {
            "title": "홍수주, '동궁' 비극적 서사 완성",
            "source_title": "홍수주, '동궁' 비극적 서사 완성",
            "source_body": (
                "배우 홍수주가 드라마 동궁에서 비극적 서사를 연기했다. "
                "기사에는 기업 계약, 매출, 실적 또는 투자 일정이 없다."
            ),
            "source_abstract": "배우 홍수주가 드라마 동궁에서 비극적 서사를 연기했다.",
            "summary": "배우 홍수주가 드라마 동궁에서 비극적 서사를 연기했다.",
            "link": "https://www.etnews.com/20260724000140",
        }
    )
    if production.contract.strict.classify(person_name_false_positive_row, now):
        errors.append("personal name containing 수주 bypassed the material headline gate")

    for material_title in (
        "현대로템, 폴란드 K2 전차 2차 수주",
        "한화에어로, 대형수주 공시",
        "조선사, 3조원대수주 성공",
        "LIG넥스원, 수주잔고 역대 최대",
    ):
        if not production.runner.korean_business_title_has_material_term(
            material_title,
            "수주",
        ):
            errors.append(f"valid contract headline was blocked by 수주 context guard: {material_title}")

    recap_row = dict(generic_row)
    recap_row.update(
        {
            "title": "[급등락주 짚어보기] 실적주 상한가·임상주 하한가",
            "source_title": "[급등락주 짚어보기] 실적주 상한가·임상주 하한가",
            "link": "https://www.etoday.co.kr/news/view/2606794",
        }
    )
    if production.contract.strict.classify(recap_row, now):
        errors.append("same-day price recap was promoted as a new high-impact article")

    jb_title = "JB금융, 2분기 순익 2196억 '사상 최대'…1000억원 자사주 소각"
    jb_body = (
        "JB금융지주가 비은행 계열사의 성장에 힘입어 분기 기준 사상 최대 실적을 "
        "달성하고 적극적인 주주환원에 나선다. "
        "23일 JB금융은 올 2분기 지배주주 당기순이익이 전년 동기 대비 5.7% "
        "증가한 2196억원을 기록했다고 밝혔다. "
        "상반기 누적 순이익 역시 3857억원으로 역대 최고치다. "
        "이날 JB금융 이사회는 주주환원 정책의 하나로 보통주 1주당 현금 314원의 "
        "분기 배당과 함께 1000억원 규모의 자기주식 취득 및 소각을 결정했다."
    )
    jb_detail = compact.extract_article_detail(fixture(jb_title, jb_body), jb_title)
    jb_row = {
        "source": "전자신문 오늘의 뉴스",
        "layer": "trusted",
        "publisher": "전자신문",
        "title": jb_title,
        "source_title": jb_detail["title"],
        "source_body": jb_detail["body"],
        "source_abstract": jb_detail["body"],
        "summary": jb_detail["body"],
        "link": "https://www.etnews.com/20260723000458",
        "published": now,
        "body_verified": True,
    }
    jb_alert = production.contract.strict.classify(jb_row, now)
    if not jb_alert:
        errors.append("JB Financial verified earnings article was not classified")
    else:
        normalized_jb = compact.normalize_alert_for_output(jb_alert)
        rendered = compact.compact_alert(normalized_jb, 1, now, {}, {})
        core_line = next((line for line in rendered.splitlines() if line.startswith("- 핵심:")), "")
        view_line = next(
            (line for line in rendered.splitlines() if line.startswith("- 투자 포인트:")),
            "",
        )
        if not all(
            term in core_line
            for term in ("2196억원", "5.7%", "역대 최대", "314원", "1000억원", "자사주")
        ):
            errors.append(f"JB Financial core omitted article facts: {core_line}")
        if not all(term in view_line for term in ("이익 추정", "주주환원")):
            errors.append(f"JB Financial investment point omitted market meaning: {view_line}")
        if "금융/자본시장" not in normalized_jb.get("sectors", []):
            errors.append("JB Financial article lost its finance sector classification")
        if jb_title in core_line or jb_title in view_line:
            errors.append("JB Financial summary repeated the headline instead of article facts")
        for marker in FORBIDDEN_COMPACT_MARKERS:
            if marker in rendered:
                errors.append(f"JB Financial compact Telegram summary retained {marker}")
        field_errors = compact_prose_errors(rendered)
        if field_errors:
            errors.append(
                "JB Financial compact facts exceeded field limits: " + ", ".join(field_errors)
            )

    detailed_article_cases = [
        (
            "[ET특징주]유한양행, 4253억원 규모 자사주 소각에 상승세",
            (
                "유한양행이 4253억원 규모의 자사주 소각 결정에 상승세다. "
                "금융감독원 전자공시시스템에 따르면 유한양행은 전날 이사회를 열고 "
                "4253억3760만4000원 규모의 자사주를 소각하기로 결정했다고 공시했다. "
                "소각 예정일은 오는 31일이며, 소각 대상은 보통주와 종류주를 포함한 "
                "총 606만4420주다."
            ),
            ("4253억3760만4000원", "소각", "606만4420주", "31일"),
            ("매입·소각",),
            ("발행주식", "주당가치"),
        ),
        (
            "[ET특징주]현대차, 2분기 실적 부진에 하락세",
            (
                "현대차는 전날 2분기 연결 기준 영업이익이 2조8509억원으로 지난해 "
                "같은 기간보다 20.8% 감소했다고 밝혔다. 매출은 49조2153억원으로 "
                "1.9% 증가했지만, 영업이익률은 5.8%로 연간 가이던스(6.3~7.3%)를 "
                "밑돌았다. 도매판매는 99만2000대로 전년 동기 대비 6.9% 감소했다."
            ),
            ("2조8509억원", "20.8% 감소", "49조2153억원", "5.8%", "6.3~7.3%"),
            ("영업이익 8509억원",),
            ("이익 추정", "가이던스"),
        ),
    ]
    for case_index, (
        title,
        body,
        required_facts,
        forbidden_facts,
        required_view_facts,
    ) in enumerate(
        detailed_article_cases,
        1,
    ):
        detail = compact.extract_article_detail(fixture(title, body), title)
        row = {
            "source": "전자신문 오늘의 뉴스",
            "layer": "trusted",
            "publisher": "전자신문",
            "title": title,
            "source_title": detail["title"],
            "source_body": detail["body"],
            "source_abstract": detail["body"],
            "summary": detail["body"],
            "link": f"https://www.etnews.com/2026072400016{case_index + 2}",
            "published": now,
            "body_verified": True,
        }
        alert = production.contract.strict.classify(row, now)
        if not alert:
            errors.append(f"detailed Korean article case was not classified: {title}")
            continue
        rendered = compact.compact_alert(
            compact.normalize_alert_for_output(alert),
            1,
            now,
            {},
            {},
        )
        core_line = next(
            (line for line in rendered.splitlines() if line.startswith("- 핵심:")),
            "",
        )
        view_line = next(
            (line for line in rendered.splitlines() if line.startswith("- 투자 포인트:")),
            "",
        )
        if not all(fact in core_line for fact in required_facts):
            errors.append(f"detailed Korean article core omitted facts: {core_line}")
        if any(fact in core_line for fact in forbidden_facts):
            errors.append(f"detailed Korean article core invented or clipped a fact: {core_line}")
        if not all(fact in view_line for fact in required_view_facts):
            errors.append(f"detailed Korean article investment point omitted meaning: {view_line}")

    sidecar_core = compact.market_sidecar_fact(
        "코스피ㆍ코스닥 동반 매도 사이드카 발동",
        (
            "외국인이 3조4285억원, 기관이 1조7019억원 순매도 중이다. "
            "삼성전자(-7.59%), SK하이닉스(-7.76%) 등은 약세다."
        ),
    )
    if not all(
        fact in sidecar_core
        for fact in ("코스피·코스닥", "3조4285억원", "1조7019억원", "7.59%", "7.76%")
    ):
        errors.append(f"sidecar article core omitted market facts: {sidecar_core}")

    tariff_title = "방미 의원단, 美에 '15% 관세 마지노선' 지켜달라 촉구"
    tariff_body = (
        "한국 여야 의원들이 미국 트럼프 행정부와 의회 관계자들을 만나 미국의 무역법 "
        "301조에 따른 추가 관세가 기존 한미 무역합의상 관세율인 15%를 넘지 않아야 "
        "한다고 촉구했다. 배준영 의원은 한국이 3500억 달러를 투자하는 대신 기존 "
        "25% 관세를 15%로 낮추기로 한 만큼 추가 관세 부담이 발생해서는 안 된다고 "
        "밝혔다. 트럼프 행정부는 강제노동 조사 결과를 근거로 한국에 12.5%의 관세를 "
        "부과했고 과잉생산을 이유로 한 추가 관세도 예고했다."
    )
    tariff_detail = compact.extract_article_detail(
        fixture(tariff_title, tariff_body),
        tariff_title,
    )
    tariff_row = {
        "source": "전자신문 오늘의 뉴스",
        "layer": "trusted",
        "publisher": "전자신문",
        "title": tariff_title,
        "source_title": tariff_detail["title"],
        "source_body": tariff_detail["body"],
        "source_abstract": tariff_detail["body"],
        "summary": tariff_detail["body"],
        "link": "https://www.etnews.com/20260724000074",
        "published": now,
        "body_verified": True,
    }
    tariff_alert = production.contract.strict.classify(tariff_row, now)
    if not tariff_alert:
        errors.append("Korea tariff article was not classified")
    else:
        normalized_tariff = compact.normalize_alert_for_output(tariff_alert)
        fx_snapshot = {
            "query_time_kst": now.isoformat(timespec="seconds"),
            "rates": {
                "USD": {
                    "code": "USD",
                    "value": 1464.88,
                    "status": "최근거래",
                    "reference_time_kst": "2026-07-24T13:21+09:00",
                    "query_time_kst": now.isoformat(timespec="seconds"),
                    "source": "Yahoo Finance",
                    "url": compact.yahoo_fx_url("USD"),
                    "error": "",
                }
            },
        }
        normalized_tariff["fx_conversion"] = compact.build_alert_fx_conversion(
            normalized_tariff,
            fx_snapshot,
            now,
        )
        rendered = compact.compact_alert(normalized_tariff, 1, now, {}, {})
        core_line = next(
            (line for line in rendered.splitlines() if line.startswith("- 핵심:")),
            "",
        )
        investment_line = next(
            (line for line in rendered.splitlines() if line.startswith("- 투자 포인트:")),
            "",
        )
        source_line = next(
            (line for line in rendered.splitlines() if line.startswith("- 출처:")),
            "",
        )
        required_facts = ("12.5%", "추가 관세", "15%", "3500억 달러", "약 512.7조원")
        if not all(term in core_line for term in required_facts):
            errors.append(f"Korea tariff detailed core omitted article facts: {core_line}")
        if len(core_line.removeprefix("- 핵심:").strip()) <= 50:
            errors.append("Korea tariff core regressed to the former 50-character cap")
        if "가격경쟁력" not in investment_line or "마진" not in investment_line:
            errors.append(f"Korea tariff investment point is not decision-useful: {investment_line}")
        if "Yahoo Finance USD/KRW" not in source_line or "2026-07-24T13:21+09:00" not in source_line:
            errors.append(f"Korea tariff FX provenance missing: {source_line}")
        if "…" in rendered or "..." in rendered:
            errors.append("Korea tariff compact output contains a truncated sentence")
        for marker in FORBIDDEN_COMPACT_MARKERS:
            if marker in rendered:
                errors.append(f"Korea tariff compact output retained removed field {marker}")

    eur_amounts = compact.extract_foreign_amounts("유럽 공장에 20억 유로를 투자한다.")
    if not eur_amounts or eur_amounts[0].get("code") != "EUR":
        errors.append("EUR amount parser did not detect a euro-denominated investment")
    else:
        eur_alert = {
            "telegram_core_fact": "유럽 공장에 20억 유로를 투자한다.",
            "news": "유럽 공장 투자",
        }
        eur_snapshot = {
            "query_time_kst": now.isoformat(timespec="seconds"),
            "rates": {
                "EUR": {
                    "code": "EUR",
                    "value": 1666.2,
                    "status": "최근거래",
                    "reference_time_kst": "2026-07-24T13:19+09:00",
                    "query_time_kst": now.isoformat(timespec="seconds"),
                    "source": "Yahoo Finance",
                    "url": compact.yahoo_fx_url("EUR"),
                    "error": "",
                }
            },
        }
        eur_conversion = compact.build_alert_fx_conversion(eur_alert, eur_snapshot, now)
        converted = compact.apply_krw_conversions(
            "유럽 공장에 20억 유로를 투자한다.",
            eur_conversion,
        )
        if "20억 유로(약 3.3조원)" not in converted:
            errors.append(f"EUR amount was not converted to KRW: {converted}")

    required_currency_codes = {
        "USD", "EUR", "JPY", "CNY", "GBP", "CHF", "CAD", "AUD", "HKD", "SGD", "TWD"
    }
    if not required_currency_codes.issubset(compact.FOREIGN_CURRENCY_SPECS):
        errors.append("major world-currency KRW conversion coverage is incomplete")
    usd_prefix_amounts = compact.extract_foreign_amounts(
        "The agreement includes USD 350 billion of investment."
    )
    if (
        not usd_prefix_amounts
        or usd_prefix_amounts[0].get("code") != "USD"
        or usd_prefix_amounts[0].get("amount") != 350_000_000_000
    ):
        errors.append("ISO-prefixed foreign amount parser did not detect USD 350 billion")


if __name__ == "__main__":
    raise SystemExit(main())
