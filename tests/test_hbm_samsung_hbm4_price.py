import pathlib
import sys
import unittest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "scripts"))
import rubin_hbm_watch as w


class SamsungHBM4PriceWatchTests(unittest.TestCase):
    def event(self, text):
        return {
            "category": "samsung_hbm4_price",
            "title": text,
            "description": "",
            "article_title": "",
            "article_description": "",
            "article_text": text,
            "source": "매일경제",
            "origin_source": "매일경제",
            "published_at_kst": "2026-10-02T15:20:00+09:00",
            "direct_link": "https://www.mk.co.kr/news/business/12167164",
        }

    def test_mk_offer_is_negotiation_not_signed(self):
        text = (
            "삼성전자는 주요 고객사와 진행 중인 2027년 HBM4 연간 공급 가격 협상에서 "
            "1Gb당 4달러대 중후반의 가격을 제시했다. 현재 HBM3E 가격은 1Gb당 1.5달러 안팎으로 "
            "3배 이상 높은 수준이다. 내년 주요 HBM 물량이 상당 부분 고객사와 협의가 끝났고 "
            "가격 협상도 이달 중 마무리 수순에 들어갈 것으로 파악된다."
        )
        obs = w.extract_samsung_hbm4_price(self.event(text))
        self.assertIsNotNone(obs)
        self.assertEqual(obs["stage"], "final_stage")
        self.assertEqual(obs["offered_price_band"], "mid_to_high_4_usd_per_gb")
        self.assertEqual(obs["reference_hbm3e_usd_per_gb"], 1.5)
        self.assertEqual(obs["price_multiple_floor"], 3.0)
        self.assertEqual(obs["volume_stage"], "largely_agreed")
        self.assertEqual(obs["target_close_month"], "2026-10")
        self.assertNotIn("offered_price_usd_per_gb_min", obs)
        self.assertNotIn("offered_price_usd_per_gb_max", obs)

    def test_mid_high_4_is_not_invented_into_numeric_range(self):
        obs = w.extract_samsung_hbm4_price(self.event(
            "삼성 2027 HBM4 가격 협상에서 1Gb당 4달러대 중후반을 제시했다. HBM3E 1Gb당 1.5달러, 3배 이상."
        ))
        self.assertEqual(obs["offered_price_band"], "mid_to_high_4_usd_per_gb")
        self.assertIsNone(obs.get("offered_price_usd_per_gb_min"))
        self.assertIsNone(obs.get("offered_price_usd_per_gb_max"))

    def test_signed_contract_upgrades_stage(self):
        obs = w.extract_samsung_hbm4_price(self.event(
            "삼성전자가 2027 HBM4 고객사 가격 협상을 타결하고 계약 체결을 완료했다. "
            "HBM4 가격 확정은 1Gb당 4.60~4.80달러다."
        ))
        self.assertEqual(obs["stage"], "signed")
        self.assertEqual(obs["offered_price_usd_per_gb_min"], 4.60)
        self.assertEqual(obs["offered_price_usd_per_gb_max"], 4.80)

    def test_baseline_same_state_is_silent(self):
        old = dict(w.SAMSUNG_HBM4_PRICE_BASELINE)
        new = dict(old)
        self.assertEqual(w.samsung_hbm4_price_changes(old, new), [])

    def test_exact_price_disclosure_alerts(self):
        old = dict(w.SAMSUNG_HBM4_PRICE_BASELINE)
        new = dict(old, offered_price_usd_per_gb_min=4.60, offered_price_usd_per_gb_max=4.80)
        reasons = w.samsung_hbm4_price_changes(old, new)
        self.assertTrue(any("제시가격 하단" in x for x in reasons))
        self.assertTrue(any("제시가격 상단" in x for x in reasons))

    def test_stage_upgrade_alerts(self):
        old = dict(w.SAMSUNG_HBM4_PRICE_BASELINE)
        new = dict(old, stage="signed")
        reasons = w.samsung_hbm4_price_changes(old, new)
        self.assertTrue(any("계약가격 단계" in x and "signed" in x for x in reasons))

    def test_typed_event_warns_offer_vs_signed(self):
        st = dict(w.SAMSUNG_HBM4_PRICE_BASELINE)
        ev = w.samsung_hbm4_price_event(st, ["기준선"])
        self.assertIn("제시·협상 가격", ev["verdict"])
        st2 = dict(st, stage="signed")
        ev2 = w.samsung_hbm4_price_event(st2, ["계약 확정"])
        self.assertIn("실제 2027 ASP", ev2["verdict"])


if __name__ == "__main__":
    unittest.main()
