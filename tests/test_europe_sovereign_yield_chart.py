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


if __name__ == "__main__":
    unittest.main()
