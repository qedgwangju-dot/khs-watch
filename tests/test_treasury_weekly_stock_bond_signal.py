"""Offline tests for weekly Nasdaq-100 versus Treasury risk-off regime."""
import datetime as dt
import unittest
from unittest.mock import Mock
from zoneinfo import ZoneInfo

import treasury_weekly_stock_bond_signal as w


CSV = (
    "observation_date,NASDAQ100\n"
    "2026-10-09,30883.15\n"
    "2026-10-12,30664.70\n"
    "2026-10-13,30569.48\n"
    "2026-10-14,29950.82\n"
    "2026-10-15,29935.59\n"
    "2026-10-16,29187.55\n"
)


def feed(rows):
    ns = "http://schemas.microsoft.com/ado/2007/08/dataservices"
    out = [
        "<feed xmlns='http://www.w3.org/2005/Atom' xmlns:d='"+ns+"'>"
    ]
    for d, rate in rows.items():
        out.append(
            f"<entry><content><d:NEW_DATE>{d}T00:00:00</d:NEW_DATE>"
            f"<d:BC_10YEAR>{rate}</d:BC_10YEAR></content></entry>"
        )
    out.append("</feed>")
    return "".join(out).encode()


class Client:
    def __init__(self, csv_data=CSV, yields=None):
        self.calls = []
        self.csv = csv_data
        self.yields = yields if yields is not None else {"2026-10-09": 5.24, "2026-10-16": 5.09}

    def get(self, url, **kwargs):
        self.calls.append((url, kwargs))
        response = Mock()
        response.raise_for_status = Mock()
        response.text = self.csv
        response.content = feed(self.yields)
        return response


class StockBondWeekTests(unittest.TestCase):
    def test_fred_csv_parses_nasdaq_closing_values(self):
        vals = w.parse_nasdaq_csv(CSV)
        self.assertEqual(vals["2026-10-16"], 29187.55)
        self.assertEqual(vals["2026-10-09"], 30883.15)

    def test_fred_legacy_date_column_supported(self):
        self.assertEqual(w.parse_nasdaq_csv(CSV.replace("observation_date", "DATE"))["2026-10-16"], 29187.55)

    def test_week_oct_16_is_a_haven_candidate_using_official_close(self):
        x = w.evaluate_week(
            w.parse_nasdaq_csv(CSV),
            {"2026-10-09": 5.24, "2026-10-16": 5.09},
            dt.date(2026,10,16),
        )
        self.assertEqual(x["category"], "안전자산 방어 신호")
        self.assertTrue(x["alert"])
        self.assertAlmostEqual(x["ndx_week_pct"], -5.4904, places=2)
        self.assertAlmostEqual(x["y10_week_bp"], -15.0)
        self.assertIn("종가 대 종가", x["reference_note"])

    def test_week_with_bond_selloff_is_opposite_warning(self):
        d=w.evaluate_week(w.parse_nasdaq_csv(CSV),{"2026-10-09":5.24,"2026-10-16":5.46},dt.date(2026,10,16))
        self.assertEqual(d["category"], "주식·국채 동반 약세 경보")

    def test_bad_equity_selloff_without_yield_hedge(self):
        d=w.evaluate_week(w.parse_nasdaq_csv(CSV),{"2026-10-09":5.24,"2026-10-16":5.19},dt.date(2026,10,16))
        self.assertEqual(d["category"], "기술주 급락·국채 완충 불충분")

    def test_no_5pct_stock_drop_no_alert(self):
        prices={"2026-10-09":30000,"2026-10-16":29800}
        x=w.evaluate_week(prices,{"2026-10-09":5.24,"2026-10-16":5.00},dt.date(2026,10,16))
        self.assertFalse(x["alert"])

    def test_missing_current_nasdaq_must_not_fallback_to_previous_close(self):
        with self.assertRaisesRegex(w.SourceMissing, "Nasdaq-100"):
            w.evaluate_week({"2026-10-09":30883.15,"2026-10-15":29935.59},
                            {"2026-10-09":5.24,"2026-10-16":5.09},dt.date(2026,10,16))

    def test_missing_previous_treasury_yield_must_not_impute(self):
        with self.assertRaisesRegex(w.SourceMissing, "10Y Treasury"):
            w.evaluate_week(w.parse_nasdaq_csv(CSV),{"2026-10-16":5.09},dt.date(2026,10,16))

    def test_csv_error_html_or_invalid_data_fail_closed(self):
        for payload in ("<html>error</html>","not,a,real,feed\n1,2,3,4\n"):
            with self.assertRaises(w.SourceMissing):
                w.parse_nasdaq_csv(payload)

    def test_friday_not_yet_closed_uses_previous_week(self):
        ts=dt.datetime(2026,10,16,15,30,tzinfo=ZoneInfo("America/New_York"))
        self.assertEqual(w.completed_friday(ts),dt.date(2026,10,9))
        self.assertEqual(w.completed_friday(ts.replace(hour=17)),dt.date(2026,10,16))

    def test_saturday_kst_uses_friday_us(self):
        ts=dt.datetime(2026,10,17,14,30,tzinfo=ZoneInfo("Asia/Seoul"))
        self.assertEqual(w.completed_friday(ts),dt.date(2026,10,16))

    def test_missing_friday_no_thursday_substitution(self):
        with self.assertRaisesRegex(w.SourceMissing, "Nasdaq-100"):
            w.evaluate_week({"2026-10-09":30,"2026-10-15":27},
                            {"2026-10-09":5.24,"2026-10-16":5.09},dt.date(2026,10,16))

    def test_client_fetch_uses_primary_official_sources_only(self):
        client=Client()
        ts=dt.datetime(2026,10,17,14,0,tzinfo=ZoneInfo("Asia/Seoul"))
        x=w.fetch_current_week(ts,client=client)
        self.assertEqual(x["end"],"2026-10-16")
        self.assertEqual(len(client.calls),2)
        self.assertTrue(client.calls[0][0].startswith("https://fred.stlouisfed.org/"))
        self.assertIn("daily_treasury_yield_curve",client.calls[1][0])
        self.assertIn("경보", w.report_text(x))
        self.assertIn("CFTC",w.report_text(x))


if __name__=="__main__":
    unittest.main()
