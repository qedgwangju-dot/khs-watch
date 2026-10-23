import pathlib
import sys
import unittest
from unittest.mock import patch

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "scripts"))
import samsung_hbm_watch as watch


class RegionalUnitProbeCompletenessTests(unittest.TestCase):
    def test_second_province_is_checked_after_first_request_fails_closed(self):
        calls = []

        class Response:
            def __init__(self, attempt_id):
                self._hbm_trade_attempt_id = attempt_id

        def fetch_sido(month, code):
            calls.append((month, code))
            if code == "44":
                return None, [], "ConnectTimeout"
            return Response("43"), [{"raw": "fixture"}], ""

        def select_row(rows, month, hs, **kwargs):
            return {"raw_amount_decimal": "2"}, ""

        with (
            patch.object(watch, "_SIDO_UNIT_RESULT", None),
            patch.object(watch, "_TRADE_EVIDENCE", None),
            patch.object(watch, "fetch_reference", return_value=({"month": "202609"}, "")),
            patch.object(watch, "_fetch_data_go_sido_raw", side_effect=fetch_sido),
            patch.object(watch, "choose_exact_row", side_effect=select_row),
            patch.object(watch, "reconcile_unit") as reconcile,
        ):
            proof, error = watch._resolve_sido_unit()

        self.assertEqual(calls, [("202609", "44"), ("202609", "43")])
        self.assertIsNone(proof)
        self.assertIn("44: ConnectTimeout", error)
        self.assertFalse(reconcile.called)

    def test_unit_proof_requires_both_successful_exact_province_rows(self):
        calls = []

        class Response:
            def __init__(self, attempt_id):
                self._hbm_trade_attempt_id = attempt_id

        def fetch_sido(month, code):
            calls.append((month, code))
            return Response(code), [{"raw": code}], ""

        def select_row(rows, month, hs, **kwargs):
            return {"region": kwargs["region"], "amount": rows[0]["raw"]}, ""

        expected_proof = {"unit": "thousand_usd", "factor_to_usd": "1000"}
        with (
            patch.object(watch, "_SIDO_UNIT_RESULT", None),
            patch.object(watch, "_TRADE_EVIDENCE", None),
            patch.object(watch, "fetch_reference", return_value=({"month": "202609"}, "")),
            patch.object(watch, "_fetch_data_go_sido_raw", side_effect=fetch_sido),
            patch.object(watch, "choose_exact_row", side_effect=select_row),
            patch.object(watch, "reconcile_unit", return_value=(expected_proof.copy(), "")) as reconcile,
        ):
            proof, error = watch._resolve_sido_unit()

        self.assertEqual(calls, [("202609", "44"), ("202609", "43")])
        self.assertEqual(error, "")
        self.assertEqual(proof["unit"], "thousand_usd")
        self.assertEqual(proof["api_attempt_ids"], {"44": "44", "43": "43"})
        reconcile.assert_called_once()
        self.assertEqual(set(reconcile.call_args.args[0]), {"44", "43"})


if __name__ == "__main__":
    unittest.main()
