"""Real-value source fixture and independent tamper/coverage regressions. No network."""
import copy
import base64
import hashlib
import json
from pathlib import Path
import unittest

from kofia_liquidity_source_guard import validate, SIDS

FIXTURE = json.loads(Path('tests/fixtures/kofia_source_20261012.json').read_text(encoding='utf-8'))


def rewrite(record, mutate):
    value = json.loads(record['response_text'])
    mutate(value)
    record['response_text'] = json.dumps(value, ensure_ascii=False, separators=(',', ':'))
    record['response_sha256'] = hashlib.sha256(record['response_text'].encode()).hexdigest()
    record['response_body_base64'] = base64.b64encode(record['response_text'].encode()).decode()
    record['response_bytes'] = len(record['response_text'].encode())


class SourceTests(unittest.TestCase):
    def setUp(self):
        self.evidence = copy.deepcopy(FIXTURE['evidence'])
        self.pending = copy.deepcopy(FIXTURE['pending'])

    def test_actual_20261012_values_and_common_comparison_dates(self):
        result = validate(self.evidence, self.pending)
        self.assertEqual(result['reference_dates'], ['20261012','20261008','20261007','20261006','20261002','20261001'])
        self.assertEqual(result['values']['mmf']['d1'], -2918091)
        self.assertEqual(result['values']['mmf']['d5'], 20425443)
        self.assertEqual(result['values']['forced']['value'], 27083)

    def test_source_hash_change_is_rejected(self):
        self.evidence['requests'][0]['response_text'] += ' '
        with self.assertRaisesRegex(RuntimeError, 'hash mismatch'): validate(self.evidence, self.pending)

    def test_pending_delta_change_is_rejected_even_with_same_declared_source(self):
        self.pending['values']['mmf']['d1'] = 2918091
        with self.assertRaisesRegex(RuntimeError, 'pending differs'): validate(self.evidence, self.pending)

    def test_wrong_request_unit_is_rejected(self):
        record = next(r for r in self.evidence['requests'] if 'dmSearch' in r['payload'])
        record['payload']['dmSearch']['tmpV40'] = '1'
        with self.assertRaisesRegex(RuntimeError, 'request unit'): validate(self.evidence, self.pending)

    def test_redirect_is_rejected(self):
        self.evidence['requests'][0]['response_url'] = 'https://other.example/meta/getSrvData.do'
        with self.assertRaisesRegex(RuntimeError, 'redirect mismatch'): validate(self.evidence, self.pending)

    def test_mmf_net_asset_selector_is_not_principal_balance(self):
        record = next(r for r in self.evidence['requests'] if r['payload'].get('dmSearch', {}).get('OBJ_NM') == SIDS['mmf']+'BO')
        record['payload']['dmSearch']['tmpV39'] = '2'
        with self.assertRaisesRegex(RuntimeError, 'principal balance'): validate(self.evidence, self.pending)

    def test_unreported_date_selector_is_rejected(self):
        record = next(r for r in self.evidence['requests'] if r['payload'].get('dmSearch', {}).get('OBJ_NM') == SIDS['cma']+'BO')
        record['payload']['dmSearch']['tmpV1'] = 'other'
        with self.assertRaisesRegex(RuntimeError, 'published-date series'): validate(self.evidence, self.pending)

    def test_missing_cma_comparison_point_is_rejected(self):
        self.evidence['requests'] = [r for r in self.evidence['requests'] if not (
            r['payload'].get('dmSearch', {}).get('OBJ_NM') == SIDS['cma']+'BO'
            and r['payload']['dmSearch']['tmpV45'] == '20261001')]
        with self.assertRaisesRegex(RuntimeError, 'missing dated cma'): validate(self.evidence, self.pending)

    def test_credit_skipped_date_is_rejected(self):
        record = next(r for r in self.evidence['requests'] if r['payload'].get('dmSearch', {}).get('OBJ_NM') == SIDS['credit']+'BO')
        rewrite(record, lambda value: value.update(ds1=[r for r in value['ds1'] if r['TMPV1'] != '20261007']))
        with self.assertRaisesRegex(RuntimeError, 'credit dates'): validate(self.evidence, self.pending)

    def test_ambiguous_mmf_total_is_rejected(self):
        record = next(r for r in self.evidence['requests'] if r['payload'].get('dmSearch', {}).get('OBJ_NM') == SIDS['mmf']+'BO')
        def duplicate(value):
            value['ds1'].append(copy.deepcopy(next(r for r in value['ds1'] if r.get('TMPV98') == '99')))
        rewrite(record, duplicate)
        with self.assertRaisesRegex(RuntimeError, 'ambiguous mmf'): validate(self.evidence, self.pending)

    def test_missing_official_balance_does_not_become_zero(self):
        record = next(r for r in self.evidence['requests'] if r['payload'].get('dmSearch', {}).get('OBJ_NM') == SIDS['deposit']+'BO')
        rewrite(record, lambda value: value['ds1'][0].update(TMPV2=None))
        with self.assertRaisesRegex(RuntimeError, 'numeric type'): validate(self.evidence, self.pending)

    def test_boolean_pending_numeric_type_is_rejected(self):
        self.pending['values']['deposit']['d1'] = False
        with self.assertRaisesRegex(RuntimeError, 'numeric type'): validate(self.evidence, self.pending)

    def test_mmf_published_daily_disagreement_is_rejected(self):
        record = next(r for r in self.evidence['requests'] if r['payload'].get('dmSearch', {}).get('OBJ_NM') == SIDS['mmf']+'BO'
                      and r['payload']['dmSearch']['tmpV34'] == '20261012')
        def change(value):
            next(r for r in value['ds1'] if r.get('TMPV98') == '99')['TMPV6'] += 100
        rewrite(record, change)
        with self.assertRaisesRegex(RuntimeError, 'daily change differs'): validate(self.evidence, self.pending)

    def test_legitimate_metadata_lag_waits_without_pending_alert(self):
        self.evidence['phase'] = 'alignment_pending'
        record = next(r for r in self.evidence['requests'] if r['payload'].get('dmSearchData', {}).get('strSvrId') == SIDS['mmf'])
        rewrite(record, lambda value: next(r for r in value['dsLatestDate'] if r['TMPV1']=='RD').update(TMPV2='20261013'))
        self.evidence['latest_dates']['mmf'] = '20261013'
        self.assertTrue(validate(self.evidence)['alignment_pending'])
        with self.assertRaisesRegex(RuntimeError, 'pending-date'): validate(self.evidence, self.pending)

    def test_future_metadata_is_not_normal_waiting(self):
        self.evidence['phase'] = 'alignment_pending'
        record = next(r for r in self.evidence['requests'] if 'dmSearchData' in r['payload'])
        rewrite(record, lambda value: next(r for r in value['dsLatestDate'] if r['TMPV1']=='RD').update(TMPV2='20261201'))
        with self.assertRaisesRegex(RuntimeError, 'future official date'): validate(self.evidence)

    def test_pending_query_time_change_is_rejected(self):
        self.pending['queried_at_kst'] = '2026-10-12T00:00:00+09:00'
        with self.assertRaisesRegex(RuntimeError, 'query time differs'): validate(self.evidence, self.pending)


if __name__ == '__main__':
    unittest.main()
