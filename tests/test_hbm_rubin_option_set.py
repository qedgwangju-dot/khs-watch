import pathlib
import sys
import unittest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "scripts"))
import rubin_hbm_watch as w


class RubinUltraHBMOptionSetTests(unittest.TestCase):
    def event(self, text, source="매일경제"):
        return {
            "category": "rubin_hbm_option_set",
            "title": text,
            "description": "",
            "article_title": "",
            "article_description": "",
            "article_text": text,
            "source": source,
            "origin_source": source,
            "published_at_kst": "2026-10-02T17:32:45+09:00",
            "direct_link": "https://www.mk.co.kr/news/business/12167424",
        }

    def test_current_reported_option_set_is_not_final(self):
        obs = w.extract_rubin_ultra_hbm_options(self.event(
            "엔비디아는 루빈 울트라에 적용할 HBM을 놓고 12단 HBM4E뿐 아니라 "
            "8단 HBM4E와 12단 HBM4, 8단 HBM4까지 선택지를 넓혀 평가 중이다."
        ))
        self.assertIsNotNone(obs)
        self.assertEqual(obs["stage"], "reported_evaluation")
        self.assertEqual(
            obs["candidate_options"],
            sorted(["HBM4E_12hi", "HBM4E_8hi", "HBM4_12hi", "HBM4_8hi"]),
        )

        merged = w.merge_rubin_ultra_hbm_options(dict(w.RUBIN_ULTRA_HBM_OPTIONS_BASELINE), obs)
        self.assertEqual(w.rubin_ultra_hbm_options_changes(w.RUBIN_ULTRA_HBM_OPTIONS_BASELINE, merged), [])

    def test_damnang_12hi_reversal_is_preference_not_final_candidate_collapse(self):
        obs = w.extract_rubin_ultra_hbm_options(self.event(
            "HBM4 will have to go back to 12Hi instead of 8Hi",
            source="Damnang Research",
        ))
        self.assertIsNotNone(obs)
        self.assertEqual(obs["reported_preferred_option"], "HBM4_12hi")
        self.assertEqual(obs["previous_reported_preferred_option"], "HBM4_8hi")
        self.assertEqual(obs["reported_preference_direction"], "8hi_to_12hi_reversal")
        self.assertEqual(obs["reported_preference_stage"], "single_industry_source")
        self.assertEqual(obs["reported_preference_support_sources"], ["Damnang"])
        self.assertNotIn("candidate_options", obs)
        self.assertNotEqual(obs.get("stage"), "official_final")

    def test_same_damnang_reversal_matches_v2_baseline_and_is_silent(self):
        old = dict(w.RUBIN_ULTRA_HBM_OPTIONS_BASELINE)
        obs = w.extract_rubin_ultra_hbm_options(self.event(
            "HBM4 will have to go back to 12Hi instead of 8Hi",
            source="Damnang Research",
        ))
        new = w.merge_rubin_ultra_hbm_options(old, obs)
        self.assertEqual(new["candidate_options"], old["candidate_options"])
        self.assertEqual(new["reported_preferred_option"], "HBM4_12hi")
        self.assertEqual(w.rubin_ultra_hbm_options_changes(old, new), [])

    def test_independent_trendforce_12hi_signal_upgrades_to_cross_verified(self):
        old = dict(w.RUBIN_ULTRA_HBM_OPTIONS_BASELINE)
        event = self.event(
            "Rubin Ultra HBM4 will revert to 12Hi instead of 8Hi, according to TrendForce checks.",
            source="TrendForce",
        )
        obs = w.extract_rubin_ultra_hbm_options(event)
        new = w.merge_rubin_ultra_hbm_options(old, obs)
        self.assertEqual(new["reported_preferred_option"], "HBM4_12hi")
        self.assertEqual(new["reported_preference_stage"], "cross_verified")
        self.assertEqual(set(new["reported_preference_support_sources"]), {"Damnang", "TrendForce"})
        reasons = w.rubin_ultra_hbm_options_changes(old, new)
        self.assertTrue(any("cross_verified" in x for x in reasons))

    def test_future_flip_back_to_8hi_resets_support_and_alerts(self):
        old = dict(w.RUBIN_ULTRA_HBM_OPTIONS_BASELINE)
        obs = w.extract_rubin_ultra_hbm_options(self.event(
            "Rubin Ultra HBM4 will switch back to 8Hi instead of 12Hi.",
            source="TrendForce",
        ))
        new = w.merge_rubin_ultra_hbm_options(old, obs)
        self.assertEqual(new["reported_preferred_option"], "HBM4_8hi")
        self.assertEqual(new["reported_preference_support_sources"], ["TrendForce"])
        self.assertEqual(new["reported_preference_stage"], "single_industry_source")
        reasons = w.rubin_ultra_hbm_options_changes(old, new)
        self.assertTrue(any("HBM4_12hi→HBM4_8hi" in x for x in reasons))

    def test_official_final_selection_is_distinct(self):
        obs = w.extract_rubin_ultra_hbm_options(self.event(
            "NVIDIA Rubin Ultra HBM final specification officially selected 8-Hi HBM4E.",
            source="NVIDIA",
        ))
        self.assertEqual(obs["stage"], "official_final")
        self.assertEqual(obs["candidate_options"], ["HBM4E_8hi"])

        old = dict(w.RUBIN_ULTRA_HBM_OPTIONS_BASELINE)
        new = w.merge_rubin_ultra_hbm_options(old, obs)
        reasons = w.rubin_ultra_hbm_options_changes(old, new)
        self.assertTrue(any("Rubin Ultra HBM 옵션 단계" in x and "official_final" in x for x in reasons))
        self.assertTrue(any("HBM 후보 조합" in x for x in reasons))

    def test_baseline_same_state_is_silent(self):
        old = dict(w.RUBIN_ULTRA_HBM_OPTIONS_BASELINE)
        self.assertEqual(w.rubin_ultra_hbm_options_changes(old, dict(old)), [])


    def test_rubin_news_refers_to_standard_rubin_not_ultra(self):
        fact = w.RUBIN_SUPPLY_MEDIA_NEWS["standard_rubin_12hi_dominant"]
        self.assertEqual(fact["product_scope"], "Rubin_HBM4_not_Rubin_Ultra")
        self.assertTrue(fact["reported_12hi_majority"])
        self.assertTrue(fact["reported_8hi_supplementary_request"])
        self.assertFalse(fact["nvidia_official_final_spec"])
        notice = w.rubin_supply_media_report_event("standard_rubin_12hi_dominant", fact)
        self.assertIn("일반 Rubin",notice["headline_ko"])
        self.assertTrue(any("Rubin Ultra" in p for p in notice["fact_bullets"]))
        self.assertNotIn("NVIDIA 공식 최종 구성 확정",notice["verdict"])

    def test_samsung_report_not_issuer_confirmed_contract(self):
        fact=w.RUBIN_SUPPLY_MEDIA_NEWS["samsung_nvhbm_tsmc_3nm_selection"]
        self.assertTrue(fact["reported_tsmc_3nm_manufacturing_selection"])
        self.assertFalse(fact["issuer_official_foundry_contract_confirmed"])
        self.assertFalse(fact["nvhbm_mass_production_confirmed"])
        self.assertTrue(fact["samsung_standard_hbm4_4nm_inhouse_unchanged"])
        notice=w.rubin_supply_media_report_event("samsung_nvhbm_tsmc_3nm_selection",fact)
        self.assertIn("보도",notice["headline_ko"])
        self.assertIn("en.sedaily.com",notice["direct_link"])
        self.assertTrue(any("1곳" in p for p in notice["fact_bullets"]))

    def test_editorial_report_is_not_manufacturer_official_foundry_upgrade(self):
        f=w.RUBIN_SUPPLY_MEDIA_NEWS["samsung_nvhbm_tsmc_3nm_selection"]
        fake={"vendor":"samsung","stage":"official_foundry_selection",
              "evidence":"reported_source_only",
              "source_url":f["source_url"],"product_scope":"nvhbm"}
        original=__import__("copy").deepcopy(w.NVHBM_FOUNDRY_BASELINE)
        got=w.merge_nvhbm_foundry_milestone(original,fake)
        self.assertEqual(got,original)

    def test_both_report_event_keys_are_distinct_and_stable(self):
        news=w.RUBIN_SUPPLY_MEDIA_NEWS
        n1=w.rubin_supply_media_report_event("standard_rubin_12hi_dominant",news["standard_rubin_12hi_dominant"])
        n2=w.rubin_supply_media_report_event("samsung_nvhbm_tsmc_3nm_selection",news["samsung_nvhbm_tsmc_3nm_selection"])
        self.assertNotEqual(n1["fact_key"],n2["fact_key"])
        self.assertEqual(n1["fact_key"],w.rubin_supply_media_report_event("standard_rubin_12hi_dominant",news["standard_rubin_12hi_dominant"])["fact_key"])
        with self.assertRaises(ValueError):
            w.rubin_supply_media_report_event("unknown",{})

    def test_initial_news_alert_preserves_independent_origin_and_links(self):
        e=[w.rubin_supply_media_report_event(k,v) for k,v in w.RUBIN_SUPPLY_MEDIA_NEWS.items()]
        rendered=w.build_alert(__import__("datetime").datetime(2026,10,18,20,30,0),e,{"rate":None})
        self.assertIn("DIGITIMES",rendered)
        self.assertIn("서울경제",rendered)
        self.assertIn("3나노",rendered)
        self.assertIn("8단",rendered)
        self.assertIn("12단",rendered)
        self.assertIn("미확정",rendered)
        self.assertIn(w.RUBIN_SUPPLY_MEDIA_NEWS["standard_rubin_12hi_dominant"]["source_url"],rendered)
        self.assertIn(w.RUBIN_SUPPLY_MEDIA_NEWS["samsung_nvhbm_tsmc_3nm_selection"]["source_url"],rendered)



if __name__ == "__main__":
    unittest.main()
