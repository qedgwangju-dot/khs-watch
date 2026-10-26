"""Offline delivery faults and receipt checks; never contacts LS or Telegram."""
import asyncio
from collections import deque
import contextlib
import io
import json
import os
from pathlib import Path
import tempfile
import time
import unittest
from unittest.mock import patch
import urllib.error

import market_alert_delivery as delivery
import kospi_shock_episode_watch as watch


class Response:
    def __init__(self, value):
        self.value = value if isinstance(value, bytes) else json.dumps(value).encode()
    def __enter__(self): return self
    def __exit__(self, *_args): return False
    def read(self): return self.value


class DeliveryTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.env = patch.dict(os.environ, {
            "TELEGRAM_BOT_TOKEN": "offline-secret-token", "TELEGRAM_CHAT_ID_PRIMARY": "-100888777666",
            "TELEGRAM_CHAT_ID_FALLBACK": "-100111222333", "EXPECTED_TELEGRAM_BOT_USERNAME": "fixture_bot",
            "MARKET_ALERT_DELIVERY_DIR": self.directory.name, "MARKET_ALERT_CODE_SHA": "fixture-code",
            "GITHUB_RUN_ID": "fixture-run",
        })
        self.env.start()
        self.addCleanup(self.env.stop)
        delivery._routes.clear()
        delivery._receipts.clear()
        self.calls = []
        self.send_effect = None
        self.chat = {"id": -100888777666, "type": "channel", "title": "장중 시황"}
        self.bot = {"id": 42, "username": "fixture_bot"}
        self.message = {"message_id": 80001, "date": 1792464300, "from": self.bot,
                        "chat": self.chat, "text": "원문 & 검증\n둘째 줄"}
        self.network = patch.object(delivery.urllib.request, "urlopen", self.urlopen)
        self.network.start()
        self.addCleanup(self.network.stop)
        sleeper = patch.object(delivery.time, "sleep", lambda *_a: None)
        sleeper.start()
        self.addCleanup(sleeper.stop)
        blocker = patch("socket.socket.connect", side_effect=AssertionError("offline only"))
        blocker.start()
        self.addCleanup(blocker.stop)

    def urlopen(self, request, **_kwargs):
        self.calls.append(request)
        if request.full_url.endswith("/getMe"):
            return Response({"ok": True, "result": self.bot})
        if request.full_url.endswith("/getChat"):
            return Response({"ok": True, "result": self.chat})
        if request.full_url.endswith("/sendMessage"):
            if self.send_effect:
                return self.send_effect(request)
            return Response({"ok": True, "result": self.message})
        raise AssertionError("unexpected endpoint")

    def sends(self):
        return [x for x in self.calls if x.full_url.endswith("/sendMessage")]

    def send(self, text="<b>원문 &amp; 검증</b>\n둘째 줄"):
        with delivery.delivery_context(market="KOSPI", stage="start", event_start_ts=1000, actor=""):
            return delivery.send_message(text)

    def test_route_audit_reads_destination_without_any_message(self):
        route = delivery.verify_route()
        self.assertEqual(route["public"]["chat_type"], "channel")
        self.assertEqual(route["public"]["route_selection"], "primary")
        self.assertEqual(route["public"]["recipient_sha256"], delivery.digest("-100888777666"))
        self.assertIsNone(route["public"]["message_auto_delete_time_sec"])
        self.chat.update(type="private", message_auto_delete_time=3600, is_forum=True)
        refreshed = delivery.verify_route(refresh=True)["public"]
        self.assertEqual(refreshed["chat_type"], "private")
        self.assertEqual(refreshed["message_auto_delete_time_sec"], 3600)
        self.assertTrue(refreshed["chat_is_forum"])
        self.assertFalse(self.sends())

    def test_wrong_bot_is_blocked_before_message(self):
        self.bot["username"] = "wrong_bot"
        with self.assertRaises(RuntimeError): self.send()
        self.assertFalse(self.sends())

    def test_wrong_getchat_destination_is_blocked(self):
        self.chat["id"] = -100444555666
        with self.assertRaises(RuntimeError): self.send()
        self.assertFalse(self.sends())

    def test_username_destination_must_resolve_to_same_username(self):
        os.environ["TELEGRAM_CHAT_ID_PRIMARY"] = "@fixture_channel"
        self.chat["username"] = "fixture_channel"
        self.assertEqual(self.send(), 80001)

    def test_fallback_is_explicitly_recorded(self):
        os.environ["TELEGRAM_CHAT_ID_PRIMARY"] = ""
        self.chat["id"] = -100111222333
        route = delivery.verify_route()
        self.assertEqual(route["public"]["route_selection"], "fallback")
        self.assertFalse(self.sends())

    def test_full_rendered_body_destination_date_and_code_are_preserved(self):
        self.assertEqual(self.send(), 80001)
        receipt = delivery.receipt_for(80001)
        self.assertEqual(receipt["telegram_rendered_text"], self.message["text"])
        self.assertEqual(receipt["telegram_date_utc"], "2026-10-20T02:45:00+00:00")
        self.assertEqual(receipt["recipient_sha256"], receipt["returned_recipient_sha256"])
        self.assertEqual(receipt["code_sha"], "fixture-code")
        self.assertEqual(receipt["run_id"], "fixture-run")
        self.assertFalse(receipt["read_only"])
        all_files = "".join(p.read_text(encoding="utf-8") for p in Path(self.directory.name).glob("*"))
        self.assertNotIn("offline-secret-token", all_files)
        self.assertNotIn("-100888777666", all_files)
        self.assertNotIn("-100111222333", all_files)

    def test_recipient_mismatch_after_post_is_uncertain(self):
        self.message["chat"] = {"id": -100444555666, "type": "channel"}
        with self.assertRaises(delivery.DeliveryUncertain): self.send()
        self.assertEqual(len(self.sends()), 1)
        self.assertEqual(next(iter(delivery._states().values()))["status"], "uncertain")

    def test_returned_text_mismatch_is_not_confirmed(self):
        self.message["text"] = "different body"
        with self.assertRaises(delivery.DeliveryUncertain): self.send()
        self.assertIsNone(delivery.receipt_for(80001))

    def test_missing_date_or_zero_id_is_not_approved(self):
        self.message.pop("date")
        self.message["message_id"] = 0
        with self.assertRaises(delivery.DeliveryUncertain): self.send()

    def test_send_timeout_is_not_automatically_retried_even_on_later_call(self):
        def timeout(_request): raise TimeoutError("offline after possible acceptance")
        self.send_effect = timeout
        with self.assertRaises(delivery.DeliveryUncertain): self.send()
        with self.assertRaises(delivery.DeliveryUncertain): self.send()
        self.assertEqual(len(self.sends()), 1)

    def test_unresolved_send_blocks_same_event_but_not_a_distinct_event(self):
        def timeout(_request): raise TimeoutError("offline after possible acceptance")
        self.send_effect = timeout
        with self.assertRaises(delivery.DeliveryUncertain): self.send()
        self.assertEqual(len(self.sends()), 1)

        # The exact event identity stays fail-closed even if a later process
        # renders a different body for it.
        self.send_effect = None
        with delivery.delivery_context(market="KOSPI", stage="start", event_start_ts=1000, actor=""):
            with self.assertRaises(delivery.DeliveryUncertain):
                delivery.send_message("re-rendered same event")
        self.assertEqual(len(self.sends()), 1)

        # A different event on the same verified route must not inherit the
        # first event's uncertainty lock.
        self.message.update(message_id=80002, text="different market event")
        with delivery.delivery_context(market="KOSDAQ", stage="start", event_start_ts=2000, actor=""):
            self.assertEqual(delivery.send_message("different market event"), 80002)
        self.assertEqual(len(self.sends()), 2)

    def test_malformed_response_is_uncertain_and_blocks_replay(self):
        self.send_effect = lambda _r: Response(b"not JSON")
        with self.assertRaises(delivery.DeliveryUncertain): self.send()
        with self.assertRaises(delivery.DeliveryUncertain): self.send("changed timestamp")
        self.assertEqual(len(self.sends()), 1)

    def test_http500_is_not_retried(self):
        def error(request): raise urllib.error.HTTPError(request.full_url, 500, "offline", {}, None)
        self.send_effect = error
        with self.assertRaises(delivery.DeliveryUncertain): self.send()
        self.assertEqual(len(self.sends()), 1)

    def test_explicit_rejection_does_not_create_an_uncertain_delivery(self):
        self.send_effect = lambda _r: Response({"ok": False, "error_code": 400})
        with self.assertRaises(RuntimeError): self.send()
        self.assertEqual(next(iter(delivery._states().values()))["status"], "rejected")

    def test_only_explicit_rate_limit_is_retried(self):
        def limited(_request):
            return (Response({"ok": False, "error_code": 429}) if len(self.sends()) == 1
                    else Response({"ok": True, "result": self.message}))
        self.send_effect = limited
        self.assertEqual(self.send(), 80001)
        self.assertEqual(len(self.sends()), 2)

    def test_persisted_approval_is_reused_after_memory_and_route_cache_reset(self):
        self.send()
        delivery._receipts.clear()
        delivery._routes.clear()
        self.assertEqual(self.send("new render timestamp"), 80001)
        self.assertEqual(len(self.sends()), 1)
        self.assertEqual(delivery.receipt_for(80001)["telegram_rendered_text"], self.message["text"])

    def test_inflight_crash_marker_blocks_automatic_send(self):
        with delivery.delivery_context(market="KOSPI", stage="start", event_start_ts=1000, actor=""):
            route = delivery.verify_route()
            identity = {k: delivery._context.get().get(k)
                        for k in ("market", "stage", "actor", "event_start_ts", "expansion_from")}
            key = delivery.digest(json.dumps(
                [route["public"]["bot_username"], route["public"]["recipient_sha256"], identity],
                sort_keys=True,
            ))
            delivery._append({"delivery_key": key, "status": "in_flight",
                              "recipient_sha256": route["public"]["recipient_sha256"]})
            with self.assertRaises(delivery.DeliveryUncertain): self.send()
        self.assertFalse(self.sends())

    def test_damaged_journal_blocks_send(self):
        (Path(self.directory.name) / "journal.jsonl").write_text('{"broken":', encoding="utf-8")
        with self.assertRaises(delivery.DeliveryUncertain): self.send()
        self.assertFalse(self.sends())

    def test_too_long_body_does_not_reach_post(self):
        with self.assertRaises(RuntimeError): self.send("가" * 4097)
        self.assertFalse(self.sends())

    def test_read_transport_retry_does_not_retry_a_message(self):
        original = self.urlopen
        count = [0]
        def flaky(request, **kwargs):
            if request.full_url.endswith("/getChat"):
                count[0] += 1
                if count[0] < 3: raise urllib.error.URLError("offline read disconnect")
            return original(request, **kwargs)
        with patch.object(delivery.urllib.request, "urlopen", flaky):
            self.assertEqual(self.send(), 80001)
        self.assertEqual(count[0], 3)
        self.assertEqual(len(self.sends()), 1)


class EventStateTests(unittest.TestCase):
    def worker(self):
        w = watch.Watch("unused", [], "unused", False)
        async def noop(*_a, **_k): pass
        for name in ("maybe_flow", "maybe_kosdaq_flow", "maybe_kosdaq_price", "maybe_alert_flow_surge",
                     "maybe_alert_kosdaq_surge", "maybe_alert_kosdaq_drop"):
            setattr(w, name, noop)
        w.session_close_ts = None
        w.opening_gap_sent = True
        w.regular_price_ready = True
        w.build_alert = lambda *_a: "offline fixture"
        return w

    def test_kospi_expansion_rejection_preserves_last_approved_threshold(self):
        now = time.time()
        w = self.worker()
        w.idx = deque([(now, 98.9)])
        w.episode = {"start_ts": now-400, "start_price": 100.0, "low_ts": now-1,
                     "low_price": 99.0, "sent_drop": .4, "alerted": True}
        with patch.object(watch, "telegram_send", side_effect=RuntimeError("offline rejected")):
            with self.assertRaises(RuntimeError): asyncio.run(w.evaluate())
        self.assertEqual(w.episode["sent_drop"], .4)
        self.assertEqual(w.msg_ids, [])

    def test_each_kospi_start_rejection_leaves_no_falsely_alerted_episode(self):
        now = time.time()
        for mode in ("complete", "missing", "stale"):
            with self.subTest(mode=mode):
                w = self.worker()
                w.idx = deque([(now, 99.5)])
                w._trigger = lambda: (True, {"peak_ts": now-300, "peak": 100.0,
                                            "cur_ts": now, "cur": 99.5, "drop": -.5})
                w._flow_channel_near = lambda ts, _key: None if mode == "missing" else ({}, ts-(45 if mode == "stale" else 0))
                with patch.object(watch, "telegram_send", side_effect=RuntimeError("offline rejected")):
                    with self.assertRaises(RuntimeError): asyncio.run(w.evaluate())
                self.assertIsNone(w.episode)
                self.assertEqual(w.msg_ids, [])

    def test_market_stage_identity_survives_to_thread(self):
        w = self.worker()
        got = []
        def fake(_text):
            got.append(dict(delivery._context.get()))
            return 123
        with patch.object(watch, "telegram_send", fake):
            for market, stage in (("KOSPI", "start"), ("KOSDAQ", "kosdaq_shock_expand"),
                                  ("KOSPI", "end"), ("KOSDAQ", "kosdaq_enrichment"),
                                  ("KOSPI", "flow_surge"), ("KOSDAQ", "kosdaq_flow_surge")):
                asyncio.run(w._send_event(stage, {"market": market, "start_ts": 1000, "actor": "기관"}, 1200, "offline"))
        self.assertEqual([r["market"] for r in got], ["KOSPI", "KOSDAQ"] * 3)
        self.assertEqual(got[-1]["actor"], "기관")

    def test_reused_kospi_start_receipt_keeps_its_approved_drop(self):
        now = time.time()
        for mode in ("complete", "missing", "stale"):
            with self.subTest(mode=mode):
                w = self.worker()
                w.idx = deque([(now, 99.2)])
                w._trigger = lambda: (True, {"peak_ts": now-300, "peak": 100.0,
                                            "cur_ts": now, "cur": 99.2, "drop": -.8})
                w._flow_channel_near = lambda ts, _key: None if mode == "missing" else ({}, ts-(45 if mode == "stale" else 0))
                w._record_delivery = lambda *_a, **_k: None
                with patch.object(watch, "telegram_send", return_value=123), \
                     patch.object(watch, "receipt_for", return_value={"context": {"observed_drop": .5}}):
                    asyncio.run(w.evaluate())
                self.assertEqual(w.episode["sent_drop"], .5)

    def test_reused_kosdaq_start_receipt_keeps_its_approved_drop(self):
        now = time.time()
        w = self.worker()
        w.kosdaq_regular_price_ready = True
        w.kosdaq_opening_gap_sent = True
        w.kosdaq_idx = deque([(now, 99.2)])
        w._kosdaq_trigger = lambda: (True, {"peak_ts": now-300, "peak": 100.0,
                                           "cur_ts": now, "cur": 99.2, "drop": -.8})
        w.build_kosdaq_drop_alert = lambda *_a: "offline fixture"
        w._record_delivery = lambda *_a, **_k: None
        with patch.object(watch, "telegram_send", return_value=123), \
             patch.object(watch, "receipt_for", return_value={"context": {"observed_drop": .5}}):
            asyncio.run(watch.Watch.maybe_alert_kosdaq_drop(w))
        self.assertEqual(w.kosdaq_episode["sent_drop"], .5)

    def test_receipt_and_event_log_are_linked_without_exposing_recipient_id(self):
        w = self.worker()
        with tempfile.TemporaryDirectory() as directory:
            logfile = Path(directory) / "events.jsonl"
            receipt = {"status": "confirmed", "request_body_sha256": "body", "returned_recipient_sha256": "recipient",
                       "telegram_rendered_text": "original body", "context": {"stage": "end", "event_start_ts": 1000,
                       "event_low_ts": 1100, "observed_ts": 1200}}
            with patch.object(watch, "DELIVERY_LOG", logfile), patch.object(watch, "receipt_for", return_value=receipt):
                w._record_delivery("end", 200, {"start_ts": 1000, "low_ts": 1150}, 1300)
            row = json.loads(logfile.read_text())
            self.assertEqual(row["observed_ts"], 1200)
            self.assertEqual(row["event_low_ts"], 1100)
            self.assertEqual(row["delivery_receipt"]["telegram_rendered_text"], "original body")

    def test_saved_event_record_is_not_appended_twice_after_checkpoint_retry(self):
        w = self.worker()
        with tempfile.TemporaryDirectory() as directory:
            logfile = Path(directory) / "events.jsonl"
            receipt = {"status": "confirmed", "delivery_key": "one-event", "request_body_sha256": "body",
                       "returned_recipient_sha256": "recipient", "context": {"stage": "end",
                       "event_start_ts": 1000, "event_low_ts": 1100, "observed_ts": 1200}}
            with patch.object(watch, "DELIVERY_LOG", logfile), patch.object(watch, "receipt_for", return_value=receipt):
                w._record_delivery("end", 200, {"start_ts": 1000, "low_ts": 1100}, 1200)
                w._record_delivery("end", 200, {"start_ts": 1000, "low_ts": 1100}, 1200)
            self.assertEqual(len(logfile.read_text().splitlines()), 1)

    def test_kosdaq_send_failure_does_not_send_a_false_source_failure_notice(self):
        w = self.worker()
        with patch.object(watch, "build_kosdaq_enrichment", return_value=("offline body", {})), \
             patch.object(watch, "telegram_send", side_effect=RuntimeError("offline rejected")) as sender:
            asyncio.run(w._run_kosdaq_enrichment({"market": "KOSDAQ", "start_ts": 1000, "low_ts": 1100}, {}))
        self.assertEqual(sender.call_count, 1)
        self.assertEqual(w.raw["last_kosdaq_enrichment_error_phase"], "delivery")


if __name__ == "__main__":
    unittest.main(verbosity=2)
