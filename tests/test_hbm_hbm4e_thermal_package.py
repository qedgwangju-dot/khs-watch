import copy
import pathlib
import sys
import tempfile
import unittest
from unittest.mock import patch
from datetime import datetime
from zoneinfo import ZoneInfo

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "scripts"))
import rubin_hbm_watch as w


class SamsungHBM4EThermalPackageWatchTests(unittest.TestCase):
    def event(self, text):
        return {
            "category": "hbm4e_thermal_package",
            "title": text,
            "description": "",
            "article_title": "",
            "article_description": "",
            "article_text": text,
            "source": "조선비즈",
            "origin_source": "조선비즈",
            "published_at_kst": "2026-10-02T15:21:00+09:00",
            "direct_link": "https://biz.chosun.com/it-science/ict/2026/10/02/MHAFNCALYJDI5P3MKV3F3MXINE/?outputType=amp",
        }

    def test_current_article_stays_at_seeded_baseline(self):
        text = (
            "삼성전자 HBM4E 발열 대응. 현재 AI 반도체용 인터포저 크기는 EUV 최대 면적의 5.5배 수준이다. "
            "인터포저가 9배, 12배를 거쳐 40배까지 확대될 것으로 보인다. "
            "삼성전자는 HCB를 GTC 2026에서 소개했다. "
            "패키지와 서버 시스템 단위의 냉각 기술 도입 가능성도 검토하고 있다."
        )
        obs = w.extract_samsung_hbm4e_thermal_package(self.event(text))
        self.assertIsNotNone(obs)
        self.assertEqual(obs["industry_current_interposer_reticle_x"], 5.5)
        self.assertEqual(obs["reported_future_interposer_reticle_x"], 40.0)
        self.assertEqual(obs["reported_future_interposer_stage"], "industry_projection")
        self.assertEqual(obs["hcb_stage"], "technology_showcase")
        self.assertEqual(obs["package_system_cooling_stage"], "reported_review")

        merged = w.merge_samsung_hbm4e_thermal_package(dict(w.SAMSUNG_HBM4E_THERMAL_BASELINE), obs)
        self.assertEqual(w.samsung_hbm4e_thermal_changes(w.SAMSUNG_HBM4E_THERMAL_BASELINE, merged), [])

    def test_interposer_current_size_change_alerts(self):
        old = dict(w.SAMSUNG_HBM4E_THERMAL_BASELINE)
        new = dict(old, industry_current_interposer_reticle_x=9.0)
        reasons = w.samsung_hbm4e_thermal_changes(old, new)
        self.assertTrue(any("현재 인터포저 면적" in x and "5.5" in x and "9" in x for x in reasons))

    def test_hcb_mass_production_is_stage_upgrade(self):
        obs = w.extract_samsung_hbm4e_thermal_package(self.event(
            "삼성전자 HBM4E 양산에 HCB 하이브리드 본딩을 적용한다. 발열과 열저항을 낮춘다."
        ))
        self.assertEqual(obs["hcb_stage"], "hbm4e_mass_production")
        old = dict(w.SAMSUNG_HBM4E_THERMAL_BASELINE)
        new = w.merge_samsung_hbm4e_thermal_package(old, obs)
        reasons = w.samsung_hbm4e_thermal_changes(old, new)
        self.assertTrue(any("HCB 단계" in x and "hbm4e_mass_production" in x for x in reasons))

    def test_hpb_validation_and_hbm5_target_are_not_hbm4e_mass_production(self):
        obs = w.extract_samsung_hbm4e_thermal_package(self.event(
            "삼성전자 HBM4E 기반으로 HPB Heat Path Block 기술을 검증 중이며 HBM5부터 적용할 계획이다."
        ))
        self.assertEqual(obs["hpb_stage"], "hbm4e_validation")
        self.assertEqual(obs["hpb_target_generation"], "hbm5")
        self.assertNotEqual(obs["hpb_stage"], "hbm4e_mass_production")

    def test_system_cooling_adoption_alerts(self):
        obs = w.extract_samsung_hbm4e_thermal_package(self.event(
            "삼성전자 HBM4E 패키지와 서버 시스템 단위 냉각 기술을 실제 양산 시스템에 도입한다."
        ))
        self.assertEqual(obs["package_system_cooling_stage"], "adopted")
        old = dict(w.SAMSUNG_HBM4E_THERMAL_BASELINE)
        new = w.merge_samsung_hbm4e_thermal_package(old, obs)
        reasons = w.samsung_hbm4e_thermal_changes(old, new)
        self.assertTrue(any("패키지·시스템 냉각 단계" in x and "adopted" in x for x in reasons))


class HybridHBMSourceGuardTests(unittest.TestCase):
    def event(self, body, *, domain="https://news.skhynix.com/en/example", published="2026-10-08T13:00:00+09:00"):
        return {
            "title": "HBM hybrid bonding update",
            "article_title": "HBM hybrid bonding update",
            "article_description": "",
            "article_text": body,
            "source": "Manufacturer",
            "direct_link": domain,
            "published_at_kst": published,
        }

    def test_single_anonymous_interview_and_republication_are_not_official(self):
        base = w.HBM_HYBRID_BOND_BASELINE
        self.assertEqual(base["reported_origin"], "Damnang")
        self.assertEqual(base["reported_origin_count"], 1)
        self.assertTrue(base["reported_sk_hybrid_customer_sample_not_started"])
        self.assertTrue(base["reported_samsung_hybrid_customer_sample_sent"])
        self.assertFalse(base["sk_official_hybrid_customer_sample_verified"])
        self.assertFalse(base["samsung_official_hybrid_customer_sample_verified"])
        self.assertTrue(base["sk_hbm4e_mr_muf_sample_shipped"])
        self.assertEqual(base["sk_revenue_share_q2_2026_pct"], 50.0)
        self.assertEqual(base["samsung_revenue_share_q2_2026_pct"], 33.0)
        story = self.event(
            "Samsung HBM hybrid bonding samples shipped to customers",
            domain=w.HBM_HYBRID_BOND_REPUBLISHER,
        )
        self.assertIsNone(w.extract_hbm_hybrid_official_observation(story))

    def test_existing_mr_muf_hbm4e_samples_are_not_hybrid_samples(self):
        text = (
            "SK hynix shipped HBM4E samples to customers using Advanced MR-MUF. "
            "Hybrid bonding technology is being developed for next-generation HBM."
        )
        self.assertIsNone(w.extract_hbm_hybrid_official_observation(self.event(text)))
        same_sentence = (
            "SK hynix HBM4E MR-MUF samples shipped to customers, while hybrid bonding "
            "technology is still under development."
        )
        self.assertIsNone(w.extract_hbm_hybrid_official_observation(self.event(same_sentence)))

    def test_customer_sample_mentioned_in_company_page_is_not_automatic_hybrid_proof(self):
        text = (
            "Samsung Electronics has shipped HBM4E samples to customers. "
            "Hybrid bonding was displayed for future HBM applications."
        )
        self.assertIsNone(w.extract_hbm_hybrid_official_observation(
            self.event(text, domain="https://news.samsung.com/global/example")
        ))

    def test_official_direct_hybrid_hbm_customer_sample_is_material(self):
        official = self.event(
            "SK hynix shipped hybrid bonding HBM samples to major customers.",
        )
        obs = w.extract_hbm_hybrid_official_observation(official)
        self.assertIsNotNone(obs)
        self.assertEqual(obs["vendor"], "skhynix")
        self.assertEqual(obs["stage"], "customer_hbm_sample_shipped")
        old = dict(w.HBM_HYBRID_BOND_BASELINE)
        merged = w.merge_hbm_hybrid_official_observation(old, obs)
        self.assertTrue(merged["skhynix_official_hybrid_customer_sample_verified"])
        self.assertFalse(merged["samsung_official_hybrid_customer_sample_verified"])
        self.assertEqual(len(w.hbm_hybrid_official_changes(old, merged)), 1)
        self.assertEqual(w.hbm_hybrid_official_changes(merged, w.merge_hbm_hybrid_official_observation(merged, obs)), [])

    def test_samsung_customer_sample_not_customer_qualification(self):
        obs = w.extract_hbm_hybrid_official_observation(self.event(
            "Samsung shipped hybrid bonding HBM samples to customers.",
            domain="https://news.samsung.com/global/example",
        ))
        self.assertIsNotNone(obs)
        self.assertEqual(obs["stage"], "customer_hbm_sample_shipped")
        out = w.merge_hbm_hybrid_official_observation(w.HBM_HYBRID_BOND_BASELINE, obs)
        self.assertTrue(out["samsung_official_hybrid_customer_sample_verified"])
        self.assertNotEqual(out["samsung_official_hybrid_stage"], "customer_qualification_passed")

    def test_planned_or_denied_milestone_cannot_upgrade(self):
        for text in (
            "SK hynix will ship hybrid bonding HBM samples to customers.",
            "SK hynix has not yet shipped hybrid bonding HBM samples to customers.",
            "No hybrid bonding HBM samples have been shipped to customers.",
            "SK hynix HBM 하이브리드 본딩 고객 샘플 출하 예정.",
            "SK hynix HBM 하이브리드 본딩 샘플은 아직 고객사에 전달되지 않았습니다.",
        ):
            with self.subTest(text=text):
                self.assertIsNone(w.extract_hbm_hybrid_official_observation(self.event(text)))

    def test_lower_evidence_or_lower_stage_never_overwrites_official(self):
        old = dict(w.HBM_HYBRID_BOND_BASELINE, skhynix_official_hybrid_stage="customer_hbm_sample_shipped")
        self.assertEqual(w.merge_hbm_hybrid_official_observation(old, {
            "vendor":"skhynix","stage":"hbm_mass_production_started",
            "evidence":"reported","source_url":"https://example.com/rumor"
        }), old)
        self.assertEqual(w.merge_hbm_hybrid_official_observation(old, {
            "vendor":"skhynix","stage":"internal_hbm_prototype",
            "evidence":"official","source_url":"https://news.skhynix.com/en/example"
        }), old)

    def test_report_notice_is_labelled_reported_and_telegram_safe(self):
        event = w.hbm_hybrid_bond_event(w.HBM_HYBRID_BOND_BASELINE, ["보도 최초"], initial=True)
        now = datetime(2026, 10, 8, 16, 4, tzinfo=ZoneInfo("Asia/Seoul"))
        text = w.build_alert(now, [event], {"rate":1400.0,"date":"2026-10-08"})
        self.assertIn("단일 익명 전문가", text)
        self.assertIn("회사 공식", text)
        self.assertIn("MR-MUF", text)
        self.assertIn("샘플 제작 지연 주장", text)
        self.assertIn("0.99^16≈85.1%", text)
        self.assertIn(w.HBM_HYBRID_BOND_PRIMARY, text)
        self.assertIn(w.HBM_HYBRID_BOND_REPUBLISHER, text)
        self.assertNotIn("양산 공급 확정", text)
        import hbm_delivery as delivery
        self.assertTrue(delivery.chunks(text))

    def test_initial_migration_once_then_no_repeat_on_same_information(self):
        memory = {"saved": {"seen_ids":[],"seen_fact_keys":[], "structure_baseline_version":w.STRUCTURE_BASELINE_VERSION}}
        def load():
            return copy.deepcopy(memory["saved"]), False
        def fake_json(path, value):
            if "rubin_hbm_pending_state.json" in str(path):
                memory["saved"].update(copy.deepcopy(value))
        with tempfile.TemporaryDirectory() as temp:
            out = pathlib.Path(temp)
            with (
                patch.object(w, "OUT", out),
                patch.object(w, "load_state", side_effect=load),
                patch.object(w, "read_feed", return_value=([],[])),
                patch.object(w, "fetch_fx", return_value={"rate":1400.0,"date":"2026-10-08","error":""}),
                patch.object(w, "write_json", side_effect=fake_json),
            ):
                w.main()
                first = (out / "rubin_hbm_alert.md").read_text(encoding="utf-8")
                self.assertIn("단일 익명 전문가", first)
                self.assertEqual(memory["saved"]["hbm_hybrid_bond_track_version"], w.HBM_HYBRID_BOND_TRACK_VERSION)
                self.assertEqual(memory["saved"]["last_send_event_count"], 1)
                w.main()
                self.assertEqual(memory["saved"]["last_send_event_count"], 0)
                self.assertEqual(memory["saved"]["hbm_hybrid_bond_track_version"], w.HBM_HYBRID_BOND_TRACK_VERSION)



if __name__ == "__main__":
    unittest.main()
