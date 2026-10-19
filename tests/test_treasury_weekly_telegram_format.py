"""Clickable Telegram HTML, visibility, no-duplicate edit and API acknowledgement tests."""
import datetime as dt
import html
import json
import tempfile
import unittest
import urllib.parse
from html.parser import HTMLParser
from pathlib import Path
from unittest.mock import patch
from zoneinfo import ZoneInfo

import treasury_weekly_haven_alert as alert
import treasury_weekly_stock_bond_signal as source


NOW=dt.datetime(2026,10,19,15,50,tzinfo=ZoneInfo("Asia/Seoul"))


def example():
    row=source.evaluate_week(
        {"2026-10-09":30883.15,"2026-10-16":29187.55},
        {"2026-10-09":5.24,"2026-10-16":5.09},
        dt.date(2026,10,16),
    )
    row["source_urls"]=[
        "https://indexes.nasdaq.com/Index/History/NDX",
        "https://api.nasdaq.com/api/quote/NDX/historical?assetclass=index",
        "https://home.treasury.gov/resource-center/data-chart-center/interest-rates/pages/xml?data=daily_treasury_yield_curve&field_tdr_date_value=2026",
    ]
    return row


class TextParser(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.parts=[]

    def handle_data(self, data):
        self.parts.append(data)

    def visible(self):
        return "".join(self.parts)


class FakeResponse:
    def __init__(self, data):
        self.raw=json.dumps(data).encode("utf-8")

    def read(self):
        return self.raw

    def __enter__(self):
        return self

    def __exit__(self, typ, value, tb):
        return False


class FakeTelegram:
    def __init__(self, *, returned_id=456, missing_links=False):
        self.requests=[]
        self.returned_id=returned_id
        self.missing_links=missing_links

    def urlopen(self, request, timeout=20):
        if isinstance(request,str):
            assert request.endswith("/getMe")
            return FakeResponse({"ok":True,"result":{"username":alert.EXPECTED_BOT}})
        values=urllib.parse.parse_qs(request.data.decode("utf-8"))
        self.requests.append((request.full_url,values))
        message_html=values["text"][0]
        parser=TextParser();parser.feed(message_html)
        links=alert._LinkParser();links.feed(message_html)
        listed=links.source_links[:-1] if self.missing_links else links.source_links
        mid=int(values.get("message_id",[self.returned_id])[0])
        return FakeResponse({
            "ok":True,
            "result":{
                "message_id":mid,
                "text":parser.visible(),
                "entities":[{"type":"text_link","url":url} for url in listed],
            },
        })


class FormattingTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        root=Path(self.tmp.name)
        self.state=root/"weekly_state.json"
        self.patches=[
            patch.object(alert,"OUT_PATH",root/"alert.txt"),
            patch.object(alert,"HTML_PATH",root/"alert.html.txt"),
            patch.object(alert,"RECEIPT_PATH",root/"receipt.json"),
        ]
        for item in self.patches:
            item.start()
            self.addCleanup(item.stop)

    def test_visible_content_is_complete_and_three_links_are_clickable(self):
        x=example()
        payload=source.report_html(x)
        parser=TextParser();parser.feed(payload)
        visible=parser.visible()
        linked=alert._LinkParser();linked.feed(payload)
        self.assertEqual(len(linked.source_links),3)
        self.assertNotIn("https://",visible)
        self.assertLess(len(visible),1100)
        self.assertNotIn("**",payload)
        self.assertIn("나스닥100: 30,883.15 → 29,187.55 (-5.49%)",visible)
        self.assertIn("미 10년물 금리: 5.24% → 5.09% (-15bp)",visible)
        for key in ("안전자산 방어 신호","CTA","CFTC","CME","공식 출처","주간 마감",
                    "미 재무부 10년물 금리","나스닥 공식 종가","경보 조건","이후 국채 수익"):
            self.assertIn(key,visible)

    def test_telegram_html_escapes_untrusted_comment_and_query_ampersands(self):
        x=example()
        x["comment"]="국채 <b>방어</b> & 기술주 위험"
        payload=source.report_html(x)
        self.assertIn("국채 &lt;b&gt;방어&lt;/b&gt; &amp; 기술주 위험",payload)
        self.assertIn("assetclass=index",payload)
        self.assertIn("&amp;field_tdr_date_value=",payload)
        self.assertNotIn("국채 <b>방어</b>",payload)

    def test_invalid_or_missing_source_links_block_delivery_before_bot(self):
        x=example()
        x["source_urls"][0]="javascript:alert(1)"
        with self.assertRaises(source.SourceMissing):
            source.report_html(x)
        x=example()
        x["source_urls"]=x["source_urls"][:-1]
        with self.assertRaises(source.SourceMissing):
            source.report_html(x)

    def test_html_uses_distinct_threshold_explanation_for_other_regimes(self):
        x=example()
        x.update(category="주식·국채 동반 약세 경보",comment="동반 하락")
        self.assertIn("금리 +10bp 이상",source.report_html(x))
        x.update(category="기술주 급락·국채 완충 불충분",comment="방어 약함")
        self.assertIn("하락은 미충족",source.report_html(x))

    def test_send_message_uses_html_parse_mode_links_and_disables_preview(self):
        fake=FakeTelegram(returned_id=502)
        with patch.dict("os.environ",{
            "TELEGRAM_BOT_TOKEN":"dummy",
            "TELEGRAM_CHAT_ID":"123",
            "EXPECTED_TELEGRAM_BOT_USERNAME":alert.EXPECTED_BOT,
        }),patch.object(alert.urllib.request,"urlopen",side_effect=fake.urlopen):
            username, mid=alert.send_telegram(source.report_html(example()))
        self.assertEqual((username,mid),(alert.EXPECTED_BOT,502))
        self.assertEqual(len(fake.requests),1)
        uri,body=fake.requests[0]
        self.assertTrue(uri.endswith("/sendMessage"))
        self.assertEqual(body["parse_mode"],["HTML"])
        self.assertEqual(body["disable_web_page_preview"],["true"])
        self.assertIn("<a href=",body["text"][0])

    def test_telegram_missing_clickable_entity_is_not_marked_verified(self):
        fake=FakeTelegram(missing_links=True)
        with patch.dict("os.environ",{
            "TELEGRAM_BOT_TOKEN":"dummy","TELEGRAM_CHAT_ID":"123",
        }),patch.object(alert.urllib.request,"urlopen",side_effect=fake.urlopen):
            with self.assertRaisesRegex(RuntimeError,"clickable source links"):
                alert.send_telegram(source.report_html(example()))

    def test_existing_message_is_edited_without_new_message_or_new_id(self):
        alert.write_state({"last_alert":{
            "end":"2026-10-16","category":"안전자산 방어 신호",
            "ndx_week_pct":-5.4904,"y10_week_bp":-15.0,
            "bot_username":alert.EXPECTED_BOT,"message_id":456,
            "confirmed_at_kst":"2026-10-19T14:21:53+09:00",
        }},self.state)
        with patch.object(source,"fetch_current_week",return_value=example()), \
             patch.object(alert,"send_telegram") as sender, \
             patch.object(alert,"edit_telegram",return_value=(alert.EXPECTED_BOT,456)) as editor:
            outcome=alert.run(now=NOW,path=self.state,repair_format=True)
        sender.assert_not_called()
        editor.assert_called_once()
        self.assertEqual(editor.call_args.args[1],456)
        self.assertEqual(outcome["status"],"telegram_edited")
        self.assertFalse(outcome["telegram_sent"])
        final=alert.load_state(self.state)["last_alert"]
        self.assertEqual(final["message_id"],456)
        self.assertEqual(final["format_revision"],alert.FORMAT_REVISION)
        self.assertEqual(final["clickable_source_links"],3)
        self.assertTrue(alert.HTML_PATH.exists())

    def test_edit_telegram_calls_edit_message_not_send_message(self):
        fake=FakeTelegram(returned_id=456)
        with patch.dict("os.environ",{
            "TELEGRAM_BOT_TOKEN":"dummy","TELEGRAM_CHAT_ID":"123",
        }),patch.object(alert.urllib.request,"urlopen",side_effect=fake.urlopen):
            user,mid=alert.edit_telegram(source.report_html(example()),456)
        self.assertEqual(mid,456)
        uri,body=fake.requests[0]
        self.assertTrue(uri.endswith("/editMessageText"))
        self.assertEqual(body["message_id"],["456"])
        self.assertEqual(body["parse_mode"],["HTML"])

    def test_edit_does_not_advance_state_after_telegram_failure(self):
        base={"last_alert":{
            "end":"2026-10-16","category":"안전자산 방어 신호",
            "ndx_week_pct":-5.4904,"y10_week_bp":-15.0,
            "bot_username":alert.EXPECTED_BOT,"message_id":456,
        }}
        alert.write_state(base,self.state)
        with patch.object(source,"fetch_current_week",return_value=example()), \
             patch.object(alert,"edit_telegram",side_effect=RuntimeError("edit denied")):
            with self.assertRaisesRegex(RuntimeError,"edit denied"):
                alert.run(now=NOW,path=self.state,repair_format=True)
        self.assertEqual(alert.load_state(self.state),base)

    def test_reformatting_a_confirmed_message_is_idempotent(self):
        alert.write_state({"last_alert":{
            "end":"2026-10-16","bot_username":alert.EXPECTED_BOT,
            "message_id":456,"format_revision":alert.FORMAT_REVISION,
        }},self.state)
        with patch.object(source,"fetch_current_week") as fetch, \
             patch.object(alert,"edit_telegram") as edit:
            result=alert.run(now=NOW,path=self.state,repair_format=True)
        self.assertEqual(result["status"],"format_already_current")
        fetch.assert_not_called()
        edit.assert_not_called()

    def test_mismatched_live_prices_prohibit_existing_message_edit(self):
        alert.write_state({"last_alert":{
            "end":"2026-10-16","category":"안전자산 방어 신호",
            "ndx_week_pct":-5.4904,"y10_week_bp":-15.0,
            "bot_username":alert.EXPECTED_BOT,"message_id":456,
        }},self.state)
        altered=example();altered["y10_week_bp"]=-25.0
        with patch.object(source,"fetch_current_week",return_value=altered), \
             patch.object(alert,"edit_telegram") as edit:
            with self.assertRaisesRegex(RuntimeError,"diverge"):
                alert.run(now=NOW,path=self.state,repair_format=True)
        edit.assert_not_called()


if __name__=="__main__":
    unittest.main()
