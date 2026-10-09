"""Unit regression tests for the separate LG/BOS/Hana automotive chiplet alert."""
import datetime as dt
import unittest
import contextlib
import json
import pathlib
import tempfile
from unittest import mock

import scripts.lg_auto_chiplet_watch as watcher
from zoneinfo import ZoneInfo

from scripts.lg_auto_chiplet_watch import (
    BASELINE, article_key, candidate_event, event_kind, host_in, norm_title,
    project_kind, quality, relevant, url_key,
)

class VehicleChipletWatchTests(unittest.TestCase):
    def item(self, title, summary=""):
        return {"title": title, "summary": summary}

    def test_end_to_end_baseline_one_alert_and_duplicate_suppression(self):
        with tempfile.TemporaryDirectory() as root:
            root = pathlib.Path(root)
            scan_times = [
                dt.datetime(2026, 10, 9, 19, 0, tzinfo=ZoneInfo("Asia/Seoul")),
                dt.datetime(2026, 10, 10, 10, 0, tzinfo=ZoneInfo("Asia/Seoul")),
                dt.datetime(2026, 10, 10, 10, 10, tzinfo=ZoneInfo("Asia/Seoul")),
            ]
            def article(title, url, publisher):
                item = {
                    "title": title,
                    "url": url,
                    "source": publisher,
                    "source_url": "https://www.mk.co.kr",
                    "quality": "신뢰 언론 보도",
                    "summary": "",
                    "published_kst": "2026-10-10T09:15+09:00",
                    "lane": "차량용 칩렛",
                }
                item["event_id"], item["stage"], item["stage_desc"] = watcher.candidate_event(item)
                return item
            events = [
                article(
                    "LG전자·보스반도체, 보쉬 차량용 칩렛 공급계약 체결 - 매일경제",
                    "https://news.google.com/rss/articles/a", "매일경제",
                ),
                article(
                    "LG전자 보쉬 칩렛 공급 계약 체결, 하나마이크론 패키징 - 연합뉴스",
                    "https://news.google.com/rss/articles/b", "연합뉴스",
                ),
            ]
            with contextlib.ExitStack() as patches:
                patches.enter_context(mock.patch.object(watcher, "STATE", root / "state.json"))
                patches.enter_context(mock.patch.object(watcher, "PENDING", root / "pending.json"))
                patches.enter_context(mock.patch.object(watcher, "ALERT", root / "alert.html"))
                patches.enter_context(mock.patch.object(watcher, "STATUS", root / "status.md"))
                patches.enter_context(mock.patch.object(watcher, "resolve_publisher", lambda url: (url, "기사 보기")))
                clock = patches.enter_context(mock.patch.object(watcher, "now_kst", side_effect=scan_times))
                scan = patches.enter_context(mock.patch.object(watcher, "collect", side_effect=[
                    ([], 13, []), (events, 13, []), (events, 13, []),
                ]))
                watcher.main()
                self.assertFalse(watcher.ALERT.exists())
                self.assertTrue(watcher.PENDING.exists())
                watcher.STATE.write_bytes(watcher.PENDING.read_bytes())
                watcher.main()
                body = watcher.ALERT.read_text(encoding="utf-8")
                self.assertIn("실제 신규 단계: 1건", body)
                self.assertIn("보쉬", body)
                state = json.loads(watcher.PENDING.read_text(encoding="utf-8"))
                self.assertEqual(len([x for x in state["seen"].values() if x.get("alerted")]), 1)
                self.assertEqual(len([x for x in state["seen"].values() if x.get("suppressed_duplicate")]), 1)
                self.assertIn("lg_bos_hana|purchase_contract|bosch|2026-10", state["events"])
                watcher.STATE.write_bytes(watcher.PENDING.read_bytes())
                watcher.main()
                self.assertFalse(watcher.ALERT.exists())

    def test_same_current_bosch_discussion_not_resent_as_new(self):
        with tempfile.TemporaryDirectory() as root:
            root = pathlib.Path(root)
            now = dt.datetime(2026, 10, 10, 12, 0, tzinfo=ZoneInfo("Asia/Seoul"))
            state = {
                "initialized": True,
                "bootstrap_kst": "2026-10-09T19:00:00+09:00",
                "last_checked_kst": "2026-10-09T19:00:00+09:00",
                "seen": {},
                "events": dict(watcher.BASELINE),
            }
            (root / "state.json").write_text(json.dumps(state, ensure_ascii=False), encoding="utf-8")
            item = {
                "title": "LG전자 보쉬 손잡고 차량용 칩렛 적용 논의 - 매일경제",
                "url": "https://news.google.com/rss/articles/news-again",
                "source": "매일경제",
                "summary": "", "quality": "신뢰 언론 보도",
                "source_url": "https://www.mk.co.kr",
                "published_kst": "2026-10-10T11:00+09:00",
            }
            item["event_id"], item["stage"], item["stage_desc"] = watcher.candidate_event(item)
            self.assertEqual(item["event_id"], "lg_bos_hana|bosch_discussion")
            with contextlib.ExitStack() as patches:
                patches.enter_context(mock.patch.object(watcher, "STATE", root / "state.json"))
                patches.enter_context(mock.patch.object(watcher, "PENDING", root / "pending.json"))
                patches.enter_context(mock.patch.object(watcher, "ALERT", root / "alert.html"))
                patches.enter_context(mock.patch.object(watcher, "STATUS", root / "status.md"))
                patches.enter_context(mock.patch.object(watcher, "now_kst", return_value=now))
                patches.enter_context(mock.patch.object(watcher, "collect", return_value=([item], 13, [])))
                watcher.main()
                self.assertFalse(watcher.ALERT.exists())
                stored = json.loads(watcher.PENDING.read_text(encoding="utf-8"))
                self.assertEqual(list(stored["seen"].values())[0]["suppressed_duplicate"], "same_event")

    def test_ministry_20260930_mou_is_development_only(self):
        t = "LG전자·보스반도체·하나마이크론, 차량용 칩렛 SoC 공동개발 협약 체결"
        eid, stage, desc = candidate_event(self.item(t))
        self.assertEqual((eid, stage), ("lg_bos_hana|development_mou", 2))
        self.assertIn("공동개발", desc)

    def test_reported_bosch_use_discussion_is_not_a_contract(self):
        t = "LG전자 보쉬와 차량용 칩렛 개발…보스반도체 AI칩 적용 논의"
        eid, stage, desc = candidate_event(self.item(t))
        self.assertEqual(eid, "lg_bos_hana|bosch_discussion")
        self.assertEqual(stage, 2)
        self.assertIn("구매계약 미확인", desc)

    def test_conjectural_bosch_supply_not_material_contract(self):
        t = "LG전자, 보쉬에 차량용 칩렛 SoC 공급 추진"
        eid, stage, desc = candidate_event(self.item(t))
        self.assertNotEqual(eid, "lg_bos_hana|purchase_contract")
        self.assertNotEqual(stage, 6)

    def test_explicit_signed_bosch_contract_is_new_step(self):
        t = "LG전자, 보쉬와 보스반도체 칩렛 공급계약 체결"
        eid, stage, desc = candidate_event(self.item(t))
        self.assertEqual(eid, "lg_bos_hana|purchase_contract|bosch")
        self.assertEqual(stage, 6)
        self.assertIn("공급계약", desc)

    def test_independent_customer_contracts_not_collapsed(self):
        bosch = self.item("LG전자·보스반도체, 보쉬 차량용 칩렛 공급계약 체결")
        bmw = self.item("LG전자·보스반도체, BMW 차량용 칩렛 공급계약 체결")
        self.assertNotEqual(candidate_event(bosch)[0], candidate_event(bmw)[0])

    def test_repeated_orders_separated_by_month(self):
        a = self.item("LG전자, 보쉬 차량용 칩렛 추가 수주", "")
        b = self.item("LG전자, 보쉬 차량용 칩렛 추가 수주", "")
        a["published_kst"] = "2027-04-03T09:00+09:00"
        b["published_kst"] = "2027-05-07T09:00+09:00"
        self.assertNotEqual(candidate_event(a)[0], candidate_event(b)[0])

    def test_imec_joint_membership_not_marked_bosch_deal(self):
        t = "LG Electronics and Bosch join imec automotive chiplet program"
        eid, stage, description = candidate_event(self.item(t))
        self.assertEqual(eid, "imec_alliance|imec_membership")
        self.assertEqual(stage, 1)
        self.assertIn("구매계약 아님", description)

    def test_mass_production_distinct_from_mou(self):
        t = "LG전자·보스반도체, 차량용 칩렛 양산 개시"
        eid, stage, _ = candidate_event(self.item(t))
        self.assertEqual(eid, "lg_bos_hana|mass_production")
        self.assertEqual(stage, 6)

    def test_automotive_qualification_has_intermediate_stage(self):
        t = "LG전자·보스반도체 차량용 칩렛 AEC-Q100 통과"
        eid, stage, _ = candidate_event(self.item(t))
        self.assertEqual((eid, stage), ("lg_bos_hana|qualification", 5))

    def test_japanese_mirise_project_not_our_lg_project(self):
        t = "BOS Semiconductors chosen for MIRISE automotive chiplet R&D project"
        self.assertFalse(relevant(t))

    def test_general_bosch_imec_program_not_lg_joint_purchase(self):
        t = "Bosch launches autonomous edge chiplet platform consortium"
        self.assertFalse(relevant(t))

    def test_imec_ecosystem_separate_from_trio_project(self):
        t = "LG Electronics and Bosch join imec automotive chiplet program"
        self.assertTrue(relevant(t))
        self.assertEqual(project_kind(t, ""), "imec_alliance")

    def test_same_article_from_relabelled_source(self):
        t1 = "LG전자, 보스반도체와 칩렛 개발 - 매일경제"
        t2 = "LG전자, 보스반도체와 칩렛 개발 - mk.co.kr"
        self.assertEqual(norm_title(t1), norm_title(t2))
        k1 = article_key({"url": "https://news.google.com/rss/articles/ID?oc=5", "title": t1})
        k2 = article_key({"url": "https://news.google.com/rss/articles/ID?oc=6", "title": t2})
        self.assertEqual(k1, k2)

    def test_news_source_not_mistaken_for_official(self):
        self.assertEqual(quality("매일경제", "https://www.mk.co.kr"), "신뢰 언론 보도")
        self.assertEqual(quality("산업통상부", "https://www.motir.go.kr"), "당사자·기관 공식")

    def test_existing_mou_and_bosch_discussion_in_baseline(self):
        self.assertIn("lg_bos_hana|development_mou", BASELINE)
        self.assertIn("lg_bos_hana|bosch_discussion", BASELINE)

    def test_failure_news_is_not_positive_milestone(self):
        title = "LG전자·보스반도체 칩렛 사업 중단, 하나마이크론 개발 중단"
        event_id, stage, desc = candidate_event(self.item(title))
        self.assertEqual((event_id, stage), ("lg_bos_hana|project_blocked", 7))

if __name__ == "__main__":
    unittest.main()
