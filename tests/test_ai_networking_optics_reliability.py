"""Offline regressions for real optics alert loss and policy-stage ambiguity."""
import importlib.util
import json
import pathlib
import tempfile
import unittest
from unittest import mock

ROOT = pathlib.Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("optics_reliability_watch", ROOT / "scripts/ai_networking_optics_watch.py")
watch = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(watch)


class OpticsReliabilityTests(unittest.TestCase):
    def test_lambda_blackwell_reprint_keeps_original_event_identity(self):
        official = "Lambda Boosts AI Factory Resiliency and Efficiency With NVIDIA Photonics - NVIDIA Blog"
        reprint = "Lambda Touts First CPO Deployment of Blackwell GPUs - HPCwire"
        expected = "sc26|lambda|cpo|first-deployment-2026-11-16"
        self.assertEqual(watch.canonical_story_key(watch.SC26_NVIDIA, official), expected)
        self.assertEqual(watch.canonical_story_key("NVIDIA", reprint), expected)
        self.assertEqual(watch.canonical_story_key(watch.SC26_NVIDIA, reprint), expected)

    def test_explicit_event_identity_merges_reprints_across_query_scopes(self):
        official = {"company": watch.SC26_NVIDIA,
                    "title": "Lambda Boosts AI Factory Resiliency and Efficiency With NVIDIA Photonics"}
        reprint = {"company": "NVIDIA", "title": "Lambda Touts First CPO Deployment of Blackwell GPUs"}
        self.assertTrue(watch.same_underlying_story(official, reprint))
        self.assertTrue(watch.same_underlying_story(reprint, official))

    def test_lambda_new_cluster_and_contract_are_not_first_deployment_reprints(self):
        original = {"company": watch.SC26_NVIDIA,
                    "title": "Lambda Boosts AI Factory Resiliency and Efficiency With NVIDIA Photonics"}
        for title in ("Lambda expands its cluster with Blackwell CPO to 20,000 GPUs",
                      "Lambda signs new contract for NVIDIA CPO Blackwell GPUs"):
            item = {"company": "NVIDIA", "title": title}
            with self.subTest(title=title):
                self.assertIn("|expansion|", watch.canonical_story_key("NVIDIA", title))
                self.assertFalse(watch.same_underlying_story(original, item))

    def test_unrelated_lambda_or_cross_company_text_is_not_globally_deduplicated(self):
        title = "Lambda Touts First CPO Deployment for New Cloud Infrastructure"
        self.assertIsNone(watch.sc26_milestone(watch.SC26_NVIDIA, title))
        a = {"company": "AlphaOptics", "title": "New 1.6T optical module starts volume production"}
        b = {"company": "BetaOptics", "title": a["title"]}
        self.assertFalse(watch.same_underlying_story(a, b))

    def test_finalizing_is_pending_and_cannot_consume_final_event(self):
        draft = "FCC is finalizing a ban on Chinese optical transceivers"
        final = "FCC finalizes a ban on Chinese optical transceivers"
        self.assertNotEqual(watch.canonical_story_key("US Optical Policy", draft),
                            watch.canonical_story_key("US Optical Policy", final))
        self.assertNotEqual(watch.stage_for(draft), watch.stage_for(final))

    def test_conditional_effective_does_not_consume_implementation(self):
        pending = "FCC optical transceiver ban could take effect after a final rule is adopted"
        effective = "FCC optical transceiver ban takes effect"
        self.assertNotEqual(watch.canonical_story_key("US Optical Policy", pending),
                            watch.canonical_story_key("US Optical Policy", effective))
        self.assertNotEqual(watch.stage_for(pending), watch.stage_for(effective))

    def test_silent_update_preserves_verified_receipt_without_inventing_one(self):
        prior = {"telegram_chat_identity_verified": True, "telegram_message_ids": [394]}
        self.assertIs(watch.preserve_delivery_metadata(prior, {})["telegram_chat_identity_verified"], True)
        self.assertNotIn("telegram_chat_identity_verified", watch.preserve_delivery_metadata({}, {}))

    def test_ninth_event_survives_eight_alert_limit_and_is_reported_next_run(self):
        companies = {name: {"ticker": name, "query": name} for name in (
            "AlphaOptics", "BetaOptics", "GammaOptics", "DeltaOptics", "EpsilonOptics",
            "ZetaOptics", "EtaOptics", "ThetaOptics", "IotaOptics")}
        rows = {name: [{"title": f"{name} starts 1.6T optical transceiver volume production for AI data centers",
                        "source": "Reuters", "source_url": "https://www.reuters.com",
                        "link": f"https://www.reuters.com/technology/{name.lower()}",
                        "published": watch.NOW.isoformat()}] for name in companies}
        with tempfile.TemporaryDirectory() as temp:
            root = pathlib.Path(temp)
            (root / "data").mkdir()
            state_path = root / "data/state.json"
            pending_path = root / "out/pending.json"
            state = {"initialized": True, "dedupe_version": 3,
                     "aaoi_power_prior_alert_correction_done": True,
                     "seen_story_keys": ["taihan|2026-09-second-shipment"]}
            state_path.write_text(json.dumps(state))
            with mock.patch.multiple(watch, ROOT=root, STATE_PATH=state_path,
                    PENDING_PATH=pending_path, ALERT_PATH=root / "out/alert.html",
                    STATUS_PATH=root / "out/status.md", COMPANIES=companies), \
                 mock.patch.object(watch, "networking_supplier_regression_checks"), \
                 mock.patch.object(watch, "new_optical_infra_regression_checks"), \
                 mock.patch.object(watch, "query_google_news", side_effect=lambda q, **kw: [dict(x) for x in rows[q]]), \
                 mock.patch.dict("os.environ", {"GITHUB_EVENT_NAME": "schedule"}):
                watch.main()
                pending = json.loads(pending_path.read_text())
                first_alert = (root / "out/alert.html").read_text()
                self.assertIn("신규 변화: <b>8건</b>", first_alert)
                item_keys = {watch.event_key(name, rows[name][0]["title"], "Reuters") for name in companies}
                self.assertEqual(len(item_keys & set(pending["seen_keys"])), 8,
                                 "An untransmitted ninth event was prematurely consumed")
                # This emulates a confirmed successful delivery committing the pending state.
                state_path.write_text(json.dumps(pending))
                watch.main()
                second_alert = (root / "out/alert.html").read_text()
                self.assertIn("신규 변화: <b>1건</b>", second_alert)
                pending2 = json.loads(pending_path.read_text())
                self.assertEqual(len(item_keys & set(pending2["seen_keys"])), 9)
                # Rendering must finish before any consumable pending state exists.
                state_path.write_text(json.dumps(state))
                with mock.patch.object(watch, "_self_test_korean_optics_alerts"), \
                     mock.patch.object(watch, "meaning_for", side_effect=RuntimeError("render failed")):
                    with self.assertRaisesRegex(RuntimeError, "render failed"):
                        watch.main()
                self.assertFalse(pending_path.exists())
                for baseline_state in ({**state, "initialized": False},
                                       {**state, "dedupe_version": 1}):
                    state_path.write_text(json.dumps(baseline_state))
                    watch.main()
                    self.assertFalse((root / "out/alert.html").exists())
                    baseline_pending = json.loads(pending_path.read_text())
                    self.assertEqual(len(item_keys & set(baseline_pending["seen_keys"])), 9)


if __name__ == "__main__":
    unittest.main()
