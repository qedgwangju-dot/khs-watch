#!/usr/bin/env python3
"""네트워크에 의존하지 않는 Warsh 금리·대차대조표 회귀검증."""
import unittest
import urllib.parse
import json
import os
from datetime import date, datetime, timedelta, timezone
from unittest.mock import MagicMock, patch

import warsh_policy_path_watch_v4 as futures
import warsh_policy_path_watch_v3 as view
import warsh_balance_sheet_watch_v2 as balance
import warsh_policy_path_watch_v3 as path_v3
import warsh_policy_source_guard as guard
import warsh_policy_state_sync as state_sync
import warsh_sep_path_watch_v2 as sep
import warsh_post_fomc_ib_reaction_watch as post_ib
import warsh_energy_shock_watch as energy
import warsh_ai_taskforce_watch_v2 as gartner
import warsh_fomc_event_watch as fomc_base
import warsh_fomc_event_watch_v4 as fomc_v4
import warsh_press_conference_watch_v3 as press_v3


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



    def test_gartner_official_archive_is_used_before_rss(self):
        archive = """
        <html><body>
        <a href="/en/newsroom/press-releases/2026-10-08-gartner-survey-shows-chief-procurement-officers-stalling-on-needed-ai-role-redesign">
          Gartner Survey Shows Chief Procurement Officers Stalling on Needed AI Role Redesign
        </a>
        </body></html>
        """
        with patch.object(gartner.base, "fetch", return_value=archive), \
             patch.object(gartner, "rss_gartner_items") as rss:
            result = gartner.structural_gartner_items()
        rss.assert_not_called()
        self.assertEqual(result[-1]["published"][:10], "2026-10-08")
        self.assertIn("Role Redesign", result[-1]["title"])
        self.assertIn("/en/newsroom/press-releases/", result[-1]["url"])
        self.assertTrue(urllib.parse.urlparse(result[-1]["url"]).hostname.endswith("gartner.com"))

    def test_gartner_source_failure_suppresses_reposting(self):
        # A cache entry is not a newly verified official release. Preserve
        # it in main's state, but never return it as a fresh article.
        with patch.object(gartner, "official_rss_items", side_effect=TimeoutError("blocked")), \
             patch.object(gartner, "official_gartner_items", side_effect=TimeoutError("blocked")):
            result = gartner.structural_gartner_items()
        self.assertEqual(result, [])


    def test_missing_probability_api_fails_closed_without_scraping_or_guessing(self):
        with patch.dict(os.environ, {
            "CME_FEDWATCH_API_ID": "", "CME_FEDWATCH_API_PASSWORD": "",
        }), patch.object(futures, "_legacy_public_settlement_snapshot") as settlement, \
             patch.object(futures.official_api, "oauth_token") as auth:
            with self.assertRaisesRegex(RuntimeError, "인증정보 미설정"):
                futures.official_snapshot()
        settlement.assert_not_called()
        auth.assert_not_called()

    def test_probability_api_failure_does_not_promote_public_settlement_to_fedwatch(self):
        with patch.dict(os.environ, {
            "CME_FEDWATCH_API_ID": "id", "CME_FEDWATCH_API_PASSWORD": "pw",
        }), patch.object(futures.v3.base,"official_policy_baseline",
                        return_value={"low":3.75,"high":4.0}), \
             patch.object(futures,"official_effr",return_value=(3.88,"2026-10-08")), \
             patch.object(futures,"ny_today",return_value=date(2026,10,9)), \
             patch.object(futures,"official_fomc_dates",return_value=[date(2026,10,28)]), \
             patch.object(futures.official_api,"oauth_token",
                        side_effect=RuntimeError("entitlement denied")), \
             patch.object(futures,"_legacy_public_settlement_snapshot") as settlement:
            with self.assertRaisesRegex(RuntimeError, "entitlement denied"):
                futures.official_snapshot()
        settlement.assert_not_called()

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

    def test_settlement_fallback_message_never_calls_expected_rate_a_probability(self):
        snap = {
            "market_data_basis":"CME 공식 지연 결제값 기반 금리 기대(확률 별도 확인 전 판정 유보)",
            "probability_source_status":"CME FedWatch 인증 API 미연결 — 공식 결제값 기반 기대금리만 사용, 구간별 확률 판정 유보",
            "meetings":[{
                "date":"2026-10-28","post_rate":4.02,"change_bp":14.0,
                "hike25_prob":None,
            }],
            "url":"https://www.cmegroup.com/markets/interest-rates/stirs/30-day-federal-fund.settlements.html",
        }
        cls = {
            "verdict":"추가 1회 인상 가능성 반영",
            "baseline_rate":3.875,"baseline_kind":"FOMC 공식 목표범위 중간값",
            "yearend_market_rate":4.02,"extra_bp":14.5,
            "sep":None,"balance":None,
        }
        msg=path_v3.message_v3(snap,cls)
        self.assertIn("공식 결제값 기반 기대변화",msg)
        self.assertIn("구간별 확률 판정 유보",msg)
        self.assertIn("실제 인상 횟수나 구간별 확률이 아닙니다",msg)
        self.assertNotIn("0.58회 상당의 <b>확률가중 평균</b>",msg)

    def test_oauth_request_requires_client_credentials_without_printing_password(self):
        with patch.object(futures.official_api,"_request_json",return_value={
            "access_token":"token-do-not-log"}) as requester:
            t=futures.official_api.oauth_token("identifier","secret")
        self.assertEqual(t,"token-do-not-log")
        args, kwargs=requester.call_args
        self.assertEqual(kwargs["body"],b"grant_type=client_credentials")
        self.assertTrue(args[1]["Authorization"].startswith("Basic "))
        self.assertNotIn("secret",str((args,kwargs)))


    def test_cme_source_health_message_never_mislabels_public_archive_as_discontinued(self):
        msg = path_v3._source_health_message(
            "error", "CME FedWatch 공식 API 인증정보 미설정"
        )
        self.assertNotIn("지원종료 FTP", msg)
        self.assertIn("구간별 확률 원천이 아니므로", msg)

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

    def test_newer_repo_delivery_blocks_repeated_source_warning(self):
        older = {
            "updated_at_utc":"2026-10-09T23:58:00+00:00",
            "source_error_kind":"transport",
            "source_health_alerted":True,
            "last_health_message_id":71,
        }
        newer = {
            "updated_at_utc":"2026-10-10T00:00:00+00:00",
            "source_error_kind":"auth_missing",
            "source_health_alerted":True,
            "last_health_message_id":72,
        }
        chosen, why = state_sync.reconcile(older, newer)
        self.assertEqual(why,"remote_newer")
        self.assertEqual(chosen["last_health_message_id"],72)
        self.assertEqual(chosen["source_error_kind"],"auth_missing")
        # 이후 감시의 새 소스오류는 이미 안내된 'auth_missing'과 같아 전송 대상 아님
        with patch.object(path_v3,"validated_snapshot",
                          side_effect=RuntimeError("CME 공식 API 인증정보 미설정")), \
             patch.object(path_v3.base,"load_state",return_value=chosen), \
             patch.object(path_v3.base,"save_state"), \
             patch.object(path_v3.base,"send") as send, \
             patch.object(path_v3.base,"FORCE",False):
            path_v3.main()
        send.assert_not_called()

    def test_unverifiable_git_state_fails_closed(self):
        x={"updated_at_utc":"2026-10-10T00:00:00+00:00",
           "last_health_message_id":72}
        y=dict(x,last_health_message_id=73)
        with self.assertRaisesRegex(RuntimeError,"상태가 서로 다름"):
            state_sync.reconcile(x,y)
        stale=dict(x,updated_at_utc="2026-10-09T23:59:00+00:00")
        best,reason=state_sync.reconcile(x,stale)
        self.assertEqual(reason,"local_newer")
        self.assertEqual(best,x)
        with self.assertRaisesRegex(RuntimeError,"갱신시각"):
            state_sync.reconcile(x,{"last_health_message_id":80})



class WarshOctoberFOMCRegressionTests(unittest.TestCase):
    def test_october_vote_and_full_dissent_names_from_official_statement(self):
        url='https://www.federalreserve.gov/newsevents/pressreleases/monetary20261028a.htm'
        raw=(
            '<html>October 28, 2026 The Federal Open Market Committee approved '
            'the following statement for release by a 10 – 2 vote: '
            'The Committee decided to maintain the target range for the federal funds rate '
            'at 3-3/4 to 4 percent. Productivity growth is strong. '
            'Voting against the monetary policy action were Lisa D. Cook and '
            'Beth M. Hammack, who preferred to raise the target range for the federal '
            'funds rate by 1/4 percentage point at this meeting. '
            'For media inquiries, contact the Board.</html>'
        )
        with patch.object(fomc_base,'fetch',return_value=(raw,url)):
            stmt=fomc_base.parse_statement(url)
        self.assertEqual(stmt['date'],'2026-10-28')
        self.assertEqual((stmt['low'],stmt['high']),(3.75,4.0))
        self.assertEqual((stmt['vote_for'],stmt['vote_against']),(10,2))
        self.assertIn('Lisa D. Cook and Beth M. Hammack',stmt['against'])
        self.assertNotIn('For media inquiries',stmt['against'])

    def test_old_meeting_followup_market_is_scrubbed_without_new_alert(self):
        state={
            'event_statement_date':'2026-10-28',
            'event_detected_at_utc':'2026-10-28T19:14:08+00:00',
            'followups_sent':['30분','90분'],
            'followup_30분_market':{'S&P 500':{'value':7700}},
            'followup_6시간_market':{'S&P 500':{'value':7500}},
            'followup_6시간_at_utc':'2026-09-17T00:00:00+00:00',
            'pre_event_market_event_date':'2026-09-16',
            'pre_event_market':{'S&P 500':{'value':7500}},
        }
        fomc_v4.prune_stale_snapshots(state,'2026-10-28')
        self.assertNotIn('followup_6시간_market',state)
        self.assertNotIn('pre_event_market',state)
        self.assertIn('followup_30분_market',state)
        state['pre_event_market_event_date']='2026-11-18'
        state['pre_event_market']={'S&P 500':{'value':7600}}
        fomc_v4.prune_stale_snapshots(state,'2026-11-18')
        self.assertIn('pre_event_market',state)
        fomc_v4.clear_event_scoped_snapshots(state,'2026-11-18')
        self.assertEqual(state['followups_sent'],[])
        self.assertIn('pre_event_market',state)

    def test_pre_event_market_capture_requires_fresh_quote(self):
        now=datetime(2026,10,28,17,40,tzinfo=timezone.utc)
        stale={'S&P 500':{'value':7700,'timestamp':'2026-10-27T17:40:00+00:00'}}
        state={}
        with patch.object(fomc_v4.base,'market_snapshot',return_value=stale):
            self.assertFalse(fomc_v4.capture_pre_event_if_due(state,'2026-10-28',now))
        fresh={'S&P 500':{'value':7700,'timestamp':now.isoformat()}}
        with patch.object(fomc_v4.base,'market_snapshot',return_value=fresh):
            self.assertTrue(fomc_v4.capture_pre_event_if_due(state,'2026-10-28',now))
        self.assertEqual(state['pre_event_market_event_date'],'2026-10-28')

    def test_2y_down_10y_up_is_not_mislabeled_as_easing(self):
        msg=fomc_base.market_read({
            '2년물':{'change_bp':-5.2},
            '10년물':{'change_bp':2.7}
        })
        self.assertIn('가팔라짐',msg)
        self.assertNotIn('함께 하락',msg)

    def test_fomc_telegram_receipt_must_match_numeric_chat(self):
        response=MagicMock()
        response.__enter__.return_value.read.return_value=json.dumps({
            'ok':True,'result':{'message_id':109,'chat':{'id':-10055}}
        }).encode()
        with patch.object(fomc_base,'TOKEN','fake'), \
             patch.object(fomc_base,'CHAT_ID','-10055'), \
             patch.object(fomc_base,'EXPECTED_BOT','hshs8879_bot'), \
             patch.object(fomc_base,'botname',return_value='hshs8879_bot'), \
             patch.object(fomc_base.urllib.request,'urlopen',return_value=response):
            self.assertEqual(fomc_base.send('test'),109)
        with patch.object(fomc_base,'TOKEN','fake'), \
             patch.object(fomc_base,'CHAT_ID','-10066'), \
             patch.object(fomc_base,'EXPECTED_BOT','hshs8879_bot'), \
             patch.object(fomc_base,'botname',return_value='hshs8879_bot'), \
             patch.object(fomc_base.urllib.request,'urlopen',return_value=response):
            with self.assertRaisesRegex(RuntimeError,'chat.id'):
                fomc_base.send('test')

    def test_october_structural_supplement_requires_official_and_reports(self):
        samples={
            press_v3.STRUCTURAL_FED:(
                'October 28, 2026 10 – 2 vote Lisa D. Cook Beth M. Hammack '
                'Productivity growth is strong 3-3/4 to 4 percent'
            ),
            press_v3.STRUCTURAL_URLS['productivity']:
                'Oct 28, 2026 Reuters Warsh productivity not running too hot',
            press_v3.STRUCTURAL_URLS['balance']:
                'Oct 28, 2026 Reuters Warsh balance sheet task force first quarter',
            press_v3.STRUCTURAL_URLS['strategy']:
                'Oct 28, 2026 Reuters Warsh 2027 2028 strategy meetings',
            press_v3.STRUCTURAL_URLS['korea']:
                '2026.10.28 워시 한국 일본 싱가포르 공급망',
            press_v3.STRUCTURAL_URLS['ai_rates']:
                '2026-10-29 워시 AI 금리 투자 변화',
            press_v3.STRUCTURAL_URLS['hearing']:
                'Oct 28, 2026 Reuters Warsh November 16 productivity hearing',
        }
        def fake_fetch(url,timeout=8):
            return samples.get(url,''),url
        with patch.object(press_v3.base,'fetch',side_effect=fake_fetch):
            verified=press_v3.verified_structural_sources()
        self.assertTrue(press_v3.structural_eligible(verified))
        self.assertTrue(all(verified.values()))
        msg=press_v3.structural_message(verified)
        self.assertIn('2027년 1분기',msg)
        self.assertIn('2분기 시행은 확정되지',msg)
        self.assertIn('한국·일본·싱가포르',msg)
        self.assertLess(len(msg),3900)
        with patch.object(press_v3.base,'fetch',return_value=('unverified','https://www.federalreserve.gov/')):
            self.assertIsNone(press_v3.verified_structural_sources())

    def test_existing_press_and_structural_delivery_are_not_repeated(self):
        stmt={'text':'Inflation remains elevated. Productivity growth is strong.'}
        cls=press_v3.classify(stmt['text'],[])
        old={
            'meeting_date':press_v3.STRUCTURAL_DATE,
            'classification':cls,
            'transcript':None,
            'structural_sent_key':press_v3.STRUCTURAL_KEY,
            'balance_addendum_sent_key':press_v3.BALANCE_ADDENDUM_KEY,
            'structural_message_id':109
        }
        with patch.object(press_v3.base,'load',return_value=old), \
             patch.object(press_v3,'current_meeting',return_value=(
                 press_v3.STRUCTURAL_DATE,'https://www.federalreserve.gov/',stmt)), \
             patch.object(press_v3,'transcript_link',return_value=None), \
             patch.object(press_v3,'reuters_rows',return_value=[]), \
             patch.object(press_v3.base,'save'), \
             patch.object(press_v3.base,'send') as sender, \
             patch.object(press_v3,'verified_structural_sources') as source_check:
            press_v3.main()
        sender.assert_not_called()
        source_check.assert_not_called()

    def test_rss_classification_churn_does_not_resend_press_release(self):
        stmt={'text':'Inflation remains elevated.'}
        old={
            'meeting_date':press_v3.STRUCTURAL_DATE,
            'classification':{'inflation_priority':False},
            'transcript':None,
            'structural_sent_key':press_v3.STRUCTURAL_KEY,
            'balance_addendum_sent_key':press_v3.BALANCE_ADDENDUM_KEY
        }
        with patch.object(press_v3.base,'load',return_value=old), \
             patch.object(press_v3,'current_meeting',return_value=(
                 press_v3.STRUCTURAL_DATE,'https://www.federalreserve.gov/',stmt)), \
             patch.object(press_v3,'transcript_link',return_value=None), \
             patch.object(press_v3,'reuters_rows',return_value=[]), \
             patch.object(press_v3.base,'save'), \
             patch.object(press_v3.base,'send') as sender:
            press_v3.main()
        sender.assert_not_called()


class WarshBalanceAddendumRegressionTests(unittest.TestCase):
    def test_syndicated_reuters_zero_width_characters_are_normalized(self):
        url=press_v3.STRUCTURAL_URLS['balance']
        raw='<html>Oct 28, 2026 Reuters Warsh balance sheet first &#8204;quarter</html>'
        with patch.object(press_v3.base,'fetch',return_value=(raw,url)):
            text=press_v3.source_text(url)
        self.assertIn('first quarter',text)

    def test_balance_addendum_marks_implementation_as_unconfirmed(self):
        msg=press_v3.balance_addendum_message({'balance':True,'korea':False})
        self.assertIn('2027년 1분기',msg)
        self.assertIn('2027년 2분기 대차대조표 축소 시행은 확정되지',msg)
        self.assertIn('연준 공식 시행지침',msg)
        self.assertLess(len(msg),3900)

    def test_confirmed_balance_addendum_cannot_resend(self):
        stmt={'text':'Inflation remains elevated.'}
        old={
            'meeting_date':press_v3.STRUCTURAL_DATE,
            'classification':press_v3.classify(stmt['text'],[]),
            'transcript':None,
            'structural_sent_key':press_v3.STRUCTURAL_KEY,
            'structural_verified_topics':['strategy','ai_rates'],
            'balance_addendum_sent_key':press_v3.BALANCE_ADDENDUM_KEY,
            'balance_addendum_message_id':118
        }
        with patch.object(press_v3.base,'load',return_value=old), \
             patch.object(press_v3,'current_meeting',return_value=(
                 press_v3.STRUCTURAL_DATE,'https://www.federalreserve.gov/',stmt)), \
             patch.object(press_v3,'transcript_link',return_value=None), \
             patch.object(press_v3,'reuters_rows',return_value=[]), \
             patch.object(press_v3.base,'save'), \
             patch.object(press_v3.base,'send') as sender, \
             patch.object(press_v3,'verified_structural_sources') as proof:
            press_v3.main()
        sender.assert_not_called()
        proof.assert_not_called()

    def test_ambiguous_balance_delivery_stays_blocked(self):
        stmt={'text':'Inflation remains elevated.'}
        old={
            'meeting_date':press_v3.STRUCTURAL_DATE,
            'classification':press_v3.classify(stmt['text'],[]),
            'transcript':None,
            'structural_sent_key':press_v3.STRUCTURAL_KEY,
            'structural_verified_topics':['strategy','ai_rates'],
            'balance_addendum_pending_key':press_v3.BALANCE_ADDENDUM_KEY,
            'balance_addendum_delivery_status':'sending'
        }
        with patch.object(press_v3.base,'load',return_value=old), \
             patch.object(press_v3,'current_meeting',return_value=(
                 press_v3.STRUCTURAL_DATE,'https://www.federalreserve.gov/',stmt)), \
             patch.object(press_v3,'transcript_link',return_value=None), \
             patch.object(press_v3,'reuters_rows',return_value=[]), \
             patch.object(press_v3.base,'save'), \
             patch.object(press_v3.base,'send') as sender, \
             patch.object(press_v3,'verified_structural_sources') as proof:
            press_v3.main()
        sender.assert_not_called()
        proof.assert_not_called()


class WarshKoreaQAFollowupTests(unittest.TestCase):
    def prior(self):
        return {
            'meeting_date':press_v3.STRUCTURAL_DATE,
            'structural_sent_key':press_v3.STRUCTURAL_KEY,
            'structural_delivery_status':'confirmed',
            'structural_message_id':117,
            'structural_verified_topics':['strategy','ai_rates'],
            'balance_addendum_sent_key':press_v3.BALANCE_ADDENDUM_KEY,
            'balance_addendum_delivery_status':'confirmed',
            'balance_addendum_message_id':118,
        }

    def test_two_independent_sources_and_official_required(self):
        fed='oct 28, 2026 fomc approved statement by a 10 - 2 vote lisa d. cook beth m. hammack 3-3/4 to 4 percent'
        news='2026.10.29 워시 한국 경제 일본 싱가포르 비행기와 선박'
        yonhap='2026.10.29 워시 한국 경제 일본 싱가포르 항공기와 선박'
        proofs={
            press_v3.STRUCTURAL_FED:fed,
            press_v3.KOREA_REPORTS[0][1]:news,
            press_v3.KOREA_REPORTS[1][1]:yonhap,
        }
        with patch.object(press_v3,'source_text',side_effect=lambda u:proofs.get(u,'')):
            verified=press_v3.verified_korea_addendum_sources()
            self.assertEqual(len(verified),2)
            self.assertIn('한국',press_v3.korea_addendum_message(verified))
            self.assertLess(len(press_v3.korea_addendum_message(verified)),3900)
            proofs.pop(press_v3.KOREA_REPORTS[1][1])
            self.assertIsNone(press_v3.verified_korea_addendum_sources())
            proofs.pop(press_v3.STRUCTURAL_FED)
            self.assertIsNone(press_v3.verified_korea_addendum_sources())

    def test_korea_sent_once_and_previous_receipts_preserved(self):
        import datetime as _dt
        class FixedDatetime(_dt.datetime):
            @classmethod
            def now(cls,tz=None):
                return cls(2026,10,29,12,0,tzinfo=tz)
        saved=self.prior()
        proof=[{'publisher':'뉴스1','url':press_v3.KOREA_REPORTS[0][1]},
               {'publisher':'연합뉴스','url':press_v3.KOREA_REPORTS[1][1]}]
        def load():return dict(saved)
        def save(v):saved.clear();saved.update(v)
        with patch.object(press_v3,'datetime',FixedDatetime), \
             patch.object(press_v3.base,'load',side_effect=load), \
             patch.object(press_v3.base,'save',side_effect=save), \
             patch.object(press_v3,'current_meeting',return_value=(
                 press_v3.STRUCTURAL_DATE,'https://www.federalreserve.gov/',{'text':'Inflation remains elevated.'})), \
             patch.object(press_v3,'transcript_link',return_value=None), \
             patch.object(press_v3,'reuters_rows',return_value=[]), \
             patch.object(press_v3,'verified_korea_addendum_sources',return_value=proof) as validator, \
             patch.object(press_v3.base,'send',return_value=119) as sender:
            press_v3.main()
            press_v3.main()
        sender.assert_called_once()
        validator.assert_called_once()
        self.assertEqual(saved['korea_addendum_message_id'],119)
        self.assertEqual(saved['korea_addendum_delivery_status'],'confirmed')
        self.assertEqual(saved['structural_message_id'],117)
        self.assertEqual(saved['balance_addendum_message_id'],118)

    def test_unknown_korea_delivery_never_retries(self):
        import datetime as _dt
        class FixedDatetime(_dt.datetime):
            @classmethod
            def now(cls,tz=None):
                return cls(2026,10,29,12,0,tzinfo=tz)
        old=self.prior()
        old.update({'korea_addendum_pending_key':press_v3.KOREA_ADDENDUM_KEY,
                    'korea_addendum_delivery_status':'sending'})
        with patch.object(press_v3,'datetime',FixedDatetime), \
             patch.object(press_v3.base,'load',return_value=old), \
             patch.object(press_v3.base,'save'), \
             patch.object(press_v3,'current_meeting',return_value=(
                 press_v3.STRUCTURAL_DATE,'https://www.federalreserve.gov/',{'text':'Inflation remains elevated.'})), \
             patch.object(press_v3,'transcript_link',return_value=None), \
             patch.object(press_v3,'reuters_rows',return_value=[]), \
             patch.object(press_v3,'verified_korea_addendum_sources') as validator, \
             patch.object(press_v3.base,'send') as sender:
            press_v3.main()
        validator.assert_not_called()
        sender.assert_not_called()


class WarshBalanceDeliveryReceiptTests(unittest.TestCase):
    def test_telegram_message_and_chat_receipt_required(self):
        fake=MagicMock()
        fake.__enter__.return_value=fake
        fake.read.return_value=json.dumps({
            'ok':True,'result':{'message_id':123,'chat':{'id':-10055}}
        }).encode()
        with patch.object(balance.base,'TOKEN','fake'), \
             patch.object(balance.base,'CHAT','-10055'), \
             patch.object(balance.base,'BOT','hshs8879_bot'), \
             patch.object(balance.base,'botname',return_value='hshs8879_bot'), \
             patch.object(balance.base.urllib.request,'urlopen',return_value=fake):
            self.assertEqual(balance.base.send('검증'),123)
            fake.read.return_value=json.dumps({
                'ok':True,'result':{'chat':{'id':-10055}}
            }).encode()
            with self.assertRaisesRegex(RuntimeError,'message_id'):
                balance.base.send('검증')
            fake.read.return_value=json.dumps({
                'ok':True,'result':{'message_id':124,'chat':{'id':-10066}}
            }).encode()
            with self.assertRaisesRegex(RuntimeError,'chat.id'):
                balance.base.send('검증')

    def test_pending_balance_send_blocks_all_retrievals(self):
        prior={'pending_key':'opaque-event','delivery_status':'sending'}
        with patch.object(balance.base,'load_state',return_value=prior), \
             patch.object(balance.base,'h41_snapshot') as fetch, \
             patch.object(balance.base,'send') as sender:
            with self.assertRaisesRegex(RuntimeError,'중복 재전송 보류'):
                balance.base.main()
        fetch.assert_not_called()
        sender.assert_not_called()

    def test_balance_alert_key_is_stable(self):
        cur={'date':'2026-10-28'}
        impl={'fingerprint':'a'}
        task={'fingerprint':'b'}
        a=balance.base.alert_key(cur,impl,task,'구성 전환',['A','B'])
        self.assertEqual(a,balance.base.alert_key(cur,impl,task,'구성 전환',['B','A']))
        self.assertNotEqual(a,balance.base.alert_key(cur,impl,task,'총량 축소',['A','B']))


class MarketInternalFinalCloseStaggerTests(unittest.TestCase):
    def test_staggered_etf_dates_skip_without_sending_or_state_write(self):
        import io
        from contextlib import redirect_stdout
        import market_internal_strength_watch as market_internal
        buf=io.StringIO()
        with patch.object(market_internal,'snapshot',side_effect=RuntimeError(
                 "ETF final-close source dates are not aligned: ['2026-10-28', '2026-10-29']")), \
             patch.object(market_internal,'load_state') as old_state, \
             patch.object(market_internal,'save_state') as saver, \
             patch.object(market_internal,'send') as sender, \
             redirect_stdout(buf):
            market_internal.main()
        result=json.loads(buf.getvalue().strip())
        self.assertFalse(result['data_valid'])
        self.assertFalse(result['sent'])
        self.assertTrue(result['retry_later'])
        old_state.assert_not_called()
        saver.assert_not_called()
        sender.assert_not_called()

    def test_unrelated_data_error_remains_failure(self):
        import market_internal_strength_watch as market_internal
        with patch.object(market_internal,'snapshot',
                          side_effect=RuntimeError('VIX Cboe/Yahoo mismatch')), \
             patch.object(market_internal,'send') as sender:
            with self.assertRaisesRegex(RuntimeError,'VIX Cboe/Yahoo mismatch'):
                market_internal.main()
            sender.assert_not_called()


if __name__ == "__main__":
    unittest.main()
