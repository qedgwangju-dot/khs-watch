import copy
import pathlib
import sys
import unittest
from datetime import datetime
from zoneinfo import ZoneInfo
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / 'scripts'))
import hbm_memory_axes as m

NOW = datetime(2026, 9, 22, 17, tzinfo=ZoneInfo('Asia/Seoul'))
ITEM = {'source':'TrendForce', 'direct_link':'https://www.trendforce.com/research/example',
        'published_at_kst':'2026-09-22T10:00:00+09:00', 'title':'삼성전자 HBM'}

class EdgeTests(unittest.TestCase):
    def record(self, value):
        return m.make_record('wafer_share', ['trendforce','industry','2027-YE'], value,
                             'pct','2027-YE',ITEM,'reference')
    def test_withdrawn_unsent_change_not_delivered(self):
        baseline = self.record(22)
        state = m.update_state({}, [], NOW, [baseline])
        state = m.update_state(state, [self.record(30)], NOW)
        self.assertTrue(state['pending'])
        state = m.update_state(state, [baseline], NOW)
        self.assertFalse(state['pending'])
        self.assertEqual(state['last_notified'][baseline['key']]['value'],22)
    def test_new_conflict_quarantines_pending_change(self):
        state=m.update_state({},[],NOW,[self.record(22)])
        state=m.update_state(state,[self.record(30)],NOW)
        state=m.update_state(state,[self.record(30),self.record(31)],NOW)
        self.assertFalse(state['pending'])
        self.assertIn('불일치',str(state['coverage']))
    def test_trendforce_name_is_not_year_end(self):
        rows,gaps=m.parse_records(ITEM,'TrendForce HBM wafer input 2027 30%.')
        self.assertEqual(rows,[])
        self.assertTrue(gaps)
    def test_annual_average_not_year_end(self):
        rows,gaps=m.parse_records(ITEM,'TrendForce HBM wafer input year-end annual average 2027 30%.')
        self.assertEqual(rows,[])
        self.assertTrue(gaps)
    def test_public_average_not_daily_high(self):
        raw='''<html><body>Last Update: Sep. 22 2026
        <table><tr><th>Item</th><th>Daily High</th><th>Daily Low</th><th>Session High</th><th>Session Low</th><th>Session Average</th><th>Session Change</th></tr>
        <tr><td>DDR5 RDIMM 32GB 4800/5600/6400</td><td>999</td><td>100</td><td>500</td><td>200</td><td>345.500</td><td>1.0%</td></tr></table></body></html>'''
        rows=m.public_spot_quotes(raw,NOW)
        self.assertEqual(len(rows),1)
        self.assertEqual(rows[0]['value'],345.5)
        self.assertEqual(rows[0]['as_of'],'2026-09-22')
        self.assertEqual(rows[0]['unit'],'USD/module')
    def test_article_content_excludes_navigation_numbers(self):
        raw='''<html><head><meta property="article:published_time" content="2026-09-20T12:00:00+09:00"></head><body>
        <nav>삼성 HBM4 수율 99%</nav><article>삼성 HBM4 24Gb 다이 12단 36GB</article><footer>가격 999</footer></body></html>'''
        body,pub=m.read_document(raw)
        self.assertNotIn('99%',body)
        self.assertNotIn('999',body)
        self.assertEqual(pub,'2026-09-20T12:00:00+09:00')

if __name__=='__main__':unittest.main()
