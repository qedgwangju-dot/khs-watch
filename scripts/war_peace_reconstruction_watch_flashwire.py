#!/usr/bin/env python3
import argparse
import hashlib

import war_peace_reconstruction_watch_breaking as base

watch = base.watch
runner = base.runner
clean = base.clean

# 외교 속보 와이어를 별도 고속축으로 감시한다.
# 특히 IFX/Interfax·TASS의 짧은 헤드라인에서 회담 일정과 공습 중단 명령이 먼저 나오는 경우를 놓치지 않는다.
FLASHWIRE_QUERIES = [
    'site:interfax.com/newsroom/top-stories (Putin OR Peskov) (Witkoff OR Kushner OR "US delegation" OR "U.S. delegation") (Kyiv OR Kiev) ("no strikes" OR "no air strikes" OR halt OR suspend OR pause OR "3 days" OR "three days") when:6h',
    'site:interfax.com/newsroom/top-stories (Putin OR Peskov) (Witkoff OR Kushner) (meet OR meeting OR talks OR Saturday) when:6h',
    'site:tass.com (Putin OR Peskov) (Witkoff OR Kushner OR "US envoys") (Saturday OR meeting OR talks OR "September 5") when:6h',
    'site:tass.com (Putin OR Peskov) (Kyiv OR Kiev) ("no strikes" OR "air strikes" OR halt OR suspend OR pause OR "3 days" OR "three days") when:6h',
    '("PUTIN ORDERS NO STRIKES ON KYIV" OR "PESKOV SAYS PUTIN ORDERS NO STRIKES") when:6h',
    '(IFX OR Interfax) Putin Peskov Kyiv ("3 days" OR "three days" OR "no strikes" OR "no air strikes") when:6h',
    '(Putin OR Peskov) (Witkoff OR Kushner) (Saturday OR meeting OR talks) Kyiv Moscow when:6h',
]

watch.QUERIES = FLASHWIRE_QUERIES + list(watch.QUERIES)
watch.TRUSTED = tuple(list(watch.TRUSTED) + ["Interfax", "IFX", "TASS"])
watch.PEACE = list(watch.PEACE) + [
    "no strikes", "no air strikes", "halt strikes", "suspend strikes", "pause strikes",
    "three days", "3 days", "72 hours", "공습 중단", "공습 금지", "3일간", "사흘간",
]

_prev_google_news = watch.google_news


def _flash_signals(row):
    text = " ".join([
        row.get("title_original", ""),
        row.get("description", ""),
        " ".join(row.get("signals_ko", [])),
    ]).lower()
    signals = []
    marks = []

    putin_peskov = any(k in text for k in ("putin", "peskov", "푸틴", "페스코프"))
    envoys = any(k in text for k in (
        "witkoff", "kushner", "us delegation", "u.s. delegation", "us envoys", "u.s. envoys",
        "미국 대표단", "미국 특사", "미 특사", "미국 협상단",
    ))
    kyiv = any(k in text for k in ("kyiv", "kiev", "키이우", "키예프"))
    no_strikes = any(k in text for k in (
        "no strikes", "no air strikes", "halt strikes", "suspend strikes", "pause strikes",
        "stop strikes", "strike suspension", "공습 중단", "공습 금지", "공격 중단",
    ))
    three_days = any(k in text for k in ("three days", "3 days", "72 hours", "3일", "사흘"))

    if putin_peskov and envoys and kyiv and no_strikes:
        if three_days:
            signals.append("푸틴, 미국 대표단 방문을 위해 키이우 공습을 3일간 중단하도록 명령했다는 보도")
            marks.extend(["키이우공습중단", "3일공습중단"])
        else:
            signals.append("푸틴, 미국 대표단 방문 기간 키이우 공습 중단을 지시했다는 보도")
            marks.append("키이우공습중단")

    if putin_peskov and envoys:
        meeting = any(k in text for k in ("meet", "meeting", "talks", "회담", "만날", "면담"))
        saturday = any(k in text for k in ("saturday", "토요일"))
        if meeting and saturday:
            signals.append("푸틴, 토요일 위트코프·쿠슈너 미국 특사단과 회담 예정")
            marks.append("푸틴미특사회담")

    return list(dict.fromkeys(signals)), sorted(set(marks))


def google_news_flashwire(query):
    rows, err = _prev_google_news(query)
    for row in rows:
        signals, marks = _flash_signals(row)
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


watch.google_news = google_news_flashwire

_prev_score = watch.score_item


def flash_score_item(x, now):
    score, tags = _prev_score(x, now)
    signals, marks = _flash_signals(x)
    if marks:
        score += 40 if "키이우공습중단" in marks else 32
        src = (x.get("source") or "").lower()
        if any(k in src for k in ("interfax", "ifx", "tass", "reuters")):
            score += 8
        tags = sorted(set(tags + ["종전·협상", "시간표", "행동확인"] + (["공습중단"] if "키이우공습중단" in marks else [])))
        x["flash_marks"] = marks
        if signals:
            x["signals_ko"] = list(dict.fromkeys(signals + list(x.get("signals_ko", []))))
            x["deep_signal"] = True
    return score, tags


watch.score_item = flash_score_item

_prev_item_id = watch.item_id


def flash_item_id(x):
    base_id = _prev_item_id(x)
    _, marks = _flash_signals(x)
    if not marks:
        return base_id
    key = base_id + "|flashwire|" + "|".join(marks)
    return hashlib.sha256(key.encode("utf-8")).hexdigest()[:20]


watch.item_id = flash_item_id


def _source_rank(x):
    src = (x.get("source") or "").lower()
    if "kremlin" in src:
        return 70
    if "reuters" in src:
        return 65
    if "interfax" in src or src == "ifx":
        return 62
    if "tass" in src:
        return 58
    if any(k in src for k in ("associated press", "ap news")):
        return 55
    if any(k in src for k in ("연합뉴스", "yonhap", "voice of america", "voa")):
        return 45
    return 20


def _flash_sort_key(x, now):
    _, marks = _flash_signals(x)
    age = watch.age_minutes(x, now)
    freshness = 10000 - (age if age is not None else 5000)
    action = 3 if "키이우공습중단" in marks else 2 if "푸틴미특사회담" in marks else 1
    return (action, _source_rank(x), freshness, len(marks))


def _inject_flash_judgment(text, displayed_items):
    all_marks = set()
    for x in displayed_items:
        _, marks = _flash_signals(x)
        all_marks.update(marks)
    if not all_marks:
        return text

    marker = "<b>투자 판정</b>\n"
    pos = text.find(marker)
    if pos == -1:
        return text
    insert_at = pos + len(marker)
    rows = []
    if "키이우공습중단" in all_marks:
        rows.append("- <b>행동:</b> 키이우 공습 중단 명령 → 실제 3일 이행 여부가 평화 발언보다 강한 확인 신호")
    if "푸틴미특사회담" in all_marks:
        rows.append("- <b>회담:</b> 푸틴-위트코프·쿠슈너 회담 → 공동발표·키이우 후속 방문 확인")
    return text[:insert_at] + "\n".join(rows) + "\n" + text[insert_at:]


def flash_build_alert(items, markets, now):
    chosen = []

    flash_items = [x for x in items if _flash_signals(x)[1]]
    flash_items.sort(key=lambda x: _flash_sort_key(x, now), reverse=True)
    for x in flash_items[:3]:
        if x not in chosen:
            chosen.append(x)

    us = base._pick_best(items, {"이번주말", "수일내", "잠정일정", "양국방문"})
    if us is not None and us not in chosen:
        chosen.append(us)
    putin = base._pick_best(items, {"푸틴외교경로"})
    if putin is not None and putin not in chosen:
        chosen.append(putin)

    for x in items:
        if x not in chosen:
            chosen.append(x)
        if len(chosen) >= 8:
            break

    chosen = chosen[:8]
    text = base._prev_build_alert(chosen, markets, now)
    core_items = [x for x in chosen if "시장파급" not in x.get("tags", [])][:6]
    market_items = [x for x in chosen if "시장파급" in x.get("tags", [])][:4]
    displayed = core_items + market_items
    text = base._inline_source_links(text, displayed)
    text = base._bold_relative_age(text)
    text = base._compact_investment_judgment(text)
    text = _inject_flash_judgment(text, displayed)
    return text.strip()[:4000] + "\n"


watch.build_alert = flash_build_alert


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
