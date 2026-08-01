from __future__ import annotations

import datetime as dt
import pathlib
import sys
import unittest
from zoneinfo import ZoneInfo

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import yen_carry_alert as legacy  # noqa: E402
import yen_carry_market_data_v2 as market  # noqa: E402


def payload(points, *, timezone="America/New_York", chart_previous_close=1.0, previous_close=None):
    meta = {
        "exchangeTimezoneName": timezone,
        "chartPreviousClose": chart_previous_close,
    }
    if previous_close is not None:
        meta["regularMarketPreviousClose"] = previous_close
    return {
        "chart": {
            "result": [
                {
                    "meta": meta,
                    "timestamp": [item[0] for item in points],
                    "indicators": {"quote": [{"close": [item[1] for item in points]}]},
                }
            ],
            "error": None,
        }
    }


class AccurateMarketDataTests(unittest.TestCase):
    def epoch(self, year, month, day, hour, minute, zone):
        return dt.datetime(year, month, day, hour, minute, tzinfo=ZoneInfo(zone)).timestamp()

    def test_nasdaq_uses_previous_trading_session_not_five_day_baseline(self):
        zone = "America/New_York"
        points = [
            (self.epoch(2026, 7, 30, 16, 0, zone), 25122.17),
            (self.epoch(2026, 7, 31, 10, 0, zone), 25200.00),
            (self.epoch(2026, 7, 31, 16, 0, zone), 25373.85),
        ]
        quote = market.parse_payload(
            payload(points, timezone=zone, chart_previous_close=24975.82),
            legacy.SYMBOLS["nasdaq_cash"],
        )
        self.assertAlmostEqual(quote.price, 25373.85, places=2)
        self.assertAlmostEqual(quote.previous_close, 25122.17, places=2)
        self.assertAlmostEqual(quote.change_pct, 1.00183, places=4)

    def test_nikkei_uses_previous_trading_session(self):
        zone = "Asia/Tokyo"
        previous = 64362.02 / 1.04
        points = [
            (self.epoch(2026, 7, 30, 15, 0, zone), previous),
            (self.epoch(2026, 7, 31, 9, 0, zone), 63000.00),
            (self.epoch(2026, 7, 31, 15, 0, zone), 64362.02),
        ]
        quote = market.parse_payload(
            payload(points, timezone=zone, chart_previous_close=64931.19),
            legacy.SYMBOLS["nikkei_cash"],
        )
        self.assertAlmostEqual(quote.price, 64362.02, places=2)
        self.assertAlmostEqual(quote.change_pct, 4.0, places=6)

    def test_usdjpy_uses_rolling_24_hour_reference(self):
        start = dt.datetime(2026, 7, 30, 21, 0, tzinfo=dt.timezone.utc).timestamp()
        points = [
            (start, 160.00),
            (start + 43_200, 158.90),
            (start + 86_400, 157.40),
        ]
        quote = market.parse_payload(
            payload(points, timezone="UTC", chart_previous_close=163.61),
            legacy.SYMBOLS["usd_jpy"],
        )
        self.assertAlmostEqual(quote.price, 157.40, places=2)
        self.assertAlmostEqual(quote.previous_close, 160.00, places=2)
        self.assertAlmostEqual(quote.change_pct, -1.625, places=6)


if __name__ == "__main__":
    unittest.main()
