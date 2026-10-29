import pathlib
import sys
import unittest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "scripts"))
import abf_cpu_monetization_watch as w




class UnimicronTargetAndCapexEvidenceTests(unittest.TestCase):
    """Price targets ≠ substrate ASP. Board equipment preorders ≠ paid capex."""

    def test_broker_target_math_and_reported_eps_do_not_become_actual_prices(self):
        context = w.UNIMICRON_TARGET_CONTEXT
        self.assertEqual((context["target_previous_twd"], context["target_new_twd"]), (1010, 1300))
        self.assertAlmostEqual((1300 / 1010 - 1) * 100, 28.7128712871, places=5)
        self.assertEqual((context["broker_pe_prior"], context["broker_pe_current"]), (28, 30))
        self.assertEqual((context["broker_eps_2026_twd"], context["broker_eps_2027_twd"]), (25.22, 43.36))
        self.assertFalse(context["official_contract_price_change_confirmed"])
        self.assertIn("broker note", context["source_kind"])

    def test_company_capex_preorder_not_cash_payment_and_not_nvidia_revenue(self):
        context = w.UNIMICRON_TARGET_CONTEXT
        self.assertTrue(context["board_preorder_not_cash_paid_or_committed_customer_revenue"])
        self.assertEqual(context["board_incremental_preorder_twd_100m"], 509)
        msg = w.unimicron_broker_notice(context)
        self.assertIn("509억대만달러(약 2조1,090억원)", msg)
        self.assertIn("실제 지급액·ABF 전용 투자액·확정 고객매출 아님", msg)
        self.assertIn("자체 자금 + 은행 융자", msg)
        self.assertIn("10/27 이사회", msg)

    def test_2026_oct_28_forecast_message_preserves_report_date_and_currency(self):
        msg = w.unimicron_broker_notice(w.UNIMICRON_TARGET_CONTEXT)
        self.assertIn("1,010대만달러(약 41,848원)", msg)
        self.assertIn("1,300대만달러(약 53,864원)", msg)
        self.assertIn("28.7%", msg)
        self.assertIn("28배 → 30배", msg)
        self.assertIn("526.5억대만달러(약 2조1,815억원)", msg)
        self.assertIn("Unimicron", msg)
        self.assertIn("증권사 실명 미공개", msg)
        self.assertNotIn("NVIDIA 단독 계약", msg)
        self.assertNotIn("ABF 가격 28.7%", msg)
        self.assertIn("실시간 환율 아님", msg)

    def test_existing_state_receipts_and_all_modules_are_not_reinitialized(self):
        prev = {"version":0,"already_seen_event_key":"keep","internal_last_message_id":342}
        new, first = w.unimicron_broker_update(prev)
        self.assertEqual(new["version"],1)
        self.assertEqual(new["already_seen_event_key"],"keep")
        self.assertEqual(new["internal_last_message_id"],342)
        self.assertIn("기판", first)
        again, second = w.unimicron_broker_update(new)
        self.assertEqual(second,"")
        self.assertEqual(again,new)

    def test_forecast_observation_does_not_trigger_goldman_or_customer_as_price_change(self):
        note = {
            "url":w.UNIMICRON_SOURCE_ARTICLE,
            "published_at_kst":"2026-10-28T09:00:00+09:00",
            "parsed":{"kind":"research_update"},
        }
        original = {**w.BASELINE,"area_structure":w.ABF_AREA_STRUCTURE_BASELINE}
        self.assertEqual(w.material_events(original,[note]),[])
        merged = w.merge_state(original,[note],[])
        self.assertEqual(merged["area_structure"]["research_forecast"]["abf_shortfall_2028_pct"],51.0)

class ABFHistoricalModelVintageTests(unittest.TestCase):
    def test_old_and_new_goldman_are_distinct_broker_forecasts(self):
        ctx = w.ABF_VINTAGE_CONTEXT
        self.assertEqual(ctx["old_shortfall_pct"], {"2026H2":10.0,"2027":21.0,"2028":42.0})
        self.assertEqual(ctx["recent_shortfall_pct"], {"2026H2":14.0,"2027":34.0,"2028":51.0})
        self.assertEqual(ctx["old_estimate_vintage"], "2026-02-03")
        self.assertEqual(ctx["recent_public_recap_as_of"], "2026-09-30")
        self.assertTrue(ctx["denominator_and_product_mix_not_fully_disclosed"])
        self.assertTrue(ctx["pcb_industry_total_is_not_abf_tam"])

    def test_october_reprint_does_not_reset_recent_goldman_facts(self):
        previous = {**w.BASELINE,"area_structure":w.ABF_AREA_STRUCTURE_BASELINE}
        item = {
            "url": "https://finance.technews.tw/2026/10/27/example",
            "title": "2026 October 27 PCB output article",
            "published_at_kst": "2026-10-27T18:00:00+09:00",
            "full_text": "February 2026 Goldman Sachs report forecast 10% in 2H26, 21% in 2027, 42% in 2028.",
            "parsed": {"kind":"research_update",
                       "goldman_abf_shortfall_2h2026_pct":10.0,
                       "goldman_abf_shortfall_2027_pct":21.0,
                       "goldman_abf_shortfall_2028_pct":42.0},
        }
        filt = w.guard_stale_goldman_recap(item)
        self.assertNotIn("goldman_abf_shortfall_2028_pct", filt["parsed"])
        self.assertEqual(w.material_events(previous,[filt]), [])
        merged = w.merge_state(previous,[filt],[])
        self.assertEqual(merged["area_structure"]["research_forecast"]["abf_shortfall_2028_pct"],51.0)

    def test_goldman_date_must_belong_to_named_research_and_beat_sept(self):
        dated = "Goldman Sachs research report dated 2026-10-27 projects revised shortfall"
        self.assertEqual(w.explicit_goldman_report_vintage(dated),"2026-10-27")
        self.assertEqual(w.explicit_goldman_report_vintage("Article published 2026-10-27, Goldman Sachs February forecast."),"")
        self.assertEqual(w.explicit_goldman_report_vintage("Goldman Sachs research report dated 2026-02-03 forecast"),"2026-02-03")
        self.assertEqual(w.explicit_goldman_report_vintage("Goldman Sachs research report dated 2026-99-99 forecast"),"")

    def test_article_date_and_firm_quote_are_not_research_vintage(self):
        misleading = (
            "Article published on 2026-10-27. Goldman Sachs February 2026 "
            "research forecast 10%/21%/42% for ABF shortages."
        )
        self.assertEqual(w.explicit_goldman_report_vintage(misleading), "")
        after = (
            "Goldman Sachs old forecast as of February 2026 and story "
            "published 2026-10-27. The source release date is unknown."
        )
        self.assertEqual(w.explicit_goldman_report_vintage(after), "")
        actual = "Goldman Sachs research report dated 2026-10-26 raises its ABF assumptions."
        self.assertEqual(w.explicit_goldman_report_vintage(actual), "2026-10-26")

    def test_later_article_must_not_change_previously_confirmed_model(self):
        item={
            "url":"https://www.skis.com.tw/skis/Report/industry/example.html",
            "title":"October 2026 latest chip shortage discussion",
            "full_text":"Article published 2026-10-27, citing Goldman Sachs February research report 10% in 2H26, 21% in 2027, 42% in 2028.",
            "parsed":{"kind":"research_update",
                      "goldman_abf_shortfall_2h2026_pct":10.0,
                      "goldman_abf_shortfall_2027_pct":21.0,
                      "goldman_abf_shortfall_2028_pct":42.0},
        }
        filtered=w.guard_stale_goldman_recap(item)
        self.assertNotIn("goldman_abf_shortfall_2027_pct", filtered["parsed"])
        prev={**w.BASELINE,"area_structure":w.ABF_AREA_STRUCTURE_BASELINE}
        updated=w.merge_state(prev,[filtered],[])
        self.assertEqual(updated["area_structure"]["research_forecast"]["abf_shortfall_2h2026_pct"],14.0)
        self.assertEqual(updated["area_structure"]["research_forecast"]["abf_shortfall_2027_pct"],34.0)
        self.assertEqual(updated["area_structure"]["research_forecast"]["abf_shortfall_2028_pct"],51.0)

    def test_research_title_cannot_borrow_a_later_news_publication_date(self):
        self.assertEqual(w.explicit_goldman_report_vintage(
            "Goldman Sachs old forecast as of February 2026 and story published 2026-10-27."),"")
        self.assertEqual(w.explicit_goldman_report_vintage(
            "An article on 2026-10-27 quotes Goldman Sachs research report dated 2026-02-03."),"2026-02-03")
        self.assertEqual(w.explicit_goldman_report_vintage(
            "Goldman Sachs research report dated 2026-10-26 raised ABF assumptions."),"2026-10-26")

    def test_standalone_abf_collection_never_wipes_other_rubin_state(self):
        import copy, json, tempfile
        from unittest import mock
        with tempfile.TemporaryDirectory() as folder:
            root = pathlib.Path(folder)
            state, pending, alert = root/"rubin.json", root/"pending.json", root/"alert.md"
            old = copy.deepcopy(w.BASELINE)
            old["area_structure"] = copy.deepcopy(w.ABF_AREA_STRUCTURE_BASELINE)
            old["goldman_vintage_context"] = copy.deepcopy(w.ABF_VINTAGE_CONTEXT)
            original = {
                "abf_cpu_monetization": old,
                "ai_component_leadtime": {"as_of":"2026-10-19","components":{"HDD":{"current":"50"}}},
                "telegram_message_id": 340,
                "unrelated_module": {"protect":True},
            }
            state.write_text(json.dumps(original,ensure_ascii=False),encoding="utf-8")
            with mock.patch.object(w,"STATE_PATH",state), \
                 mock.patch.object(w,"PENDING_PATH",pending), \
                 mock.patch.object(w,"ALERT_PATH",alert), \
                 mock.patch.object(w,"discover",return_value=[]), \
                 mock.patch.object(w,"verify_nvidia_abf_press",return_value=({},{})):
                w.main()
                result=json.loads(pending.read_text(encoding="utf-8"))
            self.assertEqual(result["telegram_message_id"],340)
            self.assertEqual(result["unrelated_module"],{"protect":True})
            self.assertEqual(result["ai_component_leadtime"]["components"]["HDD"]["current"],"50")
            self.assertEqual(result["abf_cpu_monetization"]["goldman_vintage_context"]["version"],1)

    def test_new_verified_goldman_raises_forecast_after_explicit_date(self):
        item = {
            "url":"https://www.skis.com.tw/skis/Report/industry/example.html",
            "published_at_kst":"2026-10-27T19:30:00+09:00",
            "full_text":"Goldman Sachs research report dated 2026-10-26 sees ABF 20% in 2H26 40% in 2027 60% in 2028.",
            "parsed":{"kind":"research_update","goldman_abf_shortfall_2h2026_pct":20.0,
                      "goldman_abf_shortfall_2027_pct":40.0,
                      "goldman_abf_shortfall_2028_pct":60.0},
        }
        approved = w.guard_stale_goldman_recap(item)
        self.assertEqual(approved["parsed"]["goldman_report_vintage"],"2026-10-26")
        old = {**w.BASELINE,"area_structure":w.ABF_AREA_STRUCTURE_BASELINE}
        events = w.material_events(old,[approved])
        self.assertEqual(len([x for x in events if x["type"]=="supply_gap_forecast"]),3)
        merged = w.merge_state(old,[approved],events)
        self.assertEqual(merged["area_structure"]["research_forecast"]["abf_shortfall_2028_pct"],60.0)

    def test_same_tuples_no_false_revision_and_no_double_event(self):
        ctx={"goldman_vintage_context":w.ABF_VINTAGE_CONTEXT}
        self.assertEqual(ctx["goldman_vintage_context"]["version"],w.ABF_VINTAGE_CONTEXT_VERSION)
        alert=w.build_abf_vintage_context_alert(ctx)
        for phrase in ("10%", "21%", "42%", "14%", "34%", "51%", "4%p", "13%p", "9%p", "2월", "9월말", "2.5배"):
            self.assertIn(phrase,alert)
        self.assertIn("계통접속",alert)
        self.assertIn("TechNews 기사 직접 본문은 접속 제한",alert)
        self.assertIn("실제 확정 부족률 아님",alert)
        self.assertLess(len(alert),2600)

    def test_forecast_update_filter_does_not_remove_bofa_or_physical_facts(self):
        item={
           "url":"https://www.xxquant.com/en/institution/example",
           "full_text":"Goldman Sachs report dated 2026-02-03 forecast",
           "parsed":{"kind":"research_update",
                     "goldman_abf_shortfall_2027_pct":21.0,
                     "bofa_abf_shortfall_2028_pct":22.0,
                     "feynman_2028_area_vs_2026_min_multiple":3.0},
        }
        approved=w.guard_stale_goldman_recap(item)
        self.assertNotIn("goldman_abf_shortfall_2027_pct",approved["parsed"])
        self.assertEqual(approved["parsed"]["bofa_abf_shortfall_2028_pct"],22.0)
        self.assertEqual(approved["parsed"]["feynman_2028_area_vs_2026_min_multiple"],3.0)

class AbfCpuMonetizationParseTests(unittest.TestCase):
    def test_official_ibiden_capex_and_sap(self):
        text = (
            "IBIDEN will invest approximately JPY 500 billion from FY2026 to FY2028. "
            "Gama Plant investment amount approximately JPY 220 billion. "
            "Mass production will commence from fiscal year 2027. "
            "SAP capacity will more than double by the end of FY2027."
        )
        parsed = w.parse_official_update(text, "https://www.ibiden.com/example")
        self.assertEqual(parsed["ibiden_capex_fy2026_2028_jpy_bn"], 500.0)
        self.assertEqual(parsed["ibiden_gama_capex_jpy_bn"], 220.0)
        self.assertEqual(parsed["ibiden_gama_mass_production_start_fy"], 2027)
        self.assertEqual(parsed["ibiden_sap_capacity_fy2027_multiple_min"], 2.0)

    def test_customer_sales_are_not_abf_share(self):
        text = (
            "Intel Corp. ¥ 76,709 million. "
            "Advanced Micro Devices Inc. ¥ 40,707 million. "
            "NVIDIA Corp. ¥ 75,077 million."
        )
        parsed = w.parse_official_update(text, "https://www.ibiden.com/example")
        sales = parsed["customer_sales_jpy_bn"]
        self.assertAlmostEqual(sales["Intel"], 76.709)
        self.assertAlmostEqual(sales["NVIDIA"], 75.077)
        self.assertNotIn("official_intel_abf_share_pct", parsed)

    def test_untrusted_macquarie_recap_does_not_parse(self):
        text = "Ibiden Intel 30% AMD 15% NVIDIA CPU substrate shipment started"
        self.assertEqual(w.parse_research_update(text, "https://example.com/foo"), {})

    def test_official_nvidia_cpu_confirmation(self):
        text = "Ibiden began mass production and shipment of package substrates for NVIDIA CPU."
        parsed = w.parse_official_update(text, "https://www.ibiden.com/example")
        self.assertTrue(parsed["official_nvidia_cpu_substrate_confirmed"])

    def test_official_ibiden_ai_server_sap_load_indices(self):
        text = (
            "Production load of substrate for AI server (Converted by SAP) "
            "CY24 1.0 Standard CY26 x1.8 CY28 x2.5."
        )
        parsed = w.parse_official_update(text, "https://www.ibiden.com/ir/items/en_kessannsetsumeiFY2025.pdf")
        self.assertEqual(parsed["ibiden_ai_server_sap_load_cy2024_index"], 1.0)
        self.assertEqual(parsed["ibiden_ai_server_sap_load_cy2026_index"], 1.8)
        self.assertEqual(parsed["ibiden_ai_server_sap_load_cy2028_index"], 2.5)

    def test_area_structure_baseline_uses_area_layers_not_unit_count(self):
        base = w.ABF_AREA_STRUCTURE_BASELINE
        off = base["official"]
        self.assertEqual(off["ajinomoto_pc_substrate_area_index"], 1.0)
        self.assertEqual(off["ajinomoto_hpc_substrate_area_index"], 3.5)
        self.assertEqual(off["ajinomoto_pc_abf_layers"], 6)
        self.assertEqual(off["ajinomoto_hpc_abf_layers"], 18)
        self.assertEqual(off["ajinomoto_hpc_abf_use_multiple_min"], 10.0)
        self.assertTrue(off["ibiden_area_multilayer_increases_sap_load"])
        self.assertEqual(off["ibiden_ai_server_sap_load_cy2024_index"], 1.0)
        self.assertEqual(off["ibiden_ai_server_sap_load_cy2026_index"], 1.8)
        self.assertEqual(off["ibiden_ai_server_sap_load_cy2028_index"], 2.5)
        self.assertEqual(base["research_forecast"]["abf_shortfall_2h2026_pct"], 14.0)
        self.assertFalse(base["comparison_guard"]["like_for_like_comparison_confirmed"])
        bofa = base["bofa_model"]
        self.assertEqual(bofa["prior_user_chart"]["same_chart_2021_ratio_pct"], -13.0)
        self.assertEqual(bofa["prior_user_chart"]["same_chart_2028_ratio_pct"], -16.0)
        self.assertEqual(bofa["prior_user_chart"]["same_chart_2028_shortage_minus_2021_pp"], 3.0)
        self.assertTrue(bofa["comparison_guard"]["prior_chart_2021_vs_2028_direct_same_chart"])
        self.assertFalse(bofa["comparison_guard"]["current_2028_vs_2021_direct_same_chart"])
        self.assertEqual(bofa["current_public_recap"]["abf_shortfall_2028_pct"], 19.0)

    def test_goldman_supply_gap_parser_keeps_source_specific_numbers(self):
        text = (
            "Goldman Sachs says the ABF substrate supply-demand gap is 14% in 2H26, "
            "34% in 2027 and the supply shortfall is 51% in 2028."
        )
        parsed = w.parse_research_update(text, "https://www.skis.com.tw/Report/industry/example.html")
        self.assertEqual(parsed["goldman_abf_shortfall_2h2026_pct"], 14.0)
        self.assertEqual(parsed["goldman_abf_shortfall_2027_pct"], 34.0)
        self.assertEqual(parsed["goldman_abf_shortfall_2028_pct"], 51.0)

    def test_bofa_revision_parser_keeps_prior_and_current_vintages(self):
        text = (
            "BofA expanded its ABF substrate shortage forecast for 2026-2028 "
            "from 4%/10%/16% to 7%/14%/19%. "
            "Server CPU share of ABF demand rose from 13%/14%/14% to 17%/21%/21%."
        )
        parsed = w.parse_research_update(
            text,
            "https://www.xxquant.com/en/institution/institutional-research/example",
        )
        self.assertEqual(parsed["bofa_prior_abf_shortfall_2026_pct"], 4.0)
        self.assertEqual(parsed["bofa_abf_shortfall_2026_pct"], 7.0)
        self.assertEqual(parsed["bofa_abf_shortfall_2027_pct"], 14.0)
        self.assertEqual(parsed["bofa_abf_shortfall_2028_pct"], 19.0)
        self.assertEqual(parsed["bofa_prior_server_cpu_abf_demand_share_2027_pct"], 14.0)
        self.assertEqual(parsed["bofa_server_cpu_abf_demand_share_2027_pct"], 21.0)

    def test_feynman_area_parser_requires_research_scope(self):
        text = "Feynman 2028 ABF substrate area is estimated at 3-5 times the 2026 level."
        parsed = w.parse_research_update(text, "https://www.edaily.co.kr/example")
        self.assertEqual(parsed["feynman_2028_area_vs_2026_min_multiple"], 3.0)
        self.assertEqual(parsed["feynman_2028_area_vs_2026_max_multiple"], 5.0)


class AbfCpuMonetizationMaterialityTests(unittest.TestCase):
    def test_sap_ten_percent_change_triggers(self):
        previous = w.BASELINE
        updates = [{
            "url": "https://www.ibiden.com/new",
            "parsed": {
                "kind": "official_update",
                "ibiden_sap_capacity_fy2027_multiple_min": 2.3,
            }
        }]
        ev = w.material_events(previous, updates)
        self.assertTrue(any(x["key"] == "ibiden_sap_capacity_fy2027_multiple_min" for x in ev))

    def test_research_share_five_pp_change_triggers(self):
        previous = w.BASELINE
        updates = [{
            "url": "https://www.reuters.com/example",
            "parsed": {
                "kind": "research_update",
                "macquarie_intel_abf_share_pct": 36.0,
            }
        }]
        ev = w.material_events(previous, updates)
        self.assertTrue(any(x["type"] == "research_share" for x in ev))

    def test_same_research_baseline_is_quiet(self):
        previous = w.BASELINE
        updates = [{
            "url": "https://www.reuters.com/example",
            "parsed": {
                "kind": "research_update",
                "macquarie_intel_abf_share_pct": 30.0,
                "macquarie_amd_abf_share_pct": 15.0,
                "macquarie_nvidia_cpu_substrate_shipping": True,
            }
        }]
        self.assertEqual(w.material_events(previous, updates), [])

    def test_bofa_three_pp_revision_triggers(self):
        previous = {**w.BASELINE, "area_structure": w.ABF_AREA_STRUCTURE_BASELINE}
        updates = [{
            "url": "https://www.xxquant.com/en/institution/institutional-research/example",
            "parsed": {
                "kind": "research_update",
                "bofa_abf_shortfall_2028_pct": 22.0,
            },
        }]
        ev = w.material_events(previous, updates)
        self.assertTrue(any(x["type"] == "bofa_supply_gap_forecast" and x["key"] == "bofa_abf_shortfall_2028_pct" for x in ev))

    def test_bofa_server_cpu_share_three_pp_revision_triggers(self):
        previous = {**w.BASELINE, "area_structure": w.ABF_AREA_STRUCTURE_BASELINE}
        updates = [{
            "url": "https://www.xxquant.com/en/institution/institutional-research/example",
            "parsed": {
                "kind": "research_update",
                "bofa_server_cpu_abf_demand_share_2027_pct": 24.0,
            },
        }]
        ev = w.material_events(previous, updates)
        self.assertTrue(any(x["type"] == "bofa_server_cpu_share_forecast" for x in ev))

    def test_goldman_2h2026_five_pp_revision_triggers(self):
        previous = {**w.BASELINE, "area_structure": w.ABF_AREA_STRUCTURE_BASELINE}
        updates = [{
            "url": "https://www.skis.com.tw/Report/industry/example.html",
            "parsed": {
                "kind": "research_update",
                "goldman_abf_shortfall_2h2026_pct": 20.0,
            },
        }]
        ev = w.material_events(previous, updates)
        self.assertTrue(any(x["type"] == "supply_gap_forecast" and x["key"] == "goldman_abf_shortfall_2h2026_pct" for x in ev))

    def test_goldman_2028_five_pp_revision_triggers(self):
        previous = {**w.BASELINE, "area_structure": w.ABF_AREA_STRUCTURE_BASELINE}
        updates = [{
            "url": "https://www.skis.com.tw/Report/industry/example.html",
            "parsed": {
                "kind": "research_update",
                "goldman_abf_shortfall_2028_pct": 57.0,
            },
        }]
        ev = w.material_events(previous, updates)
        self.assertTrue(any(x["type"] == "supply_gap_forecast" for x in ev))


class AbfCpuMonetizationAlertTests(unittest.TestCase):
    def test_alert_has_required_sections_and_fact_separation(self):
        state = w.BASELINE
        events = [{
            "type": "official_confirmation",
            "key": "official_nvidia_cpu_substrate_confirmed",
            "url": "https://www.ibiden.com/example",
        }]
        alert = w.build_alert(events, state)
        self.assertIn("CPU·ABF 공급사 수익화 게이트", alert)
        self.assertIn("<b>수익구조</b>", alert)
        self.assertIn("<b>1단계 현재 숫자 추적</b>", alert)
        self.assertIn("<b>2단계 미래 재평가 요인 발굴</b>", alert)
        self.assertIn("<b>관련 기업 지도</b>", alert)
        self.assertIn("<b>공정 병목 후보</b>", alert)
        self.assertIn("<b>숨은 역풍·실패모드</b>", alert)
        self.assertIn("<b>결론</b>", alert)
        self.assertIn("<b>핵심 한 줄 요약</b>", alert)
        self.assertIn("Macquarie 추정 기준선", alert)
        self.assertIn("공식 확인 전 추정", alert)

        self.assertIn("기판 개수보다 면적×층수·SAP 부하", alert)
        self.assertIn("동일 범위 직접비교 금지", alert)
        self.assertIn("Goldman 2028 전망 51%", alert)
        self.assertIn("2H26 14% → 2027 34% → 2028 51%", alert)
        self.assertIn("CY2024 1.0 → CY2026 1.8 → CY2028 2.5", alert)
        self.assertIn("BofA 사용자 제공 동일 차트", alert)
        self.assertIn("2021 -13% → 2028 -16%", alert)
        self.assertIn("4%/10%/16% → 7%/14%/19%", alert)
        self.assertIn("13%/14%/14% → 17%/21%/21%", alert)

    def test_area_structure_upgrade_event_is_explicit(self):
        state = {**w.BASELINE, "area_structure": w.ABF_AREA_STRUCTURE_BASELINE}
        alert = w.build_alert([{
            "type": "area_structure_baseline",
            "key": "area_structure_v3",
            "url": w.ABF_AREA_STRUCTURE_BASELINE["bofa_model"]["current_public_recap"]["source"],
        }], state)
        self.assertIn("ABF 수급 모델 업그레이드", alert)
        self.assertIn("2021 -13% → 2028 -16%", alert)
        self.assertIn("2021 역사 기준", alert)


class NvidiaSamsungPackageSubstrateTests(unittest.TestCase):
    def nvidia_body(self):
        return ("NVIDIA and Supply Chain Partners Expand Capacity to Accelerate AI Infrastructure Buildout. "
                "NVIDIA plans substrate capacity 2.5x for the next three years. "
                "NVIDIA confirms IBIDEN, Samsung Electro-Mechanics and Unimicron. "
                "NVIDIA signed a capacity reservation agreement with Unimicron for KF substrate expansion.")
    def samsung_body(self):
        return ("삼성전기와 엔비디아(NVIDIA)는 2026년부터 다년간 공급을 위한 "
                "전략적 비즈니스 파트너십을 발표했다. 세종 및 부산 전용 생산라인을 구축한다.")
    def test_both_issuer_primary_originals(self):
        a=w.parse_nvidia_abf_official(self.nvidia_body(),w.NVIDIA_ABF_SOURCE)
        b=w.parse_nvidia_abf_official(self.samsung_body(),w.SAMSUNG_ABF_SOURCE)
        self.assertEqual(a["global_capacity_3yr_multiple"],2.5)
        self.assertEqual(a["official_substrate_suppliers"],["IBIDEN","Samsung Electro-Mechanics","Unimicron"])
        self.assertFalse(a["kinsus_in_oct21_supplier_list"])
        self.assertTrue(b["official_multiyear_agreement"])
        self.assertFalse(b["shipments_completed_verified"])
    def test_media_reprint_and_forged_domain_never_official(self):
        self.assertEqual(w.parse_nvidia_abf_official(self.nvidia_body(),w.NVIDIA_ABF_ARTICLE),{})
        self.assertEqual(w.parse_nvidia_abf_official(self.nvidia_body(),"https://fake.example.com/official"),{})
    def test_missing_one_issuer_cannot_send_verified_contract(self):
        snap,checks=w.verify_nvidia_abf_press(reader=lambda u:self.nvidia_body() if u==w.NVIDIA_ABF_SOURCE else "")
        self.assertEqual(snap,{})
        self.assertEqual(checks["samsung"],"body_unverified")
        self.assertEqual(w.nvidia_abf_changes({},snap,[]),[])
    def test_correct_scope_funding_and_contract_exclusion(self):
        snap,checks=w.verify_nvidia_abf_press(
            reader=lambda u:self.nvidia_body() if u==w.NVIDIA_ABF_SOURCE else self.samsung_body())
        self.assertTrue(snap["verified_by_two_issuers"])
        self.assertIsNone(snap["nvidia_specific_contract_amount_krw"])
        self.assertFalse(snap["oct19_contract_attributed_to_nvidia"])
        self.assertEqual(snap["samsung_preexisting_sejong_capex_eok_krw"],42700)
        self.assertEqual(snap["samsung_preexisting_vietnam_capex_eok_krw"],25100)
        self.assertEqual(checks["nvidia"],"verified")
    def test_first_notice_and_republished_silence(self):
        s,_=w.verify_nvidia_abf_press(
            reader=lambda u:self.nvidia_body() if u==w.NVIDIA_ABF_SOURCE else self.samsung_body())
        self.assertEqual(w.nvidia_abf_changes({},s,[]),["official_20261021"])
        self.assertEqual(w.nvidia_abf_changes(s,s,[]),[])
    def test_kinsus_rumor_not_official_contract(self):
        text="NVIDIA is grooming Kinsus as a potential ABF substrate supplier."
        self.assertEqual(w.parse_future_nvidia_abf_milestone(text,w.NVIDIA_ABF_ARTICLE),"")
        self.assertEqual(w.parse_future_nvidia_abf_milestone(text,w.NVIDIA_ABF_SOURCE),"")
    def test_achieved_milestone_vs_future_targets(self):
        u="https://nvidianews.nvidia.com/news/kinsus-2027"
        self.assertEqual(w.parse_future_nvidia_abf_milestone(
            "NVIDIA has signed a supply agreement with Kinsus for ABF substrate products.",u),
            "kinsus_official_contract")
        u2="https://samsungsem.com/kr/newsroom/news/view.do?id=10999"
        self.assertEqual(w.parse_future_nvidia_abf_milestone(
            "Samsung Electro-Mechanics and NVIDIA began shipping ABF substrates.",u2),
            "samsung_actual_shipments")
        self.assertEqual(w.parse_future_nvidia_abf_milestone(
            "Samsung Electro-Mechanics and NVIDIA plan to start shipments of ABF substrates in 2027.",u2),"")
    def test_alert_has_no_samsung_specific_2_5x_or_memory_contract_mislabel(self):
        a=w.build_nvidia_abf_alert(["official_20261021"],{})
        self.assertIn("삼성전기 단독 2.5배가 아님",a)
        self.assertIn("3,605억원",a)
        self.assertIn("별개",a)
        self.assertIn(w.NVIDIA_ABF_SOURCE,a)



if __name__ == "__main__":
    unittest.main()
