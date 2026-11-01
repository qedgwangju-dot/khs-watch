from __future__ import annotations

import datetime as dt
import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import us_positioning_etf_short_interest as etf


def chart(current, previous):
    return f"""<table><tr><th>Settlement Date</th><th>Short Interest %</th><th>Short Position</th><th>Days To Cover</th><th>Short Change</th><th>Change %</th></tr>
    <tr><td>2026-10-15</td><td>12.26</td><td>{current:,}</td><td>2.41</td><td>+10,000,000</td><td>16.38</td></tr>
    <tr><td>2026-09-30</td><td>10.50</td><td>{previous:,}</td><td>1.95</td><td>+4,000,000</td><td>7.19</td></tr>
    </table>"""


def benz(current, previous):
    return f"""<table><tr><th>Settlement Date</th><th>Dissemination Date</th><th>% Float</th><th>Float</th><th>Short Interest</th><th>Volume</th><th>Days to Cover</th></tr>
    <tr><td>Oct 15, 2026</td><td>Oct 26, 2026</td><td>—</td><td>—</td><td>{current:,}</td><td>33,969,720</td><td>2.41</td></tr>
    <tr><td>Sep 30, 2026</td><td>Oct 9, 2026</td><td>—</td><td>—</td><td>{previous:,}</td><td>36,049,629</td><td>1.95</td></tr>
    </table>"""


def finshort(current, previous):
    return f"""<table><tr><th>Settlement date</th><th>Short interest</th><th>Change</th></tr>
    <tr><td>Oct 15, 2026</td><td>{current:,}</td><td>+16.38%</td></tr>
    <tr><td>Sep 30, 2026</td><td>{previous:,}</td><td>+7.19%</td></tr>
    </table>"""


CALENDAR = """<table><tr><th>Settlement Date</th><th>Due Date</th><th>Publication Date</th></tr>
<tr><td>October 15 (Thursday)</td><td>October 19 – 6:00 p.m. (Monday)</td><td>October 26 (Monday)</td></tr>
<tr><td>October 30 (Friday)</td><td>November 3 – 6:00 p.m. (Tuesday)</td><td>November 10 (Tuesday)</td></tr>
</table>"""


def getter(*, spy=None, qqq=None, corrupt=False):
    values = {"QQQ": qqq or (82_001_618, 70_458_005),
              "SPY": spy or (92_995_326, 98_476_070)}

    def get(url):
        if "finra.org" in url:
            return CALENDAR
        symbol = "QQQ" if "QQQ" in url or "qqq/" in url else "SPY"
        new, old = values[symbol]
        if "chartexchange" in url:
            return chart(new + (11 if corrupt else 0), old)
        if "benzinga" in url:
            return benz(new, old)
        if "finshort" in url:
            return finshort(new, old)
        raise AssertionError("Unexpected endpoint")
    return get


class ETFShortInterestTests(unittest.TestCase):
    def test_finra_calendar_exact_dates(self):
        actual = etf.read_calendar(CALENDAR, 2026)
        self.assertEqual(actual["2026-10-15"], "2026-10-26")
        self.assertEqual(actual["2026-10-30"], "2026-11-10")

    def test_three_sources_parse_true_position_not_daily_short_volume(self):
        for source, payload in (
            ("chartexchange", chart(82_001_618, 70_458_005)),
            ("benzinga", benz(82_001_618, 70_458_005)),
            ("finshort", finshort(82_001_618, 70_458_005)),
        ):
            with self.subTest(source=source):
                rows = etf.parse_provider(source, payload)
                self.assertEqual(rows[0], {"settlement": "2026-10-15", "shares": 82_001_618})
                self.assertEqual(rows[1], {"settlement": "2026-09-30", "shares": 70_458_005})

    def test_qqq_spy_october_15_verified_divergence(self):
        data = etf.collect(now=dt.date(2026, 11, 1), getter=getter())
        self.assertEqual(data["QQQ"]["shares"], 82_001_618)
        self.assertEqual(data["QQQ"]["change_shares"], 11_543_613)
        self.assertEqual(data["SPY"]["shares"], 92_995_326)
        self.assertEqual(data["SPY"]["change_shares"], -5_480_744)
        self.assertEqual(round(data["QQQ"]["change_pct"], 2), 16.38)
        self.assertEqual(round(data["SPY"]["change_pct"], 2), -5.57)
        self.assertEqual(round(data["divergence_pp"], 2), 21.95)
        self.assertTrue(data["signal"])
        self.assertEqual(data["published"], "2026-10-26")
        self.assertTrue(all(data[t]["publisher_count"] >= 2 for t in ("QQQ", "SPY")))
        title, body = etf.render(data)
        self.assertIn("2026-10-15", body)
        self.assertIn("2026-10-26", body)
        self.assertLess(len(title) + len(body), 3900)

    def test_conflicting_source_cannot_override_two_matching_sources(self):
        data = etf.collect(now=dt.date(2026, 11, 1), getter=getter(corrupt=True))
        self.assertEqual(data["QQQ"]["shares"], 82_001_618)
        self.assertNotIn("chartexchange", data["QQQ"]["sources"])

    def test_publication_date_and_stale_gate(self):
        with self.assertRaisesRegex(RuntimeError, "not current"):
            etf.collect(now=dt.date(2026, 10, 25), getter=getter())
        with self.assertRaisesRegex(RuntimeError, "not current"):
            etf.collect(now=dt.date(2026, 11, 12), getter=getter())

    def test_no_alert_from_ordinary_same_direction_etf_shift(self):
        data = etf.collect(
            now=dt.date(2026, 11, 1),
            getter=getter(qqq=(71_000_000, 70_458_005), spy=(99_000_000, 98_476_070))
        )
        self.assertFalse(data["signal"])
        self.assertIn("ETF 헤지", etf.render(data)[1])

    def test_validate_only_never_sends_or_advances_state(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "state.json"
            with patch.object(etf, "send_message", side_effect=AssertionError("validate-only send")):
                result = etf.run(validate_only=True, now=dt.date(2026, 11, 1),
                                 getter=getter(), state_path=path)
            self.assertEqual(result["status"], "alert_due")
            self.assertFalse(result["telegram_sent"])
            self.assertFalse(path.exists())

    def test_one_verified_send_suppresses_repeats(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "state.json"
            receipt = {"message_id": 102, "chat_id_returned": True,
                       "chat_id_match": True, "bot_username": etf.EXPECTED_BOT}
            with patch.object(etf, "send_message", return_value=receipt) as sender:
                first = etf.run(validate_only=False, now=dt.date(2026, 11, 1),
                                getter=getter(), state_path=path)
                self.assertTrue(first["telegram_sent"])
                self.assertEqual(json.loads(path.read_text())["last_alert"]["message_id"], 102)
                second = etf.run(validate_only=False, now=dt.date(2026, 11, 1),
                                 getter=getter(), state_path=path)
                self.assertEqual(second["status"], "duplicate_suppressed")
                self.assertEqual(sender.call_count, 1)

    def test_corrupt_state_refuses_reset(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "state.json"
            path.write_text("{NOT JSON")
            with self.assertRaisesRegex(RuntimeError, "unreadable"):
                etf.load_state(path)

    def test_disallow_daily_short_volume_as_short_interest(self):
        with self.assertRaises(ValueError):
            etf.parse_provider("finshort", "<p>QQQ daily short volume 20,683,025 2026-10-30</p>")


if __name__ == "__main__":
    unittest.main()
