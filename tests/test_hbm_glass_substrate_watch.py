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

    def test_chemtronics_samsung_sample_is_customer_evaluation_not_mass_production(self):
        body = (
            "켐트로닉스가 삼성전자에 유리 인터포저 샘플을 납품했다. "
            "현재 해당 샘플에 대한 평가가 이어지고 있으며 샘플에 이슈가 있으면 대응·보완하고 있다. "
            "삼성전자에 이미 납품한 유리 인터포저 샘플은 기존 방식으로 제작한 제품이다. "
            "새롭게 개발하고 있는 금속 충진 방식은 아직 고객사에 샘플이 나가지는 않았다."
        )
        rows = w.parse_glass_substrate_records(
            self.item("https://dealsite.co.kr/newsflash/170000", "딜사이트", "2026-10-02T10:00:00+09:00"),
            body,
        )
        rec = next(x for x in rows if x["axis"] == "glass_hvm_stage")
        self.assertEqual(rec["key"], "glass_hvm_stage|chemtronics|current")
        self.assertEqual(rec["value"]["stage"], "customer_evaluation")
        self.assertEqual(rec["value"]["customer"], "Samsung Electronics")
        self.assertEqual(rec["value"]["product"], "glass_interposer")
        self.assertTrue(rec["value"]["sample_delivered"])
        self.assertTrue(rec["value"]["evaluation_ongoing"])
        self.assertTrue(rec["value"]["issue_response_ongoing"])
        self.assertEqual(rec["value"]["sample_process"], "existing_method")
        self.assertEqual(rec["value"]["new_metal_fill_stage"], "development")
        self.assertFalse(rec["value"]["new_metal_fill_sample_delivered"])
        self.assertFalse(rec["value"]["mass_production_supply_confirmed"])

    def test_chemtronics_future_stage_and_new_fill_sample_alert(self):
        old = {
            "axis":"glass_hvm_stage",
            "value":{
                "stage":"customer_evaluation",
                "customer":"Samsung Electronics",
                "sample_delivered":True,
                "new_metal_fill_stage":"development",
                "new_metal_fill_sample_delivered":False,
                "mass_production_supply_confirmed":False,
            },
        }
        new = {
            "axis":"glass_hvm_stage",
            "value":{
                "stage":"po_signed",
                "customer":"Samsung Electronics",
                "sample_delivered":True,
                "new_metal_fill_stage":"customer_sample",
                "new_metal_fill_sample_delivered":True,
                "mass_production_supply_confirmed":False,
            },
        }
        reasons = w.comparison(old,new)
        self.assertTrue(any("customer_evaluation→po_signed" in x for x in reasons))
        self.assertTrue(any("신규 금속 충진 샘플 고객 전달" in x for x in reasons))

    def test_render_chemtronics_customer_is_reported_not_contract(self):
        rec = {
            "key":"glass_hvm_stage|chemtronics|current",
            "axis":"glass_hvm_stage",
            "value":{
                "stage":"customer_evaluation","mass_production_target_year":None,
                "customer":"Samsung Electronics","product":"glass_interposer",
                "sample_delivered":True,"evaluation_ongoing":True,"issue_response_ongoing":True,
                "sample_process":"existing_method","new_metal_fill_stage":"development",
                "new_metal_fill_sample_delivered":False,"mass_production_supply_confirmed":False
            },
            "unit":"stage,year","period":"current","as_of":"2026-10-02","evidence":"reported",
            "source_url":"https://dealsite.co.kr/newsflash/170000",
            "source_title":"삼성전자, 켐트로닉스 유리 인터포저 샘플 테스트",
        }
        out = w.render({"record":rec,"old":None,"reasons":["기준선"]})
        self.assertIn("고객 Samsung Electronics", out)
        self.assertIn("확정 공급계약·양산매출로 승격하지 않습니다", out)
        self.assertIn("신규 금속 충진 방식", out)

    def test_jntc_cycle_time_headline_stays_non_exact(self):
        item = {
            "title": "12시간을 분 단위로 단축…제이앤티씨, 유리기판 핵심기술 개발",
            "description": "", "source": "디일렉",
            "published_at_kst": "2026-10-06T10:00:00+09:00",
            "direct_link": "https://thelec.kr/news/articleView.html?idxno=63298",
        }
        rows = w.parse_glass_substrate_records(
            item, "제이앤티씨 TGV 유리기판. 기존 12시간 공정을 분 단위로 단축했다."
        )
        rec = next(x for x in rows if x["axis"] == "glass_process_cycle_time")
        self.assertEqual(rec["value"]["before_minutes"], 720)
        self.assertEqual(rec["value"]["after_time_class"], "minute_scale")
        self.assertIsNone(rec["value"]["after_minutes_exact"])
        self.assertEqual(rec["value"]["process_name"], "unverified_core_process")

    def test_jntc_gimcheon_capex_keeps_output_unknown(self):
        item = {"title":"JNTC Gimcheon glass substrate investment","description":"","source":"연합뉴스",
                "published_at_kst":"2026-10-06T10:00:00+09:00",
                "direct_link":"https://www.yna.co.kr/amp/view/AKR20260921036200053"}
        body = "제이앤티씨는 김천 TGV 유리기판 공장에 3,470억원을 투자한다. 2027년 하반기 착공해 2~3개 생산라인을 구축하고 2028년 중반 초기 물량에 대응한 뒤 10개 이상 라인으로 확대한다."
        rows = w.parse_glass_substrate_records(item, body)
        rec = next(x for x in rows if x["axis"] == "glass_capex")
        self.assertEqual(rec["value"]["investment_krw"], 347000000000)
        self.assertEqual(rec["value"]["line_count_min_initial"], 2)
        self.assertEqual(rec["value"]["line_count_max_initial"], 3)
        self.assertEqual(rec["value"]["line_count_mass_ramp_min"], 10)
        self.assertIsNone(rec["value"]["capacity_panels_per_month"])

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
