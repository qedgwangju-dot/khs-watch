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
        body = "조회 시각: 2026-08-02 00:00:00 KST\nUSD/JPY: 156.000 (-1.00%)\nNasdaq: -2.00%\n"
        line = "USD/JPY 24시간: -2.50% · 저가 156.000 · 고가 160.000 · 범위 4.000엔"
        result = enrich.insert_line(body, line)
        lines = result.splitlines()
        self.assertEqual(lines[2], line)


if __name__ == "__main__":
    unittest.main()
