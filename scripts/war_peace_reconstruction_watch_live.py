#!/usr/bin/env python3
import argparse

import war_peace_reconstruction_watch_clean as clean

watch = clean.watch
runner = clean.runner

# Reuters의 우크라이나 평화 기사처럼 제목 표현이 기존 검색어와 다르거나
# Google News 색인이 늦어 1시간 창을 벗어나는 경우를 놓치지 않도록
# '속보 창 + 6/12/24시간 보강 창'을 함께 돈다. 상태파일 중복 제거로 재전송은 막는다.
UKRAINE_FAST_QUERIES = [
    'site:reuters.com (Putin OR Zelenskiy OR Zelensky OR Ukraine OR Russia) ("peace deal" OR "peace agreement" OR "chance of peace" OR "constructive peace" OR "new dynamic") when:6h',
    'site:reuters.com (Zelenskiy OR Zelensky OR Ukraine) ("US delegation" OR "U.S. delegation" OR Witkoff OR Kushner) (Moscow OR Kyiv OR Kiev OR visit) when:12h',
    'site:reuters.com (Ukraine OR Russia OR Putin OR Zelenskiy OR Zelensky) peace when:24h',
    'site:reuters.com "Putin cites chance of peace deal" when:24h',
    'site:voakorea.com (푸틴 OR 젤렌스키 OR 우크라이나 OR 러시아) (평화협정 OR 평화협상 OR 미국협상단 OR 미국협상단) when:24h',
]

# 이란도 같은 이유로 1시간 검색색인 지연에 대비해 12시간 보강창을 둔다.
IRAN_BACKFILL_QUERIES = [
    'site:reuters.com (Iran OR Hormuz OR Trump) ("end the war" OR "peace deal" OR ceasefire OR negotiations OR advisers) when:12h',
    'site:wsj.com Iran Trump ("end the war" OR "declare the war over" OR advisers OR midterms) when:24h',
]

# 가장 중요한 출처별 검색을 맨 앞에 둔다.
watch.QUERIES = UKRAINE_FAST_QUERIES + IRAN_BACKFILL_QUERIES + list(watch.QUERIES)
watch.TRUSTED = tuple(list(watch.TRUSTED) + ["Voice of America", "VOA", "VOA Korea"])
watch.PEACE = list(watch.PEACE) + [
    "chance of peace", "new dynamic", "u.s. delegation", "us delegation",
    "평화 협정 가능", "평화협정 가능", "미국 협상단", "미국 대표단",
]

# 우크라이나 평화협정/미국 협상단 기사는 시장 시간표를 바꾸는 핵심 신호라 우선순위를 높인다.
_prev_score = watch.score_item


def priority_score_item(x, now):
    score, tags = _prev_score(x, now)
    text = (x.get("title_original", "") + " " + x.get("description", "")).lower()
    if any(k in text for k in ("ukraine", "russia", "putin", "zelenskiy", "zelensky", "우크라이나", "러시아", "푸틴", "젤렌스키")):
        if any(k in text for k in ("peace deal", "peace agreement", "chance of peace", "constructive peace", "u.s. delegation", "us delegation", "평화협정", "평화 협정", "미국 협상단", "미국 대표단")):
            score += 8
            tags = sorted(set(tags + ["종전·협상", "시간표"] ))
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
