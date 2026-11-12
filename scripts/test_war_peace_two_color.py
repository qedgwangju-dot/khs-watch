"""Directional presentation regressions; no collection, send, or real state writes."""
import copy
import base64
import datetime as dt
import hashlib
import html
import json
from pathlib import Path
import tempfile
import unittest
from contextlib import ExitStack
from unittest.mock import patch

import war_peace_reconstruction_watch_integrity as stage
import war_peace_reconstruction_watch_evidence as evidence
import war_peace_reconstruction_watch_runtime as runtime
import war_peace_reconstruction_watch_two_color as presentation
import war_peace_reconstruction_watch_oct04_guard as quality_guard


class TwoColorTests(unittest.TestCase):
    def setUp(self):
        self.stack = ExitStack()
        self.addCleanup(self.stack.close)
        self.folder = Path(self.stack.enter_context(tempfile.TemporaryDirectory()))
        self.watch = stage.watch
        for name, filename in {'OUT': '.', 'STATE': 'state.json', 'ALERT': 'alert.txt',
                               'AUDIT': 'evidence.json', 'PENDING': 'pending.json'}.items():
            self.stack.enter_context(patch.object(self.watch, name, self.folder/filename))
        self.watch.STATE.write_text('{"seen": [], "source_aliases": {}}', encoding='utf-8')
        self.state_before = self.watch.STATE.read_bytes()
        self.stack.enter_context(patch('urllib.request.urlopen', side_effect=AssertionError('network/send forbidden')))
        self.stack.enter_context(patch.object(stage.body_parallel, '_safe_enrich'))
        self.presenter = presentation.Presenter(stage)
        self.fixture = json.loads((Path(__file__).parent/'test_fixtures/war_market_plan_39545657385.json').read_text(encoding='utf-8'))

    def prepare(self, indices=(0, 2, 3, 4)):
        rows = [copy.deepcopy(self.fixture['articles'][i]) for i in indices]
        at = dt.datetime.fromisoformat(self.fixture['provenance']['queried_at_kst'])
        markets = self.fixture['markets']
        statuses = self.fixture['market_source_status']
        with patch.object(self.watch, 'market_source_status', statuses, create=True):
            text = stage.build_alert(rows, markets, at)
        receipt = evidence.alert_receipt(rows, markets, at, text, statuses)
        if 'original_semantic_evidence' in self.fixture:
            # The production ZIP preserves body hashes, not the full bodies.
            # Retain those exact metadata references without inventing text.
            originals = {row['id']: row for row in self.fixture['articles']}
            for row in receipt['articles']:
                row['article_text_sha256'] = originals[row['id']]['article_text_sha256']
        ids = [row['id'] for row in receipt['articles'] if row.get('rendered')]
        self.watch.ALERT.write_text(text, encoding='utf-8')
        self.watch.AUDIT.write_text(json.dumps(receipt, ensure_ascii=False), encoding='utf-8')
        self.watch.PENDING.write_text(json.dumps({'ids': ids}), encoding='utf-8')
        return text, receipt, ids

    def present(self, indices=(0, 2, 3, 4)):
        original = self.prepare(indices)
        self.presenter.verify_alert()
        return original, self.watch.ALERT.read_text(encoding='utf-8'), json.loads(self.watch.AUDIT.read_text(encoding='utf-8'))

    def test_saved_actual_four_sources_and_market_reference(self):
        (_, semantic, ids), text, receipt = self.present()
        shown = [row for row in receipt['articles'] if row.get('rendered')]
        self.assertEqual([row['classification_color'] for row in shown], [None, 'red', 'red', 'green'])
        self.assertEqual([row['semantic_classification_color'] for row in shown], ['yellow'] * 4)
        self.assertEqual([row['id'] for row in shown], ids)
        self.assertEqual(shown[0]['display_section'], 'market_reference')
        self.assertNotIn('🟡', text)
        self.assertIn('<b>시장 참고</b>', text)
        for row in semantic['articles']:
            if row.get('rendered'):
                self.assertIn(html.escape(row['title_original']), text)
        self.assertIn('4115달러선', text)
        self.assertIn('21일 푸틴에 전달', text)
        self.assertEqual(text.count('제목 기준·본문 미확인'), 4)
        self.assertIn('🔴 [신규] <b>1.', text)
        self.assertIn('🔴 [신규] <b>2.', text)
        self.assertIn('🟢 [신규] <b>3.', text)
        self.assertEqual(receipt['alert_sha256'], hashlib.sha256(text.strip().encode()).hexdigest())
        self.assertEqual(json.loads(self.watch.PENDING.read_text())['ids'], ids)
        self.assertEqual(self.watch.STATE.read_bytes(), self.state_before)

    def test_repeat_gate_and_projection_are_idempotent(self):
        self.present()
        before = [path.read_bytes() for path in (self.watch.ALERT, self.watch.AUDIT, self.watch.PENDING)]
        self.presenter.verify_alert()
        self.assertEqual(before, [path.read_bytes() for path in (self.watch.ALERT, self.watch.AUDIT, self.watch.PENDING)])

    def test_final_color_and_rehashed_evidence_tampering_rejected(self):
        self.present()
        text = self.watch.ALERT.read_text(encoding='utf-8').replace('🔴 [신규] <b>1.', '🟢 [신규] <b>1.')
        receipt = json.loads(self.watch.AUDIT.read_text(encoding='utf-8'))
        receipt['articles'][1]['classification_color'] = 'green'
        receipt['alert_sha256'] = hashlib.sha256(text.strip().encode()).hexdigest()
        self.watch.ALERT.write_text(text, encoding='utf-8')
        self.watch.AUDIT.write_text(json.dumps(receipt), encoding='utf-8')
        with self.assertRaisesRegex(RuntimeError, 'WAR_TWO_COLOR_GATE'):
            self.presenter.verify_alert()

    def test_pending_omission_rejected_by_original_gate(self):
        self.present()
        self.watch.PENDING.write_text('{"ids": []}', encoding='utf-8')
        with self.assertRaises(RuntimeError):
            self.presenter.verify_alert()

    def test_pending_duplication_rejected_by_original_gate(self):
        _, _, ids = self.prepare()
        self.watch.PENDING.write_text(json.dumps({'ids': ids + ids[:1]}), encoding='utf-8')
        with self.assertRaises(RuntimeError):
            self.presenter.verify_alert()

    def test_rehashed_wrong_semantic_subject_still_rejected(self):
        self.present()
        alert = self.folder/presentation.STAGE_ALERT
        ledger = self.folder/presentation.STAGE_EVIDENCE
        wrong = alert.read_text(encoding='utf-8').replace('21일 푸틴에 전달', '21일 시진핑에 전달')
        alert.write_text(wrong, encoding='utf-8')
        semantic = json.loads(ledger.read_text(encoding='utf-8'))
        semantic['alert_sha256'] = hashlib.sha256(wrong.strip().encode()).hexdigest()
        ledger.write_text(json.dumps(semantic), encoding='utf-8')
        receipt = json.loads(self.watch.AUDIT.read_text(encoding='utf-8'))
        receipt['semantic_proof'] = {'alert_sha256': presentation.digest(alert.read_bytes()),
                                     'evidence_sha256': presentation.digest(ledger.read_bytes())}
        self.watch.AUDIT.write_text(json.dumps(receipt), encoding='utf-8')
        with self.assertRaises(RuntimeError):
            self.presenter.verify_alert()

    def test_all_saved_inputs_keep_stale_and_duplicate_exclusions(self):
        (_, _, ids), _, receipt = self.present(tuple(range(8)))
        stale = next(row for row in receipt['articles'] if row['id'] == '877f9a1da6e73bf7e037')
        self.assertFalse(stale['rendered'])
        self.assertEqual(stale['render_withheld'], 'origin_publication_stale_or_future')
        self.assertEqual(len(ids), 4)
        self.assertNotIn('9dc2c6f2254dd75c7b9a', ids)
        self.assertEqual(self.watch.STATE.read_bytes(), self.state_before)

    def test_neutral_only_has_no_forced_direction(self):
        (_, _, ids), text, receipt = self.present((0,))
        self.assertEqual(len(ids), 1)
        self.assertNotIn('<b>핵심 변화</b>', text)
        self.assertNotIn('🔴', text)
        self.assertNotIn('🟢', text)
        self.assertIsNone(receipt['articles'][0]['classification_color'])
        self.presenter.verify_alert()

    def test_saved_natural_election_commentary_is_not_an_attack_alert(self):
        fixture = json.loads((Path(__file__).parent/'test_fixtures/war_election_commentary_41929297790.json').read_text(encoding='utf-8'))
        semantic_alert = base64.b64decode(fixture['semantic_alert_utf8_base64']).decode('utf-8')
        semantic_evidence = json.loads(base64.b64decode(fixture['semantic_evidence_utf8_base64']))
        self.assertEqual(fixture['production_run_id'], '41929297790')
        self.assertEqual(hashlib.sha256(semantic_alert.encode()).hexdigest(),
                         fixture['semantic_proof']['alert_sha256'])
        text, receipt = presentation.project(
            stage, semantic_alert, semantic_evidence, fixture['semantic_proof'],
            {'alert_utf8_base64': fixture['semantic_alert_utf8_base64'],
             'evidence_utf8_base64': fixture['semantic_evidence_utf8_base64']})
        shown = [row for row in receipt['articles'] if row.get('rendered')]
        political = [row for row in shown if '중간선거' in row['title_original']
                     and row['source'] == '파이낸스투데이']
        self.assertEqual(len(political), 3)
        self.assertTrue(all(row['classification_color'] is None for row in political))
        self.assertTrue(all(row['display_section'] == 'context_reference' for row in political))
        self.assertIn('<b>배경·시장 참고</b>', text)
        self.assertIn('이란 전쟁 · 중간선거 관련 발언', text)
        self.assertIn('방향성 기사 없음 · 배경·시장 참고만 확인', text)
        self.assertNotIn('🔴 <b>공격·타격·확전·압박</b>', text)
        self.assertNotIn('이란·호르무즈', text)
        self.assertEqual(receipt['alert_sha256'], hashlib.sha256(text.strip().encode()).hexdigest())
        self.assertNotEqual(receipt['alert_sha256'], fixture['original_delivery_alert_sha256'])
        self.watch.ALERT.write_text(semantic_alert, encoding='utf-8')
        self.watch.AUDIT.write_text(json.dumps(semantic_evidence, ensure_ascii=False), encoding='utf-8')
        self.watch.PENDING.write_text(json.dumps({'ids': [row['id'] for row in shown]}), encoding='utf-8')
        self.presenter.verify_alert()
        self.assertEqual(self.watch.ALERT.read_text(encoding='utf-8'), text)
        self.presenter.verify_alert()
        self.assertEqual(self.watch.STATE.read_bytes(), self.state_before)

    def test_election_commentary_does_not_hide_a_separate_attack(self):
        title = '중간선거 발언 뒤 이란 전쟁 후회 없다…이란이 호르무즈 유조선 공격 재개'
        row = {'title_original': title, 'tags': ['정치일정']}
        self.assertEqual(presentation.direction(stage, row), 'red')

    def test_saved_run_791_election_outlook_does_not_become_war_direction(self):
        fixture = json.loads((Path(__file__).parent / 'test_fixtures' /
                              'war_election_commentary_41960942520.json').read_text(encoding='utf-8'))
        semantic_alert = base64.b64decode(fixture['semantic_alert_utf8_base64']).decode('utf-8')
        semantic_evidence = json.loads(base64.b64decode(fixture['semantic_evidence_utf8_base64']))
        self.assertEqual(hashlib.sha256(semantic_alert.encode()).hexdigest(),
                         fixture['semantic_proof']['alert_sha256'])
        text, receipt = presentation.project(
            stage, semantic_alert, semantic_evidence, fixture['semantic_proof'],
            {'alert_utf8_base64': fixture['semantic_alert_utf8_base64'],
             'evidence_utf8_base64': fixture['semantic_evidence_utf8_base64']})
        shown = [row for row in receipt['articles'] if row.get('rendered')]
        self.assertEqual(len(shown), 4)
        self.assertEqual([row['classification_color'] for row in shown], [None] * 4)
        self.assertTrue(all(row['display_section'] == 'context_reference' for row in shown))
        self.assertNotIn('이란·호르무즈', text)
        self.assertNotIn('🔴', text)
        self.assertNotIn('🟢', text)
        self.assertIn('북미회담 영향은?', html.unescape(text))
        self.assertIn('공습', html.unescape(text))
        self.assertEqual(receipt['alert_sha256'], hashlib.sha256(text.strip().encode()).hexdigest())

    def test_natural_807_commentary_and_pending_decision_are_context(self):
        # Exact pre-presentation inputs from naturally scheduled run 42173758170.
        # All three articles were title-only; the first two were sent as red.
        fixture = json.loads((Path(__file__).parent / 'test_fixtures' /
                              'war_live_headlines_42173758170.json').read_text(encoding='utf-8'))
        snapshot = fixture['semantic_snapshot']
        semantic_alert = base64.b64decode(snapshot['alert_utf8_base64']).decode('utf-8')
        semantic_evidence = json.loads(base64.b64decode(snapshot['evidence_utf8_base64']))
        self.assertEqual(hashlib.sha256(semantic_alert.encode()).hexdigest(),
                         fixture['semantic_proof']['alert_sha256'])
        self.assertEqual(hashlib.sha256(base64.b64decode(snapshot['evidence_utf8_base64'])).hexdigest(),
                         fixture['semantic_proof']['evidence_sha256'])
        text, receipt = presentation.project(
            stage, semantic_alert, semantic_evidence, fixture['semantic_proof'], snapshot)
        shown = [row for row in receipt['articles'] if row.get('rendered')]
        self.assertEqual([row['id'] for row in shown], fixture['article_ids'])
        self.assertEqual([row['classification_color'] for row in shown], [None, None, 'red'])
        self.assertEqual([row['display_section'] for row in shown],
                         ['context_reference', 'context_reference', 'core'])
        self.assertTrue(all(not row['body_verified'] for row in shown))
        self.assertIn('중간선거 참패가 이란전쟁을 바꿀까', html.unescape(text))
        self.assertIn('이란 전쟁 논의', html.unescape(text))
        self.assertIn('7개 조건 수용 전엔 호르무즈 봉쇄 못 풀어', html.unescape(text))
        self.assertIn('🔴 <b>공격·타격·확전·압박 관련:</b> 1건', text)
        self.assertIn('<b>배경·시장 참고</b>', text)
        self.assertEqual(text.count('제목 기준·본문 미확인'), 3)
        self.assertNotEqual(receipt['alert_sha256'], fixture['original_delivery_alert_sha256'])
        self.watch.ALERT.write_text(semantic_alert, encoding='utf-8')
        self.watch.AUDIT.write_text(json.dumps(semantic_evidence, ensure_ascii=False), encoding='utf-8')
        self.watch.PENDING.write_text(json.dumps({'ids': fixture['article_ids']}), encoding='utf-8')
        self.presenter.verify_alert()
        self.assertEqual(self.watch.ALERT.read_text(encoding='utf-8'), text)
        self.assertEqual(self.watch.STATE.read_bytes(), self.state_before)

    def test_pending_decision_does_not_hide_separate_attack(self):
        title = '트럼프, 안보회의서 이란 전쟁 논의…"곧 결정"·이란 공습 지시'
        self.assertEqual(presentation.direction(stage, {'title_original': title}), 'red')

    def test_saved_run_794_mixed_headlines_keep_market_and_outlook_as_context(self):
        fixture = json.loads((Path(__file__).parent / 'test_fixtures' /
                              'war_mixed_headlines_42017880202.json').read_text(encoding='utf-8'))
        semantic_alert = base64.b64decode(fixture['semantic_alert_utf8_base64']).decode('utf-8')
        semantic_evidence = json.loads(base64.b64decode(fixture['semantic_evidence_utf8_base64']))
        self.assertEqual(fixture['production_run_id'], '42017880202')
        self.assertEqual(hashlib.sha256(semantic_alert.encode()).hexdigest(),
                         fixture['semantic_proof']['alert_sha256'])
        text, receipt = presentation.project(
            stage, semantic_alert, semantic_evidence, fixture['semantic_proof'],
            {'alert_utf8_base64': fixture['semantic_alert_utf8_base64'],
             'evidence_utf8_base64': fixture['semantic_evidence_utf8_base64']})
        shown = [row for row in receipt['articles'] if row.get('rendered')]
        self.assertEqual([row['classification_color'] for row in shown],
                         ['red', None, 'red', None])
        self.assertEqual([row['display_section'] for row in shown],
                         ['core', 'context_reference', 'core', 'context_reference'])
        self.assertTrue(all(not row['body_verified'] for row in shown))
        self.assertIn('종전 기대감', html.unescape(text))
        self.assertIn('공격·협상·봉쇄 유지 모두 난관', html.unescape(text))
        self.assertIn('🔴 <b>공격·타격·확전·압박 관련:</b> 2건', text)
        self.assertIn('<b>배경·시장 참고</b>', text)
        self.assertNotEqual(receipt['alert_sha256'], fixture['original_delivery_alert_sha256'])
        self.watch.ALERT.write_text(semantic_alert, encoding='utf-8')
        self.watch.AUDIT.write_text(json.dumps(semantic_evidence, ensure_ascii=False), encoding='utf-8')
        self.watch.PENDING.write_text(json.dumps({'ids': [row['id'] for row in shown]}), encoding='utf-8')
        self.presenter.verify_alert()
        self.assertEqual(self.watch.ALERT.read_text(encoding='utf-8'), text)
        self.presenter.verify_alert()
        self.assertEqual(self.watch.STATE.read_bytes(), self.state_before)

    def test_saved_run_796_diplomacy_and_political_commentary_not_false_red(self):
        fixture = json.loads((Path(__file__).parent / 'test_fixtures' /
                              'war_diplomacy_42019958552.json').read_text(encoding='utf-8'))
        semantic_alert = base64.b64decode(fixture['semantic_alert_utf8_base64']).decode('utf-8')
        semantic_evidence = json.loads(base64.b64decode(fixture['semantic_evidence_utf8_base64']))
        self.assertEqual(fixture['production_run_id'], '42019958552')
        self.assertEqual(hashlib.sha256(semantic_alert.encode()).hexdigest(),
                         fixture['semantic_proof']['alert_sha256'])
        text, receipt = presentation.project(
            stage, semantic_alert, semantic_evidence, fixture['semantic_proof'],
            {'alert_utf8_base64': fixture['semantic_alert_utf8_base64'],
             'evidence_utf8_base64': fixture['semantic_evidence_utf8_base64']})
        shown = [row for row in receipt['articles'] if row.get('rendered')]
        self.assertEqual(len(shown), 4)
        self.assertEqual([row['classification_color'] for row in shown],
                         [None, 'green', None, 'green'])
        self.assertEqual([row['body_verified'] for row in shown], [True, False, False, False])
        self.assertEqual([row['display_section'] for row in shown],
                         ['context_reference', 'core', 'context_reference', 'core'])
        self.assertIn('종전 MOU 초안', html.unescape(text))
        self.assertIn('68조원 보상', html.unescape(text))
        self.assertIn('🟢 <b>대화·협상·완화 관련:</b> 2건', text)
        self.assertNotIn('🔴 <b>공격·타격·확전·압박', text)
        self.assertIn('제목 기준·본문 미확인', text)
        self.assertNotEqual(receipt['alert_sha256'], fixture['original_delivery_alert_sha256'])
        self.watch.ALERT.write_text(semantic_alert, encoding='utf-8')
        self.watch.AUDIT.write_text(json.dumps(semantic_evidence, ensure_ascii=False), encoding='utf-8')
        self.watch.PENDING.write_text(json.dumps({'ids': [row['id'] for row in shown]}), encoding='utf-8')
        self.presenter.verify_alert()
        self.assertEqual(self.watch.ALERT.read_text(encoding='utf-8'), text)
        self.assertEqual(self.watch.STATE.read_bytes(), self.state_before)

    def test_saved_run_798_hypothetical_peace_or_escalation_is_context(self):
        fixture = json.loads((Path(__file__).parent / 'test_fixtures' /
                              'war_outlook_42023094034.json').read_text(encoding='utf-8'))
        semantic_alert = base64.b64decode(fixture['semantic_alert_utf8_base64']).decode('utf-8')
        semantic_evidence = json.loads(base64.b64decode(fixture['semantic_evidence_utf8_base64']))
        self.assertEqual(fixture['production_run_id'], '42023094034')
        self.assertEqual(hashlib.sha256(semantic_alert.encode()).hexdigest(),
                         fixture['semantic_proof']['alert_sha256'])
        text, receipt = presentation.project(
            stage, semantic_alert, semantic_evidence, fixture['semantic_proof'],
            {'alert_utf8_base64': fixture['semantic_alert_utf8_base64'],
             'evidence_utf8_base64': fixture['semantic_evidence_utf8_base64']})
        shown = [row for row in receipt['articles'] if row.get('rendered')]
        self.assertEqual(len(shown), 2)
        self.assertEqual([row['classification_color'] for row in shown], [None, 'red'])
        self.assertEqual([row['display_section'] for row in shown],
                         ['context_reference', 'core'])
        self.assertEqual([row['body_verified'] for row in shown], [False, True])
        self.assertIn('종전이냐 확전이냐', html.unescape(text))
        self.assertIn('튀르키예', html.unescape(text))
        self.assertIn('🔴 <b>공격·타격·확전·압박 관련:</b> 1건', text)
        self.assertIn('<b>배경·시장 참고</b>', text)
        self.assertIn('제목 기준·본문 미확인', text)
        self.assertNotEqual(receipt['alert_sha256'], fixture['original_delivery_alert_sha256'])
        self.watch.ALERT.write_text(semantic_alert, encoding='utf-8')
        self.watch.AUDIT.write_text(json.dumps(semantic_evidence, ensure_ascii=False), encoding='utf-8')
        self.watch.PENDING.write_text(json.dumps({'ids': [row['id'] for row in shown]}), encoding='utf-8')
        self.presenter.verify_alert()
        self.assertEqual(self.watch.ALERT.read_text(encoding='utf-8'), text)
        self.assertEqual(self.watch.STATE.read_bytes(), self.state_before)

    def test_peace_or_escalation_question_does_not_hide_a_separate_action(self):
        cases = (
            '종전이냐 확전이냐 기로…이란이 공격 재개',
            '종전이냐 확전이냐 기로…이란이 확전 결정',
        )
        for title in cases:
            with self.subTest(title=title):
                self.assertEqual(presentation.direction(
                    stage, {'title_original': title, 'tags': ['종전·협상', '확전']}), 'red')

    def test_election_headline_with_separate_present_action_keeps_direction(self):
        cases = (
            ('중간선거 영향 속 이란 공습 재개', 'red'),
            ('중간선거 전망 속 이란 공습 지시', 'red'),
            ('중간선거 영향 속 미국·이란 회담 재개', 'green'),
        )
        for title, expected in cases:
            with self.subTest(title=title):
                row = {'title_original': title, 'title_ko': title, 'tags': ['정치일정']}
                self.assertEqual(presentation.direction(stage, row), expected)

    def test_market_numbers_and_freshness_labels_preserved(self):
        (old, old_evidence, _), text, receipt = self.present()
        old_market = old.split('<b>시장 반응</b>', 1)[1].split('<b>투자 판정</b>', 1)[0].strip()
        new_market = text.split('<b>시장 반응</b>', 1)[1].split('<b>투자 판정</b>', 1)[0].strip()
        self.assertEqual(new_market, old_market)
        self.assertEqual(receipt['markets'], old_evidence['markets'])
        self.assertEqual(receipt['market_source_status'], old_evidence['market_source_status'])

    def test_direction_matrix_preserves_action_stage(self):
        cases = (
            ('트럼프 특사, 푸틴과 회담 추진', 'green'),
            ('미국·러시아, 평화협상 재개 논의', 'green'),
            ('젤렌스키, 패트리엇 주면 러시아 공격 중단 제안', 'green'),
            ('미국, 이란 공격하지 않겠다', 'green'),
            ('러시아가 우크라이나 공습했다', 'red'),
            ('트럼프, 이란 공격 예고', 'red'),
            ('네타냐후, 이란 공습 검토', 'red'),
            ('트럼프, 젤렌스키에 종전 압박', 'red'),
            ('우크라이나·러시아 평화협상 결렬', 'red'),
            ('러시아, 에너지 휴전 파기', 'red'),
            ('이란, 종전 협상 지연', 'red'),
            ('미국, 이란 공격 부인…호르무즈 봉쇄 유지', 'red'),
            ('트럼프 특사, 푸틴과 회담 추진 부인', 'red'),
            ('우크라, 공격 자제했지만 러는 아냐', 'red'),
            ('이란, 협상 지연하지 않겠다', 'green'),
            ('미국, 이란 제재 완화 논의', 'green'),
            ('미국, 이란 제재 완화 거부', 'red'),
            ('국제 금값, 이란 종전 협상 불확실성에 약세…온스당 4115달러선', None),
        )
        for title, expected in cases:
            with self.subTest(title=title):
                row = {'title_original': title, 'title_ko': title}
                self.assertEqual(presentation.direction(stage, row), expected)

    def test_natural_778_pressure_and_oil_price_are_not_reversed(self):
        # Exact selected article rows and semantic alert from natural run
        # 41730348909. The sent message painted pressure green and turned a
        # US-Iran oil-price story into a red Ukraine energy-ceasefire item.
        fixture = json.loads((Path(__file__).parent / 'test_fixtures' /
                              'war_live_label_41730348909.json').read_text(encoding='utf-8'))
        text, receipt = presentation.project(
            stage, fixture['semantic_text'], {'articles': fixture['articles']}, {}, {})
        rows = [row for row in receipt['articles'] if row.get('rendered')]
        self.assertEqual([row['classification_color'] for row in rows],
                         ['red', 'green', None, None])
        self.assertIn('🔴 [속보] <b>1. 이란·호르무즈</b>', text)
        self.assertIn('설득력 없어', text)
        self.assertIn('[금/유가] 美-이란 종전 기대 속 브렌트유', text)
        self.assertNotIn('우크라이나·러시아 · 에너지 휴전 발표', text)
        self.assertNotIn('🔴 [신규] <b>3.', text)
        self.assertEqual(text.count('<b>참고 '), 2)
        self.assertEqual(text.count('공격·타격·확전·압박 관련:</b> 1건'), 1)
        self.assertEqual(text.count('대화·협상·완화 관련:</b> 1건'), 1)

    def test_natural_780_airstrike_and_conditional_oil_outlook(self):
        # Saved public article rows from the first post-merge production push.
        # It sent an airstrike as green diplomacy and an oil outlook as red.
        fixture = json.loads((Path(__file__).parent / 'test_fixtures' /
                              'war_live_label_41736796260.json').read_text(encoding='utf-8'))
        now = dt.datetime.fromisoformat('2026-11-04T08:11:00+09:00')
        rows = [copy.deepcopy(fixture['articles'][i]) for i in (0, 3)]
        for row in rows:
            score, tags = stage.score_item(row, now)
            row['score'], row['tags'] = score, tags
        self.assertEqual([row['tags'] for row in rows],
                         [['대공습 보도'], ['원유 공급·가격 보도']])
        with patch.object(self.watch, 'market_source_status', {}, create=True):
            semantic = stage.build_alert(rows, [], now)
        receipt = evidence.alert_receipt(rows, [], now, semantic, {})
        text, projected = presentation.project(stage, semantic, receipt, {}, {})
        self.assertIn('🔴 [신규] <b>1. 우크라이나·러시아 · 대공습 보도</b>', text)
        self.assertIn('<b>참고 1. 원유시장 · 원유 공급·가격 보도</b>', text)
        self.assertNotIn('🟢 [신규] <b>1.', text)
        self.assertNotIn('🔴 [속보] <b>2.', text)
        self.assertEqual([row['classification_color'] for row in projected['articles']],
                         ['red', None])
        self.assertFalse(rows[0]['body_verified'])
        self.assertFalse(stage._reported_major_airstrike(
            '러시아 대공습 보류…우크라와 협상 재개'))
        self.assertNotEqual(stage.non_military_kind({
            'title_original': '이란 해법 땐 유가 80달러대로…러시아 대공습'}), 'oil_market')

    def test_saved_nov03_escalation_ahead_of_talks_is_red(self):
        # Natural schedule run 41611279264 sent these two exact headline-only
        # rows as green "외교 접촉 보도" although each reports escalating clashes.
        cases = (
            ('러시아·우크라 충돌 격화…"종전 협상 앞두고 주도권 싸움" - news.sbs.co.kr',
             'Tue, 03 Nov 2026 09:15:24 GMT'),
            ('러·우크라 충돌 격화…"종전협상 앞두고 주도권 싸움" - 연합뉴스',
             'Tue, 03 Nov 2026 08:58:19 GMT'),
        )
        now = dt.datetime.fromisoformat('2026-11-03T18:30:13+09:00')
        for title, published in cases:
            with self.subTest(title=title):
                row = {'title_original': title, 'title_ko': title,
                       'description': title, 'source': title.rsplit(' - ', 1)[-1],
                       'published': published, 'body_verified': False,
                       'tags': ['외교 접촉 보도']}
                kind = stage.non_military_kind(row)
                score, tags = stage.score_item(row, now)
                self.assertGreater(score, 0)
                self.assertEqual(tags, ['충돌·교전 격화 보도'])
                self.assertEqual(kind, 'military_report')
                self.assertEqual(stage._headline_event_label(row, kind), '충돌·교전 격화 보도')
                self.assertEqual(presentation.direction(stage, row), 'red')
        self.assertEqual(presentation.direction(stage, {
            'title_original': '미국·러시아, 종전 협상 재개 논의',
            'title_ko': '미국·러시아, 종전 협상 재개 논의',
        }), 'green')

    def test_saved_unverified_ceasefire_headlines_are_green_not_default_red(self):
        # These two exact rows were sent by natural run 39982159473. Both had
        # an explicit diplomacy tag, no verified article body, no recognized
        # event kind, and an empty semantic color; the old fallback painted
        # them red solely because direction() defaulted unknowns to red.
        cases = (
            {
                'id': 'daaaa24132fd5fc5d15c',
                'title_original': 'Kremlin confirms Oleshky ceasefire, says working with Ukraine on evacuation timing',
                'title_ko': '크렘린은 Oleshky 휴전을 확인하고 대피시기에 대해 우크라이나와 협력하고 있다고 밝혔습니다.',
                'source': 'Reuters',
                'link': 'https://www.reuters.com/world/europe/kremlin-confirms-oleshky-ceasefire-says-working-with-ukraine-evacuation-timing-2026-10-23/',
                'tags': ['종전·협상'], 'body_checked': True, 'body_verified': False,
            },
            {
                'id': '3d8a691a4e8947180e4b',
                'title_original': '크렘린궁 "러시아·우크라이나군, 휴전 날짜 조율 중" - 블루밍비트',
                'title_ko': '크렘린궁 "러시아·우크라이나군, 휴전 날짜 조율 중" - 블루밍비트',
                'description': '크렘린궁 "러시아·우크라이나군, 휴전 날짜 조율 중" 블루밍비트',
                'source': '블루밍비트', 'source_url': 'https://bloomingbit.io',
                'link': 'https://news.google.com/rss/articles/CBMiUEFVX3lxTE5qY0RERUhDQnZVLVlTWjZ5SGJvLWNvOXFJd0FOTjBScnVEMktqMTJGaEJwcHJHN2EyaUZYWVpJeXVzVGVneTI0M0NwYks0anVS?oc=5',
                'tags': ['종전·협상'], 'body_checked': True, 'body_verified': False,
            },
        )
        for row in cases:
            with self.subTest(article_id=row['id']):
                self.assertFalse(row['body_verified'])
                self.assertIsNone(stage.non_military_kind(row))
                self.assertEqual(stage.final_color(row), '')
                self.assertEqual(presentation.direction(stage, row), 'green')

        adverse = (
            'Kremlin delays ceasefire talks',
            'Kremlin denies ceasefire date coordination',
            'Russia resumed attacks as ceasefire talks continue',
        )
        for title in adverse:
            with self.subTest(title=title):
                row = {'title_original': title, 'tags': ['종전·협상'], 'body_verified': False}
                self.assertEqual(presentation.direction(stage, row), 'red')

    def test_saved_unverified_ceasefire_rows_render_green_without_claiming_body_verification(self):
        rows = [
            {
                'id': 'daaaa24132fd5fc5d15c',
                'title_original': 'Kremlin confirms Oleshky ceasefire, says working with Ukraine on evacuation timing',
                'title_ko': '크렘린은 Oleshky 휴전을 확인하고 대피시기에 대해 우크라이나와 협력하고 있다고 밝혔습니다.',
                'source': 'Reuters',
                'link': 'https://www.reuters.com/world/europe/kremlin-confirms-oleshky-ceasefire-says-working-with-ukraine-evacuation-timing-2026-10-23/',
                'tags': ['종전·협상'], 'rendered': True, 'body_checked': True,
                'body_verified': False, 'classification_color': '',
                'article_text_sha256': 'e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855',
            },
            {
                'id': '3d8a691a4e8947180e4b',
                'title_original': '크렘린궁 "러시아·우크라이나군, 휴전 날짜 조율 중" - 블루밍비트',
                'title_ko': '크렘린궁 "러시아·우크라이나군, 휴전 날짜 조율 중" - 블루밍비트',
                'description': '크렘린궁 "러시아·우크라이나군, 휴전 날짜 조율 중" 블루밍비트',
                'source': '블루밍비트',
                'link': 'https://news.google.com/rss/articles/CBMiUEFVX3lxTE5qY0RERUhDQnZVLVlTWjZ5SGJvLWNvOXFJd0FOTjBScnVEMktqMTJGaEJwcHJHN2EyaUZYWVpJeXVzVGVneTI0M0NwYks0anVS?oc=5',
                'tags': ['종전·협상'], 'rendered': True, 'body_checked': True,
                'body_verified': False, 'classification_color': '',
                'article_text_sha256': 'e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855',
            },
        ]
        semantic = [
            '<b>조회</b> 2026-10-24 00:54 KST',
            '🔴 <b>공격·타격·확전·압박</b>',
            '<b>핵심 변화</b>',
            '🔴 [속보] <b>1. Kremlin confirms Oleshky ceasefire, says working with Ukraine on evacuation timing</b>',
            '<a href="' + rows[0]['link'] + '">Reuters</a>',
            'RSS 입력 기준·본문 미확인',
            '🔴 [속보] <b>2. 크렘린궁 "러시아·우크라이나군, 휴전 날짜 조율 중" - 블루밍비트</b>',
            '<a href="' + rows[1]['link'] + '">블루밍비트</a>',
            '제목 기준·본문 미확인',
            '<b>투자 판정</b>',
            '- 기존 의미 단계',
        ]
        text, receipt = presentation.project(
            stage, '\n'.join(semantic), {'articles': rows}, {}, {})
        shown = [row for row in receipt['articles'] if row.get('rendered')]
        self.assertEqual([row['classification_color'] for row in shown], ['green', 'green'])
        self.assertEqual([row['semantic_classification_color'] for row in shown], ['', ''])
        self.assertTrue(all(row['body_verified'] is False for row in shown))
        self.assertIn('🟢 <b>대화·협상·완화</b>', text)
        self.assertNotIn('🔴 <b>공격·타격·확전·압박</b>', text)
        self.assertIn('본문 미확인', text)
        self.assertIn('대화·협상·완화 관련:</b> 2건', text)

    def test_saved_starlink_speed_restriction_restoration_is_green_despite_background_attack_tags(self):
        row = json.loads((Path(__file__).parent/'test_fixtures/war_starlink_restriction_lift_40087506788.json').read_text(encoding='utf-8'))
        self.assertFalse(row['body_verified'])
        self.assertIn('확전', row['forced_tags'])
        self.assertIsNone(stage.non_military_kind(row))
        self.assertEqual(presentation.direction(stage, row), 'green')

        block = [
            '🔴 [신규] <b>1. ' + html.escape(row['title_original'], quote=False) + '</b>',
            '<a href="' + row['link'] + '">Axios 원문</a>',
            'RSS 입력 기준·본문 미확인',
        ]
        semantic_text = '\n'.join([
            '<b>전쟁·종전·재건 웹감시</b>',
            '🔴 <b>공격·타격·확전·압박</b>',
            '조회 2026-10-24 19:51 KST',
            '<b>핵심 변화</b>',
            *block,
            '<b>투자 판정</b>',
            '- 이전 분류 요약',
        ])
        text, receipt = presentation.project(stage, semantic_text, {'articles': [row]}, {}, {})
        projected = receipt['articles'][0]
        self.assertEqual(projected['classification_color'], 'green')
        self.assertFalse(projected['body_verified'])
        self.assertIn('🟢 [신규]', text)
        self.assertNotIn('🔴 [신규]', text)
        self.assertIn('RSS 입력 기준·본문 미확인', text)

    def test_separate_current_attack_keeps_red_when_restriction_is_lifted(self):
        row = {
            'title_original': 'Starlink speed restrictions lifted as Russia resumes attacks on Ukraine',
            'tags': ['종전·협상'],
            'body_verified': False,
        }
        self.assertEqual(presentation.direction(stage, row), 'red')

    def test_stage_proof_required_on_repeat(self):
        self.present()
        (self.folder/presentation.STAGE_EVIDENCE).unlink()
        with self.assertRaisesRegex(RuntimeError, 'missing verified event-stage proof'):
            self.presenter.verify_alert()

    def test_preserved_inline_stage_proof_survives_existing_artifact_allowlist(self):
        self.present()
        receipt = json.loads(self.watch.AUDIT.read_text(encoding='utf-8'))
        snapshot = receipt['semantic_snapshot']
        for key, filename in [('alert_utf8_base64', presentation.STAGE_ALERT),
                              ('evidence_utf8_base64', presentation.STAGE_EVIDENCE)]:
            self.assertEqual(base64.b64decode(snapshot[key], validate=True), (self.folder/filename).read_bytes())

    def test_attack_plan_hold_and_future_push_keep_distinct_directions(self):
        cases = (
            ('"네타냐후, 이란 대규모 폭격하려다 트럼프 반대에 보류" - 연합뉴스', 'green', '보류·반대'),
            ('네타냐후, 이란에 대한 대규모 공습 재개 추진 - Investing.com 한국어', 'red', '계획·추진'),
            ('"네타냐후, 이란 공격 재개 추진…트럼프는 반대" - 마켓인', 'red', '계획·추진'),
        )
        for title, color, label in cases:
            with self.subTest(title=title):
                row = {'title_original': title, 'title_ko': title}
                self.assertEqual(stage.non_military_kind(row), 'military_discussion')
                self.assertEqual(stage.final_color(row), 'yellow')
                self.assertEqual(presentation.direction(stage, row), color)
                self.assertIn(label, stage.topic_label(row))
                self.assertNotIn('호르무즈', stage.topic_label(row))

    def test_separate_actual_attack_wins_over_held_plan(self):
        for suffix in ('…러시아 공습했다', '…미국 미사일 발사'):
            row = {'title_original': '네타냐후, 이란 대규모 폭격하려다 트럼프 반대에 보류' + suffix}
            self.assertEqual(presentation.direction(stage, row), 'red')
        row = {'title_original': '네타냐후, 이란 공습 계획 보류…러시아 공습 재개 추진'}
        self.assertEqual(presentation.direction(stage, row), 'red')

    def test_attack_plan_denial_and_negated_hold(self):
        row = {'title_original': '네타냐후, 이란 공습 재개 추진 부인'}
        self.assertEqual(stage._attack_plan_status(stage._headline(row)), 'denied')
        self.assertEqual(presentation.direction(stage, row), 'green')
        self.assertIn('계획 부인', stage.topic_label(row))
        row = {'title_original': '네타냐후, 이란 공습 재개 추진 보류하지 않았다'}
        self.assertNotEqual(stage._attack_plan_status(stage._headline(row)), 'held')
        self.assertEqual(presentation.direction(stage, row), 'red')

    def test_latest_operating_saved_full_body_and_inline_proof(self):
        self.fixture = json.loads((Path(__file__).parent/'test_fixtures/war_two_color_hold_39550874373.json').read_text(encoding='utf-8'))
        (_, _, ids), text, receipt = self.present((0, 1, 2, 3))
        rows = [row for row in receipt['articles'] if row.get('rendered')]
        self.assertEqual([row['classification_color'] for row in rows], ['red', 'green', 'red', 'red'])
        self.assertEqual([row['semantic_classification_color'] for row in rows], ['yellow'] * 4)
        self.assertEqual(len(ids), 4)
        self.assertNotIn('호르무즈', text)
        self.assertIn('공습·공격 계획 보류·반대', text)
        self.assertIn('종전 합의 촉구·압박', text)
        for row in rows:
            self.assertIn(html.escape(row['title_original']), text)
        snapshot = receipt['semantic_snapshot']
        self.assertEqual(presentation.digest(base64.b64decode(snapshot['alert_utf8_base64'])), receipt['semantic_proof']['alert_sha256'])
        self.assertEqual(presentation.digest(base64.b64decode(snapshot['evidence_utf8_base64'])), receipt['semantic_proof']['evidence_sha256'])
        self.presenter.verify_alert()

    def test_runtime_cleans_and_preserves_rejected_stage_proof(self):
        self.present()
        report = {'phase': 'parse_render_verify'}
        runtime._preserve_rejected(self.watch, report)
        roles = {row['role'] for row in report['rejected_artifacts']}
        self.assertEqual(roles, {'alert', 'pending', 'evidence', 'stage_alert', 'stage_evidence'})
        self.assertTrue(all(not row['verified'] for row in report['rejected_artifacts']))
        runtime._clean(self.watch)
        for filename in (presentation.STAGE_ALERT, presentation.STAGE_EVIDENCE):
            self.assertFalse((self.folder/filename).exists())
        runtime._clean_rejected(self.watch)
        self.assertFalse(any(self.folder.glob('war_peace_reconstruction_rejected_*')))

    def test_unrealized_attack_plan_after_opposition_is_held(self):
        for title in (
            '"네타냐후, 이란 대규모 공습 추진했지만…트럼프 반대에 실행 불발" - 뉴시스',
            '이스라엘, 최근 대규모 이란 공습 준비했다 불발…트럼프가 제동 - 뉴스1',
            '네타냐후, 이란 공습 추진했지만…트럼프 제동에 실행 불발',
        ):
            with self.subTest(title=title):
                row = {'title_original': title}
                self.assertEqual(stage._attack_plan_status(stage._headline(row)), 'held')
                self.assertEqual(stage.final_color(row), 'yellow')
                self.assertEqual(presentation.direction(stage, row), 'green')
                self.assertIn('계획 보류·반대', stage.topic_label(row))

    def test_unrealized_plan_does_not_hide_separate_action_or_plan(self):
        held = '네타냐후, 이란 공습 추진했지만…트럼프 반대에 실행 불발'
        for suffix in ('…러시아 공습했다', '…미국 미사일 발사', '…이스라엘 공습 재개 추진'):
            with self.subTest(suffix=suffix):
                self.assertEqual(presentation.direction(stage, {'title_original': held + suffix}), 'red')
        for title in ('네타냐후, 이란 공습 추진했지만 실행 불발은 부인',
                      '네타냐후, 이란 공습 준비했지만 실행 불발 가능성'):
            with self.subTest(title=title):
                self.assertNotEqual(stage._attack_plan_status(stage._headline({'title_original': title})), 'held')
                self.assertEqual(presentation.direction(stage, {'title_original': title}), 'red')

    def test_future_attack_question_has_explicit_actors_and_analysis_stage(self):
        title = '미국과 이스라엘은 선거 압력 속에서 이란에 대한 공습을 재개할 것인가? - Vietnam.vn'
        row = {'title_original': title, 'title_ko': title, 'tags': ['확전']}
        self.assertEqual(stage.non_military_kind(row), 'military_analysis')
        self.assertEqual(stage.final_color(row), 'yellow')
        self.assertEqual(presentation.direction(stage, row), 'red')
        self.assertEqual(stage.topic_label(row), '미국·이스라엘·이란 · 공습·공격 재개 가능성 해설')
        self.assertEqual(stage._headline_event_label(row, 'military_analysis'), '공습·공격 재개 가능성 해설')
        self.assertNotIn('호르무즈', stage.topic_label(row))

    def test_future_attack_question_keeps_separate_completed_action(self):
        question = '미국과 이스라엘은 이란 공습을 재개할 것인가?'
        for suffix in ('…러시아는 우크라이나를 공습했다', '…이란 미사일 발사', '…미국 공습 재개했다'):
            with self.subTest(suffix=suffix):
                row = {'title_original': question + suffix}
                self.assertIsNone(stage.non_military_kind(row))
                self.assertEqual(presentation.direction(stage, row), 'red')
        row = {'title_original': question + '…네타냐후 이란 공습 재개 추진'}
        self.assertEqual(stage.non_military_kind(row), 'military_discussion')
        self.assertIn('계획·추진', stage.topic_label(row))
        self.assertEqual(presentation.direction(stage, row), 'red')

    def test_latest_natural_saved_inputs_preserve_outcome_and_question(self):
        self.fixture = json.loads((Path(__file__).parent/'test_fixtures/war_held_plan_question_39578962304.json').read_text(encoding='utf-8'))
        (_, _, ids), text, receipt = self.present((0, 1, 2, 3))
        rows = [row for row in receipt['articles'] if row.get('rendered')]
        self.assertEqual([row['classification_color'] for row in rows], ['green', 'green', 'red', 'green'])
        self.assertEqual(ids, [row['id'] for row in self.fixture['articles'][:4]])
        self.assertIn('보도시각 불일치', text)
        self.assertIn('실행 불발', text)
        self.assertIn('공습·공격 재개 가능성 해설', text)
        self.assertNotIn('호르무즈', text)
        self.assertNotIn('🟡', text)
        self.assertIn('관련:</b> 1건', text)
        self.assertIn('관련:</b> 3건', text)
        self.assertEqual(receipt['markets'], self.fixture['markets'])
        self.assertEqual(self.watch.STATE.read_bytes(), self.state_before)
        self.presenter.verify_alert()

    def test_original_same_hash_wrong_natural_stage_is_rejected(self):
        fixture = json.loads((Path(__file__).parent/'test_fixtures/war_held_plan_question_39578962304.json').read_text(encoding='utf-8'))
        self.watch.ALERT.write_text(fixture['original_semantic_alert'], encoding='utf-8')
        self.watch.AUDIT.write_text(json.dumps(fixture['original_semantic_evidence'], ensure_ascii=False), encoding='utf-8')
        ids = [row['id'] for row in fixture['articles'] if row.get('rendered')]
        self.watch.PENDING.write_text(json.dumps({'ids': ids}), encoding='utf-8')
        with self.assertRaisesRegex(RuntimeError, 'WAR_INTEGRITY_GATE'):
            self.presenter.verify_alert()

    def test_oil_export_growth_and_commercial_import_contract_are_market_reference(self):
        for title in ('이란 공격에도 안 멈췄다…걸프산 원유 수출량 오히려 늘어',
                      'Indian Oil to trim Middle East oil imports under annual deals amid Iran war'):
            with self.subTest(title=title):
                row = {'title_original': title, 'tags': ['확전'], 'signals_ko': ['old attack cache']}
                self.assertEqual(stage.non_military_kind(row), 'oil_market')
                self.assertEqual(stage.final_color(row), 'yellow')
                self.assertIsNone(presentation.direction(stage, row))
                self.assertNotIn('호르무즈', stage.topic_label(row))

    def test_labor_rights_report_has_only_headline_actors(self):
        row = {'title_original': '北 노동자들, 러시아 드론 공장서 노예 취급'}
        self.assertEqual(stage.non_military_kind(row), 'security_activity')
        self.assertEqual(stage.topic_label(row), '북한·러시아 · 노동·인권 침해 보도')
        self.assertEqual(stage._headline_event_label(row, 'security_activity'), '노동·인권 침해 보도')
        self.assertEqual(stage.final_color(row), 'yellow')
        self.assertEqual(presentation.direction(stage, row), 'red')

    def test_tanker_mine_collision_keeps_claim_quantity_and_subject(self):
        title = '미 중간선거 앞…이란 “호르무즈서 유조선 3척 기뢰 충돌” - 한겨레'
        row = {'title_original': title, 'title_ko': title}
        self.assertEqual(stage.topic_label(row), '이란·호르무즈 · 선박 기뢰 충돌 보도')
        self.assertEqual(stage.final_color(row), 'red')
        self.assertEqual(stage._display_headline(row), title)
        self.assertIn('3척', stage._display_headline(row))

    def test_market_or_labor_context_does_not_hide_separate_actual_attack(self):
        for title in ('걸프산 원유 수출량 늘어…이란 미사일 발사',
                      '北 노동자 강제노동 보도…러시아 공습했다',
                      'Indian Oil trims oil imports under annual deals…Russia attacked Ukraine'):
            with self.subTest(title=title):
                self.assertEqual(presentation.direction(stage, {'title_original': title}), 'red')

    def test_saved_push_market_references_remain_in_pending(self):
        self.fixture = json.loads((Path(__file__).parent/'test_fixtures/war_market_labor_39582589584.json').read_text(encoding='utf-8'))
        (_, _, ids), text, receipt = self.present((0, 4))
        shown = [row for row in receipt['articles'] if row.get('rendered')]
        refs = [row for row in shown if row['display_section'] == 'market_reference']
        self.assertEqual({row['id'] for row in refs}, {'239e48f494707aea2549', '9fe2b8bad47ba85bafd0'})
        self.assertEqual(len(ids), 2)
        self.assertTrue(all(row['id'] in ids and row['classification_color'] is None for row in refs))
        self.assertIn('원유 교역·계약 보도', text)
        self.assertIn('Indian Oil to trim Middle East oil imports under annual deals amid Iran war', text)
        (_, _, all_ids), text, receipt = self.present(tuple(range(6)))
        shown = [row for row in receipt['articles'] if row.get('rendered')]
        self.assertEqual(all_ids, [row['id'] for row in shown])
        self.assertEqual(len(all_ids), len(set(all_ids)))
        self.assertIn('북한·러시아 · 노동·인권 침해 보도', text)
        self.assertIn('이란·호르무즈 · 선박 기뢰 충돌 보도', text)
        self.assertNotIn('원유 가격에 직접 반영', text)
        self.assertNotIn('이란·호르무즈 · 우크라이나·러시아', text)
        self.assertEqual(receipt['markets'], self.fixture['markets'])
        self.presenter.verify_alert()
        self.assertEqual(self.watch.STATE.read_bytes(), self.state_before)

    def test_original_same_hash_market_labor_push_is_rejected(self):
        fixture = json.loads((Path(__file__).parent/'test_fixtures/war_market_labor_39582589584.json').read_text(encoding='utf-8'))
        self.watch.ALERT.write_text(fixture['original_semantic_alert'], encoding='utf-8')
        self.watch.AUDIT.write_text(json.dumps(fixture['original_semantic_evidence'], ensure_ascii=False), encoding='utf-8')
        ids = [row['id'] for row in fixture['articles'] if row.get('rendered')]
        self.watch.PENDING.write_text(json.dumps({'ids': ids}), encoding='utf-8')
        with self.assertRaisesRegex(RuntimeError, 'WAR_INTEGRITY_GATE'):
            self.presenter.verify_alert()

    def test_peace_plan_delivery_with_named_recipient_is_dialogue(self):
        for title in ('美특사, 우크라 종전안 푸틴에 전달…러, 구금 미국인 석방 - 연합뉴스',
                      '미국 특사, 새 종전안 21일 푸틴에 전달',
                      'US envoy delivers peace plan to Putin'):
            with self.subTest(title=title):
                row={'title_original':title,'title_ko':title}
                self.assertEqual(stage.non_military_kind(row),'diplomatic_plan')
                self.assertEqual(stage.final_color(row),'yellow')
                self.assertEqual(presentation.direction(stage,row),'green')
                self.assertIn('종전안 논의·전달',stage.topic_label(row))
        row={'title_original':'美특사, 우크라 종전안 푸틴에 전달…러, 구금 미국인 석방'}
        self.assertEqual(stage.topic_label(row),'미국·우크라이나·러시아 · 종전안 논의·전달')

    def test_plan_delivery_denial_or_separate_attack_does_not_turn_green(self):
        for title in ('미국 특사, 종전안 푸틴에 전달 부인',
                      '미국 특사, 종전안 푸틴에 전달하지 않았다',
                      '美특사, 종전안 푸틴에 전달…러시아 공습했다'):
            with self.subTest(title=title):
                self.assertEqual(presentation.direction(stage,{'title_original':title,'title_ko':title}),'red')

    def test_latest_push_peace_plan_delivery_and_reference_preserved(self):
        self.fixture=json.loads((Path(__file__).parent/'test_fixtures/war_peace_plan_recipient_39584508384.json').read_text(encoding='utf-8'))
        (_,_,ids),text,receipt=self.present(tuple(range(len(self.fixture['articles']))))
        shown=[row for row in receipt['articles'] if row.get('rendered')]
        delivered=next(row for row in shown if row['id']=='a84a84da65087cece33e')
        self.assertEqual(delivered['classification_color'],'green')
        self.assertIn('미국·우크라이나·러시아 · 종전안 논의·전달',text)
        self.assertIn('러, 구금 미국인 석방',text)
        self.assertEqual(ids,[row['id'] for row in shown])
        self.assertEqual(receipt['markets'],self.fixture['markets'])
        self.assertTrue(any(row['display_section']=='market_reference' and row['classification_color'] is None for row in shown))
        self.presenter.verify_alert()
        self.assertEqual(self.watch.STATE.read_bytes(),self.state_before)

    def test_original_same_hash_peace_plan_push_rejected(self):
        f=json.loads((Path(__file__).parent/'test_fixtures/war_peace_plan_recipient_39584508384.json').read_text(encoding='utf-8'))
        self.watch.ALERT.write_text(f['original_semantic_alert'],encoding='utf-8')
        self.watch.AUDIT.write_text(json.dumps(f['original_semantic_evidence'],ensure_ascii=False),encoding='utf-8')
        self.watch.PENDING.write_text(json.dumps({'ids':[r['id'] for r in f['articles'] if r['rendered']]}),encoding='utf-8')
        with self.assertRaisesRegex(RuntimeError,'WAR_INTEGRITY_GATE'):
            self.presenter.verify_alert()

    def test_received_envoy_keeps_all_explicit_actors(self):
        title='러, 우크라 종전안 가져온 美 특사 접견...억류 미국인 1명 석방'
        row={'title_original':title,'title_ko':title}
        self.assertEqual(stage.non_military_kind(row),'diplomatic_contact')
        self.assertEqual(stage.topic_label(row),'미국·우크라이나·러시아 · 외교 접촉 보도')
        self.assertEqual(presentation.direction(stage,row),'green')

    def test_possible_meeting_venue_not_added_as_participant(self):
        title='Putin, at talks with Witkoff, suggests he and Trump could meet in China'
        row={'title_original':title,'title_ko':title}
        self.assertEqual(stage.non_military_kind(row),'diplomatic_plan')
        self.assertEqual(stage.topic_label(row),'미국·러시아 · 회담 추진·논의')
        self.assertEqual(presentation.direction(stage,row),'green')
        row={'title_original':'Putin, Trump and Xi could meet in China'}
        self.assertIn('중국',stage.topic_label(row))
        row={'title_original':'Putin and Trump could not meet in China'}
        self.assertEqual(presentation.direction(stage,row),'red')
        row={'title_original':title+'…Russia attacked Ukraine'}
        self.assertEqual(presentation.direction(stage,row),'red')

    def test_saved_last_push_actor_and_venue_full_gate(self):
        self.fixture=json.loads((Path(__file__).parent/'test_fixtures/war_envoy_venue_39585466115.json').read_text(encoding='utf-8'))
        (_,_,ids),text,receipt=self.present(tuple(range(len(self.fixture['articles']))))
        self.assertIn('미국·우크라이나·러시아 · 외교 접촉 보도',text)
        self.assertIn('미국·러시아 · 회담 추진·논의',text)
        self.assertIn('억류 미국인 1명 석방',text)
        self.assertEqual(ids,[r['id'] for r in receipt['articles'] if r['rendered']])
        self.assertEqual(receipt['markets'],self.fixture['markets'])
        self.presenter.verify_alert()
        self.assertEqual(self.watch.STATE.read_bytes(),self.state_before)

    def test_original_same_hash_actor_and_venue_push_rejected(self):
        f=json.loads((Path(__file__).parent/'test_fixtures/war_envoy_venue_39585466115.json').read_text(encoding='utf-8'))
        self.watch.ALERT.write_text(f['original_semantic_alert'],encoding='utf-8')
        self.watch.AUDIT.write_text(json.dumps(f['original_semantic_evidence'],ensure_ascii=False),encoding='utf-8')
        self.watch.PENDING.write_text(json.dumps({'ids':[r['id'] for r in f['articles'] if r['rendered']]}),encoding='utf-8')
        with self.assertRaisesRegex(RuntimeError,'WAR_INTEGRITY_GATE'):
            self.presenter.verify_alert()

    def test_envoy_meeting_dialogue_preserves_explicit_actors(self):
        title="푸틴, 美특사 만나 우크라 종전 논의…'4년 억류' 미국인도 석방 - 뉴스1"
        row={'title_original':title,'title_ko':title}
        self.assertEqual(stage.non_military_kind(row),'diplomatic_contact')
        self.assertEqual(stage.topic_label(row),'미국·우크라이나·러시아 · 외교 접촉 보도')
        self.assertEqual(presentation.direction(stage,row),'green')
        row={'title_original':title+'…러시아 미사일 발사했다'}
        self.assertEqual(presentation.direction(stage,row),'red')

    def test_saved_envoy_dialogue_full_body_gate(self):
        self.fixture=json.loads((Path(__file__).parent/'test_fixtures/war_envoy_dialogue_39587189116.json').read_text(encoding='utf-8'))
        (_,_,ids),text,receipt=self.present(tuple(range(len(self.fixture['articles']))))
        matched=[r for r in receipt['articles'] if r['rendered'] and '뉴스1' in r['title_original']]
        self.assertEqual(len(matched),1)
        self.assertEqual(matched[0]['classification_color'],'green')
        self.assertIn('미국·우크라이나·러시아 · 외교 접촉 보도',text)
        self.assertIn('4년 억류',text)
        self.assertEqual(ids,[r['id'] for r in receipt['articles'] if r['rendered']])
        self.presenter.verify_alert()
        self.assertEqual(self.watch.STATE.read_bytes(),self.state_before)

    def test_original_same_hash_envoy_dialogue_push_rejected(self):
        f=json.loads((Path(__file__).parent/'test_fixtures/war_envoy_dialogue_39587189116.json').read_text(encoding='utf-8'))
        self.watch.ALERT.write_text(f['original_semantic_alert'],encoding='utf-8')
        self.watch.AUDIT.write_text(json.dumps(f['original_semantic_evidence'],ensure_ascii=False),encoding='utf-8')
        self.watch.PENDING.write_text(json.dumps({'ids':[r['id'] for r in f['articles'] if r['rendered']]}),encoding='utf-8')
        with self.assertRaisesRegex(RuntimeError,'WAR_INTEGRITY_GATE'):
            self.presenter.verify_alert()

    def test_supply_exports_with_background_attacks_are_market_reference(self):
        f=json.loads((Path(__file__).parent/'test_fixtures/war_supply_talk_stage_39619132712.json').read_text(encoding='utf-8'))
        row=f['articles'][0]
        self.assertEqual(stage.non_military_kind(row),'oil_market')
        self.assertIsNone(presentation.direction(stage,row))
        self.assertEqual(stage._display_headline(row),' '.join(row['title_original'].split()))
        self.assertIn('exceeded prewar levels',stage._display_headline(row))
        self.assertIn('despite continued attacks',stage._display_headline(row))
        self.assertNotIn('원유 물동량 회복',stage.topic_label(row))

    def test_talks_participation_willingness_and_denial_keep_their_stage(self):
        title='Russia is willing in principle to join new Ukraine peace talks in November, Kremlin says'
        row={'title_original':title,'title_ko':'러시아는 11월 평화 회담에 참여할 의사가 있다고 밝혔다'}
        self.assertEqual(stage.non_military_kind(row),'diplomatic_plan')
        self.assertEqual(stage.topic_label(row),'우크라이나·러시아 · 협상 참여 의향')
        self.assertEqual(stage._display_headline(row),title)
        self.assertEqual(presentation.direction(stage,row),'green')
        row['title_original']=title.replace('is willing','is not willing')
        self.assertEqual(stage.non_military_kind(row),'diplomatic_position')
        self.assertIn('협상 참여 의향 부인',stage.topic_label(row))
        self.assertEqual(presentation.direction(stage,row),'red')

    def test_talks_resumption_request_and_spaced_peace_plan_keep_named_actors(self):
        title='위트코프, 푸틴에 우크라 3자 종전협상 재개 요청…억류 미국인 석방 - 마켓인'
        row={'title_original':title,'title_ko':title}
        self.assertEqual(stage.non_military_kind(row),'diplomatic_plan')
        self.assertEqual(stage.topic_label(row),'미국·우크라이나·러시아 · 협상 재개 요청')
        self.assertEqual(presentation.direction(stage,row),'green')
        row={'title_original':'미 특사, 푸틴에 러·우 종전 구상 전달…3자 회담 재개 논의 - 경향신문'}
        self.assertEqual(stage.non_military_kind(row),'diplomatic_plan')
        self.assertEqual(stage.topic_label(row),'미국·우크라이나·러시아 · 종전안 논의·전달')
        self.assertEqual(presentation.direction(stage,row),'green')
        row={'title_original':title.replace('재개 요청','재개 요청하지 않았다')}
        self.assertEqual(presentation.direction(stage,row),'red')

    def test_supply_or_talks_stage_does_not_hide_separate_actual_action(self):
        for title in ('Middle East oil exports exceeded prewar levels…Russia attacked Ukraine',
                      'Russia is willing in principle to join Ukraine peace talks…Russia attacked Ukraine',
                      '미 특사, 푸틴에 러·우 종전 구상 전달…러시아 미사일 발사했다',
                      '위트코프, 종전협상 재개 요청…러시아 공습했다'):
            with self.subTest(title=title):
                self.assertEqual(presentation.direction(stage,{'title_original':title}),'red')

    def test_saved_natural_supply_and_talks_full_gate(self):
        self.fixture=json.loads((Path(__file__).parent/'test_fixtures/war_supply_talk_stage_39619132712.json').read_text(encoding='utf-8'))
        (_,_,ids),text,receipt=self.present(tuple(range(len(self.fixture['articles']))))
        shown=[r for r in receipt['articles'] if r['rendered']]
        self.assertEqual(ids,['a33dae0cda0efb8ed8e2','539d309243dda80c2b2f','b592bb744ced3c857bb1','bbc4899366754465f5d3'])
        self.assertEqual([r['classification_color'] for r in shown],[None,'green','green','green'])
        self.assertEqual(shown[0]['display_section'],'market_reference')
        self.assertIn('exceeded prewar levels',text)
        self.assertIn('despite continued attacks',text)
        self.assertIn('협상 참여 의향',text)
        self.assertIn('협상 재개 요청',text)
        self.assertIn('미국·우크라이나·러시아 · 종전안 논의·전달',text)
        self.assertNotIn('실물물동량',text)
        self.assertNotIn('🟡',text)
        self.assertEqual(receipt['markets'],self.fixture['markets'])
        self.assertEqual(next(r for r in receipt['articles'] if not r['rendered'])['render_withheld'],'origin_publication_stale_or_future')
        self.presenter.verify_alert()
        self.assertEqual(self.watch.STATE.read_bytes(),self.state_before)

    def test_original_natural_wrong_supply_body_is_still_rejected(self):
        f=json.loads((Path(__file__).parent/'test_fixtures/war_supply_talk_stage_39619132712.json').read_text(encoding='utf-8'))
        self.watch.ALERT.write_text(f['original_semantic_alert'],encoding='utf-8')
        self.watch.AUDIT.write_text(json.dumps(f['original_semantic_evidence'],ensure_ascii=False),encoding='utf-8')
        self.watch.PENDING.write_text(json.dumps({'ids':[r['id'] for r in f['articles'] if r['rendered']]}),encoding='utf-8')
        with self.assertRaisesRegex(RuntimeError,'WAR_ALERT_QUALITY_GATE|WAR_INTEGRITY_GATE'):
            self.presenter.verify_alert()

    def test_election_war_policy_outlook_preserves_stage_and_explicit_actors(self):
        title="Israel's election may change its leader, but not Iran war policy"
        row={'title_original':title,'title_ko':'이스라엘 선거 전망'}
        self.assertEqual(stage.non_military_kind(row),'military_analysis')
        self.assertEqual(stage.final_color(row),'yellow')
        self.assertEqual(stage.topic_label(row),'이스라엘·이란 · 선거·전쟁 정책 전망')
        self.assertEqual(stage._display_headline(row),title)
        self.assertEqual(presentation.direction(stage,row),'red')
        row['title_original']=title+'…Russia attacked Ukraine'
        self.assertIsNone(stage.non_military_kind(row))
        self.assertEqual(presentation.direction(stage,row),'red')

    def test_sabotage_threat_preserves_warning_source_and_target(self):
        title="Germany's military warns of 'significant' Russian sabotage threat"
        row={'title_original':title,'title_ko':title}
        self.assertEqual(stage.non_military_kind(row),'security_activity')
        self.assertEqual(stage.topic_label(row),'독일·러시아 · 파괴공작 관련 보도')
        self.assertEqual(stage.final_color(row),'yellow')
        self.assertEqual(presentation.direction(stage,row),'red')
        self.assertEqual(stage._display_headline(row),title)

    def test_saved_policy_outlook_push_full_gate_keeps_four_selected_sources(self):
        self.fixture=json.loads((Path(__file__).parent/'test_fixtures/war_policy_outlook_39622466859.json').read_text(encoding='utf-8'))
        (_,_,ids),text,receipt=self.present(tuple(range(len(self.fixture['articles']))))
        shown=[r for r in receipt['articles'] if r['rendered']]
        self.assertEqual(ids,['a33dae0cda0efb8ed8e2','b592bb744ced3c857bb1','ae77a16e6fe0613bbdef','72af9f939d0987b42be6'])
        self.assertEqual([r['classification_color'] for r in shown],[None,'green','red','red'])
        self.assertEqual([r['semantic_classification_color'] for r in shown],['yellow']*4)
        self.assertIn('독일·러시아 · 파괴공작 관련 보도',text)
        self.assertIn('이스라엘·이란 · 선거·전쟁 정책 전망',text)
        self.assertIn(html.escape("Israel's election may change its leader, but not Iran war policy"),text)
        self.assertNotIn('이란·호르무즈',text)
        self.assertNotIn('🟡',text)
        self.assertEqual(receipt['markets'],self.fixture['markets'])
        self.presenter.verify_alert()
        self.assertEqual(self.watch.STATE.read_bytes(),self.state_before)

    def test_same_hash_original_policy_outlook_and_actor_omission_rejected(self):
        f=json.loads((Path(__file__).parent/'test_fixtures/war_policy_outlook_39622466859.json').read_text(encoding='utf-8'))
        self.watch.ALERT.write_text(f['original_semantic_alert'],encoding='utf-8')
        self.watch.AUDIT.write_text(json.dumps(f['original_semantic_evidence'],ensure_ascii=False),encoding='utf-8')
        self.watch.PENDING.write_text(json.dumps({'ids':[r['id'] for r in f['articles'] if r['rendered']]}),encoding='utf-8')
        with self.assertRaisesRegex(RuntimeError,'WAR_INTEGRITY_GATE'):
            self.presenter.verify_alert()

    def test_conditional_diplomacy_keeps_the_separate_war_choice_warning(self):
        f=json.loads((Path(__file__).parent/'test_fixtures/war_policy_outlook_39622466859.json').read_text(encoding='utf-8'))['natural_cases']['39657556910']
        row=next(x for x in f['articles'] if x['id']=='c770c0f5e083fd6ae47d')
        self.assertEqual(stage.non_military_kind(row),'military_statement')
        self.assertEqual(stage.topic_label(row),'미국·이란 · 조건부 외교 의향·전쟁 선택 경고')
        self.assertEqual(stage._display_headline(row),' '.join(row['title_original'].split()))
        self.assertEqual(presentation.direction(stage,row),'red')
        self.assertIn('BUT IF US CHOOSES WAR',stage._display_headline(row))
        row=copy.deepcopy(row);row['title_original']=row['title_original'].split('\n')[0]
        self.assertEqual(stage.non_military_kind(row),'diplomatic_plan')
        self.assertEqual(presentation.direction(stage,row),'green')
        row['title_original']=row['title_original'].replace('IS PREPARED','IS NOT PREPARED')
        self.assertEqual(presentation.direction(stage,row),'red')

    def test_shipping_sanctions_and_houthi_claim_do_not_invent_geographic_actors(self):
        row={'title_original':'US sanctions Greece-, Panama-based law firm over aid to Iranian shipping'}
        self.assertEqual(stage.topic_label(row),'미국·이란·그리스·파나마 · 해운 지원 제재')
        self.assertEqual(stage._display_headline(row),row['title_original'])
        self.assertEqual(presentation.direction(stage,row),'red')
        title='후티 반군은 적의 작전 지휘 센터를 공격했다고 주장했습니다. - Vietnam.vn'
        row={'title_original':title}
        self.assertEqual(stage.topic_label(row),'후티 · 공격 주장 보도')
        self.assertEqual(stage._display_headline(row),title)
        self.assertEqual(presentation.direction(stage,row),'red')

    def test_resumption_agreement_preparation_and_venue_possibility_are_not_held_talks(self):
        cases=(('푸틴, 美·우크라와 3자 종전협상 재개 동의…11월 개최 추진 - 마켓인','미국·우크라이나·러시아 · 협상 재개 동의·개최 추진'),
               ('젤렌스키 “현재 전선에서 휴전 가능”…푸틴도 3자 종전협상 재개 동의 - 한겨레','우크라이나·러시아 · 협상 재개 동의'),
               ('러시아 "우크라 종전 협상, 내달 중순 UAE 아부다비 개최 가능성" - 뉴스1','우크라이나·러시아 · 협상 개최 가능성'),
               ('美·中·러 사상 첫 3자 정상회담 가시화… 크렘린궁 “APEC 계기 준비 착수” - 조선비즈 - Chosunbiz','미국·중국·러시아 · 회담 준비·개최 추진'),
               ('"다음달 푸틴·트럼프·시진핑 3자회담 준비 중"','미국·중국·러시아 · 회담 준비·개최 추진'))
        for title,topic in cases:
            with self.subTest(title=title):
                row={'title_original':title,'title_ko':title}
                self.assertEqual(stage.non_military_kind(row),'diplomatic_plan')
                self.assertEqual(stage.topic_label(row),topic)
                self.assertEqual(presentation.direction(stage,row),'green')
                self.assertEqual(stage._display_headline(row),title)
                self.assertEqual(presentation.direction(stage,{'title_original':title+'…러시아 미사일 발사했다'}),'red')

    def test_saved_natural_two_runs_keep_selected_sources_and_full_stage_gate(self):
        fixture=json.loads((Path(__file__).parent/'test_fixtures/war_policy_outlook_39622466859.json').read_text(encoding='utf-8'))
        for wid in ('39657556910','39685268322'):
            with self.subTest(run=wid):
                self.fixture=fixture['natural_cases'][wid]
                (_,_,ids),text,receipt=self.present(tuple(range(len(self.fixture['articles']))))
                self.assertEqual(ids,[r['id'] for r in self.fixture['articles'] if r['rendered']])
                self.assertEqual(receipt['markets'],self.fixture['markets'])
                self.assertNotIn('이란·호르무즈',text)
                self.assertNotIn('사우디·후티',text)
                self.assertNotIn('🟡',text)
                if wid=='39657556910':
                    self.assertIn('조건부 외교 의향·전쟁 선택 경고',text)
                    self.assertIn('BUT IF US CHOOSES WAR',text)
                    self.assertIn('미국·이란·그리스·파나마 · 해운 지원 제재',text)
                else:
                    self.assertIn('미국·중국·러시아 · 회담 준비·개최 추진',text)
                self.presenter.verify_alert()
                self.assertEqual(self.watch.STATE.read_bytes(),self.state_before)

    def test_same_hash_actual_natural_omissions_are_rejected(self):
        fixture=json.loads((Path(__file__).parent/'test_fixtures/war_policy_outlook_39622466859.json').read_text(encoding='utf-8'))
        for wid in ('39657556910','39685268322'):
            with self.subTest(run=wid):
                f=fixture['natural_cases'][wid]
                self.watch.ALERT.write_text(f['original_semantic_alert'],encoding='utf-8')
                self.watch.AUDIT.write_text(json.dumps(f['original_semantic_evidence'],ensure_ascii=False),encoding='utf-8')
                self.watch.PENDING.write_text(json.dumps({'ids':[r['id'] for r in f['articles'] if r['rendered']]}),encoding='utf-8')
                with self.assertRaisesRegex(RuntimeError,'WAR_INTEGRITY_GATE'):
                    self.presenter.verify_alert()

    def test_named_settlement_discussion_keeps_outlook_and_explicit_actors(self):
        title='트럼프 푸틴과 논의…우크라이나 종전, 어느 때보다 가까워 - 아주경제'
        row={'title_original':title,'title_ko':title}
        self.assertEqual(stage.non_military_kind(row),'diplomatic_plan')
        self.assertEqual(stage.topic_label(row),'미국·우크라이나·러시아 · 종전 논의·전망')
        self.assertEqual(stage._display_headline(row),title)
        self.assertEqual(presentation.direction(stage,row),'green')
        self.assertEqual(presentation.direction(stage,{'title_original':title+'…러시아 미사일 발사했다'}),'red')
        row={'title_original':title.replace('논의','논의하지 않았다')}
        self.assertEqual(stage.non_military_kind(row),'diplomatic_position')
        self.assertEqual(presentation.direction(stage,row),'red')
        self.assertIn('종전 논의 부인',stage.topic_label(row))

    def test_saudi_airport_attack_casualties_do_not_impute_houthi_actor(self):
        title='Saudi civil aviation says one killed, eight injured in attack on King Fahd airport'
        row={'title_original':title,'title_ko':'사우디 공항 피격 사상자 보도'}
        self.assertEqual(stage.topic_label(row),'사우디 · 공항 공격·피해 보도')
        self.assertEqual(stage._display_headline(row),title)
        self.assertEqual(presentation.direction(stage,row),'red')
        self.assertNotIn('후티',stage.topic_label(row))
        row={'title_original':'후티, 사우디 공항 공격으로 1명 사망·8명 부상'}
        self.assertEqual(stage.topic_label(row),'사우디·후티 · 공항 공격·피해 보도')

    def test_saved_settlement_airport_push_full_gate(self):
        self.fixture=json.loads((Path(__file__).parent/'test_fixtures/war_settlement_airport_39689493215.json').read_text(encoding='utf-8'))
        (_,_,ids),text,receipt=self.present(tuple(range(len(self.fixture['articles']))))
        self.assertEqual(ids,['25e193a1aa21821b85fb','610fee7b2f1c5296019a'])
        self.assertEqual([r['classification_color'] for r in receipt['articles'] if r['rendered']],['green','red'])
        self.assertIn('미국·우크라이나·러시아 · 종전 논의·전망',text)
        self.assertIn('사우디 · 공항 공격·피해 보도',text)
        self.assertIn('one killed, eight injured',text)
        self.assertNotIn('후티',text)
        self.assertNotIn('🟡',text)
        self.assertEqual(receipt['markets'],self.fixture['markets'])
        self.presenter.verify_alert()
        self.assertEqual(self.watch.STATE.read_bytes(),self.state_before)

    def test_same_hash_wrong_settlement_color_and_assumed_airport_actor_rejected(self):
        f=json.loads((Path(__file__).parent/'test_fixtures/war_settlement_airport_39689493215.json').read_text(encoding='utf-8'))
        self.watch.ALERT.write_text(f['original_semantic_alert'],encoding='utf-8')
        self.watch.AUDIT.write_text(json.dumps(f['original_semantic_evidence'],ensure_ascii=False),encoding='utf-8')
        self.watch.PENDING.write_text(json.dumps({'ids':[r['id'] for r in f['articles'] if r['rendered']]}),encoding='utf-8')
        with self.assertRaisesRegex(RuntimeError,'WAR_INTEGRITY_GATE'):
            self.presenter.verify_alert()

    def test_detainee_release_easing_retains_explicit_us_russia_and_outlook(self):
        title='푸틴, 트럼프 요청에 억류 미국인 석방…트럼프 “종전 가장 가까운 시점” - 아시아투데이'
        row={'title_original':title,'title_ko':title}
        self.assertEqual(stage.non_military_kind(row),'diplomatic_statement')
        self.assertEqual(stage.topic_label(row),'미국·러시아 · 억류자 석방·완화 보도')
        self.assertEqual(presentation.direction(stage,row),'green')
        self.assertEqual(stage._display_headline(row),title)
        self.assertEqual(presentation.direction(stage,{'title_original':title+'…러시아 미사일 발사했다'}),'red')
        self.assertEqual(presentation.direction(stage,{'title_original':title.replace('석방','석방하지 않았다')}),'red')
        row={'title_original':title.replace('석방','석방 검토')}
        self.assertEqual(stage.non_military_kind(row),'diplomatic_plan')
        self.assertIn('석방 계획·논의',stage.topic_label(row))

    def test_named_persian_gulf_hormuz_ships_do_not_add_iran(self):
        title='페르시아만과 호르무즈 해협서 유조선 2척 피격 - VOA 한국어 홈페이지'
        row={'title_original':title,'title_ko':title}
        self.assertEqual(stage.topic_label(row),'페르시아만·호르무즈 · 선박 피격 보도')
        self.assertEqual(presentation.direction(stage,row),'red')
        self.assertEqual(stage._display_headline(row),title)
        self.assertNotIn('이란',stage.topic_label(row))

    def test_actual_release_maritime_four_full_gate_and_selection(self):
        self.fixture=json.loads((Path(__file__).parent/'test_fixtures/war_release_maritime_39690928966.json').read_text(encoding='utf-8'))
        (_,_,ids),text,receipt=self.present(tuple(range(len(self.fixture['articles']))))
        shown=[r for r in receipt['articles'] if r['rendered']]
        self.assertEqual([r['classification_color'] for r in shown],['red','green','red','green'])
        self.assertEqual(ids,[r['id'] for r in self.fixture['articles'] if r['rendered']])
        self.assertIn('미국·러시아 · 억류자 석방·완화 보도',text)
        self.assertIn('페르시아만·호르무즈 · 선박 피격 보도',text)
        self.assertNotIn('이란',text)
        self.assertIn('유조선 2척',text)
        self.assertIn('종전 가장 가까운 시점',text)
        self.assertEqual(receipt['markets'],self.fixture['markets'])
        self.presenter.verify_alert()
        self.assertEqual(self.watch.STATE.read_bytes(),self.state_before)

    def test_same_hash_release_red_and_invented_geography_rejected(self):
        f=json.loads((Path(__file__).parent/'test_fixtures/war_release_maritime_39690928966.json').read_text(encoding='utf-8'))
        self.watch.ALERT.write_text(f['original_semantic_alert'],encoding='utf-8')
        self.watch.AUDIT.write_text(json.dumps(f['original_semantic_evidence'],ensure_ascii=False),encoding='utf-8')
        self.watch.PENDING.write_text(json.dumps({'ids':[r['id'] for r in f['articles'] if r['rendered']]}),encoding='utf-8')
        with self.assertRaisesRegex(RuntimeError,'WAR_INTEGRITY_GATE'):
            self.presenter.verify_alert()

    def test_english_strike_plan_retains_actors_reported_stage_and_source_text(self):
        f=json.loads((Path(__file__).parent/'test_fixtures/war_strike_preparation_39701551356.json').read_text(encoding='utf-8'))
        row=f['articles'][0]
        self.assertEqual(stage.non_military_kind(row),'military_discussion')
        self.assertEqual(stage._attack_plan_status(stage._headline(row)),'planned')
        self.assertEqual(stage.topic_label(row),'미국·이스라엘·이란 · 공습·공격 계획·추진')
        self.assertEqual(stage._display_headline(row),' '.join(row['title_original'].split()))
        self.assertEqual(presentation.direction(stage,row),'red')
        self.assertIn('November 3',stage._display_headline(row))
        self.assertIn('reportedly',stage._display_headline(row))

    def test_english_attack_plan_denial_and_separate_actual_action(self):
        for title in ('U.S. and Israel do not plan new Iran strikes after midterms',
                      'U.S. and Israel deny plans for renewed attacks on Iran'):
            with self.subTest(title=title):
                row={'title_original':title}
                self.assertEqual(stage._attack_plan_status(stage._headline(row)),'denied')
                self.assertEqual(stage.non_military_kind(row),'military_discussion')
                self.assertEqual(presentation.direction(stage,row),'green')
                self.assertEqual(stage._display_headline(row),title)
        title='U.S. and Israel do not plan new Iran strikes; Russia launched attacks on Ukraine'
        self.assertIsNone(stage.non_military_kind({'title_original':title}))
        self.assertEqual(presentation.direction(stage,{'title_original':title}),'red')
        self.assertIsNone(stage._attack_plan_status('U.S. plans new energy imports after attacks'))

    def test_us_ukraine_russia_abbreviations_and_resumption_readiness_stage(self):
        cases=(('푸틴, 미·우크라와 종전협상 재개 동의…11월 개최 가능성 - 신아일보','미국·우크라이나·러시아 · 협상 재개 동의'),
               ('미·러·우, 3자 정상회담 열리나…러시아 "협상 재개 준비 됐다" - 동행미디어 시대','미국·우크라이나·러시아 · 협상 재개 준비'))
        for title,topic in cases:
            with self.subTest(title=title):
                row={'title_original':title}
                self.assertEqual(stage.non_military_kind(row),'diplomatic_plan')
                self.assertEqual(stage.topic_label(row),topic)
                self.assertEqual(presentation.direction(stage,row),'green')
                self.assertEqual(stage._display_headline(row),title)
                self.assertEqual(presentation.direction(stage,{'title_original':title+'…러시아 미사일 발사했다'}),'red')
        row={'title_original':'미·러·우, 러시아 "협상 재개 준비되지 않았다"'}
        self.assertEqual(stage.non_military_kind(row),'diplomatic_position')
        self.assertEqual(stage.topic_label(row),'미국·우크라이나·러시아 · 협상 재개 준비 부인')
        self.assertEqual(presentation.direction(stage,row),'red')

    def test_saved_strike_preparation_natural_full_gate_and_selection(self):
        self.fixture=json.loads((Path(__file__).parent/'test_fixtures/war_strike_preparation_39701551356.json').read_text(encoding='utf-8'))
        (_,_,ids),text,receipt=self.present(tuple(range(len(self.fixture['articles']))))
        shown=[r for r in receipt['articles'] if r['rendered']]
        self.assertEqual(ids,[r['id'] for r in self.fixture['articles'] if r['rendered']])
        self.assertEqual([r['classification_color'] for r in shown],['red','green','green','green'])
        self.assertIn('미국·이스라엘·이란 · 공습·공격 계획·추진',text)
        self.assertIn('미국·우크라이나·러시아 · 협상 재개 준비',text)
        self.assertIn(html.escape(' '.join(shown[0]['title_original'].split())),text)
        self.assertNotIn('후속 협상 실무 의제',text)
        self.assertNotIn('이란·호르무즈',text)
        self.assertNotIn('🟡',text)
        self.assertEqual(receipt['markets'],self.fixture['markets'])
        self.assertEqual(receipt['market_source_status'],self.fixture['market_source_status'])
        self.assertTrue(all(not r.get('signals_ko') for r in shown))
        self.assertEqual(self.watch.STATE.read_bytes(),self.state_before)
        self.presenter.verify_alert()

    def test_same_hash_actual_strike_cache_and_preparation_omission_rejected(self):
        f=json.loads((Path(__file__).parent/'test_fixtures/war_strike_preparation_39701551356.json').read_text(encoding='utf-8'))
        self.watch.ALERT.write_text(f['original_semantic_alert'],encoding='utf-8')
        self.watch.AUDIT.write_text(json.dumps(f['original_semantic_evidence'],ensure_ascii=False),encoding='utf-8')
        self.watch.PENDING.write_text(json.dumps({'ids':[r['id'] for r in f['articles'] if r['rendered']]}),encoding='utf-8')
        with self.assertRaisesRegex(RuntimeError,'WAR_INTEGRITY_GATE'):
            self.presenter.verify_alert()

    def test_production_entry_installs_directional_final_gate(self):
        original = stage.runner.verify_alert
        def entry():
            self.assertIsInstance(stage.runner.verify_alert.__self__, presentation.Presenter)
            return 0
        with patch.object(stage.previous, 'main', side_effect=entry):
            try:
                self.assertEqual(stage.main(), 0)
                presentation.install(stage)
                self.assertIs(stage.runner.verify_alert.__self__, stage._two_color_presenter)
            finally:
                stage.runner.verify_alert = original
        self.assertEqual(self.watch.STATE.read_bytes(), self.state_before)


class IranNoStrikeProjectionTests(unittest.TestCase):
    def test_no_rush_titles_are_not_red_in_final_two_color(self):
        for title in (
            "트럼프 대통령, 이란 공습 서두르지 않겠다고 단언",
            "중간선거 후 공습 부인한 트럼프…호르무즈 재개방 조건 내건 이란(종합)",
        ):
            with self.subTest(title=title):
                row = {'title': title, 'title_original': title, 'title_ko': title,
                       'source': '신아일보', 'tags': ['확전'], 'score': 98}
                self.assertEqual(presentation.direction(stage, row), 'green')

    def test_oil_price_fall_on_peace_hopes_is_reference_not_attack(self):
        title = "미국-이란 종전 외교적 해결 기대감에 유가 큰 폭 하락"
        row = {'title': title, 'title_original': title, 'title_ko': title,
               'source': '에너지플랫폼뉴스', 'tags': ['확전'], 'score': 95}
        self.assertIsNone(presentation.direction(stage, row))

    def test_oil_price_plunge_on_possible_talks_is_reference(self):
        title = "고개 든 미ㆍ이란 협상 재개 가능성⋯국제유가, 7%대 급락 [종합]"
        row = {'title': title, 'title_original': title, 'title_ko': title,
               'source': '이투데이', 'tags': ['종전·협상'], 'score': 90}
        self.assertIsNone(presentation.direction(stage, row))

    def test_actual_separate_attack_remains_red(self):
        title = "트럼프, 이란 공습 서두르지 않겠다 밝혔지만 동시에 미군이 이란 시설 공격을 감행"
        row = {'title': title, 'title_original': title, 'title_ko': title,
               'source': '통신사', 'tags': ['확전'], 'score': 100}
        self.assertEqual(presentation.direction(stage, row), 'red')


class Run813AttackDuringTalksTests(unittest.TestCase):
    def test_saved_publisher_headline_is_attack_not_diplomatic_contact(self):
        # Run 42346222868 sent this body-verified publisher headline in green.
        title = '美, 종전 협상 중 또 이란 공습 …"게슘섬 방공시설 무력화" - 경북도민일보'
        row = {'title_original': title, 'title_ko': title, 'description': title,
               'source': '경북도민일보', 'tags': ['외교 접촉 보도'],
               'body_verified': True, 'classification_color': 'green',
               'non_military_kind': 'diplomatic_contact'}
        self.assertEqual([m.group() for m in stage._military_actions(title.lower())],
                         ['또 이란 공습'])
        self.assertIsNone(stage.non_military_kind(row))
        self.assertEqual(stage.final_color(row), 'red')
        self.assertEqual(presentation.direction(stage, row), 'red')

        # Replay the saved discovery fields as a newly scored item.  The ZIP
        # keeps a body hash, so this validates classification without
        # claiming to have re-fetched the publisher body.
        fresh = {key: value for key, value in row.items()
                 if key not in ('tags', 'classification_color', 'non_military_kind')}
        fresh['published'] = 'Sat, 07 Nov 2026 13:28:15 +0900'
        at = dt.datetime.fromisoformat('2026-11-07T15:17:54+09:00')
        score, tags = stage.score_item(fresh, at)
        self.assertEqual(score, 12)
        self.assertIn('확전', tags)
        self.assertNotIn('외교 접촉 보도', tags)
        fresh['tags'] = tags
        self.assertNotIn('외교 접촉 보도', stage.topic_label(fresh))
        self.assertEqual(presentation.direction(stage, fresh), 'red')

    def test_speculative_or_stopped_strike_is_not_a_completed_action(self):
        for title in ('美, 종전 협상 중 또 이란 공습할까?',
                      '美, 종전 협상 중 또 이란 공습 가능성',
                      '美, 종전 협상 중 또 이란 공습을 중단'):
            with self.subTest(title=title):
                self.assertEqual(stage._military_actions(title.lower()), [])


class Run820AttackAheadOfTalksTests(unittest.TestCase):
    def test_saved_title_only_attack_intensification_is_red(self):
        fixture = json.loads((Path(__file__).parent / 'test_fixtures'
                              / 'war_run820_saved_attack_ahead_talks_42417723619.json')
                             .read_text(encoding='utf-8'))
        row = fixture['article']
        self.assertEqual(fixture['provenance']['zip_sha256'],
                         '03d69f975137e14783eba96f4950c15288198930ae449445d81b6a95037d8638')
        self.assertEqual(row['id'], 'e5856589c729cd7a2a56')
        self.assertEqual(row['title_original'],
                         '러시아, 종전 협상 앞두고 우크라이나 공격 강화 - VOA 한국어 홈페이지')
        self.assertFalse(row['body_verified'])
        self.assertEqual(row['publication_basis'], 'discovery_feed')
        self.assertEqual(row['classification_color'], 'green')  # Actual run #820 send.

        fresh = {key: copy.deepcopy(value) for key, value in row.items()
                 if key not in ('tags', 'score', 'classification_color',
                                'semantic_classification_color', 'rendered')}
        at = dt.datetime.fromisoformat('2026-11-08T06:52:17+09:00')
        self.assertEqual(stage.non_military_kind(fresh), 'military_report')
        score, tags = stage.score_item(fresh, at)
        self.assertGreater(score, 0)
        self.assertEqual(tags, ['공격 강화 보도'])
        fresh['tags'] = tags
        self.assertEqual(stage._primary_topic(fresh), '우크라이나·러시아 · 공격 강화 보도')
        self.assertEqual(presentation.direction(stage, fresh), 'red')
        semantic = stage.build_alert([fresh], [], at)
        receipt = evidence.alert_receipt([fresh], [], at, semantic, {})
        text, projected = presentation.project(stage, semantic, receipt, {}, {})
        self.assertIn('🔴 [신규] <b>1. 우크라이나·러시아 · 공격 강화 보도</b>', text)
        self.assertIn('제목 기준·본문 미확인', text)
        self.assertEqual(projected['articles'][0]['classification_color'], 'red')

    def test_planned_or_speculative_attack_intensification_is_not_reported_action(self):
        titles = (
            '러시아, 종전 협상 앞두고 우크라이나 공격 강화 계획',
            '러시아, 종전 협상 앞두고 우크라이나 공격 강화를 검토',
            '러시아, 종전 협상 앞두고 우크라이나 공격 강화 가능성',
            '러시아, 종전 협상 앞두고 우크라이나 공격 강화 우려',
            '러시아, 종전 협상 앞두고 우크라이나 공격 강화 안 한다',
            '러시아, 종전 협상 앞두고 우크라이나 공격 강화 중단',
        )
        for title in titles:
            with self.subTest(title=title):
                self.assertFalse(stage._reported_attack_escalation(title.lower()))


class Run820StrikeLinkDenialTests(unittest.TestCase):
    def test_saved_title_only_denial_is_unconfirmed_reference(self):
        fixture = json.loads((Path(__file__).parent / 'test_fixtures'
                              / 'war_run820_saved_strike_denial_42417723619.json')
                             .read_text(encoding='utf-8'))
        row = fixture['article']
        self.assertEqual(fixture['provenance']['zip_sha256'],
                         '03d69f975137e14783eba96f4950c15288198930ae449445d81b6a95037d8638')
        self.assertEqual(row['id'], 'd35454940e8c149aa92b')
        self.assertIn('EXPLOSIONS HEARD ON QESHM ISLAND NOT RELATED TO MISSILE STRIKES',
                      row['title_original'])
        self.assertFalse(row['body_verified'])
        self.assertEqual(row['tags'], ['확전'])  # Actual run #820 classification.
        self.assertEqual(row['classification_color'], 'red')

        fresh = {key: copy.deepcopy(value) for key, value in row.items()
                 if key not in ('tags', 'score', 'classification_color',
                                'semantic_classification_color', 'rendered', 'signals_ko')}
        at = dt.datetime.fromisoformat('2026-11-08T06:52:17+09:00')
        self.assertEqual(stage.non_military_kind(fresh), 'unconfirmed_explosion')
        score, tags = stage.score_item(fresh, at)
        self.assertGreater(score, 0)
        self.assertEqual(tags, ['폭발음 보도·공격 원인 미확인'])
        fresh['tags'] = tags
        self.assertEqual(stage.final_color(fresh), 'yellow')
        self.assertIsNone(presentation.direction(stage, fresh))
        semantic = stage.build_alert([fresh], [], at)
        receipt = evidence.alert_receipt([fresh], [], at, semantic, {})
        text, projected = presentation.project(stage, semantic, receipt, {}, {})
        self.assertIn('<b>참고 1. 폭발음 원인 미확인</b>', text)
        self.assertIn('RSS 입력 기준·본문 미확인', text)
        self.assertNotIn('🔴 [신규] <b>1.', text)
        self.assertIsNone(projected['articles'][0]['classification_color'])

    def test_separate_actual_strike_does_not_inherit_denial(self):
        title = ('EXPLOSIONS HEARD ON QESHM ISLAND NOT RELATED TO MISSILE STRIKES; '
                 'AIRSTRIKE HITS NEARBY PORT')
        row = {'title_original': title, 'body_verified': False}
        self.assertFalse(stage._title_only_unconfirmed_explosion(row))
        self.assertEqual(presentation.direction(stage, row), 'red')


class Run824PendingIranDecisionTests(unittest.TestCase):
    def test_saved_undecided_war_option_is_reference(self):
        fixture = json.loads((Path(__file__).parent / 'test_fixtures'
                              / 'war_run824_saved_pending_iran_decision_42451024874.json')
                             .read_text(encoding='utf-8'))
        row = fixture['article']
        self.assertEqual(fixture['provenance']['zip_sha256'],
                         'd3505d792646ea6f3f8c8050c0ad6bed69669185bd7f80b09a2bf4cc0c64d742')
        self.assertEqual(row['id'], '2b922e16bf78d4337329')
        self.assertIn('밴스는 협상, 헤그세스는 공습…트럼프 이란전 결단 임박',
                      row['title_original'])
        self.assertFalse(row['body_verified'])
        self.assertEqual(row['tags'], ['확전'])  # Actual run #824 classification.
        self.assertEqual(row['classification_color'], 'red')

        fresh = {key: copy.deepcopy(value) for key, value in row.items()
                 if key not in ('tags', 'score', 'classification_color',
                                'semantic_classification_color', 'rendered', 'signals_ko')}
        at = dt.datetime.fromisoformat('2026-11-08T14:32:25+09:00')
        self.assertEqual(stage.non_military_kind(fresh), 'military_analysis')
        score, tags = stage.score_item(fresh, at)
        self.assertGreater(score, 0)
        self.assertEqual(tags, ['이란전 결단 전망'])
        fresh['tags'] = tags
        self.assertEqual(stage.final_color(fresh), 'yellow')
        self.assertIsNone(presentation.direction(stage, fresh))
        semantic = stage.build_alert([fresh], [], at)
        receipt = evidence.alert_receipt([fresh], [], at, semantic, {})
        text, projected = presentation.project(stage, semantic, receipt, {}, {})
        self.assertIn('이란전 결단 전망', text)
        self.assertIn('본문 미확인', text)
        self.assertNotIn('🔴 [신규] <b>1.', text)
        self.assertIsNone(projected['articles'][0]['classification_color'])

    def test_separate_current_strike_keeps_risk(self):
        title = ('밴스는 협상, 헤그세스는 공습…트럼프 이란전 결단 임박; '
                 '미군이 이란을 공습했다')
        row = {'title_original': title, 'body_verified': False}
        self.assertFalse(stage._pending_iran_war_decision_outlook(title.lower()))
        self.assertEqual(presentation.direction(stage, row), 'red')
        verified = {'title_original': '밴스는 협상, 헤그세스는 공습…트럼프 이란전 결단 임박',
                    'body_verified': True}
        self.assertNotEqual(stage.non_military_kind(verified), 'military_analysis')


class Run826ElectionIranOptionsTests(unittest.TestCase):
    def test_four_saved_staff_debate_headlines_are_neutral_outlook(self):
        fixture = json.loads((Path(__file__).parent / 'test_fixtures'
                              / 'war_run826_saved_iran_options_42451661639.json')
                             .read_text(encoding='utf-8'))
        self.assertEqual(fixture['provenance']['zip_sha256'],
                         '7811ed6d0953cc7d7a53f10d7ad52572a3f02d3b968895933193ac83f0306124')
        rows = fixture['articles']
        self.assertEqual(len(rows), 4)
        self.assertEqual([row['classification_color'] for row in rows], ['red'] * 4)
        at = dt.datetime.fromisoformat('2026-11-08T14:42:08+09:00')
        fresh_rows = []
        for row in rows:
            with self.subTest(article_id=row['id']):
                fresh = {key: copy.deepcopy(value) for key, value in row.items()
                         if key not in ('tags', 'score', 'classification_color',
                                        'semantic_classification_color', 'rendered', 'signals_ko')}
                self.assertTrue(stage._election_iran_war_staff_options(
                    stage._headline(fresh)))
                self.assertEqual(stage.non_military_kind(fresh), 'military_analysis')
                score, tags = stage.score_item(fresh, at)
                self.assertGreater(score, 0)
                self.assertEqual(tags, ['이란전 선택·참모진 이견'])
                fresh['tags'] = tags
                self.assertEqual(stage.final_color(fresh), 'yellow')
                self.assertIsNone(presentation.direction(stage, fresh))
                fresh_rows.append(fresh)
        semantic = stage.build_alert(fresh_rows, [], at)
        receipt = evidence.alert_receipt(fresh_rows, [], at, semantic, {})
        text, projected = presentation.project(stage, semantic, receipt, {}, {})
        self.assertEqual(text.count('이란전 선택·참모진 이견</b>'), 4)
        self.assertNotIn('🔴 [신규] <b>', text)
        self.assertEqual([row['classification_color'] for row in projected['articles']],
                         [None] * 4)

    def test_separate_reported_action_is_not_staff_options(self):
        base = '중간선거 후 이란전 고심…트럼프 참모들 협상 vs 공습 대립'
        for title in (base + '; 미군이 이란을 공습했다',
                      base + '; 미군이 이란 공습을 재개',
                      base + '; 미국이 새 제재를 부과'):
            with self.subTest(title=title):
                self.assertFalse(stage._election_iran_war_staff_options(title.lower()))


class Run817EnergyMissileUseTests(unittest.TestCase):
    def test_saved_publisher_attack_claim_is_red_at_both_stages(self):
        fixture = json.loads((Path(__file__).parent / 'test_fixtures'
                              / 'war_run817_saved_energy_missile_use_42399686297.json')
                             .read_text(encoding='utf-8'))
        row = fixture['article']
        self.assertEqual(
            fixture['provenance']['zip_sha256'],
            'f901f6917dbaeb8611c6dea57b72159d2c8a4ce3e20727602b72d324335df450')
        self.assertEqual(row['id'], 'b29c5de3f75215ee4a00')
        self.assertEqual(
            row['title_original'],
            '젤렌스키 "러, 우크라 에너지 시설 타격에 북한제 KN-23 미사일 사용"')
        self.assertIn('러시아가 자국 에너지 시설을 공격하는 데 북한제 탄도미사일을 사용했다고 주장했다',
                      row['description'])
        self.assertEqual(row['classification_color'], 'green')  # Actual run #817 send.
        self.assertEqual(row['semantic_classification_color'], 'yellow')
        self.assertTrue(row['body_verified'])
        self.assertEqual(stage.final_color(row), 'red')
        self.assertEqual(presentation.direction(stage, row), 'red')

        # Rescore the saved publisher input without carrying forward its old
        # presentation decision. The original article body is not in the ZIP.
        fresh = {key: copy.deepcopy(value) for key, value in row.items()
                 if key not in ('tags', 'score', 'classification_color',
                                'semantic_classification_color', 'rendered')}
        at = dt.datetime.fromisoformat('2026-11-08T03:08:35+09:00')
        score, tags = stage.score_item(fresh, at)
        self.assertGreater(score, 0)
        self.assertIn('에너지 시설 공격 보도', tags)
        fresh['tags'] = tags
        self.assertEqual(stage.final_color(fresh), 'red')
        self.assertEqual(presentation.direction(stage, fresh), 'red')

    def test_plan_question_and_denial_do_not_become_completed_strikes(self):
        prefix = '젤렌스키 "러, 우크라 에너지 시설 타격에 북한제 KN-23 미사일 사용'
        for title in (prefix + ' 검토"', prefix + ' 가능성"',
                      prefix + '할 계획"', prefix + '하지 않았다고 부인"',
                      prefix + '했다는 주장 부인"', prefix + '?"'):
            with self.subTest(title=title):
                self.assertFalse(stage._reported_energy_facility_missile_use(title.lower()))


class Run801SavedInputTests(unittest.TestCase):
    def test_reported_deal_review_and_election_commentary_keep_their_stages(self):
        fixture = json.loads((Path(__file__).parent / 'test_fixtures'
                              / 'war_run801_saved_semantic_snapshot_42088307800.json')
                             .read_text(encoding='utf-8'))
        snapshot = fixture['semantic_snapshot']
        proof = fixture['semantic_proof']
        alert_bytes = base64.b64decode(snapshot['alert_utf8_base64'])
        evidence_bytes = base64.b64decode(snapshot['evidence_utf8_base64'])
        self.assertEqual(hashlib.sha256(alert_bytes).hexdigest(), proof['alert_sha256'])
        self.assertEqual(hashlib.sha256(evidence_bytes).hexdigest(), proof['evidence_sha256'])
        self.assertEqual(fixture['observed_delivered_colors'], ['red'] * 4)

        text, receipt = presentation.project(
            stage, alert_bytes.decode('utf-8'), json.loads(evidence_bytes),
            proof, snapshot)
        shown = [row for row in receipt['articles'] if row.get('rendered')]
        self.assertEqual([row['id'] for row in shown], fixture['selected_ids'])
        self.assertEqual([row['classification_color'] for row in shown],
                         ['red', 'green', None, 'red'])
        self.assertEqual(shown[2]['display_section'], 'context_reference')
        self.assertIn('🟢 <b>대화·협상·완화</b>', text)
        self.assertIn('<b>배경·시장 참고</b>', text)
        self.assertNotEqual(receipt['alert_sha256'],
                            fixture['observed_delivered_alert_sha256'])


class Run803RejectedInputTests(unittest.TestCase):
    def test_pending_decision_and_mediator_review_do_not_bypass_quality_gate(self):
        fixture = json.loads((Path(__file__).parent / 'test_fixtures'
                              / 'war_run803_rejected_alert_42131474397.json')
                             .read_text(encoding='utf-8'))
        original = fixture['rejected_alert']
        self.assertEqual(hashlib.sha256(original.encode('utf-8')).hexdigest(),
                         fixture['rejected_alert_sha256'])
        rows = fixture['selected_rows']
        self.assertEqual([row['id'] for row in rows],
                         ['ffb70a81e815e9affa6f', '9e15753f20f3aea7d279',
                          'ff7d919eafae79fdcc0b', 'cc50dc1373fb830ae9d8'])
        self.assertEqual([stage.final_color(row) for row in rows],
                         fixture['expected_stage_colors'])
        self.assertEqual([presentation.direction(stage, row) for row in rows],
                         fixture['expected_two_color'])

        with tempfile.TemporaryDirectory() as folder:
            alert = Path(folder) / 'alert.txt'
            with patch.object(quality_guard.watch, 'ALERT', alert), \
                    patch.object(quality_guard, '_orig_verify_alert', return_value=None):
                alert.write_text(original, encoding='utf-8')
                with self.assertRaisesRegex(RuntimeError, 'WAR_OCT04_QUALITY_GATE'):
                    quality_guard.verify_alert(test_mode=False)
                corrected = original.replace(
                    '🔴 [속보] <b>1.', '🟡 [속보] <b>1.', 1).replace(
                    '🔴 [신규] <b>3.', '🟢 [신규] <b>3.', 1)
                alert.write_text(corrected, encoding='utf-8')
                quality_guard.verify_alert(test_mode=False)


class Run831SavedSemanticTests(unittest.TestCase):
    def test_actual_sent_policy_options_replay_and_fresh_title_scoring(self):
        fixture = json.loads((Path(__file__).parent / 'test_fixtures'
                              / 'war_run831_saved_semantic_snapshot_42459155624.json')
                             .read_text(encoding='utf-8'))
        self.assertEqual(fixture['provenance']['zip_sha256'],
                         'fa122ccb858e71c34050e3bc2a33184a37f24427add3a90c5f2f4ac87dc7d3fc')
        self.assertEqual(fixture['provenance']['telegram_message_id'], 424)
        self.assertEqual(fixture['observed_delivered_colors'], ['red', 'green', 'red', 'red'])
        snapshot, proof = fixture['semantic_snapshot'], fixture['semantic_proof']
        alert_bytes = base64.b64decode(snapshot['alert_utf8_base64'])
        evidence_bytes = base64.b64decode(snapshot['evidence_utf8_base64'])
        self.assertEqual(hashlib.sha256(alert_bytes).hexdigest(), proof['alert_sha256'])
        self.assertEqual(hashlib.sha256(evidence_bytes).hexdigest(), proof['evidence_sha256'])

        text, receipt = presentation.project(stage, alert_bytes.decode('utf-8'),
                                             json.loads(evidence_bytes), proof, snapshot)
        shown = [row for row in receipt['articles'] if row.get('rendered')]
        self.assertEqual([row['id'] for row in shown], fixture['selected_ids'])
        self.assertEqual([row['classification_color'] for row in shown],
                         [None, 'green', None, 'red'])
        self.assertEqual([shown[i]['display_section'] for i in (0, 2)],
                         ['context_reference', 'context_reference'])
        self.assertIn('이란전 대응 방안·정책 이견', text)
        self.assertNotEqual(receipt['alert_sha256'],
                            fixture['provenance']['observed_delivered_alert_sha256'])

        queried = dt.datetime.fromisoformat('2026-11-08T16:33:00+09:00')
        for index in (0, 2):
            prior = fixture['selected_rows'][index]
            with self.subTest(id=prior['id']):
                fresh = {key: copy.deepcopy(value) for key, value in prior.items()
                         if key not in ('tags', 'score', 'classification_color',
                                        'semantic_classification_color', 'rendered', 'signals_ko')}
                self.assertFalse(fresh['body_verified'])
                score, tags = stage.score_item(fresh, queried)
                self.assertGreater(score, 0)
                self.assertEqual(stage.non_military_kind(fresh), 'military_analysis')
                self.assertEqual(tags, ['이란전 대응 방안·정책 이견'])
                fresh['tags'] = tags
                self.assertEqual(stage.final_color(fresh), 'yellow')
                self.assertIsNone(presentation.direction(stage, fresh))

        strike = fixture['selected_rows'][3]
        self.assertFalse(stage._iran_war_policy_options_headline(stage._headline(strike)))
        self.assertEqual(presentation.direction(stage, strike), 'red')

    def test_separate_executed_strike_is_not_policy_context(self):
        title = ('이란전 놓고 세 갈래 대립…종전협상, 군사작전 재개, 경제압박 강화; '
                 '한편 미군이 이란 공습을 실시했다')
        self.assertFalse(stage._iran_war_policy_options_headline(title))
        self.assertEqual(presentation.direction(stage, {'title_original': title}), 'red')


class Run829SavedSemanticTests(unittest.TestCase):
    def test_actual_sent_mislabels_replay_and_fresh_title_scoring(self):
        fixture = json.loads((Path(__file__).parent / 'test_fixtures'
                              / 'war_run829_saved_semantic_snapshot_42457812096.json')
                             .read_text(encoding='utf-8'))
        self.assertEqual(fixture['provenance']['zip_sha256'],
                         '6ef4753ed9fe8785693a5ede108982df8e91b650be3cb5db351be44bef5ab361')
        self.assertEqual(fixture['provenance']['telegram_message_id'], 423)
        self.assertEqual(fixture['observed_delivered_colors'],
                         ['red', 'green', 'green', 'green'])
        snapshot, proof = fixture['semantic_snapshot'], fixture['semantic_proof']
        alert_bytes = base64.b64decode(snapshot['alert_utf8_base64'])
        evidence_bytes = base64.b64decode(snapshot['evidence_utf8_base64'])
        self.assertEqual(hashlib.sha256(alert_bytes).hexdigest(), proof['alert_sha256'])
        self.assertEqual(hashlib.sha256(evidence_bytes).hexdigest(), proof['evidence_sha256'])

        text, receipt = presentation.project(stage, alert_bytes.decode('utf-8'),
                                             json.loads(evidence_bytes), proof, snapshot)
        shown = [row for row in receipt['articles'] if row.get('rendered')]
        self.assertEqual([row['id'] for row in shown], fixture['selected_ids'])
        self.assertEqual([row['classification_color'] for row in shown],
                         [None, 'green', 'red', 'red'])
        self.assertEqual(shown[0]['display_section'], 'market_reference')
        self.assertIn('<b>참고 1. 폭발음 원인 미확인</b>', text)
        self.assertNotEqual(receipt['alert_sha256'],
                            fixture['provenance']['observed_delivered_alert_sha256'])

        queried = dt.datetime.fromisoformat('2026-11-08T16:14:00+09:00')
        expected = [('unconfirmed_explosion', '폭발음 보도·공격 원인 미확인', None),
                    ('diplomatic_appeal', '종전협상 요구', 'green'),
                    ('diplomatic_position', '협상 제동 보도', 'red'),
                    ('diplomatic_position', '협상 양보 요구·압박', 'red')]
        for prior, (kind, tag, color) in zip(fixture['selected_rows'], expected):
            with self.subTest(id=prior['id']):
                fresh = {key: copy.deepcopy(value) for key, value in prior.items()
                         if key not in ('tags', 'score', 'classification_color',
                                        'semantic_classification_color', 'rendered', 'signals_ko')}
                self.assertFalse(fresh['body_verified'])
                score, tags = stage.score_item(fresh, queried)
                self.assertGreater(score, 0)
                self.assertEqual(stage.non_military_kind(fresh), kind)
                self.assertEqual(tags, [tag])
                fresh['tags'] = tags
                self.assertEqual(presentation.direction(stage, fresh), color)

    def test_negations_and_separate_strike_keep_their_meaning(self):
        self.assertFalse(stage._negotiation_obstruction_headline('종전 협상에 제동을 걸지 않겠다'))
        self.assertFalse(stage._negotiation_concession_pressure_headline('종전협상서 양보 요구 철회'))
        self.assertFalse(stage._negotiation_obstruction_headline('이란 공습 계획에 제동'))
        strike = {'title_original': '이란 남부에서 폭발음…미사일 공격으로 시설 피격',
                  'body_verified': False}
        self.assertFalse(stage._title_only_unconfirmed_explosion(strike))
        self.assertEqual(presentation.direction(stage, strike), 'red')


class Run834SavedSemanticTests(unittest.TestCase):
    def test_sent_policy_cards_replay_as_context_without_changing_attack_reports(self):
        fixture = json.loads((Path(__file__).parent / 'test_fixtures'
                              / 'war_run834_saved_semantic_snapshot_42489418887.json')
                             .read_text(encoding='utf-8'))
        self.assertEqual(fixture['provenance']['telegram_message_id'], 426)
        self.assertEqual(fixture['observed_delivered_colors'], ['red'] * 4)
        snapshot, proof = fixture['semantic_snapshot'], fixture['semantic_proof']
        alert_bytes = base64.b64decode(snapshot['alert_utf8_base64'])
        evidence_bytes = base64.b64decode(snapshot['evidence_utf8_base64'])
        self.assertEqual(hashlib.sha256(alert_bytes).hexdigest(), proof['alert_sha256'])
        self.assertEqual(hashlib.sha256(evidence_bytes).hexdigest(), proof['evidence_sha256'])

        text, receipt = presentation.project(stage, alert_bytes.decode('utf-8'),
                                             json.loads(evidence_bytes), proof, snapshot)
        shown = [row for row in receipt['articles'] if row.get('rendered')]
        self.assertEqual([row['id'] for row in shown], fixture['selected_ids'])
        self.assertEqual([row['classification_color'] for row in shown],
                         ['red', None, 'red', 'red'])
        self.assertEqual(shown[1]['display_section'], 'context_reference')
        self.assertFalse(shown[1]['body_verified'])
        self.assertIn('이란전 대응 방안·정책 이견', text)
        self.assertIn('부분 확인 전쟁 상황 알림 · 원천 216/227', text)
        self.assertNotEqual(receipt['alert_sha256'],
                            fixture['provenance']['observed_delivered_alert_sha256'])

        card = shown[1]
        self.assertEqual(stage.non_military_kind(card), 'military_analysis')
        self.assertIsNone(presentation.direction(stage, card))
        fresh = {key: copy.deepcopy(value) for key, value in card.items()
                 if key not in ('tags', 'score', 'classification_color',
                                'semantic_classification_color', 'rendered',
                                'signals_ko', 'display_section')}
        score, tags = stage.score_item(
            fresh, dt.datetime.fromisoformat('2026-11-08T23:23:36+09:00'))
        self.assertGreater(score, 0)
        self.assertEqual(tags, ['이란전 대응 방안·정책 이견'])
        self.assertEqual(stage.topic_label(fresh),
                         '전쟁·외교 · 이란전 대응 방안·정책 이견')
        self.assertEqual(stage.final_color(fresh), 'yellow')
        separate = card['title_original'] + '; 한편 미군이 이란을 공습했다'
        self.assertFalse(stage._iran_war_policy_options_headline(separate.lower()))
        self.assertEqual(presentation.direction(stage, {'title_original': separate}), 'red')
        blockade = card['title_original'] + '; 한편 미군이 이란 해상 봉쇄를 개시했다'
        self.assertFalse(stage._iran_war_policy_options_headline(blockade.lower()))
        self.assertEqual(presentation.direction(stage, {'title_original': blockade}), 'red')


class Run837SavedHeadlineTests(unittest.TestCase):
    def test_historical_attack_in_gaza_plan_is_not_new_escalation(self):
        # Run 42512428632 carried an Oct. 7 history sentence in its RSS
        # description. The dated sentence must not override the new headline.
        row = {
            'title_original': 'Scoop: Trump asked Netanyahu to move on Gaza peace plan in post-election call',
            'title_ko': '트럼프가 네타냐후에게 가자 평화 계획 추진을 요청',
            'description': ('The ceasefire released hostages taken during the Oct. 7, 2023 attacks. '
                            'Reconstruction would only begin after verified disarmament.'),
            'source': 'Axios',
            'published': 'Sun, 08 Nov 2026 17:59:28 +0000',
            'body_verified': False,
        }
        observed = dt.datetime.fromisoformat('2026-11-09T03:57:50+09:00')
        score, tags = stage.score_item(copy.deepcopy(row), observed)
        self.assertGreater(score, 0)
        self.assertIn('종전·협상', tags)
        self.assertNotIn('확전', tags)
        self.assertEqual(stage.topic_label(dict(row, tags=tags)), '이스라엘·가자')

        separate_attack = copy.deepcopy(row)
        separate_attack['description'] += ' Israeli forces attacked Gaza overnight.'
        self.assertIn('확전', stage.score_item(separate_attack, observed)[1])

    def test_conditional_no_renewed_war_is_green_unless_attack_is_separate(self):
        title = ("TRUMP ON IRAN: 'HIGHLY UNLIKELY' WILL ORDER US BACK TO WAR "
                 'WITH IRAN IF TALKS CONTINUE TO PROGRESS')
        self.assertEqual(presentation.direction(stage, {
            'title_original': title, 'body_verified': False}), 'green')
        for attack in ('; separately US forces struck Iran',
                       '; 한편 미군이 이란을 공습했다'):
            with self.subTest(attack=attack):
                self.assertEqual(presentation.direction(stage, {
                    'title_original': title + attack, 'body_verified': False}), 'red')


class Run839SavedSemanticTests(unittest.TestCase):
    def test_sent_unknown_blast_and_low_reattack_titles_replay_without_false_red(self):
        fixture = json.loads((Path(__file__).parent / 'test_fixtures'
                              / 'war_run839_saved_semantic_snapshot_42528186503.json')
                             .read_text(encoding='utf-8'))
        self.assertEqual(fixture['provenance']['telegram_message_id'], 427)
        self.assertEqual(fixture['observed_delivered_colors'], ['red'] * 4)
        snapshot, proof = fixture['semantic_snapshot'], fixture['semantic_proof']
        alert_bytes = base64.b64decode(snapshot['alert_utf8_base64'])
        evidence_bytes = base64.b64decode(snapshot['evidence_utf8_base64'])
        self.assertEqual(hashlib.sha256(alert_bytes).hexdigest(), proof['alert_sha256'])
        self.assertEqual(hashlib.sha256(evidence_bytes).hexdigest(), proof['evidence_sha256'])

        text, receipt = presentation.project(stage, alert_bytes.decode('utf-8'),
                                             json.loads(evidence_bytes), proof, snapshot)
        shown = [row for row in receipt['articles'] if row.get('rendered')]
        self.assertEqual([row['id'] for row in shown], fixture['selected_ids'])
        self.assertEqual([row['classification_color'] for row in shown],
                         [None, None, 'red', 'green'])
        self.assertEqual([row['display_section'] for row in shown[:2]],
                         ['context_reference', 'context_reference'])
        self.assertIn('폭발 원인 미확정', text)
        self.assertIn('낮은 재공격 가능성 발언·폭발음 원인 미확인', text)
        self.assertIn('원인 미확정 폭발음·조건부 발언은 실제 공격·완화 행동을 입증하지 않음', text)
        self.assertIn('부분 확인 전쟁 상황 알림 · 원천 216/227', text)
        self.assertNotIn('🟡', text)
        self.assertNotEqual(receipt['alert_sha256'],
                            fixture['provenance']['observed_delivered_alert_sha256'])

        for idx in (0, 1, 3):
            separate = copy.deepcopy(shown[idx])
            separate['title_original'] += '; 한편 미군이 이란을 공습했다'
            self.assertEqual(presentation.direction(stage, separate), 'red')


class Run842SavedSemanticTests(unittest.TestCase):
    def test_conditional_no_further_strikes_and_impeachment_replay(self):
        fixture = json.loads((Path(__file__).parent / 'test_fixtures'
                              / 'war_run842_saved_semantic_snapshot_42531763532.json')
                             .read_text(encoding='utf-8'))
        self.assertEqual(fixture['provenance']['telegram_message_id'], 429)
        self.assertEqual(fixture['observed_delivered_colors'], ['red'] * 3)
        snapshot, proof = fixture['semantic_snapshot'], fixture['semantic_proof']
        alert_bytes = base64.b64decode(snapshot['alert_utf8_base64'])
        evidence_bytes = base64.b64decode(snapshot['evidence_utf8_base64'])
        self.assertEqual(hashlib.sha256(alert_bytes).hexdigest(), proof['alert_sha256'])
        self.assertEqual(hashlib.sha256(evidence_bytes).hexdigest(), proof['evidence_sha256'])

        semantic_rows = json.loads(evidence_bytes)['articles']
        no_strike = next(row for row in semantic_rows
                         if '추가 공습 없을 것' in row['title_original'])
        self.assertTrue(stage._iran_attack_restraint_statement(no_strike))
        self.assertEqual(stage.non_military_kind(no_strike), 'military_position')
        self.assertEqual(stage.final_color(no_strike), 'yellow')
        text, receipt = presentation.project(stage, alert_bytes.decode('utf-8'),
                                             json.loads(evidence_bytes), proof, snapshot)
        shown = [row for row in receipt['articles'] if row.get('rendered')]
        self.assertEqual([row['id'] for row in shown], fixture['selected_ids'])
        self.assertEqual([row['classification_color'] for row in shown],
                         ['red', 'green', None])
        self.assertEqual(shown[2]['display_section'], 'context_reference')
        self.assertIn('이란과 강력한 합의 이뤄지면 추가 공습 없을 것',
                      html.unescape(text))
        self.assertIn('미국 전쟁장관 탄핵 논의', text)
        self.assertIn('부분 확인 전쟁 상황 알림 · 원천 216/227', text)
        self.assertNotEqual(receipt['alert_sha256'],
                            fixture['provenance']['observed_delivered_alert_sha256'])

        for row in (shown[1], shown[2]):
            separate = copy.deepcopy(row)
            separate['title_original'] += '; 한편 미군이 이란을 공습했다'
            self.assertEqual(presentation.direction(stage, separate), 'red')


class Run848PoliticalCeasefireQuestionTests(unittest.TestCase):
    def test_saved_question_is_context_without_erasing_current_actions(self):
        fixture = json.loads((Path(__file__).parent / 'test_fixtures'
                              / 'war_run848_political_ceasefire_question_42595658342.json')
                             .read_text(encoding='utf-8'))
        provenance, saved = fixture['provenance'], fixture['article']
        self.assertEqual(provenance['zip_sha256'],
                         'e534ce7fbaa97a59371ba7c768106a386e7e95f30d06225a442b8b2a360c2ab4')
        self.assertEqual(provenance['telegram_message_id'], 433)
        self.assertEqual(provenance['observed_delivered_color'], 'red')
        self.assertEqual(saved['semantic_classification_color'], 'green')
        self.assertEqual(saved['article_text_sha256'],
                         provenance['operating_article_text_sha256'])
        self.assertTrue(provenance['later_refetch_body_hash_matched'])
        self.assertFalse(provenance['operating_http_bytes_archived'])

        snapshot, proof = fixture['semantic_snapshot'], fixture['semantic_proof']
        alert_bytes = base64.b64decode(snapshot['alert_utf8_base64'])
        evidence_bytes = base64.b64decode(snapshot['evidence_utf8_base64'])
        self.assertEqual(hashlib.sha256(alert_bytes).hexdigest(), proof['alert_sha256'])
        self.assertEqual(hashlib.sha256(evidence_bytes).hexdigest(), proof['evidence_sha256'])
        text, projected = presentation.project(stage, alert_bytes.decode('utf-8'),
                                               json.loads(evidence_bytes), proof, snapshot)
        target = next(row for row in projected['articles']
                      if row['id'] == saved['id'])
        self.assertIsNone(target['classification_color'])
        self.assertEqual(target['display_section'], 'context_reference')
        self.assertIn('민주당 의회가 종전 앞당길까', text)
        self.assertIn('<b>참고 1.', text)
        self.assertNotIn('🔴 [신규]', text)
        self.assertEqual([row['classification_color'] for row in projected['articles']
                          if row.get('rendered')], [None, 'green', None, 'green'])

        for title, expected in (
            ('美 민주당 의회가 종전 앞당길까…미군이 이란을 공습했다', 'red'),
            ('미 민주당 의회가 종전 앞당길까…미·이란 회담 재개 합의', 'green'),
        ):
            with self.subTest(title=title):
                row = {'title_original': title, 'body_verified': False}
                self.assertEqual(presentation.direction(stage, row), expected)


class Run850AirstrikeRestraintSignalTests(unittest.TestCase):
    def test_saved_title_only_restraint_signal_is_not_escalation(self):
        fixture = json.loads((Path(__file__).parent / 'test_fixtures'
                              / 'war_run850_airstrike_restraint_signal_42603233123.json')
                             .read_text(encoding='utf-8'))
        provenance, saved = fixture['provenance'], fixture['article']
        self.assertEqual(provenance['zip_sha256'],
                         '57b1e01e1e481c35be280d8f0b51ed4e87bf5dd0e6aa879608cef4f541f3e205')
        self.assertEqual(provenance['telegram_message_id'], 434)
        self.assertEqual(provenance['observed_delivered_color'], 'red')
        self.assertFalse(saved['body_verified'])
        self.assertEqual(saved['publication_basis'], 'discovery_feed')
        self.assertEqual(saved['article_text_sha256'], hashlib.sha256(b'').hexdigest())

        snapshot, proof = fixture['semantic_snapshot'], fixture['semantic_proof']
        alert_bytes = base64.b64decode(snapshot['alert_utf8_base64'])
        evidence_bytes = base64.b64decode(snapshot['evidence_utf8_base64'])
        self.assertEqual(hashlib.sha256(alert_bytes).hexdigest(), proof['alert_sha256'])
        self.assertEqual(hashlib.sha256(evidence_bytes).hexdigest(), proof['evidence_sha256'])
        original = json.loads(evidence_bytes)
        original_row = next(row for row in original['articles'] if row['id'] == saved['id'])
        self.assertEqual(original_row['classification_color'], 'red')
        self.assertTrue(stage._iran_attack_restraint_statement(original_row))
        self.assertEqual(stage.non_military_kind(original_row), 'military_position')
        self.assertEqual(stage.final_color(original_row), 'yellow')
        now = dt.datetime.fromisoformat(original['queried_at_kst'])
        score, tags = stage.score_item(original_row, now)
        self.assertGreater(score, 0)
        self.assertNotIn('확전', tags)
        self.assertIn('군사 개입·철수 입장', tags)

        text, projected = presentation.project(stage, alert_bytes.decode('utf-8'),
                                               original, proof, snapshot)
        target = next(row for row in projected['articles'] if row['id'] == saved['id'])
        self.assertEqual(target['classification_color'], 'green')
        self.assertEqual(target['semantic_classification_color'], 'red')
        self.assertEqual(target['display_section'], 'core')
        self.assertIn('공습을 제한할 것이라는 신호', text)
        self.assertIn('제목 기준·본문 미확인', text)
        self.assertNotEqual(projected['alert_sha256'],
                            provenance['observed_delivered_alert_sha256'])

        separate = copy.deepcopy(original_row)
        separate['title_original'] += '; 한편 미군이 이란을 공습했다'
        self.assertFalse(stage._iran_attack_restraint_statement(separate))
        self.assertEqual(presentation.direction(stage, separate), 'red')
        denial = copy.deepcopy(original_row)
        denial['title_original'] += '는 보도는 허위라고 부인했다'
        self.assertFalse(stage._iran_attack_restraint_statement(denial))


class Run854NuclearTalksSignalTests(unittest.TestCase):
    def test_saved_sent_false_red_replays_as_reported_diplomacy(self):
        fixture = json.loads((Path(__file__).parent / 'test_fixtures'
                              / 'war_run854_nuclear_talks_42690647940.json')
                             .read_text(encoding='utf-8'))
        provenance, saved = fixture['provenance'], fixture['article']
        self.assertEqual(provenance['telegram_message_id'], 436)
        self.assertEqual(provenance['observed_delivered_color'], 'red')
        self.assertFalse(provenance['source_coverage_complete'])
        self.assertFalse(saved['body_verified'])
        self.assertEqual(saved['publication_basis'], 'discovery_feed')

        snapshot, proof = fixture['semantic_snapshot'], fixture['semantic_proof']
        alert_bytes = base64.b64decode(snapshot['alert_utf8_base64'])
        evidence_bytes = base64.b64decode(snapshot['evidence_utf8_base64'])
        self.assertEqual(hashlib.sha256(alert_bytes).hexdigest(), proof['alert_sha256'])
        self.assertEqual(hashlib.sha256(evidence_bytes).hexdigest(), proof['evidence_sha256'])
        original = json.loads(evidence_bytes)
        original_row = next(row for row in original['articles'] if row['id'] == saved['id'])
        self.assertEqual(original_row['classification_color'], '')
        self.assertEqual(stage.non_military_kind(original_row), 'diplomatic_contact')
        self.assertEqual(stage.final_color(original_row), 'yellow')
        self.assertEqual(stage.topic_label(original_row), '미국·이란 · 핵 회담 재개 보도')
        self.assertEqual(presentation.direction(stage, original_row), 'green')

        text, projected = presentation.project(stage, alert_bytes.decode('utf-8'),
                                               original, proof, snapshot)
        target = next(row for row in projected['articles'] if row['id'] == saved['id'])
        self.assertEqual(target['classification_color'], 'green')
        self.assertEqual(target['semantic_classification_color'], '')
        self.assertIn('🟢 [신규] <b>1. 미국·이란 · 핵 회담 재개 보도</b>', text)
        self.assertNotIn('이란·호르무즈', text.split('🟢 [신규] <b>2.', 1)[0])
        self.assertIn('RSS 입력 기준·본문 미확인', text)
        self.assertNotEqual(projected['alert_sha256'],
                            provenance['observed_delivered_alert_sha256'])

    def test_denial_or_separate_strike_does_not_turn_green(self):
        base = {'title_original': 'US-IRAN NUCLEAR TALKS REPORTEDLY REVIVED',
                'body_verified': False}
        denied = dict(base, title_original='US-IRAN NUCLEAR TALKS NOT REVIVED')
        attacked = dict(base, title_original=base['title_original']
                        + '; US attacked Iran today')
        self.assertNotEqual(stage.non_military_kind(denied), 'diplomatic_contact')
        self.assertNotEqual(presentation.direction(stage, denied), 'green')
        self.assertNotEqual(stage.non_military_kind(attacked), 'diplomatic_contact')
        self.assertEqual(presentation.direction(stage, attacked), 'red')


class Run854AirstrikeRestraintPossibilityTests(unittest.TestCase):
    def test_saved_sent_possibility_replays_as_conditional_easing(self):
        fixture = json.loads((Path(__file__).parent / 'test_fixtures'
                              / 'war_run854_airstrike_restraint_possibility_42690647940.json')
                             .read_text(encoding='utf-8'))
        provenance, saved = fixture['provenance'], fixture['article']
        self.assertEqual(provenance['telegram_message_id'], 436)
        self.assertEqual(provenance['observed_delivered_color'], 'red')
        self.assertFalse(saved['body_verified'])
        self.assertEqual(saved['classification_color'], 'red')
        self.assertEqual(saved['semantic_classification_color'], 'yellow')

        snapshot, proof = fixture['semantic_snapshot'], fixture['semantic_proof']
        alert_bytes = base64.b64decode(snapshot['alert_utf8_base64'])
        evidence_bytes = base64.b64decode(snapshot['evidence_utf8_base64'])
        self.assertEqual(hashlib.sha256(alert_bytes).hexdigest(), proof['alert_sha256'])
        self.assertEqual(hashlib.sha256(evidence_bytes).hexdigest(), proof['evidence_sha256'])
        original = json.loads(evidence_bytes)
        original_row = next(row for row in original['articles'] if row['id'] == saved['id'])
        self.assertEqual(original_row['classification_color'], 'yellow')
        self.assertTrue(stage._iran_attack_restraint_statement(original_row))
        self.assertEqual(stage.non_military_kind(original_row), 'military_position')
        self.assertEqual(stage.topic_label(original_row), '미국·이란 · 공습 제한 가능성 시사')
        self.assertEqual(presentation.direction(stage, original_row), 'green')

        text, projected = presentation.project(stage, alert_bytes.decode('utf-8'),
                                               original, proof, snapshot)
        target = next(row for row in projected['articles'] if row['id'] == saved['id'])
        self.assertEqual(target['classification_color'], 'green')
        self.assertEqual(target['semantic_classification_color'], 'yellow')
        self.assertIn('🟢 [신규] <b>3. 미국·이란 · 공습 제한 가능성 시사</b>', text)
        self.assertIn('공습 제한 가능성 시사', text)
        self.assertIn('제목 기준·본문 미확인', text)
        self.assertNotEqual(projected['alert_sha256'],
                            provenance['observed_delivered_alert_sha256'])

    def test_denial_or_separate_current_strike_blocks_easing(self):
        title = '미국, 이란에 대한 공습 제한 가능성 시사'
        denied = {'title_original': title + '했다는 보도를 부인', 'body_verified': False}
        attacked = {'title_original': title + '; 한편 미군이 이란을 공습했다',
                    'body_verified': False}
        self.assertFalse(stage._iran_attack_restraint_statement(denied))
        self.assertNotEqual(presentation.direction(stage, denied), 'green')
        self.assertFalse(stage._iran_attack_restraint_statement(attacked))
        self.assertEqual(presentation.direction(stage, attacked), 'red')


class Run856DiplomacyAndStalemateTests(unittest.TestCase):
    def _replay(self, slug, article_id):
        fixture = json.loads((Path(__file__).parent / 'test_fixtures'
                              / f'war_run856_{slug}_42711323558.json')
                             .read_text(encoding='utf-8'))
        self.assertEqual(fixture['provenance']['telegram_message_id'], 437)
        self.assertEqual(fixture['article']['classification_color'], 'red')
        snapshot, proof = fixture['semantic_snapshot'], fixture['semantic_proof']
        alert_bytes = base64.b64decode(snapshot['alert_utf8_base64'])
        evidence_bytes = base64.b64decode(snapshot['evidence_utf8_base64'])
        self.assertEqual(hashlib.sha256(alert_bytes).hexdigest(), proof['alert_sha256'])
        self.assertEqual(hashlib.sha256(evidence_bytes).hexdigest(), proof['evidence_sha256'])
        original = json.loads(evidence_bytes)
        row = next(row for row in original['articles'] if row['id'] == article_id)
        text, projected = presentation.project(stage, alert_bytes.decode('utf-8'),
                                               original, proof, snapshot)
        target = next(row for row in projected['articles'] if row['id'] == article_id)
        self.assertNotEqual(projected['alert_sha256'],
                            fixture['provenance']['observed_delivered_alert_sha256'])
        return row, target, text

    def test_saved_qatar_us_meeting_is_reported_diplomatic_contact(self):
        row, target, text = self._replay('qatar_iran_talks', '27fb05307ed11cd04cf7')
        self.assertFalse(row['body_verified'])
        self.assertEqual(stage.non_military_kind(row), 'diplomatic_contact')
        self.assertEqual(stage.topic_label(row), '카타르·미국 · 이란 협상 논의 보도')
        self.assertEqual(presentation.direction(stage, row), 'green')
        self.assertEqual(target['classification_color'], 'green')
        self.assertIn('🟢 [신규] <b>1. 카타르·미국 · 이란 협상 논의 보도</b>', text)
        self.assertNotIn('이란·호르무즈', text.split('🟢 [신규] <b>2.', 1)[0])
        self.assertIn('RSS 입력 기준·본문 미확인', text)

    def test_saved_ambiguous_order_is_context_without_direction(self):
        row, target, text = self._replay('iran_no_war_no_peace', '78a832477ee92c567732')
        self.assertTrue(row['body_verified'])
        self.assertEqual(stage.non_military_kind(row), 'diplomatic_position')
        self.assertEqual(stage.topic_label(row), '이란 · 전쟁·평화 교착 종식 지시')
        scored = copy.deepcopy(row)
        score, tags = stage.score_item(
            scored, dt.datetime.fromisoformat('2026-11-10T07:24:00+09:00'))
        self.assertGreater(score, 0)
        self.assertEqual(tags, ['전쟁·평화 교착 종식 지시'])
        self.assertIsNone(presentation.direction(stage, row))
        self.assertIsNone(target['classification_color'])
        self.assertEqual(target['display_section'], 'context_reference')
        self.assertIn('<b>참고 1. 이란 · 전쟁·평화 교착 종식 지시</b>', text)
        self.assertNotIn('이란·호르무즈', text)

    def test_separate_current_attack_retains_red(self):
        qatar = {'title_original': 'QATAR PRIME MINISTER: MET WITH TRUMP AND VANCE, '
                 'DISCUSSED WAYS TO MAKE PROGRESS IN IRAN NEGOTIATIONS; '
                 'MEANWHILE US ATTACKED IRAN', 'body_verified': False}
        stalemate = {'title_original': '이란 대통령 "최고지도자, 전쟁도 평화도 아닌 상황 종식 지시"; '
                     '한편 이란군이 공습했다', 'body_verified': True}
        self.assertFalse(stage._qatar_us_iran_negotiations_contact(stage._headline(qatar)))
        self.assertFalse(stage._no_war_no_peace_stalemate_statement(stage._headline(stalemate)))
        self.assertEqual(presentation.direction(stage, qatar), 'red')
        self.assertEqual(presentation.direction(stage, stalemate), 'red')


class Run858LowReattackStatementTests(unittest.TestCase):
    def test_saved_sent_false_red_replays_as_qualified_easing(self):
        fixture = json.loads((Path(__file__).parent / 'test_fixtures'
                              / 'war_run858_low_reattack_42713168248.json')
                             .read_text(encoding='utf-8'))
        provenance, saved = fixture['provenance'], fixture['article']
        self.assertEqual(provenance['telegram_message_id'], 438)
        self.assertEqual(saved['classification_color'], 'red')
        self.assertEqual(saved['semantic_classification_color'], 'red')
        self.assertFalse(saved['body_verified'])
        snapshot, proof = fixture['semantic_snapshot'], fixture['semantic_proof']
        alert_bytes = base64.b64decode(snapshot['alert_utf8_base64'])
        evidence_bytes = base64.b64decode(snapshot['evidence_utf8_base64'])
        self.assertEqual(hashlib.sha256(alert_bytes).hexdigest(), proof['alert_sha256'])
        self.assertEqual(hashlib.sha256(evidence_bytes).hexdigest(), proof['evidence_sha256'])
        original = json.loads(evidence_bytes)
        row = next(row for row in original['articles'] if row['id'] == saved['id'])
        self.assertTrue(stage._iran_attack_restraint_statement(row))
        self.assertEqual(stage.non_military_kind(row), 'military_position')
        self.assertEqual(stage.final_color(row), 'yellow')
        self.assertEqual(stage.topic_label(row), '미국·이란 · 공격 재개 가능성 낮다는 발언')
        self.assertEqual(presentation.direction(stage, row), 'green')
        scored = copy.deepcopy(row)
        score, tags = stage.score_item(
            scored, dt.datetime.fromisoformat('2026-11-10T07:37:00+09:00'))
        self.assertGreater(score, 0)
        self.assertEqual(tags, ['공격 재개 가능성 낮다는 발언'])

        text, projected = presentation.project(stage, alert_bytes.decode('utf-8'),
                                               original, proof, snapshot)
        target = next(row for row in projected['articles'] if row['id'] == saved['id'])
        self.assertEqual(target['classification_color'], 'green')
        self.assertEqual(target['semantic_classification_color'], 'red')
        self.assertIn('🟢 [속보] <b>1. 미국·이란 · 공격 재개 가능성 낮다는 발언</b>', text)
        self.assertIn('제목 기준·본문 미확인', text)
        self.assertNotIn('이란·호르무즈', text.split('<b>2.', 1)[0])
        self.assertNotEqual(projected['alert_sha256'],
                            provenance['observed_delivered_alert_sha256'])

    def test_denial_and_separate_attack_stay_out_of_easing(self):
        base = '트럼프 "이란戰 종식 긍정적 모멘텀…공격 재개 가능성 작아"'
        denied = {'title_original': base + '라는 발언을 부인', 'body_verified': False}
        attacked = {'title_original': base + '; 한편 미군이 이란을 공습했다',
                    'body_verified': False}
        self.assertFalse(stage._iran_attack_restraint_statement(denied))
        self.assertNotEqual(presentation.direction(stage, denied), 'green')
        self.assertFalse(stage._iran_attack_restraint_statement(attacked))
        self.assertEqual(presentation.direction(stage, attacked), 'red')


class Run869NegotiationStandoffTests(unittest.TestCase):
    def test_saved_sent_false_contact_and_green_replay(self):
        fixture = json.loads((Path(__file__).parent / 'test_fixtures'
                              / 'war_run869_negotiation_standoff_43177720603.json')
                             .read_text(encoding='utf-8'))
        provenance, saved = fixture['provenance'], fixture['article']
        self.assertEqual(provenance['telegram_message_id'], 448)
        self.assertEqual(saved['non_military_kind'], 'diplomatic_contact')
        self.assertEqual(saved['classification_color'], 'green')
        self.assertFalse(saved['body_verified'])
        self.assertEqual(hashlib.sha256(saved['title_original'].encode('utf-8')).hexdigest(),
                         provenance['title_sha256'])

        row = copy.deepcopy(saved)
        row['classification_color'] = row['semantic_classification_color']
        self.assertEqual(stage.non_military_kind(row), 'diplomatic_position')
        self.assertEqual(stage.topic_label(row), '미국·이란 · 협상 입장 대립·신경전')
        self.assertEqual(presentation.direction(stage, row), 'red')
        fresh = copy.deepcopy(row)
        fresh.pop('non_military_kind', None)
        fresh.pop('classification_color', None)
        score, tags = stage.score_item(
            fresh, dt.datetime.fromisoformat('2026-11-12T16:48:18+09:00'))
        self.assertGreater(score, 0)
        self.assertEqual(tags, ['외교 갈등·압박 보도'])
        self.assertEqual(stage.final_color(fresh), 'yellow')
        self.assertEqual(presentation.direction(stage, fresh), 'red')

    def test_standoff_ending_does_not_hide_negotiation_resumption(self):
        row = {'title_original': '트럼프·이란, 종전협상 신경전 끝내고 회담 재개 합의',
               'body_verified': False}
        self.assertFalse(stage._negotiation_standoff_headline(row['title_original']))
        self.assertEqual(presentation.direction(stage, row), 'green')


class Run872SatelliteThrottleTests(unittest.TestCase):
    def test_saved_title_only_restriction_has_no_invented_direction(self):
        fixture = json.loads((Path(__file__).parent / 'test_fixtures'
                              / 'war_run872_satellite_throttle_43257768510.json')
                             .read_text(encoding='utf-8'))
        provenance, saved = fixture['provenance'], fixture['article']
        self.assertEqual(provenance['telegram_message_id'], 451)
        self.assertEqual(saved['classification_color'], 'red')
        self.assertFalse(saved['body_verified'])
        self.assertEqual(hashlib.sha256(saved['title_original'].encode()).hexdigest(),
                         provenance['title_sha256'])
        proof, snapshot = fixture['semantic_proof'], fixture['semantic_snapshot']
        alert = base64.b64decode(snapshot['alert_utf8_base64'])
        evidence_bytes = base64.b64decode(snapshot['evidence_utf8_base64'])
        self.assertEqual(hashlib.sha256(alert).hexdigest(), proof['alert_sha256'])
        self.assertEqual(hashlib.sha256(evidence_bytes).hexdigest(), proof['evidence_sha256'])
        original = json.loads(evidence_bytes)
        row = next(row for row in original['articles'] if row['id'] == saved['id'])
        self.assertIsNone(presentation.direction(stage, row))

        text, projected = presentation.project(stage, alert.decode('utf-8'),
                                               original, proof, snapshot)
        target = next(row for row in projected['articles'] if row['id'] == saved['id'])
        self.assertIsNone(target['classification_color'])
        self.assertEqual(target['display_section'], 'context_reference')
        self.assertIn('위성 시스템 제한 보도·원인 미확인', text)
        self.assertIn('RSS 입력 기준·본문 미확인', text)
        self.assertNotIn('🔴 [신규]', text)
        self.assertNotIn('🟡', text)
        self.assertNotEqual(projected['alert_sha256'],
                            provenance['observed_delivered_alert_sha256'])

    def test_explicit_attack_pressure_and_restoration_keep_their_direction(self):
        for title, expected in (
                ('Russia attacked a Starshield satellite station today', 'red'),
                ('SpaceX throttled Starshield to pressure Ukraine', 'red'),
                ('Starshield satellite service restored after restriction', 'green')):
            with self.subTest(title=title):
                self.assertEqual(presentation.direction(stage, {
                    'title_original': title, 'body_verified': False}), expected)


class Run873NoDealRejectionTests(unittest.TestCase):
    def test_saved_no_deal_headline_cannot_turn_semantic_red_green(self):
        fixture = json.loads((Path(__file__).parent / 'test_fixtures'
                              / 'war_run873_no_deal_43319215337.json')
                             .read_text(encoding='utf-8'))
        provenance, saved = fixture['provenance'], fixture['article']
        self.assertEqual(provenance['telegram_message_id'], 452)
        self.assertEqual(saved['classification_color'], 'green')
        self.assertEqual(saved['semantic_classification_color'], 'red')
        self.assertTrue(saved['body_verified'])
        self.assertEqual(hashlib.sha256(saved['title_original'].encode()).hexdigest(),
                         provenance['title_sha256'])
        proof, snapshot = fixture['semantic_proof'], fixture['semantic_snapshot']
        alert = base64.b64decode(snapshot['alert_utf8_base64'])
        evidence_bytes = base64.b64decode(snapshot['evidence_utf8_base64'])
        self.assertEqual(hashlib.sha256(alert).hexdigest(), proof['alert_sha256'])
        self.assertEqual(hashlib.sha256(evidence_bytes).hexdigest(), proof['evidence_sha256'])
        original = json.loads(evidence_bytes)
        row = next(row for row in original['articles'] if row['id'] == saved['id'])
        self.assertEqual(row['classification_color'], 'red')
        self.assertEqual(presentation.direction(stage, row), 'red')

        text, projected = presentation.project(stage, alert.decode('utf-8'),
                                               original, proof, snapshot)
        target = next(row for row in projected['articles'] if row['id'] == saved['id'])
        self.assertEqual(target['classification_color'], 'red')
        self.assertIn('🔴 [신규] <b>1.', text)
        self.assertNotIn('🟢 [신규] <b>1.', text)
        self.assertNotEqual(projected['alert_sha256'],
                            provenance['observed_delivered_alert_sha256'])

    def test_no_deal_rejection_does_not_hide_a_separate_easing_event(self):
        title = '트럼프 "이란과 합의 필요 없다"는 보도를 부인하고 회담 재개에 합의'
        self.assertEqual(presentation.direction(stage, {
            'title_original': title, 'body_verified': False}), 'green')


if __name__ == '__main__':
    unittest.main(verbosity=2)
