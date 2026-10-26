"""Offline replay of the preserved 2026-10-26 Telegram timeout.

No LS or Telegram traffic is allowed. An ambiguous incident must remain held
while price tracking, other actors and the other market continue.
"""
import asyncio
from collections import deque
import copy
import datetime as dt
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import AsyncMock, Mock, patch

import kospi_shock_episode_watch as ks
import market_alert_delivery as delivery


FIXTURE = json.loads((Path(__file__).resolve().parents[1] / "tests/fixtures/market_delivery_timeout_20261026.json").read_text(encoding="utf-8"))


def watch():
    w = ks.Watch("unused", [], "", False)
    for name in ("maybe_flow", "maybe_kosdaq_flow", "maybe_kosdaq_price",
                 "maybe_alert_flow_surge", "maybe_alert_kosdaq_surge", "maybe_alert_kosdaq_drop"):
        setattr(w, name, AsyncMock())
    return w


class DeliveryRecovery(unittest.IsolatedAsyncioTestCase):
    async def test_preserved_timeout_closes_tracking_without_false_receipt(self):
        w = watch()
        event = copy.deepcopy(FIXTURE["episode"])
        now = FIXTURE["context"]["observed_ts"]
        w.episode = event
        w.idx = deque([(now, FIXTURE["current_price"])], maxlen=30000)
        w.regular_price_ready = True
        w.session_open_ts = now - 3600
        w.attribution = Mock(return_value={})
        w.build_end = Mock(return_value=FIXTURE["request_html"])
        w._record_delivery = Mock()
        context = FIXTURE["context"]
        identity = {k: context.get(k) for k in ("market", "stage", "actor", "event_start_ts", "expansion_from")}
        public = {"bot_username": "offline_test_bot", "recipient_sha256": delivery.digest("offline-recipient")}
        key = delivery.digest(json.dumps([public["bot_username"], public["recipient_sha256"], identity], sort_keys=True))
        prior = {"delivery_key": key, "status": "uncertain", "context": context, "error_type": "TimeoutError"}
        with tempfile.TemporaryDirectory() as tmp, patch.dict("os.environ", {"MARKET_ALERT_DELIVERY_DIR": tmp}), patch.object(delivery, "verify_route", return_value={"public": public}), patch.object(delivery.urllib.request, "urlopen", side_effect=AssertionError("Offline replay must not resend")), patch.object(ks, "telegram_send", delivery.send_message), patch.object(ks.time, "time", return_value=now):
            journal = Path(tmp) / "journal.jsonl"
            journal.write_text(json.dumps(prior) + "\n", encoding="utf-8")
            await w.evaluate()
            self.assertIsNone(w.episode)
            self.assertEqual(w.msg_ids, [])
            w._record_delivery.assert_not_called()
            self.assertEqual(journal.read_text(encoding="utf-8"), json.dumps(prior) + "\n")
            self.assertTrue(w.raw.get("delivery_holds"))
            self.assertEqual(event["end_delivery_status"], "unconfirmed")
            w._trigger = Mock(return_value=(False, {}))
            await w.evaluate()
            self.assertEqual(w.maybe_alert_kosdaq_surge.await_count, 2)

    async def test_held_event_survives_handoff_and_other_event_can_send(self):
        w = watch()
        event = {"market": "KOSPI", "start_ts": 1000.0}
        with patch.object(ks, "telegram_send", side_effect=[delivery.DeliveryUncertain("ambiguous"), 9001]) as sender, tempfile.TemporaryDirectory() as tmp:
            self.assertIsNone(await w._try_send_event("end", event, 1200.0, "held"))
            handoff = Path(tmp) / "handoff.json"
            w.save_handoff(handoff)
            restored = watch()
            restored.load_handoff(handoff)
            self.assertIsNone(await restored._try_send_event("end", event, 1300.0, "same incident"))
            self.assertEqual(await restored._try_send_event("kosdaq_flow_surge", {"market": "KOSDAQ", "actor": "기관", "start_ts": 1200.0}, 1500.0, "independent signal"), 9001)
            self.assertEqual(sender.call_count, 2)
            self.assertEqual(restored.msg_ids, [])

    async def test_unconfirmed_expansion_does_not_prevent_episode_end(self):
        w = watch()
        now = FIXTURE["context"]["observed_ts"]
        w.episode = copy.deepcopy(FIXTURE["episode"])
        w.episode["sent_drop"] = 0.0
        w.idx = deque([(now, 5488.5)], maxlen=30000)
        w.regular_price_ready = True
        w.session_open_ts = now - 3600
        w.attribution = Mock(return_value={})
        w.build_alert = Mock(return_value="expansion")
        w.build_end = Mock(return_value="end")
        w._record_delivery = Mock()
        w._run_enrichment = AsyncMock()
        with patch.object(ks, "telegram_send", side_effect=[delivery.DeliveryUncertain("ambiguous expansion"), 9002]), patch.object(ks.time, "time", return_value=now):
            await w.evaluate()
            self.assertIsNone(w.episode)
            self.assertEqual(w.msg_ids, [9002])
            self.assertEqual(w._record_delivery.call_count, 1)
            self.assertEqual(w._record_delivery.call_args.args[0], "end")
            await asyncio.sleep(0)

    async def test_kosdaq_end_uncertainty_preserves_observation_without_receipt(self):
        w = watch()
        now = FIXTURE["context"]["observed_ts"]
        w.kosdaq_episode = {**copy.deepcopy(FIXTURE["episode"]), "market": "KOSDAQ"}
        w.kosdaq_idx = deque([(now, FIXTURE["current_price"])], maxlen=30000)
        w.kosdaq_regular_price_ready = True
        w.session_open_ts = now - 3600
        w._kosdaq_attribution = Mock(return_value={})
        w.build_kosdaq_drop_alert = Mock(return_value="end")
        w._record_delivery = Mock()
        with patch.object(ks, "telegram_send", side_effect=delivery.DeliveryUncertain("ambiguous KOSDAQ end")), patch.object(ks.time, "time", return_value=now):
            await ks.Watch.maybe_alert_kosdaq_drop(w)
            self.assertIsNone(w.kosdaq_episode)
            self.assertEqual(w.msg_ids, [])
            w._record_delivery.assert_not_called()

    async def test_start_uncertainty_keeps_active_observation(self):
        w = watch()
        now = FIXTURE["context"]["observed_ts"]
        w.idx = deque([(now, 5493.97)], maxlen=30000)
        w.regular_price_ready = True
        w.session_open_ts = now - 3600
        w._trigger = Mock(return_value=(True, copy.deepcopy(FIXTURE["episode"]["trigger"])))
        w._flow_channel_near = Mock(return_value=None)
        w.build_alert = Mock(return_value="start")
        w._record_delivery = Mock()
        with patch.object(ks, "telegram_send", side_effect=delivery.DeliveryUncertain("ambiguous start")), patch.object(ks.time, "time", return_value=now):
            await w.evaluate()
            self.assertIsNotNone(w.episode)
            self.assertFalse(w.episode["alerted"])
            self.assertEqual(w.episode["start_delivery_status"], "unconfirmed")
            self.assertEqual(w.msg_ids, [])
            w._record_delivery.assert_not_called()

    async def test_surge_uncertainty_does_not_block_next_actor_or_fake_cooldown_receipt(self):
        w = watch()
        w.session_open_ts, w.session_continuous_end_ts, w.session_close_ts = 9500, 15000, 16000
        w.flows = deque([{"ts": 10320}], maxlen=2500)
        w.surge_pending = {actor: {"sample_ts": 10300, "seen_at": 10303} for actor in ("외국인", "기관")}
        w._surge_industry_context = AsyncMock(return_value={})
        w.build_flow_surge_alert = Mock(return_value="surge")
        w._record_delivery = Mock()
        candidates = [{"actor": actor, "sample_ts": 10320, "mode": "현물 중심", "spot": 550,
                       "futures": None, "confidence": "단독 신호", "spot_end_cumulative": 550,
                       "spot_window": [10020, 10320]} for actor in ("외국인", "기관")]
        with patch.object(ks, "flow_surge_candidates", return_value=candidates), patch.object(ks, "confirm_flow_surge", return_value=True), patch.object(ks.time, "time", return_value=10323), patch.object(ks, "telegram_send", side_effect=[delivery.DeliveryUncertain("ambiguous foreign surge"), 9003]) as sender:
            await ks.Watch.maybe_alert_flow_surge(w, 10323)
            self.assertEqual(w.msg_ids, [9003])
            self.assertNotIn("외국인", w.surge_sent_at)
            self.assertEqual(w.surge_sent_at["기관"], 10323)
            w.flows.append({"ts": 10340})
            await ks.Watch.maybe_alert_flow_surge(w, 10343)
            self.assertEqual(sender.call_count, 2)


if __name__ == "__main__":
    unittest.main()
