import pathlib
import sys
import unittest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "scripts"))
import nvidia_exec_signal_watch as w


class NvidiaExecCapitalReturnTests(unittest.TestCase):
    def sample_text(self):
        return (
            "NVIDIA today announced that its Board of Directors has authorized an additional "
            "$150 billion under the company's existing share repurchase program, increasing "
            "the total remaining amount authorized to $235 billion. "
            "The company expects to execute the total remaining program through fiscal year 2028."
        )

    def test_classify_buyback_as_capital_return(self):
        self.assertEqual(w.classify(self.sample_text()), "capital_return")

    def test_extract_current_buyback_numbers(self):
        cap = w.extract_capital_return(self.sample_text())
        self.assertEqual(cap["additional_authorization_usd_b"], 150.0)
        self.assertEqual(cap["remaining_authorization_usd_b"], 235.0)
        self.assertEqual(cap["execution_through_fy"], 2028)
        self.assertIsNone(cap["actual_repurchase_usd_b"])

    def test_authorization_is_not_misread_as_actual_repurchase(self):
        cap = w.extract_capital_return(self.sample_text())
        self.assertIsNone(cap["actual_repurchase_usd_b"])

    def test_fact_key_dedupes_same_buyback_numbers(self):
        a = w.fact_key("capital_return", self.sample_text())
        b = w.fact_key("capital_return", self.sample_text() + " NVIDIA confidence statement.")
        self.assertEqual(a, b)

    def test_different_authorization_gets_different_fact_key(self):
        a = w.fact_key("capital_return", self.sample_text())
        b = w.fact_key(
            "capital_return",
            "NVIDIA authorized an additional $160 billion and raised the total remaining amount to $245 billion through fiscal year 2028.",
        )
        self.assertNotEqual(a, b)

    def test_alert_explicitly_separates_authorization_and_execution(self):
        e = {
            "id": "x",
            "kind": "capital_return",
            "fact_key": w.fact_key("capital_return", self.sample_text()),
            "title": "NVIDIA share repurchase authorization increase",
            "description": self.sample_text(),
            "source": "NVIDIA Investor Relations",
            "published_at_kst": "2026-09-28T20:00:00+09:00",
            "direct_link": "https://investor.nvidia.com/",
            "rank": 100,
        }
        out = w.build_alert([e], w.datetime(2026, 9, 28, 20, 0, tzinfo=w.ZoneInfo("Asia/Seoul")))
        self.assertIn("$150 billion", out)
        self.assertIn("$235 billion", out)
        self.assertIn("FY28", out)
        self.assertIn("승인한도는 실제 매입 완료액이 아닙니다", out)
        self.assertIn("$99.3 billion", out)
        self.assertIn("$19.7 billion", out)
        self.assertIn("$39.8 billion", out)


if __name__ == "__main__":
    unittest.main()
