"""New run-894 evidence only; no network, sends, or live state writes."""
import copy
import datetime as dt
import hashlib
import json
from pathlib import Path
import tempfile
import unittest
from contextlib import ExitStack
from unittest.mock import patch

import war_peace_reconstruction_watch_evidence as evidence
import war_peace_reconstruction_watch_integrity as stage
import war_peace_reconstruction_watch_two_color as presentation


FIXTURE = Path(__file__).parent / 'test_fixtures' / 'war_run894_semantic_failure.json'


class Run894SemanticChecks(unittest.TestCase):
    def setUp(self):
        self.data = json.loads(FIXTURE.read_text(encoding='utf-8'))
        self.rows = {row['id']: copy.deepcopy(row) for row in self.data['articles']}
        self.inspection = self.rows['cc45e4d3997503228b5f']
        self.meeting = self.rows['16de15b0f7b684ac56e4']
        self.now = dt.datetime.fromisoformat(self.data['queried_at_kst'])

    def test_saved_inspection_position_is_not_a_new_facility_attack(self):
        self.assertFalse(self.inspection['body_verified'])
        self.assertTrue(stage._conditional_nuclear_inspection_headline(self.inspection))
        self.assertEqual(stage.non_military_kind(self.inspection), 'diplomatic_position')
        self.assertEqual(stage.final_color(self.inspection), 'yellow')
        self.assertIsNone(presentation.direction(stage, self.inspection))
        self.assertEqual(stage.topic_label(self.inspection), '이란 · 종전 전 핵시설 사찰 제한 입장')

    def test_separate_actual_attack_is_not_demoted_to_inspection_context(self):
        row = dict(self.inspection, title_original='이란 美공격 핵시설, 종전 전에는 사찰 불가…공격 재개')
        self.assertFalse(stage._conditional_nuclear_inspection_headline(row))

    def test_saved_us_north_korea_meeting_is_a_possibility(self):
        self.assertTrue(stage._us_north_korea_possible_meeting_headline(self.meeting))
        self.assertEqual(stage.topic_label(self.meeting), '미국·북한 · 정상 회동 가능성 발언')
        self.assertEqual(presentation.direction(stage, self.meeting), 'green')
        self.assertFalse(self.meeting['body_verified'])

    def test_actual_meeting_does_not_match_the_possibility_only_guard(self):
        row = dict(self.meeting, title_original='트럼프 김정은 만났다, 정상회담 가능성')
        self.assertFalse(stage._us_north_korea_possible_meeting_headline(row))

    def test_saved_sources_pass_fresh_semantic_and_final_gate_without_send(self):
        with ExitStack() as stack:
            folder = Path(stack.enter_context(tempfile.TemporaryDirectory()))
            for name, filename in {'OUT': '.', 'STATE': 'state.json', 'ALERT': 'alert.txt',
                                   'AUDIT': 'evidence.json', 'PENDING': 'pending.json'}.items():
                stack.enter_context(patch.object(stage.watch, name, folder / filename))
            stage.watch.STATE.write_text('{"seen": [], "source_aliases": {}}', encoding='utf-8')
            state_before = stage.watch.STATE.read_bytes()
            stack.enter_context(patch('urllib.request.urlopen', side_effect=AssertionError('network/send forbidden')))
            stack.enter_context(patch.object(stage.body_parallel, '_safe_enrich'))
            statuses = self.data['market_source_status']
            stack.enter_context(patch.object(stage.watch, 'market_source_status', statuses, create=True))
            rows = []
            for row in copy.deepcopy(self.data['articles']):
                if not row.get('rendered'):
                    continue
                score, tags = stage.score_item(row, self.now)
                if score >= 6:
                    row.update(score=score, tags=tags, age=stage.watch.age_minutes(row, self.now))
                    rows.append(row)
            semantic_text = stage.build_alert(rows, self.data['markets'], self.now)
            receipt = evidence.alert_receipt(rows, self.data['markets'], self.now, semantic_text, statuses)
            for row in receipt['articles']:
                row['article_text_sha256'] = self.rows[row['id']]['article_text_sha256']
            ids = [row['id'] for row in receipt['articles'] if row.get('rendered')]
            stage.watch.ALERT.write_text(semantic_text, encoding='utf-8')
            stage.watch.AUDIT.write_text(json.dumps(receipt, ensure_ascii=False), encoding='utf-8')
            stage.watch.PENDING.write_text(json.dumps({'ids': ids}), encoding='utf-8')
            presentation.Presenter(stage).verify_alert()
            shown = stage.watch.ALERT.read_text(encoding='utf-8')
            final = json.loads(stage.watch.AUDIT.read_text(encoding='utf-8'))
            self.assertIn('이란 · 종전 전 핵시설 사찰 제한 입장 · 본문 미확인', shown)
            self.assertNotIn('이란 · 에너지 시설 공격 보도', shown)
            self.assertIn('미국·북한 · 정상 회동 가능성 발언', shown)
            saved = next(row for row in final['articles'] if row['id'] == self.inspection['id'])
            self.assertIsNone(saved['classification_color'])
            self.assertEqual(saved['display_section'], 'context_reference')
            self.assertFalse(saved['body_verified'])
            self.assertEqual(final['alert_sha256'], hashlib.sha256(shown.strip().encode('utf-8')).hexdigest())
            self.assertEqual(stage.watch.STATE.read_bytes(), state_before)


if __name__ == '__main__':
    unittest.main()
