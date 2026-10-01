import pathlib
import sys
import unittest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "scripts"))
import hbm_memory_axes as w


class SamsungFoundryRecoveryTests(unittest.TestCase):
    def item(self, url, source="TrendForce"):
        return {
            "direct_link": url,
            "source": source,
            "published_at_kst": "2026-09-30T09:00:00+09:00",
            "title": "Samsung foundry recovery",
        }

    def test_loss_outlook_is_combined_and_reported(self):
        body = (
            "Samsung foundry and System LSI combined operating loss is expected to narrow 41.8% "
            "from 6.74 trillion won in 2025 to 3.92 trillion won in 2026. "
            "Q3 2026 loss is expected at 7,770억원 as HBM4 4nm base die demand rises."
        )
        rows = w.parse_foundry_recovery_records(
            self.item("https://www.trendforce.com/news/2026/09/30/example"), body
        )
        loss = next(x for x in rows if x["axis"] == "foundry_loss_outlook")
        self.assertAlmostEqual(loss["value"]["loss_2025_krw_trn"], 6.74)
        self.assertAlmostEqual(loss["value"]["loss_2026e_krw_trn"], 3.92)
        self.assertAlmostEqual(loss["value"]["loss_shrink_pct"], 41.8)
        self.assertAlmostEqual(loss["value"]["q3_2026e_loss_krw_trn"], 0.777)
        self.assertEqual(loss["evidence"], "reported")
        self.assertIn("combined_not_foundry_standalone", loss["scope"])

    def test_loss_revision_threshold(self):
        old = {"axis":"foundry_loss_outlook","value":{"loss_2026e_krw_trn":3.92,"loss_shrink_pct":41.84,"q3_2026e_loss_krw_trn":0.777}}
        small = {"axis":"foundry_loss_outlook","value":dict(old["value"],loss_2026e_krw_trn=3.70)}
        big = {"axis":"foundry_loss_outlook","value":dict(old["value"],loss_2026e_krw_trn=3.30)}
        self.assertEqual(w.comparison(old, small), [])
        self.assertTrue(any("2026E" in x for x in w.comparison(old, big)))

    def test_official_2nm_design_win_stage(self):
        body = (
            "Samsung Foundry earnings improved on HBM base-die demand and strong orders from U.S. customers. "
            "Design wins with major customers expanded, including 2nm HPC engagements. "
            "For H2 2026, Samsung plans to ramp second-generation 2nm mobile products."
        )
        rows = w.parse_foundry_recovery_records(
            self.item("https://news.samsung.com/global/samsung-electronics-announces-second-quarter-2026-results","Samsung Global Newsroom"),
            body,
        )
        rec = next(x for x in rows if x["axis"] == "foundry_external_2nm")
        self.assertEqual(rec["value"]["stage"], "design_win")
        self.assertTrue(rec["value"]["hpc_design_win"])
        self.assertTrue(rec["value"]["us_orders_strong"])
        self.assertTrue(rec["value"]["gen2_mobile_ramp_plan"])
        self.assertEqual(rec["evidence"], "official")

    def test_2nm_stage_upgrade_alerts(self):
        old = {"axis":"foundry_external_2nm","value":{"stage":"design_win","hpc_design_win":True}}
        new = {"axis":"foundry_external_2nm","value":{"stage":"mass_production","hpc_design_win":True}}
        self.assertTrue(any("design_win→mass_production" in x for x in w.comparison(old,new)))

    def test_taylor_schedule_change_alerts(self):
        old = {"axis":"foundry_taylor_schedule","value":{"mass_production_year":2027,"external_customer_negotiations":True}}
        new = {"axis":"foundry_taylor_schedule","value":{"mass_production_year":2028,"external_customer_negotiations":True}}
        self.assertTrue(any("2027→2028" in x for x in w.comparison(old,new)))

    def test_pricing_range_is_parsed(self):
        body = (
            "Samsung HBM4 base die demand supports 4nm new orders. "
            "Some advanced process prices rose 10~15% as utilization improved."
        )
        rows = w.parse_foundry_hbm_records(self.item("https://example.com/a","News"), body)
        pricing = next(x for x in rows if x["axis"] == "foundry_pricing")
        self.assertEqual(pricing["value"]["price_change_pct_min"], 10.0)
        self.assertEqual(pricing["value"]["price_change_pct_max"], 15.0)

    def test_render_warns_combined_loss_not_foundry_standalone(self):
        rec = {
            "key":"x","axis":"foundry_loss_outlook",
            "value":{"loss_2025_krw_trn":6.74,"loss_2026e_krw_trn":3.92,"loss_shrink_pct":41.84,"q3_2026e_loss_krw_trn":0.777},
            "unit":"KRW_trillion,pct","period":"2026","as_of":"2026-09-30","evidence":"reported",
            "source_url":"https://www.trendforce.com/news/example","source_title":"삼성 파운드리 손실 전망",
        }
        out = w.render({"record":rec,"old":None,"reasons":["기준선"]})
        self.assertIn("파운드리+System LSI", out)
        self.assertIn("파운드리 단독", out)


if __name__ == "__main__":
    unittest.main()
