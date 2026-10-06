#!/usr/bin/env python3
from __future__ import annotations

try:
    from scripts.samsung_wallet_stablecoin_watch import state_changed, topic_state
except ModuleNotFoundError:
    from samsung_wallet_stablecoin_watch import state_changed, topic_state


def base_stage2():
    return {
        "topic": "Samsung Wallet stablecoin adoption",
        "stage": 2,
        "stage_name": "사업개발·파트너십 실행",
        "achieved_stage": 2,
        "support_plan": True,
        "job_exists": True,
        "stablecoin_bd_scope": True,
        "executive_default_feature_confirmation": False,
        "smart_contract_wallet_patent_confirmed": False,
        "wallet_patent_publication": "",
        "wallet_patent_publication_date": "",
        "wallet_patent_priority_date": "",
        "wallet_patent_direct_stablecoin_link": False,
        "stablecoin_partner": "",
        "pilot_or_launch": False,
        "explicit_reversal_confirmed": False,
        "status": "진행 중",
        "official_job_scope_now": True,
    }


def official(**kwargs):
    base = {
        "samsung_support_confirmed": True,
        "job_stablecoin_confirmed": True,
        "job_fetch_ok": True,
        "article_confirmed": True,
        "kbw_executive_primary_confirmed": False,
        "kbw_executive_crosscheck_confirmed": False,
        "wallet_patent_us_confirmed": False,
        "wallet_patent_family_confirmed": False,
        "wallet_patent_news_confirmed": False,
        "explicit_reversal_confirmed": False,
        "errors": [],
    }
    base.update(kwargs)
    return base


def candidate(title: str, summary: str = ""):
    return [{"title": title, "summary": summary, "link": "https://example.com/x"}]


def assert_no_alert_for_evidence_expiry():
    prev = base_stage2()
    current = topic_state(
        official(job_stablecoin_confirmed=False, article_confirmed=False),
        [],
        prev,
    )
    changed, changes = state_changed(prev, current)
    assert current["stage"] == 2, current
    assert current["stablecoin_bd_scope"] is True, current
    assert not changed, changes


def assert_no_alert_for_transient_source_failure():
    prev = base_stage2()
    current = topic_state(
        official(
            samsung_support_confirmed=False,
            job_stablecoin_confirmed=False,
            job_fetch_ok=False,
            article_confirmed=False,
        ),
        [],
        prev,
    )
    changed, changes = state_changed(prev, current)
    assert current["stage"] == 2, current
    assert current["support_plan"] is True, current
    assert current["stablecoin_bd_scope"] is True, current
    assert not changed, changes


def assert_no_alert_for_duplicate_article():
    prev = base_stage2()
    current = topic_state(
        official(),
        candidate(
            "삼성전자 미국법인, 삼성월렛 스테이블코인 결제 담당자 채용",
            "기존 R118656 사업개발 채용 내용을 재보도",
        ),
        prev,
    )
    changed, changes = state_changed(prev, current)
    assert current["stage"] == 2, current
    assert not changed, changes


def assert_generic_visa_galaxy_card_launch_does_not_promote():
    prev = base_stage2()
    current = topic_state(
        official(),
        candidate(
            "Samsung Wallet stablecoin plans and Galaxy Card launch",
            "Galaxy Card launched with Barclays and Visa. Samsung Wallet will support stablecoins later.",
        ),
        prev,
    )
    changed, changes = state_changed(prev, current)
    assert current["stablecoin_partner"] == "", current
    assert current["pilot_or_launch"] is False, current
    assert current["stage"] == 2, current
    assert not changed, changes


def assert_kbw_executive_confirmation_alerts_once_without_promotion():
    prev = base_stage2()
    current = topic_state(
        official(
            kbw_executive_primary_confirmed=True,
            kbw_executive_crosscheck_confirmed=True,
        ),
        candidate(
            "삼성월렛, 스테이블코인 탑재 속도",
            "백원석 삼성전자 그룹장이 삼성월렛에 스테이블코인을 기본 기능으로 지원하는 방향을 공개 설명",
        ),
        prev,
    )
    changed, changes = state_changed(prev, current)
    assert current["executive_default_feature_confirmation"] is True, current
    assert current["stage"] == 2, current
    assert current["stablecoin_partner"] == "", current
    assert current["pilot_or_launch"] is False, current
    assert changed, changes
    assert any("단계 2 강화" in x for x in changes), changes

    changed_again, changes_again = state_changed(current, current)
    assert not changed_again, changes_again


def assert_kbw_tether_panel_does_not_create_tether_partner():
    prev = base_stage2()
    current = topic_state(
        official(
            kbw_executive_primary_confirmed=True,
            kbw_executive_crosscheck_confirmed=True,
        ),
        candidate(
            "테더와 삼성월렛이 KBW2026 패널 참석",
            "테더는 스테이블코인 대중화를 설명했고 백원석 그룹장은 삼성월렛의 스테이블코인 기본 기능 지원 방향을 별도로 설명",
        ),
        prev,
    )
    assert current["executive_default_feature_confirmation"] is True, current
    assert current["stablecoin_partner"] == "", current
    assert current["stage"] == 2, current


def assert_wallet_patent_alerts_once_without_stage_promotion():
    prev = base_stage2()
    current = topic_state(
        official(
            wallet_patent_us_confirmed=True,
            wallet_patent_family_confirmed=True,
            wallet_patent_news_confirmed=True,
        ),
        candidate(
            "삼성전자 스마트계약 가상자산 지갑 미국 특허 공개",
            "US20260212355A1 스마트계약 지갑 기능 관련 특허. Samsung Wallet 또는 stablecoin 제품 적용은 별도 확인 필요.",
        ),
        prev,
    )
    changed, changes = state_changed(prev, current)
    assert current["smart_contract_wallet_patent_confirmed"] is True, current
    assert current["wallet_patent_publication"] == "US20260212355A1", current
    assert current["wallet_patent_direct_stablecoin_link"] is False, current
    assert current["stage"] == 2, current
    assert current["stablecoin_partner"] == "", current
    assert current["pilot_or_launch"] is False, current
    assert changed, changes
    assert any("R&D 인프라 강화" in x for x in changes), changes

    changed_again, changes_again = state_changed(current, current)
    assert not changed_again, changes_again


def assert_single_patent_source_does_not_confirm_milestone():
    prev = base_stage2()
    current = topic_state(
        official(
            wallet_patent_us_confirmed=True,
            wallet_patent_family_confirmed=False,
            wallet_patent_news_confirmed=True,
        ),
        [],
        prev,
    )
    changed, changes = state_changed(prev, current)
    assert current["smart_contract_wallet_patent_confirmed"] is False, current
    assert current["stage"] == 2, current
    assert not changed, changes


def assert_patent_never_implies_stablecoin_partner_or_launch():
    prev = base_stage2()
    current = topic_state(
        official(
            wallet_patent_us_confirmed=True,
            wallet_patent_family_confirmed=True,
        ),
        candidate(
            "Samsung smart contract wallet patent",
            "The patent covers cryptocurrency wallet functions and recovery. No named stablecoin issuer, chain, payment network, pilot, or launch.",
        ),
        prev,
    )
    assert current["smart_contract_wallet_patent_confirmed"] is True, current
    assert current["wallet_patent_direct_stablecoin_link"] is False, current
    assert current["stablecoin_partner"] == "", current
    assert current["pilot_or_launch"] is False, current
    assert current["stage"] == 2, current


def assert_explicit_partner_promotes_once():
    prev = base_stage2()
    current = topic_state(
        official(),
        candidate(
            "Samsung Wallet stablecoin partnership with Circle announced",
            "Samsung Wallet stablecoin partnership integrates Circle USDC for payments.",
        ),
        prev,
    )
    changed, changes = state_changed(prev, current)
    assert current["stablecoin_partner"] == "Circle", current
    assert current["stage"] >= 3, current
    assert changed, changes


def assert_explicit_pilot_promotes_once():
    prev = base_stage2()
    current = topic_state(
        official(),
        candidate(
            "Samsung Wallet stablecoin pilot launches",
            "Samsung Wallet stablecoin pilot launches in the United States.",
        ),
        prev,
    )
    changed, changes = state_changed(prev, current)
    assert current["pilot_or_launch"] is True, current
    assert current["stage"] == 4, current
    assert changed, changes


def assert_explicit_reversal_alerts():
    prev = base_stage2()
    current = topic_state(
        official(explicit_reversal_confirmed=True),
        [],
        prev,
    )
    changed, changes = state_changed(prev, current)
    assert current["explicit_reversal_confirmed"] is True, current
    assert changed, changes
    assert any("철회" in x or "취소" in x for x in changes), changes


def main():
    tests = [
        assert_no_alert_for_evidence_expiry,
        assert_no_alert_for_transient_source_failure,
        assert_no_alert_for_duplicate_article,
        assert_generic_visa_galaxy_card_launch_does_not_promote,
        assert_kbw_executive_confirmation_alerts_once_without_promotion,
        assert_kbw_tether_panel_does_not_create_tether_partner,
        assert_wallet_patent_alerts_once_without_stage_promotion,
        assert_single_patent_source_does_not_confirm_milestone,
        assert_patent_never_implies_stablecoin_partner_or_launch,
        assert_explicit_partner_promotes_once,
        assert_explicit_pilot_promotes_once,
        assert_explicit_reversal_alerts,
    ]
    for test in tests:
        test()
        print(f"PASS {test.__name__}")
    print(f"Samsung stablecoin state regression tests: {len(tests)}/{len(tests)} passed")


if __name__ == "__main__":
    main()
