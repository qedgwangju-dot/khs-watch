"""Offline proof that slow optional data does not prevent primary flow polling."""
import asyncio
import contextlib
import io
import threading
import time
import unittest
from unittest.mock import patch

import kospi_shock_episode_watch as watch


class PollIsolationTests(unittest.IsolatedAsyncioTestCase):
    async def _exercise_slow_supplement(self, market):
        blocker = threading.Event()
        supplement_started = threading.Event()
        calls = []
        snapshots = []
        supplement_calls = []
        obj = watch.Watch("dummy", [], "", False)

        def make_snapshot(index):
            now = time.time()
            return {"ts": now, "market": market, "errors": {},
                    "현물": {"source_tr": "t1602", "market": market,
                           "sample_ts": now, "received_ts": now,
                           "외국인": index, "기관": index, "개인": index}}

        def supplementary(snap, market_name):
            supplement_calls.append(market_name)
            supplement_started.set()
            if not blocker.wait(3):
                raise TimeoutError("test never released supplemental call")
            snap["cash_supplement"] = {"market": market_name, "received_ts": time.time()}
            snap["현물"]["cash_supplement"] = snap["cash_supplement"]
            return snap

        def primary(token, market_name, publish, include_supplement=True):
            calls.append(market_name)
            snap = make_snapshot(len(calls))
            snapshots.append(snap)
            publish(snap)
            return supplementary(snap, market_name) if include_supplement else snap

        poll = obj.maybe_flow if market == "KOSPI" else obj.maybe_kosdaq_flow
        task_name = "flow_task" if market == "KOSPI" else "kosdaq_flow_task"
        try:
            with patch.object(watch, "fetch_flow_snapshot", side_effect=primary), \
                 patch.object(watch, "enrich_snapshot", side_effect=supplementary), \
                 patch.object(watch, "flow_snapshot_health", return_value=(True, {})), \
                 patch.object(watch, "FLOW_INTERVAL_SEC", 0), \
                 contextlib.redirect_stdout(io.StringIO()):
                await poll()
                self.assertTrue(await asyncio.to_thread(supplement_started.wait, 1))
                await asyncio.sleep(0.05)
                await poll()
                await asyncio.sleep(0.10)
                self.assertGreaterEqual(len(calls), 2, "slow optional data stalled the primary flow poll")
                self.assertFalse(blocker.is_set(), "supplement must still be blocked during the second poll")
                self.assertEqual(len(supplement_calls), 1, "do not start overlapping optional queries")
                primary_task = getattr(obj, task_name)
                if primary_task is not None:
                    await asyncio.wait_for(primary_task, 1)
                rows = obj.flows if market == "KOSPI" else obj.kosdaq_flows
                other = "KOSDAQ" if market == "KOSPI" else "KOSPI"
                wrong = {**snapshots[-1]["현물"], "market": other,
                         "sample_ts": snapshots[-1]["현물"]["sample_ts"] + 1,
                         "외국인": 9999}
                rows.append({"ts": time.time(), "현물": wrong})
                blocker.set()
                task = getattr(obj, "_kospi_supplement_task" if market == "KOSPI" else "_kosdaq_supplement_task")
                await asyncio.wait_for(task, 1)
                newest = rows[-1]["현물"]
                self.assertEqual(newest["sample_ts"], snapshots[-1]["현물"]["sample_ts"])
                self.assertEqual(newest["received_ts"], snapshots[-1]["현물"]["received_ts"])
                self.assertEqual(newest["외국인"], 2)
                self.assertIn("cash_supplement", rows[-1])
                self.assertNotIn("cash_supplement", snapshots[0]["현물"])
        finally:
            blocker.set()
            pending = [getattr(obj, n, None) for n in (task_name, "_kospi_supplement_task", "_kosdaq_supplement_task")]
            for task in pending:
                if task is not None:
                    try:
                        await asyncio.wait_for(task, 2)
                    except (asyncio.TimeoutError, asyncio.CancelledError):
                        pass

    async def test_kospi_slow_supplement_does_not_stop_primary(self):
        await self._exercise_slow_supplement("KOSPI")

    async def test_kosdaq_slow_supplement_does_not_stop_primary(self):
        await self._exercise_slow_supplement("KOSDAQ")

    async def test_optional_failure_is_recorded_per_market_without_destroying_source(self):
        obj = watch.Watch("dummy", [], "", False)
        snap = {"ts": time.time(), "market": "KOSDAQ", "errors": {},
                "현물": {"sample_ts": time.time(), "market": "KOSDAQ", "source_tr": "t1602"}}
        obj.kosdaq_flows.append(snap)
        with patch.object(watch, "enrich_snapshot", side_effect=ValueError("secret details")):
            obj._schedule_flow_supplement("KOSDAQ", snap)
            await obj._kosdaq_supplement_task
        self.assertEqual(obj.raw["last_kosdaq_supplement_error"], "ValueError")
        self.assertNotIn("last_kospi_supplement_error", obj.raw)
        self.assertEqual(obj.kosdaq_flows[-1], snap)

    async def test_verified_program_fallback_can_still_recover_snapshot_health(self):
        obj = watch.Watch("dummy", [], "", False)
        now = time.time()
        actors = {"sample_ts": now, "외국인": 1, "기관": 2, "개인": 3}
        snap = {"ts": now, "market": "KOSPI", "errors": {"프로그램": "LS unavailable"},
                "현물": dict(actors), "지수선물": dict(actors), "프로그램": None}
        alternate = {"sample_ts": now, "전체": 4, "차익": 1, "비차익": 3,
                     "market": "KOSPI", "source_tr": "ka90005", "unit_verified": True,
                     "source_scope_verified": True, "independent_population_unit_and_clock_verified": True}
        obj.raw["last_flow_snapshot"] = snap
        obj.raw["last_flow_health_issue"] = {"프로그램": "missing"}
        obj.flows.append(snap)
        def with_alternate(source, market):
            source["program_supplement"] = alternate
            source["프로그램"] = alternate
            return source
        with patch.object(watch, "enrich_snapshot", side_effect=with_alternate), \
             contextlib.redirect_stdout(io.StringIO()):
            obj._schedule_flow_supplement("KOSPI", snap)
            await obj._kospi_supplement_task
        latest = obj.raw["last_flow_snapshot"]
        self.assertEqual(latest["프로그램"]["sample_ts"], now)
        self.assertEqual(latest["recovered_source_errors"]["프로그램_LS"], "LS unavailable")
        self.assertIsNotNone(obj.last_flow_success_ts)
        self.assertNotIn("last_flow_health_issue", obj.raw)

    def test_primary_only_fetch_skips_supplement_and_default_is_compatible(self):
        cash = {"market": "KOSDAQ", "source_tr": "t1602"}
        supplemental = {"provider": "test"}
        def enrich(snap, market):
            snap["cash_supplement"] = supplemental
            return snap
        with patch.object(watch, "investor_current", return_value=cash), \
             patch.object(watch, "futures_current", return_value={"source_tr": "t8463"}), \
             patch.object(watch, "market_program_current", return_value={"source_tr": "t1640"}), \
             patch.object(watch, "enrich_snapshot", side_effect=enrich) as enrich_mock:
            primary = watch.fetch_flow_snapshot("dummy", "KOSDAQ", include_supplement=False)
            self.assertNotIn("cash_supplement", primary)
            enrich_mock.assert_not_called()
            full = watch.fetch_flow_snapshot("dummy", "KOSDAQ")
            self.assertEqual(full["cash_supplement"], supplemental)
            self.assertEqual(enrich_mock.call_count, 1)


if __name__ == "__main__":
    unittest.main()
