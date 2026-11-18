"""Offline tests for the narrowly authorized edit; no live Telegram requests."""
import copy
import datetime as dt
import io
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock, patch
import urllib.error

from scripts import repair_optics_duplicate_20261118 as repair


class FixedTargetTests(unittest.TestCase):
    def test_original_fixture_matches_the_authorized_production_hashes(self):
        original = repair.DEFAULT_ORIGINAL_PATH.read_text(encoding="utf-8").strip()
        self.assertEqual(repair.delivery.digest(original), "4440df731dcacb74d52eb024f7870db059d38d78ea6bdcc5597edd02e41e5a9c")
        self.assertEqual(repair.delivery.digest(repair.ROUTE_KEY + "|" + original), "9fc3aa5c7e228759a22505ecdffb6c0305238adb2a458c80f572f4394d1edacf")
        self.assertEqual(repair.MESSAGE_ID, 504)
        self.assertEqual(repair.ORIGINAL_SOURCE_SHA, "8cf89a3bd32f794cc8287d94927c7e89904a3ffc")
        self.assertEqual(repair.DEADLINE.isoformat(), "2026-11-19T02:04:19+00:00")
        self.assertLess(len(repair.CORRECTION_TEXT), 4096)


class OneEditTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.ledger_path = self.root / "ledger.json"
        self.output_path = self.root / "audit.json"
        self.other_state = self.root / "unrelated-state.json"
        self.other_state.write_text('{"seen_keys":["untouched"],"message_id":999}')
        self.bot = {"id": 87654321, "is_bot": True, "username": repair.BOT_USERNAME, "first_name": "Bot profile"}
        self.chat = {"id": -123456789, "type": "private", "username": "private_receiver",
                     "first_name": "Private first name", "last_name": "Private last name", "title": "Private title", "linked_chat_id": -987654321}
        self.token = "TEST_SECRET_TOKEN_DO_NOT_LOG"
        self.original = repair.DEFAULT_ORIGINAL_PATH.read_text(encoding="utf-8").strip()
        route = repair.delivery.digest(f"{self.bot['id']}|{repair.BOT_USERNAME}|{self.chat['id']}")
        bundle = repair.delivery.digest(route + "|" + self.original)
        for name, value in (("ROUTE_KEY", route), ("BUNDLE_KEY", bundle)):
            item = patch.object(repair, name, value)
            item.start()
            self.addCleanup(item.stop)
        self.ledger = {"bundles": {bundle: {
            "status": "complete", "state_persisted": True, "route_key": route,
            "bot_username": repair.BOT_USERNAME, "source_sha": repair.ORIGINAL_SOURCE_SHA,
            "part_hashes": [repair.ORIGINAL_PART_HASH], "receipts": {"0": {
                "status": "confirmed", "message_id": 504, "chat_identity_verified": True,
                "source_sha": repair.ORIGINAL_SOURCE_SHA}}}}}
        self.save_ledger()
        environment = patch.dict(os.environ, {"TELEGRAM_BOT_TOKEN": self.token,
            "TELEGRAM_CHAT_ID": str(self.chat["id"]), "GITHUB_EVENT_NAME": "push",
            "GITHUB_REF": "refs/heads/main", "GITHUB_SHA": "a" * 40})
        environment.start()
        self.addCleanup(environment.stop)
        clock = patch.object(repair, "utc_now", return_value=dt.datetime(2026, 11, 18, 3, tzinfo=dt.timezone.utc))
        self.clock = clock.start()
        self.addCleanup(clock.stop)
        git = patch.object(repair.subprocess, "run", return_value=Mock(stdout="a" * 40))
        git.start()
        self.addCleanup(git.stop)

    def save_ledger(self):
        self.ledger_path.write_text(json.dumps(self.ledger))

    @staticmethod
    def response(value):
        return io.BytesIO(json.dumps(value, ensure_ascii=False).encode())

    def reads(self):
        return [self.response({"ok": True, "result": row}) for row in (self.bot, self.chat, self.bot, self.chat)]

    def good_response(self):
        return {"ok": True, "result": {"message_id": 504, "date": 1794967459,
            "edit_date": 1794970800, "chat": self.chat, "from": self.bot, "text": repair.CORRECTION_TEXT}}

    def run_repair(self, response=None, error=None):
        before = self.ledger_path.read_bytes()
        state = self.other_state.read_bytes()
        replies = self.reads() + ([error] if error is not None else [self.response(response or self.good_response())])
        with patch.object(repair.urllib.request, "urlopen", side_effect=replies) as network:
            try:
                result = repair.repair_once(repair.DEFAULT_ORIGINAL_PATH,
                    ledger_path=self.ledger_path, output_path=self.output_path)
            finally:
                self.assertEqual(self.ledger_path.read_bytes(), before)
                self.assertEqual(self.other_state.read_bytes(), state)
                self.network_calls = network.call_args_list
        return result

    def test_exact_existing_message_is_edited_once_without_any_new_send(self):
        result = self.run_repair()
        self.assertEqual(result["status"], "verified_edit")
        self.assertTrue(result["verified_edit"])
        self.assertTrue(result["ledger_unchanged_verified"])
        self.assertEqual(result["original_text"], self.original)
        self.assertEqual(len(self.network_calls), 5)
        methods = [getattr(call.args[0], "full_url", call.args[0]).split("/")[-1].split("?")[0] for call in self.network_calls]
        self.assertEqual(methods, ["getMe", "getChat", "getMe", "getChat", "editMessageText"])
        request = self.network_calls[-1].args[0]
        payload = json.loads(request.data)
        self.assertEqual(payload["message_id"], 504)
        self.assertEqual(payload["chat_id"], self.chat["id"])
        self.assertEqual(payload["text"], repair.CORRECTION_TEXT)
        self.assertNotIn("inline_message_id", payload)
        self.assertNotIn("parse_mode", payload)

    def test_audit_omits_recipient_pii_token_chat_id_and_bot_profile_names(self):
        self.run_repair()
        artifact = self.output_path.read_text()
        for sensitive in (self.token, str(self.chat["id"]), self.chat["username"], self.chat["first_name"],
                          self.chat["last_name"], self.chat["title"], str(self.chat["linked_chat_id"]), self.bot["first_name"]):
            self.assertNotIn(sensitive, artifact)
        saved = json.loads(artifact)
        self.assertEqual(saved["api_response"]["result"]["chat"], {"id": "[redacted]", "type": "private"})
        self.assertEqual(saved["api_response"]["result"]["from"]["username"], repair.BOT_USERNAME)

    def test_not_modified_is_idempotent_but_not_a_verified_edit_receipt(self):
        body = {"ok": False, "error_code": 400, "description": "Bad Request: message is not modified: specified new message content and reply markup are exactly the same"}
        error = urllib.error.HTTPError("https://private/" + self.token, 400, "private", None, self.response(body))
        result = self.run_repair(error=error)
        self.assertEqual(result["status"], "already_applied_not_modified")
        self.assertFalse(result["verified_edit"])
        self.assertEqual(len(self.network_calls), 5)

    def test_timeout_has_no_retry_or_send_fallback_and_keeps_sanitized_audit(self):
        with self.assertRaises(repair.RepairFailure) as error:
            self.run_repair(error=TimeoutError(self.token + str(self.chat["id"])))
        self.assertEqual(error.exception.status, "edit_outcome_unknown")
        self.assertNotIn(self.token, str(error.exception))
        self.assertEqual(len(self.network_calls), 5)
        artifact = json.loads(self.output_path.read_text())
        self.assertEqual(artifact["status"], "edit_outcome_unknown")
        self.assertFalse(artifact["verified_edit"])

    def test_server_error_is_unknown_without_retry(self):
        body = {"ok": False, "error_code": 500, "description": self.token + str(self.chat["id"])}
        error = urllib.error.HTTPError("https://private/" + self.token, 500, "private", None, self.response(body))
        with self.assertRaises(repair.RepairFailure) as failure:
            self.run_repair(error=error)
        self.assertEqual(failure.exception.status, "edit_outcome_unknown")
        self.assertEqual(len(self.network_calls), 5)
        self.assertNotIn(self.token, self.output_path.read_text())

    def test_other_api_rejection_is_not_accepted_as_already_modified(self):
        body = {"ok": False, "error_code": 403, "description": "Forbidden: message is not modified"}
        with self.assertRaises(repair.RepairFailure) as error:
            self.run_repair(response=body)
        self.assertEqual(error.exception.status, "edit_rejected")
        self.assertEqual(len(self.network_calls), 5)

    def test_wrong_message_chat_bot_or_text_is_not_verified(self):
        for field in ("message_id", "chat", "from", "text"):
            with self.subTest(field=field):
                response = copy.deepcopy(self.good_response())
                response["result"][field] = {"message_id": 505, "chat": {"id": -999},
                    "from": {"id": 999, "username": "wrong_bot", "is_bot": True}, "text": "unexpected private text"}[field]
                with self.assertRaises(repair.RepairFailure) as error:
                    self.run_repair(response=response)
                self.assertEqual(error.exception.status, "edit_response_unverified")
                self.assertEqual(len(self.network_calls), 5)
                self.assertNotIn("unexpected private text", self.output_path.read_text())

    def test_inline_boolean_response_is_not_a_verified_message_edit(self):
        with self.assertRaises(repair.RepairFailure) as error:
            self.run_repair(response={"ok": True, "result": True})
        self.assertEqual(error.exception.status, "edit_response_unverified")

    def test_wrong_fixed_ledger_fields_block_before_any_network_request(self):
        original = copy.deepcopy(self.ledger)
        mutations = [lambda e: e.update(source_sha="b" * 40), lambda e: e.update(route_key="wrong"),
            lambda e: e.update(bot_username="wrong_bot"), lambda e: e.update(status="partial"),
            lambda e: e.update(state_persisted=False), lambda e: e.update(part_hashes=["wrong"]),
            lambda e: e["receipts"]["0"].update(message_id=505),
            lambda e: e["receipts"]["0"].update(message_id=True),
            lambda e: e["receipts"]["0"].update(chat_identity_verified=False),
            lambda e: e["receipts"]["0"].update(source_sha="c" * 40)]
        for mutate in mutations:
            self.ledger = copy.deepcopy(original)
            mutate(self.ledger["bundles"][repair.BUNDLE_KEY])
            self.save_ledger()
            before = self.ledger_path.read_bytes()
            with patch.object(repair.urllib.request, "urlopen") as network:
                with self.assertRaises(repair.RepairFailure):
                    repair.repair_once(repair.DEFAULT_ORIGINAL_PATH, ledger_path=self.ledger_path, output_path=self.output_path)
                network.assert_not_called()
            self.assertEqual(before, self.ledger_path.read_bytes())

    def test_original_body_tampering_blocks_before_any_request(self):
        original = self.root / "changed.html"
        original.write_text(self.original + "changed")
        with patch.object(repair.urllib.request, "urlopen") as network:
            with self.assertRaisesRegex(repair.RepairFailure, "original_message_hash_mismatch"):
                repair.repair_once(original, ledger_path=self.ledger_path, output_path=self.output_path)
            network.assert_not_called()

    def test_expired_authorization_blocks_before_route_lookup(self):
        self.clock.return_value = repair.DEADLINE + dt.timedelta(seconds=1)
        with patch.object(repair.urllib.request, "urlopen") as network:
            with self.assertRaisesRegex(repair.RepairFailure, "window_closed"):
                repair.repair_once(repair.DEFAULT_ORIGINAL_PATH, ledger_path=self.ledger_path, output_path=self.output_path)
            network.assert_not_called()

    def test_deadline_is_rechecked_after_read_only_route_verification(self):
        before, after = repair.DEADLINE - dt.timedelta(seconds=1), repair.DEADLINE + dt.timedelta(seconds=1)
        self.clock.side_effect = [before, before, after, after]
        with self.assertRaisesRegex(repair.RepairFailure, "window_closed"):
            self.run_repair()
        self.assertEqual(len(self.network_calls), 4)

    def test_wrong_live_bot_or_route_never_reaches_edit(self):
        self.bot["username"] = "wrong_bot"
        with self.assertRaisesRegex(repair.RepairFailure, "route_verification_failed"):
            self.run_repair()
        self.assertEqual(len(self.network_calls), 1)

    def test_wrong_live_numeric_route_hash_never_reaches_edit(self):
        self.chat["id"] -= 1
        with self.assertRaises(repair.RepairFailure):
            self.run_repair()
        self.assertLess(len(self.network_calls), 5)

    def test_non_main_or_non_push_run_is_blocked(self):
        with patch.dict(os.environ, {"GITHUB_EVENT_NAME": "workflow_dispatch"}), patch.object(repair.urllib.request, "urlopen") as network:
            with self.assertRaisesRegex(repair.RepairFailure, "authorized_main_push"):
                repair.repair_once(repair.DEFAULT_ORIGINAL_PATH, ledger_path=self.ledger_path, output_path=self.output_path)
            network.assert_not_called()

    def test_code_checkout_must_match_requested_push_sha(self):
        with patch.dict(os.environ, {"GITHUB_SHA": "b" * 40}), patch.object(repair.urllib.request, "urlopen") as network:
            with self.assertRaisesRegex(repair.RepairFailure, "revision_mismatch"):
                repair.repair_once(repair.DEFAULT_ORIGINAL_PATH, ledger_path=self.ledger_path, output_path=self.output_path)
            network.assert_not_called()

    def test_audit_write_failure_stops_before_edit_and_sanitizes_exception(self):
        with patch.object(repair.delivery, "atomic_json", side_effect=OSError(self.token)):
            with self.assertRaises(repair.RepairFailure) as error:
                self.run_repair()
        self.assertEqual(len(self.network_calls), 4)
        self.assertEqual(str(error.exception), "correction_audit_write_failed")


if __name__ == "__main__":
    unittest.main()
