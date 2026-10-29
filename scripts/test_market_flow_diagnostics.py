"""Offline checks of diagnostics; no broker or Telegram calls."""
import asyncio
import contextlib
import io
import json
import unittest
from collections import deque
from unittest.mock import AsyncMock, Mock, patch

import kospi_shock_episode_watch as watch


# Published KOSDAQ t1602 row from the 2026-10-29 11:32:30 saved handoff.
# Account-specific supplements are deliberately represented only by a sentinel.
OBSERVED = {
    "time": "11323000", "sample_ts": 1793241150.0, "received_ts": 1793241152.6616526,
    "market": "KOSDAQ", "source_tr": "t1602", "request_market": "3",
    "upcode": "301", "exchgubun": "U", "returned_ex_upcode": "U301",
    "timestamp_basis": "provider_time",
    "source_row": {"time": "11323000", "sv_08": 1819, "sv_17": -1170,
                   "sv_18": -529, "sv_01": -339, "sv_03": -9},
    "개인": 1819.0, "외국인": -1170.0, "기관": -529.0,
    "투신": -9.0, "금융투자": -339.0,
    "actor_quality": {"투신": {"parent": "기관", "verified": True},
                      "금융투자": {"parent": "기관", "verified": True}},
    "cash_supplement": {"account_sentinel": "DO_NOT_LOG"},
}


def spot(ts, personal, *, market="KOSDAQ"):
    return {"source_tr": "t1602", "market": market, "sample_ts": ts,
            "received_ts": ts + 2, "개인": personal, "외국인": 0.0, "기관": 0.0}


def new_watch():
    obj = watch.Watch.__new__(watch.Watch)
    obj.test = False
    obj.raw = {}
    obj.flows = deque()
    obj.kosdaq_flows = deque()
    obj.kosdaq_last_success_ts = None
    obj.session_open_ts = 1793232000.0
    obj.session_close_ts = 1793255400.0
    obj.session_continuous_end_ts = 1793254800.0
    obj.kosdaq_surge_last_processed_ts = 0.0
    obj.kosdaq_surge_pending = {}
    obj.kosdaq_surge_sent_at = {}
    obj.handoff_path = None
    return obj


def events(output, prefix):
    return [json.loads(line[len(prefix):]) for line in output.getvalue().splitlines()
            if line.startswith(prefix)]


class TraceTests(unittest.TestCase):
    def test_diagnostic_pair_capture_does_not_change_kospi_candidates(self):
        # Magnitude follows the observed 10:59:28 delivery; endpoint balances
        # below are synthetic because only the delta is needed for this check.
        before = 1793238840.0
        after = before + 300
        rows = [
            {"ts": before + 2, "현물": spot(before, 0, market="KOSPI"),
             "선물": spot(before, 0, market="KOSPI")},
            {"ts": after + 2, "현물": spot(after, 1593, market="KOSPI"),
             "선물": spot(after, 430, market="KOSPI")},
        ]
        diagnostic = {}
        without = watch.flow_surge_candidates(rows, after + 3, 1793232000.0)
        with_trace = watch.flow_surge_candidates(rows, after + 3, 1793232000.0, diagnostic)
        self.assertEqual(without, with_trace)
        self.assertEqual(1593.0, diagnostic["spot_pair"]["deltas"]["개인"])
        self.assertEqual(430.0, diagnostic["futures_pair"]["deltas"]["개인"])
        self.assertEqual("개인", with_trace[0]["actor"])

    def test_observed_row_is_logged_once_without_account_supplement(self):
        obj = new_watch()
        output = io.StringIO()
        with patch.object(watch.time, "time", return_value=1793241153.0), contextlib.redirect_stdout(output):
            obj._record_kosdaq_flow_fragment({"현물": OBSERVED})
            obj._record_kosdaq_flow_fragment({"현물": OBSERVED})
        rows = events(output, "market_flow_sample=")
        self.assertEqual(1, len(rows))
        self.assertEqual(2, len(obj.kosdaq_flows))
        self.assertEqual(OBSERVED["sample_ts"], obj.kosdaq_last_success_ts)
        self.assertEqual(OBSERVED["source_row"], rows[0]["source"]["source_row"])
        self.assertEqual(1819.0, rows[0]["actor_values"]["개인"])
        self.assertNotIn("DO_NOT_LOG", output.getvalue())

    def test_futures_row_is_marked_as_unverified(self):
        obj = new_watch()
        future = dict(OBSERVED, market="KOSPI", upcode="900", request_market="4")
        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            obj._record_kospi_flow_fragment({"선물": future})
        row = events(output, "market_flow_sample=")[0]
        self.assertEqual("KOSPI", row["market"])
        self.assertIsNone(row["unit"])
        self.assertEqual("futures_unverified", row["unit_scope"])

    def test_trace_failure_does_not_discard_a_market_sample(self):
        obj = new_watch()
        with patch.object(watch.time, "time", return_value=1793241153.0), \
             patch("builtins.print", side_effect=OSError("offline log failure")):
            obj._record_kosdaq_flow_fragment({"현물": OBSERVED})
        self.assertEqual(1, len(obj.kosdaq_flows))
        self.assertEqual(OBSERVED["sample_ts"], obj.kosdaq_last_success_ts)
        self.assertEqual("OSError", obj.raw["last_flow_trace_error"])


class DecisionTraceTests(unittest.IsolatedAsyncioTestCase):
    async def test_logging_failure_does_not_suppress_confirmed_alert(self):
        obj = new_watch()
        base = 1793240820.0
        obj.kosdaq_flows.extend([
            {"ts": base + 2, "현물": spot(base, 1700)},
            {"ts": base + 32, "현물": spot(base + 30, 1703)},
            {"ts": base + 302, "현물": spot(base + 300, 1880)},
        ])
        obj.msg_ids = []
        obj._surge_industry_context = AsyncMock(return_value=None)
        obj.build_kosdaq_flow_surge_alert = Mock(return_value="offline")
        obj._try_send_event = AsyncMock(return_value=999)
        obj._record_delivery = Mock()
        with patch("builtins.print", side_effect=OSError("offline log failure")):
            await obj.maybe_alert_kosdaq_surge(now_ts=base + 303)
            obj.kosdaq_flows.append({"ts": base + 332, "현물": spot(base + 330, 1890)})
            await obj.maybe_alert_kosdaq_surge(now_ts=base + 333)
        obj._try_send_event.assert_awaited_once()
        obj._record_delivery.assert_called_once()
        self.assertEqual([999], obj.msg_ids)
        self.assertEqual("OSError", obj.raw["last_flow_trace_error"])

    async def test_actual_threshold_confirmation_and_cooldown_are_distinguishable(self):
        obj = new_watch()
        base = 1793240820.0  # 11:27 KST
        obj.kosdaq_flows.extend([
            {"ts": base + 2, "현물": spot(base, 1700)},
            {"ts": base + 32, "현물": spot(base + 30, 1703)},
            {"ts": base + 302, "현물": spot(base + 300, 1880)},
        ])
        obj._surge_industry_context = AsyncMock(return_value=None)
        obj.build_kosdaq_flow_surge_alert = Mock(return_value="offline")
        obj._try_send_event = AsyncMock(return_value=None)
        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            await obj.maybe_alert_kosdaq_surge(now_ts=base + 303)
            obj.kosdaq_flows.append({"ts": base + 332, "현물": spot(base + 330, 1890)})
            obj.kosdaq_surge_sent_at["개인"] = base + 300  # active 20-minute cooldown
            await obj.maybe_alert_kosdaq_surge(now_ts=base + 333)
        checks = events(output, "market_flow_check=")
        decisions = events(output, "market_flow_decision=")
        self.assertEqual(["awaiting_confirmation", "cooldown"],
                         [row["result"] for row in decisions if row["actor"] == "개인"])
        self.assertEqual(180.0, checks[0]["spot_pair"]["deltas"]["개인"])
        self.assertEqual(187.0, checks[1]["spot_pair"]["deltas"]["개인"])
        self.assertGreater(decisions[-1]["cooldown_remaining_sec"], 0)
        obj._try_send_event.assert_not_awaited()

    async def test_stale_source_shows_missing_pair_and_age_without_inventing_delta(self):
        obj = new_watch()
        # The 53-second age matches the observed 14:22:53 health record; the
        # pair values here are synthetic because that live raw pair was not saved.
        end = 1793251320.0
        obj.kosdaq_flows.extend([
            {"ts": end - 298, "현물": spot(end - 300, 1700)},
            {"ts": end + 2, "현물": spot(end, 1890)},
        ])
        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            await obj.maybe_alert_kosdaq_surge(now_ts=end + 53)
        row = events(output, "market_flow_check=")[0]
        self.assertIsNone(row["spot_pair"])
        self.assertEqual(53.0, row["last_received_spot"]["age_sec"])
        self.assertEqual([], row["candidates"])


if __name__ == "__main__":
    unittest.main()
