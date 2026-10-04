#!/usr/bin/env python3
from __future__ import annotations

import datetime as dt
import pathlib
import sys
from email.utils import format_datetime

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import war_peace_reconstruction_watch_oct04_guard as mod


def row(title, *, source="국내 재게시", description="", article_text="", minutes_ago=10, link="https://example.com/test"):
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
        "signals_ko": [],
        "forced_tags": [],
    }


def check(name, cond):
    if not cond:
        raise AssertionError(name)
    print("PASS", name)


# 1) Reuters: 'will hit refineries'는 실제 피격이 아니라 공격 확대 예고.
refinery_policy = row(
    "Ukraine will hit Russian refineries in response to Moscow's new doctrine of airstrikes, Zelenskiy says",
    source="Reuters",
    description="Ukraine will double down on attacking Russian oil refineries in response to expanded Russian airstrikes.",
    link="https://www.reuters.com/business/aerospace-defense/ukraine-will-hit-russian-refineries-response-moscows-new-doctrine-airstrikes-2026-10-03/",
)
check("oct04-refinery-policy-detected", mod._future_refinery_policy(refinery_policy))
check("oct04-refinery-policy-yellow", mod.final_color(refinery_policy) == "yellow")
check("oct04-refinery-policy-topic", mod.topic_label(refinery_policy) == "우크라이나·러시아 · 정유시설 보복 공격 예고")
s, tags = mod.score_item(refinery_policy, dt.datetime.now(mod.watch.KST))
check("oct04-refinery-policy-not-actual-hit-tag", "확전위험" in tags and "공격확대예고" in tags)

# 2) Reuters 아람코 화재: Houthi 배경이 본문에 있어도 원인·책임주체 미확정이면 미사일 공격 확정 금지.
aramco_fire = row(
    "Fire, smoke seen near Aramco facility in Riyadh, witness says",
    source="Reuters",
    description=(
        "There was no immediate confirmation from Saudi authorities. "
        "There was no immediate claim of responsibility for the fire. "
        "The fire comes amid escalating hostilities with Houthis, who attacked Yanbu with missiles last week."
    ),
    link="https://www.reuters.com/business/energy/fire-smoke-seen-near-aramco-facility-riyadh-witness-says-2026-10-03/",
)
check("oct04-aramco-unknown-detected", mod._aramco_fire_unattributed(aramco_fire))
check("oct04-aramco-no-houthi-missile-mark", "후티리야드미사일위협" not in mod.emergency_marks(aramco_fire))
check("oct04-aramco-yellow", mod.final_color(aramco_fire) == "yellow")
check("oct04-aramco-topic", mod.topic_label(aramco_fire) == "사우디·아람코 · 화재 원인 미확정")

# 3) Medvedev 평화 조건은 실제 공격이 아니라 러시아 측 입장 표명.
medvedev = row(
    "Medvedev names conditions for peace in Ukraine, comments on impact of Iran attacks",
    source="TASS",
)
check("oct04-medvedev-commentary", mod._peace_conditions_commentary(medvedev))
check("oct04-medvedev-yellow", mod.final_color(medvedev) == "yellow")
check("oct04-medvedev-topic", mod.topic_label(medvedev) == "우크라이나·러시아 · 종전 조건 입장")

# 4) Lukoil 해외자산 거래는 종전 협상 맥락의 상업거래이지 휴전 진전이 아니다.
lukoil = row(
    "트럼프 특사·푸틴, 우크라 종전 협상서 '러 석유업체 빅딜' 논의",
    source="뉴스1",
    description="푸틴은 루코일 해외자산 매각 거래를 성사시켜 달라고 요청했다.",
)
check("oct04-lukoil-side-deal", mod._lukoil_side_deal(lukoil))
check("oct04-lukoil-yellow", mod.final_color(lukoil) == "yellow")
check("oct04-lukoil-topic", mod.topic_label(lukoil) == "우크라이나·러시아 · 종전협상 연계 상업거래")

# 5) 호르무즈 동일 유조선 피격 클러스터의 국내 재인용은 같은 사건 ID.
tanker_a = row(
    "호르무즈 해협서 유조선 잇달아 피격",
    source="파이낸셜뉴스",
    description="UKMTO는 지난 24시간 동안 유조선 최소 3척이 미확인 발사체 공격을 받았다고 경고했다.",
)
tanker_b = row(
    "호르무즈서 하루 새 유조선 2척 피격…정체불명 발사체 공격 잇따라",
    source="해사뉴스",
    description="UKMTO 보고를 인용한 동일 사건 재보도.",
)
check("oct04-tanker-a-detected", mod._hormuz_tanker_attack(tanker_a))
check("oct04-tanker-b-detected", mod._hormuz_tanker_attack(tanker_b))
check("oct04-tanker-same-id", mod.item_id(tanker_a) == mod.item_id(tanker_b))
check("oct04-tanker-red", mod.final_color(tanker_a) == "red")

# 6) Reuters/AP 동일 URL은 제목이 바뀌어도 동일 ID.
same_url_a = row(
    "Russia launches new strikes on Ukraine infrastructure",
    source="Reuters",
    link="https://www.reuters.com/world/europe/sample-article-2026-10-03/",
)
same_url_b = row(
    "Updated: Russia widens strikes on Ukraine infrastructure",
    source="Reuters",
    link="https://www.reuters.com/world/europe/sample-article-2026-10-03/",
)
check("oct04-stable-reuters-url-id", mod.item_id(same_url_a) == mod.item_id(same_url_b))

# 7) 빨강 실제 공격 + Lukoil 상업거래가 섞여도 '휴전 진전' 판정 금지.
bridge_attack = row(
    "Russian strikes on Kyiv bridges could create logistical nightmare for Ukraine",
    source="NYT",
    description="Russia attacked Kyiv bridges six times in three days; traffic restrictions followed.",
)
check("oct04-bridge-attack-red", mod.final_color(bridge_attack) == "red")
mix_verdict = mod.verdict([bridge_attack, lukoil])
check(
    "oct04-mixed-no-false-peace",
    "외교·휴전·종전 방향의 구체적 진전" not in mix_verdict
    and "실제 공격" in mix_verdict
    and "상업거래나 조건 제시를 휴전 진전으로 보지 않음" in mix_verdict
)

evac_warning = row(
    "Russia warns diplomats and foreigners to leave Kyiv immediately",
    source="AFP",
    description="Russia said massive retaliatory strikes will continue and warned of mortal danger.",
)
check("oct04-kyiv-evac-warning-red", mod._kyiv_evacuation_strike_warning(evac_warning) and mod.final_color(evac_warning) == "red")

# 8) 렌더링 색상/주제도 최종 출력에서 교정.
now = dt.datetime.now(mod.watch.KST)
for x in (refinery_policy, aramco_fire, medvedev, lukoil, tanker_a):
    score, tags = mod.score_item(x, now)
    x["score"] = score
    x["tags"] = tags
    x["age"] = mod.watch.age_minutes(x, now)
rendered = mod.watch.build_alert([refinery_policy, aramco_fire, medvedev, lukoil, tanker_a], [], now)
check("oct04-render-refinery-yellow", "🟡 [신규] <b>1. 우크라이나·러시아 · 정유시설 보복 공격 예고</b>" in rendered)
check("oct04-render-aramco-yellow", "사우디·아람코 · 화재 원인 미확정" in rendered and "후티의 리야드 탄도미사일 공격·요격 신호" not in rendered)
check("oct04-render-lukoil-yellow", "종전협상 연계 상업거래" in rendered)
check("oct04-render-tanker-red", "이란·호르무즈 · 유조선 피격" in rendered)

# 9) 품질 게이트는 과거 실제 오판 문구를 거부.
bad_aramco = """<b>전쟁·종전·재건 웹감시</b>
🔴 <b>공격·확전</b>
<b>핵심 변화</b>
🔴 [신규] <b>1. 중동 비상 · 복합확전 경보</b>
후티의 리야드 탄도미사일 공격·요격 신호
<a href="https://www.reuters.com/business/energy/fire-smoke-seen-near-aramco-facility-riyadh-witness-says-2026-10-03/">Reuters 원문</a>
"""
mod.watch.ALERT.parent.mkdir(parents=True, exist_ok=True)
mod.watch.ALERT.write_text(bad_aramco, encoding="utf-8")
try:
    mod.verify_alert(False)
    raise AssertionError("oct04-quality-gate-aramco")
except RuntimeError as e:
    check("oct04-quality-gate-aramco", "아람코" in str(e))

print("WAR_PEACE_OCT04_REGRESSION_OK")
