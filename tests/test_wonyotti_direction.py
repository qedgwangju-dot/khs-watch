"""Offline regression tests for the Wonyotti Telegram watch."""
import datetime as dt
import unittest
import json
import pathlib
import tempfile
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
        self.assertIn("단기 하락 압력 우세", verdict["direction"])

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


    def test_partial_large_etf_flow_is_not_prematurely_sent(self):
        prior = {"crypto": {"btc_etf": flow(date="2026-11-19", daily=-582.2, five=-1306.2)}}
        provisional = flow(date="2026-11-20", daily=-669.2, five=-1790.0, status="partial")
        provisional["previous_five_day_usd_m"] = -1306.2
        provisional["trigger_ready"] = True
        self.assertEqual(w.build_signals(prior, {"crypto": {"btc_etf": provisional}}, []), [])
        final = dict(provisional, status="complete", five_day_complete=True)
        hits = w.build_signals(prior, {"crypto": {"btc_etf": final}}, [])
        self.assertEqual(len(hits), 1)
        self.assertIn("당일 큰 규모", hits[0][1])

    def test_etf_delivery_event_identity_is_stable(self):
        event = ("암호화폐", "BTC ETF 당일 큰 규모의 순유출", "test", "", "", w.FARSIDE_BTC)
        snapshot = {"crypto": {"btc_etf": flow(date="2026-11-20", daily=-669.2, five=-1790.0)}}
        key = w._signal_delivery_key(event, snapshot, NOW)
        self.assertEqual(key, "BTC|2026-11-20|large_daily|out")

    def test_nvidia_latest_official_release_is_detectable_separately_from_10q(self):
        link = "https://nvidianews.nvidia.com/news/nvidia-announces-financial-results-for-third-quarter-fiscal-2027"
        rss = ('<rss><channel><item><title>NVIDIA Announces Financial Results for Third Quarter Fiscal 2027</title>'
               '<pubDate>Tue, 17 Nov 2026 21:20:00 GMT</pubDate>'
               '<link>' + link + '</link></item></channel></rss>')
        body = "<html><body>Revenue of $115.8 billion, up 103 percent from a year ago.</body></html>"
        def official_fetch(url, *args, **kwargs):
            return rss.encode() if url == w.NVIDIA_EARNINGS_RSS else body.encode()
        with patch.object(w, "fetch", side_effect=official_fetch):
            release, errors = w.nvidia_earnings_snapshot()
        self.assertFalse(errors, errors)
        self.assertTrue(release["verified"])
        self.assertEqual(release["revenue_b"], 115.8)
        self.assertEqual(release["date"], "2026-11-18")

    def test_one_unconfirmed_news_source_does_not_poison_future_corroboration(self):
        published = dt.datetime.now(w.KST).isoformat(timespec="seconds")
        reuters = {
            "title": "Microsoft raises AI capex guidance 10% for data center buildout",
            "description": "AI capex guidance increased", "source": "Reuters",
            "link": "https://example.com/official-article-a", "published": published,
        }
        bloomberg = {
            "title": "Microsoft raises AI capex guidance 10% for data center buildout",
            "description": "AI capex guidance increased", "source": "Bloomberg",
            "link": "https://example.com/official-article-b", "published": published,
        }
        def single_source(query):
            return [dict(reuters)] if query.startswith('"Microsoft"') else []
        def two_sources(query):
            return [dict(reuters), dict(bloomberg)] if query.startswith('"Microsoft"') else []
        with patch.object(w, "google_news", side_effect=single_source):
            alerts, remembered, errors = w.high_signal_news(set())
        self.assertFalse(alerts)
        self.assertFalse(remembered)
        self.assertFalse(errors)
        with patch.object(w, "google_news", side_effect=two_sources):
            alerts, remembered, errors = w.high_signal_news(remembered)
        self.assertEqual(len(alerts), 1)
        self.assertGreaterEqual(len(remembered), 2)
        self.assertFalse(errors)



    def test_price_rally_with_negative_etf_five_day_is_mixed_not_certain_down(self):
        current = snap(btc=61433, five=-1790)
        current["crypto"]["prices"]["BTC"]["change24"] = 3.03
        current["crypto"]["btc_etf"]["date"] = "2026-11-20"
        now = dt.datetime(2026, 11, 23, 17, 51, tzinfo=w.KST)
        result = w._crypto_direction(current, now)
        self.assertIn("혼조", result["direction"])
        self.assertIn("반등", result["reason"])
        self.assertNotIn("단기 하락 압력 우세", result["direction"])
        self.assertIn("반대", result["counter"])

    def test_official_fx_is_report_date_not_etf_trade_date(self):
        with tempfile.TemporaryDirectory() as directory:
            root = pathlib.Path(directory)
            path = root / "data" / "korea_market_stress_watch_state.json"
            path.parent.mkdir(parents=True)
            row = {"snapshot": {"usdkrw": {"ecos_official": {
                "date": "2026-11-23", "value": 1337.3,
                "stat_code": "731Y001", "item_code": "0000001",
            }}}}
            path.write_text(json.dumps(row), encoding="utf-8")
            with patch.object(w, "ROOT", root):
                fx = w._read_official_fx("2026-11-23")
        self.assertEqual(fx["rate"], 1337.3)
        self.assertEqual(fx["date"], "2026-11-23")
        self.assertEqual(fx["source"], "한국은행 ECOS")

    def test_ecb_official_cross_rate_fallback(self):
        csv_text = (
            "CURRENCY,TIME_PERIOD,OBS_VALUE\n"
            "KRW,2026-11-20,1472.04\n"
            "USD,2026-11-20,1.0990\n"
        )
        with tempfile.TemporaryDirectory() as directory:
            with patch.object(w, "ROOT", pathlib.Path(directory)):
                with patch.object(w, "fetch", return_value=csv_text.encode("utf-8")):
                    fx = w._read_official_fx("2026-11-23")
        self.assertEqual(fx["source"], "유럽중앙은행 ECB")
        self.assertEqual(fx["method"], "KRW/EUR ÷ USD/EUR 교차환산")
        self.assertAlmostEqual(fx["rate"], 1472.04 / 1.0990, places=3)

    def test_every_usd_amount_gets_krw_annotation_without_html_url_edits(self):
        sample = (
            '<b>BTC 61,433달러</b> · 적정가 85,000달러 '
            '· ETF -17억9,000만달러 · 달러 집계 -1,306.2백만달러 '
            '· NVIDIA $115.8B · ETH 1,722달러\n'
            '• 환율 1달러=1,337.30원\n'
            '<a href="https://site.example/path?x=$115.8B">원문</a>'
        )
        result = w._append_krw_to_text(sample, {"rate": 1337.3})
        for value in ("61,433달러", "85,000달러", "-17억9,000만달러",
                      "-1,306.2백만달러", "$115.8B", "1,722달러"):
            self.assertIn(value + "(약 ", result, value)
        self.assertIn("1달러=1,337.30원", result)
        self.assertIn('href="https://site.example/path?x=$115.8B"', result)
        self.assertEqual(result.count("(약 "), 6)
        self.assertAlmostEqual(w._usd_token_value("-17억9,000만달러"), -1790000000)
        self.assertAlmostEqual(w._usd_token_value("8만5,000달러"), 85000)

    def test_alert_currency_direction_and_source_period_labels(self):
        current = snap(btc=61433, five=-1790)
        current["crypto"]["prices"]["BTC"]["change24"] = 3.03
        current["crypto"]["btc_etf"]["date"] = "2026-11-20"
        current["crypto"]["btc_etf"]["daily_usd_m"] = -669.2
        now = dt.datetime(2026, 11, 23, 17, 51, tzinfo=w.KST)
        signal = (
            "암호화폐", "BTC ETF 당일 큰 규모의 순유출",
            "이전 -1,306.2백만달러 → 최근 -1,790.0백만달러; 당일 -669.2백만달러",
            "자금 확인", "다음 ETF 자료 확인", w.FARSIDE_BTC,
        )
        message = w.build_alert(
            [signal], now, current,
            {"rate": 1337.3, "date": "2026-11-23", "source": "한국은행 ECOS"},
        )
        self.assertIn("혼조 — 가격 반등·ETF 자금 순유출", message)
        self.assertIn("반대 근거", message)
        self.assertIn("판단 신뢰수준", message)
        self.assertIn("85,000달러(약 ", message)
        self.assertIn("61,433달러(약 ", message)
        self.assertIn("-1,306.2백만달러(약 ", message)
        self.assertIn("2026-11-23 한국은행 ECOS", message)
        self.assertIn("1달러=1,337.30원", message)

    def test_alert_reads_fx_at_alert_date_not_older_etf_date(self):
        with patch.object(w, "_read_official_fx", return_value={"rate": 1337.3, "date": "2026-10-31", "source": "한국은행 ECOS"}) as fx:
            w.build_alert(
                [("암호화폐", "ETF 순유출", "ETF 자금 감소", "", "", None)],
                NOW, snap(),
            )
        fx.assert_called_once_with("2026-10-31")



if __name__ == "__main__":
    unittest.main()
