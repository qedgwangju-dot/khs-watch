#!/usr/bin/env python3
"""네트워크에 의존하지 않는 Warsh 금리·대차대조표 회귀검증."""
import unittest
import os
from datetime import date, datetime, timedelta, timezone
from unittest.mock import MagicMock, patch

import warsh_policy_path_watch_v4 as futures
import warsh_policy_path_watch_v3 as view
import warsh_balance_sheet_watch_v2 as balance
import warsh_policy_path_watch_v3 as path_v3
import warsh_policy_source_guard as guard
import warsh_sep_path_watch_v2 as sep
import warsh_post_fomc_ib_reaction_watch as post_ib
import warsh_energy_shock_watch as energy
import warsh_ai_taskforce_watch_v2 as gartner


class WarshSafetyTests(unittest.TestCase):
    def test_network_failure_is_bounded(self):
        with patch.object(futures.urllib.request, "urlopen", side_effect=TimeoutError("blocked")) as opener:
            with self.assertRaises(TimeoutError):
                futures.get_json("https://example.invalid", retries=1, timeout=8)
            self.assertEqual(opener.call_count, 1)
            self.assertEqual(opener.call_args.kwargs["timeout"], 8)

    def test_futures_are_not_mislabeled_as_official_fedwatch_probabilities(self):
        rates = {(2026, 10): 3.90, (2026, 11): 4.10, (2026, 12): 4.20}
        dates = [date(2026, 10, 28), date(2026, 12, 9)]
        with patch.object(futures, "ny_today", return_value=date(2026, 10, 8)), \
             patch.object(futures, "cme_monthly_rates", return_value=("2026-10-07", rates)), \
             patch.object(futures, "official_effr", return_value=(3.88, "2026-10-07")), \
             patch.object(futures, "official_fomc_dates", return_value=dates), \
             patch.object(futures.v3.base, "official_policy_baseline", return_value={"low":3.75,"high":4.0}):
            snap = futures._legacy_public_settlement_snapshot()
        self.assertEqual(len(snap["meetings"]), 2)
        self.assertTrue(all(m["hike25_prob"] is None for m in snap["meetings"]))
        self.assertTrue(all(m["outcomes"] == {} for m in snap["meetings"]))
        self.assertIn("판정 유보", view._meeting_line(snap["meetings"][0]))
        self.assertLess(snap["meetings"][0]["change_bp"], 100)

    def test_old_effr_must_not_generate_new_signal(self):
        with patch.object(futures, "ny_today", return_value=date(2026, 10, 8)), \
             patch.object(futures, "cme_monthly_rates", return_value=("2026-10-07", {(2026, 10): 3.9})), \
             patch.object(futures, "official_effr", return_value=(3.88, "2026-09-01")):
            with self.assertRaisesRegex(RuntimeError, "오래됨"):
                futures._legacy_public_settlement_snapshot()

    def test_balance_sheet_composition_is_not_automatic_qt(self):
        cur = {
            "date": "2026-09-30", "total_assets": 6743031, "total_assets_weekly": -4673,
            "treasury": 4564161, "bills": 560211, "mbs": 1898089,
            "reserves": 2881686, "reserves_weekly": None,
            "url": "https://www.federalreserve.gov/releases/h41/Current/",
        }
        impl = {
            "date": "2026-09-16", "mode": "충분한 준비금 유지·재투자/구성 전환",
            "url": "https://www.federalreserve.gov/monetarypolicy/fomccalendars.htm",
        }
        task = {"url": "https://www.federalreserve.gov/monetarypolicy/balance-sheet-policy-task-force.htm"}
        msg = balance.summary_message_v2(cur, impl, task, "자산 구성 전환", None, "검증")
        self.assertIn("충분한 준비금 유지·QT 재개 공식 미확인", msg)
        self.assertIn("주택저당증권", msg)


    def _fresh_market_state(self):
        from zoneinfo import ZoneInfo
        now = datetime.now(timezone.utc)
        nydate = now.astimezone(ZoneInfo("America/New_York")).date()
        next_meeting = nydate + timedelta(days=12)
        last_trade = nydate - timedelta(days=1)
        return {
            "source_status": guard.SUCCESS_STATUS,
            "source_error": None,
            "official_settlement_date": last_trade.isoformat(),
            "last_validated_at_utc": now.isoformat(),
            "meetings": [{
                "date": next_meeting.isoformat(),
                "post_rate": 4.12,
                "change_bp": 25.0,
                "hike25_prob": None,
            }],
            "classification": {"extra_bp": 25.0},
            "source": "https://www.cmegroup.com/markets/interest-rates/stirs/30-day-federal-fund.settlements.html",
            "market_data_basis": "CME 공식 지연 결제값 기반 금리 기대(확률 별도 확인 전 판정 유보)",
        }

    def test_stale_market_state_is_rejected_for_ib_and_sep(self):
        state = self._fresh_market_state()
        state["source_status"] = "최신성 검증 실패 — 직전 정상값 보존"
        state["source_error"] = "CME 응답 지연"
        self.assertFalse(guard.market_state_is_fresh(state))
        with patch.object(post_ib, "load", return_value=state):
            self.assertIsNone(post_ib.market_path()["year_end"])
        with patch.object(sep, "load", return_value=state):
            self.assertIsNone(sep.market_dec())
        with patch.object(energy, "load_json", return_value=state):
            self.assertIsNone(energy.policy_snapshot()["extra_bp"])

    def test_valid_market_state_can_be_used_by_ib(self):
        state = self._fresh_market_state()
        self.assertTrue(guard.market_state_is_fresh(state))
        with patch.object(post_ib, "load", return_value=state):
            self.assertTrue(post_ib.market_path()["fresh"])

    def test_recovery_requires_new_validated_timestamp_and_trade_date(self):
        state = self._fresh_market_state()
        state.pop("last_validated_at_utc")
        self.assertFalse(guard.market_state_is_fresh(state))
        state = self._fresh_market_state()
        state["last_validated_at_utc"] = (datetime.now(timezone.utc)-timedelta(days=2)).isoformat()
        self.assertFalse(guard.market_state_is_fresh(state))
        state = self._fresh_market_state()
        state["official_settlement_date"] = (datetime.now(timezone.utc)-timedelta(days=12)).date().isoformat()
        self.assertFalse(guard.market_state_is_fresh(state))

    def test_percent_and_basis_points_are_never_the_same_unit(self):
        self.assertEqual(guard.probability_weighted_bp(90, 25), 22.5)
        self.assertEqual(guard.probability_weighted_bp(0, 25), 0)
        with self.assertRaises(ValueError):
            guard.probability_weighted_bp(120, 25)

    def test_implausible_month_end_extrapolation_fails_closed(self):
        with patch.object(futures, "ny_today", return_value=date(2026, 10, 8)), \
             patch.object(futures, "cme_monthly_rates", return_value=("2026-10-07", {(2026,10):3.70})), \
             patch.object(futures, "official_effr", return_value=(3.88,"2026-10-07")), \
             patch.object(futures, "official_fomc_dates", return_value=[date(2026,10,28)]), \
             patch.object(futures.v3.base, "official_policy_baseline", return_value={"low":3.75,"high":4.0}):
            with self.assertRaisesRegex(RuntimeError, "비정상값"):
                futures._legacy_public_settlement_snapshot()

    def test_initial_market_outage_preserves_safe_state(self):
        saved = []
        with patch.object(path_v3, "validated_snapshot", side_effect=TimeoutError("공식 결제값 조회 지연")), \
             patch.object(path_v3.base, "load_state", return_value={}), \
             patch.object(path_v3.base, "save_state", side_effect=lambda s: saved.append(s)), \
             patch.object(path_v3.base, "send", side_effect=AssertionError("발송해서는 안 됨")):
            path_v3.main()
        self.assertEqual(len(saved), 1)
        self.assertEqual(saved[0].get("meetings"), [])
        self.assertIsNone(saved[0].get("source"))
        self.assertIn("검증 실패", saved[0]["source_status"])


    def test_existing_stale_market_payload_is_quarantined(self):
        saved = []
        old = self._fresh_market_state()
        old["classification"] = {"extra_bp": 22.5, "verdict": "과거 판정"}
        with patch.object(path_v3, "validated_snapshot", side_effect=TimeoutError("CME 지연")), \
             patch.object(path_v3.base, "load_state", return_value=old), \
             patch.object(path_v3.base, "save_state", side_effect=lambda s: saved.append(s)), \
             patch.object(path_v3.base, "send", return_value=None):
            path_v3.main()
        self.assertEqual(saved[0]["meetings"], [])
        self.assertIsNone(saved[0]["source"])
        self.assertTrue(saved[0]["classification"]["market_source_stale"])
        self.assertEqual(saved[0]["last_good_snapshot"]["meetings"], old["meetings"])

    def test_third_party_source_can_never_be_fresh_market_state(self):
        state = self._fresh_market_state()
        state["source"] = "https://www.frenzycap.com/fedwatch"
        self.assertFalse(guard.market_state_is_fresh(state))

    def test_settlement_only_state_rejects_embedded_probability(self):
        state = self._fresh_market_state()
        state["meetings"][0]["hike25_prob"] = 90.0
        self.assertFalse(guard.market_state_is_fresh(state))

    def test_official_cme_ftp_csv_parser_requires_settlement_header(self):
        raw = "Symbol,Settle\nZQV6,96.100\nZQX6,95.900\nZQZ6,95.800\n"
        months = futures.parse_cme_ftp_csv(raw, date(2026, 10, 8))
        self.assertAlmostEqual(months[(2026,10)], 3.9)
        self.assertAlmostEqual(months[(2026,11)], 4.1)
        self.assertAlmostEqual(months[(2026,12)], 4.2)
        with self.assertRaisesRegex(RuntimeError, "헤더"):
            futures.parse_cme_ftp_csv("Symbol,Close\nZQV6,96.100\n", date(2026,10,8))

    def test_balance_sheet_same_date_rerun_keeps_previous_week_reference(self):
        history = [
            {"date":"2026-09-30","reserves":2881686},
            {"date":"2026-10-07","reserves":3022066},
        ]
        prev = balance.base.previous_observation(history, "2026-10-07")
        self.assertEqual(prev["date"], "2026-09-30")

    def test_missing_weekly_reserve_change_cannot_trigger_weekly_qt(self):
        cur = {
            "date":"2026-10-07",
            "total_assets":6700000,"total_assets_weekly":-100000,
            "securities":6400000,"securities_weekly":-60000,
            "reserves":3000000,"reserves_weekly":None,
            "bills":500000,"bills_weekly":0,
            "mbs":1900000,"mbs_weekly":0,
            "treasury":4500000,
        }
        regime, _ = balance.base.classify_h41(cur, [])
        self.assertNotEqual(regime, "주간 기준 대차대조표 총량 축소 신호")


    def test_effr_outside_official_target_range_is_rejected(self):
        with patch.object(futures, "ny_today", return_value=date(2026,10,8)), \
             patch.object(futures, "cme_monthly_rates", return_value=("2026-10-07",{(2026,10):3.90})), \
             patch.object(futures, "official_effr", return_value=(5.00,"2026-10-07")), \
             patch.object(futures.v3.base, "official_policy_baseline", return_value={"low":3.75,"high":4.00}):
            with self.assertRaisesRegex(RuntimeError, "불일치"):
                futures._legacy_public_settlement_snapshot()

    def test_missing_year_end_contract_never_becomes_year_end_forecast(self):
        with patch.object(futures, "ny_today", return_value=date(2026,10,8)), \
             patch.object(futures, "cme_monthly_rates", return_value=("2026-10-07",{(2026,10):3.90})), \
             patch.object(futures, "official_effr", return_value=(3.88,"2026-10-07")), \
             patch.object(futures, "official_fomc_dates", return_value=[date(2026,10,28),date(2026,12,9)]), \
             patch.object(futures.v3.base, "official_policy_baseline", return_value={"low":3.75,"high":4.00}):
            with self.assertRaisesRegex(RuntimeError, "연말 FOMC"):
                futures._legacy_public_settlement_snapshot()


    def test_cme_outage_does_not_retry_many_contract_dates(self):
        with patch.object(futures, "ny_today", return_value=date(2026, 10, 8)), \
             patch.object(futures, "get_json", side_effect=TimeoutError("blocked")) as api, \
             patch.object(futures, "cme_monthly_rates_ftp", side_effect=RuntimeError("FTP 장애")):
            with self.assertRaisesRegex(RuntimeError, "접속 장애"):
                futures.cme_monthly_rates()
        self.assertEqual(api.call_count, 1, "접속 장애에서 날짜마다 재시도해도 복구되지 않는다")

    def test_cme_csv_fallback_checks_prior_business_dates_within_bound(self):
        raw = "Symbol,Settle\nZQV6,96.100\nZQX6,95.900\nZQZ6,95.800\n"
        response = MagicMock()
        response.__enter__.return_value.read.return_value = raw.encode("utf-8")
        with patch.object(futures, "ny_today", return_value=date(2026, 10, 9)), \
             patch.object(futures.urllib.request, "urlopen", side_effect=[
                 TimeoutError("10/09 archive late"),
                 TimeoutError("10/08 archive late"),
                 response,
             ]) as opener:
            trade_date, rates = futures.cme_monthly_rates_ftp()
        self.assertEqual(trade_date, "2026-10-07")
        self.assertEqual(opener.call_count, 3)
        self.assertAlmostEqual(rates[(2026, 10)], 3.90)
        self.assertAlmostEqual(rates[(2026, 12)], 4.20)


    def test_cme_unpublished_today_tries_prior_settlement(self):
        from urllib.error import HTTPError
        prior = {"settlements": [
            {"month": "OCT 26", "settle": "96.10"},
            {"month": "NOV 26", "settle": "96.00"},
            {"month": "DEC 26", "settle": "95.90"},
        ]}
        with patch.object(futures, "ny_today", return_value=date(2026, 10, 8)), \
             patch.object(futures, "get_json", side_effect=[
                 HTTPError("https://www.cmegroup.com/", 404, "not published", {}, None),
                 prior,
             ]) as api:
            trade_date, rates = futures.cme_monthly_rates()
        self.assertEqual(trade_date, "2026-10-07")
        self.assertEqual(len(rates), 3)
        self.assertEqual(api.call_count, 2)

    def test_operational_instructions_not_navigation_control_qt(self):
        sample = (
            "Menu: old QT runoff caps and policy archive. "
            "Roll over at auction all principal payments from Treasury securities. "
            "Reinvest all principal payments from holdings of agency securities into Treasury bills. "
            "When appropriate, increase the System Open Market Account holdings "
            "to maintain an ample level of reserves."
        )
        mode, core = balance.base.interpret_implementation_text(sample)
        self.assertEqual(mode, "충분한 준비금 유지·재투자/구성 전환")
        self.assertIn("Roll over", core)
        self.assertNotIn("Menu:", core)

    def test_ambiguous_qt_wording_never_means_qt_is_confirmed(self):
        impl = {
            "date": "2026-10-28",
            "mode": "정책문구 혼재 — QT 여부 판정 유보",
            "url": "https://www.federalreserve.gov/",
        }
        cur = {
            "date": "2026-10-07", "total_assets": 6747560,
            "total_assets_weekly": 4529, "treasury": 4566384,
            "bills": 562157, "mbs": 1898089,
            "reserves": 3022066, "reserves_weekly": None,
            "url": "https://www.federalreserve.gov/releases/h41/Current/",
        }
        task = {"url": "https://www.federalreserve.gov/"}
        message = balance.summary_message_v2(cur, impl, task, "혼합", None, "정책문구 검토")
        self.assertIn("공식 정책문구 해석 유보", message)
        self.assertNotIn("QT 판정</b>: 총량축소형 QT 공식 명시", message)

    def test_previous_year_sep_never_matches_next_year_futures(self):
        from warsh_policy_path_watch import classify
        import warsh_policy_path_watch as core
        snap = {"effr": 3.88, "meetings": [
            {"date": "2027-01-27", "post_rate": 3.90},
            {"date": "2027-12-08", "post_rate": 4.10},
        ]}
        with patch.object(core, "official_policy_baseline", return_value={
            "mid": 3.875, "date": "2026-09-16", "kind": "연준 공식 중간값",
            "source": "https://www.federalreserve.gov/monetarypolicy",
        }), patch.object(core, "official_sep_baseline", return_value={
            "date": "2026-09-16", "yearend": 4.10, "nextyear": 4.10
        }), patch.object(core, "balance_sheet_baseline", return_value={
            "mode": "정책문구 혼재 — QT 여부 판정 유보",
            "regime": "혼합",
        }):
            out = classify(snap)
        self.assertEqual(out["reference_year"], 2027)
        self.assertIsNone(out["sep"])
        self.assertNotIn("이중긴축", out["tightening_mix"])

    def test_legacy_alerted_outage_without_timestamp_does_not_duplicate_immediately(self):
        legacy = {
            "source_error_streak": 20,
            "source_health_alerted": True,
        }
        saved = []
        with patch.object(path_v3, "validated_snapshot", side_effect=TimeoutError("CME")), \
             patch.object(path_v3.base, "load_state", return_value=legacy), \
             patch.object(path_v3.base, "save_state", side_effect=lambda s: saved.append(s)), \
             patch.object(path_v3.base, "send") as send, \
             patch.object(path_v3.base, "FORCE", False):
            path_v3.main()
        send.assert_not_called()
        self.assertTrue(saved[0].get("last_health_alert_at_utc"))
        self.assertEqual(saved[0].get("meetings"), [])


    def test_source_failure_warning_is_throttled_72_hours(self):
        now = datetime.now(timezone.utc)
        initial = {
            "source_error_streak": 19,
            "source_health_alerted": True,
            "last_health_alert_at_utc": (now - timedelta(hours=1)).isoformat(),
        }
        with patch.object(path_v3, "validated_snapshot", side_effect=TimeoutError("CME")), \
             patch.object(path_v3.base, "load_state", return_value=initial), \
             patch.object(path_v3.base, "save_state"), \
             patch.object(path_v3.base, "send") as send, \
             patch.object(path_v3.base, "FORCE", False):
            path_v3.main()
        send.assert_not_called()
        previous = dict(initial)
        previous["last_health_alert_at_utc"] = (now - timedelta(hours=73)).isoformat()
        with patch.object(path_v3, "validated_snapshot", side_effect=TimeoutError("CME")), \
             patch.object(path_v3.base, "load_state", return_value=previous), \
             patch.object(path_v3.base, "save_state"), \
             patch.object(path_v3.base, "send") as send, \
             patch.object(path_v3.base, "FORCE", False):
            path_v3.main()
        self.assertEqual(send.call_count, 1)



    def test_gartner_rss_503_keeps_previous_good_headline(self):
        from urllib.error import HTTPError
        item = {
            "title": "Gartner Finds AI Workforces Changing - Gartner",
            "published": "2026-10-07T10:20:03+00:00",
            "url": "https://www.gartner.com/en/newsroom/",
        }
        state = {"gartner_latest": item}
        with patch.object(gartner.base, "fetch", side_effect=HTTPError(
            "https://news.google.com/rss",503,"temporary",{},None
        )), patch.object(gartner.base, "load_state", return_value=state):
            result = gartner.structural_gartner_items()
        self.assertEqual(result, [item])


    def test_paid_fedwatch_without_entitlement_never_scrapes_or_guesses(self):
        with patch.dict(os.environ, {
            "CME_FEDWATCH_API_ID": "", "CME_FEDWATCH_API_PASSWORD": "",
        }), patch.object(futures, "cme_monthly_rates") as legacy, \
             patch.object(futures.official_api, "oauth_token") as auth:
            with self.assertRaisesRegex(RuntimeError, "인증정보 미설정"):
                futures.official_snapshot()
        legacy.assert_not_called()
        auth.assert_not_called()

    def test_official_api_probability_is_from_target_ranges_not_avg_price(self):
        today = date(2026,10,9)
        fixture = {
            "meetingDt":"2026-10-28","reportingDt":"2026-10-08",
            "rateRange":[
                {"lowerRt":350,"upperRt":375,"probability":0.0},
                {"lowerRt":375,"upperRt":400,"probability":0.4},
                {"lowerRt":400,"upperRt":425,"probability":0.6},
                {"lowerRt":425,"upperRt":450,"probability":0.0},
            ],
        }
        parsed = futures.official_api.parse_forecast(fixture, 3.75, 4.0, today)
        self.assertAlmostEqual(parsed["hike25_prob"], 60)
        self.assertAlmostEqual(parsed["hike25_or_more_prob"], 60)
        self.assertAlmostEqual(parsed["hold_prob"], 40)
        self.assertAlmostEqual(parsed["post_rate"], 4.025)
        self.assertAlmostEqual(parsed["change_bp"], 15)
        # 확률 분포가 없는 평균만으로 60%를 복원해서는 안 됨.
        bad = dict(fixture, rateRange=[dict(fixture["rateRange"][2], probability=0.35)])
        with self.assertRaisesRegex(ValueError, "합계"):
            futures.official_api.parse_forecast(bad, 3.75,4.0,today)

    def test_official_api_rejects_stale_future_and_duplicate_odds(self):
        today = date(2026,10,9)
        base = {
            "meetingDt":"2026-10-28", "reportingDt":"2026-10-08",
            "rateRange":[{"lowerRt":375,"upperRt":400,"probability":1.0}]
        }
        for item, msg in [
            (dict(base, reportingDt="2026-10-01"),"오래됨"),
            (dict(base, reportingDt="2026-10-12"),"미래"),
            (dict(base, rateRange=[
                {"lowerRt":375,"upperRt":400,"probability":0.5},
                {"lowerRt":375,"upperRt":400,"probability":0.5}]),"중복"),
            (dict(base, rateRange=[
                {"lowerRt":375,"upperRt":400,"probability":90.0}]),"확률"),
        ]:
            with self.subTest(msg=msg), self.assertRaisesRegex(ValueError,msg):
                futures.official_api.parse_forecast(item,3.75,4.0,today)

    def test_official_api_scope_is_explicitly_validated_before_market_recovery(self):
        now = datetime(2026,10,9,20,0,tzinfo=timezone.utc)
        today = date(2026,10,9)
        vals = [
            {"meetingDt":d,"reportingDt":"2026-10-08",
             "rateRange":[
                 {"lowerRt":375,"upperRt":400,"probability":.3},
                 {"lowerRt":400,"upperRt":425,"probability":.7},
             ]}
            for d in ("2026-10-28","2026-12-09")
        ]
        x = futures.official_api.build_snapshot(
            vals,["2026-10-28","2026-12-09"],
            {"low":3.75,"high":4.0},today,
        )
        state = dict(x,
            source=x["url"],source_api_url=x["source_api_url"],
            official_settlement_date=None,
            last_validated_at_utc="2026-10-09T19:58:00+00:00",
            source_status=guard.SUCCESS_STATUS,source_error=None,
        )
        self.assertTrue(guard.market_state_is_fresh(state,now=now))
        bad = dict(state,source_api_url="https://badsite.example/api")
        self.assertFalse(guard.market_state_is_fresh(bad,now=now))
        bad = dict(state,forecast_reporting_date="2026-09-19")
        self.assertFalse(guard.market_state_is_fresh(bad,now=now))
        bad = dict(state,meetings=[dict(state["meetings"][0],hike25_prob=150)])
        self.assertFalse(guard.market_state_is_fresh(bad,now=now))

    def test_official_api_path_uses_auth_and_official_forecast_payload(self):
        x = [
            {"meetingDt":d,"reportingDt":"2026-10-08",
             "rateRange":[
                {"lowerRt":375,"upperRt":400,"probability":.2},
                {"lowerRt":400,"upperRt":425,"probability":.8},
             ]}
            for d in ("2026-10-28","2026-12-09")
        ]
        with patch.dict(os.environ, {
            "CME_FEDWATCH_API_ID": "test_api_id",
            "CME_FEDWATCH_API_PASSWORD": "test_api_password",
        }), patch.object(futures, "ny_today",return_value=date(2026,10,9)), \
            patch.object(futures,"official_effr",return_value=(3.88,"2026-10-08")), \
            patch.object(futures,"official_fomc_dates",return_value=[
                date(2026,10,28),date(2026,12,9)]), \
            patch.object(futures.v3.base,"official_policy_baseline",return_value={
                "low":3.75,"high":4.0}), \
            patch.object(futures.official_api,"oauth_token",return_value="redacted") as auth, \
            patch.object(futures.official_api,"forecasts",return_value=x) as forecasts:
            snap=futures.official_snapshot()
        auth.assert_called_once_with("test_api_id","test_api_password")
        forecasts.assert_called_once_with("redacted",["2026-10-28","2026-12-09"])
        self.assertEqual(snap["forecast_reporting_date"],"2026-10-08")
        self.assertEqual(snap["official_settlement_date"],None)
        self.assertEqual(snap["meetings"][0]["hike25_prob"],80.0)

    def test_oauth_request_requires_client_credentials_without_printing_password(self):
        with patch.object(futures.official_api,"_request_json",return_value={
            "access_token":"token-do-not-log"}) as requester:
            t=futures.official_api.oauth_token("identifier","secret")
        self.assertEqual(t,"token-do-not-log")
        args, kwargs=requester.call_args
        self.assertEqual(kwargs["body"],b"grant_type=client_credentials")
        self.assertTrue(args[1]["Authorization"].startswith("Basic "))
        self.assertNotIn("secret",str((args,kwargs)))


    def test_api_entitlement_notice_only_once_and_state_streak_is_bounded(self):
        old = {
            "source_error_streak":24,
            "source_error_kind":"transport",
            "source_health_alerted":True,
            "last_health_alert_at_utc":datetime.now(timezone.utc).isoformat(),
        }
        records=[]
        reason=RuntimeError("CME FedWatch 공식 API 인증정보 미설정")
        with patch.object(path_v3,"validated_snapshot",side_effect=reason), \
             patch.object(path_v3.base,"load_state",side_effect=lambda:dict(old)), \
             patch.object(path_v3.base,"save_state",side_effect=lambda x:records.append(dict(x))), \
             patch.object(path_v3.base,"send",return_value=101) as send, \
             patch.object(path_v3.base,"FORCE",False):
            path_v3.main()
        send.assert_called_once()
        self.assertEqual(records[0]["source_error_streak"],2)
        self.assertEqual(records[0]["source_error_kind"],"auth_missing")
        self.assertEqual(records[0]["last_health_message_id"],101)

        with patch.object(path_v3,"validated_snapshot",side_effect=reason), \
             patch.object(path_v3.base,"load_state",return_value=records[0]), \
             patch.object(path_v3.base,"save_state") as save, \
             patch.object(path_v3.base,"send") as send, \
             patch.object(path_v3.base,"FORCE",False):
            path_v3.main()
        send.assert_not_called()
        self.assertEqual(save.call_args.args[0]["source_error_streak"],2)


if __name__ == "__main__":
    unittest.main()
