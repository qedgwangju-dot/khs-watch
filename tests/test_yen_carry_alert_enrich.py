from __future__ import annotations

import pathlib
import sys
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import yen_carry_alert_enrich as enrich  # noqa: E402


class YenCarryAlertEnrichTests(unittest.TestCase):
    def test_calculate_24h_change_and_range(self) -> None:
        start = 1_800_000_000
        timestamps = [start, start + 43_200, start + 86_400]
        closes = [160.0, 157.0, 156.0]
        payload = {
            "chart": {
                "result": [
                    {
                        "timestamp": timestamps,
                        "indicators": {"quote": [{"close": closes}]},
                    }
                ]
            }
        }
        change_pct, low, high, span = enrich.calculate_24h(payload)
        self.assertAlmostEqual(change_pct, -2.5)
        self.assertEqual(low, 156.0)
        self.assertEqual(high, 160.0)
        self.assertEqual(span, 4.0)

    def test_insert_line_after_usd_jpy(self) -> None:
        body = (
            "조회 시각: 2026-08-02 00:00:00 KST\n"
            "USD/JPY: 156.000 (-1.00%)\n"
            "Nasdaq: -2.00%\n"
        )
        line = (
            "USD/JPY 24시간: -2.50% · 저가 156.000 · "
            "고가 160.000 · 범위 4.000엔"
        )
        result = enrich.insert_line(body, line)
        lines = result.splitlines()
        self.assertEqual(lines[2], line)

    def test_fast_alert_marks_sector_effect_as_short_term(self) -> None:
        block = enrich.sector_impact_block(
            {"stage": 1, "fast_stage": 1, "sustained_stage": 0}
        )
        self.assertIn("급변 직후 영향", block)
        self.assertIn("실제 실적 영향은 엔고의 지속 여부", block)
        self.assertIn("일본 부담: 자동차·전자·기계", block)
        self.assertIn("한국 반도체: 직접 영향 제한적", block)

    def test_sustained_alert_marks_profit_effect_as_more_relevant(self) -> None:
        block = enrich.sector_impact_block(
            {"stage": 2, "fast_stage": 0, "sustained_stage": 2}
        )
        self.assertIn("판정 강도: 강함", block)
        self.assertIn("지속 엔고 영향", block)
        self.assertIn("매출 환산·수입 원가", block)
        self.assertIn("전력·항공·유통·식품", block)

    def test_insert_sector_block_is_idempotent_and_before_disclaimer(self) -> None:
        body = (
            "조회 시각: 2026-08-03 18:00:00 KST\n"
            "최종 판정: 1단계\n\n"
            f"{enrich.FINAL_MARKER}\n"
        )
        block = enrich.sector_impact_block(
            {"stage": 1, "fast_stage": 1, "sustained_stage": 0}
        )
        first = enrich.insert_sector_block(body, block)
        second = enrich.insert_sector_block(first, block)
        self.assertEqual(first, second)
        self.assertEqual(second.count(enrich.SECTOR_HEADING), 1)
        self.assertLess(
            second.index(enrich.SECTOR_HEADING),
            second.index(enrich.FINAL_MARKER),
        )


if __name__ == "__main__":
    unittest.main()
