import pathlib
import sys
import unittest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "scripts"))
import hbm_memory_axes as w


class HBMGenerationPricingTests(unittest.TestCase):
    def item(self, source="SemiAnalysis", url="https://semianalysis.com/example"):
        return {
            "title": "Every HBM generation steps up together in 2027",
            "description": "",
            "source": source,
            "published_at_kst": "2026-10-02T08:00:00+09:00",
            "direct_link": url,
        }

    def test_generation_prices_keep_stack_height_separate(self):
        text = (
            "SemiAnalysis 2027 HBM pricing: "
            "HBM3E $3.70/Gb, HBM4 12-Hi $4.00/Gb, HBM4E $4.31/Gb. "
            "Every HBM generation steps up together in 2027."
        )
        rows = w.parse_hbm_generation_pricing(self.item(), text)
        self.assertEqual(len(rows), 1)
        rec = rows[0]
        self.assertEqual(rec["key"], "hbm_generation_pricing|semianalysis|2027")
        pts = rec["value"]["price_usd_per_gb"]
        self.assertEqual(pts["HBM3E_stack_unspecified"], 3.70)
        self.assertEqual(pts["HBM4_12Hi"], 4.00)
        self.assertEqual(pts["HBM4E_stack_unspecified"], 4.31)
        self.assertTrue(rec["value"]["broad_step_up_2027"])
        self.assertTrue(rec["value"]["legacy_generation_price_visible"])

    def test_generic_hbm_reset_without_generation_numbers_is_not_promoted(self):
        text = (
            "Micron said 2027 HBM prices are much higher than 2026 prices. "
            "The portfolio includes HBM3E, HBM4 and HBM4E."
        )
        rows = w.parse_hbm_generation_pricing(
            self.item("Micron", "https://investors.micron.com/example"), text
        )
        self.assertEqual(rows, [])

    def test_generation_price_revision_threshold(self):
        old = {
            "axis":"hbm_generation_pricing",
            "value":{
                "price_usd_per_gb":{"HBM4_12Hi":4.00},
                "broad_step_up_2027":True,
                "legacy_generation_price_visible":False,
                "generation_count":1,
            },
        }
        small = {
            "axis":"hbm_generation_pricing",
            "value":dict(old["value"], price_usd_per_gb={"HBM4_12Hi":4.10}),
        }
        big = {
            "axis":"hbm_generation_pricing",
            "value":dict(old["value"], price_usd_per_gb={"HBM4_12Hi":4.40}),
        }
        self.assertEqual(w.comparison(old, small), [])
        self.assertTrue(any("HBM4_12Hi" in x for x in w.comparison(old, big)))

    def test_legacy_generation_new_number_alerts(self):
        old = {
            "axis":"hbm_generation_pricing",
            "value":{
                "price_usd_per_gb":{"HBM4_12Hi":4.00},
                "broad_step_up_2027":True,
                "legacy_generation_price_visible":False,
                "generation_count":1,
            },
        }
        new = {
            "axis":"hbm_generation_pricing",
            "value":{
                "price_usd_per_gb":{"HBM4_12Hi":4.00,"HBM3E_stack_unspecified":3.60},
                "broad_step_up_2027":True,
                "legacy_generation_price_visible":True,
                "generation_count":2,
            },
        }
        reasons = w.comparison(old, new)
        self.assertTrue(any("HBM3E" in x for x in reasons))
        self.assertTrue(any("구세대" in x for x in reasons))

    def test_render_warns_not_to_mix_blended_or_stack_heights(self):
        rec = {
            "key":"hbm_generation_pricing|semianalysis|2027",
            "axis":"hbm_generation_pricing",
            "value":{
                "price_usd_per_gb":{"HBM4_12Hi":4.00,"HBM4E_stack_unspecified":4.31},
                "broad_step_up_2027":True,
                "legacy_generation_price_visible":False,
                "generation_count":2,
            },
            "unit":"USD/Gb,stage","period":"2027","as_of":"2026-10-02",
            "evidence":"research",
            "source_url":"https://semianalysis.com/example",
            "source_title":"SemiAnalysis 2027 HBM generation pricing",
        }
        out = w.render({"record":rec,"old":None,"reasons":["기준선"]})
        self.assertIn("기관별 가격곡선", out)
        self.assertIn("8단·12단", out)
        self.assertIn("Blended ASP", out)


if __name__ == "__main__":
    unittest.main()
