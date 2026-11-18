"""Fault-injected delivery tests; no Telegram requests or operational files."""
import copy
import datetime as dt
import io
import json
import os
from pathlib import Path
import sys
import re
import tempfile
import unittest
from unittest.mock import Mock, patch
import urllib.error
import xml.etree.ElementTree as ET

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import ai_networking_optics_delivery as delivery


class DeliveryTests(unittest.TestCase):
    def setUp(self):
        self.ledger = {"version": 1, "bundles": {}}
        self.snapshots = []
        self.pending = {"seen_keys": ["new"], "last_checked_kst": "2026-11-18T08:00:00+09:00"}
        self.ancestor = {"seen_keys": ["old"], "last_checked_kst": "2026-11-18T07:00:00+09:00"}

    def checkpoint(self, summary):
        self.snapshots.append((copy.deepcopy(self.ledger), copy.deepcopy(summary)))

    def call(self, send, text="<b>" + "가" * 4000 + "</b>", **kwargs):
        return delivery.deliver_bundle(text=text, pending_state=kwargs.pop("pending_state", self.pending),
            ledger=self.ledger, route_key=kwargs.pop("route_key", "route-hash"),
            bot_username="existing_bot", source_sha="a" * 40, send=send,
            checkpoint=kwargs.pop("checkpoint", self.checkpoint),
            state_ancestor=kwargs.pop("state_ancestor", self.ancestor), **kwargs)

    def test_partial_rejection_then_resume_sends_only_unconfirmed_part(self):
        sender = Mock(side_effect=[101, delivery.DefinitiveRejection("rate limit")])
        with self.assertRaises(delivery.DefinitiveRejection):
            self.call(sender)
        saved = copy.deepcopy(self.snapshots[-1][0])
        entry = next(iter(saved["bundles"].values()))
        self.assertEqual(entry["receipts"]["0"]["message_id"], 101)
        self.assertEqual(entry["receipts"]["1"]["status"], "rejected")
        self.assertFalse(entry["state_persisted"])
        self.ledger = saved  # A fresh process restores the durable checkpoint.
        resumed = Mock(return_value=202)
        receipt, pending = self.call(resumed)
        self.assertEqual(resumed.call_count, 1)
        self.assertEqual(receipt["message_ids"], [101, 202])
        self.assertEqual(pending, self.pending)

    def test_timeout_is_held_even_if_next_report_changes(self):
        with self.assertRaises(delivery.AmbiguousDelivery):
            self.call(Mock(side_effect=[101, TimeoutError("private token must not escape")]))
        self.ledger = copy.deepcopy(self.snapshots[-1][0])
        sender = Mock()
        with self.assertRaisesRegex(delivery.AmbiguousDelivery, "automatic resend held"):
            self.call(sender, text="Completely different new report")
        sender.assert_not_called()

    def test_checkpoint_before_http_failure_stops_send(self):
        sender = Mock(return_value=101)
        def fail(summary):
            if summary["status"] == "in_flight":
                raise OSError("disk unavailable")
            self.checkpoint(summary)
        with self.assertRaises(OSError):
            self.call(sender, checkpoint=fail)
        sender.assert_not_called()

    def test_confirmed_checkpoint_failure_restores_unknown_marker(self):
        sender = Mock(return_value=101)
        def fail(summary):
            if summary["status"] == "partial":
                raise OSError("disk unavailable")
            self.checkpoint(summary)
        with self.assertRaises(OSError):
            self.call(sender, checkpoint=fail)
        self.assertEqual(sender.call_count, 1)
        self.ledger = copy.deepcopy(self.snapshots[-1][0])
        blocked = Mock()
        with self.assertRaises(delivery.AmbiguousDelivery):
            self.call(blocked)
        blocked.assert_not_called()

    def test_complete_receipt_replay_does_not_send_again(self):
        original, _ = self.call(Mock(side_effect=[101, 102]))
        sender = Mock()
        repeated, _ = self.call(sender)
        sender.assert_not_called()
        self.assertEqual(original["message_ids"], repeated["message_ids"])

    def test_resume_pins_original_text_and_event_state(self):
        with self.assertRaises(delivery.DefinitiveRejection):
            self.call(Mock(side_effect=[101, delivery.DefinitiveRejection("rejected")]))
        old_second = next(iter(self.ledger["bundles"].values()))["parts"][1]
        sender = Mock(return_value=202)
        _, pinned = self.call(sender, text="<broken new report", pending_state={"seen_keys": ["not delivered"]})
        sender.assert_called_once_with(old_second)
        self.assertEqual(pinned, self.pending)

    def test_route_receipts_are_not_shared(self):
        self.call(Mock(return_value=101), text="same text")
        sender = Mock(return_value=202)
        receipt, _ = self.call(sender, text="same text", route_key="different-route")
        sender.assert_called_once()
        self.assertEqual(receipt["message_ids"], [202])
        self.assertEqual(len(self.ledger["bundles"]), 2)

    def test_invalid_message_id_is_ambiguous_and_never_success(self):
        for value in (True, 0, -1, "123", None):
            with self.subTest(value=value):
                self.ledger = {"bundles": {}}
                with self.assertRaises(delivery.AmbiguousDelivery):
                    self.call(Mock(return_value=value), text="one part")
                self.assertEqual(next(iter(self.ledger["bundles"].values()))["status"], "ambiguous")

    def test_original_state_is_pinned_and_missing_ancestor_holds_resume(self):
        with self.assertRaises(delivery.DefinitiveRejection):
            self.call(Mock(side_effect=[101, delivery.DefinitiveRejection("rejected")]))
        entry = next(iter(self.ledger["bundles"].values()))
        original = copy.deepcopy(self.ancestor)
        self.ancestor["seen_keys"].append("later change")
        self.assertEqual(entry["state_ancestor"], original)
        self.assertEqual(entry["state_ancestor_sha256"], delivery.digest(original))
        entry.pop("state_ancestor")  # Legacy unfinished bundle without its baseline.
        saved = copy.deepcopy(self.ledger)
        sender = Mock()
        with self.assertRaisesRegex(RuntimeError, "original watch state"):
            self.call(sender)
        sender.assert_not_called()
        self.assertEqual(self.ledger, saved)
        self.assertEqual(entry["receipts"]["0"]["message_id"], 101)

    def test_tampered_original_state_holds_before_resuming_send(self):
        with self.assertRaises(delivery.DefinitiveRejection):
            self.call(Mock(side_effect=[101, delivery.DefinitiveRejection("rejected")]))
        next(iter(self.ledger["bundles"].values()))["state_ancestor"]["seen_keys"].append("tampered")
        sender = Mock()
        with self.assertRaisesRegex(RuntimeError, "original watch state"):
            self.call(sender)
        sender.assert_not_called()

    def test_html_split_preserves_tags_entities_and_utf16_bounds(self):
        source = '<b>' + ('한국😀 &amp; &#60;' * 400) + '</b>\n<a href="https://example.test/">' + ('링크' * 2000) + '</a>'
        parts = delivery.split_html(source)
        self.assertGreater(len(parts), 2)
        rendered = []
        for part in parts:
            self.assertLessEqual(len(part.encode("utf-16-le")) // 2, 3800)
            rendered.append("".join(ET.fromstring("<root>" + part + "</root>").itertext()))
        expected = "".join(ET.fromstring("<root>" + source + "</root>").itertext())
        self.assertEqual("".join(rendered), expected)

    def test_invalid_html_rejected_before_any_send(self):
        sender = Mock()
        with self.assertRaises(ValueError):
            self.call(sender, text="<b>unclosed")
        sender.assert_not_called()

    def test_merge_never_downgrades_confirmed_or_erases_history(self):
        self.call(Mock(return_value=101), text="one part")
        confirmed = copy.deepcopy(self.ledger)
        key = next(iter(confirmed["bundles"]))
        partial = copy.deepcopy(confirmed)
        partial["bundles"][key]["receipts"]["0"] = {"status": "in_flight"}
        confirmed["bundles"]["old"] = {"status": "complete", "state_persisted": True}
        merged = delivery.merge_ledgers(confirmed, partial)
        self.assertEqual(merged["bundles"][key]["receipts"]["0"]["message_id"], 101)
        self.assertIn("old", merged["bundles"])

    def test_merge_conflicting_confirmations_fails_visibly(self):
        self.call(Mock(return_value=101), text="one part")
        conflict = copy.deepcopy(self.ledger)
        next(iter(conflict["bundles"].values()))["receipts"]["0"]["message_id"] = 999
        with self.assertRaisesRegex(RuntimeError, "Conflicting confirmed"):
            delivery.merge_ledgers(self.ledger, conflict)


class VerifiedRouteTests(unittest.TestCase):
    @staticmethod
    def response(value):
        return io.BytesIO(json.dumps(value).encode())

    def route_responses(self):
        return [self.response({"ok": True, "result": {"id": 12, "username": "existing_bot"}}),
                self.response({"ok": True, "result": {"id": -99, "username": "existing_channel"}})]

    def test_exact_bot_chat_and_returned_chat_verified(self):
        responses = self.route_responses() + [self.response({"ok": True, "result": {"message_id": 27, "chat": {"id": -99}}})]
        with patch.object(delivery.urllib.request, "urlopen", side_effect=responses) as request:
            key, bot, send = delivery.verified_sender("test-token", "-99", "existing_bot")
            self.assertEqual(send("test"), 27)
            self.assertEqual(bot, "existing_bot")
            self.assertEqual(len(key), 64)
            self.assertNotIn("-99", key)
            self.assertEqual(request.call_count, 3)

    def test_wrong_bot_stops_before_get_chat_or_send(self):
        response = self.response({"ok": True, "result": {"id": 12, "username": "wrong_bot"}})
        with patch.object(delivery.urllib.request, "urlopen", return_value=response) as request:
            with self.assertRaisesRegex(RuntimeError, "bot identity"):
                delivery.verified_sender("test-token", "-99", "existing_bot")
            self.assertEqual(request.call_count, 1)

    def test_wrong_configured_chat_stops_before_send(self):
        with patch.object(delivery.urllib.request, "urlopen", side_effect=self.route_responses()) as request:
            with self.assertRaisesRegex(RuntimeError, "chat identity"):
                delivery.verified_sender("test-token", "-98", "existing_bot")
            self.assertEqual(request.call_count, 2)

    def test_response_timeout_has_no_blind_retry_or_secret_in_error(self):
        with patch.object(delivery.urllib.request, "urlopen", side_effect=self.route_responses() + [TimeoutError("test-token -99")]) as request:
            _, _, send = delivery.verified_sender("test-token", "-99", "existing_bot")
            with self.assertRaises(delivery.AmbiguousDelivery) as error:
                send("test")
            self.assertNotIn("test-token", str(error.exception))
            self.assertNotIn("-99", str(error.exception))
            self.assertEqual(request.call_count, 3)

    def test_http_rejection_and_server_uncertainty_are_different(self):
        for status, error_type in ((429, delivery.DefinitiveRejection), (500, delivery.AmbiguousDelivery)):
            with self.subTest(status=status):
                error = urllib.error.HTTPError("https://private/test-token", status, "private", None, None)
                with patch.object(delivery.urllib.request, "urlopen", side_effect=self.route_responses() + [error]):
                    _, _, send = delivery.verified_sender("test-token", "-99", "existing_bot")
                    with self.assertRaises(error_type):
                        send("test")

    def test_wrong_receipt_destination_is_held(self):
        wrong = self.response({"ok": True, "result": {"message_id": 27, "chat": {"id": -98}}})
        with patch.object(delivery.urllib.request, "urlopen", side_effect=self.route_responses() + [wrong]):
            _, _, send = delivery.verified_sender("test-token", "-99", "existing_bot")
            with self.assertRaises(delivery.AmbiguousDelivery):
                send("test")

    def test_read_only_route_command_never_invokes_send_message(self):
        environment = {"TELEGRAM_BOT_TOKEN": "fake-token", "TELEGRAM_CHAT_ID": "-99", "EXPECTED_TELEGRAM_BOT_USERNAME": "existing_bot"}
        with patch.dict(os.environ, environment), patch.object(delivery.urllib.request, "urlopen", side_effect=self.route_responses()) as request:
            delivery.verify_route_command()
            self.assertEqual(request.call_count, 2)
            self.assertTrue(all("sendMessage" not in str(call.args[0]) for call in request.call_args_list))

    def test_boolean_chat_identifier_cannot_match_numeric_destination(self):
        replies = [self.response({"ok": True, "result": {"id": 12, "username": "existing_bot"}}),
            self.response({"ok": True, "result": {"id": 1}}),
            self.response({"ok": True, "result": {"message_id": 27, "chat": {"id": True}}})]
        with patch.object(delivery.urllib.request, "urlopen", side_effect=replies):
            _, _, send = delivery.verified_sender("test-token", "1", "existing_bot")
            with self.assertRaises(delivery.AmbiguousDelivery):
                send("test")


class PersistenceTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        for name in ("STATE_PATH", "LEDGER_PATH", "ALERT_PATH", "PENDING_PATH", "CONFIRMED_PATH", "PARTIAL_PATH", "DELIVERED_PENDING_PATH", "GUARD_PATH", "STATUS_PATH"):
            original = getattr(delivery, name)
            patcher = patch.object(delivery, name, Path(self.temp.name) / original.name)
            patcher.start()
            self.addCleanup(patcher.stop)
        environment = patch.dict(os.environ, {"GITHUB_EVENT_NAME": "schedule"})
        environment.start()
        self.addCleanup(environment.stop)
        self.old = {"seen_keys": ["old", "false-positive"], "seen_story_records": [{"title": "old incorrect record"}],
            "last_checked_kst": "2026-11-18T07:00:00+09:00", "last_successful_delivery_kst": "2026-11-17T08:00:00+09:00",
            "telegram_message_ids": [17], "bot_username": "existing_bot", "telegram_chat_identity_verified": True}
        delivery.atomic_json(delivery.STATE_PATH, self.old)

    def complete(self):
        ledger = {"bundles": {}}
        pending = {"seen_keys": ["new", "old"], "seen_story_records": [], "last_checked_kst": "2026-11-18T08:00:00+09:00"}
        receipt, pinned = delivery.deliver_bundle(text="complete", pending_state=pending, ledger=ledger,
            route_key="route", bot_username="existing_bot", source_sha="a" * 40,
            send=Mock(return_value=27), checkpoint=lambda _: None, state_ancestor=self.old)
        for path, value in ((delivery.LEDGER_PATH, ledger), (delivery.DELIVERED_PENDING_PATH, pinned), (delivery.CONFIRMED_PATH, receipt)):
            delivery.atomic_json(path, value)
        return ledger, pending, receipt

    def test_partial_does_not_advance_seen_or_normal_receipt(self):
        delivery.ALERT_PATH.write_text("partial report")
        delivery.atomic_json(delivery.PENDING_PATH, {"seen_keys": ["undelivered"]})
        delivery.atomic_json(delivery.LEDGER_PATH, {"bundles": {"partial": {"state_persisted": False}}})
        delivery.persist_state()
        self.assertEqual(delivery.read_json(delivery.STATE_PATH), self.old)

    def test_only_bound_complete_receipt_promotes_its_pinned_state(self):
        _, pending, receipt = self.complete()
        delivery.atomic_json(delivery.PENDING_PATH, {"seen_keys": ["fresh not yet delivered"]})
        delivery.persist_state()
        result = delivery.read_json(delivery.STATE_PATH)
        self.assertEqual(result["seen_keys"], pending["seen_keys"])
        self.assertEqual(result["seen_story_records"], [])  # Do not undo producer cleanup.
        self.assertEqual(result["telegram_message_ids"], [27])
        stored = delivery.read_json(delivery.LEDGER_PATH)["bundles"][receipt["bundle_key"]]
        self.assertTrue(stored["state_persisted"])
        self.assertNotIn("parts", stored)
        self.assertEqual(stored["receipts"]["0"]["message_id"], 27)

    def test_corrupt_pending_hash_fails_without_advancing_state(self):
        self.complete()
        delivery.atomic_json(delivery.DELIVERED_PENDING_PATH, {"seen_keys": ["tampered"]})
        with self.assertRaisesRegex(RuntimeError, "not bound"):
            delivery.persist_state()
        self.assertEqual(delivery.read_json(delivery.STATE_PATH), self.old)

    def test_confirmed_legacy_bundle_without_ancestor_preserves_state_and_receipts(self):
        ledger, _, receipt = self.complete()
        ledger["bundles"][receipt["bundle_key"]].pop("state_ancestor")
        delivery.atomic_json(delivery.LEDGER_PATH, ledger)
        with self.assertRaisesRegex(RuntimeError, "original watch state"):
            delivery.persist_state()
        self.assertEqual(delivery.read_json(delivery.STATE_PATH), self.old)
        self.assertEqual(delivery.read_json(delivery.LEDGER_PATH), ledger)
        self.assertEqual(delivery.read_json(delivery.CONFIRMED_PATH), receipt)

    def test_resumed_pinned_state_preserves_concurrent_additions_and_cleanup_through_commit(self):
        def arrays(labels):
            return {"seen_keys": list(labels), "seen_story_keys": [label + "-story" for label in labels],
                "seen_story_records": [{"title": label} for label in labels]}
        ancestor = {**self.old, **arrays(["existing", "removed-false-positive"])}
        pinned = {**ancestor, **arrays(["new-delivered", "existing", "removed-false-positive"]),
            "last_checked_kst": "2026-11-18T08:00:00+09:00"}
        current = {**ancestor, **arrays(["existing", "concurrent-good"]),
            "last_checked_kst": "2026-11-18T09:00:00+09:00"}
        ledger = {"bundles": {}}
        text = "<b>" + "가" * 4000 + "</b>"
        common = dict(ledger=ledger, route_key="route", bot_username="existing_bot", source_sha="a" * 40,
            checkpoint=lambda _: delivery.atomic_json(delivery.LEDGER_PATH, ledger))
        with self.assertRaises(delivery.DefinitiveRejection):
            delivery.deliver_bundle(text=text, pending_state=pinned, state_ancestor=ancestor,
                send=Mock(side_effect=[101, delivery.DefinitiveRejection("rejected")]), **common)
        delivery.atomic_json(delivery.STATE_PATH, current)
        fresh_pending = {**current, **arrays(["different-undelivered", "existing", "concurrent-good"])}
        sender = Mock(return_value=202)
        receipt, confirmed_pending = delivery.deliver_bundle(text="new unrelated report", pending_state=fresh_pending,
            state_ancestor=current, send=sender, **common)
        sender.assert_called_once()
        self.assertEqual(confirmed_pending, pinned)
        self.assertEqual(receipt["state_ancestor_sha256"], delivery.digest(ancestor))
        delivery.atomic_json(delivery.DELIVERED_PENDING_PATH, confirmed_pending)
        delivery.atomic_json(delivery.CONFIRMED_PATH, receipt)
        delivery.persist_state()
        result = delivery.read_json(delivery.STATE_PATH)
        expected = arrays(["new-delivered", "existing", "concurrent-good"])
        for key, value in expected.items():
            self.assertEqual(result[key], value, key)
        self.assertEqual(result["last_checked_kst"], current["last_checked_kst"])

        # Exercise the actual subsequent workflow commit helper as well.
        snapshots = Path(self.temp.name) / "snapshots"
        snapshots.mkdir()
        delivery.atomic_json(snapshots / delivery.STATE_PATH.name, result)
        delivery.atomic_json(snapshots / "base-state.json", current)
        delivery.atomic_json(snapshots / delivery.LEDGER_PATH.name, delivery.read_json(delivery.LEDGER_PATH))
        remote = {**current, **arrays(["existing", "concurrent-good", "concurrent-newer"]),
            "last_checked_kst": "2026-11-18T10:00:00+09:00"}
        delivery.atomic_json(delivery.STATE_PATH, remote)
        delivery.merge_commit(snapshots)
        committed = delivery.read_json(delivery.STATE_PATH)
        for key, value in arrays(["new-delivered", "existing", "concurrent-good", "concurrent-newer"]).items():
            self.assertEqual(committed[key], value, key)

    def test_persisted_exact_payload_replay_neither_sends_nor_reapplies_new_pending(self):
        _, _, first = self.complete()
        delivery.persist_state()
        current = delivery.read_json(delivery.STATE_PATH)
        current["seen_keys"].append("concurrent-good")
        delivery.atomic_json(delivery.STATE_PATH, current)
        ledger = delivery.read_json(delivery.LEDGER_PATH)
        entry = ledger["bundles"][first["bundle_key"]]
        self.assertNotIn("state_ancestor", entry)
        sender = Mock()
        receipt, pending = delivery.deliver_bundle(text="complete", pending_state={"seen_keys": ["unconfirmed-new", "removed-false-positive"]},
            ledger=ledger, state_ancestor=current, route_key="route", bot_username="existing_bot",
            source_sha="b" * 40, send=sender, checkpoint=lambda _: None)
        sender.assert_not_called()
        self.assertTrue(receipt["state_already_persisted"])
        delivery.atomic_json(delivery.CONFIRMED_PATH, receipt)
        delivery.atomic_json(delivery.DELIVERED_PENDING_PATH, pending)
        delivery.persist_state()
        self.assertEqual(delivery.read_json(delivery.STATE_PATH), current)
        self.assertEqual(delivery.read_json(delivery.LEDGER_PATH), ledger)

    def test_silent_baseline_keeps_prior_normal_receipt(self):
        delivery.atomic_json(delivery.PENDING_PATH, {"seen_keys": ["old"], "last_checked_kst": "2026-11-18T08:00:00+09:00"})
        delivery.persist_state()
        result = delivery.read_json(delivery.STATE_PATH)
        self.assertEqual(result["telegram_message_ids"], [17])
        self.assertEqual(result["seen_keys"], ["old"])

    def test_three_way_commit_merge_keeps_remote_additions_and_cleanup(self):
        ancestor = {"seen_keys": ["old", "removed"], "seen_story_records": [{"title": "bad"}]}
        local = {"seen_keys": ["local", "old"], "seen_story_records": [], "last_checked_kst": "2026-11-18T08:00:00+09:00"}
        remote = {"seen_keys": ["remote", "old", "removed"], "seen_story_records": [{"title": "bad"}],
            "last_checked_kst": "2026-11-18T09:00:00+09:00", "telegram_message_ids": [30],
            "last_successful_delivery_kst": "2026-11-18T09:00:00+09:00"}
        result = delivery.merge_watch_state(remote, local, ancestor)
        self.assertEqual(set(result["seen_keys"]), {"local", "remote", "old"})
        self.assertEqual(result["seen_story_records"], [])
        self.assertEqual(result["telegram_message_ids"], [30])

    def test_push_is_validation_only_before_network_or_state_change(self):
        with patch.dict(os.environ, {"GITHUB_EVENT_NAME": "push"}), patch.object(delivery, "verified_sender") as verify:
            with self.assertRaises(RuntimeError):
                delivery.send_command()
            with self.assertRaises(RuntimeError):
                delivery.persist_state()
            verify.assert_not_called()
        self.assertEqual(delivery.read_json(delivery.STATE_PATH), self.old)

    def test_sender_command_requires_current_guard_before_route_request(self):
        delivery.ALERT_PATH.write_text("alert")
        delivery.atomic_json(delivery.PENDING_PATH, {"seen_keys": ["new"]})
        environment = {"TELEGRAM_BOT_TOKEN": "fake-token", "TELEGRAM_CHAT_ID": "-99", "EXPECTED_TELEGRAM_BOT_USERNAME": "existing_bot", "GITHUB_RUN_ID": "999"}
        with patch.dict(os.environ, environment), patch.object(delivery.subprocess, "run", return_value=Mock(stdout="a" * 40)), patch.object(delivery, "verified_sender") as verify:
            with self.assertRaises(RuntimeError):
                delivery.send_command()
            verify.assert_not_called()

    def test_sender_and_persistence_commands_preserve_actual_checkpoint(self):
        delivery.ALERT_PATH.write_text("<b>" + "가" * 4000 + "</b>")
        delivery.atomic_json(delivery.PENDING_PATH, {"seen_keys": ["new"], "last_checked_kst": "2026-11-18T08:00:00+09:00"})
        delivery.atomic_json(delivery.GUARD_PATH, {"status": "verified", "source_sha": "a" * 40, "run_id": "999", "run_attempt": "1"})
        environment = {"TELEGRAM_BOT_TOKEN": "fake-token", "TELEGRAM_CHAT_ID": "-99", "EXPECTED_TELEGRAM_BOT_USERNAME": "existing_bot", "GITHUB_RUN_ID": "999", "GITHUB_RUN_ATTEMPT": "1"}
        send = Mock(side_effect=[101, delivery.DefinitiveRejection("rejected")])
        with patch.dict(os.environ, environment), patch.object(delivery.subprocess, "run", return_value=Mock(stdout="a" * 40)), patch.object(delivery, "verified_sender", return_value=("route", "existing_bot", send)):
            with self.assertRaises(delivery.DefinitiveRejection):
                delivery.send_command()
            delivery.persist_state()
            self.assertEqual(delivery.read_json(delivery.STATE_PATH), self.old)
            saved = delivery.read_json(delivery.LEDGER_PATH)
            self.assertEqual(next(iter(saved["bundles"].values()))["receipts"]["0"]["message_id"], 101)
            send.side_effect = None
            send.return_value = 202
            send.reset_mock()
            delivery.send_command()
            send.assert_called_once()
            delivery.persist_state()
        self.assertEqual(delivery.read_json(delivery.STATE_PATH)["telegram_message_ids"], [101, 202])

    def test_unresolved_persistence_hold_does_not_advance_silent_baseline(self):
        delivery.atomic_json(delivery.PENDING_PATH, {"seen_keys": ["new"]})
        delivery.atomic_json(delivery.LEDGER_PATH, {"bundles": {}, "recovery_holds": {"1:1": {"status": "unresolved"}}})
        delivery.persist_state()
        self.assertEqual(delivery.read_json(delivery.STATE_PATH), self.old)

    def test_guard_api_failure_holds_without_creating_success_file(self):
        environment = {"GITHUB_REPOSITORY": "owner/repo", "GITHUB_RUN_ID": "999", "GITHUB_TOKEN": "private-token"}
        with patch.dict(os.environ, environment), patch.object(delivery.urllib.request, "urlopen", side_effect=TimeoutError("private-token")):
            with self.assertRaisesRegex(RuntimeError, "history lookup failed") as error:
                delivery.guard_command()
            self.assertNotIn("private-token", str(error.exception))
        self.assertFalse(delivery.GUARD_PATH.exists())

    def test_guard_command_binds_success_to_actual_code_and_run_attempt(self):
        current = HistoryGuardTests.run_record(999, 15, status="in_progress")
        replies = [io.BytesIO(json.dumps(current).encode()), io.BytesIO(b'{"workflow_runs": []}')]
        environment = {"GITHUB_REPOSITORY": "owner/repo", "GITHUB_RUN_ID": "999", "GITHUB_RUN_ATTEMPT": "1", "GITHUB_TOKEN": "private-token"}
        with patch.dict(os.environ, environment), patch.object(delivery.urllib.request, "urlopen", side_effect=replies) as get, patch.object(delivery.subprocess, "run", return_value=Mock(stdout="a" * 40)):
            delivery.guard_command()
            self.assertEqual(get.call_count, 2)
        verified = delivery.read_json(delivery.GUARD_PATH)
        self.assertEqual((verified["run_id"], verified["run_attempt"], verified["source_sha"]), ("999", "1", "a" * 40))
        self.assertEqual(verified["status"], "verified")

    def test_freshness_command_outputs_skip_without_touching_state(self):
        event_file = Path(self.temp.name) / "event.json"
        event_file.write_text(json.dumps(FreshnessGateTests.event()))
        output = Path(self.temp.name) / "outputs.txt"
        now = dt.datetime.now(dt.timezone.utc)
        updated_old = {**self.old, "last_checked_kst": (now - dt.timedelta(minutes=20)).isoformat()}
        delivery.atomic_json(delivery.STATE_PATH, updated_old)
        environment = {"GITHUB_EVENT_NAME": "workflow_run", "GITHUB_EVENT_PATH": str(event_file), "GITHUB_OUTPUT": str(output), "GITHUB_REPOSITORY": "owner/repo"}
        with patch.dict(os.environ, environment):
            delivery.preflight_command()
        self.assertIn("run_watch=false", output.read_text())
        self.assertIn("reason=freshness_skip", output.read_text())
        self.assertEqual(delivery.read_json(delivery.STATE_PATH), updated_old)
        self.assertFalse(delivery.LEDGER_PATH.exists())


class HistoryGuardTests(unittest.TestCase):
    def setUp(self):
        self.ledger = {"bundles": {}}
        self.state = {}
        self.current = self.run_record(999, 15, status="in_progress")
        self.job_data = {}

    @staticmethod
    def run_record(identifier, hour, **overrides):
        return {"id": identifier, "run_attempt": 1, "workflow_id": 7,
            "repository": {"full_name": "owner/repo"}, "head_repository": {"full_name": "owner/repo"},
            "path": delivery.WORKFLOW_PATH, "head_branch": "main", "event": "schedule", "status": "completed",
            "run_started_at": f"2026-11-18T{hour:02}:00:00Z", **overrides}

    def job(self, run, *, sent="success", persist="success", commit="success", attempt=1, hour=None):
        started = run["run_started_at"] if hour is None else f"2026-11-18T{hour:02}:00:00Z"
        ended = started.replace(":00:00Z", ":01:00Z")
        steps = [{"name": "Send meaningful new signal to exact requested Telegram bot", "conclusion": sent, "started_at": started, "completed_at": ended},
            {"name": "Persist baseline or delivered state", "conclusion": persist},
            {"name": "Commit watcher state and part receipts", "conclusion": commit}]
        self.job_data[(run["id"], attempt)] = [{"name": "monitor", "run_id": run["id"], "status": "completed", "started_at": started, "completed_at": ended, "steps": steps}]

    def audit(self, runs):
        return delivery.audit_previous_runs(current=self.current, runs=runs,
            load_jobs=lambda identifier, attempt: self.job_data[(identifier, attempt)],
            ledger=self.ledger, state=self.state, repository="owner/repo", expected_bot="existing_bot")

    def receipt(self, hour):
        self.state = {"last_successful_delivery_kst": f"2026-11-18T{hour:02}:00:30+00:00",
            "telegram_chat_identity_verified": True, "telegram_message_ids": [101], "bot_username": "existing_bot"}

    def test_failed_receipt_commit_holds_with_previous_run_link(self):
        previous = self.run_record(1, 10)
        self.job(previous, commit="failure")
        with self.assertRaisesRegex(delivery.AmbiguousDelivery, "runs/1/attempts/1"):
            self.audit([previous])
        self.assertEqual(self.ledger["recovery_holds"]["1:1"]["status"], "unresolved")

    def test_missing_or_cancelled_persist_is_held(self):
        for result in ("cancelled", "skipped", None):
            with self.subTest(result=result):
                previous = self.run_record(1, 10)
                self.job(previous, persist=result)
                with self.assertRaises(delivery.AmbiguousDelivery):
                    self.audit([previous])

    def test_partial_sender_and_failed_commit_are_held(self):
        previous = self.run_record(1, 10)
        self.job(previous, sent="failure", commit="cancelled")
        with self.assertRaises(delivery.AmbiguousDelivery):
            self.audit([previous])

    def test_source_503_sender_skipped_does_not_block_recovery(self):
        previous = self.run_record(1, 10)
        self.job(previous, sent="skipped", persist="skipped", commit="failure")
        self.assertEqual(self.audit([previous])["unresolved_holds"], 0)

    def test_later_verified_receipt_commit_reconciles_prior_failure(self):
        failed, later = self.run_record(1, 10), self.run_record(2, 11)
        self.job(failed, commit="failure")
        with self.assertRaises(delivery.AmbiguousDelivery):
            self.audit([failed])
        self.job(later)
        self.receipt(11)
        self.assertTrue(self.audit([failed, later])["receipt_anchor_verified"])
        self.assertEqual(self.ledger["recovery_holds"]["1:1"]["status"], "reconciled")

    def test_later_empty_success_does_not_hide_failed_commit(self):
        failed, empty = self.run_record(1, 10), self.run_record(2, 11)
        self.job(failed, commit="failure")
        self.job(empty)  # The sender can return success with no new alert.
        self.receipt(9)  # No actual delivery occurred during that step.
        with self.assertRaises(delivery.AmbiguousDelivery):
            self.audit([empty, failed])

    def test_same_run_earlier_attempt_is_checked_before_rerun_send(self):
        self.current["run_attempt"] = 2
        self.job(self.current, commit="failure", attempt=1, hour=10)
        with self.assertRaisesRegex(delivery.AmbiguousDelivery, "runs/999/attempts/1"):
            self.audit([])

    def test_later_successful_attempt_can_reconcile_first_attempt(self):
        rerun = self.run_record(1, 12, run_attempt=2)
        self.job(rerun, commit="failure", attempt=1, hour=10)
        self.job(rerun, attempt=2, hour=12)
        self.receipt(12)
        result = self.audit([rerun])
        self.assertTrue(result["receipt_anchor_verified"])
        self.assertEqual(self.ledger["recovery_holds"]["1:1"]["status"], "reconciled")

    def test_unresolved_hold_survives_history_window_rollover(self):
        previous = self.run_record(1, 10)
        self.job(previous, commit="failure")
        with self.assertRaises(delivery.AmbiguousDelivery):
            self.audit([previous])
        with self.assertRaisesRegex(delivery.AmbiguousDelivery, "runs/1/attempts/1"):
            self.audit([])

    def test_untrusted_workflow_is_not_a_receipt_anchor(self):
        previous = self.run_record(1, 10, workflow_id=99)
        self.job(previous)
        self.receipt(10)
        with self.assertRaisesRegex(RuntimeError, "workflow identity"):
            self.audit([previous])

    def test_push_runs_are_excluded(self):
        push = self.run_record(1, 10, event="push")
        self.assertEqual(self.audit([push])["checked_attempts"], 0)

    def test_wrong_bot_or_boolean_id_cannot_reconcile_failure(self):
        failed, later = self.run_record(1, 10), self.run_record(2, 11)
        self.job(failed, commit="failure")
        self.job(later)
        self.receipt(11)
        self.state["telegram_message_ids"] = [True]
        with self.assertRaises(delivery.AmbiguousDelivery):
            self.audit([later, failed])

    def test_cached_completed_attempt_does_not_query_jobs_again(self):
        previous = self.run_record(1, 10)
        self.job(previous, sent="skipped")
        self.assertEqual(self.audit([previous])["queried_attempts"], 1)
        loader = Mock(side_effect=AssertionError("completed attempt queried twice"))
        result = delivery.audit_previous_runs(current=self.current, runs=[previous], load_jobs=loader,
            ledger=self.ledger, state=self.state, repository="owner/repo", expected_bot="existing_bot")
        loader.assert_not_called()
        self.assertEqual((result["queried_attempts"], result["cached_attempts"]), (0, 1))

    def test_new_attempt_queries_only_new_attempt_and_keeps_old_cache(self):
        previous = self.run_record(1, 10)
        self.job(previous, sent="skipped")
        self.audit([previous])
        rerun = self.run_record(1, 11, run_attempt=2)
        self.job(rerun, sent="skipped", attempt=2)
        result = self.audit([rerun])
        self.assertEqual((result["queried_attempts"], result["cached_attempts"]), (1, 1))

    def test_cached_failed_commit_still_blocks(self):
        previous = self.run_record(1, 10)
        self.job(previous, commit="failure")
        with self.assertRaises(delivery.AmbiguousDelivery):
            self.audit([previous])
        loader = Mock(side_effect=AssertionError("unnecessary history query"))
        with self.assertRaises(delivery.AmbiguousDelivery):
            delivery.audit_previous_runs(current=self.current, runs=[previous], load_jobs=loader,
                ledger=self.ledger, state=self.state, repository="owner/repo", expected_bot="existing_bot")
        loader.assert_not_called()

    def test_changed_identity_does_not_reuse_cached_attempt(self):
        previous = self.run_record(1, 10, head_sha="a" * 40)
        self.job(previous, sent="skipped")
        self.audit([previous])
        previous["head_sha"] = "b" * 40
        self.assertEqual(self.audit([previous])["queried_attempts"], 1)


class WorkflowContractTests(unittest.TestCase):
    def test_actual_workflow_routes_through_guard_and_receipt_helper(self):
        workflow = (Path(__file__).resolve().parents[1] / ".github/workflows/ai-networking-optics-telegram-watch.yml").read_text()
        self.assertLess(workflow.index("ai_networking_optics_delivery.py guard"), workflow.index("ai_networking_optics_delivery.py send"))
        self.assertIn("ai_networking_optics_delivery.py persist-state", workflow)
        self.assertIn("ai_networking_optics_delivery.py merge-commit", workflow)
        self.assertIn("actions: read", workflow)
        self.assertIn("ai_networking_optics_delivery.py verify-route", workflow)
        self.assertIn('cron: "8,38 * * * *"', workflow)
        self.assertIn("cancel-in-progress: false", workflow)
        self.assertIn("out/ai_networking_optics_watch_telegram_partial.json", workflow)
        self.assertIn("out/ai_networking_optics_watch_delivery_guard.json", workflow)
        self.assertNotIn("def split_message(value", workflow)

    def test_new_freshness_gate_covers_collection_send_and_state_commit(self):
        workflow = (Path(__file__).resolve().parents[1] / ".github/workflows/ai-networking-optics-telegram-watch.yml").read_text()
        self.assertIn('"AI Security Web Watch"', workflow)
        self.assertIn('"Vera Rubin SOCAMM Capacity Telegram Watch"', workflow)
        self.assertIn('"Korea AI Semiconductor Policy Demand Watch"', workflow)
        for step in ("Check AI networking, optics and Corning signals", "Send meaningful new signal to exact requested Telegram bot", "Persist baseline or delivered state", "Commit watcher state and part receipts"):
            block = workflow.split("      - name: " + step + "\n", 1)[1].split("      - name: ", 1)[0]
            self.assertIn("if: steps.runtime_gate.outputs.run_watch == 'true'", block)


class FreshnessGateTests(unittest.TestCase):
    @staticmethod
    def event():
        return {"repository": {"full_name": "owner/repo"}, "workflow_run": {
            "name": "AI Security Web Watch", "head_repository": {"full_name": "owner/repo"},
            "head_branch": "main", "conclusion": "success", "event": "schedule"}}

    def gate(self, event=None, age_minutes=None, event_name="workflow_run"):
        now = dt.datetime(2026, 11, 18, 12, tzinfo=dt.timezone.utc)
        state = {"last_checked_kst": (now - dt.timedelta(minutes=age_minutes)).isoformat()} if age_minutes is not None else {}
        return delivery.runtime_preflight(event_name=event_name, event=event or self.event(),
            state=state, repository="owner/repo", now=now)

    def test_fresh_recent_check_skips_only_new_backup(self):
        self.assertEqual(self.gate(age_minutes=24)["reason"], "freshness_skip")
        self.assertFalse(self.gate(age_minutes=24)["run_watch"])

    def test_exact_25_minutes_and_missing_state_run(self):
        self.assertTrue(self.gate(age_minutes=25)["run_watch"])
        self.assertTrue(self.gate(age_minutes=120)["run_watch"])
        self.assertTrue(self.gate()["run_watch"])

    def test_future_timestamp_does_not_disable_monitoring(self):
        self.assertTrue(self.gate(age_minutes=-2)["run_watch"])

    def test_wrong_repo_branch_result_or_upstream_event_never_runs(self):
        changes = (("head_repository", {"full_name": "foreign/repo"}), ("head_branch", "feature"),
                   ("conclusion", "failure"), ("event", "push"), ("event", "workflow_dispatch"))
        for key, value in changes:
            with self.subTest(key=key, value=value):
                event = self.event()
                event["workflow_run"][key] = value
                self.assertFalse(self.gate(event=event, age_minutes=120)["run_watch"])

    def test_allowed_upstream_backup_event_runs_when_due(self):
        event = self.event()
        event["workflow_run"]["event"] = "workflow_run"
        self.assertTrue(self.gate(event=event, age_minutes=30)["run_watch"])

    def test_existing_cron_dispatch_push_and_two_backups_are_preserved(self):
        for event_name in ("schedule", "workflow_dispatch", "push"):
            self.assertTrue(self.gate(event_name=event_name, age_minutes=1)["run_watch"])
        for name in ("Vera Rubin SOCAMM Capacity Telegram Watch", "Korea AI Semiconductor Policy Demand Watch"):
            event = self.event()
            event["workflow_run"]["name"] = name
            self.assertTrue(self.gate(event=event, age_minutes=1)["run_watch"])


if __name__ == "__main__":
    unittest.main()
