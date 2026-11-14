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

class MaterialEventTests(unittest.TestCase):
    def fixture(self, report):
        return ("원보도 2026년 11월 주요 사실 " +
                " ".join(group[0] for group in report["need"]) +
                " 세부사항 검증 완료" * 12)

    def test_all_seven_reports_detected_only_with_original_evidence(self):
        current = {"seen_ids": ["existing-event"], "delivery_receipt": {"message_ids": [387]}}
        expected = {x["key"] for x in m.REPORTS}
        result, rendered, audit = m.apply(current, "2026-11-14T20:00:00+09:00", lambda url: self.fixture(next(
            r for r in m.REPORTS if url in [x[1] for x in r["sources"]]
        )))
        self.assertEqual(audit["verified_events"], 7)
        self.assertEqual(set(result["hbm_material_event_watch"]["seen_keys"]), expected)
        self.assertEqual(len(rendered), 3)
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
        self.assertEqual(len(result["hbm_material_event_watch"]["seen_keys"]), 7)

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
            p.parent.mkdir()
            p.write_text(json.dumps({"memory_axes": {"keep": 1}}), encoding="utf-8")
            with patch.object(m, "PENDING", p), patch.object(m, "ALERT", a), patch.object(m, "AUDIT", c):
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

if __name__ == "__main__":
    unittest.main()
