import pathlib
import sys
import unittest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "scripts"))
import ai_inference_structure_watch as m


class InferenceStructureWatchTests(unittest.TestCase):
    def test_coreweave_power_change_is_material(self):
        previous = {"neocloud": {"CoreWeave": {"active_power_gw": 1.5, "contracted_power_gw": 4.2}}}
        update = {"company": "CoreWeave", "metrics": {"active_power_gw": 1.7}, "negative": False}
        events = m.compare_neocloud(previous, update)
        self.assertTrue(any(e["label"] == "활성 전력" for e in events))

    def test_revenue_per_mw_ten_percent_is_material(self):
        previous = {"neocloud": {"CoreWeave": {"annualized_revenue_per_mw_usd_m": 40.0}}}
        update = {"company": "CoreWeave", "metrics": {"annualized_revenue_per_mw_usd_m": 44.1}, "negative": False}
        events = m.compare_neocloud(previous, update)
        self.assertTrue(any(e["label"] == "MW당 연환산 매출" for e in events))

    def test_edge_outlook_only_is_not_event(self):
        text = "We expect the edge AI inference market to grow rapidly across regional locations."
        self.assertEqual(m.parse_edge_actual(text, "https://www.att.com/example", "outlook"), {})

    def test_edge_actual_requires_commercial_scale_evidence(self):
        text = "We signed an agreement to deploy AI inference at regional edge sites with 120 MW of capacity."
        event = m.parse_edge_actual(text, "https://www.att.com/example", "regional AI inference")
        self.assertEqual(event["kind"], "edge_actual")


    def test_dell_security_article_is_not_edge_commercial_event(self):
        text = (
            "Autonomous AI agents require runtime security for enterprise inference deployment. "
            "The author has worked across Edge, 5G and AI/HPC. "
            "Dell AI Factory is available today for enterprise customers."
        )
        event = m.parse_edge_actual(
            text,
            "https://www.dell.com/en-us/blog/a-new-era-of-ai-agents-demands-a-new-security-model/",
            "A New Era of AI Agents Demands a New Security Model",
        )
        self.assertEqual(event, {})

    def test_amd_acquisition_is_not_edge_commercial_event(self):
        text = (
            "AMD entered into a definitive agreement to acquire World Labs for $8.2 billion. "
            "The acquisition supports physical AI, robotics, simulation and future edge infrastructure."
        )
        event = m.parse_edge_actual(
            text,
            "https://www.amd.com/en/example",
            "AMD to Acquire World Labs to Advance the Future of AI Compute",
        )
        self.assertEqual(event, {})

    def test_compact_alert_omits_configuration_boilerplate(self):
        latest = {
            "neocloud": {
                "CoreWeave": {
                    "active_power_gw": 1.5,
                    "contracted_power_gw": 4.2,
                    "annualized_revenue_per_mw_usd_m": 40.0,
                }
            }
        }
        alert = m.build_alert(
            [{"kind": "edge_actual", "company": "Example", "title": "Regional AI inference", "scale": "120 MW", "money": ""}],
            latest,
            ["https://www.att.com/example"],
        )
        self.assertIn("<b>변화</b>", alert)
        self.assertIn("<b>의미</b>", alert)
        self.assertIn("<b>다음 확인</b>", alert)
        self.assertNotIn("<b>강한 알림 기준</b>", alert)
        self.assertNotIn("<b>하향 반전 게이트</b>", alert)
        self.assertNotIn("<b>숨은 역풍·실패모드</b>", alert)
        self.assertNotIn("<b>제외 조건</b>", alert)

    def test_upstream_bootstrap_is_silent(self):
        after = {"agentic_ratio": "1:1", "samsung_server_cpu_fcbga_mass_production": True}
        self.assertEqual(m.upstream_events({}, after), [])

    def test_upstream_ratio_change_is_event(self):
        before = {"agentic_ratio": "1:2"}
        after = {"agentic_ratio": "1:1"}
        events = m.upstream_events(before, after)
        self.assertTrue(any(e["label"] == "에이전트형 CPU:GPU 비율" for e in events))

    def test_nebius_guidance_not_misread_as_actual(self):
        text = "We are raising our contracted power guidance to more than 4 GW by year-end."
        parsed = m.parse_nebius(text, "https://nebius.com/newsroom/example")
        self.assertEqual(parsed["metrics"].get("contracted_power_guidance_gw"), 4.0)
        self.assertNotIn("contracted_power_gw", parsed["metrics"])


    def test_ytl_actual_contracted_power_and_segment_revenue_parse(self):
        text = (
            "The data center segment achieved revenue MYR 225 million for the current quarter. "
            "With 298 MW in data center capacity already contracted, the group continues its rollout."
        )
        parsed = m.parse_ytl(text, "https://www.ytlpowerinternational.com/press-releases/example")
        self.assertAlmostEqual(parsed["metrics"]["contracted_power_gw"], 0.298)
        self.assertEqual(parsed["metrics"]["data_center_segment_revenue_myr_m"], 225.0)

    def test_ytl_revenue_change_is_material_at_ten_percent(self):
        previous = {"neocloud": {"YTL": {"data_center_segment_revenue_myr_m": 225.0}}}
        update = {
            "company": "YTL",
            "metrics": {"data_center_segment_revenue_myr_m": 250.0},
            "negative": False,
        }
        events = m.compare_neocloud(previous, update)
        self.assertTrue(any(e["label"] == "데이터센터 부문 매출" for e in events))

    def test_ytl_alert_does_not_show_unrelated_coreweave_baseline(self):
        latest = {
            "neocloud": {
                "CoreWeave": {"active_power_gw": 1.5, "contracted_power_gw": 4.2, "annualized_revenue_per_mw_usd_m": 40.0},
                "YTL": {"contracted_power_gw": 0.298, "data_center_segment_revenue_myr_m": 250.0},
            }
        }
        alert = m.build_alert(
            [{"kind": "neocloud_metric", "company": "YTL", "label": "데이터센터 부문 매출", "before": 225.0, "after": 250.0, "unit": "MYRm"}],
            latest,
            ["https://www.ytlpowerinternational.com/press-releases/example"],
        )
        self.assertIn("YTL:", alert)
        self.assertNotIn("CoreWeave:", alert)

    def test_contractual_termination_right_is_not_downside_event(self):
        text = "Microsoft has the right to terminate a GPU Service if delivery dates are missed."
        parsed = m.parse_nebius(text, "https://nebius.com/newsroom/example")
        self.assertEqual(parsed, {})

    def test_cpu_ratio_parser_prefers_agentic_one_to_one(self):
        text = "Agentic AI changes the CPU and GPU equation from 1 CPU to 8 GPU to 1:1 or better."
        parsed = m.parse_cpu_ratio(text, "https://www.intel.com/example")
        self.assertEqual(parsed["company"], "Intel")
        self.assertEqual(parsed["cpu_per_gpu"], 1.0)


    def test_ocp_official_demo_metrics_are_scoped(self):
        body=("OCP Global Summit 2026. Samsung and AMD collaborated to validate CXL memory. "
              "CMM-D MD310 provides DCD-based CXL memory pooling. "
              "The demo delivers up to 38% lower TTFT and up to 3.3x higher goodput. "
              "A production deployment at Samsung Semiconductor's US campus with SGLang "
              "delivered 5–7x KV cache utilization. "
              "BM1773 256TB QLC SSD; PM1763 up to 28.4 GB/s sequential read. "
              "FDP LMCache KV cache. LPDDR5X-PIM up to 8x higher effective bandwidth "
              "and LLM inference performance (TPS) by up to 3x.")
        state=m.parse_samsung_ocp_2026(body,m.OCP_SOURCE)
        self.assertEqual(state["demo_ttft_reduction_max_pct"],38)
        self.assertEqual(state["demo_goodput_max_x"],3.3)
        self.assertEqual(state["internal_kv_cache_min_x"],5)
        self.assertEqual(state["internal_kv_cache_max_x"],7)
        self.assertEqual(state["bm1773_qlc_capacity_tb"],256)
        self.assertEqual(state["pm1763_read_gbps"],28.4)
        self.assertEqual(state["lpddr5x_pim_tps_max_x"],3)
        self.assertFalse(state["external_amd_paid_order_confirmed"])
        self.assertFalse(state["groq_2nm_lpu_confirmed"])

    def test_trendforce_reprint_cannot_fake_official_ocp_source(self):
        text=("OCP Global Summit 2026 Samsung and AMD collaborated to validate CXL memory "
              "CMM-D MD310 DCD-based CXL memory pooling 38% 3.3x")
        self.assertEqual(m.parse_samsung_ocp_2026(text,"https://www.trendforce.com/news/foo"),{})

    def test_ocp_demo_replays_are_silent_after_initial_event(self):
        a={"product":"CMM-D MD310","amd_cxl_joint_validation":True,
           "demo_ttft_reduction_max_pct":38.0,"demo_goodput_max_x":3.3}
        self.assertEqual(len(m.compare_ocp_memory({},a)),1)
        self.assertEqual(m.compare_ocp_memory(a,a),[])
        b=dict(a,demo_goodput_max_x=3.6)
        self.assertEqual(len(m.compare_ocp_memory(a,b)),1)

    def test_amd_joint_demo_is_not_new_paid_contract(self):
        body=("OCP Global Summit 2026 Samsung and AMD collaborated to validate CXL memory "
              "CMM-D MD310 provides DCD-based CXL memory pooling.")
        s=m.parse_samsung_ocp_2026(body,m.OCP_SOURCE)
        self.assertFalse(s["external_amd_paid_order_confirmed"])
        self.assertNotIn("mass_production",str(s))

    def test_groq_generic_2nm_wafer_display_does_not_promote_4nm_lpu(self):
        text=("Samsung Foundry showed Groq 3 LPU 4nm wafers. "
              "Separately, it displayed a 2nm GAA wafer.")
        self.assertEqual(m.parse_samsung_official_ai_milestone(
            text,"https://semiconductor.samsung.com/news-events/tech-blog/ocp"),{})

    def test_groq_mass_production_requires_samsung_owned_completion(self):
        text="Samsung has begun mass production of Groq 3 LPU with Samsung Foundry at 4nm."
        good=m.parse_samsung_official_ai_milestone(
            text,"https://semiconductor.samsung.com/news-events/news/groq")
        self.assertEqual(good["kind"],"groq_foundry")
        self.assertEqual(good["stage"],"mass_production")
        self.assertEqual(m.parse_samsung_official_ai_milestone(
            text,"https://www.zdnet.co.kr/article/groq"),{})

    def test_groq_future_plan_cannot_become_actual_production(self):
        text="Samsung Foundry plans to begin mass production of Groq 3 LPU at 4nm in 2027."
        self.assertEqual(m.parse_samsung_official_ai_milestone(
            text,"https://semiconductor.samsung.com/news-events/news/groq"),{})

    def test_prior_4nm_groq_wafer_baseline_is_not_resent(self):
        self.assertEqual(m.BASELINE["groq_foundry"]["stage"],"wafer_display")
        self.assertEqual(m.stage_upgrade(m.BASELINE["groq_foundry"],
                         {"kind":"groq_foundry","company":"삼성전자","stage":"wafer_display"}),[])

    def test_ocp_alert_explains_internal_vs_customer_and_links_official_source(self):
        latest={"ocp_memory_system":{"demo_ttft_reduction_max_pct":38,
                 "demo_goodput_max_x":3.3,"internal_memory_node_deployed":True,
                 "internal_kv_cache_min_x":5,"internal_kv_cache_max_x":7}}
        text=m.build_alert([{"kind":"ocp_memory","company":"삼성전자·AMD",
             "label":"공식 검증"}],latest,[m.OCP_SOURCE])
        self.assertIn("3.3배",text)
        self.assertIn("사내",text)
        self.assertIn("외부",text)
        self.assertIn(m.OCP_SOURCE,text)
        self.assertNotIn("CoreWeave:",text)



if __name__ == "__main__":
    unittest.main()
