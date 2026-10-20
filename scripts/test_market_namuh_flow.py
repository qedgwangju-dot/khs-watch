"""Offline replay and boundary tests for actual NAMUH market source captures."""
import base64
import copy
import datetime as dt
import html
import json
import os
from pathlib import Path
import re
import tempfile
import time
import unittest
from unittest.mock import patch

import market_namuh_flow as nh
import market_supplementary_flow as routing

FIXTURE = Path(__file__).with_name('test_fixtures') / 'namuh_market_readback_20261020.json'


def resign(entry):
    raw = json.dumps(entry['response'], ensure_ascii=False).encode()
    entry['raw_base64'], entry['raw_sha256'] = base64.b64encode(raw).decode(), nh.digest(raw)
    return entry


class NamuhSourceTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.env = patch.dict(os.environ, {'MARKET_SOURCE_OFFLINE': '1', 'MARKET_SOURCE_EVIDENCE_DIR': self.temp.name})
        self.env.start(); self.addCleanup(self.env.stop)
        for target in ('requests.get', 'requests.post'):
            blocker = patch(target, side_effect=AssertionError('NETWORK_FORBIDDEN'))
            blocker.start(); self.addCleanup(blocker.stop)
        self.capture = copy.deepcopy(json.loads(FIXTURE.read_text(encoding='utf-8'))['captures']['KOSPI'])
        self.sources = self.capture['sources']

    def derive(self):
        return nh.derive_capture(self.capture)

    def cash(self):
        return nh.parse_cash(self.sources['cash'], self.sources['cash_calibration'], self.sources['cash_reference'], 'KOSPI')

    def futures(self):
        return nh.parse_futures(self.sources['futures'], 'KOSPI')

    def program(self):
        return nh.parse_program(self.sources['program'], {v:self.sources['program_'+v] for v in ('KRX','NXT')}, 'KOSPI')

    def test_actual_two_market_cumulative_replay(self):
        captures = json.loads(FIXTURE.read_text(encoding='utf-8'))['captures']
        for market, capture in captures.items():
            result = nh.derive_capture(capture)
            self.assertTrue(result['complete'], (market, result))
            self.assertFalse(result['interval_eligible'])
        self.assertEqual(self.cash()['values']['개인'], 13088.37)
        self.assertEqual(self.cash()['values']['투신'], -2509.8)
        self.assertEqual(self.program()['values']['전체'], -6064.19)
        self.assertEqual(self.futures()['values']['투신'], -2897)

    def test_cash_unit_is_exact_clock_calibration_not_magnitude(self):
        proof = self.cash()['calibration']
        self.assertEqual(proof['raw_to_won'], 1_000_000)
        self.assertGreaterEqual(proof['same_clock_actor_count'], 10)
        self.assertFalse(proof['current_value_independently_verified'])
        self.assertEqual(proof['calibration_scope'], 'KRX')

    def test_cash_foreign_group_is_separate_from_kiwoom_main_foreign(self):
        self.assertEqual(self.cash()['values']['외국인계'], -7326.15)
        self.assertNotIn('외국인', self.cash()['values'])

    def test_period_cumulative_selector_never_accepted_as_daily(self):
        self.sources['cash']['request']['cycle_cls_code'] = '3'
        with self.assertRaises(ValueError): self.cash()

    def test_wrong_cash_market_rejected(self):
        self.sources['cash']['request']['mrkt_cls_code'] = '2'
        with self.assertRaises(ValueError): self.cash()

    def test_wrong_cash_venue_rejected(self):
        self.sources['cash']['request']['market_cd'] = 'KRX'
        with self.assertRaises(ValueError): self.cash()

    def test_latest_stale_row_not_replaced_with_other_row(self):
        source = self.sources['cash']
        source['response']['Output_0'][0]['bsop_hour'] = '26/10/19'
        resign(source)
        with self.assertRaises(ValueError): self.cash()

    def test_daily_date_and_timez_conflict_rejected(self):
        source = self.sources['cash']
        source['response']['Output_0'][0]['timez12'] = '261019000000'
        resign(source)
        with self.assertRaises(ValueError): self.cash()

    def test_missing_actor_does_not_become_zero(self):
        source = self.sources['cash']
        source['response']['Output_0'][0].pop('ivtr_val')
        resign(source)
        with self.assertRaises(ValueError): self.cash()

    def test_true_cash_zero_is_preserved(self):
        source = self.sources['cash']
        for key in list(source['response']['Output_0'][0]):
            if key.endswith('_val'): source['response']['Output_0'][0][key] = 0
        resign(source)
        self.assertEqual(self.cash()['values'], dict.fromkeys(nh.ACTORS, 0))

    def test_broken_institution_sum_rejected(self):
        source = self.sources['cash']
        source['response']['Output_0'][0]['ivtr_val'] += 10
        resign(source)
        with self.assertRaises(ValueError): self.cash()

    def test_raw_hash_change_rejected(self):
        self.sources['cash']['raw_sha256'] = '0'*64
        with self.assertRaises(ValueError): self.cash()

    def test_business_error_with_http_200_rejected(self):
        source = self.sources['cash']
        source['response']['rsp_msg'] = '이용 권한이 없습니다.'
        resign(source)
        with self.assertRaises(ValueError): self.cash()

    def test_not_limited_to_one_success_code(self):
        source = self.sources['cash']
        source['response']['rsp_cd'] = '00218'
        resign(source)
        self.assertTrue(self.cash()['unit_verified'])

    def test_unknown_history_pagination_state_rejected(self):
        self.sources['cash']['response_headers'].pop('cts_flag')
        with self.assertRaises(ValueError): self.cash()

    def test_history_pagination_does_not_mean_missing_current_market_actors(self):
        self.assertEqual(self.sources['cash']['response_headers']['cts_flag'], 'Y')
        self.assertTrue(self.cash()['unit_verified'])

    def test_scale_changed_by_1000_rejected(self):
        source = self.sources['cash_calibration']
        for row in source['response']['Output_0']:
            for field in list(row):
                if field.endswith('_val'): row[field] *= 1000
        resign(source)
        with self.assertRaises(ValueError): self.cash()

    def test_reference_venue_mismatch_rejected(self):
        self.sources['cash_reference']['request']['tradeType'] = 'NXT'
        with self.assertRaises(ValueError): self.cash()

    def test_no_nearby_clock_substitution_for_unit_calibration(self):
        source = self.sources['cash_calibration']
        for row in source['response']['Output_0']:
            row['bsop_hour'] = '07:00:00'
            row['timez12'] = '000000070000'
        resign(source)
        with self.assertRaises(ValueError): self.cash()

    def test_duplicate_reference_actor_rejected(self):
        source = self.sources['cash_reference']
        first = source['response']['content'][0]
        first['netAmounts'].append(copy.deepcopy(first['netAmounts'][0]))
        resign(source)
        with self.assertRaises(ValueError): self.cash()

    def test_futures_quantity_does_not_become_won(self):
        value = self.futures()
        self.assertEqual(value['unit'], '계약')
        self.assertFalse(value['amount_in_won_verified'])
        self.assertFalse(value['interval_eligible'])
        self.assertEqual(value['product_label'], '선물(나무구분3)')

    def test_wrong_futures_product_rejected(self):
        self.sources['futures']['request']['mrkt_cls_code'] = '6'
        with self.assertRaises(ValueError): self.futures()

    def test_futures_money_selector_rejected(self):
        self.sources['futures']['request']['opt_cls_code'] = '1'
        with self.assertRaises(ValueError): self.futures()

    def test_futures_fractional_contracts_rejected(self):
        source = self.sources['futures']
        source['response']['Output_0'][0]['ivtr_val'] = 1.1
        resign(source)
        with self.assertRaises(ValueError): self.futures()

    def test_futures_reconciliation_no_rounding_tolerance(self):
        source = self.sources['futures']
        source['response']['Output_0'][0]['prsn_val'] += 1
        resign(source)
        with self.assertRaises(ValueError): self.futures()

    def test_futures_true_zero_remains_zero(self):
        source = self.sources['futures']
        for key in list(source['response']['Output_0'][0]):
            if key.endswith('_val'): source['response']['Output_0'][0][key] = 0
        resign(source)
        self.assertEqual(self.futures()['values']['외국인계'], 0)

    def test_program_uses_nine_latest_raw_amounts(self):
        value = self.program()
        self.assertTrue(value['independent_latest_cumulative_amounts_verified'])
        self.assertFalse(value['source_time_verified'])
        self.assertFalse(value['interval_eligible'])
        self.assertFalse(value['investor_breakdown_available'])
        self.assertEqual(set(value['independent_asof_clocks']), {'KRX','NXT'})

    def test_program_different_venue_asof_clocks_not_one_source_clock(self):
        self.assertFalse(self.program()['same_clock_verified'])

    def test_program_buy_sell_arithmetic_rejected(self):
        source = self.sources['program']
        source['response']['Output_0'][0]['tot_ntby_qty'] += 30
        resign(source)
        with self.assertRaises(ValueError): self.program()

    def test_program_inconsistent_independent_amounts_rejected(self):
        source = self.sources['program']
        row = source['response']['Output_0'][0]
        for key in list(row):
            if key != 'bsop_date': row[key] *= 1000
        resign(source)
        with self.assertRaises(ValueError): self.program()

    def test_program_reference_stale_date_rejected(self):
        source = self.sources['program_KRX']
        source['response']['content'][0]['bizdate'] = '20261019'
        resign(source)
        with self.assertRaises(ValueError): self.program()

    def test_program_reference_wrong_market_rejected(self):
        self.sources['program_NXT']['request']['krxMarketType'] = 'KOSDAQ'
        with self.assertRaises(ValueError): self.program()

    def test_no_refreshed_receipt_time_when_reusing_source_captures(self):
        self.capture['received_ts'] += 50
        with self.assertRaises(ValueError): self.derive()

    def bundle(self):
        result = self.derive()
        result['evidence'] = nh.retain_capture(self.capture)
        return result

    def test_render_reopens_sources_and_fits_budget(self):
        for market, capture in json.loads(FIXTURE.read_text(encoding='utf-8'))['captures'].items():
            result = nh.derive_capture(capture)
            result['evidence'] = nh.retain_capture(capture)
            text = '\n'.join(nh.lines(result, market, result['received_ts']+1))
            plain = html.unescape(re.sub('<[^>]+>', '', text))
            self.assertLessEqual(len(plain), 290)
            self.assertLessEqual(3800+len(plain), 4096)
            self.assertIn('구간수급 아님', text)
            self.assertIn('프로그램 주체·선물금액 미확인', text)
            self.assertIn('외인계', text)

    def test_render_tampered_amount_rejected_despite_old_hash(self):
        result = self.bundle()
        result['components']['cash']['values']['외국인계'] = 88888888
        text = '\n'.join(nh.lines(result, 'KOSPI', result['received_ts']+1))
        self.assertIn('확인 보류', text)
        self.assertNotIn('88,888', text)

    def test_render_tampered_evidence_rejected(self):
        result = self.bundle()
        Path(result['evidence']['path']).write_text('{}', encoding='utf-8')
        self.assertIn('확인 보류', '\n'.join(nh.lines(result, 'KOSPI', result['received_ts']+1)))

    def test_stale_render_not_freshened_by_cache(self):
        result = self.bundle()
        self.assertIn('확인 보류', '\n'.join(nh.lines(result, 'KOSPI', result['received_ts']+121)))
        nh._OBSERVATIONS['KOSPI'] = {'checked_ts':time.time(),'result':result}
        self.addCleanup(nh._OBSERVATIONS.clear)
        self.assertIs(nh.current('KOSPI'), result)
        self.assertEqual(nh.current('KOSPI')['received_ts'], self.capture['received_ts'])

    def test_one_held_component_preserves_other_verified_components(self):
        self.sources.pop('program_NXT')
        self.capture['received_ts'] = max(x['received_ts'] for x in self.sources.values())
        result = self.derive()
        self.assertFalse(result['complete'])
        self.assertTrue(result['components']['cash']['unit_verified'])
        self.assertTrue(result['components']['futures']['unit_verified'])
        self.assertEqual(result['components']['program']['status'], 'held')

    def test_source_io_error_does_not_stop_existing_price_path(self):
        snap = {'market':'KOSPI','price':1234,'현물':{'old':'LS'},'errors':{'지수선물':'old problem'}}
        with patch.object(nh, 'configured', return_value=True), patch.object(nh, 'current', side_effect=OSError('disk unavailable')):
            result = nh.enrich_snapshot(snap, 'KOSPI')
        self.assertEqual(result['price'], 1234)
        self.assertEqual(result['현물'], {'old':'LS'})
        self.assertEqual(result['errors']['지수선물'], 'old problem')

    def test_namuh_configured_routes_without_kiwoom_query(self):
        with patch.object(nh, 'configured', return_value=True), patch.object(nh, 'current', return_value={'provider':'Namuh'}) as collect, patch.object(routing.kiwoom, 'optional_cash') as old:
            self.assertEqual(routing.optional_cash('KOSPI'), {'provider':'Namuh'})
            collect.assert_called_once_with('KOSPI'); old.assert_not_called()

    def test_unconfigured_keeps_legacy_provider(self):
        with patch.object(nh, 'configured', return_value=False), patch.object(routing.kiwoom, 'optional_cash', return_value={'provider':'Kiwoom'}) as old:
            self.assertEqual(routing.optional_cash('KOSPI')['provider'], 'Kiwoom')
            old.assert_called_once_with('KOSPI')

    def test_only_readonly_allowlist_and_documented_inputs(self):
        with self.assertRaises(ValueError): nh._validate_request('/krstock/order/v1/cash', {'market_cd':'KRX'})
        inputs = nh.investor_request('KOSPI'); inputs['act_no'] = 'never'
        with self.assertRaises(ValueError): nh._validate_request(nh.INVESTORS, inputs)

    def test_token_cache_encrypted_and_reused_without_oauth(self):
        with patch.dict(os.environ, {'NHPLUG_APP_KEY':'fixture-key','NHPLUG_APP_SECRET':'fixture-secret','NHPLUG_TOKEN_CACHE_DIR':self.temp.name}):
            path, cipher, scope = nh._cache()
            data = {'scope':scope,'access_token':'fixture-token-do-not-log','expires_at':time.time()+1000}
            path.write_bytes(cipher.encrypt(json.dumps(data).encode()))
            self.assertNotIn(b'fixture-token', path.read_bytes())
            with patch.object(nh, 'configured', return_value=True), patch.object(nh, '_TOKEN', ''), patch.object(nh, '_TOKEN_UNTIL', 0):
                self.assertEqual(nh._token(), data['access_token'])

    def test_corrupt_cache_does_not_issue_another_token(self):
        with patch.dict(os.environ, {'NHPLUG_APP_KEY':'fixture-key','NHPLUG_APP_SECRET':'fixture-secret','NHPLUG_TOKEN_CACHE_DIR':self.temp.name}):
            path, _, _ = nh._cache(); path.write_bytes(b'broken')
            with patch.object(nh, 'configured', return_value=True), patch.object(nh, '_TOKEN', ''), patch.object(nh, '_TOKEN_UNTIL', 0):
                with self.assertRaisesRegex(ValueError, '캐시'): nh._token()


if __name__ == '__main__':
    unittest.main()
