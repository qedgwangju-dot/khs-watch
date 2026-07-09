#!/usr/bin/env python3
"""Contract tests for KHS policy Telegram delivery quality.

These checks encode regressions that already reached Telegram once:
raw English titles, low-impact FCC administrative notices, and wrong sector
explanations. The workflow runs this before sending Telegram alerts.
"""

from __future__ import annotations

import datetime as dt
import json
from pathlib import Path
from zoneinfo import ZoneInfo

import khs_policy_alert_guardrails
import khs_policy_alert_router
import khs_domestic_stablecoin_policy_watch
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
    assert_foreign_first_policy_sources()
    assert_stablecoin_watch_rejects_bok_generic_page()
    assert_stablecoin_semantic_dedupe()
    assert_router_final_semantic_dedupe()
    assert_router_keeps_source_families_separate()
    assert_trump_statement_reaches_policy_lane()
    assert_nato_defense_fact_sheet_is_not_generic_trump_alert()
    assert_trump_iran_war_statement_reaches_geopolitical_lane()
    assert_state_smr_moc_reaches_policy_lane()
    assert_state_smr_moc_trusted_news_fallback_is_not_overfiltered()
    assert_boem_space_launch_is_excluded()
    assert_delivery_guard_blocks_duplicate_policy_alerts()
    assert_delivery_guard_blocks_source_body_mismatch()
    assert_delivery_guard_blocks_fcc_submarine_inverter_mismatch()
    assert_delivery_guard_blocks_bok_generic_stablecoin_mismatch()
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


def assert_workflow_delivery_dedupe() -> None:
    workflow = POLICY_WORKFLOW.read_text(encoding="utf-8")
    required = [
        "KHS_TELEGRAM_DEDUPE_HOURS",
        "data/khs_telegram_delivery_seen.json",
        "hashlib.sha256(canonical_message(title, body).encode(\"utf-8\"))",
        "semantic_parts = [\"semantic\"]",
        "urllib.parse.urldefrag",
        "telegram_duplicate_skipped",
        "Commit Telegram delivery dedupe state",
    ]
    for marker in required:
        if marker not in workflow:
            raise AssertionError(f"KHS policy workflow missing Telegram delivery dedupe marker: {marker}")


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


def assert_trump_statement_reaches_policy_lane() -> None:
    item = {
        "source": "White House remarks",
        "title": "Remarks by President Donald J. Trump on Semiconductor Tariffs and China",
        "summary": "White House Trump Remarks official page link: Remarks by President Donald J. Trump on Semiconductor Tariffs and China",
        "link": "https://www.whitehouse.gov/remarks/2026/07/remarks-by-president-donald-j-trump-on-semiconductor-tariffs-and-china/",
        "published_kst": "2026-07-08T00:00:00+09:00",
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
        "link": "https://www.whitehouse.gov/fact-sheets/2026/07/fact-sheet-president-donald-j-trump-secures-historic-defense-investment-from-nato-allies-powering-american-industry/",
        "published_kst": "2026-07-08T00:00:00+09:00",
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
        "link": "https://www.whitehouse.gov/remarks/2026/07/remarks-by-president-donald-j-trump-on-iran-israel-and-the-strait-of-hormuz/",
        "published_kst": "2026-07-08T00:00:00+09:00",
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


def assert_delivery_guard_blocks_source_body_mismatch() -> None:
    cleanup()
    title_path = OUT_DIR / "khs_policy_watch_alert_title.txt"
    body_path = OUT_DIR / "khs_policy_watch_alert.md"
    title = "KHS 정책 워치: [상] FCC, 통신·주파수·위성 규제 문서 공표\n"
    required_lines = [
        f"{marker} FCC inverter policy regression check"
        for marker in khs_telegram_delivery_guard.REQUIRED_EXPLANATION_FIELDS
    ]
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
    required_lines = [
        f"{marker} FCC submarine cable/inverter mismatch regression check"
        for marker in khs_telegram_delivery_guard.REQUIRED_EXPLANATION_FIELDS
    ]
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
    required_lines = [
        f"{marker} BOK generic page/stablecoin mismatch regression check"
        for marker in khs_telegram_delivery_guard.REQUIRED_EXPLANATION_FIELDS
    ]
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


def cleanup() -> None:
    for path in POLICY_FILES:
        if path.exists():
            path.unlink()


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
        "- 의사결정 영향:",
        "- 투자 영향:",
        "- 한국장:",
        "- 반영 가능성:",
        "- 반대 근거:",
        "- 실패 신호:",
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

    alert_count = sum(1 for line in lines if line.startswith("## "))
    if alert_count != 1:
        raise AssertionError(f"expected only one delivered alert, got {alert_count}")


if __name__ == "__main__":
    raise SystemExit(main())
