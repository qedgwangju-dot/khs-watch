#!/usr/bin/env python3
import argparse
import hashlib
import re

import war_peace_reconstruction_watch_redage as prev

watch = prev.watch
runner = prev.runner
base = prev.base

# 우크라이나의 모스크바 공격 중단 ↔ 러시아의 키이우 공격 중단처럼
# 협상 기간 '쌍방 수도 공습 중단' 제안을 별도 행동 신호로 잡는다.
RECIPROCAL_QUERIES = [
    'site:president.gov.ua Zelensky Moscow Kyiv ("no air strikes" OR ceasefire OR refrain OR strikes) (Witkoff OR Kushner OR envoys) when:24h',
    'site:reuters.com Zelenskiy Moscow Kyiv (refrain OR ceasefire OR "air strikes" OR reciprocate OR reciprocal) when:24h',
    'site:apnews.com Zelensky Moscow Kyiv (pause OR ceasefire OR strikes) (envoys OR negotiations) when:24h',
    '(젤렌스키 OR Zelensky OR Zelenskiy) (모스크바 OR Moscow) (키이우 OR Kyiv) (공습 중단 OR 공격 중단 OR 휴전 OR refrain OR ceasefire OR reciprocate) when:24h',
]
watch.QUERIES = RECIPROCAL_QUERIES + list(watch.QUERIES)

_prev_google_news = watch.google_news
_prev_score = watch.score_item
_prev_item_id = watch.item_id
_prev_build_alert = watch.build_alert


def _text(row):
    return " ".join([
        row.get("title_ko", ""),
        row.get("title_original", ""),
        row.get("description", ""),
        " ".join(row.get("signals_ko", [])),
    ]).lower()


def _reciprocal_signals(row):
    text = _text(row)
    signals = []
    marks = []

    zelensky = any(k in text for k in ("zelensky", "zelenskiy", "젤렌스키"))
    moscow = any(k in text for k in ("moscow", "모스크바"))
    kyiv = any(k in text for k in ("kyiv", "kiev", "키이우", "키예프"))
    stop = any(k in text for k in (
        "refrain from strikes", "refrain from airstrikes", "halt strikes", "stop strikes",
        "no air strikes", "ceasefire", "pause strikes", "공습 중단", "공격 중단", "공습을 중단",
    ))
    reciprocal = any(k in text for k in (
        "expect the russians to do the same", "russia must do the same", "reciprocate", "reciprocal",
        "러시아도 같은", "러시아가 같은", "맞교환", "상호", "쌍방",
    ))

    if zelensky and moscow and stop:
        signals.append("젤렌스키, 협상 기간 우크라이나의 모스크바 공습 중단 의사 표명")
        marks.append("모스크바공습중단")

    if zelensky and moscow and kyiv and stop and reciprocal:
        signals.append("우크라이나의 모스크바 공습 중단 ↔ 러시아의 키이우 공습 중단을 상호 조건으로 제안")
        marks.extend(["수도상호공습중단", "행동완화"])

    # 공식 우크라이나 대통령실 표현처럼 '우리 측 공습 없음 + 러시아도 같은 조치'도 상호중단으로 판정
    if zelensky and moscow and kyiv and any(k in text for k in ("there will be no air strikes from our side", "russia must do the same")):
        signals.append("젤렌스키, 미국 특사 방문 기간 모스크바·키이우 상호 공습 중단 요구")
        marks.extend(["수도상호공습중단", "행동완화"])

    return list(dict.fromkeys(signals)), sorted(set(marks))


def reciprocal_google_news(query):
    rows, err = _prev_google_news(query)
    for row in rows:
        signals, marks = _reciprocal_signals(row)
        if not marks:
            continue
        row["signals_ko"] = list(dict.fromkeys(signals + list(row.get("signals_ko", []))))
        row["reciprocal_marks"] = marks
        row["forced_tags"] = list(dict.fromkeys(list(row.get("forced_tags", [])) + ["종전·협상", "행동완화", "공습중단"]))
        row["deep_signal"] = True
    return rows, err


watch.google_news = reciprocal_google_news


def reciprocal_score_item(x, now):
    score, tags = _prev_score(x, now)
    signals, marks = _reciprocal_signals(x)
    if marks:
        score += 42 if "수도상호공습중단" in marks else 30
        src = (x.get("source") or "").lower()
        if any(k in src for k in ("president of ukraine", "reuters", "associated press", "ap news")):
            score += 10
        tags = sorted(set(tags + ["종전·협상", "행동완화", "공습중단"]))
        x["reciprocal_marks"] = marks
        if signals:
            x["signals_ko"] = list(dict.fromkeys(signals + list(x.get("signals_ko", []))))
            x["deep_signal"] = True
    return score, tags


watch.score_item = reciprocal_score_item


def reciprocal_item_id(x):
    base_id = _prev_item_id(x)
    _, marks = _reciprocal_signals(x)
    if not marks:
        return base_id
    key = base_id + "|reciprocal|" + "|".join(marks)
    return hashlib.sha256(key.encode("utf-8")).hexdigest()[:20]


watch.item_id = reciprocal_item_id


def _inject_reciprocal(text, items):
    marks = set()
    for x in items:
        _, m = _reciprocal_signals(x)
        marks.update(m)
    if not marks:
        return text

    rows = []
    if "수도상호공습중단" in marks:
        rows.append("- <b>행동:</b> 우크라이나 모스크바 공습 중단 ↔ 러시아 키이우 공습 중단 상호 제안")
        rows.append("- <b>판정:</b> 단순 평화 발언보다 강한 완화 신호 — 실제 양측 수도 공격 중단 이행 확인")
    elif "모스크바공습중단" in marks:
        rows.append("- <b>행동:</b> 우크라이나, 협상 기간 모스크바 공습 중단 의사")

    marker = "<b>투자 판정</b>\n"
    pos = text.find(marker)
    if pos != -1:
        insert = pos + len(marker)
        return text[:insert] + "\n".join(rows) + "\n" + text[insert:]
    return text


def reciprocal_build_alert(items, markets, now):
    text = _prev_build_alert(items, markets, now)
    return _inject_reciprocal(text, items).strip()[:4000] + "\n"


watch.build_alert = reciprocal_build_alert


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
