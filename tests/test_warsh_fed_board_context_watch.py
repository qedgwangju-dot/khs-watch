import datetime as dt
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

import warsh_fed_board_context_watch as context
import warsh_speech_watch as original_speech
import warsh_policy_path_watch_v4 as futures


def example_speech(speaker, day, body):
    name = "Christopher J. Waller" if speaker == "waller" else "Michelle W. Bowman"
    return f"<html><h1>{name}</h1><p>{day}</p><p>{body}</p></html>"


class WarshFedBoardContextTests(unittest.TestCase):
    def test_speech_url_allowlist_rejects_other_hosts(self):
        self.assertIsNone(context._extract_pubday(
            "https://example.com/newsevents/speech/waller20261110a.htm"))
        self.assertEqual(
            context._extract_pubday(context.SEEDS[0]), dt.date(2026, 11, 10))

    def test_waller_december_25_50_is_conditional(self):
        body = ("even if prices cool, I would support a 25 basis point increase "
                "at our December meeting. With core CPI elevated, a "
                "50 basis point hike should be considered.")
        msg = context.speech_message(context.SEEDS[0],
            example_speech("waller", "November 10, 2026", body))
        self.assertIn("0.25%p", msg)
        self.assertIn("0.50%p", msg)
        self.assertIn("99.1%", msg)
        self.assertIn("당시", msg)
        self.assertIn("확정", msg)

    def test_bowman_credits_and_rate_costs_both_required(self):
        body = ("off-balance-sheet liabilities may be a concern if "
                "revenues from AI customers disappoint. The benefit of "
                "additional policy tightening must be carefully weighed.")
        msg = context.speech_message(context.SEEDS[1],
            example_speech("bowman", "November 10, 2026", body))
        self.assertIn("금융안정", msg)
        self.assertIn("인상", msg)
        self.assertIn("부채", msg)

    def test_unverified_speech_no_alert(self):
        self.assertIsNone(context.speech_message(
            "https://www.federalreserve.gov/newsevents/speech/waller20261111a.htm",
            example_speech("waller", "November 11, 2026", "A welcome at a conference.")))
        with self.assertRaises(RuntimeError):
            context.speech_message(context.SEEDS[0],
                example_speech("waller", "November 10, 2026", "Policy stance unclear."))

    def test_wrong_date_is_not_disguised_as_current(self):
        with self.assertRaisesRegex(RuntimeError, "date"):
            context.speech_message(context.SEEDS[0],
                example_speech("waller", "November 9, 2026",
                               "support a 25 basis point increase, 50 basis point hike, core CPI, December meeting"))

    def test_schedule_release_not_eight_rate_decisions(self):
        sample = ("Federal Reserve announces revised tentative schedule of Federal Open Market "
                  "Committee meetings in 2027. January 26-27 March 16-17 April 27-28 "
                  "June 8-9 July 27-28 September 14-15 October 26-27 "
                  "November 16-17. The October 26-27 meeting will be dedicated to "
                  "broad monetary policy strategy issues.")
        msg = context.schedule_message(sample)
        self.assertIn("7회", msg)
        self.assertIn("전략", msg)
        self.assertIn("11/17", msg)
        self.assertIn("2026년 12월", msg)

    def test_schedule_unverified_fails_closed(self):
        with self.assertRaisesRegex(RuntimeError, "not fully verified"):
            context.schedule_message("2027 FOMC meetings are under discussion.")

    def test_unknown_delivery_does_not_retry(self):
        with tempfile.TemporaryDirectory() as p:
            fake = Path(p) / "state.json"
            state = {"sent": {}, "pending": {}, "skipped": {}}
            with (patch.object(context, "STATE_PATH", fake),
                  patch.object(context, "send", side_effect=TimeoutError("ambiguous")) as send):
                with self.assertRaises(TimeoutError):
                    context.deliver(state, "speech:waller:20261110a", "msg", context.SEEDS[0])
                self.assertFalse(context.deliver(state, "speech:waller:20261110a", "msg", context.SEEDS[0]))
                self.assertEqual(send.call_count, 1)
                self.assertEqual(json.loads(fake.read_text())["pending"]["speech:waller:20261110a"]["status"],
                                 "delivery_uncertain")

    def test_confirmed_delivery_is_idempotent(self):
        with tempfile.TemporaryDirectory() as p:
            state = {"sent": {}, "pending": {}, "skipped": {}}
            with (patch.object(context, "STATE_PATH", Path(p) / "state.json"),
                  patch.object(context, "send", return_value={"message_id": 205, "recipient_verified": True}) as send):
                self.assertTrue(context.deliver(state, "calendar:2027:monetary20261112a", "msg", context.SCHEDULE))
                self.assertFalse(context.deliver(state, "calendar:2027:monetary20261112a", "msg", context.SCHEDULE))
                self.assertEqual(send.call_count, 1)
                self.assertEqual(state["sent"][context.SCHEDULE_KEY]["message_id"], 205)

    def test_november_meeting_replaces_october_strategy_and_december_rate_date(self):
        calendar = ("2026 FOMC Meetings December 8-9 "
                    "2027 FOMC Meetings January 26-27 March 16-17 April 27-28 "
                    "June 8-9 July 27-28 September 14-15 October 26-27 December 7-8 ")
        with (patch.object(futures.v3.base, "fetch", return_value=(calendar, futures.v3.base.FED_CALENDAR)),
              patch.object(futures, "ny_today", return_value=dt.date(2026, 11, 14))):
            dates = futures.official_fomc_dates()
        self.assertIn(dt.date(2026, 12, 9), dates)
        self.assertIn(dt.date(2027, 11, 17), dates)
        self.assertNotIn(dt.date(2027, 10, 27), dates)
        self.assertNotIn(dt.date(2027, 12, 8), dates)

    def test_revised_calendar_is_used_without_duplicate_november(self):
        calendar = ("2026 FOMC Meetings December 8-9 "
                    "2027 FOMC Meetings January 26-27 March 16-17 April 27-28 "
                    "June 8-9 July 27-28 September 14-15 October 26-27 November 16-17 ")
        with (patch.object(futures.v3.base, "fetch", return_value=(calendar, futures.v3.base.FED_CALENDAR)),
              patch.object(futures, "ny_today", return_value=dt.date(2026, 11, 14))):
            dates = futures.official_fomc_dates()
        self.assertEqual(dates.count(dt.date(2027, 11, 17)), 1)
        self.assertNotIn(dt.date(2027, 10, 27), dates)


class ExistingWarshSpeechArchiveFallbackTests(unittest.TestCase):
    def test_archive_fallback_identifies_official_warsh_link(self):
        page = ('<html><a class="speech-item" '
                'href="/newsevents/speech/warsh20260828a.htm">In Our Time</a></html>')
        with patch.object(original_speech, "fetch", return_value=(
            page, "https://www.federalreserve.gov/newsevents/2026-speeches.htm"
        )):
            row = original_speech.latest_warsh_archive_item()
        self.assertIsNotNone(row)
        self.assertEqual(row[2], "https://www.federalreserve.gov/newsevents/speech/warsh20260828a.htm")
        self.assertEqual(row[1], "In Our Time")
        self.assertEqual(row[0].date(), dt.date(2026, 8, 28))

    def test_archive_fallback_does_not_pick_other_speakers(self):
        page = ('<html><a href="/newsevents/speech/waller20261110a.htm">'
                'Economic Outlook</a></html>')
        with patch.object(original_speech, "fetch", return_value=(page, original_speech.SPEECH_ARCHIVE_URL)):
            self.assertIsNone(original_speech.latest_warsh_archive_item())


if __name__ == "__main__":
    unittest.main()
