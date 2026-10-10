import copy
import pathlib
import re
import sys
import tempfile
import unittest
from datetime import datetime
from unittest.mock import patch
from zoneinfo import ZoneInfo

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "scripts"))
import rubin_hbm_watch as w
import rubin_hbm_pretty as pretty
import rubin_hbm_leverage as leverage
import hbm_delivery as delivery


class NVHBMArchitectureWatchTests(unittest.TestCase):
    def event(self, text, source="NVIDIA Technical Blog"):
        return {
            "category": "nvhbm_architecture",
            "title": text,
            "description": "",
            "article_title": "",
            "article_description": "",
            "article_text": text,
            "source": source,
            "origin_source": source,
            "article_fetch_succeeded": source == "NVIDIA Technical Blog",
            "official_article_text": text if source == "NVIDIA Technical Blog" else "",
            "published_at_kst": "2026-10-03T14:00:00+09:00",
            "direct_link": "https://developer.nvidia.com/blog/nvidia-nvlink-fusion-brings-nvhbm-to-next-generation-ai-infrastructure/",
        }

    def test_official_nvidia_metrics_keep_25_and_30_separate(self):
        text = (
            "NVIDIA NVHBM moves the memory controller into the 3D HBM stack and custom base die. "
            "NVHBM provides up to 30% more memory bandwidth compared with standard HBM4e, "
            "up to 25% more compute die area, and up to 15% lower HBM power usage. "
            "Compared with JEDEC HBM4e, PHY and support area is reduced by up to 67%, "
            "with up to 80% more usable silicon across the layout and up to a 30% increase in available main-die silicon. "
            "These improvements translate into a 30% overall end-to-end performance increase per XPU. "
            "In a 1-gigawatt data center using 2,000W XPUs, the power savings can enable up to 15,000 additional XPUs. "
            "Amazon's Annapurna Labs will be the first to collaborate on NVHBM technology."
        )
        obs = w.extract_nvhbm_architecture(self.event(text))
        self.assertEqual(obs["memory_controller_location"], "hbm_base_die")
        self.assertEqual(obs["bandwidth_gain_pct_max"], 30.0)
        self.assertEqual(obs["compute_die_area_gain_pct_max"], 25.0)
        self.assertEqual(obs["main_die_silicon_gain_pct_max"], 30.0)
        self.assertEqual(obs["layout_usable_silicon_gain_pct_max"], 80.0)
        self.assertEqual(obs["phy_support_area_reduction_pct_max"], 67.0)
        self.assertEqual(obs["hbm_power_reduction_pct_max"], 15.0)
        self.assertEqual(obs["xpu_end_to_end_performance_gain_pct_max"], 30.0)
        self.assertEqual(obs["one_gw_additional_xpu_headroom_max"], 15000)
        self.assertEqual(obs["first_collaborator"], "Amazon Annapurna Labs")

    def test_semianalysis_estimates_remain_research_values(self):
        text = (
            "SemiAnalysis estimates that HBM4 controllers and PHYs take up roughly 16% of Nvidia's Rubin compute die. "
            "On Feynman with NVHBM, we estimate that falls to 4%. "
            "Samsung shows that its standard HBM4 PHY occupies 8mm x 4mm, while the custom D2D interface needs 8.5mm x 1.5mm."
        )
        obs = w.extract_nvhbm_architecture(self.event(text, source="SemiAnalysis"))
        self.assertEqual(obs["rubin_hbm_logic_phy_die_share_estimate_pct"], 16.0)
        self.assertEqual(obs["feynman_nvhbm_interface_die_share_estimate_pct"], 4.0)
        self.assertAlmostEqual(obs["samsung_custom_d2d_area_reduction_pct_estimate"], 60.15625, places=5)

    def test_named_vendor_requires_nvidia_issuer_and_completed_fact(self):
        text = (
            "NVIDIA has officially selected Samsung Electronics as an NVHBM memory partner."
        )
        external = self.event(text, source="NVIDIA Technical Blog")
        external["direct_link"] = "https://www.techpowerup.com/example-nvhbm"
        self.assertNotIn("official_memory_vendors", w.extract_nvhbm_architecture(external) or {})
        missing_fetch = self.event(text)
        missing_fetch["article_fetch_succeeded"] = False
        self.assertNotIn("official_memory_vendors", w.extract_nvhbm_architecture(missing_fetch) or {})
        rumored = self.event("Samsung Electronics is expected to be an NVHBM memory partner.")
        self.assertNotIn("official_memory_vendors", w.extract_nvhbm_architecture(rumored) or {})
        confirmed = w.extract_nvhbm_architecture(self.event(text))
        self.assertEqual(confirmed.get("official_memory_vendors"), ["Samsung Electronics"])

    def test_general_media_cannot_name_official_memory_vendor(self):
        obs = w.extract_nvhbm_architecture(self.event(
            "Samsung is expected to be an NVHBM memory partner for NVIDIA.",
            source="Some Blog",
        ))
        self.assertNotIn("official_memory_vendors", obs or {})

    def test_official_vendor_confirmation_is_material(self):
        old = dict(w.NVHBM_ARCH_BASELINE)
        new = dict(old)
        new["official_memory_vendors"] = ["Samsung Electronics"]
        reasons = w.nvhbm_architecture_changes(old, new)
        self.assertTrue(any("공식 NVHBM 메모리 파트너 실명" in x for x in reasons))

    def test_baseline_same_state_is_silent(self):
        old = dict(w.NVHBM_ARCH_BASELINE)
        self.assertEqual(w.nvhbm_architecture_changes(old, dict(old)), [])


class NVHBMFoundryStrategyTests(unittest.TestCase):
    def good_source(self, sentence, vendor="samsung", fetched=True):
        urls={
            "samsung":"https://news.samsung.com/global/hbm4e-fab-update",
            "skhynix":"https://news.skhynix.co.kr/hbm4e-custom-logic-update/",
            "micron":"https://www.micron.com/about/blog/hbm4e-base-die-update",
            "nvidia":"https://developer.nvidia.com/blog/custom-hbm4e-update",
            "media":w.NVHBM_FOUNDRY_SAMSUNG_REPORT,
            "tsmc":"https://www.tsmc.com/english/node/233",
        }
        return {
            "direct_link":urls[vendor],
            "article_fetch_succeeded":fetched,
            "official_article_title":"",
            "official_article_description":"",
            "official_article_text":sentence,
            "title":"News",
            "description":sentence,
            "source":"Company official" if vendor not in ("media",) else "ZDNet",
            "published_at_kst":"2026-10-10T11:00:00+09:00",
        }

    def test_67pct_scope_and_three_vendors_are_not_confused(self):
        s=w.NVHBM_FOUNDRY_BASELINE
        self.assertEqual(s["phy_support_area_reduction_pct_max_official"],67.0)
        self.assertIsNone(s["entire_package_area_reduction_pct"])
        self.assertEqual(s["bandwidth_gain_pct_max_official"],30.0)
        self.assertEqual(s["hbm_power_reduction_pct_max_official"],15.0)
        self.assertEqual(s["reported_core_nodes"]["samsung"]["hbm4"],"1c")
        self.assertEqual(s["reported_core_nodes"]["skhynix"]["hbm4"],"1b")
        self.assertEqual(s["reported_core_nodes"]["micron"]["next_hbm4e"],"1gamma")
        self.assertFalse(s["micron_100pct_all_hbm_outsourced"])
        self.assertFalse(s["trainium4_nvhbm_mass_production_confirmed"])
        self.assertFalse(s["tsmc_n3p_samsung_or_micron_customer_confirmed"])
        self.assertIsNone(s["confirmed_new_nv_hbm_fab_revenue_krw"])
        self.assertEqual(w.nvhbm_foundry_stage_changes(s,copy.deepcopy(s)),[])

    def test_reported_sources_or_generic_tsmc_N3P_cannot_confirm_vendor_contract(self):
        statement="Samsung has selected TSMC foundry to produce its NVHBM HBM4E base die."
        for source in ("media","nvidia","tsmc"):
            with self.subTest(source=source):
                self.assertIsNone(w.extract_nvhbm_foundry_official_milestone(
                    self.good_source(statement, vendor=source)))
        self.assertIsNone(w.extract_nvhbm_foundry_official_milestone(
            self.good_source(statement,vendor="samsung",fetched=False)))
        fake={
            "vendor":"samsung","stage":"official_mass_production",
            "evidence":"company_official_original_fetched",
            "source_url":"https://www.tsmc.com/english/news/fabrication",
        }
        self.assertEqual(w.merge_nvhbm_foundry_milestone(w.NVHBM_FOUNDRY_BASELINE,fake),
                         w.NVHBM_FOUNDRY_BASELINE)

    def test_future_intention_and_denial_cannot_become_production(self):
        for phrase in (
            "Samsung plans to select TSMC foundry for custom HBM4E base die.",
            "Samsung may have the TSMC foundry manufacture its NVHBM base die.",
            "Samsung has not begun mass production of NVHBM base die at TSMC foundry.",
            "삼성전자 NVHBM 베이스 다이 TSMC 파운드리 양산 목표.",
            "삼성전자 커스텀 HBM4E 베이스 다이를 TSMC 파운드리에서 양산할 예정이다.",
        ):
            with self.subTest(phrase=phrase):
                self.assertIsNone(w.extract_nvhbm_foundry_official_milestone(
                    self.good_source(phrase)))

    def test_official_samsung_foundry_selection_and_upgrade_once(self):
        obs=w.extract_nvhbm_foundry_official_milestone(self.good_source(
            "Samsung has selected TSMC foundry for its custom HBM4E base die."
        ))
        self.assertIsNotNone(obs)
        self.assertEqual(obs["stage"],"official_foundry_selection")
        self.assertEqual(obs["foundry"],"TSMC")
        baseline=copy.deepcopy(w.NVHBM_FOUNDRY_BASELINE)
        newer=w.merge_nvhbm_foundry_milestone(baseline,obs)
        self.assertEqual(newer["vendor_stage"]["samsung"],"official_foundry_selection")
        self.assertEqual(newer["vendor_stage"]["micron"],"reported_strategy")
        self.assertEqual(len(w.nvhbm_foundry_stage_changes(baseline,newer)),1)
        self.assertEqual(w.nvhbm_foundry_stage_changes(newer,w.merge_nvhbm_foundry_milestone(newer,obs)),[])
        lower=dict(obs,stage="reported_strategy")
        self.assertEqual(w.merge_nvhbm_foundry_milestone(newer,lower),newer)

    def test_no_automatic_micron_outsource_all_or_trainium4_sales(self):
        initial=copy.deepcopy(w.NVHBM_FOUNDRY_BASELINE)
        self.assertFalse(initial["micron_100pct_all_hbm_outsourced"])
        self.assertFalse(initial["trainium4_nvhbm_mass_production_confirmed"])
        self.assertFalse(initial["reported_base_die_manufacturing"]["micron"]["nvhbm_tsmc_contract_official"])

    def _pipeline(self,events):
        now=datetime(2026,10,10,14,30,tzinfo=ZoneInfo("Asia/Seoul"))
        raw=w.build_alert(now,events,{"rate":1350.0,"date":"2026-10-10","error":""})
        with tempfile.TemporaryDirectory() as temp:
            p=pathlib.Path(temp)/"rubin_hbm_alert.md"
            p.write_text(raw,encoding="utf-8")
            with patch.object(pretty,"ALERT",p),patch.object(leverage,"ALERT",p):
                pretty.main()
                leverage.main()
                formatted=p.read_text(encoding="utf-8")
        return raw,formatted,delivery.chunks(formatted)

    def test_foundry_notice_links_scope_and_telegram_gate(self):
        e=w.nvhbm_foundry_strategy_event(w.NVHBM_FOUNDRY_BASELINE,["새 공급망 보도"],initial=True)
        raw,final,parts=self._pipeline([e])
        self.assertIn("NVHBM 베이스 다이",final)
        self.assertIn("PHY·지원 면적 최대 -67%",final)
        self.assertIn("전체 반도체 패키지 면적 -67%가 아닙니다",final)
        self.assertIn("대역폭 최대 +30%",final)
        self.assertIn("HBM 전력 소비 최대 -15%",final)
        self.assertIn("TSMC 이원화 추진",final)
        self.assertIn("우선 검토 보도",final)
        self.assertIn("100% 외주 전환했다는 뜻은 아닙니다",final)
        self.assertIn("실제 수율 아님",final)
        self.assertNotIn("[이번 변화]",final)
        self.assertNotIn("[HBM 수요·가격 레버리지]",final)
        self.assertNotIn("288GB HBM4",final)
        self.assertNotIn("<b>2026</b>",final)
        self.assertNotIn("확정 매출",final)
        self.assertIsNone(delivery.validate_rubin_nvhbm_foundry_notification(final))
        self.assertGreaterEqual(len(parts),1)
        links=re.findall(r'<a href="([^"]+)">원문 보기</a>',final)
        self.assertEqual(len(links),9)
        self.assertIn(w.NVHBM_FOUNDRY_NEWS_SOURCE,links)
        self.assertIn(w.NVHBM_FOUNDRY_TSMC_SOURCE,links)

    def test_alert_hard_gate_blocks_metric_scope_or_links_corruption(self):
        e=w.nvhbm_foundry_strategy_event(w.NVHBM_FOUNDRY_BASELINE,["보도"],initial=True)
        _,final,_=self._pipeline([e])
        corruptions={
            "package_area":final.replace("PHY·지원 면적 최대 -67%","전체 패키지 면적 최대 -67%"),
            "rubin_leverage":final+"\n[HBM 수요·가격 레버리지]\n",
            "source_host":final.replace(w.NVHBM_FOUNDRY_NVIDIA_SOURCE,"https://example.com/fake-nvidia"),
            "broken_year":final.replace("2026-10-10","<b>2026</b>-10-10"),
            "missing_sources":re.sub(r'<a href="[^"]+">원문 보기</a>',"원문 미확인",final),
            "raw_encoded_url":final+"\n• 긴 주소 "+w.NVHBM_FOUNDRY_SAMSUNG_REPORT,
        }
        for kind,corrupt in corruptions.items():
            with self.subTest(kind=kind):
                with self.assertRaises(ValueError):
                    delivery.validate_rubin_nvhbm_foundry_notification(corrupt)

    def test_mixed_rubin_and_foundry_do_not_merge(self):
        e=w.nvhbm_foundry_strategy_event(w.NVHBM_FOUNDRY_BASELINE,["신규"],initial=True)
        rubin={
            "category":"rubin_spec", "headline_ko":"Rubin 사양 확인",
            "origin_source":"NVIDIA", "source":"NVIDIA",
            "verification":"공식", "published_at_kst":"2026-10-10T13:00:00+09:00",
            "fact_bullets":["고객 사양 확인"], "verdict":"검증 필요",
            "direct_link":"https://developer.nvidia.com/blog/example",
        }
        _,final,parts=self._pipeline([rubin,e])
        self.assertIn(delivery.MESSAGE_BREAK,final)
        self.assertIn("NVHBM 베이스 다이",final)
        self.assertGreaterEqual(len(parts),2)
        supply="".join(p for p in parts if "NVHBM 베이스 다이" in p)
        self.assertNotIn("[HBM 수요·가격 레버리지]",supply)
        self.assertIsNone(delivery.validate_rubin_nvhbm_foundry_notification(final))


    def test_standard_hbm4e_mass_production_does_not_prove_nvhbm(self):
        standard=self.good_source(
            "Samsung started mass production of standard HBM4E base die at Samsung Foundry."
        )
        obs=w.extract_nvhbm_foundry_official_milestone(standard)
        self.assertIsNotNone(obs)
        self.assertEqual(obs["stage"],"official_mass_production")
        self.assertEqual(obs["product_scope"],"standard_hbm4e")
        original=copy.deepcopy(w.NVHBM_FOUNDRY_BASELINE)
        updated=w.merge_nvhbm_foundry_milestone(original,obs)
        self.assertEqual(updated.get("memory_vendor_nvhbm_mass_production_confirmed"),[])
        self.assertEqual(
            updated["vendor_product_stage"]["samsung"]["standard_hbm4e"],
            "official_mass_production"
        )
        self.assertEqual(len(w.nvhbm_foundry_stage_changes(original,updated)),1)

    def test_later_nvhbm_same_stage_is_new_fact_not_swallowed_by_standard_hbm4e(self):
        standard=self.good_source(
            "Samsung started mass production of standard HBM4E base die at Samsung Foundry."
        )
        specialized=self.good_source(
            "Samsung started mass production of NVHBM base die at Samsung Foundry."
        )
        specialized["direct_link"]="https://news.samsung.com/global/specific-nvhbm"
        original=copy.deepcopy(w.NVHBM_FOUNDRY_BASELINE)
        first=w.merge_nvhbm_foundry_milestone(
            original,w.extract_nvhbm_foundry_official_milestone(standard)
        )
        obs=w.extract_nvhbm_foundry_official_milestone(specialized)
        self.assertEqual(obs["product_scope"],"nvhbm")
        newer=w.merge_nvhbm_foundry_milestone(first,obs)
        self.assertEqual(newer["vendor_stage"]["samsung"],"official_mass_production")
        self.assertEqual(newer["memory_vendor_nvhbm_mass_production_confirmed"],["samsung"])
        change=w.nvhbm_foundry_stage_changes(first,newer)
        self.assertEqual(len(change),1)
        self.assertEqual(change[0][0:2],("samsung","nvhbm"))
        event=w.nvhbm_foundry_strategy_event(newer,[change[0][2]],vendor="samsung",scope="nvhbm")
        self.assertEqual(event["direct_link"], specialized["direct_link"])
        self.assertIn("_samsung_nvhbm_",event["fact_key"])
        self.assertEqual(
            w.nvhbm_foundry_stage_changes(newer,w.merge_nvhbm_foundry_milestone(newer,obs)),
            []
        )
        self.assertEqual(first.get("memory_vendor_nvhbm_mass_production_confirmed"),[])

    def test_standard_custom_nvhbm_source_links_stay_distinct(self):
        original=copy.deepcopy(w.NVHBM_FOUNDRY_BASELINE)
        sentences=(
            ("standard_hbm4e","Samsung selected TSMC foundry for standard HBM4E base die."),
            ("custom_hbm","Samsung selected TSMC foundry for custom HBM4E base die."),
            ("nvhbm","Samsung selected TSMC foundry for NVHBM base die."),
        )
        new=original
        evidence={}
        for scope,sentence in sentences:
            item=self.good_source(sentence)
            item["direct_link"]=f"https://news.samsung.com/global/{scope}"
            parsed=w.extract_nvhbm_foundry_official_milestone(item)
            self.assertEqual(parsed["product_scope"],scope)
            new=w.merge_nvhbm_foundry_milestone(new,parsed)
            evidence[scope]=item["direct_link"]
        changed=w.nvhbm_foundry_stage_changes(original,new)
        self.assertEqual(len(changed),3)
        events=[
            w.nvhbm_foundry_strategy_event(new,[reason],vendor=vendor,scope=scope)
            for vendor,scope,reason in changed
        ]
        self.assertEqual(len({x["fact_key"] for x in events}),3)
        self.assertEqual({x["direct_link"] for x in events},set(evidence.values()))

    def test_verified_micron_reprint_link_passes_pretty_and_delivery_guards(self):
        self.assertEqual(
            w.NVHBM_FOUNDRY_MICRON_REPORT,
            "https://www.thelec.net/news/articleView.html?idxno=14372"
        )
        item=w.nvhbm_foundry_strategy_event(
            w.NVHBM_FOUNDRY_BASELINE,["출처 링크 검산"],initial=True
        )
        _,final,_=self._pipeline([item])
        self.assertIn(w.NVHBM_FOUNDRY_MICRON_REPORT,final)
        self.assertIn('Micron 임원 인용 보도: <a href=',final)
        self.assertIsNone(delivery.validate_rubin_nvhbm_foundry_notification(final))

    def test_alert_labels_standard_and_nvhbm_progress_separately(self):
        baseline=copy.deepcopy(w.NVHBM_FOUNDRY_BASELINE)
        baseline["vendor_product_stage"]={
            "samsung":{
                "standard_hbm4e":"official_mass_production",
                "nvhbm":"official_customer_sample",
            }
        }
        baseline["vendor_stage"]["samsung"]="official_mass_production"
        baseline["memory_vendor_nvhbm_mass_production_confirmed"]=[]
        event=w.nvhbm_foundry_strategy_event(baseline,["테스트 단계"],initial=True)
        _,formatted,parts=self._pipeline([event])
        self.assertIn("표준 HBM4E: 해당 베이스 다이 양산 공식 확인",formatted)
        self.assertIn("NVHBM: 해당 베이스 다이 고객 샘플 공식 확인",formatted)
        self.assertIn("삼성전자 NVHBM 양산: 미확정",formatted)
        self.assertNotIn("NVHBM: 해당 베이스 다이 양산 공식 확인",formatted)
        self.assertIsNone(delivery.validate_rubin_nvhbm_foundry_notification(formatted))

    def test_samsung_issuer_name_does_not_identify_samsung_foundry_counterparty(self):
        item=self.good_source(
            "Samsung selected an external foundry for NVHBM base die."
        )
        obs=w.extract_nvhbm_foundry_official_milestone(item)
        self.assertIsNotNone(obs)
        self.assertEqual(obs["stage"],"official_foundry_selection")
        self.assertEqual(obs["product_scope"],"nvhbm")
        self.assertEqual(obs["foundry"],"")
        updated=w.merge_nvhbm_foundry_milestone(
            w.NVHBM_FOUNDRY_BASELINE,obs
        )
        self.assertEqual(
            updated["confirmed_official_milestones"]["samsung"]["foundry"],
            "실명 미확인"
        )
        named=self.good_source(
            "Samsung selected Samsung Foundry for NVHBM base die."
        )
        selected=w.extract_nvhbm_foundry_official_milestone(named)
        self.assertEqual(selected["foundry"],"Samsung Foundry")

    def test_one_time_baseline_and_followup_silence(self):
        memory={"data":{
            "seen_ids":[],"seen_fact_keys":[],
            "structure_baseline_version":w.STRUCTURE_BASELINE_VERSION,
            "hbm_hybrid_bond_track_version":w.HBM_HYBRID_BOND_TRACK_VERSION,
            "hbm_hybrid_bonding":copy.deepcopy(w.HBM_HYBRID_BOND_BASELINE),
            "nvhbm_architecture_track_version":w.NVHBM_ARCH_TRACK_VERSION,
            "nvhbm_architecture":copy.deepcopy(w.NVHBM_ARCH_BASELINE),
        }}
        def load():
            return copy.deepcopy(memory["data"]),False
        def write(path,value):
            if "rubin_hbm_pending_state.json" in str(path):
                memory["data"].update(copy.deepcopy(value))
        with tempfile.TemporaryDirectory() as temp:
            with (
                patch.object(w,"OUT",pathlib.Path(temp)),
                patch.object(w,"load_state",side_effect=load),
                patch.object(w,"read_feed",return_value=([],[])),
                patch.object(w,"fetch_fx",return_value={"rate":1350.0,"date":"2026-10-10","error":""}),
                patch.object(w,"write_json",side_effect=write),
            ):
                w.main()
                self.assertEqual(memory["data"]["nvhbm_foundry_track_version"],1)
                self.assertEqual(memory["data"]["last_send_event_count"],1)
                self.assertEqual(memory["data"]["nvhbm_foundry_strategy"]["vendor_stage"]["samsung"],"reported_strategy")
                w.main()
                self.assertEqual(memory["data"]["last_send_event_count"],0)


if __name__ == "__main__":
    unittest.main()
