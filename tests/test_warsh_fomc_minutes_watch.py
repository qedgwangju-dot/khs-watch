import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import warsh_fomc_minutes_watch as watch


class TestMinutes(unittest.TestCase):
    def test_calendar_release_requires_posting(self):
        posted = '<a href="/monetarypolicy/fomcminutes20260916.htm">HTML</a> (Released October 07, 2026)'
        pending = '<a href="/monetarypolicy/fomcminutes20260916.htm">HTML</a>'
        self.assertEqual(watch.official_release_date(posted, '2026-09-16'), '2026-10-07')
        self.assertIsNone(watch.official_release_date(pending, '2026-09-16'))

    def test_meeting_date_distinct_from_release(self):
        regex = watch.meeting_date_pattern('2026-09-16')
        self.assertRegex('September 15-16, 2026', regex)
        self.assertNotRegex('October 7, 2026', regex)

    def test_no_false_new_decision(self):
        signals = {k:False for k in (
            'all_support','unanimous_vote','most_yearend','many_risk','number_modal',
            'several_not_restrictive','couple_neutral','ai_inflation','ai_core_goods',
            'ai_private_debt_term_premium','pce_3m_warning','pce_methodology',
            'few_treasury','limit_footprint'
        )}
        from unittest.mock import patch
        with patch.object(watch,'load',return_value={}):
            msg = watch.message('2026-09-16',watch.minutes_url('2026-09-16'),
                                'https://www.federalreserve.gov/newsevents/pressreleases/monetary20261007a.htm',
                                '2026-10-07',signals)
        self.assertIn('QT 재개',msg)
        self.assertIn('10월 27',msg)
        self.assertNotIn('대부분(most)',msg)


if __name__=='__main__':
    unittest.main()
