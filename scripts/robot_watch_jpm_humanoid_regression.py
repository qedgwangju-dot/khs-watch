#!/usr/bin/env python3
"""Offline regression: broker outlook, report reprints and real milestones."""
import datetime as dt
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent))
import physical_ai_watch_airan_guard as watcher
from robot_watch_jpm_humanoid_outlook import BACKFILL, GROUP, EVENT_KEY
base = watcher.base

def audit(row):
    text = " ".join(str(row.get(k) or "") for k in ("title", "description", "source"))
    group = base.topic_group(text)
    return group, base.score(row), base.key(row), base.category(text, group) if group else ""

original_now = base.NOW
try:
    base.NOW = dt.datetime(2026, 11, 15, 17, 0, tzinfo=dt.timezone.utc)
    backfill = base.query_news(BACKFILL)
    assert len(backfill) == 1 and backfill[0].get("jpm_robotis_backfill")
    g, score, k, category = audit(backfill[0])
    assert g == GROUP and score >= 11 and k == EVENT_KEY and "전망" in category
    assert "수주" in backfill[0]["description"] and "아님" in backfill[0]["description"]
    reprint = {
        "title": "JP모건 미 휴머노이드 2030년 40만대 로보티즈 선정",
        "description": "2026-11-12 J.P. Morgan humanoid market outlook, Reuters reprint",
        "source": "AI타임스", "published": "2026-11-15T12:00:00+00:00",
    }
    assert audit(reprint)[0] == GROUP
    assert audit(reprint)[1] == 0
    assert audit(reprint)[2] == EVENT_KEY
    latest_unverified = {**reprint, "title": "JP모건 휴머노이드 2030년 전망 로보티즈 상향",
                         "published": "2026-11-22T01:00:00+00:00"}
    assert audit(latest_unverified)[1] == 0, "Press rewrite must not become a fresh JP Morgan forecast"
    revised = {**latest_unverified, "source": "Reuters",
               "title": "J.P. Morgan raises 2030 humanoid forecast, includes ROBOTIS"}
    assert audit(revised)[0] == GROUP and audit(revised)[1] >= 11
    assert audit(revised)[2] != EVENT_KEY
    unrelated = {"title": "로보티즈 DYNAMIXEL 신규 고객 양산 공급계약 체결",
                 "description": "robot actuator actual order", "source": "ROBOTIS",
                 "published": "2026-11-16T00:00:00+00:00"}
    assert audit(unrelated)[0] != GROUP, "Existing robot supply lane must remain intact"
    base.NOW = dt.datetime(2026, 11, 21, 0, 0, tzinfo=dt.timezone.utc)
    assert base.query_news(BACKFILL) == [], "Temporary missed-alert catch-up must expire"
finally:
    base.NOW = original_now

print("JPMorgan humanoid outlook / ROBOTIS source-grade offline regressions: PASS")
