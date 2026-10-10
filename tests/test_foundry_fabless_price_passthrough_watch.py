import pathlib
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "scripts"))
import foundry_fabless_price_passthrough_watch as w


class FoundryFablessPricePassThroughTests(unittest.TestCase):
    def item(self, title, desc="", source="Economic Daily News", link="https://money.udn.com/money/amp/story/5612/9794455"):
        return {
            "title": title,
            "description": desc,
            "source": source,
            "link": link,
            "published_kst": "2026-10-06T18:00:00+09:00",
            "fingerprint": w._fingerprint(title, source),
        }

    def test_baseline_preserves_reported_not_official_status(self):
        b = w.BASELINE
        self.assertEqual(b["fabless_hike_min_pct"], 5.0)
        self.assertEqual(b["fabless_hike_upper_kind"], "두 자릿수")
        self.assertFalse(b["fabless_official_company_confirmed"])
        self.assertEqual(
            [b["tsmc_mature_2027_hike_min_pct"], b["tsmc_mature_2027_hike_max_pct"]],
            [3.0, 10.0],
        )
        self.assertFalse(b["tsmc_mature_official_company_confirmed"])

    def test_fabless_5_to_double_digit_does_not_invent_10pct_cap(self):
        x = self.item(
            "IC designers eye 5% to double-digit price hikes",
            "PMIC, driver IC and MCU suppliers are considering 5% to double-digit price hikes "
            "as foundry and backend manufacturing costs rise.",
            source="TrendForce",
            link=w.TREND_NEWS_URL,
        )
        obs = w._extract_state(x)
        self.assertIsNotNone(obs)
        self.assertEqual(obs["fabless_hike_min_pct"], 5.0)
        self.assertEqual(obs["fabless_hike_upper_kind"], "두 자릿수")
        self.assertFalse(obs["fabless_official_company_confirmed"])

    def test_tsmc_mature_3_to_10_report_is_not_official(self):
        x = self.item(
            "TSMC mature-node foundry price increase from January 2027",
            "TSMC mature-node prices are expected to increase 3% to 10% from January 2027.",
        )
        obs = w._extract_state(x)
        self.assertIsNotNone(obs)
        self.assertEqual(obs["tsmc_mature_2027_hike_min_pct"], 3.0)
        self.assertEqual(obs["tsmc_mature_2027_hike_max_pct"], 10.0)
        self.assertFalse(obs["tsmc_mature_official_company_confirmed"])

    def test_official_vendor_price_hike_promotes_confirmation(self):
        x = self.item(
            "Renesas announces price increase effective January 2027",
            "Renesas will raise prices for selected MCU and power IC products effective January 1, 2027.",
            source="Renesas",
            link="https://www.renesas.com/us/en/about/newsroom/example",
        )
        obs = w._extract_state(x)
        self.assertIsNotNone(obs)
        self.assertTrue(obs["fabless_official_company_confirmed"])
        self.assertIn("Renesas", obs["official_fabless_vendors"])

    def test_secondary_article_cannot_clear_existing_official_confirmation(self):
        old = dict(w.BASELINE)
        old["fabless_official_company_confirmed"] = True
        old["official_fabless_vendors"] = "Renesas"
        x = self.item(
            "IC designers consider further price hikes",
            "PMIC, driver IC and MCU suppliers consider 5% to double-digit price increases.",
        )
        obs = w._extract_state(x)
        merged = w._merge(old, obs)
        self.assertTrue(merged["fabless_official_company_confirmed"])
        self.assertEqual(merged["official_fabless_vendors"], "Renesas")

    def test_material_price_revision_threshold(self):
        old = dict(w.BASELINE)
        small = dict(old, tsmc_mature_2027_hike_max_pct=11.0)
        big = dict(old, tsmc_mature_2027_hike_max_pct=13.0)
        self.assertEqual(w._changes(old, small), [])
        self.assertTrue(any("10.0%→13.0%" in x for x in w._changes(old, big)))

    def test_inventory_pullin_not_treated_as_broad_recovery(self):
        x = self.item(
            "IC designers see customers pulling in orders",
            "Customers are pulling in orders due to expected foundry price hikes, "
            "but suppliers say this does not reflect a broad-based recovery.",
        )
        # Add price/foundry context so it belongs to this watcher.
        x["description"] += " Foundry price increase is the main cost driver for PMIC vendors."
        obs = w._extract_state(x)
        self.assertIsNotNone(obs)
        self.assertTrue(obs["order_pull_in_reported"])
        self.assertFalse(obs["broad_demand_recovery_confirmed"])
        self.assertTrue(obs["inventory_risk_flag"])

    def test_untrusted_repost_does_not_promote_state(self):
        x = self.item(
            "TSMC foundry price hike drives PMIC price increase",
            "PMIC vendors may raise prices 5% to double-digit percentages.",
            source="Random Blog",
            link="https://example.com/post",
        )
        self.assertIsNone(w._extract_state(x))

    def test_generic_foundry_capacity_news_without_price_is_rejected(self):
        x = self.item(
            "TSMC 3nm capacity remains tight",
            "AI demand keeps utilization high.",
            source="TrendForce",
            link="https://www.trendforce.com/example",
        )
        self.assertFalse(w._is_relevant(x))


    def semicap_item(self, title, desc="", link="https://www.thelec.kr/news/articleView.html?idxno=63515"):
        x = self.item(title, desc, "디일렉", link)
        x["published_kst"] = "2026-10-10T09:55:00+09:00"
        return x

    def test_asml_media_report_is_not_vendor_confirmation(self):
        x = self.semicap_item("ASML, 유지보수용 노광장비 부품값 10% 일괄 인상", "내년 1월 적용")
        self.assertEqual(w._semicap_source_grade(x, "ASML"), "reported")
        self.assertIsNone(w._semicap_observation(x))

    def test_semicap_one_time_setup_message_and_repeat_suppression(self):
        with tempfile.TemporaryDirectory() as td:
            root = pathlib.Path(td)
            state, out = root / "state.json", root / "out"
            out.mkdir()
            state.write_text('{"initialized":true,"current":{}}', encoding="utf-8")
            with patch.object(w, "STATE_PATH", state), patch.object(w, "OUT_DIR", out), \
                 patch.object(w, "ALERT_PATH", out / "alert.html"), \
                 patch.object(w, "PENDING_PATH", out / "pending.json"), \
                 patch.object(w, "STATUS_PATH", out / "status.md"):
                w.write_outputs([], [])
                msg = (out / "alert.html").read_text(encoding="utf-8")
                self.assertIn("EUV·DUV 교체부품", msg)
                self.assertIn("업체 공식 공지 미확인", msg)
                self.assertIn("신규 노광장비 가격 인상은 아직 협의 단계", msg)
                self.assertNotIn("파운드리→팹리스 가격 전가 변화", msg)
                pending = __import__("json").loads((out / "pending.json").read_text(encoding="utf-8"))
                self.assertIn(w.SEMICAP_BASELINE_KEY, pending["semicap_watch"]["delivered_keys"])
                state.write_text(__import__("json").dumps(pending), encoding="utf-8")
                w.write_outputs([], [])
                self.assertFalse((out / "alert.html").exists())

    def test_semicap_fake_source_cannot_claim_asml_hike(self):
        x = self.semicap_item("ASML spare parts 15% price increase", "Effective January 2027",
                              link="https://unverified.example/post")
        x["source"] = "ASML"
        self.assertIsNone(w._semicap_observation(x))

    def test_semicap_material_15pct_revision_and_first_party_10pct(self):
        x = self.semicap_item("ASML spare parts 15% price increase January 2027",
                              "ASML replacement parts prices rise 15%")
        obs = w._semicap_observation(x)
        self.assertEqual(obs["grade"], "reported")
        self.assertEqual(obs["rate"], "15%")
        x["title"] = "ASML spare parts 10% price increase effective January 2027"
        x["link"] = "https://www.asml.com/en/news/press-releases/example"
        obs2 = w._semicap_observation(x)
        self.assertEqual(obs2["grade"], "official")
        self.assertNotEqual(obs2["key"], w.SEMICAP_BASELINE_KEY)

    def test_semicap_2027_equipment_negotiation_not_a_hike(self):
        x = self.semicap_item("ASML negotiating new equipment price increase 10%",
                              "New lithography system prices are in talks",
                              link="https://www.asml.com/en/news/press-releases/example")
        self.assertIsNone(w._semicap_observation(x))
        x["title"] = "ASML to raise new lithography equipment prices 10% effective January 2027"
        x["description"] = "New system shipment prices"
        self.assertEqual(w._semicap_observation(x)["scope"], "systems")

    def test_semicap_peer_price_requires_first_party_not_repost(self):
        x = self.semicap_item("Tokyo Electron equipment price increase 8% January 2027",
                              "Price adjustment to semiconductor equipment",
                              link="https://www.tel.com/newsroom/release")
        self.assertEqual(w._semicap_observation(x)["vendor"], "Tokyo Electron")
        x["link"] = "https://www.thelec.kr/news/articleView.html?idxno=99"
        self.assertIsNone(w._semicap_observation(x))

    def test_no_change_baseline_stays_silent(self):
        with tempfile.TemporaryDirectory() as td:
            root = pathlib.Path(td)
            state_path = root / "state.json"
            out = root / "out"
            out.mkdir()
            state_path.write_text(
                __import__("json").dumps({
                    "initialized": True,
                    "track_version": 1,
                    "current": w.BASELINE,
                    "seen_fingerprints": [],
                    "delivered_event_keys": [],
                    "semicap_watch": {"delivered_keys": [w.SEMICAP_BASELINE_KEY]},
                }),
                encoding="utf-8",
            )
            with patch.object(w, "STATE_PATH", state_path), patch.object(w, "OUT_DIR", out), \
                 patch.object(w, "ALERT_PATH", out / "alert.html"), \
                 patch.object(w, "PENDING_PATH", out / "pending.json"), \
                 patch.object(w, "STATUS_PATH", out / "status.md"):
                w.write_outputs([], [])
                self.assertFalse((out / "alert.html").exists())


if __name__ == "__main__":
    unittest.main()
