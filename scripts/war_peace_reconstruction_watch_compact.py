#!/usr/bin/env python3
import argparse
import re

import war_peace_reconstruction_watch_maxcapture as prev

watch = prev.watch
runner = prev.runner
base = prev.base

_prev_build_alert = watch.build_alert


def _row_text(x):
    return " ".join([
        x.get("title_ko", ""),
        x.get("title_original", ""),
        x.get("description", ""),
        " ".join(x.get("signals_ko", [])),
        " ".join(x.get("tags", [])),
    ]).lower()


def _source_rank(x):
    src = (x.get("source") or "").lower()
    link = (x.get("link") or "").lower()
    text = src + " " + link
    if any(k in text for k in ("whitehouse.gov", "kremlin.ru", "president.gov.ua", "president of russia", "kremlin telegram")):
        return 100
    if "reuters" in text:
        return 95
    if any(k in text for k in ("apnews.com", "ap news", "associated press")):
        return 92
    if "interfax" in text or "ifx" in src:
        return 90
    if "tass" in text:
        return 88
    if any(k in text for k in ("ft.com", "financial times", "washingtonpost.com", "wsj.com", "wall street journal")):
        return 82
    if any(k in text for k in ("yna.co.kr", "연합뉴스", "voakorea", "voice of america", "voa")):
        return 72
    if "bing news" in src:
        return 35
    return 50


def _event_key(x):
    text = _row_text(x)
    if any(k in text for k in (
        "키이우72시간공습중단", "키이우공습중단", "72시간 중단", "3일간 중단", "3일 중단",
        "72-hour pause", "no strikes on kyiv", "no strikes on kiev",
    )):
        return "ukraine:kyiv-pause"
    if ("푸틴" in text or "putin" in text) and any(k in text for k in ("위트코프", "witkoff")) and any(k in text for k in ("쿠슈너", "kushner")) and any(k in text for k in ("회담", "meeting", "talks", "토요일", "saturday")):
        return "ukraine:putin-us-envoy-meeting"
    if any(k in text for k in ("이번 주말", "weekend")) and any(k in text for k in ("미국 대표단", "미국 특사", "미국 협상단", "us delegation", "us envoys", "witkoff")):
        return "ukraine:us-envoys-weekend"
    if "시장파급" in x.get("tags", []):
        title = re.sub(r"\W+", " ", x.get("title_ko") or x.get("title_original") or "").strip().lower()
        return "market:" + title[:90]
    title = re.sub(r"\W+", " ", x.get("title_ko") or x.get("title_original") or "").strip().lower()
    return "title:" + title[:110]


def _dedupe_events(items, now):
    chosen = []
    positions = {}
    for x in items:
        key = _event_key(x)
        if key not in positions:
            positions[key] = len(chosen)
            chosen.append(x)
            continue
        idx = positions[key]
        old = chosen[idx]
        old_age = watch.age_minutes(old, now)
        new_age = watch.age_minutes(x, now)
        old_fresh = -(old_age if old_age is not None else 99999)
        new_fresh = -(new_age if new_age is not None else 99999)
        if (_source_rank(x), new_fresh) > (_source_rank(old), old_fresh):
            chosen[idx] = x
    return chosen


def _replace_block(text, heading, next_headings, rows):
    marker = f"<b>{heading}</b>\n"
    start = text.find(marker)
    if start == -1:
        return text
    body_start = start + len(marker)
    ends = []
    for h in next_headings:
        p = text.find(f"\n<b>{h}</b>\n", body_start)
        if p != -1:
            ends.append(p)
    end = min(ends) if ends else len(text)
    if not rows:
        # 섹션 자체를 제거한다.
        before = text[:start].rstrip()
        after = text[end:]
        if after.startswith("\n"):
            after = after[1:]
        return before + ("\n" if before and after else "") + after
    return text[:body_start] + "\n".join(rows) + text[end:]


def _compact_blocks(text, items):
    joined = " ".join(_row_text(x) for x in items)
    tags = {t for x in items for t in x.get("tags", [])}
    ukraine = any(k in joined for k in ("우크라이나", "러시아", "ukraine", "russia", "푸틴", "putin", "젤렌스키", "zelensky"))
    iran = any(k in joined for k in ("이란", "호르무즈", "iran", "hormuz"))
    pause = any(k in joined for k in ("72시간 중단", "3일간 중단", "3일 중단", "72-hour pause", "no strikes on kyiv", "키이우72시간공습중단", "키이우공습중단"))
    envoy_meeting = ("위트코프" in joined or "witkoff" in joined) and ("쿠슈너" in joined or "kushner" in joined) and any(k in joined for k in ("회담", "meeting", "talks", "토요일", "saturday"))
    rebuild = "재건" in tags or any(k in joined for k in ("재건", "reconstruction", "rebuilding"))
    escalation = "확전" in tags

    if pause:
        invest = [
            "- <b>핵심:</b> 72시간 공습중단 이행 + 미 특사회담이 종전 신뢰도 결정",
            "- <b>시장:</b> 이행 확인 → 유가·위험프리미엄↓ / 달러·금리 안정 시 위험선호↑",
        ]
        contrary = ["- 키이우 공습 재개·대규모 미사일/병력 증강"] if escalation else []
        next_rows = [
            "- <b>24~72시간:</b> 실제 공습중단 이행 / 푸틴-미 특사 공동발표",
            "- <b>후속:</b> 키이우 방문 → 정상회담·휴전 조건",
        ]
    elif ukraine:
        invest = [
            "- <b>핵심:</b> 미 협상단 방문 → 정상회담 → 휴전 문안 구체화 여부",
            "- <b>시장:</b> 종전 진전 → 유가·위험프리미엄↓ / 위험선호↑",
        ]
        contrary = ["- 장거리 공습 재확대·회담 연기"] if escalation else []
        next_rows = ["- <b>다음:</b> 방문일 확정 → 공동발표 → 실제 공습 감소"]
    elif iran:
        invest = [
            "- <b>핵심:</b> 공식 휴전·종전 선언과 호르무즈 통항 정상화 여부",
            "- <b>시장:</b> 확인 시 유가·위험프리미엄↓ / 달러·금리 안정 여부 확인",
        ]
        contrary = ["- 추가 공습·호르무즈 봉쇄·병력 증강"] if escalation else []
        next_rows = ["- <b>다음:</b> 공식 합의문 → 실제 교전 중단 → 호르무즈 통항"]
    elif rebuild:
        invest = ["- <b>핵심:</b> 재건기금 → 입찰 → 본계약 → 수주까지 실제 매출 연결 확인"]
        contrary = []
        next_rows = ["- <b>다음:</b> 발주처·기업 실명·계약금액"]
    else:
        invest = ["- <b>핵심:</b> 새 전쟁·외교 신호의 실제 행동 변화 여부 확인"]
        contrary = []
        next_rows = []

    text = _replace_block(text, "투자 판정", ("반대 신호", "다음 확인"), invest)
    text = _replace_block(text, "반대 신호", ("다음 확인",), contrary)
    text = _replace_block(text, "다음 확인", (), next_rows)

    # 핵심 문장과 동일한 설명을 한 번 더 반복하는 보조문장은 제거한다.
    text = re.sub(r"\n- 푸틴, 미국 대표단 방문을 위해 키이우 공습을 3일간 중단하도록 명령했다는 보도", "", text)
    return re.sub(r"\n{3,}", "\n\n", text).strip()[:4000] + "\n"


def compact_build_alert(items, markets, now):
    deduped = _dedupe_events(items, now)
    # 동일 사건의 재전송 기사로 본문이 길어지는 것을 막되, 서로 다른 촉매는 유지한다.
    core = [x for x in deduped if "시장파급" not in x.get("tags", [])][:4]
    market = [x for x in deduped if "시장파급" in x.get("tags", [])][:2]
    selected = core + market
    text = _prev_build_alert(selected, markets, now)
    return _compact_blocks(text, selected)


watch.build_alert = compact_build_alert


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
