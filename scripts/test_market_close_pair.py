"""Offline regressions for one daily close message per market. No live sending."""
import asyncio
from collections import deque
import copy
import datetime as dt
import hashlib
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import AsyncMock, patch

import kospi_shock_episode_watch as monitor

FIXTURE = json.loads((Path(__file__).parent / 'test_fixtures/market_close_pair_20261020.json').read_text(encoding='utf-8'))
CLOSE = FIXTURE['close_ts']
NOW = FIXTURE['now_ts']
REAL_DATETIME = dt.datetime


class FixedDatetime(REAL_DATETIME):
    @classmethod
    def now(cls, tz=None):
        return REAL_DATETIME.fromtimestamp(NOW, tz)


class DailyClosePair(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.directory = Path(self.temp.name)
        self.patches = [
            patch.object(monitor.time, 'time', return_value=NOW),
            patch.object(monitor.dt, 'datetime', FixedDatetime),
            patch.object(monitor, 'telegram_send', side_effect=AssertionError('live send disabled')),
            patch('requests.get', side_effect=AssertionError('network disabled')),
            patch('requests.post', side_effect=AssertionError('network disabled')),
            patch('urllib.request.urlopen', side_effect=AssertionError('network disabled')),
            patch.object(monitor, 'DELIVERY_LOG', self.directory / 'delivery.jsonl'),
            patch.object(monitor, 'collect_program_close', side_effect=lambda _token, market, *_args:
                         {'market': market, 'status': 'held', 'reason': 'offline source fixture'}),
        ]
        for item in self.patches:
            item.start()
            self.addCleanup(item.stop)
        self.w = monitor.Watch('offline', [], '', False)
        self.close = REAL_DATETIME.fromtimestamp(CLOSE, monitor.KST)
        self.now = REAL_DATETIME.fromtimestamp(NOW, monitor.KST)
        self.w.idx = deque([tuple(FIXTURE['last_quotes']['KOSPI'])])
        self.w.kosdaq_idx = deque([tuple(FIXTURE['last_quotes']['KOSDAQ'])])
        self.w.attribution = lambda *_: copy.deepcopy(FIXTURE['attributions']['KOSPI'])
        self.w._kosdaq_attribution = lambda *_: copy.deepcopy(FIXTURE['attributions']['KOSDAQ'])
        self.w._run_enrichment = AsyncMock()
        self.w._run_kosdaq_enrichment = AsyncMock()
        self.messages = []

        async def send(stage, ep, observed_ts, text):
            self.messages.append({'stage': stage, 'episode': copy.deepcopy(ep),
                                  'observed_ts': observed_ts, 'text': text})
            return 2000 + len(self.messages)
        self.w._send_event = AsyncMock(side_effect=send)

    def finish(self):
        asyncio.run(self.w._finalize_daily_close(self.close, now=self.now))

    def archive(self, market='KOSPI'):
        key = 'kospi_episode' if market == 'KOSPI' else 'kosdaq_episode'
        self.w._remember_completed_episode(market, copy.deepcopy(FIXTURE[key]),
                                           copy.deepcopy(FIXTURE['attributions'][market]),
                                           FIXTURE['kospi_end_ts'])

    def test_saved_production_case_intraday_ended_kospi_still_closes_with_kosdaq(self):
        # This drives run() itself. The old code ignores this archived KOSPI
        # and sends only KOSDAQ, matching the actual ID888 -> ID891 omission.
        self.assertEqual(FIXTURE['original_close_delivery_markets'], ['KOSDAQ'])
        self.w.daily_close = {'date': FIXTURE['date'], 'plans': {}, 'message_ids': {},
                              'last_completed': {'KOSPI': {
                                  'episode': copy.deepcopy(FIXTURE['kospi_episode']),
                                  'attribution': copy.deepcopy(FIXTURE['attributions']['KOSPI']),
                                  'ended_ts': FIXTURE['kospi_end_ts']}}}
        self.w.episode = None
        self.w.kosdaq_episode = copy.deepcopy(FIXTURE['kosdaq_episode'])
        self.w.seed_backfill = lambda: None
        self.w.seed_kosdaq_backfill = AsyncMock()
        session = {'is_session': True, 'date': FIXTURE['date'],
                   'open': self.close.replace(hour=9, minute=0),
                   'continuous_end': self.close.replace(hour=15, minute=20), 'close': self.close}
        with patch.object(monitor, 'session_state', return_value=session):
            asyncio.run(self.w.run(dt.time(15, 32)))
        self.assertEqual([m['stage'] for m in self.messages], ['close', 'kosdaq_shock_close'])
        self.assertEqual(self.messages[0]['episode']['start_ts'], FIXTURE['kospi_episode']['start_ts'])
        self.assertIn('5,549.99', self.messages[0]['text'])
        self.assertIn('5,514.68', self.messages[0]['text'])
        self.assertIn('15:16:22', self.messages[0]['text'])
        self.assertIn('786.93', self.messages[1]['text'])
        self.assertIn('780.05', self.messages[1]['text'])
        self.assertTrue(self.w.raw['daily_close']['complete'])

    def test_archived_attribution_is_frozen_after_buffers_expire(self):
        self.archive()
        before = copy.deepcopy(self.w.daily_close['last_completed']['KOSPI'])
        self.w.flows.clear()
        self.w.attribution = lambda *_: (_ for _ in ()).throw(AssertionError('do not replace original interval'))
        self.finish()
        self.assertEqual(self.w.daily_close['plans']['KOSPI']['attribution'], before['attribution'])
        self.assertIn('현물은 개인', self.messages[0]['text'])
        self.assertIn('선물은 기관', self.messages[0]['text'])

    def test_archive_copies_episode_and_attribution(self):
        ep = copy.deepcopy(FIXTURE['kospi_episode'])
        att = copy.deepcopy(FIXTURE['attributions']['KOSPI'])
        self.w._remember_completed_episode('KOSPI', ep, att, FIXTURE['kospi_end_ts'])
        ep['low_price'] = 1
        att['spot']['기관'] = 99999
        saved = self.w.daily_close['last_completed']['KOSPI']
        self.assertEqual(saved['episode']['low_price'], 5514.68)
        self.assertNotEqual(saved['attribution']['spot']['기관'], 99999)

    def test_last_completed_event_selected_instead_of_earlier_larger_event(self):
        self.archive()
        later = copy.deepcopy(FIXTURE['kospi_episode'])
        later['start_ts'] += 10
        self.w._remember_completed_episode('KOSPI', later, FIXTURE['attributions']['KOSPI'], FIXTURE['kospi_end_ts'])
        self.finish()
        self.assertEqual(self.messages[0]['episode']['start_ts'], later['start_ts'])

    def test_active_event_takes_priority_over_previous_completed_event(self):
        self.archive()
        active = copy.deepcopy(FIXTURE['kospi_episode'])
        active['start_ts'] += 20
        self.w.episode = active
        self.finish()
        self.assertEqual(self.w.daily_close['plans']['KOSPI']['origin'], 'active')
        self.assertEqual(self.messages[0]['episode']['start_ts'], active['start_ts'])
        self.assertIsNone(self.w.episode)

    def test_both_intraday_ended_markets_receive_close(self):
        self.archive('KOSPI')
        self.archive('KOSDAQ')
        self.finish()
        self.assertEqual(len(self.messages), 2)
        self.assertEqual({p['origin'] for p in self.w.daily_close['plans'].values()}, {'completed_intraday'})

    def test_no_incident_day_still_has_two_explicit_summaries(self):
        self.finish()
        self.assertEqual(len(self.messages), 2)
        for row in self.messages:
            self.assertTrue(row['episode']['daily_summary_only'])
            self.assertIn('기록된 급락 경보 사건 없음', row['text'])
            self.assertNotIn('실제 매도주체', row['text'])

    def test_missing_price_keeps_market_visible_without_invented_close(self):
        self.w.idx.clear()
        self.finish()
        self.assertIn('코스피 장마감 요약', self.messages[0]['text'])
        self.assertIn('마감 시세 확인 보류', self.messages[0]['text'])
        self.assertNotIn('5,553.08', self.messages[0]['text'])
        self.assertEqual(len(self.messages), 2)

    def test_stale_price_not_rendered_as_a_current_close(self):
        self.archive()
        self.w.idx = deque([(CLOSE - 10, 5553.08)])
        self.finish()
        self.assertIn('마감 조회 시세 확인 보류', self.messages[0]['text'])
        self.assertNotIn('5,553.08', self.messages[0]['text'])
        self.assertFalse(self.w.daily_close['plans']['KOSPI']['quote']['available'])

    def test_received_price_labeled_as_observation_not_independent_official_close(self):
        self.archive()
        self.archive('KOSDAQ')
        self.finish()
        for row in self.messages:
            self.assertIn('마감 조회 시세', row['text'])
            self.assertIn('공식 종가 독립 대조는 미완료', row['text'])
            self.assertIn('조회 15:31:', row['text'])

    def test_quote_received_while_program_close_is_loading_is_not_falsely_stale(self):
        # 10/28 production receipt 1413 held an actual 15:32:03.643 KOSDAQ
        # observation of 771.28. The precise pre-await clock was not saved;
        # one second before the observation reproduces the same clock ordering.
        observed_ts = 1793169123.6431866
        close = REAL_DATETIME(2026, 10, 28, 15, 30, tzinfo=monitor.KST)

        class AdvancingDatetime(REAL_DATETIME):
            calls = 0

            @classmethod
            def now(cls, tz=None):
                cls.calls += 1
                at = observed_ts - 1 if cls.calls == 1 else observed_ts + 10
                return REAL_DATETIME.fromtimestamp(at, tz)

        async def prepare(*_args):
            self.w.kosdaq_idx = deque([(observed_ts, 771.28)])

        self.w._prepare_program_close = AsyncMock(side_effect=prepare)
        with patch.object(monitor.dt, 'datetime', AdvancingDatetime):
            asyncio.run(self.w._finalize_daily_close(close))
        quote = self.w.daily_close['plans']['KOSDAQ']['quote']
        self.assertTrue(quote['available'], quote)
        self.assertEqual(quote['observed_price'], 771.28)
        self.assertFalse(quote['independent_official_close_verified'])

    def test_program_source_failure_in_one_market_does_not_skip_other(self):
        def collect(_token, market, *_):
            if market == 'KOSPI': raise RuntimeError('source failure fixture')
            return {'market': market, 'status': 'held', 'reason': 'offline fixture'}
        with patch.object(monitor, 'collect_program_close', side_effect=collect) as source:
            self.finish()
        self.assertEqual(source.call_count, 2)
        self.assertEqual(len(self.messages), 2)
        self.assertIn('source failure fixture', self.messages[0]['text'])
        self.assertIn('코스닥', self.messages[1]['text'])

    def test_one_delivery_failure_attempts_other_then_preserves_failure(self):
        original = self.w._send_event.side_effect
        async def reject(stage, *args):
            if stage == 'close': raise RuntimeError('offline rejection')
            return await original(stage, *args)
        self.w._send_event.side_effect = reject
        with self.assertRaisesRegex(RuntimeError, 'Daily close delivery incomplete'):
            self.finish()
        self.assertEqual([m['stage'] for m in self.messages], ['kosdaq_shock_close'])
        self.assertEqual(set(self.w.daily_close['message_ids']), {'KOSDAQ'})
        self.assertFalse(self.w.raw['daily_close']['complete'])
        self.w._send_event.side_effect = original
        self.finish()
        self.assertEqual([m['stage'] for m in self.messages], ['kosdaq_shock_close', 'close'])
        self.assertTrue(self.w.raw['daily_close']['complete'])

    def test_second_finalization_neither_requeries_nor_resends(self):
        self.finish()
        frozen = copy.deepcopy(self.w.daily_close['plans'])
        with patch.object(monitor, 'collect_program_close', side_effect=AssertionError('no requery')):
            self.finish()
        self.assertEqual(len(self.messages), 2)
        self.assertEqual(self.w.daily_close['plans'], frozen)

    def test_freeze_both_bodies_before_first_send(self):
        original = self.w._send_event.side_effect
        async def inspect(stage, *args):
            self.assertEqual(set(self.w.daily_close['plans']), {'KOSPI', 'KOSDAQ'})
            return await original(stage, *args)
        self.w._send_event.side_effect = inspect
        self.finish()
        for plan in self.w.daily_close['plans'].values():
            self.assertEqual(hashlib.sha256(plan['text'].encode()).hexdigest(), plan['request_body_sha256'])

    def test_handoff_keeps_archived_boundary_plans_and_approved_ids(self):
        self.archive()
        self.w.handoff_path = str(self.directory / 'handoff.json')
        self.finish()
        restored = monitor.Watch('offline', [], '', False)
        restored.load_handoff(self.w.handoff_path)
        self.assertEqual(restored.daily_close, self.w.daily_close)
        restored._send_event = AsyncMock(side_effect=AssertionError('approved close must not resend'))
        asyncio.run(restored._finalize_daily_close(self.close, now=self.now))
        self.assertEqual(set(restored.raw['daily_close']['message_ids']), {'KOSPI', 'KOSDAQ'})

    def test_prior_day_handoff_cannot_suppress_today(self):
        self.archive()
        path = self.directory / 'old.json'
        self.w.save_handoff(path)
        data = json.loads(path.read_bytes())
        data['date'] = '2026-10-19'
        path.write_text(json.dumps(data), encoding='utf-8')
        restored = monitor.Watch('offline', [], '', False)
        restored.load_handoff(path)
        self.assertEqual(restored.daily_close, {})
        self.assertEqual(restored.raw['handoff_loaded']['status'], 'stale_date')

    def test_noon_test_or_following_day_never_sends_close_pair(self):
        for clock, seconds in [(self.close - dt.timedelta(hours=3), None), (self.now, 10),
                               (self.now + dt.timedelta(days=1), None)]:
            asyncio.run(self.w._finalize_daily_close(self.close, seconds, now=clock))
        self.assertEqual(self.messages, [])
        self.assertNotIn('program_close', self.w.raw)

    def test_receipts_and_evidence_keep_each_markets_identity(self):
        self.archive()
        self.w.kosdaq_episode = copy.deepcopy(FIXTURE['kosdaq_episode'])
        self.finish()
        rows = [json.loads(line) for line in (self.directory / 'delivery.jsonl').read_text(encoding='utf-8').splitlines()]
        self.assertEqual([r['market'] for r in rows], ['KOSPI', 'KOSDAQ'])
        for row, market in zip(rows, ['KOSPI', 'KOSDAQ']):
            self.assertEqual(row['evidence']['market_attribution'], FIXTURE['attributions'][market])
            self.assertEqual(row['evidence']['request_body_sha256'], self.w.daily_close['plans'][market]['request_body_sha256'])


if __name__ == '__main__':
    unittest.main()
