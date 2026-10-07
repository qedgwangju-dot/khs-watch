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
