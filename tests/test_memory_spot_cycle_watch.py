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

    def test_nand_divergence_baseline_and_thresholds(self):
        old = dict(w.NAND_DIVERGENCE_BASELINE)
        self.assertEqual(old["enterprise_direction"], "up")
        self.assertEqual(old["consumer_direction"], "weak")
        self.assertEqual(w._nand_divergence_changes(old, dict(old)), [])
        self.assertTrue(any("소비자 SSD/UFS 방향" in x for x in w._nand_divergence_changes(old, dict(old, consumer_direction="recovery"))))

    def test_nand_divergence_extracts_official_4q26_structure(self):
        item = {
            "title": "4Q26 Memory Price Forecast",
            "description": (
                "Enterprise SSD surge 23-28% QoQ. Consumer segments see only minimal compensatory increases. "
                "Overall NAND Flash up 15-20% QoQ. QLC enterprise SSD expands on KV cache offloading."
            ),
            "source": "TrendForce Research",
            "link": "https://www.trendforce.com/research/download/RP260924PL",
            "published_kst": "2026-09-24T09:00:00+09:00",
        }
        obs = w._extract_nand_divergence(item)
        self.assertEqual(obs["enterprise_direction"], "up")
        self.assertEqual(obs["consumer_direction"], "weak")
        self.assertEqual(obs["enterprise_ssd_q4_min_pct"], 23.0)
        self.assertTrue(obs["kv_cache_qlc"])

    def test_legacy_dram_unverified_edgewater_is_not_promoted(self):
        item = {
            "title": "Edgewater says Samsung may extend LP4X support to 2028",
            "description": "SK Hynix plans LP4 EOL in 2027; second-tier fulfillment 50%.",
            "source": "Edgewater",
            "link": "https://example.com/edgewater",
            "published_kst": "2026-09-30T09:00:00+09:00",
        }
        self.assertIsNone(w._extract_legacy_dram_state(item))

    def test_legacy_dram_official_confirmation_promotes(self):
        item = {
            "title": "Samsung LPDDR4X support extension",
            "description": "Samsung LPDDR4X support extended through 2028.",
            "source": "Samsung",
            "link": "https://news.samsung.com/example",
            "published_kst": "2026-10-01T09:00:00+09:00",
        }
        obs = w._extract_legacy_dram_state(item)
        self.assertEqual(obs["samsung_lp4x_support_end_year"], 2028)
        self.assertTrue(any("신규 확인" in x for x in w._legacy_dram_changes({}, obs)))

    def test_nand_wafer_contract_title_is_not_misclassified_as_dram_capa(self):
        self.assertEqual(w.classify("NAND Flash Wafer Contract Price Sep. 2026"), "NAND/eSSD")
        with patch.object(w, "_fetch", side_effect=RuntimeError("offline")):
            translated = w._translate_to_ko("NAND Flash Wafer Contract Price Sep. 2026")
        self.assertIn("NAND Flash 웨이퍼 계약가", translated)
        self.assertNotIn("DRAM 웨이퍼", translated)

    def test_sparse_monthly_price_sheet_is_suppressed(self):
        details = w._price_change_details("NAND Flash Contract Price Sep. 2026", "NAND Flash Contract Price Sep. 2026")
        signals = w._market_signal_details("NAND Flash Contract Price Sep. 2026", "NAND Flash Contract Price Sep. 2026")
        self.assertTrue(w._is_sparse_price_sheet("NAND Flash Contract Price Sep. 2026", details, signals))

    def test_public_nand_summary_is_substantive_and_not_suppressed(self):
        blob = (
            "As original manufacturers shift production capacity to high-layer 3D processes, "
            "niche NAND Flash prices remain high. Buyer cost pressure and supply discrepancies "
            "limit further price increases."
        )
        details = w._price_change_details("NAND Flash Contract Price Sep. 2026", blob)
        signals = w._market_signal_details("NAND Flash Contract Price Sep. 2026", blob)
        self.assertTrue(any("고단수 3D NAND" in x for x in signals))
        self.assertTrue(any("높은 수준" in x for x in signals))
        self.assertFalse(w._is_sparse_price_sheet("NAND Flash Contract Price Sep. 2026", details, signals))

    def test_bernstein_this_quarter_headline_routes_to_typed_state(self):
        item = {
            "title": "Memory Supercycle Intensifies: Bernstein Sees DRAM, NAND Prices Up Nearly 20% This Quarter",
            "description": "",
            "source": "finance.biggo.com",
            "link": "https://example.com/bernstein",
            "published_kst": "2026-09-30T00:35:00+09:00",
        }
        self.assertTrue(w._is_bernstein_memory_cycle_item(item))

    def test_trendforce_4q26_revision_extracts_latest_official_ranges(self):
        item = {
            "title": "AI Server Demand Sustains Memory Contract Price Increases in 4Q26, While Consumer-Side Pressure Persists, Says TrendForce",
            "description": (
                "Conventional DRAM contract prices are projected to grow 10-15% QoQ in 4Q26, "
                "while NAND Flash contract prices are expected to increase 15-20%. "
                "Enterprise SSD contract prices surge 23-28% QoQ."
            ),
            "source": "TrendForce",
            "link": "https://www.trendforce.com/presscenter/news/20260930-13258.html",
            "published_kst": "2026-09-30T09:00:00+09:00",
        }
        obs = w._extract_trendforce_4q26_revision(item)
        self.assertEqual(obs["conventional_dram_min_pct"], 10.0)
        self.assertEqual(obs["conventional_dram_max_pct"], 15.0)
        self.assertEqual(obs["overall_nand_min_pct"], 15.0)
        self.assertEqual(obs["overall_nand_max_pct"], 20.0)
        self.assertEqual(obs["enterprise_ssd_min_pct"], 23.0)
        self.assertEqual(obs["enterprise_ssd_max_pct"], 28.0)

    def test_trendforce_4q26_revision_compares_july_to_september(self):
        old = dict(w.TREND_4Q26_PRIOR_BASELINE)
        new = dict(w.TREND_4Q26_CURRENT_BASELINE)
        changes = w._trendforce_4q26_revision_changes(old, new)
        self.assertIn("Conventional DRAM: +3~8%→+10~15% QoQ", changes)
        self.assertIn("NAND Flash: +0~5%→+15~20% QoQ", changes)
        self.assertIn("Enterprise SSD: +23~28% QoQ 신규 기준", changes)
        summary = w._trendforce_4q26_revision_summary(old, new)
        self.assertIn("DRAM 밴드 중간값 5.5%→12.5% (+7.0%p)", summary)
        self.assertIn("NAND 밴드 중간값 2.5%→17.5% (+15.0%p)", summary)

    def test_main_runs_currency_guard_after_output_generation(self):
        with patch.object(w, "collect", return_value=([], [])), \
             patch.object(w, "write_outputs"), \
             patch.object(w.currency_krw_guard, "enforce_file") as guard:
            w.main()
        guard.assert_called_once_with(w.ALERT_PATH)


if __name__ == "__main__":
    unittest.main()
