"""Public GVIP/SPY 75-session relative-performance alarm regression tests."""
import datetime as dt
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch
from zoneinfo import ZoneInfo

import us_vip_relative_watch as w


def market_rows():
    dates = []
    current = dt.date(2026, 7, 8)
    while len(dates) < 76:
        if current.weekday() < 5:
            dates.append(current.isoformat())
        current += dt.timedelta(days=1)
    # All ETF quotes use identical closing dates with positive volume.
    gvip, spy = {}, {}
    for i, key in enumerate(dates):
        gvip[key] = {"close": 200 - i * 0.32, "volume": 9000}
        spy[key] = {"close": 100 + i * 0.035, "volume": 50000000}
    return gvip, spy, dates[-1]


def fixture():
    g, s, last = market_rows()
    return w.evaluate(g, s, last)


class NasdaqResponse:
    def __init__(self, ticker, data):
        self.data = data
        self.ticker = ticker

    def raise_for_status(self):
        pass

    def json(self):
        rows = []
        for day, o in self.data.items():
            rows.append({
                "date": dt.date.fromisoformat(day).strftime("%m/%d/%Y"),
                "close": f"{o['close']:,.4f}",
                "volume": f"{o['volume']:,}",
            })
        return {
            "status": {"rCode": 200},
            "data": {"symbol": self.ticker, "tradesTable": {"rows": rows}},
        }


class Source:
    def __init__(self, g, s):
        self.g = g
        self.s = s

    def get(self, url, **kwargs):
        return NasdaqResponse("GVIP", self.g) if "/GVIP/" in url else NasdaqResponse("SPY", self.s)


class VipRelativeRegression(unittest.TestCase):
    def setUp(self):
        t = tempfile.TemporaryDirectory()
        self.addCleanup(t.cleanup)
        root = Path(t.name)
        self.state = root/"state.json"
        self.patch_out = patch.object(w, "OUT", root)
        self.patch_body = patch.object(w, "CANDIDATE", root/"candidate.html")
        self.patch_receipt = patch.object(w, "RECEIPT", root/"receipt.json")
        for p in (self.patch_out, self.patch_body, self.patch_receipt):
            p.start()
            self.addCleanup(p.stop)

    def test_official_api_requires_exact_ticker_and_rows(self):
        j=NasdaqResponse("GVIP", market_rows()[0]).json()
        self.assertEqual(len(w.parse_nasdaq("GVIP", j)), 76)
        j["data"]["symbol"]="SPY"
        with self.assertRaises(w.SourceError):
            w.parse_nasdaq("GVIP", j)
        j["status"]["rCode"]=400
        with self.assertRaises(w.SourceError):
            w.parse_nasdaq("GVIP", j)

    def test_nasdaq_non_numeric_volume_is_not_a_price_error(self):
        payload = NasdaqResponse("GVIP", market_rows()[0]).json()
        rows = payload["data"]["tradesTable"]["rows"]
        rows[3]["volume"] = "N/A"
        parsed = w.parse_nasdaq("GVIP", payload)
        date_key = dt.datetime.strptime(rows[3]["date"], "%m/%d/%Y").date().isoformat()
        self.assertEqual(parsed[date_key]["volume"], 0)
        self.assertGreater(parsed[date_key]["close"], 0)

    def test_returns_are_arithmetic_percent_points_not_basket_snapshot(self):
        out=fixture()
        self.assertEqual(out["sessions"],75)
        self.assertAlmostEqual(out["gvip_return"] - out["spy_return"], out["relative_pp"],places=3)
        self.assertLess(out["relative_pp"],-10.0)
        self.assertTrue(out["band"].endswith("-15%p 이하") or out["band"].endswith("-10%p 이하"))
        body=w.render(out,"인기 보유종목 ETF 상대 약세 확인")
        self.assertIn("75거래일",body)
        self.assertIn("Nasdaq 종가",body)
        self.assertIn("GSTHHVIP",body)
        self.assertNotIn("프라임북 포지션 변화 확정",body)
        self.assertIn("href=",body)
        self.assertLess(len(body),3900)

    def test_missing_exact_session_must_withhold(self):
        g,s,last=market_rows()
        deleted = sorted(s)[-4]
        del s[deleted]
        oldest = dt.date.fromisoformat(min(s))
        s[(oldest - dt.timedelta(days=1)).isoformat()] = {"close": 100, "volume": 50000000}
        with self.assertRaisesRegex(w.SourceError,"missing or unmatched"):
            w.evaluate(g,s,last)

    def test_not_enough_history_must_withhold(self):
        g,s,last=market_rows()
        g={k:v for k,v in list(g.items())[2:]}
        with self.assertRaisesRegex(w.SourceError,"76 full"):
            w.evaluate(g,s,last)

    def test_unconfirmed_volume_and_split_must_withhold(self):
        g,s,last=market_rows()
        g[last]["volume"]=0
        with self.assertRaisesRegex(w.SourceError,"volume"):
            w.evaluate(g,s,last)
        g[last]["volume"]=9000
        g[last]["close"]*=2
        with self.assertRaisesRegex(w.SourceError,"split"):
            w.evaluate(g,s,last)

    def test_correct_last_us_session_and_strict_stale_data(self):
        ts=dt.datetime(2026,10,23,13,52,tzinfo=ZoneInfo("Asia/Seoul"))
        self.assertEqual(w.last_completed_us_weekday(ts).isoformat(),"2026-10-22")
        g,s,last=market_rows()
        client=Source(g,s)
        with self.assertRaisesRegex(w.SourceError,"latest completed"):
            w.collect(ts,client=client)

    def test_validation_has_no_telegram_or_state(self):
        with patch.object(w,"send_telegram") as send:
            x=w.run(validate_only=True,state_path=self.state,source=lambda now:fixture())
        self.assertEqual(x["status"],"validated")
        send.assert_not_called()
        self.assertFalse(self.state.exists())

    def test_first_and_duplicate_real_delivery_logic(self):
        x=fixture()
        self.assertIsNotNone(w.decide(x,{"last_alert":None}))
        with patch.object(w,"send_telegram",return_value=1108) as send:
            first=w.run(state_path=self.state,source=lambda now:x)
            second=w.run(state_path=self.state,source=lambda now:x)
        self.assertEqual(first["status"],"sent")
        self.assertEqual(first["message_id"],1108)
        self.assertEqual(second["status"],"baseline_or_no_change")
        self.assertEqual(w.load_state(self.state)["last_alert"]["message_id"],1108)
        send.assert_called_once()

    def test_worsening_bands_and_recovery(self):
        x=fixture()
        old={"last_alert":{"band":"상대성과 -10%p 이하","end":"2026-09-30","message_id":11}}
        y={**x,"relative_pp":-16,"band":"상대성과 -15%p 이하"}
        self.assertEqual(w.decide(y,old),"인기 보유종목 ETF 상대 약세 확대")
        old["last_alert"]["band"]="상대성과 -15%p 이하"
        self.assertIsNone(w.decide(x,old))
        recovered={**x,"relative_pp":-4,"band":"상대성과 -5%p 초과"}
        self.assertEqual(w.decide(recovered,old),"인기 보유종목 ETF 상대 약세 완화")

    def test_send_failure_does_not_advance_baseline(self):
        with patch.object(w,"send_telegram",side_effect=RuntimeError("Telegram rejected")):
            with self.assertRaisesRegex(RuntimeError,"Telegram rejected"):
                w.run(state_path=self.state,source=lambda now:fixture())
        self.assertFalse(self.state.exists())

    def test_source_failure_never_sends(self):
        with patch.object(w,"send_telegram") as send:
            x=w.run(state_path=self.state,source=lambda now:(_ for _ in ()).throw(w.SourceError("official provider gap")))
        self.assertEqual(x["status"],"source_withheld")
        send.assert_not_called()
        self.assertFalse(self.state.exists())

    def test_invalid_saved_state_not_reset(self):
        self.state.write_text('{"state":"corrupt"}',encoding="utf-8")
        with self.assertRaisesRegex(RuntimeError,"refusing to erase"):
            w.load_state(self.state)


    def test_one_official_session_lag_is_pending_not_source_failure(self):
        now=dt.datetime(2026,10,27,23,0,tzinfo=dt.timezone.utc)
        g,s,_=market_rows()
        g["2026-10-26"]={"close":177.2,"volume":9000}
        s["2026-10-26"]={"close":110.0,"volume":50000000}
        with self.assertRaisesRegex(w.OfficialPublicationPending,"2026-10-27"):
            w.collect(now,client=Source(g,s))

    def test_asynchronous_close_publication_is_pending_not_false_relative_signal(self):
        now=dt.datetime(2026,10,27,23,0,tzinfo=dt.timezone.utc)
        g,s,_=market_rows()
        g["2026-10-27"]={"close":176.5,"volume":9000}
        s["2026-10-26"]={"close":110.0,"volume":50000000}
        with self.assertRaises(w.OfficialPublicationPending):
            w.collect(now,client=Source(g,s))

    def test_older_than_one_completed_business_session_is_actual_source_failure(self):
        self.assertFalse(w.recent_publication_gap("2026-10-27","2026-10-23","2026-10-26"))
        self.assertFalse(w.recent_publication_gap("2026-10-27","2026-10-27","2026-10-27"))

    def test_pending_never_sends_or_changes_state(self):
        def stale(_):
            raise w.OfficialPublicationPending("Nasdaq GVIP/SPY pending completed close")
        with patch.object(w,"send_telegram") as send:
            result=w.run(state_path=self.state,source=stale)
        self.assertEqual(result["status"],"publication_pending")
        self.assertFalse(result["telegram_sent"])
        self.assertFalse(self.state.exists())
        send.assert_not_called()



if __name__ == "__main__":
    unittest.main()
