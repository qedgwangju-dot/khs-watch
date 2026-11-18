"""New run 900 evidence only: no network, sending, live state, or old fixtures."""
import ast
import copy
import datetime as dt
import html
from contextlib import ExitStack
import tempfile
import io
import json
from pathlib import Path
import textwrap
import time
import unittest
from unittest.mock import patch
import urllib.request

import war_peace_reconstruction_watch_counterstrike as counter
import war_peace_reconstruction_watch_evidence as evidence
import war_peace_reconstruction_watch_integrity as stage
import war_peace_reconstruction_watch_two_color as presentation

ROOT = Path(__file__).resolve().parent.parent
FIXTURE = ROOT / 'scripts/test_fixtures/war_run900_semantic_failure.json'
WORKFLOW = ROOT / '.github/workflows/war-peace-reconstruction-telegram-watch.yml'


def sender_function():
    source = WORKFLOW.read_text(encoding='utf-8')
    source = source.split("          python - <<'PY'\n", 1)[1].split("\n          PY", 1)[0]
    tree = ast.parse(textwrap.dedent(source))
    function = next(n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == 'request_json')
    scope = {'urllib': __import__('urllib'), 'json': json, 'time': time}
    exec(compile(ast.fix_missing_locations(ast.Module(body=[function], type_ignores=[])),
                 '<workflow sender>', 'exec'), scope)
    return scope['request_json']


class Response:
    def __enter__(self): return self
    def __exit__(self, *_): return False
    def read(self): return b'{"ok": true, "result": {"username": "example"}}'


class Run900Followup(unittest.TestCase):
    def setUp(self):
        self.row = json.loads(FIXTURE.read_text(encoding='utf-8'))['article']

    def test_actual_saved_feed_actor_is_not_treated_as_ukraine_target(self):
        signals, marks = counter._counter_signals(self.row)
        self.assertIn('러시아정유시설공격', marks)
        self.assertNotIn('우크라이나에너지시설공격', marks)
        self.assertFalse(any('우크라이나 에너지 인프라 공격 신호' in x for x in signals))
        self.assertEqual(counter.counter_item_id(self.row), '2a0265d6f900bdf1ee15')

    def test_saved_feed_through_collection_keeps_russia_and_removes_false_signal(self):
        row = copy.deepcopy(self.row)
        row.pop('signals_ko', None)
        with patch.object(counter, '_prev_google_news', return_value=([row], None)):
            got, err = counter.counter_google_news('fixture-only')
        self.assertIsNone(err)
        self.assertIn('러시아정유시설공격', got[0]['counter_marks'])
        self.assertNotIn('우크라이나에너지시설공격', got[0]['counter_marks'])
        self.assertFalse(any('우크라이나 에너지 인프라 공격 신호' in s for s in got[0]['signals_ko']))

    def test_explicit_ukraine_target_and_independent_attacks_are_kept(self):
        for title, expected_id in (
            ('Russian missile strikes Ukraine power plant', '288d2a481e40ed6c91c1'),
            ('Ukrainian drones strike Russian refinery; Russian missiles hit Ukraine power plant',
             'dc3a10cb380e29b08891'),
        ):
            with self.subTest(title=title):
                row = copy.deepcopy(self.row)
                row.update(title_original=title, description=title)
                self.assertIn('우크라이나에너지시설공격', counter._counter_signals(row)[1])
                self.assertEqual(counter.counter_item_id(row), expected_id)

    def test_independent_russian_attack_is_not_suppressed(self):
        row = copy.deepcopy(self.row)
        row['description'] += '\nRussian missiles hit Kharkiv power grid.'
        self.assertIn('우크라이나에너지시설공격', counter._counter_signals(row)[1])
        # Different wording is kept on the pre-existing path.
        row.update(title_original='Ukrainian drones strike Russian refinery',
                   description='Ukrainian drones strike Russian refinery')
        self.assertIn('우크라이나에너지시설공격', counter._counter_signals(row)[1])

    def test_empty_headline_does_not_break_existing_collection(self):
        row = copy.deepcopy(self.row)
        row['title_original'] = ''
        self.assertTrue(counter._counter_signals(row)[1])

    def test_saved_feed_through_final_presentation_gate_without_network(self):
        data = json.loads(FIXTURE.read_text(encoding='utf-8'))
        now = dt.datetime.fromisoformat(data['queried_at_kst'])
        with ExitStack() as stack:
            folder = Path(stack.enter_context(tempfile.TemporaryDirectory()))
            for name, filename in {'OUT': '.', 'STATE': 'state.json', 'ALERT': 'alert.txt',
                                   'AUDIT': 'evidence.json', 'PENDING': 'pending.json'}.items():
                stack.enter_context(patch.object(stage.watch, name, folder / filename))
            stage.watch.STATE.write_text('{"seen": [], "source_aliases": {}}', encoding='utf-8')
            state = stage.watch.STATE.read_bytes()
            stack.enter_context(patch('urllib.request.urlopen', side_effect=AssertionError('network/send forbidden')))
            stack.enter_context(patch.object(stage.body_parallel, '_safe_enrich'))
            statuses = data['market_source_status']
            stack.enter_context(patch.object(stage.watch, 'market_source_status', statuses, create=True))
            row = copy.deepcopy(self.row)
            row.pop('signals_ko', None)
            score, tags = stage.score_item(row, now)
            self.assertGreaterEqual(score, 6)
            row.update(score=score, tags=tags, age=stage.watch.age_minutes(row, now))
            text = stage.build_alert([row], data['markets'], now)
            receipt = evidence.alert_receipt([row], data['markets'], now, text, statuses)
            receipt['articles'][0]['article_text_sha256'] = self.row['article_text_sha256']
            ids = [r['id'] for r in receipt['articles'] if r['rendered']]
            self.assertEqual(ids, [self.row['id']])
            stage.watch.ALERT.write_text(text, encoding='utf-8')
            stage.watch.AUDIT.write_text(json.dumps(receipt, ensure_ascii=False), encoding='utf-8')
            stage.watch.PENDING.write_text(json.dumps({'ids': ids}), encoding='utf-8')
            presentation.Presenter(stage).verify_alert()
            shown = html.unescape(stage.watch.ALERT.read_text(encoding='utf-8'))
            saved = json.loads(stage.watch.AUDIT.read_text(encoding='utf-8'))['articles'][0]
            self.assertIn(self.row['link'], shown)
            self.assertEqual(saved['title_original'], self.row['title_original'])
            self.assertIn('러시아 정유시설 공격·피격 신호', shown)
            self.assertNotIn('우크라이나 에너지 인프라 공격 신호', shown)
            self.assertFalse(saved['body_verified'])
            self.assertEqual(stage.watch.STATE.read_bytes(), state)

    def test_timeout_retry_opt_in_is_used_only_by_getme(self):
        source = WORKFLOW.read_text(encoding='utf-8')
        script = textwrap.dedent(source.split("          python - <<'PY'\n", 1)[1].split("\n          PY", 1)[0])
        tree = ast.parse(script)
        calls = [n for n in ast.walk(tree) if isinstance(n, ast.Call)
                 and isinstance(n.func, ast.Name) and n.func.id == 'request_json']
        opted_in = [c for c in calls if any(k.arg == 'retry_read_timeout' for k in c.keywords)]
        self.assertEqual(len(opted_in), 1)
        self.assertIn('/getMe', ast.unparse(opted_in[0]))
        self.assertEqual(len(calls), 2)

    def test_getme_timeout_read_retry_is_bounded(self):
        request_json = sender_function()
        with patch('urllib.request.urlopen', side_effect=[TimeoutError('The read operation timed out'), Response()]) as call, patch('time.sleep'):
            result = request_json('https://example.invalid/getMe', retry_read_timeout=True)
        self.assertTrue(result['ok'])
        self.assertEqual(call.call_count, 2)
        with patch('urllib.request.urlopen', side_effect=TimeoutError('The read operation timed out')) as call, patch('time.sleep'):
            with self.assertRaises(TimeoutError):
                request_json('https://example.invalid/getMe', retry_read_timeout=True)
        self.assertEqual(call.call_count, 3)

    def test_send_message_timeout_is_never_newly_retried(self):
        request_json = sender_function()
        req = urllib.request.Request('https://example.invalid/sendMessage', data=b'{}', method='POST')
        with patch('urllib.request.urlopen', side_effect=TimeoutError('The read operation timed out')) as call, patch('time.sleep'):
            with self.assertRaises(TimeoutError):
                request_json(req)
        self.assertEqual(call.call_count, 1)


if __name__ == '__main__':
    unittest.main()
