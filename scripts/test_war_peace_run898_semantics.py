"""Run 898 saved semantic evidence; no network, delivery, or live state."""
import copy
import datetime as dt
import html
import json
from pathlib import Path
import tempfile
import unittest
from contextlib import ExitStack
from unittest.mock import patch

import war_peace_reconstruction_watch_evidence as evidence
import war_peace_reconstruction_watch_integrity as stage
import war_peace_reconstruction_watch_two_color as presentation

FIXTURE = Path(__file__).parent / 'test_fixtures' / 'war_run898_semantic_failure.json'

class Run898SemanticChecks(unittest.TestCase):
    def setUp(self):
        self.data = json.loads(FIXTURE.read_text(encoding='utf-8'))
        self.by_id = {r['id']: r for r in self.data['articles']}
        self.row = self.by_id['3ea5c119eabece26113a']
        self.now = dt.datetime.fromisoformat(self.data['queried_at_kst'])

    def test_saved_meeting_speculation_is_neutral_context(self):
        row = copy.deepcopy(self.row)
        score, tags = stage.score_item(row, self.now)
        self.assertGreaterEqual(score, 6)
        self.assertEqual(stage.topic_label(row), '북미 회담 가능성 관측')
        self.assertIsNone(presentation.direction(stage, row))
        self.assertTrue(row['body_verified'])

    def test_distinct_attack_or_direct_meeting_statement_is_not_suppressed(self):
        attack = dict(self.row, title_original='북미회담 가능성 시사…미군 기지 공습',
                      title_ko='북미회담 가능성 시사…미군 기지 공습')
        self.assertEqual(presentation.direction(stage, attack), 'red')
        proposal = dict(self.row, title_original='트럼프 김정은 만날 수도',
                        title_ko='트럼프 김정은 만날 수도')
        self.assertEqual(presentation.direction(stage, proposal), 'green')
        for title in ('러 반응, 북미회담 가능성 시사…회담 개최 예정',
                      '러 반응, 북미회담 가능성 시사…missile attack'):
            self.assertFalse(stage._north_korea_meeting_possibility_observation(
                dict(self.row, title_original=title)), title)

    def test_new_saved_sources_through_final_presentation_gate(self):
        with ExitStack() as stack:
            folder = Path(stack.enter_context(tempfile.TemporaryDirectory()))
            for name, filename in {'OUT': '.', 'STATE': 'state.json', 'ALERT': 'alert.txt',
                                   'AUDIT': 'evidence.json', 'PENDING': 'pending.json'}.items():
                stack.enter_context(patch.object(stage.watch, name, folder / filename))
            stage.watch.STATE.write_text('{"seen": [], "source_aliases": {}}', encoding='utf-8')
            original_state = stage.watch.STATE.read_bytes()
            stack.enter_context(patch('urllib.request.urlopen', side_effect=AssertionError('network/send forbidden')))
            stack.enter_context(patch.object(stage.body_parallel, '_safe_enrich'))
            statuses = self.data['market_source_status']
            stack.enter_context(patch.object(stage.watch, 'market_source_status', statuses, create=True))
            rows = []
            for row in copy.deepcopy(self.data['articles']):
                row.pop('signals_ko', None)
                score, tags = stage.score_item(row, self.now)
                if score >= 6:
                    row.update(score=score, tags=tags, age=stage.watch.age_minutes(row, self.now))
                    rows.append(row)
            text = stage.build_alert(rows, self.data['markets'], self.now)
            receipt = evidence.alert_receipt(rows, self.data['markets'], self.now, text, statuses)
            for row in receipt['articles']:
                row['article_text_sha256'] = self.by_id[row['id']]['article_text_sha256']
            ids = [r['id'] for r in receipt['articles'] if r.get('rendered')]
            stage.watch.ALERT.write_text(text, encoding='utf-8')
            stage.watch.AUDIT.write_text(json.dumps(receipt, ensure_ascii=False), encoding='utf-8')
            stage.watch.PENDING.write_text(json.dumps({'ids': ids}), encoding='utf-8')
            presentation.Presenter(stage).verify_alert()
            shown = html.unescape(stage.watch.ALERT.read_text(encoding='utf-8'))
            final = json.loads(stage.watch.AUDIT.read_text(encoding='utf-8'))
            saved = next(r for r in final['articles'] if r['id'] == self.row['id'])
            self.assertIn(self.row['title_original'], shown)
            self.assertIn('북미 회담 가능성 관측', shown)
            self.assertNotIn('우크라이나·러시아', shown)
            self.assertIsNone(saved['classification_color'])
            self.assertEqual(saved['display_section'], 'context_reference')
            self.assertTrue(saved['body_verified'])
            self.assertEqual(stage.watch.STATE.read_bytes(), original_state)

if __name__ == '__main__':
    unittest.main()
