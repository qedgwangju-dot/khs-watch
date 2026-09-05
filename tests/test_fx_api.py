import datetime as dt
import importlib.util
import pathlib
import sys
import unittest
from unittest.mock import patch
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / 'scripts'))
import fx_api as fx

class FxTest(unittest.TestCase):
    def setUp(self):
        fx._CACHE.clear()
        self.now=dt.datetime(2026,9,5,6,tzinfo=dt.timezone.utc)
    def row(self, rate=1400, date='2026-09-04', base='USD'):
        return [{'date':date,'base':base,'quote':'KRW','rate':rate}]
    def er(self, rate=1401):
        return {'result':'success','base_code':'USD','time_last_update_unix':int(self.now.timestamp())-100,'rates':{'KRW':rate}}
    def test_weekend_preserves_date_and_one_snapshot(self):
        with patch.object(fx,'_json',side_effect=[self.row(),self.er()]) as api:
            q=fx.daily_krw(now=self.now)
            self.assertEqual(q.date,'2026-09-04')
            self.assertEqual(q.rate,1400)
            self.assertIn('일일 기준',q.basis)
            self.assertIs(q,fx.daily_krw(now=self.now))
            self.assertEqual(api.call_count,2)
    def test_fallback_with_actual_provider(self):
        with patch.object(fx,'_json',side_effect=[OSError(),self.er()]):
            q=fx.daily_krw(now=self.now)
            self.assertEqual(q.rate,1401)
            self.assertIn('ExchangeRate-API',q.source)
    def test_never_fixed_fallback(self):
        with patch.object(fx,'_json',side_effect=OSError()):
            with self.assertRaises(RuntimeError):fx.daily_krw(now=self.now)
    def test_invalid_values_dates_and_currency_rejected(self):
        for payload in [self.row(float('nan')),self.row(-1),self.row(date='2026-08-01'),self.row(date='2026-09-06'),self.row(base='JPY')]:
            fx._CACHE.clear()
            with patch.object(fx,'_json',side_effect=[payload,OSError()]):
                with self.assertRaises(RuntimeError):fx.daily_krw(now=self.now)
    def test_same_date_disagreement_blocks(self):
        with patch.object(fx,'_json',side_effect=[self.row(date='2026-09-05'),self.er(1600)]):
            with self.assertRaises(RuntimeError):fx.daily_krw(now=self.now)
    def test_future_timestamp_rejected(self):
        payload=self.er();payload['time_last_update_unix']=int(self.now.timestamp())+1
        with patch.object(fx,'_json',side_effect=[OSError(),payload]):
            with self.assertRaises(RuntimeError):fx.daily_krw(now=self.now)
if __name__=='__main__':unittest.main()
