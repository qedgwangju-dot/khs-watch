"""Weekly equity/Treasury Telegram alert: safety and idempotency regressions."""
import datetime as dt
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from zoneinfo import ZoneInfo
import treasury_weekly_haven_alert as alert
import treasury_weekly_stock_bond_signal as source

NOW=dt.datetime(2026,10,17,14,0,tzinfo=ZoneInfo("Asia/Seoul"))

def snap():
    x=source.evaluate_week({"2026-10-09":30883.15,"2026-10-16":29187.55},
                           {"2026-10-09":5.24,"2026-10-16":5.09},dt.date(2026,10,16))
    x["source_urls"]=["https://indexes.nasdaq.com/Index/History/NDX",
                      "https://home.treasury.gov/resource-center/data-chart-center/interest-rates/"]
    return x

class WeekAlertTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        root=Path(self.tmp.name)
        self.state=root/"state.json"
        self.o=patch.object(alert,"OUT_PATH",root/"out.txt")
        self.h=patch.object(alert,"HTML_PATH",root/"telegram.html.txt")
        self.r=patch.object(alert,"RECEIPT_PATH",root/"receipt.json")
        self.o.start();self.h.start();self.r.start()
        self.addCleanup(self.o.stop);self.addCleanup(self.h.stop);self.addCleanup(self.r.stop)

    def test_validation_never_sends_or_advances_state(self):
        with patch.object(source,"fetch_current_week",return_value=snap()),patch.object(alert,"send_telegram") as send:
            x=alert.run(validate_only=True,now=NOW,path=self.state)
        self.assertEqual(x["status"],"validated")
        self.assertFalse(x["telegram_sent"])
        send.assert_not_called()
        self.assertFalse(self.state.exists())

    def test_success_requires_telegram_confirmation_before_state(self):
        with patch.object(source,"fetch_current_week",return_value=snap()),patch.object(alert,"send_telegram",return_value=(alert.EXPECTED_BOT,701)):
            x=alert.run(validate_only=False,now=NOW,path=self.state)
        self.assertEqual(x["status"],"telegram_confirmed")
        self.assertEqual(alert.load_state(self.state)["last_alert"]["message_id"],701)
        self.assertTrue(alert.RECEIPT_PATH.exists())

    def test_duplicate_skips_api_and_telegram(self):
        alert.write_state({"last_alert":{"end":"2026-10-16","message_id":701,"bot_username":alert.EXPECTED_BOT}},self.state)
        with patch.object(source,"fetch_current_week") as fetch,patch.object(alert,"send_telegram") as send:
            x=alert.run(validate_only=False,now=NOW,path=self.state)
        self.assertEqual(x["status"],"duplicate_suppressed")
        fetch.assert_not_called();send.assert_not_called()

    def test_source_failure_does_not_send_or_save(self):
        with patch.object(source,"fetch_current_week",side_effect=source.SourceMissing("missing official Friday value")),patch.object(alert,"send_telegram") as send:
            x=alert.run(validate_only=False,now=NOW,path=self.state)
        self.assertEqual(x["status"],"source_unavailable")
        send.assert_not_called()
        self.assertFalse(self.state.exists())

    def test_no_threshold_no_message(self):
        data=snap();data.update(alert=False,category="주간 급락 조건 미충족")
        with patch.object(source,"fetch_current_week",return_value=data),patch.object(alert,"send_telegram") as send:
            x=alert.run(validate_only=False,now=NOW,path=self.state)
        self.assertEqual(x["status"],"threshold_not_met")
        send.assert_not_called()
        self.assertFalse(self.state.exists())

    def test_send_failure_preserves_state(self):
        with patch.object(source,"fetch_current_week",return_value=snap()),patch.object(alert,"send_telegram",side_effect=RuntimeError("API refused")):
            with self.assertRaisesRegex(RuntimeError,"API refused"):
                alert.run(validate_only=False,now=NOW,path=self.state)
        self.assertFalse(self.state.exists())

    def test_invalid_existing_state_rejected(self):
        self.state.write_text('{"invalid":true}',encoding="utf-8")
        with self.assertRaisesRegex(RuntimeError,"refusing to reset"):
            alert.load_state(self.state)

    def test_short_message(self):
        self.assertLess(len(source.report_text(snap())),4000)

if __name__=="__main__":
    unittest.main()
