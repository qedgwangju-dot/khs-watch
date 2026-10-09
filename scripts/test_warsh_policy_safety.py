#!/usr/bin/env python3
"""네트워크에 의존하지 않는 Warsh 금리·대차대조표 회귀검증."""
import unittest
from datetime import date, datetime, timedelta, timezone
from unittest.mock import patch

import warsh_policy_path_watch_v4 as futures
import warsh_policy_path_watch_v3 as view
import warsh_balance_sheet_watch_v2 as balance
import warsh_policy_path_watch_v3 as path_v3
import warsh_policy_source_guard as guard
import warsh_sep_path_watch_v2 as sep
import warsh_post_fomc_ib_reaction_watch as post_ib


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
            snap = futures.official_snapshot()
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
                futures.official_snapshot()

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
        self.assertIn("현재는 총량축소형 QT 아님", msg)
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
                futures.official_snapshot()

    def test_initial_market_outage_preserves_safe_state(self):
        saved = []
        with patch.object(path_v3, "validated_snapshot", side_effect=TimeoutError("공식 결제값 조회 지연")), \
             patch.object(path_v3.base, "load_state", return_value={}), \
             patch.object(path_v3.base, "save_state", side_effect=lambda s: saved.append(s)), \
             patch.object(path_v3.base, "send", side_effect=AssertionError("발송해서는 안 됨")):
            path_v3.main()
        self.assertEqual(len(saved), 1)
        self.assertNotIn("meetings", saved[0])
        self.assertIn("검증 실패", saved[0]["source_status"])


    def test_effr_outside_official_target_range_is_rejected(self):
        with patch.object(futures, "ny_today", return_value=date(2026,10,8)), \
             patch.object(futures, "cme_monthly_rates", return_value=("2026-10-07",{(2026,10):3.90})), \
             patch.object(futures, "official_effr", return_value=(5.00,"2026-10-07")), \
             patch.object(futures.v3.base, "official_policy_baseline", return_value={"low":3.75,"high":4.00}):
            with self.assertRaisesRegex(RuntimeError, "불일치"):
                futures.official_snapshot()

    def test_missing_year_end_contract_never_becomes_year_end_forecast(self):
        with patch.object(futures, "ny_today", return_value=date(2026,10,8)), \
             patch.object(futures, "cme_monthly_rates", return_value=("2026-10-07",{(2026,10):3.90})), \
             patch.object(futures, "official_effr", return_value=(3.88,"2026-10-07")), \
             patch.object(futures, "official_fomc_dates", return_value=[date(2026,10,28),date(2026,12,9)]), \
             patch.object(futures.v3.base, "official_policy_baseline", return_value={"low":3.75,"high":4.00}):
            with self.assertRaisesRegex(RuntimeError, "연말 FOMC"):
                futures.official_snapshot()


if __name__ == "__main__":
    unittest.main()
