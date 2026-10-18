"""Offline regression tests for official Treasury real-yield decompositions."""
import unittest
from unittest.mock import Mock

import treasury_real_yield_signal as tips


DATES = [
    "2026-10-08", "2026-10-09", "2026-10-13",
    "2026-10-14", "2026-10-15", "2026-10-16",
]
NOM = [5.00, 5.06, 5.12, 5.18, 5.21, 5.25]
REAL = [2.60, 2.65, 2.67, 2.75, 2.80, 2.85]


def xml_sample(key, values, dates=DATES):
    entries = "".join(
        "<entry><content><m:properties>"
        f"<d:NEW_DATE>{date}T00:00:00</d:NEW_DATE>"
        f"<d:{key}>{value:.2f}</d:{key}>"
        "</m:properties></content></entry>"
        for date, value in zip(dates, values)
    )
    return (
        '<feed xmlns="http://www.w3.org/2005/Atom" '
        'xmlns:m="http://schemas.microsoft.com/ado/2007/08/dataservices/metadata" '
        'xmlns:d="http://schemas.microsoft.com/ado/2007/08/dataservices">'
        + entries + "</feed>"
    ).encode("utf-8")


class FakeSession:
    def get(self, url, **kw):
        v, field = (NOM, "BC_10YEAR") if "data=daily_treasury_yield_curve&" in url else (REAL, "TC_10YEAR")
        response = Mock()
        response.content = xml_sample(field, v)
        response.raise_for_status = Mock()
        return response


class TreasuryRealYieldTests(unittest.TestCase):
    def test_real_tips_field_and_nominal_field(self):
        self.assertEqual(tips.parse_feed(xml_sample("TC_10YEAR", REAL), "TC_10YEAR")["2026-10-16"], 2.85)
        self.assertEqual(tips.parse_feed(xml_sample("BC_10YEAR", NOM), "BC_10YEAR")["2026-10-16"], 5.25)

    def test_five_aligned_sessions_and_inflation_compensation(self):
        data = tips.decompose(dict(zip(DATES, NOM)), dict(zip(DATES, REAL)), "2026-10-16", 5.25)
        self.assertEqual(data["five"], "2026-10-08")
        self.assertAlmostEqual(data["real5"], 25.0, places=3)
        self.assertAlmostEqual(data["bei5"], 0.0, places=3)
        self.assertAlmostEqual(data["bei"], 2.40, places=3)
        self.assertEqual(tips.classify(data)[0], "실질금리 5거래일 급등·시장 내재 물가상승률 안정")

    def test_stale_real_yield_must_not_be_forward_filled(self):
        with self.assertRaisesRegex(tips.CurveMismatch, "날짜 불일치"):
            tips.decompose(dict(zip(DATES, NOM)), dict(zip(DATES[:-1], REAL[:-1])), "2026-10-16", 5.25)

    def test_conflicting_official_nominal_blocks_signal(self):
        with self.assertRaisesRegex(tips.CurveMismatch, "출처 불일치"):
            tips.decompose(dict(zip(DATES, NOM)), dict(zip(DATES, REAL)), "2026-10-16", 5.20)

    def test_duplicate_conflicting_entries_are_rejected(self):
        xml = xml_sample("TC_10YEAR", [2.85, 3.00], ["2026-10-16", "2026-10-16"])
        with self.assertRaisesRegex(tips.CurveMismatch, "conflicting"):
            tips.parse_feed(xml, "TC_10YEAR")

    def test_missing_prior_dates_not_imputed(self):
        d = tips.decompose({"2026-10-16": 5.25}, {"2026-10-16": 2.85}, "2026-10-16", 5.25)
        self.assertIsNone(d["real1"])
        self.assertIsNone(d["bei5"])
        self.assertIn("자료 부족", tips.build_block("2026-10-16", 5.25, FakeSession()) if False else tips.bp(d["real1"]))

    def test_new_3pct_entry_distinct_from_staying_above_3pct(self):
        d = tips.decompose(
            {"2026-10-15": 5.30, "2026-10-16": 5.34},
            {"2026-10-15": 2.99, "2026-10-16": 3.02},
            "2026-10-16", 5.34,
        )
        self.assertIn("신규 진입", tips.classify(d)[1])
        d["real1"] = 1.0
        self.assertNotIn("신규 진입", tips.classify(d)[1])

    def test_fetch_and_render_no_telegram(self):
        text = tips.build_block("2026-10-16", 5.25, FakeSession())
        self.assertIn("10년 실질(TIPS) 2.85%", text)
        self.assertIn("10년 손익분기 물가상승률(BEI=명목−실질) 2.40%", text)
        self.assertIn("5거래일", text)
        self.assertIn("data=daily_treasury_real_yield_curve", text)

    def test_different_dates_cannot_be_subtracted(self):
        with self.assertRaisesRegex(tips.CurveMismatch, "날짜 불일치"):
            tips.decompose({"2026-10-15": 5.2}, {"2026-10-16": 2.8}, "2026-10-16", 5.2)


if __name__ == "__main__":
    unittest.main()
