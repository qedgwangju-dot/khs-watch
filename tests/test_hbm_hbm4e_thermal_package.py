import pathlib
import sys
import unittest

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


if __name__ == "__main__":
    unittest.main()
