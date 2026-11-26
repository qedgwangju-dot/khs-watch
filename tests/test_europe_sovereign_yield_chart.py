import datetime as dt
import json
import pathlib
import tempfile
import unittest
from unittest import mock

from scripts import europe_sovereign_yield_chart as c


class EuropeYieldChartTests(unittest.TestCase):
    def setUp(self):
        self.state = {"last_checked_kst": "2026-11-25T21:40:20+09:00",
                      "history": {"fr_mkt": [{"date": "2026-11-24", "value": 4.78},
                                             {"date": "2026-11-25", "value": 4.72},
                                             {"date": "2026-11-26", "value": 5.00},
                                             {"date": "bad", "value": 9}]},
                      "last_values": {"fr_mkt": 4.72, "de_mkt": 3.22},
                      "last_source_dates": {"fr_mkt": "2026-11-25", "de_mkt": "2026-11-25"},
                      "stale": []}

    def test_history_filters_future_and_invalid(self):
        self.assertEqual(c.market_rows(self.state, "fr_mkt"),
                         [(dt.date(2026,11,24),4.78),(dt.date(2026,11,25),4.72)])

    def test_spread_uses_only_matching_dates(self):
        left = c.market_rows(self.state, "fr_mkt")
        self.assertEqual(c.same_date_spread(left, [(dt.date(2026,11,25),3.22)]),
                         [(dt.date(2026,11,25),150.0)])

    def test_current_spread_requires_fresh_comparable_data(self):
        self.assertEqual(c.live_spread(self.state,"fr_mkt","de_mkt"),150.0)
        self.state["stale"] = ["de_mkt"]
        self.assertIsNone(c.live_spread(self.state,"fr_mkt","de_mkt"))
        self.state["stale"] = []
        self.state["last_source_dates"]["de_mkt"] = "2026-11-24"
        self.assertIsNone(c.live_spread(self.state,"fr_mkt","de_mkt"))

    def test_photo_requires_verified_text_ack(self):
        with tempfile.TemporaryDirectory() as d:
            path = pathlib.Path(d)/"ack.json"
            self.assertIsNone(c.text_receipt(path,"test_bot"))
            ack = {"status":"confirmed","lane":"europe_sovereign_yields",
                   "chat_id_verified":True,"bot_username":"test_bot","message_ids":[41,42]}
            path.write_text(json.dumps(ack))
            self.assertEqual(c.text_receipt(path,"test_bot"),42)
            for key,value in (("chat_id_verified",False),("bot_username","wrong"),("message_ids",[0])):
                path.write_text(json.dumps({**ack,key:value}))
                with self.assertRaises(ValueError):
                    c.text_receipt(path,"test_bot")

    def test_multipart_png_and_reply_fields(self):
        payload, kind = c.multipart({"chat_id":"123","reply_parameters":"{}"}, b"fakepng")
        self.assertIn("multipart/form-data",kind)
        self.assertIn(b'name="photo"',payload)
        self.assertIn(b"fakepng",payload)


    def test_korean_font_install_only_when_unavailable(self):
        with mock.patch.object(c, "choose_font", return_value="NanumGothic"), \
             mock.patch.object(c.subprocess, "run") as run:
            self.assertEqual(c.ensure_korean_font(), "NanumGothic")
            run.assert_not_called()
        with mock.patch.object(c, "choose_font",
                               side_effect=[c.KoreanFontUnavailable(), "NanumGothic"]), \
             mock.patch.object(c.subprocess, "run") as run:
            self.assertEqual(c.ensure_korean_font(), "NanumGothic")
            self.assertEqual(run.call_count, 2)
            self.assertIn("fonts-nanum", run.call_args_list[-1].args[0])

    def test_missing_korean_font_never_falls_back_to_english(self):
        with mock.patch.object(c, "choose_font", side_effect=c.KoreanFontUnavailable()), \
             mock.patch.object(c.subprocess, "run"):
            with self.assertRaises(c.KoreanFontUnavailable):
                c.ensure_korean_font()

    def test_failed_font_install_is_photo_only_failure(self):
        with mock.patch.object(c, "choose_font", side_effect=c.KoreanFontUnavailable()), \
             mock.patch.object(c.subprocess, "run", side_effect=c.subprocess.CalledProcessError(1, "apt-get")):
            with self.assertRaises(c.KoreanFontUnavailable):
                c.ensure_korean_font()

    def test_non_korean_chart_is_not_sent(self):
        with tempfile.TemporaryDirectory() as d:
            p = pathlib.Path(d)
            pending, ack, receipt = p/"pending.json", p/"ack.json", p/"photo.json"
            pending.write_text(json.dumps(self.state))
            ack.write_text("{}")
            with mock.patch.object(c, "OUT", p), \
                 mock.patch.object(c, "PNG", p/"chart.png"), \
                 mock.patch.object(c, "RECEIPT", receipt), \
                 mock.patch.object(c.base, "PENDING", pending), \
                 mock.patch.object(c.base, "CONFIRMED", ack), \
                 mock.patch.object(c, "text_receipt", return_value=42), \
                 mock.patch.object(c, "render", return_value={"font_language": "en"}), \
                 mock.patch.dict(c.sys.modules, {"matplotlib": mock.Mock()}), \
                 mock.patch.object(c, "send_photo") as send:
                self.assertEqual(c.main(), 1)
                send.assert_not_called()
                self.assertEqual(c.load(receipt)["status"], "not_sent")
                self.assertEqual(c.load(pending)["last_photo_delivery"]["status"], "not_sent")
                self.assertTrue(ack.is_file())


    def test_daily_window_expanded(self):
        self.state["history"]["fr_mkt"].extend([
            {"date": "2026-07-01", "value": 4.0},
            {"date": "2026-01-01", "value": 3.0}])
        rows = c.market_rows(self.state, "fr_mkt")
        self.assertEqual(rows[0], (dt.date(2026,7,1),4.0))
        self.assertEqual(c.DAILY_CHART_DAYS, 183)

    def test_monthly_csv_distinct_completed_months_and_missing(self):
        raw = "observation_date,IRLTLT01FRM156N,IRLTLT01DEM156N\n2024-10-01,3.0,2.0\n2024-11-01,3.1,2.1\n2026-10-01,4.89,3.41591\n2026-11-01,9,8\n"
        data = c.parse_monthly_csv(raw, dt.date(2026,11,26))
        self.assertEqual(len(data["fr_mkt"]), 2)
        self.assertEqual(data["fr_mkt"][-1], (dt.date(2026,10,1),4.89))
        self.assertEqual(data["it10"], [])
        self.assertEqual(c.same_date_spread(data["fr_mkt"], data["de_mkt"])[-1][1], 147.409)

    def test_monthly_table_checks_source_and_series(self):
        raw = "<p>IRLTLT01FRM156N OECD Frequency Monthly</p><table><tr><td>2026-10-01</td><td>4.89</td></tr></table>"
        rows = c.parse_monthly_table(raw, "IRLTLT01FRM156N", dt.date(2026,11,26))
        self.assertEqual(rows, [(dt.date(2026,10,1),4.89)])
        with self.assertRaises(ValueError):
            c.parse_monthly_table(raw, "IRLTLT01DEM156N", dt.date(2026,11,26))

    def test_monthly_failure_does_not_fabricate_daily_data(self):
        def broken(url):
            raise OSError("test source unavailable")
        data = c.fetch_monthly_context(self.state, fetch=broken)
        self.assertEqual(data, {k: [] for k in c.MARKETS})
        self.assertEqual(c.monthly_summary(data)["fr_mkt"]["months"], 0)



if __name__ == "__main__":
    unittest.main()
