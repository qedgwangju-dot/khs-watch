#!/usr/bin/env python3
"""Meta-contract for high-impact news automation quality.

This guard is intentionally about process, not one headline. It keeps the
automation aligned with the operating standard: foreign/official source first,
new unseen items only, decision-impact classification, concrete Korea-market
interpretation, and no generic placeholder explanations.
"""

from __future__ import annotations

import importlib
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"

WORKFLOWS = [
    ROOT / ".github" / "workflows" / "gamejoa-preopen-news-radar.yml",
    ROOT / ".github" / "workflows" / "gamejoa-preopen-news-radar-test.yml",
    ROOT / ".github" / "workflows" / "khs-policy-watch.yml",
]

SOURCE_FILES = [
    SCRIPTS / "gamejoa_preopen_news_radar_runner.py",
    SCRIPTS / "gamejoa_preopen_news_radar_full_compact_runner.py",
    SCRIPTS / "gamejoa_preopen_news_radar_k_defense_runner.py",
    SCRIPTS / "gamejoa_preopen_news_radar_nuclear_turbine_runner.py",
    SCRIPTS / "gamejoa_preopen_news_radar_domestic_telecom_runner.py",
    SCRIPTS / "gamejoa_preopen_news_radar_korea_nuclear_siting_runner.py",
    SCRIPTS / "gamejoa_preopen_news_radar_transformer_tariff_runner.py",
    SCRIPTS / "khs_trusted_policy_news_watch.py",
    SCRIPTS / "khs_transformer_tariff_policy_watch.py",
]

LATE_TRANSLATION_OR_RELAY_SOURCES = [
    "Yonhap", "yonhap", "YNA", "yna", "연합뉴스",
    "Korea Economic", "korea economic", "한국경제", "한국경제신문",
    "매일경제", "서울경제", "서울경제신문", "서울신문",
    "Korea Herald", "korea herald", "Korea Joongang", "korea joongang",
    "Daum", "daum", "더구루", "the guru",
]


def require(path: Path, snippets: list[str], errors: list[str]) -> None:
    if not path.exists():
        errors.append(f"missing file: {path.relative_to(ROOT)}")
        return
    text = path.read_text(encoding="utf-8")
    for snippet in snippets:
        if snippet not in text:
            errors.append(f"{path.relative_to(ROOT)} missing quality hook: {snippet}")


def assert_workflows_run_self_audit(errors: list[str]) -> None:
    for workflow in WORKFLOWS:
        require(workflow, ["python scripts/verify_high_impact_news_self_audit.py"], errors)


def assert_no_late_translation_sources(errors: list[str]) -> None:
    for path in SOURCE_FILES:
        if not path.exists():
            errors.append(f"missing source contract target: {path.relative_to(ROOT)}")
            continue
        text = path.read_text(encoding="utf-8")
        for source in LATE_TRANSLATION_OR_RELAY_SOURCES:
            if source in text:
                errors.append(
                    f"late translation source leaked into production: "
                    f"{path.relative_to(ROOT)} contains {source}"
                )


def assert_guardrail_hooks(errors: list[str]) -> None:
    require(
        SCRIPTS / "gamejoa_preopen_news_radar_full_compact_runner.py",
        [
            "GENERIC_EXPLANATION_PHRASES",
            "def has_generic_explanation",
            "정책·기업 이벤트의 내용과 한국장 영향이 구체적으로 설명되지 않아 제외",
            "has_decision_impact(normalized)",
            "is_low_impact_trade_admin_notice",
            "is_actionable_local_dc_policy",
            "source_evidence_text",
            "countervailing",
            "south korea",
            "decision_matrix",
            "guard_preopen_report(report)",
        ],
        errors,
    )
    require(
        SCRIPTS / "gamejoa_preopen_news_radar_telegram_runner.py",
        [
            "filter_previously_seen_alerts(classified, now)",
            "final_alerts_for_output(deduped, limit)",
            "record_seen_alerts(final_alerts, now)",
            "selection_diagnostics",
            '"source_failures": source_failures',
            "alert_seen_keys",
            "GAMEJOA_RADAR_SEEN_TTL_DAYS",
        ],
        errors,
    )
    require(
        SCRIPTS / "gamejoa_preopen_news_radar_semisupply_runner.py",
        [
            "TRENDFORCE_RESEARCH_MAX_AGE_DAYS",
            "source_published",
            "age_days > TRENDFORCE_RESEARCH_MAX_AGE_DAYS",
        ],
        errors,
    )
    require(
        SCRIPTS / "verify_gamejoa_semisupply_contract.py",
        [
            "stale TrendForce HBM4 research item was not excluded",
            "TrendForce duplicate dedupe key mismatch",
            "foreign_first_source_contract_errors",
        ],
        errors,
    )
    require(
        SCRIPTS / "khs_policy_watch.py",
        [
            '"China MOFCOM announcements"',
            "parse_mofcom_html",
            "china_trade_controls",
            "暂停出口",
            'Source("White House fact sheets"',
            'Source("White House remarks"',
            'Source("White House videos"',
            'Source("White House briefings statements"',
            'Source("State Department office spokesperson"',
            "state_smr_moc_policy",
            "remarks by president trump",
            "TRUMP_MARKET_MOVING_TERMS",
            "TRUMP_OFFICIAL_REMARK_STRONG_TERMS",
            '"/videos/"',
            "strait of hormuz",
            "정유/화학/해운",
        ],
        errors,
    )
    require(
        SCRIPTS / "khs_policy_alert_guardrails.py",
        [
            "is_china_mofcom_trade_control",
            "반도체/HBM 공정가스",
            "정유/화학/해운",
            "strait of hormuz",
            "red sea",
            "houthi",
        ],
        errors,
    )
    require(
        SCRIPTS / "khs_trusted_policy_news_watch.py",
        [
            "china_mofcom_export_controls_tariffs",
            "China Ministry of Commerce export ban suspension tariff helium",
            "trump_direct_policy_remarks_watch",
            "트럼프 대통령 직접 발언, 시장 영향 정책 신호",
            "site:reuters.com Trump says tariffs chips AI semiconductor China",
            "site:reuters.com Trump says Iran Israel Hormuz oil",
            "site:reuters.com Trump Iran wants talks negotiations",
            "site:reuters.com Trump Iran reached out seeking new agreement",
            "site:bloomberg.com Trump Iran reached out seeking new agreement",
            "Trump says Iran wants negotiations Reuters",
            "Trump says Iran reached out seeking a new agreement",
            "reached out seeking",
            "new agreement",
            "legacy_daily_fingerprint",
            "unseen_items_for_rule",
            "story-v2",
            "compact_explanation_lines",
            "compact_korea_market_view",
            "compact_sectors",
            "site:apnews.com Trump NATO Iran Ukraine defense spending tariffs",
            "site:cnbc.com Trump tariffs Fed dollar oil chips nuclear data centers",
            "Trump comments Red Sea Houthi Iran missile strike Brent WTI Reuters",
            "korean_trump_story_title",
            "story_display_title",
            "us_japan_korea_smr_moc_state_watch",
            "GE Vernova",
            "Samsung C&T",
            "BWRX-300",
            "확정 매출 확인 불가",
        ],
        errors,
    )
    require(
        SCRIPTS / "khs_telegram_delivery_guard.py",
        [
            "FEDERAL_REGISTER_BOILERPLATE_BLOCKERS",
            "VISIBLE_ENGLISH_BLOCKERS",
            "has_source_body_mismatch",
            "source_body_mismatch",
            "duplicate_policy_heading",
            "has_long_english_run",
            "REQUIRED_EXPLANATION_FIELD_GROUPS",
        ],
        errors,
    )
    require(
        SCRIPTS / "verify_khs_policy_delivery_contract.py",
        [
            "assert_china_mofcom_export_control_reaches_policy_lane",
            "assert_foreign_first_policy_sources",
            "assert_router_final_semantic_dedupe",
            "assert_router_keeps_source_families_separate",
            "assert_delivery_guard_blocks_source_body_mismatch",
            "assert_delivery_guard_blocks_duplicate_policy_alerts",
            "raw English titles",
        ],
        errors,
    )
    require(
        SCRIPTS / "khs_policy_alert_explainer.py",
        [
            "is_china_mofcom_trade_control",
            "china_mofcom_product",
            "중국 상무부",
            "반도체/HBM 공정가스",
        ],
        errors,
    )
    require(
        SCRIPTS / "gamejoa_preopen_news_radar_runner.py",
        [
            "중국 상무부 수출통제/관세",
            "China Ministry of Commerce OR MOFCOM",
            '"helium", "rare earth", "gallium", "germanium", "graphite"',
        ],
        errors,
    )
    require(
        SCRIPTS / "gamejoa_preopen_news_radar_full_compact_runner.py",
        [
            "is_china_mofcom_control",
            "china_mofcom_product_label",
            "중국 상무부",
            "반도체/HBM 공정가스",
        ],
        errors,
    )


def assert_generic_gamejoa_item_is_rejected(errors: list[str]) -> None:
    sys.path.insert(0, str(SCRIPTS))
    runner = importlib.import_module("gamejoa_preopen_news_radar_full_compact_runner")
    sample = {
        "news": "미국, 관세·통관 정책 변화 체크",
        "original_news": "Opportunity To Request Administrative Review",
        "publisher": "Federal Register",
        "source": "Federal Register",
        "link": "https://www.federalregister.gov/example",
        "published": "2026-07-01T09:00+09:00",
        "impacts": ["시간표"],
        "paths": ["정책 타임라인"],
        "sectors": ["관세/수출주", "공급망", "물류/통상"],
        "policy_plain_summary": "공식 문서 또는 신뢰 보도에서 한국장 가격 변수 후보가 확인됐습니다.",
        "investment_view": "돈 버는 능력, 할인율, 수급, 시간표 중 무엇이 실제로 바뀌는지 원문과 시장 반응으로 재확인해야 합니다.",
        "korea_market_impact": "한국장 직접 영향은 원문에 근거가 있는 업종과 종목군으로만 제한해 확인합니다.",
    }
    normalized = runner.normalize_alert_for_output(sample)
    if runner.has_decision_impact(normalized):
        errors.append("generic GAMEJOA placeholder explanation was not rejected")


def assert_foreign_trade_requires_korea_link(errors: list[str]) -> None:
    sys.path.insert(0, str(SCRIPTS))
    runner = importlib.import_module("gamejoa_preopen_news_radar_full_compact_runner")
    morocco_notice = {
        "news": "미국, 관세·통관 정책 변화 체크",
        "original_news": "Countervailing Duty Order of Phosphate Fertilizers From Morocco",
        "publisher": "Federal Register",
        "source": "Federal Register Commerce",
        "link": "https://www.federalregister.gov/example-morocco",
        "matched": ["tariff", "duty", "countervailing"],
        "sectors": ["관세/수출주", "공급망"],
    }
    if runner.has_korea_market_link(morocco_notice):
        errors.append("unrelated foreign trade notice was treated as Korea-market material")

    china_unrelated = dict(morocco_notice)
    china_unrelated["original_news"] = "Countervailing Duty Order of Rubber Chemicals From China"
    if runner.has_korea_market_link(china_unrelated):
        errors.append("unrelated China trade notice passed without a strategic product link")

    korea_notice = dict(morocco_notice)
    korea_notice["original_news"] = "Section 232 Transformer Tariff Change for South Korea"
    korea_notice["link"] = "https://www.federalregister.gov/example-korea-transformer"
    korea_notice["matched"] = ["tariff", "transformer", "south korea"]
    if not runner.has_korea_market_link(korea_notice):
        errors.append("Korea-linked transformer tariff notice lost its direct market path")


def main() -> int:
    errors: list[str] = []
    assert_workflows_run_self_audit(errors)
    assert_no_late_translation_sources(errors)
    assert_guardrail_hooks(errors)
    assert_generic_gamejoa_item_is_rejected(errors)
    assert_foreign_trade_requires_korea_link(errors)
    if errors:
        for error in errors:
            print(f"high_impact_self_audit_error={error}")
        return 1
    print("high_impact_news_self_audit=passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
