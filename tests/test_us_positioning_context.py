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
    checked_options,breadth_comparison,parse_yahoo,parse_nasdaq,
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

    def test_expanded_message_keeps_price_trend_return_population_and_intent_separate(self):
        f=fixture();values=horizons.enriched_snapshot()
        values["CFTC|cot"]["history_3y"]["week_window"]=f["week"]
        values["Nasdaq SOX|sox"]["metrics"]["price_path"]=f["sox_path"]
        out=view.render_alert(values["CFTC|cot"],values["Cboe|options"],values["Nasdaq SOX|sox"],list(values.values()),list(values.values()),context=f["context"])
        for phrase in ["미국 주요지수 최근 5거래일 하락","1개월 전 대비","SOX 현재 추세(규칙): <b>혼재","20일선 아래·60일선 아래","-11.60%","+3,199 / 숏 -2,312 / 순 +5,511","신규 주문·청산·헤지 목적은 미확인","0.565","77.3%","매수·매도는 구분되지 않아"]:
            self.assertIn(phrase,out)
        self.assertNotIn("콜 매수 우위",out)
        self.assertTrue(all(len(line)<=3800 for line in out.splitlines()))
        # The unchanged production sender splits on complete lines, preserving tags.
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

    def test_yahoo_and_nasdaq_wrong_symbol_or_misaligned_arrays_fail(self):
        with self.assertRaises(ValueError):parse_yahoo({"chart":{"result":[{"meta":{"symbol":"SPY"}}]}},"RSP","2026-10-14")
        with self.assertRaises(ValueError):parse_nasdaq({"data":{"symbol":"SPY"}},"RSP","2026-10-14")

if __name__=="__main__":unittest.main()

