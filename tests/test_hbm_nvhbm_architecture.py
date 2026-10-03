import pathlib
import sys
import unittest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "scripts"))
import rubin_hbm_watch as w


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


if __name__ == "__main__":
    unittest.main()
