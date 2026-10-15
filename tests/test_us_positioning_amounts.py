"""Saved official turnover/FX inputs, source boundaries and operating regressions."""
import copy
import csv
from decimal import Decimal
import gzip
import io
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch
from types import SimpleNamespace

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/"scripts"))
import us_positioning_amounts as amounts
from us_positioning_fx import parse_ecos_usdkrw
from us_positioning_context import SourceReader,context_change_key
import us_positioning_presentation as view
import test_us_positioning_context as context_tests
import test_us_positioning_presentation as original

def fixture():
    return json.loads(gzip.decompress((ROOT/"tests/fixtures/us_positioning_amounts_20261015.json.gz").read_bytes()))

def observed():
    f=fixture()
    turnover=amounts.parse_turnover_csv([f["turnover_csv"].encode()],"2026-10-14")
    ref=f["NDX_20261006"]
    periods=gzip.decompress((ROOT/'tests/fixtures/us_positioning_amounts_periods_20261015.csv.gz').read_bytes())
    return dict(turnover=turnover,turnover_comparisons=amounts.parse_turnover_comparisons_csv([periods],'2026-10-14'),fx=parse_ecos_usdkrw(f["fx_responses"]["2026-10-14"],"2026-10-14"),
                nq_fx=parse_ecos_usdkrw(f["fx_responses"]["2026-10-06"],"2026-10-06"),
                nq_reference=amounts.reference_price([("2026-10-06",ref["primary"])],[("2026-10-06",ref["secondary"])],"2026-10-06"))

def rewrite(rows,fields=None):
    stream=io.StringIO();w=csv.DictWriter(stream,fieldnames=fields or amounts.FIELDS);w.writeheader();w.writerows(rows)
    return stream.getvalue().encode()

class TurnoverTests(unittest.TestCase):
    def test_real_independent_decimal_venue_sums_and_calendar_windows(self):
        value=observed()["turnover"]
        rows=list(csv.DictReader(io.StringIO(fixture()["turnover_csv"])))
        total=sum((Decimal(r["Total Notional"]) for r in rows if r["Day"]=="2026-10-14"),Decimal(0))
        self.assertEqual(str(total),"1059727163779.656264")
        self.assertEqual(Decimal(value["daily_usd"]),total)
        self.assertEqual(value["status"],"verified")
        self.assertIs(amounts.checked_turnover(value,"2026-10-14"),value)
        for key,count,start in (("5d",5,"2026-10-08"),("1m",22,"2026-09-15"),("3m",65,"2026-07-15")):
            w=value["windows"][key]
            independent=sum((Decimal(r["Total Notional"]) for r in rows if r["Day"] in w["session_dates"]),Decimal(0))
            self.assertEqual((w["sessions"],w["start_date"]),(count,start))
            self.assertEqual(Decimal(w["total_usd"]),independent)
            self.assertEqual(Decimal(w["average_daily_usd"]),independent/count)
        previous=Decimal(value["previous_daily_usd"])
        self.assertEqual(Decimal(value["change_pct"]),(total/previous-1)*100)

    def test_venue_day_or_tape_omissions_duplicates_and_extra_venue_fail_closed(self):
        rows=list(csv.DictReader(io.StringIO(fixture()["turnover_csv"])))
        cases=[rows[1:],rows+[rows[0]], [r for r in rows if r["Day"]!="2026-09-17"]]
        changed=copy.deepcopy(rows);changed[0]["Market Participant"]="Unexpected (ZZ)";cases.append(changed)
        changed=copy.deepcopy(rows);changed[0]["Tape A Notional"]="0";cases.append(changed)
        changed=copy.deepcopy(rows);changed[0]["Total Shares"]="0";cases.append(changed)
        changed=copy.deepcopy(rows);changed[0]["Total Trade Count"]="0";cases.append(changed)
        for case in cases:
            self.assertEqual(amounts.parse_turnover_csv([rewrite(case)],"2026-10-14")["status"],"unavailable")

    def test_unknown_columns_nonfinite_negative_and_summary_rows_are_rejected(self):
        raw=fixture()["turnover_csv"]
        self.assertEqual(amounts.parse_turnover_csv([raw.replace("Total Notional","USD Total",1).encode()],"2026-10-14")["status"],"unavailable")
        rows=list(csv.DictReader(io.StringIO(raw)))
        for bad in ("NaN","Infinity","-1",""):
            changed=copy.deepcopy(rows);changed[0]["Total Notional"]=bad
            self.assertEqual(amounts.parse_turnover_csv([rewrite(changed)],"2026-10-14")["status"],"unavailable")
        changed=copy.deepcopy(rows);changed[0]["Market Participant"]="TOTAL"
        self.assertEqual(amounts.parse_turnover_csv([rewrite(changed)],"2026-10-14")["status"],"unavailable")
        self.assertEqual(amounts.parse_turnover_csv([b"<html>blocked</html>"],"2026-10-14")["status"],"unavailable")

    def test_future_rows_are_excluded_and_missing_current_session_is_not_forward_filled(self):
        rows=list(csv.DictReader(io.StringIO(fixture()["turnover_csv"])))
        later=copy.deepcopy(rows[0]);later["Day"]="2026-10-15"
        self.assertEqual(amounts.parse_turnover_csv([rewrite(rows+[later])],"2026-10-14"),observed()["turnover"])
        self.assertEqual(amounts.parse_turnover_csv([rewrite(rows)],"2026-10-15")["status"],"unavailable")

    def test_tampered_saved_values_or_operands_cannot_reach_rendering(self):
        good=observed()["turnover"]
        for path,value in ((("daily_usd",),"1"),(("currency",),"KRW"),(("scope",),"S&P500"),(("windows","1m","average_daily_usd"),"1"),(("required_venue_codes",),["Q"])):
            changed=copy.deepcopy(good);target=changed
            for p in path[:-1]:target=target[p]
            target[path[-1]]=value
            self.assertIsNone(amounts.checked_turnover(changed,"2026-10-14"))
        self.assertIsNone(amounts.checked_turnover(good,"2026-10-13"))
        changed=copy.deepcopy(good);changed["daily_operands"][-1][1][0][-1]="1"
        self.assertIsNone(amounts.checked_turnover(changed,"2026-10-14"))

    def test_latest_source_data_changes_remain_dedupe_changes(self):
        values,context=context_tests.BriefTests().sources();context["amounts"]=observed()
        first=context_change_key(context,"2026-10-14")
        changed=copy.deepcopy(context);changed["amounts"]["fx"]["krw_per_usd"]="1341"
        self.assertNotEqual(first,context_change_key(changed,"2026-10-14"))
        self.assertEqual(first,context_change_key(copy.deepcopy(context),"2026-10-14"))

class MonetaryTests(unittest.TestCase):
    def test_krw_parentheses_use_exact_official_rate_and_correct_sign(self):
        fx=observed()["fx"]
        self.assertEqual(amounts.money_pair("1059727163779.656264",fx,"2026-10-14"),"1.0597조달러 (1,420.56조원)")
        self.assertEqual(amounts.money_pair("-100000000",fx,"2026-10-14",True),"-1.00억달러 (-1,340.50억원)")
        self.assertEqual(amounts.money_pair(0,fx,"2026-10-14"),"0.00달러 (0.00원)")
        for v in ("NaN",True,None):
            self.assertEqual(amounts.money_pair(v,fx,"2026-10-14"),"금액 확인 대기")

    def test_wrong_missing_or_tampered_fx_keeps_original_amount_and_visible_conversion_hold(self):
        for fx,target in (({}, "2026-10-14"),(observed()["fx"],"2026-10-06")):
            self.assertIn("1.00억달러 (원화 환산 보류",amounts.money_pair(100000000,fx,target))
        fx=observed()["fx"];fx["krw_per_usd"]="1"
        self.assertIn("원화 환산 보류",amounts.money_pair(100000000,fx,"2026-10-14"))

    def test_actual_reference_price_conflict_does_not_borrow_latest_price(self):
        value=observed()["nq_reference"]
        self.assertEqual(value["status"],"unavailable")
        self.assertIsNone(amounts.notional(19212,value,"2026-10-06"))
        self.assertEqual(value["primary_close"],31224.69)
        self.assertEqual(value["secondary_close"],31224.470703125)

    def test_nq_fixed_price_reference_multiplier_date_and_integer_contracts(self):
        ref=amounts.reference_price([("2026-10-06",30000)],[("2026-10-06",30000)],"2026-10-06")
        self.assertEqual(amounts.notional(19212,ref,"2026-10-06"),Decimal("11527200000"))
        self.assertEqual(amounts.notional(-5511,ref,"2026-10-06"),Decimal("-3306600000"))
        self.assertIsNone(amounts.notional(1.5,ref,"2026-10-06"))
        self.assertIsNone(amounts.notional(19212,ref,"2026-10-14"))
        for key,bad in (("multiplier_usd_per_point","2"),("symbol","NQ=F"),("primary_close",1),("basis","futures settlement")):
            wrong=copy.deepcopy(ref);wrong[key]=bad
            self.assertIsNone(amounts.notional(19212,wrong,"2026-10-06"))

    def test_secure_reader_redacts_real_request_url_and_exception_from_ledger(self):
        key="FAKE-ECOS-SECRET"
        for fail in (False,True):
            with tempfile.TemporaryDirectory() as tmp:
                reader=SourceReader(tmp)
                response=SimpleNamespace(content=b'{}',status_code=200,url="https://ecos.bok.or.kr/"+key,
                                         raise_for_status=lambda:None)
                with patch("requests.get",side_effect=RuntimeError(key) if fail else None,return_value=response):
                    if fail:
                        with self.assertRaises(RuntimeError):reader.get("https://ecos.bok.or.kr/"+key,evidence_url="https://ecos.bok.or.kr/[REDACTED]")
                    else:reader.get("https://ecos.bok.or.kr/"+key,evidence_url="https://ecos.bok.or.kr/[REDACTED]")
                reader.save()
                self.assertNotIn(key,(Path(tmp)/"us_positioning_source_evidence.json").read_text())
                self.assertTrue(reader.records[0]["request_credentials_redacted"])

class PeriodTurnoverTests(unittest.TestCase):
    def raw(self):
        return gzip.decompress((ROOT/'tests/fixtures/us_positioning_amounts_periods_20261015.csv.gz').read_bytes())

    def test_independent_adjacent_period_sums_averages_counts_and_directions(self):
        value=observed();current=value['turnover'];comp=value['turnover_comparisons']
        self.assertEqual(comp['status'],'verified')
        self.assertIs(amounts.checked_turnover_comparisons(comp,'2026-10-14',current),comp)
        rows=list(csv.DictReader(io.StringIO(self.raw().decode())))
        expected={'5d':('2026-10-08','2026-10-01',5,5,'-5.37'),
                  '1m':('2026-09-15','2026-08-17',22,20,'9.49'),
                  '3m':('2026-07-15','2026-04-15',65,62,'-13.45')}
        for key,(start,prior_start,count,prior_count,pct) in expected.items():
            w=comp['windows'][key];a,b=w['current'],w['previous']
            self.assertEqual((a['start_date'],b['start_date'],a['sessions'],b['sessions']),(start,prior_start,count,prior_count))
            self.assertFalse(set(a['session_dates'])&set(b['session_dates']))
            actual=[]
            for part in (a,b):
                total=sum((Decimal(r['Total Notional']) for r in rows if r['Day'] in part['session_dates']),Decimal(0))
                self.assertEqual(Decimal(part['total_usd']),total)
                self.assertEqual(Decimal(part['average_daily_usd']),total/part['sessions'])
                actual.append(total/part['sessions'])
            self.assertEqual(Decimal(w['average_change_usd']),actual[0]-actual[1])
            self.assertLess(abs(Decimal(w['average_change_pct'])-(actual[0]/actual[1]-1)*100),Decimal('1e-20'))
            self.assertEqual(f"{Decimal(w['average_change_pct']):.2f}",pct)

    def test_official_txse_live_date_changes_expected_roster_without_zero_fill(self):
        comp=observed()['turnover_comparisons'];days=dict(comp['daily_operands'])
        self.assertEqual(len(days['2026-07-09']),20)
        self.assertEqual(len(days['2026-07-10']),21)
        self.assertNotIn('F',{r[0] for r in days['2026-07-09']})
        self.assertIn('F',{r[0] for r in days['2026-07-10']})
        self.assertEqual(comp['venue_roster']['txse_live_date'],'2026-07-10')
        self.assertEqual(sum(len(r) for r in days.values()),2608)

    def test_prior_quarter_missing_venue_or_day_keeps_shorter_comparisons_and_current_values(self):
        rows=list(csv.DictReader(io.StringIO(self.raw().decode())))
        older=[r for r in rows if r['Day']=='2026-04-15']
        for missing in ([older[0]],older):
            changed=[r for r in rows if r not in missing];raw=rewrite(changed)
            current=amounts.parse_turnover_csv([raw],'2026-10-14')
            comp=amounts.parse_turnover_comparisons_csv([raw],'2026-10-14')
            self.assertEqual(current,observed()['turnover'])
            self.assertEqual(comp['status'],'partial')
            self.assertEqual(comp['windows']['5d']['status'],'verified')
            self.assertEqual(comp['windows']['1m']['status'],'verified')
            self.assertEqual(comp['windows']['3m']['status'],'unavailable')
            self.assertIs(amounts.checked_turnover_comparisons(comp,'2026-10-14',current),comp)

    def test_tampered_comparison_dates_sums_average_pct_roster_and_current_values_are_withheld(self):
        good=observed();current=good['turnover']
        cases=[(('windows','1m','previous','start_date'),'2026-08-18'),
               (('windows','1m','previous','sessions'),22),
               (('windows','3m','previous','total_usd'),'1'),
               (('windows','5d','current','average_daily_usd'),'1'),
               (('windows','5d','average_change_pct'),'1'),
               (('venue_roster','txse_live_date'),'2026-07-06')]
        for path,bad in cases:
            changed=copy.deepcopy(good['turnover_comparisons']);dest=changed
            for key in path[:-1]:dest=dest[key]
            dest[path[-1]]=bad
            self.assertIsNone(amounts.checked_turnover_comparisons(changed,'2026-10-14',current))
        self.assertIsNone(amounts.checked_turnover_comparisons(good['turnover_comparisons'],'2026-10-13',current))

    def test_direction_uses_daily_average_when_total_moves_the_other_way(self):
        comp=copy.deepcopy(observed()['turnover_comparisons']);w=comp['windows']['1m']
        current=set(w['current']['session_dates']);previous=set(w['previous']['session_dates'])
        for date,rows in comp['daily_operands']:
            if date in current|previous:
                for i,row in enumerate(rows):
                    v='95' if date in current else '100'
                    row[1:]=[v,'0','0',v] if i==0 else ['0','0','0','0']
        computed=amounts.turnover_comparisons_from_operands(comp['daily_operands'],'2026-10-14')['windows']['1m']
        self.assertGreater(Decimal(computed['current']['total_usd']),Decimal(computed['previous']['total_usd']))
        self.assertEqual(Decimal(computed['average_change_pct']),Decimal('-5'))

    def test_duplicate_responses_and_invalid_tape_totals_are_not_verified(self):
        raw=self.raw()
        self.assertEqual(amounts.parse_turnover_comparisons_csv([raw,raw],'2026-10-14')['status'],'unavailable')
        rows=list(csv.DictReader(io.StringIO(raw.decode())));next(r for r in rows if r['Day']=='2026-10-14')['Total Notional']='NaN'
        self.assertEqual(amounts.parse_turnover_comparisons_csv([rewrite(rows)],'2026-10-14')['status'],'unavailable')

    def test_old_invalid_numbers_or_tape_totals_do_not_hide_verified_shorter_periods(self):
        for column,bad in (('Total Notional','NaN'),('Total Notional','1'),('Total Shares','NaN')):
            rows=list(csv.DictReader(io.StringIO(self.raw().decode())))
            next(r for r in rows if r['Day']=='2026-04-15')[column]=bad
            comp=amounts.parse_turnover_comparisons_csv([rewrite(rows)],'2026-10-14')
            self.assertEqual(comp['status'],'partial')
            self.assertEqual(comp['windows']['5d']['status'],'verified')
            self.assertEqual(comp['windows']['1m']['status'],'verified')
            self.assertEqual(comp['windows']['3m']['missing_dates'],['2026-04-15'])

    def test_historical_revisions_change_context_and_averages_without_changing_daily_amount(self):
        values,ctx=context_tests.BriefTests().sources();ctx['amounts']=observed()
        before=context_change_key(ctx,'2026-10-14');changed=copy.deepcopy(ctx)
        operands=changed['amounts']['turnover_comparisons']['daily_operands']
        row=operands[0][1][0];row[1]=str(Decimal(row[1])+100);row[4]=str(Decimal(row[4])+100)
        changed['amounts']['turnover_comparisons']=amounts.turnover_comparisons_from_operands(operands,'2026-10-14')
        self.assertNotEqual(context_change_key(changed,'2026-10-14'),before)
        self.assertEqual(changed['amounts']['turnover'],ctx['amounts']['turnover'])
        self.assertNotEqual(changed['amounts']['turnover_comparisons']['windows']['3m'],ctx['amounts']['turnover_comparisons']['windows']['3m'])

    def test_period_amounts_and_directions_are_visible_with_fx_limits_and_one_message(self):
        values,ctx=AmountRenderingTests().sources();out=AmountRenderingTests().render(values,ctx)
        for phrase in ('5거래일 <b>↓ 감소 -5.37%','9,654.22억달러 (1,294.15조원) → 9,135.89억달러 (1,224.67조원)',
                       '1개월 <b>↑ 증가 +9.49%','9,011.53억달러 (1,208.00조원) → 9,866.79억달러 (1,322.64조원)',
                       '3개월 <b>↓ 감소 -13.45%','11,191.75억달러 (1,500.25조원) → 9,685.95억달러 (1,298.40조원)',
                       '일평균, 직전 같은 기간 → 최근 기간','순유입액 아님'):
            self.assertIn(phrase,out)
        ctx['amounts']['fx']={};out=AmountRenderingTests().render(values,ctx)
        self.assertIn('9,654.22억달러 (원화 환산 보류) → 9,135.89억달러 (원화 환산 보류)',out)
        self.assertLessEqual(len(out.strip()),view.BRIEF_MAX_CHARS)

class AmountRenderingTests(unittest.TestCase):
    def sources(self):
        values,context=context_tests.BriefTests().sources();context["amounts"]=observed()
        return values,context

    def render(self,values,context,detail=False):
        fn=view.render_detail_document if detail else view.render_alert
        return fn(values["CFTC|cot"],values["Cboe|options"],values["Nasdaq SOX|sox"],list(values.values()),list(values.values()),context=context)

    def summary(self,out):
        return out.split("<b>한눈에 보기</b>",1)[1].split("<b>① ",1)[0]

    def test_restored_summary_precedes_details_and_matches_dates_amounts_and_positions(self):
        values,context=self.sources();out=self.render(values,context);summary=self.summary(out)
        self.assertEqual(out.count("<b>한눈에 보기</b>"),1)
        for phrase in ("반도체(SOX): 11,684.38pt | 1D -4.30% | 3D -7.06% | 5D -10.58%",
                       "당일 증가 +20.06% / 5일 감소 -5.37% / 1개월 증가 +9.49% / 3개월 감소 -13.45%",
                       "통합 기관: 순롱 74,856계약 | 주간 순포지션 변화 +4,055계약 · 순롱 확대",
                       "통합 헤지펀드성: 순숏 26,738계약 | 주간 순포지션 변화 +7,044계약 · 순숏 축소",
                       "NQ E-mini: 순숏 19,212계약 · 1주 전 대비 순숏 5,511계약 축소",
                       "3년 순숏 27 / 총숏 20백분위 · 10년 순숏 45 / 총숏 38백분위",
                       "Cboe 옵션: 주식 P/C 0.61(콜이 풋의 1.63배) / 지수 1.01(거의 1:1) / 전체 0.88",
                       "가격보다 8일 이전 · 가격 전환 확인 아님"):
            self.assertIn(phrase,summary)
        self.assertLessEqual(len(out.strip()),view.BRIEF_MAX_CHARS)

    def test_summary_withholds_conflicting_sources_and_does_not_invent_krw(self):
        values,context=self.sources()
        context["indices"]["NDX"]["returns"]["windows"]["1d"]["return_pct"]+=1
        context["amounts"]["fx"]={}
        values["CFTC|cot"]["history_3y"]["week_window"]["actors"]["leveraged_funds"]["net_change"]+=1
        out=self.render(values,context);summary=self.summary(out)
        self.assertIn("나스닥100 종가: 확인 대기",out)
        self.assertIn("원화 환산 보류",out)
        self.assertIn("NQ E-mini: 현재·주간 변화 확인 대기",summary)
        self.assertNotIn("1,420.56조원",summary)
        self.assertNotIn("5,511계약 축소",summary)
        context["amounts"]["turnover"]["daily_usd"]="1"
        self.assertIn("거래대금 방향: 당일 확인 대기",self.summary(self.render(values,context)))

    def test_summary_does_not_relabel_an_older_observation_as_one_week(self):
        values,context=self.sources()
        values["CFTC|cot"]["history_3y"]["week_window"]["base_date"]="2026-09-22"
        summary=self.summary(self.render(values,context))
        self.assertIn("직전 관측(2026-09-22) 대비",summary)
        self.assertNotIn("1주 전 대비",summary)

    def test_turnover_direction_words_recompute_from_new_operands_in_both_directions_and_zero(self):
        for mode,word in ((1,'증가'),(-1,'감소'),(0,'동일')):
            values,context=self.sources();a=context['amounts'];original=a['turnover_comparisons']['daily_operands']
            dates=[r[0] for r in original]
            latest3=set(dates[-65:]);latest1=set(dates[-22:]);latest5=set(dates[-5:])
            operands=[]
            for d,venues in original:
                total=420
                if mode==1:
                    total=840 if d in latest3 else 420
                    if d in latest1:total=1680
                    if d in latest5:total=3360
                    if d==dates[-1]:total=6720
                elif mode==-1:
                    total=420 if d in latest3 else 840
                    if d in latest1:total=210
                    if d in latest5:total=105
                    if d==dates[-1]:total=42
                v=str(total//len(venues));self.assertEqual(total%len(venues),0)
                operands.append([d,[[venue[0],v,'0','0',v] for venue in venues]])
            a['turnover']=amounts.turnover_from_operands([r for r in operands if r[0] in latest3],'2026-10-14')
            a['turnover_comparisons']=amounts.turnover_comparisons_from_operands(operands,'2026-10-14')
            out=self.summary(self.render(values,context))
            for label in ('당일','5일','1개월','3개월'):
                self.assertIn(label+' '+word,out)
            self.assertNotIn('20.06%',out)

    def test_actual_new_brief_has_point_levels_actual_turnover_krw_and_precise_missingness(self):
        values,context=self.sources();out=self.render(values,context)
        for phrase in ("11,684.38pt","-524.41pt","29,950.82pt","7,718.94pt","1.0597조달러 (1,420.56조원)",
                       "20.06%","5거래일","1개월","3개월","1,340.50원","Cboe 전체 거래소·TRF","옵션 전체 거래량","프리미엄 거래대금 미제공","NDX 종가 누락·불일치"):
            self.assertIn(phrase,out)
        self.assertNotIn("11,684.38달러",out)
        self.assertLessEqual(len(out.strip()),view.BRIEF_MAX_CHARS)
        for line in out.splitlines():
            balance=original.TagBalance();balance.feed(line);self.assertFalse(balance.stack)
        detail=self.render(values,context,True)
        for phrase in ("2026-07-15~2026-10-14, 65거래일","합계","원화"):
            self.assertIn(phrase,detail)

    def test_verified_reference_path_keeps_short_size_notional_and_single_message(self):
        values,context=self.sources()
        context["amounts"]["nq_reference"]=amounts.reference_price([("2026-10-06",30000)],[("2026-10-06",30000)],"2026-10-06")
        out=self.render(values,context)
        self.assertIn("순숏 19,212계약",out)
        self.assertIn("115.27억달러",out)
        self.assertIn("계약 수 변화의 동일가격 환산",out)
        self.assertIn("거래대금·증거금 아님",out)
        self.assertLessEqual(len(out.strip()),view.BRIEF_MAX_CHARS)
        sources=list(values.values())
        with_link=view.render_alert(values["CFTC|cot"],values["Cboe|options"],values["Nasdaq SOX|sox"],sources,sources,
                                   context=context,detail_url="https://github.com/qedgwangju-dot/khs-watch/actions/runs/38736114255")
        self.assertIn("한눈에 보기",with_link)
        self.assertLessEqual(len(with_link.strip()),view.BRIEF_MAX_CHARS)
        detail=self.render(values,context,True)
        self.assertIn("만기별 실제 선물 정산가 평가액",detail)

    def test_previous_amounts_layout_upgrades_summary_once_and_preserves_same_value_dedupe(self):
        values,context=self.sources()
        run=lambda prior=None:original.OperatingIntegrationTests.run_operating_tail(self,values,prior,context)
        prior=run()["pending"]
        prior["presentation_version"]="us-positioning-amounts-krw-20261015-v1"
        preserved=copy.deepcopy(prior)
        upgraded=run(prior)
        self.assertTrue(upgraded["gate"])
        self.assertEqual(upgraded["updates"],0)
        self.assertIn("한눈에 보기",upgraded["alert"])
        self.assertEqual(upgraded["pending"]["values"],preserved["values"])
        self.assertEqual(upgraded["pending"]["seen"],preserved["seen"])
        self.assertEqual(prior,preserved)
        following=run(upgraded["pending"])
        self.assertIsNone(following["alert"])
        self.assertIsNone(following["pending"])

    def test_unavailable_fx_never_invents_a_krw_value_and_tampered_turnover_is_withheld(self):
        values,context=self.sources();context["amounts"]["fx"]={}
        out=self.render(values,context)
        self.assertIn("원화 환산 보류",out);self.assertNotIn("1,420.56조원",out)
        context["amounts"]["turnover"]["daily_usd"]="1"
        out=self.render(values,context)
        self.assertIn("실제 거래대금: 확인 대기",out)
        self.assertNotIn("1.0597조달러",out)

    def test_same_amounts_next_operating_input_suppresses_duplicates_and_fx_changes_remain_eligible(self):
        values,context=self.sources()
        run=lambda ctx,prior=None:original.OperatingIntegrationTests.run_operating_tail(self,values,prior,ctx)
        first=run(context);second=run(copy.deepcopy(context),first["pending"])
        self.assertTrue(first["gate"]);self.assertIsNone(second["alert"]);self.assertIsNone(second["pending"])
        changed=copy.deepcopy(context);changed["amounts"]["fx"]={}
        third=run(changed,first["pending"])
        self.assertIsNotNone(third["alert"]);self.assertEqual(third["updates"],1)

if __name__=="__main__":unittest.main()
