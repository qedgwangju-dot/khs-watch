import datetime as dt
import urllib.parse
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
                "additional policy tightening must be carefully weighed. "
                "AI related debt will exceed $800 billion, and other obligations "
                "are more than three times the amount of debt.")
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


class WarshClickableReadableAlertsTests(unittest.TestCase):
    def test_bowman_links_and_financing_numbers_are_readable(self):
        body = ("off-balance-sheet liabilities; revenues from AI customers disappoint; "
                "benefit of additional policy tightening; AI debt exceed $800 billion, "
                "long-term commitments more than three times the amount of debt")
        msg = context.speech_message(context.SEEDS[1],
            example_speech("bowman", "November 10, 2026", body))
        self.assertIn("<b>핵심 사실</b>", msg)
        self.assertIn("<b>쉽게 말하면</b>", msg)
        self.assertIn("8,000억달러", msg)
        self.assertIn("1,069조3,600억원", msg)
        self.assertIn("3배", msg)
        self.assertIn('<a href="https://www.federalreserve.gov/newsevents/speech/bowman20261110a.htm">연준 공식 연설</a>', msg)
        self.assertNotIn("연준 공식 원문: https://", msg)
        self.assertLess(len(msg), 3900)

    def test_waller_clickable_links_separate_quote_time_and_current_odds(self):
        body = ("support a 25 basis point increase at the December meeting, "
                "and a 50 basis point hike if core CPI stays high.")
        msg = context.speech_message(context.SEEDS[0],
            example_speech("waller", "November 10, 2026", body))
        self.assertIn("0.25%p", msg)
        self.assertIn("0.50%p", msg)
        self.assertIn("현재 확률 아님", msg)
        self.assertIn("<b>쉽게 말하면</b>", msg)
        self.assertIn('NewsId=07216006645644408', msg)
        self.assertIn("Kind=257&amp;NewsId=", msg)
        self.assertIn(">당시 확률 보도</a>", msg)
        self.assertIn(">BLS 10월 CPI</a>", msg)
        self.assertLess(len(msg), 3900)

    def test_schedule_url_is_link_and_decision_year_is_clear(self):
        raw = ("Federal Reserve announces revised tentative schedule of Federal Open Market "
               "Committee meetings in 2027. January 26-27 March 16-17 April 27-28 "
               "June 8-9 July 27-28 September 14-15 October 26-27 "
               "November 16-17. The October 26-27 meeting will be dedicated to "
               "broad monetary policy strategy issues.")
        msg = context.schedule_message(raw)
        self.assertIn("8회 유지", msg)
        self.assertIn("7회만", msg)
        self.assertIn("2026년 12월 FOMC", msg)
        self.assertIn(">연준 일정 변경 발표</a>", msg)
        self.assertIn(">공식 FOMC 달력</a>", msg)
        self.assertLess(len(msg), 3900)

    def test_unapproved_external_url_rejected(self):
        with self.assertRaises(ValueError):
            context.shortlink("이동", "http://www.federalreserve.gov/fake")
        with self.assertRaises(ValueError):
            context.shortlink("이동", "https://www.federalreserve.gov.evil.net/")

    def test_actual_telegram_api_payload_uses_html_and_edit_id(self):
        calls = []
        def fake_urlopen(req, timeout=0):
            url = req.full_url if hasattr(req, "full_url") else req
            if url.endswith("/getMe"):
                response = {"ok": True, "result": {"username": "verified_test_bot"}}
            else:
                payload = urllib.parse.parse_qs(req.data.decode("utf-8"))
                calls.append((url, payload))
                response = {
                    "ok": True, "result": {"message_id": 147, "chat": {"id": -1001234567890}},
                }
            stream = MagicMock()
            stream.__enter__.return_value = stream
            stream.read.return_value = json.dumps(response).encode("utf-8")
            return stream
        with (patch.object(context, "BOT_TOKEN", "TEST_TOKEN"),
              patch.object(context, "EXPECTED_BOT", "verified_test_bot"),
              patch.object(context, "CHAT_ID", "-1001234567890"),
              patch.object(context.urllib.request, "urlopen", side_effect=fake_urlopen)):
            receipt = context.edit_message(
                147, context.shortlink("연준 공식 연설", context.SEEDS[1]))
        self.assertEqual(receipt["message_id"], 147)
        self.assertTrue(receipt["recipient_verified"])
        self.assertTrue(calls[0][0].endswith("/editMessageText"))
        self.assertEqual(calls[0][1]["parse_mode"], ["HTML"])
        self.assertEqual(calls[0][1]["message_id"], ["147"])
        self.assertIn('<a href="https://www.federalreserve.gov/newsevents/speech/',
                      calls[0][1]["text"][0])

    def test_existing_messages_edited_once_not_resent(self):
        with tempfile.TemporaryDirectory() as p:
            state = {
                "sent": {
                    "speech:bowman:20261110a": {
                        "message_id": 147,
                        "recipient_verified": True,
                        "source": context.SEEDS[1],
                    },
                    "speech:waller:20261110a": {
                        "message_id": 148,
                        "recipient_verified": True,
                        "source": context.SEEDS[0],
                    },
                    context.SCHEDULE_KEY: {
                        "message_id": 149,
                        "recipient_verified": True,
                        "source": context.SCHEDULE,
                    },
                },
                "pending": {}, "skipped": {},
            }
            with (patch.object(context, "STATE_PATH", Path(p)/"state.json"),
                  patch.object(context, "_upgrade_message",
                               side_effect=lambda key, receipt: "<b>갱신 확인</b>") as render,
                  patch.object(context, "edit_message",
                               side_effect=lambda mid, msg: {"message_id":mid,"recipient_verified":True}) as edited,
                  patch.object(context, "send") as sent):
                items = context.upgrade_delivered_messages(state)
                self.assertEqual(len(items), 3)
                self.assertEqual(edited.call_count, 3)
                self.assertEqual(len(state["formatted"]), 3)
                self.assertEqual(context.upgrade_delivered_messages(state), [])
                sent.assert_not_called()
                self.assertEqual(edited.call_count, 3)
                self.assertTrue(all(x["version"] == context.FORMAT_VERSION
                                    for x in state["formatted"].values()))

    def test_future_new_delivery_stores_format_version_with_original_dedup(self):
        with tempfile.TemporaryDirectory() as p:
            state = {"sent": {}, "pending": {}, "skipped": {}}
            with (patch.object(context, "STATE_PATH", Path(p)/"state.json"),
                  patch.object(context, "send", return_value={"message_id":151,"recipient_verified":True}) as sender):
                self.assertTrue(context.deliver(state, "speech:waller:20261116a", "<b>신규</b>", context.SEEDS[0]))
                self.assertEqual(state["formatted"]["speech:waller:20261116a"]["version"],
                                 context.FORMAT_VERSION)
                self.assertFalse(context.deliver(state, "speech:waller:20261116a", "<b>신규</b>", context.SEEDS[0]))
                self.assertEqual(sender.call_count, 1)




class WarshRegionalFedDalyTests(unittest.TestCase):
    OFFICIAL = ("<html><h1>A Conversation with Mary C. Daly at UNLV's 2026 Economic "
                "Forecast</h1>Date Friday, Nov 13, 2026. University of Nevada, "
                "Las Vegas Center for Business and Economic Research. "
                "Mary C. Daly, president and CEO of the San Francisco Fed.</html>")
    REUTERS = ("Nov 13 (Reuters) - San Francisco Fed President Mary Daly said at "
               "the University of Nevada, Las Vegas event she would in all "
               "likelihood raise rates. services inflation excluding housing "
               "was not moving in the correct direction and producers "
               "want to pass on costs to consumers.")

    def test_official_event_date_venue_speaker_required(self):
        self.assertTrue(context.verify_daly_official_event(self.OFFICIAL))
        self.assertFalse(context.verify_daly_official_event(
            self.OFFICIAL.replace("Nov 13, 2026", "Nov 13, 2022")))
        self.assertFalse(context.verify_daly_official_event(
            self.OFFICIAL.replace("Mary C. Daly", "Someone Else")))

    def test_report_requires_quotes_and_specific_venue(self):
        self.assertTrue(context.verify_daly_report(self.REUTERS))
        self.assertFalse(context.verify_daly_report(self.REUTERS.replace(
            "not moving in the correct direction", "moving in the correct direction")))
        self.assertFalse(context.verify_daly_report(self.REUTERS.replace(
            "Nov 13", "Nov 12")))
        self.assertFalse(context.verify_daly_report(self.REUTERS.replace(
            "pass on costs", "absorb costs")))

    def test_official_and_reuters_source_fallback(self):
        def fetch(url):
            if url == context.DALY_OFFICIAL: return self.OFFICIAL
            if url == context.DALY_REUTERS: raise TimeoutError("origin not accessible")
            if url == context.DALY_NEWS_SOURCES[1]: return self.REUTERS
            raise AssertionError("unexpected source "+url)
        with patch.object(context, "fetch_public_event", side_effect=fetch):
            official, report = context.daly_event_sources()
        self.assertEqual(official, context.DALY_OFFICIAL)
        self.assertEqual(report, context.DALY_NEWS_SOURCES[1])

    def test_reuters_quote_missing_does_not_create_fake_event(self):
        with patch.object(context, "fetch_public_event",
                          side_effect=lambda url: self.OFFICIAL if url==context.DALY_OFFICIAL
                          else "<h1>Fed policy</h1>"):
            with self.assertRaisesRegex(RuntimeError, "lack a directly verified Reuters"):
                context.daly_event_sources()

    def test_daly_alert_explains_services_costs_consumption_and_decision(self):
        msg = context.daly_event_message(context.DALY_OFFICIAL,
                                         context.DALY_NEWS_SOURCES[1])
        self.assertIn("주거비 제외 서비스 물가", msg)
        self.assertIn("+0.3%", msg)
        self.assertIn("PCE", msg)
        self.assertIn("1~3개월", msg)
        self.assertIn("확정하지", msg)
        self.assertIn("스탠퍼드", msg)
        self.assertIn('>샌프란시스코 연은 행사</a>', msg)
        self.assertIn('>로이터 현장 보도</a>', msg)
        self.assertIn('>연합인포맥스 기사</a>', msg)
        self.assertLess(len(msg), 3900)

    def test_no_unverified_host(self):
        with self.assertRaises(ValueError):
            context.fetch_public_event("https://frbsf.org.attacker.example/speech")

    def test_same_event_new_key_is_never_resent(self):
        with tempfile.TemporaryDirectory() as p:
            st={"sent":{}, "pending":{}, "skipped":{}}
            with (patch.object(context, "STATE_PATH", Path(p)/"state.json"),
                  patch.object(context, "send", return_value={
                      "message_id": 155, "recipient_verified": True}) as snd):
                self.assertTrue(context.deliver(
                    st, context.DALY_KEY, "msg", context.DALY_OFFICIAL))
                self.assertFalse(context.deliver(
                    st, context.DALY_KEY, "msg", context.DALY_OFFICIAL))
                self.assertEqual(snd.call_count,1)
                self.assertEqual(st["sent"][context.DALY_KEY]["message_id"],155)
                self.assertEqual(st["formatted"][context.DALY_KEY]["version"],
                                 context.FORMAT_VERSION)


    def test_daly_format_upgrade_keeps_original_message_id(self):
        with tempfile.TemporaryDirectory() as p:
            state = {
                "sent": {context.DALY_KEY:{
                    "message_id":155, "recipient_verified":True,
                    "source":context.DALY_OFFICIAL,
                }},
                "pending":{}, "skipped":{}, "formatted":{},
            }
            with (patch.object(context,"STATE_PATH",Path(p)/"state.json"),
                  patch.object(context,"daly_event_sources",return_value=(
                      context.DALY_OFFICIAL,context.DALY_NEWS_SOURCES[1])),
                  patch.object(context,"edit_message",return_value={
                      "message_id":155,"recipient_verified":True}) as edit):
                changed=context.upgrade_delivered_messages(state)
                self.assertEqual(changed,[context.DALY_KEY])
                self.assertEqual(edit.call_count,1)
                self.assertEqual(state["formatted"][context.DALY_KEY]["message_id"],155)
                self.assertEqual(context.upgrade_delivered_messages(state),[])
                self.assertEqual(edit.call_count,1)



if __name__ == "__main__":
    unittest.main()
