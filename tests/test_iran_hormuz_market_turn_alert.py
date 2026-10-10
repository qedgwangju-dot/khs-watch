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

    def test_generic_oil_flow_alert_is_compact(self):
        current = dt.datetime(2026, 10, 1, 15, 40, tzinfo=dt.timezone.utc)
        news = [
            MODULE.NewsItem(
                "Oil prices settle down on signs Middle East exports recovering",
                "Reuters",
                "https://example.com/reuters",
                current.isoformat(),
                current.timestamp(),
                "oil_flow_recovery",
            ),
            MODULE.NewsItem(
                "Oil prices settle down on signs Middle East exports recovering",
                "BNN Bloomberg",
                "https://example.com/bnn",
                current.isoformat(),
                current.timestamp(),
                "oil_flow_recovery",
            ),
        ]
        oil = MODULE.Quote("BZ=F", "Brent", "달러/배럴", 101.81, 98.03, 3.78, 3.86, "", current.timestamp())
        fx = MODULE.Quote("KRW=X", "원·달러", "원/달러", 1364.24, 1356.54, 7.70, 0.57, "", current.timestamp())
        body = MODULE.build_physical_flow_alert_body("oil_flow_recovery", news, oil, current, fx)
        self.assertIn("[한눈에]", body)
        self.assertIn("실물          중동 원유 수출 회복", body)
        self.assertIn("시장          Brent USD 101.81", body)
        self.assertIn("[핵심]", body)
        self.assertIn("유가 ↑ + 원화 약세", body)
        self.assertIn("[다음 확인]", body)
        self.assertIn("원문: https://example.com/reuters", body)
        self.assertLessEqual(len(body.splitlines()), 25)
        self.assertNotIn("[병목]", body)
        self.assertNotIn("[다음 체크]", body)

    def test_rss_older_than_24h_is_rejected(self):
        current = dt.datetime(2026, 10, 1, 15, 40, tzinfo=dt.timezone.utc)
        old = current - dt.timedelta(hours=38)
        rss = f"""<?xml version="1.0"?>
        <rss><channel><item>
          <title>Oil prices settle down on signs Middle East exports recovering - Reuters</title>
          <link>https://example.com/old</link>
          <source>Reuters</source>
          <pubDate>{old.strftime('%a, %d %b %Y %H:%M:%S GMT')}</pubDate>
        </item></channel></rss>""".encode()
        rows = MODULE.parse_rss(rss, current, 24)
        self.assertEqual(rows, [])

    def test_saudi_osp_reuters_parser(self):
        now = dt.datetime(2026, 10, 5, 11, 0, tzinfo=dt.timezone.utc)
        html = """
        <html><body>
        Saudi Arabia unexpectedly cut November crude oil prices for Asia.
        The November Arab Light crude oil official selling price to Asia was set at $5 a barrel
        below the average of Oman and Dubai prices, down $3 from the previous month.
        State oil company Saudi Aramco made deeper cuts of $5 a barrel for the November OSPs
        of heavier grades - Arab Medium and Arab Heavy - sold to Asia.
        NOVEMBER OCTOBER CHANGE
        SUPER LIGHT -3.35 -0.35 -3.00
        EXTRA LIGHT -4.50 -1.50 -3.00
        LIGHT -5.00 -2.00 -3.00
        MEDIUM -6.00 -1.00 -5.00
        HEAVY -7.35 -2.35 -5.00
        Saudi Aramco raised the November OSPs for northwest Europe by $3 a barrel.
        Aramco kept prices unchanged for buyers in the United States.
        The discount is the widest since June 2020.
        </body></html>
        """
        item = MODULE.parse_saudi_osp_snapshot(html, now, "https://example.com", "Reuters via BOE Report")
        self.assertEqual(item.event_kind, "saudi_asia_osp_change")
        self.assertIn("Arab Light -5.00 MoM -3.00", item.title)
        self.assertIn("Arab Medium -6.00 MoM -5.00", item.title)
        self.assertIn("Arab Heavy -7.35 MoM -5.00", item.title)
        self.assertIn("NW Europe MoM +3.00", item.title)
        self.assertIn("US unchanged", item.title)

    def test_saudi_osp_cross_check_requires_two_sources(self):
        now = dt.datetime(2026, 10, 5, 11, 0, tzinfo=dt.timezone.utc)
        one = [MODULE.NewsItem(
            "Saudi OSP November Asia: Super Light -3.35; Extra Light -4.50; Arab Light -5.00 MoM -3.00; Arab Medium -6.00 MoM -5.00; Arab Heavy -7.35 MoM -5.00; NW Europe MoM +3.00; US unchanged; widest Asia Light discount since June 2020",
            "Reuters via BOE Report", "a", now.isoformat(), now.timestamp(), "saudi_asia_osp_change"
        )]
        self.assertIsNone(MODULE.confirm_event(one))
        one.append(MODULE.NewsItem(
            "Saudi OSP November Asia: Super Light -3.35; Extra Light -4.50; Arab Light -5.00; Arab Medium -6.00; Arab Heavy -7.35",
            "Saudi Aramco via Argaam", "b", now.isoformat(), now.timestamp(), "saudi_asia_osp_change"
        ))
        result = MODULE.confirm_event(one)
        self.assertIsNotNone(result)
        assert result is not None
        self.assertEqual(result[0], "saudi_asia_osp_change")

    def test_saudi_osp_alert_is_compact_and_precise(self):
        now = dt.datetime(2026, 10, 5, 11, 0, tzinfo=dt.timezone.utc)
        rows = [
            MODULE.NewsItem(
                "Saudi OSP November Asia: Super Light -3.35; Extra Light -4.50; Arab Light -5.00 MoM -3.00; Arab Medium -6.00 MoM -5.00; Arab Heavy -7.35 MoM -5.00; NW Europe MoM +3.00; US unchanged; widest Asia Light discount since June 2020",
                "Reuters via BOE Report", "https://example.com/reuters", now.isoformat(), now.timestamp(), "saudi_asia_osp_change"
            ),
            MODULE.NewsItem(
                "Saudi OSP November Asia: Super Light -3.35; Extra Light -4.50; Arab Light -5.00; Arab Medium -6.00; Arab Heavy -7.35",
                "Saudi Aramco via Argaam", "https://example.com/argaam", now.isoformat(), now.timestamp(), "saudi_asia_osp_change"
            ),
        ]
        fx = MODULE.Quote("KRW=X", "원·달러", "원/달러", 1350.0, 1360.0, -10.0, -0.735, "", now.timestamp())
        body = MODULE.build_physical_flow_alert_body("saudi_asia_osp_change", rows, None, now, fx)
        self.assertIn("Oman/Dubai 평균 대비 -5.00달러/배럴", body)
        self.assertIn("전월 대비 -3.00달러", body)
        self.assertIn("Arab Medium -6.00", body)
        self.assertIn("Arab Heavy -7.35", body)
        self.assertIn("서북유럽 전월 대비 +3달러 · 미국 동결", body)
        self.assertIn("약 6,750원/배럴", body)
        self.assertIn("절대가격이 아니라 Oman/Dubai 기준 대비 공식판매가격 차등", body)
        self.assertIn("배럴당 5달러에 판매한다는 뜻이 아닙니다", body)
        self.assertLessEqual(len(body.splitlines()), 34)

    def test_saudi_osp_next_month_creates_new_event(self):
        now = dt.datetime(2026, 10, 5, 11, 0, tzinfo=dt.timezone.utc)
        nov = [MODULE.NewsItem(
            "Saudi OSP November Asia: Arab Light -5.00 MoM -3.00; Arab Medium -6.00; Arab Heavy -7.35",
            "Reuters", "a", now.isoformat(), now.timestamp(), "saudi_asia_osp_change"
        )]
        dec = [MODULE.NewsItem(
            "Saudi OSP December Asia: Arab Light -4.00 MoM +1.00; Arab Medium -5.00; Arab Heavy -6.35",
            "Reuters", "b", now.isoformat(), now.timestamp(), "saudi_asia_osp_change"
        )]
        self.assertNotEqual(
            MODULE.event_id("saudi_asia_osp_change", nov),
            MODULE.event_id("saudi_asia_osp_change", dec),
        )

    @staticmethod
    def _eia_weekly_fixture():
        return """<html><body>
        Spot Prices (Crude Oil in Dollars per Barrel, Products in Dollars per Gallon)
        Product by Area 08/28/26 09/04/26 09/11/26 09/18/26 09/25/26 10/02/26
        Crude Oil
        WTI - Cushing, Oklahoma 84.62 91.18 99.08 103.54 93.57 98.07
        Brent - Europe 89.73 99.09 111.83 124.15 117.08 120.03
        Conventional Gasoline
        New York Harbor, Regular 3.370 3.266 3.361 3.542 3.580 3.433
        U.S. Gulf Coast, Regular 3.564 3.494 3.629 3.888 3.945 3.672
        RBOB Regular Gasoline
        Los Angeles 3.854 3.860 3.941 4.123 4.294 4.438
        No. 2 Heating Oil
        New York Harbor 4.163 4.508 4.802 5.025 4.745 4.661
        Ultra-Low-Sulfur No. 2 Diesel Fuel
        New York Harbor 4.262 4.604 4.928 5.223 4.955 4.871
        U.S. Gulf Coast 4.274 4.612 4.882 5.128 4.870 4.731
        Kerosene-Type Jet Fuel
        U.S. Gulf Coast 3.715 4.082 4.418 4.584 4.351 4.416
        </body></html>"""

    def test_eia_weekly_refining_crack_official_table_and_units(self):
        now = dt.datetime(2026, 10, 8, 5, 0, tzinfo=dt.timezone.utc)
        row = MODULE.parse_eia_weekly_refining_snapshot(self._eia_weekly_fixture(), now)
        self.assertEqual(row.event_kind, "eia_refining_crack_watch")
        self.assertEqual(row.link, MODULE.EIA_REFINING_WEEKLY_URL)
        self.assertEqual(row.source, MODULE.EIA_REFINING_SOURCE)
        m = MODULE._extract_eia_refining_metrics([row])
        self.assertIsNotNone(m)
        self.assertEqual(m["week"], "2026-10-02")
        self.assertAlmostEqual(float(m["latest"]), 66.25, places=2)
        self.assertAlmostEqual(float(m["previous"]), 76.04, places=2)
        self.assertAlmostEqual(float(m["move"]), -9.79, places=2)
        self.assertAlmostEqual(float(m["gas"]), 3.433, places=3)
        self.assertAlmostEqual(float(m["diesel"]), 4.871, places=3)

    def test_eia_refining_alert_keeps_bloomberg_separate_and_krw(self):
        now = dt.datetime(2026, 10, 8, 5, 0, tzinfo=dt.timezone.utc)
        row = MODULE.parse_eia_weekly_refining_snapshot(self._eia_weekly_fixture(), now)
        fx = MODULE.Quote("KRW=X", "원·달러", "원/달러", 1350.0, 1355.0, -5, -0.37, "", now.timestamp())
        body = MODULE.build_physical_flow_alert_body("eia_refining_crack_watch", [row], None, now, fx)
        self.assertIn("66.25달러/배럴", body)
        self.assertIn("-9.79달러 축소", body)
        self.assertIn("Bloomberg 선물 3-2-1·Shell 회사별 정제마진과 다른 지표", body)
        self.assertIn("원화 환산", body)
        self.assertIn("52주 신고가", body)
        self.assertIn("원문: https://www.eia.gov", body)
        self.assertLessEqual(len(body.splitlines()), 29)

    def test_eia_refining_official_one_source_confirms_and_dedupes(self):
        now = dt.datetime(2026, 10, 8, 5, 0, tzinfo=dt.timezone.utc)
        row = MODULE.parse_eia_weekly_refining_snapshot(self._eia_weekly_fixture(), now)
        self.assertIsNotNone(MODULE.confirm_event([row]))
        first = MODULE.event_id("eia_refining_crack_watch", [row])
        reprint = MODULE.NewsItem(row.title, row.source, row.link, row.published_utc, row.published_epoch + 7200, row.event_kind)
        self.assertEqual(first, MODULE.event_id("eia_refining_crack_watch", [reprint]))
        state = {"alerted_events": {first: now.astimezone(MODULE.KST).isoformat()}}
        self.assertIsNone(MODULE.select_unalerted_event(state, [("eia_refining_crack_watch", [row])], now)[0])

    def test_eia_refining_rejects_stale_and_missing_rows(self):
        now = dt.datetime(2026, 10, 28, 5, 0, tzinfo=dt.timezone.utc)
        with self.assertRaisesRegex(RuntimeError, "오래된"):
            MODULE.parse_eia_weekly_refining_snapshot(self._eia_weekly_fixture(), now)
        with self.assertRaisesRegex(RuntimeError, "개수 불일치"):
            MODULE.parse_eia_weekly_refining_snapshot(self._eia_weekly_fixture().replace("3.433", ""), dt.datetime(2026, 10, 8, 5, tzinfo=dt.timezone.utc))

    def test_eia_refining_rejects_unrealistic_units_and_small_change(self):
        now = dt.datetime(2026, 10, 8, 5, 0, tzinfo=dt.timezone.utc)
        with self.assertRaisesRegex(ValueError, "가격 범위"):
            MODULE.parse_eia_weekly_refining_snapshot(self._eia_weekly_fixture().replace("98.07", "999.07"), now)
        with self.assertRaisesRegex(RuntimeError, "기준 미충족"):
            MODULE.parse_eia_weekly_refining_snapshot(self._eia_weekly_fixture().replace("4.871", "5.550"), now)

    def test_eia_refining_wrong_source_cannot_claim_official(self):
        now = dt.datetime(2026, 10, 8, 5, 0, tzinfo=dt.timezone.utc)
        row = MODULE.parse_eia_weekly_refining_snapshot(self._eia_weekly_fixture(), now)
        forged = MODULE.NewsItem(row.title, "blog", "https://example.com", row.published_utc, row.published_epoch, row.event_kind)
        self.assertIsNone(MODULE._extract_eia_refining_metrics([forged]))
        self.assertIsNone(MODULE.confirm_event([forged]))

    def test_kpler_prewar_export_parser(self):
        now = dt.datetime(2026, 10, 3, 12, 0, tzinfo=dt.timezone.utc)
        html = """
        <html><body>
        At least 16.5 mbd left the region between 1 and 28 September, matching the pre-war average excluding Iran.
        40% of the region's crude now leaves without crossing Hormuz, against 17% before the war.
        In September, 60% physically crossed Hormuz, 9.9 mbd, mostly using shuttle tankers.
        In August, more than 70% of the crude crossing the strait changed tankers off Fujairah or Sohar.
        </body></html>
        """
        item = MODULE.parse_kpler_prewar_export_snapshot(html, now)
        self.assertEqual(item.event_kind, "ex_iran_crude_prewar_recovery")
        self.assertIn("16.5 Mbd", item.title)
        self.assertIn("Hormuz 9.9 Mbd 60%", item.title)
        self.assertIn("bypass 40% vs pre-war 17%", item.title)
        self.assertIn("STS over 70%", item.title)

    def test_ex_iran_prewar_body_calculates_route_substitution(self):
        now = dt.datetime(2026, 10, 3, 12, 0, tzinfo=dt.timezone.utc)
        rows = [MODULE.NewsItem(
            "Kpler Gulf crude excluding Iran 16.5 Mbd, 100% pre-war average; Hormuz 9.9 Mbd 60%; bypass 40% vs pre-war 17%; STS over 70%",
            "Kpler", "https://example.com/kpler", now.isoformat(), now.timestamp(), "ex_iran_crude_prewar_recovery"
        )]
        body = MODULE.build_physical_flow_alert_body("ex_iran_crude_prewar_recovery", rows, None, now)
        self.assertIn("이란 제외 원유  16.5 Mbd · 전쟁 전 평균의 100%", body)
        self.assertIn("호르무즈      9.9 Mbd · 전체의 60%", body)
        self.assertIn("우회          40% · 전쟁 전 17%", body)
        self.assertIn("호르무즈 약 3.8 Mbd 감소", body)
        self.assertIn("우회 약 3.8 Mbd 증가", body)
        self.assertIn("60% → 70% → 전쟁 전 83%", body)
        self.assertIn("Reuters의 2월 단일월 19.513 Mbd 비교와 분모가 다릅니다", body)

    def test_ex_iran_prewar_event_id_changes_when_route_normalizes(self):
        now = dt.datetime(2026, 10, 3, 12, 0, tzinfo=dt.timezone.utc)
        a = [MODULE.NewsItem(
            "Kpler Gulf crude excluding Iran 16.5 Mbd, 100% pre-war average; Hormuz 9.9 Mbd 60%; bypass 40% vs pre-war 17%; STS over 70%",
            "Kpler", "a", now.isoformat(), now.timestamp(), "ex_iran_crude_prewar_recovery"
        )]
        b = [MODULE.NewsItem(
            "Kpler Gulf crude excluding Iran 16.5 Mbd, 100% pre-war average; Hormuz 12.0 Mbd 73%; bypass 27% vs pre-war 17%; STS over 40%",
            "Kpler", "b", now.isoformat(), now.timestamp(), "ex_iran_crude_prewar_recovery"
        )]
        self.assertNotEqual(
            MODULE.event_id("ex_iran_crude_prewar_recovery", a),
            MODULE.event_id("ex_iran_crude_prewar_recovery", b),
        )

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
        self.assertLessEqual(len(body.splitlines()), 36)
        self.assertIn("시장          Brent USD 100.55", body)
        self.assertIn("실물          호르무즈 통과량", body)
        self.assertIn("원문: https://example.com/kpler", body)

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

    def test_jpmorgan_98pct_headline_is_classified(self):
        title = 'JPMorgan says Middle East crude flows hit 98% of pre-war level'
        self.assertEqual(MODULE.classify_event(title), "crude_product_divergence")

    def test_korean_jpmorgan_98pct_headline_is_classified(self):
        title = 'JP모건 "중동 원유 수출량, 이란戰 발발 이전 98% 복구"'
        self.assertEqual(MODULE.classify_event(title), "crude_product_divergence")

    def test_crude_product_gap_event_id_moves_on_product_recovery_band(self):
        now = dt.datetime(2026, 9, 30, 12, 0, tzinfo=dt.timezone.utc)
        a = [MODULE.NewsItem("JPMorgan Middle East crude/product snapshot crude 17.5 Mbd 98% pre-war; products 3.0 Mbd 58% pre-war; overall 89% of 2025; Hormuz 13.0 Mbd","JPMorgan via Bloomberg","a",now.isoformat(),now.timestamp(),"crude_product_divergence")]
        b = [MODULE.NewsItem("JPMorgan Middle East crude/product snapshot crude 17.6 Mbd 99% pre-war; products 3.4 Mbd 66% pre-war; overall 92% of 2025; Hormuz 13.1 Mbd","JPMorgan via Bloomberg","b",now.isoformat(),now.timestamp(),"crude_product_divergence")]
        self.assertNotEqual(MODULE.event_id("crude_product_divergence", a), MODULE.event_id("crude_product_divergence", b))

    def test_crude_product_gap_body_keeps_crude_and_products_separate(self):
        now = dt.datetime(2026, 9, 30, 12, 0, tzinfo=dt.timezone.utc)
        rows = [MODULE.NewsItem("JPMorgan Middle East crude/product snapshot crude 17.5 Mbd 98% pre-war; products 3.0 Mbd 58% pre-war; overall 89% of 2025; Hormuz 13.0 Mbd","JPMorgan via Bloomberg","https://example.com/jpm",now.isoformat(),now.timestamp(),"crude_product_divergence")]
        body = MODULE.build_physical_flow_alert_body("crude_product_divergence", rows, None, now)
        self.assertIn("원유          17.5 Mbd · 전쟁 전의 98%", body)
        self.assertIn("정제품        3.0 Mbd · 전쟁 전의 58%", body)
        self.assertIn("회복 격차     40%p", body)
        self.assertIn("원유 정상화 ≠ 연료시장 정상화", body)
        self.assertIn("정제품        58% → 70% → 85% → 95%", body)

    def test_us_diesel_policy_classification_and_stage_ids(self):
        now = dt.datetime(2026, 9, 30, 12, 0, tzinfo=dt.timezone.utc)
        denied = MODULE.NewsItem("White House denies report US is considering a diesel export ban","Reuters","a",now.isoformat(),now.timestamp(),"us_diesel_export_policy")
        considering = MODULE.NewsItem("Trump says he is still considering diesel export ban","Reuters","b",now.isoformat(),now.timestamp(),"us_diesel_export_policy")
        self.assertEqual(MODULE.classify_event(denied.title), "us_diesel_export_policy")
        self.assertEqual(MODULE.classify_event(considering.title), "us_diesel_export_policy")
        self.assertNotEqual(MODULE.event_id("us_diesel_export_policy", [denied]), MODULE.event_id("us_diesel_export_policy", [considering]))

    def test_english_news_headlines_are_rendered_in_korean(self):
        now = dt.datetime(2026, 10, 2, 6, 13, tzinfo=dt.timezone.utc)
        rows = [
            MODULE.NewsItem(
                "VIEW Chinese refiners suspend October fuel exports, sources say - Reuters",
                "Reuters",
                "https://example.com/reuters",
                now.isoformat(),
                now.timestamp(),
                "china_fuel_export_policy",
            ),
            MODULE.NewsItem(
                "Chinese refiners suspend October fuel exports, says report: Which other countries plan curbs amid Iran, Ukraine war",
                "Livemint",
                "https://example.com/livemint",
                now.isoformat(),
                now.timestamp(),
                "china_fuel_export_policy",
            ),
        ]
        body = MODULE.build_physical_flow_alert_body("china_fuel_export_policy", rows, None, now)
        self.assertIn("로이터 ·", body)
        self.assertIn("라이브민트 ·", body)
        self.assertIn("중국 정유사, 10월 정제품 수출 중단", body)
        self.assertNotIn("Chinese refiners suspend", body)
        self.assertNotIn("Which other countries", body)

    def test_us_diesel_english_headline_is_rendered_in_korean(self):
        now = dt.datetime(2026, 10, 2, 6, 13, tzinfo=dt.timezone.utc)
        row = MODULE.NewsItem(
            "Trump says he is still considering diesel export ban",
            "Reuters",
            "https://example.com/reuters",
            now.isoformat(),
            now.timestamp(),
            "us_diesel_export_policy",
        )
        self.assertEqual(MODULE._news_title_ko(row), "백악관, 미국 디젤 수출금지 여부 검토")

    def test_euronews_direct_reserve_parser(self):
        now = dt.datetime(2026, 10, 2, 12, 0, tzinfo=dt.timezone.utc)
        html = """
        <html><body>
        EU Energy Commissioner Dan Jorgensen said releasing strategic reserves is a possibility
        as the diesel squeeze bites. Member states are discussing a coordinated release.
        </body></html>
        """
        item = MODULE.parse_eu_diesel_reserve_snapshot(html, now)
        self.assertEqual(item.event_kind, "eu_diesel_reserve_policy")
        self.assertEqual(item.source, "Euronews")
        self.assertIn("strategic diesel reserves", item.title)

    def test_g7_100m_agreement_is_classified(self):
        title = "G7 agrees to release 100mn barrels of diesel and crude under pressure from Trump"
        self.assertEqual(MODULE.classify_event(title), "g7_reserve_release_agreement")

    def test_europe_immediate_diesel_agreement_is_classified(self):
        title = "Trump: Europe agrees to release diesel reserves immediately as fuel prices hover near record highs"
        self.assertEqual(MODULE.classify_event(title), "g7_reserve_release_agreement")

    def test_g7_event_requires_two_unique_sources(self):
        now = dt.datetime(2026, 10, 2, 14, 0, tzinfo=dt.timezone.utc)
        one = [MODULE.NewsItem(
            "G7 agrees to release 100mn barrels of diesel and crude under pressure from Trump",
            "Financial Times", "a", now.isoformat(), now.timestamp(), "g7_reserve_release_agreement"
        )]
        self.assertIsNone(MODULE.confirm_event(one))
        one.append(MODULE.NewsItem(
            "Trump: Europe agrees to release diesel reserves immediately as fuel prices hover near record highs",
            "Associated Press", "b", now.isoformat(), now.timestamp(), "g7_reserve_release_agreement"
        ))
        result = MODULE.confirm_event(one)
        self.assertIsNotNone(result)
        assert result is not None
        self.assertEqual(result[0], "g7_reserve_release_agreement")

    def test_g7_agreement_body_preserves_split_and_caution(self):
        now = dt.datetime(2026, 10, 2, 14, 0, tzinfo=dt.timezone.utc)
        rows = [
            MODULE.NewsItem(
                "G7 agrees to release 100mn barrels of diesel and crude under pressure from Trump",
                "Financial Times", "a", now.isoformat(), now.timestamp(), "g7_reserve_release_agreement"
            ),
            MODULE.NewsItem(
                "Trump: Europe agrees to release diesel reserves immediately as fuel prices hover near record highs",
                "Associated Press", "b", now.isoformat(), now.timestamp(), "g7_reserve_release_agreement"
            ),
        ]
        body = MODULE.build_physical_flow_alert_body("g7_reserve_release_agreement", rows, None, now)
        self.assertIn("1억 배럴", body)
        self.assertIn("경유 5,000만 배럴 + IEA 원유 5,000만 배럴", body)
        self.assertIn("1억 배럴 전체가 경유라는 뜻은 아닙니다", body)
        self.assertIn("공개 G7·IEA 공식문서", body)
        self.assertIn("파이낸셜타임스", body)
        self.assertIn("AP", body)

    def test_eu_diesel_reserve_considering_is_classified(self):
        title = 'EU energy chief says releasing strategic diesel reserves is a possibility'
        self.assertEqual(MODULE.classify_event(title), "eu_diesel_reserve_policy")

    def test_eu_diesel_reserve_stage_changes_create_new_event(self):
        now = dt.datetime(2026, 10, 2, 12, 0, tzinfo=dt.timezone.utc)
        considering = [MODULE.NewsItem(
            "EU energy chief considers release of strategic diesel reserves",
            "Euronews", "a", now.isoformat(), now.timestamp(), "eu_diesel_reserve_policy"
        )]
        approved = [MODULE.NewsItem(
            "EU members approved strategic diesel reserve release",
            "Reuters", "b", now.isoformat(), now.timestamp(), "eu_diesel_reserve_policy"
        )]
        self.assertNotEqual(
            MODULE.event_id("eu_diesel_reserve_policy", considering),
            MODULE.event_id("eu_diesel_reserve_policy", approved),
        )

    def test_eu_diesel_reserve_body_is_compact(self):
        now = dt.datetime(2026, 10, 2, 12, 0, tzinfo=dt.timezone.utc)
        rows = [MODULE.NewsItem(
            "EU energy chief says releasing strategic diesel reserves is a possibility",
            "Euronews", "https://example.com/eu", now.isoformat(), now.timestamp(), "eu_diesel_reserve_policy"
        )]
        body = MODULE.build_physical_flow_alert_body("eu_diesel_reserve_policy", rows, None, now)
        self.assertIn("EU 정책", body)
        self.assertIn("전략비축", body)
        self.assertIn("5,000만 배럴", body)
        self.assertLessEqual(len(body.splitlines()), 30)

    def test_east_west_80pct_is_new_material_stage(self):
        now = dt.datetime(2026, 10, 2, 12, 0, tzinfo=dt.timezone.utc)
        old = [MODULE.NewsItem(
            "Saudi East-West Pipeline transport hits 4.0 million barrels per day",
            "Reuters", "a", now.isoformat(), now.timestamp(), "east_west_pipeline_recovery"
        )]
        new = [MODULE.NewsItem(
            "Saudi Arabia Hikes Oil Flow on Key Pipeline to Over 80% Capacity",
            "Bloomberg", "b", now.isoformat(), now.timestamp(), "east_west_pipeline_recovery"
        )]
        self.assertEqual(MODULE.classify_event(new[0].title), "east_west_pipeline_recovery")
        self.assertNotEqual(
            MODULE.event_id("east_west_pipeline_recovery", old),
            MODULE.event_id("east_west_pipeline_recovery", new),
        )

    def test_east_west_80pct_body_calculates_lower_bound(self):
        now = dt.datetime(2026, 10, 2, 12, 0, tzinfo=dt.timezone.utc)
        rows = [MODULE.NewsItem(
            "Saudi Arabia Hikes Oil Flow on Key Pipeline to Over 80% Capacity",
            "Bloomberg", "https://example.com/bloomberg", now.isoformat(), now.timestamp(), "east_west_pipeline_recovery"
        )]
        body = MODULE.build_physical_flow_alert_body("east_west_pipeline_recovery", rows, None, now)
        self.assertIn("80% 이상", body)
        self.assertIn("최소 5.6 Mbd", body)
        self.assertIn("80% → 90% → 95%", body)

    def test_china_resume_planned_vs_actual_shipment(self):
        title="China to resume October fuel exports after brief halt, four trade sources say"
        self.assertEqual(MODULE.classify_event(title),"china_fuel_export_policy")
        self.assertEqual(MODULE._china_fuel_export_stage(title),"planned_resume")
        self.assertEqual(MODULE._china_fuel_export_stage("China fuel cargoes departed from port"),"physical_resumed")
        self.assertEqual(MODULE._china_fuel_export_stage("China resumed exports of refined fuel"),"resumption_reported")
        self.assertEqual(MODULE._china_fuel_export_stage("China suspended fuel exports"),"suspended")

    def test_china_planned_resume_key_stable_after_source_volume_omitted(self):
        now=dt.datetime(2026,10,9,13,tzinfo=dt.timezone.utc)
        row_with=MODULE.NewsItem(
          "China to resume October fuel exports, four trade sources say; approved 3.7 million metric tons",
          "Reuters",MODULE.CHINA_REUTERS_20261009_URL,now.isoformat(),now.timestamp(),"china_fuel_export_policy")
        row_without=MODULE.NewsItem(
          "China to resume October fuel exports, four trade sources say",
          "Reuters",MODULE.CHINA_REUTERS_20261009_URL,now.isoformat(),now.timestamp(),"china_fuel_export_policy")
        a=MODULE.event_id("china_fuel_export_policy",[row_with])
        b=MODULE.event_id("china_fuel_export_policy",[row_without])
        self.assertEqual(a,b)
        old_basis="china_fuel_export_policy|2026-10|planned_resume|quantity_3.7"
        import hashlib
        legacy_id="china_fuel_export_policy:"+hashlib.sha256(old_basis.encode("utf-8")).hexdigest()[:16]
        state={"alerted_events":{legacy_id:now.astimezone(MODULE.KST).isoformat()}}
        self.assertTrue(MODULE.event_recently_alerted(state,a,now))

    def test_china_future_month_is_new_event_without_reusing_october_baseline(self):
        now=dt.datetime(2026,11,5,12,tzinfo=dt.timezone.utc)
        oct_row=MODULE.NewsItem(
            "China to resume October fuel exports, four trade sources say",
            "Reuters","a",now.isoformat(),now.timestamp(),"china_fuel_export_policy")
        nov_row=MODULE.NewsItem(
            "China to resume November fuel exports, four trade sources say",
            "Reuters","b",now.isoformat(),now.timestamp(),"china_fuel_export_policy")
        self.assertEqual(MODULE._china_policy_period([oct_row]),"2026-10")
        self.assertEqual(MODULE._china_policy_period([nov_row]),"2026-11")
        self.assertNotEqual(
            MODULE.event_id("china_fuel_export_policy",[oct_row]),
            MODULE.event_id("china_fuel_export_policy",[nov_row])
        )
        body=MODULE.build_physical_flow_alert_body("china_fuel_export_policy",[nov_row],None,now)
        self.assertNotIn("10월 7일 연휴 종료",body)

    def test_china_new_reopening_does_not_combine_old_suspension(self):
        now=dt.datetime(2026,10,9,13,tzinfo=dt.timezone.utc)
        rows=[
          MODULE.NewsItem("Chinese refiners suspend October fuel exports","Reuters","a",now.isoformat(),now.timestamp()-3600,"china_fuel_export_policy"),
          MODULE.NewsItem("China to resume October fuel exports, four trade sources say","Reuters",
            MODULE.CHINA_REUTERS_20261009_URL,now.isoformat(),now.timestamp(),"china_fuel_export_policy")
        ]
        events=MODULE.confirm_events(rows)
        self.assertTrue(events)
        self.assertEqual(MODULE._china_fuel_export_stage(events[0][1]),"planned_resume")
        self.assertTrue(all(MODULE._china_fuel_export_stage(r.title)=="planned_resume" for r in events[0][1]))

    def test_china_reuters_snapshot_370m_tons_is_not_actual_exports(self):
        now=dt.datetime(2026,10,9,13,tzinfo=dt.timezone.utc)
        html="""<html>China is set to resume October refined fuel exports after a brief halt
        during Golden Week, four traders said Friday. China approved October exports
        of gasoline diesel and jet fuel combined at around 3.7 million metric tons.</html>"""
        row=MODULE.parse_china_reuters_resumption(html,now)
        self.assertEqual(MODULE._china_resumption_volume([row]),3.7)
        body=MODULE.build_physical_flow_alert_body("china_fuel_export_policy",[row],None,now)
        self.assertIn("재개 예정",body)
        self.assertIn("370만 톤",body)
        self.assertIn("실제 출항",body)
        self.assertLessEqual(len(body.splitlines()),34)

    def test_china_syndicated_reuters_not_two_independent_sources(self):
        now=dt.datetime(2026,10,9,13,tzinfo=dt.timezone.utc)
        rows=[
          MODULE.NewsItem("China to resume October fuel exports","Reuters","a",now.isoformat(),now.timestamp(),"china_fuel_export_policy"),
          MODULE.NewsItem("China to resume October fuel exports","MarketScreener","b",now.isoformat(),now.timestamp(),"china_fuel_export_policy"),
        ]
        self.assertIsNone(MODULE.confirm_event(rows))

    def test_hormuz_seven_day_is_conditional_not_seven_days_open(self):
        now=dt.datetime(2026,10,9,13,tzinfo=dt.timezone.utc)
        title="Iran Araghchi reviewing US views on seven-day plan to reopen Strait of Hormuz within seven days"
        self.assertEqual(MODULE.classify_event(title),"hormuz_7day_diplomacy")
        row=MODULE.NewsItem(title,"Xinhua",MODULE.HORMUZ_7DAY_XINHUA_URL,now.isoformat(),now.timestamp(),"hormuz_7day_diplomacy")
        body=MODULE.build_physical_flow_alert_body("hormuz_7day_diplomacy",[row],None,now)
        self.assertIn("7일 이내",body)
        self.assertIn("7일 동안 개방 확정",body)
        self.assertIn("실제 통항",body)

    def test_mma_official_url_and_dynamic_report_date_guards(self):
        a=MODULE.MMA_OIL_ISAIAS_OCT9_URL
        self.assertTrue(MODULE._is_official_mma_isaias_url(a))
        self.assertFalse(MODULE._is_official_mma_isaias_url("https://www.bsee.gov.evil.example/newsroom/latest-news/statements-and-releases/press-releases/mma-monitors-gulf-response-isaias4"))
        self.assertFalse(MODULE._is_official_mma_isaias_url("http://www.bsee.gov/newsroom/latest-news/statements-and-releases/press-releases/mma-monitors-gulf-response-isaias4"))
        self.assertEqual(MODULE._mma_report_date("<h1>MMA Isaias</h1><p>Friday, October 9, 2026</p>"),dt.date(2026,10,9))
        self.assertEqual(MODULE._discover_mma_isaias_urls('<a href="/newsroom/latest-news/statements-and-releases/press-releases/mma-monitors-gulf-response-isaias3">Oct9</a>'),[a])

    def test_mma_fetch_advances_to_latest_official_date(self):
        # Fixtures use genuine Oct7/Oct8 style with controlled Oct9 numbers; numbers are not live market assertions.
        import unittest.mock
        m=MODULE
        base="Marine Minerals Administration Isaias. {date}. evacuated from a total of {platforms} production platforms. " + (
            "approximately {pct:.2f}% of the current oil production and {gas:.2f}% of the current natural gas production. "
            "Oil, BOPD** Shut-in {bpd:,}"
        )
        pages={
            m.MMA_OIL_ISAIAS_OCT7_URL:base.format(date="October 7, 2026",platforms=8,pct=25.08,gas=16.37,bpd=511619),
            m.MMA_OIL_ISAIAS_OCT8_URL:base.format(date="October 8, 2026",platforms=121,pct=62.90,gas=44.00,bpd=1280000),
            m.MMA_OIL_ISAIAS_OCT9_URL:base.format(date="October 9, 2026",platforms=129,pct=71.50,gas=58.90,bpd=1450000),
            m.MMA_ISAIAS_NEWS_INDEX_URL:'<a href="/newsroom/latest-news/statements-and-releases/press-releases/mma-monitors-gulf-response-isaias3">Oct9</a>'
        }
        def fetch(url,timeout=16,attempts=1):
            return pages[url].encode()
        with unittest.mock.patch.object(m,"fetch_bytes",side_effect=fetch):
            row=m.fetch_mma_isaias_snapshot(dt.datetime(2026,10,10,0,0,tzinfo=dt.timezone.utc))
        self.assertEqual(row.event_kind,"us_gulf_isaias_shutin")
        self.assertIn("date=2026-10-09",row.title)
        self.assertIn("previous_bpd=1280000",row.title)
        self.assertEqual(row.link,m.MMA_OIL_ISAIAS_OCT9_URL)
        parsed=m._extract_mma_isaias_data([row])
        self.assertIsNotNone(parsed)
        body=m._build_us_gulf_isaias_alert_body([row],None,dt.datetime(2026,10,10,tzinfo=dt.timezone.utc),None)
        self.assertIn("2026-10-09",body)
        self.assertIn("isaias3",body)

    def test_mma_fetch_fails_closed_on_stale_official_report(self):
        import unittest.mock
        m=MODULE
        pages={}
        for url,d,p in (
            (m.MMA_OIL_ISAIAS_OCT7_URL,"October 7, 2026",25.08),
            (m.MMA_OIL_ISAIAS_OCT8_URL,"October 8, 2026",62.9),
            (m.MMA_OIL_ISAIAS_OCT9_URL,"October 9, 2026",71.5),
        ):
            pages[url]=f"Marine Minerals Administration Isaias {d} evacuated from a total of 129 production platforms. approximately {p:.2f}% of the current oil production and 58.90% of the current natural gas production. Oil, BOPD** Shut-in 1,450,000"
        def fetch(url,timeout=16,attempts=1):
            if url==m.MMA_ISAIAS_NEWS_INDEX_URL: return b"<html></html>"
            return pages[url].encode()
        with unittest.mock.patch.object(m,"fetch_bytes",side_effect=fetch):
            with self.assertRaisesRegex(RuntimeError,"경과"):
                m.fetch_mma_isaias_snapshot(dt.datetime(2026,10,16,tzinfo=dt.timezone.utc))

    def test_china_resumption_delay_overrides_future_plan(self):
        self.assertEqual(MODULE._china_fuel_export_stage("China's fuel exports set to resume but resumption postponed after port delays"),"resumption_delayed")
        self.assertEqual(MODULE.classify_event("China fuel exports resumption delayed for October after postponement"),"china_fuel_export_policy")

    def test_china_physical_shipments_need_independent_tracking(self):
        now=dt.datetime(2026,10,10,tzinfo=dt.timezone.utc)
        def make(name,url):
            return MODULE.NewsItem("China fuel cargoes departed port after October restart",name,url,now.isoformat(),now.timestamp(),"china_fuel_export_policy")
        row=make("Reuters","https://www.reuters.com/example")
        self.assertEqual(MODULE._china_fuel_export_stage(row.title),"physical_resumed")
        self.assertFalse(MODULE._china_physical_shipment_evidence([row]))
        self.assertIsNone(MODULE.confirm_event([row]))
        duplicate=make("Reuters via MarketScreener","https://www.marketscreener.com/example")
        self.assertIsNone(MODULE.confirm_event([row,duplicate]))
        tracker=make("Kpler","https://www.kpler.com/blog/actual-cargo-shipments")
        self.assertTrue(MODULE._china_physical_shipment_evidence([row,tracker]))
        self.assertIsNotNone(MODULE.confirm_event([row,tracker]))

    def test_mma_official_shutin_source_and_change(self):
        def page(day,oil_pct,gas_pct,bpd,platforms):
            return f"""<html>Marine Minerals Administration Isaias Thursday, October {day}, 2026
            The Marine Minerals Administration estimates that approximately {oil_pct}% of the
            current daily oil production and {gas_pct}% of the current daily natural gas production.
            Personnel have been evacuated from a total of {platforms} production platforms.
            Total Shut-in Percentage of GOA Production Oil, BOPD** Shut-in {bpd} (BOPD).</html>"""
        old=MODULE._parse_mma_isaias_report(page(7,25.08,16.37,"511,619",8),"2026-10-07")
        new=MODULE._parse_mma_isaias_report(page(8,62.89,57.35,"1,282,879",121),"2026-10-08")
        self.assertEqual(new["oil_bpd"]-old["oil_bpd"],771260)
        self.assertEqual(new["oil_pct"],62.89)

    def test_mma_cannot_use_news_claim_without_official_url(self):
        now=dt.datetime(2026,10,9,13,tzinfo=dt.timezone.utc)
        row=MODULE.NewsItem(
            "MMA Isaias date=2026-10-08; oil_bpd=1282879; oil_pct=62.89; gas_pct=57.35; platforms=121; previous_bpd=511619; previous_pct=25.08",
            "Blog","https://fake.com",now.isoformat(),now.timestamp(),"us_gulf_isaias_shutin"
        )
        self.assertIsNone(MODULE._extract_mma_isaias_data([row]))
        self.assertIsNone(MODULE.confirm_event([row]))

    def test_direct_historical_sources_expire(self):
        now=dt.datetime(2026,10,16,13,tzinfo=dt.timezone.utc)
        with self.assertRaisesRegex(RuntimeError,"유효기간"):
            MODULE.parse_china_reuters_resumption("",now)
        with self.assertRaisesRegex(RuntimeError,"신선도"):
            MODULE.parse_hormuz_xinhua_review("",now)
        with self.assertRaisesRegex(RuntimeError,"신선도"):
            MODULE.fetch_mma_isaias_snapshot(now)

    def test_hormuz_direct_source_requires_original_text(self):
        now=dt.datetime(2026,10,9,13,tzinfo=dt.timezone.utc)
        with self.assertRaisesRegex(RuntimeError,"미검증"):
            MODULE.parse_hormuz_xinhua_review("Hormuz opened for 7 days",now)
        row=MODULE.parse_hormuz_xinhua_review(
          "Araghchi seven-day plan Hormuz currently reviewing the US reply",now)
        self.assertEqual(row.event_kind,"hormuz_7day_diplomacy")

    def test_russia_diesel_announcement_and_license_are_separate_stages(self):
        promise = "Trump says Russia to immediately supply 300,000 tons of diesel fuel"
        gl = "OFAC Russia General License 135 issued 2026-10-09 authorizing Russian diesel transactions"
        self.assertEqual(MODULE.classify_event(promise), "russia_diesel_supply_transition")
        self.assertEqual(MODULE.classify_event(gl), "russia_diesel_supply_transition")
        self.assertEqual(MODULE._russian_diesel_supply_stage(promise), "deal_announced")
        self.assertEqual(MODULE._russian_diesel_supply_stage(gl), "us_license_issued")
        self.assertNotEqual(MODULE.classify_event(promise), "us_diesel_export_policy")

    def test_russia_diesel_real_ofac_primary_and_spoof_rejected(self):
        now = dt.datetime(2026, 10, 10, 0, tzinfo=dt.timezone.utc)
        html = """
        <h1>Issuance of Russia-related General License</h1>
        <p>10/09/2026</p>
        <p>The Department of the Treasury's Office of Foreign Assets Control (OFAC)
        is issuing Russia-related General License 135, Authorizing Transactions
        Related to the Sale, Delivery, Offloading, and Importation of Diesel Fuel of Russian Federation Origin.</p>
        """
        row = MODULE.parse_ofac_russian_diesel_license(html, now)
        self.assertTrue(MODULE._russian_license_is_official(row))
        self.assertIsNotNone(MODULE.confirm_event([row]))
        bad = MODULE.NewsItem(row.title, row.source, "https://fake-ofac.example/recent-actions/20261009_33",
                              row.published_utc, row.published_epoch, row.event_kind)
        self.assertFalse(MODULE._russian_license_is_official(bad))
        self.assertIsNone(MODULE.confirm_event([bad]))
        with self.assertRaisesRegex(RuntimeError, "검증 실패"):
            MODULE.parse_ofac_russian_diesel_license(html.replace("135", "134"), now)

    def test_russia_rss_syndication_not_two_independent_sources(self):
        now = dt.datetime(2026, 10, 10, 0, tzinfo=dt.timezone.utc)
        title = "Trump says Russia to immediately supply 300,000 tons of diesel fuel"
        rows = [
            MODULE.NewsItem(title, "Reuters", "https://www.reuters.com/business/energy/test",
                            now.isoformat(), now.timestamp(), "russia_diesel_supply_transition"),
            MODULE.NewsItem(title + " - Reuters", "MarketScreener", "https://marketscreener.com/reuters-test",
                            now.isoformat(), now.timestamp(), "russia_diesel_supply_transition"),
        ]
        self.assertIsNone(MODULE.confirm_event(rows))
        rows.append(MODULE.NewsItem("Trump strikes deal with Putin for Russian diesel",
                                   "Associated Press", "https://apnews.com/article/test",
                                   now.isoformat(), now.timestamp(), "russia_diesel_supply_transition"))
        result = MODULE.confirm_event(rows)
        self.assertIsNotNone(result)
        self.assertEqual(result[0], "russia_diesel_supply_transition")

    def test_russia_rhetoric_never_proves_cargo_departure(self):
        now = dt.datetime(2026, 10, 10, 0, tzinfo=dt.timezone.utc)
        title = "Trump says Russia to immediately supply 300,000 tons of diesel fuel"
        r = MODULE.NewsItem(title, "Reuters", "https://www.reuters.com/business/energy/test",
                            now.isoformat(), now.timestamp(), "russia_diesel_supply_transition")
        self.assertEqual(MODULE._russian_diesel_supply_stage(title), "deal_announced")
        self.assertNotIn("shipment_verified", [MODULE._russian_diesel_supply_stage(r.title)])
        self.assertFalse(MODULE._russian_physical_shipment_confirmed([r]))
        bad = MODULE.NewsItem("Russia diesel shipments loaded onto tanker according to sources",
                              "Reuters", r.link, r.published_utc, r.published_epoch, r.event_kind)
        self.assertIsNone(MODULE.confirm_event([bad]))
        self.assertFalse(MODULE._russian_physical_shipment_confirmed([bad]))

    def test_russia_same_license_not_sent_again_but_new_stage_can_alert(self):
        now = dt.datetime(2026, 10, 10, 0, tzinfo=dt.timezone.utc)
        row = MODULE.parse_ofac_russian_diesel_license(
            "10/09/2026 Russia-related General License 135 authorizing transactions related to"
            " sale delivery offloading and importation of Diesel Fuel of Russian Federation Origin",
            now)
        eid = MODULE.event_id("russia_diesel_supply_transition", [row])
        state = {"alerted_events":{eid:now.astimezone(MODULE.KST).isoformat()}}
        result, duplicates = MODULE.select_unalerted_event(
            state, [("russia_diesel_supply_transition", [row])], now)
        self.assertIsNone(result)
        self.assertTrue(duplicates)

    def test_russia_alert_krw_and_conditional_volume_not_claimed_delivered(self):
        now = dt.datetime(2026, 10, 10, 0, tzinfo=dt.timezone.utc)
        row = MODULE.parse_ofac_russian_diesel_license(
            "10/09/2026 Russia-related General License 135 authorizing transactions related to"
            " sale delivery offloading and importation of Diesel Fuel of Russian Federation Origin",
            now)
        body = MODULE.build_physical_flow_alert_body("russia_diesel_supply_transition",
                                                     [row], None, now)
        self.assertIn("30만 톤 초과", body)
        self.assertIn("480만 톤 초과", body)
        self.assertIn("정유시설 조건부 300만 톤", body)
        self.assertIn("실제 수출량 아님", body)
        self.assertIn("OFAC 제135호", body)
        self.assertNotIn("러시아 경유 실제 선적 복수 자료 확인", body)
        self.assertLessEqual(len(body.splitlines()), 38)

    def test_russia_license_is_not_resent_after_14_or_45_days(self):
        now = dt.datetime(2026, 10, 10, 0, tzinfo=dt.timezone.utc)
        row = MODULE.parse_ofac_russian_diesel_license(
            "10/09/2026 Russia-related General License 135 authorizing transactions related to"
            " sale delivery offloading and importation of Diesel Fuel of Russian Federation Origin",
            now
        )
        eid = MODULE.event_id("russia_diesel_supply_transition", [row])
        old_date = (now - dt.timedelta(days=70)).astimezone(MODULE.KST).isoformat()
        state = {"alerted_events": {eid: old_date}}
        self.assertTrue(MODULE.event_recently_alerted(state, eid, now))
        new_state = MODULE.build_pending_state(
            state, "another:event", "other", now, {}
        )
        self.assertIn(eid, new_state["alerted_events"])
        self.assertIsNone(
            MODULE.select_unalerted_event(
                new_state, [("russia_diesel_supply_transition", [row])], now
            )[0]
        )

    def test_russia_ap_original_title_independent_agreement(self):
        title = "Trump strikes deal with Putin for Russian diesel ahead of midterms"
        self.assertEqual(MODULE.classify_event(title), "russia_diesel_supply_transition")
        self.assertEqual(MODULE._russian_diesel_supply_stage(title), "deal_announced")

    def test_russia_novak_lifts_restrictions_but_not_loaded(self):
        title = "Novak says Russia starting to lift restrictions on diesel exports"
        self.assertEqual(MODULE.classify_event(title), "russia_diesel_supply_transition")
        self.assertEqual(MODULE._russian_diesel_supply_stage(title), "russian_ban_lifting_reported")
        self.assertFalse(MODULE._russian_physical_shipment_confirmed([
            MODULE.NewsItem(title, "Reuters", "https://www.reuters.com/test", "2026-10-10T00:00Z", 0, "russia_diesel_supply_transition")
        ]))

    def test_russia_physical_requires_date_volume_and_two_independent_providers(self):
        now = dt.datetime(2026, 10, 12, 15, tzinfo=dt.timezone.utc)
        def row(title,source,url):
            return MODULE.NewsItem(title,source,url,now.isoformat(),now.timestamp(),"russia_diesel_supply_transition")
        k = row("Kpler Russia diesel cargoes loaded 2026-10-12 300,000 metric tons",
                "Kpler","https://www.kpler.com/reports/real-track")
        r = row("Reuters Russia diesel cargo departed 2026-10-12 300000 tonnes",
                "Reuters","https://www.reuters.com/business/energy/real-report")
        self.assertEqual(MODULE.classify_event(k.title), "russia_diesel_supply_transition")
        self.assertEqual(MODULE._russian_diesel_supply_stage(k.title), "shipment_verified")
        self.assertFalse(MODULE._russian_physical_shipment_confirmed([k]))
        self.assertTrue(MODULE._russian_physical_shipment_confirmed([k,r]))
        self.assertIsNotNone(MODULE.confirm_event([k,r]))
        fp=MODULE._russian_shipment_fingerprint([k,r])
        self.assertEqual(fp,("2026-10-12",6))
        different_day = row(r.title.replace("2026-10-12","2026-10-13"),r.source,r.link)
        different_qty = row(r.title.replace("300000","600000"),r.source,r.link)
        self.assertFalse(MODULE._russian_physical_shipment_confirmed([k,different_day]))
        self.assertFalse(MODULE._russian_physical_shipment_confirmed([k,different_qty]))
        no_date = row(r.title.replace("2026-10-12",""),r.source,r.link)
        self.assertFalse(MODULE._russian_physical_shipment_confirmed([k,no_date]))

    def test_russia_actual_shipments_dedup_by_observed_date_and_tons(self):
        now=dt.datetime(2026,10,12,15,tzinfo=dt.timezone.utc)
        def pair(day, qty):
            return [
                MODULE.NewsItem(f"Kpler Russia diesel cargoes loaded {day} {qty} tonnes",
                    "Kpler","https://kpler.com/report",now.isoformat(),now.timestamp(),"russia_diesel_supply_transition"),
                MODULE.NewsItem(f"Reuters Russia diesel cargo departed {day} {qty} tonnes",
                    "Reuters","https://reuters.com/article",now.isoformat(),now.timestamp(),"russia_diesel_supply_transition")
            ]
        a=MODULE.event_id("russia_diesel_supply_transition",pair("2026-10-12",300000))
        b=MODULE.event_id("russia_diesel_supply_transition",pair("2026-10-13",300000))
        c=MODULE.event_id("russia_diesel_supply_transition",pair("2026-10-12",400000))
        self.assertNotEqual(a,b)
        self.assertNotEqual(a,c)
        self.assertEqual(a,MODULE.event_id("russia_diesel_supply_transition",pair("2026-10-12",300000)))

    def test_china_fuel_export_suspension_classified(self):
        title = "Chinese refiners suspend October fuel exports, PetroChina cancels cargoes - Reuters"
        self.assertEqual(MODULE.classify_event(title), "china_fuel_export_policy")

    def test_china_fuel_export_resume_is_new_stage(self):
        now = dt.datetime(2026, 10, 8, 1, 0, tzinfo=dt.timezone.utc)
        suspended = MODULE.NewsItem(
            "Chinese refiners suspend October fuel exports outside Hong Kong and Macau",
            "Reuters", "a", now.isoformat(), now.timestamp(), "china_fuel_export_policy"
        )
        resumed = MODULE.NewsItem(
            "China resumes refined product exports after Beijing gives green light",
            "Reuters", "b", now.isoformat(), now.timestamp(), "china_fuel_export_policy"
        )
        self.assertNotEqual(
            MODULE.event_id("china_fuel_export_policy", [suspended]),
            MODULE.event_id("china_fuel_export_policy", [resumed]),
        )

    def test_china_fuel_export_body_keeps_official_status_cautious(self):
        now = dt.datetime(2026, 10, 1, 7, 0, tzinfo=dt.timezone.utc)
        rows = [MODULE.NewsItem(
            "Chinese refiners suspend October fuel exports, PetroChina cancels cargoes",
            "Reuters", "https://example.com/reuters", now.isoformat(), now.timestamp(), "china_fuel_export_policy"
        )]
        body = MODULE.build_physical_flow_alert_body("china_fuel_export_policy", rows, None, now)
        self.assertIn("중국 정책", body)
        self.assertIn("기존 10월 선적 취소", body)
        self.assertIn("10월 7일", body)
        self.assertIn("공식 전면 금지로 표현하지 않습니다", body)

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
