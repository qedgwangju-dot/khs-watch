#!/usr/bin/env python3
"""Offline no-send checks for the new Tacta / 1X / Tesla hand milestone lane."""
from __future__ import annotations

import physical_ai_watch_airan_guard as watcher
import robot_hand_tactile_watch_extension as hand

base = watcher.base


def make(title, description, source, published="2026-11-02T02:00:00+00:00"):
    return {
        "title": title,
        "description": description,
        "source": source,
        "published": published,
        "link": "https://example.com/test-only",
    }


def classify(item):
    text = " ".join(str(item.get(k) or "") for k in ("title", "description", "source"))
    group = base.topic_group(text)
    return group, base.score(item), base.key(item), base.category(text, group)


def run():
    # Historical vendor claims are not new shipments, independent certification,
    # paid pilots, or binding orders. Do not backfill this comparative news item.
    tacta_article = make(
        "로봇 마지막 난제 손 기술… 업체마다 구현 방식 다르네",
        "Tacta Systems Tacta Hand fluidic tendon 15 joints, July 2026 launch; "
        "the company plans deliveries in early 2027. 3kg dumbbell demo.",
        "조선일보",
        "2026-10-29T00:36:00+09:00",
    )
    a, b, _, _ = classify(tacta_article)
    assert a == "tacta_dexterous_hand" and b == 0, (a, b)
    tacta_july = make(
        "Tacta Systems unveiled fluidic robotic hands",
        "TactaBot Tacta Hand 15 actuated joints. The company will deploy to "
        "electronics manufacturers in early 2027.",
        "Tacta Systems",
        "2026-07-27T00:00:00+00:00",
    )
    assert classify(tacta_july)[1] == 0

    x1_july = make(
        "1X Technologies unveils NEO robotic hands",
        "The July 2026 NEO hands have 25 DoF and 5:1 to 15:1 tendon-drive "
        "gear ratios, not a new customer shipment.",
        "1X Technologies", "2026-07-09T00:00:00+00:00",
    )
    assert classify(x1_july)[0] == "one_x_neo_dexterous_hand"
    assert classify(x1_july)[1] == 0

    tesla_plan = make(
        "Tesla Optimus replaceable sensing glove plans",
        "Tesla will integrate a replaceable sensing glove into Optimus "
        "production next year, but it is not installed yet.",
        "Reuters", "2026-09-25T00:00:00+00:00",
    )
    assert classify(tesla_plan)[0] == "tesla_optimus_hand_service"
    assert classify(tesla_plan)[1] == 0

    # Hypothetical future events: tests do not imply these events occurred.
    tacta_contract = make(
        "Tacta Systems signs new supply contract",
        "Tacta Systems signed a supply contract for Tacta Hand robots with "
        "a manufacturing customer. Customer identity and unit count withheld.",
        "Tacta Systems",
    )
    group, score, key, cat = classify(tacta_contract)
    assert group == "tacta_dexterous_hand" and score >= 11, (group, score)
    assert "고객" in cat and len(key) == 64

    tacta_contract_press = make(
        "Tacta Hand supplier signs deal",
        "Tacta Systems signed a supply contract for Tacta Hand robots.",
        "Reuters", "2026-11-03T01:00:00+00:00",
    )
    assert classify(tacta_contract_press)[0] == group
    assert classify(tacta_contract_press)[1] >= 11
    assert classify(tacta_contract_press)[2] != key, (
        "Press and official evidence must remain separate upgrades"
    )
    tacta_press_syndication = make(
        "Deal for Tacta Hand confirmed",
        "Tacta Systems signed a supply contract for dexterous hands.",
        "Bloomberg", "2026-11-03T09:00:00+00:00",
    )
    assert classify(tacta_contract_press)[2] == classify(tacta_press_syndication)[2], (
        "Same press-stage milestone this week must share a dedup key"
    )
    other_week = dict(tacta_contract_press, published="2026-11-12T09:00:00+00:00")
    assert classify(other_week)[2] != classify(tacta_contract_press)[2]

    noncredible = dict(tacta_contract, source="anonymous blog")
    assert classify(noncredible)[1] == 0

    1x_endurance = make(
        "1X Technologies NEO robotic hands new independent endurance result",
        "Independent third-party test certified 2 million cycles for the "
        "1X NEO tendon-driven robotic hand.",
        "1X Technologies",
    )
    assert classify(1x_endurance)[0] == "one_x_neo_dexterous_hand"
    assert classify(1x_endurance)[1] >= 11

    tesla_actual = make(
        "Tesla Optimus replaceable sensing glove integrated into production",
        "Tesla confirmed that the replaceable sensing glove was integrated "
        "into production Optimus robot hands.",
        "Tesla",
    )
    assert classify(tesla_actual)[0] == "tesla_optimus_hand_service"
    assert classify(tesla_actual)[1] >= 11

    negated = make(
        "Tesla Optimus sensing glove not integrated",
        "Tesla has not integrated the replaceable sensing glove into production.",
        "Reuters",
    )
    assert classify(negated)[1] == 0, "Do not alert on denied implementation"

    old_patent = make(
        "Tesla Optimus US20260310299A1 tactile patent publication",
        "Tesla patent US20260310299A1 for a tactile array sensor was published.",
        "Robotics News",
        "2026-10-08T00:00:00+00:00",
    )
    assert hand.identity(" ".join((old_patent["title"],old_patent["description"]))) == ""
    assert classify(old_patent)[0] == "tesla_touch_patent", (
        "The prior Tesla patent lane must remain separate"
    )

    assert any("Tacta" in q for q in base.QUERIES)
    assert any("1X" in q for q in base.QUERIES)
    assert len(set(base.QUERIES)) == len(base.QUERIES)
    # All checks are offline, use fabricated event descriptions and do not
    # call fetch, state writes or Telegram.


if __name__ == "__main__":
    run()
    print("Dexterous-hand milestone regression: PASS")
