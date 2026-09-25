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
        self.assertIn("DRAM</b> | 현재 20주 | 균형 8주 | 격차 2.5배 | 상태 심각한 공급 부족", alert)
        self.assertIn("NAND(eSSD)</b> | 현재 16주 | 균형 8주 | 격차 2.0배 | 상태 공급 제약", alert)
        self.assertIn("ABF</b> | 현재 48~56주 | 균형 12주 | 격차 4.3배 | 상태 심각한 공급 부족", alert)
        self.assertIn("MLCC</b> | 현재 32주 | 균형 12주 | 격차 2.7배 | 상태 공급 제약", alert)
        self.assertIn("Rubin 사양 조정", alert)
        self.assertIn("RDIMM 수요 증가", alert)
        self.assertIn("기업용 SSD로 생산능력 재배분", alert)
        self.assertIn("<b>수익구조</b>", alert)
        self.assertIn("<b>1단계 현재 숫자 추적</b>", alert)
        self.assertIn("<b>2단계 미래 재평가 요인 발굴</b>", alert)
        self.assertIn("<b>관련 기업 지도</b>", alert)
        self.assertIn("<b>공정 병목 후보</b>", alert)
        self.assertIn("<b>숨은 역풍·실패모드</b>", alert)
        self.assertIn("<b>결론</b>", alert)
        self.assertIn("<b>핵심 한 줄 요약</b>", alert)
        self.assertIn("ABF</b> | 현재 48~56주 | 균형 12주 | 격차 4.3배", alert)
        self.assertIn("삼성전기·Ibiden·Unimicron·Nan Ya PCB", alert)

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


class AgenticCPUWatchTests(unittest.TestCase):
    def test_bofa_cpu_snapshot_parse(self):
        text = (
            "BofA raises CY30E server CPU TAM to $210.6 billion. "
            "AI CPU TAM reaches $180.4 billion. "
            "Agentic AI CPU racks reach $90.2 billion, about 42.8% of the market. "
            "CPU-to-GPU ratio moves toward 1:1."
        )
        snap = w.extract_cpu_snapshot(text, "https://finvaulta.com/research/example")
        self.assertEqual(snap["server_cpu_tam_2030_bn"], 210.6)
        self.assertEqual(snap["agentic_cpu_tam_2030_bn"], 90.2)
        self.assertEqual(snap["ai_cpu_tam_2030_bn"], 180.4)
        self.assertEqual(snap["agentic_share_pct"], 42.8)
        self.assertEqual(snap["cpu_gpu_ratio"], "1:1")

    def test_cpu_materiality_thresholds(self):
        old = dict(w.CPU_BASELINE)
        small = dict(old)
        small["server_cpu_tam_2030_bn"] = 225.0
        self.assertNotIn("server_cpu_tam_2030_bn", w.cpu_material_changes(old, small))
        large = dict(old)
        large["server_cpu_tam_2030_bn"] = 235.0
        self.assertIn("server_cpu_tam_2030_bn", w.cpu_material_changes(old, large))
        share = dict(old)
        share["agentic_share_pct"] = 48.0
        self.assertIn("agentic_share_pct", w.cpu_material_changes(old, share))

    def test_component_alert_embeds_cpu_axis(self):
        alert = w.build_alert(
            w.BASELINE["components"],
            w.BASELINE["components"],
            [],
            w.BASELINE["source"],
            "2026-09-21T19:00:00+09:00",
            False,
            signals=w.BASELINE["signals"],
            cpu_state=w.CPU_BASELINE,
        )
        self.assertIn("<b>CPU·에이전트형 AI 수요축</b>", alert)
        self.assertIn("2030 서버 CPU 시장 210.6십억달러", alert)
        self.assertIn("CPU:GPU 1:1", alert)
        self.assertIn("DDR5 RDIMM·기업용 SSD·네트워크·ABF·MLCC", alert)

    def test_cpu_alert_contains_full_investment_chain(self):
        old = dict(w.CPU_BASELINE)
        new = dict(old)
        new["server_cpu_tam_2030_bn"] = 240.0
        alert = w.build_cpu_alert(
            old,
            new,
            ["server_cpu_tam_2030_bn"],
            "https://example.com/new",
            "2026-09-25T10:00:00+09:00",
            validation_note="AMD 공식자료에서 실제 배치 검증",
        )
        self.assertIn("<b>수익구조</b>", alert)
        self.assertIn("<b>1단계 현재 숫자 추적</b>", alert)
        self.assertIn("<b>2단계 미래 재평가 요인 발굴</b>", alert)
        self.assertIn("<b>관련 기업 지도</b>", alert)
        self.assertIn("<b>공정 병목 후보</b>", alert)
        self.assertIn("<b>숨은 역풍·실패모드</b>", alert)
        self.assertIn("실제 수요 검증", alert)


if __name__ == "__main__":
    unittest.main()
