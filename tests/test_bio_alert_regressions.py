from __future__ import annotations

import pathlib
import sys
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import bio_korean_guard_strict_v2 as guard
import jemperli_altb4_watch as jem_base
import jemperli_altb4_watch_v2 as jem
import qlex_wac_ir_watch_v2 as wac


class BioAlertRegressionTests(unittest.TestCase):
    def test_jemperli_canada_cross_source_dedupes_to_one_event(self):
        a = jem_base.Item(
            "Google News",
            "GSK's Jemperli accepted for review by Health Canada for dMMR/MSI-H locally advanced rectal cancer",
            "https://markets.ft.com/example",
            "Thu, 24 Sep 2026 12:00:00 GMT",
        )
        b = jem_base.Item(
            "Google News",
            "Santé Canada accepte d'examiner la présentation de GSK concernant Jemperli pour le cancer du rectum",
            "https://www.lesaffaires.com/example",
            "Thu, 24 Sep 2026 13:00:00 GMT",
            "Jemperli dostarlimab Health Canada Project Orbis rectal cancer accepted for review",
        )
        self.assertEqual(jem.event_key(a), jem.CANADA_EVENT_KEY)
        self.assertEqual(jem.event_key(b), jem.CANADA_EVENT_KEY)
        self.assertEqual(jem.event_key(a), jem.event_key(b))

    def test_jemperli_generic_unclassified_repost_is_blocked(self):
        item = jem_base.Item(
            "Google News",
            "Jemperli regulatory update",
            "https://example.com/repost",
            "Fri, 25 Sep 2026 00:00:00 GMT",
            "Jemperli FDA regulatory update",
        )
        self.assertTrue(jem_base.is_relevant(item))
        self.assertEqual(jem._stage(item), "material")
        self.assertFalse(jem.is_relevant(item))

    def test_regulatory_identifiers_render_korean_first(self):
        rendered = guard.ensure_korean_text(
            "GSK Jemperli sBLA FDA EMA PDUFA Project Orbis"
        )
        required = (
            "추가 생물학적 제제 허가 신청(sBLA)",
            "미국 식품의약국(FDA)",
            "유럽의약품청(EMA)",
            "허가 결정 예정일(PDUFA)",
            "국제 공동심사 프로그램(Project Orbis)",
        )
        for phrase in required:
            self.assertIn(phrase, rendered)

    def test_qlex_wac_cumulative_has_krw_formatter(self):
        self.assertEqual(
            wac.format_krw_from_usd_m(1026.0, 1343.8),
            "약 1조3,787억원",
        )

    def test_single_runner_health_schema_covers_all_bio_lanes(self):
        source = (ROOT / "scripts" / "bio_single_runner.py").read_text(encoding="utf-8")
        required = (
            '"qlex_collector_rc"',
            '"qlex_wac_collector_rc"',
            '"intismeran_collector_rc"',
            '"jemperli_collector_rc"',
            '"enhertu_collector_rc"',
            '"halozyme_collector_rc"',
            '"qlex_wac_state_persisted"',
            '"halozyme_state_persisted"',
        )
        for token in required:
            self.assertIn(token, source)


if __name__ == "__main__":
    unittest.main()
