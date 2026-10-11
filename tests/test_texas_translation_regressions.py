"""Offline regressions: translation, formatting, and delivery-state boundaries."""

import datetime as dt
import json
import pathlib
import sys
import tempfile
import unittest
from contextlib import ExitStack
from unittest.mock import MagicMock, patch

from requests import HTTPError, Timeout

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import texas_data_center_watch as watch
import texas_data_center_alert_formatter as formatter


class FakeClock:
    def __init__(self):
        self.now = 1000.0
        self.sleeps = []

    def monotonic(self):
        return self.now

    def sleep(self, seconds):
        if seconds <= 0:
            raise AssertionError(f"invalid sleep: {seconds}")
        self.sleeps.append(seconds)
        self.now += seconds


class TexasTranslationRegressions(unittest.TestCase):
    def setUp(self):
        self.context = ExitStack()
        self.addCleanup(self.context.close)
        self.clock = FakeClock()
        watch._translate_clean_text.cache_clear()
        self.addCleanup(watch._translate_clean_text.cache_clear)
        self.context.enter_context(patch.object(watch, "_translation_last_request_at", None))
        self.context.enter_context(patch.object(watch.time, "monotonic", self.clock.monotonic))
        self.context.enter_context(patch.object(watch.time, "sleep", self.clock.sleep))
        self.request_translation = watch._request_google_translation
        self.translate = self.context.enter_context(patch.object(watch, "_request_google_translation"))
        self.translate.return_value = "검증된 한국어 번역"
        self.http_get = self.context.enter_context(patch.object(
            watch.requests, "get", side_effect=AssertionError("unexpected translation network access")
        ))
        # No test is allowed to fetch an official source or contact Telegram.
        self.urlopen = self.context.enter_context(patch.object(
            watch.urllib.request, "urlopen", side_effect=AssertionError("unexpected network access")
        ))

    def tearDown(self):
        self.urlopen.assert_not_called()

    def test_success_is_cleaned_and_cached_after_normalization(self):
        self.translate.return_value = "  신규   승인 소식  "
        self.assertEqual(watch.translate_to_korean("New  &amp; approved"), "신규 승인 소식")
        self.assertEqual(watch.translate_to_korean(" New & approved "), "신규 승인 소식")
        self.translate.assert_called_once_with("New & approved")
        self.assertEqual(self.clock.sleeps, [])

    def test_empty_and_already_korean_text_need_no_provider(self):
        self.assertEqual(watch.translate_to_korean("  "), "")
        self.assertEqual(watch.translate_to_korean("신규 승인 소식"), "신규 승인 소식")
        self.translate.assert_not_called()
        self.assertEqual(self.clock.sleeps, [])

    def test_http_adapter_preserves_provider_selectors_and_sets_explicit_timeouts(self):
        self.http_get.side_effect = None
        response = self.http_get.return_value.__enter__.return_value
        response.status_code = 200
        response.headers = {}
        for selector in ("t0", "result-container"):
            with self.subTest(selector=selector):
                response.text = f'<html><div class="{selector}">신규 <span>승인</span></div></html>'
                self.assertEqual(self.request_translation("New approval"), "신규 승인")
                self.http_get.assert_called_with(
                    "https://translate.google.com/m",
                    params={"sl": "auto", "tl": "ko", "q": "New approval"},
                    timeout=(5, 15),
                    allow_redirects=False,
                )
        self.assertEqual(response.raise_for_status.call_count, 2)
        self.assertEqual(self.http_get.return_value.__exit__.call_count, 2)

    def test_http_adapter_rejects_error_status_and_missing_translation_element(self):
        self.http_get.side_effect = None
        response = self.http_get.return_value.__enter__.return_value
        response.status_code = 200
        response.headers = {}
        response.raise_for_status.side_effect = HTTPError("503 Service Unavailable")
        with self.assertRaisesRegex(HTTPError, "503"):
            self.request_translation("New approval")
        response.raise_for_status.side_effect = None
        response.text = "<html><body>No translation available</body></html>"
        with self.assertRaisesRegex(RuntimeError, "translation response missing text"):
            self.request_translation("New approval")

    def test_http_timeouts_use_bounded_retries_and_fail_closed(self):
        self.translate.side_effect = self.request_translation
        self.http_get.side_effect = Timeout("read timed out")
        with self.assertRaisesRegex(RuntimeError, "한국어 번역 실패.*read timed out"):
            watch.translate_to_korean("New approval")
        self.assertEqual(self.http_get.call_count, 4)
        self.assertEqual(self.clock.sleeps, [5, 15, 30])
        self.assertTrue(all(call.kwargs["timeout"] == (5, 15) for call in self.http_get.call_args_list))
        self.assertEqual(watch._translate_clean_text.cache_info().currsize, 0)

    def test_http_adapter_preserves_provider_input_length_limit(self):
        with self.assertRaisesRegex(ValueError, "shorter than 5000"):
            self.request_translation("x" * 5000)
        self.http_get.assert_not_called()

    def test_distinct_requests_are_paced_from_completion(self):
        call_times = []

        def translate(text):
            call_times.append(self.clock.now)
            self.clock.now += 2.0
            return "검증된 번역"

        self.translate.side_effect = translate
        watch.translate_to_korean("First title")
        watch.translate_to_korean("Second title")
        self.assertEqual(call_times, [1000.0, 1003.0])
        self.assertEqual(self.clock.sleeps, [watch.TRANSLATION_MIN_INTERVAL])

    def test_transient_failure_recovers_with_bounded_backoff(self):
        self.translate.side_effect = [HTTPError("503 Service Unavailable"), "신규 승인"]
        self.assertEqual(watch.translate_to_korean("New approval"), "신규 승인")
        self.assertEqual(self.translate.call_count, 2)
        self.assertEqual(self.clock.sleeps, [5])

    def test_exhaustion_is_fail_closed_and_never_cached(self):
        self.translate.side_effect = RuntimeError("Too many requests")
        with self.assertRaisesRegex(RuntimeError, "한국어 번역 실패"):
            watch.translate_to_korean("New approval")
        self.assertEqual(self.translate.call_count, 4)
        # No pointless wait after the final failed attempt.
        self.assertEqual(self.clock.sleeps, [5, 15, 30])
        self.assertEqual(watch._translate_clean_text.cache_info().currsize, 0)
        self.translate.side_effect = None
        self.translate.return_value = "신규 승인"
        self.assertEqual(watch.translate_to_korean("New approval"), "신규 승인")
        self.assertEqual(self.translate.call_count, 5)
        self.assertEqual(self.clock.sleeps[-1], watch.TRANSLATION_MIN_INTERVAL)

    def test_no_korean_or_empty_result_never_becomes_a_cached_success(self):
        for invalid in ("Untranslated English", "", None):
            with self.subTest(result=invalid):
                self.translate.return_value = invalid
                with self.assertRaisesRegex(RuntimeError, "translation returned no Korean text"):
                    watch.translate_to_korean("A pending project")
                self.assertEqual(watch._translate_clean_text.cache_info().currsize, 0)

    def test_invalid_result_can_recover_without_caching_the_invalid_value(self):
        self.translate.side_effect = ["Untranslated English", "정상 번역"]
        self.assertEqual(watch.translate_to_korean("A pending project"), "정상 번역")
        self.assertEqual(watch.translate_to_korean("A pending project"), "정상 번역")
        self.assertEqual(self.translate.call_count, 2)

    def test_last_allowed_attempt_can_succeed(self):
        self.translate.side_effect = [HTTPError("503 Service Unavailable")] * 3 + ["정상 번역"]
        self.assertEqual(watch.translate_to_korean("A pending project"), "정상 번역")
        self.assertEqual(self.translate.call_count, 4)
        self.assertEqual(self.clock.sleeps, [5, 15, 30])

    def configure_watcher(self, directory, events):
        out_dir = directory / "out"
        out_dir.mkdir()
        state_path = directory / "state.json"
        state = {"source_version": watch.SOURCE_VERSION, "seen_keys": ["already-seen"]}
        state_path.write_text(json.dumps(state), encoding="utf-8")
        self.context.enter_context(patch.object(watch, "OUT_DIR", out_dir))
        self.context.enter_context(patch.object(watch, "STATE_PATH", state_path))
        self.context.enter_context(patch.object(watch, "collect_governor", return_value=events))
        self.context.enter_context(patch.object(watch, "collect_ercot", return_value=[]))
        self.context.enter_context(patch.object(watch, "collect_puct_search", return_value=[]))
        self.context.enter_context(patch.object(watch, "now_kst", return_value=dt.datetime(
            2026, 10, 11, 12, 0, tzinfo=watch.ZoneInfo("Asia/Seoul")
        )))
        return out_dir, state_path, state_path.read_bytes()

    def test_watcher_and_formatter_share_validated_translations_across_process_boundary(self):
        event = watch.Event("ERCOT", "New approval", "https://www.ercot.com/news/release/test",
                            "2026-10-11", "Grid interconnection approved")
        with tempfile.TemporaryDirectory() as tmp:
            out_dir, state_path, original_state = self.configure_watcher(pathlib.Path(tmp), [event, event])
            self.translate.side_effect = ["신규 승인", "전력망 계통연결 승인"]
            watch.main()
            payload_path = out_dir / "texas_data_center_watch_alert.json"
            payload = json.loads(payload_path.read_text(encoding="utf-8"))
            self.assertEqual(len(payload), 1)
            self.assertEqual(payload[0]["title"], event.title)
            self.assertEqual(payload[0]["title_ko"], "신규 승인")
            self.assertEqual(payload[0]["detail_ko"], "전력망 계통연결 승인")
            self.assertEqual(self.translate.call_count, 2)
            # Simulate the formatter's separate process: in-memory cache is gone.
            watch._translate_clean_text.cache_clear()
            self.translate.side_effect = AssertionError("formatter must reuse validated translations")
            output_path = out_dir / "texas_data_center_watch_telegram.md"
            with patch.object(formatter, "IN_PATH", payload_path), patch.object(formatter, "OUT_PATH", output_path):
                formatter.main()
            output = output_path.read_text(encoding="utf-8")
            self.assertIn("신규 승인", output)
            self.assertIn("전력망 계통연결 승인", output)
            self.assertNotIn(event.title, output)
            self.assertEqual(self.translate.call_count, 2)
            # Even success only creates pending state; confirmed delivery owns persistence.
            self.assertEqual(state_path.read_bytes(), original_state)

    def test_watcher_translation_failure_does_not_advance_state_or_emit_alert(self):
        event = watch.Event("ERCOT", "New approval", "https://www.ercot.com/test", detail="Grid change")
        for failures in ([RuntimeError("rate limited")] * 4,
                         ["신규 승인"] + [RuntimeError("rate limited")] * 4,
                         ["Untranslated English"] * 4):
            with self.subTest(failures=failures), tempfile.TemporaryDirectory() as tmp:
                watch._translate_clean_text.cache_clear()
                self.translate.side_effect = failures
                out_dir, state_path, original_state = self.configure_watcher(pathlib.Path(tmp), [event])
                with self.assertRaisesRegex(RuntimeError, "한국어 번역 실패"):
                    watch.main()
                self.assertEqual(state_path.read_bytes(), original_state)
                self.assertFalse((out_dir / "texas_data_center_watch_alert.md").exists())
                self.assertFalse((out_dir / "texas_data_center_watch_alert.json").exists())
                self.assertFalse((out_dir / "texas_data_center_watch_telegram.md").exists())

    def test_payload_reuse_does_not_expand_existing_ten_event_translation_limit(self):
        events = [watch.Event("ERCOT", f"New approval {idx}", f"https://www.ercot.com/test/{idx}",
                              detail=f"Grid change {idx}") for idx in range(11)]
        with tempfile.TemporaryDirectory() as tmp:
            out_dir, state_path, original_state = self.configure_watcher(pathlib.Path(tmp), events)
            watch.main()
            payload = json.loads((out_dir / "texas_data_center_watch_alert.json").read_text(encoding="utf-8"))
            self.assertEqual(len(payload), 11)
            self.assertTrue(all("title_ko" in event and "detail_ko" in event for event in payload[:10]))
            self.assertNotIn("title_ko", payload[10])
            self.assertNotIn("detail_ko", payload[10])
            self.assertEqual(self.translate.call_count, 20)
            self.assertEqual(state_path.read_bytes(), original_state)

    def test_surplus_event_stays_unseen_and_is_in_the_next_delivery(self):
        events = [watch.Event("ERCOT", f"New approval {idx}", f"https://www.ercot.com/test/{idx}")
                  for idx in range(11)]
        with tempfile.TemporaryDirectory() as tmp:
            out_dir, state_path, original_state = self.configure_watcher(pathlib.Path(tmp), events)
            watch.main()
            payload_path = out_dir / "texas_data_center_watch_alert.json"
            payload = json.loads(payload_path.read_text(encoding="utf-8"))
            pending_path = out_dir / "texas_data_center_watch_pending_state.json"
            pending = json.loads(pending_path.read_text(encoding="utf-8"))
            delivered = {watch.Event(**{key: event[key] for key in ("source", "title", "url", "date", "detail")}).key
                         for event in payload[:10]}
            surplus = next(event for event in events if event.key not in delivered)
            self.assertEqual(set(pending["seen_keys"]), delivered | {"already-seen"})
            self.assertNotIn(surplus.key, pending["seen_keys"])
            self.assertEqual(state_path.read_bytes(), original_state)
            # Model the workflow's state copy after confirmed delivery, locally.
            state_path.write_bytes(pending_path.read_bytes())
            watch.main()
            next_payload = json.loads(payload_path.read_text(encoding="utf-8"))
            self.assertEqual(len(next_payload), 1)
            self.assertEqual(next_payload[0]["title"], surplus.title)
            self.assertIn("title_ko", next_payload[0])
            next_pending = json.loads(pending_path.read_text(encoding="utf-8"))
            self.assertEqual(set(next_pending["seen_keys"]), {event.key for event in events} | {"already-seen"})
            self.assertNotIn(surplus.key, json.loads(state_path.read_text(encoding="utf-8"))["seen_keys"])

    def test_initial_baseline_still_marks_all_current_events_without_translating(self):
        events = [watch.Event("ERCOT", f"Existing approval {idx}", f"https://www.ercot.com/test/{idx}")
                  for idx in range(11)]
        with tempfile.TemporaryDirectory() as tmp:
            out_dir, state_path, original_state = self.configure_watcher(pathlib.Path(tmp), events)
            state_path.unlink()
            watch.main()
            pending = json.loads((out_dir / "texas_data_center_watch_pending_state.json").read_text(encoding="utf-8"))
            self.assertEqual(set(pending["seen_keys"]), {event.key for event in events})
            self.assertTrue((out_dir / "texas_data_center_watch_rebaseline.txt").exists())
            self.assertFalse((out_dir / "texas_data_center_watch_alert.json").exists())
            self.assertFalse(state_path.exists())
            self.translate.assert_not_called()

    def test_legacy_formatter_payload_uses_shared_fail_closed_translator(self):
        event = {"title": "New approval", "detail": "", "url": "https://www.ercot.com/test"}
        self.translate.side_effect = RuntimeError("rate limited")
        with self.assertRaisesRegex(RuntimeError, "한국어 번역 실패"):
            formatter.generic_message(event)
        self.assertEqual(self.translate.call_count, 4)

    def test_formatter_rejects_invalid_serialized_translation_without_english_fallback(self):
        for field in ("title", "detail"):
            for invalid in ("English text", "", None):
                with self.subTest(field=field, value=invalid):
                    event = {"title": "New approval", "title_ko": "신규 승인", "detail": "Grid change",
                             "detail_ko": "계통 변화", "url": "https://www.ercot.com/test"}
                    event[f"{field}_ko"] = invalid
                    with self.assertRaisesRegex(RuntimeError, f"invalid {field}_ko"):
                        formatter.generic_message(event)
        self.translate.assert_not_called()

    def test_failed_formatter_does_not_create_telegram_output(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = pathlib.Path(tmp)
            input_path, output_path = root / "input.json", root / "telegram.md"
            input_path.write_text(json.dumps([{"title": "New approval", "title_ko": "English only"}]),
                                  encoding="utf-8")
            with patch.object(formatter, "IN_PATH", input_path), patch.object(formatter, "OUT_PATH", output_path):
                with self.assertRaisesRegex(RuntimeError, "invalid title_ko"):
                    formatter.main()
            self.assertFalse(output_path.exists())

    def test_workflow_keeps_delivery_and_commit_gates_and_runs_offline_regressions(self):
        workflow = (ROOT / ".github/workflows/texas-data-center-watch-telegram.yml").read_text(encoding="utf-8")
        self.assertIn("python -m unittest discover -s tests -p 'test_texas_translation_regressions.py'", workflow)
        self.assertLess(workflow.index("Run offline translation regression tests"),
                        workflow.index("Validate Telegram route without sending"))
        for name in ("Persist initial baseline", "Persist state after normal no-change check",
                     "Persist state only after confirmed Telegram delivery", "Commit Texas data-center state"):
            step = workflow.split(f"- name: {name}\n", 1)[1].split("- name:", 1)[0]
            self.assertIn("if: success() &&", step)
        delivery = workflow.split("- name: Persist state only after confirmed Telegram delivery\n", 1)[1]
        self.assertIn("hashFiles('out/texas_data_center_watch_telegram_confirmed.json') != ''", delivery.split("run:", 1)[0])


class TexasRecoveryTests(unittest.TestCase):
    def tearDown(self):
        watch._translate_clean_text.cache_clear()

    def test_podcast_distribution_is_not_datacenter_event(self):
        self.assertFalse(watch.relevant('REVISED: ERCOT Launches Podcast',
            'ERCOT introduces an electricity podcast. Distribution includes Amazon Music.'))

    def test_music_disambiguation_preserves_real_material_change(self):
        self.assertTrue(watch.relevant('ERCOT podcast announces data center approval',
            'The episode appears on Amazon Music. PUCT approved a data center grid connection.'))

    def test_amazon_project_remains_relevant(self):
        self.assertTrue(watch.relevant('Amazon announces Texas project',
            'Amazon commits to funding transmission and generation for its data center.'))

    def test_large_load_approval_remains_relevant(self):
        self.assertTrue(watch.relevant('PUCT Approves ERCOT Batch Zero Process',
            'The process connects large electricity users while protecting system reliability.'))

    def test_explicit_blocks_make_one_request_without_sleep_or_cache(self):
        for status, headers in [(429, {}), (403, {}), (302, {'Location':'https://www.google.com/sorry/index'}),
                                (302, {'Location':'https://unexpected.example/'})]:
            with self.subTest(status=status, headers=headers):
                watch._translation_last_request_at = None
                response=MagicMock(status_code=status, headers=headers)
                with patch.object(watch.requests, 'get') as get, patch.object(watch.time, 'sleep') as sleep:
                    get.return_value.__enter__.return_value=response
                    with self.assertRaises(watch.TranslationProviderBlocked):
                        watch.translate_to_korean('A new project approval')
                    get.assert_called_once()
                    self.assertFalse(get.call_args.kwargs['allow_redirects'])
                    sleep.assert_not_called()
                    self.assertEqual(watch._translate_clean_text.cache_info().currsize, 0)

    def test_successful_translation_still_validated(self):
        watch._translation_last_request_at = None
        response=MagicMock(status_code=200, headers={}, text='<div class="result-container">새 프로젝트 승인</div>')
        with patch.object(watch.requests, 'get') as get:
            get.return_value.__enter__.return_value=response
            self.assertEqual(watch.translate_to_korean('New project approval'), '새 프로젝트 승인')
            self.assertEqual(get.call_args.kwargs['timeout'], (5,15))


if __name__ == "__main__":
    unittest.main()
