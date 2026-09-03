#!/usr/bin/env python3
import argparse

import war_peace_reconstruction_watch_clean as clean

watch = clean.watch
runner = clean.runner

# Reuters의 /pf/api는 GitHub hosted runner에서 차단될 수 있다.
# robots.txt가 공개하는 Reuters 공식 News Sitemap을 직접 5분마다 읽어 원문 색인 지연을 줄인다.
DIRECT_REUTERS_SITEMAPS = [
    "reuters-sitemap:0",
    "reuters-sitemap:100",
    "reuters-sitemap:200",
    "reuters-sitemap:300",
]

# Google News는 보강 경로다. 1시간 창만 쓰지 않고 6/12/24시간 창을 병행해 색인 지연도 회수한다.
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

watch.QUERIES = DIRECT_REUTERS_SITEMAPS + UKRAINE_FAST_QUERIES + IRAN_BACKFILL_QUERIES + list(watch.QUERIES)
watch.TRUSTED = tuple(list(watch.TRUSTED) + ["Voice of America", "VOA", "VOA Korea"])
watch.PEACE = list(watch.PEACE) + [
    "chance of peace", "new dynamic", "u.s. delegation", "us delegation",
    "u.s. envoys", "us envoys", "평화 협정 가능", "평화협정 가능",
    "미국 협상단", "미국 대표단",
]

_prev_google_news = watch.google_news


def _reuters_news_sitemap(offset):
    base = "https://www.reuters.com/arc/outboundfeeds/news-sitemap/?outputType=xml"
    if offset:
        base += f"&from={offset}"
    try:
        root = watch.ET.fromstring(watch.req(base, 20))
    except Exception as e:
        return [], f"Reuters news sitemap {offset}: {type(e).__name__}"

    ns = {"sm": "http://www.sitemaps.org/schemas/sitemap/0.9", "news": "http://www.google.com/schemas/sitemap-news/0.9"}
    rows = []
    for node in root.findall("sm:url", ns):
        loc = watch.clean(node.findtext("sm:loc", default="", namespaces=ns))
        title = watch.clean(node.findtext("news:news/news:title", default="", namespaces=ns))
        pub = watch.clean(node.findtext("news:news/news:publication_date", default="", namespaces=ns))
        if not loc or not title:
            continue
        row = {
            "title": title,
            "title_original": title,
            "link": loc,
            "published": pub,
            "source": "Reuters",
            "description": "",
        }
        text = title.lower()
        signals = []
        if "putin" in text and any(k in text for k in ("peace deal", "peace agreement", "chance of peace")):
            signals.append("푸틴, 우크라이나 전쟁 종식을 위한 평화 협정 타결 가능성 언급")
        if any(k in text for k in ("delegation", "envoys")) and "moscow" in text and any(k in text for k in ("kyiv", "kiev")):
            signals.append("젤렌스키, 미국 협상단이 모스크바와 키이우를 방문할 예정이라고 밝혀")
        if signals:
            row["signals_ko"] = signals
            row["forced_tags"] = ["종전·협상", "시간표"]
            row["deep_signal"] = True
        rows.append(row)
    return rows, None


def google_news_with_reuters_sitemap(query):
    prefix = "reuters-sitemap:"
    if query.startswith(prefix):
        return _reuters_news_sitemap(int(query[len(prefix):] or 0))
    return _prev_google_news(query)


watch.google_news = google_news_with_reuters_sitemap

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
