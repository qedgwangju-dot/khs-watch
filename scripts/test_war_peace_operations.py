#!/usr/bin/env python3
"""No-network tests for the source-coverage operational warning."""
from __future__ import annotations

import datetime as dt
import hashlib
import json
from pathlib import Path
import tempfile
import unittest

import war_peace_reconstruction_watch_operations as operations


UTC = dt.timezone.utc


def actual_run_727_coverage():
    """Shape from the observed 11/227 fail-closed production run #727."""
    news = [{'index': n, 'query': f'fixture-{n}', 'status': 'ok'} for n in range(216)]
    news.extend({'index': n, 'query': f'fixture-{n}', 'status': 'partial',
                 'coverage_issue': {'reason': 'fallback_scope_not_verified'},
                 'error': 'original source unavailable; fallback scope unverified'}
                for n in range(216, 223))
    news.extend([
        {'index': 223, 'query': 'fixture-223', 'status': 'error',
         'http': [{'status': 'error', 'error': 'HTTPError: HTTP Error 403: Forbidden'}]},
        {'index': 224, 'query': 'fixture-224', 'status': 'error',
         'http': [{'status': 'error', 'error': 'HTTPError: HTTP Error 401: Unauthorized'}]},
        {'index': 225, 'query': 'fixture-225', 'status': 'error',
         'http': [{'status': 'error', 'error': 'TimeoutError: timed out'}]},
        {'index': 226, 'query': 'fixture-226', 'status': 'error',
         'http': [{'status': 'error', 'error': 'SourcePayloadError: invalid RSS'}]},
    ])
    return {
        'complete': False,
        'phase': 'failed',
        'failure_phase': 'collection',
        'query_count': 227,
        'error': 'IncompleteCoverage: 11/227 queries incomplete',
        'news': news,
    }


class OperationsWarningTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.coverage = self.root / 'coverage.json'
        self.state = self.root / 'ops_state.json'
        self.warning = self.root / 'ops_warning.txt'
        self.alert = self.root / 'alert.txt'
        self.pending = self.root / 'ops_state_pending.json'
        self.delivery = self.root / 'delivery.json'
        self.now = dt.datetime(2026, 11, 1, 8, 0, tzinfo=UTC)

    def tearDown(self):
        self.temp.cleanup()

    def write_coverage(self, value):
        self.coverage.write_text(json.dumps(value), encoding='utf-8')

    def prepare(self, when=None):
        return operations.prepare(now=when or self.now, coverage_path=self.coverage,
                                  state_path=self.state, warning_path=self.warning,
                                  pending_path=self.pending, alert_path=self.alert)

    def finalize(self):
        return operations.finalize(state_path=self.state, warning_path=self.warning,
                                   pending_path=self.pending, delivery_path=self.delivery)

    def write_matching_delivery(self):
        self.delivery.write_text(json.dumps({
            'status': 'confirmed',
            'kind': 'operational_source_coverage_warning',
            'alert_sha256': hashlib.sha256(self.warning.read_text(encoding='utf-8').strip().encode('utf-8')).hexdigest(),
        }), encoding='utf-8')

    def test_run_727_shape_creates_separate_warning_and_waits_for_receipt(self):
        self.write_coverage(actual_run_727_coverage())
        self.assertEqual(self.prepare(), 'send')
        text = self.warning.read_text(encoding='utf-8')
        self.assertIn('전쟁 알림 수집 지연·범위 미확인', text)
        self.assertIn('완전 확인: 216/227개 질의', text)
        self.assertIn('미완료: 11개', text)
        self.assertIn('HTTP 403 접근 거부: 1건', text)
        self.assertIn('HTTP 401 인증 거부: 1건', text)
        self.assertIn('수집 시간 초과: 1건', text)
        self.assertIn('대체 원천의 범위 미확인: 7건', text)
        self.assertFalse((self.root / 'alert.txt').exists())
        self.assertFalse(self.finalize())
        self.assertFalse(self.state.exists())
        self.write_matching_delivery()
        self.assertTrue(self.finalize())
        saved = json.loads(self.state.read_text(encoding='utf-8'))
        self.assertTrue(saved['active'])
        self.assertEqual(saved['last_warning_sent_at'], self.now.isoformat(timespec='seconds'))

    def test_failure_repeats_are_throttled_for_six_hours_even_after_recovery(self):
        self.write_coverage(actual_run_727_coverage())
        self.assertEqual(self.prepare(), 'send')
        self.write_matching_delivery()
        self.assertTrue(self.finalize())

        self.write_coverage({'complete': True, 'phase': 'verified', 'news': [{'status': 'ok'}]})
        recovered = self.now + dt.timedelta(hours=1)
        self.assertEqual(self.prepare(recovered), 'recovered')
        self.assertTrue(self.finalize())
        state = json.loads(self.state.read_text(encoding='utf-8'))
        self.assertFalse(state['active'])
        self.assertEqual(state['last_warning_sent_at'], self.now.isoformat(timespec='seconds'))

        self.write_coverage(actual_run_727_coverage())
        self.assertEqual(self.prepare(self.now + dt.timedelta(hours=2)), 'throttled')
        self.assertFalse(self.warning.exists())
        self.assertTrue(self.finalize())
        self.assertTrue(json.loads(self.state.read_text(encoding='utf-8'))['active'])

        self.assertEqual(self.prepare(self.now + dt.timedelta(hours=6)), 'send')

    def test_semantic_verification_failure_does_not_create_source_warning(self):
        self.write_coverage({
            'complete': False,
            'phase': 'failed',
            'failure_phase': 'parse_render_verify',
            'news': [{'status': 'ok'}, {'status': 'ok'}],
            'error': 'RuntimeError: semantic validation failed',
        })
        self.assertEqual(self.prepare(), 'not_source_failure')
        self.assertFalse(self.warning.exists())
        self.assertFalse(self.pending.exists())

    def test_verified_partial_alert_retains_incident_without_duplicate_warning(self):
        report = actual_run_727_coverage()
        report.update(complete=True, phase='verified', source_coverage_complete=False,
                      coverage_level='partial')
        self.write_coverage(report)
        self.alert.write_text('verified partial situation alert', encoding='utf-8')
        self.assertEqual(self.prepare(), 'partial_alert')
        self.assertFalse(self.warning.exists())
        self.assertTrue(self.finalize())
        state = json.loads(self.state.read_text(encoding='utf-8'))
        self.assertTrue(state['active'])
        self.assertEqual(state['last_failure']['query_incomplete'], 11)
        self.assertIsNone(state['last_warning_sent_at'])
        self.alert.unlink()
        self.assertEqual(self.prepare(self.now + dt.timedelta(minutes=5)), 'send')
        self.assertTrue(self.warning.exists())

    def test_collection_failure_without_query_statuses_is_labeled_unverified(self):
        self.write_coverage({
            'complete': False,
            'phase': 'failed',
            'failure_phase': 'collection',
            'error': 'IncompleteCoverage: no source queries configured',
        })
        self.assertEqual(self.prepare(), 'send')
        text = self.warning.read_text(encoding='utf-8')
        self.assertIn('질의별 상태 증거 없음', text)
        self.assertIn('미완료 질의 수: 확인 불가', text)

    def test_absent_coverage_and_corrupt_state_fail_closed(self):
        self.assertEqual(self.prepare(), 'none')
        self.write_coverage(actual_run_727_coverage())
        self.state.write_text('not-json', encoding='utf-8')
        with self.assertRaises(json.JSONDecodeError):
            self.prepare()
        self.assertFalse(self.warning.exists())

    def test_workflow_reuses_existing_sender_and_keeps_five_minute_schedule(self):
        workflow = (operations.ROOT / '.github/workflows/war-peace-reconstruction-telegram-watch.yml').read_text(encoding='utf-8')
        sender = workflow.split('- name: Send Telegram alert', 1)[1].split('- name: Finalize state after confirmed delivery', 1)[0]
        self.assertIn('out/war_peace_reconstruction_alert.txt', sender)
        self.assertIn('out/war_peace_reconstruction_ops_warning.txt', sender)
        self.assertIn('secrets.WAR_PEACE_TELEGRAM_BOT_TOKEN', sender)
        self.assertEqual(workflow.count('bot{token}/sendMessage'), 1)
        self.assertIn('cron: "*/5 * * * *"', workflow)


if __name__ == '__main__':
    unittest.main()
