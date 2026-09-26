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
