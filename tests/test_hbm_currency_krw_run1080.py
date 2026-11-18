"""Regress the clock and range corruption observed in HBM run #1080."""

import ast
import html
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import currency_krw_guard as guard


class ActualRun1080CurrencyRegression(unittest.TestCase):
    def setUp(self):
        self.fx = patch.object(guard, "_rate", return_value=(1336.21, "saved run basis"))
        self.fx.start()

    def tearDown(self):
        self.fx.stop()

    def test_actual_clock_text_is_not_interpreted_as_thirty_dollars(self):
        original = (
            "원화는 2026년 11월 18일 서울외국환중개 15:30 달러당 1,333.00원으로 "
            "환산한 발표 당일 참고액이며 실행 시점 환율이나 공식 계약가격이 아님."
        )
        converted = guard.enforce_text(original, hbm_mode=True)
        self.assertEqual(converted, original)
        self.assertNotIn("40,086원", converted)
        guard.validate_text(converted, hbm_mode=True)

    def test_actual_plain_range_converts_both_endpoints(self):
        original = (
            "동일 2.05달러 기준 단순 계산으로 2027년 HBM4 3~5.5달러는 +46~168%이고, "
            "2026년 2.05달러 '이상'인 실제 기준가격에서는 상승률이 더 낮을 수 있음. "
            "따라서 전체 가격대가 100% 이상 상승한다고 단정 금지."
        )
        converted = guard.enforce_text(html.escape(original), hbm_mode=True)
        self.assertIn("3~5.5달러(약 4,009원~약 7,349원)는", converted)
        self.assertNotIn("3~5.5달러(약 7,349원)", converted)
        self.assertEqual(guard.enforce_text(converted, hbm_mode=True), converted)

    def test_existing_range_and_url_are_preserved(self):
        original = (
            '3~5.5달러(약 3,999~7,332원) '
            '<a href="https://example.com/report?at=15:30">원문</a>'
        )
        self.assertEqual(guard.enforce_text(original, hbm_mode=True), original)

    def test_preexisting_single_endpoint_range_fails_closed(self):
        with self.assertRaises(RuntimeError):
            guard.enforce_text("3~5.5달러(약 7,349원)", hbm_mode=True)

    def test_hbm_file_delivery_path_uses_opt_in(self):
        with tempfile.TemporaryDirectory() as directory:
            alert = Path(directory) / "alert.html"
            alert.write_text("2027년 HBM4 3~5.5달러", encoding="utf-8")
            self.assertTrue(guard.enforce_file(alert, hbm_mode=True))
            self.assertIn("3~5.5달러(약 4,009원~약 7,349원)", alert.read_text(encoding="utf-8"))

    def test_plain_foreign_amount_still_converts(self):
        converted = guard.enforce_text("추가 제시가격 6.25달러", hbm_mode=True)
        self.assertIn("6.25달러(약 8,351원)", converted)

    def test_hbm_range_keeps_per_unit_and_korean_particle(self):
        converted = guard.enforce_text("예시 6~8달러/Gb와 엔비디아", hbm_mode=True)
        self.assertIn("6~8달러/Gb(약 8,017원/Gb~약 10,690원/Gb)와", converted)
        self.assertIn("엔비디아", converted)
        self.assertEqual(guard.enforce_text(converted, hbm_mode=True), converted)

    def test_range_conversion_fails_closed_when_fx_is_unavailable(self):
        with patch.object(guard, "_rate", return_value=(None, "unavailable")):
            with self.assertRaises(RuntimeError):
                guard.enforce_text("HBM4 3~5.5달러", hbm_mode=True)

    def test_actual_report_facts_keep_their_stated_fx_basis(self):
        module = ast.parse((ROOT / "scripts" / "hbm_material_event_watch.py").read_text(encoding="utf-8"))
        report_node = next(
            node.value for node in module.body
            if isinstance(node, ast.Assign)
            and any(isinstance(target, ast.Name) and target.id == "REPORTS" for target in node.targets)
        )
        report = next(
            item for item in ast.literal_eval(report_node)
            if item["key"] == "20261118_trendforce_roadshow_hbm4_per_gb_price"
        )
        original = "\n".join(html.escape(fact) for fact in report["facts"])
        converted = guard.enforce_text(original, hbm_mode=True)
        self.assertEqual(converted, original)
        self.assertIn("2.05달러(약 2,733원) 이상", converted)
        self.assertIn("3~5.5달러(약 3,999~7,332원)", converted)
        self.assertIn("15:30 기준 1달러=1,333.00원", converted)
        self.assertNotIn("40,086원", converted)
        self.assertNotIn("2,739원", converted)
        guard.validate_text(converted, hbm_mode=True)


if __name__ == "__main__":
    unittest.main()
