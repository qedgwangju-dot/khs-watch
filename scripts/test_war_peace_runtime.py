#!/usr/bin/env python3
"""Offline collection/replay/deadline tests. No network or Telegram allowed."""
from __future__ import annotations

import datetime as dt
import base64
import hashlib
import json
import multiprocessing as mp
from pathlib import Path
import tempfile
import time
from types import SimpleNamespace
import unittest
import urllib.request
from unittest.mock import patch
from email.utils import format_datetime

import war_peace_reconstruction_watch_runtime as runtime


def forbidden(*args, **kwargs):
    raise AssertionError('live network/send prohibited in offline tests')


class SourcePayloadError(ValueError):
    def __init__(self, body):
        super().__init__('expected RSS/Atom')
        self.response_body = body


def fake_watch(root, queries, *, req=None, news=None):
    root = Path(root)
    out = root / 'out'
    out.mkdir()
    state = root / 'state.json'
    state.write_text('{"seen":["confirmed-old"]}')
    watch = SimpleNamespace(OUT=out, ALERT=out/'alert.txt', PENDING=out/'pending.json',
                            SUMMARY=out/'summary.md', STATE=state, QUERIES=queries)
    watch.req = req or (lambda url, timeout=20: url.encode())
    watch.google_news = news or (lambda query: ([{'raw': watch.req(query)}], None))
    return watch


class DirectCoverageTests(unittest.TestCase):
    def test_actual_timeout_patterns_do_not_count_cross_source_fallback_as_full(self):
        for query, direct, alternate in (
            ('direct-kremlin-news', 'en.kremlin.ru', 't.me'),
            ('direct-kremlin-transcripts', 'en.kremlin.ru', 't.me'),
            ('direct-gdelt-ukraine', 'api.gdeltproject.org', 'bing.com'),
            ('direct-gdelt-iran', 'api.gdeltproject.org', 'bing.com'),
            ('ap-direct-world-rss', 'apnews.com', 'news.google.com'),
            ('__TRUMP_TRUTH_SOCIAL_ENERGY_CEASEFIRE__', 'truthsocial.com', 'news.google.com'),
        ):
            with self.subTest(query=query):
                attempts = [{'host': direct, 'status': 'error'},
                            {'host': alternate, 'status': 'ok'}]
                self.assertEqual(runtime._unverified_direct_fallback(query, attempts), direct)

    def test_original_host_recovery_and_unrelated_fallback_keep_existing_behavior(self):
        attempts = [{'host': 'en.kremlin.ru', 'status': 'error'},
                    {'host': 'en.kremlin.ru', 'status': 'ok'}]
        self.assertIsNone(runtime._unverified_direct_fallback('direct-kremlin-news', attempts))
        attempts = [{'host': 'primary.example', 'status': 'error'},
                    {'host': 'fallback.example', 'status': 'ok'}]
        self.assertIsNone(runtime._unverified_direct_fallback('ordinary-query', attempts))
        self.assertIsNone(runtime._unverified_direct_fallback('direct-kremlin-news', []))


class RuntimeTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        self.network = patch.object(urllib.request, 'urlopen', forbidden)
        self.network.start()

    def tearDown(self):
        self.network.stop()
        self.temporary.cleanup()

    def collect(self, watch, seconds=2, workers=3):
        report = {'complete': False}
        path = watch.OUT/'coverage.json'
        queries, traces = runtime.prefetch(watch, report, path, seconds=seconds, workers=workers,
                                          payload_retry_delay=0)
        return queries, traces, report

    def test_all_queries_parallel_and_ordered_replay_preserves_parent_signals(self):
        watch = fake_watch(self.root, ['slow-deep', 'fast-normal', 'late-material'])
        bucket = []
        def req(url, timeout=20):
            time.sleep(0.04 if url == 'slow-deep' else 0.002)
            return url.encode()
        def news(query):
            raw = watch.req(query)
            bucket.append(query)
            return [{'raw': raw, 'signals': list(bucket)}], None
        watch.req, watch.google_news = req, news
        queries, traces, report = self.collect(watch)
        self.assertEqual(bucket, [])  # workers never mutate parent parser globals
        self.assertEqual(len(report['news']), 3)
        self.assertTrue(all(x['status'] == 'ok' for x in report['news']))
        watch.req = forbidden  # replay must make zero HTTP requests
        restore, verify = runtime.install_replay(watch, queries, traces)
        try:
            rows = [watch.google_news(q)[0][0] for q in queries]
            verify()
        finally:
            restore()
        self.assertEqual(bucket, queries)
        self.assertEqual(rows[-1]['signals'], queries)
        self.assertEqual(rows[-1]['raw'], b'late-material')

    def test_existing_failed_primary_and_successful_fallback_replayed(self):
        watch = fake_watch(self.root, ['fallback'])
        def req(url, timeout=20):
            if url == 'primary':
                raise OSError('primary unavailable')
            return b'fallback material'
        def news(query):
            try:
                result = watch.req('primary')
            except Exception:
                result = watch.req('fallback')
            return [{'raw': result}], None
        watch.req, watch.google_news = req, news
        queries, traces, report = self.collect(watch)
        self.assertEqual(report['news'][0]['requests'], 2)
        self.assertTrue(report['news'][0]['fallback_recovered'])
        self.assertEqual([h['status'] for h in report['news'][0]['http']], ['error', 'ok'])
        watch.req = forbidden
        restore, verify = runtime.install_replay(watch, queries, traces)
        try:
            self.assertEqual(watch.google_news('fallback')[0][0]['raw'], b'fallback material')
            verify()
        finally:
            restore()

    def test_direct_origin_timeout_with_different_fallback_holds_collection(self):
        watch = fake_watch(self.root, ['direct-kremlin-news'])
        def req(url, timeout=20):
            if 'en.kremlin.ru' in url:
                raise TimeoutError('actual direct-source timeout pattern')
            return b'fallback material'
        def news(query):
            try:
                result = watch.req('https://en.kremlin.ru/events/president/news/page/1')
            except Exception:
                result = watch.req('https://t.me/s/news_kremlin')
            return [{'raw': result}], None
        watch.req, watch.google_news = req, news
        with self.assertRaises(runtime.IncompleteCoverage):
            self.collect(watch, workers=1)
        record = json.loads((watch.OUT/'coverage.json').read_text())['news'][0]
        self.assertEqual(record['status'], 'partial')
        self.assertEqual(record['coverage_issue']['original_host'], 'en.kremlin.ru')
        self.assertTrue(record['fallback_recovered'])

    def test_denied_primary_malformed_fallback_recovers_without_retrying_denial(self):
        from urllib.error import HTTPError
        watch = fake_watch(self.root, ['fallback'])
        calls = mp.get_context('fork').Array('i', [0, 0])
        valid = b'<rss><channel/></rss>'
        def req(url, timeout=20):
            index = 0 if 'api.gdeltproject.org' in url else 1
            with calls.get_lock():
                calls[index] += 1
                attempt = calls[index]
            if index == 0:
                raise HTTPError(url, 429, 'rate limited', {}, None)
            if attempt == 1:
                raise SourcePayloadError(b'<html><body/></html>')
            return valid
        def news(query):
            try:
                raw = watch.req('https://api.gdeltproject.org/api/v2/doc/doc?format=json')
            except Exception:
                try:
                    raw = watch.req('https://www.bing.com/news/search?q=fixture&format=RSS')
                except Exception:
                    return [], 'GDELT: HTTPError'
            return [{'raw': raw}], None
        watch.req, watch.google_news = req, news
        queries, traces, report = self.collect(watch, workers=1)
        self.assertEqual(list(calls), [1, 2])
        record = report['news'][0]
        self.assertEqual(record['status'], 'ok')
        self.assertTrue(record['fallback_recovered'])
        self.assertEqual(record['payload_retry_attempts'], 1)
        self.assertEqual(record['initial_attempt']['status'], 'error')
        self.assertEqual(report['blocked_providers']['api.gdeltproject.org']['code'], 429)
        self.assertEqual(record['http'][-1]['status'], 'ok')
        watch.req = forbidden
        restore, verify = runtime.install_replay(watch, queries, traces)
        try:
            self.assertEqual(watch.google_news('fallback')[0][0]['raw'], valid)
            verify()
        finally:
            restore()

    def test_empty_success_and_expired_no_request_sentinel_retained(self):
        watch = fake_watch(self.root, ['empty', 'expired'])
        watch.google_news = lambda q: ((watch.req(q) and []) if q == 'empty' else [], None)
        queries, traces, report = self.collect(watch)
        self.assertEqual(queries, ['empty', 'expired'])
        self.assertEqual(traces[1], [])
        self.assertTrue(all(x['status'] == 'ok' for x in report['news']))

    def test_one_failed_source_is_not_partial_success(self):
        watch = fake_watch(self.root, ['good', 'bad'])
        watch.google_news = lambda q: ([], 'source error' if q == 'bad' else None)
        with self.assertRaises(runtime.IncompleteCoverage):
            self.collect(watch)
        report = json.loads((watch.OUT/'coverage.json').read_text())
        self.assertEqual([x['status'] for x in report['news']], ['ok', 'error'])
        self.assertFalse(report['complete'])

    def test_malformed_rss_recovers_once_after_initial_batch_and_replays_only_verified_bytes(self):
        watch = fake_watch(self.root, ['https://source.example/?format=rss', 'https://healthy.example/'])
        calls = mp.get_context('fork').Value('i', 0)
        original = b'<html>temporarily unavailable</html>'
        valid = b'<rss><channel/></rss>'
        def req(url, timeout=20):
            if 'source.example' in url:
                with calls.get_lock():
                    calls.value += 1
                    attempt = calls.value
                if attempt == 1:
                    raise SourcePayloadError(original)
            return valid
        watch.req = req
        queries, traces, report = self.collect(watch, workers=1)
        self.assertEqual(calls.value, 2)
        record = report['news'][0]
        self.assertEqual(record['status'], 'ok')
        self.assertNotIn('error', record)
        self.assertEqual(report['payload_retry_queries'], [0])
        failure = record['initial_attempt']['http'][0]
        self.assertEqual(base64.b64decode(failure['response_body_base64']), original)
        self.assertEqual(failure['sha256'], hashlib.sha256(original).hexdigest())
        watch.req = forbidden
        restore, verify = runtime.install_replay(watch, queries, traces)
        try:
            self.assertEqual([watch.google_news(q)[0][0]['raw'] for q in queries], [valid, valid])
            verify()
        finally:
            restore()
        self.assertEqual(json.loads(watch.STATE.read_text())['seen'], ['confirmed-old'])

    def test_persistently_malformed_rss_still_fails_after_only_one_recovery_attempt(self):
        watch = fake_watch(self.root, ['https://source.example/?format=rss'])
        calls = mp.get_context('fork').Value('i', 0)
        def req(url, timeout=20):
            with calls.get_lock(): calls.value += 1
            raise SourcePayloadError(b'<html>unavailable</html>')
        watch.req = req
        with self.assertRaises(runtime.IncompleteCoverage): self.collect(watch)
        self.assertEqual(calls.value, 2)
        report = json.loads((watch.OUT/'coverage.json').read_text())
        self.assertEqual(report['news'][0]['status'], 'error')
        self.assertEqual(report['news'][0]['payload_retry_attempts'], 1)
        self.assertFalse(report['complete'])

    def test_successful_response_in_same_execution_is_not_refetched_or_replaced(self):
        watch = fake_watch(self.root, ['group'])
        calls = mp.get_context('fork').Array('i', [0, 0])
        valid = b'<rss><channel/></rss>'
        def req(url, timeout=20):
            index = 0 if 'healthy' in url else 1
            with calls.get_lock():
                calls[index] += 1
                attempt = calls[index]
            if index == 0 and attempt > 1:
                raise AssertionError('successful current response must not be refetched')
            if index == 1 and attempt == 1:
                raise SourcePayloadError(b'<html>unavailable</html>')
            return valid
        watch.req = req
        watch.google_news = lambda q: ([{'first':watch.req('https://healthy.example/?format=rss'),
                                        'second':watch.req('https://recover.example/?format=rss')}], None)
        queries, traces, report = self.collect(watch, workers=1)
        self.assertEqual(list(calls), [1, 2])
        record = report['news'][0]
        self.assertEqual(record['status'], 'ok')
        self.assertEqual(record['reused_success_requests'], 1)
        self.assertTrue(record['http'][0]['reused_from_initial_attempt'])
        self.assertEqual(record['http'][0]['sha256'], record['initial_attempt']['http'][0]['sha256'])
        self.assertNotIn('reused_from_initial_attempt', record['http'][1])
        watch.req = forbidden
        restore, verify = runtime.install_replay(watch, queries, traces)
        try:
            self.assertEqual(watch.google_news('group')[0][0], {'first':valid, 'second':valid})
            verify()
        finally:
            restore()

    def test_duplicate_url_occurrences_do_not_reuse_a_failed_body(self):
        watch = fake_watch(self.root, ['group'])
        calls = mp.get_context('fork').Value('i', 0)
        first, recovered = b'<rss><channel><title>first</title></channel></rss>', b'<rss><channel><title>recovered</title></channel></rss>'
        def req(url, timeout=20):
            with calls.get_lock():
                calls.value += 1
                attempt = calls.value
            if attempt == 2: raise SourcePayloadError(b'<html>unavailable</html>')
            return first if attempt == 1 else recovered
        watch.req = req
        url = 'https://source.example/?format=rss'
        watch.google_news = lambda q: ([{'first':watch.req(url), 'second':watch.req(url)}], None)
        queries, traces, report = self.collect(watch, workers=1)
        self.assertEqual(calls.value, 3)
        self.assertEqual(report['news'][0]['reused_success_requests'], 1)
        watch.req = forbidden
        restore, verify = runtime.install_replay(watch, queries, traces)
        try:
            self.assertEqual(watch.google_news('group')[0][0], {'first':first, 'second':recovered})
            verify()
        finally:
            restore()

    def test_recovery_retry_cannot_extend_total_deadline_or_leave_a_worker(self):
        watch = fake_watch(self.root, ['https://source.example/?format=rss'])
        calls = mp.get_context('fork').Value('i', 0)
        before = {p.pid for p in mp.active_children()}
        def req(url, timeout=20):
            with calls.get_lock():
                calls.value += 1
                attempt = calls.value
            if attempt == 1: raise SourcePayloadError(b'<html>unavailable</html>')
            time.sleep(60)
        watch.req = req
        started = time.monotonic()
        with self.assertRaises(runtime.IncompleteCoverage): self.collect(watch, seconds=0.6, workers=1)
        self.assertLess(time.monotonic()-started, 2)
        self.assertEqual(calls.value, 2)
        self.assertEqual({p.pid for p in mp.active_children()}, before)
        report = json.loads((watch.OUT/'coverage.json').read_text())
        self.assertEqual(report['news'][0]['status'], 'deadline')
        self.assertEqual(report['news'][0]['initial_attempt']['status'], 'error')

    def test_stalled_source_bounded_and_no_orphan(self):
        watch = fake_watch(self.root, ['stalled', 'not-started'])
        watch.google_news = lambda q: (time.sleep(60), None)
        before = {p.pid for p in mp.active_children()}
        started = time.monotonic()
        with self.assertRaises(runtime.IncompleteCoverage):
            self.collect(watch, seconds=0.1, workers=1)
        self.assertLess(time.monotonic()-started, 2)
        self.assertEqual({p.pid for p in mp.active_children()}, before)
        report = json.loads((watch.OUT/'coverage.json').read_text())
        self.assertEqual([x['status'] for x in report['news']], ['deadline', 'not_started_deadline'])

    def test_replay_error_swallowed_by_legacy_parser_still_fails(self):
        watch = fake_watch(self.root, ['q'])
        def news(q):
            try:
                watch.req('uncollected')
            except Exception:
                pass
            return [], None
        watch.google_news = news
        restore, _ = runtime.install_replay(watch, ['q'], {0: []})
        try:
            with self.assertRaises(runtime.IncompleteCoverage):
                watch.google_news('q')
        finally:
            restore()

    def test_changed_query_order_and_skipped_query_fail(self):
        watch = fake_watch(self.root, ['q'])
        restore, verify = runtime.install_replay(watch, ['q'], {0: []})
        try:
            with self.assertRaises(runtime.IncompleteCoverage):
                verify()
            with self.assertRaises(runtime.IncompleteCoverage):
                watch.google_news('different')
        finally:
            restore()

    def test_supervisor_success_requires_all_replayed_and_verified(self):
        watch = fake_watch(self.root, ['one', 'two'])
        def run():
            for query in watch.QUERIES:
                watch.google_news(query)
            watch.ALERT.write_text('verified alert')
            watch.PENDING.write_text('{"ids":["new"]}')
            watch.SUMMARY.write_text('complete')
        self.assertEqual(runtime.run_bounded(watch, run, total_seconds=3, collection_seconds=1), 0)
        report = json.loads((watch.OUT/'war_peace_reconstruction_coverage.json').read_text())
        self.assertTrue(report['complete'])
        self.assertTrue(watch.ALERT.exists())
        self.assertEqual(json.loads(watch.STATE.read_text())['seen'], ['confirmed-old'])

    def test_quality_failure_removes_partial_output_preserves_state(self):
        watch = fake_watch(self.root, ['one'])
        watch.AUDIT = watch.OUT/'evidence.json'
        watch.ALERT.write_text('stale')
        watch.PENDING.write_text('stale')
        def run():
            watch.google_news('one')
            watch.ALERT.write_text('unverified')
            watch.PENDING.write_text('{"ids":["new"]}')
            watch.AUDIT.write_text('{"fixture":"rejected evidence"}')
            raise ValueError('semantic quality gate')
        self.assertEqual(runtime.run_bounded(watch, run, total_seconds=3, collection_seconds=1), 1)
        self.assertFalse(watch.ALERT.exists())
        self.assertFalse(watch.PENDING.exists())
        self.assertFalse(watch.AUDIT.exists())
        self.assertEqual(json.loads(watch.STATE.read_text())['seen'], ['confirmed-old'])
        report = json.loads((watch.OUT/'war_peace_reconstruction_coverage.json').read_text())
        self.assertFalse(report['complete'])
        retained = report['rejected_artifacts']
        self.assertEqual({item['role'] for item in retained}, {'alert', 'pending', 'evidence'})
        for item in retained:
            raw = (watch.OUT/item['path']).read_bytes()
            self.assertFalse(item['verified'])
            self.assertEqual(item['bytes'], len(raw))
            self.assertEqual(item['sha256'], hashlib.sha256(raw).hexdigest())
        # A later execution must not attach rejected evidence from this failure.
        def complete():
            watch.google_news('one')
        self.assertEqual(runtime.run_bounded(watch, complete, total_seconds=3, collection_seconds=1), 0)
        self.assertFalse(any((watch.OUT/item['path']).exists() for item in retained))
        later = json.loads((watch.OUT/'war_peace_reconstruction_coverage.json').read_text())
        self.assertTrue(later['complete'])
        self.assertNotIn('rejected_artifacts', later)
        self.assertEqual(json.loads(watch.STATE.read_text())['seen'], ['confirmed-old'])

    def test_full_run_timeout_removes_output_including_stalled_enrichment_threads(self):
        watch = fake_watch(self.root, ['one'])
        def run():
            from concurrent.futures import ThreadPoolExecutor
            watch.google_news('one')
            (watch.OUT / 'render_started').write_text('started')
            watch.ALERT.write_text('partial')
            watch.PENDING.write_text('partial')
            with ThreadPoolExecutor(max_workers=1) as executor:
                executor.submit(time.sleep, 60).result()
        started = time.monotonic()
        # This tests the full-run supervisor during stalled rendering. A 100ms
        # collection budget can expire on a busy CI host before rendering ever
        # starts, which exercises a different already-covered failure branch.
        transcript = {0: [('one', 20, b'one', None)]}
        with patch.object(runtime, 'prefetch', return_value=(['one'], transcript)):
            self.assertEqual(runtime.run_bounded(watch, run, total_seconds=0.4, collection_seconds=0.1), 1)
        self.assertLess(time.monotonic()-started, 2)
        self.assertTrue((watch.OUT / 'render_started').exists())
        self.assertFalse(watch.ALERT.exists())
        self.assertFalse(watch.PENDING.exists())
        report = json.loads((watch.OUT/'war_peace_reconstruction_coverage.json').read_text())
        self.assertFalse(report['complete'])
        self.assertIn('deadline', report['error'])
        self.assertEqual({item['role'] for item in report['rejected_artifacts']}, {'alert', 'pending'})
        self.assertTrue(all(not item['verified'] for item in report['rejected_artifacts']))

    def test_http_denials_and_challenge_never_retry_or_change_identity(self):
        import war_peace_reconstruction_watch_oct04_guard as guard
        from urllib.error import HTTPError
        from unittest.mock import MagicMock
        watch = guard.watch
        for code in (401, 403, 429):
            with self.subTest(code=code):
                opener = MagicMock()
                opener.open.side_effect = HTTPError('https://blocked.example/', code, 'blocked', {}, None)
                with patch.object(watch.urllib.request, 'build_opener', return_value=opener):
                    with self.assertRaises(HTTPError):
                        watch.req('https://blocked.example/')
                self.assertEqual(opener.open.call_count, 1)
        opener = MagicMock()
        opener.open.return_value.__enter__.return_value.read.return_value = b'<html>Verify you are human</html>'
        with patch.object(watch.urllib.request, 'build_opener', return_value=opener):
            with self.assertRaises(watch.SourceAccessBlocked):
                watch.req('https://blocked.example/')
        self.assertEqual(opener.open.call_count, 1)

    def test_challenge_and_cross_provider_redirect_rejected_before_follow(self):
        import war_peace_reconstruction_watch_oct04_guard as guard
        watch = guard.watch
        request = watch.urllib.request.Request('https://news.example/rss')
        for target in ('https://news.example/captcha', 'https://consent.example/',
                       'https://alternate.example/rss'):
            with self.subTest(target=target), self.assertRaises(watch.SourceAccessBlocked):
                watch._SourceRedirects().redirect_request(request, None, 302, '', {}, target)

    def test_same_host_redirect_checks_circuit_and_news_headline_is_not_challenge(self):
        import war_peace_reconstruction_watch_oct04_guard as guard
        from unittest.mock import MagicMock
        watch = guard.watch
        original_hook = watch._before_source_request
        def block(url):
            raise runtime.RecordedSourceError('circuit open')
        watch._before_source_request = block
        try:
            request = watch.urllib.request.Request('https://news.example/rss')
            with self.assertRaises(runtime.RecordedSourceError):
                watch._SourceRedirects().redirect_request(request, None, 302, '', {}, 'https://news.example/latest')
        finally:
            watch._before_source_request = original_hook
        raw = b'<rss><channel><item><title>Access denied: aid workers blocked</title></item></channel></rss>'
        opener = MagicMock()
        opener.open.return_value.__enter__.return_value.read.return_value = raw
        with patch.object(watch.urllib.request, 'build_opener', return_value=opener):
            self.assertEqual(watch.req('https://news.example/rss'), raw)

    def test_shared_provider_circuit_stops_new_host_requests_after_denial(self):
        from urllib.error import HTTPError
        watch = fake_watch(self.root, [f'https://blocked.example/{n}' for n in range(12)]
                           + ['https://other.example/'])
        calls = mp.get_context('fork').Value('i', 0)
        def req(url, timeout=20):
            if 'blocked.example' in url:
                with calls.get_lock():
                    calls.value += 1
                raise HTTPError(url, 403, 'blocked', {}, None)
            return b'other provider'
        watch.req = req
        with self.assertRaises(runtime.IncompleteCoverage):
            self.collect(watch, workers=1)
        self.assertEqual(calls.value, 1)
        report = json.loads((watch.OUT/'coverage.json').read_text())
        self.assertEqual(report['blocked_providers']['blocked.example']['code'], 403)
        self.assertEqual(report['news'][-1]['status'], 'ok')
        self.assertEqual(report['max_inflight_source_requests'], 1)
        self.assertTrue(all(x['status'] == 'error' for x in report['news'][:-1]))
        self.assertNotIn('payload_retry_queries', report)

    def test_mixed_malformed_payload_and_access_denial_never_retries_query(self):
        from urllib.error import HTTPError
        watch = fake_watch(self.root, ['mixed'])
        calls = mp.get_context('fork').Value('i', 0)
        def req(url, timeout=20):
            with calls.get_lock(): calls.value += 1
            if 'malformed' in url: raise SourcePayloadError(b'<html>unavailable</html>')
            raise HTTPError(url, 429, 'blocked', {}, None)
        def news(query):
            for url in ('https://malformed.example/?format=rss', 'https://denied.example/?format=rss'):
                try: watch.req(url)
                except Exception: pass
            return [], 'mixed source failure'
        watch.req, watch.google_news = req, news
        with self.assertRaises(runtime.IncompleteCoverage): self.collect(watch)
        self.assertEqual(calls.value, 2)
        report = json.loads((watch.OUT/'coverage.json').read_text())
        self.assertNotIn('payload_retry_queries', report)
        self.assertEqual(report['blocked_providers']['denied.example']['code'], 429)

    def test_real_google_html_response_cannot_be_complete_empty_feed(self):
        import war_peace_reconstruction_watch_oct04_guard as guard
        watch = guard.watch
        saved = watch.OUT, watch.req, watch.QUERIES
        watch.OUT = self.root/'invalid-google'
        watch.QUERIES = ['site:reuters.com Iran ceasefire when:1h']
        watch.req = lambda url, timeout=20: b'<html><body>temporarily unavailable</body></html>'
        try:
            with self.assertRaises(runtime.IncompleteCoverage):
                self.collect(watch)
            report = json.loads((watch.OUT/'coverage.json').read_text())
            self.assertEqual(report['news'][0]['status'], 'error')
        finally:
            watch.OUT, watch.req, watch.QUERIES = saved

    def test_production_payload_error_carries_actual_failed_response(self):
        import war_peace_reconstruction_watch_oct04_guard as guard
        body = b'<html>temporarily unavailable</html>'
        with self.assertRaises(guard.watch.SourcePayloadError) as caught:
            guard.watch._validate_source_payload('https://www.bing.com/news/search?format=rss&q=example', body)
        self.assertEqual(caught.exception.response_body, body)

    def test_real_bing_emergency_failure_recovers_same_five_requests_and_replays(self):
        import war_peace_reconstruction_watch_oct04_guard as guard
        watch = guard.watch
        saved = watch.OUT, watch.req, watch.QUERIES
        watch.OUT = self.root/'bing-emergency'
        watch.QUERIES = ['__BING_MIDDLE_EAST_EMERGENCY__']
        calls = mp.get_context('fork').Value('i', 0)
        valid = b'<rss><channel/></rss>'
        def req(url, timeout=20):
            if 'The%20Hormuz%20Letter' in url:
                with calls.get_lock():
                    calls.value += 1
                    attempt = calls.value
                if attempt == 1:
                    watch._validate_source_payload(url, b'<html>temporarily unavailable</html>')
            return valid
        watch.req = req
        try:
            queries, traces, report = self.collect(watch, workers=1)
            self.assertEqual(calls.value, 2)
            self.assertEqual(report['news'][0]['status'], 'ok')
            self.assertEqual(report['news'][0]['requests'], 5)
            self.assertEqual(report['news'][0]['reused_success_requests'], 4)
            self.assertEqual([h['url'] for h in report['news'][0]['http']],
                             [h['url'] for h in report['news'][0]['initial_attempt']['http']])
            watch.req = forbidden
            restore, verify = runtime.install_replay(watch, queries, traces)
            try:
                rows, error = watch.google_news(queries[0])
                self.assertEqual(rows, [])
                self.assertIsNone(error)
                verify()
            finally:
                restore()
        finally:
            watch.OUT, watch.req, watch.QUERIES = saved

    def test_real_axios_feed_failure_or_malformed_xml_blocks_alert(self):
        import war_peace_reconstruction_watch_oct04_guard as guard
        watch = guard.watch
        saved = watch.OUT, watch.req, watch.QUERIES
        watch.QUERIES = ['__AXIOS_DIRECT_WAR_PEACE__']
        try:
            for mode in ('feed-failed', 'malformed-feed'):
                with self.subTest(mode=mode):
                    watch.OUT = self.root/mode
                    def req(url, timeout=20):
                        if url != 'https://api.axios.com/feed/':
                            raise AssertionError('obsolete Axios World page must not be requested')
                        if mode == 'feed-failed':
                            raise TimeoutError('offline source unavailable')
                        return b'<html>bot challenge</html>'
                    watch.req = req
                    with self.assertRaises(runtime.IncompleteCoverage):
                        self.collect(watch)
                    report = json.loads((watch.OUT/'coverage.json').read_text())
                    self.assertEqual(report['news'][0]['status'], 'error')
                    self.assertEqual(len(report['news'][0]['http']), 1)
                    self.assertEqual(report['news'][0]['http'][0]['url'], 'https://api.axios.com/feed/')
        finally:
            watch.OUT, watch.req, watch.QUERIES = saved

    def test_axios_valid_rss_without_legacy_world_page_replays_all_rows(self):
        import war_peace_reconstruction_watch_oct04_guard as guard
        watch = guard.watch
        saved = watch.OUT, watch.req, watch.QUERIES
        watch.OUT = self.root/'axios-rss-only'
        watch.QUERIES = ['__AXIOS_DIRECT_WAR_PEACE__']
        feed = (
            b'<rss><channel><item><title>Ukraine peace talks continue</title>'
            b'<link>https://www.axios.com/news/peace</link>'
            b'<pubDate>Mon, 12 Oct 2026 06:00:00 GMT</pubDate>'
            b'<description>Russia and Ukraine</description>'
            b'</item></channel></rss>'
        )
        def req(url, timeout=20):
            if url != 'https://api.axios.com/feed/':
                raise AssertionError('obsolete Axios World page must not be requested')
            return feed
        watch.req = req
        try:
            queries, traces, report = self.collect(watch)
            record = report['news'][0]
            self.assertEqual(record['status'], 'ok')
            self.assertEqual(record['rows'], 1)
            self.assertEqual(record['requests'], 1)
            self.assertEqual(record['http'][0]['url'], 'https://api.axios.com/feed/')
            self.assertEqual(record['http'][0]['status'], 'ok')
            watch.req = forbidden
            restore, verify = runtime.install_replay(watch, queries, traces)
            try:
                rows, error = watch.google_news('__AXIOS_DIRECT_WAR_PEACE__')
                self.assertIsNone(error)
                self.assertEqual(len(rows), 1)
                self.assertEqual(rows[0]['title'], 'Ukraine peace talks continue')
                verify()
            finally:
                restore()
        finally:
            watch.OUT, watch.req, watch.QUERIES = saved

    def test_workflow_pr_is_readonly_offline_and_isolated_from_production(self):
        root = Path(__file__).resolve().parents[1]
        workflow = (root/'.github/workflows/war-peace-reconstruction-telegram-watch.yml').read_text()
        self.assertIn('  push:\n    branches: [main]', workflow)
        self.assertIn("github.event_name != 'pull_request' && github.ref == 'refs/heads/main'", workflow)
        self.assertIn("format('war-peace-reconstruction-pr-{0}'", workflow)
        pr_job = workflow.split('  offline-regressions:', 1)[1].split('  monitor:', 1)[0]
        self.assertIn('contents: read', pr_job)
        self.assertIn('persist-credentials: false', pr_job)
        self.assertIn('python scripts/test_war_peace_offline.py', pr_job)
        self.assertNotIn('secrets.', pr_job)
        self.assertNotIn('ref: main', pr_job)
        self.assertIn('out/war_peace_reconstruction_coverage.json', workflow)
        # A generic commit body containing 'test' must never send fake headlines
        # or synthetic market prices to the production Telegram recipient.
        self.assertNotIn("contains(github.event.head_commit.message, 'Test')", workflow)
        self.assertIn("github.event_name == 'workflow_dispatch' && github.event.inputs.telegram_test == 'true'", workflow)


    def test_real_chain_all_227_queries_keep_fallbacks_and_no_network_on_replay(self):
        import war_peace_reconstruction_watch_oct04_guard as guard
        watch = guard.watch
        saved = watch.OUT, watch.req, guard.runner._signal_rows
        watch.OUT = self.root/'real-out'
        # Valid empty RSS for search/RSS; non-RSS direct parsers either accept an
        # empty page or take their existing fallbacks. Every URL is synthetic.
        watch.req = lambda url, timeout=20: b'<rss><channel/></rss>'
        guard.runner._signal_rows = {}
        try:
            queries, traces, report = self.collect(watch, seconds=5, workers=4)
            self.assertEqual(len(queries), 227)
            self.assertEqual(queries, list(watch.QUERIES))
            self.assertTrue(all(x['status'] == 'ok' for x in report['news']))
            watch.req = forbidden
            restore, verify = runtime.install_replay(watch, queries, traces)
            try:
                for query in queries:
                    rows, error = watch.google_news(query)
                    self.assertIsNone(error)
                verify()
            finally:
                restore()
        finally:
            watch.OUT, watch.req, guard.runner._signal_rows = saved


class RetryEligibilityTests(unittest.TestCase):
    def test_production_gdelt_denial_and_bing_payload_failure_is_eligible(self):
        fixture = Path(__file__).resolve().parents[1]/'tests/fixtures/war_fallback_20261014.json'
        data = json.loads(fixture.read_text(encoding='utf-8'))
        self.assertTrue(runtime._payload_retry_eligible(data['record'], data['blocked_providers']))
        malformed = data['record']['http'][-1]
        raw = base64.b64decode(malformed['response_body_base64'], validate=True)
        self.assertEqual(hashlib.sha256(raw).hexdigest(), malformed['sha256'])

    def test_unknown_primary_error_remains_ineligible(self):
        fixture = Path(__file__).resolve().parents[1]/'tests/fixtures/war_fallback_20261014.json'
        data = json.loads(fixture.read_text(encoding='utf-8'))
        data['record']['http'][0]['error'] = 'OSError: unspecified failure'
        self.assertFalse(runtime._payload_retry_eligible(data['record'], data['blocked_providers']))

    def test_denied_final_fallback_is_not_retried(self):
        fixture = Path(__file__).resolve().parents[1]/'tests/fixtures/war_fallback_20261014.json'
        data = json.loads(fixture.read_text(encoding='utf-8'))
        data['record']['http'].reverse()
        self.assertFalse(runtime._payload_retry_eligible(data['record'], data['blocked_providers']))


if __name__ == '__main__':
    unittest.main()
