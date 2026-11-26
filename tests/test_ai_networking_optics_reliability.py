"""Offline regressions for real optics alert loss and policy-stage ambiguity."""
import importlib.util
import json
import pathlib
import tempfile
import unittest
from unittest import mock

ROOT = pathlib.Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("optics_reliability_watch", ROOT / "scripts/ai_networking_optics_watch.py")
watch = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(watch)


class OpticsReliabilityTests(unittest.TestCase):

    def test_spacex_official_role_ids_distinguish_satellite_and_datacenter(self):
        today = watch.dt.datetime(2026, 11, 26, 5, 45, tzinfo=watch.dt.timezone.utc)
        rows = [
            {"id":8827682002, "absolute_url":watch.SPACEX_JOB_BOARD+"8827682002",
             "title":"Manufacturing Engineer - Supplier Development, Optics & Optomechanical Systems (Starlink)",
             "content":"Starlink Space Lasers satellite free-space optical communication. Develop suppliers, manufacturing quality and production part approval process (PPAP)."},
            {"id":8563613002, "absolute_url":watch.SPACEX_JOB_BOARD+"8563613002",
             "title":"Sourcing Specialist, Mechanical & Optical Commodities (Starlink)",
             "content":"Starlink satellites optical commodities. Develop supply base, capacity planning, long-term agreements and qualification."},
            {"id":8949272002, "absolute_url":watch.SPACEX_JOB_BOARD+"8949272002",
             "title":"Sourcing Manager (Network Infrastructure)",
             "content":"Datacenter network hardware, optical transceivers, supplier capacity reservations, 800G, 1.6T, 3.2T, co-packaged optics, InP, GaAs, 224G SerDes."},
        ]
        body = json.dumps({"jobs":rows, "meta":{"total":len(rows)}}).encode()
        items, errors, status = watch.spacex_optical_jobs(fetcher=lambda *args, **kwargs: body, observed=today)
        self.assertEqual((len(items), errors, status), (3, [], "official_board_verified"))
        self.assertEqual({x["category"] for x in items}, {"스타링크 위성 광학 공급업체 개발", "스타링크 위성 광학 부품 조달", "SpaceX AI 데이터센터 네트워크 조달"})
        for item in items:
            self.assertTrue(watch.spacex_job_source_verified(item))
            self.assertEqual(watch.canonical_story_key(watch.SPACEX_OPTICS_COMPANY, item["title"]),
                             f"spacex|optical-job|{item['spacex_job_id']}")
            self.assertIn("미확정", item["stage"])
        self.assertEqual(items[0]["spacex_date_reference"], "2026-09-23")
        self.assertEqual(items[1]["spacex_date_reference"], "2026-07-16")
        self.assertIn("224G 고속 신호전송", items[2]["spacex_features"])
        self.assertIsNone(watch.spacex_job_item(dict(rows[0], absolute_url="https://example.com/jobs/8827682002"), observed=today))
        self.assertIsNone(watch.spacex_job_item(dict(rows[2], content="Non-optical network software hiring"), observed=today))
        self.assertIsNone(watch.spacex_job_item(dict(rows[0], title="General accounting specialist"), observed=today))
        self.assertFalse(watch.spacex_job_source_verified(dict(items[0], link=watch.SPACEX_JOB_BOARD+"8563613002")))

    def test_spacex_compact_output_preserves_all_sixteen_ids_and_role_specific_features(self):
        # Reproduce the two eight-job batches delivered on 2026-11-26;
        # fixtures use the reported fields, not a live job-board request.
        supply = ["생산능력 확보·확장", "신규·복수 공급처 발굴", "품질·신뢰성 검증"]
        lta = ["장기 공급계약 협상"]
        high = ["800G", "1.6T", "3.2T", "CPO(광학 공동 패키징)", "InP(인화인듐)",
                "GaAs(갈륨비소)", "광검출기", "DSP(디지털 신호처리기)", "224G 고속 신호전송",
                "능동·수동 구리 연결 케이블", "광섬유·광케이블"]
        basic = ["CPO(광학 공동 패키징)", "DSP(디지털 신호처리기)",
                 "능동·수동 구리 연결 케이블", "광섬유·광케이블"]
        optical = ["품질·신뢰성 검증", "위성 자유공간 레이저 통신", "광검출기",
                   "DSP(디지털 신호처리기)", "광섬유·광케이블"]
        dev = "스타링크 위성 광학 공급업체 개발"
        procurement = "스타링크 위성 광학 부품 조달"
        design = "스타링크 위성 광트랜시버 개발"
        dc = "SpaceX AI 데이터센터 네트워크 조달"
        batch1 = [(8827682002, dev, ["생산부품 승인 절차(PPAP)"] + supply + ["위성 자유공간 레이저 통신"]),
                  (8949272002, dc, supply + high), (8563613002, procurement, lta + supply),
                  (8826314002, design, optical), (8950942002, dc, lta + supply + basic),
                  (8952123002, dc, lta + supply + basic), (8949091002, dc, lta + supply + basic),
                  (8677827002, design, optical)]
        batch2 = [(8563611002, procurement, lta + supply), (8932743002, procurement, lta + supply),
                  (8957252002, dc, supply + high), (8687373002, procurement, lta + supply),
                  (8957359002, dc, lta + supply + basic), (8957350002, dc, lta + supply + basic),
                  (8957360002, dc, lta + supply + basic), (8957226002, dc, supply + basic)]
        for batch, stamp in ((batch1, "2026-11-26T15:11:52+09:00"), (batch2, "2026-11-26T15:49:14+09:00")):
            items = []
            for job_id, category, features in batch:
                ref = watch.SPACEX_JOB_REFERENCES.get(job_id)
                items.append({"company": watch.SPACEX_OPTICS_COMPANY, "category": category,
                              "source": "SpaceX Careers", "title": f"SpaceX role [공고 ID: {job_id}]",
                              "link": watch.SPACEX_JOB_BOARD + str(job_id), "spacex_job_id": job_id,
                              "spacex_official_verified": True, "spacex_role_ko": category + " 인력",
                              "spacex_features": features, "spacex_observed_at": stamp,
                              "spacex_date_reference": ref[0] if ref else None,
                              "spacex_date_reference_url": ref[1] if ref else None})
            before = json.dumps(items, ensure_ascii=False, sort_keys=True)
            lines = watch.render_spacex_job_sections(items)
            rendered = "\n".join(lines)
            self.assertEqual(json.dumps(items, ensure_ascii=False, sort_keys=True), before)
            self.assertIn("공식 채용 8건", rendered)
            self.assertEqual(rendered.count("• 확인:"), 1)
            self.assertEqual(rendered.count(stamp), 1)
            self.assertEqual(rendered.count("• 투자 의미:"), len(set(x[1] for x in batch)))
            for item in items:
                self.assertEqual(rendered.count(item["link"]), 1)
                for feature in item["spacex_features"]:
                    self.assertIn(feature, rendered)
                if item["spacex_date_reference"]:
                    self.assertIn(item["spacex_date_reference"], rendered)
                    self.assertIn(item["spacex_date_reference_url"], rendered)
            high_id = 8949272002 if batch is batch1 else 8957252002
            high_line = next(i for i, line in enumerate(lines) if "800G" in line)
            self.assertIn(str(high_id), lines[high_line + 1])
            self.assertEqual(lines[high_line + 1].count("job-boards.greenhouse.io"), 1)
            self.assertIn("장기 공급계약 협상", rendered)
            # Conservative raw HTML margin including the normal header/footer.
            self.assertLessEqual(max(len(rendered), len(rendered.encode("utf-16-le")) // 2) + 300, 3800)

    def test_spacex_source_failure_is_not_empty_verified_board(self):
        def broken(*args, **kwargs):
            raise OSError("unavailable")
        items, errors, status = watch.spacex_optical_jobs(fetcher=broken, seen_ids=watch.SPACEX_REVIEW_IDS)
        self.assertEqual(items, [])
        self.assertEqual(status, "official_source_unavailable")
        self.assertTrue(errors)
        items, errors, status = watch.spacex_optical_jobs(fetcher=lambda *args, **kwargs: b'{"jobs":[],"meta":{"total":5}}', seen_ids=watch.SPACEX_REVIEW_IDS)
        self.assertEqual(status, "official_source_unavailable")
        self.assertTrue(errors)


    def test_avicena_round_and_evaluation_are_separate_events(self):
        a = "Avicena Raises $100 Million Series C to Accelerate Commercialization of microLED Optical Interconnects for AI Infrastructure"
        b = "Avicena raises $100M to commercialize microLED optical links"
        self.assertEqual(watch.avicena_milestone(a)[2], watch.AVICENA_SERIES_C_KEY)
        self.assertEqual(watch.avicena_milestone(b)[2], watch.AVICENA_SERIES_C_KEY)
        self.assertNotIn(watch.AVICENA_SERIES_C_KEY, watch.AVICENA_PRIOR_KEYS)
        self.assertEqual(watch.canonical_story_key("Samsung Electronics", a), watch.AVICENA_SERIES_C_KEY)
        self.assertTrue(watch.same_underlying_story({"company":"Avicena","title":a},
                                                    {"company":"Samsung Electronics","title":b}))
        for old in (
            "Avicena raises $25 million in Series A",
            "Avicena announces Series B funding round led by Tiger Global",
            "Avicena Ships World's First 1Tbps Evaluation Kits",
            "Avicena to Demonstrate World's First Connectorized microLED Optical Interconnect Evaluation Kit",
            "Avicena plans first commercial product launch in 2027 for LightBundle",
        ):
            self.assertIn(watch.avicena_milestone(old)[2], watch.AVICENA_PRIOR_KEYS, old)
        self.assertIsNone(watch.avicena_milestone("Unrelated microLED display maker raises $100M"))
        self.assertIsNone(watch.avicena_milestone("Avicena stock price rises on microLED"))
        self.assertIsNone(watch.avicena_milestone("Avicena seeks Series C funding"))
        self.assertEqual(watch.avicena_milestone("Avicena begins volume production of LightBundle optical interconnects")[0],
                         "아비세나 실제 양산·상용화")
        self.assertEqual(watch.avicena_milestone("Avicena signs new supply agreement for LightBundle with SK hynix")[0],
                         "아비세나 고객·공급계약")
        self.assertEqual(watch.avicena_milestone("Avicena LightBundle customer qualification completed at Samsung")[0],
                         "아비세나 고객 검증·샘플")

    def test_avicena_direct_verified_and_unavailable_sources(self):
        issuer = b"Avicena Series C LightBundle $100 million InterVest SK hynix Ventures Samsung Catalyst Fund AMD Ventures November 24, 2026"
        investor = "Avicena InterVest SK hynix Ventures Samsung Catalyst Fund シリーズC 2026/11/25".encode()
        def valid_fetch(url, timeout=12):
            return {watch.AVICENA_RELEASE_URL: issuer, watch.AVICENA_INVESTOR_URL: investor}[url]
        today = watch.dt.date(2026, 11, 25)
        item, errors = watch.avicena_series_c_backfill(fetcher=valid_fetch, on_date=today)
        self.assertTrue(item["avicena_direct_verified"])
        self.assertEqual(errors, [])
        self.assertTrue(watch.avicena_source_verified(item, [item]))
        self.assertFalse(watch.avicena_source_verified(dict(item, link="https://fake.example"), []))
        def blocked(url, timeout=12):
            raise OSError("source unavailable")
        none, failures = watch.avicena_series_c_backfill(fetcher=blocked, on_date=today)
        self.assertIsNone(none)
        self.assertTrue(failures)
        self.assertEqual(watch.avicena_series_c_backfill(fetcher=blocked, on_date=watch.dt.date(2026, 12, 9)), (None, []))

    def test_avicena_index_requires_primary_and_distinct_news_for_known_round(self):
        a = {"company":"Avicena", "title":watch.AVICENA_SERIES_C_TITLE, "source":"Avicena",
             "source_url":"https://avicena.tech", "link":"https://avicena.tech/a"}
        b = dict(a, source="VentureBurn", source_url="https://ventureburn.com", link="https://ventureburn.com/a")
        wire = dict(a, source="Business Wire", source_url="https://businesswire.com", link="https://businesswire.com/a")
        self.assertFalse(watch.avicena_source_verified(a, [a, wire]))
        self.assertTrue(watch.avicena_source_verified(a, [a, b]))
        self.assertFalse(watch.avicena_source_verified(dict(a, source_url="https://avicena.tech.fake.example"), [b]))
        self.assertFalse(watch.avicena_source_verified(b, [b]))


    def test_huang_exit_cpo_raises_questions_is_not_new_investment(self):
        headline = (
            "[News] Huang’s Exit Raises Questions Over NVIDIA’s CPO Roadmap "
            "and Supply Chain; TSMC Ties Expected to Hold - TrendForce"
        )
        self.assertTrue(watch.nvidia_cpo_leadership_outlook_only(headline))
        self.assertEqual(
            watch.canonical_story_key("NVIDIA", headline),
            watch.NVIDIA_HUANG_CPO_OUTLOOK_KEY,
        )
        self.assertEqual(
            watch.canonical_story_key("CPO Packaging & Test", headline),
            watch.NVIDIA_HUANG_CPO_OUTLOOK_KEY,
        )
        self.assertNotEqual(watch.stage_for(headline), "투자·개발자금")
        self.assertEqual(
            watch.category_for(headline, "NVIDIA"),
            "CPO 경영진 교체·공급망 영향 전망",
        )
        self.assertFalse(
            any(watch.re.search(p, headline, watch.re.I) for p in watch.ACTION_PATTERNS),
            "Raises questions cannot masquerade as a financing or new commercial event",
        )

    def test_stale_cpo_opinion_blocked_but_actual_deals_remain_eligible(self):
        now = watch.dt.datetime(2026, 11, 22, 11, 47, tzinfo=watch.dt.timezone.utc)
        published = watch.dt.datetime(2026, 11, 16, 8, 25, tzinfo=watch.dt.timezone.utc)
        stale = "NVIDIA CPO roadmap raises questions over TSMC ties and supply chain"
        self.assertTrue(watch.stale_nvidia_cpo_commentary("NVIDIA", stale, published, now))
        self.assertTrue(watch.stale_nvidia_cpo_commentary(
            "CPO Packaging & Test", stale, published, now))
        self.assertFalse(watch.stale_nvidia_cpo_commentary(
            "NVIDIA", stale, now - watch.dt.timedelta(hours=4), now))
        actual = "NVIDIA signs new CPO supply contract with TSMC amid questions over executive exit"
        self.assertFalse(watch.stale_nvidia_cpo_commentary("NVIDIA", actual, published, now))
        self.assertFalse(watch.nvidia_cpo_leadership_outlook_only(actual))
        self.assertFalse(watch.stale_nvidia_cpo_commentary(
            "Fabrinet", stale, published, now))

    def test_real_optical_funding_remains_detected(self):
        funding = "Ayar Labs raises $650 million in series B funding for optical compute"
        self.assertEqual(watch.stage_for(funding), "투자·개발자금")
        self.assertTrue(any(watch.re.search(p, funding, watch.re.I)
                            for p in watch.ACTION_PATTERNS))

    def test_lambda_blackwell_reprint_keeps_original_event_identity(self):
        official = "Lambda Boosts AI Factory Resiliency and Efficiency With NVIDIA Photonics - NVIDIA Blog"
        reprint = "Lambda Touts First CPO Deployment of Blackwell GPUs - HPCwire"
        expected = "sc26|lambda|cpo|first-deployment-2026-11-16"
        self.assertEqual(watch.canonical_story_key(watch.SC26_NVIDIA, official), expected)
        self.assertEqual(watch.canonical_story_key("NVIDIA", reprint), expected)
        self.assertEqual(watch.canonical_story_key(watch.SC26_NVIDIA, reprint), expected)

    def test_explicit_event_identity_merges_reprints_across_query_scopes(self):
        official = {"company": watch.SC26_NVIDIA,
                    "title": "Lambda Boosts AI Factory Resiliency and Efficiency With NVIDIA Photonics"}
        reprint = {"company": "NVIDIA", "title": "Lambda Touts First CPO Deployment of Blackwell GPUs"}
        self.assertTrue(watch.same_underlying_story(official, reprint))
        self.assertTrue(watch.same_underlying_story(reprint, official))

    def test_lambda_new_cluster_and_contract_are_not_first_deployment_reprints(self):
        original = {"company": watch.SC26_NVIDIA,
                    "title": "Lambda Boosts AI Factory Resiliency and Efficiency With NVIDIA Photonics"}
        for title in ("Lambda expands its cluster with Blackwell CPO to 20,000 GPUs",
                      "Lambda signs new contract for NVIDIA CPO Blackwell GPUs"):
            item = {"company": "NVIDIA", "title": title}
            with self.subTest(title=title):
                self.assertIn("|expansion|", watch.canonical_story_key("NVIDIA", title))
                self.assertFalse(watch.same_underlying_story(original, item))

    def test_unrelated_lambda_or_cross_company_text_is_not_globally_deduplicated(self):
        title = "Lambda Touts First CPO Deployment for New Cloud Infrastructure"
        self.assertIsNone(watch.sc26_milestone(watch.SC26_NVIDIA, title))
        a = {"company": "AlphaOptics", "title": "New 1.6T optical module starts volume production"}
        b = {"company": "BetaOptics", "title": a["title"]}
        self.assertFalse(watch.same_underlying_story(a, b))

    def test_finalizing_is_pending_and_cannot_consume_final_event(self):
        draft = "FCC is finalizing a ban on Chinese optical transceivers"
        final = "FCC finalizes a ban on Chinese optical transceivers"
        self.assertNotEqual(watch.canonical_story_key("US Optical Policy", draft),
                            watch.canonical_story_key("US Optical Policy", final))
        self.assertNotEqual(watch.stage_for(draft), watch.stage_for(final))

    def test_conditional_effective_does_not_consume_implementation(self):
        pending = "FCC optical transceiver ban could take effect after a final rule is adopted"
        effective = "FCC optical transceiver ban takes effect"
        self.assertNotEqual(watch.canonical_story_key("US Optical Policy", pending),
                            watch.canonical_story_key("US Optical Policy", effective))
        self.assertNotEqual(watch.stage_for(pending), watch.stage_for(effective))

    def test_silent_update_preserves_verified_receipt_without_inventing_one(self):
        prior = {"telegram_chat_identity_verified": True, "telegram_message_ids": [394]}
        self.assertIs(watch.preserve_delivery_metadata(prior, {})["telegram_chat_identity_verified"], True)
        self.assertNotIn("telegram_chat_identity_verified", watch.preserve_delivery_metadata({}, {}))

    def test_ninth_event_survives_eight_alert_limit_and_is_reported_next_run(self):
        companies = {name: {"ticker": name, "query": name} for name in (
            "AlphaOptics", "BetaOptics", "GammaOptics", "DeltaOptics", "EpsilonOptics",
            "ZetaOptics", "EtaOptics", "ThetaOptics", "IotaOptics")}
        rows = {name: [{"title": f"{name} starts 1.6T optical transceiver volume production for AI data centers",
                        "source": "Reuters", "source_url": "https://www.reuters.com",
                        "link": f"https://www.reuters.com/technology/{name.lower()}",
                        "published": watch.NOW.isoformat()}] for name in companies}
        with tempfile.TemporaryDirectory() as temp:
            root = pathlib.Path(temp)
            (root / "data").mkdir()
            state_path = root / "data/state.json"
            pending_path = root / "out/pending.json"
            state = {"initialized": True, "dedupe_version": 3,
                     "aaoi_power_prior_alert_correction_done": True,
                     "seen_story_keys": ["taihan|2026-09-second-shipment"]}
            state_path.write_text(json.dumps(state))
            with mock.patch.multiple(watch, ROOT=root, STATE_PATH=state_path,
                    PENDING_PATH=pending_path, ALERT_PATH=root / "out/alert.html",
                    STATUS_PATH=root / "out/status.md", COMPANIES=companies), \
                 mock.patch.object(watch, "networking_supplier_regression_checks"), \
                 mock.patch.object(watch, "new_optical_infra_regression_checks"), \
                 mock.patch.object(watch, "query_google_news", side_effect=lambda q, **kw: [dict(x) for x in rows[q]]), \
                 mock.patch.dict("os.environ", {"GITHUB_EVENT_NAME": "schedule"}):
                watch.main()
                pending = json.loads(pending_path.read_text())
                first_alert = (root / "out/alert.html").read_text()
                self.assertIn("신규 변화: <b>8건</b>", first_alert)
                item_keys = {watch.event_key(name, rows[name][0]["title"], "Reuters") for name in companies}
                self.assertEqual(len(item_keys & set(pending["seen_keys"])), 8,
                                 "An untransmitted ninth event was prematurely consumed")
                # This emulates a confirmed successful delivery committing the pending state.
                state_path.write_text(json.dumps(pending))
                watch.main()
                second_alert = (root / "out/alert.html").read_text()
                self.assertIn("신규 변화: <b>1건</b>", second_alert)
                pending2 = json.loads(pending_path.read_text())
                self.assertEqual(len(item_keys & set(pending2["seen_keys"])), 9)
                # Rendering must finish before any consumable pending state exists.
                state_path.write_text(json.dumps(state))
                with mock.patch.object(watch, "_self_test_korean_optics_alerts"), \
                     mock.patch.object(watch, "meaning_for", side_effect=RuntimeError("render failed")):
                    with self.assertRaisesRegex(RuntimeError, "render failed"):
                        watch.main()
                self.assertFalse(pending_path.exists())
                for baseline_state in ({**state, "initialized": False},
                                       {**state, "dedupe_version": 1}):
                    state_path.write_text(json.dumps(baseline_state))
                    watch.main()
                    self.assertFalse((root / "out/alert.html").exists())
                    baseline_pending = json.loads(pending_path.read_text())
                    self.assertEqual(len(item_keys & set(baseline_pending["seen_keys"])), 9)


    def test_apple_november_siph_hiring_and_market_reprint_are_one_event(self):
        company = watch.APPLE_SIPH_COMPANY
        hiring = "Apple recruits silicon photonics engineers for data center SoC (official roles 200684866, 200695336) Nov 2026"
        article = "Apple joins Samsung, SK hynix in $39 bn optical chip race"
        self.assertEqual(
            watch.canonical_story_key(company, hiring),
            watch.APPLE_SIPH_HIRING_KEY,
        )
        self.assertEqual(
            watch.canonical_story_key(company, article),
            watch.APPLE_SIPH_HIRING_KEY,
        )
        self.assertTrue(watch.same_underlying_story(
            {"company": company, "title": hiring},
            {"company": company, "title": article},
        ))
        self.assertIn("양산 전", watch.apple_siph_milestone(article)[1])
        self.assertIsNone(watch.apple_siph_milestone(
            "Apple stock rallies on a $39 billion optical chip market forecast"
        ))
        self.assertIsNone(watch.apple_siph_milestone(
            "Apple iPhone Duo hinge camera module production update"
        ))

    def test_apple_contract_is_not_conflated_with_official_hiring(self):
        company = watch.APPLE_SIPH_COMPANY
        contract = "Apple signs data center silicon photonics optical chip supply agreement"
        hiring = "Apple hiring silicon photonics engineers in Nov 2026"
        self.assertNotEqual(
            watch.apple_siph_milestone(contract)[0],
            watch.apple_siph_milestone(hiring)[0],
        )
        self.assertFalse(watch.same_underlying_story(
            {"company": company, "title": contract, "category": watch.apple_siph_milestone(contract)[0]},
            {"company": company, "title": hiring, "category": watch.apple_siph_milestone(hiring)[0]},
        ))

    def test_apple_official_job_role_identity_is_required(self):
        urls = watch.APPLE_SIPH_ROLE_SOURCES
        def valid_fetch(url, timeout=12):
            role = next(role_id for role_id, _, u in urls if u == url)
            return f"<html>Role Number: {role} Silicon Photonics Data Center SoC optical packaging</html>".encode()
        item, problems = watch.apple_siph_hiring_item(fetcher=valid_fetch, on_date=watch.dt.date(2026, 11, 20))
        self.assertEqual(item["verified_role_ids"], ["200684866", "200695336"])
        self.assertEqual(item["source"], "Apple Jobs")
        self.assertEqual(problems, [])
        self.assertTrue(watch.apple_siph_source_verified(item, [item]))
        self.assertEqual(watch.canonical_story_key(item["company"], item["title"]), watch.APPLE_SIPH_HIRING_KEY)
        self.assertIsNone(watch.apple_siph_hiring_item(
            fetcher=valid_fetch, on_date=watch.dt.date(2026, 12, 1))[0])
        invalid, failures = watch.apple_siph_hiring_item(
            fetcher=lambda url, timeout=12: b"Silicon Photonics anonymous job, missing role",
            on_date=watch.dt.date(2026, 11, 20),
        )
        self.assertIsNone(invalid)
        self.assertEqual(len(failures), 2)

    def test_apple_media_scope_cannot_bootstrap_future_contract(self):
        company = watch.APPLE_SIPH_COMPANY
        old = "Apple joins Samsung, SK hynix in $39 bn optical chip race"
        valid_news = {
            "company": company, "title": old, "source": "Pulse",
            "source_url": "https://pulse.mk.co.kr", "link": "https://pulse.mk.co.kr/news/all/12214394"
        }
        self.assertTrue(watch.apple_siph_source_verified(valid_news, [valid_news]))
        untrusted = {**valid_news, "source_url": "https://stock-blog.example"}
        self.assertFalse(watch.apple_siph_source_verified(untrusted, [untrusted]))
        contract = {
            "company": company, "title": "Apple signs data center silicon photonics chip supply agreement",
            "category": "애플 광연결 고객·공급계약", "source": "Reuters",
            "source_url": "https://www.reuters.com", "link": "https://reuters.com/a"
        }
        self.assertFalse(watch.apple_siph_source_verified(contract, [contract]))
        independent = {**contract, "source": "Bloomberg",
                       "source_url": "https://www.bloomberg.com",
                       "title": "Apple signs new agreement to supply silicon photonics chips for data center",
                       "link": "https://bloomberg.com/b"}
        self.assertTrue(watch.apple_siph_source_verified(contract, [contract, independent]))
        self.assertFalse(watch.apple_siph_source_verified(
            {**valid_news, "official_apple_job_verified": True,
             "source": "Apple Jobs", "source_url": "https://jobs.apple.com",
             "link": "https://malicious.example/job"},
            [],
        ))


if __name__ == "__main__":
    unittest.main()
