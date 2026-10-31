"""Offline regression tests for the Wonyotti Telegram watch."""
import datetime as dt
import unittest
from unittest.mock import patch

from scripts import wonyotti_90d_thesis_watch as w


def flow(date="2026-10-30", daily=-643.2, five=-202.4, status="complete"):
    return {
        "date": date,
        "daily_usd_m": daily,
        "five_day_usd_m": five,
        "status": status,
        "five_day_complete": status == "complete",
        "previous_five_day_complete": True,
        "previous_five_day_usd_m": 302.9,
        "previous_five_day_dates": [
            "2026-10-23", "2026-10-26", "2026-10-27", "2026-10-28", "2026-10-29",
        ],
        "five_day_dates": [
            "2026-10-26", "2026-10-27", "2026-10-28", "2026-10-29", "2026-10-30",
        ],
        "trigger_ready": True,
        "source_url": w.FARSIDE_BTC,
    }


def snap(btc=77108, five=-202.4, verified=True, etf_complete=True):
    return {
        "crypto": {
            "price_trigger_ready": verified,
            "prices": {
                "BTC": {"usd": btc, "verified": verified, "change24": -1.3},
                "ETH": {"usd": 2237.0, "verified": verified, "change24": 0.0},
                "SOL": {"usd": 95.97, "verified": verified, "change24": -1.3},
            },
            "btc_etf": flow(five=five, status="complete" if etf_complete else "partial"),
            "eth_etf": flow(daily=-155.7, five=-431.4),
        },
        "nvidia_sec": {
            "parsed_ok": True,
            "accounts_receivable_m": 63059,
            "revenue_q_m": 96221,
        },
    }


NOW = dt.datetime(2026, 10, 31, 15, 20, tzinfo=w.KST)


class WonyottiRegressionTest(unittest.TestCase):
    def test_official_flow_six_dates_and_previous_window(self):
        rows = [
            ("23 Oct 2026", -137.9),
            ("26 Oct 2026", 110.3),
            ("27 Oct 2026", 176.0),
            ("28 Oct 2026", 137.3),
            ("29 Oct 2026", 17.2),
            ("30 Oct 2026", -643.2),
        ]
        html = "<table>" + "".join(
            "<tr><td>" + day + "</td><td>" + (
                "(" + str(abs(val)) + ")" if val < 0 else str(val)
            ) + "</td><td>" + (
                "(" + str(abs(val)) + ")" if val < 0 else str(val)
            ) + "</td></tr>" for day, val in rows
        ) + "</table>"
        with patch.object(w, "fetch", return_value=html.encode()):
            out = w.farside_flow(w.FARSIDE_BTC)
        self.assertEqual(out["previous_five_day_usd_m"], 302.9)
        self.assertEqual(out["five_day_usd_m"], -202.4)
        self.assertTrue(out["five_day_complete"])
        self.assertEqual(out["date"], "2026-10-30")

    def test_correct_previous_window_even_if_old_same_day_was_partial(self):
        old = {"crypto": {"btc_etf": flow(daily=-409.5, five=31.3, status="partial")}}
        new = {"crypto": {"btc_etf": flow()}}
        hits = w.build_signals(old, new, [])
        self.assertEqual(len(hits), 1)
        self.assertIn("302.9", hits[0][2])
        self.assertIn("-202.4", hits[0][2])
        self.assertNotIn("+31.3", hits[0][2])
        self.assertIn("전환", hits[0][1])

    def test_same_etf_observation_is_silent(self):
        v = {"crypto": {"btc_etf": flow()}}
        self.assertEqual(w.build_signals(v, v, []), [])

    def test_deduplicate_same_day_same_market_event(self):
        crypto = {"btc_etf": flow()}
        event = (
            "암호화폐",
            "BTC ETF 최근 5거래일 순유입에서 순유출로 전환",
            "details",
            "meaning",
            "next",
            None,
        )
        first, keys = w.deduplicate_etf_events([event], crypto, [])
        second, _ = w.deduplicate_etf_events([event], crypto, keys)
        self.assertEqual(len(first), 1)
        self.assertEqual(len(second), 0)

    def test_krw_conversion(self):
        line = w._money_usd_m(-643.2, {"rate": 1335.3})
        self.assertEqual(line, "-6억4,320만달러(약 -8,589억원)")

    def test_bearish_pressure_is_plain(self):
        verdict = w._crypto_direction(snap(), NOW)
        self.assertEqual(verdict["direction"], "단기 하락 압력 우세")

    def test_mixed_flows_not_called_bearish(self):
        verdict = w._crypto_direction(snap(five=200.0), NOW)
        self.assertIn("혼조", verdict["direction"])

    def test_price_source_failure_suspends_direction(self):
        verdict = w._crypto_direction(snap(verified=False), NOW)
        self.assertEqual(verdict["direction"], "판단 보류")

    def test_provisional_flow_suspends_direction(self):
        verdict = w._crypto_direction(snap(etf_complete=False), NOW)
        self.assertEqual(verdict["direction"], "판단 보류")

    def test_alert_starts_with_verdict_and_omits_static_nvidia(self):
        signal = (
            "암호화폐",
            "BTC ETF 최근 5거래일 순유입에서 순유출로 전환",
            "이전 302.9 → 최신 -202.4",
            "기대감",
            "ETF",
            w.FARSIDE_BTC,
        )
        with patch.object(w, "_read_official_fx", return_value={"rate": 1335.3, "date": "2026-10-30"}):
            text = w.build_alert([signal], NOW, snap())
        self.assertIn("단기 하락 압력 우세", text)
        self.assertLess(text.index("[지금 방향"), text.index("[이번에 실제"))
        self.assertIn("원화 환산", text)
        self.assertNotIn("63.06B", text)
        self.assertIn("85,000달러", text)

    def test_technical_only_alert_does_not_claim_market_direction(self):
        tech = (
            "감시원천 이상",
            "암호화폐 가격 2회 연속 조회 실패",
            "투자판정 보류",
            "기술 경보",
            "다음 조회",
            None,
        )
        text = w.build_alert([tech], NOW, snap())
        self.assertIn("기술 알림", text)
        self.assertNotIn("단기 하락 압력 우세", text)
        self.assertNotIn("63.06B", text)


if __name__ == "__main__":
    unittest.main()
