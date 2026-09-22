import pathlib
import sys
import unittest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "scripts"))
import ai_component_leadtime_watch as w


class LeadTimeParserTests(unittest.TestCase):
    def test_balanced_benchmark_is_not_supply_status(self):
        text = (
            "DRAM current lead time 20 weeks against a balanced lead time of 8 weeks. "
            "ABF current lead time 48-56 weeks against a balanced 12 weeks. "
            "MLCC current lead time 32 weeks against a balanced 12 weeks."
        )
        rows = w.extract_components(text)
        self.assertEqual(rows["DRAM"].get("current"), "20")
        self.assertEqual(rows["DRAM"].get("balanced"), "8")
        self.assertNotIn("status", rows["DRAM"])
        self.assertNotIn("status", rows["ABF"])
        self.assertNotIn("status", rows["MLCC"])

    def test_explicit_status_groups_are_parsed(self):
        text = (
            "균형 상태인 품목은 GPU뿐이다. "
            "DRAM·HDD·ABF는 심각한 공급 부족, "
            "NAND eSSD·MLCC는 공급 제약 상태다."
        )
        rows = w.extract_components(text)
        self.assertEqual(rows["GPU"]["status"], "Balanced")
        self.assertEqual(rows["DRAM"]["status"], "Very Tight")
        self.assertEqual(rows["HDD"]["status"], "Very Tight")
        self.assertEqual(rows["ABF"]["status"], "Very Tight")
        self.assertEqual(rows["NAND(eSSD)"]["status"], "Tight")
        self.assertEqual(rows["MLCC"]["status"], "Tight")

    def test_weekly_002_bad_statuses_are_repaired(self):
        bad = {
            "source": "https://insights.trendforce.com/p/weekly-radar-002",
            "components": {
                "GPU": {"status": "Balanced", "current": "30-40", "balanced": "30-40"},
                "DRAM": {"status": "Balanced", "current": "20", "balanced": "8"},
                "NAND(eSSD)": {"status": "Very Tight", "current": "16", "balanced": "8"},
                "HDD": {"status": "Very Tight", "current": "50", "balanced": "16"},
                "ABF": {"status": "Balanced", "current": "48-56", "balanced": "12"},
                "MLCC": {"status": "Balanced", "current": "32", "balanced": "12"},
            },
        }
        fixed, changed = w.repair_weekly_002_state(bad)
        self.assertEqual(set(changed), {"DRAM", "NAND(eSSD)", "ABF", "MLCC"})
        self.assertEqual(fixed["components"]["DRAM"]["status"], "Very Tight")
        self.assertEqual(fixed["components"]["NAND(eSSD)"]["status"], "Tight")
        self.assertEqual(fixed["components"]["ABF"]["status"], "Very Tight")
        self.assertEqual(fixed["components"]["MLCC"]["status"], "Tight")

    def test_official_source_always_outranks_secondary_recap(self):
        official = w.source_score(
            "https://insights.trendforce.com/p/weekly-radar-003",
            {"HDD": {"current": "50"}},
            "Weekly Radar",
        )
        secondary = w.source_score(
            "https://example.com/repost",
            {name: {"current": "1"} for name in w.ALIASES},
            "TrendForce Weekly Radar",
        )
        self.assertGreater(official, secondary)


class LeadTimeAlertTests(unittest.TestCase):
    def setUp(self):
        self.old = {
            "GPU": {"status": "Balanced", "current": "20-30", "balanced": "20-30"},
            "DRAM": {"status": "Very Tight", "current": "20", "balanced": "8"},
            "NAND(eSSD)": {"status": "Tight", "current": "16", "balanced": "8"},
            "HDD": {"status": "Very Tight", "current": "50", "balanced": "16"},
            "ABF": {"status": "Very Tight", "current": "48-56", "balanced": "12"},
            "MLCC": {"status": "Tight", "current": "30", "balanced": "12"},
        }
        self.new = {
            "GPU": {"status": "Balanced", "current": "30-40", "balanced": "30-40"},
            "DRAM": {"status": "Very Tight", "current": "20", "balanced": "8"},
            "NAND(eSSD)": {"status": "Tight", "current": "16", "balanced": "8"},
            "HDD": {"status": "Very Tight", "current": "50", "balanced": "16"},
            "ABF": {"status": "Very Tight", "current": "48-56", "balanced": "12"},
            "MLCC": {"status": "Tight", "current": "32", "balanced": "12"},
        }

    def test_alert_contains_biggest_change_and_correct_statuses(self):
        alert = w.build_alert(
            self.old,
            self.new,
            ["GPU", "MLCC"],
            "https://insights.trendforce.com/p/weekly-radar-002",
            "2026-09-21T19:01:52+09:00",
            False,
            signals=w.BASELINE["signals"],
            changed_signals=list(w.BASELINE["signals"]),
            evidence={name: {"status", "current", "balanced"} for name in self.new},
        )
        self.assertIn("가장 큰 수치 변화", alert)
        self.assertIn("GPU 리드타임 상승", alert)
        self.assertIn("DRAM</b> | 현재 20주 | 균형 8주 | 상태 심각한 공급 부족", alert)
        self.assertIn("NAND(eSSD)</b> | 현재 16주 | 균형 8주 | 상태 공급 제약", alert)
        self.assertIn("ABF</b> | 현재 48~56주 | 균형 12주 | 상태 심각한 공급 부족", alert)
        self.assertIn("MLCC</b> | 현재 32주 | 균형 12주 | 상태 공급 제약", alert)
        self.assertIn("Rubin 사양 조정", alert)
        self.assertIn("RDIMM 수요 증가", alert)
        self.assertIn("기업용 SSD로 생산능력 재배분", alert)

    def test_unverified_status_is_labeled_not_silently_claimed(self):
        evidence = {name: {"current", "balanced"} for name in self.new}
        alert = w.build_alert(
            self.old,
            self.new,
            [],
            "https://insights.trendforce.com/p/weekly-radar-003",
            "2026-09-28T09:00:00+09:00",
            True,
            evidence=evidence,
        )
        self.assertIn("이번 주 공식 공개본문에서 상태를 직접 판독하지 못한 품목", alert)
        self.assertIn("직전 확정값 유지·이번 주 직접 판독 미확인", alert)


if __name__ == "__main__":
    unittest.main()
