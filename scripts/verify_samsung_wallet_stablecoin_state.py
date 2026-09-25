#!/usr/bin/env python3
from __future__ import annotations

from scripts.samsung_wallet_stablecoin_watch import state_changed, topic_state


def base_stage2():
    return {
        "topic": "Samsung Wallet stablecoin adoption",
        "stage": 2,
        "stage_name": "사업개발·파트너십 실행",
        "achieved_stage": 2,
        "support_plan": True,
        "job_exists": True,
        "stablecoin_bd_scope": True,
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
