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
import khs_policy_alert_guardrails
import khs_policy_alert_router
import khs_domestic_stablecoin_policy_watch
import khs_policy_runtime_patch
import khs_policy_seen_finalize
import khs_policy_watch
import khs_telegram_delivery_guard
import khs_trusted_policy_news_watch


OUT_DIR = Path("out")
POLICY_FILES = [
    OUT_DIR / "khs_policy_watch_alerts.json",
    OUT_DIR / "khs_policy_watch_alert.md",
    OUT_DIR / "khs_policy_watch_alert_title.txt",
    OUT_DIR / "khs_policy_watch.md",
]
ROOT = Path(__file__).resolve().parents[1]
POLICY_WORKFLOW = ROOT / ".github" / "workflows" / "khs-policy-watch.yml"


def main() -> int:
    OUT_DIR.mkdir(exist_ok=True)
    assert_workflow_delivery_dedupe()
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
    assert_trusted_policy_news_story_fingerprint_allows_intraday_updates()
    assert_trusted_policy_news_render_is_compact()
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
    ]
    for marker in required:
        if marker not in workflow:
            raise AssertionError(f"KHS policy workflow missing Telegram delivery dedupe marker: {marker}")
    send_index = workflow.index("- name: Send Telegram alert")
    finalize_index = workflow.index("- name: Finalize policy seen state after confirmed Telegram outcome")
    if finalize_index <= send_index:
        raise AssertionError("KHS policy seen state is finalized before Telegram delivery")


def article_fixture(title: str, body: str, published: str = "2026-07-20T12:00:00-04:00") -> str:
    return f"""
    <html><head>
      <meta property="og:title" content="{title}">
      <meta property="article:published_time" content="{published}">
    </head><body><main><div class="entry-content">
      <h1>{title}</h1>
      <p>{body}</p>
      <p>{body}</p>
    </div></main></body></html>
    """


def assert_whitehouse_detail_body_is_verified() -> None:
    title = (
        "Fact Sheet: President Donald J. Trump Secures Americaâ€™s Defense Supply "
        "Chains and Ensures Domestic Acquisition of Critical Materials"
    )
    body = (
        "The Executive Order limits waivers for critical materials from covered nations, "
        "requires comprehensive supply chain mapping, and directs qualification of new "
        "domestic and partner nation sources for national security procurement."
    )
    detail = khs_article_detail.extract_article_detail(article_fixture(title, body), title)
    if not detail.get("body_verified") or not detail.get("title_aligned"):
        raise AssertionError(f"White House detail page was not title/body verified: {detail}")
    mismatched = khs_article_detail.extract_article_detail(
        article_fixture("Unrelated ceremonial announcement", body),
        title,
    )
    if mismatched.get("body_verified"):
        raise AssertionError("White House title/body mismatch passed detail verification")


def verified_whitehouse_item(title: str, body: str, link: str) -> dict:
    return {
        "source": "White House fact sheets",
        "title": title,
        "source_title": title,
        "source_abstract": body,
        "source_body": body,
        "summary": body,
        "link": link,
        "published_kst": "2026-07-20T00:00:00+09:00",
        "body_verified": True,
    }


def assert_whitehouse_current_policy_profiles_are_specific() -> None:
    cases = [
        (
            "Fact Sheet: President Donald J. Trump Secures Americaâ€™s Defense Supply Chains and Ensures Domestic Acquisition of Critical Materials",
            "The Executive Order limits waivers for critical materials from covered nations, requires supply chain mapping, and qualifies domestic sources and partner nation sources. Related: historic defense investment from NATO allies.",
            "https://www.whitehouse.gov/fact-sheets/2026/07/fact-sheet-president-donald-j-trump-secures-americas-defense-supply-chains-and-ensures-domestic-acquisition-of-critical-materials/",
            "ë°±ì•…ê´€, ë¯¸ ë°©ì‚° í•µì‹¬ì†Œì¬ ê³µê¸‰ë§ì˜ ì ì„±êµ­ ì˜ì¡´ ì¶•ì†Œ í–‰ì •ëª…ë ¹",
            "ê³µê¸‰ë§ ì „ìˆ˜ì§€ë„",
        ),
        (
            "Fact Sheet: President Donald J. Trump Takes Action Against Canadaâ€™s Discriminatory Trade Policies",
            "Under section 338 the President imposes additional tariffs on Canada. The 50 percent tariff covers cars, alcohol and dairy and takes effect in 30 days.",
            "https://www.whitehouse.gov/fact-sheets/2026/07/fact-sheet-canada-section-338-tariffs/",
            "ë°±ì•…ê´€, ìºë‚˜ë‹¤ ìë™ì°¨Â·ì£¼ë¥˜Â·ìœ ì œí’ˆ ë“±ì— ì¶”ê°€ 50% ê´€ì„¸",
            "ì„œëª… 30ì¼ ë’¤",
        ),
        (
            "Fact Sheet: President Donald J. Trump Secures a Historic Trade Deal with Jordan",
            "The agreement on reciprocal trade with Jordan preserves duty-free access. Royal Jordanian will purchase six Boeing 787-9 aircraft for 1.4 billion dollars and Hikma will invest 1 billion dollars.",
            "https://www.whitehouse.gov/fact-sheets/2026/07/fact-sheet-trade-deal-with-jordan/",
            "ë°±ì•…ê´€, ìš”ë¥´ë‹¨ê³¼ ìƒí˜¸ë¬´ì—­í˜‘ì • ë°œí‘œ",
            "14ì–µë‹¬ëŸ¬",
        ),
        (
            "Fact Sheet: President Donald J. Trump Takes Further Action To Adjust Imports Of Aluminum Into The United States",
            "The section 232 program requests onshoring plans for primary aluminum. Approved companies building or expanding a smelter may import at half the otherwise applicable tariff rate.",
            "https://www.whitehouse.gov/fact-sheets/2026/07/fact-sheet-president-donald-j-trump-takes-further-action-to-adjust-imports-of-aluminum-into-the-united-states/",
            "ë°±ì•…ê´€, ë¯¸êµ­ ì•Œë£¨ë¯¸ëŠ„ ì œë ¨ íˆ¬ìê¸°ì—…ì— 232ì¡° ê´€ì„¸ ì ˆë°˜ ì ìš© ì¶”ì§„",
            "ê¸°ì¡´ 232ì¡° ì„¸ìœ¨ì˜ ì ˆë°˜",
        ),
    ]
    rendered_alerts = []
    for title, body, link, expected_title, expected_core in cases:
        item = verified_whitehouse_item(title, body, link)
        classified = khs_policy_watch.classify_item(item)
        if not classified:
            raise AssertionError(f"verified White House policy was not classified: {title}")
        khs_policy_alert_router.apply_router_overrides(classified)
        khs_policy_alert_guardrails.ensure_explained(classified)
        if classified.get("title_ko") != expected_title:
            raise AssertionError(
                f"White House profile title mismatch: {classified.get('title_ko')} != {expected_title}"
            )
        if expected_core not in str(classified.get("policy_plain_summary") or ""):
            raise AssertionError(
                f"White House profile summary mismatch: {classified.get('policy_plain_summary')}"
            )
        rendered_alerts.append(classified)
    rendered = khs_policy_alert_router.render_policy_report(
        rendered_alerts,
        dt.datetime(2026, 7, 23, 18, 0, tzinfo=ZoneInfo("Asia/Seoul")),
    )
    for _title, _body, _link, expected_title, _core in cases:
        if expected_title not in rendered:
            raise AssertionError(f"White House Korean title missing from compact render: {expected_title}")
    if "Fact Sheet: President" in rendered:
        raise AssertionError("White House raw English heading leaked into Telegram render")


def assert_whitehouse_fact_sheet_is_preferred_for_duplicate_story() -> None:
    fingerprint = "canada-story"
    proclamation = {
        "source": "White House proclamations",
        "title": "Imposing Additional Duties With Respect to Motor Vehicles",
        "link": "https://www.whitehouse.gov/presidential-actions/canada-motor-vehicles/",
        "fingerprint": fingerprint,
        "wh×}üæÚ$z{-®éÜj×F6…öÆW'BæÖB Ğ¢F—FÆU÷F‚çw&—FU÷FW‡B‚$´…2Ê	^ËRÉ¸ÎË™ƒ¢¾È8Ò«ZŞ¸+B¹INÊxØKÉéÈ+Ê	^ËRÊI»;RØXÎÈªNØ«…Æâ"ÂVæ6öF–æsÒ'WFbÓ‚"Ğ¢&öG•÷F‚çw&—FU÷FW‡B€Ğ¢%Æâ"æ¦ö–â…°Ğ¢/	ùª‚´…2Ê	^Ë\+~«yÎÊ	Â«:Ëj«*’É¸ÎË™‚+r##n¸XB~É¹BnÉÛÂ##£Rµ5B"ÀĞ¢""ÀĞ¢"22â¾È8+~Ù™^Ê	UÒ«ZŞ¸+B¹INÊxØKÉéÈ+Ê	^ËS¢ÈªNØXÎÉÛN»‰NËÙNÉÛ‚Éˆ«ˆ‚¸ÈË+L+~ÊH»˜NÉéÈ+«yÎÊ	ÂË+NØÂ"ÀĞ¢"ÒÙ[^ÈºÃ¢É¹Ù™BÈªNØXÎÉÛN»‰NËÙNÉÛŒ+~¹INÊxØKÉéÈ+Éè^»)^ÉØ«ˆÉËRÉÛÙHN¹ÛÂÉêÎØë‚ÉÛNÈ¨Éè^¸¸¸ºBâ"ÀĞ¢"ÒÉÙÈ*Î«+Ê	RÉˆÙjS¢È¹Î«NÙÂÂÈ‰«ˆ’Â»ºYÉyÉÛNÈY‚şÙZÉÛÉÊ‚"ÀĞ¢"ÒØŠÎÉéÉˆÙjS¢Êx«ˆ‚»i¸©BÉé«ˆÉØÈºNÊ»;N¸ºBºû¹é‚«+Ê	ÂÙÎÊH»*ØÈ^Éè^¸¸¸ºBâ"ÀĞ¢"ÒÙYÎ«ZŞÉêS¢ÉØÙh’ÂÙXØXÎØÂÂ«+Ê	ÂÂ«È8ÉéÈ+«¹éÈhÎº[Â»H^¸¸¸ºBâ"ÀĞ¢"Ò»	Éˆ«¸ª^ÈK¢ÊI«Bâ"ÀĞ¢"ÒÈºNØÊ‚ÈºÙ‹ƒ¢»	ÎÙh’Ê;ÎË+N«Ê(«(ÂÊ	ÎÙYÎ¹	º›BØXÎºx‚Ù™^È+ÉÛBÉ[ŞÙ[NÊy¸¸¸ºBâ"ÀĞ¢"ÒËiÎË)ƒ¢´&æ²öb¶÷&VF–v—FÂ7W'&Væ7’öÆ–7•Ò†‡GG3¢ò÷wwræ&ö²æ÷"æ·"ö’+rÊÙ¨Â##£Rµ5B"ÀĞ¢""ÀĞ¢"22"â¾È8+~Ù™^Ê	UÒ«ZŞ¸+B¹INÊxØKÉéÈ+Ê	^ËS¢ÈªNØXÎÉÛN»‰NËÙNÉÛ‚Éˆ«ˆ‚¸ÈË+L+~ÊH»˜NÉéÈ+«yÎÊ	ÂË+NØÂ"ÀĞ¢"ÒÙ[^ÈºÃ¢É¹Ù™BÈªNØXÎÉÛN»‰NËÙNÉÛŒ+~¹INÊxØKÉéÈ+Éè^»)^ÉØ«ˆÉËRÉÛÙHN¹ÛÂÉêÎØë‚ÉÛNÈ¨Éè^¸¸¸ºBâ"ÀĞ¢"ÒÉÙÈ*Î«+Ê	RÉˆÙjS¢È¹Î«NÙÂÂÈ‰«ˆ’Â»ºYÉyÉÛNÈY‚şÙZÉÛÉÊ‚"ÀĞ¢"ÒØŠÎÉéÉˆÙjS¢Êx«ˆ‚»i¸©BÉé«ˆÉØÈºNÊ»;N¸ºBºû¹é‚«+Ê	ÂÙÎÊH»*ØÈ^Éè^¸¸¸ºBâ"ÀĞ¢"ÒÙYÎ«ZŞÉêS¢ÉØÙh’ÂÙXØXÎØÂÂ«+Ê	ÂÂ«È8ÉéÈ+«¹éÈhÎº[Â»H^¸¸¸ºBâ"ÀĞ¢"Ò»	Éˆ«¸ª^ÈK¢ÊI«Bâ"ÀĞ¢"ÒÈºNØÊ‚ÈºÙ‹ƒ¢»	ÎÙh’Ê;ÎË+N«Ê(«(ÂÊ	ÎÙYÎ¹	º›BØXÎºx‚Ù™^È+ÉÛBÉ[ŞÙ[NÊy¸¸¸ºBâ"ÀĞ¢"ÒËiÎË)ƒ¢´&æ²öb¶÷&V–ÖVçB&W6V&6…Ò†‡GG3¢ò÷wwræ&ö²æ÷"æ·"ö"’+rÊÙ¨Â##£Rµ5B"ÀĞ¢""ÀĞ¢Ò’ÀĞ¢Væ6öF–æsÒ'WFbÓ‚"ÀĞ¢Ğ¢¶‡5÷FVÆVw&ÕöFVÆ—fW'•öwV&BæÖ–â‚Ğ¢–b&öG•÷F‚æW†—7G2‚“ Ğ¢&—6R76W'F–öäW'&÷"‚&FVÆ—fW'’wV&BF–Bæ÷B&Æö6²GWÆ–6FRöÆ–7’ÆW'G2"Ğ Ğ Ğ¦FVb76W'EöFVÆ—fW'•öwV&Eö&Æö6·5÷6÷W&6Uö&öG•öÖ—6ÖF6‚‚’ÓâæöæS Ğ¢6ÆVçW‚Ğ¢F—FÆU÷F‚ÒõUEôD•"ò&¶‡5÷öÆ–7•÷vF6…öÆW'E÷F—FÆRçG‡B Ğ¢&öG•÷F‚ÒõUEôD•"ò&¶‡5÷öÆ–7•÷vF6…öÆW'BæÖB Ğ¢F—FÆRÒ$´…2Ê	^ËRÉ¸ÎË™ƒ¢¾È8Òd42ÂØk^Èº+~Ê;ÎØÈÎÈ‰Œ+~ÉÈNÈK«yÎÊ	ÂºËÈIÂ«;^ÙÅÆâ Ğ¢&WV—&VEöÆ–æW2Ò&WV—&VEöW‡ÆæF–öåöÆ–æW2‚$d42–çfW'FW"öÆ–7’&Vw&W76–öâ6†V6²"Ğ¢&öG’Ò%Æâ"æ¦ö–â…°Ğ¢$´…2öÆ–7’vF6‚6÷W&6Rö&öG’Ö—6ÖF6‚&Vw&W76–öâ"ÀĞ¢""ÀĞ¢"22â¾È8+~Ù™^Ê	UÒd42ÂØk^Èº+~Ê;ÎØÈÎÈ‰Œ+~ÉÈNÈK«yÎÊ	ÂºËÈIÂ«;^ÙÂ"ÀĞ¢"ÒÙ[^ÈºÃ¢ºû«ZÒd4>«É›«ZŞÈ+Éy¸HÊxÉÛ»(NØKÊ	ÎÙYÎÉØB«(ØjÙYÎ¸ºN¸©B»;ºËÉè^¸¸¸ºBâ"ÀĞ¢§&WV—&VEöÆ–æW2ÀĞ¢"ÒËiÎË)ƒ¢¾ºû‚$ôTÕÒ†‡GG3¢ò÷wwræ&öVÒæv÷böæWw7&ööÒ÷&W72×&VÆV6W2ö&öVÒÖ–æ—F–FW2Öf—'7B×7FWÖW‡Æ÷&R×÷FVçF–ÂÖ÷WFW"Ö6öçF–æVçFÂ×6†VÆb×76R’+rÊÙ¨Â#3£Rµ5B"ÀĞ¢""ÀĞ¢ÒĞ¢F—FÆU÷F‚çw&—FU÷FW‡B‡F—FÆRÂVæ6öF–æsÒ'WFbÓ‚"Ğ¢&öG•÷F‚çw&—FU÷FW‡B†&öG’ÂVæ6öF–æsÒ'WFbÓ‚"Ğ¢&V6öâÒ¶‡5÷FVÆVw&ÕöFVÆ—fW'•öwV&Bæ†5÷6÷W&6Uö&öG•öÖ—6ÖF6‚‡F—FÆRÂ&öG’Ğ¢–b&V6öâÒ&&öVÕ÷6÷W&6U÷v—F…öf65ö&öG’# Ğ¢&—6R76W'F–öäW'&÷"†b'6÷W&6Rö&öG’Ö—6ÖF6‚v2æ÷BFWFV7FVC¢·&V6öçÒ"Ğ¢¶‡5÷FVÆVw&ÕöFVÆ—fW'•öwV&BæÖ–â‚Ğ¢–b&öG•÷F‚æW†—7G2‚“ Ğ¢&—6R76W'F–öäW'&÷"‚&FVÆ—fW'’wV&BF–Bæ÷B&Æö6²$ôTÒ6÷W&6Rv—F‚d42&öG’"Ğ Ğ Ğ¦FVb76W'EöFVÆ—fW'•öwV&Eö&Æö6·5öf65÷7V&Ö&–æUö–çfW'FW%öÖ—6ÖF6‚‚’ÓâæöæS Ğ¢6ÆVçW‚Ğ¢F—FÆU÷F‚ÒõUEôD•"ò&¶‡5÷öÆ–7•÷vF6…öÆW'E÷F—FÆRçG‡B Ğ¢&öG•÷F‚ÒõUEôD•"ò&¶‡5÷öÆ–7•÷vF6…öÆW'BæÖB Ğ¢F—FÆRÒ$´…2Ê	^ËRÉ¸ÎË™ƒ¢¾È8Òd42ÂØk^Èº+~Ê;ÎØÈÎÈ‰Œ+~ÉÈNÈK«yÎÊ	ÂºËÈIÂ«;^ÙÅÆâ Ğ¢&WV—&VEöÆ–æW2Ò&WV—&VEöW‡ÆæF–öåöÆ–æW2‚$d427V&Ö&–æR6&ÆRö–çfW'FW"Ö—6ÖF6‚&Vw&W76–öâ6†V6²"Ğ¢&öG’Ò%Æâ"æ¦ö–â…°Ğ¢/	ùª‚´…2Ê	^Ë\+~«yÎÊ	Â«:Ëj«*’É¸ÎË™‚+r##n¸XB~É¹BÉÛÂS£‚µ5B"ÀĞ¢""ÀĞ¢"22â¾È8+~Ù™^Ê	UÒd42ÂØk^Èº+~Ê;ÎØÈÎÈ‰Œ+~ÉÈNÈK«yÎÊ	ÂºËÈIÂ«;^ÙÂ"ÀĞ¢"ÒÙ[^ÈºÃ¢ºû«ZÒd4>««ZŞ«ÉX»;BÉ«º
Nº[ÂÉÛNÉÊºÂÉ›«ZŞÈ+¹‰¸©BÊI«ZŞÈ+Éy¸HÊxÉÛ»(NØKÈº«yÂÈ‰ÉèRÊ	ÎÙYÌ+~«ˆÊxÊË™º[Â«(ØjÊIÉÛN¹ÛÎ¸©B¸+NÉªÉè^¸¸¸ºBâ"ÀĞ¢§&WV—&VEöÆ–æW2ÀĞ¢"ÒËiÎË)ƒ¢¾ºû‚É{»
«H»;Bd45Ò†‡GG3¢ò÷wwræfVFW&Ç&Vv—7FW"æv÷böFö7VÖVçG2ó##bóró‚ó##bÓ3scR÷&Wf–WrÖöb×7V&Ö&–æRÖ6&ÆRÖÆæF–ærÖÆ–6Vç6R×'VÆW2ÖæB×&ö6VGW&W2×FòÖ76W72ÖWföÇf–ærÖæF–öæÂ×6V7W&—G’’+rÊÙ¨ÂS£‚µ5B"ÀĞ¢""ÀĞ¢ÒĞ¢F—FÆU÷F‚çw&—FU÷FW‡B‡F—FÆRÂVæ6öF–æsÒ'WFbÓ‚"Ğ¢&öG•÷F‚çw&—FU÷FW‡B†&öG’ÂVæ6öF–æsÒ'WFbÓ‚"Ğ¢&V6öâÒ¶‡5÷FVÆVw&ÕöFVÆ—fW'•öwV&Bæ†5÷6÷W&6Uö&öG•öÖ—6ÖF6‚‡F—FÆRÂ&öG’Ğ¢W‡V7FVBÒ&f65÷7V&Ö&–æUö6&ÆU÷6÷W&6U÷v—F…ö–çfW'FW%ö÷%öWV—ÖVçEö&åö&öG’ Ğ¢–b&V6öâÒW‡V7FVC Ğ¢&—6R76W'F–öäW'&÷"†b$d427V&Ö&–æR÷6÷W&6R&öG’Ö—6ÖF6‚v2æ÷BFWFV7FVC¢·&V6öçÒ"Ğ¢¶‡5÷FVÆVw&ÕöFVÆ—fW'•öwV&BæÖ–â‚Ğ¢–b&öG•÷F‚æW†—7G2‚“ Ğ¢&—6R76W'F–öäW'&÷"‚&FVÆ—fW'’wV&BF–Bæ÷B&Æö6²d427V&Ö&–æR6&ÆR6÷W&6Rv—F‚–çfW'FW"&öG’"Ğ Ğ Ğ¦FVb76W'EöFVÆ—fW'•öwV&Eö&Æö6·5ö&öµövVæW&–5÷7F&ÆV6ö–åöÖ—6ÖF6‚‚’ÓâæöæS Ğ¢6ÆVçW‚Ğ¢F—FÆU÷F‚ÒõUEôD•"ò&¶‡5÷öÆ–7•÷vF6…öÆW'E÷F—FÆRçG‡B Ğ¢&öG•÷F‚ÒõUEôD•"ò&¶‡5÷öÆ–7•÷vF6…öÆW'BæÖB Ğ¢F—FÆRÒ$´…2Ê	^ËRÉ¸ÎË™ƒ¢¾È8Ò«ZŞ¸+B¹INÊxØKÉéÈ+Ê	^ËS¢ÈªNØXÎÉÛN»‰NËÙNÉÛ‚Éˆ«ˆ‚¸ÈË+L+~ÊH»˜NÉéÈ+«yÎÊ	ÂË+NØÅÆâ Ğ¢&WV—&VEöÆ–æW2Ò&WV—&VEöW‡ÆæF–öåöÆ–æW2‚$$ô²vVæW&–2vR÷7F&ÆV6ö–âÖ—6ÖF6‚&Vw&W76–öâ6†V6²"Ğ¢&öG’Ò%Æâ"æ¦ö–â…°Ğ¢/	ùª‚´…2Ê	^Ë\+~«yÎÊ	Â«:Ëj«*’É¸ÎË™‚+r##n¸XB~É¹BÉÛÂ#£2µ5B"ÀĞ¢""ÀĞ¢"22â¾È8+~Ù™^Ê	UÒ«ZŞ¸+B¹INÊxØKÉéÈ+Ê	^ËS¢ÈªNØXÎÉÛN»‰NËÙNÉÛ‚Éˆ«ˆ‚¸ÈË+L+~ÊH»˜NÉéÈ+«yÎÊ	ÂË+NØÂ"ÀĞ¢"ÒÙ[^ÈºÃ¢É¹Ù™BÈªNØXÎÉÛN»‰NËÙNÉÛŒ+~¹INÊxØKÉéÈ+Éè^»)^ÉØ»	ÎÙh’Ê;ÎË+BÂÊH»˜NÉéÈ+ÂÊx«ˆ«+Ê	ÂÙÎÊHÉØB¹¹úÎÈ»Â«ˆÉËRÉÛÙHN¹ÛÂÉêÎØë‚ÉÛNÈ¨Éè^¸¸¸ºBâ"ÀĞ¢§&WV—&VEöÆ–æW2ÀĞ¢"ÒËiÎË)ƒ¢´&æ²öb¶÷&VF–v—FÂ7W'&Væ7’öÆ–7•Ò†‡GG3¢ò÷wwræ&ö²æ÷"æ·"÷÷'FÂ÷7V&Ö–â÷7V&Ö–âöfææ56fWG’æFóöÖVçTæóÓ#cS"’+rÊÙ¨Â#£2µ5B"ÀĞ¢""ÀĞ¢ÒĞ¢F—FÆU÷F‚çw&—FU÷FW‡B‡F—FÆRÂVæ6öF–æsÒ'WFbÓ‚"Ğ¢&öG•÷F‚çw&—FU÷FW‡B†&öG’ÂVæ6öF–æsÒ'WFbÓ‚"Ğ¢&V6öâÒ¶‡5÷FVÆVw&ÕöFVÆ—fW'•öwV&Bæ†5÷6÷W&6Uö&öG•öÖ—6ÖF6‚‡F—FÆRÂ&öG’Ğ¢W‡V7FVBÒ&&öµövVæW&–5÷vU÷v—F…÷7F&ÆV6ö–å÷öÆ–7•ö&öG’ Ğ¢–b&V6öâÒW‡V7FVC Ğ¢&—6R76W'F–öäW'&÷"†b$$ô²vVæW&–2÷6÷W&6R&öG’Ö—6ÖF6‚v2æ÷BFWFV7FVC¢·&V6öçÒ"Ğ¢¶‡5÷FVÆVw&ÕöFVÆ—fW'•öwV&BæÖ–â‚Ğ¢–b&öG•÷F‚æW†—7G2‚“ Ğ¢&—6R76W'F–öäW'&÷"‚&FVÆ—fW'’wV&BF–Bæ÷B&Æö6²$ô²vVæW&–2vRv—F‚7F&ÆV6ö–âöÆ–7’&öG’"Ğ Ğ Ğ¦FVb76W'EöFVÆ—fW'•öwV&Eö&Æö6·5÷W&Å÷F÷–5öÖ—76–ær‚’ÓâæöæS Ğ¢66W2Ò°Ğ¢€Ğ¢$´…2Ê	^ËRÉ¸ÎË™ƒ¢¾È8ÒØ«¹ûÎÙHB¸ÈØk^º’»	ÎÉk‚ÂÈ¹ÎÉêRÉˆÙjRÊ	^ËRÈºÙ‹…Æâ"ÀĞ¢.Ø«¹ûÎÙHB¸ÈØk^ºÉÙ‚ÊxÊ	»	ÎÉkÉÛB«HÈK‚Â»	¸øNË+BÂÉÛN¹èÊNÉøÉÈNÙyÉØBÉ¸ÊxÉÛÂÈ‰‚Éè¸ºN¸©BÉÛÎ»	‚ØYÎÙHÎºkşÉè^¸¸¸ºBâ"ÀĞ¢&‡GG3¢ò÷wwrçv†—FV†÷W6Ræv÷böf7B×6†VWG2ó##bóröf7B×6†VWB×&W6–FVçBÖFöæÆBÖ¢×G'V××6V7W&W2Ö†—7F÷&–2ÖFVfVç6RÖ–çfW7FÖVçBÖg&öÒÖæFòÖÆÆ–W2×÷vW&–ærÖÖW&–6âÖ–æGW7G'’ò"ÀĞ¢'6÷W&6U÷F÷–5öÖ—76–æs¦æFõöFVfVç6Uö–çfW7FÖVçB"ÀĞ¢’ÀĞ¢€Ğ¢$´…2Ê	^ËRÉ¸ÎË™ƒ¢¾È8Òd42ÂØk^Èº+~Ê;ÎØÈÎÈ‰Œ+~ÉÈNÈK«yÎÊ	ÂºËÈIÂ«;^ÙÅÆâ"ÀĞ¢$d42Øk^Èº+~Ê;ÎØÈÎÈ‰Œ+~ÉÈNÈK«yÎÊ	ÂºËÈIÎ¸©BØk^ÈºÉÛÙHN¹ÛÂÊ	^ËRÈ¹Î«NÙÎº[Â»	N«øÈ‰‚Éè¸ºN¸©BÉÛÎ»	‚ØYÎÙHÎºkşÉè^¸¸¸ºBâ"ÀĞ¢&‡GG3¢ò÷wwræfVFW&Ç&Vv—7FW"æv÷böFö7VÖVçG2ó##bóró‚ó##bÓ3scR÷&Wf–WrÖöb×7V&Ö&–æRÖ6&ÆRÖÆæF–ærÖÆ–6Vç6R×'VÆW2ÖæB×&ö6VGW&W2×FòÖ76W72ÖWföÇf–ærÖæF–öæÂ×6V7W&—G’"ÀĞ¢'6÷W&6U÷F÷–5öÖ—76–æs§7V&Ö&–æUö6&ÆR"ÀĞ¢’ÀĞ¢ĞĞ¢f÷"F—FÆRÂ6÷&RÂÆ–æ²ÂW‡V7FVB–â66W3 Ğ¢6ÆVçW‚Ğ¢F—FÆU÷F‚ÒõUEôD•"ò&¶‡5÷öÆ–7•÷vF6…öÆW'E÷F—FÆRçG‡B Ğ¢&öG•÷F‚ÒõUEôD•"ò&¶‡5÷öÆ–7•÷vF6…öÆW'BæÖB Ğ¢&WV—&VEöÆ–æW2Ò&WV—&VEöW‡ÆæF–öåöÆ–æW2‚%U$ÂF÷–2Ö—76–ær&Vw&W76–öâ6†V6²"Ğ¢&öG’Ò%Æâ"æ¦ö–â…°Ğ¢/	ùª‚´…2Ê	^Ë\+~«yÎÊ	Â«:Ëj«*’É¸ÎË™‚+r##n¸XB~É¹BÉÛÂ#£3µ5B"ÀĞ¢""ÀĞ¢"22â¾È8+~Ù™^Ê	UÒËiÎË)‚Ê;ÎÊ	Â¸ˆN¹ÛÒÙ¨Î«xØXÎÈªNØ«‚"ÀĞ¢b"ÒÙ[^ÈºÃ¢¶6÷&WÒ"ÀĞ¢§&WV—&VEöÆ–æW2ÀĞ¢b"ÒËiÎË)ƒ¢¾«;^È¹ÒËiÎË)…Ò‡¶Æ–æ·Ò’+rÊÙ¨Â#£3µ5B"ÀĞ¢""ÀĞ¢ÒĞ¢F—FÆU÷F‚çw&—FU÷FW‡B‡F—FÆRÂVæ6öF–æsÒ'WFbÓ‚"Ğ¢&öG•÷F‚çw&—FU÷FW‡B†&öG’ÂVæ6öF–æsÒ'WFbÓ‚"Ğ¢&V6öâÒ¶‡5÷FVÆVw&ÕöFVÆ—fW'•öwV&Bæ†5÷6÷W&6Uö&öG•öÖ—6ÖF6‚‡F—FÆRÂ&öG’Ğ¢–b&V6öâÒW‡V7FVC Ğ¢&—6R76W'F–öäW'&÷"†b%U$ÂF÷–2Ö—76–ærÖ—6ÖF6‚v2æ÷BFWFV7FVC¢·&V6öçÒÒ¶W‡V7FVGÒ"Ğ¢¶‡5÷FVÆVw&ÕöFVÆ—fW'•öwV&BæÖ–â‚Ğ¢–b&öG•÷F‚æW†—7G2‚“ Ğ¢&—6R76W'F–öäW'&÷"†b&FVÆ—fW'’wV&BF–Bæ÷B&Æö6²U$ÂF÷–2Ö—76–ær66S¢¶W‡V7FVGÒ"Ğ Ğ Ğ¦FVb76W'E÷&÷WFW%öW‡Æ–ç5öf65÷7V&Ö&–æUö6&ÆU÷öÆ–7’‚’ÓâæöæS Ğ¢—FVÒÒ°Ğ¢'6÷W&6R#¢$fVFW&Â&Vv—7FW"d42"ÀĞ¢'F—FÆR#¢%&Wf–Wröb7V&Ö&–æR6&ÆRÆæF–ærÆ–6Vç6R'VÆW2æB&ö6VGW&W2Fò76W72WföÇf–æræF–öæÂ6V7W&—G’"ÀĞ¢&÷&–v–æÅ÷F—FÆR#¢%&Wf–Wröb7V&Ö&–æR6&ÆRÆæF–ærÆ–6Vç6R'VÆW2æB&ö6VGW&W2Fò76W72WföÇf–æræF–öæÂ6V7W&—G’"ÀĞ¢&Æ–æ²#¢&‡GG3¢ò÷wwræfVFW&Ç&Vv—7FW"æv÷böFö7VÖVçG2ó##bóró‚ó##bÓ3scR÷&Wf–WrÖöb×7V&Ö&–æRÖ6&ÆRÖÆæF–ærÖÆ–6Vç6R×'VÆW2ÖæB×&ö6VGW&W2×FòÖ76W72ÖWföÇf–ærÖæF–öæÂ×6V7W&—G’"ÀĞ¢&–×÷'Fæ6R#¢.È8"ÀĞ¢'7FGW2#¢.Ù™^Ê	R"ÀĞ¢'V&Æ—6†VEö·7B#¢###bÓrÓ…C“££³“£"ÀĞ¢&ÖF6†VB#¢²&f65öFV6—6–öåöæ÷F–6R#¢²&æF–öæÂ6V7W&—G’"Â''VÆVÖ¶–ær%×ÒÀĞ¢&–×7G2#¢².È¹Î«NÙÂ"Â.ÙZÉÛÉÊ‚%ÒÀĞ¢'F‡2#¢².Ê	^ËRØ8ÉèN¹ÛÎÉÛ‚"Â.ÙZÉÛÉÊ‚%ÒÀĞ¢'6V7F÷'2#¢².Øk^Èºôd42şÉÈNÈK%ÒÀĞ¢ĞĞ¢Vç&–6†VBÒ¶‡5÷öÆ–7•öÆW'E÷&÷WFW"æVç&–6…öÖ—76–æuö6öçFW‡B†—FVÒĞ¢¶‡5÷öÆ–7•öÆW'E÷&÷WFW"æÇ•÷&÷WFW%ö÷fW'&–FW2†Vç&–6†VBĞ¢F—FÆRÒ¶‡5÷öÆ–7•öÆW'E÷&÷WFW"ç6fU÷F—FÆR†Vç&–6†VBĞ¢f–VÆG2Ò""æ¦ö–â€Ğ¢7G"†Vç&–6†VBævWB†¶W’’÷"""Ğ¢f÷"¶W’–â‚'öÆ–7•÷Æ–å÷7VÖÖ'’"Â&–çfW7FÖVçE÷f–Wr"Â&¶÷&VöÖ&¶WEö–×7B"Â'6V7F÷'2"Ğ¢’æÆ÷vW"‚Ğ¢–b.Ù[NÊËÈÉÛN»‰B"æ÷B–âF—FÆRæB.Ù[NÊØk^ÈºËÈÉÛN»‰B"æ÷B–âf–VÆG3 Ğ¢&—6R76W'F–öäW'&÷"‚$d427V&Ö&–æR6&ÆRöÆ–7’v2æ÷B&÷WFVBFò7V&Ö&–æR6&ÆRW‡ÆæF–öâ"Ğ¢f÷&&–FFVâÒ²&–çfW'FW""Â&VæW&w’–çfW'FW""Â'6öÆ"–çfW'FW""Â.ÉÛ»(NØK"Â.ÊNº
^»8Ù™Éê^Ë™‚%ĞĞ¢f÷"Fö¶Vâ–âf÷&&–FFVã Ğ¢–bFö¶VâæÆ÷vW"‚’–âf–VÆG3 Ğ¢&—6R76W'F–öäW'&÷"†b$d427V&Ö&–æR6&ÆRW‡ÆæF–öâÆV¶VB–çfW'FW"&öG“¢·Fö¶VçÒ"Ğ Ğ Ğ¦FVb6ÆVçW‚’ÓâæöæS Ğ¢f÷"F‚–âôÄ”5•ôd”ÄU3 Ğ¢–bF‚æW†—7G2‚“ Ğ¢F‚çVæÆ–æ²‚Ğ Ğ Ğ¦FVb&WV—&VEöW‡ÆæF–öåöÆ–æW2†æ÷FS¢7G"’ÓâÆ—7E·7G%Ó Ğ¢&WGW&â°Ğ¢b'¶Ö&¶W'5³×Ò¶æ÷FWÒ Ğ¢f÷"Ö&¶W'2–â¶‡5÷FVÆVw&ÕöFVÆ—fW'•öwV&Bå$UT•$TEôU…ÄäD”ôåôd”TÄEôu$õU0Ğ¢ĞĞ Ğ Ğ¦FVbw&—FUöf65÷&Vw&W76–öåöf—‡GW&R‚’ÓâæöæS Ğ¢ÆW'G2Ò°Ğ¢°Ğ¢'6÷W&6R#¢$fVFW&Â&Vv—7FW"d42"ÀĞ¢'F—FÆR#¢%WF—F–öâf÷"&V6öç6–FW&F–öâöb7F–öâ–â'VÆVÖ¶–ær&ö6VVF–ær"ÀĞ¢&÷&–v–æÅ÷F—FÆR#¢%WF—F–öâf÷"&V6öç6–FW&F–öâöb7F–öâ–â'VÆVÖ¶–ær&ö6VVF–ær"ÀĞ¢&Æ–æ²#¢&‡GG3¢ò÷wwræfVFW&Ç&Vv—7FW"æv÷böFö7VÖVçG2ó##bóróbó##bÓ3c÷WF—F–öâÖf÷"×&V6öç6–FW&F–öâÖöbÖ7F–öâÖ–â×'VÆVÖ¶–ær×&ö6VVF–ær"ÀĞ¢&–×÷'Fæ6R#¢.È8"ÀĞ¢'7FGW2#¢.Ù™^Ê	R"ÀĞ¢'V&Æ—6†VEö·7B#¢###bÓrÓeC“££³“£"ÀĞ¢&ÖF6†VB#¢²&f65öFV6—6–öåöæ÷F–6R#¢²'&÷÷6VB'VÆR"Â''VÆVÖ¶–ær%×ÒÀĞ¢&–×7G2#¢².È¹Î«NÙÂ"Â.È‰«ˆ’%ÒÀĞ¢'F‡2#¢².Ê	^ËRØ8ÉèN¹ÛÎÉÛ‚"Â.Ê;ÎØÈÎÈ‰‚şØk^Èº«yÎÊ	Â"Â.È‰«ˆ’%ÒÀĞ¢'6V7F÷'2#¢².Øk^Èºôd42şÉÈNÈK"Â.Øk^ÈºÉê^»˜B"Â.ÉÈNÈKØk^Èº%ÒÀĞ¢ÒÀĞ¢°Ğ¢'6÷W&6R#¢$fVFW&Â&Vv—7FW"d42"ÀĞ¢'F—FÆR#¢%&ö†–&—F–ær–×÷'FF–öâæBÖ&¶WF–æröb&Wf–÷W6Ç’WF†÷&—¦VB6÷fW&VB6öÖ×Væ–6F–öç2WV—ÖVçBFFVBFòF†R6÷fW&VBÆ—7B"ÀĞ¢&÷&–v–æÅ÷F—FÆR#¢%&ö†–&—F–ær–×÷'FF–öâæBÖ&¶WF–æröb&Wf–÷W6Ç’WF†÷&—¦VB6÷fW&VB6öÖ×Væ–6F–öç2WV—ÖVçBFFVBFòF†R6÷fW&VBÆ—7B"ÀĞ¢&Æ–æ²#¢&‡GG3¢ò÷wwræfVFW&Ç&Vv—7FW"æv÷böFö7VÖVçG2ó##bóróbó##bÓ3S‚÷&ö†–&—F–ærÖ–×÷'FF–öâÖæBÖÖ&¶WF–ærÖöb×&Wf–÷W6Ç’ÖWF†÷&—¦VBÖ6÷fW&VBÖ6öÖ×Væ–6F–öç2ÖWV—ÖVçB"ÀĞ¢&–×÷'Fæ6R#¢.È8"ÀĞ¢'7FGW2#¢.Ù™^Ê	R"ÀĞ¢'V&Æ—6†VEö·7B#¢###bÓrÓeC“££³“£"ÀĞ¢&ÖF6†VB#¢²&f65öFV6—6–öåöæ÷F–6R#¢²&6÷fW&VBÆ—7B"Â&æF–öæÂ6V7W&—G’"Â'&ö†–&—B"Â'V&Æ–2æ÷F–6R%×ÒÀĞ¢&–×7G2#¢².ºzNËiÌ+~ºxÊxL+~ÙˆN«ˆÙÙºhB"Â.È‰«ˆ’"Â.È¹Î«NÙÂ%ÒÀĞ¢'F‡2#¢².Ê	^ËRØ8ÉèN¹ÛÎÉÛ‚"Â.«;^«ˆºyÒ"Â.»ºYË+NÉÛ‚"Â.È‰«ˆ’%ÒÀĞ¢'6V7F÷'2#¢².Øk^ÈºÉê^»˜B"Â.ÉÈNÈKØk^Èº"Â.¸JNØ«É¸ÎØÂÉê^»˜B%ÒÀĞ¢ÒÀĞ¢ĞĞ¢„õUEôD•"ò&¶‡5÷öÆ–7•÷vF6…öÆW'G2æ§6öâ"’çw&—FU÷FW‡B€Ğ¢§6öâæGV×2†ÆW'G2ÂVç7W&Uö66–“ÔfÇ6RÂ–æFVçCÓ"’²%Æâ"ÀĞ¢Væ6öF–æsÒ'WFbÓ‚"ÀĞ¢Ğ Ğ Ğ¦FVb76W'E÷öÆ–7•ö÷WGWB‚’ÓâæöæS Ğ¢&öG•÷F‚ÒõUEôD•"ò&¶‡5÷öÆ–7•÷vF6…öÆW'BæÖB Ğ¢–bæ÷B&öG•÷F‚æW†—7G2‚“ Ğ¢&—6R76W'F–öäW'&÷"‚'öÆ–7’ÆW'B&öG’v2&VÖ÷fVBVæW‡V7FVFÇ’"Ğ¢&öG’Ò&öG•÷F‚ç&VE÷FW‡B†Væ6öF–æsÒ'WFbÓ‚×6–r"Ğ¢Æ–æW2Ò&öG’ç7Æ—FÆ–æW2‚Ğ Ğ¢×W7Eö6öçF–âÒ°Ğ¢$d42Â»;NÉX‚ÉÈNÙy‚Øk^ÈºÉê^»˜BÈ‰Éè\+~ØÉºzBÊ	ÎÙYÂÊË
‚«;^ÙÂ"ÀĞ¢"ÒÙ[^ÈºÃ¢"ÀĞ¢"ÒÉÙÈ*Î«+Ê	RÉˆÙjS¢"À¢"ÒØŠÎÉéÉˆÙjS¢"À¢"ÒÙYÎ«ZŞÉêS¢"À¢"Ò»	Éˆş»	¸È¢"À¢"ÒÈºNØÊ‚ÈºÙ‹ƒ¢"À¢"ÒËiÎË)ƒ¢"À¢ĞĞ¢f÷"Ö&¶W"–â×W7Eö6öçF–ã Ğ¢–bÖ&¶W"æ÷B–â&öG“ Ğ¢&—6R76W'F–öäW'&÷"†b&Ö—76–ær6ö×7BFVÆVw&ÒÖ&¶W#¢¶Ö&¶W'Ò"Ğ Ğ¢f÷&&–FFVâÒ°Ğ¢"ÒÉ¹Ê	Ã¢"ÀĞ¢"ÒÈ8Ø9Â»8Ù™C¢"ÀĞ¢"ÒÊhÈ¹ÂË+NØÃ¢"ÀĞ¢%WF—F–öâf÷"&V6öç6–FW&F–öâ"ÀĞ¢%&ö†–&—F–ær–×÷'FF–öâæBÖ&¶WF–ær"ÀĞ¢%&Wf–÷W6Ç’WF†÷&—¦VB6÷fW&VB6öÖ×Væ–6F–öç2WV—ÖVçB"ÀĞ¢.ÉÛ»(NØK"ÀĞ¢&–çfW'FW""ÀĞ¢.Èºº+É›Èº"ÀĞ¢&f65öFV6—6–öåöæ÷F–6R"ÀĞ¢ĞĞ¢Æ÷rÒ&öG’æÆ÷vW"‚Ğ¢f÷"Ö&¶W"–âf÷&&–FFVã Ğ¢†—7F6²ÒÆ÷r–bÖ&¶W"æ—6Æ÷vW"‚’VÇ6R&öGĞ¢æVVFÆRÒÖ&¶W"–bÖ&¶W"æ—6Æ÷vW"‚’VÇ6RÖ&¶W Ğ¢–bæVVFÆR–â†—7F6³ Ğ¢&—6R76W'F–öäW'&÷"†b&f÷&&–FFVâFVÆVw&ÒFW‡BÆV¶VC¢¶Ö&¶W'Ò"Ğ Ğ¢ÆöæuöÆ–æW2Ò¶Æ–æRf÷"Æ–æR–âÆ–æW2–bÆVâ†Æ–æR’â¶‡5÷FVÆVw&ÕöFVÆ—fW'•öwV&BäÔ…ô$ôE•ôÄ”äUô4„%5ĞĞ¢–bÆöæuöÆ–æW3 Ğ¢&—6R76W'F–öäW'&÷"†b&÷fW&ÆöærFVÆVw&ÒÆ–æRÆV¶VC¢¶ÆöæuöÆ–æW5³Õ³£#×Ò"Ğ Ğ¢ÆW'Eö6÷VçBÒ7VÒƒf÷"Æ–æR–âÆ–æW2–bÆ–æRç7F'G7v—F‚‚"22"’Ğ¢–bÆW'Eö6÷VçBÒ Ğ¢&—6R76W'F–öäW'&÷"†b&W‡V7FVBöæÇ’öæRFVÆ—fW&VBÆW'BÂv÷B¶ÆW'Eö6÷VçGÒ"Ğ Ğ Ğ¦–bõöæÖUõòÓÒ%õöÖ–åõò# Ğ¢&—6R7—7FVÔW†—B†Ö–â‚’Ğ