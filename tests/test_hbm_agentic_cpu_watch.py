import pathlib
import sys
import unittest
from datetime import datetime
from unittest import mock
from zoneinfo import ZoneInfo

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "scripts"))
import agentic_cpu_watch as w


class AgenticCpuParseTests(unittest.TestCase):
    def test_parse_bofa_210_snapshot(self):
        text = """
        BofA raises its CY30E server CPU total addressable market forecast to $210.6bn
        from ~$170bn, representing a 36.1% CAGR from CY26.
        Server CPU TAM 210.6 USD billion.
        AI CPU TAM 180.4 USD billion.
        split roughly 50/50 between compute/head nodes ($90.2bn)
        and agentic AI nodes ($90.2bn).
        about $30bn for traditional/IaaS.
        """
        m = w.parse_forecast(text)
        self.assertAlmostEqual(m["server_cpu_tam_2030_usd_bn"], 210.6)
        self.assertAlmostEqual(m["ai_cpu_2030_usd_bn"], 180.4)
        self.assertAlmostEqual(m["agentic_2030_usd_bn"], 90.2)
        self.assertAlmostEqual(m["compute_head_2030_usd_bn"], 90.2)
        self.assertAlmostEqual(m["agentic_share_pct"], 90.2 / 210.6 * 100)

    def test_parse_requires_agentic_server_cpu_context(self):
        self.assertEqual(w.parse_forecast("GPU TAM $500bn by 2030"), {})

    def test_ratio_extract(self):
        text = "Agentic AI is moving from a 1 CPU : 4-8 GPUs pattern toward a 1:1 ratio."
        self.assertEqual(w.extract_ratio(text), "1:1")


class AgenticCpuThresholdTests(unittest.TestCase):
    def test_tam_ten_percent_triggers(self):
        old = {"server_cpu_tam_2030_usd_bn": 210.6}
        new = {"server_cpu_tam_2030_usd_bn": 232.0}
        changes = w.material_forecast_changes(old, new)
        self.assertEqual(len(changes), 1)

    def test_subthreshold_tam_is_quiet(self):
        old = {"server_cpu_tam_2030_usd_bn": 210.6}
        new = {"server_cpu_tam_2030_usd_bn": 230.0}
        self.assertEqual(w.material_forecast_changes(old, new), [])

    def test_share_five_percentage_points_triggers(self):
        old = {"agentic_share_pct": 42.8}
        new = {"agentic_share_pct": 48.0}
        changes = w.material_forecast_changes(old, new)
        self.assertEqual(changes[0]["mode"], "pp")

    def test_ratio_structure_change(self):
        self.assertTrue(w.ratio_changed("1:1", "1:2"))
        self.assertFalse(w.ratio_changed("1:1", "1 : 1"))


class AgenticCpuAlertTests(unittest.TestCase):
    def test_snapshot_is_compact_but_keeps_key_axes(self):
        state = w.BASELINE
        block = w.snapshot_block(
            state,
            1371.0,
            "2026-09-25",
            [{"key": "server_cpu_tam_2030_usd_bn", "label": "2030 서버 CPU 시장", "before": 190.0, "after": 210.6, "delta": 10.8, "mode": "pct"}],
            None,
            [],
            standalone=False,
        )
        self.assertIn("<b>CPU·에이전트형 AI</b>", block)
        self.assertIn("• 변화:", block)
        self.assertIn("• 기준:", block)
        self.assertIn("• 의미:", block)
        self.assertIn("• 다음:", block)
        self.assertNotIn("<b>변화</b>", block)
        self.assertNotIn("<b>현재 기준선</b>", block)
        self.assertIn("2,106억달러(", block)
        self.assertIn("902억달러(", block)
        self.assertIn("42.8%", block)
        self.assertIn("1:4~8", block)
        self.assertIn("1:1", block)
        self.assertIn("DDR5 RDIMM", block)
        self.assertIn("기업용 SSD", block)
        self.assertIn("FC-BGA/ABF", block)
        self.assertNotIn("<b>관련 기업 지도</b>", block)
        self.assertNotIn("<b>숨은 역풍·실패모드</b>", block)
        self.assertNotIn("<b>알림 기준</b>", block)
        self.assertLess(len(block), 950)

    def test_material_forecast_alert_shows_old_and_new(self):
        latest = dict(w.BASELINE)
        latest["metrics"] = dict(w.BASELINE["metrics"])
        latest["metrics"]["server_cpu_tam_2030_usd_bn"] = 240.0
        changes = w.material_forecast_changes(
            w.BASELINE["metrics"], latest["metrics"]
        )
        block = w.snapshot_block(latest, None, "", changes, None, [], standalone=True)
        self.assertIn("2,106억달러", block)
        self.assertIn("2,400억달러", block)
        self.assertIn("+14.0%", block)


class AgenticCpuStructureTests(unittest.TestCase):
    def test_baselines_preserve_institution_and_source_scope(self):
        sources = w.CPU_STRUCTURE_BASELINE
        self.assertEqual(sources["bnpp_public"]["market_2025_usd_bn"], 26.0)
        self.assertEqual(sources["bnpp_public"]["market_2030_usd_bn"], 220.0)
        self.assertIn("AMD 추정치", sources["bnpp_public"]["source_kind"])
        self.assertEqual(sources["bnpp_analyst"]["market_2030_usd_bn"], 245.0)
        self.assertFalse(sources["bnpp_analyst"]["market_2030_official_confirmed"])
        self.assertTrue(sources["bnpp_analyst"]["market_2030_secondary_confirmed"])
        self.assertFalse(sources["bnpp_analyst"]["market_2025_official_confirmed"])
        self.assertEqual(sources["bnpp_analyst"]["amd_target_usd"], 960.0)
        self.assertFalse(sources["bnpp_analyst"]["arm_target_confirmed"])
        self.assertEqual(sources["digitimes"]["ai_server_cpu_2027_million"], 9.845)
        self.assertEqual(sources["digitimes"]["arm_all_server_cpu_2027_share_pct"], 32.5)
        self.assertEqual(sources["amd_system"]["helios_venice_cpus"], 18)
        self.assertEqual(sources["amd_system"]["helios_mi455x_gpus"], 72)

    def test_other_market_republication_cannot_overwrite_bnp_public(self):
        url = "https://example.org/2026/bnp-says-cpu-300b"
        provider, value = w.cpu_structure_observation(
            "BNP Paribas agentic CPUs market", "from USD30 billion in 2025 to USD245 billion in 2030",
            url,
        )
        self.assertEqual((provider, value), ("", {}))
        provider, value = w.cpu_structure_observation(
            "BNP Paribas agentic CPUs market",
            "AMD estimates suggest the data centre CPU market could rise from around USD26 billion in 2025 to around USD220 billion in 2030.",
            w.CPU_STRUCTURE_BASELINE["bnpp_public"]["source_url"],
        )
        self.assertEqual(provider, "bnpp_public")
        self.assertEqual(value["market_2025_usd_bn"], 26.0)
        self.assertEqual(value["market_2030_usd_bn"], 220.0)

    def test_digitimes_typed_nearly_double_is_not_exact_socket_ratio(self):
        url = w.CPU_STRUCTURE_BASELINE["digitimes"]["per_accelerator_source_url"]
        provider, value = w.cpu_structure_observation(
            "AI servers will carry nearly twice as many CPUs per accelerator by 2027",
            "",
            url,
        )
        self.assertEqual(provider, "digitimes")
        self.assertEqual(value["per_accelerator_cpu_2027"], "nearly_double")
        self.assertEqual(w.cpu_structure_changes(w.CPU_STRUCTURE_BASELINE["digitimes"], value, provider), [])
        provider, value = w.cpu_structure_observation(
            "AI servers will carry three times as many CPUs per accelerator by 2027",
            "",
            url,
        )
        self.assertEqual(w.cpu_structure_changes(w.CPU_STRUCTURE_BASELINE["digitimes"], value, provider), [
            "DIGITIMES 2027 가속기당 CPU 전망 변경: nearly_double→triple"
        ])

    def test_bnp_2030_revision_only_compares_same_provider(self):
        old = w.CPU_STRUCTURE_BASELINE["bnpp_public"]
        self.assertEqual(w.cpu_structure_changes(old, {"market_2030_usd_bn": 235}, "bnpp_public"), [])
        self.assertEqual(
            w.cpu_structure_changes(old, {"market_2030_usd_bn": 250}, "bnpp_public"),
            ["BNP 공개자료의 AMD 인용 CPU 시장 전망: 220→250십억달러"],
        )
        self.assertEqual(
            w.cpu_structure_changes(
                w.CPU_STRUCTURE_BASELINE["bnpp_analyst"],
                {"market_2030_usd_bn": 245}, "bnpp_analyst"
            ),
            [],
        )

    def test_secondary_bnp_target_requires_exact_issuer_and_company(self):
        url = "https://www.marketscreener.com/news/bnp-paribas-adjusts-pt-on-advanced-micro-devices-to-960-from-600-keeps-outperform-rating-ce785ddbd08af222"
        name, obs = w.cpu_structure_observation(
            "BNP Paribas Adjusts PT on Advanced Micro Devices to $960 From $600",
            "", url,
        )
        self.assertEqual(name, "bnpp_analyst")
        self.assertEqual(obs["amd_target_usd"], 960)
        self.assertEqual(w.cpu_structure_changes(w.CPU_STRUCTURE_BASELINE[name], obs, name), [])
        name, obs = w.cpu_structure_observation(
            "BNP Paribas Adjusts PT on Advanced Micro Devices to $1,100 From $960",
            "", url,
        )
        self.assertEqual(name, "bnpp_analyst")
        self.assertIn("AMD 목표주가 전망 변경", w.cpu_structure_changes(w.CPU_STRUCTURE_BASELINE[name], obs, name)[0])
        name, obs = w.cpu_structure_observation(
            "Citi adjusts AMD price target to $1,100 from $960",
            "", url,
        )
        self.assertEqual((name, obs), ("", {}))

    def test_digitimes_ai_server_cpu_quantity_is_not_all_server_total(self):
        url = w.CPU_STRUCTURE_BASELINE["digitimes"]["shipments_source_url"]
        name, obs = w.cpu_structure_observation(
            "2027 AI server CPU demand increases",
            "AI server CPU shipments in 2027 will reach 11.2 million processors.",
            url,
        )
        self.assertEqual(name, "digitimes")
        self.assertEqual(obs["ai_server_cpu_2027_million"], 11.2)
        self.assertIn("출하 전망 변경", w.cpu_structure_changes(w.CPU_STRUCTURE_BASELINE[name], obs, name)[0])
        name, obs = w.cpu_structure_observation(
            "2027 CPU shipments",
            "Total server CPU shipments in 2027 will reach 50 million.",
            url,
        )
        self.assertEqual((name, obs), ("", {}))

    def test_arm_target_requires_named_company_and_bnp_attribution(self):
        url = "https://www.marketscreener.com/news/bnp-paribas-arm-holdings-pt-405"
        name, obs = w.cpu_structure_observation(
            "BNP Paribas Adjusts PT on Arm Holdings to $405 From $350",
            "", url,
        )
        self.assertEqual(name, "bnpp_analyst")
        self.assertEqual(obs.get("arm_target_usd"), 405)
        self.assertTrue(obs.get("arm_target_confirmed"))
        self.assertNotIn("amd_target_usd", obs)
        changes = w.cpu_structure_changes(w.CPU_STRUCTURE_BASELINE[name], obs, name)
        self.assertTrue(any("신규 확인" in x for x in changes))
        self.assertEqual(
            w.cpu_structure_observation(
                "Citi Adjusts PT on Arm Holdings to $405 From $350", "", url
            ),
            ("", {}),
        )

    def test_245bn_remains_unconfirmed_without_analyst_original(self):
        ba = w.CPU_STRUCTURE_BASELINE["bnpp_analyst"]
        self.assertFalse(ba["market_2030_official_confirmed"])
        self.assertIn("2차 보도 교차확인", ba["market_2030_source_kind"])
        rendered = w.cpu_structure_block(w.CPU_STRUCTURE_BASELINE, 1345.37, [])
        self.assertIn("2,450억달러(", rendered)
        self.assertIn("보고서 원문 미열람", rendered)
        self.assertIn("2025년 300억달러(", rendered)
        self.assertIn("사용자 제공치로 미확인", rendered)

    def test_mixed_bnp_amd_nvidia_arm_targets_never_cross_attributed(self):
        url = w.CPU_STRUCTURE_BASELINE["bnpp_analyst"]["target_source_url"]
        for article in (
            "BNP Paribas sees AMD as a competitor and raised Nvidia price target to $345.",
            "BNP Paribas raised its price target on Nvidia to $345 and discussed AMD server CPUs.",
            "BNP Paribas discusses AMD processors while raising Arm price target to $405.",
        ):
            with self.subTest(article=article):
                self.assertEqual(w.cpu_structure_observation(article, "", url), ("", {}))
        name, obs = w.cpu_structure_observation(
            "BNP Paribas analyst raised its price target on AMD (NASDAQ: AMD) to $960 from $600",
            "", url,
        )
        self.assertEqual(name, "bnpp_analyst")
        self.assertEqual(obs.get("amd_target_usd"), 960.0)

    def test_digitimes_numeric_cpu_xpu_ratio_is_not_shipments_or_socket_count(self):
        di = w.CPU_STRUCTURE_BASELINE["digitimes"]
        self.assertEqual(di["cpu_xpu_ratio_2027"], 2.3)
        name, obs = w.cpu_structure_observation(
            "Agentic AI 2027年 AI伺服器CPU : XPU將提升至1 : 2.3",
            "AI server CPU:XPU ratio forecast for 2027",
            di["cpu_xpu_ratio_source_url"],
        )
        self.assertEqual(name, "digitimes")
        self.assertEqual(obs.get("cpu_xpu_ratio_2027"), 2.3)
        self.assertEqual(w.cpu_structure_changes(di, obs, "digitimes"), [])
        # The authentic DIGITIMES Chinese headline has the 1:2.3 ratio but
        # not the year. Do not silently miss it because English adds "2027".
        name2, obs2 = w.cpu_structure_observation(
            "Agentic AI、長推論驅動CPU需求　AI伺服器CPU : XPU將提升至1 : 2.3",
            "",
            di["cpu_xpu_ratio_source_url"],
        )
        self.assertEqual(name2, "digitimes")
        self.assertEqual(obs2.get("cpu_xpu_ratio_2027"), 2.3)
        self.assertEqual(w.cpu_structure_changes(di, {"cpu_xpu_ratio_2027": 2.2}, "digitimes"), [])
        self.assertIn("1:2.3→1:2", w.cpu_structure_changes(
            di, {"cpu_xpu_ratio_2027": 2.0}, "digitimes"
        )[0])
        self.assertNotIn("cpu_xpu_ratio_2027", w.cpu_structure_observation(
            "2027 NVIDIA accelerators are twice as fast",
            "AMD processor outlook", "https://www.amd.com/news", 
        )[1])

    def test_digitimes_traditional_chinese_ai_server_cpu_volume_not_total(self):
        url = w.CPU_STRUCTURE_BASELINE["digitimes"]["shipments_source_url"]
        title = "Agentic AI 2027年全球伺服器CPU出貨量將達4857.4萬顆"
        body = (
            "一般伺服器CPU為3527.9萬顆；"
            "AI伺服器CPU因配比提高，2027年出貨量將激增至984.5萬顆，年增84.1%。"
        )
        name, obs = w.cpu_structure_observation(title, body, url)
        self.assertEqual(name, "digitimes")
        self.assertAlmostEqual(obs["ai_server_cpu_2027_million"], 9.845)
        self.assertNotIn("all_server_cpu_2027_million", obs)

    def test_same_day_secondary_analyst_revision_is_not_lost(self):
        item = {
            "kind": "bing",
            "title": "BNP Paribas Adjusts PT on Advanced Micro Devices to $1,100 From $960",
            "description": "BNP Paribas adjusts the price target on AMD",
            "link": "https://www.marketscreener.com/news/bnp-paribas-adjusts-amd-pt-to-1100",
            "published_at_kst": "2026-10-05T21:00:00+09:00",
        }
        previous = w.CPU_STRUCTURE_BASELINE.copy()
        with mock.patch.object(w, "read_rss", return_value=[item]), mock.patch.object(w, "article_text", return_value=""):
            found = w.discover_cpu_structure(datetime(2026, 10, 5, 23, tzinfo=ZoneInfo("Asia/Seoul")), previous)
        self.assertEqual(len(found), 1)
        self.assertEqual(found[0]["issuer"], "bnpp_analyst")
        self.assertEqual(found[0]["metrics"].get("amd_target_usd"), 1100)

    def test_failed_source_parse_remains_retryable_instead_of_blacklisted(self):
        item = {
            "kind": "bing",
            "title": "BNP Paribas discusses AMD CPU market",
            "description": "Forecast report is restricted to subscribers",
            "link": "https://www.marketscreener.com/news/bnp-cpu-revision-2026",
            "published_at_kst": "2026-10-08T18:00:00+09:00",
        }
        previous = {
            **w.CPU_STRUCTURE_BASELINE,
            "seen_source_urls": [],
        }
        current_time = datetime(2026, 10, 8, 19, tzinfo=ZoneInfo("Asia/Seoul"))
        with mock.patch.object(w, "read_rss", return_value=[item]):
            with mock.patch.object(w, "article_text", return_value=""):
                first = w.discover_cpu_structure(current_time, previous)
            self.assertEqual(first, [])
            self.assertNotIn(item["link"], previous["seen_source_urls"])
            with mock.patch.object(
                w, "article_text",
                return_value="BNP Paribas adjusts PT on AMD to $1,100 from $960.",
            ):
                second = w.discover_cpu_structure(current_time, previous)
        self.assertEqual(len(second), 1)
        self.assertEqual(second[0]["metrics"]["amd_target_usd"], 1100)
        self.assertIn(item["link"], previous["seen_source_urls"])

    def test_same_day_bofa_revision_is_not_skipped_by_date_only_cutoff(self):
        item = {
            "kind": "bing",
            "title": "BofA agentic server CPU forecast revision",
            "description": "Bank of America server CPU TAM agentic AI outlook",
            "link": "https://example.org/new-bofa-cpu-forecast",
            "published_at_kst": "2026-10-08T19:00:00+09:00",
        }
        with (
            mock.patch.object(w, "read_rss", return_value=[item]),
            mock.patch.object(
                w, "article_text",
                return_value="BofA expects server CPU TAM $240bn in 2030 for agentic AI.",
            ),
        ):
            found = w.discover_forecasts(
                datetime(2026, 10, 8, 20, tzinfo=ZoneInfo("Asia/Seoul")),
                "2026-10-08",
            )
        self.assertEqual(len(found), 1)
        self.assertEqual(found[0]["metrics"]["server_cpu_tam_2030_usd_bn"], 240.0)

    def test_epyc_product_mention_is_not_customer_demand_validation(self):
        official_url = "https://www.amd.com/en/news/epyc-platforms"
        self.assertFalse(w.is_official_validation(
            official_url,
            "The AMD EPYC server CPU platform enables cloud computing workloads.",
        ))
        self.assertTrue(w.is_official_validation(
            official_url,
            "Meta is validating sixth-generation AMD EPYC CPUs in its labs.",
        ))
        self.assertFalse(w.is_official_validation(
            "https://untrusted.example.com/news",
            "Meta is validating sixth-generation AMD EPYC CPUs in its labs.",
        ))

    def test_cpu_validation_distinguishes_observed_orders_from_product_ramp(self):
        amd = "https://newsroom.amd.com/news/production-ramp"
        self.assertEqual(
            w.official_cpu_signal_type(amd, "AMD EPYC CPUs entered production ramp on TSMC 2nm."),
            "supply",
        )
        self.assertEqual(
            w.official_cpu_signal_type(amd, "Meta is validating sixth-generation AMD EPYC CPUs in its labs."),
            "demand",
        )
        self.assertEqual(
            w.official_cpu_signal_type(amd, "AMD EPYC CPU shipments accelerated."),
            "demand",
        )
        self.assertEqual(
            w.official_cpu_signal_type(amd, "AMD plans to ramp production of EPYC CPUs next year."),
            "",
        )
        self.assertEqual(
            w.official_cpu_signal_type(amd, "AMD expects to ramp production of EPYC CPUs next year."),
            "",
        )
        self.assertEqual(
            w.official_cpu_signal_type(
                amd, "New EPYC CPU launched. Memory chip suppliers received large orders."
            ),
            "",
        )
        self.assertEqual(
            w.official_cpu_signal_type(amd, "EPYC CPU shipments are not yet confirmed."),
            "",
        )
        self.assertEqual(
            w.official_cpu_signal_type(amd, "AMD expects EPYC CPU shipments to grow 40% in 2027."),
            "",
        )
        self.assertEqual(
            w.official_cpu_signal_type(amd, "AMD predicts that EPYC CPU revenue will double."),
            "",
        )
        self.assertEqual(
            w.official_cpu_signal_type(amd, "EPYC CPU shipments are projected to rise 40%."),
            "",
        )
        self.assertEqual(
            w.official_cpu_signal_type(amd, "EPYC CPUs are designed to support future deployments."),
            "",
        )
        self.assertEqual(
            w.official_cpu_signal_type(
                "https://unknown.test/press", "AMD EPYC CPU shipments accelerated."
            ),
            "",
        )

    def test_cpu_supply_only_alert_is_never_called_confirmed_customer_demand(self):
        supply = [{
            "title": "AMD EPYC Venice entered production ramp",
            "signal_type": "supply",
            "url": "https://newsroom.amd.com/news/production-ramp",
        }]
        block = w.snapshot_block(w.BASELINE, 1345.37, "2026-10-08", [], None, supply, standalone=False)
        self.assertIn("공식 공급확대", block)
        self.assertNotIn("공식 수요검증", block)
        demand = [dict(supply[0], signal_type="demand")]
        block2 = w.snapshot_block(w.BASELINE, 1345.37, "2026-10-08", [], None, demand, standalone=False)
        self.assertIn("공식 수요검증", block2)

    def test_same_day_official_cpu_validation_not_suppressed(self):
        item = {
            "kind": "bing",
            "title": "AMD EPYC CPU server shipment growth",
            "description": "AMD reports new CPU shipments and deployments",
            "link": "https://ir.amd.com/news-events/press-releases/detail/999/cpu-shipments",
            "published_at_kst": "2026-10-08T18:30:00+09:00",
        }
        now = datetime(2026, 10, 8, 19, tzinfo=ZoneInfo("Asia/Seoul"))
        with mock.patch.object(w, "read_rss", return_value=[item]), mock.patch.object(w, "article_text", return_value="EPYC CPU shipments accelerate"):
            found = w.discover_validation(now, "2026-10-08", set())
        self.assertEqual(len(found), 1)
        self.assertEqual(found[0]["url"], item["link"])
        # The same URL must never trigger twice, even within the lookback window.
        with mock.patch.object(w, "read_rss", return_value=[item]):
            duplicate = w.discover_validation(now, "2026-10-08", {item["link"]})
        self.assertEqual(duplicate, [])

    def test_fx_outage_blocks_validation_only_alert_without_state_advance(self):
        committed = {
            "agentic_cpu_demand": {
                **w.BASELINE,
                "cpu_structure_track_version": w.CPU_STRUCTURE_TRACK_VERSION,
                "cpu_structure": {**w.CPU_STRUCTURE_BASELINE, "cpu_xpu_ratio_alert_sent": True},
            }
        }
        with (
            mock.patch.object(w, "load_json", side_effect=[committed, {}]),
            mock.patch.object(w, "discover_forecasts", return_value=[]),
            mock.patch.object(w, "discover_validation", return_value=[{
                "title": "Official AMD EPYC shipments improve",
                "url": "https://ir.amd.com/news/events/epyc",
            }]),
            mock.patch.object(w, "discover_cpu_structure", return_value=[]),
            mock.patch.object(w, "get_fx", return_value=(None, "")),
            mock.patch.object(w, "write_json") as writer,
            mock.patch.object(w, "ALERT_PATH") as alert,
        ):
            alert.exists.return_value = False
            with self.assertRaisesRegex(RuntimeError, "verified USD/KRW conversion"):
                w.main()
            writer.assert_not_called()
            alert.write_text.assert_not_called()

    def test_existing_digitimes_ratio_numeric_upgrade_alerts_once(self):
        original_structure = w.CPU_STRUCTURE_BASELINE
        old_structure = {
            key: (dict(value) if isinstance(value, dict) else list(value))
            for key, value in original_structure.items()
        }
        old_structure["digitimes"].pop("cpu_xpu_ratio_2027", None)
        prev = {
            **w.BASELINE,
            "cpu_structure_track_version": w.CPU_STRUCTURE_TRACK_VERSION,
            "cpu_structure": old_structure,
        }

        def run(previous):
            captured = {}
            with (
                mock.patch.object(w, "load_json", side_effect=[{"agentic_cpu_demand": previous}, {}]),
                mock.patch.object(w, "discover_forecasts", return_value=[]),
                mock.patch.object(w, "discover_validation", return_value=[]),
                mock.patch.object(w, "discover_cpu_structure", return_value=[]),
                mock.patch.object(w, "get_fx", return_value=(1343.88, "2026-10-08")),
                mock.patch.object(w, "ALERT_PATH") as alert,
                mock.patch.object(w, "write_json") as writer,
            ):
                alert.exists.return_value = False
                w.main()
                captured["alerted"] = alert.write_text.called
                captured["body"] = alert.write_text.call_args.args[0] if captured["alerted"] else ""
                captured["next"] = writer.call_args.args[1]["agentic_cpu_demand"]
            return captured

        first = run(prev)
        self.assertTrue(first["alerted"])
        self.assertIn("CPU:XPU 1:2.3 수치 신규 추적", first["body"])
        self.assertEqual(first["next"]["cpu_structure"]["digitimes"]["cpu_xpu_ratio_2027"], 2.3)
        second = run(first["next"])
        self.assertFalse(second["alerted"])
        self.assertTrue(first["next"]["cpu_structure"]["cpu_xpu_ratio_alert_sent"])

        # A prior no-alert scan may already have persisted the number before
        # the one-time formatter was deployed. Its presence is not an ACK.
        already_seeded = {
            **w.BASELINE,
            "cpu_structure_track_version": w.CPU_STRUCTURE_TRACK_VERSION,
            "cpu_structure": w.CPU_STRUCTURE_BASELINE,
        }
        recovered = run(already_seeded)
        self.assertTrue(recovered["alerted"])
        self.assertTrue(recovered["next"]["cpu_structure"]["cpu_xpu_ratio_alert_sent"])
        self.assertFalse(run(recovered["next"])["alerted"])

    def test_arm_target_update_preserves_distinct_bnp_and_amd_citations(self):
        old = {
            **w.BASELINE,
            "cpu_structure_track_version": w.CPU_STRUCTURE_TRACK_VERSION,
            "cpu_structure": {
                **w.CPU_STRUCTURE_BASELINE,
                "cpu_xpu_ratio_alert_sent": True,
            },
        }
        arm_url = "https://www.marketscreener.com/news/bnp-paribas-arm-target-405"
        with (
            mock.patch.object(w, "load_json", side_effect=[{"agentic_cpu_demand": old}, {}]),
            mock.patch.object(w, "discover_forecasts", return_value=[]),
            mock.patch.object(w, "discover_validation", return_value=[]),
            mock.patch.object(w, "discover_cpu_structure", return_value=[{
                "issuer": "bnpp_analyst",
                "metrics": {"arm_target_usd": 405, "arm_target_confirmed": True},
                "url": arm_url,
                "as_of": "2026-10-12",
            }]),
            mock.patch.object(w, "get_fx", return_value=(1345.37, "2026-10-08")),
            mock.patch.object(w, "ALERT_PATH") as alert,
            mock.patch.object(w, "write_json") as writer,
        ):
            alert.exists.return_value = False
            w.main()
            analyst = writer.call_args.args[1]["agentic_cpu_demand"]["cpu_structure"]["bnpp_analyst"]
            self.assertTrue(alert.write_text.called)
        self.assertEqual(analyst["arm_target_source_url"], arm_url)
        self.assertEqual(analyst["target_source_url"], w.CPU_STRUCTURE_BASELINE["bnpp_analyst"]["target_source_url"])
        self.assertEqual(
            analyst["market_2030_source_url"],
            w.CPU_STRUCTURE_BASELINE["bnpp_analyst"]["market_2030_source_url"],
        )
        self.assertEqual(
            analyst["source_url"],
            w.CPU_STRUCTURE_BASELINE["bnpp_analyst"]["source_url"],
        )

    def test_digitimes_provenance_upgrade_and_future_source_link(self):
        original = w.CPU_STRUCTURE_BASELINE
        old_digitimes = dict(original["digitimes"])
        old_digitimes["cpu_xpu_ratio_source_kind"] = (
            "잘못된 과거 상태: DIGITIMES 원문 표제가 2027년이라고 단정"
        )
        structure = {
            **original, "digitimes": old_digitimes, "cpu_xpu_ratio_alert_sent": True,
        }
        prev = {
            **w.BASELINE,
            "cpu_structure_track_version": w.CPU_STRUCTURE_TRACK_VERSION,
            "cpu_structure": structure,
        }

        def run(new):
            with (
                mock.patch.object(w, "load_json", side_effect=[{"agentic_cpu_demand": prev}, {}]),
                mock.patch.object(w, "discover_forecasts", return_value=[]),
                mock.patch.object(w, "discover_validation", return_value=[]),
                mock.patch.object(w, "discover_cpu_structure", return_value=new),
                mock.patch.object(w, "get_fx", return_value=(1343.88, "2026-10-08")),
                mock.patch.object(w, "ALERT_PATH") as alert,
                mock.patch.object(w, "write_json") as writer,
            ):
                alert.exists.return_value = False
                w.main()
                next_state = writer.call_args.args[1]["agentic_cpu_demand"]["cpu_structure"]
                return next_state, alert.write_text.called

        repaired, sent = run([])
        self.assertFalse(sent)
        self.assertEqual(
            repaired["digitimes"]["cpu_xpu_ratio_source_kind"],
            original["digitimes"]["cpu_xpu_ratio_source_kind"],
        )
        new_url = "https://www.digitimes.com.tw/research/report/?v=20261012-new"
        revised, sent2 = run([{
            "issuer": "digitimes",
            "metrics": {"cpu_xpu_ratio_2027": 2.0},
            "url": new_url,
            "as_of": "2026-10-12",
        }])
        self.assertTrue(sent2)
        self.assertEqual(revised["digitimes"]["cpu_xpu_ratio_source_url"], new_url)
        self.assertIn("신규 공식자료", revised["digitimes"]["cpu_xpu_ratio_source_kind"])

    def test_one_shot_cpu_alert_has_separate_official_and_broker_provenance(self):
        a = w.cpu_structure_block(w.CPU_STRUCTURE_BASELINE, 1400.0, [])
        self.assertIn("260억달러(약", a)
        self.assertIn("2,200억달러(약", a)
        self.assertIn("2,450억달러(약", a)
        self.assertIn("BNP 애널리스트 2차 기사 교차확인", a)
        self.assertIn("AMD 목표주가", a)
        self.assertIn("Arm 목표주가 $405(약", a)
        self.assertIn("300억달러(약", a)
        self.assertIn("가속기당 CPU 거의 2배 전망", a)
        self.assertIn("984.5만개(+84.1%", a)
        self.assertIn("Arm 계열 전체 서버 CPU 1,580만개(32.5%)", a)
        self.assertIn("Venice CPU 18개·MI455X GPU 72개(물리 1:4)", a)
        self.assertNotIn("목표주가 $405(공식 확인)", a)
        self.assertIn("2nm 수율·ABF", a)
        self.assertLess(len(a), 2600)


if __name__ == "__main__":
    unittest.main()
