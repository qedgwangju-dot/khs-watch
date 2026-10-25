"""Offline timeout regressions. Synthetic data only; all sends forbidden."""
import contextlib
import copy
import io
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

import requests

import treasury_etf_flow_watch as base
import treasury_credit_flow_watch_ishares as watch


HTML = """<html><body>
NAV as of Oct 09, 2026 $80.00
Shares Outstanding 100,000 as of Oct 09, 2026
30 Day SEC Yield as of Oct 09, 2026 4.00%
1 Day NAV Change as of Oct 09, 2026 (+0.25%)
Net Assets of Fund $8,000,000 as of Oct 09, 2026
</body></html>"""


def response(text=HTML, status=200):
    r = requests.Response()
    r.status_code = status
    r._content = text.encode()
    r.url = "https://www.ishares.com/synthetic-fixture"
    return r


class IsharesTimeoutRegression(unittest.TestCase):
    def setUp(self):
        self.output = io.StringIO()
        self.stack = contextlib.ExitStack()
        self.addCleanup(self.stack.close)
        self.stack.enter_context(contextlib.redirect_stdout(self.output))
        # An accidental unmocked provider or Telegram request must fail.
        self.stack.enter_context(patch("requests.sessions.Session.request", side_effect=AssertionError("external request forbidden")))
        self.stack.enter_context(patch("urllib.request.urlopen", side_effect=AssertionError("external request forbidden")))
        self.sleep = self.stack.enter_context(patch("time.sleep"))

    def test_read_timeout_recovers_on_one_extra_read(self):
        with patch.object(base.requests, "get", side_effect=[requests.ReadTimeout("synthetic"), response()]) as get:
            row = base.get_ishares("SHY", watch.FUNDS["SHY"])
        self.assertEqual(row["nav"], 80.0)
        self.assertEqual(row["shares"], 100000.0)
        self.assertEqual(row["date"], "2026-10-09")
        self.assertEqual(get.call_count, 2)
        self.assertEqual(get.call_args.kwargs["timeout"], (8, 35))
        self.sleep.assert_called_once_with(2)
        self.assertIn("ishares_request_retry=true ticker=SHY reason=ReadTimeout", self.output.getvalue())

    def test_connect_timeout_also_has_one_retry(self):
        with patch.object(base.requests, "get", side_effect=[requests.ConnectTimeout("synthetic"), response()]) as get:
            base.get_ishares("SHY", watch.FUNDS["SHY"])
        self.assertEqual(get.call_count, 2)

    def test_exhaustion_reraises_and_stops_after_two_attempts(self):
        with patch.object(base.requests, "get", side_effect=requests.ReadTimeout("synthetic")) as get:
            with self.assertRaises(requests.ReadTimeout):
                base.get_ishares("SHY", watch.FUNDS["SHY"])
        self.assertEqual(get.call_count, 2)
        self.sleep.assert_called_once_with(2)
        self.assertIn("retry_budget_exhausted=true", self.output.getvalue())

    def test_one_retry_allowance_is_shared_across_funds(self):
        budget = base.IsharesRetryBudget()
        with patch.object(base.requests, "get", side_effect=[requests.ReadTimeout(), response(), requests.ReadTimeout()]) as get:
            base.get_ishares("SHY", watch.FUNDS["SHY"], retry_budget=budget)
            with self.assertRaises(requests.ReadTimeout):
                base.get_ishares("IEF", watch.FUNDS["IEF"], retry_budget=budget)
        self.assertEqual(get.call_count, 3)
        self.assertEqual(budget.remaining, 0)
        self.sleep.assert_called_once_with(2)

    def test_success_does_not_consume_shared_retry_allowance(self):
        budget = base.IsharesRetryBudget()
        with patch.object(base.requests, "get", return_value=response()) as get:
            base.get_ishares("SHY", watch.FUNDS["SHY"], retry_budget=budget)
            base.get_ishares("IEF", watch.FUNDS["IEF"], retry_budget=budget)
        self.assertEqual(get.call_count, 2)
        self.assertEqual(budget.remaining, 1)
        self.sleep.assert_not_called()

    def test_http_errors_are_not_retried(self):
        for status in (400, 401, 403, 404, 429, 500, 503):
            with self.subTest(status=status), patch.object(base.requests, "get", return_value=response(status=status)) as get:
                with self.assertRaises(requests.HTTPError):
                    base.get_ishares("SHY", watch.FUNDS["SHY"])
                get.assert_called_once()
        self.sleep.assert_not_called()

    def test_parse_and_security_errors_are_not_retried(self):
        with patch.object(base.requests, "get", return_value=response("invalid synthetic HTML")) as get:
            with self.assertRaisesRegex(RuntimeError, "parse failed"):
                base.get_ishares("SHY", watch.FUNDS["SHY"])
        get.assert_called_once()
        with patch.object(base.requests, "get", side_effect=requests.exceptions.SSLError("synthetic")) as get:
            with self.assertRaises(requests.exceptions.SSLError):
                base.get_ishares("SHY", watch.FUNDS["SHY"])
        get.assert_called_once()
        self.sleep.assert_not_called()

    def test_parser_preserves_component_dates(self):
        html = HTML.replace("100,000 as of Oct 09, 2026", "100,000 as of Oct 08, 2026")
        with patch.object(base.requests, "get", return_value=response(html)):
            row = base.get_ishares("SHY", watch.FUNDS["SHY"])
        self.assertEqual(row["date"], "2026-10-08")
        self.assertEqual(row["nav_date"], "2026-10-09")
        self.assertEqual(row["shares_date"], "2026-10-08")

    def test_parser_reads_official_nav_change_with_spaced_percent(self):
        html = HTML.replace("(+0.25%)", "$ $ 0.04 ( 0.05 %)")
        with patch.object(base.requests, "get", return_value=response(html)):
            row = base.get_ishares("IEF", watch.FUNDS["IEF"])
        self.assertEqual(row["nav_change_pct"], 0.05)

    def test_parser_rejects_nav_change_from_other_date(self):
        html = HTML.replace("1 Day NAV Change as of Oct 09", "1 Day NAV Change as of Oct 08")
        with patch.object(base.requests, "get", return_value=response(html)):
            row = base.get_ishares("IEF", watch.FUNDS["IEF"])
        self.assertIsNone(row["nav_change_pct"])

    def test_invalid_saved_state_is_not_silently_reset(self):
        with tempfile.TemporaryDirectory() as folder:
            state_path = Path(folder) / "state.json"
            state_path.write_text("{broken", encoding="utf-8")
            with patch.object(base, "DATA", state_path):
                with self.assertRaisesRegex(RuntimeError, "state is unreadable"):
                    base.load_state()
            self.assertEqual(state_path.read_text(encoding="utf-8"), "{broken")

    def main_context(self):
        state = {"history": {}, "last_delivery": {"treasury_date": "2026-10-08", "message_ids": [123], "bot_username": "khs8879887988798879_bot"}}
        self.stack.enter_context(patch.dict(os.environ, {
            "GITHUB_EVENT_NAME": "schedule",
            "TREASURY_DAILY_DIGEST": "0",
            "TREASURY_REPORT_VALIDATE_ONLY": "0",
        }))
        self.stack.enter_context(patch.object(base, "load_state", return_value=copy.deepcopy(state)))
        self.stack.enter_context(patch.object(base, "get_usdkrw", return_value={"rate": 1350, "date": "2026-10-09"}))
        curve = {"date": "2026-10-09", "2Y": 4.5, "10Y": 5.0, "30Y": 5.5}
        self.stack.enter_context(patch.object(watch, "get_curve_pair", return_value=(curve, None)))
        self.stack.enter_context(patch.object(watch, "_us_latest_weekday", return_value="2026-10-09"))
        self.sender = self.stack.enter_context(patch.object(watch, "send_exact", side_effect=AssertionError("send forbidden")))
        self.saver = self.stack.enter_context(patch.object(base, "save_state", side_effect=AssertionError("state save forbidden")))
        temp = self.stack.enter_context(tempfile.TemporaryDirectory())
        self.out = Path(temp)
        self.stack.enter_context(patch.object(base, "OUT", self.out))

    def test_main_persistent_timeout_never_sends_saves_or_reports_success(self):
        self.main_context()
        with patch.object(base.requests, "get", side_effect=requests.ReadTimeout("synthetic")) as get:
            with self.assertRaises(requests.ReadTimeout):
                watch.main()
        self.assertEqual(get.call_count, 2)
        self.sender.assert_not_called()
        self.saver.assert_not_called()
        self.assertEqual(list(self.out.iterdir()), [])
        self.assertNotIn("telegram_delivery_confirmed", self.output.getvalue())

    def test_main_uses_one_budget_across_funds(self):
        self.main_context()
        with patch.object(base.requests, "get", side_effect=[requests.ReadTimeout(), response(), requests.ReadTimeout()]) as get:
            with self.assertRaises(requests.ReadTimeout):
                watch.main()
        self.assertEqual(get.call_count, 3)
        self.assertEqual(get.call_args.args[0], watch.FUNDS["IEF"]["url"])
        self.sender.assert_not_called()
        self.saver.assert_not_called()
        self.assertEqual(list(self.out.iterdir()), [])

    def test_main_recovers_to_validation_without_send_or_state_save(self):
        self.main_context()
        history = {
            ticker: [{"date": "2026-10-08", "shares": 99_000, "nav": 79.0, "oas_bps": 89.0, "oas_date": "2026-10-08"}]
            for ticker in watch.FUNDS
        }
        with patch.dict(os.environ, {"TREASURY_REPORT_VALIDATE_ONLY": "1"}), \
             patch.object(base, "load_state", return_value={"history": history}), \
             patch.object(watch, "parse_oas_snapshot", return_value={"value": 90, "date": "2026-10-09"}), \
             patch.object(base.requests, "get", side_effect=[requests.ReadTimeout()] + [response() for _ in range(5)]) as get:
            watch.main()
        self.assertEqual(get.call_count, 6)
        self.sender.assert_not_called()
        self.saver.assert_not_called()
        self.assertIn("treasury_report_validation_only=true telegram_sent=false", self.output.getvalue())
        self.assertTrue((self.out / "treasury_etf_flow_status.md").exists())

    def test_missing_previous_fund_rows_saves_baseline_without_sending(self):
        self.main_context()
        with patch.object(watch, "parse_oas_snapshot", return_value={"value": 90, "date": "2026-10-09"}), \
             patch.object(base.requests, "get", return_value=response()), \
             patch.object(base, "save_state") as save:
            watch.main()
        self.sender.assert_not_called()
        save.assert_called_once()
        self.assertIn('"report_withheld": "fund_baseline_missing"', self.output.getvalue())
        self.assertEqual(list(self.out.iterdir()), [])

    def test_recovery_still_withholds_mismatched_component_dates(self):
        self.main_context()
        bad_date = HTML.replace("100,000 as of Oct 09, 2026", "100,000 as of Oct 08, 2026")
        with patch.object(watch, "parse_oas_snapshot", return_value={"value": 90, "date": "2026-10-09"}), \
             patch.object(base.requests, "get", side_effect=[requests.ReadTimeout(), response(bad_date)] + [response() for _ in range(4)]):
            watch.main()
        self.sender.assert_not_called()
        self.saver.assert_not_called()
        self.assertIn('"report_withheld": "fund_component_date_mismatch"', self.output.getvalue())
        self.assertEqual(list(self.out.iterdir()), [])

    def test_treasury_holiday_withholds_report_but_saves_etf_baseline(self):
        self.main_context()
        stale_curve = {"date": "2026-10-08", "2Y": 4.5, "10Y": 5.0, "30Y": 5.5}
        with patch.object(watch, "get_curve_pair", return_value=(stale_curve, None)), \
             patch.object(watch, "parse_oas_snapshot", return_value={"value": 90, "date": "2026-10-09"}), \
             patch.object(base.requests, "get", return_value=response()), \
             patch.object(base, "save_state") as save:
            watch.main()
        self.sender.assert_not_called()
        save.assert_called_once()
        saved = save.call_args.args[0]
        self.assertTrue(all(saved["history"][ticker][-1]["date"] == "2026-10-09" for ticker in watch.FUNDS))
        self.assertIn('"report_withheld": "source_date_mismatch"', self.output.getvalue())
        self.assertIn('"fund_baseline_saved": true', self.output.getvalue())
        self.assertEqual(list(self.out.iterdir()), [])

    def test_already_delivered_market_date_skips_provider_and_send(self):
        self.main_context()
        state = {"last_delivery": {"treasury_date": "2026-10-09", "message_ids": [123], "bot_username": "khs8879887988798879_bot"}}
        with patch.object(base, "load_state", return_value=state), \
             patch.object(base.requests, "get", side_effect=AssertionError("provider must be skipped")) as get:
            watch.main()
        get.assert_not_called()
        self.sender.assert_not_called()
        self.saver.assert_not_called()
        self.assertIn("same_market_day_delivery_suppressed=true", self.output.getvalue())


if __name__ == "__main__":
    unittest.main()
