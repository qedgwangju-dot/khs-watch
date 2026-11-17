import json
import sys
import tempfile
import unittest
import urllib.error
from io import BytesIO
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import warsh_speech_watch as watch


SCENARIOS = (
    "Productivity and Jobs Task Force. Supercharge idea generation. Structurally to the upside. "
    "Illustrative scenarios, not forecasts. Shared broadly across labor. Stays close to full employment. "
    "Widespread automation. Above levels consistent with full employment. Equity valuations could fall. "
    "Without the productivity gains. Critical infrastructures. Important implications for monetary policy down the road."
)
OTHER = watch.SCENARIOS_LINK.replace("16a", "18a")


class SpeechReceiptsTest(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.addCleanup(patch.stopall)
        patch('builtins.print').start()  # Keep fixture message IDs out of operational logs.
        patch.object(watch, "STATE_PATH", Path(tmp.name) / "speech.json").start()
        patch.object(watch, "EXPECTED_BOT", watch.LEGACY_BOT).start()
        patch.object(watch, "CHAT_ID", "-300").start()
        patch.object(watch, "FORCE_NOTIFY", False).start()
        self.latest = watch.SCENARIOS_LINK
        self.source = SCENARIOS
        self.fetch = patch.object(watch, "fetch", side_effect=self.fetch_source).start()
        self.bot = patch.object(watch, "telegram", side_effect=self.bot_api).start()
        self.parent_username = watch.LEGACY_BOT
        self.send_chat = -300
        self.send_error = None
        self.posts = []

    def fetch_source(self, url):
        if url == watch.RSS_URL:
            return (f"<rss><channel><item><title>Warsh, Opening Remarks</title><link>{self.latest}</link>"
                    f"<pubDate>{watch.LEGACY_PUB_DATE}</pubDate></item></channel></rss>", url)
        return self.source, url

    def bot_api(self, method, fields=None):
        if method == "getMe":
            return {"is_bot": True, "id": 65, "username": watch.LEGACY_BOT}
        if method == "getChat":
            return {"id": -300}
        self.posts.append((method, fields))
        if self.send_error:
            raise self.send_error
        if method == "editMessageText":
            return {"chat": {"id": self.send_chat}, "message_id": fields["message_id"]}
        self.assertEqual(method, "sendMessage")
        data = {"chat": {"id": self.send_chat}, "message_id": 188}
        if "reply_parameters" in fields:
            self.assertEqual(json.loads(fields["reply_parameters"]), {
                "message_id": 151, "quote": watch.SCENARIOS_LINK, "allow_sending_without_reply": False,
            })
            data["reply_to_message"] = {
                "message_id": 151, "chat": {"id": -300}, "text": "원문: " + watch.SCENARIOS_LINK,
                "from": {"is_bot": True, "username": self.parent_username},
            }
        return data

    def legacy(self):
        watch.save_state({"last_link": watch.SCENARIOS_LINK, "last_pub_date": watch.LEGACY_PUB_DATE, "custom": 42})

    def test_verified_reply_saved_and_never_duplicated(self):
        self.legacy()
        watch.main()
        watch.main()
        state = watch.load_state()
        receipt = state["receipts"][watch.SCENARIOS_LINK]
        self.assertEqual(state["custom"], 42)
        self.assertEqual((receipt["message_id"], receipt["reply_to_message_id"]), (188, 151))
        self.assertTrue(receipt["recipient_verified"])
        self.assertFalse(state["pending_sends"])
        self.assertEqual(len(self.posts), 1)
        for word in ("생산성", "자동화", "기대수익", "실현 확률", "12월 금리"):
            self.assertIn(word, self.posts[0][1]["text"])

    def test_first_run_and_repeat_remain_silent(self):
        watch.main()
        watch.main()
        self.assertFalse(self.posts)

    def test_changed_speech_saves_bound_receipt_and_preserves_original(self):
        self.legacy()
        watch.main()
        self.latest = OTHER
        watch.main()
        watch.main()
        receipts = watch.load_state()["receipts"]
        self.assertEqual(set(receipts), {OTHER, watch.SCENARIOS_LINK})
        self.assertTrue(receipts[OTHER]["route_key"])
        self.assertEqual(len(self.posts), 2)
        self.assertNotIn("reply_parameters", self.posts[1][1])

    def test_ambiguous_send_blocks_retry_but_allows_subsequent_speech(self):
        self.legacy()
        self.send_error = TimeoutError("after delivery")
        with self.assertRaises(TimeoutError):
            watch.main()
        self.send_error = None
        with self.assertRaises(RuntimeError):
            watch.main()
        self.assertEqual(len(self.posts), 1)
        self.latest = OTHER
        with self.assertRaises(RuntimeError):
            watch.main()
        self.assertIn(OTHER, watch.load_state()["receipts"])
        self.assertEqual(len(self.posts), 2)

    def test_quote_rejection_never_falls_back_to_standalone_send(self):
        self.legacy()
        self.send_error = watch.TelegramRejected("quote did not match")
        with self.assertRaises(watch.TelegramRejected):
            watch.main()
        self.assertEqual(len(self.posts), 1)
        self.assertFalse(watch.load_state()["pending_sends"])
        self.assertFalse(watch.load_state()["receipts"])

    def test_wrong_original_author_or_wrong_returned_chat_cannot_confirm(self):
        for author, chat in (("other_bot", -300), (watch.LEGACY_BOT, -100)):
            with self.subTest(author=author, chat=chat):
                self.legacy()
                self.parent_username = author
                self.send_chat = chat
                with self.assertRaises(RuntimeError):
                    watch.main()
                self.assertIn(watch.SCENARIOS_LINK, watch.load_state()["pending_sends"])
                self.assertFalse(watch.load_state()["receipts"])

    def test_known_receipt_upgraded_in_place_only_on_same_route(self):
        self.legacy()
        watch.main()
        state = watch.load_state()
        receipt = state["receipts"][watch.SCENARIOS_LINK]
        receipt["version"] = 0
        key = receipt["route_key"]
        receipt["route_key"] = "another"
        watch.save_state(state)
        with self.assertRaises(ValueError):
            watch.main()
        self.assertEqual(len(self.posts), 1)
        receipt["route_key"] = key
        watch.save_state(state)
        watch.main()
        watch.main()
        self.assertEqual([x[0] for x in self.posts], ["sendMessage", "editMessageText"])
        self.assertEqual(self.posts[1][1]["message_id"], 188)

    def test_unconfirmed_or_redirected_official_speech_cannot_send(self):
        self.legacy()
        self.source = "Illustrative scenarios, not forecasts."
        with self.assertRaises(ValueError):
            watch.main()
        self.assertFalse(self.posts)
        with patch.object(watch, "fetch", return_value=(SCENARIOS, OTHER)):
            with self.assertRaises(ValueError):
                watch.speech_message(watch.SCENARIOS_LINK, "", None)
        self.assertFalse(self.posts)

    def test_foreign_source_and_corrupt_baseline_fail_closed(self):
        self.assertFalse(watch.warsh_source(watch.SCENARIOS_LINK.replace(".gov", ".gov.example")))
        watch.STATE_PATH.write_text("{not-json")
        with self.assertRaises(ValueError):
            watch.main()
        self.bot.assert_not_called()

    def test_stale_archive_does_not_roll_back(self):
        watch.save_state({"last_link": OTHER})
        watch.main()
        self.assertEqual(watch.load_state()["last_link"], OTHER)
        self.assertFalse(self.posts)


class TelegramErrorTest(unittest.TestCase):
    def test_already_edited_acknowledgement_does_not_trigger_send(self):
        error = urllib.error.HTTPError("https://example.invalid", 400, "Bad request", {},
            BytesIO(b'{"ok":false,"error_code":400,"description":"Bad Request: message is not modified"}'))
        with patch.object(watch, "TOKEN", "fixture"), patch.object(watch.urllib.request, "urlopen", side_effect=error) as http:
            self.assertEqual(watch.deliver("updated", -300, 188), 188)
            self.assertEqual(http.call_count, 1)


if __name__ == "__main__":
    unittest.main()
