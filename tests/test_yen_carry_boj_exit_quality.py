from __future__ import annotations

import pathlib
import sys
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import yen_carry_boj_exit_quality as exitq  # noqa: E402


class BojExitQualityTests(unittest.TestCase):
    def test_planned_monthly_purchase_schedule(self):
        self.assertEqual(exitq.planned_monthly_purchase("202606"), 2.7)
        self.assertEqual(exitq.planned_monthly_purchase("202608"), 2.5)
        self.assertEqual(exitq.planned_monthly_purchase("202611"), 2.3)
        self.assertEqual(exitq.planned_monthly_purchase("202702"), 2.1)
        self.assertEqual(exitq.planned_monthly_purchase("202704"), 2.0)

    def test_account_release_parser(self):
        html = """
        <table>
          <tr><td>Japanese government securities</td><td>520,302,562,290</td></tr>
          <tr><td>Total</td><td>641,281,336,654</td></tr>
        </table>
        """
        parser = exitq.TableParser()
        parser.feed(html)
        self.assertEqual(parser.rows[0][0], "Japanese government securities")

    def test_md09_series_prefers_flow_series(self):
        rows = [
            {
                "SERIES_CODE": "STOCK",
                "NAME_OF_TIME_SERIES": "Japanese Government Bonds / Outright Purchases / Amount Outstanding",
                "CATEGORY": "Stock Table",
                "FREQUENCY": "MONTHLY",
            },
            {
                "SERIES_CODE": "FLOW",
                "NAME_OF_TIME_SERIES": "Japanese Government Bonds / Outright Purchases",
                "CATEGORY": "Flow Table / During Month",
                "FREQUENCY": "MONTHLY",
            },
        ]
        chosen = exitq.choose_md09_purchase_series(rows)
        self.assertEqual(chosen["SERIES_CODE"], "FLOW")

    def test_exit_alert_on_actual_purchase_overshoot(self):
        previous = {"initialized": True, "signals": {}}
        purchase = {
            "planned_trillion_yen": 2.5,
            "actual_trillion_yen": 3.2,
        }
        classification, reasons = exitq.classify(
            previous,
            account=None,
            purchase=purchase,
            absorption=None,
            plan={"newer_than_baseline": []},
            emergency={"recent_30d": []},
            stress={"joint_market_stress": False},
        )
        self.assertTrue(classification["signals"]["actual_over_plan"])
        self.assertEqual(classification["level"], 2)
        self.assertTrue(any("실제 매입" in reason for reason in reasons))

    def test_exit_alert_on_plan_revision_is_red(self):
        previous = {"initialized": True, "signals": {}}
        classification, reasons = exitq.classify(
            previous,
            account=None,
            purchase=None,
            absorption=None,
            plan={"newer_than_baseline": [{"date": "2026-10-30"}]},
            emergency={"recent_30d": []},
            stress={"joint_market_stress": False},
        )
        self.assertEqual(classification["level"], 3)
        self.assertTrue(classification["signals"]["plan_revision"])
        self.assertTrue(reasons)

    def test_weak_private_absorption_is_yellow(self):
        previous = {"initialized": True, "signals": {}}
        absorption = {
            "private_absorption_ratio": 0.35,
            "boj_change_same_quarter_trillion_yen": -10.0,
        }
        classification, reasons = exitq.classify(
            previous,
            account=None,
            purchase=None,
            absorption=absorption,
            plan={"newer_than_baseline": []},
            emergency={"recent_30d": []},
            stress={"joint_market_stress": False},
        )
        self.assertEqual(classification["level"], 1)
        self.assertTrue(classification["signals"]["weak_private_absorption"])
        self.assertTrue(reasons)

    def test_no_duplicate_reason_when_signal_already_active(self):
        previous = {
            "initialized": True,
            "signals": {
                "plan_revision": False,
                "emergency_purchase_signal": False,
                "actual_over_plan": True,
                "weak_private_absorption": False,
                "joint_market_stress": False,
            }
        }
        classification, reasons = exitq.classify(
            previous,
            account=None,
            purchase={"planned_trillion_yen": 2.5, "actual_trillion_yen": 3.2},
            absorption=None,
            plan={"newer_than_baseline": []},
            emergency={"recent_30d": []},
            stress={"joint_market_stress": False},
        )
        self.assertTrue(classification["signals"]["actual_over_plan"])
        self.assertEqual(reasons, [])

    def test_first_run_baselines_without_alert_reason(self):
        classification, reasons = exitq.classify(
            {},
            account=None,
            purchase={"planned_trillion_yen": 2.5, "actual_trillion_yen": 3.2},
            absorption=None,
            plan={"newer_than_baseline": []},
            emergency={"recent_30d": []},
            stress={"joint_market_stress": False},
        )
        self.assertTrue(classification["signals"]["actual_over_plan"])
        self.assertEqual(reasons, [])


if __name__ == "__main__":
    unittest.main()
