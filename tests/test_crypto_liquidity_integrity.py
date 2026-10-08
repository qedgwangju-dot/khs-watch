import unittest
from unittest.mock import patch

from scripts import crypto_liquidity_watch as watch


DAYS = [
    ("2026-09-24", 190.7),
    ("2026-09-25", 134.5),
    ("2026-09-28", 31.0),
    ("2026-09-29", 66.2),
    ("2026-09-30", -148.7),
    ("2026-10-01", 102.7),
    ("2026-10-02", 189.9),
    ("2026-10-05", -89.8),
    ("2026-10-06", 118.8),
    ("2026-10-07", -277.2),
]


def build_html(columns=12, latest_missing=1):
    tickers = list(watch.FUND_TICKERS)[:columns]
    rows = ["<tr><td>Date</td>" + "".join(f"<td>{ticker}</td>" for ticker in tickers) + "<td>Total</td></tr>"]
    for date, total in DAYS:
        import datetime as dt
        fmt = dt.date.fromisoformat(date).strftime("%d %b %Y")
        funds = [f"{total:.1f}"] + ["0.0"] * (columns - 1)
        if date == "2026-10-07" and latest_missing:
            for i in range(latest_missing):
                funds[-(i+1)] = "-"
        rows.append("<tr><td>" + fmt + "</td>" + "".join(f"<td>{value}</td>" for value in funds) + f"<td>{total:.1f}</td></tr>")
    return "<html><table>" + "".join(rows) + "</table></html>"


class CryptoLiquidityDataIntegrityTest(unittest.TestCase):
    def fetch_btc(self, html):
        with patch.object(watch, "fetch", return_value=html.encode("utf-8")):
            return watch.btc_etf_flow()

    def test_twelve_tickers_and_rolling_window_math(self):
        latest = self.fetch_btc(build_html())
        self.assertEqual(latest["date"], "2026-10-07")
        self.assertEqual(latest["total_usd_m"], -277.2)
        self.assertEqual(latest["status"], "partial")
        self.assertEqual(latest["reported_funds"], 11)
        self.assertEqual(latest["missing_tickers"], ["BTC"])
        self.assertEqual(latest["last5_usd_m"], 44.4)
        self.assertEqual(latest["prev5_usd_m"], 273.7)
        self.assertEqual(latest["five_day_change_usd_m"], -229.3)
        self.assertEqual(latest["five_day_change_pct"], -83.8)

    def test_layout_drift_rejected(self):
        with self.assertRaises(RuntimeError):
            self.fetch_btc(build_html(columns=11))

    def test_report_coverage_regression_rejected(self):
        old = self.fetch_btc(build_html())
        regressed = self.fetch_btc(build_html(latest_missing=8))
        self.assertIn("coverage regression", watch.reject_etf_source_regression(old, regressed))
        same = self.fetch_btc(build_html())
        self.assertIsNone(watch.reject_etf_source_regression(old, same))
        complete = self.fetch_btc(build_html(latest_missing=0))
        self.assertIsNone(watch.reject_etf_source_regression(old, complete))
        self.assertIn("regressed", watch.reject_etf_source_regression(complete, old))

    def test_stale_date_rejected(self):
        old = {"date": "2026-10-07", "reported_funds": 11, "status": "partial"}
        new = {"date": "2026-10-06", "reported_funds": 12, "status": "complete"}
        self.assertIn("stale trade date", watch.reject_etf_source_regression(old, new))

    def test_past_partial_history_not_duplicated(self):
        old = {
            "updated_at_kst": "2026-10-08T10:09:02+09:00",
            "btc_etf": self.fetch_btc(build_html()),
        }
        current = self.fetch_btc(build_html())
        after = watch.carry_partial_history(old, current, "2026-10-08T10:16:00+09:00")
        self.assertEqual(len(after["provisional_history"]), 1)
        self.assertEqual(after["provisional_history"][0]["coverage"], "11/12")


if __name__ == "__main__":
    unittest.main()
