import copy
import pathlib
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "scripts"))
import rubin_hbm_watch as w


class RubinPublisherMigrationTests(unittest.TestCase):
    def test_existing_other_tracks_emit_both_reports_once_then_silent(self):
        memory = {
            "seen_ids": [],
            "seen_fact_keys": [],
            "structure_baseline_version": w.STRUCTURE_BASELINE_VERSION,
            "hbm_hybrid_bond_track_version": w.HBM_HYBRID_BOND_TRACK_VERSION,
            "hbm_hybrid_bonding": copy.deepcopy(w.HBM_HYBRID_BOND_BASELINE),
            "nvhbm_architecture_track_version": w.NVHBM_ARCH_TRACK_VERSION,
            "nvhbm_architecture": copy.deepcopy(w.NVHBM_ARCH_BASELINE),
            "nvhbm_foundry_track_version": w.NVHBM_FOUNDRY_TRACK_VERSION,
            "nvhbm_foundry_strategy": copy.deepcopy(w.NVHBM_FOUNDRY_BASELINE),
        }

        def save(path, value):
            if pathlib.Path(path).name == "rubin_hbm_pending_state.json":
                memory.update(copy.deepcopy(value))

        with tempfile.TemporaryDirectory() as temp:
            output = pathlib.Path(temp)
            with (
                patch.object(w, "OUT", output),
                patch.object(w, "load_state", side_effect=lambda: (copy.deepcopy(memory), False)),
                patch.object(w, "read_feed", return_value=([], [])),
                patch.object(w, "fetch_fx", return_value={"rate": 1400.0, "date": "2026-10-18", "error": ""}),
                patch.object(w, "write_json", side_effect=save),
            ):
                w.main()
                self.assertEqual(memory["last_send_event_count"], 2)
                self.assertEqual(memory["rubin_supply_media_track_version"], w.RUBIN_SUPPLY_MEDIA_TRACK_VERSION)
                self.assertEqual(memory["rubin_supply_media"], w.RUBIN_SUPPLY_MEDIA_NEWS)
                keys = {
                    w.rubin_supply_media_report_event(kind, fact)["fact_key"]
                    for kind, fact in w.RUBIN_SUPPLY_MEDIA_NEWS.items()
                }
                self.assertEqual(len(keys), 2)
                self.assertTrue(keys.issubset(memory["seen_fact_keys"]))
                notice = (output / "rubin_hbm_alert.md").read_text(encoding="utf-8")
                self.assertIn("DIGITIMES", notice)
                self.assertIn("서울경제", notice)
                self.assertIn("미확정", notice)
                first_keys = set(memory["seen_fact_keys"])
                w.main()
                self.assertEqual(memory["last_send_event_count"], 0)
                self.assertEqual(set(memory["seen_fact_keys"]), first_keys)


if __name__ == "__main__":
    unittest.main()
