#!/usr/bin/env python3
import argparse
import datetime as dt
import json
import re
import urllib.parse
from email.utils import format_datetime

import war_peace_reconstruction_watch_apflash as prev

watch = prev.watch
runner = prev.runner
base = prev.base

# 유료 X/와이어 API 없이 공개 경로를 최대한 겹쳐 잡는다.
# Google News 외에 공식 원문 페이지, 공개 RSS, Bing News/Web RSS, GDELT를 병렬 보강한다.
DIRECT_KREMLIN_NEWS = "direct-kremlin-news"
DIRECT_KREMLIN_TRANSCRIPTS = "direct-kremlin-transcripts"
DIRECT_KREMLIN_TELEGRAM = "direct-kremlin-telegram"
DIRECT_INTERFAX_TOP = "direct-interfax-top"
DIRECT_TASS_HOME = "direct-tass-home"
DIRECT_BING_UA = "direct-bing-ukraine"
DIRECT_BING_IRAN = "direct-bing-iran"
DIRECT_BING_FIRSTSQUAWK_UA = "direct-bing-firstsquawk-ukraine"
DIRECT_BING_FIRSTSQUAWK_IRAN = "direct-bing-firstsquawk-iran"
DIRECT_GDELT_UA = "direct-gdelt-ukraine"
DIRECT_GDELT_IRAN = "direct-gdelt-iran"

MAX_CAPTURE_QUERIES = [
    DIRECT_KREMLIN_NEWS,
    DIRECT_KREMLIN_TRANSCRIPTS,
    DIRECT_KREMLIN_TELEGRAM,
    DIRECT_INTERFAX_TOP,
    DIRECT_TASS_HOME,
    DIRECT_BING_UA,
    DIRECT_BING_IRAN,
    DIRECT_BING_FIRSTSQUAWK_UA,
    DIRECT_BING_FIRSTSQUAWK_IRAN,
    DIRECT_GDELT_UA,
    DIRECT_GDELT_IRAN,
]
watch.QUERIES = MAX_CAPTURE_QUERIES + list(watch.QUERIES)
watch.TRUSTED = tuple(list(watch.TRUSTED) + [
    "Interfax", "IFX", "TASS", "President of Russia", "Kremlin Telegram",
])

_prev_google_news = watch.google_news
_prev_score = watch.score_item


def _row(title, link, source, published="", description=""):
    title = watch.clean(title)
    return {
        "title": title,
        "title_original": title,
        "link": watch.clean(link),
        "published": watch.clean(published),
        "source": source,
        "description": watch.clean(description),
    }


def _iso_to_rfc(value):
    value = watch.clean(value)
    if not value:
        return ""
    try:
        d = dt.datetime.fromisoformat(value.replace("Z", "+00:00"))
        if d.tzinfo is None:
            d = d.replace(tzinfo=dt.timezone.utc)
        return format_datetime(d)
    except Exception:
        return value


def _rss(url, source, limit=80, require_link_substr=None):
    try:
        root = watch.ET.fromstring(watch.req(url, 20))
    except Exception as e:
        return [], f"{source} RSS: {type(e).__name__}"
    rows = []
    for item in root.findall(".//item")[:limit]:
        title = watch.clean(item.findtext("title"))
        link = watch.clean(item.findtext("link"))
        pub = watch.clean(item.findtext("pubDate"))
        desc = watch.clean(item.findtext("description"))
        if not title or not link:
            continue
        if require_link_substr and require_link_substr.lower() not in link.lower():
            continue
        rows.append(_row(title, link, source, pub, desc))
    return rows, None


def _anchor_page(url, source, href_pattern, limit=60):
    try:
        raw = watch.req(url, 20).decode("utf-8", "ignore")
    except Exception as e:
        return [], f"{source}: {type(e).__name__}"
    rows = []
    seen = set()
    for href, body in re.findall(r'<a[^>]+href=["\']([^"\']+)["\'][^>]*>(.*?)</a>', raw, re.I | re.S):
        if not re.search(href_pattern, href, re.I):
            continue
        title = watch.clean(body)
        if len(title) < 18:
            continue
        link = urllib.parse.urljoin(url, href)
        key = (title.lower(), link)
        if key in seen:
            continue
        seen.add(key)
        rows.append(_row(title, link, source))
        if len(rows) >= limit:
            break
    return rows, None


def _kremlin_telegram():
    # 공개 웹 미리보기. 실패해도 다른 공식/보도 경로가 계속 작동한다.
    url = "https://t.me/s/news_kremlin"
    try:
        raw = watch.req(url, 20).decode("utf-8", "ignore")
    except Exception as e:
        return [], f"Kremlin Telegram: {type(e).__name__}"
    rows = []
    chunks = raw.split('tgme_widget_message_wrap')
    for chunk in chunks[1:60]:
        post = re.search(r'data-post=["\']news_kremlin/(\d+)["\']', chunk, re.I)
        text_m = re.search(r'<div class=["\'][^"\']*tgme_widget_message_text[^"\']*["\'][^>]*>(.*?)</div>', chunk, re.I | re.S)
        if not post or not text_m:
            continue
        title = watch.clean(text_m.group(1))
        if len(title) < 18:
            continue
        time_m = re.search(r'<time[^>]+datetime=["\']([^"\']+)["\']', chunk, re.I)
        pub = _iso_to_rfc(time_m.group(1)) if time_m else ""
        link = f"https://t.me/news_kremlin/{post.group(1)}"
        rows.append(_row(title, link, "Kremlin Telegram", pub))
    return rows[:50], None


def _bing_news(query):
    q = urllib.parse.quote_plus(query)
    url = f"https://www.bing.com/news/search?q={q}&qft=sortbydate%3d%221%22&format=RSS"
    return _rss(url, "Bing News", limit=40)


def _bing_web_firstsquawk(query):
    q = urllib.parse.quote_plus(f"site:x.com/FirstSquawk {query}")
    url = f"https://www.bing.com/search?q={q}&format=rss"
    rows, err = _rss(url, "FirstSquawk 검색", limit=30)
    if err:
        return rows, err
    out = []
    for r in rows:
        link = r.get("link", "").lower()
        text = (r.get("title_original", "") + " " + r.get("description", "")).lower()
        if "firstsquawk" in link or "firstsquawk" in text:
            out.append(r)
    return out, None


def _gdelt(query):
    params = {
        "query": query,
        "mode": "ArtList",
        "format": "json",
        "maxrecords": "100",
        "timespan": "15min",
        "sort": "DateDesc",
    }
    url = "https://api.gdeltproject.org/api/v2/doc/doc?" + urllib.parse.urlencode(params)
    try:
        data = json.loads(watch.req(url, 25).decode("utf-8", "ignore"))
    except Exception as e:
        return [], f"GDELT: {type(e).__name__}"
    rows = []
    for art in data.get("articles", [])[:100]:
        title = watch.clean(art.get("title", ""))
        link = watch.clean(art.get("url", ""))
        if not title or not link:
            continue
        source = watch.clean(art.get("domain", "")) or "GDELT"
        seen = watch.clean(art.get("seendate", ""))
        pub = ""
        if seen:
            try:
                d = dt.datetime.strptime(seen[:15], "%Y%m%dT%H%M%S").replace(tzinfo=dt.timezone.utc)
                pub = format_datetime(d)
            except Exception:
                pass
        rows.append(_row(title, link, source, pub))
    return rows, None


def maxcapture_google_news(query):
    if query == DIRECT_KREMLIN_NEWS:
        rows, err = _anchor_page(
            "https://en.kremlin.ru/events/president/news/page/1",
            "President of Russia",
            r"/events/president/news/\d+",
        )
    elif query == DIRECT_KREMLIN_TRANSCRIPTS:
        rows, err = _anchor_page(
            "https://en.kremlin.ru/events/president/transcripts/page/1",
            "President of Russia",
            r"/events/president/transcripts/\d+",
        )
    elif query == DIRECT_KREMLIN_TELEGRAM:
        rows, err = _kremlin_telegram()
    elif query == DIRECT_INTERFAX_TOP:
        rows, err = _anchor_page(
            "https://interfax.com/newsroom/top-stories/?tag=Rss",
            "Interfax",
            r"/newsroom/top-stories/",
        )
    elif query == DIRECT_TASS_HOME:
        rows, err = _anchor_page(
            "https://tass.com/",
            "TASS",
            r"^/(world|politics|defense|economy|society|emergencies)/\d+|^https://tass\.com/(world|politics|defense|economy|society|emergencies)/\d+",
        )
    elif query == DIRECT_BING_UA:
        rows, err = _bing_news('Putin Peskov Witkoff Kushner Ukraine Russia Kyiv peace ceasefire strikes')
    elif query == DIRECT_BING_IRAN:
        rows, err = _bing_news('Iran Hormuz Trump ceasefire peace strikes war negotiations')
    elif query == DIRECT_BING_FIRSTSQUAWK_UA:
        rows, err = _bing_web_firstsquawk('Putin Peskov Witkoff Kushner Kyiv Ukraine Russia')
    elif query == DIRECT_BING_FIRSTSQUAWK_IRAN:
        rows, err = _bing_web_firstsquawk('Iran Hormuz Trump ceasefire strikes war')
    elif query == DIRECT_GDELT_UA:
        rows, err = _gdelt('(Putin OR Peskov OR Zelensky OR Witkoff OR Kushner) (Ukraine OR Russia OR Kyiv OR Moscow)')
    elif query == DIRECT_GDELT_IRAN:
        rows, err = _gdelt('(Iran OR Hormuz OR Tehran) (Trump OR ceasefire OR peace OR strike OR war)')
    else:
        return _prev_google_news(query)

    # 직접 소스도 기존 심층 신호 판정 체인을 그대로 거치게 한다.
    for row in rows:
        signals, marks = prev._pause_signals(row)
        if marks:
            row["signals_ko"] = list(dict.fromkeys(signals + list(row.get("signals_ko", []))))
            row["confirmation_marks"] = marks
            row["forced_tags"] = list(dict.fromkeys(list(row.get("forced_tags", [])) + ["종전·협상", "시간표", "행동확인"]))
            row["deep_signal"] = True
    return rows, err


watch.google_news = maxcapture_google_news


def maxcapture_score_item(x, now):
    score, tags = _prev_score(x, now)
    src = (x.get("source") or "").lower()
    if any(k in src for k in ("president of russia", "kremlin telegram", "interfax", "tass")):
        score += 5
    elif "firstsquawk" in src:
        score += 3
    elif "bing news" in src or "gdelt" in src:
        score += 1
    return score, tags


watch.score_item = maxcapture_score_item


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--finalize", action="store_true")
    ap.add_argument("--telegram-test", action="store_true")
    args = ap.parse_args()
    if args.finalize:
        watch.finalize()
        return
    if args.telegram_test:
        base._write_inline_test()
    else:
        watch.run(test=False)
    runner.verify_alert(test_mode=False)


if __name__ == "__main__":
    main()
