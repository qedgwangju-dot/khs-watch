#!/usr/bin/env python3
"""2026-10-04 이후 전쟁 감시 의미 보강.

기존 oct04 guard 위에 실제 오분류 사례만 추가 교정한다.
"""
from __future__ import annotations

import argparse
import hashlib
import re

import war_peace_reconstruction_watch_oct04_guard as prev

watch = prev.watch
runner = prev.runner
base = prev.base
guard = prev.guard

_orig_marks = prev.marks
_orig_title = prev.korean_title
_orig_signals = prev.signals
_orig_score = watch.score_item
_orig_topic = watch.topic_label
_orig_color = prev.final_color
_orig_verdict = prev.verdict
_orig_verify = prev.verify_alert


def _aramco_claim(row):
    text = prev._text(row)
    core = any(x in text for x in ("aramco", "아람코")) and any(x in text for x in ("riyadh", "리야드"))
    actor = any(x in text for x in ("houthi", "houthis", "후티", "ansar allah", "안사르"))
    claim = any(x in text for x in (
        "say they attacked", "says it attacked", "claimed responsibility", "claimed it attacked",
        "공격했다고 주장", "공격 주장", "배후를 자처",
    ))
    weapons = any(x in text for x in ("missile", "drone", "미사일", "드론"))
    return core and actor and claim and weapons


def _ukraine_bridge_event(row):
    text = prev._text(row)
    return (
        any(x in text for x in ("ukraine", "ukrainian", "우크라이나"))
        and any(x in text for x in ("bridge", "bridges", "교량", "다리"))
        and any(x in text for x in ("attack", "strike", "공격", "공습", "피격", "타격"))
        and any(x in text for x in ("logistical nightmare", "traffic restrictions", "logistics", "물류", "통행 제한"))
    )


def marks(row):
    out = list(_orig_marks(row))
    if _aramco_claim(row):
        out = [m for m in out if m != "후티리야드미사일위협"]
        out.append("후티리야드아람코공격주장")
    return sorted(set(out))


def korean_title(ms):
    if "후티리야드아람코공격주장" in ms:
        return "후티, 리야드 Aramco 시설 공격 주장 — 사우디·Aramco 피해와 방어 성공 여부는 별도 확인"
    return _orig_title(ms)


def signals(ms):
    out = []
    if "후티리야드아람코공격주장" in ms:
        out.append("🔴 후티가 리야드 Aramco 시설 공격을 주장 — 사우디 당국·Aramco의 피해 확인과 방어 성공 여부는 별도 확인")
    return out + _orig_signals(ms)


def score_item(row, now):
    score, tags = _orig_score(row, now)
    ms = set(marks(row))
    tags = list(tags or [])
    if "후티리야드아람코공격주장" in ms:
        tags = [t for t in tags if t not in ("휴전·평화", "재건", "종전·협상")]
        tags += ["사우디·후티", "확전", "에너지시설위험", "공격주장", "피해확인대기"]
        score = max(score, 100)
    if _ukraine_bridge_event(row):
        tags = [t for t in tags if t not in ("휴전·평화", "재건", "종전·협상")]
        tags += ["우크라이나·러시아", "확전", "인프라위험"]
        score = max(score, 100)
    return min(score, 100), sorted(set(tags))


def item_id(row):
    if _aramco_claim(row):
        return hashlib.sha256(("event|saudi-aramco|riyadh-houthi-claim|" + prev._published_day(row)).encode()).hexdigest()[:20]
    return prev.item_id(row)


def topic_label(row):
    if "후티리야드아람코공격주장" in set(marks(row)):
        return "사우디·후티 · Aramco 공격 주장"
    if _ukraine_bridge_event(row):
        return "우크라이나·러시아 · 교량·물류 인프라 공격"
    return _orig_topic(row)


def final_color(row):
    if "후티리야드아람코공격주장" in set(marks(row)) or _ukraine_bridge_event(row):
        return "red"
    return _orig_color(row)


def verdict(items):
    if any(_aramco_claim(x) or _ukraine_bridge_event(x) for x in items):
        colors = [final_color(x) for x in items]
        if "red" in colors:
            return (
                "<b>투자 판정</b>\n"
                "- <b>핵심:</b> 실제 공격 또는 공격 주장에 따른 운영·에너지 인프라 위험이 중심\n"
                "- <b>현재 단계:</b> 군사·안보 위험 지속 — 피해 확인과 책임 주체 확인을 분리\n"
                "- <b>시장:</b> 유가·해운·보험 위험프리미엄 상승 압력\n"
                "- <b>다음:</b> 공식 피해 확인 → 추가 공격 → 운영 제한 → 실제 교전 강도"
            )
    return _orig_verdict(items)


def verify_alert(test_mode=False):
    _orig_verify(test_mode=test_mode)
    if not watch.ALERT.exists():
        return
    text = watch.ALERT.read_text(encoding="utf-8")
    low = text.lower()
    issues = []
    if "요격" in text and "fire-smoke-seen-near-aramco" in low:
        issues.append("Aramco 공격 주장과 방어 성공 여부 혼동")
    if "🟢" in text and "석유업체 빅딜" in text:
        issues.append("상업거래를 휴전 진전으로 표시")
    if issues:
        raise RuntimeError("WAR_OCT04_GUARD2: " + " | ".join(issues))


prev.marks = marks
prev.korean_title = korean_title
prev.signals = signals
watch.score_item = score_item
watch.item_id = item_id
watch.topic_label = topic_label
prev.final_color = final_color
guard._enhanced_body_color = final_color
guard._verdict = verdict
runner.verify_alert = verify_alert


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
