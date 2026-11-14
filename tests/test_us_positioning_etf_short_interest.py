from __future__ import annotations

import datetime as dt
import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import us_positioning_etf_short_interest as etf


def chart(current, previous):
    return f"""<table><tr><th>Settlement Date</th><th>Short Interest %</th><th>Short Position</th><th>Days To Cover</th><th>Short Change</th><th>Change %</th></tr>
    <tr><td>2026-10-15</td><td>12.26</td><td>{current:,}</td><td>2.41</td><td>+10,000,000</td><td>16.38</td></tr>
    <tr><td>2026-09-30</td><td>10.50</td><td>{previous:,}</td><td>1.95</td><td>+4,000,000</td><td>7.19</td></tr>
    </table>"""


def benz(current, previous):
    return f"""<table><tr><th>Settlement Date</th><th>Dissemination Date</th><th>% Float</th><th>Float</th><th>Short Interest</th><th>Volume</th><th>Days to Cover</th></tr>
    <tr><td>Oct 15, 2026</td><td>Oct 26, 2026</td><td>—</td><td>—</td><td>{current:,}</td><td>33,969,720</td><td>2.41</td></tr>
    <tr><td>Sep 30, 2026</td><td>Oct 9, 2026</td><td>—</td><td>—</td><td>{previous:,}</td><td>36,049,629</td><td>1.95</td></tr>
    </table>"""


def finshort(current, previous):
    return f"""<table><tr><th>Settlement date</th><th>Short interest</th><th>Change</th></tr>
    <tr><td>Oct 15, 2026</td><td>{current:,}</td><td>+16.38%</td></tr>
    <tr><td>Sep 30, 2026</td><td>{previous:,}</td><td>+7.19%</td></tr>
    </table>"""


CALENDAR = """<table><tr><th>Settlement Date</th><th>Due Date</th><th>Publication Date</th></tr>
<tr><td>October 15 (Thursday)</td><td>October 19 – 6:00 p.m. (Monday)</td><td>October 26 (Monday)</td></tr>
<tr><td>October 30 (Friday)</td><td>November 3 – 6:00 p.m. (Tuesday)</td><td>November 10 (Tuesday)</td></tr>
</table>"""


def getter(*, spy=None, qqq=None, corrupt=False):
    values = {"QQQ": qqq or (82_001_618, 70_458_005),
              "SPY": spy or (92_995_326, 98_476_070)}

    def get(url):
        if "finra.org" in url:
            return CALENDAR
        symbol = "QQQ" if "QQQ" in url or "qqq/" in url else "SPY"
        new, old = values[symbol]
        if "chartexchange" in url:
            return chart(new + (11 if corrupt else 0), old)
        if "benzinga" in url:
            return benz(new, old)
        if "finshort" in url:
            return finshort(new, old)
        raise AssertionError("Unexpected endpoint")
    return get


HISTORY = {
    "2026-09-15": (65_733_364, 99_297_854),
    "2026-08-14": (64_250_491, 92_190_734),
    "2026-07-15": (67_036_554, 96_827_747),
    "2026-04-15": (66_298_978, 125_003_596),
    "2025-12-31": (43_042_346, 100_831_310),
}


def history_getter(*, conflict_spy_six_month=False):
    base = getter()

    def fetch(url):
        raw = base(url)
        if "finra.org" in url or "finshort" in url:
            return raw
        ticker = "QQQ" if "QQQ" in url or "qqq/" in url else "SPY"
        column = 0 if ticker == "QQQ" else 1
        rows = []
        for day_iso, amounts in HISTORY.items():
            amount = amounts[column]
            if conflict_spy_six_month and ticker == "SPY" and day_iso == "2026-04-15" and "benzinga" in url:
                amount += 1
            if "chartexchange" in url:
                rows.append(f"<tr><td>{day_iso}</td><td>10.00</td><td>{amount:,}</td>"
                            "<td>2.00</td><td>0</td><td>0.00</td></tr>")
            elif "benzinga" in url:
                when = dt.date.fromisoformat(day_iso)
                label = f"{when:%b} {when.day}, {when.year}"
                rows.append(f"<tr><td>{label}</td><td>History</td><td>—</td>"
                            f"<td>—</td><td>{amount:,}</td><td>30000000</td><td>2.0</td></tr>")
        return raw.replace("</table>", "\n".join(rows) + "</table>", 1)

    return fetch


class ETFShortInterestTests(unittest.TestCase):
    def test_horizon_comparisons_share_same_settlement_and_source_consensus(self):
        data = etf.collect(now=dt.date(2026, 11, 2), getter=history_getter())
        periods = data["period_comparisons"]
        self.assertEqual(set(periods), {"1개월", "2개월", "3개월", "6개월", "연초"})
        self.assertEqual(periods["1개월"]["previous_settlement"], "2026-09-15")
        self.assertEqual(periods["2개월"]["previous_settlement"], "2026-08-14")
        self.assertEqual(periods["3개월"]["previous_settlement"], "2026-07-15")
        self.assertEqual(periods["6개월"]["previous_settlement"], "2026-04-15")
        self.assertEqual(periods["연초"]["previous_settlement"], "2025-12-31")
        self.assertEqual(periods["2개월"]["QQQ"]["change_shares"], 17_751_127)
        self.assertAlmostEqual(periods["2개월"]["QQQ"]["change_pct"], 27.63, places=2)
        self.assertEqual(periods["2개월"]["SPY"]["change_shares"], 804_592)
        self.assertEqual(periods["6개월"]["SPY"]["change_shares"], -32_008_270)
        self.assertAlmostEqual(periods["연초"]["QQQ"]["change_pct"], 90.51, places=2)
        self.assertEqual(data["signal_key"], "2026-10-15:82001618:92995326")
        title, message = etf.render(data)
        self.assertIn("2개월(2026-08-14)", message)
        self.assertIn("+27.63%", message)
        self.assertIn("6개월(2026-04-15)", message)
        self.assertIn("-32,008,270주", message)
        self.assertIn("서로 다른 비교기간", message)
        self.assertLess(len(title) + 2 + len(message), 3900)

    def test_conflicting_historical_publisher_withholds_only_disputed_horizon(self):
        data = etf.collect(now=dt.date(2026, 11, 2),
                           getter=history_getter(conflict_spy_six_month=True))
        self.assertNotIn("6개월", data["period_comparisons"])
        self.assertIn("2개월", data["period_comparisons"])
        title, message = etf.render(data)
        self.assertIn("6개월: 과거 잔량 교차검증 미완료", message)
        self.assertNotIn("-32,008,270주", message)
        self.assertTrue(data["signal"])

    def test_historical_comparison_validation_never_sends_or_writes_state(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "historical_state.json"
            with patch.object(etf, "send_message", side_effect=AssertionError("unexpected send")):
                result = etf.run(validate_only=True, now=dt.date(2026, 11, 2),
                                 getter=history_getter(), state_path=path)
            self.assertEqual(result["status"], "alert_due")
            self.assertTrue(result["period_comparisons"]["연초"])
            self.assertFalse(result["telegram_sent"])
            self.assertFalse(path.exists())

    def test_missed_digest_heartbeat_gate_does_not_send_or_repeat(self):
        import os
        import textwrap
        workflow=(ROOT / ".github/workflows/us-positioning-telegram-watch.yml").read_text()
        self.assertIn('Warsh Reaction Function Telegram Watch', workflow)
        self.assertIn("github.event.workflow_run.event == 'schedule'", workflow)
        marker=("      - name: Recover only genuinely missing KST morning digests\n"
                "        id: check\n"
                "        run: |\n"
                "          python - <<'PY'\n")
        self.assertEqual(workflow.count(marker), 1)
        snippet=workflow.split(marker, 1)[1].split("\n          PY", 1)[0]
        script=textwrap.dedent(snippet)
        expected='now=dt.datetime.now(ZoneInfo("Asia/Seoul"))'
        self.assertIn(expected,script)
        previous=os.getcwd()
        with tempfile.TemporaryDirectory() as tmp:
            base=Path(tmp)
            (base / "data").mkdir()
            output=base / "github_output.txt"
            try:
                os.chdir(base)
                with patch.dict(os.environ, {"GITHUB_OUTPUT":str(output)}):
                    def run_gate(saved,hour):
                        (base/"data/us_positioning_state.json").write_text(
                            json.dumps({"daily_digest_sent_date_kst":saved}))
                        code=script.replace(
                            expected,'now=dt.datetime(2026,11,6,'+str(hour)
                            +',30,tzinfo=ZoneInfo("Asia/Seoul"))')
                        exec(compile(code,"recovery_gate","exec"),{})
                        return output.read_text().splitlines()[-2:]
                    self.assertEqual(run_gate("2026-11-05",10),["due=true","digest=true"])
                    self.assertEqual(run_gate("2026-11-06",10),["due=false","digest=false"])
                    self.assertEqual(run_gate("2026-11-05",12),["due=false","digest=false"])
            finally:
                os.chdir(previous)

    def test_finra_calendar_exact_dates(self):
        actual = etf.read_calendar(CALENDAR, 2026)
        self.assertEqual(actual["2026-10-15"], "2026-10-26")
        self.assertEqual(actual["2026-10-30"], "2026-11-10")

    def test_three_sources_parse_true_position_not_daily_short_volume(self):
        for source, payload in (
            ("chartexchange", chart(82_001_618, 70_458_005)),
            ("benzinga", benz(82_001_618, 70_458_005)),
            ("finshort", finshort(82_001_618, 70_458_005)),
        ):
            with self.subTest(source=source):
                rows = etf.parse_provider(source, payload)
                self.assertEqual(rows[0], {"settlement": "2026-10-15", "shares": 82_001_618})
                self.assertEqual(rows[1], {"settlement": "2026-09-30", "shares": 70_458_005})

    def test_qqq_spy_october_15_verified_divergence(self):
        data = etf.collect(now=dt.date(2026, 11, 1), getter=getter())
        self.assertEqual(data["QQQ"]["shares"], 82_001_618)
        self.assertEqual(data["QQQ"]["change_shares"], 11_543_613)
        self.assertEqual(data["SPY"]["shares"], 92_995_326)
        self.assertEqual(data["SPY"]["change_shares"], -5_480_744)
        self.assertEqual(round(data["QQQ"]["change_pct"], 2), 16.38)
        self.assertEqual(round(data["SPY"]["change_pct"], 2), -5.57)
        self.assertEqual(round(data["divergence_pp"], 2), 21.95)
        self.assertTrue(data["signal"])
        self.assertEqual(data["published"], "2026-10-26")
        self.assertTrue(all(data[t]["publisher_count"] >= 2 for t in ("QQQ", "SPY")))
        title, body = etf.render(data)
        self.assertIn("2026-10-15", body)
        self.assertIn("2026-10-26", body)
        self.assertLess(len(title) + len(body), 3900)

    def test_conflicting_source_cannot_override_two_matching_sources(self):
        data = etf.collect(now=dt.date(2026, 11, 1), getter=getter(corrupt=True))
        self.assertEqual(data["QQQ"]["shares"], 82_001_618)
        self.assertNotIn("chartexchange", data["QQQ"]["sources"])

    def test_publication_date_and_stale_gate(self):
        with self.assertRaisesRegex(RuntimeError, "not current"):
            etf.collect(now=dt.date(2026, 10, 25), getter=getter())
        with self.assertRaisesRegex(RuntimeError, "publication lag"):
            etf.collect(now=dt.date(2026, 11, 12), getter=getter())

    def test_qqq_high_watermark_uses_verified_history_not_a_chart_caption(self):
        latest = "2026-10-30"
        start = dt.date(2025, 11, 14)
        prior = {
            (start + dt.timedelta(days=15 * i)).isoformat(): 43_000_000 + 1_000_000 * i
            for i in range(23)
        }
        prior["2026-10-15"] = 82_001_618
        history = {**prior, latest: 82_794_708}
        peak = etf._verified_qqq_high(latest, history)
        self.assertEqual(peak["months"], 12)
        self.assertEqual(peak["prior_max_shares"], 82_001_618)
        self.assertGreaterEqual(peak["observations"], 18)
        self.assertIsNone(etf._verified_qqq_high(latest, {
            **prior, latest: 81_000_000
        }))
        self.assertIsNone(etf._verified_qqq_high(latest, {
            "2026-10-15": 82_001_618, latest: 82_794_708
        }))
        self.assertNotIn("2023", str(peak))

    def test_qqq_peak_is_independent_of_spy_two_week_change(self):
        # 0.97% QQQ short increase vs 10.51% SPY increase would miss
        # the historical SPY-relative threshold; verified QQQ high is new.
        qqq_change = (82_794_708 / 82_001_618 - 1) * 100
        spy_change = (102_769_489 / 92_995_326 - 1) * 100
        self.assertLess(abs(qqq_change - spy_change), 15.0)
        self.assertLess(qqq_change, 20.0)
        history = {
            (dt.date(2025, 11, 14) + dt.timedelta(days=15 * i)).isoformat():
            43_000_000 + 1_000_000 * i for i in range(23)
        }
        history["2026-10-15"] = 82_001_618
        history["2026-10-30"] = 82_794_708
        self.assertIsNotNone(etf._verified_qqq_high("2026-10-30", history))

    def test_valid_latest_publication_remains_current_after_twelve_days(self):
        # 2026-10-15 settles / 10-26 release; next release is 11-10.
        data = etf.collect(now=dt.date(2026, 11, 9), getter=getter())
        self.assertEqual(data["settlement"], "2026-10-15")
        self.assertEqual(data["publication_age_days"], 14)
        self.assertTrue(data["signal"])

    def test_finra_calendar_year_tables_are_not_relabeled(self):
        html = """<h2>2025 Short Interest Reporting Dates</h2>
        <table><tr><th>Settlement Date</th><th>Due Date</th><th>Publication Date</th></tr>
        <tr><td>October 15 (Wednesday)</td><td>October 17</td><td>October 24</td></tr></table>
        <h2>2026 Short Interest Reporting Dates</h2>
        <table><tr><th>Settlement Date</th><th>Due Date</th><th>Publication Date</th></tr>
        <tr><td>October 15 (Thursday)</td><td>October 19</td><td>October 26</td></tr></table>"""
        self.assertEqual(etf.read_calendar(html, 2025), {
            "2025-10-15": "2025-10-24"
        })
        self.assertEqual(etf.read_calendar(html, 2026), {
            "2026-10-15": "2026-10-26"
        })

    def test_verified_prior_december_release_survives_new_year(self):
        dates = etf.verified_calendar(dt.date(2027, 1, 12), getter=lambda _url: "")
        self.assertEqual(dates.get("2026-12-31"), "2027-01-12")

    def test_us_positioning_sender_rejects_invalid_receipts_and_ambiguous_retries(self):
        workflow = (ROOT / ".github/workflows/us-positioning-telegram-watch.yml").read_text()
        send = workflow.split("      - name: Send Telegram update", 1)[1].split(
            "      - name: Persist state after successful delivery", 1
        )[0]
        self.assertNotIn("for attempt in range(3)", send)
        self.assertIn("type(message_id) is not int", send)
        self.assertIn("message_id <= 0", send)
        self.assertIn("type(returned_id) is not int", send)
        self.assertIn("recipient_matches", send)
        self.assertIn('"chat_id_match":True', send)
        self.assertIn("ids.append(message_id)", send)

    def test_us_positioning_code_audits_do_not_block_production(self):
        workflow = (ROOT / ".github/workflows/us-positioning-telegram-watch.yml").read_text()
        self.assertIn("github.event_name == 'push' && 'code-audit' || 'production'", workflow)
        self.assertIn("cancel-in-progress: false", workflow)
        self.assertIn("github.event_name != 'push'", workflow)
        self.assertIn("--validate-only", workflow)

    def test_no_alert_from_ordinary_same_direction_etf_shift(self):
        data = etf.collect(
            now=dt.date(2026, 11, 1),
            getter=getter(qqq=(71_000_000, 70_458_005), spy=(99_000_000, 98_476_070))
        )
        self.assertFalse(data["signal"])
        self.assertIn("ETF 헤지", etf.render(data)[1])

    def test_validate_only_never_sends_or_advances_state(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "state.json"
            with patch.object(etf, "send_message", side_effect=AssertionError("validate-only send")):
                result = etf.run(validate_only=True, now=dt.date(2026, 11, 1),
                                 getter=getter(), state_path=path)
            self.assertEqual(result["status"], "alert_due")
            self.assertFalse(result["telegram_sent"])
            self.assertFalse(path.exists())

    def test_one_verified_send_suppresses_repeats(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "state.json"
            receipt = {"message_id": 102, "chat_id_returned": True,
                       "chat_id_match": True, "bot_username": etf.EXPECTED_BOT}
            with patch.object(etf, "send_message", return_value=receipt) as sender:
                first = etf.run(validate_only=False, now=dt.date(2026, 11, 1),
                                getter=getter(), state_path=path)
                self.assertTrue(first["telegram_sent"])
                self.assertEqual(json.loads(path.read_text())["last_alert"]["message_id"], 102)
                second = etf.run(validate_only=False, now=dt.date(2026, 11, 1),
                                 getter=getter(), state_path=path)
                self.assertEqual(second["status"], "duplicate_suppressed")
                self.assertEqual(sender.call_count, 1)

    def test_corrupt_state_refuses_reset(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "state.json"
            path.write_text("{NOT JSON")
            with self.assertRaisesRegex(RuntimeError, "unreadable"):
                etf.load_state(path)

    def test_disallow_daily_short_volume_as_short_interest(self):
        with self.assertRaises(ValueError):
            etf.parse_provider("finshort", "<p>QQQ daily short volume 20,683,025 2026-10-30</p>")


if __name__ == "__main__":
    unittest.main()
