from __future__ import annotations

import math
import pathlib
import sys
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import yen_carry_composite_watch as watch  # noqa: E402


class YenCarryCompositeWatchTests(unittest.TestCase):
    def move(self, *, ch15=0.0, ch30=0.0, ch60=0.0, drawdown=0.0, duration=60.0, rebound=0.0):
        return watch.fx.FxMove(
            latest_price=159.0,
            latest_epoch=1_800_000_000.0,
            reference_15m=159.0,
            reference_15m_epoch=1_799_999_100.0,
            change_15m_pct=ch15,
            reference_30m=159.0,
            reference_30m_epoch=1_799_998_200.0,
            change_30m_pct=ch30,
            reference_60m=159.0,
            reference_60m_epoch=1_799_996_400.0,
            change_60m_pct=ch60,
            sustained_peak_price=160.0,
            sustained_peak_epoch=1_799_996_400.0,
            sustained_duration_minutes=duration,
            sustained_drawdown_pct=drawdown,
            sustained_low_price=158.0,
            sustained_rebound_pct=rebound,
        )

    def cftc(self, *, current_short=60000, previous_short=120000):
        return watch.CftcPosition(
            report_date="2026-08-11",
            open_interest=400000,
            leveraged_long=70000,
            leveraged_short=130000,
            net=-60000,
            net_short=current_short,
            net_short_pct_oi=current_short / 400000 * 100,
            previous_report_date="2026-08-04",
            previous_net_short=previous_short,
            short_covering=current_short < previous_short,
        )

    def mof(self, *, latest=5.1, prior=-0.3):
        return watch.MofOutwardFlow(
            latest_week="2026-08-09~08-15",
            previous_week="2026-08-02~08-08",
            latest_two_week_trillion_yen=latest,
            previous_two_week_trillion_yen=prior,
            outward_buying=latest > 0,
            outward_accelerating=latest > 0 and latest > prior,
        )

    def vol(self, *, ratio=1.0):
        return watch.FxVol(2.0, 2.0 / ratio if ratio else None, ratio, ratio >= 1.5)

    def policy(self):
        return {
            "official_joint_intervention": True,
            "further_joint_intervention_signal": True,
            "action_date": "2026-07-31",
            "age_days": 14,
            "recent": True,
        }

    def test_parse_mof_week_csv_uses_equity_plus_long_term_subtotal(self):
        rows = [
            ["2026-07-19~07-25", "1", "1", "0", "1", "1", "0", "-2000", "0", "0", "0", "-2000"],
            ["2026-07-26~08-01", "1", "1", "0", "1", "1", "0", "-1000", "0", "0", "0", "-1000"],
            ["2026-08-02~08-08", "1", "1", "0", "1", "1", "0", "25000", "0", "0", "0", "25000"],
            ["2026-08-09~08-15", "1", "1", "0", "1", "1", "0", "26000", "0", "0", "0", "26000"],
        ]
        text = "\n".join(",".join(row) for row in rows)
        result = watch.parse_mof_week_csv(text)
        self.assertAlmostEqual(result.latest_two_week_trillion_yen, 5.1)
        self.assertAlmostEqual(result.previous_two_week_trillion_yen, -0.3)
        self.assertTrue(result.outward_buying)
        self.assertTrue(result.outward_accelerating)

    def test_parse_cftc_detects_short_covering(self):
        payload = """[
          {"report_date_as_yyyy_mm_dd":"2026-08-11T00:00:00.000","open_interest_all":"400000","lev_money_positions_long_all":"70000","lev_money_positions_short_all":"130000"},
          {"report_date_as_yyyy_mm_dd":"2026-08-04T00:00:00.000","open_interest_all":"420000","lev_money_positions_long_all":"76000","lev_money_positions_short_all":"196000"}
        ]"""
        result = watch.parse_cftc_json(payload)
        self.assertEqual(result.net_short, 60000)
        self.assertEqual(result.previous_net_short, 120000)
        self.assertTrue(result.short_covering)
        self.assertAlmostEqual(result.net_short_pct_oi, 15.0)

    def test_realized_fx_vol_flags_current_block_vs_prior_blocks(self):
        points = []
        price = 160.0
        start = 1_800_000_000.0 - 60 * 3600
        for i in range(60 * 12 + 1):
            ts = start + i * 300
            hours_from_end = (1_800_000_000.0 - ts) / 3600
            bp = 4.0 if hours_from_end <= 12 else 1.0
            signed = bp if i % 2 == 0 else -bp
            price *= math.exp(signed / 10000.0)
            points.append((ts, price))
        result = watch.realized_fx_vol(points)
        self.assertIsNotNone(result.ratio)
        self.assertGreater(result.ratio, 1.5)
        self.assertTrue(result.elevated)

    def test_unwind_high_requires_combination_not_single_level(self):
        verdict = watch.classify(
            move=self.move(ch15=-0.6, ch30=-0.8, drawdown=-1.1, rebound=0.1),
            fx_vol=self.vol(ratio=1.8),
            jgb2=1.70,
            spread=1.90,
            previous_jgb2=1.62,
            previous_spread=2.10,
            cftc=self.cftc(),
            mof=self.mof(latest=-0.2, prior=0.1),
            policy=self.policy(),
        )
        self.assertEqual(verdict.unwind_level, 3)
        self.assertIn("높음", verdict.unwind_label)

    def test_short_covering_and_yen_weakness_can_signal_rebuild(self):
        verdict = watch.classify(
            move=self.move(ch15=0.20, ch30=0.30, ch60=0.55),
            fx_vol=self.vol(ratio=0.9),
            jgb2=1.70,
            spread=2.35,
            previous_jgb2=1.70,
            previous_spread=2.30,
            cftc=self.cftc(current_short=60000, previous_short=120000),
            mof=self.mof(latest=5.1, prior=-0.3),
            policy=self.policy(),
        )
        self.assertTrue(verdict.divergence_short_covering_but_yen_weak)
        self.assertGreaterEqual(verdict.rebuild_level, 2)
        self.assertEqual(verdict.unwind_level, 0)

    def test_jgb10_three_percent_is_not_an_input_or_automatic_trigger(self):
        verdict = watch.classify(
            move=self.move(),
            fx_vol=self.vol(ratio=1.0),
            jgb2=1.60,
            spread=2.40,
            previous_jgb2=1.60,
            previous_spread=2.40,
            cftc=None,
            mof=None,
            policy=None,
        )
        self.assertEqual(verdict.unwind_level, 0)

    def test_initial_baseline_does_not_send(self):
        pending = {"initialized": True, "source_dates": {"cftc": "2026-08-11", "mof_week": "w2"}}
        verdict = watch.CompositeVerdict(0, "엔캐리 청산 미확인", 2, "엔화 재약세·캐리 재구축 압력 강화", True, {})
        alert, reasons = watch.should_alert({}, pending, verdict)
        self.assertFalse(alert)
        self.assertEqual(reasons, ["최초 기준값 저장"])

    def test_new_structural_release_realerts_when_risk_active(self):
        previous = {
            "initialized": True,
            "unwind_level": 0,
            "unwind_label": "엔캐리 청산 미확인",
            "rebuild_level": 2,
            "rebuild_label": "엔화 재약세·캐리 재구축 압력 강화",
            "divergence_short_covering_but_yen_weak": True,
            "source_dates": {"cftc": "2026-08-04", "mof_week": "w1"},
        }
        pending = {"initialized": True, "source_dates": {"cftc": "2026-08-11", "mof_week": "w2"}}
        verdict = watch.CompositeVerdict(0, "엔캐리 청산 미확인", 2, "엔화 재약세·캐리 재구축 압력 강화", True, {})
        alert, reasons = watch.should_alert(previous, pending, verdict)
        self.assertTrue(alert)
        self.assertTrue(any("CFTC" in reason for reason in reasons))
        self.assertTrue(any("재무성" in reason for reason in reasons))


if __name__ == "__main__":
    unittest.main()
