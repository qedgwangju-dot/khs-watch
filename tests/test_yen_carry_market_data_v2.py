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


def payload(
    points,
    *,
    timezone="America/New_York",
    chart_previous_close=1.0,
    previous_close=None,
    regular_price=None,
    regular_time=None,
):
    meta = {
        "exchangeTimezoneName": timezone,
        "chartPreviousClose": chart_previous_close,
    }
    if previous_close is not None:
        meta["regularMarketPreviousClose"] = previous_close
    if regular_price is not None:
        meta["regularMarketPrice"] = regular_price
    if regular_time is not None:
        meta["regularMarketTime"] = regular_time
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

    def test_nasdaq_uses_official_close_and_previous_trading_close(self):
        zone = "America/New_York"
        previous = 25122.17
        official = 25373.85
        official_time = self.epoch(2026, 7, 31, 16, 0, zone)
        points = [
            (self.epoch(2026, 7, 30, 16, 0, zone), previous),
            (self.epoch(2026, 7, 31, 10, 0, zone), 25200.00),
            (self.epoch(2026, 7, 31, 15, 55, zone), 25360.00),
        ]
        quote = market.parse_payload(
            payload(
                points,
                timezone=zone,
                chart_previous_close=24975.82,
                previous_close=previous,
                regular_price=official,
                regular_time=official_time,
            ),
            legacy.SYMBOLS["nasdaq_cash"],
        )
        self.assertAlmostEqual(quote.price, official, places=2)
        self.assertAlmostEqual(quote.previous_close, previous, places=2)
        self.assertAlmostEqual(quote.change_pct, 1.00183, places=4)
        self.assertEqual(quote.timestamp_epoch, official_time)

    def test_nikkei_prefers_official_close_over_incomplete_final_bar(self):
        zone = "Asia/Tokyo"
        official = 64362.02
        previous = official / 1.04
        official_time = self.epoch(2026, 7, 31, 15, 30, zone)
        points = [
            (self.epoch(2026, 7, 30, 15, 30, zone), previous),
            (self.epoch(2026, 7, 31, 9, 0, zone), 63000.00),
            (self.epoch(2026, 7, 31, 15, 25, zone), 64299.39),
        ]
        quote = market.parse_payload(
            payload(
                points,
                timezone=zone,
                chart_previous_close=64931.19,
                previous_close=previous,
                regular_price=official,
                regular_time=official_time,
            ),
            legacy.SYMBOLS["nikkei_cash"],
        )
        self.assertAlmostEqual(quote.price, official, places=2)
        self.assertAlmostEqual(quote.change_pct, 4.0, places=6)
        self.assertEqual(quote.timestamp_epoch, official_time)

    def test_cash_falls_back_to_grouped_sessions_without_official_meta(self):
        zone = "America/New_York"
        points = [
            (self.epoch(2026, 7, 30, 16, 0, zone), 100.0),
            (self.epoch(2026, 7, 31, 16, 0, zone), 101.0),
        ]
        quote = market.parse_payload(
            payload(points, timezone=zone, chart_previous_close=95.0),
            legacy.SYMBOLS["nasdaq_cash"],
        )
        self.assertAlmostEqual(quote.price, 101.0)
        self.assertAlmostEqual(quote.previous_close, 100.0)
        self.assertAlmostEqual(quote.change_pct, 1.0)

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
