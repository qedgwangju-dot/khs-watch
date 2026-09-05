#!/usr/bin/env python3
import argparse
import hashlib
import re

import war_peace_reconstruction_watch_precise as precise

watch = precise.watch
runner = precise.runner
clean = precise.clean

# 종전·평화협상에서 '수일 내', '이번 주말', '잠정 일정'처럼 시간표가 구체화되는 후속 보도를
# 기존 기사 제목 중복 때문에 놓치지 않도록 별도 고속 검색축을 둔다.
DIPLOMACY_TIMELINE_QUERIES = [
    'site:reuters.com (Zelenskiy OR Zelensky OR Ukraine) ("US negotiators" OR "U.S. negotiators" OR "US delegation" OR "U.S. delegation" OR Witkoff OR Kushner) ("coming days" OR weekend OR "preliminary dates" OR Moscow OR Kyiv OR visit) when:6h',
    'site:reuters.com (Putin OR Russia) ("diplomatic path" OR "peace deal" OR "peace agreement" OR "chance of peace" OR "constructive peace") Ukraine when:6h',
    'site:n.news.naver.com (푸틴 OR 젤렌스키 OR 우크라이나 OR 러시아) ("미국 특사" OR "미국 대표단" OR "미국 협상단") ("수일 내" OR 수일내 OR "이번 주말" OR 주말 OR 방문 OR "잠정 일정") when:6h',
    '(푸틴 OR 젤렌스키 OR 우크라이나 OR 러시아) ("미국 특사" OR "미국 대표단" OR "미국 협상단") ("수일 내" OR 수일내 OR "이번 주말" OR 주말 OR "양국 방문" OR "잠정 일정") when:6h',
    'site:kremlin.ru Putin Ukraine (peace OR negotiations OR diplomatic) when:1d',
    'site:president.gov.ua (Witkoff OR Kushner OR US delegation OR negotiators) (Moscow OR Kyiv OR visit OR peace) when:1d',
]

watch.QUERIES = DIPLOMACY_TIMELINE_QUERIES + list(watch.QUERIES)
watch.PEACE = list(watch.PEACE) + [
    "coming days", "this weekend", "weekend", "preliminary dates", "visit both countries",
    "diplomatic path remains open", "diplomatic path", "수일 내", "수일내", "이번 주말", "주말",
    "잠정 일정", "잠정 날짜", "양국 방문", "외교적 길", "외교적 경로", "미국 특사",
]

_prev_google_news = watch.google_news


def _timeline_signals(row):
    text = " ".join([
        row.get("title_original", ""),
        row.get("description", ""),
        " ".join(row.get("signals_ko", [])),
    ]).lower()
    signals = []
    marks = []

    us_team = any(k in text for k in (
        "us negotiators", "u.s. negotiators", "us delegation", "u.s. delegation",
        "us envoys", "u.s. envoys", "witkoff", "kushner",
        "미국 협상단", "미국 대표단", "미국 특사", "미 특사",
    ))
    ukraine_russia = any(k in text for k in (
        "ukraine", "russia", "moscow", "kyiv", "kiev", "zelenskiy", "zelensky", "putin",
        "우크라이나", "러시아", "모스크바", "키이우", "젤렌스키", "푸틴",
    ))

    if us_team and ukraine_russia:
        if any(k in text for k in ("this weekend", "weekend", "이번 주말", "주말")):
            signals.append("미국 대표단의 러시아·우크라이나 방문 시점이 이번 주말로 구체화")
            marks.append("이번주말")
        elif any(k in text for k in ("coming days", "수일 내", "수일내")):
            signals.append("미국 협상단이 수일 내 러시아와 우크라이나 양국을 방문할 예정")
            marks.append("수일내")
        if any(k in text for k in ("preliminary dates", "잠정 일정", "잠정 날짜")):
            signals.append("미국 협상단의 모스크바·키이우 방문 잠정 일정이 잡힘")
            marks.append("잠정일정")
        if any(k in text for k in ("both countries", "visit both", "양국 방문")):
            if not signals:
                signals.append("미국 협상단이 러시아와 우크라이나 양국을 방문할 예정")
            marks.append("양국방문")

    if "putin" in text or "푸틴" in text:
        if any(k in text for k in (
            "diplomatic path remains open", "diplomatic path", "negotiated end", "peace deal",
            "peace agreement", "chance of peace", "외교적 길", "외교적 경로", "평화 협정", "평화협정",
        )):
            signals.append("푸틴, 우크라이나 전쟁 종식을 위한 외교적 해결 경로가 여전히 열려 있다고 언급")
            marks.append("푸틴외교경로")

    return list(dict.fromkeys(signals)), sorted(set(marks))


def google_news_breaking(query):
    rows, err = _prev_google_news(query)
    for row in rows:
        signals, marks = _timeline_signals(row)
        if not marks:
            continue
        row["signals_ko"] = list(dict.fromkeys(signals + list(row.get("signals_ko", []))))
        row["timeline_marks"] = marks
        row["forced_tags"] = list(dict.fromkeys(list(row.get("forced_tags", [])) + ["종전·협상", "시간표", "일정구체화"]))
        row["deep_signal"] = True
    return rows, err


watch.google_news = google_news_breaking

_prev_score = watch.score_item


def breaking_score_item(x, now):
    score, tags = _prev_score(x, now)
    signals, marks = _timeline_signals(x)
    if marks:
        # 방문 날짜/수일 내/주말 같은 '실제 시간표'를 일반 평화 발언보다 우선한다.
        schedule_marks = {"이번주말", "수일내", "잠정일정", "양국방문"}
        score += 24 if schedule_marks.intersection(marks) else 12
        if (x.get("source") or "").lower() == "reuters":
            score += 6
        tags = sorted(set(tags + ["종전·협상", "시간표", "일정구체화"]))
        x["timeline_marks"] = marks
        if signals:
            x["signals_ko"] = list(dict.fromkeys(signals + list(x.get("signals_ko", []))))
            x["deep_signal"] = True
    return score, tags


watch.score_item = breaking_score_item

# 기존 상태는 기사 '제목' 단위로 중복 제거한다. 같은 기사라도
# '수일 내 → 이번 주말', '잠정 일정 확정'처럼 시간표가 구체화되면 투자 촉매가 달라지므로 재알림한다.
_prev_item_id = watch.item_id


def breaking_item_id(x):
    base = _prev_item_id(x)
    _, marks = _timeline_signals(x)
    if not marks:
        return base
    key = base + "|timeline|" + "|".join(marks)
    return hashlib.sha256(key.encode("utf-8")).hexdigest()[:20]


watch.item_id = breaking_item_id

# 같은 사건을 Reuters·VOA·네이버 재전송 등 여러 출처가 동시에 잡아도 텔레그램에는
# 가장 강한 원천 1건만 우선 표시한다. 다만 '미국 협상단 일정'과 '푸틴 외교 경로'는 서로 다른 신호로 남긴다.
_prev_build_alert = watch.build_alert


def _source_rank(x):
    src = (x.get("source") or "").lower()
    if "reuters" in src:
        return 50
    if any(k in src for k in ("kremlin", "president of ukraine", "white house")):
        return 45
    if any(k in src for k in ("연합뉴스", "yonhap", "voice of america", "voa")):
        return 35
    if any(k in src for k in ("naver", "네이버", "nate", "네이트")):
        return 25
    return 10


def _pick_best(rows, wanted_marks):
    candidates = []
    for x in rows:
        _, marks = _timeline_signals(x)
        if set(marks).intersection(wanted_marks):
            age = watch.age_minutes(x, watch.dt.datetime.now(watch.KST))
            freshness = 10000 - (age if age is not None else 5000)
            candidates.append((_source_rank(x), freshness, len(marks), x))
    if not candidates:
        return None
    candidates.sort(key=lambda z: (z[0], z[1], z[2]), reverse=True)
    return candidates[0][3]


def _inline_source_links(text, displayed_items):
    """하단 원문 목록을 없애고 각 핵심 변화의 출처를 바로 누를 수 있게 만든다."""
    marker = "\n<b>원문</b>\n"
    if marker in text:
        text = text.split(marker, 1)[0].rstrip() + "\n"

    for x in displayed_items:
        src = watch.h(x.get("source") or "출처미상")
        url = watch.h(x.get("link") or "")
        if not url:
            continue
        old = f" · {src}\n"
        new = f' · <a href="{url}">{src} 원문</a>\n'
        pos = text.find(old)
        if pos == -1:
            continue
        text = text[:pos] + new + text[pos + len(old):]
    return text.strip()[:4000] + "\n"


def _bold_relative_age(text):
    """기사 경과시간만 굵게 표시해 새 기사인지 오래된 후속인지 한눈에 보이게 한다."""
    def repl(match):
        start, end = match.span(1)
        before = text[max(0, start - 3):start]
        after = text[end:end + 4]
        if before == "<b>" and after == "</b>":
            return match.group(1)
        return f"<b>{match.group(1)}</b>"

    return re.sub(r"(\d{1,5}분 전)", repl, text)


def _compact_investment_judgment(text):
    """투자 판정은 핵심 경로만 2~5줄로 압축하고 의미가 겹치는 할인율·수급 문장을 합친다."""
    marker = "<b>투자 판정</b>\n"
    start = text.find(marker)
    if start == -1:
        return text
    body_start = start + len(marker)
    end_candidates = []
    for next_marker in ("\n<b>반대 신호</b>\n", "\n<b>다음 확인</b>\n"):
        pos = text.find(next_marker, body_start)
        if pos != -1:
            end_candidates.append(pos)
    end = min(end_candidates) if end_candidates else len(text)
    block = text[body_start:end]

    lines = []
    if "할인율:" in block or "수급:" in block:
        lines.append("- <b>시장:</b> 종전 진전 → 유가·위험프리미엄↓ / 달러·금리 안정 동반 시 위험선호↑")
    if "실물가격:" in block:
        lines.append("- <b>실물가격:</b> 밀·원유·금·해운의 실제 가격 반응이 이어지는지 확인")
    if "미국 협상단의 모스크바·키이우 방문" in block:
        lines.append("- <b>시간표:</b> 미 협상단 방문 → 정상회담 → 휴전 조건·안보보장")
    if "종전 선언 → 공식 휴전문" in block:
        lines.append("- <b>이란 시간표:</b> 종전 선언 → 공식 휴전 → 호르무즈·제재 변화 → 병력 철수")
    if "정치일정:" in block:
        lines.append("- <b>정치:</b> 중간선거 부담이 확전 억제로 이어지는지 확인")
    if "전략변화:" in block:
        lines.append("- <b>전략:</b> 군사 확전보다 제재·경제압박으로 무게가 이동하는지 확인")
    if "돈 버는 능력:" in block or "한국 기업:" in block:
        lines.append("- <b>재건:</b> 기금 → 입찰 → 본계약 → 수주 / 한국기업 실명 확인 전 후보")

    if not lines:
        return text
    compact = marker + "\n".join(lines)
    return text[:start] + compact + text[end:]


def breaking_build_alert(items, markets, now):
    us_marks = {"이번주말", "수일내", "잠정일정", "양국방문"}
    putin_marks = {"푸틴외교경로"}
    chosen = []
    us = _pick_best(items, us_marks)
    if us is not None:
        chosen.append(us)
    putin = _pick_best(items, putin_marks)
    if putin is not None and putin is not us:
        chosen.append(putin)

    for x in items:
        _, marks = _timeline_signals(x)
        if marks:
            continue
        chosen.append(x)

    chosen = chosen[:8]
    text = _prev_build_alert(chosen, markets, now)

    # clean 알림의 실제 표시 순서와 동일하게 핵심 변화 → 시장 파급 순서로 링크를 삽입한다.
    core_items = [x for x in chosen if "시장파급" not in x.get("tags", [])][:6]
    market_items = [x for x in chosen if "시장파급" in x.get("tags", [])][:4]
    text = _inline_source_links(text, core_items + market_items)
    text = _bold_relative_age(text)
    text = _compact_investment_judgment(text)
    return text.strip()[:4000] + "\n"


watch.build_alert = breaking_build_alert


def _write_inline_test():
    clean.write_clean_test()
    if not watch.ALERT.exists():
        return
    text = watch.ALERT.read_text(encoding="utf-8")
    marker = "\n<b>원문</b>\n"
    if marker in text:
        text = text.split(marker, 1)[0].rstrip() + "\n"
    text = _bold_relative_age(text)
    text = _compact_investment_judgment(text)
    watch.ALERT.write_text(text, encoding="utf-8")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--finalize", action="store_true")
    ap.add_argument("--telegram-test", action="store_true")
    args = ap.parse_args()
    if args.finalize:
        watch.finalize()
        return
    if args.telegram_test:
        _write_inline_test()
    else:
        watch.run(test=False)
    runner.verify_alert(test_mode=False)


if __name__ == "__main__":
    main()
