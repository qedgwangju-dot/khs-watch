import copy
import json
import sys
import unittest
from datetime import date
from decimal import Decimal
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
from us_positioning_horizons import (
    months_before, price_month_windows, position_month_windows,
    verified_price_return, verified_position_change,
)
import us_positioning_presentation as presentation
import test_us_positioning_presentation as core_tests


def source_fixture():
    return json.loads((ROOT / "tests/fixtures/us_positioning_month_horizons_20261015.json").read_text(encoding="utf-8"))


def enriched_snapshot():
    source = source_fixture()
    values = core_tests.snapshot()
    values["Nasdaq SOX|sox"]["metrics"]["month_windows"] = price_month_windows(
        source["end_date"], source["end_close"], source["yahoo_rows"], source["nasdaq_rows"],
    )
    values["CFTC|cot"]["history_3y"]["month_windows"] = position_month_windows(
        source["nq_rows"], source["nq_end_date"], values["CFTC|cot"]["nq_mini"],
    )
    return values


class CalendarPriceTests(unittest.TestCase):
    def test_month_end_and_leap_year_are_calendar_months_not_21_or_63_sessions(self):
        self.assertEqual(months_before(date(2024, 3, 31), 1), date(2024, 2, 29))
        self.assertEqual(months_before(date(2025, 3, 31), 1), date(2025, 2, 28))
        self.assertEqual(months_before(date(2026, 1, 31), 3), date(2025, 10, 31))

    def test_actual_official_monthly_operands_and_independent_decimal_returns(self):
        m = enriched_snapshot()["Nasdaq SOX|sox"]["metrics"]["month_windows"]
        for key, base_date, official in (("1m", "2026-09-14", "11131.28"), ("3m", "2026-07-14", "12661.93")):
            with self.subTest(window=key):
                self.assertEqual(m[key]["status"], "verified")
                self.assertEqual(m[key]["base_date"], base_date)
                self.assertEqual(m[key]["base_close"], float(official))
                independent = (Decimal("11684.38") / Decimal(official) - 1) * 100
                self.assertAlmostEqual(m[key]["return_pct"], float(independent), places=10)
                self.assertAlmostEqual(verified_price_return(m[key]), float(independent), places=10)
        self.assertAlmostEqual(m["1m"]["return_pct"], 4.968880488137928)
        self.assertAlmostEqual(m["3m"]["return_pct"], -7.720387018408736)

    def test_weekend_cutoff_uses_prior_observation_and_explicit_date(self):
        rows = [("2026-06-12", 100), ("2026-06-15", 95)]
        value = price_month_windows("2026-07-14", 110, rows, rows)["1m"]
        self.assertEqual(value["cutoff_date"], "2026-06-14")
        self.assertEqual(value["base_date"], "2026-06-12")
        self.assertEqual(value["cutoff_gap_days"], 2)
        self.assertAlmostEqual(value["return_pct"], 10)

    def test_missing_official_baseline_is_not_replaced_by_yahoo_or_an_earlier_date(self):
        value = price_month_windows("2026-10-14", 110, [("2026-09-14", 100)], [("2026-09-11", 99)])["1m"]
        self.assertEqual(value["status"], "unavailable")
        self.assertIn("Same-date Nasdaq", value["reason"])
        self.assertNotIn("return_pct", value)

    def test_cross_provider_conflict_blocks_only_the_affected_window(self):
        y = [("2026-09-14", 100), ("2026-07-14", 80)]
        n = [("2026-09-14", 100.2), ("2026-07-14", 80)]
        windows = price_month_windows("2026-10-14", 110, y, n)
        self.assertEqual(windows["1m"]["status"], "unavailable")
        self.assertEqual(windows["3m"]["status"], "verified")

    def test_zero_nonfinite_or_stale_baselines_do_not_get_filled(self):
        for baseline in (0, None, float("nan")):
            value = price_month_windows("2026-10-14", 110, [("2026-09-14", baseline)], [("2026-09-14", 100)])["1m"]
            self.assertEqual(value["status"], "unavailable")
        value = price_month_windows("2026-10-14", 110, [("2026-09-01", 100)], [("2026-09-01", 100)])["1m"]
        self.assertIn("gap", value["reason"])

    def test_conflicting_duplicate_source_rows_are_not_last_row_wins(self):
        rows = [("2026-09-14", 100), ("2026-09-14", 101)]
        windows = price_month_windows("2026-10-14", 110, rows, rows)
        self.assertTrue(all(w["status"] == "unavailable" for w in windows.values()))

    def test_saved_return_and_date_tampering_cannot_change_the_direction(self):
        original = enriched_snapshot()["Nasdaq SOX|sox"]["metrics"]["month_windows"]["1m"]
        for key, value in (("return_pct", -20), ("base_close", 99), ("cutoff_date", "2026-09-15"), ("end_date", "2026-10-15")):
            item = copy.deepcopy(original)
            item[key] = value
            self.assertIsNone(verified_price_return(item, "2026-10-14", 11684.38))


class CalendarPositionTests(unittest.TestCase):
    def test_actual_nq_month_and_quarter_use_weekly_dates_before_calendar_cutoffs(self):
        windows = enriched_snapshot()["CFTC|cot"]["history_3y"]["month_windows"]
        self.assertEqual(windows["1m"]["cutoff_date"], "2026-09-06")
        self.assertEqual(windows["1m"]["base_date"], "2026-09-01")
        self.assertEqual(windows["3m"]["base_date"], "2026-06-30")
        self.assertEqual(verified_position_change(windows["1m"], "leveraged_funds"), -5120)
        self.assertEqual(verified_position_change(windows["3m"], "leveraged_funds"), 49405)
        self.assertEqual(verified_position_change(windows["1m"], "asset_manager"), 1921)
        self.assertEqual(verified_position_change(windows["3m"], "asset_manager"), 6488)

    def test_one_calendar_month_is_not_the_existing_four_week_change(self):
        values = enriched_snapshot()
        hist = values["CFTC|cot"]["history_3y"]
        self.assertEqual(hist["leveraged_net_4w_change"], 12660)
        self.assertEqual(verified_position_change(hist["month_windows"]["1m"], "leveraged_funds"), -5120)

    def test_future_report_rows_do_not_change_current_report_windows(self):
        source = source_fixture()
        before = position_month_windows(source["nq_rows"], source["nq_end_date"])
        future = {**source["nq_rows"][0], "date": "2026-10-13", "lev_long": 999999}
        after = position_month_windows(source["nq_rows"] + [future], source["nq_end_date"])
        self.assertEqual(before, after)

    def test_same_date_current_positions_must_match_live_nq_inputs(self):
        source = source_fixture()
        current = copy.deepcopy(core_tests.snapshot()["CFTC|cot"]["nq_mini"])
        current["leveraged_short"] += 1
        with self.assertRaisesRegex(ValueError, "current/history mismatch"):
            position_month_windows(source["nq_rows"], source["nq_end_date"], current)

    def test_missing_or_stale_weekly_baseline_stays_unavailable(self):
        source = source_fixture()
        rows = [source["nq_rows"][0]]
        windows = position_month_windows(rows, source["nq_end_date"])
        self.assertTrue(all(w["status"] == "unavailable" for w in windows.values()))
        rows.append({**rows[0], "date": "2026-08-01"})
        value = position_month_windows(rows, source["nq_end_date"])["1m"]
        self.assertEqual(value["status"], "unavailable")

    def test_missing_asset_fields_do_not_turn_into_zero_or_erase_valid_hedge_positions(self):
        source = source_fixture()
        for row in source["nq_rows"]:
            row.pop("asset_long")
        value = position_month_windows(source["nq_rows"], source["nq_end_date"])["1m"]
        self.assertIsNone(verified_position_change(value, "asset_manager"))
        self.assertEqual(verified_position_change(value, "leveraged_funds"), -5120)

    def test_saved_net_change_and_population_cannot_be_mixed(self):
        value = enriched_snapshot()["CFTC|cot"]["history_3y"]["month_windows"]["1m"]
        item = copy.deepcopy(value)
        item["actors"]["leveraged_funds"]["net_change"] = 7044
        self.assertIsNone(verified_position_change(item, "leveraged_funds"))
        item = copy.deepcopy(value)
        item["cftc_code"] = "20974+"
        self.assertIsNone(verified_position_change(item, "leveraged_funds"))


class MultiHorizonPresentationTests(unittest.TestCase):
    def test_actual_summary_is_mixed_not_a_short_only_downtrend(self):
        values = enriched_snapshot()
        message = core_tests.render(values)
        self.assertIn("기간 종합: 반도체 혼재 · 1개월 상승, 단기·3개월 하락", message)
        self.assertIn("+4.97% · 상승", message)
        self.assertIn("-7.72% · 하락", message)
        self.assertIn("2026-09-14 → 2026-10-14", message)
        self.assertIn("2026-07-14 → 2026-10-14", message)
        self.assertIn("헤지펀드성 -5,120계약(순숏 확대)", message)
        self.assertIn("헤지펀드성 +49,405계약(순숏 축소)", message)
        self.assertLessEqual(len(message.strip()), 3800)

    def test_missing_months_prohibit_a_whole_period_verdict(self):
        message = core_tests.render()
        self.assertIn("기간 종합: 반도체 중기 방향 확인 대기", message)
        self.assertIn("1개월: <b>확인 대기</b>", message)
        self.assertIn("3개월: <b>확인 대기</b>", message)

    def test_all_up_all_down_and_multimonth_rebound_are_different(self):
        values = enriched_snapshot()
        sox = values["Nasdaq SOX|sox"]
        m = sox["metrics"]
        m["value"] = 110
        cases = [(-1, 120, 130, "단기·1개월·3개월 모두 하락"),
                 (1, 100, 90, "단기·1개월·3개월 모두 상승"),
                 (1, 120, 130, "1·3개월 하락 속 단기 반등"),
                 (-1, 100, 90, "1·3개월 상승 속 단기 하락")]
        for short, one_base, three_base, expected in cases:
            for days in (1, 3, 5):m[f"d{days}_pct"] = short
            rows = [("2026-09-14", one_base), ("2026-07-14", three_base)]
            m["month_windows"] = price_month_windows("2026-10-14", 110, rows, rows)
            self.assertIn(expected, presentation.horizon_overview(sox)[1])

    def test_invalid_current_close_cannot_use_old_verified_months(self):
        sox = enriched_snapshot()["Nasdaq SOX|sox"]
        sox["metrics"]["final_close_confirmed"] = False
        self.assertIn("확인 대기", presentation.horizon_overview(sox)[1])

    def test_new_monthly_snapshot_passes_existing_operating_gates_and_renders(self):
        values = enriched_snapshot()
        result = core_tests.OperatingIntegrationTests.run_operating_tail(self, values)
        self.assertTrue(result["gate"])
        self.assertEqual(result["alert"], core_tests.render(values))
        self.assertEqual(result["pending"]["values"], values)
