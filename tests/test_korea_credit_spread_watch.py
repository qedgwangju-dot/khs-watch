import datetime as dt
import importlib.util
import pathlib
import unittest
from zoneinfo import ZoneInfo

spec=importlib.util.spec_from_file_location("credit",pathlib.Path(__file__).parents[1]/"scripts/korea_credit_spread_watch.py")
c=importlib.util.module_from_spec(spec);spec.loader.exec_module(c)

def sample(cp_cd=20,credit=60,n=12):
    rows=[]; day=dt.date(2026,9,1)
    for _ in range(n):
        while day.weekday()>=5: day+=dt.timedelta(days=1)
        rates={"cp":3+cp_cd/100,"cd":3,"corp":3.5+credit/100,"gov":3.5}
        rows.append({"date":day.strftime('%Y%m%d'),"rates":rates,"cp_cd":cp_cd,
                     "credit":credit,"rank":c.level(cp_cd,credit)})
        day+=dt.timedelta(days=1)
    return rows

class CreditWatchTests(unittest.TestCase):
    def test_exact_boundary_levels(self):
        for p in ((29.99,69.99,0),(30,0,1),(0,70,1),(49.9,79.9,1),
                  (50,0,2),(0,80,2),(70,0,3),(0,90,3),(100,0,4),(0,120,4)):
            self.assertEqual(c.level(p[0],p[1]),p[2])
    def test_first_baseline(self):
        x=c.decide(sample(),{})
        self.assertTrue(x['send']);self.assertEqual(x['transition'],'최초 기준선')
        y=c.decide(sample(),{'notified_rank':0,'last_alert_signature':x['signature']})
        self.assertFalse(y['send'])
    def test_worsening_immediately(self):
        rows=sample();rows[-1]['rank']=4;rows[-1]['cp_cd']=100
        x=c.decide(rows,{'notified_rank':0})
        self.assertEqual((x['rank'],x['transition']),(4,'위험 상승'))
    def test_severe_three_consecutive(self):
        rows=sample(110,125)
        for i in (1,2): rows[-i].update(cp_cd=70,credit=95,rank=3)
        self.assertEqual(c.recovery(4,rows),4)
        rows[-3].update(cp_cd=70,credit=95,rank=3)
        self.assertEqual(c.recovery(4,rows),3)
    def test_stable_five_days(self):
        rows=sample(45,74)
        for i in range(1,5): rows[-i].update(cp_cd=20,credit=60,rank=0)
        self.assertEqual(c.recovery(1,rows),1)
        rows[-5].update(cp_cd=20,credit=60,rank=0)
        self.assertEqual(c.recovery(1,rows),0)
    def test_both_spreads_must_recover(self):
        self.assertEqual(c.recovery(3,sample(20,85)),3)
    def test_early_signal_once(self):
        rows=sample();rows[-1]['cp_cd']=31
        self.assertTrue(any('10bp' in s for s in c.early(rows)))
        rows[-2]['cp_cd']=32
        self.assertFalse(any('10bp' in s for s in c.early(rows)))
    def test_cp_absolute_threshold(self):
        rows=sample();rows[-2]['rates']['cp']=3.79;rows[-1]['rates']['cp']=4.0
        self.assertTrue(any('4.00%' in s for s in c.early(rows)))
    def test_unique_four_series_only(self):
        rows=[{'ITEM_NAME1':name,'ITEM_CODE1':code} for name,code in
              [('CP(91일)','a1'),('CD(91일)','cd1'),('회사채(3년, AA-)','aa'),('국고채(3년)','gov')]]
        with self.assertRaises(ValueError): c.codes_for(rows)
        for i,r in enumerate(rows): r['ITEM_CODE1']=str(i+1)
        self.assertEqual(set(c.codes_for(rows)),{'cp','cd','corp','gov'})
        with self.assertRaises(ValueError):c.codes_for(rows+[{'ITEM_NAME1':'CP(91일)','ITEM_CODE1':'999'}])
    def test_no_misaligned_dates(self):
        rates={k:{f'202610{d:02d}':3 for d in range(1,12)} for k in c.KINDS}
        rates['cp']={'20261016':4}
        with self.assertRaises(ValueError):
            c.aligned(rates,dt.datetime(2026,10,19,18,tzinfo=ZoneInfo('Asia/Seoul')))
    def test_stale_source(self):
        rates={k:{f'202609{d:02d}':3 for d in range(1,13)} for k in c.KINDS}
        with self.assertRaises(ValueError):
            c.aligned(rates,dt.datetime(2026,10,19,18,tzinfo=ZoneInfo('Asia/Seoul')))
    def test_message_includes_all_and_status(self):
        rows=sample(60,85)
        decision=c.decide(rows,{})
        msg=c.render(rows,decision,dt.datetime(2026,10,19,18,tzinfo=ZoneInfo('Asia/Seoul')))
        for word in ('CP–CD','회사채','국고채','회복선','다음 악화선','817Y002'):
            self.assertIn(word,msg)

if __name__=='__main__':unittest.main()
