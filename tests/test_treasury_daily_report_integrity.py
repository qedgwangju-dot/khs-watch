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
import treasury_credit_flow_delivery as delivery


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
    def test_refinancing_krw_uses_unrounded_source_amounts(self):
        # 2026-09-30 MSPD values and the 2026-10-09 ECB/Frankfurter rate.
        refi = {
            "next12_t": 10.640155363354076, "next12_share": 33.42294955600567,
            "bills_t": 7.1181453141, "bill_share": 22.35958063026692,
            "plus75_b": 53.38608985575,
        }
        line = report._refinancing_line(refi, 1341.49)
        self.assertIn("$10.64T (약 1경4,274조원)", line)
        self.assertIn("Bills $7.12T (약 9,549조원)", line)
        self.assertIn("+$53.4B (약 71.62조원)", line)

    def test_negative_usd_flow_places_sign_before_currency_symbol(self):
        self.assertEqual(base.fmt_usd_flow(-8_934_000), "-$8.9M")
        self.assertEqual(base.fmt_usd_flow(-1_210_000_000), "-$1.21B")
        self.assertEqual(base.fmt_usd_flow(0), "±$0")

    def test_original_fund_flows_are_inferred_not_actual_provider_net_flows(self):
        self.assertEqual(
            base.compute_flow(
                {"date": "2026-10-08", "shares": 232100000, "nav": 76.98},
                [{"date": "2026-10-07", "shares": 232200000}],
            ),
            -7698000,
        )
        self.assertEqual(
            base.compute_flow(
                {"date": "2026-10-12", "shares": 623_600_000, "nav": 78.01},
                [{"date": "2026-10-09", "shares": 625_200_000}],
            ),
            -124_816_000.0,
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
             patch.object(report, "get_refinancing_snapshot", return_value={"record_date":"2026-09-30","next12_t":10.64,"next12_share":33.4,"bills_t":7.12,"bill_share":22.4,"plus75_b":53.4}), \
             patch.object(report.real_yield, "build_block", return_value="[실질금리·시장 내재 물가상승률]\n원천 날짜 일치: 2026-10-08"):
            rendered = report._compact_report(raw)
        self.assertIn("전체 방향: 장기 국채금리 하락 · 회사채 신용 경계", rendered)
        self.assertIn("국채·ETF 2026-10-08 / 회사채 OAS 2026-10-07", rendered)
        self.assertIn("이번 거래일 10년물 -6bp 하락", rendered)
        self.assertIn("당일 30년물 -7bp 하락", rendered)
        self.assertIn("같은 거래일 동시 위험회피로 단정하지 않음", rendered)
        self.assertIn("Bills에 +75bp 적용 시", rendered)
        self.assertIn("ETF 보유채권 포트폴리오 특성치", rendered)
        self.assertIn("금리 방향: 장기 ↓ 하락 · 2년 ↓ 하락", rendered)
        self.assertIn("국채 해석(ETF 추정): 당일 전 만기 유입 / 최근 5회 만기별 혼조", rendered)
        self.assertIn("회사채 해석(ETF 추정): 당일 투자등급 선호 신호 / 최근 5회 투자등급·고수익 모두 유입", rendered)
        self.assertEqual(rendered.count("+$512.2M"), 1)
        self.assertEqual(rendered.count(explanation), 1)

    def test_direction_panel_keeps_rate_falls_distinct_from_etf_outflows(self):
        # The user's October 15 alert: lower long yields but ETF redemptions.
        flows = {t: ("↓ 추정 순유출 -$1.0M", "확인 대기") for t in ("SHY", "IEF", "TLT", "LQD", "HYG")}
        flows["SHY"] = ("↑ 추정 순유입 +$1.0M", "확인 대기")
        lines = report._direction_panel(flows, "4.82% | ↑ +3bp", "5.19% | ↓ -2bp", "5.52% | ↓ -4bp", "기준일 시차 있는 신용위험 경계", "281.7bp | 기준 2026-10-13 | 직전 저장값 대비 ↑ +5.1bp")
        self.assertEqual(lines[0], "금리 방향: 장기 ↓ 하락 · 2년 ↑ 상승")
        self.assertIn("단기(SHY) 유입 · 중기(IEF) 유출 · 장기(TLT) 유출", lines[1])
        self.assertIn("투자등급(LQD) 유출 · 고수익(HYG) 유출", lines[2])
        self.assertIn("HYG 신용스프레드(OAS) ↑ +5.1bp", lines[3])
        self.assertNotIn("가격 상승", "\n".join(lines))

    def test_direction_panel_missing_and_mixed_rates_are_not_flattened(self):
        flows = {t: ("확인 대기", "확인 대기") for t in ("SHY", "IEF", "TLT", "LQD", "HYG")}
        missing = report._direction_panel(flows, "확인 대기", "5.19% | ↓ -2bp", "확인 대기", "확인 대기", "확인 대기")
        self.assertIn("장기 확인 대기", missing[0])
        self.assertIn("중기(IEF) 확인 대기", missing[1])
        self.assertIn("변화 비교 확인 대기", missing[3])
        mixed = report._direction_panel(flows, "4.82% | → 0bp", "5.19% | ↑ +2bp", "5.52% | ↓ -4bp", "혼조", "280.0bp | 직전 저장값 대비 → 0.0bp")
        self.assertIn("혼조 (10년 ↑ 상승 · 30년 ↓ 하락)", mixed[0])
        self.assertIn("2년 → 보합", mixed[0])
        self.assertIn("(OAS) → 0.0bp", mixed[3])

    def test_mobile_html_emphasizes_overview_and_escapes_source_text(self):
        formatted = report._format_html("[한눈에 보기]\n금리 방향: 장기 ↓ 하락\n10년: 5.19% | ↓ -2bp\nRepo: 안정\n환율: A&B <기준>")
        self.assertIn("<b>금리 방향: 장기 ↓ 하락</b>", formatted)
        self.assertNotIn("<b>10년:", formatted)
        self.assertNotIn("<b>Repo:", formatted)
        self.assertIn("A&amp;B &lt;기준&gt;", formatted)

    def test_user_daily_and_recent_flows_have_separate_interpretations(self):
        flows = {
            "SHY": ("↑ 추정 순유입 +$16.2M", "↑ +$211.1M"),
            "IEF": ("↓ 추정 순유출 -$269.1M", "↓ -$107.9M"),
            "TLT": ("↓ 추정 순유출 -$181.4M", "↑ +$340.3M"),
            "LQD": ("↓ 추정 순유출 -$205.3M", "↑ +$276.5M"),
            "HYG": ("↓ 추정 순유출 -$153.3M", "↓ -$392.0M"),
        }
        panel = report._flow_interpretation_panel(flows, {t: "2026-10-14" for t in flows})
        self.assertIn("당일 짧은 만기 선호 신호 / 최근 5회 만기별 혼조", panel[0])
        self.assertIn("당일 투자등급·고수익 모두 유출 / 최근 5회 투자등급 선호 신호", panel[1])
        self.assertEqual(panel[2], "기간 차이: TLT·LQD는 당일 유출 / 최근 5회 유입")

    def test_maturity_preference_reverses_with_new_signed_values(self):
        flows = {t: ("↓ 추정 순유출 -$1.0M", "↓ -$2.0M") for t in ("SHY", "IEF", "TLT")}
        for t in ("IEF", "TLT"):
            flows[t] = ("↑ 추정 순유입 +$3.0M", "↑ +$4.0M")
        dates = {t: "2026-10-14" for t in flows}
        for period in (0, 1):
            self.assertEqual(report._flow_preference(flows, dates, tuple(flows), period, "국채"), "긴 만기 선호 신호")

    def test_all_maturities_together_do_not_imply_a_relative_preference(self):
        dates = {t: "2026-10-14" for t in ("SHY", "IEF", "TLT")}
        for flow, expected in (("↑ +$1.0M", "전 만기 유입"), ("↓ -$1.0M", "전 만기 유출"), ("→ ±$0", "전 만기 변화 없음")):
            with self.subTest(flow=flow):
                flows = {t: (flow, flow) for t in dates}
                self.assertEqual(report._flow_preference(flows, dates, tuple(dates), 0, "국채"), expected)

    def test_zero_long_flows_do_not_become_a_short_maturity_preference(self):
        flows = {"SHY": ("↑ +$1.0M", "↑ +$1.0M"), "IEF": ("→ ±$0", "→ ±$0"), "TLT": ("→ ±$0", "→ ±$0")}
        self.assertEqual(report._flow_preference(flows, {t: "2026-10-14" for t in flows}, tuple(flows), 0, "국채"), "만기별 혼조")

    def test_credit_grade_preference_is_independent_for_each_period(self):
        flows = {"LQD": ("↓ -$3.0M", "↑ +$1.0M"), "HYG": ("↑ +$2.0M", "↓ -$2.0M")}
        dates = {t: "2026-10-14" for t in flows}
        self.assertEqual(report._flow_preference(flows, dates, tuple(flows), 0, "회사채"), "고수익 선호 신호")
        self.assertEqual(report._flow_preference(flows, dates, tuple(flows), 1, "회사채"), "투자등급 선호 신호")

    def test_recent_missing_data_does_not_inherit_the_daily_preference(self):
        flows = {"SHY": ("↑ +$1.0M", "↑ +$2.0M"), "IEF": ("↓ -$1.0M", "확인 대기"), "TLT": ("↓ -$1.0M", "↓ -$2.0M")}
        dates = {t: "2026-10-14" for t in flows}
        self.assertEqual(report._flow_preference(flows, dates, tuple(flows), 0, "국채"), "짧은 만기 선호 신호")
        self.assertIn("자금 자료 미확인", report._flow_preference(flows, dates, tuple(flows), 1, "국채"))

    def test_mismatched_or_missing_fund_dates_hold_preference(self):
        flows = {"SHY": ("↑ +$1.0M", "↑ +$1.0M"), "IEF": ("↓ -$1.0M", "↓ -$1.0M"), "TLT": ("↓ -$1.0M", "↓ -$1.0M")}
        for date in (None, "2026-10-13"):
            with self.subTest(date=date):
                dates = {"SHY": "2026-10-14", "IEF": "2026-10-14", "TLT": date}
                self.assertIn("기준일 미확인·불일치", report._flow_preference(flows, dates, tuple(flows), 0, "국채"))

    def test_signed_recent_flow_parser_preserves_legacy_minus_and_rejects_conflicts(self):
        self.assertEqual(report._period_flow_direction("↓ $-7.7M"), "유출")
        self.assertEqual(report._period_flow_direction("↑ +$1.21B"), "유입")
        for flow in ("↑ -$1.0M", "↓ 추정 순유출 +$1.0M", "추정 순유입 확인 대기", "→ ±$1.0M"):
            with self.subTest(flow=flow):
                self.assertEqual(report._period_flow_direction(flow), "확인 대기")

    def test_period_comparison_only_lists_actual_opposite_signs(self):
        flows = {t: ("↑ +$1.0M", "↑ +$2.0M") for t in ("SHY", "IEF", "TLT", "LQD", "HYG")}
        dates = {t: "2026-10-14" for t in flows}
        self.assertEqual(len(report._flow_interpretation_panel(flows, dates)), 2)
        flows["SHY"] = ("↑ +$1.0M", "↓ -$2.0M")
        flows["TLT"] = ("↓ -$1.0M", "↑ +$2.0M")
        panel = report._flow_interpretation_panel(flows, dates)
        self.assertIn("TLT는 당일 유출 / 최근 5회 유입", panel[2])
        self.assertIn("SHY는 당일 유입 / 최근 5회 유출", panel[2])

    def test_html_emphasizes_dynamic_interpretation_but_not_period_detail(self):
        text = "국채 해석(ETF 추정): 당일 짧은 만기 선호 신호 / 최근 5회 혼조\n기간 차이: TLT는 당일 유출 / 최근 5회 유입"
        rendered = report._format_html(text)
        self.assertIn("<b>국채 해석(ETF 추정):", rendered)
        self.assertNotIn("<b>기간 차이:", rendered)


    def test_jpm_30y_level_does_not_claim_a_new_breakout(self):
        current = report._jpm_30y_signal(5.60)
        self.assertIn("신규 돌파 여부는", current)
        self.assertNotIn("신규 돌파 아님", current)


    def test_daily_receipt_is_korean_date_scoped_and_preserves_source_dedupe(self):
        state = {
            "last_delivery": {
                "treasury_date": "2026-10-22",
                "daily_delivery_date_kst": "2026-10-23",
                "message_ids": [476],
                "bot_username": "khs8879887988798879_bot",
            }
        }
        self.assertTrue(delivery.source_delivery_complete(state, "2026-10-22"))
        self.assertTrue(delivery.daily_delivery_complete(state, "2026-10-23"))
        self.assertFalse(delivery.should_run_delivery(
            state, "2026-10-22", "2026-10-23", daily_digest=True
        ))
        self.assertTrue(delivery.should_run_delivery(
            state, "2026-10-22", "2026-10-24", daily_digest=True
        ))
        self.assertFalse(delivery.should_run_delivery(
            state, "2026-10-22", "2026-10-24", daily_digest=False
        ))
        self.assertTrue(delivery.should_run_delivery(
            state, "2026-10-22", "2026-10-23", daily_digest=True, validate_only=True
        ))

    def test_daily_source_hold_notice_dedupes_without_blocking_later_report(self):
        state = {
            "daily_status_notification": {
                "date_kst": "2026-10-23",
                "message_ids": [477],
                "bot_username": "khs8879887988798879_bot",
            }
        }
        self.assertFalse(delivery.should_send_daily_status(state, "2026-10-23"))
        self.assertTrue(delivery.should_send_daily_status(state, "2026-10-24"))
        self.assertTrue(delivery.should_run_delivery(
            state, "2026-10-22", "2026-10-23", daily_digest=True
        ))

    def test_curve_reports_opposing_bull_moves_by_segment(self):
        current = {"2Y": 4.65, "10Y": 4.96, "30Y": 5.29}
        previous = {"2Y": 4.81, "10Y": 5.13, "30Y": 5.42}
        name, explanation, s210, s1030 = w.curve_regime(current, previous)
        self.assertEqual(name, "수익률곡선 구간별 혼조")
        self.assertIn("2-10년 불 플래트닝", explanation)
        self.assertIn("10-30년 불 스티프닝", explanation)
        self.assertAlmostEqual(s210[2], -1.0)
        self.assertAlmostEqual(s1030[2], 4.0)


if __name__ == "__main__":
    unittest.main()
