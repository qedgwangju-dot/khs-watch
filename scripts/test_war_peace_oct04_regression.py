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


refinery_policy_kr = row(
    "젤렌스키, 러시아의 새 공습 교리에 대응해 러 정유시설 공격을 강화하고 계속 타격할 것",
    source="국내 재게시",
    description="우크라이나는 러시아 정유시설 타격을 확대할 방침이라고 밝혔다.",
)
check("oct04-refinery-policy-korean-variant", mod._future_refinery_policy(refinery_policy_kr))
check("oct04-refinery-policy-korean-yellow", mod.final_color(refinery_policy_kr) == "yellow")

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


# 2-b) Reuters 기사 업데이트로 후티가 Aramco 공격을 주장한 단계가 확인되면
# '원인 미확정'에서 '후티 공격 주장 + 사우디/Aramco 독립확인 대기'로 승격한다.
aramco_claim = row(
    "Yemen's Houthis say they attacked Aramco facility in Riyadh with missiles, drones",
    source="Reuters",
    description=(
        "Houthis said they attacked the Aramco facility in Riyadh with ballistic missiles and drones. "
        "Saudi authorities and Aramco had not yet independently confirmed damage."
    ),
    link="https://www.reuters.com/business/energy/fire-smoke-seen-near-aramco-facility-riyadh-witness-says-2026-10-03/",
)
check("oct04-aramco-houthi-claim-detected", mod._aramco_houthi_claim(aramco_claim))
check("oct04-aramco-houthi-claim-red", mod.final_color(aramco_claim) == "red")
check("oct04-aramco-houthi-claim-topic", mod.topic_label(aramco_claim) == "사우디·후티 · Aramco 공격 주장")

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
check(
    "oct04-render-refinery-yellow",
    "🟡 [" in rendered and "우크라이나·러시아 · 정유시설 보복 공격 예고" in rendered
)
check("oct04-render-aramco-yellow", "사우디·아람코 · 화재 원인 미확정" in rendered and "후티의 리야드 탄도미사일 공격·요격 신호" not in rendered)
rendered_lukoil = mod.watch.build_alert([lukoil], [], now)
check(
    "oct04-render-lukoil-yellow",
    "🟡 [" in rendered_lukoil and "종전협상 연계 상업거래" in rendered_lukoil
)
rendered_tanker = mod.watch.build_alert([tanker_a], [], now)
check(
    "oct04-render-tanker-red",
    "🔴 [" in rendered_tanker and "이란·호르무즈 · 유조선 피격" in rendered_tanker
)

# 8-b) 10/4 16:30형: 미래 정유시설 공격 예고 + Lukoil 상업거래만 있으면
# 전체를 재건·휴전 진전으로 판정하면 안 된다.
rendered_yellow_mix = mod.watch.build_alert([refinery_policy, lukoil], [], now)
check("oct04-yellow-mix-no-green-header", "🟢 <b>재건·휴전</b>" not in rendered_yellow_mix)
check("oct04-yellow-mix-has-yellow-header", "🟡 <b>군사위협·협상 제약</b>" in rendered_yellow_mix)

# 실제 공격 + 상업거래 혼재도 '휴전 진전'으로 뒤집히면 안 된다.
for x in (bridge_attack, lukoil):
    score, tags = mod.score_item(x, now)
    x["score"] = score
    x["tags"] = tags
    x["age"] = mod.watch.age_minutes(x, now)
rendered_red_yellow = mod.watch.build_alert([bridge_attack, lukoil], [], now)
check("oct04-red-yellow-no-green-header", "🟢 <b>재건·휴전</b>" not in rendered_red_yellow)
check("oct04-red-yellow-keeps-red", "🔴 <b>공격·확전</b>" in rendered_red_yellow)

# 9) Telegram 길이 제한으로 뒤쪽 항목이 잘려도 미전송 ID를 seen 처리하지 않는다.
rendered_delivery = """<b>전쟁·종전·재건 웹감시</b>
🔴 <b>공격·확전</b>
[신규] <b>1. 우크라이나·러시아</b>
항목 1
[신규] <b>2. 이란·호르무즈</b>
항목 2
[신규] <b>3. 우크라이나·러시아</b>
항목 3
[신규] <b>4. 이란·호르무즈</b>
항목 4
"""
mod.watch.ALERT.parent.mkdir(parents=True, exist_ok=True)
mod.watch.ALERT.write_text(rendered_delivery, encoding="utf-8")
mod.watch.PENDING.write_text(
    '{"ids":["id1","id2","id3","id4","id5","id6","id7","id8"]}',
    encoding="utf-8",
)
mod._sync_pending_to_rendered_alert()
pending_after = __import__("json").loads(mod.watch.PENDING.read_text(encoding="utf-8"))
check("oct04-delivery-pending-only-rendered", pending_after.get("ids") == ["id1", "id2", "id3", "id4"])
check("oct04-delivery-deferred-preserved", pending_after.get("deferred_ids") == ["id5", "id6", "id7", "id8"])

# 10) 품질 게이트는 과거 실제 오판 문구를 거부.
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


# 10-b) 송출 품질게이트와 동일하게 3시간 초과 뉴스는 후보 단계에서 제거.
stale_181 = row(
    "Saudi-backed forces recapture Mokha in counteroffensive",
    source="경향신문",
    description="Saudi-backed Yemeni forces recaptured Mokha from Houthis.",
    minutes_ago=181,
)
s, tags = mod.score_item(stale_181, dt.datetime.now(mod.watch.KST))
check("oct06-over-3h-candidate-suppressed", s == 0 and tags == [])

fresh_179 = row(
    "Saudi-backed forces recapture Mokha in counteroffensive",
    source="경향신문",
    description="Saudi-backed Yemeni forces recaptured Mokha from Houthis.",
    minutes_ago=179,
)
s, tags = mod.score_item(fresh_179, dt.datetime.now(mod.watch.KST))
check("oct06-under-3h-candidate-remains", s > 0)


# 11) 10/6 실운영 오판 재발 방지: 목하 과거 점령/현재 탈환공세, TASS 귀속, 트럼프 가정 발언.
mokha_counter = row(
    "Saudi-backed forces launch fight to free Bab al-Mandeb from Houthis",
    source="파이낸셜뉴스 · WSJ 재인용",
    description=(
        "Saudi-backed Yemeni forces launched a counteroffensive to reclaim Mokha. "
        "The offensive follows Houthi control of Mokha last month."
    ),
    link="https://www.fnnews.com/news/202610060901269464",
)
check("oct06-mokha-current-counteroffensive", mod._mokha_counteroffensive_context(mokha_counter))
s, tags = mod.score_item(mokha_counter, dt.datetime.now(mod.watch.KST))
check("oct06-mokha-current-not-stale-capture", s >= 100 and "탈환공세" in tags and "후티의 9월 점령은 배경" in mokha_counter["title_ko"])

mokha_stale = row(
    "Houthis captured strategic port of Mokha",
    source="재인용",
    description="Houthis captured Mokha last month in early September.",
)
s, tags = mod.score_item(mokha_stale, dt.datetime.now(mod.watch.KST))
check("oct06-mokha-stale-capture-suppressed", mod._stale_mokha_capture_only(mokha_stale) and s == 0 and tags == [])

tass_claim = row(
    "Russian forces hit enemy radars and data centers in Poltava, Odessa regions",
    source="TASS",
    description="The Russian Defense Ministry said its forces struck the targets during the military operation.",
    link="https://tass.com/defense/2197955",
)
s, tags = mod.score_item(tass_claim, dt.datetime.now(mod.watch.KST))
check("oct06-tass-russian-claim-detected", mod._tass_russian_strike_claim(tass_claim))
check("oct06-tass-russian-claim-attributed", s >= 100 and "러시아측주장" in tags and "독립 확인 전" in tass_claim["title_ko"])

tass_drone = row(
    "Russia faces largest drone attack of 2026 — TASS calculations",
    source="TASS",
    link="https://tass.com/politics/2197959",
)
s, tags = mod.score_item(tass_drone, dt.datetime.now(mod.watch.KST))
check("oct06-tass-drone-calculation-attributed", mod._tass_largest_drone_attack(tass_drone) and s >= 100 and "TASS 집계" in tass_drone["title_ko"])
check(
    "oct06-tass-russian-claim-final-translation",
    "러시아 국방부" in mod.translate_ko(tass_claim["title_original"])
    and "주장" in mod.translate_ko(tass_claim["title_original"])
    and "독립 확인 전" in mod.translate_ko(tass_claim["title_original"]),
)
check(
    "oct06-tass-drone-final-translation",
    "TASS 집계" in mod.translate_ko(tass_drone["title_original"])
    and "독립 확인 필요" in mod.translate_ko(tass_drone["title_original"]),
)

saudi_rabigh = "후티, 사우디 공항·정유시설 공습…韓기업 인근 라빅도 피격"
saudi_rabigh_ko = mod.translate_ko(saudi_rabigh)
check(
    "oct06-saudi-rabigh-confirmed-vs-claim-separated",
    "공항 피해는 사우디 확인" in saudi_rabigh_ko
    and "라빅 정유시설은 후티 주장 단계" in saudi_rabigh_ko,
)

trump_rhetoric = row(
    "Trump says let them take out Los Angeles, let them take out San Diego",
    source="TASS",
    description="Trump called it a small price to pay while discussing the Iran war and fuel prices.",
    link="https://tass.com/world/2197905",
)
s, tags = mod.score_item(trump_rhetoric, dt.datetime.now(mod.watch.KST))
check("oct06-trump-la-sd-rhetoric-suppressed", mod._trump_la_sd_hypothetical(trump_rhetoric) and s == 0 and tags == [])

bad_oct06 = """<b>전쟁·종전·재건 웹감시</b>
🔴 <b>공격·확전</b>
[속보] <b>1. 예멘·후티·바브엘만데브</b>
후티가 전략항 목하를 점령 — 바브엘만데브 접근 통제력이 한 단계 상승
[신규] <b>2. 이란·호르무즈</b>
트럼프 &quot;이란 전쟁으로 로스앤젤레스·샌디에이고 파괴될 수도 있다&quot;
"""
mod.watch.ALERT.write_text(bad_oct06, encoding="utf-8")
try:
    mod.verify_alert(False)
    raise AssertionError("oct06-quality-gate-live-misclassifications")
except RuntimeError as e:
    check("oct06-quality-gate-live-misclassifications", "목하" in str(e) and "가정적 정치 발언" in str(e))

# 12) 10/7 실운영 오류 재발 방지: 이스라엘 경고/사우디 중복/TASS 일정/Reuters 제목 번역.
israel_warning = row(
    "ISRAEL WARNS OF ATTACK RISK ABROAD AHEAD OF OCT. 7 ANNIVERSARY",
    source="Walter Bloomberg",
    link="https://t.me/WalterBloomberg/36471",
)
check("oct07-israel-warning-detected", mod._israel_oct7_abroad_warning(israel_warning))
s, tags = mod.score_item(israel_warning, dt.datetime.now(mod.watch.KST))
check("oct07-israel-warning-yellow", mod.final_color(israel_warning) == "yellow" and "확전" not in tags and "실제공격아님" in tags)
check(
    "oct07-israel-warning-translation",
    "10월 7일 3주년" in mod.translate_ko(israel_warning["title_original"])
    and "실제 공격 발생 아님" in mod.translate_ko(israel_warning["title_original"]),
)

tass_visit = row(
    "CIS summit, meeting with Pezeshkian, Caspian ecology: on Putin's visit to Turkmenistan",
    source="TASS",
    link="https://tass.com/politics/2198439",
)
s, tags = mod.score_item(tass_visit, dt.datetime.now(mod.watch.KST))
check("oct07-tass-turkmenistan-routine-suppressed", mod._tass_turkmenistan_visit_noise(tass_visit) and s == 0 and tags == [])

saudi_yonhap = row(
    "사우디 공항·정유시설에 후티 공습…韓기업 가까운 지역도 피격",
    source="연합뉴스",
    description="후티가 자잔·나지란 공항과 라빅 정유시설 등을 공격했다는 보도.",
)
saudi_vietnam = row(
    "Saudi Arabia confirms damage at two airports following Houthi attacks",
    source="Vietnam.vn",
    description="Saudi authorities confirmed damage at Jazan and Najran airports after Houthi attacks.",
)
saudi_special = row(
    "후티, 사우디 공항·정유시설 공습…한국 기업 진출지 인근도 피해",
    source="스페셜타임스",
    description="사우디 공항과 라빅 정유시설 관련 동일 사건 재보도.",
)
saudi_yonhap["published"] = "Tue, 06 Oct 2026 14:04:00 +0000"
saudi_vietnam["published"] = "Tue, 06 Oct 2026 13:39:00 +0000"
saudi_special["published"] = "Tue, 06 Oct 2026 19:25:00 +0000"
check("oct07-saudi-cluster-yh", mod._saudi_houthi_airport_refinery_cluster(saudi_yonhap))
check("oct07-saudi-cluster-vn", mod._saudi_houthi_airport_refinery_cluster(saudi_vietnam))
check("oct07-saudi-cluster-special", mod._saudi_houthi_airport_refinery_cluster(saudi_special))
check(
    "oct07-saudi-cross-source-same-id",
    mod.item_id(saudi_yonhap) == mod.item_id(saudi_vietnam) == mod.item_id(saudi_special),
)

reuters_tanker_title = "Russia says tanker crew rescued in Black Sea after attack set ship ablaze"
reuters_tanker_ko = mod.translate_ko(reuters_tanker_title)
check(
    "oct07-reuters-tanker-grammar",
    "공격으로 화재가 난" in reuters_tanker_ko
    and "승무원 23명 전원 구조" in reuters_tanker_ko
    and "승무원이 선박에 불을 붙였" not in reuters_tanker_ko,
)

# 13) 10/7 추가 실운영 보강: MT On Peace 상세 피해와 원인 미확정 이란 남부 폭발.
on_peace = row(
    "호르무즈서 파나마 유조선 피격…인도 '12명 부상'",
    source="연합뉴스",
    description=(
        "호르무즈 해협을 통과하던 파나마 선적 유조선 MT On Peace가 발사체에 피격됐다. "
        "선원 12명이 부상했고 이 중 11명은 인도인으로, 오만으로 이송돼 치료를 받았다."
    ),
)
s, tags = mod.score_item(on_peace, dt.datetime.now(mod.watch.KST))
check("oct07-on-peace-specific-detected", mod._hormuz_on_peace_attack(on_peace))
check("oct07-on-peace-red", mod.final_color(on_peace) == "red" and "선원12명부상" in tags)
check("oct07-on-peace-topic", mod.topic_label(on_peace) == "이란·호르무즈 · MT On Peace 피격")
check("oct07-on-peace-title", "선원 12명 부상" in on_peace["title_ko"] and "공격 주체 미확정" in on_peace["title_ko"])
check("oct07-on-peace-canonical-id", mod.item_id(on_peace) == "f3d52391fbf7d500afa0")

iran_unknown = row(
    "Explosions heard in Sirik, Qeshm and Minab in southern Iran",
    source="Walter Bloomberg",
    description="Multiple explosions were heard in Sirik, Qeshm and Minab; no hostile projectile or airstrike was officially confirmed.",
)
s, tags = mod.score_item(iran_unknown, dt.datetime.now(mod.watch.KST))
check("oct07-iran-south-unattributed-detected", mod._iran_south_unattributed_explosions(iran_unknown))
check("oct07-iran-south-unattributed-yellow", mod.final_color(iran_unknown) == "yellow" and "확전" not in tags and "원인미확정" in tags)
check("oct07-iran-south-unattributed-topic", mod.topic_label(iran_unknown) == "이란 남부 · 폭발 원인 미확정")
# 사건 ID는 게시일을 포함하므로 현재 시각 기반 모의 기사에서 10월 7일 해시를 고정하지 않는다.
import hashlib
iran_day = mod._published_day(iran_unknown)
iran_expected_id = hashlib.sha256(("event|iran-south|unattributed-explosions|" + iran_day).encode()).hexdigest()[:20]
check("oct07-iran-south-unattributed-id", mod.item_id(iran_unknown) == iran_expected_id)

iran_projectile = row(
    "Hostile projectiles hit Sirik after explosions in southern Iran",
    source="IRNA",
    description="Several areas in Sirik were hit by hostile projectiles.",
)
check("oct07-iran-south-confirmed-projectile-not-yellow", not mod._iran_south_unattributed_explosions(iran_projectile))

# 14) 10/7 08:32 dry-run에서 확인된 추가 오류: 공급회복/배경기사/불가리아 번역/사우디 재인용.
saudi_corrected_repost = row(
    "Saudi airport and Rabigh Aramco attack follow-up",
    source="Daum",
    description="Follow-up report on the same Houthi attacks on Saudi airports and the Rabigh refinery claim.",
)
saudi_corrected_repost["title_ko"] = "후티의 사우디 공항·라빅 Aramco 정유시설 공격 보도 — 공항 피해는 사우디 확인, 라빅 정유시설은 후티 주장 단계"
saudi_corrected_repost["published"] = "Tue, 06 Oct 2026 21:32:00 +0000"
check("oct07-saudi-corrected-repost-cluster", mod._saudi_houthi_airport_refinery_cluster(saudi_corrected_repost))
check("oct07-saudi-corrected-repost-canonical-id", mod.item_id(saudi_corrected_repost) == "ca42f91a5aa3fbdf8fa2")

sk_russia_background = row(
    "South Korea exports eased Russia fuel crisis caused by drone strikes, Ukraine says",
    source="Reuters",
    description="July and August 2026 South Korean exports of petroleum products eased Russia's fuel crisis after earlier drone strikes.",
    link="https://www.reuters.com/business/energy/south-korea-exports-eased-russia-fuel-crisis-caused-by-drone-strikes-ukraine-2026-10-06/",
)
s, tags = mod.score_item(sk_russia_background, dt.datetime.now(mod.watch.KST))
check("oct07-russia-fuel-background-suppressed", mod._south_korea_russia_fuel_background(sk_russia_background) and s == 0 and tags == [])

pipeline_recovery = row(
    "사우디 동서 송유관 하루 580만배럴 수송 회복…드론 공격 닷새 만에 재가동",
    source="파이낸스투데이",
    description="사우디 East-West pipeline이 재가동돼 5.8 million barrels 수준의 원유 수송을 회복했다.",
)
s, tags = mod.score_item(pipeline_recovery, dt.datetime.now(mod.watch.KST))
check("oct07-saudi-pipeline-recovery-detected", mod._saudi_east_west_pipeline_recovery(pipeline_recovery))
check("oct07-saudi-pipeline-recovery-green", mod.final_color(pipeline_recovery) == "green" and "확전" not in tags and "실물공급회복" in tags)
check("oct07-saudi-pipeline-recovery-topic", mod.topic_label(pipeline_recovery) == "사우디 · 동서 송유관 공급회복")
check("oct07-saudi-pipeline-recovery-id", mod.item_id(pipeline_recovery) == "a1fa9bcc8f6506fd0820")

bulgaria_title = "Drone sinks ship off Bulgaria, as fears grow about hybrid attacks by Russia"
bulgaria_ko = mod.translate_ko(bulgaria_title)
check(
    "oct07-bulgaria-reuters-translation",
    "상선 2척 피격" in bulgaria_ko
    and "1척 침몰" in bulgaria_ko
    and "공격 주체는 공식 확인 전" in bulgaria_ko
    and "드론이 불가리아에서 침몰" not in bulgaria_ko,
)

# 15) 10/7 07:58 실제 오송출 재발 방지: 9/6 네팔 재건 의향 기사를 한 달 뒤 신규/후속으로 재송출 금지.
nepal_old = row(
    "South Korea pledges support for Nepal's post-flood reconstruction",
    source="Bing News",
    description="South Korea expressed willingness to support Nepal's post-disaster reconstruction efforts.",
    minutes_ago=44398,
    link="https://www.msn.com/en-in/news/other/south-korea-pledges-support-for-nepals-post-flood-reconstruction/ar-AA2bFfkU",
)
s, tags = mod.score_item(nepal_old, dt.datetime.now(mod.watch.KST))
check("oct07-nepal-month-old-news-suppressed", s == 0 and tags == [])

bad_stale_alert = """<b>재난·재건 웹감시</b>
<b>핵심 변화</b>
[후속] <b>1. 네팔</b>
영문 기사 번역이 일시적으로 지연됨 — 원문 확인 필요
12:00 KST · 🟥 <b>44398분 전</b> · 재건·복구 · 재난 · 한국
"""
mod.watch.ALERT.write_text(bad_stale_alert, encoding="utf-8")
try:
    mod.verify_alert(False)
    raise AssertionError("oct07-quality-gate-stale-nepal")
except RuntimeError as e:
    check(
        "oct07-quality-gate-stale-nepal",
        ("3시간을 초과" in str(e)) or ("노후 기사 재등장" in str(e)),
    )


# 16) 10/7 실운영 추가 교정: 리야드 요격 사실/주장 분리와 JD Vance 귀속.
riyadh_intercept = row(
    "Saudi-led coalition intercepts Houthi ballistic missile north of Riyadh; Houthis claim airport strike",
    source="연합뉴스",
    description=(
        "The Saudi-led coalition said it intercepted one Houthi ballistic missile north of Riyadh. "
        "Separately, the Houthis claimed an airport strike; Saudi authorities did not immediately confirm that claimed hit."
    ),
)
s, tags = mod.score_item(riyadh_intercept, dt.datetime.now(mod.watch.KST))
check("oct07-riyadh-intercept-detected", mod._saudi_riyadh_intercept_vs_claim(riyadh_intercept))
check("oct07-riyadh-intercept-red", mod.final_color(riyadh_intercept) == "red")
check("oct07-riyadh-intercept-topic", mod.topic_label(riyadh_intercept) == "사우디·후티 · 리야드 미사일 요격")
check("oct07-riyadh-intercept-attribution", "요격 확인" in riyadh_intercept["title_ko"] and "사우디 확인 전" in riyadh_intercept["title_ko"])

vance_condition = row(
    "Iran must reduce uranium enrichment capacity to end war with US — vice president",
    source="TASS",
    description="US Vice President JD Vance said Iran must meaningfully reduce uranium enrichment capacity to end the war.",
    link="https://tass.com/world/2198519",
)
s, tags = mod.score_item(vance_condition, dt.datetime.now(mod.watch.KST))
check("oct07-vance-condition-detected", mod._vance_iran_enrichment_condition(vance_condition))
check("oct07-vance-condition-yellow", mod.final_color(vance_condition) == "yellow")
check("oct07-vance-condition-topic", mod.topic_label(vance_condition) == "미국·이란 · 종전 협상 조건")
check("oct07-vance-condition-attribution", "미국 부통령 JD Vance" in vance_condition["title_ko"] and "합의 진전 아님" in vance_condition["title_ko"] and "종전·협상" not in tags)


# 17) 10/7 동일 아덴 국제공항 공격의 매체별 재보도는 1개 사건으로 묶는다.
aden_yonhap = row(
    "후티, '외부통로 핵심' 예멘 아덴 국제공항 미사일 공격",
    source="연합뉴스TV",
    description="예멘 교통부는 후티가 탄도미사일과 폭발물 탑재 드론으로 아덴 국제공항을 공격했다고 밝혔다.",
    link="https://news.google.com/rss/articles/aden-yonhap",
)
aden_kbs = row(
    "후티, 예멘 아덴 국제공항에 미사일 공습…항공기 회항",
    source="KBS 뉴스",
    description="후티가 아덴 국제공항을 미사일과 드론으로 공격해 카이로발 항공기가 회항했다.",
    link="https://news.google.com/rss/articles/aden-kbs",
)
check("oct07-aden-cluster-yh", mod._aden_airport_attack_cluster(aden_yonhap))
check("oct07-aden-cluster-kbs", mod._aden_airport_attack_cluster(aden_kbs))
check("oct07-aden-cross-source-same-id", mod.item_id(aden_yonhap) == mod.item_id(aden_kbs))
check("oct07-aden-topic", mod.topic_label(aden_yonhap) == "예멘·후티 · 아덴 국제공항 공격")
check("oct07-aden-red", mod.final_color(aden_yonhap) == "red")


# 18) 공개시각 미확인 기사와 전망성 종전 발언은 신규 속보로 오염시키지 않는다.
unknown_time = {
    "title": "Russia kills 11 in one of its biggest strikes on Ukraine",
    "title_original": "Russia kills 11 in one of its biggest strikes on Ukraine",
    "title_ko": "",
    "description": "Major attack on Ukraine energy infrastructure",
    "article_text": "",
    "source": "Reuters",
    "link": "https://www.reuters.com/world/europe/example-2026-10-07/",
    "published": "",
    "signals_ko": [],
    "forced_tags": [],
}
s, tags = mod.score_item(unknown_time, dt.datetime.now(mod.watch.KST))
check("oct07-unknown-time-suppressed", s == 0 and tags == [])

rhetoric = row(
    "US president believes Ukraine conflict is nearing its end",
    source="TASS",
    description="The president said he believes the Ukraine conflict is nearly over, without announcing a ceasefire agreement or resumed talks.",
)
check("oct07-endgame-rhetoric-detected", mod._non_concrete_endgame_rhetoric(rhetoric))
s, tags = mod.score_item(rhetoric, dt.datetime.now(mod.watch.KST))
check("oct07-endgame-rhetoric-yellow", mod.final_color(rhetoric) == "yellow")
check("oct07-endgame-rhetoric-no-peace-tag", "종전·협상" not in tags and "합의진전아님" in tags)
check("oct07-endgame-rhetoric-topic", mod.topic_label(rhetoric) == "전쟁·외교 · 종전 전망성 발언")

bad_time = """<b>전쟁·종전·재건 웹감시</b>
[신규] <b>1. 우크라이나·러시아</b>
기사
공개시각 확인 필요 · 확전
"""
mod.watch.ALERT.write_text(bad_time, encoding="utf-8")
try:
    mod.verify_alert(False)
    raise AssertionError("oct07-quality-gate-unknown-time")
except RuntimeError as e:
    check("oct07-quality-gate-unknown-time", "공개시각" in str(e))


# 19) 조건부 선제공격 경고는 실제 공격이 아닌 노란색 군사위협으로 처리한다.
iran_preemptive = row(
    "*IRAN AMRY SAYS IT WILL LAUNCH PREEMPTIVE ATTACKS IF NECESSARY: FARS",
    source="Walter Bloomberg",
    description="",
    link="https://t.me/WalterBloomberg/36505",
)
check("oct07-conditional-threat-detected", mod._conditional_military_threat(iran_preemptive))
check("oct07-conditional-threat-yellow", mod.final_color(iran_preemptive) == "yellow")
s, tags = mod.score_item(iran_preemptive, dt.datetime.now(mod.watch.KST))
check("oct07-conditional-threat-no-red-tag", "확전" not in tags and "실제공격아님" in tags)
check("oct07-conditional-threat-topic", mod.topic_label(iran_preemptive) == "이란 · 조건부 선제공격 경고")
check(
    "oct07-conditional-threat-translation",
    mod.translate_ko(iran_preemptive["title_original"]) == "이란군, 필요할 경우 선제공격에 나설 수 있다고 경고 — 실제 공격 발생이 아닌 조건부 군사위협",
)

bad_conditional = """<b>전쟁·종전·재건 웹감시</b>
🔴 [속보] <b>1. 이란</b>
이란군, 필요한 경우 선제 공격에 나설 수 있다고 경고 — 조건부 군사위협
"""
mod.watch.ALERT.write_text(bad_conditional, encoding="utf-8")
try:
    mod.verify_alert(False)
    raise AssertionError("oct07-quality-gate-conditional-threat")
except RuntimeError as e:
    check("oct07-quality-gate-conditional-threat", "조건부 선제공격" in str(e))


# 20) 재인용된 이란 대통령 '전면전/저항' 발언은 신규 공격으로 재송출하지 않는다.
iran_full_war_repost = row(
    "IRAN PRESIDENT SAYS COUNTRY IS IN 'FULL-SCALE WAR'; REPEATS IRAN WILL 'RESIST' ENEMY: FARS",
    source="Walter Bloomberg",
    description="Iran president says country is in full-scale war and repeats that Iran will resist the enemy.",
    link="https://t.me/WalterBloomberg/36509",
)
check("oct07-recycled-iran-full-war-detected", mod._recycled_iran_full_scale_war_rhetoric(iran_full_war_repost))
s, tags = mod.score_item(iran_full_war_repost, dt.datetime.now(mod.watch.KST))
check("oct07-recycled-iran-full-war-suppressed", s == 0 and tags == [])

quote_only = row(
    "IRAN OFFICIAL SAYS MILITARY RESPONSE REMAINS AN OPTION: FARS",
    source="Walter Bloomberg",
    description="Iran official says a military response remains an option.",
)
check("oct07-quote-only-detected", mod._statement_only_no_action(quote_only))
s, tags = mod.score_item(quote_only, dt.datetime.now(mod.watch.KST))
check("oct07-quote-only-yellow", mod.final_color(quote_only) == "yellow")
check("oct07-quote-only-no-red-tag", "확전" not in tags and "실제행동미확인" in tags)


# 21) 동일 사우디 공항·라빅 공격은 다음날 재보도돼도 같은 사건 ID를 유지한다.
saudi_day1 = row(
    "Saudi Arabia confirms airport damage after Houthi attacks",
    source="Yonhap",
    description="Houthis attacked Jazan and Najran airports and claimed strikes on Riyadh airport and the Rabigh Aramco refinery.",
    minutes_ago=10,
)
saudi_day2 = row(
    "후티, 사우디 본토 공습…한국 기업 진출 지역까지 피해",
    source="서울경제",
    description="후티는 자잔·나지란 공항과 리야드 공항, 라빅 아람코 정유시설을 공격했다고 밝혔다.",
    minutes_ago=10,
)
saudi_day1["published"] = format_datetime(dt.datetime.now(mod.watch.KST) - dt.timedelta(hours=20))
check("oct07-saudi-oct06-signature-day1", mod._saudi_oct06_attack_signature(saudi_day1))
check("oct07-saudi-oct06-signature-day2", mod._saudi_oct06_attack_signature(saudi_day2))
check("oct07-saudi-cross-date-same-id", mod.item_id(saudi_day1) == mod.item_id(saudi_day2))



# 20) 국내 재게시에서 '아덴' 지명이 제목에서 빠져도 동일 공항 공격으로 묶는다.
aden_alias = row(
    "착륙 직전 여객기 긴급 회항…후티, 예멘 핵심공항 공습",
    source="전남일보",
    description="후티가 예멘 핵심공항을 공격해 카이로발 여객기가 착륙 직전 긴급 회항했다.",
    link="https://www.jnilbo.com/news/articleView.html?idxno=90000071713",
)
check("oct07-aden-alias-detected", mod._aden_airport_attack_cluster(aden_alias))
check("oct07-aden-alias-same-id", mod.item_id(aden_alias) == mod.item_id(aden_yonhap))
check("oct07-aden-alias-topic", mod.topic_label(aden_alias) == "예멘·후티 · 아덴 국제공항 공격")


# 22) 이란의 직접협상 부인은 전체 외교채널 결렬·군사확전으로 승격하지 않는다.
iran_direct_denial = row(
    "Iran denies direct talks with U.S. but says messages continue through mediators",
    source="Walter Bloomberg",
    description=(
        "Iranian officials denied direct negotiations with the United States, "
        "while saying messages continue to be exchanged through intermediaries."
    ),
    link="https://t.me/WalterBloomberg/36522",
)
check("oct07-iran-direct-denial-detected", mod._iran_direct_talks_denial_only(iran_direct_denial))
s, tags = mod.score_item(iran_direct_denial, dt.datetime.now(mod.watch.KST))
check("oct07-iran-direct-denial-yellow", mod.final_color(iran_direct_denial) == "yellow")
check("oct07-iran-direct-denial-no-red-tags", "확전" not in tags and "확전위험" not in tags and "재확전위험" not in tags)
check("oct07-iran-direct-denial-topic", mod.topic_label(iran_direct_denial) == "이란·미국 · 직접협상 부인·간접접촉 구분")
check("oct07-iran-direct-denial-title", "전체 협상 결렬" in iran_direct_denial["title_ko"])

bad_direct_denial = """<b>전쟁·종전·재건 웹감시</b>
🔴 [신규] <b>1. 이란·미국</b>
이란 측 직접협상 부인
"""
mod.watch.ALERT.write_text(bad_direct_denial, encoding="utf-8")
try:
    mod.verify_alert(False)
    raise AssertionError("oct07-quality-gate-direct-denial")
except RuntimeError as e:
    check("oct07-quality-gate-direct-denial", "직접협상 부인" in str(e))


# 23) 구체적 신규 사건 없는 '사우디-후티 격화 + 미-이란 대화 지속' 종합기사는 별도 속보로 보내지 않는다.
regional_recap = row(
    '사우디-후티 충돌 격화…"미-이란 대화 지속"',
    source="OBS경인TV",
    description="사우디-후티 충돌과 미-이란 외교 상황을 함께 정리한 지역 종합 기사.",
    link="https://news.google.com/rss/articles/obs-regional-recap",
)
check("oct07-regional-recap-detected", mod._regional_recap_without_discrete_event(regional_recap))
s, tags = mod.score_item(regional_recap, dt.datetime.now(mod.watch.KST))
check("oct07-regional-recap-suppressed", s == 0 and tags == [])


# 24) 최종 fail-closed 품질게이트: 번역 placeholder·미확정 빨강·동일 원문 중복을 차단한다.
bad_placeholder = """<b>전쟁·종전·재건 웹감시</b>
[신규] <b>1. 네팔</b>
영문 기사 번역이 일시적으로 지연됨 — 원문 확인 필요
07:50 KST · 9분 전 · 재건
"""
mod.watch.ALERT.write_text(bad_placeholder, encoding="utf-8")
try:
    mod.verify_alert(False)
    raise AssertionError("oct07-quality-gate-translation-placeholder")
except RuntimeError as e:
    check("oct07-quality-gate-translation-placeholder", "번역 실패" in str(e))

bad_uncertain_red = """<b>전쟁·종전·재건 웹감시</b>
🔴 [속보] <b>1. 중동</b>
복수 폭발음 — 원인 미확정, 공격 주체 공식 확인 전
07:50 KST · 9분 전
"""
mod.watch.ALERT.write_text(bad_uncertain_red, encoding="utf-8")
try:
    mod.verify_alert(False)
    raise AssertionError("oct07-quality-gate-uncertain-red")
except RuntimeError as e:
    check("oct07-quality-gate-uncertain-red", "확인 수준이 미확정" in str(e))

bad_duplicate_url = """<b>전쟁·종전·재건 웹감시</b>
🔴 [신규] <b>1. 예멘</b>
첫 보도
<a href="https://example.com/same">매체A 원문</a>
🔴 [신규] <b>2. 예멘</b>
재보도
<a href="https://example.com/same">매체A 원문</a>
"""
mod.watch.ALERT.write_text(bad_duplicate_url, encoding="utf-8")
try:
    mod.verify_alert(False)
    raise AssertionError("oct07-quality-gate-duplicate-url")
except RuntimeError as e:
    check("oct07-quality-gate-duplicate-url", "동일 원문 URL" in str(e))


# 25) 트럼프 10/8 이란 공격 유예 발언: 매체별 문구 차이에도 단일 사건.
trump_cnbc = row(
    "Trump says U.S. will not attack Iran before midterm election",
    source="CNBC",
    description="The president ruled out an Iran strike before Nov. 3 midterms, while talks continue.",
    link="https://www.cnbc.com/2026/10/08/iran-war-trump-midterm-election.html",
)
trump_reuters = row(
    "Trump says US will not attack Iran before midterm elections in November",
    source="Reuters",
    description="The blockade of Iran remains in full effect and talks are ongoing.",
    link="https://www.reuters.com/world/trump-us-having-productive-talks-with-iran-will-not-attack-before-us-elections-2026-10-08/",
)
trump_ap = row(
    "Trump says US will not resume military strikes on Iran before the Nov. 3 midterm elections",
    source="Associated Press",
    description="The president's no-strike pledge is not a ceasefire agreement.",
    link="https://apnews.com/article/trump-iran-midterm",
)
trump_official = row(
    "Donald J. Trump statement on Iran",
    source="Truth Social",
    description="We will not be attacking Iran at any time prior to the Midterm Elections to be held in the United States on November 3rd.",
    link="https://truthsocial.com/@realDonaldTrump/117406186276133332",
)
for name, case in (("cnbc",trump_cnbc),("reuters",trump_reuters),("ap",trump_ap),("official",trump_official)):
    check("oct08-iran-midterm-pledge-detected-"+name, mod._trump_iran_midterm_no_strike(case))
check("oct08-iran-midterm-pledge-single-id", len({mod.item_id(x) for x in (trump_cnbc,trump_reuters,trump_ap,trump_official)}) == 1)
check("oct08-iran-midterm-pledge-topic", mod.topic_label(trump_cnbc) == "미국·이란 · 11월 3일 전 추가공격 유예 발언")
score, tags = mod.score_item(trump_cnbc, dt.datetime.now(mod.watch.KST))
check("oct08-iran-midterm-pledge-yellow", score == 100 and mod.final_color(trump_cnbc) == "yellow")
check("oct08-iran-midterm-pledge-not-ceasefire", "휴전·평화" not in tags and "확전" not in tags and "봉쇄유지" in tags and "휴전미확정" in tags)
check("oct08-iran-midterm-pledge-has-constraints", "봉쇄 유지" in trump_cnbc["title_ko"] and "휴전 합의 미확정" in trump_cnbc["title_ko"])
trump_cnbc["score"],trump_cnbc["tags"],trump_cnbc["age"] = score,tags,mod.watch.age_minutes(trump_cnbc,dt.datetime.now(mod.watch.KST))
rendered_pledge = mod.watch.build_alert([trump_cnbc], [], dt.datetime.now(mod.watch.KST))
check("oct08-iran-midterm-pledge-rendered-yellow", "🟡 [" in rendered_pledge and "미국·이란 · 11월 3일 전 추가공격 유예 발언" in rendered_pledge)
check("oct08-iran-midterm-pledge-not-green-header", "🟢 <b>재건·휴전</b>" not in rendered_pledge)
check("oct08-iran-midterm-pledge-not-nov4-attack", "11월 4일 공격 결정" not in rendered_pledge)

# 26) 기존 유예 발언을 배경으로 인용한 새 공격기사는 유예 신규발언으로 오탐하면 안 된다.
iran_actual_strike = row(
    "US launches strikes on Iran despite Trump pledge",
    source="Reuters",
    description="Trump said he would not attack Iran before the midterm elections on Nov. 3, but US forces attacked today.",
)
check("oct08-historical-pledge-not-current", not mod._trump_iran_midterm_no_strike(iran_actual_strike))
iran_gossip = row(
    "Trump may not attack Iran before elections",
    source="Random blog",
    description="Anonymous analysts guess there may be no action until Nov. 3.",
)
check("oct08-unsupported-rumor-not-pledge", not mod._trump_iran_midterm_no_strike(iran_gossip))
iran_talks_only = row(
    "Trump says US and Iran holding productive talks ahead of elections",
    source="Axios",
    description="No confirmed ceasefire or policy on attacks before Nov 3.",
)
check("oct08-talks-not-no-strike-pledge", not mod._trump_iran_midterm_no_strike(iran_talks_only))

after_election_pledge = row(
    "Trump says US will not attack Iran after midterm elections",
    source="Reuters",
    description="Analysts contrasted after-election language with the October 8 pledge.",
)
check("oct08-after-is-not-before", not mod._trump_iran_midterm_no_strike(after_election_pledge))
confusing_after = row(
    "Trump says US will not attack Iran after the midterm elections",
    source="Reuters",
    description="Background mentions the earlier pledge before Nov. 3.",
)
check("oct08-background-does-not-reverse-scope", not mod._trump_iran_midterm_no_strike(confusing_after))
future_now = dt.datetime(2026, 11, 5, 12, 0, tzinfo=mod.watch.KST)
post_election_reprint = row(
    "Trump says US will not attack Iran before midterm elections",
    source="Reuters",
    description="Historical review of the October 8 statement.",
)
post_election_reprint["published"] = format_datetime(future_now - dt.timedelta(minutes=10))
post_score, post_tags = mod.score_item(post_election_reprint, future_now)
check("oct08-pre-midterm-pledge-expires-after-election", post_score == 0 and post_tags == [])

reversal = row(
    "Trump reverses no-attack pledge on Iran ahead of midterms",
    source="Reuters",
    description="No actual military strike has occurred.",
)
# 제목에 중간선거가 있어도, 공격 유예의 철회는 공격 발생과 구분.
reversal["title_original"] = "Trump reverses no-attack pledge on Iran before midterm elections"
check("oct08-reversal-detected", mod._trump_iran_midterm_pledge_reversal(reversal))
check("oct08-reversal-not-pledge", not mod._trump_iran_midterm_no_strike(reversal))
score,tags = mod.score_item(reversal,dt.datetime.now(mod.watch.KST))
check("oct08-reversal-yellow-not-red", mod.final_color(reversal)=="yellow" and "실제공격미확인" in tags and "확전" not in tags)
check("oct08-reversal-separate-id", mod.item_id(reversal)!=mod.item_id(trump_cnbc))

old_pledge = row(
    "Trump says US will not attack Iran before midterm elections",
    source="Reuters",
    description="Before November 3rd",
    minutes_ago=190,
)
old_score,old_tags = mod.score_item(old_pledge, dt.datetime.now(mod.watch.KST))
check("oct08-pledge-stale-not-reborn", old_score == 0 and old_tags == [])

bad_pledge = """<b>전쟁·종전·재건 웹감시</b>
🔴 [신규] <b>1. 미국·이란 · 11월 3일 전 추가공격 유예 발언</b>
트럼프, 11월 3일 미국 중간선거 전 이란 추가 공격 없다고 발표 — 휴전 확정
"""
mod.watch.ALERT.write_text(bad_pledge,encoding="utf-8")
try:
    mod.verify_alert(False)
    raise AssertionError("oct08-pledge-quality-gate")
except RuntimeError as e:
    check("oct08-pledge-quality-gate", "공격유예" in str(e) or "봉쇄" in str(e))


# 27) 10/9 15:45 KST 실송출에 나타난 서로 다른 한국어 제목 3건의 동일 사건 검사.
# 이 세 원문을 독립 원발언이나 별도 군사행동으로 처리하면 안 된다.
observed_reprint_titles = [
    ("아주경제", "트럼프 중간선거 전 이란 공격 안 해…해상 봉쇄는 유지 - 아주경제"),
    ("아이뉴스24", '트럼프 "11월 중간선거 전에는 이란 공격 안 한다" - 아이뉴스24'),
    ("KBS 뉴스", "트럼프 “중간선거 전 이란 공격 안 할 것” - KBS 뉴스"),
    ("OBS경인TV", '트럼프 "중간선거 전까지 이란 공격 안 할 것" - OBS경인TV'),
]
observed_reprints = [
    row(t, source=src, description="트럼프가 선거 전에 이란을 공격하지 않겠다고 밝혔다.")
    for src, t in observed_reprint_titles
]
for i, x in enumerate(observed_reprints,1):
    check(f"oct09-korean-reprint-pledge-classified-{i}", mod._trump_iran_midterm_no_strike(x))
    score, tags = mod.score_item(x, dt.datetime.now(mod.watch.KST))
    check(f"oct09-korean-reprint-yellow-{i}", score == 100 and mod.final_color(x) == "yellow")
    check(f"oct09-korean-reprint-no-red-{i}", "확전" not in tags and "휴전·평화" not in tags)
check("oct09-observed-four-one-canonical-id", len({mod.item_id(x) for x in observed_reprints+[trump_cnbc,trump_reuters]}) == 1)
check("oct09-observed-four-one-selected-row",len({mod.item_id(x): x for x in observed_reprints}) == 1)

# 상위 경보 품질 게이트는 전송 전 동일 발언의 한국어 3중 재보도를 거부해야 한다.
bad_observed_reprints = """<b>전쟁·종전·재건 웹감시</b>
🔴 [신규] <b>1. 이란·호르무즈</b>
트럼프 “중간선거 전 이란 공격 없다”했지만···뒤에선 ‘3일 집중 공격’ 계획 준비 - 경향신문
[신규] <b>2. 이란·호르무즈</b>
트럼프 "11월 중간선거 전에는 이란 공격 안 한다" - 아이뉴스24
[신규] <b>3. 이란·호르무즈</b>
트럼프 “중간선거 전 이란 공격 안 할 것” - KBS 뉴스
"""
mod.watch.ALERT.write_text(bad_observed_reprints, encoding="utf-8")
try:
    mod.verify_alert(False)
    raise AssertionError("oct09-quality-gate-duplicate-midterm-policy")
except RuntimeError as err:
    check("oct09-quality-gate-duplicate-midterm-policy", "같은 10월 8일" in str(err) or "중복 정책" in str(err))


# 28) CBS 10/7 새로운 영상은 전쟁 개전 초기(7개월 전) 쿠웨이트 기지 공습.
# 10/9 Vietnam.vn 재인용을 '방금 새로운 군사공격'으로 오인하면 안 된다.
kuwait_recapture = row(
    "Iranian attacks forced US troops to abandon major base in Kuwait",
    source="Vietnam.vn",
    description="Newly obtained footage by CBS News shows attacks on Camp Buehring during the opening days of the Iran war seven months ago.",
    minutes_ago=10,
)
check("oct09-kuwait-historical-cbs-detected", mod._historical_kuwait_base_footage(kuwait_recapture))
score,tags = mod.score_item(kuwait_recapture,dt.datetime.now(mod.watch.KST))
check("oct09-kuwait-historical-not-new-red", score == 0 and tags == [])
kuwait_short_reprint = row(
    "Iranian attacks forced US troops to abandon major base in Kuwait",
    source="Vietnam.vn",
    description="American soldiers said Iranian attacks forced evacuation.",
    minutes_ago=10,
)
check("oct09-kuwait-20261009-short-reprint-detected", mod._historical_kuwait_base_footage(kuwait_short_reprint))
kuwait_new_attack = row(
    "New Iranian missile attack on Kuwait military base today",
    source="Reuters",
    description="Fresh new attack on a military base in Kuwait on October 9.",
)
check("oct09-kuwait-fresh-attack-not-suppressed", not mod._historical_kuwait_base_footage(kuwait_new_attack))


# 29) Reuters 표준 제목은 제목에 'Iran'을 쓰지 않아도 본문이 이란을 명시한다.
reuters_short_headline = row(
    "Trump says he will not attack before US elections in November",
    source="Reuters",
    description="The United States is holding productive discussions with Iran while maintaining a blockade of Iranian ports.",
)
check("oct08-reuters-implicit-iran-detected",mod._trump_iran_midterm_no_strike(reuters_short_headline))
check("oct08-reuters-implicit-iran-same-id",mod.item_id(reuters_short_headline)==mod.item_id(trump_cnbc))
unrelated_reuters_short = row(
    "Trump says he will not attack before US elections in November",
    source="Reuters",
    description="General political remarks without a named country.",
)
check("oct08-no-iran-subject-no-trigger",not mod._trump_iran_midterm_no_strike(unrelated_reuters_short))


# 30) Run #424 실전 출력: OBS경인TV가 같은 발언을 신규 별도 기사로 송출했음.
obs_oct09_reprint = row(
    '트럼프 "중간선거 전까지 이란 공격 안 할 것" - OBS경인TV',
    source="OBS경인TV",
    description="트럼프 대통령이 11월 3일 전까지 이란을 공격하지 않겠다고 밝혔다.",
    minutes_ago=8,
)
check("oct09-obs-pledge-classified", mod._trump_iran_midterm_no_strike(obs_oct09_reprint))
check("oct09-obs-single-policy-id",mod.item_id(obs_oct09_reprint)==mod.item_id(trump_cnbc))
score,tags=mod.score_item(obs_oct09_reprint,dt.datetime.now(mod.watch.KST))
check("oct09-obs-yellow-no-military-escalation",score==100 and mod.final_color(obs_oct09_reprint)=="yellow" and "확전" not in tags)

anonymous_pledge_reprint = row(
    '트럼프 "중간선거 전까지 이란 공격 안 할 것"',
    source="불명확한 개인 블로그",
    description="트럼프의 10월 8일 이란 관련 발언을 재인용",
    minutes_ago=8,
)
check("oct09-untrusted-lexical-reprint-recognized",mod._trump_iran_midterm_no_strike(anonymous_pledge_reprint,trust_required=False))
check("oct09-untrusted-not-confirmed-policy",not mod._trump_iran_midterm_no_strike(anonymous_pledge_reprint))
score,tags=mod.score_item(anonymous_pledge_reprint,dt.datetime.now(mod.watch.KST))
check("oct09-untrusted-not-reemitted-as-war",score==0 and tags==[])


# 30) 실제 10/9 실패: 대통령 유예발언과 국방부 '3일 집중공격 계획'은 별개.
# 같은 정책 재보도(OBS·아주경제 등)는 출처·제목이 달라도 하나의 식별자.
oct09_aju = row(
    "트럼프 중간선거 전 이란 공격 안 해…해상 봉쇄는 유지 - 아주경제",
    source="아주경제",
    description="트럼프가 11월 3일 중간선거 전에는 공격을 하지 않겠다고 말했다.",
)
oct09_obs = row(
    '트럼프 "중간선거 전까지 이란 공격 안 할 것" - OBS경인TV',
    source="OBS경인TV",
    description="Trump says no Iran strike before the midterm vote",
)
oct09_kyunghyang_plan = row(
    "트럼프 “중간선거 전 이란 공격 없다”했지만···뒤에선 ‘3일 집중 공격’ 계획 준비 - 경향신문",
    source="경향신문",
    description="미 국방부가 검토한 3일 집중공격 계획과 트럼프의 선거 전 공격 보류 발언은 서로 다른 단계.",
)
oct09_yonhap_plan = row(
    '"美국방부, 이란 \'3일 집중공격\' 계획 수립…트럼프 일단 제동" - 연합뉴스',
    source="연합뉴스",
    description="작전 방안을 마련했으나 대통령의 최종 승인과 실제 공격 명령은 확인되지 않았다.",
)
oct09_nyt_plan = row(
    "Pentagon prepares three-day intensive Iran strike option as Trump says no attack before midterms",
    source="New York Times",
    description="The Pentagon examined strike options but the president has not approved an attack.",
)
for label, x in (("aju",oct09_aju),("obs",oct09_obs)):
    check("oct09-confirmed-pledge-"+label, mod._trump_iran_midterm_no_strike(x))
    check("oct09-confirmed-pledge-canonical-"+label, mod.item_id(x)==mod.item_id(trump_cnbc))
for label, x in (("kyunghyang",oct09_kyunghyang_plan),("yonhap",oct09_yonhap_plan),("nyt",oct09_nyt_plan)):
    check("oct09-three-day-plan-"+label, mod._iran_three_day_strike_plan(x))
    check("oct09-three-day-not-pledge-"+label, not mod._trump_iran_midterm_no_strike(x))
    check("oct09-three-day-unique-canonical-"+label, mod.item_id(x)==mod.item_id(oct09_kyunghyang_plan))
    score,tags = mod.score_item(x, dt.datetime.now(mod.watch.KST))
    check("oct09-three-day-yellow-"+label, mod.final_color(x)=="yellow" and "승인미확정" in tags and "확전" not in tags)
check("oct09-plan-distinct-from-pledge",mod.item_id(oct09_kyunghyang_plan)!=mod.item_id(oct09_aju))

# 실제 수집 경로처럼 점수 계산 전에 ID를 만들고, 중복 항목을 묶은 후 번역한다.
items_by_id = {}
now_replay = dt.datetime.now(mod.watch.KST)
for case in (oct09_kyunghyang_plan, oct09_aju, oct09_obs, oct09_yonhap_plan, oct09_nyt_plan):
    iid = mod.item_id(case)
    score,tags = mod.score_item(case,now_replay)
    case.update({"id":iid,"score":score,"tags":tags,"age":mod.watch.age_minutes(case,now_replay)})
    case["title_ko"] = mod.watch.translate_ko(case["title_original"])
    items_by_id.setdefault(iid,case)
check("oct09-replay-two-distinct-events",len(items_by_id)==2)
replay_render = mod.watch.build_alert(list(items_by_id.values()),[],now_replay)
check("oct09-replay-pledge-once",replay_render.count("11월 3일 전 추가공격 유예 발언")==1)
check("oct09-replay-plan-once",replay_render.count("3일 집중공격 계획 보도")==1)
mod.watch.ALERT.write_text(replay_render,encoding="utf-8")
mod.verify_alert(False)
check("oct09-replay-quality-gate-accepts-distinct-events",True)

print("WAR_PEACE_OCT04_REGRESSION_OK")
