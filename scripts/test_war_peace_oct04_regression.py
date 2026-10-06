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

print("WAR_PEACE_OCT04_REGRESSION_OK")
