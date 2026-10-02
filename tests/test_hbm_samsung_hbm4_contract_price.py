import pathlib
import sys
import unittest
from unittest import mock

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "scripts"))
import samsung_hbm_watch as w
import hbm_delivery as d


class SamsungHBM4ContractPriceTests(unittest.TestCase):
    def event(self, title="[단독] 삼성, 내년 HBM4 가격 3배 높인다", desc="", source="매일경제"):
        return {
            "id":"mk-hbm4-price",
            "title":title,
            "description":desc,
            "source":source,
            "published_at_kst":"2026-10-02T10:00:00+09:00",
            "direct_link":"https://www.mk.co.kr/news/business/12167164",
        }

    def test_headline_only_is_reference_stage_not_contract(self):
        with mock.patch.object(w, "_article_body_text", return_value=""):
            obs=w.extract_samsung_hbm4_price_observation(self.event())
        self.assertIsNotNone(obs)
        self.assertEqual(obs["price_multiple_vs_2026"],3.0)
        self.assertEqual(obs["price_yoy_pct"],200.0)
        self.assertEqual(obs["contract_stage"],"headline_reported")
        self.assertFalse(obs["body_verified"])
        self.assertEqual(obs["stack_height"],"unspecified")

    def test_body_can_promote_to_negotiating_but_not_signed(self):
        body="삼성전자가 2027년 HBM4 공급 가격을 올해의 3배 수준으로 높이는 방안을 놓고 주요 고객과 가격 협상 중이다."
        with mock.patch.object(w, "_article_body_text", return_value=body):
            obs=w.extract_samsung_hbm4_price_observation(self.event())
        self.assertEqual(obs["contract_stage"],"negotiating")
        self.assertTrue(obs["body_verified"])

    def test_signed_contract_stage_is_distinct(self):
        self.assertEqual(w._hbm4_contract_stage("Samsung signed a 2027 HBM4 supply contract at the agreed price."),"contract_signed")
        self.assertEqual(w._hbm4_contract_stage("삼성 HBM4 가격 협상이 막바지 단계다."),"final_stage")
        self.assertEqual(w._hbm4_contract_stage("삼성이 HBM4 가격 인상을 요구했다."),"proposed")

    def test_three_times_is_plus_200_not_plus_300(self):
        st=dict(w.SAMSUNG_HBM4_PRICE_BASELINE)
        self.assertEqual(st["price_multiple_vs_2026"],3.0)
        self.assertEqual(st["price_yoy_pct"],200.0)

    def test_price_multiple_revision_threshold(self):
        old=dict(w.SAMSUNG_HBM4_PRICE_BASELINE)
        small=dict(old,price_multiple_vs_2026=3.10,price_yoy_pct=210.0)
        big=dict(old,price_multiple_vs_2026=3.30,price_yoy_pct=230.0)
        self.assertFalse(any("가격 수준" in x for x in w._hbm4_price_changes(old,small)))
        self.assertTrue(any("가격 수준" in x for x in w._hbm4_price_changes(old,big)))

    def test_stage_upgrade_always_alerts(self):
        old=dict(w.SAMSUNG_HBM4_PRICE_BASELINE)
        obs=dict(old,contract_stage="agreed",body_verified=True)
        reasons=w._hbm4_price_changes(old,obs)
        self.assertTrue(any("계약 단계" in x for x in reasons))
        self.assertTrue(any("본문 직접 확인" in x for x in reasons))

    def test_stack_height_is_not_inferred_when_multiple_heights_present(self):
        self.assertEqual(w._hbm4_stack_height("HBM4 8-Hi and 12-Hi prices differ"),"unspecified")
        self.assertEqual(w._hbm4_stack_height("HBM4 12-Hi price is $4/Gb"),"12hi")

    def test_dedicated_telegram_message(self):
        obs=dict(w.SAMSUNG_HBM4_PRICE_BASELINE)
        obs.update({
            "title":"삼성 HBM4 가격 합의",
            "source":"매일경제",
            "source_url":"https://www.mk.co.kr/news/business/12167164",
            "observed_at":"2026-10-02T10:00:00+09:00",
            "contract_stage":"agreed",
            "body_verified":True,
        })
        e=w.samsung_hbm4_price_change_event(obs,dict(w.SAMSUNG_HBM4_PRICE_BASELINE),["계약 단계 headline_reported→agreed"])
        out=w.build_event_alert([e],w.datetime(2026,10,2,10,5,tzinfo=w.ZoneInfo("Asia/Seoul")))
        parts=d.chunks(out)
        self.assertEqual(len(parts),1)
        self.assertIn("삼성 HBM4 2027 계약가격 감시",parts[0])
        self.assertIn("+200%",parts[0])
        self.assertIn("실제 고객 체결가격",parts[0])


if __name__=="__main__":
    unittest.main()
