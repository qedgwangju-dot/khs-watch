import pathlib
import sys
import unittest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "scripts"))
import ai_component_leadtime_watch as w
import agentic_cpu_watch as cpuw


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

    def test_weekly_004_exact_table_lock_matches_user_provided_trendforce_screenshot(self):
        lock = w.WEEKLY_004_LOCK
        self.assertEqual(lock["as_of"], "2026-10-05")
        self.assertEqual(len(lock["components"]), 7)
        expected = {
            "CPU": ("Tight", "25-30", "16-20"),
            "GPU": ("Balanced", "30-40", "30-40"),
            "DRAM": ("Very Tight", "20", "8"),
            "NAND(eSSD)": ("Tight", "16", "8"),
            "HDD": ("Very Tight", "50", "16"),
            "ABF": ("Very Tight", "48-56", "12"),
            "MLCC": ("Tight", "35", "12"),
        }
        for name, triple in expected.items():
            self.assertEqual(w.canonical_component(lock["components"][name]), triple)

    def test_weekly_004_repair_corrects_dram_status_and_mlcc_stale_value(self):
        stale = {
            "as_of": "2026-10-05",
            "source": "https://insights.trendforce.com/p/weekly-radar-004",
            "components": {
                **w.WEEKLY_004_LOCK["components"],
                "DRAM": {"status": "Tight", "current": "20", "balanced": "8"},
                "MLCC": {"status": "Tight", "current": "32", "balanced": "12"},
            },
            "signals": {"MLCC": "old"},
        }
        fixed, component_changes, signal_changes = w.repair_weekly_004_state(stale)
        self.assertEqual(set(component_changes), {"DRAM", "MLCC"})
        self.assertEqual(fixed["components"]["DRAM"]["status"], "Very Tight")
        self.assertEqual(fixed["components"]["MLCC"]["current"], "35")
        self.assertIn("GPU", signal_changes)
        self.assertIn("MLCC", signal_changes)
        alert = w.build_weekly_004_correction_alert(
            stale["components"], fixed["components"], component_changes, signal_changes
        )
        self.assertIn("DRAM 상태 정정", alert)
        self.assertIn("MLCC 최신값", alert)
        self.assertIn("32주 → 35주", alert)
        self.assertIn("7개 품목", alert)

    def test_weekly_004_rows_parse_when_table_text_is_available(self):
        text = (
            "CPU Tight 25-30W 16-20W "
            "GPU Balanced 30-40W 30-40W "
            "DRAM Very Tight 20W 8W "
            "NAND Tight 16W 8W "
            "HDD Very Tight 50W 16W "
            "ABF Very Tight 48-56W 12W "
            "MLCC Tight 35W 12W"
        )
        rows = w.extract_components(text)
        self.assertEqual(rows["DRAM"]["status"], "Very Tight")
        self.assertEqual(rows["MLCC"]["current"], "35")
        self.assertEqual(rows["CPU"]["balanced"], "16-20")


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


    def test_cpu_lead_time_is_parsed_as_seventh_component(self):
        text = (
            "CPU current lead time 25-30 weeks against a balanced lead time of 16-20 weeks. "
            "CPU is Tight while GPU is Balanced."
        )
        rows = w.extract_components(text)
        self.assertEqual(rows["CPU"].get("current"), "25-30")
        self.assertEqual(rows["CPU"].get("balanced"), "16-20")
        self.assertEqual(rows["CPU"].get("status"), "Tight")

    def test_ubs_cross_stack_project_baseline_matches_attached_chart(self):
        base = w.UBS_PROJECT_LEADTIME_BASELINE
        self.assertFalse(base["directly_comparable_to_component_delivery_lead_time"])
        expected = {
            "Foundry": (36, 48),
            "Semicap equipment": (12, 24),
            "Adv. packaging / substrates": (12, 18),
            "Storage systems": (12, 24),
            "GPUs / AI accelerators": (6, 12),
            "Memory (HBM / DRAM)": (6, 12),
            "Optical transceivers / networking": (3, 9),
            "CPUs": (3, 6),
            "Servers": (1, 2),
        }
        for segment, (low, high) in expected.items():
            self.assertEqual(base["segments"][segment]["min_months"], low)
            self.assertEqual(base["segments"][segment]["max_months"], high)


    def test_newer_official_weekly_radar_beats_older_fuller_issue(self):
        older = {
            "direct_url": "https://insights.trendforce.com/p/weekly-radar-002",
            "published_at_kst": "2026-09-21T09:00:00+09:00",
            "score": 1100,
            "full_text": "TrendForce Weekly Radar",
        }
        newer = {
            "direct_url": "https://insights.trendforce.com/p/weekly-radar-003",
            "published_at_kst": "2026-09-28T09:00:00+09:00",
            "score": 1040,
            "full_text": "TrendForce Weekly Radar",
        }
        self.assertGreater(w.candidate_sort_key(newer), w.candidate_sort_key(older))


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

    def test_alert_is_compact_and_keeps_all_current_numbers(self):
        alert = w.build_alert(
            self.old,
            self.new,
            ["GPU", "MLCC"],
            "https://insights.trendforce.com/p/weekly-radar-002",
            "2026-09-21T19:01:52+09:00",
            False,
            signals=w.BASELINE["signals"],
            changed_signals=["GPU", "MLCC"],
            evidence={name: {"status", "current", "balanced"} for name in self.new},
        )
        self.assertIn("<b>핵심 변화</b>", alert)
        self.assertIn("<b>현재 숫자</b>", alert)
        self.assertIn("<b>미래 재평가</b>", alert)
        self.assertIn("<b>관련 기업</b>", alert)
        self.assertIn("<b>역풍·다음 확인</b>", alert)
        self.assertIn("ABF 48~56주/12주 (4.3배)", alert)
        self.assertIn("HDD 50주/16주 (3.1배)", alert)
        self.assertIn("DRAM 20주/8주 (2.5배)", alert)
        self.assertIn("NAND(eSSD) 16주/8주 (2.0배)", alert)
        self.assertIn("MLCC 32주/12주 (2.7배)", alert)
        self.assertIn("GPU 30~40주/30~40주 (1.0배)", alert)
        self.assertIn("삼성전기·Ibiden·Unimicron·Nan Ya PCB", alert)
        self.assertNotIn("<b>수익구조</b>", alert)
        self.assertNotIn("<b>공정 병목 후보</b>", alert)
        self.assertNotIn("<b>추적 기준</b>", alert)
        self.assertLess(len(alert), 2400)

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
        self.assertIn("이전 확정값 유지:", alert)
        self.assertNotIn("직전 확정값 유지·이번 주 직접 판독 미확인", alert)


    def test_cpu_change_shows_ubs_project_horizon_without_equating_metrics(self):
        old = dict(self.new)
        new = dict(self.new)
        new["CPU"] = {"status": "Tight", "current": "25-30", "balanced": "16-20"}
        alert = w.build_alert(
            old,
            new,
            ["CPU"],
            "https://insights.trendforce.com/p/weekly-radar-003",
            "2026-09-28T09:00:00+09:00",
            False,
            signals={"CPU": "에이전틱 AI·CSP 인하우스 설계 확대로 서버 CPU 조달 압력이 부각"},
            changed_signals=["CPU"],
            evidence={"CPU": {"status", "current", "balanced"}},
        )
        self.assertIn("<b>신규 추적 CPU:</b> 25~30주 / 균형 16~20주 / 공급 제약", alert)
        self.assertIn("UBS 프로젝트 기준", alert)
        self.assertIn("CPU 3~6개월", alert)
        self.assertIn("직접 비교 금지", alert)
        direction, worse, better = w.supply_direction(old, new)
        self.assertEqual((direction, worse, better), ("→ 변화 제한", 0, 0))


    def test_combined_leadtime_and_cpu_alert_fits_one_telegram_chunk(self):
        old = dict(self.new)
        new = dict(self.new)
        new["CPU"] = {"status": "Tight", "current": "25-30", "balanced": "16-20"}
        lead = w.build_alert(
            old,
            new,
            ["CPU"],
            "https://insights.trendforce.com/p/weekly-radar-003",
            "2026-09-28T19:03:30+09:00",
            False,
            signals={"CPU": "에이전틱 AI·CSP 인하우스 설계 확대로 서버 CPU 조달 압력이 부각"},
            changed_signals=["CPU"],
            evidence={"CPU": {"status", "current", "balanced"}},
        )
        cpu = cpuw.snapshot_block(
            cpuw.BASELINE,
            1348.3,
            "2026-10-02",
            [{"key": "server_cpu_tam_2030_usd_bn", "label": "2030 서버 CPU 시장", "before": 190.0, "after": 210.6, "delta": 10.8, "mode": "pct"}],
            None,
            [{"title": "AMD confirms higher CPU intensity for agentic AI"}],
            standalone=False,
        )
        combined = lead.rstrip() + "\n\n" + cpu.strip()
        utf16_units = len(combined.encode("utf-16-le")) // 2
        self.assertLess(utf16_units, 3300)
        for verbose_heading in (
            "<b>수익구조</b>",
            "<b>공정 병목 후보</b>",
            "<b>숨은 역풍·실패모드</b>",
            "<b>알림 기준</b>",
            "<b>추적 기준</b>",
        ):
            self.assertNotIn(verbose_heading, combined)


if __name__ == "__main__":
    unittest.main()
