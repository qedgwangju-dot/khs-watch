"""Offline regressions from Telegram #323. No live source or send calls."""
import datetime as dt
import copy
import html
import hashlib
from email.utils import format_datetime
import io
import json
from pathlib import Path
import tempfile
import unittest
from contextlib import ExitStack
from unittest.mock import Mock, patch

import war_peace_reconstruction_watch_integrity as integrity
import war_peace_reconstruction_watch_evidence as evidence
import war_peace_reconstruction_watch_precise as market
import war_peace_reconstruction_watch_diplomacy_flash as quality
import war_peace_reconstruction_watch_newideas as newideas
import war_peace_reconstruction_watch_bodycolor as source_body

watch = integrity.watch
NOW = dt.datetime(2026, 10, 13, 1, 57, tzinfo=watch.KST)


def article(title, *, source='파이낸셜뉴스', link='https://www.fnnews.com/news/example'):
    return {'id': 'fixture-id', 'title': title, 'title_original': title, 'title_ko': title,
            'description': '', 'source': source, 'link': link, 'tags': ['확전'], 'score': 90,
            'published': format_datetime(NOW - dt.timedelta(minutes=20)), 'body_checked': True}


class IntegrityTests(unittest.TestCase):
    def setUp(self):
        self.network = patch('urllib.request.urlopen', side_effect=AssertionError('network/send forbidden'))
        self.network.start()
        self.addCleanup(self.network.stop)
        # Fixture headlines must not inherit confirmed deliveries from the checkout.
        self.state_dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.state_dir.cleanup)
        self.state_patch = patch.object(watch, 'STATE', Path(self.state_dir.name)/'state.json')
        self.state_patch.start()
        self.addCleanup(self.state_patch.stop)
        watch.STATE.write_text('{"seen": []}', encoding='utf-8')

    def event_background_fixture(self):
        path = Path(__file__).parent/'test_fixtures/war_event_background_39343779440.json'
        value = json.loads(path.read_text(encoding='utf-8'))
        return value, dt.datetime.fromisoformat(value['provenance']['queried_at_kst'])

    def test_actual_airport_background_event_delay_keeps_current_stage_and_actor(self):
        fixture, _ = self.event_background_fixture()
        row = fixture['articles'][0]
        self.assertEqual(integrity.non_military_kind(row), 'operational_disruption')
        self.assertEqual(integrity.final_color(row), 'yellow')
        self.assertEqual(integrity.topic_label(row), '사우디 · 행사·운영 일정 변경 보도')
        self.assertEqual(integrity._display_headline(row), row['title_original'])

    def test_event_delay_background_variants_preserve_45_percent_and_quotes(self):
        for name in ('사막의 다보스', "'사막의 다보스'", '‘사막의 다보스’', '포럼', '행사'):
            title = '공항 피격·항공편 45% 취소·투자자 이탈…사우디 ' + name + ' 연기'
            with self.subTest(title=title):
                row = article(title)
                self.assertEqual(integrity.non_military_kind(row), 'operational_disruption')
                self.assertEqual(integrity.final_color(row), 'yellow')
                self.assertEqual(integrity.topic_label(row), '사우디 · 행사·운영 일정 변경 보도')
                self.assertEqual(integrity._display_headline(row), title)

    def test_actual_event_delay_score_clears_old_attack_cache(self):
        fixture, now = self.event_background_fixture()
        row = fixture['articles'][0]
        metadata = copy.deepcopy(row['source_metadata'])
        row['signals_ko'] = ['Aramco 공격 주장']
        row['forced_tags'] = ['확전']
        row['newidea_marks'] = ['과거 공격']
        row['deep_signal'] = '과거 공격'
        integrity.score_item(row, now)
        self.assertEqual(row['tags'], ['행사·운영 일정 변경 보도'])
        self.assertFalse(row['signals_ko'])
        self.assertFalse(row['forced_tags'])
        self.assertNotIn('newidea_marks', row)
        self.assertNotIn('deep_signal', row)
        self.assertEqual(row['source_metadata'], metadata)
        self.assertTrue(row['body_verified'])

    def test_event_delay_does_not_hide_separate_new_or_completed_attack(self):
        for title in ('공항 피격·항공편 45% 취소…사우디 행사 연기…후티 미사일 발사',
                      '항공편 45% 취소…사우디 행사 연기…후티 공습 개시',
                      '항공편 45% 취소…사우디 행사 연기…공항 피격됐다',
                      '항공편 45% 취소…사우디 행사 연기…후티가 공항을 공격했다'):
            with self.subTest(title=title):
                row = article(title)
                self.assertNotEqual(integrity.non_military_kind(row), 'operational_disruption')
                self.assertEqual(integrity.final_color(row), 'red')

    def test_airport_background_requires_actual_event_schedule_change(self):
        for title in ('공항 피격·항공편 45% 취소·투자자 이탈',
                      '공항 피격…사우디 행사 예정대로 개최',
                      '항공편 45% 취소…사우디 행사 연기 여부 미정'):
            with self.subTest(title=title):
                self.assertNotEqual(integrity.non_military_kind(article(title)), 'operational_disruption')

    def test_actual_event_background_full_render_gate_and_state_preserved(self):
        fixture, now = self.event_background_fixture()
        rows = fixture['articles']
        before = watch.STATE.read_bytes()
        with patch.object(integrity.body_parallel, '_safe_enrich'), patch.object(watch, 'market_source_status', fixture['market_source_status'], create=True):
            text = integrity.build_alert(rows, fixture['markets'], now)
        shown = [row for row in rows if row['link'] in html.unescape(text)]
        self.assertEqual([row['id'] for row in shown], [row['id'] for row in rows[:4]])
        self.assertEqual([row['classification_color'] for row in shown], ['yellow']*4)
        for row in shown:
            self.assertIn(html.escape(row['title_original']), text)
        self.assertIn('45%', text)
        self.assertIn('사우디 · 행사·운영 일정 변경 보도', text)
        self.assertNotIn('Aramco', text)
        self.assertNotIn('🔴', text)
        self.assertNotIn('🟢', text)
        self.assertNotIn('신규 변화의 중심은 실제 공격', text)
        self.assertIn('제목 기준·본문 미확인', text)
        receipt = evidence.alert_receipt(rows, fixture['markets'], now, text)
        with tempfile.TemporaryDirectory() as folder, ExitStack() as stack:
            for attr, name in {'ALERT':'alert.txt','PENDING':'pending.json','AUDIT':'evidence.json'}.items():
                stack.enter_context(patch.object(watch, attr, Path(folder)/name))
            watch.ALERT.write_text(text, encoding='utf-8')
            watch.PENDING.write_text(json.dumps({'ids':[row['id'] for row in shown]}), encoding='utf-8')
            watch.AUDIT.write_text(json.dumps(receipt, ensure_ascii=False), encoding='utf-8')
            integrity.verify_alert()
        self.assertEqual(watch.STATE.read_bytes(), before)

    def test_final_gate_rejects_actual_same_hash_event_background_wrong_body(self):
        fixture, now = self.event_background_fixture()
        rows = fixture['articles'][:4]
        text = fixture['sent_alert'].strip()
        receipt = evidence.alert_receipt(rows, fixture['markets'], now, text)
        self.assertEqual(receipt['alert_sha256'], fixture['provenance']['alert_sha256'])
        with tempfile.TemporaryDirectory() as folder, ExitStack() as stack:
            for attr, name in {'ALERT':'alert.txt','PENDING':'pending.json','AUDIT':'evidence.json'}.items():
                stack.enter_context(patch.object(watch, attr, Path(folder)/name))
            watch.ALERT.write_text(text, encoding='utf-8')
            watch.PENDING.write_text(json.dumps({'ids':[row['id'] for row in rows]}), encoding='utf-8')
            watch.AUDIT.write_text(json.dumps(receipt, ensure_ascii=False), encoding='utf-8')
            with self.assertRaisesRegex(RuntimeError, 'WAR_INTEGRITY_GATE'):
                integrity.verify_alert()

    def conditional_summit_fixture(self):
        path=Path(__file__).parent/'test_fixtures/war_conditional_summit_39336422842.json'
        value=json.loads(path.read_text(encoding='utf-8'))
        return value,dt.datetime.fromisoformat(value['provenance']['queried_at_kst'])

    def test_actual_willingness_excludes_explicitly_excluded_Zelensky(self):
        fixture,_=self.conditional_summit_fixture()
        row=fixture['articles'][0]
        self.assertEqual(integrity.non_military_kind(row),'diplomatic_plan')
        self.assertEqual(integrity.final_color(row),'yellow')
        self.assertEqual(integrity.topic_label(row),'미국·중국·러시아 · 회담 용의 발언')

    def test_actual_negotiation_exclusion_keeps_dispute_actors(self):
        fixture,_=self.conditional_summit_fixture()
        row=fixture['articles'][1]
        self.assertEqual(integrity.non_military_kind(row),'diplomatic_position')
        self.assertEqual(integrity.final_color(row),'yellow')
        self.assertEqual(integrity.topic_label(row),'미국·우크라이나 · 협상 참여·배제 입장')

    def test_actual_conditional_summit_keeps_compact_three_party_subject(self):
        fixture,_=self.conditional_summit_fixture()
        row=fixture['articles'][2]
        self.assertEqual(integrity.non_military_kind(row),'diplomatic_plan')
        self.assertEqual(integrity.final_color(row),'yellow')
        self.assertEqual(integrity.topic_label(row),'미국·중국·러시아 · 조건부 회담 의향')

    def test_actual_conditional_and_exclusion_render_preserves_full_gate(self):
        fixture,now=self.conditional_summit_fixture()
        rows=fixture['articles'];before=watch.STATE.read_bytes()
        with patch.object(integrity.body_parallel,'_safe_enrich'),patch.object(watch,'market_source_status',fixture['market_source_status'],create=True):
            text=integrity.build_alert(rows,fixture['markets'],now)
        receipt=evidence.alert_receipt(rows,fixture['markets'],now,text)
        shown=[r for r in receipt['articles'] if r['rendered']]
        self.assertEqual([r['id'] for r in shown],[r['id'] for r in rows[:4]])
        self.assertEqual([r['classification_color'] for r in shown],['yellow']*4)
        self.assertNotIn('미국·우크라이나·중국·러시아',text)
        self.assertIn('中이 원하면 할 것',html.unescape(text))
        for r in rows[:4]:self.assertIn(html.escape(r['title_original']),text)
        self.assertNotIn('🔴',text)
        self.assertNotIn('🟢',text)
        with tempfile.TemporaryDirectory() as folder,ExitStack() as stack:
            for attr,name in {'ALERT':'alert.txt','PENDING':'pending.json','AUDIT':'evidence.json'}.items():
                stack.enter_context(patch.object(watch,attr,Path(folder)/name))
            watch.ALERT.write_text(text,encoding='utf-8')
            watch.PENDING.write_text(json.dumps({'ids':[r['id'] for r in shown]}),encoding='utf-8')
            watch.AUDIT.write_text(json.dumps(receipt,ensure_ascii=False),encoding='utf-8')
            integrity.verify_alert()
        self.assertEqual(watch.STATE.read_bytes(),before)

    def test_final_gate_rejects_same_hash_conditional_and_exclusion_errors(self):
        fixture,now=self.conditional_summit_fixture()
        rows=fixture['articles'][:4];text=fixture['dry_run_alert'].strip()
        receipt=evidence.alert_receipt(rows,fixture['markets'],now,text)
        self.assertEqual(receipt['alert_sha256'],fixture['provenance']['alert_sha256'])
        with tempfile.TemporaryDirectory() as folder,ExitStack() as stack:
            for attr,name in {'ALERT':'alert.txt','PENDING':'pending.json','AUDIT':'evidence.json'}.items():
                stack.enter_context(patch.object(watch,attr,Path(folder)/name))
            watch.ALERT.write_text(text,encoding='utf-8')
            watch.PENDING.write_text(json.dumps({'ids':[r['id'] for r in rows]}),encoding='utf-8')
            watch.AUDIT.write_text(json.dumps(receipt,ensure_ascii=False),encoding='utf-8')
            with self.assertRaisesRegex(RuntimeError,'WAR_INTEGRITY_GATE'):integrity.verify_alert()

    def test_willingness_denial_and_condition_keep_negation(self):
        for title in ('트럼프, 푸틴·시진핑과 회담 용의 없어',
                      '트럼프, 푸틴과 회담 용의 부인'):
            with self.subTest(title=title):
                self.assertEqual(integrity.non_military_kind(article(title)),'diplomatic_position')
                self.assertIn('회담 의향 부인',integrity.topic_label(article(title)))
        title='트럼프, 미중러 정상회담 "중국이 원하면 할 것"'
        with patch.object(integrity.body_parallel,'_safe_enrich'):
            text=integrity.build_alert([article(title)],[],NOW)
        self.assertIn(html.escape(title),text)
        self.assertNotIn('🟢',text)

    def test_conditional_or_exclusion_does_not_hide_actual_operations(self):
        for title in ('트럼프, 미중러 정상회담 원하면 할 것…이란 미사일 발사',
                      '트럼프, 젤렌스키 종전협상에서 배제…러시아 공습 개시'):
            with self.subTest(title=title):
                row=article(title)
                self.assertIsNone(integrity.non_military_kind(row))
                self.assertEqual(integrity.final_color(row),'red')
        self.assertNotEqual(integrity.non_military_kind(article('트럼프, 푸틴·시진핑과 정상회담 개최')),'diplomatic_plan')

    def test_unrendered_North_Russia_contact_keeps_both_explicit_actors(self):
        fixture,_=self.conditional_summit_fixture()
        row=fixture['articles'][4]
        self.assertEqual(integrity.non_military_kind(row),'diplomatic_contact')
        self.assertEqual(integrity.topic_label(row),'북한·러시아 · 외교 접촉 보도')

    def postponement_summit_fixture(self):
        path = Path(__file__).parent/'test_fixtures/war_postponement_summit_39317765794.json'
        value = json.loads(path.read_text(encoding='utf-8'))
        return value, dt.datetime.fromisoformat(value['provenance']['queried_at_kst'])

    def test_actual_Davos_alias_postponement_is_an_operating_schedule_report(self):
        fixture, _ = self.postponement_summit_fixture()
        row = fixture['articles'][0]
        self.assertEqual(integrity.non_military_kind(row), 'operational_disruption')
        self.assertEqual(integrity.final_color(row), 'yellow')
        self.assertEqual(integrity.topic_label(row), '사우디·후티 · 행사·운영 일정 변경 보도')

    def test_actual_summit_openness_preserves_three_explicit_participants(self):
        fixture, _ = self.postponement_summit_fixture()
        row = fixture['articles'][1]
        self.assertEqual(integrity.non_military_kind(row), 'diplomatic_plan')
        self.assertEqual(integrity.final_color(row), 'yellow')
        self.assertEqual(integrity.topic_label(row), '미국·중국·러시아 · 정상회담 의향·논의')
        self.assertEqual(integrity._display_headline(row), row['title_original'])

    def test_actual_bargain_proposal_question_is_not_an_energy_ceasefire(self):
        fixture, _ = self.postponement_summit_fixture()
        row = fixture['articles'][2]
        self.assertEqual(integrity.non_military_kind(row), 'diplomatic_plan')
        self.assertEqual(integrity.final_color(row), 'yellow')
        self.assertEqual(integrity.topic_label(row), '미국·러시아 · 담판 제안·논의')

    def test_actual_meeting_uncertainty_preserves_Kim_and_no_confirmed_contact(self):
        fixture, _ = self.postponement_summit_fixture()
        row = fixture['articles'][3]
        self.assertEqual(integrity.non_military_kind(row), 'diplomatic_position')
        self.assertEqual(integrity.final_color(row), 'yellow')
        self.assertEqual(integrity.topic_label(row), '미국·북한 · 회담 여부 미정 발언')

    def test_actual_postponement_and_summit_render_preserves_full_gate_and_limits(self):
        fixture, now = self.postponement_summit_fixture()
        rows = fixture['articles']
        before = watch.STATE.read_bytes()
        with patch.object(integrity.body_parallel, '_safe_enrich'), patch.object(watch, 'market_source_status', fixture['market_source_status'], create=True):
            text = integrity.build_alert(rows, fixture['markets'], now)
        shown = [r for r in rows if r['link'] in html.unescape(text)]
        self.assertEqual([r['id'] for r in shown], [r['id'] for r in rows[:4]])
        self.assertEqual([r['classification_color'] for r in shown], ['yellow']*4)
        for row in shown:
            self.assertIn(html.escape(row['title_original']), text)
        self.assertNotIn('🔴', text)
        self.assertNotIn('🟢', text)
        self.assertNotIn('에너지 휴전 발표·양측 검증 대기', text)
        self.assertNotIn('후속 3자 협상·회담이 실제 준비 단계로 이동하는지 확인', text)
        self.assertIn('RSS 입력 기준·본문 미확인', text)
        self.assertIn('제목 기준·본문 미확인', text)
        self.assertEqual([r['body_verified'] for r in shown], [True, False, True, False])
        receipt = evidence.alert_receipt(rows, fixture['markets'], now, text)
        with tempfile.TemporaryDirectory() as folder, ExitStack() as stack:
            for attr, name in {'ALERT':'alert.txt','PENDING':'pending.json','AUDIT':'evidence.json'}.items():
                stack.enter_context(patch.object(watch,attr,Path(folder)/name))
            watch.ALERT.write_text(text,encoding='utf-8')
            watch.PENDING.write_text(json.dumps({'ids':[r['id'] for r in shown]}),encoding='utf-8')
            watch.AUDIT.write_text(json.dumps(receipt,ensure_ascii=False),encoding='utf-8')
            integrity.verify_alert()
        self.assertEqual(watch.STATE.read_bytes(),before)

    def test_final_gate_rejects_actual_same_hash_postponement_summit_wrong_body(self):
        fixture, now = self.postponement_summit_fixture()
        rows = fixture['articles'][:4]
        text = fixture['sent_alert'].strip()
        receipt = evidence.alert_receipt(rows,fixture['markets'],now,text)
        self.assertEqual(receipt['alert_sha256'],fixture['provenance']['alert_sha256'])
        with tempfile.TemporaryDirectory() as folder, ExitStack() as stack:
            for attr,name in {'ALERT':'alert.txt','PENDING':'pending.json','AUDIT':'evidence.json'}.items():
                stack.enter_context(patch.object(watch,attr,Path(folder)/name))
            watch.ALERT.write_text(text,encoding='utf-8')
            watch.PENDING.write_text(json.dumps({'ids':[r['id'] for r in rows]}),encoding='utf-8')
            watch.AUDIT.write_text(json.dumps(receipt,ensure_ascii=False),encoding='utf-8')
            with self.assertRaisesRegex(RuntimeError,'WAR_INTEGRITY_GATE'):
                integrity.verify_alert()

    def test_final_gate_rechecks_each_wrong_topic_with_a_matching_body_hash(self):
        fixture, now = self.postponement_summit_fixture()
        for index, wrong in enumerate(('사우디·후티','우크라이나·러시아','우크라이나·러시아 · 에너지 휴전 발표·양측 검증 대기','미국 · 외교 접촉 보도')):
            with self.subTest(index=index):
                rows = copy.deepcopy(fixture['articles'][:4])
                with patch.object(integrity.body_parallel,'_safe_enrich'):
                    text = integrity.build_alert(rows,fixture['markets'],now)
                topic = integrity.topic_label(rows[index])
                text = text.replace(html.escape(topic),html.escape(wrong),1)
                receipt = evidence.alert_receipt(rows,fixture['markets'],now,text)
                with tempfile.TemporaryDirectory() as folder, ExitStack() as stack:
                    for attr,name in {'ALERT':'alert.txt','PENDING':'pending.json','AUDIT':'evidence.json'}.items():
                        stack.enter_context(patch.object(watch,attr,Path(folder)/name))
                    watch.ALERT.write_text(text,encoding='utf-8')
                    watch.PENDING.write_text(json.dumps({'ids':[r['id'] for r in rows]}),encoding='utf-8')
                    watch.AUDIT.write_text(json.dumps(receipt,ensure_ascii=False),encoding='utf-8')
                    with self.assertRaisesRegex(RuntimeError,'WAR_INTEGRITY_GATE'):
                        integrity.verify_alert()

    def test_postponement_and_summit_words_do_not_hide_separate_actual_actions(self):
        for title in ("후티 미사일 발사…사우디 '사막의 다보스' 내년으로 연기",
                      'Trump open to summit with Xi and Putin; Russia attacked Ukraine',
                      '푸틴, 담판 제안…러시아 공습 개시',
                      '트럼프, 김정은 회담 여부 모르겠다…이란 미사일 발사'):
            with self.subTest(title=title):
                row=article(title)
                self.assertIsNone(integrity.non_military_kind(row))
                self.assertEqual(integrity.final_color(row),'red')

    def test_negated_summit_openness_is_not_a_positive_proposal(self):
        for title in ('Trump not open to summit with Xi and Putin',
                      "Trump isn't open to a summit with Xi and Putin",
                      'Trump not yet open to summit with Xi and Putin'):
            with self.subTest(title=title):
                row=article(title)
                self.assertEqual(integrity.non_military_kind(row),'diplomatic_position')
                self.assertEqual(integrity.topic_label(row),'미국·중국·러시아 · 정상회담 의향 부인')
                self.assertEqual(integrity._display_headline(row),title)

    def test_openness_preserves_contrast_without_an_agreement(self):
        title='Trump open to summit with Xi and Putin, but no agreement reached'
        row=article(title)
        with patch.object(integrity.body_parallel,'_safe_enrich'):
            text=integrity.build_alert([row],[],NOW)
        self.assertEqual(integrity.non_military_kind(row),'diplomatic_plan')
        self.assertEqual(row['classification_color'],'yellow')
        self.assertIn(html.escape(title),text)
        self.assertNotIn('🟢',text)

    def test_completed_summit_is_not_openness_or_a_proposal(self):
        for title in ('트럼프, 시진핑·푸틴과 정상회담 개최',
                      'Trump held a summit with Xi and Putin to discuss denuclearization'):
            with self.subTest(title=title):
                self.assertNotEqual(integrity.non_military_kind(article(title)),'diplomatic_plan')

    def test_explicit_bilateral_implemented_peace_is_not_a_summit_plan(self):
        for title in ('미국·러시아 정상회담…양측 휴전 합의 발효',
                      'Trump and Putin summit: ceasefire agreed and implemented by both sides'):
            with self.subTest(title=title):
                self.assertNotIn(integrity.non_military_kind(article(title)),('diplomatic_plan','diplomatic_position'))

    def test_meeting_location_is_not_an_extra_confirmed_participant(self):
        row=article('트럼프, 중국서 김정은과 회담 여부에 "모르겠다"')
        self.assertEqual(integrity.topic_label(row),'미국·북한 · 회담 여부 미정 발언')
        explicit=article('트럼프, 중국 시진핑과 회담 여부에 "모르겠다"')
        self.assertEqual(integrity.topic_label(explicit),'미국·중국 · 회담 여부 미정 발언')

    def test_postponement_background_and_generated_cache_do_not_change_new_event(self):
        fixture, now=self.postponement_summit_fixture()
        row=fixture['articles'][0]
        metadata=copy.deepcopy(row['source_metadata'])
        row['signals_ko']=['에너지 인프라 상호 공격 자제·중단']
        row['forced_tags']=['휴전·평화']
        with patch.object(integrity.body_parallel,'_safe_enrich'):
            text=integrity.build_alert([row],fixture['markets'],now)
        self.assertEqual(row['classification_color'],'yellow')
        self.assertTrue(row['body_verified'])
        self.assertEqual(row['source_metadata'],metadata)
        self.assertFalse(row['signals_ko'])
        self.assertFalse(row.get('forced_tags'))
        self.assertIn(html.escape(row['title_original']),text)
        self.assertNotIn('신규 변화의 중심은 실제 공격',text)

    def alias_fixture(self):
        path = Path(__file__).parent/'test_fixtures/war_source_alias_38526317484.json'
        fixture = json.loads(path.read_text(encoding='utf-8'))
        return fixture, dt.datetime.fromisoformat(fixture['provenance']['queried_at_kst'])

    def refinery_statement_fixture(self):
        path = Path(__file__).parent/'test_fixtures/war_refinery_statement_38706618570.json'
        fixture = json.loads(path.read_text(encoding='utf-8'))
        return fixture, dt.datetime.fromisoformat(fixture['provenance']['queried_at_kst'])

    def restart_declaration_fixture(self):
        path = Path(__file__).parent/'test_fixtures/war_restart_declaration_38824896981.json'
        fixture = json.loads(path.read_text(encoding='utf-8'))
        return fixture, dt.datetime.fromisoformat(fixture['provenance']['queried_at_kst'])

    def ceasefire_rejection_fixture(self):
        path = Path(__file__).parent/'test_fixtures/war_ceasefire_rejection_38830288661.json'
        fixture = json.loads(path.read_text(encoding='utf-8'))
        return fixture, dt.datetime.fromisoformat(fixture['provenance']['queried_at_kst'])

    def report_stage_fixture(self):
        path = Path(__file__).parent/'test_fixtures/war_report_stage_38836451449.json'
        fixture = json.loads(path.read_text(encoding='utf-8'))
        return fixture, dt.datetime.fromisoformat(fixture['provenance']['queried_at_kst'])

    def condemnation_shipping_fixture(self):
        path = Path(__file__).parent/'test_fixtures/war_condemnation_shipping_38896365398.json'
        fixture = json.loads(path.read_text(encoding='utf-8'))
        return fixture, dt.datetime.fromisoformat(fixture['provenance']['queried_at_kst'])

    def marked_analysis_fixture(self):
        path = Path(__file__).parent/'test_fixtures/war_marked_analysis_39004365855.json'
        fixture = json.loads(path.read_text(encoding='utf-8'))
        return fixture, dt.datetime.fromisoformat(fixture['provenance']['queried_at_kst'])

    def maritime_proposal_fixture(self):
        path = Path(__file__).parent/'test_fixtures/war_maritime_proposal_39101605203.json'
        fixture = json.loads(path.read_text(encoding='utf-8'))
        return fixture, dt.datetime.fromisoformat(fixture['provenance']['queried_at_kst'])

    def diplomatic_contact_fixture(self):
        path = Path(__file__).parent/'test_fixtures/war_diplomatic_contact_39158841555.json'
        return json.loads(path.read_text(encoding='utf-8'))['runs']

    def talk_plan_drone_fixture(self):
        path = Path(__file__).parent/'test_fixtures/war_talk_plan_drone_39177756870.json'
        value = json.loads(path.read_text(encoding='utf-8'))
        return value, dt.datetime.fromisoformat(value['provenance']['queried_at_kst'])

    def summit_support_fixture(self):
        path = Path(__file__).parent/'test_fixtures/war_diplomatic_actors_info_39187221621.json'
        value = json.loads(path.read_text(encoding='utf-8'))
        return value, dt.datetime.fromisoformat(value['provenance']['queried_at_kst'])

    def bilateral_possibility_fixture(self):
        path = Path(__file__).parent/'test_fixtures/war_bilateral_possibility_39276986309.json'
        value = json.loads(path.read_text(encoding='utf-8'))
        return value, dt.datetime.fromisoformat(value['provenance']['queried_at_kst'])

    def test_actual_Iran_Russia_ministers_keep_explicit_bilateral_contact(self):
        fixture, _ = self.bilateral_possibility_fixture()
        row = fixture['articles'][1]
        self.assertEqual(integrity.non_military_kind(row), 'diplomatic_contact')
        self.assertEqual(integrity.final_color(row), 'yellow')
        self.assertEqual(integrity.topic_label(row), '이란·러시아 · 외교 접촉 보도')

    def test_actual_summit_possibility_reaction_is_not_a_completed_contact(self):
        fixture, _ = self.bilateral_possibility_fixture()
        row = fixture['articles'][2]
        self.assertEqual(integrity.non_military_kind(row), 'diplomatic_position')
        self.assertEqual(integrity.final_color(row), 'yellow')
        self.assertEqual(integrity.topic_label(row), '러시아 · 회담 가능성에 대한 반응')

    def test_actual_bilateral_possibility_render_passes_full_gate(self):
        fixture, now = self.bilateral_possibility_fixture()
        rows = fixture['articles']
        with patch.object(integrity.body_parallel, '_safe_enrich'), patch.object(watch, 'market_source_status', fixture['market_source_status'], create=True):
            text = integrity.build_alert(rows, fixture['markets'], now)
        self.assertEqual([row['classification_color'] for row in rows], ['red', 'yellow', 'yellow'])
        for row in rows:
            self.assertIn(html.escape(row['title_original']), text)
        self.assertNotIn('이란·호르무즈', text)
        self.assertIn('이란·러시아 · 외교 접촉 보도', text)
        self.assertIn('러시아 · 회담 가능성에 대한 반응', text)
        receipt = evidence.alert_receipt(rows, fixture['markets'], now, text)
        with tempfile.TemporaryDirectory() as folder, ExitStack() as stack:
            for attr, name in {'ALERT': 'alert.txt', 'PENDING': 'pending.json', 'AUDIT': 'evidence.json'}.items():
                stack.enter_context(patch.object(watch, attr, Path(folder)/name))
            watch.ALERT.write_text(text, encoding='utf-8')
            watch.PENDING.write_text(json.dumps({'ids': [row['id'] for row in rows]}), encoding='utf-8')
            watch.AUDIT.write_text(json.dumps(receipt, ensure_ascii=False), encoding='utf-8')
            integrity.verify_alert()

    def test_final_gate_rejects_same_hash_wrong_bilateral_possibility_topics(self):
        fixture, now = self.bilateral_possibility_fixture()
        text = fixture['dry_run_alert'].strip()
        receipt = evidence.alert_receipt(fixture['articles'], fixture['markets'], now, text)
        self.assertEqual(receipt['alert_sha256'], fixture['provenance']['alert_sha256'])
        with tempfile.TemporaryDirectory() as folder, ExitStack() as stack:
            for attr, name in {'ALERT': 'alert.txt', 'PENDING': 'pending.json', 'AUDIT': 'evidence.json'}.items():
                stack.enter_context(patch.object(watch, attr, Path(folder)/name))
            watch.ALERT.write_text(text, encoding='utf-8')
            watch.PENDING.write_text(json.dumps({'ids': [row['id'] for row in fixture['articles']]}), encoding='utf-8')
            watch.AUDIT.write_text(json.dumps(receipt, ensure_ascii=False), encoding='utf-8')
            with self.assertRaisesRegex(RuntimeError, 'WAR_INTEGRITY_GATE'):
                integrity.verify_alert()

    def test_bilateral_contact_keeps_separate_operations_and_implemented_peace(self):
        for title in ('이란·러 외무장관 회담…양국 공조 강조',
                      'Iran and Russia foreign ministers hold talks'):
            with self.subTest(title=title):
                self.assertEqual(integrity.non_military_kind(article(title)), 'diplomatic_contact')
                self.assertEqual(integrity.topic_label(article(title)), '이란·러시아 · 외교 접촉 보도')
        for title in ('이란·러 외무장관 회담…이란 미사일 발사',
                      '이란·러 외무장관 회담…양측 휴전 합의 발효'):
            with self.subTest(title=title):
                self.assertNotEqual(integrity.non_military_kind(article(title)), 'diplomatic_contact')

    def demands_disruption_fixture(self):
        path = Path(__file__).parent/'test_fixtures/war_demands_disruption_attack_39271931307.json'
        value = json.loads(path.read_text(encoding='utf-8'))
        return value, dt.datetime.fromisoformat(value['provenance']['queried_at_kst'])

    def test_actual_navigation_negotiation_demands_are_not_implemented_peace(self):
        fixture, _ = self.demands_disruption_fixture()
        row = fixture['articles'][1]
        self.assertEqual(integrity.non_military_kind(row), 'diplomatic_appeal')
        self.assertEqual(integrity.final_color(row), 'yellow')
        self.assertEqual(integrity.topic_label(row), '러시아 · 항행·협상 재개 요구')

    def test_actual_forum_postponement_is_not_a_new_attack(self):
        fixture, _ = self.demands_disruption_fixture()
        row = fixture['articles'][2]
        self.assertEqual(integrity.non_military_kind(row), 'operational_disruption')
        self.assertEqual(integrity.final_color(row), 'yellow')
        self.assertEqual(integrity.topic_label(row), '사우디·후티 · 행사·운영 일정 변경 보도')

    def test_actual_casualties_keep_attack_title_and_explicit_Yemeni_actor(self):
        fixture, _ = self.demands_disruption_fixture()
        for index, group in ((0, '우크라이나·러시아'), (3, '후티·예멘 정부군'), (4, '후티·예멘 정부군')):
            with self.subTest(index=index):
                row = fixture['articles'][index]
                self.assertIsNone(integrity.non_military_kind(row))
                self.assertEqual(integrity.final_color(row), 'red')
                self.assertEqual(integrity.topic_label(row), group + ' · 공습·공격 피해 보도')

    def test_unrendered_conditional_exchange_proposal_is_not_a_completed_pause(self):
        fixture, _ = self.demands_disruption_fixture()
        row = fixture['articles'][5]
        self.assertFalse(row['rendered'])
        self.assertEqual(integrity.non_military_kind(row), 'diplomatic_plan')
        self.assertEqual(integrity.final_color(row), 'yellow')
        self.assertEqual(integrity.topic_label(row), '우크라이나·러시아 · 조건부 공격 중단 제안')

    def test_demands_postponement_scores_do_not_inherit_peace_cache(self):
        fixture, now = self.demands_disruption_fixture()
        for index in (1, 2, 5):
            with self.subTest(index=index):
                row = fixture['articles'][index]
                expected, _ = integrity.source_score._original_score(copy.deepcopy(row), now)
                score, tags = integrity.score_item(row, now)
                self.assertEqual(score, expected)
                self.assertEqual(tags, [integrity.KIND_LABELS[integrity.non_military_kind(row)]])
                self.assertFalse(row.get('signals_ko') or row.get('forced_tags'))
                self.assertNotIn('newidea_marks', row)
                self.assertNotIn('deep_signal', row)

    def test_actual_demand_disruption_render_and_full_candidate_gate(self):
        fixture, now = self.demands_disruption_fixture()
        rows = fixture['articles']
        with patch.object(integrity.body_parallel, '_safe_enrich'), patch.object(watch, 'market_source_status', fixture['market_source_status'], create=True):
            text = integrity.build_alert(rows, fixture['markets'], now)
        receipt = evidence.alert_receipt(rows, fixture['markets'], now, text)
        shown = [row for row in receipt['articles'] if row['rendered']]
        self.assertEqual([row['id'] for row in shown], [row['id'] for row in rows[:4]])
        self.assertEqual([row['classification_color'] for row in shown], ['red', 'yellow', 'yellow', 'red'])
        for row in shown:
            self.assertIn(html.escape(' '.join(row['title_original'].split())), text)
            self.assertFalse(row.get('signals_ko') or row.get('forced_tags'))
        self.assertNotIn('후속 협상 실무 의제', text)
        self.assertNotIn('🟢', text)
        self.assertIn('53명 사망·200여명 부상', text)
        self.assertIn('본문 미확인', text)
        with tempfile.TemporaryDirectory() as folder, ExitStack() as stack:
            for attr, name in {'ALERT': 'alert.txt', 'PENDING': 'pending.json', 'AUDIT': 'evidence.json'}.items():
                stack.enter_context(patch.object(watch, attr, Path(folder)/name))
            watch.ALERT.write_text(text, encoding='utf-8')
            watch.PENDING.write_text(json.dumps({'ids': [row['id'] for row in shown]}), encoding='utf-8')
            watch.AUDIT.write_text(json.dumps(receipt, ensure_ascii=False), encoding='utf-8')
            integrity.verify_alert()

    def test_final_gate_rejects_actual_same_hash_demand_disruption_wrong_body(self):
        fixture, now = self.demands_disruption_fixture()
        rows = [row for row in fixture['articles'] if row['rendered']]
        text = fixture['sent_alert'].strip()
        receipt = evidence.alert_receipt(rows, fixture['markets'], now, text)
        self.assertEqual(receipt['alert_sha256'], fixture['provenance']['alert_sha256'])
        with tempfile.TemporaryDirectory() as folder, ExitStack() as stack:
            for attr, name in {'ALERT': 'alert.txt', 'PENDING': 'pending.json', 'AUDIT': 'evidence.json'}.items():
                stack.enter_context(patch.object(watch, attr, Path(folder)/name))
            watch.ALERT.write_text(text, encoding='utf-8')
            watch.PENDING.write_text(json.dumps({'ids': [row['id'] for row in rows]}), encoding='utf-8')
            watch.AUDIT.write_text(json.dumps(receipt, ensure_ascii=False), encoding='utf-8')
            with self.assertRaisesRegex(RuntimeError, 'WAR_INTEGRITY_GATE'):
                integrity.verify_alert()

    def test_appeals_do_not_hide_separate_operations_or_implemented_ceasefire(self):
        for title in ('Lavrov calls for resumption of Yemen negotiations',
                      '라브로프, 호르무즈 항행 자유 회복 촉구'):
            with self.subTest(title=title):
                self.assertEqual(integrity.non_military_kind(article(title)), 'diplomatic_appeal')
        for title in ('Lavrov calls for negotiations; Russia launched airstrikes',
                      '라브로프, 항행 자유 회복 촉구…러시아 미사일 발사',
                      '라브로프, 협상 재개 촉구…양측 휴전 합의 발효'):
            with self.subTest(title=title):
                self.assertNotEqual(integrity.non_military_kind(article(title)), 'diplomatic_appeal')
        self.assertEqual(integrity.non_military_kind(article('Zelensky calls Trump')), 'diplomatic_contact')
        self.assertEqual(integrity.non_military_kind(article("Zelensky calls Trump's diesel deal a peace incentive")), 'diplomatic_statement')

    def test_postponement_and_casualty_boundaries_preserve_action_stage(self):
        for title in ('Saudi Arabia postpones event after Houthi attacks; Houthis launched new attacks',
                      '사우디 행사 연기…후티 미사일 발사'):
            with self.subTest(title=title):
                self.assertNotEqual(integrity.non_military_kind(article(title)), 'operational_disruption')
        for title in ('러 대규모 공습에 우크라 사상자 속출 가능성',
                      '러 공습 사상자 조사보고서 공표 연기',
                      '후티 미사일 공격에 53명 사망 보도 부인',
                      '후티 미사일 공격에 53명 사망 예상',
                      '미국, 후티 미사일 공격에 53명 사망한 사건 규탄'):
            with self.subTest(title=title):
                self.assertNotIn('공습·공격 피해 보도', integrity.topic_label(article(title)))

    def test_only_appeal_and_postponement_verdict_has_no_implemented_peace(self):
        fixture, now = self.demands_disruption_fixture()
        rows = fixture['articles'][1:3]
        with patch.object(integrity.body_parallel, '_safe_enrich'), patch.object(watch, 'market_source_status', fixture['market_source_status'], create=True):
            text = integrity.build_alert(rows, fixture['markets'], now)
        self.assertTrue(all(integrity.non_military_kind(row) for row in rows))
        self.assertNotIn('🟢', text)
        self.assertNotIn('신규 변화의 중심은 실제 공격', text)
        self.assertIn('별도 확인', text)
        self.assertEqual(('<b>투자 판정</b>' + text.split('<b>투자 판정</b>', 1)[1]).strip(), integrity.verdict(rows).strip())

    def test_actual_information_resumption_reaction_is_not_energy_ceasefire(self):
        fixture, _ = self.summit_support_fixture()
        row = fixture['articles'][3]
        self.assertEqual(integrity.non_military_kind(row), 'support_statement')
        self.assertEqual(integrity.final_color(row), 'yellow')
        self.assertEqual(integrity.topic_label(row), '미국·우크라이나·러시아 · 정보 제공·공유 재개 보도')

    def test_actual_summit_proposals_preserve_three_parties_and_proposal_stage(self):
        fixture, _ = self.summit_support_fixture()
        for index in (0, 1, 2, 6):
            with self.subTest(index=index):
                row = fixture['articles'][index]
                self.assertEqual(integrity.non_military_kind(row), 'diplomatic_plan')
                self.assertEqual(integrity.final_color(row), 'yellow')
                self.assertEqual(integrity.topic_label(row), '미국·중국·러시아 · 정상회담 제안·논의')

    def test_information_policy_score_clears_cached_energy_event(self):
        fixture, now = self.summit_support_fixture()
        row = fixture['articles'][3]
        expected_score, _ = integrity.source_score._original_score(copy.deepcopy(row), now)
        score, tags = integrity.score_item(row, now)
        self.assertEqual(score, expected_score)
        self.assertEqual(tags, [integrity.KIND_LABELS['support_statement']])
        self.assertEqual(row['tags'], tags)
        self.assertFalse(row.get('signals_ko') or row.get('forced_tags'))
        self.assertNotIn('newidea_marks', row)
        self.assertNotIn('deep_signal', row)

    def test_actual_summit_support_render_retains_titles_and_full_final_gate(self):
        fixture, now = self.summit_support_fixture()
        rows = [row for row in fixture['articles'] if row['rendered']]
        with patch.object(integrity.body_parallel, '_safe_enrich'), patch.object(watch, 'market_source_status', fixture['market_source_status'], create=True):
            text = integrity.build_alert(rows, fixture['markets'], now)
        self.assertEqual([row['classification_color'] for row in rows], ['yellow'] * 4)
        self.assertEqual(text.count('미국·중국·러시아 · 정상회담 제안·논의'), 3)
        for row in rows:
            self.assertIn(html.escape(row['title_original']), text)
            self.assertFalse(row.get('signals_ko') or row.get('forced_tags'))
            self.assertEqual(row['tags'], [integrity.KIND_LABELS[integrity.non_military_kind(row)]])
        self.assertNotIn('에너지 휴전 발표', text)
        self.assertNotIn('신규 변화의 중심은 실제 공격', text)
        self.assertNotIn('🟢', text)
        self.assertIn('제목 기준·본문 미확인', text)
        receipt = evidence.alert_receipt(rows, fixture['markets'], now, text)
        with tempfile.TemporaryDirectory() as folder, ExitStack() as stack:
            for attr, name in {'ALERT': 'alert.txt', 'PENDING': 'pending.json', 'AUDIT': 'evidence.json'}.items():
                stack.enter_context(patch.object(watch, attr, Path(folder)/name))
            watch.ALERT.write_text(text, encoding='utf-8')
            watch.PENDING.write_text(json.dumps({'ids': [row['id'] for row in rows]}), encoding='utf-8')
            watch.AUDIT.write_text(json.dumps(receipt, ensure_ascii=False), encoding='utf-8')
            integrity.verify_alert()

    def test_final_gate_rejects_actual_same_hash_summit_support_wrong_topics(self):
        fixture, now = self.summit_support_fixture()
        rows = [row for row in fixture['articles'] if row['rendered']]
        text = fixture['sent_alert'].strip()
        receipt = evidence.alert_receipt(rows, fixture['markets'], now, text)
        self.assertEqual(receipt['alert_sha256'], fixture['provenance']['alert_sha256'])
        with tempfile.TemporaryDirectory() as folder, ExitStack() as stack:
            for attr, name in {'ALERT': 'alert.txt', 'PENDING': 'pending.json', 'AUDIT': 'evidence.json'}.items():
                stack.enter_context(patch.object(watch, attr, Path(folder)/name))
            watch.ALERT.write_text(text, encoding='utf-8')
            watch.PENDING.write_text(json.dumps({'ids': [row['id'] for row in rows]}), encoding='utf-8')
            watch.AUDIT.write_text(json.dumps(receipt, ensure_ascii=False), encoding='utf-8')
            with self.assertRaisesRegex(RuntimeError, 'WAR_INTEGRITY_GATE'):
                integrity.verify_alert()

    def test_full_candidate_verdict_uses_only_four_rendered_headlines(self):
        fixture, now = self.summit_support_fixture()
        rows = fixture['articles']
        with patch.object(integrity.body_parallel, '_safe_enrich'), patch.object(watch, 'market_source_status', fixture['market_source_status'], create=True):
            text = integrity.build_alert(rows, fixture['markets'], now)
        receipt = evidence.alert_receipt(rows, fixture['markets'], now, text)
        shown = [row for row in receipt['articles'] if row['rendered']]
        self.assertEqual([row['id'] for row in shown], [row['id'] for row in rows[:4]])
        self.assertEqual([row['classification_color'] for row in shown], ['yellow'] * 4)
        self.assertEqual(('<b>투자 판정</b>' + text.split('<b>투자 판정</b>', 1)[1]).strip(), integrity.verdict(shown).strip())
        self.assertNotIn('신규 변화의 중심은 실제 공격', text)
        with tempfile.TemporaryDirectory() as folder, ExitStack() as stack:
            for attr, name in {'ALERT': 'alert.txt', 'PENDING': 'pending.json', 'AUDIT': 'evidence.json'}.items():
                stack.enter_context(patch.object(watch, attr, Path(folder)/name))
            watch.ALERT.write_text(text, encoding='utf-8')
            watch.PENDING.write_text(json.dumps({'ids': [row['id'] for row in shown]}), encoding='utf-8')
            watch.AUDIT.write_text(json.dumps(receipt, ensure_ascii=False), encoding='utf-8')
            integrity.verify_alert()

    def test_final_gate_rejects_attack_verdict_after_correct_diplomatic_items(self):
        fixture, now = self.summit_support_fixture()
        rows = [row for row in fixture['articles'] if row['rendered']]
        with patch.object(integrity.body_parallel, '_safe_enrich'), patch.object(watch, 'market_source_status', fixture['market_source_status'], create=True):
            text = integrity.build_alert(rows, fixture['markets'], now)
        text = text.split('<b>투자 판정</b>', 1)[0] + '<b>투자 판정</b>' + fixture['sent_alert'].split('<b>투자 판정</b>', 1)[1]
        receipt = evidence.alert_receipt(rows, fixture['markets'], now, text)
        with tempfile.TemporaryDirectory() as folder, ExitStack() as stack:
            for attr, name in {'ALERT': 'alert.txt', 'PENDING': 'pending.json', 'AUDIT': 'evidence.json'}.items():
                stack.enter_context(patch.object(watch, attr, Path(folder)/name))
            watch.ALERT.write_text(text, encoding='utf-8')
            watch.PENDING.write_text(json.dumps({'ids': [row['id'] for row in rows]}), encoding='utf-8')
            watch.AUDIT.write_text(json.dumps(receipt, ensure_ascii=False), encoding='utf-8')
            with self.assertRaisesRegex(RuntimeError, 'WAR_INTEGRITY_GATE.*verdict'):
                integrity.verify_alert()

    def test_information_resumption_keeps_denial_and_separate_actual_actions(self):
        for title in ('젤렌스키, 美 정보 제공 재개에 감사·러시아 정책에는 우려',
                      '미국, 우크라 군사 정보 공유 재개 보도 부인',
                      'Zelensky thanks U.S. for resuming intelligence sharing, worries about Russia policy'):
            with self.subTest(title=title):
                self.assertEqual(integrity.non_military_kind(article(title)), 'support_statement')
        for title in ('젤렌스키, 미국 정보 제공 재개에 감사…러시아 미사일 발사',
                      '미국 정보 공유 재개…우크라이나 러 정유시설 공습 재개',
                      '젤렌스키, 미국 정보 공유 재개에 감사…양측 휴전 합의 발효',
                      'Zelensky thanks U.S. for resuming intelligence sharing; Russia launched airstrikes'):
            with self.subTest(title=title):
                self.assertNotEqual(integrity.non_military_kind(article(title)), 'support_statement')

    def test_summit_proposals_keep_contact_and_completed_operation_boundaries(self):
        for title in ('푸틴, 트럼프·시진핑에 3자 정상회담 제안',
                      '트럼프, 푸틴·시진핑과 정상회담 개최 논의',
                      'Putin proposes three-way summit with Trump and Xi'):
            with self.subTest(title=title):
                self.assertEqual(integrity.non_military_kind(article(title)), 'diplomatic_plan')
                self.assertIn('미국·중국·러시아', integrity.topic_label(article(title)))
        for title in ('트럼프·푸틴, 정상회담 개최',
                      '트럼프·시진핑·푸틴 정상회담 제안…러시아 미사일 발사',
                      '트럼프·시진핑·푸틴 정상회담 제안…양측 휴전 합의 발효'):
            with self.subTest(title=title):
                self.assertNotEqual(integrity.non_military_kind(article(title)), 'diplomatic_plan')

    def test_actual_talk_restart_plan_is_not_implemented_peace(self):
        fixture, _ = self.talk_plan_drone_fixture()
        row = fixture['articles'][0]
        self.assertEqual(integrity.non_military_kind(row), 'diplomatic_plan')
        self.assertEqual(integrity.final_color(row), 'yellow')
        self.assertIn('협상 추진·논의', integrity.topic_label(row))

    def test_actual_preference_for_Russian_participation_is_not_implemented_peace(self):
        fixture, _ = self.talk_plan_drone_fixture()
        row = fixture['articles'][4]
        self.assertEqual(integrity.non_military_kind(row), 'diplomatic_position')
        self.assertEqual(integrity.final_color(row), 'yellow')
        self.assertEqual(integrity.topic_label(row), '미국·러시아 · 외교 갈등·압박 보도')

    def test_full_saved_candidates_do_not_promote_next_negotiation_preference(self):
        fixture, now = self.talk_plan_drone_fixture()
        with patch.object(integrity.body_parallel, '_safe_enrich'), patch.object(watch, 'market_source_status', fixture['market_source_status'], create=True):
            text = integrity.build_alert(fixture['articles'], fixture['markets'], now)
        self.assertIn(html.escape(fixture['articles'][4]['title_original']), text)
        self.assertEqual(fixture['articles'][4]['classification_color'], 'yellow')
        self.assertNotIn('🟢', text)
        self.assertNotIn('에너지 휴전 발표', text)
        self.assertFalse(quality._alert_quality_issues(text))

    def test_actual_calls_deal_a_name_is_not_phone_contact(self):
        fixture, _ = self.talk_plan_drone_fixture()
        row = fixture['articles'][1]
        self.assertEqual(integrity.non_military_kind(row), 'diplomatic_statement')
        self.assertEqual(integrity.final_color(row), 'yellow')
        self.assertIn('거래·정책 평가 발언', integrity.topic_label(row))

    def test_actual_drone_airstrike_overrides_background_ceasefire(self):
        fixture, _ = self.talk_plan_drone_fixture()
        row = fixture['articles'][3]
        self.assertIsNone(integrity.non_military_kind(row))
        self.assertEqual(integrity.final_color(row), 'red')
        self.assertEqual(integrity.topic_label(row), '우크라이나·러시아 · 드론 공습 보도')

    def test_diplomatic_source_score_does_not_bypass_three_hour_limit(self):
        fixture, now = self.talk_plan_drone_fixture()
        self.assertGreater(watch.age_minutes(fixture['articles'][1], now), 180)
        self.assertEqual(integrity.score_item(fixture['articles'][1], now), (0, []))

    def test_actual_rejected_inputs_keep_headlines_and_drop_stale_discovery(self):
        fixture, now = self.talk_plan_drone_fixture()
        rows = [row for row in fixture['articles'] if row['rendered']]
        with patch.object(integrity.body_parallel, '_safe_enrich'), patch.object(watch, 'market_source_status', fixture['market_source_status'], create=True):
            text = integrity.build_alert(rows, fixture['markets'], now)
        receipt = evidence.alert_receipt(rows, fixture['markets'], now, text)
        shown = [row for row in receipt['articles'] if row['rendered']]
        self.assertEqual([row['id'] for row in shown], [rows[i]['id'] for i in (0, 2, 3)])
        self.assertEqual([row['classification_color'] for row in shown], ['yellow', 'yellow', 'red'])
        for row in shown:
            self.assertIn(html.escape(row['title_original']), text)
            self.assertFalse(row.get('signals_ko') or row.get('forced_tags'))
        self.assertNotIn('🟢', text)
        self.assertNotIn('에너지 휴전 발표', text)
        self.assertNotIn('협상 재개 의사를 공개적으로 확인', text)
        self.assertEqual(rows[1]['render_withheld'], 'discovery_publication_stale')
        self.assertFalse(quality._alert_quality_issues(text))
        with tempfile.TemporaryDirectory() as folder, ExitStack() as stack:
            for attr, name in {'ALERT': 'alert.txt', 'PENDING': 'pending.json', 'AUDIT': 'evidence.json'}.items():
                stack.enter_context(patch.object(watch, attr, Path(folder)/name))
            watch.ALERT.write_text(text, encoding='utf-8')
            watch.PENDING.write_text(json.dumps({'ids': [row['id'] for row in shown]}), encoding='utf-8')
            watch.AUDIT.write_text(json.dumps(receipt, ensure_ascii=False), encoding='utf-8')
            integrity.verify_alert()

    def test_final_gate_rechecks_stale_discovery_independent_of_age_label(self):
        fixture, now = self.talk_plan_drone_fixture()
        row = fixture['articles'][1]
        with patch.object(integrity.body_parallel, '_safe_enrich'):
            text = integrity.build_alert([row], [], now - dt.timedelta(hours=4))
        self.assertTrue(text)
        receipt = evidence.alert_receipt([row], [], now, text)
        with tempfile.TemporaryDirectory() as folder, ExitStack() as stack:
            for attr, name in {'ALERT': 'alert.txt', 'PENDING': 'pending.json', 'AUDIT': 'evidence.json'}.items():
                stack.enter_context(patch.object(watch, attr, Path(folder)/name))
            watch.ALERT.write_text(text, encoding='utf-8')
            watch.PENDING.write_text(json.dumps({'ids': [row['id']]}), encoding='utf-8')
            watch.AUDIT.write_text(json.dumps(receipt, ensure_ascii=False), encoding='utf-8')
            stack.enter_context(patch.object(integrity, '_verify'))
            with self.assertRaisesRegex(RuntimeError, 'WAR_INTEGRITY_GATE.*stale discovery'):
                integrity.verify_alert()

    def test_final_gate_rechecks_actual_wrong_plan_contact_and_drone_topics(self):
        fixture, now = self.talk_plan_drone_fixture()
        rows = fixture['articles']
        text = fixture['rejected_alert'].strip()
        receipt = evidence.alert_receipt(rows, fixture['markets'], now, text)
        self.assertEqual(receipt['alert_sha256'], fixture['provenance']['alert_sha256'])
        for index in (0, 1, 3):
            with self.subTest(id=rows[index]['id']), tempfile.TemporaryDirectory() as folder, ExitStack() as stack:
                # Isolate each stored topic from the earlier global quality gate.
                one = copy.deepcopy(receipt)
                one['articles'] = [row for row in one['articles'] if not row['rendered'] or row['id'] == rows[index]['id']]
                blocks = text.splitlines()
                starts = [i for i, line in enumerate(blocks) if '[신규]' in line or '[후속]' in line or '[속보]' in line]
                start = starts[index]
                end = starts[index+1] if index+1 < len(starts) else next(i for i in range(start+1, len(blocks)) if blocks[i] == '<b>투자 판정</b>')
                isolated = '\n'.join(blocks[start:end])
                one['alert_sha256'] = hashlib.sha256(isolated.encode()).hexdigest()
                for attr, name in {'ALERT': 'alert.txt', 'PENDING': 'pending.json', 'AUDIT': 'evidence.json'}.items():
                    stack.enter_context(patch.object(watch, attr, Path(folder)/name))
                watch.ALERT.write_text(isolated, encoding='utf-8')
                watch.PENDING.write_text(json.dumps({'ids': [rows[index]['id']]}), encoding='utf-8')
                watch.AUDIT.write_text(json.dumps(one, ensure_ascii=False), encoding='utf-8')
                stack.enter_context(patch.object(integrity, '_verify'))
                with self.assertRaisesRegex(RuntimeError, 'WAR_INTEGRITY_GATE'):
                    integrity.verify_alert()

    def test_talk_plans_label_calls_and_actual_operations_keep_separate_stages(self):
        for title, kind in (
            ('젤렌스키, 이번 주 평화협상 재개 추진…푸틴 회동 논의', 'diplomatic_plan'),
            ('젤렌스키, 평화협상 재개 안 해…푸틴 회동 논의도 거부', 'diplomatic_plan'),
            ('Zelensky plans to resume peace talks; Putin meeting under discussion', 'diplomatic_plan'),
            ("Wright calls Trump's diesel deal a peace incentive. Rubio disagrees.", 'diplomatic_statement'),
            ('Wright calls Trump to discuss a diesel deal', 'diplomatic_contact'),
        ):
            with self.subTest(title=title):
                self.assertEqual(integrity.non_military_kind(article(title)), kind)
                self.assertEqual(integrity.final_color(article(title)), 'yellow')
        for title in ('우크라, 드론 1000대로 러시아 공습…트럼프와 통화',
                      '우크라, 드론 1000대로 러시아 공습…평화협상 재개 논의'):
            with self.subTest(title=title):
                self.assertIsNone(integrity.non_military_kind(article(title)))
                self.assertEqual(integrity.final_color(article(title)), 'red')
        bilateral = article('러시아·우크라이나, 평화협상 끝에 양측 휴전 합의 발효')
        self.assertIsNone(integrity.non_military_kind(bilateral))
        self.assertEqual(integrity.final_color(bilateral), 'green')
        self.assertNotEqual(integrity.non_military_kind(article("Zelensky calls Trump's proposal unacceptable")), 'diplomatic_contact')

    def test_drone_attack_denial_plan_analysis_and_report_are_not_actual_action(self):
        for title in ('우크라, 드론 1000대로 러시아 공습 계획',
                      '우크라 드론 1000대 러시아 공습 재개 논의',
                      '우크라, 드론 1000대로 러시아 공습한 적 없다고 부인',
                      '우크라 드론 1000대 러시아 공습 가능성 검토',
                      '우크라 드론 1000대 러시아 공습 왜? [해설]',
                      '우크라 드론 1000대 러시아 공습 조사보고서 공개'):
            with self.subTest(title=title):
                self.assertFalse(integrity._headline_drone_action(article(title)))


    def test_actual_envoy_call_is_not_a_new_peace_commitment(self):
        row = self.diplomatic_contact_fixture()[0]['articles'][0]
        self.assertEqual(integrity.non_military_kind(row), 'diplomatic_contact')
        self.assertEqual(integrity.final_color(row), 'yellow')
        self.assertEqual(integrity.topic_label(row), '미국·우크라이나 · 외교 접촉 보도')

    def test_actual_worldview_is_diplomatic_analysis_not_energy_ceasefire(self):
        row = self.diplomatic_contact_fixture()[1]['articles'][0]
        self.assertEqual(integrity.non_military_kind(row), 'diplomatic_analysis')
        self.assertEqual(integrity.topic_label(row), '미국·우크라이나 · 외교·안보 해설')

    def test_actual_surrender_pressure_reaction_is_not_energy_ceasefire(self):
        row = self.diplomatic_contact_fixture()[1]['articles'][2]
        self.assertEqual(integrity.non_military_kind(row), 'diplomatic_position')
        self.assertEqual(integrity.topic_label(row), '미국·우크라이나·러시아 · 외교 갈등·압박 보도')

    def test_actual_diplomatic_inputs_keep_full_headlines_and_clear_background(self):
        for fixture in self.diplomatic_contact_fixture():
            with self.subTest(run=fixture['provenance']['run_id']):
                rows = fixture['articles']
                now = dt.datetime.fromisoformat(fixture['provenance']['queried_at_kst'])
                with patch.object(integrity.body_parallel, '_safe_enrich'), patch.object(watch, 'market_source_status', fixture['market_source_status'], create=True):
                    text = integrity.build_alert(rows, fixture['markets'], now)
                for row in rows:
                    self.assertIn(html.escape(integrity._display_headline(row)), text)
                    if integrity.non_military_kind(row) in ('diplomatic_contact', 'diplomatic_analysis', 'diplomatic_position'):
                        self.assertFalse(row.get('signals_ko') or row.get('forced_tags'))
                        self.assertEqual(row['tags'], [integrity.KIND_LABELS[integrity.non_military_kind(row)]])
                expected = ['yellow', 'red'] if len(rows) == 2 else ['yellow', 'yellow', 'yellow']
                self.assertEqual([row['classification_color'] for row in rows], expected)
                self.assertNotIn('에너지 휴전 발표', text)
                self.assertNotIn('협상 재개 의사를 공개적으로 확인', text)
                self.assertNotIn('🟢', text)
                if len(rows) == 3:
                    self.assertIn('접촉·갈등·해설', text)
                receipt = evidence.alert_receipt(rows, fixture['markets'], now, text)
                with tempfile.TemporaryDirectory() as folder, ExitStack() as stack:
                    for attr, name in {'ALERT': 'alert.txt', 'PENDING': 'pending.json', 'AUDIT': 'evidence.json'}.items():
                        stack.enter_context(patch.object(watch, attr, Path(folder)/name))
                    watch.ALERT.write_text(text, encoding='utf-8')
                    watch.PENDING.write_text(json.dumps({'ids': [row['id'] for row in rows]}), encoding='utf-8')
                    watch.AUDIT.write_text(json.dumps(receipt, ensure_ascii=False), encoding='utf-8')
                    integrity.verify_alert()

    def test_final_gate_rejects_same_hash_actual_diplomatic_wrong_topics(self):
        for fixture in self.diplomatic_contact_fixture():
            with self.subTest(run=fixture['provenance']['run_id']), tempfile.TemporaryDirectory() as folder, ExitStack() as stack:
                for attr, name in {'ALERT': 'alert.txt', 'PENDING': 'pending.json', 'AUDIT': 'evidence.json'}.items():
                    stack.enter_context(patch.object(watch, attr, Path(folder)/name))
                rows = fixture['articles']
                now = dt.datetime.fromisoformat(fixture['provenance']['queried_at_kst'])
                text = fixture['actual_alert'].strip()
                receipt = evidence.alert_receipt(rows, fixture['markets'], now, text)
                self.assertEqual(receipt['alert_sha256'], fixture['provenance']['alert_sha256'])
                watch.ALERT.write_text(text, encoding='utf-8')
                watch.PENDING.write_text(json.dumps({'ids': [row['id'] for row in rows]}), encoding='utf-8')
                watch.AUDIT.write_text(json.dumps(receipt, ensure_ascii=False), encoding='utf-8')
                with self.assertRaisesRegex(RuntimeError, 'WAR_INTEGRITY_GATE'):
                    integrity.verify_alert()

    def test_diplomatic_contact_and_pressure_language_boundaries(self):
        for title, kind in (
            ('젤렌스키, 미국 특사 위트코프·쿠슈너와 통화…양국 갈등 논의', 'diplomatic_contact'),
            ('Zelensky talks with U.S. envoys about Ukraine crisis', 'diplomatic_contact'),
            ('Zelensky calls Witkoff amid U.S.-Ukraine crisis', 'diplomatic_contact'),
            ('젤렌스키, 미국의 항복 압박에 반발', 'diplomatic_position'),
            ('[월드뷰] 미국 외교 기조와 우크라이나 불확실성', 'diplomatic_analysis'),
        ):
            with self.subTest(title=title):
                self.assertEqual(integrity.non_military_kind(article(title)), kind)
                self.assertEqual(integrity.final_color(article(title)), 'yellow')

    def test_separate_actual_attack_and_explicit_peace_are_not_contact(self):
        for title in (
            '젤렌스키, 미국 특사와 통화…러시아 미사일 발사',
            '[월드뷰] 미국 외교 기조 변화…러시아 공습 재개',
            'Zelensky speaks to Witkoff; Russia launched airstrikes',
            '젤렌스키, 미국 특사와 통화…양측 휴전 합의 발효',
            'Zelensky calls for military aid from U.S.',
        ):
            with self.subTest(title=title):
                self.assertNotIn(integrity.non_military_kind(article(title)), ('diplomatic_contact', 'diplomatic_analysis', 'diplomatic_position'))

    def test_actual_gas_import_proposal_is_not_implemented_peace(self):
        fixture, _ = self.maritime_proposal_fixture()
        row = fixture['articles'][1]
        self.assertEqual(integrity.non_military_kind(row), 'trade_proposal')
        self.assertEqual(integrity.final_color(row), 'yellow')
        self.assertEqual(integrity.topic_label(row), '우크라이나·러시아 · 에너지 거래 재개 제안')

    def test_actual_maritime_headline_is_not_a_specific_UKMTO_template(self):
        fixture, now = self.maritime_proposal_fixture()
        row = fixture['articles'][0]
        with patch.object(integrity.body_parallel, '_safe_enrich'):
            text = integrity.build_alert([row], [], now)
        self.assertIn(html.escape(row['title_original']), text)
        self.assertNotIn('UKMTO', text)
        self.assertNotIn('미확인 발사체', text)
        self.assertNotIn('피격이 반복', text)
        self.assertFalse(row.get('signals_ko') or row.get('forced_tags'))
        self.assertEqual(row['classification_color'], 'red')

    def test_actual_three_item_render_retains_titles_stages_and_body_limits(self):
        fixture, now = self.maritime_proposal_fixture()
        rows = fixture['articles']
        before = watch.STATE.read_bytes()
        with patch.object(integrity.body_parallel, '_safe_enrich'), patch.object(watch, 'market_source_status', fixture['market_source_status'], create=True):
            text = integrity.build_alert(rows, fixture['markets'], now)
        for row in rows:
            self.assertIn(html.escape(row['title_original']), text)
        self.assertEqual([row['classification_color'] for row in rows], ['red', 'yellow', ''])
        self.assertNotIn('🟢', text)
        self.assertIn('제목 기준·본문 미확인', text)
        self.assertEqual(rows[1]['source_metadata']['published_at_kst'], '2026-10-18T14:29:41+09:00')
        receipt = evidence.alert_receipt(rows, fixture['markets'], now, text)
        with tempfile.TemporaryDirectory() as folder, ExitStack() as stack:
            root = Path(folder)
            for attr, name in {'ALERT': 'alert.txt', 'PENDING': 'pending.json', 'AUDIT': 'evidence.json'}.items():
                stack.enter_context(patch.object(watch, attr, root/name))
            watch.ALERT.write_text(text, encoding='utf-8')
            watch.PENDING.write_text(json.dumps({'ids': [row['id'] for row in rows]}), encoding='utf-8')
            watch.AUDIT.write_text(json.dumps(receipt, ensure_ascii=False), encoding='utf-8')
            integrity.verify_alert()
        self.assertEqual(watch.STATE.read_bytes(), before)

    def test_final_gate_rejects_actual_same_hash_UKMTO_green_proposal_body(self):
        fixture, now = self.maritime_proposal_fixture()
        rows = fixture['articles']; text = fixture['actual_alert'].strip()
        receipt = evidence.alert_receipt(rows, fixture['markets'], now, text)
        self.assertEqual(receipt['alert_sha256'], fixture['provenance']['alert_sha256'])
        with tempfile.TemporaryDirectory() as folder, ExitStack() as stack:
            root = Path(folder)
            for attr, name in {'ALERT': 'alert.txt', 'PENDING': 'pending.json', 'AUDIT': 'evidence.json'}.items():
                stack.enter_context(patch.object(watch, attr, root/name))
            watch.ALERT.write_text(text, encoding='utf-8')
            watch.PENDING.write_text(json.dumps({'ids': [row['id'] for row in rows]}), encoding='utf-8')
            watch.AUDIT.write_text(json.dumps(receipt, ensure_ascii=False), encoding='utf-8')
            with self.assertRaisesRegex(RuntimeError, 'WAR_INTEGRITY_GATE'):
                integrity.verify_alert()

    def test_trade_proposal_requires_energy_trade_and_a_proposal(self):
        for title in ('美, 유럽에 러시아산 천연가스 수입재개 제안',
                      '미국, 러시아 가스관 재가동 추진…유럽 거부',
                      'US proposes resuming Russian natural gas imports to Europe'):
            with self.subTest(title=title):
                self.assertEqual(integrity.non_military_kind(article(title)), 'trade_proposal')
                self.assertEqual(integrity.final_color(article(title)), 'yellow')
        for title in ('유럽, 러시아산 천연가스 수입 재개했다', '미국, 선거제도 변경 제안',
                      '러시아산 천연가스 가격 상승', '미국, 에너지 시설 공습 재개'):
            with self.subTest(title=title):
                self.assertNotEqual(integrity.non_military_kind(article(title)), 'trade_proposal')

    def test_trade_proposal_preserves_separate_attack_and_implemented_ceasefire(self):
        for title in ('美, 러시아 가스 수입 재개 제안…이스라엘 공습 개시',
                      'US proposes Russian gas imports and launches airstrikes'):
            with self.subTest(title=title):
                self.assertIsNone(integrity.non_military_kind(article(title)))
                self.assertEqual(integrity.final_color(article(title)), 'red')
        row = article('러시아 가스 수입 재개 제안…양측 휴전 이행 중')
        self.assertNotEqual(integrity.non_military_kind(row), 'trade_proposal')

    def test_single_trade_proposal_verdict_does_not_claim_peace_implementation(self):
        fixture, now = self.maritime_proposal_fixture()
        row = fixture['articles'][1]
        row.update(signals_ko=['새 휴전 이행'], forced_tags=['휴전·평화'], tags=['휴전·평화'])
        with patch.object(integrity.body_parallel, '_safe_enrich'):
            text = integrity.build_alert([row], [], now)
        self.assertIn(html.escape(row['title_original']), text)
        self.assertIn('제안·검토 단계', text)
        self.assertIn('양측 휴전 이행을 뜻하지 않음', text)
        self.assertNotIn('🟢', text)
        self.assertFalse(row.get('signals_ko') or row.get('forced_tags'))

    def test_maritime_current_title_counts_and_UKMTO_attribution_retained(self):
        for title in ('호르무즈 유조선 피격…테헤란 재개방안 제시',
                      'UKMTO, 오만 유조선 피격 2건 보고'):
            row = article(title)
            row.update(signals_ko=['옛 유조선 사건 요약'], forced_tags=['유조선피격'])
            with self.subTest(title=title), patch.object(integrity.body_parallel, '_safe_enrich'):
                text = integrity.build_alert([row], [], NOW)
            self.assertIn(html.escape(title), text)
            self.assertNotIn('옛 유조선 사건 요약', text)

    def test_ship_tally_remains_distinct_from_single_ship_report(self):
        row = article('호르무즈 피격 선박 2주에 24척, 개전 이후 최대 규모')
        self.assertTrue(integrity.maritime_attack_tally(row))
        self.assertEqual(integrity.topic_label(row), '호르무즈 · 선박 피격 집계 보도')

    def test_actual_marked_dilemma_headline_is_military_analysis(self):
        fixture, _ = self.marked_analysis_fixture()
        row = fixture['articles'][0]
        self.assertEqual(integrity.non_military_kind(row), 'military_analysis')
        self.assertEqual(integrity.final_color(row), 'yellow')
        self.assertEqual(integrity.topic_label(row), '사우디·후티 · 군사·안보 해설')

    def test_marked_analysis_preserves_separate_actual_military_actions(self):
        for action in ('사우디 공습 재개', '후티 미사일 발사', '후티 미사일 2발 발사',
                       '사우디 미사일 요격했다', '후티가 사우디를 공격했다',
                       '사우디 공습 진행 중', '사우디 정유시설 피격됐다'):
            row = article('후티 공습에 딜레마 빠진 사우디…' + action + ' [디브리핑]')
            with self.subTest(action=action):
                self.assertIsNone(integrity.non_military_kind(row))
                self.assertEqual(integrity.final_color(row), 'red')

    def test_marked_analysis_requires_both_editorial_marker_and_context(self):
        for title in ('후티 공습에 딜레마 빠진 사우디',
                      '후티 사우디 공습 [디브리핑]',
                      '사우디 경제 딜레마 [디브리핑]'):
            with self.subTest(title=title):
                self.assertNotEqual(integrity.non_military_kind(article(title)), 'military_analysis')

    def test_actual_marked_analysis_render_clears_attack_cache_and_preserves_limits(self):
        fixture, now = self.marked_analysis_fixture()
        rows = fixture['articles']; row = rows[0]
        row.update(forced_tags=['확전'], signals_ko=['새로운 실제 공격'],
                   deep_signal='공격 확대', newidea_marks=['공격 확대'])
        before = watch.STATE.read_bytes()
        with patch.object(integrity.body_parallel, '_safe_enrich'), patch.object(watch, 'market_source_status', fixture['market_source_status'], create=True):
            text = integrity.build_alert(rows, fixture['markets'], now)
        self.assertEqual(row['classification_color'], 'yellow')
        self.assertIn(html.escape(row['title_original']), text)
        self.assertIn('군사·안보 해설', text)
        self.assertIn('본문 미확인', text)
        self.assertNotIn('신규 변화의 중심은 실제 공격', text)
        self.assertNotIn(' · 확전 · ', text)
        self.assertFalse(row.get('signals_ko') or row.get('forced_tags') or row.get('deep_signal') or row.get('newidea_marks'))
        receipt = evidence.alert_receipt(rows, fixture['markets'], now, text)
        with tempfile.TemporaryDirectory() as folder, ExitStack() as stack:
            root = Path(folder)
            for attr, name in {'ALERT': 'alert.txt', 'PENDING': 'pending.json', 'AUDIT': 'evidence.json'}.items():
                stack.enter_context(patch.object(watch, attr, root/name))
            watch.ALERT.write_text(text, encoding='utf-8')
            watch.PENDING.write_text(json.dumps({'ids': [row['id']]}), encoding='utf-8')
            watch.AUDIT.write_text(json.dumps(receipt, ensure_ascii=False), encoding='utf-8')
            integrity.verify_alert()
        self.assertEqual(watch.STATE.read_bytes(), before)

    def test_final_gate_rejects_actual_same_hash_marked_analysis_red_body(self):
        fixture, now = self.marked_analysis_fixture()
        rows = fixture['articles']; text = fixture['actual_alert'].strip()
        receipt = evidence.alert_receipt(rows, fixture['markets'], now, text)
        self.assertEqual(receipt['alert_sha256'], fixture['provenance']['alert_sha256'])
        with tempfile.TemporaryDirectory() as folder, ExitStack() as stack:
            root = Path(folder)
            for attr, name in {'ALERT': 'alert.txt', 'PENDING': 'pending.json', 'AUDIT': 'evidence.json'}.items():
                stack.enter_context(patch.object(watch, attr, root/name))
            watch.ALERT.write_text(text, encoding='utf-8')
            watch.PENDING.write_text(json.dumps({'ids': [row['id'] for row in rows]}), encoding='utf-8')
            watch.AUDIT.write_text(json.dumps(receipt, ensure_ascii=False), encoding='utf-8')
            with self.assertRaisesRegex(RuntimeError, 'WAR_INTEGRITY_GATE'):
                integrity.verify_alert()

    def test_actual_refinery_restart_condemnation_is_diplomatic_reaction(self):
        fixture, _ = self.condemnation_shipping_fixture()
        row = fixture['articles'][0]
        self.assertEqual(integrity.non_military_kind(row), 'reaction')
        self.assertEqual(integrity.final_color(row), 'yellow')
        self.assertEqual(integrity.topic_label(row), '미국·우크라이나·러시아 · 외교반응·개입검토')

    def test_condemnation_object_scope_does_not_hide_separate_actual_action(self):
        for title in ('트럼프, 우크라이나의 러시아 정유 시설 공격 재개를 비난했다',
                      '미국, 이란의 미사일 발사를 규탄했다',
                      'Trump condemned the resumption of Ukrainian refinery attacks',
                      'Trump denounced the resumption of Ukrainian refinery attacks'):
            with self.subTest(title=title):
                self.assertEqual(integrity.non_military_kind(article(title)), 'reaction')
                self.assertEqual(integrity.final_color(article(title)), 'yellow')
        for title in ('트럼프, 정유시설 공격 재개를 비난…이스라엘 공습 개시',
                      '우크라이나 러 정유시설 공격 재개했다…트럼프 비난',
                      '트럼프 비난에도 우크라이나 러 정유시설 공격 재개',
                      'Trump condemns Ukraine and launches airstrikes'):
            with self.subTest(title=title):
                self.assertIsNone(integrity.non_military_kind(article(title)))
                self.assertEqual(integrity.final_color(article(title)), 'red')
        row = article('우크라이나 러시아 에너지 시설 공격 재개를 발표했고 모스크바는 비난했다')
        self.assertEqual(integrity.non_military_kind(row), 'military_statement')

    def test_actual_blockade_fuel_shipments_are_not_a_new_military_attack(self):
        fixture, _ = self.condemnation_shipping_fixture()
        row = fixture['articles'][1]
        self.assertEqual(integrity.non_military_kind(row), 'fuel_shipping')
        self.assertEqual(integrity.final_color(row), 'yellow')
        self.assertEqual(integrity.topic_label(row), '미국·이란 · 봉쇄·연료 선적 보도')

    def test_fuel_shipments_preserve_a_separate_actual_military_action(self):
        row = article('이란 연료 선적, 미국 해군 봉쇄 위반…미국 공습 개시')
        self.assertIsNone(integrity.non_military_kind(row))
        self.assertEqual(integrity.final_color(row), 'red')
        self.assertNotEqual(integrity.non_military_kind(article('Iran launches attacks on fuel tankers despite blockade')), 'fuel_shipping')
        self.assertNotEqual(integrity.non_military_kind(article('이란 연료 가격 상승 전망')), 'fuel_shipping')

    def test_actual_condemnation_and_shipping_render_and_final_gate(self):
        fixture, now = self.condemnation_shipping_fixture()
        rows = fixture['articles']
        before = watch.STATE.read_bytes()
        with patch.object(integrity.body_parallel, '_safe_enrich'):
            text = integrity.build_alert(rows, fixture['markets'], now)
        self.assertEqual([r['classification_color'] for r in rows], ['yellow', 'yellow'])
        self.assertIn(html.escape(rows[0]['title_original']), text)
        for phrase in ('7월 이후', '최소 8척', '410만 배럴', '알려졌습니다', '가능성이 높습니다'):
            self.assertIn(phrase, text)
        self.assertNotIn(' · 확전 · ', text)
        self.assertNotIn('신규 변화의 중심은 실제 공격', text)
        self.assertEqual(text.count('본문 미확인'), 2)
        self.assertTrue(all(not r.get('signals_ko') and not r.get('forced_tags') for r in rows))
        receipt = evidence.alert_receipt(rows, fixture['markets'], now, text)
        with tempfile.TemporaryDirectory() as folder, ExitStack() as stack:
            root = Path(folder)
            for attr, name in {'ALERT': 'alert.txt', 'PENDING': 'pending.json', 'AUDIT': 'evidence.json'}.items():
                stack.enter_context(patch.object(watch, attr, root/name))
            watch.ALERT.write_text(text, encoding='utf-8')
            watch.PENDING.write_text(json.dumps({'ids': [r['id'] for r in rows]}), encoding='utf-8')
            watch.AUDIT.write_text(json.dumps(receipt, ensure_ascii=False), encoding='utf-8')
            integrity.verify_alert()
        self.assertEqual(watch.STATE.read_bytes(), before)

    def test_final_gate_rejects_actual_same_hash_condemnation_shipping_body(self):
        fixture, now = self.condemnation_shipping_fixture()
        rows = fixture['articles']; text = fixture['actual_alert'].strip()
        receipt = evidence.alert_receipt(rows, fixture['markets'], now, text)
        with tempfile.TemporaryDirectory() as folder, ExitStack() as stack:
            root = Path(folder)
            for attr, name in {'ALERT': 'alert.txt', 'PENDING': 'pending.json', 'AUDIT': 'evidence.json'}.items():
                stack.enter_context(patch.object(watch, attr, root/name))
            watch.ALERT.write_text(text, encoding='utf-8')
            watch.PENDING.write_text(json.dumps({'ids': [r['id'] for r in rows]}), encoding='utf-8')
            watch.AUDIT.write_text(json.dumps(receipt, ensure_ascii=False), encoding='utf-8')
            with self.assertRaisesRegex(RuntimeError, 'WAR_INTEGRITY_GATE'):
                integrity.verify_alert()

    def test_final_gate_requires_visible_unverified_body_for_direct_feed_link(self):
        fixture, now = self.condemnation_shipping_fixture()
        rows = fixture['articles']
        with patch.object(integrity.body_parallel, '_safe_enrich'):
            text = integrity.build_alert(rows, fixture['markets'], now)
        text = text.replace(' · RSS 입력 기준·본문 미확인', '')
        receipt = evidence.alert_receipt(rows, fixture['markets'], now, text)
        with tempfile.TemporaryDirectory() as folder, ExitStack() as stack:
            root = Path(folder)
            for attr, name in {'ALERT': 'alert.txt', 'PENDING': 'pending.json', 'AUDIT': 'evidence.json'}.items():
                stack.enter_context(patch.object(watch, attr, root/name))
            watch.ALERT.write_text(text, encoding='utf-8')
            watch.PENDING.write_text(json.dumps({'ids': [r['id'] for r in rows]}), encoding='utf-8')
            watch.AUDIT.write_text(json.dumps(receipt, ensure_ascii=False), encoding='utf-8')
            with self.assertRaisesRegex(RuntimeError, 'unverified source body'):
                integrity.verify_alert()

    def energy_facility_fixture(self):
        path = Path(__file__).parent/'test_fixtures/war_energy_facility_38861224312.json'
        fixture = json.loads(path.read_text(encoding='utf-8'))
        return fixture, dt.datetime.fromisoformat(fixture['provenance']['queried_at_kst'])

    def test_actual_energy_facility_plan_is_a_statement(self):
        fixture, _ = self.energy_facility_fixture()
        row = fixture['articles'][0]
        self.assertEqual(integrity.non_military_kind(row), 'military_statement')
        self.assertEqual(integrity.final_color(row), 'yellow')
        self.assertEqual(integrity.topic_label(row), '미국·이란 · 군사 대응·보복 발언')

    def test_actual_energy_facility_nominal_restart_announcement_is_a_statement(self):
        fixture, _ = self.energy_facility_fixture()
        row = fixture['articles'][2]
        self.assertEqual(integrity.non_military_kind(row), 'military_statement')
        self.assertEqual(integrity.final_color(row), 'yellow')
        self.assertEqual(integrity.topic_label(row), '우크라이나·러시아 · 군사 대응·보복 발언')

    def test_actual_fallen_ceasefire_is_not_restraint(self):
        fixture, _ = self.energy_facility_fixture()
        row = fixture['articles'][3]
        self.assertFalse(integrity.mixed_restraint_attack(row))
        self.assertIsNone(integrity.non_military_kind(row))
        self.assertEqual(integrity.final_color(row), 'red')

    def test_energy_facility_plans_and_announcement_scope_keep_other_attacks(self):
        for title in ('미국은 이란 에너지 시설에 대한 새로운 공격을 계획하고 있다',
                      '우크라이나, 러시아 에너지 시설 공격 재개를 발표',
                      '미국, 이란 핵 및 에너지 시설 공격을 검토하고 있다'):
            with self.subTest(title=title):
                self.assertEqual(integrity.non_military_kind(article(title)), 'military_statement')
        for title in ('우크라이나, 러시아 에너지 시설 공격 재개를 발표…이스라엘 공습 개시',
                      '우크라이나, 러시아 에너지 시설 공격 재개했다…성명을 발표',
                      '미국, 이란 에너지 시설 공격을 계획…러시아 미사일 발사'):
            with self.subTest(title=title):
                self.assertIsNone(integrity.non_military_kind(article(title)))
                self.assertEqual(integrity.final_color(article(title)), 'red')

    def test_fallen_truce_still_preserves_explicit_separate_restraint(self):
        for title in ('휴전 무너졌다…우크라이나 공격 자제했지만 러시아 공격 계속',
                      '휴전 무너졌지만 우크라이나 공격 중단…러시아 공격 재개'):
            with self.subTest(title=title):
                self.assertTrue(integrity.mixed_restraint_attack(article(title)))

    def test_energy_facility_explicit_future_and_negation_not_promoted_to_attack(self):
        for title in ('미국, 이란 에너지 시설 공격 재개하겠다',
                      '미국, 이란 에너지 시설 공격 재개하지 않겠다',
                      '미국, 이란 핵 시설을 공격하지 않겠다고 밝혔다'):
            with self.subTest(title=title):
                row = article(title)
                self.assertEqual(integrity.non_military_kind(row), 'military_statement')
                self.assertEqual(integrity.final_color(row), 'yellow')

    def test_actual_energy_facility_render_preserves_distinct_headlines_and_gate(self):
        fixture, now = self.energy_facility_fixture()
        rows = fixture['articles']
        before = watch.STATE.read_bytes()
        with patch.object(integrity.body_parallel, '_safe_enrich'):
            text = integrity.build_alert(rows, fixture['markets'], now)
        self.assertEqual([r['classification_color'] for r in rows], ['yellow', 'yellow', 'yellow', 'red'])
        self.assertTrue(all(html.escape(r['title_original']) in text for r in rows))
        self.assertNotIn('후속 협상 실무 의제에 에너지 인프라 포함', text)
        self.assertTrue(all(not r.get('signals_ko') and not r.get('forced_tags') for r in rows))
        self.assertNotIn('동일 제목 중복', quality._alert_quality_issues(text))
        receipt = evidence.alert_receipt(rows, fixture['markets'], now, text)
        with tempfile.TemporaryDirectory() as folder, ExitStack() as stack:
            root = Path(folder)
            for attr, name in {'ALERT': 'alert.txt', 'PENDING': 'pending.json', 'AUDIT': 'evidence.json'}.items():
                stack.enter_context(patch.object(watch, attr, root/name))
            watch.ALERT.write_text(text, encoding='utf-8')
            watch.PENDING.write_text(json.dumps({'ids': [r['id'] for r in rows]}), encoding='utf-8')
            watch.AUDIT.write_text(json.dumps(receipt, ensure_ascii=False), encoding='utf-8')
            integrity.verify_alert()
        self.assertTrue(all(r.get('body_verified') is False for r in receipt['articles']))
        self.assertEqual(watch.STATE.read_bytes(), before)

    def test_final_gate_rechecks_energy_plan_color_with_matching_body_hash(self):
        fixture, now = self.energy_facility_fixture()
        rows = fixture['articles']
        with patch.object(integrity.body_parallel, '_safe_enrich'):
            text = integrity.build_alert(rows, fixture['markets'], now)
        rows[0]['classification_color'] = 'red'
        text = text.replace('🟡 [신규] <b>1.', '🔴 [신규] <b>1.')
        receipt = evidence.alert_receipt(rows, fixture['markets'], now, text)
        with tempfile.TemporaryDirectory() as folder, ExitStack() as stack:
            root = Path(folder)
            for attr, name in {'ALERT': 'alert.txt', 'PENDING': 'pending.json', 'AUDIT': 'evidence.json'}.items():
                stack.enter_context(patch.object(watch, attr, root/name))
            watch.ALERT.write_text(text, encoding='utf-8')
            watch.PENDING.write_text(json.dumps({'ids': [r['id'] for r in rows]}), encoding='utf-8')
            watch.AUDIT.write_text(json.dumps(receipt, ensure_ascii=False), encoding='utf-8')
            stack.enter_context(patch.object(integrity, '_verify'))
            with self.assertRaisesRegex(RuntimeError, 'statement presented as a new attack'):
                integrity.verify_alert()

    def test_actual_ceasefire_collapse_restart_is_not_restraint(self):
        fixture, _ = self.report_stage_fixture()
        row = fixture['articles'][0]
        self.assertFalse(integrity.mixed_restraint_attack(row))
        self.assertIsNone(integrity.non_military_kind(row))
        self.assertEqual(integrity.final_color(row), 'red')
        self.assertEqual(integrity.topic_label(row), '우크라이나·러시아 · 정유시설 공격 보도')

    def test_actual_bombing_report_delay_is_not_a_new_bombing(self):
        fixture, _ = self.report_stage_fixture()
        row = fixture['articles'][1]
        self.assertEqual(integrity.non_military_kind(row), 'military_report')
        self.assertEqual(integrity.final_color(row), 'yellow')
        self.assertEqual(integrity.topic_label(row), '미국·이란 · 공격 조사·보고서 공표')

    def test_collapsed_ceasefire_mentions_do_not_establish_restraint(self):
        for title in ('트럼프 에너지 휴전 파기…우크라이나 러 정유시설 공습 재개',
                      '휴전 결렬…러시아 공격 계속',
                      'Ceasefire has collapsed…Russia continues attacks',
                      'Truce failed but Russia resumes strikes'):
            with self.subTest(title=title):
                self.assertFalse(integrity.mixed_restraint_attack(article(title)))

    def test_explicit_restraint_survives_another_failed_truce_mention(self):
        row = article('휴전 붕괴…우크라이나 공격 자제했지만 러시아는 계속 공격')
        self.assertTrue(integrity.mixed_restraint_attack(row))
        self.assertEqual(integrity.final_color(row), 'yellow')

    def test_bombing_report_keeps_its_stage_despite_body_attack_background(self):
        row = article('미 국방부, 이란 초등학교 폭격 조사보고서 공개')
        row['description'] = '배경에는 앞선 미사일 공격과 폭격 피해, 호르무즈 항로 제한이 있다.'
        row['signals_ko'] = ['새 공격과 호르무즈 봉쇄']
        row['forced_tags'] = ['확전']
        with patch.object(integrity.body_parallel, '_safe_enrich'):
            text = integrity.build_alert([row], [], NOW)
        self.assertEqual(row['classification_color'], 'yellow')
        self.assertEqual(row['tags'], ['공격 조사·보고서 공표'])
        self.assertIn('미국·이란 · 공격 조사·보고서 공표', text)
        self.assertIn(html.escape(row['title_original']), text)
        self.assertNotIn('이란·호르무즈', text)
        self.assertNotIn('새 공격과 호르무즈 봉쇄', text)
        self.assertIn('조사·보고서 공표 단계', text)

    def test_report_mention_does_not_hide_a_separate_new_attack(self):
        for title in ('미 국방부, 이란 초등학교 폭격 조사보고서 공개…러시아 공습 개시',
                      '우크라이나, 러 정유시설 공습 재개…폭격 조사보고서도 공개',
                      'US releases bombing investigation report; Russia resumes airstrikes',
                      '미 국방부, 폭격 조사보고서 공개…러시아는 우크라이나를 폭격했다',
                      '이란 공격 조사보고서 공개…이스라엘이 레바논을 공습하고 있다',
                      'US releases bombing investigation report; Russia bombs Ukraine'):
            with self.subTest(title=title):
                row = article(title)
                self.assertIsNone(integrity.non_military_kind(row))
                self.assertEqual(integrity.final_color(row), 'red')

    def test_english_investigation_report_is_not_an_attack(self):
        row = article('US delays Iran school bombing investigation report until after midterms')
        self.assertEqual(integrity.non_military_kind(row), 'military_report')
        self.assertEqual(integrity.final_color(row), 'yellow')

    def test_actual_report_stage_render_preserves_four_titles_without_background_cache(self):
        fixture, now = self.report_stage_fixture()
        rows = fixture['articles']
        before = watch.STATE.read_bytes()
        with patch.object(integrity.body_parallel, '_safe_enrich'):
            text = integrity.build_alert(rows, fixture['markets'], now)
        self.assertEqual([row['classification_color'] for row in rows], ['red', 'yellow', 'red', 'red'])
        for row in rows:
            self.assertIn(html.escape(row['title_original']), text)
        self.assertEqual(rows[0]['tags'], ['정유시설 공격 보도'])
        self.assertEqual(rows[1]['tags'], ['공격 조사·보고서 공표'])
        self.assertTrue(all(not row.get('body_verified') for row in rows))
        self.assertNotIn('자제 발언·상대 공격 주장', text)
        self.assertEqual(watch.STATE.read_bytes(), before)

    def test_final_gate_rejects_actual_same_hash_report_stage_errors(self):
        fixture, now = self.report_stage_fixture()
        receipt = evidence.alert_receipt(fixture['articles'], fixture['markets'], now, fixture['bad_alert'])
        self.assertEqual(receipt['alert_sha256'], fixture['provenance']['alert_sha256'])
        with tempfile.TemporaryDirectory() as folder, ExitStack() as stack:
            root = Path(folder)
            for attr, name in {'ALERT': 'alert.txt', 'PENDING': 'pending.json', 'AUDIT': 'evidence.json'}.items():
                stack.enter_context(patch.object(watch, attr, root/name))
            watch.ALERT.write_text(fixture['bad_alert'], encoding='utf-8')
            watch.PENDING.write_text(json.dumps({'ids': [row['id'] for row in fixture['articles']]}), encoding='utf-8')
            watch.AUDIT.write_text(json.dumps(receipt, ensure_ascii=False), encoding='utf-8')
            stack.enter_context(patch.object(integrity, '_verify'))
            with self.assertRaisesRegex(RuntimeError, 'rendered topic differs'):
                integrity.verify_alert()

    def test_final_gate_recomputes_report_stage_after_other_items_are_corrected(self):
        fixture, now = self.report_stage_fixture()
        rows = fixture['articles']
        with patch.object(integrity.body_parallel, '_safe_enrich'):
            text = integrity.build_alert(rows, fixture['markets'], now)
        text = text.replace('🟡 [속보] <b>2.', '🔴 [속보] <b>2.')
        rows[1]['classification_color'] = 'red'
        receipt = evidence.alert_receipt(rows, fixture['markets'], now, text)
        with tempfile.TemporaryDirectory() as folder, ExitStack() as stack:
            root = Path(folder)
            for attr, name in {'ALERT': 'alert.txt', 'PENDING': 'pending.json', 'AUDIT': 'evidence.json'}.items():
                stack.enter_context(patch.object(watch, attr, root/name))
            watch.ALERT.write_text(text, encoding='utf-8')
            watch.PENDING.write_text(json.dumps({'ids': [row['id'] for row in rows]}), encoding='utf-8')
            watch.AUDIT.write_text(json.dumps(receipt, ensure_ascii=False), encoding='utf-8')
            stack.enter_context(patch.object(integrity, '_verify'))
            with self.assertRaisesRegex(RuntimeError, 'statement presented as a new attack'):
                integrity.verify_alert()

    def test_rejected_pause_request_is_not_an_observed_attack_pause(self):
        fixture, _ = self.ceasefire_rejection_fixture()
        row = fixture['articles'][0]
        self.assertFalse(integrity.mixed_restraint_attack(row))
        self.assertEqual(integrity.non_military_kind(row), 'military_statement')
        self.assertEqual(integrity.topic_label(row), '우크라이나·러시아 · 군사 대응·보복 발언')

    def test_ceasefire_rejection_is_not_a_new_ceasefire_announcement(self):
        fixture, _ = self.ceasefire_rejection_fixture()
        row = fixture['articles'][1]
        self.assertEqual(integrity.non_military_kind(row), 'ceasefire_position')
        self.assertEqual(integrity.final_color(row), 'yellow')
        self.assertEqual(integrity.topic_label(row), '우크라이나·러시아 · 휴전·공격 중단 입장')

    def test_rejection_title_with_separate_actual_attack_stays_red(self):
        for title in ('젤렌스키, 휴전 구상 거부…러 정유시설 공격 재개했다',
                      '젤렌스키, 트럼프 휴전 구상에 반기…러 정유시설 폭격 재개 - 데일리안',
                      '젤렌스키, 공격 중단 요구 거부…러시아 미사일 발사',
                      '러시아 공습 개시…젤렌스키, 에너지 휴전 걷어찼다'):
            with self.subTest(title=title):
                row = article(title)
                self.assertIsNone(integrity.non_military_kind(row))
                self.assertEqual(integrity.final_color(row), 'red')

    def test_rejected_pause_is_detected_from_the_current_title_only(self):
        row = article('트럼프, 에너지 휴전 발표…우크라이나 조건부 동참')
        row['description'] = '그보다 앞선 공격 중단 요구 거부와 휴전 철회 발언을 배경으로 소개했다.'
        self.assertNotEqual(integrity.non_military_kind(row), 'ceasefire_position')

    def test_explicit_future_after_rejection_is_not_completed_action(self):
        for title in ('젤렌스키, 공격 중단 요구 거부…“공격 재개하겠다”',
                      '우크라이나, 휴전 요구 거부…미사일 발사할 계획',
                      '젤렌스키, 휴전 거부…공습 재개할 수 있다'):
            with self.subTest(title=title):
                row = article(title)
                self.assertEqual(integrity.non_military_kind(row), 'military_statement')
                self.assertEqual(integrity.final_color(row), 'yellow')

    def test_refinery_action_title_overrides_old_ceasefire_topic(self):
        row = article('젤렌스키, 트럼프에 반기 들었다…러 정유시설 공습 재개')
        row['description'] = '과거 트럼프의 에너지 휴전 발표와 양측 검증을 배경으로 설명했다.'
        row['signals_ko'] = ['에너지 인프라 상호 공격 자제·중단']
        row['classification_color'] = 'yellow'
        with patch.object(integrity.body_parallel, '_safe_enrich'):
            text = integrity.build_alert([row], [], NOW)
        self.assertEqual(row['classification_color'], 'red')
        self.assertIn('우크라이나·러시아 · 정유시설 공격 보도', text)
        self.assertIn(html.escape(row['title_original']), text)
        self.assertNotIn('에너지 인프라 상호 공격 자제·중단', text)
        self.assertEqual(row['tags'], ['정유시설 공격 보도'])

    def test_refinery_future_and_negation_are_not_forced_actual_attacks(self):
        for title in ('젤렌스키, 러 정유시설 공격 재개하겠다',
                      '우크라이나, 러 정유시설 공습 재개하지 않았다',
                      '젤렌스키, 러 정유소 공격 재개 여부 검토'):
            with self.subTest(title=title):
                self.assertFalse(integrity._headline_refinery_action(article(title)))

    def test_actual_rejection_render_preserves_negation_request_and_future(self):
        fixture, now = self.ceasefire_rejection_fixture()
        rows = fixture['articles']
        before = watch.STATE.read_bytes()
        with patch.object(integrity.body_parallel, '_safe_enrich'):
            text = integrity.build_alert(rows, fixture['markets'], now)
        self.assertEqual([row['classification_color'] for row in rows], ['yellow', 'yellow'])
        for row in rows:
            self.assertIn(html.escape(row['title_original']), text)
        self.assertNotIn('에너지 휴전 발표·양측 검증 대기', text)
        self.assertNotIn('자제 발언·상대 공격 주장', text)
        self.assertNotIn('조건부 동참 의사', text)
        self.assertIn('거부·철회·재개 방침', text)
        self.assertEqual([row['body_verified'] for row in rows], [False, True])
        self.assertEqual(watch.STATE.read_bytes(), before)

    def test_final_gate_rejects_actual_same_hash_rejection_wrong_topics(self):
        fixture, now = self.ceasefire_rejection_fixture()
        text = fixture['bad_alert']
        receipt = evidence.alert_receipt(fixture['articles'], fixture['markets'], now, text)
        self.assertEqual(receipt['alert_sha256'], fixture['provenance']['alert_sha256'])
        with tempfile.TemporaryDirectory() as folder, ExitStack() as stack:
            root = Path(folder)
            for attr, name in {'ALERT': 'alert.txt', 'PENDING': 'pending.json', 'AUDIT': 'evidence.json'}.items():
                stack.enter_context(patch.object(watch, attr, root/name))
            watch.ALERT.write_text(text, encoding='utf-8')
            watch.PENDING.write_text(json.dumps({'ids': [row['id'] for row in fixture['articles']]}), encoding='utf-8')
            watch.AUDIT.write_text(json.dumps(receipt, ensure_ascii=False), encoding='utf-8')
            stack.enter_context(patch.object(integrity, '_verify'))
            with self.assertRaisesRegex(RuntimeError, 'rendered topic differs'):
                integrity.verify_alert()

    def test_actual_unquoted_restart_declaration_is_a_statement(self):
        fixture, _ = self.restart_declaration_fixture()
        row = fixture['articles'][0]
        self.assertEqual(integrity.non_military_kind(row), 'military_statement')
        self.assertEqual(integrity.final_color(row), 'yellow')
        self.assertEqual(integrity.topic_label(row), '우크라이나·러시아 · 군사 대응·보복 발언')

    def test_unquoted_refinery_declaration_forms_are_scoped_statements(self):
        for title in ('젤렌스키 "美 요구 거부"… 러시아 정유시설 공격 재개 선언',
                      '젤렌스키, 러 정유시설 공격 재개 방침',
                      '우크라이나, 러시아 정유소 공습 재개 계획',
                      '젤렌스키, 러시아 정유공장 타격을 재개하기로 선언'):
            with self.subTest(title=title):
                row = article(title)
                self.assertEqual(integrity.non_military_kind(row), 'military_statement')
                self.assertEqual(integrity.final_color(row), 'yellow')

    def test_declaration_keeps_independent_and_completed_actions(self):
        for title in ('젤렌스키, 러 정유시설 공격 재개 선언…러시아 미사일 발사',
                      '러시아 공습 개시…젤렌스키, 러 정유시설 공격 재개 선언',
                      '젤렌스키, 러 정유시설 공격 재개했다…추가 방침 선언',
                      '우크라이나, 러 정유시설 공격 재개하고 있다…추가 대응 선언'):
            with self.subTest(title=title):
                row = article(title)
                self.assertIsNone(integrity.non_military_kind(row))
                self.assertEqual(integrity.final_color(row), 'red')

    def test_restart_declaration_is_not_inferred_from_body_background(self):
        row = article('우크라이나, 러시아 정유시설 공격 재개')
        row['description'] = '앞선 인터뷰에서 공격 재개 선언과 방침을 설명했다.'
        self.assertIsNone(integrity.non_military_kind(row))

    def test_actual_declaration_render_preserves_headline_and_other_rows(self):
        fixture, now = self.restart_declaration_fixture()
        rows = fixture['articles']
        metadata = copy.deepcopy(rows[0]['source_metadata'])
        before = watch.STATE.read_bytes()
        with patch.object(integrity.body_parallel, '_safe_enrich'), patch.object(watch, 'market_source_status', fixture['market_source_status'], create=True):
            text = integrity.build_alert(rows, fixture['markets'], now)
        self.assertEqual([row['classification_color'] for row in rows], ['yellow', '', 'red'])
        first = text.split('[신규] <b>2.')[0]
        self.assertIn(html.escape(rows[0]['title_original']), first)
        self.assertIn('우크라이나·러시아 · 군사 대응·보복 발언', first)
        self.assertNotIn('에너지 휴전 발표', first)
        self.assertNotIn('랴잔 정유공장 공격·피격 신호', first)
        self.assertNotIn('우크라이나 에너지 인프라 공격 신호', first)
        self.assertNotIn('휴전·평화', first)
        self.assertEqual(rows[0]['source_metadata'], metadata)
        self.assertTrue(rows[0]['body_verified'])
        self.assertEqual(watch.STATE.read_bytes(), before)
        receipt = evidence.alert_receipt(rows, fixture['markets'], now, text)
        self.assertEqual([r['id'] for r in receipt['articles'] if r['rendered']], [r['id'] for r in rows])
        for row in rows[1:]:
            self.assertIn(html.escape(row['title_original']), text)

    def test_final_gate_rejects_actual_same_hash_declaration_wrong_topic(self):
        fixture, now = self.restart_declaration_fixture()
        text = fixture['bad_alert']
        receipt = evidence.alert_receipt(fixture['articles'], fixture['markets'], now, text)
        self.assertEqual(receipt['alert_sha256'], fixture['provenance']['alert_sha256'])
        with tempfile.TemporaryDirectory() as folder, ExitStack() as stack:
            root = Path(folder)
            for attr, name in {'ALERT': 'alert.txt', 'PENDING': 'pending.json', 'AUDIT': 'evidence.json'}.items():
                stack.enter_context(patch.object(watch, attr, root/name))
            watch.ALERT.write_text(text, encoding='utf-8')
            watch.PENDING.write_text(json.dumps({'ids': [row['id'] for row in fixture['articles']]}), encoding='utf-8')
            watch.AUDIT.write_text(json.dumps(receipt, ensure_ascii=False), encoding='utf-8')
            stack.enter_context(patch.object(integrity, '_verify'))
            with self.assertRaisesRegex(RuntimeError, 'rendered topic differs'):
                integrity.verify_alert()

    def test_declaration_score_clears_prior_peace_tags_without_new_sources(self):
        fixture, now = self.restart_declaration_fixture()
        row = fixture['articles'][0]
        score, tags = integrity.score_item(row, now)
        self.assertGreater(score, 0)
        self.assertEqual(tags, ['군사 대응·보복 발언'])
        self.assertEqual(row['tags'], tags)
        self.assertEqual(row['signals_ko'], [])
        self.assertEqual(row['forced_tags'], [])
        self.assertTrue(row['body_verified'])

    def test_declaration_final_gate_rechecks_extra_summary_and_cache(self):
        fixture, now = self.restart_declaration_fixture()
        rows = fixture['articles']
        with patch.object(integrity.body_parallel, '_safe_enrich'):
            clean = integrity.build_alert(rows, fixture['markets'], now)
        title = html.escape(rows[0]['title_original'])
        for mutate_text, mutate_cache, expected in (
                (True, False, 'background summary'),
                (False, True, 'background event cache')):
            with self.subTest(summary=mutate_text, cache=mutate_cache), tempfile.TemporaryDirectory() as folder, ExitStack() as stack:
                text = clean.replace(title, title + '\n- 에너지 인프라 상호 공격 자제·중단이 부상') if mutate_text else clean
                current = copy.deepcopy(rows)
                if mutate_cache:
                    current[0]['forced_tags'] = ['휴전·평화']
                receipt = evidence.alert_receipt(current, fixture['markets'], now, text)
                root = Path(folder)
                for attr, name in {'ALERT': 'alert.txt', 'PENDING': 'pending.json', 'AUDIT': 'evidence.json'}.items():
                    stack.enter_context(patch.object(watch, attr, root/name))
                watch.ALERT.write_text(text, encoding='utf-8')
                watch.PENDING.write_text(json.dumps({'ids': [row['id'] for row in current]}), encoding='utf-8')
                watch.AUDIT.write_text(json.dumps(receipt, ensure_ascii=False), encoding='utf-8')
                stack.enter_context(patch.object(integrity, '_verify'))
                with self.assertRaisesRegex(RuntimeError, expected):
                    integrity.verify_alert()

    def test_declared_article_body_precedes_unrelated_global_paragraphs(self):
        # 38709332236's later exact-source HTML has nested div#font nodes;
        # the unrelated navigation/footer are p elements. Text is synthetic.
        body = '원문 기사 본문에서 군 당국의 추가 작전 검토와 결정 전 단계를 설명한다. ' * 12
        unrelated = '<p>' + '다른 기사 목록과 저작권 안내문은 현재 기사 본문이 아니다. ' * 12 + '</p>'
        page = unrelated + '<div id="font" class="article_body"><div id="font" class="news_bm">' + body + '</div></div>' + unrelated
        actual = source_body._extract_body(page)
        self.assertEqual(actual, body.strip())
        self.assertNotIn('저작권', actual)

    def test_empty_declared_article_body_does_not_fall_back_to_footer(self):
        page = '<div class="article_body"></div><p>' + '저작권과 관련 기사 목록 안내문. ' * 30 + '</p>'
        self.assertEqual(source_body._extract_body(page), '')

    def test_declared_body_ignores_script_and_related_widgets(self):
        body = '주 기사 본문의 내용이며 별도 문장의 순서와 부정을 그대로 보존한다. ' * 12
        page = ('<div class="article_body"><div>' + body + '</div><script>오류 신호</script>'
                '<aside><p>관련기사 공격 재개</p></aside><div class="related_news">다른 사건</div></div>')
        self.assertEqual(source_body._extract_body(page), body.strip())

    def test_declared_body_handles_void_tags_without_capturing_footer(self):
        first, second = '첫 기사 문장과 검토 단계. ' * 15, '다음 기사 문장과 조건부 방침. ' * 15
        page = '<div itemprop="articleBody">' + first + '<br><img src="x">' + second + '</div><p>본문 밖</p>'
        self.assertEqual(source_body._extract_body(page), ' '.join((first + ' ' + second).split()))

    def test_short_declared_body_remains_unverified(self):
        self.assertEqual(source_body._extract_body('<div class="article-body">짧은 소개문</div><p>'+'다른 기사 내용. '*80+'</p>'), '')

    def test_existing_jsonld_article_body_keeps_precedence(self):
        body = '구조화된 주 기사 본문이며 실제 기사 내용과 기준을 보존한다. ' * 12
        page = '<script type="application/ld+json">' + json.dumps({'articleBody':body},ensure_ascii=False) + '</script>'
        page += '<div class="article_body">별도 짧은 소개</div>'
        self.assertEqual(source_body._extract_body(page), body.strip())

    def test_actual_quoted_refinery_resumption_is_a_statement(self):
        fixture, _ = self.refinery_statement_fixture()
        row = fixture['articles'][1]
        self.assertEqual(integrity.non_military_kind(row), 'military_statement')
        self.assertEqual(integrity.final_color(row), 'yellow')
        self.assertEqual(integrity.topic_label(row), '우크라이나·러시아 · 군사 대응·보복 발언')

    def test_refinery_statement_preserves_original_over_attack_cache(self):
        fixture, now = self.refinery_statement_fixture()
        row = fixture['articles'][1]
        row['title_ko'] = '우크라이나가 러시아 정유시설 공격을 재개했다'
        row['signals_ko'] = ['우크라정유시설공격재개확인']
        row['tags'] = ['확전', '공격확대예고']
        with patch.object(integrity.body_parallel, '_safe_enrich'):
            text = integrity.build_alert([row], [], now)
        self.assertIn(html.escape(row['title_original']), text)
        self.assertEqual(row['classification_color'], 'yellow')
        self.assertEqual(row['signals_ko'], [])
        self.assertNotIn('🔴 [신규]', text)
        self.assertNotIn('공격을 재개했다', text)

    def test_preserved_four_article_replay_has_statement_stage_and_same_ids(self):
        fixture, now = self.refinery_statement_fixture()
        rows = fixture['articles']
        state_before = watch.STATE.read_bytes()
        with patch.object(integrity.body_parallel, '_safe_enrich'), patch.object(watch, 'market_source_status', {}, create=True):
            text = integrity.build_alert(rows, fixture['markets'], now)
        receipt = evidence.alert_receipt(rows, fixture['markets'], now, text)
        self.assertEqual([r['id'] for r in receipt['articles'] if r['rendered']], [r['id'] for r in rows])
        self.assertEqual([r['classification_color'] for r in rows], ['yellow'] * 4)
        self.assertIn('발언·검토 단계', text)
        self.assertNotIn('신규 변화의 중심은 실제 공격', text)
        self.assertNotIn('🔴 [신규]', text)
        for row in rows:
            self.assertIn(html.escape(row['title_original']), text)
            self.assertFalse(row['body_verified'])
        self.assertEqual(watch.STATE.read_bytes(), state_before)

    def test_final_gate_rejects_actual_same_hash_red_refinery_statement(self):
        fixture, now = self.refinery_statement_fixture()
        text = fixture['bad_alert']
        receipt = evidence.alert_receipt(fixture['articles'], fixture['markets'], now, text)
        self.assertEqual(receipt['alert_sha256'], fixture['provenance']['alert_sha256'])
        with tempfile.TemporaryDirectory() as folder, ExitStack() as stack:
            root = Path(folder)
            for attr, name in {'ALERT': 'alert.txt', 'PENDING': 'pending.json', 'AUDIT': 'evidence.json'}.items():
                stack.enter_context(patch.object(watch, attr, root/name))
            watch.ALERT.write_text(text, encoding='utf-8')
            watch.PENDING.write_text(json.dumps({'ids': [row['id'] for row in fixture['articles']]}), encoding='utf-8')
            watch.AUDIT.write_text(json.dumps(receipt, ensure_ascii=False), encoding='utf-8')
            stack.enter_context(patch.object(integrity, '_verify'))
            with self.assertRaisesRegex(RuntimeError, 'rendered topic differs'):
                integrity.verify_alert()

    def test_refinery_statement_gate_rechecks_color_with_correct_topic(self):
        fixture, now = self.refinery_statement_fixture()
        row = fixture['articles'][1]
        text = ('🔴 [신규] <b>1. ' + integrity.topic_label(row) + '</b>\n'
                + html.escape(row['title_original']) + '\n<a href="' + row['link'] + '">원문</a>')
        receipt = evidence.alert_receipt([row], [], now, text)
        with tempfile.TemporaryDirectory() as folder, ExitStack() as stack:
            root = Path(folder)
            for attr, name in {'ALERT': 'alert.txt', 'PENDING': 'pending.json', 'AUDIT': 'evidence.json'}.items():
                stack.enter_context(patch.object(watch, attr, root/name))
            watch.ALERT.write_text(text, encoding='utf-8')
            watch.PENDING.write_text(json.dumps({'ids': [row['id']]}), encoding='utf-8')
            watch.AUDIT.write_text(json.dumps(receipt, ensure_ascii=False), encoding='utf-8')
            stack.enter_context(patch.object(integrity, '_verify'))
            with self.assertRaisesRegex(RuntimeError, 'statement presented'):
                integrity.verify_alert()

    def test_quoted_future_refinery_forms_remain_statements(self):
        for title in ('젤렌스키 “러 정유시설 공격 재개”…정면돌파 시사',
                      '우크라이나 "러시아 정유소 공격 재개할 계획"',
                      '젤렌스키 "러 정유시설 공격 재개하겠다"'):
            with self.subTest(title=title):
                self.assertEqual(integrity.non_military_kind(article(title)), 'military_statement')
                self.assertEqual(integrity.final_color(article(title)), 'yellow')

    def test_quoted_completed_refinery_actions_remain_attacks(self):
        for title in ('젤렌스키 "러 정유시설 공격 재개했다"…정면돌파 시사',
                      '젤렌스키 "러 정유시설 공격 재개하고 있다"…추가 대응 시사',
                      '우크라이나, 러 정유시설 공격 재개…젤렌스키 추가 압박 시사'):
            with self.subTest(title=title):
                self.assertIsNone(integrity.non_military_kind(article(title)))
                self.assertEqual(integrity.final_color(article(title)), 'red')

    def test_independent_action_outside_refinery_policy_quote_wins(self):
        for title in ('젤렌스키 "러 정유시설 공격 재개"…방침 시사, 러시아 미사일 발사',
                      '러시아 공습 개시…젤렌스키 "러 정유시설 공격 재개" 방침 시사'):
            with self.subTest(title=title):
                self.assertIsNone(integrity.non_military_kind(article(title)))
                self.assertEqual(integrity.final_color(article(title)), 'red')

    def test_other_actual_action_inside_same_policy_quote_is_not_hidden(self):
        row = article('젤렌스키 "러시아 미사일 발사, 러 정유시설 공격 재개" 방침 시사')
        self.assertIsNone(integrity.non_military_kind(row))
        self.assertEqual(integrity.final_color(row), 'red')


    def riyadh_fixture(self):
        path = Path(__file__).parent/'test_fixtures/war_riyadh_headline_38636753771.json'
        fixture = json.loads(path.read_text(encoding='utf-8'))
        return fixture, dt.datetime.fromisoformat(fixture['provenance']['queried_at_kst'])

    def test_rejected_riyadh_reports_keep_three_distinct_source_headlines(self):
        fixture, now = self.riyadh_fixture()
        rows = fixture['articles']
        with patch.object(integrity.body_parallel, '_safe_enrich'), patch.object(watch, 'market_source_status', {}, create=True):
            text = integrity.build_alert(rows, fixture['markets'], now)
        receipt = evidence.alert_receipt(rows, fixture['markets'], now, text)
        self.assertEqual([r['id'] for r in receipt['articles'] if r['rendered']],
                         [r['id'] for r in rows])
        self.assertFalse(integrity._same_source_article(rows[0], rows[1]))
        for row in rows:
            self.assertIn(row['title_original'], html.unescape(text))
            self.assertEqual(row['classification_color'], 'red')
            self.assertNotIn('duplicate_of', row)
        self.assertNotIn('공격·요격 신호', text)
        self.assertNotIn('동일 제목 중복', quality._alert_quality_issues(text))

    def test_riyadh_topic_does_not_add_houthi_actor_absent_from_headline(self):
        row = article('사우디, 리야드서 이란 미사일 요격')
        self.assertFalse(integrity._riyadh_missile_headline(row))
        self.assertNotIn('후티', integrity.topic_label(row))

    def test_riyadh_attack_claim_does_not_inherit_background_interception(self):
        fixture, _ = self.riyadh_fixture()
        row = fixture['articles'][1]
        row['article_text'] = '배경: 사우디 주도 연합군이 리야드 북쪽에서 탄도미사일을 요격했다고 발표했다.'
        row['title_ko'] = '사우디 주도 연합군, 후티 미사일 요격 확인'
        self.assertEqual(integrity.topic_label(row), '사우디·후티 · 리야드 미사일 보도')
        self.assertEqual(integrity._display_headline(row), row['title_original'])
        self.assertIn('명중', integrity._display_headline(row))
        self.assertNotIn('요격', integrity._display_headline(row))

    def test_riyadh_explicit_interception_preserves_actor_and_claim_contrast(self):
        row = article('사우디 연합군, 리야드 후티 미사일 요격…후티는 공항 명중 주장')
        text = integrity.build_alert([row], [], NOW)
        self.assertIn(row['title_original'], text)
        self.assertIn('후티는 공항 명중 주장', text)
        self.assertEqual(row['classification_color'], 'red')

    def test_riyadh_warning_and_discussion_remain_yellow(self):
        for title, kind in (
                ('후티, 리야드 미사일 공격 예고', 'military_statement'),
                ('후티, 리야드 미사일 발사 검토', 'military_discussion')):
            with self.subTest(title=title):
                row = article(title)
                text = integrity.build_alert([row], [], NOW)
                self.assertEqual(integrity.non_military_kind(row), kind)
                self.assertEqual(row['classification_color'], 'yellow')
                self.assertIn(title, text)
                self.assertNotIn('🔴 [신규]', text)

    def test_english_riyadh_claim_retains_original_over_cached_translation(self):
        row = article('Houthis claim missile hit Riyadh airport')
        row['title_ko'] = '사우디 연합군, 리야드 미사일 요격 확인'
        text = integrity.build_alert([row], [], NOW)
        self.assertIn(row['title_original'], text)
        self.assertNotIn('요격 확인', text)

    def test_final_gate_rejects_same_hash_riyadh_summary_or_invented_topic(self):
        fixture, _ = self.riyadh_fixture()
        for topic, summary, expected in (
                ('사우디·후티 · 리야드 미사일 요격', fixture['articles'][1]['title_original'], 'topic differs'),
                ('사우디·후티 · 리야드 미사일 보도', '후티의 리야드 탄도미사일 공격·요격 신호', 'headline differs')):
            with self.subTest(topic=topic, summary=summary), tempfile.TemporaryDirectory() as folder, ExitStack() as stack:
                row = copy.deepcopy(fixture['articles'][1])
                text = '🔴 [신규] <b>1. ' + topic + '</b>\n' + summary + '\n<a href="' + row['link'] + '">원문</a>'
                receipt = evidence.alert_receipt([row], [], NOW, text)
                root = Path(folder)
                for attr, name in {'ALERT': 'alert.txt', 'PENDING': 'pending.json', 'AUDIT': 'evidence.json'}.items():
                    stack.enter_context(patch.object(watch, attr, root/name))
                watch.ALERT.write_text(text, encoding='utf-8')
                watch.PENDING.write_text(json.dumps({'ids': [row['id']]}), encoding='utf-8')
                watch.AUDIT.write_text(json.dumps(receipt, ensure_ascii=False), encoding='utf-8')
                stack.enter_context(patch.object(integrity, '_verify'))
                with self.assertRaisesRegex(RuntimeError, expected):
                    integrity.verify_alert()

    def macro_fixture(self):
        path = Path(__file__).parent/'test_fixtures/war_macro_effect_38570159999.json'
        fixture = json.loads(path.read_text(encoding='utf-8'))
        return fixture, dt.datetime.fromisoformat(fixture['provenance']['queried_at_kst'])

    def test_preserved_cpi_report_keeps_prices_instead_of_cached_peace_meeting(self):
        fixture, now = self.macro_fixture()
        row = fixture['article']
        score, tags = integrity.score_item(row, now)
        row['score'], row['tags'] = score, tags
        with patch.object(integrity.body_parallel, '_safe_enrich'):
            text = integrity.build_alert([row], [], now)
        self.assertGreater(score, 0)
        self.assertEqual(integrity.non_military_kind(row), 'market_effect')
        self.assertEqual(row['classification_color'], 'yellow')
        self.assertIn('미국·물가 · 전쟁 파급 보도', text)
        self.assertIn(row['title_original'], text)
        self.assertIn('9월 CPI 3.7% 상승', text)
        self.assertEqual(row['signals_ko'], [])
        self.assertEqual(row['forced_tags'], [])
        self.assertEqual(row['tags'], ['전쟁의 물가 파급 보도'])
        for stale in ('젤렌스키', 'Trump 회동', '휴전·평화', '종전·협상'):
            self.assertNotIn(stale, text)
        receipt = evidence.alert_receipt([row], [], now, text)
        self.assertEqual([x['id'] for x in receipt['articles'] if x['rendered']], [row['id']])

    def test_late_september_requires_source_actors_and_meeting_predicate(self):
        fixture, _ = self.macro_fixture()
        signals, marks = newideas._newidea_signals(fixture['article'])
        self.assertNotIn('트럼프후속회동', marks)
        self.assertFalse(any('젤렌스키' in x for x in signals))
        actual_meeting = article('젤렌스키, 9월 말 트럼프와 회동 예정')
        _, marks = newideas._newidea_signals(actual_meeting)
        self.assertIn('트럼프후속회동', marks)

    def test_same_hash_cpi_body_with_cached_meeting_is_rejected(self):
        fixture, now = self.macro_fixture()
        row, text = fixture['article'], fixture['bad_rendered_block']
        receipt = evidence.alert_receipt([row], [], now, text)
        with tempfile.TemporaryDirectory() as folder, ExitStack() as stack:
            root = Path(folder)
            for attr, name in {'ALERT': 'alert.txt', 'PENDING': 'pending.json', 'AUDIT': 'evidence.json'}.items():
                stack.enter_context(patch.object(watch, attr, root/name))
            watch.ALERT.write_text(text, encoding='utf-8')
            watch.PENDING.write_text(json.dumps({'ids': [row['id']]}), encoding='utf-8')
            watch.AUDIT.write_text(json.dumps(receipt, ensure_ascii=False), encoding='utf-8')
            stack.enter_context(patch.object(integrity, '_verify'))
            with self.assertRaisesRegex(RuntimeError, 'WAR_INTEGRITY_GATE: rendered topic differs'):
                integrity.verify_alert()

    def test_explicit_new_attack_clause_is_not_replaced_by_macro_stage(self):
        row = article('이란, 공습 재개…전쟁 여파에 미국 CPI 물가 상승')
        self.assertIsNone(integrity.non_military_kind(row))
        self.assertEqual(integrity.final_color(row), 'red')

    def test_explicit_bilateral_peace_implementation_is_not_replaced_by_macro_stage(self):
        row = article('러시아·우크라이나, 휴전 합의·양측 공격 중단 이행 확인…전쟁 물가 부담 완화 기대')
        self.assertIsNone(integrity.non_military_kind(row))
        self.assertEqual(integrity.final_color(row), 'green')

    def test_rejected_production_alias_pair_keeps_exact_origin_once(self):
        fixture, now = self.alias_fixture()
        feed, origin = fixture['articles'][:2]
        with patch.object(integrity.body_parallel, '_safe_enrich'):
            text = integrity.build_alert(fixture['articles'], fixture['markets'], now)
        receipt = evidence.alert_receipt(fixture['articles'], fixture['markets'], now, text)
        rendered = [row['id'] for row in receipt['articles'] if row['rendered']]
        self.assertEqual(rendered, [origin['id'], *[row['id'] for row in fixture['articles'][2:]]])
        self.assertNotIn(feed['link'], text)
        self.assertIn(origin['link'], text)
        self.assertEqual(feed['duplicate_of'], origin['id'])
        self.assertEqual(feed['render_withheld'], 'duplicate_source_article')
        self.assertFalse(feed['body_verified'])
        self.assertTrue(origin['body_verified'])
        self.assertNotIn('동일 제목 중복', quality._alert_quality_issues(text))

    def test_alias_preference_is_independent_of_input_order(self):
        fixture, now = self.alias_fixture()
        for reverse in (False, True):
            pair = copy.deepcopy(fixture['articles'][:2])
            if reverse:
                pair.reverse()
            with self.subTest(reverse=reverse), patch.object(integrity.body_parallel, '_safe_enrich'):
                text = integrity.build_alert(pair, [], now)
            receipt = evidence.alert_receipt(pair, [], now, text)
            self.assertEqual([row['id'] for row in receipt['articles'] if row['rendered']],
                             [fixture['articles'][1]['id']])

    def test_alias_shared_resolved_url_does_not_mark_hidden_feed_rendered(self):
        fixture, now = self.alias_fixture()
        feed, origin = fixture['articles'][:2]
        feed['resolved_url'] = origin['link']
        with patch.object(integrity.body_parallel, '_safe_enrich'):
            text = integrity.build_alert([feed, origin], [], now)
        receipt = evidence.alert_receipt([feed, origin], [], now, text)
        self.assertFalse(receipt['articles'][0]['rendered'])
        self.assertTrue(receipt['articles'][1]['rendered'])

    def test_same_publisher_words_negation_order_and_count_are_required(self):
        for title in ('우크라이나 러시아 공격', '러시아 우크라이나 공격 안 한다',
                      '러시아 우크라이나 선박 24척 공격'):
            left = article(title)
            right = article({'우크라이나 러시아 공격': '러시아 우크라이나 공격',
                             '러시아 우크라이나 공격 안 한다': '러시아 우크라이나 공격 한다',
                             '러시아 우크라이나 선박 24척 공격': '러시아 우크라이나 선박 42척 공격'}[title])
            with self.subTest(title=title):
                self.assertFalse(integrity._same_source_article(left, right))

    def test_alias_different_publisher_host_or_publication_remains_unresolved(self):
        fixture, _ = self.alias_fixture()
        feed, origin = fixture['articles'][:2]
        variants = [dict(origin, source='다른 매체'),
                    dict(origin, link='https://other.example/article', resolved_url='https://other.example/article'),
                    dict(origin, published=format_datetime(dt.datetime(2026, 10, 14, 15, 48, tzinfo=watch.KST))),
                    dict(origin, published=''),
                    dict(origin, source_metadata={'publication_status': 'conflict'})]
        for row in variants:
            with self.subTest(row=row):
                self.assertFalse(integrity._same_source_article(feed, row))

    def test_alias_same_title_different_time_still_hits_existing_quality_gate(self):
        fixture, now = self.alias_fixture()
        feed, origin = fixture['articles'][:2]
        origin['published'] = format_datetime(now-dt.timedelta(minutes=10))
        with patch.object(integrity.body_parallel, '_safe_enrich'):
            text = integrity.build_alert([feed, origin], [], now)
        self.assertIn('동일 제목 중복', quality._alert_quality_issues(text))

    def test_alias_pipeline_saves_only_rendered_seen_and_then_suppresses_feed(self):
        fixture, _ = self.alias_fixture()
        pair = fixture['articles'][:2]
        now = dt.datetime.now(watch.KST)
        published = now-dt.timedelta(minutes=20)
        for row in pair:
            row['published'] = format_datetime(published)
        origin = pair[1]
        origin['source_metadata']['published_at_kst'] = published.isoformat()
        origin['source_metadata']['publication_candidates'] = [
            {'field': 'article:published_time', 'at_kst': published.isoformat()}]
        with tempfile.TemporaryDirectory() as folder, ExitStack() as stack:
            root = Path(folder)
            for attr, name in {'OUT': '.', 'STATE': 'state.json', 'ALERT': 'alert.txt',
                               'PENDING': 'pending.json', 'AUDIT': 'evidence.json',
                               'SUMMARY': 'summary.md'}.items():
                stack.enter_context(patch.object(watch, attr, root/name))
            initial = {'seen': ['already-confirmed'], 'updated_at': 'old'}
            watch.STATE.write_text(json.dumps(initial), encoding='utf-8')
            stack.enter_context(patch.object(watch, 'QUERIES', ['fixture']))
            stack.enter_context(patch.object(watch, 'google_news', return_value=(pair, None)))
            stack.enter_context(patch.object(watch, 'score_item', return_value=(90, ['확전'])))
            stack.enter_context(patch.object(watch, 'market_snapshot', return_value=[]))
            stack.enter_context(patch.object(watch, 'translate_ko', side_effect=lambda value: value))
            stack.enter_context(patch.object(integrity.body_parallel, '_safe_enrich'))
            watch.run()
            integrity.runner.verify_alert()
            pending = json.loads(watch.PENDING.read_text(encoding='utf-8'))
            self.assertEqual(pending['ids'], [origin['id']])
            self.assertEqual(json.loads(watch.STATE.read_text()), initial)
            # Offline simulation of the existing post-delivery finalize stage.
            watch.finalize()
            confirmed = json.loads(watch.STATE.read_text(encoding='utf-8'))
            self.assertEqual(confirmed['seen'], ['already-confirmed', origin['id']])
            self.assertEqual(confirmed['source_aliases'], {pair[0]['id']: origin['id']})
            watch.google_news.return_value = ([pair[0]], None)
            watch.run()
            self.assertFalse(watch.ALERT.exists())
            self.assertFalse(watch.PENDING.exists())
            receipt = json.loads(watch.AUDIT.read_text(encoding='utf-8'))
            self.assertFalse(receipt['articles'][0]['rendered'])
            self.assertEqual(receipt['articles'][0]['render_withheld'], 'source_alias_already_seen')
            self.assertEqual(json.loads(watch.STATE.read_text()), confirmed)

    def test_alias_finalization_does_not_learn_an_unrendered_target(self):
        fixture, _ = self.alias_fixture()
        feed, origin, shown = fixture['articles'][:3]
        feed.update(render_withheld='duplicate_source_article', duplicate_of=origin['id'], rendered=False)
        origin['rendered'] = False
        shown['rendered'] = True
        with tempfile.TemporaryDirectory() as folder, ExitStack() as stack:
            root = Path(folder)
            for attr, name in {'STATE': 'state.json', 'PENDING': 'pending.json', 'AUDIT': 'evidence.json'}.items():
                stack.enter_context(patch.object(watch, attr, root/name))
            watch.STATE.write_text('{"seen":["old"]}', encoding='utf-8')
            watch.PENDING.write_text(json.dumps({'ids': [shown['id']]}), encoding='utf-8')
            watch.AUDIT.write_text(json.dumps({'articles': [feed, origin, shown]}), encoding='utf-8')
            watch.finalize()
            state = json.loads(watch.STATE.read_text())
            self.assertEqual(state['seen'], ['old', shown['id']])
            self.assertNotIn('source_aliases', state)

    def test_alias_finalization_rejects_mismatch_without_state_write(self):
        fixture, _ = self.alias_fixture()
        feed, origin = fixture['articles'][:2]
        feed.update(render_withheld='duplicate_source_article', duplicate_of=origin['id'], rendered=False)
        origin['published'] = 'Wed, 14 Oct 2026 14:00:00 +0900'
        with tempfile.TemporaryDirectory() as folder, ExitStack() as stack:
            root = Path(folder)
            for attr, name in {'STATE': 'state.json', 'PENDING': 'pending.json', 'AUDIT': 'evidence.json'}.items():
                stack.enter_context(patch.object(watch, attr, root/name))
            before = '{"seen":["old"]}'
            watch.STATE.write_text(before, encoding='utf-8')
            watch.PENDING.write_text(json.dumps({'ids': [origin['id']]}), encoding='utf-8')
            watch.AUDIT.write_text(json.dumps({'articles': [feed, origin]}), encoding='utf-8')
            with self.assertRaisesRegex(RuntimeError, 'source alias lacks matching'):
                watch.finalize()
            self.assertEqual(watch.STATE.read_text(), before)

    def test_alias_history_without_confirmed_seen_target_does_not_suppress(self):
        fixture, now = self.alias_fixture()
        feed, origin = fixture['articles'][:2]
        state = {'seen': [], 'source_aliases': {feed['id']: origin['id']}}
        with patch.object(watch, 'load_state', return_value=state), patch.object(integrity.body_parallel, '_safe_enrich'):
            text = integrity.build_alert([feed], [], now)
        self.assertIn(feed['link'], text)

    def test_bad_alias_history_is_not_silently_reset(self):
        for aliases in ([], {'feed': ''}, {'feed': 'feed'}):
            with self.subTest(aliases=aliases), self.assertRaisesRegex(RuntimeError, 'invalid source alias history'):
                integrity._source_aliases({'source_aliases': aliases})

    def test_maritime_tally_preserves_period_count_and_ship_population(self):
        row = article('호르무즈 피격 선박 2주에 24척, 개전 이후 최대 규모')
        row['description'] = 'FT는 UKMTO와 유럽 안보 당국자 자료를 종합해 지난 11일까지 2주 동안 선박 24척이 공격당했다고 보도했다.'
        row['signals_ko'] = ['UKMTO 기준 호르무즈·오만 인근 유조선의 미확인 발사체 피격이 반복']
        row['tags'] = ['유조선피격', '해상안보', '확전']
        text = integrity.build_alert([row], [], NOW)
        self.assertEqual(integrity.topic_label(row), '호르무즈 · 선박 피격 집계 보도')
        self.assertEqual(integrity.final_color(row), 'red')
        self.assertIn(row['title_original'], text)
        self.assertIn('선박피격집계', row['tags'])
        self.assertNotIn('유조선피격', row['tags'])
        self.assertNotIn('미확인 발사체', text)
        self.assertNotIn('오만 인근', text)
        self.assertNotIn('유조선 피격', text)
        self.assertIn('기사 공표시각과 집계 기간을 구분', text)

    def test_maritime_tally_does_not_promote_denial_forecast_or_question(self):
        for title in ('호르무즈 선박 2주에 24척 피격설 부인',
                      '호르무즈 선박 2주에 24척 피격 가능성 우려',
                      '호르무즈 피격 선박 2주에 24척?',
                      '24 ships were not attacked in Hormuz in two weeks'):
            with self.subTest(title=title):
                self.assertFalse(integrity.maritime_attack_tally(article(title)))
                self.assertIsNone(integrity._primary_topic(article(title)))

    def test_single_new_ship_hit_keeps_existing_incident_classification(self):
        for title in ('호르무즈 유조선 피격…미확인 발사체로 선원 부상',
                      '호르무즈에서 10월 23일 선박 24척 피격',
                      '24 ships hit record profits in two weeks',
                      '24 vessels struck a deal over two weeks'):
            with self.subTest(title=title):
                self.assertFalse(integrity.maritime_attack_tally(article(title)))

    def test_english_tally_keeps_verified_translation_and_does_not_invent_iran(self):
        row = article('24 ships attacked in Hormuz in two weeks', source='Reuters')
        row['title_ko'] = '호르무즈에서 2주 동안 선박 24척 피격'
        self.assertEqual(integrity.topic_label(row), '호르무즈 · 선박 피격 집계 보도')
        text = integrity.build_alert([row], [], NOW)
        self.assertIn(row['title_ko'], text)
        self.assertNotIn('이란·호르무즈', text)

    def test_final_gate_rejects_changed_summary_even_when_topic_and_receipt_match(self):
        row = article('호르무즈 피격 선박 2주에 24척, 개전 이후 최대 규모')
        row['classification_color'] = 'red'
        for summary in ('호르무즈 피격 선박 2주에 42척, 개전 이후 최대 규모',
                        'UKMTO 기준 호르무즈·오만 인근 유조선의 미확인 발사체 피격이 반복'):
            with self.subTest(summary=summary), tempfile.TemporaryDirectory() as folder, ExitStack() as stack:
                root = Path(folder)
                text = '🔴 [신규] <b>1. 호르무즈 · 선박 피격 집계 보도</b>\n' + summary + '\n<a href="' + row['link'] + '">원문</a>'
                receipt = evidence.alert_receipt([row], [], NOW, text)
                for attr, name in {'ALERT': 'alert.txt', 'PENDING': 'pending.json', 'AUDIT': 'evidence.json'}.items():
                    stack.enter_context(patch.object(watch, attr, root/name))
                watch.ALERT.write_text(text, encoding='utf-8')
                watch.PENDING.write_text(json.dumps({'ids': [row['id']]}), encoding='utf-8')
                watch.AUDIT.write_text(json.dumps(receipt, ensure_ascii=False), encoding='utf-8')
                stack.enter_context(patch.object(integrity, '_verify'))
                with self.assertRaisesRegex(RuntimeError, 'rendered headline differs'):
                    integrity.verify_alert()

    def test_retaliation_statement_ignores_background_attack_and_iran_actor(self):
        row = article('美 트럼프, 중간선거 다음 후티 반군에 보복 시사 "잊지 않을 것"')
        row['description'] = '발언은 선거 이후의 대응 가능성을 설명한다. 배경에는 과거 미국 폭격과 후티의 사우디 공격, 이란 관련 주장이 있다.'
        row['signals_ko'] = ['사우디리야드후티미사일요격확인']
        self.assertEqual(integrity.non_military_kind(row), 'military_statement')
        self.assertEqual(integrity.final_color(row), 'yellow')
        self.assertEqual(integrity.topic_label(row), '미국·후티 · 군사 대응·보복 발언')
        text = integrity.build_alert([row], [], NOW)
        self.assertIn('🟡 [', text)
        self.assertNotIn('🔴', text)
        self.assertNotIn('이란·호르무즈', text)
        self.assertIn('보복 시사', text)

    def test_attack_resumption_disagreement_is_not_resumed_airstrikes(self):
        title = '네타냐후 "이란 바로 공격", 트럼프 "선거 전엔 안 돼"…이란 공습 재개 놓고 이견 - JTBC'
        row = article(title, source='JTBC', link='https://news.google.com/rss/articles/disagreement')
        row['description'] = '미국과 이스라엘이 공습 재개를 논의한다. 배경에는 과거 공습과 호르무즈 피격 보도가 있다.'
        row['signals_ko'] = ['이란호르무즈공격']
        self.assertEqual(integrity.non_military_kind(row), 'military_discussion')
        self.assertEqual(integrity.topic_label(row), '미국·이스라엘·이란 · 공습 재개 논의·이견')
        self.assertEqual(integrity.final_color(row), 'yellow')
        text = integrity.build_alert([row], [], NOW)
        self.assertIn('🟡 [', text)
        self.assertNotIn('🔴', text)
        self.assertNotIn('이란·호르무즈', text)
        self.assertIn('선거 전엔 안 돼', text)
        self.assertIn('실제 작전·운영 변화', text)

    def test_resumption_discussion_ignores_past_attack_body(self):
        row = article('네타냐후, 트럼프와 이란 공습 재개 논의…양국 선거 앞두고 고심', source='뉴시스')
        row['article_text'] = '배경에는 과거 미사일 공격과 공습 재개 및 후티 보복 공격이 언급된다.'
        self.assertEqual(integrity.non_military_kind(row), 'military_discussion')
        self.assertEqual(integrity.final_color(row), 'yellow')

    def test_actual_resumed_attack_in_separate_clause_is_preserved(self):
        row = article('이란 공습 재개…미국과 추가 공격 논의')
        self.assertIsNone(integrity.non_military_kind(row))
        self.assertEqual(integrity.final_color(row), 'red')

    def test_english_discussion_keeps_three_headline_actors(self):
        row = article('Trump and Netanyahu discuss resuming airstrikes on Iran', source='Reuters')
        row['description'] = 'The background mentions earlier airstrikes and missile attacks.'
        self.assertEqual(integrity.non_military_kind(row), 'military_discussion')
        self.assertEqual(integrity.topic_label(row), '미국·이스라엘·이란 · 공습 재개 논의·이견')
        self.assertEqual(integrity.final_color(row), 'yellow')

    def test_missile_defense_question_is_an_analysis_not_a_new_attack(self):
        row = article('사우디아라비아가 수십억 달러를 들여 구축한 "방패"가 왜 여전히 후티 반군의 미사일 공격을 막지 못하는 걸까요? - Vietnam.vn', source='Vietnam.vn')
        row['body_verified'] = False
        self.assertEqual(integrity.non_military_kind(row), 'military_analysis')
        self.assertEqual(integrity.topic_label(row), '사우디·후티 · 군사·안보 해설')
        text = integrity.build_alert([row], [], NOW)
        self.assertIn('🟡 [', text)
        self.assertNotIn('🔴', text)
        self.assertIn('새로운 군사작전 개시는 별도 확인 필요', text)

    def test_explicit_new_attack_wins_over_following_analysis_question(self):
        row = article('후티, 공습 개시…사우디 방공망은 왜 뚫렸나?')
        self.assertIsNone(integrity.non_military_kind(row))
        self.assertEqual(integrity.final_color(row), 'red')

    def test_discussion_analysis_and_attack_pass_the_full_render_and_integrity_path(self):
        now = dt.datetime.now(watch.KST)
        rows = [article('네타냐후, 트럼프와 이란 공습 재개 놓고 이견', link='https://www.fnnews.com/news/discussion'),
                article('사우디 방공망이 왜 후티 미사일 공격을 막지 못했나?', link='https://www.fnnews.com/news/analysis'),
                article('후티, 사우디 아람코 본사 미사일 공격…화재', link='https://www.fnnews.com/news/attack')]
        for n, row in enumerate(rows):
            row['id'] = f'fixture-{n}'
            row['published'] = format_datetime(now - dt.timedelta(minutes=20))
        with tempfile.TemporaryDirectory() as folder, ExitStack() as stack:
            root = Path(folder)
            stack.enter_context(patch.object(watch, 'OUT', root))
            for attr, name in {'STATE': 'state.json', 'ALERT': 'alert.txt', 'PENDING': 'pending.json',
                               'AUDIT': 'evidence.json', 'SUMMARY': 'summary.md'}.items():
                stack.enter_context(patch.object(watch, attr, root/name))
            watch.STATE.write_text('{"seen":["already-confirmed"]}', encoding='utf-8')
            stack.enter_context(patch.object(watch, 'QUERIES', ['fixture']))
            stack.enter_context(patch.object(watch, 'google_news', return_value=(rows, None)))
            stack.enter_context(patch.object(watch, 'score_item', return_value=(90, ['확전'])))
            stack.enter_context(patch.object(watch, 'market_snapshot', return_value=[]))
            stack.enter_context(patch.object(watch, 'translate_ko', side_effect=lambda value: value))
            watch.run()
            integrity.runner.verify_alert()
            receipt = json.loads(watch.AUDIT.read_text(encoding='utf-8'))
            self.assertEqual({row['title_original']: row['classification_color'] for row in receipt['articles']},
                             {row['title_original']: color for row, color in zip(rows, ('yellow', 'yellow', 'red'))})
            pending = json.loads(watch.PENDING.read_text())['ids']
            self.assertEqual(len(pending), 3)
            self.assertEqual(set(pending), {row['id'] for row in receipt['articles'] if row['rendered']})
            self.assertEqual(json.loads(watch.STATE.read_text())['seen'], ['already-confirmed'])

    def test_final_gate_rechecks_discussion_and_analysis_not_saved_red_color(self):
        for title in ('네타냐후, 트럼프와 이란 공습 재개 놓고 이견',
                      '사우디 방공망이 왜 후티 미사일 공격을 막지 못했나?'):
            with self.subTest(title=title), tempfile.TemporaryDirectory() as folder, ExitStack() as stack:
                row = article(title)
                row['classification_color'] = 'red'
                topic = integrity.topic_label(row)
                text = '🔴 [신규] <b>1. ' + topic + '</b>\n' + title + '\n<a href="' + row['link'] + '">원문</a>'
                receipt = evidence.alert_receipt([row], [], NOW, text)
                root = Path(folder)
                for attr, name in {'ALERT': 'alert.txt', 'PENDING': 'pending.json', 'AUDIT': 'evidence.json'}.items():
                    stack.enter_context(patch.object(watch, attr, root/name))
                watch.ALERT.write_text(text, encoding='utf-8')
                watch.PENDING.write_text(json.dumps({'ids': [row['id']]}), encoding='utf-8')
                watch.AUDIT.write_text(json.dumps(receipt, ensure_ascii=False), encoding='utf-8')
                stack.enter_context(patch.object(integrity, '_verify'))
                with self.assertRaisesRegex(RuntimeError, 'statement presented'):
                    integrity.verify_alert()

    def test_aramco_headquarters_headline_overrides_unrelated_interception_cache(self):
        row = article('후티 반군, 사우디 아람코 본사 공격 정황…국제유가 긴장')
        row['description'] = '본사 공격 보도에 관한 기사이며 피해 범위는 확인되지 않았다. 배경에 리야드 미사일 요격 소식이 언급된다.'
        row['signals_ko'] = ['사우디리야드후티미사일요격확인']
        self.assertEqual(integrity.topic_label(row), '사우디·후티 · 아람코 본사 공격 보도')
        text = integrity.build_alert([row], [], NOW)
        self.assertIn('아람코 본사 공격 보도', text)
        self.assertNotIn('리야드 미사일 요격', text)
        self.assertIn('공격 정황', text)

    def test_support_statement_is_not_a_fresh_energy_ceasefire_announcement(self):
        row = article('美 트럼프, 우크라 정보 지원 유지 "러시아도 종전 원해"')
        row['description'] = '새 발언은 정보 공유 중단 의혹의 부인이다. 배경에는 앞선 에너지 휴전 주장과 그 이후 러시아의 공격이 있다.'
        row['signals_ko'] = ['우크라러에너지휴전발표양측검증대기']
        self.assertEqual(integrity.non_military_kind(row), 'support_statement')
        self.assertEqual(integrity.final_color(row), 'yellow')
        text = integrity.build_alert([row], [], NOW)
        self.assertIn('정보 지원·종전 의향 발언', text)
        self.assertNotIn('에너지 휴전 발표', text)
        self.assertNotIn('🔴', text)

    def test_explicit_current_attack_wins_over_warning_in_same_headline(self):
        row = article('후티, 사우디 미사일 공격 개시…미국 보복 경고')
        self.assertIsNone(integrity.non_military_kind(row))
        self.assertEqual(integrity.final_color(row), 'red')

    def test_aramco_attack_denial_or_sanctions_do_not_gain_attack_report_topic(self):
        for title in ('사우디, 아람코 본사 공격 부인', 'EU, 아람코 시설 공격 관련 업체 제재'):
            with self.subTest(title=title):
                self.assertIsNone(integrity._primary_topic(article(title)))

    def test_aramco_aggressive_investment_is_not_a_military_attack(self):
        row = article('아람코, 공격적 투자 확대…원유 사업 경쟁력 강화')
        self.assertIsNone(integrity._primary_topic(row))

    def test_aramco_topic_does_not_invent_an_unstated_country_or_facility(self):
        row = article('Aramco attacked, damage not yet assessed', source='Reuters')
        self.assertEqual(integrity._primary_topic(row), '아람코 · 아람코 공격 보도')

    def test_aramco_attack_negation_stays_attached_to_attack_predicate(self):
        for title in ('Aramco headquarters was not attacked', 'Saudi denies Aramco HQ was attacked',
                      '사우디, 아람코 본사 공격 보도를 부인'):
            with self.subTest(title=title):
                self.assertIsNone(integrity._primary_topic(article(title)))

    def test_english_threat_headline_remains_a_statement_with_past_attacks(self):
        for actor in ('Trump', 'U.S.', 'US'):
            with self.subTest(actor=actor):
                row = article(actor + ' threatens retaliation against Houthis after election', source='Reuters')
                row['description'] = 'Background mentions earlier airstrikes and ongoing attacks in Saudi Arabia.'
                self.assertEqual(integrity.non_military_kind(row), 'military_statement')
                self.assertEqual(integrity.final_color(row), 'yellow')
                self.assertEqual(integrity.topic_label(row), '미국·후티 · 군사 대응·보복 발언')

    def test_final_gate_rechecks_headline_topic_and_statement_color(self):
        inputs = [
            (article('후티 반군, 사우디 아람코 본사 공격 정황…국제유가 긴장'),
             '사우디·후티 · 리야드 미사일 요격', 'red', 'headline event'),
            (article('美 트럼프, 중간선거 다음 후티 반군에 보복 시사 "잊지 않을 것"'),
             '미국·후티 · 군사 대응·보복 발언', 'red', 'statement presented'),
        ]
        for row, topic, color, reason in inputs:
            with self.subTest(reason=reason), tempfile.TemporaryDirectory() as folder, ExitStack() as stack:
                root = Path(folder)
                row['classification_color'] = color
                row['non_military_kind'] = None
                marker = '🔴' if color == 'red' else '🟡'
                text = marker + ' [신규] <b>1. ' + topic + '</b>\n<a href="' + row['link'] + '">원문</a>'
                receipt = evidence.alert_receipt([row], [], NOW, text)
                for attr, name in {'ALERT': 'alert.txt', 'PENDING': 'pending.json', 'AUDIT': 'evidence.json'}.items():
                    stack.enter_context(patch.object(watch, attr, root/name))
                watch.ALERT.write_text(text, encoding='utf-8')
                watch.PENDING.write_text(json.dumps({'ids':[row['id']]}), encoding='utf-8')
                watch.AUDIT.write_text(json.dumps(receipt,ensure_ascii=False), encoding='utf-8')
                stack.enter_context(patch.object(integrity,'_verify'))
                with self.assertRaisesRegex(RuntimeError, reason):
                    integrity.verify_alert()

    def test_weapon_nouns_in_sanctions_are_not_an_attack(self):
        row = article("EU, 러시아 무기망 겨냥 1569개 '역대 최대' 제재…北 미사일 기술자 등 7곳도 추가")
        row['description'] = '우크라이나 전쟁 관련 미사일·드론 핵심 부품 공급업체 826곳과 경영진 743명을 제재했다.'
        _, tags = integrity.score_item(row, NOW)
        self.assertNotIn('확전', tags)
        self.assertIn('제재·압박', tags)
        self.assertEqual(integrity.final_color(row), 'yellow')
        rendered = integrity.build_alert([row], [], NOW)
        self.assertNotIn('🔴', rendered)
        self.assertIn('제재·압박', rendered)
        self.assertIn('새로운 군사작전 개시는 확인되지 않음', rendered)

    def test_condemnation_and_reported_request_are_not_new_airstrikes(self):
        row = article('Israel condemns deadly Houthi attack on Saudi airport amid reports US wants Israel to strike in Yemen',
                      source='All Israel News', link='https://allisraelnews.com/example')
        self.assertEqual(integrity.non_military_kind(row), 'reaction')
        self.assertEqual(integrity.final_color(row), 'yellow')

    def test_explicit_new_military_action_is_preserved(self):
        for title in ('Russia launches strikes after EU sanctions',
                      'Israel condemns Houthi attack and launches airstrikes in Yemen',
                      '사우디, 공항 피격 규탄 후 보복 공습 개시'):
            with self.subTest(title=title):
                self.assertIsNone(integrity.non_military_kind(article(title)))

    def test_sanctions_background_cannot_turn_negotiations_into_actual_attacks(self):
        sanctions = article('EU sanctions Russian missile and drone suppliers')
        sanctions['description'] = 'Russia has conducted missile attacks on civilian infrastructure.'
        negotiation = article('이란, 미국 종전 제안 불충분…협상 조건 이견', source='토큰포스트')
        rendered = integrity.verdict([sanctions, negotiation])
        self.assertNotIn('실제 공격·', rendered)
        self.assertNotIn('신규 변화의 중심은 실제 공격', rendered)

    def test_refinery_denial_and_opponent_attacks_keep_speaker_and_negation(self):
        row = article('젤렌스키 "러 정유시설 이틀간 공격 안 했다…러는 계속 공격" - 뉴스1',
                      source='뉴스1', link='https://news.google.com/rss/articles/fixture')
        self.assertFalse(integrity.future_refinery_policy(row))
        _, tags = integrity.score_item(row, NOW)
        self.assertNotIn('공격확대예고', tags)
        row['tags'] = tags
        self.assertEqual(integrity.non_military_kind(row), 'mixed_restraint')
        text = integrity.build_alert([row], [], NOW)
        self.assertIn('공격 안 했다', text)
        self.assertIn('러는 계속 공격', text)
        self.assertNotIn('공격 확대 방침', text)
        self.assertNotIn('🔴', text)
        self.assertNotIn('🟢', text)
        self.assertIn('휴전 합의·실제 이행이 확인되지는 않음', text)

    def test_explicit_future_refinery_warning_is_yellow_after_final_render(self):
        row = article('젤렌스키, 러시아 정유시설 공격을 강화하고 계속 타격할 것')
        row['description'] = '우크라이나가 러시아의 새 공습 교리에 대응해 정유시설 공격을 강화할 방침이다.'
        self.assertTrue(integrity.future_refinery_policy(row))
        text = integrity.build_alert([row], [], NOW)
        self.assertNotIn('🔴 [', text)
        self.assertIn('🟡 [', text)

    def test_opponent_denial_is_not_reassigned_to_ukraine(self):
        row = article('러시아 "정유시설 공격 안 했다"…우크라이나는 공습 계속')
        self.assertFalse(integrity.refinery_attack_denial(row))

    def test_restraint_and_opponent_attack_clauses_never_become_confirmed_peace(self):
        titles = ('젤렌스키 "트럼프 휴전 언급에 공격 자제했지만 러는 계속" - 연합뉴스',
                  '젤렌스키 "트럼프 에너지 휴전 언급에도 러 공격 계속" - 연합뉴스TV',
                  'Zelensky halted attacks after Trump truce but Russia continues strikes')
        for title in titles:
            with self.subTest(title=title):
                row = article(title, source='연합뉴스')
                self.assertTrue(integrity.mixed_restraint_attack(row))
                self.assertEqual(integrity.final_color(row), 'yellow')
                _, row['tags'] = integrity.score_item(row, NOW)
                text = integrity.build_alert([row], [], NOW)
                self.assertNotIn('🟢', text)
                self.assertIn('양측 휴전 이행 미확인', text)
                metadata_line = next(line for line in text.splitlines() if '<a href=' in line)
                self.assertEqual(metadata_line.count(integrity.KIND_LABELS['mixed_restraint']), 1)

    def test_bilateral_agreement_and_implementation_without_attack_continuation_remains_green(self):
        row = article('러시아·우크라이나, 정식 휴전 합의…양측 공격 중단 이행 확인', source='Reuters')
        self.assertFalse(integrity.mixed_restraint_attack(row))
        self.assertIsNone(integrity.non_military_kind(row))
        self.assertEqual(integrity.final_color(row), 'green')

    def test_opponent_ellipsis_negation_keeps_unilateral_restraint_unconfirmed(self):
        titles = (
            '젤렌스키 "트럼프 휴전 언급에 공격 자제했지만 러는 아냐" - MBC 뉴스',
            '젤렌스키 "공격 자제했지만 러시아는 아니다"',
            '우크라이나, 공격 중단했으나 러시아는 그렇지 않아',
            '이란, 공격 자제했지만 이스라엘은 아님',
            "Zelensky halted attacks after Trump truce but Russia didn't",
            'Ukraine stopped energy strikes while Russia did not',
            'Ukraine paused attacks, but Moscow has not',
        )
        for title in titles:
            with self.subTest(title=title):
                row = article(title, source='MBC 뉴스')
                self.assertTrue(integrity.mixed_restraint_attack(row))
                _, row['tags'] = integrity.score_item(row, NOW)
                text = integrity.build_alert([row], [], NOW)
                self.assertEqual(integrity.final_color(row), 'yellow')
                self.assertNotIn('🟢', text)
                self.assertIn('🟡 [', text)
                self.assertIn('양측 휴전 이행 미확인', text)
                metadata = next(line for line in text.splitlines() if '<a href=' in line)
                self.assertEqual(metadata.count(integrity.KIND_LABELS['mixed_restraint']), 1)

    def test_unrelated_negation_does_not_erase_confirmed_bilateral_ceasefire(self):
        row = article('러시아·우크라이나, 정식 휴전 합의…양측 공격 중단 이행 확인, 재건 완료는 아냐',
                      source='Reuters')
        self.assertFalse(integrity.mixed_restraint_attack(row))
        self.assertIsNone(integrity.non_military_kind(row))
        self.assertEqual(integrity.final_color(row), 'green')

    def test_attack_object_is_not_mistaken_for_the_opponent_actor(self):
        row = article('우크라이나, 공격 자제했지만 테러는 아냐')
        self.assertFalse(integrity.mixed_restraint_attack(row))

    def test_final_gate_rechecks_headline_even_when_saved_kind_and_color_are_wrong(self):
        row = article('젤렌스키 "트럼프 휴전 언급에 공격 자제했지만 러는 아냐" - MBC 뉴스',
                      source='MBC 뉴스')
        row['classification_color'] = 'green'
        row['non_military_kind'] = None
        text = '🟢 [신규] <b>1. 우크라이나·러시아</b>\n<a href="' + row['link'] + '">원문</a>'
        receipt = evidence.alert_receipt([row], [], NOW, text)
        with tempfile.TemporaryDirectory() as folder, ExitStack() as stack:
            root = Path(folder)
            for attr, name in {'ALERT': 'alert.txt', 'PENDING': 'pending.json', 'AUDIT': 'evidence.json'}.items():
                stack.enter_context(patch.object(watch, attr, root / name))
            watch.ALERT.write_text(text, encoding='utf-8')
            watch.PENDING.write_text(json.dumps({'ids': [row['id']]}), encoding='utf-8')
            watch.AUDIT.write_text(json.dumps(receipt, ensure_ascii=False), encoding='utf-8')
            stack.enter_context(patch.object(integrity, '_verify'))
            with self.assertRaisesRegex(RuntimeError, 'WAR_INTEGRITY_GATE.*unilateral restraint'):
                integrity.verify_alert()

    def test_real_attack_and_sanctions_keep_separate_colors(self):
        attack = article('후티, 사우디 공항에 미사일 공격…여행객 부상', source='MBC 뉴스', link='https://imnews.imbc.com/example')
        attack['id'] = 'attack'
        sanctions = article('EU, 러시아 군수 공급업체 제재 확대')
        text = integrity.build_alert([attack, sanctions], [], NOW)
        self.assertRegex(text, r'🔴 \[(?:신규|속보|후속)\].*1\.')
        self.assertRegex(text, r'🟡 \[(?:신규|속보|후속)\].*2\.')

    def test_mbc_visible_and_machine_publication_conflict_is_visible(self):
        row = article("탑승 줄 섰는데 '섬광'‥사우디 공항 또 피격 - MBC 뉴스", source='MBC 뉴스',
                      link='https://imnews.imbc.com/example')
        page = '''<meta property="og:title" content="탑승 줄 섰는데 '섬광'‥사우디 공항 또 피격">
                  <meta property="article:published_time" content="2026-10-13T00:10:00+09:00">
                  <div>입력 2026-10-13 00:15 | 수정 2026-10-13 01:39</div>'''
        self.assertTrue(evidence.attach_article(row, row['link'], page, 'fixture article body'))
        self.assertEqual(row['source_metadata']['publication_status'], 'conflict')
        text = integrity.build_alert([row], [], NOW)
        self.assertIn('보도시각 불일치', text)
        self.assertIn('00:15', text)
        self.assertIn('00:10', text)

    def test_exact_publisher_and_title_are_required_for_body_verification(self):
        row = article('EU, 러시아 군수 공급업체 제재 확대')
        good = '<meta property="og:title" content="EU, 러시아 군수 공급업체 제재 확대">'
        self.assertFalse(evidence.attach_article(row, 'https://other-news.example/article', good, 'body'))
        wrong = '<meta property="og:title" content="사우디 공항 신규 공격 여행객 사망">'
        self.assertFalse(evidence.attach_article(row, row['link'], wrong, 'body'))
        self.assertFalse(row.get('body_verified', False))
        dashed = article('Iran talks - agreement signed by both sides')
        self.assertFalse(evidence.title_matches(dashed, 'Iran talks - agreement rejected by either side'))
        actors = article('Russia attacks Ukraine', source='Reuters')
        self.assertFalse(evidence.title_matches(actors, 'Ukraine attacks Russia'))
        denial = article('이란, 공격 안 한다', source='Reuters')
        self.assertFalse(evidence.title_matches(denial, '이란, 공격 한다'))
        self.assertTrue(evidence.title_matches(actors, 'Russia attacks Ukraine | Reuters'))

    def test_old_origin_date_cannot_be_refreshed_by_recent_rss(self):
        row = article('EU, 러시아 군수 공급업체 제재 확대')
        page = '''<meta property="og:title" content="EU, 러시아 군수 공급업체 제재 확대">
                  <meta property="article:published_time" content="2026-10-10T00:20:00+09:00">'''
        evidence.attach_article(row, row['link'], page, 'fixture body')
        self.assertEqual(integrity.build_alert([row], [], NOW), '')
        self.assertEqual(row['render_withheld'], 'origin_publication_stale_or_future')

    def test_receipt_identifies_rendered_rows_without_marking_deferred_seen(self):
        shown, deferred = article('first'), article('second', link='https://www.fnnews.com/news/second')
        shown['id'], deferred['id'] = 'shown', 'deferred'
        text = '<a href="https://www.fnnews.com/news/example">원문</a>'
        with patch.dict('os.environ', {'WAR_WATCH_CODE_SHA': 'actual-checkout', 'GITHUB_SHA': 'event-sha'}):
            receipt = evidence.alert_receipt([shown, deferred], [], NOW, text)
        self.assertEqual(receipt['code_sha'], 'actual-checkout')
        self.assertEqual([x['id'] for x in receipt['articles'] if x['rendered']], ['shown'])
        self.assertFalse(receipt['articles'][0]['body_verified'])
        shown['source_metadata'] = {'publication_status': 'unavailable'}
        receipt = evidence.alert_receipt([shown], [], NOW, text)
        self.assertEqual(receipt['articles'][0]['publication_basis'], 'discovery_feed')

    def test_run_and_final_gate_only_mark_rendered_article_seen(self):
        now = dt.datetime.now(watch.KST)
        stale = article('EU, 러시아 군수 공급업체 제재 확대', link='https://www.fnnews.com/news/stale')
        shown = article('후티, 사우디 공항에 미사일 공격…여행객 부상',
                        source='MBC 뉴스', link='https://imnews.imbc.com/replay/current')
        for row in (stale, shown):
            row['published'] = format_datetime(now - dt.timedelta(minutes=20))
        stale['source_metadata'] = {'publication_candidates': [
            {'field': 'article:published_time', 'at_kst': (now - dt.timedelta(days=1)).isoformat()}]}
        with tempfile.TemporaryDirectory() as folder, ExitStack() as stack:
            root = Path(folder)
            stack.enter_context(patch.object(watch, 'OUT', root))
            for attr, name in {'STATE': 'state.json', 'ALERT': 'alert.txt', 'PENDING': 'pending.json',
                               'AUDIT': 'evidence.json', 'SUMMARY': 'summary.md'}.items():
                stack.enter_context(patch.object(watch, attr, root / name))
            watch.STATE.write_text('{"seen":["already-confirmed"]}', encoding='utf-8')
            stack.enter_context(patch.object(watch, 'QUERIES', ['fixture']))
            stack.enter_context(patch.object(watch, 'google_news', return_value=([stale, shown], None)))
            stack.enter_context(patch.object(watch, 'score_item', return_value=(90, ['확전'])))
            stack.enter_context(patch.object(watch, 'market_snapshot', return_value=[]))
            stack.enter_context(patch.object(watch, 'translate_ko', side_effect=lambda value: value))
            watch.run()
            integrity.runner.verify_alert()
            pending = json.loads(watch.PENDING.read_text(encoding='utf-8'))
            receipt = json.loads(watch.AUDIT.read_text(encoding='utf-8'))
            self.assertEqual(pending['ids'], [shown['id']])
            self.assertEqual([row['id'] for row in receipt['articles'] if row['rendered']], [shown['id']])
            self.assertNotIn(stale['id'], pending['ids'])
            self.assertEqual(json.loads(watch.STATE.read_text())['seen'], ['already-confirmed'])
            watch.PENDING.write_text(json.dumps({'ids': [stale['id']]}), encoding='utf-8')
            with self.assertRaisesRegex(RuntimeError, 'WAR_INTEGRITY_GATE.*pending'):
                integrity.runner.verify_alert()

    def test_stooq_price_never_uses_yahoo_previous_close(self):
        now = dt.datetime.now(watch.KST)
        yahoo = {'price': 100.0, 'prev': 98.0, 'pct': (100 / 98 - 1) * 100,
                 'asof': now - dt.timedelta(minutes=2), 'source': 'Yahoo Finance 1분봉'}
        stooq = {'price': 100.1, 'asof': now - dt.timedelta(minutes=1), 'source': 'Stooq'}
        with patch.object(market, '_yahoo_quote', return_value=yahoo), patch.object(market, '_stooq_quote', return_value=stooq):
            rows = market.precise_market_snapshot()
        self.assertTrue(rows)
        self.assertTrue(all(row['price'] == 100.0 for row in rows))
        self.assertTrue(all(row['previous_close'] == 98.0 for row in rows))
        self.assertTrue(all(not row['verified'] for row in rows))

    def test_invalid_state_never_resets_seen(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / 'state.json'
            path.write_text('{broken', encoding='utf-8')
            with patch.object(watch, 'STATE', path), self.assertRaisesRegex(RuntimeError, 'unreadable'):
                watch.load_state()
            self.assertEqual(path.read_text(encoding='utf-8'), '{broken')

    def test_invalid_price_or_previous_close_never_reaches_report(self):
        for px, previous in [(0, 98), (100, 0), (-1, 98), (float('nan'), 98), (100, float('inf'))]:
            fixture = {'chart': {'result': [{'meta': {'symbol': 'NQ=F', 'previousClose': previous},
                'timestamp': [int(NOW.timestamp())], 'indicators': {'quote': [{'close': [px]}]}}]}}
            with self.subTest(price=px, previous=previous), patch.object(watch, 'req', return_value=json.dumps(fixture).encode()):
                self.assertIsNone(market._yahoo_quote('NQ=F'))

    def test_provider_comparison_closes_must_agree(self):
        meta = {'symbol': 'DX-Y.NYB', 'previousClose': 102.21, 'chartPreviousClose': 102.589,
                'exchangeTimezoneName': 'America/New_York', 'instrumentType': 'INDEX'}
        fixture = {'chart': {'result': [{'meta': meta, 'timestamp': [int(NOW.timestamp())],
                   'indicators': {'quote': [{'close': [102.263]}]}}]}}
        with patch.object(watch, 'req', return_value=json.dumps(fixture).encode()):
            self.assertIsNone(market._yahoo_quote('DX-Y.NYB'))
        diagnostic = market.QUOTE_DIAGNOSTICS['DX-Y.NYB']
        self.assertEqual(diagnostic['reason'], '제공처 비교종가 필드 불일치')
        self.assertEqual(diagnostic['quote_metadata']['previousClose'], 102.21)
        self.assertEqual(diagnostic['quote_metadata']['chartPreviousClose'], 102.589)

    def test_matching_close_fields_keep_exact_field_and_date_limit(self):
        for fields, expected in [({'previousClose': 98, 'chartPreviousClose': 98}, 'chartPreviousClose'),
                                 ({'previousClose': 98}, 'previousClose')]:
            fixture = {'chart': {'result': [{'meta': {'symbol': 'NQ=F', **fields},
                'timestamp': [int(NOW.timestamp())], 'indicators': {'quote': [{'close': [100]}]}}]}}
            with self.subTest(fields=fields), patch.object(watch, 'req', return_value=json.dumps(fixture).encode()):
                quote = market._yahoo_quote('NQ=F')
            self.assertEqual(quote['previous_close_field'], expected)
            self.assertFalse(quote['previous_close_date_verified'])
            self.assertAlmostEqual(quote['pct'], (100 / 98 - 1) * 100)

    def test_wrong_instrument_is_withheld_even_when_numbers_are_valid(self):
        fixture = {'chart': {'result': [{'meta': {'symbol': 'OTHER', 'previousClose': 98},
            'timestamp': [int(NOW.timestamp())], 'indicators': {'quote': [{'close': [100]}]}}]}}
        with patch.object(watch, 'req', return_value=json.dumps(fixture).encode()):
            self.assertIsNone(market._yahoo_quote('NQ=F'))
        self.assertEqual(market.QUOTE_DIAGNOSTICS['NQ=F']['reason'], '제공처 종목 코드 불일치')

    def test_missing_market_reason_is_visible_and_saved(self):
        statuses = {'DX-Y.NYB': {'name': '달러지수', 'status': 'withheld', 'reason': '제공처 비교종가 필드 불일치'}}
        row = article('EU, 러시아 군수 공급업체 제재 확대')
        with patch.object(watch, 'market_source_status', statuses, create=True):
            text = integrity.build_alert([row], [], NOW)
        self.assertIn('달러지수 (제공처 비교종가 필드 불일치)', text)
        receipt = evidence.alert_receipt([row], [], NOW, text, statuses)
        self.assertEqual(receipt['market_source_status'], statuses)

    def test_future_market_timestamp_is_withheld(self):
        quote = {'price': 100, 'prev': 98, 'pct': 2.0,
                 'asof': dt.datetime.now(watch.KST) + dt.timedelta(hours=1), 'source': 'fixture'}
        with patch.object(market, '_yahoo_quote', return_value=quote), patch.object(market, '_stooq_quote', return_value=None):
            self.assertEqual(market.precise_market_snapshot(), [])

    def test_malformed_rss_is_retried_once_at_the_same_url(self):
        response_bad = Mock()
        response_bad.__enter__ = Mock(return_value=response_bad)
        response_bad.__exit__ = Mock(return_value=False)
        response_bad.read.return_value = b'<html>temporary response</html>'
        response_ok = Mock()
        response_ok.__enter__ = Mock(return_value=response_ok)
        response_ok.__exit__ = Mock(return_value=False)
        response_ok.read.return_value = b'<rss><channel/></rss>'
        opener = Mock()
        opener.open.side_effect = [response_bad, response_ok]
        url = 'https://www.bing.com/news/search?format=rss&q=fixture'
        with patch.object(watch.urllib.request, 'build_opener', return_value=opener), patch.object(watch.time, 'sleep'):
            result = watch.req(url)
        self.assertEqual(result, b'<rss><channel/></rss>')
        self.assertEqual(opener.open.call_count, 2)
        self.assertTrue(all(call.args[0].full_url == url for call in opener.open.call_args_list))

    def test_malformed_json_and_missing_channel_are_not_zero_news(self):
        for url, body in [('https://api.gdeltproject.org/api/v2/doc/doc?format=json', b'not json'),
                          ('https://api.gdeltproject.org/api/v2/doc/doc?format=json', b'[]'),
                          ('https://www.bing.com/news/search?format=rss', b'<rss/>')]:
            with self.subTest(url=url), self.assertRaises(watch.SourcePayloadError):
                watch._validate_source_payload(url, body)


if __name__ == '__main__':
    unittest.main()
