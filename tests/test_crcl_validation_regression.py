"""Deterministic rate-direction checks, independent of mutable production state."""
import copy
import json
import pathlib
import unittest
from scripts import crcl_directional_summary as fmt

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

    def test_direct_proxy_alignment_boundary(self):
        state = self.state
        state['circle']['date'] = '2026-10-02'
        state['circle']['_previous_distinct']['date'] = '2026-09-29'
        self.assertGreater(fmt.direct_earnings(state)[2], 0)
        state['circle']['date'] = '2026-10-01'
        self.assertEqual(fmt.direct_earnings(state)[0::2], ('판정 보류', 0))

    def test_stale_treasury_uses_same_day_tbx_direction(self):
        for move, score in [(0.74, -1), (-0.74, 1)]:
            with self.subTest(move=move):
                self.state['tbx']['daily_pct'] = move
                label, text, actual = fmt.discount_view(self.state)
                self.assertEqual(actual, score)
                self.assertIn('TBX', text)
