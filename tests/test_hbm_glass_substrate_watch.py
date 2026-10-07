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

    def test_digitimes_dealsite_republication_is_not_independent_cross_verification(self):
        item = {
            "title": "Samsung tests Chemtronics glass interposer samples",
            "description": "",
            "source": "DIGITIMES",
            "published_at_kst": "2026-10-07T08:37:00+09:00",
            "direct_link": "https://www.digitimes.com/news/a20261006VL222/samsung-interposer-chemtronics-materials-development.html",
        }
        body = (
            "South Korean materials company Chemtronics has delivered glass interposer samples "
            "to Samsung Electronics, with customer evaluation now underway, according to Korean business outlet DealSite."
        )
        rows = w.parse_glass_substrate_records(item, body)
        rec = next(x for x in rows if x["axis"] == "glass_hvm_stage")
        v = rec["value"]
        self.assertEqual(v["customer"], "Samsung Electronics")
        self.assertTrue(v["sample_delivered"])
        self.assertTrue(v["evaluation_ongoing"])
        self.assertTrue(v["digitimes_republisher"])
        self.assertEqual(v["fact_origin_source"], "DealSite")
        self.assertEqual(v["independent_source_count"], 1)
        self.assertFalse(v["independent_cross_verified"])
        self.assertIsNone(v.get("samsung_official_confirmation"))
        self.assertIsNone(v.get("chemtronics_official_customer_confirmation"))

    def test_chemtronics_official_customer_confirmation_is_material(self):
        old = {"axis":"glass_hvm_stage","value":{
            "stage":"customer_evaluation","customer":"Samsung Electronics",
            "samsung_official_confirmation":False,
            "chemtronics_official_customer_confirmation":False,
            "independent_cross_verified":False,
        }}
        new = {"axis":"glass_hvm_stage","value":{
            "stage":"customer_evaluation","customer":"Samsung Electronics",
            "samsung_official_confirmation":False,
            "chemtronics_official_customer_confirmation":True,
            "independent_cross_verified":False,
        }}
        reasons = w.comparison(old,new)
        self.assertTrue(any("켐트로닉스 공식 삼성전자 고객검증 확인" in x for x in reasons))

    def test_samsung_official_customer_confirmation_is_material(self):
        old = {"axis":"glass_hvm_stage","value":{
            "stage":"customer_evaluation","customer":"Samsung Electronics",
            "samsung_official_confirmation":False,
            "chemtronics_official_customer_confirmation":False,
        }}
        new = {"axis":"glass_hvm_stage","value":{
            "stage":"customer_evaluation","customer":"Samsung Electronics",
            "samsung_official_confirmation":True,
            "chemtronics_official_customer_confirmation":False,
        }}
        reasons = w.comparison(old,new)
        self.assertTrue(any("삼성전자 공식 고객검증 확인" in x for x in reasons))

    def test_render_marks_digitimes_as_republisher_not_second_confirmation(self):
        rec = {
            "key":"glass_hvm_stage|chemtronics|current",
            "axis":"glass_hvm_stage",
            "value":{
                "stage":"customer_evaluation","customer":"Samsung Electronics",
                "product":"glass_interposer","digitimes_republisher":True,
                "samsung_official_confirmation":False,
                "chemtronics_official_customer_confirmation":False,
            },
            "unit":"stage,year","period":"current","as_of":"2026-10-07","evidence":"reported",
            "source_url":"https://dealsite.co.kr/newsflash/170000",
            "source_title":"DealSite 원보도 + DIGITIMES 재인용",
        }
        out = w.render({"record":rec,"old":rec,"reasons":["기준선"]})
        self.assertIn("DealSite 원보도 → DIGITIMES 재인용", out)
        self.assertIn("독립된 2개 검증 출처로 계산하지 않습니다", out)
        self.assertIn("삼성전자 미확인", out)
        self.assertIn("켐트로닉스 미확인", out)

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

    def test_jntc_current_ramp_metrics_parse(self):
        item = {"title":"JNTC glass substrate ramp","description":"","source":"디일렉",
                "published_at_kst":"2026-10-06T10:00:00+09:00",
                "direct_link":"https://thelec.kr/news/articleView.html?idxno=63298"}
        body = "제이앤티씨 TGV 유리기판 파일럿 라인 1개는 월 1만~1만2000개 생산능력이다. 현재 27곳과 NDA를 맺었고 최종 수요기업은 7곳, 유상 샘플 고객도 7곳이다. 2027년 2mm 제품 양산 공급을 시작한다."
        rows = w.parse_glass_substrate_records(item, body)
        rec = next(x for x in rows if x["axis"] == "glass_hvm_stage")
        v = rec["value"]
        self.assertEqual(v["pilot_line_count"], 1)
        self.assertEqual(v["pilot_capacity_units_per_month_min"], 10000)
        self.assertEqual(v["pilot_capacity_units_per_month_max"], 12000)
        self.assertEqual(v["nda_customer_count"], 27)
        self.assertEqual(v["end_customer_count"], 7)
        self.assertEqual(v["paid_sample_customer_count"], 7)

    def test_jntc_copper_fill_minute_scale_is_verified_but_exact_minutes_stay_unknown(self):
        item = {"title":"12시간을 분 단위로 단축…제이앤티씨, 유리기판 핵심기술 개발","description":"","source":"디일렉",
                "published_at_kst":"2026-10-06T10:00:00+09:00",
                "direct_link":"https://thelec.kr/news/articleView.html?idxno=63298"}
        body = "제이앤티씨는 510×515mm 크기, 2mm 두께 TGV 유리기판의 구리 충진 시간을 분 단위로 줄이는데 성공했다."
        rows = w.parse_glass_substrate_records(item, body)
        rec = next(x for x in rows if x["axis"] == "glass_process_cycle_time")
        self.assertEqual(rec["value"]["process_name"], "copper_fill_metallization")
        self.assertEqual(rec["value"]["after_time_class"], "minute_scale")
        self.assertIsNone(rec["value"]["after_minutes_exact"])
        self.assertTrue(rec["value"]["body_direct_verified"])

    def test_jntc_enriched_customer_validation_milestones_are_material(self):
        old = {"axis":"glass_hvm_stage","value":{"stage":"customer_evaluation","mass_production_target_year":2027}}
        new = {"axis":"glass_hvm_stage","value":{
            "stage":"customer_evaluation","mass_production_target_year":2027,
            "us_semiconductor_customer_validation_completed":True,
            "taiwan_end_customer_validation_ongoing":True,
            "additional_us_bigtech_collaboration_requested":True,
            "additional_us_bigtech_quality_recognized":True,
        }}
        reasons = w.comparison(old, new)
        self.assertTrue(any("미국 반도체 고객사 제품 검증 완료" in x for x in reasons))
        self.assertTrue(any("대만 최종 고객사 2mm 검증 진행" in x for x in reasons))
        self.assertTrue(any("추가 미국 빅테크 기술협력 요청" in x for x in reasons))

    def test_glass_v4_migration_promotes_current_jntc_baselines_without_pending_alert(self):
        seeds = [
            x for x in __import__("json").loads(
                (pathlib.Path(__file__).resolve().parents[1] / "data" / "hbm_memory_baselines.json").read_text(encoding="utf-8")
            )["records"]
            if x["key"] in ("glass_hvm_stage|jntc|current","glass_process_cycle_time|jntc|current","glass_capex|jntc|gimcheon")
        ]
        old_state = {
            "glass_substrate_track_version": 3,
            "last_notified": {},
            "latest": {},
            "pending": {},
            "coverage": {},
        }
        state = w.update_state(old_state, [], __import__("datetime").datetime(2026,10,6,19,0,0), seeds)
        self.assertEqual(state["glass_substrate_track_version"], 4)
        self.assertEqual(state["latest"]["glass_hvm_stage|jntc|current"]["value"]["paid_sample_customer_count"], 7)
        self.assertEqual(state["latest"]["glass_process_cycle_time|jntc|current"]["value"]["process_name"], "copper_fill_metallization")
        self.assertEqual(state["latest"]["glass_capex|jntc|gimcheon"]["value"]["investment_krw"], 347000000000)
        self.assertEqual(state["pending"], {})

    def test_jntc_cycle_process_not_inferred_from_other_sentences(self):
        item = {"title":"JNTC glass process update","description":"","source":"디일렉",
                "published_at_kst":"2026-10-06T10:00:00+09:00",
                "direct_link":"https://thelec.kr/news/articleView.html?idxno=63298"}
        body = "제이앤티씨 TGV 유리기판 핵심 공정은 기존 12시간에서 분 단위로 단축됐다. 별도로 레이저 가공, 식각, 금속화 공정을 모두 내재화했다."
        rows = w.parse_glass_substrate_records(item, body)
        rec = next(x for x in rows if x["axis"] == "glass_process_cycle_time")
        self.assertEqual(rec["value"]["process_name"], "unverified_core_process")

    def test_samsung_official_glass_pilot_post_2027_plan(self):
        item = {
            "title":"Samsung Electro-Mechanics glass core pilot and JV",
            "description":"","source":"Samsung Electro-Mechanics",
            "published_at_kst":"2026-09-10T09:00:00+09:00",
            "direct_link":"https://samsungsem.com/global/newsroom/news/view.do?id=10522",
        }
        body = (
            "Samsung Electro-Mechanics is producing glass package substrate prototypes at its Sejong plant pilot line. "
            "Mass production is planned after 2027. At KPCA Show 2026 it showcased glass fine connection channels, "
            "metal filling and precision surface processing technologies."
        )
        rows = w.parse_glass_substrate_records(item, body)
        rec = next(x for x in rows if x["key"] == "glass_hvm_stage|samsung_electromechanics|current")
        v = rec["value"]
        self.assertEqual(v["stage"], "pilot")
        self.assertEqual(v["pilot_line_location"], "Sejong")
        self.assertTrue(v["prototype_production"])
        self.assertIsNone(v["mass_production_target_year"])
        self.assertEqual(v["mass_production_earliest_year"], 2028)
        self.assertTrue(v["glass_core_metal_fill_showcased"])
        self.assertTrue(v["precision_surface_processing_showcased"])

    def test_samsung_glassem_official_acquisition_decision_parses_exactly(self):
        item = {
            "title":"Decision on Acquisition of Shares or Investment Certificates of Other Corporations",
            "description":"","source":"Samsung Electro-Mechanics",
            "published_at_kst":"2026-07-02T09:00:00+09:00",
            "direct_link":"https://m.samsungsem.com/global/about-us/investor-relations/disclosure/view.do?id=332",
        }
        body = (
            "Samsung Electro-Mechanics Decision on Acquisition. (provisional title) GlaSSEM Co., Ltd. "
            "Main business Glass Core Manufacturing and Sales. Acquisition cost (KRW) 319,100,000,000. "
            "Shareholding ratio (%) 66.2. The joint venture is being established with Dongwoo Fine-Chem. "
            "Scheduled acquisition date 2026-09-01. Cash investment is KRW 239.1 billion, "
            "and In-Kind investment is KRW 80 billion."
        )
        rows = w.parse_glass_substrate_records(item, body)
        rec = next(x for x in rows if x["axis"] == "glass_jv_stage")
        v = rec["value"]
        self.assertEqual(v["stage"], "share_acquisition_decided")
        self.assertEqual(v["investment_krw"], 319100000000)
        self.assertEqual(v["equity_pct"], 66.2)
        self.assertEqual(v["scheduled_acquisition_date"], "2026-09-01")
        self.assertEqual(v["cash_investment_krw"], 239100000000)
        self.assertEqual(v["in_kind_investment_krw"], 80000000000)
        self.assertEqual(v["partner"], "Dongwoo Fine-Chem")

    def test_samsung_jv_establishment_is_material_but_not_mass_production(self):
        old = {
            "axis":"glass_jv_stage",
            "value":{"stage":"share_acquisition_decided","investment_krw":319100000000,"equity_pct":66.2}
        }
        new = {
            "axis":"glass_jv_stage",
            "value":{"stage":"jv_established","investment_krw":319100000000,"equity_pct":66.2}
        }
        reasons = w.comparison(old,new)
        self.assertTrue(any("share_acquisition_decided→jv_established" in x for x in reasons))
        rec = {
            "key":"glass_jv_stage|samsung_electromechanics|glassem","axis":"glass_jv_stage",
            "value":{"stage":"share_acquisition_decided","investment_krw":319100000000,"equity_pct":66.2,
                     "scheduled_acquisition_date":"2026-09-01","partner":"Dongwoo Fine-Chem"},
            "unit":"KRW,pct,stage","period":"current","as_of":"2026-07-02","evidence":"official",
            "source_url":"https://m.samsungsem.com/global/about-us/investor-relations/disclosure/view.do?id=332",
            "source_title":"삼성전기 GlaSSEM 출자 결정",
        }
        out=w.render({"record":rec,"old":None,"reasons":["기준선"]})
        self.assertIn("양산 개시나 고객 매출 발생과 같은 뜻이 아닙니다", out)

    def test_lg_innotek_gumi_pilot_and_2028_target(self):
        item = {
            "title":"LG Innotek KPCA show 2026 glass substrate",
            "description":"","source":"LG Innotek",
            "published_at_kst":"2026-09-09T09:00:00+09:00",
            "direct_link":"https://www.lginnotek.com/news/pressView.do?idx=6600",
        }
        body = (
            "LG Innotek has established a glass substrate pilot line at the Gumi site. "
            "It is targeting mass production in 2028 and commercialization in 2027-2028. "
            "LG Innotek is collaborating with UTI on glass substrate research and development. "
            "Prototype production is underway."
        )
        rows=w.parse_glass_substrate_records(item,body)
        rec=next(x for x in rows if x["key"]=="glass_hvm_stage|lg_innotek|current")
        v=rec["value"]
        self.assertEqual(v["stage"],"pilot")
        self.assertEqual(v["pilot_line_location"],"Gumi")
        self.assertEqual(v["mass_production_target_year"],2028)
        self.assertEqual(v["commercialization_target_start_year"],2027)
        self.assertEqual(v["commercialization_target_end_year"],2028)
        self.assertTrue(v["uti_collaboration"])

    def test_old_sk_samsung_lg_theme_article_does_not_invent_company_stage(self):
        item = {
            "title":"반도체 게임체인저 잡아라 SK 삼성 LG 유리기판 각축",
            "description":"","source":"국민일보",
            "published_at_kst":"2025-12-11T00:50:00+09:00",
            "direct_link":"https://www.kmib.co.kr/article/view.asp?arcid=1765278382",
        }
        body = (
            "SKC 삼성전기 LG이노텍이 유리기판 시장을 놓고 경쟁하고 있다. "
            "유리기판 시장은 향후 성장할 것으로 예상된다."
        )
        rows=w.parse_glass_substrate_records(item,body)
        self.assertFalse(any(x["axis"] in ("glass_hvm_stage","glass_jv_stage") for x in rows))

    def test_new_official_competitor_baselines_seed_without_retro_alert(self):
        data=__import__("json").loads(
            (pathlib.Path(__file__).resolve().parents[1]/"data"/"hbm_memory_baselines.json").read_text(encoding="utf-8")
        )
        keys={
            "glass_hvm_stage|samsung_electromechanics|current",
            "glass_jv_stage|samsung_electromechanics|glassem",
            "glass_hvm_stage|lg_innotek|current",
        }
        seeds=[x for x in data["records"] if x["key"] in keys]
        old_state={"glass_substrate_track_version":4,"last_notified":{},"latest":{},"pending":{},"coverage":{}}
        state=w.update_state(old_state,[],__import__("datetime").datetime(2026,10,7,12,0,0),seeds)
        self.assertEqual(set(state["latest"]) & keys, keys)
        self.assertEqual(state["pending"], {})

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
