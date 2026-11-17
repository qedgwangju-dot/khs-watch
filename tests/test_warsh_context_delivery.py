import datetime as dt
import io
import unittest
import urllib.error
from unittest.mock import MagicMock, patch

import warsh_fed_board_context_watch as context


class ContextDeliveryTests(unittest.TestCase):
    def setUp(self):
        self.state = {"sent": {}, "pending": {}}

    def test_minutes_wait_for_release_and_reuse_same_receipt(self):
        with (patch.object(context, "rba_minutes_message", return_value="minutes") as render,
              patch.object(context, "save_state"),
              patch.object(context, "send", return_value={"message_id": 200, "recipient_verified": True}) as send):
            self.assertFalse(context.check_rba_minutes(self.state, context.RBA_RELEASED_AT - dt.timedelta(seconds=1)))
            self.assertTrue(context.check_rba_minutes(self.state, context.RBA_RELEASED_AT))
            self.assertFalse(context.check_rba_minutes(self.state, context.RBA_RELEASED_AT))
        render.assert_called_once_with(context.fetch_rba_minutes)
        send.assert_called_once_with("minutes")
        self.assertEqual(self.state["sent"][context.RBA_KEY]["source"], context.RBA_MINUTES_URL)

    def test_minutes_reject_redirects_and_partial_sources_without_marking_sent(self):
        response = MagicMock()
        response.__enter__.return_value.geturl.return_value = "https://www.rba.gov.au/"
        with (patch.object(context.urllib.request, "urlopen", return_value=response),
              patch.object(context, "send") as send):
            with self.assertRaisesRegex(RuntimeError, "redirect"):
                context.check_rba_minutes(self.state, context.RBA_RELEASED_AT)
        self.assertEqual(self.state, {"sent": {}, "pending": {}})
        send.assert_not_called()

    def test_confirmed_rejection_and_failed_preflight_can_be_retried(self):
        identity = MagicMock()
        identity.__enter__.return_value.read.return_value = b'{"ok":true,"result":{"username":"test_bot"}}'
        rejected = urllib.error.HTTPError("https://example.org", 429, "Too Many Requests", {},
                                          io.BytesIO(b'{"ok":false,"error_code":429}'))
        with (patch.object(context, "BOT_TOKEN", "test"),
              patch.object(context, "CHAT_ID", "100"),
              patch.object(context, "EXPECTED_BOT", "test_bot"),
              patch.object(context, "save_state"),
              patch.object(context.urllib.request, "urlopen", side_effect=[TimeoutError(), identity, rejected])):
            for _ in range(2):
                with self.assertRaises(context.TelegramNotSent):
                    context.deliver(self.state, context.RBA_KEY, "minutes", context.RBA_MINUTES_URL)
                self.assertEqual(self.state["pending"], {})
                self.assertEqual(self.state["sent"], {})


if __name__ == "__main__":
    unittest.main()
