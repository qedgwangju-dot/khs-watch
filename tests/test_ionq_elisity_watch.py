#!/usr/bin/env python3
from scripts import ionq_elisity_watch as q
from datetime import datetime
def main():
    assert q.stage("IonQ to Acquire Elisity to Accelerate Zero Trust for the Quantum Era")[0]=="agreement"
    assert q.stage("IonQ completes acquisition of Elisity")[0]=="closing"
    assert q.stage("IonQ receives regulatory approval for Elisity acquisition")[0]=="regulatory"
    assert q.stage("IonQ amends Elisity acquisition agreement terms")[0]=="amendment"
    assert q.stage("IonQ terminates Elisity acquisition agreement")[0]=="termination"
    assert q.stage("IonQ launches new quantum chip") is None
    assert q.publisher_allowed("IonQ")
    assert not q.publisher_allowed("AD HOC NEWS")
    assert not q.publisher_allowed("Fake IonQ News")
    assert q.BASELINE=="ionq-elisity:agreement:2026-10-12"
    # Future/conditional language must never become an executed milestone.
    assert q.stage("IonQ Elisity acquisition closing expected in fourth quarter") is None
    assert q.stage("IonQ Elisity acquisition expected to be completed in Q4") is None
    assert q.stage("IonQ expects regulatory approval for Elisity acquisition") is None
    assert q.stage("IonQ Elisity earnout payment expected next year") is None
    assert q.stage("IonQ Elisity acquisition integrated platform revenue expectations") is None
    assert q.stage("IonQ officially closes Elisity acquisition")[0]=="closing"
    assert q.stage("IonQ received regulatory approval for Elisity acquisition")[0]=="regulatory"
    assert q.stage("IonQ reports Elisity recurring revenue growth")[0]=="commercial"
    # A real RSS item must decode the three-part stage tuple without raising.
    import email.utils
    import xml.etree.ElementTree as ET
    now=q.now_kst()
    root=ET.Element("rss")
    channel=ET.SubElement(root,"channel")
    item=ET.SubElement(channel,"item")
    ET.SubElement(item,"title").text="IonQ completes acquisition of Elisity"
    ET.SubElement(item,"link").text="https://www.ionq.com/news/elisity-transaction-complete"
    ET.SubElement(item,"pubDate").text=email.utils.format_datetime(now)
    ET.SubElement(item,"source").text="IonQ"
    events=q.extract(root,now)
    assert len(events)==1, events
    assert events[0]["stage"]=="인수 거래 종결", events
    assert events[0]["key"].startswith("ionq-elisity:closing:"), events
    # A primary issuer release, correct event date, legacy sent key and click-only link.
    from pathlib import Path
    from tempfile import TemporaryDirectory
    from unittest.mock import patch
    fixed_now=datetime(2026,11,17,22,17,tzinfo=q.KST)
    closing_body=("IonQ Completes Acquisition of Elisity, Extending Quantum Security "
                  "for Enterprises and Government. November 4, 2026. "
                  "Today IonQ completed its acquisition of Elisity, Inc.")
    close=q.direct_official_closing(getter=lambda url:closing_body)
    assert close["event_date"]=="2026-11-03"
    assert q.already_seen({"ionq-elisity:closing:2026-11-04":{}},close)
    assert not q.already_seen({q.BASELINE:{}},close)
    rendered=q.report([close],fixed_now)
    assert '<a href="'+q.OFFICIAL_IONQ_CLOSING+'">원문</a>' in rendered
    assert "news.google.com" not in rendered and "&lt;a" not in rendered
    assert "실제 거래일: 2026-11-03" in rendered
    assert q.official_url("https://news.google.com/rss/articles/xxx")==""
    assert q.official_url("https://ionq.com.evil.example/news/x")==""
    assert q.official_url("javascript:alert(1)")==""
    assert q.official_url("https://www.ionq.com/news/example?x=1").endswith("/news/example?x=1")
    injection=dict(close,publisher="IonQ <script>x()</script>")
    assert "<script>" not in q.report([injection],fixed_now)
    assert q.verify_telegram_ack({"ok":True,"result":{"message_id":576,"chat":{"id":-1001234}}},"-1001234")==576
    for reply in (
        {"ok":True,"result":{"message_id":576,"chat":{"id":99}}},
        {"ok":True,"result":{"message_id":True,"chat":{"id":-1001234}}},
        {"ok":False,"result":{"message_id":576,"chat":{"id":-1001234}}},
    ):
        try: q.verify_telegram_ack(reply,"-1001234")
        except RuntimeError: pass
        else: raise AssertionError("Invalid Telegram receipt accepted")
    with TemporaryDirectory() as temp:
        path=Path(temp)/"state.json"
        with patch.object(q,"STATE",path):
            try: q.load()
            except RuntimeError: pass
            else: raise AssertionError("Missing state must fail closed")
            path.write_text("{broken",encoding="utf-8")
            try: q.load()
            except RuntimeError: pass
            else: raise AssertionError("Corrupt state must fail closed")
    def fake_get(url):
        if url==q.OFFICIAL_IONQ_AGREEMENT: return "IonQ to acquire Elisity definitive acquisition"
        if url==q.OFFICIAL_IONQ_CLOSING: return closing_body
        if url in [value for _,value in q.OFFICIAL_INDEXES]: return "<html></html>"
        return "<rss><channel></channel></rss>"
    with patch.object(q,"get",fake_get):
        rows,notes=q.collect(fixed_now)
    assert any(x["key"]==q.CLOSING_KEY for x in rows), rows
    assert all("news.google.com" not in x["url"] for x in rows)
    # Future changes without a primary publication date cannot become verified alerts.
    fake_index='<a href="/news/elisity-new-commercial-launch">IonQ reports Elisity recurring revenue growth</a>'
    def fake_index_get(url):
        if url==q.OFFICIAL_INDEXES[0][1]: return fake_index
        if url==q.OFFICIAL_INDEXES[1][1]: return "<html></html>"
        return "IonQ Elisity recurring revenue growth: no publication date"
    unpublished,_=q.verified_official_indexes(fixed_now,getter=fake_index_get)
    assert not unpublished,unpublished
    print("ionq_elisity_regression=passed")
if __name__=="__main__":main()
