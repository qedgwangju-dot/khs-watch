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
    return dict(turnover=turnover,fx=parse_ecos_usdkrw(f["fx_responses"]["2026-10-14"],"2026-10-14"),
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

class AmountRenderingTests(unittest.TestCase):
    def sources(self):
        values,context=context_tests.BriefTests().sources();context["amounts"]=observed()
        return values,context

    def render(self,values,context,detail=False):
        fn=view.render_detail_document if detail else view.render_alert
        return fn(values["CFTC|cot"],values["Cboe|options"],values["Nasdaq SOX|sox"],list(values.values()),list(values.values()),context=context)

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
        detail=self.render(values,context,True)
        self.assertIn("만기별 실제 선물 정산가 평가액",detail)

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
