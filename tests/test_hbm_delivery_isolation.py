"""Regression tests use fake repositories and never call Telegram or GitHub."""
import copy
import pathlib
import sys
import tempfile
import unittest
from unittest.mock import Mock, patch

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / 'scripts'))
import hbm_delivery as d


class FakeRepository:
    def __init__(self):
        self.states = {path: {'value': 1} for path, _, _ in d.ROUTES.values()}
        self.unavailable = set()

    def current(self, path):
        if path in self.unavailable:
            raise RuntimeError('simulated repository outage')
        return 'fake-sha', copy.deepcopy(self.states[path])

    def checkpoint(self, path, expected, desired):
        if d.digest(self.states[path]) != d.digest(expected):
            raise RuntimeError('simulated concurrent state change')
        self.states[path] = copy.deepcopy(desired)


class RecoveryIsolationTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        root = pathlib.Path(self.tmp.name)
        (root / 'out').mkdir()
        self.repo = FakeRepository()
        for obj, attr, val in ((d, 'ROOT', root), (d, 'OUT', root / 'out')):
            p = patch.object(obj, attr, val); p.start(); self.addCleanup(p.stop)
        p = patch.object(d, 'Repository', return_value=self.repo)
        p.start(); self.addCleanup(p.stop)
        p = patch.dict(d.os.environ, {'GITHUB_RUN_ID': 'test-run', 'GITHUB_RUN_ATTEMPT': '1'})
        p.start(); self.addCleanup(p.stop)
        self.path = d.ROUTES['samsung'][0]

    def test_uncertain_route_does_not_block_healthy_baselines(self):
        self.repo.states[self.path]['_delivery'] = {'status': 'uncertain'}
        d.write(d.OUT / 'hbm_before_samsung.json', {'value': 'stale'})
        result = d.begin()
        self.assertEqual(result['routes']['samsung']['status'], 'blocked')
        self.assertFalse((d.OUT / 'hbm_before_samsung.json').exists())
        self.assertEqual(result['routes']['rubin']['status'], 'ready')
        self.assertEqual(result['routes']['skhynix']['status'], 'ready')
        self.assertEqual(self.repo.states[self.path]['_delivery']['status'], 'uncertain')

    def test_unavailable_repository_route_is_isolated(self):
        self.repo.unavailable.add(self.path)
        result = d.begin()
        self.assertEqual(result['routes']['samsung']['status'], 'blocked')
        self.assertEqual(result['routes']['rubin']['status'], 'ready')

    def test_recovery_hold_skips_only_that_collector(self):
        self.repo.states[self.path]['_delivery'] = {'status': 'in_flight'}
        d.begin()
        with patch.object(d.subprocess, 'run') as proc, patch.object(d, 'finish', return_value={'status': 'no_message_due'}) as done:
            with self.assertRaises(RuntimeError): d.run_collectors()
        self.assertEqual([c.args[0] for c in done.call_args_list], ['rubin', 'skhynix', 'solidigm'])
        self.assertFalse(any('hbm_memory_axes.py' in c.args[0][1] for c in proc.call_args_list))
        summary = d.read(d.OUT / 'hbm_delivery_summary.json')
        self.assertEqual(summary['routes']['samsung']['stage'], 'recovery')
        self.assertEqual(summary['routes']['rubin']['status'], 'no_message_due')

    def test_cleanup_failure_does_not_stop_next_route(self):
        d.begin()
        self.repo.unavailable.add(d.ROUTES['rubin'][0])
        def finish(name):
            if name == 'rubin': raise ValueError('simulated collector failure')
            return {'status': 'no_message_due'}
        with patch.object(d.subprocess, 'run'), patch.object(d, 'finish', side_effect=finish) as done:
            with self.assertRaises(RuntimeError): d.run_collectors()
        self.assertEqual([c.args[0] for c in done.call_args_list], ['rubin', 'skhynix', 'samsung', 'solidigm'])
        summary = d.read(d.OUT / 'hbm_delivery_summary.json')
        self.assertEqual(summary['routes']['rubin']['refresh_error_type'], 'RuntimeError')
        self.assertEqual(summary['routes']['samsung']['status'], 'no_message_due')

    def test_missing_manifest_blocks_all_sends(self):
        with patch.object(d.subprocess, 'run') as proc:
            with self.assertRaises(RuntimeError): d.run_collectors()
        proc.assert_not_called()

    def test_wrong_execution_manifest_blocks_all_sends(self):
        d.begin()
        with patch.dict(d.os.environ, {'GITHUB_RUN_ATTEMPT': '2'}), patch.object(d.subprocess, 'run') as proc:
            with self.assertRaises(RuntimeError): d.run_collectors()
        proc.assert_not_called()

    def test_altered_baseline_blocks_only_affected_route(self):
        d.begin(); d.write(d.OUT / 'hbm_before_rubin.json', {'value': 999})
        with patch.object(d.subprocess, 'run'), patch.object(d, 'finish', return_value={'status': 'no_message_due'}) as done:
            with self.assertRaises(RuntimeError): d.run_collectors()
        self.assertEqual([c.args[0] for c in done.call_args_list], ['skhynix', 'samsung', 'solidigm'])

    def test_all_healthy_results_are_recorded(self):
        d.begin()
        with patch.object(d.subprocess, 'run'), patch.object(d, 'finish', return_value={'status': 'no_message_due'}):
            results = d.run_collectors()
        self.assertEqual(set(results), set(d.ROUTES))
        self.assertEqual(d.read(d.OUT / 'hbm_delivery_summary.json')['errors'], [])

    def test_existing_journal_cannot_be_overwritten_by_new_or_quiet_transaction(self):
        before = {'value': 1, '_delivery': {'status': 'uncertain'}}
        self.repo.states[self.path] = copy.deepcopy(before)
        for text in ('new alert', ''):
            send = Mock()
            with self.assertRaises(RuntimeError): d.transact(self.repo, self.path, before, {'value': 2}, text, send)
            send.assert_not_called()
            self.assertEqual(self.repo.states[self.path], before)

    def test_nonpositive_or_boolean_ack_never_promotes_state(self):
        for mid in (0, -1, True, '123', None):
            with self.subTest(mid=mid):
                before = {'value': 1}; self.repo.states[self.path] = copy.deepcopy(before)
                with self.assertRaises(RuntimeError):
                    d.transact(self.repo, self.path, before, {'value': 2}, 'alert', lambda *a: {'message_id': mid})
                self.assertEqual(self.repo.states[self.path]['value'], 1)
                self.assertEqual(self.repo.states[self.path]['_delivery']['status'], 'uncertain')

    def test_acknowledged_partial_recovers_without_resending(self):
        state = {'value': 1, '_delivery': {'status': 'partial', 'next_chunk': 1,
            'chunks': ['already delivered'], 'message_ids': [133], 'candidate': {'value': 2}}}
        self.repo.states[self.path] = copy.deepcopy(state)
        send = Mock(side_effect=AssertionError('must not resend'))
        result = d.resume_one(self.repo, self.path, state, send)
        send.assert_not_called()
        self.assertEqual(result['message_ids'], [133])
        self.assertEqual(self.repo.states[self.path]['value'], 2)
        self.assertNotIn('_delivery', self.repo.states[self.path])

    def test_partial_recovery_sends_only_remaining_chunk(self):
        state = {'value': 1, '_delivery': {'status': 'partial', 'next_chunk': 1,
            'chunks': ['first', 'second'], 'message_ids': [133], 'candidate': {'value': 2}}}
        self.repo.states[self.path] = copy.deepcopy(state)
        send = Mock(return_value={'message_id': 134})
        result = d.resume_one(self.repo, self.path, state, send)
        self.assertEqual(send.call_count, 1)
        self.assertEqual(send.call_args.args[1]['text'], 'second')
        self.assertEqual(result['message_ids'], [133, 134])

    def test_corrupt_journal_never_sends_or_promotes(self):
        for next_chunk, ids in ((-1, []), (2, []), (1, []), (True, [133]), (1, [0])):
            state = {'value': 1, '_delivery': {'status': 'partial', 'next_chunk': next_chunk,
                'chunks': ['first'], 'message_ids': ids, 'candidate': {'value': 2}}}
            self.repo.states[self.path] = copy.deepcopy(state)
            send = Mock()
            with self.assertRaises(RuntimeError): d.resume_one(self.repo, self.path, state, send)
            send.assert_not_called()
            self.assertEqual(self.repo.states[self.path], state)


if __name__ == '__main__':
    unittest.main()
