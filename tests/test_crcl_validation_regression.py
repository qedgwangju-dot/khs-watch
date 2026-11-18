"""Deterministic rate-direction checks, independent of mutable production state."""
import copy
import json
import pathlib
import unittest
from unittest.mock import patch
from scripts import crcl_directional_summary as fmt
from scripts import crcl_usdc_rate_watch as watch

FIXTURE = pathlib.Path(__file__).parent / 'fixtures' / 'crcl_date_alignment.json'

class RateDirectionRegressionTest(unittest.TestCase):
    def setUp(self):
        self.state = json.loads(FIXTURE.read_text())

    def test_mismatched_dates_withhold_proxy_and_direct_verdict(self):
        for function in (fmt.proxy_rates, fmt.direct_earnings):
            with self.subTest(function=function.__name__):
                label, _, score = function(self.state)
                self.assertEqual((label, score), ('판정 보류', 0))

    def test_aligned_rate_direction_is_preserved(self):
        self.state['sofr']['date'] = self.state['treasury']['date']
        for sofr, treasury, score in [(1, 3, 1), (-1, -3, -1), (1, -3, 0), (0, 0, 0)]:
            with self.subTest(sofr=sofr, treasury=treasury):
                self.state['sofr']['daily_bp'] = sofr
                self.state['treasury']['daily_3m_bp'] = treasury
                self.assertEqual(fmt.proxy_rates(self.state)[2], score)

    def test_missing_rate_date_withholds_verdict(self):
        for section in ('sofr', 'treasury'):
            state = copy.deepcopy(self.state)
            state[section].pop('date')
            self.assertEqual(fmt.proxy_rates(state)[0::2], ('판정 보류', 0))

    def test_direct_proxy_requires_both_exact_observation_dates(self):
        state = self.state
        state['circle']['date'] = state['usdxx']['date']
        state['circle']['_previous_distinct']['date'] = state['usdxx']['_previous_distinct']['date']
        self.assertGreater(fmt.direct_earnings(state)[2], 0)
        state['circle']['date'] = '2026-10-04'
        label, detail, score = fmt.direct_earnings(state)
        self.assertEqual((label, score), ('판정 보류', 0))
        self.assertIn('현재 1일', detail)


    def snapshot_2026_11_18(self):
        state = copy.deepcopy(self.state)
        state['updated_at_kst'] = '2026-11-18T13:23:10+09:00'
        state['circle'] = {
            'date':'2026-11-16','circulation_usd_b':68.0,
            '_previous_distinct':{'date':'2026-11-12','circulation_usd_b':67.9},
        }
        state['usdxx'] = {
            'date':'2026-11-17','sec_yield_7d':3.89,
            '_previous_distinct':{'date':'2026-11-16','sec_yield_7d':3.88},
        }
        state['sofr'] = {'date':'2026-11-16','prev_date':'2026-11-13','rate':3.93,'prev_rate':3.90,'daily_bp':3.0}
        state['treasury'] = {
            'date':'2026-11-17','prev_date':'2026-11-16',
            'three_month':4.33,'prev_three_month':4.34,'daily_3m_bp':-1.0,
            'ten_year':5.10,'prev_ten_year':5.12,'daily_10y_bp':-2.0,
        }
        state['crcl'] = {
            'date':'2026-11-17','prev_date':'2026-11-16',
            'close':54.63,'prev_close':57.65,'daily_pct':-5.24,
            'crosscheck_status':'rounding_difference','crosscheck_close':54.62,
        }
        state['tbx'] = {'date':'2026-11-17','daily_pct':-0.27}
        state['fx'] = {'rate':1335.00,'date':'2026-11-17','source':'한국은행 ECOS'}
        state['errors'] = []
        return state

    def test_dashboard_explicit_up_down_and_no_plus_on_absolute_krw_balance(self):
        state = self.snapshot_2026_11_18()
        body = fmt.build_compact_alert(state, '<b>핵심 변화</b>\n• 준비금 펀드 수익률 +1.0bp\n')
        for text in (
            'USDC 유통량 증가 ↑', '블랙록 준비금 펀드 수익률 상승 ↑',
            'SOFR 상승 ↑', '미 국채 3개월 금리 하락 ↓',
            '미 국채 10년 금리 하락 ↓', 'CRCL 주가 하락 ↓',
            'TBX 가격 하락 ↓',
            '67.9→68.0십억달러', '3.88%→3.89%', '5.12%→5.10%',
            '54.63', '(-5.24%)',
        ):
            with self.subTest(text=text):
                self.assertIn(text, body)
        self.assertIn('약 90조7,800억원', body)
        self.assertNotIn('약 +90조', body)
        self.assertNotIn('ChartExchange·Yahoo 일치', body)
        self.assertIn('차이', body)
        self.assertEqual(fmt.direct_earnings(state)[0], '판정 보류')
        self.assertIsNone(fmt._direct_proxy_pct(state))
        self.assertEqual(fmt.proxy_rates(state)[0], '판정 보류')

    def test_dashboard_stale_source_and_missing_dates_never_fabricate_new_change(self):
        state = self.snapshot_2026_11_18()
        state['errors'] = ['crcl: quote cross-check transport error']
        rendered = fmt.build_compact_alert(state, '')
        self.assertIn('직전 확인값(신규 판정 보류)', rendered)
        self.assertIn('USDC 유통량 증가 ↑', rendered)
        state['usdxx']['date'] = ''
        self.assertEqual(fmt.direct_earnings(state)[0], '판정 보류')
        self.assertIsNone(fmt._direct_proxy_pct(state))

    def test_closing_price_small_difference_uses_yahoo_without_claiming_exact_match(self):
        cx = {
            'date':'2026-11-17','close':54.62,'prev_date':'2026-11-16',
            'daily_pct':-5.26,
        }
        yahoo = {
            'date':'2026-11-17','close':54.63,'prev_date':'2026-11-16',
            'prev_close':57.65,'daily_pct':-5.24,
        }
        with patch.object(watch,'chartexchange_crcl_daily',return_value=cx), \\
             patch.object(watch,'yahoo_daily',return_value=yahoo):
            result = watch.verified_crcl_daily()
        self.assertEqual(result['close'],54.63)
        self.assertEqual(result['daily_pct'],-5.24)
        self.assertEqual(result['crosscheck_status'],'rounding_difference')
        self.assertEqual(result['crosscheck_close'],54.62)

    def test_closing_price_date_mismatch_or_large_gap_does_not_claim_confirmed(self):
        cx = {'date':'2026-11-17','close':54.62,'daily_pct':-5.26}
        with patch.object(watch,'chartexchange_crcl_daily',return_value=cx), \\
             patch.object(watch,'yahoo_daily',return_value={'date':'2026-11-16','close':57.65}):
            with self.assertRaisesRegex(RuntimeError,'date mismatch'):
                watch.verified_crcl_daily()
        with patch.object(watch,'chartexchange_crcl_daily',return_value=cx), \\
             patch.object(watch,'yahoo_daily',return_value={'date':'2026-11-17','close':56.62}):
            with self.assertRaisesRegex(RuntimeError,'discrepancy'):
                watch.verified_crcl_daily()

    def test_telegram_bot_auth_is_not_delivery_receipt(self):
        result = {
            'ok':True,'result':{'message_id':373,'chat':{'id':-1001234567890,'username':'officialchannel'}},
        }
        self.assertEqual(watch.validate_crcl_telegram_response(result,configured_chat='-1001234567890'),373)
        self.assertEqual(watch.validate_crcl_telegram_response(result,configured_chat='@OfficialChannel'),373)
        for response, chat in [
            ({'ok': True, 'result': {'message_id':373}}, '-1001234567890'),
            (result,'-100999999999'),
            (result,'@wrongchannel'),
            ({'ok':True,'result':{'message_id':0,'chat':result['result']['chat']}},'-1001234567890'),
            ({'ok':False,'result':result['result']},'-1001234567890'),
        ]:
            with self.subTest(response=response,chat=chat):
                with self.assertRaises(RuntimeError):
                    watch.validate_crcl_telegram_response(response,configured_chat=chat)

    def test_all_material_change_lines_survive_compaction(self):
        original = (
            '<b>핵심 변화</b>\n'
            + '\n'.join(f'• 별도 근거 {x}' for x in range(9))
            + '\n<b>돈 버는 능력 — 실제 핵심</b>\n'
        )
        changes = fmt._extract_changes(original)
        self.assertEqual(len(changes),9)
        self.assertIn('별도 근거 8', '\n'.join(changes))

    def test_stale_treasury_uses_same_day_tbx_direction(self):
        for move, score in [(0.74, -1), (-0.74, 1)]:
            with self.subTest(move=move):
                self.state['tbx']['daily_pct'] = move
                label, text, actual = fmt.discount_view(self.state)
                self.assertEqual(actual, score)
                self.assertIn('TBX', text)
