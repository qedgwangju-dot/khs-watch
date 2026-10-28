import pathlib,sys,unittest
from datetime import datetime
sys.path.insert(0,str(pathlib.Path(__file__).resolve().parents[1]/'scripts'))
import hbm_memory_axes as w
class HynixLTAWatchTests(unittest.TestCase):
    def item(self,url=None):
        return {'direct_link':url or w.HYNIX_Q3_2026_URL,
                'published_at_kst':'2026-10-28T08:45:00+09:00','source':'SK hynix'}
    def issuer(self):
        return ("SK hynix announced revenues of 104.6155 trillion won, operating profit of 83.3338 trillion won. "
            "HBM4 shipments began in earnest. SK hynix will ramp up M15X to maximum capacity by the end of the year. "
            "HBM4 to surpass HBM3E in both shipment volume and revenue in Q4. "
            "The 321-layer process will account for more than half domestic NAND production capacity in Q4. "
            "SK hynix has currently signed LTAs with 14 major customers. "
            "The LTA volume corresponds to more than 50% of total production capacity for 2027 and 2028. "
            "The pricing reflects market conditions within a price range agreed upon with customers.")
    def test_lta_contract_has_correct_denominator_and_no_fake_full_booking(self):
        r=next(x for x in w.parse_skhynix_q3_2026_official(self.item(),self.issuer()) if x['axis']=='skhynix_lta_2026')
        v=r['value']
        self.assertEqual(v['signed_customer_count'],14)
        self.assertEqual(v['contracted_capacity_strictly_above_pct'],50)
        self.assertEqual(v['contract_scope'],'2027_2028_total_capacity_not_HBM_only')
        self.assertFalse(v['all_2029_production_signed'])
        self.assertIsNone(v['deposits_amount_krw'])
        self.assertEqual(v['named_customers_confirmed'],[])
    def test_quarter_revenue_and_hbm4_plans_not_actual(self):
        r=next(x for x in w.parse_skhynix_q3_2026_official(self.item(),self.issuer()) if x['axis']=='skhynix_hbm4_q4_2026')
        v=r['value']
        self.assertEqual(v['q3_revenue_krw'],104615500000000)
        self.assertTrue(v['hbm4_q4_ramp_expected'])
        self.assertFalse(v['hbm4_16hi_shipment_confirmed'])
        self.assertFalse(v['m17_equipment_move_in_confirmed'])
        self.assertIsNone(v['hbm4_yield_pct_confirmed'])
    def test_nonissuer_article_cannot_claim_official_sales(self):
        self.assertEqual(w.parse_skhynix_q3_2026_official(
            self.item('https://www.yna.co.kr/article'),self.issuer()),[])
    def test_short_headline_not_enough_for_fake_lta(self):
        self.assertEqual(w.parse_skhynix_q3_2026_official(self.item(),
            'SK hynix signs 14 customer long-term agreement and 50% HBM'),[])
    def test_2029_press_is_negotiations_not_signed(self):
        i=self.item(w.HYNIX_2029_PRESS_URLS[0])
        txt=('SK하이닉스는 2029년까지 D램과 HBM 물량 사실상 완판이라고 밝혔다. '
             '이미 확보한 장기공급계약(LTA)과 고객사와 협의 중인 수요를 종합했다.')
        r=w.parse_skhynix_2029_earnings_call_news(i,txt)[0]
        self.assertFalse(r['value']['firm_signed_for_all_output'])
        self.assertTrue(r['value']['includes_unsigned_customer_negotiations'])
        self.assertEqual(r['evidence'],'reported')
    def test_2029_reprint_without_negotiations_does_not_claim_sales(self):
        self.assertFalse(w.parse_skhynix_2029_earnings_call_news(
            self.item(w.HYNIX_2029_PRESS_URLS[0]),'SK하이닉스 2029년 완판 LTA 100% 서명 확정'))
    def test_new_lta_once_and_repeated_official_release_silent(self):
        rows=w.parse_skhynix_q3_2026_official(self.item(),self.issuer())
        now=datetime(2026,10,28,13,0,0)
        state=w.update_state({},rows,now,[])
        self.assertEqual(len(state['pending']),2)
        for k in list(state['pending']):
            state['last_notified'][k]=state['pending'][k]['record']
            del state['pending'][k]
        state2=w.update_state(state,rows,now,[])
        self.assertEqual(state2['pending'],{})
    def test_new_customer_count_material(self):
        a=w.parse_skhynix_q3_2026_official(self.item(),self.issuer())[0]
        b=w.parse_skhynix_q3_2026_official(self.item(),self.issuer().replace('LTAs with 14','LTAs with 15'))[0]
        self.assertTrue(any('14→15' in x for x in w.comparison(a,b)))
    def test_alert_message_scopes_and_source(self):
        r=w.parse_skhynix_q3_2026_official(self.item(),self.issuer())[0]
        t=w.render({'record':r,'old':None,'reasons':['신규 공식자료 확인']})
        self.assertIn('전체 CAPA',t)
        self.assertIn('HBM만의',t)
        self.assertIn(w.HYNIX_Q3_2026_URL,t)
if __name__=='__main__':
    unittest.main()
