#!/usr/bin/env python3
import importlib.util
import pathlib
import sys
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]
MODULE_PATH = ROOT / "scripts" / "apple_kparts_margin_watch.py"
spec = importlib.util.spec_from_file_location("apple_kparts_margin_watch", MODULE_PATH)
m = importlib.util.module_from_spec(spec)
assert spec and spec.loader
spec.loader.exec_module(m)


class AppleKPartsMarginWatchTests(unittest.TestCase):
    def test_baseline_revisions(self):
        self.assertAlmostEqual(m.BASELINE["lg_display_revision_pct"], -40.1, places=1)
        self.assertAlmostEqual(m.BASELINE["lg_innotek_revision_pct"], -51.8, places=1)

    def test_fx_buckets(self):
        self.assertEqual(m._fx_bucket(-2.9), "normal")
        self.assertEqual(m._fx_bucket(-3.1), "yellow")
        self.assertEqual(m._fx_bucket(-5.1), "orange")

    def test_lginnotek_explicit_revision(self):
        blob = (
            "LG이노텍 3분기 영업이익은 1501억원으로 전망했다. "
            "기존 추정치 대비 영업이익을 53.6% 하향 조정했다."
        )
        rows = m._extract_revision(blob)
        self.assertTrue(any(r["company"] == "LG이노텍" and r["revision_pct"] == -53.6 for r in rows))

    def test_semco_plus9_is_not_alert_threshold(self):
        blob = (
            "삼성전기 3분기 영업이익 6500억원으로 시장 컨센서스와 기존 추정치를 약 9% 상회한다."
        )
        rows = m._extract_revision(blob)
        self.assertTrue(any(r["company"] == "삼성전기" and r["revision_pct"] == 9.0 for r in rows))
        self.assertEqual(m._revision_stage(9.0), 0)

    def test_anonymous_north_american_customer_not_relabeled_apple(self):
        blob = "삼성디스플레이는 북미 고객 중심의 판가 인하 압박을 받았다."
        result = m._extract_pricing_pressure(blob)
        self.assertIsNotNone(result)
        self.assertFalse(result["named_customer"])
        self.assertEqual(result["customer"], "북미 고객(실명 미확인)")

    def test_price_pressure_requires_customer_context(self):
        blob = "LG디스플레이는 일반적인 판가 인하 압박을 받고 있다."
        self.assertIsNone(m._extract_pricing_pressure(blob))


if __name__ == "__main__":
    result = unittest.TextTestRunner(verbosity=2).run(
        unittest.defaultTestLoader.loadTestsFromTestCase(AppleKPartsMarginWatchTests)
    )
    if not result.wasSuccessful():
        sys.exit(1)
