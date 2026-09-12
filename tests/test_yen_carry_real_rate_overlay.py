from __future__ import annotations

import json
import pathlib
import sys
import unittest

# Operational live-path recheck; no functional change.
ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import yen_carry_real_rate_overlay as overlay  # noqa: E402


def inputs(*, fed=3.625, us_cpi=3.4, boj=1.0, jp_cpi=1.9, us_period="2026-08", jp_period="2026-07"):
    return overlay.RealRateInputs(
        fed_lower=fed - 0.125,
        fed_upper=fed + 0.125,
        fed_midpoint=fed,
        fed_observation_date="2026-09-12",
        us_cpi_yoy=us_cpi,
        us_cpi_period=us_period,
        boj_policy_rate=boj,
        boj_effective_date="2026-06-17",
        jp_cpi_yoy=jp_cpi,
        jp_cpi_period=jp_period,
    )


def composite_state(*, spread=2.40, real_overlay=None):
    state = {
        "initialized": True,
        "values": {"us_jp_2y_spread": spread},
        "unwind_level": 0,
        "unwind_label": "엔캐리 청산 미확인",
        "rebuild_level": 0,
        "rebuild_label": "엔화 재약세·캐리 재구축 미확인",
    }
    if real_overlay is not None:
        state["real_rate_overlay"] = real_overlay
    return state


class YenCarryRealRateOverlayTests(unittest.TestCase):
    def test_parse_fred_latest_csv(self):
        text = "DATE,DFEDTARU\n2026-09-10,3.75\n2026-09-11,3.75\n"
        self.assertEqual(overlay.parse_fred_latest_csv(text), ("2026-09-11", 3.75))

    def test_parse_bls_cpi_api_computes_latest_yoy(self):
        payload = {
            "status": "REQUEST_SUCCEEDED",
            "Results": {
                "series": [{
                    "seriesID": "CUUR0000SA0",
                    "data": [
                        {"year": "2026", "period": "M08", "value": "340.000"},
                        {"year": "2025", "period": "M08", "value": "328.846"},
                    ],
                }]
            },
        }
        period, yoy = overlay.parse_bls_cpi_api(json.dumps(payload))
        self.assertEqual(period, "2026-08")
        self.assertAlmostEqual(yoy, 3.3919, places=3)

    def test_parse_boj_home_policy_guideline(self):
        text = """
        <div>Interest Rate Applied to the Complementary Deposit Facility 1.0% since June 17, 2026</div>
        <h3>Guideline</h3><p>The Bank will encourage the uncollateralized overnight call rate
        to remain at around 1.0 percent.</p>
        """
        rate, effective = overlay.parse_boj_policy_home(text)
        self.assertEqual(rate, 1.0)
        self.assertEqual(effective, "2026-06-17")

    def test_parse_japan_cpi_page_uses_all_items(self):
        text = """
        <h1>2025年基準 消費者物価指数 全国 2026年（令和8年）7月分</h1>
        <p>(1) 総合指数は2025年を100として102.0 前年同月比は1.9%の上昇</p>
        <p>(2) 生鮮食品を除く総合指数 前年同月比は1.8%の上昇</p>
        """
        period, yoy = overlay.parse_japan_cpi_page(text)
        self.assertEqual(period, "2026-07")
        self.assertEqual(yoy, 1.9)

    def test_current_example_is_us_real_rate_advantage(self):
        previous = composite_state(spread=2.40)
        pending = composite_state(spread=2.40)
        context = overlay.classify(previous, pending, inputs())
        metrics = context["metrics"]
        self.assertAlmostEqual(metrics["us_real_policy_rate"], 0.225, places=3)
        self.assertAlmostEqual(metrics["jp_real_policy_rate"], -0.9, places=3)
        self.assertAlmostEqual(metrics["us_jp_real_gap"], 1.125, places=3)
        self.assertIn("엔화 구조적 약세", metrics["structural_bias"])

    def test_gap_narrowing_and_market_narrowing_are_aligned(self):
        old_inputs = inputs(fed=3.625, us_cpi=3.4, boj=1.0, jp_cpi=1.9)
        base = overlay.classify(composite_state(), composite_state(), old_inputs)
        previous = composite_state(spread=2.40, real_overlay=base)
        # BOJ +25bp with CPI unchanged narrows the real and nominal policy gaps by 25bp.
        pending = composite_state(spread=2.25)
        current = overlay.classify(previous, pending, inputs(boj=1.25))
        metrics = current["metrics"]
        self.assertAlmostEqual(metrics["real_gap_change_pp"], -0.25, places=6)
        self.assertAlmostEqual(metrics["policy_gap_change_pp"], -0.25, places=6)
        self.assertEqual(metrics["real_rate_direction"], "엔화 강세 방향")
        self.assertEqual(metrics["market_rate_direction"], "엔화 강세 방향")
        self.assertEqual(metrics["signal_alignment"], "일치")
        reasons = overlay.alert_reasons(previous, current)
        self.assertTrue(any("실질정책금리 갭" in item for item in reasons))
        self.assertTrue(any("명목 정책금리 격차" in item for item in reasons))

    def test_same_policy_move_fed_and_boj_does_not_create_relative_policy_alert(self):
        old = overlay.classify(composite_state(), composite_state(), inputs(fed=3.625, boj=1.0))
        previous = composite_state(spread=2.40, real_overlay=old)
        pending = composite_state(spread=2.40)
        current = overlay.classify(previous, pending, inputs(fed=3.875, boj=1.25))
        self.assertAlmostEqual(current["metrics"]["policy_gap_change_pp"], 0.0, places=6)
        reasons = overlay.alert_reasons(previous, current)
        self.assertFalse(any("명목 정책금리 격차" in item for item in reasons))

    def test_real_rate_and_market_rate_opposite_direction_flag_conflict(self):
        old = overlay.classify(composite_state(), composite_state(), inputs())
        previous = composite_state(spread=2.40, real_overlay=old)
        # BOJ hikes (real gap narrows), while the market 2Y spread widens 15bp.
        pending = composite_state(spread=2.55)
        current = overlay.classify(previous, pending, inputs(boj=1.25))
        self.assertEqual(current["metrics"]["real_rate_direction"], "엔화 강세 방향")
        self.assertEqual(current["metrics"]["market_rate_direction"], "엔화 약세 방향")
        self.assertEqual(current["metrics"]["signal_alignment"], "충돌")
        self.assertTrue(any("서로 반대" in item for item in overlay.alert_reasons(previous, current)))

    def test_market_move_alone_never_triggers_real_rate_overlay(self):
        old = overlay.classify(composite_state(), composite_state(), inputs())
        previous = composite_state(spread=2.40, real_overlay=old)
        pending = composite_state(spread=2.20)
        current = overlay.classify(previous, pending, inputs())
        self.assertFalse(current["metrics"]["official_event_changed"])
        self.assertEqual(overlay.alert_reasons(previous, current), [])


if __name__ == "__main__":
    unittest.main()
