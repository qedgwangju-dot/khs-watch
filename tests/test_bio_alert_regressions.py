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
import halozyme_legal_watch_v4 as halo


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

    def test_halozyme_two_patent_article_without_case_number_is_not_dropped(self):
        text = "알테오젠 파트너 MSD, 할로자임 PH20 특허 2건 청구항 특허성 없음"
        case, patent = halo.get_case(text)
        self.assertEqual(case, "PGR2025-00033")
        self.assertEqual(patent, "12,049,652")
        self.assertEqual(halo.classify(text, case), "final_unpatentable")

    def test_halozyme_current_fwd_cases_upgrade_to_unpatentable(self):
        for case in ("PGR2025-00033", "PGR2025-00039"):
            self.assertEqual(
                halo.classify("Status Final Written Decision", case),
                "final_unpatentable",
            )

    def test_halozyme_unknown_fwd_does_not_assume_invalidity(self):
        self.assertEqual(
            halo.classify("Status Final Written Decision", "PGR2025-00042"),
            "final_decision",
        )

    def test_halozyme_alert_timeline_dates(self):
        item = {
            "published": "Fri, 25 Sep 2026 12:00:00 GMT",
        }
        self.assertEqual(
            halo.timeline_line("PGR2025-00033", "final_unpatentable", item),
            "2025-03-07 PGR 청구 → 2025-10-01 심판 개시 → 2026-09-25 최종서면결정",
        )
        self.assertEqual(
            halo.timeline_line("PGR2025-00039", "final_unpatentable", item),
            "2025-03-28 PGR 청구 → 2025-10-01 심판 개시 → 2026-09-25 최종서면결정",
        )

    def test_halozyme_portfolio_scorecard_is_separate_event(self):
        sample = (
            "파트너사 MSD가 할로자임(Halozyme)의 MDASE 관련 특허에 제기한 PGR 2건에서 "
            "PTAB이 심판 대상 청구항 모두에 대해 특허성이 없다고 최종 판단했습니다. "
            "이로써 MSD가 제기해 심리가 개시된 PGR 14건 가운데 7건에서 심판 대상 청구항의 특허성이 부정됐습니다. "
            "아직 최종 결정이 나오지 않은 나머지 7건도 이번 2건과 함께 지난 7월 23일 구술심리에서 다뤄졌습니다. "
            "특허 번호 12,049,652 / 12,104,185"
        )
        score = halo.parse_portfolio_scorecard(sample)
        self.assertIsNotNone(score)
        self.assertEqual(score["total"], 14)
        self.assertEqual(score["won"], 7)
        self.assertEqual(score["pending"], 7)
        self.assertEqual(score["oral_date"], "2026-07-23")

    def test_halozyme_final_unpatentable_alert_renders_timeline(self):
        item = {
            "published": "Fri, 25 Sep 2026 12:00:00 GMT",
            "url": "https://example.com/source",
            "title": "PGR2025-00033 Final Written Decision",
        }
        rendered = halo.alert(
            "PGR2025-00033",
            "12,049,652",
            "final_unpatentable",
            item,
        )
        self.assertIn("<b>타임라인:</b>", rendered)
        self.assertIn("2025-03-07 PGR 청구", rendered)
        self.assertIn("2026-09-25 최종서면결정", rendered)

    def test_halozyme_portfolio_ir_update_is_distinct_event(self):
        text = (
            "MSD가 제기해 심리가 개시된 PGR 14건 가운데 7건에서 "
            "심판 대상 청구항의 특허성이 부정됐습니다."
        )
        case, patent = halo.get_case(text)
        self.assertEqual(case, "HALOZYME-PGR-PORTFOLIO-7OF14")
        self.assertEqual(patent, "")
        self.assertEqual(halo.classify(text, case), "portfolio_update")
        rendered = halo.alert(
            case,
            patent,
            "portfolio_update",
            {
                "url": "https://www.alteogen.com/kr/sub/ir/information.php?bid=2&idx=374&mode=view&page=1",
                "published": "",
                "title": "알테오젠 파트너 MSD, 할로자임 MDASE 여섯 번째, 일곱 번째 특허 무효화 판정",
            },
        )
        self.assertIn("누적 판세 업데이트", rendered)
        self.assertIn("14건 중 7건", rendered)
        self.assertIn("잔여 7건", rendered)
        self.assertIn("2026-09-28 알테오젠 공식 IR", rendered)

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
