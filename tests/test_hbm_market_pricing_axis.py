import pathlib
import sys
import unittest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "scripts"))
import hbm_memory_axes as w


class HBMMarketPricingAxisTests(unittest.TestCase):
    def item(self):
        return {
            "title": "TrendForce 2027 HBM Blended ASP outlook",
            "description": "",
            "source": "TrendForce",
            "direct_link": "https://www.trendforce.com/presscenter/news/20260929-13255.html",
            "published_at_kst": "2026-09-29T18:00:00+09:00",
        }

    def test_parse_121pct_and_8hi_premium(self):
        body = (
            "트렌드포스는 2027년 HBM의 제품별 판매 비중을 반영한 평균판매가격(Blended ASP)은 "
            "전년 대비 121% 급등할 것으로 봤다. 8단 제품을 우선 적용할 것으로 예상된다. "
            "2027년 8단 HBM의 Gb당 판매가격은 12단 제품보다 약 10~20% 높게 형성될 전망이다."
        )
        rows = w.parse_hbm_market_pricing(self.item(), body)
        self.assertEqual(len(rows), 1)
        v = rows[0]["value"]
        self.assertEqual(v["blended_asp_yoy_pct"], 121.0)
        self.assertEqual(v["eight_hi_premium_min_pct"], 10.0)
        self.assertEqual(v["eight_hi_premium_max_pct"], 20.0)
        self.assertEqual(v["mainstream_layers"], 8)
        self.assertAlmostEqual(v["stack_bit_change_pct"], -33.3333333333, places=6)
        self.assertAlmostEqual(v["gpu_growth_break_even_min_pct"], 25.0, places=6)
        self.assertAlmostEqual(v["gpu_growth_break_even_max_pct"], 36.3636363636, places=6)

    def test_break_even_math_with_10_to_20pct_premium(self):
        x = w.hbm_stack_revenue_break_even(12, 8, 10, 20)
        self.assertAlmostEqual(x["stack_bit_change_pct"], -33.3333333333, places=6)
        self.assertAlmostEqual(x["gpu_growth_break_even_min_pct"], 25.0, places=6)
        self.assertAlmostEqual(x["gpu_growth_break_even_max_pct"], 36.3636363636, places=6)

    def test_blended_asp_requires_ten_point_revision(self):
        old = {
            "axis": "hbm_market_pricing",
            "value": {
                "blended_asp_yoy_pct": 121.0,
                "eight_hi_premium_min_pct": 10.0,
                "eight_hi_premium_max_pct": 20.0,
                "mainstream_layers": 8,
            },
        }
        small = {
            "axis": "hbm_market_pricing",
            "value": dict(old["value"], blended_asp_yoy_pct=128.0),
        }
        big = {
            "axis": "hbm_market_pricing",
            "value": dict(old["value"], blended_asp_yoy_pct=132.0),
        }
        self.assertEqual(w.comparison(old, small), [])
        self.assertTrue(any("Blended ASP" in x for x in w.comparison(old, big)))

    def test_8hi_premium_five_point_revision_alerts(self):
        old = {
            "axis": "hbm_market_pricing",
            "value": {
                "blended_asp_yoy_pct": 121.0,
                "eight_hi_premium_min_pct": 10.0,
                "eight_hi_premium_max_pct": 20.0,
                "mainstream_layers": 8,
            },
        }
        new = {
            "axis": "hbm_market_pricing",
            "value": dict(old["value"], eight_hi_premium_min_pct=15.0),
        }
        self.assertTrue(any("프리미엄 하단" in x for x in w.comparison(old, new)))

    def test_market_pricing_seed_migration_upgrades_source_without_alert(self):
        key = "hbm_market_pricing|trendforce|industry|2027"
        old = {
            "last_notified": {
                key: {
                    "key": key,
                    "axis": "hbm_market_pricing",
                    "value": {"blended_asp_yoy_pct": 121.0},
                    "evidence": "reported",
                    "as_of": "2026-09-29",
                    "period": "2027",
                    "source_url": "https://example.com/republisher",
                }
            },
            "latest": {},
            "pending": {key: {"dummy": True}},
            "coverage": {},
        }
        seed = {
            "key": key,
            "axis": "hbm_market_pricing",
            "value": {"blended_asp_yoy_pct": 121.0},
            "evidence": "research",
            "as_of": "2026-09-29",
            "period": "2027",
            "source_url": "https://www.trendforce.com/presscenter/news/20260929-13255.html",
        }
        now = w.datetime(2026, 9, 29, 19, 40, tzinfo=w.ZoneInfo("Asia/Seoul"))
        state = w.update_state(old, [], now, [seed])
        self.assertEqual(state["last_notified"][key]["evidence"], "research")
        self.assertIn("trendforce.com/presscenter", state["latest"][key]["source_url"])
        self.assertNotIn(key, state["pending"])

    def test_market_mainstream_8_to_12_alerts(self):
        old = {"axis": "hbm_market_pricing", "value": {"mainstream_layers": 8}}
        new = {"axis": "hbm_market_pricing", "value": {"mainstream_layers": 12}}
        self.assertTrue(any("8단→12단" in x for x in w.comparison(old, new)))


if __name__ == "__main__":
    unittest.main()
