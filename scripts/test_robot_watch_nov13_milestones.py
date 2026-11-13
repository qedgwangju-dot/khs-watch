#!/usr/bin/env python3
"""Offline regression: Nov-13 new stages, source grades and stable old keys."""
from __future__ import annotations
import hashlib
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import physical_ai_watch_airan_guard as watcher
from robot_watch_nov13_milestones import MERGER_BACKFILL, DKT_BACKFILL
base = watcher.base

def check(row):
    body = " ".join(str(row.get(k) or "") for k in ("title", "description", "source"))
    g = base.topic_group(body)
    return g, base.score(row), base.key(row), base.category(body, g)

def item(title, description="", source="Reuters", published="2026-11-13T00:00:00+00:00"):
    return {"title":title,"description":description,"source":source,"published":published,"link":"https://example.org/source"}

merger = base.query_news(MERGER_BACKFILL)[0]
dkt = base.query_news(DKT_BACKFILL)[0]
mg, ms, mk, mc = check(merger)
dg, ds, dk, dc = check(dkt)
assert mg == "spacex_tesla_combination" and ms >= 11 and "기업결합" in mc
assert dg == "dkt_auto_oled_expansion" and ds >= 11 and "OLED" in dc
assert "독립 확인 전" in base.verification(dkt,dg,dkt["description"])
reprint = item("SpaceX Tesla merger talks progress, Bloomberg News reports","December potential", "Investing.com")
assert check(reprint)[2] == mk, "Reuters and syndicated merger reporting must dedup"
committee = item("Tesla and SpaceX special committees review merger","No final terms agreed")
assert check(committee)[1] < 11, "October committee baseline must not re-alert"
rumor = item("SpaceX Tesla merger talks progress","unverified blog speculation","Unknown Blog")
assert check(rumor)[1] < 11, "Anonymous rumor must not act as credible reporting"
signed = item("Tesla SpaceX merger definitive agreement signed","Board officially agreed","SpaceX")
assert check(signed)[1] >= 11 and check(signed)[2] != mk, "Official signed deal is a distinct event"
prior = item("디케이티 북미 차량용 OLED 11월 양산 예정","신규 고객 전망","하나증권")
assert check(prior)[1] < 11, "Prior production forecast must not become new sales"
dkt_again = item("디케이티, 북미 전기차 OLED 양산 물량 더 커졌다", "앞좌석·뒷좌석 모듈 추가 수주","더스탁")
assert check(dkt_again)[2] == dk, "Reprint must preserve semantic DKT key"
cost = item("Anthropic: Robot cost study and work exposure","0.3% cost-competitive 70% drop","Anthropic","2026-09-30T00:00:00+00:00")
assert check(cost)[1] < 11, "Sep 30 Anthropic study must not replay in November"
revision = item("Anthropic revised robot work cost exposure study","New figures","Anthropic")
assert check(revision)[1] >= 11 and check(revision)[2] != check(cost)[2]
assert len([q for q in base.QUERIES if q==MERGER_BACKFILL])==1
assert len([q for q in base.QUERIES if q==DKT_BACKFILL])==1
print("Nov-13 robot event source-stage and anti-replay tests: PASS")
