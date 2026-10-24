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

    def test_unverified_conflicting_background_tags_are_held_without_a_red_badge(self):
        row = {
            'id': '8a173ef4e1e97850e4ac',
            'title_original': 'As Israeli election looms, Trump advisers see opportunity beyond Netanyahu',
            'title_ko': '이스라엘 선거가 다가옴에 따라 트럼프 고문들은 네타냐후 너머의 기회를 본다',
            'source': 'Axios',
            'link': 'https://www.axios.com/2026/10/24/israel-election-trump-netanyahu-advisers',
            'tags': ['정치일정', '종전·협상', '확전'],
            'body_verified': False,
            'publication_basis': 'discovery_feed',
            'article_text_sha256': 'e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855',
            'rendered': True,
            'classification_color': '',
        }
        self.assertIsNone(stage.non_military_kind(row))
        self.assertEqual(stage.final_color(row), '')
        self.assertTrue(presentation._unresolved_mixed_background(stage, row))
        self.assertIsNone(presentation.direction(stage, row))

        semantic_text = '\n'.join([
            '<b>전쟁·종전·재건 웹감시</b>',
            '🔴 <b>공격·타격·확전·압박</b>',
            '조회 2026-10-24 23:12 KST',
            '<b>핵심 변화</b>',
            '🔴 [신규] <b>1. 이란·호르무즈</b>',
            row['title_ko'],
            'RSS 보도 10-24 21:56 KST · 종전·협상 · 확전 · <a href="' + row['link'] + '">Axios 원문</a> · RSS 입력 기준·본문 미확인',
            '<b>시장 반응</b>',
            '시장자료 확인 보류',
            '<b>투자 판정</b>',
            '이전 분류 요약',
        ])
        receipt = {'articles': [copy.deepcopy(row)], 'markets': {}, 'market_source_status': {}}
        text, projected = presentation.project(stage, semantic_text, receipt, {}, {})
        output_row = projected['articles'][0]
        self.assertIsNone(output_row['classification_color'])
        self.assertEqual(output_row['display_section'], 'unresolved_direction')
        self.assertIn('<b>방향 판정 보류</b>', text)
        self.assertIn('[방향 미확정]', text)
        self.assertNotIn('🔴 [방향 미확정]', text)
        self.assertNotIn('🔴 <b>공격·타격·확전·압박</b>', text)
        self.assertIn('<b>방향 판정 보류:</b> 1건', text)
        self.assertIn('RSS 입력 기준·본문 미확인', text)

        attack = copy.deepcopy(row)
        attack['title_original'] = 'Israel launches strikes on Iran as election looms'
        self.assertFalse(presentation._unresolved_mixed_background(stage, attack))
        self.assertEqual(presentation.direction(stage, attack), 'red')

        dialogue = copy.deepcopy(row)
        dialogue['title_original'] = (
            'Kremlin confirms Oleshky ceasefire, says working with Ukraine on evacuation timing')
        self.assertFalse(presentation._unresolved_mixed_background(stage, dialogue))
        self.assertEqual(presentation.direction(stage, dialogue), 'green')

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


if __name__ == '__main__':
    unittest.main(verbosity=2)

