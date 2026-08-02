import datetime as dt
import importlib.util
import pathlib
import sys
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "iran_hormuz_market_turn_alert.py"
SPEC = importlib.util.spec_from_file_location("iran_hormuz_market_turn_alert", SCRIPT)
MODULE = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
sys.modules[SPEC.name] = MODULE
SPEC.loader.exec_module(MODULE)


class IranHormuzMarketTurnTests(unittest.TestCase):
    def test_final_ceasefire_is_classified(self):
        title = "US and Iran agree to ceasefire agreement, officials say - Reuters"
        self.assertEqual(MODULE.classify_event(title), "ceasefire")

    def test_ceasefire_hopes_are_rejected(self):
        title = "Markets rally on Iran ceasefire hopes - Reuters"
        self.assertIsNone(MODULE.classify_event(title))

    def test_temporary_attack_pause_is_rejected(self):
        title = "US and Iran pause strikes in hope of quick deal - Reuters"
        self.assertIsNone(MODULE.classify_event(title))

    def test_hormuz_normalization_is_classified(self):
        title = "Shipping resumes through the Strait of Hormuz as traffic returns to normal - Reuters"
        self.assertEqual(MODULE.classify_event(title), "hormuz_normalization")

    def test_event_needs_two_unique_sources(self):
        now = dt.datetime(2026, 8, 2, 12, 0, tzinfo=dt.timezone.utc)
        rows = [
            MODULE.NewsItem("US and Iran agree to ceasefire agreement", "Reuters", "a", now.isoformat(), now.timestamp(), "ceasefire"),
            MODULE.NewsItem("US and Iran agree to ceasefire agreement", "Reuters", "b", now.isoformat(), now.timestamp(), "ceasefire"),
        ]
        self.assertIsNone(MODULE.confirm_event(rows))
        rows.append(MODULE.NewsItem("Iran ceasefire agreement takes effect", "Associated Press", "c", now.isoformat(), now.timestamp(), "ceasefire"))
        result = MODULE.confirm_event(rows)
        self.assertIsNotNone(result)
        assert result is not None
        self.assertEqual(result[0], "ceasefire")
        self.assertEqual(len(result[1]), 2)

    def test_market_requires_both_yield_and_dollar_down(self):
        now = dt.datetime(2026, 8, 2, 12, 0, tzinfo=dt.timezone.utc).timestamp()
        down_yield = MODULE.Quote("^UST2Y", "미국 2년물 국채금리", "%", 4.20, 4.25, -0.05, -1.176, "", now)
        down_dxy = MODULE.Quote("DX-Y.NYB", "달러인덱스", "", 99.50, 100.00, -0.50, -0.50, "", now)
        up_dxy = MODULE.Quote("DX-Y.NYB", "달러인덱스", "", 100.20, 100.00, 0.20, 0.20, "", now)
        self.assertTrue(MODULE.market_confirms(down_yield, down_dxy))
        self.assertFalse(MODULE.market_confirms(down_yield, up_dxy))

    def test_alert_body_contains_required_market_values(self):
        current = dt.datetime(2026, 8, 2, 12, 0, tzinfo=dt.timezone.utc)
        news = [
            MODULE.NewsItem("US and Iran agree to ceasefire agreement", "Reuters", "a", current.isoformat(), current.timestamp(), "ceasefire"),
            MODULE.NewsItem("Iran ceasefire agreement takes effect", "Associated Press", "b", current.isoformat(), current.timestamp(), "ceasefire"),
        ]
        us2y = MODULE.Quote("^UST2Y", "미국 2년물 국채금리", "%", 4.20, 4.25, -0.05, -1.176, "", current.timestamp())
        dxy = MODULE.Quote("DX-Y.NYB", "달러인덱스", "", 99.50, 100.00, -0.50, -0.50, "", current.timestamp())
        oil = MODULE.Quote("CL=F", "WTI", "달러/배럴", 80.00, 85.00, -5.00, -5.882, "", current.timestamp())
        body = MODULE.build_alert_body("ceasefire", news, us2y, dxy, oil, current)
        self.assertIn("미국 2년물 국채금리: 4.200%", body)
        self.assertIn("달러인덱스: 99.50", body)
        self.assertIn("WTI: $80.00/배럴", body)
        self.assertIn("실패 경로", body)


if __name__ == "__main__":
    unittest.main()
