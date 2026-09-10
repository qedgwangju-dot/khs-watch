import unittest

from scripts import ecb_policy_watch as watch


class ECBPolicyWatchTests(unittest.TestCase):
    def test_parse_decision_hike_and_rates(self):
        text = """
        The Governing Council today decided to raise the three key ECB interest rates by 25 basis points.
        The interest rates on the deposit facility, the main refinancing operations and the marginal lending facility
        will be increased to 2.50%, 2.65% and 2.90% respectively.
        The conflict in the Middle East continues to generate inflation pressures.
        """
        parsed = watch.parse_decision(text)
        self.assertEqual(parsed["action"], "인상")
        self.assertEqual(parsed["bp"], 25.0)
        self.assertEqual(parsed["deposit"], 2.50)
        self.assertEqual(parsed["previous_deposit"], 2.25)
        self.assertEqual(parsed["main_refi"], 2.65)
        self.assertEqual(parsed["marginal"], 2.90)

    def test_statement_separates_indirect_and_second_round(self):
        text = """
        The duration of the energy shock matters. Higher energy costs can feed into food prices.
        We monitor indirect and second-round effects, wage growth and inflation expectations. Gas prices also matter.
        """
        parsed = watch.parse_statement(text)
        self.assertTrue(parsed["energy"])
        self.assertTrue(parsed["food"])
        self.assertTrue(parsed["indirect"])
        self.assertTrue(parsed["second_round"])
        self.assertTrue(parsed["wages"])
        self.assertTrue(parsed["expectations"])
        self.assertTrue(parsed["gas"])

    def test_alert_is_readable_and_explains_ecb(self):
        item = {"date": "2026-09-10", "link": "https://www.ecb.europa.eu/example"}
        decision = {
            "action": "인상",
            "bp": 25.0,
            "deposit": 2.50,
            "previous_deposit": 2.25,
            "main_refi": 2.65,
            "marginal": 2.90,
            "headline_projection": [("2026", 3.0), ("2027", 2.5), ("2028", 2.1)],
            "core_projection": [],
            "mentions_middle_east": True,
            "mentions_energy": True,
            "mentions_above_target": True,
        }
        statement = {
            "duration": True,
            "energy": True,
            "food": True,
            "indirect": True,
            "second_round": True,
            "wages": True,
            "expectations": True,
            "gas": True,
            "fertil": True,
            "transport": True,
        }
        _, body, _ = watch.build_main_alert(item, decision, item, statement)
        self.assertIn("ECB는?", body)
        self.assertIn("유럽중앙은행", body)
        self.assertIn("2.25% → 2.50%", body)
        self.assertIn("간접 파급", body)
        self.assertIn("2차 파급", body)
        self.assertIn("시장에서 볼 것", body)
        self.assertIn("다음 확인", body)


if __name__ == "__main__":
    unittest.main()
