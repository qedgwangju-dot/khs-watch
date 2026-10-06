import pathlib
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "scripts"))
import abf_package_substrate_cycle_watch as w


class ABFPackageSubstrateWatchTests(unittest.TestCase):
    def item(self, title, desc="", source="Hilo Research", link="https://www.xxquant.com/en/institution/institutional-research/e9049647f76459043c0fe4af2e72ff82"):
        return {
            "title": title,
            "description": desc,
            "source": source,
            "link": link,
            "published_kst": "2026-10-06T17:30:00+09:00",
            "fingerprint": w._fingerprint(title, source),
        }

    def test_user_chart_is_prior_not_live_baseline(self):
        self.assertEqual(
            [w.PRIOR_BofA["shortage_2026_pct"], w.PRIOR_BofA["shortage_2027_pct"], w.PRIOR_BofA["shortage_2028_pct"]],
            [4.0, 10.0, 16.0],
        )
        self.assertEqual(
            [w.CURRENT_BofA["shortage_2026_pct"], w.CURRENT_BofA["shortage_2027_pct"], w.CURRENT_BofA["shortage_2028_pct"]],
            [7.0, 14.0, 19.0],
        )

    def test_old_4_10_16_repost_is_historical_only(self):
        x = self.item(
            "BofA semiconductor package substrate supply shortage expected from 2026 onward",
            "ABF substrate supply shortage 2026/2027/2028: 4% / 10% / 16%.",
        )
        obs = w._extract_bofa(x)
        self.assertIsNotNone(obs)
        self.assertTrue(obs["historical_prior_repost"])
        self.assertNotIn("shortage_2028_pct", obs)

    def test_latest_bofa_7_14_19_and_server_cpu_share_extract(self):
        x = self.item(
            "BofA raises ABF substrate shortage outlook",
            "ABF substrate shortage 2026/2027/2028: 7% / 14% / 19%. "
            "Server CPU share of ABF demand 17% / 21% / 21%. "
            "Supply growth 12% / 22% / 19%.",
        )
        obs = w._extract_bofa(x)
        self.assertIsNotNone(obs)
        self.assertEqual(obs["shortage_2028_pct"], 19.0)
        self.assertEqual(obs["server_cpu_share_2027_pct"], 21.0)
        self.assertEqual(obs["supply_growth_2027_pct"], 22.0)

    def test_material_shortage_revision_requires_two_percentage_points(self):
        old = dict(w.CURRENT_BofA)
        small = dict(old, shortage_2028_pct=20.0)
        big = dict(old, shortage_2028_pct=22.0)
        self.assertEqual(w._material_changes(old, small), [])
        self.assertTrue(any("19.0%→22.0%" in x for x in w._material_changes(old, big)))

    def test_server_cpu_share_revision_requires_three_percentage_points(self):
        old = dict(w.CURRENT_BofA)
        changed = dict(old, server_cpu_share_2027_pct=25.0)
        self.assertTrue(any("21.0%→25.0%" in x for x in w._material_changes(old, changed)))

    def test_capacity_event_for_supplier_is_structural(self):
        x = self.item(
            "Unimicron expands high-end ABF substrate capacity by 35%",
            "AI server CPU demand drives capacity expansion and customer qualification.",
            source="Reuters",
            link="https://www.reuters.com/technology/example",
        )
        ev = w._event(x)
        self.assertIsNotNone(ev)
        self.assertIn("capacity", ev["event_types"])
        self.assertIn("Unimicron", ev["suppliers"])

    def test_generic_pcb_stock_news_is_rejected(self):
        x = self.item(
            "PCB stocks rise as investors rotate into AI names",
            "Shares jump after analyst target-price changes.",
            source="Reuters",
            link="https://www.reuters.com/markets/example",
        )
        self.assertFalse(w._is_abf_item(x))
        self.assertIsNone(w._event(x))

    def test_untrusted_bofa_repost_does_not_promote_typed_state(self):
        x = self.item(
            "BofA ABF substrate shortage 7% 14% 19%",
            "BofA says ABF substrate supply shortage 7% / 14% / 19%.",
            source="Random Blog",
            link="https://example.com/post",
        )
        self.assertIsNone(w._extract_bofa(x))

    def test_bootstrap_emits_one_correction_alert(self):
        with tempfile.TemporaryDirectory() as td:
            root = pathlib.Path(td)
            state = root / "state.json"
            out = root / "out"
            out.mkdir()
            state.write_text(
                __import__("json").dumps({
                    "initialized": True,
                    "track_version": 1,
                    "bootstrap_pending": True,
                    "bofa_prior": w.PRIOR_BofA,
                    "bofa_current": w.CURRENT_BofA,
                    "seen_fingerprints": [],
                    "delivered_event_keys": [],
                }),
                encoding="utf-8",
            )
            with patch.object(w, "STATE_PATH", state), patch.object(w, "OUT_DIR", out), \
                 patch.object(w, "ALERT_PATH", out / "alert.html"), \
                 patch.object(w, "PENDING_PATH", out / "pending.json"), \
                 patch.object(w, "STATUS_PATH", out / "status.md"):
                w.write_outputs([], [])
                alert = (out / "alert.html").read_text(encoding="utf-8")
                self.assertIn("4%/10%/16%", alert)
                self.assertIn("7%/14%/19%", alert)
                pending = __import__("json").loads((out / "pending.json").read_text())
                self.assertFalse(pending["bootstrap_pending"])

    def test_after_bootstrap_no_change_stays_silent(self):
        with tempfile.TemporaryDirectory() as td:
            root = pathlib.Path(td)
            state = root / "state.json"
            out = root / "out"
            out.mkdir()
            state.write_text(
                __import__("json").dumps({
                    "initialized": True,
                    "track_version": 1,
                    "bootstrap_pending": False,
                    "bofa_prior": w.PRIOR_BofA,
                    "bofa_current": w.CURRENT_BofA,
                    "seen_fingerprints": [],
                    "delivered_event_keys": [],
                }),
                encoding="utf-8",
            )
            with patch.object(w, "STATE_PATH", state), patch.object(w, "OUT_DIR", out), \
                 patch.object(w, "ALERT_PATH", out / "alert.html"), \
                 patch.object(w, "PENDING_PATH", out / "pending.json"), \
                 patch.object(w, "STATUS_PATH", out / "status.md"):
                w.write_outputs([], [])
                self.assertFalse((out / "alert.html").exists())


if __name__ == "__main__":
    unittest.main()
