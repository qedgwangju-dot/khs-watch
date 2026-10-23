import pathlib
import sys
import unittest
from unittest.mock import patch

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "scripts"))
import samsung_hbm_watch as watch


def reference(month="202609", *, omit_region=None):
    amounts = {"44": "7840316096", "43": "2797935063"}
    rows = {
        "44": {"ROW_CODE": "31", "KOR_NAME": "충남"},
        "43": {"ROW_CODE": "36", "KOR_NAME": "충북"},
    }
    if omit_region:
        amounts.pop(omit_region, None)
        rows.pop(omit_region, None)
    return {
        "provider": "K-stat 한국무역협회", "month": month, "hs": watch.HBM_HSK10,
        "unit": "usd", "monthly_not_cumulative": True,
        "amounts_usd": amounts, "source_region_codes": {"44": "31", "43": "36"},
        "selected_rows": rows, "request_scope_no_response_echo": True,
        "source_sha256": {"form": "a" * 64, "sheet": "b" * 64},
        "evidence_attempt_ids": {"form": "form-attempt", "sheet": "sheet-attempt"},
        "identity_limit": "XML has no month/HS echo; month and HSK are the validated public request scope.",
    }


class RegionalUnitProbeCompletenessTests(unittest.TestCase):
    def test_duplicate_cause_is_kept_once_and_distinct_causes_remain(self):
        error = "지역 금액 단위 검증 보류: 지역 HSK10 확인 실패: 44: invalid:non_monthly_period | 43: invalid:non_monthly_period"
        distinct = "공공데이터포털 전국 API 202609 invalid:wrong_month"
        self.assertEqual(
            watch._dedupe_error_messages([error, error, distinct]),
            [error, distinct],
        )

    def test_kstat_source_proof_requires_both_exact_province_rows(self):
        with (
            patch.object(watch, "_SIDO_SOURCE_RESULT", None),
            patch.object(watch, "_SIDO_KSTAT_REFERENCE_CACHE", {}),
            patch.object(watch, "_load_kstat_sido_reference", return_value=(reference(), "")),
        ):
            proof, error = watch._resolve_sido_source("202609")

        self.assertEqual(error, "")
        self.assertEqual(proof["status"], "official_kstat_request_scoped_source")
        self.assertEqual(proof["unit"], "usd")
        self.assertEqual(proof["amounts_usd"], {"44": "7840316096", "43": "2797935063"})
        self.assertTrue(proof["request_scope_no_response_echo"])

    def test_missing_province_row_fails_closed(self):
        with (
            patch.object(watch, "_SIDO_SOURCE_RESULT", None),
            patch.object(watch, "_SIDO_KSTAT_REFERENCE_CACHE", {}),
            patch.object(watch, "_load_kstat_sido_reference",
                         return_value=(reference(omit_region="43"), "")),
        ):
            proof, error = watch._resolve_sido_source("202609")

        self.assertIsNone(proof)
        self.assertIn("원응답 계약 불일치", error)
        self.assertIsNone(watch._SIDO_SOURCE_RESULT)

    def test_missing_month_is_not_cached_against_an_older_available_month(self):
        with (
            patch.object(watch, "_SIDO_SOURCE_RESULT", None),
            patch.object(watch, "_SIDO_KSTAT_REFERENCE_CACHE", {}),
            patch.object(watch, "_load_kstat_sido_reference", side_effect=[
                (None, "invalid:kstat_reference_requested_month_unavailable"),
                (reference("202608"), ""),
            ]) as load,
        ):
            first, first_error = watch._resolve_sido_source("202609")
            second, second_error = watch._resolve_sido_source("202608")

        self.assertIsNone(first)
        self.assertIn("requested_month_unavailable", first_error)
        self.assertEqual(second_error, "")
        self.assertEqual(second["month"], "202608")
        self.assertEqual(load.call_count, 2)


if __name__ == "__main__":
    unittest.main()
