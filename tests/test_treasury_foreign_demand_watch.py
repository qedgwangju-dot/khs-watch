import unittest

from scripts import treasury_foreign_demand_watch as watch


class TreasuryForeignDemandWatchTests(unittest.TestCase):
    def test_billions_are_rendered_in_korean_units(self):
        self.assertEqual(watch.fmt_bn(633.4), "6,334억달러")
        self.assertEqual(watch.fmt_bn(-25.9, signed=True), "-259억달러")
        self.assertEqual(watch.fmt_bn(1116.0), "1.116조달러")

    def test_parse_table5(self):
        text = """Table 5\nCountry\t2026-06\t2026-05\nJapan\t1116.0\t1143.1\nUnited Kingdom\t939.9\t948.6\nChina, Mainland\t633.4\t659.3\nGrand Total\t9299.0\t9371.1\nNotes:\n"""
        months, values = watch.parse_table5(text)
        self.assertEqual(months, ["2026-06", "2026-05"])
        self.assertEqual(values["China, Mainland"][0], 633.4)
        self.assertAlmostEqual(values["Grand Total"][0] - values["Grand Total"][1], -72.1)

    def test_parse_table3(self):
        text = """heading\nCountry\tCountry Code\tDate\tHoldings\tNet U.S. Sales\tHoldings\tNet U.S. Sales\tValuation Change\tHoldings\tNet U.S. Sales\ncountry\tcountry_code\tdate\tfor_treas_pos\tfor_treas_net\tfor_lt_treas_pos\tfor_lt_treas_net\tfor_lt_treas_valchg\tfor_st_treas_pos\tfor_st_treas_net\nJapan\t58801\t2026-06\t1116000\t-12000\t1000000\t-8000\t-9000\t116000\t-4000\n"""
        parsed = watch.parse_table3(text, "2026-06")
        self.assertEqual(parsed["Japan"]["net_mn"], -12000.0)
        self.assertEqual(parsed["Japan"]["lt_val_mn"], -9000.0)

    def test_classification_separates_holdings_from_sales(self):
        self.assertIn("순매도는 아님", watch.classify(-25.9, 3.0, -20.0))
        self.assertIn("동시에", watch.classify(-25.9, -12.0, -9.0))

    def test_parse_h41_sample(self):
        sample = """
        Wednesday Aug 12, 2026
        Marketable U.S. Treasury securities 1 2,791,600 + 8,500 - 241,000 2,800,000
        """
        result = watch.parse_h41(sample)
        self.assertIsNotNone(result)
        self.assertAlmostEqual(result["value_bn"], 2791.6)
        self.assertAlmostEqual(result["weekly_bn"], 8.5)
        self.assertAlmostEqual(result["yoy_bn"], -241.0)


if __name__ == "__main__":
    unittest.main()
