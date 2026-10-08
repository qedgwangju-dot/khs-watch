#!/usr/bin/env python3
import importlib.util
import pathlib
import sys
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]
MODULE_PATH = ROOT / "scripts" / "smartphone_memory_price_pass_through_watch.py"
spec = importlib.util.spec_from_file_location("smartphone_memory_price_pass_through_watch", MODULE_PATH)
m = importlib.util.module_from_spec(spec)
assert spec and spec.loader
spec.loader.exec_module(m)


class SmartphoneMemoryPricePassThroughTests(unittest.TestCase):
    def state(self):
        return {"metrics": dict(m.BASELINE)}

    def item(self, title, description="", source="Android Authority"):
        return {
            "title": title,
            "description": description,
            "source": source,
            "published_at_kst": "2026-10-05T12:00:00+09:00",
            "link": "https://example.com",
        }

    def test_s27_baseline_is_rumor_not_confirmed(self):
        self.assertIn("공식 미확정", m.BASELINE["s27_status"])
        self.assertEqual(m.BASELINE["s27_korea_hike_low_krw"], 100000)
        self.assertEqual(m.BASELINE["s27_korea_hike_high_krw"], 130000)

    def test_same_s27_10_to_13_manwon_repeat_does_not_alert(self):
        item = self.item(
            "Galaxy S27 price hike tipped at 100,000 won to 130,000 won",
            "Memory prices and LPDDR6 costs are blamed.",
        )
        self.assertIsNone(m._signal(item, self.state()))

    def test_material_s27_price_hike_revision_alerts(self):
        item = self.item(
            "Galaxy S27 price hike now tipped at 150,000 won to 180,000 won",
            "Memory prices and LPDDR6 costs are blamed.",
        )
        signal = m._signal(item, self.state())
        self.assertIsNotNone(signal)
        self.assertEqual(signal["stage"], 1)
        self.assertNotIn("s27_status", signal["changes"])

    def test_low_source_cannot_trigger(self):
        item = self.item(
            "Galaxy S27 price hike 200,000 won due to memory",
            "LPDDR6 and NAND prices surge.",
            "notebookcheck.net",
        )
        self.assertIsNone(m._signal(item, self.state()))

    def test_price_pass_through_requires_memory_cost_link(self):
        self.assertFalse(
            m._is_price_pass_through("Samsung raises Galaxy phone price for tax reasons")
        )
        self.assertTrue(
            m._is_price_pass_through(
                "Samsung raises Galaxy smartphone price as memory prices and component costs rise"
            )
        )

    def test_dram_and_nand_outlook_are_not_collapsed(self):
        self.assertTrue(m.BASELINE["dram_2027_tight"])
        self.assertTrue(m.BASELINE["nand_2h27_easing"])

    def test_s27_lpddr6_ufs51_remains_rumor_baseline(self):
        self.assertEqual(m.BASELINE["s27_lpddr6_ufs51_some_models_status"], "루머")

    def test_smartphone_production_cut_does_not_become_shipment_revision(self):
        article = (
            "Samsung smartphone production cut 30% in Q4 due to memory prices. "
            "DRAM cost rose 175% and IDC expects 52 million smartphones."
        )
        self.assertIsNone(m._shipment_revision_pct(article))
        self.assertFalse(m._is_shipment_revision(article))
        self.assertFalse(m._is_price_pass_through(article))

    def test_actual_shipment_forecast_revision_is_signed(self):
        article = "Samsung smartphone shipment forecast cut 12% due to memory cost increases."
        self.assertEqual(m._shipment_revision_pct(article), -12.0)

    def test_reuters_quote_does_not_make_s27_price_official(self):
        item = self.item(
            "Galaxy S27 Samsung price hike reportedly 100000 won to 130000 won",
            "Rising memory cost was cited.",
            "Reuters",
        )
        self.assertFalse(m._is_official_samsung_item(item))
        self.assertIsNone(m._signal(item, self.state()))

    def test_direct_official_link_is_required_for_confirmation(self):
        item = self.item(
            "Galaxy S27 price hike 100000 won to 130000 won due to memory",
            "Samsung news release",
            "Samsung Global Newsroom",
        )
        self.assertFalse(m._is_official_samsung_item(item))
        item["link"] = "https://news.samsung.com/global/galaxy-s27-pricing-release"
        self.assertTrue(m._is_official_samsung_item(item))


    def test_rumor_single_upper_bound_does_not_trigger(self):
        item = self.item(
            "Samsung Galaxy S27 price increase tipped at 130,000 won",
            "Rising memory costs pressure phone makers.",
            "Reuters",
        )
        self.assertIsNone(m._signal(item, self.state()))

    def test_korean_range_parses_both_ends(self):
        self.assertEqual(m._extract_krw_hike("Galaxy S27 가격 10만~13만원 인상 전망"), (100000, 130000))
        self.assertEqual(m._extract_krw_hike("Galaxy S27 price increase 100,000 won to 130,000 won"), (100000,130000))

    def test_s27_reuters_rumor_does_not_become_official(self):
        item = self.item(
            "Samsung Galaxy S27 price increase tipped at 150,000 won to 180,000 won",
            "Memory prices higher according to a tipster.", "Reuters"
        )
        self.assertFalse(m._is_official_samsung_item(item))
        self.assertEqual(m._signal(item,self.state())["stage"], 1)

    def test_verified_samsung_source_is_required_for_official_price(self):
        item = self.item(
            "Samsung announces Galaxy S27 256GB price increase 150,000 won",
            "Samsung Galaxy S27 256GB Korea launch price increased by 150,000 won.",
            "Samsung Global Newsroom",
        )
        self.assertFalse(m._official_s27_price(item))
        item["source_url"] = "https://news.samsung.com/global"
        self.assertTrue(m._official_s27_price(item))
        sig=m._signal(item,self.state())
        self.assertEqual(sig["stage"],3)
        self.assertEqual(sig["changes"]["s27_status"],"제조사 공식 발표 확인")

    def test_official_confirmation_not_collapsed_into_rumor_fact(self):
        item=self.item(
            "Samsung announces Galaxy S27 256GB price increase 130,000 won",
            "Korea Galaxy S27 256GB price increased 130,000 won.",
            "Samsung Global Newsroom"
        )
        item["source_url"]="https://news.samsung.com"
        self.assertIn("s27_official_krw_hike_130000_130000",m._fact_keys(item))
        self.assertEqual(m._signal(item,self.state())["stage"],3)

    def test_foreign_absolute_prices_cannot_become_krw_hike(self):
        item=self.item(
            "Galaxy S27 base could cost $1,400 after S26 Ultra $1,299",
            "Taiwan price increased NT$8,000 because of NAND.", "Reuters",
        )
        self.assertIsNone(m._signal(item,self.state()))
        self.assertEqual(m._extract_krw_hike(item["title"]+" "+item["description"]),(None,None))

    def test_s27_memory_spec_rumor_not_automatically_confirmed(self):
        item=self.item(
            "Samsung Galaxy S27 expected to use LPDDR6 and UFS 5.1",
            "Price pressures and rumored hardware specifications.", "Reuters",
        )
        self.assertIsNone(m._signal(item,self.state()))

    def test_ret_price_requires_concrete_model_country_and_change(self):
        generic=self.item("Samsung smartphone price rises due to memory costs","Brands face higher memory bills.","Reuters")
        self.assertIsNone(m._signal(generic,self.state()))
        specific=self.item(
            "Samsung raises Galaxy S26 prices $100 in the U.S.",
            "Samsung Galaxy S26 smartphone price increase $100 due to memory costs.",
            "Reuters",
        )
        info=m._retail_price_event(specific)
        self.assertEqual((info["model"],info["market"],info["amount"]),("S26","미국",100))
        self.assertEqual(m._signal(specific,self.state())["stage"],2)

    def test_multiple_price_bands_do_not_get_attached_to_one_sku(self):
        item=self.item(
            "Samsung raises Galaxy S26 Ultra by $100 and $200 in the U.S.",
            "Prices vary by storage; memory costs higher.", "Reuters"
        )
        self.assertIsNone(m._retail_price_event(item))
        self.assertIsNone(m._signal(item,self.state()))

    def test_memory_price_percent_not_shipment_change(self):
        self.assertIsNone(m._shipment_revision_pct(
            "Samsung LPDDR memory prices rise 20% while smartphone shipments forecast unchanged."
        ))

    def test_verified_shipment_downward_revision_is_detected(self):
        item=self.item(
            "Samsung smartphone shipments forecast cut 8% due to memory prices",
            "NAND and LPDDR supply costs hurt smartphone demand.", "TrendForce"
        )
        self.assertEqual(m._shipment_revision_pct(item["title"]+" "+item["description"]),-8.0)
        self.assertEqual(m._signal(item,self.state())["stage"],2)

    def test_corrupt_state_fails_closed(self):
        import tempfile
        from unittest.mock import patch
        with tempfile.TemporaryDirectory() as d:
            p=pathlib.Path(d)/"state.json"
            p.write_text("{broken",encoding="utf-8")
            with patch.object(m,"STATE_PATH",p):
                with self.assertRaises(RuntimeError):
                    m._load_state()

    def test_newer_rumor_cannot_overwrite_older_official_price(self):
        remote={
            "updated_at_kst":"2026-10-08T14:00:00+09:00",
            "metrics":{"s27_status":"제조사 공식 발표 확인",
                       "s27_korea_hike_low_krw":150000,"s27_korea_hike_high_krw":180000},
        }
        local={
            "updated_at_kst":"2026-10-08T15:00:00+09:00",
            "metrics":{"s27_status":"팁스터 기반 전망",
                       "s27_korea_hike_low_krw":100000,"s27_korea_hike_high_krw":130000},
        }
        merged=m._merge_checkpoint_states(remote,local)
        self.assertEqual(merged["metrics"]["s27_korea_hike_high_krw"],180000)
        self.assertEqual(merged["metrics"]["s27_status"],"제조사 공식 발표 확인")

    def test_concurrent_state_checkpoint_merges_all_dedupe_keys(self):
        remote={
            "updated_at_kst":"2026-10-08T15:00:00+09:00",
            "initial_alert_sent":True,"seen":["a"],"seen_fact_keys":["old"],
            "metrics":{"s27_status":"제조사 공식 발표 확인","x":9},
        }
        local={
            "updated_at_kst":"2026-10-08T14:59:00+09:00",
            "initial_alert_sent":True,"seen":["b"],"seen_fact_keys":["new"],
            "metrics":{"s27_status":"팁스터 기반 전망","x":8},
        }
        out=m._merge_checkpoint_states(remote,local)
        self.assertEqual(out["metrics"]["x"],9)
        self.assertEqual(out["metrics"]["s27_status"],"제조사 공식 발표 확인")
        self.assertEqual(set(out["seen_fact_keys"]),{"old","new"})
        self.assertEqual(set(out["seen"]),{"a","b"})


if __name__ == "__main__":
    result = unittest.TextTestRunner(verbosity=2).run(
        unittest.defaultTestLoader.loadTestsFromTestCase(SmartphoneMemoryPricePassThroughTests)
    )
    if not result.wasSuccessful():
        sys.exit(1)
