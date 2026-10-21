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


if __name__ == '__main__':
    unittest.main(verbosity=2)
