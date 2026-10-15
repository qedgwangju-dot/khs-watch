"""Source/operand/meaning regressions for the expanded operating presentation."""
import copy
import gzip
import json
import sys
import unittest
from datetime import date
from decimal import Decimal
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/"scripts"))
from us_positioning_context import (
    sessions,price_path,checked_path,price_returns,checked_returns,
    position_week_window,checked_composition,parse_cboe_day,option_distributions,
    checked_options,breadth_comparison,context_change_key,parse_yahoo,parse_nasdaq,
)
import us_positioning_presentation as view
import test_us_positioning_horizons as horizons
import test_us_positioning_presentation as original

def fixture():
    return json.loads((ROOT/"tests/fixtures/us_positioning_context_20261015.json").read_text(encoding="utf-8"))

def option_rows(value):
    rows={}
    for key in ("equity","index","total"):
        for r in value["values"][key]["operands"]:
            mt=rows.setdefault(r["date"],dict(date=r["date"],metrics={}))["metrics"]
            mt.update({key+"_calls":r["calls"],key+"_puts":r["puts"],key+"_pc_ratio":r["pc_ratio"]})
    return list(rows.values())

def current():
    return original.snapshot()["Cboe|options"]["metrics"]

class PricePathTests(unittest.TestCase):
    def test_observed_us_holiday_is_not_a_missing_session(self):
        days=sessions("2026-09-04","2026-09-08")
        self.assertEqual(days,["2026-09-04","2026-09-08"])

    def test_increasing_decreasing_and_flat_rules_are_separate(self):
        ds=sessions("2026-06-01","2026-10-14")
        for slope,label in ((1,"상승"),(-1,"하락"),(0,"혼재")):
            rows=[(d,1000+slope*i) for i,d in enumerate(ds)]
            result=price_path("2026-10-14",rows,rows,"TEST")
            self.assertEqual(result["status"],"verified")
            self.assertEqual(result["values"]["trend"],label)
            self.assertIsNotNone(checked_path(result,"2026-10-14"))

    def test_actual_sox_month_gain_does_not_claim_a_current_uptrend(self):
        result=fixture()["sox_path"];v=result["values"]
        self.assertIsNotNone(checked_path(result,"2026-10-14"))
        self.assertGreater(result["month_windows"]["1m"]["return_pct"],0)
        self.assertLess(v["d5_pct"],0)
        self.assertEqual(v["trend"],"혼재")
        self.assertLess(v["close"],v["ma20"])
        self.assertLess(v["close"],v["ma60"])
        self.assertGreater(v["ma20_change5_pct"],0)
        expected=sum(Decimal(str(r[1])) for r in result["operands"][-20:])/20
        self.assertAlmostEqual(v["ma20"],float(expected),places=9)
        self.assertAlmostEqual(v["drawdown63_pct"],float((Decimal("11684.38")/Decimal("13217.82")-1)*100),places=10)

    def test_missing_internal_session_and_provider_conflict_do_not_fill(self):
        result=fixture()["sox_path"];rows=result["operands"]
        primary=[(r[0],r[1]) for r in rows];peer=[(r[0],r[2]) for r in rows]
        self.assertEqual(price_path("2026-10-14",primary,peer[:-10]+peer[-9:],"SOX")["status"],"unavailable")
        changed=copy.deepcopy(peer);changed[-10]=(changed[-10][0],changed[-10][1]+1)
        self.assertEqual(price_path("2026-10-14",primary,changed,"SOX")["status"],"unavailable")

    def test_duplicated_conflict_invalid_close_and_wrong_date_stay_unavailable(self):
        item=fixture()["sox_path"];rows=[(r[0],r[1]) for r in item["operands"]]
        self.assertEqual(price_path("2026-10-14",rows+[("2026-10-14",1)],rows,"SOX")["status"],"unavailable")
        for bad in (0,None,float("nan"),True):
            self.assertEqual(price_path("2026-10-14",rows[:-1]+[("2026-10-14",bad)],rows,"SOX")["status"],"unavailable")
        self.assertIsNone(checked_path(item,"2026-10-15"))

    def test_saved_trend_return_or_tolerance_tampering_is_rejected(self):
        for location,key,new in (("values","trend","상승"),("values","ma20",1),("values","drawdown63_pct",0),("top","tolerance_points",10)):
            item=copy.deepcopy(fixture()["sox_path"])
            (item if location=="top" else item[location])[key]=new
            self.assertIsNone(checked_path(item,"2026-10-14"))

    def test_real_ndx_conflict_preserves_separately_verified_returns(self):
        item=fixture()["context"]["indices"]["NDX"]
        self.assertEqual(item["status"],"unavailable")
        self.assertIn("2026-10-06",item["reason"])
        self.assertIsNone(checked_path(item,"2026-10-14"))
        summary=checked_returns(item["returns"],"2026-10-14")
        self.assertIsNotNone(summary)
        self.assertAlmostEqual(summary["windows"]["5d"]["return_pct"],-3.880798765600091)
        self.assertAlmostEqual(summary["windows"]["1m"]["return_pct"],2.827807448443309)
        text="\n".join(view.path_lines(item,date(2026,10,14),"나스닥100"))
        self.assertIn("-3.88%",text)
        self.assertIn("1개월 전 대비 +2.83%",text)
        self.assertIn("확인 대기",text)
        self.assertNotIn("현재 추세(규칙):",text)

    def test_return_operand_or_cutoff_tampering_is_rejected(self):
        item=copy.deepcopy(fixture()["context"]["indices"]["NDX"]["returns"])
        item["windows"]["1m"]["base_date"]="2026-09-15"
        self.assertIsNone(checked_returns(item,"2026-10-14"))

class CompositionTests(unittest.TestCase):
    def test_actual_week_month_and_quarter_decompositions_reconcile(self):
        f=fixture()
        cases=[(f["week"],3199,-2312,5511),(f["month_positions"]["1m"],-4012,1108,-5120),(f["month_positions"]["3m"],14553,-34852,49405)]
        for window,l,s,n in cases:
            item=checked_composition(window,"leveraged_funds","2026-10-06")
            self.assertIsNotNone(item)
            self.assertEqual((item["long_change"],item["short_change"],item["net_change"]),(l,s,n))
            self.assertEqual(l-s,n)
        self.assertIn("롱 보유 변화의 영향이 더 큼",view.composition_description(checked_composition(cases[1][0],"leveraged_funds","2026-10-06")))
        self.assertIn("숏 보유 변화의 영향이 더 큼",view.composition_description(checked_composition(cases[2][0],"leveraged_funds","2026-10-06")))

    def test_delta_population_and_date_tampering_never_get_a_composition(self):
        base=fixture()["week"]
        for what in ("long_change","short_change","net_change"):
            item=copy.deepcopy(base);item["actors"]["leveraged_funds"][what]+=1
            self.assertIsNone(checked_composition(item,"leveraged_funds","2026-10-06"))
        item=copy.deepcopy(base);item["cftc_code"]="20974+"
        self.assertIsNone(checked_composition(item,"leveraged_funds","2026-10-06"))
        self.assertIsNone(checked_composition(base,"leveraged_funds","2026-10-13"))

    def test_missing_long_short_fields_never_become_zero(self):
        rows=[dict(date="2026-09-29",oi=100,lev_long=None,lev_short=30),
              dict(date="2026-10-06",oi=110,lev_long=50,lev_short=40)]
        out=position_week_window(rows,"2026-10-06",dict(open_interest=110,leveraged_long=50,leveraged_short=40))
        self.assertEqual(out["status"],"unavailable")
        self.assertIsNone(checked_composition(out,"leveraged_funds","2026-10-06"))

class OptionHistoryTests(unittest.TestCase):
    def test_actual_publisher_page_has_dated_arithmetic_valid_rows(self):
        with gzip.open(ROOT/"tests/fixtures/us_positioning_context_cboe_20261014.html.gz","rb") as f:raw=f.read()
        result=parse_cboe_day(raw,"2026-10-14")
        self.assertEqual(result["metrics"]["equity_calls"],2931155)
        self.assertEqual(result["metrics"]["equity_puts"],1799662)
        self.assertEqual(result["metrics"]["equity_pc_ratio"],.61)
        with self.assertRaises(ValueError):parse_cboe_day(raw,"2026-10-13")
        with self.assertRaises(ValueError):parse_cboe_day(raw.replace(b"14 October 2026",b"13 October 2026"),"2026-10-14")

    def test_actual_windows_exclude_current_day_and_validate_each_expected_session(self):
        options=fixture()["context"]["options"]
        for key,count in (("1m",22),("3m",65)):
            out=checked_options(options[key],current(),"2026-10-14")
            self.assertIsNotNone(out)
            self.assertEqual(out["expected_sessions"],count)
            self.assertTrue(all(r["date"]<"2026-10-14" for r in out["values"]["equity"]["operands"]))
        m=options["1m"]["values"]["equity"]
        sample=sorted(Decimal(str(r["pc_ratio"])) for r in m["operands"])
        self.assertEqual((sample[10]+sample[11])/2,Decimal("0.565"))
        self.assertAlmostEqual(m["current_le_percent"],17/22*100)

    def test_missing_old_date_blocks_only_the_affected_window(self):
        rows=option_rows(fixture()["context"]["options"]["3m"])
        rows=[r for r in rows if r["date"]!="2026-07-14"]
        out=option_distributions(rows,"2026-10-14",current())
        self.assertEqual(out["1m"]["status"],"verified")
        self.assertEqual(out["3m"]["status"],"unavailable")
        self.assertIn("2026-07-14",out["3m"]["missing_dates"])
        self.assertNotIn("values",out["3m"])

    def test_saved_median_percentile_and_current_ratio_tampering_fail(self):
        for key,value in (("median_pc",0),("current_le_percent",100),("current_pc",0)):
            out=copy.deepcopy(fixture()["context"]["options"]["1m"])
            out["values"]["equity"][key]=value
            self.assertIsNone(checked_options(out,current(),"2026-10-14"))

    def test_conflicting_duplicate_and_invalid_volume_are_not_silently_used(self):
        rows=option_rows(fixture()["context"]["options"]["3m"])
        bad=copy.deepcopy(rows[-1]);bad["metrics"]["equity_calls"]+=10000
        out=option_distributions(rows+[bad],"2026-10-14",current())
        self.assertTrue(all(w["status"]=="unavailable" for w in out.values()))
        rows[-1]["metrics"]["equity_calls"]=0
        out=option_distributions(rows,"2026-10-14",current())
        self.assertTrue(all(w["status"]=="unavailable" for w in out.values()))

class BreadthAndPresentationTests(unittest.TestCase):
    def test_actual_adjusted_etf_spread_uses_the_same_dates_and_units(self):
        value=fixture()["context"]["breadth"]
        out=breadth_comparison(value["series"],"2026-10-14")
        self.assertEqual(out,value["comparison"])
        for window in out["windows"].values():
            l=(Decimal(str(window["rsp_end"]))/Decimal(str(window["rsp_base"]))-1)*100
            r=(Decimal(str(window["spy_end"]))/Decimal(str(window["spy_base"]))-1)*100
            self.assertAlmostEqual(window["difference_pp"],float(l-r),places=9)
        self.assertIn("not advancing-stock percentage",out["population"])
        text="\n".join(view.breadth_lines(value,date(2026,10,14)))
        self.assertIn("원종가는 Nasdaq 대조",text)
        self.assertIn("조정값은 단일 제공처",text)
        self.assertIn("상승 종목 비율",text)

    def test_missing_adjusted_series_or_different_dates_are_not_raw_price_substitutes(self):
        value=fixture()["context"]["breadth"]["series"]
        value["RSP"]["adjusted_operands"]=[]
        self.assertEqual(breadth_comparison(value,"2026-10-14")["status"],"unavailable")

    def test_detail_keeps_price_trend_return_population_and_intent_separate(self):
        f=fixture();values=horizons.enriched_snapshot()
        values["CFTC|cot"]["history_3y"]["week_window"]=f["week"]
        values["Nasdaq SOX|sox"]["metrics"]["price_path"]=f["sox_path"]
        out=view.render_detail_alert(values["CFTC|cot"],values["Cboe|options"],values["Nasdaq SOX|sox"],list(values.values()),list(values.values()),context=f["context"])
        for phrase in ["미국 주요지수 최근 5거래일 하락","1개월 전 대비","SOX 현재 추세(규칙): <b>혼재","20일선 아래·60일선 아래","-11.60%","+3,199 / 숏 -2,312 / 순포지션 변화 +5,511","신규 주문·청산·헤지 목적은 미확인","0.565","77.3%","매수·매도는 구분되지 않아"]:
            self.assertIn(phrase,out)
        self.assertNotIn("콜 매수 우위",out)
        self.assertTrue(all(len(line)<=3800 for line in out.splitlines()))
        # The full detail retains the former two-chunk analysis, outside sending.
        chunks=[];current_lines=[]
        for line in out.strip().splitlines():
            if current_lines and len("\n".join(current_lines+[line]))>3800:
                chunks.append("\n".join(current_lines));current_lines=[]
            current_lines.append(line)
        chunks.append("\n".join(current_lines))
        self.assertEqual(len(chunks),2)
        for chunk in chunks:
            for tag in ("b","a"):
                self.assertEqual(chunk.count("<"+tag+">") if tag=="b" else chunk.count("<a "),chunk.count("</"+tag+">"))


class BriefTests(unittest.TestCase):
    def sources(self):
        f = fixture()
        values = horizons.enriched_snapshot()
        values["CFTC|cot"]["history_3y"]["week_window"] = f["week"]
        values["Nasdaq SOX|sox"]["metrics"]["price_path"] = f["sox_path"]
        return values, f["context"]

    def render(self, values=None, context=None, **kwargs):
        if values is None:
            values, context = self.sources()
        return view.render_alert(values["CFTC|cot"], values["Cboe|options"], values["Nasdaq SOX|sox"],
                                 list(values.values()), list(values.values()), context=context, **kwargs)

    def test_actual_expanded_input_becomes_one_short_message_without_detail_appendices(self):
        values, context = self.sources()
        message = self.render(values, context, detail_url="https://github.com/qedgwangju-dot/khs-watch/actions/runs/123")
        detail = view.render_detail_alert(values["CFTC|cot"],values["Cboe|options"],values["Nasdaq SOX|sox"],list(values.values()),list(values.values()),context=context)
        self.assertLessEqual(len(message.strip()), view.BRIEF_MAX_CHARS)
        self.assertLess(len(message.strip()), len(detail.strip()) * .6)
        self.assertIn("상세 수치·계산·출처</a>", message)
        for phrase in ("10년 백분위", "원수치", "112,821", "2,931,155"):
            self.assertNotIn(phrase, message)
            self.assertIn(phrase, detail)
        for line in message.splitlines():
            balance = original.TagBalance()
            balance.feed(line)
            self.assertFalse(balance.stack, line)

    def test_brief_retains_period_returns_current_trend_and_source_conflict(self):
        message = self.render()
        for phrase in ("나스닥100·S&P500 최근 5거래일 하락", "2026-10-14 마감",
                       "1개월 전 대비: <b>+4.97% · 상승", "3개월 전 대비: <b>-7.72% · 하락",
                       "1일 -2.02% / 3일 -3.02% / 5일 -3.88%", "1개월 +2.83% / 3개월 +1.23%",
                       "1일 -1.11% / 3일 -1.19% / 5일 -1.06%", "1개월 +1.30% / 3개월 +2.32%",
                       "SOX 현재 추세(규칙): <b>혼재", "20일선 아래·60일선 아래",
                       "-11.60%", "나스닥100 추세 확인 대기", "제공처 종가 불일치: 2026-10-06",
                       "기간 수익률과 현재 추세는 별개"):
            self.assertIn(phrase, message)
        self.assertNotIn("미국 증시 상승 추세", message)

    def test_brief_keeps_holdings_level_and_all_three_long_short_components(self):
        message = self.render()
        for phrase in ("현재 <b>순숏 19,212계약</b>", "통합과 별도 집계", "순숏 26,738계약",
                       "1주 전 대비: <b>순숏 5,511계약 축소</b>", "롱 3,199 증가 / 숏 2,312 감소",
                       "1개월 비교: <b>순숏 5,120계약 확대</b>", "롱 4,012 감소 / 숏 1,108 증가",
                       "3개월 비교: <b>순숏 49,405계약 축소</b>", "롱 14,553 증가 / 숏 34,852 감소",
                       "가격보다 8일 이전", "주문·청산 목적 미확인"):
            self.assertIn(phrase, message)
        self.assertNotIn("숏 청산 확인", message)
        self.assertNotRegex(message, r"순 [+-]\d")

    def test_brief_retains_relative_breadth_and_options_distribution_limits(self):
        message = self.render()
        for phrase in ("5일 +1.69%p / 1개월 -2.38%p / 3개월 -2.88%p",
                       "Yahoo 조정종가의 ETF 상대수익률", "상승 종목 비율·시장 전체 방향은 미확인",
                       "주식 0.61 / 지수 1.01 / 전체 0.88", "중앙값 0.565 / 현재값 이하 77.3%",
                       "중앙값 0.590 / 현재값 이하 61.5%", "현재일 제외·동률 포함", "매수·매도 방향과 가격 반등을 확인한 값은 아님"):
            self.assertIn(phrase, message)
        self.assertNotIn("콜 매수 우위", message)

    def test_missing_weekly_observation_is_not_labelled_as_exactly_one_week(self):
        values,context=self.sources()
        values["CFTC|cot"]["history_3y"]["week_window"]["base_date"]="2026-09-22"
        message=self.render(values,context)
        self.assertIn("직전 관측 대비(2026-09-22)",message)
        self.assertNotIn("1주 전 대비",message)

    def test_missing_or_tampered_lanes_stay_unverified_without_borrowing_another_scope(self):
        values, context = self.sources()
        context["indices"]["NDX"]["returns"]["windows"]["5d"]["return_pct"] += 1
        context["options"]["1m"]["values"]["equity"]["median_pc"] = 0
        context["breadth"]["comparison"]["windows"]["5d"]["difference_pp"] += 1
        values["CFTC|cot"]["history_3y"]["week_window"]["actors"]["leveraged_funds"]["net_change"] += 1
        message = self.render(values, context)
        self.assertIn("주요지수 종합 확인 대기", message)
        self.assertIn("1일 확인 대기 / 3일 확인 대기 / 5일 확인 대기", message)
        self.assertIn("주식 P/C 과거 1개월: 확인 대기", message)
        self.assertIn("RSP−SPY 상대수익률: 확인 대기", message)
        self.assertIn("1주 롱·숏 변화: 확인 대기", message)
        self.assertNotIn("순숏 19,212", message)

    def test_brief_is_pure_escapes_labels_and_rejects_over_budget_without_truncating(self):
        values, context = self.sources()
        original_values, original_context = copy.deepcopy(values), copy.deepcopy(context)
        message = self.render(values, context, event_label="<script>")
        self.assertIn("&lt;script&gt;", message)
        self.assertNotIn("<script>", message)
        self.assertEqual(values, original_values)
        self.assertEqual(context, original_context)
        with self.assertRaises(ValueError):
            self.render(values, context, event_label="x" * view.BRIEF_MAX_CHARS)


class AutoDirectionTests(unittest.TestCase):
    def sources(self, slope=None, end="2026-10-14"):
        values, context = BriefTests().sources()
        if slope is not None:
            days=sessions("2026-04-01",end)
            rows=[(d, 1000+slope*i) for i,d in enumerate(days)]
            path=price_path(end,rows,rows,"SOX")
            sm=values["Nasdaq SOX|sox"]["metrics"]
            sm.update(value=rows[-1][1],previous_close=rows[-2][1],price_path=path,expected_completed_session=end,
                      month_windows=horizons.price_month_windows(end,rows[-1][1],rows,rows),
                      **{f"d{n}_pct":path["values"][f"d{n}_pct"] for n in (1,3,5)})
            values["Nasdaq SOX|sox"]["period"]=end
            for symbol in ("NDX","SPX"):
                context["indices"][symbol]=price_path(end,rows,rows,symbol)
                context["indices"][symbol]["returns"]=price_returns(end,rows,rows,symbol)
        return values,context

    def render_directions(self, values, context):
        return "\n".join(view.direction_lines(values["CFTC|cot"],values["Nasdaq SOX|sox"],context))

    def test_actual_input_reads_each_period_and_price_ma_disagreement(self):
        values,context=self.sources();out=self.render_directions(values,context)
        for phrase in ("5일 모두 하락", "1개월 모두 상승", "3개월 혼재(SOX 하락·나스닥100 상승·S&P500 상승)",
                       "종가 20일선 아래·60일선 아래 / 평균선 20일 상승·60일 상승",
                       "선물 방향(2026-10-06·통합)","기관 순롱 확대·헤지펀드성 순숏 축소", "가격보다 8일 이전"):
            self.assertIn(phrase,out)

    def test_new_verified_operands_reverse_all_price_and_ma_directions(self):
        for slope,word,location in ((1,"상승","위"),(-1,"하락","아래"),(0,"보합","같음")):
            values,context=self.sources(slope)
            out=self.render_directions(values,context)
            for period in ("5일","1개월","3개월"):
                self.assertIn(period+" 모두 "+word,out)
            self.assertIn(f"종가 20일선 {location}·60일선 {location}",out)
            self.assertIn(f"평균선 20일 {word}·60일 {word}",out)
            self.assertNotIn("혼재",out)

    def test_new_source_dates_and_weekly_turnaround_are_not_fixed(self):
        values,context=self.sources(1,"2026-10-15")
        cot=values["CFTC|cot"];cot["period"]="October 13, 2026"
        cm=cot["metrics"];cm["previous_period"]="October 6, 2026"
        cm.update(asset_long=80,asset_short=20,asset_net=60,asset_long_wow=-10,asset_short_wow=5,asset_net_wow=-15,
                  lev_long=20,lev_short=80,lev_net=-60,lev_long_wow=-10,lev_short_wow=5,lev_net_wow=-15)
        out=self.render_directions(values,context)
        self.assertIn("선물 방향(2026-10-13·통합)",out)
        self.assertIn("기관 순롱 축소·헤지펀드성 순숏 확대",out)
        self.assertIn("가격보다 2일 이전",out)
        self.assertNotIn("8일 이전",out)
        for report,phrase in (("2026-10-15","가격과 같은 기준일의 주간 자료"),("2026-10-16","가격보다 1일 이후")):
            cot["period"]=report
            self.assertIn(phrase,self.render_directions(values,context))

    def test_same_sox_collector_series_drives_display_and_direction_without_ma_history(self):
        values,context=self.sources(1)
        sm=values["Nasdaq SOX|sox"]["metrics"]
        sm["d5_pct"]=-0.04997501249375147
        out=self.render_directions(values,context)
        self.assertIn("5일 혼재(SOX 하락·나스닥100 상승·S&P500 상승)",out)
        sm["price_path"]={"status":"unavailable"}
        self.assertIn("5일 혼재(SOX 하락·나스닥100 상승·S&P500 상승)",self.render_directions(values,context))
        self.assertIn("SOX 현재 상태</b>: 확인 대기",self.render_directions(values,context))

    def test_entire_flat_body_and_detail_agree_with_the_new_readout(self):
        values,context=self.sources(0)
        body=BriefTests().render(values,context)
        detail=view.render_detail_alert(values["CFTC|cot"],values["Cboe|options"],values["Nasdaq SOX|sox"],[],list(values.values()),context=context)
        self.assertIn("5일 모두 보합",body)
        self.assertIn("나스닥100·S&P500 최근 5거래일 보합",body)
        self.assertIn("미국 주요지수 최근 5거래일 보합",detail)
        self.assertNotIn("5거래일 방향 혼재",body+detail)

    def test_missing_or_tampered_price_does_not_promote_partial_population(self):
        values,context=self.sources()
        context["indices"]["NDX"]["returns"]["windows"]["5d"]["return_pct"]+=1
        out=self.render_directions(values,context)
        self.assertIn("5일 확인 대기(나스닥100)",out)
        self.assertNotIn("5일 모두 하락",out)
        sm=values["Nasdaq SOX|sox"]["metrics"]
        sm["price_path"]["values"]["ma20"]+=1
        sm["month_windows"]["1m"]["return_pct"]+=1
        out=self.render_directions(values,context)
        self.assertIn("SOX 현재 상태</b>: 확인 대기",out)
        self.assertIn("1개월 확인 대기(SOX·나스닥100)",out)

    def test_unconfirmed_or_wrong_date_sox_does_not_reuse_saved_direction(self):
        values,context=self.sources()
        values["Nasdaq SOX|sox"]["metrics"]["final_close_confirmed"]=False
        out=self.render_directions(values,context)
        self.assertIn("5일 확인 대기(SOX)",out)
        self.assertIn("1개월 확인 대기(SOX)",out)
        self.assertIn("SOX 현재 상태</b>: 확인 대기",out)
        values["Nasdaq SOX|sox"]["metrics"]["final_close_confirmed"]=True
        values["Nasdaq SOX|sox"]["metrics"]["expected_completed_session"]="2026-10-15"
        self.assertIn("5일 확인 대기(SOX)",self.render_directions(values,context))

    def test_inconsistent_integrated_position_arithmetic_stays_pending(self):
        values,context=self.sources();cm=values["CFTC|cot"]["metrics"]
        cm["asset_net"]+=1;cm["lev_net_wow"]+=1
        out=self.render_directions(values,context)
        self.assertIn("기관 확인 대기·헤지펀드성 확인 대기",out)
        cm["asset_net"]-=1;cm["lev_net_wow"]-=1;cm["previous_period"]="2026-10-07"
        self.assertIn("기관 확인 대기·헤지펀드성 확인 대기",self.render_directions(values,context))

    def test_negative_to_positive_and_zero_positions_use_actual_changes(self):
        for net,change,word in ((10,20,"순숏 → 순롱 전환"),(-10,-20,"순롱 → 순숏 전환"),(0,0,"주간 변화 없음")):
            cm=dict(lev_long=max(net,0)+100,lev_short=max(-net,0)+100,lev_net=net,
                    lev_long_wow=change,lev_short_wow=0,lev_net_wow=change)
            self.assertEqual(view._checked_integrated_change(cm,"lev"),word)

    def test_readout_does_not_mutate_input_or_carry_a_previous_narrative(self):
        values,context=self.sources();prior=copy.deepcopy((values,context))
        self.render_directions(values,context)
        self.assertEqual((values,context),prior)
        empty="\n".join(view.direction_lines({}, {}, {}))
        self.assertIn("확인 대기",empty)
        self.assertNotIn("모두 하락",empty)
        self.assertNotIn("순숏 축소",empty)


class ContextDedupeTests(unittest.TestCase):
    def saved(self):
        return json.loads(gzip.decompress((ROOT/"tests/fixtures/us_positioning_context_dedupe_20261015.json.gz").read_bytes()))

    def run_tail(self, context, prior=None):
        return original.OperatingIntegrationTests.run_operating_tail(self, original.snapshot(), prior, context)

    def test_actual_two_runs_reproduce_raw_change_but_no_changed_observation(self):
        saved = self.saved()
        before, after = saved["before"], saved["after"]
        self.assertNotEqual(before["fingerprint"], after["fingerprint"])
        self.assertNotEqual(before["metrics"], after["metrics"])
        self.assertEqual(before["metrics"]["breadth"]["comparison"], after["metrics"]["breadth"]["comparison"])
        self.assertEqual(context_change_key(before["metrics"], before["period"]),
                         context_change_key(after["metrics"], after["period"]))
        first = self.run_tail(before["metrics"])
        second = self.run_tail(after["metrics"], first["pending"])
        self.assertTrue(second["gate"])
        self.assertEqual(second["updates"], 0)
        self.assertIsNone(second["alert"])
        self.assertIsNone(second["detail"])
        self.assertIsNone(second["pending"])
        self.assertIn("context_history_only_change: True", second["status"])
        self.assertEqual(second["sources"][-1]["metrics"], after["metrics"])

    def test_a_used_adjusted_endpoint_change_remains_an_update_without_rounding(self):
        before = self.saved()["before"]
        after = copy.deepcopy(before["metrics"])
        end = before["period"]
        row = next(r for r in after["breadth"]["series"]["RSP"]["adjusted_operands"] if r[0] == end)
        row[1] += 0.00001
        after["breadth"]["comparison"] = breadth_comparison(after["breadth"]["series"], end)
        self.assertNotEqual(context_change_key(before["metrics"], end), context_change_key(after, end))
        first = self.run_tail(before["metrics"])
        second = self.run_tail(after, first["pending"])
        self.assertEqual(second["updates"], 1)
        self.assertIsNotNone(second["alert"])
        self.assertEqual(second["pending"]["values"]["미국 주요지수·시장 확산·옵션 과거 비교|context"]["metrics"], after)

    def test_unverified_comparison_or_changed_raw_close_history_is_not_ignored(self):
        before = self.saved()["before"]
        for mutation in ("bad-comparison", "raw-close", "missing-endpoint"):
            after = copy.deepcopy(before["metrics"])
            if mutation == "bad-comparison":
                after["breadth"]["comparison"]["windows"]["5d"]["difference_pp"] += 1
            elif mutation == "raw-close":
                after["breadth"]["series"]["RSP"]["operands"][3][1] += .001
            else:
                end = before["period"]
                after["breadth"]["series"]["RSP"]["adjusted_operands"] = [r for r in after["breadth"]["series"]["RSP"]["adjusted_operands"] if r[0] != end]
            with self.subTest(mutation=mutation):
                self.assertNotEqual(context_change_key(before["metrics"], before["period"]), context_change_key(after, before["period"]))

    def test_unacknowledged_context_cannot_be_suppressed_as_a_sent_observation(self):
        saved = self.saved()
        first = self.run_tail(saved["before"]["metrics"])
        prior = first["pending"]
        prior["seen"].pop("미국 주요지수·시장 확산·옵션 과거 비교|context")
        second = self.run_tail(saved["after"]["metrics"], prior)
        self.assertEqual(second["updates"], 1)
        self.assertIsNotNone(second["alert"])

    def test_date_status_and_other_context_fields_remain_exact(self):
        saved = self.saved()["before"]
        for path in (("indices", "NDX", "reason"), ("options", "1m", "status")):
            after = copy.deepcopy(saved["metrics"])
            parent = after
            for key in path[:-1]:
                parent = parent[key]
            parent[path[-1]] = "changed"
            self.assertNotEqual(context_change_key(saved["metrics"], saved["period"]), context_change_key(after, saved["period"]))
        self.assertNotEqual(context_change_key(saved["metrics"], saved["period"]), context_change_key(saved["metrics"], "2026-10-15"))

    def test_comparison_key_never_mutates_or_discards_the_preserved_original(self):
        saved = self.saved()["before"]
        original_metrics = copy.deepcopy(saved["metrics"])
        key = context_change_key(saved["metrics"], saved["period"])
        self.assertEqual(saved["metrics"], original_metrics)
        used = {w[k] for w in key["breadth"]["comparison"]["windows"].values() for k in ("base_date", "end_date")}
        for symbol in ("RSP", "SPY"):
            self.assertEqual({r[0] for r in key["breadth"]["series"][symbol]["adjusted_operands"]}, used)
            self.assertGreater(len(original_metrics["breadth"]["series"][symbol]["adjusted_operands"]), len(used))


class SourceParserBoundaryTests(unittest.TestCase):

    def test_yahoo_and_nasdaq_wrong_symbol_or_misaligned_arrays_fail(self):
        with self.assertRaises(ValueError):parse_yahoo({"chart":{"result":[{"meta":{"symbol":"SPY"}}]}},"RSP","2026-10-14")
        with self.assertRaises(ValueError):parse_nasdaq({"data":{"symbol":"SPY"}},"RSP","2026-10-14")

if __name__=="__main__":unittest.main()

