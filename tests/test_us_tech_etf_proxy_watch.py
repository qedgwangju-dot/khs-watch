"""Offline tests for the public tech ETF creations/redemptions proxy."""
import datetime as dt
import io
import os
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
        self.assertIn("JP모건 개인 순매수 불균형",message)
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

    def test_ewy_data_includes_us_listed_korea_etf_and_bilingual_economic_scope(self):
        def fetch(ticker, meta, retry_budget=None):
            if ticker == "EWY":
                return {
                    "date":"2026-10-21","nav_date":"2026-10-21",
                    "shares_date":"2026-10-21","nav":190.0,"shares":100_000_000,
                }
            return snap()[ticker]
        data=w.collect(now=dt.datetime(2026,10,22,8,0,tzinfo=dt.timezone.utc),fetcher=fetch)
        self.assertEqual(set(data),{"IYW","SOXX","EWY"})
        self.assertEqual(data["EWY"]["date"],"2026-10-21")
        result=w.calculate(data,prior_state())
        self.assertIsNone(result["movements"]["EWY"]["shares_delta"])
        message=w.render(result,1350,"2026-10-21")
        self.assertIn("EWY 공식",message)
        self.assertIn("한국거래소 외국인 현물",message)

    def test_ewy_missing_does_not_block_existing_tech_signals_or_erase_history(self):
        def fetch(ticker, meta, retry_budget=None):
            if ticker == "EWY":
                raise TimeoutError("EWY delayed publication")
            return snap()[ticker]
        data=w.collect(now=dt.datetime(2026,10,22,8,0,tzinfo=dt.timezone.utc),fetcher=fetch)
        self.assertEqual(set(data),{"IYW","SOXX"})
        old=prior_state()
        old["history"]["EWY"]=[{"date":"2026-10-20","nav":190.0,"shares":10_000_000}]
        result=w.calculate(data,old)
        self.assertIn("IYW 발행좌수 당일 +1% 이상",result["signals"])
        self.assertEqual(result["new_history"]["EWY"],old["history"]["EWY"])
        self.assertIn("판정 보류",w.render(result,1350,"2026-10-21"))

    def test_three_confirmed_ewy_creations_fire_only_with_all_sessions(self):
        x=snap()
        x["EWY"]={
            "date":"2026-10-21","nav_date":"2026-10-21",
            "shares_date":"2026-10-21","nav":190.0,"shares":101_500_000,
        }
        state=prior_state()
        state["history"]["EWY"]=[
            {"date":"2026-10-16","nav":185.0,"shares":100_000_000},
            {"date":"2026-10-19","nav":187.0,"shares":100_500_000},
            {"date":"2026-10-20","nav":188.0,"shares":101_000_000},
        ]
        result=w.calculate(x,state)
        self.assertIn("EWY 발행좌수 3거래일 연속 증가", " ".join(result["signals"]))
        self.assertEqual(result["movements"]["EWY"]["prev_date"],"2026-10-20")

        stale=prior_state()
        stale["history"]["EWY"]=[
            {"date":"2026-10-15","nav":185.0,"shares":100_000_000},
            {"date":"2026-10-19","nav":187.0,"shares":100_500_000},
            {"date":"2026-10-20","nav":188.0,"shares":101_000_000},
        ]
        result2=w.calculate(x,stale)
        self.assertNotIn("EWY 발행좌수 3거래일 연속 증가", " ".join(result2["signals"]))

    def test_ewy_source_date_mismatch_isolation(self):
        def fetch(ticker, meta, retry_budget=None):
            if ticker == "EWY":
                return {
                    "date":"2026-10-20","nav_date":"2026-10-20",
                    "shares_date":"2026-10-20","nav":190.0,"shares":100_000_000,
                }
            return snap()[ticker]
        data=w.collect(now=dt.datetime(2026,10,22,8,0,tzinfo=dt.timezone.utc),fetcher=fetch)
        self.assertEqual(set(data),{"IYW","SOXX"})

    def test_invalid_state_not_silently_reset(self):
        self.state.write_text('{"no-history":true}')
        with self.assertRaisesRegex(RuntimeError,"malformed"):
            w.load_state(self.state)

    def test_old_composite_receipt_upgrades_to_per_signal_keys(self):
        prior=prior_state()
        prior["last_alert"]={"alert_key":"2026-10-21|IYW 발행좌수 당일 +1% 이상|SOXX 발행좌수 당일 -1% 이하",
                             "message_id":1284}
        keys=w.previously_sent_signal_keys(prior)
        self.assertIn("2026-10-21|IYW 발행좌수 당일 +1% 이상",keys)
        self.assertIn("2026-10-21|SOXX 발행좌수 당일 -1% 이하",keys)

    def test_duplicate_does_not_need_second_fx_or_second_send(self):
        prior=prior_state()
        prior["last_alert"]={"alert_key":"2026-10-21|IYW 발행좌수 당일 +1% 이상","message_id":1284}
        w.save_state(prior,self.state)
        with patch.object(w.ishares,"get_usdkrw",side_effect=RuntimeError("fx offline")) as fx, patch.object(w,"send_exact") as send:
            result=w.run(state_path=self.state,getter=lambda now:snap())
        self.assertEqual(result["status"],"duplicate_suppressed")
        fx.assert_not_called()
        send.assert_not_called()

    def test_converted_per_signal_state_blocks_repeat_of_older_signal(self):
        prior=prior_state()
        prior["sent_signal_keys"]=["2026-10-21|IYW 발행좌수 당일 +1% 이상"]
        w.save_state(prior,self.state)
        with patch.object(w,"send_exact") as send:
            result=w.run(state_path=self.state,getter=lambda now:snap())
        self.assertEqual(result["status"],"duplicate_suppressed")
        send.assert_not_called()



    def test_telegram_response_wrong_chat_id_rejected(self):
        identity={"ok":True,"result":{"username":w.EXPECTED_BOT}}
        wrong={"ok":True,"result":{"message_id":1284,"chat":{"id":-1009999}}}
        responses=[io.BytesIO(json.dumps(x).encode()) for x in (identity,wrong)]
        env={"TELEGRAM_BOT_TOKEN":"test-token-not-secret",
             "TELEGRAM_CHAT_ID":"-1001234",
             "EXPECTED_TELEGRAM_BOT_USERNAME":w.EXPECTED_BOT}
        with patch.dict(os.environ,env), patch.object(
            w.urllib.request,"urlopen",side_effect=responses):
            with self.assertRaisesRegex(RuntimeError,"unexpected chat"):
                w.send_exact("testing recipient verification")

    def test_telegram_response_correct_chat_id_is_acknowledged(self):
        identity={"ok":True,"result":{"username":w.EXPECTED_BOT}}
        correct={"ok":True,"result":{"message_id":1284,"chat":{"id":-1001234}}}
        responses=[io.BytesIO(json.dumps(x).encode()) for x in (identity,correct)]
        env={"TELEGRAM_BOT_TOKEN":"test-token-not-secret",
             "TELEGRAM_CHAT_ID":"-1001234",
             "EXPECTED_TELEGRAM_BOT_USERNAME":w.EXPECTED_BOT}
        with patch.dict(os.environ,env), patch.object(
            w.urllib.request,"urlopen",side_effect=responses):
            self.assertEqual(w.send_exact("testing recipient verification"),1284)


    def test_old_ishares_snapshot_after_us_close_is_publication_pending(self):
        now = dt.datetime(2026, 10, 27, 23, 10, tzinfo=dt.timezone.utc)
        def fetch(ticker, meta, retry_budget=None):
            return snap("2026-10-26")[ticker]
        with self.assertRaisesRegex(w.OfficialPublicationPending,"2026-10-27"):
            w.collect(now=now,fetcher=fetch)

    def test_missing_two_us_business_sessions_is_source_withheld(self):
        now = dt.datetime(2026, 10, 28, 23, 10, tzinfo=dt.timezone.utc)
        def fetch(ticker, meta, retry_budget=None):
            return snap("2026-10-26")[ticker]
        with self.assertRaisesRegex(ValueError,"unavailable/stale"):
            w.collect(now=now,fetcher=fetch)

    def test_publication_pending_does_not_reuse_saved_values_or_send(self):
        original = prior_state("2026-10-23")
        w.save_state(original,self.state)
        before = self.state.read_text()
        def unavailable(_):
            raise w.OfficialPublicationPending("2026-10-27 source not yet published")
        with patch.object(w,"send_exact") as send, patch.object(w.ishares,"get_usdkrw") as fx:
            result=w.run(state_path=self.state,getter=unavailable)
        self.assertEqual(result["status"],"publication_pending")
        self.assertFalse(result["telegram_sent"])
        self.assertIn("2026-10-27",result["reason"])
        send.assert_not_called()
        fx.assert_not_called()
        self.assertEqual(before,self.state.read_text())

    def test_missing_weekday_within_four_calendar_days_blocks_daily_signal(self):
        prior=prior_state("2026-10-22")
        x=w.calculate(snap("2026-10-26",iyw_shares=101_000_000),prior)
        self.assertIsNone(x["movements"]["IYW"]["shares_delta"])
        self.assertNotIn("IYW 발행좌수 당일 +1% 이상",x["signals"])

    def test_friday_to_monday_is_one_valid_comparison_session(self):
        prior=prior_state("2026-10-23")
        prior["history"]["SOXX"][-1]["shares"]=90_350_000
        sample=snap("2026-10-26",soxx_shares=94_200_000)
        sample["SOXX"]["nav"]=492.25
        x=w.calculate(sample,prior)
        self.assertAlmostEqual(x["movements"]["SOXX"]["outstanding_shares_change_pct"],4.2612064195)
        self.assertEqual(x["movements"]["SOXX"]["estimated_creation_value_usd"],1_895_162_500)
        self.assertIn("SOXX 발행좌수 당일 +1% 이상",x["signals"])


    def test_issuer_net_assets_reconciles_with_official_soxx_oct26(self):
        payload=snap("2026-10-26",iyw_shares=98_000_000,soxx_shares=94_200_000)
        payload["SOXX"]["nav"]=492.25
        payload["SOXX"]["net_assets"]=46_369_679_654
        payload["IYW"]["net_assets"]=payload["IYW"]["nav"]*payload["IYW"]["shares"]
        def fetch(t,meta,retry_budget=None):
            return payload[t]
        now=dt.datetime(2026,10,27,14,0,tzinfo=dt.timezone.utc)
        fresh=w.collect(now=now,fetcher=fetch)
        self.assertLess(fresh["SOXX"]["asset_check_pct"],0.001)
        state=prior_state("2026-10-23")
        state["history"]["SOXX"][-1]["shares"]=90_350_000
        result=w.calculate(fresh,state)
        body=w.render(result,1327.75,"2026-10-27 ECB")
        for snippet in ("90,350,000", "94,200,000", "+3,850,000", "$492.25",
                        "순자산과 발행좌수", "+1,895.2백만달러"):
            self.assertIn(snippet,body)

    def test_inconsistent_issuer_assets_block_inflated_setting(self):
        payload=snap("2026-10-26",iyw_shares=98_000_000,soxx_shares=94_200_000)
        payload["SOXX"]["nav"]=492.25
        payload["SOXX"]["net_assets"]=40_000_000_000
        def fetch(t,meta,retry_budget=None):
            return payload[t]
        now=dt.datetime(2026,10,27,14,0,tzinfo=dt.timezone.utc)
        with self.assertRaisesRegex(ValueError,"net assets differ"):
            w.collect(now=now,fetcher=fetch)



    def _fixture_market_history(self, to_date="2026-11-02", n=75):
        import exchange_calendars
        cal=exchange_calendars.get_calendar("XNYS")
        days=[t.date().isoformat() for t in
              cal.sessions_in_range("2026-06-15",to_date)][-n:]
        def records(nav,initial,step):
            return [{"date":day,"nav":nav,"shares":initial+i*step}
                    for i,day in enumerate(days)]
        return {"IYW":records(100.0,100_000_000,10_000),
                "SOXX":records(400.0,80_000_000,5_000),
                "EWY":records(150.0,140_000_000,0)}

    def test_21_and_63_session_sums_use_each_days_nav(self):
        records=self._fixture_market_history()
        date=records["IYW"][-1]["date"]
        state={"history":{key:rows[:-1] for key,rows in records.items()}}
        current={key:{"date":date,"nav":rows[-1]["nav"],"shares":rows[-1]["shares"]}
                 for key,rows in records.items()}
        result=w.calculate(current,state)
        iyw=result["movements"]["IYW"]["rolling"]
        self.assertEqual(iyw[21]["sessions"],21)
        self.assertAlmostEqual(iyw[21]["net_usd"],21*10_000*100.0)
        self.assertAlmostEqual(iyw[63]["net_usd"],63*10_000*100.0)
        self.assertAlmostEqual(result["movements"]["EWY"]["rolling"][21]["net_usd"],0)
        self.assertEqual(result["movements"]["IYW"]["history_points"],75)
        formatted=w.render(result,1342.9,"2026-11-02 ECB")
        self.assertIn("IYW 1개월(21거래일)",formatted)
        self.assertIn("IYW 3개월(63거래일)",formatted)
        self.assertIn("중기 방향: 장·단기 설정 우위 지속",formatted)
        self.assertIn("SOXX 3개월(63거래일)",formatted)
        self.assertIn("EWY 3개월(63거래일)",formatted)

    def test_missing_exchange_session_withholds_both_rolling_windows(self):
        records=self._fixture_market_history()
        records["IYW"].pop(-10)
        self.assertIsNone(w.rolling_estimated_flows(records["IYW"],21,"IYW"))
        self.assertIsNone(w.rolling_estimated_flows(records["IYW"],63,"IYW"))

    def test_official_exchange_holidays_do_not_cause_false_missing_session(self):
        rows=self._fixture_market_history()["IYW"]
        self.assertFalse(any(x["date"]=="2026-09-07" for x in rows))
        self.assertIsNotNone(w.rolling_estimated_flows(rows,63,"IYW"))

    def test_soxx_split_crossing_blocks_long_period_but_not_unrelated_fund(self):
        rows=self._fixture_market_history(to_date="2026-11-06")
        self.assertIsNone(w.rolling_estimated_flows(rows["SOXX"],21,"SOXX"))
        self.assertIsNone(w.rolling_estimated_flows(rows["SOXX"],63,"SOXX"))
        self.assertIsNotNone(w.rolling_estimated_flows(rows["IYW"],63,"IYW"))

    def test_issuer_funddownload_parses_historical_shares_and_nav(self):
        rows=self._fixture_market_history()["IYW"]
        payload={"componentsByNameMap":{"fundDownload":{"containersByNameMap":{
            "historical":{"dataPointsByNameMap":{
                "asof":{"value":[int(x["date"].replace("-","")) for x in rows]},
                "nav":{"value":[x["nav"] for x in rows]},
                "sharesOutstanding":{"value":[x["shares"] for x in rows]},
            }}
        }}}}
        class Response:
            def raise_for_status(self): return None
            def json(self): return payload
        with patch.object(w.requests,"get",return_value=Response()) as api:
            result=w.issuer_nav_history("IYW",rows[-1])
        self.assertEqual(result[-1]["date"],"2026-11-02")
        self.assertEqual(len(result),len(rows))
        self.assertEqual(result[0]["shares"],rows[0]["shares"])
        self.assertEqual(api.call_args.kwargs["params"]["portfolioId"],"239522")
        with patch.object(w.requests,"get",return_value=Response()):
            with self.assertRaisesRegex(ValueError,"current fund page mismatch"):
                w.issuer_nav_history("IYW",{**rows[-1],"shares":1_000_000})

    def test_backfill_mismatch_does_not_replace_verified_history(self):
        old=w.prior_state() if hasattr(w,"prior_state") else prior_state()
        current=snap("2026-10-21")
        def disagree(ticker,row):
            return [{"date":"2026-10-20","nav":1.0,"shares":5.0},
                    {"date":row["date"],"nav":row["nav"],"shares":row["shares"]}]
        copied,added=w.verified_backfill(old,current,fetcher=disagree)
        self.assertEqual(added,0)
        self.assertEqual(copied["history"],old["history"])
        x=w.calculate(current,copied)
        self.assertIsNone(x["movements"]["IYW"]["rolling"][21])
        self.assertIn("1개월(21거래일) 누적: 확인 대기",w.render(x,1342.9,"date"))

    def test_monthly_sum_is_not_end_nav_times_net_shares(self):
        rows=self._fixture_market_history()["IYW"]
        last=rows[-22:]
        for i,row in enumerate(last):
            row["nav"]=120+i
        stat=w.rolling_estimated_flows(rows,21,"IYW")
        reference=sum((last[i]["shares"]-last[i-1]["shares"])*last[i]["nav"]
                      for i in range(1,len(last)))
        self.assertAlmostEqual(stat["net_usd"],reference)
        self.assertNotAlmostEqual(stat["net_usd"],
                                  (last[-1]["shares"]-last[0]["shares"])*last[-1]["nav"])


    def test_five_session_amount_is_sum_of_daily_nav_weighted_changes(self):
        # Retrospective issuer-validated SOXX observation window: 19-26 Oct.
        # A 4.26% one-day creation is not the full five-session cash proxy.
        prev=[
            ("2026-10-19",502.003427,81_100_000),
            ("2026-10-20",500.282491,83_900_000),
            ("2026-10-21",510.40,89_000_000),
            ("2026-10-22",475.34,91_550_000),
            ("2026-10-23",478.50,90_350_000),
        ]
        old=prior_state()
        old["history"]["SOXX"]=[{"date":date,"nav":nav,"shares":shares}
                                   for date,nav,shares in prev]
        recent=snap("2026-10-26",soxx_shares=94_200_000)
        recent["SOXX"]["nav"]=492.25
        outcome=w.calculate(recent,old)
        actual=outcome["movements"]["SOXX"]
        expected=6_536_910_474.8
        old_proxy=(94_200_000-81_100_000)*492.25
        self.assertAlmostEqual(actual["five_observations_creation_usd"],expected,places=1)
        self.assertNotAlmostEqual(actual["five_observations_creation_usd"],old_proxy)
        self.assertAlmostEqual(actual["five_observations_share_change_pct"],16.1528976572,places=7)
        self.assertIn("SOXX 최근 5회 발행좌수 +2.5% 이상",outcome["signals"])
        self.assertIn("일별 기준가격 적용 합계",w.render(outcome,1327.75,"2026-10-27"))

    def test_first_daily_alert_discloses_missing_five_session_history(self):
        old=prior_state("2026-10-23")
        old["history"]["SOXX"]=[{"date":"2026-10-23","nav":478.5,"shares":90_350_000}]
        current=snap("2026-10-26",soxx_shares=94_200_000)
        current["SOXX"]["nav"]=492.25
        outcome=w.calculate(current,old)
        self.assertIn("SOXX 발행좌수 당일 +1% 이상",outcome["signals"])
        self.assertIsNone(outcome["movements"]["SOXX"]["five_observations_creation_usd"])
        self.assertIn("최근 5거래일 합계: 확인 보류",w.render(outcome,1327.75,"2026-10-27"))


if __name__=="__main__":
    unittest.main()
