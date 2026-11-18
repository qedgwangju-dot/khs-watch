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
        "OpenAI robots deployed at a Texas data center construction site; 20 robots; verified actual operation.",
        "OpenAI",
    )
    later_real["link"]="https://openai.com/news/robotics-texas-deployment"
    g,s,k,c=classify(base,later_real)
    assert g==m.TOPIC and s>=11 and k!=m.RECOVERY_KEY,(g,s,k,c)
    assert "실제" in c,c
    assert base.verification(later_real,g,later_real["description"]).startswith("OpenAI 공식 도메인")
    assert "원문 추가 검증" in base.verification(later_real,g,later_real["description"])

    future=item(
        "OpenAI to deploy robots at new data centers",
        "OpenAI will deploy robots at data center construction sites in the future; not yet deployed.",
        "OpenAI"
    )
    assert classify(base,future)[1]==0,"future target must not become a real deployment"

    external_unverified=dict(later_real,source="Anonymous Blog")
    assert classify(base,external_unverified)[1]==0,"unverified blog is not an official deployment"
    syndicated=dict(later_real,source="The Next Web",link="https://thenextweb.com/news/syndicated-deployment")
    assert 11<=classify(base,syndicated)[1]<s,"reported vs issuer confirmed"
    assert classify(base,syndicated)[2]==k,"The same event is not split by publisher grade"
    next_week=dict(syndicated,published="2026-11-09T02:00:00+00:00")
    assert classify(base,next_week)[2]==k,"A next-week reprint is not a second deployment"
    undated=dict(syndicated,published=None)
    assert classify(base,undated)[2]==k,"Unknown publication date does not change event identity"
    # Same week, stage and source can still contain different real milestones.
    arizona=dict(later_real,description=later_real["description"].replace("Texas","Arizona"))
    more_robots=dict(later_real,description=later_real["description"].replace("20 robots","30 robots"))
    assert classify(base,arizona)[2]!=k,"Different sites must not collide"
    assert classify(base,more_robots)[2]!=k,"Different physical quantities must not collide"
    dated_first=dict(later_real,description=later_real["description"]+"; deployment date: 2026-11-02")
    dated_next=dict(later_real,description=later_real["description"]+"; deployment date: 2026-11-09")
    assert classify(base,dated_first)[2]!=classify(base,dated_next)[2],"Actual event dates, not publication weeks, separate batches"
    models=dict(later_real,description=later_real["description"]+"; model: Atlas; project: Stargate; partner: ACME")
    for old,new in (("model: Atlas","model: Digit"),("project: Stargate","project: SampleB"),("partner: ACME","partner: OtherCo")):
        changed=dict(models,description=models["description"].replace(old,new))
        assert classify(base,changed)[2]!=classify(base,models)[2],(old,new)
    model_count=dict(later_real,description=later_real["description"].replace("20 robots","20 Atlas robots"))
    other_count=dict(model_count,description=model_count["description"].replace("20 Atlas","21 Atlas"))
    assert classify(base,model_count)[2]!=classify(base,other_count)[2]
    equivalent_count=dict(later_real,description=later_real["description"].replace("20 robots","20.0 robots"))
    assert classify(base,equivalent_count)[2]==k

    # Neither a company source name nor its RSS homepage proves an individual
    # article. Missing strong event identity is explicitly held for review.
    vague=item("OpenAI robots data center deployment",
               "OpenAI robots deployed at a data center construction site.","OpenAI")
    for blocked in (
        vague,
        dict(vague,source_url="https://openai.com/",link="https://news.google.com/rss/articles/opaque"),
        dict(vague,link="https://openai.com/"),
        dict(vague,link="https://openai.com/news/"),
        dict(vague,link="https://openai.com.evil.invalid/news/fake"),
        dict(vague,link="https://openai.com:8443/news/fake"),
        dict(vague,source="Reuters",link="https://reuters.com/ambiguous-report"),
    ):
        assert classify(base,blocked)[1]==0,blocked
        assert "검증 대기" in base.verification(blocked,m.TOPIC,blocked["description"])
    claimed=dict(later_real,link="https://example.invalid/unknown")
    assert classify(base,claimed)[1]<s
    assert "공식 개별 원문 URL 미확인" in base.verification(claimed,m.TOPIC,claimed["description"])
    # Explicit official-document fallback handles a specific article when the
    # short RSS summary lacks a site. Cross-document aliases need manual review.
    original_doc=dict(vague,link="https://openai.com/index/robotics-example")
    repeated_doc=dict(original_doc,published="2026-11-09T00:00:00+00:00",
                      link="https://www.openai.com/index/robotics-example/?utm_source=rss#details")
    assert classify(base,original_doc)[1]>=11
    assert classify(base,repeated_doc)[2]==classify(base,original_doc)[2]
    same_original=dict(repeated_doc,source="Reuters")
    assert classify(base,same_original)[2]==classify(base,original_doc)[2]
    assert "회사 확정 전" in base.verification(same_original,m.TOPIC,same_original["description"])
    different_doc=dict(original_doc,link="https://openai.com/index/robotics-another-example")
    assert classify(base,different_doc)[2]!=classify(base,original_doc)[2]
    # Existing fixed recovery/baseline identities and caller state are intact.
    assert m.RECOVERY_KEY=="ea8753527da594520445e46c399d8b03ef140e33ce7e1d5ff10ff06ed561ea68"
    assert classify(base,retelling)[2]=="cb7ee63fd0248d92f7fa8077c7328b008b9b242885437be36d15b2577304d918"
    seen={f"old-{i}" for i in range(941)}|{k}
    snapshot=seen.copy()
    rerun=dict(next_week,key=k,score=classify(base,next_week)[1],group=m.TOPIC)
    assert base.select_diverse([rerun],seen,False,8)==[]
    assert seen==snapshot and len(seen)==942

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

