import pathlib
import sys
import unittest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "scripts"))
import rubin_hbm_watch as w


class SamsungNextGenHBMWatchTests(unittest.TestCase):
    def event(self, text, source="매일경제"):
        return {
            "category": "samsung_nextgen_hbm",
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

    def test_current_hbm5_zhbm_story_stays_at_baseline(self):
        text = (
            "삼성전자 HBM5 세대로 갈수록 고객 맞춤형 설계가 본격화할 것으로 업계는 보고 있다. "
            "삼성전자는 차세대 zHBM을 개발하고 있다. zHBM은 HBM5 대비 최대 8배 성능, "
            "전력 효율 최대 3배, 열 저항을 절반 이상 낮추는 것이 목표다. "
            "zHBM은 고객 맞춤형 설계를 지원한다."
        )
        obs = w.extract_samsung_nextgen_hbm(self.event(text))
        self.assertIsNotNone(obs)
        self.assertEqual(obs["hbm5_customization_stage"], "industry_expected")
        self.assertEqual(obs["zhbm_stage"], "concept_development")
        self.assertTrue(obs["zhbm_customer_specific_design"])
        self.assertEqual(obs["zhbm_performance_vs_hbm5_x"], 8.0)
        self.assertEqual(obs["zhbm_energy_efficiency_vs_hbm5_x"], 3.0)
        self.assertEqual(obs["zhbm_thermal_resistance_reduction_floor_pct"], 50.0)

        merged = w.merge_samsung_nextgen_hbm(dict(w.SAMSUNG_NEXTGEN_HBM_BASELINE), obs)
        self.assertEqual(w.samsung_nextgen_hbm_changes(w.SAMSUNG_NEXTGEN_HBM_BASELINE, merged), [])

    def test_zhbm_customer_sample_is_stage_upgrade(self):
        old = dict(w.SAMSUNG_NEXTGEN_HBM_BASELINE)
        obs = w.extract_samsung_nextgen_hbm(self.event(
            "삼성전자가 zHBM 고객 샘플을 주요 고객사에 공급했다. zHBM은 HBM5 대비 최대 8배 성능을 목표로 한다."
        ))
        self.assertEqual(obs["zhbm_stage"], "customer_sample")
        new = w.merge_samsung_nextgen_hbm(old, obs)
        reasons = w.samsung_nextgen_hbm_changes(old, new)
        self.assertTrue(any("zHBM 단계" in x and "customer_sample" in x for x in reasons))

    def test_zhbm_contract_is_not_confused_with_concept(self):
        obs = w.extract_samsung_nextgen_hbm(self.event(
            "삼성전자가 zHBM 공급 계약을 체결했다. 고객 맞춤형 zHBM을 공동 설계한다."
        ))
        self.assertEqual(obs["zhbm_stage"], "contract_signed")

    def test_hbm5_industry_expectation_not_upgraded_to_customer_joint_development(self):
        obs = w.extract_samsung_nextgen_hbm(self.event(
            "HBM5 세대로 갈수록 고객 맞춤형 경쟁이 본격화할 것으로 업계는 보고 있다."
        ))
        self.assertEqual(obs["hbm5_customization_stage"], "industry_expected")

    def test_baseline_same_state_is_silent(self):
        old = dict(w.SAMSUNG_NEXTGEN_HBM_BASELINE)
        self.assertEqual(w.samsung_nextgen_hbm_changes(old, dict(old)), [])


if __name__ == "__main__":
    unittest.main()
