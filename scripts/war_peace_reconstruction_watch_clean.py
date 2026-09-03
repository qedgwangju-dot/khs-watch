#!/usr/bin/env python3
import argparse
import html
import pathlib
import re

import war_peace_reconstruction_watch_runner as runner

watch = runner.watch

CORE_TERMS = (
    "iran", "hormuz", "tehran", "이란", "호르무즈", "테헤란",
    "ukraine", "russia", "putin", "zelensky", "우크라이나", "러시아", "푸틴", "젤렌스키",
    "israel", "hezbollah", "lebanon", "이스라엘", "헤즈볼라", "레바논",
    "ceasefire", "peace talks", "peace agreement", "end the war", "종전", "휴전", "평화협상",
    "reconstruction", "rebuilding", "재건", "복구", "재건기금",
)

_original_score = watch.score_item


def strict_score_item(x, now):
    score, tags = _original_score(x, now)
    text = (x.get("title_original", "") + " " + x.get("description", "")).lower()
    # 구글뉴스 검색의 주변 결과가 핵심 변화에 섞이지 않도록 전쟁 당사자·종전·재건 키워드가 없는 기사는 제외.
    if not x.get("deep_signal") and not any(term.lower() in text for term in CORE_TERMS):
        return 0, tags
    return score, tags


watch.score_item = strict_score_item


def clean_freshness(x, now):
    age = watch.age_minutes(x, now)
    if age is None:
        return "신규", "공개시각 확인 필요"
    pub = watch.parse_pub(x.get("published", ""))
    if age <= 30:
        level = "속보"
    elif age <= 180:
        level = "신규"
    else:
        level = "후속"
    return level, f"{pub:%H:%M} KST · {age}분 전"


def clean_topic_label(x):
    text = (x.get("title_original", "") + " " + x.get("description", "")).lower()
    parts = []
    if any(k in text for k in ("iran", "hormuz", "tehran", "이란", "호르무즈", "테헤란")):
        parts.append("이란·호르무즈")
    if any(k in text for k in ("ukraine", "russia", "putin", "zelensky", "우크라이나", "러시아", "푸틴", "젤렌스키")):
        parts.append("우크라이나·러시아")
    if any(k in text for k in ("israel", "hezbollah", "lebanon", "이스라엘", "헤즈볼라", "레바논")):
        parts.append("이스라엘·레바논")
    if "재건" in x.get("tags", []) or any(k in text for k in ("reconstruction", "rebuilding", "재건", "복구")):
        parts.append("재건")
    return " · ".join(dict.fromkeys(parts)) or "종전·협상"


def build_clean_alert(items, markets, now):
    peace = any("종전·협상" in x.get("tags", []) for x in items)
    escalation = any("확전" in x.get("tags", []) for x in items)
    rebuild = any("재건" in x.get("tags", []) for x in items)
    political = any("정치일정" in x.get("tags", []) for x in items)
    pressure = any("제재·압박" in x.get("tags", []) for x in items)

    lines = [
        "<b>전쟁·종전·재건 웹감시</b>",
        f"조회 {now:%Y-%m-%d %H:%M} KST",
        "",
        "<b>핵심 변화</b>",
    ]

    for idx, x in enumerate(items[:8], 1):
        tags = " · ".join(x.get("tags", [])) or "전쟁"
        level, fresh = clean_freshness(x, now)
        signals = list(x.get("signals_ko", []))
        headline = signals[0] if signals else x.get("title_ko", x.get("title_original", ""))
        lines.append(f"[{level}] <b>{idx}. {watch.h(clean_topic_label(x))}</b>")
        lines.append(f"{watch.h(headline)}")
        if signals:
            for extra in signals[1:4]:
                lines.append(f"- {watch.h(extra)}")
            meta = f"{fresh} · 본문형 신호 · {tags} · {x.get('source') or '출처미상'}"
        else:
            meta = f"{fresh} · {tags} · {x.get('source') or '출처미상'}"
        lines.append(f"{watch.h(meta)}")
        lines.append("")

    if markets:
        lines.append("<b>시장 반응</b>")
        for m in markets:
            lines.append(f"{watch.h(m['name'])}  <b>{m['price']:,.2f}</b>  {m['pct']:+.2f}%")
        lines.append("")

    judgments = []
    if peace:
        judgments.extend([
            "<b>할인율:</b> 종전·휴전 진전이면 유가·전쟁 위험프리미엄 완화 가능",
            "<b>수급:</b> 달러·금리 안정이 동반되면 나스닥·신흥국 위험선호에 우호적",
            "<b>시간표:</b> 종전 선언·공식 휴전문·정상회담·제재 변화·병력 철수 확인",
        ])
    if political:
        judgments.append("<b>정치일정:</b> 11월 중간선거 부담이 확전 억제 또는 종전 선언을 앞당기는지 확인")
    if pressure:
        judgments.append("<b>전략변화:</b> 군사 확전보다 제재·경제 압박으로 무게가 이동하는지 확인")
    if rebuild:
        judgments.extend([
            "<b>돈 버는 능력:</b> 재건기금 → 입찰 → 본계약 → 수주 → 매출 인식 순서 확인",
            "<b>한국 기업:</b> 실명·계약금액·발주처 공식 확인 전에는 후보 단계",
        ])
    if judgments:
        lines.append("<b>투자 판정</b>")
        for j in judgments:
            lines.append(f"- {j}")
        lines.append("")

    if escalation:
        lines.extend([
            "<b>반대 신호</b>",
            "- 공습·미사일·봉쇄·병력 증강이 함께 감지됨. 종전 기대와 확전 위험을 동시에 확인해야 함.",
            "",
        ])

    checkpoints = []
    if peace:
        checkpoints.extend(["트럼프의 종전 선언 여부", "공식 합의문·공동성명", "실제 교전 중단", "후속 정상·실무회담 일정"])
    if political:
        checkpoints.extend(["공화당 중간선거 여론·전쟁 지지율", "추가 대규모 공습 승인 여부"])
    if rebuild:
        checkpoints.extend(["재건기금 운용주체", "한국 기업 실명", "입찰·MOU·본계약 구분"])
    if escalation:
        checkpoints.extend(["추가 공습 여부", "호르무즈 통항량·보험료"])
    checkpoints = list(dict.fromkeys(checkpoints))[:7]
    if checkpoints:
        lines.append("<b>다음 확인</b>")
        for cp in checkpoints:
            lines.append(f"- {watch.h(cp)}")
        lines.append("")

    lines.append("<b>원문</b>")
    for idx, x in enumerate(items[:8], 1):
        src = watch.h(x.get("source") or "출처미상")
        url = watch.h(x.get("link") or "")
        lines.append(f"{idx}. <a href=\"{url}\">{src} 기사 열기</a>")

    return "\n".join(lines).strip()[:4000] + "\n"


watch.build_alert = build_clean_alert


def write_clean_test():
    now = __import__("datetime").datetime.now(watch.KST)
    text = (
        "<b>전쟁·종전·재건 웹감시 테스트</b>\n"
        f"조회 {now:%Y-%m-%d %H:%M} KST\n\n"
        "<b>핵심 변화</b>\n"
        "[속보] <b>1. 이란·호르무즈</b>\n"
        "트럼프, 고위 보좌관들과 이란 전쟁 종료 방안 논의\n"
        "방금 전 · 종전·협상 · 테스트\n\n"
        "<b>시장 반응</b>\n"
        "나스닥100 선물  29,500.00  +0.20%\n"
        "WTI  91.50  -1.10%\n\n"
        "<b>투자 판정</b>\n"
        "- 할인율: 종전 진전 시 전쟁 위험프리미엄 완화 가능\n"
        "- 시간표: 공식 발표와 실제 교전 중단 확인\n\n"
        "<b>원문</b>\n"
        "1. 테스트 기사 열기\n"
    )
    watch.OUT.mkdir(parents=True, exist_ok=True)
    watch.ALERT.write_text(text, encoding="utf-8")
    watch.PENDING.write_text('{"ids": []}\n', encoding="utf-8")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--finalize", action="store_true")
    ap.add_argument("--telegram-test", action="store_true")
    args = ap.parse_args()
    if args.finalize:
        watch.finalize()
        return
    if args.telegram_test:
        write_clean_test()
    else:
        watch.run(test=False)
    runner.verify_alert(test_mode=False)


if __name__ == "__main__":
    main()
