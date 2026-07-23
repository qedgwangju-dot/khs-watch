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
    "ì›ì¸ ê·œëª…",
    "ì¬ë°œ ë°©ì§€ íšŒê·€ í…ŒìŠ¤íŠ¸",
    "ë°˜ì˜ ì™„ë£Œ",
    "ì¬ê²€ì¦ ì™„ë£Œ",
    "ì‹¤ì œ ì†¡ì¶œ ìƒíƒœ",
    "skipped_empty",
    "Actions ì„±ê³µë§Œìœ¼ë¡œ ì™„ë£Œ ì²˜ë¦¬í•˜ì§€ ì•ŠëŠ”ë‹¤",
    "ì‹¤ì œ ì‹ ê·œ ì•Œë¦¼ ì†¡ì¶œ ë¯¸ê´€ì°°",
    "ì „ë‚  ì¥ì „íŒ í•­ëª© ì¬ì†¡ì¶œ ê¸ˆì§€",
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
    required_query_labels = {"íŠ¸ëŸ¼í”„ ì§ì ‘ë°œì–¸/ì •ì±…", "ì´ë€/í˜¸ë¥´ë¬´ì¦ˆ ê¸´ê¸‰ìƒí™©", "ë°˜ë„ì²´/AI/HBM", "K-ë°©ì‚°", "êµ­ë‚´ ì •ì±…", "ë°”ì´ì˜¤/FDA"}
    query_labels = {name for name, _query in query_plan}
    required_query_labels.add("ì¤‘êµ­ ìƒë¬´ë¶€ ìˆ˜ì¶œí†µì œ/ê´€ì„¸")
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
        "source": "Trusted news ì¤‘êµ­ ìƒë¬´ë¶€ ìˆ˜ì¶œí†µì œ/ê´€ì„¸",
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
        if "ì¤‘êµ­ ìƒë¬´ë¶€" not in str(normalized_china.get("news") or "") or "í—¬ë¥¨" not in str(normalized_china.get("news") or ""):
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
ÛŞt¶‰ËkºwµçP4(€€€€Œ±¥Ù”Á½±±Ì½¹ÍÕµ••Ù•ÉäÁÉ•½Á•¸…¹‘¥‘…Ñ”‰•™½É”Ñ¡”µ½É¹¥¹œÉÕ¸¸4(€€€±¥Ù•}½¹±å}ÁÉ½‰”€ôì4(€€€€€€€€‰¹•İÌˆè€‹²z—²‚Í••¸µÍÑ…Ñ”ƒ¶j3ªŞ ƒªÊ²
°ˆ°4(€€€€€€€€‰½É¥¥¹…±}¹•İÌˆè€‰AÉ•½Á•¸Í••¸µÍÑ…Ñ”É•É•ÍÍ¥½¸™¥áÑÕÉ”ˆ°4(€€€€€€€€‰ÁÕ‰±¥Í¡•Èˆè€‰I•ÕÑ•ÉÌˆ°4(€€€€€€€€‰±¥¹¬ˆè€‰¡ÑÑÁÌè¼½İİÜ¹É•ÕÑ•ÉÌ¹½´½İ½É±½ÁÉ•½Á•¸µÍ••¸µÉ•É•ÍÍ¥½¸µ™¥áÑÕÉ”ˆ°4(€€€ô4(€€€ÁÉ•½Á•¹}ÁÉ½‰”€ôì4(€€€€€€€€‰¹•İÌˆè€‹²‚®
€ƒ²z—²‚¶2@ƒ²’G®ÎÔƒ¶j3ªŞ ƒªÊ²
°ˆ°4(€€€€€€€€‰½É¥¥¹…±}¹•İÌˆè€‰AÉ¥½ÈÁÉ•½Á•¸‘ÕÁ±¥…Ñ”É•É•ÍÍ¥½¸™¥áÑÕÉ”ˆ°4(€€€€€€€€‰ÁÕ‰±¥Í¡•Èˆè€‰I•ÕÑ•ÉÌˆ°4(€€€€€€€€‰±¥¹¬ˆè€‰¡ÑÑÁÌè¼½İİÜ¹É•ÕÑ•ÉÌ¹½´½İ½É±½ÁÉ¥½ÈµÁÉ•½Á•¸µ‘ÕÁ±¥…Ñ”µÉ•É•ÍÍ¥½¸µ™¥áÑÕÉ”ˆ°4(€€€ô4(€€€±¥Ù•}­•ä€ôÁÉ½‘ÕÑ¥½¸¹Ñ•±•É…´¹…±•ÉÑ}Í••¹}­•åÌ¡±¥Ù•}½¹±å}ÁÉ½‰”¥lÁt4(€€€ÁÉ•½Á•¹}­•ä€ôÁÉ½‘ÕÑ¥½¸¹Ñ•±•É…´¹…±•ÉÑ}Í••¹}­•åÌ¡ÁÉ•½Á•¹}ÁÉ½‰”¥lÁt4(€€€½É¥¥¹…±}±½…‘}Í••¹}ÍÑ…Ñ”€ôÁÉ½‘ÕÑ¥½¸¹Ñ•±•É…´¹±½…‘}Í••¹}ÍÑ…Ñ”4(€€€ÁÉ½‘ÕÑ¥½¸¹Ñ•±•É…´¹±½…‘}Í••¹}ÍÑ…Ñ”€ô±…µ‰‘„èì4(€€€€€€€€‰Í••¸ˆèì4(€€€€€€€€€€€±¥Ù•}­•äèì‰™¥ÉÍÑ}Í••¹}­ÍĞˆè¹½Ü¹¥Í½™½Éµ…Ğ ¤°€‰±…¹•Ìˆèì‰±¥Ù”ˆè¹½Ü¹¥Í½™½Éµ…Ğ ¥õô°4(€€€€€€€€€€€ÁÉ•½Á•¹}­•äèì‰™¥ÉÍÑ}Í••¹}­ÍĞˆè¹½Ü¹¥Í½™½Éµ…Ğ ¤°€‰±…¹•Ìˆèì‰ÁÉ•½Á•¸ˆè¹½Ü¹¥Í½™½Éµ…Ğ ¥õô°4(€€€€€€€ô°4(€€€€€€€€‰ÕÁ‘…Ñ•‘}…Ñ}­ÍĞˆè¹½Ü¹¥Í½™½Éµ…Ğ ¤°4(€€€ô4(€€€ÑÉäè4(€€€€€€€ÁÉ½‰•Ì€ôm±¥Ù•}½¹±å}ÁÉ½‰”°ÁÉ•½Á•¹}ÁÉ½‰•t4(€€€€€€€±¥Ù•}™É•Í °±¥Ù•}Í­¥ÁÁ•€ôÁÉ½‘ÕÑ¥½¸¹Ñ•±•É…´¹™¥±Ñ•É}…±•ÉÑÍ}™½É}ÉÕ¹}µ½‘”¡ÁÉ½‰•Ì°¹½Ü°QÉÕ”¤4(€€€€€€€ÁÉ•½Á•¹}™É•Í °ÁÉ•½Á•¹}Í­¥ÁÁ•€ôÁÉ½‘ÕÑ¥½¸¹Ñ•±•É…´¹™¥±Ñ•É}…±•ÉÑÍ}™½É}ÉÕ¹}µ½‘”¡ÁÉ½‰•Ì°¹½Ü°…±Í”¤4(€€€™¥¹…±±äè4(€€€€€€€ÁÉ½‘ÕÑ¥½¸¹Ñ•±•É…´¹±½…‘}Í••¹}ÍÑ…Ñ”€ô½É¥¥¹…±}±½…‘}Í••¹}ÍÑ…Ñ”4(€€€¥˜±¥Ù•}™É•Í ½È±¥Ù•}Í­¥ÁÁ•€„ôÁÉ½‰•Ìè4(€€€€€€€•ÉÉ½ÉÌ¹…ÁÁ•¹ ‰±¥Ù”É…‘…È¹¼±½¹•È…ÁÁ±¥•ÌÍ••¸µÍÑ…Ñ”ÍÕÁÁÉ•ÍÍ¥½¸ˆ¤4(€€€¥˜±•¸¡ÁÉ•½Á•¹}™É•Í ¤€„ô€Ä½ÈÁÉ•½Á•¹}™É•Í¡lÁt¹•Ğ ‰±¥¹¬ˆ¤€„ô±¥Ù•}½¹±å}ÁÉ½‰•l‰±¥¹¬‰tè4(€€€€€€€•ÉÉ½ÉÌ¹…ÁÁ•¹ ˆÀØèÌÀÁÉ•½Á•¸‘¥•ÍĞ‘¥¹½ĞÉ•Ñ…¥¸Ñ¡”±¥Ù”µ½¹±äÍÑ½Éäˆ¤4(€€€•±¥˜¹½ĞÁÉ•½Á•¹}™É•Í¡lÁt¹•Ğ ‰}ÁÉ•½Á•¹}±¥Ù•}Í••¹}‰åÁ…ÍÌˆ¤è4(€€€€€€€•ÉÉ½ÉÌ¹…ÁÁ•¹ ˆÀØèÌÀÁÉ•½Á•¸‘¥•ÍĞ±½ÍĞ¥ÑÌ±¥Ù”µÍ••¸‰åÁ…ÍÌµ…É­•Èˆ¤4(€€€¥˜±•¸¡ÁÉ•½Á•¹}Í­¥ÁÁ•¤€„ô€Ä½ÈÁÉ•½Á•¹}Í­¥ÁÁ•‘lÁt¹•Ğ ‰±¥¹¬ˆ¤€„ôÁÉ•½Á•¹}ÁÉ½‰•l‰±¥¹¬‰tè4(€€€€€€€•ÉÉ½ÉÌ¹…ÁÁ•¹ ˆÀØèÌÀÁÉ•½Á•¸‘¥•ÍĞÉ•Á•…Ñ•„ÁÉ¥½ÈÁÉ•½Á•¸ÍÑ½Éäˆ¤4(€€€¥˜¹½ĞÁÉ½‘ÕÑ¥½¸¹Ñ•±•É…´¹Í••¹}•¹ÑÉå}¡…Í}±…¹”¡ì‰™¥ÉÍÑ}Í••¹}­ÍĞˆè¹½Ü¹¥Í½™½Éµ…Ğ ¥ô°€‰ÁÉ•½Á•¸ˆ¤è4(€€€€€€€•ÉÉ½ÉÌ¹…ÁÁ•¹ ‰±•…äÍ••¸µÍÑ…Ñ”İ…Ì¹½ĞÍÕÁÁÉ•ÍÍ•™É½´É•Á•…ĞÁÉ•½Á•¸‘•±¥Ù•Éäˆ¤4(4(€€€±•…å}ÍÑ…Ñ”€ôì4(€€€€€€€€‰Í••¸ˆèì4(€€€€€€€€€€€€‰Ñ¥Ñ±”é½±µÉ…ÜµÍ½ÕÉ”µ­•äˆèì4(€€€€€€€€€€€€€€€€‰™¥ÉÍÑ}Í••¹}­ÍĞˆè¹½Ü¹¥Í½™½Éµ…Ğ ¤°4(€€€€€€€€€€€€€€€€‰Ñ¥Ñ±”ˆè€‹®¾ãªÖ´°ƒ²vÓ®z ƒ²z³ªÎ×ªÊ§
ß¶bã®–Ó®²Ó²š ƒ²²€ƒ¶RóªÊ¤èƒ¶rÓ²‚
ß²rƒªÂ ƒ®š³²*“¶°ˆ°4(€€€€€€€€€€€ô4(€€€€€€€ô4(€€€ô4(€€€ÁÉ½‘ÕÑ¥½¸¹Ñ•±•É…´¹µ¥É…Ñ•}Í••¹}Ñ¥Ñ±•}…±¥…Í•Ì¡±•…å}ÍÑ…Ñ”¤4(€€€•áÁ•Ñ•‘}±•…å}…±¥…Ì€ô€‰Ñ¥Ñ±”èˆ€¬ÁÉ½‘ÕÑ¥½¸¹Ñ•±•É…´¹‘¥•ÍÑ}Í••¸ 4(€€€€€€€€‹®¾ãªÖ´°ƒ²vÓ®z ƒ²z³ªÎ×ªÊ§
ß¶bã®–Ó®²Ó²š ƒ²²€ƒ¶RóªÊ¤èƒ¶rÓ²‚
ß²rƒªÂ ƒ®š³²*“¶°ˆ4(€€€€¤4(€€€¥˜•áÁ•Ñ•‘}±•…å}…±¥…Ì¹½Ğ¥¸±•…å}ÍÑ…Ñ•l‰Í••¸‰tè4(€€€€€€€•ÉÉ½ÉÌ¹…ÁÁ•¹ ‰±•…äÍ••¸µÍÑ…Ñ”‘¥¹½Ğ…¥¸„…¹½¹¥…°-½É•…¸µÑ¥Ñ±”…±¥…Ìˆ¤4(4(€€€±…¹•}ÍÑ…Ñ”€ôì4(€€€€€€€€‰Í••¸ˆèì4(€€€€€€€€€€€±¥Ù•}­•äèì4(€€€€€€€€€€€€€€€€‰™¥ÉÍÑ}Í••¹}­ÍĞˆè¹½Ü¹¥Í½™½Éµ…Ğ ¤°4(€€€€€€€€€€€€€€€€‰±…¹•Ìˆèì‰±¥Ù”ˆè¹½Ü¹¥Í½™½Éµ…Ğ ¥ô°4(€€€€€€€€€€€ô4(€€€€€€€ô°4(€€€€€€€€‰ÕÁ‘…Ñ•‘}…Ñ}­ÍĞˆè¹½Ü¹¥Í½™½Éµ…Ğ ¤°4(€€€ô4(€€€½É¥¥¹…±}±½…‘}Í••¹}ÍÑ…Ñ”€ôÁÉ½‘ÕÑ¥½¸¹Ñ•±•É…´¹±½…‘}Í••¹}ÍÑ…Ñ”4(€€€½É¥¥¹…±}Í…Ù•}Í••¹}ÍÑ…Ñ”€ôÁÉ½‘ÕÑ¥½¸¹Ñ•±•É…´¹Í…Ù•}Í••¹}ÍÑ…Ñ”4(€€€½É¥¥¹…±}ÉÕ¹}µ½‘”€ô½Ì¹•¹Ù¥É½¸¹•Ğ ‰II}IU9}5=ˆ¤4(€€€ÁÉ½‘ÕÑ¥½¸¹Ñ•±•É…´¹±½…‘}Í••¹}ÍÑ…Ñ”€ô±…µ‰‘„è±…¹•}ÍÑ…Ñ”4(€€€ÁÉ½‘ÕÑ¥½¸¹Ñ•±•É…´¹Í…Ù•}Í••¹}ÍÑ…Ñ”€ô±…µ‰‘„ÍÑ…Ñ”°}¹½Üè±…¹•}ÍÑ…Ñ”¹ÕÁ‘…Ñ”¡ÍÑ…Ñ”¤4(€€€ÑÉäè4(€€€€€€€½Ì¹•¹Ù¥É½¹l‰II}IU9}5=‰t€ô€‰ÁÉ•½Á•¸ˆ4(€€€€€€€É•½É‘•‘}ÁÉ½‰”€ô‘¥Ğ¡±¥Ù•}½¹±å}ÁÉ½‰”¤4(€€€€€€€É•½É‘•‘}ÁÉ½‰•l‰}Í••¹}­•åÌ‰t€ôm±¥Ù•}­•åt4(€€€€€€€ÁÉ½‘ÕÑ¥½¸¹Ñ•±•É…´¹É•½É‘}Í••¹}…±•ÉÑÌ¡mÉ•½É‘•‘}ÁÉ½‰•t°¹½Ü¤4(€€€™¥¹…±±äè4(€€€€€€€ÁÉ½‘ÕÑ¥½¸¹Ñ•±•É…´¹±½…‘}Í••¹}ÍÑ…Ñ”€ô½É¥¥¹…±}±½…‘}Í••¹}ÍÑ…Ñ”4(€€€€€€€ÁÉ½‘ÕÑ¥½¸¹Ñ•±•É…´¹Í…Ù•}Í••¹}ÍÑ…Ñ”€ô½É¥¥¹…±}Í…Ù•}Í••¹}ÍÑ…Ñ”4(€€€€€€€¥˜½É¥¥¹…±}ÉÕ¹}µ½‘”¥Ì9½¹”è4(€€€€€€€€€€€½Ì¹•¹Ù¥É½¸¹Á½À ‰II}IU9}5=ˆ°9½¹”¤4(€€€€€€€•±Í”è4(€€€€€€€€€€€½Ì¹•¹Ù¥É½¹l‰II}IU9}5=‰t€ô½É¥¥¹…±}ÉÕ¹}µ½‘”4(€€€É•½É‘•‘}±…¹•Ì€ô±…¹•}ÍÑ…Ñ•l‰Í••¸‰um±¥Ù•}­•åt¹•Ğ ‰±…¹•Ìˆ¤½Èíô4(€€€¥˜¹½Ğì‰±¥Ù”ˆ°€‰ÁÉ•½Á•¸‰ô¹¥ÍÍÕ‰Í•Ğ¡Í•Ğ¡É•½É‘•‘}±…¹•Ì¤¤è4(€€€€€€€•ÉÉ½ÉÌ¹…ÁÁ•¹¡˜‰Í••¸µÍÑ…Ñ”‘¥¹½ĞÁÉ•Í•ÉÙ”±¥Ù”…¹ÁÉ•½Á•¸±…¹•ÌèíÉ•½É‘•‘}±…¹•Íôˆ¤4(4(€€€€ŒQ¡”Í•¹‘•È…¹Á½ÍĞµÍ•¹Ù•É¥™¥•ÈµÕÍĞ¥¹Ñ•ÉÁÉ•ĞÑ¡”µ…¹Õ…°½™˜µİ¥¹‘½Ü4(€€€€ŒÍİ¥Ñ ¥‘•¹Ñ¥…±±ä¸=Ñ¡•Éİ¥Í”Q•±•É…´…¸‰”Í•¹Ğİ¡¥±”Ñ¥½¹ÌÉ•Á½ÉÑÌ4(€€€€Œ„™…±Í”™…¥±ÕÉ”°İ¡¥ ¡¥‘•ÌÑ¡”É•…°‘•±¥Ù•ÉäÉ•ÍÕ±Ğ¸4(€€€Ñ•ÍÑ•‘}•¹Ø€ôì4(€€€€€€€€‰II}IU9}5=ˆè½Ì¹•¹Ù¥É½¸¹•Ğ ‰II}IU9}5=ˆ¤°4(€€€€€€€€‰11=]}=}]%9=]}Q1I4ˆè½Ì¹•¹Ù¥É½¸¹•Ğ ‰11=]}=}]%9=]}Q1I4ˆ¤°4(€€€€€€€€‰AI=A9}M9}]%9=]}MQIQ}-MPˆè½Ì¹•¹Ù¥É½¸¹•Ğ ‰AI=A9}M9}]%9=]}MQIQ}-MPˆ¤°4(€€€€€€€€‰AI=A9}M9}]%9=]}9}-MPˆè½Ì¹•¹Ù¥É½¸¹•Ğ ‰AI=A9}M9}]%9=]}9}-MPˆ¤°4(€€€ô4(€€€ÑÉäè4(€€€€€€€½Ì¹•¹Ù¥É½¹l‰II}IU9}5=‰t€ô€‰ÁÉ•½Á•¸ˆ4(€€€€€€€½Ì¹•¹Ù¥É½¹l‰AI=A9}M9}]%9=]}MQIQ}-MP‰t€ô€ˆÀÔèÌÀˆ4(€€€€€€€½Ì¹•¹Ù¥É½¹l‰AI=A9}M9}]%9=]}9}-MP‰t€ô€ˆÀÜèÌÀˆ4(€€€€€€€½Ì¹•¹Ù¥É½¹l‰11=]}=}]%9=]}Q1I4‰t€ô€‰ÑÉÕ”ˆ4(€€€€€€€½™™}İ¥¹‘½İ}Ñ¥µ”€ô¹½Ü¹É•Á±…”¡¡½ÕÈôÄØ°µ¥¹ÕÑ”ôÀ°Í•½¹ôÀ°µ¥É½Í•½¹ôÀ¤4(€€€€€€€¥˜¹½Ğ½µÁ…Ğ¹ÁÉ•½Á•¹}Í•¹‘}İ¥¹‘½İ}½Á•¸ ¤è4(€€€€€€€€€€€•ÉÉ½ÉÌ¹…ÁÁ•¹ ‰Q•±•É…´Í•¹‘•È¥¹½É•11=]}=}]%9=]}Q1I4õÑÉÕ”ˆ¤4(€€€€€€€¥˜¹½ĞÉÕ¹Ñ¥µ•}‘•±¥Ù•Éä¹Í•¹‘}İ¥¹‘½İ}½Á•¸¡½™™}İ¥¹‘½İ}Ñ¥µ”¤è4(€€€€€€€€€€€•ÉÉ½ÉÌ¹…ÁÁ•¹ ‰ÉÕ¹Ñ¥µ”‘•±¥Ù•ÉäÙ•É¥™¥•È¥¹½É•11=]}=}]%9=]}Q1I4õÑÉÕ”ˆ¤4(€€€€€€€½Ì¹•¹Ù¥É½¹l‰11=]}=}]%9=]}Q1I4‰t€ô€‰™…±Í”ˆ4(€€€€€€€¥˜ÉÕ¹Ñ¥µ•}‘•±¥Ù•Éä¹Í•¹‘}İ¥¹‘½İ}½Á•¸¡½™™}İ¥¹‘½İ}Ñ¥µ”¤è4(€€€€€€€€€€€•ÉÉ½ÉÌ¹…ÁÁ•¹ ‰ÉÕ¹Ñ¥µ”‘•±¥Ù•ÉäÙ•É¥™¥•È½Á•¹•Ñ¡”¹½Éµ…°ÁÉ•½Á•¸İ¥¹‘½Ü…Ğ€ÄØèÀÀ-MPˆ¤4(€€€™¥¹…±±äè4(€€€€€€€™½È¹…µ”°Ù…±Õ”¥¸Ñ•ÍÑ•‘}•¹Ø¹¥Ñ•µÌ ¤è4(€€€€€€€€€€€¥˜Ù…±Õ”¥Ì9½¹”è4(€€€€€€€€€€€€€€€½Ì¹•¹Ù¥É½¸¹Á½À¡¹…µ”°9½¹”¤4(€€€€€€€€€€€•±Í”è4(€€€€€€€€€€€€€€€½Ì¹•¹Ù¥É½¹m¹…µ•t€ôÙ…±Õ”4(4(€€€¥˜Í•¹‘}µ½‘Õ±”€„ô1=-}Q1I5}5=U1è4(€€€€€€€•ÉÉ½ÉÌ¹…ÁÁ•¹ 4(€€€€€€€€€€€˜‰íAI=UQ%=9}IU99Iô¹Ñ•±•É…´¹Í•¹‘}Ñ•±•É…´¥Ìİ¥É•Ñ¼íÍ•¹‘}µ½‘Õ±•ô°€ˆ4(€€€€€€€€€€€˜‰•áÁ•Ñ•í1=-}Q1I5}5=U1ôˆ4(€€€€€€€€¤4(€€€¥˜½µÁ…Ñ}µ½‘Õ±”€„ô1=-}Q1I5}5=U1è4(€€€€€€€•ÉÉ½ÉÌ¹…ÁÁ•¹ 4(€€€€€€€€€€€˜‰íAI=UQ%=9}IU99Iô¹Ñ•±•É…´¹½µÁ…Ñ}É•Á½ÉĞ¥Ìİ¥É•Ñ¼í½µÁ…Ñ}µ½‘Õ±•ô°€ˆ4(€€€€€€€€€€€˜‰•áÁ•Ñ•í1=-}Q1I5}5=U1ôˆ4(€€€€€€€€¤4(€€€¥˜™¥¹…±}Í•±•Ñ¥½¹}µ½‘Õ±”€„ô1=-}Q1I5}5=U1è4(€€€€€€€•ÉÉ½ÉÌ¹…ÁÁ•¹ 4(€€€€€€€€€€€˜‰íAI=UQ%=9}IU99Iô¹Ñ•±•É…´¹™¥¹…±}…±•ÉÑÍ}™½É}½ÕÑÁÕĞ¥Ìİ¥É•Ñ¼í™¥¹…±}Í•±•Ñ¥½¹}µ½‘Õ±•ô°€ˆ4(€€€€€€€€€€€˜‰•áÁ•Ñ•í1=-}Q1I5}5=U1ôˆ4(€€€€€€€€¤4(€€€¥˜…¹½¹¥…±}Í••¹}µ½‘Õ±”€„ô1=-}Q1I5}5=U1è4(€€€€€€€•ÉÉ½ÉÌ¹…ÁÁ•¹ 4(€€€€€€€€€€€˜‰íAI=UQ%=9}IU99Iô¹Ñ•±•É…´¹…¹½¹¥…±}…±•ÉÑ}™½É}Í••¸¥Ìİ¥É•Ñ¼í…¹½¹¥…±}Í••¹}µ½‘Õ±•ô°€ˆ4(€€€€€€€€€€€˜‰•áÁ•Ñ•í1=-}Q1I5}5=U1ôˆ4(€€€€€€€€¤4(4(€€€¥˜•ÉÉ½ÉÌè4(€€€€€€€™½È•ÉÉ½È¥¸•ÉÉ½ÉÌè4(€€€€€€€€€€€ÁÉ¥¹Ğ¡˜‰5)=‘•±¥Ù•Éä½¹ÑÉ…Ğ•ÉÉ½Èèí•ÉÉ½Éôˆ¤4(€€€€€€€É•ÑÕÉ¸€Ä4(4(€€€ÁÉ¥¹Ğ ‰5)=‘•±¥Ù•Éä½¹ÑÉ…Ğ=,è¡ÌààÜäQ•±•É…´±…¹”¥Ì±½­•…¹Í•¹™…¥±ÕÉ•Ì…É”™…Ñ…°¸ˆ¤(€€€É•ÑÕÉ¸€À(()‘•˜…ÍÍ•ÉÑ}­½É•…¹}‰ÕÍ¥¹•ÍÍ}…ÉÑ¥±•}½¹ÑÉ…Ğ¡ÁÉ½‘ÕÑ¥½¸°½µÁ…Ğ°¹½Ü°•ÉÉ½ÉÌè±¥ÍÑmÍÑÉt¤€´ø9½¹”è(€€€•Ñ½‘…å}Ñ¥Ñ±”€ô€‹²fãªÖ·²và°ƒ²
ó²‚
İM/¶Vc®.$€Ğ¸×²†Àƒ²
³®N“²^³Š›®Âc®>²ÊÓ®>ƒªÎ£®vğƒ®.Ó²Vc®.ˆ(€€€•Ñ½‘…å}‰½‘ä€ô€ (€€€€€€€€‹²fãªÖ·²vã²v €ÓªÆÃ®zc²vğƒ®>g²V ƒ²
ó²Ç²‚²z@€Ë²†ÀäÌÈß²Z×²nCªÎğM/¶Vc²vÓ®.'²*€ˆ(€€€€€€€€ˆÇ²†ÀÔĞÄÛ²Z×²nC²vƒ²"s®“²"c¶Z#®.¸ƒ®F@ƒ²Š®ª¤ƒ¶V§ªÎ®*Pƒ²Vô€Ó²†ÀÔÀÀÃ²Z×²nC²vÓ®.¸€ˆ(€€€€€€€€‹®Âc®¦Ğƒ²vó®Ú ƒ®Âc®>²ÊĞƒ²3²z³
ß®Ú¶J#
ß²z—®æƒ²Š®ª§²v ƒ²"s®“®>¶VĞƒ²^²Šƒ®
Ó®Ú ƒ²Â£®Î¶fSªÂ ƒ®
c¶®
³®.¸ˆ(€€€€¤(€€€•Ñ¹•İÍ}Ñ¥Ñ±”€ô€‹²^G².s²ö`°ƒ²Â£²ã®2 a0€Ì¸Äƒ¶3²*“¶Àƒ²²j§¶fPƒ²7®>ˆ(€€€•Ñ¹•İÍ}‰½‘ä€ô€ (€€€€€€€€‹²^G².s²öc²v ƒ²
ó²Ç²‚²zC²f •¸Øƒ®Â<a0€Ì¸Äƒ¶3²*“¶Àƒ²ZG²
Ã¶>'ªÂ®–ğƒ²¶Z'¶VcªÎ€ƒ²z#®.¸€ˆ(€€€€€€€€‹¶>'ªÂ®*Pƒ²vÓ®.°ƒ®@ƒ®#®²Ó®š³®B€ƒ²b#²‚W²vÓ®¦À°ƒ²ZG²
Ã¶>'ªÂ ƒ¶×ªÎğƒ®Jƒ².“²‚pƒ²z—®æƒ®Âs²óªÂ ƒ®
£²Vƒ²z#®.¸€ˆ(€€€€€€€€‹¶j3²
³®*Pƒ²®
s¶VĞƒ®“²Úp€ÄÀÄã²Z×²nC²vƒªâÃ®†w¶Z#®.¸ˆ(€€€€¤((€€€‘•˜™¥áÑÕÉ”¡Ñ¥Ñ±”èÍÑÈ°‰½‘äèÍÑÈ¤€´øÍÑÈè(€€€€€€€É•ÑÕÉ¸˜ˆˆˆ(€€€€€€€€ñ¡Ñµ°øñ¡•…ø(€€€€€€€€€€ñµ•Ñ„ÁÉ½Á•ÉÑäô‰½œéÑ¥Ñ±”ˆ½¹Ñ•¹Ğô‰íÑ¥Ñ±•ôˆø(€€€€€€€€€€ñµ•Ñ„ÁÉ½Á•ÉÑäô‰…ÉÑ¥±”éÁÕ‰±¥Í¡•‘}Ñ¥µ”ˆ½¹Ñ•¹ĞôˆÈÀÈØ´ÀÜ´ÈÍPÄÜèÀÀèÀÀ¬ÀäèÀÀˆø(€€€€€€€€ğ½¡•…øñ‰½‘äøñ‘¥Ø¥Ñ•µÁÉ½Àô‰…ÉÑ¥±•	½‘äˆø(€€€€€€€€€€ñ ÄùíÑ¥Ñ±•ôğ½ ÄøñÀùí‰½‘åôğ½Àø(€€€€€€€€€€ñÀûªâÃ²
°ƒ²nC®²ã²v ƒªÒ®‚ ƒªâÃ²^²v`ƒ¶n²4ƒ²"cªâ$°ƒªÎƒªÂtƒ¶>'ªÂ °ƒ®Âs²ó²f ƒªÎ×².s®–ğƒ¶V£ªî`ƒ¶fW²vã¶VÓ²Vğƒ¶Vs®.“ªÎ€ƒ²“®ª¶Z#®.¸ğ½Àø(€€€€€€€€ğ½‘¥Øøğ½‰½‘äøğ½¡Ñµ°ø(€€€€€€€€ˆˆˆ((€€€™½ÈÁÕ‰±¥Í¡•È°Ñ¥Ñ±”°‰½‘ä°±¥¹¬°•áÁ•Ñ•‘}­¥¹¥¸l(€€€€€€€€ (€€€€€€€€€€€€‹²vÓ¶"³®6Ã²vĞˆ°(€€€€€€€€€€€•Ñ½‘…å}Ñ¥Ñ±”°(€€€€€€€€€€€•Ñ½‘…å}‰½‘ä°(€€€€€€€€€€€€‰¡ÑÑÁÌè¼½İİÜ¹•Ñ½‘…ä¹¼¹­È½¹•İÌ½Ù¥•Ü¼ÈØÀØÜàÈˆ°(€€€€€€€€€€€€‰™½É•¥¹}Í•µ¥½¹‘ÕÑ½É}™±½Üˆ°(€€€€€€€€¤°(€€€€€€€€ (€€€€€€€€€€€€‹²‚²zC².ƒ®²àˆ°(€€€€€€€€€€€•Ñ¹•İÍ}Ñ¥Ñ±”°(€€€€€€€€€€€•Ñ¹•İÍ}‰½‘ä°(€€€€€€€€€€€€‰¡ÑÑÁÌè¼½İİÜ¹•Ñ¹•İÌ¹½´¼ÈÀÈØÀÜÈÌÀÀÀÌĞÔˆ°(€€€€€€€€€€€€‰•á¥½¹}á±}Ñ•ÍÑ•Èˆ°(€€€€€€€€¤°(€€€tè(€€€€€€€‘•Ñ…¥°€ô½µÁ…Ğ¹•áÑÉ…Ñ}…ÉÑ¥±•}‘•Ñ…¥°¡™¥áÑÕÉ”¡Ñ¥Ñ±”°‰½‘ä¤°Ñ¥Ñ±”¤(€€€€€€€¥˜¹½Ğ‘•Ñ…¥°¹•Ğ ‰‰½‘å}Ù•É¥™¥•ˆ¤½È¹½Ğ‘•Ñ…¥°¹•Ğ ‰Ñ¥Ñ±•}…±¥¹•ˆ¤è(€€€€€€€€€€€•ÉÉ½ÉÌ¹…ÁÁ•¹¡˜‰íÁÕ‰±¥Í¡•Éô…ÉÑ¥±”Ñ¥Ñ±”½‰½‘äÙ•É¥™¥…Ñ¥½¸™…¥±•ˆ¤(€€€€€€€€€€€½¹Ñ¥¹Õ”(€€€€€€€É½Ü€ôì(€€€€€€€€€€€€‰Í½ÕÉ”ˆè˜‰íÁÕ‰±¥Í¡•Éôƒ®Âc®>²ÊĞƒ®&Ó²*ˆ°(€€€€€€€€€€€€‰±…å•Èˆè€‰ÑÉÕÍÑ•ˆ°(€€€€€€€€€€€€‰ÁÕ‰±¥Í¡•ÈˆèÁÕ‰±¥Í¡•È°(€€€€€€€€€€€€‰Ñ¥Ñ±”ˆèÑ¥Ñ±”°(€€€€€€€€€€€€‰Í½ÕÉ•}Ñ¥Ñ±”ˆè‘•Ñ…¥±l‰Ñ¥Ñ±”‰t°(€€€€€€€€€€€€‰Í½ÕÉ•}‰½‘äˆè‘•Ñ…¥±l‰‰½‘ä‰t°(€€€€€€€€€€€€‰Í½ÕÉ•}…‰ÍÑÉ…Ğˆè‘•Ñ…¥±l‰‰½‘ä‰t°(€€€€€€€€€€€€‰ÍÕµµ…Éäˆè‘•Ñ…¥±l‰‰½‘ä‰t°(€€€€€€€€€€€€‰±¥¹¬ˆè±¥¹¬°(€€€€€€€€€€€€‰ÁÕ‰±¥Í¡•ˆè¹½Ü°(€€€€€€€€€€€€‰‰½‘å}Ù•É¥™¥•ˆèQÉÕ”°(€€€€€€€ô(€€€€€€€…±•ÉĞ€ôÁÉ½‘ÕÑ¥½¸¹½¹ÑÉ…Ğ¹ÍÑÉ¥Ğ¹±…ÍÍ¥™ä¡É½Ü°¹½Ü¤(€€€€€€€¥˜¹½Ğ…±•ÉĞè(€€€€€€€€€€€•ÉÉ½ÉÌ¹…ÁÁ•¹¡˜‰íÁÕ‰±¥Í¡•ÉôÙ•É¥™¥•…ÉÑ¥±”İ…Ì¹½Ğ±…ÍÍ¥™¥•ˆ¤(€€€€€€€€€€€½¹Ñ¥¹Õ”(€€€€€€€¹½Éµ…±¥é•€ô½µÁ…Ğ¹¹½Éµ…±¥é•}…±•ÉÑ}™½É}½ÕÑÁÕĞ¡…±•ÉĞ¤(€€€€€€€¥˜¹½Éµ…±¥é•¹•Ğ ‰¹•İÌˆ¤€„ôÑ¥Ñ±”è(€€€€€€€€€€€•ÉÉ½ÉÌ¹…ÁÁ•¹ (€€€€€€€€€€€€€€€˜‰íÁÕ‰±¥Í¡•Éô•á…Ğ-½É•…¸Í½ÕÉ”Ñ¥Ñ±”İ…Ì½Ù•ÉİÉ¥ÑÑ•¸èí¹½Éµ…±¥é•¹•Ğ ¹•İÌœ¥ôˆ(€€€€€€€€€€€€¤(€€€€€€€¥˜¹½Éµ…±¥é•¹•Ğ ‰­½É•…¹}‰ÕÍ¥¹•ÍÍ}­¥¹ˆ¤€„ô•áÁ•Ñ•‘}­¥¹è(€€€€€€€€€€€•ÉÉ½ÉÌ¹…ÁÁ•¹ (€€€€€€€€€€€€€€€˜‰íÁÕ‰±¥Í¡•Éô…ÉÑ¥±”‘¥¹½ĞÍ•±•Ğ¥ÑÌÍÁ•¥™¥ŒÁÉ½™¥±”è€ˆ(€€€€€€€€€€€€€€€˜‰í¹½Éµ…±¥é•¹•Ğ ­½É•…¹}‰ÕÍ¥¹•ÍÍ}­¥¹œ¥ôˆ(€€€€€€€€€€€€¤(€€€€€€€¥˜¹½Ğ½µÁ…Ğ¹Í½ÕÉ•}½ÕÑÁÕÑ}…±¥¹•¡¹½Éµ…±¥é•¤è(€€€€€€€€€€€•ÉÉ½ÉÌ¹…ÁÁ•¹¡˜‰íÁÕ‰±¥Í¡•ÉôÍ½ÕÉ”½½ÕÑÁÕĞ…±¥¹µ•¹Ğ™…¥±•ˆ¤(€€€€€€€É•¹‘•É•€ô½µÁ…Ğ¹½µÁ…Ñ}…±•ÉĞ¡¹½Éµ…±¥é•°€Ä°¹½Ü°íô°íô¤(€€€€€€€É•ÅÕ¥É•‘}µ…É­•ÉÌ€ôl(€€€€€€€€€€€€ˆ´ƒ¶V×².°èˆ°(€€€€€€€€€€€€ˆ´ƒ²vc²
³ªÊÃ²‚Tƒ²b¶Z”èˆ°(€€€€€€€€€€€€ˆ´ƒ¶"³²z@ƒ¶>³²vã¶*àèˆ°(€€€€€€€€€€€€ˆ´ƒ¶VsªÖ·²z”èˆ°(€€€€€€€€€€€€ˆ´ƒ®Âc²b¿®Âc®2 èˆ°(€€€€€€€€€€€€ˆ´ƒ².“¶2 ƒ².ƒ¶bàèˆ°(€€€€€€€€€€€€‹²nC®²àƒ®&Ó²*“®ÎÓªâÀˆ°(€€€€€€€t(€€€€€€€™½Èµ…É­•È¥¸É•ÅÕ¥É•‘}µ…É­•ÉÌè(€€€€€€€€€€€¥˜µ…É­•È¹½Ğ¥¸É•¹‘•É•è(€€€€€€€€€€€€€€€•ÉÉ½ÉÌ¹…ÁÁ•¹¡˜‰íÁÕ‰±¥Í¡•Éô½µÁ…ĞQ•±•É…´ÍÕµµ…Éäµ¥ÍÍ¥¹œíµ…É­•Éôˆ¤(€€€€€€€¥˜€ˆ´ƒ®Ú®–`ƒ®“¶*ã®š·²*èˆ¥¸É•¹‘•É•½È€ˆ´ƒªÒ®‚ ƒ¶VÓ²fàƒ¶.Ã²î¿²¶Fpèˆ¥¸É•¹‘•É•è(€€€€€€€€€€€•ÉÉ½ÉÌ¹…ÁÁ•¹¡˜‰íÁÕ‰±¥Í¡•Éô½µÁ…ĞQ•±•É…´ÍÕµµ…ÉäÉ•É•ÍÍ•Ñ¼Ù•É‰½Í”™½Éµ…Ğˆ¤((€€€•¹•É¥}Ñ¥Ñ±”€ô€‹²šw²“²v ƒ®6S®Rc®6À$ƒ²"c²jS®*Pƒ¶>·²šwŠ›²
ó²Ç²‚ªâÀ°51ƒ²z—ªâÃªÎ²Vôƒ²z®.³²Vˆ(€€€•¹•É¥}‰½‘ä€ô€ (€€€€€€€€‰$ƒ²s®Êƒ¶"³²z@ƒ¶fW®2®†pƒªÎƒ²j§®~$51ƒ²"c²jSªÂ ƒ®æƒ®–ÓªÊ0ƒ®*cªÎ€ƒ²z#®.¸€ˆ(€€€€€€€€‹²
ó²Ç²‚ªâÃ®*Pƒªâ®†s®Ê0ƒªÎƒªÂw²
³²f 51ƒ²z—ªâÃªÎ×ªâ$ƒªÎ²V÷²vƒ¶fW®2¶VcªÎ€ƒ²z#²ró®¦Àƒ²w²
Ã®*—®‚”ƒ²šw²“®>ƒªÊ¶ƒ¶Vs®.¸€ˆ(€€€€€€€€‹®.“®0ƒªÖ³²ÊĞƒªÎ²V÷ªâ#²V‡ªÎğƒªÎƒªÂw²
³®Îƒ®“²Úpƒ²vã².tƒ².s²‚C²v ƒªÎ×ªÂs®Bc² ƒ²V+²Vc®.¸ˆ(€€€€¤(€€€•¹•É¥}‘•Ñ…¥°€ô½µÁ…Ğ¹•áÑÉ…Ñ}…ÉÑ¥±•}‘•Ñ…¥° (€€€€€€€™¥áÑÕÉ”¡•¹•É¥}Ñ¥Ñ±”°•¹•É¥}‰½‘ä¤°(€€€€€€€•¹•É¥}Ñ¥Ñ±”°(€€€€¤(€€€•¹•É¥}É½Ü€ôì(€€€€€€€€‰Í½ÕÉ”ˆè€‹²vÓ¶"³®6Ã²vĞƒ²
Ã²^ˆ°(€€€€€€€€‰±…å•Èˆè€‰ÑÉÕÍÑ•ˆ°(€€€€€€€€‰ÁÕ‰±¥Í¡•Èˆè€‹²vÓ¶"³®6Ã²vĞˆ°(€€€€€€€€‰Ñ¥Ñ±”ˆè•¹•É¥}Ñ¥Ñ±”°(€€€€€€€€‰Í½ÕÉ•}Ñ¥Ñ±”ˆè•¹•É¥}‘•Ñ…¥±l‰Ñ¥Ñ±”‰t°(€€€€€€€€‰Í½ÕÉ•}‰½‘äˆè•¹•É¥}‘•Ñ…¥±l‰‰½‘ä‰t°(€€€€€€€€‰Í½ÕÉ•}…‰ÍÑÉ…Ğˆè•¹•É¥}‘•Ñ…¥±l‰‰½‘ä‰t°(€€€€€€€€‰ÍÕµµ…Éäˆè•¹•É¥}‘•Ñ…¥±l‰‰½‘ä‰t°(€€€€€€€€‰±¥¹¬ˆè€‰¡ÑÑÁÌè¼½İİÜ¹•Ñ½‘…ä¹¼¹­È½¹•İÌ½Ù¥•Ü¼ÈØÀØàÀÀˆ°(€€€€€€€€‰ÁÕ‰±¥Í¡•ˆè¹½Ü°(€€€€€€€€‰‰½‘å}Ù•É¥™¥•ˆèQÉÕ”°(€€€ô(€€€•¹•É¥}…±•ÉĞ€ôÁÉ½‘ÕÑ¥½¸¹½¹ÑÉ…Ğ¹ÍÑÉ¥Ğ¹±…ÍÍ¥™ä¡•¹•É¥}É½Ü°¹½Ü¤(€€€¥˜¹½Ğ•¹•É¥}…±•ÉĞè(€€€€€€€•ÉÉ½ÉÌ¹…ÁÁ•¹ ‰Ù•É¥™¥••¹•É¥Œ-½É•…¸‰ÕÍ¥¹•ÍÌ…ÉÑ¥±”İ…Ì¹½Ğ±…ÍÍ¥™¥•ˆ¤(€€€•±Í”è(€€€€€€€¹½Éµ…±¥é•€ô½µÁ…Ğ¹¹½Éµ…±¥é•}…±•ÉÑ}™½É}½ÕÑÁÕĞ¡•¹•É¥}…±•ÉĞ¤(€€€€€€€¥˜¹½Éµ…±¥é•¹•Ğ ‰­½É•…¹}‰ÕÍ¥¹•ÍÍ}­¥¹ˆ¤€„ô€‰Ù•É¥™¥•‘}Í½ÕÉ•}ÍÕµµ…Éäˆè(€€€€€€€€€€€•ÉÉ½ÉÌ¹…ÁÁ•¹ ‰•¹•É¥Œ-½É•…¸…ÉÑ¥±”‘¥¹½ĞÕÍ”Ù•É¥™¥•Í½ÕÉ”ÍÕµµ…ÉäÁÉ½™¥±”ˆ¤(€€€€€€€¥˜¹½Éµ…±¥é•¹•Ğ ‰¹•İÌˆ¤€„ô•¹•É¥}Ñ¥Ñ±”è(€€€€€€€€€€€•ÉÉ½ÉÌ¹…ÁÁ•¹ ‰•¹•É¥Œ-½É•…¸…ÉÑ¥±”•á…ĞÑ¥Ñ±”İ…Ì½Ù•ÉİÉ¥ÑÑ•¸ˆ¤(€€€€€€€¥˜¹½Ğ½µÁ…Ğ¹Í½ÕÉ•}½ÕÑÁÕÑ}…±¥¹•¡¹½Éµ…±¥é•¤è(€€€€€€€€€€€•ÉÉ½ÉÌ¹…ÁÁ•¹ ‰•¹•É¥Œ-½É•…¸…ÉÑ¥±”Í½ÕÉ”½½ÕÑÁÕĞ…±¥¹µ•¹Ğ™…¥±•ˆ¤(€€€€€€€É•¹‘•É•€ô½µÁ…Ğ¹½µÁ…Ñ}…±•ÉĞ¡¹½Éµ…±¥é•°€Ä°¹½Ü°íô°íô¤(€€€€€€€¥˜•¹•É¥}Ñ¥Ñ±”¹½Ğ¥¸É•¹‘•É•½È€‹²nC®²àƒ®&Ó²*“®ÎÓªâÀˆ¹½Ğ¥¸É•¹‘•É•è(€€€€€€€€€€€•ÉÉ½ÉÌ¹…ÁÁ•¹ ‰•¹•É¥Œ-½É•…¸…ÉÑ¥±”½µÁ…ĞÉ•¹‘•É¥¹œ±½ÍĞÑ¥Ñ±”½ÈÍ½ÕÉ”±¥¹¬ˆ¤(€€€€€€€¥˜€‹ªÎ×².tƒ®²ã²pƒ®bC®*Pƒ².ƒ®ŠÀƒ®ÎÓ®>²^C²pˆ¥¸É•¹‘•É•è(€€€€€€€€€€€•ÉÉ½ÉÌ¹…ÁÁ•¹ ‰•¹•É¥Œ-½É•…¸…ÉÑ¥±”™•±°‰…¬Ñ¼ÍÑ…±”•¹•É¥ŒÁ½±¥ä½Áäˆ¤((€€€‰½‘å}½¹±å}µ…Ñ•É¥…±}É½Ü€ô‘¥Ğ¡•¹•É¥}É½Ü¤(€€€‰½‘å}½¹±å}µ…Ñ•É¥…±}É½Ü¹ÕÁ‘…Ñ” (€€€€€€€ì(€€€€€€€€€€€€‰Ñ¥Ñ±”ˆè€‹¶^“²²*°€ç²nS²^@ƒ¶f7²ö¤ƒªÂ®.ˆ°(€€€€€€€€€€€€‰Í½ÕÉ•}Ñ¥Ñ±”ˆè€‹¶^“²²*°€ç²nS²^@ƒ¶f7²ö¤ƒªÂ®.ˆ°(€€€€€€€€€€€€‰Í½ÕÉ•}‰½‘äˆè€ (€€€€€€€€€€€€€€€€‹®â3®zs®NsªÂ $ƒ²b“®6Pƒ².s²*“¶s²vƒ®>²z¶Z#®.¸ƒ®Îã®²ã²^C®*PƒªÎóªÆÀƒ²"c²ó²f ƒ®“²Úpƒ®ª§¶FsªÂ ƒ²Zãªâ'®BC²®0€ˆ(€€€€€€€€€€€€€€€€‹²‚s®ª§²^C®*Pƒ².“²‚
ßªÎ²V÷
ß²šw²ƒªÂg²v ƒ²#®†s²jĞƒªÂªÊ¤ƒ®Î²"cªÂ ƒ²^®.¸ˆ(€€€€€€€€€€€€¤°(€€€€€€€€€€€€‰Í½ÕÉ•}…‰ÍÑÉ…Ğˆè€ (€€€€€€€€€€€€€€€€‹®â3®zs®NsªÂ $ƒ²b“®6Pƒ².s²*“¶s²vƒ®>²z¶Z#®.¸ƒ®Îã®²ã²^C®*PƒªÎóªÆÀƒ²"c²ó²f ƒ®“²Úpƒ®ª§¶FsªÂ ƒ²Zãªâ'®BC®.¸ˆ(€€€€€€€€€€€€¤°(€€€€€€€€€€€€‰ÍÕµµ…Éäˆè€‹®â3®zs®NsªÂ $ƒ²b“®6Pƒ².s²*“¶s²vƒ®>²z¶Z#®.¸ˆ°(€€€€€€€€€€€€‰±¥¹¬ˆè€‰¡ÑÑÁÌè¼½İİÜ¹•Ñ½‘…ä¹¼¹­È½¹•İÌ½Ù¥•Ü¼ÈØÀØØÈäˆ°(€€€€€€€ô(€€€€¤(€€€¥˜ÁÉ½‘ÕÑ¥½¸¹½¹ÑÉ…Ğ¹ÍÑÉ¥Ğ¹±…ÍÍ¥™ä¡‰½‘å}½¹±å}µ…Ñ•É¥…±}É½Ü°¹½Ü¤è(€€€€€€€•ÉÉ½ÉÌ¹…ÁÁ•¹ ‰-½É•…¸‰½‘äµ½¹±ä‰…­É½Õ¹Ñ•ÉµÌ‰åÁ…ÍÍ•Ñ¡”µ…Ñ•É¥…°¡•…‘±¥¹”…Ñ”ˆ¤((€€€É•…Á}É½Ü€ô‘¥Ğ¡•¹•É¥}É½Ü¤(€€€É•…Á}É½Ü¹ÕÁ‘…Ñ” (€€€€€€€ì(€€€€€€€€€€€€‰Ñ¥Ñ±”ˆè€‰oªâ'®NÇ®v÷²ğƒ²k²ZÓ®ÎÓªâÁtƒ².“²‚²ğƒ²¶VsªÂ
ß²z²²ğƒ¶Vc¶VsªÂ ˆ°(€€€€€€€€€€€€‰Í½ÕÉ•}Ñ¥Ñ±”ˆè€‰oªâ'®NÇ®v÷²ğƒ²k²ZÓ®ÎÓªâÁtƒ².“²‚²ğƒ²¶VsªÂ
ß²z²²ğƒ¶Vc¶VsªÂ ˆ°(€€€€€€€€€€€€‰±¥¹¬ˆè€‰¡ÑÑÁÌè¼½İİÜ¹•Ñ½‘…ä¹¼¹­È½¹•İÌ½Ù¥•Ü¼ÈØÀØÜäĞˆ°(€€€€€€€ô(€€€€¤(€€€¥˜ÁÉ½‘ÕÑ¥½¸¹½¹ÑÉ…Ğ¹ÍÑÉ¥Ğ¹±…ÍÍ¥™ä¡É•…Á}É½Ü°¹½Ü¤è(€€€€€€€•ÉÉ½ÉÌ¹…ÁÁ•¹ ‰Í…µ”µ‘…äÁÉ¥”É•…Àİ…ÌÁÉ½µ½Ñ•…Ì„¹•Ü¡¥ µ¥µÁ…Ğ…ÉÑ¥±”ˆ¤(4(4)¥˜}}¹…µ•}|€ôô€‰}}µ…¥¹}|ˆè4(€€€É…¥Í”MåÍÑ•µá¥Ğ¡µ…¥¸ ¤¤4(