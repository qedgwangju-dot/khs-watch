#!/usr/bin/env python3
"""Guard the GAMEJOA preopen radar delivery contract.

The radar must be delivered to the hs8879 policy Telegram lane. This guard is
intentionally strict so future edits cannot silently reroute the morning radar
to another bot or make Telegram failures look successful.
"""

from __future__ import annotations

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
    'GAMEJOA_KOREAN_BUSINESS_DETAIL_LIMIT: "36"',
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
    "limited_decision_impact_displayed",
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
]

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
    "MATRIX_TERMS",
    "FORBIDDEN_TEXT",
    "GAMEJOA generated report quality OK",
    "report/JSON selected count mismatch",
    "selection_diagnostics",
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


def assert_korean_business_article_contract(production, compact, now, errors: list[str]) -> None:
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

    for publisher, title, body, link, expected_kind in [
        (
            "이투데이",
            etoday_title,
            etoday_body,
            "https://www.etoday.co.kr/news/view/2606782",
            "foreign_semiconductor_flow",
        ),
        (
            "전자신문",
            etnews_title,
            etnews_body,
            "https://www.etnews.com/20260723000345",
            "exicon_cxl_tester",
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
        if not compact.source_output_aligned(normalized):
            errors.append(f"{publisher} source/output alignment failed")
        rendered = compact.compact_alert(normalized, 1, now, {}, {})
        required_markers = [
            "- 핵심:",
            "- 의사결정 영향:",
            "- 투자 포인트:",
            "- 한국장:",
            "- 반영/반대:",
            "- 실패 신호:",
            "원문 뉴스보기",
        ]
        for marker in required_markers:
            if marker not in rendered:
                errors.append(f"{publisher} compact Telegram summary missing {marker}")
        if "- 분류 매트릭스:" in rendered or "- 관련 해외 티커/지표:" in rendered:
            errors.append(f"{publisher} compact Telegram summary regressed to verbose format")

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


if __name__ == "__main__":
    raise SystemExit(main())
