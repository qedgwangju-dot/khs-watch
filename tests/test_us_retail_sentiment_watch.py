"""Offline source, deduplication, accuracy and Telegram receipt tests."""
import datetime as dt
import io
import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from scripts import us_retail_sentiment_watch as w

NOW = dt.date(2026, 10, 28)
AAII_HTML = """
<html><body><h1>Asset Allocation Survey</h1>
Asset Allocation Results for September 2026 :
Stock Funds 38.35% (+0.73%) Stocks 33.44% (0.00%)
Stocks Total 71.79%
Bond Funds 9.13% (-0.38%) Bonds 5.74% (+0.61%)
Bonds Total 14.87% Cash 13.35% (-0.95%)
<h2>Commentary</h2>October 1, 2026</body></html>
"""
CB_HTML = """
<html><body><h1>US Consumer Confidence</h1>
Latest Press Release Updated: Tuesday, October 27, 2026
The Conference Board Consumer Confidence Index rose by 7.5 points to
91.7 (1985=100) in October, up from 84.2 in September.
Overall, more consumers in October expected stock prices to
increase rather than decrease in the next 12 months.
</body></html>
"""


def source(url):
    if url == w.AAII_URL:
        return AAII_HTML
    if url == w.CB_URL:
        return CB_HTML
    raise AssertionError("Unexpected URL")


class RetailSentimentTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        root = Path(temp.name)
        self.state = root / "sentiment.json"
        self.msg_patch = patch.object(w, "MESSAGE", root / "alert.html")
        self.msg_patch.start()
        self.addCleanup(self.msg_patch.stop)

    def test_aaii_official_allocation_values_and_period(self):
        a = w.parse_aaii(AAII_HTML, NOW)
        self.assertEqual(a["period"], "2026-09")
        self.assertEqual(a["stock_pct"], 71.79)
        self.assertEqual(a["bond_pct"], 14.87)
        self.assertEqual(a["cash_pct"], 13.35)
        self.assertNotIn("all_time_high", a)

    def test_aaii_rejects_wrong_sum_and_future_month(self):
        with self.assertRaisesRegex(ValueError, "sum"):
            w.parse_aaii(AAII_HTML.replace("71.79%", "81.79%"), NOW)
        with self.assertRaisesRegex(ValueError, "future"):
            w.parse_aaii(AAII_HTML.replace("September 2026", "November 2026"), NOW)

    def test_conference_board_stocks_up_is_qualitative_not_52pct(self):
        x = w.parse_conference_board(CB_HTML, NOW)
        self.assertEqual(x["cci"], 91.7)
        self.assertEqual(x["cci_previous_revised"], 84.2)
        self.assertEqual(x["cci_delta"], 7.5)
        self.assertEqual(x["stock_outlook_12m"], "상승 기대 우세")
        self.assertIsNone(x["stock_outlook_12m_percent"])

    def test_conference_board_bad_date_and_wrong_index_direction_fail_closed(self):
        with self.assertRaisesRegex(ValueError, "future"):
            w.parse_conference_board(
                CB_HTML.replace("October 27, 2026", "October 29, 2026"), NOW)
        with self.assertRaisesRegex(ValueError, "inconsistent"):
            w.parse_conference_board(
                CB_HTML.replace("up from 84.2", "down from 84.2"), NOW)

    def test_no_stock_outlook_percent_created_when_sentence_missing(self):
        raw = CB_HTML.replace("increase rather than decrease", "change rather than remain")
        observation = w.parse_conference_board(raw, NOW)
        self.assertEqual(observation["stock_outlook_12m"], "미확인")
        self.assertIsNone(observation["stock_outlook_12m_percent"])

    def test_baselines_do_not_send_historical_alerts(self):
        with patch.object(w, "send_verified") as send:
            result = w.run(state_path=self.state, getter=source, now=NOW, sender=send)
        self.assertEqual(result["status"], "baseline_saved")
        send.assert_not_called()
        current = w.load_state(self.state)
        self.assertEqual(set(current["sources"]), {"AAII", "Conference Board"})
        self.assertEqual(current["sent_keys"], [])

    def test_identical_source_content_never_resends(self):
        w.run(state_path=self.state, getter=source, now=NOW)
        with patch.object(w, "send_verified") as send:
            second = w.run(state_path=self.state, getter=source, now=NOW, sender=send)
        self.assertEqual(second["status"], "unchanged")
        send.assert_not_called()

    def test_newer_official_aaii_release_sends_only_one_event(self):
        w.run(state_path=self.state, getter=source, now=NOW)
        october = AAII_HTML.replace("September 2026", "October 2026")
        october = october.replace("71.79%", "72.79%").replace("13.35%", "12.35%")
        future = dt.date(2026, 11, 3)
        def get(u):
            return october if u == w.AAII_URL else CB_HTML
        with patch.object(w, "MESSAGE", self.state.parent / "alert.html"):
            first = w.run(state_path=self.state, getter=get, now=future,
                          sender=lambda body: (w.EXPECTED_BOT, 2401))
        self.assertEqual(first["status"], "sent")
        self.assertEqual(len(first["events"]), 1)
        self.assertEqual(w.load_state(self.state)["last_delivery"]["message_id"], 2401)
        with patch.object(w, "send_verified") as send:
            second = w.run(state_path=self.state, getter=get, now=future, sender=send)
        self.assertEqual(second["status"], "unchanged")
        send.assert_not_called()

    def test_stale_page_cannot_roll_back_newer_confirmed_month(self):
        state = {"version": 1, "sources": {"AAII": {
            **w.parse_aaii(AAII_HTML, NOW), "period": "2026-10"
        }}, "sent_keys": [], "last_delivery": None}
        new, events = w.classify_changes(state, {"AAII": w.parse_aaii(AAII_HTML, NOW)})
        self.assertEqual(events, [])
        self.assertEqual(new["sources"]["AAII"]["period"], "2026-10")

    def test_source_failure_is_isolated_and_not_acknowledged(self):
        with patch.object(w, "send_verified") as send:
            out = w.run(state_path=self.state, getter=lambda _: (_ for _ in ()).throw(
                OSError("source blocked")), now=NOW, sender=send)
        self.assertEqual(out["status"], "source_withheld")
        self.assertFalse(self.state.exists())
        send.assert_not_called()

    def test_validate_only_never_sends_or_changes_state(self):
        with patch.object(w, "send_verified") as send:
            out = w.run(validate_only=True, state_path=self.state,
                        getter=source, now=NOW, sender=send)
        self.assertEqual(out["status"], "validated")
        self.assertFalse(self.state.exists())
        send.assert_not_called()

    def test_send_failure_leaves_source_keys_unconsumed(self):
        w.run(state_path=self.state, getter=source, now=NOW)
        prev_state = self.state.read_text()
        october = AAII_HTML.replace("September 2026", "October 2026")
        october = october.replace("71.79%", "72.79%").replace("13.35%", "12.35%")
        future = dt.date(2026, 11, 3)
        def get(url):
            return october if url == w.AAII_URL else CB_HTML
        def sender(msg):
            raise RuntimeError("Telegram not delivered")
        with self.assertRaisesRegex(RuntimeError, "not delivered"):
            w.run(state_path=self.state, getter=get, now=future, sender=sender)
        self.assertEqual(prev_state, self.state.read_text())

    def test_telegram_response_requires_chat_id_and_message_id(self):
        identity = {"ok": True, "result": {"username": w.EXPECTED_BOT}}
        wrong = {"ok": True, "result": {
            "message_id": 33, "chat": {"id": -1009999}}}
        exact = {"ok": True, "result": {
            "message_id": 44, "chat": {"id": -1004444}}}
        credentials = {"TELEGRAM_BOT_TOKEN": "dummy-value",
                       "TELEGRAM_CHAT_ID": "-1004444",
                       "EXPECTED_TELEGRAM_BOT_USERNAME": w.EXPECTED_BOT}
        with patch.dict(os.environ, credentials):
            with patch.object(w.urllib.request, "urlopen",
                              side_effect=[io.BytesIO(json.dumps(z).encode())
                                           for z in (identity, wrong)]):
                with self.assertRaisesRegex(RuntimeError, "unexpected chat"):
                    w.send_verified("<b>TEST</b>")
            with patch.object(w.urllib.request, "urlopen",
                              side_effect=[io.BytesIO(json.dumps(z).encode())
                                           for z in (identity, exact)]):
                self.assertEqual(w.send_verified("<b>TEST</b>"),
                                 (w.EXPECTED_BOT, 44))

    def test_text_does_not_claim_record_or_hedge_fund_sales(self):
        a = w.parse_aaii(AAII_HTML, NOW)
        b = w.parse_conference_board(CB_HTML, NOW)
        x = w.render([{"source": "AAII", "current": {**a, "period": "2026-10"},
                       "previous": a}], {"AAII": a, "Conference Board": b})
        self.assertIn("사상 최고", x)
        self.assertIn("단정하지", x)
        self.assertIn("서로 다른 표본", x)


if __name__ == "__main__":
    unittest.main()
