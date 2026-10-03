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
            "id": "mk-hbm4-price",
            "title": title,
            "description": desc,
            "source": source,
            "published_at_kst": "2026-10-02T10:00:00+09:00",
            "direct_link": "https://www.mk.co.kr/news/business/12167164",
        }

    def test_headline_only_is_reference_stage_not_contract(self):
        with mock.patch.object(w, "_article_body_text", return_value=""):
            obs = w.extract_samsung_hbm4_price_observation(self.event())
        self.assertIsNotNone(obs)
        self.assertEqual(obs["price_multiple_vs_hbm3e"], 3.0)
        self.assertEqual(obs["price_premium_vs_hbm3e_pct"], 200.0)
        self.assertEqual(obs["contract_stage"], "headline_reported")
        self.assertFalse(obs["body_verified"])
        self.assertEqual(obs["stack_height"], "unspecified")
        self.assertNotIn("price_multiple_vs_2026", obs)
        self.assertNotIn("price_yoy_pct", obs)

    def test_body_can_promote_to_negotiating_but_not_signed(self):
        body = (
            "삼성전자가 2027년 HBM4 공급 가격을 현재 주력 HBM3E 대비 3배 이상 높게 제시하고 "
            "주요 고객과 가격 협상 중이다."
        )
        with mock.patch.object(w, "_article_body_text", return_value=body):
            obs = w.extract_samsung_hbm4_price_observation(self.event())
        self.assertEqual(obs["contract_stage"], "negotiating")
        self.assertEqual(obs["price_multiple_vs_hbm3e"], 3.0)
        self.assertTrue(obs["body_verified"])

    def test_premium_article_zhbm_8x_never_becomes_hbm4_price_8x(self):
        title = '[단독] 삼성 "최고성능 HBM4 자신감, 협상력 확대"… 가격 프리미엄 강공'
        desc = "HBM가격 3배로 인상 삼성 zHBM 개발…성능 8배↑"
        body = (
            "삼성전자가 내년에 판매할 HBM4 가격을 큰 폭으로 높여 부를 수 있는 배경에는 경쟁사보다 "
            "높은 사양의 제품을 공급할 수 있다는 자신감이 자리 잡고 있다. "
            "삼성전자는 HBM4 연간 공급 가격 협상에서 1Gb당 4달러대 중후반의 가격을 제시했다. "
            "현재 주력 HBM3E 가격이 1Gb당 1.5달러 안팎으로 3배 이상 높은 수준이다. "
            "삼성전자는 차세대 zHBM을 개발 중이며 성능은 HBM5 대비 최대 8배를 목표로 한다."
        )
        e = self.event(title=title, desc=desc, source="v.daum.net")
        e["direct_link"] = "https://v.daum.net/v/xUwyJh4qhi?f=p"
        with mock.patch.object(w, "_article_body_text", return_value=body):
            obs = w.extract_samsung_hbm4_price_observation(e)
        self.assertEqual(obs["price_multiple_vs_hbm3e"], 3.0)
        self.assertEqual(obs["price_premium_vs_hbm3e_pct"], 200.0)
        self.assertNotEqual(obs["price_multiple_vs_hbm3e"], 8.0)
        self.assertEqual(obs["source"], "매일경제")
        self.assertEqual(obs["source_url"], "https://www.mk.co.kr/news/business/12167424")

    def test_performance_multiplier_without_price_context_is_rejected(self):
        self.assertIsNone(w._hbm4_price_multiple("삼성 zHBM 성능은 HBM5 대비 최대 8배다."))
        self.assertIsNone(w._hbm4_price_multiple("삼성 HBM4 업계 표준 8Gbps, 최대 13Gbps 성능이다."))

    def test_signed_contract_stage_is_distinct(self):
        self.assertEqual(
            w._hbm4_contract_stage("Samsung signed a 2027 HBM4 supply contract at the agreed price."),
            "contract_signed",
        )
        self.assertEqual(w._hbm4_contract_stage("삼성 HBM4 가격 협상이 막바지 단계다."), "final_stage")
        self.assertEqual(w._hbm4_contract_stage("삼성이 HBM4 가격 인상을 요구했다."), "proposed")

    def test_three_times_is_product_premium_not_yoy(self):
        st = dict(w.SAMSUNG_HBM4_PRICE_BASELINE)
        self.assertEqual(st["price_multiple_vs_hbm3e"], 3.0)
        self.assertEqual(st["price_premium_vs_hbm3e_pct"], 200.0)
        self.assertNotIn("price_yoy_pct", st)
        self.assertNotIn("price_multiple_vs_2026", st)

    def test_price_multiple_revision_threshold(self):
        old = dict(w.SAMSUNG_HBM4_PRICE_BASELINE)
        small = dict(old, price_multiple_vs_hbm3e=3.10, price_premium_vs_hbm3e_pct=210.0)
        big = dict(old, price_multiple_vs_hbm3e=3.30, price_premium_vs_hbm3e_pct=230.0)
        self.assertFalse(any("제시가격 배수" in x for x in w._hbm4_price_changes(old, small)))
        self.assertTrue(any("제시가격 배수" in x for x in w._hbm4_price_changes(old, big)))

    def test_stage_upgrade_always_alerts(self):
        old = dict(w.SAMSUNG_HBM4_PRICE_BASELINE)
        obs = dict(old, contract_stage="agreed", body_verified=True)
        reasons = w._hbm4_price_changes(old, obs)
        self.assertTrue(any("계약 단계" in x for x in reasons))

    def test_stack_height_is_not_inferred_when_multiple_heights_present(self):
        self.assertEqual(w._hbm4_stack_height("HBM4 8-Hi and 12-Hi prices differ"), "unspecified")
        self.assertEqual(w._hbm4_stack_height("HBM4 12-Hi price is $4/Gb"), "12hi")

    def test_contract_price_alert_is_not_displaced_by_four_other_events(self):
        price = {
            "published_at_kst": "2026-10-02T09:00:00+09:00",
            "samsung_hbm4_price_change": {"state": {}, "reasons": []},
        }
        others = [
            {"published_at_kst": f"2026-10-02T1{i}:00:00+09:00", "id": str(i)}
            for i in range(0, 5)
        ]
        selected = w.select_send_events([price, *others], limit=4)
        self.assertEqual(len(selected), 4)
        self.assertTrue(any(e.get("samsung_hbm4_price_change") for e in selected))

    def test_dedicated_telegram_message_uses_hbm3e_comparison_not_2026_or_yoy(self):
        obs = dict(w.SAMSUNG_HBM4_PRICE_BASELINE)
        obs.update({
            "title": "삼성 HBM4 가격 합의",
            "source": "매일경제",
            "source_url": "https://www.mk.co.kr/news/business/12167164",
            "observed_at": "2026-10-02T10:00:00+09:00",
            "contract_stage": "agreed",
            "body_verified": True,
        })
        e = w.samsung_hbm4_price_change_event(
            obs,
            dict(w.SAMSUNG_HBM4_PRICE_BASELINE),
            ["계약 단계 negotiating→agreed"],
        )
        out = w.build_event_alert(
            [e],
            w.datetime(2026, 10, 2, 10, 5, tzinfo=w.ZoneInfo("Asia/Seoul")),
        )
        parts = d.chunks(out)
        self.assertEqual(len(parts), 1)
        self.assertIn("삼성 HBM4 2027 계약가격 감시", parts[0])
        self.assertIn("HBM3E 대비", parts[0])
        self.assertIn("+200% 이상", parts[0])
        self.assertIn("전년 대비 HBM4 가격상승률이 아닙니다", parts[0])
        self.assertNotIn("2026년=1.0", parts[0])
        self.assertNotIn("전년 대비 환산", parts[0])

    def test_parser_correction_message_explains_8x_error(self):
        obs = dict(w.SAMSUNG_HBM4_PRICE_BASELINE)
        e = w.samsung_hbm4_price_change_event(
            obs,
            dict(w.SAMSUNG_HBM4_PRICE_BASELINE),
            [
                "파싱 오탐 정정: 8.00배→HBM3E 대비 3.00배 이상",
                "zHBM 성능 8배 수치를 HBM4 가격배수로 잘못 분류한 오류 제거",
            ],
            parser_correction=True,
        )
        out = w.build_event_alert(
            [e],
            w.datetime(2026, 10, 3, 14, 40, tzinfo=w.ZoneInfo("Asia/Seoul")),
        )
        self.assertIn("오탐 정정", out)
        self.assertIn("zHBM", out)
        self.assertIn("성능 8배", out)


if __name__ == "__main__":
    unittest.main()
