import pathlib
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "scripts"))
import memory_spot_cycle_watch as w


class MemorySpotCycleWatchTests(unittest.TestCase):
    def test_4q26_price_forecast_exposes_specific_contract_price_changes(self):
        blob = (
            "4Q26 Contract Prices for Enterprise SSD Surge 23-28% QoQ Against Trend, "
            "Consumer Segments See Only Minimal Compensatory Increases, "
            "Overall NAND Flash Up 15-20% QoQ. "
            "AI Server Demand Continues to Support 4Q26 DRAM Price Hikes."
        )
        details = w._price_change_details("4Q26 Memory Price Forecast", blob)
        self.assertIn("기업용 SSD 계약가: 4Q26 +23~28% QoQ", details)
        self.assertIn("NAND Flash 전체 계약가: 4Q26 +15~20% QoQ", details)
        self.assertTrue(any("DRAM 계약가" in x and "세부 등락률 미제시" in x for x in details))

    def test_dram_bulletin_states_price_type_and_public_numeric_limit(self):
        blob = (
            "Tight supply and robust CSP demand keep DRAM undersupplied; "
            "TrendForce lifts its 4Q26 contract price outlook. "
            "Segment Trends: PC and server lead gains; mobile and consumer cool on high bases."
        )
        details = w._price_change_details("DRAM Market Bulletin - Sep. 23, 2026", blob)
        self.assertTrue(any("DRAM 계약가: 4Q26 전망 상향" in x for x in details))
        self.assertTrue(any("PC·서버 DRAM" in x for x in details))

    def test_hbm_bulletin_does_not_invent_a_numeric_band(self):
        blob = (
            "Amid tight supply and richer HBM4 mix, TrendForce sharply lifts its 2027 HBM price outlook. "
            "8-Hi leads shipments and has a per-Gb premium over 12-Hi."
        )
        details = w._price_change_details("HBM Market Bulletin - Sep. 22, 2026", blob)
        self.assertTrue(any("2027년 전망 상향" in x for x in details))
        self.assertTrue(any("새 등락률·단가 범위 미제시" in x for x in details))
        self.assertTrue(any("8단 HBM" in x for x in details))

    def test_main_runs_currency_guard_after_output_generation(self):
        with patch.object(w, "collect", return_value=([], [])), \
             patch.object(w, "write_outputs"), \
             patch.object(w.currency_krw_guard, "enforce_file") as guard:
            w.main()
        guard.assert_called_once_with(w.ALERT_PATH)


if __name__ == "__main__":
    unittest.main()
