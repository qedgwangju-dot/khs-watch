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


def row(title, *, source="국내 재게시", description="", article_text="", minutes_ago=10, deep_signal=False, link="https://example.com/test"):
    now = dt.datetime.now(mod.watch.KST)
    pub = now - dt.timedelta(minutes=minutes_ago)
    return {
        "title": title,
        "title_original": title,
        "title_ko": title,
        "description": description,
        "article_text": article_text,
        "source": source,
        "link": link,
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

# 8) 호르무즈 실물 물동량 회복은 정식 재개방 문구가 없어도 고우선 경보로 분류한다.
hormuz_flow = row(
    "Hormuz oil flows surge to a record amount compared with before the war",
    source="Reuters",
)
marks = mod._physical_flow_marks(hormuz_flow)
check("hormuz-record-flow-detected", "호르무즈기록물량회복" in marks)
score, tags = mod.score_item(hormuz_flow, dt.datetime.now(mod.watch.KST))
check("hormuz-record-flow-priority", score == 100 and "실물물동량" in tags)

# 9) 오만만 STS 기록 급증은 우회 물류 회복 경보로 분류한다.
oman_sts = row(
    "Gulf of Oman ship-to-ship STS activity surges to record levels",
    source="Kpler",
)
marks = mod._physical_flow_marks(oman_sts)
check("oman-sts-record-detected", "오만만STS기록급증" in marks)
check("oman-sts-topic", mod.topic_label(oman_sts) == "호르무즈·걸프 · 원유 물동량 회복")

# 10) 사우디 원유 수출 회복도 별도 물량 경보로 분류한다.
saudi_flow = row(
    "Saudi crude shipments surge to highest level since the war began",
    source="Bloomberg",
    description="Exports through the Gulf recovered sharply.",
)
marks = mod._physical_flow_marks(saudi_flow)
check("saudi-crude-recovery-detected", "사우디원유수출회복" in marks)

# 11) 'record amount ... out of Hormuz'처럼 flow라는 단어가 없는 속보도 물량 경보로 잡는다.
record_amount = row(
    "Last night we took a record amount of oil out of the Hormuz Strait, more than before the war",
    source="Walter Bloomberg",
)
marks = mod._physical_flow_marks(record_amount)
check("hormuz-record-amount-wording", "호르무즈기록물량회복" in marks)

# 12) 7일 평균 2천만 배럴/일과 STS 10배 증가 표현을 직접 감지한다.
regional_20m = row(
    "Mideast Gulf & Gulf of Oman regional exports 7-day average exceeds 20 million barrels a day",
    source="Kpler",
)
marks = mod._physical_flow_marks(regional_20m)
check("gulf-20mbd-seven-day", "걸프7일평균2천만배럴" in marks)

sts_10x = row(
    "Gulf of Oman STS volumes increased 10x versus February",
    source="Kpler",
)
marks = mod._physical_flow_marks(sts_10x)
check("oman-sts-10x", "오만만STS기록급증" in marks)

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


# 9) Bloomberg 9/28형: 이란 측의 '중간선거 전 타결 회의 + 선거 후 확전 위험'은
# 기존 트럼프 휴전안 거절 재인용이 아니라 별도 신규 협상제약 사건으로 본다.
iran_midterm = row(
    "Iranian officials are skeptical of a deal before the U.S. midterms and see a higher risk of escalation after November 3",
    source="Bloomberg",
    description=(
        "Officials said last week's New York talks made little progress. "
        "Foreign Minister Abbas Araghchi remained in the United States for further talks through mediators "
        "after meeting Jared Kushner and Steve Witkoff."
    ),
)
marks = mod._marks(iran_midterm)
check("iran-midterm-skepticism-detected", "이란중간선거전합의회의" in marks)
check("iran-post-election-risk-detected", "이란선거후확전위험" in marks)
check("iran-araghchi-stays-detected", "아라치미국체류추가협상" in marks)
check("iran-midterm-yellow", mod._emergency_color(iran_midterm) == "yellow")
check("iran-midterm-topic", mod.topic_label(iran_midterm) == "이란·미국 · 중간선거 전 협상 제약")
midterm_score, midterm_tags = mod.score_item(iran_midterm, dt.datetime.now(mod.watch.KST))
check("iran-midterm-high-priority", midterm_score >= 99 and "협상제약" in midterm_tags)

# 10) 빨강+초록 혼재 헤더는 '초록 단독 오판'이 아니므로 품질 게이트가 막으면 안 된다.
mixed_alert = """<b>전쟁·종전·재건 웹감시</b>
🔴 <b>공격·확전</b>  |  🟢 <b>재건·휴전</b>
<b>핵심 변화</b>
🔴 [신규] <b>1. 이란·호르무즈</b>
이란 남부 복수 폭발음
🟢 [신규] <b>2. 이란·호르무즈</b>
협상 재개 신호
<b>투자 판정</b>
"""
check("quality-gate-mixed-header-allowed", not any("초록 헤더" in x for x in mod._alert_quality_issues(mixed_alert)))

print("WAR_PEACE_MIDTERM_RISK_OK")


# 11) 2026-10-01 실제 오탐: 러시아 곰 개체수·치명적 동물 공격은 전쟁 경보가 아니다.
bear_story = row(
    "Russia draws up measures to control bear population after spate of deadly attacks",
    source="Reuters",
    link="https://www.reuters.com/business/environment/russia-draws-up-measures-control-bear-population-after-spate-deadly-attacks-2026-09-30/",
)
check("wildlife-bear-false-positive", mod._obvious_false_positive(bear_story))
bear_score, bear_tags = mod.score_item(bear_story, dt.datetime.now(mod.watch.KST))
check("wildlife-bear-score-zero", bear_score == 0 and bear_tags == [])

# 12) 같은 Reuters 원문 URL은 제목이 바뀌어도 한 번만 알린다.
ukr_url = "https://www.reuters.com/world/europe/russian-air-strikes-kill-one-injure-five-around-kyiv-officials-say-2026-09-30/"
ukr_a = row("Russia launches major attack on Ukraine energy grid as winter nears", source="Reuters", link=ukr_url)
ukr_b = row("Russia hits Ukraine energy grid, cutting power as winter approaches", source="Reuters", link=ukr_url)
check("same-reuters-url-one-id-ukraine", mod.item_id(ukr_a) == mod.item_id(ukr_b))

gaza_url = "https://www.reuters.com/world/middle-east/israeli-strikes-kill-five-people-gaza-medics-say-2026-09-30/"
gaza_a = row("Israeli strikes kill six people in Gaza, medics say", source="Reuters", link=gaza_url)
gaza_b = row("Israeli strikes kill seven people in Gaza", source="Reuters", link=gaza_url)
check("same-reuters-url-one-id-gaza", mod.item_id(gaza_a) == mod.item_id(gaza_b))
check("gaza-topic-not-lebanon", mod.topic_label(gaza_a) == "이스라엘·가자")

# 13) 후티 공격 이후 EASA 사우디 영공 권고는 실제 운영 제약이므로 방향성 미확인이 아니라 확전 영향이다.
easa = row(
    "EU aviation agency issues Saudi airspace advisory after Houthi attacks",
    source="Reuters",
    link="https://www.reuters.com/world/middle-east/eu-aviation-agency-issues-saudi-airspace-advisory-after-houthi-attacks-2026-09-30/",
)
check("easa-operational-escalation", mod._operational_escalation_signal(easa))
check("easa-red", mod._final_item_color(easa) == "red")
easa_verdict = mod.guard._verdict([easa])
check("easa-red-verdict", "공격·확전" in easa_verdict or "군사행동·확전" in easa_verdict)

# 14) '폭격할지 협상을 타결할지 곧 결정'은 평화 초록이 아니라 조건부 군사옵션 노랑이다.
bomb_or_deal = row("트럼프 \"이란을 폭격할지 아니면 협상을 타결할지 곧 결정할 것\" - 프리진뉴스")
check("bomb-or-deal-conditional-risk", mod._conditional_escalation_signal(bomb_or_deal))
check("bomb-or-deal-yellow", mod._final_item_color(bomb_or_deal) == "yellow")
bomb_marks = mod._marks(bomb_or_deal)
check("bomb-or-deal-stage-mark", "미국이란군사옵션협상갈림길" in bomb_marks)
bomb_score, bomb_tags = mod.score_item(bomb_or_deal, dt.datetime.now(mod.watch.KST))
check("bomb-or-deal-tags", "확전위험" in bomb_tags and "협상갈림길" in bomb_tags)

# 15) '사흘간 호르무즈 빠져나온 원유 역대 가장 많아'는 실물 공급회복 신호이며 빨강이 아니다.
record_kr = row("트럼프 “사흘간 호르무즈 빠져나온 원유 역대 가장 많아”", source="한겨레")
record_marks = mod._physical_flow_marks(record_kr)
check("korean-record-flow-detected", "호르무즈기록물량회복" in record_marks)
check("korean-record-flow-green", mod._final_item_color(record_kr) == "green")

# 16) 같은 날 Walter 속보와 국내 재인용의 물동량 이벤트는 동일 사건 id로 묶는다.
record_en = row(
    "Last night we took a record amount of oil out of the Hormuz Strait, more than before the war",
    source="Walter Bloomberg",
)
check("same-day-flow-one-id", mod.item_id(record_kr) == mod.item_id(record_en))

# 17) 브랸스크의 우크라이나 공격은 종전·협상이 아니라 우크라이나·러시아 전쟁 사건이다.
bryansk = row("In brief: 12 people including a student injured in Ukrainian attack on Bryansk region", source="TASS")
check("bryansk-topic", mod.topic_label(bryansk) == "우크라이나·러시아")
check("bryansk-red", mod._final_item_color(bryansk) == "red")

# 18) 2026-10-01 실제 잘못된 색상 조합은 송출 직전 품질 게이트에서 거부한다.
bad_mixed = """<b>전쟁·종전·재건 웹감시</b>
🔴 <b>공격·확전</b>  |  🟢 <b>재건·휴전</b>
<b>핵심 변화</b>
🟢 [신규] <b>1. 이란·호르무즈</b>
트럼프 \"이란을 폭격할지 아니면 협상을 타결할지 곧 결정할 것\"
09:53 KST · 🟨 <b>91분 전</b> · 확전
🔴 [신규] <b>2. 이란·호르무즈</b>
트럼프 “사흘간 호르무즈 빠져나온 원유 역대 가장 많아”
09:15 KST · 🟨 <b>129분 전</b> · 실물물동량 · 원유공급회복
<b>투자 판정</b>
"""
bad_issues = mod._alert_quality_issues(bad_mixed)
check("quality-gate-green-escalation-item", any("초록 항목" in x for x in bad_issues))
check("quality-gate-red-flow-item", any("빨강 항목" in x for x in bad_issues))

bad_gaza = """<b>전쟁·종전·재건 웹감시</b>
<b>핵심 변화</b>
[신규] <b>1. 이스라엘·레바논</b>
이스라엘, 가자지구 공습으로 7명 사망
<b>투자 판정</b>
"""
check("quality-gate-gaza-topic", any("가자 사건" in x for x in mod._alert_quality_issues(bad_gaza)))

bad_bear = """<b>전쟁·종전·재건 웹감시</b>
<b>핵심 변화</b>
[신규] <b>1. 우크라이나·러시아</b>
러시아는 치명적인 공격을 가한 후 곰 개체수를 통제하기 위한 대책을 마련한다.
<b>투자 판정</b>
"""
check("quality-gate-bear", any("비군사 공격" in x for x in mod._alert_quality_issues(bad_bear)))

print("WAR_PEACE_2026_10_01_REGRESSION_OK")
