#!/usr/bin/env python3
import argparse
import hashlib

import war_peace_reconstruction_watch_interfax as direct

watch = direct.watch
runner = direct.runner
base = direct.base
flash = direct.flash

# IFX 단문 헤드라인이 공개 검색에 늦게 잡힐 때 AP·Reuters·FT의 확인 보도를 즉시 회수한다.
CONFIRMATION_QUERIES = [
    'site:apnews.com Putin ("72-hour pause" OR "pause in strikes" OR "strikes on Kyiv") (Witkoff OR Kushner OR Peskov) when:6h',
    'site:reuters.com Putin (Kyiv OR Kiev) ("pause in strikes" OR "suspend strikes" OR "no strikes" OR "72-hour") (Witkoff OR Kushner OR Peskov) when:6h',
    'site:ft.com Putin Kyiv ("suspension of strikes" OR "pause in strikes" OR "no strikes") (Witkoff OR Kushner) when:6h',
    '(Putin OR Peskov) ("72-hour pause" OR "pause in strikes" OR "suspension of strikes") Kyiv when:6h',
    '(Putin OR Peskov) (Witkoff OR Kushner) (Saturday OR Saturday meeting) when:6h',
]
watch.QUERIES = CONFIRMATION_QUERIES + list(watch.QUERIES)

_prev_google_news = watch.google_news


def _pause_signals(row):
    text = " ".join([
        row.get("title_original", ""),
        row.get("description", ""),
        " ".join(row.get("signals_ko", [])),
    ]).lower()
    signals = []
    marks = []
    putin_peskov = any(k in text for k in ("putin", "peskov", "푸틴", "페스코프"))
    kyiv = any(k in text for k in ("kyiv", "kiev", "키이우", "키예프"))
    pause = any(k in text for k in (
        "72-hour pause", "72 hour pause", "pause in strikes", "suspension of strikes",
        "suspend strikes", "no strikes", "no air strikes", "공습 중단", "공습 금지", "공격 중단",
    ))
    if putin_peskov and kyiv and pause:
        signals.append("푸틴, 미국 특사단 방문을 위해 키이우에 대한 공습을 72시간 중단하도록 명령")
        marks.extend(["키이우72시간공습중단", "행동확인"])

    envoys = any(k in text for k in ("witkoff", "kushner", "위트코프", "쿠슈너"))
    saturday = any(k in text for k in ("saturday", "토요일"))
    meeting = any(k in text for k in ("meet", "meeting", "talks", "회담", "면담"))
    if putin_peskov and envoys and saturday and meeting:
        signals.append("푸틴, 토요일 위트코프·쿠슈너 미국 특사단과 회담 예정")
        marks.append("푸틴토요일특사회담")
    return list(dict.fromkeys(signals)), sorted(set(marks))


def google_news_with_confirmations(query):
    rows, err = _prev_google_news(query)
    for row in rows:
        signals, marks = _pause_signals(row)
        if not marks:
            continue
        row["signals_ko"] = list(dict.fromkeys(signals + list(row.get("signals_ko", []))))
        row["confirmation_marks"] = marks
        forced = list(row.get("forced_tags", [])) + ["종전·협상", "시간표", "행동확인"]
        if "키이우72시간공습중단" in marks:
            forced.append("공습중단")
        row["forced_tags"] = list(dict.fromkeys(forced))
        row["deep_signal"] = True
    return rows, err


watch.google_news = google_news_with_confirmations

_prev_score = watch.score_item


def confirmation_score_item(x, now):
    score, tags = _prev_score(x, now)
    signals, marks = _pause_signals(x)
    if marks:
        score += 55 if "키이우72시간공습중단" in marks else 38
        src = (x.get("source") or "").lower()
        if any(k in src for k in ("associated press", "ap news", "reuters", "financial times")):
            score += 10
        tags = sorted(set(tags + ["종전·협상", "시간표", "행동확인"] + (["공습중단"] if "키이우72시간공습중단" in marks else [])))
        if signals:
            x["signals_ko"] = list(dict.fromkeys(signals + list(x.get("signals_ko", []))))
            x["deep_signal"] = True
    return score, tags


watch.score_item = confirmation_score_item

_prev_item_id = watch.item_id


def confirmation_item_id(x):
    base_id = _prev_item_id(x)
    _, marks = _pause_signals(x)
    if not marks:
        return base_id
    key = base_id + "|confirmation|" + "|".join(marks)
    return hashlib.sha256(key.encode("utf-8")).hexdigest()[:20]


watch.item_id = confirmation_item_id

_prev_build_alert = watch.build_alert


def confirmation_build_alert(items, markets, now):
    confirm = [x for x in items if _pause_signals(x)[1]]
    confirm.sort(
        key=lambda x: (
            2 if "키이우72시간공습중단" in _pause_signals(x)[1] else 1,
            10000 - (watch.age_minutes(x, now) if watch.age_minutes(x, now) is not None else 5000),
        ),
        reverse=True,
    )
    ordered = []
    for x in confirm + list(items):
        if x not in ordered:
            ordered.append(x)
        if len(ordered) >= 8:
            break
    return _prev_build_alert(ordered, markets, now)


watch.build_alert = confirmation_build_alert


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
