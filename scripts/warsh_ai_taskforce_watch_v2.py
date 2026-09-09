#!/usr/bin/env python3
"""High-signal Gartner filter for the Warsh AI productivity/jobs watcher."""
import email.utils
import html
import re
import urllib.parse
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
import warsh_ai_taskforce_watch as base

HIGH_SIGNAL=[
    r"future of work", r"more jobs than it eliminates", r"job creation", r"job losses?",
    r"rehir", r"workforce costs?", r"job impacts?", r"roles? .* eliminated",
    r"roles? .* created", r"employment", r"labor market", r"workforce.*AI",
]


def structural_gartner_items():
    q=urllib.parse.urlencode({'q':base.GARTNER_QUERY,'hl':'en-US','gl':'US','ceid':'US:en'})
    root=ET.fromstring(base.fetch('https://news.google.com/rss/search?'+q))
    items=[]
    for item in root.findall('./channel/item')[:40]:
        title=html.unescape((item.findtext('title') or '').strip())
        link=(item.findtext('link') or '').strip()
        src=item.find('source'); source=html.unescape((src.text or '').strip()) if src is not None else ''
        if source.lower()!='gartner' or not any(re.search(p,title,re.I) for p in HIGH_SIGNAL):continue
        pub=item.findtext('pubDate') or ''
        try:dt=email.utils.parsedate_to_datetime(pub).astimezone(timezone.utc)
        except Exception:dt=datetime.min.replace(tzinfo=timezone.utc)
        items.append({'title':title,'url':link,'published':dt.isoformat()})
    items.sort(key=lambda x:x['published'])
    return items

base.gartner_items=structural_gartner_items

if __name__=='__main__':base.main()
