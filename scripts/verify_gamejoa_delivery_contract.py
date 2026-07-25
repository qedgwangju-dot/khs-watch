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
    "- 투자 포인트:",
)
COMPACT_PROSE_LIMITS = {
    "- 핵심:": 280,
    "- 투자 포인트:": 100,
}
FORBIDDEN_COMPACT_MARKERS = (
    "- 기준/시각:",
    "- 경로/섹터:",
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
    'GAMEJOA_KOREAN_BUSINESS_DETAIL_LIMIT: "48"',
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
    'supply_chain_theme": f"us_semiconductor_selloff:',
    "GAMEJOA_CORE_MAX_CHARS = 280",
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
    assert_detailed_summary_is_preserved_before_send(compact, now, errors)
    assert_korean_business_article_contract(production, compact, now, errors)
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
            errors.append("Federal Register UAE EAR alert failed final selection source/body alignment")

    # Regression fixture for the July 21 Reuters Treasury-tax article.  The
    # collector query label contains nuclear/rate terms, but labels are routing
    # metadata and must never become article evidence or a Korean market theme.
    treasury_tax_row = {
        "source": "Trusted news 원전 인프라 금리인하",
        "layer": "trusted",
        "publisher": "Reuters",
        "title": "US Treasury flags Wall Street tax strategies potentially abusive, Bloomberg News reports",
        "summary": (
            "The Treasury Department identified several Wall Street tax strategies as potentially "
            "abusive, Bloomberg News reported."
        ),
        "link": (
            "https://www.reuters.com/legal/government/"
            "us-treasury-flags-wall-street-tax-strategies-potentially-abusive-bloomberg-news-2026-07-21/"
        ),
        "published": now,
    }
    treasury_source_text = production.base.source_content_text(treasury_tax_row)
    if any(term in treasury_source_text for term in ["원전", "smr", "가스터빈", "금리인하"]):
        errors.append("collector query label leaked into Reuters Treasury source content")
    treasury_tax_alert = production.contract.strict.classify(treasury_tax_row, now)
    if treasury_tax_alert is not None:
        errors.append("unrelated Reuters Treasury tax-strategy article was classified as high-impact Korea-market news")

    poisoned_treasury_alert = {
        "score": 100,
        "importance": "상",
        "status": "공식 확인 전",
        "source": treasury_tax_row["source"],
        "publisher": treasury_tax_row["publisher"],
        "source_title": treasury_tax_row["title"],
        "source_abstract": treasury_tax_row["summary"],
        "original_news": treasury_tax_row["title"],
        "link": treasury_tax_row["link"],
        "published": now.isoformat(timespec="minutes"),
        "news": "미국 원전·SMR·AI 전력 정책 시간표 체크",
        "policy_plain_summary": "원전, SMR, 가스터빈, AI 전력수요 관련 정책 시간표입니다.",
        "investment_view": "원전 기자재 발주와 수주 기대를 확인합니다.",
        "korea_market_impact": "두산에너빌리티와 KHNP 수급을 확인합니다.",
        "impacts": ["할인율"],
        "paths": ["할인율"],
        "sectors": ["원전/SMR/가스터빈", "두산에너빌리티/KHNP"],
    }
    if "원전" in compact.source_evidence_text(poisoned_treasury_alert):
        errors.append("collector query label leaked into final source evidence")
    if compact.source_output_aligned(poisoned_treasury_alert):
        errors.append("Reuters Treasury tax article passed with an unrelated nuclear headline/body")
    if compact.quality_display_alerts([poisoned_treasury_alert], 5):
        errors.append("Reuters Treasury source/body mismatch reached final Telegram selection")

    legitimate_nuclear_row = {
        "source": "Trusted news 원자재/금리/환율",
        "layer": "trusted",
        "publisher": "Reuters",
        "title": "US backs Westinghouse AP1000 nuclear reactor construction with low-cost loans",
        "summary": (
            "The program supports construction of AP1000 nuclear reactors to meet rising data-center "
            "power demand, subject to licensing and final financing."
        ),
        "link": "https://www.reuters.com/business/energy/example-ap1000-nuclear-loans",
        "published": now,
    }
    legitimate_nuclear_alert = production.contract.strict.classify(legitimate_nuclear_row, now)
    if legitimate_nuclear_alert is None:
        errors.append("source-authored AP1000 nuclear article was lost after query-label isolation")
    else:
        normalized_nuclear = compact.normalize_alert_for_output(legitimate_nuclear_alert)
        if not compact.source_output_aligned(normalized_nuclear):
            errors.append("source-authored AP1000 nuclear article failed source/body alignment")

    iran_row = {
        "source": "Trusted news 이란/호르무즈 긴급상황",
        "layer": "trusted",
        "publisher": "AP News",
        "title": "US attacks Iran over ship being hit in Strait of Hormuz; Tehran lashes out again at Gulf Arab states",
        "link": "https://apnews.com/article/iran-hormuz-regression-fixture",
        "summary": "The U.S. military completed airstrikes targeting Iran after a civilian vessel was attacked in the Strait of Hormuz, threatening the ceasefire.",
        "published": now,
    }
    iran_alert = production.contract.strict.classify(iran_row, now)
    if not iran_alert:
        errors.append("Iran/Hormuz ship attack and U.S. strike was not classified")
    else:
        normalized_iran = compact.normalize_alert_for_output(iran_alert)
        if normalized_iran.get("news") != "미국, 이란 재공격·호르무즈 상선 피격: 휴전·유가 리스크":
            errors.append(f"Iran/Hormuz alert did not render a specific Korean title: {normalized_iran.get('news')}")
        expected_impacts = {"돈 버는 능력", "할인율", "수급", "시간표"}
        if not expected_impacts.issubset(set(normalized_iran.get("impacts") or [])):
            errors.append(f"Iran/Hormuz alert lost decision impacts: {normalized_iran.get('impacts')}")
        if not normalized_iran.get("realtime_policy_lane"):
            errors.append("Iran/Hormuz alert was not routed to the realtime policy lane")
        reuters_duplicate = dict(normalized_iran)
        reuters_duplicate.update({
            "publisher": "Reuters on MSN",
            "source": "Trusted news 이란/호르무즈 긴급상황",
            "link": "https://www.reuters.com/world/iran-hormuz-regression-fixture",
            "published": "2026-07-12T10:30+09:00",
            "original_news": "US strikes Iran, Tehran says Strait of Hormuz closed, Gulf states hit",
        })
        one_story = compact.quality_display_alerts([reuters_duplicate, normalized_iran], 5)
        if len(one_story) != 1 or "AP" not in str(one_story[0].get("publisher") or ""):
            errors.append(f"Iran/Hormuz cross-source story was not deduped to AP: {one_story}")
        raw_reuters_variant = dict(normalized_iran)
        raw_reuters_variant.update({
            "news": "트럼프 에너지 발언: 유가·운임 리스크",
            "original_news": "U.S. renews strikes on Iran as tanker is attacked in Strait of Hormuz",
            "publisher": "Reuters",
            "link": "https://www.reuters.com/world/iran-cross-source-seen-fixture",
        })
        ap_title_keys = {key for key in production.telegram.alert_seen_keys(normalized_iran) if key.startswith("title:")}
        reuters_title_keys = {key for key in production.telegram.alert_seen_keys(raw_reuters_variant) if key.startswith("title:")}
        if not ap_title_keys.intersection(reuters_title_keys):
            errors.append("Iran/Hormuz cross-source variants did not share a canonical seen key")
        live_remaining, live_routed = production.telegram.partition_realtime_policy_alerts([normalized_iran], True)
        if live_remaining or live_routed != [normalized_iran]:
            errors.append("Iran/Hormuz alert was not single-routed away from live radar duplication")
        preopen_remaining, preopen_routed = production.telegram.partition_realtime_policy_alerts([normalized_iran], False)
        if preopen_remaining != [normalized_iran] or preopen_routed:
            errors.append("Iran/Hormuz alert was not retained for the 06:30 radar")

    # A story already announced by the real-time lane must still be available
    # to the once-daily 06:30 digest. This guards the failure where overnight
    # live polls consumed every preopen candidate before the morning run.
    live_only_probe = {
        "news": "장전 seen-state 회귀 검사",
        "original_news": "Preopen seen-state regression fixture",
        "publisher": "Reuters",
        "link": "https://www.reuters.com/world/preopen-seen-regression-fixture",
    }
    preopen_probe = {
        "news": "전날 장전판 중복 회귀 검사",
        "original_news": "Prior preopen duplicate regression fixture",
        "publisher": "Reuters",
        "link": "https://www.reuters.com/world/prior-preopen-duplicate-regression-fixture",
    }
    live_key = production.telegram.alert_seen_keys(live_only_probe)[0]
    preopen_key = production.telegram.alert_seen_keys(preopen_probe)[0]
    original_load_seen_state = production.telegram.load_seen_state
    production.telegram.load_seen_state = lambda: {
        "seen": {
            live_key: {"first_seen_kst": now.isoformat(), "lanes": {"live": now.isoformat()}},
            preopen_key: {"first_seen_kst": now.isoformat(), "lanes": {"preopen": now.isoformat()}},
        },
        "updated_at_kst": now.isoformat(),
    }
    try:
        probes = [live_only_probe, preopen_probe]
        live_fresh, live_skipped = production.telegram.filter_alerts_for_run_mode(probes, now, True)
        preopen_fresh, preopen_skipped = production.telegram.filter_alerts_for_run_mode(probes, now, False)
    finally:
        production.telegram.load_seen_state = original_load_seen_state
    if live_fresh or live_skipped != probes:
        errors.append("live radar no longer applies seen-state suppression")
    if len(preopen_fresh) != 1 or preopen_fresh[0].get("link") != live_only_probe["link"]:
        errors.append("06:30 preopen digest did not retain the live-only story")
    elif not preopen_fresh[0].get("_preopen_live_seen_bypass"):
        errors.append("06:30 preopen digest lost its live-seen bypass marker")
    if len(preopen_skipped) != 1 or preopen_skipped[0].get("link") != preopen_probe["link"]:
        errors.append("06:30 preopen digest repeated a prior preopen story")
    if not production.telegram.seen_entry_has_lane({"first_seen_kst": now.isoformat()}, "preopen"):
        errors.append("legacy seen-state was not suppressed from repeat preopen delivery")

    legacy_state = {
        "seen": {
            "title:old-raw-source-key": {
                "first_seen_kst": now.isoformat(),
                "title": "미국, 이란 재공격·호르무즈 상선 피격: 휴전·유가 리스크",
            }
        }
    }
    production.telegram.migrate_seen_title_aliases(legacy_state)
    expected_legacy_alias = "title:" + production.telegram.digest_seen(
        "미국, 이란 재공격·호르무즈 상선 피격: 휴전·유가 리스크"
    )
    if expected_legacy_alias not in legacy_state["seen"]:
        errors.append("legacy seen-state did not gain a canonical Korean-title alias")

    lane_state = {
        "seen": {
            live_key: {
                "first_seen_kst": now.isoformat(),
                "lanes": {"live": now.isoformat()},
            }
        },
        "updated_at_kst": now.isoformat(),
    }
    original_load_seen_state = production.telegram.load_seen_state
    original_save_seen_state = production.telegram.save_seen_state
    original_run_mode = os.environ.get("RADAR_RUN_MODE")
    production.telegram.load_seen_state = lambda: lane_state
    production.telegram.save_seen_state = lambda state, _now: lane_state.update(state)
    try:
        os.environ["RADAR_RUN_MODE"] = "preopen"
        recorded_probe = dict(live_only_probe)
        recorded_probe["_seen_keys"] = [live_key]
        production.telegram.record_seen_alerts([recorded_probe], now)
    finally:
        production.telegram.load_seen_state = original_load_seen_state
        production.telegram.save_seen_state = original_save_seen_state
        if original_run_mode is None:
            os.environ.pop("RADAR_RUN_MODE", None)
        else:
            os.environ["RADAR_RUN_MODE"] = original_run_mode
    recorded_lanes = lane_state["seen"][live_key].get("lanes") or {}
    if not {"live", "preopen"}.issubset(set(recorded_lanes)):
        errors.append(f"seen-state did not preserve live and preopen lanes: {recorded_lanes}")

    # The sender and post-send verifier must interpret the manual off-window
    # switch identically. Otherwise Telegram can be sent while Actions reports
    # a false failure, which hides the real delivery result.
    tested_env = {
        "RADAR_RUN_MODE": os.environ.get("RADAR_RUN_MODE"),
        "ALLOW_OFF_WINDOW_TELEGRAM": os.environ.get("ALLOW_OFF_WINDOW_TELEGRAM"),
        "PREOPEN_SEND_WINDOW_START_KST": os.environ.get("PREOPEN_SEND_WINDOW_START_KST"),
        "PREOPEN_SEND_WINDOW_END_KST": os.environ.get("PREOPEN_SEND_WINDOW_END_KST"),
    }
    try:
        os.environ["RADAR_RUN_MODE"] = "preopen"
        os.environ["PREOPEN_SEND_WINDOW_START_KST"] = "05:30"
        os.environ["PREOPEN_SEND_WINDOW_END_KST"] = "07:30"
        os.environ["ALLOW_OFF_WINDOW_TELEGRAM"] = "true"
        off_window_time = now.replace(hour=16, minute=0, second=0, microsecond=0)
        if not compact.preopen_send_window_open():
            errors.append("Telegram sender ignored ALLOW_OFF_WINDOW_TELEGRAM=true")
        if not runtime_delivery.send_window_open(off_window_time):
            errors.append("runtime delivery verifier ignored ALLOW_OFF_WINDOW_TELEGRAM=true")
        os.environ["ALLOW_OFF_WINDOW_TELEGRAM"] = "false"
        if runtime_delivery.send_window_open(off_window_time):
            errors.append("runtime delivery verifier opened the normal preopen window at 16:00 KST")
    finally:
        for name, value in tested_env.items():
            if value is None:
                os.environ.pop(name, None)
            else:
                os.environ[name] = value

    if send_module != LOCKED_TELEGRAM_MODULE:
        errors.append(
            f"{PRODUCTION_RUNNER}.telegram.send_telegram is wired to {send_module}, "
            f"expected {LOCKED_TELEGRAM_MODULE}"
        )
    if compact_module != LOCKED_TELEGRAM_MODULE:
        errors.append(
            f"{PRODUCTION_RUNNER}.telegram.compact_report is wired to {compact_module}, "
            f"expected {LOCKED_TELEGRAM_MODULE}"
        )
    if final_selection_module != LOCKED_TELEGRAM_MODULE:
        errors.append(
            f"{PRODUCTION_RUNNER}.telegram.final_alerts_for_output is wired to {final_selection_module}, "
            f"expected {LOCKED_TELEGRAM_MODULE}"
        )
    if canonical_seen_module != LOCKED_TELEGRAM_MODULE:
        errors.append(
            f"{PRODUCTION_RUNNER}.telegram.canonical_alert_for_seen is wired to {canonical_seen_module}, "
            f"expected {LOCKED_TELEGRAM_MODULE}"
        )

    if errors:
        for error in errors:
            print(f"GAMEJOA delivery contract error: {error}")
        return 1

    print("GAMEJOA delivery contract OK: hs8879 Telegram lane is locked and send failures are fatal.")
    return 0


def assert_detailed_summary_is_preserved_before_send(compact, now, errors: list[str]) -> None:
    report = "\n".join([
        f"📰 실시간 핵심 뉴스 레이더 · {now:%Y년 %m월 %d일} · {now:%H:%M}",
        f"조회: {now:%Y-%m-%d %H:%M KST}",
        "선별: 핵심 1건",
        "",
        "1) [상 | 공식 확인 전] 미국, 반도체 수출통제 확대 검토",
        (
            "- 핵심: 미국이 첨단 반도체 장비 수출통제를 확대해 한국 기업의 "
            "중국 공장 증설과 장비 반입 일정, 현지 생산비용을 다시 점검하게 됐습니다."
        ),
        (
            "- 투자 포인트: 적용 장비와 시행일이 확정되면 중국 생산법인의 "
            "증설비용과 장비 조달 일정이 바뀔 수 있습니다."
        ),
        "- 출처: <a href=\"https://www.reuters.com/world/example\">Reuters</a>",
        "",
        "💡 실시간 뉴스 코멘트",
        "오늘 핵심 변화는 `매출·마진·현금흐름·시간표`입니다.",
        "할인율: 확인 불가",
        "다음 투자기상도에서 수치·수급·테마와 재확인 필요.",
        "",
        "투자 조언이 아닌 참고용 뉴스 브리핑입니다.",
    ]) + "\n"
    try:
        compacted = compact.guard_preopen_report(report)
    except RuntimeError as exc:
        errors.append(f"detailed summary was blocked instead of preserved: {exc}")
        return
    field_errors = compact_prose_errors(compacted)
    if field_errors:
        errors.append(
            "detailed summary exceeded the field contract: "
            + ", ".join(field_errors)
        )
    if not all(
        term in compacted
        for term in ("미국이 첨단 반도체 장비 수출통제를", "중국 공장 증설", "현지 생산비용")
    ):
        errors.append("GAMEJOA detailed summary lost source-specific facts")
    core_line = next(
        (line for line in compacted.splitlines() if line.startswith("- 핵심:")),
        "",
    )
    if len(core_line.removeprefix("- 핵심:").strip()) <= 50:
        errors.append("GAMEJOA detailed core regressed to the former 50-character cap")
    for marker in FORBIDDEN_COMPACT_MARKERS:
        if marker in compacted:
            errors.append(f"removed compact field returned during detailed-summary test: {marker}")


def assert_korean_business_article_contract(production, compact, now, errors: list[str]) -> None:
    noisy_summary = compact.article_sentences(
        (
            "무단 전재 재배포 금지, AI 학습 및 활용 금지> "
            "원·달러 환율이 1470원을 밑돌며 두 달 만의 최저치를 기록했다. "
            "외국인 위험선호가 확대되며 원화가 강세를 보였다."
        ),
        ["원·달러", "1470원"],
        2,
    )
    if "무단 전재" in noisy_summary or "AI 학습" in noisy_summary:
        errors.append("Korean article summary retained publisher boilerplate")
    if not noisy_summary.startswith("원·달러 환율"):
        errors.append(f"Korean article summary did not start from article facts: {noisy_summary}")

    long_summary = compact.article_sentences(
        (
            "KB증권의 올해 2분기 연결 기준 영업이익은 6006억원으로 전년 동기보다 "
            "175.5% 늘었다. "
            + "주식시장 강세와 거래대금 증가가 위탁매매 수익을 끌어올렸다. " * 12
        ),
        ["KB증권", "영업이익", "6006억원"],
        3,
    )
    if len(long_summary) > compact.ARTICLE_SUMMARY_MAX_CHARS:
        errors.append("Korean article summary exceeded compact character limit")
    if not long_summary.endswith((".", "!", "?", "다", "…")):
        errors.append(f"Korean article summary ended mid-sentence: {long_summary[-40:]}")

    etoday_title = "외국인, 삼전·SK하닉 4.5조 사들여…반도체도 골라 담았다"
    etoday_body = (
        "외국인은 4거래일 동안 삼성전자 2조9327억원과 SK하이닉스 "
        "1조5416억원을 순매수했다. 두 종목 합계는 약 4조5000억원이다. "
        "반면 일부 반도체 소재·부품·장비 종목은 순매도해 업종 내부 차별화가 나타났다."
    )
    etnews_title = "엑시콘, 차세대 CXL 3.1 테스터 상용화 속도"
    etnews_body = (
        "엑시콘은 삼성전자와 Gen6 및 CXL 3.1 테스터 양산평가를 진행하고 있다. "
        "평가는 이달 말 마무리될 예정이며, 양산평가 통과 뒤 실제 장비 발주가 남아 있다. "
        "회사는 지난해 매출 1018억원을 기록했다."
    )

    def fixture(title: str, body: str) -> str:
        return f"""
        <html><head>
          <meta property="og:title" content="{title}">
          <meta property="article:published_time" content="2026-07-23T17:00:00+09:00">
        </head><body><div itemprop="articleBody">
          <h1>{title}</h1><p>{body}</p>
          <p>기사 원문은 관련 기업의 후속 수급, 고객 평가, 발주와 공시를 함께 확인해야 한다고 설명했다.</p>
        </div></body></html>
        """

    for publisher, title, body, link, expected_kind, expected_impacts in [
        (
            "이투데이",
            etoday_title,
            etoday_body,
            "https://www.etoday.co.kr/news/view/2606782",
            "foreign_semiconductor_flow",
            ["수급"],
        ),
        (
            "전자신문",
            etnews_title,
            etnews_body,
            "https://www.etnews.com/20260723000345",
            "exicon_cxl_tester",
            ["돈 버는 능력", "시간표", "수급"],
        ),
    ]:
        detail = compact.extract_article_detail(fixture(title, body), title)
        if not detail.get("body_verified") or not detail.get("title_aligned"):
            errors.append(f"{publisher} article title/body verification failed")
            continue
        row = {
            "source": f"{publisher} 반도체 뉴스",
            "layer": "trusted",
            "publisher": publisher,
            "title": title,
            "source_title": detail["title"],
            "source_body": detail["body"],
            "source_abstract": detail["body"],
            "summary": detail["body"],
            "link": link,
            "published": now,
            "body_verified": True,
        }
        alert = production.contract.strict.classify(row, now)
        if not alert:
            errors.append(f"{publisher} verified article was not classified")
            continue
        normalized = compact.normalize_alert_for_output(alert)
        if normalized.get("news") != title:
            errors.append(
                f"{publisher} exact Korean source title was overwritten: {normalized.get('news')}"
            )
        if normalized.get("korean_business_kind") != expected_kind:
            errors.append(
                f"{publisher} article did not select its specific profile: "
                f"{normalized.get('korean_business_kind')}"
            )
        if normalized.get("impacts") != expected_impacts:
            errors.append(
                f"{publisher} article impacts were contaminated by another overlay: "
                f"{normalized.get('impacts')}"
            )
        if normalized.get("sectors") != ["반도체/AI"]:
            errors.append(
                f"{publisher} article sectors were contaminated by another overlay: "
                f"{normalized.get('sectors')}"
            )
        if normalized.get("k_power_watch"):
            errors.append(f"{publisher} article incorrectly inherited the nuclear overlay")
        if not compact.source_output_aligned(normalized):
            errors.append(f"{publisher} source/output alignment failed")
        rendered = compact.compact_alert(normalized, 1, now, {}, {})
        required_markers = [
            "- 핵심:",
            "- 투자 포인트:",
            "원문 뉴스보기",
        ]
        for marker in required_markers:
            if marker not in rendered:
                errors.append(f"{publisher} compact Telegram summary missing {marker}")
        field_errors = compact_prose_errors(rendered)
        if field_errors:
            errors.append(
                f"{publisher} compact Telegram prose exceeded field limits: "
                + ", ".join(field_errors)
            )
        if "- 분류 매트릭스:" in rendered or "- 관련 해외 티커/지표:" in rendered:
            errors.append(f"{publisher} compact Telegram summary regressed to verbose format")
        for marker in FORBIDDEN_COMPACT_MARKERS:
            if marker in rendered:
                errors.append(f"{publisher} compact Telegram summary retained {marker}")
        if "K-원전/가스터빈" in rendered or "체코 원전" in rendered:
            errors.append(f"{publisher} compact summary contains an unrelated nuclear watch")

    edaily_direct_fixture = """
    <html><head>
      <meta property="og:title" content="정의선, 美 엔비디아 본사 찾아 젠슨 황과 회동…AI 협력 후속 논의">
      <meta property="article:published_time" content="2026-07-25T08:09:44+09:00">
    </head><body>
      <div class="news_body" itemprop="articleBody">
        정의선 현대자동차그룹 회장이 엔비디아 본사를 방문해 젠슨 황 CEO와 만났다.<br><br>
        양측은 자율주행, 로봇, 제조 AI와 새만금 AI 밸리 협력 후속 방안을 논의했다.<br><br>
        현대차그룹은 새만금 부지에 단계적으로 9조원을 투자할 계획이지만,
        이번 회동에서 별도 공급계약 금액이나 발주 규모는 공개하지 않았다.<br><br>
        후속 협력이 실제 공동개발과 장비 공급으로 이어지는지는 별도 계약과 기업 공시로 확인해야 한다.
      </div>
    </body></html>
    """
    edaily_direct = compact.extract_article_detail(
        edaily_direct_fixture,
        "정의선, 美 엔비디아 본사 찾아 젠슨 황과 회동…AI 협력 후속 논의",
    )
    if not edaily_direct.get("body_verified") or "자율주행" not in edaily_direct.get("body", ""):
        errors.append("Edaily direct-text article body was not extracted")

    expanded_cases = [
        {
            "publisher": "이데일리",
            "title": "정의선, 美 엔비디아 본사 찾아 젠슨 황과 회동…AI 협력 후속 논의",
            "body": (
                "정의선 현대자동차그룹 회장이 엔비디아 본사를 방문해 젠슨 황 CEO와 만났다. "
                "양측은 자율주행, 로봇, 제조 AI와 새만금 AI 밸리 협력 후속 방안을 논의했다. "
                "이번 회동에서 별도 공급계약 금액이나 발주 규모는 공개하지 않았다."
            ),
            "link": "https://www.edaily.co.kr/News/Read?mediaCodeNo=257&newsId=01899126645518128",
            "kind": "hyundai_nvidia_ai_partnership",
            "core_terms": ("자율주행", "로봇", "제조AI", "계약금액", "공개되지"),
            "view_terms": ("협력 논의", "계약", "발주"),
        },
        {
            "publisher": "매일경제",
            "title": "국민 64% “삼닉과 레버리지는 잘못된 만남”…31일부터 불개미 막는다",
            "body": (
                "삼성전자와 SK하이닉스 단일종목 레버리지 ETF·ETN을 사려면 31일부터 "
                "계좌에 현금 3000만원 이상을 보유해야 한다. 금융위원회는 현재 1000만원인 "
                "기본예탁금을 3000만원으로 상향하고 주식·채권 등 대용증권을 인정하지 않는다. "
                "당초 8월 순차 적용 예정이던 두 조치는 7월 31일부터 동시에 시행된다."
            ),
            "link": "https://www.mk.co.kr/news/stock/12107172",
            "kind": "single_stock_leverage_rule",
            "core_terms": ("1000만원", "3000만원", "대용증권", "7월 31일"),
            "view_terms": ("진입비용", "신규수요", "파생수급"),
        },
        {
            "publisher": "머니투데이",
            "title": '유가 하락에도 반도체 털어낸 시장…"금리·실적부터 보자"[뉴욕마감]',
            "body": (
                "뉴욕증시는 국제유가 하락에도 반도체주 급락으로 혼조 마감했다. "
                "나스닥종합지수는 0.64% 하락했고 필라델피아 반도체지수는 4.3% 급락했다. "
                "반에크 반도체 상장지수펀드(SMH)는 3.3% 하락했다. "
                "투자자들은 다음 주 FOMC와 마이크로소프트·메타·애플 실적을 앞두고 차익실현에 나섰다."
            ),
            "link": "https://www.mt.co.kr/world/2026/07/25/2026072505495617727",
            "kind": "global_semiconductor_market_shock",
            "core_terms": ("나스닥 0.64%", "필라델피아 반도체지수 4.3%", "SMH 3.3%", "FOMC"),
            "view_terms": ("삼성전자", "SK하이닉스", "외국인 수급"),
        },
        {
            "publisher": "이데일리",
            "title": "[속보]유가 하락에 S&P500 보합…반도체주 급락에 나스닥 0.6%↓",
            "body": (
                "미국 증시는 국제유가 하락에도 반도체주 급락으로 혼조 마감했다. "
                "나스닥종합지수는 0.64% 하락했고 필라델피아 반도체지수는 4.3% 급락했다. "
                "반에크 반도체 상장지수펀드(SMH)는 3.3% 하락했다. "
                "다음 주 FOMC와 빅테크 실적 발표를 앞두고 차익실현이 집중됐다."
            ),
            "link": "https://www.edaily.co.kr/News/Read?mediaCodeNo=257&newsId=01485846645518128",
            "kind": "global_semiconductor_market_shock",
            "core_terms": ("나스닥 0.64%", "필라델피아 반도체지수 4.3%", "SMH 3.3%", "FOMC"),
            "view_terms": ("삼성전자", "SK하이닉스", "외국인 수급"),
        },
        {
            "publisher": "헤럴드경제",
            "title": "“데이터센터·반도체 공장 더 짓자”…AI 열풍에 철강 수요 ‘훈풍’",
            "body": (
                "한국철강협회에 따르면 1~5월 형강 내수 판매량은 103만톤으로 전년비 9.7% 늘었다. "
                "동국제강 2분기 영업이익은 456억원으로 전년비 52.3% 증가했다. "
                "AI 데이터센터 구축 과정의 철강재 수요는 2030년까지 약 86만톤으로 추정됐다. "
                "반도체 공장 증설도 형강과 후판 수요를 늘릴 것으로 분석됐다."
            ),
            "link": "https://biz.heraldcorp.com/article/10819661?ref=naver",
            "kind": "ai_infrastructure_steel_demand",
            "core_terms": ("103만톤", "9.7%", "456억원", "52.3%", "86만톤"),
            "view_terms": ("착공", "형강", "후판", "이익 추정"),
        },
    ]
    expanded_alerts = []
    for case in expanded_cases:
        detail = compact.extract_article_detail(
            fixture(case["title"], case["body"]),
            case["title"],
        )
        row = {
            "source": f"{case['publisher']} 고충격 검색",
            "layer": "trusted",
            "publisher": case["publisher"],
            "title": case["title"],
            "source_title": detail["title"],
            "source_body": detail["body"],
            "source_abstract": detail["body"],
            "summary": detail["body"],
            "link": case["link"],
            "published": now,
            "body_verified": True,
        }
        alert = production.contract.strict.classify(row, now)
        if not alert:
            errors.append(f"{case['publisher']} expanded high-impact article was not classified: {case['title']}")
            continue
        normalized = compact.normalize_alert_for_output(alert)
        expanded_alerts.append(normalized)
        if normalized.get("korean_business_kind") != case["kind"]:
            errors.append(
                f"{case['publisher']} article selected wrong profile: "
                f"{normalized.get('korean_business_kind')} != {case['kind']}"
            )
        if not compact.source_output_aligned(normalized):
            errors.append(f"{case['publisher']} expanded article source/output alignment failed")
        rendered = compact.compact_alert(normalized, 1, now, {}, {})
        core_line = next((line for line in rendered.splitlines() if line.startswith("- 핵심:")), "")
        view_line = next(
            (line for line in rendered.splitlines() if line.startswith("- 투자 포인트:")),
            "",
        )
        for term in case["core_terms"]:
            if term not in core_line:
                errors.append(f"{case['publisher']} core omitted {term}: {core_line}")
        for term in case["view_terms"]:
            if term not in view_line:
                errors.append(f"{case['publisher']} investment point omitted {term}: {view_line}")

    market_alerts = [
        alert
        for alert in expanded_alerts
        if alert.get("korean_business_kind") == "global_semiconductor_market_shock"
    ]
    if len(market_alerts) == 2:
        if compact.alert_dedup_key(market_alerts[0]) != compact.alert_dedup_key(market_alerts[1]):
            errors.append("same US semiconductor market shock did not share an event dedupe key")
        first_seen_keys = production.telegram.alert_seen_keys(market_alerts[0])
        second_seen_keys = production.telegram.alert_seen_keys(market_alerts[1])
        if not set(first_seen_keys).intersection(second_seen_keys):
            errors.append("same market shock did not share a cross-run seen-state key")
    leverage_alert = next(
        (
            alert
            for alert in expanded_alerts
            if alert.get("korean_business_kind") == "single_stock_leverage_rule"
        ),
        None,
    )
    if leverage_alert:
        prior_day_coverage = dict(leverage_alert)
        prior_day_coverage["published"] = (now - dt.timedelta(days=1)).isoformat()
        if compact.alert_dedup_key(leverage_alert) != compact.alert_dedup_key(prior_day_coverage):
            errors.append("same effective-date leverage rule repeated across publication dates")

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
