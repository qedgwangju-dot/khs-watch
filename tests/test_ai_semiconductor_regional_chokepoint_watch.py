import datetime as dt
import pathlib
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "scripts"))
import ai_semiconductor_regional_chokepoint_watch as w


class RegionalChokepointWatchTests(unittest.TestCase):
    def item(self, title, source="Reuters", link="https://www.reuters.com/example"):
        return {
            "title": title,
            "description": "",
            "source": source,
            "link": link,
            "published_kst": "2026-10-05T19:30:00+09:00",
            "fingerprint": w._fingerprint(title, source),
        }

    def test_75pct_is_historical_not_live_2026_metric(self):
        b = w.BASELINE["historical_concentration"]
        self.assertEqual(b["east_asia_china_semiconductor_manufacturing_capacity_pct"], 75.0)
        self.assertEqual(b["vintage"], "2021")
        self.assertFalse(b["current_live_metric"])
        self.assertIn("2021", w._baseline_context("global"))

    def test_hanmi_is_korea_hbm_equipment_not_memory_vendor(self):
        b = w.BASELINE["korea"]
        self.assertIn("Hanmi Semiconductor", b["adjacent_equipment"])
        self.assertNotIn("Hanmi Semiconductor", b["leaders"])
        self.assertIn("TC bonder", " ".join(b["notes"]))

    def test_taiwan_tracks_tsmc_and_ase_but_not_ase_only_packaging(self):
        b = w.BASELINE["taiwan"]
        self.assertEqual(b["leaders"], ["TSMC", "ASE"])
        self.assertTrue(any("TSMC" in x and "CoWoS" in x for x in b["notes"]))

    def test_china_optics_regulation_is_classified(self):
        x = self.item(
            "U.S. Congress advances restriction on Innolight and Eoptolink 1.6T optical transceivers"
        )
        c = w._classify(x)
        self.assertIsNotNone(c)
        self.assertEqual(c["region"], "china")
        self.assertEqual(c["event_type"], "regulation")
        self.assertIn("Zhongji Innolight", c["entities"])
        self.assertIn("Eoptolink", c["entities"])

    def test_japan_euv_capacity_is_classified(self):
        x = self.item(
            "Tokyo Electron expands EUV coater developer capacity for advanced semiconductor production",
            source="Tokyo Electron",
            link="https://www.tel.com/news/example.html",
        )
        c = w._classify(x)
        self.assertIsNotNone(c)
        self.assertEqual(c["region"], "japan")
        self.assertEqual(c["event_type"], "capacity")
        self.assertIn("Tokyo Electron", c["entities"])
        self.assertEqual(c["source_level"], "official")

    def test_korea_hbm4_capacity_is_classified(self):
        x = self.item(
            "SK hynix expands HBM4 mass production capacity as AI memory demand rises",
            source="SK hynix",
            link="https://news.skhynix.co.kr/example",
        )
        c = w._classify(x)
        self.assertIsNotNone(c)
        self.assertEqual(c["region"], "korea")
        self.assertEqual(c["event_type"], "capacity")
        self.assertIn("SK hynix", c["entities"])

    def test_routine_stock_move_without_structural_event_is_rejected(self):
        x = self.item("TSMC shares jump after analyst raises price target")
        self.assertIsNone(w._classify(x))

    def test_official_event_passes_evidence_gate(self):
        x = self.item(
            "TSMC begins 2nm volume production capacity ramp at new fab",
            source="TSMC",
            link="https://pr.tsmc.com/english/news/0000",
        )
        c = w._classify(x)
        self.assertIsNotNone(c)
        ok, reason = w._passes_evidence_gate([c])
        self.assertTrue(ok)
        self.assertIn("공식", reason)

    def test_single_tier1_regulation_story_is_held(self):
        x = self.item(
            "U.S. considers ban on Eoptolink 1.6T optical transceivers",
            source="Reuters",
            link="https://www.reuters.com/world/example",
        )
        c = w._classify(x)
        self.assertIsNotNone(c)
        ok, reason = w._passes_evidence_gate([c])
        self.assertFalse(ok)
        self.assertIn("2곳", reason)

    def test_two_independent_tier1_regulation_sources_pass(self):
        a = self.item(
            "U.S. considers ban on Eoptolink 1.6T optical transceivers",
            source="Reuters",
            link="https://www.reuters.com/world/example",
        )
        b = self.item(
            "FCC restriction targets Eoptolink 1.6T optical transceivers",
            source="Bloomberg",
            link="https://www.bloomberg.com/news/example",
        )
        ca, cb = w._classify(a), w._classify(b)
        self.assertIsNotNone(ca)
        self.assertIsNotNone(cb)
        # Same normalized event key is required for corroboration in live grouping.
        cb["event_key"] = ca["event_key"]
        ok, reason = w._passes_evidence_gate([ca, cb])
        self.assertTrue(ok)
        self.assertIn("2곳", reason)

    def test_memory_price_only_news_does_not_duplicate_memory_watcher(self):
        x = self.item("Samsung HBM contract price rises 20% on strong AI demand")
        self.assertIsNone(w._classify(x))

    def test_structural_numbers_are_extracted_without_inventing_values(self):
        vals = w._numbers("China share rises to 25% and capacity reaches 2.4 million wpm in 2026.")
        self.assertTrue(any("25%" in x for x in vals))
        self.assertTrue(any("2.4 million" in x for x in vals))

    def test_baseline_cutoff_prevents_existing_map_from_becoming_new_alert(self):
        with tempfile.TemporaryDirectory() as td:
            root = pathlib.Path(td)
            state_path = root / "state.json"
            out_dir = root / "out"
            out_dir.mkdir()
            state = {
                "initialized": True,
                "baseline_version": 1,
                "baseline_cutoff_kst": "2026-10-05T19:05:00+09:00",
                "baseline": w.BASELINE,
                "seen_fingerprints": [],
                "delivered_event_keys": [],
            }
            state_path.write_text(__import__("json").dumps(state), encoding="utf-8")
            old = self.item(
                "TSMC expands 2nm volume production capacity",
                source="TSMC",
                link="https://pr.tsmc.com/english/news/old",
            )
            old["published_kst"] = "2026-10-05T18:00:00+09:00"
            c = w._classify(old)
            self.assertIsNotNone(c)
            with patch.object(w, "STATE_PATH", state_path), patch.object(w, "OUT_DIR", out_dir),                  patch.object(w, "ALERT_PATH", out_dir / "alert.html"),                  patch.object(w, "PENDING_PATH", out_dir / "pending.json"),                  patch.object(w, "STATUS_PATH", out_dir / "status.md"):
                w.write_outputs([c], [])
                self.assertFalse((out_dir / "alert.html").exists())
                pending = __import__("json").loads((out_dir / "pending.json").read_text())
                self.assertEqual(pending["last_eligible_count"], 0)


if __name__ == "__main__":
    unittest.main()
