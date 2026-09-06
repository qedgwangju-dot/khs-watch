#!/usr/bin/env python3
import argparse
import hashlib
import re

import war_peace_reconstruction_watch_compact as prev

watch = prev.watch
runner = prev.runner
base = prev.base

# 회담 '개최 여부'뿐 아니라 실제 협상 내용·막힌 지점·다음 일정까지 잡는다.
NEGOTIATION_DETAIL_QUERIES = [
    'site:reuters.com Putin Witkoff Kushner ("three hours" OR "more than three hours" OR "highly useful" OR "no breakthrough" OR settlement OR "economic issues" OR "Russian-American projects" OR "root causes") Ukraine when:12h',
    'site:reuters.com Putin Ukraine ("four regions" OR NATO OR "position remains unchanged" OR "unshakeable") Witkoff Kushner when:24h',
    'site:reuters.com Witkoff Kushner Kyiv Zelenskiy Sunday ("next steps" OR substantive OR proposal) when:12h',
    'site:apnews.com Putin Witkoff Kushner Ukraine ("three hours" OR breakthrough OR economic OR Kyiv) when:12h',
    'site:axios.com Putin Witkoff Kushner (Gene Lange OR sanctions OR Ukraine OR peace) when:24h',
    '(푸틴 위트코프 쿠슈너) (3시간 OR 돌파구 OR 종전안 OR 경제협력 OR 제재 OR 나토 OR 4개지역 OR 키이우) when:12h',
]
watch.QUERIES = NEGOTIATION_DETAIL_QUERIES + list(watch.QUERIES)

_prev_google_news = watch.google_news
_prev_score = watch.score_item
_prev_item_id = watch.item_id
_prev_build_alert = watch.build_alert


def _detail_text(row):
    return " ".join([
        row.get("title_ko", ""),
        row.get("title_original", ""),
        row.get("description", ""),
        " ".join(row.get("signals_ko", [])),
    ]).lower()


def _deal_signals(row):
    text = _detail_text(row)
    signals = []
    marks = []

    meeting = any(k in text for k in ("putin", "푸틴")) and any(k in text for k in ("witkoff", "위트코프")) and any(k in text for k in ("kushner", "쿠슈너"))
    if not meeting:
        return signals, marks

    if any(k in text for k in ("more than three hours", "over three hours", "3 hours 10", "three hours", "3시간 10", "3시간 이상", "3시간")):
        signals.append("푸틴-위트코프·쿠슈너 회담이 3시간 이상 진행")
        marks.append("3시간회담")

    if any(k in text for k in (
        "outlined a number of ideas", "possible avenues for a settlement", "fresh concrete proposal",
        "ideas regarding", "settlement ideas", "peace proposal", "구체적인 아이디어", "종전 해법", "평화 제안",
    )):
        signals.append("미국 측이 종전 해법을 위한 구체적 아이디어를 제시")
        marks.append("종전아이디어")

    if any(k in text for k in (
        "economic issues", "mutually beneficial russian-american projects", "russian-american projects",
        "economic projects", "경제적 이슈", "경제 문제", "미-러 프로젝트", "미·러 프로젝트", "경제 프로젝트",
    )):
        signals.append("회담에서 경제 현안과 미·러 상호이익 프로젝트도 논의")
        marks.append("경제프로젝트")

    if any(k in text for k in (
        "no breakthrough", "no concrete breakthrough", "no indication of any breakthrough", "without announcements of any breakthroughs",
        "돌파구 없음", "돌파구는 없", "구체적 돌파구", "성과 발표 없음",
    )):
        signals.append("회담은 유용하다는 평가였지만 구체적 돌파구는 발표되지 않음")
        marks.append("돌파구없음")

    if any(k in text for k in ("root causes", "근본 원인", "근본원인")):
        signals.append("러시아는 분쟁의 '근본 원인' 해결 요구를 재확인")
        marks.append("근본원인")

    regions = any(k in text for k in ("four regions", "four contested regions", "4개 지역", "4개지역", "네 지역"))
    nato = any(k in text for k in ("abandon its plan to join nato", "abandon nato", "nato aspirations", "나토 가입 포기", "nato 가입 포기"))
    unchanged = any(k in text for k in ("position remains unchanged", "unshakeable", "입장 불변", "기존 입장", "요구 유지"))
    if (regions and nato) or (unchanged and (regions or nato)):
        signals.append("러시아의 4개 지역·우크라이나 NATO 가입 포기 요구는 유지")
        marks.append("핵심쟁점불변")

    if any(k in text for k in ("due to meet", "expected in kyiv", "meet zelenskiy", "meet zelensky", "kyiv on sunday", "키이우", "젤렌스키")) and any(k in text for k in ("sunday", "일요일", "kyiv", "키이우")):
        signals.append("미국 특사단은 모스크바 회담 뒤 키이우에서 젤렌스키와 후속 회담 예정")
        marks.append("키이우후속")

    if any(k in text for k in ("next steps", "coming weeks", "수 주 내", "수주 내")) and any(k in text for k in ("white house", "백악관", "substantive", "실질적")):
        signals.append("백악관은 회담을 실질적이라고 평가하며 다음 단계를 수 주 내 제시할 방침")
        marks.append("다음단계")

    if "gene lange" in text or "진 랑게" in text:
        signals.append("미 재무부 제재 담당자 Gene Lange 동행 — 제재가 후속 협상 카드가 되는지 확인 필요")
        marks.append("제재담당동행")

    # 시점 혼합 방지: 과거 별도 사건을 이번 회담 결과로 재분류하지 않는다.
    if "robert gilman" in text or "로버트 길먼" in text or "로버트 길만" in text:
        signals.append("Robert Gilman 석방은 8월의 별도 사건으로 이번 회담 성과와 분리")
        marks.append("길먼시점분리")
    if ("bessent" in text or "베센트" in text) and any(k in text for k in ("no economic relief", "경제적 구제", "경제 완화")):
        signals.append("베센트의 '종전 전 경제적 구제 없음' 발언은 8월 31일 별도 회담 맥락으로 분리")
        marks.append("베센트시점분리")

    return list(dict.fromkeys(signals)), sorted(set(marks))


def detail_google_news(query):
    rows, err = _prev_google_news(query)
    for row in rows:
        signals, marks = _deal_signals(row)
        if not marks:
            continue
        row["signals_ko"] = list(dict.fromkeys(signals + list(row.get("signals_ko", []))))
        row["deal_marks"] = marks
        row["forced_tags"] = list(dict.fromkeys(list(row.get("forced_tags", [])) + ["종전·협상", "협상내용"]))
        row["deep_signal"] = True
    return rows, err


watch.google_news = detail_google_news


def detail_score_item(x, now):
    score, tags = _prev_score(x, now)
    signals, marks = _deal_signals(x)
    if marks:
        strong = {"돌파구없음", "핵심쟁점불변", "종전아이디어", "키이우후속", "다음단계"}
        score += 22 + (12 if strong.intersection(marks) else 0)
        src = (x.get("source") or "").lower()
        if any(k in src for k in ("reuters", "associated press", "ap news", "axios", "kremlin", "tass")):
            score += 8
        tags = sorted(set(tags + ["종전·협상", "협상내용"]))
        x["deal_marks"] = marks
        if signals:
            x["signals_ko"] = list(dict.fromkeys(signals + list(x.get("signals_ko", []))))
            x["deep_signal"] = True
    return score, tags


watch.score_item = detail_score_item


def detail_item_id(x):
    base_id = _prev_item_id(x)
    _, marks = _deal_signals(x)
    if not marks:
        return base_id
    # 같은 기사라도 '회담 시작 → 종료 → 돌파구 없음 → 키이우 후속'처럼 내용 단계가 진전되면 다시 알림.
    key = base_id + "|dealcontent|" + "|".join(marks)
    return hashlib.sha256(key.encode("utf-8")).hexdigest()[:20]


watch.item_id = detail_item_id


def _highlight_relative_age(text):
    """Telegram 일반 메시지는 글자색 지정이 안 되므로 경과시간에만 빨간 표시를 붙여 강조한다."""
    text = re.sub(r"(?<!🟥 )(<b>\d{1,5}분 전</b>)", r"🟥 \1", text)
    text = re.sub(r"(?<!🟥 )(?<!<b>)(\d{1,5}분 전)(?!</b>)", r"🟥 <b>\1</b>", text)
    return text


def _inject_deal_summary(text, items):
    signals = []
    marks = set()
    for x in items:
        s, m = _deal_signals(x)
        signals.extend(s)
        marks.update(m)
    signals = list(dict.fromkeys(signals))
    if not marks:
        return text

    rows = []
    if "3시간회담" in marks or "종전아이디어" in marks:
        bits = []
        if "3시간회담" in marks:
            bits.append("3시간+ 회담")
        if "종전아이디어" in marks:
            bits.append("미측 종전 해법 제시")
        rows.append("- <b>회담:</b> " + " · ".join(bits))
    if "경제프로젝트" in marks:
        rows.append("- <b>논의:</b> 미·러 경제 현안·상호이익 프로젝트 포함")
    if "돌파구없음" in marks:
        rows.append("- <b>판정:</b> '유용한 회담' 평가와 별개로 구체적 돌파구 발표 없음")
    if "핵심쟁점불변" in marks or "근본원인" in marks:
        rows.append("- <b>쟁점:</b> 러시아 핵심 요구 유지 여부가 실제 종전의 최대 병목")
    if "키이우후속" in marks:
        rows.append("- <b>다음:</b> 키이우 이동 → 젤렌스키 후속 회담")
    if "다음단계" in marks:
        rows.append("- <b>미국:</b> 다음 단계 수 주 내 제시 여부 확인")
    if "제재담당동행" in marks:
        rows.append("- <b>제재:</b> 미 재무부 제재 담당 동행 → 제재 완화가 협상 카드가 되는지 추적")
    if "길먼시점분리" in marks:
        rows.append("- <b>시점주의:</b> Robert Gilman 석방은 8월 별도 사건 — 이번 회담 성과로 계산하지 않음")
    if "베센트시점분리" in marks:
        rows.append("- <b>시점주의:</b> 베센트 경제구제 발언은 8월 31일 별도 맥락")

    rows = rows[:5]
    if not rows:
        return text
    block = "<b>협상 내용</b>\n" + "\n".join(rows) + "\n"

    # 핵심 변화 바로 뒤, 시장/투자 섹션 앞에 넣는다.
    insert_positions = []
    for marker in ("\n<b>시장 파급</b>\n", "\n<b>시장 반응</b>\n", "\n<b>투자 판정</b>\n"):
        pos = text.find(marker)
        if pos != -1:
            insert_positions.append(pos)
    if insert_positions:
        pos = min(insert_positions)
        return text[:pos].rstrip() + "\n\n" + block + text[pos:].lstrip("\n")
    return text.rstrip() + "\n\n" + block


def redage_build_alert(items, markets, now):
    text = _prev_build_alert(items, markets, now)
    text = _inject_deal_summary(text, items)
    return _highlight_relative_age(text).strip()[:4000] + "\n"


watch.build_alert = redage_build_alert


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
