import datetime as dt
import unittest
from zoneinfo import ZoneInfo

from scripts import europe_sovereign_yield_watch as watch


class EuropeSovereignYieldWatchTests(unittest.TestCase):
    def test_parse_france_tec10(self):
        plain = """
        Indices Quotidiens TEC-n
        01/10/2026 02/10/2026 05/10/2026 06/10/2026 07/10/2026
        TEC1 3,3330 3,3660 3,3660 3,2510 3,2590
        TEC10 4,9030 4,8990 4,8840 4,7240 4,8340
        Indices Hebdomadaires
        """
        # Exercise the same core extraction logic used by fetch_france without a network call.
        daily = watch.re.split(r"Indices Hebdomadaires|Weekly", plain, maxsplit=1, flags=watch.re.I)[0]
        dates = []
        for x in watch.re.findall(r"\b(\d{2}/\d{2}/\d{4})\b", daily):
            if x not in dates:
                dates.append(x)
        m = watch.re.search(r"\bTEC10\b\s+((?:[0-9]+[,.][0-9]+\s+){1,10})", daily)
        vals = [float(x.replace(",", ".")) for x in watch.re.findall(r"[0-9]+[,.][0-9]+", m.group(1))]
        self.assertEqual(dates[-1], "07/10/2026")
        self.assertAlmostEqual(vals[-1], 4.8340)

    def test_parse_uk(self):
        text = "Date IUDMNPY 01 Oct 26 5.201 02 Oct 26 5.247 06 Oct 26 5.330"
        rows = watch.parse_uk(text, "https://example")
        self.assertEqual(rows[-1].date, "2026-10-06")
        self.assertAlmostEqual(rows[-1].value, 5.330)

    def test_parse_germany_semicolon_csv(self):
        text = "TIME_PERIOD;OBS_VALUE\n2026-10-05;3.450\n2026-10-06;3.497\n"
        rows = watch.parse_germany(text, "https://example")
        self.assertEqual(rows[-1].date, "2026-10-06")
        self.assertAlmostEqual(rows[-1].value, 3.497)

    def test_level_event_is_new_only_once(self):
        events = []
        active = {}
        state = {"active": {}}
        watch.mark_event(events, active, state, "fr10:above:4.75", True, "프랑스 경계")
        self.assertEqual(len(events), 1)
        events2 = []
        state2 = {"active": active}
        active2 = dict(active)
        watch.mark_event(events2, active2, state2, "fr10:above:4.75", True, "프랑스 경계")
        self.assertEqual(events2, [])

    def test_business_lag(self):
        now = dt.datetime(2026, 10, 8, 0, 35, tzinfo=ZoneInfo("Asia/Seoul"))
        obs = watch.Obs("uk10", "영국 10년", "2026-10-05", 5.2, "x")
        self.assertEqual(watch.business_lag_days(obs, now, watch.LONDON), 2)

    def test_parse_market_page(self):
        text = "The yield on Italy 10Y Bond Yield rose to 4.69% on October 7, 2026, marking a 0.15 percentage points increase from the previous session."
        rows = watch.parse_market_page(text, "it10", "이탈리아 10년 시장수익률", "https://example")
        self.assertEqual(rows[-1].date, "2026-10-07")
        self.assertAlmostEqual(rows[-1].value, 4.69)
        self.assertAlmostEqual(rows[-1].daily_bp, 15.0)

    def test_same_date_snapshot_is_not_yesterday(self):
        today = watch.Obs("uk_mkt", "영국 10년", "2026-10-08", 5.45, "x")
        state = {"history": {"uk_mkt": [
            {"date": "2026-10-07", "value": 5.44},
            {"date": "2026-10-08", "value": 5.40},
        ]}}
        old = watch.previous_trading_observation(today, [today], state)
        self.assertEqual(old.date, "2026-10-07")
        self.assertAlmostEqual(old.value, 5.44)
        only_same_day = {"history": {"uk_mkt": [{"date": "2026-10-08", "value": 5.40}]}}
        self.assertIsNone(watch.previous_trading_observation(today, [today], only_same_day))

    def test_intraday_revision_replaces_history_but_not_previous_close(self):
        cur = watch.Obs("it10", "이탈리아", "2026-10-08", 4.60, "x")
        state = {"history": {"it10": [
            {"date": "2026-10-07", "value": 4.64},
            {"date": "2026-10-08", "value": 4.66},
        ]}}
        self.assertEqual(watch.merge_daily_history(state, "it10", cur), [
            {"date": "2026-10-07", "value": 4.64},
            {"date": "2026-10-08", "value": 4.60},
        ])

    def test_current_market_quote_daily_move_must_match_same_sentence(self):
        text = (
            "The yield on United Kingdom 10Y Bond Yield rose to 5.46% on "
            "October 8, 2026, marking a 0.02 percentage points increase "
            "from the previous session. Other news marking a 0.80 percentage "
            "points decrease from the previous session."
        )
        row = watch.parse_market_page(text, "uk_mkt", "영국 10년", "https://example")[0]
        self.assertAlmostEqual(row.value, 5.46)
        self.assertAlmostEqual(row.daily_bp, 2.0)
        no_move = (
            "The yield on United Kingdom 10Y Bond Yield rose to 5.46% on "
            "October 8, 2026. Other news marking a 0.80 percentage points "
            "decrease from the previous session."
        )
        row = watch.parse_market_page(no_move, "uk_mkt", "영국 10년", "https://example")[0]
        self.assertIsNone(row.daily_bp)

    def test_spread_requires_same_vendor_and_source_date(self):
        base = {
            "fr_mkt": watch.Obs("fr_mkt", "프랑스", "2026-10-08", 4.87, "tradingeconomics.com"),
            "de_mkt": watch.Obs("de_mkt", "독일", "2026-10-08", 3.48, "tradingeconomics.com"),
        }
        self.assertAlmostEqual(watch.comparable_market_spread(base, []), 139.0)
        base["de_mkt"].date = "2026-10-07"
        self.assertIsNone(watch.comparable_market_spread(base, []))
        base["de_mkt"].date = "2026-10-08"
        self.assertIsNone(watch.comparable_market_spread(base, ["fr_mkt"]))

    def test_country_coverage_excludes_stale_and_accepts_market_fallback(self):
        latest = {
            "fr10": watch.Obs("fr10", "프랑스", "2026-10-08", 4.898, "official"),
            "de_mkt": watch.Obs("de_mkt", "독일", "2026-10-08", 3.48, "market"),
            "uk10": watch.Obs("uk10", "영국", "2026-10-06", 5.33, "official"),
            "uk_mkt": watch.Obs("uk_mkt", "영국", "2026-10-08", 5.46, "market"),
        }
        coverage = watch.coverage_by_country(latest, ["uk10"])
        self.assertEqual(coverage, {"프랑스": True, "독일": True,
                                    "이탈리아": False, "영국": True})
        coverage_bad = watch.coverage_by_country(latest, ["uk10", "de_mkt", "uk_mkt"])
        self.assertEqual(sum(coverage_bad.values()), 1)

    def test_future_dated_market_data_does_not_trigger(self):
        now = dt.datetime(2026, 10, 8, 23, 54, tzinfo=ZoneInfo("Asia/Seoul"))
        row = watch.Obs("fr10", "프랑스", "2026-10-09", 5.00, "x")
        self.assertEqual(watch.business_lag_days(row, now, watch.PARIS), 999)

    def test_official_france_change_is_exact(self):
        self.assertAlmostEqual(watch.bp(4.898, 4.834), 6.4)

    def test_france_extra_5_10_hysteresis_does_not_chatter(self):
        original = {"active": {}}
        active = {}
        events = []
        watch.mark_hysteresis_event(events, active, original, "fr10:stress:5.1",
                                   5.126, 5.10, 5.03, "프랑스 공식 TEC10", "%")
        self.assertEqual(len(events), 1)
        self.assertEqual(events[0]["type"], "trigger")
        next_state = {"active": dict(active)}
        events_next = []
        watch.mark_hysteresis_event(events_next, dict(active), next_state,
                                   "fr10:stress:5.1", 5.06, 5.10, 5.03, "프랑스 공식 TEC10", "%")
        self.assertEqual(events_next, [])
        clear_events, clear_active = [], dict(active)
        watch.mark_hysteresis_event(clear_events, clear_active, next_state,
                                   "fr10:stress:5.1", 5.02, 5.10, 5.03, "프랑스 공식 TEC10", "%")
        self.assertEqual(clear_events[0]["type"], "clear")
        self.assertFalse(clear_active["fr10:stress:5.1"])

    def test_170bp_spread_first_crossing_and_next_marker(self):
        events, active, state = [], {}, {"active": {}}
        watch.mark_hysteresis_event(events, active, state, "spread:170",
                                   171.0, 170.0, 160.0, "프랑스-독일 금리차", "bp")
        self.assertEqual(events[0]["type"], "trigger")
        self.assertEqual(watch.next_spread_marker(171.0), "175bp")
        self.assertEqual(watch.next_spread_marker(173.58), "175bp")
        self.assertEqual(watch.next_spread_marker(175.01), "200bp")
        self.assertEqual(watch.next_spread_marker(None),
                         "동일 기준일 시장금리차 확인 불가")
        second = []
        watch.mark_hysteresis_event(second, dict(active), {"active": active},
                                   "spread:170", 169, 170, 160, "프랑스-독일 금리차", "bp")
        self.assertEqual(second, [])

    def test_italy_spread_requires_same_day(self):
        o = {
            "de_mkt": watch.Obs("de_mkt", "독일 10년", "2026-10-22", 3.35, "m"),
            "it10": watch.Obs("it10", "이탈리아 10년", "2026-10-22", 4.62, "m"),
        }
        _, body, _ = watch.build_alert(o, {"it10_day_bp": 3.0}, None, [], [], [],
                                      dt.datetime(2026, 10, 22, 23, tzinfo=ZoneInfo("Asia/Seoul")))
        self.assertIn("이탈리아-독일 10년 시장금리차 127.0bp", body)
        o["de_mkt"].date = "2026-10-21"
        _, body, _ = watch.build_alert(o, {}, None, [], [], [],
                                      dt.datetime(2026, 10, 22, 23, tzinfo=ZoneInfo("Asia/Seoul")))
        self.assertNotIn("이탈리아-독일 10년 시장금리차", body)

    def test_alert_explains_policy_vs_market_rate(self):
        latest = {
            "fr10": watch.Obs("fr10", "프랑스 10년", "2026-10-07", 4.834, "fr"),
            "de10": watch.Obs("de10", "독일 10년", "2026-10-07", 3.497, "de"),
        }
        title, body, detail = watch.build_alert(
            latest,
            {"fr10_day_bp": 11.0, "de10_day_bp": 2.0},
            133.7,
            [{"type": "trigger", "key": "fr", "summary": "프랑스 10년 4.75% 이상"}],
            [],
            [],
            dt.datetime(2026, 10, 7, 23, 0, tzinfo=ZoneInfo("Asia/Seoul")),
        )
        self.assertIn("ECB 정책금리와 별개", body)
        self.assertIn("동일 시장자료", body)
        self.assertIn("프랑스 TEC10 5.00%", body)
        self.assertIn("유럽 국채금리 경보", title)
        self.assertTrue(detail["signature"])


if __name__ == "__main__":
    unittest.main()
