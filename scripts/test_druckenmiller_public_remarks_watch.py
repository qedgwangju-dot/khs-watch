#!/usr/bin/env python3
"""No-network tests: source identity, timeline, news gate, format and dedup."""
from datetime import datetime,timezone,timedelta
from html import escape as xml_escape, unescape as html_unescape
from urllib.parse import parse_qs
from unittest.mock import patch, MagicMock
import io
import json
import re
import os
import unittest
import druckenmiller_public_remarks_watch as watcher

NOW=datetime(2026,11,18,5,0,tzinfo=timezone.utc)


def item(title,desc,publisher,date="Tue, 17 Nov 2026 19:20:00 GMT",link="https://example.com/article"):
    return f"""<item><title>{xml_escape(title)}</title><description>{xml_escape(desc)}</description>
    <link>{xml_escape(link)}</link><pubDate>{date}</pubDate><source>{xml_escape(publisher)}</source></item>"""


def rss(*items):
    return ('<?xml version="1.0"?><rss><channel>'+"".join(items)+'</channel></rss>').encode()


class WatchTests(unittest.TestCase):
    def test_speech_classification(self):
        self.assertIn("copper_short",watcher.signals_from_text(
            "Stan Druckenmiller says he is now short copper"))
        self.assertNotIn("copper_short",watcher.signals_from_text(
            "Druckenmiller says he is not short copper"))
        self.assertIn("equity_defensive",watcher.signals_from_text(
            "Druckenmiller holds little net exposure to equities"))
        self.assertIn("growth_2027",watcher.signals_from_text(
            "Druckenmiller fears second half of 2027 could be economically disappointing"))
        self.assertIn("ai_applications",watcher.signals_from_text(
            "Druckenmiller: AI use cases as opposed to infrastructure"))
        self.assertIn("equity_risk_on",watcher.signals_from_text(
            "Druckenmiller increasing equity exposure"))
    def test_source_parsing_and_staleness(self):
        content=rss(item("Druckenmiller short copper","Druckenmiller now short copper","CoinDesk",
                         link="https://www.coindesk.com/a"),
                    item("Druckenmiller short copper","Druckenmiller short copper","BARRON'S",
                         link="https://www.barrons.com/b"),
                    item("Druckenmiller short copper","Druckenmiller short copper","Old News",
                         date="Tue, 17 Nov 2020 19:20:00 GMT"))
        result=watcher.parse_rss(content,"bing",NOW)
        self.assertEqual(len(result),2)
        self.assertEqual({a["publisher"] for a in result},{"coindesk","barrons"})
        self.assertIn("copper_short",watcher.corroborated(result,NOW))
    def test_news_reprint_not_independent(self):
        news=[
            {"publisher":"coindesk","signals":["copper_short"],
             "published":NOW.isoformat(),"url":"https://www.coindesk.com/a"},
            {"publisher":"coindesk","signals":["copper_short"],
             "published":NOW.isoformat(),"url":"https://somewhere.com/reprint"},
        ]
        self.assertEqual(watcher.corroborated(news,NOW),{})
        news.append({"publisher":"barrons","signals":["copper_short"],
                     "published":NOW.isoformat(),"url":"https://www.barrons.com/a"})
        self.assertIn("copper_short",watcher.corroborated(news,NOW))
    def test_unsupported_publisher_or_nonperson(self):
        result=watcher.parse_rss(rss(
            item("Copper short","Short copper market today","CoinDesk"),
            item("Druckenmiller short copper","Stanley short copper","Some aggregator")),
            "google",NOW)
        self.assertEqual(result,[])
    def test_google_index_and_bing_original_url(self):
        wrapped=("https://www.bing.com/news/apiclick.aspx?ref=test&url="+
                 "https%3A%2F%2Fwww.barrons.com%2Flivecoverage%2Ftest")
        self.assertEqual(watcher.original_link(wrapped),
                         "https://www.barrons.com/livecoverage/test")
        content=rss(item("Druckenmiller short copper",
                         "Stan Druckenmiller is short copper","Barron's",
                         link=wrapped))
        self.assertEqual(watcher.parse_rss(content,"bing",NOW)[0]["publisher"],"barrons")
    def test_conflict_fails_closed(self):
        texts=[
            {"publisher":"coindesk","signals":["copper_short","copper_long"],
             "published":NOW.isoformat(),"url":"https://www.coindesk.com/a"},
            {"publisher":"barrons","signals":["copper_short","copper_long"],
             "published":NOW.isoformat(),"url":"https://www.barrons.com/b"},
        ]
        self.assertNotIn("copper_short",watcher.corroborated(texts,NOW))
        self.assertNotIn("copper_long",watcher.corroborated(texts,NOW))
    def test_state_and_no_realert(self):
        state=watcher.empty_state()
        self.assertTrue(watcher.seed_ready(state,NOW))
        state["sent_events"][watcher.SEED_KEY]={"receipt":{"message_id":1}}
        self.assertFalse(watcher.seed_ready(state,NOW))
        state["signal_values"]["copper"]={
            "value":"copper_short","event_date":"2026-11-17T00:00:00+00:00"}
        sources=[
            {"publisher":"coindesk","signals":["copper_short"],
             "published":NOW.isoformat(),"url":"https://www.coindesk.com/a"},
            {"publisher":"barrons","signals":["copper_short"],
             "published":NOW.isoformat(),"url":"https://www.barrons.com/b"},
        ]
        self.assertEqual(watcher.news_candidates(state,sources,NOW),[])
        # A stance REVERSAL on copper must alert even within 90 days.
        reversal=[dict(x,signals=["copper_long"]) for x in sources]
        changed=watcher.news_candidates(state,reversal,NOW)
        self.assertEqual(changed[0][0],"copper_long")
        state["pending"]={"key":"unconfirmed","reserved_at":NOW.isoformat()}
        with patch.object(watcher,"STATE_PATH") as dummy:
            dummy.exists.return_value=True
            dummy.read_text.return_value=json.dumps(state)
            with self.assertRaisesRegex(RuntimeError,"DELIVERY_UNCERTAIN"):
                watcher.load_state()
    def test_seed_grounding_and_length(self):
        message=watcher.seed_message()
        for needle in ("2027년 하반기","구리","자본 보존","10월 28일",
                       "3.75~4.00%","CoinDesk","Barron's",
                       "13F 보유 신고","전체 영상은 별도 미열람"):
            self.assertIn(needle,message)
        self.assertLess(len(message),3800)
        self.assertEqual(len(watcher.SEED_PUBLISHERS),2)
    def test_dynamic_message(self):
        proof=[
            {"publisher":"coindesk","signals":["copper_short"],
             "published":NOW.isoformat(),"url":"https://www.coindesk.com/a"},
            {"publisher":"barrons","signals":["copper_short"],
             "published":NOW.isoformat(),"url":"https://www.barrons.com/b"},
        ]
        msg=watcher.news_message([("copper_short",proof)])
        self.assertIn("독립 출처",msg)
        self.assertIn("매도 포지션",msg)
        self.assertIn("원문 발언 전문",msg)
        self.assertLess(len(msg),3600)
    def test_source_outage_fails_and_never_sends(self):
        state=watcher.empty_state()
        state["sent_events"][watcher.SEED_KEY]={"receipt":{"message_id":3}}
        with patch.object(watcher,"load_state",return_value=state),\
             patch.object(watcher,"discover",return_value=([],{"google":{"ok":True},"bing":{"ok":False},"coindesk":{"ok":False}})),\
             patch.object(watcher,"telegram_send") as sender,\
             patch.object(watcher,"save_state") as saver:
            with self.assertRaisesRegex(RuntimeError,"fewer than 2/3"):
                watcher.main()
            sender.assert_not_called()
            saver.assert_not_called()

    def test_clickable_seed_sources_and_html_escaping(self):
        msg=watcher.seed_message()
        self.assertIn("<b>한눈에 보기</b>",msg)
        self.assertIn("<b>쉽게 해석하면</b>",msg)
        links=re.findall(r'<a href="([^"]+)">([^<]+)</a>',msg)
        self.assertEqual(len(links),4)
        self.assertIn("CoinDesk 보도",msg)
        self.assertIn("FOMC 공식 성명",msg)
        self.assertNotIn("\nhttps://",msg)
        self.assertLess(len(msg),3800)
        anchor=watcher.source_link("원문 & 보고서","https://example.com/report?a=1&b=2")
        self.assertIn("report?a=1&amp;b=2",anchor)
        self.assertIn("원문 &amp; 보고서",anchor)
        self.assertEqual(html_unescape(links[0][0]),watcher.SEED_PUBLISHERS["CoinDesk"])
        for invalid in ("javascript:alert(1)","http://example.com","https://user:pass@example.com/a"):
            with self.assertRaises(RuntimeError):
                watcher.source_link("invalid",invalid)

    def test_dynamic_source_links_are_html_safe(self):
        proof=[
            {"publisher":"coindesk","signals":["copper_short"],
             "published":NOW.isoformat(),"url":"https://www.coindesk.com/a?x=1&y=2"},
            {"publisher":"barrons","signals":["copper_short"],
             "published":NOW.isoformat(),"url":"https://www.barrons.com/a"},
        ]
        msg=watcher.news_message([("copper_short",proof)])
        self.assertIn("<b>이번 신규 변화</b>",msg)
        self.assertIn("coindesk</a>",msg)
        self.assertIn("a?x=1&amp;y=2",msg)
        self.assertLess(len(msg),3600)

    def test_telegram_payload_html_is_guarded_without_network(self):
        me=MagicMock()
        me.__enter__.return_value=io.BytesIO(json.dumps({
            "ok":True,"result":{"username":watcher.BOT_USERNAME}
        }).encode())
        sent=MagicMock()
        sent.__enter__.return_value=io.BytesIO(json.dumps({
            "ok":True,"result":{"message_id":987,"chat":{"id":12345}}
        }).encode())
        calls=[]
        def no_network(request,timeout=None):
            calls.append(request)
            return me if len(calls)==1 else sent
        with patch.dict(os.environ,{"THIRTEENF_TELEGRAM_BOT_TOKEN":"fake-test-token",
                                   "THIRTEENF_TELEGRAM_CHAT_ID":"12345"}),\
             patch.object(watcher,"urlopen",side_effect=no_network):
            receipt=watcher.telegram_send(watcher.seed_message())
        self.assertEqual(receipt["message_id"],987)
        self.assertEqual(receipt["chat_id"],"12345")
        self.assertEqual(len(calls),2)
        sent_payload=parse_qs(calls[1].data.decode())
        self.assertEqual(sent_payload["parse_mode"],["HTML"])
        self.assertEqual(json.loads(sent_payload["link_preview_options"][0]),{"is_disabled":True})
        self.assertIn('<a href=',sent_payload["text"][0])

    def test_strict_no_live_telegram(self):
        with patch.object(watcher,"http_bytes",return_value=b"<rss/>") as ignored:
            self.assertEqual(watcher.signals_from_text("nothing relevant"),[])
        state=watcher.empty_state()
        state["sent_events"][watcher.SEED_KEY]={"receipt":{"message_id":1}}
        with patch.object(watcher,"load_state",return_value=state),\
             patch.object(watcher,"discover",return_value=([],{"google":{"ok":True},"bing":{"ok":True}})),\
             patch.object(watcher,"telegram_send") as sending,\
             patch.object(watcher,"save_state") as saving:
            self.assertEqual(watcher.main(),0)
            sending.assert_not_called()
            saving.assert_not_called()

if __name__=="__main__":
    unittest.main(verbosity=2)
