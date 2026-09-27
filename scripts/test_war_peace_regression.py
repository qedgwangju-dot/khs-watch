#!/usr/bin/env python3
"""전쟁·종전·재건 감시 회귀 테스트.

실제 운영에서 이미 발생했던 실패 패턴을 고정 테스트로 남겨,
같은 유형의 중복·노후 기사·색상 오판이 다시 들어오면 송출 전에 실패시킨다.
"""
from __future__ import annotations

import datetime as dt
import pathlib
import sys
from email.utils import format_datetime

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import war_peace_reconstruction_watch_diplomacy_flash as mod


def row(title, *, source="국내 재게시", description="", article_text="", minutes_ago=10, deep_signal=False):
    now = dt.datetime.now(mod.watch.KST)
    pub = now - dt.timedelta(minutes=minutes_ago)
    return {
        "title": title,
        "title_original": title,
        "title_ko": title,
        "description": description,
        "article_text": article_text,
        "source": source,
        "link": "https://example.com/test",
        "published": format_datetime(pub),
        "deep_signal": deep_signal,
        "signals_ko": [],
        "forced_tags": [],
    }


def check(name, cond):
    if not cond:
        raise AssertionError(name)
    print(f"PASS {name}")


# 1) 오늘 실제 오판: 후티 공격 여파·리야드 학교 등교 중단은 초록이 아니라 실제 공격 신호다.
houthi_school = row("친이란 후티 공격 이어지는 사우디…리야드 학교들, 등교 중단")
check("houthi-school-active-attack", mod._active_attack_signal(houthi_school))
check("houthi-school-topic", mod.topic_label(houthi_school) == "사우디·후티")
verdict = mod.guard._verdict([houthi_school])
check("houthi-school-red-verdict", "공격·확전" in verdict or "군사행동·확전" in verdict)

# 2) 오늘 실제 노이즈: TASS의 정례 병력손실 주장만 있는 기사는 핵심 신규 변화에서 제외한다.
tass_routine = row(
    "Military operation in Ukraine: Battlegroup East says Kyiv lost more than 1,900 troops this week",
    source="TASS",
)
check("tass-routine-filter", mod._low_value_tass_battlefield_claim(tass_routine))
score, tags = mod.score_item(tass_routine, dt.datetime.now(mod.watch.KST))
check("tass-routine-score-zero", score == 0 and tags == [])

# 3) 오래된 UAE 회담 후보지 같은 기사는 deep_signal이어도 다시 살아나면 안 된다.
old_uae = row(
    "우크라이나·러시아 후속 3자 협상 회담 준비, 차기 회담 후보지 UAE",
    minutes_ago=1272,
    deep_signal=True,
)
score, tags = mod.score_item(old_uae, dt.datetime.now(mod.watch.KST))
check("old-news-never-revives", score == 0 and tags == [])

# 4) 같은 트럼프-이란 휴전안 거절 사건을 매체별 제목 차이로 다시 신규화하지 않는다.
reject_a = row("트럼프, 이란 '7일 휴전안' 거부…중간선거 뒤 공습 재개 시사")
reject_b = row("트럼프 \"이란 휴전안 거절\"…11월 선거 후 공습 재개 검토")
reject_c = row("트럼프, 이란의 호르무즈 개방 조건에 회의적…11월 선거 후 공습 재개 검토")
reject_d = row("이란 제안 거부한 트럼프, 중간선거 이후 폭격 가능성 - 부산일보")
keys = {mod._canonical_event_key(x) for x in (reject_a, reject_b, reject_c, reject_d)}
check("iran-truce-rejection-one-event", len(keys) == 1 and None not in keys)
ids = {mod.item_id(x) for x in (reject_a, reject_b, reject_c, reject_d)}
check("iran-truce-rejection-one-id", len(ids) == 1)

# 5) 검색 질의 문맥에 리야드가 섞여도 원제목이 리야드 미사일 공격이 아니면 고위험 경보 승격 금지.
false_riyadh = row(
    "Yemen government forces repel Houthi push on key Taiz-Aden route",
    source="Reuters",
    description="Search context mentioned Riyadh missile interception yesterday.",
)
check("riyadh-source-coherence", "후티리야드미사일위협" not in mod._emergency_marks(false_riyadh))

# 6) 새 사실 없이 기존 사건을 설명하는 재가공 해설은 신규 경보에서 제외한다.
explainer = row("트럼프가 이란 휴전안을 거절한 이유는? 향후 시나리오 분석", source="국내 경제매체")
check("recycled-explainer-filter", mod._analysis_or_explainer(explainer))
score, tags = mod.score_item(explainer, dt.datetime.now(mod.watch.KST))
check("recycled-explainer-score-zero", score == 0 and tags == [])

# 7) 중요 시설 실제 공격은 TASS라도 정례 전황 필터에 걸리면 안 된다.
dc_attack = row(
    "Russian forces attacked a Vodafone data center in Kyiv",
    source="TASS",
)
check("critical-infrastructure-not-routine", not mod._low_value_tass_battlefield_claim(dc_attack))
check("critical-infrastructure-active-attack", mod._active_attack_signal(dc_attack))
dc_verdict = mod.guard._verdict([dc_attack])
check("critical-infrastructure-red", "공격·확전" in dc_verdict or "군사행동·확전" in dc_verdict)

print("WAR_PEACE_REGRESSION_OK")


# 8) 송출 직전 품질 게이트: 3시간 초과·초록/공격 모순·TASS 정례 전황은 실제 전송 전에 막는다.
stale_alert = """<b>전쟁·종전·재건 웹감시</b>
🟢 <b>재건·휴전</b>
<b>핵심 변화</b>
[후속] <b>1. 우크라이나·러시아</b>
후속 3자 협상 후보지 UAE
00:00 KST · 🟨 <b>1272분 전</b> · 종전·협상
<b>투자 판정</b>
"""
issues = mod._alert_quality_issues(stale_alert)
check("quality-gate-stale", any("노후 기사" in x for x in issues))

green_attack_alert = """<b>전쟁·종전·재건 웹감시</b>
🟢 <b>재건·휴전</b>
<b>핵심 변화</b>
[신규] <b>1. 사우디·후티</b>
친이란 후티 공격 이어지는 사우디…리야드 학교들, 등교 중단
<b>투자 판정</b>
"""
issues = mod._alert_quality_issues(green_attack_alert)
check("quality-gate-green-attack", any("초록 헤더" in x for x in issues))

tass_alert = """<b>전쟁·종전·재건 웹감시</b>
<b>핵심 변화</b>
[신규] <b>1. 우크라이나·러시아</b>
키예프는 이번 주 Battlegroup East 지역에서 1,900명 이상의 병력을 잃었습니다.
TASS 원문
<b>투자 판정</b>
"""
issues = mod._alert_quality_issues(tass_alert)
check("quality-gate-tass-routine", any("TASS 정례" in x for x in issues))

print("WAR_PEACE_QUALITY_GATE_OK")
