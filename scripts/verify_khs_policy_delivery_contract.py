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
import khs_policy_alert_explainer
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
    "- 핵심:",
    "- 핵심 내용:",
    "- 핵심 근거:",
    "- 확인 근거:",
    "- 투자 관점:",
    "- 투자 영향:",
    "- 투자 포인트:",
    "- 한국장:",
    "- 한국장 영향:",
    "- 실패 신호:",
)


def assert_compact_prose_limit(body: str, context: str, limit: int = 50) -> None:
    errors: list[str] = []
    for line in body.splitlines():
        stripped = line.strip()
        for prefix in COMPACT_PROSE_PREFIXES:
            if stripped.startswith(prefix):
                value = stripped.removeprefix(prefix).strip()
                if len(value) > limit:
                    errors.append(f"{prefix} {len(value)}자")
        if stripped.startswith("- 반영/반대:"):
            value = stripped.removeprefix("- 반영/반대:").strip()
            for part in value.split(" / ", 1):
                if len(part.strip()) > limit:
                    errors.append(f"- 반영/반대: {len(part.strip())}자")
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
    assert_treasury_borrowing_estimate_is_source_faithful()
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
    assert_boem_arctic_drilling_is_source_faithful()
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
        "Yonhap", "yonhap", "YNA", "yna", "연합뉴스",
        "Korea Economic", "korea economic", "한국경제", "한국경제신문",
        "매일경제", "서울경제", "서울경제신문", "서울신문",
        "Korea Herald", "korea herald", "Korea Joongang", "korea joongang",
        "Daum", "daum", "더구루", "the guru",
    ]
    for path in targets:
        text = path.read_text(encoding="utf-8")
        for token in forbidden:
            if token in text:
                raise AssertionError(f"foreign-first policy source contract violation: {path.name} contains {token}")



def assert_treasury_borrowing_estimate_is_source_faithful() -> None:
    treasury_urls = [source.url for source in khs_policy_watch.SOURCES if source.kind == "treasury_html"]
    if "https://home.treasury.gov/news/press-releases/sb0584" not in treasury_urls:
        raise AssertionError("Current Treasury borrowing release direct fallback is missing")
    body = (
        "WASHINGTON -- The U.S. Department of the Treasury today announced its current estimates "
        "of privately-held net marketable borrowing. During the July–September 2026 quarter, "
        "Treasury expects to borrow $739 billion in privately-held net marketable debt, assuming "
        "an end-of-September cash balance of $950 billion. The borrowing estimate is $68 billion "
        "higher than announced in May 2026. During the October–December 2026 quarter, Treasury "
        "expects to borrow $628 billion in privately-held net marketable debt, assuming an "
        "end-of-December cash balance of $850 billion. Additional financing details relating to "
        "Treasury’s Quarterly Refunding will be released at 8:30 a.m. on Wednesday, August 5, 2026."
    )
    direct_html = (
        '<html><head><title>Treasury Announces Marketable Borrowing Estimates</title></head>'
        '<body><h1>Treasury Announces Marketable Borrowing Estimates</h1>'
        f'<article>{body}</article></body></html>'
    )
    direct_source = next(
        source for source in khs_policy_watch.SOURCES
        if source.url == "https://home.treasury.gov/news/press-releases/sb0584"
    )
    direct_items = khs_policy_watch.parse_treasury_html(direct_html, direct_source)
    if len(direct_items) != 1 or not direct_items[0].get("body_verified"):
        raise AssertionError("Direct Treasury release page must produce one verified item")
    item = {
        "source": "U.S. Treasury press releases",
        "title": "Treasury Announces Marketable Borrowing Estimates",
        "source_title": "Treasury Announces Marketable Borrowing Estimates",
        "link": "https://home.treasury.gov/news/press-releases/sb0584",
        "summary": body,
        "source_body": body,
        "published_kst": "2026-08-04T04:00:00+09:00",
        "body_verified": True,
    }
    result = khs_policy_watch.classify_item(item)
    if not result:
        raise AssertionError("Treasury borrowing estimate was not classified")
    khs_policy_watch.ensure_explained(result)
    expected = ["7,390억달러", "9,500억달러", "6,280억달러", "680억달러 증가", "2026년 8월 5일"]
    summary = result.get("policy_plain_summary") or ""
    for token in expected:
        if token not in summary:
            raise AssertionError(f"Treasury source fact missing from summary: {token}")
    if result.get("title_ko") != "미 재무부, 분기별 순시장성 차입 전망 발표":
        raise AssertionError("Treasury Korean title is not source-specific")
    if result.get("matched", {}).keys() != {"treasury_borrowing"}:
        raise AssertionError(f"Treasury navigation text leaked into classification: {result.get('matched')}")
    result["sectors"] = khs_policy_alert_guardrails.direct_sectors(result)
    if "미국 국채/금리/달러" not in result["sectors"]:
        raise AssertionError(f"Treasury sector was removed by guardrails: {result['sectors']}")
    if not khs_policy_alert_guardrails.has_actionable_decision_impact(result):
        raise AssertionError(f"Treasury alert was removed by decision guard: {result.get('guardrail_note')}")
    unverified = dict(item, body_verified=False)
    if khs_policy_watch.classify_item(unverified) is not None:
        raise AssertionError("Unverified Treasury listing must fail closed")
    wrong_document = dict(
        item,
        title="Economy Statement for the Treasury Borrowing Advisory Committee",
        source_title="Economy Statement for the Treasury Borrowing Advisory Committee",
    )
    if khs_policy_watch.classify_item(wrong_document) is not None:
        raise AssertionError("Treasury TBAC economy statement must not reuse borrowing estimate profile")


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
        商务部公告2026年第99号 关于自今日起暂停氦出口的公告
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
    if "중국 상무부" not in title or "헬륨" not in title or "수출 일시 중단" not in title:
        raise AssertionError(f"MOFCOM alert title was not specifically translated: {title}")
    if "반도체/HBM 공정가스" not in (alert.get("sectors") or []):
        raise AssertionError("MOFCOM helium alert lost its Korean semiconductor gas value chain")
    if set(alert.get("impacts") or []) != {"매출·마진·현금흐름", "수급", "시간표"}:
        raise AssertionError(f"MOFCOM decision-impact matrix mismatch: {alert.get('impacts')}")
    rendered = khs_policy_alert_router.render_policy_report(
        [alert],
        dt.datetime(2026, 7, 10, 6, 30, tzinfo=ZoneInfo("Asia/Seoul")),
    )
    if title not in rendered or "반도체·HBM 공정" not in rendered or "산업가스" not in rendered:
        raise AssertionError("MOFCOM compact Korean report dropped its title or Korean value chain")
    mismatch = khs_telegram_delivery_guard.has_source_body_mismatch(title, rendered)
    if mismatch:
        raise AssertionError(f"MOFCOM source/body guard rejected a matching alert: {mismatch}")
    if khs_telegram_delivery_guard.has_long_english_run(rendered):
        raise AssertionError("MOFCOM alert leaked a long untranslated English block")

    irrelevant_fixture = """
    <html><body><a href="/zcfb/blgg/gg/2026/art/2026/art_food_test.html">
      商务部公告2026年第98号 对原产于加拿大的豌豆淀粉反倾销调查初步裁定
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
    title = "KHS 신뢰외신 정책 워치: [상·공식 확인 전] 미국, $17.5 billion 원전 대출"
    body = "\n".join(
        [
            "🚨 KHS 신뢰외신 정책·규제 고충격 워치 · 2026년 07월 25일 21:47 KST",
            "",
            "## 1. [상·공식 확인 전] 미국, 원전 대출과 5억유로 협력기금 발표",
            "- 핵심: 미국이 원전 건설에 $17.5 billion 저리 대출을 제시했습니다.",
            "- 투자 관점: 실제 대출 조건과 기자재 발주 일정을 확인합니다.",
            "- 한국장 영향: 국내 원전 기자재의 미국 공급 노출을 확인합니다.",
            "- 의사결정 영향: 매출·마진·현금흐름, 시간표",
            "- 영향 섹터: 원전/전력기기",
            "- 반영/반대: 기대 일부 반영 / 최종 대출계약은 미정",
            "- 실패 신호: 최종 대출계약과 발주가 없으면 약화됩니다.",
            "- 출처: [Reuters](https://www.reuters.com/example-policy-story) · 조회 21:47 KST",
            "",
            "Actions: https://github.com/qedgwangju-dot/khs-watch/actions/runs/1",
            "Issues: https://github.com/qedgwangju-dot/khs-watch/issues",
            "투자 조언이 아닌 참고용 정책·규제 알림입니다.",
        ]
    )
    formatted_title, formatted_body = khs_policy_telegram_formatter.format_policy_message(
        title,
        body,
        rates={"USD": 1400.0, "EUR": 1600.0},
        now=now,
    )
    required = [
        "25조원",
        "8,000억원",
        "- 핵심:",
        "https://www.reuters.com/example-policy-story",
    ]
    for marker in required:
        if marker not in f"{formatted_title}\n{formatted_body}":
            raise AssertionError(f"final policy Telegram format missing: {marker}")
    forbidden = [
        "KHS ",
        "## 1.",
        "- 투자 관점:",
        "- 한국장 영향:",
        "- 영향 섹터:",
        "- 의사결정 영향:",
        "- 반영/반대:",
        "- 실패 신호:",
        "- 원화 환산 기준:",
        "Actions:",
        "Issues:",
        "투자 조언이 아닌 참고용 정책·규제 알림입니다.",
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
        "신뢰외신 정책 워치: 글로벌 투자계획",
        "\n".join([
            "1. [상·공식 확인 전] 글로벌 투자계획",
            "- 핵심: 투자액 9500억달러와 추가계획 1조7000억달러가 발표됐습니다.",
            "- 출처: [Reuters](https://www.reuters.com/example-investment-plan)",
        ]),
        rates={"USD": 1462.1},
        now=now,
    )
    multi_core = next(
        line.removeprefix("- 핵심:").strip()
        for line in multi_amount_body.splitlines()
        if line.startswith("- 핵심:")
    )
    for marker in (
        "9500억달러(약 1,389조원)",
        "1조7000억달러(약 2,486조원)",
    ):
        if marker not in multi_core:
            raise AssertionError(f"policy 50-char FX core missing {marker}: {multi_core}")
    if len(multi_core) > 50:
        raise AssertionError(f"policy FX core exceeds 50 chars: {multi_core}")
    multi_errors = khs_policy_telegram_formatter.validate_final_policy_message(
        multi_amount_title,
        multi_amount_body,
    )
    if multi_errors:
        raise AssertionError(f"policy multi-amount format failed: {multi_errors}")


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
        "Fact Sheet: President Donald J. Trump Secures America’s Defense Supply "
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
            "Fact Sheet: President Donald J. Trump Secures America’s Defense Supply Chains and Ensures Domestic Acquisition of Critical Materials",
            "The Executive Order limits waivers for critical materials from covered nations, requires supply chain mapping, and qualifies domestic sources and partner nation sources. Related: historic defense investment from NATO allies.",
            "https://www.whitehouse.gov/fact-sheets/2026/07/fact-sheet-president-donald-j-trump-secures-americas-defense-supply-chains-and-ensures-domestic-acquisition-of-critical-materials/",
            "백악관, 미 방산 핵심소재 공급망의 적성국 의존 축소 행정명령",
            "공급망 전수지도",
        ),
        (
            "Fact Sheet: President Donald J. Trump Takes Action Against Canada’s Discriminatory Trade Policies",
            "Under section 338 the President imposes additional tariffs on Canada. The 50 percent tariff covers cars, alcohol and dairy and takes effect in 30 days.",
            "https://www.whitehouse.gov/fact-sheets/2026/07/fact-sheet-canada-section-338-tariffs/",
            "백악관, 캐나다 자동차·주류·유제품 등에 추가 50% 관세",
            "서명 30일 뒤",
        ),
        (
            "Fact Sheet: President Donald J. Trump Secures a Historic Trade Deal with Jordan",
            "The agreement on reciprocal trade with Jordan preserves duty-free access. Royal Jordanian will purchase six Boeing 787-9 aircraft for 1.4 billion dollars and Hikma will invest 1 billion dollars.",
            "https://www.whitehouse.gov/fact-sheets/2026/07/fact-sheet-trade-deal-with-jordan/",
            "백악관, 요르단과 상호무역협정 발표",
            "14억달러",
        ),
        (
            "Fact Sheet: President Donald J. Trump Takes Further Action To Adjust Imports Of Aluminum Into The United States",
            "The section 232 program requests onshoring plans for primary aluminum. Approved companies building or expanding a smelter may import at half the otherwise applicable tariff rate.",
            "https://www.whitehouse.gov/fact-sheets/2026/07/fact-sheet-president-donald-j-trump-takes-further-action-to-adjust-imports-of-aluminum-into-the-united-states/",
            "백악관, 미국 알루미늄 제련 투자기업에 232조 관세 절반 적용 추진",
            "기존 232조 세율의 절반",
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
    assert_compact_prose_limit(rendered, "White House policy")


def assert_whitehouse_fact_sheet_is_preferred_for_duplicate_story() -> None:
    fingerprint = "canada-story"
    proclamation = {
        "source": "White House proclamations",
        "title": "Imposing Additional Duties With Respect to Motor Vehicles",
        "link": "https://www.whitehouse.gov/presidential-actions/canada-motor-vehicles/",
        "fingerprint": fingerprint,
        "whitehouse_story_key": "canada-section-338-tariffs",
    }
    fact_sheet = {
        "source": "White House fact sheets",
        "title": "Fact Sheet: President Donald J. Trump Imposes Additional Tariffs on Canada",
        "link": "https://www.whitehouse.gov/fact-sheets/additional-tariffs-on-canada/",
        "fingerprint": fingerprint,
        "whitehouse_story_key": "canada-section-338-tariffs",
    }
    selected = khs_policy_watch.dedupe_candidate_fingerprints([proclamation, fact_sheet])
    if len(selected) != 1 or selected[0].get("source") != "White House fact sheets":
        raise AssertionError(f"White House duplicate story did not prefer its fact sheet: {selected}")


def assert_policy_seen_waits_for_confirmed_delivery() -> None:
    original = (
        khs_policy_seen_finalize.OUT,
        khs_policy_seen_finalize.DATA,
        khs_policy_seen_finalize.PENDING_PATH,
        khs_policy_seen_finalize.DELIVERY_PATH,
        khs_policy_seen_finalize.SEEN_PATH,
        khs_policy_seen_finalize.SURVIVING_ALERT_PATHS,
    )
    with tempfile.TemporaryDirectory() as temp:
        root = Path(temp)
        out = root / "out"
        data = root / "data"
        out.mkdir()
        data.mkdir()
        khs_policy_seen_finalize.OUT = out
        khs_policy_seen_finalize.DATA = data
        khs_policy_seen_finalize.PENDING_PATH = out / "pending.json"
        khs_policy_seen_finalize.DELIVERY_PATH = out / "confirmed.json"
        khs_policy_seen_finalize.SEEN_PATH = data / "seen.json"
        khs_policy_seen_finalize.SURVIVING_ALERT_PATHS = (out / "alerts.json",)
        khs_policy_seen_finalize.PENDING_PATH.write_text(
            json.dumps({"created_at_kst": "2026-07-23T18:00:00+09:00", "seen": {"fp1": {"title": "verified"}}}),
            encoding="utf-8",
        )
        (out / "alerts.json").write_text(
            json.dumps([{"fingerprint": "fp1"}]),
            encoding="utf-8",
        )
        khs_policy_seen_finalize.main()
        if khs_policy_seen_finalize.SEEN_PATH.exists():
            raise AssertionError("policy seen state was committed without confirmed Telegram delivery")
        khs_policy_seen_finalize.DELIVERY_PATH.write_text(
            json.dumps({"status": "confirmed", "confirmed_at_kst": "2026-07-23T18:01:00+09:00"}),
            encoding="utf-8",
        )
        khs_policy_seen_finalize.main()
        state = json.loads(khs_policy_seen_finalize.SEEN_PATH.read_text(encoding="utf-8"))
        if "fp1" not in state.get("seen", {}):
            raise AssertionError("confirmed Telegram delivery did not finalize policy seen state")
    (
        khs_policy_seen_finalize.OUT,
        khs_policy_seen_finalize.DATA,
        khs_policy_seen_finalize.PENDING_PATH,
        khs_policy_seen_finalize.DELIVERY_PATH,
        khs_policy_seen_finalize.SEEN_PATH,
        khs_policy_seen_finalize.SURVIVING_ALERT_PATHS,
    ) = original


def assert_stablecoin_watch_rejects_bok_generic_page() -> None:
    generic = "금융안정업무 소개 한국은행 지급결제 디지털화폐 금융안정 정책 업무 결제 표준"
    if khs_domestic_stablecoin_policy_watch.is_policy_candidate(generic, "Bank of Korea digital currency policy"):
        raise AssertionError("BOK generic financial-stability page passed stablecoin candidate filter")

    direct = "한국은행 원화 스테이블코인 예금 대체 준비자산 상환청구권 발행 주체 규제 법안"
    if not khs_domestic_stablecoin_policy_watch.is_policy_candidate(direct, "Bank of Korea digital currency policy"):
        raise AssertionError("BOK direct stablecoin policy text was over-filtered")

    title = khs_domestic_stablecoin_policy_watch.stablecoin_title("한국은행 한은 금융안정업무 소개 지급결제 디지털화폐")
    if "예금 대체" in title or "준비자산" in title:
        raise AssertionError("BOK actor-only text still selects deposit/reserve stablecoin title")


def assert_stablecoin_semantic_dedupe() -> None:
    base = {
        "title": "국내 디지털자산 정책: 스테이블코인 예금 대체·준비자산 규제 체크",
        "importance": "상",
        "status": "확정",
        "published_kst": "2026-07-06T00:00:00+09:00",
        "matched": {"korea_stablecoin_policy": ["스테이블코인", "예금 대체"]},
        "domestic_stablecoin_policy_watch": True,
        "link": "https://www.bok.or.kr/portal/submain/submain/cbdc.do?menuNo=201136",
        "fingerprint": "source-a",
    }
    duplicate = {
        **base,
        "source": "Bank of Korea payment research",
        "link": "https://www.bok.or.kr/portal/bbs/B0000232/list.do?menuNo=200706",
        "fingerprint": "source-b",
    }
    base["source"] = "Bank of Korea digital currency policy"
    merged = khs_domestic_stablecoin_policy_watch.merge_policy_duplicates([base, duplicate])
    if len(merged) != 1:
        raise AssertionError(f"stablecoin policy semantic dedupe failed: expected 1, got {len(merged)}")
    item = merged[0]
    if "Bank of Korea digital currency policy" not in item.get("source", ""):
        raise AssertionError("stablecoin dedupe dropped first source")
    if "Bank of Korea payment research" not in item.get("source", ""):
        raise AssertionError("stablecoin dedupe dropped second source")
    if len(item.get("source_links") or []) != 2:
        raise AssertionError("stablecoin dedupe did not keep both source links")
    source_fps = set(item.get("source_fingerprints") or [])
    if source_fps != {"source-a", "source-b"}:
        raise AssertionError(f"stablecoin dedupe did not keep source fingerprints: {source_fps}")


def assert_router_final_semantic_dedupe() -> None:
    base = {
        "title": "국내 디지털자산 정책: 스테이블코인 예금 대체·준비자산 규제 체크",
        "importance": "상",
        "status": "확정",
        "published_kst": "2026-07-06T00:00:00+09:00",
        "matched": {"korea_stablecoin_policy": ["스테이블코인", "예금 대체"]},
        "domestic_stablecoin_policy_watch": True,
        "impacts": ["시간표", "수급", "밸류에이션/할인율"],
        "sectors": ["금융/자본시장/스테이블코인"],
        "link": "https://www.bok.or.kr/portal/submain/submain/cbdc.do?menuNo=201136",
        "source": "Bank of Korea digital currency policy",
    }
    duplicate = {
        **base,
        "source": "Bank of Korea payment research",
        "link": "https://www.bok.or.kr/portal/bbs/B0000232/list.do?menuNo=200706",
    }
    merged = khs_policy_alert_router.dedupe_alerts([base, duplicate])
    if len(merged) != 1:
        raise AssertionError(f"router final semantic dedupe failed: expected 1, got {len(merged)}")
    item = merged[0]
    if len(item.get("source_links") or []) != 2:
        raise AssertionError("router final dedupe did not keep both source links")
    rendered_sources = khs_policy_alert_router.source_markdown(item)
    if "Bank of Korea digital currency policy" not in rendered_sources:
        raise AssertionError("router source rendering dropped first source")
    if "Bank of Korea payment research" not in rendered_sources:
        raise AssertionError("router source rendering dropped second source")


def assert_router_keeps_source_families_separate() -> None:
    boem = {
        "source": "BOEM news",
        "title": "Generic policy document",
        "title_ko": "미국 정책 문서 공표",
        "link": "https://www.boem.gov/newsroom/press-releases/boem-initiates-first-step-explore-potential-outer-continental-shelf-space",
        "importance": "상",
        "status": "확정",
        "published_kst": "2026-07-07T23:00:00+09:00",
        "matched": {"agency_order": ["order"]},
        "impacts": ["시간표"],
        "paths": ["정책 타임라인"],
        "sectors": ["정책/규제 일반"],
    }
    fcc = {
        **boem,
        "source": "Federal Register FCC",
        "link": "https://www.federalregister.gov/documents/2026/07/06/2026-13518/prohibiting-importation-and-marketing-of-previously-authorized-covered-communications-equipment",
        "matched": {"agency_order": ["order"]},
    }
    merged = khs_policy_alert_router.dedupe_alerts([boem, fcc])
    if len(merged) != 2:
        raise AssertionError(f"router merged different source families: expected 2, got {len(merged)}")


def assert_whitehouse_video_remarks_are_parsed_but_market_filtered() -> None:
    html = """
    <a href="/videos/president-trump-delivers-remarks-on-semiconductor-tariffs-and-china/">
    President Trump Delivers Remarks on Semiconductor Tariffs and China
    </a>
    July 8, 2026
    <a href="/videos/president-trump-speaks-at-the-faith-freedom-coalition-conference/">
    President Trump Speaks at the Faith & Freedom Coalition Conference
    </a>
    July 8, 2026
    <a href="/videos/president-trump-participates-in-a-nato-leaders-working-session/">
    President Trump Participates in a NATO Leaders Working Session
    </a>
    July 8, 2026
    """
    source = khs_policy_watch.Source("White House remarks", "https://www.whitehouse.gov/remarks/", "whitehouse_html")
    items = khs_policy_watch.parse_whitehouse_html(html, source)
    if len(items) != 3:
        raise AssertionError(f"White House remarks parser did not retain video links: {len(items)}")
    market_item = next((item for item in items if "semiconductor" in item["title"].lower()), None)
    generic_item = next((item for item in items if "faith" in item["title"].lower()), None)
    generic_nato_item = next((item for item in items if "nato" in item["title"].lower()), None)
    if not market_item or "/videos/" not in market_item["link"]:
        raise AssertionError("White House market-moving video remark link was not parsed")
    market_item.update(
        {
            "body_verified": True,
            "source_body": "President Trump announced semiconductor tariffs and China export-control policy.",
        }
    )
    generic_item.update(
        {
            "body_verified": True,
            "source_body": "President Trump addressed a political conference.",
        }
    )
    generic_nato_item.update(
        {
            "body_verified": True,
            "source_body": "President Trump participated in a NATO leaders working session.",
        }
    )
    if not khs_policy_watch.classify_item(market_item):
        raise AssertionError("White House market-moving video remark was not classified")
    if khs_policy_watch.classify_item(generic_item):
        raise AssertionError("White House generic political video remark was classified as high-impact")
    if khs_policy_watch.classify_item(generic_nato_item):
        raise AssertionError("White House generic NATO video without market detail was classified as high-impact")


def assert_whitehouse_executive_order_is_korean_and_not_fcc() -> None:
    item = {
        "source": "White House executive orders",
        "title": "Ushering in the Next Frontier of Quantum Innovation",
        "summary": "White House Executive Order official page link: Ushering in the Next Frontier of Quantum Innovation",
        "source_body": "The Executive Order directs a national quantum innovation and national security program.",
        "link": "https://www.whitehouse.gov/presidential-actions/2026/06/ushering-in-the-next-frontier-of-quantum-innovation/",
        "published_kst": "2026-07-13T00:00:00+09:00",
        "body_verified": True,
    }
    classified = khs_policy_watch.classify_item(item)
    if not classified:
        raise AssertionError("White House quantum executive order was not classified")
    if "fcc_decision_notice" in (classified.get("matched") or {}):
        raise AssertionError("White House executive order was misclassified as an FCC notice")
    title = khs_policy_alert_router.safe_title(classified)
    if title != "백악관, 양자기술 혁신·국가안보 행정명령 발표":
        raise AssertionError(f"White House executive order title was not Korean and specific: {title}")
    if any(token in title for token in ("Quantum Innovation", "FCC", "통신·주파수")):
        raise AssertionError(f"White House executive order title leaked wrong topic: {title}")


def assert_trump_statement_reaches_policy_lane() -> None:
    item = {
        "source": "White House remarks",
        "title": "Remarks by President Donald J. Trump on Semiconductor Tariffs and China",
        "summary": "White House Trump Remarks official page link: Remarks by President Donald J. Trump on Semiconductor Tariffs and China",
        "source_body": "President Trump announced semiconductor tariffs and China export-control policy.",
        "link": "https://www.whitehouse.gov/remarks/2026/07/remarks-by-president-donald-j-trump-on-semiconductor-tariffs-and-china/",
        "published_kst": "2026-07-08T00:00:00+09:00",
        "body_verified": True,
    }
    classified = khs_policy_watch.classify_item(item)
    if not classified:
        raise AssertionError("Trump direct remarks were not classified as a policy alert")
    if "presidential_action" not in (classified.get("matched") or {}):
        raise AssertionError("Trump direct remarks did not carry presidential_action match")
    classified["sectors"] = khs_policy_alert_guardrails.direct_sectors(classified)
    khs_policy_alert_guardrails.ensure_explained(classified)
    if not khs_policy_alert_guardrails.has_actionable_decision_impact(classified):
        raise AssertionError("Trump direct remarks were dropped by policy decision-impact guardrail")
    rendered = khs_policy_alert_router.render_policy_report(
        [classified],
        dt.datetime(2026, 7, 8, 15, 40, tzinfo=ZoneInfo("Asia/Seoul")),
    )
    required = [
        "트럼프 대통령 발언, 시장 영향 정책 신호",
        "- 핵심:",
        "- 의사결정 영향:",
        "백악관 트럼프 발언",
    ]
    for marker in required:
        if marker not in rendered:
            raise AssertionError(f"Trump direct remarks policy render missing: {marker}")
    if "Remarks by President Donald" in rendered:
        raise AssertionError("raw English Trump remarks title leaked into Telegram render")


def assert_nato_defense_fact_sheet_is_not_generic_trump_alert() -> None:
    item = {
        "source": "White House Fact Sheet",
        "title": "Fact Sheet: President Donald J. Trump Secures Historic Defense Investment from NATO Allies, Powering American Industry",
        "summary": (
            "At NATO's 2026 Ankara Summit, President Donald J. Trump announced a surge in defense investment "
            "from Allies, strengthening the U.S. defense industrial base. $3 billion in major deals and joint "
            "ventures were announced, including PAC-3 sustainment, MQ-4C Tritons, ATACMS, AMRAAM, Stinger, "
            "Small Diameter Bomb production, Anduril Barracuda-500 missiles, NATO 3.0, and PURL purchases."
        ),
        "source_body": (
            "At NATO's 2026 Ankara Summit, President Donald J. Trump announced a surge in defense investment "
            "from Allies, strengthening the U.S. defense industrial base. $3 billion in major deals and joint "
            "ventures were announced, including PAC-3, MQ-4C, ATACMS, AMRAAM, Stinger, SDB-I and Barracuda-500."
        ),
        "link": "https://www.whitehouse.gov/fact-sheets/2026/07/fact-sheet-president-donald-j-trump-secures-historic-defense-investment-from-nato-allies-powering-american-industry/",
        "published_kst": "2026-07-08T00:00:00+09:00",
        "body_verified": True,
    }
    classified = khs_policy_watch.classify_item(item)
    if not classified:
        raise AssertionError("NATO defense investment fact sheet was not classified")
    khs_policy_alert_guardrails.ensure_explained(classified)
    rendered = khs_policy_alert_router.render_policy_report(
        [classified],
        dt.datetime(2026, 7, 9, 9, 36, tzinfo=ZoneInfo("Asia/Seoul")),
    )
    required = [
        "백악관, NATO 방위투자 확대·미국 방산 생산 강화 발표",
        "PAC-3",
        "AMRAAM",
        "K-방산",
        "확정 매출은 아닙니다",
    ]
    for marker in required:
        if marker not in rendered:
            raise AssertionError(f"NATO defense fact sheet render missing: {marker}")
    forbidden = [
        "트럼프 대통령 발언, 시장 영향 정책 신호",
        "이란·이스라엘·호르무즈",
    ]
    for marker in forbidden:
        if marker in rendered:
            raise AssertionError(f"NATO defense fact sheet used generic Trump template: {marker}")
    cleanup()
    try:
        (OUT_DIR / "khs_policy_watch_alert_title.txt").write_text(
            "KHS 정책 워치: [상] 백악관, NATO 방위투자 확대·미국 방산 생산 강화 발표\n",
            encoding="utf-8",
        )
        (OUT_DIR / "khs_policy_watch_alert.md").write_text(rendered, encoding="utf-8")
        khs_telegram_delivery_guard.main()
        if not (OUT_DIR / "khs_policy_watch_alert.md").exists():
            raise AssertionError("NATO defense fact sheet was blocked by Telegram delivery guard")
    finally:
        cleanup()


def assert_trump_iran_war_statement_reaches_geopolitical_lane() -> None:
    item = {
        "source": "White House remarks",
        "title": "Remarks by President Donald J. Trump on Iran, Israel, and the Strait of Hormuz",
        "summary": "White House Trump Remarks official page link: Remarks by President Donald J. Trump on Iran, Israel, and the Strait of Hormuz",
        "source_body": "President Trump discussed Iran, Israel, oil shipping, and the Strait of Hormuz.",
        "link": "https://www.whitehouse.gov/remarks/2026/07/remarks-by-president-donald-j-trump-on-iran-israel-and-the-strait-of-hormuz/",
        "published_kst": "2026-07-08T00:00:00+09:00",
        "body_verified": True,
    }
    classified = khs_policy_watch.classify_item(item)
    if not classified:
        raise AssertionError("Trump Iran/Hormuz remarks were not classified as a policy alert")
    classified["sectors"] = khs_policy_alert_guardrails.direct_sectors(classified)
    if "방산/지정학" not in classified.get("sectors", []):
        raise AssertionError(f"Trump Iran/Hormuz remarks missing geopolitics sector: {classified.get('sectors')}")
    if "정유/화학/해운" not in classified.get("sectors", []):
        raise AssertionError(f"Trump Iran/Hormuz remarks missing oil/shipping sector: {classified.get('sectors')}")
    khs_policy_alert_guardrails.ensure_explained(classified)
    if not khs_policy_alert_guardrails.has_actionable_decision_impact(classified):
        raise AssertionError("Trump Iran/Hormuz remarks were dropped by decision-impact guardrail")
    rendered = khs_policy_alert_router.render_policy_report(
        [classified],
        dt.datetime(2026, 7, 8, 15, 45, tzinfo=ZoneInfo("Asia/Seoul")),
    )
    for marker in ("이란·이스라엘·중동 전쟁위험", "정유/화학/해운", "유가·환율·운임·방산"):
        if marker not in rendered:
            raise AssertionError(f"Trump Iran/Hormuz render missing market-impact marker: {marker}")


def assert_trusted_iran_hormuz_escalation_reaches_policy_lane() -> None:
    rule = next(
        rule for rule in khs_trusted_policy_news_watch.STORY_RULES
        if rule.key == "iran_hormuz_military_escalation"
    )
    item = {
        "title": "US attacks Iran over ship being hit in Strait of Hormuz; Tehran lashes out again at Gulf Arab states - AP News",
        "source": "AP News",
        "published_kst": "2026-07-12T09:45:00+09:00",
        "link": "https://apnews.com/article/iran-hormuz-regression-fixture",
        "priority": 7,
    }
    if not khs_trusted_policy_news_watch.has_required_terms(item["title"], rule):
        raise AssertionError("trusted Iran/Hormuz escalation headline did not satisfy required terms")
    rendered = khs_trusted_policy_news_watch.render_alert(
        rule,
        [item],
        dt.datetime(2026, 7, 12, 12, 30, tzinfo=ZoneInfo("Asia/Seoul")),
    )
    for marker in (
        "미국, 이란 추가 타격·호르무즈 긴장 고조 보도",
        "- 핵심:",
        "- 출처:",
        "AP News",
    ):
        if marker not in rendered:
            raise AssertionError(f"trusted Iran/Hormuz alert render missing: {marker}")
    for marker in (
        "- 투자 관점:",
        "- 한국장 영향:",
        "- 의사결정 영향:",
        "- 영향 섹터:",
        "- 반영/반대:",
        "- 실패 신호:",
    ):
        if marker in rendered:
            raise AssertionError(f"trusted Iran/Hormuz alert leaked removed field: {marker}")


def assert_trusted_trump_iran_holdoff_summary_and_header() -> None:
    rule = next(
        rule for rule in khs_trusted_policy_news_watch.STORY_RULES
        if rule.key == "trump_direct_policy_remarks_watch"
    )
    item = {
        "title": "Trump says he will hold off on fresh Iran attack in hope of quick deal - Reuters",
        "source": "Reuters",
        "published_kst": "2026-08-02T07:33:00+09:00",
        "link": "https://news.google.com/rss/articles/reuters-trump-iran-holdoff-fixture",
        "priority": 8,
    }
    rendered = khs_trusted_policy_news_watch.render_alert(
        rule,
        [item],
        dt.datetime(2026, 8, 2, 12, 29, tzinfo=ZoneInfo("Asia/Seoul")),
    )
    lines = rendered.splitlines()
    if not lines or lines[0] != "2026년 08월 02일 12:29 KST":
        raise AssertionError("trusted-policy body header is not date/time only")
    for marker in (
        "트럼프, 신속한 합의 기대하며 이란 추가 공격 보류",
        "트럼프는 신속한 합의를 기대해 이란 추가 공격을 보류했습니다. 조건부 유예입니다.",
        "Reuters",
    ):
        if marker not in rendered:
            raise AssertionError(f"Trump Iran holdoff alert missing source-specific marker: {marker}")
    if "신뢰외신 정책·규제 고충격 워치" in lines[0]:
        raise AssertionError("trusted-policy body header still contains the watch name")


def assert_trusted_policy_news_story_fingerprint_allows_intraday_updates() -> None:
    rule = next(
        rule for rule in khs_trusted_policy_news_watch.STORY_RULES
        if rule.key == "trump_direct_policy_remarks_watch"
    )
    nato_item = {
        "title": "Trump says 'a lot of unity' at NATO summit after lashing out at allies - Reuters",
        "source": "Reuters",
        "published_kst": "2026-07-09T08:58:10+09:00",
        "link": "https://example.com/nato",
    }
    iran_item = {
        "title": "Trump says Iran reached out seeking a new agreement - Bloomberg",
        "source": "Reuters",
        "published_kst": "2026-07-09T14:05:00+09:00",
        "link": "https://example.com/iran-talks",
    }
    if khs_trusted_policy_news_watch.fingerprint(rule, [nato_item]) == khs_trusted_policy_news_watch.fingerprint(rule, [iran_item]):
        raise AssertionError("trusted policy fingerprint still dedupes different Trump stories on the same day")
    legacy_fp = khs_trusted_policy_news_watch.legacy_daily_fingerprint(rule, [nato_item])
    seen = {legacy_fp: {"first_seen_kst": "2026-07-09T13:35:56+09:00"}}
    fresh = khs_trusted_policy_news_watch.unseen_items_for_rule(rule, [iran_item, nato_item], seen)
    if fresh != [iran_item]:
        raise AssertionError(f"legacy daily seen did not allow only fresh intraday Trump item: {fresh}")
    rendered = khs_trusted_policy_news_watch.korean_trump_story_title(iran_item["title"])
    if "이란의 새 합의 요청" not in rendered:
        raise AssertionError(f"Iran new-agreement headline was not translated exactly: {rendered}")
    if not khs_trusted_policy_news_watch.has_required_terms(iran_item["title"], rule):
        raise AssertionError("Trump Iran reached-out/new-agreement headline did not satisfy trusted-news required terms")


def assert_trusted_policy_news_render_is_compact() -> None:
    rule = next(
        rule for rule in khs_trusted_policy_news_watch.STORY_RULES
        if rule.key == "trump_direct_policy_remarks_watch"
    )
    item = {
        "title": "Trump says Iran reached out seeking a new agreement - CNBC",
        "source": "CNBC",
        "published_kst": "2026-07-09T19:00:18+09:00",
        "link": "https://news.google.com/example",
        "priority": 3,
    }
    rendered = khs_trusted_policy_news_watch.render_alert_bundle(
        [{"rule": rule, "items": [item], "fingerprint": "test"}],
        dt.datetime(2026, 7, 9, 22, 29, tzinfo=ZoneInfo("Asia/Seoul")),
    )
    required = [
        "트럼프, 이란의 새 합의 요청 연락 공개",
        "이란이 새 합의를 원해 미국에 연락",
        "- 핵심:",
        "- 출처:",
    ]
    for marker in required:
        if marker not in rendered:
            raise AssertionError(f"trusted policy compact render missing: {marker}")
    forbidden = [
        "- 한국 밸류체인:",
        "- 투자 관점:",
        "- 한국장 영향:",
        "- 의사결정 영향:",
        "- 영향 섹터:",
        "- 반영/반대:",
        "- 실패 신호:",
        "외 12개",
        "주요 보도 1",
        "💡 판단:",
        "KHS ",
        "## 1.",
        "트럼프 대통령의 직접 발언이 관세, 수출통제",
        "관세/수출주, 반도체/AI",
    ]
    for marker in forbidden:
        if marker in rendered:
            raise AssertionError(f"trusted policy compact render leaked verbose text: {marker}")
    if len(rendered) > 1200:
        raise AssertionError(f"trusted policy Telegram render is too long: {len(rendered)} chars")
    long_lines = [line for line in rendered.splitlines() if len(line) > khs_telegram_delivery_guard.MAX_BODY_LINE_CHARS]
    if long_lines:
        raise AssertionError(f"trusted policy Telegram render has overlong line: {long_lines[0][:120]}")
    assert_compact_prose_limit(rendered, "trusted policy")


def assert_trusted_trump_rate_and_dollar_profiles_are_specific() -> None:
    cases = [
        (
            "Trump: strong dollar sounds good but 'you make a hell of a lot more' with a weaker one - Reuters",
            "트럼프, 강달러 선호에도 약달러 수익 효과 강조",
            "강달러를 선호하지만 약달러가 수익에 유리",
        ),
        (
            "Trump says US interest rate is at least 3 points too high - Reuters",
            "트럼프, 미국 금리 3%p 이상 과도하다고 주장",
            "미국 금리가 최소 3%p 높다며 인하를 요구",
        ),
        (
            "Trump calls for Fed to cut interest rates by one full point - Reuters",
            "트럼프, 연준 금리 인하 필요성 강조",
            "금리 인하에 나서야 한다고",
        ),
    ]
    for headline, expected_title, expected_core in cases:
        profile = khs_trusted_policy_news_watch.trump_story_profile(headline)
        if not profile:
            raise AssertionError(f"Trump rate/dollar headline lacked exact profile: {headline}")
        if profile.get("title") != expected_title:
            raise AssertionError(
                f"Trump rate/dollar title mismatch: {profile.get('title')} != {expected_title}"
            )
        if expected_core not in str(profile.get("core") or ""):
            raise AssertionError(f"Trump rate/dollar core mismatch: {profile.get('core')}")
    ambiguous = "Trump comments on US economy, interest rates and the dollar - Reuters"
    if khs_trusted_policy_news_watch.trump_story_profile(ambiguous):
        raise AssertionError("ambiguous Trump macro headline received a generic policy profile")


def assert_trusted_trump_current_iran_profiles_are_source_faithful() -> None:
    cases = [
        (
            "Trump says he trusts Russia and China's leaders not to enable Iran - Reuters",
            "트럼프, 러시아·중국이 이란 지원하지 않을 것으로 신뢰",
            "러·중 지도자가 이란 지원을 막을 것으로 믿는다고",
        ),
        (
            "Trump vows to punish Iran for Houthi attacks in Red Sea; oil surges over $100 - Reuters",
            "트럼프, 후티 홍해 공격 관련 이란 응징 경고",
            "후티 공격 배후 이란을 경고했고 유가는 100달러",
        ),
    ]
    for headline, expected_title, expected_core in cases:
        profile = khs_trusted_policy_news_watch.trump_story_profile(headline)
        if not profile:
            raise AssertionError(f"current Trump/Iran headline lacked exact profile: {headline}")
        if profile.get("title") != expected_title:
            raise AssertionError(
                f"current Trump/Iran title mismatch: {profile.get('title')} != {expected_title}"
            )
        if expected_core not in str(profile.get("core") or ""):
            raise AssertionError(f"current Trump/Iran core mismatch: {profile.get('core')}")
        if len(str(profile.get("core") or "")) > 50:
            raise AssertionError(f"current Trump/Iran core exceeds 50 chars: {profile.get('core')}")


def assert_trusted_trump_hormuz_open_is_source_faithful_and_deduped() -> None:
    rule = next(
        rule for rule in khs_trusted_policy_news_watch.STORY_RULES
        if rule.key == "trump_direct_policy_remarks_watch"
    )
    item = {
        "title": "Trump says Strait of Hormuz open to commercial traffic - Reuters",
        "source": "Reuters",
        "published_kst": "2026-07-12T22:30:09+09:00",
        "link": "https://example.com/reuters-hormuz-open",
        "priority": 1,
    }
    profile = khs_trusted_policy_news_watch.trump_story_profile(item["title"])
    if not profile:
        raise AssertionError("Reuters Hormuz-open story was not given a concrete Korean profile")
    if profile.get("title") != "트럼프, 호르무즈 해협 상업 통항 가능 발언: 유가·운임 리스크 완화 신호":
        raise AssertionError(f"Hormuz-open title translation is not source-faithful: {profile.get('title')}")
    rendered = khs_trusted_policy_news_watch.render_alert_bundle(
        [{"rule": rule, "items": [item], "fingerprint": "test"}],
        dt.datetime(2026, 7, 13, 9, 0, tzinfo=ZoneInfo("Asia/Seoul")),
    )
    required = [
        "호르무즈 해협 상업 통항 가능 발언",
        "호르무즈 해협이 상업 통항에 열려 있다고",
        "- 핵심:",
        "- 출처:",
    ]
    for marker in required:
        if marker not in rendered:
            raise AssertionError(f"Hormuz-open render missing: {marker}")
    forbidden = [
        "트럼프 에너지 발언",
        "관세/수출주",
        "반도체/AI",
        "전력망/원전",
        "- 투자 관점:",
        "- 한국장 영향:",
        "- 의사결정 영향:",
        "- 영향 섹터:",
        "- 반영/반대:",
        "- 실패 신호:",
    ]
    for marker in forbidden:
        if marker in rendered:
            raise AssertionError(f"Hormuz-open render leaked generic template text: {marker}")
    iran_talks = {
        **item,
        "title": "Trump says US agreed to Iran's request to continue talks, but ceasefire is over - Reuters",
        "published_kst": "2026-07-11T07:25:15+09:00",
        "link": "https://example.com/reuters-iran-talks",
    }
    groups = khs_trusted_policy_news_watch.alert_item_groups(rule, [item, iran_talks])
    if groups != [[item], [iran_talks]]:
        raise AssertionError("different Trump headlines were bundled into one Telegram source chain")
    revised_seen = {khs_trusted_policy_news_watch.fingerprint(rule, [item]): {"first_seen_kst": "2026-07-12T23:01:16+09:00"}}
    if khs_trusted_policy_news_watch.unseen_items_for_rule(rule, [item], revised_seen) != [item]:
        raise AssertionError("corrected Hormuz-open Korean rendering was blocked before one corrective send")
    event_seen = {khs_trusted_policy_news_watch.story_event_fingerprint(rule, [item]): {"first_seen_kst": "2026-07-13T09:00:00+09:00"}}
    updated_item = {**item, "published_kst": "2026-07-13T09:10:00+09:00"}
    if khs_trusted_policy_news_watch.unseen_items_for_rule(rule, [updated_item], event_seen):
        raise AssertionError("same Reuters Hormuz headline re-alerted when only its timestamp changed")
    false_positive = "Trump administration subpoenas New York Times journalists over Air Force One story, newspaper says - Reuters"
    if khs_trusted_policy_news_watch.is_direct_trump_statement_title(false_positive):
        raise AssertionError("third-party newspaper wording was treated as a direct Trump statement")
    if khs_trusted_policy_news_watch.trump_story_profile(false_positive):
        raise AssertionError("Air Force One wording was incorrectly classified as an AI policy story")
    if not khs_trusted_policy_news_watch.is_direct_trump_statement_title(item["title"]):
        raise AssertionError("actual Reuters Trump quote was rejected by the direct-statement gate")


def assert_trusted_heat_mortality_is_source_faithful_and_deduped() -> None:
    rule = next(
        rule for rule in khs_trusted_policy_news_watch.STORY_RULES
        if rule.key == "global_extreme_heat_mortality_watch"
    )
    item = {
        "title": "India heatwave kills at least 120 as power demand hits record - Reuters",
        "source": "Reuters",
        "published_kst": "2026-07-14T09:15:00+09:00",
        "link": "https://example.com/reuters-india-heatwave",
        "priority": 1,
    }
    profile = khs_trusted_policy_news_watch.heat_mortality_story_profile(item["title"])
    if not profile:
        raise AssertionError("high-impact heat mortality headline was not given a source-specific Korean profile")
    if profile.get("title") != "인도, 폭염 사망 120명 보도: 전력수요·전력망 리스크 확인":
        raise AssertionError(f"heat mortality title is not source-faithful: {profile.get('title')}")
    rendered = khs_trusted_policy_news_watch.render_alert_bundle(
        [{"rule": rule, "items": [item], "fingerprint": "heat-test"}],
        dt.datetime(2026, 7, 14, 10, 0, tzinfo=ZoneInfo("Asia/Seoul")),
    )
    required = [
        "인도, 폭염 사망 120명 보도",
        "인도 폭염과 사망 120명 발생",
        "- 핵심:",
        "- 출처:",
    ]
    for marker in required:
        if marker not in rendered:
            raise AssertionError(f"heat mortality render missing source-specific marker: {marker}")
    forbidden = [
        "트럼프",
        "반도체/AI",
        "관세/수출주",
        "- 투자 관점:",
        "- 한국장 영향:",
        "- 의사결정 영향:",
        "- 영향 섹터:",
        "- 반영/반대:",
        "- 실패 신호:",
    ]
    for marker in forbidden:
        if marker in rendered:
            raise AssertionError(f"heat mortality render leaked unrelated template text: {marker}")
    if khs_telegram_delivery_guard.has_source_body_mismatch(
        "KHS 신뢰외신 정책 워치: [상·공식 확인 전] " + str(profile["title"]),
        rendered,
    ):
        raise AssertionError("heat mortality rendering failed the final source/body guard")
    if khs_telegram_delivery_guard.has_long_english_run(rendered):
        raise AssertionError("heat mortality rendering leaked a long raw-English run")
    low_impact = "Local heatwave blamed for one death at a village festival - Reuters"
    if khs_trusted_policy_news_watch.is_heat_mortality_high_impact_title(low_impact):
        raise AssertionError("single local heat death was incorrectly made a high-impact market alert")
    if khs_trusted_policy_news_watch.heat_mortality_story_profile(low_impact):
        raise AssertionError("single local heat death received a high-impact Korean profile")
    if not khs_trusted_policy_news_watch.is_trusted_source("World Health Organization (WHO)"):
        raise AssertionError("WHO was not registered as an official heat-mortality source")
    if not khs_trusted_policy_news_watch.is_trusted_source("World Meteorological Organization (WMO)"):
        raise AssertionError("WMO was not registered as an official heat-mortality source")
    groups = khs_trusted_policy_news_watch.alert_item_groups(rule, [item])
    if groups != [[item]]:
        raise AssertionError("heat mortality headline was not isolated into one source chain")
    seen = {khs_trusted_policy_news_watch.story_event_fingerprint(rule, [item]): {"first_seen_kst": "2026-07-14T09:20:00+09:00"}}
    updated_item = {**item, "published_kst": "2026-07-14T10:20:00+09:00"}
    if khs_trusted_policy_news_watch.unseen_items_for_rule(rule, [updated_item], seen):
        raise AssertionError("same heat mortality headline re-alerted when only its timestamp changed")


def assert_iran_hormuz_story_is_source_faithful_and_cooldown_deduped() -> None:
    rule = next(
        rule for rule in khs_trusted_policy_news_watch.STORY_RULES
        if rule.key == "iran_hormuz_military_escalation"
    )
    item = {
        "title": "US attacks Iran as Tehran retaliates against UAE tankers in Strait of Hormuz and Bahrain - AP News",
        "source": "AP News",
        "published_kst": "2026-07-14T11:38:00+09:00",
        "link": "https://example.com/ap-iran-hormuz-tankers",
        "priority": 7,
    }
    profile = khs_trusted_policy_news_watch.iran_hormuz_story_profile(item["title"])
    if not profile:
        raise AssertionError("Iran/Hormuz wire headline was not given a source-specific Korean profile")
    if profile.get("title") != "미국·이란 공방과 호르무즈 유조선 위협 보도: 유가·운임 리스크":
        raise AssertionError(f"Iran/Hormuz source title was rendered generically: {profile.get('title')}")
    rendered = khs_trusted_policy_news_watch.render_alert_bundle(
        [{"rule": rule, "items": [item], "fingerprint": "iran-hormuz-test"}],
        dt.datetime(2026, 7, 14, 14, 30, tzinfo=ZoneInfo("Asia/Seoul")),
    )
    required = [
        "미국·이란 공방과 호르무즈 유조선 위협 보도",
        "UAE 유조선·바레인 관련 대응",
        "- 핵심:",
        "- 출처:",
    ]
    for marker in required:
        if marker not in rendered:
            raise AssertionError(f"Iran/Hormuz source-specific rendering missing: {marker}")
    forbidden = [
        "미국, 이란 재공격·호르무즈 상선 피격: 휴전·유가 리스크",
        "트럼프",
        "반도체/AI",
    ]
    for marker in forbidden:
        if marker in rendered:
            raise AssertionError(f"Iran/Hormuz rendering leaked generic or unrelated text: {marker}")
    groups = khs_trusted_policy_news_watch.alert_item_groups(rule, [item])
    if groups != [[item]]:
        raise AssertionError("Iran/Hormuz article was not isolated into its own source chain")
    recent_seen = {
        "prior-escalation": {
            "key": rule.key,
            "first_seen_kst": "2026-07-14T14:05:22+09:00",
        }
    }
    if khs_trusted_policy_news_watch.unseen_items_for_rule(rule, [item], recent_seen):
        raise AssertionError("same Iran/Hormuz escalation phase bypassed the six-hour cooldown")
    later_item = {
        **item,
        "title": "US military says it is striking Iran in response to attack on civilian vessel in Strait of Hormuz - AP News",
        "published_kst": "2026-07-14T21:00:00+09:00",
        "link": "https://example.com/ap-iran-civilian-vessel",
    }
    if khs_trusted_policy_news_watch.unseen_items_for_rule(rule, [later_item], recent_seen) != [later_item]:
        raise AssertionError("a materially later Iran/Hormuz escalation was incorrectly blocked after cooldown")
    if khs_trusted_policy_news_watch.iran_hormuz_story_profile("Iran official meets Gulf diplomats - AP News"):
        raise AssertionError("non-escalation Iran headline was incorrectly assigned a market profile")


def assert_state_smr_moc_reaches_policy_lane() -> None:
    item = {
        "source": "State Department office spokesperson",
        "title": "The United States, Japan, and the Republic of Korea Sign a Trilateral Memorandum of Cooperation on Small Modular Reactor Deployments in Other Countries",
        "summary": (
            "U.S. Department of State media note. Secretary of State Marco Rubio, Japanese Foreign Minister "
            "Motegi Toshimitsu, and Republic of Korea Foreign Minister Cho Hyun signed a Memorandum of "
            "Cooperation to accelerate small modular reactor deployments in other countries, initially focused "
            "on the Indo-Pacific. The United States is committing over $10 million in new FIRST Program funding "
            "and announced an industry initiative among GE Vernova, Hitachi, Samsung C&T, and SGE to advance "
            "BWRX-300 SMR deployments across Europe."
        ),
        "link": "https://www.state.gov/releases/office-of-the-spokesperson/2026/07/the-united-states-japan-and-the-republic-of-korea-sign-a-trilateral-memorandum-of-cooperation-on-small-modular-reactor-deployments-in-other-countries",
        "published_kst": "2026-07-07T00:00:00+09:00",
    }
    classified = khs_policy_watch.classify_item(item)
    if not classified:
        raise AssertionError("State Department SMR MOC was not classified as a policy alert")
    if "state_smr_moc_policy" not in (classified.get("matched") or {}):
        raise AssertionError(f"State Department SMR MOC missing state_smr_moc_policy match: {classified.get('matched')}")
    classified["sectors"] = khs_policy_alert_guardrails.direct_sectors(classified)
    khs_policy_alert_guardrails.ensure_explained(classified)
    if not khs_policy_alert_guardrails.has_actionable_decision_impact(classified):
        raise AssertionError("State Department SMR MOC was dropped by policy decision-impact guardrail")
    rendered = khs_policy_alert_router.render_policy_report(
        [classified],
        dt.datetime(2026, 7, 8, 22, 20, tzinfo=ZoneInfo("Asia/Seoul")),
    )
    required = [
        "미·일·한, 제3국 SMR 배치 협력 MOC 체결",
        "삼성물산",
        "BWRX-300",
        "FIRST",
        "확정 매출 확인 불가",
        "원전/SMR",
        "미 국무부 대변인실",
    ]
    for marker in required:
        if marker not in rendered:
            raise AssertionError(f"State Department SMR MOC render missing: {marker}")
    forbidden = [
        "The United States, Japan, and the Republic of Korea Sign",
        "- 원제:",
        "State Department office spokesperson",
    ]
    for marker in forbidden:
        if marker in rendered:
            raise AssertionError(f"State Department SMR MOC raw text leaked: {marker}")


def assert_state_smr_moc_trusted_news_fallback_is_not_overfiltered() -> None:
    rule = next(
        rule for rule in khs_trusted_policy_news_watch.STORY_RULES
        if rule.key == "us_japan_korea_smr_moc_state_watch"
    )
    publisher = "Aju Press"
    query = '"United States" "Japan" "Republic of Korea" "Small Modular Reactor" "Memorandum of Cooperation" "Samsung C&T"'
    haystack = " ".join([
        "Seoul, Washington, Tokyo forge SMR export alliance - Aju Press",
        publisher,
        "Seoul, Washington, Tokyo forge SMR export alliance Aju Press",
        query,
    ])
    if not khs_trusted_policy_news_watch.is_rule_trusted_source(publisher, rule):
        raise AssertionError("State SMR MOC fallback source was not rule-trusted")
    if not khs_trusted_policy_news_watch.has_required_terms(haystack, rule):
        raise AssertionError("State SMR MOC fallback query terms were overfiltered")


def assert_boem_space_launch_is_excluded() -> None:
    item = {
        "source": "BOEM news",
        "title": "BOEM Initiates First Step to Explore Potential for Outer Continental Shelf Space Launch & Recovery",
        "summary": "BOEM initiates first step to explore potential Outer Continental Shelf space launch and recovery.",
        "link": "https://www.boem.gov/newsroom/press-releases/boem-initiates-first-step-explore-potential-outer-continental-shelf-space",
        "matched": {"agency_order": ["outer continental shelf", "space launch"]},
    }
    if not khs_policy_alert_guardrails.is_low_impact_false_positive(item):
        raise AssertionError("BOEM OCS space launch/recovery item was not excluded")


def assert_boem_arctic_drilling_is_source_faithful() -> None:
    item = {
        "source": "BOEM news",
        "title": "Department of the Interior Proposes Targeted Updates to Arctic Exploratory Drilling Rule to Advance American Energy Dominance",
        "link": "https://www.boem.gov/newsroom/press-releases/department-interior-proposes-targeted-updates-arctic-exploratory-drilling",
        "summary": "The proposed rule revises the 2016 Arctic Exploratory Drilling Rule and starts a 90-day public comment period.",
        "source_body": (
            "The proposal updates blowout preventer monitoring, source control and containment equipment, "
            "relief rig capability and the Integrated Operations Plan. It does not approve any specific lease, "
            "exploration plan, permit or drilling activity. A 90-day public comment period will begin."
        ),
        "body_verified": True,
        "matched": {"final_rule": ["proposed rule"]},
    }
    explained = khs_policy_alert_explainer.ensure_explained(item)
    if explained.get("title_ko") != "미 내무부, 북극해 탐사시추 규제 완화안 발표":
        raise AssertionError(f"BOEM Arctic title mismatch: {explained.get('title_ko')}")
    core = str(explained.get("policy_plain_summary") or "")
    for marker in ("2016년", "90일", "승인한 것은 아닙니다"):
        if marker not in core:
            raise AssertionError(f"BOEM Arctic summary missing: {marker}")
    if "트럼프 대통령 발언" in core or "트럼프 대통령 발언" in str(explained.get("title_ko") or ""):
        raise AssertionError("BOEM Arctic release reused generic Trump profile")


def assert_delivery_guard_blocks_duplicate_policy_alerts() -> None:
    cleanup()
    title_path = OUT_DIR / "khs_policy_watch_alert_title.txt"
    body_path = OUT_DIR / "khs_policy_watch_alert.md"
    title_path.write_text("KHS 정책 워치: [상] 국내 디지털자산 정책 중복 테스트\n", encoding="utf-8")
    body_path.write_text(
        "\n".join([
            "🚨 KHS 정책·규제 고충격 워치 · 2026년 07월 06일 22:05 KST",
            "",
            "## 1. [상·확정] 국내 디지털자산 정책: 스테이블코인 예금 대체·준비자산 규제 체크",
            "- 핵심: 원화 스테이블코인·디지털자산 입법은 금융 인프라 재편 이슈입니다.",
            "- 의사결정 영향: 시간표, 수급, 밸류에이션/할인율",
            "- 투자 영향: 지금 붙는 자금은 실적보다 미래 결제 표준 베팅입니다.",
            "- 한국장: 은행, 핀테크, 결제, 가상자산거래소를 봅니다.",
            "- 반영 가능성: 중간.",
            "- 실패 신호: 발행 주체가 좁게 제한되면 테마 확산이 약해집니다.",
            "- 출처: [Bank of Korea digital currency policy](https://www.bok.or.kr/a) · 조회 22:05 KST",
            "",
            "## 2. [상·확정] 국내 디지털자산 정책: 스테이블코인 예금 대체·준비자산 규제 체크",
            "- 핵심: 원화 스테이블코인·디지털자산 입법은 금융 인프라 재편 이슈입니다.",
            "- 의사결정 영향: 시간표, 수급, 밸류에이션/할인율",
            "- 투자 영향: 지금 붙는 자금은 실적보다 미래 결제 표준 베팅입니다.",
            "- 한국장: 은행, 핀테크, 결제, 가상자산거래소를 봅니다.",
            "- 반영 가능성: 중간.",
            "- 실패 신호: 발행 주체가 좁게 제한되면 테마 확산이 약해집니다.",
            "- 출처: [Bank of Korea payment research](https://www.bok.or.kr/b) · 조회 22:05 KST",
            "",
        ]),
        encoding="utf-8",
    )
    khs_telegram_delivery_guard.main()
    if body_path.exists():
        raise AssertionError("delivery guard did not block duplicate policy alerts")


def assert_delivery_guard_compacts_and_sends_51_character_prose() -> None:
    exact_value = "가" * 50
    exact_body, exact_changes = compact_prose_lines(f"- 핵심: {exact_value}")
    if exact_body != f"- 핵심: {exact_value}" or exact_changes:
        raise AssertionError("exact 50-character summary was changed")

    over_value = "나" * 51
    over_body, over_changes = compact_prose_lines(f"- 핵심: {over_value}")
    over_summary = over_body.removeprefix("- 핵심: ").strip()
    if over_changes != 1 or len(over_summary) > 50:
        raise AssertionError("exact 51-character summary was not compacted")

    cleanup()
    lane = next(
        item
        for item in khs_telegram_delivery_guard.LANES
        if item.name == "trusted_policy_news"
    )
    lane.title.write_text(
        "KHS 신뢰외신 정책 워치: [상] 미국, 반도체 수출통제 확대 검토\n",
        encoding="utf-8",
    )
    lane.body.write_text(
        "\n".join([
            "2026년 07월 23일 20:00 KST",
            "",
            "1. [상·예비] 미국, 반도체 수출통제 확대 검토",
            (
                "- 핵심: 미국이 첨단 반도체 장비 수출통제를 확대해 한국 기업의 "
                "중국 공장 증설과 장비 반입 일정을 다시 점검하게 됐습니다."
            ),
            (
                "- 출처: [Reuters](https://www.reuters.com/world/us/"
                "semiconductor-export-controls-example/) · 조회 20:00 KST"
            ),
            "",
        ]),
        encoding="utf-8",
    )
    try:
        khs_telegram_delivery_guard.guard_lane(lane)
        if not lane.body.exists():
            raise AssertionError("51-character prose caused the alert to be deleted")
        compacted = lane.body.read_text(encoding="utf-8")
        assert_compact_prose_limit(compacted, "51-character delivery fixture")
        if "미국이 첨단 반도체 장비 수출통제를" not in compacted:
            raise AssertionError("51-character summary lost its source-specific subject")
        for forbidden in (
            "- 투자 관점:",
            "- 한국장 영향:",
            "- 의사결정 영향:",
            "- 영향 섹터:",
            "- 반영/반대:",
            "- 실패 신호:",
        ):
            if forbidden in compacted:
                raise AssertionError(f"compact trusted-policy alert leaked removed field: {forbidden}")
    finally:
        for path in (lane.title, lane.body, lane.json):
            if path and path.exists():
                path.unlink()
        cleanup()

    decimal_summary = concise_text(
        "HBM4 계약가는 4.5% 인상될 수 있습니다. 후속 협상 확인이 필요합니다.",
    )
    if "4.5%" not in decimal_summary or len(decimal_summary) > 50:
        raise AssertionError(f"compact summary damaged a decimal value: {decimal_summary}")


def assert_auxiliary_policy_lanes_are_compact() -> None:
    now = dt.datetime(2026, 7, 23, 20, 0, tzinfo=ZoneInfo("Asia/Seoul"))
    nuclear = khs_nuclear_policy_watch.render(
        [{
            "source": "DOE Nuclear Energy",
            "title": "9 Key Takeaways from President Trump's Executive Orders on Nuclear Energy",
            "link": "https://www.energy.gov/ne/example",
            "published_kst": "2026-07-23T00:00:00+09:00",
            "matched": [
                "westinghouse",
                "ap1000",
                "nuclear reactor",
                "data center",
                "department of energy",
            ],
        }],
        now,
    )
    assert_compact_prose_limit(nuclear, "nuclear policy")

    personnel = "\n".join(
        korea_presidential_postprocess.render_personnel(
            1,
            {
                "source": "대한민국 정책브리핑",
                "title": "금융위원장 인사 발표",
                "summary": "김정책 금융위원장 임명을 공식 발표했습니다.",
                "link": "",
                "published_kst": "2026-07-23T00:00:00+09:00",
            },
            now,
        )
    )
    assert_compact_prose_limit(personnel, "Korea presidential personnel")


def assert_delivery_guard_blocks_source_body_mismatch() -> None:
    cleanup()
    title_path = OUT_DIR / "khs_policy_watch_alert_title.txt"
    body_path = OUT_DIR / "khs_policy_watch_alert.md"
    title = "KHS 정책 워치: [상] FCC, 통신·주파수·위성 규제 문서 공표\n"
    required_lines = required_explanation_lines("FCC inverter policy regression check")
    body = "\n".join([
        "KHS policy watch source/body mismatch regression",
        "",
        "## 1. [상·확정] FCC, 통신·주파수·위성 규제 문서 공표",
        "- 핵심: 미국 FCC가 외국산 에너지 인버터 제한을 검토한다는 본문입니다.",
        *required_lines,
        "- 출처: [미 BOEM](https://www.boem.gov/newsroom/press-releases/boem-initiates-first-step-explore-potential-outer-continental-shelf-space) · 조회 23:05 KST",
        "",
    ])
    title_path.write_text(title, encoding="utf-8")
    body_path.write_text(body, encoding="utf-8")
    reason = khs_telegram_delivery_guard.has_source_body_mismatch(title, body)
    if reason != "boem_source_with_fcc_body":
        raise AssertionError(f"source/body mismatch was not detected: {reason}")
    khs_telegram_delivery_guard.main()
    if body_path.exists():
        raise AssertionError("delivery guard did not block BOEM source with FCC body")


def assert_delivery_guard_blocks_fcc_submarine_inverter_mismatch() -> None:
    cleanup()
    title_path = OUT_DIR / "khs_policy_watch_alert_title.txt"
    body_path = OUT_DIR / "khs_policy_watch_alert.md"
    title = "KHS 정책 워치: [상] FCC, 통신·주파수·위성 규제 문서 공표\n"
    required_lines = required_explanation_lines("FCC submarine cable/inverter mismatch regression check")
    body = "\n".join([
        "🚨 KHS 정책·규제 고충격 워치 · 2026년 07월 08일 15:18 KST",
        "",
        "## 1. [상·확정] FCC, 통신·주파수·위성 규제 문서 공표",
        "- 핵심: 미국 FCC가 국가안보 우려를 이유로 외국산 또는 중국산 에너지 인버터 신규 수입 제한·금지 조치를 검토 중이라는 내용입니다.",
        *required_lines,
        "- 출처: [미 연방관보 FCC](https://www.federalregister.gov/documents/2026/07/08/2026-13765/review-of-submarine-cable-landing-license-rules-and-procedures-to-assess-evolving-national-security) · 조회 15:18 KST",
        "",
    ])
    title_path.write_text(title, encoding="utf-8")
    body_path.write_text(body, encoding="utf-8")
    reason = khs_telegram_delivery_guard.has_source_body_mismatch(title, body)
    expected = "fcc_submarine_cable_source_with_inverter_or_equipment_ban_body"
    if reason != expected:
        raise AssertionError(f"FCC submarine/source body mismatch was not detected: {reason}")
    khs_telegram_delivery_guard.main()
    if body_path.exists():
        raise AssertionError("delivery guard did not block FCC submarine cable source with inverter body")


def assert_delivery_guard_blocks_bok_generic_stablecoin_mismatch() -> None:
    cleanup()
    title_path = OUT_DIR / "khs_policy_watch_alert_title.txt"
    body_path = OUT_DIR / "khs_policy_watch_alert.md"
    title = "KHS 정책 워치: [상] 국내 디지털자산 정책: 스테이블코인 예금 대체·준비자산 규제 체크\n"
    required_lines = required_explanation_lines("BOK generic page/stablecoin mismatch regression check")
    body = "\n".join([
        "🚨 KHS 정책·규제 고충격 워치 · 2026년 07월 09일 12:13 KST",
        "",
        "## 1. [상·확정] 국내 디지털자산 정책: 스테이블코인 예금 대체·준비자산 규제 체크",
        "- 핵심: 원화 스테이블코인·디지털자산 입법은 발행 주체, 준비자산, 지급결제 표준을 둘러싼 금융 인프라 재편 이슈입니다.",
        *required_lines,
        "- 출처: [Bank of Korea digital currency policy](https://www.bok.or.kr/portal/submain/submain/fnncSafety.do?menuNo=201652) · 조회 12:13 KST",
        "",
    ])
    title_path.write_text(title, encoding="utf-8")
    body_path.write_text(body, encoding="utf-8")
    reason = khs_telegram_delivery_guard.has_source_body_mismatch(title, body)
    expected = "bok_generic_page_with_stablecoin_policy_body"
    if reason != expected:
        raise AssertionError(f"BOK generic/source body mismatch was not detected: {reason}")
    khs_telegram_delivery_guard.main()
    if body_path.exists():
        raise AssertionError("delivery guard did not block BOK generic page with stablecoin policy body")


def assert_delivery_guard_blocks_url_topic_missing() -> None:
    cases = [
        (
            "KHS 정책 워치: [상] 트럼프 대통령 발언, 시장 영향 정책 신호\n",
            "트럼프 대통령의 직접 발언이 관세, 반도체, 이란 전쟁위험을 움직일 수 있다는 일반 템플릿입니다.",
            "https://www.whitehouse.gov/fact-sheets/2026/07/fact-sheet-president-donald-j-trump-secures-historic-defense-investment-from-nato-allies-powering-american-industry/",
            "source_topic_missing:nato_defense_investment",
        ),
        (
            "KHS 정책 워치: [상] FCC, 통신·주파수·위성 규제 문서 공표\n",
            "FCC 통신·주파수·위성 규제 문서는 통신 인프라 정책 시간표를 바꿀 수 있다는 일반 템플릿입니다.",
            "https://www.federalregister.gov/documents/2026/07/08/2026-13765/review-of-submarine-cable-landing-license-rules-and-procedures-to-assess-evolving-national-security",
            "source_topic_missing:submarine_cable",
        ),
    ]
    for title, core, link, expected in cases:
        cleanup()
        title_path = OUT_DIR / "khs_policy_watch_alert_title.txt"
        body_path = OUT_DIR / "khs_policy_watch_alert.md"
        required_lines = required_explanation_lines("URL topic missing regression check")
        body = "\n".join([
            "🚨 KHS 정책·규제 고충격 워치 · 2026년 07월 09일 12:30 KST",
            "",
            "## 1. [상·확정] 출처 주제 누락 회귀 테스트",
            f"- 핵심: {core}",
            *required_lines,
            f"- 출처: [공식 출처]({link}) · 조회 12:30 KST",
            "",
        ])
        title_path.write_text(title, encoding="utf-8")
        body_path.write_text(body, encoding="utf-8")
        reason = khs_telegram_delivery_guard.has_source_body_mismatch(title, body)
        if reason != expected:
            raise AssertionError(f"URL topic missing mismatch was not detected: {reason} != {expected}")
        khs_telegram_delivery_guard.main()
        if body_path.exists():
            raise AssertionError(f"delivery guard did not block URL topic missing case: {expected}")


def assert_router_explains_fcc_submarine_cable_policy() -> None:
    item = {
        "source": "Federal Register FCC",
        "title": "Review of Submarine Cable Landing License Rules and Procedures To Assess Evolving National Security",
        "original_title": "Review of Submarine Cable Landing License Rules and Procedures To Assess Evolving National Security",
        "link": "https://www.federalregister.gov/documents/2026/07/08/2026-13765/review-of-submarine-cable-landing-license-rules-and-procedures-to-assess-evolving-national-security",
        "importance": "상",
        "status": "확정",
        "published_kst": "2026-07-08T09:00:00+09:00",
        "matched": {"fcc_decision_notice": ["national security", "rulemaking"]},
        "impacts": ["시간표", "할인율"],
        "paths": ["정책 타임라인", "할인율"],
        "sectors": ["통신/FCC/위성"],
    }
    enriched = khs_policy_alert_router.enrich_missing_context(item)
    khs_policy_alert_router.apply_router_overrides(enriched)
    title = khs_policy_alert_router.safe_title(enriched)
    fields = " ".join(
        str(enriched.get(key) or "")
        for key in ("policy_plain_summary", "investment_view", "korea_market_impact", "sectors")
    ).lower()
    if "해저케이블" not in title and "해저 통신케이블" not in fields:
        raise AssertionError("FCC submarine cable policy was not routed to submarine cable explanation")
    forbidden = ["inverter", "energy inverter", "solar inverter", "인버터", "전력변환장치"]
    for token in forbidden:
        if token.lower() in fields:
            raise AssertionError(f"FCC submarine cable explanation leaked inverter body: {token}")



def assert_domestic_telecom_title_gate_and_semantic_dedupe() -> None:
    dirty_title = "알뜰폰도 '데이터 안심옵션' 도입…다 써도 계속 쓴다 단계하락 1"
    clean_title = khs_domestic_telecom_policy_watch.clean_link_title(dirty_title)
    if clean_title != "알뜰폰도 '데이터 안심옵션' 도입…다 써도 계속 쓴다":
        raise AssertionError(f"telecom accessibility label was not removed: {clean_title}")

    false_titles = [
        "한-아르헨, 핵심광물 협력 MOU 체결…중남미 공급망 협력 본격화 NEW",
        "보훈의료대상자, 인근 병·의원 등 치매 치료비 지원 받을 수 있어",
        "국내 첫 한국형 이지스구축함 건조 본격화",
    ]
    for title in false_titles:
        if khs_domestic_telecom_policy_watch.has_any(
            title,
            khs_domestic_telecom_policy_watch.TITLE_TELECOM_TERMS,
        ):
            raise AssertionError(f"unrelated title passed telecom title gate: {title}")

    true_titles = [
        "알뜰폰도 데이터 안심옵션 도입…다 써도 계속 쓴다",
        "정부, 가계통신비 부담 완화 위한 요금제 개편 발표",
    ]
    for title in true_titles:
        if not khs_domestic_telecom_policy_watch.has_any(
            title,
            khs_domestic_telecom_policy_watch.TITLE_TELECOM_TERMS,
        ):
            raise AssertionError(f"telecom title was blocked: {title}")

    first = khs_domestic_telecom_policy_watch.telecom_event_fingerprint(
        "정부, 통신비 인하 정책 압박 확인",
        "가계통신비 부담 완화 방안을 논의했습니다.",
    )
    second = khs_domestic_telecom_policy_watch.telecom_event_fingerprint(
        "가계통신비 부담 완화 논의",
        "통신요금 개편 가능성을 검토했습니다.",
    )
    if first != second:
        raise AssertionError("generic telecom pressure event did not keep one semantic key")

    concrete = khs_domestic_telecom_policy_watch.telecom_event_fingerprint(
        "알뜰폰 데이터 안심옵션 8월 시행",
        "알뜰폰 데이터 안심옵션을 8월부터 시행합니다.",
    )
    if concrete == first:
        raise AssertionError("concrete telecom implementation collapsed into generic pressure event")

    mvno_first = khs_domestic_telecom_policy_watch.telecom_event_fingerprint(
        dirty_title,
        "정부가 알뜰폰 데이터 안심옵션을 도입합니다.",
    )
    mvno_second = khs_domestic_telecom_policy_watch.telecom_event_fingerprint(
        "알뜰폰 데이터 안심옵션 시행",
        "데이터 소진 뒤에도 저속으로 계속 이용할 수 있습니다.",
    )
    if mvno_first != mvno_second:
        raise AssertionError("same MVNO data-safety policy produced duplicate semantic keys")

    evidence = khs_domestic_telecom_policy_watch.policy_evidence_summary(
        "알뜰폰도 데이터 안심옵션 도입",
        "관련기사 삼성전자 신제품 출시.\n정부는 알뜰폰 데이터 안심옵션을 8월부터 도입한다.",
    )
    if "8월부터 도입" not in evidence or "삼성전자 신제품" in evidence:
        raise AssertionError(f"telecom evidence extraction mismatch: {evidence}")

    alert = {
        "source": "Korea Policy Briefing telecom policy",
        "title": dirty_title,
        "original_title": dirty_title,
        "link": "https://www.korea.kr/news/policyNewsView.do?newsId=148969169",
        "importance": "상",
        "status": "확정",
        "summary": "정부가 알뜰폰 데이터 안심옵션을 도입합니다.",
        "policy_plain_summary": "정부가 알뜰폰 데이터 안심옵션을 도입합니다.",
        "matched": {"korea_telecom_policy": ["알뜰폰", "데이터 안심옵션"]},
        "impacts": ["매출·마진·현금흐름", "시간표"],
        "sectors": ["국내 통신정책/통신3사"],
    }
    khs_policy_alert_router.apply_router_overrides(alert)
    expected_title = "정부, 알뜰폰 데이터 안심옵션 도입"
    expected_core = "정부가 알뜰폰 데이터 소진 뒤에도 저속 이용 가능한 안심옵션을 도입했습니다."
    if khs_policy_alert_router.safe_title(alert) != expected_title:
        raise AssertionError(f"MVNO title mismatch: {khs_policy_alert_router.safe_title(alert)}")
    if alert.get("policy_plain_summary") != expected_core:
        raise AssertionError(f"MVNO core mismatch: {alert.get('policy_plain_summary')}")
    report = khs_policy_alert_router.render_policy_report(
        [alert],
        dt.datetime(2026, 8, 1, 18, 12, tzinfo=ZoneInfo("Asia/Seoul")),
    )
    formatted_title, formatted_body = khs_policy_telegram_formatter.format_policy_message(
        "정책 워치: [상] 정부, 알뜰폰 데이터 안심옵션 도입",
        report,
    )
    errors = khs_policy_telegram_formatter.validate_final_policy_message(
        formatted_title,
        formatted_body,
    )
    if errors:
        raise AssertionError(f"MVNO final Telegram format failed: {errors}")
    if "단계하락" in formatted_body or expected_core not in formatted_body:
        raise AssertionError("MVNO final Telegram message lost the cleaned source-specific core")


def assert_router_explains_current_fcc_documents() -> None:
    cases = [
        (
            {
                "source": "Federal Register FCC",
                "title": "Auction of Flexible Use Licenses in the Upper C-Band for Next-Generation Wireless Services Scheduled",
                "original_title": "Auction of Flexible Use Licenses in the Upper C-Band for Next-Generation Wireless Services Scheduled",
                "link": "https://www.federalregister.gov/documents/2026/08/03/2026-15725/auction-of-flexible-use-licenses-in-the-upper-c-band-for-next-generation-wireless-services-scheduled",
                "importance": "상",
                "status": "확정",
                "published_kst": "2026-08-03T09:00:00+09:00",
                "matched": {"fcc_decision_notice": ["auction", "upper c-band"]},
                "impacts": ["시간표"],
                "paths": ["정책 타임라인"],
                "sectors": ["통신/FCC/위성"],
            },
            "FCC, 상단 C대역 차세대 무선통신 주파수 경매 일정 공표",
            "상단 C대역 100MHz 이상 면허",
        ),
        (
            {
                "source": "Federal Register FCC",
                "title": "Seeking Comment on Prohibiting the Importation and Marketing of Certain Foreign-Produced Communications Equipment",
                "original_title": "Seeking Comment on Prohibiting the Importation and Marketing of Certain Foreign-Produced Communications Equipment",
                "link": "https://www.federalregister.gov/documents/2026/08/03/2026-15659/seeking-comment-on-prohibiting-the-importation-and-marketing-of-certain-foreign-produced",
                "importance": "상",
                "status": "확정",
                "published_kst": "2026-08-03T09:00:00+09:00",
                "matched": {"fcc_decision_notice": ["covered list", "national security", "prohibit"]},
                "impacts": ["매출·마진·현금흐름", "수급", "시간표"],
                "paths": ["정책 타임라인", "공급망"],
                "sectors": ["통신/FCC/위성"],
            },
            "FCC, 외국산 군용급 무인기·핵심부품 수입·판매 금지안 의견수렴",
            "외국산 군용 무인기(UAS)·핵심부품",
        ),
    ]
    routed = []
    for alert, expected_title, expected_core in cases:
        khs_policy_alert_router.apply_router_overrides(alert)
        actual_title = khs_policy_alert_router.safe_title(alert)
        core = str(alert.get("policy_plain_summary") or "")
        if actual_title != expected_title:
            raise AssertionError(f"FCC title mismatch: {actual_title} != {expected_title}")
        if expected_core not in core:
            raise AssertionError(f"FCC core mismatch: {core}")
        routed.append(alert)

    semantic_keys = [
        khs_policy_alert_router.semantic_alert_key(alert)
        for alert in routed
    ]
    if len(set(semantic_keys)) != len(semantic_keys):
        raise AssertionError(f"distinct FCC documents collapsed to one semantic key: {semantic_keys}")

    for alert, expected_title, expected_core in cases:
        report = khs_policy_alert_router.render_policy_report(
            [alert],
            dt.datetime(2026, 8, 1, 15, 59, tzinfo=ZoneInfo("Asia/Seoul")),
        )
        if expected_title not in report or expected_core not in report:
            raise AssertionError(f"FCC rendered report lost source-specific content: {expected_title}")
        if "투자 조언이 아닌 참고용 정책·규제 알림입니다." in report:
            raise AssertionError("removed policy disclaimer leaked into router output")


def cleanup() -> None:
    for path in POLICY_FILES:
        if path.exists():
            path.unlink()


def required_explanation_lines(note: str) -> list[str]:
    return [
        f"{markers[0]} {note}"
        for markers in khs_telegram_delivery_guard.REQUIRED_EXPLANATION_FIELD_GROUPS
    ]


def write_fcc_regression_fixture() -> None:
    alerts = [
        {
            "source": "Federal Register FCC",
            "title": "Petition for Reconsideration of Action in Rulemaking Proceeding",
            "original_title": "Petition for Reconsideration of Action in Rulemaking Proceeding",
            "link": "https://www.federalregister.gov/documents/2026/07/06/2026-13611/petition-for-reconsideration-of-action-in-rulemaking-proceeding",
            "importance": "상",
            "status": "확정",
            "published_kst": "2026-07-06T09:00:00+09:00",
            "matched": {"fcc_decision_notice": ["proposed rule", "rulemaking"]},
            "impacts": ["시간표", "수급"],
            "paths": ["정책 타임라인", "주파수/통신 규제", "수급"],
            "sectors": ["통신/FCC/위성", "통신장비", "위성통신"],
        },
        {
            "source": "Federal Register FCC",
            "title": "Prohibiting Importation and Marketing of Previously Authorized Covered Communications Equipment Added to the Covered List",
            "original_title": "Prohibiting Importation and Marketing of Previously Authorized Covered Communications Equipment Added to the Covered List",
            "link": "https://www.federalregister.gov/documents/2026/07/06/2026-13518/prohibiting-importation-and-marketing-of-previously-authorized-covered-communications-equipment",
            "importance": "상",
            "status": "확정",
            "published_kst": "2026-07-06T09:00:00+09:00",
            "matched": {"fcc_decision_notice": ["covered list", "national security", "prohibit", "public notice"]},
            "impacts": ["매출·마진·현금흐름", "수급", "시간표"],
            "paths": ["정책 타임라인", "공급망", "밸류체인", "수급"],
            "sectors": ["통신장비", "위성통신", "네트워크 장비"],
        },
    ]
    (OUT_DIR / "khs_policy_watch_alerts.json").write_text(
        json.dumps(alerts, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def assert_policy_output() -> None:
    body_path = OUT_DIR / "khs_policy_watch_alert.md"
    if not body_path.exists():
        raise AssertionError("policy alert body was removed unexpectedly")
    body = body_path.read_text(encoding="utf-8-sig")
    lines = body.splitlines()

    must_contain = [
        "FCC, 보안 위험 통신장비 수입·판매 제한 절차 공표",
        "- 핵심:",
        "- 출처:",
    ]
    for marker in must_contain:
        if marker not in body:
            raise AssertionError(f"missing compact Telegram marker: {marker}")

    forbidden = [
        "- 원제:",
        "- 상태 변화:",
        "- 즉시 체크:",
        "Petition for Reconsideration",
        "Prohibiting Importation and Marketing",
        "Previously Authorized Covered Communications Equipment",
        "인버터",
        "inverter",
        "신뢰외신",
        "fcc_decision_notice",
        "KHS ",
        "## 1.",
        "- 투자 관점:",
        "- 투자 영향:",
        "- 투자 포인트:",
        "- 한국장 영향:",
        "- 한국장:",
        "- 영향 섹터:",
        "- 의사결정 영향:",
        "- 반영/반대:",
        "- 실패 신호:",
        "Actions:",
        "Issues:",
    ]
    low = body.lower()
    for marker in forbidden:
        haystack = low if marker.islower() else body
        needle = marker if marker.islower() else marker
        if needle in haystack:
            raise AssertionError(f"forbidden Telegram text leaked: {marker}")

    long_lines = [line for line in lines if len(line) > khs_telegram_delivery_guard.MAX_BODY_LINE_CHARS]
    if long_lines:
        raise AssertionError(f"overlong Telegram line leaked: {long_lines[0][:120]}")

    alert_count = sum(1 for line in lines if line.startswith("1. ["))
    if alert_count != 1:
        raise AssertionError(f"expected only one delivered alert, got {alert_count}")
    title = (OUT_DIR / "khs_policy_watch_alert_title.txt").read_text(encoding="utf-8-sig")
    if title.startswith("KHS "):
        raise AssertionError("KHS branding remained in the final Telegram title")
    format_errors = khs_policy_telegram_formatter.validate_final_policy_message(title, body)
    if format_errors:
        raise AssertionError(f"general policy final format failed: {format_errors}")
    assert_compact_prose_limit(body, "general policy")


if __name__ == "__main__":
    raise SystemExit(main())
