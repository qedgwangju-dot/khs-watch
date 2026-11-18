#!/usr/bin/env python3
"""Offline regression for dated evidence, source gates and delivery eligibility.

Uses an isolated copy of the base module and temporary files. No live queries,
Telegram requests, repository state writes or remote changes are performed.
"""
from __future__ import annotations

import contextlib
import datetime as dt
import importlib.util
import io
import json
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest

import robot_watch_nov18_verified_events as events

NOW = dt.datetime(2026, 11, 18, 6, tzinfo=dt.timezone.utc)


def fixture_base():
    path = Path(__file__).with_name("robotis_physical_ai_watch.py")
    spec = importlib.util.spec_from_file_location("_nov18_isolated_base", path)
    base = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(base)
    base.NOW = NOW
    base.FORCE = False
    base.QUERIES = []
    base.query_news = lambda q: []
    events.install(base)
    return base


def row(title, source="Boston Dynamics", link="https://bostondynamics.com/news/new-test/", description="", published="2026-11-18T01:00:00+00:00", **extra):
    return {"title": title, "description": description, "source": source,
            "link": link, "published": published, **extra}


class VerifiedEventsTests(unittest.TestCase):
    def setUp(self):
        self.base = fixture_base()

    def normalized(self, item):
        return events.normalize_followup(item, self.base.NOW)

    def assert_not_promoted(self, item, event):
        self.assertEqual(events.future_stage(item, event, self.base.NOW), "")
        self.assertEqual(self.normalized(item), item, "Unverified headlines must stay on the existing lane")

    def test_ttl_edges_and_no_future_knowledge(self):
        for instant, count in (
            (events.START - dt.timedelta(microseconds=1), 0),
            (events.START, len(events.EVENTS)),
            (events.END - dt.timedelta(microseconds=1), len(events.EVENTS)),
            (events.END, 0),
            (events.END + dt.timedelta(days=100), 0),
        ):
            self.base.NOW = instant
            self.assertEqual(len(self.base.query_news(events.BACKFILL)), count)
        self.base.NOW = NOW
        known = self.base.query_news(events.BACKFILL)[0]
        key = self.base.key(known)
        self.base.NOW = events.END
        self.assertEqual(self.base.score(known), 0)
        self.assertEqual(self.base.key(known), key)

    def test_source_event_dates_and_one_query_install(self):
        seen_queries = list(self.base.QUERIES)
        events.install(self.base)
        self.assertEqual(self.base.QUERIES, seen_queries)
        self.assertEqual(len(events.SEARCH_QUERIES), 12)
        self.assertEqual(self.base.QUERIES.count(events.BACKFILL), 1)
        for item in self.base.query_news(events.BACKFILL):
            event = item["nov18_event_id"]
            self.assertEqual(item["event_date"], events.EVENTS[event]["date"])
            self.assertEqual(item["published_precision"], "day")
            self.assertEqual(events.identity(events._body(item)), events.PREFIX + event)
            self.assertEqual(self.base.score(item), 46)
            verification = self.base.verification(item, events.PREFIX + event, events._body(item))
            self.assertTrue(verification.startswith(events.EVENTS[event].get("date_label", "발표일")))
        self.assertIn("SEC 8-K/A", events.EVENTS["amd_worldlabs"]["verification"])
        self.assertIn("SEC 공시", events.EVENTS["amd_worldlabs"]["meaning"])
        self.assertTrue(events.EVENTS["genesis"]["url"].startswith("https://www.prnewswire.com/"))
        self.assertIn("20개는 Forbes 보도 기준", events.EVENTS["genesis"]["meaning"])

    def test_genesis_investor_reprints_share_one_key(self):
        titles = (
            "Samsung Next invests in Genesis AI $500 million Series A",
            "NVIDIA joins Genesis AI Series A funding at $3.5 billion valuation",
            "삼성전자·엔비디아 제네시스AI 투자, 5억 달러 유치",
        )
        for title in titles:
            item = row(title, source="Unverified Blog", link="https://example.org/news")
            self.assertEqual(self.base.key(item), events.event_key("genesis"))
            self.assertEqual(self.base.score(item), 0, "Reprints must not independently inject pinned facts")
        self.base.NOW = events.END + dt.timedelta(days=30)
        self.assertEqual(self.base.score(row(titles[0], published=self.base.NOW.isoformat())), 0)

    def test_spot_metrics_do_not_become_atlas_results(self):
        spec = events.EVENTS["bd_gf"]
        self.assertIn("Spot 2대", spec["meaning"])
        self.assertIn("Atlas 성능이 아닙니다", spec["meaning"])
        self.assertIn("시험", spec["risk"] if "시험" in spec["risk"] else spec["meaning"])
        atlas = self.normalized(row("Boston Dynamics GlobalFoundries Atlas field tests completed"))
        spot = row("Boston Dynamics GlobalFoundries Spot field tests completed")
        self.assertGreaterEqual(self.base.score(atlas), 11)
        self.assert_not_promoted(spot, "bd_gf")
        atlas_contract = self.normalized(row("Boston Dynamics GlobalFoundries Atlas signed a binding supply contract"))
        spot_contract = self.normalized(row("Boston Dynamics GlobalFoundries Spot signed a binding supply contract"))
        self.assertGreaterEqual(self.base.score(atlas_contract), 11)
        self.assertGreaterEqual(self.base.score(spot_contract), 11)
        self.assertNotEqual(self.base.key(atlas_contract), self.base.key(spot_contract))
        joint_names = self.normalized(row("Boston Dynamics and GlobalFoundries Atlas signed a binding supply contract"))
        self.assertEqual(self.base.key(joint_names), self.base.key(atlas_contract))

    def test_samsung_conflict_and_shadow_denominator_are_preserved(self):
        body = events.EVENTS["samsung_humanoid"]["meaning"]
        self.assertIn("충돌", body)
        self.assertIn("확정하지 않습니다", body)
        self.assertIn("20→13", body)
        self.assertIn("로봇 전체 전력", body)
        item = row("삼성전자 HR HE 휴머노이드 직구동 확정", source="Unknown", link="https://news.samsung.com/kr/")
        self.assert_not_promoted(item, "samsung_humanoid")

    def test_atlas_model_name_is_not_robot_identity(self):
        self.assertEqual(events.identity("AMD World Labs Atlas model acquisition completed"), events.PREFIX + "amd_worldlabs")
        self.assertEqual(events.identity("Atlas cloud database service expands"), "")
        self.assertEqual(events.identity("Boston Dynamics Atlas robotic hand"), "", "Counterparty GF is required for this event")

    def test_future_contract_is_distinct_and_plans_are_not_completed(self):
        original = row("삼현 북미 휴머노이드 정식 공급계약 체결", source="삼현", link="https://www.samhyun.co.kr/news/new")
        actual = self.normalized(original)
        planned = dict(original, title="삼현 북미 휴머노이드 정식 공급계약 체결 예정")
        negated = dict(original, title="삼현 북미 휴머노이드 본계약 아직 미체결")
        self.assertGreaterEqual(self.base.score(actual), 11)
        self.assertNotEqual(self.base.key(actual), events.event_key("samhyun"))
        self.assert_not_promoted(planned, "samhyun")
        self.assert_not_promoted(negated, "samhyun")
        translated = self.normalized(row("Samhyun North American humanoid signed a binding supply contract", source="Samhyun", link="https://www.samhyun.co.kr/en/new"))
        self.assertEqual(self.base.key(actual), self.base.key(translated))
        same_day = self.normalized(dict(original, published="2026-11-17T01:00:00+00:00"))
        self.assertGreaterEqual(self.base.score(same_day), 11, "A distinct completed stage need not wait until the next day")
        self.assertEqual(self.base.key(same_day), self.base.key(actual), "A changed publication date is not another contract")
        old = dict(original, published="2026-11-16T01:00:00+00:00")
        self.assert_not_promoted(old, "samhyun")
        future = dict(original, published="2026-11-19T01:00:00+00:00")
        self.assert_not_promoted(future, "samhyun")

    def test_official_name_and_host_are_both_required(self):
        title = "Boston Dynamics GlobalFoundries Atlas field tests completed"
        for source, link in (("Unknown Blog", "https://bostondynamics.com/news/a"),
                             ("Boston Dynamics", "https://example.org/a"),
                             ("Boston Dynamics", "https://bostondynamics.com.evil.example/a"),
                             ("Boston Dynamics", "https://news.google.com/rss/articles/123")):
            self.assert_not_promoted(row(title, source=source, link=link), "bd_gf")
        discovery = self.normalized(row(title, link="https://news.google.com/rss/articles/123", source_url="https://bostondynamics.com"))
        self.assertGreaterEqual(self.base.score(discovery), 11)
        verification = self.base.verification(discovery, events.identity(title), title)
        self.assertIn("공식 제목 검색색인", verification)
        self.assertIn("본문 추가 검증", verification)
        self.assertIn("승격하지 않음", verification)

    def test_future_render_never_reuses_pinned_body(self):
        base = fixture_base()
        # Re-create install over a controlled source so its query normalizer is tested.
        path = Path(__file__).with_name("robotis_physical_ai_watch.py")
        spec = importlib.util.spec_from_file_location("_nov18_render_base", path)
        base = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(base)
        base.NOW, base.QUERIES = NOW, []
        base.query_news = lambda q: [row("Boston Dynamics GlobalFoundries Atlas field tests completed")]
        events.install(base)
        actual = base.query_news("future-test")[0]
        text = events._body(actual)
        group = base.topic_group(text)
        category = base.category(text, group)
        rendered = base.meaning(category)
        self.assertIn("후속", category)
        self.assertIn("본문 추가 검증", rendered)
        self.assertNotIn("900km", rendered)
        self.assertNotIn("2027년 초", actual["title"])
        self.assertNotEqual(base.key(actual), events.event_key("bd_gf"))

    def test_existing_lg_delivery_key_and_mcnex_baseline(self):
        self.assertEqual(events.event_key("lg_safety"), "df5ed2e98d898262d3f40710a990b07027c78cc9f45f9d4ec7150e5bb2b6b1c8")
        repeated = row("엠씨넥스 아틀라스 공급망 진입, 2027년 확대 전망", source="대신증권", link="https://www.daishin.com/report")
        self.assertEqual(self.base.score(repeated), 0)
        actual = self.normalized(row("엠씨넥스 아틀라스 정식 공급계약 체결", source="엠씨넥스", link="https://www.mcnex.com/news/new"))
        self.assertGreaterEqual(self.base.score(actual), 11)
        self.assertNotEqual(self.base.key(actual), self.base.key(repeated))

    def test_future_knr_integration_is_not_current_lower_body_success(self):
        self.base.NOW = dt.datetime(2026, 12, 1, 6, tzinfo=dt.timezone.utc)
        original = row("케이엔알시스템 슈퍼휴머노이드 전신 통합 완료", source="케이엔알시스템", link="https://www.knrsys.com/news/actual", published="2026-12-01T01:00:00+00:00")
        actual = self.normalized(original)
        self.assertGreaterEqual(self.base.score(actual), 11)
        self.assertNotEqual(self.base.key(actual), events.event_key("knr"))
        self.assert_not_promoted(dict(original, title=original["title"] + " 목표"), "knr")

    def test_negative_and_unrelated_completion_never_promote(self):
        cases = (
            ("OpenAI robotics physical robot demonstration completed claim denied", "openai_reorg", "OpenAI", "https://openai.com/news/test"),
            ("OpenAI robotics physical robot demonstration completed; company denies claim", "openai_reorg", "OpenAI", "https://openai.com/news/test"),
            ("OpenAI robotics physical robot demonstration completed?", "openai_reorg", "OpenAI", "https://openai.com/news/test"),
            ("OpenAI robotics physical robot demonstration completed isn't confirmed", "openai_reorg", "OpenAI", "https://openai.com/news/test"),
            ("OpenAI 로봇 실물 시연 완료는 사실무근", "openai_reorg", "OpenAI", "https://openai.com/news/test"),
            ("AMD World Labs acquisition completed; TSMC signed a binding supply agreement", "amd_worldlabs", "AMD", "https://newsroom.amd.com/news/test"),
            ("AMD World Labs acquisition completed and TSMC signed a binding supply agreement", "amd_worldlabs", "AMD", "https://newsroom.amd.com/news/test"),
            ("AMD World Labs 인수 완료 및 TSMC 정식 공급계약 체결", "amd_worldlabs", "AMD", "https://newsroom.amd.com/news/test"),
            ("삼현 북미 휴머노이드 본계약 체결 계획", "samhyun", "삼현", "https://www.samhyun.co.kr/news/test"),
            ("케이엔알시스템 슈퍼휴머노이드 전신 통합 미완료", "knr", "케이엔알시스템", "https://www.knrsys.com/news/test"),
        )
        for title, event, source, link in cases:
            with self.subTest(title=title):
                self.assert_not_promoted(row(title, source=source, link=link), event)
        actual = self.normalized(row("OpenAI robotics physical robot demonstration completed", source="OpenAI", link="https://openai.com/news/test"))
        self.assertEqual(actual["nov18_followup_stage"], "demonstration_completed")
        self.assertEqual(self.base.score(actual), 48)

    def test_material_changes_are_distinct_but_publication_dates_are_not(self):
        def contract(suffix="", day="18"):
            return self.normalized(row("삼현 북미 휴머노이드 정식 공급계약 체결 " + suffix,
                                       source="삼현", link="https://www.samhyun.co.kr/news/test",
                                       published=f"2026-11-{day}T01:00:00+00:00"))
        self.assertEqual(self.base.key(contract(day="17")), self.base.key(contract(day="18")))
        self.assertNotEqual(self.base.key(contract("100억원")), self.base.key(contract("200억원")))
        self.assertEqual(self.base.key(contract("100억원")), self.base.key(contract("10,000,000,000원")))
        self.assertNotEqual(self.base.key(contract("100대")), self.base.key(contract("200대")))
        self.assertNotEqual(self.base.key(contract("고객사: Alpha")), self.base.key(contract("고객사: Beta")))
        self.assertEqual(self.base.key(contract("고객사: Alpha")), self.base.key(contract("customer: Alpha")))

    def test_unhandled_news_delegates_every_existing_function(self):
        headlines = (
            "삼현 북미 휴머노이드 액추에이터 후속 발주 확보, 추가 수주 100억원",
            "Genesis AI raises $800 million Series B financing for Eno robots",
            "OpenAI robotics research team publishes a new control model after reorganization",
            "Samsung System LSI announces dedicated humanoid robotics processor program",
            "로보티즈 신공장 추가 설비투자와 생산능력 확대 발표",
        )
        calls = []
        def legacy(name, answer):
            def function(*args):
                calls.append((name, args))
                return answer
            return function
        base = SimpleNamespace(NOW=NOW, QUERIES=[],
            query_news=lambda q: [row(q)], topic_group=legacy("group", "legacy_group"),
            score=legacy("score", 37), key=legacy("key", "legacy_key"),
            category=legacy("category", "legacy_category"), meaning=legacy("meaning", "legacy_meaning"),
            risk=legacy("risk", "legacy_risk"), verification=legacy("verification", "legacy_verification"),
            tag_for=legacy("tag", "legacy_tag"))
        events.install(base)
        for title in headlines:
            with self.subTest(title=title):
                calls.clear()
                item = base.query_news(title)[0]
                self.assertEqual(item, row(title))
                text = events._body(item)
                group = base.topic_group(text)
                self.assertEqual(group, "legacy_group")
                self.assertEqual(base.score(item), 37)
                self.assertEqual(base.key(item), "legacy_key")
                category = base.category(text, group)
                self.assertEqual(category, "legacy_category")
                self.assertEqual(base.meaning(category), "legacy_meaning")
                self.assertEqual(base.risk(category), "legacy_risk")
                self.assertEqual(base.verification(item, group, text), "legacy_verification")
                self.assertEqual(base.tag_for(group), "legacy_tag")
                self.assertEqual([name for name, _ in calls], ["group", "score", "key", "category", "meaning", "risk", "verification", "tag"])

    def test_real_base_selection_preserves_942_seen_and_overflow(self):
        with tempfile.TemporaryDirectory(prefix="robot-nov18-") as temporary:
            root = Path(temporary)
            self.base.OUT_DIR = root / "out"
            self.base.STATE_PATH = root / "state.json"
            self.base.PENDING_PATH = root / "pending.json"
            self.base.ALERT_PATH = root / "alert.txt"
            self.base.STATUS_PATH = root / "status.md"
            original_seen = {f"historic-{i}" for i in range(941)} | {events.event_key("lg_safety")}
            self.base.STATE_PATH.write_text(json.dumps({"seen": sorted(original_seen), "seeded": True}), encoding="utf-8")
            with contextlib.redirect_stdout(io.StringIO()):
                self.base.main()
            pending = json.loads(self.base.PENDING_PATH.read_text(encoding="utf-8"))
            self.assertEqual(len(pending["last_selected"]), self.base.MAX_ALERTS)
            self.assertTrue(original_seen.issubset(pending["seen"]))
            self.assertNotIn(events.event_key("lg_safety"), pending["last_selected"])
            candidates = {events.event_key(name) for name in events.EVENTS}
            overflow = candidates - set(pending["seen"])
            self.assertTrue(overflow)
            self.assertEqual(len(set(pending["seen"]) - original_seen), len(pending["last_selected"]))
            # Simulate the existing success-persistence gate; no external send.
            self.base.STATE_PATH.write_text(json.dumps(pending), encoding="utf-8")
            with contextlib.redirect_stdout(io.StringIO()):
                self.base.main()
            second = json.loads(self.base.PENDING_PATH.read_text(encoding="utf-8"))
            self.assertEqual(set(second["last_selected"]), overflow)
            self.assertTrue(original_seen.issubset(second["seen"]))
            self.base.STATE_PATH.write_text(json.dumps(second), encoding="utf-8")
            with contextlib.redirect_stdout(io.StringIO()):
                self.base.main()
            third = json.loads(self.base.PENDING_PATH.read_text(encoding="utf-8"))
            self.assertEqual(third["last_selected"], [])
            self.assertEqual(self.base.ALERT_PATH.read_text(encoding="utf-8"), "")

    def test_real_base_first_seed_stays_silent(self):
        with tempfile.TemporaryDirectory(prefix="robot-nov18-seed-") as temporary:
            root = Path(temporary)
            for name, value in (("OUT_DIR", root / "out"), ("STATE_PATH", root / "state.json"),
                                ("PENDING_PATH", root / "pending.json"), ("ALERT_PATH", root / "alert.txt"),
                                ("STATUS_PATH", root / "status.md")):
                setattr(self.base, name, value)
            self.base.STATE_PATH.write_text(json.dumps({"seeded": False, "seen": ["existing"]}), encoding="utf-8")
            with contextlib.redirect_stdout(io.StringIO()):
                self.base.main()
            pending = json.loads(self.base.PENDING_PATH.read_text(encoding="utf-8"))
            self.assertEqual(pending["last_selected"], [])
            self.assertEqual(self.base.ALERT_PATH.read_text(encoding="utf-8"), "")
            self.assertIn("existing", pending["seen"])
            self.assertTrue({events.event_key(name) for name in events.EVENTS}.issubset(pending["seen"]))


def run():
    result = unittest.TextTestRunner(verbosity=1).run(unittest.defaultTestLoader.loadTestsFromTestCase(VerifiedEventsTests))
    if not result.wasSuccessful():
        raise AssertionError("Nov-18 verified event regressions failed")
    print("Nov-18 dated events, official source gates, semantic dedup, first-seed and overflow: PASS")


if __name__ == "__main__":
    run()
