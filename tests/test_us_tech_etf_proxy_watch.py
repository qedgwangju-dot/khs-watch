"""Offline tests for the public tech ETF creations/redemptions proxy."""
import datetime as dt
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from zoneinfo import ZoneInfo

import us_tech_etf_proxy_watch as w


def snap(date="2026-10-21",iyw_shares=100_000_000,soxx_shares=80_000_000):
    return {
        "IYW":{"date":date,"nav_date":date,"shares_date":date,"nav":252.5,"shares":iyw_shares},
        "SOXX":{"date":date,"nav_date":date,"shares_date":date,"nav":495.0,"shares":soxx_shares},
    }


def prior_state(date="2026-10-20"):
    return {"history":{
        "IYW":[{"date":date,"nav":253.0,"shares":98_000_000}],
        "SOXX":[{"date":date,"nav":490.0,"shares":80_000_000}],
    },"last_alert":None}


class TechEtfProxyTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.state=Path(self.tmp.name)/"proxy.json"
        self.candidate=patch.object(w,"CANDIDATE",Path(self.tmp.name)/"message.html")
        self.receipt=patch.object(w,"RECEIPT",Path(self.tmp.name)/"receipt.json")
        self.candidate.start();self.receipt.start()
        self.addCleanup(self.candidate.stop);self.addCleanup(self.receipt.stop)

    def test_baseline_wont_call_it_retail_or_send(self):
        with patch.object(w,"send_exact") as send:
            x=w.run(state_path=self.state,getter=lambda now:snap())
        self.assertEqual(x["status"],"baseline_or_no_signal")
        send.assert_not_called()
        self.assertTrue(self.state.exists())

    def test_strong_creations_trigger_official_proxy_only(self):
        x=w.calculate(snap(),prior_state())
        self.assertIn("IYW 발행좌수 당일 +1% 이상",x["signals"])
        message=w.render(x,1350,"2026-10-21")
        self.assertIn("추정 설정",message)
        self.assertIn("개인투자자만의 매매",message)
        self.assertIn("IYW 공식",message)
        self.assertIn("SOXX 공식",message)
        self.assertIn("억원",message)

    def test_five_consecutive_observations_detects_real_issuance_trend(self):
        dates=("2026-10-14","2026-10-15","2026-10-16","2026-10-19","2026-10-20")
        old=prior_state()
        old["history"]["IYW"]=[
            {"date":day,"nav":250.0,"shares":95_000_000+i*500_000}
            for i,day in enumerate(dates)
        ]
        old["history"]["SOXX"]=[
            {"date":day,"nav":490.0,"shares":80_000_000}
            for day in dates
        ]
        result=w.calculate(snap("2026-10-21",iyw_shares=100_000_000),old)
        self.assertIn("IYW 최근 5회 발행좌수 +2.5% 이상",result["signals"])
        self.assertEqual(result["movements"]["IYW"]["five_observations_from"],"2026-10-14")
        self.assertAlmostEqual(result["movements"]["IYW"]["five_observations_share_change_pct"],100*5/95)
        body=w.render(result,1350,"2026-10-21")
        self.assertIn("최근 5개 관측 간격",body)
        self.assertIn("억원",body)

    def test_missing_weekday_blocks_five_session_extrapolation(self):
        dates=("2026-10-13","2026-10-14","2026-10-15","2026-10-16","2026-10-20")
        old=prior_state()
        old["history"]["IYW"]=[
            {"date":day,"nav":250.0,"shares":95_000_000+i*500_000}
            for i,day in enumerate(dates)
        ]
        old["history"]["SOXX"]=[
            {"date":day,"nav":490.0,"shares":80_000_000}
            for day in dates
        ]
        result=w.calculate(snap("2026-10-21"),old)
        self.assertIsNone(result["movements"]["IYW"]["five_observations_creation_usd"])
        self.assertNotIn("IYW 최근 5회 발행좌수 +2.5% 이상",result["signals"])

    def test_different_nav_and_share_dates_fail_closed(self):
        def bad(t,meta,retry_budget=None):
            x=snap()[t]
            if t=="SOXX":x["shares_date"]="2026-10-20"
            return x
        with self.assertRaisesRegex(ValueError,"different source dates"):
            w.collect(now=dt.datetime(2026,10,22,8,0,tzinfo=dt.timezone.utc),fetcher=bad)

    def test_mismatch_between_funds_fail_closed(self):
        def bad(t,meta,retry_budget=None):
            return snap("2026-10-21" if t=="IYW" else "2026-10-20")[t]
        with self.assertRaisesRegex(ValueError,"not aligned"):
            w.collect(now=dt.datetime(2026,10,22,8,0,tzinfo=dt.timezone.utc),fetcher=bad)

    def test_future_and_old_market_dates_are_not_reported(self):
        def fake(t,meta,retry_budget=None):
            return snap("2026-10-22")[t]
        with self.assertRaisesRegex(ValueError,"unavailable/stale"):
            w.collect(now=dt.datetime(2026,10,22,8,0,tzinfo=dt.timezone.utc),fetcher=fake)

    def test_split_guard_never_raises_false_issuance(self):
        state=prior_state("2026-11-04")
        value=snap("2026-11-05",iyw_shares=98_000_000,soxx_shares=160_000_000)
        state["history"]["SOXX"][-1]["shares"]=80_000_000
        x=w.calculate(value,state)
        self.assertIsNone(x["movements"]["SOXX"]["shares_delta"])
        self.assertTrue(x["movements"]["SOXX"]["split_guard"])
        self.assertNotIn("SOXX 발행좌수 당일 +1% 이상",x["signals"])

    def test_big_unannounced_share_jump_suppresses_signal(self):
        state=prior_state()
        x=w.calculate(snap(soxx_shares=190_000_000),state)
        self.assertIsNone(x["movements"]["SOXX"]["shares_delta"])

    def test_test_mode_never_sends_or_saves(self):
        w.save_state(prior_state(),self.state)
        old=self.state.read_text()
        with patch.object(w,"send_exact") as send,patch.object(w.ishares,"get_usdkrw",return_value={"rate":1350,"date":"2026-10-21"}):
            res=w.run(validate_only=True,state_path=self.state,getter=lambda now:snap())
        self.assertEqual(res["status"],"validated")
        self.assertTrue(res["signals"])
        self.assertEqual(old,self.state.read_text())
        send.assert_not_called()

    def test_success_receipt_and_duplicate_protection(self):
        w.save_state(prior_state(),self.state)
        with patch.object(w,"send_exact",return_value=500) as send,patch.object(w.ishares,"get_usdkrw",return_value={"rate":1350,"date":"2026-10-21"}):
            first=w.run(state_path=self.state,getter=lambda now:snap())
            same=w.run(state_path=self.state,getter=lambda now:snap())
        self.assertEqual(first["status"],"sent")
        self.assertEqual(first["message_id"],500)
        self.assertEqual(same["status"],"duplicate_suppressed")
        self.assertTrue(w.RECEIPT.exists())
        send.assert_called_once()

    def test_send_error_never_commits_state(self):
        w.save_state(prior_state(),self.state)
        old=self.state.read_text()
        with patch.object(w,"send_exact",side_effect=RuntimeError("Telegram rejected")),patch.object(w.ishares,"get_usdkrw",return_value={"rate":1350,"date":"2026-10-21"}):
            with self.assertRaisesRegex(RuntimeError,"Telegram rejected"):
                w.run(state_path=self.state,getter=lambda now:snap())
        self.assertEqual(self.state.read_text(),old)

    def test_fx_error_withholds_without_advancing(self):
        w.save_state(prior_state(),self.state)
        old=self.state.read_text()
        with patch.object(w.ishares,"get_usdkrw",side_effect=RuntimeError("fx offline")),patch.object(w,"send_exact") as send:
            result=w.run(state_path=self.state,getter=lambda now:snap())
        self.assertEqual(result["status"],"fx_withheld")
        self.assertEqual(self.state.read_text(),old)
        send.assert_not_called()

    def test_invalid_state_not_silently_reset(self):
        self.state.write_text('{"no-history":true}')
        with self.assertRaisesRegex(RuntimeError,"malformed"):
            w.load_state(self.state)

if __name__=="__main__":
    unittest.main()
