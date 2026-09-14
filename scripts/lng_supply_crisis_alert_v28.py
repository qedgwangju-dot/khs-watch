#!/usr/bin/env python3
"""에너지 공급감시 v28: 호르무즈 우회 송유관 뉴스 회수율 보강.

v27의 사건·상태 변화 기준은 유지하고, 제목에 East-West/Petroline이 직접 안 들어간
Reuters/AP류 'Saudi pipeline outage' 표현도 같은 우회망 사건으로 잡는다.
"""
from __future__ import annotations

import lng_supply_crisis_alert_v2 as core
import lng_supply_crisis_alert_v27 as v27

_BASE_BUILD = core.build_regular_alert
_BASE_SETUP = core.build_setup_test

BYPASS_RECALL_QUERIES = (
    ("hormuz_shipping", '"East-West pipeline" Saudi when:7d'),
    ("hormuz_shipping", '"East-West oil pipeline" Saudi when:7d'),
    ("hormuz_shipping", '"Saudi pipeline outage" Hormuz when:7d'),
    ("hormuz_shipping", '"Saudi Arabia shuts" "oil pipeline" when:7d'),
    ("hormuz_shipping", '"Yanbu" Saudi pipeline outage when:7d'),
    ("hormuz_shipping", '사우디 송유관 가동 중단 호르무즈 우회 when:7d'),
)
for item in BYPASS_RECALL_QUERIES:
    if item not in core.NEWS_QUERIES:
        core.NEWS_QUERIES = tuple(core.NEWS_QUERIES) + (item,)

core.WORSENING_TERMS["hormuz_shipping"] = tuple(core.WORSENING_TERMS["hormuz_shipping"]) + (
    "saudi pipeline outage", "saudi pipeline attack", "shuts key oil pipeline",
    "shut key oil pipeline", "shuts down a pipeline", "shuts down oil pipeline",
    "shut down oil pipeline", "saudis shut down oil pipeline",
    "pipeline outage threatens", "송유관 중단 장기화", "사우디 송유관 중단",
)

core.SUBTYPE_TERMS = (
    ("hormuz_bypass_shutdown", (
        "saudi pipeline outage", "shuts key oil pipeline", "shut key oil pipeline",
        "shuts down key oil pipeline", "shuts down a pipeline", "shuts down oil pipeline",
        "shut down oil pipeline", "saudis shut down oil pipeline", "pipeline outage threatens",
        "사우디 송유관 중단", "송유관 중단 장기화",
    )),
) + tuple(core.SUBTYPE_TERMS)

# 현재 기사군의 다양한 표기를 한국어로 고정한다. 감시대상은 기사가 아니라 상태변화다.
v27.v12.v8.KNOWN_TRANSLATIONS.update({
    "Saudi Arabia shuts down a pipeline as Houthis seize an island, opening a new front in the Iran war":
        "사우디, 핵심 송유관 가동 중단…후티의 홍해 요충지 장악으로 중동 전선 확대",
    "Saudis shut down oil pipeline as Houthis tighten grip on Red Sea shipping":
        "사우디, 동서 송유관 가동 중단…후티의 홍해 항로 압박 확대",
    "Saudi Arabia shuts key oil pipeline after drone attack launched from Iraq":
        "사우디, 이라크발 드론 공격 뒤 핵심 동서 송유관 가동 중단",
})


def build_regular_alert_v28(groups, quotes, new_signals, cleared_signals):
    title, body, metadata = _BASE_BUILD(groups, quotes, new_signals, cleared_signals)
    metadata["version"] = 28
    metadata.setdefault("hormuz_bypass_watch", {})["recall_queries"] = "East-West + Saudi pipeline outage + Yanbu + Korean variants"
    return title, body, metadata


def build_setup_test_v28(quotes):
    title, body, metadata = _BASE_SETUP(quotes)
    body += (
        "\n• 우회 송유관 기사 제목에 East-West/Petroline이 없어도 'Saudi pipeline outage/shuts key oil pipeline' 표현을 같은 사건으로 분류"
        "\n• 검색은 East-West·Saudi pipeline outage·Yanbu·한국어 표현을 별도 쿼리로 나눠 회수율 보강"
    )
    metadata["version"] = 28
    return title, body, metadata


core.build_regular_alert = build_regular_alert_v28
core.build_setup_test = build_setup_test_v28

if __name__ == "__main__":
    raise SystemExit(core.main())
