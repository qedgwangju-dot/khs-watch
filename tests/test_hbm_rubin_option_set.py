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


if __name__ == "__main__":
    unittest.main()
