#!/usr/bin/env python3
import argparse
import html
import re
import urllib.parse
import xml.etree.ElementTree as ET

import war_peace_reconstruction_watch_bodycolor as core
import war_peace_reconstruction_watch_bodycolor_parallel as parallel

watch = core.watch
runner = core.runner
base = core.base

STRICT_RED = (
    "사실상 전면전", "전면전", "확전", "교전 격화", "공격 재개", "공습 재개", "미사일 공격", "드론 공격",
    "무인기 공격", "보복 공격", "보복 공습", "재보복", "폭격", "포격", "피격", "격침", "사망", "부상", "피란",
    "full-scale war", "all-out war", "escalation", "fighting intensified", "attack resumed", "attacks resumed",
    "airstrikes resumed", "missile attack", "drone attack", "retaliatory attack", "retaliatory strike", "killed", "wounded", "displaced",
)
STRICT_GREEN = (
    "휴전 합의", "휴전 재개", "휴전 연장", "정전 합의", "종전 협상", "종전 합의", "평화 협상", "평화협상",
    "협상 재개", "3자 협상", "3자 회담", "삼자 회담", "긴장 완화", "공격 자제", "공격 중단", "공습 중단",
    "상호 공격 자제", "재건", "복구", "재건기금", "ceasefire agreement", "ceasefire resumed", "peace talks",
    "restart peace talks", "resume peace talks", "trilateral talks", "de-escalation", "halt attacks", "stop attacks",
    "reconstruction", "rebuilding",
)
MARKET_WORDS = (
    "유가", "원유 가격", "시장 파급", "위험프리미엄", "oil prices", "crude prices", "market impact", "open interest",
)


def _headline_text(row):
    return " ".join([
        row.get("title_original", ""), row.get("title_ko", ""), row.get("description", ""),
    ]).lower()


def _headline_color(row):
    t = _headline_text(row)
    # 완화 문구는 '공격'이라는 단어를 포함해도 초록이다.
    if any(p in t for p in core.DEESCAPE):
        return "green"
    if any(p in t for p in STRICT_RED):
        return "red"
    if any(p in t for p in STRICT_GREEN):
        return "green"
    return ""


def _bing_candidates(row):
    title = (row.get("title_original") or row.get("title_ko") or "").strip()
    source = (row.get("source") or "").strip()
    if not title:
        return []
    ranked = []
    seen = set()
    for query in (f'"{title}" {source}'.strip(), title):
        try:
            url = "https://www.bing.com/news/search?format=rss&q=" + urllib.parse.quote(query)
            _, xml_text = core._request_text(url, timeout=7, max_bytes=550_000)
            if not xml_text:
                continue
            root = ET.fromstring(xml_text)
            for item in root.findall("./channel/item")[:16]:
                t = html.unescape((item.findtext("title") or "").strip())
                link = (item.findtext("link") or "").strip()
                direct = core._bing_target(link) or link
                if not direct.startswith(("http://", "https://")) or direct in seen:
                    continue
                seen.add(direct)
                score = core._similarity(title, t)
                if source and source.lower() in t.lower():
                    score += 0.12
                if score >= 0.28:
                    ranked.append((score, direct))
        except Exception:
            pass
    ranked.sort(reverse=True)
    return [u for _, u in ranked[:5]]


def _strict_enrich(row):
    if row.get("body_checked"):
        return
    row["body_checked"] = True
    candidates = []
    direct = core._resolve_original(row)
    if direct:
        candidates.append(direct)
    for u in _bing_candidates(row):
        if u not in candidates:
            candidates.append(u)

    for url in candidates[:5]:
        try:
            final_url, page = core._request_text(url, timeout=8)
            body = core._extract_body(page)
            if body:
                row["article_text"] = body
                row["resolved_url"] = final_url or url
                row["body_verified"] = True
                return
        except Exception:
            continue


def _strict_body_color(row):
    title_color = _headline_color(row)
    body = (row.get("article_text") or "").strip()

    # 원문 본문 확보 실패: 상위 래퍼의 signals/forced_tags는 절대 색상 판정에 사용하지 않는다.
    if not body:
        return title_color

    sample = body[:6500].lower()
    first = body[:2200].lower()
    red_sample = core._clean_for_red(sample)
    red_first = core._clean_for_red(first)

    hard_red = any(p in red_first for p in (
        "사실상 전면전", "전면전 양상", "확전", "교전을 격화", "공격 재개", "공습 재개", "보복 공격", "보복 공습",
        "재보복", "미사일로 공격", "미사일 공격", "드론 공격", "난타전", "full-scale war", "all-out war",
        "attack resumed", "attacks resumed", "retaliatory attack", "retaliatory strike", "missile attack",
    ))
    casualty = any(p in red_first for p in ("사망", "숨지고", "부상", "피란", "killed", "wounded", "displaced"))
    red_hits = sum(1 for p in core.BODY_RED_CRITICAL if p in red_sample)

    if hard_red or (casualty and red_hits >= 2) or red_hits >= 5:
        return "red"

    strong_green_first = any(p in first for p in (
        "휴전 합의", "휴전 재개", "종전 협상 재개", "평화 협상 재개", "평화협상 재개", "협상 재개 의사",
        "공격 중단", "공격 자제", "긴장 완화", "재건", "복구", "ceasefire agreement", "restart peace talks",
        "resume peace talks", "halt attacks", "de-escalation", "reconstruction",
    ))
    green_hits = sum(1 for p in core.BODY_GREEN_CRITICAL if p in sample)

    # 제목도 완화 방향이고 본문 첫부분이 이를 확인하거나, 본문 첫부분 자체가 명백한 완화 행동이면 초록.
    if strong_green_first and red_hits <= 1:
        return "green"
    if title_color == "green" and green_hits >= 1 and red_hits <= 1:
        return "green"

    # 시장 해설·가격 기사처럼 방향 행동이 없는 경우에는 본문에 전쟁 단어가 있어도 색상 없음.
    if any(w in _headline_text(row) for w in MARKET_WORDS):
        return ""

    # 본문은 확보했지만 현재 행동 방향이 불명확하면 무색. 누적 태그로 되돌리지 않는다.
    return title_color if title_color in ("red", "green") else ""


# 병렬 모듈이 참조하는 core 함수들을 엄격 버전으로 교체한다.
core._enrich_body = _strict_enrich
core._body_color = _strict_body_color
watch.build_alert = parallel.build_alert


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
