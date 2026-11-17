"""New run-893 evidence only; no network, sends, or live state writes."""
import base64
import copy
import datetime as dt
import hashlib
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


FIXTURE = Path(__file__).parent / 'test_fixtures' / 'war_run893_semantic_failure.json'


class Run893SemanticChecks(unittest.TestCase):
    def setUp(self):
        self.data = json.loads(FIXTURE.read_text(encoding='utf-8'))
        self.venue, self.diplomacy, self.pledge = copy.deepcopy(self.data['articles'])
        self.now = dt.datetime.fromisoformat(self.data['queried_at_kst'])

    def test_saved_venue_is_context_and_summit_statement_retained(self):
        self.assertTrue(stage._summit_venue_description_only(self.venue))
        venue_score, venue_tags = stage.score_item(self.venue, self.now)
        self.assertGreaterEqual(venue_score, 6)
        self.assertEqual(venue_tags, ['정상회담 장소 보도'])
        self.assertEqual(stage.topic_label(self.venue), '미국·중국·러시아 · 정상회담 장소 보도')
        self.assertIsNone(presentation.direction(stage, self.venue))
        score, _ = stage.score_item(self.diplomacy, self.now)
        self.assertGreaterEqual(score, 6)
        self.assertEqual(stage.topic_label(self.diplomacy), '미국·중국·러시아 · 외교 접촉 보도')
        self.assertEqual(presentation.direction(stage, self.diplomacy), 'green')

    def test_venue_with_reported_action_is_not_treated_as_place_only(self):
        for title in ('미중러 정상회담장 영빈관 미사일 공격',
                      '미중러 정상회담장 영빈관서 휴전 합의',
                      '미중러 정상회담장 영빈관서 우크라이나 전쟁 논의'):
            row = dict(self.venue, title_original=title)
            self.assertFalse(stage._summit_venue_description_only(row), title)

    def test_saved_title_only_pledge_is_context_and_stays_body_unverified(self):
        self.assertFalse(self.pledge['body_verified'])
        self.assertIsNone(presentation.direction(stage, self.pledge))
        snapshot = self.data['semantic_snapshot']
        text = base64.b64decode(snapshot['alert_utf8_base64']).decode('utf-8')
        evidence = json.loads(base64.b64decode(snapshot['evidence_utf8_base64']))
        rendered, receipt = presentation.project(stage, text, evidence, self.data['semantic_proof'], snapshot)
        actual = next(row for row in receipt['articles'] if row['id'] == self.pledge['id'])
        self.assertEqual(actual['display_section'], 'context_reference')
        self.assertIsNone(actual['classification_color'])
        self.assertFalse(actual['body_verified'])
        self.assertIn('이란전 종전 약속 발언 · 본문 미확인', rendered)
        self.assertIn('종전 약속 발언', rendered)

    def test_adverse_clause_does_not_become_a_neutral_pledge(self):
        for title in ('이란전 종전 약속 거부', '이란전 종전 약속 부인',
                      '이란전 종전 약속, 미군기지 공격 감행'):
            row = dict(self.pledge, title_original=title)
            self.assertFalse(presentation._title_only_war_end_pledge(stage, row), title)

    def test_saved_sources_fresh_selection_through_final_gate_without_send(self):
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
                score, tags = stage.score_item(row, self.now)
                if score >= 6:
                    row.update(score=score, tags=tags, age=stage.watch.age_minutes(row, self.now))
                    rows.append(row)
            semantic_text = stage.build_alert(rows, self.data['markets'], self.now)
            receipt = evidence.alert_receipt(rows, self.data['markets'], self.now, semantic_text, statuses)
            for row in receipt['articles']:
                row['article_text_sha256'] = next(original['article_text_sha256'] for original in self.data['articles']
                                                    if original['id'] == row['id'])
            ids = [row['id'] for row in receipt['articles'] if row.get('rendered')]
            stage.watch.ALERT.write_text(semantic_text, encoding='utf-8')
            stage.watch.AUDIT.write_text(json.dumps(receipt, ensure_ascii=False), encoding='utf-8')
            stage.watch.PENDING.write_text(json.dumps({'ids': ids}), encoding='utf-8')
            presentation.Presenter(stage).verify_alert()
            shown = stage.watch.ALERT.read_text(encoding='utf-8')
            final = json.loads(stage.watch.AUDIT.read_text(encoding='utf-8'))
            self.assertIn(self.venue['title_original'], html.unescape(shown))
            self.assertIn('미국·중국·러시아 · 정상회담 장소 보도', shown)
            self.assertNotIn('우크라이나·러시아', shown)
            self.assertIn('미국·중국·러시아 · 외교 접촉 보도', shown)
            self.assertIn('이란전 종전 약속 발언 · 본문 미확인', shown)
            self.assertEqual(set(ids), {self.venue['id'], self.diplomacy['id'], self.pledge['id']})
            venue = next(row for row in final['articles'] if row['id'] == self.venue['id'])
            self.assertEqual(venue['display_section'], 'context_reference')
            self.assertIsNone(venue['classification_color'])
            self.assertEqual(final['alert_sha256'], hashlib.sha256(shown.strip().encode('utf-8')).hexdigest())
            self.assertEqual(stage.watch.STATE.read_bytes(), state_before)


if __name__ == '__main__':
    unittest.main()
