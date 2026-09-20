from __future__ import annotations

import datetime as dt
import pathlib
import sys
import unittest
from zoneinfo import ZoneInfo

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import yen_carry_policy_reaction_watch as watch  # noqa: E402

KST = ZoneInfo("Asia/Seoul")


def composite(*, fed=3.875, boj=1.25, px=154.0, eligible=True, spread=2.80,
              updated="2026-10-30T11:45:00+09:00", real_gap=1.10, real_change=-0.25):
    return {
        "initialized": True,
        "updated_at_kst": updated,
        "fx_signal_eligible": eligible,
        "values": {"usdjpy": px, "us_jp_2y_spread": spread},
        "real_rate_overlay": {
            "available": True,
            "inputs": {"fed_midpoint": fed, "boj_policy_rate": boj},
            "metrics": {
                "us_jp_real_gap": real_gap,
                "real_gap_change_pp": real_change,
                "real_rate_direction": "엔화 강세 방향" if real_change <= -0.10 else "중립",
                "market_rate_direction": "중립",
                "signal_alignment": "확인 대기",
            },
        },
    }


class PolicyReactionTests(unittest.TestCase):
    def test_first_run_is_baseline_only(self):
        now = dt.datetime(2026, 10, 30, 12, 0, tzinfo=KST)
        state, title, body = watch.evaluate({}, {}, composite(), now)
        self.assertTrue(state["initialized"])
        self.assertIsNone(state["active_event"])
        self.assertIsNone(title)
        self.assertIsNone(body)

    def test_boj_hike_arms_six_hour_watch_without_duplicate_decision_alert(self):
        now = dt.datetime(2026, 10, 30, 12, 0, tzinfo=KST)
        previous = {
            "initialized": True,
            "last_policy_rates": {"fed_midpoint": 3.875, "boj_policy_rate": 1.25},
            "recent_policy_events": [],
            "active_event": None,
        }
        prev_comp = composite(boj=1.25, px=154.0)
        cur_comp = composite(boj=1.50, px=154.05)
        state, title, body = watch.evaluate(previous, prev_comp, cur_comp, now)
        self.assertTrue(state["new_boj_hike_detected"])
        self.assertIsNotNone(state["active_event"])
        self.assertEqual(state["active_event"]["baseline_usdjpy"], 154.0)
        self.assertIsNone(title)
        self.assertIsNone(body)

    def test_plus_075_percent_yen_weakness_triggers_warning(self):
        start = dt.datetime(2026, 10, 30, 12, 0, tzinfo=KST)
        active = watch.arm_boj_event(
            old_rate=1.25,
            new_rate=1.50,
            delta=0.25,
            previous_composite=composite(boj=1.25, px=154.0),
            current_composite=composite(boj=1.50, px=154.0),
            now=start,
        )
        previous = {
            "initialized": True,
            "last_policy_rates": {"fed_midpoint": 3.875, "boj_policy_rate": 1.50},
            "recent_policy_events": [
                {"bank": "BOJ", "delta_pp": 0.25, "detected_at_kst": start.isoformat()}
            ],
            "active_event": active,
        }
        now = start + dt.timedelta(minutes=60)
        current = composite(boj=1.50, px=155.25)
        state, title, body = watch.evaluate(previous, composite(boj=1.50, px=154.0), current, now)
        self.assertIn("정책 효과 불발 경계", title)
        self.assertIn("신호 충돌: 예", body)
        self.assertEqual(state["active_event"]["max_opposite_level_sent"], 1)

    def test_fed_and_boj_equal_hikes_are_classified_as_relative_offset(self):
        start = dt.datetime(2026, 10, 30, 12, 0, tzinfo=KST)
        events = [
            {
                "bank": "Fed",
                "delta_pp": 0.25,
                "detected_at_kst": (start - dt.timedelta(days=2)).isoformat(),
            },
            {
                "bank": "BOJ",
                "delta_pp": 0.25,
                "detected_at_kst": start.isoformat(),
            },
        ]
        fed, boj, net = watch.relative_policy_change(events)
        self.assertAlmostEqual(fed, 0.25)
        self.assertAlmostEqual(boj, 0.25)
        self.assertAlmostEqual(net, 0.0)
        self.assertIn("상쇄", watch.relative_policy_label(net))

    def test_six_hour_yen_strength_gets_final_confirmation(self):
        start = dt.datetime(2026, 10, 30, 12, 0, tzinfo=KST)
        active = watch.arm_boj_event(
            old_rate=1.25,
            new_rate=1.50,
            delta=0.25,
            previous_composite=composite(boj=1.25, px=154.0),
            current_composite=composite(boj=1.50, px=154.0),
            now=start,
        )
        previous = {
            "initialized": True,
            "last_policy_rates": {"fed_midpoint": 3.875, "boj_policy_rate": 1.50},
            "recent_policy_events": [
                {"bank": "BOJ", "delta_pp": 0.25, "detected_at_kst": start.isoformat()}
            ],
            "active_event": active,
        }
        now = start + dt.timedelta(minutes=361)
        current = composite(boj=1.50, px=153.0)
        state, title, body = watch.evaluate(previous, composite(boj=1.50, px=154.0), current, now)
        self.assertIn("정책 효과 확인", title)
        self.assertIn("엔화 강세 반응", body)
        self.assertTrue(state["active_event"]["final_sent"])

    def test_stale_fx_never_creates_false_reaction_alert(self):
        start = dt.datetime(2026, 10, 30, 12, 0, tzinfo=KST)
        active = watch.arm_boj_event(
            old_rate=1.25,
            new_rate=1.50,
            delta=0.25,
            previous_composite=composite(boj=1.25, px=154.0, eligible=False),
            current_composite=composite(boj=1.50, px=154.0, eligible=False),
            now=start,
        )
        previous = {
            "initialized": True,
            "last_policy_rates": {"fed_midpoint": 3.875, "boj_policy_rate": 1.50},
            "recent_policy_events": [],
            "active_event": active,
        }
        now = start + dt.timedelta(minutes=120)
        current = composite(boj=1.50, px=160.0, eligible=False)
        state, title, body = watch.evaluate(previous, {}, current, now)
        self.assertIsNone(title)
        self.assertIsNone(body)
        self.assertIsNone(state["reaction_snapshot"]["reaction_pct"])


if __name__ == "__main__":
    unittest.main()
