import contextlib
import io
import json
import pathlib
import sys
import tempfile
import unittest
import urllib.error
from unittest.mock import MagicMock, patch

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "scripts"))
import clarity_watch as mod
import source_collection_health as health


class ClaritySourceHealthTest(unittest.TestCase):
    def setUp(self):
        mod.reset_fetch_cache()
        self.url = "https://www.sec.gov/taxonomy/term/193081"

    def response(self, payload=b"<html></html>"):
        response = MagicMock()
        response.__enter__.return_value.read.return_value = payload
        return response

    def test_denied_source_is_not_retried_even_with_query_variation(self):
        error = urllib.error.HTTPError(self.url, 403, "Forbidden", {}, None)
        with patch.object(mod.urllib.request, "urlopen", side_effect=error) as open_, patch.object(mod.time, "sleep") as sleep:
            for url in (self.url, self.url, self.url + "?page=0"):
                with self.assertRaisesRegex(RuntimeError, "status=403 attempts=1"):
                    mod.fetch(url)
        self.assertEqual(open_.call_count, 1)
        sleep.assert_not_called()

    def test_retryable_503_can_recover_then_reuses_current_pass_only(self):
        error = urllib.error.HTTPError(self.url, 503, "Unavailable", {}, None)
        with patch.object(mod.urllib.request, "urlopen", side_effect=[error, self.response(b"fresh"), self.response(b"next")]) as open_, patch.object(mod.time, "sleep"):
            self.assertEqual(mod.fetch(self.url), b"fresh")
            self.assertEqual(mod.fetch(self.url), b"fresh")
            mod.reset_fetch_cache()
            self.assertEqual(mod.fetch(self.url), b"next")
        self.assertEqual(open_.call_count, 3)

    def test_429_and_retry_after_defer_without_early_retry(self):
        for code in (429, 503):
            mod.reset_fetch_cache()
            error = urllib.error.HTTPError(self.url, code, "Busy", {"Retry-After": "120"}, None)
            with patch.object(mod.urllib.request, "urlopen", side_effect=error) as open_, patch.object(mod.time, "sleep") as sleep:
                with self.assertRaises(RuntimeError):
                    mod.fetch(self.url)
                self.assertEqual(open_.call_count, 1)
                sleep.assert_not_called()

    def test_static_backfill_never_conceals_all_discovery_failures(self):
        with patch.object(mod, "fetch", side_effect=RuntimeError("blocked")):
            errors = []
            events = mod.collect_sec_exchange_orders(errors)
        self.assertEqual(events, [])
        self.assertTrue(any("discovery incomplete" in e for e in errors))
        self.assertTrue(any("direct order" in e for e in errors))

    def test_known_pdf_does_not_conceal_discovery_failures(self):
        def fetch(url, timeout=30):
            if url.endswith(".pdf"):
                return b"%PDF-test"
            raise RuntimeError("blocked")
        with patch.object(mod, "fetch", side_effect=fetch):
            errors = []
            events = mod.collect_sec_exchange_orders(errors)
        self.assertEqual(len(events), 1)
        self.assertTrue(any("discovery incomplete" in e for e in errors))

    def test_html_block_page_cannot_confirm_a_direct_pdf(self):
        with patch.object(mod, "fetch", return_value=b"<html>Access denied</html>"):
            errors = []
            events = mod.collect_sec_exchange_orders(errors)
        self.assertEqual(events, [])
        self.assertTrue(any("not a PDF" in e for e in errors))

    def test_html_200_challenge_and_unrecognized_index_remain_incomplete(self):
        for body in (b"<html><title>Access Denied</title></html>", b"<html>unrecognized</html>"):
            with self.subTest(body=body), patch.object(mod, "fetch", side_effect=lambda url, timeout=30: b"%PDF-test" if url.endswith(".pdf") else body):
                errors = []
                self.assertEqual(len(mod.collect_sec_exchange_orders(errors)), 1)
                self.assertTrue(any("discovery incomplete" in e for e in errors))

    def test_known_edgar_gap_is_never_silently_marked_complete(self):
        with contextlib.ExitStack() as stack:
            for name in ("parse_rss", "collect_federal_register", "collect_reginfo_reviews", "collect_sec_sro_crypto_orders", "collect_sec_exchange_orders", "collect_volatility_shares_3x_crypto_launch"):
                stack.enter_context(patch.object(mod, name, return_value=[]))
            errors = []
            self.assertEqual(mod.collect_regulators(errors), [])
            self.assertTrue(any("EDGAR" in e and "unavailable" in e for e in errors))

    def test_corrupt_or_truncated_state_cannot_rebaseline_or_emit(self):
        for payload in ("{truncated", "{}", json.dumps({"initialized": True, "source_version": 2})):
            with self.run_fixture() as (out, state_path, original, event):
                state_path.write_text(payload)
                with self.assertRaisesRegex(RuntimeError, "refusing rebaseline"):
                    mod.main()
                self.assertEqual(state_path.read_text(), payload)
                self.assertFalse((out / "clarity_watch_pending_state.json").exists())
                self.assertFalse((out / "clarity_watch_alert.json").exists())

    @contextlib.contextmanager
    def run_fixture(self, initialized=True):
        with tempfile.TemporaryDirectory() as directory, contextlib.ExitStack() as stack:
            out = pathlib.Path(directory)
            state_path = out / "state.json"
            original = {"initialized": initialized, "source_version": mod.SOURCE_VERSION,
                        "seen_event_keys": ["previous-sec-key"], "last_complete_check_kst": "2026-10-10T09:00:00+09:00"}
            state_path.write_text(json.dumps(original))
            event = mod.Event("상원 본회의", "표결 결과", "CLARITY passed", "https://www.senate.gov/example")
            stack.enter_context(patch.object(mod, "STATE_PATH", state_path))
            stack.enter_context(patch.object(mod, "OUT_DIR", out))
            stack.enter_context(patch.object(mod.urllib.request, "urlopen", side_effect=AssertionError("network prohibited")))
            for name in ("collect_banking", "collect_agriculture", "collect_floor", "collect_whitehouse"):
                stack.enter_context(patch.object(mod, name, return_value=[]))
            stack.enter_context(patch.object(mod, "collect_govinfo", return_value=[event]))
            def failed_sec(errors):
                errors.append("SEC discovery: HTTPError status=403")
                return []
            stack.enter_context(patch.object(mod, "collect_regulators", side_effect=failed_sec))
            yield out, state_path, original, event

    def test_partial_first_pass_cannot_bootstrap_or_advance_state(self):
        with self.run_fixture(initialized=False) as (out, state_path, original, event):
            (out / "clarity_watch_pending_state.json").write_text("stale")
            (out / "clarity_watch_alert.json").write_text("stale")
            self.assertEqual(mod.main(), 2)
            self.assertEqual(json.loads(state_path.read_text()), original)
            self.assertFalse((out / "clarity_watch_pending_state.json").exists())
            self.assertFalse((out / "clarity_watch_alert.json").exists())

    def test_independent_event_repeats_until_delivery_then_only_once(self):
        with self.run_fixture() as (out, state_path, original, event):
            self.assertEqual(mod.main(), 0)
            pending = json.loads((out / "clarity_watch_pending_state.json").read_text())
            self.assertFalse(pending["collection_complete"])
            self.assertEqual(pending["last_complete_check_kst"], original["last_complete_check_kst"])
            self.assertEqual(set(pending["seen_event_keys"]), {"previous-sec-key", event.key})
            self.assertEqual(json.loads(state_path.read_text()), original)
            # No delivery: the durable baseline is unchanged, so retry remains eligible.
            self.assertEqual(mod.main(), 0)
            self.assertEqual(len(json.loads((out / "clarity_watch_alert.json").read_text())), 1)
            # Simulate only the workflow's confirmed-delivery state copy; no sender is called.
            state_path.write_text(json.dumps(pending))
            capture = io.StringIO()
            with contextlib.redirect_stdout(capture):
                self.assertEqual(mod.main(), 0)
            self.assertFalse((out / "clarity_watch_alert.json").exists())
            self.assertIn("unknown_incomplete", capture.getvalue())
            self.assertNotIn("clarity_new_official_change=false", capture.getvalue())

    def test_workflow_persists_alert_state_only_after_confirmation(self):
        root = pathlib.Path(__file__).resolve().parents[1]
        workflow = (root / ".github/workflows/clarity-watch-telegram.yml").read_text()
        self.assertIn("hashFiles('out/clarity_watch_telegram_chunks.json') == ''", workflow)
        self.assertIn("hashFiles('out/clarity_watch_telegram_confirmed.json') != ''", workflow)

    def test_partial_notice_reaches_final_chunks_once_without_creating_an_alert(self):
        with tempfile.TemporaryDirectory() as directory:
            out = pathlib.Path(directory)
            self.assertFalse(health.append_clarity_notice(out))
            (out / "clarity_watch_pending_state.json").write_text(json.dumps({"initialized": True, "source_version": 2, "seen_event_keys": ["confirmed"], "source_errors": ["SEC blocked"], "collection_complete": False}))
            chunks = out / "clarity_watch_telegram_chunks.json"
            chunks.write_text(json.dumps(["verified event"]));
            self.assertTrue(health.append_clarity_notice(out))
            self.assertTrue(health.append_clarity_notice(out))
            self.assertEqual(json.loads(chunks.read_text()), ["verified event", health.CLARITY_NOTICE])
            with self.assertRaisesRegex(RuntimeError, "coverage incomplete"):
                health.require_complete(out, "clarity")

    def test_completeness_gate_fails_closed_for_false_missing_or_corrupt_health(self):
        with tempfile.TemporaryDirectory() as directory:
            out = pathlib.Path(directory)
            for lane, filename, field in (("clarity", "clarity_watch_pending_state.json", "collection_complete"), ("maplight", "optogenetics_translation_watch_pending_state.json", "maplight_health_ok")):
                path = out / filename
                for value in ({field: False}, {}, [], {field: "true"}):
                    path.write_text(json.dumps(value))
                    with self.assertRaises((RuntimeError, ValueError)):
                        health.require_complete(out, lane)
                valid = {field: True}
                if lane == "clarity":
                    valid.update({"initialized": True, "source_version": 2, "seen_event_keys": [], "source_errors": []})
                path.write_text(json.dumps(valid))
                health.require_complete(out, lane)

    def test_final_chunks_cannot_proceed_with_invalid_pending_checkpoint(self):
        with tempfile.TemporaryDirectory() as directory:
            out = pathlib.Path(directory)
            chunks = out / "clarity_watch_telegram_chunks.json"
            chunks.write_text(json.dumps(["verified event"]))
            for state in ({}, {"collection_complete": "true"}, {"collection_complete": True}, {"initialized": True, "source_version": 2, "seen_event_keys": [], "source_errors": ["blocked"], "collection_complete": True}):
                (out / "clarity_watch_pending_state.json").write_text(json.dumps(state))
                with self.assertRaises(ValueError):
                    health.append_clarity_notice(out)

    def test_health_failure_is_after_state_commit_and_manual_runs_are_main_only(self):
        root = pathlib.Path(__file__).resolve().parents[1]
        for name, commit_label, check in (("clarity-watch-telegram.yml", "Commit CLARITY states", "clarity-check"), ("bio-qlex-intismeran-watch.yml", "Commit bio watch states", "maplight-check")):
            workflow = (root / ".github/workflows" / name).read_text()
            self.assertIn("if: github.ref == 'refs/heads/main'", workflow)
            self.assertGreater(workflow.index("source_collection_health.py " + check), workflow.index(commit_label))


if __name__ == "__main__":
    unittest.main()
