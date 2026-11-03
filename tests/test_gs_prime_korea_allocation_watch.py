"""Tests never send Telegram messages or update live watch state."""
import datetime as dt
import json
import pathlib
import tempfile
import unittest
from unittest.mock import patch
from zoneinfo import ZoneInfo

import gs_prime_korea_allocation_watch as w

ARTICLE = """Goldman Sachs FICC and Equities. As of October 14, 2026.
Exhibit 3: Korea allocations have declined 75 bps MTD October to 3.64%
(32nd percentile 1-year and 86th percentile 5-year).
Gross allocation is at 2.59% (41st percentile 1-year, 88th percentile 5-year).
Exhibit 4: Taiwan allocations increased to 7.2%. Gross allocation at 4.5%."""
NOW = dt.datetime(2026, 11, 4, 10, 0, tzinfo=ZoneInfo("Asia/Seoul"))


class GoldmanKoreaAllocationTests(unittest.TestCase):
    def test_korea_numbers_separate_from_taiwan(self):
        r = w.parse_document("<html><body>" + ARTICLE + "</body></html>",
                             "https://alpharis.cn/events/2386", NOW)
        self.assertEqual(r["asof"], "2026-10-14")
        self.assertEqual(r["net"], 3.64)
        self.assertEqual(r["gross"], 2.59)
        self.assertEqual(r["net_1y_percentile"], 32)
        self.assertEqual(r["gross_1y_percentile"], 41)

    def test_asia_net_leverage_must_not_be_korea_share(self):
        s = "Goldman Sachs Korea foreign selling. Asia Fundamental L/S net leverage 48.0% Gross allocation China 6.9%."
        self.assertIsNone(w.parse_document(s, "https://finvaulta.com/research/goldman-sachs/2026-10-30", NOW))

    def test_both_metrics_required_and_no_cross_country_mix(self):
        s = "Goldman Sachs As of October 30, 2026. Korea allocations declined to 3.2%. Taiwan gross allocation is at 4.4%."
        self.assertIsNone(w.parse_document(s, "https://alpharis.cn/events/2399", NOW))

    def test_no_unknown_date(self):
        s = "Goldman Sachs. Korea allocations decreased to 3.2%. Gross allocation is at 2.5%."
        self.assertIsNone(w.parse_document(s, "https://alpharis.cn/events/2399", NOW))

    def test_old_report_baseline_not_alert(self):
        r = w.parse_document(ARTICLE, "https://alpharis.cn/events/2386", NOW)
        event, known, reason = w.select([r], NOW, None, set())
        self.assertIsNone(event)
        self.assertEqual(known["asof"], "2026-10-14")
        self.assertIn("오래된", reason)

    def test_new_report_once_and_revisions_distinct(self):
        recent = dict(w.parse_document(ARTICLE, "https://alpharis.cn/events/2386", NOW))
        recent["asof"] = "2026-11-03"
        cand, known, _ = w.select([recent], NOW, None, set())
        self.assertIsNotNone(cand)
        self.assertIn("2.59%", w.format_alert(cand, None))
        dup, _, _ = w.select([recent], NOW, known, {w.event_key(recent)})
        self.assertIsNone(dup)
        revised = dict(recent, gross=2.58)
        changed, _, _ = w.select([revised], NOW, known, {w.event_key(recent)})
        self.assertIsNotNone(changed)

    def test_same_day_conflicting_public_values_fail_closed(self):
        row = w.parse_document(ARTICLE, "https://alpharis.cn/events/2386", NOW)
        first = dict(row, asof="2026-11-03")
        other = dict(first, net=4.1, source="https://finvaulta.com/a", source_domain="finvaulta.com")
        cand, known, reason = w.select([first, other], NOW, None, set())
        self.assertIsNone(cand)
        self.assertIsNone(known)
        self.assertIn("수치 충돌", reason)

    def test_publication_date_not_observation_date(self):
        s = "<html><head><meta property='article:published_time' content='2026-11-03'></head><body>Goldman Sachs. Korea allocations declined to 3.4%. Gross allocation is at 2.4%.</body></html>"
        row = w.parse_document(s, "https://finvaulta.com/research/goldman-sachs/recent", NOW)
        self.assertIsNotNone(row)
        self.assertNotEqual(row["date_basis"], "관측일")
        cand, _, reason = w.select([row], NOW, None, set())
        self.assertIsNone(cand)
        self.assertIn("관측일", reason)

    def test_dynamic_discovery_prioritizes_new_reports_and_preserves_fallback(self):
        index = '<html><a href="https://finvaulta.com/research/goldman-sachs/em-weekly-2026-11-04">new</a></html>'
        with patch.object(w, "rss_links", return_value=([], False)), \
             patch.object(w, "fetch", side_effect=lambda u, timeout=7: index if u.endswith("/research/goldman-sachs") else "<html></html>"):
            urls, ok = w.discover()
        self.assertTrue(ok)
        self.assertTrue(urls[0].endswith("2026-11-04"))
        self.assertIn("https://alpharis.cn/events/2386", urls)

    def test_no_new_source_does_not_send_and_state_waits_for_delivery(self):
        with tempfile.TemporaryDirectory() as d:
            status = pathlib.Path(d) / "status.md"
            pending = pathlib.Path(d) / "pending.json"
            alert = pathlib.Path(d) / "alert.html"
            with patch.object(w, "STATE", pathlib.Path(d) / "state.json"), \
                 patch.object(w, "STATUS", status), \
                 patch.object(w, "PENDING", pending), \
                 patch.object(w, "ALERT", alert), \
                 patch.object(w, "discover", return_value=([], False)):
                self.assertEqual(w.main(), 0)
                self.assertFalse(alert.exists())
                state = json.loads(pending.read_text())
                self.assertFalse(state["seen_keys"])
                self.assertIn("원천 접근 실패", status.read_text())


if __name__ == "__main__":
    unittest.main()
