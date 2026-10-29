import json
import pathlib
import sys
import tempfile
import unittest
from unittest import mock

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "scripts"))
import ai_component_leadtime_watch as w
import agentic_cpu_watch as cpuw


class LeadTimeParserTests(unittest.TestCase):
    def test_balanced_benchmark_is_not_supply_status(self):
        text = (
            "DRAM current lead time 20 weeks against a balanced lead time of 8 weeks. "
            "ABF current lead time 48-56 weeks against a balanced 12 weeks. "
            "MLCC current lead time 32 weeks against a balanced 12 weeks."
        )
        rows = w.extract_components(text)
        self.assertEqual(rows["DRAM"].get("current"), "20")
        self.assertEqual(rows["DRAM"].get("balanced"), "8")
        self.assertNotIn("status", rows["DRAM"])
        self.assertNotIn("status", rows["ABF"])
        self.assertNotIn("status", rows["MLCC"])

    def test_explicit_status_groups_are_parsed(self):
        text = (
            "균형 상태인 품목은 GPU뿐이다. "
            "DRAM·HDD·ABF는 심각한 공급 부족, "
            "NAND eSSD·MLCC는 공급 제약 상태다."
        )
        rows = w.extract_components(text)
        self.assertEqual(rows["GPU"]["status"], "Balanced")
        self.assertEqual(rows["DRAM"]["status"], "Very Tight")
        self.assertEqual(rows["HDD"]["status"], "Very Tight")
        self.assertEqual(rows["ABF"]["status"], "Very Tight")
        self.assertEqual(rows["NAND(eSSD)"]["status"], "Tight")
        self.assertEqual(rows["MLCC"]["status"], "Tight")

    def test_weekly_002_bad_statuses_are_repaired(self):
        bad = {
            "source": "https://insights.trendforce.com/p/weekly-radar-002",
            "components": {
                "GPU": {"status": "Balanced", "current": "30-40", "balanced": "30-40"},
                "DRAM": {"status": "Balanced", "current": "20", "balanced": "8"},
                "NAND(eSSD)": {"status": "Very Tight", "current": "16", "balanced": "8"},
                "HDD": {"status": "Very Tight", "current": "50", "balanced": "16"},
                "ABF": {"status": "Balanced", "current": "48-56", "balanced": "12"},
                "MLCC": {"status": "Balanced", "current": "32", "balanced": "12"},
            },
        }
        fixed, changed = w.repair_weekly_002_state(bad)
        self.assertEqual(set(changed), {"DRAM", "NAND(eSSD)", "ABF", "MLCC"})
        self.assertEqual(fixed["components"]["DRAM"]["status"], "Very Tight")
        self.assertEqual(fixed["components"]["NAND(eSSD)"]["status"], "Tight")
        self.assertEqual(fixed["components"]["ABF"]["status"], "Very Tight")
        self.assertEqual(fixed["components"]["MLCC"]["status"], "Tight")

    def test_weekly_004_exact_table_lock_matches_user_provided_trendforce_screenshot(self):
        lock = w.WEEKLY_004_LOCK
        self.assertEqual(lock["as_of"], "2026-10-05")
        self.assertEqual(len(lock["components"]), 7)
        expected = {
            "CPU": ("Tight", "25-30", "16-20"),
            "GPU": ("Balanced", "30-40", "30-40"),
            "DRAM": ("Very Tight", "20", "8"),
            "NAND(eSSD)": ("Tight", "16", "8"),
            "HDD": ("Very Tight", "50", "16"),
            "ABF": ("Very Tight", "48-56", "12"),
            "MLCC": ("Tight", "35", "12"),
        }
        for name, triple in expected.items():
            self.assertEqual(w.canonical_component(lock["components"][name]), triple)

    def test_weekly_004_repair_corrects_dram_status_and_mlcc_stale_value(self):
        stale = {
            "as_of": "2026-10-05",
            "source": "https://insights.trendforce.com/p/weekly-radar-004",
            "components": {
                **w.WEEKLY_004_LOCK["components"],
                "DRAM": {"status": "Tight", "current": "20", "balanced": "8"},
                "MLCC": {"status": "Tight", "current": "32", "balanced": "12"},
            },
            "signals": {"MLCC": "old"},
        }
        fixed, component_changes, signal_changes = w.repair_weekly_004_state(stale)
        self.assertEqual(set(component_changes), {"DRAM", "MLCC"})
        self.assertEqual(fixed["components"]["DRAM"]["status"], "Very Tight")
        self.assertEqual(fixed["components"]["MLCC"]["current"], "35")
        self.assertIn("GPU", signal_changes)
        self.assertIn("MLCC", signal_changes)
        alert = w.build_weekly_004_correction_alert(
            stale["components"], fixed["components"], component_changes, signal_changes
        )
        self.assertIn("DRAM 상태 정정", alert)
        self.assertIn("MLCC 최신값", alert)
        self.assertIn("32주 → 35주", alert)
        self.assertIn("7개 품목", alert)

    def test_weekly_004_rows_parse_when_table_text_is_available(self):
        text = (
            "CPU Tight 25-30W 16-20W "
            "GPU Balanced 30-40W 30-40W "
            "DRAM Very Tight 20W 8W "
            "NAND Tight 16W 8W "
            "HDD Very Tight 50W 16W "
            "ABF Very Tight 48-56W 12W "
            "MLCC Tight 35W 12W"
        )
        rows = w.extract_components(text)
        self.assertEqual(rows["DRAM"]["status"], "Very Tight")
        self.assertEqual(rows["MLCC"]["current"], "35")
        self.assertEqual(rows["CPU"]["balanced"], "16-20")


    def test_cross_storage_parser_keeps_trendforce_scope_and_does_not_invent_controller_shortage(self):
        text = (
            "DRAM remains Very Tight at 20 weeks versus an 8-week balanced level, "
            "while shortages are limiting some NAND suppliers’ ability to support enterprise SSD solutions. "
            "HDD remains at 50 weeks, with relief unlikely before late 2027."
        )
        signals = w.extract_signals(text, "https://insights.trendforce.com/p/weekly-radar-005")
        self.assertEqual(
            signals["NAND(eSSD)"],
            "DRAM 공급 부족 → 일부 NAND 공급사의 기업용 SSD 솔루션 지원 능력 제약",
        )
        self.assertEqual(signals["HDD"], "HDD 50주 병목 → 공급 완화는 빨라도 2027년 말")
        self.assertNotIn("컨트롤러", signals["NAND(eSSD)"])

    def test_nand_controller_constraint_requires_explicit_same_sentence_causality(self):
        generic = (
            "DRAM shortage is constraining some NAND suppliers' ability to support enterprise SSD solutions. "
            "NAND controller demand remains healthy."
        )
        explicit = (
            "The DRAM shortage is directly constraining enterprise SSD controller shipments at some NAND suppliers."
        )
        self.assertFalse(w.extract_nand_controller_direct_constraint(generic))
        self.assertTrue(w.extract_nand_controller_direct_constraint(explicit))


    def test_memory_storage_chain_requires_direct_dram_to_essd_causality(self):
        components = w.WEEKLY_004_LOCK["components"]
        signals = w.WEEKLY_004_LOCK["signals"]
        chain = w.memory_storage_chain_state(components, signals)
        self.assertTrue(chain["active"])
        self.assertEqual(chain["dram_lead_ratio"], 2.5)
        self.assertEqual(chain["nand_essd_lead_ratio"], 2.0)
        self.assertEqual(chain["hdd_lead_ratio"], 3.125)
        self.assertTrue(chain["dram_to_enterprise_ssd_constraint_confirmed"])
        self.assertTrue(chain["hdd_relief_late_2027_or_later"])
        self.assertEqual(chain["version"], 3)
        self.assertTrue(chain["hdd_relief_is_market_normalization_outlook"])
        self.assertTrue(chain["toshiba_expanded_nearline_line_first_shipment_confirmed"])
        self.assertTrue(chain["toshiba_fy2027_capacity_nearly_double_target"])
        self.assertTrue(chain["nand_general_supply_easing_2h27_expected"])
        self.assertTrue(chain["enterprise_storage_primary_growth_engine"])
        self.assertTrue(chain["nand_essd_divergence_guard_enabled"])
        self.assertTrue(chain["nand_controller_direct_constraint_detection_enabled"])
        self.assertFalse(chain["nand_controller_direct_constraint_confirmed"])

    def test_weekly_004_hdd_signal_separates_toshiba_first_shipment_from_market_relief(self):
        signal = w.WEEKLY_004_LOCK["signals"]["HDD"]
        self.assertIn("HDD 50주", signal)
        self.assertIn("시장 완화가 빨라도 2027년 말", signal)
        self.assertIn("10/2 증설 nearline HDD 라인 첫 출하", signal)
        self.assertNotIn("가동까지 12~24개월이 필요", signal)


    def test_memory_storage_chain_alert_has_accuracy_boundary(self):
        components = w.WEEKLY_004_LOCK["components"]
        chain = w.memory_storage_chain_state(components, w.WEEKLY_004_LOCK["signals"])
        alert = w.build_memory_storage_chain_alert(
            chain,
            components,
            "https://insights.trendforce.com/p/weekly-radar-004",
        )
        self.assertIn("DRAM→기업용 SSD→HDD", alert)
        self.assertIn("DRAM", alert)
        self.assertIn("기업용 SSD", alert)
        self.assertIn("HDD", alert)
        self.assertIn("NAND 컨트롤러 출하가 DRAM 때문에 직접 제한된다는 주장은", alert)
        self.assertIn("10/2 Laguna 증설 nearline HDD 라인 첫 출하 완료", alert)
        self.assertIn("시장 전체 리드타임 정상화 전망", alert)
        self.assertIn("2H27부터 완화 가능성", alert)
        self.assertIn("기업용 SSD 병목을 전체 NAND", alert)
        self.assertIn("TrendForce 2027 NAND 수급 전망", alert)
        self.assertIn("20주", alert)
        self.assertIn("50주", alert)


    def test_official_source_always_outranks_secondary_recap(self):
        official = w.source_score(
            "https://insights.trendforce.com/p/weekly-radar-003",
            {"HDD": {"current": "50"}},
            "Weekly Radar",
        )
        secondary = w.source_score(
            "https://example.com/repost",
            {name: {"current": "1"} for name in w.ALIASES},
            "TrendForce Weekly Radar",
        )
        self.assertGreater(official, secondary)


    def test_cpu_lead_time_is_parsed_as_seventh_component(self):
        text = (
            "CPU current lead time 25-30 weeks against a balanced lead time of 16-20 weeks. "
            "CPU is Tight while GPU is Balanced."
        )
        rows = w.extract_components(text)
        self.assertEqual(rows["CPU"].get("current"), "25-30")
        self.assertEqual(rows["CPU"].get("balanced"), "16-20")
        self.assertEqual(rows["CPU"].get("status"), "Tight")

    def test_ubs_cross_stack_project_baseline_matches_attached_chart(self):
        base = w.UBS_PROJECT_LEADTIME_BASELINE
        self.assertFalse(base["directly_comparable_to_component_delivery_lead_time"])
        expected = {
            "Foundry": (36, 48),
            "Semicap equipment": (12, 24),
            "Adv. packaging / substrates": (12, 18),
            "Storage systems": (12, 24),
            "GPUs / AI accelerators": (6, 12),
            "Memory (HBM / DRAM)": (6, 12),
            "Optical transceivers / networking": (3, 9),
            "CPUs": (3, 6),
            "Servers": (1, 2),
        }
        for segment, (low, high) in expected.items():
            self.assertEqual(base["segments"][segment]["min_months"], low)
            self.assertEqual(base["segments"][segment]["max_months"], high)


    def test_newer_official_weekly_radar_beats_older_fuller_issue(self):
        older = {
            "direct_url": "https://insights.trendforce.com/p/weekly-radar-002",
            "published_at_kst": "2026-09-21T09:00:00+09:00",
            "score": 1100,
            "full_text": "TrendForce Weekly Radar",
        }
        newer = {
            "direct_url": "https://insights.trendforce.com/p/weekly-radar-003",
            "published_at_kst": "2026-09-28T09:00:00+09:00",
            "score": 1040,
            "full_text": "TrendForce Weekly Radar",
        }
        self.assertGreater(w.candidate_sort_key(newer), w.candidate_sort_key(older))



class Weekly006ScreenshotRegressionTests(unittest.TestCase):
    """TrendForce Oct 19 image and preserved Oct 12 state: no genuine easing."""

    def test_weekly_006_all_seven_rows_exactly_match_user_screenshot(self):
        issue = w.WEEKLY_006_LOCK
        self.assertEqual(issue["as_of"], "2026-10-19")
        self.assertEqual(issue["source"], "https://insights.trendforce.com/p/weekly-radar-006")
        self.assertEqual(len(issue["components"]), 7)
        expected = {
            "CPU": ("Tight", "25-30", "16-20"),
            "GPU": ("Balanced", "30-40", "30-40"),
            "DRAM": ("Very Tight", "20", "8"),
            "NAND(eSSD)": ("Tight", "16", "8"),
            "HDD": ("Very Tight", "50", "16"),
            "ABF": ("Very Tight", "48-56", "12"),
            "MLCC": ("Tight", "35", "12"),
        }
        for name, vals in expected.items():
            with self.subTest(name=name):
                self.assertEqual(w.canonical_component(issue["components"][name]), vals)

    def test_weekly_005_checkpoint_to_006_shows_zero_worsening_and_zero_easing(self):
        old, new = w.WEEKLY_005_ARCHIVED_COMPONENTS, w.WEEKLY_006_LOCK["components"]
        self.assertEqual(w.changed_components(old, new), [])
        self.assertEqual(w.supply_direction(old, new), ("→ 변화 제한", 0, 0))
        self.assertEqual(w.supply_direction_details(old, new), {
            "worse": [], "better": [], "uncertain": [],
        })

    def test_weekly_006_repair_changes_only_its_wrong_hdd_status(self):
        from copy import deepcopy
        previous = {
            "source": w.WEEKLY_006_LOCK["source"], "as_of": "2026-10-19",
            "components": deepcopy(w.WEEKLY_006_LOCK["components"]),
        }
        previous["components"]["HDD"]["status"] = "Tight"
        fixed, changes = w.repair_weekly_006_state(previous)
        self.assertEqual(changes, ["HDD"])
        self.assertEqual(fixed["components"]["HDD"]["status"], "Very Tight")
        self.assertEqual(fixed["components"]["HDD"]["current"], "50")
        self.assertEqual(w.repair_weekly_006_state(fixed)[1], [])
        self.assertEqual(fixed["image_verified_issue"], "weekly-radar-006")
        self.assertIn("2028년", fixed["signals"]["HDD"])
        correction = w.build_weekly_006_correction_alert(
            previous["components"], fixed["components"], changes,
        )
        self.assertIn("기존 알림의 ‘완화 1개’", correction)
        self.assertIn("완화 0개 (없음)", correction)
        self.assertIn("HDD", correction)
        self.assertIn("50주", correction)
        self.assertIn("완화 아님", correction)
        self.assertIn("2028년 장기계약", correction)
        self.assertIn("MLCC 35주/12주", correction)

    def test_weekly_006_outlook_extends_into_2028_without_claiming_shorter_hdd_lead(self):
        issue = w.WEEKLY_006_LOCK["components"]
        official = w.extract_signals(
            "HDD supply is tight into 2028 with 50-week lead times.",
            w.WEEKLY_006_LOCK["source"],
        )
        self.assertIn("2028년", official["HDD"])
        chain = w.memory_storage_chain_state(
            issue, {
                "NAND(eSSD)": "DRAM 부족이 일부 NAND 업체의 기업용 SSD 지원 능력까지 제약",
                "HDD": official["HDD"],
            }
        )
        self.assertTrue(chain["hdd_relief_late_2027_or_later"])
        self.assertTrue(chain["active"])
        self.assertEqual(issue["HDD"]["current"], "50")

    def test_weekly_006_repair_does_not_modify_007_or_old_vintages(self):
        from copy import deepcopy
        data = {
            "source": "https://insights.trendforce.com/p/weekly-radar-007",
            "components": deepcopy(w.WEEKLY_006_LOCK["components"]),
        }
        data["components"]["HDD"] = {"status": "Tight", "current": "44", "balanced": "16"}
        fixed, changes = w.repair_weekly_006_state(data)
        self.assertEqual(changes, [])
        self.assertEqual(fixed["components"]["HDD"]["current"], "44")
        data["source"] = "https://insights.trendforce.com/p/weekly-radar-005"
        fixed, changes = w.repair_weekly_006_state(data)
        self.assertEqual(changes, [])

    def test_status_only_narrative_does_not_promote_unverified_relief(self):
        old = w.WEEKLY_005_ARCHIVED_COMPONENTS
        merged, evidence = w.merge_verified_weekly_components(old, {
            "HDD": {"status": "Tight"},
        })
        self.assertEqual(merged["HDD"]["status"], "Very Tight")
        self.assertEqual(evidence.get("HDD"), None)
        self.assertEqual(w.supply_direction(old, merged)[1:], (0, 0))

    def test_full_official_row_can_confirm_status_only_relief_and_names_item(self):
        old = w.WEEKLY_005_ARCHIVED_COMPONENTS
        merged, evidence = w.merge_verified_weekly_components(old, {
            "HDD": {"status": "Tight", "current": "50", "balanced": "16"},
        })
        self.assertEqual(merged["HDD"]["status"], "Tight")
        self.assertEqual(evidence["HDD"], {"status", "current", "balanced"})
        label, worse, better = w.supply_direction(old, merged)
        self.assertEqual((worse, better), (0, 1))
        self.assertIn("HDD: 납기 50주 유지", w.supply_direction_details(old, merged)["better"][0])
        text = w.build_alert(
            old, merged, ["HDD"], w.WEEKLY_006_LOCK["source"],
            "2026-10-19T19:00:00+09:00", False,
        )
        self.assertIn("완화 1개 (HDD:", text)
        self.assertIn("심각한 공급 부족→공급 제약", text)

    def test_real_hdd_leadtime_improvement_names_item_and_weeks(self):
        from copy import deepcopy
        old = w.WEEKLY_005_ARCHIVED_COMPONENTS
        new = deepcopy(old)
        new["HDD"]["current"] = "46"
        self.assertEqual(w.supply_direction(old, new)[1:], (0, 1))
        msg = w.build_alert(
            old, new, ["HDD"], w.WEEKLY_006_LOCK["source"],
            "2026-10-19T19:00:00+09:00", False,
        )
        self.assertIn("완화 1개 (HDD: 50주→46주 (4주 단축))", msg)

    def test_balanced_benchmark_only_change_is_not_delivery_easing(self):
        from copy import deepcopy
        old = w.WEEKLY_005_ARCHIVED_COMPONENTS
        new = deepcopy(old)
        new["HDD"]["balanced"] = "20"
        self.assertEqual(w.supply_direction(old, new)[1:], (0, 0))
        new["HDD"]["balanced"] = "16"
        new["HDD"]["status"] = ""
        self.assertEqual(w.supply_direction(old, new)[1:], (0, 0))

    def test_conflicting_status_and_time_moves_is_held(self):
        from copy import deepcopy
        old = w.WEEKLY_005_ARCHIVED_COMPONENTS
        new = deepcopy(old)
        new["HDD"]["current"] = "54"
        new["HDD"]["status"] = "Tight"
        self.assertEqual(w.supply_component_direction(old["HDD"], new["HDD"]), "uncertain")
        self.assertEqual(w.supply_direction(old, new)[1:], (0, 0))
        msg = w.build_alert(
            old, new, ["HDD"], w.WEEKLY_006_LOCK["source"],
            "2026-10-19T19:00:00+09:00", False,
        )
        self.assertIn("방향 판정 보류", msg)
        self.assertIn("HDD", msg)

    def test_fake_official_domain_does_not_rank_above_real_trendforce(self):
        trusted = "https://insights.trendforce.com/p/weekly-radar-006"
        spoof = "https://some-trendforce.com/p/weekly-radar-006"
        self.assertEqual(w.source_tier(trusted), 3)
        self.assertNotEqual(w.source_tier(spoof), 3)
        self.assertGreater(w.source_score(trusted, {}, ""), w.source_score(spoof, {}, ""))

    def test_existing_upstream_pending_state_is_preserved(self):
        from copy import deepcopy
        with tempfile.TemporaryDirectory() as tmp:
            root = pathlib.Path(tmp)
            state = root / "rubin.json"
            pending = root / "pending.json"
            alert = root / "alert.md"
            snapshot = {
                "source": w.WEEKLY_006_LOCK["source"],
                "as_of": "2026-10-19",
                "components": deepcopy(w.WEEKLY_006_LOCK["components"]),
                "signals": {"HDD": w.WEEKLY_006_HDD_OUTLOOK},
            }
            state.write_text(json.dumps({
                "ai_component_leadtime": snapshot,
                "telegram_message_id": 308,
            }, ensure_ascii=False), encoding="utf-8")
            pending.write_text(json.dumps({
                "telegram_message_id": 308,
                "upstream_collector_update": {"preserve": "yes"},
            }, ensure_ascii=False), encoding="utf-8")
            with mock.patch.object(w, "STATE_PATH", state), \
                 mock.patch.object(w, "PENDING_PATH", pending), \
                 mock.patch.object(w, "ALERT_PATH", alert), \
                 mock.patch.object(w, "read_rss", return_value=[]):
                w.main()
                actual = json.loads(pending.read_text(encoding="utf-8"))
                self.assertEqual(actual["upstream_collector_update"]["preserve"], "yes")
                self.assertEqual(actual["telegram_message_id"], 308)
                self.assertEqual(actual["ai_component_leadtime"]["components"]["HDD"]["status"], "Very Tight")

    def test_existing_rubin_state_and_delivery_route_unchanged_after_one_correction(self):
        from copy import deepcopy
        with tempfile.TemporaryDirectory() as tmp:
            root = pathlib.Path(tmp)
            state_file = root / "rubin_hbm_watch_state.json"
            pending = root / "rubin_hbm_pending_state.json"
            alert = root / "rubin_hbm_alert.md"
            bad = {
                "as_of": "2026-10-19",
                "source": w.WEEKLY_006_LOCK["source"],
                "components": deepcopy(w.WEEKLY_006_LOCK["components"]),
                "signals": {"HDD": "에이전틱 AI 수요 증가 → HDD 공급 압박 지속"},
                "seen_urls": [w.WEEKLY_006_LOCK["source"]],
            }
            bad["components"]["HDD"]["status"] = "Tight"
            original = {
                "ai_component_leadtime": bad,
                "last_successful_delivery_kst": "2026-10-19T20:04:28+09:00",
                "telegram_message_id": 308,
                "unrelated_existing_route": {"do_not_touch": True},
            }
            state_file.write_text(json.dumps(original, ensure_ascii=False), encoding="utf-8")
            with mock.patch.object(w, "STATE_PATH", state_file), \
                 mock.patch.object(w, "PENDING_PATH", pending), \
                 mock.patch.object(w, "ALERT_PATH", alert), \
                 mock.patch.object(w, "read_rss", return_value=[]):
                w.main()
                text = alert.read_text(encoding="utf-8")
                self.assertIn("완화 0개 (없음)", text)
                snapshot = json.loads(pending.read_text(encoding="utf-8"))
                self.assertEqual(snapshot["ai_component_leadtime"]["components"]["HDD"]["status"], "Very Tight")
                self.assertEqual(snapshot["telegram_message_id"], 308)
                self.assertEqual(snapshot["unrelated_existing_route"], {"do_not_touch": True})
                # Emulate the existing delivery path's confirmed state checkpoint.
                state_file.write_text(json.dumps(snapshot, ensure_ascii=False), encoding="utf-8")
                alert.unlink(missing_ok=True)
                w.main()
                self.assertFalse(alert.exists())


class VendorMLCCAndCASPAGuards(unittest.TestCase):
    def test_vendor_report_not_merged_into_trendforce_average(self):
        data = w.MLCC_VENDOR_BASELINE
        self.assertEqual((data["maker_weeks"], data["channel_max_weeks"]), (52, 61))
        self.assertEqual(w.WEEKLY_006_LOCK["components"]["MLCC"]["current"], "35")
        self.assertEqual(data["official_2027_lta_krw"], 1072200000000)

    def test_first_vendor_alert_has_source_separation_and_contract(self):
        state, events = w.mlcc_vendor_update({}, [])
        self.assertEqual([e["kind"] for e in events], ["initial"])
        msg = w.mlcc_vendor_notice(events[0], state, w.WEEKLY_006_LOCK["components"])
        for p in ("52주", "61주", "35주", "+17주", "+22주", "FC-BGA", "1조 722억원"):
            self.assertIn(p, msg)
        state2, e2 = w.mlcc_vendor_update(state, [])
        self.assertEqual(e2, [])
        self.assertEqual(state2["maker_weeks"], 52)


    def test_philippines_factory_official_july_2027_not_after_2027(self):
        factory = w.MLCC_VENDOR_BASELINE["philippines_factory"]
        self.assertEqual(factory["official_government_goal"], "2027-07")
        self.assertEqual(factory["official_scope"], "전장용 MLCC 신설시설")
        self.assertEqual(factory["later_report_earliest"], "2027-Q1말")
        self.assertFalse(factory["ai_grade_customer_mass_production_verified"])
        self.assertIn("pco.gov.ph", factory["source_url"])

    def test_version_one_state_migration_preserves_quotes_and_corrects_once(self):
        prev = {
            "version": 1, "maker_weeks": 52, "channel_max_weeks": 61,
            "seen_facts": ["maker|52|2026-10-25"],
            "unique_existing_setting": "do not delete",
        }
        new, events = w.mlcc_vendor_update(prev, [])
        self.assertEqual([x["kind"] for x in events], ["philippines_timing_correction"])
        self.assertEqual(new["maker_weeks"], 52)
        self.assertEqual(new["channel_max_weeks"], 61)
        self.assertEqual(new["seen_facts"], prev["seen_facts"])
        self.assertEqual(new["unique_existing_setting"], prev["unique_existing_setting"])
        self.assertEqual(new["version"], w.MLCC_VENDOR_VERSION)
        notice = w.mlcc_vendor_notice(events[0], new, {})
        self.assertIn("2027년 7월까지", notice)
        self.assertIn("2027년 1분기 말", notice)
        self.assertIn("전장용", notice)
        self.assertIn("AI용", notice)
        quiet, repeated = w.mlcc_vendor_update(new, [])
        self.assertEqual(repeated, [])
        self.assertEqual(quiet, new)

    def test_untrusted_or_old_supplier_article_never_upgrades(self):
        item = {"title": "Samsung Electro Mechanics MLCC lead time 60 weeks",
                "published_at_kst": "2026-10-24T06:00:00+09:00",
                "direct_url": "https://www.digitimes.com.tw/tech/new"}
        self.assertIsNone(w.mlcc_vendor_new_fact(item))
        item["published_at_kst"] = "2026-10-27T06:00:00+09:00"
        item["direct_url"] = "https://digitimes.com.tw.fake.example/post"
        self.assertIsNone(w.mlcc_vendor_new_fact(item))

    def test_vendor_quote_material_change_only_with_named_source(self):
        state, _ = w.mlcc_vendor_update({}, [])
        source = "https://www.digitimes.com.tw/tech/new"
        item = {"title": "Samsung Electro Mechanics MLCC lead time 60 weeks",
                "published_at_kst": "2026-10-27T06:00:00+09:00",
                "direct_url": source}
        updated, events = w.mlcc_vendor_update(state, [item])
        self.assertEqual(len(events), 1)
        self.assertEqual(updated["maker_weeks"], 60)
        self.assertIn("52주 → 60주", w.mlcc_vendor_notice(events[0], updated, {}))
        _, repeat = w.mlcc_vendor_update(updated, [item])
        self.assertEqual(repeat, [])

    def test_vendor_channel_max_does_not_raise_maker_to_70(self):
        state, _ = w.mlcc_vendor_update({}, [])
        item = {"title": "Samsung Electro Mechanics MLCC distributor lead time 70 weeks",
                "published_at_kst": "2026-10-27T06:00:00+09:00",
                "direct_url": "https://www.digitimes.com.tw/tech/new"}
        modified, events = w.mlcc_vendor_update(state, [item])
        self.assertEqual(len(events), 1)
        self.assertEqual(modified["maker_weeks"], 52)
        self.assertEqual(modified["channel_max_weeks"], 70)

    def test_caspa_correction_and_company_link_one_time(self):
        state, text = w.caspa_panel_update({}, {"rate": 1324.6})
        self.assertIn("3~4배", text)
        self.assertIn("'34배'", text)
        self.assertIn("Sharon AI", text)
        self.assertIn("400억달러(약", text)
        self.assertIn("600억달러 이상(약", text)
        self.assertIn("200억달러(약", text)
        self.assertEqual(state["version"], 2)
        state2, alert2 = w.caspa_panel_update(state, {"rate": 1324.6})
        self.assertEqual(alert2, "")
        self.assertEqual(state2, state)

    def test_caspa_previous_delivery_version_one_migrates_once_without_reposting_old_costs(self):
        previous = {
            "version": 1, "as_of": "2026-10-23",
            "source_url": w.CASPA_ORIGINAL_URL,
            "wafer_hbm_relative_ddr5_min": 3, "wafer_hbm_relative_ddr5_max": 4,
            "existing_user_setting": "must_not_delete",
        }
        updated, note = w.caspa_panel_update(previous, {"rate": 1324.6})
        self.assertEqual(updated["version"], 2)
        self.assertEqual(updated["existing_user_setting"], "must_not_delete")
        self.assertTrue(updated["power_constraint_exists"])
        self.assertFalse(updated["memory_total_output_decline_unconditional"])
        self.assertTrue(updated["nvidia_can_gain_absolute_profit_despite_losing_component_spend_share"])
        self.assertIn("기판", note)
        self.assertIn("전력", note)
        self.assertIn("조건부", note)
        self.assertIn("2027년 일부", note)
        self.assertIn("CASPA 영상", note)
        self.assertNotIn("400억달러", note)
        same, repeat = w.caspa_panel_update(updated, {"rate": 1324.6})
        self.assertEqual(repeat, "")
        self.assertEqual(same, updated)

    def test_caspa_context_cannot_be_mistaken_for_company_capex_guidance(self):
        state, _ = w.caspa_panel_update({}, {"rate": 1324.6})
        self.assertEqual(state["source_kind"], "2026-10-23 CASPA participant statements; not company guidance")
        self.assertEqual(state["bottleneck_ranking"], ["패키지기판·PCB 소재", "메모리", "광결합·레이저"])
        self.assertTrue(state["power_on_site_generation_partial_workaround_not_universal"])
        self.assertTrue(state["neocloud_debt_risk_not_eliminated_by_offtake"])
        self.assertEqual(state["video_url"], "https://www.youtube.com/watch?v=NXv0qvam9yg")

    def test_caspa_without_fx_omits_unconverted_usd_amounts(self):
        _, text = w.caspa_panel_update({}, {})
        self.assertNotIn("400억달러", text)
        self.assertIn("환율 검증 실패", text)

class LeadTimeAlertTests(unittest.TestCase):
    def setUp(self):
        self.old = {
            "GPU": {"status": "Balanced", "current": "20-30", "balanced": "20-30"},
            "DRAM": {"status": "Very Tight", "current": "20", "balanced": "8"},
            "NAND(eSSD)": {"status": "Tight", "current": "16", "balanced": "8"},
            "HDD": {"status": "Very Tight", "current": "50", "balanced": "16"},
            "ABF": {"status": "Very Tight", "current": "48-56", "balanced": "12"},
            "MLCC": {"status": "Tight", "current": "30", "balanced": "12"},
        }
        self.new = {
            "GPU": {"status": "Balanced", "current": "30-40", "balanced": "30-40"},
            "DRAM": {"status": "Very Tight", "current": "20", "balanced": "8"},
            "NAND(eSSD)": {"status": "Tight", "current": "16", "balanced": "8"},
            "HDD": {"status": "Very Tight", "current": "50", "balanced": "16"},
            "ABF": {"status": "Very Tight", "current": "48-56", "balanced": "12"},
            "MLCC": {"status": "Tight", "current": "32", "balanced": "12"},
        }

    def test_alert_is_compact_and_keeps_all_current_numbers(self):
        alert = w.build_alert(
            self.old,
            self.new,
            ["GPU", "MLCC"],
            "https://insights.trendforce.com/p/weekly-radar-002",
            "2026-09-21T19:01:52+09:00",
            False,
            signals=w.BASELINE["signals"],
            changed_signals=["GPU", "MLCC"],
            evidence={name: {"status", "current", "balanced"} for name in self.new},
        )
        self.assertIn("<b>핵심 변화</b>", alert)
        self.assertIn("<b>현재 숫자</b>", alert)
        self.assertIn("<b>미래 재평가</b>", alert)
        self.assertIn("<b>관련 기업</b>", alert)
        self.assertIn("<b>역풍·다음 확인</b>", alert)
        self.assertIn("ABF 48~56주/12주 (4.3배)", alert)
        self.assertIn("HDD 50주/16주 (3.1배)", alert)
        self.assertIn("DRAM 20주/8주 (2.5배)", alert)
        self.assertIn("NAND(eSSD) 16주/8주 (2.0배)", alert)
        self.assertIn("MLCC 32주/12주 (2.7배)", alert)
        self.assertIn("GPU 30~40주/30~40주 (1.0배)", alert)
        self.assertIn("삼성전기·Ibiden·Unimicron·Nan Ya PCB", alert)
        self.assertNotIn("<b>수익구조</b>", alert)
        self.assertNotIn("<b>공정 병목 후보</b>", alert)
        self.assertNotIn("<b>추적 기준</b>", alert)
        self.assertLess(len(alert), 2400)

    def test_unverified_status_is_labeled_not_silently_claimed(self):
        evidence = {name: {"current", "balanced"} for name in self.new}
        alert = w.build_alert(
            self.old,
            self.new,
            [],
            "https://insights.trendforce.com/p/weekly-radar-003",
            "2026-09-28T09:00:00+09:00",
            True,
            evidence=evidence,
        )
        self.assertIn("이전 확정값 유지:", alert)
        self.assertNotIn("직전 확정값 유지·이번 주 직접 판독 미확인", alert)


    def test_cpu_change_shows_ubs_project_horizon_without_equating_metrics(self):
        old = dict(self.new)
        new = dict(self.new)
        new["CPU"] = {"status": "Tight", "current": "25-30", "balanced": "16-20"}
        alert = w.build_alert(
            old,
            new,
            ["CPU"],
            "https://insights.trendforce.com/p/weekly-radar-003",
            "2026-09-28T09:00:00+09:00",
            False,
            signals={"CPU": "에이전틱 AI·CSP 인하우스 설계 확대로 서버 CPU 조달 압력이 부각"},
            changed_signals=["CPU"],
            evidence={"CPU": {"status", "current", "balanced"}},
        )
        self.assertIn("<b>신규 추적 CPU:</b> 25~30주 / 균형 16~20주 / 공급 제약", alert)
        self.assertIn("UBS 프로젝트 기준", alert)
        self.assertIn("CPU 3~6개월", alert)
        self.assertIn("직접 비교 금지", alert)
        direction, worse, better = w.supply_direction(old, new)
        self.assertEqual((direction, worse, better), ("→ 변화 제한", 0, 0))


    def test_combined_leadtime_and_cpu_alert_fits_one_telegram_chunk(self):
        old = dict(self.new)
        new = dict(self.new)
        new["CPU"] = {"status": "Tight", "current": "25-30", "balanced": "16-20"}
        lead = w.build_alert(
            old,
            new,
            ["CPU"],
            "https://insights.trendforce.com/p/weekly-radar-003",
            "2026-09-28T19:03:30+09:00",
            False,
            signals={"CPU": "에이전틱 AI·CSP 인하우스 설계 확대로 서버 CPU 조달 압력이 부각"},
            changed_signals=["CPU"],
            evidence={"CPU": {"status", "current", "balanced"}},
        )
        cpu = cpuw.snapshot_block(
            cpuw.BASELINE,
            1348.3,
            "2026-10-02",
            [{"key": "server_cpu_tam_2030_usd_bn", "label": "2030 서버 CPU 시장", "before": 190.0, "after": 210.6, "delta": 10.8, "mode": "pct"}],
            None,
            [{"title": "AMD confirms higher CPU intensity for agentic AI"}],
            standalone=False,
        )
        combined = lead.rstrip() + "\n\n" + cpu.strip()
        utf16_units = len(combined.encode("utf-16-le")) // 2
        self.assertLess(utf16_units, 3300)
        for verbose_heading in (
            "<b>수익구조</b>",
            "<b>공정 병목 후보</b>",
            "<b>숨은 역풍·실패모드</b>",
            "<b>알림 기준</b>",
            "<b>추적 기준</b>",
        ):
            self.assertNotIn(verbose_heading, combined)


if __name__ == "__main__":
    unittest.main()
