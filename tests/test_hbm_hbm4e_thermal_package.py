import copy
import pathlib
import sys
import tempfile
import unittest
from unittest.mock import patch
from datetime import datetime
from zoneinfo import ZoneInfo

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "scripts"))
import rubin_hbm_watch as w
import rubin_hbm_pretty as pretty
import rubin_hbm_leverage as leverage
import hbm_delivery as delivery
import re


class SamsungHBM4EThermalPackageWatchTests(unittest.TestCase):
    def event(self, text):
        return {
            "category": "hbm4e_thermal_package",
            "title": text,
            "description": "",
            "article_title": "",
            "article_description": "",
            "article_text": text,
            "source": "조선비즈",
            "origin_source": "조선비즈",
            "published_at_kst": "2026-10-02T15:21:00+09:00",
            "direct_link": "https://biz.chosun.com/it-science/ict/2026/10/02/MHAFNCALYJDI5P3MKV3F3MXINE/?outputType=amp",
        }

    def test_current_article_stays_at_seeded_baseline(self):
        text = (
            "삼성전자 HBM4E 발열 대응. 현재 AI 반도체용 인터포저 크기는 EUV 최대 면적의 5.5배 수준이다. "
            "인터포저가 9배, 12배를 거쳐 40배까지 확대될 것으로 보인다. "
            "삼성전자는 HCB를 GTC 2026에서 소개했다. "
            "패키지와 서버 시스템 단위의 냉각 기술 도입 가능성도 검토하고 있다."
        )
        obs = w.extract_samsung_hbm4e_thermal_package(self.event(text))
        self.assertIsNotNone(obs)
        self.assertEqual(obs["industry_current_interposer_reticle_x"], 5.5)
        self.assertEqual(obs["reported_future_interposer_reticle_x"], 40.0)
        self.assertEqual(obs["reported_future_interposer_stage"], "industry_projection")
        self.assertEqual(obs["hcb_stage"], "technology_showcase")
        self.assertEqual(obs["package_system_cooling_stage"], "reported_review")

        merged = w.merge_samsung_hbm4e_thermal_package(dict(w.SAMSUNG_HBM4E_THERMAL_BASELINE), obs)
        self.assertEqual(w.samsung_hbm4e_thermal_changes(w.SAMSUNG_HBM4E_THERMAL_BASELINE, merged), [])

    def test_interposer_current_size_change_alerts(self):
        old = dict(w.SAMSUNG_HBM4E_THERMAL_BASELINE)
        new = dict(old, industry_current_interposer_reticle_x=9.0)
        reasons = w.samsung_hbm4e_thermal_changes(old, new)
        self.assertTrue(any("현재 인터포저 면적" in x and "5.5" in x and "9" in x for x in reasons))

    def test_hcb_mass_production_is_stage_upgrade(self):
        obs = w.extract_samsung_hbm4e_thermal_package(self.event(
            "삼성전자 HBM4E 양산에 HCB 하이브리드 본딩을 적용한다. 발열과 열저항을 낮춘다."
        ))
        self.assertEqual(obs["hcb_stage"], "hbm4e_mass_production")
        old = dict(w.SAMSUNG_HBM4E_THERMAL_BASELINE)
        new = w.merge_samsung_hbm4e_thermal_package(old, obs)
        reasons = w.samsung_hbm4e_thermal_changes(old, new)
        self.assertTrue(any("HCB 단계" in x and "hbm4e_mass_production" in x for x in reasons))

    def test_hpb_validation_and_hbm5_target_are_not_hbm4e_mass_production(self):
        obs = w.extract_samsung_hbm4e_thermal_package(self.event(
            "삼성전자 HBM4E 기반으로 HPB Heat Path Block 기술을 검증 중이며 HBM5부터 적용할 계획이다."
        ))
        self.assertEqual(obs["hpb_stage"], "hbm4e_validation")
        self.assertEqual(obs["hpb_target_generation"], "hbm5")
        self.assertNotEqual(obs["hpb_stage"], "hbm4e_mass_production")

    def test_system_cooling_adoption_alerts(self):
        obs = w.extract_samsung_hbm4e_thermal_package(self.event(
            "삼성전자 HBM4E 패키지와 서버 시스템 단위 냉각 기술을 실제 양산 시스템에 도입한다."
        ))
        self.assertEqual(obs["package_system_cooling_stage"], "adopted")
        old = dict(w.SAMSUNG_HBM4E_THERMAL_BASELINE)
        new = w.merge_samsung_hbm4e_thermal_package(old, obs)
        reasons = w.samsung_hbm4e_thermal_changes(old, new)
        self.assertTrue(any("패키지·시스템 냉각 단계" in x and "adopted" in x for x in reasons))


class HybridHBMSourceGuardTests(unittest.TestCase):
    def event(self, body, *, domain="https://news.skhynix.com/en/example", published="2026-10-08T13:00:00+09:00"):
        return {
            "title": "HBM hybrid bonding update",
            "article_title": "HBM hybrid bonding update",
            "article_description": "",
            "article_text": body,
            "article_fetch_succeeded": True,
            "official_article_title": "",
            "official_article_description": "",
            "official_article_text": body,
            "source": "Manufacturer",
            "direct_link": domain,
            "published_at_kst": published,
        }

    def test_single_anonymous_interview_and_republication_are_not_official(self):
        base = w.HBM_HYBRID_BOND_BASELINE
        self.assertEqual(base["reported_origin"], "Damnang")
        self.assertEqual(base["reported_origin_count"], 1)
        self.assertTrue(base["reported_sk_hybrid_customer_sample_not_started"])
        self.assertTrue(base["reported_samsung_hybrid_customer_sample_sent"])
        self.assertFalse(base["skhynix_official_hybrid_customer_sample_verified"])
        self.assertFalse(base["samsung_official_hybrid_customer_sample_verified"])
        self.assertTrue(base["sk_hbm4e_mr_muf_sample_shipped"])
        self.assertEqual(base["sk_revenue_share_q2_2026_pct"], 50.0)
        self.assertEqual(base["samsung_revenue_share_q2_2026_pct"], 33.0)
        story = self.event(
            "Samsung HBM hybrid bonding samples shipped to customers",
            domain=w.HBM_HYBRID_BOND_REPUBLISHER,
        )
        self.assertIsNone(w.extract_hbm_hybrid_official_observation(story))

    def test_existing_mr_muf_hbm4e_samples_are_not_hybrid_samples(self):
        text = (
            "SK hynix shipped HBM4E samples to customers using Advanced MR-MUF. "
            "Hybrid bonding technology is being developed for next-generation HBM."
        )
        self.assertIsNone(w.extract_hbm_hybrid_official_observation(self.event(text)))
        same_sentence = (
            "SK hynix HBM4E MR-MUF samples shipped to customers, while hybrid bonding "
            "technology is still under development."
        )
        self.assertIsNone(w.extract_hbm_hybrid_official_observation(self.event(same_sentence)))

    def test_customer_sample_mentioned_in_company_page_is_not_automatic_hybrid_proof(self):
        text = (
            "Samsung Electronics has shipped HBM4E samples to customers. "
            "Hybrid bonding was displayed for future HBM applications."
        )
        self.assertIsNone(w.extract_hbm_hybrid_official_observation(
            self.event(text, domain="https://news.samsung.com/global/example")
        ))

    def test_official_direct_hybrid_hbm_customer_sample_is_material(self):
        official = self.event(
            "SK hynix shipped hybrid bonding HBM samples to major customers.",
        )
        obs = w.extract_hbm_hybrid_official_observation(official)
        self.assertIsNotNone(obs)
        self.assertEqual(obs["vendor"], "skhynix")
        self.assertEqual(obs["stage"], "customer_hbm_sample_shipped")
        old = dict(w.HBM_HYBRID_BOND_BASELINE)
        merged = w.merge_hbm_hybrid_official_observation(old, obs)
        self.assertTrue(merged["skhynix_official_hybrid_customer_sample_verified"])
        self.assertFalse(merged["samsung_official_hybrid_customer_sample_verified"])
        self.assertEqual(len(w.hbm_hybrid_official_changes(old, merged)), 1)
        self.assertEqual(w.hbm_hybrid_official_changes(merged, w.merge_hbm_hybrid_official_observation(merged, obs)), [])

    def test_samsung_customer_sample_not_customer_qualification(self):
        obs = w.extract_hbm_hybrid_official_observation(self.event(
            "Samsung shipped hybrid bonding HBM samples to customers.",
            domain="https://news.samsung.com/global/example",
        ))
        self.assertIsNotNone(obs)
        self.assertEqual(obs["stage"], "customer_hbm_sample_shipped")
        out = w.merge_hbm_hybrid_official_observation(w.HBM_HYBRID_BOND_BASELINE, obs)
        self.assertTrue(out["samsung_official_hybrid_customer_sample_verified"])
        self.assertNotEqual(out["samsung_official_hybrid_stage"], "customer_qualification_passed")

    def test_planned_or_denied_milestone_cannot_upgrade(self):
        for text in (
            "SK hynix will ship hybrid bonding HBM samples to customers.",
            "SK hynix has not yet shipped hybrid bonding HBM samples to customers.",
            "No hybrid bonding HBM samples have been shipped to customers.",
            "SK hynix HBM 하이브리드 본딩 고객 샘플 출하 예정.",
            "SK hynix HBM 하이브리드 본딩 샘플은 아직 고객사에 전달되지 않았습니다.",
        ):
            with self.subTest(text=text):
                self.assertIsNone(w.extract_hbm_hybrid_official_observation(self.event(text)))

    def test_lower_evidence_or_lower_stage_never_overwrites_official(self):
        old = dict(w.HBM_HYBRID_BOND_BASELINE, skhynix_official_hybrid_stage="customer_hbm_sample_shipped")
        self.assertEqual(w.merge_hbm_hybrid_official_observation(old, {
            "vendor":"skhynix","stage":"hbm_mass_production_started",
            "evidence":"reported","source_url":"https://example.com/rumor"
        }), old)
        self.assertEqual(w.merge_hbm_hybrid_official_observation(old, {
            "vendor":"skhynix","stage":"internal_hbm_prototype",
            "evidence":"official","source_url":"https://news.skhynix.com/en/example"
        }), old)


    def test_official_site_quoting_competitor_cannot_promote_host_issuer(self):
        for host, sentence in (
            ("https://news.skhynix.com/en/competitor",
             "Samsung Electronics shipped hybrid bonding HBM samples to customers."),
            ("https://news.samsung.com/global/competitor",
             "SK hynix shipped hybrid bonding HBM samples to customers."),
            ("https://news.skhynix.com/en/both",
             "SK hynix and Samsung discussed that Samsung shipped hybrid bonding HBM samples to customers."),
        ):
            with self.subTest(host=host):
                self.assertIsNone(w.extract_hbm_hybrid_official_observation(
                    self.event(sentence, domain=host)
                ))

    def test_official_site_headline_is_not_article_body_proof(self):
        reported = self.event(
            "SK hynix has shipped hybrid bonding HBM samples to customers.",
        )
        reported["article_fetch_succeeded"] = False
        self.assertIsNone(w.extract_hbm_hybrid_official_observation(reported))
        reported["article_fetch_succeeded"] = True
        reported["official_article_text"] = "<html>Access denied</html>"
        self.assertIsNone(w.extract_hbm_hybrid_official_observation(reported))

    def test_enrichment_fetch_failure_does_not_forge_official_evidence(self):
        rss = {
            "id": "test", "title": "SK hynix hybrid bonding HBM samples shipped to customers",
            "description": "Claimed on a news aggregator", "source": "SK hynix",
            "link": "https://news.skhynix.com/en/sample",
            "published_at_kst": "2026-10-08T16:00:00+09:00",
        }
        with patch.object(w, "fetch", side_effect=TimeoutError("unavailable")):
            enriched = w.enrich_event(rss)
        self.assertTrue(enriched["link_verified"])
        self.assertFalse(enriched["article_fetch_succeeded"])
        self.assertIsNone(w.extract_hbm_hybrid_official_observation(enriched))

    def test_merge_must_validate_official_issuer_host(self):
        old = dict(w.HBM_HYBRID_BOND_BASELINE)
        fake = {
            "vendor": "samsung", "stage": "hbm_mass_production_started",
            "source_url": "https://news.skhynix.com/en/sk-announcement",
            "evidence": "official",
        }
        self.assertEqual(w.merge_hbm_hybrid_official_observation(old, fake), old)

    def test_separate_official_vendors_get_unique_evidence_links(self):
        state = dict(w.HBM_HYBRID_BOND_BASELINE)
        state.update({
            "skhynix_official_hybrid_stage": "customer_hbm_sample_shipped",
            "skhynix_official_stage_source_url": "https://news.skhynix.com/en/sk-original",
            "samsung_official_hybrid_stage": "customer_qualification_passed",
            "samsung_official_stage_source_url": "https://news.samsung.com/global/samsung-original",
            "last_official_stage_change_at": "2026-10-08T15:30:00+09:00",
        })
        sk = w.hbm_hybrid_bond_event(state, ["SK하이닉스 실제 고객 샘플"], vendor="skhynix")
        sam = w.hbm_hybrid_bond_event(state, ["삼성전자 고객 승인"], vendor="samsung")
        self.assertNotEqual(sk["fact_key"], sam["fact_key"])
        self.assertEqual(sk["direct_link"], state["skhynix_official_stage_source_url"])
        self.assertEqual(sam["direct_link"], state["samsung_official_stage_source_url"])
        now = datetime(2026, 10, 8, 19, tzinfo=ZoneInfo("Asia/Seoul"))
        raw = w.build_alert(now, [sk, sam], {"rate":1400.0,"date":"2026-10-08"})
        with tempfile.TemporaryDirectory() as tmp:
            f = pathlib.Path(tmp) / "alert.md"
            f.write_text(raw, encoding="utf-8")
            with patch.object(pretty, "ALERT", f), patch.object(leverage, "ALERT", f):
                pretty.main()
                leverage.main()
                formatted = f.read_text(encoding="utf-8")
            parts = delivery.chunks(formatted)
            # Both vendors have advanced beyond the technology-showcase stages.
            # The final send gate must accept real official improvements.
            self.assertIsNone(delivery.validate_rubin_hybrid_notification(formatted))
        self.assertEqual(len(parts), 2)
        self.assertIn("https://news.skhynix.com/en/sk-original", parts[0])
        self.assertNotIn("https://news.samsung.com/global/samsung-original", parts[0])
        self.assertIn("https://news.samsung.com/global/samsung-original", parts[1])
        self.assertNotIn("https://news.skhynix.com/en/sk-original", parts[1])
        self.assertIn("원문 보기", parts[0])
        self.assertIn("원문 보기", parts[1])

    def test_report_notice_is_labelled_reported_and_telegram_safe(self):
        event = w.hbm_hybrid_bond_event(w.HBM_HYBRID_BOND_BASELINE, ["보도 최초"], initial=True)
        now = datetime(2026, 10, 8, 16, 4, tzinfo=ZoneInfo("Asia/Seoul"))
        text = w.build_alert(now, [event], {"rate":1400.0,"date":"2026-10-08"})
        self.assertIn("단일 익명 전문가", text)
        self.assertIn("회사 공식", text)
        self.assertIn("MR-MUF", text)
        self.assertIn("샘플 제작 지연 주장", text)
        self.assertIn("0.99^16≈85.1%", text)
        self.assertIn(w.HBM_HYBRID_BOND_PRIMARY, text)
        self.assertIn(w.HBM_HYBRID_BOND_REPUBLISHER, text)
        self.assertNotIn("양산 공급 확정", text)
        import hbm_delivery as delivery
        self.assertTrue(delivery.chunks(text))

    def test_initial_migration_once_then_no_repeat_on_same_information(self):
        memory = {"saved": {"seen_ids":[],"seen_fact_keys":[], "structure_baseline_version":w.STRUCTURE_BASELINE_VERSION}}
        def load():
            return copy.deepcopy(memory["saved"]), False
        def fake_json(path, value):
            if "rubin_hbm_pending_state.json" in str(path):
                memory["saved"].update(copy.deepcopy(value))
        with tempfile.TemporaryDirectory() as temp:
            out = pathlib.Path(temp)
            with (
                patch.object(w, "OUT", out),
                patch.object(w, "load_state", side_effect=load),
                patch.object(w, "read_feed", return_value=([],[])),
                patch.object(w, "fetch_fx", return_value={"rate":1400.0,"date":"2026-10-08","error":""}),
                patch.object(w, "write_json", side_effect=fake_json),
            ):
                w.main()
                first = (out / "rubin_hbm_alert.md").read_text(encoding="utf-8")
                self.assertIn("단일 익명 전문가", first)
                self.assertEqual(memory["saved"]["hbm_hybrid_bond_track_version"], w.HBM_HYBRID_BOND_TRACK_VERSION)
                self.assertEqual(memory["saved"]["last_send_event_count"], 1)
                w.main()
                self.assertEqual(memory["saved"]["last_send_event_count"], 0)
                self.assertEqual(memory["saved"]["hbm_hybrid_bond_track_version"], w.HBM_HYBRID_BOND_TRACK_VERSION)



class HybridTelegramPresentationTests(unittest.TestCase):
    def _render_pipeline(self, events):
        now = datetime(2026, 10, 8, 16, 20, tzinfo=ZoneInfo("Asia/Seoul"))
        raw = w.build_alert(now, events, {"rate":1400.0,"date":"2026-10-08"})
        with tempfile.TemporaryDirectory() as temp:
            p = pathlib.Path(temp) / "rubin_hbm_alert.md"
            p.write_text(raw, encoding="utf-8")
            with (
                patch.object(pretty, "ALERT", p),
                patch.object(leverage, "ALERT", p),
            ):
                pretty.main()
                leverage.main()
                formatted = p.read_text(encoding="utf-8")
        return raw, formatted, delivery.chunks(formatted)

    def test_missing_rubin_metadata_does_not_create_fake_change_headline(self):
        with self.assertRaisesRegex(ValueError, "missing required timestamp/count"):
            pretty.format_generic_alert(
                "🚨 Rubin/HBM 구조 변화 감시\n■ HBM4E 고객 검증·양산\n"
                "1. 검증 단계 기사\n• 판정: 공식 미확인"
            )
        # Missing metadata may not be replaced by a misleading fake count.
        good = pretty.format_generic_alert(
            "🚨 Rubin/HBM 구조 변화 감시\n"
            "조회시각: 2026-10-08 19:40:00 KST\n"
            "신규 핵심 변화: 1건\n"
            "■ HBM4E 고객 검증·양산\n"
            "1. HBM4E 단계 변화\n• 판정: 확인 필요"
        )
        self.assertIn("1건", good)
        self.assertNotIn("신규 변화 <b>확인 불가</b>", good)

    def test_irrelevant_generic_hbm_notice_does_not_get_unrelated_leverage(self):
        with tempfile.TemporaryDirectory() as temp:
            p = pathlib.Path(temp) / "rubin_alert.md"
            plain = (
                "<b>🚨 Rubin/HBM 구조 변화 감시</b>\n"
                "<b>■ HBM4E 고객 검증·양산</b>\n"
                "• 기술 검증 상태 변경\n"
            )
            p.write_text(plain, encoding="utf-8")
            with patch.object(leverage, "ALERT", p):
                leverage.main()
            out = p.read_text(encoding="utf-8")
            self.assertNotIn("[HBM 수요·가격 레버리지]", out)
            self.assertIn("기술 검증 상태 변경", out)

    def test_actual_hybrid_report_has_no_generic_rubin_wrapper(self):
        state = dict(w.HBM_HYBRID_BOND_BASELINE)
        event = w.hbm_hybrid_bond_event(
            state, ["표기 정정(같은 보도, 신규 기술 진전 아님)"], initial=True
        )
        event["format_correction"] = True
        raw, formatted, parts = self._render_pipeline([event])
        self.assertIn("🚨 HBM 하이브리드 본딩", raw)
        self.assertIn("정정 안내:", formatted)
        self.assertNotIn("[이번 변화]", formatted)
        self.assertNotIn("신규 변화 확인 불가", formatted)
        self.assertNotIn("[핵심 숫자]", formatted)
        self.assertNotIn("[HBM 수요·가격 레버리지]", formatted)
        self.assertNotIn("288GB HBM4", formatted)
        self.assertNotIn("디스펙 상쇄선", formatted)
        self.assertNotIn("<b>2026</b>", formatted)
        self.assertIn("2026-10-08", formatted)
        self.assertIn("99%이고", formatted)
        self.assertNotIn("&#xC774;", formatted)
        self.assertIn("기술 가능성 확인", formatted)
        self.assertIn("기술 공개·시연", formatted)
        self.assertNotIn("technology_showcase", formatted)
        self.assertIn("하이브리드 본딩 샘플로 계산 금지", formatted)
        self.assertIn("독립 검증 2곳 아님", formatted)
        self.assertGreaterEqual(len(parts), 1)

    def test_telegram_source_urls_are_complete_clickable_anchor_only(self):
        state = dict(w.HBM_HYBRID_BOND_BASELINE)
        event = w.hbm_hybrid_bond_event(state, ["정확성 검사"], initial=True)
        _, formatted, parts = self._render_pipeline([event])
        urls = re.findall(r'<a href="([^"]+)">원문 보기</a>', formatted)
        self.assertEqual(len(urls), 5)
        for expected in (
            w.HBM_HYBRID_BOND_PRIMARY,
            w.HBM_HYBRID_BOND_REPUBLISHER,
            w.HBM_HYBRID_SK_OFFICIAL,
            w.HBM_HYBRID_SAMSUNG_OFFICIAL,
            w.HBM_HYBRID_SHARE_SOURCE,
        ):
            self.assertIn(expected, urls)
        self.assertNotIn("https://", re.sub(r'<a href="[^"]+">[^<]+</a>', "", formatted))
        self.assertNotIn("[https://", formatted)
        self.assertNotIn("<b>82%</b>", formatted)
        self.assertTrue(all(len(x.encode("utf-16-le")) // 2 <= 3600 for x in parts))


    def test_hybrid_final_telegram_gate_accepts_original_render(self):
        event = w.hbm_hybrid_bond_event(
            w.HBM_HYBRID_BOND_BASELINE, ["단일 전문가 보도·미확정"], initial=True
        )
        _, formatted, _ = self._render_pipeline([event])
        self.assertIsNone(delivery.validate_rubin_hybrid_notification(formatted))

    def test_final_telegram_gate_blocks_known_error_recurrence(self):
        event = w.hbm_hybrid_bond_event(
            w.HBM_HYBRID_BOND_BASELINE, ["단일 전문가 보도·미확정"], initial=True
        )
        _, formatted, _ = self._render_pipeline([event])
        samples = {
            "fake_change_header": formatted.replace(
                "<b>🚨 HBM 하이브리드 본딩", "🚨 Rubin/HBM 구조 변화 감시 [이번 변화]\n<b>🚨 HBM 하이브리드 본딩", 1
            ),
            "year_bold": formatted.replace("2026-10-08", "<b>2026</b>-10-08", 1),
            "broken_korean_entity": formatted.replace("99%이고", "99%&#xC774;고", 1),
            "unrelated_leverage": formatted + "\n[HBM 수요·가격 레버리지]\n",
            "unsafe_link": formatted.replace(
                w.HBM_HYBRID_BOND_PRIMARY, "https://example.com/fake-source", 1
            ),
            "visible_percent_encoded_url": formatted + "\n• 삼성 공식 "
                + w.HBM_HYBRID_SAMSUNG_OFFICIAL + "\n",
            "lost_links": re.sub(
                r'<a href="[^"]+">원문 보기</a>', "원문 주소 미확인", formatted
            ),
            "english_stage": formatted.replace("기술 공개·시연", "technology_showcase", 1),
        }
        for label, corrupt in samples.items():
            with self.subTest(label=label):
                with self.assertRaises(ValueError):
                    delivery.validate_rubin_hybrid_notification(corrupt)

    def test_hybrid_mention_in_unrelated_rubin_story_does_not_block_delivery(self):
        normal = (
            "<b>🚨 Rubin/HBM 구조 변화 감시</b>\n"
            "• 차세대 HBM 하이브리드 본딩 기술을 언급한 리서치\n"
            "• 신규 변화 1건\n"
        )
        self.assertIsNone(delivery.validate_rubin_hybrid_notification(normal))


    def test_all_hbm_feeds_failed_causes_hard_failure(self):
        old = {"seen_ids": [], "seen_fact_keys": [], "hbm_hybrid_bond_track_version": 2}
        with (
            patch.object(w, "load_state", return_value=(old, False)),
            patch.object(w, "read_feed", return_value=([], ["UpstreamTimeout"])),
            patch.object(w, "fetch_fx", side_effect=AssertionError("must fail before conversion")),
        ):
            with self.assertRaisesRegex(RuntimeError, "all configured queries failed"):
                w.main()

    def test_partial_feed_outage_does_not_claim_all_sources_failed(self):
        old = {"seen_ids": [], "seen_fact_keys": [],
               "structure_baseline_version": w.STRUCTURE_BASELINE_VERSION,
               "hbm_hybrid_bond_track_version": w.HBM_HYBRID_BOND_TRACK_VERSION}
        calls = {"n": 0}
        def fake_feed(*args):
            calls["n"] += 1
            return ([], ["UpstreamTimeout"]) if calls["n"] % 2 else ([], [])
        with tempfile.TemporaryDirectory() as tmp:
            out = pathlib.Path(tmp)
            with (
                patch.object(w, "OUT", out),
                patch.object(w, "load_state", return_value=(old, False)),
                patch.object(w, "read_feed", side_effect=fake_feed),
                patch.object(w, "fetch_fx", return_value={"rate":1400.0,"date":"2026-10-08","error":""}),
            ):
                w.main()
                state = (out / "rubin_hbm_pending_state.json").read_text(encoding="utf-8")
                self.assertIn('"feed_healthy"', state)
                self.assertIn('"feed_checks"', state)
                self.assertGreater(calls["n"], 0)

    def test_mixed_hybrid_and_rubin_events_remain_independent(self):
        state = dict(w.HBM_HYBRID_BOND_BASELINE)
        hybrid = w.hbm_hybrid_bond_event(state, ["동일 익명 인터뷰"], initial=True)
        rubin = {
            "category":"rubin_spec",
            "headline_ko":"Rubin Ultra 사양 변경 보도(시험)",
            "origin_source":"테스트",
            "source":"테스트",
            "verification":"보도",
            "published_at_kst":"2026-10-08T15:00:00+09:00",
            "fact_bullets":["테스트용 사양 정보"],
            "verdict":"확정 전",
            "direct_link":"https://example.com/demo"
        }
        _, formatted, parts = self._render_pipeline([rubin, hybrid])
        self.assertIn(delivery.MESSAGE_BREAK, formatted)
        self.assertIn("[이번 변화]", formatted)
        self.assertIn("HBM 하이브리드 본딩", formatted)
        self.assertIn('• Damnang: <a href=', formatted)
        self.assertGreaterEqual(len(parts), 2)
        hybrid_part = next(x for x in parts if "HBM 하이브리드 본딩" in x)
        self.assertNotIn("[HBM 수요·가격 레버리지]", hybrid_part)

    def test_existing_v1_state_is_normalized_with_one_correction_then_silent(self):
        old = {
            "seen_ids":[],
            "seen_fact_keys":[],
            "structure_baseline_version":w.STRUCTURE_BASELINE_VERSION,
            "hbm_hybrid_bond_track_version":1,
            "hbm_hybrid_bonding": {
                "sk_official_hybrid_stage": "technical_feasibility",
                "sk_official_hybrid_customer_sample_verified":False,
                "samsung_official_hybrid_stage": "technology_showcase",
                "samsung_official_hybrid_customer_sample_verified":False,
                "reported_origin_count":1,
            },
        }
        memory = {"saved":copy.deepcopy(old)}
        def load():
            return copy.deepcopy(memory["saved"]), False
        def fake_json(path, value):
            if "rubin_hbm_pending_state.json" in str(path):
                memory["saved"].update(copy.deepcopy(value))
        with tempfile.TemporaryDirectory() as tmp:
            output = pathlib.Path(tmp)
            with (
                patch.object(w, "OUT", output),
                patch.object(w, "load_state", side_effect=load),
                patch.object(w, "read_feed", return_value=([],[])),
                patch.object(w, "fetch_fx", return_value={"rate":1400.0,"date":"2026-10-08","error":""}),
                patch.object(w, "write_json", side_effect=fake_json),
            ):
                w.main()
                self.assertEqual(memory["saved"]["hbm_hybrid_bond_track_version"], 2)
                stage = memory["saved"]["hbm_hybrid_bonding"]
                self.assertEqual(stage["skhynix_official_hybrid_stage"], "technical_feasibility")
                self.assertFalse(stage["skhynix_official_hybrid_customer_sample_verified"])
                self.assertNotIn("sk_official_hybrid_stage", stage)
                self.assertNotIn("sk_official_hybrid_customer_sample_verified", stage)
                self.assertEqual(memory["saved"]["last_send_event_count"], 1)
                notice = (output / "rubin_hbm_alert.md").read_text(encoding="utf-8")
                self.assertIn("정정 안내:", notice)
                self.assertIn("새 기술 진전 아님", notice)
                w.main()
                self.assertEqual(memory["saved"]["last_send_event_count"], 0)


if __name__ == "__main__":
    unittest.main()
