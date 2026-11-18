"""Run 897 saved semantic evidence: no HTTP, send, or live-state writes."""
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
import war_peace_reconstruction_watch_relevance_guard as relevance
import war_peace_reconstruction_watch_two_color as presentation

FIXTURE = Path(__file__).parent / 'test_fixtures' / 'war_run897_semantic_failure.json'

class Run897SemanticChecks(unittest.TestCase):
    def setUp(self):
        self.data = json.loads(FIXTURE.read_text(encoding='utf-8'))
        self.by_id = {r['id']: r for r in self.data['articles']}
        self.market = self.by_id['43510aefc1a1c4d37b04']
        self.strike = self.by_id['c877c426b1ae90291d64']
        self.summit = self.by_id['077b36608a3100ec7e41']
        self.now = dt.datetime.fromisoformat(self.data['queried_at_kst'])

    def test_saved_articles_do_not_invent_locations_stage_or_actor_uncertainty(self):
        for original in (self.market, self.strike):
            row = copy.deepcopy(original)
            row.pop('signals_ko', None)
            marks = relevance._stage_marks(row)
            self.assertTrue(any(m.startswith('이란남부') for m in marks))
            self.assertEqual(relevance._stage_signals(row, marks), [])
        self.assertIn('미군', self.strike['title_original'])
        self.assertFalse(self.strike['body_verified'])

    def test_price_headline_is_market_context_but_separate_attack_remains_red(self):
        market = copy.deepcopy(self.market)
        market.pop('signals_ko', None)
        score, tags = stage.score_item(market, self.now)
        self.assertGreaterEqual(score, 6)
        self.assertEqual(stage.non_military_kind(market), 'oil_market')
        self.assertIsNone(presentation.direction(stage, market))
        strike = copy.deepcopy(self.strike)
        strike.pop('signals_ko', None)
        score, tags = stage.score_item(strike, self.now)
        self.assertGreaterEqual(score, 6)
        self.assertEqual(presentation.direction(stage, strike), 'red')
        for title in ('유가 반등…미군 게슘 공습', '유가 하락…휴전 합의', '유가 반등…missile strike'):
            self.assertFalse(stage._oil_price_reaction_only_headline(title), title)
        actual_attack = dict(market, title_original='유가 반등…미군 게슘 공습',
                             title_ko='유가 반등…미군 게슘 공습')
        self.assertIsNone(stage.non_military_kind(actual_attack))
        self.assertEqual(presentation.direction(stage, actual_attack), 'red')

    def test_summit_topic_names_the_three_headline_participants(self):
        self.assertEqual(stage.non_military_kind(self.summit), 'diplomatic_plan')
        self.assertEqual(stage.topic_label(self.summit), '미국·중국·러시아 · 3자 정상회담 보도')
        self.assertEqual(presentation.direction(stage, self.summit), 'green')
        for title in ('미중러 3자회담 예정…우크라이나 공격', '미중러 3자회담 개최 무산'):
            self.assertFalse(stage._us_china_russia_trilateral_summit_headline(
                dict(self.summit, title_original=title)), title)

    def test_unknown_sound_remains_unconfirmed_without_invented_places(self):
        row = dict(self.strike, title_original='게슘섬서 폭발음 보도, 원인 미확인',
                   title_ko='게슘섬서 폭발음 보도, 원인 미확인', description='게슘섬 폭발음')
        row.pop('signals_ko', None)
        self.assertEqual(relevance._stage_signals(row, relevance._stage_marks(row)), [])
        self.assertIsNone(presentation.direction(stage, row))
        self.assertFalse(row['body_verified'])

    def test_saved_selection_through_presentation_gate(self):
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
                row.pop('signals_ko', None)
                row.pop('stage_marks', None)
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
            self.assertIn(self.market['title_original'], shown)
            self.assertIn(self.strike['title_original'], shown)
            self.assertNotIn('시리크', shown)
            self.assertNotIn('미나브', shown)
            self.assertNotIn('단순 폭발음에서 발사체', shown)
            self.assertNotIn('원인 미확인 단계', shown)
            saved = next(r for r in final['articles'] if r['id'] == self.strike['id'])
            self.assertFalse(saved['body_verified'])
            self.assertEqual(saved['classification_color'], 'red')
            market = next(r for r in final['articles'] if r['id'] == self.market['id'])
            self.assertIsNone(market['classification_color'])
            self.assertEqual(market['display_section'], 'market_reference')
            self.assertIn('미국·중국·러시아 · 3자 정상회담 보도', shown)
            self.assertNotIn('우크라이나·러시아', shown)
            self.assertEqual(final['alert_sha256'], hashlib.sha256(stage.watch.ALERT.read_text(encoding='utf-8').strip().encode('utf-8')).hexdigest())
            self.assertEqual(stage.watch.STATE.read_bytes(), state_before)

if __name__ == '__main__':
    unittest.main()
