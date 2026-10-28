import unittest
from unittest.mock import patch
import datetime as dt
import contextlib
import copy
import io
import json
import pathlib
import tempfile

from scripts import crypto_liquidity_watch as watch
from scripts import crypto_alert_format as fmt
from scripts import crypto_alert_krw as krw


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

    def test_operational_failures_and_schedule_gap_are_visible_once(self):
        old = {"updated_at_kst": "2026-10-13T10:00:00+09:00", "errors": []}
        failed = {"updated_at_kst": "2026-10-13T10:16:00+09:00", "errors": ["btc_etf: timeout"]}
        first = watch.operational_triggers(old, failed, failed["updated_at_kst"])
        self.assertEqual(first, ["원천자료 조회 이상: BTC ETF"])
        repeated = watch.operational_triggers(failed, failed, "2026-10-13T10:31:00+09:00")
        self.assertEqual(repeated, [])
        recovered = {"errors": []}
        self.assertEqual(
            watch.operational_triggers(failed, recovered, "2026-10-13T10:31:00+09:00"),
            ["원천자료 조회 복구: BTC ETF"],
        )
        gap = watch.operational_triggers(old, old, "2026-10-13T11:00:00+09:00")
        self.assertEqual(len(gap), 1)
        self.assertIn("60분 (설정 15분 간격)", gap[0])

    def test_core_source_error_blocks_fresh_market_verdict(self):
        state = {
            "rates": {"date": "2026-10-12", "daily_10y_bp": 3.0, "daily_30y_bp": 4.0},
            "btc_etf": {"date": "2026-10-12", "total_usd_m": -65.4, "status": "complete"},
            "errors": ["btc_etf: Farside timeout; prior validated snapshot retained"],
        }
        verdict, reason = fmt.compact_judgement(state)
        self.assertEqual(verdict, "판정 보류")
        self.assertIn("BTC ETF 조회·검증 이상", reason)

    def test_ecos_failure_does_not_substitute_another_fx_series(self):
        with patch.object(krw, "ecos_usdkrw", return_value=None):
            with self.assertRaisesRegex(RuntimeError, "한국은행 ECOS"):
                krw.get_usdkrw(dt.date(2026, 10, 12))

    def test_fx_failure_survives_converter_and_final_formatter(self):
        state = {
            "btc_etf": {"date": "2026-10-12", "total_usd_m": -65.4, "status": "complete"},
            "rates": {"date": "2026-10-09", "10y": 5.24, "30y": 5.60},
            "errors": [],
        }
        raw = """[크립토 유동성 변화 감지]
조회시각(KST): 2026-10-13T16:06:25+09:00
• BTC 현물 ETF 새 일간 자금흐름(현재 전체 집계): -65.4백만달러
미 국채 — 미 재무부 공식 수익률곡선 기준일 2026-10-09
공식·데이터 원천:
• BTC 현물 ETF: <a href="https://farside.co.uk/btc/">원문</a>
"""
        with tempfile.TemporaryDirectory() as tmp:
            alert_path = pathlib.Path(tmp) / "alert.txt"
            state_path = pathlib.Path(tmp) / "pending.json"
            alert_path.write_text(raw, encoding="utf-8")
            state_path.write_text(json.dumps(state), encoding="utf-8")
            with (
                patch.object(krw, "ALERT_PATH", alert_path),
                patch.object(krw, "STATE_PATH", state_path),
                patch.object(krw, "ecos_usdkrw", return_value=None),
                patch.object(fmt, "ALERT_PATH", alert_path),
                patch.object(fmt, "PENDING_STATE_PATH", state_path),
            ):
                with contextlib.redirect_stdout(io.StringIO()):
                    krw.main()
                fmt.main()
            final = alert_path.read_text(encoding="utf-8")
        self.assertIn("원화 환산 보류", final)
        self.assertIn("-65.4백만달러", final)
        self.assertNotIn("약 -", final)

    def test_final_alert_exposes_fx_failure_and_source_warning(self):
        state = {
            "rates": {"date": "2026-10-12", "10y": 5.24, "30y": 5.60},
            "btc_etf": {"date": "2026-10-12", "total_usd_m": -65.4, "status": "complete"},
            "errors": ["btc_etf: Farside timeout"],
        }
        raw = """[크립토 유동성 변화 감지]
조회시각(KST): 2026-10-13T16:06:25+09:00
• 원천자료 조회 이상: BTC ETF
미 국채 — 미 재무부 공식 수익률곡선 기준일 2026-10-12
원화 환산 보류: 한국은행 ECOS 매매기준율 확인 실패
공식·데이터 원천:
• BTC 현물 ETF: <a href="https://farside.co.uk/btc/">원문</a>
"""
        with patch.object(fmt, "load_pending_state", return_value=state):
            alert = fmt.format_alert(raw)
        self.assertIn("<b>원천자료 조회 이상</b> · BTC ETF", alert)
        self.assertIn("관련 수치는 이번 실행에서 재확인되지 않음", alert)
        self.assertIn("판정 · 판정 보류", alert)
        self.assertIn("원화 환산 보류", alert)
        self.assertNotIn("약 -", alert)
        self.assertIn("<code>조회 2026-10-13T16:06:25+09:00</code>", alert)

        fallback = raw.replace(
            "원화 환산 보류: 한국은행 ECOS 매매기준율 확인 실패",
            "원화 환산 기준: 1달러=1,338.00원 | 기준일 2026-10-12 | ECB via Frankfurter 일일 기준환율 | 교차검증: 접근 불가",
        ).replace(
            "공식·데이터 원천:",
            "공식·데이터 원천:\n• 원/달러 환율: <a href=\"https://api.frankfurter.dev/v2/rates\">원문</a>",
        )
        with patch.object(fmt, "load_pending_state", return_value=state):
            legacy_alert = fmt.format_alert(fallback)
        self.assertIn(">대체 환율 원문</a>", legacy_alert)
        self.assertNotIn(">ECOS</a>", legacy_alert)

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
        self.assertTrue(any("일부 종목 미보고 거래일 최근 2/직전 0" in row for row in rows))
        note = fmt.horizon_reading(state)
        self.assertIn("최근5 순유출", note)
        self.assertIn("1개월 순유입", note)
        self.assertIn("3개월 순유입", note)

    def test_three_month_averages_convert_both_periods(self):
        state = {"windows": {"3m": {
            "valid": True, "start": "2026-07-13", "end": "2026-10-12",
            "trading_days": 65, "value_usd_m": 5783.0,
            "prev_value_usd_m": -5437.6, "change_usd_m": 11220.6,
            "avg_usd_m_per_session": 89.0, "prev_avg_usd_m_per_session": -87.7,
            "direction": "순유출→순유입 전환", "status": "잠정",
        }}}
        rows = fmt.calendar_window_reading(state, "3m", 1338.0)
        alert = fmt.ensure_krw_for_bare_usd("\n".join(rows), 1338.0)
        self.assertIn(
            "거래일평균 최근 +89.0백만달러 (약 +1,191억원)"
            " / 직전 -87.7백만달러 (약 -1,173억원)", alert
        )
        self.assertNotIn("+89.0/-87.7백만달러", alert)
        self.assertEqual(alert.count("+1,191억원"), 1)
        self.assertEqual(alert.count("-1,173억원"), 1)

    def test_partial_dates_are_labeled_for_both_comparison_periods(self):
        # Reproduces the 2026-10-28 natural alert: one partial day in each
        # period. The older date must not be silently omitted or attributed
        # to the recent period.
        window = {
            "valid": True, "start": "2026-07-28", "end": "2026-10-27",
            "trading_days": 65, "value_usd_m": 6109.7,
            "prev_value_usd_m": -6896.8, "change_usd_m": 13006.5,
            "direction": "순유출→순유입 전환", "status": "잠정",
            "partial_days": 1, "partial_dates": ["2026-08-07"],
            "prev_partial_days": 1, "prev_partial_dates": ["2026-07-27"],
        }
        output = "\n".join(fmt.calendar_window_reading({"windows": {"3m": window}}, "3m", None))
        self.assertIn("최근 1/직전 1 (최근 2026-08-07 / 직전 2026-07-27)", output)

        window.update(partial_days=0, partial_dates=[])
        output = "\n".join(fmt.calendar_window_reading({"windows": {"3m": window}}, "3m", None))
        self.assertIn("최근 0/직전 1 (직전 2026-07-27)", output)

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


class CryptoReportCompletionWordingTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        path = pathlib.Path(__file__).parent / "fixtures" / "crypto_report_completion_20261015.json"
        cls.fixture = json.loads(path.read_text(encoding="utf-8"))

    def run_preserved_snapshots(self, old, current):
        """Replay collection outputs locally; no source request or delivery is allowed."""
        observed = self.fixture["operating_state"]
        query_time = dt.datetime.fromisoformat(observed["updated_at_kst"])

        class FrozenDateTime(dt.datetime):
            @classmethod
            def now(cls, tz=None):
                return query_time.astimezone(tz) if tz else query_time.replace(tzinfo=None)

        with tempfile.TemporaryDirectory() as folder:
            root = pathlib.Path(folder)
            state_path, pending_path = root / "state.json", root / "pending.json"
            alert_path, status_path = root / "alert.txt", root / "status.md"
            state_path.write_text(json.dumps(old), encoding="utf-8")
            before = state_path.read_bytes()
            with (
                patch.object(watch, "OUT_DIR", root),
                patch.object(watch, "STATE_PATH", state_path),
                patch.object(watch, "PENDING_STATE", pending_path),
                patch.object(watch, "ALERT_PATH", alert_path),
                patch.object(watch, "STATUS_PATH", status_path),
                patch.object(watch.dt, "datetime", FrozenDateTime),
                patch.object(watch, "buyback_schedule", return_value=copy.deepcopy(observed["buyback"])),
                patch.object(watch, "treasury_rates", return_value=copy.deepcopy(observed["rates"])),
                patch.object(watch, "btc_etf_flow", return_value=copy.deepcopy(current)),
                patch("urllib.request.urlopen", side_effect=AssertionError("offline replay forbids HTTP")),
            ):
                watch.main()
            self.assertEqual(state_path.read_bytes(), before)
            pending = json.loads(pending_path.read_text(encoding="utf-8"))
            self.assertEqual(pending["errors"], [])
            raw = alert_path.read_text(encoding="utf-8") if alert_path.exists() else ""
            final = ""
            if raw:
                fx = (
                    "\n원화 환산 기준: 1달러=1,340.50원 | 기준일 2026-10-14 | "
                    "한국은행 ECOS 원/미국달러(매매기준율)\n"
                )
                with patch.object(fmt, "PENDING_STATE_PATH", pending_path):
                    final = fmt.format_alert(raw + fx)
            return raw, final, pending

    def test_operating_completion_preserves_values_without_claiming_finality(self):
        raw, final, pending = self.run_preserved_snapshots(
            self.fixture["prior_state"], self.fixture["operating_state"]["btc_etf"]
        )
        self.assertIn("BTC 현물 ETF 보고 완료:", raw)
        self.assertIn("<b>일간 보고 완료</b>", final)
        self.assertIn("이후 수정 가능", final)
        self.assertNotIn("최종 확정", raw + final)
        self.assertNotIn("→ 최종 ", raw + final)
        self.assertIn("최초 잠정 -150.5백만달러", final)
        self.assertIn("보고 합계 -261.4백만달러", final)
        self.assertIn("(9/12)", final)
        self.assertIn("(12/12)", final)
        self.assertEqual(pending["btc_etf"], self.fixture["operating_state"]["btc_etf"])
        self.assertIn("최근 3개월 · 잠정", final)
        self.assertIn("2026-07-27, 2026-08-07", final)

    def test_same_amount_completion_still_reports_coverage_and_revision_limit(self):
        # Synthetic boundary: the last unreported fund contributes zero.
        old = copy.deepcopy(self.fixture["prior_state"])
        current = self.fixture["operating_state"]["btc_etf"]
        old["btc_etf"]["total_usd_m"] = current["total_usd_m"]
        old["btc_etf"]["provisional_history"] = []
        raw, final, pending = self.run_preserved_snapshots(old, current)
        self.assertIn("보고 완료(값 동일):", raw)
        self.assertIn("일간 보고 완료", final)
        self.assertIn("값 동일 · 이후 수정 가능", final)
        self.assertNotIn("최종 확정", final)
        self.assertEqual(pending["btc_etf"]["total_usd_m"], -261.4)

    def test_unchanged_complete_snapshot_does_not_trigger_another_alert(self):
        old = self.fixture["operating_state"]
        raw, final, pending = self.run_preserved_snapshots(old, old["btc_etf"])
        self.assertEqual((raw, final), ("", ""))
        self.assertEqual(pending["btc_etf"], old["btc_etf"])

    def test_complete_day_can_still_emit_a_same_day_source_revision(self):
        # Synthetic post-completion correction, with rolling values kept consistent.
        old = self.fixture["operating_state"]
        current = copy.deepcopy(old["btc_etf"])
        for key in ("total_usd_m", "latest_recomputed_total_usd_m", "day_change_usd_m", "last5_usd_m", "five_day_change_usd_m"):
            current[key] = round(current[key] - 0.1, 1)
        current["last5_values_usd_m"][-1] = current["total_usd_m"]
        current["day_change_pct"] = round(current["day_change_usd_m"] / abs(current["prev_total_usd_m"]) * 100, 1)
        current["five_day_change_pct"] = round(current["five_day_change_usd_m"] / abs(current["prev5_usd_m"]) * 100, 1)
        for window in current["windows"].values():
            window["value_usd_m"] = round(window["value_usd_m"] - 0.1, 1)
            window["change_usd_m"] = round(window["change_usd_m"] - 0.1, 1)
            window["avg_usd_m_per_session"] = round(window["value_usd_m"] / window["trading_days"], 1)
        raw, final, pending = self.run_preserved_snapshots(old, current)
        self.assertIn("당일 합계 수정(현재 집계)", raw)
        self.assertIn("당일 합계 수정", final)
        self.assertIn("-261.5백만달러", final)
        self.assertNotIn("일간 보고 완료", final)
        self.assertEqual(pending["btc_etf"]["total_usd_m"], -261.5)

    def test_legacy_completion_triggers_render_as_revisable_reports(self):
        for suffix in ("", "(값 동일)"):
            with self.subTest(suffix=suffix):
                raw = (
                    f"• BTC 현물 ETF 최종 확정{suffix}: "
                    "직전 잠정 -150.5백만달러 (9/12) → 최종 -261.4백만달러 (12/12)"
                )
                final = "\n".join(fmt.format_trigger(raw))
                self.assertIn("일간 보고 완료", final)
                self.assertIn("이후 수정 가능", final)
                self.assertIn("보고 합계 -261.4백만달러 (12/12)", final)
                self.assertNotIn("최종 확정", final)
                self.assertNotIn("→ 최종 ", final)


if __name__ == "__main__":
    unittest.main()
