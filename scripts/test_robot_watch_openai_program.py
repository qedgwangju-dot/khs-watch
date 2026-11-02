#!/usr/bin/env python3
"""Offline no-send checks for existing-route OpenAI robotics monitoring."""
from __future__ import annotations
import datetime as dt
import io
from types import SimpleNamespace
from unittest.mock import patch
from zoneinfo import ZoneInfo

import robot_watch_openai_robotics_program as m

def item(title, description, source, pub="2026-11-02T02:00:00+00:00"):
    return {"title":title,"description":description,"source":source,
            "published":pub,"link":"https://example.invalid/offline-fixture"}

def make_base():
    def prev_group(t):
        if "OpenAI" in t and "humanoid" in t:
            return "openai_own_humanoid"
        return ""
    return SimpleNamespace(
      NOW=dt.datetime(2026,11,2,0,0,tzinfo=dt.timezone.utc),
      KST=ZoneInfo("Asia/Seoul"),QUERIES=["preexisting_query"],
      query_news=lambda q: [],
      topic_group=prev_group,
      score=lambda x:0,
      key=lambda x:"prior-state-key",
      category=lambda t,g:"preexisting-category",
      meaning=lambda cat:"preexisting meaning",
      risk=lambda cat:"preexisting risk",
      verification=lambda a,g,t:"preexisting verification",
      tag_for=lambda g:"preexisting tag",
      select_diverse=lambda items,seen,force,limit: [],
    )

def classify(base, row):
    text=" ".join(str(row.get(k) or "") for k in ("title","description","source"))
    group=base.topic_group(text)
    return group,base.score(row),base.key(row),base.category(text,group)

def run():
    base=make_base()
    m.install(base)
    assert m.RECOVERY_QUERY in base.QUERIES
    assert m.OPENAI_NEWS_FEED_QUERY in base.QUERIES
    assert m.CHEEKY_PINT_FEED_QUERY in base.QUERIES
    assert m.OPENAI_NEWS_FEED.startswith("https://openai.com/")
    assert m.CHEEKY_PINT_FEED.startswith("https://feeds.transistor.fm/")
    assert len(base.QUERIES)==len(set(base.QUERIES))

    recovered=base.query_news(m.RECOVERY_QUERY)
    assert len(recovered)==1
    g,s,k,c=classify(base,recovered[0])
    assert g==m.TOPIC and s>=11 and k==m.RECOVERY_KEY,(g,s,k)
    assert c==m.CATEGORY_BASE,(c,base.category(recovered[0]["description"],g))
    selected=[dict(recovered[0],key=k,score=s,group=g)]
    assert base.select_diverse(selected,set(),False,8)[0]["key"]==k
    assert base.select_diverse(selected,{k},False,8)==[]
    assert "현장" in base.risk(c)
    assert "계획" in base.verification(recovered[0],g,recovered[0]["description"])

    # Same CEO interview recirculated by press is not a second event.
    retelling=item(
        "Sam Altman OpenAI robots build data centers",
        "OpenAI CEO shares long term plan for robotics to build datacenters and factories.",
        "The Next Web","2026-11-01T00:00:00+00:00",
    )
    a,b,_,_=classify(base,retelling)
    assert a==m.TOPIC and b==0,(a,b)
    company_look=item(
        "OpenAI Robotics Software Engineer data center",
        "OpenAI hiring in robotics to plan hardware and data center component assembly.",
        "OpenAI","2026-11-01T00:00:00+00:00",
    )
    assert classify(base,company_look)[1]==0

    # Separate already-existing humanoid roadmap must remain untouched.
    own_demo_goal=item(
        "OpenAI 2027 humanoid demo",
        "OpenAI humanoid prototype planned for 2027.",
        "Fortune",
    )
    assert classify(base,own_demo_goal)[0]=="openai_own_humanoid"

    later_real=item(
        "OpenAI robot data center construction deployment",
        "OpenAI robots deployed at a data center construction site; verified actual operation.",
        "OpenAI",
    )
    g,s,k,c=classify(base,later_real)
    assert g==m.TOPIC and s>=11 and k!=m.RECOVERY_KEY,(g,s,k,c)
    assert "실제" in c,c
    assert base.verification(later_real,g,later_real["description"]).startswith("OpenAI 직접")

    future=item(
        "OpenAI to deploy robots at new data centers",
        "OpenAI will deploy robots at data center construction sites in the future; not yet deployed.",
        "OpenAI"
    )
    assert classify(base,future)[1]==0,"future target must not become a real deployment"

    external_unverified=dict(later_real,source="Anonymous Blog")
    assert classify(base,external_unverified)[1]==0,"unverified blog is not an official deployment"
    syndicated=dict(later_real,source="The Next Web")
    assert 11<=classify(base,syndicated)[1]<s,"reported vs issuer confirmed"
    assert classify(base,syndicated)[2]!=k,"reported vs official evidence keys separate"

    # Primary-source RSS parsing is checked with fake bytes and no HTTP.
    podcast_rss = b"""<?xml version="1.0" encoding="utf-8"?>
    <rss version="2.0"><channel><title>Cheeky Pint</title>
      <item><title>Sam Altman on superintelligence</title>
        <description>OpenAI CEO Sam Altman discusses robotics program to build data centers.</description>
        <link>https://cheekypint.transistor.fm/39/transcript</link>
        <pubDate>Thu, 29 Oct 2026 11:45:00 +0000</pubDate>
      </item>
      <item><title>Unrelated business interview</title>
        <description>No robotics content.</description>
        <link>https://cheekypint.transistor.fm/38/transcript</link>
      </item>
    </channel></rss>"""
    with patch.object(m.urllib.request,"urlopen",return_value=io.BytesIO(podcast_rss)):
        p_rows=base.query_news(m.CHEEKY_PINT_FEED_QUERY)
    assert len(p_rows)==1,(p_rows,)
    assert p_rows[0]["primary_feed"]=="Cheeky Pint"
    assert classify(base,p_rows[0])[0]==m.TOPIC
    assert classify(base,p_rows[0])[1]==0, "Past interview repeat is not fresh achievement"

    official_rss = b"""<?xml version="1.0" encoding="utf-8"?>
    <rss version="2.0"><channel><title>OpenAI News</title>
      <item><title>OpenAI robotics actual field deployment</title>
        <description>OpenAI robots deployed at a data center construction site.</description>
        <link>https://openai.com/news/robotics-construction</link>
        <pubDate>Mon, 02 Nov 2026 00:00:00 +0000</pubDate>
      </item>
    </channel></rss>"""
    with patch.object(m.urllib.request,"urlopen",return_value=io.BytesIO(official_rss)):
        n_rows=base.query_news(m.OPENAI_NEWS_FEED_QUERY)
    assert len(n_rows)==1 and n_rows[0]["source"]=="OpenAI"
    assert classify(base,n_rows[0])[1]>=11, "Official RSS achieved-stage evidence should surface"

    # Date-scoped, single historical catch-up; new stages are still tracked.
    base.NOW=dt.datetime(2026,11,7,0,0,tzinfo=dt.timezone.utc)
    assert base.query_news(m.RECOVERY_QUERY)==[]
    assert classify(base,later_real)[1]>=11

if __name__=="__main__":
    run()
    print("OpenAI robotics program no-send regression: PASS")
