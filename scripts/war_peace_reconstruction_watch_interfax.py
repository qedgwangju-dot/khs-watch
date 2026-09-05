#!/usr/bin/env python3
import argparse
import html
import re
from html.parser import HTMLParser

import war_peace_reconstruction_watch_flashwire as flash

watch = flash.watch
runner = flash.runner
base = flash.base

# Interfax/IFX 속보는 재전송 기사나 Google News 색인보다 먼저 뜰 수 있으므로
# 공식 Interfax Top Stories 페이지를 매 실행마다 직접 읽는다.
DIRECT_INTERFAX_QUERY = "interfax-direct-top-stories"
watch.QUERIES = [DIRECT_INTERFAX_QUERY] + list(watch.QUERIES)


class _InterfaxParser(HTMLParser):
    def __init__(self):
        super().__init__()
        self.in_h3 = False
        self.h3_buf = []
        self.pending_title = None
        self.rows = []

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if tag.lower() == "h3":
            self.in_h3 = True
            self.h3_buf = []
        if tag.lower() == "a" and self.pending_title:
            href = attrs.get("href", "")
            if "/newsroom/top-stories/" in href:
                if href.startswith("/"):
                    href = "https://interfax.com" + href
                self.rows.append((self.pending_title, href))
                self.pending_title = None

    def handle_endtag(self, tag):
        if tag.lower() == "h3" and self.in_h3:
            title = re.sub(r"\s+", " ", html.unescape("".join(self.h3_buf))).strip()
            if title:
                self.pending_title = title
            self.in_h3 = False
            self.h3_buf = []

    def handle_data(self, data):
        if self.in_h3:
            self.h3_buf.append(data)


def _direct_interfax():
    url = "https://interfax.com/newsroom/top-stories/"
    try:
        raw = watch.req(url, 20).decode("utf-8", errors="replace")
    except Exception as e:
        return [], f"Interfax direct: {type(e).__name__}"
    p = _InterfaxParser()
    try:
        p.feed(raw)
    except Exception as e:
        return [], f"Interfax parse: {type(e).__name__}"

    rows = []
    for title, link in p.rows[:40]:
        low = title.lower()
        # 전쟁·협상·대표단·공습 중단 관련 제목만 통과시켜 잡음을 최소화한다.
        if not any(k in low for k in (
            "putin", "peskov", "ukraine", "kyiv", "kiev", "witkoff", "kushner",
            "ceasefire", "peace", "strike", "attack", "delegation", "envoy",
        )):
            continue
        rows.append({
            "title": title,
            "title_original": title,
            "link": link,
            "published": "",
            "source": "Interfax",
            "description": "",
        })
    return rows, None


_prev_google_news = watch.google_news


def google_news_with_direct_interfax(query):
    if query == DIRECT_INTERFAX_QUERY:
        rows, err = _direct_interfax()
    else:
        rows, err = _prev_google_news(query)

    # 직접 Interfax에서도 flashwire 신호를 동일하게 적용한다.
    for row in rows:
        signals, marks = flash._flash_signals(row)
        if not marks:
            continue
        row["signals_ko"] = list(dict.fromkeys(signals + list(row.get("signals_ko", []))))
        row["flash_marks"] = marks
        forced = list(row.get("forced_tags", [])) + ["종전·협상", "시간표", "행동확인"]
        if "키이우공습중단" in marks:
            forced.append("공습중단")
        row["forced_tags"] = list(dict.fromkeys(forced))
        row["deep_signal"] = True
    return rows, err


watch.google_news = google_news_with_direct_interfax


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
