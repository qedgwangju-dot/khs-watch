#!/usr/bin/env python3
import argparse
import hashlib

import war_peace_reconstruction_watch_reciprocal as prev

watch = prev.watch
runner = prev.runner
base = prev.base

# 키이우 종전협상에 영국·프랑스·독일 국가안보보좌관이 참여하는 등
# 유럽 핵심 동맹국이 협상 테이블에 직접 들어오는 변화를 별도 신호로 잡는다.
ALLIES_QUERIES = [
    'site:reuters.com Witkoff Kushner Zelenskiy Kyiv (British OR French OR German) ("national security advisers" OR "final hour" OR joined) when:24h',
    'site:yna.co.kr (윗코프 OR 위트코프) 쿠슈너 젤렌스키 (영국 OR 프랑스 OR 독일 OR 영·프·독) (국가안보보좌관 OR 추가 회의 OR 종전) when:24h',
    '(윗코프 OR 위트코프 OR Witkoff) 쿠슈너 젤렌스키 키이우 (영국 OR 프랑스 OR 독일 OR 영·프·독) (국가안보보좌관 OR 종전협상 OR 추가회의) when:24h',
]
watch.QUERIES = ALLIES_QUERIES + list(watch.QUERIES)

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


def _allies_signals(row):
    text = _text(row)
    signals = []
    marks = []

    kyiv_talks = any(k in text for k in ("kyiv", "kiev", "키이우", "키예프")) and any(k in text for k in (
        "witkoff", "윗코프", "위트코프", "kushner", "쿠슈너", "zelensky", "zelenskiy", "젤렌스키"
    ))
    uk = any(k in text for k in ("british", "britain", "united kingdom", "영국"))
    fr = any(k in text for k in ("french", "france", "프랑스"))
    de = any(k in text for k in ("german", "germany", "독일"))
    advisers = any(k in text for k in ("national security adviser", "national security advisers", "국가안보보좌관", "안보보좌관"))

    if kyiv_talks and uk and fr and de:
        signals.append("키이우 종전협상에 영국·프랑스·독일 측도 참여")
        marks.append("영프독참여")
        if advisers:
            signals.append("영국·프랑스·독일 국가안보보좌관이 추가 회의에 참여")
            marks.append("유럽안보보좌관")

    if kyiv_talks and any(k in text for k in ("final hour", "마지막 1시간", "마지막 한 시간", "최종 1시간")):
        signals.append("영·프·독 안보보좌관이 미·우 회담 마지막 1시간에 합류")
        marks.append("최종1시간합류")

    if kyiv_talks and any(k in text for k in ("security guarantees", "security and economic guarantees", "안전보장", "안보보장")):
        signals.append("키이우 회담에서 우크라이나 안전보장 문제가 논의")
        marks.append("안전보장논의")
    if kyiv_talks and any(k in text for k in ("prosperity plan", "post-war prosperity", "전후 번영 계획", "전후 번영", "경제 보장")):
        signals.append("전후 경제·번영 계획이 종전 패키지의 일부로 논의")
        marks.append("전후경제패키지")

    return list(dict.fromkeys(signals)), sorted(set(marks))


def allies_google_news(query):
    rows, err = _prev_google_news(query)
    for row in rows:
        signals, marks = _allies_signals(row)
        if not marks:
            continue
        row["signals_ko"] = list(dict.fromkeys(signals + list(row.get("signals_ko", []))))
        row["allies_marks"] = marks
        row["forced_tags"] = list(dict.fromkeys(list(row.get("forced_tags", [])) + ["종전·협상", "유럽참여"]))
        row["deep_signal"] = True
    return rows, err


watch.google_news = allies_google_news


def allies_score_item(x, now):
    score, tags = _prev_score(x, now)
    signals, marks = _allies_signals(x)
    if marks:
        score += 30 if "영프독참여" in marks else 18
        src = (x.get("source") or "").lower()
        if any(k in src for k in ("reuters", "연합뉴스", "yonhap")):
            score += 8
        tags = sorted(set(tags + ["종전·협상", "유럽참여"]))
        x["allies_marks"] = marks
        if signals:
            x["signals_ko"] = list(dict.fromkeys(signals + list(x.get("signals_ko", []))))
            x["deep_signal"] = True
    return score, tags


watch.score_item = allies_score_item


def allies_item_id(x):
    base_id = _prev_item_id(x)
    _, marks = _allies_signals(x)
    if not marks:
        return base_id
    key = base_id + "|allies|" + "|".join(marks)
    return hashlib.sha256(key.encode("utf-8")).hexdigest()[:20]


watch.item_id = allies_item_id


def _inject_allies(text, items):
    marks = set()
    for x in items:
        _, m = _allies_signals(x)
        marks.update(m)
    if not marks:
        return text

    rows = []
    if "영프독참여" in marks:
        rows.append("- <b>유럽:</b> 영국·프랑스·독일도 키이우 종전협상에 직접 참여")
    if "최종1시간합류" in marks:
        rows.append("- <b>구조:</b> 영·프·독 안보보좌관이 미·우 회담 마지막 1시간 합류")
    if "안전보장논의" in marks or "전후경제패키지" in marks:
        rows.append("- <b>의제:</b> 안전보장·전후 경제 패키지가 실제 합의 문안으로 이어지는지 확인")

    marker = "<b>투자 판정</b>\n"
    pos = text.find(marker)
    if pos != -1:
        insert = pos + len(marker)
        return text[:insert] + "\n".join(rows[:3]) + "\n" + text[insert:]
    return text


def allies_build_alert(items, markets, now):
    text = _prev_build_alert(items, markets, now)
    return _inject_allies(text, items).strip()[:4000] + "\n"


watch.build_alert = allies_build_alert


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
