import unittest
from unittest.mock import patch

from scripts import crypto_liquidity_watch as watch
from scripts import crypto_alert_format as fmt


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

    def test_unreported_ibit_prevents_premature_overall_verdict(self):
        state = {
            "rates": {
                "date": "2026-10-07",
                "daily_10y_bp": 1.0,
                "daily_30y_bp": 3.0,
            },
            "btc_etf": {
                "date": "2026-10-07",
                "total_usd_m": -277.2,
                "status": "partial",
                "reported_funds": 11,
                "missing_funds": 1,
                "missing_tickers": ["IBIT"],
                "last5_usd_m": 44.4,
                "prev5_usd_m": 273.7,
            },
        }
        verdict, reason = fmt.compact_judgement(state)
        self.assertIn("판정 보류", verdict)
        self.assertIn("IBIT 미보고", reason)
        self.assertIn("-277.2백만달러", reason)
        state["btc_etf"]["missing_tickers"] = ["BTC"]
        verdict, _ = fmt.compact_judgement(state)
        self.assertIn("불리", verdict)
        self.assertIn("잠정", verdict)
        state["btc_etf"]["status"] = "complete"
        state["btc_etf"]["missing_tickers"] = []
        verdict, _ = fmt.compact_judgement(state)
        self.assertEqual(verdict, "불리")

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

    def test_malformed_all_data_html_flattens_to_exact_records(self):
        flat = build_html().replace("</tr><tr>", "")
        result = self.fetch_btc(flat)
        self.assertEqual(result["date"], "2026-10-07")
        self.assertEqual(result["total_usd_m"], -277.2)
        self.assertEqual(result["last5_usd_m"], 44.4)

    def test_calendar_month_boundaries_and_flow_reversals(self):
        import datetime as dt
        self.assertEqual(watch.months_before(dt.date(2026,3,31),1),dt.date(2026,2,28))
        self.assertEqual(watch.flow_direction(241.1,-701.3),"순유입→순유출 전환")
        self.assertEqual(watch.flow_direction(-30.0,20.0),"순유출→순유입 전환")

    def test_true_one_and_three_calendar_month_windows(self):
        import datetime as dt
        start, end = dt.date(2026,4,6), dt.date(2026,10,9)
        rows, day = [], start
        while day <= end:
            if day in (watch.expected_nyse_dates(day, day) or []):
                rows.append({"date":day, "total":10.0, "status":"complete",
                             "total_validated":True})
            day += dt.timedelta(days=1)
        windows = watch.calendar_windows(rows,end)
        one,three=windows["1m"],windows["3m"]
        self.assertEqual((one["start"],one["end"]),("2026-09-10","2026-10-09"))
        self.assertEqual((one["prev_start"],one["prev_end"]),("2026-08-10","2026-09-09"))
        self.assertEqual((three["start"],three["end"]),("2026-07-10","2026-10-09"))
        self.assertEqual((three["prev_start"],three["prev_end"]),("2026-04-10","2026-07-09"))
        self.assertTrue(one["valid"] and three["valid"])
        self.assertEqual(one["value_usd_m"],one["trading_days"] * 10)
        self.assertEqual(three["value_usd_m"],three["trading_days"] * 10)
        rows[-1]["status"]="partial"
        revised=watch.calendar_windows(rows,end)
        self.assertEqual(revised["1m"]["status"],"잠정")
        self.assertEqual(revised["3m"]["status"],"잠정")
        self.assertEqual(revised["1m"]["partial_days"],1)
        self.assertEqual(revised["3m"]["partial_days"],1)

    def test_truncated_history_cannot_invent_one_three_month_totals(self):
        import datetime as dt
        rows=[{"date":dt.date.fromisoformat(d),"total":v,"total_validated":True,
               "status":"complete"} for d,v in DAYS]
        periods=watch.calendar_windows(rows,dt.date(2026,10,7))
        for horizon in ("1m","3m"):
            self.assertFalse(periods[horizon]["valid"])
            self.assertIsNone(periods[horizon]["value_usd_m"])

    def test_one_missing_trading_session_invalidates_months(self):
        import datetime as dt
        day, end = dt.date(2026, 4, 10), dt.date(2026, 10, 9)
        dates = watch.expected_nyse_dates(day, end)
        self.assertIsNotNone(dates)
        self.assertEqual(len(watch.expected_nyse_dates(dt.date(2026, 7, 10), end)), 65)
        self.assertEqual(len(watch.expected_nyse_dates(dt.date(2026, 4, 10), dt.date(2026, 7, 9))), 62)
        self.assertNotIn(dt.date(2026, 7, 3), dates)
        self.assertNotIn(dt.date(2026, 9, 7), dates)
        rows = [
            {"date": d, "total": 2.0, "total_validated": True, "status": "complete"}
            for d in dates
        ]
        clean = watch.calendar_windows(rows, end)
        self.assertTrue(clean["1m"]["valid"] and clean["3m"]["valid"])
        rows = [r for r in rows if r["date"] != dt.date(2026, 9, 21)]
        missing = watch.calendar_windows(rows, end)
        self.assertFalse(missing["1m"]["valid"])
        self.assertFalse(missing["3m"]["valid"])
        self.assertIn("2026-09-21", missing["1m"]["missing_trading_dates"])
        self.assertIsNone(missing["1m"]["value_usd_m"])
        self.assertIsNone(missing["3m"]["value_usd_m"])

    def test_missing_market_holiday_calendar_fails_closed(self):
        import datetime as dt
        self.assertIsNone(watch.expected_nyse_dates(
            dt.date(2029, 1, 1), dt.date(2029, 1, 31)
        ))
        data = watch.calendar_period([], dt.date(2029, 1, 1), dt.date(2029, 1, 31), 12)
        self.assertFalse(data["valid"])
        self.assertIn("공식 달력", data["validation_issue"])

    def test_month_window_presentation_has_rolling_dates_and_average(self):
        state = {
            "status": "complete",
            "last5_usd_m": -678.9,
            "windows": {
                "1m": {
                    "valid": True, "start": "2026-09-10", "end": "2026-10-09",
                    "trading_days": 22, "value_usd_m": 1658.2,
                    "prev_value_usd_m": 3277.0, "change_usd_m": -1618.8,
                    "direction": "순유입 둔화", "status": "집계완료(수정가능)",
                },
                "3m": {
                    "valid": True, "start": "2026-07-10", "end": "2026-10-09",
                    "trading_days": 65, "value_usd_m": 5938.8,
                    "prev_value_usd_m": -5271.3, "change_usd_m": 11210.1,
                    "avg_usd_m_per_session": 91.4, "prev_avg_usd_m_per_session": -85.0,
                    "direction": "순유출→순유입 전환", "partial_days": 2,
                    "prev_partial_days": 0, "partial_dates": ["2026-07-27","2026-08-07"],
                    "status": "잠정",
                },
            },
        }
        rows = fmt.calendar_window_reading(state, "3m", 1339.2)
        self.assertTrue(any("거래일평균" in row for row in rows))
        self.assertTrue(any("미보고일 최근 2/직전 0" in row for row in rows))
        note = fmt.horizon_reading(state)
        self.assertIn("최근5 순유출", note)
        self.assertIn("1개월 순유입", note)
        self.assertIn("3개월 순유입", note)

    def test_middle_gap_blocks_three_month_only(self):
        import datetime as dt
        day,end=dt.date(2026,4,10),dt.date(2026,10,9)
        rows=[]
        while day<=end:
            if day in (watch.expected_nyse_dates(day, day) or []) and not (dt.date(2026,8,10)<=day<=dt.date(2026,8,24)):
                rows.append({"date":day,"total":5.0,"total_validated":True,
                             "status":"complete"})
            day+=dt.timedelta(days=1)
        periods=watch.calendar_windows(rows,end)
        self.assertFalse(periods["1m"]["valid"])  # previous 1M also includes the source gap
        self.assertTrue(watch.calendar_period(
            rows, dt.date(2026, 9, 10), end, 12
        )["valid"])  # current 1M alone has real observations
        self.assertFalse(periods["3m"]["valid"])

    def test_full_history_upgrades_incomplete_live_snapshot(self):
        import datetime as dt
        end=dt.date(2026,10,9)
        day=dt.date(2026,4,6)
        values=[]
        while day<=end:
            if day in (watch.expected_nyse_dates(day, day) or []):
                values.append((day,21.1 if day==end else 10.0))
            day+=dt.timedelta(days=1)

        def page(data,partial_last=False):
            lines=['<tr><th>Date</th>'+''.join(f'<th>{v}</th>' for v in watch.FUND_TICKERS)+'<th>Total</th></tr>']
            for date,value in data:
                cells=[str(value)]+["0.0"]*11
                if partial_last and date==end:
                    cells[0]="-"
                    cells[1]="-1.3"
                    value=-1.3
                lines.append('<tr><td>'+date.strftime("%d %b %Y")+'</td>'+
                             ''.join(f'<td>{v}</td>' for v in cells)+
                             f'<td>{value:.1f}</td></tr>')
            return ("<table>"+''.join(lines)+"</table>").encode()
        live=page(values[-15:],partial_last=True)
        historical=page(values)
        def fake_fetch(url,timeout=35):
            return historical if url==watch.FARSIDE_BTC_HISTORY_URL else live
        with patch.object(watch,"fetch",side_effect=fake_fetch):
            outcome=watch.btc_etf_flow()
        self.assertEqual(outcome["date"],"2026-10-09")
        self.assertEqual(outcome["total_usd_m"],21.1)
        self.assertEqual(outcome["reported_funds"],12)
        self.assertEqual(outcome["status"],"complete")
        self.assertTrue(outcome["windows"]["1m"]["valid"])
        self.assertTrue(outcome["windows"]["3m"]["valid"])
        self.assertEqual(outcome["windows"]["1m"]["start"],"2026-09-10")
        self.assertEqual(outcome["windows"]["3m"]["start"],"2026-07-10")
        self.assertEqual(outcome["history_row_count"],len(values))

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
        self.assertIn("coverage regression", watch.reject_etf_source_regression(complete, old))

    def test_zero_only_partial_placeholder_does_not_shift_rolling_window(self):
        extra = """<tr><td>08 Oct 2026</td><td>0.0</td><td>0.0</td>"""
        extra += "<td>-</td>" * 10 + "<td>0.0</td></tr>"
        html = build_html().replace("</table>", extra + "</table>")
        parsed = self.fetch_btc(html)
        self.assertEqual(parsed["date"], "2026-10-07")
        self.assertEqual(parsed["pending_date"], "2026-10-08")
        self.assertEqual(parsed["source_latest_status"], "pending")
        self.assertEqual(parsed["last5_usd_m"], 44.4)

    def test_full_zero_day_is_not_placeholder(self):
        zero_cells = "<td>0.0</td>" * 12
        extra = f"<tr><td>08 Oct 2026</td>{zero_cells}<td>0.0</td></tr>"
        parsed = self.fetch_btc(build_html().replace("</table>", extra + "</table>"))
        self.assertEqual(parsed["date"], "2026-10-08")
        self.assertEqual(parsed["status"], "complete")
        self.assertEqual(parsed["reported_funds"], 12)
        self.assertEqual(parsed["total_usd_m"], 0.0)

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
