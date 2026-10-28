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

    def test_fab_shell_acceleration_is_not_m17_equipment_or_cleanroom_revised_date(self):
        item=self.item(w.HYNIX_FAB_SHELL_PRESS_URLS[0])
        body=("SK하이닉스는 용인 클러스터와 청주 M17을 포함한 신규 팹은 "
              "건물 골조 등 건설 일정을 앞당기되 클린룸은 단계별로 나누어 오픈할 예정이라고 밝혔다. "
              "장비 반입과 양산 확대 등 실제 공급 증가는 수요에 따라 조정한다.")
        rec=w.parse_skhynix_fab_shell_2026(item,body)[0]
        v=rec['value']
        self.assertEqual(rec['evidence'],'reported')
        self.assertTrue(v['shell_acceleration_reported'])
        self.assertEqual(v['original_y2_cleanroom_month'],'2029-06')
        self.assertEqual(v['original_m17_cleanroom_month'],'2028-12')
        self.assertEqual(v['y2_approved_investment_krw'],35_200_000_000_000)
        self.assertEqual(v['m17_approved_investment_krw'],19_100_000_000_000)
        self.assertIsNone(v['new_m17_cleanroom_month'])
        self.assertFalse(v['m17_equipment_move_in_date_confirmed'])
        self.assertFalse(v['production_ramp_accelerated_confirmed'])
        message=w.render({'record':rec,'old':None,'reasons':['신규 보도 확인']})
        self.assertIn('장비 반입 날짜·양산 시점은 아직 미공개',message)
        self.assertIn('35조2,000억원',message)
        self.assertIn('19조1,000억원',message)
    def test_fab_shell_actual_q3_transcript_korean_shell_phase_wording(self):
        # The literal Q3 call uses 'M17을', '쉘' and '페이즈별'.
        item=self.item("https://stockanalysis.com/quote/krx/000660/transcripts/717350-q3-2026/")
        body=("SK하이닉스 투자 집행은 단계적으로 이루어질 예정입니다. 기반 인프라는 "
              "중장기 수요에 대비해서 선제적으로 준비하고, 장비 반입과 양산 확대 등 "
              "실제 공급 증가로 연결되는 핵심 자원은 수요에 따라 조정한다는 방침입니다. "
              "예를 들어서 용인 클러스터와 M17을 포함한 신규 팹은 건물 골조에 해당되는 "
              "쉘 건설 일정을 앞당기되, 클린룸은 페이즈별로 나누어 오픈할 예정입니다.")
        rows=w.parse_skhynix_fab_shell_2026(item,body)
        self.assertEqual(len(rows),1)
        self.assertTrue(rows[0]["value"]["equipment_move_in_follows_demand"])
        self.assertEqual(rows[0]["evidence"],"reported")
        self.assertFalse(rows[0]["value"]["m17_equipment_move_in_date_confirmed"])
        self.assertIsNone(rows[0]["value"]["new_m17_cleanroom_month"])

    def test_fab_shell_transcript_wrong_company_rejected(self):
        i=self.item("https://stockanalysis.com/quote/krx/000660/transcripts/717350-q3-2026/")
        self.assertEqual(w.parse_skhynix_fab_shell_2026(
            i, "A semiconductor company will accelerate M17 buildings in Yongin; "
               "쉘 일정을 앞당기고 클린룸은 페이즈별 개방."),[])

    def test_generic_equipment_acceleration_rumour_not_fab_issuer_confirmation(self):
        item=self.item('https://www.unverified-example.com/news')
        text=('SK하이닉스 M17 장비반입 조기화와 2027 양산 확정이라는 주장')
        self.assertEqual(w.parse_skhynix_fab_shell_2026(item,text),[])
    def test_fab_shell_report_same_state_does_not_duplicate(self):
        item=self.item(w.HYNIX_FAB_SHELL_PRESS_URLS[0])
        body=('SK하이닉스 용인 및 M17 건물 골조 공사 일정을 앞당기고 클린룸은 단계별 개방하며 '
              '장비 반입은 수요에 따라 조정')
        rec=w.parse_skhynix_fab_shell_2026(item,body)[0]
        now=datetime(2026,10,28,15,0,0)
        a=w.update_state({},[rec],now,[])
        self.assertIn(rec['key'],a['pending'])
        a['last_notified'][rec['key']]=a['pending'].pop(rec['key'])['record']
        b=w.update_state(a,[rec],now,[])
        self.assertFalse(b['pending'])
    def test_fab_shell_parser_does_not_overwrite_existing_lta_track(self):
        item=self.item(w.HYNIX_FAB_SHELL_PRESS_URLS[0])
        text=('SK하이닉스 용인과 M17 신규 팹 셸 건설 일정을 앞당기고 클린룸을 단계별로 개방')
        r=w.parse_skhynix_fab_shell_2026(item,text)
        self.assertEqual(len(r),1)
        self.assertEqual(r[0]['key'],'skhynix_fab_shell_2026|skhynix|Y2_M17')
        self.assertNotIn('skhynix_lta',r[0]['key'])

if __name__=='__main__':
    unittest.main()
