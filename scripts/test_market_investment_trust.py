"""Investment-trust coverage; offline source fixtures, no messages or state writes."""
import asyncio
from collections import deque
import copy
import datetime as dt
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch, AsyncMock, Mock

import requests
import kospi_shock_episode_watch as watch
import kospi_shock_enrichment as enrichment
import kospi_flow_attribution_ls as legacy
import market_flow_channels as channels
from market_investors import TRUST_NOTE, SUBGROUP_NOTE, trust_value
from kosdaq_surge_industries import industry_buy_context, industry_context_lines

NOW=dt.datetime(2026,10,20,14,10,tzinfo=watch.KST).timestamp()
START=NOW-300


def future_body(market='KOSDAQ', trust='-41', **changes):
    row={'date':'20261020','time':'141000','datetime':'20261020',
         'indmsamt':'110','formsamt':'-100','sysmsamt':'-10',
         'indmsvol':110,'formsvol':-100,'sysmsvol':-10,
         'etcmsamt':'0','etcmsvol':0,'natmsamt':'0','natmsvol':0,
         'invmsamt':trust,'invmsvol':-41}
    row.update(changes)
    return {'t8463OutBlock':{'tm_rng':'D','fot_clsf_cd':'F',
          'bsc_asts_id':channels.MARKET_SPECS[market]['asset'],
          **{prefix+'code':code for prefix,code in channels.FUTURES_INVESTORS.values()},
          'invcode':'0003'},'t8463OutBlock1':[row]}


def snap(ts,market,trust=0,selling=False):
    vals={'외국인':-100 if selling else 0,
          '기관':-10 if selling else 0,'개인':110 if selling else 0,'투신':trust}
    return {'ts':ts,'market':market,
      '현물':{'sample_ts':ts,'market':market,**vals},
      '선물':{'sample_ts':ts,**vals},
      '지수선물':{'sample_ts':ts,'source_tr':'t8463','source_scope_verified':True,
          'market':market,'asset':channels.MARKET_SPECS[market]['asset'],
          'unit':'LS_raw_amount','summary':future_body(market)['t8463OutBlock'],
          'source_row':{**{prefix+field:vals.get(actor,0)
             for actor,(prefix,_) in channels.FUTURES_INVESTORS.items()
             for field in ['msamt','msvol']},'invmsamt':trust,'invmsvol':trust},**vals},
      '프로그램':{'sample_ts':ts,'market':market,'source_tr':'t1640','전체':-30,
          '차익':-10,'비차익':-20,'표본시차초':2,'source_time_verified':False}}


class Offline(unittest.TestCase):
    def setUp(self):
        self.addCleanup(patch.stopall)
        patch.object(requests.sessions.Session,'request',side_effect=AssertionError('network forbidden')).start()
        patch('urllib.request.urlopen',side_effect=AssertionError('network forbidden')).start()


class SourceFields(Offline):
    def test_time_only_market_timestamp_uses_reference_date(self):
        expected=dt.datetime(2026,10,20,14,10,tzinfo=watch.KST).timestamp()
        self.assertEqual(watch.market_clock_epoch('14100000',NOW),expected)

    def test_spot_current_keeps_exact_sv03_in_both_markets(self):
        for market,code in [('1','001'),('3','301')]:
            body={'t1602OutBlock':{'ex_upcode':'U'+code},'t1602OutBlock1':[
                {'time':'14100000','sv_17':'100','sv_18':'40','sv_08':'-140','sv_03':'-32'}]}
            with self.subTest(market=market), patch.object(watch,'ls_post',return_value=body),patch.object(watch.time,'time',return_value=NOW):
                result=watch.investor_current('unused',market,code,'U')
            self.assertEqual(result['투신'],-32)
            self.assertEqual(result['기관'],40)
            self.assertEqual(result['source_row']['sv_03'],'-32')

    def test_spot_missing_nonfinite_or_empty_trust_is_not_zero(self):
        for value in [None,'','NaN','inf']:
            body={'t1602OutBlock1':[{'time':'141000','sv_17':1,'sv_18':2,'sv_08':-3,'sv_03':value}]}
            with patch.object(watch,'ls_post',return_value=body),patch.object(watch.time,'time',return_value=NOW):
                self.assertIsNone(watch.investor_current('unused','1','001')['투신'])

    def test_t8463_exact_subgroup_and_disjoint_reconciliation(self):
        for market in ['KOSPI','KOSDAQ']:
            b=channels.parse_futures(future_body(market),market,NOW+1)
            self.assertEqual(b['투신'],-41)
            self.assertEqual(b['기관'],-10)
            quality=channels.futures_investor_quality(b['summary'],b['source_row'])
            self.assertTrue(quality['verified'])
            self.assertEqual(quality['amount_sum'],0)
            self.assertNotIn('투신',quality['amounts'])
            self.assertFalse(b['unit_verified'])

    def test_bad_subgroup_code_does_not_invent_amount_or_break_parent(self):
        body=future_body();body['t8463OutBlock']['invcode']='0004'
        b=channels.parse_futures(body,'KOSDAQ',NOW+1)
        self.assertIsNone(b['투신'])
        self.assertFalse(b['actor_quality']['투신']['verified'])
        self.assertEqual(b['기관'],-10)
        self.assertTrue(b['investor_quality']['verified'])

    def test_missing_amount_or_volume_remains_subgroup_hold(self):
        for changes in [{'invmsamt':None},{'invmsvol':None},{'invmsvol':'NaN'},{'invmsvol':1.5}]:
            self.assertIsNone(channels.parse_futures(future_body(**changes),'KOSDAQ',NOW+1)['투신'])

    def test_explicit_zero_subgroup_is_preserved(self):
        self.assertEqual(channels.parse_futures(future_body(trust='0',invmsvol=0),'KOSDAQ',NOW+1)['투신'],0)

    def test_later_recorded_actual_futures_readback_subgroup(self):
        record=json.loads((Path(__file__).parent/'test_fixtures/kosdaq_futures_readback_20261015.json').read_bytes())
        received=dt.datetime(2026,10,15,11,tzinfo=watch.KST).timestamp()
        b=channels.parse_futures({'t8463OutBlock':record['summary'],'t8463OutBlock1':[record['rows'][0]]},'KOSDAQ',received)
        self.assertEqual(b['투신'],-169)
        self.assertFalse(record['original_operating_response'])

    def test_cached_subgroup_cannot_override_retained_source_row(self):
        b=channels.parse_futures(future_body(),'KOSDAQ',NOW+1);b['투신']=-9999
        self.assertIsNone(trust_value(b))


class IntervalAndRendering(Offline):
    def setUp(self):
        super().setUp()
        self.w=watch.Watch('unused',[], '',False)
        self.ep={'start_ts':START,'start_price':100,'low_ts':NOW,'low_price':99,'market':'KOSDAQ'}
        self.w.flows=deque([snap(START,'KOSPI'),snap(NOW,'KOSPI',-80,True)])
        self.w.kosdaq_flows=deque([snap(START,'KOSDAQ'),snap(NOW,'KOSDAQ',-80,True)])

    def test_subgroup_delta_kept_without_changing_parent_leader(self):
        for market in ['KOSPI','KOSDAQ']:
            a=self.w._market_attribution(START,NOW,market)
            self.assertEqual(a['spot']['투신'],-80)
            self.assertEqual(a['futures']['투신'],-80)
            self.assertEqual(a['spot_leader'],'외국인')
            self.assertEqual(a['futures_leader'],'외국인')
            self.assertNotIn('투신',a['cross_sellers'])
            self.assertNotIn('투신',a['verdict'])

    def test_missing_old_endpoint_does_not_subtract_from_zero(self):
        first=snap(START,'KOSPI')['현물'];last=snap(NOW,'KOSPI',80)['현물']
        first.pop('투신')
        self.assertIsNone(watch._actor_delta(first,last)['투신'])
        self.assertEqual(watch._actor_delta(last,last)['투신'],0)

    def test_every_drop_stage_in_both_markets_shows_subgroup(self):
        for stage in ['start','expand','end','close']:
            for market in ['KOSPI','KOSDAQ']:
                with self.subTest(stage=stage,market=market):
                    if market=='KOSDAQ':
                        text=self.w.build_kosdaq_drop_alert(stage,self.ep,NOW+20,99.5)
                    elif stage in ['end','close']:
                        text=self.w.build_end(self.ep,NOW+20,99.5,session_close=stage=='close')
                    else:text=self.w.build_alert(stage,self.ep,NOW,99)
                    self.assertIn('투신(기관 내)',text)
                    self.assertIn('-80억원',text)
                    self.assertIn('LS 순매수금액 원값',text)
                    self.assertIn(SUBGROUP_NOTE,text)

    def test_missing_subgroup_is_visible_in_message(self):
        a=self.w._market_attribution(START,NOW,'KOSPI');a['spot']['투신']=None
        text='\n'.join(watch.market_attribution_lines(a,'KOSPI'))
        self.assertIn('투신(기관 내) <b>확인 불가</b>',text)
        self.assertIn('현물 확인 보류',text)

    def test_toplevel_positive_does_not_hide_subgroup_selling(self):
        a=self.w._market_attribution(START,NOW,'KOSPI')
        a['spot']['기관']=100;a['futures']['기관']=100
        text='\n'.join(watch.market_attribution_lines(a,'KOSPI'))
        self.assertIn('기관 <b>+100억원</b>',text)
        self.assertIn('현물 순매도 · 선물 순매도',text)

    def test_legacy_derivative_and_fallback_shared_renderer(self):
        block={'stale':False,'base_time':'140000','delta':{'기관계':40,'투신':-22},'current':{'투신':-100}}
        text='\n'.join(legacy.attribution_html_lines({'kospi':block,'kp200':block,'futures':block}))
        self.assertEqual(text.count('투신(기관 내) <b>-22억원</b>'),3)
        self.assertIn('투신(기관 내) -100억원',text)
        self.assertIn(TRUST_NOTE,text)

    def test_legacy_stale_trust_is_not_classified(self):
        block={'stale':True,'base_time':'140000','delta':{'투신':-100}}
        text='\n'.join(legacy.attribution_html_lines({'kospi':block,'futures':block}))
        self.assertNotIn('현물 순매도',text)
        self.assertIn('현물 확인 보류',text)

    def test_trust_surge_uses_existing_independent_actor_thresholds(self):
        rows=[snap(START,'KOSPI',0),snap(NOW,'KOSPI',1000)]
        candidates=watch.flow_surge_candidates(rows,NOW+1)
        c=next(x for x in candidates if x['actor']=='투신')
        self.assertEqual(c['spot'],1000)
        text=self.w.build_flow_surge_alert(c,NOW+1,None)
        self.assertIn('투신(기관 내)',text)
        self.assertIn(TRUST_NOTE,text)

    def test_kosdaq_trust_surge_has_same_150_threshold_and_confirmation(self):
        self.w.session_open_ts=START-3600;self.w.session_close_ts=NOW+3600
        self.w.session_continuous_end_ts=NOW+3600
        self.w.kosdaq_flows=deque([snap(START,'KOSDAQ',0),snap(NOW,'KOSDAQ',200)])
        # Build the same production text after a newer confirming source sample.
        pair=watch._flow_surge_channel_pair(list(self.w.kosdaq_flows),'현물',NOW+1)
        self.assertEqual(pair['deltas']['투신'],200)
        text=self.w.build_kosdaq_flow_surge_alert('투신',200,pair,NOW+1,None)
        self.assertIn('150억원',text)
        self.w._send_event=AsyncMock(return_value=123)
        self.w._surge_industry_context=AsyncMock(return_value=None)
        self.w._record_delivery=Mock()
        asyncio.run(self.w.maybe_alert_kosdaq_surge(NOW+1))
        self.w._send_event.assert_not_awaited()
        self.w.kosdaq_flows.append(snap(NOW+15,'KOSDAQ',220))
        asyncio.run(self.w.maybe_alert_kosdaq_surge(NOW+16))
        self.w._send_event.assert_awaited_once()
        self.assertIn('투신(기관 내)',self.w._send_event.call_args.args[-1])
        self.assertEqual(self.w.kosdaq_surge_sent_at['투신'],NOW+16)

    def test_handoff_preserves_trust_cooldown_and_pending_for_both_markets(self):
        for attr in ['surge_sent_at','kosdaq_surge_sent_at']:setattr(self.w,attr,{'투신':NOW,'기관':NOW-30})
        for attr in ['surge_pending','kosdaq_surge_pending']:
            setattr(self.w,attr,{'투신':{'sample_ts':NOW,'seen_at':NOW,'end_value':80,'end_values':{'spot':80}}})
        with tempfile.TemporaryDirectory() as tmp:
            path=Path(tmp)/'handoff.json'
            self.w.save_handoff(path)
            restored=watch.Watch('unused',[], '',False);restored.load_handoff(path)
            for attr in ['surge_sent_at','kosdaq_surge_sent_at','surge_pending','kosdaq_surge_pending']:
                self.assertEqual(getattr(restored,attr),getattr(self.w,attr),attr)


class IndustryAndEnrichment(Offline):
    def test_trust_ubm_industry_ranking_does_not_use_parent(self):
        for market,code in [('KOSPI','013'),('KOSDAQ','319')]:
            rows=[{'record_type':'subscription_coverage','source_tr':'UBM','market':market,'ts':START-3600,'expected':[{'code':code,'name':'화학'}]}]
            for ts,value in [(START,20),(NOW,45)]:
                rows.append({'ts':ts,'received_ts':ts,'source_ts':ts,'source_time':dt.datetime.fromtimestamp(ts,watch.KST).strftime('%H%M%S'),
                     'upcode':code,'industry':'화학','investor':'투신','investor_code':'0003','msval':value,'ex_upcode':'U'+code})
                rows.append({**rows[-1],'investor':'기관','investor_code':'0018','msval':-999})
            with tempfile.TemporaryDirectory() as tmp:
                path=Path(tmp)/'industry.jsonl';path.write_text(''.join(json.dumps(r,ensure_ascii=False)+'\n' for r in rows),encoding='utf-8')
                block=industry_buy_context(START,NOW,'투신',path=path,session_open_ts=START-3600,market=market)
            self.assertTrue(block['available'],block)
            self.assertEqual(block['top'][0]['delta_raw'],25)
            self.assertIn('투신(기관 내)','\n'.join(industry_context_lines(block,'투신',START,NOW,market=market)))

    def test_native_trust_industry_uses_invmsamt_and_code0003(self):
        rows=[]
        for ts,value in [(START,20),(NOW,45)]:
            rows.append({'date':'20261020','time':dt.datetime.fromtimestamp(ts,watch.KST).strftime('%H%M%S'),'datetime':'20261020','invmsamt':value,'sysmsamt':999})
        record={'record_type':'industry_history_snapshot','source_tr':'t1621','market':'KOSDAQ','upcode':'319','industry':'화학',
            'received_ts':NOW+1,'status':'success','source_unit':'UNVERIFIED','request':{'t1621InBlock':{'upcode':'319','exchgubun':'U','bgubun':'0'}},
            'response':{'t1621OutBlock':{'invcode':'0003','ex_upcode':'U319'},'t1621OutBlock1':rows}}
        with tempfile.TemporaryDirectory() as tmp:
            path=Path(tmp)/'industry.jsonl';path.write_text(json.dumps(record,ensure_ascii=False),encoding='utf-8')
            block=industry_buy_context(START,NOW,'투신',path=path,session_open_ts=START-3600)
        self.assertTrue(block['available'],block)
        self.assertEqual(block['source_amount_field'],'invmsamt')
        self.assertEqual(block['top'][0]['delta_raw'],25)

    def test_both_enrichment_bodies_show_missing_or_confirmed_trust(self):
        raw={'generated_at_kst':'2026-10-20T14:10:00+09:00',
             'event':{'start_kst':'14:05:00','low_kst':'14:10:00'},'market_spot_deltas':{'외국인':5,'기관':10,'개인':-15,'투신':-7}}
        self.assertIn('투신(기관 내) -7억원',enrichment.render_enrichment_summary(raw))
        self.assertIn('투신(기관 내) -7억원',enrichment.render_kosdaq_enrichment(raw))
        raw['market_spot_deltas'].pop('투신')
        self.assertIn('투신(기관 내) 확인 불가',enrichment.render_enrichment_summary(raw))


if __name__=='__main__':unittest.main(verbosity=2)
