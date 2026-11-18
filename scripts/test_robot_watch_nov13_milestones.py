#!/usr/bin/env python3
"""Offline regression: Nov-13 new stages, source grades and stable old keys."""
from __future__ import annotations
import datetime as dt
import sys
from contextlib import contextmanager
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import physical_ai_watch_airan_guard as watcher
import robot_watch_nov13_milestones as milestones
from robot_watch_nov13_milestones import MERGER_BACKFILL, DKT_BACKFILL
base = watcher.base

def check(row):
    body = " ".join(str(row.get(k) or "") for k in ("title", "description", "source"))
    g = base.topic_group(body)
    return g, base.score(row), base.key(row), base.category(body, g)

def item(title, description="", source="Reuters", published="2026-11-13T00:00:00+00:00", **extra):
    return {"title":title,"description":description,"source":source,"published":published,"link":"https://example.org/source", **extra}

@contextmanager
def at_time(now):
    previous_now = base.NOW
    try:
        base.NOW = now
        yield
    finally:
        base.NOW = previous_now


def run():
    original_now = base.NOW
    # Historical fixtures remain available only in their original recovery
    # window. Freeze the test clock, never extend the production expiry.
    with at_time(dt.datetime(2026, 11, 13, tzinfo=dt.timezone.utc)):
        merger_rows = base.query_news(MERGER_BACKFILL)
        dkt_rows = base.query_news(DKT_BACKFILL)
        assert len(merger_rows) == len(dkt_rows) == 1, (merger_rows, dkt_rows)
        merger, dkt = merger_rows[0], dkt_rows[0]
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
        unidentifiable_revision = item("Anthropic revised robot work cost exposure study","New figures","Anthropic")
        assert check(unidentifiable_revision)[1] == 0
        assert "검증 대기" in base.verification(unidentifiable_revision, milestones.COST, "")
        # Hypothetical future revision fixtures, not verified current findings.
        revision = item(
            "Anthropic revised robot work cost exposure study",
            "Analysis scope: U.S. manufacturing jobs; reference period: 2026 Q3; "
            "report date: 2026-11-13; version: 2; cost-competitive share: 0.5%",
            "Anthropic", link="https://www.anthropic.com/research/robot-cost-revision",
        )
        assert check(revision)[1] >= 11 and check(revision)[2] != check(cost)[2]
        assert check(cost)[2] == "36b3cf4dd8d1b8010394bd666e602c26c85043b1fff88ff0b7984c3563f73f6b"
        revision_key = check(revision)[2]
        reissued = dict(revision, source="Anthropic Research", published="2026-11-23T00:00:00+00:00",
                        link="https://anthropic.com/research/robot-cost-revision/?utm_source=rss#section")
        assert check(reissued)[2] == revision_key, "Syndication dates and tracking URLs are not a new revision"
        changes = (
            ("0.5%", "2.0%"),
            ("U.S. manufacturing jobs", "European manufacturing jobs"),
            ("2026 Q3", "2026 Q4"),
            ("report date: 2026-11-13", "report date: 2026-11-18"),
            ("version: 2", "version: 3"),
        )
        for old, new in changes:
            changed = dict(revision, description=revision["description"].replace(old, new))
            assert check(changed)[1] >= 11, (old, new)
            assert check(changed)[2] != revision_key, "A different finding, target, period or revision must not collapse"
        changed_value = dict(revision, description=revision["description"].replace("0.5%", "2.0%"))
        rendered = base.verification(changed_value, milestones.COST, "") + base.meaning(milestones.CATEGORIES[milestones.COST])
        assert "2%" in rendered and "0.5%" not in rendered and "0.3%" not in rendered and "70%" not in rendered
        assert "원문 추가 검증" in rendered and "2026 Q3".casefold() in rendered
        for blocked in (
            dict(revision, link="https://news.google.com/rss/articles/opaque", source_url="https://anthropic.com"),
            dict(revision, link="https://anthropic.com/"),
            dict(revision, link="https://anthropic.com/research/"),
            dict(revision, link="https://anthropic.com.evil.invalid/research/fake"),
            dict(revision, link="https://anthropic.com:8443/research/fake"),
            dict(revision, source="Anonymous Blog"),
            dict(revision, description="New figures: 0.5%; previous 0.3%; robot cost study updated"),
            dict(revision, description=revision["description"].replace("2026 Q3", "last quarter")),
            dict(revision, description=revision["description"] + "; cost-competitive share: 2.0%"),
            dict(revision, description=revision["description"].replace("0.5%", "150%")),
        ):
            assert check(blocked)[1] < 11, blocked
        # The explicit document date is distinct from the later RSS date.
        old_revision = dict(revision, published="2026-11-23T00:00:00+00:00",
                            description=revision["description"].replace("report date: 2026-11-13", "report date: 2026-09-30"))
        assert check(old_revision)[1] < 11, "An old document reappearing in RSS is not a fresh revision"
        assert len([q for q in base.QUERIES if q==MERGER_BACKFILL])==1
        assert len([q for q in base.QUERIES if q==DKT_BACKFILL])==1

        # Denial, incomplete status and future targets must not be promoted
        # to issuer-confirmed completion, approval, signature or shipment.
        merger_unconfirmed = (
            "Tesla SpaceX merger not closed",
            "Tesla SpaceX merger has not yet been closed",
            "Tesla SpaceX merger never closed",
            "Tesla SpaceX merger cannot be closed",
            "Tesla SpaceX merger won't be closed",
            "Tesla SpaceX merger expected to be closed",
            "Tesla SpaceX merger will be closed",
            "Tesla SpaceX merger closed is unconfirmed",
            "Tesla SpaceX merger closed claim denied",
            "Tesla SpaceX merger no definitive agreement signed",
            "Tesla SpaceX merger definitive agreement signed is planned",
            "Tesla SpaceX merger awaiting shareholder approval",
            "Tesla SpaceX merger shareholder approval required",
            "Tesla SpaceX merger not terminated",
            "Tesla SpaceX merger terminated is planned",
            "테슬라 스페이스X 합병 미완료",
            "테슬라 스페이스X 합병 완료되지 않았다",
            "테슬라 스페이스X 합병 종결 예정",
            "테슬라 스페이스X 합병 종결될 예정이다",
            "테슬라 스페이스X 합병 본계약 체결 계획",
            "테슬라 스페이스X 합병 본계약 체결하지 않았다",
            "테슬라 스페이스X 합병 주주 승인 대기",
            "테슬라 스페이스X 합병 주주 승인 받지 못했다",
            "테슬라 스페이스X 합병 중단 검토",
            "테슬라 스페이스X 합병 철회하지 않았다",
        )
        for title in merger_unconfirmed:
            row = item(title, source="Tesla")
            assert not milestones.stage(row, milestones.MERGER).startswith("official_"), title
            assert check(row)[1] < 11, title

        dkt_unconfirmed = (
            "디케이티 북미 차량용 OLED 정식 공급계약 체결 예정",
            "디케이티 북미 차량용 OLED 구매계약 체결하지 않았다",
            "디케이티 북미 차량용 OLED 첫 출하 완료 미확인",
            "디케이티 북미 차량용 OLED 초도 출하 완료되지 않았다",
            "DKT North American auto OLED no binding supply contract signed",
            "DKT North American auto OLED binding supply contract signed is planned",
            "DKT North American auto OLED first shipment completed is unconfirmed",
        )
        for title in dkt_unconfirmed:
            row = item(title, source="DKT")
            assert milestones.stage(row, milestones.DKT) == "prior_guidance", title
            assert check(row)[1] < 11, title

        # Positive old stages and their stable keys remain unchanged. Future
        # work mentioned after an achieved stage is a separate proposition.
        confirmed = (
            ("Tesla SpaceX merger closed", "Tesla", milestones.MERGER, "official_close"),
            ("Tesla SpaceX merger shareholder approval confirmed", "Tesla", milestones.MERGER, "official_approval"),
            ("Tesla SpaceX merger terminated", "Tesla", milestones.MERGER, "official_termination"),
            ("테슬라 스페이스X 합병 중단", "Tesla", milestones.MERGER, "official_termination"),
            ("테슬라 스페이스X 합병 철회", "Tesla", milestones.MERGER, "official_termination"),
            ("Tesla SpaceX merger terminated; no definitive agreement signed", "Tesla", milestones.MERGER, "official_termination"),
            ("Tesla SpaceX merger definitive agreement signed; closing planned", "Tesla", milestones.MERGER, "official_signed"),
            ("테슬라 스페이스X 합병 본계약 체결, 종결 예정", "Tesla", milestones.MERGER, "official_signed"),
            ("디케이티 북미 차량용 OLED 정식 공급계약 체결, 출하 예정", "DKT", milestones.DKT, "official_auto_oled_contract"),
            ("디케이티 북미 차량용 OLED 첫 출하 완료, 증설 계획", "DKT", milestones.DKT, "official_auto_oled_shipment"),
        )
        for title, source, expected_group, expected_stage in confirmed:
            row = item(title, source=source)
            assert milestones.stage(row, expected_group) == expected_stage, title
            assert check(row)[1] >= 11, title
            expected_key = milestones.hashlib.sha256(
                f"robot-nov13|{expected_group}|{expected_stage}".encode("utf-8")
            ).hexdigest()
            assert check(row)[2] == expected_key, title

        unrevised = item("Anthropic robot work cost estimate not updated", source="Anthropic")
        assert milestones.stage(unrevised, milestones.COST) == "sep30_baseline"
        assert check(unrevised)[1] < 11
    assert base.NOW is original_now, "Historical fixture clock must be restored"

    # Expiry uses Korea time: 2026-11-17 00:00 KST is 11-16 15:00 UTC.
    for instant, expected_count in (
        (dt.datetime(2026, 11, 16, 14, 59, 59, tzinfo=dt.timezone.utc), 1),
        (dt.datetime(2026, 11, 16, 15, 0, 0, tzinfo=dt.timezone.utc), 0),
        (dt.datetime(2026, 11, 18, 0, 0, 0, tzinfo=dt.timezone.utc), 0),
        (dt.datetime(2027, 1, 1, 0, 0, 0, tzinfo=dt.timezone.utc), 0),
    ):
        with at_time(instant):
            for query in (MERGER_BACKFILL, DKT_BACKFILL):
                rows = base.query_news(query)
                assert len(rows) == expected_count, (instant, query, rows)
            # Expired backfills must not disable genuine later milestones.
            later_signed = dict(signed, published=instant.isoformat())
            assert check(later_signed)[1] >= 11
            assert check(later_signed)[2] != mk
        assert base.NOW is original_now, "Boundary test clock must be restored"

    class ClockRestoreProbe(Exception):
        pass

    try:
        with at_time(dt.datetime(2027, 1, 1, tzinfo=dt.timezone.utc)):
            raise ClockRestoreProbe()
    except ClockRestoreProbe:
        pass
    assert base.NOW is original_now, "Clock must also be restored after a failed assertion"
    print("Nov-13 robot event source-stage, expiry boundaries and anti-replay tests: PASS")


if __name__ == "__main__":
    run()

