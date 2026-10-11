"""Historical parser fixtures never disable live-source freshness guards."""
import datetime as dt
import pathlib
import sys
import unittest
from unittest.mock import patch

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / 'scripts'))
import lng_supply_crisis_alert_v34 as monitor

FIXTURE_NOW = dt.datetime(2026, 9, 25, 12, tzinfo=dt.timezone.utc)
TTF = '''실제 이전 최고 최저 날짜 단위 업데이트 주기 71.89 74.94 345 3.37
유럽연합 가스 71.89 -3.05 -4.07%
2026년 9월 25일 EU 가스는'''
JKM = '''실제 이전 최고 최저 날짜 단위 업데이트 주기 25.82 26.385 69.96 2.00
LNG JKM 25.82 -0.57 -2.14%
2026년 9월 25일 LNG JKM'''

class ParserClockRegressionTest(unittest.TestCase):
    def test_historical_fixture_self_validation_survives_clock_rollover(self):
        for year in (2026, 2036):
            with self.subTest(year=year), patch.object(monitor.core, 'now_utc', return_value=dt.datetime(year, 10, 11, tzinfo=dt.timezone.utc)):
                monitor._self_validate_canonical_price_parsers_v34()

    def test_default_live_clock_still_rejects_stale_prices(self):
        with patch.object(monitor.core, 'now_utc', return_value=dt.datetime(2026, 10, 11, tzinfo=dt.timezone.utc)):
            for key, fixture in [('ttf', TTF), ('jkm', JKM)]:
                with self.subTest(key=key), self.assertRaisesRegex(RuntimeError, 'stale source date=2026-09-25'):
                    monitor._parse_te_korean_detail_v34(fixture, key)

    def test_freshness_boundary_and_future_dates(self):
        for key, fixture in [('ttf', TTF), ('jkm', JKM)]:
            for age in (-1, 0, monitor.TE_MAX_AGE_DAYS_V34, monitor.TE_MAX_AGE_DAYS_V34 + 1):
                with self.subTest(key=key, age=age):
                    now = FIXTURE_NOW + dt.timedelta(days=age)
                    if age < 0 or age > monitor.TE_MAX_AGE_DAYS_V34:
                        with self.assertRaisesRegex(RuntimeError, 'stale source date'):
                            monitor._parse_te_korean_detail_v34(fixture, key, now=now)
                    else:
                        self.assertEqual(monitor._parse_te_korean_detail_v34(fixture, key, now=now)['source_date'], dt.date(2026, 9, 25))

    def test_same_page_arithmetic_disagreement_remains_rejected(self):
        with self.assertRaisesRegex(RuntimeError, 'internal values disagree'):
            monitor._parse_te_korean_detail_v34(TTF.replace('-4.07%', '+4.07%'), 'ttf', now=FIXTURE_NOW)

    def test_missing_date_remains_rejected(self):
        with self.assertRaisesRegex(RuntimeError, 'source date not found'):
            monitor._parse_te_korean_detail_v34(TTF.replace('2026년 9월 25일 EU 가스는', ''), 'ttf', now=FIXTURE_NOW)
