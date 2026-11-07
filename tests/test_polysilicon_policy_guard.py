#!/usr/bin/env python3
"""Regression checks for Proclamation 11052 and unrelated DOE space-PV alerts."""

from __future__ import annotations

import hashlib

from scripts import khs_policy_alert_guardrails as guard
from scripts import khs_policy_watch as watch
from scripts import khs_trusted_policy_news_watch as trusted


def expected_policy_fingerprint(event_key: str) -> str:
    raw = f"policy-event-v1|{event_key}"
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:16]


def main() -> None:
    # Generic White House language such as "award"/"selected" must not create a
    # DOE energy-security signal without DOE authority in the source/body.
    unrelated = {
        "source": "White House briefings statements",
        "title": "Presidential Message on the Beatification of Archbishop Fulton J. Sheen",
        "link": "https://www.whitehouse.gov/briefings-statements/example/",
        "summary": "The President selected honorees for an award.",
        "source_body": "The President selected honorees for an award.",
        "body_verified": True,
        "published_kst": "2026-09-25T12:00:00+09:00",
    }
    unrelated_result = watch.classify_item(unrelated)
    assert unrelated_result is None or "energy_security_policy" not in unrelated_result.get("matched", {})

    stockpiling = {
        "source": "Federal Register Commerce national security",
        "title": "Measures To Restrict Stockpiling of Polysilicon and Polysilicon Derivatives Under Proclamation 11052",
        "link": "https://www.federalregister.gov/documents/2026/09/24/2026-19537/measures-to-restrict-stockpiling-of-polysilicon-and-polysilicon-derivatives-under-proclamation-11052",
        "summary": (
            "Temporary final rule under Proclamation 11052. BIS will monitor stockpiling, "
            "limit new importers, and may impose an import prohibition or grant a waiver."
        ),
        "published_kst": "2026-09-24T00:00:00+09:00",
    }
    stock_result = watch.classify_item(stockpiling)
    assert stock_result is not None
    assert watch.polysilicon_11052_event_key(stockpiling, " ".join([
        stockpiling["title"].lower(), stockpiling["summary"].lower()
    ])) == "polysilicon-11052-stockpiling-tfr"
    assert stock_result["fingerprint"] == expected_policy_fingerprint("polysilicon-11052-stockpiling-tfr")
    assert guard.korean_title_for(stock_result) == "미 상무부, 폴리실리콘 사재기 차단 규칙 시행"

    base = {
        "source": "White House fact sheets",
        "title": "Fact Sheet: President Donald J. Trump Bolsters National Security and Strengthens U.S. Supply Chains by Imposing Tariffs on Polysilicon and its Derivatives",
        "link": "https://www.whitehouse.gov/fact-sheets/2026/08/example/",
        "summary": (
            "Proclamation 11052 adjusts imports of polysilicon using minimum import prices, "
            "a 15 percent ad valorem tariff, and an onshoring program."
        ),
    }
    base_text = f"{base['title']} {base['summary']}".lower()
    assert watch.polysilicon_11052_event_key(base, base_text) == "polysilicon-11052-base"
    assert trusted.semantic_policy_event_key({
        "title": base["title"],
        "description": base["summary"],
        "link": base["link"],
        "source": base["source"],
    }) == "polysilicon-11052-base"
    assert trusted.is_polysilicon_11052_base_rehash_text(base_text)
    assert not trusted.is_polysilicon_11052_base_rehash_text(
        base_text + " BIS amended the rule and changed the waiver conditions."
    )
    assert any(
        source.name == "Federal Register polysilicon Section 232"
        for source in watch.SOURCES
    )

    pra_notice = {
        "source": "Federal Register Commerce national security",
        "title": (
            "Agency Information Collection Activities; Submission to the Office of Management "
            "and Budget (OMB) for Review and Approval; Comment Request; Application Process "
            "To Waive the Import Qualification Criteria Measures To Restrict Stockpiling of "
            "Polysilicon and Polysilicon Derivatives"
        ),
        "link": (
            "https://www.federalregister.gov/documents/2026/11/06/2026-22726/"
            "agency-information-collection-activities-submission-to-the-office-of-management-and-budget-omb-for"
        ),
        "summary": (
            "November 6, 2026 notice requests 60 days of public comment on an OMB-approved "
            "information collection for the existing September 24, 2026 temporary final rule "
            "under Proclamation 11052; comment deadline January 5, 2027; "
            "estimated 165 respondents and 330 annual burden hours."
        ),
        "published_kst": "2026-11-06T00:00:00+09:00",
    }
    pra_text = (pra_notice["title"] + " " + pra_notice["summary"]).lower()
    pra_stage = "polysilicon-11052-omb-comment-2026-11-06"
    assert watch.is_polysilicon_11052_pra_notice(pra_notice, pra_text)
    assert watch.polysilicon_11052_event_key(pra_notice, pra_text) == pra_stage
    assert watch.classify_item(pra_notice) is None, "OMB paperwork rebranded as a new tariff rule"
    assert trusted.is_polysilicon_11052_pra_notice_text(pra_notice["title"], pra_notice["link"])
    assert trusted.semantic_policy_event_key(pra_notice) == pra_stage
    assert "의견수렴" in trusted.semantic_policy_title(pra_notice)
    assert guard.korean_title_for(pra_notice) == "미 상무부, 폴리실리콘 면제 신청 정보수집 의견수렴 공고"
    assert pra_stage != "polysilicon-11052-stockpiling-tfr"
    assert not watch.is_polysilicon_11052_pra_notice(stockpiling, stockpiling["summary"])
    assert not trusted.is_polysilicon_11052_pra_notice_text(
        stockpiling["title"], stockpiling["link"]
    )
    meaningful_rule_update = {
        **pra_notice,
        "title": "BIS amends the polysilicon stockpiling temporary final rule under Proclamation 11052",
        "link": "https://www.federalregister.gov/documents/2026/11/10/2026-NEW/rule-amendment",
        "summary": "New amendments to the restriction, not OMB information collection.",
    }
    assert not watch.is_polysilicon_11052_pra_notice(meaningful_rule_update, meaningful_rule_update["summary"])

    # Policy messages are independent: an invalid English heading and an
    # ungrounded generic title must not consume another verified document.
    from datetime import datetime
    from zoneinfo import ZoneInfo
    from scripts import khs_policy_alert_router as router

    good_alert = {
        **stock_result,
        "source": "Federal Register Commerce national security",
        "title_ko": "미 상무부, 폴리실리콘 사재기 차단 규칙 시행",
        "policy_event_key": "polysilicon-11052-stockpiling-tfr",
        "policy_plain_summary": "BIS의 2026년 9월 24일 임시 최종규칙 공표입니다.",
        "investment_view": "미국 수입자별 통관 가능 물량에 영향을 줄 수 있습니다.",
        "korea_market_impact": "한국 공급기업의 실제 미국향 수입·매출 관계를 확인해야 합니다.",
        "failure_signal": "실제 통관 집행과 수입량 변화가 없으면 영향은 제한적입니다.",
    }
    bad_english = {
        **good_alert,
        "source": "White House briefings statements",
        "title": "First Lady Melania Trump Unites Russia and Ukraine at The White House",
        "title_ko": "",
        "policy_event_key": "",
        "fingerprint": "english-unverified",
        "link": "https://www.whitehouse.gov/briefings-statements/2026/11/test/",
    }
    bad_generic = {
        **good_alert,
        "title": "미국, 관세·통관 정책 변화 공표",
        "title_ko": "미국, 관세·통관 정책 변화 공표",
        "policy_event_key": "",
        "fingerprint": "generic-unverified",
    }
    chosen = router.select_sendable_policy_alerts(
        [bad_english, bad_generic, good_alert],
        datetime(2026, 11, 7, 20, tzinfo=ZoneInfo("Asia/Seoul")),
    )
    assert len(chosen) == 1 and chosen[0]["fingerprint"] == good_alert["fingerprint"], chosen

    # One currency-unsafe article must not cancel an unrelated valid report.
    from types import SimpleNamespace
    from unittest.mock import patch
    from scripts import khs_policy_telegram_formatter as policy_formatter

    news_items = [
        {"rule": SimpleNamespace(key="currency-unsafe"), "items": [], "fingerprint": "fx1"},
        {"rule": SimpleNamespace(key="currency-safe"), "items": [], "fingerprint": "safe2"},
    ]
    def mock_news_report(items, _now, limit=1):
        return (
            "DOE offers $100 million in grants."
            if items[0]["fingerprint"] == "fx1"
            else "미국 정부의 한국 관련 통상정책 확정 내용입니다."
        )
    assert policy_formatter.extract_foreign_amounts("DOE offers $100 million in grants.")
    with (
        patch.object(trusted, "render_alert_bundle", side_effect=mock_news_report),
        patch.object(policy_formatter, "format_policy_message", side_effect=ValueError("No verified FX quote")),
    ):
        selected = trusted.select_currency_safe_general_alerts(
            news_items, datetime(2026, 11, 7, 20, tzinfo=ZoneInfo("Asia/Seoul"))
        )
    assert len(selected) == 1 and selected[0]["fingerprint"] == "safe2", selected

    space_pv = (
        "DOE Space Photovoltaics Research and Development Partnership Intermediary Agreement "
        "announced a funding opportunity for solar panels in space applications. "
        "Expected Timeframe for Selection Notifications: December 2026."
    )
    # The Aug. 31 base notice itself mentions future "Selection Notifications".
    # That schedule wording must not be mistaken for a new selection result.
    assert trusted.is_space_pv_pia_base_rehash_text(space_pv)
    assert watch.is_space_pv_pia_base_rehash_item(
        {
            "source": "DOE news",
            "title": "Space Photovoltaics Research and Development Partnership Intermediary Agreement",
            "link": "https://www.energy.gov/cmei/systems/space-photovoltaics-research-and-development-partnership-intermediary-agreement",
        },
        space_pv.lower(),
    )
    stale_space_pv_item = {
        "source": "DOE news",
        "title": "Space Photovoltaics Research and Development Partnership Intermediary Agreement",
        "link": "https://www.energy.gov/cmei/systems/space-photovoltaics-research-and-development-partnership-intermediary-agreement",
        "summary": space_pv,
        "published_kst": "2026-09-25T12:00:00+09:00",
    }
    assert watch.classify_item(stale_space_pv_item) is None

    selection_update = space_pv + " DOE announces selections and selected projects for award."
    assert not trusted.is_space_pv_pia_base_rehash_text(selection_update)
    assert trusted.semantic_policy_event_key({
        "title": "DOE announces selections for Space Photovoltaics R&D PIA",
        "description": selection_update,
        "link": "https://www.energy.gov/example-space-pv-selections",
        "source": "DOE",
    }) == "doe-space-pv-pia-selections"

    print("polysilicon_policy_guard=passed")


if __name__ == "__main__":
    main()
