#!/usr/bin/env python3
"""Korean-title wrapper for Trump portfolio claim Telegram alerts."""

import json
import re
import urllib.parse
import urllib.request

import trump_portfolio_claim_watch as watch


KNOWN_TITLE_KO = {
    "Nvidia, Tesla, Apple: Trump promoted companies after buying their stocks, says report":
        "엔비디아·테슬라·애플: 트럼프, 해당 종목 매수 후 기업들을 홍보했다는 보도",
    "Trump trades millions in Nvidia, Apple, Microsoft while promoting companies":
        "트럼프, 기업들을 홍보하는 동안 엔비디아·애플·마이크로소프트 주식을 수백만달러 규모로 거래",
    "Trump revamps portfolio, adding Nvidia and other AI names":
        "트럼프, 엔비디아 등 AI 관련주를 추가하며 포트폴리오 재편",
    "Trump's updated portfolio is basically a bet that America wins the AI race.":
        "트럼프의 업데이트된 포트폴리오는 미국이 AI 경쟁에서 승리할 것이라는 베팅에 가깝다",
}


def _needs_korean_translation(text: str) -> bool:
    text = text or ""
    has_hangul = bool(re.search(r"[가-힣]", text))
    has_latin = bool(re.search(r"[A-Za-z]", text))
    return has_latin and not has_hangul


def _google_translate_ko(text: str) -> str:
    """Best-effort public translation fallback; known important titles are pinned above."""
    q = urllib.parse.urlencode(
        {
            "client": "gtx",
            "sl": "auto",
            "tl": "ko",
            "dt": "t",
            "q": text,
        }
    )
    url = "https://translate.googleapis.com/translate_a/single?" + q
    req = urllib.request.Request(url, headers={"User-Agent": "KHS-Trump-Portfolio-Watch/1.0"})
    with urllib.request.urlopen(req, timeout=12) as r:
        data = json.load(r)
    parts = []
    for row in data[0] if data and data[0] else []:
        if isinstance(row, list) and row and row[0]:
            parts.append(str(row[0]))
    return "".join(parts).strip()


def translate_title_ko(title: str) -> str:
    title = (title or "").strip()
    if not title:
        return "트럼프 포트폴리오 관련 주장"
    if title in KNOWN_TITLE_KO:
        return KNOWN_TITLE_KO[title]
    if not _needs_korean_translation(title):
        return title
    try:
        translated = _google_translate_ko(title)
        if translated and re.search(r"[가-힣]", translated):
            return translated
    except Exception as e:
        print(f"WARN title translation failed: {e}")
    # Translation failure must be visible rather than silently passing English through.
    return "한국어 번역 실패 — 원제는 원문 링크에서 확인"


_original_build_generic_message = watch.build_generic_message


def build_generic_message_korean(c):
    c2 = dict(c)
    c2["title"] = translate_title_ko(c2.get("title") or "")
    return _original_build_generic_message(c2)


watch.build_generic_message = build_generic_message_korean


if __name__ == "__main__":
    watch.main()
