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
            "서명 …15523 tokens truncated…
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
