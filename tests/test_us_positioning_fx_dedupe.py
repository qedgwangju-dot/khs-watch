"""Do not report transient ECOS collection failures as new market data."""

import copy
import unittest

import test_us_positioning_amounts as amount_tests
import test_us_positioning_presentation as integration_tests
from us_positioning_fx import collect_fx, parse_ecos_usdkrw


class OfflineReader:
    def get(self, *args, **kwargs):
        raise TimeoutError("offline")


class FxCollectionDedupeTests(unittest.TestCase):
    def setUp(self):
        self.values, self.context = amount_tests.AmountRenderingTests().sources()
        self.context["amounts"]["nq_reference"] = amount_tests.amounts.reference_price(
            [("2026-10-06", 30000)], [("2026-10-06", 30000)], "2026-10-06"
        )

    def run_tail(self, context, prior=None):
        return integration_tests.OperatingIntegrationTests.run_operating_tail(self, self.values, prior, context)

    def unavailable(self, value):
        return collect_fx(OfflineReader(), value["requested_date"])

    def revised(self, value):
        operands = copy.deepcopy(value["operands"])
        row = operands["StatisticSearch"]["row"][0]
        row["DATA_VALUE"] = str(float(row["DATA_VALUE"]) + 1)
        result = parse_ecos_usdkrw(operands, value["requested_date"])
        self.assertEqual(result["status"], "verified")
        return result

    def test_same_date_collection_failure_and_recovery_are_quiet(self):
        first = self.run_tail(self.context)
        missing = copy.deepcopy(self.context)
        for field in ("fx", "nq_fx"):
            missing["amounts"][field] = self.unavailable(self.context["amounts"][field])
        failed = self.run_tail(missing, first["pending"])
        self.assertIsNone(failed["alert"])
        self.assertIsNone(failed["pending"])
        self.assertIn("context_transient_fx_only_change: True", failed["status"])
        recovered = self.run_tail(self.context, first["pending"])
        self.assertIsNone(recovered["alert"])

    def test_real_change_during_outage_is_sent_without_reusing_old_fx(self):
        first = self.run_tail(self.context)
        changed = copy.deepcopy(self.context)
        changed["amounts"]["fx"] = self.revised(changed["amounts"]["fx"])
        changed["amounts"]["nq_fx"] = self.unavailable(changed["amounts"]["nq_fx"])
        result = self.run_tail(changed, first["pending"])
        self.assertEqual(result["updates"], 1)
        self.assertIsNotNone(result["alert"])
        self.assertIn("원화 환산 보류", result["alert"])
        self.assertEqual(result["pending"]["last_verified_context_fx"]["nq_fx"], self.context["amounts"]["nq_fx"])
        stored_context = result["pending"]["values"]["미국 주요지수·시장 확산·옵션 과거 비교|context"]["metrics"]
        self.assertEqual(stored_context["amounts"]["nq_fx"]["status"], "unavailable")

        recovered = copy.deepcopy(changed)
        recovered["amounts"]["nq_fx"] = self.context["amounts"]["nq_fx"]
        self.assertIsNone(self.run_tail(recovered, result["pending"])["alert"])
        recovered["amounts"]["nq_fx"] = self.revised(recovered["amounts"]["nq_fx"])
        correction = self.run_tail(recovered, result["pending"])
        self.assertEqual(correction["updates"], 1)
        self.assertIsNotNone(correction["alert"])

    def test_different_target_date_or_missing_baseline_is_not_hidden(self):
        first = self.run_tail(self.context)
        missing = copy.deepcopy(self.context)
        missing["amounts"]["fx"] = self.unavailable(self.context["amounts"]["fx"])
        missing["amounts"]["fx"]["requested_date"] = "2026-10-15"
        self.assertIsNotNone(self.run_tail(missing, first["pending"])["alert"])

        # A legacy unavailable state has no verified baseline to compare to.
        unavailable_first = copy.deepcopy(self.context)
        unavailable_first["amounts"]["fx"] = self.unavailable(self.context["amounts"]["fx"])
        legacy = self.run_tail(unavailable_first)["pending"]
        legacy.pop("last_verified_context_fx", None)
        self.assertIsNotNone(self.run_tail(self.context, legacy)["alert"])


if __name__ == "__main__":
    unittest.main()
