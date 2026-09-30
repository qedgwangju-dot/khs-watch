import pathlib
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "scripts"))
import memory_spot_cycle_watch as w


class MemorySpotCycleWatchTests(unittest.TestCase):
    def test_4q26_price_forecast_exposes_specific_contract_price_changes(self):
        blob = (
            "4Q26 Contract Prices for Enterprise SSD Surge 23-28% QoQ Against Trend, "
            "Consumer Segments See Only Minimal Compensatory Increases, "
            "Overall NAND Flash Up 15-20% QoQ. "
            "AI Server Demand Continues to Support 4Q26 DRAM Price Hikes."
        )
        details = w._price_change_details("4Q26 Memory Price Forecast", blob)
        self.assertIn("기업용 SSD 계약가: 4Q26 +23~28% QoQ", details)
        self.assertIn("NAND Flash 전체 계약가: 4Q26 +15~20% QoQ", details)
        self.assertTrue(any("DRAM 계약가" in x and "세부 등락률 미제시" in x for x in details))

    def test_dram_bulletin_states_price_type_and_public_numeric_limit(self):
        blob = (
            "Tight supply and robust CSP demand keep DRAM undersupplied; "
            "TrendForce lifts its 4Q26 contract price outlook. "
            "Segment Trends: PC and server lead gains; mobile and consumer cool on high bases."
        )
        details = w._price_change_details("DRAM Market Bulletin - Sep. 23, 2026", blob)
        self.assertTrue(any("DRAM 계약가: 4Q26 전망 상향" in x for x in details))
        self.assertTrue(any("PC·서버 DRAM" in x for x in details))

    def test_hbm_bulletin_does_not_invent_a_numeric_band(self):
        blob = (
            "Amid tight supply and richer HBM4 mix, TrendForce sharply lifts its 2027 HBM price outlook. "
            "8-Hi leads shipments and has a per-Gb premium over 12-Hi."
        )
        details = w._price_change_details("HBM Market Bulletin - Sep. 22, 2026", blob)
        self.assertTrue(any("2027년 전망 상향" in x for x in details))
        self.assertTrue(any("새 등락률·단가 범위 미제시" in x for x in details))
        self.assertTrue(any("8단 HBM" in x for x in details))

    def test_hbm_market_pricing_extracts_121_and_8hi_premium(self):
        item = {
            "title": "TrendForce 2027 HBM Blended ASP outlook",
            "description": (
                "트렌드포스는 2027년 HBM의 제품별 판매 비중을 반영한 평균판매가격(Blended ASP)이 "
                "전년 대비 121% 상승할 것으로 봤다. 8단 HBM의 Gb당 판매가격은 12단 제품보다 "
                "약 10~20% 높게 형성될 전망이며 8단 제품을 우선 적용할 것으로 예상된다."
            ),
            "source": "한국경제TV",
            "link": "https://www.wowtv.co.kr/NewsCenter/News/Read?articleId=A202609290194",
            "published_kst": "2026-09-29T18:00:00+09:00",
        }
        obs = w._extract_hbm_market_pricing(item)
        self.assertEqual(obs["blended_asp_yoy_pct"], 121.0)
        self.assertEqual(obs["eight_hi_premium_min_pct"], 10.0)
        self.assertEqual(obs["eight_hi_premium_max_pct"], 20.0)
        self.assertEqual(obs["mainstream_layers"], 8)

    def test_official_trendforce_source_is_not_overwritten_by_republisher(self):
        old = dict(w.HBM_MARKET_PRICE_BASELINE)
        republisher = {
            "period": "2027",
            "blended_asp_yoy_pct": 121.0,
            "source": "조선비즈",
            "source_url": "https://biz.chosun.com/test",
            "source_rank": 2,
            "as_of": "2026-09-29",
        }
        merged = w._merge_hbm_market_pricing(old, republisher)
        self.assertEqual(merged["source"], "TrendForce")
        self.assertIn("trendforce.com/presscenter", merged["source_url"])

    def test_trendforce_press_date_parses_official_url(self):
        d = w._trendforce_press_date("https://www.trendforce.com/presscenter/news/20260929-13255.html")
        self.assertEqual(d.date().isoformat(), "2026-09-29")

    def test_hbm_market_pricing_thresholds(self):
        old = dict(w.HBM_MARKET_PRICE_BASELINE)
        small = dict(old, blended_asp_yoy_pct=128.0)
        big = dict(old, blended_asp_yoy_pct=132.0)
        self.assertFalse(any("Blended ASP" in x for x in w._hbm_market_pricing_changes(old, small)))
        self.assertTrue(any("Blended ASP" in x for x in w._hbm_market_pricing_changes(old, big)))
        premium = dict(old, eight_hi_premium_min_pct=15.0)
        self.assertTrue(any("프리미엄 하단" in x for x in w._hbm_market_pricing_changes(old, premium)))

    def test_hbm_market_alert_format_version_is_precise_v2(self):
        self.assertEqual(w.HBM_MARKET_ALERT_FORMAT_VERSION, 2)
        self.assertEqual(w.HBM_MARKET_PRICE_BASELINE["blended_asp_yoy_pct"], 121.0)
        self.assertEqual(w.HBM_MARKET_PRICE_BASELINE["eight_hi_premium_min_pct"], 10.0)
        self.assertEqual(w.HBM_MARKET_PRICE_BASELINE["eight_hi_premium_max_pct"], 20.0)

    def test_hbm_market_pricing_stack_regime_change_alerts(self):
        old = dict(w.HBM_MARKET_PRICE_BASELINE)
        new = dict(old, mainstream_layers=12)
        self.assertTrue(any("8단→12단" in x for x in w._hbm_market_pricing_changes(old, new)))

    def test_hbm_market_break_even_summary_uses_8hi_premium(self):
        text = w._hbm_market_break_even_summary(w.HBM_MARKET_PRICE_BASELINE)
        self.assertIn("스택당 비트 -33.3%", text)
        self.assertIn("+25.0~36.4%", text)

    def test_partial_121pct_republisher_without_trendforce_name_is_suppressed(self):
        item = {
            "title": "“내년 HBM 가격 121% 오른다…AI發 공급부족 지속”",
            "description": "",
            "source": "v.daum.net",
            "link": "https://example.com/repub",
            "published_kst": "2026-09-29T19:03:13+09:00",
        }
        self.assertTrue(w._is_hbm_market_pricing_republisher(item))

    def test_partial_average_price_republisher_is_suppressed(self):
        item = {
            "title": "“내년 HBM 평균판매가격 121% 오른다…공급 부족 현상”",
            "description": "",
            "source": "매일경제",
            "link": "https://example.com/repub2",
            "published_kst": "2026-09-29T19:02:42+09:00",
        }
        self.assertTrue(w._is_hbm_market_pricing_republisher(item))

    def test_market_pricing_republisher_is_typed_not_generic(self):
        item = {
            "title": "내년 HBM 평균판매가 121% 오른다… AI 수요에 공급 부족 지속",
            "description": "TrendForce says 2027 HBM Blended ASP rises 121% and 8-Hi leads shipments.",
            "source": "조선비즈",
            "link": "https://example.com/repub",
            "published_kst": "2026-09-29T18:14:00+09:00",
        }
        self.assertIsNotNone(w._extract_hbm_market_pricing(item))

    def test_bernstein_memory_cycle_extracts_current_baseline(self):
        item = {
            "title": "Bernstein memory supercycle update",
            "description": (
                "Conventional memory prices rise by the mid-teens to 20% in the third quarter, "
                "followed by a high-single-digit rise in the fourth quarter. "
                "Shortages persist in 2027 and prices normalize in 2028. "
                "Long-term agreements cap further price increases."
            ),
            "source": "Investing.com",
            "link": "https://example.com/bernstein",
            "published_kst": "2026-09-30T01:56:00+09:00",
        }
        obs = w._extract_bernstein_memory_cycle(item)
        self.assertEqual(obs["q3_2026_price_band"], "mid-teens~20%")
        self.assertEqual(obs["q4_2026_price_band"], "high-single-digit")
        self.assertEqual(obs["shortage_through_year"], 2027)
        self.assertEqual(obs["normalization_year"], 2028)
        self.assertTrue(obs["lta_caps_price_increases"])

    def test_bernstein_memory_cycle_only_alerts_on_state_change(self):
        old = dict(w.BERNSTEIN_MEMORY_CYCLE_BASELINE)
        same = dict(old)
        changed = dict(old, normalization_year=2029)
        self.assertEqual(w._bernstein_memory_cycle_changes(old, same), [])
        self.assertTrue(any("2028→2029" in x for x in w._bernstein_memory_cycle_changes(old, changed)))

    def test_bernstein_article_is_typed_not_generic(self):
        item = {
            "title": "Memory Supercycle Intensifies: Bernstein Sees DRAM, NAND Prices Up Nearly 20% This Quarter",
            "description": "Shortages persist in 2027; normalization is expected in 2028 and LTAs cap price increases.",
        }
        self.assertTrue(w._is_bernstein_memory_cycle_item(item))

    def test_main_runs_currency_guard_after_output_generation(self):
        with patch.object(w, "collect", return_value=([], [])), \
             patch.object(w, "write_outputs"), \
             patch.object(w.currency_krw_guard, "enforce_file") as guard:
            w.main()
        guard.assert_called_once_with(w.ALERT_PATH)


if __name__ == "__main__":
    unittest.main()
