import copy
import pathlib
import sys
import unittest
from decimal import Decimal

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "scripts"))
import hbm_trade_unit_reference as ref

FIXTURES = pathlib.Path(__file__).parent / "fixtures"


class Response:
    def __init__(self, content, status=200):
        self.content = content
        self.status_code = status


class UnitReferenceTests(unittest.TestCase):
    def setUp(self):
        self.form = (FIXTURES / "hbm_kstat_province_form_20261016.html").read_bytes()
        self.sheet = (FIXTURES / "hbm_kstat_province_202608.xml").read_bytes()
        self.calls = []

    def fetch(self, form=None, sheet=None, target_month=None):
        def request(method, url, **kwargs):
            self.calls.append((method, url, kwargs))
            return Response((self.form if form is None else form) if method == "GET" else (self.sheet if sheet is None else sheet))
        return ref.fetch_reference(request, target_month=target_month)

    def rows(self, factor="1000"):
        pack, error = self.fetch()
        self.assertEqual(error, "")
        rows = [{"month": pack["month"], "hs": ref.HS, "region_code": code,
                 "raw_amount_field": "expUsdAmt", "raw_amount_decimal": str(Decimal(amount) / Decimal(factor))}
                for code, amount in pack["amounts_usd"].items()]
        return rows, pack

    def test_actual_public_usd_rows_and_only_latest_permitted_month(self):
        pack, error = self.fetch()
        self.assertEqual(error, "")
        self.assertEqual(pack["month"], "202608")
        self.assertEqual(pack["amounts_usd"], {"44": "7496336046", "43": "1404330188"})
        self.assertEqual(pack["source_region_codes"], {"44": "31", "43": "36"})
        self.assertTrue(pack["request_scope_no_response_echo"])
        self.assertEqual([x[:2] for x in self.calls], [("GET", ref.FORM_URL), ("POST", ref.SHEET_URL)])
        data = self.calls[1][2]["data"]
        for name, value in {"p_cond_in_gb": "2", "s_item_type": "HS", "s_item_value": ref.HS,
                            "s_year": "2026", "s_month": "08", "s_field": "AMT", "s_monthsum_gb": "1",
                            "s_measure": "1", "p_measure": "1"}.items():
            self.assertEqual(data[name], value)

    def test_explicit_target_month_is_sent_without_changing_identity_claim(self):
        pack, error = self.fetch(target_month="202607")
        self.assertEqual(error, "")
        self.assertEqual(pack["month"], "202607")
        self.assertTrue(pack["request_scope_no_response_echo"])
        self.assertIn("request scope", pack["identity_limit"])
        data = self.calls[1][2]["data"]
        self.assertEqual(data["s_year"], "2026")
        self.assertEqual(data["s_month"], "07")
        self.assertEqual(data["s_item_value"], ref.HS)

    def test_changed_selection_contract_or_columns_rejected_before_post(self):
        for old, new in ((b"US$, %", b"EUR, %"), (">당월<".encode(), ">누계<".encode()),
                         ('광역자치별'.encode(), '기초자치별'.encode()), (b'SaveName:"THIS_EXP_AMT"', b'SaveName:"OTHER"')):
            with self.subTest(old=old):
                self.calls.clear()
                self.assertIn(old, self.form)
                pack, error = self.fetch(form=self.form.replace(old, new))
                self.assertIsNone(pack)
                self.assertTrue(error.startswith("invalid:"))
                self.assertEqual(len(self.calls), 1)

    def test_missing_month_option_or_default_mismatch_rejected(self):
        for changed in (self.form.replace(b'value="08"', b'value="09"'),
                        self.form.replace(b"setSelect(f.s_month, '08')", b"setSelect(f.s_month, '09')")):
            pack, error = self.fetch(form=changed)
            self.assertIsNone(pack)
            self.assertTrue(error)

    def test_wrong_province_duplicate_zero_and_missing_rows_rejected(self):
        for old, new in ((b'<![CDATA[31]]>', b'<![CDATA[44]]>'),
                         (b'<![CDATA[7496336046]]>', b'<![CDATA[0]]>'),
                         ('<![CDATA[충북]]>'.encode(), '<![CDATA[충남]]>'.encode())):
            self.assertIn(old, self.sheet)
            pack, error = self.fetch(sheet=self.sheet.replace(old, new))
            self.assertIsNone(pack)
            self.assertTrue(error)
        import xml.etree.ElementTree as ET
        root = ET.fromstring(self.sheet.lstrip())
        data = root.find("DATA")
        target = next(row for row in data if any(td.text == "충남" for td in row))
        data.append(copy.deepcopy(target))
        self.assertIsNone(self.fetch(sheet=ET.tostring(root))[0])
        root = ET.fromstring(self.sheet.lstrip())
        data = root.find("DATA")
        data.remove(next(row for row in data if any(td.text == "충북" for td in row)))
        self.assertIsNone(self.fetch(sheet=ET.tostring(root))[0])

    def test_entity_and_http_error_rejected(self):
        self.assertIsNone(self.fetch(sheet=b'<!DOCTYPE x><SHEET><DATA/></SHEET>')[0])
        pack, error = ref.fetch_reference(lambda *a, **k: Response(self.form, 403))
        self.assertIsNone(pack)
        self.assertTrue(error.startswith("invalid:"))

    def test_unique_thousand_and_plain_usd_factors(self):
        for factor, unit in (("1000", "thousand_usd"), ("1", "usd")):
            rows, pack = self.rows(factor)
            proof, error = ref.reconcile_unit(rows, pack)
            self.assertEqual(error, "")
            self.assertEqual(proof["factor_to_usd"], factor)
            self.assertEqual(proof["unit"], unit)
            self.assertTrue(all(Decimal(x["absolute_difference_usd"]) == 0 for x in proof["comparisons"].values()))
            self.assertEqual(ref.reconcile_unit({row["region_code"]: row for row in rows}, pack)[0], proof)

    def test_different_province_factors_do_not_establish_shared_contract(self):
        rows, pack = self.rows()
        rows[1]["raw_amount_decimal"] = pack["amounts_usd"][rows[1]["region_code"]]
        self.assertEqual(ref.reconcile_unit(rows, pack)[1], "invalid:unit_cross_provider_mismatch")

    def test_request_exceptions_do_not_disclose_url_or_key(self):
        for exception in (ValueError, RuntimeError):
            def request(*args, **kwargs):
                raise exception("https://example.invalid/?serviceKey=offline-secret-fixture")
            pack, error = ref.fetch_reference(request)
            self.assertIsNone(pack)
            self.assertNotIn("serviceKey", error)
            self.assertNotIn("offline-secret-fixture", error)

    def test_thousand_dollar_rounding_tolerance_is_bounded(self):
        rows, pack = self.rows()
        rows[0]["raw_amount_decimal"] = str(Decimal(rows[0]["raw_amount_decimal"]) + 1)
        self.assertIsNotNone(ref.reconcile_unit(rows, pack)[0])
        rows[0]["raw_amount_decimal"] = str(Decimal(rows[0]["raw_amount_decimal"]) + Decimal("0.001"))
        self.assertEqual(ref.reconcile_unit(rows, pack)[1], "invalid:unit_cross_provider_mismatch")

    def test_bad_or_incompatible_api_rows_never_establish_unit(self):
        mutations = (
            ("month", "202609"), ("hs", "854232"), ("region_code", "41"),
            ("raw_amount_field", "expDlr"), ("raw_amount_decimal", "0"),
            ("raw_amount_decimal", "NaN"), ("raw_amount_decimal", "Infinity"),
            ("raw_amount_decimal", "-1"), ("raw_amount_decimal", "125.0"),
        )
        for field, value in mutations:
            rows, pack = self.rows()
            rows[0][field] = value
            with self.subTest(field=field, value=value):
                self.assertIsNone(ref.reconcile_unit(rows, pack)[0])
        rows, pack = self.rows()
        self.assertIsNone(ref.reconcile_unit([rows[0], rows[0]], pack)[0])
        self.assertIsNone(ref.reconcile_unit(rows[:1], pack)[0])
        rows[0].pop("month")
        self.assertIsNone(ref.reconcile_unit(rows, pack)[0])

    def test_ambiguous_small_numbers_are_not_scale_estimates(self):
        rows, pack = self.rows()
        for row in rows:
            row["raw_amount_decimal"] = "1"
            pack["amounts_usd"][row["region_code"]] = "1"
        self.assertEqual(ref.reconcile_unit(rows, pack)[1], "invalid:unit_factor_not_unique")

    def test_no_cross_month_copy_and_no_false_echo_promotion(self):
        rows, pack = self.rows()
        before = copy.deepcopy(pack)
        proof, error = ref.reconcile_unit(rows, pack)
        self.assertEqual(error, "")
        self.assertEqual(pack, before)
        self.assertNotIn("amount_usd", proof)
        self.assertEqual(proof["month"], "202608")
        self.assertTrue(proof["request_scope_no_response_echo"])
        pack["request_scope_no_response_echo"] = False
        self.assertIsNone(ref.reconcile_unit(rows, pack)[0])


if __name__ == "__main__":
    unittest.main()
