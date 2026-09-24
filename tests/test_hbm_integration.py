import copy
import pathlib
import sys
import unittest
from datetime import datetime
from zoneinfo import ZoneInfo
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / 'scripts'))
import hbm_memory_axes as m
import hbm_delivery as d

NOW = datetime(2026, 9, 22, 16, tzinfo=ZoneInfo('Asia/Seoul'))
ITEM = {'source': 'TrendForce', 'direct_link': 'https://www.trendforce.com/research/example',
        'published_at_kst': '2026-09-22T10:00:00+09:00', 'title': '삼성전자 HBM·서버 메모리'}

class MathTests(unittest.TestCase):
    def test_capacity_units(self):
        self.assertEqual(m.product_capacity(24, 12), 36)
        self.assertEqual(m.product_capacity(32, 8), 32)
        self.assertEqual(m.product_capacity(32, 12), 48)
        self.assertEqual(m.product_capacity(32, 8, 8), 256)
    def test_distinct_break_even(self):
        a = m.capacity_comparison(36, 32)
        b = m.capacity_comparison(48, 32)
        self.assertAlmostEqual(a['capacity_change_pct'], -100 / 9)
        self.assertAlmostEqual(a['gpu_growth_break_even_pct'], 12.5)
        self.assertAlmostEqual(b['gpu_growth_break_even_pct'], 50)
    def test_stack_count_changes(self):
        self.assertAlmostEqual(m.capacity_comparison(36,32,8,12)['capacity_change_pct'], 100/3)
    def test_invalid_inputs(self):
        for args in [(0,12), (24,-1), (32,8.5), (float('nan'),8)]:
            with self.assertRaises(ValueError): m.product_capacity(*args)
    def test_premium(self):
        self.assertAlmostEqual(m.premium(2150,1000), 115)
        self.assertAlmostEqual(m.premium(2450,1000), 145)
    def test_contract_catchup_not_demand_warning(self):
        self.assertIn('추격', m.rdimm_driver({'spot':2150,'contract':1000}, {'spot':2150,'contract':1200}))
    def test_spot_weakness(self):
        self.assertIn('약화', m.rdimm_driver({'spot':2150,'contract':1000}, {'spot':2000,'contract':1000}))

class ParseTests(unittest.TestCase):
    def test_explicit_rdimm_pair(self):
        r,g = m.parse_records(ITEM, '2026-09-22 DDR5 RDIMM 64GB 4800/5600/6400 MT/s 현물가격 2150달러 고정거래가격 1000달러 고정거래 기준 2026-09')
        self.assertEqual(len(r),1); self.assertAlmostEqual(r[0]['value']['premium_pct'],115)
        self.assertEqual(r[0]['unit'],'USD/module')
    def test_premium_only_not_raw_prices(self):
        r,g=m.parse_records(ITEM,'64GB RDIMM 현물 프리미엄 115%')
        self.assertEqual(r,[]); self.assertTrue(g)
    def test_gb_chip_not_gbyte_module(self):
        r,_=m.parse_records(ITEM,'DDR5 RDIMM 16Gb 현물 33달러 고정거래 22달러')
        self.assertEqual(r,[])
    def test_missing_date_rejected(self):
        r,_=m.parse_records(ITEM,'DDR5 RDIMM 64GB 5600 MT/s 현물 2150달러 고정거래 1000달러')
        self.assertEqual(r,[])
    def test_mixed_dates_rejected(self):
        r,g=m.parse_records(ITEM,'2026-09-22 DDR5 RDIMM 64GB 5600 MT/s 현물 2150달러 고정거래 1000달러 고정거래 기준 2026-08')
        self.assertEqual(r,[]);self.assertTrue(g)
    def test_mixed_specs_rejected(self):
        r,_=m.parse_records(ITEM,'2026-09-22 64GB RDIMM 5600 MT/s 현물 2150달러 32GB RDIMM 고정거래 1000달러 고정거래 기준 2026-09')
        self.assertEqual(r,[])
    def test_configuration_math(self):
        r,_=m.parse_records(ITEM,'삼성전자 HBM4 24Gb 다이 12단 36GB. HBM4E 32Gb 다이 8단 32GB.')
        self.assertEqual(len(r),2);self.assertEqual(r[1]['value']['stack_gbyte'],32)
        self.assertTrue(all('not_customer' in x['scope'] for x in r))
    def test_inconsistent_configuration_rejected(self):
        r,g=m.parse_records(ITEM,'삼성 HBM4E 24Gb 다이 8단 32GB')
        self.assertEqual(r,[]); self.assertTrue(g)
    def test_distinct_wafer_and_bit(self):
        body='TrendForce HBM 웨이퍼 비중은 2026년말 22%, 2027년말 30%. HBM 비트 공급 비중은 2026년말 9%, 2027년말 13%.'
        r,_=m.parse_records(ITEM,body)
        self.assertEqual(len(r),4)
        self.assertEqual({x['axis'] for x in r},{'wafer_share','bit_share'})
    def test_carrier_not_wafer(self):
        r,_=m.parse_records(ITEM,'삼성전자 HBM 글라스 캐리어 세정은 2026년 월 2만장, 2027년 월 5만장.')
        self.assertEqual([x['value'] for x in r],[20000,50000])
        self.assertTrue(all(x['unit']=='cleaning_passes/month' for x in r))
    def test_fab_stage(self):
        r,_=m.parse_records(ITEM,'삼성전자 P5 Fab1은 2028년 가동 목표.')
        self.assertEqual(r[0]['value'],{'year':2028,'stage':'plan'})

    def test_malaysia_hsk10_export_parse(self):
        body = (
            '22일 관세청 수출입무역통계에 따르면 HBM이 포함되는 복합구조칩 집적회로 '
            '(HS코드 8542.32.3000)의 지난 8월 말레이시아향 수출액은 16억2454만달러로, '
            '전년 동기 대비 466.6% 증가했다. 수출 중량도 1.4t에서 3.8t으로 증가했다. '
            '같은 기간 대만향은 33억2211만달러였고 말레이시아향은 대만향의 48.9%까지 커졌다.'
        )
        item = dict(ITEM)
        item['published_at_kst'] = '2026-09-22T10:51:00+09:00'
        item['direct_link'] = 'https://biz.chosun.com/example'
        r,g = m.parse_records(item, body)
        rows = [x for x in r if x['axis'] == 'malaysia_hsk10_export']
        self.assertEqual(len(rows),1)
        self.assertEqual(rows[0]['period'],'2026-08')
        self.assertEqual(rows[0]['value']['amount_usd'],1624540000)
        self.assertEqual(rows[0]['value']['weight_kg'],3800)
        self.assertAlmostEqual(rows[0]['value']['yoy_pct'],466.6)
        self.assertEqual(rows[0]['value']['taiwan_amount_usd'],3322110000)
        self.assertAlmostEqual(rows[0]['value']['malaysia_vs_taiwan_pct'],48.9)

    def test_malaysia_new_month_is_material(self):
        base = m.make_record(
            'malaysia_hsk10_export',['KR','MY','8542323000'],
            {'amount_usd':1300000000,'weight_kg':None,'weight_kg_previous_yoy':None,
             'yoy_pct':None,'taiwan_amount_usd':None,'malaysia_vs_taiwan_pct':None,
             'jan_aug_amount_usd':None,'weight_rounded_from_public_text':False},
            'USD/kg','2026-07',ITEM,'base',as_of='2026-08-21')
        new = copy.deepcopy(base)
        new['period']='2026-08'; new['as_of']='2026-09-22'
        new['value']=dict(base['value']); new['value']['amount_usd']=1624540000
        reasons = m.comparison(base,new)
        self.assertTrue(any('새 월' in x for x in reasons))
        self.assertTrue(any('수출액' in x for x in reasons))

    def test_bernstein_hbm_revenue_estimate_parse(self):
        item = dict(ITEM)
        item['title'] = 'Bernstein Korean HBM export tracker'
        item['source'] = 'Bernstein'
        item['published_at_kst'] = '2026-09-21T09:00:00+09:00'
        body = (
            "Samsung's 3Q26 HBM revenue is estimated at US$11.4B by the regression, "
            "representing 72% QoQ growth versus Bernstein's US$9.3B forecast. "
            "SK hynix 3Q26 HBM revenue regression implies US$5.9B, down 14% QoQ. "
            "Under the most back-end-loaded case it could reach US$7.5B."
        )
        rows = m.parse_hbm_revenue_estimates(item, body)
        samsung = [x for x in rows if '|samsung|' in x['key']][0]
        skh = [x for x in rows if '|skhynix|' in x['key']][0]
        self.assertEqual(samsung['period'],'2026Q3')
        self.assertEqual(samsung['value']['estimate_usd'],11400000000)
        self.assertAlmostEqual(samsung['value']['qoq_pct'],72.0)
        self.assertEqual(skh['value']['estimate_usd'],5900000000)

    def test_hbm_revenue_estimate_large_revision_is_material(self):
        old = m.make_record(
            'hbm_revenue_estimate',['bernstein','samsung','2026Q3','regression_proxy'],
            {'estimate_usd':9300000000,'qoq_pct':40.0,'prior_formal_forecast_usd':None,
             'alternative_usd':None,'method':'regression_proxy'},
            'USD/quarter','2026Q3',ITEM,'old',as_of='2026-08-21')
        new = copy.deepcopy(old)
        new['as_of']='2026-09-21'
        new['value']=dict(old['value'])
        new['value']['estimate_usd']=11400000000
        new['value']['qoq_pct']=72.0
        reasons=m.comparison(old,new)
        self.assertTrue(any('분기 HBM 매출 추정' in x for x in reasons))
        self.assertTrue(any('전분기 증감률 전망' in x for x in reasons))

class StateTests(unittest.TestCase):
    def make(self,v=22,asof='2026-09-22',url=None):
        item=dict(ITEM)
        if url:item['direct_link']=url
        return m.make_record('wafer_share',['trendforce','industry','2027-YE'],v,'pct','2027-YE',item,'a',as_of=asof)
    def test_same_fact_new_article_silent(self):
        a=self.make();s=m.update_state({},[],NOW,[a]);b=self.make(url='https://www.trendforce.com/research/other')
        self.assertFalse(m.update_state(s,[b],NOW)['pending'])
    def test_changed_value_pending(self):
        a=self.make();s=m.update_state({},[],NOW,[a])
        self.assertEqual(len(m.update_state(s,[self.make(30)],NOW)['pending']),1)
    def test_stale_observation_does_not_roll_back(self):
        a=self.make();s=m.update_state({},[],NOW,[a])
        self.assertFalse(m.update_state(s,[self.make(30,'2026-06-02')],NOW)['pending'])
    def test_conflict_held(self):
        s=m.update_state({},[self.make(22),self.make(30)],NOW)
        self.assertFalse(s['pending']);self.assertIn('불일치',str(s['coverage']))
    def test_subthreshold_accumulates(self):
        r,_=m.parse_records(ITEM,'2026-09-22 DDR5 RDIMM 64GB 5600 MT/s 현물 2200달러 고정거래 1000달러 고정거래 기준 2026-09')
        base=r[0];s=m.update_state({},[],NOW,[base])
        small=copy.deepcopy(base);small['value']['spot']=2240;small['value']['premium_pct']=124
        s=m.update_state(s,[small],NOW);self.assertFalse(s['pending'])
        larger=copy.deepcopy(small);larger['value']['spot']=2340;larger['value']['premium_pct']=134
        s=m.update_state(s,[larger],NOW);self.assertTrue(s['pending'])
    def test_future_dated_data_rejected(self):
        self.assertFalse(m.update_state({},[self.make(22,'2027-01-01')],NOW)['latest'])
    def test_pending_survives_quiet_execution(self):
        s=m.update_state({},[self.make()],NOW)
        self.assertEqual(s['pending'],m.update_state(s,[],NOW)['pending'])
    def test_historical_first_source_seeds_without_alert(self):
        s=m.update_state({},[self.make(22,'2026-06-02')],NOW)
        self.assertFalse(s['pending']);self.assertTrue(s['last_notified'])

class FakeRepo:
    def __init__(self,state):self.state=copy.deepcopy(state);self.history=[]
    def checkpoint(self,path,expected,desired):
        assert d.digest(expected)==d.digest(self.state), 'unexpected state race'
        self.state=copy.deepcopy(desired);self.history.append(copy.deepcopy(desired))

class DeliveryTests(unittest.TestCase):
    def test_success_before_state_promotion(self):
        before={'value':1};repo=FakeRepo(before)
        def send(method,payload):
            self.assertEqual(repo.state['value'],1)
            self.assertEqual(repo.state['_delivery']['status'],'in_flight')
            return {'message_id':456}
        receipt=d.transact(repo,'x',before,{'value':2},'<b>확인</b>',send)
        self.assertEqual(receipt['message_ids'],[456]);self.assertEqual(repo.state['value'],2)
        self.assertNotIn('_delivery',repo.state)
    def test_failure_not_consumed_or_resent(self):
        before={'value':1};repo=FakeRepo(before);calls=[]
        def send(*args):calls.append(1);raise TimeoutError()
        with self.assertRaises(RuntimeError):d.transact(repo,'x',before,{'value':2},'알림',send)
        self.assertEqual(repo.state['value'],1);self.assertEqual(repo.state['_delivery']['status'],'uncertain')
        with self.assertRaises(RuntimeError):d.resume_one(repo,'x',repo.state,send)
        self.assertEqual(len(calls),1)
    def test_silent_run_commits(self):
        repo=FakeRepo({'value':1})
        d.transact(repo,'x',repo.state,{'value':2},'',lambda *x:self.fail('sent'))
        self.assertEqual(repo.state['value'],2)
    def test_late_subsystem_failure_cannot_erase_checkpoint(self):
        repo=FakeRepo({'value':1});d.transact(repo,'x',repo.state,{'value':2},'알림',lambda *a:{'message_id':3})
        try:raise FileNotFoundError('unrelated SOCAMM')
        except FileNotFoundError:pass
        self.assertEqual(repo.state['value'],2)
    def test_chunk_link_integrity(self):
        text='\n'.join(['<b>제목</b>', 'a'*3300, '<a href="https://example.com">원문</a>']*3)
        parts=d.chunks(text)
        self.assertGreater(len(parts),1)
        for p in parts:
            self.assertEqual(p.count('<a '),p.count('</a>'))
            self.assertLessEqual(len(p.encode('utf-16-le'))//2,3600)
    def test_multiline_quote_is_balanced(self):
        text = '<blockquote expandable><b>기준</b>\n' + ('여러 줄 설명\n' * 1400) + '</blockquote>'
        parts=d.chunks(text)
        self.assertGreater(len(parts),1)
        for part in parts:
            parser=d.HTMLBalance();parser.feed(part);self.assertEqual(parser.stack,[])
    def test_oversize_line_never_silently_truncated(self):
        with self.assertRaises(ValueError):d.chunks('a'*4000)
    def test_preserve_independent_state(self):
        self.assertIn('ai_component_leadtime',d.promote({'value':2},{'value':1,'ai_component_leadtime':{'x':1}}))
    def test_inflight_restart_no_send(self):
        state={'value':1,'_delivery':{'status':'in_flight'}};repo=FakeRepo(state)
        with self.assertRaises(RuntimeError):d.resume_one(repo,'x',state,lambda *x:self.fail('sent'))

if __name__=='__main__':unittest.main()
