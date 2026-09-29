import datetime as dt
import importlib.util
import pathlib
import sys
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "iran_hormuz_market_turn_alert.py"
SPEC = importlib.util.spec_from_file_location("iran_hormuz_market_turn_alert", SCRIPT)
MODULE = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
sys.modules[SPEC.name] = MODULE
SPEC.loader.exec_module(MODULE)


class IranHormuzMarketTurnTests(unittest.TestCase):
    def test_final_ceasefire_is_classified(self):
        title = "US and Iran agree to ceasefire agreement, officials say - Reuters"
        self.assertEqual(MODULE.classify_event(title), "ceasefire")

    def test_ceasefire_hopes_are_rejected(self):
        title = "Markets rally on Iran ceasefire hopes - Reuters"
        self.assertIsNone(MODULE.classify_event(title))

    def test_temporary_attack_pause_is_rejected(self):
        title = "US and Iran pause strikes in hope of quick deal - Reuters"
        self.assertIsNone(MODULE.classify_event(title))

    def test_hormuz_normalization_is_classified(self):
        title = "Shipping resumes through the Strait of Hormuz as traffic returns to normal - Reuters"
        self.assertEqual(MODULE.classify_event(title), "hormuz_normalization")

    def test_event_needs_two_unique_sources(self):
        now = dt.datetime(2026, 8, 2, 12, 0, tzinfo=dt.timezone.utc)
        rows = [
            MODULE.NewsItem("US and Iran agree to ceasefire agreement", "Reuters", "a", now.isoformat(), now.timestamp(), "ceasefire"),
            MODULE.NewsItem("US and Iran agree to ceasefire agreement", "Reuters", "b", now.isoformat(), now.timestamp(), "ceasefire"),
        ]
        self.assertIsNone(MODULE.confirm_event(rows))
        rows.append(MODULE.NewsItem("Iran ceasefire agreement takes effect", "Associated Press", "c", now.isoformat(), now.timestamp(), "ceasefire"))
        result = MODULE.confirm_event(rows)
        self.assertIsNotNone(result)
        assert result is not None
        self.assertEqual(result[0], "ceasefire")
        self.assertEqual(len(result[1]), 2)

    def test_market_requires_both_yield_and_dollar_down(self):
        now = dt.datetime(2026, 8, 2, 12, 0, tzinfo=dt.timezone.utc).timestamp()
        down_yield = MODULE.Quote("^UST2Y", "미국 2년물 국채금리", "%", 4.20, 4.25, -0.05, -1.176, "", now)
        down_dxy = MODULE.Quote("DX-Y.NYB", "달러인덱스", "", 99.50, 100.00, -0.50, -0.50, "", now)
        up_dxy = MODULE.Quote("DX-Y.NYB", "달러인덱스", "", 100.20, 100.00, 0.20, 0.20, "", now)
        self.assertTrue(MODULE.market_confirms(down_yield, down_dxy))
        self.assertFalse(MODULE.market_confirms(down_yield, up_dxy))

    def test_physical_oil_flow_recovery_is_classified(self):
        title = "Saudi Arabia ramps up Gulf oil exports after pipeline attack, data shows - Reuters"
        self.assertEqual(MODULE.classify_event(title), "oil_flow_recovery")

    def test_gulf_of_oman_sts_expansion_is_classified(self):
        title = "Saudi export rerouting amid Gulf of Oman STS bottlenecks amplify VLCC intensity - Kpler"
        self.assertEqual(MODULE.classify_event(title), "sts_reroute_expansion")

    def test_kpler_primary_data_can_confirm_flow_event(self):
        now = dt.datetime(2026, 9, 27, 12, 0, tzinfo=dt.timezone.utc)
        rows = [
            MODULE.NewsItem(
                "Saudi export rerouting amid Gulf of Oman STS bottlenecks amplify VLCC intensity",
                "Kpler",
                "a",
                now.isoformat(),
                now.timestamp(),
                "sts_reroute_expansion",
            )
        ]
        result = MODULE.confirm_event(rows)
        self.assertIsNotNone(result)
        assert result is not None
        self.assertEqual(result[0], "sts_reroute_expansion")

    def test_flow_event_id_is_stable_across_reprints(self):
        now = dt.datetime(2026, 9, 27, 12, 0, tzinfo=dt.timezone.utc)
        rows_a = [
            MODULE.NewsItem(
                "Saudi Arabia ramps up Gulf oil exports after pipeline attack",
                "Reuters",
                "a",
                now.isoformat(),
                now.timestamp(),
                "oil_flow_recovery",
            )
        ]
        rows_b = [
            MODULE.NewsItem(
                "Aramco boosts Saudi crude exports from Ras Tanura",
                "Bloomberg",
                "b",
                (now + dt.timedelta(hours=8)).isoformat(),
                (now + dt.timedelta(hours=8)).timestamp(),
                "oil_flow_recovery",
            )
        ]
        self.assertEqual(MODULE.event_id("oil_flow_recovery", rows_a), MODULE.event_id("oil_flow_recovery", rows_b))

    def test_physical_flow_body_separates_sts_from_hormuz_volume(self):
        current = dt.datetime(2026, 9, 27, 12, 0, tzinfo=dt.timezone.utc)
        news = [
            MODULE.NewsItem(
                "Gulf of Oman STS volumes surge to a record",
                "Kpler",
                "a",
                current.isoformat(),
                current.timestamp(),
                "sts_reroute_expansion",
            )
        ]
        body = MODULE.build_physical_flow_alert_body("sts_reroute_expansion", news, None, current)
        self.assertIn("STS는 같은 배럴이 여러 번 이송될 수 있어", body)
        self.assertIn("합산하지 않습니다", body)
        self.assertIn("정책 발언 처리", body)

    def test_physical_flow_alert_is_glanceable(self):
        current = dt.datetime(2026, 9, 28, 11, 34, tzinfo=dt.timezone.utc)
        news = [
            MODULE.NewsItem(
                "Kpler Gulf of Oman STS record 7.2 Mbd as of 2026-09-26; since-war average 3.7 Mbd; 2025 average 0.16 Mbd; Saudi 3 Mbd requires 36-40 additional VLCCs",
                "Kpler",
                "https://example.com/kpler",
                current.isoformat(),
                current.timestamp(),
                "sts_reroute_expansion",
            )
        ]
        oil = MODULE.Quote("BZ=F", "Brent", "달러/배럴", 100.55, 103.08, -2.53, -2.45, "", current.timestamp())
        body = MODULE.build_physical_flow_alert_body("sts_reroute_expansion", news, oil, current)
        self.assertIn("[한눈에]", body)
        self.assertIn("원유 공급     회복 ↑", body)
        self.assertIn("물류 효율     병목 심화 ↓", body)
        self.assertIn("GoO STS       7.2 Mbd", body)
        self.assertIn("전쟁 후 평균의 1.9배", body)
        self.assertIn("2025 평균의 45배", body)
        self.assertIn("VLCC 수요     Saudi +3 Mbd 처리 시 +36~40척", body)
        self.assertIn("[핵심 의미]", body)
        self.assertIn("[병목]", body)
        self.assertIn("[다음 체크]", body)
        self.assertNotIn("Kpler Gulf of Oman STS record 7.2 Mbd as of", body)

    def test_east_west_pipeline_recovery_is_classified(self):
        title = "Saudi East-West Pipeline transport hits 3.5 million barrels per day - Reuters"
        self.assertEqual(MODULE.classify_event(title), "east_west_pipeline_recovery")

    def test_pipeline_event_id_uses_material_rate_bands(self):
        now = dt.datetime(2026, 9, 28, 12, 0, tzinfo=dt.timezone.utc)
        a = [MODULE.NewsItem(
            "Saudi East-West Pipeline transport hits 3.5 million barrels per day",
            "Reuters", "a", now.isoformat(), now.timestamp(), "east_west_pipeline_recovery"
        )]
        b = [MODULE.NewsItem(
            "East-West Pipeline flow reaches 3.6 million bpd",
            "Bloomberg", "b", (now + dt.timedelta(hours=2)).isoformat(),
            (now + dt.timedelta(hours=2)).timestamp(), "east_west_pipeline_recovery"
        )]
        c = [MODULE.NewsItem(
            "East-West Pipeline flow reaches 4.0 million bpd",
            "Reuters", "c", (now + dt.timedelta(hours=4)).isoformat(),
            (now + dt.timedelta(hours=4)).timestamp(), "east_west_pipeline_recovery"
        )]
        self.assertEqual(MODULE.event_id("east_west_pipeline_recovery", a), MODULE.event_id("east_west_pipeline_recovery", b))
        self.assertNotEqual(MODULE.event_id("east_west_pipeline_recovery", a), MODULE.event_id("east_west_pipeline_recovery", c))

    def test_pipeline_body_separates_flow_from_yanbu_exports(self):
        current = dt.datetime(2026, 9, 28, 12, 0, tzinfo=dt.timezone.utc)
        news = [MODULE.NewsItem(
            "Saudi East-West Pipeline transport hits 3.5 million barrels per day",
            "Reuters", "a", current.isoformat(), current.timestamp(), "east_west_pipeline_recovery"
        )]
        body = MODULE.build_physical_flow_alert_body("east_west_pipeline_recovery", news, None, current)
        self.assertIn("East-West     3.5 Mbd", body)
        self.assertIn("vs 4Mbd      약 88% 회복", body)
        self.assertIn("Yanbu 수출     실제 선적 별도 확인 필요", body)
        self.assertIn("선적 재개 확인 전 수출 정상화로 단정하지 않습니다", body)

    def test_pipeline_single_media_source_does_not_confirm(self):
        now = dt.datetime(2026, 9, 28, 12, 0, tzinfo=dt.timezone.utc)
        rows = [MODULE.NewsItem(
            "Saudi East-West Pipeline transport hits 3.5 million barrels per day",
            "Reuters", "a", now.isoformat(), now.timestamp(), "east_west_pipeline_recovery"
        )]
        self.assertIsNone(MODULE.confirm_event(rows))

    def test_pipeline_two_sources_confirm(self):
        now = dt.datetime(2026, 9, 28, 12, 0, tzinfo=dt.timezone.utc)
        rows = [
            MODULE.NewsItem(
                "Saudi East-West Pipeline transport hits 3.5 million barrels per day",
                "Reuters", "a", now.isoformat(), now.timestamp(), "east_west_pipeline_recovery"
            ),
            MODULE.NewsItem(
                "Saudi East-West Pipeline flow reaches 3.5 million bpd",
                "Bloomberg", "b", now.isoformat(), now.timestamp(), "east_west_pipeline_recovery"
            ),
        ]
        result = MODULE.confirm_event(rows)
        self.assertIsNotNone(result)
        assert result is not None
        self.assertEqual(result[0], "east_west_pipeline_recovery")

    def test_yanbu_export_resume_is_classified_without_rate(self):
        title = "Saudi Arabia resumes oil exports via East-West Pipeline from Yanbu after repairs - Bloomberg"
        self.assertEqual(MODULE.classify_event(title), "east_west_pipeline_recovery")

    def test_pipeline_export_resume_is_new_stage(self):
        now = dt.datetime(2026, 9, 28, 12, 0, tzinfo=dt.timezone.utc)
        rate_only = [MODULE.NewsItem(
            "Saudi East-West Pipeline transport hits 3.5 million barrels per day",
            "Reuters", "a", now.isoformat(), now.timestamp(), "east_west_pipeline_recovery"
        )]
        export_resume = [MODULE.NewsItem(
            "Saudi Arabia resumes oil exports via East-West Pipeline from Yanbu after repairs",
            "Bloomberg", "b", (now + dt.timedelta(hours=1)).isoformat(),
            (now + dt.timedelta(hours=1)).timestamp(), "east_west_pipeline_recovery"
        )]
        self.assertNotEqual(
            MODULE.event_id("east_west_pipeline_recovery", rate_only),
            MODULE.event_id("east_west_pipeline_recovery", export_resume),
        )

    def test_pipeline_body_marks_yanbu_exports_resumed(self):
        current = dt.datetime(2026, 9, 28, 12, 0, tzinfo=dt.timezone.utc)
        news = [MODULE.NewsItem(
            "Saudi Arabia resumes oil exports via East-West Pipeline from Yanbu after repairs",
            "Bloomberg", "a", current.isoformat(), current.timestamp(), "east_west_pipeline_recovery"
        )]
        body = MODULE.build_physical_flow_alert_body("east_west_pipeline_recovery", news, None, current)
        self.assertIn("Yanbu 수출     재개 확인", body)
        self.assertIn("실제 수출로 연결되기 시작했습니다", body)

    def test_regional_export_recovery_is_classified(self):
        title = "Middle East crude exports reach 12.8 million bpd, highest since the war - Reuters"
        self.assertEqual(MODULE.classify_event(title), "regional_export_recovery")

    def test_india_gulf_import_recovery_is_classified(self):
        title = "Gulf crude imports to India recover to 1.52 mb/d in September - Kpler"
        self.assertEqual(MODULE.classify_event(title), "india_gulf_import_recovery")

    def test_regional_recovery_body_does_not_call_it_full_normalization(self):
        current = dt.datetime(2026, 9, 29, 4, 0, tzinfo=dt.timezone.utc)
        news = [MODULE.NewsItem(
            "Middle East crude exports reach 12.8 million bpd, highest since the war",
            "Reuters", "a", current.isoformat(), current.timestamp(), "regional_export_recovery"
        )]
        body = MODULE.build_physical_flow_alert_body("regional_export_recovery", news, None, current)
        self.assertIn("중동 수출     전쟁 후 최고 수준", body)
        self.assertIn("12.800 Mbd", body)
        self.assertIn("잠정 선박추적치는 확인이 붙으며 수정될 수 있음", body)
        self.assertIn("고정 숫자를 재사용하지 않고", body)

    def test_india_flow_body_uses_separate_baseline(self):
        current = dt.datetime(2026, 9, 29, 4, 0, tzinfo=dt.timezone.utc)
        news = [MODULE.NewsItem(
            "Gulf crude imports to India recover to 1.52 mb/d in September",
            "Kpler", "a", current.isoformat(), current.timestamp(), "india_gulf_import_recovery"
        )]
        body = MODULE.build_physical_flow_alert_body("india_gulf_import_recovery", news, None, current)
        self.assertIn("인도 유입     걸프산 1.52 Mbd", body)
        self.assertIn("2025 평균 2.24 Mbd", body)
        self.assertIn("완전 정상화는 아닙니다", body)

    def test_distinct_event_not_blocked_by_recent_other_event(self):
        current = dt.datetime(2026, 9, 29, 6, 0, tzinfo=dt.timezone.utc)
        old_rows = [MODULE.NewsItem(
            "Kpler Gulf of Oman STS record 7.2 Mbd as of 2026-09-26; since-war average 3.7 Mbd; 2025 average 0.16 Mbd",
            "Kpler", "a", current.isoformat(), current.timestamp(), "sts_reroute_expansion"
        )]
        new_rows = [MODULE.NewsItem(
            "Saudi East-West Pipeline transport hits 3.5 million barrels per day",
            "Reuters", "b", current.isoformat(), current.timestamp(), "east_west_pipeline_recovery"
        )]
        old_id = MODULE.event_id("sts_reroute_expansion", old_rows)
        state = {
            "last_alert_at_kst": current.astimezone(MODULE.KST).isoformat(),
            "last_event_id": old_id,
            "alerted_events": {old_id: current.astimezone(MODULE.KST).isoformat()},
        }
        selected, duplicates = MODULE.select_unalerted_event(
            state,
            [
                ("sts_reroute_expansion", old_rows),
                ("east_west_pipeline_recovery", new_rows),
            ],
            current,
        )
        self.assertIsNotNone(selected)
        assert selected is not None
        self.assertEqual(selected[0], "east_west_pipeline_recovery")
        self.assertIn("걸프오브오만 STS 우회 물류 급증·병목", duplicates)

    def test_same_event_is_suppressed_but_new_stage_passes(self):
        current = dt.datetime(2026, 9, 29, 6, 0, tzinfo=dt.timezone.utc)
        rate35 = [MODULE.NewsItem(
            "Saudi East-West Pipeline transport hits 3.5 million barrels per day",
            "Reuters", "a", current.isoformat(), current.timestamp(), "east_west_pipeline_recovery"
        )]
        rate40 = [MODULE.NewsItem(
            "Saudi East-West Pipeline transport hits 4.0 million barrels per day",
            "Reuters", "b", current.isoformat(), current.timestamp(), "east_west_pipeline_recovery"
        )]
        id35 = MODULE.event_id("east_west_pipeline_recovery", rate35)
        state = {"alerted_events": {id35: current.astimezone(MODULE.KST).isoformat()}}
        self.assertTrue(MODULE.event_recently_alerted(state, id35, current))
        selected, _ = MODULE.select_unalerted_event(
            state,
            [
                ("east_west_pipeline_recovery", rate35),
                ("east_west_pipeline_recovery", rate40),
            ],
            current,
        )
        self.assertIsNotNone(selected)
        assert selected is not None
        self.assertEqual(MODULE.event_id(selected[0], selected[1]), MODULE.event_id("east_west_pipeline_recovery", rate40))

    def test_regional_single_reuters_does_not_confirm(self):
        now = dt.datetime(2026, 9, 29, 6, 0, tzinfo=dt.timezone.utc)
        rows = [MODULE.NewsItem(
            "Middle East crude exports reach 12.8 million bpd, highest since the war",
            "Reuters", "a", now.isoformat(), now.timestamp(), "regional_export_recovery"
        )]
        self.assertIsNone(MODULE.confirm_event(rows))

    def test_regional_single_kpler_primary_can_confirm(self):
        now = dt.datetime(2026, 9, 29, 6, 0, tzinfo=dt.timezone.utc)
        rows = [MODULE.NewsItem(
            "Middle East crude exports reach 12.8 million bpd, highest since the war",
            "Kpler", "a", now.isoformat(), now.timestamp(), "regional_export_recovery"
        )]
        result = MODULE.confirm_event(rows)
        self.assertIsNotNone(result)
        assert result is not None
        self.assertEqual(result[0], "regional_export_recovery")

    def test_reuters_kpler_revised_snapshot_parser(self):
        current = dt.datetime(2026, 9, 29, 10, 0, tzinfo=dt.timezone.utc)
        html = """
        <html><body>
        Crude oil exports from key Middle East producers rebounded in September to
        16.328 million barrels per day (bpd), the highest since the war began.
        Exports via the Strait of Hormuz were set to hit about 9.719 million bpd this month.
        Regional exports were still about 3.2 million bpd down from 19.513 million bpd in February.
        Saudi Arabia was on track to ship about 5.4 million bpd this month.
        September shipments from Ras Tanura jumped to about 3.25 million bpd.
        </body></html>
        """
        item = MODULE.parse_mideast_export_snapshot(html, current, "https://example.com/reuters")
        self.assertEqual(item.event_kind, "regional_export_recovery")
        self.assertIn("16.328 Mbd", item.title)
        self.assertIn("9.719 Mbd", item.title)
        self.assertIn("19.513 Mbd", item.title)
        self.assertIn("83.7%", item.title)

    def test_regional_body_uses_revised_snapshot_not_hardcoded_old_value(self):
        current = dt.datetime(2026, 9, 29, 10, 0, tzinfo=dt.timezone.utc)
        news = [MODULE.NewsItem(
            "Middle East crude exports snapshot 16.328 Mbd; Hormuz 9.719 Mbd; February 19.513 Mbd; gap 3.185 Mbd; recovery 83.7%; Saudi 5.400 Mbd; RasTanura 3.250 Mbd; preliminary Kpler data may revise",
            "Reuters/Kpler",
            "https://example.com/reuters",
            current.isoformat(),
            current.timestamp(),
            "regional_export_recovery",
        )]
        body = MODULE.build_physical_flow_alert_body("regional_export_recovery", news, None, current)
        self.assertIn("16.328 Mbd", body)
        self.assertIn("9.719 Mbd", body)
        self.assertIn("19.513 Mbd", body)
        self.assertIn("83.7%", body)
        self.assertNotIn("12.8 Mbd", body)
        self.assertNotIn("18.8 Mbd", body)

    def test_regional_revision_creates_new_stage(self):
        current = dt.datetime(2026, 9, 29, 10, 0, tzinfo=dt.timezone.utc)
        old = [MODULE.NewsItem(
            "Middle East crude exports snapshot 12.800 Mbd; Hormuz 7.400 Mbd; February 18.800 Mbd; gap 6.000 Mbd; recovery 68.1%; preliminary Kpler data may revise",
            "Reuters/Kpler", "a", current.isoformat(), current.timestamp(), "regional_export_recovery"
        )]
        revised = [MODULE.NewsItem(
            "Middle East crude exports snapshot 16.328 Mbd; Hormuz 9.719 Mbd; February 19.513 Mbd; gap 3.185 Mbd; recovery 83.7%; preliminary Kpler data may revise",
            "Reuters/Kpler", "b", current.isoformat(), current.timestamp(), "regional_export_recovery"
        )]
        self.assertNotEqual(
            MODULE.event_id("regional_export_recovery", old),
            MODULE.event_id("regional_export_recovery", revised),
        )

    def test_usdkrw_format_marks_won_direction(self):
        now = dt.datetime(2026, 9, 29, 10, 0, tzinfo=dt.timezone.utc).timestamp()
        fx = MODULE.Quote("KRW=X", "원·달러", "원/달러", 1360.0, 1340.0, 20.0, 1.4925, "", now)
        text = MODULE.fmt_quote_line(fx)
        self.assertIn("1,360.00원", text)
        self.assertIn("원화 약세", text)

    def test_korea_transmission_block_oil_down_won_weak(self):
        current = dt.datetime(2026, 9, 29, 10, 0, tzinfo=dt.timezone.utc)
        news = [MODULE.NewsItem(
            "Middle East crude exports snapshot 16.328 Mbd; Hormuz 9.719 Mbd; February 19.513 Mbd; gap 3.185 Mbd; recovery 83.7%; preliminary Kpler data may revise",
            "Reuters/Kpler", "https://example.com/reuters",
            current.isoformat(), current.timestamp(), "regional_export_recovery"
        )]
        oil = MODULE.Quote("BZ=F", "Brent", "달러/배럴", 100.0, 103.0, -3.0, -2.91, "", current.timestamp())
        fx = MODULE.Quote("KRW=X", "원·달러", "원/달러", 1360.0, 1340.0, 20.0, 1.49, "", current.timestamp())
        body = MODULE.build_physical_flow_alert_body("regional_export_recovery", news, oil, current, fx)
        self.assertIn("[한국 전이]", body)
        self.assertIn("유가 ↓ 하지만 원화 약세", body)
        self.assertIn("실적 시즌", body)
        self.assertIn("원가 민감", body)
        self.assertIn("금리 경로", body)

    def test_alert_body_contains_required_market_values(self):
        current = dt.datetime(2026, 8, 2, 12, 0, tzinfo=dt.timezone.utc)
        news = [
            MODULE.NewsItem("US and Iran agree to ceasefire agreement", "Reuters", "a", current.isoformat(), current.timestamp(), "ceasefire"),
            MODULE.NewsItem("Iran ceasefire agreement takes effect", "Associated Press", "b", current.isoformat(), current.timestamp(), "ceasefire"),
        ]
        us2y = MODULE.Quote("^UST2Y", "미국 2년물 국채금리", "%", 4.20, 4.25, -0.05, -1.176, "", current.timestamp())
        dxy = MODULE.Quote("DX-Y.NYB", "달러인덱스", "", 99.50, 100.00, -0.50, -0.50, "", current.timestamp())
        oil = MODULE.Quote("CL=F", "WTI", "달러/배럴", 80.00, 85.00, -5.00, -5.882, "", current.timestamp())
        body = MODULE.build_alert_body("ceasefire", news, us2y, dxy, oil, current)
        self.assertIn("미국 2년물 국채금리: 4.200%", body)
        self.assertIn("달러인덱스: 99.50", body)
        self.assertIn("WTI: $80.00/배럴", body)
        self.assertIn("실패 경로", body)


if __name__ == "__main__":
    unittest.main()
