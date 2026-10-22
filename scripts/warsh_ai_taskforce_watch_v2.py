#!/usr/bin/env python3
"""Gartner 공식 Newsroom 우선 + RSS 보조 고신호 필터."""
import email.utils
import html
import json
import re
import urllib.parse
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from html.parser import HTMLParser

import warsh_ai_taskforce_watch as base

HIGH_SIGNAL=[
    r"future of work", r"more jobs than it eliminates", r"job creation", r"job losses?",
    r"rehir", r"layoff", r"workforce costs?", r"job impacts?", r"job chaos",
    r"role redesign", r"job redesign", r"roles? .* eliminated", r"roles? .* created",
    r"employment", r"labor market", r"workforce.*AI", r"AI.*workforce",
]
OFFICIAL_ARCHIVES=[
    # GitHub Actions에서는 Gartner의 공개 AWS 배포 경로가 더 안정적으로 응답한다.
    # 둘 다 Gartner 공식 Newsroom 콘텐츠이며, 실패 시 www 원본 경로를 재시도한다.
    "https://gcom.pdo.aws.gartner.com/en/newsroom/archive",
    "https://www.gartner.com/en/newsroom/archive",
]


class AnchorParser(HTMLParser):
    def __init__(self):
        super().__init__(); self.current=None; self.links=[]
    def handle_starttag(self,tag,attrs):
        if tag.lower()=="a":
            href=dict(attrs).get("href")
            if href:self.current={"href":href,"text":[]}
    def handle_data(self,data):
        if self.current is not None:self.current["text"].append(data)
    def handle_endtag(self,tag):
        if tag.lower()=="a" and self.current is not None:
            self.links.append((self.current["href"]," ".join(self.current["text"])))
            self.current=None


def high_signal(title):
    low=(title or "").lower()
    if "announces gartner hr symposium" in low:
        return False
    return any(re.search(p,title or "",re.I) for p in HIGH_SIGNAL)


def _date_from_url(url):
    m=re.search(r"/press-releases/(20\d{2})-(\d{1,2})-(\d{1,2})-",url,re.I)
    if not m:return None
    try:
        return datetime(int(m.group(1)),int(m.group(2)),int(m.group(3)),tzinfo=timezone.utc)
    except ValueError:
        return None


def official_gartner_items():
    errors=[]
    for archive in OFFICIAL_ARCHIVES:
        try:
            raw=base.fetch(archive)
            p=AnchorParser(); p.feed(raw)
            items=[]; seen=set()
            for href,label in p.links:
                href=urllib.parse.urljoin(archive,html.unescape(href or ""))
                if "/en/newsroom/press-releases/" not in href:continue
                title=html.unescape(re.sub(r"\s+"," ",label or "")).strip()
                if len(title)<20 or not high_signal(title):continue
                if href in seen:continue
                d=_date_from_url(href)
                if not d:continue
                seen.add(href)
                items.append({"title":title,"url":href.split("?")[0],"published":d.isoformat()})
            if items:
                items.sort(key=lambda x:x["published"])
                print(json.dumps({
                    "gartner_source_status":"공식 Newsroom 직접 조회",
                    "source":archive,
                    "items":len(items),
                },ensure_ascii=False))
                return items
            errors.append(f"{archive}: relevant items not found")
        except Exception as exc:
            errors.append(f"{archive}: {type(exc).__name__}")
    raise RuntimeError(" / ".join(errors))


def rss_gartner_items():
    q=urllib.parse.urlencode({"q":base.GARTNER_QUERY,"hl":"en-US","gl":"US","ceid":"US:en"})
    root=ET.fromstring(base.fetch("https://news.google.com/rss/search?"+q))
    items=[]
    for item in root.findall("./channel/item")[:40]:
        title=html.unescape((item.findtext("title") or "").strip())
        link=(item.findtext("link") or "").strip()
        src=item.find("source"); source=html.unescape((src.text or "").strip()) if src is not None else ""
        if source.lower()!="gartner" or not high_signal(title):continue
        pub=item.findtext("pubDate") or ""
        try:dt=email.utils.parsedate_to_datetime(pub).astimezone(timezone.utc)
        except Exception:dt=datetime.min.replace(tzinfo=timezone.utc)
        items.append({"title":title,"url":link,"published":dt.isoformat()})
    items.sort(key=lambda x:x["published"])
    return items


OFFICIAL_RSS = (
    "https://www.gartner.com/en/newsroom/rss",
    "https://www.gartner.com/newsroom/rss",
)


def official_rss_items():
    errors = []
    for rss_url in OFFICIAL_RSS:
        try:
            root = ET.fromstring(base.fetch(rss_url))
            nodes = root.findall('./channel/item')
            if not nodes:
                nodes = root.findall('.//{http://www.w3.org/2005/Atom}entry')
            items = []
            for node in nodes[:100]:
                title = html.unescape((node.findtext('title') or
                    node.findtext('{http://www.w3.org/2005/Atom}title') or '').strip())
                link = (node.findtext('link') or '').strip()
                if not link:
                    atom_link = node.find('{http://www.w3.org/2005/Atom}link')
                    link = (atom_link.get('href') or '') if atom_link is not None else ''
                if not high_signal(title):
                    continue
                # Canonical URL must be an official original article, not a
                # Google News token whose pubDate can resurface weeks later.
                original = base.canonical_gartner_item({'title':title,'url':link})
                if original is None:
                    continue
                items.append(original)
            if items:
                print(json.dumps({
                    'gartner_source_status':'Gartner 공식 뉴스 RSS',
                    'items':len(items),
                }, ensure_ascii=False))
                return items
            errors.append(rss_url + ':유효한 공식 보도자료 없음')
        except Exception as exc:
            errors.append(rss_url + ':' + type(exc).__name__)
    raise RuntimeError(' / '.join(errors))


def structural_gartner_items():
    errors = []
    try:
        return official_rss_items()
    except Exception as exc:
        errors.append('공식 RSS: ' + type(exc).__name__)
    try:
        official = official_gartner_items()
        if official:
            return official
    except Exception as exc:
        errors.append('공식 Newsroom: ' + type(exc).__name__)
    # Do not switch the delivery source to Google News: Google may supply
    # different URLs/timestamps for the same already-published article.
    print(json.dumps({
        'gartner_source_status':'공식 원천 불가·기준선 보존·보조 기사 발송 중단',
        'errors':errors,
    }, ensure_ascii=False))
    return []


base.gartner_items=structural_gartner_items

if __name__=="__main__":base.main()
