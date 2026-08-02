#!/usr/bin/env python3
"""Contract tests for KHS policy Telegram delivery quality.

These checks encode regressions that already reached Telegram once:
raw English titles, low-impact FCC administrative notices, and wrong sector
explanations. The workflow runs this before sending Telegram alerts.
"""

from __future__ import annotations

import datetime as dt
import json
import tempfile
from pathlib import Path
from zoneinfo import ZoneInfo

import khs_article_detail
from khs_compact_text import compact_prose_lines, concise_text
import khs_policy_alert_guardrails
import khs_policy_alert_router
import khs_domestic_stablecoin_policy_watch
import khs_domestic_telecom_policy_watch
import khs_nuclear_policy_watch
import khs_policy_runtime_patch
import khs_policy_seen_finalize
import khs_policy_telegram_formatter
import khs_policy_watch
import khs_telegram_delivery_guard
import khs_trusted_policy_news_watch
import korea_presidential_postprocess


OUT_DIR = Path("out")
POLICY_FILES = [
    OUT_DIR / "khs_policy_watch_alerts.json",
    OUT_DIR / "khs_policy_watch_alert.md",
    OUT_DIR / "khs_policy_watch_alert_title.txt",
    OUT_DIR / "khs_policy_watch.md",
]
ROOT = Path(__file__).resolve().parents[1]
POLICY_WORKFLOW = ROOT / ".github" / "workflows" / "khs-policy-watch.yml"
COMPACT_PROSE_PREFIXES = (
    "- í•µì‹¬:",
    "- í•µì‹¬ ë‚´ìš©:",
    "- í•µì‹¬ ê·¼ê±°:",
    "- í™•ì¸ ê·¼ê±°:",
    "- íˆ¬ì ê´€ì :",
    "- íˆ¬ì ì˜í–¥:",
    "- íˆ¬ì í¬ì¸íŠ¸:",
    "- í•œêµ­ì¥:",
    "- í•œêµ­ì¥ ì˜í–¥:",
    "- ì‹¤íŒ¨ ì‹ í˜¸:",
)


def assert_compact_prose_limit(body: str, context: str, limit: int = 50) -> None:
    errors: list[str] = []
    for line in body.splitlines():
        stripped = line.strip()
        for prefix in COMPACT_PROSE_PREFIXES:
            if stripped.startswith(prefix):
                value = stripped.removeprefix(prefix).strip()
                if len(value) > limit:
                    errors.append(f"{prefix} {len(value)}ì")
        if stripped.startswith("- ë°˜ì˜/ë°˜ëŒ€:"):
            value = stripped.removeprefix("- ë°˜ì˜/ë°˜ëŒ€:").strip()
            for part in value.split(" / ", 1):
                if len(part.strip()) > limit:
                    errors.append(f"- ë°˜ì˜/ë°˜ëŒ€: {len(part.strip())}ì")
    if errors:
        raise AssertionError(f"{context} compact prose exceeded 50 chars: {errors}")


def main() -> int:
    OUT_DIR.mkdir(exist_ok=True)
    assert_workflow_delivery_dedupe()
    assert_final_policy_telegram_format_and_currency_conversion()
    assert_domestic_telecom_title_gate_and_semantic_dedupe()
    assert_router_explains_current_fcc_documents()
    assert_runtime_patch_accepts_mofcom_watch_source()
    assert_foreign_first_policy_sources()
    assert_china_mofcom_export_control_reaches_policy_lane()
    assert_stablecoin_watch_rejects_bok_generic_page()
    assert_stablecoin_semantic_dedupe()
    assert_router_final_semantic_dedupe()
    assert_router_keeps_source_families_separate()
    assert_whitehouse_detail_body_is_verified()
    assert_whitehouse_current_policy_profiles_are_specific()
    assert_whitehouse_fact_sheet_is_preferred_for_duplicate_story()
    assert_policy_seen_waits_for_confirmed_delivery()
    assert_whitehouse_video_remarks_are_parsed_but_market_filtered()
    assert_whitehouse_executive_order_is_korean_and_not_fcc()
    assert_trump_statement_reaches_policy_lane()
    assert_nato_defense_fact_sheet_is_not_generic_trump_alert()
    assert_trump_iran_war_statement_reaches_geopolitical_lane()
    assert_trusted_iran_hormuz_escalation_reaches_policy_lane()
    assert_trusted_trump_iran_holdoff_summary_and_header()
    assert_trusted_policy_news_story_fingerprint_allows_intraday_updates()
    assert_trusted_policy_news_render_is_compact()
    assert_trusted_trump_rate_and_dollar_profiles_are_specific()
    assert_trusted_trump_current_iran_profiles_are_source_faithful()
    assert_trusted_trump_hormuz_open_is_source_faithful_and_deduped()
    assert_trusted_heat_mortality_is_source_faithful_and_deduped()
    assert_iran_hormuz_story_is_source_faithful_and_cooldown_deduped()
    assert_state_smr_moc_reaches_policy_lane()
    assert_state_smr_moc_trusted_news_fallback_is_not_overfiltered()
    assert_boem_space_launch_is_excluded()
    assert_delivery_guard_blocks_duplicate_policy_alerts()
    assert_delivery_guard_blocks_source_body_mismatch()
    assert_delivery_guard_blocks_fcc_submarine_inverter_mismatch()
    assert_delivery_guard_blocks_bok_generic_stablecoin_mismatch()
    assert_delivery_guard_blocks_url_topic_missing()
    assert_delivery_guard_compacts_and_sends_51_character_prose()
    assert_auxiliary_policy_lanes_are_compact()
    assert_router_explains_fcc_submarine_cable_policy()
    cleanup()
    try:
        write_fcc_regression_fixture()
        khs_policy_alert_guardrails.main()
        khs_policy_alert_router.main()
        khs_telegram_delivery_guard.main()
        assert_policy_output()
    finally:
        cleanup()
    print("khs_policy_delivery_contract=passed")
    return 0


def assert_foreign_first_policy_sources() -> None:
    targets = [
        ROOT / "scripts" / "khs_trusted_policy_news_watch.py",
        ROOT / "scripts" / "khs_transformer_tariff_policy_watch.py",
    ]
    forbidden = [
        "Yonhap", "yonhap", "YNA", "yna", "ì—°í•©ë‰´ìŠ¤",
        "Korea Economic", "korea economic", "í•œêµ­ê²½ì œ", "í•œêµ­ê²½ì œì‹ ë¬¸",
        "ë§¤ì¼ê²½ì œ", "ì„œìš¸ê²½ì œ", "ì„œìš¸ê²½ì œì‹ ë¬¸", "ì„œìš¸ì‹ ë¬¸",
        "Korea Herald", "korea herald", "Korea Joongang", "korea joongang",
        "Daum", "daum", "ë”êµ¬ë£¨", "the guru",
    ]
    for path in targets:
        text = path.read_text(encoding="utf-8")
        for token in forbidden:
            if token in text:
                raise AssertionError(f"foreign-first policy source contract violation: {path.name} contains {token}")


def assert_runtime_patch_accepts_mofcom_watch_source() -> None:
    source = (ROOT / "scripts" / "khs_policy_watch.py").read_text(encoding="utf-8")
    patched = khs_policy_runtime_patch.patch_watch_source(source)
    required = [
        "china_trade_controls",
        "mofcom_html",
        "korea_presidential_personnel",
        "korea_president_html",
    ]
    missing = [token for token in required if token not in patched]
    if missing:
        raise AssertionError(f"runtime patch dropped policy coverage: {missing}")


def assert_china_mofcom_export_control_reaches_policy_lane() -> None:
    source = khs_policy_watch.Source(
        "China MOFCOM announcements",
        "https://www.mofcom.gov.cn/zcfb/blgg/gg/2026/index.html",
        "mofcom_html",
    )
    fixture = """
    <html><body><ul><li>
      <a href="/zcfb/blgg/gg/2026/art/2026/art_helium_test.html">
        å•†åŠ¡éƒ¨å…¬å‘Š2026å¹´ç¬¬99å· å…³äºè‡ªä»Šæ—¥èµ·æš‚åœæ°¦å‡ºå£çš„å…¬å‘Š
      </a><span>2026-07-10</span>
    </li></ul></body></html>
    """
    items = khs_policy_watch.parse_mofcom_html(fixture, source)
    if len(items) != 1:
        raise AssertionError(f"MOFCOM official parser expected 1 item, got {len(items)}")
    alert = khs_policy_watch.classify_item(items[0])
    if not alert or "china_trade_controls" not in (alert.get("matched") or {}):
        raise AssertionError("MOFCOM helium export suspension did not reach the policy classifier")
    khs_policy_alert_router.apply_router_overrides(alert)
    title = khs_policy_alert_router.safe_title(alert)
    if "ì¤‘êµ­ ìƒë¬´ë¶€" not in title or "í—¬ë¥¨" not in title or "ìˆ˜ì¶œ ì¼ì‹œ ì¤‘ë‹¨" not in title:
        raise AssertionError(f"MOFCOM alert title was not specifically translated: {title}")
    if "ë°˜ë„ì²´/HBM ê³µì •ê°€ìŠ¤" not in (alert.get("sectors") or []):
        raise AssertionError("MOFCOM helium alert lost its Korean semiconductor gas value chain")
    if set(alert.get("impacts") or []) != {"ë§¤ì¶œÂ·ë§ˆì§„Â·í˜„ê¸ˆíë¦„", "ìˆ˜ê¸‰", "ì‹œê°„í‘œ"}:
        raise AssertionError(f"MOFCOM decision-impact matrix mismatch: {alert.get('impacts')}")
    rendered = khs_policy_alert_router.render_policy_report(
        [alert],
        dt.datetime(2026, 7, 10, 6, 30, tzinfo=ZoneInfo("Asia/Seoul")),
    )
    if title not in rendered or "ë°˜ë„ì²´Â·HBM ê³µì •" not in rendered or "ì‚°ì—…ê°€ìŠ¤" not in rendered:
        raise AssertionError("MOFCOM compact Korean report dropped its title or Korean value chain")
    mismatch = khs_telegram_delivery_guard.has_source_body_mismatch(title, rendered)
    if mismatch:
        raise AssertionError(f"MOFCOM source/body guard rejected a matching alert: {mismatch}")
    if khs_telegram_delivery_guard.has_long_english_run(rendered):
        raise AssertionError("MOFCOM alert leaked a long untranslated English block")

    irrelevant_fixture = """
    <html><body><a href="/zcfb/blgg/gg/2026/art/2026/art_food_test.html">
      å•†åŠ¡éƒ¨å…¬å‘Š2026å¹´ç¬¬98å· å¯¹åŸäº§äºåŠ æ‹¿å¤§çš„è±Œè±†æ·€ç²‰åå€¾é”€è°ƒæŸ¥åˆæ­¥è£å®š
    </a><span>2026-07-10</span></body></html>
    """
    if khs_policy_watch.parse_mofcom_html(irrelevant_fixture, source):
        raise AssertionError("unrelated MOFCOM food anti-dumping notice passed the Korea/strategic-product guard")


def assert_workflow_delivery_dedupe() -> None:
    workflow = POLICY_WORKFLOW.read_text(encoding="utf-8")
    required = [
        "KHS_TELEGRAM_DEDUPE_HOURS",
        "data/khs_telegram_delivery_seen.json",
        "hashlib.sha256(canonical_message(title, body).encode(\"utf-8\"))",
        "semantic_parts = [\"semantic\"]",
        "urllib.parse.urldefrag",
        "telegram_duplicate_skipped",
        "telegram_dry_run",
        "khs_telegram_delivery_confirmed.json",
        "Finalize policy seen state after confirmed Telegram outcome",
        "python scripts/khs_policy_seen_finalize.py",
        "Commit confirmed watch and Telegram state",
        "Upload policy watch verification artifacts",
        "out/khs_telegram_dry_run.md",
        "format_policy_message(title, body)",
        "validate_final_policy_message(title, body)",
    ]
    for marker in required:
        if marker not in workflow:
            raise AssertionError(f"KHS policy workflow missing Telegram delivery dedupe marker: {marker}")
    send_index = workflow.index("- name: Send Telegram alert")
    finalize_index = workflow.index("- name: Finalize policy seen state after confirmed Telegram outcome")
    if finalize_index <= send_index:
        raise AssertionError("KHS policy seen state is finalized before Telegram delivery")
    forbidden = [
        r'Actions: {run_url}',
        r'Issues: {issue_url}',
        r'body[:3300]',
    ]
    for marker in forbidden:
        if marker in workflow:
            raise AssertionError(f"KHS policy workflow still appends removed Telegram metadata: {marker}")


def assert_final_policy_telegram_format_and_currency_conversion() -> None:
    now = dt.datetime(2026, 7, 25, 21, 47, tzinfo=ZoneInfo("Asia/Seoul"))
    title = "KHS ì‹ ë¢°ì™¸ì‹  ì •ì±… ì›Œì¹˜: [ìƒÂ·ê³µì‹ í™•ì¸ ì „] ë¯¸êµ­, $17.5 billion ì›ì „ ëŒ€ì¶œ"
    body = "\n".join(
        [
            "ğŸš¨ KHS ì‹ ë¢°ì™¸ì‹  ì •ì±…Â·ê·œì œ ê³ ì¶©ê²© ì›Œì¹˜ Â· 2026ë…„ 07ì›” 25ì¼ 21:47 KST",
            "",
            "## 1. [ìƒÂ·ê³µì‹ í™•ì¸ ì „] ë¯¸êµ­, ì›ì „ ëŒ€ì¶œê³¼ 5ì–µìœ ë¡œ í˜‘ë ¥ê¸°ê¸ˆ ë°œí‘œ",
            "- í•µì‹¬: ë¯¸êµ­ì´ ì›ì „ ê±´ì„¤ì— $17.5 billion ì €ë¦¬ ëŒ€ì¶œì„ ì œì‹œí–ˆìŠµë‹ˆë‹¤.",
            "- íˆ¬ì ê´€ì : ì‹¤ì œ ëŒ€ì¶œ ì¡°ê±´ê³¼ ê¸°ìì¬ ë°œì£¼ ì¼ì •ì„ í™•ì¸í•©ë‹ˆë‹¤.",
            "- í•œêµ­ì¥ ì˜í–¥: êµ­ë‚´ ì›ì „ ê¸°ìì¬ì˜ ë¯¸êµ­ ê³µê¸‰ ë…¸ì¶œì„ í™•ì¸í•©ë‹ˆë‹¤.",
            "- ì˜ì‚¬ê²°ì • ì˜í–¥: ë§¤ì¶œÂ·ë§ˆì§„Â·í˜„ê¸ˆíë¦„, ì‹œê°„í‘œ",
            "- ì˜í–¥ ì„¹í„°: ì›ì „/ì „ë ¥ê¸°ê¸°",
            "- ë°˜ì˜/ë°˜ëŒ€: ê¸°ëŒ€ ì¼ë¶€ ë°˜ì˜ / ìµœì¢… ëŒ€ì¶œê³„ì•½ì€ ë¯¸ì •",
            "- ì‹¤íŒ¨ ì‹ í˜¸: ìµœì¢… ëŒ€ì¶œê³„ì•½ê³¼ ë°œì£¼ê°€ ì—†ìœ¼ë©´ ì•½í™”ë©ë‹ˆë‹¤.",
            "- ì¶œì²˜: [Reuters](https://www.reuters.com/example-policy-story) Â· ì¡°íšŒ 21:47 KST",
            "",
            "Actions: https://github.com/qedgwangju-dot/khs-watch/actions/runs/1",
            "Issues: https://github.com/qedgwangju-dot/khs-watch/issues",
            "íˆ¬ì ì¡°ì–¸ì´ ì•„ë‹Œ ì°¸ê³ ìš© ì •ì±…Â·ê·œì œ ì•Œë¦¼ì…ë‹ˆë‹¤.",
        ]
    )
    formatted_title, formatted_body = khs_policy_telegram_formatter.format_policy_message(
        title,
        body,
        rates={"USD": 1400.0, "EUR": 1600.0},
        now=now,
    )
    required = [
        "25ì¡°ì›",
        "8,000ì–µì›",
        "- í•µì‹¬:",
        "https://www.reuters.com/example-policy-story",
    ]
    for marker in required:
        if marker not in f"{formatted_title}\n{formatted_body}":
            raise AssertionError(f"final policy Telegram format missing: {marker}")
    forbidden = [
        "KHS ",
        "## 1.",
        "- íˆ¬ì ê´€ì :",
        "- í•œêµ­ì¥ ì˜í–¥:",
        "- ì˜í–¥ ì„¹í„°:",
        "- ì˜ì‚¬ê²°ì • ì˜í–¥:",
        "- ë°˜ì˜/ë°˜ëŒ€:",
        "- ì‹¤íŒ¨ ì‹ í˜¸:",
        "- ì›í™” í™˜ì‚° ê¸°ì¤€:",
        "Actions:",
        "Issues:",
        "íˆ¬ì ì¡°ì–¸ì´ ì•„ë‹Œ ì°¸ê³ ìš© ì •ì±…Â·ê·œì œ ì•Œë¦¼ì…ë‹ˆë‹¤.",
    ]
    for marker in forbidden:
        if marker in f"{formatted_title}\n{formatted_body}":
            raise AssertionError(f"final policy Telegram format leaked removed text: {marker}")
    errors = khs_policy_telegram_formatter.validate_final_policy_message(
        formatted_title,
        formatted_body,
    )
    if errors:
        raise AssertionError(f"final policy Telegram validation failed: {errors}")
    second_title, second_body = khs_policy_telegram_formatter.format_policy_message(
        formatted_title,
        formatted_body,
        rates={"USD": 1400.0, "EUR": 1600.0},
        now=now,
    )
    if (second_title, second_body) != (formatted_title, formatted_body):
        raise AssertionError("policy Telegram formatter is not idempotent")

    multi_amount_title, multi_amount_body = khs_policy_telegram_formatter.format_policy_message(
        "ì‹ ë¢°ì™¸ì‹  ì •ì±… ì›Œì¹˜: ê¸€ë¡œë²Œ íˆ¬ìê³„íš",
        "\n".join([
            "1. [ìƒÂ·ê³µì‹ í™•ì¸ ì „] ê¸€ë¡œë²Œ íˆ¬ìê³„íš",
            "- í•µì‹¬: íˆ¬ìì•¡ 9500ì–µë‹¬ëŸ¬ì™€ ì¶”ê°€ê³„íš 1ì¡°7000ì–µë‹¬ëŸ¬ê°€ ë°œí‘œëìŠµë‹ˆë‹¤.",
            "- ì¶œì²˜: [Reuters](https://www.reuters.com/example-investment-plan)",
        ]),
        rates={"USD": 1462.1},
        now=now,
    )
    multi_core = next(
        line.removeprefix("- í•µì‹¬:").strip()
        for line in multi_amount_body.splitlines()
        if line.startswith("- í•µì‹¬:")
    )
    for marker in (
        "9500ì–µë‹¬ëŸ¬(ì•½ 1,389ì¡°ì›)",
        "1ì¡°7000ì–µë‹¬ëŸ¬(ì•½ 2,486ì¡°ì›)",
    ):
        if marker not in multi_core:
            raise AssertionError(f"policy 50-char FX core missing {marker}: {multi_core}")
    if len(multi_corÛ_8êÚ$z{-®éÜj×"ÀĞ¢'7FGW2#¢.Ù™^Ê	R"ÀĞ¢'V&Æ—6†VEö·7B#¢###bÓrÓ…C“££³“£"ÀĞ¢&ÖF6†VB#¢²&f65öFV6—6–öåöæ÷F–6R#¢²&æF–öæÂ6V7W&—G’"Â''VÆVÖ¶–ær%×ÒÀĞ¢&–×7G2#¢².È¹Î«NÙÂ"Â.ÙZÉÛÉÊ‚%ÒÀĞ¢'F‡2#¢².Ê	^ËRØ8ÉèN¹ÛÎÉÛ‚"Â.ÙZÉÛÉÊ‚%ÒÀĞ¢'6V7F÷'2#¢².Øk^Èºôd42şÉÈNÈK%ÒÀĞ¢ĞĞ¢Vç&–6†VBÒ¶‡5÷öÆ–7•öÆW'E÷&÷WFW"æVç&–6…öÖ—76–æuö6öçFW‡B†—FVÒĞ¢¶‡5÷öÆ–7•öÆW'E÷&÷WFW"æÇ•÷&÷WFW%ö÷fW'&–FW2†Vç&–6†VBĞ¢F—FÆRÒ¶‡5÷öÆ–7•öÆW'E÷&÷WFW"ç6fU÷F—FÆR†Vç&–6†VBĞ¢f–VÆG2Ò""æ¦ö–â€Ğ¢7G"†Vç&–6†VBævWB†¶W’’÷"""Ğ¢f÷"¶W’–â‚'öÆ–7•÷Æ–å÷7VÖÖ'’"Â&–çfW7FÖVçE÷f–Wr"Â&¶÷&VöÖ&¶WEö–×7B"Â'6V7F÷'2"Ğ¢’æÆ÷vW"‚Ğ¢–b.Ù[NÊËÈÉÛN»‰B"æ÷B–âF—FÆRæB.Ù[NÊØk^ÈºËÈÉÛN»‰B"æ÷B–âf–VÆG3 Ğ¢&—6R76W'F–öäW'&÷"‚$d427V&Ö&–æR6&ÆRöÆ–7’v2æ÷B&÷WFVBFò7V&Ö&–æR6&ÆRW‡ÆæF–öâ"Ğ¢f÷&&–FFVâÒ²&–çfW'FW""Â&VæW&w’–çfW'FW""Â'6öÆ"–çfW'FW""Â.ÉÛ»(NØK"Â.ÊNº
^»8Ù™Éê^Ë™‚%ĞĞ¢f÷"Fö¶Vâ–âf÷&&–FFVã Ğ¢–bFö¶VâæÆ÷vW"‚’–âf–VÆG3 Ğ¢&—6R76W'F–öäW'&÷"†b$d427V&Ö&–æR6&ÆRW‡ÆæF–öâÆV¶VB–çfW'FW"&öG“¢·Fö¶VçÒ"Ğ Ğ Ğ ¦FVb76W'EöFöÖW7F–5÷FVÆV6öÕ÷F—FÆUövFUöæE÷6VÖçF–5öFVGWR‚’ÓâæöæS ¢F—'G•÷F—FÆRÒ.ÉXÎ¹ËØû¸øB~¸ÛÉÛNØKÉXÈºÎÉ‹^ÈY‚r¸øNÉè^(
n¸ºBÈÚ¸øB«8NÈhÒÉ;N¸ºB¸º«8NÙY¹ÛÒ ¢6ÆVå÷F—FÆRÒ¶‡5öFöÖW7F–5÷FVÆV6öÕ÷öÆ–7•÷vF6‚æ6ÆVåöÆ–æµ÷F—FÆR†F—'G•÷F—FÆR¢–b6ÆVå÷F—FÆRÒ.ÉXÎ¹ËØû¸øB~¸ÛÉÛNØKÉXÈºÎÉ‹^ÈY‚r¸øNÉè^(
n¸ºBÈÚ¸øB«8NÈhÒÉ;N¸ºB# ¢&—6R76W'F–öäW'&÷"†b'FVÆV6öÒ66W76–&–Æ—G’Æ&VÂv2æ÷B&VÖ÷fVC¢¶6ÆVå÷F—FÆWÒ" ¢fÇ6U÷F—FÆW2Ò°¢.ÙYÂŞÉXNº[NÙz‚ÂÙ[^ÈºÎ«IºËÂÙ‰º
RÔõRË+N«+(
nÊI¸*ºû‚«;^«ˆºyÒÙ‰º
R»;«*Ù™BäUr"À¢.»;NÙ¸ÉÙº8Î¸ÈÈ8ÉéÂÉÛ«{Â»9+~ÉÙÉ¹¹;Ë™ºzBË™º8Î»˜BÊxÉ¹»	¾ÉØBÈ‰‚ÉèÉkB"À¢.«ZŞ¸+BË*²ÙYÎ«ZŞÙ‰RÉÛNÊxÈªN«ZÎËi^ÙZ‚«NÊ»;«*Ù™B"À¢Ğ¢f÷"F—FÆR–âfÇ6U÷F—FÆW3 ¢–b¶‡5öFöÖW7F–5÷FVÆV6öÕ÷öÆ–7•÷vF6‚æ†5öç’€¢F—FÆRÀ¢¶‡5öFöÖW7F–5÷FVÆV6öÕ÷öÆ–7•÷vF6‚åD•DÄUõDTÄT4ôÕõDU$Õ2À¢“ ¢&—6R76W'F–öäW'&÷"†b'Vç&VÆFVBF—FÆR76VBFVÆV6öÒF—FÆRvFS¢·F—FÆWÒ" ¢G'VU÷F—FÆW2Ò°¢.ÉXÎ¹ËØû¸øB¸ÛÉÛNØKÉXÈºÎÉ‹^ÈY‚¸øNÉè^(
n¸ºBÈÚ¸øB«8NÈhÒÉ;N¸ºB"À¢.Ê	^»hÂ««8NØk^Èº»˜B»h¸»BÉ˜NÙ™BÉÈNÙYÂÉ©N«ˆÊ	Â«	ÎØë‚»	ÎÙÂ"À¢Ğ¢f÷"F—FÆR–âG'VU÷F—FÆW3 ¢–bæ÷B¶‡5öFöÖW7F–5÷FVÆV6öÕ÷öÆ–7•÷vF6‚æ†5öç’€¢F—FÆRÀ¢¶‡5öFöÖW7F–5÷FVÆV6öÕ÷öÆ–7•÷vF6‚åD•DÄUõDTÄT4ôÕõDU$Õ2À¢“ ¢&—6R76W'F–öäW'&÷"†b'FVÆV6öÒF—FÆRv2&Æö6¶VC¢·F—FÆWÒ" ¢f—'7BÒ¶‡5öFöÖW7F–5÷FVÆV6öÕ÷öÆ–7•÷vF6‚çFVÆV6öÕöWfVçEöf–ævW'&–çB€¢.Ê	^»hÂØk^Èº»˜BÉÛÙY‚Ê	^ËRÉY^»	RÙ™^ÉÛ‚"À¢.««8NØk^Èº»˜B»h¸»BÉ˜NÙ™B»
ÉXÉØB¸[ÎÉÙÙhÈ«^¸¸¸ºBâ"À¢¢6V6öæBÒ¶‡5öFöÖW7F–5÷FVÆV6öÕ÷öÆ–7•÷vF6‚çFVÆV6öÕöWfVçEöf–ævW'&–çB€¢.««8NØk^Èº»˜B»h¸»BÉ˜NÙ™B¸[ÎÉÙ‚"À¢.Øk^ÈºÉ©N«ˆ‚«	ÎØë‚«¸ª^ÈKÉØB«(ØjÙhÈ«^¸¸¸ºBâ"À¢¢–bf—'7BÒ6V6öæC ¢&—6R76W'F–öäW'&÷"‚&vVæW&–2FVÆV6öÒ&W77W&RWfVçBF–Bæ÷B¶VWöæR6VÖçF–2¶W’" ¢6öæ7&WFRÒ¶‡5öFöÖW7F–5÷FVÆV6öÕ÷öÆ–7•÷vF6‚çFVÆV6öÕöWfVçEöf–ævW'&–çB€¢.ÉXÎ¹ËØû¸ÛÉÛNØKÉXÈºÎÉ‹^ÈY‚É¹BÈ¹ÎÙh’"À¢.ÉXÎ¹ËØû¸ÛÉÛNØKÉXÈºÎÉ‹^ÈYÉØBÉ¹N»hØKÈ¹ÎÙhÙZ¸¸¸ºBâ"À¢¢–b6öæ7&WFRÓÒf—'7C ¢&—6R76W'F–öäW'&÷"‚&6öæ7&WFRFVÆV6öÒ–×ÆVÖVçFF–öâ6öÆÆ6VB–çFòvVæW&–2&W77W&RWfVçB" ¢×fæõöf—'7BÒ¶‡5öFöÖW7F–5÷FVÆV6öÕ÷öÆ–7•÷vF6‚çFVÆV6öÕöWfVçEöf–ævW'&–çB€¢F—'G•÷F—FÆRÀ¢.Ê	^»h«ÉXÎ¹ËØû¸ÛÉÛNØKÉXÈºÎÉ‹^ÈYÉØB¸øNÉè^ÙZ¸¸¸ºBâ"À¢¢×fæõ÷6V6öæBÒ¶‡5öFöÖW7F–5÷FVÆV6öÕ÷öÆ–7•÷vF6‚çFVÆV6öÕöWfVçEöf–ævW'&–çB€¢.ÉXÎ¹ËØû¸ÛÉÛNØKÉXÈºÎÉ‹^ÈY‚È¹ÎÙh’"À¢.¸ÛÉÛNØKÈhÎÊxB¹*NÉy¸øBÊÈhŞÉËÎºÂ«8NÈhÒÉÛNÉªÙZÈ‰‚ÉèÈ«^¸¸¸ºBâ"À¢¢–b×fæõöf—'7BÒ×fæõ÷6V6öæC ¢&—6R76W'F–öäW'&÷"‚'6ÖRÕdäòFF×6fWG’öÆ–7’&öGV6VBGWÆ–6FR6VÖçF–2¶W—2" ¢Wf–FVæ6RÒ¶‡5öFöÖW7F–5÷FVÆV6öÕ÷öÆ–7•÷vF6‚çöÆ–7•öWf–FVæ6U÷7VÖÖ'’€¢.ÉXÎ¹ËØû¸øB¸ÛÉÛNØKÉXÈºÎÉ‹^ÈY‚¸øNÉèR"À¢.«Hº
«‹È*ÂÈ+ÎÈKÊNÉéÈºÊ	ÎÙ(‚ËiÎÈ¹ÂåÆîÊ	^»h¸©BÉXÎ¹ËØû¸ÛÉÛNØKÉXÈºÎÉ‹^ÈYÉØBÉ¹N»hØK¸øNÉè^ÙYÎ¸ºBâ"À¢¢–b#É¹N»hØK¸øNÉèR"æ÷B–âWf–FVæ6R÷".È+ÎÈKÊNÉéÈºÊ	ÎÙ(‚"–âWf–FVæ6S ¢&—6R76W'F–öäW'&÷"†b'FVÆV6öÒWf–FVæ6RW‡G&7F–öâÖ—6ÖF6ƒ¢¶Wf–FVæ6WÒ" ¢ÆW'BÒ°¢'6÷W&6R#¢$¶÷&VöÆ–7’'&–Vf–ærFVÆV6öÒöÆ–7’"À¢'F—FÆR#¢F—'G•÷F—FÆRÀ¢&÷&–v–æÅ÷F—FÆR#¢F—'G•÷F—FÆRÀ¢&Æ–æ²#¢&‡GG3¢ò÷wwræ¶÷&Væ·"öæWw2÷öÆ–7”æWw5f–WræFóöæWw4–CÓCƒ“c“c’"À¢&–×÷'Fæ6R#¢.È8"À¢'7FGW2#¢.Ù™^Ê	R"À¢'7VÖÖ'’#¢.Ê	^»h«ÉXÎ¹ËØû¸ÛÉÛNØKÉXÈºÎÉ‹^ÈYÉØB¸øNÉè^ÙZ¸¸¸ºBâ"À¢'öÆ–7•÷Æ–å÷7VÖÖ'’#¢.Ê	^»h«ÉXÎ¹ËØû¸ÛÉÛNØKÉXÈºÎÉ‹^ÈYÉØB¸øNÉè^ÙZ¸¸¸ºBâ"À¢&ÖF6†VB#¢²&¶÷&V÷FVÆV6öÕ÷öÆ–7’#¢².ÉXÎ¹ËØû"Â.¸ÛÉÛNØKÉXÈºÎÉ‹^ÈY‚%×ÒÀ¢&–×7G2#¢².ºzNËiÌ+~ºxÊxL+~ÙˆN«ˆÙÙºhB"Â.È¹Î«NÙÂ%ÒÀ¢'6V7F÷'2#¢².«ZŞ¸+BØk^ÈºÊ	^ËRşØk^Èº>È*Â%ÒÀ¢Ğ¢¶‡5÷öÆ–7•öÆW'E÷&÷WFW"æÇ•÷&÷WFW%ö÷fW'&–FW2†ÆW'B¢W‡V7FVE÷F—FÆRÒ.Ê	^»hÂÉXÎ¹ËØû¸ÛÉÛNØKÉXÈºÎÉ‹^ÈY‚¸øNÉèR ¢W‡V7FVEö6÷&RÒ.Ê	^»h«ÉXÎ¹ËØû¸ÛÉÛNØKÈhÎÊxB¹*NÉy¸øBÊÈhÒÉÛNÉª’«¸ª^ÙYÂÉXÈºÎÉ‹^ÈYÉØB¸øNÉè^ÙhÈ«^¸¸¸ºBâ ¢–b¶‡5÷öÆ–7•öÆW'E÷&÷WFW"ç6fU÷F—FÆR†ÆW'B’ÒW‡V7FVE÷F—FÆS ¢&—6R76W'F–öäW'&÷"†b$ÕdäòF—FÆRÖ—6ÖF6ƒ¢¶¶‡5÷öÆ–7•öÆW'E÷&÷WFW"ç6fU÷F—FÆR†ÆW'B—Ò"¢–bÆW'BævWB‚'öÆ–7•÷Æ–å÷7VÖÖ'’"’ÒW‡V7FVEö6÷&S ¢&—6R76W'F–öäW'&÷"†b$Õdäò6÷&RÖ—6ÖF6ƒ¢¶ÆW'BævWB‚wöÆ–7•÷Æ–å÷7VÖÖ'’r—Ò"¢&W÷'BÒ¶‡5÷öÆ–7•öÆW'E÷&÷WFW"ç&VæFW%÷öÆ–7•÷&W÷'B€¢¶ÆW'EÒÀ¢GBæFFWF–ÖRƒ##bÂ‚ÂÂ‚Â"ÂG¦–æfóÕ¦öæT–æfò‚$6–õ6V÷VÂ"’’À¢¢f÷&ÖGFVE÷F—FÆRÂf÷&ÖGFVEö&öG’Ò¶‡5÷öÆ–7•÷FVÆVw&Õöf÷&ÖGFW"æf÷&ÖE÷öÆ–7•öÖW76vR€¢.Ê	^ËRÉ¸ÎË™ƒ¢¾È8ÒÊ	^»hÂÉXÎ¹ËØû¸ÛÉÛNØKÉXÈºÎÉ‹^ÈY‚¸øNÉèR"À¢&W÷'BÀ¢¢W'&÷'2Ò¶‡5÷öÆ–7•÷FVÆVw&Õöf÷&ÖGFW"çfÆ–FFUöf–æÅ÷öÆ–7•öÖW76vR€¢f÷&ÖGFVE÷F—FÆRÀ¢f÷&ÖGFVEö&öG’À¢¢–bW'&÷'3 ¢&—6R76W'F–öäW'&÷"†b$Õdäòf–æÂFVÆVw&Òf÷&ÖBf–ÆVC¢¶W'&÷'7Ò"¢–b.¸º«8NÙY¹ÛÒ"–âf÷&ÖGFVEö&öG’÷"W‡V7FVEö6÷&Ræ÷B–âf÷&ÖGFVEö&öG“ ¢&—6R76W'F–öäW'&÷"‚$Õdäòf–æÂFVÆVw&ÒÖW76vRÆ÷7BF†R6ÆVæVB6÷W&6R×7V6–f–26÷&R"  ¦FVb76W'E÷&÷WFW%öW‡Æ–ç5ö7W'&VçEöf65öFö7VÖVçG2‚’ÓâæöæS ¢66W2Ò°¢€¢°¢'6÷W&6R#¢$fVFW&Â&Vv—7FW"d42"À¢'F—FÆR#¢$V7F–öâöbfÆW†–&ÆRW6RÆ–6Vç6W2–âF†RWW"2Ô&æBf÷"æW‡BÔvVæW&F–öâv—&VÆW726W'f–6W266†VGVÆVB"À¢&÷&–v–æÅ÷F—FÆR#¢$V7F–öâöbfÆW†–&ÆRW6RÆ–6Vç6W2–âF†RWW"2Ô&æBf÷"æW‡BÔvVæW&F–öâv—&VÆW726W'f–6W266†VGVÆVB"À¢&Æ–æ²#¢&‡GG3¢ò÷wwræfVFW&Ç&Vv—7FW"æv÷böFö7VÖVçG2ó##bó‚ó2ó##bÓSs#RöV7F–öâÖöbÖfÆW†–&ÆR×W6RÖÆ–6Vç6W2Ö–â×F†R×WW"Ö2Ö&æBÖf÷"ÖæW‡BÖvVæW&F–öâ×v—&VÆW72×6W'f–6W2×66†VGVÆVB"À¢&–×÷'Fæ6R#¢.È8"À¢'7FGW2#¢.Ù™^Ê	R"À¢'V&Æ—6†VEö·7B#¢###bÓ‚Ó5C“££³“£"À¢&ÖF6†VB#¢²&f65öFV6—6–öåöæ÷F–6R#¢²&V7F–öâ"Â'WW"2Ö&æB%×ÒÀ¢&–×7G2#¢².È¹Î«NÙÂ%ÒÀ¢'F‡2#¢².Ê	^ËRØ8ÉèN¹ÛÎÉÛ‚%ÒÀ¢'6V7F÷'2#¢².Øk^Èºôd42şÉÈNÈK%ÒÀ¢ÒÀ¢$d42ÂÈ8¸º‚>¸ÈÉzÒË
ÈK¸ÈºËNÈJØk^ÈºÊ;ÎØÈÎÈ‰‚«+ŞºzBÉÛÎÊ	R«;^ÙÂ"À¢.È8¸º‚>¸ÈÉzÒÔ‡¢ÉÛNÈ8º›NÙx‚"À¢’À¢€¢°¢'6÷W&6R#¢$fVFW&Â&Vv—7FW"d42"À¢'F—FÆR#¢%6VV¶–ær6öÖÖVçBöâ&ö†–&—F–ærF†R–×÷'FF–öâæBÖ&¶WF–æröb6W'F–âf÷&V–vâÕ&öGV6VB6öÖ×Væ–6F–öç2WV—ÖVçB"À¢&÷&–v–æÅ÷F—FÆR#¢%6VV¶–ær6öÖÖVçBöâ&ö†–&—F–ærF†R–×÷'FF–öâæBÖ&¶WF–æröb6W'F–âf÷&V–vâÕ&öGV6VB6öÖ×Væ–6F–öç2WV—ÖVçB"À¢&Æ–æ²#¢&‡GG3¢ò÷wwræfVFW&Ç&Vv—7FW"æv÷böFö7VÖVçG2ó##bó‚ó2ó##bÓScS’÷6VV¶–ærÖ6öÖÖVçBÖöâ×&ö†–&—F–ær×F†RÖ–×÷'FF–öâÖæBÖÖ&¶WF–ærÖöbÖ6W'F–âÖf÷&V–vâ×&öGV6VB"À¢&–×÷'Fæ6R#¢.È8"À¢'7FGW2#¢.Ù™^Ê	R"À¢'V&Æ—6†VEö·7B#¢###bÓ‚Ó5C“££³“£"À¢&ÖF6†VB#¢²&f65öFV6—6–öåöæ÷F–6R#¢²&6÷fW&VBÆ—7B"Â&æF–öæÂ6V7W&—G’"Â'&ö†–&—B%×ÒÀ¢&–×7G2#¢².ºzNËiÌ+~ºxÊxL+~ÙˆN«ˆÙÙºhB"Â.È‰«ˆ’"Â.È¹Î«NÙÂ%ÒÀ¢'F‡2#¢².Ê	^ËRØ8ÉèN¹ÛÎÉÛ‚"Â.«;^«ˆºyÒ%ÒÀ¢'6V7F÷'2#¢².Øk^Èºôd42şÉÈNÈK%ÒÀ¢ÒÀ¢$d42ÂÉ›«ZŞÈ+«[Éª«ˆ’ºËNÉÛ«‹+~Ù[^ÈºÎ»hÙ(‚È‰Éè\+~ØÉºzB«ˆÊxÉX‚ÉÙ«*ÎÈ‰ºB"À¢.É›«ZŞÈ+«[Éª’ºËNÉÛ«‹…T2œ+~Ù[^ÈºÎ»hÙ(‚"À¢’À¢Ğ¢&÷WFVBÒµĞ¢f÷"ÆW'BÂW‡V7FVE÷F—FÆRÂW‡V7FVEö6÷&R–â66W3 ¢¶‡5÷öÆ–7•öÆW'E÷&÷WFW"æÇ•÷&÷WFW%ö÷fW'&–FW2†ÆW'B¢7GVÅ÷F—FÆRÒ¶‡5÷öÆ–7•öÆW'E÷&÷WFW"ç6fU÷F—FÆR†ÆW'B¢6÷&RÒ7G"†ÆW'BævWB‚'öÆ–7•÷Æ–å÷7VÖÖ'’"’÷"""¢–b7GVÅ÷F—FÆRÒW‡V7FVE÷F—FÆS ¢&—6R76W'F–öäW'&÷"†b$d42F—FÆRÖ—6ÖF6ƒ¢¶7GVÅ÷F—FÆWÒÒ¶W‡V7FVE÷F—FÆWÒ"¢–bW‡V7FVEö6÷&Ræ÷B–â6÷&S ¢&—6R76W'F–öäW'&÷"†b$d426÷&RÖ—6ÖF6ƒ¢¶6÷&WÒ"¢&÷WFVBæVæB†ÆW'B ¢6VÖçF–5ö¶W—2Ò°¢¶‡5÷öÆ–7•öÆW'E÷&÷WFW"ç6VÖçF–5öÆW'Eö¶W’†ÆW'B¢f÷"ÆW'B–â&÷WFV@¢Ğ¢–bÆVâ‡6WB‡6VÖçF–5ö¶W—2’’ÒÆVâ‡6VÖçF–5ö¶W—2“ ¢&—6R76W'F–öäW'&÷"†b&F—7F–æ7Bd42Fö7VÖVçG26öÆÆ6VBFòöæR6VÖçF–2¶W“¢·6VÖçF–5ö¶W—7Ò" ¢f÷"ÆW'BÂW‡V7FVE÷F—FÆRÂW‡V7FVEö6÷&R–â66W3 ¢&W÷'BÒ¶‡5÷öÆ–7•öÆW'E÷&÷WFW"ç&VæFW%÷öÆ–7•÷&W÷'B€¢¶ÆW'EÒÀ¢GBæFFWF–ÖRƒ##bÂ‚ÂÂRÂS’ÂG¦–æfóÕ¦öæT–æfò‚$6–õ6V÷VÂ"’’À¢¢–bW‡V7FVE÷F—FÆRæ÷B–â&W÷'B÷"W‡V7FVEö6÷&Ræ÷B–â&W÷'C ¢&—6R76W'F–öäW'&÷"†b$d42&VæFW&VB&W÷'BÆ÷7B6÷W&6R×7V6–f–26öçFVçC¢¶W‡V7FVE÷F—FÆWÒ"¢–b.ØŠÎÉéÊÉkÉÛBÉXN¸¸ÂË«:Éª’Ê	^Ë\+~«yÎÊ	ÂÉXÎºkÎÉè^¸¸¸ºBâ"–â&W÷'C ¢&—6R76W'F–öäW'&÷"‚'&VÖ÷fVBöÆ–7’F—66Æ–ÖW"ÆV¶VB–çFò&÷WFW"÷WGWB"  ¦FVb6ÆVçW‚’ÓâæöæS Ğ¢f÷"F‚–âôÄ”5•ôd”ÄU3 Ğ¢–bF‚æW†—7G2‚“ Ğ¢F‚çVæÆ–æ²‚Ğ Ğ Ğ¦FVb&WV—&VEöW‡ÆæF–öåöÆ–æW2†æ÷FS¢7G"’ÓâÆ—7E·7G%Ó Ğ¢&WGW&â°Ğ¢b'¶Ö&¶W'5³×Ò¶æ÷FWÒ Ğ¢f÷"Ö&¶W'2–â¶‡5÷FVÆVw&ÕöFVÆ—fW'•öwV&Bå$UT•$TEôU…ÄäD”ôåôd”TÄEôu$õU0Ğ¢ĞĞ Ğ Ğ¦FVbw&—FUöf65÷&Vw&W76–öåöf—‡GW&R‚’ÓâæöæS Ğ¢ÆW'G2Ò°Ğ¢°Ğ¢'6÷W&6R#¢$fVFW&Â&Vv—7FW"d42"ÀĞ¢'F—FÆR#¢%WF—F–öâf÷"&V6öç6–FW&F–öâöb7F–öâ–â'VÆVÖ¶–ær&ö6VVF–ær"ÀĞ¢&÷&–v–æÅ÷F—FÆR#¢%WF—F–öâf÷"&V6öç6–FW&F–öâöb7F–öâ–â'VÆVÖ¶–ær&ö6VVF–ær"ÀĞ¢&Æ–æ²#¢&‡GG3¢ò÷wwræfVFW&Ç&Vv—7FW"æv÷böFö7VÖVçG2ó##bóróbó##bÓ3c÷WF—F–öâÖf÷"×&V6öç6–FW&F–öâÖöbÖ7F–öâÖ–â×'VÆVÖ¶–ær×&ö6VVF–ær"ÀĞ¢&–×÷'Fæ6R#¢.È8"ÀĞ¢'7FGW2#¢.Ù™^Ê	R"ÀĞ¢'V&Æ—6†VEö·7B#¢###bÓrÓeC“££³“£"ÀĞ¢&ÖF6†VB#¢²&f65öFV6—6–öåöæ÷F–6R#¢²'&÷÷6VB'VÆR"Â''VÆVÖ¶–ær%×ÒÀĞ¢&–×7G2#¢².È¹Î«NÙÂ"Â.È‰«ˆ’%ÒÀĞ¢'F‡2#¢².Ê	^ËRØ8ÉèN¹ÛÎÉÛ‚"Â.Ê;ÎØÈÎÈ‰‚şØk^Èº«yÎÊ	Â"Â.È‰«ˆ’%ÒÀĞ¢'6V7F÷'2#¢².Øk^Èºôd42şÉÈNÈK"Â.Øk^ÈºÉê^»˜B"Â.ÉÈNÈKØk^Èº%ÒÀĞ¢ÒÀĞ¢°Ğ¢'6÷W&6R#¢$fVFW&Â&Vv—7FW"d42"ÀĞ¢'F—FÆR#¢%&ö†–&—F–ær–×÷'FF–öâæBÖ&¶WF–æröb&Wf–÷W6Ç’WF†÷&—¦VB6÷fW&VB6öÖ×Væ–6F–öç2WV—ÖVçBFFVBFòF†R6÷fW&VBÆ—7B"ÀĞ¢&÷&–v–æÅ÷F—FÆR#¢%&ö†–&—F–ær–×÷'FF–öâæBÖ&¶WF–æröb&Wf–÷W6Ç’WF†÷&—¦VB6÷fW&VB6öÖ×Væ–6F–öç2WV—ÖVçBFFVBFòF†R6÷fW&VBÆ—7B"ÀĞ¢&Æ–æ²#¢&‡GG3¢ò÷wwræfVFW&Ç&Vv—7FW"æv÷böFö7VÖVçG2ó##bóróbó##bÓ3S‚÷&ö†–&—F–ærÖ–×÷'FF–öâÖæBÖÖ&¶WF–ærÖöb×&Wf–÷W6Ç’ÖWF†÷&—¦VBÖ6÷fW&VBÖ6öÖ×Væ–6F–öç2ÖWV—ÖVçB"ÀĞ¢&–×÷'Fæ6R#¢.È8"ÀĞ¢'7FGW2#¢.Ù™^Ê	R"ÀĞ¢'V&Æ—6†VEö·7B#¢###bÓrÓeC“££³“£"ÀĞ¢&ÖF6†VB#¢²&f65öFV6—6–öåöæ÷F–6R#¢²&6÷fW&VBÆ—7B"Â&æF–öæÂ6V7W&—G’"Â'&ö†–&—B"Â'V&Æ–2æ÷F–6R%×ÒÀĞ¢&–×7G2#¢².ºzNËiÌ+~ºxÊxL+~ÙˆN«ˆÙÙºhB"Â.È‰«ˆ’"Â.È¹Î«NÙÂ%ÒÀĞ¢'F‡2#¢².Ê	^ËRØ8ÉèN¹ÛÎÉÛ‚"Â.«;^«ˆºyÒ"Â.»ºYË+NÉÛ‚"Â.È‰«ˆ’%ÒÀĞ¢'6V7F÷'2#¢².Øk^ÈºÉê^»˜B"Â.ÉÈNÈKØk^Èº"Â.¸JNØ«É¸ÎØÂÉê^»˜B%ÒÀĞ¢ÒÀĞ¢ĞĞ¢„õUEôD•"ò&¶‡5÷öÆ–7•÷vF6…öÆW'G2æ§6öâ"’çw&—FU÷FW‡B€Ğ¢§6öâæGV×2†ÆW'G2ÂVç7W&Uö66–“ÔfÇ6RÂ–æFVçCÓ"’²%Æâ"ÀĞ¢Væ6öF–æsÒ'WFbÓ‚"ÀĞ¢Ğ Ğ Ğ¦FVb76W'E÷öÆ–7•ö÷WGWB‚’ÓâæöæS ¢&öG•÷F‚ÒõUEôD•"ò&¶‡5÷öÆ–7•÷vF6…öÆW'BæÖB Ğ¢–bæ÷B&öG•÷F‚æW†—7G2‚“ Ğ¢&—6R76W'F–öäW'&÷"‚'öÆ–7’ÆW'B&öG’v2&VÖ÷fVBVæW‡V7FVFÇ’"Ğ¢&öG’Ò&öG•÷F‚ç&VE÷FW‡B†Væ6öF–æsÒ'WFbÓ‚×6–r"Ğ¢Æ–æW2Ò&öG’ç7Æ—FÆ–æW2‚Ğ Ğ¢×W7Eö6öçF–âÒ°¢$d42Â»;NÉX‚ÉÈNÙy‚Øk^ÈºÉê^»˜BÈ‰Éè\+~ØÉºzBÊ	ÎÙYÂÊË
‚«;^ÙÂ"À¢"ÒÙ[^ÈºÃ¢"À¢"ÒËiÎË)ƒ¢"À¢Ğ¢f÷"Ö&¶W"–â×W7Eö6öçF–ã Ğ¢–bÖ&¶W"æ÷B–â&öG“ Ğ¢&—6R76W'F–öäW'&÷"†b&Ö—76–ær6ö×7BFVÆVw&ÒÖ&¶W#¢¶Ö&¶W'Ò"Ğ Ğ¢f÷&&–FFVâÒ°Ğ¢"ÒÉ¹Ê	Ã¢"ÀĞ¢"ÒÈ8Ø9Â»8Ù™C¢"ÀĞ¢"ÒÊhÈ¹ÂË+NØÃ¢"ÀĞ¢%WF—F–öâf÷"&V6öç6–FW&F–öâ"ÀĞ¢%&ö†–&—F–ær–×÷'FF–öâæBÖ&¶WF–ær"ÀĞ¢%&Wf–÷W6Ç’WF†÷&—¦VB6÷fW&VB6öÖ×Væ–6F–öç2WV—ÖVçB"ÀĞ¢.ÉÛ»(NØK"ÀĞ¢&–çfW'FW""ÀĞ¢.Èºº+É›Èº"À¢&f65öFV6—6–öåöæ÷F–6R"À¢$´…2"À¢"22â"À¢"ÒØŠÎÉé«HÊ	¢"À¢"ÒØŠÎÉéÉˆÙjS¢"À¢"ÒØŠÎÉéØúÎÉÛØ«ƒ¢"À¢"ÒÙYÎ«ZŞÉêRÉˆÙjS¢"À¢"ÒÙYÎ«ZŞÉêS¢"À¢"ÒÉˆÙjRÈKØK¢"À¢"ÒÉÙÈ*Î«+Ê	RÉˆÙjS¢"À¢"Ò»	Éˆş»	¸È¢"À¢"ÒÈºNØÊ‚ÈºÙ‹ƒ¢"À¢$7F–öç3¢"À¢$—77VW3¢"À¢Ğ¢Æ÷rÒ&öG’æÆ÷vW"‚Ğ¢f÷"Ö&¶W"–âf÷&&–FFVã Ğ¢†—7F6²ÒÆ÷r–bÖ&¶W"æ—6Æ÷vW"‚’VÇ6R&öGĞ¢æVVFÆRÒÖ&¶W"–bÖ&¶W"æ—6Æ÷vW"‚’VÇ6RÖ&¶W Ğ¢–bæVVFÆR–â†—7F6³ Ğ¢&—6R76W'F–öäW'&÷"†b&f÷&&–FFVâFVÆVw&ÒFW‡BÆV¶VC¢¶Ö&¶W'Ò"Ğ Ğ¢ÆöæuöÆ–æW2Ò¶Æ–æRf÷"Æ–æR–âÆ–æW2–bÆVâ†Æ–æR’â¶‡5÷FVÆVw&ÕöFVÆ—fW'•öwV&BäÔ…ô$ôE•ôÄ”äUô4„%5ĞĞ¢–bÆöæuöÆ–æW3 Ğ¢&—6R76W'F–öäW'&÷"†b&÷fW&ÆöærFVÆVw&ÒÆ–æRÆV¶VC¢¶ÆöæuöÆ–æW5³Õ³£#×Ò"Ğ Ğ¢ÆW'Eö6÷VçBÒ7VÒƒf÷"Æ–æR–âÆ–æW2–bÆ–æRç7F'G7v—F‚‚#â²"’¢–bÆW'Eö6÷VçBÒ ¢&—6R76W'F–öäW'&÷"†b&W‡V7FVBöæÇ’öæRFVÆ—fW&VBÆW'BÂv÷B¶ÆW'Eö6÷VçGÒ"¢F—FÆRÒ„õUEôD•"ò&¶‡5÷öÆ–7•÷vF6…öÆW'E÷F—FÆRçG‡B"’ç&VE÷FW‡B†Væ6öF–æsÒ'WFbÓ‚×6–r"¢–bF—FÆRç7F'G7v—F‚‚$´…2"“ ¢&—6R76W'F–öäW'&÷"‚$´…2'&æF–ær&VÖ–æVB–âF†Rf–æÂFVÆVw&ÒF—FÆR"¢f÷&ÖEöW'&÷'2Ò¶‡5÷öÆ–7•÷FVÆVw&Õöf÷&ÖGFW"çfÆ–FFUöf–æÅ÷öÆ–7•öÖW76vR‡F—FÆRÂ&öG’¢–bf÷&ÖEöW'&÷'3 ¢&—6R76W'F–öäW'&÷"†b&vVæW&ÂöÆ–7’f–æÂf÷&ÖBf–ÆVC¢¶f÷&ÖEöW'&÷'7Ò"¢76W'Eö6ö×7E÷&÷6UöÆ–Ö—B†&öG’Â&vVæW&ÂöÆ–7’" Ğ Ğ¦–bõöæÖUõòÓÒ%õöÖ–åõò# Ğ¢&—6R7—7FVÔW†—B†Ö–â‚’Ğ