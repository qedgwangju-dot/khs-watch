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
    "- í•µì‹¬:",
)
COMPACT_PROSE_LIMITS = {
    "- í•µì‹¬:": 100,
}
FORBIDDEN_COMPACT_MARKERS = (
    "- ê¸°ì¤€/ì‹œê°:",
    "- ê²½ë¡œ/ì„¹í„°:",
    "- íˆ¬ì í¬ì¸íŠ¸:",
    "- ì˜ì‚¬ê²°ì • ì˜í–¥:",
    "- í•œêµ­ì¥:",
    "- ë°˜ì˜/ë°˜ëŒ€:",
    "- ì‹¤íŒ¨ ì‹ í˜¸:",
    "íˆ¬ì ì¡°ì–¸ì´ ì•„ë‹Œ ì°¸ê³ ìš© ë‰´ìŠ¤ ë¸Œë¦¬í•‘ì…ë‹ˆë‹¤.",
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
    'GAMEJOA_KOREAN_BUSINESS_DETAIL_LIMIT: "96"',
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
    "coverage.apply_source_extensions",
    "coverage.apply_term_extensions",
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
    "GAMEJOA_CORE_MAX_CHARS = 100",
    "semantic_event_theme",
    "collect_fx_snapshot",
    "build_alert_fx_conversion",
    "foreign_currency_not_converted",
    "ğŸ“° ì‹¤ì‹œê°„ í•µì‹¬ ë‰´ìŠ¤ ë ˆì´ë” Â·",
]


def compact_prose_errors(body: str) -> list[str]:
    errors: list[str] = []
    for line in body.splitlines():
        for prefix in COMPACT_PROSE_PREFIXES:
            if line.startswith(prefix):
                value = line.removeprefix(prefix).strip()
                limit = COMPACT_PROSE_LIMITS[prefix]
                if len(value) > limit:
                    errors.append(f"{prefix} {len(value)}ì")
                if "â€¦" in value or "..." in value:
                    errors.append(f"{prefix} ë§ì¤„ì„")
                if re.search(r"\[[^\]]{0,60}\s*ê¸°ì\]", value):
                    errors.append(f"{prefix} ë§¤ì²´Â·ê¸°ì í‘œê¸°")
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
    "ğŸ“° ì‹¤ì‹œê°„ í•µì‹¬ ë‰´ìŠ¤ ë ˆì´ë” Â·",
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
    if "ğŸ“° GAMEJOA ì‹¤ì‹œê°„ í•µì‹¬ ë‰´ìŠ¤ ë ˆì´ë” Â·" in runner:
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
        if "ğŸ“° GAMEJOA ì‹¤ì‹œê°„ í•µì‹¬ ë‰´ìŠ¤ ë ˆì´ë” Â·" in generated_guard:
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
    required_query_labels = {"íŠ¸ëŸ¼í”„ ì§ì ‘ë°œì–¸/ì •ì±…", "ì´ë€/í˜¸ë¥´ë¬´ì¦ˆ ê¸´ê¸‰ìƒí™©", "ë°˜ë„ì²´/AI/HBM", "K-ë°©ì‚°", "êµ­ë‚´ ì •ì±…", "ë°”ì´ì˜¤/FDA"}
    query_labels = {name for name, _query in query_plan}
    required_query_labels.add("ì¤‘êµ­ ìƒë¬´ë¶€ ìˆ˜ì¶œí†µì œ/ê´€ì„¸")
    missing_query_labels = sorted(required_query_labels - query_labels)
    if missing_query_labels:
        errors.append(f"trusted query plan missing coverage: {', '.join(missing_query_labels)}")
    korean_source_labels = {name for name, _url, _kind in production.base.SOURCES}
    required_korean_source_labels = {
        "êµ­ë‚´ ì‹ ë¢°ë§¤ì²´ AIÂ·ë°˜ë„ì²´ í˜‘ë ¥",
        "êµ­ë‚´ ì‹ ë¢°ë§¤ì²´ ë¯¸êµ­ ì¦ì‹œÂ·ë°˜ë„ì²´",
        "êµ­ë‚´ ì‹ ë¢°ë§¤ì²´ ìë³¸ì‹œì¥ ì •ì±…",
        "êµ­ë‚´ ì‹ ë¢°ë§¤ì²´ ì‚°ì—…ìˆ˜ìš”Â·CAPEX",
        "ì´ë°ì¼ë¦¬ ê¸°ì—…Â·AI",
        "ì´ë°ì¼ë¦¬ ë¯¸êµ­ ì¦ì‹œ",
        "ë§¤ì¼ê²½ì œ ìë³¸ì‹œì¥",
        "ë¨¸ë‹ˆíˆ¬ë°ì´ ê¸€ë¡œë²Œì‹œì¥",
        "í—¤ëŸ´ë“œê²½ì œ ì‚°ì—…ìˆ˜ìš”",
        "í˜„ëŒ€ì°¨Â·ì—”ë¹„ë””ì•„ AI í˜‘ë ¥",
        "AI ì¸í”„ë¼ ì² ê°• ìˆ˜ìš”",
    }
    missing_korean_sources = sorted(required_korean_source_labels - korean_source_labels)
    if missing_korean_sources:
        errors.append(
            "Korean trusted-media source coverage missing: "
            + ", ".join(missing_korean_sources)
        )
    for domain in ("edaily.co.kr", "mk.co.kr", "mt.co.kr", "biz.heraldcorp.com"):
        probe = {
            "source": "êµ­ë‚´ ì‹ ë¢°ë§¤ì²´ íšŒê·€ì ê²€",
            "publisher": "",
            "link": f"https://{domain}/regression-fixture",
        }
        if not production.runner.is_korean_business_row(probe):
            errors.append(f"Korean trusted domain was not routed to article verification: {domain}")

    target = "https://www.reuters.com/world/example"
    bing_link = "https://www.bing.com/news/apiclick.aspx?" + urllib.parse.urlencode({"url": target})
    bing_fixture = f'''<rss xmlns:news="https://www.bing.com/news/search?q=x&amp;format=rss"><channel><item>
 ÛnvîÚ$z{-®éÜj×’&6¶w&÷VæBFW&×2'—76VBF†RÖFW&–Â†VFÆ–æRvFR" ¢W'6öåöæÖUöfÇ6U÷÷6—F—fU÷&÷rÒF–7B†vVæW&–5÷&÷r¢W'6öåöæÖUöfÇ6U÷÷6—F—fU÷&÷rçWFFR€¢°¢'F—FÆR#¢.Ù˜ŞÈ‰Ê;ÂÂ~¸ù«hr»˜N«{ÊÈIÎÈ*ÂÉ˜NÈK"À¢'6÷W&6U÷F—FÆR#¢.Ù˜ŞÈ‰Ê;ÂÂ~¸ù«hr»˜N«{ÊÈIÎÈ*ÂÉ˜NÈK"À¢'6÷W&6Uö&öG’#¢€¢.»É«Ù˜ŞÈ‰Ê;Î«¹9Î¹ÛÎºx‚¸ù«hÉyÈIÂ»˜N«{ÊÈIÎÈ*Îº[ÂÉ{«‹Ùh¸ºBâ ¢.«‹È*ÎÉy¸©B«‹ÉxR«8NÉ[ÒÂºzNËiÂÂÈºNÊ¹‰¸©BØŠÎÉéÉÛÎÊ	^ÉÛBÉxn¸ºBâ ¢’À¢'6÷W&6Uö'7G&7B#¢.»É«Ù˜ŞÈ‰Ê;Î«¹9Î¹ÛÎºx‚¸ù«hÉyÈIÂ»˜N«{ÊÈIÎÈ*Îº[ÂÉ{«‹Ùh¸ºBâ"À¢'7VÖÖ'’#¢.»É«Ù˜ŞÈ‰Ê;Î«¹9Î¹ÛÎºx‚¸ù«hÉyÈIÂ»˜N«{ÊÈIÎÈ*Îº[ÂÉ{«‹Ùh¸ºBâ"À¢&Æ–æ²#¢&‡GG3¢ò÷wwræWFæWw2æ6öÒó##cs#CC"À¢Ğ¢¢–b&öGV7F–öâæ6öçG&7Bç7G&–7Bæ6Æ76–g’‡W'6öåöæÖUöfÇ6U÷÷6—F—fU÷&÷rÂæ÷r“ ¢W'&÷'2æVæB‚'W'6öæÂæÖR6öçF–æ–ærÈ‰Ê;Â'—76VBF†RÖFW&–Â†VFÆ–æRvFR" ¢f÷"ÖFW&–Å÷F—FÆR–â€¢.ÙˆN¸ÈºÎØYÂÂØûN¹è¹9Â³"ÊNË
‚.Ë
‚È‰Ê;Â"À¢.ÙYÎÙ™NÉyÉkNºÂÂ¸ÈÙ‰^È‰Ê;Â«;^È¹Â"À¢.ÊÈJÈ*ÂÂ>ÊÉ¹¸ÈÈ‰Ê;ÂÈK«;R"À¢$Ä”~¸J^ÈªNÉ¹ÂÈ‰Ê;ÎÉéN«:ÉzŞ¸ÈËYÎ¸È"À¢“ ¢–bæ÷B&öGV7F–öâç'VææW"æ¶÷&Våö'W6–æW75÷F—FÆUö†5öÖFW&–Å÷FW&Ò€¢ÖFW&–Å÷F—FÆRÀ¢.È‰Ê;Â"À¢“ ¢W'&÷'2æVæB†b'fÆ–B6öçG&7B†VFÆ–æRv2&Æö6¶VB'’È‰Ê;Â6öçFW‡BwV&C¢¶ÖFW&–Å÷F—FÆWÒ" ¢&V6÷&÷rÒF–7B†vVæW&–5÷&÷r¢&V6÷&÷rçWFFR€¢°¢'F—FÆR#¢%¾«ˆ¹;¹ÛŞÊ;ÂÊy®ÉkN»;N«‹ÒÈºNÊÊ;ÂÈ8ÙYÎ«+~ÉèNÈ8Ê;ÂÙYÙYÎ«"À¢'6÷W&6U÷F—FÆR#¢%¾«ˆ¹;¹ÛŞÊ;ÂÊy®ÉkN»;N«‹ÒÈºNÊÊ;ÂÈ8ÙYÎ«+~ÉèNÈ8Ê;ÂÙYÙYÎ«"À¢&Æ–æ²#¢&‡GG3¢ò÷wwræWFöF’æ6òæ·"öæWw2÷f–Wró#ccs“B"À¢Ğ¢¢–b&öGV7F–öâæ6öçG&7Bç7G&–7Bæ6Æ76–g’‡&V6÷&÷rÂæ÷r“ ¢W'&÷'2æVæB‚'6ÖRÖF’&–6R&V6v2&öÖ÷FVB2æWr†–v‚Ö–×7B'F–6ÆR" ¢¦%÷F—FÆRÒ$¤.«ˆÉËRÂ.»hN«‹È‰ÎÉÛR#“nÉkR~È*ÎÈ8ËYÎ¸È~(
cÉk^É¹ÉéÈ*ÎÊ;ÂÈhÎ« ¢¦%ö&öG’Ò€¢$¤.«ˆÉË^ÊxÊ;Î«»˜NÉØÙh’«8NÉ{NÈ*ÎÉÙ‚ÈKÉê^ÉyÙéÉè^ÉkB»hN«‹«‹ÊHÈ*ÎÈ8ËYÎ¸ÈÈºNÊÉØB ¢.¸ºÎÈKÙY«:Ê«{ÊÉÛ‚Ê;ÎÊ;ÎÙ™É¹Éy¸)ÈJ¸ºBâ ¢##>ÉÛÂ¤.«ˆÉË^ÉØÉŠÂ.»hN«‹Êx»Ê;ÎÊ;Â¸»«‹È‰ÎÉÛNÉÛ^ÉÛBÊN¸XB¸ù«‹¸È»˜BRãrR ¢.ÊiŞ«ÙYÂ#“nÉk^É¹ÉØB«‹ºŞÙh¸ºN«:»	ŞÙ‰N¸ºBâ ¢.È8»	«‹¸ˆNÊÈ‰ÎÉÛNÉÛRÉzŞÈ¹Â3ƒS~Ék^É¹ÉËÎºÂÉzŞ¸ÈËYÎ«:Ë™¸ºBâ ¢.ÉÛN¸*¤.«ˆÉËRÉÛNÈ*ÎÙ¨Î¸©BÊ;ÎÊ;ÎÙ™É¹Ê	^Ë^ÉÙ‚ÙY¸)ºÂ»;NØk^Ê;ÂÊ;Î¸»’ÙˆN«ˆ‚3NÉ¹ÉÙ‚ ¢.»hN«‹»¸»«;ÂÙZ«¹‚Ék^É¹«yÎºªÉÙ‚Éé«‹Ê;ÎÈ¹ÒËz¹9Ò»òÈhÎ«ÉØB«+Ê	^Ùh¸ºBâ ¢¢¦%öFWF–ÂÒ6ö×7BæW‡G&7Eö'F–6ÆUöFWF–Â†f—‡GW&R†¦%÷F—FÆRÂ¦%ö&öG’’Â¦%÷F—FÆR¢¦%÷&÷rÒ°¢'6÷W&6R#¢.ÊNÉéÈººË‚ÉŠN¸©ÉÙ‚¸›NÈªB"À¢&Æ–W"#¢'G'W7FVB"À¢'V&Æ—6†W"#¢.ÊNÉéÈººË‚"À¢'F—FÆR#¢¦%÷F—FÆRÀ¢'6÷W&6U÷F—FÆR#¢¦%öFWF–Å²'F—FÆR%ÒÀ¢'6÷W&6Uö&öG’#¢¦%öFWF–Å²&&öG’%ÒÀ¢'6÷W&6Uö'7G&7B#¢¦%öFWF–Å²&&öG’%ÒÀ¢'7VÖÖ'’#¢¦%öFWF–Å²&&öG’%ÒÀ¢&Æ–æ²#¢&‡GG3¢ò÷wwræWFæWw2æ6öÒó##cs#3CS‚"À¢'V&Æ—6†VB#¢æ÷rÀ¢&&öG•÷fW&–f–VB#¢G'VRÀ¢Ğ¢¦%öÆW'BÒ&öGV7F–öâæ6öçG&7Bç7G&–7Bæ6Æ76–g’†¦%÷&÷rÂæ÷r¢–bæ÷B¦%öÆW'C ¢W'&÷'2æVæB‚$¤"f–ææ6–ÂfW&–f–VBV&æ–æw2'F–6ÆRv2æ÷B6Æ76–f–VB"¢VÇ6S ¢æ÷&ÖÆ—¦VEö¦"Ò6ö×7Bææ÷&ÖÆ—¦UöÆW'Eöf÷%ö÷WGWB†¦%öÆW'B¢&VæFW&VBÒ6ö×7Bæ6ö×7EöÆW'B†æ÷&ÖÆ—¦VEö¦"ÂÂæ÷rÂ·ÒÂ·Ò¢6÷&UöÆ–æRÒæW‡B‚†Æ–æRf÷"Æ–æR–â&VæFW&VBç7Æ—FÆ–æW2‚’–bÆ–æRç7F'G7v—F‚‚"ÒÙ[^ÈºÃ¢"’’Â""¢f–WuöÆ–æRÒæW‡B€¢†Æ–æRf÷"Æ–æR–â&VæFW&VBç7Æ—FÆ–æW2‚’–bÆ–æRç7F'G7v—F‚‚"ÒØŠÎÉéØúÎÉÛØ«ƒ¢"’’À¢""À¢¢–bæ÷BÆÂ€¢FW&Ò–â6÷&UöÆ–æP¢f÷"FW&Ò–â‚##“nÉk^É¹"Â#RãrR"Â.ÉzŞ¸ÈËYÎ¸È"Â#3NÉ¹"Â#Ék^É¹"Â.ÉéÈ*ÎÊ;Â"¢“ ¢W'&÷'2æVæB†b$¤"f–ææ6–Â6÷&RöÖ—GFVB'F–6ÆRf7G3¢¶6÷&UöÆ–æWÒ"¢–bæ÷BÆÂ‡FW&Ò–âf–WuöÆ–æRf÷"FW&Ò–â‚.ÉÛNÉÛRËiNÊ	R"Â.Ê;ÎÊ;ÎÙ™É¹"’“ ¢W'&÷'2æVæB†b$¤"f–ææ6–Â–çfW7FÖVçBö–çBöÖ—GFVBÖ&¶WBÖVæ–æs¢·f–WuöÆ–æWÒ"¢–b.«ˆÉËRşÉé»;È¹ÎÉêR"æ÷B–âæ÷&ÖÆ—¦VEö¦"ævWB‚'6V7F÷'2"ÂµÒ“ ¢W'&÷'2æVæB‚$¤"f–ææ6–Â'F–6ÆRÆ÷7B—G2f–ææ6R6V7F÷"6Æ76–f–6F–öâ"¢–b¦%÷F—FÆR–â6÷&UöÆ–æR÷"¦%÷F—FÆR–âf–WuöÆ–æS ¢W'&÷'2æVæB‚$¤"f–ææ6–Â7VÖÖ'’&WVFVBF†R†VFÆ–æR–ç7FVBöb'F–6ÆRf7G2"¢f÷"Ö&¶W"–âdõ$$”DDTåô4ôÕ5EôÔ$´U%3 ¢–bÖ&¶W"–â&VæFW&VC ¢W'&÷'2æVæB†b$¤"f–ææ6–Â6ö×7BFVÆVw&Ò7VÖÖ'’&WF–æVB¶Ö&¶W'Ò"¢f–VÆEöW'&÷'2Ò6ö×7E÷&÷6UöW'&÷'2‡&VæFW&VB¢–bf–VÆEöW'&÷'3 ¢W'&÷'2æVæB€¢$¤"f–ææ6–Â6ö×7Bf7G2W†6VVFVBf–VÆBÆ–Ö—G3¢"²"Â"æ¦ö–â†f–VÆEöW'&÷'2¢ ¢FWF–ÆVEö'F–6ÆUö66W2Ò°¢€¢%´UNØ«Êy^Ê;ÅŞÉÊÙYÎÉiÙh’ÂC#S>Ék^É¹«yÎºª‚ÉéÈ*ÎÊ;ÂÈhÎ«ÉyÈ8È«ÈK‚"À¢€¢.ÉÊÙYÎÉiÙhÉÛBC#S>Ék^É¹«yÎºªÉÙ‚ÉéÈ*ÎÊ;ÂÈhÎ««+Ê	^ÉyÈ8È«ÈK¸ºBâ ¢.«ˆÉË^«	¸ø^É¹ÊNÉé«;^È¹ÎÈ¹ÎÈªNØYÎÉy¹Kº[Nº›BÉÊÙYÎÉiÙhÉØÊN¸*ÉÛNÈ*ÎÙ¨Îº[ÂÉ{N«: ¢#C#S>ÉkS3scºxÃCÉ¹«yÎºªÉÙ‚ÉéÈ*ÎÊ;Îº[ÂÈhÎ«ÙY«‹ºÂ«+Ê	^Ùh¸ºN«:«;^È¹ÎÙh¸ºBâ ¢.ÈhÎ«ÉˆÊ	^ÉÛÎÉØÉŠN¸©B3ÉÛÎÉÛNº›ÂÈhÎ«¸ÈÈ8ÉØ»;NØk^Ê;ÎÉ˜Ê(^ºYÊ;Îº[ÂØúÎÙZÙYÂ ¢.ËIÒcnºxÃCC#Ê;Î¸ºBâ ¢’À¢‚#C#S>ÉkS3scºxÃCÉ¹"Â.ÈhÎ«"Â#cnºxÃCC#Ê;Â"Â#3ÉÛÂ"’À¢‚.ºzNÉè\+~ÈhÎ«"Â’À¢‚.»	ÎÙhÊ;ÎÈ¹Ò"Â.Ê;Î¸»«Ë™‚"’À¢’À¢€¢%´UNØ«Êy^Ê;ÅŞÙˆN¸ÈË
‚Â.»hN«‹ÈºNÊ»hÊxNÉyÙY¹ÛŞÈK‚"À¢€¢.ÙˆN¸ÈË
¸©BÊN¸*.»hN«‹É{«+«‹ÊHÉˆÉx^ÉÛNÉÛ^ÉÛB.ÊƒSÉk^É¹ÉËÎºÂÊx¸)ÎÙ[B ¢.«	ÉØ«‹«N»;N¸ºB#ã‚R«	ÈhÎÙh¸ºN«:»	ŞÙ‰N¸ºBâºzNËiÎÉØCÊ#S>Ék^É¹ÉËÎºÂ ¢#ã’RÊiŞ«ÙhÊxºxÂÂÉˆÉx^ÉÛNÉÛ^ºZÉØRã‚^ºÂÉ{«B«ÉÛN¸ÙÈªBƒbã7ãrã2Rº[Â ¢.»	¸øÎÉY¸ºBâ¸øNºzNØÉºzN¸©B“ºxÃ#¸ÈºÂÊN¸XB¸ù«‹¸È»˜Bbã’R«	ÈhÎÙh¸ºBâ ¢’À¢‚#.ÊƒSÉk^É¹"Â##ã‚R«	ÈhÂ"Â#CÊ#S>Ék^É¹"Â#Rã‚R"Â#bã7ãrã2R"’À¢‚.ÉˆÉx^ÉÛNÉÛRƒSÉk^É¹"Â’À¢‚.ÉÛNÉÛRËiNÊ	R"Â.«ÉÛN¸ÙÈªB"’À¢’À¢Ğ¢f÷"66Uö–æFW‚Â€¢F—FÆRÀ¢&öG’À¢&WV—&VEöf7G2À¢f÷&&–FFVåöf7G2À¢&WV—&VE÷f–Wuöf7G2À¢’–âVçVÖW&FR€¢FWF–ÆVEö'F–6ÆUö66W2À¢À¢“ ¢FWF–ÂÒ6ö×7BæW‡G&7Eö'F–6ÆUöFWF–Â†f—‡GW&R‡F—FÆRÂ&öG’’ÂF—FÆR¢&÷rÒ°¢'6÷W&6R#¢.ÊNÉéÈººË‚ÉŠN¸©ÉÙ‚¸›NÈªB"À¢&Æ–W"#¢'G'W7FVB"À¢'V&Æ—6†W"#¢.ÊNÉéÈººË‚"À¢'F—FÆR#¢F—FÆRÀ¢'6÷W&6U÷F—FÆR#¢FWF–Å²'F—FÆR%ÒÀ¢'6÷W&6Uö&öG’#¢FWF–Å²&&öG’%ÒÀ¢'6÷W&6Uö'7G&7B#¢FWF–Å²&&öG’%ÒÀ¢'7VÖÖ'’#¢FWF–Å²&&öG’%ÒÀ¢&Æ–æ²#¢b&‡GG3¢ò÷wwræWFæWw2æ6öÒó##cs#Cg¶66Uö–æFW‚²'Ò"À¢'V&Æ—6†VB#¢æ÷rÀ¢&&öG•÷fW&–f–VB#¢G'VRÀ¢Ğ¢ÆW'BÒ&öGV7F–öâæ6öçG&7Bç7G&–7Bæ6Æ76–g’‡&÷rÂæ÷r¢–bæ÷BÆW'C ¢W'&÷'2æVæB†b&FWF–ÆVB¶÷&Vâ'F–6ÆR66Rv2æ÷B6Æ76–f–VC¢·F—FÆWÒ"¢6öçF–çVP¢&VæFW&VBÒ6ö×7Bæ6ö×7EöÆW'B€¢6ö×7Bææ÷&ÖÆ—¦UöÆW'Eöf÷%ö÷WGWB†ÆW'B’À¢À¢æ÷rÀ¢·ÒÀ¢·ÒÀ¢¢6÷&UöÆ–æRÒæW‡B€¢†Æ–æRf÷"Æ–æR–â&VæFW&VBç7Æ—FÆ–æW2‚’–bÆ–æRç7F'G7v—F‚‚"ÒÙ[^ÈºÃ¢"’’À¢""À¢¢f–WuöÆ–æRÒæW‡B€¢†Æ–æRf÷"Æ–æR–â&VæFW&VBç7Æ—FÆ–æW2‚’–bÆ–æRç7F'G7v—F‚‚"ÒØŠÎÉéØúÎÉÛØ«ƒ¢"’’À¢""À¢¢–bæ÷BÆÂ†f7B–â6÷&UöÆ–æRf÷"f7B–â&WV—&VEöf7G2“ ¢W'&÷'2æVæB†b&FWF–ÆVB¶÷&Vâ'F–6ÆR6÷&RöÖ—GFVBf7G3¢¶6÷&UöÆ–æWÒ"¢–bç’†f7B–â6÷&UöÆ–æRf÷"f7B–âf÷&&–FFVåöf7G2“ ¢W'&÷'2æVæB†b&FWF–ÆVB¶÷&Vâ'F–6ÆR6÷&R–çfVçFVB÷"6Æ—VBf7C¢¶6÷&UöÆ–æWÒ"¢–bæ÷BÆÂ†f7B–âf–WuöÆ–æRf÷"f7B–â&WV—&VE÷f–Wuöf7G2“ ¢W'&÷'2æVæB†b&FWF–ÆVB¶÷&Vâ'F–6ÆR–çfW7FÖVçBö–çBöÖ—GFVBÖVæ–æs¢·f–WuöÆ–æWÒ" ¢6–FV6%ö6÷&RÒ6ö×7BæÖ&¶WE÷6–FV6%öf7B€¢.ËÙNÈªNÙKÎ8hŞËÙNÈªN¸ºR¸ù»	‚ºzN¸øBÈ*ÎÉÛN¹9ÎË›B»	Î¸ù’"À¢€¢.É›«ZŞÉÛÉÛB>ÊC#ƒ^Ék^É¹Â«‹«HÉÛBÊsÉk^É¹È‰ÎºzN¸øBÊIÉÛN¸ºBâ ¢.È+ÎÈKÊNÉé‚ÓrãS’R’Â4¾ÙYÉÛN¸¸ÈªB‚ÓrãsbR’¹;ÉØÉ[ŞÈK¸ºBâ ¢’À¢¢–bæ÷BÆÂ€¢f7B–â6–FV6%ö6÷&P¢f÷"f7B–â‚.ËÙNÈªNÙKÌ+~ËÙNÈªN¸ºR"Â#>ÊC#ƒ^Ék^É¹"Â#ÊsÉk^É¹"Â#rãS’R"Â#rãsbR"¢“ ¢W'&÷'2æVæB†b'6–FV6"'F–6ÆR6÷&RöÖ—GFVBÖ&¶WBf7G3¢·6–FV6%ö6÷&WÒ" ¢F&–fe÷F—FÆRÒ.»
ºû‚ÉÙÉ¹¸º‚Â{èîÉysRR«HÈK‚ºxÊx¸[ÈJrÊxËÉÎ¸ºÎ¹ÛÂËH«ZÂ ¢F&–feö&öG’Ò€¢.ÙYÎ«ZÒÉzÎÉ[ÂÉÙÉ¹¹:NÉÛBºû«ZÒØ«¹ûÎÙHBÙhÊ	^»hÉ˜ÉÙÙ¨Â«H«8NÉé¹:NÉØBºxÎ¸)‚ºû«ZŞÉÙ‚ºËNÉzŞ»)R ¢#3ÊÉy¹Kº[‚ËiN««HÈK««‹ÊBÙYÎºû‚ºËNÉzŞÙZÉÙÈ8«HÈKÉÊÉÛ‚R^º[Â¸IÊxÉX®ÉXNÉ[Â ¢.ÙYÎ¸ºN«:ËH«ZÎÙh¸ºBâ»ÊHÉˆÉÙÉ¹ÉØÙYÎ«ZŞÉÛB3SÉkR¸ºÎ¹úÎº[ÂØŠÎÉéÙY¸©B¸ÈÈº«‹ÊB ¢##RR«HÈKº[ÂR^ºÂ¸*îËiN«‹ºÂÙYÂºxÎØÂËiN««HÈK‚»h¸»NÉÛB»	ÎÈ9ŞÙ[NÈIÎ¸©BÉX‚¹	Î¸ºN«: ¢.»	ŞÙ‰N¸ºBâØ«¹ûÎÙHBÙhÊ	^»h¸©B«	^Ê	Î¸[¸ù’ÊÈ*Â«+«;Îº[Â«{Î«ºÂÙYÎ«ZŞÉy"ãR^ÉÙ‚«HÈKº[Â ¢.»h«;ÎÙh«:«;ÎÉèÈ9ŞÈ+ÉØBÉÛNÉÊºÂÙYÂËiN««HÈK¸øBÉˆ«:Ùh¸ºBâ ¢¢F&–feöFWF–ÂÒ6ö×7BæW‡G&7Eö'F–6ÆUöFWF–Â€¢f—‡GW&R‡F&–fe÷F—FÆRÂF&–feö&öG’’À¢F&–fe÷F—FÆRÀ¢¢F&–fe÷&÷rÒ°¢'6÷W&6R#¢.ÊNÉéÈººË‚ÉŠN¸©ÉÙ‚¸›NÈªB"À¢&Æ–W"#¢'G'W7FVB"À¢'V&Æ—6†W"#¢.ÊNÉéÈººË‚"À¢'F—FÆR#¢F&–fe÷F—FÆRÀ¢'6÷W&6U÷F—FÆR#¢F&–feöFWF–Å²'F—FÆR%ÒÀ¢'6÷W&6Uö&öG’#¢F&–feöFWF–Å²&&öG’%ÒÀ¢'6÷W&6Uö'7G&7B#¢F&–feöFWF–Å²&&öG’%ÒÀ¢'7VÖÖ'’#¢F&–feöFWF–Å²&&öG’%ÒÀ¢&Æ–æ²#¢&‡GG3¢ò÷wwræWFæWw2æ6öÒó##cs#CsB"À¢'V&Æ—6†VB#¢æ÷rÀ¢&&öG•÷fW&–f–VB#¢G'VRÀ¢Ğ¢F&–feöÆW'BÒ&öGV7F–öâæ6öçG&7Bç7G&–7Bæ6Æ76–g’‡F&–fe÷&÷rÂæ÷r¢–bæ÷BF&–feöÆW'C ¢W'&÷'2æVæB‚$¶÷&VF&–fb'F–6ÆRv2æ÷B6Æ76–f–VB"¢VÇ6S ¢æ÷&ÖÆ—¦VE÷F&–fbÒ6ö×7Bææ÷&ÖÆ—¦UöÆW'Eöf÷%ö÷WGWB‡F&–feöÆW'B¢g…÷6æ6†÷BÒ°¢'VW'•÷F–ÖUö·7B#¢æ÷ræ—6öf÷&ÖB‡F–ÖW7V3Ò'6V6öæG2"’À¢'&FW2#¢°¢%U4B#¢°¢&6öFR#¢%U4B"À¢'fÇVR#¢CcBãƒ‚À¢'7FGW2#¢.ËYÎ«{Î«¹é‚"À¢'&VfW&Væ6U÷F–ÖUö·7B#¢###bÓrÓ#EC3£#³“£"À¢'VW'•÷F–ÖUö·7B#¢æ÷ræ—6öf÷&ÖB‡F–ÖW7V3Ò'6V6öæG2"’À¢'6÷W&6R#¢%–†öòf–ææ6R"À¢'W&Â#¢6ö×7Bç–†öõög…÷W&Â‚%U4B"’À¢&W'&÷"#¢""À¢Ğ¢ÒÀ¢Ğ¢æ÷&ÖÆ—¦VE÷F&–fe²&g…ö6öçfW'6–öâ%ÒÒ6ö×7Bæ'V–ÆEöÆW'Eög…ö6öçfW'6–öâ€¢æ÷&ÖÆ—¦VE÷F&–fbÀ¢g…÷6æ6†÷BÀ¢æ÷rÀ¢¢&VæFW&VBÒ6ö×7Bæ6ö×7EöÆW'B†æ÷&ÖÆ—¦VE÷F&–fbÂÂæ÷rÂ·ÒÂ·Ò¢6÷&UöÆ–æRÒæW‡B€¢†Æ–æRf÷"Æ–æR–â&VæFW&VBç7Æ—FÆ–æW2‚’–bÆ–æRç7F'G7v—F‚‚"ÒÙ[^ÈºÃ¢"’’À¢""À¢¢–çfW7FÖVçEöÆ–æRÒæW‡B€¢†Æ–æRf÷"Æ–æR–â&VæFW&VBç7Æ—FÆ–æW2‚’–bÆ–æRç7F'G7v—F‚‚"ÒØŠÎÉéØúÎÉÛØ«ƒ¢"’’À¢""À¢¢6÷W&6UöÆ–æRÒæW‡B€¢†Æ–æRf÷"Æ–æR–â&VæFW&VBç7Æ—FÆ–æW2‚’–bÆ–æRç7F'G7v—F‚‚"ÒËiÎË)ƒ¢"’’À¢""À¢¢&WV—&VEöf7G2Ò‚#"ãRR"Â.ËiN««HÈK‚"Â#RR"Â#3SÉkR¸ºÎ¹úÂ"Â.É[ÒS"ã~ÊÉ¹"¢–bæ÷BÆÂ‡FW&Ò–â6÷&UöÆ–æRf÷"FW&Ò–â&WV—&VEöf7G2“ ¢W'&÷'2æVæB†b$¶÷&VF&–fbFWF–ÆVB6÷&RöÖ—GFVB'F–6ÆRf7G3¢¶6÷&UöÆ–æWÒ"¢–bÆVâ†6÷&UöÆ–æRç&VÖ÷fW&Vf—‚‚"ÒÙ[^ÈºÃ¢"’ç7G&—‚’’ÃÒS ¢W'&÷'2æVæB‚$¶÷&VF&–fb6÷&R&Vw&W76VBFòF†Rf÷&ÖW"SÖ6†&7FW"6"¢–b.««*«+ŞÉøº
R"æ÷B–â–çfW7FÖVçEöÆ–æR÷".ºxÊxB"æ÷B–â–çfW7FÖVçEöÆ–æS ¢W'&÷'2æVæB†b$¶÷&VF&–fb–çfW7FÖVçBö–çB—2æ÷BFV6—6–öâ×W6VgVÃ¢¶–çfW7FÖVçEöÆ–æWÒ"¢–b%–†öòf–ææ6RU4Bôµ%r"æ÷B–â6÷W&6UöÆ–æR÷"###bÓrÓ#EC3£#³“£"æ÷B–â6÷W&6UöÆ–æS ¢W'&÷'2æVæB†b$¶÷&VF&–fbe‚&÷fVææ6RÖ—76–æs¢·6÷W&6UöÆ–æWÒ"¢–b.(
b"–â&VæFW&VB÷""âââ"–â&VæFW&VC ¢W'&÷'2æVæB‚$¶÷&VF&–fb6ö×7B÷WGWB6öçF–ç2G'Væ6FVB6VçFVæ6R"¢f÷"Ö&¶W"–âdõ$$”DDTåô4ôÕ5EôÔ$´U%3 ¢–bÖ&¶W"–â&VæFW&VC ¢W'&÷'2æVæB†b$¶÷&VF&–fb6ö×7B÷WGWB&WF–æVB&VÖ÷fVBf–VÆB¶Ö&¶W'Ò" ¢WW%öÖ÷VçG2Ò6ö×7BæW‡G&7Eöf÷&V–våöÖ÷VçG2‚.ÉÊ¹ûÒ«;^Éê^Éy#ÉkRÉÊºÎº[ÂØŠÎÉéÙYÎ¸ºBâ"¢–bæ÷BWW%öÖ÷VçG2÷"WW%öÖ÷VçG5³ÒævWB‚&6öFR"’Ò$UU"# ¢W'&÷'2æVæB‚$UU"Ö÷VçB'6W"F–Bæ÷BFWFV7BWW&òÖFVæöÖ–æFVB–çfW7FÖVçB"¢VÇ6S ¢WW%öÆW'BÒ°¢'FVÆVw&Õö6÷&Uöf7B#¢.ÉÊ¹ûÒ«;^Éê^Éy#ÉkRÉÊºÎº[ÂØŠÎÉéÙYÎ¸ºBâ"À¢&æWw2#¢.ÉÊ¹ûÒ«;^ÉêRØŠÎÉé"À¢Ğ¢WW%÷6æ6†÷BÒ°¢'VW'•÷F–ÖUö·7B#¢æ÷ræ—6öf÷&ÖB‡F–ÖW7V3Ò'6V6öæG2"’À¢'&FW2#¢°¢$UU"#¢°¢&6öFR#¢$UU""À¢'fÇVR#¢ccbã"À¢'7FGW2#¢.ËYÎ«{Î«¹é‚"À¢'&VfW&Væ6U÷F–ÖUö·7B#¢###bÓrÓ#EC3£’³“£"À¢'VW'•÷F–ÖUö·7B#¢æ÷ræ—6öf÷&ÖB‡F–ÖW7V3Ò'6V6öæG2"’À¢'6÷W&6R#¢%–†öòf–ææ6R"À¢'W&Â#¢6ö×7Bç–†öõög…÷W&Â‚$UU""’À¢&W'&÷"#¢""À¢Ğ¢ÒÀ¢Ğ¢WW%ö6öçfW'6–öâÒ6ö×7Bæ'V–ÆEöÆW'Eög…ö6öçfW'6–öâ†WW%öÆW'BÂWW%÷6æ6†÷BÂæ÷r¢6öçfW'FVBÒ6ö×7BæÇ•ö·'uö6öçfW'6–öç2€¢.ÉÊ¹ûÒ«;^Éê^Éy#ÉkRÉÊºÎº[ÂØŠÎÉéÙYÎ¸ºBâ"À¢WW%ö6öçfW'6–öâÀ¢¢–b##ÉkRÉÊºÂÉ[Ò2ã>ÊÉ¹’"æ÷B–â6öçfW'FVC ¢W'&÷'2æVæB†b$UU"Ö÷VçBv2æ÷B6öçfW'FVBFòµ%s¢¶6öçfW'FVGÒ" ¢&WV—&VEö7W'&Væ7•ö6öFW2Ò°¢%U4B"Â$UU""Â$¥’"Â$4å’"Â$t%"Â$4„b"Â$4B"Â$TB"Â$„´B"Â%4tB"Â%EtB ¢Ğ¢–bæ÷B&WV—&VEö7W'&Væ7•ö6öFW2æ—77V'6WB†6ö×7Bädõ$T”tåô5U%$Tä5•õ5T52“ ¢W'&÷'2æVæB‚&Ö¦÷"v÷&ÆBÖ7W'&Væ7’µ%r6öçfW'6–öâ6÷fW&vR—2–æ6ö×ÆWFR"¢W6E÷&Vf—…öÖ÷VçG2Ò6ö×7BæW‡G&7Eöf÷&V–våöÖ÷VçG2€¢%F†Rw&VVÖVçB–æ6ÇVFW2U4B3S&–ÆÆ–öâöb–çfW7FÖVçBâ ¢¢–b€¢æ÷BW6E÷&Vf—…öÖ÷VçG0¢÷"W6E÷&Vf—…öÖ÷VçG5³ÒævWB‚&6öFR"’Ò%U4B ¢÷"W6E÷&Vf—…öÖ÷VçG5³ÒævWB‚&Ö÷VçB"’Ò3Sóóó ¢“ ¢W'&÷'2æVæB‚$•4ò×&Vf—†VBf÷&V–vâÖ÷VçB'6W"F–Bæ÷BFWFV7BU4B3S&–ÆÆ–öâ"  ¦–bõöæÖUõòÓÒ%õöÖ–åõò# ¢&—6R7—7FVÔW†—B†Ö–â‚’