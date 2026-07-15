#!/usr/bin/env python3
"""Guard the GAMEJOA preopen radar delivery contract.

The radar must be delivered to the hs8879 policy Telegram lane. This guard is
intentionally strict so future edits cannot silently reroute the morning radar
to another bot or make Telegram failures look successful.
"""

from __future__ import annotations

import importlib
import sys
import urllib.parse
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]

WORKFLOW_FILES = [
    ROOT / ".github" / "workflows" / "gamejoa-preopen-news-radar.yml",
    ROOT / ".github" / "workflows" / "gamejoa-preopen-news-radar-test.yml",
]

RUNNER_FILE = ROOT / "scripts" / "gamejoa_preopen_news_radar_full_compact_runner.py"
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
    "source_output_aligned(normalized)",
    "federal_register_uae_ear",
]

REQUIRED_TELEGRAM_RUNNER_SNIPPETS = [
    "gamejoa_preopen_news_radar_seen.json",
    "gamejoa_preopen_news_radar_delivery.json",
    "filter_previously_seen_alerts(classified, now)",
    "filter_alerts_for_run_mode(classified, now, live_mode)",
    "preopen_digest_seen_bypass",
    "record_seen_alerts(final_alerts, now)",
    "delivery_confirmed_sent()",
    "reset_delivery_status()",
    "seen_state_not_recorded",
    "preopen_send_window_open(now)",
    "RADAR_RUN_MODE",
    "final_alerts_for_output(deduped, limit)",
    '"selection_diagnostics": diagnostics',
    '"source_failures": source_failures',
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
    send_module = getattr(production.telegram.send_telegram, "__module__", "")
    compact_module = getattr(production.telegram.compact_report, "__module__", "")
    final_selection_module = getattr(production.telegram.final_alerts_for_output, "__module__", "")
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
        live_remaining, live_routed = production.telegram.partition_realtime_policy_alerts([normalized_iran], True)
        if live_remaining or live_routed != [normalized_iran]:
            errors.append("Iran/Hormuz alert was not single-routed away from live radar duplication")
        preopen_remaining, preopen_routed = production.telegram.partition_realtime_policy_alerts([normalized_iran], False)
        if preopen_remaining != [normalized_iran] or preopen_routed:
            errors.append("Iran/Hormuz alert was not retained for the 06:30 radar")

    # A story already announced by the real-time lane must still be available
    # to the once-daily 06:30 digest. This guards the failure where overnight
    # live polls consumed every preopen candidate before the morning run.
    seen_probe = [{
        "news": "장전 seen-state 회귀 검사",
        "original_news": "Preopen seen-state regression fixture",
        "publisher": "Reuters",
        "link": "https://www.reuters.com/world/preopen-seen-regression-fixture",
    }]
    original_seen_filter = production.telegram.filter_previously_seen_alerts
    production.telegram.filter_previously_seen_alerts = lambda alerts, _now: ([], list(alerts))
    try:
        live_fresh, live_skipped = production.telegram.filter_alerts_for_run_mode(seen_probe, now, True)
        preopen_fresh, preopen_skipped = production.telegram.filter_alerts_for_run_mode(seen_probe, now, False)
    finally:
        production.telegram.filter_previously_seen_alerts = original_seen_filter
    if live_fresh or live_skipped != seen_probe:
        errors.append("live radar no longer applies seen-state suppression")
    if len(preopen_fresh) != 1 or preopen_skipped:
        errors.append("06:30 preopen digest was incorrectly suppressed by live seen-state")
    elif not preopen_fresh[0].get("_seen_keys"):
        errors.append("06:30 preopen digest lost post-send seen-state keys")
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

    if errors:
        for error in errors:
            print(f"GAMEJOA delivery contract error: {error}")
        return 1

    print("GAMEJOA delivery contract OK: hs8879 Telegram lane is locked and send failures are fatal.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
