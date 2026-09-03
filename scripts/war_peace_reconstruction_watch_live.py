#!/usr/bin/env python3
import argparse
import datetime as dt
import json
import urllib.parse
from email.utils import format_datetime

import war_peace_reconstruction_watch_clean as clean

watch = clean.watch
runner = clean.runner

# Google News 색인을 기다리지 않고 Reuters 섹션 자체를 5분마다 직접 확인한다.
# 검색 API가 차단될 때도 섹션 API → Google News 보강창 순서로 계속 동작한다.
DIRECT_REUTERS_SECTIONS = [
    "reuters-section:/world/europe",
    "reuters-section:/world/middle-east",
]

UKRAINE_FAST_QUERIES = [
    'site:reuters.com (Putin OR Zelenskiy OR Zelensky OR Ukraine OR Russia) ("peace deal" OR "peace agreement" OR "chance of peace" OR "constructive peace" OR "new dynamic") when:6h',
    'site:reuters.com (Zelenskiy OR Zelensky OR Ukraine) ("US delegation" OR "U.S. delegation" OR Witkoff OR Kushner) (Moscow OR Kyiv OR Kiev OR visit) when:12h',
    'site:reuters.com (Ukraine OR Russia OR Putin OR Zelenskiy OR Zelensky) peace when:24h',
    'site:reuters.com "Putin cites chance of peace deal" when:24h',
    'site:voakorea.com (푸틴 OR 젤렌스키 OR 우크라이나 OR 러시아) (평화협정 OR 평화협상 OR 미국협상단 OR 미국대표단) when:24h',
]

IRAN_BACKFILL_QUERIES = [
    'site:reuters.com (Iran OR Hormuz OR Trump) ("end the war" OR "peace deal" OR ceasefire OR negotiations OR advisers) when:12h',
    'site:wsj.com Iran Trump ("end the war" OR "declare the war over" OR advisers OR midterms) when:24h',
]

watch.QUERIES = DIRECT_REUTERS_SECTIONS + UKRAINE_FAST_QUERIES + IRAN_BACKFILL_QUERIES + list(watch.QUERIES)
watch.TRUSTED = tuple(list(watch.TRUSTED) + ["Voice of America", "VOA", "VOA Korea"])
watch.PEACE = list(watch.PEACE) + [
    "chance of peace", "new dynamic", "u.s. delegation", "us delegation",
    "u.s. envoys", "us envoys", "평화 협정 가능", "평화협정 가능",
    "미국 협상단", "미국 대표단",
]

_prev_google_news = watch.google_news


def _make_reuters_row(article):
    title = watch.clean(article.get("title") or article.get("web") or "")
    desc = watch.clean(article.get("description") or "")
    canonical = article.get("canonical_url") or ""
    if canonical.startswith("http"):
        link = canonical
    elif canonical:
        link = "https://www.reuters.com" + canonical
    else:
        return None

    display = article.get("published_time") or article.get("display_time") or ""
    pub = ""
    if display:
        try:
            d = dt.datetime.fromisoformat(display.replace("Z", "+00:00"))
            pub = format_datetime(d)
        except Exception:
            pub = ""

    row = {
        "title": title,
        "title_original": title,
        "link": link,
        "published": pub,
        "source": "Reuters",
        "description": desc,
    }

    text = (title + " " + desc).lower()
    signals = []
    if "putin" in text and any(k in text for k in ("peace deal", "peace agreement", "chance of peace")):
        signals.append("푸틴, 우크라이나 전쟁 종식을 위한 평화 협정 타결 가능성 언급")
    if any(k in text for k in ("delegation", "envoys")) and "moscow" in text and any(k in text for k in ("kyiv", "kiev")):
        signals.append("젤렌스키, 미국 협상단이 모스크바와 키이우를 방문할 예정이라고 밝혀")
    if signals:
        row["signals_ko"] = signals
        row["forced_tags"] = ["종전·협상", "시간표"]
        row["deep_signal"] = True
    return row


def _reuters_section(section):
    args = {
        "section_id": section,
        "size": 30,
        "website": "reuters",
        "fetch_type": "section",
    }
    url = (
        "https://www.reuters.com/pf/api/v3/content/fetch/articles-by-section-alias-or-id-v1?query="
        + urllib.parse.quote_plus(json.dumps(args, ensure_ascii=False, separators=(",", ":")))
    )
    try:
        data = json.loads(watch.req(url, 15).decode("utf-8"))
    except Exception as e:
        return [], f"Reuters section {section}: {type(e).__name__}"

    articles = []
    if isinstance(data.get("arcResult"), dict):
        articles = data["arcResult"].get("articles") or []
    if not articles and isinstance(data.get("result"), dict):
        articles = data["result"].get("articles") or []

    rows = []
    for article in articles[:30]:
        row = _make_reuters_row(article)
        if row:
            rows.append(row)
    return rows, None


def google_news_with_reuters_section(query):
    prefix = "reuters-section:"
    if query.startswith(prefix):
        return _reuters_section(query[len(prefix):])
    return _prev_google_news(query)


watch.google_news = google_news_with_reuters_section

_prev_score = watch.score_item


def priority_score_item(x, now):
    score, tags = _prev_score(x, now)
    text = (x.get("title_original", "") + " " + x.get("description", "")).lower()
    if any(k in text for k in ("ukraine", "russia", "putin", "zelenskiy", "zelensky", "우크라이나", "러시아", "푸틴", "젤렌스키")):
        if any(k in text for k in ("peace deal", "peace agreement", "chance of peace", "constructive peace", "u.s. delegation", "us delegation", "u.s. envoys", "us envoys", "평화협정", "평화 협정", "미국 협상단", "미국 대표단")):
            score += 8
            tags = sorted(set(tags + ["종전·협상", "시간표"]))
    return score, tags


watch.score_item = priority_score_item


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--finalize", action="store_true")
    ap.add_argument("--telegram-test", action="store_true")
    args = ap.parse_args()
    if args.finalize:
        watch.finalize()
        return
    if args.telegram_test:
        clean.write_clean_test()
    else:
        watch.run(test=False)
    runner.verify_alert(test_mode=False)


if __name__ == "__main__":
    main()
