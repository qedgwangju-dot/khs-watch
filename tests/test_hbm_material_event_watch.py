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
                       "31%→51%", "22%→2027년 31%", "2028년", "3만6,000"):
            self.assertIn(needle, alert)
        self.assertIn("전체 가격대가 100% 이상", alert)
        self.assertIn("11월 17일", alert)  # already monitored NAND event, no duplicate
        self.assertEqual(updated["delivery_receipt"], previous["delivery_receipt"])
        self.assertEqual(len(updated["hbm_material_event_watch"]["seen_keys"]), len(m.REPORTS))
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

if __name__ == "__main__":
    unittest.main()
