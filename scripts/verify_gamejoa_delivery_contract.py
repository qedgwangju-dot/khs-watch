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
COMPACT_PROSE_PREFIXES = (
    "- í•µì‹¬:",
    "- íˆ¬ìž í¬ì¸íŠ¸:",
)
FORBIDDEN_COMPACT_MARKERS = (
    "- ì˜ì‚¬ê²°ì • ì˜í–¥:",
    "- í•œêµ­ìž¥:",
    "- ë°˜ì˜/ë°˜ëŒ€:",
    "- ì‹¤íŒ¨ ì‹ í˜¸:",
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
]


def compact_prose_errors(body: str, limit: int = 50) -> list[str]:
    errors: list[str] = []
    for line in body.splitlines():
        for prefix in COMPACT_PROSE_PREFIXES:
            if line.startswith(prefix):
                value = line.removeprefix(prefix).strip()
                if len(value) > limit:
                    errors.append(f"{prefix} {len(value)}ìž")
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
]

REQUIRED_RUNTIME_GUARD_SNIPPETS = [
    "runtime report/JSON count mismatch",
    "runtime Telegram status mismatch",
    "GAMEJOA runtime delivery verified",
    "ALLOW_OFF_WINDOW_TELEGRAM",
]

REQUIRED_MAINTENANCE_CONTRACT_SNIPPETS = [
    "ì›ì¸ ê·œëª…",
    "ìž¬ë°œ ë°©ì§€ íšŒê·€ í…ŒìŠ¤íŠ¸",
    "ë°˜ì˜ ì™„ë£Œ",
    "ìž¬ê²€ì¦ ì™„ë£Œ",
    "ì‹¤ì œ ì†¡ì¶œ ìƒíƒœ",
    "skipped_empty",
    "Actions ì„±ê³µë§Œìœ¼ë¡œ ì™„ë£Œ ì²˜ë¦¬í•˜ì§€ ì•ŠëŠ”ë‹¤",
    "ì‹¤ì œ ì‹ ê·œ ì•Œë¦¼ ì†¡ì¶œ ë¯¸ê´€ì°°",
    "ì „ë‚  ìž¥ì „íŒ í•­ëª© ìž¬ì†¡ì¶œ ê¸ˆì§€",
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
    required_query_labels = {"íŠ¸ëŸ¼í”„ ì§ì ‘ë°œì–¸/ì •ì±…", "ì´ëž€/í˜¸ë¥´ë¬´ì¦ˆ ê¸´ê¸‰ìƒí™©", "ë°˜ë„ì²´/AI/HBM", "K-ë°©ì‚°", "êµ­ë‚´ ì •ì±…", "ë°”ì´ì˜¤/FDA"}
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
    assert_51_character_summary_is_compacted_before_send(compact, now, errors)
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
        "source_abstract": ç¯}¶‰žËkºwµçbc²Ús¶×²‚pƒ¶fW®2 ƒªÊ¶€ˆ°(€€€€€€€€ˆ´ƒªâÃ²’ ¿².sªÂèƒ².ƒ®ŠÃ²fã².€ƒ¶fW²
Àƒ
Üƒ²nC²Êpƒ¶fW²vàƒ²’Dƒ
Üƒ²†Ã¶j0€ÈÀèÀÀ-MPˆ°(€€€€€€€€ (€€€€€€€€€€€€ˆ´ƒ¶V×².°èƒ®¾ãªÖ·²vÐƒ²Ê£®. ƒ®Âc®>²ÊÐƒ²z—®æƒ²"c²Ús¶×²‚s®–ðƒ¶fW®2¶VÐƒ¶VsªÖ´ƒªâÃ²^²v`€ˆ(€€€€€€€€€€€€‹²’GªÖ´ƒªÎ×²z”ƒ²šw²“ªÎðƒ²z—®æƒ®Âc²zƒ²vó²‚W²vƒ®.“².pƒ²‚CªÊ¶VcªÊ0ƒ®BC²*×®.#®.¸ˆ(€€€€€€€€¤°(€€€€€€€€ (€€€€€€€€€€€€ˆ´ƒ¶"³²z@ƒ¶>³²vã¶*àèƒ²‚²j¤ƒ²z—®æ²f ƒ².s¶Z'²vó²vÐƒ¶fW²‚W®Bc®¦Ðƒ²’GªÖ´ƒ²w²
Ã®ÊW²vã²v`€ˆ(€€€€€€€€€€€€‹²šw²“®æ²j§ªÎðƒ²z—®æƒ²†Ã®.°ƒ²vó²‚W²vÐƒ®ÂS®Pƒ²"`ƒ²z#²*×®.#®.¸ˆ(€€€€€€€€¤°(€€€€€€€€ˆ´ƒªÊ÷®†p¿²ç¶ÀèƒªÎ×ªâ'®žt°ƒ²‚W²Æƒ¶²z®vó²vàðƒ®Âc®>²ÊÐ½$ˆ°(€€€€€€€€ˆ´ƒ²Ús²Ê`è€ñ„¡É•˜õp‰¡ÑÑÁÌè¼½ÝÝÜ¹É•ÕÑ•ÉÌ¹½´½Ý½É±½•á…µÁ±•pˆùI•ÕÑ•ÉÌð½„øˆ°(€€€€€€€€ˆˆ°(€€€€€€€€‹Â~J„ƒ².“².sªÂƒ®&Ó²*ƒ²öS®¦c¶*àˆ°(€€€€€€€€‹²b“®*`ƒ¶V×².°ƒ®Î¶fS®*Pƒ®ž“²Ús
ß®ž#²ž
ß¶bªâ#¶vC®š
ß².sªÂ¶Fqƒ²z®.#®.¸ˆ°(€€€€€€€€‹¶Vƒ²vã²r èƒ¶fW²vàƒ®Ú#ªÂ ˆ°(€€€€€€€€‹®.“²v0ƒ¶"³²zCªâÃ²®>²^C²pƒ²"c²æc
ß²"cªâ'
ß¶3®ž#²f ƒ²z³¶fW²vàƒ¶V²jP¸ˆ°(€€€€€€€€ˆˆ°(€€€€€€€€‹¶"³²z@ƒ²†Ã²Zã²vÐƒ²V®.0ƒ²ÂãªÎƒ²j¤ƒ®&Ó²*ƒ®â3®š³¶VG²z®.#®.¸ˆ°(€€€t¤€¬€‰q¸ˆ(€€€ÑÉäè(€€€€€€€½µÁ…Ñ•€ô½µÁ…Ð¹Õ…É‘}ÁÉ•½Á•¹}É•Á½ÉÐ¡É•Á½ÉÐ¤(€€€•á•ÁÐIÕ¹Ñ¥µ•ÉÉ½È…Ì•áŒè(€€€€€€€•ÉÉ½ÉÌ¹…ÁÁ•¹¡˜ˆÔÄµ¡…É…Ñ•ÈÍÕµµ…ÉäÝ…Ì‰±½­•¥¹ÍÑ•…½˜½µÁ…Ñ•èí•áôˆ¤(€€€€€€€É•ÑÕÉ¸(€€€™¥•±‘}•ÉÉ½ÉÌ€ô½µÁ…Ñ}ÁÉ½Í•}•ÉÉ½ÉÌ¡½µÁ…Ñ•¤(€€€¥˜™¥•±‘}•ÉÉ½ÉÌè(€€€€€€€•ÉÉ½ÉÌ¹…ÁÁ•¹ (€€€€€€€€€€€€ˆÔÄµ¡…É…Ñ•ÈÍÕµµ…ÉäÉ•µ…¥¹•½Ù•È€ÔÀ¡…ÉÌ…™Ñ•ÈÍ•¹ÁÉ•Á…É…Ñ¥½¸è€ˆ(€€€€€€€€€€€€¬€ˆ°€ˆ¹©½¥¸¡™¥•±‘}•ÉÉ½ÉÌ¤(€€€€€€€€¤(€€€¥˜€‹®¾ãªÖ·²vÐƒ²Ê£®. ƒ®Âc®>²ÊÐƒ²z—®æƒ²"c²Ús¶×²‚s®–ðˆ¹½Ð¥¸½µÁ…Ñ•è(€€€€€€€•ÉÉ½ÉÌ¹…ÁÁ•¹ ‰5)=€ÔÄµ¡…É…Ñ•ÈÍÕµµ…Éä±½ÍÐ¥ÑÌÍ½ÕÉ”µÍÁ•¥™¥ŒÍÕ‰©•Ðˆ¤(€€€™½Èµ…É­•È¥¸=I	%9}=5AQ}5I-ILè(€€€€€€€¥˜µ…É­•È¥¸½µÁ…Ñ•è(€€€€€€€€€€€•ÉÉ½ÉÌ¹…ÁÁ•¹¡˜‰É•µ½Ù•½µÁ…Ð™¥•±É•ÑÕÉ¹•‘ÕÉ¥¹œ€ÔÄµ¡…É…Ñ•ÈÑ•ÍÐèíµ…É­•Éôˆ¤(()‘•˜…ÍÍ•ÉÑ}­½É•…¹}‰ÕÍ¥¹•ÍÍ}…ÉÑ¥±•}½¹ÑÉ…Ð¡ÁÉ½‘ÕÑ¥½¸°½µÁ…Ð°¹½Ü°•ÉÉ½ÉÌè±¥ÍÑmÍÑÉt¤€´ø9½¹”è(€€€¹½¥Íå}ÍÕµµ…Éä€ô½µÁ…Ð¹…ÉÑ¥±•}Í•¹Ñ•¹•Ì (€€€€€€€€ (€€€€€€€€€€€€‹®²Ó®. ƒ²‚²z°ƒ²z³®ÂÃ¶>°ƒªâ#²ž °$ƒ¶Vg²*Ôƒ®Â<ƒ¶fs²j¤ƒªâ#²ž ø€ˆ(€€€€€€€€€€€€‹²nC
ß®.³®~°ƒ¶fc²r£²vÐ€ÄÐÜÃ²nC²vƒ®ÂG®>3®¦Àƒ®F@ƒ®.°ƒ®ž3²v`ƒ²Ös²‚²æc®–ðƒªâÃ®†w¶Z#®.¸€ˆ(€€€€€€€€€€€€‹²fãªÖ·²vàƒ²r¶^c²ƒ¶bãªÂ ƒ¶fW®2®Bc®¦Àƒ²nC¶fSªÂ ƒªÂW²ã®–ðƒ®ÎÓ²b®.¸ˆ(€€€€€€€€¤°(€€€€€€€l‹²nC
ß®.³®~°ˆ°€ˆÄÐÜÃ²n@‰t°(€€€€€€€€È°(€€€€¤(€€€¥˜€‹®²Ó®. ƒ²‚²z°ˆ¥¸¹½¥Íå}ÍÕµµ…Éä½È€‰$ƒ¶Vg²*Ôˆ¥¸¹½¥Íå}ÍÕµµ…Éäè(€€€€€€€•ÉÉ½ÉÌ¹…ÁÁ•¹ ‰-½É•…¸…ÉÑ¥±”ÍÕµµ…ÉäÉ•Ñ…¥¹•ÁÕ‰±¥Í¡•È‰½¥±•ÉÁ±…Ñ”ˆ¤(€€€¥˜¹½Ð¹½¥Íå}ÍÕµµ…Éä¹ÍÑ…ÉÑÍÝ¥Ñ  ‹²nC
ß®.³®~°ƒ¶fc²r ˆ¤è(€€€€€€€•ÉÉ½ÉÌ¹…ÁÁ•¹¡˜‰-½É•…¸…ÉÑ¥±”ÍÕµµ…Éä‘¥¹½ÐÍÑ…ÉÐ™É½´…ÉÑ¥±”™…ÑÌèí¹½¥Íå}ÍÕµµ…Éåôˆ¤((€€€±½¹}ÍÕµµ…Éä€ô½µÁ…Ð¹…ÉÑ¥±•}Í•¹Ñ•¹•Ì (€€€€€€€€ (€€€€€€€€€€€€‰-²šwªÚ3²v`ƒ²b³¶VÐ€Ë®ÚªâÀƒ²^ÃªÊÀƒªâÃ²’ ƒ²b²^²vÓ²v×²v €ØÀÀÛ²Z×²nC²ró®†pƒ²‚®ƒ®>gªâÃ®ÎÓ®.€ˆ(€€€€€€€€€€€€ˆÄÜÔ¸Ô”ƒ®*c²^#®.¸€ˆ(€€€€€€€€€€€€¬€‹²Žó².w².s²z”ƒªÂW²ã²f ƒªÆÃ®zc®2ªâ ƒ²šwªÂªÂ ƒ²r¶®ž“®žƒ²"c²v×²vƒ®3²ZÓ²b³®‚ã®.¸€ˆ€¨€ÄÈ(€€€€€€€€¤°(€€€€€€€l‰-²šwªÚ0ˆ°€‹²b²^²vÓ²vÔˆ°€ˆØÀÀÛ²Z×²n@‰t°(€€€€€€€€Ì°(€€€€¤(€€€¥˜±•¸¡±½¹}ÍÕµµ…Éä¤€ø½µÁ…Ð¹IQ%1}MU55Ie}5a}!ILè(€€€€€€€•ÉÉ½ÉÌ¹…ÁÁ•¹ ‰-½É•…¸…ÉÑ¥±”ÍÕµµ…Éä•á••‘•½µÁ…Ð¡…É…Ñ•È±¥µ¥Ðˆ¤(€€€¥˜¹½Ð±½¹}ÍÕµµ…Éä¹•¹‘ÍÝ¥Ñ   ˆ¸ˆ°€ˆ„ˆ°€ˆüˆ°€‹®.ˆ°€‹Š˜ˆ¤¤è(€€€€€€€•ÉÉ½ÉÌ¹…ÁÁ•¹¡˜‰-½É•…¸…ÉÑ¥±”ÍÕµµ…Éä•¹‘•µ¥µÍ•¹Ñ•¹”èí±½¹}ÍÕµµ…Éål´ÐÀéuôˆ¤((€€€•Ñ½‘…å}Ñ¥Ñ±”€ô€‹²fãªÖ·²và°ƒ²
ó²‚
ÝM/¶Vc®.$€Ð¸×²†Àƒ²
³®N“²^³Š›®Âc®>²ÊÓ®>ƒªÎ£®vðƒ®.Ó²Vc®.ˆ(€€€•Ñ½‘…å}‰½‘ä€ô€ (€€€€€€€€‹²fãªÖ·²vã²v €ÓªÆÃ®zc²vðƒ®>g²V ƒ²
ó²Ç²‚²z@€Ë²†ÀäÌÈß²Z×²nCªÎðM/¶Vc²vÓ®.'²*€ˆ(€€€€€€€€ˆÇ²†ÀÔÐÄÛ²Z×²nC²vƒ²"s®ž“²"c¶Z#®.¸ƒ®F@ƒ²Š®ª¤ƒ¶V§ªÎ®*Pƒ²Vô€Ó²†ÀÔÀÀÃ²Z×²nC²vÓ®.¸€ˆ(€€€€€€€€‹®Âc®¦Ðƒ²vó®Ú ƒ®Âc®>²ÊÐƒ²3²z³
ß®Ú¶J#
ß²z—®æƒ²Š®ª§²v ƒ²"s®ž“®>¶VÐƒ²^²Šƒ®
Ó®Ú ƒ²Â£®Î¶fSªÂ ƒ®
c¶®
³®.¸ˆ(€€€€¤(€€€•Ñ¹•ÝÍ}Ñ¥Ñ±”€ô€‹²^G².s²ö`°ƒ²Â£²ã®2 a0€Ì¸Äƒ¶3²*“¶Àƒ²²j§¶fPƒ²7®>ˆ(€€€•Ñ¹•ÝÍ}‰½‘ä€ô€ (€€€€€€€€‹²^G².s²öc²v ƒ²
ó²Ç²‚²zC²f •¸Øƒ®Â<a0€Ì¸Äƒ¶3²*“¶Àƒ²ZG²
Ã¶>'ªÂ®–ðƒ²ž¶Z'¶VcªÎ€ƒ²z#®.¸€ˆ(€€€€€€€€‹¶>'ªÂ®*Pƒ²vÓ®.°ƒ®ž@ƒ®ž#®²Ó®š³®B€ƒ²b#²‚W²vÓ®¦À°ƒ²ZG²
Ã¶>'ªÂ ƒ¶×ªÎðƒ®Jƒ².“²‚pƒ²z—®æƒ®Âs²ŽóªÂ ƒ®
£²Vƒ²z#®.¸€ˆ(€€€€€€€€‹¶j3²
³®*Pƒ²ž®
s¶VÐƒ®ž“²Úp€ÄÀÄã²Z×²nC²vƒªâÃ®†w¶Z#®.¸ˆ(€€€€¤((€€€‘•˜™¥áÑÕÉ”¡Ñ¥Ñ±”èÍÑÈ°‰½‘äèÍÑÈ¤€´øÍÑÈè(€€€€€€€É•ÑÕÉ¸˜ˆˆˆ(€€€€€€€€ñ¡Ñµ°øñ¡•…ø(€€€€€€€€€€ñµ•Ñ„ÁÉ½Á•ÉÑäô‰½œéÑ¥Ñ±”ˆ½¹Ñ•¹Ðô‰íÑ¥Ñ±•ôˆø(€€€€€€€€€€ñµ•Ñ„ÁÉ½Á•ÉÑäô‰…ÉÑ¥±”éÁÕ‰±¥Í¡•‘}Ñ¥µ”ˆ½¹Ñ•¹ÐôˆÈÀÈØ´ÀÜ´ÈÍPÄÜèÀÀèÀÀ¬ÀäèÀÀˆø(€€€€€€€€ð½¡•…øñ‰½‘äøñ‘¥Ø¥Ñ•µÁÉ½Àô‰…ÉÑ¥±•	½‘äˆø(€€€€€€€€€€ñ ÄùíÑ¥Ñ±•ôð½ ÄøñÀùí‰½‘åôð½Àø(€€€€€€€€€€ñÀûªâÃ²
°ƒ²nC®²ã²v ƒªÒ®‚ ƒªâÃ²^²v`ƒ¶n²4ƒ²"cªâ$°ƒªÎƒªÂtƒ¶>'ªÂ °ƒ®Âs²Žó²f ƒªÎ×².s®–ðƒ¶V£ªî`ƒ¶fW²vã¶VÓ²Vðƒ¶Vs®.“ªÎ€ƒ²“®ª¶Z#®.¸ð½Àø(€€€€€€€€ð½‘¥Øøð½‰½‘äøð½¡Ñµ°ø(€€€€€€€€ˆˆˆ((€€€™½ÈÁÕ‰±¥Í¡•È°Ñ¥Ñ±”°‰½‘ä°±¥¹¬°•áÁ•Ñ•‘}­¥¹°•áÁ•Ñ•‘}¥µÁ…ÑÌ¥¸l(€€€€€€€€ (€€€€€€€€€€€€‹²vÓ¶"³®6Ã²vÐˆ°(€€€€€€€€€€€•Ñ½‘…å}Ñ¥Ñ±”°(€€€€€€€€€€€•Ñ½‘…å}‰½‘ä°(€€€€€€€€€€€€‰¡ÑÑÁÌè¼½ÝÝÜ¹•Ñ½‘…ä¹¼¹­È½¹•ÝÌ½Ù¥•Ü¼ÈØÀØÜàÈˆ°(€€€€€€€€€€€€‰™½É•¥¹}Í•µ¥½¹‘ÕÑ½É}™±½Üˆ°(€€€€€€€€€€€l‹²"cªâ$‰t°(€€€€€€€€¤°(€€€€€€€€ (€€€€€€€€€€€€‹²‚²zC².ƒ®²àˆ°(€€€€€€€€€€€•Ñ¹•ÝÍ}Ñ¥Ñ±”°(€€€€€€€€€€€•Ñ¹•ÝÍ}‰½‘ä°(€€€€€€€€€€€€‰¡ÑÑÁÌè¼½ÝÝÜ¹•Ñ¹•ÝÌ¹½´¼ÈÀÈØÀÜÈÌÀÀÀÌÐÔˆ°(€€€€€€€€€€€€‰•á¥½¹}á±}Ñ•ÍÑ•Èˆ°(€€€€€€€€€€€l‹®> ƒ®Ê®*Pƒ®*—®‚”ˆ°€‹².sªÂ¶Fpˆ°€‹²"cªâ$‰t°(€€€€€€€€¤°(€€€tè(€€€€€€€‘•Ñ…¥°€ô½µÁ…Ð¹•áÑÉ…Ñ}…ÉÑ¥±•}‘•Ñ…¥°¡™¥áÑÕÉ”¡Ñ¥Ñ±”°‰½‘ä¤°Ñ¥Ñ±”¤(€€€€€€€¥˜¹½Ð‘•Ñ…¥°¹•Ð ‰‰½‘å}Ù•É¥™¥•ˆ¤½È¹½Ð‘•Ñ…¥°¹•Ð ‰Ñ¥Ñ±•}…±¥¹•ˆ¤è(€€€€€€€€€€€•ÉÉ½ÉÌ¹…ÁÁ•¹¡˜‰íÁÕ‰±¥Í¡•Éô…ÉÑ¥±”Ñ¥Ñ±”½‰½‘äÙ•É¥™¥…Ñ¥½¸™…¥±•ˆ¤(€€€€€€€€€€€½¹Ñ¥¹Õ”(€€€€€€€É½Ü€ôì(€€€€€€€€€€€€‰Í½ÕÉ”ˆè˜‰íÁÕ‰±¥Í¡•Éôƒ®Âc®>²ÊÐƒ®&Ó²*ˆ°(€€€€€€€€€€€€‰±…å•Èˆè€‰ÑÉÕÍÑ•ˆ°(€€€€€€€€€€€€‰ÁÕ‰±¥Í¡•ÈˆèÁÕ‰±¥Í¡•È°(€€€€€€€€€€€€‰Ñ¥Ñ±”ˆèÑ¥Ñ±”°(€€€€€€€€€€€€‰Í½ÕÉ•}Ñ¥Ñ±”ˆè‘•Ñ…¥±l‰Ñ¥Ñ±”‰t°(€€€€€€€€€€€€‰Í½ÕÉ•}‰½‘äˆè‘•Ñ…¥±l‰‰½‘ä‰t°(€€€€€€€€€€€€‰Í½ÕÉ•}…‰ÍÑÉ…Ðˆè‘•Ñ…¥±l‰‰½‘ä‰t°(€€€€€€€€€€€€‰ÍÕµµ…Éäˆè‘•Ñ…¥±l‰‰½‘ä‰t°(€€€€€€€€€€€€‰±¥¹¬ˆè±¥¹¬°(€€€€€€€€€€€€‰ÁÕ‰±¥Í¡•ˆè¹½Ü°(€€€€€€€€€€€€‰‰½‘å}Ù•É¥™¥•ˆèQÉÕ”°(€€€€€€€ô(€€€€€€€…±•ÉÐ€ôÁÉ½‘ÕÑ¥½¸¹½¹ÑÉ…Ð¹ÍÑÉ¥Ð¹±…ÍÍ¥™ä¡É½Ü°¹½Ü¤(€€€€€€€¥˜¹½Ð…±•ÉÐè(€€€€€€€€€€€•ÉÉ½ÉÌ¹…ÁÁ•¹¡˜‰íÁÕ‰±¥Í¡•ÉôÙ•É¥™¥•…ÉÑ¥±”Ý…Ì¹½Ð±…ÍÍ¥™¥•ˆ¤(€€€€€€€€€€€½¹Ñ¥¹Õ”(€€€€€€€¹½Éµ…±¥é•€ô½µÁ…Ð¹¹½Éµ…±¥é•}…±•ÉÑ}™½É}½ÕÑÁÕÐ¡…±•ÉÐ¤(€€€€€€€¥˜¹½Éµ…±¥é•¹•Ð ‰¹•ÝÌˆ¤€„ôÑ¥Ñ±”è(€€€€€€€€€€€•ÉÉ½ÉÌ¹…ÁÁ•¹ (€€€€€€€€€€€€€€€˜‰íÁÕ‰±¥Í¡•Éô•á…Ð-½É•…¸Í½ÕÉ”Ñ¥Ñ±”Ý…Ì½Ù•ÉÝÉ¥ÑÑ•¸èí¹½Éµ…±¥é•¹•Ð ¹•ÝÌœ¥ôˆ(€€€€€€€€€€€€¤(€€€€€€€¥˜¹½Éµ…±¥é•¹•Ð ‰­½É•…¹}‰ÕÍ¥¹•ÍÍ}­¥¹ˆ¤€„ô•áÁ•Ñ•‘}­¥¹è(€€€€€€€€€€€•ÉÉ½ÉÌ¹…ÁÁ•¹ (€€€€€€€€€€€€€€€˜‰íÁÕ‰±¥Í¡•Éô…ÉÑ¥±”‘¥¹½ÐÍ•±•Ð¥ÑÌÍÁ•¥™¥ŒÁÉ½™¥±”è€ˆ(€€€€€€€€€€€€€€€˜‰í¹½Éµ…±¥é•¹•Ð ­½É•…¹}‰ÕÍ¥¹•ÍÍ}­¥¹œ¥ôˆ(€€€€€€€€€€€€¤(€€€€€€€¥˜¹½Éµ…±¥é•¹•Ð ‰¥µÁ…ÑÌˆ¤€„ô•áÁ•Ñ•‘}¥µÁ…ÑÌè(€€€€€€€€€€€•ÉÉ½ÉÌ¹…ÁÁ•¹ (€€€€€€€€€€€€€€€˜‰íÁÕ‰±¥Í¡•Éô…ÉÑ¥±”¥µÁ…ÑÌÝ•É”½¹Ñ…µ¥¹…Ñ•‰ä…¹½Ñ¡•È½Ù•É±…äè€ˆ(€€€€€€€€€€€€€€€˜‰í¹½Éµ…±¥é•¹•Ð ¥µÁ…ÑÌœ¥ôˆ(€€€€€€€€€€€€¤(€€€€€€€¥˜¹½Éµ…±¥é•¹•Ð ‰Í•Ñ½ÉÌˆ¤€„ôl‹®Âc®>²ÊÐ½$‰tè(€€€€€€€€€€€•ÉÉ½ÉÌ¹…ÁÁ•¹ (€€€€€€€€€€€€€€€˜‰íÁÕ‰±¥Í¡•Éô…ÉÑ¥±”Í•Ñ½ÉÌÝ•É”½¹Ñ…µ¥¹…Ñ•‰ä…¹½Ñ¡•È½Ù•É±…äè€ˆ(€€€€€€€€€€€€€€€˜‰í¹½Éµ…±¥é•¹•Ð Í•Ñ½ÉÌœ¥ôˆ(€€€€€€€€€€€€¤(€€€€€€€¥˜¹½Éµ…±¥é•¹•Ð ‰­}Á½Ý•É}Ý…Ñ ˆ¤è(€€€€€€€€€€€•ÉÉ½ÉÌ¹…ÁÁ•¹¡˜‰íÁÕ‰±¥Í¡•Éô…ÉÑ¥±”¥¹½ÉÉ•Ñ±ä¥¹¡•É¥Ñ•Ñ¡”¹Õ±•…È½Ù•É±…äˆ¤(€€€€€€€¥˜¹½Ð½µÁ…Ð¹Í½ÕÉ•}½ÕÑÁÕÑ}…±¥¹•¡¹½Éµ…±¥é•¤è(€€€€€€€€€€€•ÉÉ½ÉÌ¹…ÁÁ•¹¡˜‰íÁÕ‰±¥Í¡•ÉôÍ½ÕÉ”½½ÕÑÁÕÐ…±¥¹µ•¹Ð™…¥±•ˆ¤(€€€€€€€É•¹‘•É•€ô½µÁ…Ð¹½µÁ…Ñ}…±•ÉÐ¡¹½Éµ…±¥é•°€Ä°¹½Ü°íô°íô¤(€€€€€€€É•ÅÕ¥É•‘}µ…É­•ÉÌ€ôl(€€€€€€€€€€€€ˆ´ƒ¶V×².°èˆ°(€€€€€€€€€€€€ˆ´ƒ¶"³²z@ƒ¶>³²vã¶*àèˆ°(€€€€€€€€€€€€ˆ´ƒªÊ÷®†p¿²ç¶Àèˆ°(€€€€€€€€€€€€‹²nC®²àƒ®&Ó²*“®ÎÓªâÀˆ°(€€€€€€€t(€€€€€€€™½Èµ…É­•È¥¸É•ÅÕ¥É•‘}µ…É­•ÉÌè(€€€€€€€€€€€¥˜µ…É­•È¹½Ð¥¸É•¹‘•É•è(€€€€€€€€€€€€€€€•ÉÉ½ÉÌ¹…ÁÁ•¹¡˜‰íÁÕ‰±¥Í¡•Éô½µÁ…ÐQ•±•É…´ÍÕµµ…Éäµ¥ÍÍ¥¹œíµ…É­•Éôˆ¤(€€€€€€€™¥•±‘}•ÉÉ½ÉÌ€ô½µÁ…Ñ}ÁÉ½Í•}•ÉÉ½ÉÌ¡É•¹‘•É•¤(€€€€€€€¥˜™¥•±‘}•ÉÉ½ÉÌè(€€€€€€€€€€€•ÉÉ½ÉÌ¹…ÁÁ•¹ (€€€€€€€€€€€€€€€˜‰íÁÕ‰±¥Í¡•Éô½µÁ…ÐQ•±•É…´ÁÉ½Í”•á••‘•€ÔÀ¡…ÉÌè€ˆ(€€€€€€€€€€€€€€€€¬€ˆ°€ˆ¹©½¥¸¡™¥•±‘}•ÉÉ½ÉÌ¤(€€€€€€€€€€€€¤(€€€€€€€¥˜€ˆ´ƒ®Ú®–`ƒ®ž“¶*ã®š·²*èˆ¥¸É•¹‘•É•½È€ˆ´ƒªÒ®‚ ƒ¶VÓ²fàƒ¶.Ã²î¿²ž¶Fpèˆ¥¸É•¹‘•É•è(€€€€€€€€€€€•ÉÉ½ÉÌ¹…ÁÁ•¹¡˜‰íÁÕ‰±¥Í¡•Éô½µÁ…ÐQ•±•É…´ÍÕµµ…ÉäÉ•É•ÍÍ•Ñ¼Ù•É‰½Í”™½Éµ…Ðˆ¤(€€€€€€€™½Èµ…É­•È¥¸=I	%9}=5AQ}5I-ILè(€€€€€€€€€€€¥˜µ…É­•È¥¸É•¹‘•É•è(€€€€€€€€€€€€€€€•ÉÉ½ÉÌ¹…ÁÁ•¹¡˜‰íÁÕ‰±¥Í¡•Éô½µÁ…ÐQ•±•É…´ÍÕµµ…ÉäÉ•Ñ…¥¹•íµ…É­•Éôˆ¤(€€€€€€€¥˜€‰,·²nC²‚¿ªÂ²*“¶Ã®æ ˆ¥¸É•¹‘•É•½È€‹²ÊÓ²öPƒ²nC²‚ˆ¥¸É•¹‘•É•è(€€€€€€€€€€€•ÉÉ½ÉÌ¹…ÁÁ•¹¡˜‰íÁÕ‰±¥Í¡•Éô½µÁ…ÐÍÕµµ…Éä½¹Ñ…¥¹Ì…¸Õ¹É•±…Ñ•¹Õ±•…ÈÝ…Ñ ˆ¤((€€€•¹•É¥}Ñ¥Ñ±”€ô€‹²šw²“²v ƒ®6S®Rc®6À$ƒ²"c²jS®*Pƒ¶>·²šwŠ›²
ó²Ç²‚ªâÀ°51ƒ²z—ªâÃªÎ²Vôƒ²z®.³²Vˆ(€€€•¹•É¥}‰½‘ä€ô€ (€€€€€€€€‰$ƒ²s®Êƒ¶"³²z@ƒ¶fW®2®†pƒªÎƒ²j§®~$51ƒ²"c²jSªÂ ƒ®æƒ®–ÓªÊ0ƒ®*cªÎ€ƒ²z#®.¸€ˆ(€€€€€€€€‹²
ó²Ç²‚ªâÃ®*Pƒªâ®†s®Ê0ƒªÎƒªÂw²
³²f 51ƒ²z—ªâÃªÎ×ªâ$ƒªÎ²V÷²vƒ¶fW®2¶VcªÎ€ƒ²z#²ró®¦Àƒ²w²
Ã®*—®‚”ƒ²šw²“®>ƒªÊ¶ƒ¶Vs®.¸€ˆ(€€€€€€€€‹®.“®ž0ƒªÖ³²ÊÐƒªÎ²V÷ªâ#²V‡ªÎðƒªÎƒªÂw²
³®Îƒ®ž“²Úpƒ²vã².tƒ².s²‚C²v ƒªÎ×ªÂs®Bc²ž ƒ²V+²Vc®.¸ˆ(€€€€¤(€€€•¹•É¥}‘•Ñ…¥°€ô½µÁ…Ð¹•áÑÉ…Ñ}…ÉÑ¥±•}‘•Ñ…¥° (€€€€€€€™¥áÑÕÉ”¡•¹•É¥}Ñ¥Ñ±”°•¹•É¥}‰½‘ä¤°(€€€€€€€•¹•É¥}Ñ¥Ñ±”°(€€€€¤(€€€•¹•É¥}É½Ü€ôì(€€€€€€€€‰Í½ÕÉ”ˆè€‹²vÓ¶"³®6Ã²vÐƒ²
Ã²^ˆ°(€€€€€€€€‰±…å•Èˆè€‰ÑÉÕÍÑ•ˆ°(€€€€€€€€‰ÁÕ‰±¥Í¡•Èˆè€‹²vÓ¶"³®6Ã²vÐˆ°(€€€€€€€€‰Ñ¥Ñ±”ˆè•¹•É¥}Ñ¥Ñ±”°(€€€€€€€€‰Í½ÕÉ•}Ñ¥Ñ±”ˆè•¹•É¥}‘•Ñ…¥±l‰Ñ¥Ñ±”‰t°(€€€€€€€€‰Í½ÕÉ•}‰½‘äˆè•¹•É¥}‘•Ñ…¥±l‰‰½‘ä‰t°(€€€€€€€€‰Í½ÕÉ•}…‰ÍÑÉ…Ðˆè•¹•É¥}‘•Ñ…¥±l‰‰½‘ä‰t°(€€€€€€€€‰ÍÕµµ…Éäˆè•¹•É¥}‘•Ñ…¥±l‰‰½‘ä‰t°(€€€€€€€€‰±¥¹¬ˆè€‰¡ÑÑÁÌè¼½ÝÝÜ¹•Ñ½‘…ä¹¼¹­È½¹•ÝÌ½Ù¥•Ü¼ÈØÀØàÀÀˆ°(€€€€€€€€‰ÁÕ‰±¥Í¡•ˆè¹½Ü°(€€€€€€€€‰‰½‘å}Ù•É¥™¥•ˆèQÉÕ”°(€€€ô(€€€•¹•É¥}…±•ÉÐ€ôÁÉ½‘ÕÑ¥½¸¹½¹ÑÉ…Ð¹ÍÑÉ¥Ð¹±…ÍÍ¥™ä¡•¹•É¥}É½Ü°¹½Ü¤(€€€¥˜¹½Ð•¹•É¥}…±•ÉÐè(€€€€€€€•ÉÉ½ÉÌ¹…ÁÁ•¹ ‰Ù•É¥™¥••¹•É¥Œ-½É•…¸‰ÕÍ¥¹•ÍÌ…ÉÑ¥±”Ý…Ì¹½Ð±…ÍÍ¥™¥•ˆ¤(€€€•±Í”è(€€€€€€€¹½Éµ…±¥é•€ô½µÁ…Ð¹¹½Éµ…±¥é•}…±•ÉÑ}™½É}½ÕÑÁÕÐ¡•¹•É¥}…±•ÉÐ¤(€€€€€€€¥˜¹½Éµ…±¥é•¹•Ð ‰­½É•…¹}‰ÕÍ¥¹•ÍÍ}­¥¹ˆ¤€„ô€‰Ù•É¥™¥•‘}Í½ÕÉ•}ÍÕµµ…Éäˆè(€€€€€€€€€€€•ÉÉ½ÉÌ¹…ÁÁ•¹ ‰•¹•É¥Œ-½É•…¸…ÉÑ¥±”‘¥¹½ÐÕÍ”Ù•É¥™¥•Í½ÕÉ”ÍÕµµ…ÉäÁÉ½™¥±”ˆ¤(€€€€€€€¥˜¹½Éµ…±¥é•¹•Ð ‰¹•ÝÌˆ¤€„ô•¹•É¥}Ñ¥Ñ±”è(€€€€€€€€€€€•ÉÉ½ÉÌ¹…ÁÁ•¹ ‰•¹•É¥Œ-½É•…¸…ÉÑ¥±”•á…ÐÑ¥Ñ±”Ý…Ì½Ù•ÉÝÉ¥ÑÑ•¸ˆ¤(€€€€€€€¥˜¹½Ð½µÁ…Ð¹Í½ÕÉ•}½ÕÑÁÕÑ}…±¥¹•¡¹½Éµ…±¥é•¤è(€€€€€€€€€€€•ÉÉ½ÉÌ¹…ÁÁ•¹ ‰•¹•É¥Œ-½É•…¸…ÉÑ¥±”Í½ÕÉ”½½ÕÑÁÕÐ…±¥¹µ•¹Ð™…¥±•ˆ¤(€€€€€€€É•¹‘•É•€ô½µÁ…Ð¹½µÁ…Ñ}…±•ÉÐ¡¹½Éµ…±¥é•°€Ä°¹½Ü°íô°íô¤(€€€€€€€¥˜•¹•É¥}Ñ¥Ñ±”¹½Ð¥¸É•¹‘•É•½È€‹²nC®²àƒ®&Ó²*“®ÎÓªâÀˆ¹½Ð¥¸É•¹‘•É•è(€€€€€€€€€€€•ÉÉ½ÉÌ¹…ÁÁ•¹ ‰•¹•É¥Œ-½É•…¸…ÉÑ¥±”½µÁ…ÐÉ•¹‘•É¥¹œ±½ÍÐÑ¥Ñ±”½ÈÍ½ÕÉ”±¥¹¬ˆ¤(€€€€€€€¥˜€‹ªÎ×².tƒ®²ã²pƒ®bC®*Pƒ².ƒ®ŠÀƒ®ÎÓ®>²^C²pˆ¥¸É•¹‘•É•è(€€€€€€€€€€€•ÉÉ½ÉÌ¹…ÁÁ•¹ ‰•¹•É¥Œ-½É•…¸…ÉÑ¥±”™•±°‰…¬Ñ¼ÍÑ…±”•¹•É¥ŒÁ½±¥ä½Áäˆ¤((€€€‰½‘å}½¹±å}µ…Ñ•É¥…±}É½Ü€ô‘¥Ð¡•¹•É¥}É½Ü¤(€€€‰½‘å}½¹±å}µ…Ñ•É¥…±}É½Ü¹ÕÁ‘…Ñ” (€€€€€€€ì(€€€€€€€€€€€€‰Ñ¥Ñ±”ˆè€‹¶^“²ž²*°€ç²nS²^@ƒ¶f7²ö¤ƒªÂ®.ˆ°(€€€€€€€€€€€€‰Í½ÕÉ•}Ñ¥Ñ±”ˆè€‹¶^“²ž²*°€ç²nS²^@ƒ¶f7²ö¤ƒªÂ®.ˆ°(€€€€€€€€€€€€‰Í½ÕÉ•}‰½‘äˆè€ (€€€€€€€€€€€€€€€€‹®â3®zs®NsªÂ $ƒ²b“®6Pƒ².s²*“¶s²vƒ®>²z¶Z#®.¸ƒ®Îã®²ã²^C®*PƒªÎóªÆÀƒ²"c²Žó²f ƒ®ž“²Úpƒ®ª§¶FsªÂ ƒ²Zãªâ'®BC²ž®ž0€ˆ(€€€€€€€€€€€€€€€€‹²‚s®ª§²^C®*Pƒ².“²‚
ßªÎ²V÷
ß²šw²ƒªÂg²v ƒ²#®†s²jÐƒªÂªÊ¤ƒ®Î²"cªÂ ƒ²^®.¸ˆ(€€€€€€€€€€€€¤°(€€€€€€€€€€€€‰Í½ÕÉ•}…‰ÍÑÉ…Ðˆè€ (€€€€€€€€€€€€€€€€‹®â3®zs®NsªÂ $ƒ²b“®6Pƒ².s²*“¶s²vƒ®>²z¶Z#®.¸ƒ®Îã®²ã²^C®*PƒªÎóªÆÀƒ²"c²Žó²f ƒ®ž“²Úpƒ®ª§¶FsªÂ ƒ²Zãªâ'®BC®.¸ˆ(€€€€€€€€€€€€¤°(€€€€€€€€€€€€‰ÍÕµµ…Éäˆè€‹®â3®zs®NsªÂ $ƒ²b“®6Pƒ².s²*“¶s²vƒ®>²z¶Z#®.¸ˆ°(€€€€€€€€€€€€‰±¥¹¬ˆè€‰¡ÑÑÁÌè¼½ÝÝÜ¹•Ñ½‘…ä¹¼¹­È½¹•ÝÌ½Ù¥•Ü¼ÈØÀØØÈäˆ°(€€€€€€€ô(€€€€¤(€€€¥˜ÁÉ½‘ÕÑ¥½¸¹½¹ÑÉ…Ð¹ÍÑÉ¥Ð¹±…ÍÍ¥™ä¡‰½‘å}½¹±å}µ…Ñ•É¥…±}É½Ü°¹½Ü¤è(€€€€€€€•ÉÉ½ÉÌ¹…ÁÁ•¹ ‰-½É•…¸‰½‘äµ½¹±ä‰…­É½Õ¹Ñ•ÉµÌ‰åÁ…ÍÍ•Ñ¡”µ…Ñ•É¥…°¡•…‘±¥¹”…Ñ”ˆ¤((€€€É•…Á}É½Ü€ô‘¥Ð¡•¹•É¥}É½Ü¤(€€€É•…Á}É½Ü¹ÕÁ‘…Ñ” (€€€€€€€ì(€€€€€€€€€€€€‰Ñ¥Ñ±”ˆè€‰oªâ'®NÇ®v÷²Žðƒ²žk²ZÓ®ÎÓªâÁtƒ².“²‚²Žðƒ²¶VsªÂ
ß²z²²Žðƒ¶Vc¶VsªÂ ˆ°(€€€€€€€€€€€€‰Í½ÕÉ•}Ñ¥Ñ±”ˆè€‰oªâ'®NÇ®v÷²Žðƒ²žk²ZÓ®ÎÓªâÁtƒ².“²‚²Žðƒ²¶VsªÂ
ß²z²²Žðƒ¶Vc¶VsªÂ ˆ°(€€€€€€€€€€€€‰±¥¹¬ˆè€‰¡ÑÑÁÌè¼½ÝÝÜ¹•Ñ½‘…ä¹¼¹­È½¹•ÝÌ½Ù¥•Ü¼ÈØÀØÜäÐˆ°(€€€€€€€ô(€€€€¤(€€€¥˜ÁÉ½‘ÕÑ¥½¸¹½¹ÑÉ…Ð¹ÍÑÉ¥Ð¹±…ÍÍ¥™ä¡É•…Á}É½Ü°¹½Ü¤è(€€€€€€€•ÉÉ½ÉÌ¹…ÁÁ•¹ ‰Í…µ”µ‘…äÁÉ¥”É•…ÀÝ…ÌÁÉ½µ½Ñ•…Ì„¹•Ü¡¥ µ¥µÁ…Ð…ÉÑ¥±”ˆ¤((€€€©‰}Ñ¥Ñ±”€ô€‰)ªâ#²rÔ°€Ë®ÚªâÀƒ²"s²vÔ€ÈÄäÛ²ZÔ€Ÿ²
³²ƒ²Ös®2 ŸŠ˜ÄÀÀÃ²Z×²n@ƒ²zC²
³²Žðƒ²3ªÂˆ(€€€©‰}‰½‘ä€ô€ (€€€€€€€€‰)ªâ#²r×²ž²ŽóªÂ ƒ®æ²v¶Z$ƒªÎ²^Ó²
³²v`ƒ²Ç²z—²^@ƒ¶zc²z²ZÐƒ®ÚªâÀƒªâÃ²’ ƒ²
³²ƒ²Ös®2 ƒ².“²‚²v€ˆ(€€€€€€€€‹®.³²Ç¶VcªÎ€ƒ²‚ªÞç²‚²vàƒ²Žó²Žó¶fc²nC²^@ƒ®
c²ƒ®.¸€ˆ(€€€€€€€€ˆÈÏ²vð)ªâ#²r×²v ƒ²b°€Ë®ÚªâÀƒ²ž®ÂÃ²Žó²Žðƒ®.çªâÃ²"s²vÓ²v×²vÐƒ²‚®ƒ®>gªâÀƒ®2®æ€Ô¸Ü”€ˆ(€€€€€€€€‹²šwªÂ¶Vp€ÈÄäÛ²Z×²nC²vƒªâÃ®†w¶Z#®.“ªÎ€ƒ®Âw¶bS®.¸€ˆ(€€€€€€€€‹²®ÂcªâÀƒ®"²‚ƒ²"s²vÓ²vÔƒ²^·².p€ÌàÔß²Z×²nC²ró®†pƒ²^·®2 ƒ²ÖsªÎƒ²æc®.¸€ˆ(€€€€€€€€‹²vÓ®
€)ªâ#²rÔƒ²vÓ²
³¶j3®*Pƒ²Žó²Žó¶fc²n@ƒ²‚W²Æ²v`ƒ¶Vc®
c®†pƒ®ÎÓ¶×²Žð€Ç²Žó®.äƒ¶bªâ €ÌÄÓ²nC²v`€ˆ(€€€€€€€€‹®ÚªâÀƒ®ÂÃ®.çªÎðƒ¶V£ªî`€ÄÀÀÃ²Z×²n@ƒªÞs®ª£²v`ƒ²zCªâÃ²Žó².tƒ²Þ£®Ntƒ®Â<ƒ²3ªÂ²vƒªÊÃ²‚W¶Z#®.¸ˆ(€€€€¤(€€€©‰}‘•Ñ…¥°€ô½µÁ…Ð¹•áÑÉ…Ñ}…ÉÑ¥±•}‘•Ñ…¥°¡™¥áÑÕÉ”¡©‰}Ñ¥Ñ±”°©‰}‰½‘ä¤°©‰}Ñ¥Ñ±”¤(€€€©‰}É½Ü€ôì(€€€€€€€€‰Í½ÕÉ”ˆè€‹²‚²zC².ƒ®²àƒ²b“®*c²v`ƒ®&Ó²*ˆ°(€€€€€€€€‰±…å•Èˆè€‰ÑÉÕÍÑ•ˆ°(€€€€€€€€‰ÁÕ‰±¥Í¡•Èˆè€‹²‚²zC².ƒ®²àˆ°(€€€€€€€€‰Ñ¥Ñ±”ˆè©‰}Ñ¥Ñ±”°(€€€€€€€€‰Í½ÕÉ•}Ñ¥Ñ±”ˆè©‰}‘•Ñ…¥±l‰Ñ¥Ñ±”‰t°(€€€€€€€€‰Í½ÕÉ•}‰½‘äˆè©‰}‘•Ñ…¥±l‰‰½‘ä‰t°(€€€€€€€€‰Í½ÕÉ•}…‰ÍÑÉ…Ðˆè©‰}‘•Ñ…¥±l‰‰½‘ä‰t°(€€€€€€€€‰ÍÕµµ…Éäˆè©‰}‘•Ñ…¥±l‰‰½‘ä‰t°(€€€€€€€€‰±¥¹¬ˆè€‰¡ÑÑÁÌè¼½ÝÝÜ¹•Ñ¹•ÝÌ¹½´¼ÈÀÈØÀÜÈÌÀÀÀÐÔàˆ°(€€€€€€€€‰ÁÕ‰±¥Í¡•ˆè¹½Ü°(€€€€€€€€‰‰½‘å}Ù•É¥™¥•ˆèQÉÕ”°(€€€ô(€€€©‰}…±•ÉÐ€ôÁÉ½‘ÕÑ¥½¸¹½¹ÑÉ…Ð¹ÍÑÉ¥Ð¹±…ÍÍ¥™ä¡©‰}É½Ü°¹½Ü¤(€€€¥˜¹½Ð©‰}…±•ÉÐè(€€€€€€€•ÉÉ½ÉÌ¹…ÁÁ•¹ ‰)¥¹…¹¥…°Ù•É¥™¥••…É¹¥¹Ì…ÉÑ¥±”Ý…Ì¹½Ð±…ÍÍ¥™¥•ˆ¤(€€€•±Í”è(€€€€€€€É•¹‘•É•€ô½µÁ…Ð¹½µÁ…Ñ}…±•ÉÐ¡©‰}…±•ÉÐ°€Ä°¹½Ü°íô°íô¤(€€€€€€€½É•}±¥¹”€ô¹•áÐ ¡±¥¹”™½È±¥¹”¥¸É•¹‘•É•¹ÍÁ±¥Ñ±¥¹•Ì ¤¥˜±¥¹”¹ÍÑ…ÉÑÍÝ¥Ñ  ˆ´ƒ¶V×².°èˆ¤¤°€ˆˆ¤(€€€€€€€Ù¥•Ý}±¥¹”€ô¹•áÐ (€€€€€€€€€€€€¡±¥¹”™½È±¥¹”¥¸É•¹‘•É•¹ÍÁ±¥Ñ±¥¹•Ì ¤¥˜±¥¹”¹ÍÑ…ÉÑÍÝ¥Ñ  ˆ´ƒ¶"³²z@ƒ¶>³²vã¶*àèˆ¤¤°(€€€€€€€€€€€€ˆˆ°(€€€€€€€€¤(€€€€€€€¥˜¹½Ð…±°¡Ñ•É´¥¸½É•}±¥¹”™½ÈÑ•É´¥¸€ ˆÈÄäÛ²Z×²n@ˆ°€ˆÔ¸Ü”ˆ°€‹²^·®2 ƒ²Ös®2 ˆ¤¤è(€€€€€€€€€€€•ÉÉ½ÉÌ¹…ÁÁ•¹¡˜‰)¥¹…¹¥…°½É”½µ¥ÑÑ•…ÉÑ¥±”™…ÑÌèí½É•}±¥¹•ôˆ¤(€€€€€€€¥˜¹½Ð…±°¡Ñ•É´¥¸Ù¥•Ý}±¥¹”™½ÈÑ•É´¥¸€ ˆÌÄÓ²n@ˆ°€ˆÄÀÀÃ²Z×²n@ˆ°€‹²zC²
³²Žðˆ¤¤è(€€€€€€€€€€€•ÉÉ½ÉÌ¹…ÁÁ•¹¡˜‰)¥¹…¹¥…°¥¹Ù•ÍÑµ•¹ÐÁ½¥¹Ð½µ¥ÑÑ•Í¡…É•¡½±‘•ÈÉ•ÑÕÉ¸èíÙ¥•Ý}±¥¹•ôˆ¤(€€€€€€€¥˜€‹ªâ#²rÔ¿²zC®Îã².s²z”ˆ¹½Ð¥¸É•¹‘•É•è(€€€€€€€€€€€•ÉÉ½ÉÌ¹…ÁÁ•¹ ‰)¥¹…¹¥…°…ÉÑ¥±”±½ÍÐ¥ÑÌ™¥¹…¹”Í•Ñ½È±…ÍÍ¥™¥…Ñ¥½¸ˆ¤(€€€€€€€¥˜©‰}Ñ¥Ñ±”¥¸½É•}±¥¹”½È©‰}Ñ¥Ñ±”¥¸Ù¥•Ý}±¥¹”è(€€€€€€€€€€€•ÉÉ½ÉÌ¹…ÁÁ•¹ ‰)¥¹…¹¥…°ÍÕµµ…ÉäÉ•Á•…Ñ•Ñ¡”¡•…‘±¥¹”¥¹ÍÑ•…½˜…ÉÑ¥±”™…ÑÌˆ¤(€€€€€€€™½Èµ…É­•È¥¸=I	%9}=5AQ}5I-ILè(€€€€€€€€€€€¥˜µ…É­•È¥¸É•¹‘•É•è(€€€€€€€€€€€€€€€•ÉÉ½ÉÌ¹…ÁÁ•¹¡˜‰)¥¹…¹¥…°½µÁ…ÐQ•±•É…´ÍÕµµ…ÉäÉ•Ñ…¥¹•íµ…É­•Éôˆ¤(€€€€€€€™¥•±‘}•ÉÉ½ÉÌ€ô½µÁ…Ñ}ÁÉ½Í•}•ÉÉ½ÉÌ¡É•¹‘•É•¤(€€€€€€€¥˜™¥•±‘}•ÉÉ½ÉÌè(€€€€€€€€€€€•ÉÉ½ÉÌ¹…ÁÁ•¹ (€€€€€€€€€€€€€€€€‰)¥¹…¹¥…°½µÁ…Ð™…ÑÌ•á••‘•€ÔÀ¡…ÉÌè€ˆ€¬€ˆ°€ˆ¹©½¥¸¡™¥•±‘}•ÉÉ½ÉÌ¤(€€€€€€€€€€€€¤(4(4)¥˜}}¹…µ•}|€ôô€‰}}µ…¥¹}|ˆè4(€€€É…¥Í”MåÍÑ•µá¥Ð¡µ…¥¸ ¤¤4