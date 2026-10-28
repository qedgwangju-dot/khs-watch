import json
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
import warsh_beige_book_watch as beige
import warsh_imf_policy_shift_watch as imf

import datetime as _dt


class FixedIMFEventDatetime(_dt.datetime):
    """Keep event-window tests independent of the date CI is executed."""
    @classmethod
    def now(cls, tz=None):
        return cls(2026, 10, 16, 12, 0, tzinfo=tz)


BEIGE_HTML='''<html><h1>Beige Book - October 2026</h1>
<h2>National Summary</h2>
<h3>Overall Economic Activity</h3>
Five Districts reported that some firms had either reduced staffing levels
(through attrition), delayed hiring, or anticipated less job creation after
increasing productivity by investing in AI.
Most Districts reported little or no change in overall consumer spending.
<h3>Prices</h3>
Three Districts characterized overall price growth as robust,
while eight noted that growth was moderate.
One District reported modest price growth.
Moreover, four Districts reported that the pace of price increases picked up
since the prior period.
Firms reported elevated diesel prices and noted that fuel surcharges were
passing on increased costs throughout the supply chain.
Contacts in multiple Districts noted continued price pressure from other
commodities, tariffs, and insurance.
Consumer-facing firms noted tighter profit margins as price-sensitive
customers continue to resist price hikes.
Firms in several Districts cited persistent uncertainty around energy and
tariffs and expect that prices will increase further in the coming months,
as existing contracts expire, and firms must renegotiate hedge contracts
for their own inputs and/or delivery contracts to their customers.
<h3>Highlights by Federal Reserve District</h3>
Last Update: October 14, 2026</html>'''


class TestBeigeBook(unittest.TestCase):
    def test_national_counts_do_not_double_count_input_intensity(self):
        d=beige.parse_national(BEIGE_HTML)
        self.assertEqual([d['strong_price_districts'],d['moderate_price_districts'],
                          d['modest_price_districts'],d['price_acceleration_districts'],
                          d['ai_hiring_districts']],[3,8,1,4,5])
        self.assertTrue(d['energy_freight'])
        self.assertTrue(d['contract_lag'])

    def test_inconsistent_counts_fail_closed(self):
        with self.assertRaisesRegex(ValueError,'합계'):
            beige.parse_national(BEIGE_HTML.replace(
                'One District reported modest price growth',
                'Two District reported modest price growth'))

    def test_release_requires_official_last_update(self):
        self.assertEqual(beige.release_meta(BEIGE_HTML,2026,10),'2026-10-14')
        self.assertIsNone(beige.release_meta(BEIGE_HTML.replace(
            'October 14, 2026','October 13, 2025'),2026,10))
        self.assertIsNone(beige.release_meta(BEIGE_HTML.replace(
            'Last Update: October 14, 2026','Scheduled October 14, 2026'),2026,10))

    def test_message_korean_and_distinguishes_fed_action(self):
        msg=beige.message({'release_date':'2026-10-14',
            'values':beige.parse_national(BEIGE_HTML),
            'url':'https://www.federalreserve.gov/monetarypolicy/beigebook202610-summary.htm'})
        self.assertIn('4곳',msg)
        self.assertIn('5곳',msg)
        self.assertIn('금리인상 확정이 아닙니다',msg)


class TestIMF(unittest.TestCase):
    def test_talk_is_not_policy_commitment(self):
        msg=imf.compose('연준·IMF 행사 일정 교차확인',
           [{'publisher':'Reuters','url':imf.REUTERS,'title':'Warsh IMF Bangkok'}],True)
        self.assertIn('미리 약속하지 않음',msg)
        self.assertIn('Citi',msg)
        self.assertIn('증권사 전망(연준 결정 아님)',msg)
        self.assertNotIn('10월 인상 확정',msg)

    def test_unverified_coverage_blocks_alert(self):
        with patch.object(imf,'get',side_effect=TimeoutError('network')):
            with self.assertRaisesRegex(RuntimeError,'검증 실패'):
                imf.dated_coverage()

    def test_dedup_does_not_send_twice(self):
        memory={}
        def save(x): memory.clear();memory.update(x)
        with patch.object(imf,'datetime',FixedIMFEventDatetime),\
             patch.object(imf,'read_state',side_effect=lambda: memory.copy()),\
             patch.object(imf,'save',side_effect=save),\
             patch.object(imf,'official_event',return_value='공식 확인'),\
             patch.object(imf,'dated_coverage',return_value=[
                 {'publisher':'Reuters','url':imf.REUTERS,'title':'Warsh IMF Bangkok'}]),\
             patch.object(imf,'citi_reported',return_value=False),\
             patch.object(imf,'ai_policy_sources',side_effect=RuntimeError('not yet verified')),\
             patch.object(imf,'send',return_value=76) as sender:
            imf.main()
            imf.main()
            self.assertEqual(sender.call_count,1)
            self.assertEqual(memory['message_id'],76)
            self.assertEqual(memory['delivery_status'],'confirmed')
            self.assertEqual(memory['last_sent_key'],imf.EVENT_ID)


    def test_citi_followup_is_one_time_and_distinct_from_imf(self):
        memory={
            'last_sent_key':imf.EVENT_ID,'message_id':89,
            'citi_reported':False,'delivery_status':'confirmed'
        }
        def save(x): memory.clear(); memory.update(x)
        with patch.object(imf,'datetime',FixedIMFEventDatetime),\
             patch.object(imf,'read_state',side_effect=lambda: memory.copy()),\
             patch.object(imf,'save',side_effect=save),\
             patch.object(imf,'citi_reported',return_value=imf.CITI_REUTERS_MIRRORS[0]),\
             patch.object(imf,'ai_policy_sources',side_effect=RuntimeError('not yet verified')),\
             patch.object(imf,'send',return_value=90) as sender:
            imf.main()
            imf.main()
            self.assertEqual(sender.call_count,1)
            self.assertEqual(memory['message_id'],89)
            self.assertEqual(memory['citi_message_id'],90)
            self.assertTrue(memory['citi_reported'])
            self.assertEqual(memory['citi_delivery_status'],'confirmed')

    def test_ai_policy_followup_source_validation(self):
        official='Federal Reserve Data Improve quality, Productivity and Jobs assess artificial intelligence'
        press='2026-10-16 RTHK AFP Kevin Warsh IMF Bangkok AI supply data monetary policy'
        def fetch_stub(url,timeout=8):
            if url==imf.FED_TASKFORCES:return official
            if url==imf.AFP_RTHK:return press
            raise AssertionError(url)
        with patch.object(imf,'get',side_effect=fetch_stub):
            sources=imf.ai_policy_sources()
        self.assertEqual(sources['press'],imf.AFP_RTHK)

    def test_ai_policy_followup_does_not_prejudge_rates(self):
        msg=imf.ai_policy_followup_message({
            'federal':imf.FED_TASKFORCES,'press':imf.AFP_RTHK})
        self.assertIn('정책 운영의 변경·도입 확정은 아님',msg)
        self.assertIn('단기 AI 설비투자·총수요 확대',msg)
        self.assertIn('금리인하·인상 확정으로 해석하지 않음',msg)
        self.assertIn('연준 공식 태스크포스',msg)

    def test_ai_policy_followup_once_preserves_prior_receipts(self):
        memory={'last_sent_key':imf.EVENT_ID,'message_id':89,
                'citi_reported':True,'citi_message_id':90,
                'delivery_status':'confirmed'}
        def save(state):memory.clear();memory.update(state)
        # This one-time follow-up belongs to the Oct 16 release window, not
        # the wall-clock date when CI happens to be re-run.
        import datetime as _dt
        class FixedDatetime(_dt.datetime):
            @classmethod
            def now(cls,tz=None):
                return cls(2026,10,16,12,0,tzinfo=tz)
        with patch.object(imf,'datetime',FixedDatetime),\
             patch.object(imf,'read_state',side_effect=lambda:memory.copy()),\
             patch.object(imf,'save',side_effect=save),\
             patch.object(imf,'ai_policy_sources',return_value={
                 'federal':imf.FED_TASKFORCES,'press':imf.AFP_RTHK}),\
             patch.object(imf,'send',return_value=91) as sender:
            imf.main()
            imf.main()
        self.assertEqual(sender.call_count,1)
        self.assertEqual(memory['message_id'],89)
        self.assertEqual(memory['citi_message_id'],90)
        self.assertEqual(memory['ai_policy_message_id'],91)
        self.assertEqual(memory['ai_policy_delivery_status'],'confirmed')

    def test_ai_policy_sources_fail_closed(self):
        with patch.object(imf,'get',return_value='uncorroborated headlines'):
            with self.assertRaisesRegex(RuntimeError,'검증 실패'):
                imf.ai_policy_sources()

    def test_citi_update_does_not_claim_fomc_action(self):
        msg=imf.citi_followup_message(imf.CITI_REUTERS_MIRRORS[0])
        self.assertIn('2026년 10월 14일',msg)
        self.assertIn('단일 Reuters 보도',msg)
        self.assertIn('연준 결정이나 확인된 CME 시장확률이 아닙니다',msg)


if __name__=='__main__':unittest.main()
