#!/usr/bin/env python3
"""Conservative semantic guard for the independent space-launch Telegram watch."""
import datetime as dt
import hashlib
import re

RECENT_HOURS=48
TARGET=re.compile(r"price target|target price|목표주가|애널리스트 목표",re.I)
BROKER=re.compile(r"morgan stanley|pivotal research|citizens|citigroup|citi|"
                  r"keybanc|cantor fitzgerald|barclays|stifel|needham|"
                  r"analyst|애널리스트|증권사|목표주가",re.I)
DELAY=re.compile(r"delay|postpon|2027|pushed back|slips?|shift.*next year|"
                 r"연기|지연",re.I)
NOISE=re.compile(r"lawsuit|class action|options activity|why stock|insider sale|"
                 r"price prediction|주가 급등만|주가 전망만",re.I)
STOP=set(("rocket lab rocketlab spacex starship neutron electron flight first launch"
          " shares share price target stock stocks year 2026 2027 2028 the of to for"
          " and on in a an after by from with new company analyst said says may"
          " rocket satellite space story investing bloomberg reuters").split())
WORDS=re.compile(r"[a-zA-Z0-9가-힣]+")

def material_words(title):
    title=re.sub(r"\s+[-|]\s+[^-|]{1,65}$","",title.lower())
    return {w for w in WORDS.findall(title) if len(w)>2 and w not in STOP}

def kind(category,title):
    t=title.lower()
    if category=="rocketlab":
        if "neutron" in t and DELAY.search(t):return "development_delay"
        if TARGET.search(t) or BROKER.search(t):return "analyst"
        if re.search(r"contract|award|signed|secures|수주|계약",t):return "contract"
        return "development"
    if category=="spacex_valuation":
        if TARGET.search(t) or BROKER.search(t):return "analyst"
        return "space_technology"
    return "sector"

def eligible(category,item,now):
    title=str(item.get("title") or "")
    if not title or NOISE.search(title):return False
    date=item.get("published")
    if not date:return False
    try:pub=dt.datetime.fromisoformat(date)
    except (TypeError,ValueError):return False
    if pub.tzinfo is None:return False
    age=now-pub.astimezone(dt.timezone.utc)
    if not -dt.timedelta(minutes=20)<=age<=dt.timedelta(hours=RECENT_HOURS):
        return False
    if category=="rocketlab":
        if kind(category,title) in ("development_delay","analyst"):return False
        if not re.search(r"rocket lab|electron|neutron|synspective",title,re.I):return False
    if category=="spacex_valuation" and kind(category,title)=="analyst":
        return False
    return True

def semantic_pair(category,a,b):
    sa=str(a.get("source") or "").casefold().strip()
    sb=str(b.get("source") or "").casefold().strip()
    if not sa or not sb or sa==sb:return False
    ta,tb=str(a.get("title") or ""),str(b.get("title") or "")
    if NOISE.search(ta) or NOISE.search(tb):return False
    if kind(category,ta)!=kind(category,tb):return False
    x,y=material_words(ta),material_words(tb)
    common=x&y
    return len(common)>=2 and len(common)/max(1,len(x|y))>=0.4

def topic_key(category,title):
    s=title.lower()
    if category=="rocketlab" and "synspective" in s:
        return "electron_synspective"
    if category=="rocketlab" and "neutron" in s:
        return "neutron_development"
    if category=="spacex_valuation" and "flight 15" in s:
        return "flight15"
    word="|".join(sorted(material_words(title)))
    return hashlib.sha256(word.encode("utf-8")).hexdigest()[:14]

def semantic_id(category,item):
    pub=dt.datetime.fromisoformat(item["published"])
    monday=pub.date()-dt.timedelta(days=pub.weekday())
    event=kind(category,item["title"])
    return "semantic:"+category+":"+topic_key(category,item["title"])+":"+event+":"+monday.isoformat()

def self_test():
    now=dt.datetime(2026,10,17,10,tzinfo=dt.timezone.utc)
    article=lambda title,date="2026-10-16T10:00:00+00:00":dict(title=title,published=date,source="Reuters")
    assert kind("rocketlab","Rocket Lab Neutron first launch delayed to 2027")=="development_delay"
    assert kind("rocketlab","Citizens cuts Rocket Lab target after Neutron delay")=="development_delay"
    assert kind("spacex_valuation","Morgan Stanley raises SpaceX price target")=="analyst"
    assert not eligible("rocketlab",article("Rocket Lab Neutron debut delayed to 2027"),now)
    assert not eligible("rocketlab",article("Citizens lowers Rocket Lab price target on Neutron delay"),now)
    assert not eligible("spacex_valuation",article("Morgan Stanley raises SpaceX target price"),now)
    assert eligible("rocketlab",article("Rocket Lab signs Synspective Electron launch contract"),now)
    assert not eligible("rocketlab",article("Rocket Lab signs Synspective Electron launch contract","2026-10-12T10:00:00+00:00"),now)
    a=article("Rocket Lab secures Synspective 20-launch contract")
    b=dict(article("Synspective secures Rocket Lab 20-launch contract"),source="Bloomberg")
    c=dict(article("Citizens cuts Rocket Lab target after Neutron launch delay"),source="Bloomberg")
    assert semantic_pair("rocketlab",a,b) and not semantic_pair("rocketlab",a,c)
    assert semantic_id("rocketlab",a)==semantic_id("rocketlab",b)
    print("space_launch_event_guard_self_test=ok stale=1 categories=1 semantic_dedup=1")
if __name__=="__main__":self_test()
