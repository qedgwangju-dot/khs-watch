"""Offline regressions from Telegram #323. No live source or send calls."""
import datetime as dt
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
                text = integrity.build_alert([row], [], NOW)
                self.assertNotIn('🟢', text)
                self.assertIn('양측 휴전 이행 미확인', text)

    def test_bilateral_agreement_and_implementation_without_attack_continuation_remains_green(self):
        row = article('러시아·우크라이나, 정식 휴전 합의…양측 공격 중단 이행 확인', source='Reuters')
        self.assertFalse(integrity.mixed_restraint_attack(row))
        self.assertIsNone(integrity.non_military_kind(row))
        self.assertEqual(integrity.final_color(row), 'green')

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
