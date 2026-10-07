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
        self.assertTrue(parsed["valid"])
        self.assertEqual(parsed["action"], "인상")
        self.assertEqual(parsed["bp"], 25.0)
        self.assertEqual(parsed["deposit"], 2.50)
        self.assertEqual(parsed["previous_deposit"], 2.25)
        self.assertEqual(parsed["main_refi"], 2.65)
        self.assertEqual(parsed["marginal"], 2.90)

    def test_invalid_decision_fails_closed(self):
        parsed = watch.parse_decision("The Governing Council discussed monetary policy.")
        self.assertFalse(parsed["valid"])

    def test_statement_current_vs_risk_is_separated(self):
        text = """
        Because energy inflation did not rise as much as anticipated, we are not really seeing much of the indirect effects.
        Some are visible, but it is still contained. Second-round effects, we're not seeing.
        We are taking into account higher food prices in the future.
        If we continue to have this longer-than-anticipated energy shock, it would impact food prices.
        Gas prices could also increase if supply is disrupted.
        """
        parsed = watch.parse_statement(text)
        self.assertTrue(parsed["energy"])
        self.assertTrue(parsed["food"])
        self.assertTrue(parsed["indirect"])
        self.assertTrue(parsed["second_round"])
        self.assertTrue(parsed["indirect_contained"])
        self.assertTrue(parsed["second_round_not_seen"])
        self.assertTrue(parsed["food_future"])
        self.assertTrue(parsed["longer_energy"])
        self.assertTrue(parsed["gas"])

    def test_extract_official_links_from_index(self):
        html = """
        <a href="/press/pr/date/2026/html/ecb.mp260910~abc.en.html">Monetary policy decisions</a>
        <a href="/press/press_conference/monetary-policy-statement/2026/html/ecb.is260910~def.en.html">
          Monetary policy statement
        </a>
        """
        rows = watch.extract_official_links(html, "https://www.ecb.europa.eu/press/press_conference/html/index.en.html")
        self.assertEqual(len(rows), 2)
        self.assertEqual(rows[0]["kind"], "decision")
        self.assertEqual(rows[0]["date"], "2026-09-10")
        self.assertEqual(rows[1]["kind"], "statement")
        self.assertEqual(rows[1]["date"], "2026-09-10")

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
            "indirect_contained": True,
            "second_round_not_seen": True,
            "food_future": True,
            "longer_energy": True,
        }
        _, body, detail = watch.build_main_alert(item, decision, item, statement)
        self.assertIn("ECB는?", body)
        self.assertIn("21개국", body)
        self.assertIn("2.25% → 2.50%", body)
        self.assertIn("간접 파급은 아직 제한적", body)
        self.assertIn("2차 파급은 아직 관측되지 않았", body)
        self.assertIn("식료품 가격 상승 자체는 간접 파급", body)
        self.assertIn("시장에서 볼 것", body)
        self.assertIn("다음 확인", body)
        self.assertTrue(detail["signature"])

    def test_signature_is_deterministic(self):
        self.assertEqual(watch.signature({"b": 2, "a": 1}), watch.signature({"a": 1, "b": 2}))


if __name__ == "__main__":
    unittest.main()
