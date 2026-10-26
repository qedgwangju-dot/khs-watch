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
        self.assertIsNone(rec["value"]["mass_production_supply_confirmed"])

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
        self.assertEqual(v["fact_origin_sources"], ["DealSite"])
        self.assertIsNone(v.get("samsung_official_confirmation"))
        self.assertIsNone(v.get("chemtronics_official_customer_confirmation"))

    def test_independent_digitimes_followup_can_raise_origin_count_to_two(self):
        old = {
            "glass_substrate_track_version": 5,
            "last_notified": {
                "glass_hvm_stage|chemtronics|current": {
                    "key":"glass_hvm_stage|chemtronics|current","axis":"glass_hvm_stage",
                    "value":{
                        "stage":"customer_evaluation","customer":"Samsung Electronics",
                        "sample_delivered":True,"evaluation_ongoing":True,
                        "issue_response_ongoing":True,"mass_production_supply_confirmed":False,
                        "fact_origin_source":"DealSite","fact_origin_sources":["DealSite"],
                        "independent_source_count":1,"independent_cross_verified":False,
                    },
                    "unit":"stage,year","period":"current","as_of":"2026-10-07","evidence":"reported",
                    "source_url":"https://dealsite.co.kr/example","source_title":"DealSite"
                }
            },
            "latest": {}, "pending": {}, "coverage": {},
        }
        item = {
            "title":"Samsung tests Chemtronics glass interposer samples independently",
            "description":"","source":"DIGITIMES",
            "published_at_kst":"2026-10-08T08:37:00+09:00",
            "direct_link":"https://www.digitimes.com/news/independent-chemtronics.html",
        }
        body = (
            "DIGITIMES supply-chain checks found Chemtronics delivered glass interposer samples "
            "to Samsung Electronics and customer evaluation is ongoing."
        )
        rec = next(x for x in w.parse_glass_substrate_records(item, body) if x["axis"]=="glass_hvm_stage")
        self.assertEqual(rec["value"]["fact_origin_source"], "DIGITIMES")
        state = w.update_state(old, [rec], __import__("datetime").datetime(2026,10,8,10,0,0), [])
        v = state["latest"]["glass_hvm_stage|chemtronics|current"]["value"]
        self.assertEqual(set(v["fact_origin_sources"]), {"DealSite","DIGITIMES"})
        self.assertEqual(v["independent_source_count"], 2)
        self.assertTrue(v["independent_cross_verified"])
        self.assertTrue(any("독립 출처 2곳 이상" in x for x in state["pending"]["glass_hvm_stage|chemtronics|current"]["reasons"]))

    def test_digitimes_republisher_never_inflates_origin_count(self):
        old = {
            "glass_substrate_track_version": 5,
            "last_notified": {
                "glass_hvm_stage|chemtronics|current": {
                    "key":"glass_hvm_stage|chemtronics|current","axis":"glass_hvm_stage",
                    "value":{
                        "stage":"customer_evaluation","customer":"Samsung Electronics",
                        "sample_delivered":True,"evaluation_ongoing":True,
                        "issue_response_ongoing":True,"mass_production_supply_confirmed":False,
                        "fact_origin_source":"DealSite","fact_origin_sources":["DealSite"],
                        "independent_source_count":1,"independent_cross_verified":False,
                    },
                    "unit":"stage,year","period":"current","as_of":"2026-10-07","evidence":"reported",
                    "source_url":"https://dealsite.co.kr/example","source_title":"DealSite"
                }
            },
            "latest": {}, "pending": {}, "coverage": {},
        }
        item = {
            "title":"Samsung tests Chemtronics glass interposer samples",
            "description":"","source":"DIGITIMES",
            "published_at_kst":"2026-10-08T08:37:00+09:00",
            "direct_link":"https://www.digitimes.com/news/republication.html",
        }
        body = (
            "Chemtronics delivered glass interposer samples to Samsung Electronics, with evaluation underway, "
            "according to Korean business outlet DealSite."
        )
        rec = next(x for x in w.parse_glass_substrate_records(item, body) if x["axis"]=="glass_hvm_stage")
        state = w.update_state(old, [rec], __import__("datetime").datetime(2026,10,8,10,0,0), [])
        v = state["latest"]["glass_hvm_stage|chemtronics|current"]["value"]
        self.assertEqual(v["fact_origin_sources"], ["DealSite"])
        self.assertEqual(v["independent_source_count"], 1)
        self.assertFalse(v["independent_cross_verified"])
        self.assertNotIn("glass_hvm_stage|chemtronics|current", state["pending"])

    def test_official_domain_without_customer_fact_does_not_fake_confirmation(self):
        item = {
            "title":"Samsung advanced packaging overview mentions Chemtronics",
            "description":"","source":"Samsung",
            "published_at_kst":"2026-10-08T08:00:00+09:00",
            "direct_link":"https://semiconductor.samsung.com/news/packaging-example",
        }
        body = "Samsung Electronics describes glass interposer technology. Chemtronics is mentioned as an ecosystem company."
        rows = w.parse_glass_substrate_records(item, body)
        # No sample/evaluation/contract transition exists, so no HVM record should be created at all.
        self.assertFalse(any(x["key"]=="glass_hvm_stage|chemtronics|current" for x in rows))

    def test_korean_glass_company_names_pass_axis_gate(self):
        self.assertTrue(w.is_axis_text("제이앤티씨 유리기판 TGV 공정시간 12시간을 분 단위로 단축"))
        self.assertTrue(w.is_axis_text("LG이노텍 유리기판 파일럿 양산 검토"))
        self.assertTrue(w.is_axis_text("SKC 앱솔릭스 유리기판 고객 검증"))

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
        self.assertEqual(state["glass_substrate_track_version"], 5)
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


    def test_foplp_mature_node_volume_production_not_ai_copos_or_glass(self):
        item = self.item(
            "https://www.trendforce.com/presscenter/news/20260617-13107.html",
            "TrendForce", "2026-06-17T09:00:00+09:00")
        body = ("Several Taiwan manufacturers have already achieved volume production of "
                "FOPLP for mature-node PMICs and RF devices, utilizing panels up to 620 × 750 mm.")
        rows = w.parse_foplp_records(item, body)
        rec = next(x for x in rows if x["axis"] == "foplp_mature_node_industry")
        self.assertEqual(rec["value"]["panel_width_mm"], 620)
        self.assertEqual(rec["value"]["panel_height_mm"], 750)
        self.assertFalse(rec["value"]["ai_hpc_mass_production_confirmed"])
        self.assertFalse(rec["value"]["tsmc_copos_mass_production_confirmed"])
        self.assertFalse(any(x["axis"] == "foplp_company_ai_stage" for x in rows))

    def test_generic_copos_and_foplp_story_does_not_forge_tsmc_ai_production(self):
        item = self.item("https://www.ctee.com.tw/news/20261010700049-439901", "工商時報",
                         "2026-10-10T12:00:00+09:00")
        body = ("TSMC CoPoS remains under validation with production expected in 2028-2029. "
                "FOPLP has already demonstrated mass production for legacy PMIC and RF packages. "
                "Glass core substrates face TGV and warpage barriers.")
        rows = w.parse_foplp_records(item, body)
        self.assertFalse(any(x["axis"] == "foplp_company_ai_stage" for x in rows))
        self.assertFalse(any(x["axis"] == "foplp_mature_node_industry" for x in rows))

    def test_foplp_keyword_cannot_hide_preexisting_glass_evidence_gate(self):
        text = "FOPLP 510×515mm 유리기판 TGV"
        self.assertTrue(w.is_axis_text(text))

    def test_foplp_expected_future_ai_mass_production_is_not_current_stage(self):
        item = self.item("https://www.ctee.com.tw/news/future", "工商時報")
        rows = w.parse_foplp_records(
            item, "TSMC plans to begin FOPLP mass production for AI accelerators by 2028.")
        self.assertFalse(any(x["axis"] == "foplp_company_ai_stage" for x in rows))

    def test_foplp_copos_not_auto_converted_to_tsmc_company_foplp_stage(self):
        item = self.item("https://www.tsmc.com/english/news", "TSMC")
        body = "TSMC has started CoPoS pilot production for FOPLP-style AI accelerators."
        self.assertFalse(any(x["axis"] == "foplp_company_ai_stage"
                             for x in w.parse_foplp_records(item, body)))

    def test_foplp_ase_official_customer_qualification_is_distinct_event(self):
        item = self.item("https://www.aseglobal.com/en/news/foplp-ai", "ASE",
                         "2026-10-15T15:00:00+09:00")
        body = "ASE has completed customer qualification for FOPLP AI accelerators."
        rows = w.parse_foplp_records(item, body)
        rec = next(x for x in rows if x["axis"] == "foplp_company_ai_stage")
        self.assertEqual(rec["key"], "foplp_company_ai_stage|ase|AI_HPC")
        self.assertEqual(rec["value"]["stage"], "customer_qualified")
        self.assertTrue(rec["value"]["issuer_official"])
        self.assertEqual(rec["evidence"], "official")
        rendered = w.render({"record":rec,"old":None,"reasons":["고객 검증 완료"]})
        self.assertIn("FOPLP", rendered)
        self.assertNotIn("TSMC CoPoS 양산", rendered)
        self.assertIn("고객 검증", rendered)

    def test_foplp_media_qualification_cannot_promote_itself_to_official(self):
        item = self.item("https://www.ctee.com.tw/news/independent-ase-foplp", "工商時報",
                         "2026-10-15T15:00:00+09:00")
        rec = next(x for x in w.parse_foplp_records(
            item, "ASE has completed customer qualification for FOPLP AI accelerators.")
            if x["axis"] == "foplp_company_ai_stage")
        self.assertFalse(rec["value"]["issuer_official"])
        self.assertEqual(rec["evidence"], "reported")

    def test_foplp_pilot_and_official_promotion_material(self):
        old = {"axis":"foplp_company_ai_stage",
               "value":{"stage":"customer_qualified","manufacturer":"ase","issuer_official":False}}
        new = {"axis":"foplp_company_ai_stage",
               "value":{"stage":"pilot_production","manufacturer":"ase","issuer_official":True}}
        self.assertTrue(any("pilot_production" in x for x in w.comparison(old,new)))
        reverse = w.comparison(new,old)
        self.assertEqual(reverse, [])
        promoted = {"axis":"foplp_company_ai_stage",
                    "value":{"stage":"customer_qualified","manufacturer":"ase","issuer_official":True}}
        self.assertTrue(any("회사 공식" in x for x in w.comparison(old,promoted)))

    def test_foplp_seed_version_avoids_retroactive_telegram(self):
        data = __import__("json").loads(
            (pathlib.Path(__file__).resolve().parents[1]/"data"/"hbm_memory_baselines.json")
            .read_text(encoding="utf-8"))
        seed = next(x for x in data["records"]
                    if x["key"] == "foplp_mature_node_industry|industry|PMIC_RF")
        old = {"foplp_track_version":0, "last_notified":{}, "latest":{},
               "pending":{}, "coverage":{}}
        now = __import__("datetime").datetime(2026,10,10,17,0,0)
        state = w.update_state(old,[seed],now,[seed])
        self.assertEqual(state["foplp_track_version"], w.FOPLP_TRACK_VERSION)
        self.assertIn(seed["key"],state["last_notified"])
        self.assertNotIn(seed["key"],state["pending"])
        state2 = w.update_state(state,[seed],now,[seed])
        self.assertNotIn(seed["key"],state2["pending"])


    def test_hbf_ocp_v070_is_public_draft_not_finished_product(self):
        item={"direct_link":w.HBF_OCP_STORAGE_URL,"published_at_kst":"2026-08-03T09:00:00+09:00",
              "source":"OCP","title":"HBF specification"}
        body="High Bandwidth Flash (HBF™) High-Level Base Die Specification V0.7.0"
        rec=w.parse_hbf_ocp_version(item,body)[0]
        self.assertEqual(rec["key"],"hbf_ocp_spec|ocp|base_die")
        self.assertEqual(rec["value"]["version"],"0.7.0")
        self.assertFalse(rec["value"]["final_spec_officially_confirmed"])
        self.assertFalse(rec["value"]["commercial_sales_confirmed"])
    def test_hbf_issuer_only_and_cross_subject_version_guard(self):
        item={"direct_link":"https://newspim.com/news/view/20261014000748",
              "published_at_kst":"2026-10-14T15:00:00+09:00"}
        body="High Bandwidth Flash HBF High-Level Base Die Specification V1.0.0 final"
        self.assertEqual(w.parse_hbf_ocp_version(item,body),[])
        self.assertEqual(w.parse_hbf_company_milestones(item,
            "SK hynix completed HBF customer qualification"),[])
        another="HBF architecture overview. Random SSD Specification V2.0.0"
        self.assertEqual(w.parse_hbf_ocp_version(
            dict(item,direct_link=w.HBF_OCP_STORAGE_URL),another),[])
    def test_hbf_2027_january_target_does_not_prove_final(self):
        item={"direct_link":w.HBF_OCP_STORAGE_URL,"published_at_kst":"2027-01-05T10:00:00+09:00"}
        body=("High Bandwidth Flash HBF High-Level Base Die Specification V0.7.0. "
              "A final specification is expected in January 2027.")
        rec=w.parse_hbf_ocp_version(item,body)[0]
        self.assertFalse(rec["value"]["final_spec_officially_confirmed"])
        old={"axis":"hbf_ocp_spec","value":{"version":"0.7.0","final_spec_officially_confirmed":False}}
        self.assertEqual(w.comparison(old,rec),[])
    def test_hbf_ocp_actual_revision_changes_once(self):
        item={"direct_link":w.HBF_OCP_STORAGE_URL,"published_at_kst":"2027-01-15T10:00:00+09:00"}
        a=w.parse_hbf_ocp_version(item,"High Bandwidth Flash (HBF) High-Level Base Die Specification V0.7.0")[0]
        b=w.parse_hbf_ocp_version(item,"High Bandwidth Flash (HBF) High-Level Base Die Specification V1.0.0")[0]
        self.assertEqual(b["value"]["publication_stage"],"public_spec")
        self.assertTrue(any("0.7.0→1.0.0" in z for z in w.comparison(a,b)))
        self.assertEqual(w.comparison(b,b),[])
        self.assertEqual(w.comparison(b,a),[])
    def test_hbf_real_final_requires_explicit_ocp_text(self):
        item={"direct_link":w.HBF_OCP_STORAGE_URL,"published_at_kst":"2027-01-15T10:00:00+09:00"}
        rec=w.parse_hbf_ocp_version(item,
          "High Bandwidth Flash (HBF) final specification. High Bandwidth Flash (HBF) High-Level Base Die Specification V1.0.0")[0]
        self.assertTrue(rec["value"]["final_spec_officially_confirmed"])
    def test_hbf_google_tenstorrent_are_partners_not_confirmed_buyers(self):
        item={"direct_link":"https://news.skhynix.co.kr/hbf-at-fms-2026/",
              "published_at_kst":"2026-08-04T10:00:00+09:00","source":"SK하이닉스"}
        body=("SK hynix Sandisk unveiled HBF public specification. "
              "Google and Tenstorrent joined as HBF consortium members. "
              "High-performance 375-layer eSSD mass production is targeted for 2027.")
        self.assertEqual(w.parse_hbf_company_milestones(item,body),[])
    def test_hbf_actual_customer_qualification_requires_issuer_and_completed(self):
        body="SK hynix completed HBF customer qualification for AI inference chips."
        item={"direct_link":"https://news.skhynix.co.kr/hbf-customer-official/",
              "published_at_kst":"2027-03-01T10:00:00+09:00","title":"고객 검증"}
        official=w.parse_hbf_company_milestones(item,body)
        self.assertEqual(official[0]["value"]["stage"],"customer_qualified")
        self.assertEqual(w.parse_hbf_company_milestones(dict(item,direct_link="https://newspim.com/test"),body),[])
        expected="SK hynix plans HBF customer qualification in 2027."
        self.assertEqual(w.parse_hbf_company_milestones(item,expected),[])
    def test_hbf_only_explicit_mass_production_can_trigger(self):
        item={"direct_link":"https://news.skhynix.co.kr/hbf-mass-production/",
              "published_at_kst":"2028-01-01T10:00:00+09:00","title":"HBF 실제 양산"}
        rows=w.parse_hbf_company_milestones(item,
            "SK hynix has begun HBF mass production for AI inference.")
        self.assertEqual(rows[0]["value"]["stage"],"mass_production")
        old=dict(rows[0]);old["value"]=dict(old["value"],stage="customer_qualified")
        self.assertTrue(w.comparison(old,rows[0]))
        self.assertEqual(w.comparison(rows[0],old),[])
    def test_hbf_baselines_seed_without_retroactive_alert(self):
        import json
        source=json.loads((pathlib.Path(__file__).resolve().parents[1]/"data/hbm_memory_baselines.json").read_text(encoding="utf-8"))
        base=[x for x in source["records"] if x["axis"].startswith("hbf_")]
        self.assertEqual(len(base),2)
        state=w.update_state({},[],__import__("datetime").datetime(2026,10,14,17,0),base)
        self.assertEqual(state["hbf_track_version"],w.HBF_TRACK_VERSION)
        self.assertFalse(state["pending"])
        self.assertFalse(state["latest"]["hbf_ocp_spec|ocp|base_die"]["value"]["final_spec_officially_confirmed"])
    def test_hbf_alert_separates_specs_from_sales_and_warehouses(self):
        import json
        data=json.loads((pathlib.Path(__file__).resolve().parents[1]/"data/hbm_memory_baselines.json").read_text(encoding="utf-8"))
        r=next(x for x in data["records"] if x["axis"]=="hbf_ocp_spec")
        msg=w.render({"record":r,"old":None,"reasons":["최초 버전"]})
        self.assertIn("UCIe",msg)
        self.assertIn("양산 매출",msg)
        self.assertIn("고객 검증",msg)
        self.assertIn("원문",msg)


    def test_hbf_new_official_revision_does_not_carry_old_numeric_specification(self):
        item={"direct_link":w.HBF_OCP_STORAGE_URL,"published_at_kst":"2027-02-01T09:00:00+09:00"}
        rec=w.parse_hbf_ocp_version(
            item,"High Bandwidth Flash (HBF) High-Level Base Die Specification V1.0.0")[0]
        self.assertIsNone(rec["value"]["spec_bandwidth_max_tbps"])
        self.assertIsNone(rec["value"]["spec_capacity_max_gb"])
        out=w.render({"record":rec,"old":None,"reasons":["새 규격"]})
        self.assertIn("기존 V0.7.0 수치 재사용 금지",out)
        self.assertNotIn("최대 512GB",out)

    def test_generic_hbf_commentary_without_milestone_does_not_crowd_existing_feeds(self):
        self.assertFalse(w.is_axis_text("HBF may become important for AI demand in the future"))
        self.assertTrue(w.is_axis_text("SK hynix HBF final specification January 2027"))
        self.assertTrue(w.is_axis_text("HBF 2027년 1월 최종 규격 일정 발표"))


    def test_nvidia_glass_reported_supplier_interest_stays_at_baseline(self):
        item={"title":"NVIDIA increases its bet on glass substrates",
              "source":"GMT EIGHT","description":"",
              "published_at_kst":"2026-10-25T08:00:00+09:00",
              "direct_link":"https://gmt8press.com/flash/detail/1531939"}
        body=("NVIDIA is evaluating glass substrates for future AI GPU packages. "
              "SCHMID works with companies in NVIDIA, Intel and AMD supply chains.")
        rows=w.parse_nvidia_glass_adoption(item,body)
        self.assertEqual(len(rows),1)
        self.assertEqual(rows[0]["value"]["stage"],"reported_evaluation")
        self.assertEqual(rows[0]["evidence"],"reported")
        self.assertFalse(rows[0]["value"]["nvidia_glass_contract_confirmed"])

    def test_nvidia_organic_abf_substrate_contract_is_not_glass_core(self):
        item={"direct_link":"https://nvidianews.nvidia.com/news/substrate-expansion",
              "source":"NVIDIA","title":"Partnership",
              "published_at_kst":"2026-10-21T10:00:00+09:00"}
        body=("NVIDIA and Samsung Electro-Mechanics signed a multiyear ABF package substrate "
              "supply agreement beginning in 2026. IBIDEN and Unimicron will increase substrate "
              "capacity 2.5x over the next three years.")
        self.assertEqual(w.parse_nvidia_glass_adoption(item,body),[])

    def test_nvidia_corning_optical_fiber_glass_is_not_glass_core(self):
        item={"direct_link":"https://nvidianews.nvidia.com/news/nvidia-and-corning",
              "source":"NVIDIA","title":"NVIDIA Corning",
              "published_at_kst":"2026-05-06T10:00:00+09:00"}
        body="NVIDIA and Corning expand optical fiber glass connectivity plants by 10x."
        self.assertEqual(w.parse_nvidia_glass_adoption(item,body),[])

    def test_nvidia_glass_true_official_contract_requires_explicit_same_clause(self):
        item={"direct_link":"https://nvidianews.nvidia.com/news/nvidia-glass-core",
              "source":"NVIDIA","title":"Official NVIDIA announcement",
              "published_at_kst":"2027-08-01T11:00:00+09:00"}
        body="NVIDIA signed a supply agreement for glass-core substrates with Example Semiconductor."
        rows=w.parse_nvidia_glass_adoption(item,body)
        self.assertEqual(len(rows),1)
        self.assertEqual(rows[0]["evidence"],"official")
        self.assertEqual(rows[0]["value"]["stage"],"official_supply_contract")
        seed={"axis":"glass_nvidia_adoption",
              "value":{"stage":"reported_evaluation"},"evidence":"reported"}
        self.assertTrue(w.comparison(seed,rows[0]))

    def test_nvidia_glass_roadmap_forecast_is_not_official_mass_production(self):
        item={"direct_link":"https://nvidianews.nvidia.com/news/glass-core",
              "source":"NVIDIA","title":"Future roadmap",
              "published_at_kst":"2027-01-01T11:00:00+09:00"}
        body="NVIDIA plans to begin mass production using glass-core substrates in 2028."
        rows=w.parse_nvidia_glass_adoption(item,body)
        self.assertEqual(rows[0]["value"]["stage"],"reported_evaluation")

    def test_nvidia_supplier_chain_reference_is_not_joint_development(self):
        item={"direct_link":"https://www.schmid-group.com/en/press/nvidia-suppliers",
              "source":"SCHMID","title":"Supply chain",
              "published_at_kst":"2026-10-25T12:00:00+09:00"}
        body="SCHMID jointly develops glass-core substrates with companies in NVIDIA's supply chain."
        rows=w.parse_nvidia_glass_adoption(item,body)
        self.assertEqual(rows[0]["value"]["stage"],"reported_evaluation")

    def test_nvidia_glass_initial_seed_is_silent_and_duplicate_reprint_silent(self):
        import json
        from datetime import datetime
        seed=next(x for x in json.loads(
            (pathlib.Path(__file__).resolve().parents[1]/"data/hbm_memory_baselines.json")
            .read_text(encoding="utf-8"))["records"]
            if x["axis"]=="glass_nvidia_adoption")
        now=datetime(2026,10,26,12,0,0)
        state=w.update_state({},[seed],now,[seed])
        self.assertEqual(state["nvidia_glass_track_version"],1)
        self.assertNotIn(seed["key"],state["pending"])
        reprint=dict(seed,as_of="2026-10-25",
                     source_url="https://gmt8press.com/flash/detail/1531939")
        again=w.update_state(state,[reprint],now,[seed])
        self.assertNotIn(seed["key"],again["pending"])

    def test_nvidia_glass_company_stage_not_promoted_by_media_reprint(self):
        official={"axis":"glass_nvidia_adoption",
                  "value":{"stage":"official_customer_qualification"},"evidence":"official"}
        media={"axis":"glass_nvidia_adoption",
               "value":{"stage":"reported_evaluation"},"evidence":"reported"}
        self.assertEqual(w.comparison(official,media),[])
        self.assertTrue(w.is_axis_text("NVIDIA increases its bet on glass substrates"))
        self.assertTrue(w.is_axis_text("英伟达玻璃基板客户认证待确认"))


if __name__ == "__main__":
    unittest.main()
