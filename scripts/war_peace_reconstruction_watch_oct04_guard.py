#!/usr/bin/env python3
"""2026-10-04 전쟁 감시 최종 의미·중복·출처 귀속 게이트.

기존 수집/상태/Telegram 경로는 그대로 두고 마지막 판정층만 보강한다.
"""
from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import re
import urllib.parse

import war_peace_reconstruction_watch_diplomacy_flash as prev

watch = prev.watch
runner = prev.runner
base = prev.base
guard = prev.guard

_orig_emergency_marks = prev._emergency_marks
_orig_marks = prev._marks
_orig_korean_title = prev._korean_title
_orig_signals = prev._signals
_orig_score_item = watch.score_item
_orig_item_id = watch.item_id
_orig_topic_label = watch.topic_label
_orig_final_color = prev._final_item_color
_orig_verdict = guard._verdict
_orig_semantic_fix = prev._semantic_output_fix
_orig_verify_alert = runner.verify_alert
_orig_translate_ko = watch.translate_ko


def translate_ko(title):
    """출처 귀속이 의미의 일부인 제목은 번역 단계에서 귀속 문구를 보존한다."""
    raw = str(title or "")
    low = raw.lower()
    if (
        ("drones strike two ships" in low and "bulgaria" in low and "black sea" in low)
        or ("drone sinks ship off bulgaria" in low)
    ):
        return "불가리아 흑해 경제수역에서 드론 공격으로 상선 2척 피격, 이 중 1척 침몰 — 공격 주체는 공식 확인 전"
    if (
        "israel" in low
        and any(x in low for x in ("oct. 7", "oct 7", "october 7", "10월 7일"))
        and any(x in low for x in ("attack risk abroad", "attacks abroad", "terror threat", "terror risk", "해외 공격 위험", "해외 테러"))
        and any(x in low for x in ("anniversary", "주년"))
    ):
        return "이스라엘 국가안보회의, 10월 7일 3주년 전후 해외의 이스라엘인·유대인 대상 공격 위험 증가 경고 — 실제 공격 발생 아님"
    if (
        any(x in low for x in ("iran army", "iran amry", "이란군"))
        and any(x in low for x in ("preemptive attack", "preemptive strike", "선제 공격", "선제공격"))
        and any(x in low for x in ("if necessary", "if needed", "necessary", "필요한 경우", "필요시"))
    ):
        return "이란군, 필요할 경우 선제공격에 나설 수 있다고 경고 — 실제 공격 발생이 아닌 조건부 군사위협"
    if (
        "tanker crew rescued in black sea" in low
        and "attack set ship ablaze" in low
    ):
        return "러시아 교통부, 흑해에서 무인수상정 공격으로 화재가 난 유조선 승무원 23명 전원 구조됐다고 발표"
    if (
        ("iran must" in low or "iran" in low)
        and "enrichment" in low
        and any(x in low for x in ("vice president", "jd vance", "vance"))
        and any(x in low for x in ("end war", "end the war", "ending the war"))
    ):
        return "미국 부통령 JD Vance, 이란이 전쟁 종식을 원하면 우라늄 농축 능력을 의미 있게 감축해야 한다고 제시 — 미국 측 협상 조건, 합의 진전 아님"
    if (
        any(x in low for x in ("saudi-led coalition", "saudi coalition", "사우디 주도 연합군"))
        and any(x in low for x in ("riyadh", "리야드"))
        and any(x in low for x in ("intercepted", "intercept", "destroyed", "요격"))
        and any(x in low for x in ("houthi", "후티"))
    ):
        return "사우디 주도 연합군, 리야드 북쪽 상공서 후티 탄도미사일 요격 확인 — 후티의 리야드 공항 등 타격 주장은 사우디 확인 전"
    if (
        any(x in low for x in ("houthi", "후티"))
        and any(x in low for x in ("saudi", "사우디"))
        and any(x in low for x in ("rabigh", "라빅"))
        and any(x in low for x in ("refinery", "정유시설", "aramco", "아람코"))
    ):
        return "후티의 사우디 공항·라빅 Aramco 정유시설 공격 보도 — 공항 피해는 사우디 확인, 라빅 정유시설은 후티 주장 단계"
    if (
        ("tass calculations" in low or "tass calculation" in low)
        and "drone" in low and "2026" in low
    ):
        return "TASS 집계: 러시아가 2026년 최대 규모급 드론 공격을 받았다고 보도 — 세부 규모·피해는 독립 확인 필요"
    if (
        "russian" in low and ("poltava" in low or "odessa" in low or "odesa" in low)
        and ("radar" in low or "data center" in low)
        and any(x in low for x in ("hit", "strike", "struck", "attacked"))
    ):
        return "TASS: 러시아 국방부는 폴타바·오데사 등에서 우크라이나군 레이더·데이터센터를 타격했다고 주장 — 독립 확인 전"
    return _orig_translate_ko(raw)


watch.translate_ko = translate_ko


def _title(row):
    return prev._display_title_text(row)


def _text(row):
    return prev._text(row)


def _published_day(row):
    try:
        pub = watch.parse_pub(row.get("published", ""))
        if pub:
            return pub.astimezone(watch.KST).date().isoformat()
    except Exception:
        pass
    return dt.datetime.now(watch.KST).date().isoformat()


def _week_key():
    iso = dt.datetime.now(watch.KST).isocalendar()
    return f"{iso.year}-W{iso.week:02d}"


def _future_refinery_policy(row):
    # 원제목뿐 아니라 검색 스니펫/본문에 미래형 공격 방침이 있으면 잡는다.
    # 다만 이미 발생한 피격·화재와 구분하기 위해 '향후/계획/예고' 동사가 반드시 필요하다.
    t = _text(row)
    future = any(x in t for x in (
        "will hit", "will strike", "will attack", "plans to strike", "plans to attack",
        "double down on attacking", "vows to strike", "vows to attack",
        "will keep hitting", "will continue hitting", "will intensify strikes",
        "공격하겠다", "타격하겠다", "공격할 것", "타격할 것",
        "공격 확대", "타격 확대", "공격 늘리", "공격을 늘리", "보복 공격 예고",
        "공격을 강화", "타격을 강화", "계속 공격", "계속 타격",
    ))
    target = any(x in t for x in ("refinery", "refineries", "oil refinery", "정유소", "정유시설", "정유 공장"))
    actual_now = any(x in _title(row) for x in (
        "refinery hit", "refinery struck", "refinery attacked", "refinery fire",
        "정유시설 피격", "정유소 피격", "정유시설 화재", "정유소 화재",
    ))
    return future and target and not actual_now


def _aramco_houthi_claim(row):
    title = _title(row)
    text = _text(row)
    aramco_riyadh = (
        any(x in text for x in ("aramco", "아람코"))
        and any(x in text for x in ("riyadh", "리야드"))
    )
    houthi = any(x in text for x in ("houthi", "houthis", "ansar allah", "후티", "안사르 알라", "안사르알라"))
    attack = any(x in text for x in (
        "say they attacked", "says it attacked", "said it attacked", "claimed responsibility",
        "claimed it attacked", "targeted aramco", "attacked aramco",
        "공격했다고 밝혔다", "공격했다고 주장", "공격 주장", "공격했다며",
    ))
    weapon = any(x in text for x in (
        "ballistic missile", "ballistic missiles", "missile", "missiles", "drone", "drones",
        "탄도미사일", "미사일", "드론",
    ))
    return aramco_riyadh and houthi and attack and weapon


def _aramco_fire_unattributed(row):
    title = _title(row)
    text = _text(row)
    core = (
        any(x in title for x in ("aramco", "아람코"))
        and any(x in title for x in ("riyadh", "리야드"))
        and any(x in title for x in ("fire", "smoke", "blaze", "화재", "연기"))
    )
    explicit = any(x in title for x in (
        "missile attack", "drone attack", "attacked by", "strike on", "struck by",
        "미사일 공격", "드론 공격", "공격받", "피격", "공습",
    ))
    uncertain = any(x in text for x in (
        "no immediate claim of responsibility", "no claim of responsibility",
        "no immediate confirmation", "cause was not immediately known",
        "원인 미확정", "배후 미확정", "공격 주체 미확정", "공식 확인 전",
    ))
    return core and not explicit and uncertain and not _aramco_houthi_claim(row)


def _peace_conditions_commentary(row):
    t = _title(row)
    peace = any(x in t for x in (
        "conditions for peace", "peace conditions", "conditions for a peaceful solution",
        "terms for peace", "종전 조건", "평화 조건", "평화적 해결 조건",
    ))
    speaker = any(x in t for x in (
        "medvedev", "comments on", "commented on", "outlined", "names conditions",
        "메드베데프", "논평", "조건을 제시", "조건 제시",
    ))
    return peace and speaker


def _lukoil_side_deal(row):
    title = _title(row)
    text = _text(row)
    commercial = any(x in text for x in (
        "lukoil", "루코일", "oil deal", "big deal", "asset sale",
        "sale of overseas assets", "overseas asset sale", "해외자산 매각",
        "해외 자산 매각", "석유업체 빅딜", "석유 업체 빅딜", "자산 거래",
    ))
    talks = any(x in text for x in (
        "peace talks", "ukraine talks", "ceasefire talks", "종전 협상", "휴전 협상", "우크라 종전",
    ))
    title_hint = any(x in title for x in ("석유업체 빅딜", "oil deal", "lukoil", "루코일"))
    return commercial and talks and title_hint


def _hormuz_tanker_attack(row):
    title = _title(row)
    text = _text(row)
    hormuz = any(x in text for x in ("hormuz", "호르무즈"))
    tanker = any(x in text for x in ("tanker", "tankers", "crude oil tanker", "유조선"))
    hit = any(x in text for x in (
        "struck by an unknown projectile", "struck by unknown projectile", "hit by an unknown projectile",
        "tanker struck", "tankers struck", "attacked", "attack on tanker",
        "피격", "정체불명 발사체", "미확인 발사체", "유조선 공격",
    ))
    title_hit = any(x in title for x in (
        "tanker struck", "tankers struck", "tanker hit", "tankers hit", "tanker attack",
        "유조선 피격", "유조선 공격", "유조선 잇달아 피격", "유조선 2척 피격",
    ))
    recent = any(x in text for x in ("ukmto", "past 24 hours", "last 24 hours", "지난 24시간", "하루 새"))
    return hormuz and tanker and hit and (title_hit or recent)


def _kyiv_bridge_attack(row):
    t = _title(row)
    kyiv = any(x in t for x in ("kyiv", "kiev", "키이우", "키예프"))
    bridge = any(x in t for x in ("bridge", "bridges", "교량", "다리"))
    strike = any(x in t for x in (
        "strikes on", "attacks on", "bridge attack", "bridge strikes",
        "공격", "공습", "피격",
    ))
    return kyiv and bridge and strike


def _kyiv_evacuation_strike_warning(row):
    t = _title(row)
    kyiv = any(x in t for x in ("kyiv", "kiev", "키이우", "키예프"))
    leave = any(x in t for x in ("leave kyiv", "leave kiev", "evacuate", "evacuation", "떠나라", "대피"))
    threat = any(x in _text(row) for x in (
        "massive retaliatory strikes", "massive strikes", "mortal danger",
        "대규모 보복 공격", "대규모 공격", "최후통첩", "위험",
    ))
    return kyiv and leave and threat


def _new_tanker_attack_variant(row):
    t = _title(row)
    return any(x in t for x in ("another tanker", "additional tanker", "fourth tanker", "fifth tanker", "추가 유조선", "또 다른 유조선", "4번째 유조선", "5번째 유조선"))


def _hormuz_on_peace_attack(row):
    t = _text(row).lower()
    hormuz = any(x in t for x in ("hormuz", "호르무즈"))
    vessel = any(x in t for x in ("mt on peace", "on peace", "온 피스", "온피스"))
    panama_12 = (
        any(x in t for x in ("panama-flagged", "panama flagged", "파나마 선적", "파나마 국적", "파나마"))
        and any(x in t for x in ("12 crew", "12 seafarers", "12 injured", "12명 부상", "12명이 부상"))
    )
    strike = any(x in t for x in (
        "struck by a projectile", "hit by a projectile", "projectile struck", "tanker attacked",
        "피격", "공격", "발사체",
    ))
    return hormuz and strike and (vessel or panama_12)


def _iran_south_unattributed_explosions(row):
    t = _text(row).lower()
    south = any(x in t for x in (
        "sirik", "qeshm", "keshm", "minab", "hormozgan",
        "시리크", "게슘", "케슘", "미나브", "호르무즈간",
    ))
    explosion = any(x in t for x in ("explosion", "explosions", "blast", "blasts", "폭발", "폭발음"))
    explicit_attack = any(x in t for x in (
        "hostile projectile", "enemy attack", "air strike", "airstrike",
        "missile strike", "drone strike", "projectile hit", "projectiles hit",
        "적의 공격", "공습", "미사일 공격", "드론 공격", "발사체 피격", "발사체가 타격",
    ))
    attack_explicitly_unconfirmed = any(x in t for x in (
        "no hostile projectile", "no projectile strike", "no airstrike",
        "no hostile projectile or airstrike", "projectile or airstrike was officially confirmed",
        "발사체·공습 확인 여부", "발사체 피격 확인 전", "공습 확인 전",
        "원인 미확정 단계",
    ))
    return south and explosion and (attack_explicitly_unconfirmed or not explicit_attack)


def _saudi_east_west_pipeline_recovery(row):
    t = _text(row).lower()
    east_west = any(x in t for x in (
        "east-west pipeline", "east west pipeline", "petroline",
        "동서 송유관", "동-서 송유관", "동서 파이프라인",
    ))
    volume = any(x in t for x in ("5.8 million", "5.8m", "580만", "5,800,000"))
    recovery = any(x in t for x in (
        "resumed", "restarted", "restart", "recovered", "recovery", "flow remains uninterrupted",
        "재가동", "수송 회복", "운송 회복", "흐름 회복", "가동 재개",
    ))
    return east_west and volume and recovery


def _south_korea_russia_fuel_background(row):
    src = " ".join([str(row.get("link", "")), str(row.get("resolved_url", ""))]).lower()
    t = _text(row).lower()
    if "south-korea-exports-eased-russia-fuel-crisis-caused-by-drone-strikes-ukraine-2026-10-06" in src:
        return True
    return (
        any(x in t for x in ("south korea exports", "south korean exports", "한국 수출"))
        and any(x in t for x in ("russia fuel crisis", "russian fuel crisis", "러시아 연료 위기"))
        and any(x in t for x in ("july and august", "7월", "8월", "176,000", "176000"))
    )


def _israel_oct7_abroad_warning(row):
    t = _text(row).lower()
    israel = any(x in t for x in ("israel", "israeli", "이스라엘"))
    anniversary = (
        any(x in t for x in ("oct. 7", "oct 7", "october 7", "10월 7일"))
        and any(x in t for x in ("anniversary", "주년"))
    )
    warning = any(x in t for x in (
        "warns of attack risk abroad", "warns of attacks abroad", "attack risk abroad",
        "terror threat abroad", "terror risk abroad", "heightened terror threat",
        "해외 공격 위험", "해외 테러 위험", "공격 위험 경고",
    ))
    actual = any(x in t for x in (
        "attack occurred", "attacked today", "was attacked", "were attacked",
        "explosion killed", "casualties reported", "공격이 발생", "실제 공격",
        "피격됐다", "폭발로 사망", "사상자 발생",
    ))
    return israel and anniversary and warning and not actual


def _conditional_military_threat(row):
    """조건부·미래형 군사위협을 실제 공격과 분리한다."""
    t = _text(row).lower()
    military = any(x in t for x in (
        "army", "military", "armed forces", "군", "군대", "군부",
    ))
    threat = any(x in t for x in (
        "preemptive attack", "preemptive strike", "launch a preemptive", "start a preemptive",
        "선제 공격", "선제공격", "선제 타격", "선제타격",
    ))
    conditional = any(x in t for x in (
        "if necessary", "if needed", "if required", "when necessary", "could launch", "may launch",
        "필요한 경우", "필요할 경우", "필요시", "필요하면", "할 수 있다", "나설 수",
    ))
    actual = any(x in t for x in (
        "launched a preemptive attack", "carried out a preemptive strike", "struck today",
        "공격을 개시했다", "선제 공격을 감행", "선제타격을 실시", "실제 공격",
    ))
    return military and threat and conditional and not actual


def _non_concrete_endgame_rhetoric(row):
    """종전이 임박했다는 전망·평가를 실제 휴전/협상 진전과 분리한다."""
    t = _text(row).lower()
    theater = any(x in t for x in (
        "ukraine", "russia", "iran", "israel", "gaza", "yemen",
        "우크라이나", "러시아", "이란", "이스라엘", "가자", "예멘",
    ))
    rhetoric = any(x in t for x in (
        "nearing its end", "nearly over", "almost over", "peace is getting closer",
        "peace getting closer", "end is near", "could end soon", "will end soon",
        "believes the conflict", "thinks the conflict", "expects the war",
        "분쟁이 거의 끝", "전쟁이 거의 끝", "종전이 가까워", "평화가 가까워",
        "곧 끝날 것", "끝이 가까워",
    ))
    concrete = any(x in t for x in (
        "ceasefire agreement signed", "peace agreement signed", "signed ceasefire",
        "talks resumed", "negotiations resumed", "meeting date set", "summit date set",
        "휴전 합의 체결", "평화협정 체결", "협상 재개", "회담 재개",
        "회담 날짜 확정", "정상회담 날짜 확정",
    ))
    return theater and rhetoric and not concrete


def _trump_ukraine_peace_rhetoric(row):
    """전망·수사성 종전 발언을 실제 협상 진전과 분리한다."""
    src = " ".join([str(row.get("source", "")), str(row.get("link", "")), str(row.get("resolved_url", ""))]).lower()
    t = _text(row).lower()
    exact = "2198491" in src
    trump = any(x in t for x in ("trump", "트럼프"))
    ukraine = any(x in t for x in ("ukraine", "russia-ukraine", "우크라이나", "러시아-우크라이나"))
    rhetoric = any(x in t for x in (
        "believes the conflict is almost over", "conflict is almost over",
        "peace is getting closer", "peace is actually getting closer",
        "nearing its end", "almost over", "분쟁이 거의 끝", "평화가 가까워", "종전이 가까워",
    ))
    concrete = any(x in t for x in (
        "signed agreement", "ceasefire agreement signed", "official ceasefire",
        "합의문 서명", "휴전 합의 체결", "공식 휴전",
    ))
    return (exact or (trump and ukraine and rhetoric)) and not concrete


def _vance_iran_enrichment_condition(row):
    src = " ".join([str(row.get("source", "")), str(row.get("link", "")), str(row.get("resolved_url", ""))]).lower()
    t = _text(row).lower()
    exact = "2198519" in src
    iran = any(x in t for x in ("iran", "iranian", "이란"))
    enrichment = any(x in t for x in ("enrichment", "uranium enrichment", "농축", "우라늄 농축"))
    vp = any(x in t for x in ("jd vance", "vance", "vice president", "미국 부통령", "밴스"))
    end_war = any(x in t for x in ("end war", "end the war", "ending the war", "전쟁 종식", "전쟁을 끝", "종전"))
    return (exact or (iran and enrichment and vp and end_war))


def _saudi_riyadh_intercept_vs_claim(row):
    t = _text(row).lower()
    saudi = any(x in t for x in ("saudi", "사우디"))
    houthi = any(x in t for x in ("houthi", "houthis", "후티"))
    riyadh = any(x in t for x in ("riyadh", "리야드"))
    intercept = any(x in t for x in (
        "intercepted", "intercept", "destroyed north of riyadh", "north of riyadh",
        "요격", "격추", "리야드 북쪽", "리야드 북부",
    ))
    missile = any(x in t for x in ("ballistic missile", "missile", "탄도미사일", "미사일"))
    claimed_target = any(x in t for x in (
        "king khalid", "king khalid international airport", "킹칼리드", "킹 칼리드",
        "claimed", "claims", "주장",
    ))
    return saudi and houthi and riyadh and intercept and missile and claimed_target


def _tass_turkmenistan_visit_noise(row):
    src = " ".join([str(row.get("source", "")), str(row.get("link", ""))]).lower()
    t = _text(row).lower()
    if "tass.com/politics/2198439" in src:
        return True
    return (
        "tass" in src
        and "turkmenistan" in t
        and "cis summit" in t
        and "caspian" in t
        and any(x in t for x in ("pezeshkian", "페제쉬키안"))
    )


def _saudi_houthi_airport_refinery_cluster(row):
    t = _text(row).lower()
    corrected = str(row.get("title_ko", "")).lower()
    if "공항 피해는 사우디 확인" in corrected and "라빅" in corrected and "후티 주장 단계" in corrected:
        return True
    saudi = any(x in t for x in ("saudi", "사우디"))
    houthi = any(x in t for x in ("houthi", "houthis", "후티"))
    attack = any(x in t for x in (
        "attack", "attacked", "strike", "struck", "missile", "drone",
        "공격", "공습", "피격", "미사일", "드론",
    ))
    airport = any(x in t for x in ("airport", "airports", "공항"))
    refinery = any(x in t for x in ("refinery", "aramco", "rabigh", "정유시설", "정유소", "아람코", "라빅"))
    airport_damage = airport and any(x in t for x in (
        "two airports", "2 airports", "damage", "damaged", "injured",
        "공항 두 곳", "공항 2곳", "피해", "부상",
    ))
    named_targets = any(x in t for x in ("jazan", "najran", "riyadh", "rabigh", "자잔", "나지란", "리야드", "라빅"))
    return saudi and houthi and attack and ((airport and refinery) or airport_damage or (airport and named_targets))


def _aden_airport_attack_cluster(row):
    """같은 아덴 국제공항 탄도미사일·드론 공격의 매체별 재보도를 하나로 묶는다."""
    t = _text(row).lower()
    aden = any(x in t for x in ("aden", "아덴"))
    airport = any(x in t for x in ("international airport", "airport", "국제공항", "공항"))
    houthi = any(x in t for x in ("houthi", "houthis", "후티"))
    attack = any(x in t for x in (
        "ballistic missile", "missile", "drone", "attack", "attacked", "strike", "struck",
        "탄도미사일", "미사일", "드론", "공격", "공습", "피격",
    ))
    return aden and airport and houthi and attack


def _new_saudi_houthi_attack_variant(row):
    t = _text(row).lower()
    return any(x in t for x in (
        "another attack", "new attack", "additional attack", "another strike", "new strike",
        "again attacked", "second wave", "또다시 공격", "추가 공격", "새 공격", "2차 공습",
    ))


def _cluster_day(row, shift_hours=6):
    try:
        pub = watch.parse_pub(row.get("published", ""))
        if pub:
            return (pub.astimezone(watch.KST) - dt.timedelta(hours=shift_hours)).date().isoformat()
    except Exception:
        pass
    return (dt.datetime.now(watch.KST) - dt.timedelta(hours=shift_hours)).date().isoformat()


def _trump_la_sd_hypothetical(row):
    """정치 연설의 가정적 수사를 실제 군사 신규 변화로 올리지 않는다."""
    t = _text(row)
    trump = any(x in t for x in ("trump", "트럼프"))
    cities = (
        any(x in t for x in ("los angeles", "로스앤젤레스", "la "))
        and any(x in t for x in ("san diego", "샌디에이고"))
    )
    rhetoric = any(x in t for x in (
        "let them take out los angeles", "let 'em take out los angeles",
        "let them take out san diego", "let 'em take out san diego",
        "small price to pay", "파괴될 수도 있다", "공격하도록 내버려",
        "작은 대가", "작은 대가를 치를",
    ))
    concrete = any(x in t for x in (
        "missile launched at los angeles", "missile launched at san diego",
        "attack on los angeles", "attack on san diego",
        "credible intelligence", "specific threat", "미사일 발사", "실제 공격",
        "구체적 위협", "신뢰할 만한 정보",
    ))
    return trump and cities and rhetoric and not concrete


def _mokha_counteroffensive_context(row):
    """후티의 과거 목하 점령을 현재 사실로 재생산하지 않고 현재 반격을 잡는다."""
    t = _text(row)
    mokha = any(x in t for x in ("mokha", "mocha", "al-makha", "목하", "모카"))
    houthi = any(x in t for x in ("houthi", "houthis", "후티"))
    current = any(x in t for x in (
        "counteroffensive", "counter-offensive", "reclaim", "recapture", "retake",
        "expel", "free bab al-mandeb", "saudi-backed forces", "yemeni forces",
        "탈환 공세", "탈환작전", "탈환 작전", "반격", "되찾", "축출",
        "사우디 지원 예멘군", "예멘 정부군",
    ))
    return mokha and houthi and current


def _stale_mokha_capture_only(row):
    t = _text(row)
    mokha = any(x in t for x in ("mokha", "mocha", "al-makha", "목하", "모카"))
    houthi = any(x in t for x in ("houthi", "houthis", "후티"))
    capture = any(x in t for x in (
        "captured mokha", "seized mokha", "control of mokha", "took mokha",
        "목하를 점령", "모카를 점령", "목하 장악", "모카 장악",
    ))
    old = any(x in t for x in (
        "last month", "early september", "in september", "since september",
        "지난달", "9월 초", "9월에", "9월부터",
    ))
    return mokha and houthi and capture and old and not _mokha_counteroffensive_context(row)


def _tass_russian_strike_claim(row):
    src = " ".join([str(row.get("source", "")), str(row.get("link", ""))]).lower()
    t = _text(row)
    tass = "tass" in src
    exact = "2197955" in src
    actors = any(x in t for x in ("russian troops", "russian forces", "russian defense ministry", "러시아군", "러시아 국방부"))
    action = any(x in t for x in ("hit", "struck", "strike", "attacked", "destroyed", "타격", "공격"))
    objects = any(x in t for x in ("poltava", "odessa", "odesa", "radar", "data center", "데이터센터", "레이더"))
    return tass and (exact or (actors and action and objects))


def _tass_largest_drone_attack(row):
    src = " ".join([str(row.get("source", "")), str(row.get("link", ""))]).lower()
    t = _text(row)
    return "tass" in src and (
        "2197959" in src
        or (
            any(x in t for x in ("largest drone attack", "biggest drone attack", "최대 규모의 드론 공격", "최대 규모 드론 공격"))
            and any(x in t for x in ("2026", "tass calculation", "tass calculations", "tass 집계", "타스 집계"))
        )
    )


def emergency_marks(row):
    marks = list(_orig_emergency_marks(row))
    if _aramco_fire_unattributed(row):
        marks = [m for m in marks if m != "후티리야드미사일위협"]
    return sorted(set(marks))


prev._emergency_marks = emergency_marks


def marks(row):
    out = list(_orig_marks(row))
    if _aramco_houthi_claim(row):
        out.append("후티리야드아람코공격주장")
    if _future_refinery_policy(row):
        out.append("러정유시설보복공격확대예고")
    if _aramco_fire_unattributed(row):
        out.append("리야드아람코화재원인미확정")
    if _peace_conditions_commentary(row):
        out.append("러시아종전조건입장표명")
    if _lukoil_side_deal(row):
        out.append("루코일종전협상연계상업거래")
    if _hormuz_tanker_attack(row):
        out.append("호르무즈유조선피격클러스터")
    if _hormuz_on_peace_attack(row):
        out.append("호르무즈온피스유조선피격")
    if _iran_south_unattributed_explosions(row):
        out.append("이란남부폭발원인미확정")
    if _saudi_east_west_pipeline_recovery(row):
        out.append("사우디동서송유관회복")
    if _israel_oct7_abroad_warning(row):
        out.append("이스라엘10월7일해외공격위험경고")
    if _vance_iran_enrichment_condition(row):
        out.append("미국부통령이란농축종전조건")
    if _non_concrete_endgame_rhetoric(row):
        out.append("종전전망성발언")
    if _conditional_military_threat(row):
        out.append("조건부군사위협")
    if _saudi_riyadh_intercept_vs_claim(row):
        out.append("사우디리야드후티미사일요격확인")
    if _saudi_houthi_airport_refinery_cluster(row):
        out.append("사우디후티공항정유시설공격클러스터")
    if _aden_airport_attack_cluster(row):
        out.append("예멘아덴공항후티공격클러스터")
    if _mokha_counteroffensive_context(row):
        out.append("목하탈환공세")
    if _tass_russian_strike_claim(row):
        out.append("러시아국방부타격주장")
    if _tass_largest_drone_attack(row):
        out.append("TASS러시아최대드론공격집계")
    out = [m for m in out if not (_aramco_fire_unattributed(row) and m == "후티리야드미사일위협")]
    return sorted(set(out))


prev._marks = marks


def korean_title(ms):
    if "후티리야드아람코공격주장" in ms:
        return "후티, 리야드 Aramco 시설 미사일·드론 공격 주장 — 사우디·Aramco 독립 확인 대기"
    if "리야드아람코화재원인미확정" in ms:
        return "리야드 아람코 시설 인근 화재·연기 — 공격 여부·원인·배후 미확정"
    if "러정유시설보복공격확대예고" in ms:
        return "우크라이나, 러시아 정유시설 공격 확대 예고 — 실제 신규 피격 확인과 구분"
    if "러시아종전조건입장표명" in ms:
        return "메드베데프, 우크라이나 종전 조건 재확인 — 실제 합의 진전이 아닌 러시아 측 입장 표명"
    if "루코일종전협상연계상업거래" in ms:
        return "종전 협상 과정에서 루코일 해외자산 매각 논의 — 휴전 진전과 별개의 상업거래"
    if "사우디동서송유관회복" in ms:
        return "사우디 동서 송유관 재가동 — 하루 580만배럴 수송 회복, 호르무즈 우회 공급능력 개선"
    if "호르무즈온피스유조선피격" in ms:
        return "호르무즈 해협서 MT On Peace 발사체 피격 — 선원 12명 부상(인도인 11명), 오만으로 치료 이송·공격 주체 미확정"
    if "이란남부폭발원인미확정" in ms:
        return "이란 남부 시리크·게슘·미나브 일대 폭발음 — 원인·공격 주체 미확정, 발사체·공습 공식 확인 대기"
    if "호르무즈유조선피격클러스터" in ms:
        return "호르무즈 유조선 피격 지속 — 미확인 발사체·선박 피해를 실제 해상안보 사건으로 추적"
    if "이스라엘10월7일해외공격위험경고" in ms:
        return "이스라엘 국가안보회의, 10월 7일 3주년 전후 해외의 이스라엘인·유대인 대상 공격 위험 증가 경고 — 실제 공격 발생 아님"
    if "미국부통령이란농축종전조건" in ms:
        return "미국 부통령 JD Vance, 이란이 전쟁 종식을 원하면 우라늄 농축 능력을 의미 있게 감축해야 한다고 제시 — 미국 측 협상 조건, 합의 진전 아님"
    if "종전전망성발언" in ms:
        return "전쟁·분쟁 종식이 가까워졌다는 전망성 발언 — 구체적 휴전 합의·협상 재개·일정 확정 전에는 실제 진전으로 보지 않음"
    if "조건부군사위협" in ms:
        return "이란군, 필요할 경우 선제공격에 나설 수 있다고 경고 — 실제 공격 발생이 아닌 조건부 군사위협"
    if "사우디리야드후티미사일요격확인" in ms:
        return "사우디 주도 연합군, 리야드 북쪽 상공서 후티 탄도미사일 요격 확인 — 후티의 리야드 공항 등 타격 주장은 사우디 확인 전"
    if "예멘아덴공항후티공격클러스터" in ms:
        return "후티, 예멘 아덴 국제공항에 탄도미사일·드론 공격 — 동일 사건의 매체별 재보도는 1건으로 묶음"
    if "목하탈환공세" in ms:
        return "사우디 지원 예멘군, 후티가 장악했던 목하·바브엘만데브 일대 탈환 공세 — 후티의 9월 점령은 배경"
    if "러시아국방부타격주장" in ms:
        return "러시아 국방부, 폴타바·오데사 등에서 우크라이나군 레이더·데이터센터를 타격했다고 주장 — 독립 확인 전"
    if "TASS러시아최대드론공격집계" in ms:
        return "TASS 집계: 러시아가 2026년 최대 규모 드론 공격을 받았다고 보도 — 세부 피해·귀속은 추가 확인"
    return _orig_korean_title(ms)


prev._korean_title = korean_title


def signals(ms):
    out = []
    if "후티리야드아람코공격주장" in ms:
        out.append("🔴 후티가 리야드 Aramco 시설을 탄도미사일·드론으로 공격했다고 주장 — 현장 화재·연기와 별개로 사우디·Aramco의 피해·요격·원인 공식 확인은 후속 검증")
    if "리야드아람코화재원인미확정" in ms:
        out.append("🟡 Reuters는 리야드 Aramco 시설 인근 화재·연기를 확인했지만 당시 공격 여부·원인·배후는 공식 확인 전")
    if "러정유시설보복공격확대예고" in ms:
        out.append("🟡 젤렌스키의 러시아 정유시설 공격 확대 방침·보복 예고 — 실제 신규 정유시설 피격·화재·가동중단과 분리")
    if "러시아종전조건입장표명" in ms:
        out.append("🟡 메드베데프가 우크라이나 평화 조건을 재확인한 입장 표명 — 회담 타결·휴전 합의로 승격하지 않음")
    if "루코일종전협상연계상업거래" in ms:
        out.append("🟡 푸틴·미 특사 간 루코일 해외자산 매각 논의 — 종전회담과 같은 자리에서 논의됐지만 휴전 진전 자체는 아님")
    if "호르무즈온피스유조선피격" in ms:
        out.append("🔴 MT On Peace가 호르무즈 해협에서 발사체에 피격돼 선원 12명이 부상(인도인 11명) — 오만 당국이 치료 이송, 공격 주체는 미확정")
    elif "호르무즈유조선피격클러스터" in ms:
        out.append("🔴 UKMTO 기준 호르무즈·오만 인근 유조선의 미확인 발사체 피격이 반복 — 동일 사건 재인용과 실제 추가 피격을 분리")
    if "이란남부폭발원인미확정" in ms:
        out.append("🟡 이란 남부 시리크·게슘·미나브 일대에서 복수 폭발음 보도 — 원인·공격 주체가 확인되기 전에는 실제 공습·피격으로 승격하지 않음")
    if "사우디동서송유관회복" in ms:
        out.append("🟢 사우디 동서 송유관 원유 수송이 하루 580만배럴 수준으로 회복 — 과거 공격의 현재 신규 확전이 아니라 실물 공급 복구 신호")
    if "이스라엘10월7일해외공격위험경고" in ms:
        out.append("🟡 이스라엘 국가안보회의가 10월 7일 3주년 전후 해외 공격 위험 증가를 경고 — 실제 공격 발생과는 구분")
    if "미국부통령이란농축종전조건" in ms:
        out.append("🟡 미국 부통령 JD Vance가 이란의 우라늄 농축 능력 감축을 전쟁 종식 조건으로 제시 — 미국 측 협상 조건이며 합의 진전 자체는 아님")
    if "종전전망성발언" in ms:
        out.append("🟡 종전이 가까워졌다는 평가·전망 — 구체적 합의문, 협상 재개, 회담 일정이 확인되기 전에는 실제 종전 진전으로 승격하지 않음")
    if "조건부군사위협" in ms:
        out.append("🟡 이란군의 선제공격 가능성 경고 — 조건부·미래형 발언이며 실제 공격 개시와 분리")
    if "사우디리야드후티미사일요격확인" in ms:
        out.append("🔴 사우디 주도 연합군이 리야드 북쪽에서 후티 탄도미사일 요격을 확인 — 후티의 킹칼리드 국제공항 등 타격 주장은 사우디 확인 전")
    if "예멘아덴공항후티공격클러스터" in ms:
        out.append("🔴 예멘 교통부 기준 후티가 아덴 국제공항을 탄도미사일·드론으로 공격 — 동일 사건의 연합뉴스TV·KBS 등 재보도는 중복 송출하지 않음")
    if "목하탈환공세" in ms:
        out.append("🔴 현재 변화는 사우디 지원 예멘군의 목하·바브엘만데브 탈환 공세 — 후티의 9월 목하 점령을 신규 속보로 재사용하지 않음")
    if "러시아국방부타격주장" in ms:
        out.append("🔴 러시아 국방부가 폴타바·오데사 등에서 레이더·데이터센터를 타격했다고 주장 — TASS 중계이며 독립 확인 전")
    if "TASS러시아최대드론공격집계" in ms:
        out.append("🔴 TASS 집계로 러시아의 2026년 최대 규모 드론 공격 보도 — 피해·발사 주체·규모는 독립 자료로 추가 확인")

    # 이 게이트에서 의미를 확정한 사건은 상위 모듈의 범용 신호를 덧붙이지 않는다.
    # 그래야 '공격 확대 예고'가 '실제 피격', '상업거래'가 '휴전 진전'으로 다시 오염되지 않는다.
    custom = {
        "후티리야드아람코공격주장", "리야드아람코화재원인미확정",
        "러정유시설보복공격확대예고", "러시아종전조건입장표명",
        "루코일종전협상연계상업거래", "호르무즈유조선피격클러스터",
        "이스라엘10월7일해외공격위험경고", "호르무즈온피스유조선피격",
        "미국부통령이란농축종전조건", "사우디리야드후티미사일요격확인",
        "이란남부폭발원인미확정", "사우디동서송유관회복",
        "목하탈환공세", "러시아국방부타격주장", "TASS러시아최대드론공격집계",
        "예멘아덴공항후티공격클러스터", "종전전망성발언", "조건부군사위협",
    }
    if set(ms) & custom:
        return out
    return _orig_signals(ms)


prev._signals = signals


def score_item(row, now):
    # 송출 직전 품질게이트(3시간)와 후보 선별 기준을 동일하게 맞춘다.
    # 공개시각을 확인하지 못한 기사는 "신규/속보"로 승격하지 않는다.
    age = watch.age_minutes(row, now)
    fresh_limit = int(getattr(prev, "FRESH_NEWS_MAX_MINUTES", 3 * 60))
    if age is None:
        return 0, []
    if age > fresh_limit:
        return 0, []
    if (
        _trump_la_sd_hypothetical(row)
        or _stale_mokha_capture_only(row)
        or _tass_turkmenistan_visit_noise(row)
        or _south_korea_russia_fuel_background(row)
    ):
        return 0, []
    score, tags = _orig_score_item(row, now)
    ms = set(marks(row))
    tags = list(tags or [])
    yellow = {
        "러정유시설보복공격확대예고", "리야드아람코화재원인미확정",
        "러시아종전조건입장표명", "루코일종전협상연계상업거래",
        "이스라엘10월7일해외공격위험경고", "이란남부폭발원인미확정",
        "종전전망성발언", "조건부군사위협",
    }
    if ms & yellow:
        tags = [t for t in tags if t not in ("확전", "휴전·평화", "재건", "종전·협상")]
        tags += ["협상·위협제약"]
        score = max(score, 98)
    if "러정유시설보복공격확대예고" in ms:
        tags += ["우크라이나·러시아", "확전위험", "공격확대예고"]
    if "후티리야드아람코공격주장" in ms:
        tags = [t for t in tags if t not in ("휴전·평화", "재건", "종전·협상")]
        tags += ["사우디·후티", "확전", "Aramco", "공격주장", "공식확인대기"]
        score = max(score, 100)
    if "리야드아람코화재원인미확정" in ms:
        tags += ["사우디·아람코", "에너지시설위험", "원인미확정"]
    if "러시아종전조건입장표명" in ms:
        tags += ["우크라이나·러시아", "종전조건", "입장표명"]
    if "루코일종전협상연계상업거래" in ms:
        tags += ["우크라이나·러시아", "협상연계상업거래", "이해충돌점검"]
    if "이스라엘10월7일해외공격위험경고" in ms:
        row["title_ko"] = korean_title(ms)
        tags = [t for t in tags if t not in ("확전", "휴전·평화", "재건", "종전·협상")]
        tags += ["이스라엘", "해외안보경고", "실제공격아님"]
        score = max(score, 98)
    if "미국부통령이란농축종전조건" in ms:
        row["title_ko"] = korean_title(ms)
        row["signals_ko"] = []
        tags = [t for t in tags if t not in ("확전", "휴전·평화", "재건", "종전·협상")]
        tags += ["미국·이란", "협상조건", "합의진전아님", "JD Vance"]
        score = max(score, 98)
    if "종전전망성발언" in ms:
        row["title_ko"] = korean_title(ms)
        row["signals_ko"] = []
        tags = [t for t in tags if t not in ("확전", "휴전·평화", "재건", "종전·협상")]
        tags += ["전망성발언", "합의진전아님"]
        score = max(score, 98)
    if "조건부군사위협" in ms:
        row["title_ko"] = korean_title(ms)
        row["signals_ko"] = []
        tags = [t for t in tags if t not in ("확전", "휴전·평화", "재건", "종전·협상")]
        tags += ["군사위협", "조건부발언", "실제공격아님"]
        score = max(score, 98)
    if "사우디리야드후티미사일요격확인" in ms:
        row["title_ko"] = korean_title(ms)
        row["signals_ko"] = []
        tags = [t for t in tags if t not in ("휴전·평화", "재건", "종전·협상")]
        tags += ["사우디·후티", "확전", "미사일요격확인", "공항타격주장미확인"]
        score = max(score, 100)
    if "예멘아덴공항후티공격클러스터" in ms:
        row["title_ko"] = korean_title(ms)
        row["signals_ko"] = []
        tags = [t for t in tags if t not in ("휴전·평화", "재건", "종전·협상")]
        tags += ["예멘·후티", "확전", "아덴국제공항", "민간항공위험"]
        score = max(score, 100)
    if "이란남부폭발원인미확정" in ms:
        row["title_ko"] = korean_title(ms)
        row["signals_ko"] = []
        tags = [t for t in tags if t not in ("확전", "휴전·평화", "재건", "종전·협상")]
        tags += ["이란·호르무즈", "원인미확정", "공식확인대기"]
        score = max(score, 98)
    if "사우디동서송유관회복" in ms:
        row["title_ko"] = korean_title(ms)
        row["signals_ko"] = []
        tags = [t for t in tags if t not in ("확전", "휴전·평화", "재건", "종전·협상", "에너지위험", "반대신호")]
        tags += ["사우디", "실물공급회복", "원유수송회복", "580만배럴"]
        score = max(score, 100)
    if "호르무즈온피스유조선피격" in ms:
        row["title_ko"] = korean_title(ms)
        row["signals_ko"] = []
        tags = [t for t in tags if t not in ("휴전·평화", "재건", "종전·협상")]
        tags += ["이란·호르무즈", "확전", "해상안보", "유조선피격", "MT On Peace", "선원12명부상"]
        score = max(score, 100)
    if "호르무즈유조선피격클러스터" in ms:
        tags = [t for t in tags if t not in ("휴전·평화", "재건", "종전·협상")]
        tags += ["이란·호르무즈", "확전", "해상안보", "유조선피격"]
        score = max(score, 100)
    if "목하탈환공세" in ms:
        row["title_ko"] = korean_title(ms)
        row["signals_ko"] = []
        tags = [t for t in tags if t not in ("휴전·평화", "재건", "종전·협상")]
        tags += ["예멘·후티", "확전", "해상병목", "탈환공세"]
        score = max(score, 100)
    if "러시아국방부타격주장" in ms:
        row["title_ko"] = korean_title(ms)
        row["signals_ko"] = []
        tags = [t for t in tags if t not in ("휴전·평화", "재건", "종전·협상")]
        tags += ["우크라이나·러시아", "확전", "러시아측주장", "독립확인대기"]
        score = max(score, 100)
    if "TASS러시아최대드론공격집계" in ms:
        row["title_ko"] = korean_title(ms)
        row["signals_ko"] = []
        tags = [t for t in tags if t not in ("휴전·평화", "재건", "종전·협상")]
        tags += ["우크라이나·러시아", "확전", "TASS집계", "독립확인필요"]
        score = max(score, 100)
    if _kyiv_bridge_attack(row) or _kyiv_evacuation_strike_warning(row):
        tags = [t for t in tags if t not in ("휴전·평화", "재건", "종전·협상")]
        tags += ["우크라이나·러시아", "확전", "인프라위험"]
        score = max(score, 100)
    return min(score, 100), sorted(set(tags))


watch.score_item = score_item


def _stable_source_url(row):
    raw = (row.get("resolved_url") or row.get("link") or "").strip()
    if not raw:
        return None
    try:
        p = urllib.parse.urlparse(raw)
        host = p.netloc.lower().replace("www.", "")
        path = re.sub(r"/+$", "", p.path or "/")
        if any(x in host for x in ("reuters.com", "apnews.com", "ukmto.org")) and path:
            return host + path.lower()
    except Exception:
        return None
    return None


def item_id(row):
    if _conditional_military_threat(row):
        return hashlib.sha256(("event|conditional-military-threat|" + _published_day(row)).encode()).hexdigest()[:20]
    if _non_concrete_endgame_rhetoric(row):
        return hashlib.sha256(("event|endgame-rhetoric|" + _published_day(row)).encode()).hexdigest()[:20]
    if _aden_airport_attack_cluster(row):
        return hashlib.sha256(("event|yemen-houthi|aden-airport-attack|" + _published_day(row)).encode()).hexdigest()[:20]
    if _vance_iran_enrichment_condition(row):
        return hashlib.sha256(("event|us-iran|vance-enrichment-condition|" + _published_day(row)).encode()).hexdigest()[:20]
    if _saudi_riyadh_intercept_vs_claim(row):
        return hashlib.sha256(("event|saudi-houthi|riyadh-missile-intercept|" + _published_day(row)).encode()).hexdigest()[:20]
    if _saudi_east_west_pipeline_recovery(row):
        return hashlib.sha256("event|saudi|east-west-pipeline-recovery|2026-10-06".encode()).hexdigest()[:20]
    if _hormuz_on_peace_attack(row):
        return hashlib.sha256("event|hormuz|mt-on-peace|2026-10-06".encode()).hexdigest()[:20]
    if _iran_south_unattributed_explosions(row):
        key = f"iran-south|unattributed-explosions|{_published_day(row)}"
        return hashlib.sha256(("event|" + key).encode()).hexdigest()[:20]
    if _saudi_houthi_airport_refinery_cluster(row):
        key = f"saudi-houthi|airport-refinery-attack|{_cluster_day(row, 12)}"
        if _new_saudi_houthi_attack_variant(row):
            norm = re.sub(r"\W+", " ", _title(row)).strip()
            key += "|additional|" + norm[:80]
        return hashlib.sha256(("event|" + key).encode()).hexdigest()[:20]
    if _israel_oct7_abroad_warning(row):
        key = f"israel|oct7-abroad-warning|{_published_day(row)}"
        return hashlib.sha256(("event|" + key).encode()).hexdigest()[:20]
    if _hormuz_tanker_attack(row):
        key = f"hormuz|tanker-attack-cluster|{_published_day(row)}"
        if _new_tanker_attack_variant(row):
            norm = re.sub(r"\W+", " ", _title(row)).strip()
            key += "|additional|" + norm[:80]
        return hashlib.sha256(("event|" + key).encode()).hexdigest()[:20]
    if _future_refinery_policy(row):
        return hashlib.sha256(("event|ukraine-russia|refinery-retaliation-policy|" + _week_key()).encode()).hexdigest()[:20]
    if _lukoil_side_deal(row):
        return hashlib.sha256(("event|ukraine-russia|lukoil-side-deal|" + _week_key()).encode()).hexdigest()[:20]
    if _aramco_fire_unattributed(row):
        return hashlib.sha256(("event|saudi-aramco|riyadh-unattributed-fire|" + _published_day(row)).encode()).hexdigest()[:20]
    if _peace_conditions_commentary(row):
        return hashlib.sha256(("event|ukraine-russia|peace-conditions-commentary|" + _published_day(row)).encode()).hexdigest()[:20]
    stable = _stable_source_url(row)
    if stable:
        return hashlib.sha256(("url|" + stable).encode()).hexdigest()[:20]
    return _orig_item_id(row)


watch.item_id = item_id


def topic_label(row):
    ms = set(marks(row))
    if "후티리야드아람코공격주장" in ms:
        return "사우디·후티 · Aramco 공격 주장"
    if "리야드아람코화재원인미확정" in ms:
        return "사우디·아람코 · 화재 원인 미확정"
    if "러정유시설보복공격확대예고" in ms:
        return "우크라이나·러시아 · 정유시설 보복 공격 예고"
    if "러시아종전조건입장표명" in ms:
        return "우크라이나·러시아 · 종전 조건 입장"
    if "루코일종전협상연계상업거래" in ms:
        return "우크라이나·러시아 · 종전협상 연계 상업거래"
    if "호르무즈온피스유조선피격" in ms:
        return "이란·호르무즈 · MT On Peace 피격"
    if "이란남부폭발원인미확정" in ms:
        return "이란 남부 · 폭발 원인 미확정"
    if "호르무즈유조선피격클러스터" in ms:
        return "이란·호르무즈 · 유조선 피격"
    if "이스라엘10월7일해외공격위험경고" in ms:
        return "이스라엘 · 10월 7일 해외 공격 위험 경고"
    if "미국부통령이란농축종전조건" in ms:
        return "미국·이란 · 종전 협상 조건"
    if "종전전망성발언" in ms:
        return "전쟁·외교 · 종전 전망성 발언"
    if "조건부군사위협" in ms:
        return "이란 · 조건부 선제공격 경고"
    if "사우디리야드후티미사일요격확인" in ms:
        return "사우디·후티 · 리야드 미사일 요격"
    if "예멘아덴공항후티공격클러스터" in ms:
        return "예멘·후티 · 아덴 국제공항 공격"
    if "사우디동서송유관회복" in ms:
        return "사우디 · 동서 송유관 공급회복"
    if "사우디후티공항정유시설공격클러스터" in ms:
        return "사우디·후티"
    if "목하탈환공세" in ms:
        return "예멘·후티·바브엘만데브 · 탈환 공세"
    if "러시아국방부타격주장" in ms:
        return "우크라이나·러시아 · 러시아 국방부 타격 주장"
    if "TASS러시아최대드론공격집계" in ms:
        return "우크라이나·러시아 · 대규모 드론 공격"
    return _orig_topic_label(row)


watch.topic_label = topic_label
try:
    prev.clean_mod.clean_topic_label = topic_label
except Exception:
    pass


def final_color(row):
    ms = set(marks(row))
    if "사우디동서송유관회복" in ms:
        return "green"
    if "후티리야드아람코공격주장" in ms:
        return "red"
    if "사우디리야드후티미사일요격확인" in ms:
        return "red"
    if "예멘아덴공항후티공격클러스터" in ms:
        return "red"
    if "미국부통령이란농축종전조건" in ms:
        return "yellow"
    if "종전전망성발언" in ms:
        return "yellow"
    if "조건부군사위협" in ms:
        return "yellow"
    if ms & {
        "러정유시설보복공격확대예고", "리야드아람코화재원인미확정",
        "러시아종전조건입장표명", "루코일종전협상연계상업거래",
        "이스라엘10월7일해외공격위험경고", "이란남부폭발원인미확정",
    }:
        return "yellow"
    if "호르무즈온피스유조선피격" in ms:
        return "red"
    if "호르무즈유조선피격클러스터" in ms:
        return "red"
    if ms & {"목하탈환공세", "러시아국방부타격주장", "TASS러시아최대드론공격집계"}:
        return "red"
    if _kyiv_bridge_attack(row) or _kyiv_evacuation_strike_warning(row):
        return "red"
    return _orig_final_color(row)


prev._final_item_color = final_color
prev._emergency_color = final_color
guard._enhanced_body_color = final_color
guard.prev._strict_body_color = final_color
guard.prev.core._body_color = final_color


_PEACE_MARKS = {
    "아라치위트코프뉴욕회동확인", "이란뉴욕대표단외교전권", "뉴욕중재종전합의안협의",
    "미구체조치시외교재개환영", "이란직접협상확인", "정식휴전합의", "종전합의",
    "크렘린에너지휴전긍정평가", "아라치미국체류추가협상",
}


def verdict(items):
    colors = [final_color(x) for x in items]
    red = "red" in colors
    yellow = "yellow" in colors
    all_marks = {m for x in items for m in marks(x)}
    peace = bool(all_marks & _PEACE_MARKS)
    supply_recovery = "사우디동서송유관회복" in all_marks
    if any(_kyiv_bridge_attack(x) or _kyiv_evacuation_strike_warning(x) for x in items):
        red = True
    if red and supply_recovery:
        return (
            "<b>투자 판정</b>\n"
            "- <b>핵심:</b> 실제 공격·해상안보 위험은 지속되지만 사우디 동서 송유관 수송은 하루 580만배럴 수준으로 회복\n"
            "- <b>현재 단계:</b> 군사 위험과 실물 공급 회복이 동시에 존재 — 과거 공격과 현재 재가동을 같은 확전 신호로 합치지 않음\n"
            "- <b>시장:</b> 해운·보험 위험프리미엄은 남지만 원유 공급 차질 압력은 일부 완화\n"
            "- <b>다음:</b> 송유관 지속 가동 → 얀부 선적 → 추가 공격 여부 → 실제 수출 물량"
        )
    if red and peace:
        return (
            "<b>투자 판정</b>\n"
            "- <b>핵심:</b> 실제 공격과 구체적 외교 진전이 동시에 존재\n"
            "- <b>현재 단계:</b> 혼재 단계 — 협상 문구보다 실제 교전 감소·합의 이행이 우선\n"
            "- <b>시장:</b> 군사 위험과 완화 기대가 충돌해 유가·해운·보험 변동성이 확대될 수 있음\n"
            "- <b>다음:</b> 실제 공격 빈도 → 공식 합의문 → 이행 여부"
        )
    if red:
        return (
            "<b>투자 판정</b>\n"
            "- <b>핵심:</b> 신규 변화의 중심은 실제 공격·해상안보·운영 위험\n"
            "- <b>현재 단계:</b> 군사·안보 위험 지속 — 상업거래나 조건 제시를 휴전 진전으로 보지 않음\n"
            "- <b>시장:</b> 유가·해운·보험 위험프리미엄 상승 압력\n"
            "- <b>다음:</b> 추가 공격 → 시설·선박 피해 → 운항 제한 → 실제 교전 강도"
        )
    if yellow:
        return (
            "<b>투자 판정</b>\n"
            "- <b>핵심:</b> 공격 확대 예고·협상 조건·원인 미확정 위험·상업거래를 실제 공격이나 휴전 진전과 분리\n"
            "- <b>현재 단계:</b> 경계·협상 제약 단계 — 실제 행동 확인 전 방향성 과대평가 금지\n"
            "- <b>시장:</b> 확인 전에는 위험프리미엄의 방향보다 변동성 확대 요인\n"
            "- <b>다음:</b> 실제 공격 발생 → 공식 책임 확인 → 협상 결과 → 운영 영향"
        )
    return _orig_verdict(items)


guard._verdict = verdict


def semantic_fix(text):
    text = _orig_semantic_fix(text)
    lines = text.splitlines()
    item_re = re.compile(r"^(?:[🔴🟢🟡]\s+)?\[(속보|신규|후속)\]\s+<b>(\d+)\.\s+([^<]+)</b>")
    positions = [i for i, line in enumerate(lines) if item_re.search(line)]
    rendered = []
    for n, i in enumerate(positions):
        end = positions[n + 1] if n + 1 < len(positions) else len(lines)
        for j in range(i + 1, end):
            if lines[j] in ("<b>시장 파급</b>", "<b>시장 반응</b>", "<b>투자 판정</b>"):
                end = j
                break
        block = "\n".join(lines[i:end]).lower()
        m = item_re.search(lines[i])
        if not m:
            continue
        level, idx = m.group(1), m.group(2)
        marker = None
        topic = None
        if any(x in block for x in ("동서 송유관 재가동", "하루 580만배럴 수송 회복", "실물 공급 복구 신호")):
            marker, topic = "🟢", "사우디 · 동서 송유관 공급회복"
        elif any(x in block for x in ("리야드 aramco 시설 미사일·드론 공격 주장", "리야드 aramco 시설을 탄도미사일·드론으로 공격했다고 주장")):
            marker, topic = "🔴", "사우디·후티 · Aramco 공격 주장"
        elif any(x in block for x in ("mt on peace", "선원 12명 부상(인도인 11명)")):
            marker, topic = "🔴", "이란·호르무즈 · MT On Peace 피격"
        elif any(x in block for x in ("원인·공격 주체 미확정", "원인 미확정 단계, 발사체·공습 확인 여부 추적")) and any(x in block for x in ("시리크", "게슘", "미나브")):
            marker, topic = "🟡", "이란 남부 · 폭발 원인 미확정"
        elif any(x in block for x in ("유조선 피격 지속", "유조선 잇달아 피격", "유조선 2척 피격")):
            marker, topic = "🔴", "이란·호르무즈 · 유조선 피격"
        elif any(x in block for x in ("정유시설 공격 확대 예고", "실제 신규 피격 확인과 구분")):
            marker, topic = "🟡", "우크라이나·러시아 · 정유시설 보복 공격 예고"
        elif any(x in block for x in ("아람코 시설 인근 화재·연기", "공격 여부·원인·배후 미확정")):
            marker, topic = "🟡", "사우디·아람코 · 화재 원인 미확정"
        elif any(x in block for x in ("종전 조건 재확인", "실제 합의 진전이 아닌 러시아 측 입장 표명")):
            marker, topic = "🟡", "우크라이나·러시아 · 종전 조건 입장"
        elif any(x in block for x in ("루코일 해외자산 매각", "휴전 진전과 별개의 상업거래")):
            marker, topic = "🟡", "우크라이나·러시아 · 종전협상 연계 상업거래"
        elif any(x in block for x in ("10월 7일 3주년 전후 해외", "oct. 7 anniversary", "october 7 anniversary")):
            marker, topic = "🟡", "이스라엘 · 10월 7일 해외 공격 위험 경고"
        elif (
            " · 확전" in block
            or any(x in block for x in (
                "strikes on", "bridge attack", "bridge strikes", "massive retaliatory strikes",
                "미사일 공격", "드론 공격", "공습", "피격", "보복 공습", "대규모 보복",
            ))
        ):
            marker = "🔴"
            topic = m.group(3).strip()
        if marker:
            lines[i] = f"{marker} [{level}] <b>{idx}. {topic}</b>"
            rendered.append((marker, block))

    if rendered:
        lines = [line for line in lines if not (
            "<b>공격·확전</b>" in line or "<b>재건·휴전</b>" in line or
            "<b>실물 공급회복</b>" in line or "<b>협상 제약·불확실성</b>" in line or
            "<b>군사위협·협상 제약</b>" in line
        )]
        badges = []
        all_headers = "\n".join(lines).lower()
        has_red_line = bool(re.search(r"(?m)^🔴\s+\[(?:속보|신규|후속)\]", all_headers))
        has_green_line = bool(re.search(r"(?m)^🟢\s+\[(?:속보|신규|후속)\]", all_headers))
        has_yellow_line = bool(re.search(r"(?m)^🟡\s+\[(?:속보|신규|후속)\]", all_headers))
        if any(m == "🔴" for m, _ in rendered) or has_red_line:
            badges.append("🔴 <b>공격·확전</b>")
        if has_green_line:
            if any(x in all_headers for x in ("실물물동량", "원유공급회복", "원유 물동량 회복")):
                badges.append("🟢 <b>실물 공급회복</b>")
            else:
                badges.append("🟢 <b>재건·휴전</b>")
        if any(m == "🟡" for m, _ in rendered) or has_yellow_line:
            badges.append("🟡 <b>군사위협·협상 제약</b>")
        if badges and lines:
            lines.insert(1, "  |  ".join(dict.fromkeys(badges)))
    return "\n".join(lines)


prev._semantic_output_fix = semantic_fix


def verify_alert(test_mode=False):
    _orig_verify_alert(test_mode=test_mode)
    if not watch.ALERT.exists():
        return
    text = watch.ALERT.read_text(encoding="utf-8")
    low = text.lower()
    issues = []
    if "후티의 리야드 탄도미사일 공격·요격 신호" in text and "fire-smoke-seen-near-aramco" in low:
        issues.append("아람코 원인 미확정 화재를 후티 미사일 공격으로 귀속")
    if "🟢" in text and any(x in low for x in ("루코일 해외자산 매각", "석유업체 빅딜")):
        issues.append("상업거래를 휴전 진전으로 표시")
    if "🔴" in text and "정유시설 공격 확대 예고" in text:
        issues.append("미래 공격 예고를 실제 피격으로 표시")
    if "🔴" in text and "종전 조건 재확인" in text:
        issues.append("종전 조건 입장표명을 실제 확전으로 표시")
    if "후티가 전략항 목하를 점령" in text or "후티가 전략항 모카를 점령" in text:
        issues.append("후티의 과거 목하 점령을 신규 현재 사건으로 재사용")
    if ("로스앤젤레스" in text and "샌디에이고" in text and ("파괴될 수도" in text or "take out los angeles" in low)):
        issues.append("트럼프의 가정적 정치 발언을 실제 군사 신규 변화로 표시")
    if "tass.com/defense/2197955" in low and ("러시아 국방부" not in text or "주장" not in text):
        issues.append("TASS 러시아 국방부 타격 주장을 독립 확인된 사실처럼 표시")
    if "tass.com/defense/2197955" in low and "독립 확인 전" not in text:
        issues.append("TASS 러시아 국방부 타격 주장에 독립확인 상태 누락")
    if "tass.com/politics/2197959" in low and ("TASS 집계" not in text or "독립 확인" not in text):
        issues.append("TASS 드론 규모 집계를 확정 사실처럼 표시")
    if ("라빅" in text and "정유시설" in text and "후티" in text) and "주장 단계" not in text:
        issues.append("라빅 정유시설 공격을 후티 주장 단계와 사우디 확인 피해로 분리하지 않음")
    if "tass.com/politics/2198439" in low:
        issues.append("투르크메니스탄 CIS·카스피 정상 일정 기사를 종전·협상 신규 변화로 표시")
    if "2198519" in low and ("미국 부통령" not in text or "협상 조건" not in text):
        issues.append("이란 농축 조건 발언의 미국 부통령 JD Vance 귀속 또는 협상조건 성격 누락")
    if "후티의 리야드 탄도미사일 공격·요격 신호" in text:
        issues.append("리야드 미사일 요격 확인과 후티의 공항 타격 주장을 혼합 표시")
    if "승무원이 선박에 불을 붙였" in text:
        issues.append("Reuters 유조선 제목 문법을 오역해 승무원이 방화한 것으로 표시")
    if "10월을 앞두고 해외 공격 위험 경고 7주년" in text:
        issues.append("이스라엘 10월 7일 3주년 해외 공격위험 경고 제목을 오역")
    if re.search(r"(?ms)^🔴\s+\[(?:속보|신규|후속)\]\s+<b>\d+\.[^<]*</b>\n[^\n]*(?:10월 7일 3주년|해외 공격 위험 증가 경고)", text):
        issues.append("이스라엘의 해외 공격위험 경고를 실제 공격·확전으로 표시")
    if re.search(r"(?ms)^🔴\s+\[(?:속보|신규|후속)\]\s+<b>\d+\.[^<]*</b>\n[^\n]*(?:시리크|게슘|미나브)[^\n]*(?:원인 미확정|원인·공격 주체 미확정)", text):
        issues.append("이란 남부 원인 미확정 폭발음을 실제 공격·확전으로 표시")
    if ("mt on peace" in low or "온 피스" in text) and "12명" in text and "부상" in text and "공격 주체" not in text:
        issues.append("MT On Peace 피격의 피해·공격주체 확인 수준을 구분하지 않음")
    if "south-korea-exports-eased-russia-fuel-crisis-caused-by-drone-strikes-ukraine-2026-10-06" in low:
        issues.append("과거 러시아 연료위기·한국 수출 배경기사를 신규 확전으로 표시")
    if "드론이 불가리아에서 침몰" in text:
        issues.append("Reuters 불가리아 흑해 선박 드론 공격 제목을 문법 오역")
    if "AMRY" in text or "amry" in low:
        issues.append("Iran Army 원문 오탈자를 번역 과정에서 그대로 노출")
    if re.search(r"(?ms)^🔴\s+\[(?:속보|신규|후속)\].*?(?:선제공격|선제 공격).*?(?:필요한 경우|필요할 경우|필요시|조건부)", text):
        issues.append("조건부 선제공격 경고를 실제 공격·확전으로 표시")
    if "공개시각 확인 필요" in text:
        issues.append("공개시각을 확인하지 못한 기사를 신규·속보 알림으로 송출")
    stale_ages = [int(x) for x in re.findall(r"(\d{3,})분 전", text)]
    if any(x > int(getattr(prev, "FRESH_NEWS_MAX_MINUTES", 3 * 60)) for x in stale_ages):
        issues.append("3시간을 초과한 오래된 기사가 신규·후속 알림으로 송출됨")
    if re.search(r"(?ms)^🔴\s+\[(?:속보|신규|후속)\]\s+<b>\d+\.[^<]*</b>\n[^\n]*(?:동서 송유관|580만배럴)[^\n]*(?:회복|재가동)", text):
        issues.append("사우디 동서 송유관 공급회복을 신규 확전으로 표시")
    aden_blocks = re.findall(r"(?ms)^[🔴🟢🟡]?\s*\[(?:속보|신규|후속)\]\s+<b>\d+\.[^<]*</b>\n[^\n]*(?:아덴 국제공항|aden international airport)[^\n]*(?:미사일|공격|공습|missile|attack)", text, flags=re.I)
    if len(aden_blocks) > 1:
        issues.append("동일 아덴 국제공항 공격을 매체별 재보도로 중복 송출")
    if issues:
        raise RuntimeError("WAR_OCT04_QUALITY_GATE: " + " | ".join(issues))


runner.verify_alert = verify_alert


def _rendered_item_count(text):
    return len(re.findall(r"(?m)^[🔴🟢🟡]?\s*\[(?:속보|신규|후속)\]\s+<b>\d+\.", text or ""))


def _sync_pending_to_rendered_alert():
    """Telegram 본문에 실제 포함된 항목만 seen 처리되도록 pending을 맞춘다.

    최종 렌더링은 Telegram 길이 제한 때문에 뒤쪽 항목이 잘릴 수 있다.
    잘린 항목까지 seen으로 확정하면 다음 실행에서 영구 누락되므로,
    전송 직전 pending ID를 실제 렌더링된 항목 수에 맞춰 줄인다.
    """
    if not watch.ALERT.exists() or not watch.PENDING.exists():
        return
    alert_text = watch.ALERT.read_text(encoding="utf-8")
    rendered = _rendered_item_count(alert_text)
    pending = json.loads(watch.PENDING.read_text(encoding="utf-8"))
    ids = list(pending.get("ids", []))
    if not ids:
        return
    if rendered <= 0:
        raise RuntimeError("WAR_OCT04_DELIVERY_GATE: alert exists but no rendered items")
    if rendered < len(ids):
        pending["ids"] = ids[:rendered]
        pending["deferred_ids"] = ids[rendered:]
        pending["rendered_count"] = rendered
        watch.PENDING.write_text(json.dumps(pending, ensure_ascii=False), encoding="utf-8")


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
    _sync_pending_to_rendered_alert()
    runner.verify_alert(test_mode=False)


if __name__ == "__main__":
    main()
