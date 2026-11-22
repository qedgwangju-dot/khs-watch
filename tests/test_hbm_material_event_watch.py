"""Offline evidence-lineage and state/Telegram regression tests for HBM material watch."""
from __future__ import annotations

import copy
import json
import pathlib
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "scripts"))
import hbm_material_event_watch as m
import hbm_delivery as d
import rubin_hbm_watch as r

class MaterialEventTests(unittest.TestCase):
    def fixture(self, report):
        return ("원보도 2026년 11월 주요 사실 " +
                " ".join(group[0] for group in report["need"]) +
                " 세부사항 검증 완료" * 12)

    def test_all_eight_reports_detected_only_with_original_evidence(self):
        current = {"seen_ids": ["existing-event"], "delivery_receipt": {"message_ids": [387]}}
        expected = {x["key"] for x in m.REPORTS if x["date"] <= "2026-11-14"}
        result, rendered, audit = m.apply(current, "2026-11-14T20:00:00+09:00", lambda url: self.fixture(next(
            r for r in m.REPORTS if url in [x[1] for x in r["sources"]]
        )))
        self.assertEqual(audit["verified_events"], 8)
        self.assertEqual(set(result["hbm_material_event_watch"]["seen_keys"]), expected)
        self.assertEqual(len(rendered), 4)
        self.assertEqual(result["seen_ids"], ["existing-event"])
        self.assertEqual(result["delivery_receipt"], {"message_ids": [387]})
        for segment in rendered:
            for part in d.chunks(segment):
                self.assertIn("근거 기사", part)
        self.assertIn("싸이맥스", rendered[0])
        self.assertIn("에스디옵틱스", rendered[0])
        self.assertIn("공식 수율 공개 없음", rendered[1])
        self.assertIn("정식 제품 공급계약", rendered[2])

    def test_repeat_is_silent_and_does_not_call_sources(self):
        cached = {"hbm_material_event_watch": {"seen_keys": [r["key"] for r in m.REPORTS]}}
        def never(url):
            raise AssertionError("must not fetch already acknowledged event")
        result, msgs, audit = m.apply(cached, "2026-11-14T20:10:00+09:00", never)
        self.assertEqual(msgs, [])
        self.assertEqual(audit["verified_events"], 0)
        self.assertEqual(len(result["hbm_material_event_watch"]["seen_keys"]), len(m.REPORTS))

    def test_missing_loi_or_supplier_does_not_trigger_false_contract(self):
        r = m.REPORTS[0]
        body = self.fixture(r).replace("LOI", "선정").replace("싸이맥스", "장비사")
        found, gaps = m.probe(r, lambda url: body)
        self.assertIsNone(found)
        self.assertTrue(all(x["status"] == "required_article_facts_not_verified" for x in gaps))

    def test_failed_source_tries_second_but_does_not_count_as_two_origins(self):
        r = m.REPORTS[1]
        def fetch(url):
            if "chosun.com" in url:
                raise TimeoutError("unavailable")
            return self.fixture(r)
        found, gaps = m.probe(r, fetch)
        self.assertIsNotNone(found)
        self.assertEqual(found["lineage"], "재인용")
        self.assertIn("DIGITIMES", found["source_label"])
        self.assertEqual(len(gaps), 1)

    def test_total_source_failure_keeps_key_retryable(self):
        def unavailable(url): raise TimeoutError("source inaccessible")
        original = {"memory_axes": {"hbf_roadmap": "keep"}}
        result, output, audit = m.apply(original, "2026-11-14T20:20:00+09:00", unavailable)
        self.assertEqual(output, [])
        self.assertEqual(result["hbm_material_event_watch"]["seen_keys"], [])
        self.assertEqual(result["memory_axes"], original["memory_axes"])
        self.assertGreater(len(audit["gaps"]), 0)

    def test_untrusted_markup_is_escaped_and_delivery_not_direct(self):
        fake = {
            "date": "2026-11-12", "label": "<bad>title", "group": "glass",
            "lineage": "원보도", "facts": ["</b><script>bad</script>"],
            "caution": "LOI <> contract", "source": "https://www.etnews.com/20261112000021",
            "source_label": "전자신문",
        }
        rendered = m.render("glass", [fake], "2026-11-14T20:21:00+09:00")
        self.assertNotIn("<script>", rendered)
        self.assertNotIn("<bad>", rendered)
        self.assertTrue(d.chunks(rendered))

    def test_main_updates_only_pending_and_notifies_only_through_existing_route(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = pathlib.Path(tmp)
            p = root / "out" / "rubin_hbm_pending_state.json"
            a = root / "out" / "rubin_hbm_alert.md"
            c = root / "out" / "hbm_material_event_coverage.json"
            base = root / "out" / "hbm_before_rubin.json"
            p.parent.mkdir()
            p.write_text(json.dumps({"memory_axes": {"keep": 1}}), encoding="utf-8")
            base.write_text(json.dumps({"memory_axes": {"keep": 1}}), encoding="utf-8")
            with patch.object(m, "PENDING", p), patch.object(m, "ALERT", a), patch.object(m, "AUDIT", c), patch.object(m, "BASELINE", base):
                with patch.object(m, "fetch_article", side_effect=RuntimeError("test_only")):
                    # The default fetcher is bound at function definition; pass a
                    # mock apply instead to verify I/O without live sources.
                    with patch.object(m, "apply", return_value=(
                        {"memory_axes": {"keep": 1}, "hbm_material_event_watch": {"seen_keys": []}}, [], {"verified_events": 0, "gaps": []}
                    )):
                        m.main()
            self.assertFalse(a.exists())
            self.assertEqual(json.loads(p.read_text())["memory_axes"]["keep"], 1)
            self.assertTrue(c.exists())

    def test_real_collector_rebuild_preserves_acknowledged_seven_keys(self):
        acknowledged = [report["key"] for report in m.REPORTS]
        durable = {"seen_ids": ["keep-existing"], "hbm_material_event_watch": {"seen_keys": acknowledged}}
        carried = r.carry_material_event_state(durable)
        self.assertEqual(carried["seen_keys"], acknowledged)
        candidate = {"seen_ids": ["keep-existing"], "hbm_material_event_watch": carried}
        m.require_durable_seen_keys(durable, candidate)
        def never_fetch(_):
            raise AssertionError("Already sent articles must never be fetched again")
        result, messages, audit = m.apply(candidate, "2026-11-15T14:30:00+09:00", never_fetch)
        self.assertEqual(messages, [])
        self.assertEqual(audit["verified_events"], 0)
        self.assertEqual(set(result["hbm_material_event_watch"]["seen_keys"]), set(acknowledged))

    def test_missing_durable_seen_keys_preflight_fails_closed_before_fetch_or_send(self):
        before = {"hbm_material_event_watch": {"seen_keys": [m.REPORTS[0]["key"]]}}
        with self.assertRaisesRegex(RuntimeError, "duplicate alert blocked"):
            m.require_durable_seen_keys(before, {})
        with self.assertRaisesRegex(RuntimeError, "duplicate alert blocked"):
            m.require_durable_seen_keys(before, {"hbm_material_event_watch": {"seen_keys": []}})
        m.require_durable_seen_keys(before, {"hbm_material_event_watch": {"seen_keys": [m.REPORTS[0]["key"]]}})

    def test_missing_baseline_main_fails_closed_and_preserves_existing_alert(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = pathlib.Path(tmp)
            pending = path / "rubin_pending.json"
            existing_alert = path / "alert.html"
            absent_baseline = path / "missing_baseline.json"
            pending.write_text(json.dumps({"hbm_material_event_watch": {"seen_keys": []}}), encoding="utf-8")
            existing_alert.write_text("existing-notification", encoding="utf-8")
            with patch.object(m, "PENDING", pending), patch.object(m, "BASELINE", absent_baseline), patch.object(m, "ALERT", existing_alert):
                with self.assertRaisesRegex(RuntimeError, "duplicate alert blocked"):
                    m.main()
            self.assertEqual(existing_alert.read_text(encoding="utf-8"), "existing-notification")

    def test_replay_across_four_rubins_is_silent_after_acknowledgement(self):
        prior = {"hbm_material_event_watch": {"seen_keys": []}}
        def evidence(url):
            report = next(r for r in m.REPORTS if url in [s[1] for s in r["sources"]])
            return self.fixture(report)
        prior, first, first_audit = m.apply(prior, "2026-11-14T19:29:30+09:00", evidence)
        self.assertEqual(first_audit["verified_events"], 8)
        self.assertEqual(len(first), 4)
        for t in ("2026-11-15T06:02:09+09:00","2026-11-15T08:20:32+09:00","2026-11-15T10:24:06+09:00","2026-11-15T11:58:29+09:00"):
            candidate={"hbm_material_event_watch": r.carry_material_event_state(prior)}
            m.require_durable_seen_keys(prior,candidate)
            def reject_fetch(url): raise AssertionError("unexpected repeated lookup")
            prior, alerts, audit = m.apply(candidate,t,reject_fetch)
            self.assertEqual(alerts, [])
            self.assertEqual(audit["verified_events"], 0)


    def test_semianalysis_forecast_is_not_a_customer_contract(self):
        report = next(row for row in m.REPORTS if "semianalysis" in row["key"])
        self.assertIn("total capacity", " ".join(report["facts"]))
        self.assertIn("전망", " ".join(report["facts"]))
        self.assertIn("분모", " ".join(report["facts"]))
        self.assertIn("평균판매단가", report["caution"])
        found, gaps = m.probe(report, lambda url: self.fixture(report))
        self.assertEqual(gaps, [])
        self.assertEqual(found["verified_kind"], "reported_not_issuer_confirmed")
        rendered = m.render("allocation", [found], "2026-11-16T03:25:00+09:00")
        self.assertIn("70%", rendered)
        self.assertIn("3.7달러/Gb", rendered)
        self.assertTrue(d.chunks(rendered))

    def test_official_new_allocation_requires_named_denominator_and_contract(self):
        good = {
            "category": "hbm_supply_allocation",
            "direct_link": "https://news.skhynix.com/en/example",
            "title": "SK hynix HBM4 2028 non-NVIDIA customers 45% signed allocation contracts",
        }
        fact = r.make_fact(good)
        self.assertIsNotNone(fact)
        self.assertIn("45", fact["headline_ko"])
        self.assertTrue(r.relevant("hbm_supply_allocation", good["title"]))
        self.assertIsNone(r.make_fact(dict(good, direct_link="https://newsletter.semianalysis.com/p/post")))
        self.assertIsNone(r.make_fact(dict(good, title="SK hynix HBM4 2028 non-NVIDIA 45% allocation may change")))
        self.assertIsNone(r.make_fact(dict(good, title="SK hynix HBM4 2028 non-NVIDIA 45% estimated by SemiAnalysis")))
        self.assertIsNone(r.make_fact(dict(good, title="SK hynix 2028 customers HBM4 45% signed capacity")))

    def test_official_article_cannot_join_signed_other_contract_and_hbm4_analyst_estimate(self):
        original = {
            "category": "hbm_supply_allocation",
            "direct_link": "https://news.skhynix.com/en/official-2028",
        }
        wrong = dict(original, title=(
            "SK hynix signed NAND agreements with 15 customers in 2028. "
            "SemiAnalysis estimates HBM4 2028 non-NVIDIA capacity allocation may reach 70%."))
        self.assertIsNone(r.make_fact(wrong))
        wrong2 = dict(original, title=(
            "SK hynix HBM4 2028 non-NVIDIA allocation 70% could be signed. "
            "A separate HBM4 customer signed a 2027 LTA."))
        self.assertIsNone(r.make_fact(wrong2))
        yes = dict(original, title="SK hynix HBM4 2028 non-NVIDIA customers 45.5% signed allocation contracts")
        got = r.make_fact(yes)
        self.assertIsNotNone(got)
        self.assertIn("45.5%", got["headline_ko"])

    def test_forecast_notice_stays_silent_on_repeated_main_collector_runs(self):
        report = next(x for x in m.REPORTS if "semianalysis" in x["key"])
        previously_sent = {"hbm_material_event_watch": {"seen_keys": [x["key"] for x in m.REPORTS]}}
        result, alert, audit = m.apply(previously_sent, "2026-11-16T03:25:00+09:00",
                                       lambda _: (_ for _ in ()).throw(AssertionError("previously sent")))
        self.assertEqual(alert, [])
        self.assertEqual(audit["verified_events"], 0)
        self.assertIn(report["key"], result["hbm_material_event_watch"]["seen_keys"])

    def test_future_dated_filing_is_never_fetched_or_sent_before_nov16(self):
        previously_sent = {"hbm_material_event_watch": {"seen_keys": [
            row["key"] for row in m.REPORTS if row["date"] <= "2026-11-15"
        ]}}
        def never_fetch(url):
            raise AssertionError("Future filing cannot be fetched")
        _, alerts, audit = m.apply(previously_sent, "2026-11-15T23:59:00+09:00", never_fetch)
        self.assertEqual(alerts, [])
        self.assertEqual(audit["verified_events"], 0)

    def test_two_2026q3_filing_events_recover_once_with_exact_period_and_anonymity(self):
        earlier = [row["key"] for row in m.REPORTS if row["date"] < "2026-11-16"]
        state = {"hbm_material_event_watch": {"seen_keys": earlier}}
        def fact_fixture(url):
            row = next(r for r in m.REPORTS if url in [v[1] for v in r["sources"]])
            return self.fixture(row)
        out, alerts, audit = m.apply(state, "2026-11-17T15:20:00+09:00", fact_fixture)
        self.assertEqual(audit["verified_events"], 3)
        self.assertEqual(len(alerts), 2)
        self.assertIn("70.2%", alerts[0])
        self.assertIn("62.5%", alerts[0])
        self.assertIn("34조9,778", alerts[0])
        self.assertIn("10조948", alerts[0])
        self.assertIn("실명 미공개", alerts[0])
        self.assertIn("50% 초과", alerts[0])
        self.assertIn("2027년 상반기", alerts[1])
        self.assertIn("2028년 +4.9%", alerts[1])
        self.assertIn("2028년 450조원", alerts[1])
        self.assertIn("10조~20조원", alerts[1])
        self.assertEqual(len(out["hbm_material_event_watch"]["seen_keys"]), sum(r["date"] <= "2026-11-17" for r in m.REPORTS))
        for chunk in d.chunks(alerts[0]):
            self.assertTrue(chunk.strip())
        def no_repeat(_):
            raise AssertionError("Previously acknowledged filing must not be fetched")
        again, no_alert, repeat_audit = m.apply(out, "2026-11-17T15:47:00+09:00", no_repeat)
        self.assertEqual(no_alert, [])
        self.assertEqual(repeat_audit["verified_events"], 0)
        self.assertEqual(len(again["hbm_material_event_watch"]["seen_keys"]), sum(r["date"] <= "2026-11-17" for r in m.REPORTS))

    def test_skhynix_filing_bogus_big_customer_or_revenue_is_not_promoted(self):
        row = next(x for x in m.REPORTS if "geo_customer_concentration" in x["key"])
        for missing in ("34조9778", "23조8509", "147조7392", "62.5%"):
            body = self.fixture(row).replace(missing, "0원")
            found, gaps = m.probe(row, lambda url: body)
            self.assertIsNone(found)
            self.assertTrue(gaps)
        self.assertNotIn("엔비디아 확정", " ".join(row["facts"]))

    def test_kiwoom_2028_forecast_keeps_sources_stages_and_rejects_missing_prices(self):
        row = next(x for x in m.REPORTS if "kiwoom_2028" in x["key"])
        self.assertEqual(row["date"], "2026-11-16")
        self.assertIn("박유악", " ".join(row["facts"]))
        self.assertIn("원본 PDF 전문 직접 확인은 제한", row["caution"])
        self.assertIn("시장점유율 10~20%", " ".join(row["facts"]))
        self.assertIn("2027년 상반기", " ".join(row["facts"]))
        self.assertIn("2027년 하반기", " ".join(row["facts"]))
        for absent in ("-54%", "-47%", "450조"):
            evidence = self.fixture(row).replace(absent, "삭제됨")
            result, errors = m.probe(row, lambda url: evidence)
            self.assertIsNone(result)
            self.assertTrue(errors)

    def test_kiwoom_scenario_recovers_once_without_resetting_old_confirmed_receipt(self):
        row = next(x for x in m.REPORTS if "kiwoom_2028" in x["key"])
        earlier = [x["key"] for x in m.REPORTS if x is not row]
        preserved = {
            "delivery_receipt": {"status": "confirmed", "message_ids": [488]},
            "hbm_material_event_watch": {"seen_keys": earlier},
        }
        updated, alerts, audit = m.apply(preserved, "2026-11-17T23:10:00+09:00",
                                         lambda url: self.fixture(row))
        self.assertEqual(audit["verified_events"], 1)
        self.assertEqual(len(alerts), 1)
        self.assertIn("증권사", alerts[0])
        self.assertIn("2028년 +8.4%", alerts[0])
        self.assertEqual(updated["delivery_receipt"], preserved["delivery_receipt"])
        again, alerts_again, audit_again = m.apply(
            updated, "2026-11-17T23:20:00+09:00",
            lambda _: (_ for _ in ()).throw(AssertionError("must not refetch")))
        self.assertEqual(alerts_again, [])
        self.assertEqual(audit_again["verified_events"], 0)
        self.assertEqual(again["hbm_material_event_watch"]["seen_keys"],
                         updated["hbm_material_event_watch"]["seen_keys"])

    def test_trendforce_roadshow_only_after_publication_and_exact_event_once(self):
        roadshow = [r for r in m.REPORTS if r["date"] == "2026-11-18"]
        self.assertEqual(len(roadshow), 4)
        previous = {
            "delivery_receipt": {"status": "confirmed", "message_ids": [493]},
            "hbm_material_event_watch": {"seen_keys": [
                r["key"] for r in m.REPORTS if r["date"] < "2026-11-18"
            ]},
        }
        def never(url):
            raise AssertionError("Future-dated Roadshow cannot be read")
        _, before_alerts, before_audit = m.apply(
            previous, "2026-11-17T23:59:59+09:00", never)
        self.assertEqual(before_alerts, [])
        self.assertEqual(before_audit["verified_events"], 0)

        # Independently sufficient exact numeric evidence for each item.
        evidence = " ".join(" ".join(terms[0] for terms in x["need"]) for x in roadshow)
        updated, alerts, audit = m.apply(
            previous, "2026-11-18T18:15:00+09:00", lambda _: evidence)
        self.assertEqual(audit["verified_events"], 4)
        self.assertEqual(len(alerts), 1)  # one grouped Telegram alert, not four notifications
        alert = alerts[0]
        for needle in ("2.05", "3~5.5", "5달러", "2027년 2분기",
                       "31%→2027년 51%", "22%→2027년 31%", "2028년", "3만6,000"):
            self.assertIn(needle, alert)
        self.assertIn("전체 가격대가 100% 이상", alert)
        self.assertIn("11월 17일", alert)  # already monitored NAND event, no duplicate
        self.assertEqual(updated["delivery_receipt"], previous["delivery_receipt"])
        self.assertEqual(len(updated["hbm_material_event_watch"]["seen_keys"]),
                         sum(row["date"] <= "2026-11-18" for row in m.REPORTS))
        for chunk in d.chunks(alert):
            self.assertTrue(chunk.strip())
        _, repeated, repeated_audit = m.apply(
            updated, "2026-11-18T19:00:00+09:00",
            lambda _: (_ for _ in ()).throw(AssertionError("Acknowledged event refetched")))
        self.assertEqual(repeated, [])
        self.assertEqual(repeated_audit["verified_events"], 0)

    def test_trendforce_roadshow_numeric_gate_and_price_scope(self):
        news = next(r for r in m.REPORTS if "roadshow_hbm4_per_gb" in r["key"])
        self.assertIn("상승률", " ".join(news["facts"]))
        self.assertIn("분모가 다름", " ".join(news["facts"]))
        self.assertNotIn("확정 납품", news["label"])
        for omitted in ("2.05", "3~5.5", "HBM4E"):
            source = " ".join(terms[0] for terms in news["need"]).replace(omitted, "MISSING")
            obs, gaps = m.probe(news, lambda _: source)
            self.assertIsNone(obs)
            self.assertTrue(gaps)
        self.assertIn("전체 생산능력으로 확정 사용 금지", " ".join(
            next(r for r in m.REPORTS if "2028_dram_supply_risk" in r["key"])["facts"]))

    def test_trendforce_digest_preserves_all_numeric_facts_in_short_visible_sections(self):
        import currency_krw_guard as krw
        roadshow = [r for r in m.REPORTS if r["date"] == "2026-11-18"]
        items = [{**r, "source": r["sources"][0][1],
                  "source_label": r["sources"][0][0],
                  "lineage": r["sources"][0][2]} for r in roadshow]
        short = m.render("roadshow", items, "2026-11-18T18:33:49+09:00")
        long = m.render("roadshow", [
            {**r, "short_title": None, "brief_facts": None, "brief_caution": None}
            for r in items
        ], "2026-11-18T18:33:49+09:00")
        self.assertLess(len(short), len(long) * 0.8)
        self.assertEqual(short.count("<b>■ "), 4)
        self.assertEqual(short.count("근거 기사"), 4)
        self.assertNotIn("• 최초 보도", short)
        for part in ("2.05달러/Gb", "3~5.5달러/Gb", "5달러/Gb",
                     "1.67달러/Gb", "3.70달러/Gb", "+121.6%",
                     "10~15%", "5~10%", "3~8%", "+0~5%",
                     "2027년 2분기", "11월 17일", "31%→2027년 51%",
                     "22%→2027년 31%", "2027년 42%", "18만→28만",
                     "20만→26만", "3~4배", "23%→2027년 약 30%",
                     "+78%", "+54%", "+60%", "+118%", "월 20만장",
                     "월 30만장", "10만~20만장", "월 3만6,000장",
                     "전원 인가", "전체 가격대가 100% 이상"):
            self.assertIn(part, short)
        with patch("currency_krw_guard._rate", return_value=(1336.21, "test")):
            paired = krw.enforce_text(short, hbm_mode=True)
        self.assertIn("1달러=1,333.00원", paired)
        self.assertNotIn("1달러(약", paired)
        self.assertNotIn("달러당(약", paired)
        self.assertNotIn("달러(약 40,086원)", paired)
        segments = d.chunks(paired)
        self.assertTrue(segments)
        self.assertEqual(len(segments), 1)  # four complete topics + FX reference in one message
        self.assertTrue(all(len(part.encode("utf-16-le")) // 2 <= 3600
                            for part in segments))
        self.assertEqual(sum(part.count("근거 기사") for part in segments), 4)

    def test_munhwa_20high_equipment_article_gate_and_safe_retry(self):
        """Single-source equipment lead stays unverified until exact publisher body."""
        report = next(row for row in m.REPORTS if row["key"] ==
                      "20261119_munhwa_skhynix_20high_hybrid_bonder_report")
        previous = {
            "delivery_receipt": {"status": "confirmed", "message_ids": [512, 513]},
            "hbm_hybrid_bonding": {"skhynix_official_hybrid_stage": "technical_feasibility"},
            "hbm_material_event_watch": {"seen_keys": [
                row["key"] for row in m.REPORTS if row["date"] < "2026-11-19"
            ]},
        }
        def no_fetch(_):
            raise AssertionError("No future or acknowledged article fetch")
        out, msgs, audit = m.apply(previous, "2026-11-18T23:59:59+09:00", no_fetch)
        self.assertEqual(msgs, [])
        self.assertEqual(audit["verified_events"], 0)
        self.assertNotIn(report["key"], out["hbm_material_event_watch"]["seen_keys"])

        def inaccessible(_):
            raise TimeoutError("publisher unavailable")
        blocked, alerts, audit = m.apply(previous, "2026-11-19T12:00:00+09:00", inaccessible)
        self.assertEqual(alerts, [])
        self.assertEqual(audit["verified_events"], 0)
        self.assertIn(report["key"], [v["key"] for v in audit["gaps"]])
        self.assertNotIn(report["key"], blocked["hbm_material_event_watch"]["seen_keys"])

        incomplete = "SK하이닉스 20단 HBM 하이브리드 본더"
        found, missing = m.probe(report, lambda url: incomplete)
        self.assertIsNone(found)
        self.assertEqual(len(missing), 1)
        self.assertEqual(missing[0]["status"], "required_article_facts_not_verified")

        exact_article = (
            "2026년 11월 19일 문화일보 단독. "
            "SK하이닉스 20단 HBM 하이브리드 본더 투입 보도. "
            "고객 승인·양산 장비 대수·구매계약 미공개. "
        ) * 8
        later, notices, checked = m.apply(
            blocked, "2026-11-19T12:15:00+09:00",
            lambda url: exact_article if url == "https://munhwa.com/article/11632525"
            else (_ for _ in ()).throw(AssertionError("unexpected source"))
        )
        self.assertEqual(checked["verified_events"], 1)
        self.assertEqual(checked["verified_keys"], [report["key"]])
        self.assertEqual(len(notices), 1)
        msg = notices[0]
        self.assertIn("하이브리드 본더 투입 보도", msg)
        self.assertIn("문화일보 단독 보도", msg)
        self.assertIn("https://munhwa.com/article/11632525", msg)
        self.assertIn("https://news.skhynix.com/en/tech-note-series-ep2/", msg)
        self.assertIn("기존 평가의 후속인지", msg)
        self.assertEqual(later["delivery_receipt"], previous["delivery_receipt"])
        self.assertEqual(later["hbm_hybrid_bonding"], previous["hbm_hybrid_bonding"])
        self.assertEqual(sum(v.count("근거 기사") for v in d.chunks(msg)), 1)
        m.require_durable_seen_keys(previous, later)
        repeated, repeated_alerts, again_audit = m.apply(
            later, "2026-11-20T09:00:00+09:00", no_fetch
        )
        self.assertEqual(repeated_alerts, [])
        self.assertEqual(again_audit["verified_events"], 0)
        self.assertIn(report["key"], repeated["hbm_material_event_watch"]["seen_keys"])

    def test_hybrid_bonder_vendor_queries_do_not_confuse_tc_bonders(self):
        self.assertTrue(r.relevant(
            "hbm_hybrid_bonding",
            "SK하이닉스 20단 HBM 하이브리드 본더 SHB2 Nano 반입 평가"))
        self.assertTrue(r.relevant(
            "hbm_hybrid_bonding",
            "SK hynix HBM5 hybrid bonder Kinex Besi pilot evaluation"))
        self.assertFalse(r.relevant(
            "hbm_hybrid_bonding",
            "SK하이닉스 HBM4 한미반도체 TC 본더 442억원 수주"))
        self.assertFalse(r.relevant(
            "hbm_hybrid_bonding",
            "삼성전자 HBM4E 패키징 수율 반도체 시장 전망"))

    def test_named_supplier_context_requires_three_distinct_evidence_lanes(self):
        correction = next(r for r in m.REPORTS
                          if r["key"] == "20261119_hbm_hybrid_bonder_supplier_names_correction")
        munhwa_key = "20261119_munhwa_skhynix_20high_hybrid_bonder_report"
        previous = {
            "delivery_receipt": {"status": "confirmed", "message_ids": [526]},
            "hbm_hybrid_bonding": {"skhynix_official_hybrid_stage": "technical_feasibility"},
            "hbm_material_event_watch": {"seen_keys": [
                r["key"] for r in m.REPORTS if r is not correction
            ]},
        }
        def never(url):
            raise AssertionError("No unscheduled/acknowledged fetch: " + url)
        absent_prior = copy.deepcopy(previous)
        absent_prior["hbm_material_event_watch"]["seen_keys"].remove(munhwa_key)
        blocked_prior, out_prior, _ = m.apply(
            absent_prior, "2026-11-19T16:00:00+09:00",
            lambda _: (_ for _ in ()).throw(TimeoutError("no publisher"))
        )
        self.assertEqual(out_prior, [])
        self.assertNotIn(correction["key"],
                         blocked_prior["hbm_material_event_watch"]["seen_keys"])

        url_h = "https://www.hanwhasemitech.com/ko-mo/media/news/detail.asp?board_id=3470"
        url_n = "https://www.inews24.com/v/1959204"
        url_g = "https://www.greened.kr/news/articleView.html?idxno=337399"
        bodies = {
            url_h: "SHB2 Nano 0.1 고객사 하이브리드 본더 평가",
            url_n: "한화세미텍 SK하이닉스 2세대 하이브리드 본더. 어플라이드머티어리얼즈 BESI",
            url_g: "SK하이닉스 베시 키넥스 Datacon 본딩 시스템 평가",
        }
        def confirmed(url):
            if url not in bodies:
                raise TimeoutError("source not reachable")
            return bodies[url]
        verified, messages, audit = m.apply(
            previous, "2026-11-19T17:00:00+09:00", confirmed
        )
        self.assertEqual(audit["verified_events"], 1)
        self.assertEqual(audit["verified_keys"], [correction["key"]])
        self.assertEqual(len(messages), 1)
        rendered = messages[0]
        for expected in ("한화세미텍", "SHB2 Nano", "Datacon 8800 CHAMEO",
                         "어플라이드 머티어리얼즈", "베시(Besi)",
                         "TC Bonder 4.5 Griffin", "442억원",
                         "양산 장비 확정", "신규 계약 상대방"):
            self.assertIn(expected, rendered)
        self.assertIn(url_h, rendered)
        self.assertIn(url_n, rendered)
        self.assertIn(url_g, rendered)
        self.assertTrue(all(len(x.encode("utf-16-le")) // 2 <= 3600
                            for x in d.chunks(rendered)))
        self.assertEqual(verified["delivery_receipt"], previous["delivery_receipt"])
        self.assertEqual(verified["hbm_hybrid_bonding"], previous["hbm_hybrid_bonding"])
        self.assertEqual(len(verified["hbm_material_event_watch"]["seen_keys"]),
                         len(m.REPORTS))
        _, repeated, again = m.apply(verified, "2026-11-20T10:00:00+09:00", never)
        self.assertEqual(repeated, [])
        self.assertEqual(again["verified_events"], 0)

        def inews_only(url):
            if url in (url_h, url_n):
                return bodies[url]
            raise TimeoutError("other media not reachable")
        held, no_send, gaps = m.apply(
            previous, "2026-11-19T18:00:00+09:00", inews_only
        )
        self.assertEqual(no_send, [])
        self.assertNotIn(correction["key"], held["hbm_material_event_watch"]["seen_keys"])
        self.assertIn("independent_publishers_insufficient",
                      [e["status"] for e in gaps["gaps"]])

        held2, no_send2, gaps2 = m.apply(
            previous, "2026-11-19T18:00:00+09:00",
            lambda _: (_ for _ in ()).throw(TimeoutError("offline"))
        )
        self.assertEqual(no_send2, [])
        self.assertNotIn(correction["key"], held2["hbm_material_event_watch"]["seen_keys"])
        self.assertIn("required_independent_evidence_missing",
                      [e["status"] for e in gaps2["gaps"]])


    def test_nvidia_390bn_commitment_official_and_independent_sources_once(self):
        record = next(row for row in m.REPORTS if
                      row["key"] == "20261118_nvidia_fy27q3_memory_supply_capacity_390bn")
        official = "https://www.sec.gov/Archives/edgar/data/1045810/000104581026000088/q3fy27cfocommentary.htm"
        news1 = "https://www.news1.kr/industry/general-industry/6357997"
        bodies = {
            official: ("As of October 25, 2026 NVIDIA supply commitments increased "
                       "from $279 billion last quarter to $390 billion, primarily "
                       "related to multi-year procurement of memory supply. "
                       "Remainder 2027 69, 2028 $ 203, 2029 $ 92."),
            news1: ("엔비디아 공급약정 3900억 달러, 전분기 2790억 달러에서 증가. "
                    "메모리 장기구매 확대. 2028 회계연도 2030억 달러, "
                    "2029 회계연도 920억 달러."),
        }
        past = {
            "delivery_receipt": {"status": "confirmed", "message_ids": [527]},
            "hbm_material_event_watch": {"seen_keys": [
                row["key"] for row in m.REPORTS if row is not record
            ]},
        }
        def fetch(url):
            return bodies[url]
        before, alerts_early, audit_early = m.apply(
            past, "2026-11-18T23:59:00+09:00",
            lambda _: (_ for _ in ()).throw(AssertionError("before recovery gate")))
        self.assertEqual(alerts_early, [])
        self.assertEqual(audit_early["verified_events"], 0)

        after, alerts, audit = m.apply(
            past, "2026-11-19T23:30:00+09:00", fetch)
        self.assertEqual(audit["verified_events"], 1)
        self.assertEqual(audit["verified_keys"], [record["key"]])
        self.assertEqual(len(alerts), 1)
        content = alerts[0]
        for item in ("3,900억달러", "+1,110억달러", "+39.8%", "2,030억달러",
                     "920억달러", "5,180억달러", "HBM4", "SOCAMM",
                     "전액 HBM4", "확정 매출", "공식 제출·독립 보도"):
            self.assertIn(item, content)
        self.assertIn(official, content)
        self.assertIn(news1, content)
        self.assertNotIn("업체별 확인 근거", content)
        self.assertEqual(after["delivery_receipt"], past["delivery_receipt"])
        m.require_durable_seen_keys(past, after)
        self.assertTrue(all(len(x.encode("utf-16-le")) // 2 <= 3600
                            for x in d.chunks(content)))
        _, repeated, check = m.apply(
            after, "2026-11-20T06:23:00+09:00",
            lambda _: (_ for _ in ()).throw(AssertionError("already acknowledged")))
        self.assertEqual(repeated, [])
        self.assertEqual(check["verified_events"], 0)

    def test_nvidia_390bn_official_failure_and_unverified_media_hold_state(self):
        record = next(row for row in m.REPORTS if
                      row["key"] == "20261118_nvidia_fy27q3_memory_supply_capacity_390bn")
        official = record["evidence_groups"][0][1][0][1]
        news1 = record["evidence_groups"][1][1][0][1]
        valid_official = ("NVIDIA supply commitments from $279 billion last quarter "
                          "to $390 billion, primarily related to multi-year procurement "
                          "of memory supply; 2028 203, 2029 92.")
        valid_news = ("엔비디아 3900억 2790억 메모리 2028 2029.")
        existing = {"hbm_material_event_watch": {"seen_keys": [
            row["key"] for row in m.REPORTS if row is not record
        ]}}
        scenarios = (
            lambda url: (_ for _ in ()).throw(TimeoutError("offline")),
            lambda url: valid_news if url == news1 else
                (_ for _ in ()).throw(TimeoutError("official blocked")),
            lambda url: valid_official if url == official else
                (_ for _ in ()).throw(TimeoutError("press blocked")),
            lambda url: (valid_official.replace("$390 billion", "$290 billion")
                         if url == official else valid_news),
            lambda url: (valid_official if url == official else
                         valid_news.replace("3900억", "3000억").replace("2790억", "2700억")),
        )
        for fetch in scenarios:
            with self.subTest(scenario=repr(fetch)):
                state, output, audit = m.apply(
                    existing, "2026-11-19T23:35:00+09:00", fetch)
                self.assertEqual(output, [])
                self.assertEqual(audit["verified_events"], 0)
                self.assertNotIn(record["key"], state["hbm_material_event_watch"]["seen_keys"])
                self.assertTrue(audit["gaps"])
                self.assertIn("required_independent_evidence_missing",
                              [x["status"] for x in audit["gaps"]])


    def test_nvidia_sec_http_blocked_accepts_exact_original_mirror_only_with_independent_news(self):
        row = next(x for x in m.REPORTS
                   if x["key"] == "20261118_nvidia_fy27q3_memory_supply_capacity_390bn")
        primary = row["evidence_groups"][0][1][0][1]
        mirror = row["evidence_groups"][0][1][1][1]
        news1 = row["evidence_groups"][1][1][0][1]
        exact = ("NVIDIA CFO Commentary supply commitments increased from "
                 "$279 billion last quarter to $390 billion primarily related "
                 "to the multi-year procurement of memory supply. "
                 "Fiscal 2028 $203 2029 $92.")
        press = ("엔비디아 메모리 3900억 달러, 종전 2790억 달러로 "
                 "2028 회계연도 2030억 달러, 2029 회계연도 920억 달러.")
        state = {"delivery_receipt": {"status": "confirmed", "message_ids": [527]},
                 "hbm_material_event_watch": {"seen_keys": [
                     r["key"] for r in m.REPORTS if r is not row]}}
        def simulated(url):
            if url == primary:
                raise OSError("SEC rejects hosted runner")
            if url == mirror:
                return exact
            if url == news1:
                return press
            raise OSError("not needed")
        candidate, alerts, audit = m.apply(state, "2026-11-19T23:58:00+09:00", simulated)
        self.assertEqual(audit["verified_events"], 1)
        self.assertIn(row["key"], candidate["hbm_material_event_watch"]["seen_keys"])
        self.assertEqual(candidate["delivery_receipt"], state["delivery_receipt"])
        self.assertEqual(len(alerts), 1)
        self.assertIn(mirror, alerts[0])
        self.assertIn(news1, alerts[0])
        self.assertIn(primary, alerts[0])  # Original SEC link retained for user.
        self.assertIn("동일 재게시", alerts[0])
        self.assertTrue(d.chunks(alerts[0]))
        failed_fetch=lambda url: exact if url == mirror else (_ for _ in ()).throw(OSError("blocked"))
        no_change, notice, blocked = m.apply(state, "2026-11-19T23:58:00+09:00", failed_fetch)
        self.assertEqual(notice, [])
        self.assertNotIn(row["key"], no_change["hbm_material_event_watch"]["seen_keys"])
        self.assertTrue(blocked["gaps"])


    def test_nvidia_hbm_alert_compact_single_fx_and_complete_facts(self):
        import currency_krw_guard as krw
        row = next(x for x in m.REPORTS
                   if x["key"] == "20261118_nvidia_fy27q3_memory_supply_capacity_390bn")
        self.assertIn("메모리 장기조달", row["short_title"])
        self.assertNotIn("2,790억달러", row["short_title"])
        obs = {**row, "source": "https://www.stocktitan.net/example",
               "source_label": "SEC 동일 재게시", "lineage": "동일 원문",
               "verified_source_links": (
                   ("SEC 동일 재게시", "https://www.stocktitan.net/example"),
                   ("연합뉴스 독립 보도", "https://www.yna.co.kr/view/AKR20261118027500009"),
               ),
               "verified_source_caption": "엔비디아 CFO 설명 동일 공시 재게시·독립 보도"}
        raw = m.render("nvidia_commitments", [obs], "2026-11-20T00:11:00+09:00")
        with patch("currency_krw_guard._rate", return_value=(1328.45, "test")):
            converted = krw.enforce_text(raw, hbm_mode=True)
        for term in ("2,790억달러", "3,900억달러", "1,110억달러",
                     "2,030억달러", "920억달러", "100억달러", "80억달러",
                     "5,180억달러", "280억달러", "740억달러", "200억달러",
                     "60억달러", "1,158억달러", "1,076억달러", "1,300억달러",
                     "70→75%", "SOCAMM", "HBM4E", "확정 매출"):
            self.assertIn(term, converted)
        for wrong in ("기사 발표 당시 원화 환산", "약 520조8,000억원", "억원)(약 "):
            self.assertNotIn(wrong, converted)
        self.assertEqual(len(d.chunks(converted)), 1)
        self.assertLessEqual(len(converted.encode("utf-16-le")) // 2, 3300)
        import html as html_module, re as re_module
        visible = html_module.unescape(re_module.sub(r"<[^>]+>", "", converted))
        self.assertLessEqual(len(visible), 1900)
        self.assertIn("엔비디아 CFO 설명 동일 공시 재게시", visible)
        self.assertIn("USD/KRW", visible)


    def test_nvidia_compact_layout_never_resends_acknowledged_key(self):
        key = "20261118_nvidia_fy27q3_memory_supply_capacity_390bn"
        previous = {"delivery_receipt": {"status": "confirmed", "message_ids": [535]},
                    "hbm_material_event_watch": {"seen_keys": [r["key"] for r in m.REPORTS]}}
        def no_fetch(_):
            raise AssertionError("Already acknowledged material event must not refetch or resend")
        updated, messages, audit = m.apply(previous, "2026-11-20T07:23:00+09:00", no_fetch)
        self.assertEqual(messages, [])
        self.assertEqual(audit["verified_events"], 0)
        self.assertIn(key, updated["hbm_material_event_watch"]["seen_keys"])
        self.assertEqual(previous["delivery_receipt"], updated["delivery_receipt"])



    def test_samsung_2029_booking_2031_demand_report_preserves_contract_stages(self):
        report = next(row for row in m.REPORTS
                      if row["key"] == "20261121_samsung_memory_2029_booking_2031_lta_report")
        official = report["evidence_groups"][0][1][0][1]
        call = report["evidence_groups"][1][1][0][1]
        article = report["evidence_groups"][2][1][0][1]
        valid = {
            official: "삼성전자 2026년 3분기 HBM4 서버용 SSD 시설투자 메모리 판매 확대",
            call: "삼성전자 주요 10곳 LTA 체결 추가 10곳 협상. 60~70% 목표, 2027 HBM 물량.",
            article: ("삼성전자 2027~2029년 메모리 공급능력 대부분 계약 확보, 2031년 "
                      "장기계약 요청. 주요 10곳 2030년 60~70% 목표. "
                      "HBM D램 비트 연간 20~25% 상승, 기업용 SSD 충족률 50%."),
        }
        other_keys = [r["key"] for r in m.REPORTS if r is not report]
        previous = {
            "delivery_receipt": {"status": "confirmed", "message_ids": [535]},
            "hbm_material_event_watch": {"seen_keys": other_keys},
        }
        def no_fetch(_):
            raise AssertionError("Future or already delivered event must not query sources")
        before, early, _ = m.apply(previous, "2026-11-20T23:59:00+09:00", no_fetch)
        self.assertEqual(early, [])
        self.assertNotIn(report["key"], before["hbm_material_event_watch"]["seen_keys"])
        after, msgs, audit = m.apply(
            previous, "2026-11-22T17:30:00+09:00", lambda url: valid[url])
        self.assertEqual(audit["verified_events"], 1)
        self.assertEqual(audit["verified_keys"], [report["key"]])
        self.assertEqual(len(msgs), 1)
        notice = msgs[0]
        for term in ("2027~2029년", "2031년", "고객 10곳", "추가 10곳",
                     "60~70%", "20~25%", "기업용 SSD 50%", "HBM",
                     "공급 충족률", "독립", "기사", "미공개", "가격"):
            self.assertIn(term, notice)
        for source in (official, call, article):
            self.assertIn(source, notice)
        self.assertEqual(after["delivery_receipt"], previous["delivery_receipt"])
        self.assertIn(report["key"], after["hbm_material_event_watch"]["seen_keys"])
        m.require_durable_seen_keys(previous, after)
        self.assertEqual(len(d.chunks(notice)), 1)
        self.assertTrue(all(len(chunk.encode("utf-16-le")) // 2 <= 3600 for chunk in d.chunks(notice)))
        repeat, no_msg, checked = m.apply(after, "2026-11-22T18:00:00+09:00", no_fetch)
        self.assertEqual(no_msg, [])
        self.assertEqual(checked["verified_events"], 0)
        self.assertEqual(repeat["hbm_material_event_watch"]["seen_keys"],
                         after["hbm_material_event_watch"]["seen_keys"])

    def test_samsung_2031_only_reported_and_independent_evidence_gates(self):
        report = next(row for row in m.REPORTS
                      if row["key"] == "20261121_samsung_memory_2029_booking_2031_lta_report")
        official = report["evidence_groups"][0][1][0][1]
        call = report["evidence_groups"][1][1][0][1]
        article = report["evidence_groups"][2][1][0][1]
        mirror = report["evidence_groups"][2][1][1][1]
        official_body = "삼성전자 2026년 3분기 HBM4 SSD 시설투자"
        call_body = "삼성전자 10곳 계약, 추가 10곳 협상. 60~70% 2027 HBM4."
        article_body = ("삼성전자 2027~2029 메모리 생산능력 대부분 계약 2031 "
                        "요청 10곳, 2030 60~70% HBM 비트 20~25% SSD 50%")
        reprint_body = ("Samsung memory manufacturing capacity 2027 2029 booked "
                        "through 2031 according to Economy Tribune. 60% HBM")
        base = {"hbm_material_event_watch": {"seen_keys": [
            r["key"] for r in m.REPORTS if r is not report]}}
        def blocked(_):
            raise TimeoutError("provider unavailable")
        no_update, notices, audit = m.apply(base, "2026-11-22T17:45:00+09:00", blocked)
        self.assertEqual(notices, [])
        self.assertNotIn(report["key"], no_update["hbm_material_event_watch"]["seen_keys"])
        self.assertTrue(audit["gaps"])
        cases = [
            lambda url: official_body if url == official else blocked(url),
            lambda url: article_body if url == article else blocked(url),
            lambda url: call_body if url == call else blocked(url),
            lambda url: {
                official: official_body,
                call: call_body,
                article: article_body.replace("2031", "2028"),
            }.get(url, "") if url in (official, call, article) else blocked(url),
        ]
        for fetch in cases:
            out, msgs, audit = m.apply(base, "2026-11-22T17:45:00+09:00", fetch)
            self.assertEqual(msgs, [])
            self.assertNotIn(report["key"], out["hbm_material_event_watch"]["seen_keys"])
            self.assertIn("required_independent_evidence_missing",
                          [g["status"] for g in audit["gaps"]])
        def fallback(url):
            if url == official:
                return official_body
            if url == call:
                return call_body
            if url == mirror:
                return reprint_body
            raise TimeoutError("original publisher unavailable")
        out, msgs, audit = m.apply(base, "2026-11-22T17:55:00+09:00", fallback)
        self.assertEqual(len(msgs), 1)
        self.assertIn(report["key"], out["hbm_material_event_watch"]["seen_keys"])
        self.assertIn("Wccftech", msgs[0])
        self.assertIn("별도 독립 입증이 아님", msgs[0])
        self.assertIn(article, msgs[0])
        self.assertEqual(audit["verified_events"], 1)
        # No secondary story becomes official 2029 contracted output.
        self.assertIn("공식", report["brief_caution"])
        self.assertIn("협의", " ".join(report["brief_facts"]))
        self.assertIn("2029년", " ".join(report["brief_facts"]))


    def test_samsung_lta_compact_visual_and_complete_numerics(self):
        import html as html_module
        import re as re_module
        row = next(x for x in m.REPORTS
                   if x["key"] == "20261121_samsung_memory_2029_booking_2031_lta_report")
        official = row["evidence_groups"][0][1][0][1]
        call = row["evidence_groups"][1][1][0][1]
        article = row["evidence_groups"][2][1][0][1]
        proof = {**row, "source": article, "source_label": "단독 원보도",
                 "verified_source_links": (
                     ("삼성 공식", official), ("회사발언 취재", call),
                     ("이코노미트리뷴", article))}
        notice = m.render("samsung_memory_lta", [proof], "2026-11-22T17:33:00+09:00")
        visible = html_module.unescape(re_module.sub(r"<[^>]+>", "", notice))
        for term in ("2027~2029년", "2031년", "10곳", "추가 10곳",
                     "2030년", "60~70%", "20~25%", "HBM", "범용 D램",
                     "기업용 SSD 50%", "소비자용", "키옥시아", "가격",
                     "선수금", "미공개", "재인용", "독립"):
            self.assertIn(term, visible)
        self.assertLessEqual(len(visible), 1350)
        self.assertEqual(len(d.chunks(notice)), 1)
        self.assertEqual(notice.count(article), 1)
        self.assertEqual(notice.count(official), 1)
        self.assertEqual(notice.count(call), 1)
        self.assertNotIn("비교 근거:", notice)
        self.assertNotIn("삼성 공식 실적·컨퍼런스콜 검증·원보도", notice)

    def test_samsung_lta_compact_reprint_keeps_original_link_and_stage(self):
        row = next(x for x in m.REPORTS
                   if x["key"] == "20261121_samsung_memory_2029_booking_2031_lta_report")
        official = row["evidence_groups"][0][1][0][1]
        call = row["evidence_groups"][1][1][0][1]
        mirror = row["evidence_groups"][2][1][1][1]
        article = row["evidence_groups"][2][1][0][1]
        proof = {**row, "source": mirror, "source_label": "재인용",
                 "verified_source_links": (
                     ("삼성 실적", official), ("컨콜", call), ("Wccftech 재인용", mirror))}
        rendered = m.render("samsung_memory_lta", [proof], "2026-11-22T17:45:00+09:00")
        self.assertIn("Wccftech(재인용)", rendered)
        self.assertIn("원문(직접 확인 전)", rendered)
        for url in (official, call, mirror, article):
            self.assertIn(url, rendered)
        self.assertEqual(len(d.chunks(rendered)), 1)


if __name__ == "__main__":
    unittest.main()
