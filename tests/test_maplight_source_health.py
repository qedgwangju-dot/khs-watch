import contextlib
import datetime as dt
import json
import pathlib
import ssl
import sys
import tempfile
import unittest
import urllib.error
from email.utils import format_datetime
from unittest.mock import patch

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "scripts"))
import optogenetics_translation_watch as mod


class MapLightSourceHealthTest(unittest.TestCase):
    def error(self, code, headers=None):
        return urllib.error.HTTPError(mod.MAPLIGHT_RSS, code, "fixture", headers or {}, None)

    def test_403_is_classified_and_never_retried(self):
        with patch.object(mod, "fetch_text", side_effect=self.error(403)) as fetch, patch.object(mod.time, "sleep") as sleep:
            with self.assertRaisesRegex(mod.MapLightFetchError, "status=403 retryable=false attempts=1"):
                mod.fetch_maplight_rss()
        fetch.assert_called_once_with(mod.MAPLIGHT_RSS, timeout=35)
        sleep.assert_not_called()

    def test_transient_503_recovers_without_changing_source(self):
        with patch.object(mod, "fetch_text", side_effect=[self.error(503), "<rss/>"]) as fetch, patch.object(mod.time, "sleep") as sleep:
            self.assertEqual(mod.fetch_maplight_rss(), "<rss/>")
        self.assertEqual(fetch.call_count, 2)
        self.assertTrue(all(c.args == (mod.MAPLIGHT_RSS,) for c in fetch.call_args_list))
        sleep.assert_called_once_with(1.0)

    def test_exhaustion_is_bounded_and_preserves_status(self):
        with patch.object(mod, "fetch_text", side_effect=self.error(502)) as fetch, patch.object(mod.time, "sleep") as sleep:
            with self.assertRaisesRegex(mod.MapLightFetchError, "status=502 retryable=true attempts=3"):
                mod.fetch_maplight_rss()
        self.assertEqual(fetch.call_count, 3)
        self.assertEqual(sleep.call_count, 2)

    def test_retry_after_is_honored_not_capped_earlier(self):
        with patch.object(mod, "fetch_text", side_effect=[self.error(429, {"Retry-After": "10"}), "ok"]), patch.object(mod.time, "sleep") as sleep:
            self.assertEqual(mod.fetch_maplight_rss(), "ok")
        sleep.assert_called_once_with(10.0)
        for header in ("120", "invalid", format_datetime(dt.datetime.now(dt.timezone.utc) + dt.timedelta(minutes=10))):
            with self.subTest(header=header), patch.object(mod, "fetch_text", side_effect=self.error(429, {"Retry-After": header})) as fetch, patch.object(mod.time, "sleep") as sleep:
                with self.assertRaises(mod.MapLightFetchError):
                    mod.fetch_maplight_rss()
                self.assertEqual(fetch.call_count, 1)
                sleep.assert_not_called()

    def test_timeout_retries_but_tls_certificate_failure_does_not(self):
        with patch.object(mod, "fetch_text", side_effect=[TimeoutError(), "ok"]), patch.object(mod.time, "sleep"):
            self.assertEqual(mod.fetch_maplight_rss(), "ok")
        error = urllib.error.URLError(ssl.SSLCertVerificationError("fixture"))
        with patch.object(mod, "fetch_text", side_effect=error) as fetch, patch.object(mod.time, "sleep") as sleep:
            with self.assertRaisesRegex(mod.MapLightFetchError, "SSLCertVerificationError"):
                mod.fetch_maplight_rss()
            self.assertEqual(fetch.call_count, 1)
            sleep.assert_not_called()

    def test_xml_parse_failure_is_not_retried_or_treated_as_success(self):
        with patch.object(mod, "fetch_text", return_value="not XML") as fetch, patch.object(mod.time, "sleep") as sleep:
            with self.assertRaises(mod.ET.ParseError):
                mod.validate_maplight_bridge_and_events()
        self.assertEqual(fetch.call_count, 1)
        sleep.assert_not_called()

    def test_discovery_rejects_malformed_or_paginated_payload(self):
        for value in ({}, {"studies": None}, {"studies": [] , "nextPageToken": "more"}, {"studies": [{}]}):
            with self.subTest(value=value), patch.object(mod, "fetch_json", return_value=value):
                with self.assertRaises(ValueError):
                    mod.discover_maplight_trials()

    def test_corrupt_or_truncated_existing_state_is_not_an_initial_baseline(self):
        for payload in ("{truncated", "{}", json.dumps({"initialized": True, "seen_event_keys": []})):
            with tempfile.TemporaryDirectory() as directory:
                state = pathlib.Path(directory) / "state.json"
                state.write_text(payload)
                with patch.object(mod, "STATE", state):
                    with self.assertRaisesRegex(RuntimeError, "refusing rebaseline"):
                        mod.load_state()
                self.assertEqual(state.read_text(), payload)

    def test_failed_source_preserves_all_maplight_baselines_and_checkpoint(self):
        real_discovery = mod.discover_maplight_trials
        with tempfile.TemporaryDirectory() as directory, contextlib.ExitStack() as stack:
            root = pathlib.Path(directory)
            (root / "out").mkdir()
            (root / "data").mkdir()
            old = {
                "initialized": True, "source_version": 9, "seen_event_keys": [],
                "maplight_track_version": 2,
                "maplight_seen_milestone_keys": ["existing-milestone", "maplight|ml007|vista-results"],
                "maplight_trial_snapshots": {"NCT-maplight": {"overall_status": "RECRUITING"}},
                "maplight_last_successful_check_kst": "2026-10-10T09:00:00+09:00",
                "trial_snapshots": {nct: {} for nct in mod.TRIALS},
            }
            state = root / "data/state.json"
            state.write_text(json.dumps(old))
            for name, value in {"ROOT": root, "STATE": state, "PENDING": root / "out/pending.json", "ALERT": root / "out/alert.md", "STATUS": root / "out/status.md"}.items():
                stack.enter_context(patch.object(mod, name, value))
            stack.enter_context(patch.object(mod.urllib.request, "urlopen", side_effect=AssertionError("network prohibited")))
            stack.enter_context(patch.object(mod, "validate_nobel", return_value=True))
            stack.enter_context(patch.object(mod, "validate_maplight_bridge_and_events", side_effect=self.error(403)))
            stack.enter_context(patch.object(mod, "meaningful_press_links", return_value=[]))
            stack.enter_context(patch.object(mod, "meaningful_google_official_links", return_value=[]))
            stack.enter_context(patch.object(mod, "trial_snapshot", side_effect=lambda nct: (nct, {})))
            stack.enter_context(patch.object(mod, "rv001_registry_snapshot", return_value={}))
            stack.enter_context(patch.object(mod, "discover_maplight_trials", return_value=[{"nct": "NEW", "program": "ML-007C-MA", "snapshot": {}}]))
            stack.enter_context(patch.object(mod, "discover_nonretinal_trials", return_value=[]))
            self.assertEqual(mod.main(), 0)
            pending = json.loads(mod.PENDING.read_text())
            for key in ("maplight_track_version", "maplight_seen_milestone_keys", "maplight_trial_snapshots", "maplight_last_successful_check_kst"):
                self.assertEqual(pending[key], old[key], key)
            self.assertFalse(pending["maplight_health_ok"])
            self.assertFalse(mod.ALERT.exists())
            self.assertEqual(json.loads(state.read_text()), old)
            self.assertIn("status=403", mod.STATUS.read_text())
            # Healthy RSS must not rescue a malformed/empty trial discovery.
            for payload in ({}, {"studies": []}):
                with patch.object(mod, "validate_maplight_bridge_and_events", return_value=(True, [])), patch.object(mod, "discover_maplight_trials", side_effect=real_discovery), patch.object(mod, "fetch_json", return_value=payload):
                    self.assertEqual(mod.main(), 0)
                pending = json.loads(mod.PENDING.read_text())
                self.assertFalse(pending["maplight_health_ok"])
                for key in ("maplight_track_version", "maplight_seen_milestone_keys", "maplight_trial_snapshots", "maplight_last_successful_check_kst"):
                    self.assertEqual(pending[key], old[key], key)
                self.assertFalse(mod.ALERT.exists())


if __name__ == "__main__":
    unittest.main()
