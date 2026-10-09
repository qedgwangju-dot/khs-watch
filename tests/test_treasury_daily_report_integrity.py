"""Regression tests for the existing Treasury ETF→GitHub Actions→Telegram report.

All market observations in these fixtures are explicitly synthetic or copied from the
user-provided October 9 report; no external network calls or Telegram messages.
"""
import datetime as dt
import unittest
from unittest.mock import patch
from zoneinfo import ZoneInfo

import treasury_credit_flow_watch_ishares as w
import treasury_credit_flow_watch_refinancing as report
import treasury_credit_flow_watch_marketstress as stress
import treasury_etf_flow_watch as base


def example():
    results = {
        "SHY": {"date": "2026-10-08", "flow_usd": 113666000},
        "IEF": {"date": "2026-10-08", "flow_usd": 8943000},
        "TLT": {"date": "2026-10-08", "flow_usd": 334669000, "nav_change_pct": 0.91},
        "LQD": {
            "date": "2026-10-08", "flow_usd": 512200000,
            "oas_date": "2026-10-07", "oas_bps": 82.51,
        },
        "HYG": {
            "date": "2026-10-08", "flow_usd": -7698000,
            "nav_change_pct": -0.09, "oas_date": "2026-10-07",
            "oas_bps": 274.41,
        },
    }
    prior = {
        "LQD": {"oas_date": "2026-10-06", "oas_bps": 83.13},
        "HYG": {"oas_date": "2026-10-06", "oas_bps": 269.13},
    }
    today = {"date": "2026-10-08", "2Y": 4.75, "10Y": 5.22, "30Y": 5.60}
    yesterday = {"date": "2026-10-07", "2Y": 4.77, "10Y": 5.28, "30Y": 5.67}
    return results, prior, today, yesterday


class TreasuryReportIntegrity(unittest.TestCase):
    def test_original_fund_flows_are_inferred_not_actual_provider_net_flows(self):
        self.assertEqual(
            base.compute_flow(
                {"date": "2026-10-08", "shares": 232100000, "nav": 76.98},
                [{"date": "2026-10-07", "shares": 232200000}],
            ),
            -7698000,
        )

    def test_latest_market_date_is_independent_of_korean_date(self):
        ts = dt.datetime(2026, 10, 9, 12, 2, tzinfo=ZoneInfo("Asia/Seoul"))
        self.assertEqual(w._us_latest_weekday(ts), "2026-10-08")

    def test_actual_2026_10_08_is_rate_down_and_credit_observation_lagged(self):
        data, prior, curve, previous = example()
        t_label, _ = w.treasury_class(data, curve)
        c_label, c_reason, _, hdelta = w.credit_class(data, prior)
        headline, reason = w.overall_class(t_label, c_label, data, curve, previous)
        self.assertEqual(t_label, "중·장기채 가격·자금 동반 회복")
        self.assertEqual(c_label, "기준일 시차 있는 신용위험 경계")
        self.assertAlmostEqual(hdelta, 5.28)
        self.assertIn("2026-10-07", c_reason)
        self.assertIn("2026-10-08", c_reason)
        self.assertIn("같은 날 동시 위험회피 확정 아님", c_reason)
        self.assertEqual(headline, "국채금리 하락·선행 신용경계")
        self.assertIn("-6bp", reason)
        self.assertIn("-7bp", reason)
        self.assertIn("다른 거래일", reason)
        self.assertNotIn("동시에 확인", reason)

    def test_same_day_spread_rise_can_be_stated_as_same_day(self):
        data, prior, curve, previous = example()
        data["HYG"]["oas_date"] = "2026-10-08"
        data["LQD"]["oas_date"] = "2026-10-08"
        c_label, _, _, _ = w.credit_class(data, prior)
        headline, _ = w.overall_class("중·장기채 가격·자금 동반 회복", c_label, data, curve, previous)
        self.assertEqual(c_label, "신용위험 경계 강화")
        self.assertEqual(headline, "국채금리 하락·신용경계")

    def test_rising_yields_and_lagged_credit_must_not_be_called_simultaneous(self):
        data, prior, _, previous = example()
        higher = {"date": "2026-10-08", "2Y": 4.78, "10Y": 5.30, "30Y": 5.72}
        c_label, _, _, _ = w.credit_class(data, prior)
        headline, text = w.overall_class("국채 ETF 혼조", c_label, data, higher, previous)
        self.assertEqual(headline, "장기금리 상승·선행 신용경계")
        self.assertIn("관측일이 달라", text)

    def test_yield_level_stress_is_not_a_fresh_selloff(self):
        title, reason = stress._market_stress(5.22, 5.60, -6, -7)
        self.assertIn("수준 경보", title)
        self.assertIn("-6bp 하락", reason)
        self.assertIn("-7bp 하락", reason)
        self.assertIn("신규", reason) if "신규" in reason else self.assertIn("매도세로 단정하지 않음", reason)

    def test_report_parser_handles_signed_rates_and_different_fund_dates(self):
        self.assertEqual(report._rate_move_bp("5.22% | ↓ -6bp"), -6)
        self.assertEqual(report._rate_move_bp("5.67% | ↑ +3bp"), 3)
        self.assertEqual(
            report._fund_date(
                "HYG", "HYG (미 고수익 회사채) — 2026-10-08\n• 가격: NAV $76.98"
            ), "2026-10-08",
        )
        alert = report._credit_alert_line(
            "↓ 추정 순유출 $-7.7M",
            "274.4bp | 기준 2026-10-07 | 직전 저장값 대비 ↑ +5.3bp",
            "2026-10-08",
        )
        self.assertIn("같은 거래일 동시 위험회피로 단정하지 않음", alert)
        self.assertIn("2026-10-08", alert)
        self.assertIn("2026-10-07", alert)

    def test_next_credit_alert_does_not_repeat_triggered_threshold(self):
        txt = report._next_alert(
            5.22, 5.60, "↓ 추정 순유출 $-7.7M",
            "274.4bp | 기준 2026-10-07 | 직전 저장값 대비 ↑ +5.3bp",
        )
        self.assertIn("HYG OAS 추가 확대 지속 여부", txt)
        self.assertNotIn("HYG 자금유출 + OAS 일간 +5bp 이상", txt)

    def test_telegram_report_preserves_source_dates_and_directions(self):
        data, prior, curve, previous = example()
        t_head, t_reason = w.treasury_class(data, curve)
        c_head, c_reason, _, _ = w.credit_class(data, prior)
        overall, explanation = w.overall_class(t_head, c_head, data, curve, previous)

        lines = [
            "조회시각(KST): 2026-10-09 12:02:42",
            "환율: 1달러=1,343.46원 | 기준 2026-10-08",
            f"전체 자금 방향: {overall}", f"→ {explanation}",
            f"ETF 자금 방향: {t_head}", f"→ {t_reason}",
            f"신용자금 방향: {c_head}", f"→ {c_reason}",
        ]
        funds = {
            "SHY": ("미 국채 1~3년", "↑ 추정 순유입 +$113.7M (+1,527억원)", "↑ +$454.1M (+6,100억원)", None),
            "IEF": ("미 국채 7~10년", "↑ 추정 순유입 +$8.9M (+120억원)", "↓ $-267.6M (-3,595억원)", None),
            "TLT": ("미 국채 20년 이상", "↑ 추정 순유입 +$334.7M (+4,496억원)", "↑ +$1.71B (+2.30조원)", None),
            "LQD": ("미 투자등급 회사채", "↑ 추정 순유입 +$512.2M (+6,881억원)", "↑ +$1.54B (+2.07조원)", "82.5bp | 기준 2026-10-07 | 직전 저장값 대비 ↓ -0.6bp"),
            "HYG": ("미 고수익 회사채", "↓ 추정 순유출 $-7.7M (-103억원)", "↑ +$622.4M (+8,362억원)", "274.4bp | 기준 2026-10-07 | 직전 저장값 대비 ↑ +5.3bp"),
        }
        for ticker, (label, dayflow, last5, oas) in funds.items():
            lines += [
                f"{ticker} ({label}) — 2026-10-08",
                "• 가격: NAV $77.00 | 1일 +0.0% | 30일 SEC 7.18%",
                f"• 일간 자금: {dayflow}",
                f"• 최근 5회: {last5}",
            ]
            if oas:
                lines.append(f"• 포트폴리오 OAS: {oas}")
            lines.append("")

        lines += [
            "기준: 2026-10-08 | 직전: 2026-10-07",
            "• 2년: 4.75% | ↓ -2bp",
            "• 10년: 5.22% | ↓ -6bp",
            "• 30년: 5.60% | ↓ -7bp",
            "• 2년-10년 금리차: 51bp → 47bp (-4bp)",
            "• 10년-30년 금리차: 39bp → 38bp (-1bp)",
            "• 현재 형태: 불 플래트닝",
            "• 쉬운 해석: 금리 하락, 장기금리 하락폭 더 큼",
            "• 오늘의 주도축: 금리 하락 구간",
        ]
        raw = "\n".join(lines)

        with patch.object(report, "get_repo_stress", return_value="Repo: 안정 | 기준 2026-10-07"), \
             patch.object(report.readable, "get_growth_cost_snapshot", return_value={"ok": False}), \
             patch.object(report, "get_refinancing_snapshot", return_value={"record_date":"2026-09-30","next12_t":10.64,"next12_share":33.4,"bills_t":7.12,"bill_share":22.4,"plus75_b":53.4}):
            rendered = report._compact_report(raw)
        self.assertIn("전체 방향: 국채금리 하락·선행 신용경계", rendered)
        self.assertIn("국채·ETF 2026-10-08 / 회사채 OAS 2026-10-07", rendered)
        self.assertIn("이번 거래일 10년물 -6bp 하락", rendered)
        self.assertIn("당일 30년물 -7bp 하락", rendered)
        self.assertIn("같은 거래일 동시 위험회피로 단정하지 않음", rendered)
        self.assertIn("Bills에 +75bp 적용 시", rendered)


    def test_jpm_30y_level_does_not_claim_a_new_breakout(self):
        current = report._jpm_30y_signal(5.60)
        self.assertIn("신규 돌파 여부는", current)
        self.assertNotIn("신규 돌파 아님", current)


if __name__ == "__main__":
    unittest.main()
