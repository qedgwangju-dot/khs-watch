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
from html import unescape, escape as html_escape
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
MS_VIDEO_CHANNEL="UCz6RzD6KG_hH_oHb2kyW5jQ"
MS_VIDEO_FEED="https://www.youtube.com/feeds/videos.xml?channel_id="+MS_VIDEO_CHANNEL
CORE_FEEDS=("google","bing","coindesk")
ALL_SIGNALS={
    "equity":"순주식노출 낮춤·방어적",
    "copper":"구리 매도 포지션",
    "growth":"2027년 하반기 경제 둔화 경계",
    "ai":"AI 인프라보다 적용·수익화 중시",
    "risk":"자본 보존·대규모 베팅 자제",
    "fed_view":"연준 추가 긴축 우려(본인 판단)",
    "usd":"소규모 달러 매수(보도 기준)",
}
SIGNAL_DIMENSION={
    "copper_short":"copper","copper_long":"copper",
    "equity_defensive":"equity","equity_risk_on":"equity",
    "growth_2027":"growth","ai_applications":"ai",
    "fed_hawkish":"fed_view","credit_stress":"credit","dollar_long":"usd",
    "copper_closed":"copper","equity_net_short":"equity",
    "fed_dovish":"fed_view","credit_easing":"credit","dollar_short":"usd",
}

SPEECH_PATTERNS={
    "copper_short":(r"\bshort(?:ing)?\s+copper\b",r"\bcopper\s+short\b",
                    r"betting\s+against\s+copper",r"bearish\s+on\s+copper"),
    "copper_long":(r"\blong\s+copper\b",r"bullish\s+on\s+copper"),
    "equity_defensive":(r"little\s+net\s+exposure\s+to\s+equities",
                         r"neither\s+long\s+nor\s+short\s+equities",
                         r"not\s+long\s+or\s+short\s+equities",
                         r"not\s+long\s+equities.{0,35}not\s+short\s+equities",
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
    "fed_hawkish":(r"fed\s+is\s+not\s+cutting.{0,30}(?:hiking|raising)",
                   r"federal\s+reserve.{0,50}hiking\s+rates"),
    "credit_stress":(r"credit\s+spreads\s+(?:widening|widened|are\s+wider)",
                     r"widening\s+credit\s+spreads"),
    "dollar_long":(r"(?:small|modest)\s+(?:long\s+)?(?:u\.s\.\s+)?dollar\s+(?:long\s+)?position",
                   r"(?:small|modest)\s+long\s+(?:u\.s\.\s+)?dollar"),
    "copper_closed":(r"\b(?:covered|closed(?: out)?|exited)\s+(?:his|our|their|the)\s+(?:short copper(?: position)?|copper short(?: position)?|short position in copper)\b",
                     r"\bno longer short copper\b"),
    "equity_net_short":(r"\b(?:now|currently)\s+net short\s+(?:stocks|equities)\b",),
    "fed_dovish":(r"\bnow\s+(?:expects?|anticipates?)\s+(?:the\s+)?fed\s+to\s+(?:cut|lower)\s+(?:interest\s+)?rates\b",),
    "credit_easing":(r"\bcredit spreads\s+(?:are\s+)?(?:now\s+)?(?:narrowing|tightening)\b",),
    "dollar_short":(r"\b(?:now|currently)\s+short\s+(?:the\s+)?(?:u\.s\.\s+)?dollar\b",),
}
LABELS={
    "copper_short":"구리 매도 포지션",
    "copper_long":"구리 매수·강세 포지션",
    "equity_defensive":"주식 순노출 축소·자본보존",
    "equity_risk_on":"주식 위험노출 확대",
    "growth_2027":"2027년 하반기 경기 둔화 우려",
    "ai_applications":"AI 인프라보다 활용·성과 중심",
    "fed_hawkish":"연준 긴축 전망(당사자 판단, 공식 결정 아님)",
    "credit_stress":"신용 스프레드 확대 경계",
    "dollar_long":"미국 달러 매수 포지션",
    "copper_closed":"구리 매도 포지션 청산",
    "equity_net_short":"주식 순매도 포지션 전환",
    "fed_dovish":"연준 금리 인하 전망 전환(당사자 판단)",
    "credit_easing":"신용 스프레드 축소·위험 완화 판단",
    "dollar_short":"미국 달러 매도 포지션 전환",
}
# Independent FIRST-PARTY editorial publishers. Republishing mirrors do not
# create a second confirmation. Google/Bing are discoverers, NOT publishers.
PUBLISHER_ALIASES={
    "coindesk":"coindesk", "barron's":"barrons","barrons":"barrons",
    "marketwatch":"marketwatch", "reuters":"reuters",
    "bloomberg":"bloomberg", "the wall street journal":"wsj",
    "wall street journal":"wsj","wsj":"wsj","cnbc":"cnbc",
    "financial times":"ft","the information":"theinformation",
    "realclearpolitics":"realclear","realclearmarkets":"realclear",
    "the street":"thestreet","thestreet":"thestreet",
}
ALLOWED_PUBLISHERS=set(PUBLISHER_ALIASES.values())
FALLBACK_PUBLISHER_URL={
    "coindesk.com":"coindesk","barrons.com":"barrons",
    "marketwatch.com":"marketwatch","reuters.com":"reuters",
    "bloomberg.com":"bloomberg","wsj.com":"wsj","cnbc.com":"cnbc",
    "ft.com":"ft","theinformation.com":"theinformation",
    "realclearpolitics.com":"realclear","realclearmarkets.com":"realclear",
    "thestreet.com":"thestreet",
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
    if "copper_closed" in found:
        found=[key for key in found if key!="copper_short"]
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
    if root.tag.lower()!="rss" or root.find("channel") is None:
        raise ValueError("Expected valid RSS channel; not HTML or a challenge page")
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
        elif source_name.startswith("google") and not src and " - " in title:
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
        # A later article about the already delivered 11/17 interview is
        # retrospective evidence, not a newly reported portfolio decision.
        seed_day=datetime.fromisoformat(SEED_DATE).date()
        known_seed=("tomorrowx" in (title+" "+description).lower()
                    and 0<=(date.date()-seed_day).days<=21)
        results.append({"title":title,"description":description,
                        "url":link,"publisher":label,
                        "published":date.isoformat(),"signals":events,
                        "source":source_name,
                        "known_event":SEED_KEY if known_seed else None})
    return results


def feed_urls():
    broad='Druckenmiller OR "Duquesne Family Office"'
    interview='(Druckenmiller OR "Duquesne Family Office") (interview OR summit OR remarks OR portfolio OR outlook)'
    return {
        "google":"https://news.google.com/rss/search?q="+quote(broad+" when:7d")+
                 "&hl=en-US&gl=US&ceid=US:en",
        "google_interviews":"https://news.google.com/rss/search?q="+quote(interview+" when:7d")+
                 "&hl=en-US&gl=US&ceid=US:en",
        "bing":"https://www.bing.com/news/search?q="+quote(broad)+
               "&format=rss&setmkt=en-US",
        "coindesk":"https://www.coindesk.com/arc/outboundfeeds/rss/",
    }


def official_video_metadata(raw,now):
    # Official host's video metadata is a discovery aid, not a transcript or
    # an independent second confirmation of any trading position.
    ns={"a":"http://www.w3.org/2005/Atom",
        "yt":"http://www.youtube.com/xml/schemas/2015"}
    root=ET.fromstring(raw)
    if root.tag!="{http://www.w3.org/2005/Atom}feed" or root.findtext("yt:channelId",namespaces=ns)!=MS_VIDEO_CHANNEL:
        raise ValueError("Invalid Morgan Stanley channel feed")
    result=[]
    for entry in root.findall("a:entry",ns):
        title=clean(entry.findtext("a:title",namespaces=ns))
        published=entry.findtext("a:published",namespaces=ns) or ""
        if not is_about_druckenmiller(title,""):
            continue
        date=datetime.fromisoformat(published.replace("Z","+00:00"))
        if date.tzinfo is None:
            raise ValueError("Official video publication time missing timezone")
        if not -timedelta(hours=6)<=now-date<=timedelta(days=14):
            continue
        video_id=entry.findtext("yt:videoId",namespaces=ns) or ""
        if not re.fullmatch(r"[A-Za-z0-9_-]{11}",video_id):
            raise ValueError("Invalid official video ID")
        result.append({"title":title,"video_id":video_id,"published":published,
                       "same_event":"tomorrowx" in title.lower()})
    return result


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
    try:
        videos=official_video_metadata(fetch(MS_VIDEO_FEED),now)
        health["morgan_stanley_video"]={"ok":True,"kind":"metadata_only","matches":len(videos),
                                       "videos":videos}
    except (ET.ParseError,RuntimeError,ValueError) as error:
        health["morgan_stanley_video"]={"ok":False,"kind":"metadata_only","error":type(error).__name__}
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
    # Conflicting directions within the same risk dimension fail closed.
    dimensions=defaultdict(list)
    for signal in valid:
        dimensions[SIGNAL_DIMENSION.get(signal,signal)].append(signal)
    for conflicting in dimensions.values():
        if len(conflicting)>1:
            for signal in conflicting:
                valid.pop(signal,None)
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
        raise RuntimeError("DRUCKENMILLER_DELIVERY_UNCERTAIN: pending GitHub reservation requires manual reconciliation")
    return state


def save_state(state):
    STATE_PATH.parent.mkdir(exist_ok=True)
    STATE_PATH.write_text(json.dumps(state,ensure_ascii=False,indent=2,sort_keys=True)+"\n",
                          encoding="utf-8")


def seed_ready(state,now):
    start=datetime(2026,11,17,tzinfo=timezone.utc)
    return (SEED_KEY not in state["sent_events"] and
            start <= now <= start+timedelta(days=4))


def source_link(label, url):
    """Telegram HTML anchor with a validated URL and escaped attributes."""
    parsed=urlparse(str(url or ""))
    if parsed.scheme != "https" or not parsed.hostname or parsed.username or parsed.password:
        raise RuntimeError("Telegram source URL must be a public HTTPS address")
    safe_url=html_escape(url,quote=True)
    return f'<a href="{safe_url}">{html_escape(label)}</a>'


def seed_message():
    return "\n".join([
        "<b>드러켄밀러 | 투자 기조 변화</b>",
        "2026년 11월 17일 · TomorrowX 공개 발언 관련 보도",
        "",
        "<b>한눈에 보기</b>",
        "■ <b>주식</b> 순노출 낮게 유지·소규모 매수/매도, 전량 매도 확정 아님",
        "■ <b>구리</b> 매도(숏) 포지션 보유",
        "■ <b>경기</b> 2027년 하반기 둔화 경계, 침체 확정 아님",
        "■ <b>투자전략</b> 큰 베팅보다 자본 보존 우선",
        "■ <b>위험 신호</b> 신용 스프레드 확대·원자재 약세 주시",
        "■ <b>AI</b> 인프라 구축보다 AI 활용·수익모델에 관심",
        "■ <b>연준</b> 추가 긴축 우려는 드러켄밀러의 견해;",
        "  10월 28일 공식 FOMC는 기준금리 3.75~4.00% 동결",
        "",
        "<b>쉽게 해석하면</b>",
        "지금은 공격적인 큰 투자보다 손실을 피하며 방향을 확인하겠다는 뜻입니다.",
        "",
        "<b>확인 범위</b>",
        "※ 11월 17일 발언과 9월 30일 13F 보유 신고는 기준 시점이 다릅니다.",
        "※ 행사 발언 전문·전체 영상은 별도 미열람; 보도로 확인된 내용만 전달.",
        "",
        "<b>출처 (선택하면 원문 이동)</b>",
        source_link("CoinDesk 보도", SEED_PUBLISHERS["CoinDesk"])
        +" · "+source_link("Barron's 보도", SEED_PUBLISHERS["Barron's"]),
        source_link("TomorrowX 행사 안내",PRIMARY_EVENT)
        +" · "+source_link("10/28 FOMC 공식 성명",FED_OFFICIAL),
    ])


def news_candidates(state,articles,now):
    if SEED_KEY in state.get("sent_events",{}):
        articles=[article for article in articles if article.get("known_event")!=SEED_KEY]
    ready=corroborated(articles,now)
    changed=[]
    for signal,proof in ready.items():
        dimension=SIGNAL_DIMENSION.get(signal,signal)
        last=state.get("signal_values",{}).get(dimension,{})
        published=datetime.fromisoformat(proof[0]["published"])
        if last.get("event_date") and published<=datetime.fromisoformat(last["event_date"]):
            continue
        if (last.get("value")==signal and last.get("event_date") and
                (published.date()-datetime.fromisoformat(last["event_date"]).date()).days<90):
            continue
        changed.append((signal,proof))
    changed.sort(key=lambda x:x[0])
    return changed[:6]


def news_message(changed):
    lines=[
        "<b>드러켄밀러 | 새 공개발언</b>",
        "독립 매체 2곳 이상에서 같은 투자 판단을 보도한 경우",
        "",
        "<b>이번 신규 변화</b>",
    ]
    for signal,proof in changed:
        label=html_escape(LABELS[signal])
        date=html_escape(proof[0]["published"][:10])
        lines.append("■ <b>"+label+"</b> · 보도일 "+date)
        original_links=[
            source_link(a["publisher"],a["url"]) for a in proof[:2]
        ]
        lines.append("  원문: "+" · ".join(original_links))
    lines += [
        "",
        "<b>확인 범위</b>",
        "※ 독립 편집 매체 2곳의 보도 일치에 근거합니다.",
        "※ 제목·요약문 기반 판정이며 발언 전문과 포지션 증빙은 별도 확인 대상입니다.",
        "※ 분기별 13F만으로 구리 선물·공매도·현금 보유를 판단하지 않습니다.",
    ]
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


def telegram_preflight(expected_chat=None,check_live_chat=False):
    """Confirm bot identity and recipient before reserving a delivery."""
    token=(os.getenv("THIRTEENF_TELEGRAM_BOT_TOKEN") or "").strip()
    chat=(os.getenv("THIRTEENF_TELEGRAM_CHAT_ID") or
          os.getenv("KHS_POLICY_TELEGRAM_CHAT_ID") or "").strip()
    if not token or not chat:
        raise RuntimeError("Existing Telegram bot/chat secrets not configured")
    base=f"https://api.telegram.org/bot{token}/"
    from urllib.parse import urlencode
    try:
        with urlopen(base+"getMe",timeout=20) as resp:
            me=json.load(resp)
        username=str((me.get("result") or {}).get("username") or "").lower()
        if me.get("ok") is not True or username!=BOT_USERNAME:
            raise RuntimeError("Wrong Telegram bot")
        resolved=chat
        if check_live_chat or not chat.lstrip("-").isdigit():
            with urlopen(base+"getChat?"+urlencode({"chat_id":chat}),timeout=20) as resp:
                target=json.load(resp)
            actual=(target.get("result") or {}).get("id")
            if target.get("ok") is not True or type(actual) is not int or not actual:
                raise RuntimeError("Telegram getChat did not confirm numeric chat identity")
            resolved=str(actual)
            if chat.lstrip("-").isdigit() and resolved!=chat:
                raise RuntimeError("Configured and resolved chat identities differ")
        if expected_chat is not None and resolved!=str(expected_chat):
            raise RuntimeError("Resolved recipient differs from last confirmed delivery")
    except Exception as exc:
        raise RuntimeError("Telegram read-only route verification failed: "+type(exc).__name__) from None
    print("DRUCKENMILLER_ROUTE_VERIFIED=true bot_and_chat=true")
    return base,username,chat,resolved


def telegram_send(message,route=None):
    if len(message)>3800:
        raise RuntimeError("Telegram message exceeds single-send guard")
    base,username,chat,resolved=route or telegram_preflight()
    from urllib.parse import urlencode
    payload=urlencode({"chat_id":chat,"text":message,"parse_mode":"HTML",
                       "link_preview_options":json.dumps({"is_disabled":True})}).encode()
    # One send attempt. A lost response may conceal a successful delivery;
    # persistent pending state blocks automatic retries.
    req=Request(base+"sendMessage",data=payload)
    try:
        with urlopen(req,timeout=28) as resp:
            result=json.load(resp)
    except Exception as exc:
        raise RuntimeError("Telegram delivery uncertain: "+type(exc).__name__+"; no auto resend") from None
    receipt=result.get("result") or {}
    mid=receipt.get("message_id")
    actual=(receipt.get("chat") or {}).get("id")
    if result.get("ok") is not True or type(mid) is not int or mid<=0 or type(actual) is not int:
        raise RuntimeError("Telegram send receipt incomplete; no auto resend")
    if str(actual)!=resolved:
        raise RuntimeError("Unexpected Telegram chat recipient; no auto resend")
    return {"bot":username,"message_id":mid,"chat_id":str(actual),
            "sent_at":iso_now().isoformat()}


def main():
    now=iso_now()
    state=load_state()
    probe=(os.getenv("DRUCKENMILLER_PROBE_ONLY") or "false").lower()=="true"
    source_items,health=discover(now)
    healthy=sum(1 for name in CORE_FEEDS if health.get(name,{}).get("ok"))
    print(f"DRUCKENMILLER_NEWS_SOURCE_HEALTH={healthy}/3 "
          f"matches={len(source_items)} detail={json.dumps(health,ensure_ascii=False)}")
    partial=[name for name,entry in health.items() if not entry.get("ok")]
    if partial:
        print("DRUCKENMILLER_SOURCE_COVERAGE_PARTIAL="+",".join(partial))

    # A single surviving RSS source cannot support reliable surveillance:
    # mark the run as FAILED, never report a false all-clear.
    if healthy<2:
        raise RuntimeError("Druckenmiller news source degradation: fewer than 2/3 independent discovery feeds healthy")
    boot=seed_ready(state,now)
    changes=news_candidates(state,source_items,now)
    if boot:
        message=seed_message()
        event=SEED_KEY
        recorded={SIGNAL_DIMENSION[key]:{"value":key,"event_date":SEED_DATE+"T00:00:00+00:00"}
                  for key in ("copper_short","equity_defensive","growth_2027","ai_applications")}
        # Also treat the specific 11/17 remarks as prior coverage; reused
        # summaries should not trigger multiple follow-up alerts.
        # All of these are part of the 2026-11-17 interview; do not send
        # follow-up fragments merely because another outlet covers one point.
        for key in ("copper_short","equity_defensive","growth_2027","ai_applications",
                    "fed_hawkish","credit_stress","dollar_long"):
            recorded[SIGNAL_DIMENSION[key]]={"value":key,"event_date":SEED_DATE+"T00:00:00+00:00"}
            changes=[item for item in changes if item[0]!=key]
    elif changes and healthy>=1:
        labels=";".join(key for key,_ in changes)
        earliest=min(item[1][0]["published"][:10] for item in changes)
        event="public-remarks:"+earliest+":"+hashlib.sha256(labels.encode()).hexdigest()[:16]
        if event in state["sent_events"]:
            print("DRUCKENMILLER_NO_NEW_SIGNALS duplicate_event_key")
            return 0
        message=news_message(changes)
        recorded={SIGNAL_DIMENSION.get(key,key):{"value":key,"event_date":proof[0]["published"],
                       "outlets":[x["publisher"] for x in proof[:3]]} for key,proof in changes}
    else:
        if any(name in CORE_FEEDS for name in partial):
            raise RuntimeError("Core source coverage incomplete; no verified signal, not a complete all-clear")
        if partial:
            print("DRUCKENMILLER_PARTIAL_SCAN_NO_CONFIRMED_SIGNAL")
        else:
            print("DRUCKENMILLER_NO_NEW_SIGNALS")
        return 0

    if probe:
        print(f"DRUCKENMILLER_PROBE_ONLY event={event} chars={len(message)} "
              f"independent_sources_seed={len(SEED_PUBLISHERS) if boot else 'dynamic'}")
        print("DRUCKENMILLER_PREVIEW_BEGIN\n"+message+"\nDRUCKENMILLER_PREVIEW_END")
        return 0

    # A read-only authentication or routing failure must not reserve an
    # event that has not reached sendMessage.
    route=telegram_preflight((state.get("last_success") or {}).get("chat_id"),check_live_chat=True)
    state["pending"]={"key":event,"reserved_at":now.isoformat(),
                      "verified_mode":"two_reported_publishers" if boot else "rss_two_independent_editorial_sources"}
    save_state(state)
    commit_state("Reserve Druckenmiller public remarks Telegram alert before send")
    print("DRUCKENMILLER_PRE_SEND_RESERVATION_COMMITTED")
    receipt=telegram_send(message,route)
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
        if (os.getenv("DRUCKENMILLER_PROBE_ONLY") or "false").lower()=="true":
            baseline=load_state()
            telegram_preflight((baseline.get("last_success") or {}).get("chat_id"),check_live_chat=True)
        raise SystemExit(main())
    except Exception as exc:
        print(f"DRUCKENMILLER_WATCH_ERROR={type(exc).__name__} {exc}",file=sys.stderr)
        raise
