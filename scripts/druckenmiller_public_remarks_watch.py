#!/usr/bin/env python3
"""New public remarks by Stanley Druckenmiller, independently from 13F.

Automatic news discovery is corroborated by separate original publishers;
publisher reprints are never counted twice. The first verified November 17
2026 TomorrowX event is a one-time, explicitly sourced historical seed.
No quotes are invented from RSS snippets and no price/portfolio position is
inferred from quarterly 13F disclosures.

Telegram send is one-shot and pre-reserved on GitHub to avoid timeout replay.
"""
from __future__ import annotations

from collections import defaultdict
from datetime import datetime, timedelta, timezone
from email.utils import parsedate_to_datetime
from html import unescape
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import parse_qs, quote, urlparse, unquote
from urllib.request import Request, urlopen
import hashlib
import json
import os
import re
import subprocess
import sys
import time
import xml.etree.ElementTree as ET


STATE_PATH=Path("data/druckenmiller_public_remarks_state.json")
OUT_DIR=Path("out")
BOT_USERNAME="khs887988798879_bot"
SEED_DATE="2026-11-17"
SEED_KEY="public-remarks:2026-11-17:TomorrowX:capital-defense-copper-short-AI-apps-v1"
PRIMARY_EVENT="https://tomorrowxsummit.com/"
SEED_PUBLISHERS={
    "CoinDesk":"https://www.coindesk.com/business/2026/11/17/druckenmiller-says-he-is-short-copper-warns-of-economic-weakness-in-2027",
    "Barron's":"https://www.barrons.com/livecoverage/stock-market-news-today-111726/card/druckenmiller-says-he-is-short-copper-D9N45T6gjlETmVy8E6he",
}
FED_OFFICIAL="https://www.federalreserve.gov/newsevents/pressreleases/monetary20261028a.htm"
ALL_SIGNALS={
    "equity":"순주식노출 낮춤·방어적",
    "copper":"구리 매도 포지션",
    "growth":"2027년 하반기 경제 둔화 경계",
    "ai":"AI 인프라보다 적용·수익화 중시",
    "risk":"자본 보존·대규모 베팅 자제",
    "fed_view":"연준 추가 긴축 우려(본인 판단)",
    "usd":"소규모 달러 매수(보도 기준)",
}
SPEECH_PATTERNS={
    "copper_short":(r"\bshort(?:ing)?\s+copper\b",r"\bcopper\s+short\b",
                    r"betting\s+against\s+copper",r"bearish\s+on\s+copper"),
    "copper_long":(r"\blong\s+copper\b",r"bullish\s+on\s+copper"),
    "equity_defensive":(r"little\s+net\s+exposure\s+to\s+equities",
                         r"neither\s+long\s+nor\s+short\s+equities",
                         r"not\s+long\s+or\s+short\s+equities",
                         r"capital\s+preservation",
                         r"preserving\s+capital",
                         r"low\s+net\s+(?:equity|stock)\s+exposure"),
    "equity_risk_on":(r"(?:raising|increasing)\s+(?:net\s+)?(?:equity|stock)\s+exposure",
                      r"(?:more|heavily)\s+long\s+(?:stocks|equities)"),
    "growth_2027":(r"(?:second\s+half|h2|late)\s+(?:of\s+)?['’]?27.{0,80}(?:econom|disappoint|weak)",
                   r"(?:second\s+half|h2|late)\s+(?:of\s+)?2027.{0,80}(?:econom|disappoint|weak)"),
    "ai_applications":(r"ai\s+(?:use\s+cases|applications).{0,65}(?:as\s+opposed|rather|infrastructure)",
                        r"(?:focus|shifting|shift).{0,80}(?:ai\s+applications|ai\s+use\s+cases)",
                        r"(?:tasks|outcomes)\s+instead\s+of\s+tokens"),
}
LABELS={
    "copper_short":"구리 매도 포지션",
    "copper_long":"구리 매수·강세 포지션",
    "equity_defensive":"주식 순노출 축소·자본보존",
    "equity_risk_on":"주식 위험노출 확대",
    "growth_2027":"2027년 하반기 경기 둔화 우려",
    "ai_applications":"AI 인프라보다 활용·성과 중심",
}
# Independent FIRST-PARTY editorial publishers. Republishing mirrors do not
# create a second confirmation. Google/Bing are discoverers, NOT publishers.
PUBLISHER_ALIASES={
    "coindesk":"coindesk", "barron's":"barrons","barrons":"barrons",
    "marketwatch":"marketwatch", "reuters":"reuters",
    "bloomberg":"bloomberg", "the wall street journal":"wsj",
    "wall street journal":"wsj","wsj":"wsj","cnbc":"cnbc",
    "financial times":"ft","the information":"theinformation",
}
ALLOWED_PUBLISHERS=set(PUBLISHER_ALIASES.values())
FALLBACK_PUBLISHER_URL={
    "coindesk.com":"coindesk","barrons.com":"barrons",
    "marketwatch.com":"marketwatch","reuters.com":"reuters",
    "bloomberg.com":"bloomberg","wsj.com":"wsj","cnbc.com":"cnbc",
    "ft.com":"ft","theinformation.com":"theinformation",
}


def iso_now():
    return datetime.now(timezone.utc)


def clean(text):
    text=re.sub(r"<[^>]+>"," ",str(text or ""))
    return " ".join(unescape(text).split())


def original_link(raw):
    parsed=urlparse(str(raw or ""))
    if parsed.netloc.lower().endswith("bing.com") and parsed.path.endswith("/apiclick.aspx"):
        extracted=parse_qs(parsed.query).get("url",[])
        if extracted:
            return unquote(extracted[0]) if "%3A" in extracted[0] else extracted[0]
    return str(raw or "")


def publisher(name,link=""):
    base=clean(name).lower().strip()
    for key,canonical in PUBLISHER_ALIASES.items():
        if key==base or base.startswith(key+" "):
            return canonical
    domain=(urlparse(original_link(link)).hostname or "").lower().removeprefix("www.")
    for suffix,canonical in FALLBACK_PUBLISHER_URL.items():
        if domain==suffix or domain.endswith("."+suffix):
            return canonical
    return None


def is_about_druckenmiller(title,description):
    combined=(title+" "+description).lower()
    return ("druckenmiller" in combined or "duquesne family office" in combined)


def signals_from_text(text):
    value=clean(text).lower().replace("’","'")
    found=[]
    for key,expressions in SPEECH_PATTERNS.items():
        if not any(re.search(pattern,value,re.I) for pattern in expressions):
            continue
        if key=="copper_short" and re.search(r"(?:not|no\s+longer)\s+short(?:ing)?\s+copper",value):
            continue
        found.append(key)
    return sorted(found)


def parse_date(raw):
    try:
        date=parsedate_to_datetime(str(raw or ""))
        if date.tzinfo is None:
            date=date.replace(tzinfo=timezone.utc)
        return date.astimezone(timezone.utc)
    except (TypeError, ValueError, IndexError):
        return None


def parse_rss(raw,source_name,now=None):
    now=now or iso_now()
    root=ET.fromstring(raw)
    results=[]
    for item in root.findall(".//item")[:80]:
        title=clean(item.findtext("title"))
        description=clean(item.findtext("description"))
        date=parse_date(item.findtext("pubDate"))
        if not date or (now-date)>timedelta(days=4) or (date-now)>timedelta(hours=6):
            continue
        link=original_link(item.findtext("link") or "")
        src=item.findtext("source") or ""
        # Bing RSS has <News:Source>; find by local namespace name.
        for node in item:
            if node.tag.lower().endswith("}source"):
                src=src or (node.text or "")
        if source_name=="coindesk":
            src="CoinDesk"
        elif source_name=="google" and not src and " - " in title:
            src=title.rsplit(" - ",1)[-1]
        label=publisher(src,link)
        if not label or not is_about_druckenmiller(title,description):
            continue
        if "coindesk" in (title+" "+description).lower() and label not in ("coindesk",):
            # Syndication or a roundup that explicitly credits CoinDesk
            # cannot corroborate the original CoinDesk article.
            if any(x in (title+" "+description).lower()
                   for x in ("according to coindesk","source: coindesk","originally published by coindesk")):
                label="coindesk"
        events=signals_from_text(title+" "+description)
        if not events:
            continue
        results.append({"title":title,"description":description,
                        "url":link,"publisher":label,
                        "published":date.isoformat(),"signals":events,
                        "source":source_name})
    return results


def feed_urls():
    query1='"Stanley Druckenmiller"'
    query2='"Druckenmiller" copper stocks economy AI'
    return {
        "google":"https://news.google.com/rss/search?q="+quote(query1+" when:7d")+
                 "&hl=en-US&gl=US&ceid=US:en",
        "bing":"https://www.bing.com/news/search?q="+quote(query2)+
               "&format=rss&setmkt=en-US",
        "coindesk":"https://www.coindesk.com/arc/outboundfeeds/rss/",
    }


def http_bytes(url,max_bytes=3_000_000,attempts=2):
    last=None
    for trial in range(attempts):
        try:
            req=Request(url,headers={"User-Agent":"Mozilla/5.0 (compatible; KHSWatch/1.0; public-news-rss)",
                                      "Accept":"application/xml,application/rss+xml,text/xml,*/*"})
            with urlopen(req,timeout=22) as resp:
                body=resp.read(max_bytes+1)
                if len(body)>max_bytes:
                    raise RuntimeError("News RSS feed too large")
                if not body:
                    raise RuntimeError("News RSS feed empty")
                return body
        except (HTTPError,URLError,TimeoutError,OSError,RuntimeError) as e:
            last=e
            if trial+1<attempts:
                time.sleep(1+trial)
    raise RuntimeError(f"source fetch failure {urlparse(url).hostname}: {type(last).__name__}") from last


def discover(now=None,fetch=http_bytes):
    now=now or iso_now()
    all_items=[]
    health={}
    for name,url in feed_urls().items():
        try:
            itemlist=parse_rss(fetch(url),name,now)
            health[name]={"ok":True,"matches":len(itemlist)}
            all_items.extend(itemlist)
        except (ET.ParseError,RuntimeError,ValueError) as error:
            health[name]={"ok":False,"error":type(error).__name__}
    # De-duplicate indexes of the same editorial story.
    dedup={}
    for article in all_items:
        key=(article["publisher"],
             re.sub(r"\W+"," ",article["title"].lower()).strip()[:130])
        dedup.setdefault(key,article)
    return list(dedup.values()),health


def corroborated(articles,now=None):
    now=now or iso_now()
    grouped=defaultdict(dict)
    for a in articles:
        for key in a["signals"]:
            # One original publisher = one source; multiple search engines
            # or republishing same report never add confidence.
            grouped[key].setdefault(a["publisher"],a)
    valid={}
    for key,sources in grouped.items():
        if len(sources)<2:
            continue
        if key not in LABELS:
            continue
        ordered=sorted(sources.values(),key=lambda x:x["published"],reverse=True)
        if not any(now-datetime.fromisoformat(x["published"])<timedelta(hours=72)
                   for x in ordered):
            continue
        valid[key]=ordered[:3]
    # Contradictory reports on the SAME position cannot be treated as verified.
    if "copper_short" in valid and "copper_long" in valid:
        valid.pop("copper_short")
        valid.pop("copper_long")
    if "equity_defensive" in valid and "equity_risk_on" in valid:
        valid.pop("equity_defensive")
        valid.pop("equity_risk_on")
    return valid


def empty_state():
    return {"version":1,"sent_events":{},"signal_values":{},"pending":None,
            "last_success":None}


def load_state():
    if not STATE_PATH.exists():
        return empty_state()
    state=json.loads(STATE_PATH.read_text(encoding="utf-8"))
    if state.get("version")!=1 or not isinstance(state.get("sent_events"),dict):
        raise RuntimeError("Public remarks state invalid; refuse to send")
    if state.get("pending"):
        print("DRUCKENMILLER_DELIVERY_UNCERTAIN pending GitHub reservation; manual reconciliation required")
        return None
    return state


def save_state(state):
    STATE_PATH.parent.mkdir(exist_ok=True)
    STATE_PATH.write_text(json.dumps(state,ensure_ascii=False,indent=2,sort_keys=True)+"\n",
                          encoding="utf-8")


def seed_ready(state,now):
    start=datetime(2026,11,17,tzinfo=timezone.utc)
    return (SEED_KEY not in state["sent_events"] and
            start <= now <= start+timedelta(days=4))


def seed_message():
    return "\n".join([
        "[드러켄밀러 투자 기조 변화 | 11월 17일 TomorrowX]",
        "판정: 행사 주최측 발표와 서로 다른 두 언론 보도 대조",
        "■ 주식: 순노출 낮게 유지·소규모 롱/숏, 전량 매도 확정 아님",
        "■ 구리: 매도(숏) 포지션 보유 발언",
        "■ 경기: 2027년 하반기 둔화 가능성 경계, 지금 경기침체 확정 아님",
        "■ 투자전략: 큰 베팅보다 자본 보존·불확실성 해소를 우선",
        "■ AI: 인프라 투자 기업보다 AI 적용·수익모델을 중시",
        "■ 연준: 발언의 '긴축'은 그의 정책 판단; 10월 28일 FOMC는 3.75~4.00% 동결",
        "※ 11월 17일 발언과 9월 30일 13F 보유 신고는 날짜와 조사 대상이 다릅니다.",
        "※ 행사 발언 전문·전체 영상은 별도 미열람. 정확한 개별 인용보다 취재로 확인된 내용만 표시.",
        "행사 공식: "+PRIMARY_EVENT,
        "CoinDesk: "+SEED_PUBLISHERS["CoinDesk"],
        "Barron's: "+SEED_PUBLISHERS["Barron's"],
        "FOMC: "+FED_OFFICIAL,
    ])


def news_candidates(state,articles,now):
    ready=corroborated(articles,now)
    changed=[]
    for signal,proof in ready.items():
        last=state.get("signal_values",{}).get(signal,{})
        published=datetime.fromisoformat(proof[0]["published"])
        if (last.get("value")==signal and last.get("event_date") and
                (published.date()-datetime.fromisoformat(last["event_date"]).date()).days<90):
            continue
        changed.append((signal,proof))
    changed.sort(key=lambda x:x[0])
    return changed[:6]


def news_message(changed):
    lines=["[드러켄밀러 새 공개발언 · 독립 출처 교차검증]",
           "■ 새로운 투자 판단·포지션 변화"]
    for signal,proof in changed:
        lines.append("• "+LABELS[signal]+" (보도일 "+proof[0]["published"][:10]+")")
        for article in proof[:2]:
            lines.append("  "+article["publisher"]+": "+article["url"])
    lines += ["※ 독립 언론 2곳 이상에서 같은 내용을 보도했을 때만 발송합니다.",
              "※ 뉴스 검색 RSS 제목·요약 기반 교차검증입니다. 원문 발언 전문과 실제 포지션 명세의 직접 확인은 별개입니다.",
              "※ 13F 분기말 주식 보유가 구리 선물·주식 공매도·현금잔액을 증명하지 않습니다."]
    result="\n".join(lines)
    if len(result)>3600:
        raise RuntimeError("Public remarks digest unexpectedly long")
    return result


def run_git(args):
    return subprocess.run(["git",*args],capture_output=True,text=True)


def commit_state(message):
    """Push prior to sending, or commit final receipt afterward, without force."""
    config=run_git(["config","user.name","github-actions[bot]"])
    run_git(["config","user.name","github-actions[bot]"])
    run_git(["config","user.email","41898282+github-actions[bot]@users.noreply.github.com"])
    staged=run_git(["add",str(STATE_PATH)])
    if staged.returncode:
        raise RuntimeError("Cannot stage state: "+staged.stderr[-200:])
    diff=run_git(["diff","--cached","--quiet"])
    if diff.returncode==0:
        raise RuntimeError("Expected delivery state update was not staged")
    result=run_git(["commit","-m",message])
    if result.returncode:
        raise RuntimeError("Cannot commit state "+result.stderr[-250:])
    for n in range(4):
        fetched=run_git(["fetch","origin","main"])
        if fetched.returncode:
            raise RuntimeError("Cannot fetch GitHub main")
        rebase=run_git(["rebase","origin/main"])
        if rebase.returncode:
            run_git(["rebase","--abort"])
            raise RuntimeError("GitHub state rebase conflict; no force push")
        pushed=run_git(["push","origin","HEAD:main"])
        if pushed.returncode==0:
            return True
        time.sleep(1+n)
    raise RuntimeError("Cannot push delivery state (four attempts); no automatic resend")


def telegram_send(message):
    token=(os.getenv("THIRTEENF_TELEGRAM_BOT_TOKEN") or "").strip()
    chat=(os.getenv("THIRTEENF_TELEGRAM_CHAT_ID") or
          os.getenv("KHS_POLICY_TELEGRAM_CHAT_ID") or "").strip()
    if not token or not chat:
        raise RuntimeError("Existing Telegram bot/chat secrets not configured")
    if len(message)>3800:
        raise RuntimeError("Telegram message exceeds single-send guard")
    base=f"https://api.telegram.org/bot{token}/"
    with urlopen(base+"getMe",timeout=20) as resp:
        me=json.load(resp)
    username=str((me.get("result") or {}).get("username") or "").lower()
    if not me.get("ok") or username!=BOT_USERNAME:
        raise RuntimeError("Wrong Telegram bot; no message sent")
    from urllib.parse import urlencode
    payload=urlencode({"chat_id":chat,"text":message,
                       "disable_web_page_preview":"true"}).encode()
    # Deliberate one attempt. A lost response may conceal successful delivery;
    # persistent pending state blocks all future automatic retries.
    req=Request(base+"sendMessage",data=payload)
    with urlopen(req,timeout=28) as resp:
        result=json.load(resp)
    receipt=result.get("result") or {}
    mid=receipt.get("message_id")
    actual=str((receipt.get("chat") or {}).get("id") or "")
    if not result.get("ok") or mid is None or not actual:
        raise RuntimeError("Telegram send receipt incomplete; no auto resend")
    if chat.lstrip("-").isdigit() and actual!=chat:
        raise RuntimeError("Unexpected Telegram chat recipient; no auto resend")
    return {"bot":username,"message_id":mid,"chat_id":actual,
            "sent_at":iso_now().isoformat()}


def main():
    now=iso_now()
    state=load_state()
    if state is None:
        return 0  # block new sends; do not overwrite the pending state
    probe=(os.getenv("DRUCKENMILLER_PROBE_ONLY") or "false").lower()=="true"
    source_items,health=discover(now)
    healthy=sum(1 for x in health.values() if x.get("ok"))
    print(f"DRUCKENMILLER_NEWS_SOURCE_HEALTH={healthy}/3 "
          f"matches={len(source_items)} detail={json.dumps(health,ensure_ascii=False)}")

    boot=seed_ready(state,now)
    changes=news_candidates(state,source_items,now)
    if boot:
        message=seed_message()
        event=SEED_KEY
        recorded={key:{"value":key,"event_date":SEED_DATE+"T00:00:00+00:00"}
                  for key in ("copper_short","equity_defensive","growth_2027","ai_applications")}
        # Also treat the specific 11/17 remarks as prior coverage; reused
        # summaries should not trigger multiple follow-up alerts.
        for key in ("copper_short","equity_defensive","growth_2027","ai_applications"):
            changes=[item for item in changes if item[0]!=key]
    elif changes and healthy>=1:
        labels=";".join(key for key,_ in changes)
        earliest=min(item[1][0]["published"][:10] for item in changes)
        event="public-remarks:"+earliest+":"+hashlib.sha256(labels.encode()).hexdigest()[:16]
        if event in state["sent_events"]:
            print("DRUCKENMILLER_NO_NEW_SIGNALS duplicate_event_key")
            return 0
        message=news_message(changes)
        recorded={key:{"value":key,"event_date":proof[0]["published"],
                       "outlets":[x["publisher"] for x in proof[:3]]} for key,proof in changes}
    else:
        if healthy==0:
            raise RuntimeError("All three public-news sources unavailable; cannot declare no change")
        print("DRUCKENMILLER_NO_NEW_SIGNALS")
        return 0

    if probe:
        print(f"DRUCKENMILLER_PROBE_ONLY event={event} chars={len(message)} "
              f"independent_sources_seed={len(SEED_PUBLISHERS) if boot else 'dynamic'}")
        print("DRUCKENMILLER_PREVIEW_BEGIN\n"+message+"\nDRUCKENMILLER_PREVIEW_END")
        return 0

    state["pending"]={"key":event,"reserved_at":now.isoformat(),
                      "verified_mode":"two_reported_publishers" if boot else "rss_two_independent_editorial_sources"}
    save_state(state)
    commit_state("Reserve Druckenmiller public remarks Telegram alert before send")
    print("DRUCKENMILLER_PRE_SEND_RESERVATION_COMMITTED")
    receipt=telegram_send(message)
    state["pending"]=None
    state["sent_events"][event]={"receipt":receipt,"date":now.date().isoformat()}
    state["signal_values"].update(recorded)
    state["last_success"]=receipt
    save_state(state)
    commit_state("Confirm Druckenmiller public remarks Telegram delivery")
    print(f"DRUCKENMILLER_TELEGRAM_CONFIRMED message_id={receipt['message_id']} chat_id_confirmed=true")
    return 0


if __name__=="__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:
        print(f"DRUCKENMILLER_WATCH_ERROR={type(exc).__name__} {exc}",file=sys.stderr)
        raise
