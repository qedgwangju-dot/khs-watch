import copy
import json
import pathlib
import sys
import tempfile
import unittest
from datetime import datetime
from unittest.mock import patch
from zoneinfo import ZoneInfo

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / 'scripts'))
import samsung_hbm_watch as w
import hbm_memory_axes as axes


def pack():
    amounts = {
        '202609': [15013987000., 7840000000., 2800000000., 1610000000.],
        '202608': [12220000000., 7500000000., 1400000000., 1624540000.],
        '202606': [12680000000., 7108000000., 2106800000., 1113400000.],
        '202509': [5233000000., 3156200000., 1156000000., 63950000.],
    }
    rows = {}
    for month, values in amounts.items():
        rows[month] = dict(zip(['national_amount','samsung_region_amount','hynix_chungbuk_amount','malaysia_amount'],values))
        rows[month].update(national_weight=147860., malaysia_weight=4756., icheon_amount=None)
    return dict(month='202609',hs=w.HBM_HSK10,region_hs=w.HBM_HSK10,icheon_hs=w.REGION_HS6,
                series=rows,source_url=w.KCS_SOURCE_PAGE,icheon_public_available=False,
                malaysia_public_available=True,malaysia_source_url='https://www.data.go.kr/data/15100475/openapi.do',
                availability_notes=[],optional_errors=[],errors=[])


class ExportRuntimeIntegrityTests(unittest.TestCase):
    def setUp(self):
        self.network=patch('requests.sessions.Session.request',side_effect=AssertionError('network disabled'))
        self.network.start();self.addCleanup(self.network.stop)
        self.now=datetime(2026,10,16,1,0,tzinfo=ZoneInfo('Asia/Seoul'))

    def notified_state(self,p):
        return dict(last_official_alert_month=p['month'],last_official_alert_snapshot=w.official_snapshot(p),
                    export_alert_format_version=w.EXPORT_ALERT_FORMAT_VERSION,compare_version=w.COMPARE_VERSION)

    def test_each_current_and_comparison_revision_is_not_lost(self):
        original=pack();state=self.notified_state(original)
        for month in original['series']:
            for field in ['national_amount','samsung_region_amount','hynix_chungbuk_amount','malaysia_amount','national_weight','malaysia_weight']:
                with self.subTest(month=month,field=field):
                    changed=copy.deepcopy(original);changed['series'][month][field]+=1.
                    decision=w.official_monthly_decision(state,changed)
                    self.assertTrue(decision['due']);self.assertTrue(decision['revision'])

    def test_query_metadata_does_not_resend_same_source(self):
        p=pack();state=self.notified_state(p)
        p['retrieved_at']='2026-10-17T01:00:00+09:00';p['optional_errors']=['same known city limitation']
        self.assertFalse(w.official_monthly_decision(state,p)['due'])

    def test_optional_source_gap_is_not_a_numeric_revision(self):
        p=pack();state=self.notified_state(p)
        missing=copy.deepcopy(p)
        missing['series']['202609']['malaysia_amount']=None
        missing['series'].pop('202509')
        self.assertFalse(w.official_monthly_decision(state,missing)['due'])

    def test_sent_numeric_revision_keeps_missing_optional_baseline(self):
        p=pack();state=self.notified_state(p)
        missing=copy.deepcopy(p)
        missing['series']['202609']['national_amount']+=1
        missing['series']['202609']['malaysia_amount']=None
        saved,_=self.run_main(state,missing,poll=True)
        self.assertIsNone(saved['last_official_alert_snapshot']['series']['202609']['malaysia_amount'])
        self.assertEqual(saved['last_official_notified_values']['series']['202609']['malaysia_amount'],1610000000.)
        recovered=copy.deepcopy(p);recovered['series']['202609']['national_amount']+=1
        self.assertFalse(w.official_monthly_decision(saved,recovered)['due'])

    def test_first_new_optional_observation_is_additional_confirmation(self):
        p=pack();previous=copy.deepcopy(p);previous['series']['202609']['malaysia_amount']=None
        decision=w.official_monthly_decision(self.notified_state(previous),p)
        self.assertTrue(decision['due']);self.assertTrue(decision['availability'])
        self.assertFalse(decision['revision'])

    def test_older_source_month_cannot_roll_back_a_confirmed_newer_month(self):
        p=pack();state=self.notified_state(p)
        state.update(official_month='202609',last_successful_official_month='202609')
        older=copy.deepcopy(p);older['month']='202608'
        saved,text=self.run_main(state,older,poll=True)
        self.assertFalse(saved['monthly_due'])
        self.assertEqual(saved['last_successful_official_month'],'202609')
        self.assertEqual(saved['official_month'],'202609')
        self.assertEqual(saved['last_official_alert_month'],'202609')
        self.assertIn('최신월 후퇴',str(saved['official_errors']))
        self.assertNotIn('삼성전자 vs SK하이닉스 HBM 수출 방향',text)

    def test_monthly_candidate_never_skips_gate_when_body_is_missing(self):
        for body in ['', '일반 뉴스', '삼성·하이닉스 제목 변경']:
            with self.subTest(body=body), self.assertRaisesRegex(ValueError,'body missing'):
                w.validate_monthly_payload(body,{'monthly_due':True})

    def test_xml_repeated_identity_or_amount_tag_is_malformed(self):
        import xml.etree.ElementTree as ET
        for field in ['year','hsCode','expDlr']:
            raw=f'<response><item><{field}>1</{field}><{field}>1</{field}></item></response>'
            with self.subTest(field=field),self.assertRaises(ValueError):w._xml_rows(ET.fromstring(raw))

    def test_api_error_text_never_copies_credentials_to_errors(self):
        from types import SimpleNamespace
        raw=b'<response><header><resultCode>30</resultCode><resultMsg>bad credential abc-private-value</resultMsg></header></response>'
        response=SimpleNamespace(content=raw,raise_for_status=lambda:None)
        with patch.object(w,'DATA_GO_KEY','offline'),patch.object(w,'_request_with_retry',return_value=response):
            for call in [lambda:w.fetch_data_go_item_month('202609'),lambda:w._fetch_data_go_sido_raw('202609','44'),lambda:w.fetch_data_go_country_item_month('202609')]:
                result=call();self.assertNotIn('abc-private-value',str(result));self.assertIn('00',result[-1])

    def test_revision_baseline_promotes_only_after_existing_delivery_checkpoint(self):
        p=pack();state=self.notified_state(p);unchanged=copy.deepcopy(state)
        changed=copy.deepcopy(p);changed['series']['202609']['national_amount']+=1000
        w.official_monthly_decision(state,changed)
        self.assertEqual(state,unchanged)
        accepted=dict(state,last_official_alert_snapshot=w.official_snapshot(changed))
        self.assertFalse(w.official_monthly_decision(accepted,changed)['due'])

    def test_new_month_and_format_upgrade_once(self):
        p=pack();state=self.notified_state(p);state['export_alert_format_version']-=1
        self.assertTrue(w.official_monthly_decision(state,p)['format_upgrade'])
        state['export_alert_format_version']=w.EXPORT_ALERT_FORMAT_VERSION
        self.assertFalse(w.official_monthly_decision(state,p)['due'])
        state['last_official_alert_month']='202608'
        self.assertTrue(w.official_monthly_decision(state,p)['due'])

    def test_positive_four_point_six_is_not_flat(self):
        self.assertEqual(w._regional_direction(4.6,10.3),'▲ 소폭 증가')
        self.assertEqual(w._regional_direction(-4.6,-10.3),'▼ 소폭 감소')
        self.assertEqual(w._regional_direction(0.,10.3),'→ 보합')
        self.assertEqual(w._regional_direction(99.2,32.9),'▲ 강한 증가')
        self.assertEqual(w._regional_direction(20,None),'판정 보류')

    def test_period_scope_and_small_direction_are_explicit(self):
        result=w.build_monthly(self.now,1336.79,'2026-10-14 daily',pack())
        self.assertIn('3개월 전 2026-06 → 2026-09',result)
        self.assertIn('3개월 누계가 아닙니다',result)
        self.assertIn('충북 전체',result)
        self.assertIn('청주시·특정 회사로 분리되지 않습니다',result)
        self.assertIn('▲ 소폭 증가',result)
        self.assertNotIn('정밀 대용지표',result)
        self.assertIn('HBM 제품 판매단가(ASP)로 해석하지 않습니다',result)
        self.assertIn('한국 관세청 국가별 품목 API',result)

    def test_financial_numbers_do_not_accept_nan_or_infinity(self):
        for value in ['NaN','inf','-inf']:
            self.assertIsNone(w._number(value))
        self.assertEqual(w._number('0'),0.)

    def test_official_government_record_is_not_labeled_company_disclosure(self):
        item=dict(source='관세청 공공데이터포털',direct_link='https://www.data.go.kr/data/15100475/openapi.do',
                  published_at_kst='2026-10-16T01:00:00+09:00',title='관세청 품목별 국가별 수출입실적')
        record=axes.make_record('malaysia_hsk10_export',['KR','MY','8542323000'],
                               dict(amount_usd=1610000000.,weight_kg=4756.),'USD/kg','2026-09',item,'공식 통계',
                               as_of='2026-10-16')
        record['evidence']='official'
        result=axes.render(dict(record=record,old=None,reasons=['새 월']),rate=None)
        self.assertIn('근거 단계: 한국 관세청 공식 무역통계',result)
        self.assertNotIn('근거 단계: 회사 공식자료',result)

    def run_main(self,state,official=None,errors=None,poll=False):
        with tempfile.TemporaryDirectory() as directory:
            out=pathlib.Path(directory);alert=out/'alert.html'
            with patch.object(w,'OUT',out),patch.object(w,'ALERT',alert),patch.object(w,'STATUS',out/'status.md'), \
                 patch.object(w,'load_state',return_value=copy.deepcopy(state)),patch.object(w,'save_state') as save, \
                 patch.object(w,'read_events',return_value=[]),patch.object(w,'fx_quote',return_value=(1336.79,'fixture daily')), \
                 patch.object(w,'_official_poll_due',return_value=(poll,24)), \
                 patch.object(w,'fetch_official_hbm_pack',return_value=(official,errors or [])) as collect:
                w.main()
                if not poll:collect.assert_not_called()
                return save.call_args.args[0], alert.read_text(encoding='utf-8') if alert.exists() else ''

    def test_no_poll_preserves_last_valid_malaysia_values_without_new_observation(self):
        state=dict(malaysia_hsk10_amount_usd=1610000000.,malaysia_hsk10_weight_kg=4756.,
                   malaysia_public_available=True,official_month='202609',official_data_ok=True)
        saved,_=self.run_main(state)
        self.assertEqual(saved['malaysia_hsk10_amount_usd'],state['malaysia_hsk10_amount_usd'])
        self.assertEqual(saved['malaysia_hsk10_weight_kg'],state['malaysia_hsk10_weight_kg'])
        self.assertTrue(saved['malaysia_public_available'])
        self.assertFalse(saved['official_observed_this_run'])

    def test_source_health_uses_actual_poll_times_from_run_966(self):
        # Run 966 started at 11:09:20, while the preserved HTTP ledger ran from
        # 11:10:13 to 11:10:31 KST. No network or Telegram call is made here.
        tz = ZoneInfo('Asia/Seoul')
        times = iter([
            datetime(2026, 10, 30, 11, 9, 20, tzinfo=tz),
            datetime(2026, 10, 30, 11, 10, 13, 231330, tzinfo=tz),
            datetime(2026, 10, 30, 11, 10, 31, 428783, tzinfo=tz),
        ])

        class CapturedClock(datetime):
            @classmethod
            def now(cls, tz=None):
                return next(times)

        baseline = self.notified_state(pack())
        baseline['official_source_health'] = {'status': 'ok'}
        with patch.object(w, 'datetime', CapturedClock):
            saved, text = self.run_main(baseline, pack(), poll=True)
        self.assertEqual(saved['last_official_poll_attempt_kst'], '2026-10-30T11:10:13+09:00')
        self.assertEqual(saved['last_successful_official_at_kst'], '2026-10-30T11:10:31+09:00')
        self.assertEqual(saved['official_source_health']['last_checked_at_kst'], '2026-10-30T11:10:31+09:00')
        self.assertFalse(saved['monthly_due'])
        self.assertEqual(saved['last_official_alert_snapshot'], baseline['last_official_alert_snapshot'])
        self.assertEqual(text, '')

    def test_monthly_message_and_proof_use_poll_completion(self):
        tz = ZoneInfo('Asia/Seoul')
        times = iter([
            datetime(2026, 10, 30, 11, 9, 20, tzinfo=tz),
            datetime(2026, 10, 30, 11, 10, 13, tzinfo=tz),
            datetime(2026, 10, 30, 11, 10, 31, tzinfo=tz),
        ])

        class CapturedClock(datetime):
            @classmethod
            def now(cls, tz=None):
                return next(times)

        baseline = self.notified_state(pack())
        baseline['last_official_alert_month'] = '202608'
        with patch.object(w, 'datetime', CapturedClock), \
             patch.object(w, '_write_trade_validation', wraps=w._write_trade_validation) as write_proof:
            saved, text = self.run_main(baseline, pack(), poll=True)
        self.assertTrue(saved['monthly_due'])
        self.assertIn('<b>조회</b>: 2026-10-30 11:10 KST', text)
        self.assertEqual(write_proof.call_args.kwargs['observed_at'].isoformat(), '2026-10-30T11:10:31+09:00')

    def test_failed_poll_does_not_advance_last_success_time(self):
        tz = ZoneInfo('Asia/Seoul')
        times = iter([
            datetime(2026, 10, 30, 11, 9, 20, tzinfo=tz),
            datetime(2026, 10, 30, 11, 10, 13, tzinfo=tz),
            datetime(2026, 10, 30, 11, 10, 31, tzinfo=tz),
        ])

        class CapturedClock(datetime):
            @classmethod
            def now(cls, tz=None):
                return next(times)

        previous = '2026-10-29T08:28:17+09:00'
        with patch.object(w, 'datetime', CapturedClock):
            saved, _ = self.run_main({'last_successful_official_at_kst': previous}, None, ['연결시간초과'], poll=True)
        self.assertEqual(saved['last_successful_official_at_kst'], previous)
        self.assertEqual(saved['last_official_poll_attempt_kst'], '2026-10-30T11:10:13+09:00')
        self.assertEqual(saved['official_source_health']['last_checked_at_kst'], '2026-10-30T11:10:31+09:00')

    def test_all_unpublished_months_do_not_retain_old_ok_health(self):
        state=dict(official_source_health={'status':'ok'})
        saved,_=self.run_main(state,errors=['공표 대기: 필수 월 자료 없음'],poll=True)
        self.assertEqual(saved['official_source_health']['status'],'waiting_publication')
        self.assertFalse(saved['monthly_due'])

    def test_saved_non_monthly_period_failure_is_validation_hold_and_dedupes(self):
        errors = [
            "지역 금액 단위 검증 보류: invalid:non_monthly_period",
            "지역 금액 단위 검증 보류: invalid:non_monthly_period",
        ]
        previous = dict(official_source_health={"status": "error", "signature": "legacy-generic-failure"})
        saved, text = self.run_main(previous, None, errors, poll=True)
        self.assertEqual(saved["official_source_health"]["status"], "validation_hold")
        self.assertEqual(saved["official_source_health"]["classes"], ["월별 기간 검증 보류"])
        self.assertIn("원자료 월별 검증 보류", text)
        self.assertNotIn("조회 장애", text)
        self.assertFalse(saved["monthly_due"])
        self.assertFalse(saved["official_observed_this_run"])
        due, interval = w._official_poll_due({
            "official_source_health": saved["official_source_health"],
            "official_source_health_version": w.OFFICIAL_SOURCE_HEALTH_VERSION,
            "compare_version": w.COMPARE_VERSION,
            "export_alert_format_version": w.EXPORT_ALERT_FORMAT_VERSION,
        }, self.now)
        self.assertTrue(due)
        self.assertEqual(interval, 1)

        repeated, repeated_text = self.run_main(saved, None, errors, poll=True)
        self.assertEqual(repeated["official_source_health"]["status"], "validation_hold")
        self.assertEqual(repeated_text, "")

    def test_monthly_period_validation_recovery_uses_specific_alert(self):
        p = pack()
        state = self.notified_state(p)
        state["official_source_health"] = {"status": "validation_hold", "target_month": "202609"}
        saved, text = self.run_main(state, p, [], poll=True)
        self.assertEqual(saved["official_source_health"]["status"], "ok")
        self.assertIn("원자료 월별 검증 보류 해소", text)
        self.assertNotIn("원자료 조회 복구", text)
        self.assertFalse(saved["monthly_due"])

    def test_missing_annual_comparison_is_partial_not_full_recovery(self):
        p=pack();p['series'].pop('202509')
        state=dict(official_source_health={'status':'error'})
        saved,text=self.run_main(state,p,['전년 전국 API 실패: ReadTimeout'],poll=True)
        self.assertEqual(saved['official_source_health']['status'],'partial')
        self.assertNotIn('원자료 조회 복구',text)
        self.assertIn('전년동월 <b>확인 불가</b>',text)


if __name__=='__main__':unittest.main()
