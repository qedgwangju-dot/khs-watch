import pathlib
import sys
import unittest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "scripts"))
import hbm_memory_axes as w


class GlassSubstrateWatchTests(unittest.TestCase):
    def item(self, url="https://www.digitimes.com/news/a20261001PD230/ai-chip-tsmc-corning-tgv-agc.html", source="DIGITIMES", date="2026-10-01T13:56:00+09:00"):
        return {
            "direct_link": url,
            "source": source,
            "published_at_kst": date,
            "title": "Four glass makers converge on 510x515mm substrate, hinting at TSMC's next move",
        }

    def test_four_supplier_510x515_convergence_is_not_tsmc_official(self):
        body = (
            "Corning, AGC, Nippon Electric Glass (NEG), and SCHOTT have centered their next-generation "
            "glass core substrate and TGV roadmaps on a unified 510x515mm format. "
            "The alignment strongly suggests TSMC is eyeing this exact specification for a post-2030 glass substrate platform."
        )
        rows = w.parse_glass_substrate_records(self.item(), body)
        rec = next(x for x in rows if x["axis"] == "glass_panel_standard")
        self.assertEqual(rec["value"]["supplier_count"], 4)
        self.assertEqual(rec["value"]["width_mm"], 510)
        self.assertEqual(rec["value"]["height_mm"], 515)
        self.assertEqual(rec["value"]["tsmc_status"], "reported_candidate")
        self.assertIn("not_tsmc_official", rec["scope"])

    def test_single_vendor_page_does_not_replace_industry_count(self):
        body = "AGC provides TGV panel format production, e.g. 510x515mm, for semiconductor packaging."
        rows = w.parse_glass_substrate_records(
            self.item("https://www.agc.com/en/products/electoric/detail/tgv.html", "AGC"), body
        )
        self.assertFalse(any(x["axis"] == "glass_panel_standard" for x in rows))

    def test_trendforce_copos_roadmap_is_kept_separate(self):
        body = (
            "TSMC CoPoS has standardized on a 310x310mm panel format. "
            "2026 is the validation period, pilot production is targeted for 2027, "
            "and mass production is slated for the second half of 2028. "
            "Glass core substrate commercial-scale production is likely after 2030."
        )
        rows = w.parse_glass_substrate_records(
            self.item("https://www.trendforce.com/presscenter/news/20260617-13107.html", "TrendForce", "2026-06-17T09:00:00+09:00"),
            body,
        )
        rec = next(x for x in rows if x["axis"] == "glass_tsmc_roadmap")
        self.assertEqual(rec["value"]["copos_width_mm"], 310)
        self.assertEqual(rec["value"]["pilot_year"], 2027)
        self.assertEqual(rec["value"]["mass_production_year"], 2028)
        self.assertEqual(rec["value"]["mass_production_half"], "H2")
        self.assertEqual(rec["value"]["glass_core_commercial_after_year"], 2030)

    def test_jntc_panel_yield_and_hvm_stage(self):
        body = (
            "JNTC TGV glass substrate has achieved a mass production yield of approximately 94%. "
            "The company is conducting customer evaluation with global semiconductor packaging firms "
            "and targets mass production in 2027."
        )
        rows = w.parse_glass_substrate_records(
            self.item("https://en.edaily.co.kr/news/eda202607135464/", "EDAILY", "2026-07-13T10:00:00+09:00"),
            body,
        )
        y = next(x for x in rows if x["axis"] == "glass_panel_yield")
        h = next(x for x in rows if x["axis"] == "glass_hvm_stage")
        self.assertEqual(y["value"]["yield_pct"], 94.0)
        self.assertEqual(h["value"]["stage"], "customer_evaluation")
        self.assertEqual(h["value"]["mass_production_target_year"], 2027)

    def test_yield_crossing_90_alerts(self):
        old = {"axis":"glass_panel_yield","value":{"yield_pct":88.0}}
        new = {"axis":"glass_panel_yield","value":{"yield_pct":92.0}}
        reasons = w.comparison(old, new)
        self.assertTrue(any("90%" in x for x in reasons))

    def test_tsmc_official_adoption_upgrade_alerts(self):
        old = {"axis":"glass_panel_standard","value":{"width_mm":510,"height_mm":515,"supplier_count":4,"tsmc_status":"reported_candidate"}}
        new = {"axis":"glass_panel_standard","value":{"width_mm":510,"height_mm":515,"supplier_count":4,"tsmc_status":"official_adopted"}}
        reasons = w.comparison(old, new)
        self.assertTrue(any("reported_candidate→official_adopted" in x for x in reasons))

    def test_hvm_stage_upgrade_alerts(self):
        old = {"axis":"glass_hvm_stage","value":{"stage":"customer_evaluation","mass_production_target_year":2027}}
        new = {"axis":"glass_hvm_stage","value":{"stage":"po_signed","mass_production_target_year":2027}}
        reasons = w.comparison(old, new)
        self.assertTrue(any("customer_evaluation→po_signed" in x for x in reasons))

    def test_render_keeps_tgv_hole_and_panel_yield_separate(self):
        rec = {
            "key":"glass_panel_yield|jntc|current",
            "axis":"glass_panel_yield",
            "value":{"yield_pct":94.0},
            "unit":"pct","period":"current","as_of":"2026-07-13","evidence":"reported",
            "source_url":"https://en.edaily.co.kr/news/eda202607135464/",
            "source_title":"JNTC TGV 유리기판 양산 수율 약 94%",
        }
        out = w.render({"record":rec,"old":None,"reasons":["기준선"]})
        self.assertIn("전체 패널 전기수율", out)
        self.assertIn("85%·90%", out)


if __name__ == "__main__":
    unittest.main()
