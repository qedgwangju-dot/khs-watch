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
    print("ionq_elisity_regression=passed")
if __name__=="__main__":main()
